"""Background thread for periodic data retention purging."""

import logging
import threading
import time

from .. import db
from ..data_retention import purge_expired

logger = logging.getLogger(__name__)

_WEEKLY_SECONDS = 7 * 24 * 3600
_INITIAL_DELAY = 60  # Wait 60s after startup before first purge

_stop_event = threading.Event()
_thread = None


def start():
    """Start the retention purge background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="retention-purge")
    _thread.start()
    logger.info("Retention purge scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Purge expired data on startup + weekly."""
    from ..scheduler_lock import acquire_lock, release_lock

    # Initial delay — let the app finish starting up
    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        # DB-backed lock: skip if another instance is already running
        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "retention_purge", ttl_seconds=_WEEKLY_SECONDS):
                    logger.debug("Retention purge: another instance holds the lock, skipping")
                    if _stop_event.wait(_WEEKLY_SECONDS):
                        break
                    continue
        except Exception:
            logger.exception("Retention purge: lock acquisition failed")

        try:
            with db.connection() as conn:
                results = purge_expired(conn)
            if any(v > 0 for v in results.values()):
                logger.info("Retention purge results: %s", results)
            else:
                logger.debug("Retention purge: nothing to purge")
        except Exception:
            logger.exception("Retention purge failed")

        # Release lock after work completes
        try:
            with db.connection() as conn:
                release_lock(conn, "retention_purge")
        except Exception:
            pass

        # Wait one week (or until stop signal)
        if _stop_event.wait(_WEEKLY_SECONDS):
            break

    logger.info("Retention purge scheduler stopped")
