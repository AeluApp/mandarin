"""Tests for Doc 23 B-02: Teacher Pilot Qualification."""

import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.teacher_qualification import (
    add_lead,
    score_candidate,
    get_qualified_leads,
    get_all_leads,
    _deterministic_score,
)


from tests.shared_db import make_test_db as _make_db


class TestAddLead(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_add_basic_lead(self):
        lead_id = add_lead(
            self.conn,
            name="Test Teacher",
            platform="italki",
            language_pair="zh-en",
        )
        self.assertIsNotNone(lead_id)

        row = self.conn.execute(
            "SELECT * FROM teacher_lead WHERE id = ?", (lead_id,)
        ).fetchone()
        self.assertEqual(row["name"], "Test Teacher")
        self.assertEqual(row["platform"], "italki")
        self.assertEqual(row["status"], "discovered")

    def test_add_lead_with_all_fields(self):
        lead_id = add_lead(
            self.conn,
            name="Expert Teacher",
            platform="preply",
            profile_url="https://preply.com/teacher/123",
            language_pair="zh-en",
            teaching_style_tags=["communicative", "structured"],
            platform_rating=4.9,
            estimated_students=150,
        )
        self.assertIsNotNone(lead_id)


class TestDeterministicScore(unittest.TestCase):
    def test_base_score(self):
        lead = MagicMock()
        lead.__getitem__ = lambda s, k: {
            "platform_rating": None,
            "estimated_students": None,
            "language_pair": None,
        }.get(k)
        score = _deterministic_score(lead)
        self.assertEqual(score, 0.5)

    def test_high_rating_boost(self):
        lead = MagicMock()
        lead.__getitem__ = lambda s, k: {
            "platform_rating": 4.9,
            "estimated_students": None,
            "language_pair": "zh-en",
        }.get(k)
        score = _deterministic_score(lead)
        self.assertGreater(score, 0.7)


class TestScoreCandidate(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    @patch("mandarin.ai.ollama_client.is_ollama_available", return_value=False)
    def test_deterministic_fallback(self, mock_avail):
        lead_id = add_lead(self.conn, "Test", "italki",
                           platform_rating=4.8, language_pair="zh-en")
        score = score_candidate(self.conn, lead_id)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0.5)

        # Check status was updated
        lead = self.conn.execute(
            "SELECT * FROM teacher_lead WHERE id = ?", (lead_id,)
        ).fetchone()
        self.assertIn(lead["status"], ("qualified", "disqualified"))

    def test_nonexistent_lead(self):
        score = score_candidate(self.conn, 9999)
        self.assertIsNone(score)


class TestGetQualifiedLeads(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_results(self):
        leads = get_qualified_leads(self.conn)
        self.assertEqual(leads, [])

    def test_qualified_leads(self):
        add_lead(self.conn, "Good Teacher", "italki")
        self.conn.execute(
            "UPDATE teacher_lead SET qualification_score = 0.85, status = 'qualified'"
        )
        self.conn.commit()

        leads = get_qualified_leads(self.conn)
        self.assertEqual(len(leads), 1)

    def test_min_score_filter(self):
        add_lead(self.conn, "OK Teacher", "italki")
        self.conn.execute(
            "UPDATE teacher_lead SET qualification_score = 0.6, status = 'discovered'"
        )
        self.conn.commit()

        leads = get_qualified_leads(self.conn, min_score=0.7)
        self.assertEqual(len(leads), 0)

        leads = get_qualified_leads(self.conn, min_score=0.5)
        self.assertEqual(len(leads), 1)


class TestGetAllLeads(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty(self):
        leads = get_all_leads(self.conn)
        self.assertEqual(leads, [])

    def test_filter_by_status(self):
        add_lead(self.conn, "A", "italki")
        add_lead(self.conn, "B", "preply")
        self.conn.execute(
            "UPDATE teacher_lead SET status = 'contacted' WHERE name = 'B'"
        )
        self.conn.commit()

        leads = get_all_leads(self.conn, status="discovered")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["name"], "A")


if __name__ == "__main__":
    unittest.main()
