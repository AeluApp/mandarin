"""Background thread for periodic web crawling (Doc 23 A-05).

Runs every 6 hours, checks crawl_source table for sources due for crawl.
Uses same pattern as email_scheduler.py (threading.Thread + scheduler_lock).
"""

import logging
import threading

from .. import db

logger = logging.getLogger(__name__)

_SIX_HOURS = 21600
_INITIAL_DELAY = 600  # Wait 10 minutes after startup

_stop_event = threading.Event()
_thread = None


def start():
    """Start the crawl scheduler background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="crawl-scheduler")
    _thread.start()
    logger.info("Crawl scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Crawl due sources every 6 hours."""
    from ..scheduler_lock import acquire_lock, release_lock

    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "crawl_scheduler", ttl_seconds=_SIX_HOURS):
                    logger.debug("Crawl scheduler: another instance holds the lock, skipping")
                    if _stop_event.wait(_SIX_HOURS):
                        break
                    continue
        except Exception:
            logger.exception("Crawl scheduler: lock acquisition failed")
            if _stop_event.wait(_SIX_HOURS):
                break
            continue

        try:
            _run_crawls()
        except Exception:
            logger.exception("Crawl scheduler: crawl run failed")

        try:
            _run_research_discovery()
        except Exception:
            logger.exception("Crawl scheduler: research discovery failed")

        # Release lock
        try:
            with db.connection() as conn:
                release_lock(conn, "crawl_scheduler")
        except Exception:
            pass

        if _stop_event.wait(_SIX_HOURS):
            break

    logger.info("Crawl scheduler stopped")


def _run_crawls():
    """Crawl all sources that are due."""
    from ..ai.web_crawler import get_sources_due_for_crawl, crawl_source

    with db.connection() as conn:
        sources = get_sources_due_for_crawl(conn)
        logger.info("Crawl scheduler: %d sources due for crawl", len(sources))
        for source in sources:
            try:
                result = crawl_source(conn, source["id"])
                logger.info("Crawled %s: %s", source["name"], result.get("status"))
            except Exception as e:
                logger.warning("Crawl source %s failed: %s", source["name"], e)


def _run_research_discovery():
    """Run weekly research discovery (only on first crawl of the week)."""
    from ..ai.research_synthesis import discover_papers, score_relevance

    with db.connection() as conn:
        # Check if we've already run this week
        try:
            last = conn.execute("""
                SELECT MAX(created_at) as last_run FROM research_paper
                WHERE created_at >= datetime('now', '-7 days')
            """).fetchone()
            if last and last["last_run"]:
                return  # Already ran this week
        except Exception:
            pass

        try:
            papers = discover_papers(conn)
            for paper in papers:
                if paper.get("id"):
                    score_relevance(conn, paper["id"])
            logger.info("Research discovery: %d papers found", len(papers))
        except Exception as e:
            logger.warning("Research discovery failed: %s", e)
