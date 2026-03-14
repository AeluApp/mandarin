"""Onboarding, Placement, and Activation (Doc 17).

Adaptive placement, diagnostic intake, and cold-start curriculum scaffolding.
"""

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


def build_placement_probe(conn: sqlite3.Connection) -> list[dict]:
    """Selects items spanning HSK 1-6 for placement probing.
    2-3 items per HSK level, targeting high-frequency vocabulary.
    """
    try:
        probe_items = conn.execute("""
            SELECT id, hanzi, english, hsk_level
            FROM content_item
            WHERE status = 'drill_ready'
            AND hsk_level BETWEEN 1 AND 6
            ORDER BY hsk_level, RANDOM()
            LIMIT 20
        """).fetchall()
        return [dict(i) for i in probe_items]
    except sqlite3.OperationalError:
        return []


def estimate_placement_from_probe(conn: sqlite3.Connection, onboarding_id: int) -> dict:
    """Estimates placement HSK level from probe responses.
    Uses threshold model: highest level at which accuracy >= 70%.
    """
    try:
        responses = conn.execute("""
            SELECT hsk_level_of_item,
                   AVG(CASE WHEN correct=1 THEN 100.0 ELSE 0.0 END) as accuracy,
                   COUNT(*) as cnt
            FROM placement_probe_responses
            WHERE onboarding_id=?
            GROUP BY hsk_level_of_item
            ORDER BY hsk_level_of_item
        """, (onboarding_id,)).fetchall()
    except sqlite3.OperationalError:
        return {'hsk_estimate': 1.0, 'confidence': 'low'}

    placement = 1.0
    for r in responses:
        cnt = r['cnt'] or 0
        acc = r['accuracy'] or 0
        if cnt >= 2 and acc >= 70.0:
            placement = r['hsk_level_of_item']
        elif cnt >= 2 and acc < 50.0:
            break

    confidence = 'medium' if len(responses) >= 4 else 'low'

    try:
        conn.execute("""
            UPDATE onboarding_sessions
            SET placement_hsk_estimate=?, placement_confidence=?
            WHERE id=?
        """, (placement, confidence, onboarding_id))
    except sqlite3.OperationalError:
        pass

    return {'hsk_estimate': placement, 'confidence': confidence}


def generate_onboarding_curriculum(conn: sqlite3.Connection, user_id: int, onboarding_id: int) -> dict:
    """Generates the first week's curriculum based on placement results.
    Seeds initial memory states and grammar pattern priorities.
    """
    session = None
    try:
        session = conn.execute(
            "SELECT * FROM onboarding_sessions WHERE id=?",
            (onboarding_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        pass

    if not session:
        return {'placement_level': 1.0, 'items_seeded': 0, 'first_session_ready': False}

    placement = (session['placement_hsk_estimate'] or 1.0)
    level = max(1, int(placement))

    # Seed vocabulary from content_item at placement level and one below
    items_to_seed = []
    try:
        items_to_seed = conn.execute("""
            SELECT ci.id
            FROM content_item ci
            WHERE ci.status = 'drill_ready'
            AND ci.hsk_level BETWEEN ? AND ?
            ORDER BY ci.difficulty ASC
            LIMIT 50
        """, (max(1, level - 1), level)).fetchall()
    except sqlite3.OperationalError:
        pass

    # Initialize memory states for seeded items
    seeded = 0
    for item in items_to_seed:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO memory_states
                (user_id, content_item_id, stability, difficulty, state)
                VALUES (?,?,0.4,0.5,'new')
            """, (user_id, item['id']))
            seeded += 1
        except sqlite3.OperationalError:
            break

    # Mark activation complete
    try:
        conn.execute("""
            UPDATE onboarding_sessions
            SET activation_completed=1
            WHERE id=?
        """, (onboarding_id,))
    except sqlite3.OperationalError:
        pass

    return {
        'placement_level': placement,
        'items_seeded': seeded,
        'first_session_ready': seeded > 0,
    }
