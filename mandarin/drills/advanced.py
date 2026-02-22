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

def run_intuition_drill(item: dict, conn, show_fn, input_fn, prominent: bool = True) -> DrillResult:
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
        INSERT INTO progress (content_item_id, modality)
        VALUES (?, 'reading')
        ON CONFLICT(content_item_id, modality) DO NOTHING
    """, (item["id"],))
    conn.execute("""
        UPDATE progress SET
            intuition_attempts = intuition_attempts + 1,
            intuition_correct = intuition_correct + ?
        WHERE content_item_id = ? AND modality = 'reading'
    """, (1 if correct else 0, item["id"]))

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


def _load_measure_words() -> list:
    """Load measure words from data/measure_words.json with inline fallback."""
    global _MEASURE_WORDS_CACHE
    if _MEASURE_WORDS_CACHE is not None:
        return _MEASURE_WORDS_CACHE

    with _measure_words_lock:
        if _MEASURE_WORDS_CACHE is not None:
            return _MEASURE_WORDS_CACHE

        mw_path = Path(__file__).parent.parent.parent / "data" / "measure_words.json"
        try:
            with open(mw_path) as f:
                _MEASURE_WORDS_CACHE = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning("Could not load measure_words.json; using inline fallback")
            # Inline fallback -- small set of common HSK 1-2 measure words
            _MEASURE_WORDS_CACHE = [
                {"measure_word": "\u4e2a", "pinyin": "g\u00e8", "meaning": "general classifier",
                 "nouns": [{"hanzi": "\u4eba", "english": "person"}, {"hanzi": "\u82f9\u679c", "english": "apple"}]},
                {"measure_word": "\u672c", "pinyin": "b\u011bn", "meaning": "books/bound items",
                 "nouns": [{"hanzi": "\u4e66", "english": "book"}, {"hanzi": "\u6742\u5fd7", "english": "magazine"}]},
                {"measure_word": "\u676f", "pinyin": "b\u0113i", "meaning": "cups/glasses of liquid",
                 "nouns": [{"hanzi": "\u6c34", "english": "water"}, {"hanzi": "\u5496\u5561", "english": "coffee"}]},
                {"measure_word": "\u53ea", "pinyin": "zh\u012b", "meaning": "animals / one of a pair",
                 "nouns": [{"hanzi": "\u732b", "english": "cat"}, {"hanzi": "\u72d7", "english": "dog"}]},
                {"measure_word": "\u5f20", "pinyin": "zh\u0101ng", "meaning": "flat objects",
                 "nouns": [{"hanzi": "\u7eb8", "english": "paper"}, {"hanzi": "\u684c\u5b50", "english": "table"}]},
                {"measure_word": "\u6761", "pinyin": "ti\u00e1o", "meaning": "long/narrow things",
                 "nouns": [{"hanzi": "\u8def", "english": "road"}, {"hanzi": "\u9c7c", "english": "fish"}]},
                {"measure_word": "\u4ef6", "pinyin": "ji\u00e0n", "meaning": "clothing/matters",
                 "nouns": [{"hanzi": "\u8863\u670d", "english": "clothing"}, {"hanzi": "\u4e8b", "english": "matter"}]},
            ]
        return _MEASURE_WORDS_CACHE


def _build_noun_to_mw_map(mw_data: list) -> dict:
    """Build a lookup: noun_hanzi -> {measure_word, pinyin, meaning, usage_example}.

    First mapping wins -- earlier entries in the JSON are the primary classifier.
    """
    mapping = {}
    for entry in mw_data:
        mw = entry["measure_word"]
        mw_pinyin = entry.get("pinyin", "")
        mw_meaning = entry.get("meaning", "")
        for noun in entry.get("nouns", []):
            noun_hanzi = noun["hanzi"]
            if noun_hanzi in mapping:
                continue  # keep primary classifier
            example = f"\u4e00{mw}{noun_hanzi}"
            mapping[noun_hanzi] = {
                "measure_word": mw,
                "pinyin": mw_pinyin,
                "meaning": mw_meaning,
                "example": example,
            }
    return mapping


def run_measure_word_drill(item: dict, conn, show_fn, input_fn,
                           prominent: bool = True) -> DrillResult:
    """Measure word MC: show a noun, pick the correct classifier from 4 options."""
    mw_data = _load_measure_words()
    noun_map = _build_noun_to_mw_map(mw_data)

    hanzi = item.get("hanzi", "").strip()
    english = item.get("english", "").strip()

    # Find the correct measure word for this item's hanzi
    # Check if item hanzi is a known noun, or if any known noun is a substring
    correct_info = noun_map.get(hanzi)
    if not correct_info:
        # Try matching any known noun contained in the item hanzi
        for noun_hanzi, info in noun_map.items():
            if noun_hanzi in hanzi:
                correct_info = info
                break

    if not correct_info:
        # Item not in measure word mapping -- cannot drill, return None to signal skip
        return None

    correct_mw = correct_info["measure_word"]

    # Build 4 options: correct + 3 distractors from different measure words
    all_mws = list({e["measure_word"] for e in mw_data})
    distractors = [mw for mw in all_mws if mw != correct_mw]
    random.shuffle(distractors)
    distractors = distractors[:3]

    # Ensure we have at least 2 total options
    options = [correct_mw] + distractors
    if len(options) < 2:
        return None
    random.shuffle(options)

    # Display
    show_fn(f"\n  What measure word goes with {format_hanzi_inline(hanzi)} ({english})?\n")
    for i, opt in enumerate(options, 1):
        # Find the meaning for this measure word
        opt_meaning = ""
        for e in mw_data:
            if e["measure_word"] == opt:
                opt_meaning = e.get("meaning", "")
                break
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

    return DrillResult(
        content_item_id=item["id"], modality="reading", drill_type="measure_word",
        correct=correct, user_answer=user_picked, expected_answer=correct_mw,
        error_type=None if correct else "vocab", feedback=feedback,
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
    for set_key, hset in _get_homophone_sets().items():
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
