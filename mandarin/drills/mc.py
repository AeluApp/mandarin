"""Multiple-choice drill implementations."""

import json
import logging
import os
import random

from .. import db

logger = logging.getLogger(__name__)
from .base import (
    DrillResult, format_hanzi, format_hanzi_inline, format_hanzi_option,
    format_answer_feedback,
    _skip_result, _handle_confidence, _run_mc_input,
    cause_to_error_type, classify_error_cause, elaborate_error,
)
from .hints import get_hanzi_hint

# ── Confusable pairs (Doctrine §2: distractors from known confusables) ──

_CONFUSABLE_PAIRS = {}  # hanzi -> list of confusable hanzi
_CONFUSABLE_PAIRS_RAW = []  # Full list from JSON (for distinction lookup)

def _load_confusable_pairs():
    """Load confusable_pairs.json into a lookup dict: hanzi -> [confusable_hanzi].

    Also caches the raw list in _CONFUSABLE_PAIRS_RAW for distinction lookups.
    """
    global _CONFUSABLE_PAIRS, _CONFUSABLE_PAIRS_RAW
    if _CONFUSABLE_PAIRS:
        return
    path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "confusable_pairs.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            pairs = json.load(f)
        _CONFUSABLE_PAIRS_RAW = pairs
        for entry in pairs:
            group = entry["pair"]
            for i, char in enumerate(group):
                others = [g for j, g in enumerate(group) if j != i]
                _CONFUSABLE_PAIRS.setdefault(char, []).extend(others)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        logger.debug("confusable_pairs.json not loaded", exc_info=True)


# ── MC distractor improvements ──────────────────────────────


def _normalize_english(text: str) -> str:
    """Normalize English text for dedup comparison: lowercase, strip articles/prepositions."""
    t = text.lower().strip()
    # Remove leading "to " for verb forms
    if t.startswith("to "):
        t = t[3:]
    # Remove parenthetical alternatives like "(come)"
    import re
    t = re.sub(r'\([^)]*\)', '', t).strip()
    # Remove leading articles
    for prefix in ("a ", "an ", "the "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return t.strip()


def _split_synonyms(text: str) -> set:
    """Split semicolon/comma-separated synonym lists into individual terms."""
    import re
    parts = re.split(r'[;,]', text)
    terms = set()
    for p in parts:
        p = p.strip().lower()
        if p:
            # Strip articles
            for prefix in ("a ", "an ", "the ", "to "):
                if p.startswith(prefix):
                    p = p[len(prefix):]
            if p:
                terms.add(p.strip())
    return terms


def _english_overlap(a: str, b: str) -> bool:
    """Return True if a and b overlap significantly (shared synonyms or core words)."""
    if not a or not b:
        return False
    # Direct containment
    if a in b or b in a:
        return True
    # Split on semicolons/commas — if any synonym segment matches, it's overlap.
    # e.g. "mother; mom" vs "ma; mom; mother" share "mom" and "mother"
    syns_a = _split_synonyms(a)
    syns_b = _split_synonyms(b)
    if syns_a & syns_b:
        return True
    # Check if primary word (longest word) matches
    words_a = sorted(a.replace(";", " ").replace(",", " ").split(), key=len, reverse=True)
    words_b = sorted(b.replace(";", " ").replace(",", " ").split(), key=len, reverse=True)
    if words_a and words_b and len(words_a[0]) >= 3 and words_a[0] == words_b[0]:
        return True
    return False


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

    # Tier -1 (confusable pairs): Known visually/phonetically confusable characters
    rows = []
    if field == "hanzi":
        _load_confusable_pairs()
        confusables = _CONFUSABLE_PAIRS.get(correct_val, [])
        if confusables:
            placeholders = ",".join("?" * len(confusables))
            conf_rows = conn.execute(
                f"SELECT DISTINCT hanzi FROM content_item WHERE hanzi IN ({placeholders}) AND id != ? AND review_status = 'approved'",
                (*confusables, item_id),
            ).fetchall()
            for r in conf_rows:
                if r[0] and r[0] != correct_val and len(rows) < n_options - 1:
                    rows.append(r)
                    max_tier_used = 0  # confusable = best quality

    # Tier 0 (phonetic): Same HSK level + phonetic similarity (shared pinyin initial)
    if hsk and field in ("english", "hanzi"):
        correct_pinyin = (correct_item.get("pinyin") or "")[:2].lower()
        if correct_pinyin:
            rows = conn.execute("""
                SELECT DISTINCT ci.{f} FROM content_item ci
                LEFT JOIN progress p ON ci.id = p.content_item_id
                WHERE ci.id != ? AND ci.hsk_level = ? AND ci.{f} != ? AND ci.{f} != ''
                  AND ci.review_status = 'approved'
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
              AND ci.review_status = 'approved'
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
              AND ci.review_status = 'approved'
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
              AND review_status = 'approved'
            ORDER BY RANDOM() LIMIT ?
        """.format(f=field), (item_id, correct_val,
                               (n_options - 1 - len(rows)) * 2)).fetchall()
        for r in more:
            if r[0] not in existing_vals and len(rows) < n_options - 1:
                rows.append(r)
                max_tier_used = 3

    if max_tier_used == 3:
        logger.warning("[distractor-quality] item=%s field=%s: fell back to tier 3 (weak distractors)", item_id, field)

    # Build options: deduplicate, always include correct answer.
    # Use fuzzy dedup — reject distractors that are substrings of or
    # overlap heavily with the correct answer or other options.
    seen = {correct_val}
    seen_normalized = {_normalize_english(correct_val)}
    options = []
    for r in rows:
        val = (r[0] or "").strip()
        if not val or val in seen:
            continue
        norm = _normalize_english(val)
        # Skip if normalized form matches or is contained in any existing option
        if norm in seen_normalized:
            continue
        if any(_english_overlap(norm, s) for s in seen_normalized):
            continue
        options.append(val)
        seen.add(val)
        seen_normalized.add(norm)
        if len(options) >= n_options - 1:
            break

    options.append(correct_val)

    # Guarantee at least 2 options — pad with placeholder if DB is too sparse
    if len(options) < 2:
        options.insert(0, "(none of the above)")
        max_tier_used = 3

    random.shuffle(options)
    return options, max(max_tier_used, 0)


def _lookup_item_by_field(conn, field: str, value: str):
    """Look up a content_item by a given field value for wrong-answer context.

    Returns dict with hanzi, pinyin, english or None if not found.
    Field name is validated against an allowlist.
    """
    _ALLOWED = {"english", "hanzi", "pinyin"}
    if field not in _ALLOWED:
        return None
    if not value or not value.strip():
        return None
    row = conn.execute(
        "SELECT hanzi, pinyin, english FROM content_item WHERE {f} = ? AND review_status = 'approved' LIMIT 1".format(f=field),
        (value,),
    ).fetchone()
    return dict(row) if row else None


# ── Drill implementations ──────────────────────────────

def run_mc_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True,
                  show_pinyin: bool = False, english_level: str = "full") -> DrillResult:
    """Multiple-choice: show hanzi only, pick English meaning (or pinyin when English faded)."""
    # When English is faded, use pinyin options instead
    if english_level != "full":
        field = "pinyin"
        correct_answer = item["pinyin"]
    else:
        field = "english"
        correct_answer = item["english"]

    options, tier = generate_mc_options(conn, item, field=field, n_options=4)

    show_fn(format_hanzi(item['hanzi'], prominent))
    if show_pinyin:
        show_fn(f"  {item['pinyin']}")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, correct_answer, "reading", "mc", show_fn, input_fn,
                           english_level=english_level)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_answer
    feedback = ""
    error_type = None
    cause = None
    if not correct:
        # Build specific feedback: show what wrong pick refers to + correct answer
        wrong_item = _lookup_item_by_field(conn, field, user_picked)
        if wrong_item and field == "english":
            # Forward MC: user picked wrong English meaning
            # Max-2 rule: show hanzi + pinyin (omit english since pinyin is present)
            feedback = (
                f"  You picked \"{user_picked}\""
                f" ({format_hanzi_inline(wrong_item['hanzi'])} {wrong_item.get('pinyin', '')})."
                f" The correct answer is {format_hanzi_inline(item['hanzi'])}"
                f" ({item.get('pinyin', '')})"
            )
        elif wrong_item and field == "pinyin":
            # Max-2 rule: show hanzi + pinyin for correct answer (omit english)
            feedback = (
                f"  You picked {user_picked}"
                f" ({format_hanzi_inline(wrong_item['hanzi'])})."
                f" The correct answer is {format_hanzi_inline(item['hanzi'])}"
                f" ({item.get('pinyin', '')})"
            )
        else:
            feedback = format_answer_feedback(item, english_level)
        cause = classify_error_cause(user_picked, correct_answer, "mc", item)
        elaboration = elaborate_error(cause, user_picked, correct_answer, item, "mc")
        if elaboration:
            feedback += f"\n{elaboration}"
        hint_text, _ = get_hanzi_hint(item["hanzi"], wrong_answer=user_picked, error_type="vocab")
        if hint_text:
            feedback += f"\n{hint_text}"
        error_type = cause_to_error_type(cause, "vocab")

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="mc",
        correct=correct, user_answer=user_picked, expected_answer=correct_answer,
        error_type=error_type, error_cause=cause, feedback=feedback,
        distractor_tier=tier,
    )


def run_reverse_mc_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True,
                          show_pinyin: bool = False, english_level: str = "full") -> DrillResult:
    """Reverse MC: show English (or pinyin), pick the correct hanzi."""
    options, tier = generate_mc_options(conn, item, field="hanzi", n_options=4)

    # When English is faded, prompt with pinyin instead
    if english_level != "full":
        show_fn(f"\n  Which character is: {item['pinyin']}?\n")
    else:
        show_fn(f"\n  Which character means: {item['english']}?\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt)}")

    result = _run_mc_input(item, options, item["hanzi"], "reading", "reverse_mc", show_fn, input_fn,
                           english_level=english_level)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == item["hanzi"]
    feedback = ""
    error_type = None
    cause = None
    if not correct:
        # Build specific feedback: show what wrong hanzi means + correct answer
        wrong_item = _lookup_item_by_field(conn, "hanzi", user_picked)
        if wrong_item:
            feedback = (
                f"  You picked {format_hanzi_inline(user_picked)}"
                f" ({wrong_item.get('pinyin', '')}) = {wrong_item.get('english', '')}."
                f" The correct answer is {format_hanzi_inline(item['hanzi'])}"
                f" ({item.get('pinyin', '')}) = {item.get('english', '')}"
            )
        else:
            feedback = format_answer_feedback(item, english_level)
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
        error_type=error_type, error_cause=cause, feedback=feedback,
        distractor_tier=tier,
    )


# ── Contrastive drill ──────────────────────────────

def _get_confusable_distinction(hanzi_a: str, hanzi_b: str) -> str:
    """Look up a curated distinction hint for a pair of confusable hanzi.

    Returns the distinction string, or empty string if no match found.
    """
    _load_confusable_pairs()
    for entry in _CONFUSABLE_PAIRS_RAW:
        pair = entry.get("pair", [])
        if hanzi_a in pair and hanzi_b in pair:
            return entry.get("distinction", "")
    return ""


def run_contrastive_drill(item: dict, conn, show_fn, input_fn,
                          partner_id: int = None, **kwargs) -> DrillResult:
    """Contrastive drill: present two interference pair items and ask learner to distinguish.

    Shows both items with their distinguishing features, asks which matches a given meaning.
    Uses confusable_pairs.json for curated distinction hints when available.
    """
    # Resolve partner_id from item metadata if not provided directly
    if partner_id is None:
        partner_id = (item.get("metadata") or {}).get("contrastive_partner_id")
        if partner_id is None:
            partner_id = item.get("contrastive_partner_id")

    # Find a partner from interference_pairs if none specified
    if partner_id is None:
        try:
            row = conn.execute("""
                SELECT item_id_a, item_id_b FROM interference_pairs
                WHERE (item_id_a = ? OR item_id_b = ?)
                  AND interference_strength = 'high'
                ORDER BY RANDOM() LIMIT 1
            """, (item["id"], item["id"])).fetchone()
            if row:
                partner_id = row["item_id_b"] if row["item_id_a"] == item["id"] else row["item_id_a"]
        except Exception:
            pass

    # No partner found — fall back to regular MC
    if partner_id is None:
        return run_mc_drill(item, conn, show_fn, input_fn)

    # Look up partner content_item
    partner = conn.execute(
        "SELECT * FROM content_item WHERE id = ?", (partner_id,)
    ).fetchone()
    if not partner:
        return run_mc_drill(item, conn, show_fn, input_fn)
    partner = dict(partner)

    # Randomly choose which item's meaning to ask about
    if random.random() < 0.5:
        target, other = item, partner
    else:
        target, other = partner, item

    english = target.get("english", "")
    option_a = f"{item['hanzi']} ({item.get('pinyin', '')})"
    option_b = f"{partner['hanzi']} ({partner.get('pinyin', '')})"
    options = [option_a, option_b]
    correct_option = f"{target['hanzi']} ({target.get('pinyin', '')})"
    random.shuffle(options)

    # Display
    show_fn(f"\n  Which one means '{english}'?\n")
    for i_opt, opt in enumerate(options, 1):
        show_fn(f"  {i_opt}. {format_hanzi_option(opt)}")

    # Get input
    answer = input_fn("\n  > ").strip()

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, "reading", "contrastive", answer)

    conf_result = _handle_confidence(
        answer, item, "reading", "contrastive", correct_option, show_fn,
        options=options, input_fn=input_fn,
    )
    if conf_result:
        return conf_result

    # Parse choice
    try:
        choice = int(answer) - 1
        if 0 <= choice < len(options):
            user_picked = options[choice]
        else:
            raise ValueError("out of range")
    except (ValueError, IndexError):
        user_picked = answer

    correct = user_picked == correct_option
    feedback = ""
    error_type = None
    error_cause = None

    if correct:
        feedback = f"  {format_hanzi_inline(target['hanzi'])} = {english}"
    else:
        feedback = (
            f"  Not quite. {format_hanzi_inline(target['hanzi'])}"
            f" ({target.get('pinyin', '')}) = {english}"
        )
        error_type = "vocab"
        error_cause = "contrastive_confusion"

    # Show distinction hint if available (whether correct or wrong)
    distinction = _get_confusable_distinction(item["hanzi"], partner["hanzi"])
    if distinction:
        feedback += f"\n  Hint: {distinction}"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="contrastive",
        correct=correct, user_answer=user_picked, expected_answer=correct_option,
        error_type=error_type, error_cause=error_cause, feedback=feedback,
    )
