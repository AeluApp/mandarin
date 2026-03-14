"""Tests for GenAI layer (Doc 12) — session intelligence, corpus analysis,
generative feedback, prompt registry, embeddings, whisper pronunciation."""

import json
import sqlite3
import unittest
from unittest.mock import patch, MagicMock


def _make_db():
    """Create in-memory DB with GenAI tables + dependencies."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT, pinyin TEXT, english TEXT,
            hsk_level INTEGER DEFAULT 1,
            status TEXT DEFAULT 'drill_ready',
            usage_map TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            content_item_id INTEGER,
            session_id INTEGER,
            score INTEGER DEFAULT 0,
            given_answer TEXT,
            correct_answer TEXT,
            response_ms INTEGER DEFAULT 1000,
            drill_type TEXT DEFAULT 'hanzi_to_english',
            reviewed_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (content_item_id) REFERENCES content_item(id)
        )
    """)
    conn.execute("""
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE tutor_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tutor_session_id INTEGER NOT NULL,
            wrong_form TEXT NOT NULL,
            correct_form TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE speaking_practice_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            session_id INTEGER,
            prompt_type TEXT NOT NULL DEFAULT 'read_aloud',
            target_zh TEXT NOT NULL,
            expected_zh TEXT NOT NULL DEFAULT '',
            whisper_transcription TEXT,
            tone_accuracy REAL,
            character_accuracy REAL,
            overall_score REAL,
            error_types TEXT,
            audio_duration_seconds REAL,
            whisper_confidence REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE genai_prompt_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_key TEXT NOT NULL UNIQUE,
            prompt_text TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE genai_session_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL DEFAULT 1,
            analysis_type TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE genai_item_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_item_id INTEGER NOT NULL UNIQUE,
            embedding BLOB NOT NULL,
            model_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (content_item_id) REFERENCES content_item(id)
        )
    """)
    conn.execute("""
        CREATE TABLE pi_ai_generation_log (
            id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
            task_type TEXT NOT NULL,
            model_used TEXT NOT NULL DEFAULT 'test',
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            generation_time_ms INTEGER,
            from_cache INTEGER NOT NULL DEFAULT 0,
            success INTEGER NOT NULL DEFAULT 1,
            error TEXT,
            finding_id TEXT,
            item_id TEXT,
            json_parse_failure INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE schema_version (
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _seed_items(conn, count=10):
    """Seed content items."""
    for i in range(1, count + 1):
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?,?,?,?)",
            (f"字{i}", f"zi{i}", f"word{i}", (i % 3) + 1),
        )
    conn.commit()


def _seed_reviews(conn, session_id=1, correct=5, incorrect=5):
    """Seed review events."""
    conn.execute("INSERT INTO session_log (id) VALUES (?)", (session_id,))
    for i in range(1, correct + incorrect + 1):
        score = 1 if i <= correct else 0
        conn.execute(
            """INSERT INTO review_event
               (content_item_id, session_id, score, given_answer, correct_answer, response_ms, drill_type)
               VALUES (?,?,?,?,?,?,?)""",
            (min(i, 10), session_id, score, f"ans{i}", f"correct{i}", 800 + i * 100, "hanzi_to_english"),
        )
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════
# Schema / Migration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaMigration(unittest.TestCase):

    def test_schema_version_bumped(self):
        from mandarin.db.core import SCHEMA_VERSION
        self.assertGreaterEqual(SCHEMA_VERSION, 73)

    def test_migration_registered(self):
        from mandarin.db.core import MIGRATIONS
        self.assertIn(72, MIGRATIONS)

    def test_migration_creates_tables(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Create prereq tables
        conn.execute("CREATE TABLE content_item (id INTEGER PRIMARY KEY, status TEXT, usage_map TEXT)")
        conn.execute("""CREATE TABLE pi_ai_generation_log (
            id TEXT PRIMARY KEY, task_type TEXT, model_used TEXT,
            occurred_at TEXT DEFAULT (datetime('now')),
            from_cache INTEGER DEFAULT 0, success INTEGER DEFAULT 1
        )""")
        conn.execute("""CREATE TABLE ai_component_registry (
            id TEXT PRIMARY KEY, component_name TEXT UNIQUE
        )""")
        conn.execute("INSERT INTO ai_component_registry VALUES ('1', 'abandonment_risk_model')")
        conn.commit()
        from mandarin.db.core import _migrate_v72_to_v73
        _migrate_v72_to_v73(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        self.assertIn("genai_prompt_registry", tables)
        self.assertIn("genai_session_analysis", tables)
        self.assertIn("genai_item_embeddings", tables)
        # T6: rename check
        row = conn.execute(
            "SELECT component_name FROM ai_component_registry WHERE id='1'"
        ).fetchone()
        self.assertEqual(row[0], "abandonment_risk_heuristic")


# ═══════════════════════════════════════════════════════════════════════════
# Session Intelligence Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionIntelligence(unittest.TestCase):

    def test_classify_error_shapes_empty(self):
        from mandarin.ai.genai_layer import classify_error_shapes
        conn = _make_db()
        _seed_items(conn)
        result = classify_error_shapes(conn, session_id=999)
        self.assertEqual(result["other"], 0)

    def test_classify_error_shapes_with_errors(self):
        from mandarin.ai.genai_layer import classify_error_shapes
        conn = _make_db()
        _seed_items(conn)
        _seed_reviews(conn, session_id=1, correct=3, incorrect=7)
        result = classify_error_shapes(conn, session_id=1)
        total_errors = sum(result.values())
        self.assertEqual(total_errors, 7)

    def test_diagnose_session_empty(self):
        from mandarin.ai.genai_layer import diagnose_session
        conn = _make_db()
        result = diagnose_session(conn, session_id=999)
        self.assertEqual(result["total_reviews"], 0)

    def test_diagnose_session_with_data(self):
        from mandarin.ai.genai_layer import diagnose_session
        conn = _make_db()
        _seed_items(conn)
        _seed_reviews(conn, session_id=1, correct=6, incorrect=4)
        result = diagnose_session(conn, session_id=1)
        self.assertEqual(result["total_reviews"], 10)
        self.assertAlmostEqual(result["accuracy"], 0.6, places=2)
        self.assertIn("drill_type_breakdown", result)
        self.assertIn("error_shapes", result)

    def test_analyze_tutor_session(self):
        from mandarin.ai.genai_layer import analyze_tutor_session
        conn = _make_db()
        conn.execute("INSERT INTO tutor_corrections (tutor_session_id, wrong_form, correct_form) VALUES (1, '我去学校', '我去了学校')")
        conn.execute("INSERT INTO tutor_corrections (tutor_session_id, wrong_form, correct_form) VALUES (1, '他很高兴', '他很开心')")
        conn.commit()
        result = analyze_tutor_session(conn, tutor_session_id=1)
        self.assertEqual(result["correction_count"], 2)
        self.assertEqual(len(result["corrections"]), 2)


# ═══════════════════════════════════════════════════════════════════════════
# Corpus Intelligence Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCorpusIntelligence(unittest.TestCase):

    def test_analyze_corpus_coverage_empty(self):
        from mandarin.ai.genai_layer import analyze_corpus_coverage
        conn = _make_db()
        result = analyze_corpus_coverage(conn)
        self.assertEqual(result["total_items"], 0)
        self.assertIn("static_baselines", result)

    def test_analyze_corpus_coverage_with_items(self):
        from mandarin.ai.genai_layer import analyze_corpus_coverage
        conn = _make_db()
        _seed_items(conn)
        result = analyze_corpus_coverage(conn)
        self.assertEqual(result["total_items"], 10)
        self.assertIn("hsk_distribution", result)
        self.assertIn("static_baselines", result)
        self.assertIn("measured_at", result["static_baselines"])

    def test_populate_usage_maps_ollama_unavailable(self):
        from mandarin.ai.genai_layer import populate_usage_maps
        conn = _make_db()
        _seed_items(conn)
        with patch("mandarin.ai.ollama_client.is_ollama_available", return_value=False):
            result = populate_usage_maps(conn)
        self.assertEqual(result["status"], "skipped")

    def test_usage_map_pct(self):
        from mandarin.ai.genai_layer import analyze_corpus_coverage
        conn = _make_db()
        _seed_items(conn, count=10)
        # Populate 3 usage maps
        for i in range(1, 4):
            conn.execute("UPDATE content_item SET usage_map = ? WHERE id = ?",
                         (json.dumps({"test": True}), i))
        conn.commit()
        result = analyze_corpus_coverage(conn)
        self.assertAlmostEqual(result["usage_map_pct"], 30.0, places=1)


# ═══════════════════════════════════════════════════════════════════════════
# Generative Feedback Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerativeFeedback(unittest.TestCase):

    def test_learning_insight_too_few_reviews(self):
        from mandarin.ai.genai_layer import generate_learning_insight
        conn = _make_db()
        result = generate_learning_insight(conn, user_id=1, lookback_days=7)
        self.assertIsNone(result)

    def test_explain_error_batch_empty(self):
        from mandarin.ai.genai_layer import explain_error_batch
        conn = _make_db()
        result = explain_error_batch(conn, item_ids=[])
        self.assertEqual(result, [])

    def test_parse_llm_json_valid(self):
        from mandarin.ai.genai_layer import _parse_llm_json
        result = _parse_llm_json('```json\n{"key": "value"}\n```')
        self.assertEqual(result, {"key": "value"})


# ═══════════════════════════════════════════════════════════════════════════
# Prompt Registry Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptRegistry(unittest.TestCase):

    def test_get_prompt_exists(self):
        from mandarin.ai.genai_layer import get_prompt
        result = get_prompt("usage_map_generation")
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "corpus")

    def test_get_prompt_missing(self):
        from mandarin.ai.genai_layer import get_prompt
        result = get_prompt("nonexistent_prompt")
        self.assertIsNone(result)

    def test_seed_prompt_registry(self):
        from mandarin.ai.genai_layer import seed_prompt_registry, PROMPT_REGISTRY
        conn = _make_db()
        seeded = seed_prompt_registry(conn)
        self.assertEqual(seeded, len(PROMPT_REGISTRY))
        # Idempotent: second call seeds 0
        seeded2 = seed_prompt_registry(conn)
        self.assertEqual(seeded2, 0)

    def test_detect_prompt_regressions_none(self):
        from mandarin.ai.genai_layer import seed_prompt_registry, detect_prompt_regressions
        conn = _make_db()
        seed_prompt_registry(conn)
        findings = detect_prompt_regressions(conn)
        self.assertEqual(len(findings), 0)


# ═══════════════════════════════════════════════════════════════════════════
# Embedding Layer Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEmbeddingLayer(unittest.TestCase):

    def test_compute_embeddings_no_sentence_transformers(self):
        from mandarin.ai.genai_layer import compute_item_embeddings
        conn = _make_db()
        _seed_items(conn)
        with patch("mandarin.ai.genai_layer._get_multilingual_model", side_effect=ImportError("no module")):
            result = compute_item_embeddings(conn)
        self.assertEqual(result["status"], "skipped")

    def test_find_similar_items_no_model(self):
        from mandarin.ai.genai_layer import find_similar_items
        conn = _make_db()
        with patch("mandarin.ai.genai_layer._get_multilingual_model", side_effect=ImportError("no module")):
            result = find_similar_items(conn, "你好")
        self.assertEqual(result, [])

    def test_compute_embeddings_mock_model(self):
        import numpy as np
        from mandarin.ai.genai_layer import compute_item_embeddings
        conn = _make_db()
        _seed_items(conn, count=3)
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(3, 768).astype(np.float32)
        with patch("mandarin.ai.genai_layer._get_multilingual_model", return_value=mock_model):
            result = compute_item_embeddings(conn, content_item_ids=[1, 2, 3])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["computed"], 3)

    def test_find_similar_items_with_data(self):
        import numpy as np
        from mandarin.ai.genai_layer import compute_item_embeddings, find_similar_items
        conn = _make_db()
        _seed_items(conn, count=3)
        mock_model = MagicMock()
        embeddings = np.random.rand(3, 768).astype(np.float32)
        mock_model.encode.return_value = embeddings
        with patch("mandarin.ai.genai_layer._get_multilingual_model", return_value=mock_model):
            compute_item_embeddings(conn, content_item_ids=[1, 2, 3])
            # For query, return single embedding
            mock_model.encode.return_value = embeddings[:1]
            results = find_similar_items(conn, "字1")
        self.assertGreater(len(results), 0)
        self.assertIn("similarity", results[0])


# ═══════════════════════════════════════════════════════════════════════════
# Whisper Pronunciation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestWhisperPronunciation(unittest.TestCase):

    def test_pronunciation_feedback_no_session(self):
        from mandarin.ai.genai_layer import generate_pronunciation_feedback
        conn = _make_db()
        result = generate_pronunciation_feedback(conn, session_id=1, practice_session_id=999)
        self.assertIsNone(result)

    def test_pronunciation_feedback_good_score(self):
        from mandarin.ai.genai_layer import generate_pronunciation_feedback
        conn = _make_db()
        conn.execute("""
            INSERT INTO speaking_practice_sessions
            (id, session_id, prompt_type, target_zh, overall_score, tone_accuracy, character_accuracy)
            VALUES (1, 1, 'read_aloud', '你好', 0.95, 0.9, 1.0)
        """)
        conn.commit()
        result = generate_pronunciation_feedback(conn, session_id=1, practice_session_id=1)
        self.assertIsNone(result)  # Score >= 0.8, no feedback needed


# ═══════════════════════════════════════════════════════════════════════════
# GenAI Audit Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestGenAIAudit(unittest.TestCase):

    def test_corpus_coverage_findings_empty(self):
        from mandarin.intelligence.genai_audit import analyze_corpus_coverage_findings
        conn = _make_db()
        findings = analyze_corpus_coverage_findings(conn)
        self.assertEqual(len(findings), 0)

    def test_prompt_performance_no_failures(self):
        from mandarin.intelligence.genai_audit import analyze_prompt_performance
        conn = _make_db()
        findings = analyze_prompt_performance(conn)
        self.assertEqual(len(findings), 0)

    def test_prompt_performance_high_failure_rate(self):
        from mandarin.intelligence.genai_audit import analyze_prompt_performance
        conn = _make_db()
        import uuid
        for i in range(10):
            conn.execute(
                "INSERT INTO pi_ai_generation_log (id, task_type, json_parse_failure) VALUES (?, ?, ?)",
                (str(uuid.uuid4()), "test", 1 if i < 5 else 0),
            )
        conn.commit()
        findings = analyze_prompt_performance(conn)
        failure_findings = [f for f in findings if "parse failure" in f.get("title", "").lower()]
        self.assertGreater(len(failure_findings), 0)


# ═══════════════════════════════════════════════════════════════════════════
# JSON Parse Utility Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestJSONParse(unittest.TestCase):

    def test_parse_plain_json(self):
        from mandarin.ai.genai_layer import _parse_llm_json
        result = _parse_llm_json('{"a": 1}')
        self.assertEqual(result, {"a": 1})

    def test_parse_fenced_json(self):
        from mandarin.ai.genai_layer import _parse_llm_json
        result = _parse_llm_json('```json\n{"a": 1}\n```')
        self.assertEqual(result, {"a": 1})

    def test_parse_invalid_json(self):
        from mandarin.ai.genai_layer import _parse_llm_json
        result = _parse_llm_json('not json at all')
        self.assertIsNone(result)

    def test_parse_empty(self):
        from mandarin.ai.genai_layer import _parse_llm_json
        result = _parse_llm_json('')
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
