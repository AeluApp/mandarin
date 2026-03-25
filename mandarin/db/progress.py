"""Progress tracking — SRS, attempts, mastery stages, error focus."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, date, timezone, UTC
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
    REQUIRE_PRODUCTION_FOR_STABLE,
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


# Production drill types: learner must produce output, not just recognize.
# Derived from DRILL_DIRECTION_MAP — directions where the target is hanzi or pinyin output.
PRODUCTION_DRILL_TYPES = {
    "reverse_mc", "english_to_pinyin", "listening_dictation",
    "pinyin_to_hanzi", "ime_type", "intuition", "speaking",
    "word_order", "sentence_build",
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

    # LECTOR-style: shorten intervals for items with many interference neighbors.
    # High-density items need more frequent review to maintain distinctiveness.
    interference_density = row.get("interference_density") or 0.0
    if interference_density > 0 and correct:
        # At most 30% shorter interval for maximally confusable items
        density_mult = 1.0 - (0.3 * min(interference_density, 1.0))
        interval *= density_mult

    # Cap interval to MAX_INTERVAL to prevent unbounded scheduling
    interval = min(interval, MAX_INTERVAL)

    next_review = (datetime.now(UTC) + timedelta(days=interval)).date().isoformat()

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
                                modality_count: int = 1,
                                has_production_correct: bool = False) -> dict:
    """Compute 6-stage mastery model transitions.

    Pure function — no DB access, no side effects.

    Streak and attempt thresholds scale with item difficulty (easy items
    need less evidence, hard items need more). The diversity criterion
    combines drill type breadth and modality breadth.

    If REQUIRE_PRODUCTION_FOR_STABLE is True, the item must have at least
    one correct attempt in a production drill type before promoting to stable.

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
        # Production gate: require at least 1 correct production drill
        production_met = (not REQUIRE_PRODUCTION_FOR_STABLE) or has_production_correct
        if (gate_score >= 3.6
                and streak_correct >= scaled_streak - 1
                and distinct_days >= PROMOTE_STABLE_DAYS - 1
                and production_met):
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
                    modality_count: int = 1,
                    has_production_correct: bool = False) -> dict:
    """Compute mastery transition via _compute_mastery_transition.

    Returns the mastery result dict (mastery_stage, historically_weak, etc.).
    """
    return _compute_mastery_transition(
        row, correct, confidence, streak_correct, streak_incorrect,
        drill_type, distinct_days, total_after, drill_type_count,
        modality_count=modality_count,
        has_production_correct=has_production_correct,
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
               user_id: int = 1, metadata: dict = None,
               error_cause: str = None) -> None:
    """Log an incorrect attempt to error_log, update error_focus & error shapes."""
    if error_type:
        # Extract tone confusion data from metadata when available
        tone_user = None
        tone_expected = None
        if metadata and error_type == "tone":
            tone_user = metadata.get("tone_user")
            tone_expected = metadata.get("tone_expected")

        try:
            conn.execute("""
                INSERT INTO error_log
                    (user_id, session_id, content_item_id, modality, error_type,
                     user_answer, expected_answer, drill_type, tone_user, tone_expected,
                     error_cause)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, session_id, item_id, modality, error_type,
                  user_answer, expected, drill_type, tone_user, tone_expected,
                  error_cause))
        except sqlite3.OperationalError:
            # Fallback for DBs without error_cause column yet
            conn.execute("""
                INSERT INTO error_log
                    (user_id, session_id, content_item_id, modality, error_type,
                     user_answer, expected_answer, drill_type, tone_user, tone_expected)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, session_id, item_id, modality, error_type,
                  user_answer, expected, drill_type, tone_user, tone_expected))

    # Persist detailed error shape for cross-session tracking
    if error_cause:
        try:
            conn.execute("""
                INSERT INTO error_shape_summary
                    (user_id, content_item_id, error_shape)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, content_item_id, error_shape) DO UPDATE SET
                    occurrence_count = occurrence_count + 1,
                    last_seen_at = datetime('now'),
                    consecutive_correct = 0,
                    resolved = 0,
                    resolved_at = NULL
            """, (user_id, item_id, error_cause))
        except sqlite3.OperationalError:
            pass  # Table not yet migrated

    # Auto-detect interference pairs from MC confusion patterns
    if error_type and drill_type in ("mc", "reverse_mc", "pinyin_to_hanzi"):
        try:
            _detect_confusion_pair(conn, item_id, user_answer, drill_type, user_id)
        except Exception:
            logger.debug("confusion pair detection failed", exc_info=True)

    try:
        update_error_focus(conn, item_id, error_type or "other", False, user_id=user_id)
    except sqlite3.Error:
        logger.debug("error_focus update failed (table may be missing)", exc_info=True)


def record_attempt(conn: sqlite3.Connection, content_item_id: int,
                   modality: str, correct: bool,
                   session_id: int = None,
                   error_type: str = None,
                   error_cause: str = None,
                   user_answer: str = None,
                   expected_answer: str = None,
                   drill_type: str = None,
                   confidence: str = "full",
                   response_ms: int = None,
                   user_id: int = 1,
                   metadata: dict = None) -> None:
    """Record an attempt, update SRS, log errors.

    Orchestrates helpers: _update_attempt_counts, _update_srs_state,
    _update_mastery, _update_retention, _log_error.

    confidence: "full" (normal), "half" (50/50 — softer penalty),
                "unknown" (admitted — no penalty, review sooner),
                "narrowed" (got it right from 2 choices — limited credit),
                "narrowed_wrong" (missed even with 2 choices — review soon)
    """
    if modality not in _VALID_MODALITIES:
        logger.error("record_attempt: invalid modality %r, defaulting to 'reading'", modality)
        modality = "reading"
    if confidence not in _VALID_CONFIDENCES:
        logger.error("record_attempt: invalid confidence %r, defaulting to 'full'", confidence)
        confidence = "full"
    if not isinstance(content_item_id, int) or content_item_id <= 0:
        logger.error("record_attempt: bad content_item_id %r, skipping", content_item_id)
        return

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

    # 2c. Check if item has any correct production drill in its history.
    # Current drill counts if it's production and correct.
    has_production_correct = (correct and drill_type in PRODUCTION_DRILL_TYPES)
    if not has_production_correct:
        # Check historical drill_types_seen for any production type with correct attempts
        existing_types = ctx["types_set"]
        if existing_types & PRODUCTION_DRILL_TYPES:
            # At least one production drill type was seen; check if any were correct
            # via the attempt_log or by checking the drill_types_seen + total_correct > 0
            # Since drill_types_seen only records types attempted (not correct),
            # we conservatively accept: if we have production types in history AND
            # total_correct > 0, production was likely correct at least once.
            # For a more precise check we'd need per-drill-type correct tracking,
            # but this is a reasonable approximation.
            has_production_correct = (row.get("total_correct") or 0) > 0

    # 3. Mastery transition
    mastery = _update_mastery(conn, row, correct, confidence, drill_type,
                              srs["streak_correct"], srs["streak_incorrect"],
                              ctx["distinct_days"], ctx["total_after"],
                              ctx["drill_type_count"],
                              modality_count=modality_count,
                              has_production_correct=has_production_correct)

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

    # 5b. Per-item tone tracking (Doctrine §2: tone mastery per item)
    if error_type == "tone" or (drill_type and "tone" in (drill_type or "")):
        tone_was_correct = 1 if correct else 0
        try:
            conn.execute("""
                UPDATE progress SET
                    tone_attempts = tone_attempts + 1,
                    tone_correct = tone_correct + ?
                WHERE user_id = ? AND content_item_id = ? AND modality = ?
            """, (tone_was_correct, user_id, content_item_id, modality))
        except sqlite3.OperationalError:
            logger.debug("tone_attempts column missing — migration pending")

    # 6. Log error if incorrect
    if not correct:
        _log_error(conn, content_item_id, session_id, modality,
                   error_type, user_answer, expected_answer, drill_type,
                   user_id=user_id, metadata=metadata, error_cause=error_cause)
    else:
        # Update error focus for correct answers (may resolve errors)
        try:
            update_error_focus(conn, content_item_id, error_type or "other", True,
                               user_id=user_id)
        except sqlite3.Error:
            logger.debug("error_focus update failed (table may be missing)", exc_info=True)
        # Resolve persistent error shapes on correct answers
        _resolve_error_shapes(conn, content_item_id, user_id=user_id)

    # 6a. Review event log (Doctrine §12: per-review instrumentation)
    try:
        conn.execute("""
            INSERT INTO review_event (user_id, session_id, content_item_id, modality,
                                      drill_type, correct, confidence, response_ms, error_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, session_id, content_item_id, modality,
              drill_type, 1 if correct else 0, confidence, response_ms, error_type))
    except sqlite3.OperationalError:
        logger.debug("review_event table missing — migration pending")

    # 6a2. FSRS memory state update (Doc 13: memory science)
    try:
        from ..ai.memory_model import process_review as _fsrs_process_review, RATING_GOOD, RATING_AGAIN
        _fsrs_rating = RATING_GOOD if correct else RATING_AGAIN
        _fsrs_process_review(conn, user_id, content_item_id, _fsrs_rating, response_ms)
    except Exception:
        logger.debug("FSRS memory state update skipped", exc_info=True)

    # 6a3. Learner model pattern state update (Doc 16: learner model)
    try:
        from ..ai.learner_model import update_pattern_state_from_review as _update_patterns
        _update_patterns(conn, user_id, content_item_id, correct)
    except Exception:
        logger.debug("Learner model pattern update skipped", exc_info=True)

    # 6a4. Thompson Sampling posterior update for drill type selection
    if drill_type:
        try:
            from ..scheduler import _update_drill_type_posterior
            _update_drill_type_posterior(conn, user_id, content_item_id, drill_type, correct)
        except Exception:
            logger.debug("Drill type posterior update skipped", exc_info=True)

    # 6b. Item graduation event (Doctrine §12: graduation rate KPI)
    old_stage = (row.get("mastery_stage") or "seen")
    new_stage = mastery["mastery_stage"]
    if old_stage != "stable" and new_stage == "stable":
        try:
            conn.execute("""
                INSERT INTO client_event (user_id, event_type, event_data, created_at)
                VALUES (?, 'item.graduated', ?, datetime('now'))
            """, (user_id, json.dumps({
                "content_item_id": content_item_id,
                "modality": modality,
                "total_attempts": (row.get("total_attempts") or 0) + 1,
            })))
        except sqlite3.OperationalError:
            logger.debug("client_event table missing for item.graduated")

    conn.commit()

    # Lifecycle: first_correct (fire once per user)
    if correct:
        try:
            prev_correct = conn.execute(
                "SELECT COUNT(*) as cnt FROM progress WHERE user_id = ? AND total_correct > 0",
                (user_id,)
            ).fetchone()
            if prev_correct and prev_correct["cnt"] == 1:
                from ..marketing_hooks import log_lifecycle_event
                log_lifecycle_event("first_correct", user_id=str(user_id), conn=conn,
                                    content_item_id=content_item_id, modality=modality)
        except Exception:
            pass


def override_last_attempt(conn: sqlite3.Connection, content_item_id: int,
                          modality: str, user_id: int = 1) -> bool:
    """Override the most recent wrong attempt as correct.

    Adjusts progress counters (total_correct, streaks) and re-runs
    mastery/retention updates. Returns True if override was applied.
    """
    row = conn.execute("""
        SELECT * FROM progress
        WHERE user_id = ? AND content_item_id = ? AND modality = ?
    """, (user_id, content_item_id, modality)).fetchone()
    if not row:
        return False
    row = dict(row)

    # Adjust counters: +1 correct, fix streaks
    new_total_correct = row["total_correct"] + 1
    new_streak_correct = row["streak_correct"] + 1
    new_streak_incorrect = max(0, row["streak_incorrect"] - 1)

    # Re-run mastery with corrected streaks
    distinct_days = row.get("distinct_review_days") or 1
    drill_types_seen = row.get("drill_types_seen") or ""
    drill_type_count = len([t for t in drill_types_seen.split(",") if t])
    total_attempts = row.get("total_attempts") or 1

    # Check if item has production drill history
    types_set = set(t for t in drill_types_seen.split(",") if t)
    has_prod = bool(types_set & PRODUCTION_DRILL_TYPES) and new_total_correct > 0
    mastery = _compute_mastery_transition(
        {**row, "total_correct": new_total_correct},
        True, "full", new_streak_correct, new_streak_incorrect,
        None, distinct_days, total_attempts, drill_type_count,
        has_production_correct=has_prod,
    )

    # Re-run retention with correct=True
    ret = _compute_retention_update(row, True, "full", modality=modality)

    # Re-run SRS with correct=True
    srs = _compute_srs_update(row, True, "full", None, mastery["mastery_stage"])

    conn.execute("""
        UPDATE progress SET
            total_correct = ?,
            streak_correct = ?,
            streak_incorrect = ?,
            mastery_stage = ?,
            historically_weak = ?,
            weak_cycle_count = ?,
            stable_since_date = ?,
            successes_while_stable = ?,
            half_life_days = ?,
            difficulty = ?,
            last_p_recall = ?,
            ease_factor = ?,
            interval_days = ?,
            repetitions = ?,
            next_review_date = ?
        WHERE user_id = ? AND content_item_id = ? AND modality = ?
    """, (new_total_correct,
          srs["streak_correct"], srs["streak_incorrect"],
          mastery["mastery_stage"], mastery["historically_weak"],
          mastery["weak_cycle_count"], mastery["stable_since_date"],
          mastery["successes_while_stable"],
          ret["half_life"], ret["difficulty"], round(ret["p_recall"], 3),
          srs["ease"], srs["interval"], srs["reps"], srs["next_review"],
          user_id, content_item_id, modality))

    # Also fix content_item counter
    conn.execute("""
        UPDATE content_item SET times_correct = times_correct + 1 WHERE id = ?
    """, (content_item_id,))

    conn.commit()
    return True


_CONFUSION_PAIR_THRESHOLD = 3  # Errors before auto-flagging interference


def _detect_confusion_pair(conn: sqlite3.Connection, item_id: int,
                           user_answer: str, drill_type: str,
                           user_id: int = 1) -> None:
    """Auto-detect interference pairs from repeated MC confusion patterns.

    When the same wrong answer is picked 3+ times for the same item, look up
    the confused item and insert into interference_pairs.
    """
    if not user_answer or not user_answer.strip():
        return

    # Resolve the confused item ID from the wrong answer
    field = "hanzi" if drill_type in ("reverse_mc", "pinyin_to_hanzi") else "english"
    confused = conn.execute(
        f"SELECT id FROM content_item WHERE {field} = ? AND id != ? LIMIT 1",
        (user_answer.strip(), item_id)
    ).fetchone()
    if not confused:
        return
    confused_id = confused["id"]

    # Count how many times this exact confusion has occurred
    count_row = conn.execute("""
        SELECT COUNT(*) as cnt FROM error_log
        WHERE content_item_id = ? AND user_answer = ? AND user_id = ?
    """, (item_id, user_answer.strip(), user_id)).fetchone()
    if (count_row["cnt"] or 0) < _CONFUSION_PAIR_THRESHOLD:
        return

    # Canonical ordering for UNIQUE constraint
    id_a, id_b = min(item_id, confused_id), max(item_id, confused_id)

    # Check if pair already exists
    existing = conn.execute("""
        SELECT id FROM interference_pairs
        WHERE item_id_a = ? AND item_id_b = ?
    """, (id_a, id_b)).fetchone()

    if existing:
        # Increment co-occurrence counter
        try:
            conn.execute("""
                UPDATE interference_pairs SET error_co_occurrence = error_co_occurrence + 1
                WHERE id = ?
            """, (existing["id"],))
        except sqlite3.OperationalError:
            pass
    else:
        try:
            conn.execute("""
                INSERT INTO interference_pairs
                    (item_id_a, item_id_b, interference_type, interference_strength, detected_by)
                VALUES (?, ?, 'semantic_field', 'medium', 'error_pattern')
            """, (id_a, id_b))
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            pass  # Table missing or constraint violation


def _resolve_error_shapes(conn: sqlite3.Connection, content_item_id: int,
                          user_id: int = 1) -> None:
    """On correct answer, increment consecutive_correct on unresolved error shapes.

    Resolves shapes after 3 consecutive correct answers (matching error_focus logic).
    """
    try:
        rows = conn.execute("""
            SELECT id, consecutive_correct FROM error_shape_summary
            WHERE content_item_id = ? AND user_id = ? AND resolved = 0
        """, (content_item_id, user_id)).fetchall()
        for row in rows:
            new_consec = (row["consecutive_correct"] or 0) + 1
            if new_consec >= 3:
                conn.execute("""
                    UPDATE error_shape_summary SET
                        consecutive_correct = ?, resolved = 1, resolved_at = datetime('now')
                    WHERE id = ?
                """, (new_consec, row["id"]))
            else:
                conn.execute("""
                    UPDATE error_shape_summary SET consecutive_correct = ?
                    WHERE id = ?
                """, (new_consec, row["id"]))
    except sqlite3.OperationalError:
        pass  # Table not yet migrated


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
            ON CONFLICT(user_id, content_item_id, error_type) DO UPDATE SET
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
          AND ci.review_status = 'approved'
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
            WHERE ci.status = 'drill_ready' AND ci.review_status = 'approved'
              AND ci.hsk_level IS NOT NULL
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
            # Weighted progress: credit all learning stages proportionally
            seen_n = r["seen_stage"] or 0
            passed_n = r["passed_once"] or 0
            stabilizing_n = stabilizing
            stable_n = r["stable"] or 0
            durable_n = r["durable"] or 0
            weighted = (seen_n * 0.1 + passed_n * 0.3
                        + stabilizing_n * 0.6 + stable_n * 0.9
                        + durable_n * 1.0)
            progress_pct = (weighted / total * 100) if total > 0 else 0
            result[r["hsk_level"]] = {
                "total": total,
                "mastered": mastered,
                "pct": progress_pct,
                "mastered_pct": (mastered / total * 100) if total > 0 else 0,
                "seen": seen,
                "not_seen": total - seen,
                "stable": stable_n,
                "durable": durable_n,
                "stabilizing": stabilizing_n,
                "passed_once": passed_n,
                "seen_stage": seen_n,
                "decayed": r["decayed"] or 0,
                # Backward compat aliases
                "improving": stabilizing,
                "weak": seen_n + passed_n,
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
        WHERE ci.status = 'drill_ready' AND ci.review_status = 'approved'
          AND ci.hsk_level IS NOT NULL
        GROUP BY ci.hsk_level
        ORDER BY ci.hsk_level
    """, (user_id,)).fetchall()
    result = {}
    for r in rows:
        total = r["total"]
        seen = r["seen"] or 0
        mastered = r["mastered"] or 0
        mastered_pct = (mastered / total * 100) if total > 0 else 0
        result[r["hsk_level"]] = {
            "total": total,
            "mastered": mastered,
            "pct": mastered_pct,
            "mastered_pct": mastered_pct,
            "seen": seen,
            "not_seen": total - seen,
        }
    return result
