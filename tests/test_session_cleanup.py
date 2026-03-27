"""Tests for orphaned session cleanup and session outcome taxonomy."""

from datetime import datetime, timedelta, timezone, UTC

from mandarin.db.session import get_session_funnel, end_session


def test_orphaned_session_marked_interrupted(test_db):
    """Sessions with no ended_at older than 1 hour should be marked 'interrupted'."""
    conn, _ = test_db

    # Insert an orphaned session (started 2 hours ago, never ended)
    two_hours_ago = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO session_log (user_id, session_type, items_planned, started_at,
                                 items_completed, items_correct)
        VALUES (1, 'standard', 10, ?, 3, 2)
    """, (two_hours_ago,))
    conn.commit()

    # Run the same cleanup query used in create_app()
    conn.execute("""
        UPDATE session_log
        SET session_outcome = 'interrupted',
            ended_at = datetime('now'),
            early_exit = 1
        WHERE session_outcome = 'started'
          AND ended_at IS NULL
          AND started_at < datetime('now', '-1 hour')
    """)
    conn.commit()

    row = conn.execute("SELECT session_outcome, early_exit FROM session_log WHERE user_id = 1").fetchone()
    assert row["session_outcome"] == "interrupted"
    assert row["early_exit"] == 1


def test_recent_session_not_cleaned_up(test_db):
    """Sessions started less than 1 hour ago should NOT be cleaned up."""
    conn, _ = test_db

    # Insert a session started 10 minutes ago (still in progress)
    ten_min_ago = (datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO session_log (user_id, session_type, items_planned, started_at,
                                 items_completed, items_correct)
        VALUES (1, 'standard', 10, ?, 3, 2)
    """, (ten_min_ago,))
    conn.commit()

    # Run cleanup
    conn.execute("""
        UPDATE session_log
        SET session_outcome = 'interrupted',
            ended_at = datetime('now'),
            early_exit = 1
        WHERE session_outcome = 'started'
          AND ended_at IS NULL
          AND started_at < datetime('now', '-1 hour')
    """)
    conn.commit()

    row = conn.execute("SELECT session_outcome FROM session_log WHERE user_id = 1").fetchone()
    assert row["session_outcome"] == "started"  # Not touched — still in-progress


def test_completed_session_not_affected(test_db):
    """Already completed sessions should not be affected by cleanup."""
    conn, _ = test_db

    two_hours_ago = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO session_log (user_id, session_type, items_planned, started_at,
                                 ended_at, session_outcome, items_completed, items_correct)
        VALUES (1, 'standard', 10, ?, ?, 'completed', 10, 8)
    """, (two_hours_ago, one_hour_ago))
    conn.commit()

    # Run cleanup
    conn.execute("""
        UPDATE session_log
        SET session_outcome = 'interrupted',
            ended_at = datetime('now'),
            early_exit = 1
        WHERE session_outcome = 'started'
          AND ended_at IS NULL
          AND started_at < datetime('now', '-1 hour')
    """)
    conn.commit()

    row = conn.execute("SELECT session_outcome FROM session_log WHERE user_id = 1").fetchone()
    assert row["session_outcome"] == "completed"


def test_total_sessions_excludes_interrupted(test_db):
    """total_sessions should only count completed sessions."""
    conn, _ = test_db

    # end_session with early_exit and 0 items = bounced
    sid = conn.execute("""
        INSERT INTO session_log (user_id, session_type, items_planned, items_completed, items_correct)
        VALUES (1, 'standard', 10, 0, 0)
    """).lastrowid
    conn.commit()
    end_session(conn, sid, items_completed=0, items_correct=0, early_exit=True)

    profile = conn.execute("SELECT total_sessions FROM learner_profile WHERE user_id = 1").fetchone()
    assert profile["total_sessions"] == 0  # Bounced should not count


def test_session_funnel_includes_interrupted(test_db):
    """get_session_funnel should include interrupted count."""
    conn, _ = test_db

    two_hours_ago = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO session_log (user_id, session_type, items_planned, started_at,
                                 ended_at, session_outcome, items_completed, items_correct, early_exit)
        VALUES (1, 'standard', 10, ?, datetime('now'), 'interrupted', 3, 2, 1)
    """, (two_hours_ago,))
    conn.commit()

    funnel = get_session_funnel(conn, days=30, user_id=1)
    assert funnel["interrupted"] == 1
    assert funnel["completed"] == 0
