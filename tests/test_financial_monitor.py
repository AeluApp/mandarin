"""Tests for mandarin.openclaw.financial_monitor — revenue, churn, anomalies, digest."""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone, UTC

from mandarin.openclaw.financial_monitor import (
    Anomaly,
    ChurnAnalyzer,
    ChurnReport,
    FinancialDigest,
    FinancialMonitor,
    PaymentAnomalyDetector,
    RevenueMetrics,
    RevenueSnapshot,
    THRESHOLDS,
    WeeklyDigest,
)


def _make_conn():
    from tests.shared_db import make_test_db
    return make_test_db()


def _ts(days_ago=0, hours_ago=0):
    dt = datetime.now(UTC) - timedelta(days=days_ago, hours=hours_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _add_user(conn, uid, tier="free", status="active", email=None, days_ago=30):
    email = email or f"u{uid}@test.com"
    created = _ts(days_ago)
    conn.execute(
        "INSERT OR REPLACE INTO user (id, email, password_hash, subscription_tier, subscription_status, created_at) "
        "VALUES (?, ?, 'test_hash', ?, ?, ?)",
        (uid, email, tier, status, created),
    )
    conn.commit()


# ── Dataclass tests ───────────────────────────────────────

class TestRevenueSnapshot(unittest.TestCase):
    def test_defaults(self):
        rs = RevenueSnapshot()
        self.assertEqual(rs.mrr, 0.0)
        self.assertEqual(rs.paying_customers, 0)
        self.assertNotEqual(rs.computed_at, "")

    def test_auto_timestamp(self):
        rs = RevenueSnapshot()
        datetime.strptime(rs.computed_at, "%Y-%m-%d %H:%M:%S")


class TestChurnReport(unittest.TestCase):
    def test_defaults(self):
        cr = ChurnReport()
        self.assertEqual(cr.churn_rate, 0.0)
        self.assertEqual(cr.churned_users, [])
        self.assertEqual(cr.trend, "stable")


class TestAnomaly(unittest.TestCase):
    def test_defaults(self):
        a = Anomaly("TEST", "high", "detail")
        self.assertNotEqual(a.detected_at, "")
        self.assertEqual(a.affected_users, 0)


class TestWeeklyDigest(unittest.TestCase):
    def test_construction(self):
        d = WeeklyDigest(
            period="Week of 2026-03-10",
            revenue=RevenueSnapshot(),
            churn=ChurnReport(),
        )
        self.assertEqual(d.highlights, [])
        self.assertEqual(d.action_items, [])


class TestThresholds(unittest.TestCase):
    def test_all_thresholds_present(self):
        expected_keys = {"failed_payment_multiplier", "refund_cluster_count",
                         "revenue_drop_pct", "min_data_days", "churn_session_threshold"}
        self.assertEqual(set(THRESHOLDS.keys()), expected_keys)

    def test_thresholds_positive(self):
        for k, v in THRESHOLDS.items():
            self.assertGreater(v, 0, f"Threshold {k} should be positive")


# ── RevenueMetrics ────────────────────────────────────────

class TestRevenueMetrics(unittest.TestCase):
    def test_empty_db(self):
        conn = _make_conn()
        # make_test_db() seeds a bootstrap free user (id=1)
        rs = RevenueMetrics().compute(conn)
        self.assertEqual(rs.total_customers, 1)
        self.assertEqual(rs.mrr, 0.0)
        self.assertEqual(rs.paying_customers, 0)

    def test_free_users_only(self):
        conn = _make_conn()
        _add_user(conn, 1, "free")
        _add_user(conn, 2, "free")
        rs = RevenueMetrics().compute(conn)
        self.assertEqual(rs.total_customers, 2)
        self.assertEqual(rs.paying_customers, 0)
        self.assertEqual(rs.free_users, 2)
        self.assertEqual(rs.mrr, 0.0)

    def test_monthly_subscriber(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        rs = RevenueMetrics().compute(conn)
        self.assertEqual(rs.paying_customers, 1)
        self.assertAlmostEqual(rs.mrr, 9.0, places=2)
        self.assertAlmostEqual(rs.arr, 108.0, places=2)

    def test_annual_subscriber(self):
        conn = _make_conn()
        # 'paid' tier maps to $9/month in _TIER_PRICES
        _add_user(conn, 1, "paid", "active")
        rs = RevenueMetrics().compute(conn)
        self.assertAlmostEqual(rs.mrr, 9.0, places=2)

    def test_mixed_tiers(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        _add_user(conn, 2, "paid", "active")
        _add_user(conn, 3, "free", "active")
        rs = RevenueMetrics().compute(conn)
        self.assertEqual(rs.total_customers, 3)
        self.assertEqual(rs.paying_customers, 2)
        self.assertEqual(rs.free_users, 1)
        expected_mrr = 9.0 + 9.0
        self.assertAlmostEqual(rs.mrr, round(expected_mrr, 2), places=1)

    def test_conversion_rate(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        _add_user(conn, 2, "free")
        _add_user(conn, 3, "free")
        _add_user(conn, 4, "free")
        rs = RevenueMetrics().compute(conn)
        self.assertAlmostEqual(rs.conversion_rate, 0.25, places=2)

    def test_cancelled_not_counted(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "cancelled")
        rs = RevenueMetrics().compute(conn)
        self.assertEqual(rs.paying_customers, 0)
        self.assertEqual(rs.mrr, 0.0)


# ── ChurnAnalyzer ─────────────────────────────────────────

class TestChurnAnalyzer(unittest.TestCase):
    def test_no_churn(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        cr = ChurnAnalyzer().analyze(conn)
        self.assertEqual(len(cr.churned_users), 0)
        self.assertEqual(cr.churn_rate, 0.0)

    def test_churned_user(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "cancelled")
        _add_user(conn, 2, "paid", "active")
        cr = ChurnAnalyzer().analyze(conn)
        self.assertEqual(len(cr.churned_users), 1)
        self.assertEqual(cr.churned_users[0]["status"], "cancelled")
        self.assertGreater(cr.churn_rate, 0)

    def test_at_risk_low_sessions(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        # No sessions this week => at risk
        cr = ChurnAnalyzer().analyze(conn)
        self.assertEqual(len(cr.at_risk_users), 1)

    def test_at_risk_not_free(self):
        conn = _make_conn()
        _add_user(conn, 1, "free", "active")
        cr = ChurnAnalyzer().analyze(conn)
        # Free users should not be in at_risk
        self.assertEqual(len(cr.at_risk_users), 0)

    def test_reason_breakdown(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "cancelled")
        _add_user(conn, 2, "paid", "expired")
        _add_user(conn, 3, "paid", "cancelled")
        cr = ChurnAnalyzer().analyze(conn)
        self.assertEqual(cr.reasons.get("cancelled", 0), 2)
        self.assertEqual(cr.reasons.get("expired", 0), 1)

    def test_expired_counted_as_churn(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "expired")
        cr = ChurnAnalyzer().analyze(conn)
        self.assertEqual(len(cr.churned_users), 1)

    def test_past_due_counted_as_churn(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "past_due")
        cr = ChurnAnalyzer().analyze(conn)
        self.assertEqual(len(cr.churned_users), 1)


# ── PaymentAnomalyDetector ───────────────────────────────

class TestPaymentAnomalyDetector(unittest.TestCase):
    def test_no_anomalies(self):
        conn = _make_conn()
        anomalies = PaymentAnomalyDetector().detect(conn)
        self.assertEqual(anomalies, [])

    def test_failed_payment_spike(self):
        conn = _make_conn()
        # Baseline: 2 failures last week
        for _ in range(2):
            conn.execute(
                "INSERT INTO lifecycle_event (event_type, created_at) VALUES ('payment_failed', ?)",
                (_ts(10),),
            )
        # Recent: 5 failures this week (>2x baseline)
        for _ in range(5):
            conn.execute(
                "INSERT INTO lifecycle_event (event_type, created_at) VALUES ('payment_failed', ?)",
                (_ts(1),),
            )
        conn.commit()
        anomalies = PaymentAnomalyDetector().detect(conn)
        types = [a.anomaly_type for a in anomalies]
        self.assertIn("FAILED_PAYMENT_SPIKE", types)

    def test_refund_cluster(self):
        conn = _make_conn()
        for _ in range(5):
            conn.execute(
                "INSERT INTO lifecycle_event (event_type, created_at) VALUES ('refund', ?)",
                (_ts(0, hours_ago=1),),
            )
        conn.commit()
        anomalies = PaymentAnomalyDetector().detect(conn)
        types = [a.anomaly_type for a in anomalies]
        self.assertIn("REFUND_CLUSTER", types)

    def test_refund_below_threshold(self):
        conn = _make_conn()
        for _ in range(2):
            conn.execute(
                "INSERT INTO lifecycle_event (event_type, created_at) VALUES ('refund', ?)",
                (_ts(0, hours_ago=1),),
            )
        conn.commit()
        anomalies = PaymentAnomalyDetector().detect(conn)
        types = [a.anomaly_type for a in anomalies]
        self.assertNotIn("REFUND_CLUSTER", types)

    def test_revenue_drop(self):
        conn = _make_conn()
        # Last week: 10 new subs
        for _ in range(10):
            conn.execute(
                "INSERT INTO lifecycle_event (event_type, created_at) VALUES ('subscription_created', ?)",
                (_ts(10),),
            )
        # This week: 5 new subs (50% drop)
        for _ in range(5):
            conn.execute(
                "INSERT INTO lifecycle_event (event_type, created_at) VALUES ('subscription_created', ?)",
                (_ts(1),),
            )
        conn.commit()
        anomalies = PaymentAnomalyDetector().detect(conn)
        types = [a.anomaly_type for a in anomalies]
        self.assertIn("REVENUE_DROP", types)

    def test_suspicious_signups(self):
        conn = _make_conn()
        for i in range(25):
            conn.execute(
                "INSERT INTO user (email, password_hash, created_at) VALUES (?, 'test_hash', ?)",
                (f"bot{i}@spam.com", _ts(0, hours_ago=1)),
            )
        conn.commit()
        anomalies = PaymentAnomalyDetector().detect(conn)
        types = [a.anomaly_type for a in anomalies]
        self.assertIn("SUSPICIOUS_SIGNUPS", types)

    def test_no_suspicious_normal_signup(self):
        conn = _make_conn()
        for i in range(5):
            conn.execute(
                "INSERT INTO user (email, password_hash, created_at) VALUES (?, 'test_hash', ?)",
                (f"real{i}@user.com", _ts(0, hours_ago=1)),
            )
        conn.commit()
        anomalies = PaymentAnomalyDetector().detect(conn)
        types = [a.anomaly_type for a in anomalies]
        self.assertNotIn("SUSPICIOUS_SIGNUPS", types)


# ── FinancialDigest ───────────────────────────────────────

class TestFinancialDigest(unittest.TestCase):
    def test_weekly_digest_empty(self):
        conn = _make_conn()
        digest = FinancialDigest().generate_weekly(conn)
        self.assertIsInstance(digest, WeeklyDigest)
        self.assertIn("Week of", digest.period)

    def test_highlights_with_paying_users(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        _add_user(conn, 2, "free")
        digest = FinancialDigest().generate_weekly(conn)
        self.assertTrue(any("MRR" in h for h in digest.highlights))

    def test_action_items_with_at_risk(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        # No sessions = at risk
        digest = FinancialDigest().generate_weekly(conn)
        self.assertTrue(any("churn risk" in a for a in digest.action_items))

    def test_action_items_with_churned(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "cancelled")
        digest = FinancialDigest().generate_weekly(conn)
        self.assertTrue(any("churned" in a.lower() for a in digest.action_items))


# ── FinancialMonitor (main interface) ─────────────────────

class TestFinancialMonitor(unittest.TestCase):
    def test_no_conn_snapshot(self):
        fm = FinancialMonitor()
        snap = fm.snapshot()
        self.assertEqual(snap.mrr, 0.0)

    def test_no_conn_anomalies(self):
        fm = FinancialMonitor()
        self.assertEqual(fm.check_anomalies(), [])

    def test_no_conn_digest(self):
        fm = FinancialMonitor()
        digest = fm.weekly_digest()
        self.assertEqual(digest.period, "")

    def test_with_conn_snapshot(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        fm = FinancialMonitor(conn)
        snap = fm.snapshot()
        self.assertAlmostEqual(snap.mrr, 9.0, places=2)

    def test_format_digest_text(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        fm = FinancialMonitor(conn)
        digest = fm.weekly_digest()
        text = fm.format_digest(digest)
        self.assertIn("Financial Digest", text)
        self.assertIn("MRR", text)
        self.assertIn("Customers", text)

    def test_format_digest_html(self):
        conn = _make_conn()
        _add_user(conn, 1, "paid", "active")
        fm = FinancialMonitor(conn)
        digest = fm.weekly_digest()
        html = fm.format_digest_html(digest)
        self.assertIn("<div", html)
        self.assertIn("Financial Digest", html)
        self.assertIn("MRR", html)

    def test_format_digest_empty(self):
        fm = FinancialMonitor()
        digest = fm.weekly_digest()
        text = fm.format_digest(digest)
        self.assertIn("$0.00", text)


if __name__ == "__main__":
    unittest.main()
