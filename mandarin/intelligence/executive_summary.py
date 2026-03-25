"""Executive Summary Generator — one-page state of the business.

All consulting firms require a single-page summary that any executive
can scan in 60 seconds to understand: what's working, what's broken,
and the 3 things that matter most today.

Aggregates from existing data sources — zero new tables needed.
Optionally uses Qwen LLM for a 3-sentence narrative.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query, _safe_query_all
from datetime import UTC

logger = logging.getLogger(__name__)


def generate_executive_summary(conn: sqlite3.Connection) -> dict:
    """Generate structured executive one-pager with top 3 actions.

    Returns a dict suitable for JSON serialization and admin dashboard display.
    All data comes from existing tables — no new schema required.
    """
    summary = {
        "generated_at": None,
        "headline_metrics": {},
        "quick_ratio": None,
        "top_risks": [],
        "top_actions": [],
        "constraint_dimension": None,
        "hypothesis_status": {},
        "overall_grade": None,
        "llm_narrative": None,
    }

    try:
        from datetime import datetime, timezone
        summary["generated_at"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # ── Headline metrics ──
    try:
        total_users = _safe_scalar(conn, "SELECT COUNT(*) FROM user WHERE is_admin = 0", default=0)
        active_7d = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM session_log
            WHERE completed_at >= datetime('now', '-7 days')
        """, default=0)
        sessions_7d = _safe_scalar(conn, """
            SELECT COUNT(*) FROM session_log
            WHERE started_at >= datetime('now', '-7 days')
        """, default=0)

        # Revenue estimate (paid users × monthly price)
        paid_users = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE subscription_tier IN ('paid', 'premium') AND subscription_status = 'active'
        """, default=0)
        mrr_estimate = paid_users * 14.99  # Monthly price from payment.py

        summary["headline_metrics"] = {
            "total_users": total_users,
            "active_users_7d": active_7d,
            "sessions_7d": sessions_7d,
            "paid_users": paid_users,
            "mrr_estimate": round(mrr_estimate, 2),
        }
    except Exception as e:
        logger.debug("Executive summary headline metrics failed: %s", e)

    # ── Latest audit grade ──
    try:
        audit = _safe_query(conn, """
            SELECT overall_grade, overall_score, dimension_scores
            FROM product_audit ORDER BY run_at DESC LIMIT 1
        """)
        if audit:
            summary["overall_grade"] = audit["overall_grade"]
            summary["overall_score"] = audit["overall_score"]
    except Exception:
        pass

    # ── Top 3 risks ──
    try:
        risks = _safe_query_all(conn, """
            SELECT title, category, probability, impact,
                   (probability * impact) as risk_score
            FROM quality_risk
            WHERE status IN ('open', 'mitigating')
            ORDER BY risk_score DESC
            LIMIT 3
        """)
        summary["top_risks"] = [
            {"title": r["title"], "category": r["category"],
             "score": r["risk_score"]}
            for r in risks
        ]
    except Exception:
        pass

    # ── Top 3 actions (from latest audit findings) ──
    try:
        findings = _safe_query_all(conn, """
            SELECT dimension, severity, title, recommendation
            FROM pi_finding
            WHERE status IN ('new', 'acknowledged')
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    ELSE 3
                END,
                created_at DESC
            LIMIT 3
        """)
        summary["top_actions"] = [
            {"dimension": f["dimension"], "severity": f["severity"],
             "title": f["title"], "recommendation": f["recommendation"]}
            for f in findings
        ]
    except Exception:
        pass

    # ── System constraint (Theory of Constraints) ──
    try:
        audit = _safe_query(conn, """
            SELECT dimension_scores FROM product_audit
            ORDER BY run_at DESC LIMIT 1
        """)
        if audit and audit["dimension_scores"]:
            scores = json.loads(audit["dimension_scores"])
            # Find the dimension with the lowest score (the constraint)
            worst = None
            worst_score = 999
            for dim, info in scores.items():
                if dim.startswith("_"):
                    continue
                sc = info.get("score", 100) if isinstance(info, dict) else 100
                if sc < worst_score:
                    worst_score = sc
                    worst = dim
            if worst:
                summary["constraint_dimension"] = worst
                summary["constraint_score"] = worst_score
    except Exception:
        pass

    # ── Hypothesis status ──
    try:
        hyp_counts = {}
        for status in ("untested", "confirmed", "disconfirmed", "inconclusive"):
            hyp_counts[status] = _safe_scalar(conn, """
                SELECT COUNT(*) FROM pi_strategic_hypotheses WHERE status = ?
            """, (status,), default=0)
        summary["hypothesis_status"] = hyp_counts
    except Exception:
        pass

    # ── Quick Ratio (Bain growth accounting) ──
    try:
        new_mrr_users = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE subscription_tier IN ('paid', 'premium')
              AND subscription_status = 'active'
              AND created_at >= datetime('now', '-30 days')
        """, default=0)
        churned_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM lifecycle_event
            WHERE event_type = 'cancellation_completed'
              AND created_at >= datetime('now', '-30 days')
        """, default=0)
        new_mrr = new_mrr_users * 14.99
        churn_mrr = churned_users * 14.99
        denominator = churn_mrr if churn_mrr > 0 else 0.01
        quick_ratio = round(new_mrr / denominator, 2) if denominator > 0 else None
        summary["quick_ratio"] = quick_ratio
    except Exception:
        pass

    # ── LLM narrative (optional, Qwen) ──
    try:
        from ..ai.ollama_client import generate, is_ollama_available
        if is_ollama_available():
            metrics = summary.get("headline_metrics", {})
            grade = summary.get("overall_grade", "unknown")
            constraint = summary.get("constraint_dimension", "unknown")
            qr = summary.get("quick_ratio")

            prompt = (
                f"Write exactly 3 sentences summarizing this business status for a solo founder. "
                f"Be direct, no filler. "
                f"Users: {metrics.get('total_users', 0)}, "
                f"active (7d): {metrics.get('active_users_7d', 0)}, "
                f"MRR: ${metrics.get('mrr_estimate', 0)}, "
                f"product grade: {grade}, "
                f"system constraint: {constraint}, "
                f"quick ratio: {qr}. "
                f"Top risk: {summary['top_risks'][0]['title'] if summary['top_risks'] else 'none identified'}."
            )
            resp = generate(
                prompt=prompt,
                system="You are a concise management consultant writing a 3-sentence executive summary.",
                temperature=0.3,
                max_tokens=200,
                task_type="executive_summary",
                conn=conn,
            )
            if resp.success:
                summary["llm_narrative"] = resp.text.strip()
    except Exception as e:
        logger.debug("Executive summary LLM narrative skipped: %s", e)

    return summary


def _analyze_executive_freshness(conn) -> list[dict]:
    """Emit finding if executive summary hasn't been reviewed recently."""
    findings = []

    # Check if product_audit has been run recently
    try:
        last_audit = _safe_query(conn, """
            SELECT run_at FROM product_audit ORDER BY run_at DESC LIMIT 1
        """)
        if not last_audit:
            findings.append(_finding(
                "strategic", "medium",
                "No product audit has been run",
                "The executive summary depends on product audit data. No audit "
                "results exist yet. Run the product intelligence pipeline.",
                "Run a product audit to populate executive summary data.",
                "Call run_product_audit() to generate findings and scores.",
                "Without audit data, the executive summary has no substance.",
                ["mandarin/intelligence/__init__.py"],
            ))
        else:
            from datetime import datetime
            try:
                last_dt = datetime.fromisoformat(last_audit["run_at"].replace("Z", "+00:00"))
                now = datetime.now(last_dt.tzinfo) if last_dt.tzinfo else datetime.now()
                days_stale = (now - last_dt).days
                if days_stale > 7:
                    findings.append(_finding(
                        "strategic", "low",
                        f"Product audit is {days_stale} days old",
                        f"The last product audit was {days_stale} days ago. "
                        f"Executive summary data may be stale.",
                        "Run a fresh product audit for current data.",
                        "Call run_product_audit() to refresh findings.",
                        "Stale audit data means stale executive summary.",
                        ["mandarin/intelligence/__init__.py"],
                    ))
            except (ValueError, TypeError):
                pass
    except Exception:
        pass

    return findings


ANALYZERS = [
    _analyze_executive_freshness,
]
