"""Social, Accountability, and Habit Architecture (Doc 18).

Commitment devices, study partner features, and cohort benchmarking.
"""

import logging
import sqlite3
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def create_weekly_commitment(
    conn: sqlite3.Connection, user_id: int,
    target_sessions: int, target_new_items: int
) -> dict:
    """Creates a weekly study commitment (commitment device)."""
    week_start = _current_week_start()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO study_commitments
            (user_id, week_start, target_sessions, target_new_items)
            VALUES (?,?,?,?)
        """, (user_id, week_start.isoformat(), target_sessions, target_new_items))
    except sqlite3.OperationalError:
        return {'error': 'table not available'}

    return {
        'week_start': week_start.isoformat(),
        'target_sessions': target_sessions,
        'target_new_items': target_new_items,
        'message': f'Committed: {target_sessions} sessions and {target_new_items} new items this week.',
    }


def get_commitment_status(conn: sqlite3.Connection, user_id: int) -> dict:
    """Returns current week's commitment status."""
    week_start = _current_week_start()
    commitment = None
    try:
        commitment = conn.execute("""
            SELECT * FROM study_commitments
            WHERE user_id=? AND week_start=?
        """, (user_id, week_start.isoformat())).fetchone()
    except sqlite3.OperationalError:
        return {'has_commitment': False}

    if not commitment:
        return {'has_commitment': False}

    sessions_done = 0
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id=? AND started_at >= ? AND ended_at IS NOT NULL
        """, (user_id, f'{week_start.isoformat()} 00:00:00')).fetchone()
        sessions_done = (row['cnt'] or 0) if row else 0
    except sqlite3.OperationalError:
        pass

    target = commitment['target_sessions'] or 1
    pct_sessions = sessions_done / max(1, target)
    days_remaining = 7 - (date.today() - week_start).days

    return {
        'has_commitment': True,
        'target_sessions': target,
        'completed_sessions': sessions_done,
        'pct_complete': round(pct_sessions * 100),
        'days_remaining': days_remaining,
        'on_track': sessions_done >= (target * (7 - days_remaining) / 7),
    }


def evaluate_weekly_commitments(conn: sqlite3.Connection) -> None:
    """Runs at end of each week. Evaluates all commitments."""
    last_week = _current_week_start() - timedelta(days=7)
    try:
        pending = conn.execute("""
            SELECT * FROM study_commitments
            WHERE week_start=? AND commitment_met IS NULL
        """, (last_week.isoformat(),)).fetchall()
    except sqlite3.OperationalError:
        return

    for c in pending:
        try:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM session_log
                WHERE user_id=?
                AND started_at BETWEEN ? AND ?
                AND ended_at IS NOT NULL
            """, (
                c['user_id'],
                f"{c['week_start']} 00:00:00",
                f"{(last_week + timedelta(days=7)).isoformat()} 23:59:59",
            )).fetchone()
            sessions_done = (row['cnt'] or 0) if row else 0
        except sqlite3.OperationalError:
            sessions_done = 0

        met = sessions_done >= (c['target_sessions'] or 0)
        try:
            conn.execute("""
                UPDATE study_commitments
                SET completed_sessions=?, commitment_met=?
                WHERE id=?
            """, (sessions_done, int(met), c['id']))
        except sqlite3.OperationalError:
            pass


def _current_week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


# ─────────────────────────────────────────────
# ANALYZER
# ─────────────────────────────────────────────

def analyze_accountability(conn: sqlite3.Connection) -> list[dict]:
    """Audit cycle analyzer for commitment effectiveness."""
    from ..intelligence._base import _finding
    findings = []

    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(commitment_met) as met
            FROM study_commitments
            WHERE week_start >= date('now','-28 days')
            AND commitment_met IS NOT NULL
        """).fetchone()

        total = (row['total'] or 0) if row else 0
        if total >= 4:
            met = (row['met'] or 0)
            rate = met / total
            if rate < 0.50:
                findings.append(_finding(
                    dimension="accountability",
                    severity="medium",
                    title=f"Commitment met rate low: {rate:.0%} over last 4 weeks",
                    analysis="Commitments being set but not met. Targets may be too ambitious.",
                    recommendation="Consider reducing session frequency target or session length.",
                    claude_prompt="Check study_commitments met rate over recent weeks.",
                    impact="Unmet commitments can discourage rather than motivate.",
                    files=["mandarin/ai/accountability.py"],
                ))
    except sqlite3.OperationalError:
        pass

    return findings
