"""Listening drill implementations."""

import json
import logging
import os
import random
import re
import threading

from .base import (
    DrillResult, format_hanzi, format_hanzi_inline,
    format_answer_feedback,
    _skip_result, _handle_confidence, _run_mc_input,
    cause_to_error_type, classify_error_cause, elaborate_error,
)
from .mc import generate_mc_options
from .tone import _generate_tone_options
from .production import char_overlap_score

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")

# ── Reading passages cache ──────────────────────────────
_READING_PASSAGES_CACHE = None
_reading_passages_lock = threading.Lock()


def _load_reading_passages():
    """Load reading passages from data/reading_passages.json."""
    global _READING_PASSAGES_CACHE
    if _READING_PASSAGES_CACHE is not None:
        return _READING_PASSAGES_CACHE
    with _reading_passages_lock:
        if _READING_PASSAGES_CACHE is not None:
            return _READING_PASSAGES_CACHE
        path = os.path.join(_DATA_DIR, "reading_passages.json")
        try:
            with open(path) as f:
                data = json.load(f)
                _READING_PASSAGES_CACHE = data.get("passages", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("Could not load reading_passages.json: %s", e)
            _READING_PASSAGES_CACHE = []
        return _READING_PASSAGES_CACHE


# ── Detail question generation ──────────────────────────────

def generate_detail_question(english: str) -> str:
    """Generate a detail question based on the English translation content."""
    eng_lower = english.lower()
    # Number detection
    for word in eng_lower.split():
        if word.isdigit():
            return "How many?"
    number_words = ["one", "two", "three", "four", "five", "six", "seven", "eight",
                    "nine", "ten", "several", "many", "few", "some"]
    if any(w in eng_lower.split() for w in number_words):
        return "How many?"
    # Time detection
    time_words = ["morning", "afternoon", "evening", "night", "o'clock", "today",
                  "tomorrow", "yesterday", "monday", "tuesday", "wednesday",
                  "thursday", "friday", "saturday", "sunday", "week", "month", "year"]
    if any(w in eng_lower for w in time_words):
        return "When?"
    # Person detection
    person_words = ["he", "she", "they", "teacher", "student", "friend", "mother",
                    "father", "brother", "sister", "doctor", "boss", "colleague"]
    if any(w in eng_lower.split() for w in person_words):
        return "Who?"
    # Location detection
    location_words = ["school", "hospital", "hotel", "restaurant", "store", "home",
                      "office", "library", "park", "station", "airport", "here", "there"]
    if any(w in eng_lower for w in location_words):
        return "Where?"
    return "What is being described?"


# ── Listening drills ──────────────────────────────

def run_listening_gist_drill(item: dict, conn, show_fn, input_fn,
                            prominent: bool = True, audio_enabled: bool = False,
                            english_level: str = "full") -> DrillResult:
    """Listening gist: listen to audio or read pinyin, pick the meaning."""
    if audio_enabled:
        from ..audio import speak_and_wait
        speak_and_wait(item["hanzi"])
        show_fn(f"\n  Listen:")
        show_fn(f"  What does this mean?\n")
    else:
        show_fn(f"\n  Listen (read the pinyin):")
        show_fn(f"  \"{item['pinyin']}\"\n")
        show_fn(f"  What does this mean?\n")

    # Listening drills always use pinyin options — forces Chinese processing
    # rather than English-to-English matching
    field = "pinyin"
    correct_answer = item["pinyin"]

    options, tier = generate_mc_options(conn, item, field=field, n_options=4)
    # Show English hint above options so learner knows what to listen for
    if english_level == "full":
        show_fn(f"  ({item.get('english', '')})\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, correct_answer, "listening", "listening_gist", show_fn, input_fn,
                           english_level=english_level)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_answer
    feedback = ""
    error_type = None
    cause = None
    if not correct:
        feedback = format_answer_feedback(item, english_level)
        # Error-cause analysis
        cause = classify_error_cause(user_picked, correct_answer, "listening_gist", item)
        elaboration = elaborate_error(cause, user_picked, correct_answer, item, "listening_gist")
        if elaboration:
            feedback += f"\n{elaboration}"
        # Add character-by-character pinyin breakdown for multi-char items
        hanzi = item.get("hanzi", "")
        pinyin_str = item.get("pinyin", "")
        if len(hanzi) >= 2:
            syllables = re.split(r"[\s\u2018\u2019]+", pinyin_str.strip())
            if len(syllables) == len(hanzi):
                pairs = [f"{h} {p}" for h, p in zip(hanzi, syllables)]
                feedback += "\n  " + " \u00b7 ".join(pairs)
        error_type = cause_to_error_type(cause, "vocab")

    return DrillResult(
        content_item_id=item["id"], modality="listening", drill_type="listening_gist",
        correct=correct, user_answer=user_picked, expected_answer=correct_answer,
        error_type=error_type, error_cause=cause, feedback=feedback,
        distractor_tier=tier,
    )


def run_listening_detail_drill(item: dict, conn, show_fn, input_fn,
                                prominent: bool = True,
                                audio_enabled: bool = False,
                                english_level: str = "full") -> DrillResult:
    """Listening detail: hear a sentence, pick specific detail (who/what/when/how many)."""
    if audio_enabled:
        from ..audio import speak_and_wait
        speak_and_wait(item["hanzi"])
        show_fn(f"\n  Listen carefully:")
    else:
        show_fn(f"\n  Listen (read the pinyin):")
        show_fn(f"  \"{item['pinyin']}\"\n")

    question = generate_detail_question(item["english"])
    show_fn(f"  {question}\n")

    # Listening drills always use pinyin options — forces Chinese processing
    field = "pinyin"
    correct_answer = item["pinyin"]

    options, tier = generate_mc_options(conn, item, field=field, n_options=4)
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, correct_answer, "listening", "listening_detail", show_fn, input_fn,
                           english_level=english_level)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_answer
    feedback = ""
    error_type = None
    cause = None
    if not correct:
        feedback = format_answer_feedback(item, english_level)
        # Error-cause analysis
        cause = classify_error_cause(user_picked, correct_answer, "listening_detail", item)
        elaboration = elaborate_error(cause, user_picked, correct_answer, item, "listening_detail")
        if elaboration:
            feedback += f"\n{elaboration}"
        error_type = cause_to_error_type(cause, "vocab")

    return DrillResult(
        content_item_id=item["id"], modality="listening", drill_type="listening_detail",
        correct=correct, user_answer=user_picked, expected_answer=correct_answer,
        error_type=error_type, error_cause=cause, feedback=feedback,
        distractor_tier=tier,
    )


def run_listening_tone_drill(item: dict, conn, show_fn, input_fn,
                              prominent: bool = True,
                              audio_enabled: bool = False) -> DrillResult:
    """Listening tone: hear a word, pick the correct toned pinyin from 4 options."""
    if audio_enabled:
        from ..audio import speak_and_wait
        speak_and_wait(item["hanzi"])
        show_fn(f"\n  Listen, then identify the tones:")
    else:
        show_fn(f"\n  Identify the tones:")

    show_fn(format_hanzi(item['hanzi'], prominent))

    correct_pinyin = item["pinyin"]
    options = _generate_tone_options(correct_pinyin)

    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, correct_pinyin, "listening", "listening_tone", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_pinyin
    feedback = ""
    error_type = None
    cause = None
    if not correct:
        feedback = f"  \u2192 {format_hanzi_inline(item['hanzi'])} = {correct_pinyin}"
        # Error-cause analysis for tone discrimination
        cause = classify_error_cause(user_picked, correct_pinyin, "listening_tone", item)
        elaboration = elaborate_error(cause, user_picked, correct_pinyin, item, "listening_tone")
        if elaboration:
            feedback += f"\n{elaboration}"
        error_type = cause_to_error_type(cause, "tone")

    return DrillResult(
        content_item_id=item["id"], modality="listening", drill_type="listening_tone",
        correct=correct, user_answer=user_picked, expected_answer=correct_pinyin,
        error_type=error_type, error_cause=cause, feedback=feedback,
    )


def run_listening_dictation_drill(item: dict, conn, show_fn, input_fn,
                                   prominent: bool = True,
                                   audio_enabled: bool = False) -> DrillResult:
    """Listening dictation: hear a word, type the hanzi."""
    if audio_enabled:
        from ..audio import speak_and_wait
        speak_and_wait(item["hanzi"])
        show_fn(f"\n  Listen and type the characters:")
    else:
        show_fn(f"\n  Write the characters for:")
        show_fn(f"  \"{item['pinyin']}\"\n")

    answer = input_fn("  hanzi> ").strip()

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, "listening", "listening_dictation", answer)

    conf_result = _handle_confidence(answer, item, "listening", "listening_dictation", item["hanzi"], show_fn)
    if conf_result:
        return conf_result

    expected = item["hanzi"].strip()
    correct = answer == expected

    feedback = ""
    cause = None
    if not correct:
        # Character-by-character comparison
        comparison = []
        for i, (exp_ch, usr_ch) in enumerate(zip(expected, answer)):
            if exp_ch == usr_ch:
                comparison.append(f"[green]{exp_ch}[/green]")
            else:
                comparison.append(f"[red]{usr_ch}\u2192{exp_ch}[/red]")
        # Handle length differences
        if len(answer) < len(expected):
            for ch in expected[len(answer):]:
                comparison.append(f"[red]_{ch}[/red]")
        elif len(answer) > len(expected):
            comparison.append(f"  [dim](extra: {answer[len(expected):]})[/dim]")

        feedback = f"  \u2192 {format_hanzi_inline(expected)} ({item['pinyin']}) = {item['english']}"
        if comparison:
            feedback += f"\n  {''.join(comparison)}"
        # Error-cause analysis
        cause = classify_error_cause(answer, expected, "listening_dictation", item)
        elaboration = elaborate_error(cause, answer, expected, item, "listening_dictation")
        if elaboration:
            feedback += f"\n{elaboration}"

    return DrillResult(
        content_item_id=item["id"], modality="listening", drill_type="listening_dictation",
        correct=correct, user_answer=answer, expected_answer=expected,
        error_type=None if correct else "vocab", error_cause=cause, feedback=feedback,
    )


# ── Listening passage drill ──────────────────────────────

def run_listening_passage_drill(item: dict, conn, show_fn, input_fn,
                                prominent: bool = True,
                                audio_enabled: bool = False) -> DrillResult:
    """Listening passage: listen to a multi-sentence passage, answer comprehension question.

    Plays TTS of a passage from reading_passages.json, then asks an MC
    comprehension question. HSK 3+. Tests sustained listening.
    """
    hsk_level = item.get("hsk_level", 0)
    passages = _load_reading_passages()
    if not passages:
        return run_listening_gist_drill(item, conn, show_fn, input_fn,
                                       prominent=prominent, audio_enabled=audio_enabled)

    # Find passages at or below this HSK level
    matching = [p for p in passages if p.get("hsk_level", 0) == hsk_level
                and p.get("questions")]
    if not matching:
        matching = [p for p in passages
                    if p.get("hsk_level", 0) <= hsk_level
                    and p.get("questions")]
    if not matching:
        return run_listening_gist_drill(item, conn, show_fn, input_fn,
                                       prominent=prominent, audio_enabled=audio_enabled)

    passage = random.choice(matching)
    text_zh = passage.get("text_zh", "")
    text_pinyin = passage.get("text_pinyin", "")
    title = passage.get("title", "")

    # Pick a random comprehension question
    questions = passage.get("questions", [])
    q = random.choice(questions)
    # Prefer Chinese question when available to keep Chinese on screen
    q_text = q.get("q_zh") or q.get("q_en", "")
    q_text_en = q.get("q_en", "")
    correct_answer = q.get("answer", "")

    if not text_zh or not q_text or not correct_answer:
        return run_listening_gist_drill(item, conn, show_fn, input_fn,
                                       prominent=prominent, audio_enabled=audio_enabled)

    # Play or show the passage
    if audio_enabled:
        from ..audio import speak_and_wait
        speak_and_wait(text_zh)
        show_fn(f"\n  Listen to the passage:")
        if title:
            show_fn(f"  [dim]{title}[/dim]")
        # Show hanzi text so Chinese is on screen
        show_fn(f"  {format_hanzi_inline(text_zh)}")
    else:
        show_fn(f"\n  Read the passage (pinyin):")
        if title:
            show_fn(f"  [dim]{title}[/dim]")
        show_fn(f"  \"{text_pinyin}\"\n")

    # Show the question (prefer Chinese, fall back to English)
    show_fn(f"  {q_text}")
    if q_text_en and q_text != q_text_en:
        show_fn(f"  [dim]({q_text_en})[/dim]")
    show_fn("")

    # Generate MC options: correct + 3 distractors from other questions' answers
    options = [correct_answer]
    # Gather distractor answers from other passages/questions
    all_answers = []
    for p in passages:
        for pq in p.get("questions", []):
            a = pq.get("answer", "")
            if a and a != correct_answer:
                all_answers.append(a)
    random.shuffle(all_answers)
    for a in all_answers:
        if a not in options:
            options.append(a)
        if len(options) >= 4:
            break

    # If not enough distractors, pad
    while len(options) < 2:
        options.append("—")

    random.shuffle(options)

    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    result = _run_mc_input(item, options, correct_answer, "listening",
                           "listening_passage", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_answer
    feedback = ""
    error_type = None
    cause = None
    if not correct:
        feedback = f"  Your answer: {user_picked}\n  → Correct: {correct_answer}"
        # Show the relevant sentence from the passage
        feedback += f"\n  [dim]Passage: {format_hanzi_inline(text_zh[:80])}{'...' if len(text_zh) > 80 else ''}[/dim]"
        # Error cause analysis
        cause = classify_error_cause(user_picked, correct_answer, "listening_passage", item)
        elaboration = elaborate_error(cause, user_picked, correct_answer, item, "listening_passage")
        if elaboration:
            feedback += f"\n{elaboration}"
        error_type = cause_to_error_type(cause, "vocab")

    return DrillResult(
        content_item_id=item["id"], modality="listening", drill_type="listening_passage",
        correct=correct, user_answer=user_picked, expected_answer=correct_answer,
        error_type=error_type, error_cause=cause, feedback=feedback,
    )


# ── Dictation sentence drill ──────────────────────────────

def _edit_distance_score(expected: str, user_input: str) -> float:
    """Normalized edit distance score: 1.0 = identical, 0.0 = completely different."""
    if not expected and not user_input:
        return 1.0
    if not expected or not user_input:
        return 0.0
    m, n = len(expected), len(user_input)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if expected[i - 1] == user_input[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    distance = dp[m][n]
    max_len = max(m, n)
    return 1.0 - (distance / max_len) if max_len > 0 else 1.0


def run_dictation_sentence_drill(item: dict, conn, show_fn, input_fn,
                                 prominent: bool = True,
                                 audio_enabled: bool = False) -> DrillResult:
    """Sentence-level dictation: play/show a full sentence, user types all characters.

    Uses char_overlap_score + edit distance for partial credit grading.
    HSK 2+ for sentence/phrase/chunk items.
    """
    hanzi = item.get("hanzi", "").strip()
    pinyin = item.get("pinyin", "").strip()
    english = item.get("english", "").strip()
    item_id = item.get("id", 0)

    if not hanzi:
        return None

    # Play or show the sentence
    if audio_enabled:
        from ..audio import speak_and_wait
        speak_and_wait(hanzi)
        show_fn(f"\n  Listen and type the full sentence:")
    else:
        show_fn(f"\n  Write this sentence in Chinese:")
        show_fn(f"  \"{pinyin}\"")

    show_fn(f"  ({english})\n")

    answer = input_fn("  sentence> ").strip()

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, "ime", "dictation_sentence", answer)

    conf_result = _handle_confidence(answer, item, "ime", "dictation_sentence",
                                     hanzi, show_fn)
    if conf_result:
        return conf_result

    # Grade: combine char overlap + edit distance
    expected_norm = hanzi.replace(" ", "")
    answer_norm = answer.replace(" ", "")

    if answer_norm == expected_norm:
        return DrillResult(
            content_item_id=item_id, modality="ime", drill_type="dictation_sentence",
            correct=True, user_answer=answer, expected_answer=hanzi,
            confidence="full", score=1.0,
        )

    overlap = char_overlap_score(expected_norm, answer_norm)
    edit_score = _edit_distance_score(expected_norm, answer_norm)
    combined = 0.5 * overlap + 0.5 * edit_score

    correct = combined >= 0.7
    feedback = ""

    if combined >= 0.7:
        feedback = f"  (close — exact: {format_hanzi_inline(hanzi)})"
    else:
        # Character-by-character comparison
        comparison = []
        for i, exp_ch in enumerate(expected_norm):
            if i < len(answer_norm):
                usr_ch = answer_norm[i]
                if usr_ch == exp_ch:
                    comparison.append(f"[green]{exp_ch}[/green]")
                else:
                    comparison.append(f"[red]{usr_ch}→{exp_ch}[/red]")
        if len(answer_norm) < len(expected_norm):
            for ch in expected_norm[len(answer_norm):]:
                comparison.append(f"[red]_{ch}[/red]")
        elif len(answer_norm) > len(expected_norm):
            comparison.append(f"  [dim](extra: {answer_norm[len(expected_norm):]})[/dim]")

        feedback = f"  → {format_hanzi_inline(hanzi)} ({pinyin})"
        if comparison:
            feedback += f"\n  {''.join(comparison)}"

    return DrillResult(
        content_item_id=item_id, modality="ime", drill_type="dictation_sentence",
        correct=correct, user_answer=answer, expected_answer=hanzi,
        error_type=None if correct else "vocab", feedback=feedback,
        score=combined,
    )


# ── Minimal pair tone drill ──────────────────────────────

def _find_minimal_pairs(conn, item: dict, n: int = 1) -> list:
    """Find minimal tone pairs for a given item.

    Looks for content items with same pinyin base but different tones.
    Returns list of (item_hanzi, item_pinyin, pair_hanzi, pair_pinyin) tuples.
    """
    pinyin = item.get("pinyin", "").strip()
    hanzi = item.get("hanzi", "").strip()
    if not pinyin or not hanzi:
        return []

    # Strip tone numbers/marks to get base pinyin
    import re
    base = re.sub(r'[1-4\u0304\u0301\u030C\u0300]', '', pinyin.lower()).strip()
    if not base:
        return []

    # Search for items with similar pinyin but different tones
    rows = conn.execute("""
        SELECT hanzi, pinyin FROM content_item
        WHERE hanzi != ? AND pinyin != ?
        AND review_status = 'approved'
        AND LOWER(REPLACE(REPLACE(REPLACE(REPLACE(pinyin, '1', ''), '2', ''), '3', ''), '4', ''))
            LIKE ?
        ORDER BY RANDOM() LIMIT ?
    """, (hanzi, pinyin, f"%{base}%", n * 3)).fetchall()

    pairs = []
    for row in rows:
        p_hanzi = row["hanzi"]
        p_pinyin = row["pinyin"]
        p_base = re.sub(r'[1-4\u0304\u0301\u030C\u0300]', '', p_pinyin.lower()).strip()
        if p_base == base and p_pinyin.lower() != pinyin.lower():
            pairs.append((hanzi, pinyin, p_hanzi, p_pinyin))
            if len(pairs) >= n:
                break

    return pairs


def run_minimal_pair_drill(item: dict, conn, show_fn, input_fn,
                           prominent: bool = True,
                           audio_enabled: bool = False) -> DrillResult:
    """Minimal pair tone drill: hear two words, identify if tones are same or different.

    If different, bonus question: which tone was each?
    Tests fine-grained tone discrimination.
    """
    hanzi = item.get("hanzi", "").strip()
    pinyin = item.get("pinyin", "").strip()
    item_id = item.get("id", 0)

    # Find a minimal pair
    pairs = _find_minimal_pairs(conn, item, n=1)

    if not pairs:
        # No minimal pair found — create a same-tone scenario
        is_same = True
        word_a = hanzi
        pinyin_a = pinyin
        word_b = hanzi  # Same word
        pinyin_b = pinyin
    else:
        _, _, pair_hanzi, pair_pinyin = pairs[0]
        # Randomly decide whether to present same or different
        if random.random() < 0.4:
            # Same tone pair (play the same word twice)
            is_same = True
            word_a = hanzi
            pinyin_a = pinyin
            word_b = hanzi
            pinyin_b = pinyin
        else:
            # Different tone pair
            is_same = False
            if random.random() < 0.5:
                word_a, pinyin_a = hanzi, pinyin
                word_b, pinyin_b = pair_hanzi, pair_pinyin
            else:
                word_a, pinyin_a = pair_hanzi, pair_pinyin
                word_b, pinyin_b = hanzi, pinyin

    # Play or show the two words
    show_fn("\n  Minimal Pair: Listen to two words.")

    if audio_enabled:
        from ..audio import speak_and_wait
        import time as _time
        show_fn("  Word 1:")
        speak_and_wait(word_a)
        _time.sleep(0.5)
        show_fn("  Word 2:")
        speak_and_wait(word_b)
    else:
        show_fn(f"  Word 1: {pinyin_a}")
        show_fn(f"  Word 2: {pinyin_b}")

    show_fn("\n  Are the tones the same or different?\n")
    options = ["Same tones", "Different tones"]
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {opt}")

    correct_answer = "Same tones" if is_same else "Different tones"

    result = _run_mc_input(item, options, correct_answer, "listening",
                           "minimal_pair", show_fn, input_fn)
    if isinstance(result, DrillResult):
        return result
    user_picked = result

    correct = user_picked == correct_answer
    feedback = ""
    error_type = None

    if not correct:
        if is_same:
            feedback = f"  → Both were: {format_hanzi_inline(word_a)} ({pinyin_a})"
        else:
            feedback = (f"  → Word 1: {format_hanzi_inline(word_a)} ({pinyin_a})\n"
                       f"  → Word 2: {format_hanzi_inline(word_b)} ({pinyin_b})")
        error_type = "tone"
    else:
        if not is_same:
            feedback = (f"  Word 1: {format_hanzi_inline(word_a)} ({pinyin_a})\n"
                       f"  Word 2: {format_hanzi_inline(word_b)} ({pinyin_b})")

    return DrillResult(
        content_item_id=item_id, modality="listening", drill_type="minimal_pair",
        correct=correct, user_answer=user_picked, expected_answer=correct_answer,
        error_type=error_type, feedback=feedback,
    )


# ── Passage sentence dictation drill ──────────────────────────────

def run_passage_sentence_dictation(item: dict, conn, show_fn, input_fn,
                                   prominent: bool = True,
                                   audio_enabled: bool = False) -> DrillResult:
    """Passage sentence dictation: pick a sentence from a reading passage, play audio, type hanzi.

    Bridges listening and reading modalities. Uses passages at the learner's HSK level.
    Character-by-character grading with partial credit.
    """
    hsk_level = item.get("hsk_level", 0)
    passages = _load_reading_passages()

    if not passages:
        return run_listening_dictation_drill(item, conn, show_fn, input_fn,
                                            prominent=prominent, audio_enabled=audio_enabled)

    # Find passages at this HSK level
    matching = [p for p in passages if p.get("hsk_level", 0) == hsk_level]
    if not matching:
        matching = [p for p in passages if p.get("hsk_level", 0) <= max(hsk_level, 2)]
    if not matching:
        return run_listening_dictation_drill(item, conn, show_fn, input_fn,
                                            prominent=prominent, audio_enabled=audio_enabled)

    passage = random.choice(matching)
    text_zh = passage.get("text_zh", "")

    # Split into sentences
    sentences = re.split(r'([。！？])', text_zh)
    full_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i] + sentences[i + 1]
        if sent.strip() and len(sent.strip()) >= 2:
            full_sentences.append(sent.strip())
    if len(sentences) % 2 == 1 and sentences[-1].strip() and len(sentences[-1].strip()) >= 2:
        full_sentences.append(sentences[-1].strip())

    if not full_sentences:
        return run_listening_dictation_drill(item, conn, show_fn, input_fn,
                                            prominent=prominent, audio_enabled=audio_enabled)

    target_sentence = random.choice(full_sentences)

    # Play or show
    title = passage.get("title", "")
    if title:
        show_fn(f"  [dim]From: {title}[/dim]")

    if audio_enabled:
        from ..audio import speak_and_wait
        speak_and_wait(target_sentence)
        show_fn("\n  Listen and type the sentence:")
    else:
        # Show pinyin approximation — use passage pinyin if available
        show_fn("\n  Type this sentence in Chinese:")
        show_fn(f"  (from a passage at HSK {hsk_level})")

    answer = input_fn("  sentence> ").strip()
    item_id = item.get("id", 0)

    if answer.upper() in ("Q", "B"):
        return _skip_result(item, "listening", "passage_dictation", answer)

    conf_result = _handle_confidence(answer, item, "listening", "passage_dictation",
                                     target_sentence, show_fn)
    if conf_result:
        return conf_result

    # Grade: combine char overlap + edit distance
    expected_norm = target_sentence.replace(" ", "")
    # Remove punctuation for comparison
    expected_clean = re.sub(r'[。！？，、；：\u201c\u201d\u2018\u2019（）\s]', '', expected_norm)
    answer_clean = re.sub(r'[。！？，、；：\u201c\u201d\u2018\u2019（）\s]', '', answer)

    if answer_clean == expected_clean:
        return DrillResult(
            content_item_id=item_id, modality="listening",
            drill_type="passage_dictation",
            correct=True, user_answer=answer, expected_answer=target_sentence,
            score=1.0,
        )

    overlap = char_overlap_score(expected_clean, answer_clean)
    edit_score = _edit_distance_score(expected_clean, answer_clean)
    combined = 0.5 * overlap + 0.5 * edit_score

    correct = combined >= 0.7
    feedback = ""

    if combined >= 0.7:
        feedback = f"  (close — exact: {format_hanzi_inline(target_sentence)})"
    else:
        # Character-by-character comparison
        comparison = []
        for i, exp_ch in enumerate(expected_clean):
            if i < len(answer_clean):
                usr_ch = answer_clean[i]
                if usr_ch == exp_ch:
                    comparison.append(f"[green]{exp_ch}[/green]")
                else:
                    comparison.append(f"[red]{usr_ch}→{exp_ch}[/red]")
        if len(answer_clean) < len(expected_clean):
            for ch in expected_clean[len(answer_clean):]:
                comparison.append(f"[red]_{ch}[/red]")
        elif len(answer_clean) > len(expected_clean):
            comparison.append(f"  [dim](extra: {answer_clean[len(expected_clean):]})[/dim]")

        feedback = f"  → {format_hanzi_inline(target_sentence)}"
        if comparison:
            feedback += f"\n  {''.join(comparison)}"

    return DrillResult(
        content_item_id=item_id, modality="listening",
        drill_type="passage_dictation",
        correct=correct, user_answer=answer, expected_answer=target_sentence,
        error_type=None if correct else "vocab", feedback=feedback,
        score=combined,
    )
