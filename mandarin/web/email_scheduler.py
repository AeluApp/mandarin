"""Background thread for periodic email trigger checking and sending.

Runs hourly:
1. Calls check_email_triggers() from marketing_hooks — returns pending emails
2. Maps each trigger to the appropriate email template function
3. Sends via Resend (through email.py)
4. Logs lifecycle_event("email_triggered") for dedup
5. Calls get_at_risk_users() from churn_detection — logs churn_risk_detected events
6. Checks for streak-at-risk users and sends push notifications
"""

import logging
import threading
import time

from .. import db
from ..marketing_hooks import check_email_triggers, log_lifecycle_event
from ..churn_detection import get_at_risk_users
from ..email import (
    send_activation_nudge,
    send_onboarding_tip,
    send_churn_prevention,
    send_milestone_reached,
    send_winback,
    send_weekly_progress,
)
from datetime import UTC

logger = logging.getLogger(__name__)

_HOURLY_SECONDS = 3600
_INITIAL_DELAY = 120  # Wait 2 minutes after startup

_stop_event = threading.Event()
_thread = None


def start():
    """Start the email scheduler background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="email-scheduler")
    _thread.start()
    logger.info("Email scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


# Email sequence -> template function mapping
_TEMPLATE_MAP = {
    "activation_nudge": send_activation_nudge,
    "onboarding": send_onboarding_tip,
    "churn_prevention": send_churn_prevention,
    "milestone": send_milestone_reached,
    "winback": send_winback,
}


def _send_trigger(trigger: dict, conn) -> bool:
    """Send a single email trigger using the appropriate template.

    Returns True if sent successfully.
    """
    user_id = trigger["user_id"]
    sequence = trigger["email_sequence"]
    email_number = trigger["email_number"]

    # Look up user email and name
    row = conn.execute(
        "SELECT email, display_name, marketing_opt_out FROM user WHERE id = ? AND is_active = 1",
        (int(user_id),)
    ).fetchone()

    if not row:
        return False

    # Respect marketing opt-out
    if row["marketing_opt_out"]:
        return False

    to = row["email"]
    name = row["display_name"] or ""

    template_fn = _TEMPLATE_MAP.get(sequence)
    if not template_fn:
        logger.warning("No template for sequence=%s", sequence)
        return False

    try:
        if sequence == "churn_prevention":
            # Extract days from reason text
            reason = trigger.get("reason", "")
            days = 0
            for word in reason.split():
                if word.isdigit():
                    days = int(word)
                    break
            sent = template_fn(to, name, email_number, days=days, user_id=user_id)
        elif sequence == "milestone":
            reason = trigger.get("reason", "")
            milestone = reason.replace("Milestone reached: ", "") if "Milestone reached:" in reason else "unknown"
            sent = template_fn(to, name, milestone, user_id=user_id)
        else:
            sent = template_fn(to, name, email_number, user_id=user_id)

        return sent
    except Exception:
        logger.exception("Failed to send %s #%d to user %s", sequence, email_number, user_id)
        return False


def _process_triggers():
    """Check for and send all pending email triggers."""
    triggers = check_email_triggers()
    if not triggers:
        return

    logger.info("Found %d email triggers to process", len(triggers))

    with db.connection() as conn:
        for trigger in triggers:
            if _send_trigger(trigger, conn):
                # Log as sent for dedup
                log_lifecycle_event(
                    "email_triggered",
                    user_id=trigger["user_id"],
                    conn=conn,
                    sequence=trigger["email_sequence"],
                    email_number=trigger["email_number"],
                )
                logger.info(
                    "Sent %s #%d to user %s",
                    trigger["email_sequence"],
                    trigger["email_number"],
                    trigger["user_id"],
                )


def _process_churn_risk():
    """Detect at-risk users and log churn_risk_detected lifecycle events."""
    try:
        at_risk = get_at_risk_users(min_risk=60)
    except Exception:
        logger.exception("Failed to get at-risk users")
        return

    if not at_risk:
        return

    with db.connection() as conn:
        for user in at_risk:
            uid = str(user["user_id"])
            # Check if we already logged this recently (within 7 days)
            recent = conn.execute(
                """SELECT id FROM lifecycle_event
                   WHERE event_type = 'churn_risk_detected'
                     AND user_id = ?
                     AND created_at >= datetime('now', '-7 days')
                   LIMIT 1""",
                (uid,)
            ).fetchone()
            if not recent:
                log_lifecycle_event(
                    "churn_risk_detected",
                    user_id=uid,
                    conn=conn,
                    score=user["score"],
                    risk_level=user["risk_level"],
                )


def _check_streak_reminders():
    """Find users whose streak is at risk and send push notifications."""
    try:
        from .push import send_push_to_user
    except ImportError:
        return  # push module not available

    try:
        with db.connection() as conn:
            # Users who had a session yesterday but not today, and have streak_reminders on
            rows = conn.execute("""
                SELECT DISTINCT sl.user_id, u.display_name,
                    (SELECT COUNT(DISTINCT date(s2.started_at))
                     FROM session_log s2
                     WHERE s2.user_id = sl.user_id
                       AND s2.items_completed > 0
                       AND date(s2.started_at) >= date('now', '-30 days')
                       AND date(s2.started_at) < date('now')
                    ) as recent_days
                FROM session_log sl
                JOIN user u ON u.id = sl.user_id
                LEFT JOIN learner_profile lp ON lp.user_id = sl.user_id
                WHERE date(sl.started_at) = date('now', '-1 day')
                  AND sl.items_completed > 0
                  AND sl.user_id NOT IN (
                      SELECT user_id FROM session_log
                      WHERE date(started_at) = date('now')
                        AND items_completed > 0
                  )
                  AND COALESCE(lp.streak_reminders, 1) = 1
            """).fetchall()

            for row in rows:
                streak_days = row["recent_days"] or 1
                send_push_to_user(
                    conn, row["user_id"],
                    title=f"{streak_days}-day streak",
                    body="Items ready for review. About 5 minutes.",
                    url="/"
                )
    except Exception:
        logger.exception("Failed to check streak reminders")


def _send_weekly_progress_emails():
    """Send weekly progress digest every Monday at ~9am UTC."""
    from datetime import datetime, timezone
    now = datetime.now(UTC)
    # Only run on Mondays (weekday=0), roughly between 8-10 UTC
    if now.weekday() != 0 or now.hour < 8 or now.hour > 10:
        return

    try:
        with db.connection() as conn:
            # Find users with >=1 session in last 7 days, not opted out
            rows = conn.execute("""
                SELECT DISTINCT sl.user_id, u.email, u.display_name, u.marketing_opt_out
                FROM session_log sl
                JOIN user u ON u.id = sl.user_id
                WHERE sl.items_completed > 0
                  AND sl.started_at >= date('now', '-7 days')
                  AND u.is_active = 1
            """).fetchall()

            for row in rows:
                if row["marketing_opt_out"]:
                    continue

                uid = row["user_id"]

                # Check if weekly digest already sent this week
                already = conn.execute(
                    """SELECT id FROM lifecycle_event
                       WHERE event_type = 'email_triggered'
                         AND user_id = ?
                         AND json_extract(metadata, '$.sequence') = 'weekly_progress'
                         AND created_at >= date('now', '-6 days')
                       LIMIT 1""",
                    (str(uid),)
                ).fetchone()
                if already:
                    continue

                # Compute stats
                week = conn.execute(
                    """SELECT COUNT(*) as sessions,
                              COALESCE(SUM(items_completed), 0) as items,
                              COALESCE(SUM(items_correct), 0) as correct
                       FROM session_log
                       WHERE user_id = ? AND items_completed > 0
                         AND started_at >= date('now', '-7 days')""",
                    (uid,)
                ).fetchone()

                prev_week = conn.execute(
                    """SELECT COALESCE(SUM(items_correct), 0) as correct,
                              COALESCE(SUM(items_completed), 0) as completed
                       FROM session_log
                       WHERE user_id = ? AND items_completed > 0
                         AND started_at >= date('now', '-14 days')
                         AND started_at < date('now', '-7 days')""",
                    (uid,)
                ).fetchone()

                accuracy = round(week["correct"] / week["items"] * 100, 1) if week["items"] else None
                prev_acc = round(prev_week["correct"] / prev_week["completed"] * 100, 1) if prev_week["completed"] else None
                if accuracy is not None and prev_acc is not None:
                    trend = "up" if accuracy > prev_acc + 1 else ("down" if accuracy < prev_acc - 1 else "flat")
                else:
                    trend = "flat"

                # Words in long-term memory
                lt_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM progress
                       WHERE user_id = ? AND mastery_stage IN ('stable', 'durable')""",
                    (uid,)
                ).fetchone()
                words_lt = lt_row["cnt"] if lt_row else 0

                # Streak
                from .middleware import _compute_streak
                streak = _compute_streak(conn, user_id=uid)

                # Milestone
                thresholds = [25, 50, 100, 150, 200, 300, 500]
                next_ms = None
                sessions_to = None
                items_per = week["correct"] / week["sessions"] if week["sessions"] else 0
                for t in thresholds:
                    if words_lt < t:
                        next_ms = t
                        remaining = t - words_lt
                        sessions_to = max(1, round(remaining / items_per)) if items_per > 0 else None
                        break

                stats = {
                    "sessions": week["sessions"],
                    "items_reviewed": week["items"],
                    "accuracy": accuracy,
                    "accuracy_trend": trend,
                    "words_long_term": words_lt,
                    "streak_days": streak,
                    "next_milestone": next_ms,
                    "sessions_to_milestone": sessions_to,
                }

                if send_weekly_progress(row["email"], row["display_name"], stats, user_id=uid):
                    log_lifecycle_event(
                        "email_triggered",
                        user_id=str(uid),
                        conn=conn,
                        sequence="weekly_progress",
                        email_number=0,
                    )
    except Exception:
        logger.exception("Weekly progress email failed")


def _check_daily_reminders():
    """Find active users who haven't studied today and send a gentle push reminder."""
    try:
        from .push import send_push_to_user
    except ImportError:
        return  # push module not available

    try:
        with db.connection() as conn:
            # Users active in last 7 days who haven't studied today
            rows = conn.execute("""
                SELECT DISTINCT sl.user_id, u.display_name
                FROM session_log sl
                JOIN user u ON u.id = sl.user_id
                LEFT JOIN learner_profile lp ON lp.user_id = sl.user_id
                WHERE sl.items_completed > 0
                  AND sl.started_at >= date('now', '-7 days')
                  AND sl.user_id NOT IN (
                      SELECT user_id FROM session_log
                      WHERE date(started_at) = date('now')
                        AND items_completed > 0
                  )
                  AND COALESCE(lp.streak_reminders, 1) = 1
                GROUP BY sl.user_id
            """).fetchall()

            for row in rows:
                send_push_to_user(
                    conn, row["user_id"],
                    title="Ready to practice?",
                    body="A quick session keeps your memory fresh.",
                    url="/"
                )
    except Exception:
        logger.exception("Failed to check daily reminders")


def _run_loop():
    """Process email triggers + churn detection hourly."""
    from ..scheduler_lock import acquire_lock, release_lock

    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        # DB-backed lock: skip if another instance is already running
        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "email_scheduler", ttl_seconds=_HOURLY_SECONDS):
                    logger.debug("Email scheduler: another instance holds the lock, skipping")
                    if _stop_event.wait(_HOURLY_SECONDS):
                        break
                    continue
        except Exception:
            logger.exception("Email scheduler: lock acquisition failed")

        try:
            _process_triggers()
        except Exception:
            logger.exception("Email trigger processing failed")

        try:
            _process_churn_risk()
        except Exception:
            logger.exception("Churn risk processing failed")

        try:
            _check_streak_reminders()
        except Exception:
            logger.exception("Streak reminder check failed")

        try:
            _check_daily_reminders()
        except Exception:
            logger.exception("Daily reminder check failed")

        try:
            _send_weekly_progress_emails()
        except Exception:
            logger.exception("Weekly progress email failed")

        # Release lock after work completes
        try:
            with db.connection() as conn:
                release_lock(conn, "email_scheduler")
        except Exception:
            pass

        if _stop_event.wait(_HOURLY_SECONDS):
            break

    logger.info("Email scheduler stopped")
