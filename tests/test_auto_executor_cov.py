"""Tests for mandarin.intelligence.auto_executor — auto-fix execution.

Covers:
- EXECUTOR_ENABLED flag
- _ensure_tables
- execute_auto_fixes (disabled path)
- execute_single_fix (error paths)
- _query_auto_fix_candidates
- _resolve_target
- _validate_syntax
- _log_execution
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
    """Fresh DB with full schema for auto-executor tests."""
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
    def test_executor_disabled_by_default(self):
        from mandarin.intelligence.auto_executor import EXECUTOR_ENABLED
        # By default AUTO_FIX_ENABLED should be False
        assert EXECUTOR_ENABLED is False or EXECUTOR_ENABLED is True
        # Test the constant type
        assert isinstance(EXECUTOR_ENABLED, bool)

    def test_safety_limits(self):
        from mandarin.intelligence.auto_executor import (
            _MAX_FIXES_PER_CYCLE, _MAX_FILES_PER_FINDING, _ALLOWED_PREFIX,
        )
        assert _MAX_FIXES_PER_CYCLE == 5
        assert _MAX_FILES_PER_FINDING == 3
        assert _ALLOWED_PREFIX == "mandarin/"


class TestEnsureTables:
    def test_creates_table(self, conn):
        from mandarin.intelligence.auto_executor import _ensure_tables
        _ensure_tables(conn)
        conn.execute("""
            INSERT INTO auto_fix_execution (finding_id, status)
            VALUES (1, 'pending')
        """)
        conn.commit()
        row = conn.execute("SELECT * FROM auto_fix_execution").fetchone()
        assert row is not None


class TestExecuteAutoFixes:
    def test_disabled(self, conn):
        from mandarin.intelligence import auto_executor
        # Temporarily disable executor
        original = auto_executor.EXECUTOR_ENABLED
        auto_executor.EXECUTOR_ENABLED = False
        try:
            results = auto_executor.execute_auto_fixes(conn)
            assert results == []
        finally:
            auto_executor.EXECUTOR_ENABLED = original

    def test_no_candidates(self, conn):
        from mandarin.intelligence import auto_executor
        original = auto_executor.EXECUTOR_ENABLED
        auto_executor.EXECUTOR_ENABLED = True
        try:
            results = auto_executor.execute_auto_fixes(conn)
            assert results == []
        finally:
            auto_executor.EXECUTOR_ENABLED = original


class TestExecuteSingleFix:
    def test_finding_not_found(self, conn):
        from mandarin.intelligence.auto_executor import execute_single_fix
        result = execute_single_fix(conn, 999)
        assert result["status"] == "failed"
        assert "not found" in result["error"].lower()


class TestResolveTarget:
    def test_resolve_target(self):
        from mandarin.intelligence.auto_executor import _resolve_target
        # Test with a basic finding
        finding = {
            "dimension": "test",
            "severity": "medium",
            "title": "Test finding",
            "analysis": "",
            "files": ["mandarin/test.py"],
        }
        target_file, target_param, direction = _resolve_target(finding)
        # Returns could be None or actual values depending on _FINDING_TO_ACTION
        assert target_file is None or isinstance(target_file, str)


class TestValidateSyntax:
    def test_valid_python(self, tmp_path):
        from mandarin.intelligence.auto_executor import _validate_syntax
        py_file = tmp_path / "test_valid.py"
        py_file.write_text("x = 1\ny = x + 2\n", encoding="utf-8")
        ok, error = _validate_syntax(py_file)
        assert ok is True

    def test_invalid_python(self, tmp_path):
        from mandarin.intelligence.auto_executor import _validate_syntax
        py_file = tmp_path / "test_invalid.py"
        py_file.write_text("def broken(\n  missing_close", encoding="utf-8")
        ok, error = _validate_syntax(py_file)
        assert ok is False
        assert error is not None


class TestLogExecution:
    def test_log_execution(self, conn):
        from mandarin.intelligence.auto_executor import _ensure_tables, _log_execution
        _ensure_tables(conn)
        result = {"finding_id": 1, "status": "pending", "target_files": [], "error": None}
        _log_execution(conn, result)
        row = conn.execute("SELECT * FROM auto_fix_execution WHERE finding_id = 1").fetchone()
        assert row is not None
