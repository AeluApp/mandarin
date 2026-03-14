"""Input Acquisition Layer (Doc 15).

Reading and listening pipelines for comprehensible input above HSK 6.
"""

import json
import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


def analyze_text_difficulty(conn: sqlite3.Connection, text_id: int) -> dict:
    """Analyzes reading text difficulty. Returns comprehensibility assessment."""
    try:
        text = conn.execute(
            "SELECT * FROM reading_texts WHERE id=?", (text_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return {}
    if not text:
        return {}

    above_ceiling = json.loads(text['above_ceiling_words'] or '[]')
    word_count = text['word_count'] or 1
    density = len(above_ceiling) / max(1, word_count)

    return {
        'text_id': text_id,
        'word_count': word_count,
        'hsk_ceiling': text['hsk_ceiling'],
        'above_ceiling_word_count': len(above_ceiling),
        'above_ceiling_density': density,
        'is_comprehensible_input': density <= 0.05,
        'i_plus_one_rating': (
            'too_easy' if density < 0.01 else
            'optimal' if density <= 0.05 else
            'challenging' if density <= 0.10 else
            'too_difficult'
        ),
        'above_ceiling_words': above_ceiling[:10],
    }


def recommend_reading_texts(conn: sqlite3.Connection, user_id: int, n: int = 3) -> list[dict]:
    """Recommends reading texts at the learner's i+1 level."""
    target_ceiling = 2  # default
    try:
        proficiency = conn.execute(
            "SELECT vocab_hsk_estimate FROM learner_proficiency_zones WHERE user_id=?",
            (user_id,)
        ).fetchone()
        if proficiency and proficiency['vocab_hsk_estimate']:
            target_ceiling = min(9, int(proficiency['vocab_hsk_estimate']) + 1)
    except sqlite3.OperationalError:
        pass

    try:
        texts = conn.execute("""
            SELECT rt.*, COUNT(re.id) as times_read
            FROM reading_texts rt
            LEFT JOIN reading_events re ON re.text_id = rt.id AND re.user_id = ?
            WHERE rt.approved = 1
            AND rt.hsk_ceiling = ?
            AND (re.id IS NULL OR re.completion_pct < 0.90)
            GROUP BY rt.id
            ORDER BY rt.difficulty_score ASC
            LIMIT ?
        """, (user_id, target_ceiling, n)).fetchall()
        return [dict(t) for t in texts]
    except sqlite3.OperationalError:
        return []


def process_inline_lookup(
    conn: sqlite3.Connection, user_id: int, reading_event_id: int, hanzi: str
) -> dict:
    """Processes an inline dictionary lookup during reading."""
    # Find item in corpus
    item = None
    try:
        item = conn.execute(
            "SELECT * FROM content_item WHERE hanzi=? AND status='drill_ready' AND review_status='approved' LIMIT 1",
            (hanzi,)
        ).fetchone()
    except sqlite3.OperationalError:
        pass

    queued_for_srs = False
    if item:
        try:
            in_srs = conn.execute(
                "SELECT 1 FROM memory_states WHERE user_id=? AND content_item_id=?",
                (user_id, item['id'])
            ).fetchone()
            if not in_srs:
                conn.execute("""
                    INSERT OR IGNORE INTO pending_srs_additions
                    (user_id, content_item_id, encounter_source)
                    VALUES (?,?,'reading_lookup')
                """, (user_id, item['id']))
                queued_for_srs = True
        except sqlite3.OperationalError:
            pass

    # Log lookup in reading event
    try:
        event = conn.execute(
            "SELECT lookups FROM reading_events WHERE id=?",
            (reading_event_id,)
        ).fetchone()
        if event:
            lookups = json.loads(event['lookups'] or '[]')
            lookups.append({'hanzi': hanzi})
            conn.execute(
                "UPDATE reading_events SET lookups=? WHERE id=?",
                (json.dumps(lookups, ensure_ascii=False), reading_event_id)
            )
    except sqlite3.OperationalError:
        pass

    return {
        'hanzi': hanzi,
        'item_found': bool(item),
        'queued_for_srs': queued_for_srs,
        'item': dict(item) if item else None,
    }


# ─────────────────────────────────────────────
# ANALYZER
# ─────────────────────────────────────────────

def analyze_input_layer(conn: sqlite3.Connection) -> list[dict]:
    """Audit cycle analyzer for input layer coverage."""
    from ..intelligence._base import _finding
    findings = []

    # 1. Reading text coverage at each HSK level
    try:
        coverage = conn.execute("""
            SELECT hsk_ceiling, COUNT(*) as cnt
            FROM reading_texts
            WHERE approved=1
            GROUP BY hsk_ceiling
            ORDER BY hsk_ceiling
        """).fetchall()
        level_counts = {r['hsk_ceiling']: r['cnt'] for r in coverage}

        for level in range(3, 8):
            if level_counts.get(level, 0) < 5:
                findings.append(_finding(
                    dimension="input_layer",
                    severity="medium" if level <= 5 else "low",
                    title=f"Insufficient reading texts at HSK {level}",
                    analysis=f"Only {level_counts.get(level, 0)} approved texts at HSK {level}. Target: 10+ per level.",
                    recommendation=f"Generate reading passages at HSK {level}.",
                    claude_prompt=f"Check reading_texts count for hsk_ceiling={level}.",
                    impact="Learners at this level lack comprehensible input material.",
                    files=["mandarin/ai/input_layer.py"],
                ))
    except sqlite3.OperationalError:
        pass

    # 2. Active learners not using reading layer
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT ms.user_id) as cnt
            FROM memory_states ms
            WHERE ms.reps >= 100
            AND NOT EXISTS (
                SELECT 1 FROM reading_events re
                WHERE re.user_id = ms.user_id
                AND re.started_at >= datetime('now','-30 days')
            )
        """).fetchone()
        non_readers = (row["cnt"] or 0) if row else 0

        if non_readers > 0:
            findings.append(_finding(
                dimension="input_layer",
                severity="low",
                title=f"{non_readers} active learner(s) not using reading layer in last 30 days",
                analysis="At 100+ reviews, learners benefit significantly from reading practice.",
                recommendation="Surface reading recommendations more prominently.",
                claude_prompt="Check memory_states users with reps>=100 not in reading_events.",
                impact="Missed acquisition opportunity through comprehensible input.",
                files=["mandarin/ai/input_layer.py"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings
