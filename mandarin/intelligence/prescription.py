"""Product Intelligence — Prescription layer.

Each audit cycle produces exactly one work order: the next thing to do,
why, and what success looks like.

Architecture: identify_system_constraint() → generate_work_order()
→ subordinate everything else.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, UTC
from typing import Optional

from ._base import (
    _VERIFICATION_WINDOWS, _safe_query, _safe_query_all, _safe_scalar,
)

logger = logging.getLogger(__name__)


# ── WorkOrder dataclass ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class WorkOrder:
    id: int
    audit_cycle_id: int
    finding_id: int
    prediction_id: str | None
    constraint_dimension: str
    constraint_score: float
    marginal_improvement: float
    instruction: str
    target_file: str | None
    target_parameter: str | None
    direction: str | None
    success_metric: str
    success_baseline: float
    success_threshold: float
    verification_window_days: int
    subordinated_count: int
    subordinated_finding_ids: list
    confidence_label: str | None
    confidence_score: float | None
    instruction_source: str = "legacy_lookup"  # 'influence_model', 'legacy_lookup', 'insufficient_data'


class NoActionableFindings(Exception):
    """Raised when no findings are actionable."""
    pass


# ── Finding-to-action lookup ─────────────────────────────────────────────────
# (dimension, keyword_in_title) → (target_file, target_parameter, direction)
# Empty-string keyword = dimension-level fallback.

_FINDING_TO_ACTION = {
    # retention
    ("retention", "churn"): ("mandarin/scheduler.py", "RETENTION_THRESHOLD", "increase"),
    ("retention", "d1"): ("mandarin/web/session_routes.py", "first_session_flow", "improve"),
    ("retention", "d7"): ("mandarin/scheduler.py", "REVIEW_INTERVAL_SCALE", "decrease"),
    ("retention", ""): ("mandarin/scheduler.py", "retention_policy", "improve"),
    # ux
    ("ux", "completion"): ("mandarin/web/session_routes.py", "session_completion_rate", "increase"),
    ("ux", "rage"): ("mandarin/web/static/app.js", "event_handlers", "fix"),
    ("ux", "error"): ("mandarin/web/routes.py", "error_handling", "fix"),
    ("ux", ""): ("mandarin/web/routes.py", "ux_flow", "improve"),
    # drill_quality
    ("drill_quality", "accuracy"): ("mandarin/drills/dispatch.py", "drill_accuracy", "increase"),
    ("drill_quality", "scaffolding"): ("mandarin/drills/hints.py", "scaffolding_level", "increase"),
    ("drill_quality", ""): ("mandarin/drills/dispatch.py", "drill_design", "improve"),
    # srs_funnel
    ("srs_funnel", "stuck"): ("mandarin/scheduler.py", "STUCK_THRESHOLD", "decrease"),
    ("srs_funnel", "leech"): ("mandarin/scheduler.py", "LEECH_THRESHOLD", "decrease"),
    ("srs_funnel", ""): ("mandarin/scheduler.py", "srs_intervals", "tune"),
    # engineering
    ("engineering", "crash"): ("mandarin/web/routes.py", "crash_rate", "decrease"),
    ("engineering", "error"): ("mandarin/web/routes.py", "error_rate", "decrease"),
    ("engineering", "latency"): ("mandarin/web/routes.py", "response_time", "decrease"),
    ("engineering", ""): ("mandarin/web/routes.py", "stability", "improve"),
    # onboarding
    ("onboarding", "signup"): ("mandarin/web/onboarding_routes.py", "signup_conversion", "increase"),
    ("onboarding", "first session"): ("mandarin/web/onboarding_routes.py", "first_session_rate", "increase"),
    ("onboarding", ""): ("mandarin/web/onboarding_routes.py", "onboarding_flow", "improve"),
    # content
    ("content", "coverage"): ("mandarin/scheduler.py", "vocab_coverage", "increase"),
    ("content", "gap"): ("mandarin/web/gap_routes.py", "content_gaps", "fill"),
    ("content", ""): ("mandarin/scheduler.py", "content_library", "expand"),
    # frustration
    ("frustration", "rage"): ("mandarin/web/static/app.js", "click_handlers", "fix"),
    ("frustration", ""): ("mandarin/web/static/app.js", "ux_friction", "reduce"),
    # tone_phonology
    ("tone_phonology", "tone"): ("mandarin/tone_grading.py", "tone_accuracy", "increase"),
    ("tone_phonology", ""): ("mandarin/tone_grading.py", "phonology_model", "improve"),
    # scheduler_audit
    ("scheduler_audit", "interval"): ("mandarin/scheduler.py", "interval_algorithm", "tune"),
    ("scheduler_audit", ""): ("mandarin/scheduler.py", "scheduler_policy", "improve"),
    # engagement
    ("engagement", "active"): ("mandarin/scheduler.py", "engagement_triggers", "increase"),
    ("engagement", ""): ("mandarin/scheduler.py", "engagement_policy", "improve"),
    # security
    ("security", ""): ("mandarin/security.py", "security_policy", "harden"),
    # profitability
    ("profitability", "conversion"): ("mandarin/web/payment_routes.py", "conversion_rate", "increase"),
    ("profitability", ""): ("mandarin/web/payment_routes.py", "revenue_model", "improve"),
    # encounter_loop
    ("encounter_loop", ""): ("mandarin/scheduler.py", "encounter_cleanup", "improve"),
    # platform
    ("platform", "capacitor"): ("mobile/capacitor.config.ts", "cap_config", "fix"),
    ("platform", "flutter"): ("flutter_app/lib/api/api_client.dart", "flutter_parity", "improve"),
    ("platform", "tauri"): ("desktop/tauri-app/src-tauri/tauri.conf.json", "tauri_config", "fix"),
    ("platform", ""): ("mandarin/web/static/app.js", "cross_platform", "improve"),
    # genai
    ("genai", "model"): ("mandarin/ai/ollama_client.py", "model_selection", "improve"),
    ("genai", "streaming"): ("mandarin/ai/ollama_client.py", "streaming", "add"),
    ("genai", "quality"): ("mandarin/ai/genai_layer.py", "output_quality", "improve"),
    ("genai", "failure"): ("mandarin/ai/ollama_client.py", "error_handling", "fix"),
    ("genai", "latency"): ("mandarin/ai/ollama_client.py", "performance", "improve"),
    ("genai", ""): ("mandarin/ai/genai_layer.py", "genai_pipeline", "improve"),
    # agentic
    ("agentic", "memory"): ("mandarin/ai/memory.py", "conversation_memory", "add"),
    ("agentic", "notification"): ("mandarin/openclaw/__init__.py", "notifications", "add"),
    ("agentic", "coverage"): ("mandarin/ai/agentic.py", "action_types", "expand"),
    ("agentic", ""): ("mandarin/ai/agentic.py", "agentic_pipeline", "improve"),
    # flow
    ("flow", ""): ("mandarin/web/session_routes.py", "session_flow", "improve"),
    # curriculum
    ("curriculum", ""): ("mandarin/scheduler.py", "curriculum_coverage", "expand"),
    # hsk_cliff
    ("hsk_cliff", ""): ("mandarin/scheduler.py", "hsk_cliff_mitigation", "improve"),
    # cross_modality / error_taxonomy
    ("cross_modality", ""): ("mandarin/drills/dispatch.py", "modality_balance", "improve"),
    ("error_taxonomy", ""): ("mandarin/drills/dispatch.py", "error_classification", "improve"),
    # marketing / copy / pm / competitive / ui
    ("marketing", ""): ("mandarin/web/marketing_routes.py", "marketing_effectiveness", "improve"),
    ("copy", ""): ("mandarin/web/templates/index.html", "copy_quality", "improve"),
    ("pm", ""): ("mandarin/settings.py", "pm_process", "improve"),
    ("competitive", ""): ("mandarin/scheduler.py", "competitive_features", "improve"),
    ("ui", ""): ("mandarin/web/static/style.css", "ui_design", "improve"),
    # OR-system findings (analyzers_or.py)
    ("engineering", "spc"): ("mandarin/quality/spc.py", "spc_violation", "investigate"),
    ("engineering", "queue"): ("mandarin/settings.py", "new_item_ceiling", "reduce"),
    ("engineering", "monte carlo"): ("mandarin/settings.py", "capacity", "plan"),
    ("marketing", "viral"): ("mandarin/web/marketing_hooks.py", "referral_ux", "improve"),
    ("marketing", "price"): ("mandarin/settings.py", "pricing", "update"),
    ("retention", "ltv"): ("mandarin/web/session_routes.py", "retention_features", "improve"),
    # Strategy framework findings (analyzers_strategy.py)
    ("strategic", "horizon"): ("mandarin/scheduler.py", "block_allocation", "adjust"),
    ("competitive", "porter"): ("mandarin/intelligence/analyzers_business.py", "competitive_position", "improve"),
    ("competitive", "blue ocean"): ("mandarin/web/static/app.js", "differentiation", "improve"),
    ("profitability", "unit"): ("mandarin/analytics/clv.py", "unit_economics", "improve"),
    ("profitability", "cac"): ("mandarin/marketing_hooks.py", "acquisition_cost", "track"),
    # Behavioral economics (behavioral_econ dimension)
    ("behavioral_econ", "doctrine"): ("mandarin/web/static/app.js", "nudge_copy", "fix"),
    ("behavioral_econ", "nudge"): ("mandarin/nudge_registry.py", "nudge_coverage", "expand"),
    ("behavioral_econ", "progress"): ("mandarin/web/dashboard_routes.py", "progress_framing", "improve"),
    ("behavioral_econ", ""): ("mandarin/nudge_registry.py", "behavioral_econ", "improve"),
    # Growth accounting
    ("growth_accounting", "quick"): ("mandarin/payment.py", "revenue_health", "monitor"),
    ("growth_accounting", "waterfall"): ("mandarin/payment.py", "mrr_composition", "track"),
    ("growth_accounting", "cohort"): ("mandarin/analytics/clv.py", "cohort_retention", "improve"),
    ("growth_accounting", ""): ("mandarin/payment.py", "growth_accounting", "improve"),
    # Customer journey
    ("journey", "drop"): ("mandarin/web/onboarding_routes.py", "funnel_conversion", "improve"),
    ("journey", ""): ("mandarin/web/onboarding_routes.py", "customer_journey", "improve"),
    # Brand health
    ("brand_health", "nps"): ("mandarin/web/session_routes.py", "nps_collection", "add"),
    ("brand_health", ""): ("mandarin/marketing_hooks.py", "brand_health", "improve"),
    # Learning science — non-core modality coverage
    ("learning_science", "extensive"): ("mandarin/scheduler.py", "reading_coverage_threshold", "increase"),
    ("learning_science", "narrow"): ("mandarin/scheduler.py", "listening_topic_grouping", "add"),
    ("learning_science", "output"): ("mandarin/conversation.py", "production_difficulty", "increase"),
    ("learning_science", "form"): ("mandarin/scheduler.py", "grammar_context_gate", "add"),
    ("learning_science", "interleav"): ("mandarin/scheduler.py", "cross_modality_rotation", "increase"),
    ("learning_science", "difficult"): ("mandarin/scheduler.py", "listening_speed_progression", "add"),
    ("learning_science", "media"): ("mandarin/media.py", "media_content", "expand"),
    ("learning_science", ""): ("mandarin/scheduler.py", "learning_science_compliance", "improve"),
    # Modality-specific drill quality
    ("drill_quality", "reading"): ("mandarin/scheduler.py", "reading_difficulty", "calibrate"),
    ("drill_quality", "listening"): ("mandarin/scheduler.py", "listening_difficulty", "calibrate"),
    ("drill_quality", "conversation"): ("mandarin/conversation.py", "conversation_quality", "improve"),
    ("drill_quality", "grammar"): ("mandarin/scheduler.py", "grammar_integration", "improve"),
    ("drill_quality", "spc"): ("mandarin/quality/spc.py", "modality_spc", "investigate"),
    # Behavioral economics per modality
    ("behavioral_econ", "reading"): ("mandarin/web/dashboard_routes.py", "reading_milestones", "add"),
    ("behavioral_econ", "listening"): ("mandarin/scheduler.py", "playback_speed_choice", "add"),
    ("behavioral_econ", "conversation"): ("mandarin/conversation.py", "encouragement_messages", "add"),
    ("behavioral_econ", "grammar"): ("mandarin/scheduler.py", "grammar_encounter_gate", "improve"),
    ("behavioral_econ", "modality"): ("mandarin/nudge_registry.py", "modality_nudge", "add"),
    ("behavioral_econ", "exploration"): ("mandarin/nudge_registry.py", "modality_nudge", "add"),
    # Modality-specific engagement/retention
    ("engagement", "reading"): ("mandarin/scheduler.py", "reading_scheduling", "increase"),
    ("engagement", "listening"): ("mandarin/scheduler.py", "listening_scheduling", "increase"),
    ("engagement", "modality"): ("mandarin/scheduler.py", "modality_balance", "improve"),
    ("retention", "modality"): ("mandarin/scheduler.py", "modality_onboarding", "improve"),
    ("retention", "mono"): ("mandarin/nudge_registry.py", "exploration_nudge", "add"),
    # output_production
    ("output_production", "speaking"): ("mandarin/drills/production.py", "speaking_output", "improve"),
    ("output_production", "writing"): ("mandarin/drills/production.py", "writing_output", "improve"),
    ("output_production", ""): ("mandarin/drills/production.py", "production_quality", "improve"),
    # tutor_integration
    ("tutor_integration", "grammar"): ("mandarin/ai/grammar_tutor.py", "grammar_feedback", "improve"),
    ("tutor_integration", "explanation"): ("mandarin/ai/grammar_tutor.py", "explanation_quality", "improve"),
    ("tutor_integration", ""): ("mandarin/ai/grammar_tutor.py", "tutor_pipeline", "improve"),
    # tone_quality
    ("tone_quality", "sandhi"): ("mandarin/ai/tone_sandhi.py", "sandhi_rules", "fix"),
    ("tone_quality", "accuracy"): ("mandarin/ai/tone_sandhi.py", "tone_accuracy", "improve"),
    ("tone_quality", ""): ("mandarin/ai/tone_sandhi.py", "tone_quality", "improve"),
    # feature_usage
    ("feature_usage", "adoption"): ("mandarin/web/routes.py", "feature_adoption", "increase"),
    ("feature_usage", "discovery"): ("mandarin/web/routes.py", "feature_discovery", "improve"),
    ("feature_usage", ""): ("mandarin/web/routes.py", "feature_usage", "track"),
    # engineering_health
    ("engineering_health", "test"): ("mandarin/web/quality_scheduler.py", "test_coverage", "increase"),
    ("engineering_health", "debt"): ("mandarin/web/quality_scheduler.py", "tech_debt", "reduce"),
    ("engineering_health", ""): ("mandarin/web/quality_scheduler.py", "engineering_health", "improve"),
    # data_quality
    ("data_quality", "integrity"): ("mandarin/db/core.py", "data_integrity", "fix"),
    ("data_quality", "orphan"): ("mandarin/db/core.py", "orphan_records", "clean"),
    ("data_quality", ""): ("mandarin/db/core.py", "data_quality", "improve"),
    # genai_governance
    ("genai_governance", "policy"): ("mandarin/ai/ollama_client.py", "governance_policy", "enforce"),
    ("genai_governance", "safety"): ("mandarin/ai/ollama_client.py", "safety_filter", "tighten"),
    ("genai_governance", ""): ("mandarin/ai/ollama_client.py", "genai_governance", "improve"),
    # memory_model
    ("memory_model", "decay"): ("mandarin/ai/memory.py", "memory_decay", "tune"),
    ("memory_model", "context"): ("mandarin/ai/memory.py", "context_window", "expand"),
    ("memory_model", ""): ("mandarin/ai/memory.py", "memory_model", "improve"),
    # learner_model
    ("learner_model", "proficiency"): ("mandarin/ai/learner_model.py", "proficiency_estimation", "improve"),
    ("learner_model", "calibration"): ("mandarin/ai/learner_model.py", "model_calibration", "tune"),
    ("learner_model", ""): ("mandarin/ai/learner_model.py", "learner_model", "improve"),
    # rag
    ("rag", "retrieval"): ("mandarin/ai/rag_layer.py", "retrieval_quality", "improve"),
    ("rag", "embedding"): ("mandarin/ai/rag_layer.py", "embedding_quality", "improve"),
    ("rag", ""): ("mandarin/ai/rag_layer.py", "rag_pipeline", "improve"),
    # native_speaker_validation
    ("native_speaker_validation", "coverage"): ("mandarin/ai/native_speaker_validation.py", "validation_coverage", "increase"),
    ("native_speaker_validation", "accuracy"): ("mandarin/ai/native_speaker_validation.py", "validation_accuracy", "improve"),
    ("native_speaker_validation", ""): ("mandarin/ai/native_speaker_validation.py", "native_validation", "improve"),
    # input_layer
    ("input_layer", "recognition"): ("mandarin/drills/base.py", "input_recognition", "improve"),
    ("input_layer", "feedback"): ("mandarin/drills/base.py", "input_feedback", "improve"),
    ("input_layer", ""): ("mandarin/drills/base.py", "input_layer", "improve"),
    # accountability
    ("accountability", "audit"): ("mandarin/ai/accountability.py", "audit_trail", "improve"),
    ("accountability", "transparency"): ("mandarin/ai/accountability.py", "decision_transparency", "improve"),
    ("accountability", ""): ("mandarin/ai/accountability.py", "accountability", "improve"),
    # commercial
    ("commercial", "pricing"): ("mandarin/payment.py", "pricing_model", "optimize"),
    ("commercial", "subscription"): ("mandarin/payment.py", "subscription_flow", "improve"),
    ("commercial", ""): ("mandarin/payment.py", "commercial_model", "improve"),
    # timing
    ("timing", "schedule"): ("mandarin/scheduler.py", "session_timing", "optimize"),
    ("timing", "notification"): ("mandarin/scheduler.py", "notification_timing", "tune"),
    ("timing", ""): ("mandarin/scheduler.py", "timing_policy", "improve"),
    # governance
    ("governance", "compliance"): ("mandarin/intelligence/governance.py", "compliance_check", "enforce"),
    ("governance", "policy"): ("mandarin/intelligence/governance.py", "governance_policy", "update"),
    ("governance", ""): ("mandarin/intelligence/governance.py", "governance", "improve"),
    # tonal_vibe
    ("tonal_vibe", "warmth"): ("mandarin/web/static/style.css", "color_warmth", "increase"),
    ("tonal_vibe", "serif"): ("mandarin/web/static/style.css", "typography", "improve"),
    ("tonal_vibe", ""): ("mandarin/web/static/style.css", "tonal_vibe", "improve"),
    # strategic (fallback)
    ("strategic", ""): ("mandarin/intelligence/prescription.py", "strategic_priority", "reassess"),
    # copy_drift
    ("copy_drift", "price"): ("marketing/landing/index.html", "pricing_copy", "fix"),
    ("copy_drift", "feature"): ("marketing/landing/index.html", "feature_claims", "fix"),
    ("copy_drift", ""): ("marketing/landing/index.html", "copy_accuracy", "fix"),
}

# Error-type dimensions where improvement means metric goes DOWN
_ERROR_DIMENSIONS = {
    "engineering", "frustration", "security",
}


def _get_current_constraint(conn) -> dict:
    """Query latest product audit dimension scores and identify system constraint."""
    from ._synthesis import identify_system_constraint

    row = _safe_query(conn, """
        SELECT dimension_scores FROM product_audit
        ORDER BY run_at DESC LIMIT 1
    """)
    if not row or not row["dimension_scores"]:
        return {"constraint": None}

    try:
        dimension_scores = json.loads(row["dimension_scores"])
    except (json.JSONDecodeError, TypeError):
        return {"constraint": None}

    return identify_system_constraint(conn, dimension_scores)


def _select_candidate_finding(conn, constraint: dict):
    """Select the best actionable finding for the constraint dimension.

    Priority: severity → model confidence → times seen.
    Falls back to any dimension if no constraint-dim finding exists.
    """
    constraint_dim = constraint.get("constraint")

    def _query_findings(dimension_filter=None):
        if dimension_filter:
            return _safe_query(conn, """
                SELECT pf.*, COALESCE(mc.current_confidence, 0.5) as model_confidence
                FROM pi_finding pf
                LEFT JOIN pi_model_confidence mc ON mc.model_id = pf.dimension
                WHERE pf.dimension = ?
                  AND pf.status NOT IN ('resolved', 'rejected', 'implemented', 'verified')
                ORDER BY
                    CASE pf.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                         WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END,
                    COALESCE(mc.current_confidence, 0.5) DESC,
                    pf.times_seen DESC
                LIMIT 1
            """, (dimension_filter,))
        else:
            return _safe_query(conn, """
                SELECT pf.*, COALESCE(mc.current_confidence, 0.5) as model_confidence
                FROM pi_finding pf
                LEFT JOIN pi_model_confidence mc ON mc.model_id = pf.dimension
                WHERE pf.status NOT IN ('resolved', 'rejected', 'implemented', 'verified')
                ORDER BY
                    CASE pf.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                         WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END,
                    COALESCE(mc.current_confidence, 0.5) DESC,
                    pf.times_seen DESC
                LIMIT 1
            """)

    # Try constraint dimension first
    if constraint_dim:
        candidate = _query_findings(constraint_dim)
        if candidate:
            return candidate

    # Fallback: any dimension
    candidate = _query_findings()
    if candidate:
        return candidate

    raise NoActionableFindings("No actionable findings in any dimension")


def _build_instruction(conn, candidate) -> tuple:
    """Build imperative instruction text using influence model with legacy fallback.

    Tries the influence model first. If confidence >= 0.40, uses its recommendation.
    Otherwise falls back to _FINDING_TO_ACTION lookup table.
    Logs which source was used.

    Returns (instruction, target_file, target_parameter, direction, instruction_source).
    """
    dimension = candidate["dimension"]
    title = candidate["title"] or ""
    instruction_source = "legacy_lookup"

    # ── Try influence model first ──
    try:
        from .change_generator import generate_specific_change
        finding_dict = {
            "dimension": dimension,
            "title": title,
            "severity": candidate["severity"],
            "id": candidate["id"],
        }
        change = generate_specific_change(conn, finding_dict)

        if change and change.influence_confidence >= 0.40:
            # Pull advisor recommendation for richer instruction
            advisor_text = _get_advisor_text(conn, candidate["id"])

            instruction = (
                f"{change.specific_change} "
                f"Severity: {candidate['severity']}.{advisor_text}"
            )
            return (
                instruction,
                change.file_path,
                change.parameter_name,
                change.direction,
                "influence_model",
            )
    except (ImportError, Exception) as e:
        logger.debug("Influence model unavailable, falling back to legacy: %s", e)

    # ── Try prescription_memory (learned from past outcomes) ──
    try:
        from .prescription_memory import suggest_prescription
        memory_suggestions = suggest_prescription(conn, context={
            "dimension": dimension,
            "severity": candidate["severity"],
            "metric_name": candidate.get("metric_name", dimension),
        })
        if memory_suggestions:
            best = memory_suggestions[0]
            if best.get("success_rate", 0) > 0.5:
                instruction_source = "prescription_memory"
                target_file = best.get("target_file")
                target_parameter = best.get("target_parameter")
                direction = best.get("direction")
                if target_file:
                    advisor_text = _get_advisor_text(conn, candidate["id"])
                    instruction = (
                        f"In {target_file}, {direction} {target_parameter}. "
                        f"Finding: {title}. "
                        f"Severity: {candidate['severity']}. "
                        f"(Learned: {best['success_rate']:.0%} success rate "
                        f"over {best.get('sample_size', 0)} prior actions){advisor_text}"
                    )
                    return instruction, target_file, target_parameter, direction, instruction_source
    except (ImportError, Exception) as e:
        logger.debug("Prescription memory unavailable: %s", e)

    # ── Legacy fallback: _FINDING_TO_ACTION ──
    target_file = None
    target_parameter = None
    direction = None

    for (dim, keyword), (f, p, d) in _FINDING_TO_ACTION.items():
        if dim != dimension:
            continue
        if keyword and keyword.lower() in title.lower():
            target_file, target_parameter, direction = f, p, d
            break

    # Dimension-level fallback
    if target_file is None:
        fallback = _FINDING_TO_ACTION.get((dimension, ""))
        if fallback:
            target_file, target_parameter, direction = fallback

    # Pull advisor recommendation for richer instruction
    advisor_text = _get_advisor_text(conn, candidate["id"])

    # Build instruction
    if target_file:
        instruction = (
            f"In {target_file}, {direction} {target_parameter}. "
            f"Finding: {title}. "
            f"Severity: {candidate['severity']}.{advisor_text}"
        )
    else:
        # Both systems failed — honest fallback
        instruction_source = "insufficient_data"
        instruction = (
            f"Address [{dimension}] finding: {title}. "
            f"Severity: {candidate['severity']}. "
            f"No specific file target identified — investigate dimension.{advisor_text}"
        )

    return instruction, target_file, target_parameter, direction, instruction_source


def _get_advisor_text(conn, finding_id: int) -> str:
    """Pull top advisor recommendation text for a finding."""
    advisor_rec = _safe_query(conn, """
        SELECT recommendation FROM pi_advisor_opinion
        WHERE finding_id = ?
        ORDER BY priority_score DESC
        LIMIT 1
    """, (finding_id,))

    if advisor_rec and advisor_rec["recommendation"]:
        return f" Advisor recommendation: {advisor_rec['recommendation']}"
    return ""


def _compute_subordination(conn, candidate, constraint: dict) -> tuple:
    """Count open findings NOT in constraint dimension with severity >= medium.

    Returns (count, json_id_list).
    """
    constraint_dim = constraint.get("constraint") or candidate["dimension"]

    rows = _safe_query_all(conn, """
        SELECT id FROM pi_finding
        WHERE dimension != ?
          AND status NOT IN ('resolved', 'rejected', 'implemented', 'verified')
          AND severity IN ('critical', 'high', 'medium')
    """, (constraint_dim,))

    ids = [r["id"] for r in (rows or [])]
    return len(ids), json.dumps(ids)


def _build_success_condition(conn, candidate) -> tuple:
    """Determine success metric, baseline, threshold, and verification window.

    Returns (metric_name, baseline, threshold, window_days).
    """
    from .feedback_loops import _measure_current_metric

    dimension = candidate["dimension"]
    metric_name = dimension  # metric_name == dimension in _measure_current_metric

    baseline = _measure_current_metric(conn, dimension, metric_name)
    if baseline is None:
        baseline = 0.0

    window_days = _VERIFICATION_WINDOWS.get(dimension, 14)

    # Predicted improvement: use model confidence as a scaling factor
    model_confidence = candidate["model_confidence"] if "model_confidence" in candidate.keys() else 0.5
    predicted_improvement = 5.0 * model_confidence  # scale: 0-5 points

    # For error-type dimensions, success means metric goes DOWN
    if dimension in _ERROR_DIMENSIONS:
        threshold = baseline - predicted_improvement * 0.5
    else:
        threshold = baseline + predicted_improvement * 0.5

    return metric_name, round(baseline, 4), round(threshold, 4), window_days


def generate_work_order(conn, audit_cycle_id: int) -> WorkOrder:
    """Orchestrator: produce exactly one work order per audit cycle.

    1. Get constraint
    2. Select candidate finding
    3. Build instruction
    4. Compute subordination
    5. Build success condition
    6. Emit prediction
    7. Persist to pi_work_order
    8. Supersede previous pending work orders
    9. Return frozen WorkOrder
    """
    from .feedback_loops import emit_prediction

    # 1. Constraint
    constraint = _get_current_constraint(conn)

    # 2. Candidate
    candidate = _select_candidate_finding(conn, constraint)

    # 3. Instruction
    instruction, target_file, target_param, direction, instruction_source = _build_instruction(conn, candidate)

    # 4. Subordination
    sub_count, sub_ids = _compute_subordination(conn, candidate, constraint)

    # 5. Success condition
    metric_name, baseline, threshold, window_days = _build_success_condition(conn, candidate)

    # 6. Emit prediction (required before finding can move to 'implemented')
    dimension = candidate["dimension"]
    model_confidence = candidate["model_confidence"] if "model_confidence" in candidate.keys() else 0.5

    if dimension in _ERROR_DIMENSIONS:
        predicted_delta = -(threshold - baseline)  # negative = improving for error dims
    else:
        predicted_delta = threshold - baseline

    prediction_id = emit_prediction(
        conn,
        finding_id=candidate["id"],
        model_id=dimension,
        dimension=dimension,
        metric_name=metric_name,
        predicted_delta=predicted_delta,
        confidence=model_confidence,
    )

    # Confidence label
    if model_confidence >= 0.7:
        confidence_label = "high"
    elif model_confidence >= 0.4:
        confidence_label = "medium"
    else:
        confidence_label = "low"

    constraint_score = constraint.get("constraint_score", 0.0)
    marginal_improvement = constraint.get("marginal_improvement", 0.0)

    now = datetime.now(UTC)
    due_at = (now + timedelta(days=window_days)).strftime("%Y-%m-%d %H:%M:%S")

    # 7. Persist
    try:
        cursor = conn.execute("""
            INSERT INTO pi_work_order
                (audit_cycle_id, finding_id, prediction_id,
                 constraint_dimension, constraint_score, marginal_improvement,
                 instruction, target_file, target_parameter, direction,
                 success_metric, success_baseline, success_threshold,
                 verification_window_days, verification_due_at,
                 subordinated_count, subordinated_finding_ids,
                 confidence_label, confidence_score, instruction_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit_cycle_id, candidate["id"], prediction_id,
            dimension, constraint_score, marginal_improvement,
            instruction, target_file, target_param, direction,
            metric_name, baseline, threshold,
            window_days, due_at,
            sub_count, sub_ids,
            confidence_label, model_confidence, instruction_source,
        ))
        conn.commit()
        work_order_id = cursor.lastrowid
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to persist work order: %s", e)
        raise

    # 8. Supersede previous pending work orders
    try:
        conn.execute("""
            UPDATE pi_work_order
            SET status = 'superseded'
            WHERE status = 'pending' AND id != ?
        """, (work_order_id,))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error):
        pass  # non-fatal

    # 9. Return
    return WorkOrder(
        id=work_order_id,
        audit_cycle_id=audit_cycle_id,
        finding_id=candidate["id"],
        prediction_id=prediction_id,
        constraint_dimension=dimension,
        constraint_score=constraint_score,
        marginal_improvement=marginal_improvement,
        instruction=instruction,
        target_file=target_file,
        target_parameter=target_param,
        direction=direction,
        success_metric=metric_name,
        success_baseline=baseline,
        success_threshold=threshold,
        verification_window_days=window_days,
        subordinated_count=sub_count,
        subordinated_finding_ids=json.loads(sub_ids),
        confidence_label=confidence_label,
        confidence_score=model_confidence,
        instruction_source=instruction_source,
    )


def mark_work_order_implemented(conn, work_order_id: int, parameter_name=None,
                                 old_value=None, new_value=None, notes=None) -> bool:
    """Mark a work order as verifying and advance the finding lifecycle.

    If the finding is in investigating/diagnosed, auto-advances through
    intermediate states to 'recommended' then to 'implemented'.
    The prediction record already exists from generate_work_order.
    """
    from .finding_lifecycle import transition_finding

    wo = _safe_query(conn, """
        SELECT id, finding_id, status FROM pi_work_order WHERE id = ?
    """, (work_order_id,))
    if not wo or wo["status"] not in ("pending",):
        return False

    finding_id = wo["finding_id"]

    # Get current finding status
    finding = _safe_query(conn, "SELECT status FROM pi_finding WHERE id = ?", (finding_id,))
    if not finding:
        return False

    current_status = finding["status"]

    # Auto-advance finding through lifecycle to 'implemented'
    # investigating → diagnosed → recommended → implemented
    _ADVANCE_PATH = {
        "investigating": ["diagnosed", "recommended", "implemented"],
        "diagnosed": ["recommended", "implemented"],
        "recommended": ["implemented"],
    }

    steps = _ADVANCE_PATH.get(current_status, [])
    for step in steps:
        ok = transition_finding(conn, finding_id, step)
        if not ok:
            logger.warning(
                "Failed to advance finding %d to %s during work order implementation",
                finding_id, step,
            )
            return False

    # Record parameter change if provided
    if parameter_name is not None:
        try:
            from .parameter_registry import record_parameter_change
            record_parameter_change(
                conn, parameter_name, old_value, new_value,
                changed_by="human", work_order_id=work_order_id,
            )
        except (ImportError, Exception) as e:
            logger.warning("Failed to record parameter change: %s", e)
    elif notes:
        # Structural change — log to parameter history without edge update
        try:
            from .parameter_registry import _safe_query as _pq
            from uuid import uuid4 as _uuid4
            conn.execute("""
                INSERT INTO pi_parameter_history
                    (id, parameter_id, changed_at, changed_by, work_order_id)
                VALUES (?, 'structural_change', ?, 'human', ?)
            """, (str(_uuid4()), datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                  work_order_id))
            conn.commit()
        except Exception:
            pass  # non-fatal

    # Mark work order as verifying
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            UPDATE pi_work_order
            SET status = 'verifying', implemented_at = ?
            WHERE id = ?
        """, (now, work_order_id))
        conn.commit()
        return True
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to mark work order implemented: %s", e)
        return False


def check_stale_work_orders(conn) -> list:
    """Find pending work orders older than 2× verification_window_days, mark as stale."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    stale = []
    try:
        rows = conn.execute("""
            SELECT id, verification_window_days, created_at
            FROM pi_work_order
            WHERE status = 'pending'
        """).fetchall()

        for row in rows:
            created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
            stale_after = created + timedelta(days=row["verification_window_days"] * 2)
            if datetime.strptime(now, "%Y-%m-%d %H:%M:%S") >= stale_after:
                conn.execute(
                    "UPDATE pi_work_order SET status = 'stale' WHERE id = ?",
                    (row["id"],)
                )
                stale.append(row["id"])

        if stale:
            conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.warning("Stale work order check failed: %s", e)

    return stale


def get_current_work_order(conn):
    """Return the most recent non-terminal work order with finding details, or None."""
    row = _safe_query(conn, """
        SELECT wo.*, pf.title as finding_title, pf.dimension as finding_dimension,
               pf.severity as finding_severity, pf.status as finding_status
        FROM pi_work_order wo
        JOIN pi_finding pf ON wo.finding_id = pf.id
        WHERE wo.status NOT IN ('succeeded', 'failed', 'stale', 'superseded')
        ORDER BY wo.created_at DESC
        LIMIT 1
    """)
    if not row:
        return None

    return {
        "id": row["id"],
        "audit_cycle_id": row["audit_cycle_id"],
        "finding_id": row["finding_id"],
        "prediction_id": row["prediction_id"],
        "constraint_dimension": row["constraint_dimension"],
        "constraint_score": row["constraint_score"],
        "marginal_improvement": row["marginal_improvement"],
        "instruction": row["instruction"],
        "target_file": row["target_file"],
        "target_parameter": row["target_parameter"],
        "direction": row["direction"],
        "success_metric": row["success_metric"],
        "success_baseline": row["success_baseline"],
        "success_threshold": row["success_threshold"],
        "verification_window_days": row["verification_window_days"],
        "verification_due_at": row["verification_due_at"],
        "subordinated_count": row["subordinated_count"],
        "subordinated_finding_ids": row["subordinated_finding_ids"],
        "status": row["status"],
        "implemented_at": row["implemented_at"],
        "verified_at": row["verified_at"],
        "confidence_label": row["confidence_label"],
        "confidence_score": row["confidence_score"],
        "instruction_source": row["instruction_source"] if "instruction_source" in row.keys() else "legacy_lookup",
        "finding_title": row["finding_title"],
        "finding_dimension": row["finding_dimension"],
        "finding_severity": row["finding_severity"],
        "finding_status": row["finding_status"],
    }


def get_active_work_orders(conn) -> list:
    """Return ALL non-terminal work orders with finding details."""
    rows = _safe_query_all(conn, """
        SELECT wo.*, pf.title as finding_title, pf.dimension as finding_dimension,
               pf.severity as finding_severity, pf.status as finding_status
        FROM pi_work_order wo
        JOIN pi_finding pf ON wo.finding_id = pf.id
        WHERE wo.status NOT IN ('succeeded', 'failed', 'stale', 'superseded')
        ORDER BY wo.created_at DESC
    """)
    if not rows:
        return []

    result = []
    for row in rows:
        wo = {
            "id": row["id"],
            "audit_cycle_id": row["audit_cycle_id"],
            "finding_id": row["finding_id"],
            "constraint_dimension": row["constraint_dimension"],
            "instruction": row["instruction"],
            "target_file": row["target_file"],
            "status": row["status"],
            "finding_title": row["finding_title"],
            "finding_dimension": row["finding_dimension"],
            "finding_severity": row["finding_severity"],
        }
        # Include slot and platform_status if available
        try:
            wo["slot"] = row["slot"]
        except (IndexError, KeyError):
            pass
        try:
            wo["platform_status"] = row["platform_status"]
        except (IndexError, KeyError):
            pass
        result.append(wo)
    return result


def get_work_order_history(conn, limit: int = 20) -> list:
    """Return recent work orders with outcome details."""
    rows = _safe_query_all(conn, """
        SELECT wo.*, pf.title as finding_title, pf.dimension as finding_dimension,
               pf.severity as finding_severity
        FROM pi_work_order wo
        JOIN pi_finding pf ON wo.finding_id = pf.id
        ORDER BY wo.created_at DESC
        LIMIT ?
    """, (limit,))

    return [
        {
            "id": r["id"],
            "audit_cycle_id": r["audit_cycle_id"],
            "finding_id": r["finding_id"],
            "constraint_dimension": r["constraint_dimension"],
            "instruction": r["instruction"],
            "status": r["status"],
            "created_at": r["created_at"],
            "implemented_at": r["implemented_at"],
            "verified_at": r["verified_at"],
            "success_metric": r["success_metric"],
            "success_baseline": r["success_baseline"],
            "success_threshold": r["success_threshold"],
            "outcome_notes": r["outcome_notes"],
            "confidence_label": r["confidence_label"],
            "instruction_source": r["instruction_source"] if "instruction_source" in r.keys() else "legacy_lookup",
            "finding_title": r["finding_title"],
            "finding_dimension": r["finding_dimension"],
            "finding_severity": r["finding_severity"],
        }
        for r in (rows or [])
    ]


def _check_subordination(conn, finding_id: int):
    """Check if a finding is held by an active work order's subordination list.

    Returns a warning dict if subordinated, None otherwise.
    """
    # Get active (pending/verifying) work orders
    wo = _safe_query(conn, """
        SELECT id, constraint_dimension, subordinated_finding_ids, instruction
        FROM pi_work_order
        WHERE status IN ('pending', 'verifying')
        ORDER BY created_at DESC
        LIMIT 1
    """)
    if not wo or not wo["subordinated_finding_ids"]:
        return None

    try:
        sub_ids = json.loads(wo["subordinated_finding_ids"])
    except (json.JSONDecodeError, TypeError):
        return None

    if finding_id in sub_ids:
        return {
            "subordination_warning": True,
            "active_work_order_id": wo["id"],
            "constraint_dimension": wo["constraint_dimension"],
            "message": (
                f"This finding is subordinated to the system constraint "
                f"({wo['constraint_dimension']}). Current work order: "
                f"{wo['instruction'][:100]}..."
            ),
        }

    return None
