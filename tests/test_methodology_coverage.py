"""Tests for methodology coverage grading.

13 test categories:
1. N/A components excluded from weighted average
2. Framework with all N/A scores 100
3. _score_to_grade() boundaries
4. Detection function returns DetectionResult with all fields
5. check_wip_limits: defined but never triggered → gaps include enforcement warning
6. check_subordination_enforcer: no active work order → low confidence
7. Finding generated only for grades below B+
8. Severity mapping: D→high, F→critical
9. Trend: prior B → current A = 'improving'
10. Override persisted with reason
11. Admin endpoint returns all 9 frameworks
12. Component grades persisted with audit_cycle_id
13. grade_all_frameworks() completes without error on empty DB
"""

import json
import sqlite3
import uuid

import pytest

from tests.shared_db import make_test_db
from mandarin.intelligence.methodology_coverage import (
    DetectionResult,
    _score_to_grade,
    _compute_trend,
    grade_all_frameworks,
    generate_methodology_findings,
    check_wip_limits,
    check_subordination_enforcer,
    check_dpmo_implementation,
    DETECTION_FUNCTIONS,
)


# ---------------------------------------------------------------------------
# Schema — minimal tables needed for methodology coverage tests
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
    audit_id INTEGER,
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
    linked_finding_id INTEGER,
    times_seen INTEGER NOT NULL DEFAULT 1,
    last_seen_audit_id INTEGER,
    resolution_notes TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quality_metric (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_type TEXT NOT NULL,
    value REAL,
    details TEXT,
    measured_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS spc_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chart_type TEXT NOT NULL,
    value REAL NOT NULL,
    subgroup_size INTEGER DEFAULT 1,
    observed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS work_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT,
    item_type TEXT,
    status TEXT DEFAULT 'backlog',
    created_at TEXT DEFAULT (datetime('now')),
    ready_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    blocked_at TEXT,
    unblocked_at TEXT,
    service_class TEXT,
    review_at TEXT
);

CREATE TABLE IF NOT EXISTS experiment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    status TEXT DEFAULT 'draft',
    start_date TEXT,
    end_date TEXT,
    metric_name TEXT,
    hypothesis TEXT,
    min_sample_size INTEGER DEFAULT 0,
    conclusion TEXT,
    guardrail_metrics TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS experiment_assignment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER,
    user_id TEXT,
    variant TEXT,
    assigned_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS experiment_exposure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER,
    user_id TEXT,
    variant TEXT,
    exposed_at TEXT DEFAULT (datetime('now')),
    session_id TEXT,
    outcome_metric TEXT,
    outcome_value REAL
);

CREATE TABLE IF NOT EXISTS pi_dmaic_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension TEXT,
    define_json TEXT,
    measure_json TEXT,
    analyze_json TEXT,
    improve_json TEXT,
    control_json TEXT,
    run_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_false_negative_signal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_source TEXT,
    signal_id TEXT,
    dimension TEXT,
    detected_at TEXT DEFAULT (datetime('now')),
    had_finding INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS pi_threshold_calibration (
    metric_name TEXT PRIMARY KEY,
    threshold_value REAL,
    calibrated_at TEXT,
    sample_size INTEGER,
    false_positive_rate REAL,
    false_negative_rate REAL,
    prior_threshold REAL,
    notes TEXT,
    verification_window_days INTEGER
);

CREATE TABLE IF NOT EXISTS pi_work_order (
    id TEXT PRIMARY KEY,
    audit_cycle_id TEXT,
    finding_id INTEGER,
    prediction_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    constraint_dimension TEXT,
    constraint_score REAL,
    marginal_improvement REAL,
    instruction TEXT,
    target_file TEXT,
    target_parameter TEXT,
    direction TEXT,
    success_metric TEXT,
    success_baseline REAL,
    success_threshold REAL,
    verification_window_days INTEGER,
    verification_due_at TEXT,
    subordinated_count INTEGER DEFAULT 0,
    subordinated_finding_ids TEXT,
    status TEXT DEFAULT 'pending',
    implemented_at TEXT,
    verified_at TEXT,
    outcome_notes TEXT,
    confidence_label TEXT,
    confidence_score REAL,
    instruction_source TEXT
);

CREATE TABLE IF NOT EXISTS pi_advisor_opinion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER,
    advisor TEXT,
    recommendation TEXT,
    priority_score REAL,
    effort_estimate REAL,
    rationale TEXT,
    tradeoff_notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_advisor_resolution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    winning_advisor TEXT,
    resolution_rationale TEXT,
    tradeoff_summary TEXT,
    weekly_effort_budget REAL,
    constraint_notes TEXT
);

CREATE TABLE IF NOT EXISTS pi_decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER,
    decision_class TEXT,
    escalation_level TEXT,
    presented_to TEXT,
    decision TEXT,
    decision_reason TEXT,
    override_expires_at TEXT,
    outcome_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    requires_approval INTEGER,
    approved_at TEXT
);

CREATE TABLE IF NOT EXISTS pi_recommendation_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER,
    action_type TEXT,
    action_description TEXT,
    files_changed TEXT,
    metric_before REAL,
    metric_after REAL,
    delta_pct REAL,
    effective INTEGER,
    verified_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    items_planned INTEGER,
    items_completed INTEGER,
    accuracy REAL,
    experiment_variant TEXT,
    client_platform TEXT
);

CREATE TABLE IF NOT EXISTS lifecycle_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    event_type TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_framework_components (
    id TEXT PRIMARY KEY,
    framework TEXT NOT NULL,
    component_name TEXT NOT NULL,
    component_description TEXT NOT NULL,
    solo_dev_applicable TEXT NOT NULL
        CHECK(solo_dev_applicable IN ('yes','no','partial','when_scaled')),
    applicability_rationale TEXT NOT NULL,
    detection_function TEXT,
    weight REAL NOT NULL DEFAULT 1.0,
    UNIQUE(framework, component_name)
);

CREATE TABLE IF NOT EXISTS pi_framework_grades (
    id TEXT PRIMARY KEY,
    graded_at TEXT NOT NULL DEFAULT (datetime('now')),
    audit_cycle_id TEXT,
    framework TEXT NOT NULL,
    component_name TEXT NOT NULL,
    raw_score REAL NOT NULL,
    weighted_score REAL NOT NULL,
    grade_label TEXT NOT NULL,
    evidence TEXT NOT NULL,
    gap_description TEXT,
    recommendation TEXT,
    solo_dev_applicable TEXT NOT NULL,
    was_overridden INTEGER DEFAULT 0,
    override_reason TEXT
);

CREATE TABLE IF NOT EXISTS pi_framework_summary_grades (
    id TEXT PRIMARY KEY,
    graded_at TEXT NOT NULL DEFAULT (datetime('now')),
    audit_cycle_id TEXT,
    framework TEXT NOT NULL,
    overall_score REAL NOT NULL,
    overall_grade TEXT NOT NULL,
    applicable_component_count INTEGER NOT NULL,
    na_component_count INTEGER NOT NULL,
    gap_count INTEGER NOT NULL,
    prior_grade TEXT,
    trend TEXT CHECK(trend IN ('improving','stable','declining')),
    summary_text TEXT NOT NULL
);
"""


@pytest.fixture
def conn():
    """In-memory SQLite with methodology coverage schema."""
    c = make_test_db()
    c.executescript(_DDL)
    c.commit()
    return c


def _seed_components(conn):
    """Seed the standard framework components."""
    from mandarin.db.core import _seed_framework_components
    _seed_framework_components(conn)
    conn.commit()


# ---------------------------------------------------------------------------
# 1. N/A components excluded from weighted average
# ---------------------------------------------------------------------------

class TestNAExclusion:
    def test_na_components_not_in_average(self, conn):
        """N/A components (weight=0 or solo_dev_applicable='no') should not affect scores."""
        _seed_components(conn)
        result = grade_all_frameworks(conn)
        # Spiral and Scrum should be N/A
        spiral = result["frameworks"].get("spiral", {})
        scrum = result["frameworks"].get("scrum", {})
        assert spiral.get("na_count", 0) >= 1
        assert scrum.get("na_count", 0) >= 1
        # Their applicable count should be 0
        assert spiral.get("applicable_count", 0) == 0
        assert scrum.get("applicable_count", 0) == 0


# ---------------------------------------------------------------------------
# 2. Framework with all N/A scores 100
# ---------------------------------------------------------------------------

class TestAllNAFramework:
    def test_all_na_scores_100(self, conn):
        """A framework where all components are N/A should get score 100."""
        _seed_components(conn)
        result = grade_all_frameworks(conn)
        spiral = result["frameworks"].get("spiral", {})
        assert spiral["score"] == 100.0
        scrum = result["frameworks"].get("scrum", {})
        assert scrum["score"] == 100.0


# ---------------------------------------------------------------------------
# 3. _score_to_grade() boundaries
# ---------------------------------------------------------------------------

class TestScoreToGrade:
    @pytest.mark.parametrize("score,expected", [
        (95, "A+"), (100, "A+"), (94, "A"), (88, "A"), (87, "B+"),
        (80, "B+"), (79, "B"), (70, "B"), (69, "C+"), (60, "C+"),
        (59, "C"), (50, "C"), (49, "D"), (40, "D"), (39, "F"), (0, "F"),
    ])
    def test_grade_boundaries(self, score, expected):
        assert _score_to_grade(score) == expected


# ---------------------------------------------------------------------------
# 4. Detection function returns DetectionResult with all fields
# ---------------------------------------------------------------------------

class TestDetectionResult:
    def test_dpmo_returns_detection_result(self, conn):
        result = check_dpmo_implementation(conn)
        assert isinstance(result, DetectionResult)
        assert result.component_name == "DPMO tracking"
        assert result.framework == "six_sigma"
        assert isinstance(result.present, bool)
        assert isinstance(result.quality, float)
        assert isinstance(result.evidence, list)
        assert isinstance(result.gaps, list)
        assert isinstance(result.raw_score, float)
        assert isinstance(result.confidence, float)

    def test_all_detection_functions_exist(self):
        """All detection functions should be registered."""
        assert len(DETECTION_FUNCTIONS) == 46


# ---------------------------------------------------------------------------
# 5. check_wip_limits: defined but never triggered → gaps include warning
# ---------------------------------------------------------------------------

class TestWipLimits:
    def test_wip_limits_with_high_wip_warns(self, conn):
        """If WIP count is high, gap should mention enforcement."""
        for i in range(10):
            conn.execute(
                "INSERT INTO work_item (title, status) VALUES (?, 'in_progress')",
                (f"item-{i}",))
        conn.commit()
        result = check_wip_limits(conn)
        gap_text = " ".join(result.gaps)
        assert "exceed" in gap_text.lower() or "enforcement" in gap_text.lower()


# ---------------------------------------------------------------------------
# 6. check_subordination_enforcer: no active work order → low confidence
# ---------------------------------------------------------------------------

class TestSubordinationEnforcer:
    def test_no_work_order_low_confidence(self, conn):
        result = check_subordination_enforcer(conn)
        assert result.confidence < 0.5
        assert not result.present
        assert len(result.gaps) > 0


# ---------------------------------------------------------------------------
# 7. Finding generated only for grades below B+
# ---------------------------------------------------------------------------

class TestFindingsGeneration:
    def test_no_findings_for_high_grades(self, conn):
        """Frameworks at B+ or above should not generate findings."""
        _seed_components(conn)
        findings = generate_methodology_findings(conn)
        # Spiral and Scrum (score=100, N/A) should not generate findings
        spiral_findings = [f for f in findings if "spiral" in f.get("title", "").lower()]
        scrum_findings = [f for f in findings if "scrum" in f.get("title", "").lower()]
        assert len(spiral_findings) == 0
        assert len(scrum_findings) == 0

    def test_findings_for_low_grades(self, conn):
        """Frameworks with low scores should generate findings."""
        _seed_components(conn)
        # On empty DB, most frameworks will score low
        findings = generate_methodology_findings(conn)
        # At least some frameworks should generate findings on empty DB
        assert len(findings) > 0


# ---------------------------------------------------------------------------
# 8. Severity mapping: D→high, F→critical
# ---------------------------------------------------------------------------

class TestSeverityMapping:
    def test_severity_mapping(self, conn):
        """Low-scoring frameworks should get appropriate severity."""
        _seed_components(conn)
        findings = generate_methodology_findings(conn)
        # On empty DB, frameworks score 0 (F grade) → should be critical
        for f in findings:
            score_str = f.get("title", "")
            if "(0/100)" in score_str:
                assert f["severity"] == "critical", f"F-grade finding should be critical: {f['title']}"


# ---------------------------------------------------------------------------
# 9. Trend: prior B → current A = 'improving'
# ---------------------------------------------------------------------------

class TestTrend:
    def test_improving_trend(self):
        assert _compute_trend("B", "A") == "improving"

    def test_declining_trend(self):
        assert _compute_trend("A", "C") == "declining"

    def test_stable_trend(self):
        assert _compute_trend("B", "B") == "stable"

    def test_slight_improvement_still_improving(self):
        # B=75, B+=84 → 9 point jump > 3 threshold → improving
        assert _compute_trend("B", "B+") == "improving"

    def test_same_grade_stable(self):
        assert _compute_trend("A", "A") == "stable"


# ---------------------------------------------------------------------------
# 10. Override persisted with reason
# ---------------------------------------------------------------------------

class TestOverride:
    def test_override_persisted(self, conn):
        _seed_components(conn)
        # Insert an override for a specific component
        conn.execute(
            """INSERT INTO pi_framework_grades
               (id, framework, component_name, raw_score, weighted_score,
                grade_label, evidence, solo_dev_applicable, was_overridden, override_reason)
               VALUES (?, 'six_sigma', 'DPMO tracking', 95, 95, 'A+', '[]', 'yes', 1, 'Manual review confirmed')""",
            (str(uuid.uuid4()),))
        conn.commit()

        # Re-grade — should pick up override
        result = grade_all_frameworks(conn)
        ss = result["frameworks"]["six_sigma"]
        dpmo_comp = [c for c in ss["components"] if c["component_name"] == "DPMO tracking"]
        assert len(dpmo_comp) == 1
        assert dpmo_comp[0]["was_overridden"] == 1
        assert dpmo_comp[0]["raw_score"] == 95


# ---------------------------------------------------------------------------
# 11. Admin endpoint returns all 9 frameworks
# ---------------------------------------------------------------------------

class TestAllFrameworks:
    def test_nine_frameworks_returned(self, conn):
        _seed_components(conn)
        result = grade_all_frameworks(conn)
        frameworks = result["frameworks"]
        expected = {"six_sigma", "lean", "kanban", "operations_research",
                    "theory_of_constraints", "spc", "doe", "spiral", "scrum"}
        assert set(frameworks.keys()) == expected
        assert result["framework_count"] == 9


# ---------------------------------------------------------------------------
# 12. Component grades persisted with audit_cycle_id
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_grades_persisted(self, conn):
        _seed_components(conn)
        grade_all_frameworks(conn, audit_cycle_id="test-audit-123")
        # Check pi_framework_grades has rows
        count = conn.execute("SELECT COUNT(*) FROM pi_framework_grades").fetchone()[0]
        assert count > 0
        # Check audit_cycle_id
        row = conn.execute(
            "SELECT audit_cycle_id FROM pi_framework_grades LIMIT 1"
        ).fetchone()
        assert row[0] == "test-audit-123"
        # Check summary grades persisted
        summary_count = conn.execute(
            "SELECT COUNT(*) FROM pi_framework_summary_grades"
        ).fetchone()[0]
        assert summary_count == 9  # One per framework


# ---------------------------------------------------------------------------
# 13. grade_all_frameworks() completes without error on empty DB
# ---------------------------------------------------------------------------

class TestEmptyDB:
    def test_empty_db_no_crash(self, conn):
        """Grading should complete on empty DB (no seed data → no components → empty result)."""
        result = grade_all_frameworks(conn)
        assert "frameworks" in result
        assert "overall_score" in result
        assert "overall_grade" in result

    def test_empty_db_with_components_no_crash(self, conn):
        """Grading with seeded components but no data should still work."""
        _seed_components(conn)
        result = grade_all_frameworks(conn)
        assert result["framework_count"] == 9
        # All applicable frameworks should have grades (even if F)
        for fw_name, fw_data in result["frameworks"].items():
            assert "grade" in fw_data
            assert "score" in fw_data
            assert fw_data["score"] >= 0
            assert fw_data["score"] <= 100
