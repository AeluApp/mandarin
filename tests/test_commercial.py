"""Tests for Doc 19: Commercial Intelligence and Go-to-Market."""

import sqlite3
import unittest

from mandarin.db.core import SCHEMA_VERSION
from mandarin.ai.commercial import (
    generate_institutional_usage_report,
    _interpret_cohort_results,
    get_pricing_recommendation,
    analyze_commercial_intelligence,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY, email TEXT);
        INSERT INTO user (id, email) VALUES (1, 'test@aelu.app');
        INSERT INTO user (id, email) VALUES (2, 'student1@aelu.app');
        INSERT INTO user (id, email) VALUES (3, 'student2@aelu.app');

        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, content_item_id INTEGER,
            correct INTEGER, created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE memory_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_item_id INTEGER NOT NULL,
            stability REAL DEFAULT 0.4,
            state TEXT DEFAULT 'new'
        );

        CREATE TABLE learner_proficiency_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            composite_hsk_estimate REAL
        );

        CREATE TABLE cohorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE cohort_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cohort_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            active INTEGER DEFAULT 1,
            UNIQUE(cohort_id, user_id)
        );

        CREATE TABLE pi_commercial_readiness (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_name TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'pending',
            confirmed_at TEXT, notes TEXT
        );

        CREATE TABLE product_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT, score REAL, dimension_scores TEXT,
            findings TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


class TestInstitutionalUsageReport(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_member_count_correct(self):
        cohort_id = self.conn.execute(
            "INSERT INTO cohorts (name) VALUES ('Test Cohort')"
        ).lastrowid
        self.conn.execute(
            "INSERT INTO cohort_members (cohort_id, user_id) VALUES (?, 2)", (cohort_id,)
        )
        self.conn.execute(
            "INSERT INTO cohort_members (cohort_id, user_id) VALUES (?, 3)", (cohort_id,)
        )

        report = generate_institutional_usage_report(self.conn, cohort_id)
        self.assertEqual(report['member_count'], 2)

    def test_empty_cohort(self):
        cohort_id = self.conn.execute(
            "INSERT INTO cohorts (name) VALUES ('Empty')"
        ).lastrowid
        report = generate_institutional_usage_report(self.conn, cohort_id)
        self.assertEqual(report['member_count'], 0)

    def test_nonexistent_cohort(self):
        report = generate_institutional_usage_report(self.conn, 9999)
        self.assertEqual(report, {})


class TestInterpretCohortResults(unittest.TestCase):
    def test_strong_engagement(self):
        text = _interpret_cohort_results(10, 4.0, 80.0, 100, 3.5)
        self.assertIn('strong engagement', text)

    def test_moderate_engagement(self):
        text = _interpret_cohort_results(5, 2.0, 70.0, 30, 2.0)
        self.assertIn('moderate engagement', text)

    def test_low_engagement(self):
        text = _interpret_cohort_results(2, 0.5, 50.0, 10, 1.0)
        self.assertIn('Low session frequency', text)


class TestPricingRecommendation(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_not_ready_when_conditions_pending(self):
        rec = get_pricing_recommendation(self.conn)
        self.assertFalse(rec['b2c_recommendation']['ready'])
        self.assertFalse(rec['b2b_recommendation']['ready'])

    def test_b2c_ready_when_conditions_confirmed(self):
        self.conn.execute("""
            INSERT INTO pi_commercial_readiness (condition_name, status)
            VALUES ('teacher_dashboard_deployed', 'confirmed')
        """)
        self.conn.execute("""
            INSERT INTO pi_commercial_readiness (condition_name, status)
            VALUES ('student_onboarding_validated', 'confirmed')
        """)
        rec = get_pricing_recommendation(self.conn)
        self.assertTrue(rec['b2c_recommendation']['ready'])


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_active_cohort_without_report(self):
        self.conn.execute("INSERT INTO cohorts (name, active) VALUES ('Active', 1)")
        findings = analyze_commercial_intelligence(self.conn)
        cohort_findings = [f for f in findings if 'cohort' in f['title'].lower()]
        self.assertEqual(len(cohort_findings), 1)
        self.assertEqual(cohort_findings[0]['severity'], 'high')

    def test_no_cohorts_no_findings(self):
        findings = analyze_commercial_intelligence(self.conn)
        self.assertEqual(findings, [])


class TestSchemaVersion(unittest.TestCase):
    def test_schema_includes_doc19(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 82)


if __name__ == "__main__":
    unittest.main()
