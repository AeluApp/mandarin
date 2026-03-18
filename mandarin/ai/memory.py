"""Conversation memory for OpenClaw bots using mem0.

Provides per-user conversational memory that persists across sessions.
Uses LiteLLM as LLM backend and LanceDB as vector store — both local, no API keys.
Gracefully degrades to no-op when mem0 is not installed.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_memory_instance: Optional[object] = None
_mem0_available: Optional[bool] = None


def _get_memory():
    """Singleton that creates mem0.Memory with LiteLLM + LanceDB config.

    Returns the Memory instance, or None if mem0 is not installed.
    """
    global _memory_instance, _mem0_available

    if _mem0_available is False:
        return None

    if _memory_instance is not None:
        return _memory_instance

    try:
        from mem0 import Memory
        from ..settings import OLLAMA_URL, OLLAMA_PRIMARY_MODEL, DATA_DIR

        lancedb_path = str(DATA_DIR / "mem0_lancedb")

        config = {
            "llm": {
                "provider": "litellm",
                "config": {
                    "model": f"ollama/{OLLAMA_PRIMARY_MODEL}",
                    "api_base": OLLAMA_URL,
                    "temperature": 0.1,
                    "max_tokens": 1024,
                },
            },
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": OLLAMA_PRIMARY_MODEL,
                    "ollama_base_url": OLLAMA_URL,
                },
            },
            "vector_store": {
                "provider": "lancedb",
                "config": {
                    "url": lancedb_path,
                    "collection_name": "openclaw_memory",
                },
            },
            "version": "v1.1",
        }

        _memory_instance = Memory.from_config(config)
        _mem0_available = True
        logger.info("mem0 conversation memory initialized (LanceDB at %s)", lancedb_path)
        return _memory_instance

    except ImportError:
        _mem0_available = False
        logger.debug("mem0 not installed — conversation memory disabled")
        return None
    except Exception as exc:
        _mem0_available = False
        logger.warning("mem0 initialization failed: %s", exc)
        return None


def add_memory(user_id: str, message: str, response: str, channel: str = "") -> None:
    """Store a conversation turn in mem0.

    Args:
        user_id: Truncated user identifier (max 20 chars for privacy).
        message: The user's message text.
        response: The bot's response text.
        channel: Source channel (imessage, telegram, discord, whatsapp, voice).

    Never raises — all exceptions are caught and logged.
    """
    try:
        mem = _get_memory()
        if mem is None:
            return

        messages = [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response},
        ]

        metadata = {}
        if channel:
            metadata["channel"] = channel

        mem.add(messages, user_id=user_id, metadata=metadata)
        logger.debug("Stored memory for user=%s channel=%s", user_id[:6], channel)

    except Exception as exc:
        logger.debug("add_memory failed (non-fatal): %s", exc)


def search_memory(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """Retrieve relevant memories for a user given a query.

    Args:
        user_id: The user identifier to scope the search.
        query: The search query (typically the user's current message).
        limit: Maximum number of memories to return.

    Returns:
        List of memory dicts with at least a "memory" or "text" key.
        Returns empty list on any error.
    """
    try:
        mem = _get_memory()
        if mem is None:
            return []

        results = mem.search(query, user_id=user_id, limit=limit)

        # mem0 v1.1 returns {"results": [...]} or a list directly
        if isinstance(results, dict):
            return results.get("results", results.get("memories", []))
        if isinstance(results, list):
            return results
        return []

    except Exception as exc:
        logger.debug("search_memory failed (non-fatal): %s", exc)
        return []
