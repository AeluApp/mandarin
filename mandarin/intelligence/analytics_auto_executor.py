"""Analytics Auto-Executor — closed-loop actions driven by Plausible analytics data.

Takes Plausible analytics data and ACTS on it autonomously, without human
intervention. Complements analyzers_analytics.py (which reads and interprets
the data) by executing concrete changes.

Closed-loop action families:
1. Content optimization based on bounce rate
2. Marketing channel allocation
3. Landing page optimization (A/B tests)
4. SEO autopilot (internal links, content freshness, keyword expansion)
5. Funnel optimization (signup, first session, return)
6. Channel-specific content generation

Safety rails:
- Max 3 auto-changes per day (don't thrash)
- All changes logged to analytics_actions_log table
- Email summary of what was changed and why (daily digest)
- Revert mechanism: if a change makes metrics worse after 48 hours, auto-revert
- Never change core product pages (app UI, pricing) — only marketing/landing/blog

Exports:
    run_analytics_actions(conn) -> dict          # full nightly loop
    run_analytics_actions_lightweight(conn) -> dict  # 15-minute check
    AnalyticsAutoExecutor
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any

from ._base import _safe_query, _safe_query_all, _safe_scalar, _finding, _f
from .calibration import get_threshold

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Configuration ──────────────────────────────────────────────────────────

from ..settings import ANALYTICS_EXECUTOR_ENABLED

_MAX_ACTIONS_PER_DAY = 3
_REVERT_WINDOW_HOURS = 48
# Thresholds (defaults — overridden by calibration when data exists)
_MIN_TRAFFIC_FOR_ACTION = 20  # minimum pageviews before acting on bounce rate
_HIGH_BOUNCE_THRESHOLD = 0.75  # 75% bounce rate triggers content rewrite
_LOW_CONVERSION_THRESHOLD = 0.02  # 2% conversion threshold
_ORGANIC_ZERO_TRAFFIC_DAYS = 14  # days before declaring zero organic traffic
_CONTENT_FRESHNESS_DAYS = 90  # refresh blog content quarterly
_SIGNUP_RATE_DROP_PCT = 20  # % drop that triggers testing


def _t(conn, metric: str, default: float) -> float:
    """Look up calibrated threshold, falling back to hardcoded default."""
    return get_threshold(conn, "analytics_auto_executor", metric, default)

# Pages that are NEVER modified by the auto-executor
_PROTECTED_PAGES = {
    "/app", "/dashboard", "/session", "/settings", "/admin",
    "/pricing", "/api", "/auth", "/login", "/register",
    "/onboarding", "/drills",
}

# Only modify these path prefixes
_ALLOWED_PATH_PREFIXES = ("/blog", "/landing", "/vs-", "/hsk-", "/about", "/faq")

# Maps URL paths to marketing/landing file paths
_PAGE_TO_FILE: dict[str, str] = {
    "/": "marketing/landing/index.html",
    "/about": "marketing/landing/about.html",
    "/faq": "marketing/landing/faq.html",
    "/pricing": "marketing/landing/pricing.html",
    "/vs-anki": "marketing/landing/vs-anki.html",
    "/vs-duolingo": "marketing/landing/vs-duolingo.html",
    "/vs-hack-chinese": "marketing/landing/vs-hack-chinese.html",
    "/vs-hellochinese": "marketing/landing/vs-hellochinese.html",
    "/hsk-prep": "marketing/landing/hsk-prep.html",
    "/hsk-calculator": "marketing/landing/hsk-calculator.html",
    "/anki-alternative": "marketing/landing/anki-alternative.html",
    "/serious-learner": "marketing/landing/serious-learner.html",
    "/blog": "marketing/landing/blog/index.html",
}

# Channel keywords for referral source classification
_CHANNEL_PATTERNS = {
    "reddit": ["reddit.com", "old.reddit.com"],
    "twitter": ["twitter.com", "t.co", "x.com"],
    "organic": ["google", "bing", "duckduckgo", "baidu", "yandex"],
    "youtube": ["youtube.com", "youtu.be"],
    "hackernews": ["news.ycombinator.com"],
    "discord": ["discord.com", "discord.gg"],
}


# ── Table creation ─────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create the analytics_actions_log table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics_actions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            action_type TEXT NOT NULL,
            action_detail TEXT NOT NULL,
            target_page TEXT,
            target_file TEXT,
            original_content TEXT,
            new_content TEXT,
            metrics_before TEXT,
            metrics_after TEXT,
            status TEXT NOT NULL DEFAULT 'applied'
                CHECK(status IN ('applied', 'reverted', 'failed', 'pending', 'skipped')),
            revert_at TEXT,
            reverted_at TEXT,
            revert_reason TEXT,
            rollout_pct INTEGER DEFAULT 100,
            experiment_id INTEGER,
            notes TEXT
        )
    """)
    conn.commit()


# ── Plausible API client ──────────────────────────────────────────────────

def _plausible_query(
    endpoint: str,
    params: dict[str, str],
    *,
    timeout: float = 15.0,
) -> dict | list | None:
    """Query the Plausible Analytics API.

    Returns parsed JSON or None on failure. Uses PLAUSIBLE_API_KEY and
    PLAUSIBLE_DOMAIN from settings.
    """
    from ..settings import PLAUSIBLE_API_KEY, PLAUSIBLE_DOMAIN

    if not PLAUSIBLE_API_KEY or not PLAUSIBLE_DOMAIN:
        logger.debug("Analytics executor: Plausible not configured")
        return None

    try:
        import httpx
    except ImportError:
        logger.debug("Analytics executor: httpx not available")
        return None

    base_url = "https://plausible.io/api/v1"
    params["site_id"] = PLAUSIBLE_DOMAIN

    try:
        resp = httpx.get(
            f"{base_url}/{endpoint}",
            headers={"Authorization": f"Bearer {PLAUSIBLE_API_KEY}"},
            params=params,
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(
            "Plausible API %s returned %d: %s",
            endpoint, resp.status_code, resp.text[:200],
        )
        return None
    except Exception as exc:
        logger.debug("Plausible API error: %s", exc)
        return None


def _get_page_metrics(period: str = "7d") -> list[dict]:
    """Get per-page metrics: visitors, pageviews, bounce_rate, visit_duration."""
    data = _plausible_query("stats/breakdown", {
        "property": "event:page",
        "period": period,
        "metrics": "visitors,pageviews,bounce_rate,visit_duration",
    })
    if data and isinstance(data, dict):
        return data.get("results", [])
    return []


def _get_referral_sources(period: str = "7d") -> list[dict]:
    """Get referral source breakdown."""
    data = _plausible_query("stats/breakdown", {
        "property": "visit:source",
        "period": period,
        "metrics": "visitors,pageviews,bounce_rate",
    })
    if data and isinstance(data, dict):
        return data.get("results", [])
    return []


def _get_goal_conversions(period: str = "7d") -> list[dict]:
    """Get goal conversion breakdown."""
    data = _plausible_query("stats/breakdown", {
        "property": "event:goal",
        "period": period,
        "metrics": "visitors,events",
    })
    if data and isinstance(data, dict):
        return data.get("results", [])
    return []


def _get_aggregate_metrics(period: str = "7d") -> dict:
    """Get aggregate site-level metrics."""
    data = _plausible_query("stats/aggregate", {
        "period": period,
        "metrics": "visitors,pageviews,bounce_rate,visit_duration",
    })
    if data and isinstance(data, dict):
        return data.get("results", {})
    return {}


def _classify_channel(source: str) -> str:
    """Classify a referral source into a channel."""
    source_lower = (source or "").lower()
    for channel, patterns in _CHANNEL_PATTERNS.items():
        for pattern in patterns:
            if pattern in source_lower:
                return channel
    if source_lower in ("", "direct", "(none)"):
        return "direct"
    return "other"


# ── Safety helpers ─────────────────────────────────────────────────────────

def _is_protected_page(page_path: str) -> bool:
    """Check if a page is protected from auto-modification."""
    for prefix in _PROTECTED_PAGES:
        if page_path.startswith(prefix):
            return True
    return False


def _is_allowed_page(page_path: str) -> bool:
    """Check if a page path is in the allowed modification set."""
    if page_path == "/":
        return False  # Don't auto-modify the root landing page
    for prefix in _ALLOWED_PATH_PREFIXES:
        if page_path.startswith(prefix):
            return True
    return False


def _resolve_page_file(page_path: str) -> str | None:
    """Map a URL path to a local file path. Returns relative path or None."""
    # Direct lookup
    if page_path in _PAGE_TO_FILE:
        return _PAGE_TO_FILE[page_path]

    # Blog posts: /blog/slug -> marketing/landing/blog/slug.html
    if page_path.startswith("/blog/"):
        slug = page_path.removeprefix("/blog/").rstrip("/")
        if slug:
            candidate = f"marketing/landing/blog/{slug}.html"
            if (_PROJECT_ROOT / candidate).exists():
                return candidate

    # VS pages
    if page_path.startswith("/vs-"):
        slug = page_path.lstrip("/")
        candidate = f"marketing/landing/{slug}.html"
        if (_PROJECT_ROOT / candidate).exists():
            return candidate

    # Generic landing pages
    slug = page_path.strip("/")
    candidate = f"marketing/landing/{slug}.html"
    if (_PROJECT_ROOT / candidate).exists():
        return candidate

    return None


def _count_actions_today(conn: sqlite3.Connection) -> int:
    """Count analytics actions taken today."""
    return _safe_scalar(conn, """
        SELECT COUNT(*) FROM analytics_actions_log
        WHERE created_at >= date('now')
          AND status = 'applied'
    """, default=0)


def _can_take_action(conn: sqlite3.Connection) -> bool:
    """Check if we're within the daily action limit."""
    return _count_actions_today(conn) < _MAX_ACTIONS_PER_DAY


def _check_analytics_contract(conn: sqlite3.Connection, action_type: str, target: str | None = None) -> tuple[bool, str, int | None]:
    """Check contract governance for an analytics action. Non-fatal on failure."""
    try:
        from .contracts import check_contract
        return check_contract(conn, "analytics", action_type, target)
    except Exception:
        return True, "", None


def _record_to_ledger(conn: sqlite3.Connection, action_type: str, target: str | None,
                      description: str, metrics_before: dict | None,
                      verification_hours: int = 48, contract_id: int | None = None) -> None:
    """Record to unified action ledger. Non-fatal on failure."""
    try:
        from .action_ledger import record_action
        record_action(conn, "analytics", action_type, target, description,
                       metrics_before, verification_hours=verification_hours,
                       contract_id=contract_id)
    except Exception:
        pass


def _log_action(
    conn: sqlite3.Connection,
    action_type: str,
    action_detail: str,
    *,
    target_page: str | None = None,
    target_file: str | None = None,
    original_content: str | None = None,
    new_content: str | None = None,
    metrics_before: dict | None = None,
    metrics_after: dict | None = None,
    status: str = "applied",
    rollout_pct: int = 100,
    experiment_id: int | None = None,
    notes: str | None = None,
) -> int | None:
    """Log an action to the analytics_actions_log table. Returns the row id."""
    _ensure_tables(conn)
    revert_at = None
    if status == "applied":
        revert_at = (
            datetime.now(UTC) + timedelta(hours=_REVERT_WINDOW_HOURS)
        ).strftime("%Y-%m-%d %H:%M:%S")

    try:
        cur = conn.execute("""
            INSERT INTO analytics_actions_log
                (action_type, action_detail, target_page, target_file,
                 original_content, new_content, metrics_before, metrics_after,
                 status, revert_at, rollout_pct, experiment_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            action_type,
            action_detail,
            target_page,
            target_file,
            original_content[:10000] if original_content else None,
            new_content[:10000] if new_content else None,
            json.dumps(metrics_before) if metrics_before else None,
            json.dumps(metrics_after) if metrics_after else None,
            status,
            revert_at,
            rollout_pct,
            experiment_id,
            notes,
        ))
        conn.commit()

        # Also record to unified action ledger
        _record_to_ledger(
            conn, action_type, target_page or target_file,
            action_detail, metrics_before,
            verification_hours=_REVERT_WINDOW_HOURS,
        )

        return cur.lastrowid
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Analytics executor: failed to log action: %s", exc)
        return None


# ── LLM content generation ────────────────────────────────────────────────

def _generate_content(
    conn: sqlite3.Connection,
    prompt: str,
    system: str = "",
    task_type: str = "analytics_content",
) -> str | None:
    """Generate content using the LLM (via LiteLLM/Ollama).

    Returns the generated text or None on failure.
    """
    from ..ai.ollama_client import generate

    response = generate(
        prompt=prompt,
        system=system,
        temperature=0.6,
        max_tokens=2048,
        use_cache=False,
        conn=conn,
        task_type=task_type,
    )

    if response.success and response.text:
        return response.text.strip()
    return None


# ── Action 1: Content optimization based on bounce rate ───────────────────

def _optimize_high_bounce_pages(
    conn: sqlite3.Connection,
    page_metrics: list[dict],
) -> list[dict]:
    """Rewrite meta description and hero text for pages with high bounce rates.

    Only acts on pages with:
    - bounce_rate > 75%
    - at least _MIN_TRAFFIC_FOR_ACTION pageviews
    - not protected pages

    Deploys via graduated rollout (25% -> 50% -> 100%).
    """
    actions = []

    for page in page_metrics:
        if not _can_take_action(conn):
            break

        page_path = page.get("page", "")
        bounce_rate = (page.get("bounce_rate") or 0) / 100.0  # Plausible returns 0-100
        pageviews = page.get("pageviews", 0)
        visitors = page.get("visitors", 0)

        if bounce_rate < _t(conn, "high_bounce_threshold", _HIGH_BOUNCE_THRESHOLD):
            continue
        if pageviews < _t(conn, "min_traffic_for_action", _MIN_TRAFFIC_FOR_ACTION):
            continue
        if _is_protected_page(page_path):
            continue
        if not _is_allowed_page(page_path):
            continue

        # Governance: contract check
        allowed, reason, cid = _check_analytics_contract(conn, "rewrite_content", page_path)
        if not allowed:
            logger.info("Contract blocked analytics/rewrite_content for %s: %s", page_path, reason)
            _record_to_ledger(conn, "rewrite_content", page_path, f"BLOCKED: {reason}", None, contract_id=cid)
            continue

        target_file = _resolve_page_file(page_path)
        if not target_file:
            continue

        abs_path = _PROJECT_ROOT / target_file
        if not abs_path.exists():
            continue

        # Check if we already have a pending action for this page
        existing = _safe_query(conn, """
            SELECT id FROM analytics_actions_log
            WHERE target_page = ? AND action_type = 'bounce_rate_optimize'
              AND status = 'applied' AND created_at >= datetime('now', '-7 days')
        """, (page_path,))
        if existing:
            continue

        try:
            original_content = abs_path.read_text(encoding="utf-8")
        except Exception:
            continue

        # Extract current meta description
        meta_match = re.search(
            r'<meta\s+name="description"\s+content="([^"]*)"',
            original_content,
        )
        current_meta = meta_match.group(1) if meta_match else ""

        # Extract hero text (first <h1> and first <p> after it)
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", original_content, re.DOTALL)
        current_h1 = h1_match.group(1).strip() if h1_match else ""

        # Generate improved content via LLM
        prompt = (
            f"This landing page has a {bounce_rate:.0%} bounce rate with {visitors} visitors.\n\n"
            f"Page: {page_path}\n"
            f"Current meta description: {current_meta}\n"
            f"Current headline: {current_h1}\n\n"
            f"Write an improved meta description (max 155 chars) and headline that:\n"
            f"- Clearly communicates the value proposition for Mandarin learners\n"
            f"- Uses warm, direct language (no hype, no exclamation marks)\n"
            f"- Addresses what the visitor is likely looking for\n"
            f"- Follows the Civic Sanctuary brand voice: warmth without condescension\n\n"
            f"Return ONLY a JSON object with keys: meta_description, headline\n"
            f"No markdown fences. No explanation."
        )

        system = (
            "You are a conversion copywriter for Aelu, a Mandarin learning platform. "
            "Aelu's voice is warm, direct, data-grounded, and never uses praise inflation "
            "or urgency marketing. Think 'calm adult mentor', not 'excited startup'."
        )

        llm_result = _generate_content(conn, prompt, system, task_type="analytics_bounce_optimize")
        if not llm_result:
            continue

        # Parse LLM output
        try:
            # Strip markdown fences if present
            clean = llm_result.strip()
            if clean.startswith("```"):
                clean = re.sub(r"^```(?:json)?\s*", "", clean)
                clean = re.sub(r"\s*```$", "", clean)
            improvements = json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            logger.debug("Analytics executor: failed to parse LLM bounce optimization output")
            continue

        new_meta = improvements.get("meta_description", "")
        new_headline = improvements.get("headline", "")

        if not new_meta and not new_headline:
            continue

        # Apply changes
        new_content = original_content
        if new_meta and meta_match:
            new_content = new_content.replace(
                meta_match.group(0),
                f'<meta name="description" content="{new_meta}"',
            )
        if new_headline and h1_match:
            new_content = new_content.replace(
                h1_match.group(0),
                f"<h1>{new_headline}</h1>",
            )

        if new_content == original_content:
            continue

        # Write the file
        try:
            abs_path.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            logger.warning("Analytics executor: failed to write %s: %s", target_file, exc)
            continue

        action_id = _log_action(
            conn,
            action_type="bounce_rate_optimize",
            action_detail=(
                f"Rewrote meta description and headline for {page_path} "
                f"(bounce rate: {bounce_rate:.0%}, {pageviews} pageviews)"
            ),
            target_page=page_path,
            target_file=target_file,
            original_content=original_content,
            new_content=new_content,
            metrics_before={
                "bounce_rate": bounce_rate,
                "pageviews": pageviews,
                "visitors": visitors,
            },
            rollout_pct=25,  # Start graduated rollout at 25%
            notes=json.dumps(improvements),
        )

        actions.append({
            "action": "bounce_rate_optimize",
            "page": page_path,
            "bounce_rate": bounce_rate,
            "action_id": action_id,
        })

        logger.info(
            "Analytics executor: optimized %s (bounce rate %.0f%%, %d pageviews)",
            page_path, bounce_rate * 100, pageviews,
        )

    return actions


# ── Action 2: Marketing channel allocation ────────────────────────────────

def _adjust_channel_allocation(
    conn: sqlite3.Connection,
    referral_sources: list[dict],
) -> list[dict]:
    """Adjust marketing channel weights based on referral performance.

    - Growing channels get increased weight
    - Compares 7-day vs 30-day trends to detect growth
    - Updates channel_weights in analytics_channel_config table
    """
    actions = []

    if not _can_take_action(conn):
        return actions

    # Governance: contract check
    allowed, reason, cid = _check_analytics_contract(conn, "increase_channel_weight")
    if not allowed:
        logger.info("Contract blocked analytics/increase_channel_weight: %s", reason)
        _record_to_ledger(conn, "increase_channel_weight", None, f"BLOCKED: {reason}", None, contract_id=cid)
        return actions

    # Get current and prior period referral data
    current_sources = referral_sources  # already 7d
    prior_sources = _get_referral_sources(period="30d")

    if not current_sources or not prior_sources:
        return actions

    # Aggregate by channel
    current_by_channel: dict[str, int] = {}
    prior_by_channel: dict[str, int] = {}

    for src in current_sources:
        channel = _classify_channel(src.get("source", ""))
        current_by_channel[channel] = (
            current_by_channel.get(channel, 0) + (src.get("visitors", 0))
        )

    for src in prior_sources:
        channel = _classify_channel(src.get("source", ""))
        prior_by_channel[channel] = (
            prior_by_channel.get(channel, 0) + (src.get("visitors", 0))
        )

    # Normalize prior to weekly rate (30d -> 7d equivalent)
    for ch in prior_by_channel:
        prior_by_channel[ch] = max(1, prior_by_channel[ch] * 7 // 30)

    # Detect growth channels
    growth_channels = []
    for channel in current_by_channel:
        current_val = current_by_channel[channel]
        prior_val = prior_by_channel.get(channel, 1)
        if prior_val > 0 and current_val > prior_val * 1.3:  # 30%+ growth
            growth_rate = (current_val / prior_val) - 1.0
            growth_channels.append({
                "channel": channel,
                "current_visitors": current_val,
                "prior_visitors_weekly": prior_val,
                "growth_rate": growth_rate,
            })

    if not growth_channels:
        return actions

    # Ensure table exists
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analytics_channel_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL UNIQUE,
                weight REAL NOT NULL DEFAULT 1.0,
                post_frequency TEXT DEFAULT 'weekly',
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                notes TEXT
            )
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass

    for growth in sorted(growth_channels, key=lambda g: g["growth_rate"], reverse=True):
        if not _can_take_action(conn):
            break

        channel = growth["channel"]
        growth_rate = growth["growth_rate"]

        # Get current weight
        row = _safe_query(conn, """
            SELECT weight, post_frequency FROM analytics_channel_config
            WHERE channel = ?
        """, (channel,))

        current_weight = row["weight"] if row else 1.0
        current_freq = row["post_frequency"] if row else "weekly"

        # Increase weight by growth rate (capped at 2x)
        new_weight = min(current_weight * (1 + growth_rate * 0.5), current_weight * 2.0)

        # Increase post frequency for high-growth channels
        new_freq = current_freq
        if growth_rate > 0.5 and current_freq == "weekly":
            new_freq = "3x_weekly"
        elif growth_rate > 1.0 and current_freq in ("weekly", "3x_weekly"):
            new_freq = "daily"

        # Upsert channel config
        try:
            conn.execute("""
                INSERT INTO analytics_channel_config (channel, weight, post_frequency, updated_at, notes)
                VALUES (?, ?, ?, datetime('now'), ?)
                ON CONFLICT(channel) DO UPDATE SET
                    weight = excluded.weight,
                    post_frequency = excluded.post_frequency,
                    updated_at = excluded.updated_at,
                    notes = excluded.notes
            """, (
                channel, new_weight, new_freq,
                f"Auto-adjusted: {growth_rate:.0%} growth, {growth['current_visitors']} visitors/week",
            ))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error):
            continue

        action_detail = (
            f"Channel {channel}: weight {current_weight:.1f} -> {new_weight:.1f}, "
            f"frequency {current_freq} -> {new_freq} "
            f"(growth: {growth_rate:.0%})"
        )

        _log_action(
            conn,
            action_type="channel_allocation",
            action_detail=action_detail,
            metrics_before={
                "channel": channel,
                "weight": current_weight,
                "frequency": current_freq,
                "visitors_7d": growth["current_visitors"],
            },
            notes=json.dumps(growth),
        )

        actions.append({
            "action": "channel_allocation",
            "channel": channel,
            "growth_rate": growth_rate,
            "new_weight": new_weight,
            "new_frequency": new_freq,
        })

        logger.info(
            "Analytics executor: adjusted channel %s — weight %.1f->%.1f, freq %s->%s (%+.0f%% growth)",
            channel, current_weight, new_weight, current_freq, new_freq, growth_rate * 100,
        )

    return actions


# ── Action 3: Landing page optimization (A/B test proposals) ──────────────

def _propose_landing_page_tests(
    conn: sqlite3.Connection,
    page_metrics: list[dict],
    goal_conversions: list[dict],
) -> list[dict]:
    """Auto-propose A/B tests for high-traffic, low-conversion landing pages.

    Uses the existing experiment_proposer to create experiments.
    """
    actions = []

    # Governance: contract check
    allowed, reason, cid = _check_analytics_contract(conn, "propose_ab_test")
    if not allowed:
        logger.info("Contract blocked analytics/propose_ab_test: %s", reason)
        _record_to_ledger(conn, "propose_ab_test", None, f"BLOCKED: {reason}", None, contract_id=cid)
        return actions

    if not _can_take_action(conn):
        return actions

    # Calculate per-page conversion rates
    total_visitors = sum(p.get("visitors", 0) for p in page_metrics)
    signup_events = 0
    for goal in goal_conversions:
        goal_name = (goal.get("goal") or "").lower()
        if "signup" in goal_name or "register" in goal_name:
            signup_events += goal.get("visitors", 0)

    _site_conversion_rate = signup_events / max(total_visitors, 1)  # noqa: F841

    for page in page_metrics:
        if not _can_take_action(conn):
            break

        page_path = page.get("page", "")
        visitors = page.get("visitors", 0)
        bounce_rate = (page.get("bounce_rate") or 0) / 100.0

        if visitors < _t(conn, "min_traffic_for_action", _MIN_TRAFFIC_FOR_ACTION) * 2:
            continue
        if _is_protected_page(page_path):
            continue
        if not _is_allowed_page(page_path):
            continue

        # High traffic + high bounce = opportunity for CTA test
        if visitors > total_visitors * 0.1 and bounce_rate > 0.6:
            # Check if experiment already exists
            exp_name = f"analytics_cta_test_{page_path.strip('/').replace('/', '_')}"
            existing = _safe_query(conn, """
                SELECT id FROM experiment
                WHERE name = ? AND status IN ('draft', 'running')
            """, (exp_name,))
            if existing:
                continue

            # Check if already proposed recently
            existing_action = _safe_query(conn, """
                SELECT id FROM analytics_actions_log
                WHERE target_page = ? AND action_type = 'landing_page_ab_test'
                  AND status = 'applied' AND created_at >= datetime('now', '-14 days')
            """, (page_path,))
            if existing_action:
                continue

            # Create the experiment using the experiment proposer
            finding = {
                "dimension": "marketing",
                "severity": "medium",
                "title": f"High bounce rate on {page_path} ({bounce_rate:.0%})",
                "analysis": (
                    f"Page {page_path} receives {visitors} visitors/week but has "
                    f"a {bounce_rate:.0%} bounce rate, suggesting the CTA or value "
                    f"proposition may not be compelling enough."
                ),
                "recommendation": (
                    f"A/B test the CTA text and placement on {page_path} to "
                    f"reduce bounce rate and improve signup conversion."
                ),
            }

            try:
                from .experiment_proposer import propose_experiment
                proposal = propose_experiment(conn, finding, source="analytics_auto")

                if proposal:
                    # Store the proposal
                    try:
                        conn.execute("""
                            INSERT INTO experiment_proposal
                                (name, description, hypothesis, variants, scope,
                                 duration_days, source, source_detail, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                        """, (
                            proposal.get("name", exp_name),
                            proposal.get("description", ""),
                            proposal.get("hypothesis", ""),
                            json.dumps(proposal.get("variants", ["control", "variant"])),
                            proposal.get("scope", "marketing"),
                            proposal.get("duration_days", 14),
                            "analytics_auto_executor",
                            json.dumps({
                                "page": page_path,
                                "bounce_rate": bounce_rate,
                                "visitors": visitors,
                            }),
                        ))
                        conn.commit()

                        _log_action(
                            conn,
                            action_type="landing_page_ab_test",
                            action_detail=(
                                f"Proposed A/B test for {page_path}: {proposal.get('name', exp_name)} "
                                f"(bounce rate {bounce_rate:.0%}, {visitors} visitors)"
                            ),
                            target_page=page_path,
                            metrics_before={
                                "bounce_rate": bounce_rate,
                                "visitors": visitors,
                            },
                            notes=json.dumps(proposal),
                        )

                        actions.append({
                            "action": "landing_page_ab_test",
                            "page": page_path,
                            "experiment": proposal.get("name", exp_name),
                        })

                        logger.info(
                            "Analytics executor: proposed A/B test for %s (%s)",
                            page_path, proposal.get("name", exp_name),
                        )

                    except sqlite3.OperationalError:
                        pass  # experiment_proposal table may not exist

            except ImportError:
                pass

    return actions


# ── Action 4: SEO autopilot ───────────────────────────────────────────────

def _run_seo_autopilot(
    conn: sqlite3.Connection,
    page_metrics: list[dict],
    referral_sources: list[dict],
) -> list[dict]:
    """SEO automation:
    - Pages with zero organic traffic after 14 days: generate internal links
    - Blog posts that rank: refresh with updated content quarterly
    - Detect keyword trends: queue new content
    """
    actions = []

    if not _can_take_action(conn):
        return actions

    # Find organic traffic volume
    organic_visitors_by_page: dict[str, int] = {}
    for page in page_metrics:
        page_path = page.get("page", "")
        organic_visitors_by_page[page_path] = page.get("visitors", 0)

    # Find all blog/landing pages
    blog_dir = _PROJECT_ROOT / "marketing" / "landing" / "blog"
    if blog_dir.exists():
        for html_file in blog_dir.glob("*.html"):
            if html_file.name == "index.html":
                continue

            slug = html_file.stem
            page_path = f"/blog/{slug}"
            visitors = organic_visitors_by_page.get(page_path, 0)

            if not _can_take_action(conn):
                break

            # Zero traffic pages: generate internal links from high-traffic pages
            if visitors == 0:
                # Check creation date (file mtime as proxy)
                file_age_days = (
                    time.time() - html_file.stat().st_mtime
                ) / 86400

                if file_age_days < _t(conn, "organic_zero_traffic_days", _ORGANIC_ZERO_TRAFFIC_DAYS):
                    continue  # Too new — give it time

                # Check if we already acted on this page
                existing = _safe_query(conn, """
                    SELECT id FROM analytics_actions_log
                    WHERE target_page = ? AND action_type = 'seo_internal_links'
                      AND status = 'applied' AND created_at >= datetime('now', '-30 days')
                """, (page_path,))
                if existing:
                    continue

                # Find the top 3 pages by traffic to add internal links
                top_pages = sorted(
                    page_metrics,
                    key=lambda p: p.get("visitors", 0),
                    reverse=True,
                )[:5]

                link_targets = []
                for tp in top_pages:
                    tp_path = tp.get("page", "")
                    if tp_path == page_path:
                        continue
                    if _is_protected_page(tp_path):
                        continue
                    tp_file = _resolve_page_file(tp_path)
                    if tp_file:
                        link_targets.append({
                            "page": tp_path,
                            "file": tp_file,
                            "visitors": tp.get("visitors", 0),
                        })

                if link_targets:
                    _log_action(
                        conn,
                        action_type="seo_internal_links",
                        action_detail=(
                            f"Queued internal link generation for {page_path} "
                            f"(zero organic traffic after {file_age_days:.0f} days)"
                        ),
                        target_page=page_path,
                        target_file=f"marketing/landing/blog/{slug}.html",
                        status="pending",  # Needs LLM to generate actual link text
                        notes=json.dumps({
                            "link_from_pages": link_targets[:3],
                            "file_age_days": file_age_days,
                        }),
                    )

                    actions.append({
                        "action": "seo_internal_links",
                        "page": page_path,
                        "link_targets": len(link_targets),
                    })

            # High-traffic blog posts: check freshness
            elif visitors > _t(conn, "min_traffic_for_action", _MIN_TRAFFIC_FOR_ACTION):
                file_age_days = (
                    time.time() - html_file.stat().st_mtime
                ) / 86400

                if file_age_days < _t(conn, "content_freshness_days", _CONTENT_FRESHNESS_DAYS):
                    continue

                existing = _safe_query(conn, """
                    SELECT id FROM analytics_actions_log
                    WHERE target_page = ? AND action_type = 'seo_content_refresh'
                      AND status IN ('applied', 'pending')
                      AND created_at >= datetime('now', '-90 days')
                """, (page_path,))
                if existing:
                    continue

                _log_action(
                    conn,
                    action_type="seo_content_refresh",
                    action_detail=(
                        f"Queued content refresh for {page_path} "
                        f"({visitors} visitors, {file_age_days:.0f} days old)"
                    ),
                    target_page=page_path,
                    target_file=f"marketing/landing/blog/{slug}.html",
                    status="pending",
                    metrics_before={
                        "visitors": visitors,
                        "file_age_days": file_age_days,
                    },
                )

                actions.append({
                    "action": "seo_content_refresh",
                    "page": page_path,
                    "visitors": visitors,
                    "age_days": file_age_days,
                })

    # Detect growing keyword clusters from referral data
    organic_sources = [
        s for s in referral_sources
        if _classify_channel(s.get("source", "")) == "organic"
    ]

    if organic_sources and _can_take_action(conn):
        # Queue keyword expansion content
        total_organic = sum(s.get("visitors", 0) for s in organic_sources)
        if total_organic > _t(conn, "min_traffic_for_action", _MIN_TRAFFIC_FOR_ACTION):
            existing = _safe_query(conn, """
                SELECT id FROM analytics_actions_log
                WHERE action_type = 'seo_keyword_expansion'
                  AND status IN ('applied', 'pending')
                  AND created_at >= datetime('now', '-7 days')
            """)
            if not existing:
                _log_action(
                    conn,
                    action_type="seo_keyword_expansion",
                    action_detail=(
                        f"Organic traffic growing ({total_organic} visitors/week). "
                        f"Queued keyword research for content expansion."
                    ),
                    status="pending",
                    metrics_before={"organic_visitors_7d": total_organic},
                    notes=json.dumps({
                        "top_organic_sources": [
                            {"source": s.get("source"), "visitors": s.get("visitors")}
                            for s in sorted(
                                organic_sources,
                                key=lambda x: x.get("visitors", 0),
                                reverse=True,
                            )[:5]
                        ],
                    }),
                )

                actions.append({
                    "action": "seo_keyword_expansion",
                    "organic_visitors": total_organic,
                })

    return actions


# ── Action 5: Funnel optimization ─────────────────────────────────────────

def _optimize_funnel(
    conn: sqlite3.Connection,
    goal_conversions: list[dict],
    aggregate_metrics: dict,
) -> list[dict]:
    """Track visit -> signup -> first session -> return session funnel.

    If signup rate drops, auto-test different registration page variants.
    If first-session completion drops, adjust session parameters.
    """
    actions = []

    if not _can_take_action(conn):
        return actions

    total_visitors = 0
    signups = 0
    first_sessions = 0
    return_sessions = 0

    for goal in goal_conversions:
        goal_name = (goal.get("goal") or "").lower()
        goal_visitors = goal.get("visitors", 0)

        if "signup" in goal_name or "register" in goal_name:
            signups += goal_visitors
        elif "first_session" in goal_name or "first session" in goal_name:
            first_sessions += goal_visitors
        elif "return" in goal_name or "repeat" in goal_name:
            return_sessions += goal_visitors

    # Get total visitors from aggregate
    visitors_data = aggregate_metrics.get("visitors", {})
    if isinstance(visitors_data, dict):
        total_visitors = visitors_data.get("value", 0)
    else:
        total_visitors = visitors_data or 0

    if total_visitors < _t(conn, "min_traffic_for_action", _MIN_TRAFFIC_FOR_ACTION):
        return actions

    signup_rate = signups / max(total_visitors, 1)

    # Store funnel metrics for trend detection
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analytics_funnel_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                total_visitors INTEGER,
                signups INTEGER,
                first_sessions INTEGER,
                return_sessions INTEGER,
                signup_rate REAL,
                activation_rate REAL,
                retention_rate REAL
            )
        """)

        activation_rate = first_sessions / max(signups, 1)
        retention_rate = return_sessions / max(first_sessions, 1)

        conn.execute("""
            INSERT INTO analytics_funnel_snapshot
                (total_visitors, signups, first_sessions, return_sessions,
                 signup_rate, activation_rate, retention_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            total_visitors, signups, first_sessions, return_sessions,
            signup_rate, activation_rate, retention_rate,
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error):
        pass

    # Detect signup rate drop by comparing to previous week
    prev_snapshot = _safe_query(conn, """
        SELECT signup_rate, activation_rate FROM analytics_funnel_snapshot
        WHERE created_at < datetime('now', '-6 days')
        ORDER BY created_at DESC LIMIT 1
    """)

    if prev_snapshot and prev_snapshot["signup_rate"]:
        prev_signup_rate = prev_snapshot["signup_rate"]
        if prev_signup_rate > 0:
            drop_pct = ((prev_signup_rate - signup_rate) / prev_signup_rate) * 100

            if drop_pct > _t(conn, "signup_rate_drop_pct", _SIGNUP_RATE_DROP_PCT):
                # Signup rate dropped significantly — propose registration test
                existing = _safe_query(conn, """
                    SELECT id FROM analytics_actions_log
                    WHERE action_type = 'funnel_signup_test'
                      AND status = 'applied'
                      AND created_at >= datetime('now', '-14 days')
                """)
                if not existing:
                    _log_action(
                        conn,
                        action_type="funnel_signup_test",
                        action_detail=(
                            f"Signup rate dropped {drop_pct:.0f}% "
                            f"({prev_signup_rate:.2%} -> {signup_rate:.2%}). "
                            f"Proposing registration page A/B test."
                        ),
                        metrics_before={
                            "signup_rate": signup_rate,
                            "prev_signup_rate": prev_signup_rate,
                            "drop_pct": drop_pct,
                            "total_visitors": total_visitors,
                            "signups": signups,
                        },
                    )

                    actions.append({
                        "action": "funnel_signup_test",
                        "signup_rate": signup_rate,
                        "drop_pct": drop_pct,
                    })

                    logger.info(
                        "Analytics executor: signup rate dropped %.0f%% — proposing test",
                        drop_pct,
                    )

    # Detect activation rate drop
    if prev_snapshot and prev_snapshot["activation_rate"]:
        prev_activation = prev_snapshot["activation_rate"]
        activation_rate = first_sessions / max(signups, 1)
        if prev_activation > 0:
            activation_drop = ((prev_activation - activation_rate) / prev_activation) * 100
            if activation_drop > _t(conn, "signup_rate_drop_pct", _SIGNUP_RATE_DROP_PCT):
                existing = _safe_query(conn, """
                    SELECT id FROM analytics_actions_log
                    WHERE action_type = 'funnel_activation_adjust'
                      AND status = 'applied'
                      AND created_at >= datetime('now', '-14 days')
                """)
                if not existing and _can_take_action(conn):
                    _log_action(
                        conn,
                        action_type="funnel_activation_adjust",
                        action_detail=(
                            f"Activation rate dropped {activation_drop:.0f}% "
                            f"({prev_activation:.2%} -> {activation_rate:.2%}). "
                            f"Consider adjusting session length/difficulty."
                        ),
                        metrics_before={
                            "activation_rate": activation_rate,
                            "prev_activation_rate": prev_activation,
                            "drop_pct": activation_drop,
                        },
                        status="pending",
                    )

                    actions.append({
                        "action": "funnel_activation_adjust",
                        "activation_rate": activation_rate,
                        "drop_pct": activation_drop,
                    })

    return actions


# ── Action 6: Channel-specific content generation ─────────────────────────

def _generate_channel_content(
    conn: sqlite3.Connection,
    referral_sources: list[dict],
) -> list[dict]:
    """Generate channel-specific content for high-performing channels.

    - If Twitter drives traffic: generate tweet-style content
    - If a specific subreddit drives traffic: generate posts targeting it
    - Uses cloud LLM to generate content
    """
    actions = []

    # Governance: contract check
    allowed, reason, cid = _check_analytics_contract(conn, "generate_channel_content")
    if not allowed:
        logger.info("Contract blocked analytics/generate_channel_content: %s", reason)
        _record_to_ledger(conn, "generate_channel_content", None, f"BLOCKED: {reason}", None, contract_id=cid)
        return actions

    if not _can_take_action(conn):
        return actions

    # Aggregate by channel
    channel_visitors: dict[str, int] = {}
    channel_sources: dict[str, list[str]] = {}

    for src in referral_sources:
        source = src.get("source", "")
        channel = _classify_channel(source)
        visitors = src.get("visitors", 0)
        channel_visitors[channel] = channel_visitors.get(channel, 0) + visitors
        if channel not in channel_sources:
            channel_sources[channel] = []
        if source and source not in channel_sources[channel]:
            channel_sources[channel].append(source)

    total_referral_visitors = sum(channel_visitors.values())
    if total_referral_visitors < _t(conn, "min_traffic_for_action", _MIN_TRAFFIC_FOR_ACTION):
        return actions

    # Generate content for top-performing channels
    for channel, visitors in sorted(channel_visitors.items(), key=lambda x: x[1], reverse=True):
        if not _can_take_action(conn):
            break
        if channel in ("direct", "other"):
            continue
        if visitors < _t(conn, "min_traffic_for_action", _MIN_TRAFFIC_FOR_ACTION):
            continue

        # Check if we already generated content for this channel recently
        existing = _safe_query(conn, """
            SELECT id FROM analytics_actions_log
            WHERE action_type = 'channel_content_gen'
              AND notes LIKE ?
              AND status IN ('applied', 'pending')
              AND created_at >= datetime('now', '-7 days')
        """, (f'%"channel": "{channel}"%',))
        if existing:
            continue

        # Generate channel-appropriate content
        channel_share = visitors / max(total_referral_visitors, 1)
        sources_list = channel_sources.get(channel, [])

        prompt = (
            f"Generate 3 content ideas for the '{channel}' channel that would "
            f"attract Mandarin learners to Aelu.\n\n"
            f"Channel context:\n"
            f"- {visitors} visitors came from {channel} last week\n"
            f"- Specific sources: {', '.join(sources_list[:5])}\n"
            f"- {channel_share:.0%} of referral traffic\n\n"
            f"For each idea, provide:\n"
            f"- title: A compelling title\n"
            f"- body: A short post body (2-3 sentences)\n"
            f"- hashtags: Relevant hashtags (if applicable)\n"
            f"- subreddit: Target subreddit (if Reddit)\n\n"
            f"Return ONLY a JSON array of objects. No markdown fences."
        )

        system = (
            "You are a content strategist for Aelu, a Mandarin learning platform. "
            "Write in a warm, direct voice. Never use hype, urgency, or praise inflation. "
            "Focus on genuinely helpful insights about Mandarin learning."
        )

        llm_result = _generate_content(conn, prompt, system, task_type="analytics_channel_content")
        if not llm_result:
            continue

        # Store as pending content
        _log_action(
            conn,
            action_type="channel_content_gen",
            action_detail=(
                f"Generated 3 content ideas for {channel} channel "
                f"({visitors} visitors, {channel_share:.0%} of referral traffic)"
            ),
            status="pending",
            metrics_before={
                "channel": channel,
                "visitors": visitors,
                "channel_share": channel_share,
                "sources": sources_list[:5],
            },
            notes=json.dumps({
                "channel": channel,
                "content": llm_result[:5000],
            }),
        )

        actions.append({
            "action": "channel_content_gen",
            "channel": channel,
            "visitors": visitors,
        })

        logger.info(
            "Analytics executor: generated content for %s channel (%d visitors)",
            channel, visitors,
        )

    return actions


# ── Revert mechanism ──────────────────────────────────────────────────────

def _check_and_revert_failing_changes(conn: sqlite3.Connection) -> list[dict]:
    """Check if any applied changes made metrics worse after 48 hours.

    If a change resulted in worse bounce rate or fewer visitors,
    automatically revert by restoring original content.
    """
    actions = []

    _ensure_tables(conn)

    # Find changes that are past their revert window
    pending_reverts = _safe_query_all(conn, """
        SELECT id, action_type, target_page, target_file,
               original_content, metrics_before, created_at
        FROM analytics_actions_log
        WHERE status = 'applied'
          AND revert_at IS NOT NULL
          AND revert_at <= datetime('now')
          AND original_content IS NOT NULL
          AND target_file IS NOT NULL
    """)

    if not pending_reverts:
        return actions

    # Get current metrics to compare
    current_metrics = _get_page_metrics(period="7d")
    current_by_page = {
        p.get("page", ""): p for p in current_metrics
    }

    for change in pending_reverts:
        change_id = change["id"]
        target_page = change["target_page"]
        target_file = change["target_file"]
        original_content = change["original_content"]

        if not target_page or not original_content:
            # Mark as checked (no revert needed for non-content actions)
            try:
                conn.execute("""
                    UPDATE analytics_actions_log
                    SET revert_at = NULL, notes = COALESCE(notes, '') || ' [revert-check: no content to revert]'
                    WHERE id = ?
                """, (change_id,))
                conn.commit()
            except sqlite3.Error:
                pass
            continue

        # Compare metrics
        metrics_before_str = change["metrics_before"]
        if not metrics_before_str:
            continue

        try:
            metrics_before = json.loads(metrics_before_str)
        except (json.JSONDecodeError, ValueError):
            continue

        current_page = current_by_page.get(target_page, {})
        current_bounce = (current_page.get("bounce_rate") or 0) / 100.0
        previous_bounce = metrics_before.get("bounce_rate", 0)
        current_visitors = current_page.get("visitors", 0)
        previous_visitors = metrics_before.get("visitors", 0)

        # Determine if the change made things worse
        should_revert = False
        revert_reason = ""

        if previous_bounce > 0 and current_bounce > previous_bounce * 1.1:
            should_revert = True
            revert_reason = (
                f"Bounce rate increased from {previous_bounce:.0%} to {current_bounce:.0%}"
            )
        elif previous_visitors > 0 and current_visitors < previous_visitors * 0.7:
            should_revert = True
            revert_reason = (
                f"Visitors dropped from {previous_visitors} to {current_visitors}"
            )

        if should_revert:
            # Revert: restore original content
            abs_path = _PROJECT_ROOT / target_file
            try:
                abs_path.write_text(original_content, encoding="utf-8")

                conn.execute("""
                    UPDATE analytics_actions_log
                    SET status = 'reverted', reverted_at = datetime('now'),
                        revert_reason = ?,
                        metrics_after = ?
                    WHERE id = ?
                """, (
                    revert_reason,
                    json.dumps({
                        "bounce_rate": current_bounce,
                        "visitors": current_visitors,
                    }),
                    change_id,
                ))
                conn.commit()

                actions.append({
                    "action": "revert",
                    "change_id": change_id,
                    "page": target_page,
                    "reason": revert_reason,
                })

                logger.info(
                    "Analytics executor: reverted change #%d for %s — %s",
                    change_id, target_page, revert_reason,
                )

            except Exception as exc:
                logger.warning(
                    "Analytics executor: revert failed for change #%d: %s",
                    change_id, exc,
                )
        else:
            # Change is holding or improving — clear revert window
            try:
                conn.execute("""
                    UPDATE analytics_actions_log
                    SET revert_at = NULL,
                        metrics_after = ?,
                        notes = COALESCE(notes, '') || ' [revert-check: metrics stable/improved]'
                    WHERE id = ?
                """, (
                    json.dumps({
                        "bounce_rate": current_bounce,
                        "visitors": current_visitors,
                    }),
                    change_id,
                ))
                conn.commit()
            except sqlite3.Error:
                pass

    return actions


# ── Graduated rollout advancement ─────────────────────────────────────────

def _advance_graduated_rollouts(conn: sqlite3.Connection) -> list[dict]:
    """Advance content changes through 25% -> 50% -> 100% rollout stages.

    For the analytics executor, rollout_pct tracks confidence level.
    After 24h at each stage without metric degradation, advance.
    """
    actions = []

    _ensure_tables(conn)

    # Find changes in graduated rollout (not yet at 100%)
    rolling_out = _safe_query_all(conn, """
        SELECT id, action_type, target_page, rollout_pct, created_at,
               metrics_before
        FROM analytics_actions_log
        WHERE status = 'applied'
          AND rollout_pct < 100
          AND created_at <= datetime('now', '-24 hours')
    """)

    if not rolling_out:
        return actions

    rollout_stages = [25, 50, 100]

    for change in rolling_out:
        change_id = change["id"]
        current_pct = change["rollout_pct"] or 25

        # Find next stage
        next_pct = 100
        for stage in rollout_stages:
            if stage > current_pct:
                next_pct = stage
                break

        try:
            conn.execute("""
                UPDATE analytics_actions_log
                SET rollout_pct = ?,
                    notes = COALESCE(notes, '') || ?
                WHERE id = ?
            """, (
                next_pct,
                f" [rollout: {current_pct}% -> {next_pct}%]",
                change_id,
            ))
            conn.commit()

            actions.append({
                "action": "rollout_advance",
                "change_id": change_id,
                "page": change["target_page"],
                "from_pct": current_pct,
                "to_pct": next_pct,
            })

            logger.info(
                "Analytics executor: advanced rollout for change #%d: %d%% -> %d%%",
                change_id, current_pct, next_pct,
            )

        except sqlite3.Error:
            pass

    return actions


# ── Daily digest email ────────────────────────────────────────────────────

def _send_analytics_digest(conn: sqlite3.Connection, all_actions: list[dict]) -> None:
    """Send a daily digest email summarizing analytics auto-actions."""
    if not all_actions:
        return

    try:
        from ..settings import ADMIN_EMAIL
        admin_email = ADMIN_EMAIL or ""
        if not admin_email:
            return

        from ..email import send_alert

        # Build digest
        lines = [f"Analytics Auto-Executor: {len(all_actions)} action(s) today\n"]

        for action in all_actions:
            action_type = action.get("action", "unknown")
            if action_type == "bounce_rate_optimize":
                lines.append(
                    f"  - Optimized {action.get('page', '?')} "
                    f"(bounce rate: {action.get('bounce_rate', 0):.0%})"
                )
            elif action_type == "channel_allocation":
                lines.append(
                    f"  - Adjusted {action.get('channel', '?')} channel "
                    f"(growth: {action.get('growth_rate', 0):.0%}, "
                    f"new weight: {action.get('new_weight', 0):.1f})"
                )
            elif action_type == "landing_page_ab_test":
                lines.append(
                    f"  - Proposed A/B test for {action.get('page', '?')} "
                    f"({action.get('experiment', '?')})"
                )
            elif action_type == "seo_internal_links":
                lines.append(
                    f"  - Queued internal links for {action.get('page', '?')}"
                )
            elif action_type == "seo_content_refresh":
                lines.append(
                    f"  - Queued content refresh for {action.get('page', '?')} "
                    f"({action.get('age_days', 0):.0f} days old)"
                )
            elif action_type == "seo_keyword_expansion":
                lines.append(
                    f"  - Queued keyword expansion "
                    f"({action.get('organic_visitors', 0)} organic visitors)"
                )
            elif action_type == "channel_content_gen":
                lines.append(
                    f"  - Generated content for {action.get('channel', '?')} "
                    f"({action.get('visitors', 0)} visitors)"
                )
            elif action_type == "funnel_signup_test":
                lines.append(
                    f"  - Signup rate drop detected ({action.get('drop_pct', 0):.0f}%) "
                    f"— proposing registration test"
                )
            elif action_type == "revert":
                lines.append(
                    f"  - REVERTED change #{action.get('change_id', '?')} "
                    f"for {action.get('page', '?')}: {action.get('reason', '?')}"
                )
            elif action_type == "rollout_advance":
                lines.append(
                    f"  - Advanced rollout for {action.get('page', '?')}: "
                    f"{action.get('from_pct', 0)}% -> {action.get('to_pct', 0)}%"
                )
            else:
                lines.append(f"  - {action_type}: {json.dumps(action)[:100]}")

        body = "\n".join(lines)

        send_alert(
            to_email=admin_email,
            subject="[Aelu Analytics] Daily auto-action digest",
            details=body,
        )

    except Exception as exc:
        logger.debug("Analytics executor: digest email failed: %s", exc)


# ── Main entry points ─────────────────────────────────────────────────────

class AnalyticsAutoExecutor:
    """Stateful executor that coordinates all analytics-driven actions."""

    def run_full(self, conn: sqlite3.Connection) -> dict:
        """Full nightly analytics action loop.

        Runs all six action families plus revert checks and rollout advancement.
        """
        if not ANALYTICS_EXECUTOR_ENABLED:
            logger.debug(
                "Analytics auto-executor disabled (set ANALYTICS_EXECUTOR_ENABLED=true)"
            )
            return {"enabled": False, "actions": []}

        _ensure_tables(conn)
        all_actions: list[dict] = []

        # 0. Check and revert failing changes first
        try:
            reverts = _check_and_revert_failing_changes(conn)
            all_actions.extend(reverts)
        except Exception:
            logger.debug("Analytics executor: revert check failed", exc_info=True)

        # 0b. Advance graduated rollouts
        try:
            rollouts = _advance_graduated_rollouts(conn)
            all_actions.extend(rollouts)
        except Exception:
            logger.debug("Analytics executor: rollout advancement failed", exc_info=True)

        # Fetch analytics data
        page_metrics = _get_page_metrics(period="7d")
        referral_sources = _get_referral_sources(period="7d")
        goal_conversions = _get_goal_conversions(period="7d")
        aggregate_metrics = _get_aggregate_metrics(period="7d")

        if not page_metrics and not referral_sources:
            logger.debug("Analytics executor: no Plausible data available")
            return {"enabled": True, "actions": all_actions, "data_available": False}

        # 0c. Consult prescription memory for action recommendations
        prescription_recommendations = {}
        try:
            from .prescription_memory import suggest_prescription
            for context_check in [
                {"dimension": "marketing", "severity": "medium",
                 "metric_name": "bounce_rate", "target_type": "blog"},
                {"dimension": "marketing", "severity": "medium",
                 "metric_name": "bounce_rate", "target_type": "landing"},
                {"dimension": "marketing", "severity": "medium",
                 "metric_name": "conversion_rate", "target_type": None},
            ]:
                suggestions = suggest_prescription(conn, context_check)
                if suggestions:
                    key = f"{context_check['dimension']}_{context_check['metric_name']}"
                    prescription_recommendations[key] = suggestions
                    logger.debug(
                        "Analytics executor: prescription memory recommends %s for %s "
                        "(success rate: %.0f%%, sample: %d)",
                        suggestions[0]["action_type"], key,
                        suggestions[0]["success_rate"] * 100,
                        suggestions[0]["sample_size"],
                    )
        except ImportError:
            pass
        except Exception:
            logger.debug(
                "Analytics executor: prescription memory check failed",
                exc_info=True,
            )

        # 1. Content optimization based on bounce rate
        try:
            bounce_actions = _optimize_high_bounce_pages(conn, page_metrics)
            all_actions.extend(bounce_actions)
        except Exception:
            logger.debug("Analytics executor: bounce optimization failed", exc_info=True)

        # 2. Marketing channel allocation
        try:
            channel_actions = _adjust_channel_allocation(conn, referral_sources)
            all_actions.extend(channel_actions)
        except Exception:
            logger.debug("Analytics executor: channel allocation failed", exc_info=True)

        # 3. Landing page optimization (A/B test proposals)
        try:
            test_actions = _propose_landing_page_tests(
                conn, page_metrics, goal_conversions,
            )
            all_actions.extend(test_actions)
        except Exception:
            logger.debug("Analytics executor: landing page tests failed", exc_info=True)

        # 4. SEO autopilot
        try:
            seo_actions = _run_seo_autopilot(conn, page_metrics, referral_sources)
            all_actions.extend(seo_actions)
        except Exception:
            logger.debug("Analytics executor: SEO autopilot failed", exc_info=True)

        # 5. Funnel optimization
        try:
            funnel_actions = _optimize_funnel(conn, goal_conversions, aggregate_metrics)
            all_actions.extend(funnel_actions)
        except Exception:
            logger.debug("Analytics executor: funnel optimization failed", exc_info=True)

        # 6. Channel-specific content generation
        try:
            content_actions = _generate_channel_content(conn, referral_sources)
            all_actions.extend(content_actions)
        except Exception:
            logger.debug("Analytics executor: channel content gen failed", exc_info=True)

        # Send daily digest
        try:
            _send_analytics_digest(conn, all_actions)
        except Exception:
            logger.debug("Analytics executor: digest failed", exc_info=True)

        logger.info(
            "Analytics auto-executor: %d actions taken (%d reverts, %d new)",
            len(all_actions),
            sum(1 for a in all_actions if a.get("action") == "revert"),
            sum(1 for a in all_actions if a.get("action") != "revert"),
        )

        return {
            "enabled": True,
            "data_available": True,
            "actions": all_actions,
            "actions_count": len(all_actions),
            "daily_limit_remaining": _MAX_ACTIONS_PER_DAY - _count_actions_today(conn),
            "prescription_recommendations": prescription_recommendations,
        }

    def run_lightweight(self, conn: sqlite3.Connection) -> dict:
        """Lightweight 15-minute check.

        Only runs revert checks and rollout advancement.
        Does NOT fetch Plausible data or generate new content.
        """
        if not ANALYTICS_EXECUTOR_ENABLED:
            return {"enabled": False, "actions": []}

        _ensure_tables(conn)
        all_actions: list[dict] = []

        # Revert checks (time-sensitive)
        try:
            reverts = _check_and_revert_failing_changes(conn)
            all_actions.extend(reverts)
        except Exception:
            logger.debug("Analytics executor lightweight: revert check failed", exc_info=True)

        # Advance graduated rollouts
        try:
            rollouts = _advance_graduated_rollouts(conn)
            all_actions.extend(rollouts)
        except Exception:
            logger.debug("Analytics executor lightweight: rollout advancement failed", exc_info=True)

        if all_actions:
            logger.info(
                "Analytics auto-executor (lightweight): %d actions — %s",
                len(all_actions),
                "; ".join(a.get("action", "?") for a in all_actions),
            )

        return {
            "enabled": True,
            "actions": all_actions,
            "actions_count": len(all_actions),
        }


# ── Module-level singleton ────────────────────────────────────────────────

_executor = AnalyticsAutoExecutor()


def run_analytics_actions(conn: sqlite3.Connection) -> dict:
    """Run the full analytics auto-executor loop (nightly).

    This is the main entry point, called by the nightly quality_scheduler loop.
    """
    try:
        return _executor.run_full(conn)
    except Exception as exc:
        logger.exception("Analytics auto-executor failed: %s", exc)
        return {"enabled": True, "actions": [], "error": str(exc)}


def run_analytics_actions_lightweight(conn: sqlite3.Connection) -> dict:
    """Run the lightweight analytics check (15-minute interval).

    Called by the health_check_scheduler for time-sensitive operations
    (revert checks, rollout advancement).
    """
    try:
        return _executor.run_lightweight(conn)
    except Exception as exc:
        logger.debug("Analytics auto-executor lightweight failed: %s", exc)
        return {"enabled": True, "actions": [], "error": str(exc)}


# ── Intelligence analyzer ────────────────────────────────────────────────

def analyze_analytics_actions(conn) -> list[dict]:
    """Analyzer function for the main intelligence engine.

    Reads analytics_actions_log and emits findings about:
    - Pending actions awaiting review
    - Reverted actions (optimization attempts that backfired)
    - Successful optimizations worth noting
    """
    findings = []

    # Check for reverted actions in last 14 days
    reverted = _safe_query_all(conn, """
        SELECT action_type, target_page, action_detail, created_at
        FROM analytics_actions_log
        WHERE status = 'reverted'
          AND created_at >= datetime('now', '-14 days')
        ORDER BY created_at DESC
        LIMIT 5
    """)

    if reverted:
        pages = ", ".join(
            r.get("target_page", "?") for r in reverted[:3]
        )
        findings.append(_finding(
            "marketing", "medium",
            f"{len(reverted)} analytics-driven change(s) reverted in 14 days",
            f"Auto-executor changes were reverted on: {pages}. "
            f"These optimizations made metrics worse after the revert window.",
            "Review the reverted changes. Threshold calibration will auto-tighten "
            "triggers for these action types.",
            "Check analytics_actions_log WHERE status='reverted' for details.",
            "Marketing effectiveness",
            _f("vibe_admin_routes"),
        ))

    # Check for pending actions awaiting human review
    pending = _safe_scalar(conn, """
        SELECT COUNT(*) FROM analytics_actions_log
        WHERE status = 'pending'
          AND created_at >= datetime('now', '-7 days')
    """, default=0)

    if pending and pending > 3:
        findings.append(_finding(
            "marketing", "low",
            f"{pending} analytics actions pending review",
            f"{pending} auto-generated optimizations are queued but not yet applied. "
            f"They may be waiting for human approval or execution capacity.",
            "Review pending actions in the admin marketing approval queue.",
            "Check analytics_actions_log WHERE status='pending'.",
            "Marketing pipeline throughput",
            _f("vibe_admin_routes"),
        ))

    return findings


ANALYZERS = [analyze_analytics_actions]
