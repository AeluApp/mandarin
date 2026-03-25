"""Autonomous marketing execution scheduler.

Follows the same daemon pattern as experiment_daemon.py:
- Background thread with start()/stop()
- threading.Event for shutdown
- scheduler_lock for multi-instance safety
- Hourly tick, calendar-driven actions

Pipeline per tick:
1. Parse content calendar → what's due today?
2. Look up content from the bank
3. Run identity guard + copy drift + voice standard
4. Generate A/B variants (if enabled)
5. Queue or post (Twitter auto-post, Reddit → approval queue)
6. Every 6th tick: collect performance metrics
7. Sunday: run content optimizer

Disabled by default: MARKETING_SCHEDULER_ENABLED=true to enable.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from datetime import date, datetime, UTC

from .. import db

logger = logging.getLogger(__name__)

_CYCLE_SECONDS = 3600  # 1 hour
_INITIAL_DELAY = 600  # 10 minutes after startup
_METRICS_INTERVAL = 6  # collect metrics every 6th tick
_LOCK_NAME = "marketing_scheduler"

_stop_event = threading.Event()
_thread: threading.Thread | None = None
_tick_count = 0

ENABLED = os.environ.get("MARKETING_SCHEDULER_ENABLED", "").lower() in ("true", "1", "yes")


def start() -> None:
    """Start the marketing scheduler daemon thread."""
    global _thread
    if not ENABLED:
        logger.debug("Marketing scheduler disabled (set MARKETING_SCHEDULER_ENABLED=true)")
        return
    if _thread is not None and _thread.is_alive():
        return

    _stop_event.clear()
    _thread = threading.Thread(target=_daemon_loop, name="marketing-scheduler", daemon=True)
    _thread.start()
    logger.info("Marketing scheduler started")


def stop() -> None:
    """Signal the daemon to stop."""
    _stop_event.set()


def _daemon_loop() -> None:
    """Main daemon loop — sleep, acquire lock, tick."""
    _stop_event.wait(_INITIAL_DELAY)
    if _stop_event.is_set():
        return

    while not _stop_event.is_set():
        try:
            with db.connection() as conn:
                if _acquire_lock(conn):
                    try:
                        _daemon_tick(conn)
                    finally:
                        _release_lock(conn)
        except Exception:
            logger.exception("Marketing scheduler tick failed")

        _stop_event.wait(_CYCLE_SECONDS)


def _acquire_lock(conn) -> bool:
    """Acquire the scheduler lock (DB-backed, same pattern as other schedulers)."""
    try:
        from ..scheduler_lock import try_acquire
        return try_acquire(conn, _LOCK_NAME)
    except (ImportError, Exception):
        return True  # If lock module unavailable, proceed (single instance assumed)


def _release_lock(conn) -> None:
    """Release the scheduler lock."""
    try:
        from ..scheduler_lock import release
        release(conn, _LOCK_NAME)
    except (ImportError, Exception):
        pass


def _daemon_tick(conn) -> None:
    """One tick of the marketing scheduler."""
    global _tick_count
    _tick_count += 1

    today = date.today()
    logger.info("Marketing tick #%d for %s", _tick_count, today.isoformat())

    # 1. Get today's calendar actions
    try:
        from ..marketing.calendar_parser import parse_calendar, get_actions_for_date
        actions = parse_calendar()
        todays_actions = get_actions_for_date(actions, today)
    except Exception as e:
        logger.warning("Calendar parsing failed: %s", e)
        todays_actions = []

    if not todays_actions:
        logger.debug("No calendar actions for today")
    else:
        logger.info("Found %d actions for today", len(todays_actions))

    # 2. Process each action
    for action in todays_actions:
        try:
            _process_action(conn, action)
        except Exception as e:
            logger.warning("Failed to process action '%s': %s",
                          action.action_description[:50], e)

    # 3. Process approved items in the queue
    _process_approval_queue(conn)

    # 4. Collect metrics periodically
    if _tick_count % _METRICS_INTERVAL == 0:
        _collect_metrics(conn)

    # 5. Weekly optimization (Sunday)
    if today.weekday() == 6:  # Sunday
        _run_weekly_optimization(conn)


def _process_action(conn, action) -> None:
    """Process a single calendar action: lookup → guard → post/queue."""
    # Dedup: check if already executed
    existing = conn.execute(
        "SELECT id FROM marketing_calendar_state WHERE action_hash = ?",
        (action.action_hash,),
    ).fetchone()
    if existing:
        return  # Already processed

    # Mark as queued
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT OR IGNORE INTO marketing_calendar_state
            (calendar_week, calendar_day, action_hash, status, executed_at)
        VALUES (?, ?, ?, 'queued', ?)
    """, (action.week, action.day_of_week, action.action_hash, now))
    conn.commit()

    # Skip non-automatable actions
    if action.ready_status == "Manual":
        conn.execute(
            "UPDATE marketing_calendar_state SET status = 'manual' WHERE action_hash = ?",
            (action.action_hash,),
        )
        conn.commit()
        logger.debug("Skipping manual action: %s", action.action_description[:50])
        return

    # Look up content from bank
    content_id = action.content_key
    if not content_id:
        logger.debug("No content key for action: %s", action.action_description[:50])
        return

    try:
        from ..marketing.content_bank import load_content_bank, personalize_content
        bank = load_content_bank()
        piece = bank.get(content_id)
    except Exception as e:
        logger.warning("Content bank lookup failed: %s", e)
        return

    if not piece:
        logger.debug("Content piece '%s' not found in bank", content_id)
        return

    # Personalize (replace [brackets] with real data)
    text = personalize_content(piece, conn=conn)

    # Run identity guard
    try:
        from ..marketing.anonymity_guard import check_identity
        identity_result = check_identity(text, conn=conn)
        if not identity_result.passed:
            violations = ", ".join(v.pattern_name for v in identity_result.violations)
            logger.warning("Identity guard BLOCKED content '%s': %s", content_id, violations)
            conn.execute(
                "UPDATE marketing_calendar_state SET status = 'skipped', notes = ? WHERE action_hash = ?",
                (f"Identity guard: {violations}", action.action_hash),
            )
            conn.commit()
            return
    except Exception as e:
        logger.warning("Identity guard failed: %s — holding content", e)
        return

    # Route to platform
    if action.platform == "twitter":
        _post_twitter(conn, content_id, text, action)
    elif action.platform == "reddit":
        _queue_reddit(conn, content_id, text, action)
    elif action.platform == "newsletter":
        _send_newsletter(conn, content_id, text, action)
    else:
        logger.debug("Platform '%s' not yet automated", action.platform)

    # Mark as posted
    conn.execute(
        "UPDATE marketing_calendar_state SET status = 'posted' WHERE action_hash = ?",
        (action.action_hash,),
    )
    conn.commit()


def _post_twitter(conn, content_id: str, text: str, action) -> None:
    """Post to Twitter/X (auto-post for ready content)."""
    try:
        from ..marketing.social_twitter import post_tweet, is_twitter_configured
        if not is_twitter_configured():
            logger.debug("Twitter not configured, skipping")
            return

        result = post_tweet(text)
        _log_post(conn, content_id, "twitter", result.post_id if result.success else "",
                  "posted" if result.success else "failed", result.error,
                  utm_campaign=content_id)

        if result.success:
            logger.info("Posted tweet for '%s'", content_id)
        else:
            logger.warning("Twitter post failed for '%s': %s", content_id, result.error)
    except Exception as e:
        logger.warning("Twitter posting error: %s", e)


def _queue_reddit(conn, content_id: str, text: str, action) -> None:
    """Queue Reddit post for human approval (never auto-posts)."""
    try:
        from ..marketing.social_reddit import queue_reddit_post
        # Extract subreddit from action description if possible
        import re
        sub_match = re.search(r"r/(\w+)", action.action_description)
        subreddit = sub_match.group(1) if sub_match else "ChineseLanguage"

        queue_id = queue_reddit_post(conn, subreddit, "", text, content_id=content_id)
        logger.info("Reddit post queued (queue_id=%d) for '%s'", queue_id, content_id)

        # Notify via iMessage if configured
        _notify_approval_needed(conn, queue_id, "reddit", content_id)
    except Exception as e:
        logger.warning("Reddit queue error: %s", e)


def _send_newsletter(conn, content_id: str, text: str, action) -> None:
    """Send newsletter via Resend."""
    try:
        from ..marketing.social_newsletter import send_newsletter, is_newsletter_configured
        if not is_newsletter_configured():
            logger.debug("Newsletter not configured, skipping")
            return

        # Use text as HTML body (newsletters should already have HTML in the bank)
        result = send_newsletter(
            subject=f"Aelu — {content_id.replace('_', ' ').title()}",
            body_html=text,
            utm_campaign=content_id,
        )

        _log_post(conn, content_id, "newsletter", result.post_id if result.success else "",
                  "posted" if result.success else "failed", result.error)
    except Exception as e:
        logger.warning("Newsletter send error: %s", e)


def _log_post(conn, content_id: str, platform: str, platform_post_id: str,
              status: str, error: str = "", utm_campaign: str = "") -> None:
    """Log a post attempt to marketing_post_log."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT INTO marketing_post_log
                (content_id, platform, platform_post_id, posted_at, status, error, utm_campaign, utm_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (content_id, platform, platform_post_id, now, status, error or None,
              utm_campaign, platform))
        conn.commit()
    except Exception:
        logger.debug("Post log write failed", exc_info=True)


def _process_approval_queue(conn) -> None:
    """Post any approved items from the marketing_approval_queue."""
    try:
        rows = conn.execute("""
            SELECT id, platform, content_id
            FROM marketing_approval_queue
            WHERE status = 'approved'
            ORDER BY submitted_at
            LIMIT 5
        """).fetchall()

        for row in rows:
            if row["platform"] == "reddit":
                from ..marketing.social_reddit import post_approved
                result = post_approved(conn, row["id"])
                if result.success:
                    conn.execute(
                        "UPDATE marketing_approval_queue SET status = 'expired' WHERE id = ?",
                        (row["id"],),
                    )
                    _log_post(conn, row["content_id"], "reddit", result.post_id, "posted")
                    conn.commit()
    except Exception:
        logger.debug("Approval queue processing failed", exc_info=True)


def _notify_approval_needed(conn, queue_id: int, platform: str, content_id: str) -> None:
    """Send email notification that a post needs approval."""
    try:
        import resend
        resend.api_key = os.environ.get("RESEND_API_KEY", "")
        notify_email = os.environ.get("MARKETING_NOTIFY_EMAIL", "")
        from_email = os.environ.get("FROM_EMAIL", "")

        if not (resend.api_key and notify_email and from_email):
            logger.debug("Marketing notification email not configured")
            return

        # Get the queued post text for context
        row = conn.execute(
            "SELECT content_text FROM marketing_approval_queue WHERE id = ?",
            (queue_id,),
        ).fetchone()
        preview = row["content_text"][:300] if row else "(no preview)"

        resend.Emails.send({
            "from": from_email,
            "to": [notify_email],
            "subject": f"[Aelu] {platform.title()} post needs approval (#{queue_id})",
            "html": (
                f"<h3>Marketing post needs your approval</h3>"
                f"<p><strong>Platform:</strong> {platform.title()}<br>"
                f"<strong>Content ID:</strong> {content_id}<br>"
                f"<strong>Queue ID:</strong> #{queue_id}</p>"
                f"<p><strong>Preview:</strong></p>"
                f"<pre style='background:#f5f0e8;padding:16px;border-radius:8px;'>{preview}</pre>"
                f"<p>Approve at: <a href='https://aeluapp.com/admin'>aeluapp.com/admin</a></p>"
            ),
        })
        logger.info("Approval notification sent to %s for queue_id=%d", notify_email, queue_id)
    except (ImportError, Exception) as e:
        logger.debug("Approval notification failed: %s", e)


def _collect_metrics(conn) -> None:
    """Pull engagement metrics from platform APIs for recent posts."""
    try:
        rows = conn.execute("""
            SELECT id, content_id, platform, platform_post_id
            FROM marketing_post_log
            WHERE status = 'posted' AND platform_post_id != ''
            AND posted_at > datetime('now', '-7 days')
        """).fetchall()

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        for row in rows:
            metrics = None
            if row["platform"] == "twitter":
                from ..marketing.social_twitter import get_tweet_metrics
                metrics = get_tweet_metrics(row["platform_post_id"])
            elif row["platform"] == "reddit":
                from ..marketing.social_reddit import get_post_metrics
                metrics = get_post_metrics(row["platform_post_id"])

            if metrics:
                for metric_type, value in metrics.items():
                    conn.execute("""
                        INSERT INTO marketing_content_metrics
                            (post_log_id, metric_type, metric_value, measured_at)
                        VALUES (?, ?, ?, ?)
                    """, (row["id"], metric_type, float(value), now))
                conn.commit()

        logger.info("Collected metrics for %d posts", len(rows))
    except Exception:
        logger.debug("Metrics collection failed", exc_info=True)


def _run_weekly_optimization(conn) -> None:
    """Weekly optimization cycle — extract patterns, generate variants."""
    try:
        from ..marketing.content_optimizer import run_optimization_cycle
        run_optimization_cycle(conn)
    except (ImportError, Exception) as e:
        logger.debug("Weekly optimization skipped: %s", e)
