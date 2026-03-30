"""FSRS (Free Spaced Repetition Schedule) — evidence-based scheduling algorithm.

Implements FSRS-4.5 with 19 parameters controlling stability, difficulty, and
retrievability. Uses a power-law forgetting curve: R(t) = (1 + t/(9·S))^(-1)

References:
- Ye (2023): "A Stochastic Shortest Path Algorithm for Optimizing Spaced Repetition Scheduling"
- Open Spaced Repetition project: https://github.com/open-spaced-repetition/fsrs4anki

This implementation uses only Python stdlib (no numpy/scipy dependencies).
Default parameters are from FSRS-4.5 research. Per-learner calibration can
override defaults after 50+ reviews.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)


class Rating(IntEnum):
    """FSRS rating scale, mapped from Aelu's confidence + correctness."""
    AGAIN = 1   # Incorrect
    HARD = 2    # Correct but slow/uncertain
    GOOD = 3    # Correct with moderate confidence
    EASY = 4    # Correct with full confidence


# FSRS-4.5 default parameters (from research)
DEFAULT_WEIGHTS = [
    0.4072,   # w0: initial stability for Again
    1.1829,   # w1: initial stability for Hard
    3.1262,   # w2: initial stability for Good
    15.4722,  # w3: initial stability for Easy
    7.2102,   # w4: difficulty weight 1
    0.5316,   # w5: difficulty weight 2
    1.0651,   # w6: difficulty mean reversion speed
    0.0046,   # w7: stability decay for Again
    1.5418,   # w8: stability increase factor (success)
    0.1618,   # w9: difficulty factor on stability
    1.0000,   # w10: recall factor on stability
    2.0616,   # w11: stability factor on stability
    0.0565,   # w12: difficulty mean reversion target (scaled)
    0.3280,   # w13: success stability growth base
    1.4261,   # w14: failure stability recovery
    0.2197,   # w15: failure stability difficulty factor
    0.0000,   # w16: failure stability stability factor
    0.0000,   # w17: reserved
    0.0000,   # w18: reserved
]

# Target retrievability (desired recall probability when item is due)
DESIRED_RETENTION = 0.9

# Clamps
MIN_STABILITY = 0.1   # days
MAX_STABILITY = 36500  # 100 years
MIN_DIFFICULTY = 1.0
MAX_DIFFICULTY = 10.0


@dataclass
class FSRSState:
    """State of an item in FSRS."""
    stability: float    # S: memory stability in days (half-life analog)
    difficulty: float   # D: item difficulty [1, 10]
    reps: int           # number of reviews
    lapses: int         # number of times rated Again after first success


def map_to_rating(correct: bool, confidence: str = "full") -> Rating:
    """Map Aelu's correctness + confidence to FSRS rating.

    Aelu confidence levels: full, half, narrowed, unknown, narrowed_wrong
    """
    if not correct:
        return Rating.AGAIN
    if confidence in ("unknown", "narrowed_wrong"):
        return Rating.HARD
    if confidence in ("half", "narrowed"):
        return Rating.GOOD
    return Rating.EASY  # "full" confidence


def initial_stability(rating: Rating, w: list[float] | None = None) -> float:
    """Compute initial stability for a new item based on first rating."""
    if w is None:
        w = DEFAULT_WEIGHTS
    # w[0]-w[3] are initial stabilities for each rating
    idx = rating.value - 1
    if idx < len(w):
        return max(MIN_STABILITY, w[idx])
    return w[2]  # default to Good


def initial_difficulty(rating: Rating, w: list[float] | None = None) -> float:
    """Compute initial difficulty from first rating."""
    if w is None:
        w = DEFAULT_WEIGHTS
    # D0(G) = w[4] - exp(w[5] * (G - 1)) + 1
    d = w[4] - math.exp(w[5] * (rating.value - 1)) + 1
    return _clamp(d, MIN_DIFFICULTY, MAX_DIFFICULTY)


def retrievability(stability: float, elapsed_days: float) -> float:
    """Compute recall probability using FSRS power-law forgetting curve.

    R(t, S) = (1 + t/(9·S))^(-1)

    At t=0: R=1.0 (just reviewed)
    At t=9S: R=0.5 (half-life)
    """
    if stability <= 0 or elapsed_days < 0:
        return 1.0
    return (1 + elapsed_days / (9.0 * stability)) ** (-1)


def next_interval(stability: float, desired_retention: float = DESIRED_RETENTION) -> float:
    """Compute the optimal interval given stability and desired retention.

    Solve R(t, S) = desired_retention for t:
    t = 9·S·(1/R - 1)
    """
    if desired_retention <= 0 or desired_retention >= 1:
        return stability
    interval = 9.0 * stability * (1.0 / desired_retention - 1.0)
    return max(1.0, min(interval, MAX_STABILITY))


def update_stability_success(
    s: float, d: float, r: float, rating: Rating,
    w: list[float] | None = None,
) -> float:
    """Update stability after a successful review (rating >= Hard).

    S'(S, D, R, G) = S · (e^(w8) · (11 - D) · S^(-w9) · (e^(w10·(1-R)) - 1) · hard_penalty · easy_bonus + 1)
    """
    if w is None:
        w = DEFAULT_WEIGHTS

    # Core stability increase formula
    inner = (
        math.exp(w[8])
        * (11 - d)
        * (s ** (-w[9]))
        * (math.exp(w[10] * (1 - r)) - 1)
    )

    # Rating modifiers
    if rating == Rating.HARD:
        inner *= w[13]  # hard penalty (< 1)
    elif rating == Rating.EASY:
        inner *= w[14]  # easy bonus (> 1)

    new_s = s * (inner + 1)
    return _clamp(new_s, MIN_STABILITY, MAX_STABILITY)


def update_stability_failure(
    s: float, d: float, r: float,
    w: list[float] | None = None,
) -> float:
    """Update stability after a lapse (rating = Again).

    S'_f(D, S, R) = w[11] · D^(-w[12]) · ((S+1)^w[13] - 1) · e^(w[14]·(1-R))
    """
    if w is None:
        w = DEFAULT_WEIGHTS

    new_s = (
        w[11]
        * (d ** (-w[15]))
        * ((s + 1) ** w[16] - 1)
        * math.exp(w[14] * (1 - r))
    )
    return _clamp(new_s, MIN_STABILITY, max(s, MIN_STABILITY))


def update_difficulty(
    d: float, rating: Rating,
    w: list[float] | None = None,
) -> float:
    """Update difficulty after a review.

    D'(D, G) = w[6] · D0(3) · (1 - w[6]) + w[6] · (D - w[7] · (G - 3))
    Mean reversion toward D0(Good) with adjustment based on rating.
    """
    if w is None:
        w = DEFAULT_WEIGHTS

    d0_good = initial_difficulty(Rating.GOOD, w)
    delta = d - w[7] * (rating.value - 3)
    new_d = w[6] * d0_good + (1 - w[6]) * delta

    return _clamp(new_d, MIN_DIFFICULTY, MAX_DIFFICULTY)


def schedule_review(
    state: FSRSState,
    rating: Rating,
    elapsed_days: float,
    w: list[float] | None = None,
    desired_retention: float = DESIRED_RETENTION,
) -> tuple[FSRSState, float]:
    """Process a review and return updated state + next interval.

    Args:
        state: Current FSRS state (stability, difficulty, reps, lapses)
        rating: User's rating for this review
        elapsed_days: Days since last review
        w: FSRS parameters (uses defaults if None)
        desired_retention: Target recall probability at next review

    Returns:
        (new_state, interval_days)
    """
    if w is None:
        w = DEFAULT_WEIGHTS

    if state.reps == 0:
        # First review — initialize
        new_s = initial_stability(rating, w)
        new_d = initial_difficulty(rating, w)
        new_lapses = 1 if rating == Rating.AGAIN else 0
    else:
        # Compute current retrievability
        r = retrievability(state.stability, elapsed_days)

        # Update difficulty
        new_d = update_difficulty(state.difficulty, rating, w)

        # Update stability based on success/failure
        if rating == Rating.AGAIN:
            new_s = update_stability_failure(state.stability, new_d, r, w)
            new_lapses = state.lapses + 1
        else:
            new_s = update_stability_success(state.stability, new_d, r, rating, w)
            new_lapses = state.lapses

    interval = next_interval(new_s, desired_retention)

    new_state = FSRSState(
        stability=new_s,
        difficulty=new_d,
        reps=state.reps + 1,
        lapses=new_lapses,
    )

    return new_state, interval


def fsrs_schedule_from_history(
    reviews: list[dict],
    w: list[float] | None = None,
    desired_retention: float = DESIRED_RETENTION,
) -> dict:
    """Compute FSRS state and next interval from full review history.

    Args:
        reviews: List of {"correct": bool, "confidence": str, "elapsed_days": float}
                 in chronological order
        w: FSRS parameters
        desired_retention: Target retention

    Returns:
        {
            "stability": float,
            "difficulty": float,
            "retrievability": float,  # current recall probability
            "interval_days": float,   # recommended next interval
            "reps": int,
            "lapses": int,
        }
    """
    if not reviews:
        return {
            "stability": 0.0,
            "difficulty": 5.0,
            "retrievability": 0.0,
            "interval_days": 1.0,
            "reps": 0,
            "lapses": 0,
        }

    state = FSRSState(stability=0.0, difficulty=5.0, reps=0, lapses=0)
    interval = 1.0

    for review in reviews:
        rating = map_to_rating(
            review.get("correct", False),
            review.get("confidence", "full"),
        )
        elapsed = review.get("elapsed_days", 0.0)
        state, interval = schedule_review(state, rating, elapsed, w, desired_retention)

    # Current retrievability (assuming elapsed_days since last review = 0 for now)
    current_r = 1.0  # Just reviewed

    return {
        "stability": round(state.stability, 4),
        "difficulty": round(state.difficulty, 4),
        "retrievability": round(current_r, 4),
        "interval_days": round(interval, 2),
        "reps": state.reps,
        "lapses": state.lapses,
    }


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value to [minimum, maximum]."""
    return max(minimum, min(maximum, value))
