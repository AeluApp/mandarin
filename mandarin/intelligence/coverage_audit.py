"""Product Intelligence — Coverage Audit Registry.

Maps every Aelu component to its intelligence coverage status.
Identifies gaps and blind spots where the engine has no visibility.
Emits findings for actionable gaps.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from ._base import _finding, _safe_scalar

logger = logging.getLogger(__name__)

DOMAINS = ["learning", "content", "ai_components", "methodology", "product_market"]

# Full coverage map: every component the engine should watch
# status: "covered" | "partial" | "gap" | "blind_spot"
COVERAGE_MAP = [
    # ── Learning Domain ──
    {"domain": "learning", "component": "srs_scheduler", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "scheduler_audit dimension"},
    {"domain": "learning", "component": "drill_quality_scoring", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "drill_quality dimension"},
    {"domain": "learning", "component": "tone_grading", "status": "covered", "document": "Doc 5 (AI Outcome)", "notes": "AI component outcome measurement"},
    {"domain": "learning", "component": "difficulty_model", "status": "covered", "document": "Doc 5 (AI Outcome)", "notes": "ML health monitoring"},
    {"domain": "learning", "component": "error_taxonomy", "status": "covered", "document": "Doc 2 (Domain Analyzers)", "notes": "error_taxonomy dimension"},
    {"domain": "learning", "component": "cross_modality_transfer", "status": "covered", "document": "Doc 2 (Domain Analyzers)", "notes": "cross_modality dimension"},
    {"domain": "learning", "component": "curriculum_progression", "status": "covered", "document": "Doc 2 (Domain Analyzers)", "notes": "curriculum dimension"},
    {"domain": "learning", "component": "hsk_level_transitions", "status": "covered", "document": "Doc 2 (Domain Analyzers)", "notes": "hsk_cliff dimension"},
    {"domain": "learning", "component": "encounter_loop", "status": "covered", "document": "Doc 2 (Domain Analyzers)", "notes": "encounter_loop dimension"},
    {"domain": "learning", "component": "session_pacing", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "timing dimension"},
    {"domain": "learning", "component": "retention_tracking", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "retention dimension"},
    {"domain": "learning", "component": "speaking_practice", "status": "partial", "document": "Doc 5 (AI Outcome)", "notes": "Tone grading measured but speaking frequency/fluency not tracked"},
    {"domain": "learning", "component": "reading_comprehension", "status": "gap", "document": None, "notes": "Graded reader exists but no comprehension quality metric"},
    {"domain": "learning", "component": "listening_comprehension", "status": "gap", "document": None, "notes": "Extensive listening exists but comprehension not measured"},

    # ── Content Domain ──
    {"domain": "content", "component": "content_accuracy", "status": "covered", "document": "Doc 5 (AI Outcome)", "notes": "AI review queue accuracy tracking"},
    {"domain": "content", "component": "content_coverage_hsk", "status": "covered", "document": "Doc 2 (Domain Analyzers)", "notes": "curriculum analyzer checks HSK coverage"},
    {"domain": "content", "component": "context_notes_quality", "status": "partial", "document": "Doc 1 (Analyzers)", "notes": "Existence checked but quality not measured"},
    {"domain": "content", "component": "dialogue_scenarios", "status": "gap", "document": None, "notes": "8 scenarios exist but usage/effectiveness not tracked"},
    {"domain": "content", "component": "grammar_point_coverage", "status": "partial", "document": "Doc 2 (Domain Analyzers)", "notes": "curriculum checks grammar but not per-point effectiveness"},
    {"domain": "content", "component": "media_shelf_quality", "status": "gap", "document": None, "notes": "Media ingest exists but quality/engagement not measured"},
    {"domain": "content", "component": "graded_reader_passages", "status": "gap", "document": None, "notes": "Passages served but readability/engagement not tracked"},
    {"domain": "content", "component": "seed_item_balance", "status": "covered", "document": "Doc 2 (Domain Analyzers)", "notes": "HSK level distribution analyzed"},
    {"domain": "content", "component": "content_freshness", "status": "gap", "document": None, "notes": "No staleness detection for content items"},
    {"domain": "content", "component": "register_pragmatic_coverage", "status": "partial", "document": "Doc 2 (Domain Analyzers)", "notes": "Drill types exist but register balance not measured"},

    # ── AI Components Domain ──
    {"domain": "ai_components", "component": "ai_review_queue", "status": "covered", "document": "Doc 5 (AI Outcome)", "notes": "Full outcome measurement pipeline"},
    {"domain": "ai_components", "component": "fuzzy_dedup", "status": "covered", "document": "Doc 5 (AI Outcome)", "notes": "Dedup outcome tracking"},
    {"domain": "ai_components", "component": "tone_grading_model", "status": "covered", "document": "Doc 5 (AI Outcome)", "notes": "Parselmouth F0 + outcome measurement"},
    {"domain": "ai_components", "component": "difficulty_prediction", "status": "covered", "document": "Doc 5 (AI Outcome)", "notes": "ML health + prediction accuracy"},
    {"domain": "ai_components", "component": "thompson_sampling", "status": "partial", "document": "Doc 1 (Analyzers)", "notes": "Scheduler audited but bandit arm performance not individually tracked"},
    {"domain": "ai_components", "component": "content_generation", "status": "gap", "document": None, "notes": "Content gen scripts exist but output quality not monitored"},
    {"domain": "ai_components", "component": "portfolio_verdict", "status": "covered", "document": "Doc 5 (AI Outcome)", "notes": "AI portfolio assessment"},
    {"domain": "ai_components", "component": "ab_test_engine", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "z-test + experiment endpoints"},
    {"domain": "ai_components", "component": "context_note_generation", "status": "gap", "document": None, "notes": "Generated notes not quality-validated post-creation"},
    {"domain": "ai_components", "component": "jieba_segmentation", "status": "blind_spot", "document": None, "notes": "Used in media ingest but segmentation accuracy never validated"},

    # ── Methodology Domain ──
    {"domain": "methodology", "component": "six_sigma_copq", "status": "covered", "document": "Doc 3 (Feedback Loops)", "notes": "COPQ estimation"},
    {"domain": "methodology", "component": "lean_cycle_times", "status": "covered", "document": "Doc 3 (Feedback Loops)", "notes": "Cycle time tracking"},
    {"domain": "methodology", "component": "toc_constraint", "status": "covered", "document": "Doc 3 (Feedback Loops)", "notes": "Theory of Constraints identification"},
    {"domain": "methodology", "component": "spc_control_charts", "status": "covered", "document": "Doc 4 (Methodology)", "notes": "SPC-to-action automation"},
    {"domain": "methodology", "component": "dmaic_log", "status": "covered", "document": "Doc 4 (Methodology)", "notes": "DMAIC tracking"},
    {"domain": "methodology", "component": "wip_limits", "status": "covered", "document": "Doc 4 (Methodology)", "notes": "WIP limits + aging alerts"},
    {"domain": "methodology", "component": "kanban_flow", "status": "covered", "document": "Doc 4 (Methodology)", "notes": "Service class targets"},
    {"domain": "methodology", "component": "velocity_tracking", "status": "covered", "document": "Doc 4 (Methodology)", "notes": "Velocity tracking"},
    {"domain": "methodology", "component": "risk_appetite", "status": "covered", "document": "Doc 4 (Methodology)", "notes": "Risk appetite thresholds"},
    {"domain": "methodology", "component": "release_gate", "status": "covered", "document": "Doc 4 (Methodology)", "notes": "DoD in release_gate.sh"},
    {"domain": "methodology", "component": "framework_grading", "status": "covered", "document": "Doc 4 (Methodology)", "notes": "grade_all_frameworks"},
    {"domain": "methodology", "component": "external_grounding", "status": "covered", "document": "Doc 4 (External Grounding)", "notes": "Knowledge base + benchmarks"},
    {"domain": "methodology", "component": "prediction_ledger", "status": "covered", "document": "Doc 3 (Feedback Loops)", "notes": "Falsifiable predictions + scoring"},

    # ── Product-Market Domain ──
    {"domain": "product_market", "component": "onboarding_flow", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "onboarding dimension"},
    {"domain": "product_market", "component": "pricing_model", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "profitability dimension"},
    {"domain": "product_market", "component": "competitive_analysis", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "competitive dimension"},
    {"domain": "product_market", "component": "user_engagement", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "engagement dimension"},
    {"domain": "product_market", "component": "marketing_copy", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "copy + marketing dimensions"},
    {"domain": "product_market", "component": "streak_system", "status": "partial", "document": "Doc 1 (Analyzers)", "notes": "Streak exists but gamification effectiveness not measured"},
    {"domain": "product_market", "component": "nps_tracking", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "NPS detractor alerts"},
    {"domain": "product_market", "component": "churn_prediction", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "Churn risk alerts in admin notifications"},
    {"domain": "product_market", "component": "platform_coverage", "status": "covered", "document": "Doc 1 (Analyzers)", "notes": "platform dimension + client_platform analytics"},
    {"domain": "product_market", "component": "weekly_progress_email", "status": "gap", "document": None, "notes": "Email sent but open/click/engagement not tracked"},
    {"domain": "product_market", "component": "teacher_dashboard", "status": "partial", "document": "Doc 1 (Analyzers)", "notes": "Teacher notifications exist but teacher UX not measured"},
    {"domain": "product_market", "component": "referral_system", "status": "blind_spot", "document": None, "notes": "No referral system exists — organic growth unmonitored"},
]

# Prioritized gap closure list (from doc's Table 6)
_GAP_CLOSURE_PRIORITY = [
    {"priority": 1, "component": "reading_comprehension", "domain": "learning", "effort": "medium", "rationale": "Core skill with existing UI but no quality signal"},
    {"priority": 2, "component": "listening_comprehension", "domain": "learning", "effort": "medium", "rationale": "Core skill with existing UI but no quality signal"},
    {"priority": 3, "component": "content_freshness", "domain": "content", "effort": "low", "rationale": "Simple staleness query on content items"},
    {"priority": 4, "component": "dialogue_scenarios", "domain": "content", "effort": "low", "rationale": "Track usage counts from session_log"},
    {"priority": 5, "component": "media_shelf_quality", "domain": "content", "effort": "medium", "rationale": "Track watch completion + vocab encounters per media"},
    {"priority": 6, "component": "graded_reader_passages", "domain": "content", "effort": "medium", "rationale": "Track read completion + lookup rate"},
    {"priority": 7, "component": "content_generation", "domain": "ai_components", "effort": "medium", "rationale": "Post-generation quality validation"},
    {"priority": 8, "component": "context_note_generation", "domain": "ai_components", "effort": "low", "rationale": "Validate generated notes against known-good patterns"},
    {"priority": 9, "component": "weekly_progress_email", "domain": "product_market", "effort": "low", "rationale": "Track email opens via pixel or link tracking"},
    {"priority": 10, "component": "jieba_segmentation", "domain": "ai_components", "effort": "high", "rationale": "Need gold-standard segmented corpus for validation"},
]


def get_coverage_summary(conn) -> dict:
    """Compute coverage summary across all domains.

    Returns dict with domain breakdowns, gap count, coverage percentage,
    and list of gaps.
    """
    domains = {}
    gaps = []

    for domain in DOMAINS:
        domain_items = [c for c in COVERAGE_MAP if c["domain"] == domain]
        covered = sum(1 for c in domain_items if c["status"] == "covered")
        partial = sum(1 for c in domain_items if c["status"] == "partial")
        gap = sum(1 for c in domain_items if c["status"] == "gap")
        blind_spot = sum(1 for c in domain_items if c["status"] == "blind_spot")
        total = len(domain_items)
        domains[domain] = {
            "covered": covered,
            "partial": partial,
            "gap": gap,
            "blind_spot": blind_spot,
            "total": total,
        }
        gaps.extend([c for c in domain_items if c["status"] in ("gap", "blind_spot")])

    total_components = len(COVERAGE_MAP)
    covered_count = sum(1 for c in COVERAGE_MAP if c["status"] == "covered")
    partial_count = sum(1 for c in COVERAGE_MAP if c["status"] == "partial")
    # Partial counts as 0.5 coverage
    coverage_pct = round((covered_count + partial_count * 0.5) / total_components * 100, 1) if total_components > 0 else 0

    return {
        "domains": domains,
        "gap_count": len(gaps),
        "coverage_pct": coverage_pct,
        "gaps": [{"domain": g["domain"], "component": g["component"], "status": g["status"], "notes": g["notes"]} for g in gaps],
        "total_components": total_components,
    }


def log_coverage_snapshot(conn) -> int:
    """Persist the current coverage map to pi_coverage_audit_log.

    Returns the number of rows inserted.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = 0
    for entry in COVERAGE_MAP:
        try:
            conn.execute("""
                INSERT INTO pi_coverage_audit_log
                    (id, logged_at, component, domain, coverage_status, covering_document, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid4()), now,
                entry["component"], entry["domain"], entry["status"],
                entry.get("document"), entry.get("notes"),
            ))
            rows += 1
        except Exception:
            pass
    conn.commit()
    return rows


def get_gap_closure_priority() -> list[dict]:
    """Return the prioritized gap closure list (10 items, ordered)."""
    return list(_GAP_CLOSURE_PRIORITY)


def generate_coverage_findings(conn) -> list[dict]:
    """Emit findings for coverage gaps that are actionable now (priority 1-3)."""
    findings = []
    for item in _GAP_CLOSURE_PRIORITY[:3]:
        findings.append(_finding(
            dimension="pm",
            severity="medium",
            title=f"Intelligence gap: {item['component']}",
            analysis=f"The {item['component']} component in the {item['domain']} domain has no intelligence coverage. {item['rationale']}.",
            recommendation=f"Add measurement for {item['component']} to close this intelligence gap.",
            claude_prompt=f"Add intelligence coverage for {item['component']}: measure quality/effectiveness and emit findings when degraded.",
            impact=f"Closes intelligence gap in {item['domain']} domain",
            files=["mandarin/intelligence/coverage_audit.py"],
        ))
    return findings


ANALYZERS = [generate_coverage_findings]
