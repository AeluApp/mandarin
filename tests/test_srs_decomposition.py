"""Tests for decomposed SRS helpers -- pure functions, no DB needed.

Validates:
- _compute_srs_update: ease/interval/reps/streaks
- _compute_mastery_transition: 6-stage lifecycle
- _compute_retention_update: half-life/difficulty/p_recall
"""

import pytest
from datetime import date, timedelta

from mandarin.db.progress import (
    _compute_srs_update,
    _compute_mastery_transition,
    _compute_retention_update,
)
from mandarin.config import (
    EASE_FLOOR, EASE_CORRECT_BOOST, EASE_WRONG_PENALTY,
    INTERVAL_INITIAL, INTERVAL_SECOND, INTERVAL_WRONG,
    STREAK_STABLE_MULT, STREAK_EXTENDED_MULT,
    MAX_INTERVAL,
    INITIAL_HALF_LIFE,
    PARTIAL_CONFIDENCE_DAMPEN,
    CONFIDENCE_DAMPEN,
)


def _base_row(**overrides):
    """Create a minimal progress row dict for testing."""
    row = {
        "ease_factor": 2.5,
        "interval_days": 1.0,
        "repetitions": 0,
        "streak_correct": 0,
        "streak_incorrect": 0,
        "mastery_stage": "seen",
        "historically_weak": 0,
        "weak_cycle_count": 0,
        "stable_since_date": None,
        "successes_while_stable": 0,
        "half_life_days": INITIAL_HALF_LIFE,
        "difficulty": 0.5,
        "last_review_date": None,
        "total_attempts": 0,
        "avg_response_ms": None,
        "drill_types_seen": "",
        "distinct_review_days": 0,
    }
    row.update(overrides)
    return row


# ---- TestComputeSrsUpdate ----

def test_correct_first_attempt():
    row = _base_row()
    result = _compute_srs_update(row, True, "full", None, "seen")
    assert result["reps"] == 1
    assert result["interval"] == INTERVAL_INITIAL
    assert result["streak_correct"] == 1
    assert result["streak_incorrect"] == 0
    assert result["ease"] == pytest.approx(2.5 + EASE_CORRECT_BOOST)


def test_correct_second_attempt():
    row = _base_row(repetitions=1, streak_correct=1)
    result = _compute_srs_update(row, True, "full", None, "seen")
    assert result["reps"] == 2
    assert result["interval"] == INTERVAL_SECOND


def test_correct_third_attempt():
    row = _base_row(repetitions=2, ease_factor=2.5, interval_days=3.0, streak_correct=2)
    result = _compute_srs_update(row, True, "full", None, "seen")
    assert result["reps"] == 3
    assert result["interval"] == pytest.approx(3.0 * 2.5)


def test_wrong_resets():
    row = _base_row(repetitions=5, streak_correct=5, ease_factor=2.8)
    result = _compute_srs_update(row, False, "full", None, "seen")
    assert result["reps"] == 0
    assert result["interval"] == INTERVAL_WRONG
    assert result["streak_correct"] == 0
    assert result["streak_incorrect"] == 1
    assert result["ease"] == pytest.approx(2.8 - EASE_WRONG_PENALTY)


def test_ease_floor():
    row = _base_row(ease_factor=EASE_FLOOR)
    result = _compute_srs_update(row, False, "full", None, "seen")
    assert result["ease"] >= EASE_FLOOR


def test_unknown_confidence():
    row = _base_row(streak_correct=3, streak_incorrect=0)
    result = _compute_srs_update(row, True, "unknown", None, "seen")
    assert result["interval"] == INTERVAL_INITIAL
    assert result["streak_correct"] == 3  # unchanged


def test_narrowed_confidence():
    row = _base_row(interval_days=10.0, ease_factor=2.5)
    result = _compute_srs_update(row, True, "narrowed", None, "seen")
    assert result["interval"] == pytest.approx(max(INTERVAL_INITIAL, 10.0 * 0.6))


def test_half_confidence():
    row = _base_row(repetitions=3, interval_days=10.0, ease_factor=2.5)
    result = _compute_srs_update(row, True, "half", None, "seen")
    assert result["reps"] == 2
    assert result["interval"] == pytest.approx(max(INTERVAL_INITIAL, 10.0 * 0.5))


def test_speed_not_used():
    """Speed-based adjustments removed -- response_ms should not affect interval."""
    row = _base_row(repetitions=2, interval_days=3.0, ease_factor=2.5, streak_correct=2)
    result_fast = _compute_srs_update(row, True, "full", 1000, "seen")
    result_slow = _compute_srs_update(row, True, "full", 15000, "seen")
    result_none = _compute_srs_update(row, True, "full", None, "seen")
    assert result_fast["interval"] == pytest.approx(result_slow["interval"])
    assert result_fast["interval"] == pytest.approx(result_none["interval"])


def test_streak_cap_stable():
    row = _base_row(repetitions=2, interval_days=3.0, ease_factor=2.5, streak_correct=10)
    result = _compute_srs_update(row, True, "full", None, "stable")
    # interval = 3.0 * 2.5 * STREAK_STABLE_MULT (only one multiplier)
    expected = 3.0 * 2.5 * STREAK_STABLE_MULT
    assert result["interval"] == pytest.approx(expected, abs=0.1)


def test_streak_cap_extended_exclusive():
    """Extended streak uses only EXTENDED_MULT, not both multipliers."""
    row = _base_row(repetitions=2, interval_days=3.0, ease_factor=2.5, streak_correct=15)
    result = _compute_srs_update(row, True, "full", None, "stable")
    # Only EXTENDED_MULT applies, NOT STABLE_MULT * EXTENDED_MULT
    expected = 3.0 * 2.5 * STREAK_EXTENDED_MULT
    assert result["interval"] == pytest.approx(expected, abs=0.1)


def test_interval_cap():
    """Interval should never exceed MAX_INTERVAL."""
    row = _base_row(repetitions=2, interval_days=300.0, ease_factor=2.5, streak_correct=15)
    result = _compute_srs_update(row, True, "full", None, "durable")
    assert result["interval"] <= MAX_INTERVAL


def test_next_review_is_future():
    row = _base_row()
    result = _compute_srs_update(row, True, "full", None, "seen")
    assert result["next_review"] > date.today().isoformat()


# ---- TestComputeMasteryTransition ----

def test_seen_to_passed_once():
    row = _base_row()
    result = _compute_mastery_transition(
        row, True, "full", streak_correct=2, streak_incorrect=0,
        drill_type="mc", distinct_days=1, total_after=2, drill_type_count=1,
    )
    assert result["mastery_stage"] == "passed_once"


def test_passed_once_to_stabilizing():
    row = _base_row(mastery_stage="passed_once")
    result = _compute_mastery_transition(
        row, True, "full", streak_correct=3, streak_incorrect=0,
        drill_type="mc", distinct_days=2, total_after=4, drill_type_count=1,
    )
    assert result["mastery_stage"] == "stabilizing"


def test_stabilizing_to_stable():
    row = _base_row(mastery_stage="stabilizing")
    result = _compute_mastery_transition(
        row, True, "full", streak_correct=6, streak_incorrect=0,
        drill_type="mc", distinct_days=3, total_after=10, drill_type_count=2,
    )
    assert result["mastery_stage"] == "stable"
    assert result["stable_since_date"] is not None


def test_stable_to_durable():
    old_date = (date.today() - timedelta(days=31)).isoformat()
    row = _base_row(mastery_stage="stable", stable_since_date=old_date,
                    successes_while_stable=4)
    result = _compute_mastery_transition(
        row, True, "full", streak_correct=10, streak_incorrect=0,
        drill_type="mc", distinct_days=10, total_after=30, drill_type_count=3,
    )
    # successes increments to 5 (>= PROMOTE_DURABLE_SUCCESSES=5)
    # days_stable=31 (>= PROMOTE_DURABLE_DAYS_STABLE=30)
    assert result["mastery_stage"] == "durable"


def test_stable_to_decayed():
    row = _base_row(mastery_stage="stable", stable_since_date="2024-01-01")
    result = _compute_mastery_transition(
        row, False, "full", streak_correct=0, streak_incorrect=3,
        drill_type="mc", distinct_days=5, total_after=15, drill_type_count=2,
    )
    # Demotion requires DEMOTE_STABLE_STREAK_INCORRECT=3
    assert result["mastery_stage"] == "decayed"
    assert result["stable_since_date"] is None


def test_stable_not_decayed_at_2_incorrect():
    """2 incorrect should NOT demote stable (threshold is now 3)."""
    row = _base_row(mastery_stage="stable", stable_since_date="2024-01-01")
    result = _compute_mastery_transition(
        row, False, "full", streak_correct=0, streak_incorrect=2,
        drill_type="mc", distinct_days=5, total_after=15, drill_type_count=2,
    )
    assert result["mastery_stage"] == "stable"


def test_stabilizing_regression():
    row = _base_row(mastery_stage="stabilizing")
    result = _compute_mastery_transition(
        row, False, "full", streak_correct=0, streak_incorrect=3,
        drill_type="mc", distinct_days=2, total_after=6, drill_type_count=1,
    )
    assert result["mastery_stage"] == "seen"
    assert result["weak_cycle_count"] == 1


def test_decayed_recovery():
    row = _base_row(mastery_stage="decayed")
    result = _compute_mastery_transition(
        row, True, "full", streak_correct=3, streak_incorrect=0,
        drill_type="mc", distinct_days=3, total_after=15, drill_type_count=2,
    )
    assert result["mastery_stage"] == "stabilizing"


def test_historically_weak_after_3_cycles():
    row = _base_row(mastery_stage="stabilizing", weak_cycle_count=2)
    result = _compute_mastery_transition(
        row, False, "full", streak_correct=0, streak_incorrect=3,
        drill_type="mc", distinct_days=2, total_after=10, drill_type_count=1,
    )
    assert result["historically_weak"] == 1


def test_legacy_weak_remapped():
    row = _base_row(mastery_stage="weak")
    result = _compute_mastery_transition(
        row, True, "full", streak_correct=2, streak_incorrect=0,
        drill_type="mc", distinct_days=1, total_after=3, drill_type_count=1,
    )
    assert result["mastery_stage"] == "passed_once"


def test_legacy_improving_remapped():
    row = _base_row(mastery_stage="improving")
    result = _compute_mastery_transition(
        row, True, "full", streak_correct=6, streak_incorrect=0,
        drill_type="mc", distinct_days=3, total_after=10, drill_type_count=2,
    )
    assert result["mastery_stage"] == "stable"


# ---- TestComputeRetentionUpdate ----

def test_first_attempt_correct():
    row = _base_row()
    result = _compute_retention_update(row, True, "full")
    assert result["half_life"] > INITIAL_HALF_LIFE
    assert result["difficulty"] < 0.5  # easier after correct
    assert result["p_recall"] >= 0.0
    assert result["p_recall"] <= 1.0


def test_first_attempt_wrong():
    row = _base_row()
    result = _compute_retention_update(row, False, "full")
    assert result["half_life"] <= INITIAL_HALF_LIFE
    assert result["difficulty"] > 0.5  # harder after wrong


def test_partial_confidence_dampened_update():
    """Half/narrowed confidence applies per-confidence dampened retention update."""
    row = _base_row(half_life_days=5.0, difficulty=0.4)
    result_full = _compute_retention_update(row, True, "full")
    result_narrowed = _compute_retention_update(row, True, "narrowed")
    result_half = _compute_retention_update(row, True, "half")
    # Narrowed uses CONFIDENCE_DAMPEN["narrowed"] = 0.4 (weaker than half)
    expected_hl_narrowed = 5.0 + (result_full["half_life"] - 5.0) * CONFIDENCE_DAMPEN["narrowed"]
    assert result_narrowed["half_life"] == pytest.approx(expected_hl_narrowed, abs=0.01)
    assert result_narrowed["half_life"] != 5.0  # not frozen
    # Half uses CONFIDENCE_DAMPEN["half"] = 0.5
    expected_hl_half = 5.0 + (result_full["half_life"] - 5.0) * CONFIDENCE_DAMPEN["half"]
    assert result_half["half_life"] == pytest.approx(expected_hl_half, abs=0.01)
    # Narrowed should be closer to original than half (weaker signal)
    assert abs(result_narrowed["half_life"] - 5.0) < abs(result_half["half_life"] - 5.0)


def test_half_wrong_dampened():
    """Half confidence wrong applies dampened difficulty increase."""
    row = _base_row(difficulty=0.5)
    result = _compute_retention_update(row, False, "half")
    assert result["difficulty"] > 0.5


def test_unknown_confidence_dampened():
    """Unknown confidence applies dampened update (treats as failed recall)."""
    row = _base_row(half_life_days=5.0, difficulty=0.4)
    result = _compute_retention_update(row, True, "unknown")
    # Unknown now applies dampened failed-recall update, not frozen
    assert result["half_life"] < 5.0, "unknown should reduce HL (dampened failed recall)"
    assert result["difficulty"] != 0.4, "unknown should adjust difficulty (dampened)"


def test_p_recall_in_range():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    row = _base_row(last_review_date=yesterday, half_life_days=2.0)
    result = _compute_retention_update(row, True, "full")
    assert result["p_recall"] > 0.0
    assert result["p_recall"] <= 1.0
