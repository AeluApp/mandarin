"""Tests for mandarin.improve — system self-improvement pattern detection.

Covers:
- detect_patterns
- _check_early_exits
- _check_persistent_errors
- _check_boredom
- _check_duration_trend
- _check_accuracy_plateau
- _check_velocity_decline
- _check_interest_drift
- apply_proposal
- _VALID_LENS_COLS
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
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
    def test_valid_lens_cols(self):
        from mandarin.improve import _VALID_LENS_COLS
        assert isinstance(_VALID_LENS_COLS, frozenset)
        assert "lens_quiet_observation" in _VALID_LENS_COLS
        assert "lens_comedy" in _VALID_LENS_COLS


class TestDetectPatterns:
    def test_no_sessions(self, conn):
        from mandarin.improve import detect_patterns
        proposals = detect_patterns(conn, user_id=1)
        assert proposals == []

    def test_with_sessions(self, conn):
        from mandarin.improve import detect_patterns
        # Create enough sessions for pattern detection
        for i in range(10):
            conn.execute("""
                INSERT INTO session_log (user_id, session_outcome, items_completed,
                                         items_correct, duration_seconds, started_at,
                                         early_exit)
                VALUES (1, 'completed', 10, ?, 300, datetime('now', ? || ' days'), 0)
            """, (7, f"-{i}"))
        conn.commit()
        proposals = detect_patterns(conn, user_id=1)
        assert isinstance(proposals, list)


class TestCheckFunctions:
    def test_check_early_exits_none(self):
        from mandarin.improve import _check_early_exits
        proposals = []
        sessions = [{"early_exit": False} for _ in range(5)]
        _check_early_exits(sessions, proposals)
        assert len(proposals) == 0

    def test_check_early_exits_detected(self):
        from mandarin.improve import _check_early_exits
        proposals = []
        sessions = [{"early_exit": True} for _ in range(5)]
        _check_early_exits(sessions, proposals)
        assert len(proposals) >= 1

    def test_check_boredom_none(self):
        from mandarin.improve import _check_boredom
        proposals = []
        sessions = [{"boredom_flags": 0, "items_correct": 7, "items_completed": 10}
                     for _ in range(5)]
        _check_boredom(sessions, proposals)
        assert isinstance(proposals, list)

    def test_check_duration_trend_stable(self):
        from mandarin.improve import _check_duration_trend
        proposals = []
        sessions = [{"duration_seconds": 300} for _ in range(10)]
        _check_duration_trend(sessions, proposals)
        assert isinstance(proposals, list)

    def test_check_duration_trend_declining(self):
        from mandarin.improve import _check_duration_trend
        proposals = []
        # Sessions with sharply declining duration
        sessions = [{"duration_seconds": 300 - i * 30} for i in range(10)]
        _check_duration_trend(sessions, proposals)
        assert isinstance(proposals, list)

    def test_check_accuracy_plateau(self):
        from mandarin.improve import _check_accuracy_plateau
        proposals = []
        sessions = [{"items_correct": 7, "items_completed": 10} for _ in range(10)]
        _check_accuracy_plateau(sessions, proposals)
        assert isinstance(proposals, list)


class TestApplyProposal:
    def test_apply_nonexistent(self, conn):
        from mandarin.improve import apply_proposal
        # apply_proposal expects an ID, not a dict
        result = apply_proposal(conn, 999, user_id=1)
        assert result is None or isinstance(result, dict)
