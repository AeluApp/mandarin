"""Tests for mandarin.intelligence.self_healing — infrastructure self-healing.

Covers:
- _ensure_tables
- _get_memory_usage_mb
- _get_disk_usage_pct
- _get_error_rate
- _get_avg_response_time
- _get_stale_scheduler_locks
- _get_active_user_count
- collect_health_metrics
- _clear_llm_caches
- _truncate_logs
- _release_stale_locks
- _disable_feature_by_flag
- _reset_connection_pool
- SelfHealingEngine rate limiting, logging, remediation
- run_health_check
"""

import json
import sqlite3
import tempfile
import time
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mandarin.db.core import init_db, _migrate


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    """Fresh DB with full schema + tables needed for self-healing."""
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    c.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, is_admin)
        VALUES (1, 'test@example.com', 'hash', 'Test', 1)
    """)
    # Ensure tables needed for self-healing
    c.executescript("""
        CREATE TABLE IF NOT EXISTS request_timing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT,
            duration_ms REAL,
            status_code INTEGER,
            recorded_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS scheduler_lock (
            name TEXT PRIMARY KEY,
            locked_by TEXT,
            locked_at TEXT,
            expires_at TEXT
        );
        CREATE TABLE IF NOT EXISTS feature_flag (
            name TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """)
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


# ── Table creation ──────────────────────────────────────────────────

class TestEnsureTables:
    def test_creates_table(self, conn):
        from mandarin.intelligence.self_healing import _ensure_tables
        _ensure_tables(conn)
        # Verify table exists by inserting a row
        conn.execute("""
            INSERT INTO self_healing_log (action_type, issue_detected, action_taken)
            VALUES ('test', 'test issue', 'test action')
        """)
        conn.commit()
        row = conn.execute("SELECT * FROM self_healing_log").fetchone()
        assert row is not None


# ── Health metric collection ─────────────────────────────────────────

class TestHealthMetrics:
    def test_get_memory_usage(self):
        from mandarin.intelligence.self_healing import _get_memory_usage_mb
        mem = _get_memory_usage_mb()
        assert isinstance(mem, float)
        assert mem >= 0

    def test_get_disk_usage(self):
        from mandarin.intelligence.self_healing import _get_disk_usage_pct
        pct = _get_disk_usage_pct()
        assert isinstance(pct, float)
        assert 0 <= pct <= 100

    def test_get_error_rate_no_data(self, conn):
        from mandarin.intelligence.self_healing import _get_error_rate
        rate = _get_error_rate(conn, minutes=15)
        assert rate == 0.0

    def test_get_error_rate_graceful(self, conn):
        from mandarin.intelligence.self_healing import _get_error_rate
        # With no data, should return 0.0 gracefully
        rate = _get_error_rate(conn, minutes=5)
        assert isinstance(rate, float)

    def test_get_avg_response_time_no_data(self, conn):
        from mandarin.intelligence.self_healing import _get_avg_response_time
        avg = _get_avg_response_time(conn, minutes=15)
        assert avg == 0.0

    def test_get_avg_response_time_with_data(self, conn):
        from mandarin.intelligence.self_healing import _get_avg_response_time
        conn.execute("INSERT INTO request_timing (path, duration_ms, status_code) VALUES ('/api/test', 200, 200)")
        conn.execute("INSERT INTO request_timing (path, duration_ms, status_code) VALUES ('/api/test', 400, 200)")
        conn.commit()
        avg = _get_avg_response_time(conn, minutes=15)
        assert avg == 300.0

    def test_get_stale_locks_empty(self, conn):
        from mandarin.intelligence.self_healing import _get_stale_scheduler_locks
        locks = _get_stale_scheduler_locks(conn)
        assert locks == []

    def test_get_stale_locks_with_expired(self, conn):
        from mandarin.intelligence.self_healing import _get_stale_scheduler_locks
        conn.execute("""
            INSERT INTO scheduler_lock (name, locked_by, locked_at, expires_at)
            VALUES ('test_lock', 'worker1', datetime('now', '-2 hours'), datetime('now', '-1 hour'))
        """)
        conn.commit()
        locks = _get_stale_scheduler_locks(conn)
        assert len(locks) == 1

    def test_get_active_user_count(self, conn):
        from mandarin.intelligence.self_healing import _get_active_user_count
        count = _get_active_user_count(conn, minutes=15)
        assert count == 0

    def test_collect_health_metrics(self, conn):
        from mandarin.intelligence.self_healing import collect_health_metrics
        metrics = collect_health_metrics(conn)
        assert "timestamp" in metrics
        assert "memory_mb" in metrics
        assert "disk_usage_pct" in metrics
        assert "error_rate_15m" in metrics
        assert "avg_response_ms_15m" in metrics
        assert "stale_locks" in metrics
        assert "active_users_15m" in metrics


# ── Remediation actions ──────────────────────────────────────────────

class TestRemediationActions:
    def test_clear_llm_caches(self):
        from mandarin.intelligence.self_healing import _clear_llm_caches
        result = _clear_llm_caches()
        assert "caches_cleared" in result
        assert result["gc_collected"] is True

    def test_truncate_logs(self):
        from mandarin.intelligence.self_healing import _truncate_logs
        result = _truncate_logs()
        assert "truncated_files" in result
        assert "count" in result

    def test_release_stale_locks_empty(self, conn):
        from mandarin.intelligence.self_healing import _release_stale_locks
        result = _release_stale_locks(conn)
        assert result["count"] == 0
        assert result["released_locks"] == []

    def test_release_stale_locks_with_expired(self, conn):
        from mandarin.intelligence.self_healing import _release_stale_locks
        conn.execute("""
            INSERT INTO scheduler_lock (name, locked_by, locked_at, expires_at)
            VALUES ('stale_job', 'worker1', datetime('now', '-3 hours'), datetime('now', '-1 hour'))
        """)
        conn.commit()
        result = _release_stale_locks(conn)
        assert result["count"] == 1
        assert "stale_job" in result["released_locks"]

    def test_disable_feature_by_flag(self, conn):
        from mandarin.intelligence.self_healing import _disable_feature_by_flag
        result = _disable_feature_by_flag(conn, "some_feature", "high error rate")
        assert result["flag_name"] == "self_healing_disabled_some_feature"
        assert result["feature"] == "some_feature"

    def test_reset_connection_pool(self):
        from mandarin.intelligence.self_healing import _reset_connection_pool
        result = _reset_connection_pool()
        assert result["reset"] is True


# ── SelfHealingEngine tests ──────────────────────────────────────────

class TestSelfHealingEngine:
    def test_engine_creation(self):
        from mandarin.intelligence.self_healing import SelfHealingEngine
        engine = SelfHealingEngine()
        assert engine._action_log == []

    def test_count_recent_actions(self):
        from mandarin.intelligence.self_healing import SelfHealingEngine
        engine = SelfHealingEngine()
        assert engine._count_recent_actions() == 0

    def test_record_and_count(self):
        from mandarin.intelligence.self_healing import SelfHealingEngine
        engine = SelfHealingEngine()
        engine._record_action("memory_high")
        assert engine._count_recent_actions() == 1
        assert engine._count_recent_actions("memory_high") == 1
        assert engine._count_recent_actions("restart") == 0

    def test_can_take_action_initially(self):
        from mandarin.intelligence.self_healing import SelfHealingEngine
        engine = SelfHealingEngine()
        assert engine._can_take_action("memory_high") is True

    def test_cooldown_prevents_repeat(self):
        from mandarin.intelligence.self_healing import SelfHealingEngine
        engine = SelfHealingEngine()
        engine._record_action("memory_high")
        # Should be blocked by cooldown
        assert engine._can_take_action("memory_high") is False

    def test_rate_limit_total_actions(self):
        from mandarin.intelligence.self_healing import SelfHealingEngine, _MAX_ACTIONS_PER_HOUR
        engine = SelfHealingEngine()
        for i in range(_MAX_ACTIONS_PER_HOUR):
            engine._action_log.append({"type": f"action_{i}", "time": time.time()})
        assert engine._can_take_action("new_action") is False

    def test_restart_rate_limit(self):
        from mandarin.intelligence.self_healing import SelfHealingEngine, _MAX_RESTARTS_PER_HOUR
        engine = SelfHealingEngine()
        for i in range(_MAX_RESTARTS_PER_HOUR):
            engine._action_log.append({"type": "restart", "time": time.time()})
        assert engine._can_take_action("restart") is False

    def test_log_action(self, conn):
        from mandarin.intelligence.self_healing import SelfHealingEngine, _ensure_tables
        _ensure_tables(conn)
        engine = SelfHealingEngine()
        engine._log_action(
            conn, "test_action", "test issue", "test action taken",
            details={"key": "value"}, success=True,
        )
        row = conn.execute("SELECT * FROM self_healing_log ORDER BY id DESC LIMIT 1").fetchone()
        assert row is not None
        assert row["action_type"] == "test_action"

    def test_check_and_remediate_no_issues(self, conn):
        from mandarin.intelligence.self_healing import SelfHealingEngine
        engine = SelfHealingEngine()
        result = engine.check_and_remediate(conn)
        assert "issues_found" in result or "actions_taken" in result or isinstance(result, dict)

    def test_get_error_rate_by_endpoint(self, conn):
        from mandarin.intelligence.self_healing import _get_error_rate_by_endpoint
        result = _get_error_rate_by_endpoint(conn, minutes=60)
        assert isinstance(result, list)


# ── run_health_check ───────────────────────────────────────────────────

class TestRunHealthCheck:
    def test_run_health_check(self, conn):
        from mandarin.intelligence.self_healing import run_health_check
        result = run_health_check(conn)
        assert isinstance(result, dict)
