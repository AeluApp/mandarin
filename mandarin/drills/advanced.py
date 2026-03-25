"""Advanced drill implementations: intuition, register, pragmatic, slang, measure word, particle, homophone."""

import json
import logging
import os
import random
import threading
from pathlib import Path
from typing import Optional

from .base import (
    DrillResult, format_hanzi, format_hanzi_inline, format_hanzi_option,
    _skip_result, _handle_confidence, _run_mc_input,
)
from .hints import get_hanzi_hint
from .mc import run_mc_drill

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")


def _load_json(filename):
    with open(os.path.join(_DATA_DIR, filename)) as f:
        return json.load(f)


# ── Lazy-loaded data caches ──────────────────────────────
_REGISTER_SCENARIOS_CACHE = None
_PRAGMATIC_SCENARIOS_CACHE = None
_SLANG_ITEMS_CACHE = None
_HOMOPHONE_SETS_CACHE = None
_CLOZE_CONTEXTS_CACHE = None
_SYNONYM_GROUPS_CACHE = None


def _get_register_scenarios():
    global _REGISTER_SCENARIOS_CACHE
    if _REGISTER_SCENARIOS_CACHE is None:
        _REGISTER_SCENARIOS_CACHE = _load_json("register_scenarios.json")
    return _REGISTER_SCENARIOS_CACHE


def _get_pragmatic_scenarios():
    global _PRAGMATIC_SCENARIOS_CACHE
    if _PRAGMATIC_SCENARIOS_CACHE is None:
        _PRAGMATIC_SCENARIOS_CACHE = _load_json("pragmatic_scenarios.json")
    return _PRAGMATIC_SCENARIOS_CACHE


def _get_slang_items():
    """Load slang items from slang_expressions.json, mapping fields to match drill expectations."""
    global _SLANG_ITEMS_CACHE
    if _SLANG_ITEMS_CACHE is None:
        raw = _load_json("slang_expressions.json")
        # Map slang_expressions.json fields to the shape the drill code expects:
        #   slang_expressions.json: expression, pinyin, meaning, register, hsk_level,
        #                           example_sentence, example_english, origin
        #   drill expects: slang, pinyin, meaning, formal, context
        _SLANG_ITEMS_CACHE = []
        for item in raw:
            _SLANG_ITEMS_CACHE.append({
                "slang": item["expression"],
                "pinyin": item["pinyin"],
                "meaning": item["meaning"],
                "formal": item.get("formal", item["meaning"]),
                "context": item.get("origin", ""),
            })
    return _SLANG_ITEMS_CACHE


def _get_homophone_sets():
    global _HOMOPHONE_SETS_CACHE
    if _HOMOPHONE_SETS_CACHE is None:
        _HOMOPHONE_SETS_CACHE = _load_json("homophones.json")
    return _HOMOPHONE_SETS_CACHE


def _get_cloze_contexts():
    global _CLOZE_CONTEXTS_CACHE
    if _CLOZE_CONTEXTS_CACHE is None:
        try:
            _CLOZE_CONTEXTS_CACHE = _load_json("cloze_contexts.json")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("Could not load cloze_contexts.json: %s", e)
            _CLOZE_CONTEXTS_CACHE = []
    return _CLOZE_CONTEXTS_CACHE


def _get_synonym_groups():
    global _SYNONYM_GROUPS_CACHE
    if _SYNONYM_GROUPS_CACHE is None:
        try:
            _SYNONYM_GROUPS_CACHE = _load_json("synonym_groups.json")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("Could not load synonym_groups.json: %s", e)
            _SYNONYM_GROUPS_CACHE = []
    return _SYNONYM_GROUPS_CACHE


# ── Intuition drill ──────────────────────────────

def run_intuition_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True, user_id: int = 1) -> DrillResult:
    """Intuition drill: 'which sounds most natural?'

    Present the correct phrase plus 2 subtly wrong variants.
    Track results in progress.intuition_attempts / intuition_correct.
    """
    correct_hanzi = item["hanzi"]
    correct_english = item["english"]

    # Generate variants by swapping word order or changing particles
    variants = _generate_intuition_variants(correct_hanzi)
    options = variants + [correct_hanzi]
    # Deduplicate (variants might match original for short items)
    options = list(dict.fromkeys(options))
    if len(options) < 2:
        # Can't make meaningful variants — fall back to MC
        return run_mc_drill(item, conn, show_fn, input_fn)

    random.shuffle(options)

    show_fn(f"\n  Which sounds most natural for: {correct_english}?\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt)}")

    result = _run_mc_input(item, options, correct_hanzi, "reading", "intuition", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_hanzi
    feedback = ""
    if not correct:
        feedback = f"  \u2192 {format_hanzi_inline(correct_hanzi)} ({item['pinyin']}) = {correct_english}"

    # Update intuition tracking
    conn.execute("""
        INSERT INTO progress (user_id, content_item_id, modality)
        VALUES (?, ?, 'reading')
        ON CONFLICT(user_id, content_item_id, modality) DO NOTHING
    """, (user_id, item["id"]))
    conn.execute("""
        UPDATE progress SET
            intuition_attempts = intuition_attempts + 1,
            intuition_correct = intuition_correct + ?
        WHERE user_id = ? AND content_item_id = ? AND modality = 'reading'
    """, (1 if correct else 0, user_id, item["id"]))

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="intuition",
        correct=correct, user_answer=user_picked, expected_answer=correct_hanzi,
        error_type=None if correct else "grammar", feedback=feedback,
    )


def _generate_intuition_variants(hanzi: str) -> list:
    """Generate linguistically plausible wrong variants of a Chinese phrase.

    Strategies (tried in order, first 2 valid variants returned):
    1. Adverb displacement -- move 很/都/也/就/才/已经 after the verb
    2. Particle substitution -- swap 了/过/着 with each other
    3. Measure word errors -- swap common measure words with wrong ones
    4. Verb-object reversal -- reverse 2-char verb-object compounds
    5. Negation displacement -- move 不/没 to wrong position

    Falls back to naive character manipulation for very short phrases or
    when no linguistic strategy produces a distinct variant.
    """
    variants: list[str] = []

    def _add(v: str) -> None:
        """Append variant if it differs from original and isn't a duplicate."""
        if v != hanzi and v not in variants:
            variants.append(v)

    # -- Strategy 1: Adverb displacement --
    # Common pre-verbal adverbs that learners misplace after the verb.
    _ADVERBS = ["\u5df2\u7ecf", "\u5f88", "\u90fd", "\u4e5f", "\u5c31", "\u624d"]
    for adv in _ADVERBS:
        if len(variants) >= 2:
            break
        idx = hanzi.find(adv)
        if idx == -1:
            continue
        after_adv = idx + len(adv)
        # There must be at least one character after the adverb (the verb)
        if after_adv >= len(hanzi):
            continue
        # Move adverb to end of phrase (after the verb+object).
        before = hanzi[:idx]
        after = hanzi[after_adv:]
        _add(before + after + adv)

    # -- Strategy 2: Particle substitution --
    # Swap aspect particles 了/过/着 with each other (common L2 error).
    _PARTICLES = {"\u4e86": "\u8fc7", "\u8fc7": "\u7740", "\u7740": "\u4e86"}
    for orig_p, swap_p in _PARTICLES.items():
        if len(variants) >= 2:
            break
        idx = hanzi.find(orig_p)
        if idx == -1:
            continue
        _add(hanzi[:idx] + swap_p + hanzi[idx + len(orig_p):])

    # -- Strategy 3: Measure word errors --
    # Swap a measure word with a wrong one (e.g., 一本书 -> 一个书).
    _MW_MAP = {
        "\u4e2a": "\u672c", "\u672c": "\u4e2a", "\u676f": "\u4e2a", "\u5757": "\u4e2a",
        "\u6761": "\u4e2a", "\u5f20": "\u4e2a", "\u53ea": "\u4e2a",
    }
    for mw, wrong_mw in _MW_MAP.items():
        if len(variants) >= 2:
            break
        idx = hanzi.find(mw)
        if idx == -1:
            continue
        # Measure word typically follows a number or 一/二/三/几/两/这/那
        if idx > 0 and hanzi[idx - 1] in "\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u51e0\u4e24\u8fd9\u90a3\u6bcf":
            _add(hanzi[:idx] + wrong_mw + hanzi[idx + len(mw):])

    # -- Strategy 4: Verb-object reversal --
    # For exactly 2-character strings, reverse them (开门 -> 门开).
    if len(hanzi) == 2 and len(variants) < 2:
        _add(hanzi[::-1])

    # -- Strategy 5: Negation displacement --
    # Move 不/没 from pre-verbal to sentence-initial (不我喜欢 style).
    _NEGATIONS = ["\u6ca1\u6709", "\u4e0d", "\u6ca1"]
    for neg in _NEGATIONS:
        if len(variants) >= 2:
            break
        idx = hanzi.find(neg)
        if idx == -1 or idx == 0:
            continue
        # Pull negation to the front of the string
        without = hanzi[:idx] + hanzi[idx + len(neg):]
        _add(neg + without)

    # -- Fallback: naive character manipulation --
    # Used when no linguistic strategy fired (e.g., very short phrases).
    chars = list(hanzi)
    if len(variants) < 2 and len(chars) >= 4:
        v = chars.copy()
        mid = len(v) // 2
        v[mid - 1], v[mid] = v[mid], v[mid - 1]
        _add("".join(v))

    if len(variants) < 2 and len(chars) >= 2:
        _add(hanzi[::-1])

    return variants[:2]


# ── Register choice drill ──────────────────────────────




def run_register_choice_drill(item: dict, conn, show_fn, input_fn,
                              prominent: bool = True) -> DrillResult:
    """Register choice: pick the most appropriate register for a social situation."""
    scenario = random.choice(_get_register_scenarios())
    options = scenario["options"]
    random.shuffle(options)

    show_fn(f"\n  Situation: {scenario['situation']}")
    show_fn(f"  {format_hanzi_option(scenario['situation_zh'])}\n")
    show_fn(f"  What would you say?\n")

    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt['text'])}")

    answer = input_fn("\n  > ").strip()

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, "reading", "register_choice", answer)

    best = max(options, key=lambda o: o["score"])
    conf_result = _handle_confidence(answer, item, "reading", "register_choice",
                                     best["text"], show_fn,
                                     options=[o["text"] for o in options],
                                     input_fn=input_fn)
    if conf_result:
        return conf_result

    try:
        choice = int(answer) - 1
        picked = options[choice]
    except (ValueError, IndexError):
        picked = {"text": answer, "score": 0.0, "register": "?", "feedback": ""}

    correct = picked["score"] >= 0.8
    feedback = f"  {picked['feedback']}" if picked.get("feedback") else ""
    if not correct and best["text"] != picked.get("text"):
        feedback += f"\n  Better: {format_hanzi_inline(best['text'])}"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="register_choice",
        correct=correct, user_answer=picked.get("text", answer),
        expected_answer=best["text"],
        error_type=None if correct else "register_mismatch",
        feedback=feedback, score=picked.get("score", 0.0),
    )


# ── Pragmatic drill ──────────────────────────────




def run_pragmatic_drill(item: dict, conn, show_fn, input_fn,
                        prominent: bool = True) -> DrillResult:
    """Pragmatic drill: pick the most culturally appropriate response."""
    scenario = random.choice(_get_pragmatic_scenarios())
    options = scenario["options"]
    random.shuffle(options)

    show_fn(f"\n  Situation: {scenario['situation']}")
    show_fn(f"  {format_hanzi_option(scenario['situation_zh'])}\n")
    show_fn(f"  What's the most appropriate response?\n")

    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt['text'])}")

    answer = input_fn("\n  > ").strip()

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, "reading", "pragmatic", answer)

    best = max(options, key=lambda o: o["score"])
    conf_result = _handle_confidence(answer, item, "reading", "pragmatic",
                                     best["text"], show_fn,
                                     options=[o["text"] for o in options],
                                     input_fn=input_fn)
    if conf_result:
        return conf_result

    try:
        choice = int(answer) - 1
        picked = options[choice]
    except (ValueError, IndexError):
        picked = {"text": answer, "score": 0.0, "feedback": ""}

    correct = picked["score"] >= 0.8
    feedback = f"  {picked['feedback']}" if picked.get("feedback") else ""
    if not correct and best["text"] != picked.get("text"):
        feedback += f"\n  Better: {format_hanzi_inline(best['text'])}"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="pragmatic",
        correct=correct, user_answer=picked.get("text", answer),
        expected_answer=best["text"],
        error_type=None if correct else "pragmatics_mismatch",
        feedback=feedback, score=picked.get("score", 0.0),
    )


# ── Slang exposure drill ──────────────────────────────




def run_slang_exposure_drill(item: dict, conn, show_fn, input_fn,
                             prominent: bool = True) -> DrillResult:
    """Slang exposure: learn colloquial expressions and their meanings."""
    slang_item = random.choice(_get_slang_items())

    # Randomly choose between "what does it mean" and "what's the formal version"
    if random.random() < 0.6:
        # What does it mean?
        show_fn(f"\n  What does this colloquial expression mean?\n")
        show_fn(f"  {format_hanzi(slang_item['slang'], prominent)}")

        correct_answer = slang_item["meaning"]
        distractors = [s["meaning"] for s in _get_slang_items() if s != slang_item]
        random.shuffle(distractors)
        options = distractors[:3] + [correct_answer]
        random.shuffle(options)
    else:
        # What's the formal equivalent?
        show_fn(f"\n  What's the more formal way to say:\n")
        show_fn(f"  {format_hanzi(slang_item['slang'], prominent)}")
        show_fn(f"  ({slang_item['meaning']})\n")

        correct_answer = slang_item["formal"]
        distractors = [s["formal"] for s in _get_slang_items() if s != slang_item]
        random.shuffle(distractors)
        options = distractors[:3] + [correct_answer]
        random.shuffle(options)

    for i, opt in enumerate(options, 1):
        if any('\u4e00' <= c <= '\u9fff' for c in str(opt)):
            show_fn(f"  {i}. {format_hanzi_option(opt)}")
        else:
            show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, correct_answer, "reading", "slang_exposure", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_answer
    feedback = ""
    if not correct:
        feedback = f"  \u2192 {format_hanzi_inline(slang_item['slang'])} = {slang_item['meaning']}"
    feedback += f"\n  [dim italic]{slang_item['context']}[/dim italic]"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="slang_exposure",
        correct=correct, user_answer=user_picked, expected_answer=correct_answer,
        error_type=None if correct else "vocab", feedback=feedback,
    )


# ── Measure word drill ──────────────────────────────

_MEASURE_WORDS_CACHE = None
_measure_words_lock = threading.Lock()


_CONFUSABLE_GROUPS_CACHE = None


def _load_measure_words() -> list:
    """Load measure words from data/measure_words.json with inline fallback.

    The JSON may be a flat list (legacy) or an object with ``classifiers``
    and ``confusable_groups`` keys (enriched format).
    """
    global _MEASURE_WORDS_CACHE, _CONFUSABLE_GROUPS_CACHE
    if _MEASURE_WORDS_CACHE is not None:
        return _MEASURE_WORDS_CACHE

    with _measure_words_lock:
        if _MEASURE_WORDS_CACHE is not None:
            return _MEASURE_WORDS_CACHE

        mw_path = Path(__file__).parent.parent.parent / "data" / "measure_words.json"
        try:
            with open(mw_path) as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                _MEASURE_WORDS_CACHE = raw.get("classifiers", [])
                _CONFUSABLE_GROUPS_CACHE = raw.get("confusable_groups", {})
            else:
                _MEASURE_WORDS_CACHE = raw
                _CONFUSABLE_GROUPS_CACHE = {}
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning("Could not load measure_words.json; using inline fallback")
            _MEASURE_WORDS_CACHE = [
                {"classifier": "\u4e2a", "pinyin": "g\u00e8", "meaning": "general classifier",
                 "nouns": [{"hanzi": "\u4eba", "english": "person"}, {"hanzi": "\u82f9\u679c", "english": "apple"}]},
                {"classifier": "\u672c", "pinyin": "b\u011bn", "meaning": "books/bound items",
                 "nouns": [{"hanzi": "\u4e66", "english": "book"}, {"hanzi": "\u6742\u5fd7", "english": "magazine"}]},
                {"classifier": "\u676f", "pinyin": "b\u0113i", "meaning": "cups/glasses of liquid",
                 "nouns": [{"hanzi": "\u6c34", "english": "water"}, {"hanzi": "\u5496\u5561", "english": "coffee"}]},
                {"classifier": "\u53ea", "pinyin": "zh\u012b", "meaning": "animals / one of a pair",
                 "nouns": [{"hanzi": "\u732b", "english": "cat"}, {"hanzi": "\u72d7", "english": "dog"}]},
                {"classifier": "\u5f20", "pinyin": "zh\u0101ng", "meaning": "flat objects",
                 "nouns": [{"hanzi": "\u7eb8", "english": "paper"}, {"hanzi": "\u684c\u5b50", "english": "table"}]},
                {"classifier": "\u6761", "pinyin": "ti\u00e1o", "meaning": "long/narrow things",
                 "nouns": [{"hanzi": "\u8def", "english": "road"}, {"hanzi": "\u9c7c", "english": "fish"}]},
                {"classifier": "\u4ef6", "pinyin": "ji\u00e0n", "meaning": "clothing/matters",
                 "nouns": [{"hanzi": "\u8863\u670d", "english": "clothing"}, {"hanzi": "\u4e8b", "english": "matter"}]},
            ]
            _CONFUSABLE_GROUPS_CACHE = {}
        return _MEASURE_WORDS_CACHE


def _load_confusable_groups() -> dict:
    """Return confusable groups (loads measure words data if needed)."""
    global _CONFUSABLE_GROUPS_CACHE
    if _CONFUSABLE_GROUPS_CACHE is None:
        _load_measure_words()
    return _CONFUSABLE_GROUPS_CACHE or {}


def _build_noun_to_mw_map(mw_data: list) -> dict:
    """Build a lookup: noun_hanzi -> {measure_word, pinyin, meaning, usage_example}.

    Reads from both the enriched ``nouns`` field (preferred) and the original
    ``examples`` field (fallback: strips leading 一+classifier from phrases
    like "一本书" → "书").

    First mapping wins -- earlier entries in the JSON are the primary classifier.
    """
    mapping = {}
    for entry in mw_data:
        mw = entry.get("classifier") or entry.get("measure_word", "")
        mw_pinyin = entry.get("pinyin", "")
        mw_meaning = entry.get("meaning", "")

        # Prefer explicit nouns list when available
        nouns = entry.get("nouns", [])
        if nouns:
            for noun in nouns:
                noun_hanzi = noun["hanzi"]
                if noun_hanzi in mapping:
                    continue
                example = f"\u4e00{mw}{noun_hanzi}"
                mapping[noun_hanzi] = {
                    "measure_word": mw,
                    "pinyin": mw_pinyin,
                    "meaning": mw_meaning,
                    "example": example,
                }
        else:
            # Parse nouns from example phrases: "一本书" → "书"
            for ex in entry.get("examples", []):
                phrase = ex.get("hanzi", "")
                # Strip leading number characters + classifier
                stripped = phrase
                # Remove leading digits / 一二三四五六七八九十几两这那每
                while stripped and stripped[0] in "一二三四五六七八九十几两这那每0123456789":
                    stripped = stripped[1:]
                # Remove the classifier itself
                if stripped.startswith(mw):
                    stripped = stripped[len(mw):]
                noun_hanzi = stripped.strip()
                if not noun_hanzi or noun_hanzi in mapping:
                    continue
                mapping[noun_hanzi] = {
                    "measure_word": mw,
                    "pinyin": mw_pinyin,
                    "meaning": mw_meaning,
                    "example": phrase,
                }
    return mapping


def _find_correct_mw(item: dict, noun_map: dict) -> dict | None:
    """Look up the correct measure word info for an item. Returns None if not found."""
    hanzi = item.get("hanzi", "").strip()
    correct_info = noun_map.get(hanzi)
    if not correct_info:
        for noun_hanzi, info in noun_map.items():
            if noun_hanzi in hanzi:
                correct_info = info
                break
    return correct_info


def _get_mw_entry(mw: str, mw_data: list) -> dict | None:
    """Find the full entry for a measure word character."""
    for e in mw_data:
        if (e.get("classifier") or e.get("measure_word", "")) == mw:
            return e
    return None


def _get_confusable_distractors(correct_mw: str, mw_data: list,
                                 confusable_groups: dict, n: int = 3) -> list:
    """Pick distractors from same confusable group first, then same category, then random."""
    distractors = []

    # 1. Same confusable group
    for _gname, group in confusable_groups.items():
        if correct_mw in group.get("classifiers", []):
            for mw in group["classifiers"]:
                if mw != correct_mw and mw not in distractors:
                    distractors.append(mw)
            break

    # 2. Same category
    if len(distractors) < n:
        correct_entry = _get_mw_entry(correct_mw, mw_data)
        correct_cat = correct_entry.get("category", "") if correct_entry else ""
        if correct_cat:
            for e in mw_data:
                mw = e.get("classifier") or e.get("measure_word", "")
                if mw != correct_mw and mw not in distractors and e.get("category") == correct_cat:
                    distractors.append(mw)

    # 3. Random fill
    if len(distractors) < n:
        all_mws = list({e.get("classifier") or e.get("measure_word", "") for e in mw_data})
        remaining = [mw for mw in all_mws if mw != correct_mw and mw not in distractors]
        random.shuffle(remaining)
        distractors.extend(remaining)

    random.shuffle(distractors)
    return distractors[:n]


def _get_semantic_feedback(correct_mw: str, user_mw: str, mw_data: list,
                            confusable_groups: dict) -> str:
    """Build semantic feedback for a wrong answer.

    Returns the semantic_rule for the correct classifier.
    If user picked from the same confusable group, also returns the discrimination_tip.
    """
    parts = []

    # Semantic rule for correct answer
    correct_entry = _get_mw_entry(correct_mw, mw_data)
    if correct_entry and correct_entry.get("semantic_rule"):
        parts.append(f"  {format_hanzi_inline(correct_mw)}: {correct_entry['semantic_rule']}")

    # Check if both are in the same confusable group
    for _gname, group in confusable_groups.items():
        classifiers = group.get("classifiers", [])
        if correct_mw in classifiers and user_mw in classifiers:
            tip = group.get("discrimination_tip", "")
            if tip:
                parts.append(f"  [dim italic]Tip: {tip}[/dim italic]")
            break

    return "\n".join(parts)


def run_measure_word_drill(item: dict, conn, show_fn, input_fn,
                           prominent: bool = True) -> DrillResult:
    """Measure word MC: show a noun, pick the correct classifier from 4 options."""
    mw_data = _load_measure_words()
    confusable_groups = _load_confusable_groups()
    noun_map = _build_noun_to_mw_map(mw_data)

    hanzi = item.get("hanzi", "").strip()
    english = item.get("english", "").strip()
    hsk_level = item.get("hsk_level", 0) or 0

    correct_info = _find_correct_mw(item, noun_map)
    if not correct_info:
        return None

    correct_mw = correct_info["measure_word"]

    # Intelligent distractors from confusable groups
    distractors = _get_confusable_distractors(correct_mw, mw_data, confusable_groups, n=3)

    # For HSK 1-2: ensure 个 is a distractor (learners over-generalize it)
    if hsk_level <= 2 and correct_mw != "\u4e2a" and "\u4e2a" not in distractors:
        distractors[-1] = "\u4e2a"

    options = [correct_mw] + distractors
    if len(options) < 2:
        return None
    random.shuffle(options)

    # Display
    show_fn(f"\n  What measure word goes with {format_hanzi_inline(hanzi)} ({english})?\n")
    for i, opt in enumerate(options, 1):
        opt_entry = _get_mw_entry(opt, mw_data)
        opt_meaning = opt_entry.get("meaning", "") if opt_entry else ""
        show_fn(f"  {i}. {format_hanzi_option(opt)}  [dim]({opt_meaning})[/dim]")

    result = _run_mc_input(item, options, correct_mw, "reading", "measure_word", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_mw
    feedback = ""
    if not correct:
        feedback = (f"  \u2192 {format_hanzi_inline(correct_mw)} ({correct_info['pinyin']})"
                    f" \u2014 {correct_info['meaning']}")
        feedback += f"\n  Usage: {correct_info['example']}"
        semantic = _get_semantic_feedback(correct_mw, user_picked, mw_data, confusable_groups)
        if semantic:
            feedback += f"\n{semantic}"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="measure_word",
        correct=correct, user_answer=user_picked, expected_answer=correct_mw,
        error_type=None if correct else "measure_word", feedback=feedback,
    )


def run_measure_word_cloze_drill(item: dict, conn, show_fn, input_fn,
                                  prominent: bool = True) -> DrillResult:
    """Measure word cloze: fill in the blank classifier in a full sentence."""
    mw_data = _load_measure_words()
    confusable_groups = _load_confusable_groups()
    noun_map = _build_noun_to_mw_map(mw_data)

    correct_info = _find_correct_mw(item, noun_map)
    if not correct_info:
        return None

    correct_mw = correct_info["measure_word"]
    correct_entry = _get_mw_entry(correct_mw, mw_data)

    # Try to find a sentence from the data
    sentence = None
    if correct_entry and correct_entry.get("sentences"):
        candidates = [s for s in correct_entry["sentences"]
                      if correct_mw in s.get("zh", "")]
        if candidates:
            picked = random.choice(candidates)
            sentence = picked["zh"]

    # Fallback: construct "他买了一____<noun>"
    if not sentence:
        hanzi = item.get("hanzi", "").strip()
        sentence = f"\u4ed6\u4e70\u4e86\u4e00{correct_mw}{hanzi}\u3002"

    blanked = sentence.replace(correct_mw, "____", 1)

    # Distractors from confusable group
    distractors = _get_confusable_distractors(correct_mw, mw_data, confusable_groups, n=3)
    options = [correct_mw] + distractors
    if len(options) < 2:
        return None
    random.shuffle(options)

    show_fn(f"\n  Fill in the measure word:")
    show_fn(f"  {format_hanzi_inline(blanked)}\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt)}")

    result = _run_mc_input(item, options, correct_mw, "reading", "measure_word_cloze", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_mw
    feedback = ""
    if not correct:
        feedback = f"  \u2192 {format_hanzi_inline(sentence)}"
        semantic = _get_semantic_feedback(correct_mw, user_picked, mw_data, confusable_groups)
        if semantic:
            feedback += f"\n{semantic}"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="measure_word_cloze",
        correct=correct, user_answer=user_picked, expected_answer=correct_mw,
        error_type=None if correct else "measure_word", feedback=feedback,
    )


def run_measure_word_production_drill(item: dict, conn, show_fn, input_fn,
                                       prominent: bool = True) -> DrillResult:
    """Measure word production: type the correct classifier for a noun."""
    mw_data = _load_measure_words()
    confusable_groups = _load_confusable_groups()
    noun_map = _build_noun_to_mw_map(mw_data)

    hanzi = item.get("hanzi", "").strip()
    english = item.get("english", "").strip()

    correct_info = _find_correct_mw(item, noun_map)
    if not correct_info:
        return None

    correct_mw = correct_info["measure_word"]
    correct_pinyin = correct_info["pinyin"]
    correct_entry = _get_mw_entry(correct_mw, mw_data)

    show_fn(f"\n  Type the measure word for {format_hanzi_inline(hanzi)} ({english})")
    show_fn(f"  [dim](Enter hanzi or pinyin. ? for hint, N to skip)[/dim]\n")

    # Progressive hints
    hints_given = 0
    while True:
        answer = input_fn("  > ").strip()

        if answer.upper() in ("Q", "B"):
            return _skip_result(item, "reading", "measure_word_production", answer)

        if answer.upper() == "N":
            return _skip_result(item, "reading", "measure_word_production", "N")

        if answer == "?":
            hints_given += 1
            if hints_given == 1:
                # Category hint
                cat = correct_entry.get("category", "") if correct_entry else ""
                show_fn(f"  Hint: category is '{cat}'")
            elif hints_given == 2:
                # Semantic rule
                rule = correct_entry.get("semantic_rule", "") if correct_entry else ""
                if rule:
                    show_fn(f"  Hint: {rule}")
                else:
                    show_fn(f"  Hint: {correct_info['meaning']}")
            else:
                # Pinyin first letter
                if correct_pinyin:
                    show_fn(f"  Hint: pinyin starts with '{correct_pinyin[0]}'")
            continue

        # Check answer: accept hanzi or pinyin
        correct = (answer == correct_mw or
                   answer.lower() == correct_pinyin.lower().replace("\u0304", "").replace("\u0301", "").replace("\u030c", "").replace("\u0300", ""))
        # Also accept exact pinyin with tones
        if not correct and answer.lower() == correct_pinyin.lower():
            correct = True

        feedback = ""
        if not correct:
            feedback = (f"  \u2192 {format_hanzi_inline(correct_mw)} ({correct_pinyin})"
                        f" \u2014 {correct_info['meaning']}")
            semantic = _get_semantic_feedback(correct_mw, answer, mw_data, confusable_groups)
            if semantic:
                feedback += f"\n{semantic}"

        return DrillResult(
            content_item_id=item["id"], modality="reading", drill_type="measure_word_production",
            correct=correct, user_answer=answer, expected_answer=correct_mw,
            error_type=None if correct else "measure_word", feedback=feedback,
        )


def run_measure_word_discrimination_drill(item: dict, conn, show_fn, input_fn,
                                            prominent: bool = True) -> DrillResult:
    """Measure word discrimination: 'Which noun uses 条?' — binary MC."""
    mw_data = _load_measure_words()
    confusable_groups = _load_confusable_groups()
    noun_map = _build_noun_to_mw_map(mw_data)

    correct_info = _find_correct_mw(item, noun_map)
    if not correct_info:
        return None

    correct_mw = correct_info["measure_word"]
    target_noun = item.get("hanzi", "").strip()
    target_english = item.get("english", "").strip()

    # Find a confusable noun (uses a different classifier from same group)
    wrong_noun = None
    wrong_noun_en = None
    for _gname, group in confusable_groups.items():
        classifiers = group.get("classifiers", [])
        if correct_mw not in classifiers:
            continue
        # Find nouns that use a different classifier in this group
        for other_mw in classifiers:
            if other_mw == correct_mw:
                continue
            for noun_h, info in noun_map.items():
                if info["measure_word"] == other_mw and noun_h != target_noun:
                    wrong_noun = noun_h
                    wrong_noun_en = ""
                    # Try to find English from mw_data nouns
                    other_entry = _get_mw_entry(other_mw, mw_data)
                    if other_entry:
                        for n in other_entry.get("nouns", []):
                            if n["hanzi"] == noun_h:
                                wrong_noun_en = n["english"]
                                break
                    break
            if wrong_noun:
                break
        break

    if not wrong_noun:
        # Fallback: pick any noun that uses a different classifier
        candidates = [(nh, info) for nh, info in noun_map.items()
                      if info["measure_word"] != correct_mw and nh != target_noun]
        if not candidates:
            return None
        wrong_noun, wrong_info = random.choice(candidates)
        wrong_entry = _get_mw_entry(wrong_info["measure_word"], mw_data)
        wrong_noun_en = ""
        if wrong_entry:
            for n in wrong_entry.get("nouns", []):
                if n["hanzi"] == wrong_noun:
                    wrong_noun_en = n["english"]
                    break

    # Build binary MC
    correct_label = f"{format_hanzi_inline(target_noun)}"
    if target_english:
        correct_label += f" ({target_english})"
    wrong_label = f"{format_hanzi_inline(wrong_noun)}"
    if wrong_noun_en:
        wrong_label += f" ({wrong_noun_en})"

    options = [target_noun, wrong_noun]
    labels = {target_noun: correct_label, wrong_noun: wrong_label}
    random.shuffle(options)

    show_fn(f"\n  Which one uses {format_hanzi_inline(correct_mw)}?\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {labels[opt]}")

    result = _run_mc_input(item, options, target_noun, "reading", "measure_word_disc", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == target_noun
    feedback = ""
    if not correct:
        feedback = f"  \u2192 {format_hanzi_inline(correct_mw)} + {format_hanzi_inline(target_noun)}"
        # Show discrimination tip
        for _gname, group in confusable_groups.items():
            if correct_mw in group.get("classifiers", []):
                tip = group.get("discrimination_tip", "")
                if tip:
                    feedback += f"\n  [dim italic]Tip: {tip}[/dim italic]"
                break

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="measure_word_disc",
        correct=correct, user_answer=user_picked, expected_answer=target_noun,
        error_type=None if correct else "measure_word", feedback=feedback,
    )


# ── Particle discrimination drill ──────────────────────────────

# Particle sets for discrimination drills
_PARTICLE_SETS = {
    "aspect": {
        "particles": ["\u4e86", "\u8fc7", "\u7740"],
        "label": "Aspect (completed / experienced / ongoing)",
    },
    "de": {
        "particles": ["\u7684", "\u5730", "\u5f97"],
        "label": "De (possessive / adverbial / complement)",
    },
    "question": {
        "particles": ["\u5417", "\u5462", "\u5427"],
        "label": "Question (yes-no / follow-up / suggestion)",
    },
    "conjunction": {
        "particles": ["\u548c", "\u6216", "\u8fd8\u662f"],
        "label": "Connector (and / or / or-question)",
    },
}


def run_particle_disc_drill(item: dict, conn, show_fn, input_fn,
                            prominent: bool = True) -> DrillResult:
    """Particle discrimination: blank out a particle in a sentence, user picks the right one."""
    hanzi = item.get("hanzi", "").strip()
    english = item.get("english", "").strip()

    if not hanzi:
        return None

    # Find which particle set applies to this item
    matched_set_key = None
    matched_particle = None

    for set_key, pset in _PARTICLE_SETS.items():
        for particle in pset["particles"]:
            if particle in hanzi:
                matched_set_key = set_key
                matched_particle = particle
                break
        if matched_set_key:
            break

    if not matched_set_key or not matched_particle:
        # Item doesn't contain any particle from our sets -- signal skip
        return None

    pset = _PARTICLE_SETS[matched_set_key]
    particles = pset["particles"]

    # Build the blanked sentence: replace the first occurrence of the particle with ____
    blanked = hanzi.replace(matched_particle, "____", 1)

    # Display
    show_fn(f"\n  Fill in the blank \u2014 {pset['label']}:")
    show_fn(f"  {format_hanzi_inline(blanked)}")
    if english:
        show_fn(f"  ({english})\n")
    else:
        show_fn("")

    # Show particle options
    options = particles[:]
    random.shuffle(options)
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt)}")

    result = _run_mc_input(item, options, matched_particle, "reading", "particle_disc", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == matched_particle
    feedback = ""
    if not correct:
        feedback = f"  \u2192 {format_hanzi_inline(matched_particle)} in: {format_hanzi_inline(hanzi)}"
        if english:
            feedback += f"\n  = {english}"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="particle_disc",
        correct=correct, user_answer=user_picked, expected_answer=matched_particle,
        error_type=None if correct else "grammar", feedback=feedback,
    )


# ── Homophone drill ──────────────────────────────

# Characters sharing the same pinyin but different hanzi and meanings.



def run_homophone_drill(item: dict, conn, show_fn, input_fn,
                        prominent: bool = True, **kwargs) -> DrillResult:
    """Homophone discrimination: pick the correct character for a context.

    Shows a sentence with a blank where a homophone goes, and the learner
    picks which character fits. Specifically targets 的/地/得, 在/再,
    做/作/坐/座, and other common confusions.
    """
    hanzi = item.get("hanzi") or ""

    # Find which homophone set contains a character from this item
    matched_set = None
    matched_char = None
    for _set_key, hset in _get_homophone_sets().items():
        for entry in hset["chars"]:
            if entry["hanzi"] in hanzi:
                matched_set = hset
                matched_char = entry
                break
        if matched_set:
            break

    if not matched_set or not matched_char:
        # Fallback to MC if item doesn't contain a known homophone
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    # Build the drill: show the example sentence with a blank
    example = matched_char["example"]
    target = matched_char["hanzi"]
    blanked = example.replace(target, "___", 1)

    show_fn(f"\n  Fill in the blank:")
    show_fn(f"  {format_hanzi(blanked, prominent)}")
    show_fn(f"  ({matched_char['example_en']})\n")

    # Show options from the homophone set
    options = [c["hanzi"] for c in matched_set["chars"]]
    random.shuffle(options)
    for i, opt in enumerate(options, 1):
        role = next(c["role"] for c in matched_set["chars"] if c["hanzi"] == opt)
        show_fn(f"  {i}. {format_hanzi_option(opt)} \u2014 {role}")

    result = _run_mc_input(item, options, target, "reading", "homophone", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == target
    feedback = ""
    if not correct:
        feedback = (
            f"  \u2192 {format_hanzi_inline(target)} ({matched_char['role']})\n"
            f"  Rule: {matched_char['rule']}\n"
            f"  Example: {format_hanzi_inline(example)} = {matched_char['example_en']}"
        )
    else:
        # Even on correct, reinforce the rule
        feedback = f"  [dim]{matched_char['rule']}[/dim]"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="homophone",
        correct=correct, user_answer=user_picked, expected_answer=target,
        error_type=None if correct else "vocab", feedback=feedback,
    )


# ── Cloze context drill ──────────────────────────────

def run_cloze_context_drill(item: dict, conn, show_fn, input_fn,
                            prominent: bool = True) -> DrillResult:
    """Cloze context: show a sentence with a blank, pick the word that fits.

    Tests contextual vocabulary and grammar across all HSK levels.
    Data comes from cloze_contexts.json.
    """
    hsk_level = item.get("hsk_level", 0)
    contexts = _get_cloze_contexts()
    if not contexts:
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    # Find cloze items matching this HSK level
    matching = [c for c in contexts if c.get("hsk_level") == hsk_level]
    if not matching:
        # Try nearby levels
        matching = [c for c in contexts
                    if abs(c.get("hsk_level", 0) - hsk_level) <= 1]
    if not matching:
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    cloze = random.choice(matching)
    sentence = cloze.get("sentence_zh", cloze.get("sentence", ""))
    answer = cloze.get("blank_answer", cloze.get("answer", ""))
    options = list(cloze.get("options", []))

    if not sentence or not answer or len(options) < 2:
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    # Ensure answer is in options
    if answer not in options:
        options.append(answer)
    random.shuffle(options)

    # Display
    show_fn(f"\n  Fill in the blank:")
    show_fn(f"  {format_hanzi_inline(sentence)}\n")

    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt)}")

    result = _run_mc_input(item, options, answer, "reading", "cloze_context",
                           show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == answer
    feedback = ""
    if not correct:
        filled = sentence.replace("____", f"[{answer}]")
        feedback = f"  → {format_hanzi_inline(filled)}"
        explanation = cloze.get("explanation", "")
        if explanation:
            feedback += f"\n  {explanation}"

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="cloze_context",
        correct=correct, user_answer=user_picked, expected_answer=answer,
        error_type=None if correct else "vocab", feedback=feedback,
    )


# ── Synonym discrimination drill ──────────────────────────────

def run_synonym_disc_drill(item: dict, conn, show_fn, input_fn,
                           prominent: bool = True) -> DrillResult:
    """Synonym discrimination: which near-synonym fits this context?

    Tests fine distinctions between words like 了解/理解/明白.
    Only triggered for items at stabilizing mastery or above.
    Data comes from synonym_groups.json.
    """
    hanzi = item.get("hanzi", "").strip()
    groups = _get_synonym_groups()
    if not groups:
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    # Find a synonym group containing this item's hanzi
    matched_group = None
    for group in groups:
        words = [w.get("word", "") for w in group.get("words", [])]
        if hanzi in words:
            matched_group = group
            break

    if not matched_group:
        # Try matching by any word in the item
        for group in groups:
            words = [w.get("word", "") for w in group.get("words", [])]
            for w in words:
                if w in hanzi or hanzi in w:
                    matched_group = group
                    break
            if matched_group:
                break

    if not matched_group:
        # Fall back to a random group at the item's HSK level
        hsk_level = item.get("hsk_level", 0)
        level_groups = [g for g in groups if g.get("hsk_level", 0) == hsk_level]
        if not level_groups:
            level_groups = [g for g in groups
                           if abs(g.get("hsk_level", 0) - hsk_level) <= 1]
        if level_groups:
            matched_group = random.choice(level_groups)

    if not matched_group:
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    # Pick a test sentence from the group
    test_sentences = matched_group.get("test_sentences", [])
    if not test_sentences:
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    test = random.choice(test_sentences)
    sentence = test.get("sentence", "")
    correct_word = test.get("answer", "")
    words_data = matched_group.get("words", [])
    options = [w.get("word", "") for w in words_data if w.get("word")]

    if not sentence or not correct_word or len(options) < 2:
        return run_mc_drill(item, conn, show_fn, input_fn, prominent=prominent)

    if correct_word not in options:
        options.append(correct_word)
    random.shuffle(options)

    # Display
    group_label = matched_group.get("group_name", "")
    show_fn(f"\n  Which word fits?")
    if group_label:
        show_fn(f"  [dim]({group_label})[/dim]")
    show_fn(f"  {format_hanzi_inline(sentence)}\n")

    for i, opt in enumerate(options, 1):
        # Find the meaning for this option
        meaning = ""
        for w in words_data:
            if w.get("word") == opt:
                meaning = w.get("meaning", "")
                break
        if meaning:
            show_fn(f"  {i}. {format_hanzi_option(opt)} — {meaning}")
        else:
            show_fn(f"  {i}. {format_hanzi_option(opt)}")

    result = _run_mc_input(item, options, correct_word, "reading", "synonym_disc",
                           show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_word
    feedback = ""
    if not correct:
        filled = sentence.replace("____", correct_word)
        feedback = f"  → {format_hanzi_inline(filled)}"
        # Show the distinction
        explanation = test.get("explanation", "")
        if explanation:
            feedback += f"\n  {explanation}"
        # Show correct word's nuance
        for w in words_data:
            if w.get("word") == correct_word:
                nuance = w.get("nuance", w.get("meaning", ""))
                feedback += f"\n  {format_hanzi_inline(correct_word)}: {nuance}"
                break
    else:
        # Reinforce distinction on correct answer
        for w in words_data:
            if w.get("word") == correct_word:
                nuance = w.get("nuance", "")
                if nuance:
                    feedback = f"  [dim]{nuance}[/dim]"
                break

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="synonym_disc",
        correct=correct, user_answer=user_picked, expected_answer=correct_word,
        error_type=None if correct else "vocab", feedback=feedback,
    )


# ── Lazy-loaded caches for new drills ──────────────────────────────
_TONE_SANDHI_CACHE = None
_COLLOCATIONS_CACHE = None
_CHENGYU_CACHE = None


def _get_tone_sandhi():
    global _TONE_SANDHI_CACHE
    if _TONE_SANDHI_CACHE is None:
        _TONE_SANDHI_CACHE = _load_json("tone_sandhi.json")
        if isinstance(_TONE_SANDHI_CACHE, dict):
            _TONE_SANDHI_CACHE = _TONE_SANDHI_CACHE.get("entries", [])
    return _TONE_SANDHI_CACHE


def _get_collocations():
    global _COLLOCATIONS_CACHE
    if _COLLOCATIONS_CACHE is None:
        _COLLOCATIONS_CACHE = _load_json("collocations.json")
        if isinstance(_COLLOCATIONS_CACHE, dict):
            _COLLOCATIONS_CACHE = _COLLOCATIONS_CACHE.get("entries", [])
    return _COLLOCATIONS_CACHE


def _get_chengyu():
    global _CHENGYU_CACHE
    if _CHENGYU_CACHE is None:
        _CHENGYU_CACHE = _load_json("chengyu.json")
        if isinstance(_CHENGYU_CACHE, dict):
            _CHENGYU_CACHE = _CHENGYU_CACHE.get("entries", [])
    return _CHENGYU_CACHE


# ── Tone Sandhi Drill ──────────────────────────────

def run_tone_sandhi_drill(item: dict, conn, show_fn, input_fn,
                          prominent: bool = True) -> DrillResult | None:
    """How is this word actually pronounced? Tests tone sandhi rules."""
    entries = _get_tone_sandhi()
    item_level = item.get("hsk_level") or 3

    candidates = [e for e in entries if (e.get("hsk_level") or 1) <= item_level]
    if not candidates:
        return None

    entry = random.choice(candidates)
    word = entry["word"]
    correct = entry["pinyin_sandhi"]
    base_pinyin = entry["pinyin_base"]
    entry.get("rule", "")

    # Build options: correct sandhi + base form + 2 plausible alternatives
    options = [correct]
    if base_pinyin != correct:
        options.append(base_pinyin)

    # Generate plausible alternatives from other entries
    other_pinyins = [e["pinyin_sandhi"] for e in entries
                     if e["pinyin_sandhi"] != correct and e["pinyin_sandhi"] != base_pinyin]
    random.shuffle(other_pinyins)
    for p in other_pinyins:
        if len(options) >= 4:
            break
        if p not in options:
            options.append(p)

    # Pad with base if needed
    while len(options) < 4 and base_pinyin not in options:
        options.append(base_pinyin)
        break

    options = options[:4]
    random.shuffle(options)

    show_fn(f"\n  How is {format_hanzi_inline(word)} actually pronounced?", prominent=prominent)
    show_fn("")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, correct, "reading", "tone_sandhi", show_fn, input_fn)
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
        drill_type="tone_sandhi", correct=is_correct,
        user_answer=user_picked, expected_answer=correct,
        error_type=None if is_correct else "tone",
        feedback=feedback,
    )


# ── Collocation Drill ──────────────────────────────

def run_collocation_drill(item: dict, conn, show_fn, input_fn,
                          prominent: bool = True) -> DrillResult | None:
    """Which verb goes with this object? Tests verb-object collocations."""
    entries = _get_collocations()
    item_level = item.get("hsk_level") or 3

    candidates = [e for e in entries if (e.get("hsk_level") or 1) <= item_level]
    if not candidates:
        return None

    entry = random.choice(candidates)
    verb = entry["verb"]
    obj = entry["object"]
    meaning = entry["meaning"]
    confusables = list(entry.get("confusables", []))

    correct = verb
    options = [correct] + confusables[:3]
    random.shuffle(options)

    show_fn(f"\n  Which verb goes with {format_hanzi_inline(obj)}?", prominent=prominent)
    show_fn(f"  ({meaning})")
    show_fn("")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_inline(opt)}")

    result = _run_mc_input(item, options, correct, "reading", "collocation", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    is_correct = (user_picked == correct)

    feedback = ""
    if not is_correct:
        feedback = f"  → {format_hanzi_inline(verb + obj)}"
    literal = entry.get("literal", "")
    if literal:
        feedback += f"\n  [dim]Literal: {literal}[/dim]"
    example = entry.get("example", "")
    if example:
        feedback += f"\n  {format_hanzi_inline(example)}"

    return DrillResult(
        content_item_id=item["id"], modality="reading",
        drill_type="collocation", correct=is_correct,
        user_answer=user_picked, expected_answer=correct,
        error_type=None if is_correct else "vocab",
        feedback=feedback,
    )


# ── Radical Drill ──────────────────────────────

def run_radical_drill(item: dict, conn, show_fn, input_fn,
                      prominent: bool = True) -> DrillResult | None:
    """Radical identification — two sub-formats:
    1. Given a character, identify its radical
    2. Given a radical, identify which character contains it
    """
    # Load radicals data (flat list, not versioned)
    try:
        radicals = _load_json("radicals.json")
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    if not radicals:
        return None

    # Pick sub-format
    sub_format = random.choice(["identify_radical", "identify_character"])

    if sub_format == "identify_radical":
        # Pick a radical that has examples
        with_examples = [r for r in radicals if r.get("examples")]
        if not with_examples:
            return None

        entry = random.choice(with_examples)
        radical = entry["radical"]
        meaning = entry.get("meaning", "")
        examples = entry.get("examples", [])

        if not examples:
            return None

        # Pick a character from this radical's examples
        target_char = random.choice(examples)
        correct = radical

        # Pick 3 other radicals as distractors
        other_radicals = [r["radical"] for r in radicals
                         if r["radical"] != radical]
        random.shuffle(other_radicals)
        distractors = other_radicals[:3]

        options = [correct] + distractors
        random.shuffle(options)

        show_fn(f"\n  What is the radical of {format_hanzi_inline(target_char)}?", prominent=prominent)
        show_fn("")
        for i, opt in enumerate(options):
            opt_entry = next((r for r in radicals if r["radical"] == opt), None)
            label = f"{opt}"
            if opt_entry and opt_entry.get("meaning"):
                label += f" ({opt_entry['meaning']})"
            show_fn(f"  {i+1}. {label}")

    else:  # identify_character
        entry = random.choice([r for r in radicals if r.get("examples")])
        radical = entry["radical"]
        meaning = entry.get("meaning", "")
        examples = entry.get("examples", [])

        if not examples:
            return None

        correct = random.choice(examples)

        # Distractors: chars from OTHER radicals
        other_chars = []
        for r in radicals:
            if r["radical"] != radical and r.get("examples"):
                other_chars.extend(r["examples"])
        random.shuffle(other_chars)
        distractors = other_chars[:3]

        options = [correct] + distractors
        random.shuffle(options)

        hint = f" ({meaning})" if meaning else ""
        show_fn(f"\n  Which character contains the radical {radical}{hint}?", prominent=prominent)
        show_fn("")
        for i, opt in enumerate(options):
            show_fn(f"  {i+1}. {format_hanzi_inline(opt)}")

    result = _run_mc_input(item, options, correct, "reading", "radical", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    is_correct = (user_picked == correct)

    feedback = ""
    if not is_correct:
        feedback = f"  → {correct}"
        if sub_format == "identify_radical" and meaning:
            feedback += f" ({meaning})"

    return DrillResult(
        content_item_id=item["id"], modality="reading",
        drill_type="radical", correct=is_correct,
        user_answer=user_picked, expected_answer=correct,
        error_type=None if is_correct else "vocab",
        feedback=feedback,
    )


# ── Chengyu Drill ──────────────────────────────

def run_chengyu_drill(item: dict, conn, show_fn, input_fn,
                      prominent: bool = True) -> DrillResult | None:
    """Chengyu (4-character idiom) drill — two sub-formats:
    1. Meaning MC: show chengyu → pick meaning
    2. Fill-in-blank: show 3 of 4 characters → pick the missing one
    """
    entries = _get_chengyu()
    item_level = item.get("hsk_level") or 5

    candidates = [e for e in entries if (e.get("hsk_level") or 1) <= item_level]
    if not candidates:
        return None

    entry = random.choice(candidates)
    chengyu = entry["chengyu"]
    meaning = entry["meaning"]
    pinyin = entry.get("pinyin", "")
    literal = entry.get("literal", "")
    characters = entry.get("characters", list(chengyu))

    sub_format = random.choice(["meaning", "fill_blank"])

    if sub_format == "meaning":
        correct = meaning
        # Build distractors from other entries' meanings
        other_meanings = [e["meaning"] for e in entries if e["meaning"] != meaning]
        random.shuffle(other_meanings)
        distractors = other_meanings[:3]

        options = [correct] + distractors
        random.shuffle(options)

        show_fn(f"\n  What does {format_hanzi_inline(chengyu)} mean?", prominent=prominent)
        if pinyin:
            show_fn(f"  [{pinyin}]")
        show_fn("")
        for i, opt in enumerate(options):
            show_fn(f"  {i+1}. {opt}")

    else:  # fill_blank
        if len(characters) != 4:
            # Fall back to meaning format
            return run_chengyu_drill(item, conn, show_fn, input_fn, prominent)

        # Remove one character
        blank_idx = random.randint(0, 3)
        correct = characters[blank_idx]
        display_chars = list(characters)
        display_chars[blank_idx] = "____"
        display = "".join(display_chars)

        # Distractors: other single characters
        all_chars = set()
        for e in entries:
            for c in e.get("characters", list(e["chengyu"])):
                all_chars.add(c)
        all_chars.discard(correct)
        distractors = random.sample(list(all_chars), min(3, len(all_chars)))

        options = [correct] + distractors
        random.shuffle(options)

        show_fn(f"\n  Fill in the missing character:", prominent=prominent)
        show_fn(f"  {format_hanzi_inline(display)}")
        if meaning:
            show_fn(f"  ({meaning})")
        show_fn("")
        for i, opt in enumerate(options):
            show_fn(f"  {i+1}. {format_hanzi_inline(opt)}")

    result = _run_mc_input(item, options, correct, "reading", "chengyu", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    is_correct = (user_picked == correct)

    feedback = ""
    if not is_correct:
        if sub_format == "meaning":
            feedback = f"  → {meaning}"
        else:
            feedback = f"  → {format_hanzi_inline(chengyu)}"
    if literal:
        feedback += f"\n  [dim]Literal: {literal}[/dim]"
    example = entry.get("example", "")
    if example:
        feedback += f"\n  {format_hanzi_inline(example)}"

    return DrillResult(
        content_item_id=item["id"], modality="reading",
        drill_type="chengyu", correct=is_correct,
        user_answer=user_picked,
        expected_answer=correct,
        error_type=None if is_correct else "vocab",
        feedback=feedback,
    )
