"""Tests for mandarin.intelligence.finding_lifecycle.

Covers: deduplicate_findings, transition_finding, attach_hypothesis,
tag_root_cause, compute_engine_accuracy, check_stale_findings,
check_regression — both positive and negative cases.
"""

import sqlite3
from datetime import datetime, timedelta, timezone, UTC

import pytest

from mandarin.intelligence.finding_lifecycle import (
    attach_hypothesis,
    check_regression,
    check_stale_findings,
    compute_engine_accuracy,
    deduplicate_findings,
    tag_root_cause,
    transition_finding,
)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE product_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT DEFAULT (datetime('now')),
    overall_grade TEXT,
    overall_score REAL,
    dimension_scores TEXT,
    findings_json TEXT,
    findings_count INTEGER,
    critical_count INTEGER DEFAULT 0,
    high_count INTEGER DEFAULT 0
);

CREATE TABLE pi_finding (
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

CREATE TABLE pi_prediction_ledger (
    id TEXT PRIMARY KEY,
    finding_id INTEGER NOT NULL,
    model_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    claim_type TEXT NOT NULL DEFAULT 'metric_will_improve',
    metric_name TEXT NOT NULL,
    metric_baseline REAL,
    predicted_delta REAL NOT NULL,
    predicted_delta_confidence REAL NOT NULL,
    verification_window_days INTEGER NOT NULL,
    verification_due_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    outcome_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE pi_model_confidence (
    model_id TEXT PRIMARY KEY,
    dimension TEXT,
    correct_count INTEGER DEFAULT 0,
    directionally_correct_count INTEGER DEFAULT 0,
    wrong_count INTEGER DEFAULT 0,
    insufficient_data_count INTEGER DEFAULT 0,
    measurement_failure_count INTEGER DEFAULT 0,
    current_confidence REAL DEFAULT 0.5,
    last_updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE pi_recommendation_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    action_type TEXT,
    action_description TEXT,
    files_changed TEXT,
    commit_hash TEXT,
    metric_before TEXT,
    metric_after TEXT,
    verified_at TEXT,
    delta_pct REAL,
    effective INTEGER
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """In-memory SQLite connection with the three PI tables."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_DDL)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def conn_with_audit(conn):
    """Connection that already has one product_audit row (id=1)."""
    conn.execute(
        "INSERT INTO product_audit (overall_grade, overall_score, findings_count) "
        "VALUES ('B', 82.0, 0)"
    )
    conn.commit()
    return conn


def _insert_finding(conn, **kwargs):
    """Helper: insert a pi_finding row and return its id."""
    defaults = dict(
        audit_id=None,
        dimension="ux",
        severity="medium",
        title="Test finding",
        analysis="Some analysis",
        status="investigating",
        metric_name=None,
        metric_value_at_detection=None,
        times_seen=1,
        last_seen_audit_id=None,
        resolved_at=None,
        resolution_notes=None,
        created_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        updated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
    )
    defaults.update(kwargs)
    cur = conn.execute("""
        INSERT INTO pi_finding
            (audit_id, dimension, severity, title, analysis, status,
             metric_name, metric_value_at_detection, times_seen,
             last_seen_audit_id, resolved_at, resolution_notes,
             created_at, updated_at)
        VALUES
            (:audit_id, :dimension, :severity, :title, :analysis, :status,
             :metric_name, :metric_value_at_detection, :times_seen,
             :last_seen_audit_id, :resolved_at, :resolution_notes,
             :created_at, :updated_at)
    """, defaults)
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# deduplicate_findings
# ---------------------------------------------------------------------------

class TestDeduplicateFindings:

    def test_new_finding_is_inserted_and_returned(self, conn_with_audit):
        """A finding with no prior match is inserted and returned as genuinely new."""
        findings = [{"dimension": "retention", "severity": "high", "title": "Drop-off at step 3"}]
        result = deduplicate_findings(conn_with_audit, findings)

        assert len(result) == 1
        assert result[0]["title"] == "Drop-off at step 3"

        row = conn_with_audit.execute(
            "SELECT * FROM pi_finding WHERE title = 'Drop-off at step 3'"
        ).fetchone()
        assert row is not None
        assert row["dimension"] == "retention"
        assert row["severity"] == "high"
        assert row["status"] == "investigating"
        assert row["times_seen"] == 1

    def test_duplicate_increments_times_seen_and_not_returned(self, conn_with_audit):
        """An existing open finding with the same (dimension, title) is updated, not re-inserted."""
        _insert_finding(conn_with_audit, dimension="ux", title="Slow load", times_seen=1)

        findings = [{"dimension": "ux", "title": "Slow load", "severity": "medium"}]
        result = deduplicate_findings(conn_with_audit, findings)

        assert result == []  # not genuinely new

        row = conn_with_audit.execute(
            "SELECT times_seen FROM pi_finding WHERE dimension='ux' AND title='Slow load'"
        ).fetchone()
        assert row["times_seen"] == 2

    def test_multiple_increments_accumulate(self, conn_with_audit):
        """Calling deduplicate twice on the same finding increments times_seen each time."""
        _insert_finding(conn_with_audit, dimension="ux", title="Slow load", times_seen=1)

        findings = [{"dimension": "ux", "title": "Slow load", "severity": "medium"}]
        deduplicate_findings(conn_with_audit, findings)
        deduplicate_findings(conn_with_audit, findings)

        row = conn_with_audit.execute(
            "SELECT times_seen FROM pi_finding WHERE dimension='ux' AND title='Slow load'"
        ).fetchone()
        assert row["times_seen"] == 3

    def test_resolved_finding_treated_as_new(self, conn_with_audit):
        """A finding whose prior match is resolved is treated as new and inserted."""
        _insert_finding(
            conn_with_audit,
            dimension="retention",
            title="Churn spike",
            status="resolved",
        )

        findings = [{"dimension": "retention", "title": "Churn spike", "severity": "high"}]
        result = deduplicate_findings(conn_with_audit, findings)

        assert len(result) == 1  # new row was inserted
        count = conn_with_audit.execute(
            "SELECT COUNT(*) FROM pi_finding WHERE dimension='retention' AND title='Churn spike'"
        ).fetchone()[0]
        assert count == 2  # original resolved + new investigating

    def test_rejected_finding_treated_as_new(self, conn_with_audit):
        """A finding whose prior match is rejected is treated as new."""
        _insert_finding(
            conn_with_audit,
            dimension="content",
            title="Wrong pinyin",
            status="rejected",
        )

        findings = [{"dimension": "content", "title": "Wrong pinyin", "severity": "low"}]
        result = deduplicate_findings(conn_with_audit, findings)

        assert len(result) == 1

    def test_different_dimension_treated_as_new(self, conn_with_audit):
        """Same title but different dimension → new insertion."""
        _insert_finding(conn_with_audit, dimension="ux", title="Error message unclear")

        findings = [{"dimension": "content", "title": "Error message unclear", "severity": "low"}]
        result = deduplicate_findings(conn_with_audit, findings)

        assert len(result) == 1

    def test_empty_input_returns_empty(self, conn_with_audit):
        result = deduplicate_findings(conn_with_audit, [])
        assert result == []

    def test_mixed_batch_splits_new_and_duplicate(self, conn_with_audit):
        """Batch with both a duplicate and a genuinely new finding."""
        _insert_finding(conn_with_audit, dimension="ux", title="Existing finding")

        findings = [
            {"dimension": "ux", "title": "Existing finding", "severity": "low"},
            {"dimension": "retention", "title": "Brand new finding", "severity": "high"},
        ]
        result = deduplicate_findings(conn_with_audit, findings)

        assert len(result) == 1
        assert result[0]["title"] == "Brand new finding"

    def test_new_finding_linked_to_latest_audit(self, conn_with_audit):
        """Newly inserted finding's last_seen_audit_id matches the most recent audit."""
        findings = [{"dimension": "onboarding", "title": "Confusing step 1", "severity": "medium"}]
        deduplicate_findings(conn_with_audit, findings)

        row = conn_with_audit.execute(
            "SELECT last_seen_audit_id FROM pi_finding WHERE title='Confusing step 1'"
        ).fetchone()
        assert row["last_seen_audit_id"] == 1  # audit id inserted in conn_with_audit

    def test_no_audit_table_still_inserts(self, conn):
        """With no product_audit rows, deduplicate still inserts findings (audit_id=None)."""
        findings = [{"dimension": "security", "title": "Missing auth check", "severity": "critical"}]
        result = deduplicate_findings(conn, findings)

        assert len(result) == 1
        row = conn.execute("SELECT audit_id FROM pi_finding WHERE title='Missing auth check'").fetchone()
        assert row is not None
        assert row["audit_id"] is None

    def test_metric_name_defaults_to_dimension(self, conn_with_audit):
        """When no metric_name is given, it defaults to the dimension value."""
        findings = [{"dimension": "performance", "title": "Slow API", "severity": "high"}]
        deduplicate_findings(conn_with_audit, findings)

        row = conn_with_audit.execute(
            "SELECT metric_name FROM pi_finding WHERE title='Slow API'"
        ).fetchone()
        assert row["metric_name"] == "performance"


# ---------------------------------------------------------------------------
# transition_finding
# ---------------------------------------------------------------------------

class TestTransitionFinding:

    # -- Valid forward transitions -------------------------------------------

    def test_investigating_to_diagnosed(self, conn):
        fid = _insert_finding(conn, status="investigating")
        assert transition_finding(conn, fid, "diagnosed") is True
        row = conn.execute("SELECT status FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["status"] == "diagnosed"

    def test_diagnosed_to_recommended(self, conn):
        fid = _insert_finding(conn, status="diagnosed")
        assert transition_finding(conn, fid, "recommended") is True

    def test_recommended_to_implemented(self, conn):
        fid = _insert_finding(conn, status="recommended")
        # Enforcement gate requires a prediction record before marking implemented
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status, created_at)
            VALUES ('pred-test', ?, 'test_model', 'ux', 'metric_will_improve', 'ux_score',
                    50.0, 5.0, 0.7, 7,
                    datetime('now', '+7 days'), 'pending', datetime('now'))
        """, (fid,))
        conn.commit()
        assert transition_finding(conn, fid, "implemented") is True

    def test_implemented_to_verified(self, conn):
        fid = _insert_finding(conn, status="implemented")
        assert transition_finding(conn, fid, "verified") is True

    def test_verified_to_resolved(self, conn):
        fid = _insert_finding(conn, status="verified")
        assert transition_finding(conn, fid, "resolved") is True

    def test_resolved_to_investigating_regression(self, conn):
        """Regression path: resolved → investigating."""
        fid = _insert_finding(conn, status="resolved")
        assert transition_finding(conn, fid, "investigating") is True
        row = conn.execute("SELECT status FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["status"] == "investigating"

    def test_verified_to_investigating_regression(self, conn):
        """Regression path: verified → investigating."""
        fid = _insert_finding(conn, status="verified")
        assert transition_finding(conn, fid, "investigating") is True

    # -- Rejection from states that allow it --------------------------------

    @pytest.mark.parametrize("from_status", [
        "investigating", "diagnosed", "recommended", "implemented",
    ])
    def test_states_that_allow_rejection(self, conn, from_status):
        """investigating/diagnosed/recommended/implemented all permit → rejected."""
        fid = _insert_finding(conn, status=from_status)
        assert transition_finding(conn, fid, "rejected") is True
        row = conn.execute("SELECT status FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["status"] == "rejected"

    def test_verified_to_rejected_invalid(self, conn):
        """verified only allows resolved or investigating (regression) — not rejected."""
        fid = _insert_finding(conn, status="verified")
        assert transition_finding(conn, fid, "rejected") is False
        row = conn.execute("SELECT status FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["status"] == "verified"  # unchanged

    # -- Invalid transitions -------------------------------------------------

    def test_investigating_to_recommended_invalid(self, conn):
        fid = _insert_finding(conn, status="investigating")
        assert transition_finding(conn, fid, "recommended") is False
        row = conn.execute("SELECT status FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["status"] == "investigating"  # unchanged

    def test_investigating_to_verified_invalid(self, conn):
        fid = _insert_finding(conn, status="investigating")
        assert transition_finding(conn, fid, "verified") is False

    def test_diagnosed_to_investigating_invalid(self, conn):
        fid = _insert_finding(conn, status="diagnosed")
        assert transition_finding(conn, fid, "investigating") is False

    def test_diagnosed_to_verified_invalid(self, conn):
        fid = _insert_finding(conn, status="diagnosed")
        assert transition_finding(conn, fid, "verified") is False

    def test_recommended_to_investigating_invalid(self, conn):
        fid = _insert_finding(conn, status="recommended")
        assert transition_finding(conn, fid, "investigating") is False

    def test_implemented_to_diagnosed_invalid(self, conn):
        fid = _insert_finding(conn, status="implemented")
        assert transition_finding(conn, fid, "diagnosed") is False

    def test_rejected_is_terminal(self, conn):
        """Rejected is a terminal state — no further transitions allowed."""
        fid = _insert_finding(conn, status="rejected")
        assert transition_finding(conn, fid, "investigating") is False
        assert transition_finding(conn, fid, "resolved") is False

    def test_nonexistent_finding_returns_false(self, conn):
        assert transition_finding(conn, 9999, "diagnosed") is False

    # -- Notes and resolved_at fields ---------------------------------------

    def test_resolution_notes_set_on_transition(self, conn):
        fid = _insert_finding(conn, status="verified")
        transition_finding(conn, fid, "resolved", notes="Root fix confirmed in prod")
        row = conn.execute("SELECT resolution_notes FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["resolution_notes"] == "Root fix confirmed in prod"

    def test_resolved_at_set_when_transitioning_to_resolved(self, conn):
        fid = _insert_finding(conn, status="verified")
        transition_finding(conn, fid, "resolved")
        row = conn.execute("SELECT resolved_at FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["resolved_at"] is not None

    def test_resolved_at_not_set_for_non_resolved_transition(self, conn):
        fid = _insert_finding(conn, status="investigating")
        transition_finding(conn, fid, "diagnosed")
        row = conn.execute("SELECT resolved_at FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["resolved_at"] is None

    def test_updated_at_changes_on_transition(self, conn):
        old_ts = "2020-01-01 00:00:00"
        fid = _insert_finding(conn, status="investigating", updated_at=old_ts)
        transition_finding(conn, fid, "diagnosed")
        row = conn.execute("SELECT updated_at FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["updated_at"] != old_ts


# ---------------------------------------------------------------------------
# attach_hypothesis
# ---------------------------------------------------------------------------

class TestAttachHypothesis:

    def test_sets_hypothesis_and_falsification(self, conn):
        fid = _insert_finding(conn)
        result = attach_hypothesis(
            conn, fid,
            hypothesis="Users drop because the form is confusing",
            falsification="A/B test shows no difference after simplification",
        )
        assert result is True

        row = conn.execute("SELECT hypothesis, falsification FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["hypothesis"] == "Users drop because the form is confusing"
        assert row["falsification"] == "A/B test shows no difference after simplification"

    def test_overwrites_existing_hypothesis(self, conn):
        fid = _insert_finding(conn)
        attach_hypothesis(conn, fid, "Old hypothesis", "Old falsification")
        attach_hypothesis(conn, fid, "New hypothesis", "New falsification")

        row = conn.execute("SELECT hypothesis FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["hypothesis"] == "New hypothesis"

    def test_updated_at_changes(self, conn):
        old_ts = "2020-01-01 00:00:00"
        fid = _insert_finding(conn, updated_at=old_ts)
        attach_hypothesis(conn, fid, "Some hypothesis", "Some falsification")

        row = conn.execute("SELECT updated_at FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["updated_at"] != old_ts

    def test_returns_true_for_nonexistent_id(self, conn):
        """attach_hypothesis uses a blind UPDATE — returns True even if no row matched."""
        result = attach_hypothesis(conn, 9999, "h", "f")
        assert result is True  # no error raised, UPDATE affects 0 rows silently

    def test_empty_strings_are_accepted(self, conn):
        fid = _insert_finding(conn)
        result = attach_hypothesis(conn, fid, "", "")
        assert result is True
        row = conn.execute("SELECT hypothesis, falsification FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["hypothesis"] == ""
        assert row["falsification"] == ""


# ---------------------------------------------------------------------------
# tag_root_cause
# ---------------------------------------------------------------------------

class TestTagRootCause:

    def test_mark_as_root_cause(self, conn):
        fid = _insert_finding(conn)
        result = tag_root_cause(conn, fid, is_root=True)

        assert result is True
        row = conn.execute("SELECT root_cause_tag, linked_finding_id FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["root_cause_tag"] == "root_cause"
        assert row["linked_finding_id"] is None  # no link for root causes

    def test_mark_as_symptom_with_link(self, conn):
        root_id = _insert_finding(conn, title="Root issue")
        symptom_id = _insert_finding(conn, title="Downstream symptom")

        result = tag_root_cause(conn, symptom_id, is_root=False, linked_finding_id=root_id)

        assert result is True
        row = conn.execute(
            "SELECT root_cause_tag, linked_finding_id FROM pi_finding WHERE id=?", (symptom_id,)
        ).fetchone()
        assert row["root_cause_tag"] == "symptom"
        assert row["linked_finding_id"] == root_id

    def test_root_cause_clears_linked_finding_id(self, conn):
        """Even if linked_finding_id is passed for a root cause, it should be stored as None."""
        fid = _insert_finding(conn)
        tag_root_cause(conn, fid, is_root=True, linked_finding_id=42)

        row = conn.execute("SELECT linked_finding_id FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["linked_finding_id"] is None

    def test_symptom_without_link_stores_none(self, conn):
        fid = _insert_finding(conn)
        result = tag_root_cause(conn, fid, is_root=False)  # no linked_finding_id

        assert result is True
        row = conn.execute("SELECT linked_finding_id FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["linked_finding_id"] is None

    def test_overwrite_tag(self, conn):
        fid = _insert_finding(conn)
        tag_root_cause(conn, fid, is_root=True)
        tag_root_cause(conn, fid, is_root=False, linked_finding_id=99)

        row = conn.execute("SELECT root_cause_tag FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["root_cause_tag"] == "symptom"

    def test_updated_at_changes(self, conn):
        old_ts = "2020-01-01 00:00:00"
        fid = _insert_finding(conn, updated_at=old_ts)
        tag_root_cause(conn, fid, is_root=True)

        row = conn.execute("SELECT updated_at FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["updated_at"] != old_ts

    def test_returns_true_for_nonexistent_id(self, conn):
        """Blind UPDATE — returns True even if id doesn't exist."""
        result = tag_root_cause(conn, 9999, is_root=True)
        assert result is True


# ---------------------------------------------------------------------------
# compute_engine_accuracy
# ---------------------------------------------------------------------------

class TestComputeEngineAccuracy:

    def test_empty_db_returns_zero_counts(self, conn):
        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["total_findings"] == 0
        assert result["true_positives"] == 0
        assert result["false_positives"] == 0
        assert result["false_positive_rate"] == 0.0
        assert result["per_dimension"] == {}

    def test_total_findings_counted(self, conn):
        _insert_finding(conn, dimension="ux", title="F1", status="investigating")
        _insert_finding(conn, dimension="ux", title="F2", status="diagnosed")
        _insert_finding(conn, dimension="retention", title="F3", status="resolved")

        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["total_findings"] == 3

    def test_true_positives_are_verified_and_resolved(self, conn):
        _insert_finding(conn, title="Verified F", status="verified")
        _insert_finding(conn, title="Resolved F", status="resolved")
        _insert_finding(conn, title="Still open", status="investigating")

        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["true_positives"] == 2

    def test_false_positives_are_rejected(self, conn):
        _insert_finding(conn, title="Rejected 1", status="rejected")
        _insert_finding(conn, title="Rejected 2", status="rejected")
        _insert_finding(conn, title="Valid", status="verified")

        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["false_positives"] == 2

    def test_false_positive_rate_calculation(self, conn):
        for i in range(8):
            _insert_finding(conn, title=f"Valid {i}", status="verified")
        for i in range(2):
            _insert_finding(conn, title=f"Bad {i}", status="rejected")

        result = compute_engine_accuracy(conn, lookback_days=90)
        # 2 rejected out of 10 total = 20%
        assert result["false_positive_rate"] == 20.0

    def test_false_positive_rate_zero_when_no_rejected(self, conn):
        _insert_finding(conn, title="Good finding", status="verified")

        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["false_positive_rate"] == 0.0

    def test_per_dimension_breakdown(self, conn):
        _insert_finding(conn, dimension="ux", title="UX 1", status="verified")
        _insert_finding(conn, dimension="ux", title="UX 2", status="rejected")
        _insert_finding(conn, dimension="retention", title="Ret 1", status="investigating")

        result = compute_engine_accuracy(conn, lookback_days=90)

        assert "ux" in result["per_dimension"]
        assert "retention" in result["per_dimension"]

        ux = result["per_dimension"]["ux"]
        assert ux["total"] == 2
        assert ux["verified"] == 1
        assert ux["rejected"] == 1
        assert ux["fpr"] == 50.0

        ret = result["per_dimension"]["retention"]
        assert ret["total"] == 1
        assert ret["verified"] == 0
        assert ret["rejected"] == 0
        assert ret["fpr"] == 0.0

    def test_lookback_excludes_old_findings(self, conn):
        """Findings older than lookback_days should not be counted."""
        old_ts = (datetime.now(UTC) - timedelta(days=200)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_finding(conn, title="Old finding", status="rejected", created_at=old_ts, updated_at=old_ts)
        _insert_finding(conn, title="Recent finding", status="investigating")

        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["total_findings"] == 1  # only the recent one

    def test_avg_resolution_days_none_when_no_resolved(self, conn):
        _insert_finding(conn, status="investigating")
        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["avg_resolution_days"] is None

    def test_avg_resolution_days_computed(self, conn):
        """Insert a resolved finding with explicit created/resolved timestamps."""
        created = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        resolved = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        fid = _insert_finding(conn, status="resolved", created_at=created, updated_at=resolved)
        conn.execute(
            "UPDATE pi_finding SET resolved_at=? WHERE id=?", (resolved, fid)
        )
        conn.commit()

        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["avg_resolution_days"] is not None
        assert result["avg_resolution_days"] >= 9.0  # ~10 days

    def test_result_keys_present(self, conn):
        result = compute_engine_accuracy(conn)
        expected_keys = {
            "total_findings", "true_positives", "false_positives",
            "false_positive_rate", "avg_resolution_days", "per_dimension",
        }
        assert expected_keys.issubset(result.keys())

    def test_default_lookback_is_ninety_days(self, conn):
        """Default lookback_days=90 — old finding not counted."""
        old_ts = (datetime.now(UTC) - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_finding(conn, title="Old", status="verified", created_at=old_ts, updated_at=old_ts)
        result = compute_engine_accuracy(conn)
        assert result["total_findings"] == 0


# ---------------------------------------------------------------------------
# check_stale_findings
# ---------------------------------------------------------------------------

class TestCheckStaleFindings:

    def test_fresh_findings_not_stale(self, conn):
        """Findings updated recently should not appear as stale."""
        _insert_finding(conn, status="investigating")  # updated_at defaults to now()
        _insert_finding(conn, status="diagnosed")

        result = check_stale_findings(conn)
        assert result == []

    def test_stale_investigating_detected(self, conn):
        """An investigating finding not updated for 15 days is stale."""
        stale_ts = (datetime.now(UTC) - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_finding(
            conn, status="investigating",
            title="Old bug", dimension="ux",
            updated_at=stale_ts, created_at=stale_ts,
        )

        result = check_stale_findings(conn)
        assert len(result) == 1
        assert "Old bug" in result[0]["title"]
        assert result[0]["severity"] == "medium"
        assert result[0]["dimension"] == "pm"

    def test_stale_diagnosed_detected(self, conn):
        """A diagnosed finding not updated for 15 days is also stale."""
        stale_ts = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_finding(
            conn, status="diagnosed",
            title="Diagnosed but stuck",
            updated_at=stale_ts, created_at=stale_ts,
        )

        result = check_stale_findings(conn)
        assert len(result) == 1
        assert "Diagnosed but stuck" in result[0]["title"]

    def test_stale_recommended_not_detected(self, conn):
        """Only investigating/diagnosed are checked — recommended is not stale."""
        stale_ts = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_finding(
            conn, status="recommended",
            title="Recommended but old",
            updated_at=stale_ts, created_at=stale_ts,
        )

        result = check_stale_findings(conn)
        assert result == []

    def test_stale_resolved_not_detected(self, conn):
        stale_ts = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_finding(
            conn, status="resolved",
            title="Long resolved",
            updated_at=stale_ts, created_at=stale_ts,
        )

        result = check_stale_findings(conn)
        assert result == []

    def test_exactly_14_days_is_stale(self, conn):
        """The SQL uses <= datetime('now', '-14 days') — exactly 14 days old IS stale."""
        boundary_ts = (datetime.now(UTC) - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_finding(
            conn, status="investigating",
            title="Borderline finding",
            updated_at=boundary_ts, created_at=boundary_ts,
        )

        result = check_stale_findings(conn)
        assert len(result) == 1

    def test_multiple_stale_findings_all_returned(self, conn):
        stale_ts = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        for i in range(3):
            _insert_finding(
                conn, status="investigating",
                title=f"Stale finding {i}",
                updated_at=stale_ts, created_at=stale_ts,
            )

        result = check_stale_findings(conn)
        assert len(result) == 3

    def test_returns_finding_dicts_with_expected_keys(self, conn):
        stale_ts = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_finding(
            conn, status="investigating",
            title="Key check finding",
            updated_at=stale_ts, created_at=stale_ts,
        )

        result = check_stale_findings(conn)
        assert len(result) == 1
        finding = result[0]
        for key in ("dimension", "severity", "title", "analysis", "recommendation"):
            assert key in finding, f"Missing key: {key}"

    def test_empty_db_returns_empty_list(self, conn):
        assert check_stale_findings(conn) == []


# ---------------------------------------------------------------------------
# check_regression
# ---------------------------------------------------------------------------

class TestCheckRegression:

    def test_no_resolved_findings_returns_empty(self, conn):
        _insert_finding(conn, status="investigating")
        result = check_regression(conn)
        assert result == []

    def test_resolved_with_no_recurrence_returns_empty(self, conn):
        """A resolved finding with no new investigating match should not trigger."""
        resolved_ts = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        fid = _insert_finding(
            conn,
            title="Fixed bug",
            dimension="ux",
            status="resolved",
            created_at=resolved_ts,
            updated_at=resolved_ts,
        )
        conn.execute("UPDATE pi_finding SET resolved_at=? WHERE id=?", (resolved_ts, fid))
        conn.commit()

        result = check_regression(conn)
        assert result == []

    def test_regression_detected_when_same_issue_reappears(self, conn):
        """Resolved finding + new investigating finding with matching dimension+title prefix → regression."""
        resolved_ts = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        recent_ts = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        fid = _insert_finding(
            conn,
            title="Crash on login",
            dimension="reliability",
            status="resolved",
            metric_name="reliability",
            created_at=resolved_ts,
            updated_at=resolved_ts,
        )
        conn.execute("UPDATE pi_finding SET resolved_at=? WHERE id=?", (resolved_ts, fid))
        conn.commit()

        # New investigating finding with same title prefix appearing after resolution
        _insert_finding(
            conn,
            title="Crash on login",
            dimension="reliability",
            status="investigating",
            created_at=recent_ts,
            updated_at=recent_ts,
        )

        result = check_regression(conn)
        assert len(result) == 1
        assert "Crash on login" in result[0]["title"]
        assert result[0]["severity"] == "high"
        assert result[0]["dimension"] == "reliability"

    def test_regression_reopens_resolved_finding(self, conn):
        """When regression is detected, the resolved finding's status is set to investigating."""
        resolved_ts = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        recent_ts = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        fid = _insert_finding(
            conn,
            title="Duplicate word shown",
            dimension="content",
            status="resolved",
            metric_name="content",
            created_at=resolved_ts,
            updated_at=resolved_ts,
        )
        conn.execute("UPDATE pi_finding SET resolved_at=? WHERE id=?", (resolved_ts, fid))
        conn.commit()

        _insert_finding(
            conn,
            title="Duplicate word shown",
            dimension="content",
            status="investigating",
            created_at=recent_ts,
            updated_at=recent_ts,
        )

        check_regression(conn)

        row = conn.execute("SELECT status FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert row["status"] == "investigating"

    def test_regression_appends_note_to_resolution_notes(self, conn):
        resolved_ts = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        recent_ts = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        fid = _insert_finding(
            conn,
            title="Score mismatch",
            dimension="scoring",
            status="resolved",
            metric_name="scoring",
            resolution_notes="Fixed by patch v1.2",
            created_at=resolved_ts,
            updated_at=resolved_ts,
        )
        conn.execute("UPDATE pi_finding SET resolved_at=? WHERE id=?", (resolved_ts, fid))
        conn.commit()

        _insert_finding(
            conn,
            title="Score mismatch",
            dimension="scoring",
            status="investigating",
            created_at=recent_ts,
            updated_at=recent_ts,
        )

        check_regression(conn)

        row = conn.execute("SELECT resolution_notes FROM pi_finding WHERE id=?", (fid,)).fetchone()
        assert "[Regression detected]" in row["resolution_notes"]
        assert "Fixed by patch v1.2" in row["resolution_notes"]

    def test_old_resolved_finding_outside_90_days_ignored(self, conn):
        """Resolved findings older than 90 days are not checked for regression."""
        old_ts = (datetime.now(UTC) - timedelta(days=95)).strftime("%Y-%m-%d %H:%M:%S")
        recent_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        fid = _insert_finding(
            conn,
            title="Ancient bug",
            dimension="ux",
            status="resolved",
            metric_name="ux",
            created_at=old_ts,
            updated_at=old_ts,
        )
        conn.execute("UPDATE pi_finding SET resolved_at=? WHERE id=?", (old_ts, fid))
        conn.commit()

        _insert_finding(
            conn,
            title="Ancient bug",
            dimension="ux",
            status="investigating",
            created_at=recent_ts,
            updated_at=recent_ts,
        )

        result = check_regression(conn)
        assert result == []

    def test_resolved_finding_without_metric_name_ignored(self, conn):
        """Findings with no metric_name are excluded from regression detection."""
        resolved_ts = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        recent_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        fid = _insert_finding(
            conn,
            title="No metric finding",
            dimension="ux",
            status="resolved",
            metric_name=None,  # explicitly no metric_name
            created_at=resolved_ts,
            updated_at=resolved_ts,
        )
        conn.execute("UPDATE pi_finding SET resolved_at=? WHERE id=?", (resolved_ts, fid))
        conn.commit()

        _insert_finding(
            conn,
            title="No metric finding",
            dimension="ux",
            status="investigating",
            created_at=recent_ts,
            updated_at=recent_ts,
        )

        result = check_regression(conn)
        assert result == []

    def test_regression_finding_dict_has_expected_keys(self, conn):
        resolved_ts = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
        recent_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        fid = _insert_finding(
            conn,
            title="Regressed issue",
            dimension="retention",
            status="resolved",
            metric_name="retention",
            created_at=resolved_ts,
            updated_at=resolved_ts,
        )
        conn.execute("UPDATE pi_finding SET resolved_at=? WHERE id=?", (resolved_ts, fid))
        conn.commit()

        _insert_finding(
            conn,
            title="Regressed issue",
            dimension="retention",
            status="investigating",
            created_at=recent_ts,
            updated_at=recent_ts,
        )

        result = check_regression(conn)
        assert len(result) == 1
        finding = result[0]
        for key in ("dimension", "severity", "title", "analysis", "recommendation", "files"):
            assert key in finding, f"Missing key: {key}"

    def test_empty_db_returns_empty_list(self, conn):
        assert check_regression(conn) == []
