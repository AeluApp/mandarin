"""Progress tracking — SRS, attempts, mastery stages, error focus."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

from ..config import (
    EASE_FLOOR, EASE_CORRECT_BOOST, EASE_WRONG_PENALTY,
    EASE_NARROWED_PENALTY, EASE_HALF_PENALTY,
    INTERVAL_INITIAL, INTERVAL_SECOND, INTERVAL_WRONG,
    INTERVAL_NARROWED_MULT, INTERVAL_HALF_MULT,
    STREAK_STABLE_THRESHOLD, STREAK_STABLE_MULT,
    STREAK_EXTENDED_THRESHOLD, STREAK_EXTENDED_MULT,
    MAX_INTERVAL,
    PROMOTE_PASSED_ONCE_STREAK, PROMOTE_STABILIZING_STREAK,
    PROMOTE_STABILIZING_DAYS, PROMOTE_STABLE_STREAK,
    PROMOTE_STABLE_ATTEMPTS, PROMOTE_STABLE_DRILL_TYPES,
    PROMOTE_STABLE_DAYS, PROMOTE_DURABLE_DAYS_STABLE,
    PROMOTE_DURABLE_SUCCESSES,
    DEMOTE_STABLE_STREAK_INCORRECT, DEMOTE_STABILIZING_STREAK_INCORRECT,
    DEMOTE_WEAK_CYCLE_THRESHOLD,
    RECOVERY_STREAK_CORRECT,
    DIFFICULTY_HALF_WRONG_PENALTY,
    INITIAL_HALF_LIFE,
    PARTIAL_CONFIDENCE_DAMPEN,
    CONFIDENCE_DAMPEN,
)


DRILL_DIRECTION_MAP = {
    "mc": "hanzi_to_en",
    "reverse_mc": "en_to_hanzi",
    "english_to_pinyin": "en_to_pinyin",
    "listening_gist": "pinyin_to_en",
    "listening_detail": "pinyin_to_en",
    "listening_tone": "pinyin_to_pinyin",
    "listening_dictation": "pinyin_to_hanzi",
    "hanzi_to_pinyin": "hanzi_to_pinyin",
    "pinyin_to_hanzi": "pinyin_to_hanzi",
    "tone": "hanzi_to_pinyin",
    "ime_type": "hanzi_to_pinyin",
    "intuition": "en_to_hanzi",
    "register_choice": None,
    "pragmatic": None,
    "slang_exposure": None,
    "speaking": None,
    "transfer": None,
    "measure_word": "hanzi_to_en",
    "word_order": "en_to_hanzi",
    "sentence_build": "en_to_hanzi",
    "particle_disc": "hanzi_to_hanzi",
    "homophone": "hanzi_to_hanzi",
}


_VALID_MODALITIES = {"reading", "listening", "speaking", "ime"}
_VALID_CONFIDENCES = {"full", "half", "unknown", "narrowed", "narrowed_wrong"}


def _compute_srs_update(row: dict, correct: bool, confidence: str,
                        response_ms: int, mastery_stage: str) -> dict:
    """Compute SM-2 ease/interval/reps/streaks from current state.

    Pure function — no DB access, no side effects.

    Returns dict with keys:
        ease, interval, reps, streak_correct, streak_incorrect, next_review
    """
    from datetime import timedelta

    ease = row["ease_factor"]
    interval = row["interval_days"]
    reps = row["repetitions"]

    if confidence in ("unknown", "narrowed_wrong"):
        interval = INTERVAL_INITIAL
        streak_correct = row["streak_correct"]
        streak_incorrect = row["streak_incorrect"]
    elif confidence == "narrowed":
        interval = max(INTERVAL_INITIAL, interval * INTERVAL_NARROWED_MULT)
        ease = max(EASE_FLOOR, ease - EASE_NARROWED_PENALTY)
        streak_correct = row["streak_correct"]
        streak_incorrect = row["streak_incorrect"]
    elif confidence == "half":
        reps = max(0, reps - 1)
        interval = max(INTERVAL_INITIAL, interval * INTERVAL_HALF_MULT)
        ease = max(EASE_FLOOR, ease - EASE_HALF_PENALTY)
        streak_correct = row["streak_correct"]
        streak_incorrect = row["streak_incorrect"]
    elif correct:
        if reps == 0:
            interval = INTERVAL_INITIAL
        elif reps == 1:
            interval = INTERVAL_SECOND
        else:
            interval = interval * ease
        reps += 1
        ease = max(EASE_FLOOR, ease + EASE_CORRECT_BOOST)
        streak_correct = row["streak_correct"] + 1
        streak_incorrect = 0

        # Streak cap: push well-known stable/durable items further out
        # Use elif to prevent compounding (was ×1.3 × ×1.2 = ×1.56)
        if streak_correct >= STREAK_EXTENDED_THRESHOLD:
            interval *= STREAK_EXTENDED_MULT
        elif streak_correct >= STREAK_STABLE_THRESHOLD and mastery_stage in ('stable', 'durable'):
            interval *= STREAK_STABLE_MULT
    else:
        reps = 0
        interval = INTERVAL_WRONG
        ease = max(EASE_FLOOR, ease - EASE_WRONG_PENALTY)
        streak_correct = 0
        streak_incorrect = row["streak_incorrect"] + 1

    # Cap interval to MAX_INTERVAL to prevent unbounded scheduling
    interval = min(interval, MAX_INTERVAL)

    next_review = (datetime.now(timezone.utc) + timedelta(days=interval)).date().isoformat()

    return {
        "ease": ease,
        "interval": interval,
        "reps": reps,
        "streak_correct": streak_correct,
        "streak_incorrect": streak_incorrect,
        "next_review": next_review,
    }


def _compute_mastery_transition(row: dict, correct: bool, confidence: str,
                                streak_correct: int, streak_incorrect: int,
                                drill_type: str, distinct_days: int,
                                total_after: int, drill_type_count: int,
                                modality_count: int = 1) -> dict:
    """Compute 6-stage mastery model transitions.

    Pure function — no DB access, no side effects.

    Streak and attempt thresholds scale with item difficulty (easy items
    need less evidence, hard items need more). The diversity criterion
    combines drill type breadth and modality breadth.

    Returns dict with keys:
        mastery_stage, historically_weak, weak_cycle_count,
        stable_since_date, successes_while_stable
    """
    today = date.today().isoformat()
    mastery_stage = row.get("mastery_stage") or "seen"

    # Remap legacy stages
    if mastery_stage == "weak":
        mastery_stage = "seen"
    elif mastery_stage == "improving":
        mastery_stage = "stabilizing"

    historically_weak = row.get("historically_weak") or 0
    weak_cycle_count = row.get("weak_cycle_count") or 0
    stable_since_date = row.get("stable_since_date")
    successes_while_stable = row.get("successes_while_stable") or 0

    # ── Promotion path ──
    # Require full confidence for promotions — narrowed/half answers don't count
    full_conf = confidence in ("full", None)
    if mastery_stage == "seen" and streak_correct >= PROMOTE_PASSED_ONCE_STREAK and full_conf:
        mastery_stage = "passed_once"
    if mastery_stage == "passed_once" and streak_correct >= PROMOTE_STABILIZING_STREAK and distinct_days >= PROMOTE_STABILIZING_DAYS and full_conf:
        mastery_stage = "stabilizing"
    if mastery_stage == "stabilizing":
        # Conjunctive mastery gate: 4 criteria, each normalized to [0, 1].
        # Equal weighting is intentional — each criterion is necessary, not
        # substitutable. Streak tests recall consistency, attempts test volume,
        # diversity tests transfer across contexts and modalities, days test
        # long-term retention across sessions. Gate at 3.6/4.0 (90%) means
        # all criteria must be substantially met; one weak area can be offset
        # slightly but not compensated entirely. Hard minimums (streak, days)
        # prevent degenerate cases where one maxed criterion carries three zeros.
        #
        # Streak and attempt thresholds scale with item difficulty: easy items
        # need less evidence to promote, hard items need more.
        difficulty = row.get("difficulty") or 0.5
        diff_scale = 0.5 + difficulty  # Range: 0.5 (easy) to 1.5 (hard)
        scaled_streak = max(3, round(PROMOTE_STABLE_STREAK * diff_scale))
        scaled_attempts = max(5, round(PROMOTE_STABLE_ATTEMPTS * diff_scale))

        # Combined diversity: both drill types AND modalities must show breadth
        diversity = min(1.0, drill_type_count / PROMOTE_STABLE_DRILL_TYPES) * 0.5 \
                  + min(1.0, modality_count / 2) * 0.5
        gate_score = (
            min(1.0, streak_correct / scaled_streak)
            + min(1.0, total_after / scaled_attempts)
            + diversity
            + min(1.0, distinct_days / PROMOTE_STABLE_DAYS)
        )
        if (gate_score >= 3.6
                and streak_correct >= scaled_streak - 1
                and distinct_days >= PROMOTE_STABLE_DAYS - 1):
            mastery_stage = "stable"
            stable_since_date = today
            successes_while_stable = 0
    if mastery_stage == "stable" and correct and confidence in ("full", None):
        successes_while_stable += 1
    if mastery_stage == "stable" and stable_since_date:
        try:
            stable_date = date.fromisoformat(stable_since_date)
            days_stable = (date.today() - stable_date).days
            if days_stable >= PROMOTE_DURABLE_DAYS_STABLE and successes_while_stable >= PROMOTE_DURABLE_SUCCESSES:
                mastery_stage = "durable"
        except (ValueError, TypeError):
            pass
    if mastery_stage == "durable" and correct and confidence in ("full", None):
        successes_while_stable += 1

    # ── Demotion path (graduated) ──
    # Items with strong history (many correct answers) are harder to demote.
    # Base threshold: 3 consecutive wrong. Per 20 correct beyond 10: +1 (max 6).
    total_correct = row.get("total_correct") or 0
    demotion_threshold = DEMOTE_STABLE_STREAK_INCORRECT + min(
        3, max(0, (total_correct - 10) // 20)
    )
    if mastery_stage in ("stable", "durable") and streak_incorrect >= demotion_threshold:
        mastery_stage = "decayed"
        stable_since_date = None
        successes_while_stable = 0
    elif mastery_stage == "stabilizing" and streak_incorrect >= DEMOTE_STABILIZING_STREAK_INCORRECT:
        mastery_stage = "seen"
        weak_cycle_count += 1
        if weak_cycle_count >= DEMOTE_WEAK_CYCLE_THRESHOLD:
            historically_weak = 1

    # ── Recovery path ──
    if mastery_stage == "decayed" and streak_correct >= RECOVERY_STREAK_CORRECT:
        mastery_stage = "stabilizing"

    return {
        "mastery_stage": mastery_stage,
        "historically_weak": historically_weak,
        "weak_cycle_count": weak_cycle_count,
        "stable_since_date": stable_since_date,
        "successes_while_stable": successes_while_stable,
    }


def _compute_retention_update(row: dict, correct: bool,
                              confidence: str, modality: str = None) -> dict:
    """Compute half-life regression update.

    Pure function — no DB access, no side effects.

    Returns dict with keys: half_life, difficulty, p_recall
    """
    from ..retention import predict_recall, update_half_life, update_difficulty

    old_hl = row.get("half_life_days") or INITIAL_HALF_LIFE
    old_diff = row.get("difficulty") or 0.5
    last_reviewed = row.get("last_review_date")

    if last_reviewed:
        try:
            review_date = date.fromisoformat(last_reviewed[:10])
            days_since = max(0, (date.today() - review_date).days)
        except (ValueError, TypeError):
            days_since = 1.0
    else:
        days_since = 1.0

    p_recall = predict_recall(old_hl, days_since)

    if confidence in ("full", None):
        new_hl = update_half_life(old_hl, correct, days_since, old_diff)
        new_diff = update_difficulty(old_diff, correct, p_recall)
    elif confidence in ("half", "narrowed"):
        # Dampened update — partial signal still informs the model
        dampen = CONFIDENCE_DAMPEN.get(confidence, 0.5)
        full_hl = update_half_life(old_hl, correct, days_since, old_diff)
        full_diff = update_difficulty(old_diff, correct, p_recall)
        new_hl = old_hl + (full_hl - old_hl) * dampen
        new_diff = old_diff + (full_diff - old_diff) * dampen
    else:
        # unknown, narrowed_wrong — treat as failed recall with harsh dampening
        dampen = CONFIDENCE_DAMPEN.get(confidence, 0.15)
        full_hl = update_half_life(old_hl, False, days_since, old_diff)
        full_diff = update_difficulty(old_diff, False, p_recall)
        new_hl = old_hl + (full_hl - old_hl) * dampen
        new_diff = old_diff + (full_diff - old_diff) * dampen

    # Modality-specific decay multipliers removed — half-life update mechanism
    # captures modality differences naturally through the feedback loop.

    return {
        "half_life": new_hl,
        "difficulty": new_diff,
        "p_recall": p_recall,
    }


def _update_attempt_counts(conn: sqlite3.Connection, item_id: int,
                           modality: str, correct: bool,
                           response_ms: int, drill_type: str,
                           user_id: int = 1) -> dict:
    """Upsert progress row, update content_item counters, compute derived fields.

    Returns dict with keys: row, drill_direction, today, distinct_days,
    types_set, drill_type_count, total_after, new_avg_ms.
    """
    drill_direction = DRILL_DIRECTION_MAP.get(drill_type) if drill_type else None

    # Upsert progress row
    conn.execute("""
        INSERT INTO progress (user_id, content_item_id, modality)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, content_item_id, modality) DO NOTHING
    """, (user_id, item_id, modality))

    # Fetch current state
    row = conn.execute("""
        SELECT * FROM progress
        WHERE user_id = ? AND content_item_id = ? AND modality = ?
    """, (user_id, item_id, modality)).fetchone()
    row = dict(row)

    today = date.today().isoformat()

    # Track distinct review days
    distinct_days = row.get("distinct_review_days") or 0
    last_reviewed = row.get("last_review_date")
    if last_reviewed != today:
        distinct_days += 1

    # Count distinct drill types seen
    existing_types = row.get("drill_types_seen") or ""
    types_set = set(existing_types.split(",")) if existing_types else set()
    if drill_type:
        types_set.discard("")
        types_set.add(drill_type)
    drill_type_count = len(types_set)
    total_after = row["total_attempts"] + 1

    # Update avg_response_ms (rolling average)
    old_avg_ms = row.get("avg_response_ms")
    if response_ms is not None and response_ms > 0:
        if old_avg_ms and row["total_attempts"] > 0:
            new_avg_ms = old_avg_ms * 0.7 + response_ms * 0.3
        else:
            new_avg_ms = float(response_ms)
    else:
        new_avg_ms = old_avg_ms

    # Update content_item counters
    conn.execute("""
        UPDATE content_item SET
            times_shown = times_shown + 1,
            times_correct = times_correct + ?
        WHERE id = ?
    """, (1 if correct else 0, item_id))

    return {
        "row": row,
        "drill_direction": drill_direction,
        "today": today,
        "distinct_days": distinct_days,
        "types_set": types_set,
        "drill_type_count": drill_type_count,
        "total_after": total_after,
        "new_avg_ms": new_avg_ms,
    }


def _update_srs_state(conn: sqlite3.Connection, row: dict, correct: bool,
                      confidence: str, response_ms: int,
                      mastery_stage: str) -> dict:
    """Compute SRS update via _compute_srs_update.

    Returns the SRS result dict (ease, interval, reps, streaks, next_review).
    """
    return _compute_srs_update(row, correct, confidence, response_ms, mastery_stage)


def _update_mastery(conn: sqlite3.Connection, row: dict, correct: bool,
                    confidence: str, drill_type: str,
                    streak_correct: int, streak_incorrect: int,
                    distinct_days: int, total_after: int,
                    drill_type_count: int,
                    modality_count: int = 1) -> dict:
    """Compute mastery transition via _compute_mastery_transition.

    Returns the mastery result dict (mastery_stage, historically_weak, etc.).
    """
    return _compute_mastery_transition(
        row, correct, confidence, streak_correct, streak_incorrect,
        drill_type, distinct_days, total_after, drill_type_count,
        modality_count=modality_count,
    )


def _update_retention(conn: sqlite3.Connection, row: dict, correct: bool,
                      confidence: str, modality: str) -> dict:
    """Compute retention update via _compute_retention_update.

    Returns the retention result dict (half_life, difficulty, p_recall).
    """
    return _compute_retention_update(row, correct, confidence, modality=modality)


def _log_error(conn: sqlite3.Connection, item_id: int, session_id: int,
               modality: str, error_type: str, user_answer: str,
               expected: str, drill_type: str,
               user_id: int = 1) -> None:
    """Log an incorrect attempt to error_log and update error_focus."""
    if error_type:
        conn.execute("""
            INSERT INTO error_log
                (user_id, session_id, content_item_id, modality, error_type,
                 user_answer, expected_answer, drill_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, session_id, item_id, modality, error_type,
              user_answer, expected, drill_type))

    try:
        update_error_focus(conn, item_id, error_type or "other", False, user_id=user_id)
    except sqlite3.Error:
        logger.debug("error_focus update failed (table may be missing)", exc_info=True)


def record_attempt(conn: sqlite3.Connection, content_item_id: int,
                   modality: str, correct: bool,
                   session_id: int = None,
                   error_type: str = None,
                   user_answer: str = None,
                   expected_answer: str = None,
                   drill_type: str = None,
                   confidence: str = "full",
                   response_ms: int = None,
                   user_id: int = 1) -> None:
    """Record an attempt, update SRS, log errors.

    Orchestrates helpers: _update_attempt_counts, _update_srs_state,
    _update_mastery, _update_retention, _log_error.

    confidence: "full" (normal), "half" (50/50 — softer penalty),
                "unknown" (admitted — no penalty, review sooner),
                "narrowed" (got it right from 2 choices — limited credit),
                "narrowed_wrong" (missed even with 2 choices — review soon)
    """
    assert modality in _VALID_MODALITIES, f"invalid modality: {modality!r}"
    assert confidence in _VALID_CONFIDENCES, f"invalid confidence: {confidence!r}"
    assert isinstance(content_item_id, int) and content_item_id > 0, \
        f"content_item_id must be positive int, got {content_item_id!r}"

    # 1. Upsert progress row, update counters, compute derived fields
    ctx = _update_attempt_counts(conn, content_item_id, modality, correct,
                                 response_ms, drill_type, user_id=user_id)
    row = ctx["row"]
    mastery_stage = row.get("mastery_stage") or "seen"

    # 2. SRS update (ease, interval, streaks)
    srs = _update_srs_state(conn, row, correct, confidence, response_ms, mastery_stage)

    # 2b. Compute modality diversity for mastery gate
    mod_row = conn.execute("""
        SELECT COUNT(DISTINCT modality) as mod_count FROM progress
        WHERE content_item_id = ? AND user_id = ?
    """, (content_item_id, user_id)).fetchone()
    modality_count = mod_row["mod_count"] if mod_row else 1

    # 3. Mastery transition
    mastery = _update_mastery(conn, row, correct, confidence, drill_type,
                              srs["streak_correct"], srs["streak_incorrect"],
                              ctx["distinct_days"], ctx["total_after"],
                              ctx["drill_type_count"],
                              modality_count=modality_count)

    # 4. Retention update (half-life, difficulty, p_recall)
    ret = _update_retention(conn, row, correct, confidence, modality)

    # 5. Apply all updates to progress row
    new_types_str = ",".join(sorted(ctx["types_set"]))
    conn.execute("""
        UPDATE progress SET
            ease_factor = ?, interval_days = ?, repetitions = ?,
            next_review_date = ?, last_review_date = ?,
            total_attempts = total_attempts + 1,
            total_correct = total_correct + ?,
            streak_correct = ?, streak_incorrect = ?,
            drill_direction = COALESCE(?, drill_direction),
            mastery_stage = ?,
            historically_weak = ?,
            weak_cycle_count = ?,
            avg_response_ms = ?,
            drill_types_seen = ?,
            distinct_review_days = ?,
            half_life_days = ?,
            difficulty = ?,
            last_p_recall = ?,
            stable_since_date = ?,
            successes_while_stable = ?
        WHERE user_id = ? AND content_item_id = ? AND modality = ?
    """, (srs["ease"], srs["interval"], srs["reps"],
          srs["next_review"], ctx["today"],
          1 if correct else 0,
          srs["streak_correct"], srs["streak_incorrect"],
          ctx["drill_direction"],
          mastery["mastery_stage"], mastery["historically_weak"],
          mastery["weak_cycle_count"],
          ctx["new_avg_ms"], new_types_str, ctx["distinct_days"],
          ret["half_life"], ret["difficulty"], round(ret["p_recall"], 3),
          mastery["stable_since_date"], mastery["successes_while_stable"],
          user_id, content_item_id, modality))

    # 6. Log error if incorrect
    if not correct:
        _log_error(conn, content_item_id, session_id, modality,
                   error_type, user_answer, expected_answer, drill_type,
                   user_id=user_id)
    else:
        # Update error focus for correct answers (may resolve errors)
        try:
            update_error_focus(conn, content_item_id, error_type or "other", True,
                               user_id=user_id)
        except sqlite3.Error:
            logger.debug("error_focus update failed (table may be missing)", exc_info=True)

    conn.commit()


def update_error_focus(conn: sqlite3.Connection, content_item_id: int,
                       error_type: str, correct: bool,
                       user_id: int = 1) -> None:
    """Update error_focus tracking after an attempt."""
    if not error_type:
        error_type = "other"

    if not correct:
        conn.execute("""
            INSERT INTO error_focus (user_id, content_item_id, error_type)
            VALUES (?, ?, ?)
            ON CONFLICT(content_item_id, error_type) DO UPDATE SET
                error_count = error_count + 1,
                consecutive_correct = 0,
                last_error_at = datetime('now'),
                resolved = 0,
                resolved_at = NULL
        """, (user_id, content_item_id, error_type))
    else:
        row = conn.execute("""
            SELECT id, consecutive_correct FROM error_focus
            WHERE content_item_id = ? AND error_type = ? AND user_id = ? AND resolved = 0
        """, (content_item_id, error_type, user_id)).fetchone()
        if row:
            new_consec = (row["consecutive_correct"] or 0) + 1
            if new_consec >= 3:
                conn.execute("""
                    UPDATE error_focus SET
                        consecutive_correct = ?,
                        resolved = 1,
                        resolved_at = datetime('now')
                    WHERE id = ?
                """, (new_consec, row["id"]))
            else:
                conn.execute("""
                    UPDATE error_focus SET consecutive_correct = ?
                    WHERE id = ?
                """, (new_consec, row["id"]))


def get_error_focus_items(conn: sqlite3.Connection, limit: int = 3,
                          user_id: int = 1) -> list[dict]:
    """Get unresolved error-focus items for priority scheduling."""
    rows = conn.execute("""
        SELECT ci.*, ef.error_type as focus_error_type, ef.error_count
        FROM error_focus ef
        JOIN content_item ci ON ef.content_item_id = ci.id
        WHERE ef.resolved = 0 AND ef.user_id = ?
        ORDER BY ef.error_count DESC, ef.last_error_at DESC
        LIMIT ?
    """, (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def get_resolved_this_session(conn: sqlite3.Connection, session_id: int,
                              user_id: int = 1) -> list[dict]:
    """Get error_focus items resolved during the current session timeframe."""
    row = conn.execute(
        "SELECT started_at FROM session_log WHERE id = ?", (session_id,)
    ).fetchone()
    if not row:
        return []

    rows = conn.execute("""
        SELECT ci.hanzi, ef.error_type
        FROM error_focus ef
        JOIN content_item ci ON ef.content_item_id = ci.id
        WHERE ef.resolved = 1 AND ef.resolved_at >= ? AND ef.user_id = ?
    """, (row["started_at"], user_id)).fetchall()
    return [dict(r) for r in rows]


def get_stage_transitions(conn: sqlite3.Connection, session_id: int,
                          user_id: int = 1) -> list[dict]:
    """Get items whose mastery stage changed during this session.

    Detects transitions by comparing current mastery_stage against
    what it would have been before the session's attempts.

    Returns list of {"hanzi": str, "from": str, "to": str}.
    """
    # Get all items attempted this session with their current stage
    rows = conn.execute("""
        SELECT DISTINCT ci.hanzi, p.mastery_stage, p.streak_correct,
               p.streak_incorrect, p.total_attempts
        FROM error_log el
        JOIN content_item ci ON el.content_item_id = ci.id
        JOIN progress p ON p.content_item_id = ci.id AND p.user_id = ?
        WHERE el.session_id = ? AND el.user_id = ?

        UNION

        SELECT DISTINCT ci.hanzi, p.mastery_stage, p.streak_correct,
               p.streak_incorrect, p.total_attempts
        FROM progress p
        JOIN content_item ci ON ci.id = p.content_item_id
        WHERE p.last_review_date = ? AND p.user_id = ?
    """, (user_id, session_id, user_id, date.today().isoformat(), user_id)).fetchall()

    # Use a simpler approach: find items where current stage differs from
    # what we'd expect if they hadn't improved. We detect "improving" and
    # "stable" items that were recently at lower stages based on their
    # streak lengths and total attempts.
    transitions = []
    for r in rows:
        stage = r["mastery_stage"] or "seen"
        streak_c = r["streak_correct"] or 0
        streak_i = r["streak_incorrect"] or 0
        total = r["total_attempts"] or 0

        # Detect likely recent transitions based on streak proximity to thresholds
        if stage == "passed_once" and streak_c == 1:
            transitions.append({
                "hanzi": r["hanzi"],
                "from": "seen",
                "to": "passed_once",
            })
        elif stage == "stabilizing" and 3 <= streak_c <= 5:
            transitions.append({
                "hanzi": r["hanzi"],
                "from": "passed_once",
                "to": "stabilizing",
            })
        elif stage == "stable" and streak_c >= 6 and total <= 12:
            transitions.append({
                "hanzi": r["hanzi"],
                "from": "stabilizing",
                "to": "stable",
            })
        elif stage == "decayed" and streak_i >= 2 and streak_i <= 3:
            transitions.append({
                "hanzi": r["hanzi"],
                "from": "stable",
                "to": "decayed",
            })

    return transitions


def get_items_due_count(conn: sqlite3.Connection, user_id: int = 1) -> int:
    """Count items due for review today or earlier."""
    today = date.today().isoformat()
    row = conn.execute("""
        SELECT COUNT(DISTINCT content_item_id) as cnt
        FROM progress WHERE next_review_date <= ? AND user_id = ?
    """, (today, user_id)).fetchone()
    return row["cnt"] if row else 0


def get_new_items_available(conn: sqlite3.Connection, user_id: int = 1) -> int:
    """Count drill-ready items never attempted."""
    row = conn.execute("""
        SELECT COUNT(*) as cnt FROM content_item ci
        WHERE ci.status = 'drill_ready'
          AND NOT EXISTS (
              SELECT 1 FROM progress p
              WHERE p.content_item_id = ci.id AND p.total_attempts > 0
                AND p.user_id = ?
          )
    """, (user_id,)).fetchone()
    return row["cnt"] if row else 0


def get_mastery_by_hsk(conn: sqlite3.Connection, user_id: int = 1) -> dict[int, dict]:
    """Return mastery stats per HSK level."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(progress)").fetchall()}
    has_stages = "mastery_stage" in cols

    if has_stages:
        rows = conn.execute("""
            SELECT ci.hsk_level,
                   COUNT(DISTINCT ci.id) as total,
                   COUNT(DISTINCT CASE WHEN p.total_attempts > 0 THEN ci.id END) as seen,
                   COUNT(DISTINCT CASE WHEN p.mastery_stage = 'seen' THEN ci.id END) as seen_stage,
                   COUNT(DISTINCT CASE WHEN p.mastery_stage = 'passed_once' THEN ci.id END) as passed_once,
                   COUNT(DISTINCT CASE WHEN p.mastery_stage = 'stabilizing' THEN ci.id END) as stabilizing,
                   COUNT(DISTINCT CASE WHEN p.mastery_stage = 'stable' THEN ci.id END) as stable,
                   COUNT(DISTINCT CASE WHEN p.mastery_stage = 'durable' THEN ci.id END) as durable,
                   COUNT(DISTINCT CASE WHEN p.mastery_stage = 'decayed' THEN ci.id END) as decayed
            FROM content_item ci
            LEFT JOIN progress p ON ci.id = p.content_item_id AND p.user_id = ?
            WHERE ci.status = 'drill_ready' AND ci.hsk_level IS NOT NULL
            GROUP BY ci.hsk_level
            ORDER BY ci.hsk_level
        """, (user_id,)).fetchall()
        result = {}
        for r in rows:
            total = r["total"]
            seen = r["seen"] or 0
            stable = (r["stable"] or 0) + (r["durable"] or 0)
            stabilizing = r["stabilizing"] or 0
            mastered = stable  # Only stable+durable count as mastered
            result[r["hsk_level"]] = {
                "total": total,
                "mastered": mastered,
                "pct": (mastered / total * 100) if total > 0 else 0,
                "seen": seen,
                "not_seen": total - seen,
                "stable": r["stable"] or 0,
                "durable": r["durable"] or 0,
                "stabilizing": stabilizing,
                "passed_once": r["passed_once"] or 0,
                "seen_stage": r["seen_stage"] or 0,
                "decayed": r["decayed"] or 0,
                # Backward compat aliases
                "improving": stabilizing,
                "weak": (r["seen_stage"] or 0) + (r["passed_once"] or 0),
            }
        return result

    # Fallback for pre-V3 databases
    rows = conn.execute("""
        SELECT ci.hsk_level,
               COUNT(DISTINCT ci.id) as total,
               COUNT(DISTINCT CASE WHEN p.total_attempts > 0 THEN ci.id END) as seen,
               COUNT(DISTINCT CASE WHEN p.streak_correct >= 3 THEN ci.id END) as mastered
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.user_id = ?
        WHERE ci.status = 'drill_ready' AND ci.hsk_level IS NOT NULL
        GROUP BY ci.hsk_level
        ORDER BY ci.hsk_level
    """, (user_id,)).fetchall()
    result = {}
    for r in rows:
        total = r["total"]
        seen = r["seen"] or 0
        mastered = r["mastered"] or 0
        result[r["hsk_level"]] = {
            "total": total,
            "mastered": mastered,
            "pct": (mastered / total * 100) if total > 0 else 0,
            "seen": seen,
            "not_seen": total - seen,
        }
    return result
