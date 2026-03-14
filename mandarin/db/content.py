"""Content item queries — insert, query, context notes."""

import json
import logging
import os
import sqlite3
from datetime import date
from typing import List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")


def _load_json(filename):
    try:
        with open(os.path.join(_DATA_DIR, filename)) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load content data file %s: %s", filename, e)
        raise


_VALID_ITEM_TYPES = {"vocab", "sentence", "phrase", "chunk", "grammar"}
_VALID_REGISTERS = {"casual", "neutral", "professional", "mixed"}
_VALID_STATUSES = {"drill_ready", "raw", "retired"}
_VALID_REVIEW_STATUSES = {"approved", "pending_review", "rejected"}


def insert_content_item(conn: sqlite3.Connection, *,
                        hanzi: str, pinyin: str, english: str,
                        item_type: str = "vocab", hsk_level: int = None,
                        register: str = "neutral", content_lens: str = None,
                        source: str = None, source_context: str = None,
                        difficulty: float = 0.5, tags: list = None,
                        status: str = "drill_ready",
                        review_status: str = "approved") -> int:
    """Insert a content item. Returns the new row ID.

    Validates inputs before insertion — raises ValueError on bad data.
    AI-generated items should pass review_status='pending_review'.
    """
    if not hanzi or not hanzi.strip():
        raise ValueError("hanzi must be non-empty")
    if item_type not in _VALID_ITEM_TYPES:
        raise ValueError(f"invalid item_type: {item_type!r}")
    if register not in _VALID_REGISTERS:
        raise ValueError(f"invalid register: {register!r}")
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    if review_status not in _VALID_REVIEW_STATUSES:
        raise ValueError(f"invalid review_status: {review_status!r}")
    if hsk_level is not None and not (1 <= hsk_level <= 9):
        raise ValueError(f"hsk_level must be 1-9, got {hsk_level}")
    cur = conn.execute("""
        INSERT INTO content_item
            (hanzi, pinyin, english, item_type, hsk_level, register,
             content_lens, source, source_context, difficulty, tags, status,
             review_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (hanzi, pinyin, english, item_type, hsk_level, register,
          content_lens, source, source_context, difficulty,
          json.dumps(tags or []), status, review_status))
    return cur.lastrowid


def seed_context_notes(conn: sqlite3.Connection, notes_dict: dict) -> int:
    """Populate context_note on content_items from a {hanzi: note} dict.
    Returns count of items updated."""
    updated = 0
    for hanzi, note in notes_dict.items():
        cur = conn.execute(
            "UPDATE content_item SET context_note = ? WHERE hanzi = ? AND context_note IS NULL",
            (note, hanzi))
        updated += cur.rowcount
    conn.commit()
    return updated


_VALID_MODALITIES = {"reading", "listening", "speaking", "ime"}


def _filter_unreviewed_ai_content(items: List[dict]) -> List[dict]:
    """NIST AI RMF: skip AI-generated content that hasn't been human-reviewed.

    If is_ai_generated=1 and human_reviewed_at is NULL, the item is excluded
    and a warning is logged. This is a soft gate — does not require schema
    changes to human_reviewed_at NOT NULL.
    """
    filtered = []
    for item in items:
        if item.get("is_ai_generated") and not item.get("human_reviewed_at"):
            logger.warning(
                "NIST-AI: skipping unreviewed AI content item %s (hanzi=%s, prompt=%s)",
                item.get("id"), item.get("hanzi"), item.get("generated_by_prompt"),
            )
            continue
        filtered.append(item)
    return filtered


def get_items_due(conn: sqlite3.Connection, modality: str,
                  limit: int = 20, today: str = None,
                  user_id: int = 1) -> List[dict]:
    """Get content items due for review in a given modality.

    Only returns drill_ready items. Uses half-life retention model
    to prioritize items with lowest predicted recall probability.
    Falls back to next_review_date ordering if half_life not available.

    NIST AI RMF: AI-generated content without human review is excluded.
    """
    today = today or date.today().isoformat()
    rows = conn.execute("""
        SELECT ci.*, p.ease_factor, p.interval_days, p.repetitions,
               p.next_review_date, p.total_attempts, p.total_correct,
               p.streak_correct, p.half_life_days, p.difficulty AS item_difficulty,
               p.last_review_date, p.mastery_stage
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.modality = ? AND p.user_id = ?
        WHERE ci.is_mined_out = 0
          AND ci.status = 'drill_ready'
          AND ci.review_status = 'approved'
          AND (ci.is_ai_generated = 0 OR ci.human_reviewed_at IS NOT NULL)
          AND (p.next_review_date IS NULL OR p.next_review_date <= ?)
          AND (p.suspended_until IS NULL OR p.suspended_until <= ?)
        ORDER BY
            CASE WHEN p.next_review_date IS NULL THEN 0 ELSE 1 END,
            -- Prioritize by lowest predicted recall (most urgent)
            CASE WHEN p.half_life_days IS NOT NULL AND p.last_review_date IS NOT NULL
                 THEN p.half_life_days / MAX(1, julianday(?) - julianday(p.last_review_date))
                 ELSE 999 END ASC,
            p.next_review_date ASC,
            ci.difficulty ASC
        LIMIT ?
    """, (modality, user_id, today, today, today, limit)).fetchall()
    items = [dict(r) for r in rows]
    return _filter_unreviewed_ai_content(items)


def get_new_items(conn: sqlite3.Connection, modality: str,
                  limit: int = 5, hsk_max: int = 9,
                  user_id: int = 1) -> List[dict]:
    """Get content items never reviewed in a given modality.

    Only returns drill_ready items.

    NIST AI RMF: AI-generated content without human review is excluded.
    """
    if modality not in _VALID_MODALITIES:
        raise ValueError(f"Invalid modality: {modality!r}")
    suitable_col = f"suitable_for_{modality}"
    rows = conn.execute(f"""
        SELECT ci.*
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.modality = ? AND p.user_id = ?
        WHERE p.id IS NULL
          AND ci.is_mined_out = 0
          AND ci.status = 'drill_ready'
          AND ci.review_status = 'approved'
          AND (ci.is_ai_generated = 0 OR ci.human_reviewed_at IS NOT NULL)
          AND ci.{suitable_col} = 1
          AND (ci.hsk_level IS NULL OR ci.hsk_level <= ?)
        ORDER BY ci.hsk_level ASC, ci.difficulty ASC
        LIMIT ?
    """, (modality, user_id, hsk_max, limit)).fetchall()
    items = [dict(r) for r in rows]
    return _filter_unreviewed_ai_content(items)


def content_count(conn: sqlite3.Connection) -> int:
    """Total content items."""
    row = conn.execute("SELECT COUNT(*) FROM content_item").fetchone()
    return row[0] if row else 0



# ── Construction seed data ──

_CONSTRUCTIONS_CACHE = None


def _get_constructions():
    global _CONSTRUCTIONS_CACHE
    if _CONSTRUCTIONS_CACHE is None:
        _CONSTRUCTIONS_CACHE = _load_json("constructions.json")
    return _CONSTRUCTIONS_CACHE


def seed_constructions(conn: sqlite3.Connection) -> int:
    """Seed construction table and link to content items by hanzi match.

    Idempotent — skips existing constructions.
    Returns count of new constructions inserted.
    """
    inserted = 0
    for c in _get_constructions():
        existing = conn.execute(
            "SELECT id FROM construction WHERE name = ?", (c["name"],)
        ).fetchone()
        if existing:
            cid = existing[0]
        else:
            cur = conn.execute("""
                INSERT INTO construction (name, pattern_zh, description, hsk_level, category)
                VALUES (?, ?, ?, ?, ?)
            """, (c["name"], c["pattern_zh"], c["description"], c["hsk_level"], c["category"]))
            cid = cur.lastrowid
            inserted += 1

        # Link to content items matching any hanzi in hanzi_tags
        for hanzi in c.get("hanzi_tags", []):
            items = conn.execute(
                "SELECT id FROM content_item WHERE hanzi = ?", (hanzi,)
            ).fetchall()
            for item in items:
                conn.execute("""
                    INSERT OR IGNORE INTO content_construction (content_item_id, construction_id)
                    VALUES (?, ?)
                """, (item[0], cid))

    conn.commit()
    return inserted
