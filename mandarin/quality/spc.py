"""Statistical Process Control — Shewhart control charts with Western Electric rules."""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def compute_control_limits(data_points: list[float], chart_type: str = "xbar") -> dict:
    """Compute UCL, CL, LCL for a Shewhart control chart (3-sigma).

    Returns: {"ucl": float, "cl": float, "lcl": float, "sigma": float}
    """
    if not data_points or len(data_points) < 2:
        return {"ucl": 100.0, "cl": 0.0, "lcl": 0.0, "sigma": 0.0}

    n = len(data_points)
    cl = sum(data_points) / n
    variance = sum((x - cl) ** 2 for x in data_points) / (n - 1)
    sigma = math.sqrt(variance) if variance > 0 else 0.001

    return {
        "ucl": cl + 3 * sigma,
        "cl": cl,
        "lcl": cl - 3 * sigma,
        "sigma": sigma,
    }


def detect_out_of_control(data_points: list[float], limits: dict) -> list[dict]:
    """Apply Western Electric rules to detect out-of-control points.

    Rules:
    1. Any single point > 3σ from center
    2. 2 of 3 consecutive points > 2σ from center (same side)
    3. 4 of 5 consecutive points > 1σ from center (same side)
    4. 8 consecutive points on same side of center line

    Returns: [{index, value, rule, description}]
    """
    violations = []
    if not data_points or not limits:
        return violations

    cl = limits["cl"]
    sigma = limits["sigma"]
    if sigma <= 0:
        return violations

    n = len(data_points)

    for i, x in enumerate(data_points):
        z = (x - cl) / sigma

        # Rule 1: single point > 3σ
        if abs(z) > 3:
            violations.append({"index": i, "value": x, "rule": 1,
                             "description": f"Point {i} at {z:.1f}σ exceeds 3σ limit"})

        # Rule 2: 2 of 3 consecutive > 2σ (same side)
        if i >= 2:
            window = [(data_points[j] - cl) / sigma for j in range(i-2, i+1)]
            above = sum(1 for w in window if w > 2)
            below = sum(1 for w in window if w < -2)
            if above >= 2:
                violations.append({"index": i, "value": x, "rule": 2,
                                 "description": f"2 of 3 points above 2σ at index {i}"})
            if below >= 2:
                violations.append({"index": i, "value": x, "rule": 2,
                                 "description": f"2 of 3 points below 2σ at index {i}"})

        # Rule 3: 4 of 5 consecutive > 1σ (same side)
        if i >= 4:
            window = [(data_points[j] - cl) / sigma for j in range(i-4, i+1)]
            above = sum(1 for w in window if w > 1)
            below = sum(1 for w in window if w < -1)
            if above >= 4:
                violations.append({"index": i, "value": x, "rule": 3,
                                 "description": f"4 of 5 points above 1σ at index {i}"})
            if below >= 4:
                violations.append({"index": i, "value": x, "rule": 3,
                                 "description": f"4 of 5 points below 1σ at index {i}"})

        # Rule 4: 8 consecutive on same side
        if i >= 7:
            window = [data_points[j] - cl for j in range(i-7, i+1)]
            if all(w > 0 for w in window):
                violations.append({"index": i, "value": x, "rule": 4,
                                 "description": f"8 consecutive points above center at index {i}"})
            if all(w < 0 for w in window):
                violations.append({"index": i, "value": x, "rule": 4,
                                 "description": f"8 consecutive points below center at index {i}"})

    # Deduplicate by index
    seen = set()
    unique = []
    for v in violations:
        if v["index"] not in seen:
            seen.add(v["index"])
            unique.append(v)
    return unique


def get_spc_charts(conn) -> dict:
    """Generate SPC chart data for key quality indicators."""
    charts = {}

    # 1. Daily session completion rate
    try:
        rows = conn.execute("""
            SELECT date(started_at) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed
            FROM session_log
            WHERE started_at >= datetime('now', '-30 days')
            GROUP BY date(started_at)
            ORDER BY day
        """).fetchall()
        if rows:
            data = [round(r["completed"] / max(1, r["total"]) * 100, 1) for r in rows]
            labels = [r["day"] for r in rows]
            limits = compute_control_limits(data)
            ooc = detect_out_of_control(data, limits)
            charts["session_completion"] = {
                "title": "Session Completion Rate (%)",
                "data": data, "labels": labels,
                "limits": limits, "violations": ooc,
            }
    except Exception:
        pass

    # 2. Daily average accuracy
    try:
        rows = conn.execute("""
            SELECT date(reviewed_at) as day,
                   AVG(CASE WHEN rating >= 3 THEN 1.0 ELSE 0.0 END) * 100 as accuracy
            FROM review_event
            WHERE reviewed_at >= datetime('now', '-30 days')
            GROUP BY date(reviewed_at)
            ORDER BY day
        """).fetchall()
        if rows:
            data = [round(r["accuracy"], 1) for r in rows]
            labels = [r["day"] for r in rows]
            limits = compute_control_limits(data)
            ooc = detect_out_of_control(data, limits)
            charts["accuracy"] = {
                "title": "Daily Average Accuracy (%)",
                "data": data, "labels": labels,
                "limits": limits, "violations": ooc,
            }
    except Exception:
        pass

    # 3. Content generation rejection rate
    try:
        rows = conn.execute("""
            SELECT date(created_at) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
            FROM pi_ai_review_queue
            WHERE created_at >= datetime('now', '-30 days')
            GROUP BY date(created_at)
            ORDER BY day
        """).fetchall()
        if rows:
            data = [round(r["rejected"] / max(1, r["total"]) * 100, 1) for r in rows]
            labels = [r["day"] for r in rows]
            limits = compute_control_limits(data)
            ooc = detect_out_of_control(data, limits)
            charts["rejection_rate"] = {
                "title": "Content Rejection Rate (%)",
                "data": data, "labels": labels,
                "limits": limits, "violations": ooc,
            }
    except Exception:
        pass

    # 4. LLM latency P95
    try:
        rows = conn.execute("""
            SELECT date(occurred_at) as day,
                   MAX(generation_time_ms) as p95_ms
            FROM pi_ai_generation_log
            WHERE occurred_at >= datetime('now', '-30 days')
            AND success = 1
            GROUP BY date(occurred_at)
            ORDER BY day
        """).fetchall()
        if rows:
            data = [r["p95_ms"] or 0 for r in rows]
            labels = [r["day"] for r in rows]
            limits = compute_control_limits(data)
            ooc = detect_out_of_control(data, limits)
            charts["llm_latency"] = {
                "title": "LLM Latency P95 (ms)",
                "data": data, "labels": labels,
                "limits": limits, "violations": ooc,
            }
    except Exception:
        pass

    return charts


# ---------------------------------------------------------------------------
# Backward-compatible aliases used by quality_scheduler, admin_routes, and
# methodology modules that import the legacy API.
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

_D2 = 1.128


def collect_observations(conn, chart_type: str, days: int = 30) -> List[float]:
    """Collect daily observations for the given chart type (legacy API)."""
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
    """Calculate control limits for an individuals (I-MR) chart (legacy API)."""
    if not values:
        return {
            "center_line": 0.0, "ucl": 0.0, "lcl": 0.0,
            "values": [], "subgroup_size": subgroup_size,
        }

    n = len(values)
    mean = sum(values) / n

    if n < 2:
        return {
            "center_line": round(mean, 6), "ucl": round(mean, 6),
            "lcl": round(mean, 6), "values": values, "subgroup_size": subgroup_size,
        }

    mrs = [abs(values[i] - values[i - 1]) for i in range(1, n)]
    mr_bar = sum(mrs) / len(mrs)
    sigma_hat = mr_bar / _D2

    ucl = mean + 3 * sigma_hat
    lcl = max(0.0, mean - 3 * sigma_hat)

    return {
        "center_line": round(mean, 6), "ucl": round(ucl, 6),
        "lcl": round(lcl, 6), "values": values, "subgroup_size": subgroup_size,
    }


def _legacy_detect_ooc(
    values: List[float], center_line: float, ucl: float, lcl: float,
) -> List[Dict[str, Any]]:
    """Legacy out-of-control detection (rules 1-4 with original signatures)."""
    if len(values) < 2:
        return []

    violations: List[Dict[str, Any]] = []
    sigma = (ucl - center_line) / 3.0 if ucl != center_line else 0.0

    for i, v in enumerate(values):
        if v > ucl or v < lcl:
            violations.append({
                "index": i, "value": round(v, 6), "rule": 1,
                "description": f"Point beyond control limits ({v:.4f})",
            })

    if len(values) >= 7:
        inc_run = 1
        dec_run = 1
        for i in range(1, len(values)):
            if values[i] > values[i - 1]:
                inc_run += 1; dec_run = 1
            elif values[i] < values[i - 1]:
                dec_run += 1; inc_run = 1
            else:
                inc_run = 1; dec_run = 1
            if inc_run >= 7:
                violations.append({"index": i, "value": round(values[i], 6), "rule": 2,
                                   "description": f"Trend: {inc_run} consecutive increasing points"})
            if dec_run >= 7:
                violations.append({"index": i, "value": round(values[i], 6), "rule": 2,
                                   "description": f"Trend: {dec_run} consecutive decreasing points"})

    if len(values) >= 8:
        run = 1
        above = values[0] > center_line
        for i in range(1, len(values)):
            current_above = values[i] > center_line
            if current_above == above and values[i] != center_line:
                run += 1
            else:
                run = 1; above = current_above
            if run >= 8:
                side = "above" if above else "below"
                violations.append({"index": i, "value": round(values[i], 6), "rule": 3,
                                   "description": f"Shift: {run} consecutive points {side} center line"})

    if sigma > 0 and len(values) >= 3:
        two_sigma_upper = center_line + 2 * sigma
        two_sigma_lower = center_line - 2 * sigma
        for i in range(2, len(values)):
            window = values[i - 2: i + 1]
            above_2s = sum(1 for v in window if v > two_sigma_upper)
            below_2s = sum(1 for v in window if v < two_sigma_lower)
            if above_2s >= 2:
                violations.append({"index": i, "value": round(values[i], 6), "rule": 4,
                                   "description": "2 of 3 points beyond 2-sigma (upper)"})
            if below_2s >= 2:
                violations.append({"index": i, "value": round(values[i], 6), "rule": 4,
                                   "description": "2 of 3 points beyond 2-sigma (lower)"})

    return violations


def get_spc_chart_data(conn, chart_type: str, days: int = 30) -> Dict[str, Any]:
    """Full SPC chart data for a given metric (legacy API)."""
    observations = collect_observations(conn, chart_type, days)
    limits = calculate_control_limits(observations)
    violations = _legacy_detect_ooc(
        observations, limits["center_line"], limits["ucl"], limits["lcl"],
    )
    status = "out_of_control" if violations else "in_control"
    return {
        "chart_type": chart_type, "observations": observations,
        "control_limits": limits, "violations": violations, "status": status,
    }


def compute_spc_chart(conn, chart_type: str, days: int = 30) -> Dict[str, Any]:
    """Alias for get_spc_chart_data (legacy API)."""
    result = get_spc_chart_data(conn, chart_type, days)
    result["out_of_control"] = result["status"] == "out_of_control"
    return result


def observe(conn, chart_type: str, days: int = 30) -> Optional[float]:
    """Return the latest observation value for chart_type (legacy API)."""
    observations = collect_observations(conn, chart_type, days)
    return observations[-1] if observations else None
