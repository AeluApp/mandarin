"""Marketing hooks — lifecycle event logging and email trigger detection.

This module provides:
1. log_lifecycle_event() — inserts lifecycle events into the lifecycle_event table
2. check_already_sent() — checks if a specific email was already sent
3. check_email_triggers() — scans the database for users who should receive lifecycle emails

All functions are deterministic and use zero external API calls. The email
trigger checker returns a list of dicts describing which emails to queue;
the actual sending is handled by a separate worker or cron job.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
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
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

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
