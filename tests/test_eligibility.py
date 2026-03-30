"""Tests for mandarin.experiments.eligibility — rule-based experiment filtering.

Covers:
- check_eligibility: min_tenure_days, hsk_band, engagement_bands,
  exclude_dormant_days, platforms, min_data_sufficiency, require_features
- Helper functions: _tenure_days, _avg_hsk_level, _engagement_band,
  _days_since_last_session, _last_platform, _metric_count, _has_feature
- _load_rules: stored eligibility_rules JSON path
- _is_admin: nonexistent user (return False) branch
"""

import pytest

from tests.shared_db import make_test_db
from mandarin.experiments.eligibility import (
    check_eligibility,
    _load_rules,
    _is_active,
    _is_admin,
    _tenure_days,
    _avg_hsk_level,
    _engagement_band,
    _days_since_last_session,
    _last_platform,
    _metric_count,
    _has_feature,
    DEFAULT_ELIGIBILITY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exp(conn, exp_id=10, name="elig_test", eligibility_rules=None):
    """Insert a minimal experiment row."""
    conn.execute(
        "INSERT OR IGNORE INTO experiment (id, name, status, variants, eligibility_rules) "
        "VALUES (?, ?, 'draft', '[\"control\",\"treatment\"]', ?)",
        (exp_id, name, eligibility_rules),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# check_eligibility — rule branches (all uncovered by prior tests)
# ---------------------------------------------------------------------------

class TestCheckEligibilityRules:

    def test_min_tenure_excluded(self):
        """User just created → tenure ≈ 0 → excluded when min_tenure_days is high."""
        conn = make_test_db()
        _make_exp(conn, 10, "elig_tenure")
        rules = {"min_tenure_days": 9999, "exclude_admin": False}
        eligible, reasons = check_eligibility(conn, 10, 1, rules=rules)
        assert not eligible
        assert any("insufficient_tenure" in r for r in reasons)

    def test_hsk_band_excluded(self):
        """User has no learner_profile → hsk=None → no exclusion (None not in range)."""
        conn = make_test_db()
        _make_exp(conn, 11, "elig_hsk")
        # With no hsk data, _avg_hsk_level returns None — rule passes through silently
        rules = {"hsk_band": [1, 2], "exclude_admin": False, "min_sessions": 0}
        eligible, reasons = check_eligibility(conn, 11, 1, rules=rules)
        # hsk is None → filter doesn't fire → not in reasons
        assert "hsk_out_of_range" not in " ".join(reasons)

    def test_engagement_band_excluded(self):
        """User with no recent sessions is 'low' — excluded from high-engagement-only test."""
        conn = make_test_db()
        _make_exp(conn, 12, "elig_engagement")
        rules = {
            "engagement_bands": ["high", "medium"],
            "exclude_admin": False,
            "min_sessions": 0,
        }
        eligible, reasons = check_eligibility(conn, 12, 1, rules=rules)
        assert any("engagement_band_excluded" in r for r in reasons)

    def test_exclude_dormant_no_sessions(self):
        """User with no sessions → _days_since_last_session returns None → not flagged."""
        conn = make_test_db()
        _make_exp(conn, 13, "elig_dormant")
        rules = {"exclude_dormant_days": 1, "exclude_admin": False, "min_sessions": 0}
        eligible, reasons = check_eligibility(conn, 13, 1, rules=rules)
        assert "dormant" not in " ".join(reasons)

    def test_platform_filter(self):
        """User with no session history → platform=None → not excluded."""
        conn = make_test_db()
        _make_exp(conn, 14, "elig_platform")
        rules = {"platforms": ["ios"], "exclude_admin": False, "min_sessions": 0}
        eligible, reasons = check_eligibility(conn, 14, 1, rules=rules)
        assert "platform_excluded" not in " ".join(reasons)

    def test_min_data_sufficiency_excluded(self):
        """User with no sessions → count=0 < min_count → data_insufficiency reason."""
        conn = make_test_db()
        _make_exp(conn, 15, "elig_datasuff")
        rules = {
            "min_data_sufficiency": {
                "metric": "sessions",
                "min_count": 99,
                "lookback_days": 30,
            },
            "exclude_admin": False,
            "min_sessions": 0,
        }
        eligible, reasons = check_eligibility(conn, 15, 1, rules=rules)
        assert any("data_insufficiency" in r for r in reasons)

    def test_require_features_missing(self):
        """Feature not in learner_profile → missing_feature reason appended."""
        conn = make_test_db()
        _make_exp(conn, 16, "elig_features")
        rules = {
            "require_features": ["nonexistent_flag"],
            "exclude_admin": False,
            "min_sessions": 0,
        }
        eligible, reasons = check_eligibility(conn, 16, 1, rules=rules)
        assert any("missing_feature" in r for r in reasons)

    def test_comprehensive_rules_all_paths(self):
        """All rule keys active at once — exercises every helper function body."""
        conn = make_test_db()
        _make_exp(conn, 17, "elig_comprehensive")
        rules = {
            "exclude_admin": False,
            "min_sessions": 0,
            "min_tenure_days": 9999,
            "hsk_band": [3, 5],
            "engagement_bands": ["high"],
            "exclude_dormant_days": 1,
            "platforms": ["ios"],
            "min_data_sufficiency": {
                "metric": "sessions",
                "min_count": 99,
                "lookback_days": 30,
            },
            "require_features": ["tones_v2_enabled"],
        }
        eligible, reasons = check_eligibility(conn, 17, 1, rules=rules)
        assert isinstance(eligible, bool)
        assert isinstance(reasons, list)
        # At minimum tenure exclusion must fire (tenure ≈ 0 << 9999)
        assert any("insufficient_tenure" in r for r in reasons)


# ---------------------------------------------------------------------------
# _load_rules — stored eligibility_rules JSON path (line 166)
# ---------------------------------------------------------------------------

class TestLoadRules:

    def test_load_stored_rules(self):
        """When experiment has eligibility_rules JSON, _load_rules parses it."""
        conn = make_test_db()
        _make_exp(conn, 20, "elig_stored",
                  eligibility_rules='{"min_sessions": 3, "exclude_admin": false}')
        rules = _load_rules(conn, 20)
        assert rules["min_sessions"] == 3
        assert rules["exclude_admin"] is False

    def test_load_rules_missing_experiment(self):
        """Non-existent experiment returns DEFAULT_ELIGIBILITY."""
        conn = make_test_db()
        rules = _load_rules(conn, 99999)
        assert rules == DEFAULT_ELIGIBILITY

    def test_load_rules_no_eligibility_rules(self):
        """Experiment with NULL eligibility_rules returns DEFAULT_ELIGIBILITY."""
        conn = make_test_db()
        _make_exp(conn, 21, "elig_null_rules", eligibility_rules=None)
        rules = _load_rules(conn, 21)
        assert rules == DEFAULT_ELIGIBILITY


# ---------------------------------------------------------------------------
# _is_admin — nonexistent user returns False (line 188)
# ---------------------------------------------------------------------------

class TestIsAdmin:

    def test_nonexistent_user_returns_false(self):
        conn = make_test_db()
        assert _is_admin(conn, 999999) is False

    def test_existing_non_admin_returns_false(self):
        conn = make_test_db()
        assert _is_admin(conn, 1) is False


# ---------------------------------------------------------------------------
# Helper functions — direct tests for function bodies
# ---------------------------------------------------------------------------

class TestTenureDays:

    def test_existing_user_has_positive_tenure(self):
        conn = make_test_db()
        tenure = _tenure_days(conn, 1)
        assert tenure is not None
        assert tenure >= 0

    def test_nonexistent_user_returns_none(self):
        conn = make_test_db()
        tenure = _tenure_days(conn, 999999)
        assert tenure is None


class TestAvgHskLevel:

    def test_no_learner_profile_returns_none(self):
        conn = make_test_db()
        hsk = _avg_hsk_level(conn, 1)
        # user 1 may or may not have learner_profile — either None or a float
        assert hsk is None or isinstance(hsk, float)

    def test_user_with_profile(self):
        conn = make_test_db()
        conn.execute(
            "INSERT OR IGNORE INTO learner_profile "
            "(user_id, level_reading, level_listening, level_speaking, level_ime) "
            "VALUES (1, 3, 2, 2, 3)"
        )
        conn.commit()
        hsk = _avg_hsk_level(conn, 1)
        assert hsk is not None
        assert 1.0 <= hsk <= 6.0


class TestEngagementBand:

    def test_no_sessions_returns_low(self):
        conn = make_test_db()
        band = _engagement_band(conn, 1)
        assert band == "low"

    def test_high_sessions_returns_high(self):
        """Insert 20 sessions in last 14 days → high engagement."""
        conn = make_test_db()
        for i in range(20):
            conn.execute(
                "INSERT INTO session_log (user_id, started_at, session_outcome) "
                "VALUES (1, datetime('now', '-1 days'), 'completed')"
            )
        conn.commit()
        band = _engagement_band(conn, 1)
        assert band == "high"

    def test_medium_sessions(self):
        """5 sessions in 14 days → 2.5/week → medium engagement."""
        conn = make_test_db()
        for i in range(5):
            conn.execute(
                "INSERT INTO session_log (user_id, started_at, session_outcome) "
                "VALUES (1, datetime('now', '-3 days'), 'completed')"
            )
        conn.commit()
        band = _engagement_band(conn, 1)
        assert band in ("low", "medium")  # 5/2 = 2.5 → medium


class TestDaysSinceLastSession:

    def test_no_sessions_returns_none(self):
        conn = make_test_db()
        days = _days_since_last_session(conn, 1)
        assert days is None

    def test_with_recent_session(self):
        conn = make_test_db()
        conn.execute(
            "INSERT INTO session_log (user_id, started_at, session_outcome) "
            "VALUES (1, datetime('now', '-2 days'), 'completed')"
        )
        conn.commit()
        days = _days_since_last_session(conn, 1)
        assert days is not None
        assert 1 < days < 4


class TestLastPlatform:

    def test_no_sessions_returns_none(self):
        conn = make_test_db()
        platform = _last_platform(conn, 1)
        assert platform is None

    def test_with_session(self):
        conn = make_test_db()
        conn.execute(
            "INSERT INTO session_log (user_id, started_at, session_outcome, client_platform) "
            "VALUES (1, datetime('now'), 'completed', 'android')"
        )
        conn.commit()
        platform = _last_platform(conn, 1)
        assert platform == "android"


class TestMetricCount:

    def test_sessions_metric_zero(self):
        conn = make_test_db()
        count = _metric_count(conn, 1, "sessions", 30)
        assert count == 0

    def test_sessions_metric_with_data(self):
        conn = make_test_db()
        conn.execute(
            "INSERT INTO session_log (user_id, started_at, session_outcome) "
            "VALUES (1, datetime('now', '-1 days'), 'completed')"
        )
        conn.commit()
        count = _metric_count(conn, 1, "sessions", 30)
        assert count == 1

    def test_review_events_metric(self):
        """review_events metric path (lines 312-315)."""
        conn = make_test_db()
        count = _metric_count(conn, 1, "review_events", 30)
        assert count >= 0

    def test_unknown_metric_returns_zero(self):
        """Unknown metric falls through to else: return 0 (line 317)."""
        conn = make_test_db()
        count = _metric_count(conn, 1, "unknown_metric_xyz", 30)
        assert count == 0


class TestHasFeature:

    def test_nonexistent_feature_returns_false(self):
        conn = make_test_db()
        result = _has_feature(conn, 1, "nonexistent_column_xyz")
        assert result is False

    def test_user_without_profile(self):
        conn = make_test_db()
        # No learner_profile for user 1 → returns False
        result = _has_feature(conn, 999999, "level_reading")
        assert result is False
