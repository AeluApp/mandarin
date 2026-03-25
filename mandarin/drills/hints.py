"""Sticky hanzi hint engine — radical, contrast, component, and phonetic hints."""

import json
import os
from typing import Optional

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")


def _load_json(filename):
    with open(os.path.join(_DATA_DIR, filename)) as f:
        return json.load(f)


# ── Sticky Hanzi Hint Engine ──────────────────────────────

HINT_TYPES = ["radical", "contrast", "component", "phonetic"]

# Lazy-loaded radical hints from radicals.json
_RADICAL_HINTS_CACHE = None

# Common simplified/variant radical forms not in the Kangxi 214 set.
# Maps variant -> (meaning description) so learners see the simplified
# forms they actually encounter in modern Chinese characters.
_VARIANT_RADICAL_HINTS = {
    "\u6c35": "water radical \u2014 rivers, liquids, wetness",
    "\u4ebb": "person radical \u2014 people, human actions",
    "\u95e8": "gate radical \u2014 doors, openings",
    "\u8f66": "vehicle radical \u2014 cars, transport",
    "\u9a6c": "horse radical \u2014 horses, speed",
    "\u9c7c": "fish radical \u2014 fish, aquatic",
    "\u9e1f": "bird radical \u2014 birds, flying",
}


def _get_radical_hints():
    """Build radical hints dict from radicals.json + common variant forms."""
    global _RADICAL_HINTS_CACHE
    if _RADICAL_HINTS_CACHE is not None:
        return _RADICAL_HINTS_CACHE

    raw = _load_json("radicals.json")
    hints = {}
    for entry in raw:
        radical = entry["radical"]
        meaning = entry["meaning"]
        hints[radical] = f"{meaning} radical"

    # Add simplified/variant forms that learners encounter but aren't in Kangxi
    hints.update(_VARIANT_RADICAL_HINTS)

    _RADICAL_HINTS_CACHE = hints
    return _RADICAL_HINTS_CACHE


def get_hanzi_hint(hanzi: str, wrong_answer: str = "",
                   last_hint_type: str = None,
                   error_type: str = None) -> tuple:
    """Generate a sticky hint for a hanzi miss. Returns (hint_text, hint_type).

    If error_type is provided, routes to the most relevant hint strategy first:
      tone → phonetic, segment → contrast, ime_confusable → phonetic,
      vocab → radical, grammar → component.
    Falls back to rotation if preferred hint returns None.
    Max 2 lines.
    """
    # Error-type-specific routing: try the best hint type first
    error_preferred = {
        "tone": "phonetic",
        "segment": "contrast",
        "ime_confusable": "phonetic",
        "vocab": "radical",
        "grammar": "component",
    }
    preferred = error_preferred.get(error_type) if error_type else None

    # Pick hint type: prefer error-specific, then rotate away from last
    if preferred and preferred != last_hint_type:
        available = [preferred] + [t for t in HINT_TYPES if t != preferred and t != last_hint_type]
    else:
        available = [t for t in HINT_TYPES if t != last_hint_type]
    if not available:
        available = HINT_TYPES
    hint_type = available[0]

    if hint_type == "radical":
        hint = _radical_hint(hanzi)
    elif hint_type == "contrast":
        hint = _contrast_hint(hanzi, wrong_answer)
    elif hint_type == "component":
        hint = _component_hint(hanzi)
    elif hint_type == "phonetic":
        hint = _phonetic_hint(hanzi)
    else:
        hint = None

    if hint:
        return hint, hint_type

    # Fallback: try other types
    for t in available[1:]:
        if t == "radical":
            hint = _radical_hint(hanzi)
        elif t == "contrast":
            hint = _contrast_hint(hanzi, wrong_answer)
        elif t == "component":
            hint = _component_hint(hanzi)
        elif t == "phonetic":
            hint = _phonetic_hint(hanzi)
        if hint:
            return hint, t

    return None, None


def _radical_hint(hanzi: str) -> str | None:
    """Generate a radical-based hint without revealing the answer character."""
    radical_hints = _get_radical_hints()
    for char in hanzi:
        for radical, meaning in radical_hints.items():
            # Only show the radical if it's a component, not the whole character
            if radical != char and radical in char:
                return f"  Hint: contains the {meaning}"
    # If the character itself is a radical, give the meaning without showing it
    if len(hanzi) == 1 and hanzi in radical_hints:
        return f"  Hint: this character means {radical_hints[hanzi]}"
    return None


def _contrast_hint(hanzi: str, wrong_answer: str) -> str | None:
    """Generate a visual contrast hint between correct and wrong.

    Only shows the wrong answer the user already picked — never the correct one.
    Points to the distinguishing feature without revealing the right answer.
    """
    if not wrong_answer or len(wrong_answer) < 1:
        return None
    # Identify which side/component differs between them
    if len(hanzi) == 1 and len(wrong_answer) == 1:
        return f"  Hint: you picked {wrong_answer} — the right answer differs on the right side"
    elif len(hanzi) <= 2 and len(wrong_answer) <= 4:
        return f"  Hint: look more carefully at the right side of your answer ({wrong_answer})"
    return None


def _component_hint(hanzi: str) -> str | None:
    """Generate a component/shape hint without revealing the character itself."""
    if len(hanzi) == 1:
        code = ord(hanzi)
        if 0x4E00 <= code <= 0x9FFF:
            radical_hints = _get_radical_hints()
            # Try to give structural info without showing the character
            for radical, meaning in radical_hints.items():
                if radical != hanzi:
                    # Only mention the radical if it's a component, not the whole character
                    return f"  Hint: think about the {meaning} — it's part of this character"
            return "  Hint: look at the character's internal structure — what parts do you recognize?"
    elif len(hanzi) >= 2:
        return f"  Hint: this is a {len(hanzi)}-character word — think about what connects them"
    return None


def _phonetic_hint(hanzi: str) -> str | None:
    """Generate a phonetic/sound hint without revealing characters."""
    if len(hanzi) >= 2:
        return "  Hint: the pronunciation follows from the right-side component"
    elif len(hanzi) == 1:
        return "  Hint: the sound comes from one of the components inside"
    return None
