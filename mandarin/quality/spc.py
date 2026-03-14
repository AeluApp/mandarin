"""Statistical Process Control — control charts and out-of-control detection."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# d2 constant for moving range with subgroup size n=2
_D2 = 1.128


def collect_observations(conn, chart_type: str, days: int = 30) -> List[float]:
    """Collect daily observations for the given chart type.

    chart_type:
      'drill_accuracy'      — daily accuracy from session_log
      'response_time'       — daily avg response_ms from review_event
      'session_completion'  — daily completion rate from session_log

    Returns list of float values, one per day with data, oldest first.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if chart_type == "drill_accuracy":
        rows = conn.execute(
            """
            SELECT DATE(started_at) AS day,
                   SUM(items_correct) AS correct,
                   SUM(items_completed) AS completed
            FROM session_log
            WHERE started_at >= ? AND items_completed > 0
            GROUP BY DATE(started_at)
            ORDER BY day
            """,
            (cutoff,),
        ).fetchall()
        values = []
        for r in rows:
            completed = (r["completed"] or 0)
            correct = (r["correct"] or 0)
            if completed > 0:
                values.append(correct / completed)
        return values

    elif chart_type == "response_time":
        rows = conn.execute(
            """
            SELECT DATE(created_at) AS day,
                   AVG(response_ms) AS avg_ms
            FROM review_event
            WHERE created_at >= ? AND response_ms IS NOT NULL
            GROUP BY DATE(created_at)
            ORDER BY day
            """,
            (cutoff,),
        ).fetchall()
        return [float(r["avg_ms"]) for r in rows if r["avg_ms"] is not None]

    elif chart_type == "session_completion":
        rows = conn.execute(
            """
            SELECT DATE(started_at) AS day,
                   SUM(items_completed) AS completed,
                   SUM(items_planned) AS planned
            FROM session_log
            WHERE started_at >= ? AND items_planned > 0
            GROUP BY DATE(started_at)
            ORDER BY day
            """,
            (cutoff,),
        ).fetchall()
        values = []
        for r in rows:
            planned = (r["planned"] or 0)
            completed = (r["completed"] or 0)
            if planned > 0:
                values.append(min(completed / planned, 1.0))
        return values

    else:
        logger.warning("Unknown chart_type: %s", chart_type)
        return []


def calculate_control_limits(
    values: List[float], subgroup_size: int = 1
) -> Dict[str, Any]:
    """Calculate control limits for an individuals (I-MR) chart.

    Uses the moving range method: sigma_hat = MR_bar / d2.
    UCL = mean + 3*sigma_hat, LCL = max(0, mean - 3*sigma_hat).
    """
    if not values:
        return {
            "center_line": 0.0,
            "ucl": 0.0,
            "lcl": 0.0,
            "values": [],
            "subgroup_size": subgroup_size,
        }

    n = len(values)
    mean = sum(values) / n

    if n < 2:
        return {
            "center_line": round(mean, 6),
            "ucl": round(mean, 6),
            "lcl": round(mean, 6),
            "values": values,
            "subgroup_size": subgroup_size,
        }

    # Moving ranges
    mrs = [abs(values[i] - values[i - 1]) for i in range(1, n)]
    mr_bar = sum(mrs) / len(mrs)
    sigma_hat = mr_bar / _D2

    ucl = mean + 3 * sigma_hat
    lcl = max(0.0, mean - 3 * sigma_hat)

    return {
        "center_line": round(mean, 6),
        "ucl": round(ucl, 6),
        "lcl": round(lcl, 6),
        "values": values,
        "subgroup_size": subgroup_size,
    }


def detect_out_of_control(
    values: List[float],
    center_line: float,
    ucl: float,
    lcl: float,
) -> List[Dict[str, Any]]:
    """Detect out-of-control points using Western Electric rules.

    Rules:
      1. Point beyond 3-sigma (UCL/LCL)
      2. 7+ consecutive points increasing or decreasing (trend)
      3. 8+ consecutive points on same side of center line (shift)
      4. 2 of 3 consecutive points beyond 2-sigma on same side
    """
    if len(values) < 2:
        return []

    violations: List[Dict[str, Any]] = []
    sigma = (ucl - center_line) / 3.0 if ucl != center_line else 0.0

    # Rule 1: Beyond 3-sigma
    for i, v in enumerate(values):
        if v > ucl or v < lcl:
            violations.append({
                "index": i,
                "value": round(v, 6),
                "rule": 1,
                "description": f"Point beyond control limits ({v:.4f})",
            })

    # Rule 2: 7+ consecutive increasing or decreasing
    if len(values) >= 7:
        inc_run = 1
        dec_run = 1
        for i in range(1, len(values)):
            if values[i] > values[i - 1]:
                inc_run += 1
                dec_run = 1
            elif values[i] < values[i - 1]:
                dec_run += 1
                inc_run = 1
            else:
                inc_run = 1
                dec_run = 1

            if inc_run >= 7:
                violations.append({
                    "index": i,
                    "value": round(values[i], 6),
                    "rule": 2,
                    "description": f"Trend: {inc_run} consecutive increasing points",
                })
            if dec_run >= 7:
                violations.append({
                    "index": i,
                    "value": round(values[i], 6),
                    "rule": 2,
                    "description": f"Trend: {dec_run} consecutive decreasing points",
                })

    # Rule 3: 8+ consecutive on same side of center
    if len(values) >= 8:
        run = 1
        above = values[0] > center_line
        for i in range(1, len(values)):
            current_above = values[i] > center_line
            if current_above == above and values[i] != center_line:
                run += 1
            else:
                run = 1
                above = current_above

            if run >= 8:
                side = "above" if above else "below"
                violations.append({
                    "index": i,
                    "value": round(values[i], 6),
                    "rule": 3,
                    "description": f"Shift: {run} consecutive points {side} center line",
                })

    # Rule 4: 2 of 3 beyond 2-sigma on same side
    if sigma > 0 and len(values) >= 3:
        two_sigma_upper = center_line + 2 * sigma
        two_sigma_lower = center_line - 2 * sigma
        for i in range(2, len(values)):
            window = values[i - 2 : i + 1]
            above_2s = sum(1 for v in window if v > two_sigma_upper)
            below_2s = sum(1 for v in window if v < two_sigma_lower)
            if above_2s >= 2:
                violations.append({
                    "index": i,
                    "value": round(values[i], 6),
                    "rule": 4,
                    "description": "2 of 3 points beyond 2-sigma (upper)",
                })
            if below_2s >= 2:
                violations.append({
                    "index": i,
                    "value": round(values[i], 6),
                    "rule": 4,
                    "description": "2 of 3 points beyond 2-sigma (lower)",
                })

    return violations


def get_spc_chart_data(
    conn, chart_type: str, days: int = 30
) -> Dict[str, Any]:
    """Full SPC chart data for a given metric.

    Returns chart_type, observations, control_limits, violations, status.
    """
    observations = collect_observations(conn, chart_type, days)
    limits = calculate_control_limits(observations)
    violations = detect_out_of_control(
        observations,
        limits["center_line"],
        limits["ucl"],
        limits["lcl"],
    )
    status = "out_of_control" if violations else "in_control"

    return {
        "chart_type": chart_type,
        "observations": observations,
        "control_limits": limits,
        "violations": violations,
        "status": status,
    }
