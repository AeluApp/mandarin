"""Base drill types, helpers, and formatting utilities."""

import random
import re
from dataclasses import dataclass
from typing import Optional, Union

from .hints import get_hanzi_hint


# ── Hanzi display formatting ──────────────────────────────

HANZI_STYLES = {
    "prominent": "bold bright_magenta",
    "compact": "bold magenta",
    "inline": "bold bright_magenta",
    "option": "magenta",
}


def format_hanzi(hanzi: str, prominent: bool = True) -> str:
    """Format hanzi for display — bigger/spaced when prominent.

    prominent=True: space characters out, bright purple, vertical padding
    prominent=False: just bold purple (for advanced learners, HSK 6+)
    """
    if prominent:
        style = HANZI_STYLES["prominent"]
        spaced = "  ".join(hanzi)
        return f"\n[{style}]  {spaced}[/{style}]\n"
    else:
        style = HANZI_STYLES["compact"]
        return f"[{style}]  {hanzi}[/{style}]"


def format_hanzi_inline(hanzi: str) -> str:
    """Format hanzi for inline feedback — bright purple but compact."""
    style = HANZI_STYLES["inline"]
    return f"[{style}]{hanzi}[/{style}]"


def format_hanzi_option(hanzi: str) -> str:
    """Format hanzi for MC option lists — subtle purple."""
    style = HANZI_STYLES["option"]
    return f"[{style}]{hanzi}[/{style}]"


@dataclass
class DrillResult:
    """Result of a single drill attempt."""
    content_item_id: int
    modality: str
    drill_type: str
    correct: bool
    user_answer: str = ""
    expected_answer: str = ""
    error_type: Optional[str] = None  # tone, segment, ime_confusable, grammar, vocab, other
    skipped: bool = False
    feedback: str = ""  # Rich feedback string shown after answer
    score: Optional[float] = None  # 0.0-1.0 for conversation drills
    confidence: str = "full"  # full, half, unknown
    requirement_ref: Optional[dict] = None  # HSK provenance: {type, name, hsk_level, source}
    distractor_tier: Optional[int] = None  # 0=phonetic, 1=same HSK, 2=nearby, 3=fallback
    metadata: Optional[dict] = None  # Arbitrary metadata (e.g. media_id, tone_scores)


# ── Confidence states ──────────────────────────────
# ? = "I'm 50/50" — award partial credit (0.5)
# N = "I don't know this" — no credit but no penalty, log as still_unknown

def check_confidence_input(answer: str) -> Optional[str]:
    """Check if input is a confidence signal. Returns 'half', 'unknown', or None."""
    stripped = answer.strip()
    if stripped == "?":
        return "half"
    if stripped.upper() == "N":
        return "unknown"
    return None


# ── Gradient scaffold hints ──────────────────────────────

def format_scaffold_hint(pinyin: str, level: str) -> str:
    """Format a scaffold hint based on mastery-driven level.

    full_pinyin: return pinyin as-is
    tone_marks: extract tone numbers, return space-separated: "3 3"
    initial: first consonant of each syllable: "n h"
    none: return ""
    """
    if level == "full_pinyin":
        return pinyin
    if level == "tone_marks":
        from ..tone_grading import pinyin_to_tones
        tones = pinyin_to_tones(pinyin)
        return " ".join(str(t) for t in tones) if tones else ""
    if level == "initial":
        # Extract first consonant of each syllable
        syllables = re.split(r"[\s'']+", pinyin.strip())
        initials = []
        for syl in syllables:
            clean = re.sub(r'[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]',
                           lambda m: 'a' if m.group() in 'āáǎà' else
                           'e' if m.group() in 'ēéěè' else
                           'i' if m.group() in 'īíǐì' else
                           'o' if m.group() in 'ōóǒò' else
                           'u' if m.group() in 'ūúǔù' else 'v', syl)
            if clean:
                initials.append(clean[0])
        return " ".join(initials) if initials else ""
    return ""


# ── Skip/quit helper ──────────────────────────────

def _skip_result(item: dict, modality: str, drill_type: str, answer: str) -> DrillResult:
    """Create a skip/quit result."""
    return DrillResult(
        content_item_id=item["id"], modality=modality, drill_type=drill_type,
        correct=False, skipped=True, user_answer=answer,
        expected_answer=item.get("english", ""),
    )


# ── Confidence handling ──────────────────────────────

def _handle_confidence(answer: str, item: dict, modality: str, drill_type: str,
                       correct_answer: str, show_fn, options: list = None,
                       input_fn=None) -> Optional[DrillResult]:
    """Handle ? (50/50) and N (still_unknown) inputs.

    When options are provided and user types N on an MC drill, narrows to 2 choices
    instead of revealing the answer immediately.

    Returns DrillResult or None.
    """
    conf = check_confidence_input(answer)
    if conf is None:
        return None

    if conf == "half":
        # 50/50: show the answer, award partial credit
        show_fn(f"  → {format_hanzi_inline(item['hanzi'])} ({item.get('pinyin', '')}) = {item.get('english', '')}")
        return DrillResult(
            content_item_id=item["id"], modality=modality, drill_type=drill_type,
            correct=False, user_answer="?", expected_answer=correct_answer,
            confidence="half",
            feedback="  (50/50)",
            score=0.5,
        )
    elif conf == "unknown":
        # MC drills with options: narrow to 2 choices instead of revealing
        if options and input_fn and len(options) > 2:
            return _handle_narrowed_choice(
                item, modality, drill_type, correct_answer, options, show_fn, input_fn
            )

        # Non-MC drills or already narrow: show the answer directly
        show_fn(f"  → {format_hanzi_inline(item['hanzi'])} ({item.get('pinyin', '')}) = {item.get('english', '')}")
        hint_text, hint_type = get_hanzi_hint(item["hanzi"])
        feedback = "  (Marked unknown)"
        if hint_text:
            feedback += f"\n{hint_text}"
        return DrillResult(
            content_item_id=item["id"], modality=modality, drill_type=drill_type,
            correct=False, user_answer="N", expected_answer=correct_answer,
            confidence="unknown",
            feedback=feedback,
            score=0.0,
        )
    return None


def _handle_narrowed_choice(item: dict, modality: str, drill_type: str,
                            correct_answer: str, options: list,
                            show_fn, input_fn) -> DrillResult:
    """Narrow MC from 4 options to 2. Limited credit if correct, no penalty if wrong/skip."""
    # Pick one distractor at random (not the correct answer)
    distractors = [o for o in options if o != correct_answer]
    distractor = random.choice(distractors) if distractors else options[0]
    narrow_options = [correct_answer, distractor]
    random.shuffle(narrow_options)

    show_fn(f"\n  Down to two — pick one (or N to skip):\n")
    for i, opt in enumerate(narrow_options, 1):
        # Use hanzi option style if the options look like Chinese characters
        if any('\u4e00' <= c <= '\u9fff' for c in str(opt)):
            show_fn(f"  {i}. {format_hanzi_option(opt)}")
        else:
            show_fn(f"  {i}. {opt}")

    answer2 = input_fn("\n  > ").strip()

    # Second N — truly don't know, show answer
    if answer2.strip().upper() == "N":
        show_fn(f"  → {format_hanzi_inline(item['hanzi'])} ({item.get('pinyin', '')}) = {item.get('english', '')}")
        hint_text, hint_type = get_hanzi_hint(item["hanzi"])
        feedback = "  (Still unknown)"
        if hint_text:
            feedback += f"\n{hint_text}"
        return DrillResult(
            content_item_id=item["id"], modality=modality, drill_type=drill_type,
            correct=False, user_answer="N", expected_answer=correct_answer,
            confidence="unknown",
            feedback=feedback,
            score=0.0,
        )

    # Q/B — skip
    if answer2.upper() in ("Q", "B"):
        return DrillResult(
            content_item_id=item["id"], modality=modality, drill_type=drill_type,
            correct=False, skipped=True, user_answer=answer2,
            expected_answer=correct_answer,
        )

    # Parse choice
    try:
        choice = int(answer2) - 1
        user_picked = narrow_options[choice]
    except (ValueError, IndexError):
        user_picked = answer2

    correct = user_picked == correct_answer
    if correct:
        feedback = "  (Narrowed)"
        return DrillResult(
            content_item_id=item["id"], modality=modality, drill_type=drill_type,
            correct=False, user_answer=user_picked, expected_answer=correct_answer,
            confidence="narrowed",
            feedback=feedback,
            score=0.3,
        )
    else:
        show_fn(f"  → {format_hanzi_inline(item['hanzi'])} ({item.get('pinyin', '')}) = {item.get('english', '')}")
        hint_text, hint_type = get_hanzi_hint(item["hanzi"])
        feedback = "  (Missed narrowed)"
        if hint_text:
            feedback += f"\n{hint_text}"
        return DrillResult(
            content_item_id=item["id"], modality=modality, drill_type=drill_type,
            correct=False, user_answer=user_picked, expected_answer=correct_answer,
            confidence="narrowed_wrong",
            feedback=feedback,
            score=0.0,
        )


# ── MC input helper ──────────────────────────────

def _run_mc_input(item: dict, options: list, correct_answer: str,
                  modality: str, drill_type: str,
                  show_fn, input_fn) -> Union[DrillResult, str]:
    """Handle the common MC input pattern: prompt, skip, confidence, choice parsing.

    Returns either a DrillResult (for skip/confidence shortcuts) or the
    user's picked option as a string (for the caller to evaluate correctness).
    """
    answer = input_fn("\n  > ").strip()

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, modality, drill_type, answer)

    conf_result = _handle_confidence(
        answer, item, modality, drill_type, correct_answer, show_fn,
        options=options, input_fn=input_fn,
    )
    if conf_result:
        return conf_result

    try:
        choice = int(answer) - 1
        user_picked = options[choice]
    except (ValueError, IndexError):
        user_picked = answer

    return user_picked


# ── Error-cause analysis ──────────────────────────────

def classify_error_cause(user_answer: str, expected_answer: str,
                          drill_type: str, item: dict) -> str:
    """Classify the specific cause of an error for targeted feedback.

    Returns a cause string like "tone_2_as_3", "phonetic_similar",
    "character_confusion", "segmentation", or "other".
    """
    if not user_answer or not expected_answer:
        return "other"

    user = user_answer.strip().lower()
    expected = expected_answer.strip().lower()

    # Tone confusion: same consonants/vowels but different tones
    if drill_type in ("tone", "listening_tone"):
        from .pinyin import marked_to_numbered
        user_num = marked_to_numbered(user)
        exp_num = marked_to_numbered(expected)
        # Extract tone numbers
        user_tones = re.findall(r'\d', user_num)
        exp_tones = re.findall(r'\d', exp_num)
        if user_tones and exp_tones and user_tones != exp_tones:
            # Find first differing tone
            for u, e in zip(user_tones, exp_tones):
                if u != e:
                    return f"tone_{e}_as_{u}"
            return "tone_confusion"

    # Character confusion: check if user picked a visually/phonetically similar character
    if drill_type in ("mc", "reverse_mc"):
        # Check if user answer shares phonetic similarity
        if user and expected and user[0] == expected[0]:
            return "phonetic_similar"
        return "vocab"

    # IME segmentation: wrong syllable boundaries
    if drill_type in ("ime_type",):
        if len(user) != len(expected):
            return "segmentation"
        return "ime_confusion"

    # Listening: general categorization
    if drill_type.startswith("listening"):
        return "listening_comprehension"

    return "other"


# Valid error_type values for the DB CHECK constraint
_VALID_ERROR_TYPES = frozenset({
    'tone', 'segment', 'ime_confusable', 'grammar', 'vocab', 'other',
    'register_mismatch', 'particle_misuse', 'function_word_omission',
    'temporal_sequencing', 'measure_word', 'politeness_softening',
    'reference_tracking', 'pragmatics_mismatch',
})

# Map detailed cause strings to valid DB error_types
_CAUSE_TO_ERROR_TYPE = {
    "tone_confusion": "tone",
    "phonetic_similar": "vocab",
    "ime_confusion": "ime_confusable",
    "segmentation": "segment",
    "listening_comprehension": "vocab",
}


def cause_to_error_type(cause: str, fallback: str = "other") -> str:
    """Map a classify_error_cause result to a valid DB error_type.

    Detailed cause strings (tone_2_as_3, phonetic_similar, etc.) are useful
    for feedback but must be normalized for the error_log CHECK constraint.
    """
    if cause in _VALID_ERROR_TYPES:
        return cause
    if cause in _CAUSE_TO_ERROR_TYPE:
        return _CAUSE_TO_ERROR_TYPE[cause]
    # Tone pattern: tone_X_as_Y → "tone"
    if cause.startswith("tone_"):
        return "tone"
    return fallback


# ── Elaborated feedback ──────────────────────────────

# Tone contour descriptions for elaborated feedback
TONE_DESCRIPTIONS = {
    "1": "flat/high",
    "2": "rising",
    "3": "dipping",
    "4": "falling",
    "5": "neutral",
    "0": "neutral",
}

def elaborate_error(cause: str, user_answer: str, expected_answer: str,
                    item: dict, drill_type: str) -> str:
    """Generate a brief explanation of why the answer was wrong.

    Returns 1-2 line explanation, or empty string if no useful elaboration.
    """
    # Tone confusion: describe the contour difference
    if cause.startswith("tone_"):
        parts = cause.split("_")
        if len(parts) >= 4:
            expected_tone = parts[1]
            heard_tone = parts[3]
            exp_desc = TONE_DESCRIPTIONS.get(expected_tone, expected_tone)
            heard_desc = TONE_DESCRIPTIONS.get(heard_tone, heard_tone)
            return f"  Tone {expected_tone} ({exp_desc}) heard as {heard_tone} ({heard_desc})"

    if cause == "tone_confusion":
        return "  Tone mismatch — listen for pitch direction"

    # Phonetic similarity
    if cause == "phonetic_similar":
        return f"  Similar sound — compare: {item.get('pinyin', '')}"

    # Segmentation
    if cause == "segmentation":
        pinyin = item.get("pinyin", "")
        return f"  Check syllable boundaries: {pinyin}"

    # IME confusion
    if cause == "ime_confusion":
        pinyin = item.get("pinyin", "")
        return f"  Expected: {pinyin}"

    return ""
