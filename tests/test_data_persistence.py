"""Tests for data persistence — review sessions survive crashes and restarts.

Validates:
- Progress survives connection close/reopen
- Partial session data doesn't produce duplicates
- Session metrics are durable
- SRS state is not lost on restart
"""

import tempfile
from pathlib import Path

import pytest

from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.db.content import insert_content_item
from mandarin.db.progress import record_attempt
from mandarin.db.session import start_session


def _fresh_db():
    """Create a fresh database file. Returns (path,)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier)
        VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin')
    """)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1)")
    conn.commit()
    conn.close()
    return path


def _open_db(path):
    """Open an existing database."""
    conn = init_db(path)
    _migrate(conn)
    return conn


def _seed_item(conn, content_item_id=1):
    """Insert a content item for testing."""
    insert_content_item(conn,
        hanzi="你好",
        pinyin="nǐ hǎo",
        english="hello",
        hsk_level=1,
    )


# ── Progress Survives Close/Reopen ──────────────────────────────────────────


def test_progress_survives_close_reopen():
    """Record attempts, close DB, reopen — progress rows must be intact."""
    path = _fresh_db()
    try:
        # Session 1: record some attempts
        conn = _open_db(path)
        _seed_item(conn)
        session_id = start_session(conn)
        record_attempt(conn, content_item_id=1, modality="reading", correct=True,
                       response_ms=2000, drill_type="mc", session_id=session_id)
        record_attempt(conn, content_item_id=1, modality="reading", correct=True,
                       response_ms=1500, drill_type="mc", session_id=session_id)
        conn.close()

        # Session 2: reopen and verify
        conn = _open_db(path)
        row = conn.execute("""
            SELECT total_attempts, streak_correct, mastery_stage
            FROM progress
            WHERE user_id = 1 AND content_item_id = 1 AND modality = 'reading'
        """).fetchone()
        assert row is not None
        assert row["total_attempts"] == 2
        assert row["streak_correct"] >= 1
        conn.close()
    finally:
        path.unlink(missing_ok=True)


def test_srs_state_preserved_across_sessions():
    """Ease factor and interval must persist across DB close/reopen."""
    path = _fresh_db()
    try:
        conn = _open_db(path)
        _seed_item(conn)
        session_id = start_session(conn)
        # Multiple correct answers to build up ease and interval
        for _ in range(5):
            record_attempt(conn, content_item_id=1, modality="reading", correct=True,
                           response_ms=2000, drill_type="mc", session_id=session_id)
        row_before = conn.execute("""
            SELECT ease_factor, interval_days, half_life_days
            FROM progress
            WHERE user_id = 1 AND content_item_id = 1 AND modality = 'reading'
        """).fetchone()
        ease_before = row_before["ease_factor"]
        interval_before = row_before["interval_days"]
        hl_before = row_before["half_life_days"]
        conn.close()

        conn = _open_db(path)
        row_after = conn.execute("""
            SELECT ease_factor, interval_days, half_life_days
            FROM progress
            WHERE user_id = 1 AND content_item_id = 1 AND modality = 'reading'
        """).fetchone()
        assert row_after["ease_factor"] == ease_before
        assert row_after["interval_days"] == interval_before
        assert row_after["half_life_days"] == hl_before
        conn.close()
    finally:
        path.unlink(missing_ok=True)


def test_session_log_preserved():
    """Session log entries must survive close/reopen."""
    path = _fresh_db()
    try:
        conn = _open_db(path)
        _seed_item(conn)
        session_id = start_session(conn)
        record_attempt(conn, content_item_id=1, modality="reading", correct=True,
                       response_ms=2000, drill_type="mc", session_id=session_id)
        conn.close()

        conn = _open_db(path)
        row = conn.execute(
            "SELECT * FROM session_log WHERE id = ?", (session_id,)
        ).fetchone()
        assert row is not None
        assert row["items_completed"] >= 0
        conn.close()
    finally:
        path.unlink(missing_ok=True)


# ── Partial Session (Crash Simulation) ──────────────────────────────────────


def test_partial_session_no_duplicates():
    """If we record 2 attempts, crash, then record again — no duplicates."""
    path = _fresh_db()
    try:
        # First run: 2 attempts
        conn = _open_db(path)
        _seed_item(conn)
        session_id = start_session(conn)
        record_attempt(conn, content_item_id=1, modality="reading", correct=True,
                       response_ms=2000, drill_type="mc", session_id=session_id)
        record_attempt(conn, content_item_id=1, modality="reading", correct=False,
                       response_ms=3000, drill_type="mc", session_id=session_id)
        conn.close()  # simulated crash

        # Second run: record one more attempt
        conn = _open_db(path)
        session_id2 = start_session(conn)
        record_attempt(conn, content_item_id=1, modality="reading", correct=True,
                       response_ms=1800, drill_type="mc", session_id=session_id2)
        conn.close()

        # Verify: should have exactly 1 progress row (upsert, not insert)
        conn = _open_db(path)
        rows = conn.execute("""
            SELECT * FROM progress
            WHERE user_id = 1 AND content_item_id = 1 AND modality = 'reading'
        """).fetchall()
        assert len(rows) == 1
        assert rows[0]["total_attempts"] == 3  # all attempts counted
        conn.close()
    finally:
        path.unlink(missing_ok=True)


def test_mastery_stage_survives_crash():
    """Mastery stage promotions must survive crash/restart."""
    path = _fresh_db()
    try:
        conn = _open_db(path)
        _seed_item(conn)
        session_id = start_session(conn)
        # Enough correct answers to promote past 'seen'
        for _ in range(5):
            record_attempt(conn, content_item_id=1, modality="reading", correct=True,
                           response_ms=2000, drill_type="mc", session_id=session_id)
        row = conn.execute("""
            SELECT mastery_stage FROM progress
            WHERE user_id = 1 AND content_item_id = 1 AND modality = 'reading'
        """).fetchone()
        stage = row["mastery_stage"]
        conn.close()

        conn = _open_db(path)
        row2 = conn.execute("""
            SELECT mastery_stage FROM progress
            WHERE user_id = 1 AND content_item_id = 1 AND modality = 'reading'
        """).fetchone()
        assert row2["mastery_stage"] == stage
        conn.close()
    finally:
        path.unlink(missing_ok=True)


# ── Error Log Persistence ──────────────────────────────────────────────────


def test_error_log_recorded_on_wrong():
    """Incorrect attempts should create error_log entries that persist."""
    path = _fresh_db()
    try:
        conn = _open_db(path)
        _seed_item(conn)
        session_id = start_session(conn)
        record_attempt(conn, content_item_id=1, modality="reading", correct=False,
                       response_ms=3000, drill_type="mc", session_id=session_id,
                       error_type="vocab", user_answer="wrong", expected_answer="nǐ hǎo")
        conn.close()

        conn = _open_db(path)
        errors = conn.execute(
            "SELECT * FROM error_log WHERE content_item_id = 1"
        ).fetchall()
        assert len(errors) >= 1
        conn.close()
    finally:
        path.unlink(missing_ok=True)
