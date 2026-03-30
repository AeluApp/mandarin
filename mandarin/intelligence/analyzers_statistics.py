"""Statistics health analyzers — monitor SPC charts, DPMO trends, capability indices,
IRT calibration, retention forecasts, experiment power, segment drift, normality,
forecasting accuracy, and effect size distributions."""

import json
import logging
import math
import sqlite3

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Check 1: SPC charts in control ──────────────────────────────────

def check_spc_charts_in_control(conn):
    """Flag SPC charts with out-of-control signals in the last 7 days."""
    findings = []
    try:
        # Get distinct chart types with recent observations
        chart_types = _safe_query_all(conn,
            "SELECT DISTINCT chart_type FROM spc_observation "
            "WHERE observed_at > datetime('now', '-7 days')")

        if not chart_types:
            return findings

        from ..quality.spc import compute_control_limits, detect_out_of_control

        ooc_charts = []

        for row in chart_types:
            chart_type = row["chart_type"] if isinstance(row, dict) else row[0]
            if chart_type is None:
                continue

            # Get observations for this chart (last 30 days for limits, flag last 7)
            obs_rows = _safe_query_all(conn,
                "SELECT value, observed_at FROM spc_observation "
                "WHERE chart_type = ? "
                "AND observed_at > datetime('now', '-30 days') "
                "ORDER BY observed_at",
                (chart_type,))

            if not obs_rows or len(obs_rows) < 5:
                continue

            values = []
            for o in obs_rows:
                v = o["value"] if isinstance(o, dict) else o[0]
                if v is not None:
                    values.append(float(v))

            if len(values) < 5:
                continue

            limits = compute_control_limits(values)
            violations = detect_out_of_control(values, limits)

            if violations:
                ooc_charts.append((chart_type, len(violations)))

        if ooc_charts:
            chart_names = ", ".join(
                f"'{c}' ({n} violation{'s' if n > 1 else ''})"
                for c, n in ooc_charts
            )
            findings.append(_finding(
                "statistics", "high",
                f"{len(ooc_charts)} SPC chart(s) out of control",
                f"The following SPC charts have out-of-control signals in the "
                f"last 7 days: {chart_names}. Out-of-control signals indicate "
                f"special cause variation that needs investigation.",
                "Investigate the root cause of each out-of-control chart. "
                "Check for recent changes (deployments, content updates, "
                "user population shifts) that could explain the variation.",
                "Query spc_observation for recent values by chart_type. "
                "Run Western Electric rules. Identify which rules triggered "
                "and correlate with deployment or change logs.",
                "Process stability and early warning",
                ["mandarin/quality/spc.py",
                 "mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 2: DPMO trend ────────────────────────────────────────────

def check_dpmo_trend(conn):
    """Flag if DPMO (defects per million opportunities) is trending upward."""
    findings = []
    try:
        rows = _safe_query_all(conn,
            "SELECT value, measured_at FROM quality_metric "
            "WHERE metric_type = 'dpmo' "
            "AND measured_at > datetime('now', '-30 days') "
            "ORDER BY measured_at")

        if not rows or len(rows) < 6:
            return findings  # Need at least 6 data points for comparison

        values = []
        for r in rows:
            v = r["value"] if isinstance(r, dict) else r[0]
            if v is not None:
                values.append(float(v))

        if len(values) < 6:
            return findings

        # Compare last 3 values against the prior 3
        prior_3 = values[-6:-3]
        last_3 = values[-3:]

        prior_avg = sum(prior_3) / len(prior_3)
        last_avg = sum(last_3) / len(last_3)

        # Trending up if all of last 3 exceed all of prior 3 averages
        if all(v > prior_avg for v in last_3) and last_avg > prior_avg:
            pct_increase = ((last_avg - prior_avg) / prior_avg * 100
                           if prior_avg > 0 else 0)
            findings.append(_finding(
                "statistics", "medium",
                f"DPMO trending upward ({prior_avg:.0f} -> {last_avg:.0f})",
                f"Defects per million opportunities has been trending upward "
                f"over the last 30 days. The last 3 measurements average "
                f"{last_avg:.0f} DPMO vs {prior_avg:.0f} DPMO for the prior "
                f"3 measurements ({pct_increase:.0f}% increase). Rising DPMO "
                f"indicates quality degradation.",
                "Investigate recent changes that could introduce defects. "
                "Review content quality, drill accuracy, and system errors. "
                "Consider tightening quality gates.",
                "Query quality_metric WHERE metric_type='dpmo' ORDER BY "
                "measured_at DESC. Identify the sources of defects by "
                "correlating with content changes and error logs.",
                "Quality trend monitoring (Six Sigma DPMO)",
                ["mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 3: Capability indices ─────────────────────────────────────

def check_capability_indices(conn):
    """Flag any process capability index (Cpk) below 1.0."""
    findings = []
    try:
        rows = _safe_query_all(conn,
            "SELECT metric_type, value, measured_at FROM quality_metric "
            "WHERE metric_type LIKE 'capability%' "
            "ORDER BY measured_at DESC")

        if not rows:
            return findings

        # Get the latest value for each metric_type
        latest = {}
        for r in rows:
            mt = r["metric_type"] if isinstance(r, dict) else r[0]
            val = r["value"] if isinstance(r, dict) else r[1]
            if mt not in latest and val is not None:
                latest[mt] = float(val)

        low_cpk = [(mt, v) for mt, v in latest.items() if v < 1.0]

        if low_cpk:
            details = ", ".join(f"{mt}: {v:.2f}" for mt, v in low_cpk)
            findings.append(_finding(
                "statistics", "high",
                f"{len(low_cpk)} capability index/indices below 1.0",
                f"The following capability indices are below the 1.0 threshold: "
                f"{details}. A Cpk < 1.0 means the process is not capable of "
                f"consistently producing output within specification limits. "
                f"Defects are expected.",
                "Identify which processes have low capability. Reduce process "
                "variation (tighten controls) or widen specification limits if "
                "appropriate. Target Cpk >= 1.33 for critical processes.",
                "Query quality_metric WHERE metric_type LIKE 'capability%'. "
                "For each low-Cpk process, investigate the underlying data "
                "distribution and sources of variation.",
                "Process capability and defect prevention",
                ["mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 4: IRT calibration freshness ──────────────────────────────

def check_irt_calibration_freshness(conn):
    """Flag if >50% of content items lack IRT (Item Response Theory) calibration."""
    findings = []
    try:
        total = _safe_scalar(conn,
            "SELECT COUNT(*) FROM content_item",
            default=0)

        if total < 10:
            return findings  # Not enough items to assess

        # Handle missing column gracefully
        uncalibrated = _safe_scalar(conn,
            "SELECT COUNT(*) FROM content_item "
            "WHERE irt_difficulty IS NULL",
            default=None)

        if uncalibrated is None:
            # Column doesn't exist — all items lack calibration
            uncalibrated = total

        ratio = uncalibrated / total if total > 0 else 0

        if ratio > 0.50:
            findings.append(_finding(
                "statistics", "medium",
                f"{ratio*100:.0f}% of content items lack IRT calibration "
                f"({uncalibrated}/{total})",
                f"{uncalibrated} of {total} content items have no IRT difficulty "
                f"calibration. Without IRT parameters, adaptive scheduling "
                f"cannot optimally match item difficulty to learner ability, "
                f"leading to suboptimal learning efficiency.",
                "Run IRT calibration on items with sufficient response data. "
                "Prioritize high-frequency items. Consider using a Rasch model "
                "or 2PL model depending on data volume.",
                "Query content_item WHERE irt_difficulty IS NULL. Identify "
                "items with enough review_event data for calibration. "
                "Propose a calibration pipeline.",
                "Adaptive learning effectiveness",
                ["mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 5: Retention forecast ─────────────────────────────────────

def check_retention_forecast(conn):
    """Flag if D30 retention is below 0.30 (30%)."""
    findings = []
    try:
        # Get the most recent retention metric
        row = _safe_query(conn,
            "SELECT value, measured_at FROM quality_metric "
            "WHERE metric_type LIKE 'retention%' "
            "ORDER BY measured_at DESC LIMIT 1")

        if row is None:
            return findings

        value = row["value"] if isinstance(row, dict) else row[0]
        measured_at = row["measured_at"] if isinstance(row, dict) else row[1]

        if value is None:
            return findings

        retention = float(value)

        if retention < 0.30:
            findings.append(_finding(
                "statistics", "high",
                f"D30 retention at {retention*100:.1f}% (target: >=30%)",
                f"The most recent retention metric is {retention*100:.1f}% "
                f"(measured at {measured_at}), which is below the 30% threshold. "
                f"Low retention indicates learners are not finding sustained "
                f"value, threatening long-term viability.",
                "Investigate churn drivers: onboarding friction, content gaps, "
                "difficulty spikes, or insufficient engagement hooks. Segment "
                "by learner archetype to identify who is leaving and when.",
                "Query quality_metric WHERE metric_type LIKE 'retention%'. "
                "Cross-reference with session_log and user cohort data to "
                "identify when and why learners drop off.",
                "User retention and product-market fit",
                ["mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 6: Experiment power ───────────────────────────────────────

def check_experiment_power(conn):
    """Flag running experiments that are underpowered (low enrollment relative to time elapsed)."""
    findings = []
    try:
        # Get running experiments
        experiments = _safe_query_all(conn,
            "SELECT id, name, min_sample_size, started_at "
            "FROM experiment "
            "WHERE status = 'running' AND started_at IS NOT NULL")

        if not experiments:
            return findings

        underpowered = []

        for exp in experiments:
            if isinstance(exp, dict):
                exp_id = exp.get("id")
                name = exp.get("name", f"experiment {exp_id}")
                min_sample = exp.get("min_sample_size", 100)
                started_at = exp.get("started_at")
            else:
                exp_id = exp[0]
                name = exp[1] if len(exp) > 1 else f"experiment {exp_id}"
                min_sample = exp[2] if len(exp) > 2 else 100
                started_at = exp[3] if len(exp) > 3 else None

            if not started_at or not min_sample:
                continue

            # Get elapsed days
            elapsed = _safe_scalar(conn,
                "SELECT julianday('now') - julianday(?)",
                (started_at,), default=0)

            if elapsed is None or elapsed < 1:
                continue

            # Check if outcome_window_days column exists; default to 14 days
            outcome_window = _safe_scalar(conn,
                "SELECT outcome_window_days FROM experiment WHERE id = ?",
                (exp_id,), default=None)

            if outcome_window is None:
                outcome_window = 14  # Default window

            # Current enrollment
            current_sample = _safe_scalar(conn,
                "SELECT COUNT(DISTINCT user_id) FROM experiment_assignment "
                "WHERE experiment_id = ?",
                (exp_id,), default=0)

            # If elapsed > 50% of outcome window but sample < 50% of min
            if (elapsed > outcome_window * 0.5 and
                    current_sample < min_sample * 0.5):
                underpowered.append((
                    name, current_sample, min_sample,
                    elapsed, outcome_window
                ))

        if underpowered:
            details = ", ".join(
                f"'{n}' ({cs}/{ms} users, {ed:.0f}/{ow}d elapsed)"
                for n, cs, ms, ed, ow in underpowered[:5]
            )
            findings.append(_finding(
                "statistics", "medium",
                f"{len(underpowered)} experiment(s) underpowered",
                f"These running experiments have enrolled less than 50% of "
                f"their minimum sample size while past 50% of their outcome "
                f"window: {details}. Underpowered experiments waste time and "
                f"cannot detect meaningful effects.",
                "Consider increasing traffic allocation, extending the "
                "experiment duration, or stopping experiments that cannot "
                "reach statistical significance.",
                "Query experiment WHERE status='running'. Compare "
                "experiment_assignment counts against min_sample_size and "
                "elapsed time. Flag experiments unlikely to reach power.",
                "Experiment validity and resource efficiency",
                ["mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 7: Segment drift ─────────────────────────────────────────

def check_segment_drift(conn):
    """Flag if any learner segment has <5% or >60% of users (possible drift)."""
    findings = []
    try:
        total = _safe_scalar(conn,
            "SELECT COUNT(*) FROM user WHERE is_active = 1",
            default=0)

        if total < 10:
            return findings  # Not enough users to segment

        # Handle missing column gracefully
        segments = _safe_query_all(conn,
            "SELECT learner_segment, COUNT(*) AS cnt "
            "FROM user WHERE is_active = 1 AND learner_segment IS NOT NULL "
            "GROUP BY learner_segment")

        if not segments:
            return findings

        drifted = []
        segmented_total = 0

        for row in segments:
            seg = row["learner_segment"] if isinstance(row, dict) else row[0]
            cnt = row["cnt"] if isinstance(row, dict) else row[1]
            if seg is None or cnt is None:
                continue
            segmented_total += cnt

        if segmented_total < 10:
            return findings

        for row in segments:
            seg = row["learner_segment"] if isinstance(row, dict) else row[0]
            cnt = row["cnt"] if isinstance(row, dict) else row[1]
            if seg is None or cnt is None:
                continue

            pct = cnt / segmented_total * 100

            if pct < 5 or pct > 60:
                drifted.append((seg, cnt, pct))

        if drifted:
            details = ", ".join(
                f"'{s}': {c} users ({p:.1f}%)"
                for s, c, p in drifted
            )
            findings.append(_finding(
                "statistics", "low",
                f"Learner segment distribution may have drifted",
                f"Some learner segments have unusual representation: {details}. "
                f"Segments below 5% may be too small for meaningful analysis. "
                f"Segments above 60% may indicate classification drift or a "
                f"need to refine segmentation criteria.",
                "Review segmentation criteria and thresholds. Check if the "
                "learner population has genuinely shifted or if the "
                "classification logic needs updating.",
                "Query user WHERE learner_segment IS NOT NULL GROUP BY "
                "learner_segment. Compare current distribution against "
                "historical baselines. Propose re-segmentation if needed.",
                "Segment validity for targeted interventions",
                ["mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 8: Normality violations ───────────────────────────────────

def check_normality_violations(conn):
    """Flag SPC charts where data skewness violates normality assumptions."""
    findings = []
    try:
        chart_types = _safe_query_all(conn,
            "SELECT DISTINCT chart_type FROM spc_observation "
            "WHERE observed_at > datetime('now', '-30 days')")

        if not chart_types:
            return findings

        skewed_charts = []

        for row in chart_types:
            chart_type = row["chart_type"] if isinstance(row, dict) else row[0]
            if chart_type is None:
                continue

            obs_rows = _safe_query_all(conn,
                "SELECT value FROM spc_observation "
                "WHERE chart_type = ? "
                "AND observed_at > datetime('now', '-30 days') "
                "ORDER BY observed_at",
                (chart_type,))

            if not obs_rows or len(obs_rows) < 10:
                continue

            values = []
            for o in obs_rows:
                v = o["value"] if isinstance(o, dict) else o[0]
                if v is not None:
                    values.append(float(v))

            if len(values) < 10:
                continue

            # Compute skewness
            n = len(values)
            mean = sum(values) / n
            variance = sum((x - mean) ** 2 for x in values) / (n - 1)
            std_dev = math.sqrt(variance) if variance > 0 else 0

            if std_dev == 0:
                continue

            m3 = sum((x - mean) ** 3 for x in values) / n
            skewness = m3 / (std_dev ** 3)

            if abs(skewness) > 2:
                skewed_charts.append((chart_type, skewness))

        if skewed_charts:
            details = ", ".join(
                f"'{c}' (skew={s:.2f})"
                for c, s in skewed_charts
            )
            findings.append(_finding(
                "statistics", "medium",
                f"{len(skewed_charts)} SPC chart(s) violate normality assumptions",
                f"These SPC charts have |skewness| > 2: {details}. "
                f"Shewhart control charts assume approximately normal data. "
                f"Highly skewed data produces unreliable control limits and "
                f"false alarms (or missed signals).",
                "Consider transforming the data (log, Box-Cox) before charting, "
                "or switch to a distribution-free control chart method (e.g., "
                "EWMA or nonparametric charts). Investigate the cause of skew.",
                "Query spc_observation by chart_type. Compute skewness for "
                "each. For skewed charts, propose data transformations or "
                "alternative charting methods.",
                "SPC assumption validity",
                ["mandarin/quality/spc.py",
                 "mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 9: Forecasting accuracy ──────────────────────────────────

def check_forecasting_accuracy(conn):
    """Flag if stored forecasts have mean absolute error > 20%."""
    findings = []
    try:
        # Look for forecast vs actual pairs in quality_metric
        forecast_rows = _safe_query_all(conn,
            "SELECT value, details, measured_at FROM quality_metric "
            "WHERE metric_type = 'forecast_accuracy' "
            "ORDER BY measured_at DESC LIMIT 30")

        if not forecast_rows:
            # No forecast accuracy data yet — handle gracefully
            return findings

        errors = []
        for r in forecast_rows:
            val = r["value"] if isinstance(r, dict) else r[0]
            if val is not None:
                errors.append(abs(float(val)))

        if not errors:
            return findings

        mae = sum(errors) / len(errors)

        if mae > 0.20:
            findings.append(_finding(
                "statistics", "medium",
                f"Forecast accuracy degraded (MAE: {mae*100:.1f}%)",
                f"The mean absolute error of stored forecasts is {mae*100:.1f}%, "
                f"exceeding the 20% threshold (based on {len(errors)} "
                f"measurements). Poor forecasting accuracy reduces the value "
                f"of predictive analytics and planning.",
                "Review and retrain forecasting models. Check for concept "
                "drift (changing user behavior), data quality issues, or "
                "model staleness. Consider ensemble methods or more frequent "
                "model updates.",
                "Query quality_metric WHERE metric_type='forecast_accuracy'. "
                "Analyze error distribution over time. Identify periods of "
                "high error and correlate with external changes.",
                "Predictive analytics reliability",
                ["mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 10: Effect size distribution ──────────────────────────────

def check_effect_size_distribution(conn):
    """Flag if most concluded experiments have Cohen's d < 0.2 (negligible effects)."""
    findings = []
    try:
        rows = _safe_query_all(conn,
            "SELECT name, conclusion FROM experiment "
            "WHERE status = 'concluded' AND conclusion IS NOT NULL")

        if not rows or len(rows) < 3:
            return findings  # Need at least 3 concluded experiments

        small_effect = 0
        total_with_effect = 0

        for r in rows:
            r["name"] if isinstance(r, dict) else r[0]
            conclusion_raw = r["conclusion"] if isinstance(r, dict) else r[1]

            if not conclusion_raw:
                continue

            try:
                conclusion = json.loads(conclusion_raw) if isinstance(conclusion_raw, str) else conclusion_raw
            except (json.JSONDecodeError, TypeError):
                continue

            effect_size = conclusion.get("effect_size") or conclusion.get("cohens_d")
            if effect_size is None:
                continue

            total_with_effect += 1
            if abs(float(effect_size)) < 0.2:
                small_effect += 1

        if total_with_effect < 3:
            return findings

        ratio = small_effect / total_with_effect

        if ratio > 0.60:
            findings.append(_finding(
                "statistics", "low",
                f"{ratio*100:.0f}% of experiments show negligible effect sizes "
                f"(d < 0.2)",
                f"{small_effect} of {total_with_effect} concluded experiments "
                f"with effect size data have Cohen's d < 0.2 (negligible "
                f"effect). This suggests experiments may not be testing "
                f"sufficiently bold hypotheses, or the metrics chosen are "
                f"not sensitive enough to detect real differences.",
                "Review experiment design: consider testing larger changes, "
                "choosing more sensitive primary metrics, or focusing on "
                "areas with more room for improvement. Small effects may "
                "not justify the cost of experimentation.",
                "Query experiment WHERE status='concluded'. Parse conclusion "
                "JSON for effect_size. Analyze whether small effects are "
                "concentrated in certain areas.",
                "Experiment ROI and hypothesis quality",
                ["mandarin/intelligence/analyzers_statistics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Analyzer registry ────────────────────────────────────────────────

ANALYZERS = [
    check_spc_charts_in_control,
    check_dpmo_trend,
    check_capability_indices,
    check_irt_calibration_freshness,
    check_retention_forecast,
    check_experiment_power,
    check_segment_drift,
    check_normality_violations,
    check_forecasting_accuracy,
    check_effect_size_distribution,
]
