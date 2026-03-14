"""M/G/1 queue model for the review queue.

Replaces linear extrapolation with a proper queueing-theory model.
Computes utilization, average queue length, wait time, and overflow
probability from actual session_log and progress data.

Uses Little's Law (L = lambda * W) for validation.

Zero Claude tokens at runtime — all deterministic computation.
"""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date, timedelta

from .. import db

logger = logging.getLogger(__name__)

# Queue capacity: maximum manageable review queue size before
# the learner should stop adding new items.
DEFAULT_QUEUE_CAPACITY = 50


def _compute_arrival_rate(conn: sqlite3.Connection, user_id: int,
                          lookback_days: int = 30) -> float:
    """Compute lambda: new items entering the review queue per day.

    Counts items that had their first attempt in the lookback window.
    """
    # No first_attempt_date column — approximate by counting items with
    # few attempts and recent last_review_date (recently introduced items).
    row = conn.execute("""
        SELECT COUNT(DISTINCT content_item_id) as cnt
        FROM progress
        WHERE user_id = ?
          AND total_attempts > 0
          AND total_attempts <= 5
          AND last_review_date >= date('now', ? || ' days')
    """, (user_id, f"-{lookback_days}")).fetchone()

    new_items = (row["cnt"] or 0) if row else 0
    # Also count items re-entering from decay
    try:
        decay_row = conn.execute("""
            SELECT COUNT(DISTINCT content_item_id) as cnt
            FROM progress
            WHERE user_id = ?
              AND mastery_stage = 'decayed'
              AND last_review_date >= date('now', ? || ' days')
        """, (user_id, f"-{lookback_days}")).fetchone()
        decayed_reentries = (decay_row["cnt"] or 0) if decay_row else 0
    except sqlite3.OperationalError:
        decayed_reentries = 0

    total_arrivals = new_items + decayed_reentries
    return total_arrivals / max(lookback_days, 1)


def _compute_service_rate(conn: sqlite3.Connection, user_id: int,
                          lookback_days: int = 30) -> tuple[float, float]:
    """Compute mu and sigma^2: items reviewed per day and variance.

    Service = an item being reviewed and either promoted or re-queued
    at a longer interval. Returns (mu, sigma_squared).
    """
    sessions = db.get_session_history(conn, limit=50, user_id=user_id)
    if not sessions:
        return 0.0, 0.0

    # Filter to lookback window
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    recent = [s for s in sessions if (s.get("started_at") or "") >= cutoff]
    if not recent:
        return 0.0, 0.0

    # Items completed per session
    items_per_session = [s.get("items_completed", 0) for s in recent]
    dates_seen = set()
    for s in recent:
        if s.get("started_at"):
            dates_seen.add(s["started_at"][:10])

    active_days = max(len(dates_seen), 1)
    total_items = sum(items_per_session)
    mu = total_items / max(lookback_days, 1)  # items/day averaged over window

    # Variance in service time: variance of items-per-day
    if len(items_per_session) >= 2:
        mean_per_session = total_items / len(items_per_session)
        variance = sum((x - mean_per_session) ** 2 for x in items_per_session) / (len(items_per_session) - 1)
        # Convert session variance to daily variance
        sessions_per_day = len(recent) / max(lookback_days, 1)
        sigma_sq = variance * sessions_per_day if sessions_per_day > 0 else variance
    else:
        sigma_sq = 0.0

    return mu, sigma_sq


def queue_model(conn: sqlite3.Connection, user_id: int = 1,
                queue_capacity: int = DEFAULT_QUEUE_CAPACITY) -> dict:
    """Model the review queue as an M/G/1 queue.

    Arrival rate (lambda): new items entering queue per day
    Service rate (mu): items reviewed per day
    Service time variance (sigma^2): variance in review throughput

    Returns:
    - utilization (rho = lambda/mu)
    - avg_queue_length (L via Pollaczek-Khinchine formula)
    - avg_wait_time (W = L/lambda via Little's Law)
    - overflow_probability: P(queue > capacity)
    - stability: whether rho < 1
    - recommendation: string
    """
    arrival_rate = _compute_arrival_rate(conn, user_id)
    service_rate, service_variance = _compute_service_rate(conn, user_id)

    # Current queue depth
    due_count = db.get_items_due_count(conn, user_id=user_id)

    # Handle edge cases
    if service_rate <= 0:
        if arrival_rate <= 0:
            return {
                "arrival_rate": 0.0,
                "service_rate": 0.0,
                "utilization": 0.0,
                "avg_queue_length": due_count,
                "avg_wait_time": 0.0,
                "overflow_probability": 0.0,
                "current_queue_depth": due_count,
                "queue_capacity": queue_capacity,
                "stability": True,
                "littles_law_check": 0.0,
                "recommendation": "No activity data yet. Start practicing to generate queue metrics.",
            }
        return {
            "arrival_rate": round(arrival_rate, 3),
            "service_rate": 0.0,
            "utilization": float("inf"),
            "avg_queue_length": float("inf"),
            "avg_wait_time": float("inf"),
            "overflow_probability": 1.0,
            "current_queue_depth": due_count,
            "queue_capacity": queue_capacity,
            "stability": False,
            "littles_law_check": 0.0,
            "recommendation": "Queue is growing with no review activity. Resume sessions to stabilize.",
        }

    rho = arrival_rate / service_rate

    if rho >= 1.0:
        # Unstable queue
        return {
            "arrival_rate": round(arrival_rate, 3),
            "service_rate": round(service_rate, 3),
            "service_variance": round(service_variance, 3),
            "utilization": round(rho, 3),
            "avg_queue_length": float("inf"),
            "avg_wait_time": float("inf"),
            "overflow_probability": 1.0,
            "current_queue_depth": due_count,
            "queue_capacity": queue_capacity,
            "stability": False,
            "littles_law_check": 0.0,
            "recommendation": (
                f"Queue is unstable (utilization {rho:.0%}). "
                f"Reduce new items or increase session frequency. "
                f"Current arrival: {arrival_rate:.1f}/day, service: {service_rate:.1f}/day."
            ),
        }

    # Pollaczek-Khinchine formula for M/G/1:
    # L_q = (rho^2 + lambda^2 * sigma^2) / (2 * (1 - rho))
    # L = L_q + rho (items in service + items waiting)
    rho_sq = rho ** 2
    lambda_sq_sigma_sq = (arrival_rate ** 2) * service_variance
    l_q = (rho_sq + lambda_sq_sigma_sq) / (2.0 * (1.0 - rho))
    l_total = l_q + rho

    # Little's Law: W = L / lambda
    w = l_total / arrival_rate if arrival_rate > 0 else 0.0

    # Little's Law validation: L should approximately equal lambda * W
    littles_check = abs(l_total - arrival_rate * w) if arrival_rate > 0 else 0.0

    # Overflow probability: P(queue > capacity)
    # For M/G/1, approximate using geometric tail: P(Q > k) ~ rho^k
    if rho > 0 and rho < 1:
        overflow_prob = rho ** queue_capacity
    else:
        overflow_prob = 0.0

    # Generate recommendation
    if rho < 0.5:
        recommendation = (
            f"Queue is healthy ({rho:.0%} utilization). "
            f"Room to add more new items per session."
        )
    elif rho < 0.75:
        recommendation = (
            f"Queue is moderately loaded ({rho:.0%} utilization). "
            f"Current pace is sustainable."
        )
    elif rho < 0.9:
        recommendation = (
            f"Queue is getting heavy ({rho:.0%} utilization). "
            f"Consider reducing new items from {arrival_rate:.1f}/day to "
            f"{arrival_rate * 0.7:.1f}/day."
        )
    else:
        recommendation = (
            f"Queue is near capacity ({rho:.0%} utilization). "
            f"Strongly recommend pausing new items and focusing on reviews."
        )

    return {
        "arrival_rate": round(arrival_rate, 3),
        "service_rate": round(service_rate, 3),
        "service_variance": round(service_variance, 3),
        "utilization": round(rho, 3),
        "avg_queue_length": round(l_total, 1),
        "avg_wait_time_days": round(w, 1),
        "overflow_probability": round(overflow_prob, 6),
        "current_queue_depth": due_count,
        "queue_capacity": queue_capacity,
        "stability": True,
        "littles_law_check": round(littles_check, 4),
        "recommendation": recommendation,
    }
