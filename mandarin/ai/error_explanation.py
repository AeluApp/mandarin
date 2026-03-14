"""Error explanations for persistent mistakes via local LLM."""

from __future__ import annotations

import logging
from typing import Optional

from .ollama_client import generate, is_ollama_available

logger = logging.getLogger(__name__)

ERROR_EXPLANATION_SYSTEM = """You are a patient Mandarin Chinese tutor. A student keeps making the same mistake.

Give a brief, clear explanation (2-3 sentences max) of WHY this specific mistake happens and how to remember the correct answer. Reference the actual correct and wrong answers. Be encouraging but honest. No fluff.

Focus on:
- Why the confusion occurs (similar sounds, similar characters, false friends)
- A concrete memory aid or pattern to prevent recurrence
- Keep it short — this appears inline during practice"""

# Gate: only generate for persistent or high-value errors
_MIN_TIMES_WRONG = 3
_ALWAYS_EXPLAIN_TYPES = {"tone", "conceptual"}


def generate_error_explanation(
    conn,
    item_id: str,
    correct_answer: str,
    wrong_answer: str,
    item_content: dict,
    error_type: str = "",
    times_wrong: int = 1,
    learner_hsk_level: int = 1,
) -> Optional[str]:
    """Generate an explanation for a persistent mistake. Returns None if not applicable."""
    # Gate check
    if times_wrong < _MIN_TIMES_WRONG and error_type not in _ALWAYS_EXPLAIN_TYPES:
        return None

    if not is_ollama_available():
        return None

    # Build cache-friendly prompt
    cache_key = f"error:{item_id}:{wrong_answer}"
    prompt = _build_error_prompt(
        correct_answer, wrong_answer, item_content, error_type,
        times_wrong, learner_hsk_level,
    )

    response = generate(
        prompt=prompt,
        system=ERROR_EXPLANATION_SYSTEM,
        temperature=0.5,
        max_tokens=256,
        use_cache=True,
        conn=conn,
        task_type="error_explanation",
    )

    if not response.success:
        return None

    explanation = response.text.strip()

    # Quality check: must reference correct or wrong answer
    if correct_answer and wrong_answer:
        if correct_answer not in explanation and wrong_answer not in explanation:
            logger.debug("Error explanation doesn't reference answers, discarding")
            return None

    return explanation


def _build_error_prompt(
    correct: str, wrong: str, content: dict,
    error_type: str, times_wrong: int, hsk_level: int,
) -> str:
    parts = [
        f"The student answered '{wrong}' but the correct answer is '{correct}'.",
        f"They've gotten this wrong {times_wrong} time(s).",
    ]
    if error_type:
        parts.append(f"Error type: {error_type}")
    hanzi = content.get("hanzi", "")
    pinyin = content.get("pinyin", "")
    english = content.get("english", "")
    if hanzi:
        parts.append(f"Word: {hanzi} [{pinyin}] = {english}")
    parts.append(f"Learner HSK level: {hsk_level}")
    parts.append("Give a brief, specific explanation of why this mistake happens and how to fix it.")
    return "\n".join(parts)
