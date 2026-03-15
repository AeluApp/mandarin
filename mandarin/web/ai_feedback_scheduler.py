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
    """Run encounter→drill batch processing + quality checks."""
    from ..ai.ollama_client import is_ollama_available

    if not is_ollama_available():
        logger.debug("AI feedback: Ollama not available, skipping drill generation")
    else:
        from ..ai.drill_generator import process_pending_encounters
        with db.connection() as conn:
            result = process_pending_encounters(conn, max_batch=20)
            logger.info("AI feedback drill generation: %s", result)

    # Audio coherence: batch-check unchecked items (runs even without Ollama)
    try:
        from ..ai.audio_coherence import batch_check_coherence
        with db.connection() as conn:
            coherence_results = batch_check_coherence(conn, limit=20)
            passed = sum(1 for r in coherence_results if r.get("passed"))
            logger.info("AI feedback audio coherence: %d/%d passed",
                        passed, len(coherence_results))
    except Exception:
        logger.debug("Audio coherence batch check skipped", exc_info=True)

    # RAG enrichment: add example sentences to knowledge base entries
    try:
        from ..ai.rag_layer import enrich_with_example_sentences
        with db.connection() as conn:
            enrich_result = enrich_with_example_sentences(conn, min_hsk_level=5)
            if enrich_result.get("enriched", 0) > 0:
                logger.info("AI feedback RAG enrichment: %s", enrich_result)
    except Exception:
        logger.debug("RAG enrichment skipped", exc_info=True)

    # Stale workflow detection: find and retry stuck workflows
    try:
        from ..ai.workflow_engine import get_stale_workflows
        with db.connection() as conn:
            stale = get_stale_workflows(conn, max_age_hours=12)
            if stale:
                logger.warning("AI feedback: %d stale workflows found", len(stale))
    except Exception:
        logger.debug("Stale workflow check skipped", exc_info=True)
