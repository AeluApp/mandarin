"""Background thread for Signal bot polling via Matrix/Beeper bridge.

Polls every 10 seconds for inbound Signal messages, processes them
through the OpenClaw intent pipeline, and replies via Matrix.
"""

import logging
import threading

from ..scheduler_lock import acquire_lock, release_lock

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 10  # seconds
_INITIAL_DELAY = 30  # seconds after startup

_stop_event = threading.Event()
_thread = None


def start():
    """Start the Signal bot polling thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="signal-bot")
    _thread.start()
    logger.info("Signal bot scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Poll for Signal messages every 10 seconds."""
    from ..openclaw.signal_bot import is_configured, poll_once

    if not is_configured():
        logger.info("Signal bot: not configured (missing MATRIX or SIGNAL credentials), not starting")
        return

    if _stop_event.wait(_INITIAL_DELAY):
        return

    logger.info("Signal bot: polling started (every %ds)", _POLL_INTERVAL)

    while not _stop_event.is_set():
        try:
            poll_once()
        except Exception:
            logger.exception("Signal bot: poll error")

        if _stop_event.wait(_POLL_INTERVAL):
            break

    logger.info("Signal bot scheduler stopped")
