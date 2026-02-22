"""Pinyin-related drill implementations and helpers."""

import re

from .base import (
    DrillResult, format_hanzi, format_hanzi_inline, format_hanzi_option,
    _skip_result, _handle_confidence, _run_mc_input,
    cause_to_error_type, classify_error_cause, elaborate_error,
)
from .hints import get_hanzi_hint
from .mc import generate_mc_options


# ── Tone number <-> mark conversion ──────────────────────────────

TONE_MARK_TO_NUM = {
    "ā": "a1", "á": "a2", "ǎ": "a3", "à": "a4",
    "ē": "e1", "é": "e2", "ě": "e3", "è": "e4",
    "ī": "i1", "í": "i2", "ǐ": "i3", "ì": "i4",
    "ō": "o1", "ó": "o2", "ǒ": "o3", "ò": "o4",
    "ū": "u1", "ú": "u2", "ǔ": "u3", "ù": "u4",
    "ǖ": "v1", "ǘ": "v2", "ǚ": "v3", "ǜ": "v4",
}

TONE_NUM_TO_MARK = {}
for _mark, _num in TONE_MARK_TO_NUM.items():
    TONE_NUM_TO_MARK[_num] = _mark


def marked_to_numbered(pinyin: str) -> str:
    """Convert tone-marked pinyin to numbered: ma -> ma1, beizi -> bei1zi."""
    result = []
    tone_num = ""
    for ch in pinyin:
        if ch in TONE_MARK_TO_NUM:
            base_num = TONE_MARK_TO_NUM[ch]
            result.append(base_num[0])
            tone_num = base_num[1]
        else:
            if tone_num and not ch.isalpha():
                result.append(tone_num)
                tone_num = ""
            result.append(ch)
    if tone_num:
        result.append(tone_num)
    return "".join(result)


def strip_tones(pinyin: str) -> str:
    """Remove all tone information from pinyin."""
    tone_map = str.maketrans(
        "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ",
        "aaaaeeeeiiiioooouuuuvvvv"
    )
    # Strip tone marks
    result = pinyin.translate(tone_map)
    # Strip tone numbers
    result = re.sub(r'([a-zü])([1-4])', r'\1', result)
    return result.lower()


def normalize_pinyin(s: str) -> str:
    """Normalize pinyin for comparison: lowercase, no spaces, no apostrophes."""
    return s.lower().replace(" ", "").replace("'", "").replace("\u2019", "")


# ── Pinyin matching ──────────────────────────────

def _pinyin_match(user: str, expected: str):
    """Check if user pinyin matches expected. Returns (correct, match_type).

    match_type: 'exact', 'numbered', 'no_tone', or None (wrong).
    Accepts tone numbers (ma1 = ma) and plain pinyin (mama = mama, counted correct).
    """
    user_norm = normalize_pinyin(user)
    expected_norm = normalize_pinyin(expected)

    # Exact match (with tone marks)
    if user_norm == expected_norm:
        return True, "exact"

    # Convert both to numbered form and compare
    user_numbered = normalize_pinyin(marked_to_numbered(user))
    expected_numbered = normalize_pinyin(marked_to_numbered(expected))

    if user_numbered == expected_numbered:
        return True, "numbered"

    # User typed tone numbers directly: ma1ma -> compare with ma1ma
    # Strip all non-alphanumeric for this check
    user_alnum = re.sub(r'[^a-z0-9]', '', user.lower())
    expected_alnum = re.sub(r'[^a-z0-9]', '', expected_numbered)
    if user_alnum == expected_alnum:
        return True, "numbered"

    # Plain pinyin (no tones at all) -- accept as correct but note it
    user_stripped = strip_tones(user)
    expected_stripped = strip_tones(expected)
    if user_stripped == expected_stripped and user_stripped:
        return True, "no_tone"

    return False, None


def _classify_ime_error(user: str, expected: str) -> str:
    """Classify IME error: tone, ime_confusable, or segment."""
    user_stripped = strip_tones(user)
    expected_stripped = strip_tones(expected)

    if user_stripped == expected_stripped:
        return "tone"

    # Check edit distance for confusables
    if abs(len(user_stripped) - len(expected_stripped)) <= 1:
        diffs = 0
        for a, b in zip(user_stripped, expected_stripped):
            if a != b:
                diffs += 1
        if diffs <= 2:
            return "ime_confusable"

    return "segment"


# ── IME drill ──────────────────────────────

def run_ime_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True) -> DrillResult:
    """IME typing: show English+hanzi, type the pinyin.

    Accepts:
    - Tone-marked pinyin: mama
    - Tone-numbered pinyin: ma1ma
    - Plain pinyin (no tones): mama (marked as tone error if tones expected)
    """
    show_fn(f"\n  Type the pinyin for:")
    show_fn(format_hanzi(item['hanzi'], prominent))

    answer = input_fn("  pinyin> ").strip()

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, "ime", "ime_type", answer)

    conf_result = _handle_confidence(answer, item, "ime", "ime_type", item["pinyin"], show_fn)
    if conf_result:
        return conf_result

    expected = item["pinyin"].strip()
    correct, match_type = _pinyin_match(answer, expected)

    error_type = None
    feedback = ""
    if not correct:
        error_type = _classify_ime_error(answer, expected)
        feedback = f"  → {format_hanzi_inline(item['hanzi'])} = {expected}"
        if error_type == "tone":
            feedback += "  (tones were off)"
        elif error_type == "ime_confusable":
            feedback += "  (close — check the syllables)"
        # Additional elaboration from error-cause classifier
        cause = classify_error_cause(answer, expected, "ime_type", item)
        elaboration = elaborate_error(cause, answer, expected, item, "ime_type")
        if elaboration:
            feedback += f"\n{elaboration}"
    elif match_type == "no_tone":
        # Correct syllables but no tones provided — accept but note it
        feedback = f"  (correct syllables — practice the tones: {expected})"

    return DrillResult(
        content_item_id=item["id"], modality="ime", drill_type="ime_type",
        correct=correct, user_answer=answer, expected_answer=expected,
        error_type=error_type, feedback=feedback,
    )


# ── New pinyin drills ──────────────────────────────

def run_english_to_pinyin_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True) -> DrillResult:
    """English -> Pinyin MC: show English, pick the correct pinyin."""
    options, tier = generate_mc_options(conn, item, field="pinyin", n_options=4)

    show_fn(f"\n  What's the pinyin for: \"{item['english']}\"?\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, item["pinyin"], "reading", "english_to_pinyin", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == item["pinyin"]
    feedback = ""
    error_type = None
    if not correct:
        feedback = f"  → {format_hanzi_inline(item['hanzi'])} ({item['pinyin']}) = {item['english']}"
        cause = classify_error_cause(user_picked, item["pinyin"], "english_to_pinyin", item)
        elaboration = elaborate_error(cause, user_picked, item["pinyin"], item, "english_to_pinyin")
        if elaboration:
            feedback += f"\n{elaboration}"
        error_type = "tone"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="english_to_pinyin",
        correct=correct, user_answer=user_picked, expected_answer=item["pinyin"],
        error_type=error_type, feedback=feedback,
        distractor_tier=tier,
    )


def run_hanzi_to_pinyin_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True,
                               show_pinyin: bool = False) -> DrillResult:
    """Hanzi -> Pinyin MC: show hanzi, pick the correct pinyin."""
    options, tier = generate_mc_options(conn, item, field="pinyin", n_options=4)

    show_fn(format_hanzi(item['hanzi'], prominent))
    show_fn(f"  What's the pinyin?\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, item["pinyin"], "reading", "hanzi_to_pinyin", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == item["pinyin"]
    feedback = ""
    error_type = None
    if not correct:
        feedback = f"  → {format_hanzi_inline(item['hanzi'])} ({item['pinyin']}) = {item['english']}"
        cause = classify_error_cause(user_picked, item["pinyin"], "hanzi_to_pinyin", item)
        elaboration = elaborate_error(cause, user_picked, item["pinyin"], item, "hanzi_to_pinyin")
        if elaboration:
            feedback += f"\n{elaboration}"
        error_type = "tone"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="hanzi_to_pinyin",
        correct=correct, user_answer=user_picked, expected_answer=item["pinyin"],
        error_type=error_type, feedback=feedback,
        distractor_tier=tier,
    )


def run_pinyin_to_hanzi_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True) -> DrillResult:
    """Pinyin -> Hanzi MC: show pinyin + English, pick the correct hanzi."""
    options, tier = generate_mc_options(conn, item, field="hanzi", n_options=4)

    show_fn(f"\n  Which character is: {item['pinyin']}  ({item['english']})?\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt)}")

    result = _run_mc_input(item, options, item["hanzi"], "reading", "pinyin_to_hanzi", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == item["hanzi"]
    feedback = ""
    error_type = None
    if not correct:
        feedback = f"  → {format_hanzi_inline(item['hanzi'])} ({item['pinyin']}) = {item['english']}"
        cause = classify_error_cause(user_picked, item["hanzi"], "pinyin_to_hanzi", item)
        elaboration = elaborate_error(cause, user_picked, item["hanzi"], item, "pinyin_to_hanzi")
        if elaboration:
            feedback += f"\n{elaboration}"
        hint_text, _ = get_hanzi_hint(item["hanzi"], wrong_answer=user_picked, error_type="vocab")
        if hint_text:
            feedback += f"\n{hint_text}"
        error_type = cause_to_error_type(cause, "vocab")

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="pinyin_to_hanzi",
        correct=correct, user_answer=user_picked, expected_answer=item["hanzi"],
        error_type=error_type, feedback=feedback,
        distractor_tier=tier,
    )
