"""Multiple-choice drill implementations."""

import random
import sys

from .. import db
from .base import (
    DrillResult, format_hanzi, format_hanzi_inline, format_hanzi_option,
    _skip_result, _handle_confidence, _run_mc_input,
    cause_to_error_type, classify_error_cause, elaborate_error,
)
from .hints import get_hanzi_hint


# ── MC distractor improvements ──────────────────────────────

def generate_mc_options(conn, correct_item: dict,
                        field: str = "english", n_options: int = 4):
    """Generate multiple-choice options with smart distractors.

    Returns (options_list, max_tier_used) where max_tier_used indicates
    distractor quality: 0=phonetic, 1=same HSK, 2=nearby, 3=fallback.

    Prefers distractors from:
    1. Same HSK level, excluding mastered_strong (streak_correct >= 5)
    2. Similar length (±50% character count for hanzi/pinyin fields)
    3. Same item_type (vocab vs sentence)

    Invariants:
    - Correct answer is always present and non-empty
    - No duplicate options
    - At least 2 total options (correct + 1 distractor minimum)
    - Length constraints applied per field type
    """
    # SECURITY: whitelist of allowed column names prevents SQL injection.
    # Only these three columns may be used in ORDER BY / WHERE clauses below.
    _ALLOWED_FIELDS = {"english", "hanzi", "pinyin"}
    if field not in _ALLOWED_FIELDS:
        raise ValueError(f"generate_mc_options: field must be one of {_ALLOWED_FIELDS}, got {field!r}")

    correct_val = (correct_item.get(field) or "").strip()
    if not correct_val:
        return [correct_val or "?"], 3

    item_id = correct_item["id"]
    hsk = correct_item.get("hsk_level")
    correct_len = len(correct_val)
    max_tier_used = -1  # Track highest tier needed

    # Length invariant bounds (avoid obvious outliers by field type)
    if field == "english":
        min_len = max(3, int(correct_len * 0.4))
        max_len = max(correct_len + 15, int(correct_len * 1.8))
    elif field in ("hanzi", "pinyin"):
        min_len = max(1, int(correct_len * 0.5))
        max_len = int(correct_len * 1.5) + 1
    else:
        min_len = 0
        max_len = 9999

    # Tier 0 (phonetic): Same HSK level + phonetic similarity (shared pinyin initial)
    rows = []
    if hsk and field in ("english", "hanzi"):
        correct_pinyin = (correct_item.get("pinyin") or "")[:2].lower()
        if correct_pinyin:
            rows = conn.execute("""
                SELECT DISTINCT ci.{f} FROM content_item ci
                LEFT JOIN progress p ON ci.id = p.content_item_id
                WHERE ci.id != ? AND ci.hsk_level = ? AND ci.{f} != ? AND ci.{f} != ''
                  AND (p.streak_correct IS NULL OR p.streak_correct < 5)
                  AND LENGTH(ci.{f}) BETWEEN ? AND ?
                  AND LOWER(SUBSTR(ci.pinyin, 1, 2)) = ?
                ORDER BY RANDOM() LIMIT ?
            """.format(f=field), (item_id, hsk, correct_val,
                                   min_len, max_len, correct_pinyin,
                                   n_options - 1)).fetchall()
            if rows:
                max_tier_used = 0

    # Tier 1 (same HSK): Same HSK level, exclude mastered_strong items
    if len(rows) < n_options - 1 and hsk:
        existing_vals = {r[0] for r in rows}
        more = conn.execute("""
            SELECT DISTINCT ci.{f} FROM content_item ci
            LEFT JOIN progress p ON ci.id = p.content_item_id
            WHERE ci.id != ? AND ci.hsk_level = ? AND ci.{f} != ? AND ci.{f} != ''
              AND (p.streak_correct IS NULL OR p.streak_correct < 5)
              AND LENGTH(ci.{f}) BETWEEN ? AND ?
            ORDER BY RANDOM() LIMIT ?
        """.format(f=field), (item_id, hsk, correct_val,
                               min_len, max_len, n_options - 1)).fetchall()
        for r in more:
            if r[0] not in existing_vals and len(rows) < n_options - 1:
                rows.append(r)
                max_tier_used = max(max_tier_used, 1)

    # Tier 2 (nearby HSK): Nearby HSK levels
    if len(rows) < n_options - 1 and hsk:
        existing_vals = {r[0] for r in rows}
        more = conn.execute("""
            SELECT DISTINCT ci.{f} FROM content_item ci
            WHERE ci.id != ? AND ci.hsk_level BETWEEN ? AND ?
              AND ci.{f} != ? AND ci.{f} != ''
              AND LENGTH(ci.{f}) BETWEEN ? AND ?
            ORDER BY RANDOM() LIMIT ?
        """.format(f=field), (item_id, max(1, hsk - 1), hsk + 1, correct_val,
                               min_len, max_len,
                               (n_options - 1 - len(rows)) * 2)).fetchall()
        for r in more:
            if r[0] not in existing_vals and len(rows) < n_options - 1:
                rows.append(r)
                max_tier_used = max(max_tier_used, 2)

    # Tier 3 (fallback): Any items (relax length constraint)
    if len(rows) < n_options - 1:
        existing_vals = {r[0] for r in rows}
        more = conn.execute("""
            SELECT DISTINCT {f} FROM content_item
            WHERE id != ? AND {f} != ? AND {f} != ''
            ORDER BY RANDOM() LIMIT ?
        """.format(f=field), (item_id, correct_val,
                               (n_options - 1 - len(rows)) * 2)).fetchall()
        for r in more:
            if r[0] not in existing_vals and len(rows) < n_options - 1:
                rows.append(r)
                max_tier_used = 3

    if max_tier_used == 3:
        print(f"[distractor-quality] item={item_id} field={field}: fell back to tier 3 (weak distractors)", file=sys.stderr)

    # Build options: deduplicate, always include correct answer
    seen = {correct_val}
    options = []
    for r in rows:
        val = (r[0] or "").strip()
        if val and val not in seen:
            options.append(val)
            seen.add(val)
        if len(options) >= n_options - 1:
            break

    options.append(correct_val)
    random.shuffle(options)
    return options, max(max_tier_used, 0)


# ── Drill implementations ──────────────────────────────

def run_mc_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True,
                  show_pinyin: bool = False) -> DrillResult:
    """Multiple-choice: show hanzi only, pick English meaning."""
    options, tier = generate_mc_options(conn, item, field="english", n_options=4)

    show_fn(format_hanzi(item['hanzi'], prominent))
    if show_pinyin:
        show_fn(f"  {item['pinyin']}")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, item["english"], "reading", "mc", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == item["english"]
    feedback = ""
    error_type = None
    if not correct:
        feedback = f"  → {format_hanzi_inline(item['hanzi'])} ({item['pinyin']}) = {item['english']}"
        cause = classify_error_cause(user_picked, item["english"], "mc", item)
        elaboration = elaborate_error(cause, user_picked, item["english"], item, "mc")
        if elaboration:
            feedback += f"\n{elaboration}"
        hint_text, _ = get_hanzi_hint(item["hanzi"], wrong_answer=user_picked, error_type="vocab")
        if hint_text:
            feedback += f"\n{hint_text}"
        error_type = cause_to_error_type(cause, "vocab")

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="mc",
        correct=correct, user_answer=user_picked, expected_answer=item["english"],
        error_type=error_type, feedback=feedback,
        distractor_tier=tier,
    )


def run_reverse_mc_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True,
                          show_pinyin: bool = False) -> DrillResult:
    """Reverse MC: show English, pick the correct hanzi."""
    options, tier = generate_mc_options(conn, item, field="hanzi", n_options=4)

    show_fn(f"\n  Which character means: {item['english']}?\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt)}")

    result = _run_mc_input(item, options, item["hanzi"], "reading", "reverse_mc", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == item["hanzi"]
    feedback = ""
    error_type = None
    if not correct:
        feedback = f"  → {format_hanzi_inline(item['hanzi'])} ({item['pinyin']}) = {item['english']}"
        cause = classify_error_cause(user_picked, item["hanzi"], "reverse_mc", item)
        elaboration = elaborate_error(cause, user_picked, item["hanzi"], item, "reverse_mc")
        if elaboration:
            feedback += f"\n{elaboration}"
        hint_text, _ = get_hanzi_hint(item["hanzi"], wrong_answer=user_picked, error_type="vocab")
        if hint_text:
            feedback += f"\n{hint_text}"
        error_type = cause_to_error_type(cause, "vocab")

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="reverse_mc",
        correct=correct, user_answer=user_picked, expected_answer=item["hanzi"],
        error_type=error_type, feedback=feedback,
        distractor_tier=tier,
    )
