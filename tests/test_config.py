"""Tests for centralized config -- importability, no circular imports, value sanity."""

import pytest


# ---- TestConfigImport ----

def test_import_retention_constants():
    from mandarin.config import RECALL_THRESHOLD, MIN_HALF_LIFE, MAX_HALF_LIFE, INITIAL_HALF_LIFE
    assert RECALL_THRESHOLD == pytest.approx(0.85)
    assert MIN_HALF_LIFE == pytest.approx(0.5)
    assert MAX_HALF_LIFE == pytest.approx(365.0)
    assert INITIAL_HALF_LIFE == pytest.approx(1.0)


def test_import_sm2_constants():
    from mandarin.config import EASE_FLOOR, EASE_CORRECT_BOOST, EASE_WRONG_PENALTY
    assert EASE_FLOOR == pytest.approx(1.3)
    assert EASE_CORRECT_BOOST == pytest.approx(0.1)
    assert EASE_WRONG_PENALTY == pytest.approx(0.2)


def test_import_streak_constants():
    from mandarin.config import STREAK_STABLE_THRESHOLD, STREAK_EXTENDED_THRESHOLD
    assert STREAK_STABLE_THRESHOLD == 10
    assert STREAK_EXTENDED_THRESHOLD == 15


def test_import_mastery_gates():
    from mandarin.config import (
        PROMOTE_PASSED_ONCE_STREAK, PROMOTE_STABILIZING_STREAK,
        PROMOTE_STABLE_STREAK, PROMOTE_DURABLE_DAYS_STABLE,
        PROMOTE_DURABLE_SUCCESSES,
        DEMOTE_STABLE_STREAK_INCORRECT, RECOVERY_STREAK_CORRECT,
    )
    assert PROMOTE_PASSED_ONCE_STREAK == 2
    assert PROMOTE_STABILIZING_STREAK == 3
    assert PROMOTE_STABLE_STREAK == 6
    assert PROMOTE_DURABLE_DAYS_STABLE == 30
    assert PROMOTE_DURABLE_SUCCESSES == 5
    assert DEMOTE_STABLE_STREAK_INCORRECT == 3
    assert RECOVERY_STREAK_CORRECT == 3


def test_import_day_profiles():
    from mandarin.config import DAY_PROFILES
    assert len(DAY_PROFILES) == 7
    for dow in range(7):
        assert dow in DAY_PROFILES
        assert "name" in DAY_PROFILES[dow]
        assert "length_mult" in DAY_PROFILES[dow]
        assert "new_mult" in DAY_PROFILES[dow]
        assert "mode" in DAY_PROFILES[dow]


def test_import_weights():
    from mandarin.config import DEFAULT_WEIGHTS, GAP_WEIGHTS
    assert len(DEFAULT_WEIGHTS) == 4
    assert len(GAP_WEIGHTS) == 4
    for w in (DEFAULT_WEIGHTS, GAP_WEIGHTS):
        total = sum(w.values())
        assert total == pytest.approx(1.0, abs=0.01)


def test_no_circular_imports():
    """Importing config should not trigger circular imports."""
    import mandarin.config
    import mandarin.retention
    import mandarin.scheduler
    import mandarin.db.progress


def test_retention_uses_config_constants():
    """retention.py should re-export the same values as config."""
    from mandarin.config import RECALL_THRESHOLD as cfg_rt
    from mandarin.retention import RECALL_THRESHOLD as ret_rt
    assert cfg_rt == ret_rt


def test_sanity_checks():
    """Constants should have sane relationships."""
    from mandarin.config import (
        MIN_HALF_LIFE, MAX_HALF_LIFE, INITIAL_HALF_LIFE,
        MAX_INTERVAL,
        EASE_FLOOR,
        STREAK_STABLE_THRESHOLD, STREAK_EXTENDED_THRESHOLD,
        LAG_CLAMP_MIN, LAG_CLAMP_MAX,
        PARTIAL_CONFIDENCE_DAMPEN,
    )
    assert MIN_HALF_LIFE < INITIAL_HALF_LIFE
    assert INITIAL_HALF_LIFE < MAX_HALF_LIFE
    assert MAX_INTERVAL == MAX_HALF_LIFE
    assert EASE_FLOOR > 1.0
    assert STREAK_STABLE_THRESHOLD < STREAK_EXTENDED_THRESHOLD
    assert LAG_CLAMP_MIN < LAG_CLAMP_MAX
    assert PARTIAL_CONFIDENCE_DAMPEN > 0
    assert PARTIAL_CONFIDENCE_DAMPEN < 1
