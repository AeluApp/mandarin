"""Product Intelligence — Coverage Audit Registry.

Maps every Aelu component to its intelligence coverage status.
Identifies gaps and blind spots where the engine has no visibility.
Emits findings for actionable gaps.
"""

import logging
from datetime import datetime, timezone, UTC
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
    {"domain": "content", "component": "content_freshness", "status": "covered", "document": "Doc 6 (Coverage Audit)", "notes": "Staleness detection + content_freshness quality_metric tracked"},
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
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
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
    """Emit findings for coverage gaps that are actionable now (top 3 uncovered)."""
    findings = []
    # Build set of covered components from the matrix
    covered = {item["component"] for item in COVERAGE_MAP if item["status"] == "covered"}

    emitted = 0
    for item in _GAP_CLOSURE_PRIORITY:
        if emitted >= 3:
            break
        if item["component"] in covered:
            continue  # Already has coverage — skip
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
        emitted += 1
    return findings


def analyze_reading_comprehension(conn):
    """Measure reading comprehension quality from graded reader sessions."""
    findings = []
    # Check if graded reader sessions exist
    reader_sessions = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE session_type = 'reading' AND started_at > datetime('now', '-30 days')
    """, default=0)
    reader_lookups = _safe_scalar(conn, """
        SELECT COUNT(*) FROM vocab_encounter
        WHERE source = 'reader' AND created_at > datetime('now', '-30 days')
    """, default=0)

    if reader_sessions == 0:
        findings.append(_finding(
            dimension="content",
            severity="medium",
            title="No reading comprehension data in last 30 days",
            analysis="No graded reader sessions recorded. Reading comprehension quality cannot be assessed.",
            recommendation="Encourage reading sessions to generate comprehension data.",
            claude_prompt="Check graded reader availability and session routing for reading type sessions.",
            impact="Closes reading_comprehension intelligence gap",
            files=["mandarin/web/reader_routes.py", "mandarin/intelligence/coverage_audit.py"],
        ))
    elif reader_sessions > 0 and reader_lookups > 0:
        lookup_rate = reader_lookups / max(1, reader_sessions)
        if lookup_rate > 20:
            findings.append(_finding(
                dimension="content",
                severity="medium",
                title=f"High lookup rate in reading sessions ({lookup_rate:.0f}/session)",
                analysis=f"Readers look up {lookup_rate:.0f} words per session on average, "
                         "suggesting texts may be above current level.",
                recommendation="Review graded reader level assignment; consider easier texts.",
                claude_prompt="Check reader text HSK level assignment vs. user proficiency.",
                impact="Reading comprehension quality",
                files=["mandarin/web/reader_routes.py"],
            ))
    return findings


def analyze_listening_comprehension(conn):
    """Measure listening comprehension from media shelf and audio drill data."""
    findings = []
    audio_drills = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE drill_type IN ('dictation', 'listening_mc', 'tone_pair')
        AND created_at > datetime('now', '-30 days')
    """, default=0)
    media_views = _safe_scalar(conn, """
        SELECT COUNT(*) FROM media_event
        WHERE created_at > datetime('now', '-30 days')
    """, default=0)

    if audio_drills == 0 and media_views == 0:
        findings.append(_finding(
            dimension="content",
            severity="medium",
            title="No listening comprehension data in last 30 days",
            analysis="No audio drill attempts or media consumption recorded. "
                     "Listening comprehension quality cannot be assessed.",
            recommendation="Ensure audio drills are being scheduled and media shelf is accessible.",
            claude_prompt="Check audio drill scheduling in scheduler.py and media shelf availability.",
            impact="Closes listening_comprehension intelligence gap",
            files=["mandarin/scheduler.py", "mandarin/media_ingest.py"],
        ))
    elif audio_drills > 0:
        audio_accuracy = _safe_scalar(conn, """
            SELECT AVG(CASE WHEN correct = 1 THEN 1.0 ELSE 0.0 END)
            FROM review_event
            WHERE drill_type IN ('dictation', 'listening_mc', 'tone_pair')
            AND created_at > datetime('now', '-30 days')
        """, default=0)
        if audio_accuracy is not None and audio_accuracy < 0.5:
            findings.append(_finding(
                dimension="content",
                severity="medium",
                title=f"Low listening drill accuracy ({audio_accuracy:.0%})",
                analysis=f"Audio drill accuracy is {audio_accuracy:.0%} over the last 30 days. "
                         "This may indicate listening comprehension difficulties or drill difficulty miscalibration.",
                recommendation="Review audio drill difficulty levels and consider scaffolding.",
                claude_prompt="Check audio drill difficulty calibration and consider adding easier listening exercises.",
                impact="Listening comprehension quality",
                files=["mandarin/scheduler.py"],
            ))
    return findings


def analyze_content_freshness(conn):
    """Detect stale content items that haven't been updated in a long time."""
    findings = []
    stale_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE status = 'drill_ready'
        AND (updated_at IS NULL OR updated_at < datetime('now', '-365 days'))
        AND created_at < datetime('now', '-365 days')
    """, default=0)
    total_items = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item WHERE status = 'drill_ready'
    """, default=0)

    if total_items > 0 and stale_count > 0:
        stale_pct = stale_count / total_items * 100
        if stale_pct > 20:
            findings.append(_finding(
                dimension="content",
                severity="low",
                title=f"{stale_count} content items unchanged for >1 year ({stale_pct:.0f}%)",
                analysis=f"{stale_count} of {total_items} drill-ready items have not been updated "
                         "in over a year. While vocabulary is stable, context notes and example "
                         "sentences may benefit from periodic review.",
                recommendation="Review oldest content items for accuracy and freshness.",
                claude_prompt="Query content_item WHERE updated_at < datetime('now', '-365 days') "
                             "and review context notes and example sentences for staleness.",
                impact="Closes content_freshness intelligence gap",
                files=["mandarin/db/core.py"],
            ))

    # Check for items with no context notes
    no_context = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE status = 'drill_ready' AND (context_notes IS NULL OR context_notes = '')
    """, default=0)
    if total_items > 0 and no_context > 100:
        findings.append(_finding(
            dimension="content",
            severity="low",
            title=f"{no_context} items missing context notes",
            analysis=f"{no_context} drill-ready items have no context notes. Context notes "
                     "improve learning by providing usage examples and cultural context.",
            recommendation="Generate context notes for items missing them, starting with HSK 1-3.",
            claude_prompt="Add context notes to content items missing them: "
                         "SELECT id, hanzi FROM content_item WHERE context_notes IS NULL AND hsk_level <= 3.",
            impact="Content quality improvement",
            files=["mandarin/ai/rag_layer.py"],
        ))
    return findings


def generate_waste_findings(conn) -> list[dict]:
    """Detect genuine operational waste from content pipeline data.

    Identifies four Lean waste types:
    - Waiting: items stuck in review queue
    - Overprocessing: duplicate items generated before dedup
    - Staleness: unused content items
    - Defects: rejected or low-quality items
    """
    findings = []

    # Waiting waste: items in review queue > 24h
    stale_queue = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE review_decision IS NULL
        AND created_at < datetime('now', '-1 day')
    """, default=0)
    if stale_queue > 0:
        findings.append(_finding(
            dimension="methodology", severity="low",
            title=f"Waiting waste: {stale_queue} items in review queue > 24h",
            analysis=f"{stale_queue} content items have been waiting in the review queue "
                     "for more than 24 hours without a decision.",
            recommendation="Process review queue items regularly to reduce waiting waste.",
            claude_prompt="Check pi_ai_review_queue for stale items and process them via batch review endpoint.",
            impact="Lean waste reduction: waiting",
            files=["mandarin/web/admin_routes.py"],
        ))

    # Overprocessing/excess waste: items that were deduped (generated unnecessarily)
    dedup_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item WHERE status = 'deduped'
    """, default=0)
    if dedup_count > 0:
        findings.append(_finding(
            dimension="methodology", severity="low",
            title=f"Excess production waste: {dedup_count} items deduped after generation",
            analysis=f"{dedup_count} content items were generated but later identified as "
                     "duplicates. This overproduction represents wasted generation effort.",
            recommendation="Improve pre-generation dedup checks to avoid generating duplicates.",
            claude_prompt="Review fuzzy_dedup.py and drill_generator.py for pre-generation dedup.",
            impact="Lean waste reduction: overprocessing",
            files=["mandarin/ml/fuzzy_dedup.py", "mandarin/ai/drill_generator.py"],
        ))

    # Staleness waste: items never used in drills (skip in pre-launch)
    total_reviews = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
    """, default=0)
    if total_reviews > 0:
        # Only check for unused items when there are actual drill sessions
        unused = _safe_scalar(conn, """
            SELECT COUNT(*) FROM content_item ci
            WHERE ci.status = 'drill_ready'
            AND ci.created_at < datetime('now', '-30 days')
            AND NOT EXISTS (
                SELECT 1 FROM review_event re WHERE re.content_item_id = ci.id
            )
        """, default=0)
        if unused > 100:
            findings.append(_finding(
                dimension="methodology", severity="low",
                title=f"Staleness waste: {unused} drill-ready items unused in 30d",
                analysis=f"{unused} content items are marked drill_ready but have never "
                         "appeared in a drill session. They may need scheduling attention.",
                recommendation="Review content scheduling to ensure all drill-ready items are reachable.",
                claude_prompt="Check scheduler.py to ensure content items are being scheduled for drills.",
                impact="Lean waste reduction: unused inventory",
                files=["mandarin/scheduler.py"],
            ))

    return findings


def generate_queue_findings(conn) -> list[dict]:
    """Monitor review queue depth and emit saturation alerts.

    Implements Operations Research queuing theory monitoring.
    """
    findings = []

    # Queue depth check
    pending = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE review_decision IS NULL
    """, default=0)
    approved = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE review_decision = 'approved'
    """, default=0)
    rejected = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE review_decision = 'rejected'
    """, default=0)
    total = pending + approved + rejected

    if pending > 50:
        findings.append(_finding(
            dimension="methodology", severity="medium",
            title=f"Queue saturation: {pending} items pending review",
            analysis=f"The content review queue has {pending} items awaiting review "
                     f"({total} total, {approved} approved, {rejected} rejected). "
                     "Queue depth exceeds saturation threshold (50).",
            recommendation="Increase review throughput or batch-approve validated items.",
            claude_prompt="Process review queue via POST /api/admin/ai/review-queue/batch.",
            impact="Operations research: queue stability",
            files=["mandarin/web/admin_routes.py"],
        ))
    elif pending > 20:
        findings.append(_finding(
            dimension="methodology", severity="low",
            title=f"Queue depth: {pending} items pending review ({total} total)",
            analysis=f"The content review queue has {pending} pending items. "
                     f"Throughput: {approved} approved, {rejected} rejected.",
            recommendation="Monitor queue depth and process items before saturation.",
            claude_prompt="Check review queue trends and processing rate.",
            impact="Operations research: queue monitoring",
            files=["mandarin/web/admin_routes.py"],
        ))

    return findings


ANALYZERS = [
    generate_coverage_findings,
    analyze_reading_comprehension,
    analyze_listening_comprehension,
    analyze_content_freshness,
    generate_waste_findings,
    generate_queue_findings,
]
