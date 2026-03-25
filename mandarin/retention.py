"""Half-life retention model — principled memory decay and scheduling.

Based on the half-life regression (HLR) approach:
  p(recall) = 2^(-Δ/h)

Where:
  Δ = days since last review
  h = half-life (days until 50% recall probability)

This gives:
  - Principled scheduling: review when p drops below threshold
  - Item difficulty estimation from outcome patterns
  - Honest retention reporting (% above recall threshold)
  - Retention-based forecasting (predict future decay)

References:
  Settles & Meeder (2016), "A Trainable Spaced Repetition Model"
  Pimsleur (1967), graduated interval recall

Dual-model architecture:
  SM-2 (db/progress.py) sets review intervals — when to show an item next.
  Half-life regression (this module) predicts recall probability — how likely
  recall is right now. SM-2 drives scheduling; HLR drives prioritization,
  retention stats, and calibration. They address different questions about
  the same underlying memory process.
"""

import logging
import math
from datetime import date, timedelta, UTC
from typing import Optional

logger = logging.getLogger(__name__)


# ── Constants (canonical source: config.py) ──

from .config import (
    RECALL_THRESHOLD, MIN_HALF_LIFE, MAX_HALF_LIFE, INITIAL_HALF_LIFE,
    LAG_CLAMP_MIN, LAG_CLAMP_MAX,
)


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple:
    """Wilson score confidence interval for a binomial proportion.

    Better than normal approximation for small samples.
    Returns (lower, upper) bounds.
    """
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z ** 2 / total
    center = (p + z ** 2 / (2 * total)) / denom
    spread = z * math.sqrt(p * (1 - p) / total + z ** 2 / (4 * total ** 2)) / denom
    return (round(max(0.0, center - spread), 3), round(min(1.0, center + spread), 3))


def predict_recall(half_life_days: float, days_since_review: float) -> float:
    """Predict probability of recall using exponential decay.

    p = 2^(-Δ/h)

    Args:
        half_life_days: Current half-life estimate for this item.
        days_since_review: Days since last review (can be fractional).

    Returns:
        Probability of recall in [0, 1].
    """
    if half_life_days <= 0:
        return 0.0
    if days_since_review <= 0:
        return 1.0
    return 2.0 ** (-days_since_review / half_life_days)


def update_half_life(half_life: float, correct: bool,
                     days_since_review: float, difficulty: float) -> float:
    """Update half-life after a review attempt.

    On correct:
      Boost = 1 + clamp(lag_ratio, 0.5, 2.0) * (1 - 0.5 * difficulty)
      New half-life = old * boost

    On incorrect:
      Decay = max(0.1, 0.5 * (1 + difficulty))
      New half-life = max(MIN_HALF_LIFE, old * decay)

    The lag_ratio (Δ/h) captures how "overdue" the review was:
      - lag_ratio < 1: reviewed early → smaller boost
      - lag_ratio = 1: reviewed right at half-life → standard boost
      - lag_ratio > 1: reviewed late → larger boost (harder retrieval)

    Args:
        half_life: Current half-life in days.
        correct: Whether the answer was correct.
        days_since_review: Days since last review.
        difficulty: Item difficulty in [0, 1] (0=easy, 1=hard).

    Returns:
        Updated half-life in days, clamped to [MIN_HALF_LIFE, MAX_HALF_LIFE].
    """
    half_life = max(half_life, MIN_HALF_LIFE)
    difficulty = max(0.0, min(1.0, difficulty))

    if correct:
        lag_ratio = days_since_review / half_life if half_life > 0 else 1.0
        clamped_lag = max(LAG_CLAMP_MIN, min(LAG_CLAMP_MAX, lag_ratio))
        boost = 1.0 + clamped_lag * (1.0 - 0.5 * difficulty)
        new_hl = half_life * boost
    else:
        decay = max(0.1, 0.5 * (1.0 + difficulty))
        new_hl = half_life * decay

    return max(MIN_HALF_LIFE, min(MAX_HALF_LIFE, round(new_hl, 2)))


def update_difficulty(difficulty: float, correct: bool,
                      predicted_p: float) -> float:
    """Update item difficulty based on outcome vs prediction.

    If predicted recall was high but learner got it wrong:
      → Item is harder than estimated → increase difficulty
    If predicted recall was low but learner got it right:
      → Item is easier than estimated → decrease difficulty

    Uses a bounded update rule:
      On correct: d -= α * (1 + (p - 0.5))
      On wrong:   d += β * (1 + (p - 0.5))

    Where α = 0.05, β = 0.065 (β ≈ 1.3α: slight asymmetry near 85% recall target).

    Args:
        difficulty: Current difficulty in [0, 1].
        correct: Whether the answer was correct.
        predicted_p: Predicted recall probability before the attempt.

    Returns:
        Updated difficulty in [0.05, 0.95].
    """
    predicted_p = max(0.0, min(1.0, predicted_p))
    delta = predicted_p - 0.5

    if correct:
        difficulty -= 0.05 * (1.0 + delta)
    else:
        difficulty += 0.065 * (1.0 + delta)

    return round(max(0.05, min(0.95, difficulty)), 3)


def days_until_threshold(half_life_days: float,
                         threshold: float = RECALL_THRESHOLD) -> float:
    """Calculate days until recall probability drops to threshold.

    From p = 2^(-Δ/h):
      Δ = -h * log2(p)

    Args:
        half_life_days: Current half-life.
        threshold: Target recall probability.

    Returns:
        Days until recall drops to threshold.
    """
    if half_life_days <= 0 or threshold <= 0 or threshold >= 1:
        return 0.0
    return -half_life_days * math.log2(threshold)


def scheduling_priority(half_life_days: float, days_since_review: float,
                        difficulty: float) -> float:
    """Compute scheduling priority for an item.

    Higher priority = more urgently needs review.

    Priority = (1 - p_recall) * (1 + difficulty)

    Items near the recall threshold with high difficulty get highest priority.

    Args:
        half_life_days: Current half-life.
        days_since_review: Days since last review.
        difficulty: Item difficulty.

    Returns:
        Priority score (higher = schedule sooner).
    """
    p = predict_recall(half_life_days, days_since_review)
    return (1.0 - p) * (1.0 + difficulty)


def compute_retention_stats(conn, user_id: int = 1) -> dict:
    """Compute retention metrics across all reviewed items.

    Returns:
        {
            "total_items": int,
            "above_threshold": int,    # Items with p >= RECALL_THRESHOLD
            "below_threshold": int,    # Items with p < RECALL_THRESHOLD
            "avg_recall": float,       # Mean recall probability
            "avg_half_life": float,    # Mean half-life in days
            "avg_difficulty": float,   # Mean difficulty
            "retention_pct": float,    # % above threshold
            "by_modality": {mod: {above, below, avg_recall}},
            "by_hsk": {level: {above, below, avg_recall}},
        }
    """
    rows = conn.execute("""
        SELECT p.half_life_days, p.difficulty, p.last_review_date,
               p.modality, ci.hsk_level, p.total_attempts
        FROM progress p
        JOIN content_item ci ON p.content_item_id = ci.id
        WHERE p.total_attempts > 0
          AND p.half_life_days IS NOT NULL
          AND p.last_review_date IS NOT NULL
          AND p.user_id = ?
    """, (user_id,)).fetchall()

    # Coverage: how many items have been reviewed vs total in system
    coverage_row = conn.execute("""
        SELECT COUNT(DISTINCT ci.id) as total_in_system,
               COUNT(DISTINCT CASE WHEN p.total_attempts > 0 THEN ci.id END) as ever_reviewed
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.user_id = ?
    """, (user_id,)).fetchone()
    total_in_system = coverage_row["total_in_system"] or 0
    ever_reviewed = coverage_row["ever_reviewed"] or 0

    if not rows:
        return {
            "total_items": 0, "above_threshold": 0, "below_threshold": 0,
            "avg_recall": 0.0, "avg_half_life": 0.0, "avg_difficulty": 0.5,
            "retention_pct": 0.0, "by_modality": {}, "by_hsk": {},
            "total_in_system": total_in_system,
            "ever_reviewed": ever_reviewed,
            "coverage_pct": round(ever_reviewed / total_in_system * 100, 1) if total_in_system > 0 else 0.0,
            "retention_ci": (0.0, 0.0),
        }

    today = date.today()
    total = 0
    above = 0
    below = 0
    recall_sum = 0.0
    hl_sum = 0.0
    diff_sum = 0.0

    by_modality = {}
    by_hsk = {}

    for r in rows:
        hl = r["half_life_days"] or INITIAL_HALF_LIFE
        diff = r["difficulty"] or 0.5
        last_review = r["last_review_date"]

        try:
            review_date = date.fromisoformat(last_review[:10])
        except (ValueError, TypeError):
            logger.debug("Skipping item with unparseable review date: %s", last_review)
            continue

        days_since = max(0, (today - review_date).days)
        p = predict_recall(hl, days_since)

        total += 1
        recall_sum += p
        hl_sum += hl
        diff_sum += diff

        if p >= RECALL_THRESHOLD:
            above += 1
        else:
            below += 1

        # Per modality
        mod = r["modality"]
        if mod not in by_modality:
            by_modality[mod] = {"above": 0, "below": 0, "recall_sum": 0, "count": 0}
        by_modality[mod]["count"] += 1
        by_modality[mod]["recall_sum"] += p
        if p >= RECALL_THRESHOLD:
            by_modality[mod]["above"] += 1
        else:
            by_modality[mod]["below"] += 1

        # Per HSK level
        hsk = r["hsk_level"] or 0
        if hsk not in by_hsk:
            by_hsk[hsk] = {"above": 0, "below": 0, "recall_sum": 0, "count": 0}
        by_hsk[hsk]["count"] += 1
        by_hsk[hsk]["recall_sum"] += p
        if p >= RECALL_THRESHOLD:
            by_hsk[hsk]["above"] += 1
        else:
            by_hsk[hsk]["below"] += 1

    # Summarize per-group
    for group in list(by_modality.values()) + list(by_hsk.values()):
        group["avg_recall"] = round(group["recall_sum"] / group["count"], 3) if group["count"] > 0 else 0.0
        del group["recall_sum"]

    return {
        "total_items": total,
        "above_threshold": above,
        "below_threshold": below,
        "avg_recall": round(recall_sum / total, 3) if total > 0 else 0.0,
        "avg_half_life": round(hl_sum / total, 1) if total > 0 else 0.0,
        "avg_difficulty": round(diff_sum / total, 3) if total > 0 else 0.5,
        "retention_pct": round(above / total * 100, 1) if total > 0 else 0.0,
        "by_modality": by_modality,
        "by_hsk": by_hsk,
        "total_in_system": total_in_system,
        "ever_reviewed": ever_reviewed,
        "coverage_pct": round(ever_reviewed / total_in_system * 100, 1) if total_in_system > 0 else 0.0,
        "retention_ci": wilson_ci(above, total),
    }


def compute_session_metrics(conn, session_id: int, user_id: int = 1) -> dict:
    """Compute structured metrics for a completed session.

    Measures what actually happened — no inflation, no spin.

    Returns dict suitable for inserting into session_metrics table.
    """
    # Get items attempted in this session
    rows = conn.execute("""
        SELECT p.half_life_days, p.difficulty, p.last_review_date,
               p.content_item_id, p.modality
        FROM progress p
        WHERE p.user_id = ?
          AND p.content_item_id IN (
            SELECT DISTINCT content_item_id FROM error_log WHERE session_id = ?
            UNION
            SELECT DISTINCT ci.id FROM content_item ci
            JOIN progress p2 ON ci.id = p2.content_item_id
            WHERE p2.user_id = ? AND p2.last_review_date = date('now')
        )
        AND p.total_attempts > 0
    """, (user_id, session_id, user_id)).fetchall()

    today = date.today()
    above = 0
    below = 0
    recall_sum = 0.0
    diff_sum = 0.0
    total = 0

    for r in rows:
        hl = r["half_life_days"] or INITIAL_HALF_LIFE
        p = predict_recall(hl, 0)  # After review, recall is ~1.0
        total += 1
        recall_sum += p
        diff_sum += (r["difficulty"] or 0.5)
        if p >= RECALL_THRESHOLD:
            above += 1
        else:
            below += 1

    # Approximate strengthened/weakened from session results.
    # Items with all correct → half-life increased (strengthened).
    # Items with all incorrect → half-life decreased (weakened).
    strengthened = 0
    weakened = 0
    session_results = conn.execute("""
        SELECT el.content_item_id,
               SUM(CASE WHEN el.error_type IS NULL THEN 1 ELSE 0 END) as correct_count,
               COUNT(*) as total_count
        FROM error_log el
        WHERE el.session_id = ?
        GROUP BY el.content_item_id
    """, (session_id,)).fetchall()
    for sr in session_results:
        total_ct = sr["total_count"] or 0
        correct_ct = sr["correct_count"] or 0
        if total_ct > 0 and correct_ct == total_ct:
            strengthened += 1
        elif total_ct > 0 and correct_ct == 0:
            weakened += 1

    # Transfer events: items correct in a modality they haven't been tested in before
    transfer = 0
    transfer_rows = conn.execute("""
        SELECT p.content_item_id, p.modality, p.drill_types_seen
        FROM progress p
        WHERE p.user_id = ?
          AND p.last_review_date = ?
          AND p.total_attempts = 1
          AND p.total_correct = 1
    """, (user_id, today.isoformat())).fetchall()
    for tr in transfer_rows:
        # Check if this item has progress in other modalities
        other = conn.execute("""
            SELECT COUNT(*) FROM progress
            WHERE content_item_id = ? AND modality != ? AND total_attempts > 0
              AND user_id = ?
        """, (tr["content_item_id"], tr["modality"], user_id)).fetchone()
        if other and other[0] > 0:
            transfer += 1

    return {
        "recall_above_threshold": above,
        "recall_below_threshold": below,
        "avg_recall": round(recall_sum / total, 3) if total > 0 else None,
        "avg_difficulty": round(diff_sum / total, 3) if total > 0 else None,
        "items_strengthened": strengthened,
        "items_weakened": weakened,
        "transfer_events": transfer,
    }


def save_session_metrics(conn, session_id: int, metrics: dict, user_id: int = 1):
    """Save session metrics to the database."""
    from datetime import datetime, timezone
    conn.execute("""
        INSERT OR REPLACE INTO session_metrics
        (session_id, recall_above_threshold, recall_below_threshold,
         avg_recall, avg_difficulty, items_strengthened, items_weakened,
         transfer_events, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        metrics.get("recall_above_threshold", 0),
        metrics.get("recall_below_threshold", 0),
        metrics.get("avg_recall"),
        metrics.get("avg_difficulty"),
        metrics.get("items_strengthened", 0),
        metrics.get("items_weakened", 0),
        metrics.get("transfer_events", 0),
        datetime.now(UTC).isoformat(),
    ))
    conn.commit()


def compute_calibration(conn, n_bins: int = 5, user_id: int = 1) -> dict:
    """Compute calibration curve: predicted recall vs actual outcomes.

    Bins items by their last_p_recall at time of review, then checks
    whether actual accuracy in each bin matches the prediction.

    Returns:
        {
            "bins": [{"predicted": float, "actual": float, "count": int}, ...],
            "brier_score": float,  # Mean squared error of predictions (lower = better)
            "n_items": int,
            "calibration_error": float,  # Mean absolute calibration error
        }
    """
    # Use last_p_recall stored on progress rows + actual outcome from recent sessions
    rows = conn.execute("""
        SELECT p.last_p_recall, p.total_correct, p.total_attempts
        FROM progress p
        WHERE p.total_attempts >= 2
          AND p.last_p_recall IS NOT NULL
          AND p.user_id = ?
    """, (user_id,)).fetchall()

    if not rows:
        return {"bins": [], "brier_score": None, "n_items": 0, "calibration_error": None}

    # Bin by predicted recall
    [i / n_bins for i in range(n_bins + 1)]
    bins = [{"predicted_sum": 0.0, "actual_sum": 0.0, "count": 0} for _ in range(n_bins)]

    brier_sum = 0.0
    n = 0
    for r in rows:
        p_pred = r["last_p_recall"]
        if p_pred is None:
            continue
        # Use most recent accuracy as proxy for actual recall
        actual = r["total_correct"] / r["total_attempts"] if r["total_attempts"] > 0 else 0

        # Find bin
        bin_idx = min(int(p_pred * n_bins), n_bins - 1)
        bins[bin_idx]["predicted_sum"] += p_pred
        bins[bin_idx]["actual_sum"] += actual
        bins[bin_idx]["count"] += 1

        brier_sum += (p_pred - actual) ** 2
        n += 1

    result_bins = []
    calibration_error_sum = 0.0
    calibration_n = 0
    for _i, b in enumerate(bins):
        if b["count"] > 0:
            pred_avg = round(b["predicted_sum"] / b["count"], 3)
            actual_avg = round(b["actual_sum"] / b["count"], 3)
            result_bins.append({
                "predicted": pred_avg,
                "actual": actual_avg,
                "count": b["count"],
            })
            calibration_error_sum += abs(pred_avg - actual_avg) * b["count"]
            calibration_n += b["count"]

    return {
        "bins": result_bins,
        "brier_score": round(brier_sum / n, 4) if n > 0 else None,
        "n_items": n,
        "calibration_error": round(calibration_error_sum / calibration_n, 3) if calibration_n > 0 else None,
    }
