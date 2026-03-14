"""Guided conversation drill — structured speaking practice with prompts.

Provides contextual speaking practice beyond single-word tone grading:
1. Situational prompts (ordering food, asking directions, etc.)
2. Role-play with guided responses
3. Free-form conversation with grammar-aware feedback
4. Progressive difficulty from scripted to open-ended

All have deterministic fallbacks when Ollama is unavailable.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Optional

from .ollama_client import generate, is_ollama_available

logger = logging.getLogger(__name__)

# ── Conversation scenarios by HSK level ──────────────

SCENARIOS = {
    1: [
        {
            "id": "greet_1",
            "title": "Meeting someone new",
            "title_zh": "认识新朋友",
            "situation": "You're at a coffee shop and the person next to you says hello.",
            "prompt_zh": "你好！你叫什么名字？",
            "prompt_pinyin": "Nǐ hǎo! Nǐ jiào shénme míngzì?",
            "prompt_en": "Hello! What's your name?",
            "expected_patterns": ["我叫", "你好"],
            "grammar_points": ["self_introduction"],
            "sample_response": "你好！我叫…。你呢？",
        },
        {
            "id": "order_1",
            "title": "Ordering a drink",
            "title_zh": "点饮料",
            "situation": "You're at a café. The server asks what you'd like.",
            "prompt_zh": "你好，请问你要喝什么？",
            "prompt_pinyin": "Nǐ hǎo, qǐngwèn nǐ yào hē shénme?",
            "prompt_en": "Hello, what would you like to drink?",
            "expected_patterns": ["我要", "请给我", "一杯"],
            "grammar_points": ["want_verb", "measure_words"],
            "sample_response": "我要一杯咖啡，谢谢。",
        },
        {
            "id": "how_much_1",
            "title": "Asking the price",
            "title_zh": "问价钱",
            "situation": "You want to buy something at a market.",
            "prompt_zh": "这个苹果很好吃！",
            "prompt_pinyin": "Zhège píngguǒ hěn hǎo chī!",
            "prompt_en": "These apples are delicious!",
            "expected_patterns": ["多少钱", "几块"],
            "grammar_points": ["questions_how_much"],
            "sample_response": "多少钱一斤？",
        },
    ],
    2: [
        {
            "id": "directions_2",
            "title": "Asking for directions",
            "title_zh": "问路",
            "situation": "You're looking for the subway station.",
            "prompt_zh": "你好，你找什么地方？",
            "prompt_pinyin": "Nǐ hǎo, nǐ zhǎo shénme dìfāng?",
            "prompt_en": "Hello, what place are you looking for?",
            "expected_patterns": ["怎么走", "在哪里", "地铁站"],
            "grammar_points": ["location_words", "directional_verbs"],
            "sample_response": "请问，地铁站怎么走？",
        },
        {
            "id": "past_event_2",
            "title": "Talking about yesterday",
            "title_zh": "说说昨天",
            "situation": "A friend asks what you did yesterday.",
            "prompt_zh": "你昨天做了什么？",
            "prompt_pinyin": "Nǐ zuótiān zuò le shénme?",
            "prompt_en": "What did you do yesterday?",
            "expected_patterns": ["了", "昨天"],
            "grammar_points": ["completed_action_le", "time_words"],
            "sample_response": "我昨天去了图书馆看书。",
        },
        {
            "id": "comparison_2",
            "title": "Comparing things",
            "title_zh": "比较",
            "situation": "You're shopping with a friend and comparing two items.",
            "prompt_zh": "你觉得哪个好？",
            "prompt_pinyin": "Nǐ juédé nǎge hǎo?",
            "prompt_en": "Which one do you think is better?",
            "expected_patterns": ["比", "更", "觉得"],
            "grammar_points": ["comparison_bi", "opinion_juede"],
            "sample_response": "我觉得这个比那个好看。",
        },
    ],
    3: [
        {
            "id": "explain_3",
            "title": "Explaining a problem",
            "title_zh": "说明问题",
            "situation": "Your internet isn't working. Call customer service.",
            "prompt_zh": "您好，有什么可以帮您的？",
            "prompt_pinyin": "Nín hǎo, yǒu shénme kěyǐ bāng nín de?",
            "prompt_en": "Hello, how can I help you?",
            "expected_patterns": ["因为", "所以", "不能", "已经"],
            "grammar_points": ["cause_effect", "resultative_complement"],
            "sample_response": "你好，我的网络坏了，已经两天不能上网了。",
        },
        {
            "id": "opinion_3",
            "title": "Expressing an opinion",
            "title_zh": "表达看法",
            "situation": "A classmate asks your opinion about learning Chinese.",
            "prompt_zh": "你觉得学中文难不难？",
            "prompt_pinyin": "Nǐ juédé xué Zhōngwén nán bù nán?",
            "prompt_en": "Do you think learning Chinese is hard?",
            "expected_patterns": ["虽然", "但是", "一方面", "觉得"],
            "grammar_points": ["concession", "opinion_structures"],
            "sample_response": "虽然中文的声调很难，但是我觉得语法不太复杂。",
        },
    ],
}

CONVERSATION_SYSTEM = """You are a Mandarin conversation partner in a roleplay scenario.

Scenario: {situation}
The learner's HSK level: {hsk_level}

You said: {prompt_zh}
The learner responded: {user_response}

Evaluate their response:
1. Was it contextually appropriate? (yes/no)
2. Was the grammar correct? List any errors briefly.
3. Did they use expected patterns? (Expected: {expected_patterns})
4. Give a natural follow-up line to continue the conversation.
5. Rate overall: excellent / good / needs_work

Output ONLY valid JSON:
{{
  "appropriate": true/false,
  "grammar_correct": true/false,
  "grammar_notes": "brief note on errors, or empty",
  "patterns_used": ["which expected patterns appeared"],
  "follow_up_zh": "your next line in Chinese",
  "follow_up_pinyin": "pinyin for follow-up",
  "follow_up_en": "English translation",
  "rating": "excellent/good/needs_work",
  "encouragement": "one encouraging sentence"
}}"""


def get_scenario(
    conn, hsk_level: int = 2, exclude_ids: list[str] = None,
) -> Optional[dict]:
    """Pick a conversation scenario appropriate for the learner's level."""
    exclude_ids = exclude_ids or []

    # Gather scenarios at or below the learner's level
    candidates = []
    for level in range(max(1, hsk_level - 1), hsk_level + 1):
        for s in SCENARIOS.get(level, []):
            if s["id"] not in exclude_ids:
                candidates.append(s)

    if not candidates:
        # Fallback: any scenario
        for level_scenarios in SCENARIOS.values():
            candidates.extend(level_scenarios)

    if not candidates:
        return None

    return random.choice(candidates)


def evaluate_response(
    conn,
    scenario: dict,
    user_response: str,
    hsk_level: int = 2,
) -> dict:
    """Evaluate a learner's spoken/typed response to a conversation prompt.

    Returns evaluation with grammar notes, pattern usage, follow-up, and rating.
    """
    if not user_response.strip():
        return {
            "appropriate": False,
            "grammar_correct": False,
            "grammar_notes": "",
            "patterns_used": [],
            "follow_up_zh": scenario.get("sample_response", ""),
            "follow_up_pinyin": "",
            "follow_up_en": "",
            "rating": "needs_work",
            "encouragement": "Try responding — even a simple answer is a good start!",
            "source": "db",
        }

    # Check pattern usage deterministically
    patterns_used = []
    response_lower = user_response.lower()
    for pattern in scenario.get("expected_patterns", []):
        if pattern in user_response or pattern in response_lower:
            patterns_used.append(pattern)

    # Try LLM evaluation
    if is_ollama_available():
        system = CONVERSATION_SYSTEM.format(
            situation=scenario.get("situation", ""),
            hsk_level=hsk_level,
            prompt_zh=scenario.get("prompt_zh", ""),
            user_response=user_response[:200],
            expected_patterns=", ".join(scenario.get("expected_patterns", [])),
        )
        response = generate(
            prompt="Evaluate this conversation response.",
            system=system,
            temperature=0.3,
            max_tokens=512,
            use_cache=True,
            conn=conn,
            task_type="conversation_eval",
        )
        if response.success:
            parsed = _parse_evaluation(response.text)
            if parsed:
                parsed["source"] = "llm"
                return parsed

    # Deterministic fallback
    has_patterns = len(patterns_used) > 0
    is_long_enough = len(user_response) >= 4

    return {
        "appropriate": has_patterns or is_long_enough,
        "grammar_correct": True,  # Can't verify without LLM
        "grammar_notes": "",
        "patterns_used": patterns_used,
        "follow_up_zh": scenario.get("sample_response", ""),
        "follow_up_pinyin": "",
        "follow_up_en": "",
        "rating": "good" if has_patterns else "needs_work",
        "encouragement": (
            "Good use of the expected patterns!"
            if has_patterns
            else f"Try using: {', '.join(scenario.get('expected_patterns', []))}"
        ),
        "source": "db",
    }


def generate_follow_up(
    conn,
    scenario: dict,
    conversation_history: list[dict],
    hsk_level: int = 2,
) -> dict:
    """Generate a natural follow-up in an ongoing conversation.

    conversation_history is a list of {"role": "user"|"tutor", "text": str}.
    Returns {"text_zh", "text_pinyin", "text_en", "source"}.
    """
    if not is_ollama_available() or not conversation_history:
        return {
            "text_zh": scenario.get("sample_response", "好的。"),
            "text_pinyin": "",
            "text_en": "",
            "source": "db",
        }

    history_text = "\n".join(
        f"{'Tutor' if h['role'] == 'tutor' else 'Learner'}: {h['text']}"
        for h in conversation_history[-6:]  # Last 3 exchanges
    )

    system = f"""You are a Mandarin conversation partner.
Scenario: {scenario.get('situation', '')}
HSK level: {hsk_level}

Conversation so far:
{history_text}

Continue naturally. Keep your response at HSK {hsk_level} level.
Output JSON: {{"text_zh": "...", "text_pinyin": "...", "text_en": "..."}}"""

    response = generate(
        prompt="Continue the conversation naturally.",
        system=system,
        temperature=0.7,
        max_tokens=256,
        conn=conn,
        task_type="conversation_followup",
    )

    if response.success:
        parsed = _parse_json_safe(response.text)
        if parsed and parsed.get("text_zh"):
            parsed["source"] = "llm"
            return parsed

    return {
        "text_zh": scenario.get("sample_response", "好的。"),
        "text_pinyin": "",
        "text_en": "",
        "source": "db",
    }


def list_scenarios(hsk_level: int = None) -> list[dict]:
    """List all available conversation scenarios, optionally filtered by level."""
    result = []
    for level, scenarios in sorted(SCENARIOS.items()):
        if hsk_level is not None and level != hsk_level:
            continue
        for s in scenarios:
            result.append({
                "id": s["id"],
                "hsk_level": level,
                "title": s["title"],
                "title_zh": s["title_zh"],
                "situation": s["situation"],
                "grammar_points": s.get("grammar_points", []),
            })
    return result


# ── Helpers ─────────────────────────────────────────

def _parse_evaluation(text: str) -> Optional[dict]:
    """Parse JSON evaluation from LLM response."""
    import re
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        data = json.loads(text)
        # Validate required fields
        if "rating" in data and "appropriate" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _parse_json_safe(text: str) -> Optional[dict]:
    """Parse JSON from LLM response, tolerating markdown fences."""
    import re
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
