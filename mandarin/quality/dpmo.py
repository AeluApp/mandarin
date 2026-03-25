"""DPMO (Defects Per Million Opportunities) from review_event data."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Sigma lookup table: (lower_dpmo_bound, upper_dpmo_bound) -> sigma
# Based on standard Six Sigma conversion tables.
_SIGMA_TABLE: list[tuple[float, float, float]] = [
    (933200, 1000000, 0.0),
    (841300, 933200, 0.5),
    (691500, 841300, 1.0),
    (500000, 691500, 1.5),
    (308500, 500000, 2.0),
    (158700, 308500, 2.5),
    (66807, 158700, 3.0),
    (22750, 66807, 3.5),
    (6210, 22750, 4.0),
    (1350, 6210, 4.5),
    (233, 1350, 5.0),
    (32, 233, 5.5),
    (3.4, 32, 6.0),
    (0, 3.4, 6.5),
]


def sigma_from_dpmo(dpmo: float) -> float:
    """Convert DPMO to approximate sigma level using lookup table.

    Uses linear interpolation within each half-sigma band for smoother
    results than a simple step function.
    """
    if dpmo <= 0:
        return 6.5
    if dpmo >= 1_000_000:
        return 0.0

    for lower, upper, sigma_base in _SIGMA_TABLE:
        if lower <= dpmo < upper:
            # Linear interpolation within the band
            fraction = (upper - dpmo) / (upper - lower) if upper != lower else 0.0
            return sigma_base + fraction * 0.5

    return 0.0


def calculate_dpmo(conn, days: int = 30) -> dict[str, Any]:
    """Calculate DPMO from review_event data.

    Opportunity = each review_event row.
    Defect = review where correct=0.
    DPMO = (defects / opportunities) * 1,000,000.

    Returns dict with total_opportunities, total_defects, dpmo,
    sigma_level, period_days.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS defects
        FROM review_event
        WHERE created_at >= ?
        """,
        (cutoff,),
    ).fetchone()

    total = (row["total"] if row else 0) or 0
    defects = (row["defects"] if row else 0) or 0

    if total == 0:
        dpmo = 0.0
        sigma = 6.5
    else:
        dpmo = (defects / total) * 1_000_000
        sigma = sigma_from_dpmo(dpmo)

    return {
        "total_opportunities": total,
        "total_defects": defects,
        "dpmo": round(dpmo, 1),
        "sigma_level": round(sigma, 2),
        "period_days": days,
    }


def get_dpmo_trend(conn, periods: int = 12, period_days: int = 7) -> list[dict[str, Any]]:
    """Return DPMO values for consecutive periods, most recent last.

    Each entry: {period_start, period_end, dpmo, sigma_level,
    total_opportunities, total_defects}.
    """
    now = datetime.now(UTC)
    results: list[dict[str, Any]] = []

    for i in range(periods - 1, -1, -1):
        period_end = now - timedelta(days=i * period_days)
        period_start = period_end - timedelta(days=period_days)

        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS defects
            FROM review_event
            WHERE created_at >= ? AND created_at < ?
            """,
            (period_start.isoformat(), period_end.isoformat()),
        ).fetchone()

        total = (row["total"] if row else 0) or 0
        defects = (row["defects"] if row else 0) or 0

        if total == 0:
            dpmo = 0.0
        else:
            dpmo = (defects / total) * 1_000_000

        results.append({
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "dpmo": round(dpmo, 1),
            "sigma_level": round(sigma_from_dpmo(dpmo), 2),
            "total_opportunities": total,
            "total_defects": defects,
        })

    return results
