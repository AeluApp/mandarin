"""Tests for Intelligence Coverage Audit (Document 6).

Covers: coverage map, summary, snapshot persistence, gap closure priority,
cross-domain constraint finder, pedagogical safety, engagement health,
AI portfolio verdict, content quality, constraint persistence, priority order.
"""

import json
import sqlite3
import unittest
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.t2


def _make_db():
    """Create an in-memory SQLite DB with tables needed for coverage audit."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Core tables
    conn.execute("""CREATE TABLE session_log (
        id INTEGER PRIMARY KEY, user_id INTEGER, started_at TEXT DEFAULT (datetime('now')),
        items_planned INTEGER DEFAULT 10, items_completed INTEGER DEFAULT 8,
        early_exit INTEGER DEFAULT 0, client_platform TEXT DEFAULT 'web'
    )""")
    conn.execute("""CREATE TABLE product_audit (
        id INTEGER PRIMARY KEY, run_at TEXT DEFAULT (datetime('now')),
        overall_grade TEXT, overall_score REAL,
        dimension_scores TEXT, findings_json TEXT,
        findings_count INTEGER, critical_count INTEGER, high_count INTEGER
    )""")

    # Intelligence tables
    conn.execute("""CREATE TABLE pi_coverage_audit_log (
        id TEXT PRIMARY KEY,
        logged_at TEXT NOT NULL DEFAULT (datetime('now')),
        component TEXT NOT NULL,
        domain TEXT NOT NULL,
        coverage_status TEXT NOT NULL,
        covering_document TEXT,
        notes TEXT
    )""")
    conn.execute("""CREATE TABLE pi_system_constraint_history (
        id TEXT PRIMARY KEY,
        identified_at TEXT NOT NULL DEFAULT (datetime('now')),
        constraint_type TEXT NOT NULL,
        domain TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT NOT NULL,
        resolved_at TEXT,
        resolution TEXT
    )""")
    conn.execute("""CREATE TABLE pi_ai_review_queue (
        id INTEGER PRIMARY KEY,
        content_item_id INTEGER,
        category TEXT,
        review_decision TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE pi_ai_portfolio_assessments (
        id TEXT PRIMARY KEY,
        assessed_at TEXT DEFAULT (datetime('now')),
        overall_verdict TEXT,
        component_count INTEGER,
        healthy_count INTEGER,
        degraded_count INTEGER,
        critical_count INTEGER
    )""")
    conn.execute("""CREATE TABLE pi_framework_grades (
        id TEXT PRIMARY KEY,
        framework TEXT,
        grade TEXT,
        score REAL,
        audit_cycle_id TEXT,
        graded_at TEXT DEFAULT (datetime('now'))
    )""")
    return conn


class TestCoverageMap(unittest.TestCase):
    """Tests for the coverage map registry."""

    def test_coverage_map_has_all_domains(self):
        from mandarin.intelligence.coverage_audit import COVERAGE_MAP, DOMAINS
        map_domains = set(c["domain"] for c in COVERAGE_MAP)
        for d in DOMAINS:
            self.assertIn(d, map_domains)

    def test_coverage_map_entries_have_required_fields(self):
        from mandarin.intelligence.coverage_audit import COVERAGE_MAP
        for entry in COVERAGE_MAP:
            self.assertIn("domain", entry)
            self.assertIn("component", entry)
            self.assertIn("status", entry)
            self.assertIn(entry["status"], ("covered", "partial", "gap", "blind_spot"))


class TestCoverageSummary(unittest.TestCase):
    """Tests for get_coverage_summary."""

    def test_summary_returns_valid_dict_on_empty_db(self):
        from mandarin.intelligence.coverage_audit import get_coverage_summary
        conn = _make_db()
        result = get_coverage_summary(conn)
        self.assertIn("domains", result)
        self.assertIn("gap_count", result)
        self.assertIn("coverage_pct", result)
        self.assertIn("gaps", result)
        self.assertIn("total_components", result)

    def test_summary_counts_gaps_correctly(self):
        from mandarin.intelligence.coverage_audit import get_coverage_summary, COVERAGE_MAP
        conn = _make_db()
        result = get_coverage_summary(conn)
        expected_gaps = sum(1 for c in COVERAGE_MAP if c["status"] in ("gap", "blind_spot"))
        self.assertEqual(result["gap_count"], expected_gaps)

    def test_coverage_pct_between_0_and_100(self):
        from mandarin.intelligence.coverage_audit import get_coverage_summary
        conn = _make_db()
        result = get_coverage_summary(conn)
        self.assertGreaterEqual(result["coverage_pct"], 0)
        self.assertLessEqual(result["coverage_pct"], 100)

    def test_summary_has_all_five_domains(self):
        from mandarin.intelligence.coverage_audit import get_coverage_summary, DOMAINS
        conn = _make_db()
        result = get_coverage_summary(conn)
        for d in DOMAINS:
            self.assertIn(d, result["domains"])


class TestCoverageSnapshot(unittest.TestCase):
    """Tests for log_coverage_snapshot."""

    def test_snapshot_persists_rows(self):
        from mandarin.intelligence.coverage_audit import log_coverage_snapshot, COVERAGE_MAP
        conn = _make_db()
        rows = log_coverage_snapshot(conn)
        self.assertEqual(rows, len(COVERAGE_MAP))
        count = conn.execute("SELECT COUNT(*) FROM pi_coverage_audit_log").fetchone()[0]
        self.assertEqual(count, len(COVERAGE_MAP))


class TestGapClosurePriority(unittest.TestCase):
    """Tests for gap closure priority list."""

    def test_returns_10_items(self):
        from mandarin.intelligence.coverage_audit import get_gap_closure_priority
        result = get_gap_closure_priority()
        self.assertEqual(len(result), 10)

    def test_ordered_by_priority(self):
        from mandarin.intelligence.coverage_audit import get_gap_closure_priority
        result = get_gap_closure_priority()
        for i, item in enumerate(result):
            self.assertEqual(item["priority"], i + 1)


class TestCoverageFindings(unittest.TestCase):
    """Tests for generate_coverage_findings."""

    def test_returns_list_on_empty_db(self):
        from mandarin.intelligence.coverage_audit import generate_coverage_findings
        conn = _make_db()
        result = generate_coverage_findings(conn)
        self.assertIsInstance(result, list)
        # Should emit 3 findings (top 3 priorities)
        self.assertEqual(len(result), 3)


class TestConstraintFinder(unittest.TestCase):
    """Tests for cross-domain constraint finder."""

    def test_returns_valid_dict_on_empty_db(self):
        from mandarin.intelligence.constraint_finder import identify_cross_domain_constraint
        conn = _make_db()
        result = identify_cross_domain_constraint(conn)
        self.assertIn("constraint", result)
        self.assertIn("domain", result)
        self.assertIn("severity", result)
        self.assertIn("description", result)
        self.assertIn("all_constraints", result)
        self.assertIn("checked_at", result)

    def test_detects_pedagogical_safety_issue(self):
        from mandarin.intelligence.constraint_finder import identify_cross_domain_constraint
        conn = _make_db()
        # Inject accuracy rejections
        for i in range(3):
            conn.execute("""
                INSERT INTO pi_ai_review_queue (category, review_decision, created_at)
                VALUES ('accuracy', 'rejected', datetime('now'))
            """)
        conn.commit()
        result = identify_cross_domain_constraint(conn)
        self.assertEqual(result["domain"], "pedagogical_safety")
        self.assertEqual(result["severity"], "critical")

    def test_persists_to_constraint_history(self):
        from mandarin.intelligence.constraint_finder import identify_cross_domain_constraint
        conn = _make_db()
        # Inject a rejection to trigger persistence
        conn.execute("""
            INSERT INTO pi_ai_review_queue (category, review_decision, created_at)
            VALUES ('accuracy', 'rejected', datetime('now'))
        """)
        conn.commit()
        identify_cross_domain_constraint(conn)
        count = conn.execute("SELECT COUNT(*) FROM pi_system_constraint_history").fetchone()[0]
        self.assertGreaterEqual(count, 1)

    def test_pedagogical_safety_returns_none_when_clean(self):
        from mandarin.intelligence.constraint_finder import _check_pedagogical_safety
        conn = _make_db()
        result = _check_pedagogical_safety(conn)
        self.assertIsNone(result)

    def test_engagement_handles_empty_session_log(self):
        from mandarin.intelligence.constraint_finder import _get_engagement_health
        conn = _make_db()
        result = _get_engagement_health(conn)
        self.assertIsNone(result)

    def test_ai_portfolio_reads_assessment(self):
        from mandarin.intelligence.constraint_finder import _get_ai_portfolio_verdict
        conn = _make_db()
        conn.execute("""
            INSERT INTO pi_ai_portfolio_assessments
                (id, overall_verdict, component_count, healthy_count, degraded_count, critical_count)
            VALUES ('test', 'degraded', 5, 2, 2, 1)
        """)
        conn.commit()
        result = _get_ai_portfolio_verdict(conn)
        self.assertIsNotNone(result)
        self.assertEqual(result["domain"], "ai_health")

    def test_content_quality_handles_empty_queue(self):
        from mandarin.intelligence.constraint_finder import _get_content_quality_constraint
        conn = _make_db()
        result = _get_content_quality_constraint(conn)
        self.assertIsNone(result)

    def test_priority_order_safety_over_engagement(self):
        """Pedagogical safety (priority 0) should come before engagement (priority 2)."""
        from mandarin.intelligence.constraint_finder import identify_cross_domain_constraint
        conn = _make_db()
        # Add both a safety issue and low engagement
        conn.execute("""
            INSERT INTO pi_ai_review_queue (category, review_decision, created_at)
            VALUES ('accuracy', 'rejected', datetime('now'))
        """)
        conn.execute("""
            INSERT INTO session_log (user_id, started_at)
            VALUES (1, datetime('now', '-20 days'))
        """)
        conn.commit()
        result = identify_cross_domain_constraint(conn)
        # Primary constraint should be pedagogical safety, not engagement
        self.assertEqual(result["domain"], "pedagogical_safety")


if __name__ == "__main__":
    unittest.main()
