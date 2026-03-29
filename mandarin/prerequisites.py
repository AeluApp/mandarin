"""Curriculum prerequisite graph — identify and enforce learning dependencies.

Prerequisites for Mandarin content items:
- Character components: compound characters require knowledge of component characters
- Grammar patterns: complex structures require simpler structures
- Compound words: multi-character words require knowledge of individual characters
- Semantic fields: advanced vocabulary builds on basic vocabulary in same domain

Soft gating: prerequisites are recommendations, not hard blocks. After 7 days
without meeting prerequisites, items are unlocked anyway.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SOFT_GATE_DAYS = 7  # Days before overriding prerequisite gate

# Mastery stages considered "met" for prerequisite purposes
_MET_STAGES = frozenset({"passed_once", "stabilizing", "stable", "durable"})


def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create prerequisite_edge table if missing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prerequisite_edge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            prerequisite_id INTEGER NOT NULL,
            edge_type TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_id, prerequisite_id, edge_type)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_prereq_item
            ON prerequisite_edge(item_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_prereq_prereq
            ON prerequisite_edge(prerequisite_id)
    """)


def build_prerequisite_graph(conn: sqlite3.Connection, limit: int = 1000) -> int:
    """Scan content items and build prerequisite edges.

    Returns number of new edges created.
    """
    try:
        _ensure_tables(conn)
    except Exception:
        logger.exception("Failed to create prerequisite tables")
        return 0

    count = 0
    count += _detect_character_components(conn, limit)
    count += _detect_compound_words(conn, limit)
    conn.commit()
    return count


def _detect_character_components(conn: sqlite3.Connection, limit: int) -> int:
    """Find multi-character items where individual characters are also content items.

    For each content item with hanzi length > 1, check if individual characters
    are also content items. If so, create prerequisite edges (the single
    characters are prerequisites for the multi-character item).
    """
    try:
        # Get all items — we need both multi-char and single-char
        rows = conn.execute("""
            SELECT id, hanzi FROM content_item
            WHERE status = 'drill_ready' AND review_status = 'approved'
            LIMIT ?
        """, (limit,)).fetchall()
    except Exception:
        logger.exception("Failed to query content_item for character components")
        return 0

    # Build a lookup from single character to item ID
    char_to_id: Dict[str, int] = {}
    for row in rows:
        if len(row["hanzi"]) == 1:
            char_to_id[row["hanzi"]] = row["id"]

    count = 0
    for row in rows:
        hanzi = row["hanzi"]
        if len(hanzi) < 2:
            continue

        # Each individual character that exists as its own content item
        # is a prerequisite for this multi-character item
        for ch in hanzi:
            prereq_id = char_to_id.get(ch)
            if prereq_id is None or prereq_id == row["id"]:
                continue
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO prerequisite_edge
                        (item_id, prerequisite_id, edge_type)
                    VALUES (?, ?, 'character_component')
                """, (row["id"], prereq_id))
                if conn.total_changes:
                    count += 1
            except Exception:
                pass
    return count


def _detect_compound_words(conn: sqlite3.Connection, limit: int) -> int:
    """Find compound words where component words are content items at lower HSK levels.

    For items with HSK level, look for sub-words (contained hanzi strings)
    at a lower HSK level that are also content items. Those lower-level items
    are prerequisites.
    """
    try:
        rows = conn.execute("""
            SELECT id, hanzi, hsk_level FROM content_item
            WHERE status = 'drill_ready'
              AND review_status = 'approved'
              AND hsk_level IS NOT NULL
              AND LENGTH(hanzi) >= 2
            ORDER BY hsk_level ASC
            LIMIT ?
        """, (limit,)).fetchall()
    except Exception:
        logger.exception("Failed to query content_item for compound words")
        return 0

    # Build lookup of hanzi -> (id, hsk_level) for multi-char items
    # that could be sub-words
    word_lookup: Dict[str, tuple] = {}
    try:
        all_items = conn.execute("""
            SELECT id, hanzi, hsk_level FROM content_item
            WHERE status = 'drill_ready'
              AND review_status = 'approved'
              AND hsk_level IS NOT NULL
              AND LENGTH(hanzi) >= 2
            LIMIT ?
        """, (limit,)).fetchall()
        for item in all_items:
            word_lookup[item["hanzi"]] = (item["id"], item["hsk_level"])
    except Exception:
        logger.exception("Failed to build word lookup for compound detection")
        return 0

    count = 0
    for row in rows:
        hanzi = row["hanzi"]
        hsk = row["hsk_level"]
        if hsk is None or len(hanzi) < 3:
            # Need at least 3 chars to contain a 2-char sub-word
            continue

        # Check all possible 2-char sub-strings
        for start in range(len(hanzi) - 1):
            sub = hanzi[start:start + 2]
            entry = word_lookup.get(sub)
            if entry is None:
                continue
            sub_id, sub_hsk = entry
            if sub_id == row["id"]:
                continue
            # Only create edge if the sub-word is at a lower HSK level
            if sub_hsk is not None and hsk is not None and sub_hsk < hsk:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO prerequisite_edge
                            (item_id, prerequisite_id, edge_type)
                        VALUES (?, ?, 'compound_word')
                    """, (row["id"], sub_id))
                    if conn.total_changes:
                        count += 1
                except Exception:
                    pass
    return count


def check_prerequisites_met(
    conn: sqlite3.Connection, user_id: int, item_id: int
) -> Dict:
    """Check if all prerequisites for an item are met.

    Returns:
        {
            "met": bool,       -- True if all prerequisites satisfied (or overridden)
            "missing": list,   -- List of dicts for unmet prerequisites
            "override": bool,  -- True if soft gate period has expired
        }

    "override" is True if the item has been waiting > SOFT_GATE_DAYS,
    meaning all prerequisites are bypassed regardless of mastery state.
    """
    result = {"met": True, "missing": [], "override": False}

    try:
        edges = conn.execute("""
            SELECT prerequisite_id, edge_type FROM prerequisite_edge
            WHERE item_id = ?
        """, (item_id,)).fetchall()
    except Exception:
        logger.exception("Failed to query prerequisites for item %d", item_id)
        return result  # No edges found => met

    if not edges:
        return result

    # Check soft gate: has the item been available longer than SOFT_GATE_DAYS?
    try:
        item_row = conn.execute("""
            SELECT created_at FROM content_item WHERE id = ?
        """, (item_id,)).fetchone()
        if item_row and item_row["created_at"]:
            age = conn.execute("""
                SELECT julianday('now') - julianday(?) AS days_available
            """, (item_row["created_at"],)).fetchone()
            if age and age["days_available"] is not None:
                if age["days_available"] > SOFT_GATE_DAYS:
                    result["override"] = True
                    result["met"] = True
                    return result
    except Exception:
        # If we can't check the gate, continue with normal prerequisite check
        pass

    missing = []
    for edge in edges:
        prereq_id = edge["prerequisite_id"]
        edge_type = edge["edge_type"]

        # Check if the user has met this prerequisite in any modality
        try:
            progress_rows = conn.execute("""
                SELECT mastery_stage FROM progress
                WHERE content_item_id = ? AND user_id = ?
            """, (prereq_id, user_id)).fetchall()
        except Exception:
            # Can't verify — assume not met
            missing.append({
                "prerequisite_id": prereq_id,
                "edge_type": edge_type,
                "mastery_stage": None,
            })
            continue

        if not progress_rows:
            # Never studied — prerequisite not met
            missing.append({
                "prerequisite_id": prereq_id,
                "edge_type": edge_type,
                "mastery_stage": "unseen",
            })
            continue

        # Check if ANY modality has reached a "met" mastery stage
        met = False
        best_stage = "seen"
        for pr in progress_rows:
            stage = pr["mastery_stage"]
            if stage in _MET_STAGES:
                met = True
                break
            best_stage = stage

        if not met:
            missing.append({
                "prerequisite_id": prereq_id,
                "edge_type": edge_type,
                "mastery_stage": best_stage,
            })

    if missing:
        result["met"] = False
        result["missing"] = missing

    return result


def get_prerequisites(
    conn: sqlite3.Connection, item_id: int
) -> List[Dict]:
    """Get all prerequisite items for a given item.

    Returns a list of dicts with keys:
        prerequisite_id, edge_type, hanzi, pinyin, english
    """
    try:
        rows = conn.execute("""
            SELECT
                pe.prerequisite_id,
                pe.edge_type,
                ci.hanzi,
                ci.pinyin,
                ci.english
            FROM prerequisite_edge pe
            JOIN content_item ci ON ci.id = pe.prerequisite_id
            WHERE pe.item_id = ?
        """, (item_id,)).fetchall()
        return [
            {
                "prerequisite_id": row["prerequisite_id"],
                "edge_type": row["edge_type"],
                "hanzi": row["hanzi"],
                "pinyin": row["pinyin"],
                "english": row["english"],
            }
            for row in rows
        ]
    except Exception:
        logger.exception("Failed to get prerequisites for item %d", item_id)
        return []


def get_dependents(
    conn: sqlite3.Connection, item_id: int
) -> List[Dict]:
    """Get all items that depend on this item as a prerequisite.

    Returns a list of dicts with keys:
        item_id, edge_type, hanzi, pinyin, english
    """
    try:
        rows = conn.execute("""
            SELECT
                pe.item_id,
                pe.edge_type,
                ci.hanzi,
                ci.pinyin,
                ci.english
            FROM prerequisite_edge pe
            JOIN content_item ci ON ci.id = pe.item_id
            WHERE pe.prerequisite_id = ?
        """, (item_id,)).fetchall()
        return [
            {
                "item_id": row["item_id"],
                "edge_type": row["edge_type"],
                "hanzi": row["hanzi"],
                "pinyin": row["pinyin"],
                "english": row["english"],
            }
            for row in rows
        ]
    except Exception:
        logger.exception("Failed to get dependents for item %d", item_id)
        return []
