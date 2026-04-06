"""Agentic model selection — auto-discover, benchmark, and route.

When aelu runs in the cloud, this module autonomously:
1. Discovers available models (local Ollama or cloud providers via LiteLLM)
2. Benchmarks each model against each task type using cached prompts
3. Picks the best model per task (quality → latency → cost)
4. Activates routing so generate() uses the winner

Runs on the daily scheduler. No human intervention required.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import time
from datetime import datetime, timezone, UTC
from typing import Optional

import httpx

from ..settings import (
    OLLAMA_URL, LITELLM_MODEL, IS_CLOUD_MODEL,
    _TASK_COMPLEXITY, _extract_model_size_b,
)

# Backward-compat alias
OLLAMA_PRIMARY_MODEL = LITELLM_MODEL

logger = logging.getLogger(__name__)

# Benchmark config
_BENCHMARK_SAMPLE_SIZE = 10
_MIN_QUALITY_THRESHOLD = 0.6
_MIN_SAMPLES_FOR_ROUTING = 5
_REBENCHMARK_DAYS = 7

# Provider → API key env var mapping
# New providers are auto-activated when their API key env var is set.
_PROVIDER_KEY_MAP = {
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "sambanova": "SAMBANOVA_API_KEY",
    "novita": "NOVITA_API_KEY",
    "lepton": "LEPTON_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Provider → (models_endpoint, LiteLLM prefix)
_PROVIDER_API_ENDPOINTS = {
    "together": ("https://api.together.xyz/v1/models", "together_ai"),
    "groq": ("https://api.groq.com/openai/v1/models", "groq"),
    "deepseek": ("https://api.deepseek.com/v1/models", "deepseek"),
    "fireworks": ("https://api.fireworks.ai/inference/v1/models", "fireworks_ai"),
    "mistral": ("https://api.mistral.ai/v1/models", "mistral"),
    "cerebras": ("https://api.cerebras.ai/v1/models", "cerebras"),
    "sambanova": ("https://api.sambanova.ai/v1/models", "sambanova"),
    "novita": ("https://api.novita.ai/v3/openai/models", "novita"),
    "lepton": ("https://api.lepton.ai/v1/models", "lepton"),
}

_MIN_MODEL_SIZE_B = 3.0  # Skip models below 3B params
_CHAT_MODEL_KEYWORDS = {"chat", "instruct", "it", "turbo", "versatile", "latest"}

def _provider_has_key(provider: str) -> bool:
    """Check if a cloud provider has an API key configured."""
    from .. import settings as _settings
    key_name = _PROVIDER_KEY_MAP.get(provider, "")
    if not key_name:
        return False
    return bool(getattr(_settings, key_name, None))

# Known open-source models available on major cloud providers.
# model_selector auto-discovers new models weekly; this is the seed list.
# LiteLLM handles routing based on the model string prefix.
_CLOUD_OSS_MODELS = [
    # Groq — ultra-fast inference via custom LPU hardware
    {"name": "groq/llama-3.3-70b-versatile", "provider": "groq", "size_b": 70.0},
    {"name": "groq/llama-3.1-8b-instant", "provider": "groq", "size_b": 8.0},
    {"name": "groq/mixtral-8x7b-32768", "provider": "groq", "size_b": 47.0},
    {"name": "groq/gemma2-9b-it", "provider": "groq", "size_b": 9.0},

    # Together AI — widest model selection
    {"name": "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo", "provider": "together", "size_b": 70.0},
    {"name": "together_ai/meta-llama/Llama-3.1-8B-Instruct-Turbo", "provider": "together", "size_b": 8.0},
    {"name": "together_ai/mistralai/Mixtral-8x7B-Instruct-v0.1", "provider": "together", "size_b": 47.0},
    {"name": "together_ai/Qwen/Qwen2.5-72B-Instruct", "provider": "together", "size_b": 72.0},
    {"name": "together_ai/Qwen/Qwen2.5-7B-Instruct", "provider": "together", "size_b": 7.0},
    {"name": "together_ai/deepseek-ai/DeepSeek-V3", "provider": "together", "size_b": 671.0},
    {"name": "together_ai/google/gemma-2-27b-it", "provider": "together", "size_b": 27.0},

    # Fireworks AI — fast long-context inference
    {"name": "fireworks_ai/accounts/fireworks/models/llama-v3p1-70b-instruct", "provider": "fireworks", "size_b": 70.0},

    # DeepSeek — best cost/quality ratio
    {"name": "deepseek/deepseek-chat", "provider": "deepseek", "size_b": 200.0},

    # Mistral — strong Mistral/Mixtral models, EU data residency
    {"name": "mistral/mistral-large-latest", "provider": "mistral", "size_b": 123.0},
    {"name": "mistral/mistral-small-latest", "provider": "mistral", "size_b": 22.0},
]


# ─── Discovery ──────────────────────────────────────────────────


def _is_chat_model(model_id: str, model_data: dict = None) -> bool:
    """Heuristic: is this model suitable for chat/instruction tasks?"""
    model_lower = model_id.lower()
    # Exclude known non-chat model types
    if any(skip in model_lower for skip in (
        "embed", "whisper", "tts", "vision-only", "rerank",
        "guard", "safety", "clip", "vae", "encoder",
    )):
        return False
    # Include if name has chat/instruct keywords or is a known architecture
    if any(kw in model_lower for kw in _CHAT_MODEL_KEYWORDS):
        return True
    # Check model_data type field if available
    if model_data:
        mtype = str(model_data.get("type", "")).lower()
        if mtype in ("chat", "language", "text-generation"):
            return True
    # Default: include if size is reasonable (let benchmarking filter poor performers)
    return True


def _discover_from_openrouter(seen_names: set) -> list[dict]:
    """Query OpenRouter for all available open-source models.

    OpenRouter aggregates models from dozens of providers. New providers
    and models appear automatically — this is how we discover new players
    without hardcoding them. Filters to open-source models only.
    """
    from .. import settings as _settings
    api_key = getattr(_settings, "OPENROUTER_API_KEY", None)
    if not api_key:
        return []

    discovered = []
    try:
        resp = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )
        if resp.status_code != 200:
            return []

        for m in resp.json().get("data", []):
            model_id = m.get("id", "")
            if not model_id:
                continue

            # OpenRouter marks proprietary models; skip them
            pricing = m.get("pricing", {})
            # Skip if no pricing data (likely not available)
            if not pricing:
                continue

            # Filter: only instruct/chat models
            if not _is_chat_model(model_id, m):
                continue

            # Size filter
            size = _extract_model_size_b(model_id)
            if 0 < size < _MIN_MODEL_SIZE_B:
                continue

            full_name = f"openrouter/{model_id}"
            if full_name in seen_names:
                continue

            discovered.append({
                "name": full_name,
                "provider": "openrouter",
                "size_b": size,
                "local": False,
            })
            seen_names.add(full_name)

    except Exception:
        logger.debug("Model discovery: OpenRouter API failed", exc_info=True)

    if discovered:
        logger.info("Model discovery: %d open-source models from OpenRouter",
                     len(discovered))

    return discovered


def _discover_from_provider_apis(seen_names: set) -> list[dict]:
    """Query each configured provider's /models endpoint for live catalog.

    Discovers new models released since the seed list was last updated.
    """
    from .. import settings as _settings
    discovered = []

    for provider, (endpoint, litellm_prefix) in _PROVIDER_API_ENDPOINTS.items():
        key_name = _PROVIDER_KEY_MAP.get(provider, "")
        api_key = getattr(_settings, key_name, None) if key_name else None
        if not api_key:
            continue

        try:
            resp = httpx.get(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            # Most providers follow OpenAI format: {"data": [...]}
            models_list = data.get("data", data.get("models", []))
            if isinstance(data, list):
                models_list = data

            for m in models_list:
                if isinstance(m, str):
                    model_id = m
                    model_data = {}
                elif isinstance(m, dict):
                    model_id = m.get("id", m.get("name", ""))
                    model_data = m
                else:
                    continue

                if not model_id:
                    continue

                # Format with LiteLLM prefix
                full_name = f"{litellm_prefix}/{model_id}"
                if full_name in seen_names:
                    continue

                # Filter: chat-capable and large enough
                if not _is_chat_model(model_id, model_data):
                    continue

                size = _extract_model_size_b(model_id)
                if size < _MIN_MODEL_SIZE_B and size > 0:
                    continue

                discovered.append({
                    "name": full_name,
                    "provider": provider,
                    "size_b": size,
                    "local": False,
                })
                seen_names.add(full_name)

        except Exception:
            logger.debug("Model discovery: %s API failed", provider, exc_info=True)

    if discovered:
        logger.info("Model discovery: %d new models from provider APIs: %s",
                     len(discovered),
                     ", ".join(m["name"] for m in discovered[:5]))

    return discovered


def discover_available_models(conn=None) -> list[dict]:
    """Discover models available across all configured providers.

    Cloud-first: seed list → live provider APIs → LiteLLM → local Ollama.
    Runs daily via the model selection scheduler.
    """
    models = []
    seen_names = set()

    # 1. OpenRouter: meta-provider — discovers new providers and models autonomously.
    #    First so it's the source of truth for what's available.
    openrouter_models = _discover_from_openrouter(seen_names)
    models.extend(openrouter_models)

    # 2. Direct provider APIs: query each configured provider for their catalog
    live_models = _discover_from_provider_apis(seen_names)
    models.extend(live_models)

    # 3. Seed list: known-good models as fallback if APIs are down
    for m in _CLOUD_OSS_MODELS:
        provider = m["provider"]
        if _provider_has_key(provider) and m["name"] not in seen_names:
            models.append({**m, "local": False})
            seen_names.add(m["name"])

    # 4. LiteLLM model list (static, updates with pip upgrade)
    try:
        import litellm
        provider_models = getattr(litellm, "models", None)
        if isinstance(provider_models, (list, tuple)):
            for name in provider_models[:100]:
                if isinstance(name, str) and name not in seen_names:
                    models.append({
                        "name": name,
                        "provider": "litellm",
                        "size_b": _extract_model_size_b(name),
                        "local": False,
                    })
                    seen_names.add(name)
    except Exception:
        pass

    # 5. Local Ollama
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        if resp.status_code == 200:
            for m in resp.json().get("models", []):
                name = m.get("name", "")
                if name and name not in seen_names:
                    models.append({
                        "name": name,
                        "provider": "ollama",
                        "size_b": _extract_model_size_b(name),
                        "local": True,
                    })
                    seen_names.add(name)
    except Exception:
        pass

    cloud_count = sum(1 for m in models if not m.get("local"))
    local_count = sum(1 for m in models if m.get("local"))
    logger.info("Model discovery: found %d models (%d cloud, %d local, %d OpenRouter, %d direct API)",
                len(models), cloud_count, local_count, len(openrouter_models), len(live_models))
    if cloud_count == 0 and local_count == 0:
        logger.error("Model discovery: NO models available — check API keys and Ollama")
    elif cloud_count == 0:
        logger.warning("Model discovery: no cloud models — using local Ollama only")
    return models


# ─── Benchmarking ───────────────────────────────────────────────

def benchmark_model_on_task(conn, model_name: str, task_type: str,
                            sample_size: int = _BENCHMARK_SAMPLE_SIZE) -> dict:
    """Benchmark a model on a task using cached prompts as test cases.

    Uses the current primary model as a judge to score candidate outputs.
    """
    # Get cached prompt/response pairs for this task type
    try:
        rows = conn.execute("""
            SELECT prompt_text, response_text, model_used
            FROM pi_ai_generation_cache c
            JOIN pi_ai_generation_log l ON c.prompt_hash = (
                SELECT prompt_hash FROM pi_ai_generation_cache
                WHERE id = c.id
            )
            WHERE c.response_text IS NOT NULL AND c.response_text != ''
            ORDER BY RANDOM()
            LIMIT ?
        """, (sample_size,)).fetchall()
    except Exception:
        rows = []

    # Fallback: get any cached prompts
    if not rows:
        try:
            rows = conn.execute("""
                SELECT prompt_text, response_text, model_used
                FROM pi_ai_generation_cache
                WHERE response_text IS NOT NULL AND response_text != ''
                ORDER BY RANDOM()
                LIMIT ?
            """, (sample_size,)).fetchall()
        except Exception:
            rows = []

    if not rows:
        return {"quality": None, "latency_p50": None, "sample_count": 0}

    from .ollama_client import _call_llm

    scores = []
    latencies = []

    for row in rows:
        prompt_text = row["prompt_text"] or ""
        reference = row["response_text"] or ""

        if not prompt_text.strip():
            continue

        # Run the candidate model
        start = time.monotonic()
        result = _call_llm(prompt_text, "", model_name, 0.3, 1024)
        latency_ms = int((time.monotonic() - start) * 1000)

        if not result.success:
            scores.append(0.0)
            latencies.append(latency_ms)
            continue

        latencies.append(latency_ms)
        candidate = result.text

        # Score: structural quality checks (fast, no extra LLM call)
        score = _score_output(task_type, candidate, reference)
        scores.append(score)

    if not scores:
        return {"quality": None, "latency_p50": None, "sample_count": 0}

    return {
        "quality": statistics.mean(scores),
        "latency_p50": int(statistics.median(latencies)) if latencies else None,
        "latency_p95": int(sorted(latencies)[int(len(latencies) * 0.95)]) if len(latencies) > 1 else latencies[0] if latencies else None,
        "sample_count": len(scores),
    }


def _score_output(task_type: str, candidate: str, reference: str) -> float:
    """Score candidate output quality 0-1 without an LLM judge call.

    Uses structural checks: JSON validity, length ratio, key overlap.
    """
    if not candidate.strip():
        return 0.0

    score = 0.5  # baseline: produced non-empty output

    # JSON validity check (many tasks expect JSON)
    candidate_json = _try_parse_json(candidate)
    reference_json = _try_parse_json(reference)

    if reference_json is not None:
        # Reference was JSON — candidate should be too
        if candidate_json is not None:
            score += 0.2  # valid JSON
            # Key overlap for dicts
            if isinstance(reference_json, dict) and isinstance(candidate_json, dict):
                ref_keys = set(reference_json.keys())
                cand_keys = set(candidate_json.keys())
                if ref_keys:
                    overlap = len(ref_keys & cand_keys) / len(ref_keys)
                    score += 0.2 * overlap
        else:
            score -= 0.3  # expected JSON but got freetext
    else:
        # Reference was freetext — check length ratio
        if reference:
            ratio = len(candidate) / max(len(reference), 1)
            if 0.3 < ratio < 3.0:
                score += 0.2  # reasonable length

    # Chinese character presence (most tasks should produce some)
    if re.search(r"[\u4e00-\u9fff]", candidate):
        score += 0.1

    return min(max(score, 0.0), 1.0)


def _try_parse_json(text: str):
    """Try to parse JSON, return parsed or None."""
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# ─── Selection ──────────────────────────────────────────────────

def select_best_model_per_task(conn) -> dict[str, str]:
    """Pick the best benchmarked model for each task type."""
    routing = {}
    try:
        rows = conn.execute("""
            SELECT task_type, model_name, quality_score, latency_p50_ms,
                   cost_per_1k_tokens, sample_count
            FROM pi_model_registry
            WHERE quality_score >= ? AND sample_count >= ?
            ORDER BY task_type, quality_score DESC, latency_p50_ms ASC,
                     COALESCE(cost_per_1k_tokens, 999) ASC
        """, (_MIN_QUALITY_THRESHOLD, _MIN_SAMPLES_FOR_ROUTING)).fetchall()
    except Exception:
        return routing

    for row in rows:
        task = row["task_type"]
        if task not in routing:  # first row per task is the winner (sorted by quality desc)
            routing[task] = row["model_name"]

    return routing


def apply_model_routing(conn, routing: dict[str, str]) -> None:
    """Activate the selected models in the registry."""
    datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Deactivate all
    try:
        conn.execute("UPDATE pi_model_registry SET is_active = 0")
    except Exception:
        return

    # Activate winners
    for task_type, model_name in routing.items():
        try:
            conn.execute("""
                UPDATE pi_model_registry SET is_active = 1
                WHERE task_type = ? AND model_name = ?
            """, (task_type, model_name))
        except Exception:
            pass

    try:
        conn.commit()
    except Exception:
        pass

    logger.info("Model routing updated: %d task types routed", len(routing))
    for task, model in sorted(routing.items()):
        logger.info("  %s → %s", task, model)


# ─── Main Cycle ─────────────────────────────────────────────────

def run_model_selection_cycle(conn) -> dict:
    """Full model selection cycle: discover → benchmark → select → route.

    Called by the daily scheduler. Benchmarks are cached for _REBENCHMARK_DAYS.
    """
    result = {"models_found": 0, "benchmarks_run": 0, "tasks_routed": 0}

    # 1. Discover
    models = discover_available_models(conn)
    result["models_found"] = len(models)
    if not models:
        return result

    # 2. Get task types that have cached data
    task_types = list(_TASK_COMPLEXITY.keys())

    # 3. Benchmark each (model, task) pair not benchmarked recently
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    benchmarks_run = 0

    for model_info in models:
        model_name = model_info["name"]
        provider = model_info.get("provider", "unknown")

        for task_type in task_types:
            # Skip if benchmarked recently
            try:
                row = conn.execute("""
                    SELECT benchmarked_at FROM pi_model_registry
                    WHERE task_type = ? AND model_name = ?
                    AND benchmarked_at >= datetime('now', ?)
                """, (task_type, model_name, f"-{_REBENCHMARK_DAYS} days")).fetchone()
                if row:
                    continue
            except Exception:
                pass

            # Check if model is plausibly capable (don't benchmark 1.5b on complex tasks)
            min_size = _TASK_COMPLEXITY.get(task_type, 1.0)
            if model_info.get("size_b", 0) < min_size:
                continue

            # Run benchmark
            logger.info("Benchmarking %s on task '%s'...", model_name, task_type)
            bench = benchmark_model_on_task(conn, model_name, task_type)

            if bench["quality"] is None:
                continue

            # Upsert result
            try:
                conn.execute("""
                    INSERT INTO pi_model_registry
                    (task_type, model_name, provider, quality_score,
                     latency_p50_ms, latency_p95_ms, sample_count, benchmarked_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_type, model_name) DO UPDATE SET
                        quality_score = excluded.quality_score,
                        latency_p50_ms = excluded.latency_p50_ms,
                        latency_p95_ms = excluded.latency_p95_ms,
                        sample_count = excluded.sample_count,
                        benchmarked_at = excluded.benchmarked_at
                """, (
                    task_type, model_name, provider,
                    bench["quality"], bench["latency_p50"],
                    bench.get("latency_p95"), bench["sample_count"], now,
                ))
                conn.commit()
                benchmarks_run += 1
            except Exception:
                logger.debug("Failed to save benchmark for %s/%s", model_name, task_type, exc_info=True)

    result["benchmarks_run"] = benchmarks_run

    # 4. Select best per task
    routing = select_best_model_per_task(conn)
    result["tasks_routed"] = len(routing)

    # 5. Apply routing
    if routing:
        apply_model_routing(conn, routing)

    logger.info(
        "Model selection cycle: %d models, %d benchmarks, %d tasks routed",
        result["models_found"], result["benchmarks_run"], result["tasks_routed"],
    )
    return result
