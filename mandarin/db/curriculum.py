"""Curriculum queries — grammar, skills, HSK progression."""

import sqlite3
from pathlib import Path
from typing import List, Optional


def get_grammar_points(conn: sqlite3.Connection, hsk_max: int = 9) -> List[dict]:
    """Get grammar points up to the given HSK level."""
    rows = conn.execute("""
        SELECT * FROM grammar_point WHERE hsk_level <= ?
        ORDER BY hsk_level, difficulty
    """, (hsk_max,)).fetchall()
    return [dict(r) for r in rows]


def get_skills(conn: sqlite3.Connection, category: str = None) -> List[dict]:
    """Get skills, optionally filtered by category."""
    if category:
        rows = conn.execute(
            "SELECT * FROM skill WHERE category = ? ORDER BY hsk_level",
            (category,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM skill ORDER BY category, hsk_level").fetchall()
    return [dict(r) for r in rows]


def link_content_grammar(conn: sqlite3.Connection, content_item_id: int,
                         grammar_point_id: int) -> None:
    """Link a content item to a grammar point."""
    conn.execute("""
        INSERT OR IGNORE INTO content_grammar (content_item_id, grammar_point_id)
        VALUES (?, ?)
    """, (content_item_id, grammar_point_id))
    conn.commit()


def link_content_skill(conn: sqlite3.Connection, content_item_id: int,
                       skill_id: int) -> None:
    """Link a content item to a skill."""
    conn.execute("""
        INSERT OR IGNORE INTO content_skill (content_item_id, skill_id)
        VALUES (?, ?)
    """, (content_item_id, skill_id))
    conn.commit()


def get_core_lexicon_coverage(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Check coverage of core lexicon lenses."""
    result = {}
    for lens in ["function_words", "time_sequence", "numbers_measure"]:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN p.last_review_date >= date('now', '-14 days') THEN 1 ELSE 0 END) as recent
            FROM content_item ci
            LEFT JOIN progress p ON ci.id = p.content_item_id AND p.user_id = ?
            WHERE ci.content_lens = ? AND ci.status = 'drill_ready'
        """, (user_id, lens,)).fetchone()
        total = row["total"] or 0
        recent = row["recent"] or 0
        result[lens] = {
            "total": total,
            "seen_recently": recent,
            "pct": (recent / total * 100) if total > 0 else 100,
        }
    return result


def get_core_catchup_items(conn: sqlite3.Connection, limit: int = 3, user_id: int = 1) -> List[dict]:
    """Get core lexicon items that haven't been reviewed in 3+ sessions."""
    rows = conn.execute("""
        SELECT ci.* FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.user_id = ?
        WHERE ci.content_lens IN ('function_words', 'time_sequence', 'numbers_measure')
          AND ci.status = 'drill_ready'
          AND (p.last_review_date IS NULL OR p.last_review_date < date('now', '-14 days'))
        ORDER BY
            CASE WHEN p.last_review_date IS NULL THEN 0 ELSE 1 END,
            p.last_review_date ASC
        LIMIT ?
    """, (user_id, limit,)).fetchall()
    return [dict(r) for r in rows]


def get_skill_coverage(conn: sqlite3.Connection, user_id: int = 1) -> List[dict]:
    """Get skill categories with their practice coverage."""
    rows = conn.execute("""
        SELECT s.category,
               COUNT(DISTINCT s.id) as total_skills,
               COUNT(DISTINCT CASE WHEN p.total_attempts > 0 THEN cs.skill_id END) as practiced
        FROM skill s
        LEFT JOIN content_skill cs ON s.id = cs.skill_id
        LEFT JOIN progress p ON cs.content_item_id = p.content_item_id AND p.user_id = ?
        GROUP BY s.category
    """, (user_id,)).fetchall()
    result = []
    for r in rows:
        total = r["total_skills"] or 0
        practiced = r["practiced"] or 0
        result.append({
            "category": r["category"],
            "total_skills": total,
            "practiced": practiced,
            "pct": (practiced / total * 100) if total > 0 else 0,
        })
    return result


def should_suggest_next_hsk(conn: sqlite3.Connection, user_id: int = 1) -> Optional[int]:
    """Check if the learner should be prompted to load the next HSK level.

    Returns the next level to suggest, or None.
    """
    from .progress import get_mastery_by_hsk
    mastery = get_mastery_by_hsk(conn, user_id=user_id)
    if not mastery:
        return None

    max_level = max(mastery.keys())
    if mastery[max_level]["pct"] < 80:
        return None

    next_level = max_level + 1
    hsk_file = Path(__file__).parent.parent.parent / "data" / "hsk" / f"hsk{next_level}.json"
    if hsk_file.exists():
        return next_level
    return None
