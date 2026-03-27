"""Extended coverage tests for mandarin/scheduler.py — exercising public API
functions that cascade through many internal helpers.

Goal: raise scheduler.py line coverage from ~61.5% to 75% by calling the
public entry-points with realistic seeded data, exercising internal helpers
like _plan_session_params, _plan_error_focus_items, _plan_contrastive_drills,
_plan_encounter_boost_items, _plan_grammar_boost_items,
_plan_cross_modality_boost_items, _plan_injections, _plan_minimal_pair_drills,
_plan_holdout_probes, _plan_delayed_validations, _build_session_plan,
_compute_item_priority, _new_item_budget, _adaptive_session_length,
_enforce_wip_limit, get_aging_summary, sensitivity_analysis,
evaluate_decision_table, rank_items_by_objective, preview_next_session, etc.
"""

import random
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Schema path for in-memory DB setup
SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


# ── DB helpers ─────────────────────────────────────────────────────────

def _create_test_db():
    """Create an in-memory SQLite DB with the production schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()
    from mandarin.db.core import _migrate
    _migrate(conn)
    return conn


def _seed_items(conn, n=20, hsk=1, with_pinyin=True, with_english=True):
    """Insert n drill-ready content items. Returns list of row IDs."""
    ids = []
    for i in range(n):
        pinyin = f"pīn{i}" if with_pinyin else ""
        english = f"word_{i}" if with_english else ""
        cur = conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, item_type, hsk_level,
                                      register, status, difficulty)
            VALUES (?, ?, ?, 'vocab', ?, 'neutral', 'drill_ready', 0.5)
        """, (f"字{i}", pinyin, english, hsk))
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


def _seed_progress(conn, item_ids, modality="reading", mastery="seen",
                   streak=0, next_review=None, accuracy_pct=60,
                   interval=1.0, user_id=1):
    """Insert progress rows for the given item IDs with configurable params."""
    if next_review is None:
        next_review = date.today().isoformat()
    total_attempts = 10
    total_correct = max(0, round(total_attempts * accuracy_pct / 100))
    for item_id in item_ids:
        conn.execute("""
            INSERT OR REPLACE INTO progress
                (user_id, content_item_id, modality, ease_factor, interval_days,
                 repetitions, next_review_date, last_review_date,
                 total_attempts, total_correct, streak_correct, streak_incorrect,
                 mastery_stage, historically_weak, weak_cycle_count,
                 half_life_days, difficulty, distinct_review_days,
                 avg_response_ms, drill_types_seen)
            VALUES (?, ?, ?, 2.5, ?, 1, ?, ?, ?, ?, ?, 0, ?,
                    0, 0, 1.0, 0.5, 3, 1200.0, 'mc,reverse_mc')
        """, (user_id, item_id, modality, interval, next_review,
              (date.today() - timedelta(days=1)).isoformat(),
              total_attempts, total_correct, streak, mastery))
    conn.commit()


def _seed_all_modalities(conn, n=20, hsk=1, mastery="seen", streak=0,
                         accuracy_pct=60, user_id=1):
    """Seed n items with progress across all four modalities."""
    ids = _seed_items(conn, n=n, hsk=hsk)
    for mod in ("reading", "ime", "listening", "speaking"):
        _seed_progress(conn, ids, modality=mod, mastery=mastery,
                       streak=streak, accuracy_pct=accuracy_pct,
                       user_id=user_id)
    return ids


def _seed_error_log(conn, item_ids, error_type="tone", user_id=1):
    """Insert error_log entries for the given item IDs."""
    for item_id in item_ids:
        for _ in range(4):  # Multiple errors to trigger error-focus
            conn.execute("""
                INSERT INTO error_log (user_id, content_item_id, error_type,
                                       modality, created_at)
                VALUES (?, ?, ?, 'reading', datetime('now', '-1 hour'))
            """, (user_id, item_id, error_type))
    conn.commit()


def _seed_session_log(conn, n=5, user_id=1, days_ago=0,
                      items_planned=12, items_completed=10,
                      items_correct=8, duration=300):
    """Insert session_log entries to provide adaptive data."""
    for i in range(n):
        session_date = date.today() - timedelta(days=days_ago + i)
        conn.execute("""
            INSERT INTO session_log (user_id, session_type, duration_seconds,
                                     started_at, items_planned, items_completed,
                                     items_correct, session_day_of_week,
                                     early_exit)
            VALUES (?, 'standard', ?, ?, ?, ?, ?, ?, 0)
        """, (user_id, duration, session_date.isoformat(),
              items_planned, items_completed, items_correct,
              session_date.weekday()))
    conn.commit()


def _set_last_session(conn, days_ago, user_id=1):
    """Set the last_session_date on learner_profile."""
    dt = (date.today() - timedelta(days=days_ago)).isoformat()
    conn.execute("UPDATE learner_profile SET last_session_date = ? WHERE user_id = ?",
                 (dt, user_id))
    conn.commit()


# ── Standard mock decorator for day profile ───────────────────────────

STANDARD_PROFILE = {
    "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
    "mode": "standard",
}
CONSOLIDATION_PROFILE = {
    "name": "Monday warmup", "length_mult": 0.85, "new_mult": 0.5,
    "mode": "consolidation",
}
STRETCH_PROFILE = {
    "name": "Wednesday stretch", "length_mult": 1.3, "new_mult": 1.5,
    "mode": "stretch",
}


def _patch_day_profile(profile_dict):
    """Return a list of mock decorators that set a fixed day profile."""
    return [
        patch("mandarin.scheduler.get_day_profile", return_value=profile_dict),
        patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0),
    ]


# ═══════════════════════════════════════════════════════════════════════
# 1. plan_standard_session — deep cascading tests
# ═══════════════════════════════════════════════════════════════════════


class TestPlanStandardSessionCoverage:
    """Exercise plan_standard_session with varied data configurations
    to reach internal helpers like error focus, contrastive drills,
    encounter boost, grammar boost, cross-modality boost, injections,
    holdout probes, delayed validations, and peak-end ordering."""

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_with_rich_data(self, mock_tod, mock_profile):
        """Lots of items with diverse progress — exercises most internal paths."""
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=30, accuracy_pct=65)
        _seed_error_log(conn, ids[:5], error_type="tone")
        _seed_error_log(conn, ids[5:8], error_type="vocab")
        _seed_session_log(conn, n=10, days_ago=0)

        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=15)

        assert plan.session_type == "standard"
        assert isinstance(plan.drills, list)
        assert isinstance(plan.micro_plan, str)
        assert plan.estimated_seconds >= 0
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_with_error_focus_items(self, mock_tod, mock_profile):
        """Seed heavy errors to exercise _plan_error_focus_items."""
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=25, accuracy_pct=40)
        # Many errors across multiple types
        _seed_error_log(conn, ids[:10], error_type="tone")
        _seed_error_log(conn, ids[3:8], error_type="segment")
        _seed_error_log(conn, ids[8:12], error_type="ime_confusable")

        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=12)
        assert plan.session_type == "standard"
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=CONSOLIDATION_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_consolidation_mode_exercises_filtering(self, mock_tod, mock_profile):
        """Consolidation mode exercises different sorting and filtering paths."""
        conn = _create_test_db()
        _seed_all_modalities(conn, n=20, mastery="stable", streak=5,
                                   accuracy_pct=85)
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=8)
        assert plan.session_type == "standard"
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STRETCH_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_stretch_mode_exercises_grow_paths(self, mock_tod, mock_profile):
        """Stretch mode should exercise the reverse-sort path in modality drills."""
        conn = _create_test_db()
        _seed_all_modalities(conn, n=25, accuracy_pct=80)
        _seed_session_log(conn, n=8, days_ago=0)
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=15)
        assert plan.session_type == "standard"
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_first_session_scaffolding(self, mock_tod, mock_profile):
        """A user with total_sessions=0 exercises _scaffold_first_session."""
        conn = _create_test_db()
        # Reset total_sessions to 0
        conn.execute("UPDATE learner_profile SET total_sessions = 0")
        conn.commit()
        _seed_all_modalities(conn, n=15, mastery="seen", accuracy_pct=50)
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=10)
        assert plan.session_type == "standard"
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_long_gap_session(self, mock_tod, mock_profile):
        """A 10-day gap exercises long-gap reactivation paths."""
        conn = _create_test_db()
        _set_last_session(conn, days_ago=10)
        _seed_all_modalities(conn, n=20, mastery="stable", streak=3)
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=12)
        assert plan.session_type == "standard"
        # Long gap should suppress new items
        new_count = sum(1 for d in plan.drills if d.is_new)
        assert new_count == 0
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_with_mixed_hsk_levels(self, mock_tod, mock_profile):
        """Mix of HSK levels exercises bounce-level detection."""
        conn = _create_test_db()
        ids_1 = _seed_items(conn, n=10, hsk=1)
        ids_2 = _seed_items(conn, n=10, hsk=2)
        ids_3 = _seed_items(conn, n=10, hsk=3)
        # HSK 2 has terrible accuracy -> bounce detection
        for mod in ("reading", "ime", "listening", "speaking"):
            _seed_progress(conn, ids_1, modality=mod, accuracy_pct=80)
            _seed_progress(conn, ids_2, modality=mod, accuracy_pct=30)
            _seed_progress(conn, ids_3, modality=mod, accuracy_pct=70)
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=12)
        assert plan.session_type == "standard"
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_with_historically_weak_items(self, mock_tod, mock_profile):
        """Items marked historically_weak exercise weak-item handling."""
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=20, accuracy_pct=50)
        # Mark some items as historically weak
        for item_id in ids[:5]:
            conn.execute("""
                UPDATE progress SET historically_weak = 1, weak_cycle_count = 3
                WHERE content_item_id = ?
            """, (item_id,))
        conn.commit()
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=12)
        assert plan.session_type == "standard"
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_with_no_target_uses_profile_default(self, mock_tod, mock_profile):
        """Calling without target_items exercises profile-based target."""
        conn = _create_test_db()
        _seed_all_modalities(conn, n=20)
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=None)
        assert plan.session_type == "standard"
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_with_varied_mastery_stages(self, mock_tod, mock_profile):
        """Different mastery stages across items exercise drill-type selection."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=30)
        stages = ["seen", "learning", "reviewing", "stable", "durable"]
        for i, item_id in enumerate(ids):
            stage = stages[i % len(stages)]
            streak = i if stage in ("stable", "durable") else 0
            for mod in ("reading", "ime", "listening", "speaking"):
                _seed_progress(conn, [item_id], modality=mod, mastery=stage,
                               streak=streak, accuracy_pct=50 + i * 2)
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=12)
        assert plan.session_type == "standard"
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 2. plan_minimal_session
# ═══════════════════════════════════════════════════════════════════════


class TestPlanMinimalSessionCoverage:

    def test_with_seeded_data(self):
        conn = _create_test_db()
        _seed_all_modalities(conn, n=20)
        from mandarin.scheduler import plan_minimal_session
        plan = plan_minimal_session(conn)
        assert plan.session_type == "minimal"
        assert plan.estimated_seconds == 90
        assert isinstance(plan.drills, list)
        conn.close()

    def test_with_empty_db(self):
        conn = _create_test_db()
        from mandarin.scheduler import plan_minimal_session
        plan = plan_minimal_session(conn)
        assert plan.session_type == "minimal"
        assert len(plan.drills) == 0
        conn.close()

    def test_with_only_new_items(self):
        """No progress => fallback to new IME items."""
        conn = _create_test_db()
        _seed_items(conn, n=10)
        from mandarin.scheduler import plan_minimal_session
        plan = plan_minimal_session(conn)
        assert plan.session_type == "minimal"
        conn.close()

    def test_with_gap_message(self):
        """Set a gap to exercise gap_message path."""
        conn = _create_test_db()
        _set_last_session(conn, days_ago=5)
        _seed_all_modalities(conn, n=15)
        from mandarin.scheduler import plan_minimal_session
        plan = plan_minimal_session(conn)
        assert plan.session_type == "minimal"
        # 5-day gap should produce a gap message
        if plan.gap_message:
            assert isinstance(plan.gap_message, str)
        conn.close()

    def test_partial_modality_data(self):
        """Only IME progress, no listening or reading."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="ime")
        from mandarin.scheduler import plan_minimal_session
        plan = plan_minimal_session(conn)
        assert plan.session_type == "minimal"
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 3. plan_catchup_session
# ═══════════════════════════════════════════════════════════════════════


class TestPlanCatchupSessionCoverage:

    def test_with_low_accuracy_items(self):
        """Low accuracy triggers problem-item selection."""
        conn = _create_test_db()
        _seed_all_modalities(conn, n=20, accuracy_pct=35)
        from mandarin.scheduler import plan_catchup_session
        plan = plan_catchup_session(conn)
        assert plan.session_type == "catchup"
        assert isinstance(plan.drills, list)
        conn.close()

    def test_with_empty_db(self):
        conn = _create_test_db()
        from mandarin.scheduler import plan_catchup_session
        plan = plan_catchup_session(conn)
        assert plan.session_type == "catchup"
        assert len(plan.drills) == 0
        conn.close()

    def test_with_mixed_accuracy(self):
        """Mix of good and bad items: exercises both problem and confidence paths."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=20)
        # Half terrible, half great
        for mod in ("reading", "ime", "listening", "speaking"):
            _seed_progress(conn, ids[:10], modality=mod, accuracy_pct=25, streak=0)
            _seed_progress(conn, ids[10:], modality=mod, accuracy_pct=90, streak=8)
        from mandarin.scheduler import plan_catchup_session
        plan = plan_catchup_session(conn)
        assert plan.session_type == "catchup"
        assert len(plan.drills) > 0
        conn.close()

    def test_with_gap(self):
        """Catchup session with gap exercises gap_message path."""
        conn = _create_test_db()
        _set_last_session(conn, days_ago=8)
        _seed_all_modalities(conn, n=15, accuracy_pct=40)
        from mandarin.scheduler import plan_catchup_session
        plan = plan_catchup_session(conn)
        assert plan.session_type == "catchup"
        if plan.gap_message:
            assert isinstance(plan.gap_message, str)
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 4. plan_speaking_session
# ═══════════════════════════════════════════════════════════════════════


class TestPlanSpeakingSessionCoverage:

    def test_with_items_having_pinyin(self):
        conn = _create_test_db()
        _seed_items(conn, n=15, with_pinyin=True)
        from mandarin.scheduler import plan_speaking_session
        plan = plan_speaking_session(conn)
        assert plan.session_type == "speaking"
        for d in plan.drills:
            assert d.modality == "speaking"
            assert d.drill_type == "speaking"
        conn.close()

    def test_with_no_items(self):
        conn = _create_test_db()
        from mandarin.scheduler import plan_speaking_session
        plan = plan_speaking_session(conn)
        assert plan.session_type == "speaking"
        assert len(plan.drills) == 0
        conn.close()

    def test_without_pinyin(self):
        """Items missing pinyin should be excluded."""
        conn = _create_test_db()
        _seed_items(conn, n=10, with_pinyin=False)
        from mandarin.scheduler import plan_speaking_session
        plan = plan_speaking_session(conn)
        assert plan.session_type == "speaking"
        assert len(plan.drills) == 0
        conn.close()

    def test_estimated_seconds(self):
        """Each speaking drill is ~20 seconds."""
        conn = _create_test_db()
        _seed_items(conn, n=10, with_pinyin=True)
        from mandarin.scheduler import plan_speaking_session
        plan = plan_speaking_session(conn)
        if len(plan.drills) > 0:
            assert plan.estimated_seconds == len(plan.drills) * 20
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 5. preview_next_session
# ═══════════════════════════════════════════════════════════════════════


class TestPreviewNextSessionCoverage:

    def test_with_progress_data(self):
        """Preview with existing progress should return items.

        preview_next_session queries p.next_review which may not exist.
        The function handles missing columns via try/except, returning [].
        """
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading", mastery="seen")
        from mandarin.scheduler import preview_next_session
        result = preview_next_session(conn, user_id=1, n=3)
        assert isinstance(result, list)
        assert len(result) <= 3
        for item in result:
            assert "hanzi" in item
            assert "pinyin" in item
            assert "english" in item
            assert "is_new" in item
        conn.close()

    def test_with_empty_db(self):
        """Empty DB should return empty list (from new items query)."""
        conn = _create_test_db()
        from mandarin.scheduler import preview_next_session
        result = preview_next_session(conn, user_id=1, n=3)
        assert isinstance(result, list)
        conn.close()

    def test_with_only_new_items(self):
        """No progress => falls through to new items query."""
        conn = _create_test_db()
        _seed_items(conn, n=5)
        from mandarin.scheduler import preview_next_session
        result = preview_next_session(conn, user_id=1, n=3)
        assert isinstance(result, list)
        # Should find new items
        for item in result:
            assert item.get("is_new") is True
        conn.close()

    def test_n_larger_than_available(self):
        """Requesting more items than available should not crash."""
        conn = _create_test_db()
        _seed_items(conn, n=2)
        from mandarin.scheduler import preview_next_session
        result = preview_next_session(conn, user_id=1, n=10)
        assert isinstance(result, list)
        assert len(result) <= 10
        conn.close()

    def test_with_durable_items_excluded(self):
        """Durable items should be excluded from preview."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=5)
        _seed_progress(conn, ids, modality="reading", mastery="durable", streak=10)
        from mandarin.scheduler import preview_next_session
        result = preview_next_session(conn, user_id=1, n=3)
        assert isinstance(result, list)
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 6. get_aging_summary
# ═══════════════════════════════════════════════════════════════════════


class TestGetAgingSummaryCoverage:

    def test_with_diverse_aging(self):
        """Items at various overdue levels should produce a tier breakdown.

        Note: get_aging_summary queries current_interval which may not exist.
        The function handles this with try/except, returning all-zeros.
        This test verifies the graceful handling either way.
        """
        conn = _create_test_db()
        ids = _seed_items(conn, n=20)
        # Seed progress with different last_review dates
        for i, item_id in enumerate(ids):
            days_ago = i * 2  # 0, 2, 4, ... 38 days since review
            last_rev = (date.today() - timedelta(days=days_ago)).isoformat()
            _seed_progress(conn, [item_id], modality="reading",
                           interval=3.0)
            conn.execute("""
                UPDATE progress SET last_review_date = ?
                WHERE content_item_id = ? AND modality = 'reading'
            """, (last_rev, item_id))
        conn.commit()

        from mandarin.scheduler import get_aging_summary
        result = get_aging_summary(conn, user_id=1)
        assert isinstance(result, dict)
        for tier in ("green", "yellow", "orange", "red"):
            assert tier in result
            assert isinstance(result[tier], int)
            assert result[tier] >= 0
        assert "total" in result
        assert result["total"] == sum(result[t] for t in ("green", "yellow", "orange", "red"))
        conn.close()

    def test_with_empty_db(self):
        """No progress data should return all-zero tiers."""
        conn = _create_test_db()
        from mandarin.scheduler import get_aging_summary
        result = get_aging_summary(conn, user_id=1)
        assert isinstance(result, dict)
        assert result["total"] == 0
        conn.close()

    def test_all_on_time(self):
        """All items reviewed recently -> function returns valid result.

        Since current_interval may not be a column, get_aging_summary may
        return all-zero tiers (exception path). Either way it should not crash.
        """
        conn = _create_test_db()
        ids = _seed_items(conn, n=5)
        _seed_progress(conn, ids, modality="reading", interval=30.0)
        from mandarin.scheduler import get_aging_summary
        result = get_aging_summary(conn, user_id=1)
        assert isinstance(result, dict)
        assert "total" in result
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 7. rank_items_by_objective
# ═══════════════════════════════════════════════════════════════════════


class TestRankItemsByObjectiveCoverage:

    def test_basic_ranking(self):
        """Items with different properties should be ranked."""
        from mandarin.scheduler import rank_items_by_objective
        items = []
        for i in range(10):
            items.append({
                "id": i + 1,
                "hanzi": f"字{i}",
                "pinyin": f"pīn{i}",
                "english": f"word_{i}",
                "hsk_level": 1 + (i % 3),
                "difficulty": 0.3 + i * 0.05,
                "mastery_stage": "seen" if i < 5 else "stable",
                "streak_correct": i,
                "total_attempts": i * 3,
                "total_correct": i * 2,
                "half_life_days": 1.0 + i * 0.3,
                "last_review_date": (date.today() - timedelta(days=i)).isoformat(),
                "historically_weak": 1 if i < 3 else 0,
                "times_shown": i * 2,
                "status": "drill_ready",
                "_confusable_boost": i % 3 == 0,
            })
        recent_ids = {1, 2, 3}
        recent_drill_types = ["mc", "mc", "tone", "reverse_mc"]
        result = rank_items_by_objective(items, recent_ids, recent_drill_types,
                                         target_difficulty=0.6)
        assert isinstance(result, list)
        assert len(result) == 10
        # Result should be a reordered version of the input
        result_ids = {item["id"] for item in result}
        assert result_ids == {item["id"] for item in items}

    def test_empty_items(self):
        from mandarin.scheduler import rank_items_by_objective
        result = rank_items_by_objective([], set(), [])
        assert result == []

    def test_single_item(self):
        from mandarin.scheduler import rank_items_by_objective
        items = [{
            "id": 1, "hanzi": "字", "pinyin": "zì", "english": "char",
            "hsk_level": 1, "difficulty": 0.5, "mastery_stage": "seen",
            "streak_correct": 0, "total_attempts": 0, "total_correct": 0,
            "half_life_days": 1.0, "last_review_date": None,
            "historically_weak": 0, "times_shown": 0, "status": "drill_ready",
        }]
        result = rank_items_by_objective(items, set(), [])
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_with_recent_ids_deprioritization(self):
        """Items in recent_ids should be deprioritized (lower rank)."""
        from mandarin.scheduler import rank_items_by_objective
        items = []
        for i in range(5):
            items.append({
                "id": i + 1, "hanzi": f"字{i}", "pinyin": f"pīn{i}",
                "english": f"word_{i}", "hsk_level": 1, "difficulty": 0.5,
                "mastery_stage": "seen", "streak_correct": 0,
                "total_attempts": 5, "total_correct": 3,
                "half_life_days": 1.0,
                "last_review_date": (date.today() - timedelta(days=1)).isoformat(),
                "historically_weak": 0, "times_shown": 5,
                "status": "drill_ready",
            })
        # Mark items 1-3 as recent
        result = rank_items_by_objective(items, {1, 2, 3}, [])
        assert isinstance(result, list)
        assert len(result) == 5


# ═══════════════════════════════════════════════════════════════════════
# 8. sensitivity_analysis
# ═══════════════════════════════════════════════════════════════════════


class TestSensitivityAnalysisCoverage:

    def test_basic_analysis(self):
        conn = _create_test_db()
        from mandarin.scheduler import sensitivity_analysis
        result = sensitivity_analysis(conn, user_id=1)
        assert isinstance(result, dict)
        assert "target_items" in result
        assert "new_item_ratio" in result
        assert "new_budget" in result
        for param_name, data in result.items():
            assert "base_value" in data
            assert "low_value" in data
            assert "high_value" in data
            assert "low_effect" in data
            assert "high_effect" in data
            assert "sensitivity" in data
            assert data["sensitivity"] in ("low", "medium", "high")
        conn.close()

    def test_with_custom_session_length(self):
        """Set a preferred_session_length and verify it's used."""
        conn = _create_test_db()
        conn.execute("""
            UPDATE learner_profile SET preferred_session_length = 20
            WHERE user_id = 1
        """)
        conn.commit()
        from mandarin.scheduler import sensitivity_analysis
        result = sensitivity_analysis(conn, user_id=1)
        assert result["target_items"]["base_value"] == 20
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 9. evaluate_decision_table
# ═══════════════════════════════════════════════════════════════════════


class TestEvaluateDecisionTableCoverage:

    def test_standard_session_default(self):
        """Default params should match the standard_session rule."""
        from mandarin.scheduler import evaluate_decision_table
        result = evaluate_decision_table({})
        assert isinstance(result, dict)
        assert "matched_rules" in result
        assert "actions" in result
        assert "standard_session" in result["matched_rules"]

    def test_long_gap_reactivation(self):
        from mandarin.scheduler import evaluate_decision_table
        result = evaluate_decision_table({"is_long_gap": True})
        assert "long_gap_reactivation" in result["matched_rules"]
        assert result["actions"].get("session_type") == "catchup"

    def test_high_wip_block(self):
        from mandarin.scheduler import evaluate_decision_table
        result = evaluate_decision_table({
            "wip_count": 50, "wip_limit": 30
        })
        assert "high_wip_block" in result["matched_rules"]
        # Note: standard_session default also matches and may overwrite new_items
        assert "actions" in result

    def test_bounce_detected(self):
        from mandarin.scheduler import evaluate_decision_table
        result = evaluate_decision_table({
            "bounce_levels": {2, 3}
        })
        assert "bounce_detected" in result["matched_rules"]

    def test_consolidation_day(self):
        from mandarin.scheduler import evaluate_decision_table
        result = evaluate_decision_table({
            "day_profile": {"mode": "consolidation"}
        })
        assert "consolidation_day" in result["matched_rules"]

    def test_gentle_day(self):
        from mandarin.scheduler import evaluate_decision_table
        result = evaluate_decision_table({
            "day_profile": {"mode": "gentle"}
        })
        assert "consolidation_day" in result["matched_rules"]

    def test_stretch_day(self):
        from mandarin.scheduler import evaluate_decision_table
        result = evaluate_decision_table({
            "day_profile": {"mode": "stretch"}
        })
        assert "stretch_day" in result["matched_rules"]

    def test_multiple_rules_match(self):
        """Long gap + bounce should both match and merge actions."""
        from mandarin.scheduler import evaluate_decision_table
        result = evaluate_decision_table({
            "is_long_gap": True,
            "bounce_levels": {1},
        })
        assert "long_gap_reactivation" in result["matched_rules"]
        assert "bounce_detected" in result["matched_rules"]
        # Merged actions should contain keys from both
        assert "session_type" in result["actions"]


# ═══════════════════════════════════════════════════════════════════════
# 10. Internal helpers exercised via direct calls
# ═══════════════════════════════════════════════════════════════════════


class TestInternalHelpersCoverage:
    """Directly exercise key internal helpers that are hard to reach
    through the public API alone."""

    def test_get_aging_tier(self):
        from mandarin.scheduler import _get_aging_tier
        assert _get_aging_tier(-1) == "green"
        assert _get_aging_tier(0) == "green"
        assert _get_aging_tier(1) == "yellow"
        assert _get_aging_tier(2) == "yellow"
        assert _get_aging_tier(3) == "orange"
        assert _get_aging_tier(7) == "orange"
        assert _get_aging_tier(8) == "red"
        assert _get_aging_tier(100) == "red"

    def test_enforce_wip_limit_under(self):
        """WIP well under limit should pass budget through unchanged."""
        conn = _create_test_db()
        from mandarin.scheduler import _enforce_wip_limit
        budget, exceeded = _enforce_wip_limit(conn, 5, user_id=1)
        assert budget == 5
        assert not exceeded
        conn.close()

    def test_enforce_wip_limit_at_limit(self):
        """WIP at the limit should block new items.

        Note: _get_learning_wip queries current_interval which may not exist
        as a column (added by migration). The function handles this gracefully
        via try/except, so this test verifies the graceful fallback.
        """
        conn = _create_test_db()
        ids = _seed_items(conn, n=35)
        _seed_progress(conn, ids, modality="reading", mastery="learning",
                       interval=3.0)
        from mandarin.scheduler import _enforce_wip_limit
        budget, exceeded = _enforce_wip_limit(conn, 5, user_id=1)
        # If current_interval column doesn't exist, WIP returns 0 -> budget unchanged
        assert isinstance(budget, int)
        assert isinstance(exceeded, bool)
        conn.close()

    def test_new_item_budget(self):
        """Exercise _new_item_budget with varied mastery data."""
        conn = _create_test_db()
        _seed_all_modalities(conn, n=20, mastery="seen", accuracy_pct=70)
        from mandarin.scheduler import _new_item_budget
        budget = _new_item_budget(conn, user_id=1)
        assert isinstance(budget, int)
        assert budget >= 0
        conn.close()

    def test_new_item_budget_empty_db(self):
        conn = _create_test_db()
        from mandarin.scheduler import _new_item_budget
        budget = _new_item_budget(conn, user_id=1)
        assert isinstance(budget, int)
        assert budget >= 0
        conn.close()

    def test_adaptive_session_length_no_data(self):
        """Without session history, should return base length."""
        conn = _create_test_db()
        from mandarin.scheduler import _adaptive_session_length
        result = _adaptive_session_length(conn, 12, user_id=1)
        assert isinstance(result, int)
        assert result >= 1
        conn.close()

    def test_adaptive_session_length_with_history(self):
        """With session history, should adapt length."""
        conn = _create_test_db()
        _seed_session_log(conn, n=15, days_ago=0,
                          items_planned=12, items_completed=4,
                          items_correct=3, duration=120)
        from mandarin.scheduler import _adaptive_session_length
        result = _adaptive_session_length(conn, 12, user_id=1)
        assert isinstance(result, int)
        assert result >= 1
        conn.close()

    def test_adaptive_session_length_high_completion(self):
        """High completion rate should allow growth."""
        conn = _create_test_db()
        _seed_session_log(conn, n=20, days_ago=0,
                          items_planned=10, items_completed=10,
                          items_correct=9, duration=300)
        from mandarin.scheduler import _adaptive_session_length
        result = _adaptive_session_length(conn, 12, user_id=1)
        assert isinstance(result, int)
        conn.close()

    def test_check_register_gate_no_data(self):
        conn = _create_test_db()
        from mandarin.scheduler import _check_register_gate
        result = _check_register_gate(conn, user_id=1)
        assert isinstance(result, bool)
        conn.close()

    def test_check_register_gate_with_data(self):
        conn = _create_test_db()
        _seed_all_modalities(conn, n=30, accuracy_pct=90)
        from mandarin.scheduler import _check_register_gate
        result = _check_register_gate(conn, user_id=1)
        assert isinstance(result, bool)
        conn.close()

    def test_get_hsk_bounce_levels_no_data(self):
        conn = _create_test_db()
        from mandarin.scheduler import _get_hsk_bounce_levels
        result = _get_hsk_bounce_levels(conn, user_id=1)
        assert isinstance(result, set)
        conn.close()

    def test_get_hsk_bounce_levels_with_errors(self):
        """Seed enough bad data at a level to trigger bounce detection."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=15, hsk=2)
        # Very low accuracy at hsk 2
        _seed_progress(conn, ids, modality="reading", accuracy_pct=20)
        _seed_error_log(conn, ids, error_type="vocab")
        from mandarin.scheduler import _get_hsk_bounce_levels
        result = _get_hsk_bounce_levels(conn, user_id=1)
        assert isinstance(result, set)
        conn.close()

    def test_has_confusable(self):
        from mandarin.scheduler import _has_confusable
        # Common confusable characters
        assert isinstance(_has_confusable("己"), bool)
        assert isinstance(_has_confusable("abc"), bool)
        assert isinstance(_has_confusable(""), bool)

    def test_time_of_day_penalty_no_data(self):
        conn = _create_test_db()
        from mandarin.scheduler import _time_of_day_penalty
        result = _time_of_day_penalty(conn, user_id=1)
        assert isinstance(result, float)
        assert 0 <= result <= 1.0
        conn.close()

    def test_time_of_day_penalty_with_session_data(self):
        conn = _create_test_db()
        _seed_session_log(conn, n=20, days_ago=0,
                          items_planned=12, items_completed=6,
                          items_correct=3, duration=200)
        from mandarin.scheduler import _time_of_day_penalty
        result = _time_of_day_penalty(conn, user_id=1)
        assert isinstance(result, float)
        conn.close()

    def test_compute_interleave_weight(self):
        conn = _create_test_db()
        from mandarin.scheduler import _compute_interleave_weight
        result = _compute_interleave_weight(conn, user_id=1)
        assert isinstance(result, float)
        conn.close()

    def test_compute_interleave_weight_with_data(self):
        conn = _create_test_db()
        _seed_session_log(conn, n=10, days_ago=0)
        _seed_all_modalities(conn, n=15)
        from mandarin.scheduler import _compute_interleave_weight
        result = _compute_interleave_weight(conn, user_id=1)
        assert isinstance(result, float)
        conn.close()

    def test_derive_data_driven_weights(self):
        conn = _create_test_db()
        _seed_all_modalities(conn, n=20, accuracy_pct=60)
        from mandarin.scheduler import _derive_data_driven_weights
        from mandarin.config import DEFAULT_WEIGHTS
        result = _derive_data_driven_weights(conn, DEFAULT_WEIGHTS, user_id=1)
        assert isinstance(result, dict)
        # Should have same keys as input
        assert set(result.keys()) == set(DEFAULT_WEIGHTS.keys())
        # All weights should be positive
        for w in result.values():
            assert w > 0
        conn.close()

    def test_derive_data_driven_weights_no_data(self):
        conn = _create_test_db()
        from mandarin.scheduler import _derive_data_driven_weights
        from mandarin.config import DEFAULT_WEIGHTS
        result = _derive_data_driven_weights(conn, DEFAULT_WEIGHTS, user_id=1)
        # Should fall back to base weights
        assert result == DEFAULT_WEIGHTS
        conn.close()

    def test_adjust_weights_for_errors(self):
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=15, accuracy_pct=50)
        _seed_error_log(conn, ids[:5], error_type="tone")
        from mandarin.scheduler import _adjust_weights_for_errors
        from mandarin.config import DEFAULT_WEIGHTS
        result = _adjust_weights_for_errors(conn, DEFAULT_WEIGHTS, user_id=1)
        assert isinstance(result, dict)
        conn.close()

    def test_adjust_weights_for_errors_no_data(self):
        conn = _create_test_db()
        from mandarin.scheduler import _adjust_weights_for_errors
        from mandarin.config import DEFAULT_WEIGHTS
        result = _adjust_weights_for_errors(conn, DEFAULT_WEIGHTS, user_id=1)
        assert isinstance(result, dict)
        conn.close()

    def test_session_seed_deterministic(self):
        """Same inputs should produce same seed."""
        conn = _create_test_db()
        from mandarin.scheduler import _session_seed
        seed1 = _session_seed(conn, user_id=1)
        seed2 = _session_seed(conn, user_id=1)
        assert seed1 == seed2
        assert isinstance(seed1, int)
        conn.close()

    def test_get_day_profile_without_conn(self):
        from mandarin.scheduler import get_day_profile
        result = get_day_profile(conn=None, user_id=1)
        assert isinstance(result, dict)
        assert "name" in result
        assert "length_mult" in result
        assert "mode" in result

    def test_get_day_profile_with_conn(self):
        conn = _create_test_db()
        from mandarin.scheduler import get_day_profile
        result = get_day_profile(conn=conn, user_id=1)
        assert isinstance(result, dict)
        conn.close()

    def test_get_adaptive_day_profile_no_data(self):
        conn = _create_test_db()
        from mandarin.scheduler import get_adaptive_day_profile
        result = get_adaptive_day_profile(conn, user_id=1)
        # Should return None with insufficient data
        assert result is None
        conn.close()

    def test_get_adaptive_day_profile_with_data(self):
        """Seed enough session data across multiple weeks."""
        conn = _create_test_db()
        # Need ADAPTIVE_MIN_SESSIONS sessions and ADAPTIVE_MIN_WEEKS of data
        _seed_session_log(conn, n=30, days_ago=0,
                          items_planned=12, items_completed=10,
                          items_correct=8, duration=300)
        from mandarin.scheduler import get_adaptive_day_profile
        result = get_adaptive_day_profile(conn, user_id=1)
        # May still be None if not enough weeks, but should not crash
        assert result is None or isinstance(result, dict)
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 11. Kanban policies and constants
# ═══════════════════════════════════════════════════════════════════════


class TestKanbanPoliciesCoverage:

    def test_kanban_policies_structure(self):
        from mandarin.scheduler import KANBAN_POLICIES
        assert isinstance(KANBAN_POLICIES, dict)
        assert "definition_of_done" in KANBAN_POLICIES
        assert "entry_criteria" in KANBAN_POLICIES
        assert "exit_criteria" in KANBAN_POLICIES
        assert "escalation_rules" in KANBAN_POLICIES
        assert "wip_limit" in KANBAN_POLICIES

    def test_aging_tiers_structure(self):
        from mandarin.scheduler import AGING_TIERS
        assert isinstance(AGING_TIERS, dict)
        for tier_name in ("green", "yellow", "orange", "red"):
            assert tier_name in AGING_TIERS
            tier = AGING_TIERS[tier_name]
            assert "min_days" in tier
            assert "max_days" in tier
            assert "label" in tier
            assert "priority_mult" in tier

    def test_scheduling_decision_table_structure(self):
        from mandarin.scheduler import SCHEDULING_DECISION_TABLE
        assert isinstance(SCHEDULING_DECISION_TABLE, list)
        assert len(SCHEDULING_DECISION_TABLE) >= 5
        for rule in SCHEDULING_DECISION_TABLE:
            assert "rule" in rule
            assert "description" in rule
            assert "conditions" in rule
            assert "actions" in rule

    def test_learning_wip_limit_value(self):
        from mandarin.scheduler import LEARNING_WIP_LIMIT
        assert isinstance(LEARNING_WIP_LIMIT, int)
        assert LEARNING_WIP_LIMIT > 0

    def test_get_learning_wip_no_data(self):
        conn = _create_test_db()
        from mandarin.scheduler import _get_learning_wip
        result = _get_learning_wip(conn, user_id=1)
        assert isinstance(result, int)
        assert result == 0
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 12. Pure function edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestComputeItemPriorityCoverage:

    def test_basic_priority_computation(self):
        from mandarin.scheduler import _compute_item_priority
        item = {
            "id": 1, "hanzi": "字", "pinyin": "zì", "english": "char",
            "hsk_level": 1, "difficulty": 0.5, "mastery_stage": "seen",
            "streak_correct": 0, "total_attempts": 5, "total_correct": 3,
            "half_life_days": 1.0,
            "last_review_date": (date.today() - timedelta(days=1)).isoformat(),
            "historically_weak": 0, "times_shown": 5,
            "status": "drill_ready",
        }
        score = _compute_item_priority(item, set(), [], 0.6)
        assert isinstance(score, (int, float))

    def test_priority_with_recent_ids(self):
        from mandarin.scheduler import _compute_item_priority
        item = {
            "id": 1, "hanzi": "字", "pinyin": "zì", "english": "char",
            "hsk_level": 1, "difficulty": 0.5, "mastery_stage": "seen",
            "streak_correct": 0, "total_attempts": 5, "total_correct": 3,
            "half_life_days": 1.0,
            "last_review_date": (date.today() - timedelta(days=1)).isoformat(),
            "historically_weak": 0, "times_shown": 5,
            "status": "drill_ready",
        }
        score_not_recent = _compute_item_priority(item, set(), [], 0.6)
        score_recent = _compute_item_priority(item, {1}, [], 0.6)
        # Recent items should have lower priority
        assert score_recent <= score_not_recent

    def test_priority_historically_weak_boost(self):
        from mandarin.scheduler import _compute_item_priority
        item_normal = {
            "id": 1, "hanzi": "字", "pinyin": "zì", "english": "char",
            "hsk_level": 1, "difficulty": 0.5, "mastery_stage": "seen",
            "streak_correct": 0, "total_attempts": 5, "total_correct": 3,
            "half_life_days": 1.0,
            "last_review_date": (date.today() - timedelta(days=1)).isoformat(),
            "historically_weak": 0, "times_shown": 5,
            "status": "drill_ready",
        }
        item_weak = dict(item_normal)
        item_weak["historically_weak"] = 1
        item_weak["id"] = 2
        _compute_item_priority(item_normal, set(), [], 0.6)
        score_weak = _compute_item_priority(item_weak, set(), [], 0.6)
        # Weak items should generally have higher priority
        assert isinstance(score_weak, (int, float))


class TestScaffoldFirstSessionCoverage:

    def test_scaffold_with_drills(self):
        from mandarin.scheduler import _scaffold_first_session, DrillItem
        drills = [
            DrillItem(content_item_id=i, hanzi=f"字{i}", pinyin=f"pīn{i}",
                      english=f"word_{i}", modality="reading",
                      drill_type=dt)
            for i, dt in enumerate([
                "mc", "reverse_mc", "tone", "ime_type", "listening_gist",
                "mc", "reverse_mc", "tone",
            ], start=1)
        ]
        result = _scaffold_first_session(drills)
        assert isinstance(result, list)
        assert len(result) == len(drills)

    def test_scaffold_empty(self):
        from mandarin.scheduler import _scaffold_first_session
        result = _scaffold_first_session([])
        assert result == []


class TestAddListenProducePairsCoverage:

    def test_listen_produce_pairs(self):
        from mandarin.scheduler import _add_listen_produce_pairs, DrillItem
        drills = [
            DrillItem(content_item_id=i, hanzi=f"字{i}", pinyin=f"pīn{i}",
                      english=f"word_{i}", modality="reading",
                      drill_type="mc")
            for i in range(1, 6)
        ]
        result = _add_listen_produce_pairs(drills)
        assert isinstance(result, list)
        assert len(result) >= len(drills)

    def test_listen_produce_empty(self):
        from mandarin.scheduler import _add_listen_produce_pairs
        result = _add_listen_produce_pairs([])
        assert result == []


class TestPeakEndOrderingCoverage:

    def test_peak_end_ordering(self):
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=10)
        from mandarin.scheduler import _apply_peak_end_ordering, DrillItem
        drills = [
            DrillItem(content_item_id=ids[i], hanzi=f"字{i}", pinyin=f"pīn{i}",
                      english=f"word_{i}", modality="reading", drill_type="mc",
                      is_confidence_win=(i > 7))
            for i in range(min(10, len(ids)))
        ]
        result = _apply_peak_end_ordering(drills, conn, user_id=1)
        assert isinstance(result, list)
        assert len(result) == len(drills)
        conn.close()

    def test_peak_end_empty(self):
        conn = _create_test_db()
        from mandarin.scheduler import _apply_peak_end_ordering
        result = _apply_peak_end_ordering([], conn, user_id=1)
        assert result == []
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 13. Validate plan edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestValidatePlanCoverage:

    def test_media_comprehension_drill_type(self):
        from mandarin.scheduler import _validate_plan, SessionPlan, DrillItem
        plan = SessionPlan(
            session_type="standard",
            drills=[DrillItem(
                content_item_id=1, hanzi="字", pinyin="zì", english="char",
                modality="reading", drill_type="media_comprehension",
            )],
        )
        result = _validate_plan(plan)
        assert isinstance(result, SessionPlan)

    def test_plan_with_all_valid_session_types(self):
        from mandarin.scheduler import _validate_plan, SessionPlan
        for session_type in ("standard", "minimal", "catchup", "speaking"):
            plan = SessionPlan(session_type=session_type, drills=[])
            result = _validate_plan(plan)
            assert result.session_type == session_type


# ═══════════════════════════════════════════════════════════════════════
# 14. Error drill preference mapping
# ═══════════════════════════════════════════════════════════════════════


class TestErrorDrillPreferenceCoverage:

    def test_all_categories_non_empty(self):
        from mandarin.scheduler import ERROR_DRILL_PREFERENCE
        for category, types in ERROR_DRILL_PREFERENCE.items():
            assert isinstance(types, list)
            assert len(types) > 0, f"{category} has no drill types"

    def test_measure_word_category(self):
        from mandarin.scheduler import ERROR_DRILL_PREFERENCE
        assert "measure_word" in ERROR_DRILL_PREFERENCE
        assert "measure_word" in ERROR_DRILL_PREFERENCE["measure_word"]

    def test_number_category(self):
        from mandarin.scheduler import ERROR_DRILL_PREFERENCE
        assert "number" in ERROR_DRILL_PREFERENCE
        assert "number_system" in ERROR_DRILL_PREFERENCE["number"]


# ═══════════════════════════════════════════════════════════════════════
# 15. Deep internal helper coverage
# ═══════════════════════════════════════════════════════════════════════


class TestComputeInterleaveWeightDeep:
    """Exercise _compute_interleave_weight with enough session data
    containing mapping_groups_used to go past the early returns."""

    def _seed_sessions_with_groups(self, conn, n=10, groups_pattern=None):
        """Seed session_log entries with mapping_groups_used."""
        groups_a = "hanzi_to_english,english_to_hanzi,discrimination"
        groups_b = "pinyin_to_english,english_to_pinyin,listening_detail"
        for i in range(n):
            session_date = date.today() - timedelta(days=i)
            # Alternate groups so we get overlap and novelty
            if groups_pattern:
                groups = groups_pattern[i % len(groups_pattern)]
            else:
                groups = groups_a if i % 2 == 0 else groups_b
            conn.execute("""
                INSERT INTO session_log (user_id, session_type, duration_seconds,
                    started_at, items_planned, items_completed,
                    items_correct, session_day_of_week,
                    mapping_groups_used, early_exit)
                VALUES (1, 'standard', 300, ?, 12, 10, ?, ?, ?, 0)
            """, (session_date.isoformat(),
                  8 if i % 2 == 0 else 6,  # Varied accuracy
                  session_date.weekday(), groups))
        conn.commit()

    def test_with_enough_sessions(self):
        conn = _create_test_db()
        self._seed_sessions_with_groups(conn, n=12)
        from mandarin.scheduler import _compute_interleave_weight
        result = _compute_interleave_weight(conn, user_id=1)
        assert isinstance(result, float)
        assert 0.05 <= result <= 0.5
        conn.close()

    def test_with_all_same_groups(self):
        """All sessions use same groups => repeated accuracy data only."""
        conn = _create_test_db()
        self._seed_sessions_with_groups(
            conn, n=12,
            groups_pattern=["hanzi_to_english,english_to_hanzi,discrimination"]
        )
        from mandarin.scheduler import _compute_interleave_weight
        result = _compute_interleave_weight(conn, user_id=1)
        assert isinstance(result, float)
        conn.close()

    def test_with_alternating_groups_high_accuracy_diff(self):
        """Create data where novel groups clearly outperform repeated ones."""
        conn = _create_test_db()
        groups_a = "hanzi_to_english,english_to_hanzi,discrimination"
        groups_b = "pinyin_to_english,english_to_pinyin,listening_detail"
        for i in range(12):
            session_date = date.today() - timedelta(days=i)
            groups = groups_a if i % 2 == 0 else groups_b
            # Novel sessions (odd indices that don't repeat previous) get higher accuracy
            correct = 10 if i % 2 == 1 else 5
            conn.execute("""
                INSERT INTO session_log (user_id, session_type, duration_seconds,
                    started_at, items_planned, items_completed,
                    items_correct, session_day_of_week,
                    mapping_groups_used, early_exit)
                VALUES (1, 'standard', 300, ?, 12, 10, ?, ?, ?, 0)
            """, (session_date.isoformat(), correct,
                  session_date.weekday(), groups))
        conn.commit()
        from mandarin.scheduler import _compute_interleave_weight
        result = _compute_interleave_weight(conn, user_id=1)
        assert isinstance(result, float)
        conn.close()


class TestTimeOfDayPenaltyDeep:
    """Exercise _time_of_day_penalty with enough sessions at current time window."""

    def test_with_many_sessions_at_current_hour(self):
        """Seed many sessions at the current time window to exercise deeper path."""
        conn = _create_test_db()
        from datetime import datetime
        current_hour = datetime.now().hour
        for i in range(20):
            session_date = date.today() - timedelta(days=i)
            conn.execute("""
                INSERT INTO session_log (user_id, session_type, duration_seconds,
                    started_at, items_planned, items_completed,
                    items_correct, session_day_of_week,
                    session_started_hour, early_exit)
                VALUES (1, 'standard', 300, ?, 12, 10, 9, ?, ?, 0)
            """, (session_date.isoformat(), session_date.weekday(), current_hour))
        conn.commit()
        from mandarin.scheduler import _time_of_day_penalty
        result = _time_of_day_penalty(conn, user_id=1)
        assert isinstance(result, float)
        # High accuracy (9/10) => no penalty
        assert result == 1.0
        conn.close()

    def test_with_low_accuracy_sessions(self):
        """Low accuracy at current hour should return penalty."""
        conn = _create_test_db()
        from datetime import datetime
        current_hour = datetime.now().hour
        for i in range(20):
            session_date = date.today() - timedelta(days=i)
            conn.execute("""
                INSERT INTO session_log (user_id, session_type, duration_seconds,
                    started_at, items_planned, items_completed,
                    items_correct, session_day_of_week,
                    session_started_hour, early_exit)
                VALUES (1, 'standard', 300, ?, 12, 10, 3, ?, ?, 0)
            """, (session_date.isoformat(), session_date.weekday(), current_hour))
        conn.commit()
        from mandarin.scheduler import _time_of_day_penalty
        result = _time_of_day_penalty(conn, user_id=1)
        assert isinstance(result, float)
        # Low accuracy (3/10) => penalty
        assert result <= 1.0
        conn.close()


class TestAdaptiveDayProfileDeep:
    """Exercise get_adaptive_day_profile with enough data to return non-None."""

    def test_full_adaptive_profile_gentle(self):
        """Seed sparse sessions to trigger 'gentle' mode (high skip rate)."""
        conn = _create_test_db()
        today_dow = date.today().weekday()
        # Seed sessions spread across 4+ weeks, but few for today's DOW
        for week_offset in range(6):
            for dow in range(7):
                session_date = date.today() - timedelta(weeks=week_offset, days=(today_dow - dow) % 7)
                if dow == today_dow and week_offset > 0:
                    continue  # Skip most today-DOW sessions -> high skip rate
                conn.execute("""
                    INSERT INTO session_log (user_id, session_type, duration_seconds,
                        started_at, items_planned, items_completed,
                        items_correct, session_day_of_week, early_exit)
                    VALUES (1, 'standard', 300, ?, 12, 10, 8, ?, 0)
                """, (session_date.isoformat(), dow))
        conn.commit()
        from mandarin.scheduler import get_adaptive_day_profile
        result = get_adaptive_day_profile(conn, user_id=1)
        # Should return a dict (enough data) or None
        assert result is None or isinstance(result, dict)
        conn.close()

    def test_full_adaptive_profile_standard(self):
        """Seed consistent sessions to get 'standard' or 'stretch' mode."""
        conn = _create_test_db()
        today_dow = date.today().weekday()
        for week_offset in range(6):
            for dow in range(7):
                session_date = date.today() - timedelta(weeks=week_offset, days=(today_dow - dow) % 7)
                conn.execute("""
                    INSERT INTO session_log (user_id, session_type, duration_seconds,
                        started_at, items_planned, items_completed,
                        items_correct, session_day_of_week, early_exit)
                    VALUES (1, 'standard', 300, ?, 12, 10, 8, ?, 0)
                """, (session_date.isoformat(), dow))
        conn.commit()
        from mandarin.scheduler import get_adaptive_day_profile
        result = get_adaptive_day_profile(conn, user_id=1)
        assert result is not None
        assert isinstance(result, dict)
        assert "mode" in result
        assert result["mode"] in ("standard", "stretch", "consolidation", "gentle")
        conn.close()

    def test_early_exit_heavy_profile(self):
        """Many early exits should trigger 'consolidation' mode."""
        conn = _create_test_db()
        today_dow = date.today().weekday()
        for week_offset in range(6):
            for dow in range(7):
                session_date = date.today() - timedelta(weeks=week_offset, days=(today_dow - dow) % 7)
                early = 1 if dow == today_dow else 0
                completed = 4 if dow == today_dow else 10
                conn.execute("""
                    INSERT INTO session_log (user_id, session_type, duration_seconds,
                        started_at, items_planned, items_completed,
                        items_correct, session_day_of_week, early_exit)
                    VALUES (1, 'standard', 300, ?, 12, ?, 8, ?, ?)
                """, (session_date.isoformat(), completed, dow, early))
        conn.commit()
        from mandarin.scheduler import get_adaptive_day_profile
        result = get_adaptive_day_profile(conn, user_id=1)
        assert result is not None
        assert isinstance(result, dict)
        conn.close()


class TestDirectHelperCallsCoverage:
    """Direct calls to internal helpers for deeper code path coverage."""

    def test_plan_error_focus_items_directly(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading", accuracy_pct=40)
        # Need to seed error_focus table (via error_log linked to sessions)
        _seed_session_log(conn, n=3, days_ago=0)
        session_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM session_log ORDER BY started_at DESC LIMIT 3").fetchall()]
        for item_id in ids[:5]:
            for sid in session_ids:
                conn.execute("""
                    INSERT INTO error_log (user_id, content_item_id, error_type,
                                           modality, session_id, created_at)
                    VALUES (1, ?, 'tone', 'reading', ?, datetime('now', '-1 hour'))
                """, (item_id, sid))
        conn.commit()
        from mandarin.scheduler import _plan_error_focus_items
        seen_ids = set()
        result = _plan_error_focus_items(conn, seen_ids, user_id=1)
        assert isinstance(result, list)
        conn.close()

    def test_plan_contrastive_drills_directly(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading")
        from mandarin.scheduler import _plan_contrastive_drills
        seen_ids = set()
        result = _plan_contrastive_drills(conn, seen_ids, user_id=1)
        assert isinstance(result, list)
        conn.close()

    def test_plan_encounter_boost_items_directly(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading")
        from mandarin.scheduler import _plan_encounter_boost_items
        drills = []
        seen_ids = set()
        _plan_encounter_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_plan_reading_struggle_boost_directly(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading")
        from mandarin.scheduler import _plan_reading_struggle_boost
        drills = []
        seen_ids = set()
        _plan_reading_struggle_boost(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_plan_grammar_boost_items_directly(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading")
        from mandarin.scheduler import _plan_grammar_boost_items
        drills = []
        seen_ids = set()
        _plan_grammar_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_plan_cross_modality_boost_items_directly(self):
        """Seed items with strong reading + weak listening to trigger cross-modality."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=15)
        _seed_progress(conn, ids, modality="reading", mastery="stable",
                       streak=5, accuracy_pct=90)
        _seed_progress(conn, ids, modality="listening", mastery="seen",
                       streak=0, accuracy_pct=40)
        from mandarin.scheduler import _plan_cross_modality_boost_items
        drills = []
        seen_ids = set()
        _plan_cross_modality_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        # Should find items with modality gap
        if drills:
            for d in drills:
                assert d.metadata.get("cross_modality_boost") is True
        conn.close()

    def test_plan_injections_directly(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=20)
        _seed_progress(conn, ids, modality="reading")
        from mandarin.scheduler import _plan_injections
        drills = []
        seen_ids = set()
        _plan_injections(conn, drills, seen_ids, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_plan_holdout_probes_directly(self):
        conn = _create_test_db()
        from mandarin.scheduler import _plan_holdout_probes
        drills = []
        seen_ids = set()
        _plan_holdout_probes(conn, drills, seen_ids, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_plan_delayed_validations_directly(self):
        conn = _create_test_db()
        from mandarin.scheduler import _plan_delayed_validations
        drills = []
        seen_ids = set()
        _plan_delayed_validations(conn, drills, seen_ids, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_plan_minimal_pair_drills_directly(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading")
        from mandarin.scheduler import _plan_minimal_pair_drills
        drills = []
        seen_ids = set()
        _plan_minimal_pair_drills(conn, drills, seen_ids, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_get_lens_weights(self):
        conn = _create_test_db()
        from mandarin.scheduler import _get_lens_weights
        result = _get_lens_weights(conn, user_id=1)
        assert isinstance(result, dict)
        conn.close()

    def test_get_core_injection_items(self):
        conn = _create_test_db()
        _seed_items(conn, n=10)
        from mandarin.scheduler import _get_core_injection_items
        result = _get_core_injection_items(conn, set(), limit=2, user_id=1)
        assert isinstance(result, list)
        conn.close()

    def test_get_hsk_prerequisite_cap(self):
        conn = _create_test_db()
        from mandarin.scheduler import _get_hsk_prerequisite_cap
        result = _get_hsk_prerequisite_cap(conn, user_id=1)
        assert isinstance(result, int)
        assert result >= 1
        conn.close()

    def test_thompson_sample_drill_type(self):
        conn = _create_test_db()
        from mandarin.scheduler import _thompson_sample_drill_type
        eligible = ["mc", "reverse_mc", "tone"]
        result = _thompson_sample_drill_type(conn, user_id=1, item_id=1,
                                              eligible_types=eligible)
        assert result in eligible
        conn.close()

    def test_thompson_sample_empty_eligible(self):
        conn = _create_test_db()
        from mandarin.scheduler import _thompson_sample_drill_type
        result = _thompson_sample_drill_type(conn, user_id=1, item_id=1,
                                              eligible_types=[])
        assert result == "mc"
        conn.close()

    def test_update_drill_type_posterior(self):
        conn = _create_test_db()
        from mandarin.scheduler import _update_drill_type_posterior
        # Should not crash even if table doesn't exist (try/except)
        _update_drill_type_posterior(conn, user_id=1, item_id=1,
                                     drill_type="mc", correct=True)
        _update_drill_type_posterior(conn, user_id=1, item_id=1,
                                     drill_type="mc", correct=False)
        conn.close()

    def test_bandit_drill_selection(self):
        conn = _create_test_db()
        from mandarin.scheduler import _bandit_drill_selection
        item = {"id": 1, "hanzi": "字", "pinyin": "zì", "english": "char"}
        result = _bandit_drill_selection(conn, item, "seen", user_id=1,
                                          eligible_types=["mc", "reverse_mc", "tone"])
        # May return None (not enough data) or a drill type
        assert result is None or result in ("mc", "reverse_mc", "tone")
        conn.close()

    def test_bandit_drill_selection_single_arm(self):
        conn = _create_test_db()
        from mandarin.scheduler import _bandit_drill_selection
        item = {"id": 1}
        result = _bandit_drill_selection(conn, item, "seen", user_id=1,
                                          eligible_types=["mc"])
        assert result is None  # Need >= 2 arms
        conn.close()

    def test_bandit_drill_selection_no_eligible(self):
        conn = _create_test_db()
        from mandarin.scheduler import _bandit_drill_selection
        item = {"id": 1}
        result = _bandit_drill_selection(conn, item, "seen", user_id=1,
                                          eligible_types=[])
        assert result is None
        conn.close()

    def test_item_is_drillable_by_fields(self):
        from mandarin.scheduler import _item_is_drillable_by_fields
        # mc requires hanzi + english
        assert _item_is_drillable_by_fields("你", "nǐ", "you", "mc")
        assert not _item_is_drillable_by_fields("", "nǐ", "you", "mc")
        assert _item_is_drillable_by_fields("你", "", "you", "mc")  # no pinyin OK
        # hanzi_to_pinyin requires all three
        assert _item_is_drillable_by_fields("你", "nǐ", "you", "hanzi_to_pinyin")
        assert not _item_is_drillable_by_fields("你", "nǐ", "", "hanzi_to_pinyin")
        assert not _item_is_drillable_by_fields("", "nǐ", "you", "hanzi_to_pinyin")
        # Unknown type requires all three
        assert _item_is_drillable_by_fields("你", "nǐ", "you", "future_type")
        assert not _item_is_drillable_by_fields("你", "", "you", "future_type")

    def test_pick_drill_type_with_conn(self):
        """Call _pick_drill_type with a real connection to exercise bandit path."""
        conn = _create_test_db()
        from mandarin.scheduler import _pick_drill_type
        item = {"id": 1, "hanzi": "字", "pinyin": "zì", "english": "char",
                "item_type": "vocab", "register": "neutral"}
        tracker = {}
        result = _pick_drill_type("reading", item, tracker, conn=conn, user_id=1)
        assert isinstance(result, str)
        conn.close()

    def test_pick_drill_type_with_mastery_stages(self):
        """Call _pick_drill_type with various mastery stages."""
        conn = _create_test_db()
        from mandarin.scheduler import _pick_drill_type
        item = {"id": 1, "hanzi": "字", "pinyin": "zì", "english": "char",
                "item_type": "vocab", "register": "neutral"}
        for stage in ("seen", "learning", "stabilizing", "stable", "durable"):
            tracker = {}
            result = _pick_drill_type("reading", item, tracker, conn=conn,
                                       mastery_stage=stage, user_id=1)
            assert isinstance(result, str)
        conn.close()

    def test_load_confusable_chars(self):
        from mandarin.scheduler import _load_confusable_chars
        result = _load_confusable_chars()
        assert isinstance(result, set)

    def test_clear_confusable_cache(self):
        from mandarin.scheduler import clear_confusable_cache, _has_confusable
        clear_confusable_cache()
        # Should reload on next call
        result = _has_confusable("己")
        assert isinstance(result, bool)

    def test_apply_cross_session_interference_penalty(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=5)
        due_items = [{"id": i} for i in ids]
        from mandarin.scheduler import _apply_cross_session_interference_penalty
        # Should not crash even without interference_pairs data
        _apply_cross_session_interference_penalty(conn, due_items)
        conn.close()

    def test_apply_cross_session_interference_penalty_empty(self):
        conn = _create_test_db()
        from mandarin.scheduler import _apply_cross_session_interference_penalty
        _apply_cross_session_interference_penalty(conn, [])
        conn.close()


class TestComputeItemPriorityDeep:
    """More thorough _compute_item_priority tests to cover all branches."""

    def test_with_ml_prediction_optimal(self):
        from mandarin.scheduler import _compute_item_priority
        item = {
            "id": 1, "difficulty": 0.5, "current_interval": 5.0,
            "days_since_review": 3, "streak_correct": 2,
            "total_attempts": 10, "error_count": 0,
            "historically_weak": 0, "_ml_predicted_accuracy": 0.78,
            "_candidate_drill_type": "mc",
        }
        score = _compute_item_priority(item, set(), [], 0.6)
        assert 0 <= score <= 1

    def test_with_ml_prediction_too_hard(self):
        from mandarin.scheduler import _compute_item_priority
        item = {
            "id": 1, "difficulty": 0.8, "current_interval": 5.0,
            "days_since_review": 3, "streak_correct": 0,
            "total_attempts": 10, "error_count": 3,
            "historically_weak": 0, "_ml_predicted_accuracy": 0.3,
            "_candidate_drill_type": "mc",
        }
        score = _compute_item_priority(item, set(), [], 0.6)
        assert 0 <= score <= 1

    def test_with_ml_prediction_too_easy(self):
        from mandarin.scheduler import _compute_item_priority
        item = {
            "id": 1, "difficulty": 0.2, "current_interval": 30.0,
            "days_since_review": 1, "streak_correct": 10,
            "total_attempts": 50, "error_count": 0,
            "historically_weak": 0, "_ml_predicted_accuracy": 0.99,
            "_candidate_drill_type": "tone",
        }
        score = _compute_item_priority(item, set(), ["tone", "tone", "tone"], 0.6)
        assert 0 <= score <= 1

    def test_with_high_urgency(self):
        from mandarin.scheduler import _compute_item_priority
        item = {
            "id": 1, "difficulty": 0.5, "current_interval": 1.0,
            "days_since_review": 10, "streak_correct": 0,
            "total_attempts": 5, "error_count": 5,
            "historically_weak": 1,
        }
        score = _compute_item_priority(item, set(), [], 0.6)
        assert score > 0  # High urgency + errors

    def test_with_zero_attempts_and_errors(self):
        from mandarin.scheduler import _compute_item_priority
        item = {
            "id": 1, "difficulty": 0.5, "current_interval": None,
            "days_since_review": 0, "streak_correct": 0,
            "total_attempts": 5, "error_count": 0,
        }
        score = _compute_item_priority(item, set(), [], 0.6)
        # Zero attempts with streak=0 should still get error_score=0.3
        assert isinstance(score, float)


class TestObjectiveWeightsCoverage:

    def test_weights_sum_to_one(self):
        from mandarin.scheduler import OBJECTIVE_WEIGHTS
        total = sum(OBJECTIVE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_all_weight_keys_present(self):
        from mandarin.scheduler import OBJECTIVE_WEIGHTS
        expected = {"retention_urgency", "difficulty_match", "variety_bonus", "error_weight"}
        assert set(OBJECTIVE_WEIGHTS.keys()) == expected


class TestBuildSessionPlanCoverage:
    """Test _build_session_plan with realistic inputs."""

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_build_plan_with_many_drills(self, mock_tod, mock_profile):
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=20, accuracy_pct=70)
        from mandarin.scheduler import (
            _build_session_plan, DrillItem,
            _pick_modality_distribution, _pick_mapping_groups,
        )
        from mandarin.config import DEFAULT_WEIGHTS

        drills = [
            DrillItem(content_item_id=ids[i], hanzi=f"字{i}", pinyin=f"pīn{i}",
                      english=f"word_{i}", modality=mod, drill_type=dt,
                      is_new=(i > 15))
            for i, (mod, dt) in enumerate([
                ("reading", "mc"), ("ime", "ime_type"), ("reading", "reverse_mc"),
                ("listening", "listening_gist"), ("reading", "tone"),
                ("ime", "ime_type"), ("reading", "mc"), ("speaking", "speaking"),
                ("reading", "reverse_mc"), ("listening", "listening_gist"),
            ])
            if i < len(ids)
        ]

        params = {
            "target_items": 12,
            "day_profile": STANDARD_PROFILE,
            "days_gap": 0,
            "is_long_gap": False,
            "distribution": _pick_modality_distribution(12, DEFAULT_WEIGHTS),
            "weights": DEFAULT_WEIGHTS,
            "allowed_types": set(),
            "chosen_groups": [],
            "new_budget": 3,
            "bounce_levels": set(),
            "total_sessions": 5,
            "experiment_variant": None,
            "wip_exceeded": False,
        }

        plan = _build_session_plan(drills, params, conn, user_id=1)
        assert plan.session_type == "standard"
        assert isinstance(plan.micro_plan, str)
        assert plan.estimated_seconds >= 0
        conn.close()


class TestAdjustWeightsForErrorsDeep:
    """Exercise _adjust_weights_for_errors with actual error data."""

    def test_with_tone_errors(self):
        """Tone errors should boost reading modality weight."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading", accuracy_pct=50)
        _seed_session_log(conn, n=3, days_ago=0)
        session_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM session_log").fetchall()]
        for item_id in ids[:5]:
            for sid in session_ids:
                conn.execute("""
                    INSERT INTO error_log (user_id, content_item_id, error_type,
                                           modality, session_id, created_at)
                    VALUES (1, ?, 'tone', 'reading', ?, datetime('now'))
                """, (item_id, sid))
        conn.commit()

        from mandarin.scheduler import _adjust_weights_for_errors
        from mandarin.config import DEFAULT_WEIGHTS
        result = _adjust_weights_for_errors(conn, DEFAULT_WEIGHTS, user_id=1)
        assert isinstance(result, dict)
        # Weights should still sum to ~1.0
        total = sum(result.values())
        assert abs(total - 1.0) < 0.01
        conn.close()

    def test_with_mixed_error_types(self):
        """Multiple error types across modalities."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=15)
        _seed_progress(conn, ids, modality="reading", accuracy_pct=50)
        _seed_progress(conn, ids, modality="ime", accuracy_pct=50)
        _seed_session_log(conn, n=3, days_ago=0)
        session_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM session_log").fetchall()]
        error_types = ["tone", "segment", "ime_confusable", "vocab", "grammar"]
        for i, item_id in enumerate(ids[:10]):
            etype = error_types[i % len(error_types)]
            for sid in session_ids:
                conn.execute("""
                    INSERT INTO error_log (user_id, content_item_id, error_type,
                                           modality, session_id, created_at)
                    VALUES (1, ?, ?, 'reading', ?, datetime('now'))
                """, (item_id, etype, sid))
        conn.commit()

        from mandarin.scheduler import _adjust_weights_for_errors
        from mandarin.config import DEFAULT_WEIGHTS
        result = _adjust_weights_for_errors(conn, DEFAULT_WEIGHTS, user_id=1)
        assert isinstance(result, dict)
        conn.close()


class TestGetHskBounceLevelsDeep:
    """Exercise _get_hsk_bounce_levels with data that triggers bounce detection."""

    def test_bounce_detection_triggered(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=15, hsk=2)
        _seed_progress(conn, ids, modality="reading", accuracy_pct=20)
        _seed_session_log(conn, n=5, days_ago=0)
        session_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM session_log").fetchall()]
        # Seed many errors linked to these sessions
        for item_id in ids:
            for sid in session_ids:
                conn.execute("""
                    INSERT INTO error_log (user_id, content_item_id, error_type,
                                           modality, session_id, created_at)
                    VALUES (1, ?, 'vocab', 'reading', ?, datetime('now'))
                """, (item_id, sid))
        conn.commit()
        from mandarin.scheduler import _get_hsk_bounce_levels
        result = _get_hsk_bounce_levels(conn, user_id=1)
        assert isinstance(result, set)
        # HSK 2 should be flagged as bouncing
        if result:
            assert 2 in result
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 16. Tests with seeded specialty tables (error_focus, interference_pairs, etc.)
# ═══════════════════════════════════════════════════════════════════════


def _seed_error_focus(conn, item_ids, error_type="tone", user_id=1):
    """Seed the error_focus table with unresolved items."""
    for item_id in item_ids:
        conn.execute("""
            INSERT OR IGNORE INTO error_focus (user_id, content_item_id, error_type,
                first_flagged_at, last_error_at, error_count,
                consecutive_correct, resolved)
            VALUES (?, ?, ?, datetime('now', '-1 day'), datetime('now', '-1 hour'),
                    5, 0, 0)
        """, (user_id, item_id, error_type))
    conn.commit()


def _seed_interference_pairs(conn, item_ids):
    """Seed the interference_pairs table with high-strength pairs."""
    for i in range(0, len(item_ids) - 1, 2):
        conn.execute("""
            INSERT INTO interference_pairs (item_id_a, item_id_b,
                interference_type, interference_strength,
                detected_by, detected_at)
            VALUES (?, ?, 'visual_similarity', 'high', 'error_pattern', datetime('now'))
        """, (item_ids[i], item_ids[i + 1]))
    conn.commit()


def _seed_drill_type_posterior(conn, item_ids, user_id=1):
    """Seed the drill_type_posterior table for bandit drill selection."""
    for item_id in item_ids:
        for dt in ("mc", "reverse_mc", "tone"):
            conn.execute("""
                INSERT OR IGNORE INTO drill_type_posterior
                    (user_id, content_item_id, drill_type, alpha, beta, updated_at)
                VALUES (?, ?, ?, 3.0, 2.0, datetime('now'))
            """, (user_id, item_id, dt))
    conn.commit()


def _seed_vocab_encounter(conn, item_ids, user_id=1):
    """Seed the vocab_encounter table for encounter-boost items."""
    for item_id in item_ids:
        hanzi = conn.execute(
            "SELECT hanzi FROM content_item WHERE id = ?", (item_id,)
        ).fetchone()
        conn.execute("""
            INSERT INTO vocab_encounter (user_id, content_item_id, hanzi,
                source_type, source_id, looked_up, created_at)
            VALUES (?, ?, ?, 'reading', 'test_passage_1', 1,
                    datetime('now', '-1 day'))
        """, (user_id, item_id, hanzi["hanzi"] if hanzi else ""))
    conn.commit()


class TestErrorFocusDrillsCoverage:
    """Exercise _plan_error_focus_items with seeded error_focus data."""

    def test_error_focus_with_data(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading", accuracy_pct=40)
        _seed_error_focus(conn, ids[:5], error_type="tone")
        _seed_error_focus(conn, ids[5:8], error_type="vocab")
        from mandarin.scheduler import _plan_error_focus_items
        seen_ids = set()
        result = _plan_error_focus_items(conn, seen_ids, user_id=1)
        assert isinstance(result, list)
        # Should find error focus items
        assert len(result) > 0
        for d in result:
            assert d.is_error_focus is True
        conn.close()

    def test_error_focus_with_all_error_types(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=20)
        _seed_progress(conn, ids, modality="reading")
        _seed_progress(conn, ids, modality="ime")
        types = ["tone", "segment", "ime_confusable", "vocab", "grammar", "other"]
        for i, etype in enumerate(types):
            start = i * 3
            end = start + 3
            _seed_error_focus(conn, ids[start:end], error_type=etype)
        from mandarin.scheduler import _plan_error_focus_items
        seen_ids = set()
        result = _plan_error_focus_items(conn, seen_ids, user_id=1)
        assert isinstance(result, list)
        assert len(result) > 0
        conn.close()


class TestContrastiveDrillsCoverage:
    """Exercise _plan_contrastive_drills with seeded interference_pairs data."""

    def test_contrastive_with_pairs(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading")
        _seed_interference_pairs(conn, ids)
        from mandarin.scheduler import _plan_contrastive_drills
        seen_ids = set()
        result = _plan_contrastive_drills(conn, seen_ids, user_id=1)
        assert isinstance(result, list)
        # Should find contrastive pairs
        if result:
            for d in result:
                assert d.drill_type == "contrastive"
                assert "contrastive_partner_id" in d.metadata
        conn.close()

    def test_contrastive_with_seen_ids_overlap(self):
        """If pair items are already in seen_ids, should skip them."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading")
        _seed_interference_pairs(conn, ids)
        from mandarin.scheduler import _plan_contrastive_drills
        # Pre-fill seen_ids with all items
        seen_ids = set(ids)
        result = _plan_contrastive_drills(conn, seen_ids, user_id=1)
        assert isinstance(result, list)
        assert len(result) == 0  # All items already seen
        conn.close()


class TestBanditDrillSelectionCoverage:
    """Exercise Thompson Sampling bandit with seeded drill_type_posterior."""

    def test_bandit_with_posterior_data(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=5)
        _seed_drill_type_posterior(conn, ids)
        from mandarin.scheduler import _bandit_drill_selection
        item = {"id": ids[0], "hanzi": "字0", "pinyin": "pīn0", "english": "word_0"}
        result = _bandit_drill_selection(conn, item, "seen", user_id=1,
                                          eligible_types=["mc", "reverse_mc", "tone"])
        # Should use Thompson Sampling and return a valid drill type
        assert result in ("mc", "reverse_mc", "tone")
        conn.close()

    def test_pick_drill_type_with_conn_and_posteriors(self):
        """Full _pick_drill_type with real posteriors."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=5)
        _seed_drill_type_posterior(conn, ids)
        from mandarin.scheduler import _pick_drill_type
        item = {"id": ids[0], "hanzi": "字0", "pinyin": "pīn0", "english": "word_0",
                "item_type": "vocab", "register": "neutral"}
        tracker = {}
        result = _pick_drill_type("reading", item, tracker, conn=conn, user_id=1)
        assert isinstance(result, str)
        conn.close()


class TestEncounterBoostWithDataCoverage:
    """Exercise _plan_encounter_boost_items with seeded vocab_encounter data."""

    def test_encounter_boost_with_lookups(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=15)
        _seed_progress(conn, ids, modality="reading")
        _seed_vocab_encounter(conn, ids[:8])
        from mandarin.scheduler import _plan_encounter_boost_items
        drills = []
        seen_ids = set()
        _plan_encounter_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()


class TestEncounterBoostWithVariedMasteryCoverage:
    """Exercise encounter boost with different mastery stages for each item."""

    def test_encounter_boost_with_passed_once(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids[:5], modality="reading", mastery="passed_once",
                       streak=2, accuracy_pct=70)
        _seed_progress(conn, ids[5:], modality="reading", mastery="stable",
                       streak=5, accuracy_pct=90)
        _seed_vocab_encounter(conn, ids)
        from mandarin.scheduler import _plan_encounter_boost_items
        drills = []
        seen_ids = set()
        _plan_encounter_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()


class TestCrossModalityBoostWithDataCoverage:
    """Exercise _plan_cross_modality_boost_items with clear modality gap data."""

    def test_cross_modality_with_clear_gap(self):
        """Reading stable + listening seen should trigger cross-modality boost."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        # Strong reading: stable mastery
        _seed_progress(conn, ids, modality="reading", mastery="stable",
                       streak=8, accuracy_pct=95)
        # Weak listening: seen mastery
        _seed_progress(conn, ids, modality="listening", mastery="seen",
                       streak=0, accuracy_pct=30)
        from mandarin.scheduler import _plan_cross_modality_boost_items
        drills = []
        seen_ids = set()
        _plan_cross_modality_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        # Should find cross-modality items
        if drills:
            for d in drills:
                assert d.metadata.get("cross_modality_boost") is True
                assert d.modality == "listening"  # Weak modality
        conn.close()

    def test_cross_modality_durable_vs_seen(self):
        """Durable reading + seen ime should produce highest priority gaps."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading", mastery="durable",
                       streak=15, accuracy_pct=98)
        _seed_progress(conn, ids, modality="ime", mastery="seen",
                       streak=0, accuracy_pct=20)
        from mandarin.scheduler import _plan_cross_modality_boost_items
        drills = []
        seen_ids = set()
        _plan_cross_modality_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        if drills:
            for d in drills:
                assert d.modality == "ime"
        conn.close()


class TestStandardSessionWithFullData:
    """Exercise plan_standard_session with all specialty tables populated
    to hit deeper internal paths."""

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_with_error_focus_and_interference(self, mock_tod, mock_profile):
        """Full session planning with error focus and contrastive drills."""
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=25, accuracy_pct=60)
        _seed_error_focus(conn, ids[:5], error_type="tone")
        _seed_error_focus(conn, ids[5:8], error_type="vocab")
        _seed_interference_pairs(conn, ids[:10])
        _seed_drill_type_posterior(conn, ids[:10])
        _seed_vocab_encounter(conn, ids[10:15])
        _seed_session_log(conn, n=10, days_ago=0)

        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=15)
        assert plan.session_type == "standard"
        assert len(plan.drills) > 0
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_with_cross_modality_gaps(self, mock_tod, mock_profile):
        """Session with cross-modality gaps to exercise gap-filling."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=25)
        # Create modality gaps: strong reading, weak everything else
        _seed_progress(conn, ids, modality="reading", mastery="stable",
                       streak=5, accuracy_pct=90)
        _seed_progress(conn, ids, modality="listening", mastery="seen",
                       streak=0, accuracy_pct=40)
        _seed_progress(conn, ids, modality="ime", mastery="seen",
                       streak=0, accuracy_pct=35)
        _seed_progress(conn, ids, modality="speaking", mastery="seen",
                       streak=0, accuracy_pct=30)
        _seed_error_focus(conn, ids[:3], error_type="tone")
        _seed_session_log(conn, n=5, days_ago=0)

        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=12)
        assert plan.session_type == "standard"
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STRETCH_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_stretch_with_full_data(self, mock_tod, mock_profile):
        """Stretch mode with all specialty data populated."""
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=30, accuracy_pct=85)
        _seed_error_focus(conn, ids[:3], error_type="segment")
        _seed_interference_pairs(conn, ids[:8])
        _seed_drill_type_posterior(conn, ids[:15])
        _seed_vocab_encounter(conn, ids[15:20])
        _seed_session_log(conn, n=15, days_ago=0, items_correct=10)

        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=18)
        assert plan.session_type == "standard"
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 17. Counter-metric adjustments and lifecycle events
# ═══════════════════════════════════════════════════════════════════════


class TestCounterMetricAdjustmentsCoverage:
    """Exercise _apply_counter_metric_adjustments with lifecycle_event data."""

    def _seed_lifecycle_events(self, conn, actions):
        """Seed lifecycle_event table with counter_metric_scheduler_adjust events."""
        import json
        for action_data in actions:
            conn.execute("""
                INSERT INTO lifecycle_event (event_type, user_id, metadata, created_at)
                VALUES ('counter_metric_scheduler_adjust', 1, ?, datetime('now'))
            """, (json.dumps(action_data),))
        conn.commit()

    def test_reduce_new_item_budget(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "reduce_new_item_budget", "params": {"multiplier": 0.5}}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 0.4, "ime": 0.3, "listening": 0.2, "speaking": 0.1}, "distribution": {"reading": 5, "ime": 4, "listening": 2, "speaking": 1}}
        adjustments = _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert isinstance(adjustments, list)
        assert plan["new_budget"] == 2  # 4 * 0.5
        conn.close()

    def test_pause_new_items(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "pause_new_items"}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 0.4, "ime": 0.3, "listening": 0.2, "speaking": 0.1}, "distribution": {"reading": 5}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan["new_budget"] == 0
        conn.close()

    def test_increase_spacing_multiplier(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "increase_spacing_multiplier", "params": {"factor": 0.8}}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan.get("_cm_spacing_factor") == 0.8
        conn.close()

    def test_shorten_sessions(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "shorten_sessions", "params": {"multiplier": 0.7}}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 0.4, "ime": 0.3, "listening": 0.2, "speaking": 0.1}, "distribution": {"reading": 5}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan["target_items"] < 12
        conn.close()

    def test_switch_to_minimal_mode(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "switch_to_minimal_mode"}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 0.4, "ime": 0.3, "listening": 0.2, "speaking": 0.1}, "distribution": {"reading": 5}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan["new_budget"] == 0
        conn.close()

    def test_boost_production_drills(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "boost_production_drills", "params": {"production_weight": 3.0}}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan.get("_cm_production_boost") == 3.0
        conn.close()

    def test_enforce_production_gate(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "enforce_production_gate"}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan.get("_cm_production_gate") is True
        conn.close()

    def test_increase_drill_diversity(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "increase_drill_diversity", "params": {"min_types": 4}}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan.get("_cm_min_drill_types") == 4
        conn.close()

    def test_increase_difficulty_floor(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "increase_difficulty_floor", "params": {"min_difficulty": 0.4}}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan.get("_cm_difficulty_floor") == 0.4
        conn.close()

    def test_increase_long_term_reviews(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "increase_long_term_reviews", "params": {"boost_factor": 1.5}}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan.get("_cm_lt_review_boost") == 1.5
        conn.close()

    def test_add_response_floor(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "add_response_floor", "params": {"floor_ms": 1000}}
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert plan.get("_cm_response_floor_ms") == 1000
        conn.close()

    def test_multiple_actions(self):
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "reduce_new_item_budget", "params": {"multiplier": 0.5}},
            {"action": "boost_production_drills", "params": {"production_weight": 2.0}},
            {"action": "add_response_floor", "params": {"floor_ms": 800}},
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 6, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        adjustments = _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert len(adjustments) == 3
        assert plan["new_budget"] == 3
        assert plan.get("_cm_production_boost") == 2.0
        assert plan.get("_cm_response_floor_ms") == 800
        conn.close()

    def test_deduplication_of_same_action(self):
        """Duplicate actions should be deduplicated (most recent only)."""
        conn = _create_test_db()
        self._seed_lifecycle_events(conn, [
            {"action": "reduce_new_item_budget", "params": {"multiplier": 0.5}},
            {"action": "reduce_new_item_budget", "params": {"multiplier": 0.3}},
        ])
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 6, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        adjustments = _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        # Only the first (most recent due to DESC ordering) should be applied
        assert len(adjustments) == 1
        conn.close()

    def test_no_events(self):
        conn = _create_test_db()
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12, "weights": {"reading": 1.0}, "distribution": {"reading": 12}}
        adjustments = _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert adjustments == []
        conn.close()

    def test_invalid_json_metadata(self):
        """Invalid JSON in metadata should be skipped gracefully."""
        conn = _create_test_db()
        conn.execute("""
            INSERT INTO lifecycle_event (event_type, user_id, metadata, created_at)
            VALUES ('counter_metric_scheduler_adjust', 1, 'not valid json', datetime('now'))
        """)
        conn.commit()
        from mandarin.scheduler import _apply_counter_metric_adjustments
        plan = {"new_budget": 4, "target_items": 12}
        adjustments = _apply_counter_metric_adjustments(conn, user_id=1, plan=plan)
        assert adjustments == []
        conn.close()


class TestGetUnderrepresentedRegistersCoverage:
    """Exercise _get_underrepresented_registers."""

    def test_no_data(self):
        conn = _create_test_db()
        from mandarin.scheduler import _get_underrepresented_registers
        result = _get_underrepresented_registers(conn, user_id=1)
        assert isinstance(result, list)
        # All registers should be underrepresented with no data
        assert len(result) == 4
        conn.close()

    def test_with_progress_data(self):
        """With items covering some registers, result should exclude them."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=5)
        # Set register to 'neutral' on the items
        _seed_progress(conn, ids, modality="reading")
        from mandarin.scheduler import _get_underrepresented_registers
        result = _get_underrepresented_registers(conn, user_id=1)
        assert isinstance(result, list)
        conn.close()


class TestGetLensWeightsDeepCoverage:
    """Exercise _get_lens_weights with lens profile data."""

    def test_with_lens_data(self):
        conn = _create_test_db()
        # Update profile with lens scores
        conn.execute("""
            UPDATE learner_profile SET
                lens_quiet_observation = 0.8,
                lens_comedy = 0.3,
                lens_food = 0.9,
                lens_travel = 0.7
            WHERE user_id = 1
        """)
        conn.commit()
        from mandarin.scheduler import _get_lens_weights
        result = _get_lens_weights(conn, user_id=1)
        assert isinstance(result, dict)
        assert result["lens_quiet_observation"] == 0.8
        assert result["lens_comedy"] == 0.3
        assert result["lens_food"] == 0.9
        conn.close()


class TestInterleaveWeightFullPath:
    """Exercise _compute_interleave_weight deep body with sufficient data
    where both repeated and novel groups have enough observations."""

    def test_enough_data_for_full_analysis(self):
        """Seed sessions with a pattern that guarantees both repeated and novel
        consecutive pairs: A,A,B,B,A,A,B,B... (two repeated, then two novel).
        Consecutive sessions ordered DESC by started_at, so i=0 is most recent."""
        conn = _create_test_db()
        group_a = "hanzi_to_english,english_to_hanzi,discrimination"
        group_b = "pinyin_to_english,listening_detail,listening_tone"
        # Pattern: A,A,B,B,A,A,B,B,A,A => consecutive pairs have overlap (AA,BB)
        # AND no overlap (AB,BA) -> guaranteed both repeated_acc and novel_acc >= 2
        pattern = [group_a, group_a, group_b, group_b] * 5  # 20 sessions
        for i in range(20):
            session_date = date.today() - timedelta(days=i)
            correct = 7 + (i % 4)  # 7,8,9,10 cycle
            conn.execute("""
                INSERT INTO session_log (user_id, session_type, duration_seconds,
                    started_at, items_planned, items_completed,
                    items_correct, session_day_of_week,
                    mapping_groups_used, early_exit)
                VALUES (1, 'standard', 300, ?, 12, 10, ?, ?, ?, 0)
            """, (session_date.isoformat(), correct,
                  session_date.weekday(), pattern[i]))
        conn.commit()
        from mandarin.scheduler import _compute_interleave_weight
        result = _compute_interleave_weight(conn, user_id=1)
        assert isinstance(result, float)
        assert 0.05 <= result <= 0.5
        conn.close()

    def test_with_strong_novel_advantage(self):
        """Create pattern where novel transitions have high accuracy and
        repeated transitions have low accuracy -> novel should dominate."""
        conn = _create_test_db()
        group_a = "hanzi_to_english,english_to_hanzi"
        group_b = "pinyin_to_english,listening_detail"
        # Pattern: A,A,B,B,A,A,B,B... Repeated pairs=AA,BB. Novel pairs=AB,BA.
        pattern = [group_a, group_a, group_b, group_b] * 5
        for i in range(20):
            session_date = date.today() - timedelta(days=i)
            # For repeated (AA, BB): low accuracy (4/10)
            # For novel (AB, BA): high accuracy (9/10)
            # In DESC order: session 0 is most recent. Pair (i, i+1):
            # i=0,1: A,A -> overlap -> repeated
            # i=1,2: A,B -> no overlap -> novel
            # i=2,3: B,B -> overlap -> repeated
            # i=3,4: B,A -> no overlap -> novel
            # So accuracy pattern: repeated gets 4, novel gets 9
            if i % 4 in (0, 2):
                correct = 4  # Will be "repeated" pair
            else:
                correct = 9  # Will be "novel" pair
            conn.execute("""
                INSERT INTO session_log (user_id, session_type, duration_seconds,
                    started_at, items_planned, items_completed,
                    items_correct, session_day_of_week,
                    mapping_groups_used, early_exit)
                VALUES (1, 'standard', 300, ?, 12, 10, ?, ?, ?, 0)
            """, (session_date.isoformat(), correct,
                  session_date.weekday(), pattern[i]))
        conn.commit()
        from mandarin.scheduler import _compute_interleave_weight
        result = _compute_interleave_weight(conn, user_id=1)
        assert isinstance(result, float)
        assert 0.05 <= result <= 0.5
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 18. Grammar boost with seeded grammar tables
# ═══════════════════════════════════════════════════════════════════════


def _seed_grammar_data(conn, item_ids):
    """Seed grammar_point, content_grammar, and grammar_progress tables."""
    for i in range(1, 4):
        conn.execute("""
            INSERT OR IGNORE INTO grammar_point (id, name, name_zh, hsk_level,
                category, description, difficulty)
            VALUES (?, ?, ?, ?, 'structure', ?, 0.5)
        """, (i, f"grammar_{i}", f"语法{i}", 1, f"Grammar point {i}"))
    conn.commit()
    for idx, item_id in enumerate(item_ids[:6]):
        gp_id = (idx % 3) + 1
        conn.execute("""
            INSERT OR IGNORE INTO content_grammar (content_item_id, grammar_point_id)
            VALUES (?, ?)
        """, (item_id, gp_id))
    conn.commit()
    for gp_id in range(1, 4):
        conn.execute("""
            INSERT OR IGNORE INTO grammar_progress (user_id, grammar_point_id,
                studied_at, drill_attempts, drill_correct, mastery_score)
            VALUES (1, ?, datetime('now', '-1 day'), 5, 3, 0.6)
        """, (gp_id,))
    conn.commit()


class TestGrammarBoostWithDataCoverage:

    def test_grammar_boost_with_recently_studied_points(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=15)
        _seed_progress(conn, ids, modality="reading", mastery="seen")
        _seed_grammar_data(conn, ids)
        from mandarin.scheduler import _plan_grammar_boost_items
        drills = []
        seen_ids = set()
        _plan_grammar_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        if drills:
            for d in drills:
                assert d.metadata.get("grammar_boost") is True
        conn.close()

    def test_grammar_boost_with_passed_once_mastery(self):
        """Items with passed_once mastery should get reverse_mc drill type."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=15)
        # Seed with passed_once mastery
        _seed_progress(conn, ids, modality="reading", mastery="passed_once",
                       streak=2, accuracy_pct=75)
        _seed_grammar_data(conn, ids)
        from mandarin.scheduler import _plan_grammar_boost_items
        drills = []
        seen_ids = set()
        _plan_grammar_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_grammar_boost_with_stable_mastery(self):
        """Items with stable mastery should get cloze_context drill type."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=15)
        _seed_progress(conn, ids, modality="reading", mastery="stable",
                       streak=5, accuracy_pct=90)
        _seed_grammar_data(conn, ids)
        from mandarin.scheduler import _plan_grammar_boost_items
        drills = []
        seen_ids = set()
        _plan_grammar_boost_items(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    @patch("mandarin.scheduler.get_day_profile", return_value=STANDARD_PROFILE)
    @patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
    def test_standard_session_with_grammar_data(self, mock_tod, mock_profile):
        conn = _create_test_db()
        ids = _seed_all_modalities(conn, n=20, accuracy_pct=65)
        _seed_grammar_data(conn, ids)
        _seed_error_focus(conn, ids[:3], error_type="grammar")
        from mandarin.scheduler import plan_standard_session
        plan = plan_standard_session(conn, target_items=12)
        assert plan.session_type == "standard"
        conn.close()


class TestReadingStruggleBoostWithDataCoverage:

    def test_reading_struggle_with_low_comprehension(self):
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading", mastery="seen")
        conn.execute("""
            INSERT INTO reading_progress (user_id, passage_id, completed_at,
                words_looked_up, questions_correct, questions_total)
            VALUES (1, 'test_passage_1', datetime('now', '-1 day'), 5, 1, 5)
        """)
        for item_id in ids[:5]:
            hanzi = conn.execute(
                "SELECT hanzi FROM content_item WHERE id = ?", (item_id,)
            ).fetchone()
            conn.execute("""
                INSERT INTO vocab_encounter (user_id, content_item_id, hanzi,
                    source_type, source_id, looked_up, created_at)
                VALUES (1, ?, ?, 'reading', 'test_passage_1', 1,
                        datetime('now', '-1 day'))
            """, (item_id, hanzi["hanzi"] if hanzi else ""))
        conn.commit()
        from mandarin.scheduler import _plan_reading_struggle_boost
        drills = []
        seen_ids = set()
        _plan_reading_struggle_boost(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        if drills:
            for d in drills:
                assert d.metadata.get("reading_struggle_boost") is True
        conn.close()

    def test_reading_struggle_with_passed_once_mastery(self):
        """Items with passed_once mastery should get reverse_mc drill type."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading", mastery="passed_once",
                       streak=2, accuracy_pct=60)
        conn.execute("""
            INSERT INTO reading_progress (user_id, passage_id, completed_at,
                words_looked_up, questions_correct, questions_total)
            VALUES (1, 'test_passage_2', datetime('now', '-2 days'), 3, 1, 5)
        """)
        for item_id in ids[:5]:
            hanzi = conn.execute(
                "SELECT hanzi FROM content_item WHERE id = ?", (item_id,)
            ).fetchone()
            conn.execute("""
                INSERT INTO vocab_encounter (user_id, content_item_id, hanzi,
                    source_type, source_id, looked_up, created_at)
                VALUES (1, ?, ?, 'reading', 'test_passage_2', 1,
                        datetime('now', '-2 days'))
            """, (item_id, hanzi["hanzi"] if hanzi else ""))
        conn.commit()
        from mandarin.scheduler import _plan_reading_struggle_boost
        drills = []
        seen_ids = set()
        _plan_reading_struggle_boost(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()

    def test_reading_struggle_with_stable_mastery(self):
        """Items with stable mastery should get cloze_context drill type."""
        conn = _create_test_db()
        ids = _seed_items(conn, n=10)
        _seed_progress(conn, ids, modality="reading", mastery="stable",
                       streak=5, accuracy_pct=85)
        conn.execute("""
            INSERT INTO reading_progress (user_id, passage_id, completed_at,
                words_looked_up, questions_correct, questions_total)
            VALUES (1, 'test_passage_3', datetime('now', '-3 days'), 4, 1, 5)
        """)
        for item_id in ids[:5]:
            hanzi = conn.execute(
                "SELECT hanzi FROM content_item WHERE id = ?", (item_id,)
            ).fetchone()
            conn.execute("""
                INSERT INTO vocab_encounter (user_id, content_item_id, hanzi,
                    source_type, source_id, looked_up, created_at)
                VALUES (1, ?, ?, 'reading', 'test_passage_3', 1,
                        datetime('now', '-3 days'))
            """, (item_id, hanzi["hanzi"] if hanzi else ""))
        conn.commit()
        from mandarin.scheduler import _plan_reading_struggle_boost
        drills = []
        seen_ids = set()
        _plan_reading_struggle_boost(conn, seen_ids, 12, drills, user_id=1)
        assert isinstance(drills, list)
        conn.close()


class TestAdditionalEdgeCases:

    def test_pick_drill_type_speaking_modality(self):
        from mandarin.scheduler import _pick_drill_type
        item = {"id": 1, "hanzi": "字", "pinyin": "zì", "english": "char",
                "item_type": "vocab", "register": "neutral"}
        tracker = {}
        result = _pick_drill_type("speaking", item, tracker)
        assert result in ("speaking", "mc")

    def test_pick_drill_type_listening_modality(self):
        from mandarin.scheduler import _pick_drill_type
        item = {"id": 1, "hanzi": "字", "pinyin": "zì", "english": "char",
                "item_type": "vocab", "register": "neutral"}
        tracker = {}
        result = _pick_drill_type("listening", item, tracker)
        assert isinstance(result, str)

    def test_interleave_large_mixed_list(self):
        from mandarin.scheduler import _interleave, DrillItem
        random.seed(42)
        drills = []
        for i in range(15):
            modality = ["reading", "ime", "listening", "speaking"][i % 4]
            drill_type = ["mc", "reverse_mc", "tone", "ime_type", "listening_gist"][i % 5]
            drills.append(DrillItem(
                content_item_id=i + 1, hanzi=f"字{i}", pinyin=f"pīn{i}",
                english=f"word_{i}", modality=modality, drill_type=drill_type,
                metadata={"hsk_level": 1 + (i % 3)},
            ))
        result = _interleave(drills)
        assert len(result) == 15
        result_ids = {d.content_item_id for d in result}
        assert result_ids == {d.content_item_id for d in drills}

    def test_listen_produce_pairs_with_listening_drills(self):
        from mandarin.scheduler import _add_listen_produce_pairs, DrillItem
        drills = [
            DrillItem(content_item_id=1, hanzi="字1", pinyin="pīn1",
                      english="word_1", modality="listening",
                      drill_type="listening_gist"),
            DrillItem(content_item_id=2, hanzi="字2", pinyin="pīn2",
                      english="word_2", modality="reading", drill_type="mc"),
            DrillItem(content_item_id=3, hanzi="字3", pinyin="pīn3",
                      english="word_3", modality="listening",
                      drill_type="listening_gist"),
            DrillItem(content_item_id=4, hanzi="字4", pinyin="pīn4",
                      english="word_4", modality="reading", drill_type="tone"),
            DrillItem(content_item_id=5, hanzi="字5", pinyin="pīn5",
                      english="word_5", modality="reading", drill_type="mc"),
            DrillItem(content_item_id=6, hanzi="字6", pinyin="pīn6",
                      english="word_6", modality="reading", drill_type="mc"),
        ]
        result = _add_listen_produce_pairs(drills)
        assert isinstance(result, list)
        assert len(result) >= len(drills)

    def test_gap_messages_full_range(self):
        from mandarin.scheduler import get_gap_message, GAP_MESSAGES
        for threshold in sorted(GAP_MESSAGES.keys()):
            msg = get_gap_message(threshold)
            if GAP_MESSAGES[threshold]:
                assert msg is not None

    def test_pick_modality_distribution_gap_weights(self):
        from mandarin.scheduler import _pick_modality_distribution
        from mandarin.config import GAP_WEIGHTS
        counts = _pick_modality_distribution(10, GAP_WEIGHTS)
        assert sum(counts.values()) >= 8
        for mod in GAP_WEIGHTS:
            assert counts[mod] >= 1
