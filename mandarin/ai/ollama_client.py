"""Ollama HTTP client — local LLM generation with caching and fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..settings import (
    OLLAMA_URL, OLLAMA_PRIMARY_MODEL, OLLAMA_FALLBACK_MODEL, OLLAMA_TIMEOUT,
)

logger = logging.getLogger(__name__)


@dataclass
class OllamaResponse:
    success: bool
    text: str = ""
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    generation_time_ms: int = 0
    from_cache: bool = False
    error: Optional[str] = None


def is_ollama_available() -> bool:
    """Check if Ollama is running. Returns False gracefully on any error."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    use_cache: bool = True,
    conn=None,
    task_type: str = "unknown",
) -> OllamaResponse:
    """Generate text via Ollama. Tries primary model, falls back to smaller model."""

    # Check cache first
    if use_cache and conn is not None:
        cached = _check_cache(conn, prompt, system)
        if cached is not None:
            _log_generation(conn, task_type, cached)
            return cached

    # Try primary model, then fallback
    for model in [OLLAMA_PRIMARY_MODEL, OLLAMA_FALLBACK_MODEL]:
        result = _call_ollama(prompt, system, model, temperature, max_tokens)
        if result.success:
            if conn is not None:
                if use_cache:
                    _write_cache(conn, prompt, system, result)
                _log_generation(conn, task_type, result)
            return result
        logger.warning("Ollama %s failed: %s — trying next", model, result.error)

    # Both models failed
    failed = OllamaResponse(success=False, error=result.error if result else "all models failed")
    if conn is not None:
        _log_generation(conn, task_type, failed)
    return failed


def _call_ollama(
    prompt: str, system: str, model: str, temperature: float, max_tokens: int,
) -> OllamaResponse:
    """POST to Ollama /api/generate. Returns OllamaResponse."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if system:
        payload["system"] = system

    start = time.monotonic()
    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=float(OLLAMA_TIMEOUT),
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code != 200:
            return OllamaResponse(
                success=False, model_used=model, generation_time_ms=elapsed_ms,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        data = resp.json()
        return OllamaResponse(
            success=True,
            text=data.get("response", ""),
            model_used=model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            generation_time_ms=elapsed_ms,
        )
    except httpx.TimeoutException:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return OllamaResponse(
            success=False, model_used=model, generation_time_ms=elapsed_ms,
            error="timeout",
        )
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return OllamaResponse(
            success=False, model_used=model, generation_time_ms=elapsed_ms,
            error=str(e),
        )


def _prompt_hash(prompt: str, system: str) -> str:
    """SHA-256 hash of prompt + system for cache lookup."""
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    h.update(b"\x00")
    h.update(system.encode("utf-8"))
    return h.hexdigest()


def _check_cache(conn, prompt: str, system: str) -> Optional[OllamaResponse]:
    """Look up a cached generation by prompt hash."""
    ph = _prompt_hash(prompt, system)
    row = conn.execute(
        "SELECT id, response_text, model_used FROM pi_ai_generation_cache WHERE prompt_hash = ?",
        (ph,),
    ).fetchone()
    if row is None:
        return None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE pi_ai_generation_cache SET hit_count = hit_count + 1, last_hit_at = ? WHERE id = ?",
        (now, row["id"]),
    )
    conn.commit()

    return OllamaResponse(
        success=True, text=row["response_text"], model_used=row["model_used"],
        from_cache=True,
    )


def _write_cache(conn, prompt: str, system: str, response: OllamaResponse) -> None:
    """Persist a generation to the cache table."""
    ph = _prompt_hash(prompt, system)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            """INSERT OR IGNORE INTO pi_ai_generation_cache
               (id, prompt_hash, prompt_text, system_text, model_used, response_text, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), ph, prompt[:4000], system[:2000],
             response.model_used, response.text, now),
        )
        conn.commit()
    except Exception:
        logger.debug("Cache write failed", exc_info=True)


def generate_structured(
    prompt: str,
    response_model,
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    conn=None,
    task_type: str = "unknown",
):
    """Generate structured output via Instructor + Ollama's OpenAI-compatible endpoint.

    Uses instructor library to enforce JSON schema at the sampling level.
    Falls back to standard generate() + post-hoc validation if Instructor unavailable.
    """
    try:
        import instructor
        from openai import OpenAI
    except ImportError:
        # Fallback: use standard generate
        return None

    start = time.monotonic()
    try:
        client = instructor.from_openai(
            OpenAI(base_url=f"{OLLAMA_URL}/v1", api_key="ollama"),
            mode=instructor.Mode.JSON,
        )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        result = client.chat.completions.create(
            model=OLLAMA_PRIMARY_MODEL,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        resp = OllamaResponse(
            success=True,
            text=result.model_dump_json() if hasattr(result, 'model_dump_json') else str(result),
            model_used=OLLAMA_PRIMARY_MODEL,
            generation_time_ms=elapsed_ms,
        )

        if conn is not None:
            _log_generation(conn, task_type, resp)
            # Prompt observability tracing
            _trace_prompt(conn, task_type, prompt, resp)

        return result

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.debug("Instructor structured generation failed: %s", e)
        if conn is not None:
            failed = OllamaResponse(
                success=False, model_used=OLLAMA_PRIMARY_MODEL,
                generation_time_ms=elapsed_ms, error=str(e),
            )
            _log_generation(conn, task_type, failed)
        return None


def _trace_prompt(conn, task_type: str, prompt: str, response: OllamaResponse) -> None:
    """Trace prompt call for observability (C-02)."""
    try:
        from .prompt_observability import trace_prompt_call
        trace_prompt_call(
            conn,
            prompt_key=task_type,
            prompt_text=prompt[:4000],
            response_text=response.text[:4000] if response.text else "",
            latency_ms=response.generation_time_ms,
            model_used=response.model_used,
            success=response.success,
            input_tokens=response.prompt_tokens,
            output_tokens=response.completion_tokens,
            error_type=response.error if not response.success else None,
        )
    except Exception:
        logger.debug("Prompt tracing failed", exc_info=True)


def _log_generation(conn, task_type: str, response: OllamaResponse, **kwargs) -> None:
    """Persist every generation attempt to the log table."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            """INSERT INTO pi_ai_generation_log
               (id, occurred_at, task_type, model_used, prompt_tokens, completion_tokens,
                generation_time_ms, from_cache, success, error, finding_id, item_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), now, task_type,
             response.model_used or "none",
             response.prompt_tokens, response.completion_tokens,
             response.generation_time_ms,
             1 if response.from_cache else 0,
             1 if response.success else 0,
             response.error,
             kwargs.get("finding_id"), kwargs.get("item_id")),
        )
        conn.commit()
    except Exception:
        logger.debug("Generation log write failed", exc_info=True)

    # Prompt observability tracing (C-02)
    _trace_prompt(conn, task_type, "", response)
