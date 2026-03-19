"""Growth & business health analyzers — Bain/McKinsey frameworks.

Covers: Growth Accounting (Quick Ratio), Revenue Waterfall, Cohort Unit
Economics, Scenario Modeling, CAC Health, Decision Log Health.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query, _safe_query_all

logger = logging.getLogger(__name__)


# ── 1. Growth Accounting (Bain Quick Ratio) ──────────────────────────


def _analyze_growth_accounting(conn) -> list[dict]:
    """Bain Growth Accounting: Quick Ratio = (new + expansion + reactivation) / (contraction + churn).

    The single best health metric for a subscription business. Healthy > 3.0.
    Pre-launch: emits informational finding about readiness.
    """
    findings = []

    try:
        # Count new paying users in last 30 days
        new_paid = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE subscription_tier IN ('paid', 'premium')
              AND subscription_status = 'active'
              AND created_at >= datetime('now', '-30 days')
        """, default=0)

        # Count churned users in last 30 days
        churned = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM lifecycle_event
            WHERE event_type = 'cancellation_completed'
              AND created_at >= datetime('now', '-30 days')
        """, default=0)

        # Count reactivated users (cancelled then resubscribed)
        reactivated = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT u.id) FROM user u
            WHERE u.subscription_status = 'active'
              AND u.subscription_tier IN ('paid', 'premium')
              AND u.updated_at >= datetime('now', '-30 days')
              AND EXISTS (
                  SELECT 1 FROM lifecycle_event le
                  WHERE le.user_id = u.id
                    AND le.event_type = 'cancellation_completed'
                    AND le.created_at < u.updated_at
              )
        """, default=0)

        # Monthly price estimate
        price = 14.99
        new_mrr = new_paid * price
        reactivation_mrr = reactivated * price
        churn_mrr = churned * price

        # No expansion/contraction yet (single tier)
        expansion_mrr = 0
        contraction_mrr = 0

        numerator = new_mrr + expansion_mrr + reactivation_mrr
        denominator = contraction_mrr + churn_mrr

        total_paid = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE subscription_tier IN ('paid', 'premium')
              AND subscription_status = 'active'
        """, default=0)

        if total_paid == 0 and new_paid == 0:
            # Pre-launch: no paying users yet
            findings.append(_finding(
                "growth_accounting", "low",
                "Growth accounting: no paying users yet",
                "Quick Ratio cannot be computed with zero revenue. This is "
                "expected pre-launch. The growth accounting infrastructure "
                "is ready and will activate when paying users arrive.",
                "Focus on product-market fit signals before monetization metrics.",
                "Review conversion funnel readiness: pricing page, trial flow, upgrade prompts.",
                "Growth accounting infrastructure is ready for launch.",
                ["mandarin/payment.py", "mandarin/tier_gate.py"],
            ))
            return findings

        if denominator == 0:
            # New revenue but no churn — perfect start
            quick_ratio = float("inf")
            findings.append(_finding(
                "growth_accounting", "low",
                f"Quick Ratio: ∞ (${new_mrr:.0f} new MRR, $0 churn)",
                f"New MRR: ${new_mrr:.0f}, Churn MRR: $0. Zero churn is "
                f"ideal but may not be sustainable. Quick Ratio is infinite.",
                "Monitor churn rate as the user base grows.",
                "Check churn detection signals and retention metrics.",
                "Growth accounting: healthy start.",
                ["mandarin/churn_detection.py"],
            ))
            return findings

        quick_ratio = round(numerator / denominator, 2)

        if quick_ratio < 1.0:
            severity = "critical"
            msg = f"Quick Ratio {quick_ratio} — revenue is shrinking"
            rec = "Urgent: churn exceeds new revenue. Focus on retention before acquisition."
        elif quick_ratio < 2.0:
            severity = "high"
            msg = f"Quick Ratio {quick_ratio} — unstable growth"
            rec = "Growth is fragile. Reduce churn and build reactivation flows."
        elif quick_ratio < 3.0:
            severity = "medium"
            msg = f"Quick Ratio {quick_ratio} — adequate growth"
            rec = "Growth is sustainable but not strong. Explore expansion revenue (tier upgrades)."
        else:
            severity = "low"
            msg = f"Quick Ratio {quick_ratio} — healthy growth"
            rec = "Strong growth. Maintain current trajectory."

        analysis = (
            f"New MRR: ${new_mrr:.0f}, Expansion: ${expansion_mrr:.0f}, "
            f"Reactivation: ${reactivation_mrr:.0f}, "
            f"Contraction: ${contraction_mrr:.0f}, Churn: ${churn_mrr:.0f}. "
            f"Quick Ratio: {quick_ratio}."
        )

        findings.append(_finding(
            "growth_accounting", severity, msg, analysis, rec,
            "Compute Quick Ratio from user and lifecycle_event tables.",
            "Growth accounting (Bain framework)",
            ["mandarin/payment.py", "mandarin/churn_detection.py"],
        ))

        # Flag absence of expansion revenue path
        if expansion_mrr == 0 and total_paid > 5:
            findings.append(_finding(
                "growth_accounting", "low",
                "No expansion MRR path (single pricing tier)",
                "All paying users are on the same tier. Expansion MRR "
                "(upgrades, add-ons) is a key growth lever for subscription "
                "businesses. Consider premium features or higher tiers.",
                "Explore premium tier with advanced analytics, priority support, or API access.",
                "Review payment.py pricing structure and tier_gate.py feature gating.",
                "Single-tier pricing limits the Quick Ratio numerator.",
                ["mandarin/payment.py", "mandarin/tier_gate.py"],
            ))

    except Exception as e:
        logger.debug("Growth accounting analyzer failed: %s", e)

    return findings


# ── 2. Revenue Waterfall (McKinsey) ──────────────────────────────────


def _analyze_revenue_waterfall(conn) -> list[dict]:
    """McKinsey revenue waterfall: monthly new/expansion/contraction/churn MRR breakdown."""
    findings = []

    try:
        # Check if waterfall table exists
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        if "pi_revenue_waterfall" not in tables:
            findings.append(_finding(
                "growth_accounting", "low",
                "Revenue waterfall table not yet created",
                "The pi_revenue_waterfall table does not exist. This table "
                "stores monthly MRR decomposition for trend analysis.",
                "Run database migration to create the waterfall table.",
                "Run migration v116 to create pi_revenue_waterfall.",
                "Cannot track revenue composition without the waterfall table.",
                ["mandarin/db/core.py"],
            ))
            return findings

        # Check for recent waterfall data
        latest = _safe_query(conn, """
            SELECT month, net_new_mrr, ending_mrr
            FROM pi_revenue_waterfall
            ORDER BY month DESC LIMIT 1
        """)

        if not latest:
            findings.append(_finding(
                "growth_accounting", "low",
                "Revenue waterfall: no data yet",
                "The waterfall table exists but has no entries. "
                "Waterfall data will be computed when paying users exist.",
                "Waterfall computation will activate with first paying users.",
                "Populate pi_revenue_waterfall from payment event data.",
                "Revenue composition tracking awaiting first revenue.",
                ["mandarin/payment.py"],
            ))
        elif latest["net_new_mrr"] and latest["net_new_mrr"] < 0:
            findings.append(_finding(
                "growth_accounting", "high",
                f"Revenue waterfall: negative net new MRR (${latest['net_new_mrr']:.0f})",
                f"Month {latest['month']}: net new MRR is negative, meaning "
                f"churn exceeds new revenue. Ending MRR: ${latest['ending_mrr']:.0f}.",
                "Focus on churn reduction. Consider pause-subscription option, "
                "win-back campaigns, or product improvements for churning segments.",
                "Analyze churn_detection.py signals for the churning cohort.",
                "Negative net new MRR is a critical business health signal.",
                ["mandarin/churn_detection.py", "mandarin/payment.py"],
            ))

    except Exception as e:
        logger.debug("Revenue waterfall analyzer failed: %s", e)

    return findings


# ── 3. Cohort Unit Economics ─────────────────────────────────────────


def _analyze_cohort_economics(conn) -> list[dict]:
    """Cohort unit economics: LTV, retention, revenue by signup month."""
    findings = []

    try:
        # Get cohorts with enough users
        cohorts = _safe_query_all(conn, """
            SELECT strftime('%Y-%m', created_at) as cohort_month,
                   COUNT(*) as size
            FROM user
            WHERE is_admin = 0 AND created_at IS NOT NULL
            GROUP BY cohort_month
            HAVING size >= 3
            ORDER BY cohort_month DESC
            LIMIT 6
        """)

        if len(cohorts) < 2:
            return findings  # Not enough cohorts to compare

        # For each cohort, compute D7 retention
        cohort_retention = []
        for c in cohorts:
            month = c["cohort_month"]
            d7_retained = _safe_scalar(conn, """
                SELECT COUNT(DISTINCT sl.user_id) FROM session_log sl
                JOIN user u ON sl.user_id = u.id
                WHERE strftime('%Y-%m', u.created_at) = ?
                  AND u.is_admin = 0
                  AND sl.completed_at >= datetime(u.first_session_at, '+7 days')
            """, (month,), default=0)
            retention_pct = round(d7_retained / c["size"] * 100, 1) if c["size"] > 0 else 0
            cohort_retention.append({
                "month": month,
                "size": c["size"],
                "d7_retention_pct": retention_pct,
            })

        # Compare latest cohort to average of prior cohorts
        if len(cohort_retention) >= 2:
            latest = cohort_retention[0]
            prior_avg = sum(c["d7_retention_pct"] for c in cohort_retention[1:]) / len(cohort_retention[1:])

            if latest["d7_retention_pct"] < prior_avg * 0.8:
                findings.append(_finding(
                    "growth_accounting", "high",
                    f"Cohort quality declining: {latest['month']} D7 retention {latest['d7_retention_pct']}% vs avg {prior_avg:.0f}%",
                    f"Latest cohort ({latest['month']}, n={latest['size']}) has D7 "
                    f"retention of {latest['d7_retention_pct']}%, which is >20% below "
                    f"the historical average of {prior_avg:.0f}%. This suggests "
                    f"acquisition quality or onboarding is degrading.",
                    "Investigate: Did acquisition channel mix change? Did onboarding "
                    "change? Are new users a different profile?",
                    "Compare latest cohort characteristics to prior cohorts in user table.",
                    "Cohort quality decline signals product-market fit erosion.",
                    ["mandarin/web/onboarding_routes.py", "mandarin/marketing_hooks.py"],
                ))

    except Exception as e:
        logger.debug("Cohort economics analyzer failed: %s", e)

    return findings


# ── 4. Scenario Modeling ─────────────────────────────────────────────


def _analyze_scenario_model(conn) -> list[dict]:
    """Scenario modeling: bull/base/bear 12-month revenue projections."""
    findings = []

    try:
        total_paid = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE subscription_tier IN ('paid', 'premium')
              AND subscription_status = 'active'
        """, default=0)

        if total_paid < 3:
            # Not enough data for meaningful projections
            findings.append(_finding(
                "growth_accounting", "low",
                "Scenario modeling: insufficient revenue data",
                f"Only {total_paid} paying users — need 3+ for meaningful "
                f"projections. Scenario modeling will activate when revenue data exists.",
                "Focus on reaching first paid users before projecting revenue.",
                "Scenario modeling awaiting sufficient revenue data.",
                "Cannot project revenue without baseline data.",
                ["mandarin/payment.py"],
            ))
            return findings

        # Compute current monthly metrics
        price = 14.99
        current_mrr = total_paid * price

        # Monthly churn rate
        churned_30d = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM lifecycle_event
            WHERE event_type = 'cancellation_completed'
              AND created_at >= datetime('now', '-30 days')
        """, default=0)
        churn_rate = churned_30d / max(1, total_paid)

        # Monthly growth rate (new paid users / total paid)
        new_30d = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE subscription_tier IN ('paid', 'premium')
              AND subscription_status = 'active'
              AND created_at >= datetime('now', '-30 days')
        """, default=0)
        growth_rate = new_30d / max(1, total_paid)

        # Project 12 months
        scenarios = {}
        for name, g_mult, c_mult in [("bull", 1.0, 0.8), ("base", 1.0, 1.0), ("bear", 0.5, 2.0)]:
            mrr = current_mrr
            g = growth_rate * g_mult
            c = min(0.5, churn_rate * c_mult)  # Cap churn at 50%
            for _ in range(12):
                mrr = mrr * (1 + g - c)
            scenarios[name] = round(mrr, 2)

        spread = scenarios["bull"] - scenarios["bear"]
        analysis = (
            f"12-month ARR projections — Bull: ${scenarios['bull']*12:.0f}, "
            f"Base: ${scenarios['base']*12:.0f}, Bear: ${scenarios['bear']*12:.0f}. "
            f"Current MRR: ${current_mrr:.0f}, growth rate: {growth_rate*100:.1f}%/mo, "
            f"churn rate: {churn_rate*100:.1f}%/mo."
        )

        if scenarios["bear"] < current_mrr * 0.5:
            findings.append(_finding(
                "growth_accounting", "medium",
                f"Bear scenario shows >50% revenue decline (${scenarios['bear']:.0f} vs ${current_mrr:.0f})",
                analysis,
                "Reduce churn rate (biggest lever in bear scenario). "
                "Diversify revenue with expansion MRR.",
                "Focus on churn reduction: review churn_detection.py signals.",
                "Revenue vulnerability in downside scenario.",
                ["mandarin/churn_detection.py", "mandarin/payment.py"],
            ))

    except Exception as e:
        logger.debug("Scenario model analyzer failed: %s", e)

    return findings


# ── 5. Decision Log Health ───────────────────────────────────────────


def _analyze_decision_log_health(conn) -> list[dict]:
    """Decision log health: unmeasured outcomes, decision frequency, quality signals."""
    findings = []

    try:
        # Check if pi_decision_log exists and has data
        total_decisions = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_decision_log
        """, default=0)

        if total_decisions == 0:
            findings.append(_finding(
                "strategic", "low",
                "No decisions logged in decision log",
                "The pi_decision_log is empty. Strategic, product, and "
                "operational decisions should be logged with rationale for "
                "future reference and outcome measurement.",
                "Log key decisions as they are made, including rationale "
                "and expected outcome.",
                "Start logging decisions in pi_decision_log table.",
                "No decision audit trail exists.",
                ["mandarin/web/admin_routes.py"],
            ))
            return findings

        # Check for decisions without outcome measurement
        unmeasured = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_decision_log
            WHERE outcome_notes IS NULL
              AND created_at <= datetime('now', '-30 days')
        """, default=0)

        if unmeasured > 0:
            findings.append(_finding(
                "strategic", "low",
                f"{unmeasured} decision(s) older than 30 days with no measured outcome",
                f"{unmeasured} decisions were made more than 30 days ago but "
                f"their outcomes haven't been recorded. Decision quality "
                f"improves when outcomes are tracked.",
                "Review past decisions and record what actually happened.",
                "Update outcome_notes in pi_decision_log for old decisions.",
                "Unmeasured decisions can't improve future decision quality.",
                ["mandarin/web/admin_routes.py"],
            ))

        # Check for decision recency
        recent = _safe_scalar(conn, """
            SELECT COUNT(*) FROM pi_decision_log
            WHERE created_at >= datetime('now', '-30 days')
        """, default=0)

        if recent == 0 and total_decisions > 0:
            findings.append(_finding(
                "strategic", "medium",
                "No decisions logged in the last 30 days",
                "The last decision in the log is over 30 days old. "
                "For a pre-launch product, key decisions should be "
                "happening regularly.",
                "Log strategic decisions (pricing, feature priority, "
                "competitive response) as they occur.",
                "Check pi_decision_log recency and add recent decisions.",
                "Decision frequency reflects strategic activity level.",
                ["mandarin/web/admin_routes.py"],
            ))

    except Exception as e:
        logger.debug("Decision log analyzer failed: %s", e)

    return findings


# ── 6. CAC Health (placeholder) ──────────────────────────────────────


def _analyze_cac_health(conn) -> list[dict]:
    """CAC health: customer acquisition cost tracking and LTV/CAC ratio."""
    findings = []

    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        if "acquisition_cost" not in tables:
            findings.append(_finding(
                "growth_accounting", "low",
                "No CAC tracking infrastructure",
                "Customer acquisition cost (CAC) is not tracked. For organic-only "
                "growth this is acceptable, but CAC tracking should be ready "
                "before any paid acquisition begins.",
                "Create acquisition_cost table to track spend by channel when "
                "paid acquisition starts.",
                "Run migration to create acquisition_cost table.",
                "Cannot compute LTV/CAC ratio without CAC data.",
                ["mandarin/db/core.py"],
            ))
    except Exception:
        pass

    return findings


ANALYZERS = [
    _analyze_growth_accounting,
    _analyze_revenue_waterfall,
    _analyze_cohort_economics,
    _analyze_scenario_model,
    _analyze_decision_log_health,
    _analyze_cac_health,
]
