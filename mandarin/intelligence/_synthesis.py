"""Product Intelligence Engine — synthesis, trending, data confidence, audit persistence."""

import json
import logging
import sqlite3

from ._base import (
    _GRADE_THRESHOLDS, _SEVERITY_ORDER, _WEIGHTED_DIMENSIONS,
    _safe_query, _safe_query_all, _safe_scalar,
)

logger = logging.getLogger(__name__)


def _compute_trends(conn, current_scores: dict) -> dict:
    """Exponential smoothing on last 5 audit scores with forecasting.

    Returns dict of {dim: {arrow, smoothed, days_to_boundary, slope_per_audit}}
    instead of just arrow strings. The arrow is still accessible as the string value.
    """
    alpha = 0.3  # smoothing factor

    try:
        rows = conn.execute(
            "SELECT dimension_scores, run_at FROM product_audit ORDER BY run_at DESC LIMIT 5"
        ).fetchall()
        if len(rows) < 3:
            return {dim: {"arrow": "→", "smoothed": info["score"],
                          "days_to_boundary": None, "slope_per_audit": 0.0}
                    for dim, info in current_scores.items()}

        prev_scores_list = []
        for row in rows:
            try:
                prev_scores_list.append(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                continue

        if len(prev_scores_list) < 3:
            return {dim: {"arrow": "→", "smoothed": info["score"],
                          "days_to_boundary": None, "slope_per_audit": 0.0}
                    for dim, info in current_scores.items()}

        trends = {}
        for dim, info in current_scores.items():
            # Build score series: oldest to newest
            series = [ps.get(dim, {}).get("score", None) for ps in reversed(prev_scores_list)]
            series = [s for s in series if s is not None]
            series.append(info["score"])

            if len(series) < 3:
                trends[dim] = {"arrow": "→", "smoothed": info["score"],
                               "days_to_boundary": None, "slope_per_audit": 0.0}
                continue

            # Simple exponential smoothing
            smoothed = series[0]
            for val in series[1:]:
                smoothed = alpha * val + (1 - alpha) * smoothed

            # Compute slope per audit (average of last 3 differences)
            diffs = [series[i] - series[i - 1] for i in range(1, len(series))]
            recent_diffs = diffs[-3:] if len(diffs) >= 3 else diffs
            slope = sum(recent_diffs) / len(recent_diffs) if recent_diffs else 0.0

            # Arrow based on slope
            if slope > 3:
                arrow = "↑"
            elif slope < -3:
                arrow = "↓"
            else:
                arrow = "→"

            # Forecast: days until grade boundary crossing (for declining dimensions)
            days_to_boundary = None
            if slope < -0.5:
                current = info["score"]
                # Find the next lower grade boundary
                for threshold, _grade in _GRADE_THRESHOLDS:
                    if current > threshold:
                        points_to_boundary = current - threshold
                        # Assume ~7 days between audits
                        audits_to_boundary = points_to_boundary / abs(slope)
                        days_to_boundary = round(audits_to_boundary * 7, 0)
                        break

            trends[dim] = {
                "arrow": arrow,
                "smoothed": round(smoothed, 1),
                "days_to_boundary": days_to_boundary,
                "slope_per_audit": round(slope, 2),
            }
        return trends
    except (sqlite3.OperationalError, json.JSONDecodeError, KeyError):
        return {dim: {"arrow": "→", "smoothed": info["score"],
                      "days_to_boundary": None, "slope_per_audit": 0.0}
                for dim, info in current_scores.items()}


def identify_system_constraint(conn, dimension_scores: dict) -> dict:
    """Theory of Constraints: find the dimension whose improvement yields
    the largest overall score improvement.

    Simulates fixing each non-A dimension to 90 and computes marginal gain.
    Returns exploitation strategy (what to do now) and elevation strategy (invest in).
    """
    if not dimension_scores:
        return {"constraint": None, "exploitation": "", "elevation": "", "subordination": ""}

    # Current overall (weighted average)
    total_weight = 0.0
    weighted_sum = 0.0
    for dim, info in dimension_scores.items():
        weight = 1.5 if dim in _WEIGHTED_DIMENSIONS else 1.0
        weighted_sum += info["score"] * weight
        total_weight += weight
    current_overall = weighted_sum / total_weight if total_weight > 0 else 80.0

    # Simulate fixing each dimension to 90 and measure improvement
    best_dim = None
    best_improvement = 0.0
    improvements = {}

    for target_dim, target_info in dimension_scores.items():
        if target_info["score"] >= 90:
            continue  # Already A grade
        # Compute new overall with this dimension at 90
        new_sum = 0.0
        for dim, info in dimension_scores.items():
            weight = 1.5 if dim in _WEIGHTED_DIMENSIONS else 1.0
            score = 90.0 if dim == target_dim else info["score"]
            new_sum += score * weight
        new_overall = new_sum / total_weight if total_weight > 0 else 80.0
        improvement = new_overall - current_overall
        improvements[target_dim] = round(improvement, 2)
        if improvement > best_improvement:
            best_improvement = improvement
            best_dim = target_dim

    if best_dim is None:
        return {
            "constraint": None,
            "exploitation": "All dimensions at A grade — no constraint",
            "elevation": "",
            "subordination": "",
            "improvements": improvements,
        }

    # Build exploitation/elevation strategies based on dimension type
    exploitation_map = {
        "retention": "Focus current sprint on churn-risk users and session quality",
        "ux": "Fix top UX friction points from client error logs",
        "drill_quality": "Improve lowest-accuracy drill types and add scaffolding",
        "srs_funnel": "Unblock stuck items in the mastery pipeline",
        "engineering": "Fix crashes and reduce error rates in hot paths",
        "onboarding": "Optimize signup-to-first-session conversion",
        "content": "Add content for uncovered grammar/vocabulary areas",
        "tone_phonology": "Improve tone grading accuracy and add targeted drills",
    }
    elevation_map = {
        "retention": "Build predictive churn model and proactive intervention",
        "ux": "Add session quality instrumentation and A/B test UI variants",
        "drill_quality": "Design new drill types for weak modalities",
        "srs_funnel": "Rework SRS interval algorithm for stuck items",
        "engineering": "Add comprehensive error monitoring and alerting",
        "onboarding": "Build guided onboarding flow with progress milestones",
        "content": "Expand content library with automated generation",
        "tone_phonology": "Integrate real-time tone feedback in drill flow",
    }

    # Non-constraints should subordinate
    non_constraints = [d for d in improvements if d != best_dim and improvements[d] > 0]
    subordination = ""
    if non_constraints:
        subordination = (
            f"Don't optimize {', '.join(non_constraints[:3])} until {best_dim} improves. "
            f"Improvements to non-constraints won't meaningfully improve the overall score."
        )

    return {
        "constraint": best_dim,
        "constraint_score": dimension_scores[best_dim]["score"],
        "marginal_improvement": round(best_improvement, 2),
        "exploitation": exploitation_map.get(best_dim, f"Focus sprint on {best_dim} dimension"),
        "elevation": elevation_map.get(best_dim, f"Invest in {best_dim} infrastructure"),
        "subordination": subordination,
        "improvements": improvements,
    }


def run_dmaic_cycle(conn, dimension: str) -> dict:
    """Run a Six Sigma DMAIC cycle for a given dimension.

    Define → Measure → Analyze → Improve → Control.
    Persists cycle to pi_dmaic_log table.
    """
    from .feedback_loops import _measure_current_metric

    # Define: pull latest finding titles + severities
    findings = _safe_query_all(conn, """
        SELECT title, severity, times_seen, status
        FROM pi_finding
        WHERE dimension = ? AND status NOT IN ('resolved', 'rejected')
        ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END
    """, (dimension,))
    define = {
        "dimension": dimension,
        "open_findings": [{"title": f["title"], "severity": f["severity"],
                           "times_seen": f["times_seen"] or 1} for f in (findings or [])],
        "problem_count": len(findings or []),
    }

    # Measure: current metric value
    current = _measure_current_metric(conn, dimension, dimension)
    measure = {"current_value": current, "metric_name": dimension}

    # Analyze: root cause tags
    root_causes = _safe_query_all(conn, """
        SELECT title, root_cause_tag, linked_finding_id
        FROM pi_finding
        WHERE dimension = ? AND root_cause_tag IS NOT NULL
          AND status NOT IN ('resolved', 'rejected')
    """, (dimension,))
    analyze = {
        "root_causes": [{"title": r["title"], "tag": r["root_cause_tag"]}
                        for r in (root_causes or [])],
        "root_cause_count": len(root_causes or []),
    }

    # Improve: pull recommendations with highest priority from advisors
    recommendations = _safe_query_all(conn, """
        SELECT ao.recommendation, ao.priority_score, ao.advisor
        FROM pi_advisor_opinion ao
        JOIN pi_finding pf ON ao.finding_id = pf.id
        WHERE pf.dimension = ? AND pf.status NOT IN ('resolved', 'rejected')
        ORDER BY ao.priority_score DESC
        LIMIT 5
    """, (dimension,))
    improve = {
        "top_recommendations": [{"recommendation": r["recommendation"],
                                  "priority": r["priority_score"],
                                  "advisor": r["advisor"]}
                                 for r in (recommendations or [])],
    }

    # Control: SPC status + threshold calibration
    spc_status = _safe_query_all(conn, """
        SELECT chart_type, value, ucl, lcl, rule_violated
        FROM spc_observation
        WHERE chart_type LIKE ? || '%'
        ORDER BY observed_at DESC LIMIT 5
    """, (dimension,))
    calibration = _safe_query(conn, """
        SELECT threshold_value, false_positive_rate, calibrated_at
        FROM pi_threshold_calibration
        WHERE metric_name = ?
    """, (dimension,))
    control = {
        "spc_observations": [dict(s) for s in (spc_status or [])],
        "calibration": dict(calibration) if calibration else None,
        "in_control": all(
            not (s.get("rule_violated")) for s in (spc_status or [])
        ),
    }

    # Persist to pi_dmaic_log
    try:
        conn.execute("""
            INSERT INTO pi_dmaic_log
                (dimension, define_json, measure_json, analyze_json, improve_json, control_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            dimension,
            json.dumps(define), json.dumps(measure), json.dumps(analyze),
            json.dumps(improve), json.dumps(control),
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error):
        pass

    return {
        "dimension": dimension,
        "define": define,
        "measure": measure,
        "analyze": analyze,
        "improve": improve,
        "control": control,
    }


def compute_cycle_times(conn) -> dict:
    """Lean cycle time analysis for finding lifecycle.

    Measures time between stages: created → first recommendation → implementation → verification → resolution.
    Returns {mean_days, p95_days, bottleneck_stage, bottleneck_pct, per_stage}.
    """
    # Get resolved findings with timestamps
    resolved = _safe_query_all(conn, """
        SELECT pf.id, pf.created_at,
               pf.resolved_at,
               julianday(pf.resolved_at) - julianday(pf.created_at) as total_days
        FROM pi_finding pf
        WHERE pf.resolved_at IS NOT NULL
          AND pf.created_at IS NOT NULL
    """)

    if not resolved:
        return {"mean_days": None, "p95_days": None, "bottleneck_stage": None,
                "bottleneck_pct": None, "per_stage": {}}

    total_days_list = [r["total_days"] for r in resolved if r["total_days"] is not None]
    if not total_days_list:
        return {"mean_days": None, "p95_days": None, "bottleneck_stage": None,
                "bottleneck_pct": None, "per_stage": {}}

    total_days_list.sort()
    mean_days = round(sum(total_days_list) / len(total_days_list), 1)
    p95_idx = int(len(total_days_list) * 0.95)
    p95_days = round(total_days_list[min(p95_idx, len(total_days_list) - 1)], 1)

    # Per-stage timing: measure time spent in each status
    stage_times = {}
    for status in ["investigating", "diagnosed", "recommended", "implemented", "verified"]:
        # Count findings that passed through this stage and avg time in it
        count = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_finding
            WHERE resolved_at IS NOT NULL
              AND status != 'rejected'
        """)
        stage_times[status] = {"avg_days": None, "count": count or 0}

    # Estimate stage durations from recommendation outcomes
    rec_time = _safe_query(conn, """
        SELECT AVG(julianday(ro.created_at) - julianday(pf.created_at)) as avg_to_rec
        FROM pi_recommendation_outcome ro
        JOIN pi_finding pf ON ro.finding_id = pf.id
    """)
    verify_time = _safe_query(conn, """
        SELECT AVG(julianday(ro.verified_at) - julianday(ro.created_at)) as avg_to_verify
        FROM pi_recommendation_outcome ro
        WHERE ro.verified_at IS NOT NULL
    """)

    stages = {}
    to_rec = (rec_time["avg_to_rec"] if rec_time and rec_time["avg_to_rec"] else None)
    to_verify = (verify_time["avg_to_verify"] if verify_time and verify_time["avg_to_verify"] else None)

    if to_rec is not None:
        stages["investigation_to_recommendation"] = round(to_rec, 1)
    if to_verify is not None:
        stages["recommendation_to_verification"] = round(to_verify, 1)
    if to_rec is not None and to_verify is not None and mean_days:
        remaining = mean_days - to_rec - to_verify
        stages["verification_to_resolution"] = round(max(0, remaining), 1)

    # Identify bottleneck
    bottleneck_stage = None
    bottleneck_pct = None
    if stages:
        bottleneck_stage = max(stages, key=stages.get)
        bottleneck_pct = round(stages[bottleneck_stage] / mean_days * 100, 1) if mean_days > 0 else None

    return {
        "mean_days": mean_days,
        "p95_days": p95_days,
        "bottleneck_stage": bottleneck_stage,
        "bottleneck_pct": bottleneck_pct,
        "per_stage": stages,
        "total_resolved": len(total_days_list),
    }


def _save_audit(conn, overall_grade, overall_score_val, dimension_scores, findings):
    """Persist audit results for trending."""
    try:
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        high = sum(1 for f in findings if f.get("severity") == "high")
        conn.execute(
            """INSERT INTO product_audit
               (overall_grade, overall_score, dimension_scores, findings_json,
                findings_count, critical_count, high_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (overall_grade, overall_score_val,
             json.dumps(dimension_scores),
             json.dumps(findings),
             len(findings), critical, high),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("product_audit table not yet created, skipping save")


def _assess_data_confidence(conn) -> dict:
    """Assess data availability for each dimension. Returns {dimension: confidence_level}."""
    confidence = {}

    total_users = _safe_scalar(conn, "SELECT COUNT(*) FROM user")
    total_sessions = _safe_scalar(conn, "SELECT COUNT(*) FROM session_log")
    total_reviews = _safe_scalar(conn, "SELECT COUNT(*) FROM review_event")
    total_events = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_event WHERE created_at >= datetime('now', '-7 days')
    """)
    total_requests = _safe_scalar(conn, """
        SELECT COUNT(*) FROM request_timing WHERE recorded_at >= datetime('now', '-7 days')
    """)

    # Each dimension needs specific data to be meaningful
    for dim in ["profitability", "retention", "onboarding", "marketing"]:
        if total_users >= 20:
            confidence[dim] = "high"
        elif total_users >= 5:
            confidence[dim] = "medium"
        elif total_users > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["ux", "flow", "engagement"]:
        if total_sessions >= 50:
            confidence[dim] = "high"
        elif total_sessions >= 10:
            confidence[dim] = "medium"
        elif total_sessions > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["drill_quality", "content"]:
        if total_reviews >= 200:
            confidence[dim] = "high"
        elif total_reviews >= 50:
            confidence[dim] = "medium"
        elif total_reviews > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["frustration", "copy"]:
        if total_events >= 100:
            confidence[dim] = "high"
        elif total_events >= 20:
            confidence[dim] = "medium"
        elif total_events > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["timing", "engineering"]:
        if total_requests >= 100:
            confidence[dim] = "high"
        elif total_requests >= 30:
            confidence[dim] = "medium"
        elif total_requests > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["ui", "platform"]:
        # Needs both sessions and client errors
        errors = _safe_scalar(conn, "SELECT COUNT(*) FROM client_error_log WHERE timestamp >= datetime('now', '-7 days')")
        if (total_sessions or 0) >= 20 and (errors or 0) >= 5:
            confidence[dim] = "high"
        elif (total_sessions or 0) >= 5:
            confidence[dim] = "medium"
        elif (total_sessions or 0) > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["security"]:
        security_events = _safe_scalar(conn, "SELECT COUNT(*) FROM security_audit_log")
        if (security_events or 0) >= 20:
            confidence[dim] = "high"
        elif (security_events or 0) >= 5:
            confidence[dim] = "medium"
        elif (security_events or 0) > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["pm"]:
        if total_reviews >= 50 and total_users >= 5:
            confidence[dim] = "high"
        elif total_users >= 3:
            confidence[dim] = "medium"
        else:
            confidence[dim] = "low"

    for dim in ["competitive"]:
        content_count = _safe_scalar(conn, "SELECT COUNT(*) FROM content_item")
        if (content_count or 0) >= 50:
            confidence[dim] = "high"
        elif (content_count or 0) > 0:
            confidence[dim] = "medium"
        else:
            confidence[dim] = "none"

    # New domain-specific dimensions
    for dim in ["srs_funnel", "error_taxonomy", "cross_modality", "curriculum"]:
        if total_reviews >= 200:
            confidence[dim] = "high"
        elif total_reviews >= 50:
            confidence[dim] = "medium"
        elif total_reviews > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["hsk_cliff"]:
        content_count = _safe_scalar(conn, "SELECT COUNT(*) FROM content_item")
        if total_reviews >= 200 and (content_count or 0) >= 50:
            confidence[dim] = "high"
        elif total_reviews >= 50:
            confidence[dim] = "medium"
        elif total_reviews > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["tone_phonology"]:
        recordings = _safe_scalar(conn, "SELECT COUNT(*) FROM audio_recording")
        if (recordings or 0) >= 50:
            confidence[dim] = "high"
        elif (recordings or 0) >= 10:
            confidence[dim] = "medium"
        elif (recordings or 0) > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["scheduler_audit"]:
        if total_sessions >= 50:
            confidence[dim] = "high"
        elif total_sessions >= 10:
            confidence[dim] = "medium"
        elif total_sessions > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    for dim in ["encounter_loop"]:
        encounters = _safe_scalar(conn, "SELECT COUNT(*) FROM vocab_encounter")
        if (encounters or 0) >= 50:
            confidence[dim] = "high"
        elif (encounters or 0) >= 10:
            confidence[dim] = "medium"
        elif (encounters or 0) > 0:
            confidence[dim] = "low"
        else:
            confidence[dim] = "none"

    # Code-inspection dimensions: confidence is based on whether analyzers
    # actually found something.  If a code-inspection dimension has 0 findings,
    # confidence should be "low" (not "high") — 0 findings means "we might not
    # be looking hard enough", not "everything is perfect".
    _CODE_INSPECTION_DIMS = {
        "visual_design", "animation", "sound_design", "copywriting",
        "branding", "mobile_perf", "behavioral_econ", "strategic",
        "genai", "agentic", "genai_governance", "cross_platform",
    }
    for dim in _CODE_INSPECTION_DIMS:
        if dim not in confidence:
            # These dimensions rely on static code analyzers, not user data.
            # Default to "medium" — they produce findings from code inspection.
            confidence[dim] = "medium"

    return confidence


def _synthesize(findings: list[dict], dimension_scores: dict = None, data_confidence: dict = None) -> dict:
    """Cross-dimension correlation, root cause analysis, and priority stack-ranking.

    Correlations are computed from co-occurrence patterns, not hardcoded rules.
    """
    synthesis = {
        "correlations": [],
        "root_causes": [],
        "top_5": [],
        "summary": "",
        "data_gaps": [],
    }

    # Flag dimensions with insufficient data
    no_data_dims = []
    if data_confidence:
        no_data_dims = [dim for dim, conf in data_confidence.items() if conf in ("none", "low")]
        if no_data_dims:
            synthesis["data_gaps"] = no_data_dims
            synthesis["correlations"].append(
                f"Insufficient data for confident analysis in: {', '.join(sorted(no_data_dims))}. "
                "Grades for these dimensions are capped at B — cannot claim health without evidence."
            )

    if not findings:
        if no_data_dims:
            synthesis["summary"] = (
                f"No findings detected, but {len(no_data_dims)} dimensions lack sufficient data for analysis. "
                "This is not a clean bill of health — it means the product is under-instrumented."
            )
        else:
            synthesis["summary"] = "No findings across all dimensions with sufficient data. Product is healthy."
        return synthesis

    # ── Computed Correlations ──
    # Build co-occurrence matrix: which dimensions' findings share files?
    dims_with_findings = {f["dimension"] for f in findings}
    by_dim = {}
    for f in findings:
        by_dim.setdefault(f["dimension"], []).append(f)

    # File-based co-occurrence: dimensions that share the same hot files
    dim_files = {}
    for f in findings:
        dim = f.get("dimension", "unknown")
        for filepath in f.get("files", []):
            dim_files.setdefault(filepath, set()).add(dim)
    # Find files touched by multiple dimensions
    shared_files = {f: dims for f, dims in dim_files.items() if len(dims) >= 2}
    seen_pairs = set()
    for filepath, dims in shared_files.items():
        dims_list = sorted(dims)
        for i in range(len(dims_list)):
            for j in range(i + 1, len(dims_list)):
                pair = (dims_list[i], dims_list[j])
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    # Count shared findings
                    shared_count = sum(1 for f in findings
                                       if f.get("dimension") in pair and filepath in f.get("files", []))
                    if shared_count >= 2:
                        synthesis["correlations"].append(
                            f"{pair[0]} and {pair[1]} share findings in {filepath} — "
                            f"fixing {filepath} may resolve issues in both dimensions."
                        )

    # Severity-based correlations: if multiple high-severity dimensions share a causal pattern
    critical_dims = [dim for dim, fs in by_dim.items()
                     if any(f.get("severity") == "critical" for f in fs)]
    if len(critical_dims) >= 2:
        synthesis["correlations"].append(
            f"Critical issues span {len(critical_dims)} dimensions ({', '.join(critical_dims)}). "
            "This suggests a systemic problem, not isolated bugs."
        )

    # Specific pattern: retention + ux problems compound
    if "retention" in dims_with_findings and "ux" in dims_with_findings:
        retention_severity = max(_SEVERITY_ORDER.get(f.get("severity"), 9) for f in by_dim.get("retention", []))
        ux_severity = max(_SEVERITY_ORDER.get(f.get("severity"), 9) for f in by_dim.get("ux", []))
        if retention_severity <= 1 and ux_severity <= 1:  # Both have high+ findings
            synthesis["correlations"].append(
                "UX and retention problems are compounding — poor UX drives churn, churn masks UX improvements. "
                "Fix UX first to get clean retention signal."
            )

    # ── Root Cause Grouping ──
    # Group by file, but also check if findings in the same file are actually related
    file_counts = {}
    for f in findings:
        for filepath in f.get("files", []):
            file_counts[filepath] = file_counts.get(filepath, 0) + 1
    hot_files = [(f, c) for f, c in file_counts.items() if c >= 3]
    hot_files.sort(key=lambda x: -x[1])
    for filepath, count in hot_files[:3]:
        related = [f for f in findings if filepath in f.get("files", [])]
        related_dims = {f["dimension"] for f in related}
        synthesis["root_causes"].append({
            "file": filepath,
            "finding_count": count,
            "dimensions": sorted(related_dims),
            "examples": [f["title"] for f in related[:3]],
        })

    # ── Top 5 Priority ──
    # Score: severity × dimension weight × actionability
    dimension_weight = {dim: 1.5 if dim in _WEIGHTED_DIMENSIONS else 1.0
                        for dim in dims_with_findings}
    severity_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    scored = []
    for f in findings:
        sev = severity_score.get(f.get("severity", "low"), 1)
        dim_w = dimension_weight.get(f.get("dimension", "unknown"), 1.0)
        # Actionability bonus: findings with specific files and prompts are more actionable
        action_bonus = 1.0
        if f.get("files"):
            action_bonus += 0.2
        if f.get("claude_prompt") and len(f.get("claude_prompt", "")) > 100:
            action_bonus += 0.1
        scored.append((sev * dim_w * action_bonus, f))
    scored.sort(key=lambda x: -x[0])
    synthesis["top_5"] = [
        {"title": f["title"], "severity": f["severity"], "dimension": f["dimension"],
         "score": round(s, 1)}
        for s, f in scored[:5]
    ]

    # ── Human Reviewer Summary ──
    critical_count = sum(1 for f in findings if f.get("severity") == "critical")
    high_count = sum(1 for f in findings if f.get("severity") == "high")
    medium_count = sum(1 for f in findings if f.get("severity") == "medium")

    # Build a real summary, not a template fill
    parts = []

    # Health assessment
    if critical_count > 0:
        parts.append(f"{critical_count} critical issue{'s' if critical_count > 1 else ''} requiring immediate attention")
    if high_count > 0:
        parts.append(f"{high_count} high-priority improvement{'s' if high_count > 1 else ''}")
    if medium_count > 0:
        parts.append(f"{medium_count} medium-priority item{'s' if medium_count > 1 else ''}")

    # Data coverage
    if data_confidence:
        confident_dims = sum(1 for c in data_confidence.values() if c == "high")
        total_dims = len(data_confidence)
        if confident_dims < total_dims:
            parts.append(f"only {confident_dims}/{total_dims} dimensions have sufficient data for confident grading")

    summary = f"Across {len(dims_with_findings)} dimensions with findings: {'; '.join(parts)}."

    # What to fix first
    if synthesis["top_5"]:
        top = synthesis["top_5"][0]
        summary += f" Start with: {top['title']} ({top['severity']}, {top['dimension']})."

    # Root cause insight
    if synthesis["root_causes"]:
        rc = synthesis["root_causes"][0]
        summary += f" Hot spot: {rc['file']} appears in {rc['finding_count']} findings across {', '.join(rc['dimensions'])}."

    synthesis["summary"] = summary
    return synthesis
