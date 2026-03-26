"""LLM cost monitoring and enforcement — spend tracking with automatic kill-switches.

Queries the llm_cost_log table (populated by ollama_client._log_cost()) and
enforces daily/monthly spend limits by toggling feature flags.  When a limit
is breached, non-essential LLM capabilities are progressively disabled:

    daily  > $2  (soft)  -> disable content_generation
    daily  > $5  (hard)  -> disable core_learning (except grading)
    monthly > $25 (soft) -> disable content_generation + marketing
    monthly > $50 (hard) -> disable ALL + email CRITICAL alert

Feature flags managed:
    llm_content_generation_enabled
    llm_core_learning_enabled
    llm_marketing_enabled

Auto-recovery: on the 1st of each month, re-enable all flags if monthly
spend is back under soft limit.

Exports:
    get_daily_spend(conn) -> float
    get_monthly_spend(conn) -> float
    check_and_enforce_limits(conn) -> dict
    is_task_allowed(conn, task_type) -> bool
    auto_recover_monthly(conn) -> dict
    get_cost_summary(conn) -> dict
    run_cost_check(conn) -> dict
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, UTC

from ..feature_flags import is_enabled, set_flag
from ..settings import (
    ADMIN_EMAIL,
    LLM_DAILY_SOFT_LIMIT,
    LLM_DAILY_HARD_LIMIT,
    LLM_MONTHLY_SOFT_LIMIT,
    LLM_MONTHLY_HARD_LIMIT,
)

logger = logging.getLogger(__name__)

# ── Task classification ──────────────────────────────────────────────────

# core_learning: tasks essential for the student learning loop
_CORE_LEARNING_TASKS = frozenset({
    "conversation_eval", "conversation_followup", "drill_generation",
    "error_explanation", "reading_generation", "reading_generation_retry",
    "openclaw_intent", "openclaw_chat", "voice_audit",
    "interference_detection", "classify_prescription",
})

# Grading is always allowed even when core_learning is disabled
_GRADING_TASKS = frozenset({
    "conversation_eval",
})

# content_generation: background content creation
_CONTENT_GENERATION_TASKS = frozenset({
    "reading_generation", "reading_generation_retry",
    "experiment_design", "agent_plan",
})

# marketing: marketing-related LLM tasks
_MARKETING_TASKS = frozenset({
    "copy_drift_review", "editorial_critic", "aesthetic_quality_evaluation",
})

# Feature flag names
_FLAG_CONTENT_GEN = "llm_content_generation_enabled"
_FLAG_CORE_LEARNING = "llm_core_learning_enabled"
_FLAG_MARKETING = "llm_marketing_enabled"

_ALL_FLAGS = [_FLAG_CONTENT_GEN, _FLAG_CORE_LEARNING, _FLAG_MARKETING]


def _classify_task(task_type: str) -> str:
    """Classify a task_type into a spending category."""
    if task_type in _MARKETING_TASKS:
        return "marketing"
    if task_type in _CONTENT_GENERATION_TASKS:
        return "content_generation"
    if task_type in _CORE_LEARNING_TASKS:
        return "core_learning"
    return "other"


# ── Spend queries ────────────────────────────────────────────────────────

def get_daily_spend(conn: sqlite3.Connection) -> float:
    """Total LLM spend (USD) for today."""
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_cost_log WHERE date(created_at) = date('now')"
        ).fetchone()
        return float(row[0]) if row else 0.0
    except sqlite3.OperationalError:
        return 0.0


def get_monthly_spend(conn: sqlite3.Connection) -> float:
    """Total LLM spend (USD) for the current calendar month."""
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_cost_log "
            "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
        ).fetchone()
        return float(row[0]) if row else 0.0
    except sqlite3.OperationalError:
        return 0.0


def _get_spend_by_category(conn: sqlite3.Connection, period: str = "day") -> dict:
    """Breakdown of spend by task category for the given period.

    period: 'day' or 'month'
    """
    if period == "day":
        where = "date(created_at) = date('now')"
    else:
        where = "strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"

    try:
        rows = conn.execute(
            f"SELECT task_type, COALESCE(SUM(cost_usd), 0) as total "
            f"FROM llm_cost_log WHERE {where} GROUP BY task_type"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    breakdown = {"core_learning": 0.0, "content_generation": 0.0, "marketing": 0.0, "other": 0.0}
    for row in rows:
        category = _classify_task(row["task_type"] if isinstance(row, sqlite3.Row) else row[0])
        cost = float(row["total"] if isinstance(row, sqlite3.Row) else row[1])
        breakdown[category] += cost
    return breakdown


# ── Limit enforcement (the kill-switch) ──────────────────────────────────

def _gov_check_cost(conn, target=None):
    """Check contract governance for a cost monitor action. Non-fatal."""
    try:
        from .contracts import check_contract
        return check_contract(conn, "cost_monitor", "toggle_cost_flag", target)
    except Exception:
        return True, "", None


def _gov_record_cost(conn, target, description, metrics_before, verification_hours=24, contract_id=None):
    """Record to unified action ledger. Non-fatal."""
    try:
        from .action_ledger import record_action
        record_action(conn, "cost_monitor", "toggle_cost_flag", target, description,
                       metrics_before, verification_hours=verification_hours, contract_id=contract_id)
    except Exception:
        pass


def check_and_enforce_limits(conn: sqlite3.Connection) -> dict:
    """Check spend against limits and toggle feature flags accordingly.

    Returns a dict describing what was checked and any actions taken.
    """
    daily = get_daily_spend(conn)
    monthly = get_monthly_spend(conn)
    actions = []

    # Governance check (done once — cost monitor actions share one contract)
    allowed, reason, cid = _gov_check_cost(conn)
    if not allowed:
        logger.info("Contract blocked cost_monitor/toggle_cost_flag: %s", reason)
        _gov_record_cost(conn, None, f"BLOCKED: {reason}", None, contract_id=cid)
        return {
            "daily_spend": daily,
            "monthly_spend": monthly,
            "daily_soft_limit": LLM_DAILY_SOFT_LIMIT,
            "daily_hard_limit": LLM_DAILY_HARD_LIMIT,
            "monthly_soft_limit": LLM_MONTHLY_SOFT_LIMIT,
            "monthly_hard_limit": LLM_MONTHLY_HARD_LIMIT,
            "actions": [f"BLOCKED by contract: {reason}"],
        }

    cost_metrics = {"daily_spend": daily, "monthly_spend": monthly}

    # Daily soft limit: disable content generation
    if daily > LLM_DAILY_SOFT_LIMIT:
        if _ensure_flag_disabled(conn, _FLAG_CONTENT_GEN):
            desc = f"daily ${daily:.2f} > ${LLM_DAILY_SOFT_LIMIT:.2f}: disabled content_generation"
            actions.append(desc)
            _gov_record_cost(conn, _FLAG_CONTENT_GEN, desc, cost_metrics, contract_id=cid)

    # Daily hard limit: disable core learning (except grading)
    if daily > LLM_DAILY_HARD_LIMIT:
        if _ensure_flag_disabled(conn, _FLAG_CORE_LEARNING):
            desc = f"daily ${daily:.2f} > ${LLM_DAILY_HARD_LIMIT:.2f}: disabled core_learning"
            actions.append(desc)
            _gov_record_cost(conn, _FLAG_CORE_LEARNING, desc, cost_metrics, contract_id=cid)

    # Monthly soft limit: disable content generation + marketing
    if monthly > LLM_MONTHLY_SOFT_LIMIT:
        if _ensure_flag_disabled(conn, _FLAG_CONTENT_GEN):
            desc = f"monthly ${monthly:.2f} > ${LLM_MONTHLY_SOFT_LIMIT:.2f}: disabled content_generation"
            actions.append(desc)
            _gov_record_cost(conn, _FLAG_CONTENT_GEN, desc, cost_metrics, contract_id=cid)
        if _ensure_flag_disabled(conn, _FLAG_MARKETING):
            desc = f"monthly ${monthly:.2f} > ${LLM_MONTHLY_SOFT_LIMIT:.2f}: disabled marketing"
            actions.append(desc)
            _gov_record_cost(conn, _FLAG_MARKETING, desc, cost_metrics, contract_id=cid)

    # Monthly hard limit: disable ALL + send critical alert
    if monthly > LLM_MONTHLY_HARD_LIMIT:
        for flag in _ALL_FLAGS:
            _ensure_flag_disabled(conn, flag)
        desc = f"monthly ${monthly:.2f} > ${LLM_MONTHLY_HARD_LIMIT:.2f}: disabled ALL LLM"
        actions.append(desc)
        _gov_record_cost(conn, "ALL_FLAGS", desc, cost_metrics, contract_id=cid)
        _send_critical_cost_alert(daily, monthly)

    # Auto-recover: if under limits, re-enable flags
    if daily <= LLM_DAILY_SOFT_LIMIT and monthly <= LLM_MONTHLY_SOFT_LIMIT:
        for flag in _ALL_FLAGS:
            if _ensure_flag_enabled(conn, flag):
                desc = f"spend under limits: re-enabled {flag}"
                actions.append(desc)
                _gov_record_cost(conn, flag, desc, cost_metrics, contract_id=cid)

    elif daily <= LLM_DAILY_HARD_LIMIT and monthly <= LLM_MONTHLY_SOFT_LIMIT:
        # Only re-enable core_learning if daily is under hard limit
        if _ensure_flag_enabled(conn, _FLAG_CORE_LEARNING):
            desc = f"daily under hard limit: re-enabled core_learning"
            actions.append(desc)
            _gov_record_cost(conn, _FLAG_CORE_LEARNING, desc, cost_metrics, contract_id=cid)

    if actions:
        logger.info("Cost monitor actions: %s", "; ".join(actions))

    return {
        "daily_spend": daily,
        "monthly_spend": monthly,
        "daily_soft_limit": LLM_DAILY_SOFT_LIMIT,
        "daily_hard_limit": LLM_DAILY_HARD_LIMIT,
        "monthly_soft_limit": LLM_MONTHLY_SOFT_LIMIT,
        "monthly_hard_limit": LLM_MONTHLY_HARD_LIMIT,
        "actions": actions,
    }


def _ensure_flag_disabled(conn: sqlite3.Connection, flag_name: str) -> bool:
    """Disable a flag if it is currently enabled. Returns True if changed."""
    if is_enabled(conn, flag_name):
        set_flag(conn, flag_name, enabled=False,
                 description=f"Auto-disabled by cost monitor at {datetime.now(UTC).isoformat()}")
        return True
    return False


def _ensure_flag_enabled(conn: sqlite3.Connection, flag_name: str) -> bool:
    """Enable a flag if it is currently disabled. Returns True if changed."""
    if not is_enabled(conn, flag_name):
        set_flag(conn, flag_name, enabled=True,
                 description=f"Auto-recovered by cost monitor at {datetime.now(UTC).isoformat()}")
        return True
    return False


def _send_critical_cost_alert(daily: float, monthly: float) -> None:
    """Email and message admin about critical cost breach."""
    alert_details = (
        f"Monthly LLM spend: ${monthly:.2f} (hard limit: ${LLM_MONTHLY_HARD_LIMIT:.2f})\n"
        f"Daily LLM spend: ${daily:.2f}\n\n"
        f"ALL LLM features have been automatically disabled.\n"
        f"Review spend at /admin and re-enable manually if appropriate."
    )

    # Email notification
    try:
        from ..email import send_alert
        to = ADMIN_EMAIL or "hello@aeluapp.com"
        send_alert(
            to,
            subject="CRITICAL: LLM monthly spend exceeded hard limit",
            details=alert_details,
        )
    except Exception:
        logger.exception("Failed to send critical cost alert email")

    # Matrix / Beeper notification
    try:
        from ..notifications.matrix_client import send_alert as matrix_alert
        matrix_alert(
            subject="CRITICAL: LLM monthly spend exceeded hard limit",
            details=alert_details,
        )
    except Exception:
        logger.exception("Failed to send critical cost alert via Matrix")


# ── Pre-call gate ────────────────────────────────────────────────────────

def is_task_allowed(conn: sqlite3.Connection, task_type: str) -> bool:
    """Check whether a given LLM task is currently allowed under cost limits.

    Called before each LLM invocation. Grading tasks are always allowed.
    """
    # Grading is exempt from all cost gates
    if task_type in _GRADING_TASKS:
        return True

    category = _classify_task(task_type)

    if category == "content_generation":
        return is_enabled(conn, _FLAG_CONTENT_GEN)
    elif category == "marketing":
        return is_enabled(conn, _FLAG_MARKETING)
    elif category == "core_learning":
        return is_enabled(conn, _FLAG_CORE_LEARNING)

    # "other" tasks follow core_learning flag
    return is_enabled(conn, _FLAG_CORE_LEARNING)


# ── Monthly auto-recovery ────────────────────────────────────────────────

def auto_recover_monthly(conn: sqlite3.Connection) -> dict:
    """Re-enable all LLM flags on the 1st of the month if spend is under soft limit.

    Should be called from the health check loop.
    """
    now = datetime.now(UTC)
    if now.day != 1:
        return {"action": "skipped", "reason": "not the 1st of the month"}

    monthly = get_monthly_spend(conn)
    if monthly <= LLM_MONTHLY_SOFT_LIMIT:
        recovered = []
        for flag in _ALL_FLAGS:
            if _ensure_flag_enabled(conn, flag):
                recovered.append(flag)
        if recovered:
            logger.info("Monthly auto-recovery: re-enabled %s", recovered)
        return {"action": "recovered", "flags": recovered, "monthly_spend": monthly}

    return {"action": "skipped", "reason": f"monthly spend ${monthly:.2f} still above soft limit"}


# ── Admin API summary ────────────────────────────────────────────────────

def get_cost_summary(conn: sqlite3.Connection) -> dict:
    """Build a JSON-serializable cost summary for the admin dashboard."""
    daily = get_daily_spend(conn)
    monthly = get_monthly_spend(conn)
    daily_breakdown = _get_spend_by_category(conn, "day")
    monthly_breakdown = _get_spend_by_category(conn, "month")

    # Flag statuses
    flags = {}
    for flag in _ALL_FLAGS:
        flags[flag] = is_enabled(conn, flag)

    # Recent high-cost calls (top 10 today)
    recent_calls = []
    try:
        rows = conn.execute(
            "SELECT model, task_type, prompt_tokens, completion_tokens, cost_usd, created_at "
            "FROM llm_cost_log WHERE date(created_at) = date('now') "
            "ORDER BY cost_usd DESC LIMIT 10"
        ).fetchall()
        recent_calls = [dict(r) for r in rows]
    except sqlite3.OperationalError:
        pass

    # Daily trend (last 30 days)
    daily_trend = []
    try:
        rows = conn.execute(
            "SELECT date(created_at) as day, COALESCE(SUM(cost_usd), 0) as total, COUNT(*) as calls "
            "FROM llm_cost_log WHERE created_at >= datetime('now', '-30 days') "
            "GROUP BY date(created_at) ORDER BY day"
        ).fetchall()
        daily_trend = [dict(r) for r in rows]
    except sqlite3.OperationalError:
        pass

    return {
        "daily_spend": round(daily, 4),
        "monthly_spend": round(monthly, 4),
        "daily_breakdown": {k: round(v, 4) for k, v in daily_breakdown.items()},
        "monthly_breakdown": {k: round(v, 4) for k, v in monthly_breakdown.items()},
        "limits": {
            "daily_soft": LLM_DAILY_SOFT_LIMIT,
            "daily_hard": LLM_DAILY_HARD_LIMIT,
            "monthly_soft": LLM_MONTHLY_SOFT_LIMIT,
            "monthly_hard": LLM_MONTHLY_HARD_LIMIT,
        },
        "flags": flags,
        "recent_high_cost_calls": recent_calls,
        "daily_trend_30d": daily_trend,
    }


# ── Health check entry point ─────────────────────────────────────────────

def run_cost_check(conn: sqlite3.Connection) -> dict:
    """Entry point for the health check scheduler.

    Runs limit enforcement and monthly auto-recovery.
    """
    result = check_and_enforce_limits(conn)
    recovery = auto_recover_monthly(conn)
    result["monthly_recovery"] = recovery
    return result
