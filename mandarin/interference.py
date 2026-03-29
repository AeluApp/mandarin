"""Interference-aware scheduling — detect and manage confusable pairs.

Based on Bjork's LECTOR principle: space confusables apart when learning,
interleave them deliberately once mastery is established.

Confusable categories for Mandarin:
- Tone pairs: same pinyin, different tone (妈 mā / 马 mǎ)
- Homophones: same pronunciation, different character (是 shì / 事 shì)
- Visual confusables: similar-looking characters (人 rén / 入 rù)
- Semantic confusables: related meanings easily mixed up
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Mastery stages where interleaving is beneficial (desirable difficulty)
_INTERLEAVE_STAGES = frozenset({"stable", "durable"})

# Mastery stages where spacing apart is needed (avoid interference)
_SPACE_APART_STAGES = frozenset({"seen", "passed_once", "stabilizing", "decayed"})

# Tone diacritics mapped to their tone number and stripped form
_TONE_MARKS = {
    "ā": ("a", 1), "á": ("a", 2), "ǎ": ("a", 3), "à": ("a", 4),
    "ē": ("e", 1), "é": ("e", 2), "ě": ("e", 3), "è": ("e", 4),
    "ī": ("i", 1), "í": ("i", 2), "ǐ": ("i", 3), "ì": ("i", 4),
    "ō": ("o", 1), "ó": ("o", 2), "ǒ": ("o", 3), "ò": ("o", 4),
    "ū": ("u", 1), "ú": ("u", 2), "ǔ": ("u", 3), "ù": ("u", 4),
    "ǖ": ("ü", 1), "ǘ": ("ü", 2), "ǚ": ("ü", 3), "ǜ": ("ü", 4),
}


def _strip_tones(pinyin: str) -> str:
    """Strip tone diacritics from pinyin, returning the toneless base.

    Example: 'māo' -> 'mao', 'nǚ' -> 'nü'
    """
    result = []
    for ch in pinyin.lower():
        if ch in _TONE_MARKS:
            result.append(_TONE_MARKS[ch][0])
        else:
            result.append(ch)
    return "".join(result)


def _normalize_pinyin(pinyin: str) -> str:
    """Normalize pinyin for comparison: lowercase, strip spaces/numbers."""
    return re.sub(r"[0-9\s]+", "", pinyin.lower().strip())


def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create confusable_pair and interference_event tables if missing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS confusable_pair (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_a_id INTEGER NOT NULL,
            item_b_id INTEGER NOT NULL,
            confusable_type TEXT NOT NULL,
            similarity_score REAL DEFAULT 0.5,
            detected_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_a_id, item_b_id, confusable_type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interference_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            confused_item_id INTEGER NOT NULL,
            intended_item_id INTEGER NOT NULL,
            recorded_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_confusable_pair_a
            ON confusable_pair(item_a_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_confusable_pair_b
            ON confusable_pair(item_b_id)
    """)


def detect_confusables(conn: sqlite3.Connection, limit: int = 500) -> int:
    """Scan content items and detect confusable pairs.

    Returns number of new pairs detected.
    Stores in confusable_pair table.
    """
    try:
        _ensure_tables(conn)
    except Exception:
        logger.exception("Failed to create confusable tables")
        return 0

    count = 0
    count += _detect_tone_pairs(conn, limit)
    count += _detect_homophones(conn, limit)
    count += _detect_visual_confusables(conn, limit)
    conn.commit()
    return count


def _detect_tone_pairs(conn: sqlite3.Connection, limit: int) -> int:
    """Find items with same pinyin base but different tones."""
    try:
        rows = conn.execute("""
            SELECT id, hanzi, pinyin FROM content_item
            WHERE status = 'drill_ready' AND review_status = 'approved'
            LIMIT ?
        """, (limit,)).fetchall()
    except Exception:
        logger.exception("Failed to query content_item for tone pairs")
        return 0

    # Group by toneless pinyin base
    groups: Dict[str, List[sqlite3.Row]] = {}
    for row in rows:
        base = _strip_tones(row["pinyin"])
        groups.setdefault(base, []).append(row)

    count = 0
    for base, items in groups.items():
        if len(items) < 2:
            continue
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                # Only pair items with different hanzi (same pinyin base)
                if a["hanzi"] == b["hanzi"]:
                    continue
                # Ensure normalized full pinyin actually differs (tone difference)
                if _normalize_pinyin(a["pinyin"]) == _normalize_pinyin(b["pinyin"]):
                    # Same base AND same full pinyin => homophone, not tone pair
                    continue
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO confusable_pair
                            (item_a_id, item_b_id, confusable_type, similarity_score)
                        VALUES (?, ?, 'tone_pair', 0.7)
                    """, (min(a["id"], b["id"]), max(a["id"], b["id"])))
                    if conn.total_changes:
                        count += 1
                except Exception:
                    pass
    return count


def _detect_homophones(conn: sqlite3.Connection, limit: int) -> int:
    """Find items with identical pronunciation but different characters."""
    try:
        rows = conn.execute("""
            SELECT id, hanzi, pinyin FROM content_item
            WHERE status = 'drill_ready' AND review_status = 'approved'
            LIMIT ?
        """, (limit,)).fetchall()
    except Exception:
        logger.exception("Failed to query content_item for homophones")
        return 0

    # Group by normalized pinyin (with tones intact)
    groups: Dict[str, List[sqlite3.Row]] = {}
    for row in rows:
        key = _normalize_pinyin(row["pinyin"])
        groups.setdefault(key, []).append(row)

    count = 0
    for key, items in groups.items():
        if len(items) < 2:
            continue
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a["hanzi"] == b["hanzi"]:
                    continue
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO confusable_pair
                            (item_a_id, item_b_id, confusable_type, similarity_score)
                        VALUES (?, ?, 'homophone', 0.8)
                    """, (min(a["id"], b["id"]), max(a["id"], b["id"])))
                    if conn.total_changes:
                        count += 1
                except Exception:
                    pass
    return count


def _detect_visual_confusables(conn: sqlite3.Connection, limit: int) -> int:
    """Find items with similar-looking characters (shared radicals, stroke similarity).

    Uses a simple heuristic: single-character items that share component
    characters with other single-character hanzi. For multi-character items,
    checks if they share any individual characters.
    """
    try:
        rows = conn.execute("""
            SELECT id, hanzi FROM content_item
            WHERE status = 'drill_ready' AND review_status = 'approved'
            LIMIT ?
        """, (limit,)).fetchall()
    except Exception:
        logger.exception("Failed to query content_item for visual confusables")
        return 0

    # Build a map of individual characters to item IDs
    char_to_items: Dict[str, List[int]] = {}
    for row in rows:
        hanzi = row["hanzi"]
        if len(hanzi) == 1:
            # Single-character items: index by the character itself
            char_to_items.setdefault(hanzi, []).append(row["id"])
        else:
            # Multi-character items: index by each constituent character
            for ch in hanzi:
                char_to_items.setdefault(ch, []).append(row["id"])

    # Pair items that share characters but are different items
    seen_pairs = set()
    count = 0
    for row in rows:
        hanzi = row["hanzi"]
        if len(hanzi) != 1:
            continue
        # Find other single-character items sharing this character
        # via the character map — look for items that have overlapping
        # character sets
        related_ids = set()
        for ch in hanzi:
            for item_id in char_to_items.get(ch, []):
                if item_id != row["id"]:
                    related_ids.add(item_id)

        for other_id in related_ids:
            pair_key = (min(row["id"], other_id), max(row["id"], other_id))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # Verify the other item is also a single-character item for
            # true visual confusability (multi-char sharing one char is
            # more a prerequisite relationship than visual confusion)
            try:
                other = conn.execute(
                    "SELECT hanzi FROM content_item WHERE id = ?",
                    (other_id,)
                ).fetchone()
                if other and len(other["hanzi"]) == 1:
                    conn.execute("""
                        INSERT OR IGNORE INTO confusable_pair
                            (item_a_id, item_b_id, confusable_type,
                             similarity_score)
                        VALUES (?, ?, 'visual', 0.5)
                    """, pair_key)
                    if conn.total_changes:
                        count += 1
            except Exception:
                pass
    return count


def get_confusable_pairs(
    conn: sqlite3.Connection, item_id: int
) -> List[Dict]:
    """Get all confusable pairs for a given item.

    Returns a list of dicts with keys:
        partner_id, confusable_type, similarity_score
    """
    try:
        rows = conn.execute("""
            SELECT
                CASE WHEN item_a_id = ? THEN item_b_id ELSE item_a_id END
                    AS partner_id,
                confusable_type,
                similarity_score
            FROM confusable_pair
            WHERE item_a_id = ? OR item_b_id = ?
        """, (item_id, item_id, item_id)).fetchall()
        return [
            {
                "partner_id": row["partner_id"],
                "confusable_type": row["confusable_type"],
                "similarity_score": row["similarity_score"],
            }
            for row in rows
        ]
    except Exception:
        logger.exception("Failed to get confusable pairs for item %d", item_id)
        return []


def should_space_apart(
    conn: sqlite3.Connection,
    item_a_id: int,
    item_b_id: int,
    user_id: int = 1,
) -> bool:
    """Check if two confusable items should be spaced apart in the same session.

    Early mastery (seen, passed_once, stabilizing, decayed): space apart
    (avoid interference).
    Later mastery (stable, durable): interleave deliberately (desirable
    difficulty).

    Returns True if the items should be spaced apart (not shown together).
    """
    try:
        # Check if these items are actually a confusable pair
        pair = conn.execute("""
            SELECT 1 FROM confusable_pair
            WHERE (item_a_id = ? AND item_b_id = ?)
               OR (item_a_id = ? AND item_b_id = ?)
        """, (
            min(item_a_id, item_b_id), max(item_a_id, item_b_id),
            min(item_a_id, item_b_id), max(item_a_id, item_b_id),
        )).fetchone()

        if not pair:
            return False  # Not confusable — no spacing needed

        # Get mastery stages for both items across all modalities
        stages = conn.execute("""
            SELECT mastery_stage FROM progress
            WHERE content_item_id IN (?, ?) AND user_id = ?
        """, (item_a_id, item_b_id, user_id)).fetchall()

        if not stages:
            # No progress at all — space apart to avoid early interference
            return True

        # If ANY modality for either item is still in early mastery,
        # space them apart
        for row in stages:
            if row["mastery_stage"] in _SPACE_APART_STAGES:
                return True

        # Both items are stable/durable across all modalities —
        # interleave for desirable difficulty
        return False

    except Exception:
        logger.exception(
            "Failed to check spacing for items %d and %d", item_a_id, item_b_id
        )
        # Default to spacing apart on error (safer for learning)
        return True


def record_interference_event(
    conn: sqlite3.Connection,
    user_id: int,
    confused_item_id: int,
    intended_item_id: int,
) -> None:
    """Record when a user confuses one item with another.

    This data feeds back into the confusable pair similarity scores
    and scheduling decisions.
    """
    try:
        _ensure_tables(conn)
        conn.execute("""
            INSERT INTO interference_event
                (user_id, confused_item_id, intended_item_id)
            VALUES (?, ?, ?)
        """, (user_id, confused_item_id, intended_item_id))

        # Boost similarity score for this pair if it exists
        pair_a = min(confused_item_id, intended_item_id)
        pair_b = max(confused_item_id, intended_item_id)
        conn.execute("""
            UPDATE confusable_pair
            SET similarity_score = MIN(1.0, similarity_score + 0.05)
            WHERE item_a_id = ? AND item_b_id = ?
        """, (pair_a, pair_b))

        # If no existing pair, create one as user-confirmed confusable
        conn.execute("""
            INSERT OR IGNORE INTO confusable_pair
                (item_a_id, item_b_id, confusable_type, similarity_score)
            VALUES (?, ?, 'user_confirmed', 0.9)
        """, (pair_a, pair_b))

        conn.commit()
    except Exception:
        logger.exception(
            "Failed to record interference event: user=%d confused=%d intended=%d",
            user_id, confused_item_id, intended_item_id,
        )
