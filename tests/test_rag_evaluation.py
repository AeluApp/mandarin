"""Tests for Doc 23 2A: RAG Evaluation with FAISS + RAGAS metrics."""

import json
import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.rag_evaluation import (
    build_faiss_index,
    hybrid_retrieve,
    rebuild_index_if_stale,
    evaluate_retrieval,
    _bm25_retrieve,
)

from tests.shared_db import make_test_db

# Check if sentence-transformers model is loadable (needs HuggingFace access)
_HAS_EMBEDDING_MODEL = False
try:
    from mandarin.ai.genai_layer import _get_multilingual_model
    _model = _get_multilingual_model()
    _HAS_EMBEDDING_MODEL = _model is not None
except Exception:
    pass


def _make_db():
    conn = make_test_db()
    conn.executescript("""
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

    @unittest.skipUnless(_HAS_EMBEDDING_MODEL, "sentence-transformers model not available (needs HuggingFace)")
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
            rebuild_index_if_stale(self.conn)
            mock_build.assert_called_once()


class TestEvaluateRetrieval(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    @unittest.skipUnless(_HAS_EMBEDDING_MODEL, "sentence-transformers model not available (needs HuggingFace)")
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
