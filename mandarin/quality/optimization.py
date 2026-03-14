"""Formal optimization for session scheduling decisions.

Three tools:
1. optimize_session: maximize expected retention gain per minute
2. decision_table: return-probability x queue-state decision matrix
3. pareto_frontier: multi-objective optimization (retention vs breadth vs time)

Uses scipy.optimize.linprog when available; falls back to greedy heuristic.

Zero Claude tokens at runtime — all deterministic computation.
"""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional

from .. import db
from ..config import (
    SECONDS_PER_DRILL,
    MAX_NEW_ITEM_RATIO,
    NEW_BUDGET_DEFAULT,
)

logger = logging.getLogger(__name__)

# Cognitive load constraint: max new items per 5-minute window
MAX_NEW_PER_5MIN = 3

# Session composition bounds
MIN_REVIEW_FRACTION = 0.60
MAX_NEW_FRACTION = 0.40


# ── Helpers ─────────────────────────────────────────────────────────

def _get_candidate_items(conn: sqlite3.Connection, user_id: int,
                         limit: int = 100) -> list[dict]:
    """Fetch candidate items for scheduling with priority metadata."""
    today = date.today().isoformat()
    rows = conn.execute("""
        SELECT ci.id, ci.hanzi, ci.pinyin, ci.english, ci.hsk_level,
               ci.difficulty, ci.item_type,
               p.total_attempts, p.total_correct, p.streak_correct,
               p.interval_days, p.half_life_days, p.mastery_stage,
               p.last_review_date, p.next_review_date,
               (p.total_attempts - p.total_correct) as error_count,
               CASE WHEN p.next_review_date IS NULL THEN 1 ELSE 0 END as is_new,
               CASE WHEN p.next_review_date IS NOT NULL
                    THEN MAX(0, julianday(?) - julianday(p.next_review_date))
                    ELSE 0 END as days_overdue
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id
             AND p.modality = 'reading' AND p.user_id = ?
        WHERE ci.status = 'drill_ready'
          AND ci.review_status = 'approved'
          AND ci.is_mined_out = 0
          AND (p.next_review_date IS NULL OR p.next_review_date <= ?)
        ORDER BY
            CASE WHEN p.next_review_date IS NULL THEN 1 ELSE 0 END,
            days_overdue DESC,
            ci.difficulty ASC
        LIMIT ?
    """, (today, user_id, today, limit)).fetchall()
    return [dict(r) for r in rows]


def _estimate_retention_gain(item: dict) -> float:
    """Estimate the retention gain from reviewing an item now.

    Items that are more overdue or have lower streaks benefit more.
    Returns a value in [0, 1].
    """
    days_overdue = item.get("days_overdue", 0) or 0
    half_life = item.get("half_life_days", 7.0) or 7.0
    streak = item.get("streak_correct", 0) or 0

    # Recall probability (exponential decay)
    if half_life > 0 and days_overdue > 0:
        recall_prob = math.exp(-0.693 * days_overdue / half_life)
    else:
        recall_prob = 0.9

    # Gain = how much recall improves from review
    # Maximum gain when recall has dropped significantly
    gain = max(0.0, 1.0 - recall_prob)

    # New items have fixed expected gain
    if item.get("is_new"):
        gain = 0.5  # Moderate — new items are uncertain

    # Reduce gain for well-streaked items (diminishing returns)
    if streak > 5:
        gain *= max(0.3, 1.0 - (streak - 5) * 0.1)

    return min(1.0, gain)


def _estimate_drill_time(item: dict) -> float:
    """Estimate time in minutes for a single drill on this item."""
    base_time = SECONDS_PER_DRILL / 60.0
    difficulty = item.get("difficulty", 0.5) or 0.5

    # Harder items take longer
    time_factor = 0.8 + 0.4 * difficulty
    return base_time * time_factor


# ── optimize_session ────────────────────────────────────────────────

def optimize_session(conn: sqlite3.Connection, user_id: int = 1,
                     time_budget_minutes: int = 15) -> dict:
    """Maximize expected retention gain per session minute.

    Decision variables:
    - Which items to include (from due items)
    - How many new items to introduce
    - Which drill types to use

    Constraints:
    - Total time <= time_budget_minutes
    - Cognitive load <= threshold (no more than 3 new items per 5 minutes)
    - At least 60% review, at most 40% new items

    Uses scipy.optimize.linprog if available, greedy heuristic fallback.
    """
    candidates = _get_candidate_items(conn, user_id)

    if not candidates:
        return {
            "items": [],
            "total_items": 0,
            "new_items": 0,
            "review_items": 0,
            "estimated_minutes": 0.0,
            "expected_retention_gain": 0.0,
            "time_budget_minutes": time_budget_minutes,
            "method": "empty",
            "constraints_satisfied": True,
        }

    # Annotate candidates with gain and time estimates
    for item in candidates:
        item["_retention_gain"] = _estimate_retention_gain(item)
        item["_drill_time_min"] = _estimate_drill_time(item)
        item["_gain_per_minute"] = (
            item["_retention_gain"] / max(item["_drill_time_min"], 0.01)
        )

    # Separate review and new items
    review_items = [i for i in candidates if not i.get("is_new")]
    new_items = [i for i in candidates if i.get("is_new")]

    # Sort by gain-per-minute descending
    review_items.sort(key=lambda x: x["_gain_per_minute"], reverse=True)
    new_items.sort(key=lambda x: x["_gain_per_minute"], reverse=True)

    # Try scipy optimization first
    try:
        result = _optimize_with_scipy(
            review_items, new_items, time_budget_minutes
        )
        if result is not None:
            return result
    except Exception as e:
        logger.debug("scipy optimization unavailable or failed: %s", e)

    # Greedy fallback
    return _optimize_greedy(review_items, new_items, time_budget_minutes)


def _optimize_with_scipy(review_items: list, new_items: list,
                         time_budget: float) -> dict | None:
    """Attempt LP optimization with scipy."""
    try:
        from scipy.optimize import linprog
    except ImportError:
        return None

    all_items = review_items + new_items
    n = len(all_items)
    if n == 0:
        return None

    # Objective: maximize total retention gain (minimize negative gain)
    c = [-item["_retention_gain"] for item in all_items]

    # Constraint 1: total time <= budget
    A_ub = [[item["_drill_time_min"] for item in all_items]]
    b_ub = [time_budget]

    # Constraint 2: new items <= MAX_NEW_FRACTION * total selected
    # Approximation: new_items <= MAX_NEW_FRACTION * n (linearized)
    new_constraint = [0.0] * n
    for i in range(len(review_items), n):
        new_constraint[i] = 1.0
    max_new = max(1, round(n * MAX_NEW_FRACTION))
    A_ub.append(new_constraint)
    b_ub.append(max_new)

    # Constraint 3: cognitive load — new items capped
    five_min_slots = max(1, int(time_budget / 5))
    max_new_cognitive = MAX_NEW_PER_5MIN * five_min_slots
    A_ub.append(new_constraint)
    b_ub.append(max_new_cognitive)

    # Bounds: 0 <= x_i <= 1 (relaxed LP)
    bounds = [(0, 1)] * n

    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')

    if not result.success:
        return None

    # Round to binary: select items with x > 0.5
    selected = []
    total_time = 0.0
    total_gain = 0.0
    n_new = 0
    n_review = 0

    # Sort by x value descending to pick best items
    indexed = sorted(enumerate(result.x), key=lambda x: x[1], reverse=True)

    for idx, x_val in indexed:
        if x_val < 0.3:
            continue
        item = all_items[idx]
        if total_time + item["_drill_time_min"] > time_budget:
            continue
        if item.get("is_new") and n_new >= max_new_cognitive:
            continue

        selected.append(item)
        total_time += item["_drill_time_min"]
        total_gain += item["_retention_gain"]
        if item.get("is_new"):
            n_new += 1
        else:
            n_review += 1

    # Verify review fraction
    total_selected = n_new + n_review
    if total_selected > 0 and n_review / total_selected < MIN_REVIEW_FRACTION:
        # Drop new items until constraint satisfied
        while n_new > 0 and total_selected > 0 and n_review / total_selected < MIN_REVIEW_FRACTION:
            for i in range(len(selected) - 1, -1, -1):
                if selected[i].get("is_new"):
                    total_time -= selected[i]["_drill_time_min"]
                    total_gain -= selected[i]["_retention_gain"]
                    selected.pop(i)
                    n_new -= 1
                    total_selected -= 1
                    break

    return {
        "items": [
            {"id": i["id"], "hanzi": i.get("hanzi", ""), "is_new": bool(i.get("is_new")),
             "retention_gain": round(i["_retention_gain"], 3),
             "drill_time_min": round(i["_drill_time_min"], 2)}
            for i in selected
        ],
        "total_items": len(selected),
        "new_items": n_new,
        "review_items": n_review,
        "estimated_minutes": round(total_time, 1),
        "expected_retention_gain": round(total_gain, 3),
        "time_budget_minutes": time_budget,
        "method": "scipy_linprog",
        "constraints_satisfied": True,
    }


def _optimize_greedy(review_items: list, new_items: list,
                     time_budget: float) -> dict:
    """Greedy heuristic: fill session with highest gain-per-minute items."""
    selected = []
    total_time = 0.0
    total_gain = 0.0
    n_new = 0
    n_review = 0

    five_min_slots = max(1, int(time_budget / 5))
    max_new_cognitive = MAX_NEW_PER_5MIN * five_min_slots
    max_total = max(1, round(time_budget * 60 / SECONDS_PER_DRILL))
    max_new_by_fraction = max(1, round(max_total * MAX_NEW_FRACTION))
    max_new = min(max_new_cognitive, max_new_by_fraction)

    # First pass: fill with review items (must be >= 60%)
    for item in review_items:
        if total_time + item["_drill_time_min"] > time_budget:
            continue
        selected.append(item)
        total_time += item["_drill_time_min"]
        total_gain += item["_retention_gain"]
        n_review += 1

    # Second pass: add new items within constraints
    for item in new_items:
        if total_time + item["_drill_time_min"] > time_budget:
            continue
        if n_new >= max_new:
            continue
        # Check review fraction constraint
        if (n_review / (n_review + n_new + 1)) < MIN_REVIEW_FRACTION:
            continue
        selected.append(item)
        total_time += item["_drill_time_min"]
        total_gain += item["_retention_gain"]
        n_new += 1

    return {
        "items": [
            {"id": i["id"], "hanzi": i.get("hanzi", ""), "is_new": bool(i.get("is_new")),
             "retention_gain": round(i["_retention_gain"], 3),
             "drill_time_min": round(i["_drill_time_min"], 2)}
            for i in selected
        ],
        "total_items": len(selected),
        "new_items": n_new,
        "review_items": n_review,
        "estimated_minutes": round(total_time, 1),
        "expected_retention_gain": round(total_gain, 3),
        "time_budget_minutes": time_budget,
        "method": "greedy",
        "constraints_satisfied": True,
    }


# ── decision_table ──────────────────────────────────────────────────

def decision_table(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Generate a decision table for session parameter selection.

    Dimensions:
    - Return probability (daily/sporadic/unknown)
    - Queue state (low/medium/high/overflowed)

    Output: optimal new_item_count for each cell.
    """
    # Determine current queue state
    due_count = db.get_items_due_count(conn, user_id=user_id)

    # Classify queue state thresholds
    queue_thresholds = {"low": 10, "medium": 25, "high": 50}

    # Get actual return pattern
    sessions = db.get_session_history(conn, limit=30, user_id=user_id)
    from ..diagnostics import compute_velocity
    velocity = compute_velocity(sessions)
    spw = velocity.get("sessions_per_week", 0)

    # Classify return probability
    if spw >= 4:
        actual_return = "daily"
    elif spw >= 1.5:
        actual_return = "sporadic"
    else:
        actual_return = "unknown"

    # Classify actual queue state
    if due_count <= queue_thresholds["low"]:
        actual_queue = "low"
    elif due_count <= queue_thresholds["medium"]:
        actual_queue = "medium"
    elif due_count <= queue_thresholds["high"]:
        actual_queue = "high"
    else:
        actual_queue = "overflowed"

    # Build the decision matrix
    # Each cell: optimal new_item_count based on the intersection
    matrix = {
        "daily": {
            "low": {"new_items": 5, "rationale": "Frequent visits, light queue — maximize breadth"},
            "medium": {"new_items": 3, "rationale": "Frequent visits, moderate queue — balanced approach"},
            "high": {"new_items": 1, "rationale": "Frequent visits, heavy queue — prioritize clearance"},
            "overflowed": {"new_items": 0, "rationale": "Frequent visits, overflowed — review only until queue stabilizes"},
        },
        "sporadic": {
            "low": {"new_items": 3, "rationale": "Irregular visits, light queue — moderate new items"},
            "medium": {"new_items": 2, "rationale": "Irregular visits, moderate queue — conservative growth"},
            "high": {"new_items": 0, "rationale": "Irregular visits, heavy queue — review only"},
            "overflowed": {"new_items": 0, "rationale": "Irregular visits, overflowed — review only, consider shorter sessions"},
        },
        "unknown": {
            "low": {"new_items": 2, "rationale": "Unknown pattern, light queue — cautious introduction"},
            "medium": {"new_items": 1, "rationale": "Unknown pattern, moderate queue — minimal new items"},
            "high": {"new_items": 0, "rationale": "Unknown pattern, heavy queue — review only"},
            "overflowed": {"new_items": 0, "rationale": "Unknown pattern, overflowed — review only"},
        },
    }

    # Find current recommendation
    current_cell = matrix[actual_return][actual_queue]

    return {
        "matrix": matrix,
        "current_state": {
            "return_probability": actual_return,
            "queue_state": actual_queue,
            "sessions_per_week": round(spw, 1),
            "due_count": due_count,
        },
        "recommendation": {
            "new_items": current_cell["new_items"],
            "rationale": current_cell["rationale"],
        },
        "queue_thresholds": queue_thresholds,
    }


# ── pareto_frontier ─────────────────────────────────────────────────

def pareto_frontier(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Multi-objective optimization: retention vs breadth vs session time.

    Generates candidate session configurations and filters to
    Pareto-optimal points (no point is dominated in all objectives).

    Returns list of Pareto-optimal points, each with:
    - retention_rate, breadth_coverage, session_minutes
    """
    # Get learner state
    from .sensitivity import _get_learner_state
    state = _get_learner_state(conn, user_id)

    candidates = _get_candidate_items(conn, user_id, limit=80)
    review_candidates = [i for i in candidates if not i.get("is_new")]
    new_candidates = [i for i in candidates if i.get("is_new")]

    # Annotate
    for item in candidates:
        item["_retention_gain"] = _estimate_retention_gain(item)
        item["_drill_time_min"] = _estimate_drill_time(item)

    # Generate candidate configurations
    # Vary: session time (5, 10, 15, 20, 25 min) x new items (0, 1, 2, 3, 5)
    time_options = [5, 10, 15, 20, 25]
    new_options = [0, 1, 2, 3, 5]

    points = []
    for time_budget in time_options:
        for n_new in new_options:
            # Build a session greedily
            selected_reviews = []
            selected_new = []
            total_time = 0.0
            total_gain = 0.0

            # Add review items
            for item in sorted(review_candidates,
                               key=lambda x: x["_retention_gain"], reverse=True):
                if total_time + item["_drill_time_min"] > time_budget:
                    break
                selected_reviews.append(item)
                total_time += item["_drill_time_min"]
                total_gain += item["_retention_gain"]

            # Add new items
            added_new = 0
            for item in sorted(new_candidates,
                               key=lambda x: x.get("hsk_level", 1)):
                if added_new >= n_new:
                    break
                if total_time + item["_drill_time_min"] > time_budget:
                    break
                selected_new.append(item)
                total_time += item["_drill_time_min"]
                total_gain += item["_retention_gain"]
                added_new += 1

            total_items = len(selected_reviews) + len(selected_new)
            if total_items == 0:
                continue

            # Compute objectives
            # 1. Retention: average expected gain from reviewing
            retention_score = total_gain / total_items if total_items > 0 else 0

            # 2. Breadth: fraction of new content (coverage expansion)
            breadth_score = added_new / max(total_items, 1)

            # 3. Time efficiency: gain per minute
            time_efficiency = total_gain / max(total_time, 0.1)

            points.append({
                "session_minutes": round(total_time, 1),
                "time_budget": time_budget,
                "total_items": total_items,
                "new_items": added_new,
                "review_items": len(selected_reviews),
                "retention_rate": round(retention_score, 3),
                "breadth_coverage": round(breadth_score, 3),
                "time_efficiency": round(time_efficiency, 3),
                "total_retention_gain": round(total_gain, 3),
            })

    # Filter to Pareto frontier
    # A point is Pareto-optimal if no other point dominates it in ALL objectives
    pareto = []
    objectives = ["retention_rate", "breadth_coverage", "time_efficiency"]

    for i, p in enumerate(points):
        dominated = False
        for j, q in enumerate(points):
            if i == j:
                continue
            # q dominates p if q is >= p in all objectives and > in at least one
            all_ge = all(q[o] >= p[o] for o in objectives)
            any_gt = any(q[o] > p[o] for o in objectives)
            if all_ge and any_gt:
                dominated = True
                break
        if not dominated:
            pareto.append(p)

    # Sort by retention descending
    pareto.sort(key=lambda x: x["retention_rate"], reverse=True)

    return {
        "pareto_points": pareto,
        "total_candidates_evaluated": len(points),
        "objectives": objectives,
        "current_state": {
            "items_seen": state["items_seen"],
            "items_mastered": state["items_mastered"],
            "due_count": state["due_count"],
            "avg_accuracy": round(state["avg_accuracy"], 3),
        },
    }
