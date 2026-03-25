"""Xiaohongshu (小红书) content generation — bilingual post drafts.

XHS has no public API for foreign developers, so this module generates
ready-to-paste bilingual content rather than auto-posting. Posts are
queued in the marketing_approval_queue with platform='xhs' for review.

XHS content style:
- Bilingual (Chinese + English) — the audience is Chinese learners AND
  Chinese speakers interested in language education
- Image-heavy (carousel format dominates XHS)
- Personal, journaling tone (fits the anonymous builder persona)
- Heavy use of emoji and line breaks (XHS convention)
- Hashtags in Chinese: #学中文 #HSK #汉语学习

Exports:
    generate_xhs_post(conn, source_text, content_id) -> int | None  # queue ID
    get_xhs_hashtags() -> list[str]
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

# XHS-relevant Chinese hashtags for Mandarin learning content
_XHS_HASHTAGS = [
    "#学中文", "#HSK", "#汉语学习", "#中文学习", "#学习打卡",
    "#外国人学中文", "#中文", "#普通话", "#语言学习", "#学习方法",
]


def get_xhs_hashtags() -> list[str]:
    return _XHS_HASHTAGS


def generate_xhs_post(conn, source_text: str, content_id: str = "") -> int | None:
    """Generate a bilingual XHS post from English source content.

    Uses cloud LLM to translate and adapt the content for XHS format:
    - Chinese text first, English below
    - XHS-native formatting (emoji, line breaks, hashtags)
    - Educational and personal tone

    Returns the approval queue ID, or None on failure.
    """
    try:
        from ..ai.ollama_client import generate as llm_generate
    except ImportError:
        return None

    resp = llm_generate(
        prompt=(
            f"Adapt this English educational content about learning Mandarin into a "
            f"Xiaohongshu (小红书) post. Format:\n\n"
            f"1. Chinese version first (simplified, natural tone, with emoji)\n"
            f"2. Then '---' separator\n"
            f"3. English version below\n"
            f"4. End with Chinese hashtags\n\n"
            f"XHS style: personal, journaling tone. Use line breaks between points. "
            f"Add relevant emoji. Keep it warm and educational, not salesy.\n\n"
            f"Source content:\n{source_text[:1500]}\n\n"
            f"Respond with JSON: {{\"chinese\": \"...\", \"english\": \"...\", \"hashtags\": [\"#学中文\", ...]}}"
        ),
        system=(
            "You write bilingual Chinese/English educational social media content. "
            "Your tone is warm, personal, and educational — like a friend sharing study tips. "
            "Never reveal the author's name or identity. First-person 'I' is fine."
        ),
        temperature=0.6,
        max_tokens=1024,
        conn=conn,
        task_type="reading_generation",
    )

    if not resp.success:
        logger.warning("XHS content generation failed: %s", resp.error)
        return None

    try:
        # Parse the response
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json.loads(text)
        chinese = data.get("chinese", "")
        english = data.get("english", "")
        hashtags = data.get("hashtags", _XHS_HASHTAGS[:5])

        if not chinese:
            return None

        # Compose the full XHS post
        xhs_post = f"{chinese}\n\n---\n\n{english}\n\n{' '.join(hashtags)}"

        # Run identity guard
        from .anonymity_guard import check_identity
        identity_check = check_identity(xhs_post, conn=conn)
        if not identity_check.passed:
            logger.warning("XHS post blocked by identity guard")
            return None

        # Queue for manual posting (XHS has no API)
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.execute("""
            INSERT INTO marketing_approval_queue
                (content_id, platform, content_text, reason, status, submitted_at)
            VALUES (?, 'xhs', ?, 'XHS requires manual posting — copy and paste to app', 'pending', ?)
        """, (content_id, xhs_post, now))
        conn.commit()

        queue_id = cursor.lastrowid
        logger.info("XHS post queued (queue_id=%d) for manual posting", queue_id)
        return queue_id

    except (json.JSONDecodeError, KeyError) as e:
        logger.debug("XHS content parse failed: %s", e)
        return None
