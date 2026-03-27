"""Tests for mandarin.intelligence.return_monitor — user return tracking.

Covers:
- _ensure_tables
- _action_already_taken
- _log_action
- _get_users_no_return_24h / 48h
- _get_users_at_risk_7d
- _get_churning_subscribers
- _get_accuracy_trend
- _get_users_with_accuracy_trends
- _adjust_difficulty_down / _adjust_difficulty_up
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
    """Fresh DB with full schema for return monitor tests."""
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    c.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, is_admin)
        VALUES (1, 'test@example.com', 'hash', 'Test', 0)
    """)
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


class TestEnsureTables:
    def test_creates_action_log(self, conn):
        from mandarin.intelligence.return_monitor import _ensure_tables
        _ensure_tables(conn)
        conn.execute("""
            INSERT INTO return_monitor_action_log (user_id, rule_name, action_taken)
            VALUES (1, 'test_rule', 'test_action')
        """)
        conn.commit()
        row = conn.execute("SELECT * FROM return_monitor_action_log").fetchone()
        assert row is not None


class TestActionDedup:
    def test_action_not_taken(self, conn):
        from mandarin.intelligence.return_monitor import _ensure_tables, _action_already_taken
        _ensure_tables(conn)
        assert _action_already_taken(conn, 1, "test_rule") is False

    def test_action_already_taken(self, conn):
        from mandarin.intelligence.return_monitor import (
            _ensure_tables, _action_already_taken, _log_action,
        )
        _ensure_tables(conn)
        _log_action(conn, 1, "test_rule", "test_action", details={"k": "v"})
        conn.commit()
        assert _action_already_taken(conn, 1, "test_rule") is True


class TestLogAction:
    def test_log_action_success(self, conn):
        from mandarin.intelligence.return_monitor import _ensure_tables, _log_action
        _ensure_tables(conn)
        _log_action(conn, 1, "activation_24h", "sent_email", details={"email": "test"})
        conn.commit()
        row = conn.execute(
            "SELECT * FROM return_monitor_action_log WHERE rule_name = 'activation_24h'"
        ).fetchone()
        assert row is not None
        assert row["action_taken"] == "sent_email"


class TestUserQueries:
    def test_no_return_24h_empty(self, conn):
        from mandarin.intelligence.return_monitor import _get_users_no_return_24h
        users = _get_users_no_return_24h(conn)
        assert users == []

    def test_no_return_48h_empty(self, conn):
        from mandarin.intelligence.return_monitor import _get_users_no_return_48h
        users = _get_users_no_return_48h(conn)
        assert users == []

    def test_at_risk_7d_empty(self, conn):
        from mandarin.intelligence.return_monitor import _get_users_at_risk_7d
        users = _get_users_at_risk_7d(conn)
        assert users == []

    def test_churning_subscribers_empty(self, conn):
        from mandarin.intelligence.return_monitor import _get_churning_subscribers
        users = _get_churning_subscribers(conn)
        assert users == []


class TestAccuracyTrend:
    def test_no_data(self, conn):
        from mandarin.intelligence.return_monitor import _get_accuracy_trend
        trend = _get_accuracy_trend(conn, user_id=1, session_count=3)
        assert trend is None

    def test_dropping_trend(self, conn):
        from mandarin.intelligence.return_monitor import _get_accuracy_trend
        # Insert 3 sessions with decreasing accuracy
        # _get_accuracy_trend queries items_correct & items_completed, ordered by started_at DESC
        # Newest first: 5/10, 7/10, 9/10 -> chronological: 9/10, 7/10, 5/10 = dropping
        for i, (correct, completed) in enumerate([(5, 10), (7, 10), (9, 10)]):
            conn.execute("""
                INSERT INTO session_log (user_id, session_outcome, items_correct,
                                         items_completed, started_at)
                VALUES (1, 'completed', ?, ?, datetime('now', ? || ' hours'))
            """, (correct, completed, f"-{(i + 1) * 24}"))
        conn.commit()
        trend = _get_accuracy_trend(conn, user_id=1, session_count=3)
        assert trend == "dropping"

    def test_rising_trend(self, conn):
        from mandarin.intelligence.return_monitor import _get_accuracy_trend
        # Newest first: 9/10, 7/10, 5/10 -> chronological: 5/10, 7/10, 9/10 = rising
        for i, (correct, completed) in enumerate([(9, 10), (7, 10), (5, 10)]):
            conn.execute("""
                INSERT INTO session_log (user_id, session_outcome, items_correct,
                                         items_completed, started_at)
                VALUES (1, 'completed', ?, ?, datetime('now', ? || ' hours'))
            """, (correct, completed, f"-{(i + 1) * 24}"))
        conn.commit()
        trend = _get_accuracy_trend(conn, user_id=1, session_count=3)
        assert trend == "rising"

    def test_no_trend(self, conn):
        from mandarin.intelligence.return_monitor import _get_accuracy_trend
        for i, (correct, completed) in enumerate([(7, 10), (5, 10), (7, 10)]):
            conn.execute("""
                INSERT INTO session_log (user_id, session_outcome, items_correct,
                                         items_completed, started_at)
                VALUES (1, 'completed', ?, ?, datetime('now', ? || ' hours'))
            """, (correct, completed, f"-{(i + 1) * 24}"))
        conn.commit()
        trend = _get_accuracy_trend(conn, user_id=1, session_count=3)
        assert trend is None


class TestGetUsersWithAccuracyTrends:
    def test_empty(self, conn):
        from mandarin.intelligence.return_monitor import _get_users_with_accuracy_trends
        dropping, rising = _get_users_with_accuracy_trends(conn)
        assert dropping == []
        assert rising == []


class TestDifficultyAdjustment:
    def test_adjust_difficulty_down(self, conn):
        from mandarin.intelligence.return_monitor import _adjust_difficulty_down
        result = _adjust_difficulty_down(conn, user_id=1, pct=0.10)
        assert isinstance(result, dict)

    def test_adjust_difficulty_up(self, conn):
        from mandarin.intelligence.return_monitor import _adjust_difficulty_up
        result = _adjust_difficulty_up(conn, user_id=1, pct=0.20)
        assert isinstance(result, dict)


class TestRunCheck:
    def test_run_check_empty(self, conn):
        from mandarin.intelligence.return_monitor import run_check
        result = run_check(conn)
        assert isinstance(result, dict)

    def test_analyzers_exist(self):
        from mandarin.intelligence.return_monitor import ANALYZERS
        assert isinstance(ANALYZERS, list)
        assert len(ANALYZERS) > 0
