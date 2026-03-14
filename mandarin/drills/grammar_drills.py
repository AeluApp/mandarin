"""Grammar drill implementations: complement, ba/bei, error correction."""

import json
import os
import random
from typing import Optional

from .base import DrillResult, format_hanzi, format_hanzi_inline, _run_mc_input

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")

# ── Lazy-loaded caches ──────────────────────────────
_COMPLEMENT_CACHE = None
_BA_BEI_CACHE = None
_ERROR_SENTENCES_CACHE = None


def _get_complement_patterns():
    global _COMPLEMENT_CACHE
    if _COMPLEMENT_CACHE is None:
        path = os.path.join(_DATA_DIR, "complement_patterns.json")
        with open(path) as f:
            data = json.load(f)
        _COMPLEMENT_CACHE = data.get("entries", data)
    return _COMPLEMENT_CACHE


def _get_ba_bei_patterns():
    global _BA_BEI_CACHE
    if _BA_BEI_CACHE is None:
        path = os.path.join(_DATA_DIR, "ba_bei_patterns.json")
        with open(path) as f:
            data = json.load(f)
        _BA_BEI_CACHE = data.get("entries", data)
    return _BA_BEI_CACHE


def _get_error_sentences():
    global _ERROR_SENTENCES_CACHE
    if _ERROR_SENTENCES_CACHE is None:
        path = os.path.join(_DATA_DIR, "error_sentences.json")
        with open(path) as f:
            data = json.load(f)
        _ERROR_SENTENCES_CACHE = data.get("entries", data)
    return _ERROR_SENTENCES_CACHE


# ── Complement Drill ──────────────────────────────

def run_complement_drill(item: dict, conn, show_fn, input_fn,
                         prominent: bool = True) -> Optional[DrillResult]:
    """Fill-in-the-blank complement drill (MC).

    Covers result, potential, direction, and degree complements.
    """
    entries = _get_complement_patterns()
    item_level = item.get("hsk_level") or 3

    candidates = [e for e in entries if (e.get("hsk_level") or 1) <= item_level]
    if not candidates:
        return None

    entry = random.choice(candidates)
    comp_type = entry.get("type", "result")

    if comp_type == "potential":
        prompt_text = entry["prompt"]
        correct = entry["answer"]
        distractors = list(entry.get("distractors", []))

        show_fn(f"\n  What does this mean?", prominent=prominent)
        show_fn(f"  {format_hanzi_inline(prompt_text)}")
        show_fn("")

        options = [correct] + distractors[:3]
        random.shuffle(options)

        for i, opt in enumerate(options, 1):
            show_fn(f"  {i}. {opt}")
    else:
        sentence = entry.get("sentence", "")
        correct = entry["answer"]
        distractors = list(entry.get("distractors", []))

        show_fn(f"\n  Fill in the blank:", prominent=prominent)
        show_fn(f"  {format_hanzi_inline(sentence)}")
        show_fn("")

        options = [correct] + distractors[:3]
        random.shuffle(options)

        for i, opt in enumerate(options, 1):
            show_fn(f"  {i}. {format_hanzi_inline(opt)}")

    result = _run_mc_input(item, options, correct, "reading", "complement", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    is_correct = (user_picked == correct)

    feedback = ""
    if not is_correct:
        feedback = f"  → {correct}"
    explanation = entry.get("explanation", "")
    if explanation:
        feedback += f"\n  [dim]{explanation}[/dim]"

    return DrillResult(
        content_item_id=item["id"], modality="reading",
        drill_type="complement", correct=is_correct,
        user_answer=user_picked, expected_answer=correct,
        error_type=None if is_correct else "grammar",
        feedback=feedback,
    )


# ── 把/被 Drill ──────────────────────────────

def run_ba_bei_drill(item: dict, conn, show_fn, input_fn,
                     prominent: bool = True) -> Optional[DrillResult]:
    """把/被 pattern drill — rewrite, identify, or fill sub-formats."""
    entries = _get_ba_bei_patterns()
    item_level = item.get("hsk_level") or 4

    candidates = [e for e in entries if (e.get("hsk_level") or 1) <= item_level]
    if not candidates:
        return None

    entry = random.choice(candidates)
    sub_type = entry.get("type", "identify")

    if sub_type == "rewrite":
        svo = entry["svo"]
        correct = entry["answer"]
        distractors = list(entry.get("distractors", []))

        show_fn(f"\n  Rewrite using 把:", prominent=prominent)
        show_fn(f"  {format_hanzi_inline(svo)}")
        show_fn("")

        options = [correct] + distractors[:3]
        random.shuffle(options)

        for i, opt in enumerate(options, 1):
            show_fn(f"  {i}. {format_hanzi_inline(opt)}")

    elif sub_type == "identify":
        sentence = entry["sentence"]
        correct = entry["answer"]
        distractors = list(entry.get("distractors", []))

        show_fn(f"\n  Which construction is used?", prominent=prominent)
        show_fn(f"  {format_hanzi_inline(sentence)}")
        show_fn("")

        options = [correct] + distractors[:3]
        random.shuffle(options)

        for i, opt in enumerate(options, 1):
            show_fn(f"  {i}. {opt}")

    else:  # fill
        sentence = entry["sentence"]
        correct = entry["answer"]
        distractors = list(entry.get("distractors", []))

        show_fn(f"\n  Fill in the blank:", prominent=prominent)
        show_fn(f"  {format_hanzi_inline(sentence)}")
        show_fn("")

        options = [correct] + distractors[:3]
        random.shuffle(options)

        for i, opt in enumerate(options, 1):
            show_fn(f"  {i}. {format_hanzi_inline(opt)}")

    result = _run_mc_input(item, options, correct, "reading", "ba_bei", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    is_correct = (user_picked == correct)

    feedback = ""
    if not is_correct:
        feedback = f"  → {correct}"
    explanation = entry.get("explanation", "")
    if explanation:
        feedback += f"\n  [dim]{explanation}[/dim]"

    return DrillResult(
        content_item_id=item["id"], modality="reading",
        drill_type="ba_bei", correct=is_correct,
        user_answer=user_picked, expected_answer=correct,
        error_type=None if is_correct else "grammar",
        feedback=feedback,
    )


# ── Error Correction Drill ──────────────────────────────

def run_error_correction_drill(item: dict, conn, show_fn, input_fn,
                               prominent: bool = True) -> Optional[DrillResult]:
    """Show a sentence with an error → pick the error span (MC)."""
    entries = _get_error_sentences()
    item_level = item.get("hsk_level") or 3

    candidates = [e for e in entries if (e.get("hsk_level") or 1) <= item_level]
    if not candidates:
        return None

    entry = random.choice(candidates)
    wrong_sentence = entry["wrong"]
    correct_sentence = entry["correct"]
    error_span = entry.get("error_span")
    distractors = list(entry.get("distractors", []))

    if error_span is None:
        correct = "No error"
        options = ["No error"] + distractors[:3]
    else:
        correct = error_span
        options = [correct] + distractors[:3]

    show_fn(f"\n  Find the error:", prominent=prominent)
    show_fn(f"  {format_hanzi_inline(wrong_sentence)}")
    show_fn("")

    random.shuffle(options)

    for i, opt in enumerate(options, 1):
        label = format_hanzi_inline(opt) if opt != "No error" else opt
        show_fn(f"  {i}. {label}")

    result = _run_mc_input(item, options, correct, "reading", "error_correction", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    is_correct = (user_picked == correct)

    feedback = ""
    if not is_correct:
        feedback = f"  → Error: {format_hanzi_inline(correct) if correct != 'No error' else correct}"
    if correct_sentence != wrong_sentence:
        feedback += f"\n  Correct: {format_hanzi_inline(correct_sentence)}"
    explanation = entry.get("explanation", "")
    if explanation:
        feedback += f"\n  [dim]{explanation}[/dim]"

    return DrillResult(
        content_item_id=item["id"], modality="reading",
        drill_type="error_correction", correct=is_correct,
        user_answer=user_picked, expected_answer=correct,
        error_type=None if is_correct else "grammar",
        feedback=feedback,
    )
