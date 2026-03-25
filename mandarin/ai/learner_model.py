"""Learner Model and Personalization Engine (Doc 16).

Three-layer learner model:
  Layer 1: Vocabulary knowledge state (from memory_states / Doc 13)
  Layer 2: Grammar pattern mastery (per grammar_point)
  Layer 3: Proficiency zone estimates (HSK level per skill domain)

Zero Claude tokens at runtime — all computations are deterministic.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# PATTERN STATE UPDATE
# Links review events to grammar patterns via content_grammar.
# ─────────────────────────────────────────────

def update_pattern_state_from_review(
    conn: sqlite3.Connection,
    user_id: int,
    content_item_id: int,
    correct: bool,
) -> None:
    """Update learner_pattern_states after a review event.

    Looks up grammar_point(s) linked to this content_item via content_grammar,
    then updates the learner's mastery state for each pattern.
    """
    try:
        item_patterns = conn.execute("""
            SELECT cg.grammar_point_id
            FROM content_grammar cg
            WHERE cg.content_item_id = ?
        """, (content_item_id,)).fetchall()
    except sqlite3.OperationalError:
        return

    for row in item_patterns:
        _upsert_pattern_state(conn, user_id, row["grammar_point_id"], correct)


def _upsert_pattern_state(
    conn: sqlite3.Connection,
    user_id: int,
    grammar_point_id: int,
    correct: bool,
) -> None:
    existing = conn.execute("""
        SELECT * FROM learner_pattern_states
        WHERE user_id=? AND grammar_point_id=?
    """, (user_id, grammar_point_id)).fetchone()

    now = datetime.now(UTC).isoformat()

    if not existing:
        conn.execute("""
            INSERT INTO learner_pattern_states
            (user_id, grammar_point_id, status, encounters,
             correct_streak, error_count_30d, first_encountered_at, last_updated_at)
            VALUES (?,?,'introduced',1,?,0,?,?)
        """, (
            user_id, grammar_point_id,
            1 if correct else 0, now, now,
        ))
    else:
        state = dict(existing)
        new_streak = (state["correct_streak"] + 1) if correct else 0
        new_errors = state["error_count_30d"] + (0 if correct else 1)
        new_encounters = state["encounters"] + 1
        new_status = _compute_pattern_status(
            state["status"], new_streak, new_encounters, new_errors,
        )

        conn.execute("""
            UPDATE learner_pattern_states SET
                status=?, encounters=?, correct_streak=?,
                error_count_30d=?, last_updated_at=?
            WHERE user_id=? AND grammar_point_id=?
        """, (
            new_status, new_encounters, new_streak,
            new_errors, now, user_id, grammar_point_id,
        ))


def _compute_pattern_status(
    current_status: str, streak: int, encounters: int, errors_30d: int,
) -> str:
    """Determine pattern mastery status from evidence signals."""
    if encounters < 3:
        return "introduced"
    if errors_30d > 3 or streak < 2:
        return "acquiring"
    if streak >= 5 and errors_30d <= 1 and encounters >= 20:
        return "mastered"
    if streak >= 3 and errors_30d <= 2:
        return "consolidating"
    return current_status


def update_pattern_avg_stability(
    conn: sqlite3.Connection,
    user_id: int,
    grammar_point_id: int,
) -> None:
    """Recompute average memory stability for items exercising this pattern.

    Called periodically, not on every review.
    """
    try:
        row = conn.execute("""
            SELECT AVG(ms.stability) as avg_s
            FROM memory_states ms
            JOIN content_grammar cg ON cg.content_item_id = ms.content_item_id
            WHERE ms.user_id = ?
            AND cg.grammar_point_id = ?
            AND ms.reps >= 3
        """, (user_id, grammar_point_id)).fetchone()

        avg = row["avg_s"] if row else None
        if avg is not None:
            conn.execute("""
                UPDATE learner_pattern_states
                SET avg_stability=?, last_updated_at=datetime('now')
                WHERE user_id=? AND grammar_point_id=?
            """, (avg, user_id, grammar_point_id))
    except sqlite3.OperationalError:
        logger.debug("update_pattern_avg_stability skipped — table missing")


# ─────────────────────────────────────────────
# PROFICIENCY ZONE ESTIMATION
# ─────────────────────────────────────────────

def estimate_proficiency_zones(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Compute proficiency zone estimates across skill domains.

    Runs weekly or after significant milestone (100 new items reviewed).
    """
    vocab = _estimate_vocab_zone(conn, user_id)
    grammar = _estimate_grammar_zone(conn, user_id)
    listening = _estimate_listening_zone(conn, user_id)

    composite = _compute_composite_hsk(vocab, grammar, listening)

    # Upsert proficiency zones
    existing = conn.execute(
        "SELECT 1 FROM learner_proficiency_zones WHERE user_id=?",
        (user_id,),
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE learner_proficiency_zones SET
                vocab_hsk_estimate=?, vocab_items_mastered=?, vocab_coverage_pct=?,
                grammar_hsk_estimate=?, grammar_patterns_mastered=?, grammar_coverage_pct=?,
                listening_hsk_estimate=?, listening_confidence=?,
                composite_hsk_estimate=?, computed_at=datetime('now')
            WHERE user_id=?
        """, (
            vocab["hsk_estimate"], vocab["items_mastered"], vocab["coverage_pct"],
            grammar["hsk_estimate"], grammar["patterns_mastered"], grammar["coverage_pct"],
            listening["hsk_estimate"], listening["confidence"],
            composite, user_id,
        ))
    else:
        conn.execute("""
            INSERT INTO learner_proficiency_zones
            (user_id, vocab_hsk_estimate, vocab_items_mastered, vocab_coverage_pct,
             grammar_hsk_estimate, grammar_patterns_mastered, grammar_coverage_pct,
             listening_hsk_estimate, listening_confidence,
             composite_hsk_estimate)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            user_id,
            vocab["hsk_estimate"], vocab["items_mastered"], vocab["coverage_pct"],
            grammar["hsk_estimate"], grammar["patterns_mastered"], grammar["coverage_pct"],
            listening["hsk_estimate"], listening["confidence"],
            composite,
        ))

    return {
        "vocab": vocab,
        "grammar": grammar,
        "listening": listening,
        "composite_hsk": composite,
    }


def _estimate_vocab_zone(conn: sqlite3.Connection, user_id: int) -> dict:
    """Estimate vocabulary HSK level from mastered items in memory_states."""
    try:
        by_level = conn.execute("""
            SELECT ci.hsk_level, COUNT(*) as mastered
            FROM memory_states ms
            JOIN content_item ci ON ci.id = ms.content_item_id
            WHERE ms.user_id = ?
            AND ms.state = 'review'
            AND ms.stability >= 21
            AND ci.hsk_level IS NOT NULL
            GROUP BY ci.hsk_level
            ORDER BY ci.hsk_level
        """, (user_id,)).fetchall()
    except sqlite3.OperationalError:
        return {"hsk_estimate": 0.0, "items_mastered": 0, "coverage_pct": 0.0}

    # Estimate total items per HSK level from content_item corpus
    try:
        totals = conn.execute("""
            SELECT hsk_level, COUNT(*) as total
            FROM content_item
            WHERE status='drill_ready' AND hsk_level IS NOT NULL
            GROUP BY hsk_level
        """).fetchall()
    except sqlite3.OperationalError:
        totals = []

    total_by_level = {r["hsk_level"]: r["total"] for r in totals}
    mastered_by_level = {r["hsk_level"]: r["mastered"] for r in by_level}
    items_mastered = sum(mastered_by_level.values())

    hsk_estimate = 0.0
    for level in range(1, 10):
        total = total_by_level.get(level, 0)
        if total == 0:
            continue
        mastered = mastered_by_level.get(level, 0)
        coverage = mastered / total
        if coverage >= 0.80:
            hsk_estimate = level
        elif coverage >= 0.40:
            hsk_estimate = level - 1 + coverage

    coverage_at_estimate = 0.0
    est_level = max(1, round(hsk_estimate))
    if total_by_level.get(est_level, 0) > 0:
        coverage_at_estimate = (
            mastered_by_level.get(est_level, 0) / total_by_level[est_level]
        )

    return {
        "hsk_estimate": round(hsk_estimate, 1),
        "items_mastered": items_mastered,
        "coverage_pct": round(coverage_at_estimate * 100, 1),
    }


def _estimate_grammar_zone(conn: sqlite3.Connection, user_id: int) -> dict:
    """Estimate grammar HSK level from mastered patterns."""
    try:
        by_hsk = conn.execute("""
            SELECT gp.hsk_level, COUNT(*) as mastered
            FROM learner_pattern_states lps
            JOIN grammar_point gp ON gp.id = lps.grammar_point_id
            WHERE lps.user_id = ?
            AND lps.status = 'mastered'
            GROUP BY gp.hsk_level
        """, (user_id,)).fetchall()
    except sqlite3.OperationalError:
        return {"hsk_estimate": 0.0, "patterns_mastered": 0, "coverage_pct": 0.0}

    try:
        total_by_level_rows = conn.execute("""
            SELECT hsk_level, COUNT(*) as total
            FROM grammar_point
            WHERE hsk_level IS NOT NULL
            GROUP BY hsk_level
        """).fetchall()
    except sqlite3.OperationalError:
        total_by_level_rows = []

    total_lookup = {r["hsk_level"]: r["total"] for r in total_by_level_rows}
    mastered_lookup = {r["hsk_level"]: r["mastered"] for r in by_hsk}
    total_mastered = sum(mastered_lookup.values())

    hsk_estimate = 0.0
    for level in range(1, 10):
        total = total_lookup.get(level, 0)
        if total == 0:
            continue
        mastered = mastered_lookup.get(level, 0)
        if total > 0 and mastered / total >= 0.80:
            hsk_estimate = level

    est_level = max(1, round(hsk_estimate))
    coverage = 0.0
    if total_lookup.get(est_level, 0) > 0:
        coverage = mastered_lookup.get(est_level, 0) / total_lookup[est_level]

    return {
        "hsk_estimate": round(hsk_estimate, 1),
        "patterns_mastered": total_mastered,
        "coverage_pct": round(coverage * 100, 1),
    }


def _estimate_listening_zone(conn: sqlite3.Connection, user_id: int) -> dict:
    """Estimate listening level from audio drill performance."""
    try:
        audio_accuracy = conn.execute("""
            SELECT ci.hsk_level,
                   AVG(CASE WHEN re.correct=1 THEN 100.0 ELSE 0.0 END) as accuracy,
                   COUNT(*) as cnt
            FROM review_event re
            JOIN content_item ci ON ci.id = re.content_item_id
            WHERE re.user_id = ?
            AND re.modality = 'listening'
            AND re.created_at >= datetime('now','-30 days')
            AND ci.hsk_level IS NOT NULL
            GROUP BY ci.hsk_level
            HAVING COUNT(*) >= 10
        """, (user_id,)).fetchall()
    except sqlite3.OperationalError:
        return {"hsk_estimate": None, "confidence": "insufficient_data"}

    if not audio_accuracy:
        return {"hsk_estimate": None, "confidence": "insufficient_data"}

    highest_passing = 0.0
    for row in audio_accuracy:
        if row["hsk_level"] and row["accuracy"] >= 75.0:
            highest_passing = max(highest_passing, row["hsk_level"])

    return {
        "hsk_estimate": round(highest_passing, 1) if highest_passing > 0 else None,
        "confidence": "medium",
    }


def _compute_composite_hsk(vocab: dict, grammar: dict, listening: dict) -> float:
    """Composite HSK estimate. Vocab 50%, grammar 35%, listening 15%."""
    weights = {"vocab": 0.5, "grammar": 0.35, "listening": 0.15}

    total_weight = 0.0
    weighted_sum = 0.0

    if vocab.get("hsk_estimate"):
        weighted_sum += vocab["hsk_estimate"] * weights["vocab"]
        total_weight += weights["vocab"]
    if grammar.get("hsk_estimate"):
        weighted_sum += grammar["hsk_estimate"] * weights["grammar"]
        total_weight += weights["grammar"]
    if listening.get("hsk_estimate"):
        weighted_sum += listening["hsk_estimate"] * weights["listening"]
        total_weight += weights["listening"]

    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 1)


# ─────────────────────────────────────────────
# LEARNER MODEL CONTEXT GENERATION
# Serializes learner state for use in Qwen prompts.
# ─────────────────────────────────────────────

def get_learner_model_context(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Return structured learner knowledge state for Qwen prompts.

    All Qwen calls needing learner context should use this function
    instead of ad-hoc queries.
    """
    proficiency = conn.execute(
        "SELECT * FROM learner_proficiency_zones WHERE user_id=?",
        (user_id,),
    ).fetchone()

    try:
        mastered_patterns = conn.execute("""
            SELECT gp.name, gp.category, gp.hsk_level
            FROM learner_pattern_states lps
            JOIN grammar_point gp ON gp.id = lps.grammar_point_id
            WHERE lps.user_id = ?
            AND lps.status = 'mastered'
            ORDER BY gp.hsk_level
        """, (user_id,)).fetchall()
    except sqlite3.OperationalError:
        mastered_patterns = []

    try:
        acquiring_patterns = conn.execute("""
            SELECT gp.name, gp.category, lps.error_count_30d
            FROM learner_pattern_states lps
            JOIN grammar_point gp ON gp.id = lps.grammar_point_id
            WHERE lps.user_id = ?
            AND lps.status IN ('acquiring','consolidating')
            ORDER BY lps.error_count_30d DESC
            LIMIT 10
        """, (user_id,)).fetchall()
    except sqlite3.OperationalError:
        acquiring_patterns = []

    context = {
        "composite_hsk": proficiency["composite_hsk_estimate"] if proficiency else None,
        "vocab_hsk": proficiency["vocab_hsk_estimate"] if proficiency else None,
        "grammar_hsk": proficiency["grammar_hsk_estimate"] if proficiency else None,
        "mastered_patterns": [
            {"name": r["name"], "category": r["category"]}
            for r in mastered_patterns
        ],
        "active_patterns": [
            {"name": r["name"], "category": r["category"],
             "errors_30d": r["error_count_30d"]}
            for r in acquiring_patterns
        ],
    }

    # Cache snapshot
    try:
        conn.execute("""
            INSERT INTO learner_model_snapshots (user_id, snapshot)
            VALUES (?,?)
        """, (user_id, json.dumps(context, ensure_ascii=False)))
    except sqlite3.OperationalError:
        pass

    return context


# ─────────────────────────────────────────────
# TEACHER-FACING STUDENT INSIGHT
# ─────────────────────────────────────────────

def get_student_insight_for_teacher(
    conn: sqlite3.Connection,
    student_user_id: int,
) -> dict:
    """Structured learner model data for the teacher dashboard.

    FERPA access check must be performed before calling this function.
    """
    context = get_learner_model_context(conn, student_user_id)

    try:
        top_struggles = conn.execute("""
            SELECT gp.name, gp.category, lps.error_count_30d, lps.encounters
            FROM learner_pattern_states lps
            JOIN grammar_point gp ON gp.id = lps.grammar_point_id
            WHERE lps.user_id = ?
            AND lps.status = 'acquiring'
            ORDER BY lps.error_count_30d DESC, lps.encounters ASC
            LIMIT 3
        """, (student_user_id,)).fetchall()
    except sqlite3.OperationalError:
        top_struggles = []

    try:
        struggling_items = conn.execute("""
            SELECT ci.hanzi, ci.english, ms.lapses, ms.reps,
                   CAST(ms.lapses AS REAL)/ms.reps as lapse_rate
            FROM memory_states ms
            JOIN content_item ci ON ci.id = ms.content_item_id
            WHERE ms.user_id = ?
            AND ms.reps >= 5
            AND CAST(ms.lapses AS REAL)/ms.reps > 0.30
            ORDER BY lapse_rate DESC
            LIMIT 5
        """, (student_user_id,)).fetchall()
    except sqlite3.OperationalError:
        struggling_items = []

    return {
        "proficiency": {
            "composite_hsk": context["composite_hsk"],
            "vocab_hsk": context["vocab_hsk"],
            "grammar_hsk": context["grammar_hsk"],
        },
        "grammar_struggles": [
            {"pattern": r["name"], "category": r["category"],
             "recent_errors": r["error_count_30d"]}
            for r in top_struggles
        ],
        "vocabulary_struggles": [
            {"hanzi": r["hanzi"], "meaning": r["english"],
             "lapse_rate": round(r["lapse_rate"] * 100)}
            for r in struggling_items
        ],
        "teaching_priorities": _generate_teaching_priorities(top_struggles),
    }


def _generate_teaching_priorities(struggles) -> list[str]:
    """Generate specific actionable priorities for the teacher."""
    priorities = []
    for s in struggles[:2]:
        priorities.append(
            f"Review {s['name']} -- {s['error_count_30d']} errors in last 30 days"
        )
    return priorities


# ─────────────────────────────────────────────
# LEARNER MODEL ANALYZER
# Wired into audit cycle via intelligence/learner_audit.py
# ─────────────────────────────────────────────

def analyze_learner_model(conn: sqlite3.Connection) -> list[dict]:
    """Audit cycle analyzer for learner model health."""
    from ..intelligence._base import _finding

    findings = []

    # 1. Pattern states not updated in 7+ days for active learners
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT user_id) as cnt
            FROM learner_pattern_states
            WHERE last_updated_at < datetime('now','-7 days')
            AND status IN ('acquiring','consolidating')
        """).fetchone()
        stale_states = (row["cnt"] if row else 0) or 0

        if stale_states > 0:
            findings.append(_finding(
                dimension="learner_model",
                severity="medium",
                title=f"{stale_states} learner(s) with stale pattern states",
                analysis="Pattern states not updated in 7+ days for active acquiring patterns.",
                recommendation="Run update_pattern_avg_stability() and ensure review handler "
                               "calls update_pattern_state_from_review().",
                claude_prompt="Check learner_pattern_states for users with stale acquiring patterns.",
                impact="Stale pattern states degrade curriculum sequencing accuracy.",
                files=["mandarin/ai/learner_model.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # 2. Active learners without proficiency zone estimate
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT ms.user_id) as cnt
            FROM memory_states ms
            WHERE ms.reps >= 50
            AND NOT EXISTS (
                SELECT 1 FROM learner_proficiency_zones lpz
                WHERE lpz.user_id = ms.user_id
            )
        """).fetchone()
        no_proficiency = (row["cnt"] if row else 0) or 0

        if no_proficiency > 0:
            findings.append(_finding(
                dimension="learner_model",
                severity="low",
                title=f"{no_proficiency} active learner(s) without proficiency zone estimate",
                analysis="Learners with 50+ reviews should have proficiency zone estimates.",
                recommendation="Run estimate_proficiency_zones() for these users.",
                claude_prompt="Find users in memory_states with reps>=50 but no proficiency zone.",
                impact="Missing proficiency data limits curriculum personalization.",
                files=["mandarin/ai/learner_model.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # 3. Grammar points with no items tagged (HSK 1-4)
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM grammar_point gp
            WHERE gp.hsk_level <= 4
            AND NOT EXISTS (
                SELECT 1 FROM content_grammar cg
                WHERE cg.grammar_point_id = gp.id
            )
        """).fetchone()
        untagged = (row["cnt"] if row else 0) or 0

        if untagged > 0:
            findings.append(_finding(
                dimension="learner_model",
                severity="medium",
                title=f"{untagged} HSK 1-4 grammar point(s) with no items tagged",
                analysis="Grammar points with no linked content_items cannot be tracked "
                         "in the learner model.",
                recommendation="Tag approved items with grammar points via content_grammar.",
                claude_prompt="Find grammar_point rows with hsk_level<=4 and no content_grammar links.",
                impact="Untagged patterns create blind spots in the learner model.",
                files=["mandarin/ai/learner_model.py", "schema.sql"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings
