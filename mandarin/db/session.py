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
                  user_id: int = 1,
                  client_platform: str = "cli",
                  experiment_variant: str = None) -> int:
    """Start a new session. Returns session ID."""
    logger.info("Starting session: type=%s, planned=%d, user=%d, platform=%s",
                session_type, items_planned, user_id, client_platform)
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
             session_started_hour, session_day_of_week, client_platform, experiment_variant)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, session_type, items_planned, days_gap,
          json.dumps(plan_snapshot) if plan_snapshot else None,
          local_hour, date.today().weekday(), client_platform, experiment_variant))
    conn.commit()
    session_id = cur.lastrowid

    # Lifecycle: first_session_started (if this is the user's first session)
    try:
        prev = conn.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE user_id = ? AND id < ?",
            (user_id, session_id)
        ).fetchone()
        if prev and prev["cnt"] == 0:
            from ..marketing_hooks import log_lifecycle_event
            log_lifecycle_event("first_session_started", user_id=str(user_id), conn=conn,
                                session_type=session_type)
            # Stamp first_session_at on user record
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE user SET first_session_at = ? WHERE id = ? AND first_session_at IS NULL",
                (now_str, user_id)
            )
            conn.commit()
    except Exception:
        pass

    return session_id


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
    if row and row["started_at"]:
        try:
            start = datetime.strptime(row["started_at"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
            duration = max(0, int((end - start).total_seconds()))
        except (ValueError, TypeError):
            pass

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
    # Increment total_sessions only for "completed", but always update
    # last_session_date if any items were completed (so streak/gap tracking
    # stays accurate even for abandoned sessions with progress).
    if outcome == "completed":
        conn.execute("""
            UPDATE learner_profile SET
                total_sessions = total_sessions + 1,
                last_session_date = ?,
                updated_at = ?
            WHERE user_id = ?
        """, (date.today().isoformat(), now, user_id))
    elif items_completed > 0:
        conn.execute("""
            UPDATE learner_profile SET
                last_session_date = ?,
                updated_at = ?
            WHERE user_id = ?
        """, (date.today().isoformat(), now, user_id))
    else:
        conn.execute("""
            UPDATE learner_profile SET
                updated_at = ?
            WHERE user_id = ?
        """, (now, user_id))

    conn.commit()

    # Lifecycle: session_complete
    if outcome == "completed":
        try:
            from ..marketing_hooks import log_lifecycle_event
            log_lifecycle_event("session_complete", user_id=str(user_id), conn=conn,
                                session_id=session_id, items_completed=items_completed,
                                items_correct=items_correct, duration=duration)
        except Exception:
            pass

        # Activation detection: 3+ completed sessions within 14 days of signup
        try:
            user_row = conn.execute(
                "SELECT created_at, activation_at FROM user WHERE id = ?", (user_id,)
            ).fetchone()
            if user_row and not user_row["activation_at"]:
                session_count = conn.execute(
                    """SELECT COUNT(*) as cnt FROM session_log
                       WHERE user_id = ? AND session_outcome = 'completed'
                         AND started_at <= datetime(?, '+14 days')""",
                    (user_id, user_row["created_at"])
                ).fetchone()
                if session_count and session_count["cnt"] >= 3:
                    conn.execute(
                        "UPDATE user SET activation_at = ? WHERE id = ? AND activation_at IS NULL",
                        (now, user_id)
                    )
                    conn.commit()
                    log_lifecycle_event("user_activated", user_id=str(user_id), conn=conn,
                                        sessions_to_activate=session_count["cnt"])
        except Exception:
            pass


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
    """Days since last session with any items completed. None if no sessions.

    Cross-checks both the profile's last_session_date and session_log to
    use whichever is more recent (guards against profile not being updated).
    """
    from .profile import get_profile
    profile = get_profile(conn, user_id=user_id)
    profile_date = None
    if profile.get("last_session_date"):
        try:
            profile_date = date.fromisoformat(profile["last_session_date"])
        except (ValueError, TypeError):
            pass

    # Also check session_log directly as backup
    log_row = conn.execute(
        """SELECT date(started_at) as d FROM session_log
           WHERE user_id = ? AND items_completed > 0
           ORDER BY started_at DESC LIMIT 1""",
        (user_id,)
    ).fetchone()
    log_date = None
    if log_row and log_row["d"]:
        try:
            log_date = date.fromisoformat(log_row["d"])
        except (ValueError, TypeError):
            pass

    # Use the most recent of the two
    last = max(filter(None, [profile_date, log_date]), default=None)
    if last is None:
        return None
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
    interrupted = counts.get("interrupted", 0)

    return {
        "total": total,
        "completed": completed,
        "abandoned": abandoned,
        "bounced": bounced,
        "interrupted": interrupted,
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
