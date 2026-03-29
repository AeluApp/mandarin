"""FSRS per-learner calibration — fit personalized parameters from review history.

After 50+ reviews, gradient descent on the user's review history can personalize
the 19 FSRS parameters (w0-w18) to their individual learning patterns.

Uses only Python stdlib (no numpy/scipy). Optimization is simple gradient descent
with finite differences, suitable for running nightly in the quality scheduler.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3

from .fsrs import (
    DEFAULT_WEIGHTS,
    FSRSState,
    Rating,
    map_to_rating,
    retrievability,
    schedule_review,
)

logger = logging.getLogger(__name__)

# Minimum reviews before calibration is attempted
MIN_REVIEWS_FOR_CALIBRATION = 50

# Learning rate and iterations for gradient descent
LEARNING_RATE = 0.01
MAX_ITERATIONS = 100
CONVERGENCE_THRESHOLD = 1e-6

# Which parameters to optimize (first 17 are meaningful)
OPTIMIZABLE_PARAMS = list(range(17))


def calibrate_user(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    max_iterations: int = MAX_ITERATIONS,
) -> dict:
    """Fit personalized FSRS parameters for a user.

    Loads review history, runs gradient descent to minimize log-loss
    between predicted retrievability and actual outcomes.

    Returns:
        {
            "calibrated": bool,
            "weights": list[float] | None,
            "loss_before": float,
            "loss_after": float,
            "n_reviews": int,
            "improvement_pct": float,
        }
    """
    # Load review history
    reviews = _load_review_history(conn, user_id)
    if len(reviews) < MIN_REVIEWS_FOR_CALIBRATION:
        return {
            "calibrated": False,
            "weights": None,
            "n_reviews": len(reviews),
            "reason": f"Need {MIN_REVIEWS_FOR_CALIBRATION}+ reviews, have {len(reviews)}",
        }

    # Group reviews by item
    item_reviews = _group_by_item(reviews)

    # Initial loss with default weights
    loss_before = _compute_loss(item_reviews, DEFAULT_WEIGHTS)

    # Optimize
    best_weights = list(DEFAULT_WEIGHTS)
    best_loss = loss_before

    for iteration in range(max_iterations):
        # Compute gradient via finite differences
        gradient = _compute_gradient(item_reviews, best_weights)

        # Update weights
        new_weights = [
            w - LEARNING_RATE * g if i in OPTIMIZABLE_PARAMS else w
            for i, (w, g) in enumerate(zip(best_weights, gradient))
        ]

        # Clamp weights to reasonable ranges
        new_weights = _clamp_weights(new_weights)

        new_loss = _compute_loss(item_reviews, new_weights)

        if new_loss < best_loss:
            improvement = best_loss - new_loss
            best_weights = new_weights
            best_loss = new_loss
            if improvement < CONVERGENCE_THRESHOLD:
                break
        else:
            # Reduce learning rate on no improvement
            break

    # Save calibrated weights
    improvement_pct = (
        (loss_before - best_loss) / loss_before * 100
        if loss_before > 0
        else 0.0
    )

    if improvement_pct > 1.0:  # Only save if meaningful improvement
        _save_weights(conn, user_id, best_weights)
        logger.info(
            "FSRS calibration for user %d: loss %.4f → %.4f (%.1f%% improvement, %d reviews)",
            user_id, loss_before, best_loss, improvement_pct, len(reviews),
        )

    return {
        "calibrated": improvement_pct > 1.0,
        "weights": best_weights if improvement_pct > 1.0 else None,
        "loss_before": round(loss_before, 6),
        "loss_after": round(best_loss, 6),
        "n_reviews": len(reviews),
        "improvement_pct": round(improvement_pct, 2),
    }


def get_user_weights(conn: sqlite3.Connection, user_id: int) -> list[float]:
    """Get personalized FSRS weights for a user, falling back to defaults."""
    try:
        row = conn.execute(
            "SELECT w_vector FROM learner_fsrs_params WHERE user_id = ? "
            "ORDER BY calibrated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if row and row["w_vector"]:
            weights = json.loads(row["w_vector"])
            if isinstance(weights, list) and len(weights) >= 17:
                return weights
    except (sqlite3.OperationalError, json.JSONDecodeError, KeyError):
        pass
    return list(DEFAULT_WEIGHTS)


def calibrate_all_eligible(conn: sqlite3.Connection, limit: int = 20) -> int:
    """Calibrate FSRS parameters for all eligible users.

    Called by the quality scheduler nightly. Returns count of users calibrated.
    """
    try:
        rows = conn.execute(
            """
            SELECT user_id, COUNT(*) AS review_count
            FROM review_event
            GROUP BY user_id
            HAVING review_count >= ?
            ORDER BY review_count DESC
            LIMIT ?
            """,
            (MIN_REVIEWS_FOR_CALIBRATION, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return 0

    calibrated = 0
    for row in rows:
        try:
            result = calibrate_user(conn, row["user_id"])
            if result.get("calibrated"):
                calibrated += 1
        except Exception:
            logger.debug("FSRS calibration failed for user %d", row["user_id"])

    return calibrated


def _load_review_history(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """Load a user's review history for calibration."""
    try:
        rows = conn.execute(
            """
            SELECT content_item_id, correct, confidence, created_at,
                   response_ms
            FROM review_event
            WHERE user_id = ?
            ORDER BY created_at ASC
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def _group_by_item(reviews: list[dict]) -> dict[int, list[dict]]:
    """Group reviews by content_item_id, computing elapsed_days between reviews."""
    from datetime import datetime

    items: dict[int, list[dict]] = {}
    for r in reviews:
        item_id = r.get("content_item_id")
        if item_id is None:
            continue
        if item_id not in items:
            items[item_id] = []
        items[item_id].append(r)

    # Compute elapsed_days for each review
    for item_id, item_reviews in items.items():
        for i, review in enumerate(item_reviews):
            if i == 0:
                review["elapsed_days"] = 0.0
            else:
                try:
                    prev_dt = datetime.fromisoformat(item_reviews[i - 1]["created_at"])
                    curr_dt = datetime.fromisoformat(review["created_at"])
                    review["elapsed_days"] = max(0.0, (curr_dt - prev_dt).total_seconds() / 86400)
                except (ValueError, TypeError):
                    review["elapsed_days"] = 1.0

    return items


def _compute_loss(
    item_reviews: dict[int, list[dict]], weights: list[float]
) -> float:
    """Compute log-loss between predicted retrievability and actual outcomes."""
    total_loss = 0.0
    total_count = 0

    for item_id, reviews in item_reviews.items():
        state = FSRSState(stability=0.0, difficulty=5.0, reps=0, lapses=0)

        for review in reviews:
            rating = map_to_rating(
                review.get("correct", False),
                review.get("confidence", "full"),
            )
            elapsed = review.get("elapsed_days", 0.0)

            # Predict retrievability BEFORE this review
            if state.reps > 0 and elapsed > 0:
                r = retrievability(state.stability, elapsed)
                actual = 1.0 if review.get("correct") else 0.0

                # Log-loss: -[y·log(p) + (1-y)·log(1-p)]
                r_clamped = max(0.001, min(0.999, r))
                loss = -(
                    actual * math.log(r_clamped)
                    + (1 - actual) * math.log(1 - r_clamped)
                )
                total_loss += loss
                total_count += 1

            # Update state
            state, _ = schedule_review(state, rating, elapsed, weights)

    return total_loss / max(total_count, 1)


def _compute_gradient(
    item_reviews: dict[int, list[dict]], weights: list[float], eps: float = 0.001
) -> list[float]:
    """Compute gradient via finite differences (central difference)."""
    gradient = [0.0] * len(weights)
    base_loss = _compute_loss(item_reviews, weights)

    for i in OPTIMIZABLE_PARAMS:
        weights_plus = list(weights)
        weights_plus[i] += eps

        loss_plus = _compute_loss(item_reviews, weights_plus)
        gradient[i] = (loss_plus - base_loss) / eps

    return gradient


def _clamp_weights(weights: list[float]) -> list[float]:
    """Clamp weights to reasonable ranges."""
    clamped = list(weights)
    # Initial stabilities (w0-w3): must be positive
    for i in range(4):
        clamped[i] = max(0.01, min(100.0, clamped[i]))
    # Difficulty weights (w4-w7): reasonable range
    for i in range(4, 8):
        clamped[i] = max(-5.0, min(20.0, clamped[i]))
    # Stability update weights (w8-w16): reasonable range
    for i in range(8, min(17, len(clamped))):
        clamped[i] = max(-2.0, min(10.0, clamped[i]))
    return clamped


def _save_weights(conn: sqlite3.Connection, user_id: int, weights: list[float]) -> None:
    """Persist calibrated weights to learner_fsrs_params table."""
    try:
        conn.execute(
            """
            INSERT INTO learner_fsrs_params (user_id, w_vector, calibrated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                w_vector = excluded.w_vector,
                calibrated_at = excluded.calibrated_at
            """,
            (user_id, json.dumps([round(w, 6) for w in weights])),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("learner_fsrs_params table may not exist")
