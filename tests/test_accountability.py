"""Tests for Doc 18: Social, Accountability, and Habit Architecture."""

import unittest
from datetime import date, timedelta

from mandarin.db.core import SCHEMA_VERSION
from mandarin.ai.accountability import (
    create_weekly_commitment,
    get_commitment_status,
    evaluate_weekly_commitments,
    _current_week_start,
    analyze_accountability,
)


from tests.shared_db import make_test_db as _make_db


class TestWeeklyCommitment(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_creates_commitment(self):
        result = create_weekly_commitment(self.conn, 1, target_sessions=4, target_new_items=10)
        self.assertIn('week_start', result)
        self.assertEqual(result['target_sessions'], 4)
        self.assertIn('Committed', result['message'])

    def test_replaces_existing_commitment(self):
        create_weekly_commitment(self.conn, 1, target_sessions=3, target_new_items=5)
        create_weekly_commitment(self.conn, 1, target_sessions=5, target_new_items=15)

        week_start = _current_week_start()
        row = self.conn.execute(
            "SELECT target_sessions FROM study_commitments WHERE user_id=1 AND week_start=?",
            (week_start.isoformat(),)
        ).fetchone()
        self.assertEqual(row['target_sessions'], 5)


class TestCommitmentStatus(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_no_commitment_returns_false(self):
        status = get_commitment_status(self.conn, 1)
        self.assertFalse(status['has_commitment'])

    def test_on_track_when_ahead(self):
        create_weekly_commitment(self.conn, 1, target_sessions=4, target_new_items=10)
        # Add some sessions
        week_start = _current_week_start()
        for i in range(3):
            self.conn.execute("""
                INSERT INTO session_log (user_id, started_at, ended_at)
                VALUES (1, ?, ?)
            """, (f"{week_start.isoformat()} 10:0{i}:00",
                  f"{week_start.isoformat()} 10:2{i}:00"))

        status = get_commitment_status(self.conn, 1)
        self.assertTrue(status['has_commitment'])
        self.assertEqual(status['completed_sessions'], 3)


class TestEvaluateCommitments(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_marks_commitment_met(self):
        last_week = _current_week_start() - timedelta(days=7)
        self.conn.execute("""
            INSERT INTO study_commitments (user_id, week_start, target_sessions)
            VALUES (1, ?, 2)
        """, (last_week.isoformat(),))

        # Add completed sessions last week
        for i in range(3):
            self.conn.execute("""
                INSERT INTO session_log (user_id, started_at, ended_at)
                VALUES (1, ?, ?)
            """, (f"{last_week.isoformat()} 10:0{i}:00",
                  f"{last_week.isoformat()} 10:2{i}:00"))

        evaluate_weekly_commitments(self.conn)

        row = self.conn.execute(
            "SELECT commitment_met, completed_sessions FROM study_commitments WHERE user_id=1"
        ).fetchone()
        self.assertEqual(row['commitment_met'], 1)
        self.assertEqual(row['completed_sessions'], 3)


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_db_no_findings(self):
        findings = analyze_accountability(self.conn)
        self.assertEqual(findings, [])

    def test_low_met_rate_triggers_finding(self):
        # Insert 6 commitments within 28 days, only 1 met (17%)
        for i in range(6):
            week = (date.today() - timedelta(days=3 * i)).isoformat()
            met = 1 if i == 0 else 0
            self.conn.execute("""
                INSERT INTO study_commitments
                (user_id, week_start, target_sessions, commitment_met)
                VALUES (1, ?, 4, ?)
            """, (week, met))

        findings = analyze_accountability(self.conn)
        commitment_findings = [f for f in findings if 'commitment' in f['title'].lower()]
        self.assertEqual(len(commitment_findings), 1)
        self.assertEqual(commitment_findings[0]['severity'], 'medium')


class TestSchemaVersion(unittest.TestCase):
    def test_schema_includes_doc18(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 81)


if __name__ == "__main__":
    unittest.main()
