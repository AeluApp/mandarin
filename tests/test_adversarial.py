"""Tests for Doc 23 C-01: Adversarial Multi-Agent Debate."""

import json
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.adversarial import (
    run_adversarial_debate,
    batch_debate,
    get_debate_results,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE adversarial_debate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL,
            content_id INTEGER,
            content_data TEXT NOT NULL,
            critic_output TEXT,
            defender_output TEXT,
            judge_verdict TEXT,
            judge_score REAL,
            dimensions_tested TEXT,
            passed INTEGER,
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


class TestAdversarialDebate(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    @patch("mandarin.ai.ollama_client.is_ollama_available", return_value=False)
    def test_skipped_when_ollama_unavailable(self, mock_avail):
        result = run_adversarial_debate(
            self.conn,
            {"hanzi": "你好", "english": "hello"},
            "vocabulary",
        )
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "ollama_unavailable")

    @patch("mandarin.ai.ollama_client.generate")
    @patch("mandarin.ai.ollama_client.is_ollama_available", return_value=True)
    def test_full_debate_flow(self, mock_avail, mock_gen):
        # Mock three sequential Qwen calls
        mock_gen.side_effect = [
            MagicMock(success=True, text=json.dumps({
                "flaws": [{"category": "tone", "detail": "wrong tone", "severity": "medium"}],
                "overall_assessment": "has issues",
            })),
            MagicMock(success=True, text=json.dumps({
                "responses": [{"flaw": "tone", "valid": True, "evidence": "correct"}],
                "conceded_flaws": ["wrong tone"],
            })),
            MagicMock(success=True, text=json.dumps({
                "accuracy_score": 0.8,
                "naturalness_score": 0.9,
                "pedagogical_score": 0.85,
                "cultural_score": 0.95,
                "verdict": "pass",
                "reasoning": "Good quality overall",
            })),
        ]

        result = run_adversarial_debate(
            self.conn,
            {"hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello"},
            "vocabulary",
            content_id=1,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["verdict"], "pass")
        self.assertTrue(result["passed"])
        self.assertGreater(result["overall_score"], 0.7)

        # Check DB record
        row = self.conn.execute("SELECT * FROM adversarial_debate").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["judge_verdict"], "pass")
        self.assertEqual(row["passed"], 1)

    @patch("mandarin.ai.ollama_client.generate")
    @patch("mandarin.ai.ollama_client.is_ollama_available", return_value=True)
    def test_critic_failure(self, mock_avail, mock_gen):
        mock_gen.return_value = MagicMock(success=False, error="timeout")

        result = run_adversarial_debate(
            self.conn, {"hanzi": "测试"}, "vocabulary"
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["step"], "critic")


class TestBatchDebate(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    @patch("mandarin.ai.ollama_client.is_ollama_available", return_value=False)
    def test_batch_all_skipped(self, mock_avail):
        items = [
            {"hanzi": "你好", "id": 1},
            {"hanzi": "谢谢", "id": 2},
        ]
        results = batch_debate(self.conn, items, "vocabulary")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["status"] == "skipped" for r in results))


class TestGetDebateResults(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        self.conn.execute("""
            INSERT INTO adversarial_debate
            (content_type, content_data, judge_verdict, judge_score, passed)
            VALUES ('vocabulary', '{}', 'pass', 0.9, 1)
        """)

    def test_get_all_results(self):
        results = get_debate_results(self.conn)
        self.assertEqual(len(results), 1)

    def test_filter_by_type(self):
        results = get_debate_results(self.conn, content_type="vocabulary")
        self.assertEqual(len(results), 1)
        results = get_debate_results(self.conn, content_type="grammar")
        self.assertEqual(len(results), 0)

    def test_passed_only(self):
        self.conn.execute("""
            INSERT INTO adversarial_debate
            (content_type, content_data, judge_verdict, judge_score, passed)
            VALUES ('vocabulary', '{}', 'fail', 0.3, 0)
        """)
        results = get_debate_results(self.conn, passed_only=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["judge_verdict"], "pass")


if __name__ == "__main__":
    unittest.main()
