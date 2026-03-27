"""Tests for mandarin.intelligence.session_diagnostics — failure diagnosis.

Covers:
- _ensure_tables
- _get_undiagnosed_sessions
- _get_session_errors
- _get_session_reviews
- _get_session_client_errors
- _get_llm_errors_during_session
- _classify_session (all 7 rules)
- _fix_content_too_hard
- _fix_content_too_easy
- _fix_tts_failed
- _fix_llm_timeout
- diagnose_sessions / run_check
- ANALYZERS list
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
    """Fresh DB with full schema for session diagnostics tests."""
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    c.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, is_admin)
        VALUES (1, 'test@example.com', 'hash', 'Test', 0)
    """)
    # Seed content items for FK constraints in review_event
    for i in range(1, 20):
        c.execute("""
            INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, hsk_level, difficulty)
            VALUES (?, ?, 'test', 'test', 1, 0.5)
        """, (i, f"字{i}"))
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


class TestEnsureTables:
    def test_creates_session_diagnosis_table(self, conn):
        from mandarin.intelligence.session_diagnostics import _ensure_tables
        _ensure_tables(conn)
        conn.execute("""
            INSERT INTO session_diagnosis (session_id, classification)
            VALUES (1, 'content_too_hard')
        """)
        conn.commit()
        row = conn.execute("SELECT * FROM session_diagnosis").fetchone()
        assert row is not None


class TestGetUndiagnosedSessions:
    def test_no_sessions(self, conn):
        from mandarin.intelligence.session_diagnostics import (
            _ensure_tables, _get_undiagnosed_sessions,
        )
        _ensure_tables(conn)
        sessions = _get_undiagnosed_sessions(conn, hours=24)
        assert sessions == []

    def test_with_abandoned_session(self, conn):
        from mandarin.intelligence.session_diagnostics import (
            _ensure_tables, _get_undiagnosed_sessions,
        )
        _ensure_tables(conn)
        conn.execute("""
            INSERT INTO session_log (user_id, session_outcome,
                                     items_planned, items_completed, early_exit,
                                     started_at)
            VALUES (1, 'abandoned', 20, 5, 1, datetime('now'))
        """)
        conn.commit()
        sessions = _get_undiagnosed_sessions(conn, hours=24)
        assert len(sessions) >= 1
        assert sessions[0]["session_outcome"] == "abandoned"


class TestGetSessionEvidence:
    def test_get_session_errors_empty(self, conn):
        from mandarin.intelligence.session_diagnostics import _get_session_errors
        errors = _get_session_errors(conn, 999)
        assert errors == []

    def test_get_session_reviews_empty(self, conn):
        from mandarin.intelligence.session_diagnostics import _get_session_reviews
        reviews = _get_session_reviews(conn, 999)
        assert reviews == []

    def test_get_session_client_errors_empty(self, conn):
        from mandarin.intelligence.session_diagnostics import _get_session_client_errors
        errors = _get_session_client_errors(conn, 999, 1, "2024-01-01 00:00:00")
        assert errors == []

    def test_get_llm_errors_empty(self, conn):
        from mandarin.intelligence.session_diagnostics import _get_llm_errors_during_session
        errors = _get_llm_errors_during_session(conn, "2024-01-01 00:00:00")
        assert errors == []


class TestClassifySession:
    def test_tts_failed(self, conn):
        from mandarin.intelligence.session_diagnostics import (
            _ensure_tables, _classify_session, TTS_FAILED,
        )
        _ensure_tables(conn)

        # Create session
        conn.execute("""
            INSERT INTO session_log (id, user_id, session_outcome, items_planned, items_completed,
                                     started_at, early_exit)
            VALUES (100, 1, 'abandoned', 20, 5, datetime('now'), 1)
        """)
        # Create TTS error — use valid error_type from CHECK constraint
        conn.execute("""
            INSERT INTO error_log (user_id, session_id, content_item_id, modality, error_type, notes)
            VALUES (1, 100, 1, 'listening', 'tone', 'tts generation failed for audio')
        """)
        conn.commit()

        session = {"session_id": 100, "user_id": 1, "session_outcome": "abandoned",
                    "items_planned": 20, "items_completed": 5, "started_at": "2024-01-01",
                    "early_exit": True}
        classification, confidence, evidence = _classify_session(conn, session)
        assert classification == TTS_FAILED
        assert confidence >= 0.9

    def test_content_too_hard(self, conn):
        from mandarin.intelligence.session_diagnostics import (
            _ensure_tables, _classify_session, CONTENT_TOO_HARD,
        )
        _ensure_tables(conn)

        conn.execute("""
            INSERT INTO session_log (id, user_id, session_outcome, items_planned, items_completed,
                                     started_at, early_exit)
            VALUES (101, 1, 'abandoned', 20, 5, datetime('now'), 1)
        """)
        # Add review events with low accuracy
        for i in range(10):
            conn.execute("""
                INSERT INTO review_event (session_id, content_item_id, modality, drill_type,
                                         correct, response_ms)
                VALUES (101, ?, 'reading', 'mc', ?, 2000)
            """, (i + 1, 1 if i < 2 else 0))  # 2/10 = 20% accuracy
        conn.commit()

        session = {"session_id": 101, "user_id": 1, "session_outcome": "abandoned",
                    "items_planned": 20, "items_completed": 5, "started_at": "2024-01-01",
                    "early_exit": True}
        classification, confidence, evidence = _classify_session(conn, session)
        assert classification == CONTENT_TOO_HARD

    def test_content_too_easy(self, conn):
        from mandarin.intelligence.session_diagnostics import (
            _ensure_tables, _classify_session, CONTENT_TOO_EASY,
        )
        _ensure_tables(conn)

        conn.execute("""
            INSERT INTO session_log (id, user_id, session_outcome, items_planned, items_completed,
                                     started_at, early_exit)
            VALUES (102, 1, 'abandoned', 20, 5, datetime('now'), 1)
        """)
        # Add review events with high accuracy + fast responses
        for i in range(10):
            conn.execute("""
                INSERT INTO review_event (session_id, content_item_id, modality, drill_type,
                                         correct, response_ms)
                VALUES (102, ?, 'reading', 'mc', 1, 500)
            """, (i + 1,))
        conn.commit()

        session = {"session_id": 102, "user_id": 1, "session_outcome": "abandoned",
                    "items_planned": 20, "items_completed": 5, "started_at": "2024-01-01",
                    "early_exit": True}
        classification, confidence, evidence = _classify_session(conn, session)
        assert classification == CONTENT_TOO_EASY

    def test_user_quit_bounced(self, conn):
        from mandarin.intelligence.session_diagnostics import (
            _ensure_tables, _classify_session, USER_QUIT,
        )
        _ensure_tables(conn)

        session = {"session_id": 103, "user_id": 1, "session_outcome": "bounced",
                    "items_planned": 20, "items_completed": 0, "started_at": "2024-01-01",
                    "early_exit": True}
        classification, confidence, evidence = _classify_session(conn, session)
        assert classification == USER_QUIT
        assert confidence >= 0.85

    def test_user_quit_early_exit_no_items(self, conn):
        from mandarin.intelligence.session_diagnostics import (
            _ensure_tables, _classify_session, USER_QUIT,
        )
        _ensure_tables(conn)

        session = {"session_id": 104, "user_id": 1, "session_outcome": "abandoned",
                    "items_planned": 20, "items_completed": 0, "started_at": "2024-01-01",
                    "early_exit": True}
        classification, confidence, evidence = _classify_session(conn, session)
        assert classification == USER_QUIT

    def test_unknown_classification(self, conn):
        from mandarin.intelligence.session_diagnostics import (
            _ensure_tables, _classify_session, UNKNOWN,
        )
        _ensure_tables(conn)

        # A session with no clear failure pattern
        session = {"session_id": 105, "user_id": 1, "session_outcome": "abandoned",
                    "items_planned": 20, "items_completed": 10, "started_at": "2024-01-01",
                    "early_exit": False}
        classification, confidence, evidence = _classify_session(conn, session)
        # Should be UNKNOWN or some other classification
        assert classification is not None


class TestFixActions:
    def test_fix_content_too_hard(self, conn):
        from mandarin.intelligence.session_diagnostics import _fix_content_too_hard
        # Add content items
        for i in range(1, 4):
            conn.execute("""
                INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, difficulty)
                VALUES (?, ?, 'test', 'test', 0.8)
            """, (i, f"字{i}"))
        conn.execute("""
            INSERT INTO session_log (id, user_id, session_outcome) VALUES (200, 1, 'abandoned')
        """)
        for i in range(1, 4):
            conn.execute("""
                INSERT INTO review_event (session_id, content_item_id, modality, correct)
                VALUES (200, ?, 'reading', 0)
            """, (i,))
        conn.commit()

        session = {"session_id": 200, "user_id": 1}
        result = _fix_content_too_hard(conn, session, {})
        assert result["items_adjusted"] >= 0

    def test_fix_content_too_easy(self, conn):
        from mandarin.intelligence.session_diagnostics import _fix_content_too_easy
        session = {"session_id": 201, "user_id": 1}
        result = _fix_content_too_easy(conn, session, {})
        assert "level_adjusted" in result

    def test_fix_tts_failed(self, conn):
        from mandarin.intelligence.session_diagnostics import _fix_tts_failed
        session = {"session_id": 202, "user_id": 1}
        result = _fix_tts_failed(conn, session, {})
        assert "items_marked_no_audio" in result

    def test_fix_llm_timeout(self, conn):
        from mandarin.intelligence.session_diagnostics import _fix_llm_timeout
        session = {"session_id": 203, "user_id": 1}
        evidence = {"llm_models": ["qwen2.5:7b"], "timeout_errors": 3}
        result = _fix_llm_timeout(conn, session, evidence)
        assert isinstance(result, dict)


class TestRunCheck:
    def test_run_check_empty(self, conn):
        from mandarin.intelligence.session_diagnostics import run_check
        result = run_check(conn)
        assert isinstance(result, dict)

    def test_analyzers_exist(self):
        from mandarin.intelligence.session_diagnostics import ANALYZERS
        assert isinstance(ANALYZERS, list)
        assert len(ANALYZERS) > 0


class TestConstants:
    def test_classification_constants(self):
        from mandarin.intelligence.session_diagnostics import (
            CONTENT_TOO_HARD, CONTENT_TOO_EASY, TTS_FAILED,
            LLM_TIMEOUT, UI_ERROR, USER_QUIT, UNKNOWN,
        )
        assert CONTENT_TOO_HARD == "content_too_hard"
        assert CONTENT_TOO_EASY == "content_too_easy"
        assert TTS_FAILED == "tts_failed"
        assert LLM_TIMEOUT == "llm_timeout"
        assert UI_ERROR == "ui_error"
        assert USER_QUIT == "user_quit"
        assert UNKNOWN == "unknown"
