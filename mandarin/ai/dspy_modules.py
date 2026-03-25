"""DSPy modules for optimizable Mandarin learning prompts.

Wraps the existing PROMPT_REGISTRY prompt templates as DSPy Signatures
that can be auto-optimized using quality_score data from prompt_trace.
Uses LiteLLM as the LLM backend.
"""

import json
import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

_dspy_configured = False
_dspy_available: bool | None = None

# ═══════════════════════════════════════════════════════════════════════════════
# DSPy Configuration
# ═══════════════════════════════════════════════════════════════════════════════


def configure_dspy() -> bool:
    """Configure DSPy with LiteLLM backend pointing to local Ollama.

    Returns True if DSPy is configured successfully, False otherwise.
    Idempotent — safe to call multiple times.
    """
    global _dspy_configured, _dspy_available

    if _dspy_available is False:
        return False

    if _dspy_configured:
        return True

    try:
        import dspy
        from ..settings import OLLAMA_URL, OLLAMA_PRIMARY_MODEL

        lm = dspy.LM(
            model=f"ollama_chat/{OLLAMA_PRIMARY_MODEL}",
            api_base=OLLAMA_URL,
            temperature=0.5,
            max_tokens=1024,
        )
        dspy.configure(lm=lm)

        _dspy_configured = True
        _dspy_available = True
        logger.info("DSPy configured with Ollama model %s", OLLAMA_PRIMARY_MODEL)
        return True

    except ImportError:
        _dspy_available = False
        logger.debug("DSPy not installed — optimizable prompts disabled")
        return False
    except Exception as exc:
        _dspy_available = False
        logger.warning("DSPy configuration failed: %s", exc)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# DSPy Signatures
# ═══════════════════════════════════════════════════════════════════════════════

try:
    import dspy

    class DrillGeneration(dspy.Signature):
        """Generate a drill item for Mandarin spaced repetition practice.

        Given a vocabulary item with its hanzi, pinyin, English meaning, and
        the learner's HSK level, produce an appropriate drill with the correct
        answer and plausible distractors.
        """
        hanzi: str = dspy.InputField(desc="Simplified Chinese characters")
        pinyin: str = dspy.InputField(desc="Pinyin with tone marks")
        english: str = dspy.InputField(desc="English translation")
        hsk_level: int = dspy.InputField(desc="Learner's HSK level (1-9)")

        drill_type: str = dspy.OutputField(desc="One of: mcq, fill_blank, translate_to_chinese, translate_to_english")
        question: str = dspy.OutputField(desc="The drill question text")
        correct_answer: str = dspy.OutputField(desc="The correct answer")
        distractors: str = dspy.OutputField(desc="JSON array of 3 plausible wrong answers")

    class ErrorExplanation(dspy.Signature):
        """Explain why a Mandarin learner made a specific mistake.

        Given the target character/word, the correct answer, and what the
        student answered, produce an explanation with a memory aid.
        """
        hanzi: str = dspy.InputField(desc="The Chinese characters being studied")
        correct_answer: str = dspy.InputField(desc="What the correct answer should be")
        wrong_answer: str = dspy.InputField(desc="What the student answered incorrectly")

        explanation: str = dspy.OutputField(desc="Brief explanation of why this confusion occurs")
        correct_usage: str = dspy.OutputField(desc="Example of correct usage in a sentence")
        mnemonic: str = dspy.OutputField(desc="A memory aid to prevent recurrence")

    class LearningInsight(dspy.Signature):
        """Analyze error patterns and produce learning advice.

        Given a summary of recent errors and the lookback period, identify
        patterns and produce actionable study advice.
        """
        error_summary: str = dspy.InputField(desc="Bullet-point list of recent errors with hanzi, expected, and given answers")
        lookback_days: int = dspy.InputField(desc="Number of days the error summary covers")

        patterns: str = dspy.OutputField(desc="JSON array of 2-3 identified error patterns")
        advice: str = dspy.OutputField(desc="JSON array of actionable study recommendations")
        focus_areas: str = dspy.OutputField(desc="JSON array of specific topics or characters to review")

    class ReadingGeneration(dspy.Signature):
        """Generate a graded reading passage for Mandarin learners.

        Given target vocabulary, HSK level, and an optional topic, produce
        a reading passage with translation and comprehension questions.
        """
        target_vocabulary: str = dspy.InputField(desc="Comma-separated target vocabulary words in hanzi")
        hsk_level: int = dspy.InputField(desc="Target HSK level (1-9)")
        topic: str = dspy.InputField(desc="Optional topic or theme for the passage")

        passage_zh: str = dspy.OutputField(desc="The reading passage in simplified Chinese")
        passage_en: str = dspy.OutputField(desc="English translation of the passage")
        comprehension_questions: str = dspy.OutputField(desc="JSON array of {question, answer} dicts in Chinese")

    _HAS_DSPY = True

except ImportError:
    _HAS_DSPY = False

    # Stub classes so imports don't fail
    class DrillGeneration:  # type: ignore[no-redef]
        pass

    class ErrorExplanation:  # type: ignore[no-redef]
        pass

    class LearningInsight:  # type: ignore[no-redef]
        pass

    class ReadingGeneration:  # type: ignore[no-redef]
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# Module Instances (ChainOfThought wrappers)
# ═══════════════════════════════════════════════════════════════════════════════

drill_generator: object | None = None
error_explainer: object | None = None
insight_generator: object | None = None
reading_generator: object | None = None

if _HAS_DSPY:
    try:
        import dspy
        drill_generator = dspy.ChainOfThought(DrillGeneration)
        error_explainer = dspy.ChainOfThought(ErrorExplanation)
        insight_generator = dspy.ChainOfThought(LearningInsight)
        reading_generator = dspy.ChainOfThought(ReadingGeneration)
    except Exception as exc:
        logger.debug("Failed to create DSPy ChainOfThought modules: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# Optimizer: Learn from prompt_trace quality scores
# ═══════════════════════════════════════════════════════════════════════════════

# Map prompt_trace.prompt_key to the DSPy module name
_PROMPT_KEY_TO_MODULE = {
    "drill_generation": "drill_generator",
    "error_explanation": "error_explainer",
    "learning_insight": "insight_generator",
    "reading_generation": "reading_generator",
}

# Map module names to their signature classes for building examples
_MODULE_SIGNATURES = {
    "drill_generator": DrillGeneration,
    "error_explainer": ErrorExplanation,
    "insight_generator": LearningInsight,
    "reading_generator": ReadingGeneration,
}


def optimize_from_traces(conn: sqlite3.Connection, module_name: str) -> dict:
    """Optimize a DSPy module using high-quality prompt_trace examples.

    Queries the prompt_trace table for entries with output_quality_score > 0.8,
    fetches corresponding cached prompt/response pairs from pi_ai_generation_cache,
    builds dspy.Example instances, and runs BootstrapFewShot if enough examples.

    Args:
        conn: SQLite connection with prompt_trace and pi_ai_generation_cache tables.
        module_name: One of 'drill_generator', 'error_explainer',
                     'insight_generator', 'reading_generator'.

    Returns:
        Dict with status, examples_found, and optimized flag.
    """
    if not _HAS_DSPY:
        return {"status": "skipped", "reason": "dspy not installed"}

    if not configure_dspy():
        return {"status": "skipped", "reason": "dspy configuration failed"}

    import dspy

    # Resolve prompt_key from module_name
    prompt_key = None
    for pk, mn in _PROMPT_KEY_TO_MODULE.items():
        if mn == module_name:
            prompt_key = pk
            break

    if prompt_key is None:
        return {"status": "error", "reason": f"unknown module: {module_name}"}

    # Get the target module instance
    module_map = {
        "drill_generator": drill_generator,
        "error_explainer": error_explainer,
        "insight_generator": insight_generator,
        "reading_generator": reading_generator,
    }
    target_module = module_map.get(module_name)
    if target_module is None:
        return {"status": "error", "reason": f"module {module_name} not initialized"}

    # Query high-quality traces with their cached prompts/responses
    try:
        rows = conn.execute("""
            SELECT pt.prompt_hash, pt.output_quality_score,
                   c.prompt_text, c.response_text
            FROM prompt_trace pt
            JOIN pi_ai_generation_cache c ON c.prompt_hash = pt.prompt_hash
            WHERE pt.prompt_key = ?
              AND pt.output_quality_score > 0.8
              AND pt.success = 1
            ORDER BY pt.output_quality_score DESC
            LIMIT 50
        """, (prompt_key,)).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("optimize_from_traces query failed: %s", exc)
        return {"status": "skipped", "reason": "tables not available"}

    if len(rows) < 10:
        return {
            "status": "insufficient_data",
            "examples_found": len(rows),
            "min_required": 10,
        }

    # Build DSPy examples from cached data
    examples = []
    for row in rows:
        example = _build_example_from_cache(
            module_name, row["prompt_text"], row["response_text"],
        )
        if example is not None:
            examples.append(example)

    if len(examples) < 10:
        return {
            "status": "insufficient_data",
            "examples_found": len(examples),
            "min_required": 10,
            "parse_failures": len(rows) - len(examples),
        }

    # Split into train/val
    split_idx = max(1, int(len(examples) * 0.8))
    trainset = examples[:split_idx]
    valset = examples[split_idx:]

    # Define a simple metric: response should be parseable as JSON
    def quality_metric(example, pred, trace=None):
        """Check that predictions produce valid, non-empty outputs."""
        try:
            for field_name in _get_output_field_names(module_name):
                value = getattr(pred, field_name, "")
                if not value or not str(value).strip():
                    return False
                # If field is expected to be JSON, try parsing
                if field_name in ("distractors", "patterns", "advice",
                                  "focus_areas", "comprehension_questions"):
                    parsed = json.loads(str(value))
                    if not isinstance(parsed, list) or len(parsed) == 0:
                        return False
            return True
        except (json.JSONDecodeError, AttributeError):
            return False

    # Run BootstrapFewShot
    try:
        from dspy.teleprompt import BootstrapFewShot

        optimizer = BootstrapFewShot(
            metric=quality_metric,
            max_bootstrapped_demos=4,
            max_labeled_demos=4,
        )

        optimized_module = optimizer.compile(
            target_module,
            trainset=trainset,
            valset=valset,
        )

        # Replace the module instance in the global scope
        globals()[module_name] = optimized_module

        logger.info(
            "DSPy module '%s' optimized with %d examples (%d train, %d val)",
            module_name, len(examples), len(trainset), len(valset),
        )
        return {
            "status": "optimized",
            "examples_found": len(examples),
            "trainset_size": len(trainset),
            "valset_size": len(valset),
        }

    except Exception as exc:
        logger.warning("DSPy optimization failed for %s: %s", module_name, exc)
        return {"status": "error", "reason": str(exc)}


def _get_output_field_names(module_name: str) -> list[str]:
    """Get the output field names for a given module."""
    field_map = {
        "drill_generator": ["drill_type", "question", "correct_answer", "distractors"],
        "error_explainer": ["explanation", "correct_usage", "mnemonic"],
        "insight_generator": ["patterns", "advice", "focus_areas"],
        "reading_generator": ["passage_zh", "passage_en", "comprehension_questions"],
    }
    return field_map.get(module_name, [])


def _build_example_from_cache(
    module_name: str, prompt_text: str, response_text: str,
) -> object | None:
    """Parse a cached prompt/response pair into a dspy.Example.

    Extracts input fields from the prompt text and output fields from
    the response JSON. Returns None if parsing fails.
    """
    if not _HAS_DSPY:
        return None

    import dspy

    try:
        # Try to parse response as JSON
        response_clean = response_text.strip()
        if response_clean.startswith("```"):
            import re
            response_clean = re.sub(r"^```(?:json)?\s*\n?", "", response_clean)
            response_clean = re.sub(r"\n?```\s*$", "", response_clean)
        response_data = json.loads(response_clean)
    except (json.JSONDecodeError, ValueError):
        return None

    if module_name == "drill_generator":
        return _build_drill_example(prompt_text, response_data)
    elif module_name == "error_explainer":
        return _build_error_example(prompt_text, response_data)
    elif module_name == "insight_generator":
        return _build_insight_example(prompt_text, response_data)
    elif module_name == "reading_generator":
        return _build_reading_example(prompt_text, response_data)
    return None


def _build_drill_example(prompt_text: str, response: dict) -> object | None:
    """Build a DSPy Example for drill generation."""
    import dspy

    # Extract inputs from prompt text heuristically
    hanzi = response.get("hanzi", "")
    pinyin = response.get("pinyin", "")
    english = response.get("english", "")
    hsk_level = response.get("hsk_level", 1)

    drill_type = response.get("drill_type", "")
    distractors = response.get("distractors", [])

    if not hanzi or not drill_type:
        return None

    # Build example sentence as question if available
    question = response.get("example_sentence_hanzi", f"What does {hanzi} mean?")
    correct_answer = response.get("english", english)

    return dspy.Example(
        hanzi=hanzi,
        pinyin=pinyin,
        english=english,
        hsk_level=hsk_level,
        drill_type=drill_type,
        question=question,
        correct_answer=correct_answer,
        distractors=json.dumps(distractors),
    ).with_inputs("hanzi", "pinyin", "english", "hsk_level")


def _build_error_example(prompt_text: str, response: dict) -> object | None:
    """Build a DSPy Example for error explanation."""
    import dspy

    # Response from error_explanation may be plain text, not structured
    # But if it came from the cache with quality_score > 0.8, try to extract
    explanation = ""
    correct_usage = ""
    mnemonic = ""

    if isinstance(response, dict):
        explanation = response.get("explanation", response.get("text", ""))
        correct_usage = response.get("correct_usage", response.get("example", ""))
        mnemonic = response.get("mnemonic", response.get("memory_aid", ""))
    elif isinstance(response, str):
        explanation = response

    if not explanation:
        return None

    # Extract hanzi, correct, wrong from prompt text
    import re
    correct_match = re.search(r"correct answer is ['\"](.+?)['\"]", prompt_text)
    wrong_match = re.search(r"answered ['\"](.+?)['\"]", prompt_text)

    correct_answer = correct_match.group(1) if correct_match else ""
    wrong_answer = wrong_match.group(1) if wrong_match else ""

    # Try to find hanzi
    hanzi_match = re.search(r"([\u4e00-\u9fff]+)", prompt_text)
    hanzi = hanzi_match.group(1) if hanzi_match else ""

    if not hanzi:
        return None

    return dspy.Example(
        hanzi=hanzi,
        correct_answer=correct_answer,
        wrong_answer=wrong_answer,
        explanation=explanation,
        correct_usage=correct_usage or f"Example: {hanzi}",
        mnemonic=mnemonic or "Review the character components.",
    ).with_inputs("hanzi", "correct_answer", "wrong_answer")


def _build_insight_example(prompt_text: str, response: dict) -> object | None:
    """Build a DSPy Example for learning insight."""
    import dspy

    patterns = response.get("patterns", [])
    advice = response.get("advice", [])
    focus_areas = response.get("focus_areas", [])

    if not patterns:
        return None

    # Extract error_summary and lookback_days from prompt
    import re
    days_match = re.search(r"past (\d+) days", prompt_text)
    lookback_days = int(days_match.group(1)) if days_match else 7

    # The error summary is everything between the first newline and the last instruction
    error_lines = []
    for line in prompt_text.split("\n"):
        line = line.strip()
        if line.startswith("- ") and any(c >= "\u4e00" and c <= "\u9fff" for c in line):
            error_lines.append(line)

    error_summary = "\n".join(error_lines) if error_lines else prompt_text[:500]

    return dspy.Example(
        error_summary=error_summary,
        lookback_days=lookback_days,
        patterns=json.dumps(patterns),
        advice=json.dumps(advice),
        focus_areas=json.dumps(focus_areas),
    ).with_inputs("error_summary", "lookback_days")


def _build_reading_example(prompt_text: str, response: dict) -> object | None:
    """Build a DSPy Example for reading passage generation."""
    import dspy

    passage_zh = response.get("body", "")
    passage_en = response.get("english_body", "")
    questions = response.get("comprehension_questions", [])

    if not passage_zh:
        return None

    # Extract target vocab and HSK level from prompt
    import re
    hsk_match = re.search(r"HSK\s*(\d+)", prompt_text, re.IGNORECASE)
    hsk_level = int(hsk_match.group(1)) if hsk_match else 2

    vocab = response.get("vocabulary", [])
    target_vocabulary = ", ".join(
        v.get("hanzi", "") for v in vocab if isinstance(v, dict) and v.get("hanzi")
    ) if vocab else ""

    # Try to extract topic
    topic_match = re.search(r"topic[:\s]+[\"']?(.+?)[\"']?(?:\.|,|\n|$)", prompt_text, re.IGNORECASE)
    topic = topic_match.group(1).strip() if topic_match else ""

    return dspy.Example(
        target_vocabulary=target_vocabulary,
        hsk_level=hsk_level,
        topic=topic,
        passage_zh=passage_zh,
        passage_en=passage_en,
        comprehension_questions=json.dumps(questions),
    ).with_inputs("target_vocabulary", "hsk_level", "topic")
