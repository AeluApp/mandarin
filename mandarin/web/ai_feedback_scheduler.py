"""Background thread for AI drill generation from vocab encounters."""

import logging
import threading

from .. import db

logger = logging.getLogger(__name__)

_DAILY_SECONDS = 86400
_INITIAL_DELAY = 600  # 10 min after startup

_stop_event = threading.Event()
_thread = None


def start():
    """Start the AI feedback background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="ai-feedback")
    _thread.start()
    logger.info("AI feedback scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Process pending encounters daily."""
    from ..scheduler_lock import acquire_lock, release_lock

    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "ai_feedback", ttl_seconds=_DAILY_SECONDS):
                    logger.debug("AI feedback: another instance holds the lock, skipping")
                    if _stop_event.wait(_DAILY_SECONDS):
                        break
                    continue
        except Exception:
            logger.exception("AI feedback: lock acquisition failed")
            if _stop_event.wait(_DAILY_SECONDS):
                break
            continue

        try:
            _process()
        except Exception:
            logger.exception("AI feedback processing failed")

        try:
            with db.connection() as conn:
                release_lock(conn, "ai_feedback")
        except Exception:
            pass

        if _stop_event.wait(_DAILY_SECONDS):
            break

    logger.info("AI feedback scheduler stopped")


def _process():
    """Run encounter→drill batch processing."""
    from ..ai.ollama_client import is_ollama_available

    if not is_ollama_available():
        logger.debug("AI feedback: Ollama not available, skipping")
        return

    from ..ai.drill_generator import process_pending_encounters

    with db.connection() as conn:
        result = process_pending_encounters(conn, max_batch=20)
        logger.info("AI feedback: %s", result)
