"""Tests for Doc 21: RAG Layer for HSK 6+ and GenAI Hardening."""

import json
import sqlite3
import tempfile
import os
import pytest

from mandarin.ai.rag_layer import (
    import_cc_cedict,
    enrich_with_example_sentences,
    retrieve_context_for_generation,
    _format_context_for_prompt,
    generate_with_rag,
    log_json_failure,
    _log_drift_risk_flag,
    run_assertions,
    _build_prompt_from_template,
    analyze_generation_failures,
    analyze_rag_coverage,
    PROMPT_REGRESSION_SUITE,
)


def _make_db():
    """Create an in-memory DB with Doc 21 schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT);
        INSERT INTO user (id, username) VALUES (1, 'test');

        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            item_type TEXT DEFAULT 'vocab',
            hsk_level INTEGER,
            content_lens TEXT,
            status TEXT DEFAULT 'drill_ready',
            difficulty REAL DEFAULT 0.5,
            times_shown INTEGER DEFAULT 0,
            times_correct INTEGER DEFAULT 0,
            is_mined_out INTEGER DEFAULT 0
        );

        CREATE TABLE rag_knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL UNIQUE,
            pinyin TEXT NOT NULL,
            cc_cedict_definitions TEXT NOT NULL,
            part_of_speech TEXT,
            usage_notes TEXT,
            traditional_form TEXT,
            hsk_level INTEGER,
            frequency_rank INTEGER,
            example_sentences TEXT,
            common_collocations TEXT,
            learner_errors TEXT,
            near_synonyms TEXT,
            drift_risk TEXT DEFAULT 'low',
            cc_cedict_version TEXT,
            last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            manually_reviewed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE rag_retrieval_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queried_at TEXT NOT NULL DEFAULT (datetime('now')),
            hanzi TEXT NOT NULL,
            retrieved INTEGER NOT NULL DEFAULT 1,
            num_examples_retrieved INTEGER NOT NULL DEFAULT 0,
            generation_prompt_key TEXT,
            generation_succeeded INTEGER,
            quality_signal REAL
        );

        CREATE TABLE json_generation_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            failed_at TEXT NOT NULL DEFAULT (datetime('now')),
            prompt_key TEXT NOT NULL,
            failure_type TEXT NOT NULL,
            prompt_length INTEGER,
            response_length INTEGER,
            response_sample TEXT
        );

        CREATE TABLE drift_risk_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
            hanzi_list TEXT NOT NULL,
            prompt_key TEXT NOT NULL,
            reviewed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE prompt_regression_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL DEFAULT (datetime('now')),
            passed INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            findings_json TEXT
        );

        CREATE TABLE pi_ai_generation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT,
            json_parse_failure INTEGER DEFAULT 0
        );
    """)
    return conn


def _seed_kb(conn):
    """Seed knowledge base with test entries."""
    conn.execute("""
        INSERT INTO rag_knowledge_base
        (hanzi, pinyin, cc_cedict_definitions, hsk_level, drift_risk,
         example_sentences, near_synonyms, learner_errors)
        VALUES ('民主', 'minzhu', '["democracy", "democratic"]', 6, 'low',
                '[{"sentence_hanzi": "民主是重要的", "source": "test"}]',
                '[{"hanzi": "自由", "distinction": "freedom vs democracy"}]',
                '[{"error_description": "confused with 民族"}]')
    """)
    conn.execute("""
        INSERT INTO rag_knowledge_base
        (hanzi, pinyin, cc_cedict_definitions, hsk_level, drift_risk)
        VALUES ('缘故', 'yuangu', '["reason", "cause"]', 7, 'low')
    """)
    conn.execute("""
        INSERT INTO rag_knowledge_base
        (hanzi, pinyin, cc_cedict_definitions, hsk_level, drift_risk)
        VALUES ('吐槽', 'tucao', '["to roast", "to mock"]', 8, 'high')
    """)
    conn.commit()


def _make_cedict_file():
    """Create a temp CC-CEDICT file for testing."""
    content = """#! version=2024-03-01
# CC-CEDICT test data
買 买 [mai3] /to buy/to purchase/
賣 卖 [mai4] /to sell/
民主 民主 [min2 zhu3] /democracy/democratic/
"""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return tmp.name


# ─────────────────────────────────────────────
# CC-CEDICT IMPORT TESTS
# ─────────────────────────────────────────────


class TestCEDICTImport:
    def test_imports_matching_items(self):
        conn = _make_db()
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) "
            "VALUES ('买', 'mai', 'to buy', 3)"
        )
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) "
            "VALUES ('民主', 'minzhu', 'democracy', 6)"
        )
        conn.commit()

        cedict_file = _make_cedict_file()
        try:
            result = import_cc_cedict(conn, cedict_file)
            assert result["imported"] == 2
            assert result["errors"] == 0

            row = conn.execute(
                "SELECT * FROM rag_knowledge_base WHERE hanzi='买'"
            ).fetchone()
            assert row is not None
            defs = json.loads(row["cc_cedict_definitions"])
            assert "to buy" in defs
        finally:
            os.unlink(cedict_file)

    def test_idempotent_update(self):
        conn = _make_db()
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) "
            "VALUES ('买', 'mai', 'to buy', 3)"
        )
        conn.commit()

        cedict_file = _make_cedict_file()
        try:
            import_cc_cedict(conn, cedict_file)
            import_cc_cedict(conn, cedict_file)  # Should update, not duplicate
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM rag_knowledge_base WHERE hanzi='买'"
            ).fetchone()["cnt"]
            assert count == 1
        finally:
            os.unlink(cedict_file)

    def test_skips_non_hsk_items(self):
        conn = _make_db()
        # No content_items seeded, so nothing matches
        cedict_file = _make_cedict_file()
        try:
            result = import_cc_cedict(conn, cedict_file)
            assert result["imported"] == 0
            assert result["skipped"] > 0
        finally:
            os.unlink(cedict_file)

    def test_missing_file(self):
        conn = _make_db()
        result = import_cc_cedict(conn, "/nonexistent/cedict.txt")
        assert "error" in result


# ─────────────────────────────────────────────
# RETRIEVAL TESTS
# ─────────────────────────────────────────────


class TestRetrieval:
    def test_retrieves_known_items(self):
        conn = _make_db()
        _seed_kb(conn)
        result = retrieve_context_for_generation(conn, ["民主"], "test_prompt")
        assert len(result["items_found"]) == 1
        assert result["items_found"][0]["hanzi"] == "民主"
        assert len(result["items_missing"]) == 0
        assert result["context_text"] != ""

    def test_returns_missing_for_unknown(self):
        conn = _make_db()
        _seed_kb(conn)
        result = retrieve_context_for_generation(conn, ["不存在"], "test_prompt")
        assert len(result["items_found"]) == 0
        assert "不存在" in result["items_missing"]

    def test_logs_retrieval(self):
        conn = _make_db()
        _seed_kb(conn)
        retrieve_context_for_generation(conn, ["民主", "unknown"], "test_prompt")
        logs = conn.execute("SELECT * FROM rag_retrieval_log").fetchall()
        assert len(logs) == 2
        retrieved_counts = [l["retrieved"] for l in logs]
        assert 1 in retrieved_counts
        assert 0 in retrieved_counts


# ─────────────────────────────────────────────
# FORMAT CONTEXT TESTS
# ─────────────────────────────────────────────


class TestFormatContext:
    def test_includes_definitions(self):
        found = [{
            "hanzi": "民主", "pinyin": "minzhu",
            "definitions": ["democracy", "democratic"],
            "examples": [], "near_synonyms": [],
            "learner_errors": [], "drift_risk": "low",
        }]
        text = _format_context_for_prompt(found, [])
        assert "民主" in text
        assert "democracy" in text

    def test_flags_drift_risk(self):
        found = [{
            "hanzi": "吐槽", "pinyin": "tucao",
            "definitions": ["to roast"],
            "examples": [], "near_synonyms": [],
            "learner_errors": [], "drift_risk": "high",
        }]
        text = _format_context_for_prompt(found, [])
        assert "conservative" in text.lower()

    def test_includes_missing_items(self):
        text = _format_context_for_prompt([], ["不存在"])
        assert "不存在" in text
        assert "caution" in text.lower()

    def test_empty_returns_empty(self):
        assert _format_context_for_prompt([], []) == ""


# ─────────────────────────────────────────────
# G6 FAILURE LOGGING TESTS
# ─────────────────────────────────────────────


class TestFailureLogging:
    def test_logs_json_failure(self):
        conn = _make_db()
        log_json_failure(conn, "test_prompt", "prompt text", "bad json response")
        row = conn.execute(
            "SELECT * FROM json_generation_failures"
        ).fetchone()
        assert row is not None
        assert row["prompt_key"] == "test_prompt"
        assert row["failure_type"] == "invalid_json"
        assert row["response_sample"] == "bad json response"

    def test_logs_empty_response(self):
        conn = _make_db()
        log_json_failure(conn, "test_prompt", "prompt", "", failure_type="empty_response")
        row = conn.execute(
            "SELECT * FROM json_generation_failures"
        ).fetchone()
        assert row["failure_type"] == "empty_response"
        assert row["response_length"] == 0

    def test_truncates_long_response(self):
        conn = _make_db()
        long_response = "x" * 1000
        log_json_failure(conn, "test", "p", long_response)
        row = conn.execute(
            "SELECT * FROM json_generation_failures"
        ).fetchone()
        assert len(row["response_sample"]) == 500

    def test_drift_risk_flag(self):
        conn = _make_db()
        _log_drift_risk_flag(conn, ["吐槽", "网红"], "test_prompt")
        row = conn.execute("SELECT * FROM drift_risk_flags").fetchone()
        assert row is not None
        parsed = json.loads(row["hanzi_list"])
        assert "吐槽" in parsed


# ─────────────────────────────────────────────
# ASSERTION ENGINE TESTS
# ─────────────────────────────────────────────


class TestAssertions:
    def test_field_present_passes(self):
        parsed = {"question": "test", "correct_answer": "yes"}
        failures = run_assertions(parsed, [("field_present", "question")])
        assert failures == []

    def test_field_present_fails(self):
        parsed = {"question": "test"}
        failures = run_assertions(parsed, [("field_present", "missing_field")])
        assert len(failures) == 1

    def test_value_range_passes(self):
        parsed = {"score": 75}
        failures = run_assertions(parsed, [("value_range", "score", 0, 100)])
        assert failures == []

    def test_value_range_fails(self):
        parsed = {"score": 150}
        failures = run_assertions(parsed, [("value_range", "score", 0, 100)])
        assert len(failures) == 1

    def test_value_less_than(self):
        parsed = {"score": 50}
        assert run_assertions(parsed, [("value_less_than", "score", 70)]) == []
        assert len(run_assertions(parsed, [("value_less_than", "score", 30)])) == 1

    def test_value_greater_than(self):
        parsed = {"score": 80}
        assert run_assertions(parsed, [("value_greater_than", "score", 60)]) == []
        assert len(run_assertions(parsed, [("value_greater_than", "score", 90)])) == 1

    def test_list_length_gte(self):
        parsed = {"distractors": ["a", "b", "c"]}
        assert run_assertions(parsed, [("list_length_gte", "distractors", 2)]) == []
        assert len(run_assertions(parsed, [("list_length_gte", "distractors", 5)])) == 1

    def test_field_length_gte(self):
        parsed = {"summary": "This is a test summary with enough length"}
        assert run_assertions(parsed, [("field_length_gte", "summary", 20)]) == []
        assert len(run_assertions(parsed, [("field_length_gte", "summary", 100)])) == 1

    def test_field_value_in(self):
        parsed = {"error_shape": "tonal"}
        assert run_assertions(parsed, [
            ("field_value_in", "error_shape", ["tonal", "lexical"])
        ]) == []
        assert len(run_assertions(parsed, [
            ("field_value_in", "error_shape", ["grammar"])
        ])) == 1

    def test_field_contains(self):
        parsed = {"answer": "民主是重要的"}
        assert run_assertions(parsed, [("field_contains", "answer", "民主")]) == []

    def test_no_field_contains(self):
        parsed = {"question": "What is 民主?"}
        assert run_assertions(parsed, [("no_field_contains", "question", "democracy")]) == []


# ─────────────────────────────────────────────
# TEMPLATE BUILDING
# ─────────────────────────────────────────────


class TestTemplateBuild:
    def test_simple_format(self):
        template = "Generate a drill for {hanzi} ({pinyin})"
        result = _build_prompt_from_template(template, {"hanzi": "买", "pinyin": "mai"})
        assert "买" in result
        assert "mai" in result

    def test_missing_keys_handled(self):
        template = "Generate for {hanzi} at level {hsk_level}"
        result = _build_prompt_from_template(template, {"hanzi": "买"})
        assert "买" in result


# ─────────────────────────────────────────────
# ANALYZER TESTS
# ─────────────────────────────────────────────


class TestAnalyzers:
    def test_failure_findings_on_high_count(self):
        conn = _make_db()
        for _ in range(10):
            conn.execute("""
                INSERT INTO json_generation_failures
                (prompt_key, failure_type, prompt_length, response_length)
                VALUES ('bad_prompt', 'invalid_json', 100, 50)
            """)
        conn.commit()

        findings = analyze_generation_failures(conn)
        failure_findings = [f for f in findings if "bad_prompt" in f["title"]]
        assert len(failure_findings) == 1

    def test_drift_risk_finding(self):
        conn = _make_db()
        conn.execute("""
            INSERT INTO drift_risk_flags (hanzi_list, prompt_key, reviewed)
            VALUES ('["吐槽"]', 'test', 0)
        """)
        conn.commit()

        findings = analyze_generation_failures(conn)
        drift_findings = [f for f in findings if "drift" in f["title"].lower()]
        assert len(drift_findings) == 1

    def test_rag_coverage_missing_items(self):
        conn = _make_db()
        # Add HSK 6+ content_item with no KB entry
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) "
            "VALUES ('新词', 'xinci', 'neologism', 7)"
        )
        conn.commit()

        findings = analyze_rag_coverage(conn)
        missing = [f for f in findings if "not in RAG" in f["title"]]
        assert len(missing) == 1

    def test_no_findings_when_healthy(self):
        conn = _make_db()
        findings = analyze_generation_failures(conn)
        assert findings == []
        findings = analyze_rag_coverage(conn)
        assert findings == []

    def test_retrieval_miss_rate_finding(self):
        conn = _make_db()
        # 20 retrievals, 4 misses (20% > 15% threshold)
        for i in range(16):
            conn.execute("""
                INSERT INTO rag_retrieval_log (hanzi, retrieved) VALUES ('word', 1)
            """)
        for i in range(4):
            conn.execute("""
                INSERT INTO rag_retrieval_log (hanzi, retrieved) VALUES ('missing', 0)
            """)
        conn.commit()

        findings = analyze_rag_coverage(conn)
        miss_findings = [f for f in findings if "miss rate" in f["title"].lower()]
        assert len(miss_findings) == 1


# ─────────────────────────────────────────────
# ENRICHMENT TEST
# ─────────────────────────────────────────────


class TestEnrichment:
    def test_enriches_from_corpus(self):
        conn = _make_db()
        # Add KB entry without examples
        conn.execute("""
            INSERT INTO rag_knowledge_base
            (hanzi, pinyin, cc_cedict_definitions, hsk_level)
            VALUES ('民主', 'minzhu', '["democracy"]', 6)
        """)
        # Add a sentence containing the word
        conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, hsk_level, item_type)
            VALUES ('民主是重要的', 'minzhu shi zhongyao de', 'Democracy is important', 6, 'sentence')
        """)
        conn.commit()

        result = enrich_with_example_sentences(conn, min_hsk_level=5)
        assert result["enriched"] == 1

        row = conn.execute(
            "SELECT example_sentences FROM rag_knowledge_base WHERE hanzi='民主'"
        ).fetchone()
        examples = json.loads(row["example_sentences"])
        assert len(examples) >= 1


# ─────────────────────────────────────────────
# SCHEMA MIGRATION TEST
# ─────────────────────────────────────────────


class TestSchemaMigration:
    def test_migration_creates_tables(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE content_item (id INTEGER PRIMARY KEY);
            CREATE TABLE user (id INTEGER PRIMARY KEY);
        """)

        from mandarin.db.core import _migrate_v75_to_v76
        _migrate_v75_to_v76(conn)

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "rag_knowledge_base" in tables
        assert "rag_retrieval_log" in tables
        assert "json_generation_failures" in tables
        assert "drift_risk_flags" in tables
        assert "prompt_regression_log" in tables

    def test_migration_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE content_item (id INTEGER PRIMARY KEY);
            CREATE TABLE user (id INTEGER PRIMARY KEY);
        """)

        from mandarin.db.core import _migrate_v75_to_v76
        _migrate_v75_to_v76(conn)
        _migrate_v75_to_v76(conn)  # Should not error
