"""Financial monitoring — Stripe anomaly detection + business metrics.

Monitor revenue, detect anomalies (churn spikes, failed payment clusters,
suspicious patterns), generate weekly business digest. Not making decisions —
surfacing signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Configurable thresholds
THRESHOLDS = {
    "failed_payment_multiplier": 2.0,
    "refund_cluster_count": 3,
    "revenue_drop_pct": 10,
    "min_data_days": 7,
    "churn_session_threshold": 2,
}


@dataclass
class RevenueSnapshot:
    mrr: float = 0.0
    arr: float = 0.0
    total_customers: int = 0
    paying_customers: int = 0
    free_users: int = 0
    conversion_rate: float = 0.0
    avg_revenue_per_user: float = 0.0
    computed_at: str = ""

    def __post_init__(self):
        if not self.computed_at:
            self.computed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ChurnReport:
    churn_rate: float = 0.0
    churned_users: list[dict] = field(default_factory=list)
    at_risk_users: list[dict] = field(default_factory=list)
    reasons: dict = field(default_factory=dict)
    trend: str = "stable"  # improving, stable, worsening


@dataclass
class Anomaly:
    anomaly_type: str
    severity: str  # low, medium, high, critical
    detail: str
    affected_users: int = 0
    detected_at: str = ""

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class WeeklyDigest:
    period: str
    revenue: RevenueSnapshot
    churn: ChurnReport
    anomalies: list[Anomaly] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)


# Pricing tiers (from settings.py, duplicated here for independence)
_TIER_PRICES = {
    "monthly": 9.0,
    "pro": 9.0,
    "annual": 79.0,
    "institutional": 199.0,
}


class RevenueMetrics:
    """Compute revenue metrics from database."""

    def compute(self, conn) -> RevenueSnapshot:
        total = conn.execute("SELECT COUNT(*) as cnt FROM user").fetchone()
        total_count = total["cnt"] if total else 0

        paying = conn.execute("""
            SELECT subscription_tier, COUNT(*) as cnt FROM user
            WHERE subscription_tier IS NOT NULL AND subscription_tier != 'free'
            AND subscription_status = 'active'
            GROUP BY subscription_tier
        """).fetchall()

        mrr = 0.0
        paying_count = 0
        for row in paying:
            tier = row["subscription_tier"]
            cnt = row["cnt"]
            paying_count += cnt
            price = _TIER_PRICES.get(tier, 0)
            if tier == "annual":
                mrr += (price / 12) * cnt
            else:
                mrr += price * cnt

        free_count = total_count - paying_count
        conversion = paying_count / max(total_count, 1)
        arpu = mrr / max(paying_count, 1)

        return RevenueSnapshot(
            mrr=round(mrr, 2),
            arr=round(mrr * 12, 2),
            total_customers=total_count,
            paying_customers=paying_count,
            free_users=free_count,
            conversion_rate=round(conversion, 4),
            avg_revenue_per_user=round(arpu, 2),
        )


class ChurnAnalyzer:
    """Analyze churn patterns."""

    def analyze(self, conn, days: int = 30) -> ChurnReport:
        # Users who cancelled or lapsed
        churned = []
        try:
            rows = conn.execute("""
                SELECT id, email, subscription_tier, subscription_status
                FROM user
                WHERE subscription_status IN ('cancelled', 'expired', 'past_due')
                AND subscription_tier != 'free'
            """).fetchall()
            churned = [{"user_id": r["id"], "email": r["email"],
                        "tier": r["subscription_tier"], "status": r["subscription_status"]}
                       for r in rows]
        except Exception:
            pass

        # Total paid users (active + churned) for rate calculation
        total_paid = conn.execute("""
            SELECT COUNT(*) as cnt FROM user
            WHERE subscription_tier IS NOT NULL AND subscription_tier != 'free'
        """).fetchone()
        total = total_paid["cnt"] if total_paid else 0
        rate = len(churned) / max(total, 1)

        # At-risk users: paid, declining engagement
        at_risk = []
        try:
            paid_users = conn.execute("""
                SELECT id, email, subscription_tier FROM user
                WHERE subscription_status = 'active' AND subscription_tier != 'free'
            """).fetchall()
            for u in paid_users:
                sessions = conn.execute("""
                    SELECT COUNT(*) as cnt FROM session_log
                    WHERE user_id = ? AND session_outcome = 'completed'
                    AND started_at >= datetime('now', '-7 days')
                """, (u["id"],)).fetchone()
                if sessions and sessions["cnt"] < THRESHOLDS["churn_session_threshold"]:
                    at_risk.append({"user_id": u["id"], "email": u["email"],
                                    "sessions_this_week": sessions["cnt"]})
        except Exception:
            pass

        # Reason breakdown
        reasons = {}
        for u in churned:
            status = u["status"]
            reasons[status] = reasons.get(status, 0) + 1

        return ChurnReport(
            churn_rate=round(rate, 4),
            churned_users=churned,
            at_risk_users=at_risk,
            reasons=reasons,
            trend="stable",
        )


class PaymentAnomalyDetector:
    """Detect payment anomalies."""

    def detect(self, conn, days: int = 7) -> list[Anomaly]:
        anomalies = []

        # FAILED_PAYMENT_SPIKE
        try:
            recent_failed = conn.execute("""
                SELECT COUNT(*) as cnt FROM lifecycle_event
                WHERE event_type = 'payment_failed'
                AND created_at >= datetime('now', ? || ' days')
            """, (f"-{days}",)).fetchone()
            baseline = conn.execute("""
                SELECT COUNT(*) as cnt FROM lifecycle_event
                WHERE event_type = 'payment_failed'
                AND created_at >= datetime('now', ? || ' days')
                AND created_at < datetime('now', ? || ' days')
            """, (f"-{days * 2}", f"-{days}")).fetchone()

            recent = recent_failed["cnt"] if recent_failed else 0
            base = baseline["cnt"] if baseline else 0
            if base > 0 and recent > base * THRESHOLDS["failed_payment_multiplier"]:
                anomalies.append(Anomaly(
                    "FAILED_PAYMENT_SPIKE", "high",
                    f"Failed payments: {recent} (vs {base} baseline)",
                    affected_users=recent,
                ))
        except Exception:
            pass

        # REFUND_CLUSTER
        try:
            refunds = conn.execute("""
                SELECT COUNT(*) as cnt FROM lifecycle_event
                WHERE event_type = 'refund'
                AND created_at >= datetime('now', '-24 hours')
            """).fetchone()
            if refunds and refunds["cnt"] >= THRESHOLDS["refund_cluster_count"]:
                anomalies.append(Anomaly(
                    "REFUND_CLUSTER", "high",
                    f"{refunds['cnt']} refunds in last 24 hours",
                    affected_users=refunds["cnt"],
                ))
        except Exception:
            pass

        # REVENUE_DROP
        try:
            # Compare this week's new subs vs last week
            this_week = conn.execute("""
                SELECT COUNT(*) as cnt FROM lifecycle_event
                WHERE event_type = 'subscription_created'
                AND created_at >= datetime('now', '-7 days')
            """).fetchone()
            last_week = conn.execute("""
                SELECT COUNT(*) as cnt FROM lifecycle_event
                WHERE event_type = 'subscription_created'
                AND created_at >= datetime('now', '-14 days')
                AND created_at < datetime('now', '-7 days')
            """).fetchone()

            tw = this_week["cnt"] if this_week else 0
            lw = last_week["cnt"] if last_week else 0
            if lw > 0:
                drop_pct = ((lw - tw) / lw) * 100
                if drop_pct >= THRESHOLDS["revenue_drop_pct"]:
                    anomalies.append(Anomaly(
                        "REVENUE_DROP", "medium",
                        f"New subscriptions down {drop_pct:.0f}% week-over-week ({tw} vs {lw})",
                    ))
        except Exception:
            pass

        # SUSPICIOUS_SIGNUPS
        try:
            signups = conn.execute("""
                SELECT COUNT(*) as cnt FROM user
                WHERE created_at >= datetime('now', '-24 hours')
            """).fetchone()
            if signups and signups["cnt"] > 20:
                anomalies.append(Anomaly(
                    "SUSPICIOUS_SIGNUPS", "medium",
                    f"{signups['cnt']} signups in last 24 hours",
                    affected_users=signups["cnt"],
                ))
        except Exception:
            pass

        return anomalies


class FinancialDigest:
    """Generate weekly financial digest."""

    def generate_weekly(self, conn) -> WeeklyDigest:
        revenue = RevenueMetrics().compute(conn)
        churn = ChurnAnalyzer().analyze(conn)
        anomalies = PaymentAnomalyDetector().detect(conn)

        highlights = []
        if revenue.paying_customers > 0:
            highlights.append(f"MRR: ${revenue.mrr:.2f} ({revenue.paying_customers} paying)")
        if revenue.conversion_rate > 0:
            highlights.append(f"Conversion rate: {revenue.conversion_rate:.1%}")
        if churn.churn_rate < 0.05:
            highlights.append("Churn rate healthy")

        action_items = []
        if churn.at_risk_users:
            action_items.append(f"{len(churn.at_risk_users)} users at churn risk — review engagement")
        if churn.churned_users:
            action_items.append(f"{len(churn.churned_users)} churned users — consider win-back campaign")
        for a in anomalies:
            if a.severity in ("high", "critical"):
                action_items.append(f"[{a.severity.upper()}] {a.detail}")

        period = datetime.now(timezone.utc).strftime("Week of %Y-%m-%d")

        return WeeklyDigest(
            period=period, revenue=revenue, churn=churn,
            anomalies=anomalies, highlights=highlights, action_items=action_items,
        )


class FinancialMonitor:
    """Main interface for financial monitoring."""

    def __init__(self, conn=None):
        self.conn = conn

    def snapshot(self) -> RevenueSnapshot:
        if not self.conn:
            return RevenueSnapshot()
        return RevenueMetrics().compute(self.conn)

    def check_anomalies(self) -> list[Anomaly]:
        if not self.conn:
            return []
        return PaymentAnomalyDetector().detect(self.conn)

    def weekly_digest(self) -> WeeklyDigest:
        if not self.conn:
            return WeeklyDigest(period="", revenue=RevenueSnapshot(), churn=ChurnReport())
        return FinancialDigest().generate_weekly(self.conn)

    def format_digest(self, digest: WeeklyDigest) -> str:
        lines = [f"Financial Digest — {digest.period}", ""]

        lines.append(f"MRR: ${digest.revenue.mrr:.2f} | ARR: ${digest.revenue.arr:.2f}")
        lines.append(f"Customers: {digest.revenue.total_customers} ({digest.revenue.paying_customers} paying)")
        lines.append(f"Conversion: {digest.revenue.conversion_rate:.1%}")
        lines.append("")

        if digest.highlights:
            lines.append("Highlights:")
            for h in digest.highlights:
                lines.append(f"  + {h}")
            lines.append("")

        if digest.anomalies:
            lines.append("Anomalies:")
            for a in digest.anomalies:
                lines.append(f"  [{a.severity.upper()}] {a.detail}")
            lines.append("")

        if digest.action_items:
            lines.append("Action items:")
            for item in digest.action_items:
                lines.append(f"  - {item}")

        return "\n".join(lines)

    def format_digest_html(self, digest: WeeklyDigest) -> str:
        parts = [
            '<div style="font-family: Source Sans 3, sans-serif; max-width: 600px;">',
            f'<h2 style="color: #1a7a6d;">Financial Digest — {digest.period}</h2>',
            '<table style="border-collapse: collapse; width: 100%;">',
            f'<tr><td><strong>MRR</strong></td><td>${digest.revenue.mrr:.2f}</td></tr>',
            f'<tr><td><strong>Paying</strong></td><td>{digest.revenue.paying_customers}</td></tr>',
            f'<tr><td><strong>Conversion</strong></td><td>{digest.revenue.conversion_rate:.1%}</td></tr>',
            '</table>',
        ]
        if digest.action_items:
            parts.append('<h3>Action Items</h3><ul>')
            for item in digest.action_items:
                parts.append(f'<li>{item}</li>')
            parts.append('</ul>')
        parts.append('</div>')
        return "\n".join(parts)
