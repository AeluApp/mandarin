"""Methodology Coverage Grading — grades how well the system implements its claimed frameworks.

42 detection functions query actual DB tables. No code inspection, no tokens.
Solo-dev calibrated: N/A components don't penalize, but applicable gaps do.

Frameworks graded: Six Sigma, Lean, Kanban, Operations Research,
Theory of Constraints, SPC, DoE, Spiral (N/A), Scrum (N/A).
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from ._base import _finding, _f, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class DetectionResult:
    component_name: str
    framework: str
    present: bool
    quality: float       # 0-100
    evidence: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    raw_score: float = 0.0
    confidence: float = 0.0


# ── Grade scale (finer than _base._GRADE_THRESHOLDS) ────────────────────────

_MC_GRADE_THRESHOLDS = [
    (95, "A+"), (88, "A"), (80, "B+"), (70, "B"),
    (60, "C+"), (50, "C"), (40, "D"), (0, "F"),
]


def _score_to_grade(score: float) -> str:
    """Convert 0-100 score to methodology coverage letter grade."""
    for threshold, grade in _MC_GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _grade_to_numeric(grade: str) -> float:
    """Convert grade label back to midpoint score for trend comparison."""
    _map = {"A+": 97, "A": 91, "B+": 84, "B": 75, "C+": 65, "C": 55, "D": 45, "F": 20}
    return _map.get(grade, 0)


# ── Detection Functions ─────────────────────────────────────────────────────
#
# Each function: fn(conn) -> DetectionResult
# Score logic documented in plan spec.


# ── Six Sigma ──

def check_dpmo_implementation(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    rows = _safe_scalar(conn, "SELECT COUNT(*) FROM quality_metric WHERE metric_type = 'dpmo'")
    if rows > 0:
        score += 40
        evidence.append(f"{rows} DPMO measurements recorded")
        recent = _safe_scalar(conn,
            "SELECT COUNT(*) FROM quality_metric WHERE metric_type = 'dpmo' AND measured_at > datetime('now', '-30 days')")
        if recent > 0:
            score += 20
            evidence.append(f"{recent} measurements in last 30 days")
        else:
            gaps.append("No DPMO measurements in last 30 days")
        sigma = _safe_scalar(conn, "SELECT COUNT(*) FROM quality_metric WHERE metric_type LIKE '%sigma%'")
        if sigma > 0:
            score += 25
            evidence.append("Sigma level tracking active")
        else:
            gaps.append("No sigma level tracking")
        trend = _safe_scalar(conn, "SELECT COUNT(DISTINCT date(measured_at)) FROM quality_metric WHERE metric_type = 'dpmo'")
        if trend >= 3:
            score += 15
            evidence.append(f"Trending over {trend} distinct dates")
        else:
            gaps.append("Insufficient trend data (need 3+ dates)")
    else:
        gaps.append("No DPMO measurements found")
    return DetectionResult("DPMO tracking", "six_sigma", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_spc_implementation(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    chart_types = _safe_query_all(conn,
        "SELECT DISTINCT chart_type FROM spc_observation")
    n_types = len(chart_types)
    if n_types > 0:
        score += min(80, n_types * 40)
        evidence.append(f"{n_types} chart type(s): {', '.join(r[0] for r in chart_types)}")
        for ct in chart_types:
            ct_count = _safe_scalar(conn,
                "SELECT COUNT(*) FROM spc_observation WHERE chart_type = ?", (ct[0],))
            if ct_count >= 25:
                score += 20 / n_types
                evidence.append(f"{ct[0]}: {ct_count} observations (sufficient)")
            else:
                gaps.append(f"{ct[0]}: only {ct_count} observations (need 25+)")
    else:
        gaps.append("No SPC observations recorded")
    return DetectionResult("Statistical Process Control", "six_sigma", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_cpk_implementation(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    rows = _safe_scalar(conn, "SELECT COUNT(*) FROM quality_metric WHERE metric_type LIKE 'capability%'")
    if rows > 0:
        score += 50
        evidence.append(f"{rows} capability metric(s)")
        recent = _safe_scalar(conn,
            "SELECT COUNT(*) FROM quality_metric WHERE metric_type LIKE 'capability%' AND measured_at > datetime('now', '-30 days')")
        if recent > 0:
            score += 30
            evidence.append("Recent capability data available")
        else:
            gaps.append("No recent capability measurements")
        per_dim = _safe_scalar(conn,
            "SELECT COUNT(DISTINCT metric_type) FROM quality_metric WHERE metric_type LIKE 'capability%'")
        if per_dim > 1:
            score += 20
            evidence.append(f"Capability tracked across {per_dim} dimensions")
    else:
        gaps.append("No process capability (Cpk) metrics found")
    return DetectionResult("Process capability (Cpk)", "six_sigma", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_dmaic_implementation(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    rows = _safe_query_all(conn, "SELECT * FROM pi_dmaic_log ORDER BY run_at DESC LIMIT 5")
    if rows:
        phases = ["define_json", "measure_json", "analyze_json", "improve_json", "control_json"]
        phase_present = set()
        for row in rows:
            for p in phases:
                val = row[p] if p in row.keys() else None
                if val and val != "null":
                    phase_present.add(p)
        score = min(100, len(phase_present) * 20)
        evidence.append(f"{len(phase_present)}/5 DMAIC phases have data")
        for p in phases:
            if p not in phase_present:
                gaps.append(f"DMAIC phase '{p.replace('_json', '')}' has no data")
    else:
        gaps.append("No DMAIC log entries found")
    return DetectionResult("DMAIC cycle", "six_sigma", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_copq_implementation(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    rows = _safe_scalar(conn, "SELECT COUNT(*) FROM quality_metric WHERE metric_type LIKE '%copq%'")
    if rows > 0:
        score += 60
        evidence.append(f"{rows} COPQ measurement(s)")
        categorized = _safe_scalar(conn,
            "SELECT COUNT(DISTINCT metric_type) FROM quality_metric WHERE metric_type LIKE '%copq%'")
        if categorized > 1:
            score += 40
            evidence.append(f"COPQ categorized into {categorized} types")
        else:
            gaps.append("COPQ not categorized by failure type")
    else:
        gaps.append("No Cost of Poor Quality metrics found")
    return DetectionResult("Cost of Poor Quality", "six_sigma", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_false_negative_detection(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    rows = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_false_negative_signal")
    if rows > 0:
        score += 50
        evidence.append(f"{rows} false negative signal(s) recorded")
    else:
        gaps.append("No false negative signals recorded")
    fn_rate = _safe_query(conn,
        "SELECT false_negative_rate FROM pi_threshold_calibration WHERE false_negative_rate IS NOT NULL LIMIT 1")
    if fn_rate:
        score += 30
        evidence.append("False negative rate tracked in threshold calibration")
    else:
        gaps.append("False negative rate not tracked in calibration")
    recent = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_false_negative_signal WHERE detected_at > datetime('now', '-30 days')")
    if recent > 0:
        score += 20
        evidence.append(f"{recent} recent signals (last 30 days)")
    elif rows > 0:
        gaps.append("No recent false negative signals")
    return DetectionResult("False negative detection", "six_sigma", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_bidirectional_calibration(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    cal_rows = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_threshold_calibration")
    if cal_rows > 0:
        score += 50
        evidence.append(f"{cal_rows} calibration entries")
        fpr = _safe_query(conn,
            "SELECT false_positive_rate FROM pi_threshold_calibration WHERE false_positive_rate IS NOT NULL LIMIT 1")
        if fpr:
            score += 25
            evidence.append("False positive rate tracked")
        else:
            gaps.append("False positive rate not tracked")
        loosening = _safe_query(conn,
            "SELECT COUNT(*) FROM pi_threshold_calibration WHERE prior_threshold IS NOT NULL AND threshold_value > prior_threshold")
        if loosening and loosening[0] > 0:
            score += 25
            evidence.append("Evidence of threshold loosening (bidirectional)")
        else:
            gaps.append("No evidence of threshold loosening — calibration may be one-directional")
    else:
        gaps.append("No threshold calibration data found")
    return DetectionResult("Bidirectional calibration", "six_sigma", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_western_electric_rules(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    we_metrics = _safe_scalar(conn,
        "SELECT COUNT(*) FROM quality_metric WHERE metric_type LIKE '%western%' OR metric_type LIKE '%rule%'")
    spc_findings = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%pattern%' OR title LIKE '%rule%' OR title LIKE '%SPC%'")
    if we_metrics > 0 or spc_findings > 0:
        score += 60
        evidence.append(f"Pattern detection evidence: {we_metrics} metrics, {spc_findings} findings")
    else:
        gaps.append("No Western Electric rule pattern detection evidence")
    trend_detection = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%trend%' OR title LIKE '%run%'")
    if trend_detection > 0:
        score += 40
        evidence.append(f"Trend/run detection: {trend_detection} findings")
    else:
        gaps.append("No trend or run detection evidence")
    return DetectionResult("Western Electric rules", "six_sigma", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


# ── Lean ──

def check_vsm_implementation(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    flow_findings = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE dimension IN ('flow', 'timing', 'ux')")
    if flow_findings > 0:
        score += 40
        evidence.append(f"{flow_findings} flow-related findings (value stream analysis)")
    else:
        gaps.append("No flow-related findings generated")
    funnel = _safe_scalar(conn,
        "SELECT COUNT(*) FROM lifecycle_event", default=0)
    if funnel > 0:
        score += 30
        evidence.append(f"{funnel} lifecycle/funnel events tracked")
    else:
        gaps.append("No lifecycle funnel data")
    dropoff = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%drop%' OR title LIKE '%funnel%'")
    if dropoff > 0:
        score += 30
        evidence.append(f"Dropoff detection active ({dropoff} findings)")
    else:
        gaps.append("No funnel dropoff detection findings")
    return DetectionResult("Value Stream Mapping", "lean", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_waste_identification(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    waste_types = {
        "overproduction": "title LIKE '%overproduc%' OR title LIKE '%excess%'",
        "staleness": "title LIKE '%stale%' OR title LIKE '%unused%' OR title LIKE '%staleness%'",
        "defects": "dimension = 'drill_quality'",
        "waiting": "title LIKE '%wait%' OR title LIKE '%delay%' OR title LIKE '%slow%'",
    }
    detected = 0
    for wtype, clause in waste_types.items():
        count = _safe_scalar(conn, f"SELECT COUNT(*) FROM pi_finding WHERE {clause}")
        if count > 0:
            detected += 1
            evidence.append(f"Waste type '{wtype}': {count} findings")
    score = min(100, detected * 25)
    if detected < len(waste_types):
        missing = [w for w in waste_types if _safe_scalar(conn,
            f"SELECT COUNT(*) FROM pi_finding WHERE {waste_types[w]}") == 0]
        for w in missing:
            gaps.append(f"Waste type '{w}' not detected")
    return DetectionResult("Waste identification", "lean", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_cycle_time_measurement(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    completed = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE started_at IS NOT NULL AND completed_at IS NOT NULL")
    if completed >= 5:
        score += 50
        evidence.append(f"{completed} completed items with timestamps")
    elif completed > 0:
        score += 20
        evidence.append(f"Only {completed} items with cycle time data (need 5+)")
        gaps.append("Insufficient completed items for reliable cycle time")
    else:
        gaps.append("No work items with both started_at and completed_at")
    ct_findings = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%cycle%' OR title LIKE '%lead time%'")
    if ct_findings > 0:
        score += 30
        evidence.append(f"Cycle time tracked in {ct_findings} findings")
    else:
        gaps.append("No cycle time findings generated")
    if completed >= 5:
        avg_ct = _safe_query(conn,
            """SELECT AVG(julianday(completed_at) - julianday(started_at))
               FROM work_item WHERE started_at IS NOT NULL AND completed_at IS NOT NULL""")
        if avg_ct and avg_ct[0]:
            score += 20
            evidence.append(f"Average cycle time: {avg_ct[0]:.1f} days")
    return DetectionResult("Cycle time measurement", "lean", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_flow_metrics(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    completed_per_week = _safe_query(conn,
        """SELECT COUNT(*) * 7.0 / MAX(1, julianday('now') - julianday(MIN(completed_at)))
           FROM work_item WHERE completed_at IS NOT NULL""")
    if completed_per_week and completed_per_week[0] and completed_per_week[0] > 0:
        score += 50
        evidence.append(f"Throughput measurable: ~{completed_per_week[0]:.1f} items/week")
    else:
        gaps.append("Cannot compute throughput (no completed work items)")
    lead_time = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%lead%' OR title LIKE '%throughput%'")
    if lead_time > 0:
        score += 50
        evidence.append(f"Lead time/throughput tracked in {lead_time} findings")
    else:
        gaps.append("No lead time tracking in findings")
    return DetectionResult("Flow metrics", "lean", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_pull_system(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    svc = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE service_class IS NOT NULL")
    if svc > 0:
        score += 50
        evidence.append(f"{svc} work items with service class assigned")
    else:
        gaps.append("No service classes assigned to work items")
    in_progress = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE status = 'in_progress'")
    if in_progress is not None and in_progress <= 5:
        score += 50
        evidence.append(f"WIP appears bounded: {in_progress} in progress")
    elif in_progress is not None:
        score += 25
        gaps.append(f"WIP may be too high: {in_progress} items in progress")
    return DetectionResult("Pull system", "lean", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_audit_frequency(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    last_audit = _safe_query(conn,
        "SELECT MAX(run_at) FROM product_audit")
    if last_audit and last_audit[0]:
        from datetime import datetime as _dt
        try:
            last = _dt.fromisoformat(last_audit[0].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days_ago = (now - last).days
            if days_ago <= 7:
                score = 100
                evidence.append(f"Last audit {days_ago} day(s) ago (within 7-day target)")
            elif days_ago <= 30:
                score = 60
                evidence.append(f"Last audit {days_ago} days ago")
                gaps.append("Audit frequency below 7-day target")
            else:
                score = 30
                evidence.append(f"Last audit {days_ago} days ago")
                gaps.append(f"Audit significantly overdue ({days_ago} days)")
        except (ValueError, TypeError):
            score = 30
            evidence.append("Audit exists but date unparseable")
    else:
        gaps.append("No product audits found")
    return DetectionResult("Audit frequency", "lean", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


# ── Kanban ──

def check_wip_limits(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    statuses = _safe_query_all(conn,
        "SELECT status, COUNT(*) FROM work_item GROUP BY status")
    if statuses:
        score += 40
        status_str = ", ".join(f"{r[0]}: {r[1]}" for r in statuses)
        evidence.append(f"Work stages defined: {status_str}")
    else:
        gaps.append("No work items with defined stages")
    in_progress = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE status = 'in_progress'")
    if in_progress is not None and in_progress <= 5:
        score += 40
        evidence.append(f"In-progress count bounded: {in_progress}")
    elif in_progress is not None:
        score += 20
        gaps.append(f"WIP may exceed limits: {in_progress} in progress — enforcement not detected")
    svc = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE service_class IS NOT NULL")
    if svc > 0:
        score += 20
        evidence.append(f"{svc} items with service class")
    else:
        gaps.append("No service class differentiation")
    return DetectionResult("WIP limits", "kanban", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_service_classes(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    expedite = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE service_class NOT IN ('standard') AND service_class IS NOT NULL")
    if expedite > 0:
        score += 60
        evidence.append(f"{expedite} non-standard service class items (expedite/etc)")
    else:
        gaps.append("No expedite or non-standard service classes used")
    review_at = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE review_at IS NOT NULL")
    if review_at > 0:
        score += 40
        evidence.append(f"{review_at} items with review_at dates set")
    else:
        gaps.append("No review_at dates set on work items")
    return DetectionResult("Service classes", "kanban", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_aging_alerts(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    stale = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%stale%' OR title LIKE '%aging%'")
    if stale > 0:
        score += 60
        evidence.append(f"{stale} stale/aging findings generated")
    else:
        gaps.append("No stale or aging findings detected")
    blocked = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE blocked_at IS NOT NULL")
    if blocked > 0:
        score += 40
        evidence.append(f"{blocked} work items have blocked_at tracking")
    else:
        gaps.append("No blocked_at tracking on work items")
    return DetectionResult("Aging alerts", "kanban", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_kanban_flow_metrics(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    completed_per_week = _safe_query(conn,
        """SELECT COUNT(*) * 7.0 / MAX(1, julianday('now') - julianday(MIN(completed_at)))
           FROM work_item WHERE completed_at IS NOT NULL""")
    if completed_per_week and completed_per_week[0] and completed_per_week[0] > 0:
        score += 50
        evidence.append(f"Throughput: ~{completed_per_week[0]:.1f} items/week")
    else:
        gaps.append("Cannot compute throughput")
    ct = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE started_at IS NOT NULL AND completed_at IS NOT NULL")
    if ct >= 3:
        score += 50
        evidence.append(f"Cycle time measurable: {ct} completed items with timestamps")
    else:
        gaps.append(f"Insufficient cycle time data ({ct} items, need 3+)")
    return DetectionResult("Flow metrics", "kanban", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_explicit_policies(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    wo_with_metric = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_work_order WHERE success_metric IS NOT NULL AND success_threshold IS NOT NULL")
    if wo_with_metric > 0:
        score += 50
        evidence.append(f"{wo_with_metric} work orders with DoD (success metric + threshold)")
    else:
        gaps.append("No work orders with explicit success criteria")
    decisions = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_decision_log WHERE decision_class IS NOT NULL")
    if decisions > 0:
        score += 50
        evidence.append(f"{decisions} logged decisions with decision_class")
    else:
        gaps.append("No decision policies logged")
    return DetectionResult("Explicit policies", "kanban", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_cfd_implementation(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    has_timestamps = _safe_scalar(conn,
        """SELECT COUNT(*) FROM work_item
           WHERE created_at IS NOT NULL AND started_at IS NOT NULL AND completed_at IS NOT NULL""")
    if has_timestamps > 0:
        score += 60
        evidence.append(f"{has_timestamps} items with full lifecycle timestamps (created→started→completed)")
    else:
        gaps.append("Work items lack full lifecycle timestamps for CFD")
    history_days = _safe_query(conn,
        """SELECT julianday('now') - julianday(MIN(created_at))
           FROM work_item WHERE created_at IS NOT NULL""")
    if history_days and history_days[0] and history_days[0] >= 30:
        score += 40
        evidence.append(f"Historical data spans {history_days[0]:.0f} days (≥30 for CFD)")
    elif history_days and history_days[0]:
        score += 20
        gaps.append(f"Only {history_days[0]:.0f} days of history (need 30+ for meaningful CFD)")
    else:
        gaps.append("No historical work item data")
    return DetectionResult("CFD implementation", "kanban", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_blocker_tracking(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    blocked = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE blocked_at IS NOT NULL")
    if blocked > 0:
        score += 60
        evidence.append(f"{blocked} items have blocked_at recorded")
    else:
        gaps.append("blocked_at never used on work items")
    unblocked = _safe_scalar(conn,
        "SELECT COUNT(*) FROM work_item WHERE unblocked_at IS NOT NULL")
    if unblocked > 0:
        score += 40
        evidence.append(f"{unblocked} items also have unblocked_at (full blocker lifecycle)")
    elif blocked > 0:
        gaps.append("blocked_at used but unblocked_at never recorded")
    return DetectionResult("Blocker tracking", "kanban", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


# ── Operations Research ──

def check_thompson_sampling(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    experiments = _safe_scalar(conn, "SELECT COUNT(*) FROM experiment")
    if experiments > 0:
        score += 50
        evidence.append(f"{experiments} experiment(s) defined")
    else:
        gaps.append("No experiments defined")
    assignments = _safe_scalar(conn, "SELECT COUNT(*) FROM experiment_assignment")
    if assignments > 0:
        score += 30
        evidence.append(f"{assignments} experiment assignment(s)")
    else:
        gaps.append("No experiment assignments tracked")
    concluded = _safe_scalar(conn,
        "SELECT COUNT(*) FROM experiment WHERE status = 'concluded'")
    if concluded > 0:
        score += 20
        evidence.append(f"{concluded} concluded experiment(s)")
    elif experiments > 0:
        gaps.append("No experiments concluded yet")
    return DetectionResult("Thompson Sampling", "operations_research", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_knapsack_implementation(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    budget = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_advisor_resolution WHERE weekly_effort_budget IS NOT NULL")
    if budget > 0:
        score += 60
        evidence.append(f"{budget} advisor resolution(s) with budget constraints")
    else:
        gaps.append("No budget-constrained advisor resolutions")
    advisors = _safe_scalar(conn,
        "SELECT COUNT(DISTINCT advisor) FROM pi_advisor_opinion")
    if advisors > 1:
        score += 40
        evidence.append(f"{advisors} distinct advisors contributing")
    elif advisors == 1:
        score += 20
        evidence.append("Only 1 advisor contributing")
        gaps.append("Single advisor — limited optimization scope")
    else:
        gaps.append("No advisor opinions recorded")
    return DetectionResult("Knapsack optimization", "operations_research", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_queuing_theory(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    queue_metrics = _safe_scalar(conn,
        "SELECT COUNT(*) FROM quality_metric WHERE metric_type LIKE '%queue%' OR metric_type LIKE '%saturation%'")
    if queue_metrics > 0:
        score += 60
        evidence.append(f"{queue_metrics} queue/saturation metrics tracked")
    else:
        gaps.append("No queue depth or saturation metrics")
    alert = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%saturation%' OR title LIKE '%queue%'")
    if alert > 0:
        score += 40
        evidence.append(f"{alert} saturation/queue findings generated")
    else:
        gaps.append("No queue saturation alerts generated")
    return DetectionResult("Queuing theory", "operations_research", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_queue_stability_alert(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    critical = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE (title LIKE '%queue%' OR title LIKE '%saturation%') AND severity = 'critical'")
    if critical > 0:
        score = 100
        evidence.append(f"{critical} critical queue stability finding(s)")
    else:
        non_critical = _safe_scalar(conn,
            "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%queue%' OR title LIKE '%saturation%'")
        if non_critical > 0:
            score = min(70, non_critical * 30)
            evidence.append(f"{non_critical} queue finding(s) (non-critical)")
        else:
            gaps.append("No queue stability alerts generated")
    return DetectionResult("Queue stability alert", "operations_research", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_power_analysis(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    with_sample = _safe_scalar(conn,
        "SELECT COUNT(*) FROM experiment WHERE min_sample_size > 0")
    if with_sample > 0:
        score += 60
        evidence.append(f"{with_sample} experiment(s) with min_sample_size set")
    else:
        gaps.append("No experiments have min_sample_size defined")
    pre_start = _safe_scalar(conn,
        """SELECT COUNT(*) FROM experiment
           WHERE min_sample_size > 0 AND start_date IS NOT NULL
           AND created_at <= start_date""")
    if pre_start > 0:
        score += 40
        evidence.append(f"{pre_start} set sample size before start (proper power analysis)")
    elif with_sample > 0:
        gaps.append("Sample size may have been set after experiment start")
    return DetectionResult("Power analysis", "operations_research", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_batch_sizing(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    varies = _safe_query(conn,
        """SELECT COUNT(DISTINCT items_planned) FROM session_log
           WHERE items_planned IS NOT NULL AND items_planned > 0""")
    distinct_sizes = varies[0] if varies else 0
    if distinct_sizes > 2:
        score += 60
        evidence.append(f"Session batch size varies: {distinct_sizes} distinct values")
    elif distinct_sizes > 0:
        score += 30
        evidence.append(f"Only {distinct_sizes} distinct batch sizes")
        gaps.append("Limited batch size variation — may not be adaptive")
    else:
        gaps.append("No items_planned data in session_log")
    adaptive = _safe_scalar(conn,
        "SELECT COUNT(*) FROM session_log WHERE items_planned IS NOT NULL AND items_planned > 0")
    if adaptive > 10:
        score += 40
        evidence.append(f"{adaptive} sessions with planned item counts")
    elif adaptive > 0:
        score += 20
        gaps.append("Insufficient session data for adaptive batch assessment")
    return DetectionResult("Batch sizing", "operations_research", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


# ── Theory of Constraints ──

def check_constraint_identification(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    wo = _safe_query(conn,
        "SELECT constraint_dimension, confidence_score FROM pi_work_order WHERE constraint_dimension IS NOT NULL ORDER BY created_at DESC LIMIT 1")
    if wo:
        score += 60
        evidence.append(f"Current constraint: {wo[0]}")
        recent = _safe_scalar(conn,
            "SELECT COUNT(*) FROM pi_work_order WHERE constraint_dimension IS NOT NULL AND created_at > datetime('now', '-30 days')")
        if recent > 0:
            score += 20
            evidence.append(f"Constraint identified recently ({recent} in last 30 days)")
        else:
            gaps.append("Constraint identification not recent")
        conf = wo[1] if wo[1] else 0
        if conf > 0.5:
            score += 20
            evidence.append(f"Confidence score: {conf:.2f}")
        else:
            gaps.append(f"Low constraint confidence: {conf}")
    else:
        gaps.append("No constraint dimension identified in work orders")
    return DetectionResult("Constraint identification", "theory_of_constraints", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_exploitation_strategy(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    wo = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_work_order WHERE instruction IS NOT NULL")
    if wo > 0:
        score += 60
        evidence.append(f"{wo} work order(s) with actionable instructions")
    else:
        gaps.append("No work orders with actionable instructions")
    targeted = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_work_order WHERE target_file IS NOT NULL OR target_parameter IS NOT NULL")
    if targeted > 0:
        score += 40
        evidence.append(f"{targeted} work orders target specific files/parameters")
    elif wo > 0:
        gaps.append("Work order instructions not targeted to specific files/parameters")
    return DetectionResult("Exploitation strategy", "theory_of_constraints", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_subordination_enforcer(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    sub = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_work_order WHERE subordinated_count > 0")
    if sub > 0:
        score += 50
        evidence.append(f"{sub} work order(s) with active subordination")
    else:
        gaps.append("No work orders with subordination enforcement")
    sub_count = _safe_query(conn,
        "SELECT MAX(subordinated_count) FROM pi_work_order WHERE subordinated_count > 0")
    if sub_count and sub_count[0] and sub_count[0] > 0:
        score += 30
        evidence.append(f"Max subordinated findings: {sub_count[0]}")
    overrides = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_decision_log WHERE decision = 'override'")
    if overrides > 0:
        score += 20
        evidence.append(f"{overrides} subordination overrides logged")
    elif sub > 0:
        gaps.append("No subordination override history")
    return DetectionResult("Subordination enforcer", "theory_of_constraints", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_elevation_strategy(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    mi = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_work_order WHERE marginal_improvement IS NOT NULL")
    if mi > 0:
        score += 60
        evidence.append(f"{mi} work order(s) track marginal improvement")
    else:
        gaps.append("No marginal improvement tracking in work orders")
    direction = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_work_order WHERE direction IS NOT NULL")
    if direction > 0:
        score += 40
        evidence.append(f"{direction} work orders specify improvement direction")
    elif mi > 0:
        gaps.append("Marginal improvement tracked but no direction specified")
    return DetectionResult("Elevation strategy", "theory_of_constraints", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_constraint_history(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    distinct = _safe_scalar(conn,
        "SELECT COUNT(DISTINCT constraint_dimension) FROM pi_work_order WHERE constraint_dimension IS NOT NULL")
    if distinct >= 2:
        score += 60
        evidence.append(f"{distinct} different constraints identified historically")
    elif distinct == 1:
        score += 30
        evidence.append("Only 1 constraint ever identified")
        gaps.append("No constraint transitions observed — may be stuck")
    else:
        gaps.append("No constraint history")
    transitions = _safe_query_all(conn,
        """SELECT DISTINCT constraint_dimension FROM pi_work_order
           WHERE constraint_dimension IS NOT NULL ORDER BY created_at""")
    if len(transitions) >= 2:
        score += 40
        chain = " → ".join(r[0] for r in transitions)
        evidence.append(f"Constraint progression: {chain}")
    elif distinct >= 2:
        score += 20
        gaps.append("Constraints identified but transition order unclear")
    return DetectionResult("Constraint history", "theory_of_constraints", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


# ── SPC ──

def check_control_charts(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    chart_types = _safe_query_all(conn,
        "SELECT chart_type, COUNT(*) FROM spc_observation GROUP BY chart_type")
    n_types = 0
    for ct in chart_types:
        if ct[1] >= 20:
            n_types += 1
            score += 30
            evidence.append(f"Chart '{ct[0]}': {ct[1]} observations (sufficient)")
        else:
            evidence.append(f"Chart '{ct[0]}': {ct[1]} observations (need 20+)")
            gaps.append(f"Chart '{ct[0]}' has insufficient data")
    score = min(90, score)
    if n_types >= 3:
        score += 10
        evidence.append(f"{n_types} chart types with sufficient data")
    if not chart_types:
        gaps.append("No SPC control chart data")
    return DetectionResult("Control charts", "spc", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_ooc_detection(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    ooc_findings = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%SPC%' OR title LIKE '%control%' OR title LIKE '%violation%'")
    if ooc_findings > 0:
        score += 60
        evidence.append(f"{ooc_findings} OOC/SPC violation findings")
    else:
        gaps.append("No out-of-control findings generated")
    ooc_metrics = _safe_scalar(conn,
        "SELECT COUNT(*) FROM quality_metric WHERE metric_type LIKE '%violation%'")
    if ooc_metrics > 0:
        score += 40
        evidence.append(f"{ooc_metrics} violation metrics recorded")
    else:
        gaps.append("No SPC violation metrics tracked")
    return DetectionResult("OOC detection", "spc", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_cause_distinction(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    rca = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE root_cause_tag IS NOT NULL")
    if rca > 0:
        score += 50
        evidence.append(f"{rca} findings with root cause tags")
    else:
        gaps.append("No root cause tags on findings")
    analyze = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_dmaic_log WHERE analyze_json IS NOT NULL AND analyze_json != 'null'")
    if analyze > 0:
        score += 50
        evidence.append(f"{analyze} DMAIC analyze phases completed")
    else:
        gaps.append("No DMAIC analyze phase data")
    return DetectionResult("Cause distinction", "spc", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_spc_closure(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    resolved = _safe_scalar(conn,
        """SELECT COUNT(*) FROM pi_finding
           WHERE (dimension LIKE '%spc%' OR title LIKE '%SPC%' OR title LIKE '%control%')
           AND status = 'resolved'""")
    if resolved > 0:
        score += 60
        evidence.append(f"{resolved} SPC-related findings resolved")
    else:
        gaps.append("No SPC-related findings have been resolved")
    returned = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_recommendation_outcome WHERE effective = 1")
    if returned > 0:
        score += 40
        evidence.append(f"{returned} effective recommendation outcomes (metrics returned to control)")
    else:
        gaps.append("No verified effective recommendation outcomes")
    return DetectionResult("SPC closure", "spc", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_western_electric(conn) -> DetectionResult:
    """Delegates to the Six Sigma Western Electric check (shared detection)."""
    return check_western_electric_rules(conn)


# ── DoE ──

def check_ab_framework(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    experiments = _safe_scalar(conn, "SELECT COUNT(*) FROM experiment")
    if experiments > 0:
        score += 40
        evidence.append(f"{experiments} experiment(s) defined")
    else:
        gaps.append("No experiments in A/B framework")
    assignments = _safe_scalar(conn, "SELECT COUNT(*) FROM experiment_assignment")
    if assignments > 0:
        score += 30
        evidence.append(f"{assignments} assignment(s) tracked")
    else:
        gaps.append("No experiment assignments")
    exposures = _safe_scalar(conn, "SELECT COUNT(*) FROM experiment_exposure")
    if exposures > 0:
        score += 30
        evidence.append(f"{exposures} exposure(s) logged")
    else:
        gaps.append("No experiment exposures logged")
    return DetectionResult("A/B framework", "doe", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_power_analysis_doe(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    with_sample = _safe_scalar(conn,
        "SELECT COUNT(*) FROM experiment WHERE min_sample_size > 0")
    if with_sample > 0:
        score += 70
        evidence.append(f"{with_sample} experiment(s) with min_sample_size")
    else:
        gaps.append("No experiments with power analysis (min_sample_size)")
    pre_conclusion = _safe_scalar(conn,
        """SELECT COUNT(*) FROM experiment
           WHERE min_sample_size > 0 AND status != 'concluded'""")
    if pre_conclusion > 0:
        score += 30
        evidence.append(f"{pre_conclusion} active experiments with pre-computed sample size")
    elif with_sample > 0:
        gaps.append("Power analysis may have been post-hoc")
    return DetectionResult("Power analysis", "doe", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_significance_testing(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    concluded = _safe_scalar(conn,
        "SELECT COUNT(*) FROM experiment WHERE conclusion IS NOT NULL AND status = 'concluded'")
    if concluded > 0:
        score += 60
        evidence.append(f"{concluded} concluded experiment(s) with conclusions")
    else:
        gaps.append("No concluded experiments with statistical conclusions")
    # Check if conclusion mentions statistics
    stat_conclusion = _safe_query(conn,
        """SELECT conclusion FROM experiment
           WHERE conclusion IS NOT NULL AND status = 'concluded' LIMIT 1""")
    if stat_conclusion and stat_conclusion[0]:
        conclusion_text = str(stat_conclusion[0]).lower()
        if any(kw in conclusion_text for kw in ['p-value', 'significant', 'z-test', 'chi-square', 'confidence']):
            score += 40
            evidence.append("Conclusion contains statistical language")
        else:
            score += 20
            gaps.append("Conclusion may lack formal statistical testing")
    return DetectionResult("Significance testing", "doe", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_effect_size(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    conclusions = _safe_query_all(conn,
        "SELECT conclusion FROM experiment WHERE conclusion IS NOT NULL AND status = 'concluded'")
    has_effect = False
    has_ztest = False
    for row in conclusions:
        text = str(row[0]).lower()
        if 'effect size' in text or 'cohen' in text or 'practical significance' in text:
            has_effect = True
        if 'z-test' in text or 'z test' in text:
            has_ztest = True
    if has_effect:
        score = 100
        evidence.append("Effect size reported in experiment conclusions")
    elif has_ztest:
        score = 50
        evidence.append("Z-test used (partial credit for statistical rigor)")
        gaps.append("Effect size not explicitly reported")
    elif conclusions:
        score = 20
        evidence.append("Experiments concluded but no effect size language")
        gaps.append("No effect size measurement in conclusions")
    else:
        gaps.append("No concluded experiments to check for effect size")
    return DetectionResult("Effect size", "doe", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_experiment_health(conn) -> DetectionResult:
    score, evidence, gaps = 0.0, [], []
    # Check for guardrail_metrics — column may not exist
    guardrails = _safe_scalar(conn,
        "SELECT COUNT(*) FROM experiment WHERE guardrail_metrics IS NOT NULL", default=0)
    if guardrails > 0:
        score += 50
        evidence.append(f"{guardrails} experiment(s) with guardrail metrics")
    else:
        # Column may not exist, check more broadly
        total = _safe_scalar(conn, "SELECT COUNT(*) FROM experiment")
        if total > 0:
            gaps.append("No guardrail metrics defined on experiments")
        else:
            gaps.append("No experiments to assess health")
    # SRM check evidence — look for mentions in findings or quality metrics
    srm = _safe_scalar(conn,
        "SELECT COUNT(*) FROM quality_metric WHERE metric_type LIKE '%srm%' OR metric_type LIKE '%ratio%mismatch%'")
    srm_findings = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_finding WHERE title LIKE '%SRM%' OR title LIKE '%sample ratio%'")
    if srm > 0 or srm_findings > 0:
        score += 50
        evidence.append("SRM check evidence found")
    else:
        gaps.append("No sample ratio mismatch (SRM) checking detected")
    return DetectionResult("Experiment health", "doe", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


# ── Design for Six Sigma (DFSS) ──

def check_voc_capture(conn) -> DetectionResult:
    """Check Voice of Customer signal capture."""
    score, evidence, gaps = 0.0, [], []
    total = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_voc_capture")
    if total > 0:
        score += 40
        evidence.append(f"{total} VOC signals captured")
        recent = _safe_scalar(conn,
            "SELECT COUNT(*) FROM pi_voc_capture WHERE captured_at >= datetime('now', '-30 days')")
        if recent > 0:
            score += 30
            evidence.append(f"{recent} VOC signals in last 30 days")
        else:
            gaps.append("No VOC signals captured in last 30 days")
        sources = _safe_scalar(conn,
            "SELECT COUNT(DISTINCT source) FROM pi_voc_capture")
        if sources >= 2:
            score += 30
            evidence.append(f"{sources} distinct VOC sources")
        else:
            gaps.append("VOC signals from only one source (need diversity)")
    else:
        gaps.append("No Voice of Customer signals captured")
    return DetectionResult("VOC capture", "dfss", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_design_fmea_usage(conn) -> DetectionResult:
    """Check Design FMEA usage in DMADV cycles."""
    score, evidence, gaps = 0.0, [], []
    total = _safe_scalar(conn,
        "SELECT COUNT(*) FROM pi_dmadv_log WHERE design_fmea_max_rpn > 0")
    if total > 0:
        score += 50
        evidence.append(f"{total} DMADV cycle(s) with Design FMEA scores")
        blocked = _safe_scalar(conn,
            "SELECT COUNT(*) FROM pi_dmadv_log WHERE gate_blocked = 'design'")
        if blocked > 0:
            score += 25
            evidence.append(f"{blocked} feature(s) blocked by design gate (gate is enforced)")
        else:
            evidence.append("No features blocked (all passed or FMEA returned low risk)")
        recent = _safe_scalar(conn,
            "SELECT COUNT(*) FROM pi_dmadv_log WHERE run_at >= datetime('now', '-30 days')")
        if recent > 0:
            score += 25
            evidence.append(f"{recent} DMADV cycle(s) in last 30 days")
        else:
            gaps.append("No DMADV cycles in last 30 days")
    else:
        # Check if cycles exist but without FMEA
        any_cycles = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_dmadv_log")
        if any_cycles > 0:
            score += 20
            evidence.append(f"{any_cycles} DMADV cycle(s) exist but without Design FMEA scores")
            gaps.append("Design FMEA not producing RPN scores (LLM may be offline)")
        else:
            gaps.append("No DMADV cycles recorded — Design FMEA not used")
    return DetectionResult("Design FMEA", "dfss", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_dmadv_implementation(conn) -> DetectionResult:
    """Check DMADV cycle implementation completeness."""
    score, evidence, gaps = 0.0, [], []
    total = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_dmadv_log")
    if total > 0:
        score += 30
        evidence.append(f"{total} DMADV cycle(s) recorded")
        # Check phase completeness: all 5 phases should have data
        complete = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_dmadv_log
            WHERE define_json IS NOT NULL AND define_json != '{}'
              AND measure_json IS NOT NULL AND measure_json != '{}'
              AND analyze_json IS NOT NULL AND analyze_json != '{}'
              AND design_json IS NOT NULL AND design_json != '{}'
              AND verify_json IS NOT NULL AND verify_json != '{}'
        """)
        if complete > 0:
            score += 40
            evidence.append(f"{complete} cycle(s) with all 5 DMADV phases complete")
        else:
            gaps.append("No DMADV cycles with all 5 phases completed")
        approved = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_dmadv_log WHERE approved = 1")
        if approved > 0:
            score += 30
            evidence.append(f"{approved} feature(s) approved through DMADV gate")
        else:
            gaps.append("No features have passed the DMADV approval gate")
    else:
        gaps.append("No DMADV cycles recorded — DFSS not yet active")
    return DetectionResult("DMADV cycle", "dfss", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


def check_design_verification(conn) -> DetectionResult:
    """Check post-launch design specification verification."""
    score, evidence, gaps = 0.0, [], []
    total = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_design_spec")
    if total > 0:
        score += 30
        evidence.append(f"{total} design spec(s) defined")
        verified = _safe_scalar(conn,
            "SELECT COUNT(*) FROM pi_design_spec WHERE status = 'verified'")
        if verified > 0:
            pct = round(verified / total * 100, 1)
            score += 40
            evidence.append(f"{verified}/{total} spec(s) verified ({pct}%)")
        else:
            gaps.append("No design specs have been verified post-launch")
        active = _safe_scalar(conn,
            "SELECT COUNT(*) FROM pi_design_spec WHERE status IN ('draft', 'active')")
        if active > 0:
            score += 30
            evidence.append(f"{active} spec(s) awaiting verification")
        else:
            if verified == total:
                score += 30
                evidence.append("All specs verified")
            else:
                gaps.append("No active specs pending verification")
    else:
        gaps.append("No design specifications created — post-launch verification not tracked")
    return DetectionResult("Design verification", "dfss", score > 0, min(score, 100),
                           evidence, gaps, min(score, 100), min(1.0, score / 100))


# ── Detection function registry ─────────────────────────────────────────────

DETECTION_FUNCTIONS = {
    # Six Sigma
    "check_dpmo_implementation": check_dpmo_implementation,
    "check_spc_implementation": check_spc_implementation,
    "check_cpk_implementation": check_cpk_implementation,
    "check_dmaic_implementation": check_dmaic_implementation,
    "check_copq_implementation": check_copq_implementation,
    "check_false_negative_detection": check_false_negative_detection,
    "check_bidirectional_calibration": check_bidirectional_calibration,
    "check_western_electric_rules": check_western_electric_rules,
    # Lean
    "check_vsm_implementation": check_vsm_implementation,
    "check_waste_identification": check_waste_identification,
    "check_cycle_time_measurement": check_cycle_time_measurement,
    "check_flow_metrics": check_flow_metrics,
    "check_pull_system": check_pull_system,
    "check_audit_frequency": check_audit_frequency,
    # Kanban
    "check_wip_limits": check_wip_limits,
    "check_service_classes": check_service_classes,
    "check_aging_alerts": check_aging_alerts,
    "check_kanban_flow_metrics": check_kanban_flow_metrics,
    "check_explicit_policies": check_explicit_policies,
    "check_cfd_implementation": check_cfd_implementation,
    "check_blocker_tracking": check_blocker_tracking,
    # Operations Research
    "check_thompson_sampling": check_thompson_sampling,
    "check_knapsack_implementation": check_knapsack_implementation,
    "check_queuing_theory": check_queuing_theory,
    "check_queue_stability_alert": check_queue_stability_alert,
    "check_power_analysis": check_power_analysis,
    "check_batch_sizing": check_batch_sizing,
    # Theory of Constraints
    "check_constraint_identification": check_constraint_identification,
    "check_exploitation_strategy": check_exploitation_strategy,
    "check_subordination_enforcer": check_subordination_enforcer,
    "check_elevation_strategy": check_elevation_strategy,
    "check_constraint_history": check_constraint_history,
    # SPC
    "check_control_charts": check_control_charts,
    "check_ooc_detection": check_ooc_detection,
    "check_cause_distinction": check_cause_distinction,
    "check_spc_closure": check_spc_closure,
    "check_western_electric": check_western_electric,
    # DoE
    "check_ab_framework": check_ab_framework,
    "check_power_analysis_doe": check_power_analysis_doe,
    "check_significance_testing": check_significance_testing,
    "check_effect_size": check_effect_size,
    "check_experiment_health": check_experiment_health,
    # DFSS
    "check_voc_capture": check_voc_capture,
    "check_design_fmea_usage": check_design_fmea_usage,
    "check_dmadv_implementation": check_dmadv_implementation,
    "check_design_verification": check_design_verification,
}


# ── Grading Engine ───────────────────────────────────────────────────────────

def grade_all_frameworks(conn, audit_cycle_id=None) -> dict:
    """Run all detections, compute weighted grades, persist, return summary.

    Returns dict with per-framework grades and overall methodology score.
    """
    # Load component registry
    components = _safe_query_all(conn,
        "SELECT * FROM pi_framework_components ORDER BY framework, component_name")
    if not components:
        logger.warning("No framework components found — seed migration may not have run")
        return {"frameworks": {}, "overall_score": 0, "overall_grade": "F"}

    # Group by framework
    frameworks = {}
    for comp in components:
        fw = comp["framework"]
        if fw not in frameworks:
            frameworks[fw] = []
        frameworks[fw].append(comp)

    results = {}
    all_applicable_scores = []
    all_applicable_weights = []

    for fw_name, fw_components in frameworks.items():
        component_grades = []
        applicable_scores = []
        applicable_weights = []
        na_count = 0
        gap_count = 0

        for comp in fw_components:
            applicable = comp["solo_dev_applicable"]
            detect_fn_name = comp["detection_function"]
            weight = comp["weight"]

            if applicable == "no" or weight == 0.0 or not detect_fn_name:
                # N/A component — skip from weighted average
                na_count += 1
                component_grades.append({
                    "component_name": comp["component_name"],
                    "raw_score": 0,
                    "weighted_score": 0,
                    "grade_label": "N/A",
                    "evidence": [],
                    "gaps": [],
                    "solo_dev_applicable": applicable,
                    "weight": weight,
                })
                continue

            # Run detection
            detect_fn = DETECTION_FUNCTIONS.get(detect_fn_name)
            if not detect_fn:
                logger.warning("Detection function %s not found", detect_fn_name)
                na_count += 1
                continue

            try:
                result = detect_fn(conn)
            except Exception as e:
                logger.warning("Detection %s failed: %s", detect_fn_name, e)
                result = DetectionResult(
                    comp["component_name"], fw_name,
                    False, 0, [], [f"Detection error: {e}"], 0, 0,
                )

            grade_label = _score_to_grade(result.raw_score)
            if result.gaps:
                gap_count += len(result.gaps)

            # Check for override
            override = _safe_query(conn,
                """SELECT raw_score, override_reason FROM pi_framework_grades
                   WHERE framework = ? AND component_name = ? AND was_overridden = 1
                   ORDER BY graded_at DESC LIMIT 1""",
                (fw_name, comp["component_name"]))
            was_overridden = 0
            override_reason = None
            if override:
                result.raw_score = override[0]
                grade_label = _score_to_grade(result.raw_score)
                was_overridden = 1
                override_reason = override[1]

            weighted = result.raw_score * weight
            applicable_scores.append(weighted)
            applicable_weights.append(weight)
            all_applicable_scores.append(weighted)
            all_applicable_weights.append(weight)

            grade_entry = {
                "component_name": comp["component_name"],
                "raw_score": round(result.raw_score, 1),
                "weighted_score": round(weighted, 1),
                "grade_label": grade_label,
                "evidence": result.evidence,
                "gaps": result.gaps,
                "gap_description": "; ".join(result.gaps) if result.gaps else None,
                "recommendation": _generate_recommendation(fw_name, comp["component_name"], result),
                "solo_dev_applicable": applicable,
                "weight": weight,
                "was_overridden": was_overridden,
                "override_reason": override_reason,
            }
            component_grades.append(grade_entry)

            # Persist component grade
            _persist_component_grade(conn, fw_name, comp["component_name"],
                                     grade_entry, audit_cycle_id)

        # Framework score: weighted average of applicable components
        if applicable_weights:
            fw_score = sum(applicable_scores) / sum(applicable_weights)
        else:
            fw_score = 100.0  # All N/A → perfect score

        fw_grade = _score_to_grade(fw_score)

        # Trend from prior
        prior = _safe_query(conn,
            """SELECT overall_grade FROM pi_framework_summary_grades
               WHERE framework = ? ORDER BY graded_at DESC LIMIT 1""",
            (fw_name,))
        prior_grade = prior[0] if prior else None
        trend = _compute_trend(prior_grade, fw_grade) if prior_grade else None

        # Summary text
        summary = _generate_framework_summary(fw_name, fw_score, fw_grade, component_grades, gap_count)

        results[fw_name] = {
            "score": round(fw_score, 1),
            "grade": fw_grade,
            "applicable_count": len(applicable_weights),
            "na_count": na_count,
            "gap_count": gap_count,
            "prior_grade": prior_grade,
            "trend": trend,
            "summary": summary,
            "components": component_grades,
        }

        # Persist framework summary
        _persist_framework_summary(conn, fw_name, fw_score, fw_grade,
                                   len(applicable_weights), na_count, gap_count,
                                   prior_grade, trend, summary, audit_cycle_id)

    # Overall methodology score
    if all_applicable_weights:
        overall_score = sum(all_applicable_scores) / sum(all_applicable_weights)
    else:
        overall_score = 100.0
    overall_grade = _score_to_grade(overall_score)

    conn.commit()

    return {
        "frameworks": results,
        "overall_score": round(overall_score, 1),
        "overall_grade": overall_grade,
        "framework_count": len(results),
        "graded_at": datetime.now(timezone.utc).isoformat(),
    }


def _compute_trend(prior_grade, current_grade):
    """Compare grades to determine trend."""
    prior_val = _grade_to_numeric(prior_grade)
    current_val = _grade_to_numeric(current_grade)
    if current_val > prior_val + 3:
        return "improving"
    elif current_val < prior_val - 3:
        return "declining"
    return "stable"


def _generate_recommendation(framework, component, result):
    """Generate a recommendation for underperforming components."""
    if result.raw_score >= 80:
        return None
    if not result.gaps:
        return None
    return f"[{framework}/{component}] Address: {result.gaps[0]}"


def _generate_framework_summary(fw_name, score, grade, components, gap_count):
    """Generate human-readable summary of framework coverage."""
    applicable = [c for c in components if c["grade_label"] != "N/A"]
    if not applicable:
        return f"{fw_name}: All components N/A for solo dev. No action needed."
    strong = [c for c in applicable if c["raw_score"] >= 80]
    weak = [c for c in applicable if c["raw_score"] < 50]
    parts = [f"{fw_name}: {grade} ({score:.0f}/100)."]
    if strong:
        parts.append(f"Strong: {', '.join(c['component_name'] for c in strong)}.")
    if weak:
        parts.append(f"Gaps: {', '.join(c['component_name'] for c in weak)}.")
    parts.append(f"{gap_count} total gap(s).")
    return " ".join(parts)


def _persist_component_grade(conn, framework, component_name, grade_entry, audit_cycle_id):
    """Persist a single component grade to pi_framework_grades."""
    conn.execute(
        """INSERT INTO pi_framework_grades
           (id, audit_cycle_id, framework, component_name, raw_score, weighted_score,
            grade_label, evidence, gap_description, recommendation,
            solo_dev_applicable, was_overridden, override_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), audit_cycle_id, framework, component_name,
         grade_entry["raw_score"], grade_entry["weighted_score"],
         grade_entry["grade_label"],
         json.dumps(grade_entry.get("evidence", [])),
         grade_entry.get("gap_description"),
         grade_entry.get("recommendation"),
         grade_entry["solo_dev_applicable"],
         grade_entry.get("was_overridden", 0),
         grade_entry.get("override_reason")),
    )


def _persist_framework_summary(conn, framework, score, grade,
                                applicable_count, na_count, gap_count,
                                prior_grade, trend, summary, audit_cycle_id):
    """Persist framework summary grade to pi_framework_summary_grades."""
    conn.execute(
        """INSERT INTO pi_framework_summary_grades
           (id, audit_cycle_id, framework, overall_score, overall_grade,
            applicable_component_count, na_component_count, gap_count,
            prior_grade, trend, summary_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), audit_cycle_id, framework, score, grade,
         applicable_count, na_count, gap_count,
         prior_grade, trend, summary),
    )


# ── Findings Generator (ANALYZERS-compatible) ───────────────────────────────

_SEVERITY_MAP = {
    "B": "low",
    "C+": "medium",
    "C": "medium",
    "D": "high",
    "F": "critical",
}


def generate_methodology_findings(conn) -> list:
    """Generate findings for frameworks graded below B+.

    Compatible with the ANALYZERS pattern: fn(conn) -> list[dict].
    """
    findings = []
    try:
        grades = grade_all_frameworks(conn)
    except Exception as e:
        logger.warning("Methodology grading failed in findings generator: %s", e)
        return []

    for fw_name, fw_data in grades.get("frameworks", {}).items():
        grade = fw_data.get("grade", "A+")
        score = fw_data.get("score", 100)

        # Only generate findings for grades below B+
        if score >= 80:
            continue

        severity = _SEVERITY_MAP.get(grade, "low")

        # Collect top 3 gaps
        all_gaps = []
        for comp in fw_data.get("components", []):
            for gap in comp.get("gaps", []):
                all_gaps.append(f"[{comp['component_name']}] {gap}")
        top_gaps = all_gaps[:3]
        detail = "\n".join(f"- {g}" for g in top_gaps) if top_gaps else "No specific gaps identified."

        findings.append(_finding(
            dimension="methodology",
            severity=severity,
            title=f"Methodology gap: {fw_name} coverage at {grade} ({score:.0f}/100)",
            analysis=f"{fw_data.get('summary', fw_name + ' needs improvement.')} Top gaps:\n{detail}",
            recommendation=f"Address {fw_name} methodology gaps to improve coverage score.",
            claude_prompt=f"Review and improve {fw_name} methodology implementation. Focus on: {'; '.join(top_gaps[:2]) if top_gaps else 'general coverage'}",
            impact=f"{fw_name} methodology coverage is below B+ threshold",
            files=_f("admin_routes"),
        ))

    return findings


ANALYZERS = [generate_methodology_findings]
