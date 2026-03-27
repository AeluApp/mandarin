"""Property-based tests for the SRS retention engine.

Tests invariants that must hold for ALL valid inputs, using hypothesis
to generate random values. Complements the hand-picked cases in
test_retention.py and the integration-level tests in test_retention_property.py.

Covers:
- update_half_life monotonicity (correct increases, incorrect decreases)
- predict_recall range, monotonicity, and boundary behavior
- days_until_threshold positivity and monotonicity
- update_difficulty clamping
- Half-life clamping between MIN_HALF_LIFE and MAX_HALF_LIFE
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math

from hypothesis import given, strategies as st, assume, settings, HealthCheck
from mandarin.retention import update_half_life, predict_recall, days_until_threshold, update_difficulty
from mandarin.config import MIN_HALF_LIFE, MAX_HALF_LIFE, RECALL_THRESHOLD


# ── Strategies ──

st_half_life = st.floats(min_value=0.5, max_value=365.0)
st_difficulty = st.floats(min_value=0.05, max_value=0.95)
st_days_since = st.floats(min_value=0.0, max_value=365.0)
st_p_recall = st.floats(min_value=0.0, max_value=1.0)


# ── update_half_life properties ──

@given(
    half_life=st_half_life,
    days_since=st.floats(min_value=0.01, max_value=365.0),
    difficulty=st_difficulty,
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_correct_answer_never_decreases_half_life(half_life, days_since, difficulty):
    """update_half_life with correct=True always returns HL >= input HL.

    A correct answer should strengthen memory, never weaken it.
    The result may equal the input only if clamped at MAX_HALF_LIFE.
    """
    new_hl = update_half_life(half_life, True, days_since, difficulty)
    # The input may be below MIN_HALF_LIFE, which gets clamped up internally.
    # Compare against the effective input (clamped to at least MIN_HALF_LIFE).
    effective_input = max(half_life, MIN_HALF_LIFE)
    assert new_hl >= effective_input, (
        f"correct answer decreased HL: {effective_input} -> {new_hl} "
        f"(days_since={days_since}, difficulty={difficulty})"
    )


@given(
    half_life=st.floats(min_value=1.0, max_value=300.0),
    days_since=st.floats(min_value=0.01, max_value=365.0),
    difficulty=st_difficulty,
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_incorrect_answer_never_increases_half_life(half_life, days_since, difficulty):
    """update_half_life with correct=False always returns HL <= input HL.

    A wrong answer should weaken memory, never strengthen it.
    The result may equal the input only if clamped at MIN_HALF_LIFE.
    """
    new_hl = update_half_life(half_life, False, days_since, difficulty)
    assert new_hl <= half_life, (
        f"incorrect answer increased HL: {half_life} -> {new_hl} "
        f"(days_since={days_since}, difficulty={difficulty})"
    )


@given(
    half_life=st_half_life,
    days_since=st_days_since,
    difficulty=st_difficulty,
    correct=st.booleans(),
)
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_half_life_always_clamped(half_life, days_since, difficulty, correct):
    """Half-life is always clamped between MIN_HALF_LIFE and MAX_HALF_LIFE."""
    new_hl = update_half_life(half_life, correct, days_since, difficulty)
    assert new_hl >= MIN_HALF_LIFE, f"HL below floor: {new_hl}"
    assert new_hl <= MAX_HALF_LIFE, f"HL above ceiling: {new_hl}"


# ── predict_recall properties ──

@given(
    half_life=st.floats(min_value=0.01, max_value=1000.0),
    days_since=st.floats(min_value=0.0, max_value=1000.0),
)
def test_predict_recall_always_in_unit_interval(half_life, days_since):
    """predict_recall always returns a value in [0, 1]."""
    p = predict_recall(half_life, days_since)
    assert 0.0 <= p <= 1.0, f"p_recall out of range: {p}"


@given(
    half_life=st.floats(min_value=0.01, max_value=1000.0),
    t1=st.floats(min_value=0.0, max_value=500.0),
    t2=st.floats(min_value=0.0, max_value=500.0),
)
def test_predict_recall_monotonically_decreasing_with_time(half_life, t1, t2):
    """More elapsed time should give lower or equal recall probability.

    Memory decays over time; recall can never improve by waiting longer.
    """
    assume(t1 < t2)
    p1 = predict_recall(half_life, t1)
    p2 = predict_recall(half_life, t2)
    assert p1 >= p2, (
        f"recall increased with time: p({t1})={p1} < p({t2})={p2} "
        f"(half_life={half_life})"
    )


@given(half_life=st.floats(min_value=0.01, max_value=1000.0))
def test_predict_recall_at_time_zero_is_one(half_life):
    """predict_recall at time=0 returns exactly 1.0.

    Immediately after review, recall should be perfect.
    """
    p = predict_recall(half_life, 0.0)
    assert p == 1.0, f"p_recall(hl={half_life}, t=0) = {p}, expected 1.0"


@given(half_life=st.floats(min_value=0.01, max_value=1000.0))
def test_predict_recall_at_half_life_is_half(half_life):
    """predict_recall at time=half_life returns approximately 0.5.

    By definition of half-life, p = 2^(-1) = 0.5.
    """
    p = predict_recall(half_life, half_life)
    assert abs(p - 0.5) < 1e-10, (
        f"p_recall(hl={half_life}, t={half_life}) = {p}, expected 0.5"
    )


# ── days_until_threshold properties ──

@given(half_life=st.floats(min_value=0.01, max_value=365.0))
def test_days_until_threshold_positive_for_positive_half_life(half_life):
    """days_until_threshold returns a positive value for any positive half_life.

    There is always a finite time until recall drops to the threshold.
    """
    result = days_until_threshold(half_life)
    assert result > 0, f"days_until_threshold({half_life}) = {result}, expected > 0"


@given(
    hl1=st.floats(min_value=0.01, max_value=365.0),
    hl2=st.floats(min_value=0.01, max_value=365.0),
)
def test_days_until_threshold_monotonically_increasing_with_half_life(hl1, hl2):
    """Longer half-life means more days until recall drops to threshold.

    Items with stronger memory take longer to decay to the review point.
    """
    assume(hl1 < hl2)
    d1 = days_until_threshold(hl1)
    d2 = days_until_threshold(hl2)
    assert d1 < d2, (
        f"days_until_threshold not monotonic: "
        f"d({hl1})={d1} >= d({hl2})={d2}"
    )


@given(
    half_life=st.floats(min_value=0.01, max_value=365.0),
    threshold=st.floats(min_value=0.01, max_value=0.99),
)
def test_days_until_threshold_matches_formula(half_life, threshold):
    """days_until_threshold should match the analytic formula: -h * log2(p)."""
    result = days_until_threshold(half_life, threshold)
    expected = -half_life * math.log2(threshold)
    assert abs(result - expected) < 1e-10, (
        f"days_until_threshold({half_life}, {threshold}) = {result}, expected {expected}"
    )


# ── update_difficulty properties ──

@given(
    difficulty=st_difficulty,
    correct=st.booleans(),
    predicted_p=st_p_recall,
)
def test_difficulty_always_clamped(difficulty, correct, predicted_p):
    """Difficulty is always clamped between 0.05 and 0.95 after update."""
    new_diff = update_difficulty(difficulty, correct, predicted_p)
    assert new_diff >= 0.05, f"difficulty below floor: {new_diff}"
    assert new_diff <= 0.95, f"difficulty above ceiling: {new_diff}"


@given(
    difficulty=st.floats(min_value=0.10, max_value=0.90),
    predicted_p=st.floats(min_value=0.0, max_value=1.0),
)
def test_correct_answer_decreases_or_maintains_difficulty(difficulty, predicted_p):
    """A correct answer should decrease (or maintain) difficulty.

    Getting an item right means it might be easier than estimated.
    """
    new_diff = update_difficulty(difficulty, True, predicted_p)
    assert new_diff <= difficulty, (
        f"correct answer increased difficulty: {difficulty} -> {new_diff}"
    )


@given(
    difficulty=st.floats(min_value=0.10, max_value=0.90),
    predicted_p=st.floats(min_value=0.0, max_value=1.0),
)
def test_incorrect_answer_increases_or_maintains_difficulty(difficulty, predicted_p):
    """A wrong answer should increase (or maintain) difficulty.

    Getting an item wrong means it might be harder than estimated.
    """
    new_diff = update_difficulty(difficulty, False, predicted_p)
    assert new_diff >= difficulty, (
        f"incorrect answer decreased difficulty: {difficulty} -> {new_diff}"
    )
