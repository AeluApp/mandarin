"""Session lifecycle — start, end, history, error summary."""

import logging
import sqlite3
import json
from datetime import datetime, date, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


def start_session(conn: sqlite3.Connection,
                  session_type: str = "standard",
                  items_planned: int = 0,
                  plan_snapshot: dict = None,
                  user_id: int = 1) -> int:
    """Start a new session. Returns session ID."""
    # Calculate days since last session
    last = conn.execute(
        "SELECT last_session_date FROM learner_profile WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    days_gap = None
    if last and last["last_session_date"]:
        last_date = date.fromisoformat(last["last_session_date"])
        days_gap = (date.today() - last_date).days

    local_hour = datetime.now().hour  # local time, not UTC
    cur = conn.execute("""
        INSERT INTO session_log
            (user_id, session_type, items_planned, days_since_last_session, plan_snapshot,
             session_started_hour, session_day_of_week)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, session_type, items_planned, days_gap,
          json.dumps(plan_snapshot) if plan_snapshot else None,
          local_hour, date.today().weekday()))
    conn.commit()
    return cur.lastrowid


def end_session(conn: sqlite3.Connection, session_id: int,
                items_completed: int, items_correct: int,
                modality_counts: dict = None,
                early_exit: bool = False,
                boredom_flags: int = 0,
                user_id: int = 1) -> None:
    """End a session and update profile."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    # Get start time for duration calc
    row = conn.execute(
        "SELECT started_at FROM session_log WHERE id = ?", (session_id,)
    ).fetchone()
    duration = None
    if row:
        start = datetime.strptime(row["started_at"], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
        duration = max(0, int((end - start).total_seconds()))

    # Determine funnel outcome
    if early_exit and items_completed == 0:
        outcome = "bounced"
    elif early_exit:
        outcome = "abandoned"
    else:
        outcome = "completed"

    conn.execute("""
        UPDATE session_log SET
            ended_at = ?, duration_seconds = ?,
            items_completed = ?, items_correct = ?,
            modality_counts = ?, early_exit = ?, boredom_flags = ?,
            session_outcome = ?
        WHERE id = ?
    """, (now, duration, items_completed, items_correct,
          json.dumps(modality_counts or {}),
          1 if early_exit else 0, boredom_flags, outcome, session_id))

    # Update learner profile
    conn.execute("""
        UPDATE learner_profile SET
            total_sessions = total_sessions + 1,
            last_session_date = ?,
            updated_at = ?
        WHERE user_id = ?
    """, (date.today().isoformat(), now, user_id))

    conn.commit()


def update_session_progress(conn: sqlite3.Connection, session_id: int,
                            items_completed: int, items_correct: int) -> None:
    """Incrementally update session counts after each drill.

    This ensures partial progress is saved even if the session crashes.
    """
    conn.execute("""
        UPDATE session_log SET items_completed = ?, items_correct = ?
        WHERE id = ?
    """, (items_completed, items_correct, session_id))
    conn.commit()


def get_session_history(conn: sqlite3.Connection, limit: int = 20,
                        user_id: int = 1) -> List[dict]:
    """Get recent sessions. Excludes bounces with zero items completed."""
    rows = conn.execute("""
        SELECT * FROM session_log
        WHERE items_completed > 0 AND user_id = ?
        ORDER BY started_at DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


def get_days_since_last_session(conn: sqlite3.Connection,
                                user_id: int = 1) -> Optional[int]:
    """Days since last completed session. None if no sessions."""
    from .profile import get_profile
    profile = get_profile(conn, user_id=user_id)
    if not profile.get("last_session_date"):
        return None
    last = date.fromisoformat(profile["last_session_date"])
    return (date.today() - last).days


def get_session_funnel(conn: sqlite3.Connection, days: int = 30,
                       user_id: int = 1) -> dict:
    """Session funnel metrics over the last N days.

    Returns counts of started, completed, abandoned, bounced sessions
    and a completion rate.
    """
    rows = conn.execute("""
        SELECT session_outcome, COUNT(*) as cnt
        FROM session_log
        WHERE started_at >= datetime('now', ? || ' days')
          AND session_outcome IS NOT NULL
          AND user_id = ?
        GROUP BY session_outcome
    """, (f"-{days}", user_id)).fetchall()

    counts = {r["session_outcome"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    completed = counts.get("completed", 0)
    abandoned = counts.get("abandoned", 0)
    bounced = counts.get("bounced", 0)
    started = counts.get("started", 0)

    return {
        "total": total,
        "completed": completed,
        "abandoned": abandoned,
        "bounced": bounced,
        "in_progress": started,
        "completion_rate": (completed / total * 100) if total > 0 else 0,
        "days": days,
    }


def get_error_summary(conn: sqlite3.Connection,
                      last_n_sessions: int = 10,
                      user_id: int = 1) -> dict:
    """Error type counts from recent sessions."""
    rows = conn.execute("""
        SELECT error_type, COUNT(*) as count
        FROM error_log
        WHERE user_id = ?
          AND session_id IN (
            SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT ?
        )
        GROUP BY error_type
        ORDER BY count DESC
    """, (user_id, user_id, last_n_sessions)).fetchall()
    return {r["error_type"]: r["count"] for r in rows}
