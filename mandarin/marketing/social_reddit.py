"""Reddit API integration — posting with mandatory approval queue.

ALL Reddit posts require human approval before posting. Posts are queued
in the marketing_approval_queue table and must be approved via admin UI
or email before the scheduler will post them.

Dual-account strategy:
- REDDIT_USERNAME / REDDIT_PASSWORD: official brand account (u/aeluapp or similar)
  Used for: launch announcements, product updates, official support
- REDDIT_ALT_USERNAME / REDDIT_ALT_PASSWORD: pseudonymous community account
  Used for: value posts, study tips, "hey guys here's what worked for me"
  This account should have established karma from genuine participation

The scheduler tags each post with which account to use based on content type.
Both accounts require approval before posting.

Uses raw httpx (no PRAW dependency). OAuth2 "script" app type.

Exports:
    queue_reddit_post(conn, subreddit, title, body, content_id, account) -> int
    post_approved(conn, queue_id) -> PostResult
    get_post_metrics(post_id) -> dict | None
    is_reddit_configured() -> bool
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_API_BASE = "https://oauth.reddit.com"
_USER_AGENT = "aelu-marketing/1.0"

# Rate limiting: Reddit API = 100 requests/min, but we post sparingly
_MIN_POST_INTERVAL = 600  # 10 minutes between posts
_last_post_time = 0.0

# Cached OAuth token
_cached_token: str = ""
_token_expires: float = 0.0


@dataclass
class PostResult:
    success: bool
    platform: str = "reddit"
    post_id: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)


def is_reddit_configured(account: str = "official") -> bool:
    """Check if Reddit API credentials are configured for the specified account.

    account: "official" (brand account) or "community" (pseudonymous account)
    """
    if account == "community":
        return bool(
            os.environ.get("REDDIT_CLIENT_ID")
            and os.environ.get("REDDIT_CLIENT_SECRET")
            and os.environ.get("REDDIT_ALT_USERNAME")
            and os.environ.get("REDDIT_ALT_PASSWORD")
        )
    return bool(
        os.environ.get("REDDIT_CLIENT_ID")
        and os.environ.get("REDDIT_CLIENT_SECRET")
        and os.environ.get("REDDIT_USERNAME")
        and os.environ.get("REDDIT_PASSWORD")
    )


def _get_token() -> str | None:
    """Get OAuth2 access token using script app credentials."""
    global _cached_token, _token_expires

    if _cached_token and time.monotonic() < _token_expires:
        return _cached_token

    try:
        resp = httpx.post(
            _TOKEN_URL,
            auth=(os.environ["REDDIT_CLIENT_ID"], os.environ["REDDIT_CLIENT_SECRET"]),
            data={
                "grant_type": "password",
                "username": os.environ["REDDIT_USERNAME"],
                "password": os.environ["REDDIT_PASSWORD"],
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            _cached_token = data["access_token"]
            _token_expires = time.monotonic() + data.get("expires_in", 3600) - 60
            return _cached_token
        logger.warning("Reddit auth failed: %d %s", resp.status_code, resp.text[:200])
        return None
    except Exception as e:
        logger.warning("Reddit auth error: %s", e)
        return None


def queue_reddit_post(
    conn, subreddit: str, title: str, body: str, content_id: str = "",
    variant_id: str = "",
) -> int:
    """Queue a Reddit post for human approval. Returns queue row ID.

    ALL Reddit posts go through this queue — never auto-posted.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    content_text = f"r/{subreddit}\n\nTitle: {title}\n\n{body}"

    cursor = conn.execute("""
        INSERT INTO marketing_approval_queue
            (content_id, variant_id, platform, content_text, reason, status, submitted_at)
        VALUES (?, ?, 'reddit', ?, 'All Reddit posts require approval', 'pending', ?)
    """, (content_id, variant_id, content_text, now))
    conn.commit()

    queue_id = cursor.lastrowid
    logger.info("Reddit post queued for approval (queue_id=%d, r/%s)", queue_id, subreddit)
    return queue_id


def post_approved(conn, queue_id: int) -> PostResult:
    """Post an approved Reddit submission. Called after human approval."""
    global _last_post_time

    if not is_reddit_configured():
        return PostResult(success=False, error="Reddit API not configured")

    # Rate limit
    now = time.monotonic()
    if now - _last_post_time < _MIN_POST_INTERVAL:
        wait = int(_MIN_POST_INTERVAL - (now - _last_post_time))
        return PostResult(success=False, error=f"Rate limited, wait {wait}s")

    # Load approved post from queue
    row = conn.execute(
        "SELECT content_text, content_id FROM marketing_approval_queue WHERE id = ? AND status = 'approved'",
        (queue_id,),
    ).fetchone()
    if not row:
        return PostResult(success=False, error=f"Queue item {queue_id} not found or not approved")

    # Parse the queued content: "r/subreddit\n\nTitle: ...\n\n..."
    lines = row["content_text"].split("\n\n", 2)
    if len(lines) < 3:
        return PostResult(success=False, error="Malformed queue content")

    subreddit = lines[0].replace("r/", "").strip()
    title = lines[1].replace("Title: ", "").strip()
    body = lines[2].strip()

    token = _get_token()
    if not token:
        return PostResult(success=False, error="Failed to get Reddit OAuth token")

    try:
        resp = httpx.post(
            f"{_API_BASE}/api/submit",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": _USER_AGENT,
            },
            data={
                "sr": subreddit,
                "kind": "self",
                "title": title,
                "text": body,
                "api_type": "json",
            },
            timeout=15.0,
        )

        _last_post_time = time.monotonic()

        if resp.status_code == 200:
            data = resp.json()
            errors = data.get("json", {}).get("errors", [])
            if errors:
                return PostResult(success=False, error=str(errors))

            post_data = data.get("json", {}).get("data", {})
            post_id = post_data.get("id", "") or post_data.get("name", "")
            logger.info("Reddit post submitted: r/%s (id=%s)", subreddit, post_id)
            return PostResult(success=True, post_id=post_id, data=data)

        return PostResult(success=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}")

    except Exception as e:
        logger.exception("Reddit post failed")
        return PostResult(success=False, error=str(e))


def get_post_metrics(post_id: str) -> dict | None:
    """Get metrics for a Reddit post (upvotes, comments, ratio)."""
    if not is_reddit_configured():
        return None

    token = _get_token()
    if not token:
        return None

    try:
        resp = httpx.get(
            f"{_API_BASE}/api/info",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": _USER_AGENT,
            },
            params={"id": f"t3_{post_id}"},
            timeout=10.0,
        )

        if resp.status_code == 200:
            children = resp.json().get("data", {}).get("children", [])
            if children:
                post = children[0].get("data", {})
                return {
                    "upvotes": post.get("ups", 0),
                    "downvotes": post.get("downs", 0),
                    "score": post.get("score", 0),
                    "upvote_ratio": post.get("upvote_ratio", 0.0),
                    "num_comments": post.get("num_comments", 0),
                }
        return None

    except Exception as e:
        logger.debug("Failed to get Reddit metrics: %s", e)
        return None
