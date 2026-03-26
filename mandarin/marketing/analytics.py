"""Plausible Analytics server-side API integration + UTM tracking.

Pulls page views, referrers, and UTM breakdown data from Plausible's
Stats API. Maps UTM parameters back to content variants for A/B attribution.

Exports:
    get_page_views(page, period) -> dict | None
    get_referrers(period) -> list[dict] | None
    get_utm_breakdown(utm_source, period) -> list[dict] | None
    get_goal_conversions(goal, period) -> dict | None
    is_plausible_configured() -> bool
"""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://plausible.io/api/v1"
_CACHE_TTL = 3600  # 1 hour
_cache: dict[str, tuple[float, object]] = {}


def is_plausible_configured() -> bool:
    """Check if Plausible API is configured."""
    return bool(
        os.environ.get("PLAUSIBLE_API_KEY")
        and os.environ.get("PLAUSIBLE_DOMAIN")
    )


def _api_get(endpoint: str, params: dict | None = None) -> dict | None:
    """Make an authenticated GET request to the Plausible API."""
    if not is_plausible_configured():
        return None

    api_key = os.environ["PLAUSIBLE_API_KEY"]
    domain = os.environ["PLAUSIBLE_DOMAIN"]

    # Cache check
    cache_key = f"{endpoint}:{params}"
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if time.monotonic() - ts < _CACHE_TTL:
            return data

    try:
        all_params = {"site_id": domain}
        if params:
            all_params.update(params)

        resp = httpx.get(
            f"{_API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {api_key}"},
            params=all_params,
            timeout=15.0,
        )

        if resp.status_code == 200:
            data = resp.json()
            _cache[cache_key] = (time.monotonic(), data)
            return data

        logger.warning("Plausible API %d: %s", resp.status_code, resp.text[:200])
        return None

    except Exception as e:
        logger.debug("Plausible API error: %s", e)
        return None


def get_page_views(page: str = "", period: str = "7d") -> dict | None:
    """Get aggregate page views for a specific page or all pages."""
    params = {"period": period, "metrics": "visitors,pageviews,bounce_rate,visit_duration"}
    if page:
        params["filters"] = f"event:page=={page}"
    return _api_get("/stats/aggregate", params)


def get_referrers(period: str = "7d") -> list[dict] | None:
    """Get referrer breakdown."""
    data = _api_get("/stats/breakdown", {
        "period": period,
        "property": "visit:source",
        "metrics": "visitors,pageviews",
    })
    return data.get("results") if data else None


def get_utm_breakdown(utm_source: str = "", period: str = "7d") -> list[dict] | None:
    """Get UTM campaign breakdown, optionally filtered by source."""
    params = {
        "period": period,
        "property": "visit:utm_campaign",
        "metrics": "visitors,pageviews",
    }
    if utm_source:
        params["filters"] = f"visit:utm_source=={utm_source}"

    data = _api_get("/stats/breakdown", params)
    return data.get("results") if data else None


def get_goal_conversions(goal: str, period: str = "7d") -> dict | None:
    """Get conversion count for a specific goal."""
    return _api_get("/stats/aggregate", {
        "period": period,
        "metrics": "visitors,events",
        "filters": f"event:goal=={goal}",
    })
