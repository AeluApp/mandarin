"""Grammar drill implementations: complement, ba/bei, error correction."""

import json
import os
import random
from typing import Optional

from .base import DrillResult, format_hanzi, format_hanzi_inline, _run_mc_input

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")

# ── Context sentence templates for grammar point types ──────────────
# Maps grammar drill category to a short contextual introduction shown
# before the drill question so the learner sees the pattern in use first.

_COMPLEMENT_CONTEXT = {
    "result": "Result complements show the outcome of an action — what happened after the verb.",
    "potential": "Potential complements use 得/不 to say whether something can or can't be done.",
    "direction": "Direction complements show where the action goes — up, down, in, out, toward or away.",
    "degree": "Degree complements use 得 to describe how well or to what extent something is done.",
}

_BA_BEI_CONTEXT = {
    "rewrite": "把 sentences move the object before the verb, emphasising disposal or manipulation.",
    "identify": "Distinguish 把 (disposal/action on object) from 被 (passive, something done to the subject).",
    "fill": "Choose 把 (the subject acts on the object) or 被 (the subject receives the action).",
}

_ERROR_CONTEXT = "Chinese word order, particles, and aspect markers follow specific rules. " \
                 "Find where the rule is broken."


def _show_grammar_context(show_fn, context_text: str, example_zh: str = "",
                          example_en: str = "") -> None:
    """Display a brief context introduction before a grammar drill question.

    Shows the grammar pattern description and an optional example sentence
    so the learner has a frame of reference before being tested.
    """
    show_fn(f"\n  [dim]{context_text}[/dim]")
    if example_zh:
        show_fn(f"  e.g. {format_hanzi_inline(example_zh)}")
        if example_en:
            show_fn(f"       \"{example_en}\"")
    show_fn("")


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
                         prominent: bool = True) -> DrillResult | None:
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

    # Show contextual introduction for the complement type
    context = _COMPLEMENT_CONTEXT.get(comp_type, "")
    if context:
        # Pick a different entry of the same type as an example (avoid spoiling the answer)
        example_entries = [e for e in candidates if e.get("type") == comp_type and e is not entry]
        ex_zh = ""
        ex_en = ""
        if example_entries:
            ex = random.choice(example_entries)
            ex_zh = ex.get("sentence", ex.get("prompt", ""))
            ex_en = ex.get("meaning", "")
        _show_grammar_context(show_fn, context, ex_zh, ex_en)

    if comp_type == "potential":
        prompt_text = entry["prompt"]
        correct = entry["answer"]
        distractors = list(entry.get("distractors", []))

        show_fn(f"  What does this mean?", prominent=prominent)
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
                     prominent: bool = True) -> DrillResult | None:
    """把/被 pattern drill — rewrite, identify, or fill sub-formats."""
    entries = _get_ba_bei_patterns()
    item_level = item.get("hsk_level") or 4

    candidates = [e for e in entries if (e.get("hsk_level") or 1) <= item_level]
    if not candidates:
        return None

    entry = random.choice(candidates)
    sub_type = entry.get("type", "identify")

    # Show contextual introduction for the 把/被 sub-type
    context = _BA_BEI_CONTEXT.get(sub_type, "")
    if context:
        example_entries = [e for e in candidates if e.get("type") == sub_type and e is not entry]
        ex_zh = ""
        ex_en = ""
        if example_entries:
            ex = random.choice(example_entries)
            ex_zh = ex.get("ba_form", ex.get("sentence", ""))
            ex_en = ex.get("explanation", "")
        _show_grammar_context(show_fn, context, ex_zh, ex_en)

    if sub_type == "rewrite":
        svo = entry["svo"]
        correct = entry["answer"]
        distractors = list(entry.get("distractors", []))

        show_fn(f"  Rewrite using 把:", prominent=prominent)
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
                               prominent: bool = True) -> DrillResult | None:
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

    # Show contextual introduction — what kind of error to look for
    error_type_detail = entry.get("error_type_detail", "")
    _ERROR_TYPE_HINTS = {
        "aspect": "Aspect markers (了, 过, 着) follow specific rules about when to use them.",
        "comparative": "Comparative sentences with 比 have a specific structure.",
        "progressive": "The progressive marker 在 indicates an action happening right now.",
        "word_order": "Chinese word order places time, place, and duration in specific positions.",
        "negation": "不 negates habits and future; 没 negates past actions and 有.",
        "de_particle": "的, 得, and 地 each serve a different grammatical role.",
        "conjunction": "Paired conjunctions (虽然...但是, 因为...所以) must appear together.",
        "complement": "Complements follow the verb directly; 了 comes after the complement.",
        "ba_complement": "把 sentences require a result or change — a bare verb is not enough.",
        "passive": "被 precedes the agent who performs the action.",
        "duration": "Duration phrases go between the verb and the object.",
        "degree_complement": "In V得 constructions, the description follows 得.",
        "superlative": "更 (more) and 最 (most) cannot be combined.",
        "adverb_position": "Adverbs like 也, 都, 就 go before the verb or negation.",
        "separable_verb": "Separable verbs (起床, 上课) can only be split in specific ways.",
    }
    context_hint = _ERROR_TYPE_HINTS.get(error_type_detail, _ERROR_CONTEXT)
    _show_grammar_context(show_fn, context_hint)

    if error_span is None:
        correct = "No error"
        options = ["No error"] + distractors[:3]
    else:
        correct = error_span
        options = [correct] + distractors[:3]

    show_fn(f"  Find the error:", prominent=prominent)
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
