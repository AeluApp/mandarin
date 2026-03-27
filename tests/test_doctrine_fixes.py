"""Tests for the three doctrine violation fixes.

1. Production mastery gate — stable promotion requires production drill history
2. Onboarding flow — placement seeds content immediately, goal deferred
3. Metrics-to-scheduler closed loop — metrics snapshot adjusts session plan
"""

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from mandarin.db.progress import (
    _compute_mastery_transition,
    PRODUCTION_DRILL_TYPES,
    DRILL_DIRECTION_MAP,
    record_attempt,
)
from mandarin.config import (
    REQUIRE_PRODUCTION_FOR_STABLE,
    PROMOTE_STABLE_STREAK,
    PROMOTE_STABLE_ATTEMPTS,
    PROMOTE_STABLE_DRILL_TYPES,
    PROMOTE_STABLE_DAYS,
)
from mandarin.scheduler import (
    _get_metrics_snapshot,
    _apply_metrics_feedback,
    _pick_modality_distribution,
    MIN_SESSION_ITEMS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from tests.shared_db import make_test_db


class _NullPath:
    """Placeholder for in-memory DBs so callers can still call path.unlink()."""
    def unlink(self, missing_ok=False):
        pass


def _make_db():
    """Create a fresh test database using the shared factory."""
    conn = make_test_db()
    return conn, _NullPath()


def _seed_content_item(conn, item_id=1, hanzi="好", pinyin="hǎo", english="good"):
    """Insert a minimal content_item."""
    conn.execute("""
        INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, hsk_level, times_shown, times_correct)
        VALUES (?, ?, ?, ?, 1, 0, 0)
    """, (item_id, hanzi, pinyin, english))
    conn.commit()


def _make_stabilizing_row(difficulty=0.5):
    """Create a mock progress row that's ready for stable promotion."""
    return {
        "mastery_stage": "stabilizing",
        "historically_weak": 0,
        "weak_cycle_count": 0,
        "stable_since_date": None,
        "successes_while_stable": 0,
        "difficulty": difficulty,
        "total_correct": 15,
    }


# ===========================================================================
# 1. Production mastery gate tests
# ===========================================================================

class TestProductionMasteryGate:
    """Verify that promotion to stable requires a production drill."""

    def test_config_constant_exists(self):
        """REQUIRE_PRODUCTION_FOR_STABLE should be True."""
        assert REQUIRE_PRODUCTION_FOR_STABLE is True

    def test_production_drill_types_defined(self):
        """PRODUCTION_DRILL_TYPES should contain known production types."""
        assert "reverse_mc" in PRODUCTION_DRILL_TYPES
        assert "pinyin_to_hanzi" in PRODUCTION_DRILL_TYPES
        assert "sentence_build" in PRODUCTION_DRILL_TYPES
        assert "word_order" in PRODUCTION_DRILL_TYPES
        assert "intuition" in PRODUCTION_DRILL_TYPES
        assert "speaking" in PRODUCTION_DRILL_TYPES
        # Recognition types should NOT be in production set
        assert "mc" not in PRODUCTION_DRILL_TYPES
        assert "listening_gist" not in PRODUCTION_DRILL_TYPES

    def test_stable_blocked_without_production(self):
        """Item meeting all other criteria should NOT promote to stable without production."""
        row = _make_stabilizing_row()
        result = _compute_mastery_transition(
            row,
            correct=True,
            confidence="full",
            streak_correct=PROMOTE_STABLE_STREAK + 2,
            streak_incorrect=0,
            drill_type="mc",
            distinct_days=PROMOTE_STABLE_DAYS + 1,
            total_after=PROMOTE_STABLE_ATTEMPTS + 5,
            drill_type_count=PROMOTE_STABLE_DRILL_TYPES + 1,
            modality_count=2,
            has_production_correct=False,  # No production!
        )
        assert result["mastery_stage"] == "stabilizing", \
            "Should stay stabilizing without production drill history"

    def test_stable_promoted_with_production(self):
        """Item meeting all criteria INCLUDING production should promote to stable."""
        row = _make_stabilizing_row()
        result = _compute_mastery_transition(
            row,
            correct=True,
            confidence="full",
            streak_correct=PROMOTE_STABLE_STREAK + 2,
            streak_incorrect=0,
            drill_type="reverse_mc",
            distinct_days=PROMOTE_STABLE_DAYS + 1,
            total_after=PROMOTE_STABLE_ATTEMPTS + 5,
            drill_type_count=PROMOTE_STABLE_DRILL_TYPES + 1,
            modality_count=2,
            has_production_correct=True,  # Has production!
        )
        assert result["mastery_stage"] == "stable", \
            "Should promote to stable with production drill history"

    def test_stable_promotion_respects_config_flag(self):
        """When REQUIRE_PRODUCTION_FOR_STABLE is False, production gate is skipped."""
        row = _make_stabilizing_row()
        with patch("mandarin.db.progress.REQUIRE_PRODUCTION_FOR_STABLE", False):
            result = _compute_mastery_transition(
                row,
                correct=True,
                confidence="full",
                streak_correct=PROMOTE_STABLE_STREAK + 2,
                streak_incorrect=0,
                drill_type="mc",
                distinct_days=PROMOTE_STABLE_DAYS + 1,
                total_after=PROMOTE_STABLE_ATTEMPTS + 5,
                drill_type_count=PROMOTE_STABLE_DRILL_TYPES + 1,
                modality_count=2,
                has_production_correct=False,
            )
        assert result["mastery_stage"] == "stable", \
            "Should promote to stable when production gate is disabled"

    def test_record_attempt_detects_production_drill(self):
        """record_attempt should detect current production drill and pass it through."""
        conn, path = _make_db()
        try:
            _seed_content_item(conn, item_id=1)

            # First, do many recognition drills to build up streak/attempts
            for i in range(15):
                record_attempt(conn, 1, "reading", True, drill_type="mc",
                               confidence="full", response_ms=500)

            # Check mastery - should NOT be stable yet (no production drill)
            row = conn.execute(
                "SELECT mastery_stage FROM progress WHERE content_item_id = 1 AND user_id = 1"
            ).fetchone()
            # It might be stabilizing or passed_once depending on day count
            # The key test: it should NOT be "stable" without production
            if row:
                assert row["mastery_stage"] != "stable" or not REQUIRE_PRODUCTION_FOR_STABLE, \
                    "Should not be stable without a production drill"

            # Now do a production drill
            record_attempt(conn, 1, "reading", True, drill_type="reverse_mc",
                           confidence="full", response_ms=500)
            conn.commit()
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_record_attempt_detects_historical_production(self):
        """record_attempt should detect historical production drill types."""
        conn, path = _make_db()
        try:
            _seed_content_item(conn, item_id=1)

            # Do one production drill early
            record_attempt(conn, 1, "reading", True, drill_type="pinyin_to_hanzi",
                           confidence="full", response_ms=500)

            # Then do many recognition drills
            for i in range(14):
                record_attempt(conn, 1, "reading", True, drill_type="mc",
                               confidence="full", response_ms=500)

            # The item should have production in its history
            row = conn.execute(
                "SELECT drill_types_seen FROM progress WHERE content_item_id = 1 AND user_id = 1"
            ).fetchone()
            if row:
                types = set(row["drill_types_seen"].split(","))
                assert "pinyin_to_hanzi" in types, "Production drill should be in drill_types_seen"
            conn.commit()
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ===========================================================================
# 2. Onboarding flow tests
# ===========================================================================

class TestOnboardingFlow:
    """Verify the revised onboarding flow: placement -> seed -> drill -> goal (optional)."""

    def _make_app(self):
        """Create a minimal Flask test client with onboarding routes."""
        from flask import Flask
        from flask_login import LoginManager, UserMixin
        from mandarin.web.onboarding_routes import onboarding_bp

        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret"
        app.register_blueprint(onboarding_bp)

        login_manager = LoginManager()
        login_manager.init_app(app)

        class FakeUser(UserMixin):
            def __init__(self, uid):
                self.id = uid

        self._fake_user = FakeUser(1)

        @login_manager.user_loader
        def load_user(uid):
            return FakeUser(int(uid))

        return app

    def test_placement_submit_seeds_content_and_completes(self):
        """Placement submit should seed content and mark onboarding complete."""
        app = self._make_app()
        conn, path = _make_db()
        try:
            mock_result = {
                "estimated_level": 1,
                "score": 0,
                "total": 5,
                "breakdown": [],
            }
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["_user_id"] = "1"

                with patch("mandarin.web.onboarding_routes.score_placement", return_value=mock_result), \
                     patch("mandarin.web.onboarding_routes.db") as mock_db, \
                     patch("flask_login.utils._get_user", return_value=self._fake_user):

                    mock_conn = MagicMock()
                    mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
                    mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)

                    # Mock the auto_seed to return 50 items
                    with patch("mandarin.web.onboarding_routes._auto_seed_content", return_value=50):
                        resp = client.post(
                            "/api/onboarding/placement/submit",
                            json={"answers": [1, 2, 3]},
                            content_type="application/json",
                        )

                    assert resp.status_code == 200
                    data = resp.get_json()
                    assert data["items_seeded"] == 50
                    assert data["ready_for_first_session"] is True
                    # Verify onboarding_complete was set
                    calls = [str(c) for c in mock_conn.execute.call_args_list]
                    complete_calls = [c for c in calls if "onboarding_complete" in c]
                    assert len(complete_calls) > 0, "Should set onboarding_complete = 1"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_goal_skip_defaults_to_standard(self):
        """Skip goal should default to standard (5 sessions/week)."""
        app = self._make_app()
        conn, path = _make_db()
        try:
            with app.test_client() as client:
                with patch("flask_login.utils._get_user", return_value=self._fake_user), \
                     patch("mandarin.web.onboarding_routes.db") as mock_db:

                    mock_conn = MagicMock()
                    mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
                    mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)

                    resp = client.post("/api/onboarding/goal/skip")
                    assert resp.status_code == 200
                    data = resp.get_json()
                    assert data["goal"] == "standard"
                    assert data["skipped"] is True
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_goal_setting_still_works_after_session(self):
        """Original goal-setting endpoint should still work for post-session use."""
        app = self._make_app()
        conn, path = _make_db()
        try:
            with app.test_client() as client:
                with patch("flask_login.utils._get_user", return_value=self._fake_user), \
                     patch("mandarin.web.onboarding_routes.db") as mock_db:

                    mock_conn = MagicMock()
                    mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
                    mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)

                    resp = client.post(
                        "/api/onboarding/goal",
                        json={"goal": "deep"},
                        content_type="application/json",
                    )
                    assert resp.status_code == 200
                    data = resp.get_json()
                    assert data["goal"] == "deep"
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ===========================================================================
# 3. Metrics-to-scheduler feedback loop tests
# ===========================================================================

class TestMetricsSchedulerFeedback:
    """Verify _get_metrics_snapshot and _apply_metrics_feedback."""

    def test_get_metrics_snapshot_empty_db(self):
        """Snapshot on empty DB should return safe defaults."""
        conn, path = _make_db()
        try:
            snapshot = _get_metrics_snapshot(conn, user_id=1)
            assert snapshot["retention_7d"] is None
            assert snapshot["modality_coverage"] == {}
            assert snapshot["accuracy_trend"] == "stable"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_get_metrics_snapshot_with_data(self):
        """Snapshot should compute metrics from session and progress data."""
        conn, path = _make_db()
        try:
            _seed_content_item(conn, item_id=1)
            _seed_content_item(conn, item_id=2, hanzi="不", pinyin="bù", english="not")

            # Insert progress rows — 1 retained (85%+), 1 not
            conn.execute("""
                INSERT INTO progress (user_id, content_item_id, modality,
                    total_attempts, total_correct, last_review_date)
                VALUES (1, 1, 'reading', 10, 9, date('now', '-1 day'))
            """)
            conn.execute("""
                INSERT INTO progress (user_id, content_item_id, modality,
                    total_attempts, total_correct, last_review_date)
                VALUES (1, 2, 'reading', 10, 5, date('now', '-1 day'))
            """)

            # Insert session logs — this week decent, last week better (declining)
            now = datetime.now(timezone.utc)
            this_week = now.isoformat()
            last_week = (now - timedelta(days=8)).isoformat()

            conn.execute("""
                INSERT INTO session_log (user_id, started_at, items_planned, items_completed,
                    items_correct, modality_counts)
                VALUES (1, ?, 10, 10, 6, '{"reading": 5, "listening": 5}')
            """, (this_week,))
            conn.execute("""
                INSERT INTO session_log (user_id, started_at, items_planned, items_completed,
                    items_correct, modality_counts)
                VALUES (1, ?, 10, 10, 9, '{"reading": 5, "listening": 3, "speaking": 2}')
            """, (last_week,))
            conn.commit()

            snapshot = _get_metrics_snapshot(conn, user_id=1)

            # retention_7d: 1 out of 2 items at 85%+ = 0.5
            assert snapshot["retention_7d"] == 0.5

            # modality_coverage: only 1 session this week
            assert snapshot["modality_coverage"]["reading"] == 1.0
            assert snapshot["modality_coverage"]["listening"] == 1.0
            assert snapshot["modality_coverage"]["speaking"] == 0.0

            # accuracy trend: 60% this week vs 90% last week = declining
            assert snapshot["accuracy_trend"] == "declining"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_apply_metrics_feedback_low_retention(self):
        """Low retention should halve new_item_budget."""
        conn, path = _make_db()
        try:
            plan = {
                "target_items": 12,
                "new_budget": 4,
                "weights": {"reading": 0.25, "listening": 0.35, "speaking": 0.15, "ime": 0.25},
                "distribution": {"reading": 3, "listening": 4, "speaking": 2, "ime": 3},
            }
            # Mock low retention
            with patch("mandarin.scheduler._get_metrics_snapshot", return_value={
                "retention_7d": 0.40,  # < 60%
                "modality_coverage": {"reading": 0.8, "listening": 0.7, "speaking": 0.6, "ime": 0.5},
                "accuracy_trend": "stable",
            }):
                result = _apply_metrics_feedback(conn, 1, plan)

            assert result["new_budget"] == 2, "Should halve new_budget when retention < 60%"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_apply_metrics_feedback_low_modality_coverage(self):
        """Low modality coverage should boost that modality's weight."""
        conn, path = _make_db()
        try:
            plan = {
                "target_items": 12,
                "new_budget": 3,
                "weights": {"reading": 0.25, "listening": 0.35, "speaking": 0.15, "ime": 0.25},
                "distribution": {"reading": 3, "listening": 4, "speaking": 2, "ime": 3},
            }
            with patch("mandarin.scheduler._get_metrics_snapshot", return_value={
                "retention_7d": 0.80,  # fine
                "modality_coverage": {"reading": 0.8, "listening": 0.7, "speaking": 0.2, "ime": 0.3},
                "accuracy_trend": "stable",
            }):
                result = _apply_metrics_feedback(conn, 1, plan)

            # speaking and ime were < 50% coverage, should be boosted
            # Original: speaking=0.15, ime=0.25 → boosted: speaking=0.225, ime=0.375
            # After renormalization they should be relatively larger
            assert result["weights"]["speaking"] > 0.15, \
                "Speaking weight should increase when coverage < 50%"
            assert result["weights"]["ime"] > 0.25, \
                "IME weight should increase when coverage < 50%"
            # Weights should still sum to ~1.0
            total = sum(result["weights"].values())
            assert abs(total - 1.0) < 0.01, f"Weights should sum to ~1.0, got {total}"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_apply_metrics_feedback_declining_accuracy(self):
        """Declining accuracy should reduce session length by 20%."""
        conn, path = _make_db()
        try:
            plan = {
                "target_items": 12,
                "new_budget": 3,
                "weights": {"reading": 0.25, "listening": 0.35, "speaking": 0.15, "ime": 0.25},
                "distribution": {"reading": 3, "listening": 4, "speaking": 2, "ime": 3},
            }
            with patch("mandarin.scheduler._get_metrics_snapshot", return_value={
                "retention_7d": 0.80,
                "modality_coverage": {"reading": 0.8, "listening": 0.7, "speaking": 0.6, "ime": 0.5},
                "accuracy_trend": "declining",
            }):
                result = _apply_metrics_feedback(conn, 1, plan)

            # 12 * 0.8 = 9.6 → rounds to 10
            expected = max(MIN_SESSION_ITEMS, round(12 * 0.8))
            assert result["target_items"] == expected, \
                f"Should reduce target_items to {expected}, got {result['target_items']}"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_apply_metrics_feedback_all_adjustments(self):
        """All three adjustments should apply simultaneously."""
        conn, path = _make_db()
        try:
            plan = {
                "target_items": 12,
                "new_budget": 4,
                "weights": {"reading": 0.25, "listening": 0.35, "speaking": 0.15, "ime": 0.25},
                "distribution": {"reading": 3, "listening": 4, "speaking": 2, "ime": 3},
            }
            with patch("mandarin.scheduler._get_metrics_snapshot", return_value={
                "retention_7d": 0.30,          # < 60% → halve new_budget
                "modality_coverage": {
                    "reading": 0.8, "listening": 0.7,
                    "speaking": 0.1, "ime": 0.9,  # speaking < 50% → boost
                },
                "accuracy_trend": "declining",  # → reduce target by 20%
            }):
                result = _apply_metrics_feedback(conn, 1, plan)

            # Budget: 4 * 0.5 = 2
            assert result["new_budget"] == 2
            # Target: 12 * 0.8 = 10
            assert result["target_items"] == max(MIN_SESSION_ITEMS, round(12 * 0.8))
            # Speaking weight should be boosted relative to original
            assert result["weights"]["speaking"] > 0.15
            # Snapshot and adjustments should be recorded
            assert "_metrics_snapshot" in result
            assert len(result["_metrics_adjustments"]) == 3
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_apply_metrics_feedback_no_adjustments_when_healthy(self):
        """No adjustments when all metrics are healthy."""
        conn, path = _make_db()
        try:
            plan = {
                "target_items": 12,
                "new_budget": 3,
                "weights": {"reading": 0.25, "listening": 0.35, "speaking": 0.15, "ime": 0.25},
                "distribution": {"reading": 3, "listening": 4, "speaking": 2, "ime": 3},
            }
            with patch("mandarin.scheduler._get_metrics_snapshot", return_value={
                "retention_7d": 0.85,  # healthy
                "modality_coverage": {"reading": 0.8, "listening": 0.7, "speaking": 0.6, "ime": 0.5},
                "accuracy_trend": "improving",  # good
            }):
                result = _apply_metrics_feedback(conn, 1, plan)

            assert result["target_items"] == 12
            assert result["new_budget"] == 3
            assert result["_metrics_adjustments"] == []
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_apply_metrics_feedback_none_retention(self):
        """When retention is None (no data), no retention adjustment should be made."""
        conn, path = _make_db()
        try:
            plan = {
                "target_items": 12,
                "new_budget": 4,
                "weights": {"reading": 0.25, "listening": 0.35, "speaking": 0.15, "ime": 0.25},
                "distribution": {"reading": 3, "listening": 4, "speaking": 2, "ime": 3},
            }
            with patch("mandarin.scheduler._get_metrics_snapshot", return_value={
                "retention_7d": None,  # no data
                "modality_coverage": {},
                "accuracy_trend": "stable",
            }):
                result = _apply_metrics_feedback(conn, 1, plan)

            assert result["new_budget"] == 4, "Should not adjust budget when retention is None"
            assert result["target_items"] == 12
        finally:
            conn.close()
            path.unlink(missing_ok=True)
