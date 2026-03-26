"""Unified Action Audit Trail — single ledger for all automated intelligence actions.

Replaces 6 separate action log tables with a single, counterfactual-aware
audit trail. Every automated action (cache clear, email send, feature toggle,
content rewrite, etc.) is recorded here with before/after metrics and a
verification window.

After the verification window elapses, the system measures whether the action
improved, was neutral to, or regressed the target metric — adjusted for the
pre-existing baseline trend (counterfactual).

Tables:
    action_ledger — unified audit trail

Functions:
    record_action(conn, ...) -> action_id
    verify_pending_actions(conn)
    get_action_summary(conn, days=7) -> dict
    compute_baseline_trend(conn, metric_name, target, days=7) -> float
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, UTC

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Table creation ─────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create the action_ledger table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS action_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            module TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target TEXT,
            description TEXT,
            precondition_met INTEGER DEFAULT 1,
            contract_id INTEGER,
            metrics_before TEXT,
            metrics_after TEXT,
            baseline_trend REAL,
            verified_at TEXT,
            outcome TEXT DEFAULT 'pending'
                CHECK (outcome IN ('pending','improved','neutral','regressed','reverted')),
            verification_window_hours INTEGER DEFAULT 48,
            action_delta REAL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_ledger_module
        ON action_ledger(module, timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_action_ledger_outcome
        ON action_ledger(outcome, timestamp)
    """)
    conn.commit()


# ── Core functions ─────────────────────────────────────────────────────────

def record_action(
    conn: sqlite3.Connection,
    module: str,
    action_type: str,
    target: str | None,
    description: str | None,
    metrics_before: dict | None,
    verification_hours: int = 48,
    contract_id: int | None = None,
    baseline_trend: float | None = None,
) -> int | None:
    """Record an automated action in the unified ledger.

    Args:
        conn: Database connection.
        module: Originating module name (e.g. 'self_healing', 'cost_monitor').
        action_type: Specific action (e.g. 'clear_cache', 'toggle_flag').
        target: What was acted on (file path, content_item_id, flag name, etc.).
        description: Human-readable description of what happened.
        metrics_before: JSON-serializable dict of metrics at time of action.
        verification_hours: Hours to wait before verifying outcome.
        contract_id: FK to action_contract table (if contract-governed).
        baseline_trend: Pre-computed slope of the target metric over 7 days.

    Returns:
        The action_id (row id) or None on failure.
    """
    _ensure_tables(conn)

    try:
        cur = conn.execute("""
            INSERT INTO action_ledger
                (module, action_type, target, description,
                 metrics_before, verification_window_hours,
                 contract_id, baseline_trend)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            module,
            action_type,
            target,
            description,
            json.dumps(metrics_before) if metrics_before else None,
            verification_hours,
            contract_id,
            baseline_trend,
        ))
        conn.commit()
        return cur.lastrowid
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Action ledger: failed to record action: %s", exc)
        return None


def verify_pending_actions(conn: sqlite3.Connection) -> dict:
    """Verify actions whose verification window has elapsed.

    For each pending action past its window:
    1. Fetch current metric value via module-specific fetcher.
    2. Compute baseline-adjusted delta.
    3. Set outcome (improved / neutral / regressed).

    Returns a summary dict.
    """
    _ensure_tables(conn)

    pending = _safe_query_all(conn, """
        SELECT id, module, action_type, target, metrics_before,
               baseline_trend, verification_window_hours, timestamp
        FROM action_ledger
        WHERE outcome = 'pending'
          AND datetime(timestamp, '+' || verification_window_hours || ' hours') <= datetime('now')
        ORDER BY timestamp ASC
        LIMIT 50
    """)

    if not pending:
        return {"verified": 0, "improved": 0, "neutral": 0, "regressed": 0}

    counts = {"verified": 0, "improved": 0, "neutral": 0, "regressed": 0}

    for row in pending:
        action_id = row["id"]
        module = row["module"]
        action_type = row["action_type"]
        target = row["target"]

        # Fetch current metrics via module-specific fetcher
        fetcher = _METRIC_FETCHERS.get((module, action_type))
        if fetcher is None:
            # Fallback: try module-level fetcher
            fetcher = _METRIC_FETCHERS.get((module, "*"))

        metrics_after = None
        if fetcher:
            try:
                metrics_after = fetcher(conn, target)
            except Exception as exc:
                logger.debug(
                    "Action ledger: metric fetcher failed for %s/%s: %s",
                    module, action_type, exc,
                )

        # Compute delta
        metrics_before_raw = row["metrics_before"]
        baseline = row["baseline_trend"] or 0.0
        outcome = "neutral"
        action_delta = None

        if metrics_before_raw and metrics_after:
            try:
                before_dict = json.loads(metrics_before_raw)
                delta = _compute_delta(before_dict, metrics_after, baseline)
                action_delta = delta

                if delta is not None:
                    # Positive delta = improvement, negative = regression
                    # Threshold: ±2% to avoid noise
                    if delta > 0.02:
                        outcome = "improved"
                    elif delta < -0.02:
                        outcome = "regressed"
                    else:
                        outcome = "neutral"
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.debug("Action ledger: delta computation failed for action %d: %s",
                             action_id, exc)

        # Update the action record
        try:
            conn.execute("""
                UPDATE action_ledger
                SET verified_at = datetime('now'),
                    outcome = ?,
                    metrics_after = ?,
                    action_delta = ?
                WHERE id = ?
            """, (
                outcome,
                json.dumps(metrics_after) if metrics_after else None,
                action_delta,
                action_id,
            ))
            conn.commit()
            counts["verified"] += 1
            counts[outcome] += 1
        except (sqlite3.OperationalError, sqlite3.Error) as exc:
            logger.debug("Action ledger: failed to update action %d: %s", action_id, exc)

    if counts["verified"] > 0:
        logger.info(
            "Action ledger: verified %d action(s) — %d improved, %d neutral, %d regressed",
            counts["verified"], counts["improved"], counts["neutral"], counts["regressed"],
        )

    return counts


def get_action_summary(conn: sqlite3.Connection, days: int = 7) -> dict:
    """Get a summary of actions over the last N days.

    Returns dict with:
        total_actions, success_rate, by_module, by_action_type, recent
    """
    _ensure_tables(conn)

    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM action_ledger
        WHERE timestamp >= datetime('now', ? || ' days')
    """, (f"-{days}",), default=0)

    improved = _safe_scalar(conn, """
        SELECT COUNT(*) FROM action_ledger
        WHERE timestamp >= datetime('now', ? || ' days')
          AND outcome = 'improved'
    """, (f"-{days}",), default=0)

    neutral = _safe_scalar(conn, """
        SELECT COUNT(*) FROM action_ledger
        WHERE timestamp >= datetime('now', ? || ' days')
          AND outcome = 'neutral'
    """, (f"-{days}",), default=0)

    regressed = _safe_scalar(conn, """
        SELECT COUNT(*) FROM action_ledger
        WHERE timestamp >= datetime('now', ? || ' days')
          AND outcome = 'regressed'
    """, (f"-{days}",), default=0)

    pending = _safe_scalar(conn, """
        SELECT COUNT(*) FROM action_ledger
        WHERE timestamp >= datetime('now', ? || ' days')
          AND outcome = 'pending'
    """, (f"-{days}",), default=0)

    # Verified total (non-pending)
    verified = total - pending
    success_rate = (improved / verified) if verified > 0 else 0.0

    # By module
    by_module_rows = _safe_query_all(conn, """
        SELECT module, COUNT(*) as cnt,
               SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) as improved,
               SUM(CASE WHEN outcome = 'regressed' THEN 1 ELSE 0 END) as regressed
        FROM action_ledger
        WHERE timestamp >= datetime('now', ? || ' days')
        GROUP BY module
        ORDER BY cnt DESC
    """, (f"-{days}",))

    by_module = {}
    for row in (by_module_rows or []):
        by_module[row["module"]] = {
            "total": row["cnt"],
            "improved": row["improved"],
            "regressed": row["regressed"],
        }

    # By action_type
    by_type_rows = _safe_query_all(conn, """
        SELECT action_type, COUNT(*) as cnt,
               SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) as improved,
               SUM(CASE WHEN outcome = 'regressed' THEN 1 ELSE 0 END) as regressed
        FROM action_ledger
        WHERE timestamp >= datetime('now', ? || ' days')
        GROUP BY action_type
        ORDER BY cnt DESC
    """, (f"-{days}",))

    by_action_type = {}
    for row in (by_type_rows or []):
        by_action_type[row["action_type"]] = {
            "total": row["cnt"],
            "improved": row["improved"],
            "regressed": row["regressed"],
        }

    # Recent actions
    recent_rows = _safe_query_all(conn, """
        SELECT id, timestamp, module, action_type, target, description,
               outcome, action_delta, verified_at
        FROM action_ledger
        WHERE timestamp >= datetime('now', ? || ' days')
        ORDER BY timestamp DESC
        LIMIT 50
    """, (f"-{days}",))

    recent = [dict(r) for r in recent_rows] if recent_rows else []

    return {
        "days": days,
        "total_actions": total,
        "improved": improved,
        "neutral": neutral,
        "regressed": regressed,
        "pending": pending,
        "success_rate": round(success_rate, 3),
        "by_module": by_module,
        "by_action_type": by_action_type,
        "recent": recent,
    }


def compute_baseline_trend(
    conn: sqlite3.Connection,
    metric_name: str,
    target: str | None,
    days: int = 7,
) -> float | None:
    """Calculate the slope of a metric over recent history.

    Queries the action_ledger for past actions on the same target and
    metric, computing the average delta per day as a simple trend estimator.

    Returns slope (delta per day) or None if insufficient data.
    """
    _ensure_tables(conn)

    # Look at verified actions for this target over the window
    rows = _safe_query_all(conn, """
        SELECT action_delta, timestamp
        FROM action_ledger
        WHERE target = ?
          AND outcome != 'pending'
          AND action_delta IS NOT NULL
          AND timestamp >= datetime('now', ? || ' days')
        ORDER BY timestamp ASC
    """, (target, f"-{days}"))

    if not rows or len(rows) < 2:
        return None

    # Simple linear trend: average delta
    deltas = [r["action_delta"] for r in rows if r["action_delta"] is not None]
    if not deltas:
        return None

    return sum(deltas) / len(deltas)


# ── Module-specific metric fetchers ────────────────────────────────────────

def _fetch_self_healing_metrics(conn: sqlite3.Connection, target: str | None) -> dict | None:
    """Fetch current health metrics for self-healing verification."""
    try:
        from .self_healing import collect_health_metrics
        return collect_health_metrics(conn)
    except Exception:
        return None


def _fetch_core_loop_metrics(conn: sqlite3.Connection, target: str | None) -> dict | None:
    """Fetch core loop metrics for verification."""
    try:
        from .core_loop_monitor import (
            _session_completion_rate, _drill_error_rate,
            _tts_failure_rate, _llm_timeout_rate,
        )
        comp_rate, comp_total = _session_completion_rate(conn)
        err_rate, err_total = _drill_error_rate(conn)
        tts_rate, tts_total = _tts_failure_rate(conn)
        llm_rate, llm_total = _llm_timeout_rate(conn)
        return {
            "session_completion_rate": comp_rate,
            "drill_error_rate": err_rate,
            "tts_failure_rate": tts_rate,
            "llm_timeout_rate": llm_rate,
        }
    except Exception:
        return None


def _fetch_cost_metrics(conn: sqlite3.Connection, target: str | None) -> dict | None:
    """Fetch cost metrics for verification."""
    try:
        from .cost_monitor import get_daily_spend, get_monthly_spend
        return {
            "daily_spend": get_daily_spend(conn),
            "monthly_spend": get_monthly_spend(conn),
        }
    except Exception:
        return None


def _fetch_dependency_metrics(conn: sqlite3.Connection, target: str | None) -> dict | None:
    """Fetch dependency health metrics for verification."""
    try:
        from .dependency_monitor import _get_last_status, DEPENDENCIES
        statuses = {}
        for dep_name in DEPENDENCIES:
            statuses[dep_name] = _get_last_status(conn, dep_name)
        return {"dependency_statuses": statuses}
    except Exception:
        return None


def _fetch_return_metrics(conn: sqlite3.Connection, target: str | None) -> dict | None:
    """Fetch return/retention metrics for verification."""
    try:
        users_24h_count = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user u
            JOIN learner_profile lp ON u.id = lp.user_id
            WHERE u.is_admin = 0 AND u.is_active = 1
              AND lp.last_session_date <= date('now', '-1 day')
              AND lp.last_session_date > date('now', '-2 days')
              AND lp.total_sessions >= 1
        """, default=0)
        return {"users_no_return_24h": users_24h_count}
    except Exception:
        return None


def _fetch_analytics_metrics(conn: sqlite3.Connection, target: str | None) -> dict | None:
    """Fetch analytics metrics for verification (page-level if target is a page path)."""
    try:
        from .analytics_auto_executor import _get_page_metrics
        page_metrics = _get_page_metrics(period="7d")
        if target and page_metrics:
            for pm in page_metrics:
                if pm.get("page") == target:
                    return {
                        "bounce_rate": (pm.get("bounce_rate") or 0) / 100.0,
                        "visitors": pm.get("visitors", 0),
                        "pageviews": pm.get("pageviews", 0),
                    }
        # Return aggregate if no specific page match
        from .analytics_auto_executor import _get_aggregate_metrics
        agg = _get_aggregate_metrics(period="7d")
        return agg if agg else None
    except Exception:
        return None


# Registry: (module, action_type) -> callable(conn, target) -> dict|None
# Use "*" as action_type for module-level fallback fetcher
_METRIC_FETCHERS: dict[tuple[str, str], callable] = {
    ("self_healing", "*"): _fetch_self_healing_metrics,
    ("core_loop_monitor", "*"): _fetch_core_loop_metrics,
    ("cost_monitor", "*"): _fetch_cost_metrics,
    ("dependency_monitor", "*"): _fetch_dependency_metrics,
    ("return_monitor", "*"): _fetch_return_metrics,
    ("analytics", "*"): _fetch_analytics_metrics,
    ("auto_executor", "*"): _fetch_self_healing_metrics,  # general health
}


# ── Delta computation ──────────────────────────────────────────────────────

def _compute_delta(
    metrics_before: dict,
    metrics_after: dict,
    baseline_trend: float,
) -> float | None:
    """Compute counterfactual-adjusted delta between before and after metrics.

    Compares a single "primary" metric between before/after, subtracting
    the baseline trend to isolate the action's effect.

    Primary metric selection:
    - If metrics have a common key, uses the first numeric one found.
    - Returns the raw delta minus the baseline (expected drift).
    """
    if not metrics_before or not metrics_after:
        return None

    # Find the first common numeric key
    for key in metrics_before:
        if key not in metrics_after:
            continue
        before_val = metrics_before[key]
        after_val = metrics_after[key]

        if isinstance(before_val, (int, float)) and isinstance(after_val, (int, float)):
            raw_delta = after_val - before_val
            # Subtract baseline trend (expected change without action)
            adjusted_delta = raw_delta - (baseline_trend or 0.0)
            return adjusted_delta

    return None
