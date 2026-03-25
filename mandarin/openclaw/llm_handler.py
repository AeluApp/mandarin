"""OpenClaw LLM handler — intent classification and conversational orchestration.

Uses Ollama for natural language understanding. Classifies user messages into
intents and orchestrates tool calls. Falls back to keyword matching when
Ollama is unavailable.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from ..ai.ollama_client import generate, is_ollama_available

logger = logging.getLogger(__name__)

# ── Intent definitions ────────────────────────────────────

INTENTS = {
    "status": "Check learning status, due items, streak, weekly progress",
    "review": "Check or manage the content review queue",
    "approve": "Approve a specific review item (needs item_id)",
    "reject": "Reject a specific review item (needs item_id and optional reason)",
    "audit": "Check latest product audit results",
    "briefing": "Get learner briefing or tutor prep",
    "errors": "Analyze error patterns and interference pairs",
    "session": "Start or plan a study session",
    "help": "Show available commands",
    "chat": "General conversation (no tool needed)",
}

SYSTEM_PROMPT = """You are the Aelu assistant, a calm and helpful Mandarin learning companion.
You help the owner manage their learning system via Telegram.

When the user sends a message, classify their intent into exactly one of these categories:
{intents}

Respond with ONLY a JSON object:
{{"intent": "<intent_name>", "args": {{"key": "value"}}, "reply": "<brief natural language response>"}}

Rules:
- If the user asks about their progress, due items, or streak → "status"
- If they mention review, pending items, queue → "review"
- If they say "approve" + a number → "approve" with args {{"item_id": <number>}}
- If they say "reject" + a number → "reject" with args {{"item_id": <number>, "reason": "<reason if given>"}}
- If they mention audit, grade, findings → "audit"
- If they mention briefing, tutor, prep, italki → "briefing"
- If they mention errors, mistakes, confusion, interference → "errors"
- If they want to study, practice, drill → "session"
- If they ask what you can do → "help"
- For greetings, thanks, or off-topic → "chat" with a brief friendly reply
- Keep replies concise. No emoji overload. Match the calm Aelu tone.
"""


@dataclass
class IntentResult:
    intent: str
    args: dict
    reply: str = ""
    confidence: float = 1.0
    from_llm: bool = False


def classify_intent(text: str, conn=None, user_id: str = "") -> IntentResult:
    """Classify user message into an intent.

    Tries Ollama first, falls back to keyword matching.
    """
    # Try LLM classification if available
    if is_ollama_available():
        result = _classify_with_llm(text, conn, user_id=user_id)
        if result is not None:
            return result

    # Keyword fallback
    return _classify_with_keywords(text)


def _classify_with_llm(text: str, conn=None, user_id: str = "") -> IntentResult | None:
    """Use Ollama to classify intent."""
    intents_str = "\n".join(f"- {k}: {v}" for k, v in INTENTS.items())
    system = SYSTEM_PROMPT.format(intents=intents_str)

    # Prepend conversation memory context if available
    try:
        from ..ai.memory import search_memory
        if user_id and text:
            memories = search_memory(user_id, text, limit=3)
            if memories:
                memory_context = "\n".join(
                    m.get("memory", m.get("text", "")) for m in memories
                )
                system = f"Previous context about this user:\n{memory_context}\n\n{system}"
    except (ImportError, Exception):
        pass

    response = generate(
        prompt=text,
        system=system,
        temperature=0.1,
        max_tokens=256,
        use_cache=False,
        conn=conn,
        task_type="openclaw_intent",
    )

    if not response.success:
        logger.debug("LLM intent classification failed: %s", response.error)
        return None

    try:
        # Parse JSON from response
        raw = response.text.strip()
        # Handle cases where LLM wraps in markdown code blocks
        if raw.startswith("```"):
            raw = re.sub(r"```(?:json)?\s*", "", raw)
            raw = raw.rstrip("`").strip()

        data = json.loads(raw)
        intent = data.get("intent", "chat")
        if intent not in INTENTS:
            intent = "chat"

        return IntentResult(
            intent=intent,
            args=data.get("args", {}),
            reply=data.get("reply", ""),
            confidence=0.9,
            from_llm=True,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.debug("Failed to parse LLM intent response: %s", response.text[:200])
        return None


def _classify_with_keywords(text: str) -> IntentResult:
    """Simple keyword-based intent classification fallback."""
    lower = text.lower().strip()

    # Command-style messages
    if lower.startswith("/"):
        cmd = lower.split()[0][1:]
        arg_text = lower[len(cmd) + 1:].strip()
        if cmd in INTENTS:
            args = _extract_args(cmd, arg_text)
            return IntentResult(intent=cmd, args=args, confidence=1.0)

    # Approve/reject with number
    approve_match = re.match(r"(?:approve|ok|yes|y)\s+(\d+)", lower)
    if approve_match:
        return IntentResult(
            intent="approve",
            args={"item_id": int(approve_match.group(1))},
            confidence=0.95,
        )

    reject_match = re.match(r"(?:reject|no|n)\s+(\d+)\s*(.*)", lower)
    if reject_match:
        return IntentResult(
            intent="reject",
            args={"item_id": int(reject_match.group(1)),
                  "reason": reject_match.group(2).strip()},
            confidence=0.95,
        )

    # Keyword matching
    keyword_map = {
        "status": ["status", "due", "streak", "progress", "how am i", "how's it going"],
        "review": ["review", "queue", "pending", "items to review"],
        "audit": ["audit", "grade", "findings", "quality"],
        "briefing": ["briefing", "brief", "tutor", "prep", "italki"],
        "errors": ["error", "mistake", "confus", "interfere", "pattern"],
        "session": ["study", "practice", "drill", "session", "let's go", "ready"],
        "help": ["help", "what can you do", "commands", "?"],
    }

    for intent, keywords in keyword_map.items():
        if any(kw in lower for kw in keywords):
            return IntentResult(intent=intent, args={}, confidence=0.7)

    return IntentResult(intent="chat", args={}, reply="", confidence=0.5)


def _extract_args(cmd: str, arg_text: str) -> dict:
    """Extract arguments from command text."""
    args = {}
    if cmd in ("approve", "reject") and arg_text:
        parts = arg_text.split(maxsplit=1)
        try:
            args["item_id"] = int(parts[0])
        except ValueError:
            pass
        if cmd == "reject" and len(parts) > 1:
            args["reason"] = parts[1]
    return args


def generate_chat_response(text: str, conn=None, user_id: str = "") -> str:
    """Generate a conversational response for non-tool messages."""
    if not is_ollama_available():
        return "I can help with: /status, /review, /audit, /briefing, /errors. What would you like?"

    system = (
        "You are the Aelu assistant — calm, helpful, concise. "
        "You help manage a Mandarin learning system. "
        "If the user seems to want a specific action, suggest the relevant command. "
        "Available: /status, /review, /audit, /briefing, /errors, /session. "
        "Keep responses under 3 sentences."
    )

    # Prepend conversation memory context if available
    try:
        from ..ai.memory import search_memory
        if user_id and text:
            memories = search_memory(user_id, text, limit=3)
            if memories:
                memory_context = "\n".join(
                    m.get("memory", m.get("text", "")) for m in memories
                )
                system = f"Previous context about this user:\n{memory_context}\n\n{system}"
    except (ImportError, Exception):
        pass

    response = generate(
        prompt=text,
        system=system,
        temperature=0.7,
        max_tokens=256,
        use_cache=False,
        conn=conn,
        task_type="openclaw_chat",
    )

    if response.success:
        return response.text.strip()
    return "I can help with: /status, /review, /audit, /briefing, /errors. What would you like?"
