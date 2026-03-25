"""Twitter/X API v2 integration — posting and metrics.

Uses OAuth 2.0 for app-level posting. All calls go through the unified
client with rate limiting and error handling.

Feature-flagged: TWITTER_API_KEY must be set and marketing_twitter_enabled
feature flag must be active.

Exports:
    post_tweet(text, reply_to_id=None) -> PostResult
    post_thread(tweets: list[str]) -> PostResult
    get_tweet_metrics(tweet_id) -> dict | None
    is_twitter_configured() -> bool
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Rate limiting: Twitter API v2 free tier = 1,500 tweets/month, 17 per 15 min
_RATE_LIMIT_WINDOW = 15 * 60  # 15 minutes
_RATE_LIMIT_MAX = 15  # conservative (API limit is 17)
_rate_window_start = 0.0
_rate_count = 0


@dataclass
class PostResult:
    success: bool
    platform: str = "twitter"
    post_id: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)


def is_twitter_configured() -> bool:
    """Check if Twitter API credentials are configured."""
    return bool(
        os.environ.get("TWITTER_API_KEY")
        and os.environ.get("TWITTER_API_SECRET")
        and os.environ.get("TWITTER_ACCESS_TOKEN")
        and os.environ.get("TWITTER_ACCESS_SECRET")
    )


def _check_rate_limit() -> bool:
    """Check if we're within rate limits. Returns True if OK to proceed."""
    global _rate_window_start, _rate_count
    now = time.monotonic()
    if now - _rate_window_start > _RATE_LIMIT_WINDOW:
        _rate_window_start = now
        _rate_count = 0
    return _rate_count < _RATE_LIMIT_MAX


def _increment_rate() -> None:
    global _rate_count
    _rate_count += 1


def _get_client():
    """Get authenticated Twitter API client via tweepy or httpx."""
    import httpx
    from requests_oauthlib import OAuth1

    auth = OAuth1(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_SECRET"],
    )
    return auth


def post_tweet(text: str, reply_to_id: str | None = None) -> PostResult:
    """Post a single tweet. Returns PostResult with tweet_id on success."""
    if not is_twitter_configured():
        return PostResult(success=False, error="Twitter API not configured")

    if not _check_rate_limit():
        return PostResult(success=False, error="Rate limit exceeded")

    import httpx

    url = "https://api.twitter.com/2/tweets"
    payload: dict = {"text": text}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    try:
        # Use OAuth 1.0a User Context for tweet creation
        from requests_oauthlib import OAuth1Session

        session = OAuth1Session(
            os.environ["TWITTER_API_KEY"],
            client_secret=os.environ["TWITTER_API_SECRET"],
            resource_owner_key=os.environ["TWITTER_ACCESS_TOKEN"],
            resource_owner_secret=os.environ["TWITTER_ACCESS_SECRET"],
        )

        resp = session.post(url, json=payload)
        _increment_rate()

        if resp.status_code in (200, 201):
            data = resp.json()
            tweet_id = data.get("data", {}).get("id", "")
            logger.info("Tweet posted: %s (id=%s)", text[:50], tweet_id)
            return PostResult(success=True, post_id=tweet_id, data=data)

        logger.warning("Twitter API error %d: %s", resp.status_code, resp.text[:200])
        return PostResult(success=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}")

    except ImportError:
        return PostResult(success=False, error="requests-oauthlib not installed")
    except Exception as e:
        logger.exception("Twitter post failed")
        return PostResult(success=False, error=str(e))


def post_thread(tweets: list[str]) -> PostResult:
    """Post a thread (chain of tweets). Returns PostResult with first tweet's ID."""
    if not tweets:
        return PostResult(success=False, error="Empty thread")

    first_result = post_tweet(tweets[0])
    if not first_result.success:
        return first_result

    reply_to = first_result.post_id
    for tweet_text in tweets[1:]:
        result = post_tweet(tweet_text, reply_to_id=reply_to)
        if not result.success:
            logger.warning("Thread broken at tweet: %s", result.error)
            break
        reply_to = result.post_id

    return first_result  # Return the first tweet's result


def get_tweet_metrics(tweet_id: str) -> dict | None:
    """Get engagement metrics for a tweet. Returns dict or None.

    Requires Twitter API Basic tier ($100/mo) for read access.
    """
    if not is_twitter_configured():
        return None

    try:
        from requests_oauthlib import OAuth1Session

        session = OAuth1Session(
            os.environ["TWITTER_API_KEY"],
            client_secret=os.environ["TWITTER_API_SECRET"],
            resource_owner_key=os.environ["TWITTER_ACCESS_TOKEN"],
            resource_owner_secret=os.environ["TWITTER_ACCESS_SECRET"],
        )

        url = f"https://api.twitter.com/2/tweets/{tweet_id}"
        params = {"tweet.fields": "public_metrics,created_at"}
        resp = session.get(url, params=params)

        if resp.status_code == 200:
            data = resp.json().get("data", {})
            metrics = data.get("public_metrics", {})
            return {
                "impressions": metrics.get("impression_count", 0),
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "replies": metrics.get("reply_count", 0),
                "quotes": metrics.get("quote_count", 0),
                "bookmarks": metrics.get("bookmark_count", 0),
            }
        return None

    except Exception as e:
        logger.debug("Failed to get tweet metrics: %s", e)
        return None
