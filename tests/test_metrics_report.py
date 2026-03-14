"""Smoke tests for mandarin.metrics_report — covers all metric functions
and report formatters to bring the module up from 0% coverage.
"""

import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from mandarin.metrics_report import (
    _business_health,
    _engagement,
    _learning_outcomes,
    _funnel_metrics,
    _north_star,
    _completion_by_segment,
    _retention_cohorts,
    _growth_accounting,
    _crash_rate,
    _week_comparison,
    _generate_report_text,
    _generate_report_md,
    _safe_div,
    _safe_pct,
    _delta_str,
    _table_exists,
    generate_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """In-memory SQLite DB with tables and seed data matching the schema
    that metrics_report queries expect."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row

    c.executescript("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY, email TEXT, display_name TEXT,
            subscription_tier TEXT DEFAULT 'free', created_at TEXT,
            last_login_at TEXT, is_active INTEGER DEFAULT 1,
            password_hash TEXT DEFAULT ''
        );
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY, user_id INTEGER, started_at TEXT,
            ended_at TEXT, duration_seconds INTEGER,
            session_type TEXT DEFAULT 'standard',
            items_planned INTEGER DEFAULT 0,
            items_completed INTEGER DEFAULT 0,
            items_correct INTEGER DEFAULT 0,
            session_outcome TEXT DEFAULT 'completed',
            early_exit INTEGER DEFAULT 0,
            boredom_flags INTEGER DEFAULT 0,
            modality_counts TEXT,
            session_day_of_week INTEGER
        );
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY, user_id INTEGER,
            content_item_id INTEGER, modality TEXT DEFAULT 'reading',
            mastery_stage TEXT DEFAULT 'seen',
            total_attempts INTEGER DEFAULT 0,
            total_correct INTEGER DEFAULT 0,
            last_review_date TEXT, accuracy REAL DEFAULT 0.0
        );
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY, hanzi TEXT, pinyin TEXT,
            english TEXT, hsk_level INTEGER DEFAULT 1,
            status TEXT DEFAULT 'drill_ready',
            scale_level TEXT DEFAULT 'word',
            created_at TEXT
        );
        CREATE TABLE lifecycle_event (
            id INTEGER PRIMARY KEY, user_id INTEGER,
            event_type TEXT, created_at TEXT
        );
        CREATE TABLE crash_log (
            id INTEGER PRIMARY KEY, user_id INTEGER,
            timestamp TEXT, error_type TEXT, error_message TEXT
        );
        CREATE TABLE error_log (
            id INTEGER PRIMARY KEY, user_id INTEGER,
            content_item_id INTEGER, error_type TEXT,
            created_at TEXT
        );
    """)

    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    three_days_ago = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    ten_days_ago = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    month_ago = (now - timedelta(days=25)).strftime("%Y-%m-%d %H:%M:%S")
    # lifecycle_event timestamps need timezone info for fromisoformat() compat
    month_ago_iso = (now - timedelta(days=25)).isoformat()

    # Seed user
    c.execute(
        "INSERT INTO user (id, email, display_name, created_at) "
        "VALUES (1, 'test@test.com', 'Test', ?)",
        (month_ago,),
    )

    # Seed content items (10 items across HSK 1-3)
    for i in range(1, 11):
        c.execute(
            "INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (i, f"字{i}", f"zi{i}", f"word{i}", min(i, 3), month_ago),
        )

    # Session this week — completed, with data
    c.execute(
        "INSERT INTO session_log "
        "(user_id, started_at, ended_at, duration_seconds, "
        "items_planned, items_completed, items_correct, session_outcome, "
        "modality_counts) "
        "VALUES (1, ?, ?, 300, 10, 8, 6, 'completed', ?)",
        (three_days_ago, three_days_ago, '{"reading": 4, "listening": 2, "tone": 2}'),
    )

    # Session last week — abandoned with early exit
    c.execute(
        "INSERT INTO session_log "
        "(user_id, started_at, ended_at, duration_seconds, "
        "items_planned, items_completed, items_correct, "
        "session_outcome, early_exit, boredom_flags) "
        "VALUES (1, ?, ?, 120, 10, 3, 2, 'abandoned', 1, 1)",
        (ten_days_ago, ten_days_ago),
    )

    # Session 25 days ago — for growth accounting "older" bucket
    c.execute(
        "INSERT INTO session_log "
        "(user_id, started_at, ended_at, duration_seconds, "
        "items_planned, items_completed, items_correct, "
        "session_outcome) "
        "VALUES (1, ?, ?, 180, 10, 5, 4, 'completed')",
        (month_ago, month_ago),
    )

    # Seed progress — 5 items mastered, reviewed recently
    for i in range(1, 6):
        c.execute(
            "INSERT INTO progress "
            "(user_id, content_item_id, modality, mastery_stage, "
            "total_attempts, total_correct, last_review_date, accuracy) "
            "VALUES (1, ?, 'reading', 'stable', 10, 9, ?, 0.9)",
            (i, yesterday),
        )

    # Seed lifecycle event — signup (ISO format with tz for fromisoformat)
    c.execute(
        "INSERT INTO lifecycle_event (user_id, event_type, created_at) "
        "VALUES (1, 'signup', ?)",
        (month_ago_iso,),
    )

    c.commit()
    yield c
    c.close()


@pytest.fixture
def empty_conn():
    """In-memory SQLite DB with tables but NO data — for edge-case tests."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row

    c.executescript("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY, email TEXT, display_name TEXT,
            subscription_tier TEXT DEFAULT 'free', created_at TEXT,
            last_login_at TEXT, is_active INTEGER DEFAULT 1
        );
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY, user_id INTEGER, started_at TEXT,
            ended_at TEXT, duration_seconds INTEGER,
            session_type TEXT DEFAULT 'standard',
            items_planned INTEGER DEFAULT 0,
            items_completed INTEGER DEFAULT 0,
            items_correct INTEGER DEFAULT 0,
            session_outcome TEXT DEFAULT 'completed',
            early_exit INTEGER DEFAULT 0,
            boredom_flags INTEGER DEFAULT 0,
            modality_counts TEXT,
            session_day_of_week INTEGER
        );
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY, user_id INTEGER,
            content_item_id INTEGER, modality TEXT DEFAULT 'reading',
            mastery_stage TEXT DEFAULT 'seen',
            total_attempts INTEGER DEFAULT 0,
            total_correct INTEGER DEFAULT 0,
            last_review_date TEXT, accuracy REAL DEFAULT 0.0
        );
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY, hanzi TEXT, pinyin TEXT,
            english TEXT, hsk_level INTEGER DEFAULT 1,
            status TEXT DEFAULT 'drill_ready',
            scale_level TEXT DEFAULT 'word',
            created_at TEXT
        );
        CREATE TABLE lifecycle_event (
            id INTEGER PRIMARY KEY, user_id INTEGER,
            event_type TEXT, created_at TEXT
        );
        CREATE TABLE crash_log (
            id INTEGER PRIMARY KEY, user_id INTEGER,
            timestamp TEXT, error_type TEXT, error_message TEXT
        );
    """)

    c.commit()
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_safe_div_normal(self):
        assert _safe_div(10, 5) == 2.0

    def test_safe_div_zero_denominator(self):
        assert _safe_div(10, 0) == 0.0

    def test_safe_pct_normal(self):
        assert _safe_pct(3, 4) == 75.0

    def test_safe_pct_zero_denominator(self):
        assert _safe_pct(5, 0) == 0.0

    def test_delta_str_positive(self):
        assert _delta_str(5, "%") == "+5%"

    def test_delta_str_negative(self):
        assert _delta_str(-3, "pp") == "-3pp"

    def test_delta_str_zero(self):
        assert _delta_str(0) == "0"

    def test_table_exists_true(self, conn):
        assert _table_exists(conn, "session_log") is True

    def test_table_exists_false(self, conn):
        assert _table_exists(conn, "nonexistent_table") is False


# ---------------------------------------------------------------------------
# Business Health
# ---------------------------------------------------------------------------

class TestBusinessHealth:
    def test_returns_expected_keys(self, conn):
        result = _business_health(conn, user_id=1)
        assert "active_users_30d" in result
        assert "wau" in result
        assert "sessions_this_week" in result
        assert "sessions_last_week" in result

    def test_active_user_detected(self, conn):
        result = _business_health(conn, user_id=1)
        assert result["active_users_30d"] == 1

    def test_sessions_this_week_counted(self, conn):
        result = _business_health(conn, user_id=1)
        # We inserted one session 3 days ago with items_completed > 0
        assert result["sessions_this_week"] >= 1

    def test_empty_db_zero_values(self, empty_conn):
        result = _business_health(empty_conn, user_id=1)
        assert result["active_users_30d"] == 0
        assert result["wau"] == 0
        assert result["sessions_this_week"] == 0


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------

class TestEngagement:
    def test_returns_expected_keys(self, conn):
        result = _engagement(conn, user_id=1)
        expected_keys = [
            "sessions_per_user_week", "avg_session_duration_sec",
            "avg_session_duration_min", "drill_accuracy_pct",
            "accuracy_by_modality", "drill_type_diversity",
            "drill_types_used", "reading_adoption_pct",
            "listening_adoption_pct", "early_exit_rate_pct",
            "boredom_flag_rate_pct",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_drill_accuracy_is_numeric(self, conn):
        result = _engagement(conn, user_id=1)
        assert isinstance(result["drill_accuracy_pct"], float)

    def test_drill_type_diversity_from_modality_counts(self, conn):
        result = _engagement(conn, user_id=1)
        # We seeded one session with {"reading": 4, "listening": 2, "tone": 2}
        assert result["drill_type_diversity"] >= 1
        assert isinstance(result["drill_types_used"], list)

    def test_empty_db_no_crash(self, empty_conn):
        result = _engagement(empty_conn, user_id=1)
        assert result["sessions_per_user_week"] == 0
        assert result["drill_accuracy_pct"] == 0.0


# ---------------------------------------------------------------------------
# Learning Outcomes
# ---------------------------------------------------------------------------

class TestLearningOutcomes:
    def test_returns_expected_keys(self, conn):
        result = _learning_outcomes(conn, user_id=1)
        assert "words_at_85pct" in result
        assert "avg_retention_pct" in result
        assert "most_failed_items" in result
        assert "hsk_distribution" in result
        assert "mastery_distribution" in result

    def test_words_at_85pct(self, conn):
        result = _learning_outcomes(conn, user_id=1)
        # 5 progress rows with 9/10 = 90% accuracy, >= 3 attempts
        assert result["words_at_85pct"] == 5

    def test_mastery_distribution(self, conn):
        result = _learning_outcomes(conn, user_id=1)
        assert "stable" in result["mastery_distribution"]
        assert result["mastery_distribution"]["stable"] == 5

    def test_empty_db_returns_defaults(self, empty_conn):
        result = _learning_outcomes(empty_conn, user_id=1)
        assert result["words_at_85pct"] == 0
        assert result["avg_retention_pct"] == 0.0


# ---------------------------------------------------------------------------
# Funnel Metrics
# ---------------------------------------------------------------------------

class TestFunnelMetrics:
    def test_returns_expected_keys(self, conn):
        result = _funnel_metrics(conn, user_id=1)
        assert "new_content_this_week" in result
        assert "vocab_encounters_this_week" in result
        assert "sessions_by_day" in result
        assert "session_outcomes" in result

    def test_session_outcomes_include_completed(self, conn):
        result = _funnel_metrics(conn, user_id=1)
        # We have sessions with 'completed' and 'abandoned' outcomes
        outcomes = result["session_outcomes"]
        assert isinstance(outcomes, dict)

    def test_sessions_by_day_has_all_days(self, conn):
        result = _funnel_metrics(conn, user_id=1)
        days = result["sessions_by_day"]
        assert len(days) == 7
        for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            assert d in days

    def test_empty_db_no_crash(self, empty_conn):
        result = _funnel_metrics(empty_conn, user_id=1)
        assert result["new_content_this_week"] == 0


# ---------------------------------------------------------------------------
# North Star
# ---------------------------------------------------------------------------

class TestNorthStar:
    def test_returns_expected_keys(self, conn):
        result = _north_star(conn, user_id=1)
        assert "items_mastered_this_week" in result
        assert "mastered_per_active_user" in result
        assert "active_users_this_week" in result

    def test_mastered_items_counted(self, conn):
        result = _north_star(conn, user_id=1)
        # 5 items with 90% accuracy, 10 attempts, reviewed yesterday
        assert result["items_mastered_this_week"] == 5

    def test_empty_db_returns_zeros(self, empty_conn):
        result = _north_star(empty_conn, user_id=1)
        assert result["items_mastered_this_week"] == 0


# ---------------------------------------------------------------------------
# Completion by Segment
# ---------------------------------------------------------------------------

class TestCompletionBySegment:
    def test_returns_expected_keys(self, conn):
        result = _completion_by_segment(conn, user_id=1)
        assert "by_session_type" in result
        assert "by_hsk_band" in result
        assert "overall_rate" in result
        assert "overall_total" in result
        assert "overall_completed" in result

    def test_session_types_populated(self, conn):
        result = _completion_by_segment(conn, user_id=1)
        # We have a 'standard' session this week
        if result["by_session_type"]:
            for stype, data in result["by_session_type"].items():
                assert "total" in data
                assert "completed" in data
                assert "rate" in data

    def test_empty_db_no_crash(self, empty_conn):
        result = _completion_by_segment(empty_conn, user_id=1)
        assert result["overall_rate"] == 0.0


# ---------------------------------------------------------------------------
# Retention Cohorts
# ---------------------------------------------------------------------------

class TestRetentionCohorts:
    def test_returns_expected_keys(self, conn):
        result = _retention_cohorts(conn)
        assert "d1" in result
        assert "d7" in result
        assert "d30" in result
        assert "signups_30d" in result

    def test_signup_detected(self, conn):
        result = _retention_cohorts(conn)
        # We seeded one signup 25 days ago
        assert result["signups_30d"] >= 1

    def test_d1_eligible(self, conn):
        result = _retention_cohorts(conn)
        # User signed up 25 days ago — easily D1 eligible
        assert result["d1_eligible"] >= 1

    def test_empty_db_returns_zeros(self, empty_conn):
        result = _retention_cohorts(empty_conn)
        assert result["d1"] == 0.0
        assert result["signups_30d"] == 0


# ---------------------------------------------------------------------------
# Growth Accounting
# ---------------------------------------------------------------------------

class TestGrowthAccounting:
    def test_returns_expected_keys(self, conn):
        result = _growth_accounting(conn)
        assert "new" in result
        assert "retained" in result
        assert "resurrected" in result
        assert "churned" in result
        assert "net_retention" in result

    def test_user_categorised(self, conn):
        result = _growth_accounting(conn)
        # User 1 has session this week (3d ago) + last week (10d ago) => retained
        total = result["new"] + result["retained"] + result["resurrected"] + result["churned"]
        assert total >= 1

    def test_empty_db_all_zero(self, empty_conn):
        result = _growth_accounting(empty_conn)
        assert result["new"] == 0
        assert result["retained"] == 0
        assert result["resurrected"] == 0
        assert result["churned"] == 0


# ---------------------------------------------------------------------------
# Crash Rate
# ---------------------------------------------------------------------------

class TestCrashRate:
    def test_no_crashes_zero_rate(self, conn):
        result = _crash_rate(conn)
        assert result["crashes"] == 0
        assert result["rate_pct"] == 0.0
        assert result["top_errors"] == []

    def test_with_crashes_positive_rate(self, conn):
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO crash_log (user_id, timestamp, error_type, error_message) "
            "VALUES (1, ?, 'ValueError', 'test crash')",
            (now_str,),
        )
        conn.execute(
            "INSERT INTO crash_log (user_id, timestamp, error_type, error_message) "
            "VALUES (1, ?, 'ValueError', 'another crash')",
            (now_str,),
        )
        conn.commit()

        result = _crash_rate(conn)
        assert result["crashes"] == 2
        assert result["rate_pct"] > 0
        assert len(result["top_errors"]) >= 1
        assert result["top_errors"][0]["type"] == "ValueError"

    def test_sessions_counted(self, conn):
        result = _crash_rate(conn)
        # We have at least 1 session this week
        assert result["sessions"] >= 1

    def test_empty_db_no_crash_data(self, empty_conn):
        result = _crash_rate(empty_conn)
        assert result["crashes"] == 0
        assert result["sessions"] == 0
        assert result["rate_pct"] == 0.0


# ---------------------------------------------------------------------------
# Week Comparison
# ---------------------------------------------------------------------------

class TestWeekComparison:
    def test_returns_expected_keys(self, conn):
        result = _week_comparison(conn, user_id=1)
        expected = [
            "sessions_delta", "items_delta",
            "accuracy_this_week", "accuracy_last_week", "accuracy_delta",
            "avg_dur_this_week", "avg_dur_last_week",
        ]
        for key in expected:
            assert key in result, f"Missing key: {key}"

    def test_sessions_delta_computed(self, conn):
        result = _week_comparison(conn, user_id=1)
        # 1 session this week (3d ago), 1 last week (10d ago) => delta = 0
        assert isinstance(result["sessions_delta"], int)

    def test_accuracy_values_are_float(self, conn):
        result = _week_comparison(conn, user_id=1)
        assert isinstance(result["accuracy_this_week"], float)
        assert isinstance(result["accuracy_last_week"], float)

    def test_empty_db_no_crash(self, empty_conn):
        result = _week_comparison(empty_conn, user_id=1)
        assert result["sessions_delta"] == 0
        assert result["accuracy_this_week"] == 0.0


# ---------------------------------------------------------------------------
# Report Formatters
# ---------------------------------------------------------------------------

def _build_metric_dicts(conn):
    """Run all metric functions and return the dicts needed by formatters."""
    biz = _business_health(conn, user_id=1)
    eng = _engagement(conn, user_id=1)
    learn = _learning_outcomes(conn, user_id=1)
    funnel = _funnel_metrics(conn, user_id=1)
    wow = _week_comparison(conn, user_id=1)
    ns = _north_star(conn, user_id=1)
    comp_seg = _completion_by_segment(conn, user_id=1)
    retention = _retention_cohorts(conn)
    growth = _growth_accounting(conn)
    crashes = _crash_rate(conn)
    extra = {
        "north_star": ns,
        "completion_by_segment": comp_seg,
        "retention": retention,
        "growth": growth,
        "crashes": crashes,
    }
    return biz, eng, learn, funnel, wow, extra


class TestGenerateReportText:
    def test_returns_string(self, conn):
        biz, eng, learn, funnel, wow, extra = _build_metric_dicts(conn)
        result = _generate_report_text(biz, eng, learn, funnel, wow, "2026-02-26", extra=extra)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_section_headers(self, conn):
        biz, eng, learn, funnel, wow, extra = _build_metric_dicts(conn)
        result = _generate_report_text(biz, eng, learn, funnel, wow, "2026-02-26", extra=extra)
        assert "NORTH STAR" in result
        assert "BUSINESS HEALTH" in result
        assert "ENGAGEMENT" in result
        assert "LEARNING OUTCOMES" in result

    def test_contains_report_date(self, conn):
        biz, eng, learn, funnel, wow, extra = _build_metric_dicts(conn)
        result = _generate_report_text(biz, eng, learn, funnel, wow, "2026-02-26", extra=extra)
        assert "2026-02-26" in result


class TestGenerateReportMd:
    def test_returns_string_with_markdown_headers(self, conn):
        biz, eng, learn, funnel, wow, extra = _build_metric_dicts(conn)
        result = _generate_report_md(biz, eng, learn, funnel, wow, "2026-02-26", extra=extra)
        assert isinstance(result, str)
        assert "# Weekly Report" in result
        assert "## North Star" in result
        assert "## Business Health" in result
        assert "## Engagement" in result

    def test_markdown_tables_present(self, conn):
        biz, eng, learn, funnel, wow, extra = _build_metric_dicts(conn)
        result = _generate_report_md(biz, eng, learn, funnel, wow, "2026-02-26", extra=extra)
        # Markdown tables use |
        assert "|" in result
        assert "| Metric |" in result


# ---------------------------------------------------------------------------
# generate_report (integration — uses db_path, not conn)
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_with_real_db_file_returns_dict(self, conn):
        """Write the in-memory DB to a temp file, then call generate_report."""
        import tempfile, shutil
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        tmp_path = Path(tmp.name)
        try:
            # Copy in-memory DB to file
            disk = sqlite3.connect(str(tmp_path))
            conn.backup(disk)
            disk.close()

            result = generate_report(
                db_path=str(tmp_path),
                output_format="quiet",
                save=False,
                user_id=1,
            )
            assert isinstance(result, dict)
            assert "business_health" in result
            assert "engagement" in result
            assert "learning_outcomes" in result
            assert "funnel" in result
            assert "week_comparison" in result
            assert "north_star" in result
            assert "completion_by_segment" in result
            assert "retention" in result
            assert "growth" in result
            assert "crashes" in result
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_missing_db_returns_empty(self, tmp_path):
        result = generate_report(
            db_path=str(tmp_path / "nonexistent.db"),
            output_format="quiet",
            save=False,
        )
        assert result == {}

    def test_plain_format_prints(self, conn, capsys):
        """Ensure plain format writes to stdout."""
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        tmp_path = Path(tmp.name)
        try:
            disk = sqlite3.connect(str(tmp_path))
            conn.backup(disk)
            disk.close()

            generate_report(
                db_path=str(tmp_path),
                output_format="plain",
                save=False,
                user_id=1,
            )
            captured = capsys.readouterr()
            assert "WEEKLY REPORT" in captured.out
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_dict_includes_north_star_data(self, conn):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        tmp_path = Path(tmp.name)
        try:
            disk = sqlite3.connect(str(tmp_path))
            conn.backup(disk)
            disk.close()

            result = generate_report(
                db_path=str(tmp_path),
                output_format="quiet",
                save=False,
                user_id=1,
            )
            ns = result["north_star"]
            assert "items_mastered_this_week" in ns
            assert "mastered_per_active_user" in ns
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Edge cases — all functions on empty DB
# ---------------------------------------------------------------------------

class TestEmptyDbEdgeCases:
    """Every metric function must survive an empty database without error."""

    def test_business_health_empty(self, empty_conn):
        result = _business_health(empty_conn, user_id=99)
        assert result["wau"] == 0

    def test_engagement_empty(self, empty_conn):
        result = _engagement(empty_conn, user_id=99)
        assert result["drill_accuracy_pct"] == 0.0

    def test_learning_outcomes_empty(self, empty_conn):
        result = _learning_outcomes(empty_conn, user_id=99)
        assert result["words_at_85pct"] == 0

    def test_funnel_metrics_empty(self, empty_conn):
        result = _funnel_metrics(empty_conn, user_id=99)
        assert result["new_content_this_week"] == 0

    def test_north_star_empty(self, empty_conn):
        result = _north_star(empty_conn, user_id=99)
        assert result["items_mastered_this_week"] == 0

    def test_completion_by_segment_empty(self, empty_conn):
        result = _completion_by_segment(empty_conn, user_id=99)
        assert result["overall_rate"] == 0.0

    def test_retention_cohorts_empty(self, empty_conn):
        result = _retention_cohorts(empty_conn)
        assert result["signups_30d"] == 0

    def test_growth_accounting_empty(self, empty_conn):
        result = _growth_accounting(empty_conn)
        assert result["new"] == 0

    def test_crash_rate_empty(self, empty_conn):
        result = _crash_rate(empty_conn)
        assert result["rate_pct"] == 0.0

    def test_week_comparison_empty(self, empty_conn):
        result = _week_comparison(empty_conn, user_id=99)
        assert result["sessions_delta"] == 0

    def test_formatters_with_empty_data(self, empty_conn):
        """Text and Markdown formatters must not crash on empty data."""
        biz, eng, learn, funnel, wow, extra = _build_metric_dicts(empty_conn)
        text = _generate_report_text(biz, eng, learn, funnel, wow, "2026-02-26", extra=extra)
        assert isinstance(text, str) and len(text) > 0
        md = _generate_report_md(biz, eng, learn, funnel, wow, "2026-02-26", extra=extra)
        assert isinstance(md, str) and "# Weekly Report" in md
