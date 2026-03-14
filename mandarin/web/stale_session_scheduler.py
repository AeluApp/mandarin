"""Background thread for periodic stale session cleanup.

Runs hourly: marks sessions that started >1 hour ago with no end_time as
'interrupted'. Uses DB-backed lock for multi-instance safety.
"""

import logging
import threading

from .. import db

logger = logging.getLogger(__name__)

_HOURLY_SECONDS = 3600
_stop_event = threading.Event()
_thread = None


def cleanup_stale_sessions():
    """Mark sessions older than 1 hour with no end time as interrupted."""
    try:
        with db.connection() as conn:
            cur = conn.execute("""
                UPDATE session_log
                SET session_outcome = 'interrupted',
                    ended_at = datetime('now'),
                    early_exit = 1
                WHERE session_outcome = 'started'
                  AND ended_at IS NULL
                  AND started_at < datetime('now', '-1 hour')
            """)
            conn.commit()
            if cur.rowcount:
                logger.info("Marked %d orphaned session(s) as interrupted", cur.rowcount)
    except Exception as e:
        logger.warning("Orphaned session cleanup failed: %s", e)


def start():
    """Start the stale session cleanup background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()

    # Run once immediately at startup
    cleanup_stale_sessions()

    _thread = threading.Thread(target=_run_loop, daemon=True, name="stale-session-cleanup")
    _thread.start()
    logger.info("Stale session cleanup scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Clean up stale sessions hourly with DB-backed lock."""
    from ..scheduler_lock import acquire_lock, release_lock

    while not _stop_event.is_set():
        if _stop_event.wait(_HOURLY_SECONDS):
            break

        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "stale_session_cleanup", ttl_seconds=_HOURLY_SECONDS):
                    continue
        except Exception:
            continue

        cleanup_stale_sessions()

        try:
            with db.connection() as conn:
                release_lock(conn, "stale_session_cleanup")
        except Exception:
            pass

    logger.info("Stale session cleanup scheduler stopped")
