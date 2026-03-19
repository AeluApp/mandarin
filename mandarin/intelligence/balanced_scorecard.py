"""Balanced Scorecard — Kaplan & Norton lag/lead indicator framework.

Four perspectives: Financial, Customer, Internal Process, Learning & Growth.
Each perspective has lag indicators (outcomes) linked to lead indicators
(drivers). When a lag is red but its lead is green, there's a measurement
disconnect. When both are red, there's a real problem.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query

logger = logging.getLogger(__name__)


# ── Metric definitions ───────────────────────────────────────────────

# Each metric: (key, name, perspective, indicator_type, target, red_threshold, higher_is_better)
_BSC_METRICS = [
    # Financial perspective
    ("f_mrr", "Monthly Recurring Revenue", "financial", "lag", 500, 0, True),
    ("f_conversion", "Free-to-Paid Conversion %", "financial", "lag", 5.0, 1.0, True),
    ("f_ltv", "Customer Lifetime Value", "financial", "lag", 50, 10, True),
    ("f_acquisition_rate", "New Users / Month", "financial", "lead", 20, 3, True),
    ("f_trial_starts", "Trial Starts / Month", "financial", "lead", 10, 1, True),

    # Customer perspective
    ("c_d30_retention", "D30 Retention %", "customer", "lag", 30, 10, True),
    ("c_churn_rate", "Monthly Churn Rate %", "customer", "lag", 5, 15, False),
    ("c_nps", "Net Promoter Score", "customer", "lag", 50, 0, True),
    ("c_d1_retention", "D1 Retention %", "customer", "lead", 50, 20, True),
    ("c_session_frequency", "Sessions / Active User / Week", "customer", "lead", 3, 1, True),
    ("c_activation_rate", "Activation Rate %", "customer", "lead", 40, 15, True),

    # Internal process perspective
    ("i_audit_score", "Product Audit Score", "internal_process", "lag", 80, 50, True),
    ("i_dpmo", "DPMO (Defects per Million)", "internal_process", "lag", 10000, 50000, False),
    ("i_finding_resolution", "Finding Resolution Rate %", "internal_process", "lead", 70, 30, True),
    ("i_work_order_completion", "Work Order Completion Rate %", "internal_process", "lead", 60, 20, True),

    # Learning & growth perspective
    ("l_content_coverage", "HSK Content Coverage %", "learning_growth", "lag", 90, 50, True),
    ("l_model_accuracy", "AI Model Accuracy %", "learning_growth", "lag", 80, 60, True),
    ("l_content_velocity", "New Content Items / Month", "learning_growth", "lead", 50, 5, True),
]

# Lag → Lead linkages
_LAG_LEAD_LINKS = {
    "f_mrr": ["f_acquisition_rate", "f_trial_starts"],
    "f_conversion": ["f_trial_starts", "c_activation_rate"],
    "f_ltv": ["c_d30_retention", "c_session_frequency"],
    "c_d30_retention": ["c_d1_retention", "c_session_frequency"],
    "c_churn_rate": ["c_session_frequency", "c_activation_rate"],
    "c_nps": ["c_d1_retention", "c_session_frequency"],
    "i_audit_score": ["i_finding_resolution", "i_work_order_completion"],
    "i_dpmo": ["i_work_order_completion"],
    "l_content_coverage": ["l_content_velocity"],
    "l_model_accuracy": ["l_content_velocity"],
}


def _compute_metric_value(conn, metric_key: str) -> float | None:
    """Compute current value for a BSC metric from live database data."""
    try:
        if metric_key == "f_mrr":
            paid = _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE subscription_tier IN ('paid', 'premium') AND subscription_status = 'active'
            """, default=0)
            return round(paid * 14.99, 2)

        elif metric_key == "f_conversion":
            total = _safe_scalar(conn, "SELECT COUNT(*) FROM user WHERE is_admin = 0", default=1)
            paid = _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE subscription_tier IN ('paid', 'premium') AND is_admin = 0
            """, default=0)
            return round(paid / max(1, total) * 100, 1)

        elif metric_key == "f_acquisition_rate":
            return _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE is_admin = 0 AND created_at >= datetime('now', '-30 days')
            """, default=0)

        elif metric_key == "f_trial_starts":
            # Trial starts approximated by first_session_at in last 30 days
            return _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE is_admin = 0 AND first_session_at >= datetime('now', '-30 days')
            """, default=0)

        elif metric_key == "c_d1_retention":
            eligible = _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE is_admin = 0 AND first_session_at IS NOT NULL
                  AND first_session_at <= datetime('now', '-1 day')
            """, default=0)
            retained = _safe_scalar(conn, """
                SELECT COUNT(DISTINCT sl.user_id) FROM session_log sl
                JOIN user u ON sl.user_id = u.id
                WHERE u.is_admin = 0
                  AND sl.completed_at >= datetime(u.first_session_at, '+1 day')
                  AND sl.completed_at < datetime(u.first_session_at, '+2 days')
            """, default=0)
            return round(retained / max(1, eligible) * 100, 1)

        elif metric_key == "c_d30_retention":
            eligible = _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE is_admin = 0 AND first_session_at IS NOT NULL
                  AND first_session_at <= datetime('now', '-30 days')
            """, default=0)
            retained = _safe_scalar(conn, """
                SELECT COUNT(DISTINCT sl.user_id) FROM session_log sl
                JOIN user u ON sl.user_id = u.id
                WHERE u.is_admin = 0
                  AND sl.completed_at >= datetime(u.first_session_at, '+30 days')
            """, default=0)
            return round(retained / max(1, eligible) * 100, 1)

        elif metric_key == "c_churn_rate":
            paid = _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE subscription_tier IN ('paid', 'premium')
            """, default=1)
            churned = _safe_scalar(conn, """
                SELECT COUNT(DISTINCT user_id) FROM lifecycle_event
                WHERE event_type = 'cancellation_completed'
                  AND created_at >= datetime('now', '-30 days')
            """, default=0)
            return round(churned / max(1, paid) * 100, 1)

        elif metric_key == "c_session_frequency":
            active = _safe_scalar(conn, """
                SELECT COUNT(DISTINCT user_id) FROM session_log
                WHERE completed_at >= datetime('now', '-7 days')
            """, default=1)
            sessions = _safe_scalar(conn, """
                SELECT COUNT(*) FROM session_log
                WHERE completed_at >= datetime('now', '-7 days')
            """, default=0)
            return round(sessions / max(1, active), 1)

        elif metric_key == "c_activation_rate":
            with_session = _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE is_admin = 0 AND first_session_at IS NOT NULL
            """, default=1)
            activated = _safe_scalar(conn, """
                SELECT COUNT(*) FROM user
                WHERE is_admin = 0 AND activation_at IS NOT NULL
            """, default=0)
            return round(activated / max(1, with_session) * 100, 1)

        elif metric_key == "c_nps":
            feedback = conn.execute("""
                SELECT rating FROM user_feedback
                WHERE feedback_type = 'nps' AND rating IS NOT NULL
                  AND created_at >= datetime('now', '-90 days')
            """).fetchall()
            if len(feedback) < 5:
                return None
            total = len(feedback)
            promoters = sum(1 for r in feedback if r["rating"] >= 9)
            detractors = sum(1 for r in feedback if r["rating"] <= 6)
            return round((promoters - detractors) / total * 100)

        elif metric_key == "i_audit_score":
            row = _safe_query(conn, """
                SELECT overall_score FROM product_audit ORDER BY run_at DESC LIMIT 1
            """)
            return row["overall_score"] if row else None

        elif metric_key == "i_dpmo":
            total_attempts = _safe_scalar(conn, """
                SELECT COUNT(*) FROM review_event
                WHERE reviewed_at >= datetime('now', '-30 days')
            """, default=0)
            errors = _safe_scalar(conn, """
                SELECT COUNT(*) FROM review_event
                WHERE correct = 0 AND reviewed_at >= datetime('now', '-30 days')
            """, default=0)
            if total_attempts > 0:
                return round(errors / total_attempts * 1_000_000)
            return None

        elif metric_key == "i_finding_resolution":
            total_findings = _safe_scalar(conn, """
                SELECT COUNT(*) FROM pi_finding WHERE status != 'new'
            """, default=0)
            resolved = _safe_scalar(conn, """
                SELECT COUNT(*) FROM pi_finding WHERE status = 'resolved'
            """, default=0)
            return round(resolved / max(1, total_findings + resolved) * 100, 1)

        elif metric_key == "l_content_coverage":
            total_items = _safe_scalar(conn, "SELECT COUNT(*) FROM content_item", default=0)
            # HSK 1-4 = ~1200 target items
            return round(min(100, total_items / 1200 * 100), 1)

        elif metric_key == "l_content_velocity":
            return _safe_scalar(conn, """
                SELECT COUNT(*) FROM content_item
                WHERE created_at >= datetime('now', '-30 days')
            """, default=0)

    except Exception as e:
        logger.debug("BSC metric %s computation failed: %s", metric_key, e)

    return None


def compute_balanced_scorecard(conn: sqlite3.Connection) -> dict:
    """Compute the full Balanced Scorecard with current values and RAG status."""
    perspectives = {}

    for key, name, perspective, indicator_type, target, red_threshold, higher_is_better in _BSC_METRICS:
        value = _compute_metric_value(conn, key)

        # Determine RAG status
        if value is None:
            status = "grey"  # No data
        elif higher_is_better:
            if value >= target:
                status = "green"
            elif value >= red_threshold:
                status = "amber"
            else:
                status = "red"
        else:  # Lower is better (churn, DPMO)
            if value <= target:
                status = "green"
            elif value <= red_threshold:
                status = "amber"
            else:
                status = "red"

        linked_leads = _LAG_LEAD_LINKS.get(key, [])

        if perspective not in perspectives:
            perspectives[perspective] = []

        perspectives[perspective].append({
            "key": key,
            "name": name,
            "indicator_type": indicator_type,
            "current_value": value,
            "target": target,
            "status": status,
            "linked_leads": linked_leads,
        })

    return {
        "perspectives": perspectives,
        "summary": {
            p: _perspective_health(metrics)
            for p, metrics in perspectives.items()
        },
    }


def _perspective_health(metrics: list[dict]) -> str:
    """Compute overall health for a perspective: red/amber/green."""
    statuses = [m["status"] for m in metrics if m["status"] != "grey"]
    if not statuses:
        return "grey"
    if "red" in statuses:
        return "red"
    if "amber" in statuses:
        return "amber"
    return "green"


def _analyze_scorecard_health(conn) -> list[dict]:
    """Emit findings for BSC perspectives with red status or lag/lead disconnects."""
    findings = []

    try:
        bsc = compute_balanced_scorecard(conn)

        # Check for red perspectives
        for perspective, health in bsc.get("summary", {}).items():
            if health == "red":
                # Find which metrics are red
                red_metrics = [
                    m for m in bsc["perspectives"].get(perspective, [])
                    if m["status"] == "red"
                ]
                metric_names = ", ".join(m["name"] for m in red_metrics)
                findings.append(_finding(
                    "strategic", "high",
                    f"BSC {perspective} perspective is RED: {metric_names}",
                    f"The {perspective} perspective of the Balanced Scorecard "
                    f"has {len(red_metrics)} red metric(s): {metric_names}. "
                    f"This indicates a fundamental problem in this business area.",
                    f"Address the red metrics in the {perspective} perspective. "
                    f"Start with the lag indicators and trace to their lead drivers.",
                    f"Investigate {perspective} BSC metrics and their lead indicators.",
                    f"Red BSC perspective signals a strategic-level problem.",
                    ["mandarin/web/admin_routes.py"],
                ))

        # Check for lag/lead disconnects
        for perspective, metrics in bsc.get("perspectives", {}).items():
            for metric in metrics:
                if metric["indicator_type"] != "lag" or metric["status"] != "red":
                    continue
                # Check if linked leads are green (disconnect)
                for lead_key in metric.get("linked_leads", []):
                    lead = next(
                        (m for p_metrics in bsc["perspectives"].values()
                         for m in p_metrics if m["key"] == lead_key),
                        None,
                    )
                    if lead and lead["status"] == "green":
                        findings.append(_finding(
                            "strategic", "medium",
                            f"BSC disconnect: {metric['name']} (red) but {lead['name']} (green)",
                            f"Lag indicator '{metric['name']}' is red, but its lead "
                            f"indicator '{lead['name']}' is green. This disconnect suggests "
                            f"either the causal chain is wrong (the lead doesn't actually "
                            f"drive the lag) or there's a confounding factor.",
                            f"Investigate whether '{lead['name']}' truly drives "
                            f"'{metric['name']}'. The causal model may need updating.",
                            f"Review the lag/lead linkage between {metric['key']} and {lead_key}.",
                            "BSC lag/lead disconnects reveal flawed causal assumptions.",
                            ["mandarin/intelligence/balanced_scorecard.py"],
                        ))

    except Exception as e:
        logger.debug("BSC health analyzer failed: %s", e)

    return findings


ANALYZERS = [
    _analyze_scorecard_health,
]
