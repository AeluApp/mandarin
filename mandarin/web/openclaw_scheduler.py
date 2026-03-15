"""Background thread for OpenClaw scheduled agent triggers.

Runs agent checks periodically:
- Study reminders: 8am, 12pm, 6pm (checks every hour)
- Review queue monitor: every hour (fires when items pending >1hr)
- Audit briefing: weekly after product audit
"""

import logging
import threading
from datetime import datetime

from .. import db

logger = logging.getLogger(__name__)

_ONE_HOUR = 3600
_INITIAL_DELAY = 300  # 5 min after startup

_stop_event = threading.Event()
_thread = None


def start():
    """Start the OpenClaw scheduler (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="openclaw-scheduler")
    _thread.start()
    logger.info("OpenClaw scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Check agent triggers every hour."""
    from ..scheduler_lock import acquire_lock, release_lock

    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "openclaw_scheduler", ttl_seconds=_ONE_HOUR):
                    if _stop_event.wait(_ONE_HOUR):
                        break
                    continue
        except Exception:
            logger.exception("OpenClaw scheduler: lock failed")
            if _stop_event.wait(_ONE_HOUR):
                break
            continue

        try:
            _check_study_reminder()
        except Exception:
            logger.debug("Study reminder check failed", exc_info=True)

        try:
            _check_review_queue()
        except Exception:
            logger.debug("Review queue check failed", exc_info=True)

        try:
            _check_audit_briefing()
        except Exception:
            logger.debug("Audit briefing check failed", exc_info=True)

        try:
            with db.connection() as conn:
                release_lock(conn, "openclaw_scheduler")
        except Exception:
            pass

        if _stop_event.wait(_ONE_HOUR):
            break

    logger.info("OpenClaw scheduler stopped")


def _check_study_reminder():
    """Fire study reminder at 8am, 12pm, 6pm if due items exist."""
    now = datetime.now()
    hour = now.hour

    # Only fire at reminder hours
    if hour not in (8, 12, 18):
        return

    with db.connection() as conn:
        # Check if reminders are enabled
        profile = conn.execute(
            "SELECT streak_reminders FROM learner_profile WHERE user_id = 1"
        ).fetchone()
        if profile and not profile["streak_reminders"]:
            return

        # Count due items
        due = conn.execute("""
            SELECT COUNT(*) as cnt FROM progress
            WHERE user_id = 1 AND next_review_date <= date('now')
        """).fetchone()
        due_count = due["cnt"] if due else 0

        if due_count == 0:
            return

        # Check if we already fired this hour
        already_fired = conn.execute("""
            SELECT id FROM openclaw_message_log
            WHERE agent_type = 'study_reminder'
            AND created_at >= datetime('now', '-1 hour')
        """).fetchone()
        if already_fired:
            return

        # Build reminder message
        struggling = conn.execute("""
            SELECT ci.hanzi, ci.pinyin
            FROM progress p
            JOIN content_item ci ON ci.id = p.content_item_id
            WHERE p.user_id = 1 AND p.next_review_date <= date('now')
            ORDER BY p.half_life_days ASC
            LIMIT 2
        """).fetchall()

        struggle_text = ""
        if struggling:
            items = [f"{r['hanzi']} ({r['pinyin']})" for r in struggling]
            struggle_text = f" {' and '.join(items)} need attention."

        est_minutes = max(1, due_count // 2)
        message = (
            f"You have {due_count} items due for review (~{est_minutes} minutes)."
            f"{struggle_text} Ready?"
        )

        # Log the reminder (actual delivery depends on configured transport)
        conn.execute("""
            INSERT INTO openclaw_message_log
            (agent_type, direction, message_text, user_id)
            VALUES ('study_reminder', 'outbound', ?, 1)
        """, (message,))
        conn.commit()
        logger.info("Study reminder: %s", message)


def _check_review_queue():
    """Alert admin when AI-generated items are pending review for >1 hour."""
    with db.connection() as conn:
        try:
            pending = conn.execute("""
                SELECT COUNT(*) as cnt FROM pi_ai_review_queue
                WHERE status = 'pending'
                AND created_at <= datetime('now', '-1 hour')
            """).fetchone()
            pending_count = pending["cnt"] if pending else 0
        except Exception:
            return

        if pending_count == 0:
            return

        # Check if we already alerted this cycle
        already_alerted = conn.execute("""
            SELECT id FROM openclaw_message_log
            WHERE agent_type = 'review_queue'
            AND created_at >= datetime('now', '-1 hour')
        """).fetchone()
        if already_alerted:
            return

        message = f"{pending_count} items pending review (oldest >1 hour). Review in admin panel."

        conn.execute("""
            INSERT INTO openclaw_message_log
            (agent_type, direction, message_text, user_id)
            VALUES ('review_queue', 'outbound', ?, 1)
        """, (message,))
        conn.commit()
        logger.info("Review queue alert: %s", message)


def _check_audit_briefing():
    """Send weekly audit summary after product audit completes."""
    with db.connection() as conn:
        try:
            # Check if audit ran this week and we haven't briefed yet
            latest_audit = conn.execute("""
                SELECT id, overall_grade, overall_score, created_at
                FROM product_audit
                WHERE created_at >= datetime('now', '-7 days')
                ORDER BY created_at DESC LIMIT 1
            """).fetchone()
        except Exception:
            return

        if not latest_audit:
            return

        # Check if we already briefed for this audit
        already_briefed = conn.execute("""
            SELECT id FROM openclaw_message_log
            WHERE agent_type = 'audit_briefing'
            AND message_text LIKE ?
        """, (f"%audit #{latest_audit['id']}%",)).fetchone()
        if already_briefed:
            return

        # Count findings needing attention
        try:
            findings = conn.execute("""
                SELECT COUNT(*) as cnt FROM pi_finding
                WHERE severity IN ('critical', 'high')
                AND status = 'open'
            """).fetchone()
            finding_count = findings["cnt"] if findings else 0
        except Exception:
            finding_count = 0

        grade = latest_audit.get("overall_grade", "?")
        score = latest_audit.get("overall_score", 0)
        message = (
            f"Weekly audit #{latest_audit['id']} complete. "
            f"Grade: {grade} ({score:.1f}). "
            f"{finding_count} findings need attention."
        )

        conn.execute("""
            INSERT INTO openclaw_message_log
            (agent_type, direction, message_text, user_id)
            VALUES ('audit_briefing', 'outbound', ?, 1)
        """, (message,))
        conn.commit()
        logger.info("Audit briefing: %s", message)
