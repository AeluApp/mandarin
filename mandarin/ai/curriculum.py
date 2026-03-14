"""Curriculum Architecture and HSK 9 Pathway (Doc 14).

Curriculum sequencing: what to teach next based on learner model data.
"""

import json
import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

HSK_MILESTONES = {
    1: {'vocab_target': 150, 'grammar_patterns': 10,
        'can_do': 'Introduce yourself, ask basic questions, understand simple phrases'},
    2: {'vocab_target': 300, 'grammar_patterns': 25,
        'can_do': 'Handle simple daily interactions, understand short passages'},
    3: {'vocab_target': 600, 'grammar_patterns': 50,
        'can_do': 'Discuss familiar topics, express opinions simply, read simple texts'},
    4: {'vocab_target': 1200, 'grammar_patterns': 80,
        'can_do': 'Discuss a range of topics fluently, understand main points of complex text'},
    5: {'vocab_target': 2500, 'grammar_patterns': 110,
        'can_do': 'Read Chinese-language newspapers, understand native speaker media'},
    6: {'vocab_target': 5000, 'grammar_patterns': 140,
        'can_do': 'Express yourself fluently and spontaneously, understand complex texts'},
    7: {'vocab_target': 6000, 'grammar_patterns': 175,
        'can_do': 'Discuss abstract topics, understand formal and written registers'},
    8: {'vocab_target': 8000, 'grammar_patterns': 210,
        'can_do': 'Read contemporary literature, understand academic and professional discourse'},
    9: {'vocab_target': 11000, 'grammar_patterns': 250,
        'can_do': 'Near-native proficiency: formal writing, classical allusions, all registers'},
}


def get_curriculum_recommendation(conn: sqlite3.Connection, user_id: int) -> dict:
    """Returns what the system recommends introducing next."""
    # Get proficiency from learner_proficiency_zones
    proficiency = None
    try:
        proficiency = conn.execute(
            "SELECT * FROM learner_proficiency_zones WHERE user_id=?",
            (user_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        pass

    if not proficiency:
        return _cold_start_recommendation()

    current_level = (proficiency['composite_hsk_estimate'] or 0) if proficiency else 0
    if current_level <= 0:
        return _cold_start_recommendation()
    current_level_floor = max(1, int(current_level))

    # 1. Grammar pattern gaps at current level (grammar_point with no learner_pattern_states entry)
    pattern_gaps = []
    try:
        pattern_gaps = conn.execute("""
            SELECT gp.id as grammar_point_id, gp.name, gp.category
            FROM grammar_point gp
            WHERE gp.hsk_level = ?
            AND NOT EXISTS (
                SELECT 1 FROM learner_pattern_states lps
                WHERE lps.user_id = ?
                AND lps.grammar_point_id = gp.id
            )
            AND EXISTS (
                SELECT 1 FROM content_grammar cg WHERE cg.grammar_point_id = gp.id
            )
            LIMIT 3
        """, (current_level_floor, user_id)).fetchall()
    except sqlite3.OperationalError:
        pass

    # 2. Vocabulary gaps at current level (content_item at this hsk_level not yet in memory_states)
    vocab_gaps = []
    try:
        vocab_gaps = conn.execute("""
            SELECT ci.hanzi, ci.pinyin, ci.english, ci.hsk_level
            FROM content_item ci
            WHERE ci.hsk_level = ?
            AND ci.status = 'drill_ready'
            AND NOT EXISTS (
                SELECT 1 FROM memory_states ms
                WHERE ms.content_item_id = ci.id
                AND ms.user_id = ?
            )
            LIMIT 10
        """, (current_level_floor, user_id)).fetchall()
    except sqlite3.OperationalError:
        pass

    # 3. Next-level patterns with prerequisites met (simplified: no prereq tracking)
    next_level_ready = _get_next_level_ready_patterns(conn, user_id, current_level_floor)

    # 4. Consolidating patterns needing volume
    consolidating = []
    try:
        consolidating = conn.execute("""
            SELECT lps.grammar_point_id, gp.name, lps.encounters
            FROM learner_pattern_states lps
            JOIN grammar_point gp ON gp.id = lps.grammar_point_id
            WHERE lps.user_id = ?
            AND lps.status = 'consolidating'
            AND lps.encounters < 15
            ORDER BY lps.encounters ASC
            LIMIT 5
        """, (user_id,)).fetchall()
    except sqlite3.OperationalError:
        pass

    milestone = HSK_MILESTONES.get(current_level_floor, {})
    next_milestone = HSK_MILESTONES.get(current_level_floor + 1, {})

    vocab_mastered = (proficiency['vocab_items_mastered'] or 0) if proficiency else 0
    grammar_mastered = (proficiency['grammar_patterns_mastered'] or 0) if proficiency else 0

    return {
        'current_composite_hsk': round(current_level, 1),
        'current_milestone': milestone.get('can_do', ''),
        'next_milestone': {
            'level': current_level_floor + 1,
            'target': next_milestone.get('can_do', ''),
            'vocab_gap': max(0, next_milestone.get('vocab_target', 0) - vocab_mastered),
            'pattern_gap': max(0, next_milestone.get('grammar_patterns', 0) - grammar_mastered),
        },
        'immediate_priorities': {
            'pattern_gaps_this_level': [dict(r) for r in pattern_gaps],
            'vocabulary_gaps_this_level': [dict(r) for r in vocab_gaps],
            'next_level_patterns_ready': next_level_ready,
            'consolidating_needs_volume': [dict(r) for r in consolidating],
        },
        'recommendation': _generate_recommendation_text(
            pattern_gaps, vocab_gaps, next_level_ready
        ),
    }


def _get_next_level_ready_patterns(conn: sqlite3.Connection, user_id: int, current_level: int) -> list:
    """Patterns at the next level not yet encountered by the learner."""
    try:
        next_level_patterns = conn.execute("""
            SELECT gp.id as grammar_point_id, gp.name, gp.category
            FROM grammar_point gp
            WHERE gp.hsk_level = ?
            AND NOT EXISTS (
                SELECT 1 FROM learner_pattern_states lps
                WHERE lps.user_id = ?
                AND lps.grammar_point_id = gp.id
            )
            AND EXISTS (
                SELECT 1 FROM content_grammar cg WHERE cg.grammar_point_id = gp.id
            )
            LIMIT 3
        """, (current_level + 1, user_id)).fetchall()
        return [dict(p) for p in next_level_patterns]
    except sqlite3.OperationalError:
        return []


def _cold_start_recommendation() -> dict:
    return {
        'current_composite_hsk': 0.0,
        'recommendation': 'Start with HSK 1 vocabulary and tonal foundation.',
        'immediate_priorities': {
            'pattern_gaps_this_level': [],
            'vocabulary_gaps_this_level': [],
            'next_level_patterns_ready': [],
            'consolidating_needs_volume': [],
        },
    }


def _generate_recommendation_text(pattern_gaps, vocab_gaps, ready_patterns) -> str:
    parts = []
    if pattern_gaps:
        names = ', '.join(r['name'] for r in pattern_gaps[:2])
        parts.append(f"Introduce {names} at current HSK level.")
    if vocab_gaps:
        parts.append(f"Generate drills for {len(vocab_gaps)} uncovered vocabulary items.")
    if ready_patterns:
        names = ', '.join(r['name'] for r in ready_patterns[:2])
        parts.append(f"Prerequisites met for {names} — ready to introduce.")
    return ' '.join(parts) if parts else 'Continue current review schedule.'


# ─────────────────────────────────────────────
# ANALYZER
# ─────────────────────────────────────────────

def analyze_curriculum_coverage(conn: sqlite3.Connection) -> list[dict]:
    """Audit cycle analyzer for curriculum coverage gaps."""
    from ..intelligence._base import _finding
    findings = []

    # 1. Grammar patterns at HSK 1-5 with no content items
    try:
        zero_item_patterns = conn.execute("""
            SELECT gp.name, gp.hsk_level
            FROM grammar_point gp
            WHERE gp.hsk_level <= 5
            AND NOT EXISTS (
                SELECT 1 FROM content_grammar cg WHERE cg.grammar_point_id = gp.id
            )
        """).fetchall()

        if zero_item_patterns:
            names = ', '.join(r['name'] for r in zero_item_patterns[:5])
            findings.append(_finding(
                dimension="curriculum",
                severity="high",
                title=f"{len(zero_item_patterns)} HSK 1-5 grammar pattern(s) with no drill items",
                analysis=f"Patterns without items: {names}. Cannot track in learner model without items.",
                recommendation="Generate drill items for these patterns.",
                claude_prompt="Find grammar_point entries with no content_grammar links.",
                impact="Learner model cannot track mastery for patterns with no items.",
                files=["mandarin/ai/curriculum.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # 2. Learners with stale proficiency estimates
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt
            FROM learner_proficiency_zones
            WHERE composite_hsk_estimate > 0
            AND computed_at < datetime('now','-30 days')
        """).fetchone()
        stale = (row["cnt"] or 0) if row else 0

        if stale > 0:
            findings.append(_finding(
                dimension="curriculum",
                severity="low",
                title=f"{stale} learner(s) with proficiency estimate not updated in 30 days",
                analysis="Proficiency zones may be stale, leading to outdated curriculum recommendations.",
                recommendation="Run estimate_proficiency_zones() for these users.",
                claude_prompt="Check learner_proficiency_zones for stale computed_at.",
                impact="Curriculum recommendations based on outdated data.",
                files=["mandarin/ai/curriculum.py", "mandarin/ai/learner_model.py"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings
