"""Stratification — compute user strata for balanced experiment assignment.

Strata are computed from pre-treatment characteristics only (HSK band and
engagement band).  The stratum string is included in the assignment hash so
that balance is maintained within each stratum.
"""

from __future__ import annotations

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

# Default stratification: HSK band × engagement band = up to 9 cells
DEFAULT_STRATIFICATION_CONFIG: dict = {
    "variables": ["hsk_band", "engagement_band"],
    "min_stratum_size": 10,
    "collapse_strategy": "merge_adjacent",
}


def compute_stratum(
    conn: sqlite3.Connection,
    user_id: int,
    config: dict | None = None,
) -> str:
    """Compute the stratification stratum for a user.

    Returns a deterministic string like ``'hsk:low|eng:med'`` suitable for
    inclusion in an assignment hash key.
    """
    config = config or DEFAULT_STRATIFICATION_CONFIG
    variables = config.get("variables", ["hsk_band", "engagement_band"])

    parts: list[str] = []
    for var in variables:
        if var == "hsk_band":
            parts.append(f"hsk:{_hsk_band(conn, user_id)}")
        elif var == "engagement_band":
            parts.append(f"eng:{_engagement_band(conn, user_id)}")
        elif var == "tenure_band":
            parts.append(f"ten:{_tenure_band(conn, user_id)}")
        else:
            logger.warning("Unknown stratification variable: %s", var)

    return "|".join(parts) if parts else "default"


def validate_strata(
    conn: sqlite3.Connection,
    experiment_id: int,
    min_stratum_size: int = 10,
) -> dict:
    """Check stratum sizes for an experiment and return diagnostics.

    Returns ``{strata: {stratum: {n_total, n_per_variant}}, warnings: [...]}``.
    """
    try:
        rows = conn.execute(
            """SELECT stratum, variant, COUNT(*) as n
               FROM experiment_assignment
               WHERE experiment_id = ?
               GROUP BY stratum, variant""",
            (experiment_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"strata": {}, "warnings": ["assignment table missing stratum column"]}

    strata: dict[str, dict] = {}
    for r in rows:
        s = r["stratum"] or "default"
        if s not in strata:
            strata[s] = {"n_total": 0, "variants": {}}
        strata[s]["n_total"] += r["n"]
        strata[s]["variants"][r["variant"]] = r["n"]

    warnings: list[str] = []
    for s, info in strata.items():
        for variant, count in info["variants"].items():
            if count < min_stratum_size:
                warnings.append(
                    f"stratum '{s}' variant '{variant}' has only {count} users "
                    f"(< {min_stratum_size})"
                )

    return {"strata": strata, "warnings": warnings}


def get_stratum_sizes(
    conn: sqlite3.Connection,
    experiment_id: int,
) -> dict[str, int]:
    """Return {stratum: total_count} for an experiment."""
    try:
        rows = conn.execute(
            """SELECT stratum, COUNT(*) as n
               FROM experiment_assignment
               WHERE experiment_id = ?
               GROUP BY stratum""",
            (experiment_id,),
        ).fetchall()
        return {r["stratum"] or "default": r["n"] for r in rows}
    except sqlite3.OperationalError:
        return {}


# ── Band computation helpers ─────────────────────────────────────────────────


def _hsk_band(conn: sqlite3.Connection, user_id: int) -> str:
    """Return 'low', 'mid', or 'high'."""
    try:
        row = conn.execute(
            """SELECT
                 (COALESCE(level_reading, 1) + COALESCE(level_listening, 1) +
                  COALESCE(level_speaking, 1) + COALESCE(level_ime, 1)) / 4.0 as avg_level
               FROM learner_profile WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        if not row or row["avg_level"] is None:
            return "low"
        level = float(row["avg_level"])
        if level <= 2.5:
            return "low"
        elif level <= 4.5:
            return "mid"
        return "high"
    except sqlite3.OperationalError:
        return "low"


def _engagement_band(conn: sqlite3.Connection, user_id: int) -> str:
    """Return 'low', 'med', or 'high' based on sessions in last 14 days."""
    try:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM session_log
               WHERE user_id = ? AND started_at >= datetime('now', '-14 days')""",
            (user_id,),
        ).fetchone()
        weekly = (row["cnt"] if row else 0) / 2.0
        if weekly < 2:
            return "low"
        elif weekly < 5:
            return "med"
        return "high"
    except sqlite3.OperationalError:
        return "low"


def _tenure_band(conn: sqlite3.Connection, user_id: int) -> str:
    """Return 'new' (<30 days) or 'est' (30+ days)."""
    try:
        row = conn.execute(
            "SELECT julianday('now') - julianday(created_at) as days FROM user WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row or row["days"] is None:
            return "new"
        return "new" if row["days"] < 30 else "est"
    except sqlite3.OperationalError:
        return "new"
