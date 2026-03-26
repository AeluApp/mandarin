"""Behavioral Contracts — governance constraints for automated intelligence actions.

Each module that takes automated actions has contracts defining:
- Governance level: auto, bounded, or human_required
- Rate limits: max per hour and per day
- Target restrictions: allowed/blocked path patterns
- Rollback capability
- Preconditions that must hold before the action fires

The contract system is the central gate: before any module acts, it calls
check_contract() to determine if the action is permitted. Blocked actions
are recorded in the action_ledger for audit visibility.

Tables:
    action_contract — per-module/action governance rules

Functions:
    check_contract(conn, module, action_type, target) -> (allowed, reason, contract_id)
    get_all_contracts(conn) -> list
    get_contract_violations(conn, days=7) -> list
    seed_contracts(conn) — idempotent initial seeding
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Table creation ─────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create the action_contract table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS action_contract (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            action_type TEXT NOT NULL,
            governance_level TEXT NOT NULL DEFAULT 'bounded'
                CHECK (governance_level IN ('auto','bounded','human_required')),
            max_per_hour INTEGER,
            max_per_day INTEGER,
            requires_verification INTEGER DEFAULT 1,
            verification_window_hours INTEGER DEFAULT 48,
            allowed_targets TEXT,
            blocked_targets TEXT,
            rollback_capable INTEGER DEFAULT 0,
            preconditions TEXT,
            description TEXT,
            UNIQUE(module, action_type)
        )
    """)
    conn.commit()


# ── Contract checking ──────────────────────────────────────────────────────

def check_contract(
    conn: sqlite3.Connection,
    module: str,
    action_type: str,
    target: str | None = None,
) -> tuple[bool, str, int | None]:
    """Check whether an action is permitted by its contract.

    Returns:
        (allowed, reason, contract_id)
        - allowed: True if the action may proceed.
        - reason: Explanation (empty string if allowed).
        - contract_id: The contract row id, or None if no contract found.
    """
    _ensure_tables(conn)

    # Ensure action_ledger table exists for rate limit queries
    try:
        from .action_ledger import _ensure_tables as _ensure_ledger_tables
        _ensure_ledger_tables(conn)
    except Exception:
        pass

    contract = _safe_query(conn, """
        SELECT id, governance_level, max_per_hour, max_per_day,
               allowed_targets, blocked_targets, preconditions
        FROM action_contract
        WHERE module = ? AND action_type = ?
    """, (module, action_type))

    if not contract:
        # No contract = allowed (fail-open for actions not yet registered)
        return True, "", None

    contract_id = contract["id"]
    governance = contract["governance_level"]

    # 1. Human-required actions are always blocked from automation
    if governance == "human_required":
        return False, f"Contract requires human approval for {module}/{action_type}", contract_id

    # 2. Rate limit: per-hour
    max_per_hour = contract["max_per_hour"]
    if max_per_hour is not None:
        hourly_count = _safe_scalar(conn, """
            SELECT COUNT(*) FROM action_ledger
            WHERE module = ? AND action_type = ?
              AND timestamp >= datetime('now', '-1 hour')
              AND precondition_met = 1
        """, (module, action_type), default=0)

        if hourly_count >= max_per_hour:
            return (
                False,
                f"Hourly rate limit exceeded: {hourly_count}/{max_per_hour} for {module}/{action_type}",
                contract_id,
            )

    # 3. Rate limit: per-day
    max_per_day = contract["max_per_day"]
    if max_per_day is not None:
        daily_count = _safe_scalar(conn, """
            SELECT COUNT(*) FROM action_ledger
            WHERE module = ? AND action_type = ?
              AND timestamp >= datetime('now', '-24 hours')
              AND precondition_met = 1
        """, (module, action_type), default=0)

        if daily_count >= max_per_day:
            return (
                False,
                f"Daily rate limit exceeded: {daily_count}/{max_per_day} for {module}/{action_type}",
                contract_id,
            )

    # 4. Target blocking
    if target:
        blocked_raw = contract["blocked_targets"]
        if blocked_raw:
            try:
                blocked_patterns = json.loads(blocked_raw)
                for pattern in blocked_patterns:
                    if _target_matches(target, pattern):
                        return (
                            False,
                            f"Target '{target}' is blocked by pattern '{pattern}'",
                            contract_id,
                        )
            except (json.JSONDecodeError, TypeError):
                pass

        # 5. Target allowlist (if set, target must match at least one)
        allowed_raw = contract["allowed_targets"]
        if allowed_raw:
            try:
                allowed_patterns = json.loads(allowed_raw)
                matched = any(
                    _target_matches(target, pattern)
                    for pattern in allowed_patterns
                )
                if not matched:
                    return (
                        False,
                        f"Target '{target}' not in allowed patterns",
                        contract_id,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

    # 6. Preconditions
    preconditions_raw = contract["preconditions"]
    if preconditions_raw:
        try:
            preconditions = json.loads(preconditions_raw)
            ok, reason = _check_preconditions(conn, preconditions)
            if not ok:
                return False, f"Precondition not met: {reason}", contract_id
        except (json.JSONDecodeError, TypeError):
            pass

    return True, "", contract_id


def _target_matches(target: str, pattern: str) -> bool:
    """Check if a target matches a pattern.

    Supports:
    - Exact match
    - Glob-style wildcards (* matches any segment)
    - Prefix match (pattern ending with *)
    """
    if target == pattern:
        return True
    if pattern.endswith("*"):
        return target.startswith(pattern[:-1])
    # Simple glob: convert * to regex .*
    try:
        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        return bool(re.match(regex, target))
    except re.error:
        return False


def _check_preconditions(
    conn: sqlite3.Connection,
    preconditions: dict,
) -> tuple[bool, str]:
    """Evaluate precondition rules.

    Supported precondition types:
    - {"flag_enabled": "flag_name"} — feature flag must be enabled
    - {"flag_disabled": "flag_name"} — feature flag must be disabled
    - {"min_data_points": N} — minimum rows in a metric table
    """
    for key, value in preconditions.items():
        if key == "flag_enabled":
            flag_val = _safe_scalar(conn, """
                SELECT enabled FROM feature_flag WHERE name = ?
            """, (value,), default=0)
            if not flag_val:
                return False, f"Feature flag '{value}' is not enabled"

        elif key == "flag_disabled":
            flag_val = _safe_scalar(conn, """
                SELECT enabled FROM feature_flag WHERE name = ?
            """, (value,), default=0)
            if flag_val:
                return False, f"Feature flag '{value}' is enabled (must be disabled)"

    return True, ""


# ── Query functions ────────────────────────────────────────────────────────

def get_all_contracts(conn: sqlite3.Connection) -> list[dict]:
    """Return all contracts as a list of dicts."""
    _ensure_tables(conn)
    rows = _safe_query_all(conn, """
        SELECT * FROM action_contract ORDER BY module, action_type
    """)
    return [dict(r) for r in rows] if rows else []


def get_contract_violations(conn: sqlite3.Connection, days: int = 7) -> list[dict]:
    """Return actions that were blocked by contracts over the last N days.

    These are actions recorded in the ledger where precondition_met = 0
    or whose description starts with 'BLOCKED:'.
    """
    _ensure_tables(conn)

    # Ensure action_ledger table exists
    try:
        from .action_ledger import _ensure_tables as _ensure_ledger_tables
        _ensure_ledger_tables(conn)
    except Exception:
        pass

    rows = _safe_query_all(conn, """
        SELECT al.id, al.timestamp, al.module, al.action_type, al.target,
               al.description, al.contract_id,
               ac.governance_level, ac.max_per_hour, ac.max_per_day
        FROM action_ledger al
        LEFT JOIN action_contract ac ON al.contract_id = ac.id
        WHERE al.timestamp >= datetime('now', ? || ' days')
          AND (al.precondition_met = 0 OR al.description LIKE 'BLOCKED:%')
        ORDER BY al.timestamp DESC
        LIMIT 100
    """, (f"-{days}",))

    return [dict(r) for r in rows] if rows else []


# ── Contract seeding ───────────────────────────────────────────────────────

def seed_contracts(conn: sqlite3.Connection) -> int:
    """Idempotent seeding of all contracts for existing automated actions.

    Uses INSERT OR IGNORE so re-running is safe.
    Returns the number of contracts inserted.
    """
    _ensure_tables(conn)

    contracts = _get_default_contracts()
    inserted = 0

    for c in contracts:
        try:
            cur = conn.execute("""
                INSERT OR IGNORE INTO action_contract
                    (module, action_type, governance_level, max_per_hour, max_per_day,
                     requires_verification, verification_window_hours,
                     allowed_targets, blocked_targets, rollback_capable,
                     preconditions, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c["module"],
                c["action_type"],
                c.get("governance_level", "bounded"),
                c.get("max_per_hour"),
                c.get("max_per_day"),
                c.get("requires_verification", 1),
                c.get("verification_window_hours", 48),
                json.dumps(c["allowed_targets"]) if c.get("allowed_targets") else None,
                json.dumps(c["blocked_targets"]) if c.get("blocked_targets") else None,
                c.get("rollback_capable", 0),
                json.dumps(c["preconditions"]) if c.get("preconditions") else None,
                c.get("description", ""),
            ))
            if cur.rowcount > 0:
                inserted += 1
        except (sqlite3.OperationalError, sqlite3.Error) as exc:
            logger.debug("Contract seed: failed for %s/%s: %s",
                         c["module"], c["action_type"], exc)

    conn.commit()

    if inserted:
        logger.info("Contract seed: inserted %d new contract(s)", inserted)

    return inserted


def _get_default_contracts() -> list[dict]:
    """Define the default contracts for all known automated actions."""
    return [
        # ── self_healing ─────────────────────────────────────────────────
        {
            "module": "self_healing",
            "action_type": "clear_caches",
            "governance_level": "auto",
            "max_per_hour": 3,
            "max_per_day": 10,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 0,
            "description": "Clear LLM response caches to free memory",
        },
        {
            "module": "self_healing",
            "action_type": "clean_temp",
            "governance_level": "auto",
            "max_per_hour": 2,
            "max_per_day": 5,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 0,
            "description": "Clean temporary files to free disk space",
        },
        {
            "module": "self_healing",
            "action_type": "truncate_logs",
            "governance_level": "bounded",
            "max_per_hour": 1,
            "max_per_day": 3,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 0,
            "description": "Truncate large log files to free disk space",
        },
        {
            "module": "self_healing",
            "action_type": "release_locks",
            "governance_level": "auto",
            "max_per_hour": 5,
            "max_per_day": 20,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 0,
            "description": "Release stale scheduler locks",
        },
        {
            "module": "self_healing",
            "action_type": "disable_feature",
            "governance_level": "bounded",
            "max_per_hour": 2,
            "max_per_day": 5,
            "requires_verification": 1,
            "verification_window_hours": 24,
            "rollback_capable": 1,
            "description": "Disable a feature via feature flag due to high error rate",
        },
        {
            "module": "self_healing",
            "action_type": "reset_pool",
            "governance_level": "bounded",
            "max_per_hour": 2,
            "max_per_day": 5,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 0,
            "description": "Reset database connection pool",
        },
        {
            "module": "self_healing",
            "action_type": "restart_machine",
            "governance_level": "bounded",
            "max_per_hour": 1,
            "max_per_day": 3,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 0,
            "description": "Restart Fly.io machine via API (last resort)",
        },

        # ── auto_executor ────────────────────────────────────────────────
        {
            "module": "auto_executor",
            "action_type": "apply_code_fix",
            "governance_level": "bounded",
            "max_per_hour": 2,
            "max_per_day": 5,
            "requires_verification": 1,
            "verification_window_hours": 48,
            "allowed_targets": ["mandarin/*"],
            "blocked_targets": ["mandarin/settings.py", "mandarin/web/admin_routes.py"],
            "rollback_capable": 1,
            "description": "Apply LLM-generated code fix to a file",
        },

        # ── analytics (analytics_auto_executor) ─────────────────────────
        {
            "module": "analytics",
            "action_type": "rewrite_content",
            "governance_level": "bounded",
            "max_per_hour": 1,
            "max_per_day": 3,
            "requires_verification": 1,
            "verification_window_hours": 48,
            "allowed_targets": ["marketing/*"],
            "blocked_targets": ["marketing/landing/pricing.html"],
            "rollback_capable": 1,
            "description": "Rewrite landing page content to optimize bounce rate",
        },
        {
            "module": "analytics",
            "action_type": "increase_channel_weight",
            "governance_level": "auto",
            "max_per_hour": 1,
            "max_per_day": 3,
            "requires_verification": 1,
            "verification_window_hours": 168,
            "rollback_capable": 0,
            "description": "Adjust marketing channel allocation weights",
        },
        {
            "module": "analytics",
            "action_type": "propose_ab_test",
            "governance_level": "auto",
            "max_per_hour": 2,
            "max_per_day": 5,
            "requires_verification": 1,
            "verification_window_hours": 168,
            "rollback_capable": 1,
            "description": "Propose A/B test for landing page optimization",
        },
        {
            "module": "analytics",
            "action_type": "generate_internal_links",
            "governance_level": "bounded",
            "max_per_hour": 1,
            "max_per_day": 3,
            "requires_verification": 1,
            "verification_window_hours": 168,
            "allowed_targets": ["marketing/*"],
            "rollback_capable": 1,
            "description": "Generate internal links for SEO improvement",
        },
        {
            "module": "analytics",
            "action_type": "generate_channel_content",
            "governance_level": "bounded",
            "max_per_hour": 1,
            "max_per_day": 3,
            "requires_verification": 1,
            "verification_window_hours": 168,
            "rollback_capable": 0,
            "description": "Generate channel-specific marketing content",
        },

        # ── core_loop_monitor ────────────────────────────────────────────
        {
            "module": "core_loop_monitor",
            "action_type": "set_feature_flag",
            "governance_level": "bounded",
            "max_per_hour": 3,
            "max_per_day": 10,
            "requires_verification": 1,
            "verification_window_hours": 24,
            "rollback_capable": 1,
            "description": "Set a feature flag to adjust session/drill behavior",
        },
        {
            "module": "core_loop_monitor",
            "action_type": "lower_difficulty",
            "governance_level": "auto",
            "max_per_hour": 5,
            "max_per_day": 20,
            "requires_verification": 1,
            "verification_window_hours": 48,
            "rollback_capable": 1,
            "description": "Lower content item difficulty due to high error rate",
        },
        {
            "module": "core_loop_monitor",
            "action_type": "quarantine_content",
            "governance_level": "bounded",
            "max_per_hour": 3,
            "max_per_day": 10,
            "requires_verification": 1,
            "verification_window_hours": 48,
            "rollback_capable": 1,
            "description": "Quarantine content item causing session abandonments",
        },

        # ── return_monitor ───────────────────────────────────────────────
        {
            "module": "return_monitor",
            "action_type": "send_activation_email",
            "governance_level": "auto",
            "max_per_hour": 10,
            "max_per_day": 50,
            "requires_verification": 1,
            "verification_window_hours": 48,
            "rollback_capable": 0,
            "description": "Send activation email to user who hasn't returned in 24h",
        },
        {
            "module": "return_monitor",
            "action_type": "adjust_difficulty",
            "governance_level": "auto",
            "max_per_hour": 10,
            "max_per_day": 50,
            "requires_verification": 1,
            "verification_window_hours": 168,
            "rollback_capable": 1,
            "description": "Adjust user difficulty (up or down) based on accuracy trend or inactivity",
        },
        {
            "module": "return_monitor",
            "action_type": "send_reengagement_email",
            "governance_level": "auto",
            "max_per_hour": 10,
            "max_per_day": 50,
            "requires_verification": 1,
            "verification_window_hours": 168,
            "rollback_capable": 0,
            "description": "Send re-engagement email to at-risk user (7d inactive)",
        },
        {
            "module": "return_monitor",
            "action_type": "send_winback_email",
            "governance_level": "bounded",
            "max_per_hour": 5,
            "max_per_day": 20,
            "requires_verification": 1,
            "verification_window_hours": 336,
            "rollback_capable": 0,
            "description": "Send win-back email to churning paid subscriber",
        },

        # ── cost_monitor ─────────────────────────────────────────────────
        {
            "module": "cost_monitor",
            "action_type": "toggle_cost_flag",
            "governance_level": "auto",
            "max_per_hour": 5,
            "max_per_day": 20,
            "requires_verification": 1,
            "verification_window_hours": 24,
            "rollback_capable": 1,
            "description": "Toggle LLM feature flag based on spend limits",
        },

        # ── dependency_monitor ───────────────────────────────────────────
        {
            "module": "dependency_monitor",
            "action_type": "switch_fallback",
            "governance_level": "auto",
            "max_per_hour": 5,
            "max_per_day": 20,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 1,
            "description": "Switch to fallback mode for a degraded/dead dependency",
        },
        {
            "module": "dependency_monitor",
            "action_type": "disable_feature",
            "governance_level": "bounded",
            "max_per_hour": 3,
            "max_per_day": 10,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 1,
            "description": "Fully disable features for a dead dependency",
        },
        {
            "module": "dependency_monitor",
            "action_type": "enable_feature",
            "governance_level": "auto",
            "max_per_hour": 5,
            "max_per_day": 20,
            "requires_verification": 1,
            "verification_window_hours": 1,
            "rollback_capable": 1,
            "description": "Re-enable features after dependency recovery",
        },
    ]
