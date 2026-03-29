"""Integration tests for the Product Intelligence engine API.

Tests the 7 admin API endpoints for the intelligence engine by exercising
the underlying functions directly against an in-memory SQLite database.

Covered flows:
1. Create findings via deduplicate_findings
2. Transition findings through valid and invalid state transitions
3. Record recommendation outcomes
4. Get loop closure summary
5. Run the Mediator advisor system on findings
6. Classify and escalate findings via classify_and_escalate_all
7. Compute engine accuracy meta-analysis
8. Threshold calibration
"""

import json
import sqlite3

import pytest

from tests.shared_db import make_test_db
from mandarin.intelligence.finding_lifecycle import (
    transition_finding,
    deduplicate_findings,
    compute_engine_accuracy,
    attach_hypothesis,
    tag_root_cause,
    check_stale_findings,
)
from mandarin.intelligence.feedback_loops import (
    record_recommendation_outcome,
    get_loop_closure_summary,
    calibrate_thresholds,
    get_calibrated_threshold,
)
from mandarin.intelligence.advisors import Mediator
from mandarin.intelligence.human_loop import classify_and_escalate_all, classify_decision, compute_escalation


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS product_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL DEFAULT (datetime('now')),
    overall_score REAL,
    overall_grade TEXT,
    dimension_scores TEXT,
    finding_count INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    high_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pi_finding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id INTEGER REFERENCES product_audit(id),
    dimension TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'low',
    title TEXT NOT NULL,
    analysis TEXT,
    recommendation TEXT,
    claude_prompt TEXT,
    impact TEXT,
    files TEXT,
    status TEXT NOT NULL DEFAULT 'investigating',
    metric_name TEXT,
    metric_value_at_detection REAL,
    hypothesis TEXT,
    falsification TEXT,
    root_cause_tag TEXT,
    linked_finding_id INTEGER REFERENCES pi_finding(id),
    times_seen INTEGER NOT NULL DEFAULT 1,
    last_seen_audit_id INTEGER REFERENCES product_audit(id),
    resolution_notes TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_recommendation_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES pi_finding(id),
    action_type TEXT NOT NULL,
    action_description TEXT,
    files_changed TEXT,
    metric_before TEXT,
    metric_after TEXT,
    delta_pct REAL,
    effective INTEGER,
    verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES pi_finding(id),
    decision_class TEXT,
    escalation_level TEXT,
    presented_to TEXT,
    decision TEXT,
    decision_reason TEXT,
    override_expires_at TEXT,
    outcome_notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_advisor_opinion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES pi_finding(id),
    advisor TEXT NOT NULL,
    recommendation TEXT,
    priority_score REAL,
    effort_estimate REAL,
    rationale TEXT,
    tradeoff_notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_advisor_resolution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES pi_finding(id),
    winning_advisor TEXT,
    resolution_rationale TEXT,
    tradeoff_summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_threshold_calibration (
    metric_name TEXT PRIMARY KEY,
    threshold_value REAL NOT NULL DEFAULT 1.0,
    calibrated_at TEXT NOT NULL DEFAULT (datetime('now')),
    sample_size INTEGER,
    false_positive_rate REAL,
    false_negative_rate REAL,
    prior_threshold REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS pi_prediction_ledger (
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

CREATE TABLE IF NOT EXISTS pi_model_confidence (
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
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """In-memory SQLite connection with all intelligence tables created."""
    c = make_test_db()
    c.executescript(_DDL)
    c.commit()
    yield c
    c.close()


def _insert_finding(conn, dimension="retention", severity="medium",
                    title="Test finding", analysis="Some analysis",
                    status="investigating", audit_id=None):
    """Helper: insert a pi_finding row directly and return its id."""
    cursor = conn.execute("""
        INSERT INTO pi_finding
            (audit_id, dimension, severity, title, analysis, status, metric_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (audit_id, dimension, severity, title, analysis, status, dimension))
    conn.commit()
    return cursor.lastrowid


def _insert_audit(conn, overall_score=75.0, dimension_scores=None):
    """Helper: insert a product_audit row and return its id."""
    ds = json.dumps(dimension_scores or {})
    cursor = conn.execute("""
        INSERT INTO product_audit (overall_score, overall_grade, dimension_scores, findings_json, findings_count)
        VALUES (?, 'C', ?, '[]', 0)
    """, (overall_score, ds))
    conn.commit()
    return cursor.lastrowid


# ---------------------------------------------------------------------------
# 1. Finding deduplication
# ---------------------------------------------------------------------------

class TestFindingDeduplication:

    def test_new_finding_is_inserted(self, conn):
        findings = [{
            "dimension": "retention",
            "severity": "high",
            "title": "D7 retention below benchmark",
            "analysis": "D7 is 22%, below the 30-40% benchmark.",
        }]
        new = deduplicate_findings(conn, findings)
        assert len(new) == 1

        row = conn.execute("SELECT * FROM pi_finding WHERE title = ?",
                           ("D7 retention below benchmark",)).fetchone()
        assert row is not None
        assert row["dimension"] == "retention"
        assert row["severity"] == "high"
        assert row["status"] == "investigating"
        assert row["times_seen"] == 1

    def test_duplicate_finding_increments_times_seen(self, conn):
        _insert_finding(conn, title="Duplicate finding", dimension="ux", status="investigating")

        findings = [{"dimension": "ux", "severity": "medium", "title": "Duplicate finding"}]
        new = deduplicate_findings(conn, findings)

        # Not genuinely new — existing open finding was updated instead
        assert len(new) == 0

        row = conn.execute(
            "SELECT times_seen FROM pi_finding WHERE title = 'Duplicate finding'"
        ).fetchone()
        assert row["times_seen"] == 2

    def test_resolved_finding_does_not_count_as_duplicate(self, conn):
        _insert_finding(conn, title="Old finding", dimension="ux", status="resolved")

        findings = [{"dimension": "ux", "severity": "low", "title": "Old finding"}]
        new = deduplicate_findings(conn, findings)

        # Resolved finding should not match — a new row should be created
        assert len(new) == 1
        rows = conn.execute(
            "SELECT id FROM pi_finding WHERE title = 'Old finding'"
        ).fetchall()
        assert len(rows) == 2

    def test_multiple_new_findings_all_inserted(self, conn):
        findings = [
            {"dimension": "engineering", "severity": "critical", "title": "Crash on login"},
            {"dimension": "security", "severity": "high", "title": "Brute force risk"},
            {"dimension": "ux", "severity": "low", "title": "Minor layout issue"},
        ]
        new = deduplicate_findings(conn, findings)
        assert len(new) == 3

        count = conn.execute("SELECT COUNT(*) FROM pi_finding").fetchone()[0]
        assert count == 3

    def test_audit_id_is_set_when_audit_exists(self, conn):
        audit_id = _insert_audit(conn)
        findings = [{"dimension": "retention", "severity": "medium", "title": "Audit-linked finding"}]
        deduplicate_findings(conn, findings)

        row = conn.execute(
            "SELECT audit_id FROM pi_finding WHERE title = 'Audit-linked finding'"
        ).fetchone()
        assert row["audit_id"] == audit_id


# ---------------------------------------------------------------------------
# 2. State machine transitions (transition_finding)
# ---------------------------------------------------------------------------

class TestTransitionFinding:

    def test_valid_transition_investigating_to_diagnosed(self, conn):
        fid = _insert_finding(conn, status="investigating")
        result = transition_finding(conn, fid, "diagnosed", notes="Root cause identified.")
        assert result is True
        row = conn.execute("SELECT status FROM pi_finding WHERE id = ?", (fid,)).fetchone()
        assert row["status"] == "diagnosed"

    def test_valid_transition_diagnosed_to_recommended(self, conn):
        fid = _insert_finding(conn, status="diagnosed")
        result = transition_finding(conn, fid, "recommended")
        assert result is True
        row = conn.execute("SELECT status FROM pi_finding WHERE id = ?", (fid,)).fetchone()
        assert row["status"] == "recommended"

    def test_valid_transition_recommended_to_implemented(self, conn):
        fid = _insert_finding(conn, status="recommended")
        # Enforcement gate requires prediction record
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
        result = transition_finding(conn, fid, "implemented")
        assert result is True

    def test_valid_transition_implemented_to_verified(self, conn):
        fid = _insert_finding(conn, status="implemented")
        result = transition_finding(conn, fid, "verified")
        assert result is True

    def test_valid_transition_verified_to_resolved(self, conn):
        fid = _insert_finding(conn, status="verified")
        result = transition_finding(conn, fid, "resolved")
        assert result is True
        row = conn.execute("SELECT status, resolved_at FROM pi_finding WHERE id = ?", (fid,)).fetchone()
        assert row["status"] == "resolved"
        assert row["resolved_at"] is not None

    def test_valid_transition_any_to_rejected(self, conn):
        for status in ("investigating", "diagnosed", "recommended", "implemented"):
            fid = _insert_finding(conn, status=status, title=f"Finding in {status}")
            result = transition_finding(conn, fid, "rejected")
            assert result is True, f"Expected rejected transition from {status} to succeed"

    def test_invalid_transition_investigating_to_resolved(self, conn):
        fid = _insert_finding(conn, status="investigating")
        result = transition_finding(conn, fid, "resolved")
        assert result is False
        row = conn.execute("SELECT status FROM pi_finding WHERE id = ?", (fid,)).fetchone()
        assert row["status"] == "investigating"  # Unchanged

    def test_invalid_transition_rejected_to_anything(self, conn):
        fid = _insert_finding(conn, status="rejected")
        result = transition_finding(conn, fid, "investigating")
        assert result is False

    def test_invalid_transition_diagnosed_to_verified(self, conn):
        fid = _insert_finding(conn, status="diagnosed")
        result = transition_finding(conn, fid, "verified")
        assert result is False

    def test_transition_nonexistent_finding(self, conn):
        result = transition_finding(conn, finding_id=99999, new_status="diagnosed")
        assert result is False

    def test_resolution_notes_saved_on_transition(self, conn):
        fid = _insert_finding(conn, status="investigating")
        transition_finding(conn, fid, "diagnosed", notes="Identified as SRS scheduling bug")
        row = conn.execute(
            "SELECT resolution_notes FROM pi_finding WHERE id = ?", (fid,)
        ).fetchone()
        assert row["resolution_notes"] == "Identified as SRS scheduling bug"

    def test_regression_path_resolved_to_investigating(self, conn):
        fid = _insert_finding(conn, status="resolved")
        result = transition_finding(conn, fid, "investigating", notes="Regression detected")
        assert result is True
        row = conn.execute("SELECT status FROM pi_finding WHERE id = ?", (fid,)).fetchone()
        assert row["status"] == "investigating"

    def test_full_lifecycle_path(self, conn):
        """Walk a finding through the complete happy path."""
        fid = _insert_finding(conn, status="investigating")

        # Insert prediction record (required before implementing)
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status, created_at)
            VALUES ('pred-lifecycle', ?, 'test_model', 'ux', 'metric_will_improve', 'ux_score',
                    50.0, 5.0, 0.7, 7,
                    datetime('now', '+7 days'), 'pending', datetime('now'))
        """, (fid,))
        conn.commit()

        states = ["diagnosed", "recommended", "implemented", "verified", "resolved"]
        for state in states:
            ok = transition_finding(conn, fid, state)
            assert ok is True, f"Transition to {state} failed"

        row = conn.execute("SELECT status, resolved_at FROM pi_finding WHERE id = ?", (fid,)).fetchone()
        assert row["status"] == "resolved"
        assert row["resolved_at"] is not None


# ---------------------------------------------------------------------------
# 3. Hypothesis and root cause tagging
# ---------------------------------------------------------------------------

class TestHypothesisAndRootCause:

    def test_attach_hypothesis(self, conn):
        fid = _insert_finding(conn)
        result = attach_hypothesis(
            conn, fid,
            hypothesis="Users drop off due to too-hard first drills",
            falsification="If we soften first session, D7 goes up by 3pp",
        )
        assert result is True
        row = conn.execute(
            "SELECT hypothesis, falsification FROM pi_finding WHERE id = ?", (fid,)
        ).fetchone()
        assert row["hypothesis"] == "Users drop off due to too-hard first drills"
        assert "3pp" in row["falsification"]

    def test_tag_root_cause_as_root(self, conn):
        fid = _insert_finding(conn)
        result = tag_root_cause(conn, fid, is_root=True)
        assert result is True
        row = conn.execute(
            "SELECT root_cause_tag, linked_finding_id FROM pi_finding WHERE id = ?", (fid,)
        ).fetchone()
        assert row["root_cause_tag"] == "root_cause"
        assert row["linked_finding_id"] is None

    def test_tag_root_cause_as_symptom_with_link(self, conn):
        root_fid = _insert_finding(conn, title="Root cause finding")
        symptom_fid = _insert_finding(conn, title="Symptom finding")
        result = tag_root_cause(conn, symptom_fid, is_root=False, linked_finding_id=root_fid)
        assert result is True
        row = conn.execute(
            "SELECT root_cause_tag, linked_finding_id FROM pi_finding WHERE id = ?",
            (symptom_fid,)
        ).fetchone()
        assert row["root_cause_tag"] == "symptom"
        assert row["linked_finding_id"] == root_fid


# ---------------------------------------------------------------------------
# 4. Recommendation outcomes and feedback loop
# ---------------------------------------------------------------------------

class TestRecommendationOutcomes:

    def test_record_outcome_returns_positive_id(self, conn):
        fid = _insert_finding(conn)
        outcome_id = record_recommendation_outcome(
            conn, fid,
            action_type="code_change",
            description="Reduced first session difficulty",
            files_changed=["mandarin/scheduler.py"],
            metric_before={"value": 22.5, "label": "D7 retention %"},
        )
        assert outcome_id > 0

    def test_outcome_stored_correctly(self, conn):
        fid = _insert_finding(conn)
        outcome_id = record_recommendation_outcome(
            conn, fid,
            action_type="code_change",
            description="Improved button contrast",
            files_changed=["mandarin/web/static/style.css"],
            metric_before={"value": 3, "label": "rage_clicks/day"},
        )
        row = conn.execute(
            "SELECT * FROM pi_recommendation_outcome WHERE id = ?", (outcome_id,)
        ).fetchone()
        assert row["finding_id"] == fid
        assert row["action_type"] == "code_change"
        assert row["action_description"] == "Improved button contrast"

        files = json.loads(row["files_changed"])
        assert "mandarin/web/static/style.css" in files

        before = json.loads(row["metric_before"])
        assert before["value"] == 3

    def test_outcome_with_no_files_or_metric(self, conn):
        fid = _insert_finding(conn)
        outcome_id = record_recommendation_outcome(
            conn, fid,
            action_type="experiment",
            description="Investigated but no action taken",
        )
        assert outcome_id > 0

    def test_multiple_outcomes_for_same_finding(self, conn):
        fid = _insert_finding(conn)
        for i in range(3):
            record_recommendation_outcome(conn, fid, action_type="config_change",
                                          description=f"Iteration {i}")
        count = conn.execute(
            "SELECT COUNT(*) FROM pi_recommendation_outcome WHERE finding_id = ?", (fid,)
        ).fetchone()[0]
        assert count == 3


# ---------------------------------------------------------------------------
# 5. Loop closure summary (GET /api/admin/intelligence/feedback-summary)
# ---------------------------------------------------------------------------

class TestLoopClosureSummary:

    def test_empty_database_returns_zeroes(self, conn):
        summary = get_loop_closure_summary(conn)
        assert summary["total_outcomes"] == 0
        assert summary["verified_outcomes"] == 0
        assert summary["closure_rate"] == 0.0
        assert summary["effective_count"] == 0
        assert summary["ineffective_count"] == 0
        assert summary["neutral_count"] == 0
        assert summary["calibration_count"] == 0

    def test_counts_unverified_outcomes(self, conn):
        fid = _insert_finding(conn)
        record_recommendation_outcome(conn, fid, action_type="code_change", description="Fix A")
        record_recommendation_outcome(conn, fid, action_type="code_change", description="Fix B")

        summary = get_loop_closure_summary(conn)
        assert summary["total_outcomes"] == 2
        assert summary["verified_outcomes"] == 0
        assert summary["closure_rate"] == 0.0

    def test_counts_verified_outcomes(self, conn):
        fid = _insert_finding(conn)
        # One unverified
        record_recommendation_outcome(conn, fid, action_type="code_change", description="Unverified fix")
        # One verified + effective
        outcome_id = record_recommendation_outcome(
            conn, fid, action_type="config_change", description="Verified fix"
        )
        conn.execute("""
            UPDATE pi_recommendation_outcome
            SET verified_at = datetime('now'), effective = 1
            WHERE id = ?
        """, (outcome_id,))
        conn.commit()

        summary = get_loop_closure_summary(conn)
        assert summary["total_outcomes"] == 2
        assert summary["verified_outcomes"] == 1
        assert summary["closure_rate"] == 50.0
        assert summary["effective_count"] == 1

    def test_counts_effective_ineffective_neutral(self, conn):
        fid = _insert_finding(conn)
        for effective_value in (1, -1, 0):
            oid = record_recommendation_outcome(
                conn, fid, action_type="config_change", description=f"Outcome {effective_value}"
            )
            conn.execute("""
                UPDATE pi_recommendation_outcome
                SET verified_at = datetime('now'), effective = ?
                WHERE id = ?
            """, (effective_value, oid))
        conn.commit()

        summary = get_loop_closure_summary(conn)
        assert summary["effective_count"] == 1
        assert summary["ineffective_count"] == 1
        assert summary["neutral_count"] == 1

    def test_calibration_count_reflected(self, conn):
        conn.execute("""
            INSERT INTO pi_threshold_calibration (metric_name, threshold_value)
            VALUES ('retention', 1.2), ('ux', 1.4)
        """)
        conn.commit()

        summary = get_loop_closure_summary(conn)
        assert summary["calibration_count"] == 2


# ---------------------------------------------------------------------------
# 6. Threshold calibration
# ---------------------------------------------------------------------------

class TestThresholdCalibration:

    def test_no_calibration_below_min_sample(self, conn):
        # Only 4 findings per dimension — below HAVING total >= 5
        for i in range(4):
            _insert_finding(
                conn,
                title=f"Finding {i}",
                dimension="retention",
                status="rejected",
            )
        adjustments = calibrate_thresholds(conn)
        assert adjustments == []

    def test_high_fpr_triggers_calibration(self, conn):
        # Insert 6 rejected, 2 verified — FPR = 75% > 25% threshold
        for i in range(6):
            _insert_finding(conn, title=f"Rejected {i}", dimension="ux", status="rejected")
        for i in range(2):
            _insert_finding(conn, title=f"Verified {i}", dimension="ux", status="verified")

        adjustments = calibrate_thresholds(conn)
        assert len(adjustments) == 1
        adj = adjustments[0]
        assert adj["dimension"] == "ux"
        assert adj["fpr"] > 25.0
        assert adj["new"] > 1.0  # Tightened

    def test_calibration_is_persisted(self, conn):
        for i in range(6):
            _insert_finding(conn, title=f"FP {i}", dimension="engineering", status="rejected")
        for i in range(1):
            _insert_finding(conn, title=f"TP {i}", dimension="engineering", status="verified")

        calibrate_thresholds(conn)

        row = conn.execute(
            "SELECT threshold_value FROM pi_threshold_calibration WHERE metric_name = 'engineering'"
        ).fetchone()
        assert row is not None
        assert row["threshold_value"] > 1.0

    def test_get_calibrated_threshold_uses_default(self, conn):
        val = get_calibrated_threshold(conn, "unknown_metric", default=2.5)
        assert val == 2.5

    def test_get_calibrated_threshold_returns_stored(self, conn):
        conn.execute("""
            INSERT INTO pi_threshold_calibration (metric_name, threshold_value)
            VALUES ('security', 1.8)
        """)
        conn.commit()

        val = get_calibrated_threshold(conn, "security")
        assert val == 1.8

    def test_low_fpr_does_not_trigger_calibration(self, conn):
        # Only 1 rejected out of 10 — FPR = 10%, below 25%
        for i in range(9):
            _insert_finding(conn, title=f"Good {i}", dimension="content", status="verified")
        _insert_finding(conn, title="Bad 0", dimension="content", status="rejected")

        adjustments = calibrate_thresholds(conn)
        content_adj = [a for a in adjustments if a["dimension"] == "content"]
        assert content_adj == []


# ---------------------------------------------------------------------------
# 7. Mediator advisor system (GET /api/admin/intelligence/sprint-plan)
# ---------------------------------------------------------------------------

class TestMediator:

    def _make_finding(self, dimension="retention", severity="medium",
                      title="Test finding", files=None):
        return {
            "dimension": dimension,
            "severity": severity,
            "title": title,
            "analysis": f"Analysis for {title}",
            "recommendation": f"Fix {title}",
            "impact": "User impact",
            "files": files or [],
        }

    def test_evaluate_all_returns_opinions_per_finding(self, conn):
        findings = [
            self._make_finding("retention", "high", "Retention drop"),
            self._make_finding("engineering", "critical", "Crash on startup"),
        ]
        # Insert findings so mediator can find them by dimension+title
        for f in findings:
            _insert_finding(conn, dimension=f["dimension"], severity=f["severity"],
                            title=f["title"])

        mediator = Mediator()
        all_opinions = mediator.evaluate_all(conn, findings)

        assert "Retention drop" in all_opinions
        assert "Crash on startup" in all_opinions
        # Each finding should have 4 advisor opinions (retention, learning, growth, stability)
        assert len(all_opinions["Retention drop"]) == 4
        assert len(all_opinions["Crash on startup"]) == 4

    def test_each_opinion_has_required_fields(self, conn):
        finding = self._make_finding("ux", "medium", "Session completion low")
        _insert_finding(conn, dimension="ux", severity="medium", title="Session completion low")

        mediator = Mediator()
        all_opinions = mediator.evaluate_all(conn, [finding])
        opinions = all_opinions["Session completion low"]

        for op in opinions:
            assert "advisor" in op
            assert "priority_score" in op
            assert "effort_estimate" in op
            assert "recommendation" in op
            assert "rationale" in op

    def test_opinions_persisted_to_pi_advisor_opinion(self, conn):
        finding = self._make_finding("drill_quality", "high", "Drill accuracy below target")
        _insert_finding(conn, dimension="drill_quality", severity="high",
                        title="Drill accuracy below target")

        mediator = Mediator()
        mediator.evaluate_all(conn, [finding])

        count = conn.execute(
            "SELECT COUNT(*) FROM pi_advisor_opinion WHERE finding_id IS NOT NULL"
        ).fetchone()[0]
        assert count > 0

    def test_plan_sprint_returns_valid_structure(self, conn):
        findings = [
            self._make_finding("retention", "high", "Sprint item A", files=["mandarin/scheduler.py"]),
            self._make_finding("engineering", "critical", "Sprint item B", files=["mandarin/web/routes.py"]),
            self._make_finding("ux", "low", "Sprint item C", files=[]),
        ]
        for f in findings:
            _insert_finding(conn, dimension=f["dimension"], severity=f["severity"], title=f["title"])

        mediator = Mediator()
        plan = mediator.plan_sprint(conn, findings, weekly_budget_hours=20.0)

        assert "plan" in plan
        assert "total_hours" in plan
        assert "budget_hours" in plan
        assert "remaining_hours" in plan
        assert "deferred_count" in plan
        assert plan["budget_hours"] == 20.0
        assert plan["total_hours"] + plan["remaining_hours"] == pytest.approx(20.0)

    def test_plan_sprint_respects_budget(self, conn):
        # Create many findings that would overflow a tiny budget
        findings = [
            self._make_finding("retention", "high", f"Heavy item {i}",
                               files=["schema.sql", "mandarin/scheduler.py"])
            for i in range(10)
        ]
        for f in findings:
            _insert_finding(conn, dimension=f["dimension"], severity=f["severity"], title=f["title"])

        mediator = Mediator()
        plan = mediator.plan_sprint(conn, findings, weekly_budget_hours=5.0)

        total_effort = sum(item["effort_hours"] for item in plan["plan"])
        assert total_effort <= 5.0

    def test_plan_sprint_sorts_by_priority_descending(self, conn):
        findings = [
            self._make_finding("ux", "low", "Low priority item"),
            self._make_finding("engineering", "critical", "Critical item"),
            self._make_finding("retention", "high", "High priority item"),
        ]
        for f in findings:
            _insert_finding(conn, dimension=f["dimension"], severity=f["severity"], title=f["title"])

        mediator = Mediator()
        plan = mediator.plan_sprint(conn, findings, weekly_budget_hours=40.0)

        if len(plan["plan"]) >= 2:
            for i in range(len(plan["plan"]) - 1):
                assert plan["plan"][i]["priority"] >= plan["plan"][i + 1]["priority"]

    def test_mediator_resolve_consensus(self, conn):
        finding = self._make_finding("retention", "high", "Consensus finding")
        _insert_finding(conn, dimension="retention", severity="high", title="Consensus finding")

        mediator = Mediator()
        from mandarin.intelligence.advisors import _ADVISORS
        opinions = [a.evaluate(finding, conn) for a in _ADVISORS]

        resolution = mediator.resolve(conn, finding, opinions)
        assert "winning_advisor" in resolution
        assert "resolution_rationale" in resolution
        assert "priority" in resolution
        assert resolution["priority"] > 0

    def test_mediator_resolve_empty_opinions(self, conn):
        finding = self._make_finding("ux", "low", "No opinion finding")
        mediator = Mediator()
        resolution = mediator.resolve(conn, finding, [])
        assert resolution["winning_advisor"] is None
        assert resolution["priority"] == 0

    def test_stability_advisor_boosts_critical_findings(self, conn):
        from mandarin.intelligence.advisors import StabilityAdvisor
        advisor = StabilityAdvisor()

        critical = self._make_finding("engineering", "critical", "Critical crash")
        medium = self._make_finding("engineering", "medium", "Medium bug")

        op_critical = advisor.evaluate(critical, conn)
        op_medium = advisor.evaluate(medium, conn)

        # Critical should score higher than medium for stability advisor
        assert op_critical["priority_score"] > op_medium["priority_score"]


# ---------------------------------------------------------------------------
# 8. classify_and_escalate_all (human_loop)
# ---------------------------------------------------------------------------

class TestClassifyAndEscalate:

    def _make_finding(self, dimension="ux", severity="medium", title="Test",
                      analysis="", files=None):
        return {
            "dimension": dimension,
            "severity": severity,
            "title": title,
            "analysis": analysis or f"Analysis: {title}",
            "recommendation": "Fix it",
            "impact": "User impact",
            "files": files or [],
        }

    def test_returns_list_for_empty_findings(self, conn):
        result = classify_and_escalate_all(conn, [])
        assert result == []

    def test_each_item_has_required_fields(self, conn):
        findings = [self._make_finding()]
        result = classify_and_escalate_all(conn, findings)
        assert len(result) == 1
        item = result[0]
        assert "title" in item
        assert "decision_class" in item
        assert "escalation_level" in item
        assert "escalation_order" in item
        assert "context" in item
        assert "finding" in item

    def test_critical_severity_escalates_to_emergency(self, conn):
        finding = self._make_finding("security", "critical", "Critical auth bypass")
        _insert_finding(conn, dimension="security", severity="critical",
                        title="Critical auth bypass")
        result = classify_and_escalate_all(conn, [finding])
        assert result[0]["escalation_level"] == "emergency"

    def test_low_severity_single_file_is_informed_fix(self, conn):
        finding = self._make_finding("ux", "low", "Minor layout tweak",
                                     files=["mandarin/web/static/style.css"])
        result = classify_and_escalate_all(conn, [finding])
        assert result[0]["decision_class"] == "informed_fix"

    def test_insufficient_data_returns_investigation(self, conn):
        finding = self._make_finding(
            "retention", "medium", "Possibly insufficient data",
            analysis="no data available for this metric",
        )
        result = classify_and_escalate_all(conn, [finding])
        assert result[0]["decision_class"] == "investigation"

    def test_sorted_by_escalation_order_descending(self, conn):
        findings = [
            self._make_finding("security", "critical", "Critical issue"),
            self._make_finding("ux", "low", "Low issue"),
            self._make_finding("retention", "medium", "Medium issue"),
        ]
        # Insert critical into DB so escalation lookup works
        _insert_finding(conn, dimension="security", severity="critical", title="Critical issue")

        result = classify_and_escalate_all(conn, findings)

        orders = [item["escalation_order"] for item in result]
        assert orders == sorted(orders, reverse=True)

    def test_times_seen_affects_escalation(self, conn):
        # A finding seen 3+ times with high severity should escalate
        fid = _insert_finding(conn, dimension="retention", severity="high",
                              title="Chronic retention drop")
        conn.execute(
            "UPDATE pi_finding SET times_seen = 4 WHERE id = ?", (fid,)
        )
        conn.commit()

        finding = self._make_finding("retention", "high", "Chronic retention drop")
        escalation = compute_escalation(conn, finding)
        assert escalation in ("escalate", "emergency")

    def test_nudge_for_first_medium_finding(self, conn):
        finding = self._make_finding("ux", "medium", "Brand new medium finding")
        escalation = compute_escalation(conn, finding)
        assert escalation == "nudge"

    def test_quiet_for_first_low_finding(self, conn):
        finding = self._make_finding("ux", "low", "Brand new low finding")
        escalation = compute_escalation(conn, finding)
        assert escalation == "quiet"

    def test_context_frame_has_expected_keys(self, conn):
        findings = [self._make_finding("retention", "medium", "Context frame test")]
        result = classify_and_escalate_all(conn, findings)
        context = result[0]["context"]
        assert "benchmarks" in context
        assert "why_now" in context
        assert "correlations" in context

    def test_retention_dimension_includes_industry_benchmark(self, conn):
        findings = [self._make_finding("retention", "medium", "Benchmark test")]
        result = classify_and_escalate_all(conn, findings)
        context = result[0]["context"]
        benchmark_labels = [b.get("label", "") for b in context.get("benchmarks", [])]
        assert any("retention" in label.lower() or "D7" in label or "language" in label.lower()
                   for label in benchmark_labels)


# ---------------------------------------------------------------------------
# 9. classify_decision standalone
# ---------------------------------------------------------------------------

class TestClassifyDecision:

    def _finding(self, severity, dimension, files=None, analysis=""):
        return {
            "severity": severity,
            "dimension": dimension,
            "files": files or [],
            "analysis": analysis,
            "title": f"{dimension} finding",
        }

    def test_low_single_file_no_conflict_is_informed_fix(self):
        f = self._finding("low", "ux", files=["style.css"])
        assert classify_decision(f) == "informed_fix"

    def test_medium_no_files_is_informed_fix(self):
        f = self._finding("medium", "ux", files=[])
        assert classify_decision(f) == "informed_fix"

    def test_medium_multiple_files_is_informed_fix(self):
        f = self._finding("medium", "retention", files=["routes.py", "scheduler.py"])
        assert classify_decision(f) == "informed_fix"

    def test_no_data_analysis_is_investigation(self):
        f = self._finding("high", "retention", analysis="insufficient data to conclude")
        assert classify_decision(f) == "investigation"

    def test_high_severity_learning_dim_without_conflict_is_informed_fix(self):
        f = self._finding("high", "drill_quality", files=["drills/"])
        # No advisor conflict — high + learning dim without conflict -> judgment_call or informed_fix
        result = classify_decision(f)
        # With no advisor opinions, has_conflict=False, so high+learning_dim = judgment_call
        assert result in ("judgment_call", "informed_fix")

    def test_high_severity_profitability_is_values_decision(self):
        f = self._finding("high", "profitability", files=["routes.py"])
        result = classify_decision(f)
        assert result == "values_decision"


# ---------------------------------------------------------------------------
# 10. compute_engine_accuracy (GET /api/admin/intelligence/engine-meta)
# ---------------------------------------------------------------------------

class TestComputeEngineAccuracy:

    def test_empty_database_returns_zero_counts(self, conn):
        result = compute_engine_accuracy(conn)
        assert result["total_findings"] == 0
        assert result["true_positives"] == 0
        assert result["false_positives"] == 0
        assert result["false_positive_rate"] == 0.0
        assert result["avg_resolution_days"] is None
        assert result["per_dimension"] == {}

    def test_counts_findings_by_status(self, conn):
        _insert_finding(conn, title="Verified A", status="verified")
        _insert_finding(conn, title="Resolved B", status="resolved")
        _insert_finding(conn, title="Rejected C", status="rejected")
        _insert_finding(conn, title="Open D", status="investigating")

        result = compute_engine_accuracy(conn)
        assert result["total_findings"] == 4
        assert result["true_positives"] == 2   # verified + resolved
        assert result["false_positives"] == 1  # rejected

    def test_false_positive_rate_calculation(self, conn):
        for i in range(3):
            _insert_finding(conn, title=f"Rejected {i}", status="rejected")
        for i in range(7):
            _insert_finding(conn, title=f"Verified {i}", status="verified")

        result = compute_engine_accuracy(conn)
        assert result["false_positive_rate"] == pytest.approx(30.0)

    def test_per_dimension_breakdown(self, conn):
        _insert_finding(conn, dimension="retention", title="R1", status="verified")
        _insert_finding(conn, dimension="retention", title="R2", status="rejected")
        _insert_finding(conn, dimension="engineering", title="E1", status="resolved")

        result = compute_engine_accuracy(conn)
        dims = result["per_dimension"]
        assert "retention" in dims
        assert "engineering" in dims
        assert dims["retention"]["total"] == 2
        assert dims["retention"]["verified"] == 1
        assert dims["retention"]["rejected"] == 1
        assert dims["retention"]["fpr"] == pytest.approx(50.0)

    def test_avg_resolution_days_populated(self, conn):
        # Insert a finding with resolved_at set
        conn.execute("""
            INSERT INTO pi_finding
                (dimension, severity, title, status, created_at, resolved_at, metric_name)
            VALUES ('retention', 'medium', 'Resolved finding', 'resolved',
                    datetime('now', '-10 days'), datetime('now'), 'retention')
        """)
        conn.commit()

        result = compute_engine_accuracy(conn)
        assert result["avg_resolution_days"] is not None
        assert result["avg_resolution_days"] > 0

    def test_lookback_days_filters_old_findings(self, conn):
        # Insert a finding created 200 days ago (outside 90-day lookback)
        conn.execute("""
            INSERT INTO pi_finding
                (dimension, severity, title, status, created_at, metric_name)
            VALUES ('retention', 'high', 'Very old finding', 'rejected',
                    datetime('now', '-200 days'), 'retention')
        """)
        # Insert a recent finding
        _insert_finding(conn, title="Recent finding", status="verified")
        conn.commit()

        result = compute_engine_accuracy(conn, lookback_days=90)
        assert result["total_findings"] == 1
        assert result["true_positives"] == 1
        assert result["false_positives"] == 0


# ---------------------------------------------------------------------------
# 11. Check stale findings
# ---------------------------------------------------------------------------

class TestStaleFindingDetection:

    def test_fresh_finding_not_stale(self, conn):
        _insert_finding(conn, title="Fresh finding", status="investigating")
        stale = check_stale_findings(conn)
        assert all(f["title"] != "Stale finding: 'Fresh finding'" for f in stale)

    def test_old_investigating_finding_flagged_as_stale(self, conn):
        conn.execute("""
            INSERT INTO pi_finding
                (dimension, severity, title, status, updated_at, metric_name)
            VALUES ('retention', 'medium', 'Lingering investigation', 'investigating',
                    datetime('now', '-20 days'), 'retention')
        """)
        conn.commit()

        stale = check_stale_findings(conn)
        assert len(stale) == 1
        assert "Lingering investigation" in stale[0]["title"]

    def test_resolved_finding_not_flagged(self, conn):
        conn.execute("""
            INSERT INTO pi_finding
                (dimension, severity, title, status, updated_at, resolved_at, metric_name)
            VALUES ('ux', 'low', 'Old resolved finding', 'resolved',
                    datetime('now', '-30 days'), datetime('now', '-30 days'), 'ux')
        """)
        conn.commit()

        stale = check_stale_findings(conn)
        stale_titles = [f["title"] for f in stale]
        assert not any("Old resolved finding" in t for t in stale_titles)


# ---------------------------------------------------------------------------
# 12. End-to-end integration: full PI flow
# ---------------------------------------------------------------------------

class TestEndToEndIntelligenceFlow:
    """Exercise the complete workflow as if called by the admin API."""

    def test_full_flow(self, conn):
        """
        Simulates:
          1. GET /api/admin/intelligence/findings (seed data)
          2. POST /api/admin/intelligence/findings/<id>/transition
          3. POST /api/admin/intelligence/findings/<id>/outcome
          4. GET /api/admin/intelligence/feedback-summary
          5. GET /api/admin/intelligence/sprint-plan (Mediator)
          6. POST /api/admin/intelligence/findings/<id>/decide → classify_and_escalate_all
          7. GET /api/admin/intelligence/engine-meta → compute_engine_accuracy
        """
        # Step 1: Seed findings via deduplication (simulates engine run)
        raw_findings = [
            {
                "dimension": "retention",
                "severity": "high",
                "title": "D7 retention has dropped 8pp",
                "analysis": "D7 is 22%, down from 30%. Cohort analysis shows week-3 dropoff.",
                "recommendation": "Reduce week-3 difficulty curve.",
                "impact": "~40 active users at risk of churn.",
                "files": ["mandarin/scheduler.py"],
            },
            {
                "dimension": "engineering",
                "severity": "critical",
                "title": "NullPointerException in session close path",
                "analysis": "5 crashes in last 24h. Traceback points to session_cleanup.",
                "recommendation": "Add None guard in cleanup_session().",
                "impact": "Data loss risk for active sessions.",
                "files": ["mandarin/web/routes.py"],
            },
            {
                "dimension": "ux",
                "severity": "medium",
                "title": "Session abandonment rate up 12%",
                "analysis": "Early exit events increased this week.",
                "recommendation": "Audit first 5 items in session.",
                "impact": "Completion rate below 70% target.",
                "files": ["mandarin/web/static/app.js"],
            },
        ]
        new_findings = deduplicate_findings(conn, raw_findings)
        assert len(new_findings) == 3

        # Verify all three were inserted
        count = conn.execute("SELECT COUNT(*) FROM pi_finding").fetchone()[0]
        assert count == 3

        # Step 2: Transition the retention finding through the lifecycle
        ret_row = conn.execute(
            "SELECT id FROM pi_finding WHERE dimension = 'retention'"
        ).fetchone()
        ret_fid = ret_row["id"]

        assert transition_finding(conn, ret_fid, "diagnosed",
                                  notes="Identified week-3 difficulty spike as cause") is True
        assert transition_finding(conn, ret_fid, "recommended") is True
        # Enforcement gate requires prediction record
        conn.execute("""
            INSERT INTO pi_prediction_ledger
                (id, finding_id, model_id, dimension, claim_type, metric_name,
                 metric_baseline, predicted_delta, predicted_delta_confidence,
                 verification_window_days, verification_due_at, status, created_at)
            VALUES ('pred-e2e', ?, 'retention_model', 'retention', 'metric_will_improve', 'd7_retention',
                    22.0, 8.0, 0.7, 30,
                    datetime('now', '+30 days'), 'pending', datetime('now'))
        """, (ret_fid,))
        conn.commit()
        assert transition_finding(conn, ret_fid, "implemented") is True
        assert transition_finding(conn, ret_fid, "verified") is True

        # Step 3: Record outcome for the retention fix
        outcome_id = record_recommendation_outcome(
            conn, ret_fid,
            action_type="config_change",
            description="Reduced difficulty curve after week 2",
            files_changed=["mandarin/scheduler.py"],
            metric_before={"value": 22.0, "label": "D7 retention %"},
        )
        assert outcome_id > 0

        # Manually mark as effective (simulates verify_recommendation_outcomes)
        conn.execute("""
            UPDATE pi_recommendation_outcome
            SET verified_at = datetime('now'), effective = 1, delta_pct = 8.5
            WHERE id = ?
        """, (outcome_id,))
        conn.commit()

        # Step 4: Feedback summary
        summary = get_loop_closure_summary(conn)
        assert summary["total_outcomes"] == 1
        assert summary["verified_outcomes"] == 1
        assert summary["effective_count"] == 1
        assert summary["closure_rate"] == 100.0

        # Step 5: Sprint plan via Mediator
        open_findings = [
            f for f in raw_findings
            if f["dimension"] in ("engineering", "ux")
        ]
        mediator = Mediator()
        plan = mediator.plan_sprint(conn, open_findings, weekly_budget_hours=16.0)
        assert "plan" in plan
        assert len(plan["plan"]) >= 1
        for item in plan["plan"]:
            assert item["effort_hours"] > 0
            assert item["priority"] > 0

        # Step 6: Classify and escalate all open findings
        all_raw_open = raw_findings  # All three still in scope
        decision_queue = classify_and_escalate_all(conn, all_raw_open)
        assert len(decision_queue) == 3

        # Critical engineering finding must appear at or near top
        first = decision_queue[0]
        assert first["severity"] == "critical" or first["escalation_level"] == "emergency"

        # Verify every item has a decision class
        for item in decision_queue:
            assert item["decision_class"] in (
                "auto_fix", "informed_fix", "judgment_call",
                "values_decision", "investigation",
            )
            assert item["escalation_level"] in (
                "quiet", "nudge", "alert", "escalate", "emergency",
            )

        # Step 7: Engine accuracy meta-analysis
        # Resolve the retention finding so it shows as a true positive
        assert transition_finding(conn, ret_fid, "resolved") is True

        accuracy = compute_engine_accuracy(conn)
        assert accuracy["total_findings"] == 3
        assert accuracy["true_positives"] >= 1  # retention is resolved
        assert "retention" in accuracy["per_dimension"]
        assert "engineering" in accuracy["per_dimension"]

    def test_deduplication_then_second_run_increments_count(self, conn):
        """Simulates two successive engine runs — second run should deduplicate."""
        finding = {
            "dimension": "profitability",
            "severity": "medium",
            "title": "Conversion rate stagnant",
            "analysis": "Paid conversion stayed at 4% for 3 weeks.",
        }

        # First run
        new1 = deduplicate_findings(conn, [finding])
        assert len(new1) == 1

        # Second run — same finding still open
        new2 = deduplicate_findings(conn, [finding])
        assert len(new2) == 0  # Not new

        row = conn.execute(
            "SELECT times_seen FROM pi_finding WHERE title = 'Conversion rate stagnant'"
        ).fetchone()
        assert row["times_seen"] == 2

    def test_invalid_transition_does_not_corrupt_state(self, conn):
        """Rapid-fire invalid transitions should leave state intact."""
        fid = _insert_finding(conn, status="investigating")

        # Attempt various invalid transitions
        for bad_state in ("resolved", "verified", "implemented"):
            result = transition_finding(conn, fid, bad_state)
            assert result is False

        row = conn.execute("SELECT status FROM pi_finding WHERE id = ?", (fid,)).fetchone()
        assert row["status"] == "investigating"

    def test_mediator_and_human_loop_agree_on_critical(self, conn):
        """Critical findings should be flagged by both mediator (high priority) and human loop (emergency)."""
        finding = {
            "dimension": "security",
            "severity": "critical",
            "title": "SQL injection in search endpoint",
            "analysis": "Unsanitized input in search route allows arbitrary SQL.",
            "recommendation": "Parameterise all search queries.",
            "impact": "Full database exposure risk.",
            "files": ["mandarin/web/routes.py"],
        }
        _insert_finding(conn, dimension="security", severity="critical",
                        title="SQL injection in search endpoint")

        mediator = Mediator()
        plan = mediator.plan_sprint(conn, [finding], weekly_budget_hours=20.0)
        assert len(plan["plan"]) == 1
        # Stability advisor gives critical items 2× multiplier — should dominate
        assert plan["plan"][0]["winning_advisor"] is not None

        queue = classify_and_escalate_all(conn, [finding])
        assert queue[0]["escalation_level"] == "emergency"
