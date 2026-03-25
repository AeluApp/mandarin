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

# HSK 4-5 produce medium-complexity passages that need more output tokens than
# low HSK (short) or high HSK (cached from prior runs).  Scale token budget by
# level so Qwen doesn't truncate mid-JSON.
_MAX_TOKENS_BY_HSK = {
    1: 2048, 2: 2048, 3: 2048,
    4: 4096, 5: 4096,
    6: 4096, 7: 4096, 8: 4096, 9: 4096,
}

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
) -> dict | None:
    """Generate a graded reading passage. Returns passage dict or None."""
    if not is_ollama_available():
        return None

    prompt = _build_reading_prompt(
        target_hsk_level, target_vocabulary or [], topic, length_characters, content_lens,
    )

    max_tokens = _MAX_TOKENS_BY_HSK.get(target_hsk_level, 4096)

    response = generate(
        prompt=prompt,
        system=READING_CONTENT_SYSTEM,
        temperature=0.8,
        max_tokens=max_tokens,
        use_cache=True,
        conn=conn,
        task_type="reading_generation",
    )

    if not response.success:
        return None

    passage = _parse_passage_response(response.text)

    # Retry once with higher token budget + lower temperature on parse failure
    if passage is None and max_tokens < 6144:
        logger.info("Reading passage parse failed for HSK %d, retrying with more tokens", target_hsk_level)
        response = generate(
            prompt=prompt + "\n\nIMPORTANT: Output complete, valid JSON. Close all brackets.",
            system=READING_CONTENT_SYSTEM,
            temperature=0.6,
            max_tokens=6144,
            use_cache=False,  # Don't use the cached truncated response
            conn=conn,
            task_type="reading_generation_retry",
        )
        if response.success:
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

    # Constrain output size to reduce truncation risk at mid-levels
    if hsk_level <= 3:
        parts.append("Include 5-8 vocabulary items and 2-3 comprehension questions.")
    elif hsk_level <= 5:
        parts.append("Include 6-10 vocabulary items and 2-3 comprehension questions.")
        parts.append("Keep vocabulary entries concise — one-line English translations.")
    else:
        parts.append("Include 8-12 vocabulary items and 3-4 comprehension questions.")

    if vocabulary:
        parts.append(f"Include these words: {', '.join(vocabulary)}")
    if topic:
        parts.append(f"Topic: {topic}")
    if content_lens:
        parts.append(f"Content approach: {content_lens}")
    parts.append("Output JSON only, no markdown fences. Ensure all brackets and braces are closed.")
    return "\n".join(parts)


def _repair_json(text: str) -> str:
    """Best-effort repair of common LLM JSON mistakes."""
    # Missing commas between string array elements
    text = re.sub(r'"\s*\n(\s*")', r'",\n\1', text)
    # Missing commas between object/array elements
    text = re.sub(r'(\})\s*\n(\s*\{)', r'\1,\n\2', text)
    text = re.sub(r'(\])\s*\n(\s*\[)', r'\1,\n\2', text)
    # Missing comma after number before key
    text = re.sub(r'(\d)\s*\n(\s*")', r'\1,\n\2', text)
    # Trailing commas before closing brackets
    text = re.sub(r',\s*(\])', r'\1', text)
    text = re.sub(r',\s*(\})', r'\1', text)
    # Single quotes → double quotes (best effort)
    if "'" in text and '"' not in text[:20]:
        text = text.replace("'", '"')
    return text


def _recover_truncated_json(text: str) -> str | None:
    """Attempt to close truncated JSON by balancing brackets/braces.

    Works for the common case where Qwen output is cut mid-value or
    mid-array.  Strips back to the last complete value, then closes
    all open delimiters.
    """
    # Strip trailing partial string value (cut mid-word)
    text = re.sub(r',\s*"[^"]*$', '', text)       # trailing key with no value
    text = re.sub(r':\s*"[^"]*$', ': ""', text)    # key: "partial  → key: ""
    text = re.sub(r',\s*$', '', text)               # trailing comma

    # Count unmatched delimiters
    opens = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            opens.append(ch)
        elif ch == '}' and opens and opens[-1] == '{':
            opens.pop()
        elif ch == ']' and opens and opens[-1] == '[':
            opens.pop()

    if not opens:
        return text  # Already balanced

    # Close in reverse order
    closers = {'[': ']', '{': '}'}
    suffix = ''.join(closers[o] for o in reversed(opens))
    return text + suffix


def _parse_passage_response(content: str) -> dict | None:
    """Parse JSON from LLM response with repair and truncation recovery."""
    text = content.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    # Attempt 1: direct parse
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Attempt 2: lightweight repair
        try:
            data = json.loads(_repair_json(text))
        except (json.JSONDecodeError, ValueError):
            # Attempt 3: truncation recovery
            recovered = _recover_truncated_json(_repair_json(text))
            if recovered:
                try:
                    data = json.loads(recovered)
                    logger.info("Recovered truncated reading passage JSON")
                except (json.JSONDecodeError, ValueError):
                    logger.warning("Failed to parse reading response as JSON (even after repair): %s", text[:200])
                    return None
            else:
                logger.warning("Failed to parse reading response as JSON: %s", text[:200])
                return None

    for field in ("title", "body", "pinyin_body"):
        if not data.get(field):
            logger.warning("Reading response missing required field: %s", field)
            return None

    return data


def _persist_reading_passage(conn, passage: dict, hsk_level: int, content_lens: str) -> None:
    """Persist passage to reading_texts table and reading_passages.json."""
    passage["source"] = "ai_generated"
    passage["hsk_level"] = hsk_level
    if content_lens:
        passage["content_lens"] = content_lens

    # Primary: insert into reading_texts table (what the analyzer checks)
    try:
        title = passage.get("title", "")
        body = passage.get("body", "")
        pinyin = passage.get("pinyin_body", "")
        word_count = len(body)

        conn.execute("""
            INSERT INTO reading_texts
            (title, content_hanzi, content_pinyin, word_count, hsk_ceiling,
             source, approved, approved_at)
            VALUES (?, ?, ?, ?, ?, 'ai_generated', 0, NULL)
        """, (title, body, pinyin, word_count, hsk_level))
        conn.commit()
    except Exception:
        logger.debug("Failed to persist reading passage to DB", exc_info=True)

    # Secondary: append to flat file (backward compat)
    try:
        data = {"passages": []}
        if _READING_PASSAGES_PATH.exists():
            with open(_READING_PASSAGES_PATH, encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    data = raw
                    if "passages" not in data:
                        data["passages"] = []
                elif isinstance(raw, list):
                    data = {"passages": raw}

        data["passages"].append(passage)

        with open(_READING_PASSAGES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.debug("Failed to persist reading passage to JSON", exc_info=True)


# ── Vocabulary Profile (Nation 2006, Krashen i+1) ──────────────────

def compute_vocabulary_profile(passage_text: str, known_hanzi: set) -> dict:
    """Compute Nation's vocabulary coverage profile for a passage.

    Uses jieba word segmentation for token-level (not character-level) analysis.
    Nation (2006): 95-98% coverage for unassisted reading, 90-95% with glossing.
    Aelu has glossing → target 90-95%.

    Returns:
        token_coverage: float (0-1) — % of running tokens that are known
        unique_coverage: float (0-1) — % of unique word types that are known
        new_word_count: int — number of unique unknown words
        new_word_density: float — unknown words per 20 tokens
        verdict: 'too_easy' | 'optimal' | 'challenging' | 'too_hard'
    """
    try:
        import jieba
    except ImportError:
        # Fallback to character-level if jieba unavailable
        chars = [c for c in passage_text if '\u4e00' <= c <= '\u9fff']
        if not chars:
            return {"token_coverage": 1.0, "unique_coverage": 1.0,
                    "new_word_count": 0, "new_word_density": 0.0, "verdict": "too_easy"}
        known = sum(1 for c in chars if c in known_hanzi)
        cov = known / len(chars)
        unique = set(chars)
        unique_known = sum(1 for c in unique if c in known_hanzi)
        verdict = "too_easy" if cov > 0.98 else "optimal" if cov >= 0.90 else "challenging" if cov >= 0.85 else "too_hard"
        return {"token_coverage": round(cov, 3), "unique_coverage": round(unique_known / len(unique), 3) if unique else 1.0,
                "new_word_count": len(unique) - unique_known, "new_word_density": 0.0, "verdict": verdict}

    tokens = list(jieba.cut(passage_text))
    # Filter to tokens containing at least one CJK character
    meaningful = [t for t in tokens if any('\u4e00' <= c <= '\u9fff' for c in t)]

    if not meaningful:
        return {"token_coverage": 1.0, "unique_coverage": 1.0,
                "new_word_count": 0, "new_word_density": 0.0, "verdict": "too_easy"}

    # A word is "known" if ALL its characters are in the known set
    known_count = sum(1 for t in meaningful if all(c in known_hanzi for c in t if '\u4e00' <= c <= '\u9fff'))
    coverage = known_count / len(meaningful)

    unique_tokens = set(meaningful)
    unique_known = sum(1 for t in unique_tokens if all(c in known_hanzi for c in t if '\u4e00' <= c <= '\u9fff'))
    unique_coverage = unique_known / len(unique_tokens) if unique_tokens else 1.0

    new_words = len(unique_tokens) - unique_known
    # Nation's threshold: max 1 new word per 20 running tokens
    density = new_words / max(1, len(meaningful) / 20)

    if coverage > 0.98:
        verdict = "too_easy"
    elif coverage >= 0.90:
        verdict = "optimal"      # Nation's 90-95% with glossing support
    elif coverage >= 0.85:
        verdict = "challenging"  # Acceptable with heavy glossing
    else:
        verdict = "too_hard"

    return {
        "token_coverage": round(coverage, 3),
        "unique_coverage": round(unique_coverage, 3),
        "new_word_count": new_words,
        "new_word_density": round(density, 2),
        "verdict": verdict,
    }
