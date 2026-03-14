"""Graded reading passage generation via local LLM."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from .ollama_client import generate, is_ollama_available
from .validation import validate_generated_content

logger = logging.getLogger(__name__)

READING_CONTENT_SYSTEM = """You are a skilled Mandarin Chinese content writer. Generate a graded reading passage.

Output ONLY valid JSON with these fields:
- title: passage title in Chinese (simplified)
- title_pinyin: pinyin with tone marks
- title_english: English translation of title
- body: the passage in simplified Chinese characters
- pinyin_body: full pinyin with tone marks for the body
- english_body: English translation of the body
- vocabulary: array of {hanzi, pinyin, english} for key words
- comprehension_questions: array of {question, answer} in Chinese
- estimated_hsk_level: integer 1-9

Use simplified characters only. Write naturally — avoid textbook smell (教材味).
Keep sentences short and clear for the target HSK level.
Include 分寸 — disciplined aptness, not flashiness."""

_READING_PASSAGES_PATH = Path(__file__).parent.parent.parent / "data" / "reading_passages.json"


def generate_reading_passage(
    conn,
    target_hsk_level: int = 2,
    target_vocabulary: list[str] = None,
    topic: str = "",
    length_characters: int = 200,
    content_lens: str = "",
) -> Optional[dict]:
    """Generate a graded reading passage. Returns passage dict or None."""
    if not is_ollama_available():
        return None

    prompt = _build_reading_prompt(
        target_hsk_level, target_vocabulary or [], topic, length_characters, content_lens,
    )

    response = generate(
        prompt=prompt,
        system=READING_CONTENT_SYSTEM,
        temperature=0.8,
        max_tokens=2048,
        use_cache=True,
        conn=conn,
        task_type="reading_generation",
    )

    if not response.success:
        return None

    passage = _parse_passage_response(response.text)
    if passage is None:
        return None

    # Validate
    validated = validate_generated_content("reading", passage)
    if validated["validation_issues"]:
        logger.warning("Reading passage validation issues: %s", validated["validation_issues"])
        return None

    _persist_reading_passage(conn, passage, target_hsk_level, content_lens)
    return passage


def _build_reading_prompt(
    hsk_level: int, vocabulary: list[str], topic: str,
    length: int, content_lens: str,
) -> str:
    parts = [f"Generate a reading passage for HSK level {hsk_level}."]
    parts.append(f"Target length: approximately {length} characters.")
    if vocabulary:
        parts.append(f"Include these words: {', '.join(vocabulary)}")
    if topic:
        parts.append(f"Topic: {topic}")
    if content_lens:
        parts.append(f"Content approach: {content_lens}")
    parts.append("Output JSON only, no markdown fences.")
    return "\n".join(parts)


def _parse_passage_response(content: str) -> Optional[dict]:
    """Parse JSON from LLM response."""
    text = content.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse reading response as JSON: %s", text[:200])
        return None

    for field in ("title", "body", "pinyin_body"):
        if not data.get(field):
            logger.warning("Reading response missing required field: %s", field)
            return None

    return data


def _persist_reading_passage(conn, passage: dict, hsk_level: int, content_lens: str) -> None:
    """Append passage to reading_passages.json (existing flat-file pattern)."""
    try:
        passages = []
        if _READING_PASSAGES_PATH.exists():
            with open(_READING_PASSAGES_PATH, "r", encoding="utf-8") as f:
                passages = json.load(f)

        passage["source"] = "ai_generated"
        passage["hsk_level"] = hsk_level
        if content_lens:
            passage["content_lens"] = content_lens
        passages.append(passage)

        with open(_READING_PASSAGES_PATH, "w", encoding="utf-8") as f:
            json.dump(passages, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.debug("Failed to persist reading passage", exc_info=True)
