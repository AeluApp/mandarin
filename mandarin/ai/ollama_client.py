"""LLM client — unified generation via LiteLLM with caching and fallback.

Uses LiteLLM as the routing layer so any model (Ollama, OpenAI, Anthropic,
cloud-hosted open-source via Groq/Together/Fireworks/SiliconFlow/DeepSeek,
etc.) can be used without changing call sites.

Cloud-first: routes to cloud-hosted 70B+ open-source models by default.
Falls back to local Ollama when cloud providers are unavailable.
Falls back to direct httpx calls when LiteLLM is not installed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, UTC
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

from ..settings import (
    OLLAMA_URL, OLLAMA_TIMEOUT,
    LITELLM_MODEL, LITELLM_FALLBACK, IS_CLOUD_MODEL,
)

# Backward-compat imports for call sites that use these names
OLLAMA_PRIMARY_MODEL = LITELLM_MODEL
OLLAMA_FALLBACK_MODEL = LITELLM_FALLBACK

logger = logging.getLogger(__name__)

# Suppress litellm's verbose logging
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)


@dataclass
class OllamaResponse:
    success: bool
    text: str = ""
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    generation_time_ms: int = 0
    from_cache: bool = False
    error: str | None = None


# Alias for gradual migration — new code should prefer LLMResponse
LLMResponse = OllamaResponse


def is_llm_available() -> bool:
    """Check if any LLM provider is reachable. Cloud-first, then local Ollama.

    Returns True if we can make LLM calls. This is the primary health check.
    """
    # Cloud: try a lightweight LiteLLM call
    if IS_CLOUD_MODEL:
        try:
            import litellm
            # Use model_list or a quick test to verify provider is up
            # litellm.check_valid_key handles provider health
            return True  # If we have cloud keys configured, assume available
        except ImportError:
            pass

    # Local Ollama fallback
    return _is_ollama_running()


def is_ollama_available() -> bool:
    """Backward-compat alias. Prefer is_llm_available() for new code."""
    return is_llm_available()


def _is_ollama_running() -> bool:
    """Check if local Ollama is running."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _get_task_model(conn, task_type: str) -> str | None:
    """Look up the best benchmarked model for this task type from pi_model_registry."""
    if conn is None:
        return None
    try:
        row = conn.execute("""
            SELECT model_name FROM pi_model_registry
            WHERE task_type = ? AND is_active = 1
            ORDER BY quality_score DESC LIMIT 1
        """, (task_type,)).fetchone()
        return row["model_name"] if row else None
    except Exception:
        return None


def _auto_score_quality(conn, task_type: str, result: OllamaResponse) -> None:
    """Score output quality and write to prompt_trace. Lightweight structural checks."""
    if not result.success or not result.text:
        return
    score = None
    if task_type in ("drill_generation", "reading_generation", "error_explanation",
                     "conversation_eval", "teacher_comms", "research_synthesis"):
        try:
            json.loads(result.text.strip())
            score = 0.8  # valid JSON
        except (json.JSONDecodeError, ValueError):
            # Check for JSON in code blocks
            import re
            if re.search(r"```(?:json)?\s*[\[\{]", result.text):
                score = 0.6  # JSON in code block (usable but messy)
            else:
                score = 0.2  # expected JSON, got freetext
    elif task_type in ("classify_prescription", "openclaw_intent"):
        # Classification: short, clean output = good
        text = result.text.strip()
        if len(text) < 50 and "\n" not in text:
            score = 0.9
        else:
            score = 0.4
    if score is not None:
        try:
            conn.execute("""
                UPDATE prompt_trace SET output_quality_score = ?
                WHERE prompt_key = ? AND output_quality_score IS NULL
                ORDER BY created_at DESC LIMIT 1
            """, (score, task_type))
            conn.commit()
        except Exception:
            pass


def is_model_capable(task_type: str) -> bool:
    """Check if the current model is large enough for this task type.

    Compares MODEL_SIZE_B (extracted from model name at startup) against
    the minimum required for the task in _TASK_COMPLEXITY.  Unknown tasks
    default to tier 1 (any model).

    With cloud-hosted 70B+ models, all task types should pass.
    """
    from ..settings import _TASK_COMPLEXITY, MODEL_SIZE_B
    min_size = _TASK_COMPLEXITY.get(task_type, 1.0)
    return MODEL_SIZE_B >= min_size


def generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    use_cache: bool = True,
    conn=None,
    task_type: str = "unknown",
) -> OllamaResponse:
    """Generate text via LLM. Tries primary model, falls back to smaller model.

    Skips the call entirely if the model is too small for the task_type,
    returning a failure so callers hit their rule-based fallback.
    """
    # Spend cap gate: skip non-critical tasks if monthly spend exceeded
    if IS_CLOUD_MODEL and conn is not None:
        from ..settings import LLM_MONTHLY_SPEND_CAP_USD
        if LLM_MONTHLY_SPEND_CAP_USD > 0:
            _CRITICAL_TASKS = {"drill_generation", "error_explanation", "openclaw_intent", "openclaw_chat"}
            if task_type not in _CRITICAL_TASKS:
                try:
                    spend_row = conn.execute("""
                        SELECT COALESCE(SUM(cost_usd), 0) as total
                        FROM llm_cost_log
                        WHERE created_at > datetime('now', 'start of month')
                    """).fetchone()
                    if spend_row and spend_row["total"] >= LLM_MONTHLY_SPEND_CAP_USD:
                        logger.warning(
                            "LLM spend cap reached ($%.2f/$%.2f) — skipping task '%s'",
                            spend_row["total"], LLM_MONTHLY_SPEND_CAP_USD, task_type,
                        )
                        return OllamaResponse(
                            success=False, model_used=LITELLM_MODEL,
                            error=f"Monthly LLM spend cap reached (${spend_row['total']:.2f}/${LLM_MONTHLY_SPEND_CAP_USD:.2f})",
                        )
                except Exception:
                    pass  # If cost table doesn't exist yet, proceed

    # Capability gate: skip if model is too small for this task
    if not is_model_capable(task_type):
        from ..settings import MODEL_SIZE_B, _TASK_COMPLEXITY
        min_size = _TASK_COMPLEXITY.get(task_type, 1.0)
        logger.info(
            "Skipping task '%s': model %s (%.1fb) below minimum %.1fb",
            task_type, LITELLM_MODEL, MODEL_SIZE_B, min_size,
        )
        return OllamaResponse(
            success=False, model_used=LITELLM_MODEL,
            error=f"Model too small for task '{task_type}' (have {MODEL_SIZE_B:.1f}b, need {min_size:.0f}b)",
        )

    # Check cache first
    if use_cache and conn is not None:
        cached = _check_cache(conn, prompt, system)
        if cached is not None:
            _log_generation(conn, task_type, cached)
            return cached

    # Task-specific model routing (from benchmark results in pi_model_registry)
    task_model = _get_task_model(conn, task_type)
    if task_model:
        models_to_try = [task_model, LITELLM_MODEL]
    else:
        models_to_try = [LITELLM_MODEL, LITELLM_FALLBACK]

    # Deduplicate while preserving order
    seen = set()
    unique_models = []
    for m in models_to_try:
        if m not in seen:
            seen.add(m)
            unique_models.append(m)

    # Try models in order (cloud-first, then fallback)
    result = None
    for i, model in enumerate(unique_models):
        result = _call_llm(prompt, system, model, temperature, max_tokens)
        if result.success:
            # Log if we fell back to a non-primary model
            if i > 0:
                logger.warning(
                    "LLM fallback: task '%s' served by %s (primary %s failed)",
                    task_type, model, unique_models[0],
                )
            if conn is not None:
                if use_cache:
                    _write_cache(conn, prompt, system, result)
                _log_generation(conn, task_type, result)
                _auto_score_quality(conn, task_type, result)
                _log_cost(conn, model, task_type, result)
            return result
        logger.warning("LLM %s failed: %s — trying next", model, result.error)

    # All models failed
    logger.error("All LLM providers failed for task '%s': %s", task_type,
                 result.error if result else "no models configured")
    failed = OllamaResponse(success=False, error=result.error if result else "all models failed")
    if conn is not None:
        _log_generation(conn, task_type, failed)
    return failed


def _call_llm(
    prompt: str, system: str, model: str, temperature: float, max_tokens: int,
) -> OllamaResponse:
    """Route LLM call through LiteLLM (falls back to direct httpx if unavailable)."""
    try:
        import litellm
        return _call_via_litellm(litellm, prompt, system, model, temperature, max_tokens)
    except ImportError:
        return _call_ollama_direct(prompt, system, model, temperature, max_tokens)


def _call_via_litellm(litellm, prompt, system, model, temperature, max_tokens):
    """LiteLLM-based call — supports any model provider via unified API.

    Handles cloud providers (Groq, Together, Fireworks, SiliconFlow, DeepSeek,
    Mistral) and local Ollama transparently. LiteLLM routes based on the model
    string prefix (groq/, together_ai/, fireworks_ai/, ollama/, etc.).
    """
    from ..settings import _is_cloud_model

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Cloud models use their name directly; local Ollama models need the prefix
    if _is_cloud_model(model) or "/" in model:
        litellm_model = model
        extra_kwargs = {}
    else:
        litellm_model = f"ollama/{model}"
        extra_kwargs = {"api_base": OLLAMA_URL}

    start = time.monotonic()
    try:
        resp = litellm.completion(
            model=litellm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=float(OLLAMA_TIMEOUT),
            **extra_kwargs,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        content = resp.choices[0].message.content if resp.choices else ""
        usage = resp.usage or type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()
        return OllamaResponse(
            success=True,
            text=content or "",
            model_used=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            generation_time_ms=elapsed_ms,
        )
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return OllamaResponse(
            success=False, model_used=model, generation_time_ms=elapsed_ms,
            error=str(e),
        )


def _call_ollama_direct(
    prompt: str, system: str, model: str, temperature: float, max_tokens: int,
) -> OllamaResponse:
    """Direct httpx fallback when LiteLLM is not installed."""
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


# Backward compat alias
_call_ollama = _call_ollama_direct


def _log_cost(conn, model: str, task_type: str, result: OllamaResponse) -> None:
    """Log per-call LLM cost for spend tracking."""
    try:
        # Estimate cost from token counts
        pt = result.prompt_tokens or 0
        ct = result.completion_tokens or 0
        # Local Ollama: ~$0, Cloud OSS: ~$0.30-0.90/M tokens (much cheaper than proprietary)
        from ..settings import _is_cloud_model
        model_lower = model.lower()
        if not _is_cloud_model(model):
            cost = 0.0  # Local is free
        elif "groq" in model_lower:
            cost = (pt * 0.00000059 + ct * 0.00000079)  # Groq rates
        elif "deepseek" in model_lower:
            cost = (pt * 0.00000028 + ct * 0.00000028)  # DeepSeek V3 rates
        elif "together" in model_lower or "fireworks" in model_lower:
            cost = (pt * 0.0000009 + ct * 0.0000009)  # ~$0.90/M avg
        else:
            cost = (pt * 0.000001 + ct * 0.000002)  # Conservative cloud OSS estimate

        conn.execute("""
            INSERT INTO llm_cost_log (model, task_type, prompt_tokens, completion_tokens, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (result.model_used, task_type, pt, ct, cost))
        conn.commit()
    except Exception:
        pass


def _prompt_hash(prompt: str, system: str) -> str:
    """SHA-256 hash of prompt + system for cache lookup."""
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    h.update(b"\x00")
    h.update(system.encode("utf-8"))
    return h.hexdigest()


def _check_cache(conn, prompt: str, system: str) -> OllamaResponse | None:
    """Look up a cached generation by prompt hash."""
    ph = _prompt_hash(prompt, system)
    row = conn.execute(
        "SELECT id, response_text, model_used FROM pi_ai_generation_cache WHERE prompt_hash = ?",
        (ph,),
    ).fetchone()
    if row is None:
        return None

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
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
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
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
    """Generate structured output via Instructor + LiteLLM.

    Uses instructor library to enforce JSON schema at the sampling level.
    Prefers LiteLLM backend; falls back to direct OpenAI-compat if unavailable.
    """
    try:
        import instructor
    except ImportError:
        return None

    start = time.monotonic()
    try:
        from ..settings import _is_cloud_model

        # Prefer LiteLLM backend for unified model routing
        try:
            import litellm
            client = instructor.from_litellm(
                litellm.completion,
                mode=instructor.Mode.JSON,
            )
        except ImportError:
            # Fallback: direct OpenAI-compatible endpoint (local Ollama)
            from openai import OpenAI
            client = instructor.from_openai(
                OpenAI(base_url=f"{OLLAMA_URL}/v1", api_key="ollama"),
                mode=instructor.Mode.JSON,
            )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Cloud models use name directly; local needs ollama/ prefix
        if _is_cloud_model(LITELLM_MODEL) or "/" in LITELLM_MODEL:
            structured_model = LITELLM_MODEL
            extra_kwargs = {}
        else:
            structured_model = f"ollama/{LITELLM_MODEL}"
            extra_kwargs = {"api_base": OLLAMA_URL}

        result = client.chat.completions.create(
            model=structured_model,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra_kwargs,
        )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        resp = OllamaResponse(
            success=True,
            text=result.model_dump_json() if hasattr(result, 'model_dump_json') else str(result),
            model_used=LITELLM_MODEL,
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
                success=False, model_used=LITELLM_MODEL,
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
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
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
