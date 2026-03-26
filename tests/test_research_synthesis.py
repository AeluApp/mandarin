"""Tests for Doc 23 B-01: Research Synthesis."""

import pytest
pytest.importorskip("httpx")

import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.research_synthesis import (
    discover_papers,
    score_relevance,
    synthesize_application,
    get_research_digest,
    _store_paper,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE research_paper (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            authors TEXT,
            abstract TEXT,
            doi TEXT,
            published_date TEXT,
            relevance_score REAL,
            applicability_analysis TEXT,
            methodology_tags TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE research_application (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            aelu_component TEXT NOT NULL,
            proposed_change TEXT NOT NULL,
            impact_estimate TEXT,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
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


class TestStorePaper(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_store_new_paper(self):
        paper_id = _store_paper(self.conn, {
            "source": "arxiv",
            "title": "Test Paper on SLA",
            "authors": "Author A, Author B",
            "abstract": "This paper studies spaced repetition.",
            "doi": "10.1234/test",
        })
        self.assertIsNotNone(paper_id)

    def test_duplicate_paper_skipped(self):
        _store_paper(self.conn, {"source": "arxiv", "title": "Duplicate"})
        result = _store_paper(self.conn, {"source": "arxiv", "title": "Duplicate"})
        self.assertIsNone(result)


class TestScoreRelevance(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_relevant_paper_high_score(self):
        paper_id = _store_paper(self.conn, {
            "source": "arxiv",
            "title": "Spaced Repetition for Mandarin Vocabulary Retention",
            "abstract": "We study FSRS-based spaced repetition for Chinese L2 vocabulary "
                        "acquisition. Tone acquisition and character recognition are improved.",
        })
        score = score_relevance(self.conn, paper_id)
        self.assertGreater(score, 0.3)

    def test_irrelevant_paper_low_score(self):
        paper_id = _store_paper(self.conn, {
            "source": "arxiv",
            "title": "Quantum Computing Advances",
            "abstract": "New breakthroughs in quantum error correction.",
        })
        score = score_relevance(self.conn, paper_id)
        self.assertLess(score, 0.3)

    def test_nonexistent_paper(self):
        score = score_relevance(self.conn, 9999)
        self.assertEqual(score, 0.0)


class TestGetResearchDigest(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_digest(self):
        digest = get_research_digest(self.conn)
        self.assertEqual(digest["papers_found"], 0)

    def test_digest_with_papers(self):
        _store_paper(self.conn, {
            "source": "arxiv",
            "title": "SLA Paper",
            "abstract": "spaced repetition",
        })
        # Need to set relevance score for it to appear
        self.conn.execute(
            "UPDATE research_paper SET relevance_score = 0.8 WHERE id = 1"
        )
        self.conn.commit()

        digest = get_research_digest(self.conn)
        self.assertEqual(digest["papers_found"], 1)


class TestDiscoverPapers(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    @patch("mandarin.ai.research_synthesis._search_arxiv", return_value=[])
    @patch("mandarin.ai.research_synthesis._search_semantic_scholar", return_value=[])
    def test_no_results(self, mock_ss, mock_arxiv):
        papers = discover_papers(self.conn)
        self.assertEqual(papers, [])


if __name__ == "__main__":
    unittest.main()
