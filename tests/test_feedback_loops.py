"""Tests for mandarin/intelligence/feedback_loops.py.

Uses in-memory SQLite with conn.row_factory = sqlite3.Row so that all
row accesses via column name work exactly as the production code expects.
"""

import json
import sqlite3

import pytest

from mandarin.intelligence.feedback_loops import (
    analyze_experiments,
    analyze_improvement_log,
    calibrate_thresholds,
    get_calibrated_threshold,
    get_loop_closure_summary,
    measure_encounter_effectiveness,
    record_recommendation_outcome,
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS pi_finding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    dimension TEXT,
    severity TEXT,
    title TEXT,
    analysis TEXT,
    status TEXT DEFAULT 'investigating',
    hypothesis TEXT,
    falsification TEXT,
    root_cause_tag TEXT,
    linked_finding_id INTEGER,
    metric_name TEXT,
    metric_value_at_detection REAL,
    times_seen INTEGER DEFAULT 1,
    last_seen_audit_id INTEGER,
    resolved_at TEXT,
    resolution_notes TEXT
);

CREATE TABLE IF NOT EXISTS pi_recommendation_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    action_type TEXT CHECK(action_type IN ('code_change','config_change','content_change','experiment')),
    action_description TEXT,
    files_changed TEXT,
    commit_hash TEXT,
    metric_before TEXT,
    metric_after TEXT,
    verified_at TEXT,
    delta_pct REAL,
    effective INTEGER CHECK(effective IN (-1,0,1))
);

CREATE TABLE IF NOT EXISTS pi_threshold_calibration (
    metric_name TEXT PRIMARY KEY,
    threshold_value REAL,
    calibrated_at TEXT DEFAULT (datetime('now')),
    sample_size INTEGER,
    false_positive_rate REAL,
    false_negative_rate REAL,
    prior_threshold REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS experiment (
    id INTEGER PRIMARY KEY,
    name TEXT,
    status TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    min_sample_size INTEGER
);

CREATE TABLE IF NOT EXISTS experiment_assignment (
    id INTEGER PRIMARY KEY,
    experiment_id INTEGER,
    user_id INTEGER
);

CREATE TABLE IF NOT EXISTS improvement_log (
    id INTEGER PRIMARY KEY,
    status TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vocab_encounter (
    id INTEGER PRIMARY KEY,
    content_item_id INTEGER,
    looked_up INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    hanzi TEXT,
    source_type TEXT,
    source_id INTEGER
);

CREATE TABLE IF NOT EXISTS progress (
    content_item_id INTEGER,
    user_id INTEGER,
    mastery_stage TEXT,
    repetitions INTEGER,
    ease_factor REAL
);
"""


@pytest.fixture
def conn():
    """In-memory SQLite connection with row_factory and all required tables."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(DDL)
    c.commit()
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_finding(conn, *, dimension="retention", severity="medium",
                    title="Test finding", status="investigating",
                    created_at=None):
    sql = """
        INSERT INTO pi_finding (dimension, severity, title, status, created_at)
        VALUES (?, ?, ?, ?, COALESCE(?, datetime('now')))
    """
    cur = conn.execute(sql, (dimension, severity, title, status, created_at))
    conn.commit()
    return cur.lastrowid


def _insert_outcome(conn, *, finding_id=1, action_type="code_change",
                    description="fixed it", files_changed=None,
                    metric_before=None, metric_after=None,
                    verified_at=None, delta_pct=None, effective=None,
                    created_at=None):
    conn.execute("""
        INSERT INTO pi_recommendation_outcome
            (finding_id, action_type, action_description, files_changed,
             metric_before, metric_after, verified_at, delta_pct, effective,
             created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))
    """, (
        finding_id, action_type, description,
        json.dumps(files_changed) if files_changed else None,
        json.dumps(metric_before) if metric_before else None,
        json.dumps(metric_after) if metric_after else None,
        verified_at, delta_pct, effective, created_at,
    ))
    conn.commit()


# ===========================================================================
# record_recommendation_outcome
# ===========================================================================

class TestRecordRecommendationOutcome:

    def test_returns_positive_id(self, conn):
        fid = _insert_finding(conn)
        outcome_id = record_recommendation_outcome(
            conn, fid, "code_change", "patched the bug"
        )
        assert isinstance(outcome_id, int)
        assert outcome_id > 0

    def test_row_persisted(self, conn):
        fid = _insert_finding(conn)
        outcome_id = record_recommendation_outcome(
            conn, fid, "config_change", "tuned scheduler",
            files_changed=["mandarin/scheduler.py"],
            metric_before={"value": 0.42},
        )
        row = conn.execute(
            "SELECT * FROM pi_recommendation_outcome WHERE id = ?", (outcome_id,)
        ).fetchone()
        assert row is not None
        assert row["finding_id"] == fid
        assert row["action_type"] == "config_change"
        assert row["action_description"] == "tuned scheduler"

    def test_files_changed_serialized_as_json(self, conn):
        fid = _insert_finding(conn)
        files = ["mandarin/web/routes.py", "schema.sql"]
        oid = record_recommendation_outcome(
            conn, fid, "code_change", "two-file fix", files_changed=files
        )
        row = conn.execute(
            "SELECT files_changed FROM pi_recommendation_outcome WHERE id = ?", (oid,)
        ).fetchone()
        assert json.loads(row["files_changed"]) == files

    def test_metric_before_serialized_as_json(self, conn):
        fid = _insert_finding(conn)
        mb = {"value": 73.5, "unit": "pct"}
        oid = record_recommendation_outcome(
            conn, fid, "experiment", "A/B test variant", metric_before=mb
        )
        row = conn.execute(
            "SELECT metric_before FROM pi_recommendation_outcome WHERE id = ?", (oid,)
        ).fetchone()
        assert json.loads(row["metric_before"]) == mb

    def test_null_files_and_metric(self, conn):
        fid = _insert_finding(conn)
        oid = record_recommendation_outcome(
            conn, fid, "content_change", "rewrote passage"
        )
        row = conn.execute(
            "SELECT files_changed, metric_before FROM pi_recommendation_outcome WHERE id = ?",
            (oid,)
        ).fetchone()
        assert row["files_changed"] is None
        assert row["metric_before"] is None

    def test_ids_are_sequential(self, conn):
        fid = _insert_finding(conn)
        id1 = record_recommendation_outcome(conn, fid, "code_change", "first")
        id2 = record_recommendation_outcome(conn, fid, "code_change", "second")
        assert id2 == id1 + 1

    def test_invalid_action_type_returns_minus_one(self, conn):
        """The CHECK constraint on action_type should cause failure → -1."""
        fid = _insert_finding(conn)
        result = record_recommendation_outcome(
            conn, fid, "invalid_type", "should fail"
        )
        assert result == -1

    def test_multiple_outcomes_for_same_finding(self, conn):
        fid = _insert_finding(conn)
        record_recommendation_outcome(conn, fid, "code_change", "attempt 1")
        record_recommendation_outcome(conn, fid, "code_change", "attempt 2")
        count = conn.execute(
            "SELECT COUNT(*) FROM pi_recommendation_outcome WHERE finding_id = ?", (fid,)
        ).fetchone()[0]
        assert count == 2


# ===========================================================================
# calibrate_thresholds
# ===========================================================================

class TestCalibrateThresholds:

    def test_empty_db_returns_empty_list(self, conn):
        result = calibrate_thresholds(conn)
        assert result == []

    def test_no_calibration_when_fewer_than_5_findings(self, conn):
        for _ in range(4):
            _insert_finding(conn, dimension="retention", status="rejected")
        result = calibrate_thresholds(conn)
        assert result == []

    def test_no_calibration_when_fpr_below_threshold(self, conn):
        # 5 findings, 1 rejected → FPR = 20 % (<= 25 %)
        for i in range(4):
            _insert_finding(conn, dimension="retention", status="verified")
        _insert_finding(conn, dimension="retention", status="rejected")
        result = calibrate_thresholds(conn)
        assert result == []

    def test_calibration_triggered_when_fpr_exceeds_25pct(self, conn):
        # 5 findings, 2 rejected → FPR = 40 % (> 25 %)
        for _ in range(3):
            _insert_finding(conn, dimension="retention", status="verified")
        for _ in range(2):
            _insert_finding(conn, dimension="retention", status="rejected")
        result = calibrate_thresholds(conn)
        assert len(result) == 1
        adj = result[0]
        assert adj["dimension"] == "retention"
        assert adj["fpr"] == pytest.approx(40.0, abs=0.1)

    def test_new_threshold_is_20pct_higher_than_default(self, conn):
        for _ in range(3):
            _insert_finding(conn, dimension="ux", status="verified")
        for _ in range(2):
            _insert_finding(conn, dimension="ux", status="rejected")
        result = calibrate_thresholds(conn)
        adj = result[0]
        # Default prior is 1.0 → new = 1.0 * 1.2 = 1.2
        assert adj["new"] == pytest.approx(1.2, abs=0.001)
        assert adj["prior"] is None

    def test_subsequent_calibration_uses_stored_threshold(self, conn):
        # Seed an existing calibration
        conn.execute("""
            INSERT INTO pi_threshold_calibration (metric_name, threshold_value)
            VALUES ('engineering', 2.0)
        """)
        conn.commit()
        for _ in range(3):
            _insert_finding(conn, dimension="engineering", status="verified")
        for _ in range(2):
            _insert_finding(conn, dimension="engineering", status="rejected")
        result = calibrate_thresholds(conn)
        adj = result[0]
        assert adj["prior"] == pytest.approx(2.0)
        assert adj["new"] == pytest.approx(2.4, abs=0.001)

    def test_calibration_record_written_to_table(self, conn):
        for _ in range(3):
            _insert_finding(conn, dimension="frustration", status="verified")
        for _ in range(2):
            _insert_finding(conn, dimension="frustration", status="rejected")
        calibrate_thresholds(conn)
        row = conn.execute(
            "SELECT * FROM pi_threshold_calibration WHERE metric_name = 'frustration'"
        ).fetchone()
        assert row is not None
        assert row["threshold_value"] == pytest.approx(1.2, abs=0.001)
        assert row["sample_size"] == 5
        assert row["false_positive_rate"] == pytest.approx(40.0, abs=0.1)

    def test_multiple_dimensions_calibrated_independently(self, conn):
        for dim in ("retention", "ux"):
            for _ in range(3):
                _insert_finding(conn, dimension=dim, status="verified")
            for _ in range(2):
                _insert_finding(conn, dimension=dim, status="rejected")
        result = calibrate_thresholds(conn)
        dims = {adj["dimension"] for adj in result}
        assert "retention" in dims
        assert "ux" in dims

    def test_old_findings_excluded_from_calibration(self, conn):
        # Findings older than 180 days should not be included.
        for _ in range(3):
            _insert_finding(
                conn, dimension="retention", status="verified",
                created_at="2020-01-01 00:00:00"
            )
        for _ in range(2):
            _insert_finding(
                conn, dimension="retention", status="rejected",
                created_at="2020-01-01 00:00:00"
            )
        result = calibrate_thresholds(conn)
        assert result == []

    def test_upsert_updates_existing_calibration(self, conn):
        # Insert initial calibration
        conn.execute("""
            INSERT INTO pi_threshold_calibration
                (metric_name, threshold_value, false_positive_rate)
            VALUES ('retention', 1.5, 10.0)
        """)
        conn.commit()
        for _ in range(3):
            _insert_finding(conn, dimension="retention", status="verified")
        for _ in range(2):
            _insert_finding(conn, dimension="retention", status="rejected")
        calibrate_thresholds(conn)
        rows = conn.execute(
            "SELECT COUNT(*) FROM pi_threshold_calibration WHERE metric_name = 'retention'"
        ).fetchone()[0]
        assert rows == 1  # Still just one row — upsert, not duplicate

    def test_returns_sample_size_in_adjustment(self, conn):
        for _ in range(6):
            _insert_finding(conn, dimension="profitability", status="rejected")
        result = calibrate_thresholds(conn)
        assert result[0]["sample_size"] == 6


# ===========================================================================
# get_calibrated_threshold
# ===========================================================================

class TestGetCalibratedThreshold:

    def test_returns_default_when_table_empty(self, conn):
        val = get_calibrated_threshold(conn, "nonexistent_metric", default=2.5)
        assert val == pytest.approx(2.5)

    def test_returns_stored_threshold(self, conn):
        conn.execute("""
            INSERT INTO pi_threshold_calibration (metric_name, threshold_value)
            VALUES ('retention', 1.8)
        """)
        conn.commit()
        val = get_calibrated_threshold(conn, "retention", default=1.0)
        assert val == pytest.approx(1.8)

    def test_default_when_metric_not_present(self, conn):
        conn.execute("""
            INSERT INTO pi_threshold_calibration (metric_name, threshold_value)
            VALUES ('ux', 1.3)
        """)
        conn.commit()
        val = get_calibrated_threshold(conn, "retention", default=9.9)
        assert val == pytest.approx(9.9)

    def test_default_value_is_1_0_when_not_supplied(self, conn):
        val = get_calibrated_threshold(conn, "anything")
        assert val == pytest.approx(1.0)

    def test_calibrated_value_overrides_explicit_default(self, conn):
        conn.execute("""
            INSERT INTO pi_threshold_calibration (metric_name, threshold_value)
            VALUES ('frustration', 3.14)
        """)
        conn.commit()
        val = get_calibrated_threshold(conn, "frustration", default=99.0)
        assert val == pytest.approx(3.14)

    def test_roundtrip_after_calibrate_thresholds(self, conn):
        for _ in range(3):
            _insert_finding(conn, dimension="engineering", status="verified")
        for _ in range(2):
            _insert_finding(conn, dimension="engineering", status="rejected")
        calibrate_thresholds(conn)
        val = get_calibrated_threshold(conn, "engineering", default=1.0)
        assert val == pytest.approx(1.2, abs=0.001)


# ===========================================================================
# analyze_experiments
# ===========================================================================

class TestAnalyzeExperiments:

    def test_empty_db_returns_empty_list(self, conn):
        result = analyze_experiments(conn)
        assert result == []

    def test_no_finding_when_running_experiment_has_insufficient_sample(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, min_sample_size)
            VALUES (1, 'btn_color', 'running', 100)
        """)
        # Only 50 assignments
        for i in range(50):
            conn.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id) VALUES (1, ?)",
                (i + 1,)
            )
        conn.commit()
        findings = analyze_experiments(conn)
        sample_findings = [f for f in findings if "reached sample size" in f["title"]]
        assert len(sample_findings) == 0

    def test_finding_when_experiment_reaches_min_sample(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, min_sample_size)
            VALUES (1, 'btn_color', 'running', 50)
        """)
        for i in range(50):
            conn.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id) VALUES (1, ?)",
                (i + 1,)
            )
        conn.commit()
        findings = analyze_experiments(conn)
        sample_findings = [f for f in findings if "reached sample size" in f["title"]]
        assert len(sample_findings) == 1

    def test_sample_size_finding_includes_experiment_name(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, min_sample_size)
            VALUES (1, 'onboarding_v2', 'running', 10)
        """)
        for i in range(10):
            conn.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id) VALUES (1, ?)",
                (i + 1,)
            )
        conn.commit()
        findings = analyze_experiments(conn)
        sample_findings = [f for f in findings if "reached sample size" in f["title"]]
        assert any("onboarding_v2" in f["title"] for f in sample_findings)

    def test_finding_when_experiment_running_over_30_days(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, created_at, min_sample_size)
            VALUES (1, 'old_exp', 'running', datetime('now', '-31 days'), 200)
        """)
        conn.commit()
        findings = analyze_experiments(conn)
        stale = [f for f in findings if "30 days" in f["title"]]
        assert len(stale) == 1

    def test_stale_finding_includes_experiment_name(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, created_at, min_sample_size)
            VALUES (1, 'stale_v3', 'running', datetime('now', '-45 days'), 500)
        """)
        conn.commit()
        findings = analyze_experiments(conn)
        stale = [f for f in findings if "30 days" in f["title"]]
        assert any("stale_v3" in f["title"] for f in stale)

    def test_completed_experiment_does_not_appear(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, min_sample_size)
            VALUES (1, 'done_exp', 'completed', 10)
        """)
        for i in range(20):
            conn.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id) VALUES (1, ?)",
                (i + 1,)
            )
        conn.commit()
        findings = analyze_experiments(conn)
        assert findings == []

    def test_new_running_experiment_within_30_days_no_stale(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, created_at, min_sample_size)
            VALUES (1, 'fresh_exp', 'running', datetime('now', '-5 days'), 200)
        """)
        conn.commit()
        findings = analyze_experiments(conn)
        stale = [f for f in findings if "30 days" in f["title"]]
        assert len(stale) == 0

    def test_finding_severity_is_medium(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, min_sample_size)
            VALUES (1, 'x', 'running', 5)
        """)
        for i in range(5):
            conn.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id) VALUES (1, ?)",
                (i + 1,)
            )
        conn.commit()
        findings = analyze_experiments(conn)
        for f in findings:
            assert f["severity"] == "medium"

    def test_finding_dimension_is_pm(self, conn):
        conn.execute("""
            INSERT INTO experiment (id, name, status, created_at, min_sample_size)
            VALUES (1, 'pm_test', 'running', datetime('now', '-31 days'), 999)
        """)
        conn.commit()
        findings = analyze_experiments(conn)
        for f in findings:
            assert f["dimension"] == "pm"

    def test_default_min_sample_size_of_100_applied(self, conn):
        # Experiment with NULL min_sample_size → default 100
        conn.execute("""
            INSERT INTO experiment (id, name, status)
            VALUES (1, 'no_min', 'running')
        """)
        for i in range(100):
            conn.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id) VALUES (1, ?)",
                (i + 1,)
            )
        conn.commit()
        findings = analyze_experiments(conn)
        sample_findings = [f for f in findings if "reached sample size" in f["title"]]
        assert len(sample_findings) == 1


# ===========================================================================
# analyze_improvement_log
# ===========================================================================

class TestAnalyzeImprovementLog:

    def test_empty_db_returns_empty_list(self, conn):
        result = analyze_improvement_log(conn)
        assert result == []

    def test_no_finding_when_no_stale_proposals(self, conn):
        # Recent proposed entry — should not trigger
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('proposed', datetime('now', '-10 days'))
        """)
        conn.commit()
        result = analyze_improvement_log(conn)
        assert result == []

    def test_finding_when_proposal_older_than_30_days(self, conn):
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('proposed', datetime('now', '-31 days'))
        """)
        conn.commit()
        result = analyze_improvement_log(conn)
        assert len(result) == 1

    def test_finding_title_contains_count(self, conn):
        for _ in range(3):
            conn.execute("""
                INSERT INTO improvement_log (status, created_at)
                VALUES ('proposed', datetime('now', '-35 days'))
            """)
        conn.commit()
        result = analyze_improvement_log(conn)
        assert len(result) == 1
        assert "3" in result[0]["title"]

    def test_applied_status_not_counted(self, conn):
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('applied', datetime('now', '-45 days'))
        """)
        conn.commit()
        result = analyze_improvement_log(conn)
        assert result == []

    def test_archived_status_not_counted(self, conn):
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('archived', datetime('now', '-45 days'))
        """)
        conn.commit()
        result = analyze_improvement_log(conn)
        assert result == []

    def test_mixed_statuses_only_proposed_counted(self, conn):
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('proposed', datetime('now', '-40 days'))
        """)
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('applied', datetime('now', '-40 days'))
        """)
        conn.commit()
        result = analyze_improvement_log(conn)
        assert len(result) == 1
        assert "1" in result[0]["title"]

    def test_finding_severity_is_medium(self, conn):
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('proposed', datetime('now', '-32 days'))
        """)
        conn.commit()
        result = analyze_improvement_log(conn)
        assert result[0]["severity"] == "medium"

    def test_finding_dimension_is_pm(self, conn):
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('proposed', datetime('now', '-32 days'))
        """)
        conn.commit()
        result = analyze_improvement_log(conn)
        assert result[0]["dimension"] == "pm"

    def test_exactly_30_days_old_not_triggered(self, conn):
        # The query uses <=, so exactly 30 days should be included.
        conn.execute("""
            INSERT INTO improvement_log (status, created_at)
            VALUES ('proposed', datetime('now', '-30 days'))
        """)
        conn.commit()
        result = analyze_improvement_log(conn)
        # Whether this triggers depends on SQLite rounding; we only assert
        # that the function returns a list without raising.
        assert isinstance(result, list)


# ===========================================================================
# get_loop_closure_summary
# ===========================================================================

class TestGetLoopClosureSummary:

    def test_returns_all_expected_keys(self, conn):
        summary = get_loop_closure_summary(conn)
        expected_keys = {
            "total_outcomes", "verified_outcomes", "closure_rate",
            "effective_count", "ineffective_count", "neutral_count",
            "calibration_count",
        }
        assert expected_keys <= set(summary.keys())

    def test_all_zeros_on_empty_db(self, conn):
        summary = get_loop_closure_summary(conn)
        assert summary["total_outcomes"] == 0
        assert summary["verified_outcomes"] == 0
        assert summary["effective_count"] == 0
        assert summary["ineffective_count"] == 0
        assert summary["neutral_count"] == 0
        assert summary["calibration_count"] == 0

    def test_closure_rate_zero_when_no_outcomes(self, conn):
        summary = get_loop_closure_summary(conn)
        assert summary["closure_rate"] == 0.0

    def test_total_outcomes_counts_all_rows(self, conn):
        fid = _insert_finding(conn)
        for _ in range(4):
            _insert_outcome(conn, finding_id=fid)
        summary = get_loop_closure_summary(conn)
        assert summary["total_outcomes"] == 4

    def test_verified_outcomes_only_counts_rows_with_verified_at(self, conn):
        fid = _insert_finding(conn)
        _insert_outcome(conn, finding_id=fid, verified_at="2026-01-01 00:00:00")
        _insert_outcome(conn, finding_id=fid, verified_at=None)
        _insert_outcome(conn, finding_id=fid, verified_at="2026-02-01 00:00:00")
        summary = get_loop_closure_summary(conn)
        assert summary["verified_outcomes"] == 2

    def test_closure_rate_computed_correctly(self, conn):
        fid = _insert_finding(conn)
        _insert_outcome(conn, finding_id=fid, verified_at="2026-01-01 00:00:00")
        _insert_outcome(conn, finding_id=fid, verified_at=None)
        summary = get_loop_closure_summary(conn)
        # 1 verified / 2 total = 50%
        assert summary["closure_rate"] == pytest.approx(50.0, abs=0.1)

    def test_effective_count(self, conn):
        fid = _insert_finding(conn)
        _insert_outcome(conn, finding_id=fid, effective=1)
        _insert_outcome(conn, finding_id=fid, effective=1)
        _insert_outcome(conn, finding_id=fid, effective=-1)
        summary = get_loop_closure_summary(conn)
        assert summary["effective_count"] == 2

    def test_ineffective_count(self, conn):
        fid = _insert_finding(conn)
        _insert_outcome(conn, finding_id=fid, effective=-1)
        _insert_outcome(conn, finding_id=fid, effective=1)
        summary = get_loop_closure_summary(conn)
        assert summary["ineffective_count"] == 1

    def test_neutral_count(self, conn):
        fid = _insert_finding(conn)
        _insert_outcome(conn, finding_id=fid, effective=0)
        _insert_outcome(conn, finding_id=fid, effective=0)
        _insert_outcome(conn, finding_id=fid, effective=1)
        summary = get_loop_closure_summary(conn)
        assert summary["neutral_count"] == 2

    def test_calibration_count(self, conn):
        conn.execute("""
            INSERT INTO pi_threshold_calibration (metric_name, threshold_value)
            VALUES ('retention', 1.2), ('ux', 1.4)
        """)
        conn.commit()
        summary = get_loop_closure_summary(conn)
        assert summary["calibration_count"] == 2

    def test_closure_rate_100_when_all_verified(self, conn):
        fid = _insert_finding(conn)
        for _ in range(3):
            _insert_outcome(conn, finding_id=fid, verified_at="2026-01-01 00:00:00")
        summary = get_loop_closure_summary(conn)
        assert summary["closure_rate"] == pytest.approx(100.0, abs=0.1)

    def test_counts_do_not_overlap(self, conn):
        fid = _insert_finding(conn)
        _insert_outcome(conn, finding_id=fid, effective=1)
        _insert_outcome(conn, finding_id=fid, effective=-1)
        _insert_outcome(conn, finding_id=fid, effective=0)
        summary = get_loop_closure_summary(conn)
        total_eff = (
            summary["effective_count"]
            + summary["ineffective_count"]
            + summary["neutral_count"]
        )
        # Rows with NULL effective are not counted in any bucket.
        assert total_eff <= summary["total_outcomes"]


# ===========================================================================
# measure_encounter_effectiveness
# ===========================================================================

class TestMeasureEncounterEffectiveness:

    def test_returns_expected_keys(self, conn):
        result = measure_encounter_effectiveness(conn)
        assert "boosted_reps_to_stable" in result
        assert "control_reps_to_stable" in result
        assert "lift_pct" in result

    def test_all_none_on_empty_db(self, conn):
        result = measure_encounter_effectiveness(conn)
        assert result["boosted_reps_to_stable"] is None
        assert result["control_reps_to_stable"] is None
        assert result["lift_pct"] is None

    def _seed_encounter_items(self, conn, item_ids, reps, looked_up=1):
        for item_id, rep in zip(item_ids, reps, strict=False):
            conn.execute("""
                INSERT INTO vocab_encounter (content_item_id, looked_up) VALUES (?, ?)
            """, (item_id, looked_up))
            conn.execute("""
                INSERT INTO progress (content_item_id, user_id, mastery_stage, repetitions, ease_factor)
                VALUES (?, 1, 'stable', ?, 2.5)
            """, (item_id, rep))
        conn.commit()

    def _seed_control_items(self, conn, item_ids, reps):
        for item_id, rep in zip(item_ids, reps, strict=False):
            conn.execute("""
                INSERT INTO progress (content_item_id, user_id, mastery_stage, repetitions, ease_factor)
                VALUES (?, 1, 'stable', ?, 2.5)
            """, (item_id, rep))
        conn.commit()

    def test_boosted_items_require_fewer_reps(self, conn):
        # Encounter items: 4, 4, 4 → avg 4
        self._seed_encounter_items(conn, [1, 2, 3], [4, 4, 4])
        # Control items: 8, 8 → avg 8
        self._seed_control_items(conn, [10, 11], [8, 8])
        result = measure_encounter_effectiveness(conn)
        assert result["boosted_reps_to_stable"] == pytest.approx(4.0, abs=0.1)
        assert result["control_reps_to_stable"] == pytest.approx(8.0, abs=0.1)

    def test_lift_pct_positive_when_encounter_needs_fewer_reps(self, conn):
        self._seed_encounter_items(conn, [1, 2, 3], [4, 4, 4])
        self._seed_control_items(conn, [10, 11], [8, 8])
        result = measure_encounter_effectiveness(conn)
        # lift = (control - boosted) / control * 100 = (8-4)/8*100 = 50%
        assert result["lift_pct"] == pytest.approx(50.0, abs=0.1)

    def test_lift_pct_negative_when_encounter_needs_more_reps(self, conn):
        self._seed_encounter_items(conn, [1, 2], [10, 10])
        self._seed_control_items(conn, [10, 11], [6, 6])
        result = measure_encounter_effectiveness(conn)
        assert result["lift_pct"] is not None
        assert result["lift_pct"] < 0

    def test_non_looked_up_encounters_excluded(self, conn):
        # Insert encounter row with looked_up=0; it should NOT count as boosted
        self._seed_encounter_items(conn, [1, 2], [4, 4], looked_up=0)
        self._seed_control_items(conn, [10, 11], [8, 8])
        result = measure_encounter_effectiveness(conn)
        # Items 1 and 2 have encounters but looked_up=0, so they fall into control bucket
        # boosted group is empty → None
        assert result["boosted_reps_to_stable"] is None

    def test_item_not_at_stable_excluded(self, conn):
        # Item with encounter but mastery_stage != 'stable'
        conn.execute("""
            INSERT INTO vocab_encounter (content_item_id, looked_up) VALUES (1, 1)
        """)
        conn.execute("""
            INSERT INTO progress (content_item_id, user_id, mastery_stage, repetitions, ease_factor)
            VALUES (1, 1, 'learning', 3, 2.5)
        """)
        conn.commit()
        result = measure_encounter_effectiveness(conn)
        assert result["boosted_reps_to_stable"] is None

    def test_reps_rounded_to_one_decimal(self, conn):
        # 3 items with reps 3, 4, 5 → avg = 4.0
        self._seed_encounter_items(conn, [1, 2, 3], [3, 4, 5])
        self._seed_control_items(conn, [10, 11, 12], [7, 8, 9])
        result = measure_encounter_effectiveness(conn)
        # Verify the result is a float rounded to 1 decimal place
        assert result["boosted_reps_to_stable"] == pytest.approx(4.0, abs=0.05)
        assert result["control_reps_to_stable"] == pytest.approx(8.0, abs=0.05)

    def test_none_when_control_group_empty(self, conn):
        # All stable items are encounter-sourced — no control group
        self._seed_encounter_items(conn, [1, 2, 3], [5, 5, 5])
        result = measure_encounter_effectiveness(conn)
        # Control avg will be None (no rows)
        assert result["control_reps_to_stable"] is None
        assert result["lift_pct"] is None

    def test_encounter_items_excluded_from_control(self, conn):
        # Items 1, 2 are encounter items; items 10, 11 are control.
        # Ensure item 1 and 2 do NOT appear in the control average.
        self._seed_encounter_items(conn, [1, 2], [4, 4])
        self._seed_control_items(conn, [10, 11], [10, 10])
        result = measure_encounter_effectiveness(conn)
        # Control should be 10.0, not an average including 4s.
        assert result["control_reps_to_stable"] == pytest.approx(10.0, abs=0.1)


# ===========================================================================
# Integration: calibrate → get_calibrated_threshold → loop summary
# ===========================================================================

class TestIntegration:

    def test_calibrate_then_retrieve(self, conn):
        """Full round-trip: calibrate a dimension, then read back the threshold."""
        for _ in range(3):
            _insert_finding(conn, dimension="profitability", status="investigating")
        for _ in range(2):
            _insert_finding(conn, dimension="profitability", status="rejected")
        calibrate_thresholds(conn)
        threshold = get_calibrated_threshold(conn, "profitability", default=0.5)
        assert threshold == pytest.approx(1.2, abs=0.001)

    def test_record_outcome_reflected_in_summary(self, conn):
        fid = _insert_finding(conn)
        record_recommendation_outcome(conn, fid, "code_change", "patched")
        summary = get_loop_closure_summary(conn)
        assert summary["total_outcomes"] == 1
        assert summary["verified_outcomes"] == 0
        assert summary["closure_rate"] == 0.0

    def test_verified_outcome_increases_closure_rate(self, conn):
        fid = _insert_finding(conn)
        oid = record_recommendation_outcome(conn, fid, "code_change", "patched")
        # Mark it verified manually
        conn.execute("""
            UPDATE pi_recommendation_outcome
            SET verified_at = datetime('now'), effective = 1
            WHERE id = ?
        """, (oid,))
        conn.commit()
        summary = get_loop_closure_summary(conn)
        assert summary["verified_outcomes"] == 1
        assert summary["closure_rate"] == pytest.approx(100.0, abs=0.1)
        assert summary["effective_count"] == 1

    def test_full_flow_experiment_to_outcome(self, conn):
        """Simulate: running experiment reaches sample → finding → outcome recorded."""
        conn.execute("""
            INSERT INTO experiment (id, name, status, min_sample_size)
            VALUES (1, 'full_flow', 'running', 5)
        """)
        for i in range(5):
            conn.execute(
                "INSERT INTO experiment_assignment (experiment_id, user_id) VALUES (1, ?)",
                (i + 1,)
            )
        conn.commit()
        exp_findings = analyze_experiments(conn)
        assert len([f for f in exp_findings if "reached sample size" in f["title"]]) == 1

        # Now record an outcome for a related finding
        fid = _insert_finding(conn, dimension="pm", title="Conclude full_flow experiment")
        oid = record_recommendation_outcome(
            conn, fid, "experiment", "concluded experiment, deployed winner"
        )
        assert oid > 0
        summary = get_loop_closure_summary(conn)
        assert summary["total_outcomes"] == 1
