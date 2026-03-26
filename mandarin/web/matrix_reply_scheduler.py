"""Matrix reply polling scheduler — checks for approval replies every 60 seconds.

Polls the Matrix DM room for new messages from the configured user.
Recognizes "approve <id>" and "reject <id>" commands and applies them
to the marketing_post_queue.

Follows the same threading/locking pattern as health_check_scheduler.py.
"""

import logging
import threading

from .. import db
from ..scheduler_lock import acquire_lock, release_lock

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 60   # Check every 60 seconds
_INITIAL_DELAY = 30           # 30 seconds after startup
_LOCK_TTL = 45                # Shorter than interval to avoid overlap

_stop_event = threading.Event()
_thread = None


def start():
    """Start the Matrix reply polling scheduler (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return

    # Skip if Matrix is not configured.
    from ..settings import MATRIX_ACCESS_TOKEN
    if not MATRIX_ACCESS_TOKEN:
        logger.debug("Matrix reply scheduler: MATRIX_ACCESS_TOKEN not set, not starting")
        return

    _stop_event.clear()
    _thread = threading.Thread(
        target=_run_loop, daemon=True, name="matrix-reply-poll"
    )
    _thread.start()
    logger.info("Matrix reply scheduler started (every %ds)", _POLL_INTERVAL_SECONDS)


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Main loop — wait initial delay, then poll every 60 seconds."""
    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        conn = None
        try:
            conn = db.get_connection()

            # DB-backed lock: skip if another instance is already running
            if not acquire_lock(conn, "matrix_reply_poll", ttl_seconds=_LOCK_TTL):
                logger.debug("Matrix reply poll: another instance holds the lock, skipping")
                if _stop_event.wait(_POLL_INTERVAL_SECONDS):
                    break
                continue

            _poll_tick()
            release_lock(conn, "matrix_reply_poll")

        except Exception:
            logger.exception("Matrix reply poll tick failed")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        if _stop_event.wait(_POLL_INTERVAL_SECONDS):
            break

    logger.info("Matrix reply scheduler stopped")


def _poll_tick():
    """Single poll tick — check for new commands and process them."""
    from ..notifications.matrix_client import poll_replies, process_approval_commands

    commands = poll_replies()
    if commands:
        logger.info("Matrix: received %d command(s): %s", len(commands), commands)
        results = process_approval_commands(commands)
        for r in results:
            logger.info("Matrix approval result: %s", r)
