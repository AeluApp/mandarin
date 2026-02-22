"""Regression tests: pin every SRS constant to prevent accidental drift.

If any constant changes, a test here will fail. That is intentional.
Update these values ONLY when you deliberately change a constant in config.py.
"""


# ---- Retention model ----

def test_recall_threshold():
    from mandarin.config import RECALL_THRESHOLD
    assert RECALL_THRESHOLD == 0.85


def test_min_half_life():
    from mandarin.config import MIN_HALF_LIFE
    assert MIN_HALF_LIFE == 0.5


def test_max_half_life():
    from mandarin.config import MAX_HALF_LIFE
    assert MAX_HALF_LIFE == 365.0


def test_initial_half_life():
    from mandarin.config import INITIAL_HALF_LIFE
    assert INITIAL_HALF_LIFE == 1.0


def test_max_interval_equals_max_half_life():
    from mandarin.config import MAX_INTERVAL, MAX_HALF_LIFE
    assert MAX_INTERVAL == MAX_HALF_LIFE


# ---- Ease parameters ----

def test_ease_floor():
    from mandarin.config import EASE_FLOOR
    assert EASE_FLOOR == 1.3


def test_ease_correct_boost():
    from mandarin.config import EASE_CORRECT_BOOST
    assert EASE_CORRECT_BOOST == 0.1


def test_ease_wrong_penalty():
    from mandarin.config import EASE_WRONG_PENALTY
    assert EASE_WRONG_PENALTY == 0.2


def test_ease_narrowed_penalty():
    from mandarin.config import EASE_NARROWED_PENALTY
    assert EASE_NARROWED_PENALTY == 0.03


def test_ease_half_penalty():
    from mandarin.config import EASE_HALF_PENALTY
    assert EASE_HALF_PENALTY == 0.05


# ---- Interval parameters ----

def test_interval_initial():
    from mandarin.config import INTERVAL_INITIAL
    assert INTERVAL_INITIAL == 1.0


def test_interval_second():
    from mandarin.config import INTERVAL_SECOND
    assert INTERVAL_SECOND == 3.0


def test_interval_wrong():
    from mandarin.config import INTERVAL_WRONG
    assert INTERVAL_WRONG == 0.5


def test_interval_narrowed_mult():
    from mandarin.config import INTERVAL_NARROWED_MULT
    assert INTERVAL_NARROWED_MULT == 0.6


def test_interval_half_mult():
    from mandarin.config import INTERVAL_HALF_MULT
    assert INTERVAL_HALF_MULT == 0.5


# ---- Streak cap thresholds ----

def test_streak_stable_threshold():
    from mandarin.config import STREAK_STABLE_THRESHOLD
    assert STREAK_STABLE_THRESHOLD == 10


def test_streak_stable_mult():
    from mandarin.config import STREAK_STABLE_MULT
    assert STREAK_STABLE_MULT == 1.3


def test_streak_extended_threshold():
    from mandarin.config import STREAK_EXTENDED_THRESHOLD
    assert STREAK_EXTENDED_THRESHOLD == 15


def test_streak_extended_mult():
    from mandarin.config import STREAK_EXTENDED_MULT
    assert STREAK_EXTENDED_MULT == 1.2


# ---- Promotion thresholds ----

def test_promote_passed_once_streak():
    from mandarin.config import PROMOTE_PASSED_ONCE_STREAK
    assert PROMOTE_PASSED_ONCE_STREAK == 2


def test_promote_stabilizing_streak():
    from mandarin.config import PROMOTE_STABILIZING_STREAK
    assert PROMOTE_STABILIZING_STREAK == 3


def test_promote_stabilizing_days():
    from mandarin.config import PROMOTE_STABILIZING_DAYS
    assert PROMOTE_STABILIZING_DAYS == 2


def test_promote_stable_streak():
    from mandarin.config import PROMOTE_STABLE_STREAK
    assert PROMOTE_STABLE_STREAK == 6


def test_promote_stable_attempts():
    from mandarin.config import PROMOTE_STABLE_ATTEMPTS
    assert PROMOTE_STABLE_ATTEMPTS == 10


def test_promote_stable_drill_types():
    from mandarin.config import PROMOTE_STABLE_DRILL_TYPES
    assert PROMOTE_STABLE_DRILL_TYPES == 2


def test_promote_stable_days():
    from mandarin.config import PROMOTE_STABLE_DAYS
    assert PROMOTE_STABLE_DAYS == 3


def test_promote_durable_days_stable():
    from mandarin.config import PROMOTE_DURABLE_DAYS_STABLE
    assert PROMOTE_DURABLE_DAYS_STABLE == 30


def test_promote_durable_successes():
    from mandarin.config import PROMOTE_DURABLE_SUCCESSES
    assert PROMOTE_DURABLE_SUCCESSES == 5


# ---- Demotion thresholds ----

def test_demote_stable_streak_incorrect():
    from mandarin.config import DEMOTE_STABLE_STREAK_INCORRECT
    assert DEMOTE_STABLE_STREAK_INCORRECT == 3


def test_demote_stabilizing_streak_incorrect():
    from mandarin.config import DEMOTE_STABILIZING_STREAK_INCORRECT
    assert DEMOTE_STABILIZING_STREAK_INCORRECT == 3


def test_demote_weak_cycle_threshold():
    from mandarin.config import DEMOTE_WEAK_CYCLE_THRESHOLD
    assert DEMOTE_WEAK_CYCLE_THRESHOLD == 3


# ---- Recovery ----

def test_recovery_streak_correct():
    from mandarin.config import RECOVERY_STREAK_CORRECT
    assert RECOVERY_STREAK_CORRECT == 3


# ---- Difficulty update ----

def test_difficulty_correct_alpha():
    from mandarin.config import DIFFICULTY_CORRECT_ALPHA
    assert DIFFICULTY_CORRECT_ALPHA == 0.05


def test_difficulty_wrong_beta():
    from mandarin.config import DIFFICULTY_WRONG_BETA
    assert DIFFICULTY_WRONG_BETA == 0.065


def test_difficulty_half_wrong_penalty():
    from mandarin.config import DIFFICULTY_HALF_WRONG_PENALTY
    assert DIFFICULTY_HALF_WRONG_PENALTY == 0.02


# ---- Retention model tuning ----

def test_lag_clamp_min():
    from mandarin.config import LAG_CLAMP_MIN
    assert LAG_CLAMP_MIN == 0.3


def test_lag_clamp_max():
    from mandarin.config import LAG_CLAMP_MAX
    assert LAG_CLAMP_MAX == 4.0


def test_partial_confidence_dampen():
    from mandarin.config import PARTIAL_CONFIDENCE_DAMPEN
    assert PARTIAL_CONFIDENCE_DAMPEN == 0.5


# ---- Structural and relational invariants ----

def test_no_circular_imports_star():
    """from mandarin.config import * should succeed without error."""
    exec("from mandarin.config import *")


def test_all_constants_are_numeric():
    """Every pinned constant must be int or float."""
    from mandarin.config import (
        RECALL_THRESHOLD, MIN_HALF_LIFE, MAX_HALF_LIFE, INITIAL_HALF_LIFE,
        MAX_INTERVAL, EASE_FLOOR, EASE_CORRECT_BOOST, EASE_WRONG_PENALTY,
        EASE_NARROWED_PENALTY, EASE_HALF_PENALTY,
        INTERVAL_INITIAL, INTERVAL_SECOND, INTERVAL_WRONG,
        INTERVAL_NARROWED_MULT, INTERVAL_HALF_MULT,
        STREAK_STABLE_THRESHOLD, STREAK_STABLE_MULT,
        STREAK_EXTENDED_THRESHOLD, STREAK_EXTENDED_MULT,
        PROMOTE_PASSED_ONCE_STREAK, PROMOTE_STABILIZING_STREAK,
        PROMOTE_STABILIZING_DAYS, PROMOTE_STABLE_STREAK,
        PROMOTE_STABLE_ATTEMPTS, PROMOTE_STABLE_DRILL_TYPES,
        PROMOTE_STABLE_DAYS, PROMOTE_DURABLE_DAYS_STABLE,
        PROMOTE_DURABLE_SUCCESSES,
        DEMOTE_STABLE_STREAK_INCORRECT, DEMOTE_STABILIZING_STREAK_INCORRECT,
        DEMOTE_WEAK_CYCLE_THRESHOLD, RECOVERY_STREAK_CORRECT,
        DIFFICULTY_CORRECT_ALPHA, DIFFICULTY_WRONG_BETA,
        DIFFICULTY_HALF_WRONG_PENALTY,
        LAG_CLAMP_MIN, LAG_CLAMP_MAX, PARTIAL_CONFIDENCE_DAMPEN,
    )
    constants = [
        RECALL_THRESHOLD, MIN_HALF_LIFE, MAX_HALF_LIFE, INITIAL_HALF_LIFE,
        MAX_INTERVAL, EASE_FLOOR, EASE_CORRECT_BOOST, EASE_WRONG_PENALTY,
        EASE_NARROWED_PENALTY, EASE_HALF_PENALTY,
        INTERVAL_INITIAL, INTERVAL_SECOND, INTERVAL_WRONG,
        INTERVAL_NARROWED_MULT, INTERVAL_HALF_MULT,
        STREAK_STABLE_THRESHOLD, STREAK_STABLE_MULT,
        STREAK_EXTENDED_THRESHOLD, STREAK_EXTENDED_MULT,
        PROMOTE_PASSED_ONCE_STREAK, PROMOTE_STABILIZING_STREAK,
        PROMOTE_STABILIZING_DAYS, PROMOTE_STABLE_STREAK,
        PROMOTE_STABLE_ATTEMPTS, PROMOTE_STABLE_DRILL_TYPES,
        PROMOTE_STABLE_DAYS, PROMOTE_DURABLE_DAYS_STABLE,
        PROMOTE_DURABLE_SUCCESSES,
        DEMOTE_STABLE_STREAK_INCORRECT, DEMOTE_STABILIZING_STREAK_INCORRECT,
        DEMOTE_WEAK_CYCLE_THRESHOLD, RECOVERY_STREAK_CORRECT,
        DIFFICULTY_CORRECT_ALPHA, DIFFICULTY_WRONG_BETA,
        DIFFICULTY_HALF_WRONG_PENALTY,
        LAG_CLAMP_MIN, LAG_CLAMP_MAX, PARTIAL_CONFIDENCE_DAMPEN,
    ]
    for c in constants:
        assert isinstance(c, (int, float)), f"{c!r} is not numeric"


def test_all_thresholds_positive():
    """Every threshold / constant must be positive (> 0)."""
    from mandarin.config import (
        RECALL_THRESHOLD, MIN_HALF_LIFE, MAX_HALF_LIFE, INITIAL_HALF_LIFE,
        MAX_INTERVAL, EASE_FLOOR, EASE_CORRECT_BOOST, EASE_WRONG_PENALTY,
        EASE_NARROWED_PENALTY, EASE_HALF_PENALTY,
        INTERVAL_INITIAL, INTERVAL_SECOND, INTERVAL_WRONG,
        INTERVAL_NARROWED_MULT, INTERVAL_HALF_MULT,
        STREAK_STABLE_THRESHOLD, STREAK_STABLE_MULT,
        STREAK_EXTENDED_THRESHOLD, STREAK_EXTENDED_MULT,
        PROMOTE_PASSED_ONCE_STREAK, PROMOTE_STABILIZING_STREAK,
        PROMOTE_STABILIZING_DAYS, PROMOTE_STABLE_STREAK,
        PROMOTE_STABLE_ATTEMPTS, PROMOTE_STABLE_DRILL_TYPES,
        PROMOTE_STABLE_DAYS, PROMOTE_DURABLE_DAYS_STABLE,
        PROMOTE_DURABLE_SUCCESSES,
        DEMOTE_STABLE_STREAK_INCORRECT, DEMOTE_STABILIZING_STREAK_INCORRECT,
        DEMOTE_WEAK_CYCLE_THRESHOLD, RECOVERY_STREAK_CORRECT,
        DIFFICULTY_CORRECT_ALPHA, DIFFICULTY_WRONG_BETA,
        DIFFICULTY_HALF_WRONG_PENALTY,
        LAG_CLAMP_MIN, LAG_CLAMP_MAX, PARTIAL_CONFIDENCE_DAMPEN,
    )
    all_vals = [
        RECALL_THRESHOLD, MIN_HALF_LIFE, MAX_HALF_LIFE, INITIAL_HALF_LIFE,
        MAX_INTERVAL, EASE_FLOOR, EASE_CORRECT_BOOST, EASE_WRONG_PENALTY,
        EASE_NARROWED_PENALTY, EASE_HALF_PENALTY,
        INTERVAL_INITIAL, INTERVAL_SECOND, INTERVAL_WRONG,
        INTERVAL_NARROWED_MULT, INTERVAL_HALF_MULT,
        STREAK_STABLE_THRESHOLD, STREAK_STABLE_MULT,
        STREAK_EXTENDED_THRESHOLD, STREAK_EXTENDED_MULT,
        PROMOTE_PASSED_ONCE_STREAK, PROMOTE_STABILIZING_STREAK,
        PROMOTE_STABILIZING_DAYS, PROMOTE_STABLE_STREAK,
        PROMOTE_STABLE_ATTEMPTS, PROMOTE_STABLE_DRILL_TYPES,
        PROMOTE_STABLE_DAYS, PROMOTE_DURABLE_DAYS_STABLE,
        PROMOTE_DURABLE_SUCCESSES,
        DEMOTE_STABLE_STREAK_INCORRECT, DEMOTE_STABILIZING_STREAK_INCORRECT,
        DEMOTE_WEAK_CYCLE_THRESHOLD, RECOVERY_STREAK_CORRECT,
        DIFFICULTY_CORRECT_ALPHA, DIFFICULTY_WRONG_BETA,
        DIFFICULTY_HALF_WRONG_PENALTY,
        LAG_CLAMP_MIN, LAG_CLAMP_MAX, PARTIAL_CONFIDENCE_DAMPEN,
    ]
    for v in all_vals:
        assert v > 0, f"{v!r} is not positive"


def test_max_interval_identity():
    from mandarin.config import MAX_INTERVAL, MAX_HALF_LIFE
    assert MAX_INTERVAL == MAX_HALF_LIFE


def test_lag_clamp_ordering():
    from mandarin.config import LAG_CLAMP_MIN, LAG_CLAMP_MAX
    assert LAG_CLAMP_MIN < LAG_CLAMP_MAX


def test_partial_confidence_dampen_range():
    from mandarin.config import PARTIAL_CONFIDENCE_DAMPEN
    assert PARTIAL_CONFIDENCE_DAMPEN > 0
    assert PARTIAL_CONFIDENCE_DAMPEN < 1


def test_promote_monotonic_progression():
    """Promotion streaks should form a strictly increasing sequence."""
    from mandarin.config import (
        PROMOTE_PASSED_ONCE_STREAK,
        PROMOTE_STABILIZING_STREAK,
        PROMOTE_STABLE_STREAK,
    )
    assert PROMOTE_PASSED_ONCE_STREAK < PROMOTE_STABILIZING_STREAK
    assert PROMOTE_STABILIZING_STREAK < PROMOTE_STABLE_STREAK


def test_streak_threshold_ordering():
    from mandarin.config import STREAK_STABLE_THRESHOLD, STREAK_EXTENDED_THRESHOLD
    assert STREAK_STABLE_THRESHOLD < STREAK_EXTENDED_THRESHOLD


# ---- Interleave weight constants ----

def test_interleave_weight_thresholds():
    from mandarin.config import (
        INTERLEAVE_STRONG_NOVEL_DIFF, INTERLEAVE_MILD_NOVEL_DIFF,
        INTERLEAVE_STRONG_REPEAT_DIFF, INTERLEAVE_MILD_REPEAT_DIFF,
    )
    assert INTERLEAVE_STRONG_NOVEL_DIFF == 0.1
    assert INTERLEAVE_MILD_NOVEL_DIFF == 0.05
    assert INTERLEAVE_STRONG_REPEAT_DIFF == -0.1
    assert INTERLEAVE_MILD_REPEAT_DIFF == -0.05
    # Novel thresholds are positive and ordered
    assert INTERLEAVE_MILD_NOVEL_DIFF < INTERLEAVE_STRONG_NOVEL_DIFF
    # Repeat thresholds are negative and ordered
    assert INTERLEAVE_STRONG_REPEAT_DIFF < INTERLEAVE_MILD_REPEAT_DIFF


def test_interleave_weight_values():
    from mandarin.config import (
        INTERLEAVE_WEIGHT_STRONG_NOVEL, INTERLEAVE_WEIGHT_MILD_NOVEL,
        INTERLEAVE_WEIGHT_STRONG_REPEAT, INTERLEAVE_WEIGHT_MILD_REPEAT,
        INTERLEAVE_WEIGHT_NEUTRAL,
        INTERLEAVE_WEIGHT_FLOOR, INTERLEAVE_WEIGHT_CEILING,
    )
    assert INTERLEAVE_WEIGHT_STRONG_NOVEL == 0.1
    assert INTERLEAVE_WEIGHT_MILD_NOVEL == 0.15
    assert INTERLEAVE_WEIGHT_STRONG_REPEAT == 0.4
    assert INTERLEAVE_WEIGHT_MILD_REPEAT == 0.3
    assert INTERLEAVE_WEIGHT_NEUTRAL == 0.25
    assert INTERLEAVE_WEIGHT_FLOOR == 0.05
    assert INTERLEAVE_WEIGHT_CEILING == 0.5
    # Floor < all weights < ceiling
    for w in (INTERLEAVE_WEIGHT_STRONG_NOVEL, INTERLEAVE_WEIGHT_MILD_NOVEL,
              INTERLEAVE_WEIGHT_STRONG_REPEAT, INTERLEAVE_WEIGHT_MILD_REPEAT,
              INTERLEAVE_WEIGHT_NEUTRAL):
        assert INTERLEAVE_WEIGHT_FLOOR <= w <= INTERLEAVE_WEIGHT_CEILING


# ---- Adaptive session length constants ----

def test_adaptive_length_constants():
    from mandarin.config import (
        ADAPTIVE_LENGTH_MIN_SESSIONS, ADAPTIVE_LENGTH_RECENT_SESSIONS,
        ADAPTIVE_LENGTH_LOW_COMPLETION, ADAPTIVE_LENGTH_SHRINK_FACTOR,
        ADAPTIVE_LENGTH_MIN_ITEMS, ADAPTIVE_LENGTH_HIGH_COMPLETION,
        ADAPTIVE_LENGTH_HIGH_MIN_SESSIONS, ADAPTIVE_LENGTH_GROW_FACTOR,
    )
    assert ADAPTIVE_LENGTH_MIN_SESSIONS == 3
    assert ADAPTIVE_LENGTH_RECENT_SESSIONS == 5
    assert ADAPTIVE_LENGTH_LOW_COMPLETION == 0.8
    assert ADAPTIVE_LENGTH_SHRINK_FACTOR == 0.8
    assert ADAPTIVE_LENGTH_MIN_ITEMS == 4
    assert ADAPTIVE_LENGTH_HIGH_COMPLETION == 0.95
    assert ADAPTIVE_LENGTH_HIGH_MIN_SESSIONS == 5
    assert ADAPTIVE_LENGTH_GROW_FACTOR == 1.1
    # Completion thresholds are ordered
    assert ADAPTIVE_LENGTH_LOW_COMPLETION < ADAPTIVE_LENGTH_HIGH_COMPLETION
    # Min sessions ≤ recent sessions
    assert ADAPTIVE_LENGTH_MIN_SESSIONS <= ADAPTIVE_LENGTH_RECENT_SESSIONS
