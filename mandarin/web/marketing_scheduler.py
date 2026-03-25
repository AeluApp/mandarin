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

    # Run quality gates: identity + voice + LLM quality score
    # If content fails, attempt LLM rewrite before blocking
    gate_result = _run_quality_gates(conn, text, content_id)
    if not gate_result["passed"]:
        # Try to fix it via LLM rewrite
        fixed_text = _attempt_quality_fix(conn, text, gate_result["reason"])
        if fixed_text:
            # Re-check the fixed version
            recheck = _run_quality_gates(conn, fixed_text, content_id)
            if recheck["passed"]:
                text = fixed_text
                logger.info("Auto-fixed content '%s' (was: %s)", content_id, gate_result["reason"])
            else:
                conn.execute(
                    "UPDATE marketing_calendar_state SET status = 'skipped', notes = ? WHERE action_hash = ?",
                    (f"Failed after fix attempt: {recheck['reason']}", action.action_hash),
                )
                conn.commit()
                logger.warning("Quality gate BLOCKED '%s' after fix attempt: %s", content_id, recheck["reason"])
                return
        else:
            conn.execute(
                "UPDATE marketing_calendar_state SET status = 'skipped', notes = ? WHERE action_hash = ?",
                (gate_result["reason"], action.action_hash),
            )
            conn.commit()
            logger.warning("Quality gate BLOCKED '%s': %s", content_id, gate_result["reason"])
            return

    # Route to platform
    if action.platform == "twitter":
        _post_twitter(conn, content_id, text, action)
    elif action.platform == "reddit":
        _queue_reddit(conn, content_id, text, action)
    elif action.platform == "newsletter":
        _send_newsletter(conn, content_id, text, action)
    elif action.platform == "youtube":
        # YouTube/TikTok/Reels — cross-post as TikTok carousel
        _post_tiktok(conn, content_id, text, action)
        # Also generate XHS bilingual version
        _generate_xhs(conn, content_id, text)
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


def _attempt_quality_fix(conn, text: str, issue: str) -> str | None:
    """Attempt to fix low-quality content via LLM rewrite.

    Returns the fixed text, or None if rewrite fails or isn't appropriate.
    Identity violations (founder name) are always fixable.
    Voice violations (praise inflation) are fixable.
    Very low quality scores may not be salvageable.
    """
    try:
        from ..ai.ollama_client import generate as llm_generate, is_llm_available
        if not is_llm_available():
            return None

        resp = llm_generate(
            prompt=(
                f"This social media post for a Mandarin learning app failed quality review.\n\n"
                f"Issue: {issue}\n\n"
                f"Original post:\n{text}\n\n"
                f"Rewrite it to fix the issue while keeping the core message. Rules:\n"
                f"- Keep first-person 'I' voice but never reveal who 'I' is (no names, employers, photos)\n"
                f"- No praise inflation (Amazing!, Incredible!)\n"
                f"- No urgency language (Don't miss, Act now, Limited time)\n"
                f"- Keep the educational insight intact\n"
                f"- Stay under {len(text) + 50} characters\n\n"
                f"Respond with ONLY the rewritten post text, nothing else."
            ),
            system="You are a social media editor. Fix the issue while preserving the content's value.",
            temperature=0.4,
            max_tokens=500,
            conn=conn,
            task_type="voice_audit",
        )

        if resp.success and resp.text.strip():
            fixed = resp.text.strip()
            # Strip any wrapping quotes the LLM might add
            if fixed.startswith('"') and fixed.endswith('"'):
                fixed = fixed[1:-1]
            return fixed
        return None

    except (ImportError, Exception) as e:
        logger.debug("Quality fix attempt failed: %s", e)
        return None


def _run_quality_gates(conn, text: str, content_id: str) -> dict:
    """Run all quality gates on content before posting. Returns {passed, reason, score}.

    Gates (all must pass):
    1. Identity guard — no founder name/identity
    2. Voice standard — no praise inflation, urgency marketing
    3. LLM quality score — cloud model rates content 1-10, must score ≥ 7
    """
    # Gate 1: Identity guard
    try:
        from ..marketing.anonymity_guard import check_identity
        identity_result = check_identity(text, conn=conn)
        if not identity_result.passed:
            violations = ", ".join(v.pattern_name for v in identity_result.violations)
            return {"passed": False, "reason": f"Identity guard: {violations}", "score": 0}
    except Exception as e:
        return {"passed": False, "reason": f"Identity guard error: {e}", "score": 0}

    # Gate 2: Voice standard (forbidden patterns)
    try:
        from ..intelligence.vibe_marketing_eng import VOICE_STANDARD
        import re
        for pattern_str, pattern_name in VOICE_STANDARD.get("forbidden_patterns", []):
            if re.search(pattern_str, text, re.IGNORECASE):
                return {"passed": False, "reason": f"Voice standard violation: {pattern_name}", "score": 0}
    except (ImportError, Exception):
        pass  # If vibe module unavailable, skip

    # Gate 3: LLM quality score (must score ≥ 7/10)
    try:
        from ..ai.ollama_client import generate as llm_generate, is_llm_available
        if is_llm_available():
            resp = llm_generate(
                prompt=(
                    f"Rate this social media post for a Mandarin learning app on a scale of 1-10. "
                    f"Consider: clarity, educational value, engagement potential, professional tone. "
                    f"A score of 7+ means it's ready to publish. Below 7 means it needs revision.\n\n"
                    f"Post:\n{text[:500]}\n\n"
                    f"Respond with ONLY a JSON object: {{\"score\": N, \"reason\": \"...\"}}"
                ),
                system="You are a social media editor. Be strict — only high-quality content should score 7+.",
                temperature=0.2,
                max_tokens=100,
                conn=conn,
                task_type="voice_audit",
            )
            if resp.success:
                import json
                try:
                    data = json.loads(resp.text.strip())
                    score = data.get("score", 7)
                    if score < 7:
                        return {
                            "passed": False,
                            "reason": f"Quality score {score}/10: {data.get('reason', 'below threshold')}",
                            "score": score,
                        }
                    return {"passed": True, "reason": "All gates passed", "score": score}
                except (json.JSONDecodeError, KeyError):
                    pass  # Parse failed, proceed
    except (ImportError, Exception):
        pass  # LLM unavailable, proceed with pattern-only checks

    return {"passed": True, "reason": "Pattern gates passed (LLM unavailable)", "score": 7}


def _post_tiktok(conn, content_id: str, text: str, action) -> None:
    """Post to TikTok as a photo carousel (auto-generated from text)."""
    try:
        from ..marketing.social_tiktok import is_tiktok_configured, generate_carousel_from_text, post_carousel
        if not is_tiktok_configured():
            logger.debug("TikTok not configured, skipping")
            return

        image_urls = generate_carousel_from_text(text, conn=conn)
        if not image_urls:
            logger.debug("TikTok carousel generation failed for '%s'", content_id)
            return

        result = post_carousel(
            title=content_id,
            image_urls=image_urls,
            description=text[:500],
            hashtags=["LearnChinese", "MandarinChinese", "HSK", "ChineseLanguage"],
        )
        _log_post(conn, content_id, "tiktok", result.post_id if result.success else "",
                  "posted" if result.success else "failed", result.error)
    except Exception as e:
        logger.debug("TikTok posting error: %s", e)


def _generate_xhs(conn, content_id: str, text: str) -> None:
    """Generate bilingual XHS post and queue for manual posting."""
    try:
        from ..marketing.social_xhs import generate_xhs_post
        queue_id = generate_xhs_post(conn, text, content_id=content_id)
        if queue_id:
            _notify_approval_needed(conn, queue_id, "xhs", content_id)
    except Exception as e:
        logger.debug("XHS generation error: %s", e)


def _run_weekly_optimization(conn) -> None:
    """Weekly optimization cycle — extract patterns, generate variants, evaluate channels."""
    try:
        from ..marketing.content_optimizer import run_optimization_cycle
        run_optimization_cycle(conn)
    except (ImportError, Exception) as e:
        logger.debug("Weekly optimization skipped: %s", e)

    # Run channel strategy evaluation
    try:
        _evaluate_channel_strategy(conn)
    except (ImportError, Exception) as e:
        logger.debug("Channel strategy evaluation skipped: %s", e)


def _evaluate_channel_strategy(conn) -> None:
    """Use LLM to evaluate if current channel mix is optimal.

    Analyzes performance data and recommends:
    - New channels to try
    - Channels to stop (low ROI)
    - Whether paid social/search has a business case
    - Emerging platforms relevant to Mandarin learners

    Results queued as an email digest to the admin.
    """
    try:
        from ..ai.ollama_client import generate as llm_generate
    except ImportError:
        return

    # Gather performance data
    try:
        channel_data = conn.execute("""
            SELECT
                platform,
                COUNT(*) as posts,
                SUM(CASE WHEN status = 'posted' THEN 1 ELSE 0 END) as successful,
                MAX(posted_at) as last_post
            FROM marketing_post_log
            GROUP BY platform
        """).fetchall()

        metrics_data = conn.execute("""
            SELECT
                pl.platform,
                cm.metric_type,
                AVG(cm.metric_value) as avg_value
            FROM marketing_content_metrics cm
            JOIN marketing_post_log pl ON pl.id = cm.post_log_id
            GROUP BY pl.platform, cm.metric_type
        """).fetchall()
    except Exception:
        channel_data = []
        metrics_data = []

    channel_summary = "\n".join(
        f"- {r['platform']}: {r['posts']} posts, {r['successful']} successful, last: {r['last_post']}"
        for r in channel_data
    ) if channel_data else "No posts yet."

    metrics_summary = "\n".join(
        f"- {r['platform']} {r['metric_type']}: avg {r['avg_value']:.1f}"
        for r in metrics_data
    ) if metrics_data else "No metrics yet."

    resp = llm_generate(
        prompt=(
            f"You are a marketing strategist for Aelu, a Mandarin Chinese learning app. "
            f"Analyze the current channel performance and recommend optimizations.\n\n"
            f"Current channels and performance:\n{channel_summary}\n\n"
            f"Engagement metrics:\n{metrics_summary}\n\n"
            f"Currently active: Twitter, Reddit, Newsletter, TikTok, Xiaohongshu (manual)\n"
            f"Pricing: $14.99/month, free tier for HSK 1-2\n"
            f"Target audience: Self-study adults (25-45) learning Mandarin\n\n"
            f"Evaluate:\n"
            f"1. Are we on the right platforms? What should we add/drop?\n"
            f"2. Should we consider paid social or paid search? Make the business case with estimated CAC vs LTV.\n"
            f"3. Any emerging platforms or communities we're missing?\n"
            f"4. Specific tactical recommendations for next week.\n\n"
            f"Respond with JSON: {{"
            f"\"channel_recommendations\": [{{\"action\": \"add/keep/drop/test\", \"channel\": \"...\", \"reason\": \"...\", \"priority\": \"high/medium/low\"}}],"
            f"\"paid_recommendation\": {{\"should_test\": true/false, \"estimated_cac\": \"$X\", \"reasoning\": \"...\"}},"
            f"\"tactical_actions\": [\"...\"]"
            f"}}"
        ),
        system="You are a data-driven marketing strategist. Be specific and actionable.",
        temperature=0.4,
        max_tokens=1024,
        conn=conn,
        task_type="experiment_design",
    )

    if not resp.success:
        return

    # Email the strategy digest
    try:
        import resend
        resend.api_key = os.environ.get("RESEND_API_KEY", "")
        notify_email = os.environ.get("MARKETING_NOTIFY_EMAIL", "")
        from_email = os.environ.get("FROM_EMAIL", "")

        if resend.api_key and notify_email and from_email:
            # Format nicely
            import json
            try:
                data = json.loads(resp.text.strip())
                channels = data.get("channel_recommendations", [])
                paid = data.get("paid_recommendation", {})
                tactics = data.get("tactical_actions", [])

                channels_html = "".join(
                    f"<li><strong>{c.get('action', '').upper()}</strong> {c.get('channel', '')}: "
                    f"{c.get('reason', '')} (priority: {c.get('priority', '')})</li>"
                    for c in channels
                )
                tactics_html = "".join(f"<li>{t}</li>" for t in tactics)
                paid_html = (
                    f"<p><strong>Should test paid?</strong> {'Yes' if paid.get('should_test') else 'No'}<br>"
                    f"Estimated CAC: {paid.get('estimated_cac', 'N/A')}<br>"
                    f"Reasoning: {paid.get('reasoning', 'N/A')}</p>"
                )

                resend.Emails.send({
                    "from": from_email,
                    "to": [notify_email],
                    "subject": "[Aelu] Weekly Marketing Strategy Digest",
                    "html": (
                        f"<h2>Weekly Channel Strategy Review</h2>"
                        f"<h3>Channel Recommendations</h3><ul>{channels_html}</ul>"
                        f"<h3>Paid Media Assessment</h3>{paid_html}"
                        f"<h3>Tactical Actions for Next Week</h3><ul>{tactics_html}</ul>"
                        f"<hr><p><em>Auto-generated by Aelu marketing intelligence. "
                        f"Review approval queue at <a href='https://aeluapp.com/admin'>admin</a>.</em></p>"
                    ),
                })
                logger.info("Channel strategy digest sent")
            except (json.JSONDecodeError, Exception):
                # Send raw text if JSON parse fails
                resend.Emails.send({
                    "from": from_email,
                    "to": [notify_email],
                    "subject": "[Aelu] Weekly Marketing Strategy Digest",
                    "html": f"<pre>{resp.text[:3000]}</pre>",
                })
    except (ImportError, Exception) as e:
        logger.debug("Strategy digest email failed: %s", e)
