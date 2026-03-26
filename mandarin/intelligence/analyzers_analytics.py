"""Plausible analytics analyzer — pulls visitor data and generates findings.

Calls the Plausible Stats API v1 to retrieve aggregate metrics, traffic
sources, and per-page performance.

Generates findings when:
  - A specific page has bounce rate >80% (medium/high)
  - A landing page has zero visits in 7 days (medium)
  - Traffic drops >50% week over week (high)
  - A referral source is driving significant traffic (informational)
  - A blog post has high traffic but high bounce rate (medium)

Gracefully skips when PLAUSIBLE_API_KEY is not configured.

Exports:
    ANALYZERS: list of analyzer functions
    fetch_analytics_stats: standalone function for admin dashboard use
"""

import logging

import requests

from ._base import _finding

logger = logging.getLogger(__name__)

# Plausible Stats API v1 base
_API_BASE = "https://plausible.io/api/v1/stats"


def _get_config() -> tuple[str, str]:
    """Retrieve the Plausible API key and site ID from settings.

    Returns (api_key, site_id). Both empty strings if not configured.
    """
    try:
        from ..settings import PLAUSIBLE_API_KEY, PLAUSIBLE_DOMAIN
        return (PLAUSIBLE_API_KEY or ""), (PLAUSIBLE_DOMAIN or "")
    except (ImportError, AttributeError):
        return "", ""


def _api_get(endpoint: str, params: dict, api_key: str) -> dict | None:
    """Make an authenticated GET request to the Plausible Stats API.

    Returns parsed JSON on success, None on failure.
    """
    url = f"{_API_BASE}/{endpoint}"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning("Plausible API %s returned status %s: %s",
                           endpoint, resp.status_code, resp.text[:200])
            return None
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Plausible API call failed (%s): %s", endpoint, exc)
        return None


def fetch_analytics_stats() -> dict | None:
    """Fetch analytics data from Plausible Stats API.

    Returns a dict with:
        aggregate: dict with visitors, pageviews, bounce_rate, visit_duration
        sources: list of {source, visitors} dicts
        pages: list of {page, visitors, bounce_rate} dicts
        site_id: the Plausible site ID queried

    Returns None if API key is not set or the API calls fail.
    """
    api_key, site_id = _get_config()
    if not api_key or not site_id:
        return None

    base_params = {"site_id": site_id, "period": "7d"}

    # 1. Aggregate metrics
    aggregate_data = _api_get("aggregate", {
        **base_params,
        "metrics": "visitors,pageviews,bounce_rate,visit_duration",
    }, api_key)

    if aggregate_data is None:
        return None

    # 2. Traffic sources breakdown
    sources_data = _api_get("breakdown", {
        **base_params,
        "property": "visit:source",
        "metrics": "visitors",
    }, api_key)

    # 3. Per-page breakdown
    pages_data = _api_get("breakdown", {
        **base_params,
        "property": "visit:page",
        "metrics": "visitors,bounce_rate",
    }, api_key)

    # Parse aggregate results — Plausible returns {"results": {"visitors": {"value": N}, ...}}
    agg_results = aggregate_data.get("results", {})
    aggregate = {
        "visitors": agg_results.get("visitors", {}).get("value", 0),
        "pageviews": agg_results.get("pageviews", {}).get("value", 0),
        "bounce_rate": agg_results.get("bounce_rate", {}).get("value", 0),
        "visit_duration": agg_results.get("visit_duration", {}).get("value", 0),
    }

    # Parse sources — Plausible returns {"results": [{"source": "...", "visitors": N}, ...]}
    sources = []
    if sources_data:
        for entry in sources_data.get("results", []):
            sources.append({
                "source": entry.get("source", "Unknown"),
                "visitors": entry.get("visitors", 0),
            })

    # Parse pages — Plausible returns {"results": [{"page": "/...", "visitors": N, "bounce_rate": N}, ...]}
    pages = []
    if pages_data:
        for entry in pages_data.get("results", []):
            pages.append({
                "page": entry.get("page", ""),
                "visitors": entry.get("visitors", 0),
                "bounce_rate": entry.get("bounce_rate", 0),
            })

    return {
        "aggregate": aggregate,
        "sources": sources,
        "pages": pages,
        "site_id": site_id,
    }


def _fetch_previous_period_visitors(api_key: str, site_id: str) -> int | None:
    """Fetch visitor count for the previous 7-day period for trend comparison."""
    data = _api_get("aggregate", {
        "site_id": site_id,
        "period": "custom",
        "date": _get_previous_period_range(),
        "metrics": "visitors",
    }, api_key)
    if data is None:
        return None
    results = data.get("results", {})
    return results.get("visitors", {}).get("value", 0)


def _get_previous_period_range() -> str:
    """Return date range string for the 7-day period before the current 7-day period.

    Format: 'YYYY-MM-DD,YYYY-MM-DD' (start,end).
    """
    from datetime import date, timedelta
    today = date.today()
    prev_end = today - timedelta(days=7)
    prev_start = prev_end - timedelta(days=6)
    return f"{prev_start.isoformat()},{prev_end.isoformat()}"


def _analyze_analytics(conn) -> list[dict]:
    """Analyzer function that checks Plausible analytics for actionable insights.

    Follows the standard analyzer pattern: takes a db connection, returns
    a list of finding dicts.
    """
    findings: list[dict] = []

    stats = fetch_analytics_stats()
    if stats is None:
        # API key not set or API unreachable — skip silently
        return findings

    aggregate = stats.get("aggregate", {})
    sources = stats.get("sources", [])
    pages = stats.get("pages", [])
    site_id = stats.get("site_id", "")

    total_visitors = aggregate.get("visitors", 0)
    overall_bounce = aggregate.get("bounce_rate", 0)

    # ── 1. High bounce rate on specific pages (>80%) ─────────────────
    for page in pages:
        page_path = page.get("page", "")
        page_visitors = page.get("visitors", 0)
        page_bounce = page.get("bounce_rate", 0)

        # Only flag pages with meaningful traffic (at least 10 visitors)
        if page_bounce > 80 and page_visitors >= 10:
            severity = "high" if page_bounce > 90 else "medium"
            findings.append(_finding(
                "marketing", severity,
                f"High bounce rate on {page_path}: {page_bounce}%",
                f"Page '{page_path}' has a {page_bounce}% bounce rate over the last "
                f"7 days with {page_visitors} visitors. This suggests the page content "
                f"may not match visitor expectations, or the page loads too slowly.",
                "Review the page content, headline, and CTA alignment with traffic "
                "sources. Check page load performance. Consider A/B testing the hero "
                "section or CTA placement.",
                f"Investigate high bounce rate ({page_bounce}%) on '{page_path}'. "
                f"Check page load speed, content relevance, and CTA clarity. "
                f"Consider running an A/B test on the CTA placement or hero copy.",
                "Visitor engagement",
                [f"marketing/landing{page_path}" if page_path.startswith("/") else page_path],
            ))

    # ── 2. Blog post with high traffic but high bounce rate ──────────
    for page in pages:
        page_path = page.get("page", "")
        page_visitors = page.get("visitors", 0)
        page_bounce = page.get("bounce_rate", 0)

        if ("/blog/" in page_path and page_visitors >= 10
                and page_bounce > 75 and page_visitors >= total_visitors * 0.05):
            findings.append(_finding(
                "marketing", "medium",
                f"Blog post driving traffic but losing visitors: {page_path}",
                f"Blog post '{page_path}' attracted {page_visitors} visitors "
                f"(top traffic) but has {page_bounce}% bounce rate. Visitors are "
                f"reading the post but not converting or exploring further.",
                "Add a stronger CTA within the blog post. Consider inline signup "
                "forms, related post links, or a sticky CTA bar. A/B test the CTA "
                "placement (top vs bottom vs inline).",
                f"Blog post '{page_path}' has high traffic ({page_visitors} visitors) but "
                f"{page_bounce}% bounce rate. Auto-generate an A/B test for CTA placement "
                f"on this page — test inline CTA vs end-of-post CTA.",
                "Content conversion",
                [f"marketing/landing{page_path}" if page_path.startswith("/") else page_path],
            ))

    # ── 3. Top referral sources — informational findings ──────────────
    if sources and total_visitors > 0:
        for source in sources[:3]:
            source_name = source.get("source", "Unknown")
            source_visitors = source.get("visitors", 0)
            source_pct = round(source_visitors / total_visitors * 100, 1) if total_visitors else 0

            if source_pct >= 25:
                findings.append(_finding(
                    "marketing", "low",
                    f"Top referral: {source_name} driving {source_pct}% of traffic",
                    f"'{source_name}' is the leading traffic source with {source_visitors} "
                    f"visitors ({source_pct}% of total) in the last 7 days. This channel "
                    f"is performing well and may warrant increased investment.",
                    f"Increase posting frequency and content quality for {source_name}. "
                    f"Analyze which specific content/links on {source_name} drive the "
                    f"most traffic and double down.",
                    f"'{source_name}' is driving {source_pct}% of traffic ({source_visitors} "
                    f"visitors). Increase content production for this channel. Review which "
                    f"specific {source_name} content/posts drove the most visits.",
                    "Traffic acquisition",
                    ["marketing/social-media.md", "marketing/reddit-playbook.md"],
                ))

    # ── 4. Landing pages with zero visits ────────────────────────────
    # Check known marketing pages from the database
    try:
        known_pages = conn.execute("""
            SELECT page_slug FROM pi_marketing_pages
            WHERE page_slug IS NOT NULL AND page_slug != ''
        """).fetchall()
        visited_paths = {p.get("page", "") for p in pages}

        for row in known_pages:
            slug = row["page_slug"]
            # Normalize: the DB might store "vs-anki" and Plausible reports "/vs-anki"
            normalized = f"/{slug}" if not slug.startswith("/") else slug
            if normalized not in visited_paths and slug not in visited_paths:
                findings.append(_finding(
                    "marketing", "medium",
                    f"Landing page with zero traffic: {slug}",
                    f"Marketing page '{slug}' received zero visits in the last 7 days. "
                    f"It may not be indexed by search engines, not linked from anywhere, "
                    f"or not discoverable.",
                    "Submit the page to Google Search Console for indexing. Add "
                    "internal links from high-traffic pages. Check that the page "
                    "appears in the sitemap.",
                    f"Landing page '{slug}' has zero traffic after 7 days. Submit to "
                    f"Google Search Console for indexing. Add internal links from "
                    f"high-traffic pages. Verify it appears in sitemap.xml.",
                    "Page discoverability",
                    [f"marketing/landing/{slug}.html"],
                ))
    except Exception:
        # pi_marketing_pages table may not exist yet — skip gracefully
        pass

    # ── 5. Traffic trend — week over week drop ───────────────────────
    api_key, _ = _get_config()
    prev_visitors = _fetch_previous_period_visitors(api_key, site_id)
    if prev_visitors is not None and prev_visitors > 0:
        change_pct = round((total_visitors - prev_visitors) / prev_visitors * 100, 1)
        if change_pct <= -50:
            findings.append(_finding(
                "marketing", "high",
                f"Traffic dropped {abs(change_pct)}% week over week",
                f"Visitors fell from {prev_visitors} to {total_visitors} "
                f"({change_pct}% change) compared to the previous 7-day period. "
                f"This is a significant decline that may indicate a technical issue, "
                f"lost ranking, or external factor.",
                "Check Google Search Console for indexing issues or ranking drops. "
                "Review recent deployments for broken pages or redirects. Check "
                "if any major referral source stopped sending traffic.",
                f"URGENT: Traffic dropped {abs(change_pct)}% week over week "
                f"({prev_visitors} to {total_visitors} visitors). Check Google Search "
                f"Console for deindexing, review recent deployments for broken pages, "
                f"and verify all marketing landing pages are accessible.",
                "Traffic health",
                ["marketing/landing/index.html", "fly.toml"],
            ))
        elif change_pct >= 50 and total_visitors >= 20:
            # Traffic is growing significantly — positive signal
            findings.append(_finding(
                "marketing", "low",
                f"Traffic grew {change_pct}% week over week",
                f"Visitors increased from {prev_visitors} to {total_visitors} "
                f"({change_pct}% growth) compared to the previous 7-day period. "
                f"This growth trend suggests marketing efforts are gaining traction.",
                "Capitalize on the growth by expanding the content calendar. "
                "Identify which channels and pages drove the increase and "
                "double down on those strategies.",
                f"Traffic grew {change_pct}% week over week ({prev_visitors} to "
                f"{total_visitors}). Identify the growth drivers and expand the "
                f"content calendar to sustain momentum.",
                "Growth trajectory",
                ["marketing/community-content.md", "marketing/social-media.md"],
            ))

    return findings


# ── Exported analyzer list ────────────────────────────────────────────────

ANALYZERS = [_analyze_analytics]
