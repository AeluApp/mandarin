"""Lean Six Sigma analyzers — monitor DMAIC cycles, counter-metrics, NPS, and email effectiveness."""

import json
import logging
import sqlite3

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Check 1: Open DMAIC cycles past target closure ─────────────────────

def _check_stale_dmaic_cycles(conn):
    """Flag DMAIC cycles that have been open for more than 8 weeks."""
    findings = []
    try:
        stale = _safe_query_all(conn,
            "SELECT id, dimension, run_at, control_json FROM pi_dmaic_log "
            "WHERE (control_json IS NULL OR control_json = 'null' OR "
            "json_extract(control_json, '$.status') != 'stable') "
            "AND run_at < datetime('now', '-56 days') "
            "ORDER BY run_at LIMIT 10")

        if stale:
            dims = [r["dimension"] if isinstance(r, dict) else r[1] for r in stale]
            findings.append(_finding(
                "methodology", "medium",
                f"{len(stale)} DMAIC cycle(s) open for 8+ weeks without closure",
                f"These DMAIC cycles have been open without reaching stable CONTROL "
                f"status: {', '.join(dims[:5])}. A DMAIC cycle should close within "
                f"8 weeks — either the improvement worked (SPC in control) or the "
                f"approach should be revised.",
                "Review open DMAIC cycles and either close them (if SPC is stable) "
                "or revise the improvement approach.",
                "Review pi_dmaic_log entries that have been open for 56+ days. "
                "Check SPC charts for those dimensions. If in control, close them. "
                "If not, propose a revised improvement approach.",
                "DMAIC cycle management efficiency",
                ["mandarin/intelligence/quality_metrics_generator.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 2: Counter-metrics drifting wrong direction ──────────────────

def _check_counter_metric_drift(conn):
    """Flag counter-metrics that are degrading while primary KPIs improve.

    This is the Goodhart detection check — if accuracy goes up but
    delayed_recall_accuracy goes down, something is wrong.
    """
    findings = []
    try:
        # Get last two snapshots to detect direction
        snapshots = _safe_query_all(conn,
            "SELECT id, overall_health, alert_count, critical_count, "
            "integrity_json, cost_json, distortion_json, outcome_json "
            "FROM counter_metric_snapshot "
            "ORDER BY computed_at DESC LIMIT 2")

        if not snapshots or len(snapshots) < 2:
            return findings

        latest = snapshots[0]
        prev = snapshots[1]

        latest_critical = latest["critical_count"] if isinstance(latest, dict) else latest[3]
        prev_critical = prev["critical_count"] if isinstance(prev, dict) else prev[3]

        if latest_critical > prev_critical:
            increase = latest_critical - prev_critical
            findings.append(_finding(
                "methodology", "high",
                f"Counter-metric critical alerts increased by {increase} "
                f"(Goodhart risk)",
                f"Counter-metric critical count rose from {prev_critical} to "
                f"{latest_critical}. This may indicate that a primary KPI is being "
                f"optimized at the expense of learning quality. Counter-metrics "
                f"protect against Goodhart's Law: 'When a measure becomes a target, "
                f"it ceases to be a good measure.'",
                "Investigate which primary KPI improvement is causing counter-metric "
                "degradation. Consider pausing the optimization until the root cause "
                "is understood.",
                "Check counter_metric_snapshot table for rising critical_count. "
                "Compare integrity_json and outcome_json between the latest two "
                "snapshots to identify which specific counter-metrics degraded.",
                "Learning quality integrity (anti-Goodhart)",
                ["mandarin/counter_metrics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 3: NPS below industry benchmark ──────────────────────────────

def _check_nps_health(conn):
    """Flag if NPS drops below 50 (good) or 30 (concerning)."""
    findings = []
    try:
        rows = _safe_query_all(conn,
            "SELECT score FROM nps_response "
            "WHERE responded_at > datetime('now', '-30 days')")

        if not rows or len(rows) < 5:
            return findings  # Not enough data

        scores = [r["score"] if isinstance(r, dict) else r[0] for r in rows]
        promoters = sum(1 for s in scores if s >= 9) / len(scores)
        detractors = sum(1 for s in scores if s <= 6) / len(scores)
        nps = (promoters - detractors) * 100

        if nps < 30:
            severity = "high"
            label = "concerning"
        elif nps < 50:
            severity = "medium"
            label = "below good"
        else:
            return findings  # NPS is fine

        findings.append(_finding(
            "methodology", severity,
            f"NPS is {nps:.0f} ({label} — target: 50+)",
            f"Net Promoter Score over the last 30 days is {nps:.0f} based on "
            f"{len(scores)} responses. Promoters: {promoters*100:.0f}%, "
            f"Detractors: {detractors*100:.0f}%. NPS below 50 indicates "
            f"the product experience needs improvement.",
            "Review recent NPS feedback text for themes. Consider A/B testing "
            "changes to address common complaints.",
            "Query nps_response table for recent low scores and their feedback "
            "text. Look for patterns in detractor comments.",
            "Customer satisfaction and product-market fit",
            ["mandarin/web/nps_routes.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 4: Email effectiveness declining ─────────────────────────────

def _check_email_effectiveness(conn):
    """Flag if email open or click rates are declining."""
    findings = []
    try:
        # Compare last 2 weeks vs previous 2 weeks
        recent = _safe_query(conn,
            "SELECT COUNT(*) AS sent, "
            "SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) AS opened, "
            "SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) AS clicked "
            "FROM email_send_log "
            "WHERE sent_at > datetime('now', '-14 days')")

        prev = _safe_query(conn,
            "SELECT COUNT(*) AS sent, "
            "SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) AS opened, "
            "SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) AS clicked "
            "FROM email_send_log "
            "WHERE sent_at > datetime('now', '-28 days') "
            "AND sent_at <= datetime('now', '-14 days')")

        if not recent or not prev:
            return findings

        recent_sent = recent[0] if recent else 0
        prev_sent = prev[0] if prev else 0

        if recent_sent < 10 or prev_sent < 10:
            return findings  # Not enough data

        recent_open_rate = (recent[1] or 0) / recent_sent
        prev_open_rate = (prev[1] or 0) / prev_sent

        if prev_open_rate > 0 and recent_open_rate < prev_open_rate * 0.7:
            drop_pct = ((prev_open_rate - recent_open_rate) / prev_open_rate) * 100
            findings.append(_finding(
                "methodology", "medium",
                f"Email open rate dropped {drop_pct:.0f}% vs previous 2 weeks",
                f"Email open rate fell from {prev_open_rate*100:.1f}% to "
                f"{recent_open_rate*100:.1f}%. This may indicate email fatigue, "
                f"deliverability issues, or irrelevant content.",
                "Review email frequency and content. Consider A/B testing subject "
                "lines and reducing email cadence for disengaged users.",
                "Check email_send_log for declining open rates. Review email "
                "content and frequency.",
                "Email channel effectiveness",
                ["mandarin/email.py", "mandarin/web/email_scheduler.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Analyzer registry ──────────────────────────────────────────────────

ANALYZERS = [
    _check_stale_dmaic_cycles,
    _check_counter_metric_drift,
    _check_nps_health,
    _check_email_effectiveness,
]
