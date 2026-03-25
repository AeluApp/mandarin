"""TikTok Content Publishing API integration — photo carousels and video posts.

Uses TikTok's Content Publishing API v2 for posting. Supports:
- Photo carousels (educational content, tips — easiest to auto-generate)
- Video uploads (screen recordings, pre-recorded shorts)

Photo carousels are the primary auto-post format since they can be generated
from text content without video production. The content optimizer generates
carousel slides from tweet/thread content.

Feature-flagged: TIKTOK_CLIENT_KEY must be set.

Exports:
    post_carousel(title, slides, conn=None) -> PostResult
    post_video(title, video_url, conn=None) -> PostResult
    is_tiktok_configured() -> bool
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_API_BASE = "https://open.tiktokapis.com/v2"

# Rate limiting
_MIN_POST_INTERVAL = 300  # 5 minutes between posts
_last_post_time = 0.0

# OAuth token cache
_cached_token: str = ""
_token_expires: float = 0.0


@dataclass
class PostResult:
    success: bool
    platform: str = "tiktok"
    post_id: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)


def is_tiktok_configured() -> bool:
    """Check if TikTok API credentials are configured."""
    return bool(
        os.environ.get("TIKTOK_CLIENT_KEY")
        and os.environ.get("TIKTOK_CLIENT_SECRET")
        and os.environ.get("TIKTOK_ACCESS_TOKEN")
    )


def _get_headers() -> dict:
    """Get auth headers for TikTok API."""
    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _check_rate_limit() -> bool:
    global _last_post_time
    now = time.monotonic()
    return now - _last_post_time >= _MIN_POST_INTERVAL


def post_carousel(
    title: str,
    image_urls: list[str],
    description: str = "",
    hashtags: list[str] | None = None,
) -> PostResult:
    """Post a photo carousel to TikTok.

    Args:
        title: Post title (not shown on TikTok, used for logging)
        image_urls: List of public image URLs (2-35 images, 1080x1920 recommended)
        description: Post caption text
        hashtags: Optional hashtags to append to description
    """
    global _last_post_time

    if not is_tiktok_configured():
        return PostResult(success=False, error="TikTok API not configured")

    if not _check_rate_limit():
        return PostResult(success=False, error="Rate limited")

    if len(image_urls) < 2:
        return PostResult(success=False, error="Carousel needs at least 2 images")

    if len(image_urls) > 35:
        image_urls = image_urls[:35]

    # Append hashtags to description
    caption = description
    if hashtags:
        caption += "\n\n" + " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)

    try:
        import httpx

        # Step 1: Initialize photo post
        init_resp = httpx.post(
            f"{_API_BASE}/post/publish/content/init/",
            headers=_get_headers(),
            json={
                "post_info": {
                    "title": caption[:2200],  # TikTok caption limit
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_comment": False,
                    "auto_add_music": True,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "photo_cover_index": 0,
                    "photo_images": image_urls,
                },
                "post_mode": "DIRECT_POST",
                "media_type": "PHOTO",
            },
            timeout=30.0,
        )

        _last_post_time = time.monotonic()

        if init_resp.status_code == 200:
            data = init_resp.json()
            if data.get("error", {}).get("code") == "ok":
                publish_id = data.get("data", {}).get("publish_id", "")
                logger.info("TikTok carousel posted: %s (id=%s)", title[:50], publish_id)
                return PostResult(success=True, post_id=publish_id, data=data)
            else:
                error_msg = data.get("error", {}).get("message", "Unknown error")
                return PostResult(success=False, error=error_msg)

        return PostResult(success=False, error=f"HTTP {init_resp.status_code}")

    except ImportError:
        return PostResult(success=False, error="httpx not installed")
    except Exception as e:
        logger.exception("TikTok post failed")
        return PostResult(success=False, error=str(e))


def post_video(
    title: str,
    video_url: str,
    description: str = "",
    hashtags: list[str] | None = None,
) -> PostResult:
    """Post a video to TikTok from a public URL.

    Args:
        title: Post title (logging only)
        video_url: Public URL to the video file
        description: Post caption text
        hashtags: Optional hashtags
    """
    global _last_post_time

    if not is_tiktok_configured():
        return PostResult(success=False, error="TikTok API not configured")

    if not _check_rate_limit():
        return PostResult(success=False, error="Rate limited")

    caption = description
    if hashtags:
        caption += "\n\n" + " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)

    try:
        import httpx

        init_resp = httpx.post(
            f"{_API_BASE}/post/publish/video/init/",
            headers=_get_headers(),
            json={
                "post_info": {
                    "title": caption[:2200],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_comment": False,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": video_url,
                },
                "post_mode": "DIRECT_POST",
                "media_type": "VIDEO",
            },
            timeout=30.0,
        )

        _last_post_time = time.monotonic()

        if init_resp.status_code == 200:
            data = init_resp.json()
            if data.get("error", {}).get("code") == "ok":
                publish_id = data.get("data", {}).get("publish_id", "")
                logger.info("TikTok video posted: %s (id=%s)", title[:50], publish_id)
                return PostResult(success=True, post_id=publish_id, data=data)
            else:
                error_msg = data.get("error", {}).get("message", "Unknown error")
                return PostResult(success=False, error=error_msg)

        return PostResult(success=False, error=f"HTTP {init_resp.status_code}")

    except ImportError:
        return PostResult(success=False, error="httpx not installed")
    except Exception as e:
        logger.exception("TikTok video post failed")
        return PostResult(success=False, error=str(e))


def generate_carousel_from_text(text: str, conn=None) -> list[str] | None:
    """Generate carousel slide images from text content via asset generator.

    Converts a tweet/tip into 3-5 educational carousel slides in the
    Civic Sanctuary aesthetic (watercolor, Mediterranean tones).

    Returns list of image URLs (hosted on app's static assets) or None on failure.
    """
    try:
        from ..ai.ollama_client import generate as llm_generate

        # Use LLM to break text into slide content
        resp = llm_generate(
            prompt=(
                f"Break this educational content into 3-5 carousel slides for TikTok/Instagram. "
                f"Each slide should have a short headline (max 8 words) and 1-2 lines of body text. "
                f"Respond with JSON: {{\"slides\": [{{\"headline\": \"...\", \"body\": \"...\"}}]}}\n\n"
                f"Content:\n{text}"
            ),
            system="You create social media carousel slides. Keep text short and impactful.",
            temperature=0.5,
            max_tokens=512,
            conn=conn,
            task_type="reading_generation",
        )

        if not resp.success:
            return None

        import json
        try:
            data = json.loads(resp.text.strip())
            slides = data.get("slides", [])
            if not slides:
                return None

            # Generate slide images via asset generator
            from ..ai.asset_generator import generate_carousel_slides
            image_urls = generate_carousel_slides(slides)
            return image_urls if image_urls else None

        except (json.JSONDecodeError, ImportError):
            return None

    except (ImportError, Exception) as e:
        logger.debug("Carousel generation failed: %s", e)
        return None
