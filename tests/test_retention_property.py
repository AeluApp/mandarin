"""Property-based tests for retention model and SRS update functions.

Uses hypothesis to generate random inputs and verify invariants that
must hold for ALL valid inputs, not just hand-picked examples.
"""

import pytest
from datetime import date, timedelta

from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st

from mandarin.retention import predict_recall, update_half_life, update_difficulty
from mandarin.db.progress import (
    _compute_srs_update,
    _compute_retention_update,
)
from mandarin.config import (
    EASE_FLOOR, INITIAL_HALF_LIFE, MIN_HALF_LIFE, MAX_HALF_LIFE,
)
from mandarin.drills import char_overlap_score


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
        "total_correct": 0,
        "avg_response_ms": None,
        "drill_types_seen": "",
        "distinct_review_days": 0,
    }
    row.update(overrides)
    return row


# ---- Retention model: predict_recall ----

@given(
    half_life=st.floats(min_value=0.1, max_value=365.0),
    elapsed=st.floats(min_value=0.0, max_value=1000.0),
)
def test_p_recall_in_range(half_life, elapsed):
    """p_recall should always be in [0, 1]."""
    p = predict_recall(half_life, elapsed)
    assert p >= 0.0
    assert p <= 1.0


@given(
    half_life=st.floats(min_value=0.1, max_value=365.0),
    elapsed_a=st.floats(min_value=0.0, max_value=500.0),
    elapsed_b=st.floats(min_value=0.0, max_value=500.0),
)
def test_p_recall_monotonically_decreasing_with_elapsed(half_life, elapsed_a, elapsed_b):
    """More elapsed time should give lower or equal recall."""
    assume(elapsed_a < elapsed_b)
    p_a = predict_recall(half_life, elapsed_a)
    p_b = predict_recall(half_life, elapsed_b)
    assert p_a >= p_b


@given(
    hl_a=st.floats(min_value=0.1, max_value=365.0),
    hl_b=st.floats(min_value=0.1, max_value=365.0),
    elapsed=st.floats(min_value=0.1, max_value=500.0),
)
def test_p_recall_monotonically_increasing_with_half_life(hl_a, hl_b, elapsed):
    """Longer half-life should give higher or equal recall for same elapsed time."""
    assume(hl_a < hl_b)
    p_a = predict_recall(hl_a, elapsed)
    p_b = predict_recall(hl_b, elapsed)
    assert p_a <= p_b


@given(half_life=st.floats(min_value=0.1, max_value=365.0))
def test_p_recall_at_zero_elapsed_is_one(half_life):
    """p_recall(any_hl, 0) should be ~1.0."""
    p = predict_recall(half_life, 0.0)
    assert abs(p - 1.0) < 1e-10


# ---- SRS update: _compute_srs_update ----

@given(
    ease=st.floats(min_value=EASE_FLOOR, max_value=5.0),
    interval=st.floats(min_value=0.5, max_value=100.0),
    reps=st.integers(min_value=0, max_value=20),
    streak_c=st.integers(min_value=0, max_value=20),
    streak_i=st.integers(min_value=0, max_value=10),
    correct=st.booleans(),
    confidence=st.sampled_from(["full", "half", "unknown", "narrowed", "narrowed_wrong"]),
    mastery=st.sampled_from(["seen", "passed_once", "stabilizing", "stable", "durable", "decayed"]),
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_interval_always_positive(ease, interval, reps, streak_c, streak_i,
                                  correct, confidence, mastery):
    """Interval should always be positive after any update."""
    row = _base_row(
        ease_factor=ease,
        interval_days=interval,
        repetitions=reps,
        streak_correct=streak_c,
        streak_incorrect=streak_i,
    )
    result = _compute_srs_update(row, correct, confidence, None, mastery)
    assert result["interval"] > 0.0


@given(
    ease=st.floats(min_value=EASE_FLOOR, max_value=5.0),
    interval=st.floats(min_value=0.5, max_value=100.0),
    reps=st.integers(min_value=0, max_value=20),
    streak_c=st.integers(min_value=0, max_value=20),
    streak_i=st.integers(min_value=0, max_value=10),
    correct=st.booleans(),
    confidence=st.sampled_from(["full", "half", "unknown", "narrowed", "narrowed_wrong"]),
    mastery=st.sampled_from(["seen", "passed_once", "stabilizing", "stable", "durable", "decayed"]),
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_ease_never_below_floor(ease, interval, reps, streak_c, streak_i,
                                correct, confidence, mastery):
    """Ease should always be >= EASE_FLOOR after any update."""
    row = _base_row(
        ease_factor=ease,
        interval_days=interval,
        repetitions=reps,
        streak_correct=streak_c,
        streak_incorrect=streak_i,
    )
    result = _compute_srs_update(row, correct, confidence, None, mastery)
    assert result["ease"] >= EASE_FLOOR


@given(
    streak_c=st.integers(min_value=0, max_value=20),
    reps=st.integers(min_value=0, max_value=20),
)
def test_correct_increases_streak(streak_c, reps):
    """A correct answer with full confidence should increment streak_correct."""
    row = _base_row(
        streak_correct=streak_c,
        streak_incorrect=0,
        repetitions=reps,
    )
    result = _compute_srs_update(row, True, "full", None, "seen")
    assert result["streak_correct"] == streak_c + 1


@given(
    streak_c=st.integers(min_value=0, max_value=20),
    streak_i=st.integers(min_value=0, max_value=10),
    reps=st.integers(min_value=0, max_value=20),
)
def test_wrong_resets_streak(streak_c, streak_i, reps):
    """A wrong answer with full confidence should reset streak_correct to 0."""
    row = _base_row(
        streak_correct=streak_c,
        streak_incorrect=streak_i,
        repetitions=reps,
    )
    result = _compute_srs_update(row, False, "full", None, "seen")
    assert result["streak_correct"] == 0


# ---- Retention update: _compute_retention_update ----

@given(
    half_life=st.floats(min_value=MIN_HALF_LIFE, max_value=MAX_HALF_LIFE),
    difficulty=st.floats(min_value=0.05, max_value=0.95),
    correct=st.booleans(),
    confidence=st.sampled_from(["full", "half", "narrowed"]),
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_difficulty_in_range(half_life, difficulty, correct, confidence):
    """Difficulty should always stay in [0, 1] after update."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    row = _base_row(
        half_life_days=half_life,
        difficulty=difficulty,
        last_review_date=yesterday,
    )
    result = _compute_retention_update(row, correct, confidence)
    assert result["difficulty"] >= 0.0
    assert result["difficulty"] <= 1.0


@given(
    half_life=st.floats(min_value=MIN_HALF_LIFE, max_value=MAX_HALF_LIFE),
    difficulty=st.floats(min_value=0.05, max_value=0.95),
    correct=st.booleans(),
    confidence=st.sampled_from(["full", "half", "narrowed"]),
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_half_life_in_bounds(half_life, difficulty, correct, confidence):
    """Half-life should always be in [MIN_HALF_LIFE, MAX_HALF_LIFE] after update."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    row = _base_row(
        half_life_days=half_life,
        difficulty=difficulty,
        last_review_date=yesterday,
    )
    result = _compute_retention_update(row, correct, confidence)
    assert result["half_life"] >= MIN_HALF_LIFE
    assert result["half_life"] <= MAX_HALF_LIFE


# ---- Scoring: char_overlap_score ----

@given(
    s1=st.text(min_size=0, max_size=50),
    s2=st.text(min_size=0, max_size=50),
)
def test_score_in_range(s1, s2):
    """Score should always be in [0, 1]."""
    score = char_overlap_score(s1, s2)
    assert score >= 0.0
    assert score <= 1.0


@given(s=st.text(min_size=1, max_size=50))
def test_identical_strings_score_one(s):
    """char_overlap_score(s, s) should be 1.0 for any non-empty string."""
    score = char_overlap_score(s, s)
    assert score == pytest.approx(1.0)


@given(s=st.text(min_size=0, max_size=50))
def test_empty_first_is_zero(s):
    """char_overlap_score("", anything) should be 0.0."""
    score = char_overlap_score("", s)
    assert score == pytest.approx(0.0)


@given(s=st.text(min_size=1, max_size=50))
def test_empty_second_is_zero(s):
    """char_overlap_score(anything, "") should be 0.0."""
    score = char_overlap_score(s, "")
    assert score == pytest.approx(0.0)
