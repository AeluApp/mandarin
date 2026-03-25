"""Production drill implementations: transfer, translation, sentence build, word order."""

import json
import logging
import os
import random
import threading

from .base import (
    DrillResult, format_hanzi, format_hanzi_inline,
    format_answer_feedback,
    _skip_result, _handle_confidence, get_progressive_hint,
)
from .hints import get_hanzi_hint
from .mc import run_mc_drill
from .pinyin import strip_tones, normalize_pinyin

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")

# ── Sentence templates cache ──────────────────────────────
_SENTENCE_TEMPLATES_CACHE = None
_sentence_templates_lock = threading.Lock()


def _load_sentence_templates():
    """Load sentence templates from data/sentence_templates.json."""
    global _SENTENCE_TEMPLATES_CACHE
    if _SENTENCE_TEMPLATES_CACHE is not None:
        return _SENTENCE_TEMPLATES_CACHE
    with _sentence_templates_lock:
        if _SENTENCE_TEMPLATES_CACHE is not None:
            return _SENTENCE_TEMPLATES_CACHE
        path = os.path.join(_DATA_DIR, "sentence_templates.json")
        try:
            with open(path) as f:
                _SENTENCE_TEMPLATES_CACHE = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("Could not load sentence_templates.json: %s", e)
            _SENTENCE_TEMPLATES_CACHE = []
        return _SENTENCE_TEMPLATES_CACHE


def grade_sentence_production(user_input: str, template: dict) -> tuple:
    """Grade user's sentence against a template with multiple acceptable answers.

    Returns (score, feedback, correct) where:
    - score: 0.0-1.0
    - feedback: string explaining the grade
    - correct: bool
    """
    if not user_input or not template:
        return (0.0, "", False)

    user_norm = user_input.replace(" ", "").strip()
    acceptable = template.get("acceptable_answers", [])
    required_kw = template.get("required_keywords", [])

    # Exact match any acceptable answer → 1.0
    for ans in acceptable:
        if user_norm == ans.replace(" ", ""):
            return (1.0, "", True)

    # All keywords + high char_overlap → 0.8
    kw_present = sum(1 for kw in required_kw if kw in user_norm)
    kw_ratio = kw_present / len(required_kw) if required_kw else 0

    # Find best overlap with any acceptable answer
    best_overlap = 0.0
    best_answer = acceptable[0] if acceptable else ""
    for ans in acceptable:
        overlap = char_overlap_score(ans.replace(" ", ""), user_norm)
        if overlap > best_overlap:
            best_overlap = overlap
            best_answer = ans

    if kw_ratio == 1.0 and best_overlap >= 0.7:
        fb = f"  Close — expected: {format_hanzi_inline(best_answer)}"
        return (0.8, fb, True)

    # All keywords present → 0.6
    if kw_ratio == 1.0:
        fb = f"  Keywords correct — full answer: {format_hanzi_inline(best_answer)}"
        return (0.6, fb, True)

    # Partial keywords + some overlap → 0.4
    if kw_ratio >= 0.5 or best_overlap >= 0.5:
        fb = f"  Partial — expected: {format_hanzi_inline(best_answer)}"
        return (0.4, fb, False)

    # No match
    fb = f"  → {format_hanzi_inline(best_answer)}"
    return (0.0, fb, False)


# ── Construction transfer drill ──────────────────────────────

def run_transfer_drill(item: dict, conn, show_fn, input_fn,
                       prominent: bool = True, english_level: str = "full") -> DrillResult:
    """Construction transfer: test if learner recognizes a grammar pattern in a new context.

    Shows a construction name + pattern, presents the target item alongside
    distractors that DON'T share the construction. Learner picks which sentence
    uses the pattern.

    Tests rule learning, not item memorization.
    """
    # Find what construction this item is linked to
    constr_row = conn.execute("""
        SELECT c.name, c.pattern_zh, c.description
        FROM content_construction cc
        JOIN construction c ON c.id = cc.construction_id
        WHERE cc.content_item_id = ?
        LIMIT 1
    """, (item["id"],)).fetchone()

    if not constr_row:
        # Fallback to MC if no construction link
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    construction_name = constr_row["description"] or constr_row["name"]
    pattern = constr_row["pattern_zh"] or ""

    # Get distractors: items NOT linked to this construction
    distractor_rows = conn.execute("""
        SELECT ci.hanzi, ci.pinyin, ci.english FROM content_item ci
        WHERE ci.status = 'drill_ready'
          AND ci.review_status = 'approved'
          AND ci.id != ?
          AND ci.id NOT IN (
              SELECT cc2.content_item_id FROM content_construction cc2
              WHERE cc2.construction_id = (
                  SELECT cc3.construction_id FROM content_construction cc3
                  WHERE cc3.content_item_id = ? LIMIT 1
              )
          )
        ORDER BY RANDOM() LIMIT 3
    """, (item["id"], item["id"])).fetchall()

    if len(distractor_rows) < 3:
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    # Build options
    correct_text = f"{item['hanzi']} ({item['pinyin']}) \u2014 {item['english']}"
    options = [correct_text]
    for d in distractor_rows:
        d = dict(d)
        options.append(f"{d['hanzi']} ({d['pinyin']}) \u2014 {d['english']}")

    random.shuffle(options)
    options.index(correct_text)

    show_fn(f"\n  Which uses: [bold]{construction_name}[/bold]")
    if pattern:
        show_fn(f"  Pattern: {pattern}")
    show_fn("")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    answer = input_fn("\n  > ").strip()

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, "reading", "transfer", answer)

    try:
        choice = int(answer) - 1
        user_picked = options[choice]
    except (ValueError, IndexError):
        user_picked = answer

    correct = (user_picked == correct_text)
    feedback = ""
    if not correct:
        feedback = f"  \u2192 {correct_text}"
        feedback += f"\n  {construction_name}: {pattern}"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="transfer",
        correct=correct, user_answer=user_picked, expected_answer=correct_text,
        error_type=None if correct else "grammar", feedback=feedback,
    )


# ── Translation drill (free-form production) ──────────────

def char_overlap_score(expected: str, user_input: str) -> float:
    """Character-level Jaccard similarity between expected and user input."""
    if not expected or not user_input:
        return 0.0
    s1 = set(expected)
    s2 = set(user_input)
    intersection = s1 & s2
    union = s1 | s2
    return len(intersection) / len(union) if union else 0.0


def run_translation_drill(item: dict, conn, show_fn, input_fn,
                          prominent: bool = True, english_level: str = "full") -> DrillResult:
    """Free-form translation: show English (or pinyin), type hanzi or pinyin."""
    # When English is faded, prompt with pinyin instead
    if english_level != "full":
        show_fn(f"\n  What does this mean: \"{item['pinyin']}\"?")
    else:
        show_fn(f"\n  How would you say: \"{item['english']}\"?")
    show_fn(f"  [dim]Type the hanzi (or pinyin):[/dim]")

    hint_stage = 0
    hints_used = 0
    while True:
        answer = input_fn("\n  > ").strip()

        if answer.upper() in ("Q", "B"):
            return _skip_result(item, "reading", "translation", answer)

        conf_result = _handle_confidence(answer, item, "reading", "translation",
                                         item["hanzi"], show_fn, english_level=english_level,
                                         allow_hint=True)
        if conf_result == "HINT":
            hint_text, hint_stage = get_progressive_hint(item, hint_stage)
            show_fn(hint_text)
            hints_used += 1
            continue
        if conf_result:
            return conf_result

        expected_hanzi = item["hanzi"]
        expected_pinyin = item.get("pinyin", "")

        # Check exact hanzi match first
        if answer == expected_hanzi:
            if hints_used:
                return DrillResult(
                    content_item_id=item["id"], modality="reading", drill_type="translation",
                    correct=True, user_answer=answer, expected_answer=expected_hanzi,
                    confidence="half", score=0.5,
                    feedback=f"  (correct, with {hints_used} hint{'s' if hints_used > 1 else ''})",
                )
            return DrillResult(
                content_item_id=item["id"], modality="reading", drill_type="translation",
                correct=True, user_answer=answer, expected_answer=expected_hanzi,
                confidence="full",
            )

        # Check pinyin match (stripped of tones)
        if expected_pinyin:
            user_stripped = strip_tones(normalize_pinyin(answer))
            expected_stripped = strip_tones(normalize_pinyin(expected_pinyin))
            if user_stripped and user_stripped == expected_stripped:
                if hints_used:
                    return DrillResult(
                        content_item_id=item["id"], modality="reading", drill_type="translation",
                        correct=True, user_answer=answer, expected_answer=expected_hanzi,
                        feedback=f"  (pinyin accepted, with hints \u2014 the hanzi is {format_hanzi_inline(expected_hanzi)})",
                        confidence="half", score=0.5,
                    )
                return DrillResult(
                    content_item_id=item["id"], modality="reading", drill_type="translation",
                    correct=True, user_answer=answer, expected_answer=expected_hanzi,
                    feedback=f"  (pinyin accepted \u2014 the hanzi is {format_hanzi_inline(expected_hanzi)})",
                    confidence="full",
                )

        # Character overlap scoring
        score = char_overlap_score(expected_hanzi, answer)
        if score >= 0.6:
            return DrillResult(
                content_item_id=item["id"], modality="reading", drill_type="translation",
                correct=True, user_answer=answer, expected_answer=expected_hanzi,
                feedback=f"  (close \u2014 exact: {format_hanzi_inline(expected_hanzi)} {expected_pinyin})",
                confidence="half", score=score,
            )
        elif score >= 0.3:
            return DrillResult(
                content_item_id=item["id"], modality="reading", drill_type="translation",
                correct=False, user_answer=answer, expected_answer=expected_hanzi,
                feedback=format_answer_feedback(item, english_level),
                error_type="vocab", error_cause="production_vocab", confidence="half", score=score,
            )

        feedback = format_answer_feedback(item, english_level)
        hint_text, _ = get_hanzi_hint(expected_hanzi, wrong_answer=answer, error_type="vocab")
        if hint_text:
            feedback += f"\n{hint_text}"

        return DrillResult(
            content_item_id=item["id"], modality="reading", drill_type="translation",
            correct=False, user_answer=answer, expected_answer=expected_hanzi,
            error_type="vocab", error_cause="production_vocab", feedback=feedback,
        )


# ── Sentence construction drill ──────────────────────────────

def run_sentence_build_drill(item: dict, conn, show_fn, input_fn,
                             prominent: bool = True, english_level: str = "full") -> DrillResult:
    """Sentence build: show English meaning + key word, user types full Chinese sentence.

    If a matching sentence template is available (from sentence_templates.json),
    uses multi-answer grading with partial credit. Otherwise falls back to
    single-answer exact match.
    """
    hanzi = item.get("hanzi", "").strip()
    english = item.get("english", "").strip()
    pinyin = item.get("pinyin", "").strip()

    if not hanzi or not english:
        return None

    # Try to find a sentence template matching this item's HSK level
    hsk_level = item.get("hsk_level", 0)
    templates = _load_sentence_templates()
    matching = [t for t in templates if t.get("hsk_level") == hsk_level] if templates else []
    template = random.choice(matching) if matching else None

    if template:
        # Template-based drill: use template's prompt and multi-answer grading
        prompt_en = template.get("prompt_en", english)
        key_hint = template.get("key_word_hint", "")

        # When English is faded, show pinyin prompt instead
        if english_level != "full":
            show_fn(f"\n  Say in Chinese: [bold]{pinyin}[/bold]")
        else:
            show_fn(f"\n  Say in Chinese: [bold]{prompt_en}[/bold]")
        if key_hint:
            show_fn(f"  Key word: {format_hanzi_inline(key_hint)}\n")
        else:
            show_fn("")

        best_answer = template.get("acceptable_answers", [hanzi])[0]
        hint_stage = 0
        hints_used = 0
        while True:
            answer = input_fn("  sentence> ").strip()

            if answer.upper() in ("Q", "B"):
                return _skip_result(item, "reading", "sentence_build", answer)

            conf_result = _handle_confidence(answer, item, "reading", "sentence_build",
                                             best_answer, show_fn, english_level=english_level,
                                             allow_hint=True)
            if conf_result == "HINT":
                hint_text, hint_stage = get_progressive_hint(item, hint_stage)
                show_fn(hint_text)
                hints_used += 1
                continue
            if conf_result:
                return conf_result

            score, feedback, correct = grade_sentence_production(answer, template)
            if hints_used and correct:
                score = min(score, 0.5)
            if not feedback and not correct:
                feedback = f"  \u2192 {format_hanzi_inline(best_answer)}"

            return DrillResult(
                content_item_id=item["id"], modality="reading", drill_type="sentence_build",
                correct=correct, user_answer=answer, expected_answer=best_answer,
                error_type=None if correct else "grammar", feedback=feedback,
                score=score, confidence="half" if hints_used and correct else "full",
            )

    # Fallback: original single-answer logic
    if " " in hanzi:
        parts = [w for w in hanzi.split() if w.strip()]
    else:
        parts = [hanzi[i:i+2] for i in range(0, len(hanzi), 2)]

    if not parts:
        return None

    key_word = random.choice(parts)

    # When English is faded, show pinyin prompt instead
    if english_level != "full":
        show_fn(f"\n  Say in Chinese: [bold]{pinyin}[/bold]")
    else:
        show_fn(f"\n  Say in Chinese: [bold]{english}[/bold]")
    show_fn(f"  Key word: {format_hanzi_inline(key_word)}\n")

    hint_stage = 0
    hints_used = 0
    while True:
        answer = input_fn("  sentence> ").strip()

        if answer.upper() in ("Q", "B"):
            return _skip_result(item, "reading", "sentence_build", answer)

        conf_result = _handle_confidence(answer, item, "reading", "sentence_build",
                                         hanzi, show_fn, english_level=english_level,
                                         allow_hint=True)
        if conf_result == "HINT":
            hint_text, hint_stage = get_progressive_hint(item, hint_stage)
            show_fn(hint_text)
            hints_used += 1
            continue
        if conf_result:
            return conf_result

        expected_norm = hanzi.replace(" ", "")
        answer_norm = answer.replace(" ", "")

        if answer_norm == expected_norm:
            correct = True
            confidence = "half" if hints_used else "full"
        elif all(ch in answer_norm for ch in expected_norm):
            correct = False
            confidence = "half"
        else:
            correct = False
            confidence = "full"

        feedback = ""
        if not correct:
            feedback = format_answer_feedback(item, english_level)

        return DrillResult(
            content_item_id=item["id"], modality="reading", drill_type="sentence_build",
            correct=correct, user_answer=answer, expected_answer=hanzi,
            error_type=None if correct else "grammar", feedback=feedback,
            confidence=confidence, score=0.5 if hints_used and correct else None,
        )


# ── Word order drill ──────────────────────────────

def run_word_order_drill(item: dict, conn, show_fn, input_fn,
                         prominent: bool = True, english_level: str = "full") -> DrillResult:
    """Word order: show English + jumbled Chinese words, user arranges correctly."""
    hanzi = item.get("hanzi", "").strip()
    english = item.get("english", "").strip()
    pinyin = item.get("pinyin", "").strip()

    if not hanzi or not english:
        return None

    # Split hanzi into individual words/characters
    # For multi-character words separated by spaces, use space splitting;
    # otherwise split into individual characters
    if " " in hanzi:
        words = [w for w in hanzi.split() if w.strip()]
    else:
        # Single-character split for compact hanzi strings
        words = list(hanzi)

    # Need at least 2 pieces to shuffle meaningfully
    if len(words) < 2:
        return None

    # Shuffle until the order differs from original
    jumbled = words[:]
    attempts = 0
    while jumbled == words and attempts < 10:
        random.shuffle(jumbled)
        attempts += 1

    # Display — when English is faded, show pinyin instead
    show_fn(f"\n  Arrange in correct Chinese word order:")
    if english_level != "full":
        show_fn(f"  Pinyin: [bold]{pinyin}[/bold]\n")
    else:
        show_fn(f"  English: [bold]{english}[/bold]\n")
    show_fn(f"  Words: {format_hanzi_inline('  '.join(jumbled))}\n")

    hint_stage = 0
    hints_used = 0
    while True:
        answer = input_fn("  order> ").strip()

        if answer.upper() in ("Q", "B"):
            return _skip_result(item, "reading", "word_order", answer)

        conf_result = _handle_confidence(answer, item, "reading", "word_order",
                                         hanzi, show_fn, english_level=english_level,
                                         allow_hint=True)
        if conf_result == "HINT":
            hint_text, hint_stage = get_progressive_hint(item, hint_stage)
            show_fn(hint_text)
            hints_used += 1
            continue
        if conf_result:
            return conf_result

        # Normalize both: strip spaces for comparison
        expected_norm = hanzi.replace(" ", "")
        answer_norm = answer.replace(" ", "")

        correct = answer_norm == expected_norm
        feedback = ""
        if not correct:
            feedback = f"  \u2192 Correct order: {format_hanzi_inline(hanzi)}"
            if english_level in ("full", "feedback_only"):
                feedback += f"\n  = {english}"

        return DrillResult(
            content_item_id=item["id"], modality="reading", drill_type="word_order",
            correct=correct, user_answer=answer, expected_answer=hanzi,
            error_type=None if correct else "grammar", feedback=feedback,
            confidence="half" if hints_used and correct else "full",
            score=0.5 if hints_used and correct else None,
        )
