"""Tests for Doc 7: Engagement, Multi-User, Teacher Dashboard Intelligence."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone, UTC

import pytest

from mandarin.intelligence.analysis_scope import AnalysisScope
from mandarin.intelligence.engagement import (
    ANALYZERS as ENGAGEMENT_ANALYZERS,
    _extract_session_features,
    compute_abandonment_risk,
    generate_engagement_snapshot,
    score_intervention_effectiveness,
    _analyze_engagement_risk,
    _analyze_intervention_effectiveness,
)
from mandarin.intelligence.cohort_analysis import (
    ANALYZERS as COHORT_ANALYZERS,
    generate_cohort_snapshot,
    _analyze_cohort_health,
)
from tests.shared_db import make_test_db


@pytest.fixture
def conn():
    """In-memory SQLite with the full production schema."""
    c = make_test_db()
    c.execute("PRAGMA foreign_keys=OFF")
    return c


# ── Test 1: _extract_session_features returns zeros on empty DB ─────────


def test_extract_session_features_empty(conn):
    result = _extract_session_features(conn, user_id=1, days=7)
    assert result["sessions"] == 0
    # _safe_scalar defaults to 0 for NULL aggregates
    assert result["avg_accuracy"] == 0
    assert result["avg_duration"] == 0
    assert result["early_exits"] == 0
    assert result["boredom_flags"] == 0


# ── Test 2: _extract_session_features returns correct counts ────────────


def test_extract_session_features_with_data(conn):
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                  duration_seconds, early_exit, boredom_flags)
        VALUES (1, ?, 10, 8, 300, 0, 1)
    """, (now,))
    conn.execute("""
        INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                  duration_seconds, early_exit, boredom_flags)
        VALUES (1, ?, 10, 6, 240, 1, 0)
    """, (now,))
    conn.commit()

    result = _extract_session_features(conn, user_id=1, days=7)
    assert result["sessions"] == 2
    assert result["avg_accuracy"] is not None
    assert 0.6 <= result["avg_accuracy"] <= 0.8
    assert result["early_exits"] == 1
    assert result["boredom_flags"] == 1


# ── Test 3: compute_abandonment_risk returns high risk with no sessions ──


def test_abandonment_risk_no_sessions(conn):
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (1, 'a@a.com', 'h')")
    conn.commit()
    result = compute_abandonment_risk(conn, user_id=1)
    # No sessions → recency factor fires (0.30) → medium risk
    assert result["risk"] >= 0.25
    assert result["level"] in ("medium", "high", "critical")
    assert "no_completed_sessions" in result["factors"]


# ── Test 4: compute_abandonment_risk returns low risk for active user ────


def test_abandonment_risk_active_user(conn):
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (1, 'a@a.com', 'h')")
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    for ts in [now, yesterday]:
        conn.execute("""
            INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                      duration_seconds, early_exit, boredom_flags)
            VALUES (1, ?, 10, 8, 300, 0, 0)
        """, (ts,))
    # Also add some in prior week
    prior = (datetime.now(UTC) - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                  duration_seconds, early_exit, boredom_flags)
        VALUES (1, ?, 10, 8, 300, 0, 0)
    """, (prior,))
    conn.commit()

    result = compute_abandonment_risk(conn, user_id=1)
    assert result["risk"] < 0.25
    assert result["level"] == "low"


# ── Test 5: compute_abandonment_risk detects frequency decline ───────────


def test_abandonment_risk_frequency_decline(conn):
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (1, 'a@a.com', 'h')")
    # 3 sessions in prior week, 0 in current week
    for i in range(3):
        ts = (datetime.now(UTC) - timedelta(days=8 + i)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                      duration_seconds, early_exit, boredom_flags)
            VALUES (1, ?, 10, 8, 300, 0, 0)
        """, (ts,))
    conn.commit()

    result = compute_abandonment_risk(conn, user_id=1)
    assert "session_frequency_dropped_to_zero" in result["factors"]


# ── Test 6: frustration proxy raises risk ────────────────────────────────


def test_abandonment_risk_frustration(conn):
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (1, 'a@a.com', 'h')")
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                  duration_seconds, early_exit, boredom_flags)
        VALUES (1, ?, 10, 3, 300, 3, 2)
    """, (now,))
    conn.commit()

    result = compute_abandonment_risk(conn, user_id=1)
    assert "frustration_signals" in result["factors"]


# ── Test 7: generate_engagement_snapshot is idempotent ───────────────────


def test_engagement_snapshot_idempotent(conn):
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (1, 'a@a.com', 'h')")
    conn.commit()

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    r1 = generate_engagement_snapshot(conn, user_id=1, snapshot_date=today)
    r2 = generate_engagement_snapshot(conn, user_id=1, snapshot_date=today)

    count = conn.execute(
        "SELECT COUNT(*) FROM pi_engagement_snapshots WHERE user_id = 1 AND snapshot_date = ?",
        (today,),
    ).fetchone()[0]
    assert count == 1
    assert r1["risk"] == r2["risk"]


# ── Test 8: generate_cohort_snapshot correct counts ──────────────────────


def test_cohort_snapshot_counts(conn):
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (10, 'teacher@a.com', 'h')")
    conn.execute("INSERT INTO classroom (id, teacher_user_id, name, invite_code) VALUES (1, 10, 'HSK1', 'abc')")
    for uid in [1, 2, 3]:
        conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (?, ?, 'h')", (uid, f"s{uid}@a.com"))
        conn.execute("INSERT INTO classroom_student (classroom_id, user_id) VALUES (1, ?)", (uid,))
    conn.commit()

    result = generate_cohort_snapshot(conn, classroom_id=1)
    assert result["total_students"] == 3
    assert result["at_risk_count"] + result["high_risk_count"] >= 0  # just no crash


# ── Test 9: cohort snapshot detects declining trend ──────────────────────


def test_cohort_snapshot_declining_trend(conn):
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (10, 'teacher@a.com', 'h')")
    conn.execute("INSERT INTO classroom (id, teacher_user_id, name, invite_code) VALUES (1, 10, 'HSK1', 'abc')")
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (1, 's1@a.com', 'h')")
    conn.execute("INSERT INTO classroom_student (classroom_id, user_id) VALUES (1, 1)")

    # Insert a prior snapshot with low risk
    conn.execute("""
        INSERT INTO pi_cohort_snapshots
            (classroom_id, snapshot_date, avg_abandonment_risk, engagement_trend)
        VALUES (1, date('now', '-5 days'), 0.05, 'stable')
    """)
    conn.commit()

    # Student has no sessions → high risk → trend should be declining
    result = generate_cohort_snapshot(conn, classroom_id=1)
    assert result["engagement_trend"] == "declining"


# ── Test 10: _analyze_engagement_risk returns empty on no snapshots ──────


def test_analyze_engagement_risk_empty(conn):
    findings = _analyze_engagement_risk(conn)
    assert findings == []


# ── Test 11: _analyze_engagement_risk emits finding when >20% at risk ────


def test_analyze_engagement_risk_high(conn):
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    # 5 users, 2 at high risk = 40%
    for uid in range(1, 6):
        level = "high" if uid <= 2 else "low"
        risk = 0.6 if uid <= 2 else 0.1
        conn.execute("""
            INSERT INTO pi_engagement_snapshots
                (user_id, snapshot_date, abandonment_risk, risk_level)
            VALUES (?, ?, ?, ?)
        """, (uid, today, risk, level))
    conn.commit()

    findings = _analyze_engagement_risk(conn)
    assert len(findings) >= 1
    assert "at high/critical" in findings[0]["title"]


# ── Test 12: AnalysisScope.solo() single-user filter ────────────────────


def test_analysis_scope_solo():
    scope = AnalysisScope.solo(42)
    assert scope.is_solo
    assert not scope.is_cohort
    sql, params = scope.user_filter_sql()
    assert "user_id = ?" in sql
    assert params == [42]


# ── Test 13: AnalysisScope.cohort() IN-clause filter ────────────────────


def test_analysis_scope_cohort():
    scope = AnalysisScope.cohort(1, [10, 20, 30])
    assert scope.is_cohort
    assert not scope.is_solo
    sql, params = scope.user_filter_sql("s")
    assert "s.user_id IN" in sql
    assert params == [10, 20, 30]


# ── Test 14: intervention logging + scoring ──────────────────────────────


def test_intervention_logging_and_scoring(conn):
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (1, 's@a.com', 'h')")
    conn.execute("INSERT OR REPLACE INTO user (id, email, password_hash) VALUES (10, 't@a.com', 'h')")

    # Log intervention with high risk
    conn.execute("""
        INSERT INTO pi_teacher_interventions
            (teacher_user_id, student_user_id, intervention_type, risk_at_intervention, created_at)
        VALUES (10, 1, 'email', 0.7, datetime('now', '-10 days'))
    """)
    conn.commit()

    # Student now has sessions → lower risk
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    for ts in [now, yesterday]:
        conn.execute("""
            INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                      duration_seconds, early_exit, boredom_flags)
            VALUES (1, ?, 10, 9, 300, 0, 0)
        """, (ts,))
    # Prior week sessions too (prevent frequency decline flag)
    prior = (datetime.now(UTC) - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                  duration_seconds, early_exit, boredom_flags)
        VALUES (1, ?, 10, 9, 300, 0, 0)
    """, (prior,))
    conn.commit()

    scored = score_intervention_effectiveness(conn)
    assert scored == 1

    row = conn.execute(
        "SELECT effective, risk_after_7d FROM pi_teacher_interventions WHERE id = 1"
    ).fetchone()
    assert row["risk_after_7d"] is not None
    # effective should be 1 since risk dropped from 0.7
    assert row["effective"] == 1


# ── Test 15: migration v67→v68 creates all 4 tables ─────────────────────


def test_migration_v67_to_v68():
    """Verify migration creates the 4 new tables."""
    from mandarin.db.core import _migrate_v67_to_v68, _table_set

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row

    _migrate_v67_to_v68(c)

    tables = _table_set(c)
    assert "pi_engagement_snapshots" in tables
    assert "pi_engagement_events" in tables
    assert "pi_cohort_snapshots" in tables
    assert "pi_teacher_interventions" in tables

    # Verify idempotent
    _migrate_v67_to_v68(c)

    c.close()
