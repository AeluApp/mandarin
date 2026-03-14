"""OpenClaw security — prompt injection defense, input sanitization, audit trail."""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..settings import (
    OPENCLAW_TELEGRAM_TOKEN,
)

logger = logging.getLogger(__name__)

# Owner chat ID — only this Telegram user can interact with the bot
OWNER_CHAT_ID = int(
    __import__("os").environ.get("OPENCLAW_TELEGRAM_OWNER_ID", "0")
)

# ── Input limits ──────────────────────────────────────────
MAX_MESSAGE_LENGTH = 2000
MAX_COMMAND_ARG_LENGTH = 200

# ── Injection patterns ───────────────────────────────────
# These patterns detect common prompt injection attempts.
# They're intentionally conservative — false positives are cheap,
# false negatives are expensive.
_INJECTION_PATTERNS = [
    # Direct instruction override attempts
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.I),
    re.compile(r"forget\s+(everything|all|your)\s+(instructions?|rules?|training)", re.I),
    # System prompt extraction
    re.compile(r"(print|show|reveal|output|display|repeat)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)", re.I),
    re.compile(r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?|rules?)", re.I),
    # Role hijacking
    re.compile(r"you\s+are\s+now\s+", re.I),
    re.compile(r"pretend\s+(to\s+be|you\s+are)", re.I),
    re.compile(r"act\s+as\s+(if\s+you|a\s+)", re.I),
    re.compile(r"new\s+(persona|role|identity|character)", re.I),
    # Delimiter injection
    re.compile(r"```system", re.I),
    re.compile(r"\[INST\]|\[/INST\]", re.I),
    re.compile(r"<\|?(system|assistant|user)\|?>", re.I),
    # SQL/code injection via chat
    re.compile(r"(DROP|DELETE|UPDATE|INSERT|ALTER)\s+TABLE", re.I),
    re.compile(r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER)\s+", re.I),
]


def sanitize_input(text: str) -> str:
    """Clean user input: strip control chars, limit length, normalize whitespace."""
    if not text:
        return ""
    # Remove null bytes and other control characters (keep newlines, tabs)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Truncate
    return cleaned[:MAX_MESSAGE_LENGTH]


def check_prompt_injection(text: str) -> tuple[bool, Optional[str]]:
    """Check for prompt injection patterns.

    Returns (is_safe, matched_pattern_description).
    """
    if not text:
        return True, None

    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return False, f"injection_pattern: {match.group()[:50]}"

    return True, None


def validate_owner(chat_id: int) -> bool:
    """Check if the Telegram chat ID belongs to the owner."""
    if OWNER_CHAT_ID == 0:
        logger.warning("OPENCLAW_TELEGRAM_OWNER_ID not set — rejecting all messages")
        return False
    return chat_id == OWNER_CHAT_ID


def log_message(
    conn,
    *,
    direction: str,  # "inbound" or "outbound"
    channel: str,    # "telegram", "n8n", "voice", "api"
    message_text: str,
    user_identifier: str = "",
    intent: str = "",
    tool_called: str = "",
    tool_result: str = "",
    injection_detected: bool = False,
    injection_detail: str = "",
) -> str:
    """Write an entry to the openclaw_message_log audit trail.

    Returns the message_id (UUID).
    """
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            """INSERT INTO openclaw_message_log
               (id, created_at, direction, channel, user_identifier,
                message_text, intent, tool_called, tool_result,
                injection_detected, injection_detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, now, direction, channel, user_identifier,
             message_text[:4000], intent, tool_called,
             tool_result[:4000] if tool_result else "",
             1 if injection_detected else 0, injection_detail[:500]),
        )
        conn.commit()
    except Exception:
        logger.debug("Failed to log openclaw message", exc_info=True)
    return msg_id


def sanitize_output(text: str) -> str:
    """Sanitize LLM output before sending to user.

    Strips any leaked system prompt fragments or suspicious patterns.
    """
    if not text:
        return ""
    # Remove any accidentally leaked system prompt markers
    cleaned = re.sub(r"<\|?(system|assistant)\|?>.*?<\|?/(system|assistant)\|?>", "", text, flags=re.S)
    # Remove markdown code blocks that might contain system prompts
    cleaned = re.sub(r"```system\b.*?```", "[redacted]", cleaned, flags=re.S | re.I)
    # Truncate to reasonable response length
    return cleaned[:MAX_MESSAGE_LENGTH]
