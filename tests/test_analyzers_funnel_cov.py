"""Tests for mandarin.intelligence.analyzers_funnel — activation funnel analysis.

Covers:
- FUNNEL_STAGES definition
- _count_visits / _count_signups / _count_email_verified / etc.
- _STAGE_COUNTERS mapping
- analyze_funnel
- _fix_auto_test_registration_page
- _fix_resend_verification
- run_check / ANALYZERS
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
    """Fresh DB with full schema for funnel analyzer tests."""
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    c.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, is_admin)
        VALUES (1, 'admin@example.com', 'hash', 'Admin', 1)
    """)
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


class TestFunnelStages:
    def test_stages_defined(self):
        from mandarin.intelligence.analyzers_funnel import FUNNEL_STAGES
        assert isinstance(FUNNEL_STAGES, list)
        assert len(FUNNEL_STAGES) >= 7
        for stage in FUNNEL_STAGES:
            assert "from" in stage
            assert "to" in stage
            assert "threshold" in stage

    def test_stage_counters_mapping(self):
        from mandarin.intelligence.analyzers_funnel import _STAGE_COUNTERS
        assert "visit" in _STAGE_COUNTERS
        assert "signup" in _STAGE_COUNTERS
        assert "subscription" in _STAGE_COUNTERS


class TestStageCounts:
    def test_count_visits_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_visits
        count = _count_visits(conn, "-7 days")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_signups_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_signups
        count = _count_signups(conn, "-7 days")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_email_verified_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_email_verified
        count = _count_email_verified(conn, "-7 days")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_first_session_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_first_session
        count = _count_first_session(conn, "-7 days")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_session_completed_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_session_completed
        count = _count_session_completed(conn, "-7 days")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_return_day2_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_return_day2
        count = _count_return_day2(conn, "-7 days")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_return_day7_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_return_day7
        count = _count_return_day7(conn, "-7 days")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_subscription_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_subscription
        count = _count_subscription(conn, "-7 days")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_signups_with_data(self, conn):
        from mandarin.intelligence.analyzers_funnel import _count_signups
        # Add non-admin users created recently
        for uid in range(2, 7):
            conn.execute("""
                INSERT INTO user (id, email, password_hash, display_name, is_admin,
                                  created_at)
                VALUES (?, ?, 'hash', ?, 0, datetime('now'))
            """, (uid, f"user{uid}@test.com", f"User{uid}"))
        conn.commit()
        count = _count_signups(conn, "-7 days")
        # Bootstrap user (id=1, is_admin=0) + 5 new users = 6
        assert count >= 5


class TestAnalyzeFunnel:
    def test_analyze_activation_funnel_empty(self, conn):
        from mandarin.intelligence.analyzers_funnel import analyze_activation_funnel
        results = analyze_activation_funnel(conn)
        assert isinstance(results, list)

    def test_analyzers_exist(self):
        from mandarin.intelligence.analyzers_funnel import ANALYZERS
        assert isinstance(ANALYZERS, list)
        assert len(ANALYZERS) > 0


class TestFixActions:
    def test_fix_registration_page(self, conn):
        from mandarin.intelligence.analyzers_funnel import _fix_auto_test_registration_page
        result = _fix_auto_test_registration_page(conn, 2.0, 3.0)
        assert isinstance(result, dict)
        assert "action" in result

    def test_fix_resend_verification(self, conn):
        from mandarin.intelligence.analyzers_funnel import _fix_resend_verification
        result = _fix_resend_verification(conn, 40.0, 50.0)
        assert isinstance(result, dict)
        assert "action" in result

    def test_fix_auto_test_onboarding(self, conn):
        from mandarin.intelligence.analyzers_funnel import _fix_auto_test_onboarding
        result = _fix_auto_test_onboarding(conn, 30.0, 35.0)
        assert isinstance(result, dict)
        assert "action" in result
