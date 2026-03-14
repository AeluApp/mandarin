"""Sensitivity analysis — what-if parameter sweeps for scheduling decisions.

Varies key scheduling parameters and projects their impact on retention,
queue depth, and time-to-next-HSK-level. Each sweep generates 5-7 data
points across the parameter's valid range, suitable for charting.

Zero Claude tokens at runtime — all deterministic computation.
"""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date
from typing import Any, Dict, List

from .. import db
from ..config import (
    SECONDS_PER_DRILL,
    MAX_NEW_ITEM_RATIO,
    NEW_BUDGET_DEFAULT,
)

logger = logging.getLogger(__name__)


# ── Parameter ranges ────────────────────────────────────────────────

PARAMETER_SPECS = {
    "new_items_per_session": {
        "range": (0, 3, 5, 8, 10, 15, 20),
        "label": "New items per session",
        "unit": "items",
    },
    "session_length_minutes": {
        "range": (5, 8, 10, 15, 20, 25, 30),
        "label": "Session length",
        "unit": "minutes",
    },
    "review_threshold": {
        "range": (0.70, 0.75, 0.80, 0.85, 0.90, 0.95),
        "label": "Review recall threshold",
        "unit": "probability",
    },
    "sessions_per_week": {
        "range": (1, 2, 3, 4, 5, 6, 7),
        "label": "Sessions per week",
        "unit": "sessions/week",
    },
}


# ── Helpers: extract learner state from DB ──────────────────────────

def _get_learner_state(conn: sqlite3.Connection, user_id: int) -> dict:
    """Extract current learner metrics needed for projections."""
    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions") or 0

    # Queue depth: items due now
    due_count = db.get_items_due_count(conn, user_id=user_id)

    # Total items seen
    row = conn.execute("""
        SELECT COUNT(DISTINCT content_item_id) as seen,
               COUNT(DISTINCT CASE WHEN mastery_stage IN ('stable', 'durable')
                     THEN content_item_id END) as mastered
        FROM progress WHERE total_attempts > 0 AND user_id = ?
    """, (user_id,)).fetchone()
    items_seen = (row["seen"] or 0) if row else 0
    items_mastered = (row["mastered"] or 0) if row else 0

    # Average accuracy from recent sessions
    sessions = db.get_session_history(conn, limit=20, user_id=user_id)
    if sessions:
        total_correct = sum(s.get("items_correct", 0) for s in sessions)
        total_completed = sum(s.get("items_completed", 0) for s in sessions)
        avg_accuracy = total_correct / total_completed if total_completed > 0 else 0.75
        avg_items_per_session = total_completed / len(sessions) if sessions else 10
    else:
        avg_accuracy = 0.75
        avg_items_per_session = 10

    # Current sessions per week from velocity
    from ..diagnostics import compute_velocity
    velocity = compute_velocity(sessions)
    current_spw = velocity.get("sessions_per_week", 3.0)

    # Current HSK level (use reading as proxy)
    from ..diagnostics import _compute_modality_stats, _estimate_levels
    modality_stats = _compute_modality_stats(conn, user_id=user_id)
    estimated_levels = _estimate_levels(conn, modality_stats, user_id=user_id)
    reading_level = estimated_levels.get("reading", {}).get("level", 1.0)

    # Items available for new introduction
    new_available = db.get_new_items_available(conn, user_id=user_id)

    # Average half-life of items in progress
    hl_row = conn.execute("""
        SELECT AVG(half_life_days) as avg_hl
        FROM progress
        WHERE half_life_days IS NOT NULL AND half_life_days > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    avg_half_life = (hl_row["avg_hl"] or 7.0) if hl_row else 7.0

    return {
        "total_sessions": total_sessions,
        "due_count": due_count,
        "items_seen": items_seen,
        "items_mastered": items_mastered,
        "avg_accuracy": avg_accuracy,
        "avg_items_per_session": avg_items_per_session,
        "current_spw": current_spw,
        "reading_level": reading_level,
        "new_available": new_available,
        "avg_half_life": avg_half_life,
    }


# ── Projection models ──────────────────────────────────────────────

def _project_retention(state: dict, new_items: int, review_capacity: int,
                       review_threshold: float) -> float:
    """Project retention rate given scheduling parameters.

    Simple steady-state model: retention degrades when review capacity
    can't keep up with items entering the review queue.
    """
    items_in_system = state["items_seen"] + new_items
    if items_in_system == 0:
        return 1.0

    # Each item needs review every avg_half_life days at the threshold
    # Lower threshold = less frequent reviews needed
    review_demand_per_day = items_in_system / max(state["avg_half_life"], 1.0)
    reviews_per_day = review_capacity / max(state["avg_half_life"], 1.0)

    # Utilization: if demand > capacity, some items lapse
    utilization = review_demand_per_day / max(reviews_per_day, 0.01)
    if utilization <= 1.0:
        # Under-utilized: retention is high, bounded by threshold
        return min(0.99, review_threshold + (1.0 - review_threshold) * (1.0 - utilization))
    else:
        # Over-utilized: retention degrades proportionally
        overflow = utilization - 1.0
        return max(0.3, review_threshold * math.exp(-overflow))


def _project_queue_depth(state: dict, new_items_per_session: int,
                         reviews_per_session: int, spw: float) -> int:
    """Project steady-state queue depth.

    Queue grows by new_items * spw per week, shrinks by reviews * spw.
    Items re-enter queue after avg_half_life days.
    """
    items_entering_per_week = new_items_per_session * spw
    items_reviewed_per_week = reviews_per_session * spw
    # Re-entries: items come back for review after half-life
    items_in_system = state["items_seen"]
    reentry_per_week = items_in_system / max(state["avg_half_life"], 1.0) * 7.0

    total_arrivals = items_entering_per_week + reentry_per_week
    net_growth = total_arrivals - items_reviewed_per_week

    # Steady state: queue = current_due + net_growth * weeks until balance
    if net_growth <= 0:
        # Queue is draining
        return max(0, state["due_count"] + int(net_growth))
    else:
        # Queue growing — project 4 weeks out
        return state["due_count"] + int(net_growth * 4)


def _project_time_to_next_hsk(state: dict, mastery_rate: float,
                               spw: float) -> float:
    """Project weeks to next HSK level given mastery rate and pace.

    Returns weeks (float). Returns float('inf') if unreachable.
    """
    from ..diagnostics import HSK_CUMULATIVE
    current_level = state["reading_level"]
    next_level = math.ceil(current_level)
    if next_level <= current_level:
        next_level = int(current_level) + 1
    next_level = min(9, next_level)

    target_vocab = int(HSK_CUMULATIVE.get(next_level, next_level * 500) * 0.8)
    vocab_gap = max(0, target_vocab - state["items_mastered"])
    if vocab_gap == 0:
        return 0.0

    effective_rate = max(mastery_rate, 0.5)
    sessions_needed = vocab_gap / effective_rate
    weeks = sessions_needed / max(spw, 0.5)
    return min(weeks, 520.0)  # Cap at 10 years


# ── Main API ────────────────────────────────────────────────────────

def sensitivity_analysis(conn: sqlite3.Connection, user_id: int = 1,
                         parameters: dict | None = None) -> dict:
    """Vary parameters and compute impact on retention/queue depth/HSK time.

    Parameters dict can include:
    - new_items_per_session: int (vary from 0 to 20)
    - session_length_minutes: int (vary from 5 to 30)
    - review_threshold: float (vary from 0.7 to 0.95)
    - sessions_per_week: int (vary from 1 to 7)

    If parameters is None, sweeps all four parameters.

    Returns dict with parameter sweeps and their impacts, each containing
    arrays suitable for charting.
    """
    state = _get_learner_state(conn, user_id)

    # Default baseline values
    baseline = {
        "new_items_per_session": NEW_BUDGET_DEFAULT,
        "session_length_minutes": round(state["avg_items_per_session"] * SECONDS_PER_DRILL / 60, 1),
        "review_threshold": 0.85,
        "sessions_per_week": round(state["current_spw"], 1),
    }

    param_names = list((parameters or {}).keys()) if parameters else list(PARAMETER_SPECS.keys())
    if not param_names:
        param_names = list(PARAMETER_SPECS.keys())

    results = {}
    for param_name in param_names:
        spec = PARAMETER_SPECS.get(param_name)
        if spec is None:
            continue

        sweep_values = list(spec["range"])
        retention_points = []
        queue_depth_points = []
        hsk_time_points = []

        for val in sweep_values:
            # Derive scheduling parameters at this sweep point
            if param_name == "new_items_per_session":
                new_items = val
                session_items = max(new_items + 4, round(baseline["session_length_minutes"] * 60 / SECONDS_PER_DRILL))
                review_items = max(0, session_items - new_items)
                spw = baseline["sessions_per_week"]
                threshold = baseline["review_threshold"]
            elif param_name == "session_length_minutes":
                session_items = max(1, round(val * 60 / SECONDS_PER_DRILL))
                new_items = min(baseline["new_items_per_session"],
                                round(session_items * MAX_NEW_ITEM_RATIO))
                review_items = max(0, session_items - new_items)
                spw = baseline["sessions_per_week"]
                threshold = baseline["review_threshold"]
            elif param_name == "review_threshold":
                threshold = val
                session_items = round(baseline["session_length_minutes"] * 60 / SECONDS_PER_DRILL)
                new_items = baseline["new_items_per_session"]
                review_items = max(0, session_items - new_items)
                spw = baseline["sessions_per_week"]
            elif param_name == "sessions_per_week":
                spw = val
                session_items = round(baseline["session_length_minutes"] * 60 / SECONDS_PER_DRILL)
                new_items = baseline["new_items_per_session"]
                review_items = max(0, session_items - new_items)
                threshold = baseline["review_threshold"]
            else:
                continue

            # Project outcomes
            retention = _project_retention(state, new_items, review_items, threshold)
            queue_depth = _project_queue_depth(state, new_items, review_items, spw)
            hsk_weeks = _project_time_to_next_hsk(
                state, mastery_rate=new_items * 0.7, spw=spw
            )

            retention_points.append(round(retention, 3))
            queue_depth_points.append(max(0, queue_depth))
            hsk_time_points.append(round(hsk_weeks, 1))

        results[param_name] = {
            "label": spec["label"],
            "unit": spec["unit"],
            "sweep_values": sweep_values,
            "baseline_value": baseline.get(param_name),
            "retention_rate": retention_points,
            "queue_depth": queue_depth_points,
            "weeks_to_next_hsk": hsk_time_points,
        }

    return {
        "user_id": user_id,
        "current_state": {
            "total_sessions": state["total_sessions"],
            "items_seen": state["items_seen"],
            "items_mastered": state["items_mastered"],
            "due_count": state["due_count"],
            "avg_accuracy": round(state["avg_accuracy"], 3),
            "current_hsk_level": round(state["reading_level"], 1),
        },
        "baseline": baseline,
        "sweeps": results,
    }
