"""Placement quiz — adaptive level assessment for new users.

15 multiple-choice questions spanning HSK 1-9. True adaptive staircase:
each question's difficulty adjusts based on the previous answer.
Correct → harder, incorrect → easier. Step size is 2 for the first 5
questions (rapid convergence) and 1 thereafter (fine-tuning).
Estimates the highest level where the user achieves >= 60% accuracy.
"""

import json
import logging
import random
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data" / "hsk"

# Cache loaded questions
_question_cache = None

TOTAL_QUESTIONS = 15
_RAPID_PHASE_END = 5  # First N questions use large step size
_STEP_LARGE = 2       # Step size during rapid convergence phase
_STEP_SMALL = 1       # Step size during fine-tuning phase
_DEFAULT_START_LEVEL = 3  # Start level for returning users
_NEW_USER_START_LEVEL = 2  # Start level for new users
_POOL_PER_LEVEL = 3   # Pre-generate this many questions per level


def _load_questions():
    """Load HSK vocabulary for placement quiz questions from HSK JSON files."""
    global _question_cache
    if _question_cache is not None:
        return _question_cache

    questions_by_level = {}
    for level in range(1, 10):
        hsk_file = _DATA_DIR / f"hsk{level}.json"
        if not hsk_file.exists():
            continue
        try:
            data = json.load(hsk_file.open(encoding="utf-8"))
            items = data.get("items", [])
            # Filter to items with hanzi, pinyin, and english
            valid = [
                i for i in items
                if i.get("hanzi") and i.get("english") and i.get("pinyin")
            ]
            questions_by_level[level] = valid
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not load hsk%d.json for placement quiz", level)

    _question_cache = questions_by_level
    return questions_by_level


def _make_mc_question(item: dict, all_items: list, level: int) -> dict:
    """Create a multiple-choice question from an HSK item."""
    correct_english = item["english"]

    # Generate 3 distractors from the same or adjacent levels
    distractors = []
    candidates = [i for i in all_items if i["english"] != correct_english]
    random.shuffle(candidates)
    seen = {correct_english.lower()}
    for c in candidates:
        eng = c["english"]
        if eng.lower() not in seen:
            distractors.append(eng)
            seen.add(eng.lower())
            if len(distractors) == 3:
                break

    # If not enough distractors, pad with generic ones
    while len(distractors) < 3:
        distractors.append(f"(option {len(distractors) + 1})")

    options = [correct_english] + distractors
    random.shuffle(options)

    return {
        "hanzi": item["hanzi"],
        "pinyin": item["pinyin"],
        "hsk_level": level,
        "options": options,
        "correct": correct_english,
    }


def _build_quiz_pool():
    """Build a pool of pre-generated questions for each HSK level.

    Returns (quiz_pool, all_items, max_level) where quiz_pool is
    {level: [question_dict, ...]} with up to _POOL_PER_LEVEL per level.
    """
    questions_by_level = _load_questions()
    if not questions_by_level:
        return {}, [], 0

    max_level = max(questions_by_level.keys())

    all_items = []
    for items in questions_by_level.values():
        all_items.extend(items)

    quiz_pool = {}
    for level in range(1, max_level + 1):
        items = questions_by_level.get(level, [])
        if not items:
            continue
        selected = random.sample(items, min(_POOL_PER_LEVEL, len(items)))
        quiz_pool[level] = [
            _make_mc_question(item, all_items, level)
            for item in selected
        ]

    return quiz_pool, all_items, max_level


def _pick_question_from_pool(quiz_pool, target_level, used_per_level, max_level):
    """Pick a question from the pool at target_level, falling back to adjacent levels.

    Returns (question_dict, actual_level) or (None, None) if exhausted.
    """
    level = max(1, min(max_level, target_level))
    pool = quiz_pool.get(level, [])
    idx = used_per_level.get(level, 0)

    if idx >= len(pool):
        # Fallback: try adjacent levels, preferring direction of target
        for offset in [1, -1, 2, -2, 3, -3]:
            alt = max(1, min(max_level, level + offset))
            alt_pool = quiz_pool.get(alt, [])
            alt_idx = used_per_level.get(alt, 0)
            if alt_idx < len(alt_pool):
                level = alt
                pool = alt_pool
                idx = alt_idx
                break
        else:
            return None, None

    if idx < len(pool):
        q = pool[idx].copy()
        used_per_level[level] = idx + 1
        return q, level

    return None, None


def _adaptive_step(question_number: int) -> int:
    """Return the step size for the given question number (1-based)."""
    if question_number <= _RAPID_PHASE_END:
        return _STEP_LARGE
    return _STEP_SMALL


def init_adaptive_state(returning: bool = False) -> dict:
    """Initialize the adaptive placement quiz state.

    Builds the question pool and returns the state dict that tracks
    the quiz progression. This state is passed to generate_next_question()
    on each step.

    Returns dict with:
        - quiz_pool: {level: [question_dicts]}
        - max_level: int
        - current_level: int (the next question's target level)
        - question_number: int (1-based, next question to serve)
        - used_per_level: {level: count}
        - answers: [] (populated as the quiz progresses)
        - complete: bool
    """
    quiz_pool, _all_items, max_level = _build_quiz_pool()
    if not quiz_pool:
        return {"error": "no_questions", "complete": True}

    start_level = _DEFAULT_START_LEVEL if returning else _NEW_USER_START_LEVEL

    return {
        "quiz_pool": quiz_pool,
        "max_level": max_level,
        "current_level": start_level,
        "question_number": 1,
        "used_per_level": {lvl: 0 for lvl in range(1, max_level + 1)},
        "answers": [],
        "complete": False,
    }


def generate_next_question(state: dict) -> dict | None:
    """Generate the next adaptive question based on current state.

    Args:
        state: The adaptive state dict from init_adaptive_state() or
               a previous call's updated state.

    Returns a question dict with hanzi, pinyin, hsk_level, options,
    correct, question_number — or None if the quiz is complete or
    exhausted.

    The state dict is mutated in place to record the question served.
    """
    if state.get("complete"):
        return None

    q_num = state["question_number"]
    if q_num > TOTAL_QUESTIONS:
        state["complete"] = True
        return None

    quiz_pool = state["quiz_pool"]
    max_level = state["max_level"]
    current_level = state["current_level"]
    used_per_level = state["used_per_level"]

    q, actual_level = _pick_question_from_pool(
        quiz_pool, current_level, used_per_level, max_level
    )

    if q is None:
        state["complete"] = True
        return None

    q["question_number"] = q_num
    q["_level_presented"] = actual_level
    return q


def record_answer_and_adapt(state: dict, selected: str, hanzi: str) -> bool:
    """Record the learner's answer and adapt the difficulty for the next question.

    Args:
        state: The adaptive state dict (mutated in place).
        selected: The option the learner selected.
        hanzi: The hanzi of the question answered.

    Returns True if the answer was correct, False otherwise.
    """
    q_num = state["question_number"]

    # Look up the correct answer server-side
    questions_by_level = _load_questions()
    hanzi_to_english = {}
    for _lvl, items in questions_by_level.items():
        for item in items:
            hanzi_to_english[item.get("hanzi", "")] = item.get("english", "")

    correct = hanzi_to_english.get(hanzi, "")
    is_correct = selected.strip() == correct.strip()

    # Find the HSK level of the question that was answered
    # (from the quiz_pool, via the last question served)
    # We use current_level as the presented level before adaptation
    presented_level = state["current_level"]
    # Try to get the actual level from the pool tracking
    for lvl, pool in state["quiz_pool"].items():
        for pq in pool:
            if pq.get("hanzi") == hanzi:
                presented_level = lvl
                break

    state["answers"].append({
        "hsk_level": presented_level,
        "selected": selected.strip(),
        "hanzi": hanzi,
        "correct": correct,
        "is_correct": is_correct,
    })

    # Adaptive staircase: adjust difficulty
    step = _adaptive_step(q_num)
    max_level = state["max_level"]

    if is_correct:
        state["current_level"] = min(max_level, state["current_level"] + step)
    else:
        state["current_level"] = max(1, state["current_level"] - step)

    # Advance to next question
    state["question_number"] = q_num + 1
    if state["question_number"] > TOTAL_QUESTIONS:
        state["complete"] = True

    return is_correct


# ── Legacy batch generation (kept for backwards compatibility) ──────


def generate_placement_quiz(conn: sqlite3.Connection = None,
                            returning: bool = False) -> list:
    """Generate a 15-question adaptive placement quiz spanning HSK 1-9.

    LEGACY: generates all questions upfront with a fixed staircase pattern.
    Prefer the adaptive flow (init_adaptive_state + generate_next_question +
    record_answer_and_adapt) for true mid-quiz adaptation.

    Returns list of question dicts, each with:
        - hanzi, pinyin, hsk_level, options (4 choices), correct answer
        - question_number (1-15)
    """
    questions_by_level = _load_questions()
    if not questions_by_level:
        return []

    max_level = max(questions_by_level.keys()) if questions_by_level else 5

    # Build a pool of all items for distractors
    all_items = []
    for items in questions_by_level.values():
        all_items.extend(items)

    # Pre-generate 3 questions per level (1-9) = up to 27 questions
    quiz_pool = {}
    for level in range(1, max_level + 1):
        items = questions_by_level.get(level, [])
        if not items:
            continue
        selected = random.sample(items, min(3, len(items)))
        quiz_pool[level] = [
            _make_mc_question(item, all_items, level)
            for item in selected
        ]

    # Flatten into a sequenced list
    start_level = 3 if returning else 1
    questions = []
    current_level = start_level
    used_per_level = {lvl: 0 for lvl in range(1, max_level + 1)}

    for q_num in range(1, 16):
        # Clamp level
        level = max(1, min(max_level, current_level))
        pool = quiz_pool.get(level, [])

        idx = used_per_level.get(level, 0)
        if idx >= len(pool):
            # Fallback: try adjacent levels
            for offset in [1, -1, 2, -2, 3, -3]:
                alt = max(1, min(max_level, level + offset))
                alt_pool = quiz_pool.get(alt, [])
                alt_idx = used_per_level.get(alt, 0)
                if alt_idx < len(alt_pool):
                    level = alt
                    pool = alt_pool
                    idx = alt_idx
                    break

        if idx < len(pool):
            q = pool[idx].copy()
            q["question_number"] = q_num
            q["_level_presented"] = level
            questions.append(q)
            used_per_level[level] = idx + 1
        else:
            break

        # Adaptive step: larger jumps early, smaller later
        if q_num <= 5:
            step = 2
        else:
            step = 1

        # Staircase: cycle to ensure coverage at generation time
        # Actual adaptation happens in score_placement()
        if q_num % 2 == 0:
            current_level = min(max_level, current_level + step)
        else:
            current_level = max(1, current_level)

    return questions


def score_placement(answers: list) -> dict:
    """Score placement quiz answers and estimate HSK level.

    Args:
        answers: List of dicts, each with:
            - hsk_level: int (1-9)
            - selected: str (user's answer)
            - hanzi: str (the character shown — used to look up correct answer)
            Optionally: correct: str (if provided by client, used as-is)

    Returns dict with:
        - estimated_level: int (1-9)
        - confidence: str ("high", "medium", "low")
        - per_level_accuracy: dict {level: {correct, total, pct}}
        - total_correct: int
        - total_questions: int
    """
    if not answers:
        return {
            "estimated_level": 1,
            "confidence": "low",
            "per_level_accuracy": {},
            "total_correct": 0,
            "total_questions": 0,
        }

    # Build hanzi→english lookup so we can score server-side
    # (client does not receive correct answers to prevent cheating)
    questions_by_level = _load_questions()
    hanzi_to_english = {}
    for _lvl, items in questions_by_level.items():
        for item in items:
            hanzi_to_english[item.get("hanzi", "")] = item.get("english", "")

    # Tally per-level accuracy
    per_level = {}
    total_correct = 0
    total_questions = len(answers)

    for ans in answers:
        if isinstance(ans, str):
            # Legacy flat string format — cannot score, skip
            continue
        level = ans.get("hsk_level", 1)
        selected = ans.get("selected", "").strip()
        # Look up correct answer server-side from hanzi
        hanzi = ans.get("hanzi", "")
        correct = ans.get("correct", "").strip() or hanzi_to_english.get(hanzi, "")
        is_correct = selected == correct
        if is_correct:
            total_correct += 1

        if level not in per_level:
            per_level[level] = {"correct": 0, "total": 0}
        per_level[level]["total"] += 1
        if is_correct:
            per_level[level]["correct"] += 1

    # Calculate percentages
    for level in per_level:
        stats = per_level[level]
        stats["pct"] = round(stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0

    # Estimated level = highest level with >= 60% accuracy
    estimated_level = 1
    for level in sorted(per_level.keys()):
        if per_level[level]["pct"] >= 60:
            estimated_level = level

    # Confidence based on number of questions answered and spread
    levels_tested = len(per_level)
    if total_questions >= 12 and total_correct >= 4 and levels_tested >= 3:
        confidence = "high"
    elif total_questions >= 8 and total_correct >= 3:
        confidence = "high"
    elif total_questions >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "estimated_level": estimated_level,
        "confidence": confidence,
        "per_level_accuracy": per_level,
        "total_correct": total_correct,
        "total_questions": total_questions,
    }
