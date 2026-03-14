"""Encounter→drill conversion via local LLM."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .ollama_client import generate, is_ollama_available, OllamaResponse
from .validation import validate_generated_content

logger = logging.getLogger(__name__)

DRILL_GENERATION_SYSTEM = """You are a Mandarin Chinese teaching assistant. Generate drill items for a spaced repetition system.

Output ONLY valid JSON with these fields:
- hanzi: simplified Chinese characters
- pinyin: with tone marks (e.g. nǐ hǎo)
- english: concise English translation
- drill_type: one of "mcq", "fill_blank", "translate_to_chinese", "translate_to_english"
- example_sentence_hanzi: a natural example sentence using the target word
- example_sentence_pinyin: pinyin for the example sentence
- example_sentence_english: English translation of the example sentence
- distractors: array of 3 plausible wrong answers (for mcq type)
- hsk_level: estimated HSK level (1-9)
- confidence: your confidence score 0.0-1.0

Use simplified characters only. Pinyin must have tone marks. Distractors must be plausible but clearly wrong."""


@dataclass
class GeneratedDrillItem:
    hanzi: str
    pinyin: str
    english: str
    drill_type: str
    example_sentence_hanzi: str = ""
    example_sentence_pinyin: str = ""
    example_sentence_english: str = ""
    distractors: list = None
    hsk_level: int = 1
    confidence: float = 0.0
    encounter_id: str = ""

    def __post_init__(self):
        if self.distractors is None:
            self.distractors = []


def generate_drill_from_encounter(
    conn, encounter_id: str, target_word: str,
    source_sentence: str = "", learner_hsk_level: int = 1,
    language_notes: str = "",
) -> Optional[GeneratedDrillItem]:
    """Generate a drill item from a vocab encounter. Returns None on failure."""
    prompt = _build_drill_prompt(target_word, source_sentence, learner_hsk_level, language_notes)

    response = generate(
        prompt=prompt,
        system=DRILL_GENERATION_SYSTEM,
        temperature=0.6,
        use_cache=True,
        conn=conn,
        task_type="drill_generation",
    )

    if not response.success:
        _mark_encounter_failed(conn, encounter_id, response.error or "generation_failed")
        return None

    item = _parse_drill_response(response.text, encounter_id)
    if item is None:
        _mark_encounter_failed(conn, encounter_id, "parse_failed")
        return None

    # Validate
    content = validate_generated_content("drill", {
        "hanzi": item.hanzi, "pinyin": item.pinyin, "english": item.english,
        "drill_type": item.drill_type, "distractors": item.distractors,
    })

    validation_issues = _validate_drill_item(item, target_word, learner_hsk_level)
    content["validation_issues"].extend(validation_issues)

    if content["validation_issues"]:
        # Route to review queue instead of direct insertion
        _enqueue_for_review(conn, item, content["validation_issues"], encounter_id)
        _mark_encounter_failed(conn, encounter_id, "needs_review")
        return item

    # Persist directly
    item_id = _persist_drill_item(conn, item)
    _mark_encounter_generated(conn, encounter_id, item_id)
    return item


def _build_drill_prompt(
    target_word: str, source_sentence: str, hsk_level: int, language_notes: str,
) -> str:
    parts = [f"Create a drill item for the word: {target_word}"]
    parts.append(f"Learner HSK level: {hsk_level}")
    if source_sentence:
        parts.append(f"Original context: {source_sentence}")
    if language_notes:
        parts.append(f"Notes: {language_notes}")
    parts.append("Output JSON only, no markdown fences or explanation.")
    return "\n".join(parts)


def _parse_drill_response(content: str, encounter_id: str) -> Optional[GeneratedDrillItem]:
    """Parse JSON from LLM response. Strips markdown fences if present."""
    text = content.strip()
    # Strip markdown code fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse drill response as JSON: %s", text[:200])
        return None

    # Check required fields
    for field in ("hanzi", "pinyin", "english"):
        if not data.get(field):
            logger.warning("Drill response missing required field: %s", field)
            return None

    return GeneratedDrillItem(
        hanzi=data["hanzi"],
        pinyin=data["pinyin"],
        english=data["english"],
        drill_type=data.get("drill_type", "mcq"),
        example_sentence_hanzi=data.get("example_sentence_hanzi", ""),
        example_sentence_pinyin=data.get("example_sentence_pinyin", ""),
        example_sentence_english=data.get("example_sentence_english", ""),
        distractors=data.get("distractors", []),
        hsk_level=int(data.get("hsk_level", 1)),
        confidence=float(data.get("confidence", 0.0)),
        encounter_id=encounter_id,
    )


def _validate_drill_item(item: GeneratedDrillItem, target_word: str, hsk_level: int) -> list[str]:
    """Additional validation beyond basic field checks. Returns list of issues."""
    issues = []

    # Target word should appear in example sentence
    if item.example_sentence_hanzi and target_word not in item.example_sentence_hanzi:
        issues.append(f"target word '{target_word}' not in example sentence")

    # Low confidence flag
    if item.confidence < 0.80:
        issues.append(f"low confidence: {item.confidence:.2f}")

    # HSK level sanity check
    if item.hsk_level > hsk_level + 2:
        issues.append(f"generated HSK {item.hsk_level} too high for learner level {hsk_level}")

    return issues


def _persist_drill_item(conn, item: GeneratedDrillItem) -> str:
    """INSERT into content_item with source='ai_generated'.

    Sets review_status='pending_review' so AI-generated items must be
    approved before being served to users. Returns item id.
    """
    item_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO content_item
           (id, hanzi, pinyin, english, hsk_level, status, source,
            example_sentence_hanzi, example_sentence_pinyin, example_sentence_english,
            review_status)
           VALUES (?, ?, ?, ?, ?, 'drill_ready', 'ai_generated', ?, ?, ?,
                   'pending_review')""",
        (item_id, item.hanzi, item.pinyin, item.english, item.hsk_level,
         item.example_sentence_hanzi, item.example_sentence_pinyin,
         item.example_sentence_english),
    )
    conn.commit()
    return item_id


def _mark_encounter_generated(conn, encounter_id: str, item_id: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE vocab_encounter
           SET drill_generation_status = 'generated', generated_item_id = ?,
               generation_attempted_at = ?
           WHERE id = ?""",
        (item_id, now, encounter_id),
    )
    conn.commit()


def _mark_encounter_failed(conn, encounter_id: str, error: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE vocab_encounter
           SET drill_generation_status = 'failed', generation_error = ?,
               generation_attempted_at = ?
           WHERE id = ?""",
        (error[:500], now, encounter_id),
    )
    conn.commit()


def _enqueue_for_review(conn, item: GeneratedDrillItem, issues: list[str], encounter_id: str) -> None:
    """Add item to pi_ai_review_queue for human review."""
    content_json = json.dumps({
        "hanzi": item.hanzi, "pinyin": item.pinyin, "english": item.english,
        "drill_type": item.drill_type, "distractors": item.distractors,
        "hsk_level": item.hsk_level, "example_sentence_hanzi": item.example_sentence_hanzi,
        "example_sentence_pinyin": item.example_sentence_pinyin,
        "example_sentence_english": item.example_sentence_english,
    }, ensure_ascii=False)
    conn.execute(
        """INSERT INTO pi_ai_review_queue
           (id, content_type, content_json, validation_issues, encounter_id)
           VALUES (?, 'drill', ?, ?, ?)""",
        (str(uuid.uuid4()), content_json, json.dumps(issues), encounter_id),
    )
    conn.commit()


def process_pending_encounters(conn, max_batch: int = 20) -> dict:
    """Batch-process pending vocab encounters into drill items."""
    if not is_ollama_available():
        return {"processed": 0, "skipped_reason": "ollama_unavailable"}

    rows = conn.execute(
        """SELECT id, hanzi, content_item_id
           FROM vocab_encounter
           WHERE drill_generation_status = 'pending' AND hanzi IS NOT NULL
           ORDER BY created_at ASC
           LIMIT ?""",
        (max_batch,),
    ).fetchall()

    results = {"processed": 0, "generated": 0, "failed": 0, "review": 0}

    for row in rows:
        results["processed"] += 1
        try:
            # Get learner HSK level
            profile = conn.execute(
                "SELECT level_reading FROM learner_profile LIMIT 1"
            ).fetchone()
            hsk = int(profile["level_reading"]) if profile else 1

            item = generate_drill_from_encounter(
                conn, encounter_id=row["id"],
                target_word=row["hanzi"],
                learner_hsk_level=hsk,
            )
            if item:
                results["generated"] += 1
            else:
                results["failed"] += 1
        except Exception as e:
            logger.warning("Encounter processing failed for %s: %s", row["id"], e)
            _mark_encounter_failed(conn, row["id"], str(e)[:500])
            results["failed"] += 1

    return results
