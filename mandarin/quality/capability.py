"""Process capability analysis — Cp, Cpk for learning system metrics."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def calculate_cpk(
    values: list[float],
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Calculate process capability indices Cp and Cpk.

    Cp  = (USL - LSL) / (6 * sigma)
    Cpu = (USL - mean) / (3 * sigma)
    Cpl = (mean - LSL) / (3 * sigma)
    Cpk = min(Cpu, Cpl)  — or whichever is defined.

    At least one of lsl/usl must be provided.
    Returns dict with mean, std, cp, cpk, cpu, cpl, n, lsl, usl.
    """
    result: dict[str, Any] = {
        "mean": None,
        "std": None,
        "cp": None,
        "cpk": None,
        "cpu": None,
        "cpl": None,
        "n": 0,
        "lsl": lsl,
        "usl": usl,
    }

    if not values or (lsl is None and usl is None):
        return result

    n = len(values)
    result["n"] = n

    if n < 2:
        mean = values[0] if values else 0.0
        result["mean"] = round(mean, 6)
        result["std"] = 0.0
        return result

    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0

    result["mean"] = round(mean, 6)
    result["std"] = round(std, 6)

    if std == 0:
        # Perfect process — capability is infinite in theory.
        # Return large sentinel values.
        if usl is not None and mean <= usl:
            result["cpu"] = 99.0
        elif usl is not None:
            result["cpu"] = -99.0

        if lsl is not None and mean >= lsl:
            result["cpl"] = 99.0
        elif lsl is not None:
            result["cpl"] = -99.0

        if lsl is not None and usl is not None:
            result["cp"] = 99.0

        caps = [v for v in [result["cpu"], result["cpl"]] if v is not None]
        result["cpk"] = min(caps) if caps else None
        return result

    if usl is not None:
        cpu = (usl - mean) / (3 * std)
        result["cpu"] = round(cpu, 4)

    if lsl is not None:
        cpl = (mean - lsl) / (3 * std)
        result["cpl"] = round(cpl, 4)

    if lsl is not None and usl is not None:
        cp = (usl - lsl) / (6 * std)
        result["cp"] = round(cp, 4)

    caps = [v for v in [result["cpu"], result["cpl"]] if v is not None]
    result["cpk"] = round(min(caps), 4) if caps else None

    return result


def assess_api_latency(conn, days: int = 7) -> dict[str, Any]:
    """Cpk analysis for response_ms with USL=500ms.

    Lower is better — we only care about an upper spec limit.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT response_ms FROM review_event
        WHERE created_at >= ? AND response_ms IS NOT NULL
        """,
        (cutoff,),
    ).fetchall()

    values = [float(r["response_ms"]) for r in rows]
    result = calculate_cpk(values, usl=500.0)
    result["metric"] = "api_latency_ms"
    result["spec"] = "USL=500ms"
    result["days"] = days
    return result


def assess_session_load(conn, days: int = 7) -> dict[str, Any]:
    """Cpk analysis for session duration with USL=1800s (30 min)."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT duration_seconds FROM session_log
        WHERE started_at >= ? AND duration_seconds IS NOT NULL
        """,
        (cutoff,),
    ).fetchall()

    values = [float(r["duration_seconds"]) for r in rows]
    result = calculate_cpk(values, usl=1800.0)
    result["metric"] = "session_duration_s"
    result["spec"] = "USL=1800s"
    result["days"] = days
    return result


def assess_drill_accuracy(conn, days: int = 7) -> dict[str, Any]:
    """Cpk analysis for drill accuracy with LSL=0.6 (60% minimum).

    Aggregates per-session accuracy rates.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT items_correct, items_completed FROM session_log
        WHERE started_at >= ? AND items_completed > 0
        """,
        (cutoff,),
    ).fetchall()

    values = []
    for r in rows:
        completed = r["items_completed"] or 0
        correct = r["items_correct"] or 0
        if completed > 0:
            values.append(correct / completed)

    result = calculate_cpk(values, lsl=0.6, usl=1.0)
    result["metric"] = "drill_accuracy"
    result["spec"] = "LSL=0.6, USL=1.0"
    result["days"] = days
    return result


def calculate_process_performance(
    values: list[float],
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Any]:
    """Calculate process PERFORMANCE indices Pp and Ppk.

    Unlike Cp/Cpk (which use within-subgroup variation), Pp/Ppk use
    overall standard deviation — appropriate for learning system metrics
    where "subgroups" are artificial.

    Pp  = (USL - LSL) / (6 * sigma_overall)
    Ppk = min((USL - mu) / (3 * sigma_overall), (mu - LSL) / (3 * sigma_overall))

    Interpretation:
        Ppk >= 1.33 — capable process
        1.0 <= Ppk < 1.33 — marginally capable
        Ppk < 1.0 — not capable
    """
    result: dict[str, Any] = {
        "pp": None, "ppk": None, "ppu": None, "ppl": None,
        "mean": None, "std_overall": None, "n": 0,
        "lsl": lsl, "usl": usl, "interpretation": "insufficient_data",
    }

    if not values or (lsl is None and usl is None):
        return result

    n = len(values)
    result["n"] = n

    if n < 2:
        result["mean"] = values[0] if values else 0.0
        return result

    mean = sum(values) / n
    # Overall sigma (population std dev for Pp/Ppk)
    variance = sum((x - mean) ** 2 for x in values) / n
    sigma = math.sqrt(variance) if variance > 0 else 0.0

    result["mean"] = round(mean, 6)
    result["std_overall"] = round(sigma, 6)

    if sigma == 0:
        result["pp"] = 99.0
        result["ppk"] = 99.0
        result["interpretation"] = "perfect"
        return result

    if usl is not None:
        ppu = (usl - mean) / (3 * sigma)
        result["ppu"] = round(ppu, 4)

    if lsl is not None:
        ppl = (mean - lsl) / (3 * sigma)
        result["ppl"] = round(ppl, 4)

    if lsl is not None and usl is not None:
        pp = (usl - lsl) / (6 * sigma)
        result["pp"] = round(pp, 4)

    caps = [v for v in [result["ppu"], result["ppl"]] if v is not None]
    ppk = round(min(caps), 4) if caps else None
    result["ppk"] = ppk

    # Interpret
    if ppk is not None:
        if ppk >= 1.33:
            result["interpretation"] = "capable"
        elif ppk >= 1.0:
            result["interpretation"] = "marginally_capable"
        else:
            result["interpretation"] = "not_capable"

    return result


def assess_accuracy_performance(conn, days: int = 30) -> dict[str, Any]:
    """Pp/Ppk for drill accuracy: LSL=70% (target), USL=100%.

    Uses 30-day window for process performance (longer than Cpk's 7-day).
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT items_correct, items_completed FROM session_log
        WHERE started_at >= ? AND items_completed > 0
        """,
        (cutoff,),
    ).fetchall()

    values = []
    for r in rows:
        completed = r["items_completed"] or 0
        correct = r["items_correct"] or 0
        if completed > 0:
            values.append(correct / completed)

    result = calculate_process_performance(values, lsl=0.70, usl=1.0)
    result["metric"] = "drill_accuracy_performance"
    result["spec"] = "LSL=70%, USL=100%"
    result["days"] = days
    return result


def get_capability_summary(conn) -> dict[str, Any]:
    """All capability assessments in a single dict."""
    return {
        "api_latency": assess_api_latency(conn),
        "session_load": assess_session_load(conn),
        "drill_accuracy": assess_drill_accuracy(conn),
        "accuracy_performance": assess_accuracy_performance(conn),
    }
