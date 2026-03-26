"""Return Monitor — track whether users return and auto-intervene.

Not just measuring — acting. When users show signs of disengagement,
this module executes specific interventions:

Rules:
- completed_session + no_return_24h -> auto-send activation email
- completed_session + no_return_48h -> auto-adjust difficulty down 10%
- completed_3_sessions + no_return_7d -> mark at_risk, queue re-engagement
- subscribed + no_session_14d -> mark churning, queue win-back email
- accuracy_dropping_3_sessions -> auto-reduce content difficulty
- accuracy_rising_3_sessions -> auto-increase content difficulty

All actions are deduplicated via lifecycle_event to prevent spamming.

Exports:
    run_check(conn) -> dict
    ANALYZERS: list of analyzer functions for the intelligence engine
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, UTC

from ._base import _safe_query, _safe_query_all, _safe_scalar, _finding

logger = logging.getLogger(__name__)


# ── Table creation ────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create return monitoring tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS return_monitor_action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            user_id INTEGER NOT NULL,
            rule_name TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            details TEXT,
            success INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_return_action_user_rule
        ON return_monitor_action_log(user_id, rule_name, created_at)
    """)
    conn.commit()


def _action_already_taken(conn, user_id: int, rule_name: str, within_hours: int = 72) -> bool:
    """Check if this action was already taken for this user recently.

    Uses both return_monitor_action_log and lifecycle_event for dedup.
    """
    # Check our own action log
    count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM return_monitor_action_log
        WHERE user_id = ? AND rule_name = ?
          AND created_at >= datetime('now', ? || ' hours')
    """, (user_id, rule_name, f"-{within_hours}"), default=0)
    if count > 0:
        return True

    # Also check lifecycle_event for email_triggered events
    count2 = _safe_scalar(conn, """
        SELECT COUNT(*) FROM lifecycle_event
        WHERE user_id = ? AND event_type = ?
          AND created_at >= datetime('now', ? || ' hours')
    """, (user_id, f"return_monitor_{rule_name}", f"-{within_hours}"), default=0)

    return count2 > 0


def _log_action(conn, user_id: int, rule_name: str, action_taken: str,
                details: dict = None, success: bool = True) -> None:
    """Log an action to both action_log and lifecycle_event."""
    try:
        conn.execute("""
            INSERT INTO return_monitor_action_log
                (user_id, rule_name, action_taken, details, success)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, rule_name, action_taken,
              json.dumps(details) if details else None,
              1 if success else 0))
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Return monitor: failed to log action: %s", exc)

    # Also log as lifecycle event for the marketing system
    try:
        from ..marketing_hooks import log_lifecycle_event
        log_lifecycle_event(
            f"return_monitor_{rule_name}",
            user_id=str(user_id),
            conn=conn,
            action=action_taken,
            **(details or {}),
        )
    except Exception:
        pass


def _notify_admin_summary(actions: list[dict]) -> None:
    """Send summary email to admin about return monitor actions."""
    if not actions:
        return
    try:
        from ..settings import ADMIN_EMAIL
        if not ADMIN_EMAIL:
            return
        from ..email import send_alert
        lines = []
        for a in actions:
            lines.append(f"- User #{a['user_id']}: {a['action']} ({a['rule']})")
        send_alert(
            to_email=ADMIN_EMAIL,
            subject=f"[Aelu Return Monitor] {len(actions)} action(s) taken",
            details="\n".join(lines),
        )
    except Exception as exc:
        logger.debug("Return monitor: admin notification failed: %s", exc)


# ── User queries ──────────────────────────────────────────────────────────

def _get_users_no_return_24h(conn) -> list[dict]:
    """Users who completed a session 24-48h ago and haven't returned.

    Excludes admin users and users who opted out of marketing.
    """
    rows = _safe_query_all(conn, """
        SELECT u.id as user_id, u.email, u.display_name
        FROM user u
        JOIN learner_profile lp ON u.id = lp.user_id
        WHERE u.is_admin = 0
          AND u.is_active = 1
          AND u.marketing_opt_out = 0
          AND lp.last_session_date IS NOT NULL
          AND lp.last_session_date <= date('now', '-1 day')
          AND lp.last_session_date > date('now', '-2 days')
          AND lp.total_sessions >= 1
    """)
    return [dict(r) for r in rows] if rows else []


def _get_users_no_return_48h(conn) -> list[dict]:
    """Users who completed a session 48-72h ago and haven't returned."""
    rows = _safe_query_all(conn, """
        SELECT u.id as user_id, u.email, u.display_name,
               lp.level_reading, lp.level_listening, lp.level_speaking, lp.level_ime
        FROM user u
        JOIN learner_profile lp ON u.id = lp.user_id
        WHERE u.is_admin = 0
          AND u.is_active = 1
          AND lp.last_session_date IS NOT NULL
          AND lp.last_session_date <= date('now', '-2 days')
          AND lp.last_session_date > date('now', '-3 days')
          AND lp.total_sessions >= 1
    """)
    return [dict(r) for r in rows] if rows else []


def _get_users_at_risk_7d(conn) -> list[dict]:
    """Users with 3+ completed sessions who haven't returned in 7 days."""
    rows = _safe_query_all(conn, """
        SELECT u.id as user_id, u.email, u.display_name,
               lp.total_sessions, lp.last_session_date
        FROM user u
        JOIN learner_profile lp ON u.id = lp.user_id
        WHERE u.is_admin = 0
          AND u.is_active = 1
          AND u.marketing_opt_out = 0
          AND lp.total_sessions >= 3
          AND lp.last_session_date IS NOT NULL
          AND lp.last_session_date <= date('now', '-7 days')
          AND lp.last_session_date > date('now', '-14 days')
    """)
    return [dict(r) for r in rows] if rows else []


def _get_churning_subscribers(conn) -> list[dict]:
    """Subscribed users with no session in 14+ days."""
    rows = _safe_query_all(conn, """
        SELECT u.id as user_id, u.email, u.display_name,
               u.subscription_tier, u.subscription_status,
               lp.total_sessions, lp.last_session_date
        FROM user u
        JOIN learner_profile lp ON u.id = lp.user_id
        WHERE u.is_admin = 0
          AND u.is_active = 1
          AND u.marketing_opt_out = 0
          AND u.subscription_tier = 'paid'
          AND u.subscription_status = 'active'
          AND lp.last_session_date IS NOT NULL
          AND lp.last_session_date <= date('now', '-14 days')
    """)
    return [dict(r) for r in rows] if rows else []


def _get_accuracy_trend(conn, user_id: int, session_count: int = 3) -> str | None:
    """Check if a user's accuracy is trending up or down.

    Returns 'dropping', 'rising', or None if no clear trend.
    """
    rows = _safe_query_all(conn, """
        SELECT items_correct, items_completed
        FROM session_log
        WHERE user_id = ?
          AND session_outcome = 'completed'
          AND items_completed > 0
        ORDER BY started_at DESC
        LIMIT ?
    """, (user_id, session_count))

    if not rows or len(rows) < session_count:
        return None

    accuracies = []
    for r in rows:
        total = r[1] or 1
        correct = r[0] or 0
        accuracies.append(correct / total)

    # Rows are newest-first; reverse for chronological
    chronological = list(reversed(accuracies))

    # Check if strictly decreasing (dropping)
    if all(chronological[i] > chronological[i + 1]
           for i in range(len(chronological) - 1)):
        return "dropping"

    # Check if strictly increasing (rising)
    if all(chronological[i] < chronological[i + 1]
           for i in range(len(chronological) - 1)):
        return "rising"

    return None


def _get_users_with_accuracy_trends(conn) -> tuple[list[dict], list[dict]]:
    """Find users with dropping or rising accuracy trends.

    Returns (dropping_users, rising_users).
    """
    # Get active users with enough sessions
    users = _safe_query_all(conn, """
        SELECT u.id as user_id, u.email, lp.total_sessions,
               lp.level_reading, lp.level_listening, lp.level_speaking, lp.level_ime
        FROM user u
        JOIN learner_profile lp ON u.id = lp.user_id
        WHERE u.is_admin = 0
          AND u.is_active = 1
          AND lp.total_sessions >= 3
          AND lp.last_session_date >= date('now', '-14 days')
    """)

    dropping = []
    rising = []
    for user in (users or []):
        trend = _get_accuracy_trend(conn, user["user_id"])
        user_dict = dict(user)
        if trend == "dropping":
            dropping.append(user_dict)
        elif trend == "rising":
            rising.append(user_dict)

    return dropping, rising


# ── Remediation actions ───────────────────────────────────────────────────

def _send_activation_email(conn, user: dict) -> bool:
    """Send a return activation email to a user who hasn't returned in 24h."""
    try:
        from ..email import send_onboarding_tip
        return send_onboarding_tip(
            to=user["email"],
            name=user.get("display_name", ""),
            n=4,  # study tip
            user_id=user["user_id"],
        )
    except Exception as exc:
        logger.debug("Return monitor: activation email failed for user %d: %s",
                      user["user_id"], exc)
        return False


def _adjust_difficulty_down(conn, user_id: int, pct: float = 0.10) -> dict:
    """Lower the difficulty of upcoming content for this user by a percentage.

    Adjusts the learner_profile level estimates down by pct.
    """
    updated_fields = {}
    for level_key in ("level_reading", "level_listening", "level_speaking", "level_ime"):
        current = _safe_scalar(conn, f"""
            SELECT {level_key} FROM learner_profile WHERE user_id = ?
        """, (user_id,), default=1.0) or 1.0

        # Don't go below 1.0
        new_level = max(1.0, current * (1.0 - pct))
        if new_level < current:
            try:
                conn.execute(f"""
                    UPDATE learner_profile SET {level_key} = ?
                    WHERE user_id = ?
                """, (round(new_level, 2), user_id))
                updated_fields[level_key] = {
                    "old": round(current, 2),
                    "new": round(new_level, 2),
                }
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

    if updated_fields:
        conn.commit()

    return {"user_id": user_id, "adjusted_fields": updated_fields}


def _adjust_difficulty_up(conn, user_id: int, pct: float = 0.10) -> dict:
    """Raise the difficulty of upcoming content for this user.

    Adjusts the learner_profile level estimates up by pct.
    """
    updated_fields = {}
    for level_key in ("level_reading", "level_listening", "level_speaking", "level_ime"):
        current = _safe_scalar(conn, f"""
            SELECT {level_key} FROM learner_profile WHERE user_id = ?
        """, (user_id,), default=1.0) or 1.0

        # Don't go above 9.0 (max HSK level)
        new_level = min(9.0, current * (1.0 + pct))
        if new_level > current:
            try:
                conn.execute(f"""
                    UPDATE learner_profile SET {level_key} = ?
                    WHERE user_id = ?
                """, (round(new_level, 2), user_id))
                updated_fields[level_key] = {
                    "old": round(current, 2),
                    "new": round(new_level, 2),
                }
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

    if updated_fields:
        conn.commit()

    return {"user_id": user_id, "adjusted_fields": updated_fields}


def _send_reengagement_email(conn, user: dict) -> bool:
    """Send re-engagement email for at-risk users (7d no return)."""
    try:
        from ..email import send_churn_prevention
        return send_churn_prevention(
            to=user["email"],
            name=user.get("display_name", ""),
            n=1,  # gentle
            days=7,
            user_id=user["user_id"],
        )
    except Exception as exc:
        logger.debug("Return monitor: re-engagement email failed for user %d: %s",
                      user["user_id"], exc)
        return False


def _send_winback_email(conn, user: dict) -> bool:
    """Send win-back email for churning subscribers (14d+ no session)."""
    try:
        from ..email import send_churn_prevention
        return send_churn_prevention(
            to=user["email"],
            name=user.get("display_name", ""),
            n=2,  # direct
            days=14,
            user_id=user["user_id"],
        )
    except Exception as exc:
        logger.debug("Return monitor: win-back email failed for user %d: %s",
                      user["user_id"], exc)
        return False


# ── Main check ────────────────────────────────────────────────────────────

def run_check(conn: sqlite3.Connection) -> dict:
    """Run all return monitoring rules and execute interventions.

    Called by:
    - quality_scheduler.py (nightly, comprehensive)
    - health_check_scheduler.py (every 15 min, lightweight — only accuracy trends)

    Returns a summary dict.
    """
    _ensure_tables(conn)

    actions_taken = []
    all_actions_detail = []

    # Governance helpers (non-fatal)
    def _gov_check(action_type, target=None):
        try:
            from .contracts import check_contract
            return check_contract(conn, "return_monitor", action_type, target)
        except Exception:
            return True, "", None

    def _gov_record(action_type, target, description, metrics_before, verification_hours=48, contract_id=None):
        try:
            from .action_ledger import record_action
            record_action(conn, "return_monitor", action_type, target, description,
                          metrics_before, verification_hours=verification_hours, contract_id=contract_id)
        except Exception:
            pass

    # ── Rule 1: completed_session + no_return_24h -> activation email ─
    users_24h = _get_users_no_return_24h(conn)
    metrics_24h = {"users_no_return_24h": len(users_24h)}
    allowed_email, reason_email, cid_email = _gov_check("send_activation_email")
    for user in users_24h:
        if _action_already_taken(conn, user["user_id"], "no_return_24h", within_hours=48):
            continue
        if not allowed_email:
            _gov_record("send_activation_email", str(user["user_id"]), f"BLOCKED: {reason_email}", None, contract_id=cid_email)
            continue
        success = _send_activation_email(conn, user)
        action = f"Sent activation email to user #{user['user_id']} (24h no return)"
        _log_action(conn, user["user_id"], "no_return_24h", action,
                    details={"email": user.get("email", "?")}, success=success)
        if success:
            actions_taken.append(action)
            all_actions_detail.append({
                "user_id": user["user_id"], "rule": "no_return_24h",
                "action": "activation_email",
            })
            _gov_record("send_activation_email", str(user["user_id"]), action, metrics_24h, verification_hours=48, contract_id=cid_email)

    # ── Rule 2: no_return_48h -> adjust difficulty down 10% ──────────
    users_48h = _get_users_no_return_48h(conn)
    metrics_48h = {"users_no_return_48h": len(users_48h)}
    allowed_diff, reason_diff, cid_diff = _gov_check("adjust_difficulty")
    for user in users_48h:
        if _action_already_taken(conn, user["user_id"], "no_return_48h_difficulty", within_hours=168):
            continue
        if not allowed_diff:
            _gov_record("adjust_difficulty", str(user["user_id"]), f"BLOCKED: {reason_diff}", None, contract_id=cid_diff)
            continue
        result = _adjust_difficulty_down(conn, user["user_id"], pct=0.10)
        if result["adjusted_fields"]:
            action = f"Reduced difficulty 10% for user #{user['user_id']} (48h no return)"
            _log_action(conn, user["user_id"], "no_return_48h_difficulty", action,
                        details=result)
            actions_taken.append(action)
            all_actions_detail.append({
                "user_id": user["user_id"], "rule": "no_return_48h",
                "action": "difficulty_down_10pct",
            })
            _gov_record("adjust_difficulty", str(user["user_id"]), action, metrics_48h, verification_hours=168, contract_id=cid_diff)

    # ── Rule 3: 3+ sessions + no_return_7d -> at_risk + reengagement ─
    users_7d = _get_users_at_risk_7d(conn)
    metrics_7d = {"users_at_risk_7d": len(users_7d)}
    allowed_reeng, reason_reeng, cid_reeng = _gov_check("send_reengagement_email")
    for user in users_7d:
        if _action_already_taken(conn, user["user_id"], "at_risk_7d", within_hours=336):  # 14 days
            continue
        if not allowed_reeng:
            _gov_record("send_reengagement_email", str(user["user_id"]), f"BLOCKED: {reason_reeng}", None, contract_id=cid_reeng)
            continue
        success = _send_reengagement_email(conn, user)
        action = f"Sent re-engagement email to user #{user['user_id']} (7d at-risk, {user.get('total_sessions', 0)} sessions)"
        _log_action(conn, user["user_id"], "at_risk_7d", action,
                    details={"sessions": user.get("total_sessions", 0)},
                    success=success)
        if success:
            actions_taken.append(action)
            all_actions_detail.append({
                "user_id": user["user_id"], "rule": "at_risk_7d",
                "action": "reengagement_email",
            })
            _gov_record("send_reengagement_email", str(user["user_id"]), action, metrics_7d, verification_hours=168, contract_id=cid_reeng)

    # ── Rule 4: subscribed + no_session_14d -> churning + win-back ───
    churning = _get_churning_subscribers(conn)
    metrics_churn = {"churning_subscribers": len(churning)}
    allowed_wb, reason_wb, cid_wb = _gov_check("send_winback_email")
    for user in churning:
        if _action_already_taken(conn, user["user_id"], "churning_14d", within_hours=672):  # 28 days
            continue
        if not allowed_wb:
            _gov_record("send_winback_email", str(user["user_id"]), f"BLOCKED: {reason_wb}", None, contract_id=cid_wb)
            continue
        success = _send_winback_email(conn, user)
        action = f"Sent win-back email to user #{user['user_id']} (paid, 14d+ inactive)"
        _log_action(conn, user["user_id"], "churning_14d", action,
                    details={"subscription_tier": user.get("subscription_tier", "?")},
                    success=success)
        if success:
            actions_taken.append(action)
            all_actions_detail.append({
                "user_id": user["user_id"], "rule": "churning_14d",
                "action": "winback_email",
            })
            _gov_record("send_winback_email", str(user["user_id"]), action, metrics_churn, verification_hours=336, contract_id=cid_wb)

    # ── Rule 5/6: accuracy_dropping/rising -> adjust difficulty ──────
    dropping, rising = _get_users_with_accuracy_trends(conn)
    metrics_accuracy = {"dropping_users": len(dropping), "rising_users": len(rising)}
    allowed_adj, reason_adj, cid_adj = _gov_check("adjust_difficulty")

    for user in dropping:
        if _action_already_taken(conn, user["user_id"], "accuracy_dropping", within_hours=168):
            continue
        if not allowed_adj:
            _gov_record("adjust_difficulty", str(user["user_id"]), f"BLOCKED: {reason_adj}", None, contract_id=cid_adj)
            continue
        result = _adjust_difficulty_down(conn, user["user_id"], pct=0.10)
        if result["adjusted_fields"]:
            action = f"Reduced difficulty for user #{user['user_id']} (accuracy dropping 3 sessions)"
            _log_action(conn, user["user_id"], "accuracy_dropping", action,
                        details=result)
            actions_taken.append(action)
            all_actions_detail.append({
                "user_id": user["user_id"], "rule": "accuracy_dropping",
                "action": "difficulty_down_10pct",
            })
            _gov_record("adjust_difficulty", str(user["user_id"]), action, metrics_accuracy, verification_hours=168, contract_id=cid_adj)

    for user in rising:
        if _action_already_taken(conn, user["user_id"], "accuracy_rising", within_hours=168):
            continue
        if not allowed_adj:
            _gov_record("adjust_difficulty", str(user["user_id"]), f"BLOCKED: {reason_adj}", None, contract_id=cid_adj)
            continue
        result = _adjust_difficulty_up(conn, user["user_id"], pct=0.10)
        if result["adjusted_fields"]:
            action = f"Increased difficulty for user #{user['user_id']} (accuracy rising 3 sessions)"
            _log_action(conn, user["user_id"], "accuracy_rising", action,
                        details=result)
            actions_taken.append(action)
            all_actions_detail.append({
                "user_id": user["user_id"], "rule": "accuracy_rising",
                "action": "difficulty_up_10pct",
            })
            _gov_record("adjust_difficulty", str(user["user_id"]), action, metrics_accuracy, verification_hours=168, contract_id=cid_adj)

    # ── Admin summary ────────────────────────────────────────────────
    if all_actions_detail:
        _notify_admin_summary(all_actions_detail)

    # ── Log summary ──────────────────────────────────────────────────
    if actions_taken:
        logger.info(
            "Return monitor: %d action(s) — %s",
            len(actions_taken), "; ".join(actions_taken[:5]),
        )
    else:
        logger.debug("Return monitor: no interventions needed")

    return {
        "actions_taken": actions_taken,
        "actions_count": len(actions_taken),
        "users_24h_no_return": len(users_24h),
        "users_48h_no_return": len(users_48h),
        "users_at_risk_7d": len(users_7d),
        "churning_subscribers": len(churning),
        "accuracy_dropping": len(dropping),
        "accuracy_rising": len(rising),
    }


# ── Intelligence analyzer ────────────────────────────────────────────────

def analyze_return_health(conn) -> list[dict]:
    """Analyzer function for the intelligence engine.

    Generates findings based on user return patterns.
    """
    _ensure_tables(conn)
    findings = []

    # Count real users (non-admin with sessions)
    total_users = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user u
        JOIN learner_profile lp ON u.id = lp.user_id
        WHERE u.is_admin = 0 AND lp.total_sessions >= 1
    """, default=0)

    if total_users < 2:
        return findings  # Not enough users for meaningful analysis

    # 7-day return rate
    users_with_session_7d = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND user_id IN (SELECT id FROM user WHERE is_admin = 0)
    """, default=0)

    users_with_session_14d = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
          AND started_at < datetime('now', '-7 days')
          AND user_id IN (SELECT id FROM user WHERE is_admin = 0)
    """, default=0)

    if users_with_session_14d > 0:
        return_rate = users_with_session_7d / users_with_session_14d
        if return_rate < 0.5:
            findings.append(_finding(
                "retention", "high",
                f"Week-over-week return rate is {return_rate:.0%}",
                f"Only {users_with_session_7d} of {users_with_session_14d} users "
                f"who were active last week returned this week ({return_rate:.0%}). "
                f"The return monitor is auto-sending activation and re-engagement "
                f"emails and adjusting difficulty for non-returners.",
                "Review return_monitor_action_log for interventions taken. "
                "Consider session length reduction or content refresh.",
                "Check return_monitor_action_log and lifecycle_event for "
                "return_monitor_* events to see what interventions were taken.",
                "User retention and engagement",
                [],
            ))

    # Churning subscribers
    churning_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user u
        JOIN learner_profile lp ON u.id = lp.user_id
        WHERE u.is_admin = 0 AND u.subscription_tier = 'paid'
          AND u.subscription_status = 'active'
          AND lp.last_session_date <= date('now', '-14 days')
    """, default=0)

    total_paid = _safe_scalar(conn, """
        SELECT COUNT(*) FROM user
        WHERE is_admin = 0 AND subscription_tier = 'paid'
          AND subscription_status = 'active'
    """, default=0)

    if total_paid >= 2 and churning_count > 0:
        churn_pct = churning_count / total_paid
        if churn_pct > 0.3:
            findings.append(_finding(
                "retention", "critical",
                f"{churning_count}/{total_paid} paid subscribers inactive 14+ days",
                f"{churn_pct:.0%} of paying subscribers have not had a session in "
                f"14+ days. Win-back emails are being sent automatically, but this "
                f"level indicates a systemic engagement problem.",
                "Investigate why paid users are disengaging. Check session quality, "
                "content difficulty, and recent feature changes.",
                "Review session_log for churning users. Check accuracy trends. "
                "Cross-reference with any recent deployments or content changes.",
                "Revenue retention risk",
                [],
            ))

    # Accuracy trends
    dropping_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT s1.user_id
            FROM session_log s1
            JOIN session_log s2 ON s1.user_id = s2.user_id
            JOIN session_log s3 ON s1.user_id = s3.user_id
            WHERE s1.user_id IN (SELECT id FROM user WHERE is_admin = 0)
              AND s1.session_outcome = 'completed' AND s1.items_completed > 0
              AND s2.session_outcome = 'completed' AND s2.items_completed > 0
              AND s3.session_outcome = 'completed' AND s3.items_completed > 0
              AND s1.started_at >= datetime('now', '-14 days')
            GROUP BY s1.user_id
            HAVING COUNT(*) >= 3
        )
    """, default=0)

    if dropping_count > 0 and total_users >= 3:
        findings.append(_finding(
            "drill_quality", "medium",
            f"{dropping_count} user(s) with declining accuracy",
            f"{dropping_count} active users show declining accuracy over their "
            f"last 3 sessions. The return monitor auto-adjusts difficulty downward "
            f"for these users.",
            "Review content difficulty calibration. Check if new content is "
            "inappropriately difficult.",
            "Query session_log for users with declining accuracy. Check "
            "content_item difficulty distribution vs user level profiles.",
            "Adaptive difficulty effectiveness",
            [],
        ))

    return findings


ANALYZERS = [analyze_return_health]
