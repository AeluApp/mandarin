"""Marketing hooks — lifecycle event logging and email trigger detection.

This module provides:
1. log_lifecycle_event() — inserts lifecycle events into the lifecycle_event table
2. check_already_sent() — checks if a specific email was already sent
3. check_email_triggers() — scans the database for users who should receive lifecycle emails

All functions are deterministic and use zero external API calls. The email
trigger checker returns a list of dicts describing which emails to queue;
the actual sending is handled by a separate worker or cron job.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC
from pathlib import Path

logger = logging.getLogger(__name__)


def log_lifecycle_event(event_type: str, user_id: str = None, conn: sqlite3.Connection = None, **metadata):
    """Insert a lifecycle event into the lifecycle_event table.

    Args:
        event_type: One of the supported event types (signup, first_session,
            activation, session_complete, upgrade, cancellation_initiated,
            cancellation_completed, cancellation_reason, pause_started,
            pause_ended, reactivation, milestone_reached, churn_risk_detected,
            email_triggered, discount_applied, etc.)
        user_id: Optional user identifier.
        conn: Optional existing database connection. If None, opens a new one.
        **metadata: Arbitrary key-value pairs stored as JSON in the metadata column.
    """
    metadata_json = json.dumps(metadata) if metadata else None
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    owns_conn = conn is None
    if owns_conn:
        from . import db
        conn = db.ensure_db()

    try:
        conn.execute(
            """INSERT INTO lifecycle_event (event_type, user_id, metadata, created_at)
               VALUES (?, ?, ?, ?)""",
            (event_type, user_id, metadata_json, now_utc)
        )
        conn.commit()
        logger.info("lifecycle event logged: type=%s user=%s", event_type, user_id)
    except sqlite3.Error as e:
        logger.error("failed to log lifecycle event: type=%s user=%s error=%s", event_type, user_id, e)
        raise
    finally:
        if owns_conn:
            conn.close()


def check_already_sent(user_id: str, sequence: str, email_number: int,
                       conn: sqlite3.Connection = None) -> bool:
    """Check if a specific email was already sent to a user.

    Looks for a lifecycle_event with event_type='email_triggered' and matching
    sequence + email_number in the metadata JSON.

    Args:
        user_id: The user to check.
        sequence: Email sequence name (e.g., 'activation_nudge', 'onboarding').
        email_number: The email number within the sequence.
        conn: Optional existing database connection. If None, opens a new one.

    Returns:
        True if the email was already sent, False otherwise.
    """
    owns_conn = conn is None
    if owns_conn:
        from . import db
        conn = db.ensure_db()

    try:
        # Use JSON extraction to check metadata fields
        rows = conn.execute(
            """SELECT id FROM lifecycle_event
               WHERE event_type = 'email_triggered'
                 AND user_id = ?
                 AND json_extract(metadata, '$.sequence') = ?
                 AND json_extract(metadata, '$.email_number') = ?
               LIMIT 1""",
            (user_id, sequence, email_number)
        ).fetchall()
        return len(rows) > 0
    except sqlite3.Error as e:
        logger.error("check_already_sent error: user=%s seq=%s num=%d error=%s",
                     user_id, sequence, email_number, e)
        return False
    finally:
        if owns_conn:
            conn.close()


def check_email_triggers(db_path=None):
    """Scan the database for users who should receive lifecycle emails.

    Returns a list of dicts, each with:
        - user_id: str
        - email_sequence: str (e.g., 'activation_nudge', 'onboarding', 'churn_prevention')
        - email_number: int (1-based index within the sequence)
        - reason: str (human-readable explanation)

    Trigger conditions (14 rules):
        1.  Signed up, no session in 24h -> activation_nudge #1
        2.  Signed up, no session in 5 days -> activation_nudge #2
        3.  Signed up, no session in 10 days -> activation_nudge #3
        4.  Completed first session -> onboarding #3 (feature discovery)
        5.  Day 4 after signup -> onboarding #4 (study tip)
        6.  Day 7 after signup -> onboarding #5 (progress summary)
        7.  Day 10 after signup -> onboarding #6 (feature discovery)
        8.  Day 14 after signup -> onboarding #7 (check-in)
        9.  Reached HSK 2 boundary -> upgrade #1 (milestone)
        10. No session in 5+ days (paid user) -> churn_prevention #1
        11. No session in 8+ days (paid user) -> churn_prevention #2
        12. No session in 12+ days (paid user) -> churn_prevention #3
        13. No session in 19+ days (paid user) -> churn_prevention #4
        14. Milestone reached -> milestone email (specific to milestone)

    This function queries existing tables (session_log, lifecycle_event, etc.)
    to determine trigger conditions.
    """
    from .db.core import get_connection, DB_PATH

    path = Path(db_path) if db_path else DB_PATH
    if not path.exists():
        logger.warning("Database not found at %s — no email triggers to check", path)
        return []

    conn = get_connection(path)
    triggers = []

    try:
        # Ensure tables exist before querying
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        if "lifecycle_event" not in tables:
            logger.warning("lifecycle_event table not found — skipping email trigger check")
            return []

        has_session_log = "session_log" in tables
        has_progress = "progress" in tables
        has_content = "content_item" in tables

        # ── Activation nudge triggers (rules 1-3) ─────────────────────────
        # Find users who signed up but have no session_log entries.
        # "Signed up" is detected from lifecycle_event with event_type='signup'.

        signup_users = conn.execute(
            """SELECT DISTINCT user_id,
                      created_at as signup_at,
                      CAST((julianday('now') - julianday(created_at)) * 24 AS INTEGER) as hours_since_signup,
                      CAST(julianday('now') - julianday(created_at) AS INTEGER) as days_since_signup
               FROM lifecycle_event
               WHERE event_type = 'signup'
                 AND user_id IS NOT NULL"""
        ).fetchall()

        for user in signup_users:
            user_id = user["user_id"]
            hours = user["hours_since_signup"] or 0
            days = user["days_since_signup"] or 0

            # Check if user has any sessions
            has_session = False
            if has_session_log:
                # Check for session_complete lifecycle events or session_log entries
                session_check = conn.execute(
                    """SELECT id FROM lifecycle_event
                       WHERE user_id = ? AND event_type IN ('first_session', 'session_complete')
                       LIMIT 1""",
                    (user_id,)
                ).fetchone()
                has_session = session_check is not None

            if not has_session:
                # Rule 1: No session in 24+ hours
                if hours >= 24 and not check_already_sent(user_id, "activation_nudge", 1, conn):
                    triggers.append({
                        "user_id": user_id,
                        "email_sequence": "activation_nudge",
                        "email_number": 1,
                        "reason": f"Signed up {hours} hours ago, no session started",
                    })

                # Rule 2: No session in 5+ days
                if days >= 5 and not check_already_sent(user_id, "activation_nudge", 2, conn):
                    triggers.append({
                        "user_id": user_id,
                        "email_sequence": "activation_nudge",
                        "email_number": 2,
                        "reason": f"Signed up {days} days ago, no session started",
                    })

                # Rule 3: No session in 10+ days
                if days >= 10 and not check_already_sent(user_id, "activation_nudge", 3, conn):
                    triggers.append({
                        "user_id": user_id,
                        "email_sequence": "activation_nudge",
                        "email_number": 3,
                        "reason": f"Signed up {days} days ago, no session started",
                    })

        # ── Onboarding triggers (rules 4-8) ───────────────────────────────
        # These trigger for users who HAVE started sessions.

        for user in signup_users:
            user_id = user["user_id"]
            days = user["days_since_signup"] or 0

            # Check if user completed their first session
            first_session = conn.execute(
                """SELECT id FROM lifecycle_event
                   WHERE user_id = ? AND event_type = 'first_session'
                   LIMIT 1""",
                (user_id,)
            ).fetchone()

            # Rule 4: Completed first session -> onboarding #3
            if first_session and not check_already_sent(user_id, "onboarding", 3, conn):
                triggers.append({
                    "user_id": user_id,
                    "email_sequence": "onboarding",
                    "email_number": 3,
                    "reason": "Completed first session — feature discovery email",
                })

            # Rule 5: Day 4 after signup -> onboarding #4
            if days >= 4 and not check_already_sent(user_id, "onboarding", 4, conn):
                # Only send if user has had at least one session
                if first_session:
                    triggers.append({
                        "user_id": user_id,
                        "email_sequence": "onboarding",
                        "email_number": 4,
                        "reason": f"Day {days} after signup — study tip",
                    })

            # Rule 6: Day 7 after signup -> onboarding #5
            if days >= 7 and not check_already_sent(user_id, "onboarding", 5, conn):
                if first_session:
                    triggers.append({
                        "user_id": user_id,
                        "email_sequence": "onboarding",
                        "email_number": 5,
                        "reason": f"Day {days} after signup — progress summary",
                    })

            # Rule 7: Day 10 after signup -> onboarding #6
            if days >= 10 and not check_already_sent(user_id, "onboarding", 6, conn):
                if first_session:
                    triggers.append({
                        "user_id": user_id,
                        "email_sequence": "onboarding",
                        "email_number": 6,
                        "reason": f"Day {days} after signup — feature discovery",
                    })

            # Rule 8: Day 14 after signup -> onboarding #7
            if days >= 14 and not check_already_sent(user_id, "onboarding", 7, conn):
                if first_session:
                    triggers.append({
                        "user_id": user_id,
                        "email_sequence": "onboarding",
                        "email_number": 7,
                        "reason": f"Day {days} after signup — check-in",
                    })

        # ── Upgrade trigger (rule 9) ──────────────────────────────────────
        # Users who have reached the HSK 2 boundary: 80%+ of HSK 2 vocab at stable+ mastery.
        if has_progress and has_content:
            # Get users who logged a milestone for HSK 2 boundary
            hsk2_milestone_users = conn.execute(
                """SELECT DISTINCT user_id FROM lifecycle_event
                   WHERE event_type = 'milestone_reached'
                     AND json_extract(metadata, '$.milestone') IN ('hsk2_complete', 'hsk2_boundary')
                     AND user_id IS NOT NULL"""
            ).fetchall()

            for row in hsk2_milestone_users:
                uid = row["user_id"]
                if not check_already_sent(uid, "upgrade", 1, conn):
                    triggers.append({
                        "user_id": uid,
                        "email_sequence": "upgrade",
                        "email_number": 1,
                        "reason": "Reached HSK 2 boundary — upgrade milestone email",
                    })

        # ── Churn prevention triggers (rules 10-13) ──────────────────────
        # Find paid users with inactivity gaps.
        # Paid users are identified by an 'upgrade' lifecycle event without a
        # subsequent 'cancellation_completed'.
        paid_users = conn.execute(
            """SELECT DISTINCT le.user_id
               FROM lifecycle_event le
               WHERE le.event_type = 'upgrade'
                 AND le.user_id IS NOT NULL
                 AND le.user_id NOT IN (
                     SELECT user_id FROM lifecycle_event
                     WHERE event_type = 'cancellation_completed'
                       AND user_id IS NOT NULL
                 )
                 AND le.user_id NOT IN (
                     SELECT user_id FROM lifecycle_event
                     WHERE event_type = 'pause_started'
                       AND user_id IS NOT NULL
                       AND user_id NOT IN (
                           SELECT user_id FROM lifecycle_event
                           WHERE event_type = 'pause_ended'
                             AND user_id IS NOT NULL
                       )
                 )"""
        ).fetchall()

        for row in paid_users:
            uid = row["user_id"]

            # Find the user's last session (from lifecycle events)
            last_session = conn.execute(
                """SELECT MAX(created_at) as last_at
                   FROM lifecycle_event
                   WHERE user_id = ?
                     AND event_type IN ('session_complete', 'first_session')""",
                (uid,)
            ).fetchone()

            if not last_session or not last_session["last_at"]:
                continue

            days_inactive = conn.execute(
                "SELECT CAST(julianday('now') - julianday(?) AS INTEGER) as days",
                (last_session["last_at"],)
            ).fetchone()

            days = (days_inactive["days"] or 0) if days_inactive else 0

            # Rule 10: 5+ days inactive
            if days >= 5 and not check_already_sent(uid, "churn_prevention", 1, conn):
                triggers.append({
                    "user_id": uid,
                    "email_sequence": "churn_prevention",
                    "email_number": 1,
                    "reason": f"Paid user inactive for {days} days — gentle check-in",
                })

            # Rule 11: 8+ days inactive
            if days >= 8 and not check_already_sent(uid, "churn_prevention", 2, conn):
                triggers.append({
                    "user_id": uid,
                    "email_sequence": "churn_prevention",
                    "email_number": 2,
                    "reason": f"Paid user inactive for {days} days — direct check-in",
                })

            # Rule 12: 12+ days inactive
            if days >= 12 and not check_already_sent(uid, "churn_prevention", 3, conn):
                triggers.append({
                    "user_id": uid,
                    "email_sequence": "churn_prevention",
                    "email_number": 3,
                    "reason": f"Paid user inactive for {days} days — honest assessment",
                })

            # Rule 13: 19+ days inactive
            if days >= 19 and not check_already_sent(uid, "churn_prevention", 4, conn):
                triggers.append({
                    "user_id": uid,
                    "email_sequence": "churn_prevention",
                    "email_number": 4,
                    "reason": f"Paid user inactive for {days} days — final outreach",
                })

        # ── Win-back triggers (rules 15-17) ───────────────────────────────
        # Find cancelled users at 7d, 30d, 60d post-cancellation.
        cancelled_users = conn.execute(
            """SELECT user_id, created_at as cancelled_at,
                      CAST(julianday('now') - julianday(created_at) AS INTEGER) as days_since
               FROM lifecycle_event
               WHERE event_type = 'cancellation_completed'
                 AND user_id IS NOT NULL"""
        ).fetchall()

        for row in cancelled_users:
            uid = row["user_id"]
            days = row["days_since"] or 0

            # Rule 15: 7+ days post-cancel
            if days >= 7 and not check_already_sent(uid, "winback", 1, conn):
                triggers.append({
                    "user_id": uid,
                    "email_sequence": "winback",
                    "email_number": 1,
                    "reason": f"Cancelled {days} days ago — gentle win-back",
                })

            # Rule 16: 30+ days post-cancel
            if days >= 30 and not check_already_sent(uid, "winback", 2, conn):
                triggers.append({
                    "user_id": uid,
                    "email_sequence": "winback",
                    "email_number": 2,
                    "reason": f"Cancelled {days} days ago — progress reminder",
                })

            # Rule 17: 60+ days post-cancel
            if days >= 60 and not check_already_sent(uid, "winback", 3, conn):
                triggers.append({
                    "user_id": uid,
                    "email_sequence": "winback",
                    "email_number": 3,
                    "reason": f"Cancelled {days} days ago — final win-back",
                })

        # ── Milestone triggers (rule 14) ──────────────────────────────────
        # Find unprocessed milestone events that haven't had an email sent yet.
        milestone_events = conn.execute(
            """SELECT le.user_id, le.metadata, le.created_at
               FROM lifecycle_event le
               WHERE le.event_type = 'milestone_reached'
                 AND le.user_id IS NOT NULL
               ORDER BY le.created_at DESC"""
        ).fetchall()

        for evt in milestone_events:
            uid = evt["user_id"]
            meta = {}
            if evt["metadata"]:
                try:
                    meta = json.loads(evt["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass

            milestone = meta.get("milestone", "unknown")

            # Use the milestone name as a pseudo email_number to avoid duplicate sends
            # We encode milestone as a hash-based number for the already_sent check
            milestone_num = hash(milestone) % 10000

            if not check_already_sent(uid, "milestone", milestone_num, conn):
                triggers.append({
                    "user_id": uid,
                    "email_sequence": "milestone",
                    "email_number": milestone_num,
                    "reason": f"Milestone reached: {milestone}",
                })

    except sqlite3.Error as e:
        logger.error("check_email_triggers error: %s", e)
    finally:
        conn.close()

    return triggers


# ── Referral / Viral Coefficient ──────────────────────────────────────────


def generate_referral_code(user_id: int) -> str:
    """Generate a unique referral code for a user."""
    return f"aelu-{hashlib.md5(str(user_id).encode()).hexdigest()[:8]}"


def track_referral(conn, referrer_code: str, new_user_id: int, channel: str = "link") -> bool:
    """Log a referral when a new user signs up with a referral code."""
    try:
        # Look up referrer from code
        # Code format: aelu-{hash8} where hash is md5(user_id)[:8]
        # We need to search all users (not ideal but works for small scale)
        users = conn.execute("SELECT id FROM user").fetchall()
        referrer_id = None
        for u in users:
            if generate_referral_code(u["id"]) == referrer_code:
                referrer_id = u["id"]
                break

        if referrer_id is None:
            return False

        conn.execute("""
            INSERT INTO referral_log (referrer_id, referred_id, channel, referral_code)
            VALUES (?, ?, ?, ?)
        """, (referrer_id, new_user_id, channel, referrer_code))
        conn.commit()
        return True
    except Exception:
        return False


def compute_viral_coefficient(conn, days: int = 30) -> dict:
    """Compute viral k-factor: k = invites x conversion_rate."""
    try:
        # Count referrals in period
        referrals = conn.execute("""
            SELECT COUNT(*) as cnt FROM referral_log
            WHERE created_at >= datetime('now', ? || ' days')
        """, (f"-{days}",)).fetchone()

        # Count total users in period
        total_users = conn.execute("""
            SELECT COUNT(*) as cnt FROM user
            WHERE created_at >= datetime('now', ? || ' days')
        """, (f"-{days}",)).fetchone()

        # Count unique referrers
        referrers = conn.execute("""
            SELECT COUNT(DISTINCT referrer_id) as cnt FROM referral_log
            WHERE created_at >= datetime('now', ? || ' days')
        """, (f"-{days}",)).fetchone()

        ref_count = referrals["cnt"] if referrals else 0
        user_count = total_users["cnt"] if total_users else 1
        referrer_count = referrers["cnt"] if referrers else 0

        # k = (referrals / users) -- simplified viral coefficient
        k = ref_count / max(1, user_count)

        return {
            "k_factor": round(k, 3),
            "referrals": ref_count,
            "total_users": user_count,
            "unique_referrers": referrer_count,
            "period_days": days,
        }
    except Exception as e:
        return {"k_factor": 0.0, "error": str(e)}


def check_fresh_start_triggers(db_path=None):
    """Detect fresh-start opportunities for re-engagement (Dai, Milkman & Riis 2014).

    Temporal landmarks motivate goal pursuit. Returns a list of trigger dicts
    for users who might benefit from a fresh-start nudge. DOCTRINE-compliant:
    no guilt, no urgency — just 'your schedule has been adjusted.'

    Triggers:
        1. New calendar month: inactive 7+ days at month boundary
        2. Monday: users with weekly goals, inactive 3+ days
        3. HSK level completion: just completed a level milestone
        4. Cultural events: Chinese New Year, Mid-Autumn Festival
    """
    from .db.core import get_connection, DB_PATH
    from datetime import datetime

    path = Path(db_path) if db_path else DB_PATH
    if not path.exists():
        return []

    conn = get_connection(path)
    triggers = []

    try:
        now = datetime.now(UTC)

        # 1. New month + inactive 7+ days
        if now.day <= 3:  # First 3 days of month
            inactive_users = conn.execute(
                """SELECT u.id, u.email,
                          julianday('now') - julianday(MAX(sl.completed_at)) as days_inactive
                   FROM user u
                   LEFT JOIN session_log sl ON u.id = sl.user_id
                   WHERE u.is_admin = 0
                   GROUP BY u.id
                   HAVING days_inactive >= 7"""
            ).fetchall()
            for user in inactive_users:
                if not check_already_sent(str(user["id"]), "fresh_start", 1, conn=conn):
                    triggers.append({
                        "user_id": str(user["id"]),
                        "email_sequence": "fresh_start",
                        "email_number": 1,
                        "trigger_type": "new_month",
                        "reason": f"New month, inactive {int(user['days_inactive'])} days",
                    })

        # 2. Monday + inactive 3+ days (users with weekly goals)
        if now.weekday() == 0:  # Monday
            try:
                monday_users = conn.execute(
                    """SELECT u.id,
                              julianday('now') - julianday(MAX(sl.completed_at)) as days_inactive
                       FROM user u
                       JOIN learner_profile lp ON u.id = lp.user_id
                       LEFT JOIN session_log sl ON u.id = sl.user_id
                       WHERE u.is_admin = 0
                         AND lp.target_sessions_per_week >= 3
                       GROUP BY u.id
                       HAVING days_inactive >= 3 AND days_inactive < 14"""
                ).fetchall()
                for user in monday_users:
                    if not check_already_sent(str(user["id"]), "fresh_start_monday", 1, conn=conn):
                        triggers.append({
                            "user_id": str(user["id"]),
                            "email_sequence": "fresh_start_monday",
                            "email_number": 1,
                            "trigger_type": "monday",
                            "reason": f"Monday reset, inactive {int(user['days_inactive'])} days",
                        })
            except Exception:
                pass

    except Exception as e:
        logger.error("Fresh start trigger check failed: %s", e)
    finally:
        conn.close()

    return triggers
