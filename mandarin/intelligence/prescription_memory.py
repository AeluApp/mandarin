"""Prescription Memory — the system remembers which actions worked where.

When the intelligence engine encounters a problem (dimension + severity + metric),
it can look up historical outcomes: "Last time we saw high-severity bounce_rate
issues on blog pages, rewrite_meta had an 85% success rate vs rewrite_cta at 60%."

This converts the system from stateless (pick the default action) to learned
(pick the historically best action for this context).

Tables:
    prescription_history — every action outcome indexed by context hash

Functions:
    compute_context_hash — deterministic hash for (dimension, severity, metric, target_type)
    record_prescription_outcome — store outcome after verification
    suggest_prescription — ranked action recommendations for a context
    get_prescription_stats — what the system has learned overall
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Table creation ────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create prescription_history table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prescription_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_hash TEXT NOT NULL,
            context_json TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_pattern TEXT,
            outcome TEXT CHECK (outcome IN ('improved', 'neutral', 'regressed', 'reverted')),
            delta_pct REAL,
            action_ledger_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_prescription_context_hash
        ON prescription_history(context_hash)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_prescription_action_type
        ON prescription_history(action_type)
    """)
    conn.commit()


# ── Context hashing ──────────────────────────────────────────────────────

def compute_context_hash(
    dimension: str,
    severity: str,
    metric_name: str,
    target_type: str | None = None,
) -> str:
    """Compute a deterministic hash for a prescription context.

    The hash encodes the "situation" the system was in when an action was
    taken. When the same situation recurs, we can look up what worked before.

    Args:
        dimension: the intelligence dimension (e.g., 'marketing', 'ux')
        severity: finding severity ('critical', 'high', 'medium', 'low')
        metric_name: the specific metric (e.g., 'bounce_rate', 'session_completion')
        target_type: type of target (e.g., 'blog', 'landing', 'vs_page'), or None

    Returns:
        A hex digest string suitable for exact-match lookups.
    """
    components = [
        dimension.lower().strip(),
        severity.lower().strip(),
        metric_name.lower().strip(),
        (target_type or "").lower().strip(),
    ]
    raw = "|".join(components)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _generalize_target(target: str | None) -> str | None:
    """Generalize a specific target path into a pattern.

    Examples:
        '/blog/hsk3-study-plan' → '/blog/*'
        '/vs-anki' → '/vs-*'
        '/landing/pricing' → '/landing/*'
        None → None
    """
    if not target:
        return None

    target = target.strip()

    # Blog posts: /blog/anything → /blog/*
    if re.match(r"^/blog/.+", target):
        return "/blog/*"

    # VS pages: /vs-anything → /vs-*
    if re.match(r"^/vs-.+", target):
        return "/vs-*"

    # HSK pages: /hsk-anything → /hsk-*
    if re.match(r"^/hsk-.+", target):
        return "/hsk-*"

    # Landing subpages: /landing/anything → /landing/*
    if re.match(r"^/landing/.+", target):
        return "/landing/*"

    # File paths: marketing/landing/blog/anything.html → marketing/landing/blog/*
    if "/" in target and target.endswith(".html"):
        parts = target.rsplit("/", 1)
        return parts[0] + "/*"

    return target


def _infer_target_type(target_pattern: str | None) -> str | None:
    """Infer a broad target type from the pattern.

    Used for context hashing — groups /blog/*, /vs-*, etc. into categories.
    """
    if not target_pattern:
        return None
    if target_pattern.startswith("/blog"):
        return "blog"
    if target_pattern.startswith("/vs-"):
        return "vs_page"
    if target_pattern.startswith("/hsk-"):
        return "hsk_page"
    if target_pattern.startswith("/landing"):
        return "landing"
    if "marketing/landing/blog" in target_pattern:
        return "blog"
    if "marketing/landing" in target_pattern:
        return "landing"
    return "other"


# ── Recording outcomes ───────────────────────────────────────────────────

def record_prescription_outcome(
    conn: sqlite3.Connection,
    context: dict,
    action_type: str,
    target_pattern: str | None,
    outcome: str,
    delta_pct: float | None = None,
    action_id: int | None = None,
) -> int | None:
    """Record the outcome of a prescription action.

    Called when an action's outcome has been verified (typically by
    verify_recommendation_outcomes in feedback_loops.py).

    Args:
        conn: database connection
        context: dict with keys: dimension, severity, metric_name, target_type
        action_type: what was done (e.g., 'rewrite_meta', 'reduce_difficulty')
        target_pattern: generalized target (e.g., '/blog/*')
        outcome: 'improved', 'neutral', 'regressed', or 'reverted'
        delta_pct: percentage change in the target metric
        action_id: optional FK to pi_recommendation_outcome.id or similar

    Returns:
        The prescription_history row id, or None on failure.
    """
    _ensure_tables(conn)

    dimension = context.get("dimension", "")
    severity = context.get("severity", "")
    metric_name = context.get("metric_name", "")
    target_type = context.get("target_type")

    context_hash = compute_context_hash(dimension, severity, metric_name, target_type)

    # Generalize target if it's specific
    if target_pattern:
        target_pattern = _generalize_target(target_pattern)

    context_json = json.dumps({
        "dimension": dimension,
        "severity": severity,
        "metric_name": metric_name,
        "target_type": target_type,
    }, sort_keys=True)

    try:
        cur = conn.execute("""
            INSERT INTO prescription_history
                (context_hash, context_json, action_type, target_pattern,
                 outcome, delta_pct, action_ledger_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            context_hash, context_json, action_type, target_pattern,
            outcome, delta_pct, action_id,
        ))
        conn.commit()
        return cur.lastrowid
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Prescription memory: failed to record outcome: %s", exc)
        return None


# ── Suggesting actions ───────────────────────────────────────────────────

def suggest_prescription(
    conn: sqlite3.Connection,
    context: dict,
) -> list[dict]:
    """Suggest the best action for a given context based on historical outcomes.

    Tries exact context match first. If no history, progressively broadens
    the search by dropping target_type, then severity.

    Args:
        conn: database connection
        context: dict with keys: dimension, severity, metric_name, target_type

    Returns:
        Ranked list of action recommendations:
        [
            {
                "action_type": "rewrite_cta",
                "success_rate": 0.85,
                "avg_delta": 12.3,
                "sample_size": 7,
                "match_level": "exact",
            },
            ...
        ]
        Empty list if no historical data.
    """
    _ensure_tables(conn)

    dimension = context.get("dimension", "")
    severity = context.get("severity", "")
    metric_name = context.get("metric_name", "")
    target_type = context.get("target_type")

    # ── Level 1: Exact match ──
    exact_hash = compute_context_hash(dimension, severity, metric_name, target_type)
    results = _query_prescription_stats(conn, exact_hash)
    if results:
        for r in results:
            r["match_level"] = "exact"
        return results

    # ── Level 2: Drop target_type (same dimension + severity + metric) ──
    broad_hash = compute_context_hash(dimension, severity, metric_name, None)
    results = _query_prescription_stats(conn, broad_hash)
    if results:
        for r in results:
            r["match_level"] = "no_target_type"
        return results

    # ── Level 3: Drop severity too (same dimension + metric only) ──
    # Query across all severities for this dimension+metric
    dimension_results = _query_prescription_stats_by_dimension(
        conn, dimension, metric_name,
    )
    if dimension_results:
        for r in dimension_results:
            r["match_level"] = "dimension_metric_only"
        return dimension_results

    # ── Level 4: Dimension-only fallback ──
    fallback = _query_prescription_stats_by_dimension_only(conn, dimension)
    if fallback:
        for r in fallback:
            r["match_level"] = "dimension_only"
        return fallback

    return []


def _query_prescription_stats(
    conn: sqlite3.Connection,
    context_hash: str,
) -> list[dict]:
    """Get action stats for an exact context hash."""
    rows = _safe_query_all(conn, """
        SELECT
            action_type,
            COUNT(*) as sample_size,
            SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) as improved,
            SUM(CASE WHEN outcome = 'regressed' THEN 1 ELSE 0 END) as regressed,
            AVG(CASE WHEN outcome = 'improved' THEN delta_pct ELSE NULL END) as avg_delta
        FROM prescription_history
        WHERE context_hash = ?
        GROUP BY action_type
        HAVING sample_size >= 2
        ORDER BY
            CAST(SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) AS REAL)
            / COUNT(*) DESC,
            sample_size DESC
    """, (context_hash,))

    if not rows:
        return []

    results = []
    for row in rows:
        total = row["sample_size"]
        improved = row["improved"] or 0
        success_rate = improved / max(total, 1)
        results.append({
            "action_type": row["action_type"],
            "success_rate": round(success_rate, 3),
            "avg_delta": round(row["avg_delta"] or 0.0, 1),
            "sample_size": total,
        })

    return results


def _query_prescription_stats_by_dimension(
    conn: sqlite3.Connection,
    dimension: str,
    metric_name: str,
) -> list[dict]:
    """Get action stats matching dimension + metric across all severities."""
    rows = _safe_query_all(conn, """
        SELECT
            ph.action_type,
            COUNT(*) as sample_size,
            SUM(CASE WHEN ph.outcome = 'improved' THEN 1 ELSE 0 END) as improved,
            AVG(CASE WHEN ph.outcome = 'improved' THEN ph.delta_pct ELSE NULL END) as avg_delta
        FROM prescription_history ph
        WHERE ph.context_json LIKE ?
          AND ph.context_json LIKE ?
        GROUP BY ph.action_type
        HAVING sample_size >= 2
        ORDER BY
            CAST(SUM(CASE WHEN ph.outcome = 'improved' THEN 1 ELSE 0 END) AS REAL)
            / COUNT(*) DESC,
            sample_size DESC
    """, (
        f'%"dimension": "{dimension}"%',
        f'%"metric_name": "{metric_name}"%',
    ))

    if not rows:
        return []

    results = []
    for row in rows:
        total = row["sample_size"]
        improved = row["improved"] or 0
        success_rate = improved / max(total, 1)
        results.append({
            "action_type": row["action_type"],
            "success_rate": round(success_rate, 3),
            "avg_delta": round(row["avg_delta"] or 0.0, 1),
            "sample_size": total,
        })

    return results


def _query_prescription_stats_by_dimension_only(
    conn: sqlite3.Connection,
    dimension: str,
) -> list[dict]:
    """Get action stats matching just the dimension — broadest fallback."""
    rows = _safe_query_all(conn, """
        SELECT
            ph.action_type,
            COUNT(*) as sample_size,
            SUM(CASE WHEN ph.outcome = 'improved' THEN 1 ELSE 0 END) as improved,
            AVG(CASE WHEN ph.outcome = 'improved' THEN ph.delta_pct ELSE NULL END) as avg_delta
        FROM prescription_history ph
        WHERE ph.context_json LIKE ?
        GROUP BY ph.action_type
        HAVING sample_size >= 3
        ORDER BY
            CAST(SUM(CASE WHEN ph.outcome = 'improved' THEN 1 ELSE 0 END) AS REAL)
            / COUNT(*) DESC,
            sample_size DESC
        LIMIT 10
    """, (f'%"dimension": "{dimension}"%',))

    if not rows:
        return []

    results = []
    for row in rows:
        total = row["sample_size"]
        improved = row["improved"] or 0
        success_rate = improved / max(total, 1)
        results.append({
            "action_type": row["action_type"],
            "success_rate": round(success_rate, 3),
            "avg_delta": round(row["avg_delta"] or 0.0, 1),
            "sample_size": total,
        })

    return results


# ── Stats and reporting ──────────────────────────────────────────────────

def get_prescription_stats(conn: sqlite3.Connection) -> dict:
    """Summary of what the system has learned from prescription outcomes.

    Returns:
        {
            "total_outcomes": int,
            "outcomes_by_result": {"improved": N, "neutral": N, ...},
            "top_actions": [...],
            "best_performers": [...],
            "worst_performers": [...],
            "contexts_with_most_data": [...],
            "overall_success_rate": float,
        }
    """
    _ensure_tables(conn)

    total = _safe_scalar(
        conn, "SELECT COUNT(*) FROM prescription_history", default=0,
    )

    # Outcomes breakdown
    outcome_rows = _safe_query_all(conn, """
        SELECT outcome, COUNT(*) as cnt
        FROM prescription_history
        GROUP BY outcome
    """)
    outcomes_by_result = {}
    for row in (outcome_rows or []):
        outcomes_by_result[row["outcome"] or "unknown"] = row["cnt"]

    improved = outcomes_by_result.get("improved", 0)
    overall_success_rate = improved / max(total, 1)

    # Top action types by volume
    top_actions = _safe_query_all(conn, """
        SELECT
            action_type,
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) as improved,
            SUM(CASE WHEN outcome = 'regressed' THEN 1 ELSE 0 END) as regressed,
            AVG(CASE WHEN outcome = 'improved' THEN delta_pct ELSE NULL END) as avg_positive_delta,
            CAST(SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) AS REAL)
                / COUNT(*) as success_rate
        FROM prescription_history
        GROUP BY action_type
        ORDER BY total DESC
        LIMIT 10
    """)

    # Best performers (highest success rate with meaningful sample)
    best = _safe_query_all(conn, """
        SELECT
            action_type,
            COUNT(*) as total,
            CAST(SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) AS REAL)
                / COUNT(*) as success_rate,
            AVG(CASE WHEN outcome = 'improved' THEN delta_pct ELSE NULL END) as avg_delta
        FROM prescription_history
        GROUP BY action_type
        HAVING total >= 5
        ORDER BY success_rate DESC
        LIMIT 5
    """)

    # Worst performers
    worst = _safe_query_all(conn, """
        SELECT
            action_type,
            COUNT(*) as total,
            CAST(SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) AS REAL)
                / COUNT(*) as success_rate,
            SUM(CASE WHEN outcome = 'regressed' THEN 1 ELSE 0 END) as regressed
        FROM prescription_history
        GROUP BY action_type
        HAVING total >= 5
        ORDER BY success_rate ASC
        LIMIT 5
    """)

    # Contexts with the most data (most outcomes recorded)
    contexts = _safe_query_all(conn, """
        SELECT
            context_json,
            COUNT(*) as total,
            CAST(SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) AS REAL)
                / COUNT(*) as success_rate
        FROM prescription_history
        GROUP BY context_hash
        ORDER BY total DESC
        LIMIT 10
    """)

    def _row_to_dict(row):
        return dict(row) if row else {}

    return {
        "total_outcomes": total,
        "outcomes_by_result": outcomes_by_result,
        "overall_success_rate": round(overall_success_rate, 3),
        "top_actions": [_row_to_dict(r) for r in (top_actions or [])],
        "best_performers": [_row_to_dict(r) for r in (best or [])],
        "worst_performers": [_row_to_dict(r) for r in (worst or [])],
        "contexts_with_most_data": [
            {
                "context": json.loads(r["context_json"]) if r.get("context_json") else {},
                "total": r["total"],
                "success_rate": round(r["success_rate"], 3),
            }
            for r in (contexts or [])
        ],
    }
