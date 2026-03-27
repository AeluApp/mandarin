"""Tests for mandarin.intelligence.dependency_monitor — external dependency monitoring.

Covers:
- Constants (HEALTHY, DEGRADED, DEAD, DEPENDENCIES)
- _ensure_tables
- _log_health / _log_transition
- _set_feature_flag / _get_feature_flag
- _get_last_status / _get_recent_statuses
- _handle_transition
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
    """Fresh DB with full schema for dependency monitor tests."""
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


class TestConstants:
    def test_health_states(self):
        from mandarin.intelligence.dependency_monitor import HEALTHY, DEGRADED, DEAD
        assert HEALTHY == "healthy"
        assert DEGRADED == "degraded"
        assert DEAD == "dead"

    def test_dependencies_defined(self):
        from mandarin.intelligence.dependency_monitor import DEPENDENCIES
        assert isinstance(DEPENDENCIES, dict)
        assert "llm" in DEPENDENCIES
        assert "tts" in DEPENDENCIES
        assert "stripe" in DEPENDENCIES
        assert "resend" in DEPENDENCIES
        assert "plausible" in DEPENDENCIES
        for dep_name, dep_config in DEPENDENCIES.items():
            assert "healthy_threshold_ms" in dep_config
            assert "degraded_threshold_ms" in dep_config
            assert "fallback_flag" in dep_config


class TestEnsureTables:
    def test_creates_tables(self, conn):
        from mandarin.intelligence.dependency_monitor import _ensure_tables
        _ensure_tables(conn)
        conn.execute("""
            INSERT INTO dependency_health (dep_name, status, latency_ms)
            VALUES ('llm', 'healthy', 200)
        """)
        conn.commit()
        row = conn.execute("SELECT * FROM dependency_health").fetchone()
        assert row is not None


class TestLogging:
    def test_log_health(self, conn):
        from mandarin.intelligence.dependency_monitor import _ensure_tables, _log_health
        _ensure_tables(conn)
        _log_health(conn, "llm", "healthy", latency_ms=150)
        row = conn.execute("SELECT * FROM dependency_health WHERE dep_name = 'llm'").fetchone()
        assert row is not None
        assert row["status"] == "healthy"
        assert row["latency_ms"] == 150

    def test_log_transition(self, conn):
        from mandarin.intelligence.dependency_monitor import _ensure_tables, _log_transition
        _ensure_tables(conn)
        _log_transition(conn, "tts", "healthy", "degraded", "preemptive_alert",
                        details={"latency": 8000})
        row = conn.execute("SELECT * FROM dependency_transition_log").fetchone()
        assert row is not None
        assert row["dep_name"] == "tts"
        assert row["old_status"] == "healthy"
        assert row["new_status"] == "degraded"


class TestFeatureFlags:
    def test_set_and_get_flag(self, conn):
        from mandarin.intelligence.dependency_monitor import _set_feature_flag, _get_feature_flag
        _set_feature_flag(conn, "dep_llm_fallback", 1)
        assert _get_feature_flag(conn, "dep_llm_fallback") == 1

    def test_get_flag_default(self, conn):
        from mandarin.intelligence.dependency_monitor import _get_feature_flag
        val = _get_feature_flag(conn, "nonexistent_flag", default=42)
        assert val == 42


class TestStatusQueries:
    def test_get_last_status_no_data(self, conn):
        from mandarin.intelligence.dependency_monitor import (
            _ensure_tables, _get_last_status, HEALTHY,
        )
        _ensure_tables(conn)
        status = _get_last_status(conn, "llm")
        assert status == HEALTHY

    def test_get_last_status_with_data(self, conn):
        from mandarin.intelligence.dependency_monitor import (
            _ensure_tables, _log_health, _get_last_status,
        )
        _ensure_tables(conn)
        _log_health(conn, "llm", "degraded", latency_ms=6000)
        assert _get_last_status(conn, "llm") == "degraded"

    def test_get_recent_statuses(self, conn):
        from mandarin.intelligence.dependency_monitor import (
            _ensure_tables, _log_health, _get_recent_statuses,
        )
        _ensure_tables(conn)
        _log_health(conn, "stripe", "healthy", latency_ms=100)
        _log_health(conn, "stripe", "degraded", latency_ms=5000)
        _log_health(conn, "stripe", "dead", latency_ms=20000)
        statuses = _get_recent_statuses(conn, "stripe", count=3)
        assert len(statuses) == 3
        assert statuses[0] == "dead"  # Most recent first


class TestRunCheck:
    def test_run_check(self, conn):
        from mandarin.intelligence.dependency_monitor import run_check
        result = run_check(conn)
        assert isinstance(result, dict)

    def test_analyzers_exist(self):
        from mandarin.intelligence.dependency_monitor import ANALYZERS
        assert isinstance(ANALYZERS, list)
        assert len(ANALYZERS) > 0
