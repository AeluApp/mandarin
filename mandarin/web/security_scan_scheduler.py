"""Background thread for weekly automated security scanning."""

import logging
import threading

from .. import db
from ..security_scanner import run_full_scan

logger = logging.getLogger(__name__)

_WEEKLY_SECONDS = 7 * 24 * 3600
_INITIAL_DELAY = 120  # Wait 2min after startup before first scan

_stop_event = threading.Event()
_thread = None


def start():
    """Start the security scan background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="security-scan")
    _thread.start()
    logger.info("Security scan scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Run full security scan on startup + weekly."""
    from ..scheduler_lock import acquire_lock, release_lock

    # Initial delay — let the app finish starting up
    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        # DB-backed lock: skip if another instance is already running
        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "security_scan", ttl_seconds=_WEEKLY_SECONDS):
                    logger.debug("Security scan: another instance holds the lock, skipping")
                    if _stop_event.wait(_WEEKLY_SECONDS):
                        break
                    continue
        except Exception:
            logger.exception("Security scan: lock acquisition failed")

        try:
            with db.connection() as conn:
                results = run_full_scan(conn)
            combined = results.get("combined", {})
            high_count = combined.get("high", 0)
            if high_count > 0:
                logger.critical("Security scan: %d HIGH severity findings!", high_count)
            else:
                logger.info("Security scan completed: %s", combined)
        except Exception:
            logger.exception("Security scan failed")

        # Release lock after work completes
        try:
            with db.connection() as conn:
                release_lock(conn, "security_scan")
        except Exception:
            pass

        # Wait one week (or until stop signal)
        if _stop_event.wait(_WEEKLY_SECONDS):
            break

    logger.info("Security scan scheduler stopped")
