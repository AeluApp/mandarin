"""Tests for Doc 23 2A: RAG Evaluation with FAISS + RAGAS metrics."""

import json
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.rag_evaluation import (
    build_faiss_index,
    hybrid_retrieve,
    rebuild_index_if_stale,
    evaluate_retrieval,
    _bm25_retrieve,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL, pinyin TEXT, english TEXT,
            hsk_level INTEGER, status TEXT DEFAULT 'drill_ready'
        );
        CREATE TABLE grammar_point (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, name_zh TEXT, description TEXT
        );
        CREATE TABLE rag_faiss_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            index_name TEXT NOT NULL UNIQUE,
            dimension INTEGER NOT NULL,
            num_vectors INTEGER NOT NULL DEFAULT 0,
            built_at TEXT NOT NULL DEFAULT (datetime('now')),
            index_path TEXT NOT NULL
        );
        CREATE TABLE rag_evaluation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            retrieved_count INTEGER NOT NULL DEFAULT 0,
            faithfulness_score REAL,
            relevance_score REAL,
            context_precision_score REAL,
            generation_prompt_key TEXT,
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

        INSERT INTO content_item (hanzi, pinyin, english, hsk_level)
        VALUES ('你好', 'nǐ hǎo', 'hello', 1);
        INSERT INTO content_item (hanzi, pinyin, english, hsk_level)
        VALUES ('谢谢', 'xiè xiè', 'thank you', 1);
        INSERT INTO content_item (hanzi, pinyin, english, hsk_level)
        VALUES ('再见', 'zài jiàn', 'goodbye', 1);
    """)
    return conn


class TestBM25Retrieve(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_basic_search(self):
        results = _bm25_retrieve(self.conn, "hello")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["hanzi"], "你好")

    def test_chinese_search(self):
        results = _bm25_retrieve(self.conn, "谢谢")
        self.assertEqual(len(results), 1)

    def test_empty_query(self):
        results = _bm25_retrieve(self.conn, "")
        self.assertEqual(results, [])


class TestHybridRetrieve(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_bm25_fallback(self):
        """When FAISS unavailable, falls back to BM25."""
        results = hybrid_retrieve(self.conn, "hello", top_k=5)
        self.assertGreaterEqual(len(results), 1)


class TestBuildFaissIndex(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_no_faiss_skips(self):
        with patch("mandarin.ai.rag_evaluation._HAS_FAISS", False):
            result = build_faiss_index(self.conn)
            self.assertEqual(result["status"], "skipped")

    def test_no_numpy_skips(self):
        with patch("mandarin.ai.rag_evaluation._HAS_NUMPY", False):
            result = build_faiss_index(self.conn)
            self.assertEqual(result["status"], "skipped")


class TestRebuildIfStale(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_no_index_triggers_build(self):
        with patch("mandarin.ai.rag_evaluation.build_faiss_index") as mock_build:
            mock_build.return_value = {"status": "completed"}
            result = rebuild_index_if_stale(self.conn)
            mock_build.assert_called_once()


class TestEvaluateRetrieval(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_evaluation_logged(self):
        result = evaluate_retrieval(
            self.conn,
            query="hello",
            retrieved_docs=[{"hanzi": "你好", "english": "hello"}],
        )
        self.assertEqual(result["retrieved_count"], 1)

        # Check log entry
        row = self.conn.execute(
            "SELECT * FROM rag_evaluation_log"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["query"], "hello")


if __name__ == "__main__":
    unittest.main()
