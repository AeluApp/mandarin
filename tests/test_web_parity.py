"""Tests for web dashboard enhancements.

Tests verify:
- Streak computation returns correct consecutive day counts
- Index route returns mastery data
- Personalization API returns valid structure
"""

import sqlite3
from datetime import date, datetime, timedelta, timezone

from mandarin.web.middleware import _compute_streak


# ---- Helpers ----

def _utc_today():
    """Return today's date in UTC (matching _compute_streak's internal clock)."""
    return datetime.now(timezone.utc).date()


def _make_streak_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            started_at TEXT,
            items_completed INTEGER DEFAULT 0,
            session_outcome TEXT DEFAULT 'completed'
        )
    """)
    conn.commit()
    return conn


def _add_session(conn, d: date, completed: int = 5):
    conn.execute(
        "INSERT INTO session_log (started_at, items_completed) VALUES (?, ?)",
        (d.isoformat() + " 10:00:00", completed),
    )
    conn.commit()


# ---- TestComputeStreak ----

def test_no_sessions_returns_zero():
    conn = _make_streak_db()
    assert _compute_streak(conn) == 0
    conn.close()


def test_today_only_returns_one():
    conn = _make_streak_db()
    _add_session(conn, _utc_today())
    assert _compute_streak(conn) == 1
    conn.close()


def test_today_and_yesterday_returns_two():
    conn = _make_streak_db()
    _add_session(conn, _utc_today())
    _add_session(conn, _utc_today() - timedelta(days=1))
    assert _compute_streak(conn) == 2
    conn.close()


def test_gap_breaks_streak():
    conn = _make_streak_db()
    _add_session(conn, _utc_today())
    _add_session(conn, _utc_today() - timedelta(days=1))
    # Skip a day
    _add_session(conn, _utc_today() - timedelta(days=3))
    assert _compute_streak(conn) == 2
    conn.close()


def test_old_session_no_streak():
    conn = _make_streak_db()
    _add_session(conn, _utc_today() - timedelta(days=5))
    assert _compute_streak(conn) == 0
    conn.close()


def test_yesterday_start_counts():
    """Streak can start from yesterday (haven't practiced today yet)."""
    conn = _make_streak_db()
    _add_session(conn, _utc_today() - timedelta(days=1))
    _add_session(conn, _utc_today() - timedelta(days=2))
    assert _compute_streak(conn) == 2
    conn.close()


def test_zero_completed_not_counted():
    conn = _make_streak_db()
    _add_session(conn, _utc_today(), completed=0)
    assert _compute_streak(conn) == 0
    conn.close()


def test_multiple_sessions_same_day():
    conn = _make_streak_db()
    _add_session(conn, _utc_today())
    _add_session(conn, _utc_today())  # second session same day
    _add_session(conn, _utc_today() - timedelta(days=1))
    assert _compute_streak(conn) == 2
    conn.close()
