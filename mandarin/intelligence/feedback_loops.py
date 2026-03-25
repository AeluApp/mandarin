"""Product Intelligence — Feedback loops: outcome tracking, threshold calibration,
prediction ledger, self-correction.

Closes the loop between recommendations and results. Tracks whether
implemented recommendations actually improved the target metrics.
Self-calibrates thresholds based on historical false positive rates.
Emits falsifiable predictions and scores them against actual outcomes.
"""

import json
import logging
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone, UTC
from uuid import uuid4

from ._base import (
    _VERIFICATION_WINDOWS,
    _finding, _safe_query, _safe_query_all, _safe_scalar,
)

logger = logging.getLogger(__name__)


def record_recommendation_outcome(
    conn, finding_id: int, action_type: str, description: str,
    files_changed: list = None, metric_before: dict = None,
) -> int:
    """Record that a finding's recommendation was acted on.

    Returns the outcome ID, or -1 on failure.
    """
    try:
        cursor = conn.execute("""
            INSERT INTO pi_recommendation_outcome
                (finding_id, action_type, action_description, files_changed, metric_before)
            VALUES (?, ?, ?, ?, ?)
        """, (
            finding_id, action_type, description,
            json.dumps(files_changed) if files_changed else None,
            json.dumps(metric_before) if metric_before else None,
        ))
        conn.commit()
        return cursor.lastrowid
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to record outcome: %s", e)
        return -1


def verify_recommendation_outcomes(conn) -> list[dict]:
    """For outcomes without metric_after that are >7 days old, attempt to verify.

    Checks the current state of the metric and computes delta.
    Returns list of verification results.
    """
    # Use dimension-specific verification windows instead of hardcoded 7 days
    unverified = _safe_query_all(conn, """
        SELECT ro.id, ro.finding_id, ro.metric_before, ro.created_at,
               pf.dimension, pf.metric_name
        FROM pi_recommendation_outcome ro
        JOIN pi_finding pf ON ro.finding_id = pf.id
        WHERE ro.metric_after IS NULL
          AND ro.verified_at IS NULL
    """)
    # Filter by dimension-specific window
    filtered = []
    for row in (unverified or []):
        window_days = _VERIFICATION_WINDOWS.get(row["dimension"], 7)
        import datetime as _dt
        created = row["created_at"]
        if created:
            try:
                # Check if enough time has passed for this dimension
                created_dt = _dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
                now = _dt.datetime.now(_dt.UTC)
                if (now - created_dt).days >= window_days:
                    filtered.append(row)
            except (ValueError, TypeError):
                filtered.append(row)  # fallback: include it
    unverified = filtered

    results = []
    for row in (unverified or []):
        metric_before = None
        if row["metric_before"]:
            try:
                metric_before = json.loads(row["metric_before"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Try to measure current metric value based on dimension
        current_value = _measure_current_metric(conn, row["dimension"], row["metric_name"])

        if current_value is not None and metric_before:
            before_val = metric_before.get("value", 0)
            if before_val != 0:
                delta_pct = round((current_value - before_val) / abs(before_val) * 100, 1)
            else:
                delta_pct = 0.0

            # Determine effectiveness
            # For most metrics, higher is better (retention, completion rate)
            # For error metrics, lower is better
            error_dimensions = {"engineering", "frustration", "security"}
            if row["dimension"] in error_dimensions:
                effective = 1 if delta_pct < -5 else (-1 if delta_pct > 5 else 0)
            else:
                effective = 1 if delta_pct > 5 else (-1 if delta_pct < -5 else 0)

            try:
                conn.execute("""
                    UPDATE pi_recommendation_outcome
                    SET metric_after = ?,
                        verified_at = datetime('now'),
                        delta_pct = ?,
                        effective = ?
                    WHERE id = ?
                """, (
                    json.dumps({"value": current_value}),
                    delta_pct, effective, row["id"],
                ))
                conn.commit()
                results.append({
                    "outcome_id": row["id"],
                    "finding_id": row["finding_id"],
                    "delta_pct": delta_pct,
                    "effective": effective,
                })
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

    return results


def _measure_current_metric(conn, dimension: str, metric_name: str):
    """Measure the current value of a metric based on dimension.

    Returns a float or None if unmeasurable. Covers all 48+ dimensions.
    """
    metric_queries = {
        "retention": "SELECT COUNT(DISTINCT user_id) * 100.0 / NULLIF((SELECT COUNT(*) FROM user WHERE created_at <= datetime('now', '-7 days')), 0) FROM session_log s JOIN user u ON s.user_id = u.id WHERE u.created_at <= datetime('now', '-7 days') AND s.started_at >= datetime(u.created_at, '+7 days')",
        "ux": "SELECT COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM session_log), 0) FROM session_log WHERE items_completed > 0 AND items_completed >= items_planned * 0.8",
        "engineering": "SELECT COUNT(*) FROM crash_log WHERE timestamp >= datetime('now', '-7 days') AND request_path NOT IN ('/unhandled', '/unhandled/')",
        "frustration": "SELECT COUNT(*) FROM client_event WHERE category = 'ux' AND event = 'rage_click' AND created_at >= datetime('now', '-7 days')",
        "profitability": "SELECT COUNT(CASE WHEN subscription_tier='paid' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) FROM user",
        "onboarding": "SELECT COUNT(DISTINCT CASE WHEN s.id IS NOT NULL THEN u.id END) * 100.0 / NULLIF(COUNT(DISTINCT u.id), 0) FROM user u LEFT JOIN session_log s ON u.id = s.user_id WHERE u.created_at >= datetime('now', '-30 days')",
        "engagement": "SELECT COUNT(DISTINCT user_id) * 100.0 / NULLIF((SELECT COUNT(*) FROM user), 0) FROM session_log WHERE started_at >= datetime('now', '-7 days')",
        "security": "SELECT COUNT(*) FROM security_audit_log WHERE created_at >= datetime('now', '-7 days')",
        "drill_quality": "SELECT AVG(CASE WHEN correct=1 THEN 100.0 ELSE 0.0 END) FROM review_event WHERE created_at >= datetime('now', '-14 days')",
        "srs_funnel": "SELECT COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM progress), 0) FROM progress WHERE mastery_stage IN ('stable')",
        "flow": "SELECT AVG(CAST(items_completed AS REAL) / NULLIF(items_planned, 0)) * 100 FROM session_log WHERE items_planned > 0 AND started_at >= datetime('now', '-14 days')",
        "curriculum": "SELECT COUNT(DISTINCT grammar_point_id) * 100.0 / NULLIF((SELECT COUNT(*) FROM grammar_point), 0) FROM grammar_progress",
        "tone_phonology": "SELECT AVG(CASE WHEN tone_scores_json IS NOT NULL THEN 1 ELSE 0 END) * 100 FROM audio_recording WHERE created_at >= datetime('now', '-14 days')",
        "scheduler_audit": "SELECT AVG(CAST(items_completed AS REAL) / NULLIF(items_planned, 0)) * 100 FROM session_log WHERE items_planned > 0 AND started_at >= datetime('now', '-30 days')",
        "platform": "SELECT COUNT(DISTINCT client_platform) FROM session_log WHERE started_at >= datetime('now', '-14 days')",
        "encounter_loop": "SELECT COUNT(DISTINCT ve.content_item_id) * 100.0 / NULLIF(COUNT(DISTINCT ve.id), 0) FROM vocab_encounter ve JOIN review_event re ON ve.content_item_id = re.content_item_id AND re.created_at > ve.created_at WHERE ve.looked_up = 1",
        "content": "SELECT COUNT(*) FROM content_item",
        "pm": "SELECT COUNT(*) FROM improvement_log WHERE status = 'proposed' AND created_at <= datetime('now', '-30 days')",
        "competitive": "SELECT COUNT(*) FROM content_item WHERE hsk_level IS NOT NULL",
        "marketing": "SELECT COUNT(DISTINCT u.id) FROM user u WHERE u.created_at >= datetime('now', '-30 days')",
        "copy": "SELECT COUNT(*) FROM client_event WHERE category = 'copy' AND created_at >= datetime('now', '-14 days')",
        # ── Additional dimensions ──────────────────────────────────────
        "visual_vibe": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'visual_vibe' AND status NOT IN ('resolved', 'rejected')",
        "copy_drift": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'copy_drift' AND status NOT IN ('resolved', 'rejected')",
        "runtime_health": "SELECT COUNT(*) FROM crash_log WHERE timestamp >= datetime('now', '-7 days')",
        "tonal_vibe": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'tonal_vibe' AND status NOT IN ('resolved', 'rejected')",
        "feature_usage": "SELECT COUNT(DISTINCT event) FROM client_event WHERE created_at >= datetime('now', '-14 days')",
        "engineering_health": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'engineering_health' AND status NOT IN ('resolved', 'rejected')",
        "strategic": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'strategic' AND status NOT IN ('resolved', 'rejected')",
        "governance": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'governance' AND status NOT IN ('resolved', 'rejected')",
        "data_quality": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'data_quality' AND status NOT IN ('resolved', 'rejected')",
        "genai_governance": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'genai_governance' AND status NOT IN ('resolved', 'rejected')",
        "memory_model": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'memory_model' AND status NOT IN ('resolved', 'rejected')",
        "learner_model": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'learner_model' AND status NOT IN ('resolved', 'rejected')",
        "genai": "SELECT COUNT(*) FROM crash_log WHERE timestamp >= datetime('now', '-7 days') AND request_path LIKE '%/ai/%'",
        "rag": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'rag' AND status NOT IN ('resolved', 'rejected')",
        "native_speaker_validation": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'native_speaker_validation' AND status NOT IN ('resolved', 'rejected')",
        "input_layer": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'input_layer' AND status NOT IN ('resolved', 'rejected')",
        "accountability": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'accountability' AND status NOT IN ('resolved', 'rejected')",
        "commercial": "SELECT COUNT(CASE WHEN subscription_tier = 'paid' THEN 1 END) FROM user",
        "agentic": "SELECT COUNT(*) FROM pi_work_order WHERE status IN ('succeeded') AND created_at >= datetime('now', '-30 days')",
        "cross_platform": "SELECT COUNT(DISTINCT client_platform) FROM session_log WHERE started_at >= datetime('now', '-14 days')",
        "behavioral_econ": "SELECT COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM session_log WHERE started_at >= datetime('now', '-14 days')), 0) FROM session_log WHERE items_completed > 0 AND started_at >= datetime('now', '-14 days')",
        "growth_accounting": "SELECT COUNT(DISTINCT u.id) FROM user u WHERE u.created_at >= datetime('now', '-30 days')",
        "journey": "SELECT COUNT(DISTINCT CASE WHEN s.id IS NOT NULL THEN u.id END) * 100.0 / NULLIF(COUNT(DISTINCT u.id), 0) FROM user u LEFT JOIN session_log s ON u.id = s.user_id WHERE u.created_at >= datetime('now', '-30 days')",
        "brand_health": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'brand_health' AND status NOT IN ('resolved', 'rejected')",
        "learning_science": "SELECT AVG(CASE WHEN correct = 1 THEN 100.0 ELSE 0.0 END) FROM review_event WHERE created_at >= datetime('now', '-14 days')",
        "output_production": "SELECT COUNT(*) FROM review_event WHERE drill_type IN ('production', 'speaking', 'writing') AND created_at >= datetime('now', '-14 days')",
        "tutor_integration": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'tutor_integration' AND status NOT IN ('resolved', 'rejected')",
        "tone_quality": "SELECT AVG(CASE WHEN tone_scores_json IS NOT NULL THEN 1 ELSE 0 END) * 100 FROM audio_recording WHERE created_at >= datetime('now', '-14 days')",
        "timing": "SELECT AVG(julianday(started_at, '+' || CAST(duration_seconds AS TEXT) || ' seconds') - julianday(started_at)) * 86400 FROM session_log WHERE started_at >= datetime('now', '-14 days') AND duration_seconds IS NOT NULL",
        "ui": "SELECT COUNT(*) FROM pi_finding WHERE dimension = 'ui' AND status NOT IN ('resolved', 'rejected')",
    }

    sql = metric_queries.get(dimension)
    if sql:
        return _safe_scalar(conn, sql)
    return None


def calibrate_thresholds(conn) -> list[dict]:
    """Self-calibrate thresholds based on historical finding accuracy.

    For each dimension:
    - Count findings that were eventually verified vs rejected
    - If false positive rate > 25%: tighten threshold by 20%
    - Persist calibrations to pi_threshold_calibration

    Returns list of calibration adjustments.
    """
    adjustments = []

    dim_stats = _safe_query_all(conn, """
        SELECT dimension,
               COUNT(*) as total,
               SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
               SUM(CASE WHEN status IN ('verified','resolved') THEN 1 ELSE 0 END) as verified
        FROM pi_finding
        WHERE created_at >= datetime('now', '-180 days')
        GROUP BY dimension
        HAVING total >= 5
    """)

    for row in (dim_stats or []):
        total = row["total"]
        rejected = row["rejected"] or 0
        verified = row["verified"] or 0
        fpr = rejected / total if total > 0 else 0

        # Look up current threshold
        existing = _safe_query(conn, """
            SELECT threshold_value FROM pi_threshold_calibration
            WHERE metric_name = ?
        """, (row["dimension"],))
        prior_threshold = existing["threshold_value"] if existing else None

        new_threshold = None
        notes = ""

        if fpr > 0.25:
            # Tighten by 20% (make it harder to trigger)
            new_threshold = (prior_threshold or 1.0) * 1.2
            notes = f"Auto-calibrated: FPR was {round(fpr*100,1)}%, tightened threshold by 20%"
        elif fpr < 0.10 and total >= 10 and verified > 0:
            # Bidirectional: loosen by ~10% when FPR is very low
            new_threshold = (prior_threshold or 1.0) / 1.1
            notes = f"Auto-calibrated: FPR was {round(fpr*100,1)}%, loosened threshold by ~10%"

        if new_threshold is not None:
            try:
                conn.execute("""
                    INSERT INTO pi_threshold_calibration
                        (metric_name, threshold_value, sample_size,
                         false_positive_rate, false_negative_rate,
                         prior_threshold, notes)
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                    ON CONFLICT(metric_name) DO UPDATE SET
                        threshold_value = excluded.threshold_value,
                        calibrated_at = datetime('now'),
                        sample_size = excluded.sample_size,
                        false_positive_rate = excluded.false_positive_rate,
                        prior_threshold = pi_threshold_calibration.threshold_value,
                        notes = excluded.notes
                """, (
                    row["dimension"], new_threshold, total,
                    round(fpr * 100, 1), prior_threshold, notes,
                ))
                conn.commit()
                adjustments.append({
                    "dimension": row["dimension"],
                    "prior": prior_threshold,
                    "new": new_threshold,
                    "fpr": round(fpr * 100, 1),
                    "sample_size": total,
                    "direction": "tightened" if fpr > 0.25 else "loosened",
                })
            except (sqlite3.OperationalError, sqlite3.Error) as e:
                logger.debug("Threshold calibration failed: %s", e)

    return adjustments


def get_calibrated_threshold(conn, metric_name: str, default: float = 1.0) -> float:
    """Look up calibrated threshold value, or return default."""
    row = _safe_query(conn, """
        SELECT threshold_value FROM pi_threshold_calibration
        WHERE metric_name = ?
    """, (metric_name,))
    if row and row["threshold_value"] is not None:
        return row["threshold_value"]
    return default


def analyze_spc_closure(conn) -> list[dict]:
    """Check SPC violations via spc_observation table and cross-reference with work_items."""
    findings = []

    # Direct SPC observation queries: group by chart_type, find OOC points
    spc_charts = _safe_query_all(conn, """
        SELECT chart_type,
               COUNT(*) as total_obs,
               SUM(CASE WHEN rule_violated IS NOT NULL THEN 1 ELSE 0 END) as ooc_count,
               MAX(observed_at) as latest
        FROM spc_observation
        WHERE observed_at >= datetime('now', '-30 days')
        GROUP BY chart_type
    """)

    for chart in (spc_charts or []):
        if (chart["ooc_count"] or 0) == 0:
            continue

        # Check if there's a work_item addressing this chart
        work_item = _safe_query(conn, """
            SELECT id, title, status FROM work_item
            WHERE title LIKE '%' || ? || '%'
              AND status NOT IN ('done', 'cancelled')
            ORDER BY created_at DESC LIMIT 1
        """, (chart["chart_type"],))

        # Check if recent observations returned to control
        recent_in_control = _safe_scalar(conn, """
            SELECT COUNT(*) FROM spc_observation
            WHERE chart_type = ?
              AND rule_violated IS NULL
              AND observed_at = (SELECT MAX(observed_at) FROM spc_observation WHERE chart_type = ?)
        """, (chart["chart_type"], chart["chart_type"]))

        status = "returned to control" if recent_in_control else "still out of control"
        has_work = f"work_item #{work_item['id']} ({work_item['status']})" if work_item else "no work_item"

        if not recent_in_control:
            findings.append(_finding(
                "pm", "medium",
                f"SPC chart '{chart['chart_type']}': {chart['ooc_count']} OOC points, {status}",
                f"Chart '{chart['chart_type']}' has {chart['ooc_count']}/{chart['total_obs']} "
                f"out-of-control observations. Status: {status}. Tracked by: {has_work}.",
                "Investigate root cause and verify corrective action effectiveness.",
                f"SPC: {chart['chart_type']} — {chart['ooc_count']} violations. {has_work}.",
                "SPC: unresolved violations indicate process instability",
                [],
            ))

    return findings


def analyze_experiments(conn) -> list[dict]:
    """Check experiment health: sufficient sample, conclusions, deployment."""
    findings = []

    # Running experiments with sufficient sample
    running = _safe_query_all(conn, """
        SELECT id, name, created_at, min_sample_size
        FROM experiment
        WHERE status = 'running'
    """)

    for exp in (running or []):
        exp_id = exp["id"]
        # Check sample size
        sample = _safe_scalar(conn, """
            SELECT COUNT(*) FROM experiment_assignment WHERE experiment_id = ?
        """, (exp_id,))

        min_needed = exp["min_sample_size"] or 100
        if sample and sample >= min_needed:
            # Welch's t-test for significance
            significance_note = ""
            variant_stats = _safe_query_all(conn, """
                SELECT ea.variant,
                       AVG(re.correct) as mean_correct,
                       COUNT(*) as n,
                       AVG(re.correct * re.correct) - AVG(re.correct) * AVG(re.correct) as variance
                FROM experiment_assignment ea
                JOIN review_event re ON ea.user_id = re.user_id
                    AND re.created_at >= ea.assigned_at
                WHERE ea.experiment_id = ?
                GROUP BY ea.variant
                HAVING n >= 10
            """, (exp_id,))
            if variant_stats and len(variant_stats) >= 2:
                v0, v1 = variant_stats[0], variant_stats[1]
                m0, m1 = v0["mean_correct"] or 0, v1["mean_correct"] or 0
                n0, n1 = v0["n"] or 1, v1["n"] or 1
                var0 = max((v0["variance"] or 0), 1e-10)
                var1 = max((v1["variance"] or 0), 1e-10)
                se = math.sqrt(var0 / n0 + var1 / n1)
                if se > 0:
                    t_stat = (m0 - m1) / se
                    # Approximate p-value using normal approximation for large samples
                    # |t| > 1.96 → p < 0.05
                    p_approx = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))
                    winner = v0["variant"] if m0 > m1 else v1["variant"]
                    if p_approx < 0.05:
                        significance_note = (
                            f" SIGNIFICANT: {winner} wins (t={round(t_stat, 2)}, "
                            f"p≈{round(p_approx, 4)}, Δ={round(abs(m0-m1)*100, 1)}pp)."
                        )
                    else:
                        significance_note = (
                            f" Not significant yet (t={round(t_stat, 2)}, p≈{round(p_approx, 4)})."
                        )

            findings.append(_finding(
                "pm", "medium",
                f"Experiment '{exp['name']}' has reached sample size ({sample}/{min_needed})",
                f"This experiment has sufficient data for analysis but is still running.{significance_note}",
                "Conclude the experiment and deploy the winner.",
                f"Experiment {exp_id} ({exp['name']}): {sample} assignments, min={min_needed}{significance_note}",
                "Process: experiments at sample size should be concluded",
                [],
            ))

    # Experiments with no conclusion after 30 days
    old_running = _safe_query_all(conn, """
        SELECT id, name, created_at FROM experiment
        WHERE status = 'running'
          AND created_at <= datetime('now', '-30 days')
    """)
    for exp in (old_running or []):
        findings.append(_finding(
            "pm", "medium",
            f"Experiment '{exp['name']}' running >30 days without conclusion",
            f"Started {exp['created_at']}. Long-running experiments waste resources.",
            "Either conclude with available data or cancel if underpowered.",
            f"Old experiment: {exp['name']} (started {exp['created_at']})",
            "Process: stale experiments indicate decision paralysis",
            [],
        ))

    return findings


def analyze_improvement_log(conn) -> list[dict]:
    """Check improvement_log for stale proposals and effectiveness."""
    findings = []

    # Stale proposals
    stale = _safe_scalar(conn, """
        SELECT COUNT(*) FROM improvement_log
        WHERE status = 'proposed'
          AND created_at <= datetime('now', '-30 days')
    """)
    if stale and stale > 0:
        findings.append(_finding(
            "pm", "medium",
            f"{stale} improvement proposals stale >30 days",
            "Proposed improvements that haven't been acted on for 30+ days.",
            "Review and either approve, apply, or archive stale proposals.",
            f"{stale} stale improvement proposals",
            "Process: stale proposals = decision bottleneck",
            [],
        ))

    return findings


def measure_encounter_effectiveness(conn) -> dict:
    """Compare mastery trajectory: encounter-sourced items vs organic.

    Returns {boosted_reps_to_stable, control_reps_to_stable, lift_pct}.
    """
    # Items from encounters that reached stable
    encounter_items = _safe_query(conn, """
        SELECT AVG(p.repetitions) as avg_reps, COUNT(*) as n
        FROM progress p
        JOIN vocab_encounter ve ON p.content_item_id = ve.content_item_id
        WHERE ve.looked_up = 1
          AND p.mastery_stage = 'stable'
    """)

    # Matched control: items NOT from encounters that reached stable
    control_items = _safe_query(conn, """
        SELECT AVG(p.repetitions) as avg_reps, COUNT(*) as n
        FROM progress p
        WHERE p.mastery_stage = 'stable'
          AND p.content_item_id NOT IN (
              SELECT content_item_id FROM vocab_encounter WHERE looked_up = 1
          )
    """)

    result = {
        "boosted_reps_to_stable": None,
        "control_reps_to_stable": None,
        "lift_pct": None,
    }

    if encounter_items and control_items:
        boosted = encounter_items["avg_reps"]
        control = control_items["avg_reps"]
        if boosted is not None and control is not None and control > 0:
            result["boosted_reps_to_stable"] = round(boosted, 1)
            result["control_reps_to_stable"] = round(control, 1)
            result["lift_pct"] = round((control - boosted) / control * 100, 1)

    return result


def get_loop_closure_summary(conn) -> dict:
    """Summary of feedback loop health.

    Returns:
        total_outcomes, verified_outcomes, closure_rate,
        effective_count, ineffective_count, neutral_count,
        calibration_count
    """
    total = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_recommendation_outcome")
    verified = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_recommendation_outcome WHERE verified_at IS NOT NULL
    """)
    effective = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_recommendation_outcome WHERE effective = 1
    """)
    ineffective = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_recommendation_outcome WHERE effective = -1
    """)
    neutral = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_recommendation_outcome WHERE effective = 0
    """)
    calibrations = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_threshold_calibration")

    return {
        "total_outcomes": total or 0,
        "verified_outcomes": verified or 0,
        "closure_rate": round((verified or 0) / (total or 1) * 100, 1),
        "effective_count": effective or 0,
        "ineffective_count": ineffective or 0,
        "neutral_count": neutral or 0,
        "calibration_count": calibrations or 0,
    }


def estimate_copq(conn) -> dict:
    """Six Sigma: Cost of Poor Quality estimation.

    Formula: sum(finding_count_by_severity × churn_probability × LTV × affected_users).
    """
    LTV = 50.0  # Lifetime value per user in dollars
    SEVERITY_CHURN = {"critical": 0.10, "high": 0.05, "medium": 0.02, "low": 0.005}

    total_users = _safe_scalar(conn, "SELECT COUNT(*) FROM user") or 1

    severity_counts = _safe_query_all(conn, """
        SELECT severity, COUNT(*) as cnt
        FROM pi_finding
        WHERE status NOT IN ('resolved', 'rejected')
        GROUP BY severity
    """)

    total_copq = 0.0
    breakdown = {}
    for row in (severity_counts or []):
        sev = row["severity"]
        count = row["cnt"] or 0
        churn_prob = SEVERITY_CHURN.get(sev, 0.01)
        cost = count * churn_prob * LTV * total_users
        total_copq += cost
        breakdown[sev] = {
            "finding_count": count,
            "churn_probability": churn_prob,
            "estimated_cost": round(cost, 2),
        }

    return {
        "total_copq": round(total_copq, 2),
        "ltv": LTV,
        "total_users": total_users,
        "breakdown": breakdown,
    }


def compute_power_analysis(conn, experiment_id: int) -> dict:
    """DoE: compute statistical power for a running experiment.

    Given baseline rate and MDE=5pp, compute required sample size.
    Reports current power and additional assignments needed.
    """
    MDE = 0.05  # minimum detectable effect = 5 percentage points
    POWER_TARGET = 0.80
    Z_ALPHA = 1.96  # two-tailed
    Z_BETA = 0.84   # 80% power

    # Get baseline rate from control variant
    baseline = _safe_query(conn, """
        SELECT AVG(re.correct) as baseline_rate, COUNT(*) as n
        FROM experiment_assignment ea
        JOIN review_event re ON ea.user_id = re.user_id
            AND re.created_at >= ea.assigned_at
        WHERE ea.experiment_id = ? AND ea.variant = 'control'
    """, (experiment_id,))

    if not baseline or baseline["baseline_rate"] is None:
        return {"available": False, "reason": "No control variant data"}

    p0 = baseline["baseline_rate"]
    p1 = p0 + MDE
    n_control = baseline["n"] or 0

    # Required sample size per arm (normal approximation)
    # n = ((Z_α√(2p̄q̄) + Z_β√(p0q0 + p1q1)) / (p1 - p0))²
    p_bar = (p0 + p1) / 2
    numerator = (Z_ALPHA * math.sqrt(2 * p_bar * (1 - p_bar)) +
                 Z_BETA * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1)))
    required_per_arm = math.ceil((numerator / MDE) ** 2) if MDE > 0 else 0

    # Current sample sizes
    total_assigned = _safe_scalar(conn, """
        SELECT COUNT(*) FROM experiment_assignment WHERE experiment_id = ?
    """, (experiment_id,))

    # Current power (approximate)
    if n_control > 0 and MDE > 0:
        se = math.sqrt(p0 * (1 - p0) / n_control + p0 * (1 - p0) / n_control)
        z_observed = MDE / se if se > 0 else 0
        current_power = 0.5 * (1 + math.erf((z_observed - Z_ALPHA) / math.sqrt(2)))
    else:
        current_power = 0.0

    additional_needed = max(0, required_per_arm * 2 - (total_assigned or 0))

    return {
        "available": True,
        "baseline_rate": round(p0, 4),
        "mde": MDE,
        "required_per_arm": required_per_arm,
        "required_total": required_per_arm * 2,
        "current_total": total_assigned or 0,
        "current_power": round(current_power, 3),
        "additional_needed": additional_needed,
        "at_target_power": current_power >= POWER_TARGET,
    }


# ── Self-Correction Layer ───────────────────────────────────────────


def _increment_measurement_failure(conn, model_id: str) -> None:
    """Increment measurement_failure_count for a model that can't measure its dimension."""
    try:
        existing = _safe_query(conn, "SELECT model_id FROM pi_model_confidence WHERE model_id = ?", (model_id,))
        if existing:
            conn.execute("""
                UPDATE pi_model_confidence
                SET measurement_failure_count = measurement_failure_count + 1,
                    last_updated = datetime('now')
                WHERE model_id = ?
            """, (model_id,))
        else:
            conn.execute("""
                INSERT INTO pi_model_confidence
                    (model_id, dimension, measurement_failure_count, last_updated)
                VALUES (?, '', 1, datetime('now'))
            """, (model_id,))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error):
        pass


def emit_prediction(conn, finding_id, model_id: str, dimension: str,
                    metric_name: str, predicted_delta: float, confidence: float):
    """Emit a falsifiable prediction at finding creation time.

    Must be called BEFORE any intervention occurs.
    Rules:
    - metric_baseline is immutable after insert (enforced by never issuing UPDATE on it)
    - verification_window_days comes from _VERIFICATION_WINDOWS — raises ValueError if missing
    - Returns prediction_id or None if metric unmeasurable
    """
    baseline = _measure_current_metric(conn, dimension, metric_name)
    if baseline is None:
        _increment_measurement_failure(conn, model_id)
        return None

    window_days = _VERIFICATION_WINDOWS.get(dimension)
    if window_days is None:
        raise ValueError(
            f"No verification window defined for dimension '{dimension}'. "
            f"Add it to _VERIFICATION_WINDOWS before emitting predictions."
        )

    prediction_id = str(uuid4())
    due_at = (datetime.now(UTC) + timedelta(days=window_days)).strftime("%Y-%m-%d %H:%M:%S")

    if predicted_delta > 0:
        claim_type = "metric_will_improve"
    elif predicted_delta < 0:
        claim_type = "metric_will_worsen"
    else:
        claim_type = "no_change"

    try:
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (prediction_id, finding_id, model_id, dimension, claim_type,
              metric_name, baseline, predicted_delta, confidence,
              window_days, due_at))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to emit prediction: %s", e)
        return None

    return prediction_id


def record_prediction_outcomes(conn) -> list[dict]:
    """Score pending predictions whose verification window has passed.

    Classification:
    - correct: direction right AND magnitude within 20%
    - directionally_correct: direction right but magnitude off
    - wrong: direction wrong
    - insufficient_data: metric unmeasurable at verification time
    - invalidated: finding was never acted on (not scored)

    Returns list of outcome dicts.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    results = []

    due = _safe_query_all(conn, """
        SELECT p.id, p.finding_id, p.model_id, p.dimension, p.metric_name,
               p.metric_baseline, p.predicted_delta, p.verification_due_at
        FROM pi_prediction_ledger p
        WHERE p.status = 'pending'
          AND p.verification_due_at <= ?
    """, (now,))

    for pred in (due or []):
        # Check if finding was acted on
        decision = _safe_query(conn, """
            SELECT decision FROM pi_decision_log
            WHERE finding_id = ?
              AND decision IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """, (pred["finding_id"],))

        # Also check if a recommendation outcome was recorded (auto_fix path)
        outcome_exists = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_recommendation_outcome
            WHERE finding_id = ?
        """, (pred["finding_id"],))

        was_acted_on = (decision is not None) or ((outcome_exists or 0) > 0)

        if not was_acted_on:
            # Never acted on — invalidate, don't score
            try:
                conn.execute("""
                    UPDATE pi_prediction_ledger SET status = 'invalidated'
                    WHERE id = ?
                """, (pred["id"],))
            except (sqlite3.OperationalError, sqlite3.Error):
                pass
            continue

        # Measure current metric
        actual = _measure_current_metric(conn, pred["dimension"], pred["metric_name"])

        if actual is None:
            outcome_class = "insufficient_data"
            actual_delta = 0.0
            direction_correct = 0
            magnitude_error = 0.0
        else:
            actual_delta = actual - pred["metric_baseline"]
            predicted = pred["predicted_delta"]

            # Direction check
            if predicted == 0:
                direction_correct = 1 if abs(actual_delta) < 1.0 else 0
            else:
                direction_correct = 1 if (actual_delta > 0) == (predicted > 0) else 0

            magnitude_error = abs(predicted - actual_delta)

            # Classification
            if predicted != 0:
                within_20pct = magnitude_error <= abs(predicted) * 0.20
            else:
                within_20pct = abs(actual_delta) < 1.0

            if direction_correct and within_20pct:
                outcome_class = "correct"
            elif direction_correct:
                outcome_class = "directionally_correct"
            else:
                outcome_class = "wrong"

        outcome_id = str(uuid4())
        try:
            conn.execute("""
                INSERT INTO pi_prediction_outcomes
                    (id, prediction_id, recorded_at, metric_actual, actual_delta,
                     direction_correct, magnitude_error, outcome_class)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (outcome_id, pred["id"], now, actual or 0,
                  actual_delta, direction_correct, magnitude_error, outcome_class))

            conn.execute("""
                UPDATE pi_prediction_ledger
                SET status = 'verified', outcome_id = ?
                WHERE id = ?
            """, (outcome_id, pred["id"]))
        except (sqlite3.OperationalError, sqlite3.Error):
            pass

        # Update model confidence (only for scored outcomes)
        _update_model_confidence(conn, pred["model_id"], pred["dimension"], outcome_class)

        results.append({
            "prediction_id": pred["id"],
            "outcome_id": outcome_id,
            "outcome_class": outcome_class,
            "actual_delta": actual_delta,
            "predicted_delta": pred["predicted_delta"],
            "direction_correct": direction_correct,
        })

    try:
        conn.commit()
    except sqlite3.Error:
        pass

    return results


def expire_stale_predictions(conn) -> int:
    """Mark predictions past their verification window that are still pending as expired.

    Expiry is not neutral — it means measurement infrastructure failed.
    Increments measurement_failure_count on the model.
    Returns count of expired predictions.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    expired = _safe_query_all(conn, """
        SELECT id, model_id, dimension FROM pi_prediction_ledger
        WHERE status = 'pending'
          AND verification_due_at <= ?
    """, (now,))

    count = 0
    for pred in (expired or []):
        try:
            conn.execute("""
                UPDATE pi_prediction_ledger SET status = 'expired'
                WHERE id = ?
            """, (pred["id"],))
            _increment_measurement_failure(conn, pred["model_id"])
            count += 1
        except (sqlite3.OperationalError, sqlite3.Error):
            pass

    try:
        conn.commit()
    except sqlite3.Error:
        pass

    return count


def _update_model_confidence(conn, model_id: str, dimension: str, outcome_class: str) -> None:
    """Update model confidence using Beta-Binomial with Laplace smoothing.

    insufficient_data doesn't count as success or failure for confidence calc.
    """
    existing = _safe_query(conn, "SELECT * FROM pi_model_confidence WHERE model_id = ?", (model_id,))

    if not existing:
        try:
            conn.execute("""
                INSERT INTO pi_model_confidence (model_id, dimension) VALUES (?, ?)
            """, (model_id, dimension))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error):
            pass
        existing = _safe_query(conn, "SELECT * FROM pi_model_confidence WHERE model_id = ?", (model_id,))
        if not existing:
            return

    correct = (existing["correct_count"] or 0) + (1 if outcome_class == "correct" else 0)
    dir_correct = (existing["directionally_correct_count"] or 0) + (1 if outcome_class == "directionally_correct" else 0)
    wrong = (existing["wrong_count"] or 0) + (1 if outcome_class == "wrong" else 0)
    insuff = (existing["insufficient_data_count"] or 0) + (1 if outcome_class == "insufficient_data" else 0)

    # Beta-Binomial with Laplace smoothing
    # insufficient_data doesn't count as success or failure
    scored_total = correct + dir_correct + wrong
    confidence = (correct + 0.5 * dir_correct + 1) / (scored_total + 2)

    try:
        conn.execute("""
            UPDATE pi_model_confidence
            SET correct_count = ?, directionally_correct_count = ?,
                wrong_count = ?, insufficient_data_count = ?,
                current_confidence = ?, last_updated = datetime('now')
            WHERE model_id = ?
        """, (correct, dir_correct, wrong, insuff, round(confidence, 4), model_id))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error):
        pass


def get_model_confidence(conn, model_id: str) -> dict:
    """Get confidence info for a model. Returns {confidence, label, scored_count}."""
    row = _safe_query(conn, "SELECT * FROM pi_model_confidence WHERE model_id = ?", (model_id,))
    if not row:
        return {"confidence": 0.5, "label": "medium", "scored_count": 0}

    scored = (row["correct_count"] or 0) + (row["directionally_correct_count"] or 0) + (row["wrong_count"] or 0)
    confidence = row["current_confidence"] or 0.5

    # Models with fewer than 5 scored outcomes always render as 'medium'
    if scored < 5:
        label = "medium"
    elif confidence >= 0.70:
        label = "high"
    elif confidence >= 0.40:
        label = "medium"
    else:
        label = "low"

    return {
        "confidence": confidence,
        "label": label,
        "scored_count": scored,
        "correct": row["correct_count"] or 0,
        "directionally_correct": row["directionally_correct_count"] or 0,
        "wrong": row["wrong_count"] or 0,
        "insufficient_data": row["insufficient_data_count"] or 0,
        "measurement_failures": row["measurement_failure_count"] or 0,
    }


def _compute_override_accuracy(conn, lookback_days: int = 30) -> dict:
    """Compute per-dimension accuracy of human overrides vs engine predictions.

    Returns {dimension: {human: count, engine: count}} where:
    - human += 1 when override was applied and prediction was wrong (human was right)
    - engine += 1 when override was applied but prediction was correct (engine was right)
    """
    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")

    overrides = _safe_query_all(conn, """
        SELECT dl.finding_id, pf.dimension,
               po.outcome_class
        FROM pi_decision_log dl
        JOIN pi_finding pf ON dl.finding_id = pf.id
        JOIN pi_prediction_ledger pl ON pl.finding_id = dl.finding_id
        JOIN pi_prediction_outcomes po ON po.prediction_id = pl.id
        WHERE dl.decision LIKE 'Override:%'
          AND dl.created_at >= ?
          AND po.outcome_class != 'insufficient_data'
    """, (cutoff,))

    by_dimension = defaultdict(lambda: {"human": 0, "engine": 0})
    for row in (overrides or []):
        dim = row["dimension"]
        if row["outcome_class"] == "wrong":
            by_dimension[dim]["human"] += 1
        else:
            by_dimension[dim]["engine"] += 1

    return dict(by_dimension)


def generate_self_audit_report(conn, lookback_days: int = 30) -> dict:
    """Generate the self-audit report — the engine looking at itself.

    Produces accurate counts, model rankings, constraint info,
    measurement health, and human override analysis.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")

    # Prediction counts
    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_prediction_ledger WHERE created_at >= ?
    """, (cutoff,))
    correct = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_prediction_ledger p
        JOIN pi_prediction_outcomes o ON o.prediction_id = p.id
        WHERE p.created_at >= ? AND o.outcome_class = 'correct'
    """, (cutoff,))
    dir_correct = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_prediction_ledger p
        JOIN pi_prediction_outcomes o ON o.prediction_id = p.id
        WHERE p.created_at >= ? AND o.outcome_class = 'directionally_correct'
    """, (cutoff,))
    wrong = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_prediction_ledger p
        JOIN pi_prediction_outcomes o ON o.prediction_id = p.id
        WHERE p.created_at >= ? AND o.outcome_class = 'wrong'
    """, (cutoff,))
    expired = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_prediction_ledger
        WHERE created_at >= ? AND status = 'expired'
    """, (cutoff,))
    invalidated = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_prediction_ledger
        WHERE created_at >= ? AND status = 'invalidated'
    """, (cutoff,))
    insuff = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_prediction_ledger p
        JOIN pi_prediction_outcomes o ON o.prediction_id = p.id
        WHERE p.created_at >= ? AND o.outcome_class = 'insufficient_data'
    """, (cutoff,))

    total = total or 0
    correct = correct or 0
    dir_correct = dir_correct or 0
    wrong = wrong or 0
    expired = expired or 0
    invalidated = invalidated or 0
    insuff = insuff or 0

    scored = correct + dir_correct + wrong
    engine_accuracy = round(correct / scored * 100, 1) if scored > 0 else None

    # Worst models
    worst_models = _safe_query_all(conn, """
        SELECT model_id, dimension, current_confidence, wrong_count
        FROM pi_model_confidence
        WHERE wrong_count > 0
        ORDER BY current_confidence ASC
        LIMIT 3
    """)
    worst = [{"model_id": m["model_id"], "dimension": m["dimension"],
              "confidence": m["current_confidence"], "wrong_count": m["wrong_count"]}
             for m in (worst_models or [])]

    # Best models
    best_models = _safe_query_all(conn, """
        SELECT model_id, dimension, current_confidence, correct_count
        FROM pi_model_confidence
        WHERE correct_count > 0
        ORDER BY current_confidence DESC
        LIMIT 3
    """)
    best = [{"model_id": m["model_id"], "dimension": m["dimension"],
             "confidence": m["current_confidence"], "correct_count": m["correct_count"]}
            for m in (best_models or [])]

    # Current constraint
    from ._synthesis import identify_system_constraint
    try:
        # Get latest dimension scores
        latest_audit = _safe_query(conn, """
            SELECT dimension_scores FROM product_audit ORDER BY run_at DESC LIMIT 1
        """)
        if latest_audit and latest_audit["dimension_scores"]:
            dim_scores = json.loads(latest_audit["dimension_scores"])
            constraint_result = identify_system_constraint(conn, dim_scores)
            current_constraint = constraint_result.get("constraint")
            constraint_confidence = constraint_result.get("marginal_improvement", 0)
        else:
            current_constraint = None
            constraint_confidence = None
    except Exception:
        current_constraint = None
        constraint_confidence = None

    # Measurement health
    measurable_count = 0
    for dim in _VERIFICATION_WINDOWS:
        val = _measure_current_metric(conn, dim, dim)
        if val is not None:
            measurable_count += 1

    high_insuff_models = _safe_query_all(conn, """
        SELECT model_id, dimension,
               insufficient_data_count * 1.0 /
                   MAX(1, correct_count + directionally_correct_count + wrong_count + insufficient_data_count) as insuff_rate
        FROM pi_model_confidence
        WHERE correct_count + directionally_correct_count + wrong_count + insufficient_data_count > 0
        HAVING insuff_rate > 0.20
    """)
    blind_spots = [{"model_id": m["model_id"], "dimension": m["dimension"],
                    "insuff_rate": round(m["insuff_rate"] * 100, 1)}
                   for m in (high_insuff_models or [])]

    # Override analysis
    override_data = _compute_override_accuracy(conn, lookback_days)
    total_overrides = sum(v["human"] + v["engine"] for v in override_data.values())
    human_correct = sum(v["human"] for v in override_data.values())
    engine_correct_in_overrides = sum(v["engine"] for v in override_data.values())
    human_override_accuracy = round(human_correct / total_overrides * 100, 1) if total_overrides > 0 else None

    human_better = [d for d, v in override_data.items() if v["human"] > v["engine"]]
    engine_better = [d for d, v in override_data.items() if v["engine"] > v["human"]]

    report = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_days": lookback_days,
        "prediction_accuracy": {
            "total": total,
            "correct": correct,
            "correct_pct": round(correct / total * 100, 1) if total > 0 else 0,
            "directionally_correct": dir_correct,
            "directionally_correct_pct": round(dir_correct / total * 100, 1) if total > 0 else 0,
            "wrong": wrong,
            "wrong_pct": round(wrong / total * 100, 1) if total > 0 else 0,
            "expired": expired,
            "expired_pct": round(expired / total * 100, 1) if total > 0 else 0,
            "invalidated": invalidated,
            "insufficient_data": insuff,
            "insufficient_data_pct": round(insuff / total * 100, 1) if total > 0 else 0,
        },
        "worst_models": worst,
        "best_models": best,
        "current_constraint": current_constraint,
        "constraint_confidence": constraint_confidence,
        "measurement_health": {
            "measurable_dimensions": measurable_count,
            "total_dimensions": len(_VERIFICATION_WINDOWS),
            "expired_predictions": expired,
            "blind_spot_models": blind_spots,
        },
        "human_override_analysis": {
            "total_overrides": total_overrides,
            "human_correct": human_correct,
            "human_correct_pct": round(human_correct / total_overrides * 100, 1) if total_overrides > 0 else None,
            "engine_correct": engine_correct_in_overrides,
            "engine_correct_pct": round(engine_correct_in_overrides / total_overrides * 100, 1) if total_overrides > 0 else None,
            "human_better_domains": human_better,
            "engine_better_domains": engine_better,
        },
        "engine_accuracy": engine_accuracy,
        "human_override_accuracy": human_override_accuracy,
    }

    # External grounding section
    try:
        from .external_grounding import get_external_grounding_summary
        report["external_grounding"] = get_external_grounding_summary(conn)
    except (ImportError, Exception):
        report["external_grounding"] = None

    # ML system health section
    try:
        report["ml_system_health"] = _collect_ml_health(conn)
    except Exception:
        report["ml_system_health"] = None

    # AI portfolio section
    try:
        from .ai_outcome import compute_ai_portfolio_verdict
        report["ai_portfolio"] = compute_ai_portfolio_verdict(conn)
    except (ImportError, Exception):
        report["ai_portfolio"] = None

    # Coverage audit section (Doc 6)
    try:
        from .coverage_audit import get_coverage_summary
        report["coverage_audit"] = get_coverage_summary(conn)
    except (ImportError, Exception):
        report["coverage_audit"] = None

    # Cross-domain constraint (Doc 6)
    try:
        from .constraint_finder import identify_cross_domain_constraint
        report["cross_domain_constraint"] = identify_cross_domain_constraint(conn)
    except (ImportError, Exception):
        report["cross_domain_constraint"] = None

    # Engagement snapshot coverage (Doc 7)
    try:
        eng_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM pi_engagement_snapshots
            WHERE snapshot_date >= date('now', '-3 days')
        """)
        active_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM session_log
            WHERE started_at >= datetime('now', '-7 days')
        """)
        report["engagement_coverage"] = {
            "snapped_users": eng_users or 0,
            "active_users": active_users or 0,
        }
    except Exception:
        report["engagement_coverage"] = None

    # Tutor integration coverage (Doc 8)
    try:
        tutor_count = _safe_scalar(conn, "SELECT COUNT(*) FROM tutor_sessions WHERE user_id = 1")
        last_tutor = _safe_scalar(conn, "SELECT MAX(session_date) FROM tutor_sessions WHERE user_id = 1")
        report["tutor_coverage"] = {"total_sessions": tutor_count or 0, "last_session": last_tutor}
    except Exception:
        report["tutor_coverage"] = None

    # Persist to pi_self_audit_report
    report_id = str(uuid4())
    try:
        conn.execute("""
            INSERT INTO pi_self_audit_report
                (id, generated_at, lookback_days, total_predictions,
                 correct_count, directionally_correct_count, wrong_count,
                 expired_count, invalidated_count, insufficient_data_count,
                 worst_models_json, best_models_json,
                 current_constraint, constraint_confidence,
                 human_override_accuracy, engine_accuracy,
                 override_domains_json, report_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id, report["generated_at"], lookback_days, total,
            correct, dir_correct, wrong, expired, invalidated, insuff,
            json.dumps(worst), json.dumps(best),
            current_constraint, constraint_confidence,
            human_override_accuracy, engine_accuracy,
            json.dumps(override_data), json.dumps(report),
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to persist self-audit report: %s", e)

    report["id"] = report_id
    return report


def _collect_ml_health(conn) -> dict:
    """Collect ML system health for the self-audit report."""
    result = {"difficulty_model": {}, "fuzzy_dedup": {}, "training_pipeline": {}}

    # Difficulty model
    try:
        from ..ml.model_store import load_model_metadata
        meta = load_model_metadata(conn, "difficulty_model")
        if meta:
            result["difficulty_model"] = {
                "status": "trained",
                "trained_at": meta.trained_at,
                "samples": meta.samples,
                "val_accuracy": meta.val_accuracy,
                "baseline_accuracy": meta.baseline_accuracy,
                "improvement": meta.improvement,
            }
        else:
            result["difficulty_model"] = {"status": "not_trained"}
    except (ImportError, Exception):
        result["difficulty_model"] = {"status": "unavailable"}

    # Difficulty predictions calibration
    try:
        cal_row = conn.execute("""
            SELECT COUNT(*) as total,
                   AVG(CASE WHEN actual_correct IS NOT NULL
                       THEN ABS(predicted_accuracy - actual_correct) END) as cal_error
            FROM pi_difficulty_predictions
            WHERE created_at >= datetime('now', '-14 days')
            AND actual_correct IS NOT NULL
        """).fetchone()
        if cal_row and (cal_row["total"] or 0) > 0:
            result["difficulty_model"]["calibration_error"] = round(cal_row["cal_error"] or 0, 3)
            result["difficulty_model"]["recent_predictions"] = cal_row["total"]
    except Exception:
        pass

    # Fuzzy dedup
    try:
        from ..ml.fuzzy_dedup import is_available
        result["fuzzy_dedup"] = {"model_loaded": is_available()}
    except (ImportError, Exception):
        result["fuzzy_dedup"] = {"model_loaded": False}

    # Last pipeline run
    try:
        last_run = conn.execute("""
            SELECT run_at, results_json FROM pi_ml_pipeline_runs
            ORDER BY run_at DESC LIMIT 1
        """).fetchone()
        if last_run:
            result["training_pipeline"] = {
                "last_run": last_run["run_at"],
            }
        else:
            result["training_pipeline"] = {"last_run": None}
    except Exception:
        result["training_pipeline"] = {"last_run": None}

    return result
