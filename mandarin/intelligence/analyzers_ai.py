"""Product Intelligence — AI/GenAI/agentic technology analyzers.

8 analyzers that inspect the AI stack: model diversity, output quality,
streaming, OpenClaw maturity, ML model health, agentic coverage,
AI feedback loops, and AI marketing readiness.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query_all

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_AI_DIR = os.path.join(_PROJECT_ROOT, "mandarin", "ai")
_OPENCLAW_DIR = os.path.join(_PROJECT_ROOT, "mandarin", "openclaw")
_TEMPLATE_DIR = os.path.join(_PROJECT_ROOT, "mandarin", "web", "templates")


def _read_file(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _scan_dir(directory: str, pattern: str = "*.py") -> dict[str, str]:
    """Read all matching files in a directory."""
    results = {}
    for path in glob.glob(os.path.join(directory, pattern)):
        content = _read_file(path)
        if content:
            results[os.path.basename(path)] = content
    return results


# ── 1. GenAI Model Diversity ─────────────────────────────────────

def _analyze_genai_model_diversity(conn) -> list[dict]:
    """Check whether aelu relies on a single model with no comparison."""
    findings = []
    ai_files = _scan_dir(_AI_DIR)

    # Check how many distinct model references exist
    model_refs = set()
    for content in ai_files.values():
        for match in re.findall(r"(?:qwen|llama|mistral|phi|gemma|deepseek)[\w.:/-]*", content, re.I):
            model_refs.add(match.lower().split(":")[0])

    if len(model_refs) <= 1:
        findings.append(_finding(
            "genai", "medium",
            "Single LLM model dependency — no model comparison",
            f"Only {len(model_refs)} model family referenced across {len(ai_files)} AI files. "
            "Without comparing outputs from multiple models, there is no way to measure "
            "whether the current model produces optimal results.",
            "Add LiteLLM model router to compare Qwen 7b vs 14b outputs on the same prompts. "
            "Log quality scores per model to identify the best model for each task type.",
            "In mandarin/ai/ollama_client.py, configure LiteLLM with multiple model aliases "
            "and add A/B logging to prompt_trace to compare output quality by model.",
            "GenAI reliability",
            ["mandarin/ai/ollama_client.py", "mandarin/settings.py"],
        ))

    # Check for prompt A/B testing
    has_ab_test = False
    for content in ai_files.values():
        if re.search(r"(?:ab_test|variant|experiment|split_test)", content, re.I):
            has_ab_test = True
            break
    if not has_ab_test:
        findings.append(_finding(
            "genai", "low",
            "No prompt A/B testing infrastructure",
            "No evidence of prompt variant testing. Manual prompt engineering without "
            "measurement leads to unknown quality drift.",
            "Add prompt variant support to PROMPT_REGISTRY with quality_score tracking.",
            "In mandarin/ai/genai_layer.py PROMPT_REGISTRY, add a 'variants' field "
            "and log which variant was used in prompt_trace.",
            "GenAI optimization",
            ["mandarin/ai/genai_layer.py"],
        ))

    return findings


# ── 2. GenAI Output Quality ──────────────────────────────────────

def _analyze_genai_output_quality(conn) -> list[dict]:
    """Check LLM generation success rates and quality scores."""
    findings = []

    # Generation log stats
    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_generation_log
        WHERE occurred_at >= datetime('now', '-14 days')
    """)
    if total and total > 10:
        failures = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_ai_generation_log
            WHERE occurred_at >= datetime('now', '-14 days') AND success = 0
        """) or 0
        failure_rate = failures / total
        if failure_rate > 0.05:
            findings.append(_finding(
                "genai", "high" if failure_rate > 0.15 else "medium",
                f"LLM generation failure rate: {failure_rate:.0%} ({failures}/{total})",
                f"In the last 14 days, {failure_rate:.0%} of LLM calls failed. "
                "This directly impacts drill generation, error explanations, and content creation.",
                "Investigate error patterns in pi_ai_generation_log. Common causes: model timeout, "
                "JSON parse failure, out-of-memory.",
                "Query pi_ai_generation_log WHERE success=0 grouped by error to find patterns.",
                "GenAI reliability",
                ["mandarin/ai/ollama_client.py"],
            ))

        # Latency P95
        try:
            p95 = conn.execute("""
                SELECT generation_time_ms FROM pi_ai_generation_log
                WHERE occurred_at >= datetime('now', '-14 days') AND success = 1
                ORDER BY generation_time_ms DESC
                LIMIT 1 OFFSET (
                    SELECT CAST(COUNT(*) * 0.05 AS INTEGER) FROM pi_ai_generation_log
                    WHERE occurred_at >= datetime('now', '-14 days') AND success = 1
                )
            """).fetchone()
            if p95 and p95[0] > 10000:
                findings.append(_finding(
                    "genai", "medium",
                    f"LLM P95 latency: {p95[0] / 1000:.1f}s — users waiting too long",
                    f"95th percentile generation time is {p95[0]}ms. For interactive features "
                    "like drill generation and error explanations, this causes noticeable UI lag.",
                    "Add streaming support for interactive LLM calls. Consider a smaller model "
                    "for latency-sensitive tasks.",
                    "Add SSE streaming to mandarin/ai/ollama_client.py generate() and update "
                    "app.js to consume streamed responses.",
                    "GenAI performance",
                    ["mandarin/ai/ollama_client.py", "mandarin/web/static/app.js"],
                ))
        except Exception:
            pass

    # Quality score distribution from prompt_trace
    try:
        low_quality = _safe_scalar(conn, """
            SELECT COUNT(*) FROM prompt_trace
            WHERE quality_score IS NOT NULL AND quality_score < 0.7
            AND created_at >= datetime('now', '-14 days')
        """)
        total_traced = _safe_scalar(conn, """
            SELECT COUNT(*) FROM prompt_trace
            WHERE quality_score IS NOT NULL
            AND created_at >= datetime('now', '-14 days')
        """)
        if total_traced and total_traced > 10 and low_quality:
            low_rate = low_quality / total_traced
            if low_rate > 0.20:
                findings.append(_finding(
                    "genai", "medium",
                    f"Low-quality LLM outputs: {low_rate:.0%} score below 0.7",
                    f"{low_quality}/{total_traced} traced prompts scored below 0.7 quality. "
                    "This suggests prompt templates need optimization or the model is "
                    "underperforming on certain task types.",
                    "Use DSPy to auto-optimize prompts with low quality scores.",
                    "Query prompt_trace GROUP BY prompt_key to find which tasks have "
                    "the lowest quality. Apply DSPy BootstrapFewShot optimization.",
                    "GenAI quality",
                    ["mandarin/ai/genai_layer.py", "mandarin/ai/dspy_modules.py"],
                ))
    except Exception:
        pass

    return findings


# ── 3. GenAI Streaming ───────────────────────────────────────────

def _analyze_genai_streaming(conn) -> list[dict]:
    """Check if LLM responses are streamed or block the UI."""
    findings = []
    ai_files = _scan_dir(_AI_DIR)

    has_streaming = False
    for content in ai_files.values():
        if re.search(r"(?:stream|SSE|Server-Sent|chunk|yield)", content, re.I):
            has_streaming = True
            break

    if not has_streaming:
        findings.append(_finding(
            "genai", "medium",
            "No LLM streaming — responses block the UI until complete",
            "All LLM calls use synchronous completion (stream=False). For interactive "
            "features like drill generation and error explanations, users see a loading "
            "spinner for 5-15 seconds with no progress indication.",
            "Add streaming support via LiteLLM's stream=True mode. Deliver tokens "
            "via WebSocket (already available in the Flask app via flask-sock).",
            "In mandarin/ai/ollama_client.py, add a generate_stream() function that "
            "yields tokens. In app.js, consume via WebSocket for real-time display.",
            "GenAI UX",
            ["mandarin/ai/ollama_client.py", "mandarin/web/static/app.js"],
        ))

    return findings


# ── 4. OpenClaw Maturity ─────────────────────────────────────────

def _analyze_openclaw_maturity(conn) -> list[dict]:
    """Assess OpenClaw bot infrastructure maturity."""
    findings = []
    openclaw_files = _scan_dir(_OPENCLAW_DIR)

    # Check for conversation memory
    has_memory = False
    for content in openclaw_files.values():
        if re.search(r"(?:memory|mem0|conversation_history|chat_history)", content, re.I):
            has_memory = True
            break
    if not has_memory:
        findings.append(_finding(
            "agentic", "medium",
            "OpenClaw bots have no conversation memory",
            "All 5 bot channels (iMessage, Telegram, Discord, WhatsApp, Voice) are stateless. "
            "Each message is processed independently with no awareness of prior conversation. "
            "Users must repeat context every time they interact.",
            "Integrate mem0 for per-user conversation memory. Add search_memory() before "
            "LLM calls and add_memory() after responses.",
            "In mandarin/openclaw/llm_handler.py, inject mem0 context into the system prompt "
            "before generate_chat_response(). Store each turn via add_memory().",
            "Agentic maturity",
            ["mandarin/openclaw/llm_handler.py", "mandarin/ai/memory.py"],
        ))

    # Check for proactive notifications
    has_notifications = False
    for content in openclaw_files.values():
        if re.search(r"(?:notify_owner|proactive|scheduled_message|push_notification)", content, re.I):
            has_notifications = True
            break
    if not has_notifications:
        findings.append(_finding(
            "agentic", "low",
            "OpenClaw has no proactive notification capability",
            "Bots only respond to incoming messages. No ability to proactively alert the "
            "owner about audit findings, system issues, or learner milestones.",
            "Add notify_owner() to openclaw/__init__.py that sends via the best available channel.",
            "Add notify_owner() function that tries iMessage → Telegram → Discord in order.",
            "Agentic proactivity",
            ["mandarin/openclaw/__init__.py"],
        ))

    # Check for student/learner interface
    has_student_access = False
    for content in openclaw_files.values():
        if re.search(r"(?:student|learner|role_check|user_role|rbac)", content, re.I):
            has_student_access = True
            break
    if not has_student_access:
        findings.append(_finding(
            "agentic", "low",
            "OpenClaw is admin-only — no student/learner bot interface",
            "Bot interactions are restricted to the owner/admin. Students cannot interact "
            "with the system via messaging channels for practice, questions, or progress checks.",
            "Add role-based access so students can interact via Telegram/Discord for "
            "vocabulary practice and progress queries.",
            "Add user_role field to OpenClaw security context. Route student queries "
            "to safe, read-only command handlers.",
            "Agentic reach",
            ["mandarin/openclaw/security.py", "mandarin/openclaw/llm_handler.py"],
        ))

    return findings


# ── 5. ML Model Health ───────────────────────────────────────────

def _analyze_ml_model_health(conn) -> list[dict]:
    """Check traditional ML model health (LightGBM difficulty predictor)."""
    findings = []

    # Check model staleness
    try:
        last_train = _safe_scalar(conn, """
            SELECT MAX(created_at) FROM pi_difficulty_predictions
        """)
        if last_train:
            stale = _safe_scalar(conn, """
                SELECT ? < datetime('now', '-14 days')
            """, (last_train,))
            if stale:
                findings.append(_finding(
                    "genai", "medium",
                    "Difficulty prediction model has not retrained in 14+ days",
                    f"Last prediction recorded at {last_train}. Model drift increases as "
                    "learner patterns change but the model remains frozen.",
                    "Add periodic model retraining triggered by the intelligence loop.",
                    "In mandarin/ai/agentic.py recalibrate_fsrs handler, also trigger "
                    "LightGBM retraining from mandarin/ai/memory_model.py.",
                    "ML freshness",
                    ["mandarin/ai/memory_model.py"],
                ))
    except Exception:
        pass

    # Check for ensemble / model comparison
    ai_files = _scan_dir(_AI_DIR)
    has_ensemble = False
    for content in ai_files.values():
        if re.search(r"(?:ensemble|voting|stacking|model_comparison|model_registry)", content, re.I):
            has_ensemble = True
            break
    if not has_ensemble:
        findings.append(_finding(
            "genai", "low",
            "Single ML model with no ensemble or comparison",
            "Only one LightGBM model is used for difficulty prediction. No ensemble, "
            "no model versioning, no A/B testing of model versions.",
            "Add model versioning to track prediction accuracy over time. "
            "Consider a simple ensemble with FSRS as baseline.",
            "Add a model_version field to pi_difficulty_predictions and log accuracy "
            "per version for comparison.",
            "ML robustness",
            ["mandarin/ai/memory_model.py"],
        ))

    return findings


# ── 6. Agentic Coverage ─────────────────────────────────────────

def _analyze_agentic_coverage(conn) -> list[dict]:
    """Check the breadth and success rate of autonomous actions."""
    findings = []

    # Count auto-executable action types
    try:
        from ..ai.agentic import _AUTO_EXECUTABLE_ACTIONS
        action_count = len(_AUTO_EXECUTABLE_ACTIONS)
        if action_count < 8:
            findings.append(_finding(
                "agentic", "medium",
                f"Only {action_count} auto-executable action types — most findings require human action",
                f"The prescription executor recognizes {action_count} action types. "
                "Findings from discipline analyzers (visual_design, animation, etc.) "
                "cannot be auto-executed and queue indefinitely.",
                "Expand classify_prescription() with patterns for CSS, template, config, "
                "security, and platform sync actions.",
                "In mandarin/ai/agentic.py, add keyword patterns for the 5 new action "
                "types and route them to the LangGraph agent.",
                "Agentic coverage",
                ["mandarin/ai/agentic.py"],
            ))
    except ImportError:
        pass

    # Prescription execution success rate
    try:
        total = _safe_scalar(conn, """
            SELECT COUNT(*) FROM prescription_execution_log
            WHERE created_at >= datetime('now', '-30 days')
        """)
        if total and total >= 5:
            executed = _safe_scalar(conn, """
                SELECT COUNT(*) FROM prescription_execution_log
                WHERE created_at >= datetime('now', '-30 days') AND status = 'executed'
            """) or 0
            _safe_scalar(conn, """
                SELECT COUNT(*) FROM prescription_execution_log
                WHERE created_at >= datetime('now', '-30 days') AND status = 'error'
            """) or 0
            exec_rate = executed / total
            if exec_rate < 0.20:
                findings.append(_finding(
                    "agentic", "medium",
                    f"Low auto-execution rate: {exec_rate:.0%} ({executed}/{total})",
                    f"Only {exec_rate:.0%} of prescriptions auto-execute. The rest require "
                    "human intervention, creating a bottleneck for a solo developer.",
                    "Expand action type classification and add the LangGraph code change agent.",
                    "Review prescription_execution_log for 'requires_human' entries and "
                    "add keyword patterns to classify_prescription().",
                    "Agentic throughput",
                    ["mandarin/ai/agentic.py", "mandarin/ai/llm_agent.py"],
                ))
    except Exception:
        pass

    return findings


# ── 7. AI Feedback Loops ─────────────────────────────────────────

def _analyze_ai_feedback_loops(conn) -> list[dict]:
    """Check if AI systems are learning from their own outputs."""
    findings = []

    # Prediction outcome distribution
    try:
        rows = _safe_query_all(conn, """
            SELECT outcome_class, COUNT(*) as cnt
            FROM pi_prediction_outcome
            WHERE recorded_at >= datetime('now', '-30 days')
            GROUP BY outcome_class
        """)
        if rows:
            total = sum(r["cnt"] for r in rows)
            outcomes = {r["outcome_class"]: r["cnt"] for r in rows}
            wrong = outcomes.get("wrong", 0)
            if total >= 10 and wrong / total > 0.30:
                findings.append(_finding(
                    "genai", "medium",
                    f"High prediction false positive rate: {wrong / total:.0%}",
                    f"{wrong}/{total} scored predictions were wrong in the last 30 days. "
                    "The intelligence system is making confident predictions that don't match reality.",
                    "Review the influence model directions and retrain with more observations.",
                    "Check pi_prediction_outcome for patterns in wrong predictions.",
                    "AI calibration",
                    ["mandarin/intelligence/feedback_loops.py"],
                ))
    except Exception:
        pass

    # Check if influence model is learning
    try:
        learned = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT dimension) FROM pi_influence_observation
            WHERE observation_count >= 10
        """)
        total_dims = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT dimension) FROM pi_influence_observation
        """)
        if total_dims and total_dims > 0 and (learned or 0) < total_dims * 0.3:
            findings.append(_finding(
                "genai", "low",
                f"Influence model learning slowly: {learned or 0}/{total_dims} dimensions have 10+ observations",
                "Most dimensions have insufficient observations for the influence model "
                "to learn reliable parameter-score relationships.",
                "Run more audit cycles. Each audit produces observations that feed the model.",
                "The influence model learns automatically from audit data. Run more cycles.",
                "AI learning",
                ["mandarin/intelligence/change_generator.py"],
            ))
    except Exception:
        pass

    return findings


# ── 8. AI Marketing Readiness ────────────────────────────────────

def _analyze_ai_marketing_readiness(conn) -> list[dict]:
    """Check if AI features are surfaced and marketable."""
    findings = []

    # Check templates for AI messaging
    templates = {}
    for name in ["index.html", "login.html", "register.html"]:
        content = _read_file(os.path.join(_TEMPLATE_DIR, name))
        if content:
            templates[name] = content

    has_ai_messaging = False
    for content in templates.values():
        if re.search(r"(?:AI|artificial intelligence|powered by|smart|intelligent|adaptive)",
                      content, re.I):
            has_ai_messaging = True
            break

    if not has_ai_messaging:
        findings.append(_finding(
            "marketing", "medium",
            "AI features invisible to users — missing marketing opportunity",
            "The app uses AI/ML for drill generation, difficulty prediction, "
            "error explanations, and content creation, but none of this is communicated "
            "to users in the UI. AI is a key differentiator that should be visible.",
            "Add 'AI-powered' badges to drill generation, error explanations, and "
            "reading passages. Surface AI features on the landing/login page.",
            "In mandarin/web/templates/index.html and app.js, add visual indicators "
            "for AI-generated content (e.g., sparkle icon, 'Powered by AI' tag).",
            "Marketing differentiation",
            ["mandarin/web/templates/index.html", "mandarin/web/static/app.js"],
        ))

    # Check for feature flags
    ai_files = _scan_dir(_AI_DIR)
    has_feature_flags = False
    for content in ai_files.values():
        if re.search(r"(?:feature_flag|feature_toggle|gradual_rollout|canary)", content, re.I):
            has_feature_flags = True
            break
    if not has_feature_flags:
        findings.append(_finding(
            "marketing", "low",
            "No AI feature flags for gradual rollout",
            "AI features have no toggle mechanism. New AI capabilities are either fully "
            "deployed or not — no way to gradually roll out to a subset of users.",
            "Add a simple feature flag system for AI features (e.g., in learner_profile.json).",
            "Add a FEATURE_FLAGS dict in settings.py with toggles for AI features.",
            "Marketing control",
            ["mandarin/settings.py"],
        ))

    return findings


ANALYZERS = [
    _analyze_genai_model_diversity,
    _analyze_genai_output_quality,
    _analyze_genai_streaming,
    _analyze_openclaw_maturity,
    _analyze_ml_model_health,
    _analyze_agentic_coverage,
    _analyze_ai_feedback_loops,
    _analyze_ai_marketing_readiness,
]
