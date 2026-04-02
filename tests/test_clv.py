"""Tests for Customer Lifetime Value and cohort retention analytics.

Covers: compute_cohort_retention, compute_ltv, predict_ltv_segment
from mandarin/analytics/clv.py.
"""

import sqlite3
import unittest

from mandarin.analytics.clv import (
    compute_cohort_retention,
    compute_ltv,
    predict_ltv_segment,
)
from tests.shared_db import make_test_db


def _make_clv_db():
    """Create in-memory DB with the full production schema + payment_event."""
    conn = make_test_db()
    # PHANTOM TABLE: payment_event is not in the production migration chain.
    # TODO: Add payment_event to schema.sql when payment processing is activated.
    conn.execute("""CREATE TABLE IF NOT EXISTS payment_event (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount_cents INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'succeeded',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    return conn


class TestComputeCohortRetention(unittest.TestCase):
    """Tests for compute_cohort_retention()."""

    def setUp(self):
        self.conn = _make_clv_db()

    def tearDown(self):
        self.conn.close()

    def test_two_users_same_cohort(self):
        """Two users in the same month cohort returns a single cohort entry."""
        self.conn.executescript("""
            INSERT OR REPLACE INTO user (id, email, password_hash, created_at)
            VALUES (1, 'a@test.com', 'h', '2025-06-01 10:00:00');
            INSERT OR REPLACE INTO user (id, email, password_hash, created_at)
            VALUES (2, 'b@test.com', 'h', '2025-06-15 12:00:00');

            -- User 1 has a session on day 1 after signup
            INSERT INTO session_log (user_id, started_at, early_exit, duration_seconds)
            VALUES (1, '2025-06-02 10:00:00', 0, 600);

            -- User 2 has a session on day 1 after signup
            INSERT INTO session_log (user_id, started_at, early_exit, duration_seconds)
            VALUES (2, '2025-06-16 12:00:00', 0, 300);
        """)

        results = compute_cohort_retention(self.conn, cohort_month="2025-06")
        self.assertEqual(len(results), 1)

        cohort = results[0]
        self.assertEqual(cohort["cohort"], "2025-06")
        self.assertEqual(cohort["users"], 2)
        # day_1 retention: both users had sessions on day 1
        self.assertEqual(cohort["day_1"], 100.0)
        # All expected retention keys present
        for day in [1, 7, 14, 30, 60, 90]:
            self.assertIn(f"day_{day}", cohort)

    def test_empty_tables(self):
        """No session data returns cohorts with 0% retention (bootstrap user exists)."""
        results = compute_cohort_retention(self.conn)
        # make_test_db() seeds a bootstrap user, so we get one cohort with zero retention
        for cohort in results:
            self.assertEqual(cohort["day_1"], 0.0)
            self.assertEqual(cohort["day_7"], 0.0)

    def test_users_no_sessions(self):
        """Users exist but no sessions still produces cohort with 0% retention."""
        self.conn.execute(
            "INSERT OR REPLACE INTO user (id, email, password_hash, created_at) "
            "VALUES (2, 'solo@test.com', 'test_hash', '2025-07-01 00:00:00')"
        )
        results = compute_cohort_retention(self.conn)
        self.assertTrue(len(results) >= 1)
        july_cohort = [r for r in results if r["cohort"] == "2025-07"]
        self.assertEqual(len(july_cohort), 1)
        self.assertEqual(july_cohort[0]["users"], 1)
        self.assertEqual(july_cohort[0]["day_1"], 0.0)


class TestComputeLtv(unittest.TestCase):
    """Tests for compute_ltv()."""

    def setUp(self):
        self.conn = _make_clv_db()

    def tearDown(self):
        self.conn.close()

    def test_individual_ltv_with_payments(self):
        """Individual LTV returns correct revenue and ARPU for seeded payments."""
        self.conn.executescript("""
            INSERT OR REPLACE INTO user (id, email, password_hash, created_at)
            VALUES (1, 'payer@test.com', 'h', '2025-01-01 00:00:00');

            INSERT INTO payment_event (user_id, amount_cents, status)
            VALUES (1, 1000, 'succeeded');
            INSERT INTO payment_event (user_id, amount_cents, status)
            VALUES (1, 1000, 'succeeded');
            INSERT INTO payment_event (user_id, amount_cents, status)
            VALUES (1, 500, 'failed');

            INSERT INTO session_log (user_id, started_at) VALUES (1, '2025-01-01 10:00:00');
            INSERT INTO session_log (user_id, started_at) VALUES (1, '2025-03-01 10:00:00');
        """)

        result = compute_ltv(self.conn, user_id=1)
        self.assertEqual(result["user_id"], 1)
        # Two succeeded payments of $10 each = $20
        self.assertAlmostEqual(result["total_revenue"], 20.0, places=2)
        self.assertGreater(result["months_active"], 0)
        self.assertIn("monthly_arpu", result)

    def test_aggregate_ltv(self):
        """Aggregate LTV (no user_id) returns totals across all users."""
        self.conn.executescript("""
            INSERT OR REPLACE INTO user (id, email, password_hash, created_at)
            VALUES (1, 'u1@test.com', 'h', '2025-01-01');
            INSERT OR REPLACE INTO user (id, email, password_hash, created_at)
            VALUES (2, 'u2@test.com', 'h', '2025-01-01');

            INSERT INTO payment_event (user_id, amount_cents, status)
            VALUES (1, 2000, 'succeeded');
            INSERT INTO payment_event (user_id, amount_cents, status)
            VALUES (2, 3000, 'succeeded');

            INSERT INTO session_log (user_id, started_at) VALUES (1, '2025-01-01');
            INSERT INTO session_log (user_id, started_at) VALUES (1, '2025-02-01');
            INSERT INTO session_log (user_id, started_at) VALUES (2, '2025-01-01');
            INSERT INTO session_log (user_id, started_at) VALUES (2, '2025-03-01');
        """)

        result = compute_ltv(self.conn)
        self.assertIn("total_users", result)
        self.assertEqual(result["total_users"], 2)
        # $20 + $30 = $50
        self.assertAlmostEqual(result["total_revenue"], 50.0, places=2)
        self.assertIn("estimated_ltv", result)

    def test_empty_tables_no_error(self):
        """Empty payment and session tables return graceful result."""
        result = compute_ltv(self.conn)
        # Should not crash; returns dict (possibly with zeroes or error key)
        self.assertIsInstance(result, dict)


class TestPredictLtvSegment(unittest.TestCase):
    """Tests for predict_ltv_segment()."""

    def setUp(self):
        self.conn = _make_clv_db()

    def tearDown(self):
        self.conn.close()

    def test_high_engagement_user(self):
        """User with 5+ sessions, 70%+ completion, 300s+ avg -> 'high'."""
        self.conn.execute(
            "INSERT OR REPLACE INTO user (id, email, password_hash, created_at) "
            "VALUES (1, 'power@test.com', 'h', '2025-04-01 00:00:00')"
        )
        # 6 sessions, all completed, 400s each — within 14 days of signup
        for i in range(6):
            day = i + 1
            self.conn.execute(
                "INSERT INTO session_log (user_id, started_at, early_exit, duration_seconds) "
                "VALUES (1, ?, 0, 400)",
                (f"2025-04-{day + 1:02d} 10:00:00",),
            )
        self.conn.commit()

        self.assertEqual(predict_ltv_segment(self.conn, user_id=1), "high")

    def test_low_engagement_user(self):
        """User with only 1 session -> 'low'."""
        self.conn.execute(
            "INSERT OR REPLACE INTO user (id, email, password_hash, created_at) "
            "VALUES (1, 'casual@test.com', 'h', '2025-04-01 00:00:00')"
        )
        self.conn.execute(
            "INSERT INTO session_log (user_id, started_at, early_exit, duration_seconds) "
            "VALUES (1, '2025-04-02 10:00:00', 1, 60)"
        )
        self.conn.commit()

        self.assertEqual(predict_ltv_segment(self.conn, user_id=1), "low")

    def test_medium_engagement_user(self):
        """User with moderate engagement -> 'medium'."""
        self.conn.execute(
            "INSERT OR REPLACE INTO user (id, email, password_hash, created_at) "
            "VALUES (1, 'mid@test.com', 'h', '2025-04-01 00:00:00')"
        )
        # 3 sessions, 2/3 completed (67% < 70%), 200s avg
        # early_exit=0 means completed, early_exit=1 means not completed
        for i, (comp, dur) in enumerate([(0, 200), (0, 200), (1, 200)]):
            self.conn.execute(
                "INSERT INTO session_log (user_id, started_at, early_exit, duration_seconds) "
                "VALUES (1, ?, ?, ?)",
                (f"2025-04-{i + 2:02d} 10:00:00", comp, dur),
            )
        self.conn.commit()

        self.assertEqual(predict_ltv_segment(self.conn, user_id=1), "medium")

    def test_no_sessions_returns_unknown(self):
        """User with zero sessions -> 'unknown'."""
        self.conn.execute(
            "INSERT OR REPLACE INTO user (id, email, password_hash, created_at) "
            "VALUES (1, 'ghost@test.com', 'h', '2025-04-01 00:00:00')"
        )
        self.conn.commit()

        self.assertEqual(predict_ltv_segment(self.conn, user_id=1), "unknown")

    def test_nonexistent_user_returns_unknown(self):
        """Querying a user_id not in the DB -> 'unknown'."""
        self.assertEqual(predict_ltv_segment(self.conn, user_id=999), "unknown")


if __name__ == "__main__":
    unittest.main()
