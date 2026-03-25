"""Product Intelligence Engine — comprehensive self-diagnosing product audit.

Analyzes the product across multiple dimensions and generates prioritized,
actionable Claude Code prompts telling the developer what needs to change.

Each finding includes:
- dimension, severity, title, analysis, recommendation
- claude_prompt (ready to paste into Claude Code)
- impact (qualitative), files (list of files to modify)

V4: Nonlinear scoring, data confidence, domain analyzers, finding lifecycle,
feedback loops, multi-agent advisors, human-in-the-loop. Zero Claude tokens.
"""

import logging

from ._base import (
    _SEVERITY_ORDER, _count_by, _dimension_score, _overall_score,
)
from ._synthesis import (
    _assess_data_confidence, _compute_trends, _save_audit, _synthesize,
)
from .analyzers_business import ANALYZERS as BUSINESS_ANALYZERS
from .analyzers_product import ANALYZERS as PRODUCT_ANALYZERS
from .analyzers_engineering import ANALYZERS as ENGINEERING_ANALYZERS

logger = logging.getLogger(__name__)

# Standard dimensions (original 18)
_STANDARD_DIMS = [
    "profitability", "retention", "ux", "ui", "engineering", "security",
    "pm", "marketing", "onboarding", "competitive",
    "flow", "drill_quality", "timing", "platform", "engagement",
    "content", "frustration", "copy",
]

# Domain-specific dimensions (Phase 2)
_DOMAIN_DIMS = [
    "srs_funnel", "error_taxonomy", "cross_modality", "curriculum",
    "hsk_cliff", "tone_phonology", "scheduler_audit", "encounter_loop",
]

# System/process dimensions (always shown even when findings are suppressed)
_SYSTEM_PROCESS_DIMS = [
    "methodology", "strategic", "genai_governance",
]


def run_product_audit(conn) -> dict:
    """Run comprehensive product audit across all dimensions.

    Returns a dict with keys:
        findings, dimension_scores, overall, trends, synthesis, data_confidence,
        finding_lifecycle, feedback_summary, advisor_opinions, sprint_plan,
        decision_queue
    """
    findings = []

    # Collect all analyzers
    all_analyzers = BUSINESS_ANALYZERS + PRODUCT_ANALYZERS + ENGINEERING_ANALYZERS

    # Import domain analyzers (Phase 2)
    try:
        from .analyzers_domain import ANALYZERS as DOMAIN_ANALYZERS
        all_analyzers = all_analyzers + DOMAIN_ANALYZERS
    except ImportError:
        DOMAIN_ANALYZERS = []

    # Import product experience analyzers (Phase 7)
    try:
        from .product_experience import ANALYZERS as PE_ANALYZERS
        all_analyzers = all_analyzers + PE_ANALYZERS
    except ImportError:
        pass

    # Import methodology coverage analyzers (Phase 8)
    try:
        from .methodology_coverage import ANALYZERS as MC_ANALYZERS
        all_analyzers = all_analyzers + MC_ANALYZERS
    except ImportError:
        pass

    # Import AI health analyzers (local LLM monitoring)
    try:
        from ..ai.health import ANALYZERS as AI_HEALTH_ANALYZERS
        all_analyzers = all_analyzers + AI_HEALTH_ANALYZERS
    except ImportError:
        pass

    # Import ML health analyzers (difficulty model + fuzzy dedup)
    try:
        from ..ml.health import ANALYZERS as ML_HEALTH_ANALYZERS
        all_analyzers = all_analyzers + ML_HEALTH_ANALYZERS
    except ImportError:
        pass

    # Import runtime health analyzers (error spikes, slow endpoints, webhooks, DB health)
    try:
        from .analyzers_runtime import ANALYZERS as RUNTIME_ANALYZERS
        all_analyzers = all_analyzers + RUNTIME_ANALYZERS
    except ImportError:
        pass

    # Import AI outcome measurement analyzers
    try:
        from .ai_outcome import ANALYZERS as AI_OUTCOME_ANALYZERS
        all_analyzers = all_analyzers + AI_OUTCOME_ANALYZERS
    except ImportError:
        pass

    # Import coverage audit analyzers (Doc 6)
    try:
        from .coverage_audit import ANALYZERS as COVERAGE_ANALYZERS
        all_analyzers = all_analyzers + COVERAGE_ANALYZERS
    except ImportError:
        pass

    # Import engagement analyzers (Doc 7)
    try:
        from .engagement import ANALYZERS as ENGAGEMENT_ANALYZERS
        all_analyzers = all_analyzers + ENGAGEMENT_ANALYZERS
    except ImportError:
        pass

    # Import cohort analysis analyzers (Doc 7)
    try:
        from .cohort_analysis import ANALYZERS as COHORT_ANALYZERS
        all_analyzers = all_analyzers + COHORT_ANALYZERS
    except ImportError:
        pass

    # Import output/tone/tutor analyzers (Doc 8)
    try:
        from .output_tone_tutor import ANALYZERS as OUTPUT_TONE_TUTOR_ANALYZERS
        all_analyzers = all_analyzers + OUTPUT_TONE_TUTOR_ANALYZERS
    except ImportError:
        pass

    # Import vibe/marketing/feature/engineering analyzers (Doc 9)
    try:
        from .vibe_marketing_eng import ANALYZERS as VME_ANALYZERS
        all_analyzers = all_analyzers + VME_ANALYZERS
    except ImportError:
        pass

    # Import strategic intelligence analyzers (Doc 10)
    try:
        from .strategic_intelligence import ANALYZERS as STRATEGIC_ANALYZERS
        all_analyzers = all_analyzers + STRATEGIC_ANALYZERS
    except ImportError:
        pass

    # Import governance analyzers (Doc 11) — runs first conceptually
    try:
        from .governance import ANALYZERS as GOVERNANCE_ANALYZERS
        all_analyzers = all_analyzers + GOVERNANCE_ANALYZERS
    except ImportError:
        pass

    # Import GenAI governance analyzers (Doc 12)
    try:
        from .genai_audit import ANALYZERS as GENAI_ANALYZERS
        all_analyzers = all_analyzers + GENAI_ANALYZERS
    except ImportError:
        pass

    # Import memory model analyzers (Doc 13)
    try:
        from .memory_audit import ANALYZERS as MEMORY_ANALYZERS
        all_analyzers = all_analyzers + MEMORY_ANALYZERS
    except ImportError:
        pass

    # Import learner model analyzers (Doc 16)
    try:
        from .learner_audit import ANALYZERS as LEARNER_ANALYZERS
        all_analyzers = all_analyzers + LEARNER_ANALYZERS
    except ImportError:
        pass

    # Import RAG/GenAI hardening analyzers (Doc 21)
    try:
        from .rag_audit import ANALYZERS as RAG_ANALYZERS
        all_analyzers = all_analyzers + RAG_ANALYZERS
    except ImportError:
        pass

    # Import native speaker validation analyzers (Doc 22)
    try:
        from .nsv_audit import ANALYZERS as NSV_ANALYZERS
        all_analyzers = all_analyzers + NSV_ANALYZERS
    except ImportError:
        pass

    # Import curriculum coverage analyzers (Doc 14)
    try:
        from .curriculum_audit import ANALYZERS as CURRICULUM_ANALYZERS
        all_analyzers = all_analyzers + CURRICULUM_ANALYZERS
    except ImportError:
        pass

    # Import input acquisition layer analyzers (Doc 15)
    try:
        from .input_audit import ANALYZERS as INPUT_ANALYZERS
        all_analyzers = all_analyzers + INPUT_ANALYZERS
    except ImportError:
        pass

    # Import accountability analyzers (Doc 18)
    try:
        from .accountability_audit import ANALYZERS as ACCOUNTABILITY_ANALYZERS
        all_analyzers = all_analyzers + ACCOUNTABILITY_ANALYZERS
    except ImportError:
        pass

    # Import commercial intelligence analyzers (Doc 19)
    try:
        from .commercial_audit import ANALYZERS as COMMERCIAL_ANALYZERS
        all_analyzers = all_analyzers + COMMERCIAL_ANALYZERS
    except ImportError:
        pass

    # Import agentic technology layer analyzers (Doc 23)
    try:
        from .agentic_audit import ANALYZERS as AGENTIC_ANALYZERS
        all_analyzers = all_analyzers + AGENTIC_ANALYZERS
    except ImportError:
        pass

    # Import prompt observability analyzers (Doc 23 C-02)
    try:
        from ..ai.prompt_observability import analyze_prompt_health
        all_analyzers = all_analyzers + [analyze_prompt_health]
    except ImportError:
        pass

    # Import discipline analyzers (visual design, animation, sound, copy, etc.)
    try:
        from .analyzers_discipline import ANALYZERS as DISCIPLINE_ANALYZERS
        all_analyzers = all_analyzers + DISCIPLINE_ANALYZERS
    except ImportError:
        pass

    # Import cross-platform analyzers (Phase 5)
    try:
        from .analyzers_platform import ANALYZERS as PLATFORM_ANALYZERS
        all_analyzers = all_analyzers + PLATFORM_ANALYZERS
    except ImportError:
        pass

    # Import AI/GenAI/agentic technology analyzers (Phase 7)
    try:
        from .analyzers_ai import ANALYZERS as AI_ANALYZERS
        all_analyzers = all_analyzers + AI_ANALYZERS
    except ImportError:
        pass

    # Import Operations Research analyzers (SPC, queue, CLV, Monte Carlo, etc.)
    try:
        from .analyzers_or import ANALYZERS as OR_ANALYZERS
        all_analyzers = all_analyzers + OR_ANALYZERS
    except ImportError:
        pass

    # Import strategy framework analyzers (TAM/SAM/SOM, Three Horizons, Porter, BCG, etc.)
    try:
        from .analyzers_strategy import ANALYZERS as STRATEGY_ANALYZERS
        all_analyzers = all_analyzers + STRATEGY_ANALYZERS
    except ImportError:
        pass

    # Import behavioral economics analyzers (DOCTRINE-aware nudge evaluation)
    try:
        from .analyzers_behavioral_econ import ANALYZERS as BEHAV_ECON_ANALYZERS
        all_analyzers = all_analyzers + BEHAV_ECON_ANALYZERS
    except ImportError:
        pass

    # Import growth & business health analyzers (Bain/McKinsey frameworks)
    try:
        from .analyzers_growth import ANALYZERS as GROWTH_ANALYZERS
        all_analyzers = all_analyzers + GROWTH_ANALYZERS
    except ImportError:
        pass

    # Import consulting analyzers (NPS, CES, journey, JTBD, Kano, brand health)
    try:
        from .analyzers_consulting import ANALYZERS as CONSULTING_ANALYZERS
        all_analyzers = all_analyzers + CONSULTING_ANALYZERS
    except ImportError:
        pass

    # Import balanced scorecard analyzer (Kaplan & Norton)
    try:
        from .balanced_scorecard import ANALYZERS as BSC_ANALYZERS
        all_analyzers = all_analyzers + BSC_ANALYZERS
    except ImportError:
        pass

    # Import executive summary analyzer (freshness check)
    try:
        from .executive_summary import ANALYZERS as EXEC_ANALYZERS
        all_analyzers = all_analyzers + EXEC_ANALYZERS
    except ImportError:
        pass

    # Import OR modality analyzers (SPC, queue, process capability per modality)
    try:
        from .analyzers_or_modality import ANALYZERS as OR_MOD_ANALYZERS
        all_analyzers = all_analyzers + OR_MOD_ANALYZERS
    except ImportError:
        pass

    # Import behavioral economics modality analyzers (nudges, choice, framing)
    try:
        from .analyzers_behav_econ_modality import ANALYZERS as BE_MOD_ANALYZERS
        all_analyzers = all_analyzers + BE_MOD_ANALYZERS
    except ImportError:
        pass

    # Import learning science analyzers (Krashen, Swain, Long, Bjork, Gilmore)
    try:
        from .analyzers_learning_science import ANALYZERS as LS_ANALYZERS
        all_analyzers = all_analyzers + LS_ANALYZERS
    except ImportError:
        pass

    # Import modality adaptation layer (core-loop analyzers extended to non-core features)
    try:
        from .analyzers_modality_adaptation import ANALYZERS as MOD_ADAPT_ANALYZERS
        all_analyzers = all_analyzers + MOD_ADAPT_ANALYZERS
    except ImportError:
        pass

    # Import design quality analyzers (visual_vibe: Awwwards-tier aesthetic self-improvement)
    try:
        from .analyzers_design_quality import ANALYZERS as DESIGN_QUALITY_ANALYZERS
        all_analyzers = all_analyzers + DESIGN_QUALITY_ANALYZERS
    except ImportError:
        pass

    # Import copy/content truth-drift analyzers (pricing, features, privacy, legal)
    try:
        from .analyzers_copy_drift import ANALYZERS as COPY_DRIFT_ANALYZERS
        all_analyzers = all_analyzers + COPY_DRIFT_ANALYZERS
    except ImportError:
        pass

    # Run all analyzers
    for analyzer in all_analyzers:
        try:
            results = analyzer(conn)
            findings.extend(results)
        except Exception as e:
            logger.warning("Product intelligence analyzer %s failed: %s", analyzer.__name__, e)

    findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 9))

    # Suppress false signals based on product lifecycle phase
    from ._base import suppress_low_sample_findings, _lifecycle_phase, _real_user_count
    lifecycle_phase = _lifecycle_phase(conn)
    lifecycle_real_users = _real_user_count(conn)
    findings = suppress_low_sample_findings(conn, findings)

    # Assess data confidence per dimension
    data_confidence = _assess_data_confidence(conn)

    # Dimension scoring — score all known dimensions
    all_dimensions = sorted(set(
        _STANDARD_DIMS + _DOMAIN_DIMS + _SYSTEM_PROCESS_DIMS +
        [f.get("dimension", "unknown") for f in findings]
    ))

    # Track which dimensions had findings suppressed by lifecycle phase
    from ._base import (
        _CODE_ASSESSABLE_DOWNGRADE_DIMENSIONS, _USER_BEHAVIOR_DIMENSIONS,
        _CODE_DATA_DIMENSIONS,
    )

    dimension_scores = {}
    for dim in all_dimensions:
        conf = data_confidence.get(dim, "low")
        score, grade = _dimension_score(findings, dim, confidence=conf)
        dim_findings = [f for f in findings if f.get("dimension") == dim]
        entry = {
            "score": score,
            "grade": grade,
            "finding_count": len(dim_findings),
            "confidence": conf,
        }
        # Mark dimensions whose severity was adjusted by lifecycle phase
        if lifecycle_phase != "established":
            if dim in _CODE_ASSESSABLE_DOWNGRADE_DIMENSIONS:
                entry["downgraded"] = True
                entry["suppression_reason"] = lifecycle_phase
            elif dim in _USER_BEHAVIOR_DIMENSIONS and lifecycle_phase == "pre_launch":
                entry["suppressed"] = True
                entry["suppression_reason"] = "pre_launch"
            # Code/data dimensions are NOT suppressed or downgraded
        dimension_scores[dim] = entry

    # Trends from previous audits (needs >=3 data points)
    # New format: {dim: {arrow, smoothed, days_to_boundary, slope_per_audit}}
    trends_raw = _compute_trends(conn, dimension_scores)
    trends = {}
    for dim in dimension_scores:
        trend_val = trends_raw.get(dim, {"arrow": "→"})
        if isinstance(trend_val, dict):
            dimension_scores[dim]["trend"] = trend_val.get("arrow", "→")
            trends[dim] = trend_val
        else:
            # Backward compat with string format
            dimension_scores[dim]["trend"] = trend_val
            trends[dim] = {"arrow": trend_val}

    # Overall
    score_val, grade = _overall_score(dimension_scores)
    overall = {"score": score_val, "grade": grade}

    # ── Phase 3: Finding Lifecycle ──
    finding_lifecycle = {}
    false_negatives = {}
    try:
        from .finding_lifecycle import (
            deduplicate_findings, auto_tag_root_causes,
            check_stale_findings, check_regression, compute_engine_accuracy,
            estimate_false_negatives,
        )
        # Deduplicate against existing findings
        new_findings = deduplicate_findings(conn, findings)
        # Auto-tag root causes
        auto_tag_root_causes(conn, findings)
        # Check for stale findings
        stale = check_stale_findings(conn)
        findings.extend(stale)
        # Check for regressions
        regressions = check_regression(conn)
        findings.extend(regressions)
        # Engine accuracy meta-analysis
        accuracy = compute_engine_accuracy(conn)
        # False negative estimation (Six Sigma)
        false_negatives = estimate_false_negatives(conn)
        finding_lifecycle = {
            "new_findings": len(new_findings),
            "stale_findings": len(stale),
            "regressions": len(regressions),
            "engine_accuracy": accuracy,
        }
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Finding lifecycle failed: %s", e)

    # ── Phase 4: Feedback Loops ──
    feedback_summary = {}
    copq = {}
    cycle_times = {}
    self_audit = {}
    try:
        from .feedback_loops import (
            verify_recommendation_outcomes, calibrate_thresholds,
            get_loop_closure_summary, estimate_copq,
            record_prediction_outcomes, expire_stale_predictions,
            generate_self_audit_report,
        )
        from ._synthesis import compute_cycle_times
        # Self-correction: score pending predictions and expire stale ones
        record_prediction_outcomes(conn)
        expire_stale_predictions(conn)
        verify_recommendation_outcomes(conn)
        calibration = calibrate_thresholds(conn)
        feedback_summary = get_loop_closure_summary(conn)
        feedback_summary["calibration_adjustments"] = len(calibration)
        # Six Sigma COPQ
        copq = estimate_copq(conn)
        # Lean cycle times
        cycle_times = compute_cycle_times(conn)
        # Self-correction: self-audit report
        self_audit = generate_self_audit_report(conn)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Feedback loops failed: %s", e)

    # ── Phase 5: Multi-Agent Advisors ──
    advisor_opinions = {}
    sprint_plan = {}
    try:
        from .advisors import Mediator
        mediator = Mediator()
        opinions = mediator.evaluate_all(conn, findings)
        advisor_opinions = opinions
        sprint_plan = mediator.plan_sprint(conn, findings)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Advisors failed: %s", e)

    # ── Phase 6: Human-in-the-Loop ──
    decision_queue = []
    try:
        from .human_loop import (
            classify_and_escalate_all, apply_overrides, check_override_sunsets,
        )
        # Apply overrides to filter suppressed findings
        findings = apply_overrides(findings, conn)
        # Check for expired overrides
        override_findings = check_override_sunsets(conn)
        findings.extend(override_findings)
        # Classify and escalate
        decision_queue = classify_and_escalate_all(conn, findings, advisor_opinions)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Human-in-the-loop failed: %s", e)

    # Synthesis (after all phases have had their say)
    synthesis = _synthesize(findings, dimension_scores, data_confidence)

    # Cross-domain constraint finder (Doc 6), falls back to ToC-only
    constraint = {}
    try:
        from .constraint_finder import identify_cross_domain_constraint
        constraint = identify_cross_domain_constraint(conn, dimension_scores)
    except Exception:
        try:
            from ._synthesis import identify_system_constraint
            constraint = identify_system_constraint(conn, dimension_scores)
        except Exception as e:
            logger.warning("ToC constraint identification failed: %s", e)

    # Save for trending
    _save_audit(conn, grade, score_val, dimension_scores, findings)

    # ── DMAIC Logging ──
    # Record Define→Measure→Analyze→Improve→Control entries for each
    # dimension with findings, so methodology_coverage detects DMAIC activity.
    try:
        from .quality_metrics_generator import create_dmaic_entry_from_audit
        create_dmaic_entry_from_audit(conn, findings, dimension_scores, overall)
    except (ImportError, AttributeError):
        pass
    except Exception as e:
        logger.warning("DMAIC logging failed: %s", e)

    # ── Meta-Intelligence: GenAI validates the intelligence system itself ──
    try:
        from .meta_intelligence import (
            meta_validate_dimensions, meta_validate_findings,
            meta_validate_scoring, meta_suggest_criteria,
        )
        meta_findings = []
        meta_findings.extend(meta_validate_dimensions(conn, dimension_scores))
        meta_findings.extend(meta_validate_findings(conn, findings))
        meta_findings.extend(meta_validate_scoring(conn, dimension_scores))
        # Suggest criteria for dimensions scoring 100/A with 0 findings
        for dim, info in dimension_scores.items():
            if info.get("score", 0) >= 95 and info.get("finding_count", 0) == 0:
                meta_findings.extend(meta_suggest_criteria(conn, dim, findings))
        if meta_findings:
            findings.extend(meta_findings)
            # Re-score 'meta' dimension (uses top-level import)
            m_score, m_grade = _dimension_score(meta_findings, "meta", confidence="medium")
            dimension_scores["meta"] = {
                "score": m_score, "grade": m_grade,
                "finding_count": len(meta_findings), "confidence": "medium",
            }
            # Update overall score
            score_val, grade = _overall_score(dimension_scores)
            overall = {"score": score_val, "grade": grade}
    except ImportError:
        pass
    except Exception as e:
        logger.debug("Meta-intelligence failed: %s", e)

    # ── Prescription Layer ──
    work_order = None
    try:
        from .prescription import generate_work_order, check_stale_work_orders, NoActionableFindings
        audit_row = conn.execute("SELECT MAX(id) FROM product_audit").fetchone()
        audit_cycle_id = audit_row[0] if audit_row else None
        if audit_cycle_id:
            check_stale_work_orders(conn)
            try:
                wo = generate_work_order(conn, audit_cycle_id)
                work_order = {
                    "id": wo.id,
                    "finding_id": wo.finding_id,
                    "prediction_id": wo.prediction_id,
                    "constraint_dimension": wo.constraint_dimension,
                    "constraint_score": wo.constraint_score,
                    "marginal_improvement": wo.marginal_improvement,
                    "instruction": wo.instruction,
                    "target_file": wo.target_file,
                    "target_parameter": wo.target_parameter,
                    "direction": wo.direction,
                    "success_metric": wo.success_metric,
                    "success_baseline": wo.success_baseline,
                    "success_threshold": wo.success_threshold,
                    "verification_window_days": wo.verification_window_days,
                    "subordinated_count": wo.subordinated_count,
                    "confidence_label": wo.confidence_label,
                    "confidence_score": wo.confidence_score,
                    "instruction_source": wo.instruction_source,
                    "status": "pending",
                }
            except NoActionableFindings:
                work_order = {"status": "no_actionable_findings"}
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Prescription layer failed: %s", e)

    # ── Product Experience: release regression check ──
    release_regressions = None
    try:
        from .product_experience import analyze_release_regressions, seed_feedback_prompts
        seed_feedback_prompts(conn)
        regressions = analyze_release_regressions(conn)
        if regressions:
            findings.extend(regressions)
            release_regressions = [{"title": r.get("title"), "dimension": r.get("dimension")} for r in regressions]
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Release regression check failed: %s", e)

    # ── External Grounding ──
    external_grounding = None
    try:
        from .external_grounding import (
            seed_knowledge_base, seed_benchmark_registry,
            detect_knowledge_conflicts, compare_against_benchmarks,
        )
        seed_knowledge_base(conn)
        seed_benchmark_registry(conn)
        conflicts = detect_knowledge_conflicts(conn)
        benchmarks = compare_against_benchmarks(conn)
        external_grounding = {
            "knowledge_conflicts": conflicts,
            "benchmark_comparisons": benchmarks,
            "conflicts_count": len(conflicts),
            "benchmarks_count": len(benchmarks),
        }
    except ImportError:
        pass
    except Exception as e:
        logger.warning("External grounding failed: %s", e)

    # ── Quality Metrics Generation (pre-methodology) ──
    # Populate quality_metric, spc_observation, advisor budgets, work item
    # lifecycle timestamps, and DMAIC measure data BEFORE methodology grading
    # so detection functions find real operational evidence.
    try:
        from .quality_metrics_generator import run_all as run_quality_metrics
        run_quality_metrics(conn)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Quality metrics generation failed: %s", e)

    # ── Grammar/Skill Auto-Linking ──
    # Link grammar points and skills to content items so curriculum analyzers
    # find populated content_grammar / content_skill junction tables.
    try:
        from ..grammar_linker import link_all as link_grammar_all
        link_grammar_all(conn)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Grammar/skill linking failed: %s", e)

    # ── Data Seeding (copy registry, marketing pages) ──
    try:
        from .quality_metrics_generator import seed_copy_registry, seed_marketing_pages
        seed_copy_registry(conn)
        seed_marketing_pages(conn)
    except (ImportError, AttributeError):
        pass
    except Exception as e:
        logger.warning("Data seeding failed: %s", e)

    # ── Methodology Coverage Grading ──
    methodology_grades = None
    try:
        from .methodology_coverage import grade_all_frameworks
        audit_row_mc = conn.execute("SELECT MAX(id) FROM product_audit").fetchone()
        mc_audit_id = audit_row_mc[0] if audit_row_mc else None
        methodology_grades = grade_all_frameworks(conn, audit_cycle_id=mc_audit_id)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Methodology coverage grading failed: %s", e)

    return {
        "findings": findings,
        "dimension_scores": dimension_scores,
        "overall": overall,
        "trends": trends,
        "synthesis": synthesis,
        "data_confidence": data_confidence,
        # New layers
        "finding_lifecycle": finding_lifecycle,
        "feedback_summary": feedback_summary,
        "advisor_opinions": advisor_opinions,
        "sprint_plan": sprint_plan,
        "decision_queue": decision_queue,
        # A+ additions
        "constraint": constraint,
        "copq": copq,
        "false_negatives": false_negatives,
        "cycle_times": cycle_times,
        "self_audit": self_audit,
        "work_order": work_order,
        "external_grounding": external_grounding,
        "release_regressions": release_regressions,
        "methodology_grades": methodology_grades,
        # Lifecycle context
        "lifecycle_phase": lifecycle_phase,
        "real_user_count": lifecycle_real_users,
        # Backward compat
        "total": len(findings),
        "by_severity": _count_by(findings, "severity"),
        "by_dimension": _count_by(findings, "dimension"),
        "top_priorities": findings[:5],
    }
