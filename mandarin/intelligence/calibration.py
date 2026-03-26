"""Outcome-based threshold calibration — the system learns from its own actions.

Tracks every hardcoded threshold across intelligence modules, replaces them with
calibrated values derived from action outcomes, and adjusts sensitivity nightly.

The core idea: if actions triggered by a threshold succeed >90% of the time,
the threshold can be loosened (trigger earlier). If <50% succeed, tighten it
(trigger less often). This prevents the system from acting on noise while
ensuring it catches real problems.

Tables:
    calibrated_threshold — current calibrated value per (module, metric)
    calibration_log — audit trail of every adjustment

Functions:
    get_threshold(conn, module, metric, default) — read calibrated or default
    calibrate_thresholds(conn) — nightly adjustment loop
    get_calibration_history(conn, module, days) — recent adjustments
"""

from __future__ import annotations

import logging
import sqlite3

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)

# ── Threshold registry ─────────────────────────────────────────────────
#
# Maps (module, action_type) → (metric_key, default_value).
# This is how we know which threshold to adjust when an action succeeds
# or fails. The metric_key is the (module, metric) pair stored in
# calibrated_threshold.
#
# When a module takes an action because metric X breached threshold T,
# the outcome tells us whether T was set correctly.

_ACTION_TO_THRESHOLD = {
    # core_loop_monitor actions → thresholds they're triggered by
    ("core_loop_monitor", "session_completion_rate"): {
        "module": "core_loop_monitor",
        "metric": "session_completion_rate_min",
        "default": 0.70,
    },
    ("core_loop_monitor", "avg_session_duration"): {
        "module": "core_loop_monitor",
        "metric": "avg_session_duration_max_sec",
        "default": 1200.0,
    },
    ("core_loop_monitor", "drill_error_rate"): {
        "module": "core_loop_monitor",
        "metric": "drill_error_rate_max",
        "default": 0.30,
    },
    ("core_loop_monitor", "tts_failure_rate"): {
        "module": "core_loop_monitor",
        "metric": "tts_failure_rate_max",
        "default": 0.05,
    },
    ("core_loop_monitor", "llm_timeout_rate"): {
        "module": "core_loop_monitor",
        "metric": "llm_timeout_rate_max",
        "default": 0.10,
    },
    ("core_loop_monitor", "conversation_abandonment"): {
        "module": "core_loop_monitor",
        "metric": "conversation_abandonment_max",
        "default": 0.50,
    },
    ("core_loop_monitor", "item_breakpoint"): {
        "module": "core_loop_monitor",
        "metric": "item_abandon_threshold",
        "default": 3.0,
    },
    ("core_loop_monitor", "drill_type_failure"): {
        "module": "core_loop_monitor",
        "metric": "drill_type_failure_rate_max",
        "default": 0.40,
    },
    # return_monitor actions → thresholds
    ("return_monitor", "no_return_24h"): {
        "module": "return_monitor",
        "metric": "no_return_24h_hours",
        "default": 24.0,
    },
    ("return_monitor", "no_return_48h_difficulty"): {
        "module": "return_monitor",
        "metric": "difficulty_adjust_pct",
        "default": 0.10,
    },
    ("return_monitor", "at_risk_7d"): {
        "module": "return_monitor",
        "metric": "at_risk_days",
        "default": 7.0,
    },
    ("return_monitor", "churning_14d"): {
        "module": "return_monitor",
        "metric": "churning_days",
        "default": 14.0,
    },
    ("return_monitor", "accuracy_dropping"): {
        "module": "return_monitor",
        "metric": "accuracy_drop_sessions",
        "default": 3.0,
    },
    # dependency_monitor latency thresholds
    ("dependency_monitor", "llm_latency"): {
        "module": "dependency_monitor",
        "metric": "llm_healthy_threshold_ms",
        "default": 5000.0,
    },
    ("dependency_monitor", "tts_latency"): {
        "module": "dependency_monitor",
        "metric": "tts_healthy_threshold_ms",
        "default": 3000.0,
    },
    ("dependency_monitor", "stripe_latency"): {
        "module": "dependency_monitor",
        "metric": "stripe_healthy_threshold_ms",
        "default": 2000.0,
    },
    # analytics_auto_executor thresholds
    ("analytics_auto_executor", "bounce_rate_optimize"): {
        "module": "analytics_auto_executor",
        "metric": "high_bounce_threshold",
        "default": 0.75,
    },
    ("analytics_auto_executor", "channel_allocation"): {
        "module": "analytics_auto_executor",
        "metric": "channel_growth_threshold",
        "default": 0.30,
    },
    ("analytics_auto_executor", "seo_content_refresh"): {
        "module": "analytics_auto_executor",
        "metric": "content_freshness_days",
        "default": 90.0,
    },
    ("analytics_auto_executor", "min_traffic_gate"): {
        "module": "analytics_auto_executor",
        "metric": "min_traffic_for_action",
        "default": 20.0,
    },
    ("analytics_auto_executor", "signup_rate_drop"): {
        "module": "analytics_auto_executor",
        "metric": "signup_rate_drop_pct",
        "default": 20.0,
    },
    ("analytics_auto_executor", "organic_zero_traffic"): {
        "module": "analytics_auto_executor",
        "metric": "organic_zero_traffic_days",
        "default": 14.0,
    },
    # self_healing thresholds
    ("self_healing", "memory_check"): {
        "module": "self_healing",
        "metric": "memory_high_mb",
        "default": 512.0,
    },
    ("self_healing", "memory_critical"): {
        "module": "self_healing",
        "metric": "memory_critical_mb",
        "default": 768.0,
    },
    ("self_healing", "disk_check"): {
        "module": "self_healing",
        "metric": "disk_pressure_pct",
        "default": 90.0,
    },
    ("self_healing", "disk_critical"): {
        "module": "self_healing",
        "metric": "disk_critical_pct",
        "default": 95.0,
    },
    ("self_healing", "error_rate"): {
        "module": "self_healing",
        "metric": "error_rate_threshold",
        "default": 0.10,
    },
    ("self_healing", "slow_response"): {
        "module": "self_healing",
        "metric": "slow_response_ms",
        "default": 5000.0,
    },
}

# Maximum adjustment per calibration cycle (prevents runaway drift)
_MAX_INCREASE_FACTOR = 1.15   # +15%
_MAX_DECREASE_FACTOR = 0.85   # -15%

# Minimum sample size before we calibrate
_MIN_SAMPLE_SIZE = 10

# Success rate thresholds for calibration decisions
_TIGHTEN_BELOW = 0.50   # <50% success → make harder to trigger
_LOOSEN_ABOVE = 0.90    # >90% success → make easier to trigger


# ── Table creation ────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create calibration tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibrated_threshold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            metric TEXT NOT NULL,
            default_value REAL NOT NULL,
            calibrated_value REAL NOT NULL,
            calibration_reason TEXT,
            last_calibrated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(module, metric)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibration_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            module TEXT NOT NULL,
            metric TEXT NOT NULL,
            old_value REAL NOT NULL,
            new_value REAL NOT NULL,
            success_rate REAL,
            sample_size INTEGER,
            reason TEXT
        )
    """)
    conn.commit()


# ── Core API ──────────────────────────────────────────────────────────────

def get_threshold(
    conn: sqlite3.Connection,
    module: str,
    metric: str,
    default: float,
) -> float:
    """Return the calibrated threshold value, or the default if none exists.

    This is the function all modules should call instead of using hardcoded
    constants. It's a fast single-row lookup.

    Args:
        conn: database connection
        module: the module name (e.g., 'core_loop_monitor')
        metric: the metric name (e.g., 'session_completion_rate_min')
        default: the hardcoded default to fall back on

    Returns:
        The calibrated value if one exists, otherwise the default.
    """
    _ensure_tables(conn)
    row = _safe_query(conn, """
        SELECT calibrated_value FROM calibrated_threshold
        WHERE module = ? AND metric = ?
    """, (module, metric))
    if row and row[0] is not None:
        return float(row[0])
    return default


def calibrate_thresholds(conn: sqlite3.Connection) -> list[dict]:
    """Run the nightly calibration cycle.

    For each (module, action_type) combination in the outcome data:
    1. Query verified action outcomes from the last 30 days
    2. Compute success rate
    3. If success_rate < 50% with 10+ samples: tighten threshold (+10%, max +15%)
    4. If success_rate > 90% with 10+ samples: loosen threshold (-5%, max -15%)
    5. Log the adjustment

    The system uses pi_recommendation_outcome as the action ledger — each
    recorded outcome has an `effective` field: 1 = improved, 0 = neutral,
    -1 = regressed.

    Returns:
        List of adjustment dicts describing what changed.
    """
    _ensure_tables(conn)
    adjustments = []

    # ── Strategy 1: Use pi_recommendation_outcome (verified actions) ──
    # Group by (dimension as proxy for module, action_type)
    outcome_groups = _safe_query_all(conn, """
        SELECT
            pf.dimension,
            ro.action_type,
            COUNT(*) as total,
            SUM(CASE WHEN ro.effective = 1 THEN 1 ELSE 0 END) as improved,
            SUM(CASE WHEN ro.effective = -1 THEN 1 ELSE 0 END) as regressed,
            SUM(CASE WHEN ro.effective = 0 THEN 1 ELSE 0 END) as neutral
        FROM pi_recommendation_outcome ro
        JOIN pi_finding pf ON ro.finding_id = pf.id
        WHERE ro.verified_at IS NOT NULL
          AND ro.verified_at >= datetime('now', '-30 days')
        GROUP BY pf.dimension, ro.action_type
        HAVING total >= ?
    """, (_MIN_SAMPLE_SIZE,))

    for group in (outcome_groups or []):
        total = group["total"]
        improved = group["improved"] or 0
        regressed = group["regressed"] or 0
        success_rate = improved / max(total, 1)

        # Find matching threshold to adjust
        action_key = (group["dimension"], group["action_type"])
        threshold_info = _ACTION_TO_THRESHOLD.get(action_key)
        if not threshold_info:
            # Try to match by action_type alone (common pattern)
            for key, info in _ACTION_TO_THRESHOLD.items():
                if key[1] == group["action_type"]:
                    threshold_info = info
                    break
        if not threshold_info:
            continue

        module = threshold_info["module"]
        metric = threshold_info["metric"]
        default_val = threshold_info["default"]

        # Get current value
        current_val = get_threshold(conn, module, metric, default_val)

        # Decide adjustment direction
        new_val = current_val
        reason = None

        if success_rate < _TIGHTEN_BELOW:
            # Actions triggered by this threshold fail too often — tighten
            factor = 1.10
            new_val = current_val * min(factor, _MAX_INCREASE_FACTOR)
            reason = (
                f"Tightened: success rate {success_rate:.0%} < {_TIGHTEN_BELOW:.0%} "
                f"({improved}/{total} improved, {regressed} regressed)"
            )
        elif success_rate > _LOOSEN_ABOVE:
            # Actions almost always work — can trigger earlier
            factor = 0.95
            new_val = current_val * max(factor, _MAX_DECREASE_FACTOR)
            reason = (
                f"Loosened: success rate {success_rate:.0%} > {_LOOSEN_ABOVE:.0%} "
                f"({improved}/{total} improved)"
            )

        if reason and new_val != current_val:
            _apply_calibration(
                conn, module, metric, default_val,
                current_val, new_val, success_rate, total, reason,
            )
            adjustments.append({
                "module": module,
                "metric": metric,
                "old_value": round(current_val, 4),
                "new_value": round(new_val, 4),
                "success_rate": round(success_rate, 3),
                "sample_size": total,
                "reason": reason,
            })

    # ── Strategy 2: Use core_loop_action_log (direct action outcomes) ──
    # The core_loop_monitor logs actions with success=1/0
    core_loop_groups = _safe_query_all(conn, """
        SELECT
            metric_name,
            COUNT(*) as total,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
        FROM core_loop_action_log
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY metric_name
        HAVING total >= ?
    """, (_MIN_SAMPLE_SIZE,))

    for group in (core_loop_groups or []):
        total = group["total"]
        successes = group["successes"] or 0
        success_rate = successes / max(total, 1)

        # Map metric_name to threshold
        action_key = ("core_loop_monitor", group["metric_name"])
        threshold_info = _ACTION_TO_THRESHOLD.get(action_key)
        if not threshold_info:
            continue

        module = threshold_info["module"]
        metric = threshold_info["metric"]
        default_val = threshold_info["default"]
        current_val = get_threshold(conn, module, metric, default_val)

        new_val = current_val
        reason = None

        if success_rate < _TIGHTEN_BELOW:
            new_val = current_val * min(1.10, _MAX_INCREASE_FACTOR)
            reason = (
                f"Tightened (core_loop): success rate {success_rate:.0%} "
                f"({successes}/{total} succeeded)"
            )
        elif success_rate > _LOOSEN_ABOVE:
            new_val = current_val * max(0.95, _MAX_DECREASE_FACTOR)
            reason = (
                f"Loosened (core_loop): success rate {success_rate:.0%} "
                f"({successes}/{total} succeeded)"
            )

        if reason and new_val != current_val:
            # Avoid double-adjusting if already adjusted from strategy 1
            already = any(
                a["module"] == module and a["metric"] == metric
                for a in adjustments
            )
            if not already:
                _apply_calibration(
                    conn, module, metric, default_val,
                    current_val, new_val, success_rate, total, reason,
                )
                adjustments.append({
                    "module": module,
                    "metric": metric,
                    "old_value": round(current_val, 4),
                    "new_value": round(new_val, 4),
                    "success_rate": round(success_rate, 3),
                    "sample_size": total,
                    "reason": reason,
                })

    # ── Strategy 3: Use analytics_actions_log (analytics executor) ──
    analytics_groups = _safe_query_all(conn, """
        SELECT
            action_type,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) as applied,
            SUM(CASE WHEN status = 'reverted' THEN 1 ELSE 0 END) as reverted
        FROM analytics_actions_log
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY action_type
        HAVING total >= ?
    """, (_MIN_SAMPLE_SIZE,))

    for group in (analytics_groups or []):
        total = group["total"]
        applied = group["applied"] or 0
        reverted = group["reverted"] or 0
        # For analytics actions: reverted = failed, applied and not reverted = success
        success_rate = (applied - reverted) / max(total, 1)

        action_key = ("analytics_auto_executor", group["action_type"])
        threshold_info = _ACTION_TO_THRESHOLD.get(action_key)
        if not threshold_info:
            continue

        module = threshold_info["module"]
        metric = threshold_info["metric"]
        default_val = threshold_info["default"]
        current_val = get_threshold(conn, module, metric, default_val)

        new_val = current_val
        reason = None

        if success_rate < _TIGHTEN_BELOW:
            new_val = current_val * min(1.10, _MAX_INCREASE_FACTOR)
            reason = (
                f"Tightened (analytics): success rate {success_rate:.0%} "
                f"({reverted}/{total} reverted)"
            )
        elif success_rate > _LOOSEN_ABOVE:
            new_val = current_val * max(0.95, _MAX_DECREASE_FACTOR)
            reason = (
                f"Loosened (analytics): success rate {success_rate:.0%} "
                f"({applied}/{total} applied, {reverted} reverted)"
            )

        if reason and new_val != current_val:
            already = any(
                a["module"] == module and a["metric"] == metric
                for a in adjustments
            )
            if not already:
                _apply_calibration(
                    conn, module, metric, default_val,
                    current_val, new_val, success_rate, total, reason,
                )
                adjustments.append({
                    "module": module,
                    "metric": metric,
                    "old_value": round(current_val, 4),
                    "new_value": round(new_val, 4),
                    "success_rate": round(success_rate, 3),
                    "sample_size": total,
                    "reason": reason,
                })

    # ── Strategy 4: Use action_ledger (unified audit trail) ──────────
    # Covers self_healing, return_monitor, dependency_monitor, auto_executor
    ledger_groups = _safe_query_all(conn, """
        SELECT
            module,
            action_type,
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'improved' THEN 1 ELSE 0 END) as improved,
            SUM(CASE WHEN outcome = 'regressed' THEN 1 ELSE 0 END) as regressed
        FROM action_ledger
        WHERE outcome IS NOT NULL AND outcome != 'pending'
          AND verified_at >= datetime('now', '-30 days')
        GROUP BY module, action_type
        HAVING total >= ?
    """, (_MIN_SAMPLE_SIZE,))

    for group in (ledger_groups or []):
        total = group["total"]
        improved = group["improved"] or 0
        success_rate = improved / max(total, 1)

        action_key = (group["module"], group["action_type"])
        threshold_info = _ACTION_TO_THRESHOLD.get(action_key)
        if not threshold_info:
            continue

        module = threshold_info["module"]
        metric = threshold_info["metric"]
        default_val = threshold_info["default"]
        current_val = get_threshold(conn, module, metric, default_val)

        new_val = current_val
        reason = None

        if success_rate < _TIGHTEN_BELOW:
            new_val = current_val * min(1.10, _MAX_INCREASE_FACTOR)
            reason = (
                f"Tightened (ledger): success rate {success_rate:.0%} "
                f"({improved}/{total} improved, {group['regressed'] or 0} regressed)"
            )
        elif success_rate > _LOOSEN_ABOVE:
            new_val = current_val * max(0.95, _MAX_DECREASE_FACTOR)
            reason = (
                f"Loosened (ledger): success rate {success_rate:.0%} "
                f"({improved}/{total} improved)"
            )

        if reason and new_val != current_val:
            already = any(
                a["module"] == module and a["metric"] == metric
                for a in adjustments
            )
            if not already:
                _apply_calibration(
                    conn, module, metric, default_val,
                    current_val, new_val, success_rate, total, reason,
                )
                adjustments.append({
                    "module": module,
                    "metric": metric,
                    "old_value": round(current_val, 4),
                    "new_value": round(new_val, 4),
                    "success_rate": round(success_rate, 3),
                    "sample_size": total,
                    "reason": reason,
                })

    if adjustments:
        logger.info(
            "Calibration: %d threshold(s) adjusted — %s",
            len(adjustments),
            "; ".join(
                f"{a['module']}.{a['metric']}: {a['old_value']}->{a['new_value']}"
                for a in adjustments
            ),
        )
    else:
        logger.debug("Calibration: no adjustments needed (insufficient data or stable)")

    return adjustments


def get_calibration_history(
    conn: sqlite3.Connection,
    module: str | None = None,
    days: int = 30,
) -> list[dict]:
    """Return recent calibration adjustments.

    Args:
        conn: database connection
        module: filter to a specific module, or None for all
        days: lookback window

    Returns:
        List of calibration log entries, newest first.
    """
    _ensure_tables(conn)

    if module:
        rows = _safe_query_all(conn, """
            SELECT timestamp, module, metric, old_value, new_value,
                   success_rate, sample_size, reason
            FROM calibration_log
            WHERE module = ? AND timestamp >= datetime('now', ? || ' days')
            ORDER BY timestamp DESC
        """, (module, f"-{days}"))
    else:
        rows = _safe_query_all(conn, """
            SELECT timestamp, module, metric, old_value, new_value,
                   success_rate, sample_size, reason
            FROM calibration_log
            WHERE timestamp >= datetime('now', ? || ' days')
            ORDER BY timestamp DESC
        """, (f"-{days}",))

    return [dict(r) for r in rows] if rows else []


def get_calibration_summary(conn: sqlite3.Connection) -> dict:
    """Return a summary of all calibrated thresholds and recent activity.

    Used by the admin dashboard.
    """
    _ensure_tables(conn)

    # All current calibrations
    thresholds = _safe_query_all(conn, """
        SELECT module, metric, default_value, calibrated_value,
               calibration_reason, last_calibrated_at
        FROM calibrated_threshold
        ORDER BY last_calibrated_at DESC
    """)

    # Recent adjustments (last 7 days)
    recent = _safe_query_all(conn, """
        SELECT COUNT(*) as count,
               SUM(CASE WHEN new_value > old_value THEN 1 ELSE 0 END) as tightened,
               SUM(CASE WHEN new_value < old_value THEN 1 ELSE 0 END) as loosened
        FROM calibration_log
        WHERE timestamp >= datetime('now', '-7 days')
    """)

    recent_stats = dict(recent[0]) if recent else {
        "count": 0, "tightened": 0, "loosened": 0,
    }

    # Total calibrated vs total known thresholds
    total_calibrated = _safe_scalar(
        conn, "SELECT COUNT(*) FROM calibrated_threshold", default=0,
    )
    total_known = len(_ACTION_TO_THRESHOLD)

    return {
        "thresholds": [dict(r) for r in thresholds] if thresholds else [],
        "total_calibrated": total_calibrated,
        "total_known_thresholds": total_known,
        "coverage_pct": round(
            total_calibrated / max(total_known, 1) * 100, 1,
        ),
        "recent_7d": {
            "adjustments": recent_stats.get("count", 0) or 0,
            "tightened": recent_stats.get("tightened", 0) or 0,
            "loosened": recent_stats.get("loosened", 0) or 0,
        },
    }


# ── Internal helpers ──────────────────────────────────────────────────────

def _apply_calibration(
    conn: sqlite3.Connection,
    module: str,
    metric: str,
    default_value: float,
    old_value: float,
    new_value: float,
    success_rate: float,
    sample_size: int,
    reason: str,
) -> None:
    """Upsert calibrated_threshold and append to calibration_log."""
    try:
        conn.execute("""
            INSERT INTO calibrated_threshold
                (module, metric, default_value, calibrated_value,
                 calibration_reason, last_calibrated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(module, metric) DO UPDATE SET
                calibrated_value = excluded.calibrated_value,
                calibration_reason = excluded.calibration_reason,
                last_calibrated_at = excluded.last_calibrated_at
        """, (module, metric, default_value, new_value, reason))

        conn.execute("""
            INSERT INTO calibration_log
                (module, metric, old_value, new_value,
                 success_rate, sample_size, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (module, metric, old_value, new_value,
              success_rate, sample_size, reason))

        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Calibration: failed to apply adjustment: %s", exc)
