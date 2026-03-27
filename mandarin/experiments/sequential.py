"""Sequential testing — O'Brien-Fleming alpha spending with maturation awareness.

Allows ethical early stopping of experiments without inflating the false
positive rate.  Key improvement over the prior implementation: the information
fraction is based on *mature* observations (users whose outcome window has
closed), not raw assignment count.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3

logger = logging.getLogger(__name__)


def sequential_test(
    conn: sqlite3.Connection,
    experiment_name: str,
    alpha: float = 0.05,
) -> dict:
    """Run a sequential test using O'Brien-Fleming spending function.

    Returns ``{can_conclude, adjusted_alpha, current_p, information_fraction,
    recommendation, mature_n, planned_n}``.

    Recommendations:
    - ``continue``: keep collecting data
    - ``stop_winner``: significant result, conclude
    - ``stop_futility``: full sample reached, no effect — conclude as null
    - ``insufficient_data``: not enough data for any decision
    """
    try:
        exp = conn.execute(
            "SELECT id, variants, min_sample_size, outcome_window_days FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {"can_conclude": False, "recommendation": "insufficient_data"}

    if not exp:
        return {"can_conclude": False, "recommendation": "insufficient_data"}

    experiment_id = exp["id"]
    variant_names = json.loads(exp["variants"])
    planned_n = (exp["min_sample_size"] or 100) * len(variant_names)
    outcome_window = exp["outcome_window_days"] if exp["outcome_window_days"] else 7

    # Current total assignments
    total_assigned = _count_assignments(conn, experiment_id)

    if total_assigned == 0 or len(variant_names) < 2:
        return {
            "can_conclude": False,
            "adjusted_alpha": 0.0,
            "current_p": None,
            "information_fraction": 0.0,
            "recommendation": "insufficient_data",
            "mature_n": 0,
            "planned_n": planned_n,
        }

    # Mature observations: users assigned at least outcome_window days ago
    mature_n = _count_mature_assignments(conn, experiment_id, outcome_window)

    # Information fraction based on mature observations
    information_fraction = min(1.0, mature_n / planned_n) if planned_n > 0 else 0.0

    if information_fraction < 0.1:
        return {
            "can_conclude": False,
            "adjusted_alpha": 0.0,
            "current_p": None,
            "information_fraction": round(information_fraction, 3),
            "recommendation": "insufficient_data",
            "mature_n": mature_n,
            "planned_n": planned_n,
        }

    adjusted_alpha = _obrien_fleming_boundary(alpha, information_fraction)

    # Get current p-value from analysis
    from .analysis import get_experiment_results
    results = get_experiment_results(conn, experiment_name)
    current_p = results.get("p_value")
    min_met = results.get("min_sample_met", False)

    can_conclude = current_p is not None and current_p < adjusted_alpha

    if current_p is None:
        recommendation = "insufficient_data"
    elif can_conclude and min_met:
        recommendation = "stop_winner"
    elif information_fraction >= 1.0 and (current_p is None or current_p > 0.2):
        recommendation = "stop_futility"
    else:
        recommendation = "continue"

    return {
        "can_conclude": can_conclude,
        "adjusted_alpha": round(adjusted_alpha, 6),
        "current_p": current_p,
        "information_fraction": round(information_fraction, 3),
        "recommendation": recommendation,
        "mature_n": mature_n,
        "planned_n": planned_n,
    }


def _obrien_fleming_boundary(alpha: float, information_fraction: float) -> float:
    """O'Brien-Fleming spending function.

    Returns the adjusted alpha at this information fraction.  Early looks
    require very strong evidence; later looks are more permissive.
    """
    if information_fraction <= 0 or information_fraction > 1:
        return 0.0

    z_alpha = _inv_normal(1 - alpha / 2)
    z_boundary = z_alpha / math.sqrt(information_fraction)
    adjusted_alpha = 2 * (1 - 0.5 * (1 + math.erf(z_boundary / math.sqrt(2))))
    return adjusted_alpha


def _inv_normal(p: float) -> float:
    """Approximate inverse normal CDF (Abramowitz & Stegun)."""
    if p <= 0 or p >= 1:
        return 0.0
    if p < 0.5:
        return -_inv_normal(1 - p)
    t = math.sqrt(-2 * math.log(1 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return t - (c0 + c1 * t + c2 * t**2) / (1 + d1 * t + d2 * t**2 + d3 * t**3)


def _count_assignments(conn: sqlite3.Connection, experiment_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) as n FROM experiment_assignment WHERE experiment_id = ?",
        (experiment_id,),
    ).fetchone()
    return row["n"] if row else 0


def _count_mature_assignments(
    conn: sqlite3.Connection, experiment_id: int, window_days: int,
) -> int:
    """Count assignments made at least *window_days* ago."""
    try:
        sql = f"""SELECT COUNT(*) as n FROM experiment_assignment
                WHERE experiment_id = ?
                  AND assigned_at <= datetime('now', '-{window_days} days')"""
        row = conn.execute(sql, (experiment_id,)).fetchone()
        return row["n"] if row else 0
    except sqlite3.OperationalError:
        # Fallback: count all assignments
        return _count_assignments(conn, experiment_id)
