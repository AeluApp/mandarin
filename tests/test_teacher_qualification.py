"""Tests for Doc 23 B-02: Teacher Pilot Qualification."""

import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.teacher_qualification import (
    add_lead,
    score_candidate,
    get_qualified_leads,
    get_all_leads,
    _deterministic_score,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE teacher_lead (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            profile_url TEXT,
            language_pair TEXT,
            teaching_style_tags TEXT,
            platform_rating REAL,
            estimated_students INTEGER,
            qualification_score REAL,
            qualification_notes TEXT,
            source_crawl_id INTEGER,
            status TEXT NOT NULL DEFAULT 'discovered',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE crawl_source (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, url TEXT NOT NULL,
            source_type TEXT NOT NULL, crawl_interval_hours INTEGER DEFAULT 24,
            last_crawl_at TEXT, active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pi_ai_generation_cache (
            id TEXT PRIMARY KEY, prompt_hash TEXT, prompt_text TEXT,
            system_text TEXT, model_used TEXT, response_text TEXT,
            generated_at TEXT, hit_count INTEGER DEFAULT 0, last_hit_at TEXT
        );
        CREATE TABLE pi_ai_generation_log (
            id TEXT PRIMARY KEY, occurred_at TEXT, task_type TEXT,
            model_used TEXT, prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0, generation_time_ms INTEGER DEFAULT 0,
            from_cache INTEGER DEFAULT 0, success INTEGER DEFAULT 1,
            error TEXT, json_parse_failure INTEGER DEFAULT 0,
            finding_id TEXT, item_id TEXT
        );
        CREATE TABLE prompt_trace (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_key TEXT, prompt_hash TEXT, input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0, latency_ms INTEGER DEFAULT 0,
            model_used TEXT, success INTEGER DEFAULT 1, error_type TEXT,
            output_quality_score REAL, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


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
