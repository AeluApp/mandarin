"""Weekly Metrics Report Generator — Marketing analytics for the Aelu app.

Calculates Level 1-3 KPIs from metrics-dashboard.md and outputs a formatted
weekly report. Saves reports to the reports/ directory as .txt and .md files.

Designed for the current single-user local database, with queries adapted
to work without a users table. Forward-compatible with multi-user.

KPIs covered:
  Business Health:  active users, WAU, session counts
  Engagement:       sessions/user/week, duration, accuracy, diversity,
                    feature adoption (reading, listening, cleanup loop)
  Learning Outcomes: mastery distribution, retention, most-failed items,
                     HSK level distribution
  Funnel:           new content, vocab encounters, sessions by day-of-week

Usage:
    python -m mandarin.metrics_report
    python -m mandarin.metrics_report --weeks 4
    ./run metrics
"""

import argparse
import json
import logging
import sqlite3
from datetime import datetime, date, timedelta, timezone, UTC
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from .settings import DB_PATH as _DEFAULT_DB_PATH
_REPORTS_DIR = Path(__file__).parent.parent / "reports"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _safe_div(a, b, default=0.0):
    return a / b if b and b > 0 else default


def _safe_pct(a, b, default=0.0):
    return (a / b * 100) if b and b > 0 else default


# ---------------------------------------------------------------------------
# Business Health KPIs
# ---------------------------------------------------------------------------

def _business_health(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Calculate business health metrics.

    For single-user: active_users is 0 or 1. Multi-user: COUNT(DISTINCT user_id).
    """
    metrics = {}

    # Active users: had a session in last 30 days
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM session_log
        WHERE started_at >= datetime('now', '-30 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    sessions_30d = (row["cnt"] or 0) if row else 0
    metrics["active_users_30d"] = 1 if sessions_30d > 0 else 0

    # WAU: session in last 7 days
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    sessions_7d = (row["cnt"] or 0) if row else 0
    metrics["wau"] = 1 if sessions_7d > 0 else 0
    metrics["sessions_this_week"] = sessions_7d

    # Sessions last week for comparison
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
          AND started_at < datetime('now', '-7 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    metrics["sessions_last_week"] = (row["cnt"] or 0) if row else 0

    return metrics


# ---------------------------------------------------------------------------
# Engagement KPIs
# ---------------------------------------------------------------------------

def _engagement(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Calculate engagement metrics."""
    metrics = {}

    # Sessions per active user this week (single-user: same as session count)
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    metrics["sessions_per_user_week"] = row["cnt"] or 0

    # Average session duration (last 7 days)
    row = conn.execute("""
        SELECT AVG(duration_seconds) AS avg_dur,
               MIN(duration_seconds) AS min_dur,
               MAX(duration_seconds) AS max_dur
        FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND items_completed > 0
          AND duration_seconds IS NOT NULL
          AND duration_seconds > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    avg_dur = row["avg_dur"] if row else None
    metrics["avg_session_duration_sec"] = round(avg_dur, 0) if avg_dur else 0
    metrics["avg_session_duration_min"] = round(avg_dur / 60, 1) if avg_dur else 0.0

    # Drill accuracy — overall (last 7 days)
    row = conn.execute("""
        SELECT SUM(items_completed) AS total,
               SUM(items_correct) AS correct
        FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    total_items = (row["total"] or 0) if row else 0
    total_correct = (row["correct"] or 0) if row else 0
    metrics["drill_accuracy_pct"] = round(_safe_pct(total_correct, total_items), 1)

    # Drill accuracy by modality (from progress table, overall)
    modality_acc = {}
    if _table_exists(conn, "progress"):
        rows = conn.execute("""
            SELECT modality,
                   SUM(total_correct) AS correct,
                   SUM(total_attempts) AS attempts
            FROM progress
            WHERE total_attempts > 0
              AND user_id = ?
            GROUP BY modality
        """, (user_id,)).fetchall()
        for r in rows:
            mod = r["modality"] if r else None
            if mod:
                modality_acc[mod] = round(_safe_pct(r["correct"] or 0, r["attempts"] or 0), 1)
    metrics["accuracy_by_modality"] = modality_acc

    # Drill type diversity (unique modalities used this week)
    types_seen = set()
    rows = conn.execute("""
        SELECT modality_counts FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND items_completed > 0
          AND modality_counts IS NOT NULL
          AND user_id = ?
    """, (user_id,)).fetchall()
    for r in rows:
        try:
            mc = json.loads(r["modality_counts"])
            for k, v in mc.items():
                if v and v > 0:
                    types_seen.add(k)
        except (json.JSONDecodeError, TypeError):
            pass
    metrics["drill_type_diversity"] = len(types_seen)
    metrics["drill_types_used"] = sorted(types_seen)

    # Feature adoption: reading
    reading_count = 0
    listening_count = 0
    for r in rows:
        try:
            mc = json.loads(r["modality_counts"])
            if mc.get("reading", 0) > 0:
                reading_count += 1
            if mc.get("listening", 0) > 0:
                listening_count += 1
        except (json.JSONDecodeError, TypeError):
            pass
    total_sessions_week = len(rows) or 1
    metrics["reading_adoption_pct"] = round(_safe_pct(reading_count, total_sessions_week), 1)
    metrics["listening_adoption_pct"] = round(_safe_pct(listening_count, total_sessions_week), 1)
    metrics["reading_sessions"] = reading_count
    metrics["listening_sessions"] = listening_count

    # Feature adoption: cleanup loop (words looked up then drilled)
    if _table_exists(conn, "vocab_encounter"):
        row = conn.execute("""
            SELECT COUNT(*) AS looked_up
            FROM vocab_encounter
            WHERE looked_up = 1
              AND created_at >= datetime('now', '-30 days')
              AND user_id = ?
        """, (user_id,)).fetchone()
        looked_up = row["looked_up"] or 0

        # Check how many of those looked-up words were subsequently drilled
        drilled_after = 0
        if looked_up > 0 and _table_exists(conn, "progress"):
            row2 = conn.execute("""
                SELECT COUNT(DISTINCT ve.hanzi) AS cnt
                FROM vocab_encounter ve
                JOIN content_item ci ON ci.hanzi = ve.hanzi
                JOIN progress p ON p.content_item_id = ci.id
                WHERE ve.looked_up = 1
                  AND ve.created_at >= datetime('now', '-30 days')
                  AND ve.user_id = ?
                  AND p.total_attempts > 0
                  AND p.last_review_date >= ve.created_at
                  AND p.user_id = ?
            """, (user_id, user_id)).fetchone()
            drilled_after = (row2["cnt"] or 0) if row2 else 0

        metrics["cleanup_loop_looked_up"] = looked_up
        metrics["cleanup_loop_drilled"] = drilled_after
        metrics["cleanup_loop_pct"] = round(_safe_pct(drilled_after, looked_up), 1)
    else:
        metrics["cleanup_loop_looked_up"] = 0
        metrics["cleanup_loop_drilled"] = 0
        metrics["cleanup_loop_pct"] = 0.0

    # Early exit rate and boredom flags
    row = conn.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN early_exit = 1 THEN 1 ELSE 0 END) AS exits,
               SUM(CASE WHEN boredom_flags > 0 THEN 1 ELSE 0 END) AS bored
        FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND user_id = ?
    """, (user_id,)).fetchone()
    total_all = row["total"] or 1
    metrics["early_exit_rate_pct"] = round(_safe_pct(row["exits"] or 0, total_all), 1)
    metrics["boredom_flag_rate_pct"] = round(_safe_pct(row["bored"] or 0, total_all), 1)

    return metrics


# ---------------------------------------------------------------------------
# Learning Outcomes KPIs
# ---------------------------------------------------------------------------

def _learning_outcomes(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Calculate learning outcome metrics."""
    metrics = {}

    if not _table_exists(conn, "progress"):
        return {
            "words_at_85pct": 0,
            "avg_retention_pct": 0.0,
            "most_failed_items": [],
            "hsk_distribution": {},
            "mastery_distribution": {},
        }

    # Words at 85%+ mastery (accuracy over all attempts)
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM progress
        WHERE total_attempts >= 3
          AND (total_correct * 1.0 / total_attempts) >= 0.85
          AND user_id = ?
    """, (user_id,)).fetchone()
    metrics["words_at_85pct"] = row["cnt"] or 0

    # Average vocabulary retention (items reviewed in last 30 days)
    row = conn.execute("""
        SELECT AVG(total_correct * 1.0 / total_attempts) AS avg_ret
        FROM progress
        WHERE total_attempts > 0
          AND last_review_date >= date('now', '-30 days')
          AND user_id = ?
    """, (user_id,)).fetchone()
    avg_ret = row["avg_ret"] if row else None
    metrics["avg_retention_pct"] = round(avg_ret * 100, 1) if avg_ret else 0.0

    # Most-failed items (top 10)
    most_failed = []
    if _table_exists(conn, "error_log"):
        rows = conn.execute("""
            SELECT ci.hanzi, ci.pinyin, ci.english, ci.hsk_level,
                   COUNT(e.id) AS error_count,
                   (SELECT e2.error_type FROM error_log e2
                    WHERE e2.content_item_id = ci.id
                      AND e2.user_id = ?
                    GROUP BY e2.error_type ORDER BY COUNT(*) DESC LIMIT 1
                   ) AS primary_error_type
            FROM error_log e
            JOIN content_item ci ON ci.id = e.content_item_id
            WHERE e.created_at >= datetime('now', '-30 days')
              AND e.user_id = ?
            GROUP BY ci.id
            ORDER BY error_count DESC
            LIMIT 10
        """, (user_id, user_id)).fetchall()
        for r in rows:
            most_failed.append({
                "hanzi": r["hanzi"],
                "pinyin": r["pinyin"],
                "english": r["english"],
                "hsk_level": r["hsk_level"],
                "error_count": r["error_count"],
                "error_type": r["primary_error_type"],
            })
    metrics["most_failed_items"] = most_failed

    # HSK level distribution (of actively studied items)
    hsk_dist = {}
    rows = conn.execute("""
        SELECT ci.hsk_level, COUNT(DISTINCT ci.id) AS cnt
        FROM content_item ci
        JOIN progress p ON p.content_item_id = ci.id
        WHERE p.total_attempts > 0
          AND ci.hsk_level IS NOT NULL
          AND p.user_id = ?
        GROUP BY ci.hsk_level
        ORDER BY ci.hsk_level
    """, (user_id,)).fetchall()
    for r in rows:
        hsk_dist[f"HSK {r['hsk_level']}"] = r["cnt"]
    metrics["hsk_distribution"] = hsk_dist

    # Mastery stage distribution
    mastery_dist = {}
    rows = conn.execute("""
        SELECT mastery_stage, COUNT(*) AS cnt
        FROM progress
        WHERE total_attempts > 0
          AND user_id = ?
        GROUP BY mastery_stage
        ORDER BY cnt DESC
    """, (user_id,)).fetchall()
    for r in rows:
        mastery_dist[r["mastery_stage"]] = r["cnt"]
    metrics["mastery_distribution"] = mastery_dist

    return metrics


# ---------------------------------------------------------------------------
# Funnel / activity pattern KPIs
# ---------------------------------------------------------------------------

def _funnel_metrics(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Calculate funnel and activity pattern metrics."""
    metrics = {}

    # New content items encountered this week
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM content_item
        WHERE created_at >= datetime('now', '-7 days')
    """).fetchone()
    metrics["new_content_this_week"] = row["cnt"] or 0

    # Vocab encounters this week
    if _table_exists(conn, "vocab_encounter"):
        row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM vocab_encounter
            WHERE created_at >= datetime('now', '-7 days')
              AND user_id = ?
        """, (user_id,)).fetchone()
        metrics["vocab_encounters_this_week"] = row["cnt"] or 0
    else:
        metrics["vocab_encounters_this_week"] = 0

    # Sessions by day of week (last 30 days)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_counts = {d: 0 for d in day_names}

    rows = conn.execute("""
        SELECT session_day_of_week AS dow, COUNT(*) AS cnt
        FROM session_log
        WHERE started_at >= datetime('now', '-30 days')
          AND items_completed > 0
          AND session_day_of_week IS NOT NULL
          AND user_id = ?
        GROUP BY session_day_of_week
    """, (user_id,)).fetchall()
    for r in rows:
        dow = r["dow"]
        if dow is not None and 0 <= dow <= 6:
            day_counts[day_names[dow]] = r["cnt"]

    # If session_day_of_week is not populated, parse from started_at
    if all(v == 0 for v in day_counts.values()):
        rows = conn.execute("""
            SELECT started_at FROM session_log
            WHERE started_at >= datetime('now', '-30 days')
              AND items_completed > 0
              AND user_id = ?
        """, (user_id,)).fetchall()
        for r in rows:
            try:
                dt = datetime.fromisoformat(r["started_at"])
                day_counts[day_names[dt.weekday()]] += 1
            except (ValueError, TypeError):
                pass

    metrics["sessions_by_day"] = day_counts

    # Session outcome distribution (last 30 days)
    outcome_dist = {}
    if _table_exists(conn, "session_log"):
        rows = conn.execute("""
            SELECT session_outcome, COUNT(*) AS cnt
            FROM session_log
            WHERE started_at >= datetime('now', '-30 days')
              AND session_outcome IS NOT NULL
              AND user_id = ?
            GROUP BY session_outcome
        """, (user_id,)).fetchall()
        for r in rows:
            outcome_dist[r["session_outcome"] or "unknown"] = r["cnt"]
    metrics["session_outcomes"] = outcome_dist

    return metrics


# ---------------------------------------------------------------------------
# North Star: Weekly Items Mastered per Active User
# ---------------------------------------------------------------------------

def _north_star(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Calculate the north star metric: weekly items mastered per active user.

    An item is 'mastered' when it has 3+ attempts and 85%+ accuracy.
    We count items that crossed the 85% threshold this week (reviewed this week
    and currently at 85%+).
    """
    metrics = {}

    if not _table_exists(conn, "progress"):
        return {"items_mastered_this_week": 0, "mastered_per_active_user": 0.0}

    # Items reviewed this week that are now at 85%+ mastery
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM progress
        WHERE total_attempts >= 3
          AND (total_correct * 1.0 / total_attempts) >= 0.85
          AND last_review_date >= date('now', '-7 days')
          AND user_id = ?
    """, (user_id,)).fetchone()
    mastered = row["cnt"] or 0
    metrics["items_mastered_this_week"] = mastered

    # Active users this week (for multi-user: COUNT DISTINCT)
    row = conn.execute("""
        SELECT COUNT(DISTINCT user_id) AS cnt FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND items_completed > 0
    """).fetchone()
    active_users = row["cnt"] or 1
    metrics["active_users_this_week"] = active_users
    metrics["mastered_per_active_user"] = round(_safe_div(mastered, active_users), 1)

    return metrics


# ---------------------------------------------------------------------------
# False Mastery Health Metric (Doctrine §2)
# ---------------------------------------------------------------------------

def _false_mastery_rate(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Rate at which mastered items subsequently fail. Healthy if ≤10%."""
    from .diagnostics import compute_false_mastery_rate
    return compute_false_mastery_rate(conn, user_id=user_id)


# ---------------------------------------------------------------------------
# Completion Rate by Segment
# ---------------------------------------------------------------------------

def _completion_by_segment(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Session completion rate broken out by session_type and HSK level band."""
    metrics = {"by_session_type": {}, "by_hsk_band": {}}

    # By session_type (exclude sessions < 30 seconds)
    rows = conn.execute("""
        SELECT session_type,
               COUNT(*) AS total,
               SUM(CASE WHEN session_outcome = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND (duration_seconds IS NULL OR duration_seconds >= 30)
          AND user_id = ?
        GROUP BY session_type
    """, (user_id,)).fetchall()
    for r in rows:
        stype = r["session_type"] or "unknown"
        total = r["total"] or 0
        completed = r["completed"] or 0
        metrics["by_session_type"][stype] = {
            "total": total,
            "completed": completed,
            "rate": round(_safe_pct(completed, total), 1),
        }

    # Accuracy by HSK level band (from progress table, not sessions)
    if _table_exists(conn, "progress"):
        rows = conn.execute("""
            SELECT
                CASE
                    WHEN ci.hsk_level BETWEEN 1 AND 3 THEN 'HSK 1-3'
                    WHEN ci.hsk_level BETWEEN 4 AND 6 THEN 'HSK 4-6'
                    WHEN ci.hsk_level BETWEEN 7 AND 9 THEN 'HSK 7-9'
                    ELSE 'Other'
                END AS band,
                SUM(p.total_attempts) AS attempts,
                SUM(p.total_correct) AS correct
            FROM progress p
            JOIN content_item ci ON ci.id = p.content_item_id
            WHERE p.total_attempts > 0
              AND p.last_review_date >= date('now', '-7 days')
              AND p.user_id = ?
            GROUP BY band
        """, (user_id,)).fetchall()
        for r in rows:
            band = r["band"] or "Other"
            attempts = r["attempts"] or 0
            correct = r["correct"] or 0
            metrics["by_hsk_band"][band] = {
                "total": attempts,
                "completed": correct,
                "rate": round(_safe_pct(correct, attempts), 1),
            }

    # Overall rate
    row = conn.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN session_outcome = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND (duration_seconds IS NULL OR duration_seconds >= 30)
          AND user_id = ?
    """, (user_id,)).fetchone()
    total = row["total"] or 0
    completed = row["completed"] or 0
    metrics["overall_rate"] = round(_safe_pct(completed, total), 1)
    metrics["overall_total"] = total
    metrics["overall_completed"] = completed

    return metrics


# ---------------------------------------------------------------------------
# D1/D7/D30 Retention Cohorts (multi-user ready)
# ---------------------------------------------------------------------------

def _retention_cohorts(conn: sqlite3.Connection) -> dict:
    """Calculate D1, D7, D30 retention rates across all users.

    For each user who signed up in the trailing 30 days, check if they had
    a session on day 1, day 7, and day 30 relative to signup.
    """
    metrics = {"d1": 0.0, "d7": 0.0, "d30": 0.0, "signups_30d": 0}

    if not _table_exists(conn, "lifecycle_event"):
        return metrics

    # Get signup dates for users who signed up in last 60 days
    signups = conn.execute("""
        SELECT user_id, MIN(created_at) AS signup_date
        FROM lifecycle_event
        WHERE event_type = 'signup'
          AND created_at >= datetime('now', '-60 days')
        GROUP BY user_id
    """).fetchall()

    if not signups:
        return metrics

    d1_eligible = 0
    d1_retained = 0
    d7_eligible = 0
    d7_retained = 0
    d30_eligible = 0
    d30_retained = 0

    for s in signups:
        uid = s["user_id"]
        signup_str = s["signup_date"]
        if not signup_str:
            continue
        try:
            signup_dt = datetime.fromisoformat(signup_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        now = datetime.now(UTC)
        days_since = (now - signup_dt).days

        # D1: had session on day 0-1 (within 48h of signup)
        if days_since >= 1:
            d1_eligible += 1
            row = conn.execute("""
                SELECT 1 FROM session_log
                WHERE user_id = ?
                  AND items_completed > 0
                  AND started_at >= ? AND started_at < ?
                LIMIT 1
            """, (uid, signup_str, (signup_dt + timedelta(hours=48)).isoformat())).fetchone()
            if row:
                d1_retained += 1

        # D7: had session on days 6-8
        if days_since >= 8:
            d7_eligible += 1
            day6 = (signup_dt + timedelta(days=6)).isoformat()
            day9 = (signup_dt + timedelta(days=9)).isoformat()
            row = conn.execute("""
                SELECT 1 FROM session_log
                WHERE user_id = ?
                  AND items_completed > 0
                  AND started_at >= ? AND started_at < ?
                LIMIT 1
            """, (uid, day6, day9)).fetchone()
            if row:
                d7_retained += 1

        # D30: had session on days 28-32
        if days_since >= 32:
            d30_eligible += 1
            day28 = (signup_dt + timedelta(days=28)).isoformat()
            day33 = (signup_dt + timedelta(days=33)).isoformat()
            row = conn.execute("""
                SELECT 1 FROM session_log
                WHERE user_id = ?
                  AND items_completed > 0
                  AND started_at >= ? AND started_at < ?
                LIMIT 1
            """, (uid, day28, day33)).fetchone()
            if row:
                d30_retained += 1

    metrics["signups_30d"] = len(signups)
    metrics["d1"] = round(_safe_pct(d1_retained, d1_eligible), 1)
    metrics["d1_eligible"] = d1_eligible
    metrics["d1_retained"] = d1_retained
    metrics["d7"] = round(_safe_pct(d7_retained, d7_eligible), 1)
    metrics["d7_eligible"] = d7_eligible
    metrics["d7_retained"] = d7_retained
    metrics["d30"] = round(_safe_pct(d30_retained, d30_eligible), 1)
    metrics["d30_eligible"] = d30_eligible
    metrics["d30_retained"] = d30_retained

    return metrics


# ---------------------------------------------------------------------------
# Growth Accounting (multi-user ready)
# ---------------------------------------------------------------------------

def _growth_accounting(conn: sqlite3.Connection) -> dict:
    """Break active users into new, retained, resurrected, and churned.

    - New: session this week, no session in any prior week
    - Retained: session this week AND last week
    - Resurrected: session this week, none in weeks 2-4, had one before that
    - Churned: session last week, no session this week
    """
    metrics = {"new": 0, "retained": 0, "resurrected": 0, "churned": 0,
               "net_retention": 0.0}

    # Users active this week
    this_week = set()
    rows = conn.execute("""
        SELECT DISTINCT user_id FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND items_completed > 0
    """).fetchall()
    for r in rows:
        this_week.add(r["user_id"])

    # Users active last week
    last_week = set()
    rows = conn.execute("""
        SELECT DISTINCT user_id FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
          AND started_at < datetime('now', '-7 days')
          AND items_completed > 0
    """).fetchall()
    for r in rows:
        last_week.add(r["user_id"])

    # Users active weeks 2-4 ago (but not last week)
    weeks_2_4 = set()
    rows = conn.execute("""
        SELECT DISTINCT user_id FROM session_log
        WHERE started_at >= datetime('now', '-28 days')
          AND started_at < datetime('now', '-14 days')
          AND items_completed > 0
    """).fetchall()
    for r in rows:
        weeks_2_4.add(r["user_id"])

    # Users with any session before 4 weeks ago
    older = set()
    rows = conn.execute("""
        SELECT DISTINCT user_id FROM session_log
        WHERE started_at < datetime('now', '-28 days')
          AND items_completed > 0
    """).fetchall()
    for r in rows:
        older.add(r["user_id"])

    all_prior = last_week | weeks_2_4 | older

    for uid in this_week:
        if uid not in all_prior:
            metrics["new"] += 1
        elif uid in last_week:
            metrics["retained"] += 1
        else:
            metrics["resurrected"] += 1

    for uid in last_week:
        if uid not in this_week:
            metrics["churned"] += 1

    retained_plus_churned = metrics["retained"] + metrics["churned"]
    metrics["net_retention"] = round(
        _safe_pct(metrics["retained"] + metrics["resurrected"], retained_plus_churned), 1
    ) if retained_plus_churned > 0 else 0.0

    return metrics


# ---------------------------------------------------------------------------
# Crash Rate
# ---------------------------------------------------------------------------

def _crash_rate(conn: sqlite3.Connection) -> dict:
    """Calculate server crash rate: crashes / total sessions this week."""
    metrics = {"crashes": 0, "sessions": 0, "rate_pct": 0.0, "top_errors": []}

    # Crash count (last 7 days)
    if _table_exists(conn, "crash_log"):
        row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM crash_log
            WHERE timestamp >= datetime('now', '-7 days')
        """).fetchone()
        metrics["crashes"] = row["cnt"] or 0

        # Top 3 error types
        rows = conn.execute("""
            SELECT error_type, COUNT(*) AS cnt
            FROM crash_log
            WHERE timestamp >= datetime('now', '-7 days')
            GROUP BY error_type
            ORDER BY cnt DESC
            LIMIT 3
        """).fetchall()
        metrics["top_errors"] = [
            {"type": r["error_type"], "count": r["cnt"]} for r in rows
        ]

    # Total sessions as denominator (more reliable than log line count)
    row = conn.execute("""
        SELECT COUNT(*) AS cnt FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
    """).fetchone()
    metrics["sessions"] = row["cnt"] or 0

    metrics["rate_pct"] = round(
        _safe_pct(metrics["crashes"], metrics["sessions"]), 3
    )

    return metrics


# ---------------------------------------------------------------------------
# Week-over-week comparison
# ---------------------------------------------------------------------------

def _week_comparison(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Compare this week vs. last week on key metrics."""
    comp = {}

    # This week
    tw = conn.execute("""
        SELECT COUNT(*) AS sessions,
               SUM(items_completed) AS items,
               SUM(items_correct) AS correct,
               AVG(duration_seconds) AS avg_dur
        FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()

    # Last week
    lw = conn.execute("""
        SELECT COUNT(*) AS sessions,
               SUM(items_completed) AS items,
               SUM(items_correct) AS correct,
               AVG(duration_seconds) AS avg_dur
        FROM session_log
        WHERE started_at >= datetime('now', '-14 days')
          AND started_at < datetime('now', '-7 days')
          AND items_completed > 0
          AND user_id = ?
    """, (user_id,)).fetchone()

    tw_sessions = tw["sessions"] or 0
    lw_sessions = lw["sessions"] or 0
    tw_items = tw["items"] or 0
    lw_items = lw["items"] or 0
    tw_correct = tw["correct"] or 0
    lw_correct = lw["correct"] or 0
    tw_dur = tw["avg_dur"] or 0
    lw_dur = lw["avg_dur"] or 0

    comp["sessions_delta"] = tw_sessions - lw_sessions
    comp["items_delta"] = tw_items - lw_items
    comp["accuracy_this_week"] = round(_safe_pct(tw_correct, tw_items), 1)
    comp["accuracy_last_week"] = round(_safe_pct(lw_correct, lw_items), 1)
    comp["accuracy_delta"] = round(comp["accuracy_this_week"] - comp["accuracy_last_week"], 1)
    comp["avg_dur_this_week"] = round(tw_dur / 60, 1) if tw_dur else 0
    comp["avg_dur_last_week"] = round(lw_dur / 60, 1) if lw_dur else 0

    return comp


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _delta_str(val, suffix=""):
    """Format a delta value with +/- prefix."""
    if val > 0:
        return f"+{val}{suffix}"
    elif val < 0:
        return f"{val}{suffix}"
    return f"0{suffix}"


def _generate_report_text(
    biz: dict,
    eng: dict,
    learn: dict,
    funnel: dict,
    wow: dict,
    report_date: str,
    extra: dict | None = None,
) -> str:
    """Generate the weekly report as plain text."""
    extra = extra or {}
    ns = extra.get("north_star", {})
    comp_seg = extra.get("completion_by_segment", {})
    retention = extra.get("retention", {})
    growth = extra.get("growth", {})
    crashes = extra.get("crashes", {})

    lines = []
    lines.append(f"WEEKLY REPORT: Week of {report_date}")
    lines.append("=" * 60)
    lines.append("")

    # North Star
    lines.append("NORTH STAR")
    mastered = ns.get("items_mastered_this_week", 0)
    per_user = ns.get("mastered_per_active_user", 0.0)
    lines.append(f"  Items mastered/user:     {per_user} "
                 f"({mastered} items mastered this week)")
    lines.append(f"  WASU:                    {biz['wau']} "
                 f"(sessions this week: {biz['sessions_this_week']})")
    lines.append("")

    # Business Health
    lines.append("BUSINESS HEALTH")
    lines.append(f"  Active users (30d):      {biz['active_users_30d']}")
    lines.append(f"  Weekly active users:     {biz['wau']}")
    lines.append(f"  Sessions this week:      {biz['sessions_this_week']} "
                 f"(last week: {biz['sessions_last_week']}, "
                 f"delta: {_delta_str(wow['sessions_delta'])})")
    lines.append("")

    # Engagement
    lines.append("ENGAGEMENT")
    lines.append(f"  Sessions/user/week:      {eng['sessions_per_user_week']} (target: 3-5)")
    lines.append(f"  Avg session duration:    {eng['avg_session_duration_min']} min (target: 12-20)")
    lines.append(f"  Drill accuracy:          {eng['drill_accuracy_pct']}% "
                 f"(target: 70-85%) "
                 f"[{_delta_str(wow['accuracy_delta'], 'pp')} WoW]")

    if eng["accuracy_by_modality"]:
        mod_parts = ", ".join(f"{k}: {v}%" for k, v in sorted(eng["accuracy_by_modality"].items()))
        lines.append(f"    By modality:           {mod_parts}")

    lines.append(f"  Drill types used (avg):  {eng['drill_type_diversity']} "
                 f"({', '.join(eng['drill_types_used'])})")
    lines.append(f"  Early exit rate:         {eng['early_exit_rate_pct']}% (target: < 15%)")
    lines.append(f"  Boredom flag rate:       {eng['boredom_flag_rate_pct']}% (target: < 10%)")
    lines.append("")

    # Feature Adoption
    lines.append("FEATURE ADOPTION")
    lines.append(f"  Reading (graded reader): {eng['reading_adoption_pct']}% "
                 f"({eng['reading_sessions']} sessions)")
    lines.append(f"  Listening drills:        {eng['listening_adoption_pct']}% "
                 f"({eng['listening_sessions']} sessions)")
    lines.append(f"  Cleanup loop:            {eng['cleanup_loop_pct']}% "
                 f"({eng['cleanup_loop_drilled']}/{eng['cleanup_loop_looked_up']} words)")
    lines.append("")

    # Learning Outcomes
    lines.append("LEARNING OUTCOMES")
    lines.append(f"  Words at 85%+ mastery:   {learn['words_at_85pct']}")
    lines.append(f"  Avg vocab retention:     {learn['avg_retention_pct']}%")

    if learn.get("hsk_distribution"):
        hsk_parts = ", ".join(f"{k}: {v}" for k, v in learn["hsk_distribution"].items())
        lines.append(f"  HSK distribution:        {hsk_parts}")

    if learn.get("mastery_distribution"):
        mastery_parts = ", ".join(
            f"{k}: {v}" for k, v in learn["mastery_distribution"].items()
        )
        lines.append(f"  Mastery stages:          {mastery_parts}")

    if learn.get("most_failed_items"):
        lines.append("")
        lines.append("  MOST-FAILED ITEMS (last 30 days)")
        lines.append(f"    {'Hanzi':<8} {'Pinyin':<14} {'English':<20} {'HSK':>3} {'Errs':>4} {'Type':<10}")
        lines.append(f"    {'-'*8} {'-'*14} {'-'*20} {'-'*3} {'-'*4} {'-'*10}")
        for item in learn["most_failed_items"][:10]:
            lines.append(
                f"    {item['hanzi']:<8} {(item['pinyin'] or ''):<14} "
                f"{(item['english'] or ''):<20} {item['hsk_level'] or '-':>3} "
                f"{item['error_count']:>4} {(item['error_type'] or ''):<10}"
            )
    lines.append("")

    # Funnel
    lines.append("ACTIVITY PATTERNS")
    lines.append(f"  New content this week:   {funnel['new_content_this_week']}")
    lines.append(f"  Vocab encounters (7d):   {funnel['vocab_encounters_this_week']}")

    if funnel.get("sessions_by_day"):
        day_str = "  ".join(f"{d}: {c}" for d, c in funnel["sessions_by_day"].items())
        lines.append(f"  Sessions by day (30d):   {day_str}")

    if funnel.get("session_outcomes"):
        outcome_str = ", ".join(f"{k}: {v}" for k, v in funnel["session_outcomes"].items())
        lines.append(f"  Session outcomes (30d):  {outcome_str}")
    lines.append("")

    # Completion Rate by Segment
    if comp_seg:
        lines.append("COMPLETION RATE BY SEGMENT")
        lines.append(f"  Overall:                 {comp_seg.get('overall_rate', 0)}% "
                     f"({comp_seg.get('overall_completed', 0)}/{comp_seg.get('overall_total', 0)})")
        if comp_seg.get("by_session_type"):
            for stype, data in comp_seg["by_session_type"].items():
                lines.append(f"    {stype:<22} {data['rate']}% ({data['completed']}/{data['total']})")
        if comp_seg.get("by_hsk_band"):
            lines.append("  Accuracy by HSK band (7d):")
            for band, data in comp_seg["by_hsk_band"].items():
                lines.append(f"    {band:<22} {data['rate']}% ({data['completed']}/{data['total']} items)")
        lines.append("")

    # Crash Rate
    if crashes:
        lines.append("RELIABILITY")
        lines.append(f"  Crashes this week:       {crashes.get('crashes', 0)}")
        lines.append(f"  Sessions this week:      {crashes.get('sessions', 0)}")
        lines.append(f"  Crash rate:              {crashes.get('rate_pct', 0)}%")
        if crashes.get("top_errors"):
            for err in crashes["top_errors"]:
                lines.append(f"    {err['type']}: {err['count']}")
        lines.append("")

    # Retention Cohorts
    if retention and retention.get("signups_30d", 0) > 0:
        lines.append("RETENTION COHORTS")
        lines.append(f"  Signups (60d):           {retention.get('signups_30d', 0)}")
        lines.append(f"  D1 retention:            {retention.get('d1', 0)}% "
                     f"({retention.get('d1_retained', 0)}/{retention.get('d1_eligible', 0)})")
        lines.append(f"  D7 retention:            {retention.get('d7', 0)}% "
                     f"({retention.get('d7_retained', 0)}/{retention.get('d7_eligible', 0)})")
        lines.append(f"  D30 retention:           {retention.get('d30', 0)}% "
                     f"({retention.get('d30_retained', 0)}/{retention.get('d30_eligible', 0)})")
        lines.append("")

    # Growth Accounting
    if growth and (growth.get("new", 0) + growth.get("retained", 0) +
                   growth.get("resurrected", 0) + growth.get("churned", 0)) > 0:
        lines.append("GROWTH ACCOUNTING")
        lines.append(f"  New users:               {growth.get('new', 0)}")
        lines.append(f"  Retained:                {growth.get('retained', 0)}")
        lines.append(f"  Resurrected:             {growth.get('resurrected', 0)}")
        lines.append(f"  Churned:                 {growth.get('churned', 0)}")
        lines.append(f"  Net retention:           {growth.get('net_retention', 0)}%")
        lines.append("")

    # Week-over-week
    lines.append("WEEK-OVER-WEEK COMPARISON")
    lines.append(f"  Sessions:     {biz['sessions_this_week']} vs {biz['sessions_last_week']} "
                 f"({_delta_str(wow['sessions_delta'])})")
    lines.append(f"  Accuracy:     {wow['accuracy_this_week']}% vs {wow['accuracy_last_week']}% "
                 f"({_delta_str(wow['accuracy_delta'], 'pp')})")
    lines.append(f"  Avg duration: {wow['avg_dur_this_week']} min vs "
                 f"{wow['avg_dur_last_week']} min")
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def _generate_report_md(
    biz: dict,
    eng: dict,
    learn: dict,
    funnel: dict,
    wow: dict,
    report_date: str,
    extra: dict | None = None,
) -> str:
    """Generate the weekly report as Markdown."""
    extra = extra or {}
    ns = extra.get("north_star", {})
    comp_seg = extra.get("completion_by_segment", {})
    retention = extra.get("retention", {})
    growth = extra.get("growth", {})
    crashes = extra.get("crashes", {})

    lines = []
    lines.append(f"# Weekly Report: Week of {report_date}")
    lines.append("")

    # North Star
    lines.append("## North Star")
    mastered = ns.get("items_mastered_this_week", 0)
    per_user = ns.get("mastered_per_active_user", 0.0)
    lines.append(f"- **Items mastered/active user:** {per_user} ({mastered} items this week)")
    lines.append(f"- **WASU:** {biz['wau']} (sessions this week: {biz['sessions_this_week']})")
    lines.append("")

    # Business Health
    lines.append("## Business Health")
    lines.append(f"| Metric | Value | Last Week | Delta |")
    lines.append(f"|--------|-------|-----------|-------|")
    lines.append(f"| Active users (30d) | {biz['active_users_30d']} | - | - |")
    lines.append(f"| Weekly active users | {biz['wau']} | - | - |")
    lines.append(f"| Sessions | {biz['sessions_this_week']} | "
                 f"{biz['sessions_last_week']} | {_delta_str(wow['sessions_delta'])} |")
    lines.append("")

    # Engagement
    lines.append("## Engagement")
    lines.append(f"| Metric | Value | Target | Status |")
    lines.append(f"|--------|-------|--------|--------|")
    spuw = eng['sessions_per_user_week']
    lines.append(f"| Sessions/user/week | {spuw} | 3-5 | "
                 f"{'OK' if 3 <= spuw <= 5 else 'Below' if spuw < 3 else 'High'} |")
    dur = eng['avg_session_duration_min']
    lines.append(f"| Avg session duration | {dur} min | 12-20 min | "
                 f"{'OK' if 12 <= dur <= 20 else 'Short' if dur < 12 else 'Long'} |")
    acc = eng['drill_accuracy_pct']
    lines.append(f"| Drill accuracy | {acc}% | 70-85% | "
                 f"{'OK' if 70 <= acc <= 85 else 'Low' if acc < 70 else 'High (too easy?)'} |")
    div = eng['drill_type_diversity']
    lines.append(f"| Drill type diversity | {div} types | 5+ | "
                 f"{'OK' if div >= 5 else 'Low'} |")
    lines.append(f"| Early exit rate | {eng['early_exit_rate_pct']}% | < 15% | "
                 f"{'OK' if eng['early_exit_rate_pct'] < 15 else 'High'} |")
    lines.append(f"| Boredom flag rate | {eng['boredom_flag_rate_pct']}% | < 10% | "
                 f"{'OK' if eng['boredom_flag_rate_pct'] < 10 else 'High'} |")
    lines.append("")

    # Accuracy by modality
    if eng["accuracy_by_modality"]:
        lines.append("### Accuracy by Modality")
        lines.append("| Modality | Accuracy |")
        lines.append("|----------|----------|")
        for k, v in sorted(eng["accuracy_by_modality"].items()):
            lines.append(f"| {k} | {v}% |")
        lines.append("")

    # Feature Adoption
    lines.append("## Feature Adoption")
    lines.append(f"| Feature | Usage | Sessions |")
    lines.append(f"|---------|-------|----------|")
    lines.append(f"| Reading (graded reader) | {eng['reading_adoption_pct']}% | "
                 f"{eng['reading_sessions']} |")
    lines.append(f"| Listening drills | {eng['listening_adoption_pct']}% | "
                 f"{eng['listening_sessions']} |")
    lines.append(f"| Cleanup loop | {eng['cleanup_loop_pct']}% | "
                 f"{eng['cleanup_loop_drilled']}/{eng['cleanup_loop_looked_up']} words |")
    lines.append("")

    # Learning Outcomes
    lines.append("## Learning Outcomes")
    lines.append(f"- **Words at 85%+ mastery:** {learn['words_at_85pct']}")
    lines.append(f"- **Avg vocab retention (30d):** {learn['avg_retention_pct']}%")
    lines.append("")

    if learn.get("hsk_distribution"):
        lines.append("### HSK Distribution (actively studied)")
        lines.append("| Level | Items |")
        lines.append("|-------|-------|")
        for k, v in learn["hsk_distribution"].items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    if learn.get("mastery_distribution"):
        lines.append("### Mastery Stages")
        lines.append("| Stage | Count |")
        lines.append("|-------|-------|")
        for k, v in learn["mastery_distribution"].items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    if learn.get("most_failed_items"):
        lines.append("### Most-Failed Items (last 30 days)")
        lines.append("| Hanzi | Pinyin | English | HSK | Errors | Error Type |")
        lines.append("|-------|--------|---------|-----|--------|------------|")
        for item in learn["most_failed_items"][:10]:
            lines.append(
                f"| {item['hanzi']} | {item['pinyin'] or '-'} | "
                f"{item['english'] or '-'} | {item['hsk_level'] or '-'} | "
                f"{item['error_count']} | {item['error_type'] or '-'} |"
            )
        lines.append("")

    # Activity Patterns
    lines.append("## Activity Patterns")
    lines.append(f"- **New content this week:** {funnel['new_content_this_week']}")
    lines.append(f"- **Vocab encounters (7d):** {funnel['vocab_encounters_this_week']}")
    lines.append("")

    if funnel.get("sessions_by_day"):
        lines.append("### Sessions by Day of Week (last 30 days)")
        lines.append("| Day | Sessions |")
        lines.append("|-----|----------|")
        for d, c in funnel["sessions_by_day"].items():
            lines.append(f"| {d} | {c} |")
        lines.append("")

    # Completion Rate by Segment
    if comp_seg:
        lines.append("## Completion Rate by Segment")
        lines.append(f"**Overall:** {comp_seg.get('overall_rate', 0)}% "
                     f"({comp_seg.get('overall_completed', 0)}/{comp_seg.get('overall_total', 0)} sessions)")
        lines.append("")
        if comp_seg.get("by_session_type"):
            lines.append("| Session Type | Total | Completed | Rate |")
            lines.append("|-------------|-------|-----------|------|")
            for stype, data in comp_seg["by_session_type"].items():
                lines.append(f"| {stype} | {data['total']} | {data['completed']} | {data['rate']}% |")
            lines.append("")
        if comp_seg.get("by_hsk_band"):
            lines.append("### Accuracy by HSK Band (7d)")
            lines.append("| HSK Band | Attempts | Correct | Accuracy |")
            lines.append("|----------|----------|---------|----------|")
            for band, data in comp_seg["by_hsk_band"].items():
                lines.append(f"| {band} | {data['total']} | {data['completed']} | {data['rate']}% |")
            lines.append("")

    # Reliability
    if crashes:
        lines.append("## Reliability")
        lines.append(f"- **Crashes (7d):** {crashes.get('crashes', 0)}")
        lines.append(f"- **Sessions (7d):** {crashes.get('sessions', 0)}")
        lines.append(f"- **Crash rate:** {crashes.get('rate_pct', 0)}%")
        if crashes.get("top_errors"):
            lines.append("")
            lines.append("| Error Type | Count |")
            lines.append("|-----------|-------|")
            for err in crashes["top_errors"]:
                lines.append(f"| {err['type']} | {err['count']} |")
        lines.append("")

    # Retention Cohorts
    if retention and retention.get("signups_30d", 0) > 0:
        lines.append("## Retention Cohorts")
        lines.append(f"Signups in last 60 days: {retention.get('signups_30d', 0)}")
        lines.append("")
        lines.append("| Cohort | Eligible | Retained | Rate |")
        lines.append("|--------|----------|----------|------|")
        lines.append(f"| D1 (session within 48h) | {retention.get('d1_eligible', 0)} | "
                     f"{retention.get('d1_retained', 0)} | {retention.get('d1', 0)}% |")
        lines.append(f"| D7 (session days 6-8) | {retention.get('d7_eligible', 0)} | "
                     f"{retention.get('d7_retained', 0)} | {retention.get('d7', 0)}% |")
        lines.append(f"| D30 (session days 28-32) | {retention.get('d30_eligible', 0)} | "
                     f"{retention.get('d30_retained', 0)} | {retention.get('d30', 0)}% |")
        lines.append("")

    # Growth Accounting
    if growth and (growth.get("new", 0) + growth.get("retained", 0) +
                   growth.get("resurrected", 0) + growth.get("churned", 0)) > 0:
        lines.append("## Growth Accounting")
        lines.append("| Category | Users |")
        lines.append("|----------|-------|")
        lines.append(f"| New (first session ever) | {growth.get('new', 0)} |")
        lines.append(f"| Retained (active both weeks) | {growth.get('retained', 0)} |")
        lines.append(f"| Resurrected (returned after gap) | {growth.get('resurrected', 0)} |")
        lines.append(f"| Churned (active last week, not this) | {growth.get('churned', 0)} |")
        lines.append(f"")
        lines.append(f"**Net retention:** {growth.get('net_retention', 0)}%")
        lines.append("")

    # WoW
    lines.append("## Week-over-Week")
    lines.append("| Metric | This Week | Last Week | Delta |")
    lines.append("|--------|-----------|-----------|-------|")
    lines.append(f"| Sessions | {biz['sessions_this_week']} | "
                 f"{biz['sessions_last_week']} | {_delta_str(wow['sessions_delta'])} |")
    lines.append(f"| Accuracy | {wow['accuracy_this_week']}% | "
                 f"{wow['accuracy_last_week']}% | {_delta_str(wow['accuracy_delta'], 'pp')} |")
    lines.append(f"| Avg duration | {wow['avg_dur_this_week']} min | "
                 f"{wow['avg_dur_last_week']} min | - |")
    lines.append("")

    return "\n".join(lines)


def _print_report_rich(
    biz: dict,
    eng: dict,
    learn: dict,
    funnel: dict,
    wow: dict,
    report_date: str,
    extra: dict | None = None,
) -> None:
    """Print the report using Rich tables."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    extra = extra or {}
    ns = extra.get("north_star", {})
    comp_seg = extra.get("completion_by_segment", {})
    retention = extra.get("retention", {})
    growth = extra.get("growth", {})
    crashes = extra.get("crashes", {})

    console = Console()
    console.print()

    # Header — North Star: Items Mastered per Active User
    mastered = ns.get("items_mastered_this_week", 0)
    per_user = ns.get("mastered_per_active_user", 0.0)
    console.print(Panel(
        f"[bold]Items mastered/user (North Star):[/bold] {per_user}  "
        f"[dim]({mastered} items this week)[/dim]\n"
        f"[bold]WASU:[/bold] {biz['wau']}    "
        f"[dim]Sessions: {biz['sessions_this_week']} "
        f"({_delta_str(wow['sessions_delta'])} WoW)[/dim]",
        title=f"Weekly Metrics Report -- {report_date}",
        border_style="dim",
        width=76,
    ))

    # Business Health
    t = Table(title="Business Health", box=box.SIMPLE, width=76)
    t.add_column("Metric", style="bold", min_width=24)
    t.add_column("Value", min_width=10)
    t.add_column("Prev Week", min_width=10)
    t.add_column("Delta", min_width=10)
    t.add_row("Active users (30d)", str(biz["active_users_30d"]), "-", "-")
    t.add_row("Weekly active users", str(biz["wau"]), "-", "-")
    t.add_row("Sessions", str(biz["sessions_this_week"]),
              str(biz["sessions_last_week"]), _delta_str(wow["sessions_delta"]))
    console.print(t)

    # Engagement
    t = Table(title="Engagement", box=box.SIMPLE, width=76)
    t.add_column("Metric", style="bold", min_width=26)
    t.add_column("Value", min_width=12)
    t.add_column("Target", min_width=10)
    t.add_column("Status", min_width=10)
    spuw = eng["sessions_per_user_week"]
    t.add_row("Sessions/user/week", str(spuw), "3-5",
              "[green]OK[/green]" if 3 <= spuw <= 5 else "[yellow]Below[/yellow]")
    dur = eng["avg_session_duration_min"]
    t.add_row("Avg session duration", f"{dur} min", "12-20 min",
              "[green]OK[/green]" if 12 <= dur <= 20 else "[yellow]Short[/yellow]" if dur < 12 else "[yellow]Long[/yellow]")
    acc = eng["drill_accuracy_pct"]
    t.add_row("Drill accuracy", f"{acc}%", "70-85%",
              "[green]OK[/green]" if 70 <= acc <= 85 else "[yellow]Low[/yellow]" if acc < 70 else "[yellow]High[/yellow]")
    t.add_row("Drill type diversity", f"{eng['drill_type_diversity']} types", "5+",
              "[green]OK[/green]" if eng["drill_type_diversity"] >= 5 else "[yellow]Low[/yellow]")
    t.add_row("Early exit rate", f"{eng['early_exit_rate_pct']}%", "< 15%",
              "[green]OK[/green]" if eng["early_exit_rate_pct"] < 15 else "[red]High[/red]")
    t.add_row("Boredom flag rate", f"{eng['boredom_flag_rate_pct']}%", "< 10%",
              "[green]OK[/green]" if eng["boredom_flag_rate_pct"] < 10 else "[red]High[/red]")
    console.print(t)

    # Feature Adoption
    t = Table(title="Feature Adoption", box=box.SIMPLE, width=76)
    t.add_column("Feature", style="bold", min_width=24)
    t.add_column("Adoption", min_width=10)
    t.add_column("Sessions", min_width=10)
    t.add_row("Reading (graded reader)", f"{eng['reading_adoption_pct']}%",
              str(eng["reading_sessions"]))
    t.add_row("Listening drills", f"{eng['listening_adoption_pct']}%",
              str(eng["listening_sessions"]))
    t.add_row("Cleanup loop", f"{eng['cleanup_loop_pct']}%",
              f"{eng['cleanup_loop_drilled']}/{eng['cleanup_loop_looked_up']} words")
    console.print(t)

    # Learning Outcomes
    t = Table(title="Learning Outcomes", box=box.SIMPLE, width=76)
    t.add_column("Metric", style="bold", min_width=26)
    t.add_column("Value", min_width=14)
    t.add_row("Words at 85%+ mastery", str(learn["words_at_85pct"]))
    t.add_row("Avg vocab retention (30d)", f"{learn['avg_retention_pct']}%")
    console.print(t)

    if learn.get("hsk_distribution"):
        t = Table(title="HSK Distribution (actively studied)", box=box.SIMPLE, width=50)
        t.add_column("Level", style="bold")
        t.add_column("Items", justify="right")
        for k, v in learn["hsk_distribution"].items():
            t.add_row(k, str(v))
        console.print(t)

    if learn.get("mastery_distribution"):
        t = Table(title="Mastery Stage Distribution", box=box.SIMPLE, width=50)
        t.add_column("Stage", style="bold")
        t.add_column("Count", justify="right")
        for k, v in learn["mastery_distribution"].items():
            t.add_row(k, str(v))
        console.print(t)

    # Most-failed items
    if learn.get("most_failed_items"):
        t = Table(title="Most-Failed Items (last 30 days)", box=box.SIMPLE, width=76)
        t.add_column("Hanzi", style="bold bright_cyan")
        t.add_column("Pinyin")
        t.add_column("English")
        t.add_column("HSK", justify="right")
        t.add_column("Errs", justify="right")
        t.add_column("Type")
        for item in learn["most_failed_items"][:10]:
            t.add_row(
                item["hanzi"],
                item["pinyin"] or "-",
                item["english"] or "-",
                str(item["hsk_level"] or "-"),
                str(item["error_count"]),
                item["error_type"] or "-",
            )
        console.print(t)

    # Activity Patterns
    if funnel.get("sessions_by_day"):
        t = Table(title="Sessions by Day (last 30 days)", box=box.SIMPLE, width=50)
        t.add_column("Day", style="bold")
        t.add_column("Sessions", justify="right")
        for d, c in funnel["sessions_by_day"].items():
            t.add_row(d, str(c))
        console.print(t)

    console.print(f"  [dim]New content this week: {funnel['new_content_this_week']}  |  "
                  f"Vocab encounters: {funnel['vocab_encounters_this_week']}[/dim]")
    console.print()

    # Completion Rate by Segment
    if comp_seg and comp_seg.get("by_session_type"):
        t = Table(title=f"Completion Rate by Segment (overall: {comp_seg.get('overall_rate', 0)}%)",
                  box=box.SIMPLE, width=76)
        t.add_column("Segment", style="bold", min_width=24)
        t.add_column("Total", justify="right")
        t.add_column("Completed", justify="right")
        t.add_column("Rate", justify="right")
        for stype, data in comp_seg["by_session_type"].items():
            rate = data["rate"]
            color = "[green]" if rate >= 75 else "[yellow]" if rate >= 60 else "[red]"
            t.add_row(stype, str(data["total"]), str(data["completed"]),
                      f"{color}{rate}%[/{color[1:]}")
        if comp_seg.get("by_hsk_band"):
            for band, data in comp_seg["by_hsk_band"].items():
                rate = data["rate"]
                color = "[green]" if rate >= 75 else "[yellow]" if rate >= 60 else "[red]"
                t.add_row(band, str(data["total"]), str(data["completed"]),
                          f"{color}{rate}%[/{color[1:]}")
        console.print(t)

    # Reliability
    if crashes:
        crash_count = crashes.get("crashes", 0)
        crash_rate = crashes.get("rate_pct", 0)
        color = "[green]" if crash_rate < 0.1 else "[yellow]" if crash_rate < 1 else "[red]"
        console.print(f"  Crashes (7d): {color}{crash_count}[/{color[1:]}  "
                      f"Rate: {color}{crash_rate}%[/{color[1:]}  "
                      f"[dim](of {crashes.get('sessions', 0)} sessions)[/dim]")
        if crashes.get("top_errors"):
            for err in crashes["top_errors"]:
                console.print(f"    [dim]{err['type']}: {err['count']}[/dim]")
        console.print()

    # Retention Cohorts
    if retention and retention.get("signups_30d", 0) > 0:
        t = Table(title="Retention Cohorts", box=box.SIMPLE, width=76)
        t.add_column("Cohort", style="bold", min_width=24)
        t.add_column("Eligible", justify="right")
        t.add_column("Retained", justify="right")
        t.add_column("Rate", justify="right")
        for label, key in [("D1 (within 48h)", "d1"), ("D7 (days 6-8)", "d7"),
                           ("D30 (days 28-32)", "d30")]:
            rate = retention.get(key, 0)
            color = "[green]" if rate >= 50 else "[yellow]" if rate >= 25 else "[red]"
            t.add_row(label,
                      str(retention.get(f"{key}_eligible", 0)),
                      str(retention.get(f"{key}_retained", 0)),
                      f"{color}{rate}%[/{color[1:]}")
        console.print(t)

    # Growth Accounting
    if growth and (growth.get("new", 0) + growth.get("retained", 0) +
                   growth.get("resurrected", 0) + growth.get("churned", 0)) > 0:
        t = Table(title="Growth Accounting", box=box.SIMPLE, width=76)
        t.add_column("Category", style="bold", min_width=30)
        t.add_column("Users", justify="right")
        t.add_row("New (first session ever)", str(growth.get("new", 0)))
        t.add_row("Retained (active both weeks)", f"[green]{growth.get('retained', 0)}[/green]")
        t.add_row("Resurrected (returned after gap)", str(growth.get("resurrected", 0)))
        t.add_row("Churned (active last week only)", f"[red]{growth.get('churned', 0)}[/red]")
        t.add_row("", "")
        nr = growth.get("net_retention", 0)
        color = "[green]" if nr >= 100 else "[yellow]" if nr >= 80 else "[red]"
        t.add_row("[bold]Net retention[/bold]", f"{color}{nr}%[/{color[1:]}")
        console.print(t)

    console.print()


# ---------------------------------------------------------------------------
# Report runner
# ---------------------------------------------------------------------------

def generate_report(db_path: str = None, output_format: str = "rich",
                    save: bool = True, user_id: int = 1) -> dict:
    """Generate the weekly metrics report.

    Args:
        db_path: Path to the SQLite database.
        output_format: 'rich', 'plain', or 'quiet' (no console output).
        save: Whether to save .txt and .md files to reports/ directory.
        user_id: User ID to generate report for.

    Returns:
        Dict with all metric sections.
    """
    path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    if not path.exists():
        logger.warning("Database not found at: %s", path)
        logger.warning("Run a session first to create the database.")
        return {}

    conn = _get_connection(path)
    try:
        biz = _business_health(conn, user_id=user_id)
        eng = _engagement(conn, user_id=user_id)
        learn = _learning_outcomes(conn, user_id=user_id)
        funnel = _funnel_metrics(conn, user_id=user_id)
        wow = _week_comparison(conn, user_id=user_id)
        ns = _north_star(conn, user_id=user_id)
        comp_seg = _completion_by_segment(conn, user_id=user_id)
        retention = _retention_cohorts(conn)
        growth = _growth_accounting(conn)
        crashes = _crash_rate(conn)
        false_mastery = _false_mastery_rate(conn, user_id=user_id)
    finally:
        conn.close()

    report_date = date.today().isoformat()

    # Console output
    extra = {"north_star": ns, "completion_by_segment": comp_seg,
             "retention": retention, "growth": growth, "crashes": crashes,
             "false_mastery": false_mastery}
    if output_format == "rich":
        try:
            _print_report_rich(biz, eng, learn, funnel, wow, report_date, extra=extra)
        except ImportError:
            print(_generate_report_text(biz, eng, learn, funnel, wow, report_date, extra=extra))
    elif output_format == "plain":
        print(_generate_report_text(biz, eng, learn, funnel, wow, report_date, extra=extra))

    # Save to files
    if save:
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        filename_base = f"weekly-report-{report_date}"

        txt_path = _REPORTS_DIR / f"{filename_base}.txt"
        txt_content = _generate_report_text(biz, eng, learn, funnel, wow, report_date, extra=extra)
        txt_path.write_text(txt_content, encoding="utf-8")

        md_path = _REPORTS_DIR / f"{filename_base}.md"
        md_content = _generate_report_md(biz, eng, learn, funnel, wow, report_date, extra=extra)
        md_path.write_text(md_content, encoding="utf-8")

        if output_format != "quiet":
            print(f"  Reports saved to:")
            print(f"    {txt_path}")
            print(f"    {md_path}")
            print()

    return {
        "business_health": biz,
        "engagement": eng,
        "learning_outcomes": learn,
        "funnel": funnel,
        "week_comparison": wow,
        "north_star": ns,
        "completion_by_segment": comp_seg,
        "retention": retention,
        "growth": growth,
        "crashes": crashes,
        "false_mastery": false_mastery,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Weekly Metrics Report — Aelu",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite database (default: data/mandarin.db)",
    )
    parser.add_argument(
        "--output-format",
        choices=["rich", "plain", "quiet"],
        default="rich",
        help="Output format: rich (default), plain text, or quiet (save only).",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save report files to reports/ directory.",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=1,
        help="Number of weeks of history to include (currently generates latest week).",
    )

    args = parser.parse_args()

    generate_report(
        db_path=args.db_path,
        output_format=args.output_format,
        save=not args.no_save,
    )


if __name__ == "__main__":
    main()
