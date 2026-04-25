"""Nightly intelligence batch — runs daily at 03:00 UTC.

1. Measure delayed recall for samples that are 24h+ old
2. Run monthly intelligence self-audit (1st of month only)
3. Log lifecycle event
"""

import logging
import threading
from datetime import datetime, timezone, UTC

from .. import db
from ..scheduler_lock import acquire_lock, release_lock

logger = logging.getLogger(__name__)

_DAILY_SECONDS = 86400
_INITIAL_DELAY = 60  # 1 minute after startup

_stop_event = threading.Event()
_thread = None


def start():
    """Start the nightly intelligence scheduler (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(
        target=_run_loop, daemon=True, name="nightly-intelligence"
    )
    _thread.start()
    logger.info("Nightly intelligence scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _seconds_until_next_run(target_hour: int = 3) -> int:
    """Seconds until the next occurrence of target_hour UTC."""
    from datetime import timedelta
    now = datetime.now(UTC)
    target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return max(int((target - now).total_seconds()), 60)


def _run_loop():
    """Main loop — wait until 03:00 UTC, run tick, repeat daily."""
    if _stop_event.wait(_INITIAL_DELAY):
        return

    # Catch-up: if last digest was >24h ago, run immediately on startup
    # (handles missed runs due to redeployments crossing the 03:00 window)
    try:
        catch_conn = db.get_connection()
        last_event = catch_conn.execute("""
            SELECT MAX(created_at) FROM openclaw_message_log
            WHERE agent_type = 'nightly_intelligence'
        """).fetchone()
        last_ts = last_event[0] if last_event and last_event[0] else None
        catch_conn.close()

        should_catch_up = True
        if last_ts:
            from datetime import timedelta
            last_dt = datetime.fromisoformat(last_ts).replace(tzinfo=UTC)
            if (datetime.now(UTC) - last_dt).total_seconds() < _DAILY_SECONDS:
                should_catch_up = False

        if should_catch_up:
            logger.info("Nightly intelligence: catch-up run (missed scheduled window)")
            conn = db.get_connection()
            try:
                if acquire_lock(conn, "nightly_intelligence", ttl_seconds=3600):
                    _intelligence_tick(conn)
                    release_lock(conn, "nightly_intelligence")
                    # Log so we don't catch up again
                    conn.execute("""
                        INSERT INTO openclaw_message_log
                        (agent_type, direction, message_text, user_id)
                        VALUES ('nightly_intelligence', 'outbound', 'catch-up digest sent', 1)
                    """)
                    conn.commit()
            except Exception:
                logger.exception("Nightly intelligence catch-up failed")
            finally:
                conn.close()
    except Exception:
        logger.debug("Nightly intelligence: catch-up check failed", exc_info=True)

    while not _stop_event.is_set():
        # Sleep until next 03:00 UTC
        wait_seconds = _seconds_until_next_run(target_hour=3)
        if _stop_event.wait(wait_seconds):
            break

        conn = None
        try:
            conn = db.get_connection()
            if not acquire_lock(conn, "nightly_intelligence", ttl_seconds=3600):
                logger.debug("Nightly intelligence: lock held, skipping")
                continue

            _intelligence_tick(conn)
            release_lock(conn, "nightly_intelligence")

        except Exception:
            logger.exception("Nightly intelligence tick failed")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    logger.info("Nightly intelligence scheduler stopped")


def _intelligence_tick(conn):
    """Single nightly tick."""
    now = datetime.now(UTC)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    actions = []

    # 1. Measure delayed recall for 24h+ samples
    try:
        from ..counter_metrics import delayed_recall_accuracy
        result = delayed_recall_accuracy(conn)
        measured = result.get("sample_size", 0)
        if measured > 0:
            actions.append(f"measured {measured} delayed recall samples")
            logger.info("Measured %d delayed recall samples", measured)
    except Exception:
        logger.exception("Failed to measure delayed recall")

    # 2. Monthly intelligence audit (1st of month)
    if now.day == 1:
        try:
            from ..intelligence_audit import run_monthly_audit
            audit = run_monthly_audit(conn)
            actions.append(f"monthly audit: {audit.get('audit_type', 'unknown')}")
            logger.info("Monthly intelligence audit completed")
        except Exception:
            logger.exception("Failed to run monthly intelligence audit")

    # 3. Send daily intelligence digest email
    try:
        from ..email import send_daily_intelligence_digest
        send_daily_intelligence_digest(conn)
        actions.append("sent daily intelligence digest")
    except Exception:
        logger.exception("Failed to send daily intelligence digest")

    # 4. Log lifecycle event
    try:
        from ..marketing_hooks import log_lifecycle_event
        log_lifecycle_event(
            "intelligence_tick",
            user_id="1",
            conn=conn,
            actions=actions,
            timestamp=now_str,
        )
    except Exception:
        pass

    logger.info("Nightly intelligence tick: %d actions", len(actions))
