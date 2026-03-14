"""Tone drill implementations."""

import random
import unicodedata

from .base import (
    DrillResult, format_hanzi, format_hanzi_inline,
    _skip_result, _handle_confidence, _run_mc_input,
    cause_to_error_type, classify_error_cause, elaborate_error,
)
from .pinyin import strip_tones


# ── Tone contour descriptions (for enriched wrong-answer feedback) ──────

TONE_CONTOURS = {
    1: "Tone 1 is high and flat \u2192",
    2: "Tone 2 rises \u2197",
    3: "Tone 3 dips then rises \u2198\u2197",
    4: "Tone 4 falls sharply \u2198",
}


# ── Tone option generation ──────────────────────────────

_TONE_VARIANTS = {
    "a": ["\u0101", "\u00e1", "\u01ce", "\u00e0"],
    "e": ["\u0113", "\u00e9", "\u011b", "\u00e8"],
    "i": ["\u012b", "\u00ed", "\u01d0", "\u00ec"],
    "o": ["\u014d", "\u00f3", "\u01d2", "\u00f2"],
    "u": ["\u016b", "\u00fa", "\u01d4", "\u00f9"],
    "\u00fc": ["\u01d6", "\u01d8", "\u01da", "\u01dc"],
}

# Reverse: toned char -> (base, tone_num)
_TONED_CHAR_INFO = {}
for _base, _variants in _TONE_VARIANTS.items():
    for _i, _v in enumerate(_variants, 1):
        _TONED_CHAR_INFO[_v] = (_base, _i)


def _generate_tone_options(correct_pinyin: str, n_options: int = 4) -> list:
    """Generate tone variants for a tone drill."""
    options = [correct_pinyin]

    # Find all toned characters and their positions
    toned_positions = []
    for i, ch in enumerate(correct_pinyin):
        if ch in _TONED_CHAR_INFO:
            base, tone = _TONED_CHAR_INFO[ch]
            toned_positions.append((i, base, tone))

    if not toned_positions:
        # No tone marks found — generate numbered-form variants as fallback.
        # Extract the base syllable and create tone1-4 options.
        stripped = strip_tones(correct_pinyin)
        if stripped:
            options = [f"{stripped}{i}" for i in range(1, n_options + 1)]
            # Mark one as "correct" (tone 1 by convention for unmarked pinyin)
            random.shuffle(options)
        return options

    # Generate variants by changing the first toned vowel
    pos, base, correct_tone = toned_positions[0]
    variants = _TONE_VARIANTS.get(base, [])

    for tone_idx, variant_char in enumerate(variants, 1):
        if tone_idx != correct_tone:
            alt = correct_pinyin[:pos] + variant_char + correct_pinyin[pos + 1:]
            if alt not in options:
                options.append(alt)
        if len(options) >= n_options:
            break

    # If multi-syllable and still need options, vary second toned vowel
    if len(options) < n_options and len(toned_positions) > 1:
        pos2, base2, tone2 = toned_positions[1]
        variants2 = _TONE_VARIANTS.get(base2, [])
        for tone_idx, variant_char in enumerate(variants2, 1):
            if tone_idx != tone2:
                alt = correct_pinyin[:pos2] + variant_char + correct_pinyin[pos2 + 1:]
                if alt not in options:
                    options.append(alt)
            if len(options) >= n_options:
                break

    options = options[:n_options]
    random.shuffle(options)
    return options


# ── Tone drill ──────────────────────────────

def run_tone_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True,
                   audio_enabled: bool = False, english_level: str = "full") -> DrillResult:
    """Tone discrimination: show hanzi (+ english when not faded), pick correct toned pinyin."""
    correct_pinyin = item["pinyin"]
    options = _generate_tone_options(correct_pinyin)

    # Play audio BEFORE showing options
    if audio_enabled:
        from ..audio import speak_and_wait
        speak_and_wait(item["hanzi"])
        show_fn(f"\n  Listen, then pick the correct tone:")
    else:
        show_fn(f"\n  What's the correct tone for:")

    show_fn(format_hanzi(item['hanzi'], prominent))
    # Show English hint only when not faded
    if english_level == "full":
        show_fn(f"  ({item.get('english', '')})")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, correct_pinyin, "reading", "tone", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    # Normalize Unicode to NFC to avoid false mismatches on composed vs decomposed diacritics
    user_picked = unicodedata.normalize('NFC', user_picked)
    correct_pinyin = unicodedata.normalize('NFC', correct_pinyin)

    correct = user_picked == correct_pinyin
    feedback = ""
    error_type = None
    cause = None
    tone_meta = None
    if not correct:
        feedback = f"  \u2192 {format_hanzi_inline(item['hanzi'])} = {correct_pinyin}"
        # Error-cause analysis
        cause = classify_error_cause(user_picked, correct_pinyin, "tone", item)
        elaboration = elaborate_error(cause, user_picked, correct_pinyin, item, "tone")
        if elaboration:
            feedback += f"\n{elaboration}"
        # Add tone contour descriptions for expected tones
        from ..tone_grading import pinyin_to_tones
        expected_tones = pinyin_to_tones(correct_pinyin)
        if expected_tones:
            contours = [TONE_CONTOURS.get(t, f"Tone {t}") for t in expected_tones]
            feedback += "\n  " + ", ".join(contours)
        error_type = cause_to_error_type(cause, "tone")

        # Extract tone numbers for confusion tracking
        user_tones = pinyin_to_tones(user_picked)
        if user_tones and expected_tones:
            tone_meta = {
                "tone_user": user_tones[0],
                "tone_expected": expected_tones[0],
            }

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="tone",
        correct=correct, user_answer=user_picked, expected_answer=correct_pinyin,
        error_type=error_type, error_cause=cause, feedback=feedback,
        metadata=tone_meta,
    )
