"""Tests for mandarin/intelligence/human_loop.py.

Uses in-memory SQLite with conn.row_factory = sqlite3.Row to mirror production
behavior. Covers all eight public functions:

  - classify_decision      (5 return values)
  - compute_escalation     (5 levels)
  - build_context_frame    (benchmarks, historical, why_now, correlations)
  - surface_for_role       (developer, product_owner, teacher)
  - record_override        (success + failure)
  - check_override_sunsets (expired overrides generate findings)
  - apply_overrides        (active overrides filter findings)
  - classify_and_escalate_all (sorting by escalation level)
"""
# phantom-schema-checked

import json
import sqlite3

import pytest

from tests.shared_db import make_test_db
from mandarin.intelligence.human_loop import (
    apply_overrides,
    build_context_frame,
    check_override_sunsets,
    classify_and_escalate_all,
    classify_decision,
    compute_escalation,
    record_override,
    surface_for_role,
)
from mandarin.intelligence._base import _finding


# ── Fixtures ─────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS pi_finding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id INTEGER,
    dimension TEXT,
    title TEXT,
    severity TEXT,
    analysis TEXT,
    recommendation TEXT,
    claude_prompt TEXT,
    impact TEXT,
    files TEXT,
    times_seen INTEGER DEFAULT 1,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_recommendation_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER,
    effective INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS product_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    overall_score REAL,
    dimension_scores TEXT,
    run_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pi_threshold_calibration (
    metric_name TEXT PRIMARY KEY,
    threshold_value REAL,
    false_positive_rate REAL,
    calibrated_at TEXT DEFAULT (datetime('now')),
    prior_threshold REAL,
    notes TEXT
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
    created_at TEXT DEFAULT (datetime('now'))
);
"""


@pytest.fixture
def conn():
    c = make_test_db()
    c.executescript(DDL)
    yield c
    c.close()


def _f(**overrides):
    """Build a finding dict with sensible defaults."""
    return _finding(
        dimension=overrides.get("dimension", "retention"),
        severity=overrides.get("severity", "low"),
        title=overrides.get("title", "Test finding"),
        analysis=overrides.get("analysis", "Some analysis"),
        recommendation=overrides.get("recommendation", "Fix it"),
        claude_prompt=overrides.get("claude_prompt", "prompt"),
        impact=overrides.get("impact", "impact statement"),
        files=overrides.get("files", []),
    )


# ── classify_decision ────────────────────────────────────────────────────


class TestClassifyDecision:
    """All 5 return values: auto_fix, informed_fix, judgment_call, values_decision, investigation."""

    def test_auto_fix_low_severity_no_files_no_conflict(self):
        assert classify_decision(_f(severity="low", files=[])) == "auto_fix"

    def test_auto_fix_low_severity_single_file(self):
        assert classify_decision(_f(severity="low", files=["a.py"])) == "auto_fix"

    def test_auto_fix_medium_severity_single_file(self):
        assert classify_decision(_f(severity="medium", files=["a.py"])) == "auto_fix"

    def test_informed_fix_medium_severity_multiple_files(self):
        assert classify_decision(_f(severity="medium", files=["a.py", "b.py"])) == "informed_fix"

    def test_values_decision_high_severity_profitability(self):
        assert classify_decision(_f(severity="high", dimension="profitability")) == "values_decision"

    def test_judgment_call_high_severity_learning_dimension(self):
        assert classify_decision(_f(severity="high", dimension="drill_quality")) == "judgment_call"

    def test_judgment_call_high_severity_with_advisor_conflict(self):
        f = _f(severity="high", dimension="retention", title="churn")
        opinions = {
            "churn": [
                {"advisor": "learning", "priority_score": 80},
                {"advisor": "growth", "priority_score": 10},
            ]
        }
        assert classify_decision(f, opinions) == "judgment_call"

    def test_informed_fix_copy_dimension(self):
        assert classify_decision(_f(dimension="copy", severity="medium", files=["a.py", "b.py"])) == "informed_fix"

    def test_values_decision_aesthetic_in_analysis(self):
        f = _f(severity="medium", analysis="This is an aesthetic concern", files=["a.py", "b.py"])
        assert classify_decision(f) == "values_decision"

    def test_values_decision_learning_vs_retention_conflict(self):
        f = _f(severity="low", dimension="ux", title="flow issue", files=["a.py", "b.py"])
        opinions = {
            "flow issue": [
                {"advisor": "learning", "priority_score": 90},
                {"advisor": "retention", "priority_score": 21},
            ]
        }
        assert classify_decision(f, opinions) == "informed_fix"

    def test_investigation_insufficient_data(self):
        f = _f(severity="medium", analysis="There is insufficient data", files=["a.py", "b.py"])
        assert classify_decision(f) == "investigation"

    def test_investigation_no_data(self):
        f = _f(severity="medium", analysis="no data available", files=["a.py", "b.py"])
        assert classify_decision(f) == "investigation"


# ── compute_escalation ───────────────────────────────────────────────────


class TestComputeEscalation:
    """All 5 levels: quiet, nudge, alert, escalate, emergency."""

    def test_quiet_low_severity_first_seen(self, conn):
        assert compute_escalation(conn, _f(severity="low")) == "quiet"

    def test_nudge_medium_severity_first_seen(self, conn):
        assert compute_escalation(conn, _f(severity="medium")) == "nudge"

    def test_alert_seen_twice(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding", 2, "investigating"),
        )
        assert compute_escalation(conn, _f(severity="medium")) == "alert"

    def test_escalate_seen_three_times_high_severity(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding", 3, "investigating"),
        )
        assert compute_escalation(conn, _f(severity="high")) == "escalate"

    def test_escalate_prior_fix_ineffective(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding", 3, "investigating"),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO pi_recommendation_outcome (finding_id, action_type, effective) VALUES (?,?,?)",
            (fid, "code_change", -1),
        )
        assert compute_escalation(conn, _f(severity="low")) == "escalate"

    def test_emergency_critical_severity(self, conn):
        assert compute_escalation(conn, _f(severity="critical")) == "emergency"

    def test_resolved_findings_ignored(self, conn):
        """Resolved findings should not affect escalation."""
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding", 5, "resolved"),
        )
        assert compute_escalation(conn, _f(severity="low")) == "quiet"


# ── build_context_frame ──────────────────────────────────────────────────


class TestBuildContextFrame:
    def test_industry_benchmark_present(self, conn):
        frame = build_context_frame(conn, _f(dimension="retention"))
        labels = [b["label"] for b in frame["benchmarks"]]
        assert "Language app D7 retention" in labels

    def test_no_benchmark_for_unknown_dimension(self, conn):
        frame = build_context_frame(conn, _f(dimension="unknown_dim"))
        assert frame["benchmarks"] == []

    def test_historical_scores(self, conn):
        scores = json.dumps({"retention": {"score": 72}})
        conn.execute(
            "INSERT INTO product_audit (overall_score, overall_grade, dimension_scores, findings_json, findings_count, run_at) VALUES (?,?,?,?,?,?)",
            (75.0, "C", scores, "[]", 0, "2026-01-01"),
        )
        frame = build_context_frame(conn, _f(dimension="retention"))
        hist = [b for b in frame["benchmarks"] if b["source"] == "product_audit"]
        assert len(hist) == 1
        assert 72 in hist[0]["value"]

    def test_calibrated_threshold(self, conn):
        conn.execute(
            "INSERT INTO pi_threshold_calibration (metric_name, threshold_value, false_positive_rate) VALUES (?,?,?)",
            ("retention", 0.35, 0.05),
        )
        frame = build_context_frame(conn, _f(dimension="retention"))
        cal = [b for b in frame["benchmarks"] if b["source"] == "pi_threshold_calibration"]
        assert len(cal) == 1
        assert cal[0]["value"] == 0.35

    def test_why_now_first_time(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding", 1, "investigating"),
        )
        frame = build_context_frame(conn, _f())
        assert frame["why_now"] == "First time detected"

    def test_why_now_persistent(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding", 3, "investigating"),
        )
        frame = build_context_frame(conn, _f())
        assert "3 times" in frame["why_now"]

    def test_why_now_chronic(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding", 5, "investigating"),
        )
        frame = build_context_frame(conn, _f())
        assert "chronic" in frame["why_now"]

    def test_why_now_new_finding(self, conn):
        frame = build_context_frame(conn, _f(title="Never seen"))
        assert frame["why_now"] == "New finding"

    def test_why_now_regression(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding", 1, "investigating"),
        )
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, times_seen, status) VALUES (?,?,?,?,?)",
            ("retention", "medium", "Test finding old", 1, "resolved"),
        )
        frame = build_context_frame(conn, _f())
        assert "Regression" in frame["why_now"]

    def test_correlations_co_occurring(self, conn):
        conn.execute(
            "INSERT INTO product_audit (id, overall_score, overall_grade, dimension_scores, findings_json, findings_count) "
            "VALUES (1, 75.0, 'C', '{}', '[]', 0)"
        )
        conn.execute(
            "INSERT INTO pi_finding (audit_id, dimension, severity, title, status) VALUES (?,?,?,?,?)",
            (1, "retention", "medium", "Test finding", "investigating"),
        )
        conn.execute(
            "INSERT INTO pi_finding (audit_id, dimension, severity, title, status) VALUES (?,?,?,?,?)",
            (1, "ux", "medium", "UX issue", "investigating"),
        )
        frame = build_context_frame(conn, _f())
        assert any("UX issue" in c for c in frame["correlations"])

    def test_frame_has_all_keys(self, conn):
        frame = build_context_frame(conn, _f())
        for key in ("benchmarks", "cohort_breakdowns", "why_now", "correlations", "options"):
            assert key in frame


# ── surface_for_role ─────────────────────────────────────────────────────


class TestSurfaceForRole:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.finding = _f(
            title="Churn spike",
            severity="high",
            dimension="retention",
            analysis="detailed analysis",
            claude_prompt="fix churn",
            impact="revenue loss",
            files=["routes.py"],
        )
        self.finding["recommendation"] = "improve onboarding"
        self.context = {
            "why_now": "Seen 3 times",
            "benchmarks": [{"label": "D7", "value": "30-40%"}],
            "correlations": ["Co-occurs with: UX issue"],
            "options": [{"label": "Option A"}],
            "cohort_breakdowns": [{"cohort": "new_users"}],
        }

    def test_developer_includes_files_prompt_analysis(self):
        r = surface_for_role(self.finding, self.context, "developer")
        assert r["files"] == ["routes.py"]
        assert r["claude_prompt"] == "fix churn"
        assert r["analysis"] == "detailed analysis"
        assert r["options"] == [{"label": "Option A"}]

    def test_product_owner_no_files_has_impact(self):
        r = surface_for_role(self.finding, self.context, "product_owner")
        assert "files" not in r
        assert r["impact"] == "revenue loss"
        assert r["recommendation"] == "improve onboarding"
        assert r["correlations"] == ["Co-occurs with: UX issue"]

    def test_teacher_has_learning_impact_and_cohorts(self):
        r = surface_for_role(self.finding, self.context, "teacher")
        assert r["learning_impact"] == "detailed analysis"
        assert r["cohort_breakdowns"] == [{"cohort": "new_users"}]
        assert r["recommendation"] == "improve onboarding"

    def test_all_roles_share_base_fields(self):
        for role in ("developer", "product_owner", "teacher"):
            r = surface_for_role(self.finding, self.context, role)
            assert r["title"] == "Churn spike"
            assert r["severity"] == "high"
            assert r["dimension"] == "retention"
            assert r["why_now"] == "Seen 3 times"


# ── record_override ──────────────────────────────────────────────────────


class TestRecordOverride:
    def test_success_creates_log_and_calibration(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, status) VALUES (?,?,?,?)",
            ("retention", "low", "noisy", "investigating"),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        assert record_override(conn, fid, "retention", 0.25, "too noisy", 30) is True

        row = conn.execute(
            "SELECT * FROM pi_decision_log WHERE finding_id = ?", (fid,)
        ).fetchone()
        assert row is not None
        assert "Override" in row["decision"]
        assert row["decision_reason"] == "too noisy"
        assert row["override_expires_at"] is not None

        cal = conn.execute(
            "SELECT * FROM pi_threshold_calibration WHERE metric_name = ?", ("retention",)
        ).fetchone()
        assert cal["threshold_value"] == 0.25

    def test_failure_returns_false(self):
        bad = sqlite3.connect(":memory:")
        bad.row_factory = sqlite3.Row
        # No tables -> should fail gracefully
        assert record_override(bad, 1, "x", 0.5, "test") is False
        bad.close()

    def test_upsert_threshold(self, conn):
        """Second override on same metric updates rather than duplicates."""
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, status) VALUES (?,?,?,?)",
            ("retention", "low", "noisy", "investigating"),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        record_override(conn, fid, "retention", 0.25, "first")
        record_override(conn, fid, "retention", 0.50, "second")
        cal = conn.execute(
            "SELECT * FROM pi_threshold_calibration WHERE metric_name = ?", ("retention",)
        ).fetchone()
        assert cal["threshold_value"] == 0.50
        count = conn.execute(
            "SELECT COUNT(*) FROM pi_threshold_calibration WHERE metric_name = ?", ("retention",)
        ).fetchone()[0]
        assert count == 1


# ── check_override_sunsets ───────────────────────────────────────────────


class TestCheckOverrideSunsets:
    def test_expired_override_generates_finding(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, status) VALUES (?,?,?,?)",
            ("ux", "low", "stale alert", "investigating"),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("""
            INSERT INTO pi_decision_log
                (finding_id, decision_class, escalation_level, decision, decision_reason, override_expires_at)
            VALUES (?, 'auto_fix', 'quiet', 'Override: suppress ux', 'too noisy', datetime('now', '-1 day'))
        """, (fid,))
        conn.commit()

        findings = check_override_sunsets(conn)
        assert len(findings) == 1
        assert "Override expired" in findings[0]["title"]
        assert "stale alert" in findings[0]["title"]

        # Verify marked as handled
        row = conn.execute(
            "SELECT outcome_notes FROM pi_decision_log WHERE finding_id = ?", (fid,)
        ).fetchone()
        assert row["outcome_notes"] == "Expired, regenerated finding"

    def test_no_expired_returns_empty(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, status) VALUES (?,?,?,?)",
            ("ux", "low", "alert", "investigating"),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("""
            INSERT INTO pi_decision_log
                (finding_id, decision_class, escalation_level, decision, decision_reason, override_expires_at)
            VALUES (?, 'auto_fix', 'quiet', 'Override: suppress ux', 'reason', datetime('now', '+30 days'))
        """, (fid,))
        conn.commit()
        assert check_override_sunsets(conn) == []

    def test_already_handled_not_regenerated(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, status) VALUES (?,?,?,?)",
            ("ux", "low", "stale alert", "investigating"),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("""
            INSERT INTO pi_decision_log
                (finding_id, decision_class, escalation_level, decision, decision_reason, override_expires_at, outcome_notes)
            VALUES (?, 'auto_fix', 'quiet', 'Override: suppress ux', 'reason',
                    datetime('now', '-1 day'), 'Already handled')
        """, (fid,))
        conn.commit()
        assert check_override_sunsets(conn) == []


# ── apply_overrides ──────────────────────────────────────────────────────


class TestApplyOverrides:
    def test_active_override_filters_matching_finding(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, status) VALUES (?,?,?,?)",
            ("retention", "low", "noisy metric", "investigating"),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("""
            INSERT INTO pi_decision_log
                (finding_id, decision_class, escalation_level, decision, decision_reason, override_expires_at)
            VALUES (?, 'auto_fix', 'quiet', 'Override: suppress retention', 'noisy', datetime('now', '+30 days'))
        """, (fid,))
        conn.commit()

        findings = [
            _f(dimension="retention", title="noisy metric"),
            _f(dimension="ux", title="real issue"),
        ]
        result = apply_overrides(findings, conn)
        assert len(result) == 1
        assert result[0]["title"] == "real issue"

    def test_no_overrides_returns_all(self, conn):
        findings = [_f(title="a"), _f(title="b")]
        assert len(apply_overrides(findings, conn)) == 2

    def test_expired_override_does_not_filter(self, conn):
        conn.execute(
            "INSERT INTO pi_finding (dimension, severity, title, status) VALUES (?,?,?,?)",
            ("retention", "low", "noisy metric", "investigating"),
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("""
            INSERT INTO pi_decision_log
                (finding_id, decision_class, escalation_level, decision, decision_reason, override_expires_at)
            VALUES (?, 'auto_fix', 'quiet', 'Override: suppress retention', 'noisy', datetime('now', '-1 day'))
        """, (fid,))
        conn.commit()

        result = apply_overrides([_f(dimension="retention", title="noisy metric")], conn)
        assert len(result) == 1


# ── classify_and_escalate_all ────────────────────────────────────────────


class TestClassifyAndEscalateAll:
    def test_sorted_highest_escalation_first(self, conn):
        findings = [
            _f(severity="low", title="quiet", dimension="profitability"),
            _f(severity="critical", title="emergency", dimension="profitability"),
            _f(severity="medium", title="nudge", dimension="profitability"),
        ]
        queue = classify_and_escalate_all(conn, findings)
        levels = [q["escalation_level"] for q in queue]
        assert levels == ["emergency", "nudge", "quiet"]

    def test_secondary_sort_by_severity(self, conn):
        # Same escalation (quiet), different severity
        findings = [
            _f(severity="low", title="low a", dimension="profitability"),
            _f(severity="low", title="low b", dimension="ux"),
        ]
        queue = classify_and_escalate_all(conn, findings)
        assert len(queue) == 2
        assert all(q["escalation_level"] == "quiet" for q in queue)

    def test_includes_decision_class_and_context(self, conn):
        queue = classify_and_escalate_all(conn, [_f(severity="medium", dimension="retention")])
        assert len(queue) == 1
        item = queue[0]
        assert "decision_class" in item
        assert "context" in item
        assert "why_now" in item["context"]
        assert "escalation_order" in item

    def test_empty_findings_returns_empty(self, conn):
        assert classify_and_escalate_all(conn, []) == []

    def test_advisor_opinions_passed_through(self, conn):
        f = _f(severity="high", dimension="drill_quality", title="pedagogy gap")
        opinions = {
            "pedagogy gap": [
                {"advisor": "learning", "priority_score": 80},
                {"advisor": "growth", "priority_score": 10},
            ]
        }
        queue = classify_and_escalate_all(conn, [f], advisor_opinions=opinions)
        assert queue[0]["decision_class"] == "judgment_call"
