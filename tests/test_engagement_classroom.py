"""Tests for Doc 7: Engagement, Multi-User, Teacher Dashboard Intelligence."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

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


def _create_schema(c):
    """Create minimal schema for engagement tests."""
    c.executescript("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY,
            email TEXT, display_name TEXT, role TEXT DEFAULT 'student',
            is_admin INTEGER DEFAULT 0
        );

        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY,
            hanzi TEXT, pinyin TEXT, english TEXT,
            hsk_level INTEGER DEFAULT 1,
            status TEXT DEFAULT 'drill_ready'
        );

        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at TEXT,
            duration_seconds INTEGER,
            session_type TEXT DEFAULT 'standard',
            items_planned INTEGER DEFAULT 0,
            items_completed INTEGER DEFAULT 0,
            items_correct INTEGER DEFAULT 0,
            early_exit INTEGER DEFAULT 0,
            boredom_flags INTEGER DEFAULT 0,
            days_since_last_session INTEGER,
            session_started_hour INTEGER,
            session_day_of_week INTEGER,
            session_outcome TEXT DEFAULT 'started',
            client_platform TEXT DEFAULT 'web',
            experiment_variant TEXT,
            modality_counts TEXT DEFAULT '{}',
            mapping_groups_used TEXT,
            plan_snapshot TEXT,
            last_activity_at TEXT
        );
        CREATE INDEX idx_session_log_user ON session_log(user_id, started_at);

        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            session_id INTEGER,
            content_item_id INTEGER NOT NULL,
            modality TEXT NOT NULL,
            drill_type TEXT,
            correct INTEGER NOT NULL,
            confidence TEXT DEFAULT 'full',
            response_ms INTEGER,
            error_type TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE vocab_encounter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            content_item_id INTEGER,
            hanzi TEXT,
            source_type TEXT,
            source_id INTEGER,
            looked_up INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE classroom (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            invite_code TEXT UNIQUE NOT NULL,
            max_students INTEGER DEFAULT 30,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE classroom_student (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL DEFAULT (datetime('now')),
            status TEXT DEFAULT 'active',
            UNIQUE(classroom_id, user_id)
        );

        CREATE TABLE pi_engagement_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,
            sessions_7d INTEGER DEFAULT 0,
            sessions_14d INTEGER DEFAULT 0,
            avg_accuracy_7d REAL,
            avg_duration_7d REAL,
            early_exits_7d INTEGER DEFAULT 0,
            boredom_flags_7d INTEGER DEFAULT 0,
            avg_response_ms_7d REAL,
            items_reviewed_7d INTEGER DEFAULT 0,
            encounters_7d INTEGER DEFAULT 0,
            abandonment_risk REAL DEFAULT 0.0,
            risk_level TEXT DEFAULT 'low',
            risk_factors TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, snapshot_date)
        );

        CREATE TABLE pi_engagement_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE pi_cohort_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,
            total_students INTEGER DEFAULT 0,
            active_students_7d INTEGER DEFAULT 0,
            avg_accuracy REAL,
            avg_sessions_per_student REAL,
            at_risk_count INTEGER DEFAULT 0,
            high_risk_count INTEGER DEFAULT 0,
            avg_abandonment_risk REAL,
            engagement_trend TEXT DEFAULT 'stable',
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(classroom_id, snapshot_date)
        );

        CREATE TABLE pi_teacher_interventions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_user_id INTEGER NOT NULL,
            student_user_id INTEGER NOT NULL,
            classroom_id INTEGER,
            intervention_type TEXT NOT NULL,
            notes TEXT,
            risk_at_intervention REAL,
            risk_after_7d REAL,
            effective INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)


@pytest.fixture
def conn():
    """In-memory SQLite with engagement/classroom tables."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=OFF")
    _create_schema(c)
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
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
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
    conn.execute("INSERT INTO user (id, email) VALUES (1, 'a@a.com')")
    conn.commit()
    result = compute_abandonment_risk(conn, user_id=1)
    # No sessions → recency factor fires (0.30) → medium risk
    assert result["risk"] >= 0.25
    assert result["level"] in ("medium", "high", "critical")
    assert "no_completed_sessions" in result["factors"]


# ── Test 4: compute_abandonment_risk returns low risk for active user ────


def test_abandonment_risk_active_user(conn):
    conn.execute("INSERT INTO user (id, email) VALUES (1, 'a@a.com')")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    for ts in [now, yesterday]:
        conn.execute("""
            INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                      duration_seconds, early_exit, boredom_flags)
            VALUES (1, ?, 10, 8, 300, 0, 0)
        """, (ts,))
    # Also add some in prior week
    prior = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
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
    conn.execute("INSERT INTO user (id, email) VALUES (1, 'a@a.com')")
    # 3 sessions in prior week, 0 in current week
    for i in range(3):
        ts = (datetime.now(timezone.utc) - timedelta(days=8 + i)).strftime("%Y-%m-%d %H:%M:%S")
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
    conn.execute("INSERT INTO user (id, email) VALUES (1, 'a@a.com')")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
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
    conn.execute("INSERT INTO user (id, email) VALUES (1, 'a@a.com')")
    conn.commit()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
    conn.execute("INSERT INTO user (id, email) VALUES (10, 'teacher@a.com')")
    conn.execute("INSERT INTO classroom (id, teacher_user_id, name, invite_code) VALUES (1, 10, 'HSK1', 'abc')")
    for uid in [1, 2, 3]:
        conn.execute("INSERT INTO user (id, email) VALUES (?, ?)", (uid, f"s{uid}@a.com"))
        conn.execute("INSERT INTO classroom_student (classroom_id, user_id) VALUES (1, ?)", (uid,))
    conn.commit()

    result = generate_cohort_snapshot(conn, classroom_id=1)
    assert result["total_students"] == 3
    assert result["at_risk_count"] + result["high_risk_count"] >= 0  # just no crash


# ── Test 9: cohort snapshot detects declining trend ──────────────────────


def test_cohort_snapshot_declining_trend(conn):
    conn.execute("INSERT INTO user (id, email) VALUES (10, 'teacher@a.com')")
    conn.execute("INSERT INTO classroom (id, teacher_user_id, name, invite_code) VALUES (1, 10, 'HSK1', 'abc')")
    conn.execute("INSERT INTO user (id, email) VALUES (1, 's1@a.com')")
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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
    conn.execute("INSERT INTO user (id, email) VALUES (1, 's@a.com')")
    conn.execute("INSERT INTO user (id, email) VALUES (10, 't@a.com')")

    # Log intervention with high risk
    conn.execute("""
        INSERT INTO pi_teacher_interventions
            (teacher_user_id, student_user_id, intervention_type, risk_at_intervention, created_at)
        VALUES (10, 1, 'email', 0.7, datetime('now', '-10 days'))
    """)
    conn.commit()

    # Student now has sessions → lower risk
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    for ts in [now, yesterday]:
        conn.execute("""
            INSERT INTO session_log (user_id, started_at, items_completed, items_correct,
                                      duration_seconds, early_exit, boredom_flags)
            VALUES (1, ?, 10, 9, 300, 0, 0)
        """, (ts,))
    # Prior week sessions too (prevent frequency decline flag)
    prior = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
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
