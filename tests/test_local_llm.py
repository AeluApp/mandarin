"""Tests for local LLM (Ollama) integration — all HTTP mocked."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

# Ensure ai package is importable
from mandarin.ai.ollama_client import (
    is_ollama_available, generate, OllamaResponse, _prompt_hash,
)
from mandarin.ai.validation import validate_generated_content
from mandarin.ai.drill_generator import (
    _parse_drill_response, _validate_drill_item, GeneratedDrillItem,
    process_pending_encounters,
)
from mandarin.ai.error_explanation import generate_error_explanation
from mandarin.ai.health import check_ollama_health


@pytest.fixture
def conn():
    """In-memory SQLite with the AI tables."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")

    c.executescript("""
        CREATE TABLE pi_ai_generation_cache (
            id TEXT PRIMARY KEY,
            prompt_hash TEXT NOT NULL UNIQUE,
            prompt_text TEXT NOT NULL,
            system_text TEXT,
            model_used TEXT NOT NULL,
            response_text TEXT NOT NULL,
            generated_at TEXT NOT NULL DEFAULT (datetime('now')),
            hit_count INTEGER NOT NULL DEFAULT 0,
            last_hit_at TEXT
        );

        CREATE TABLE pi_ai_generation_log (
            id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
            task_type TEXT NOT NULL,
            model_used TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            generation_time_ms INTEGER,
            from_cache INTEGER NOT NULL,
            success INTEGER NOT NULL,
            error TEXT,
            finding_id TEXT,
            item_id TEXT
        );

        CREATE TABLE pi_ai_review_queue (
            id TEXT PRIMARY KEY,
            queued_at TEXT NOT NULL DEFAULT (datetime('now')),
            content_type TEXT NOT NULL,
            content_json TEXT NOT NULL,
            validation_issues TEXT,
            encounter_id TEXT,
            reviewed_at TEXT,
            reviewed_by TEXT DEFAULT 'human',
            review_decision TEXT CHECK (
                review_decision IN ('approved', 'rejected', 'edited')
            ),
            edited_content_json TEXT,
            review_notes TEXT
        );

        CREATE TABLE vocab_encounter (
            id TEXT PRIMARY KEY,
            content_item_id INTEGER,
            hanzi TEXT,
            source_type TEXT,
            source_id TEXT,
            looked_up INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            drill_generation_status TEXT DEFAULT 'pending',
            generated_item_id TEXT,
            generation_attempted_at TEXT,
            generation_error TEXT
        );

        CREATE TABLE content_item (
            id TEXT PRIMARY KEY,
            hanzi TEXT,
            pinyin TEXT,
            english TEXT,
            hsk_level INTEGER DEFAULT 1,
            status TEXT DEFAULT 'drill_ready',
            source TEXT,
            example_sentence_hanzi TEXT,
            example_sentence_pinyin TEXT,
            example_sentence_english TEXT
        );

        CREATE TABLE learner_profile (
            id INTEGER PRIMARY KEY,
            level_reading INTEGER DEFAULT 1
        );

        CREATE TABLE error_log (
            id INTEGER PRIMARY KEY,
            content_item_id INTEGER
        );
    """)
    c.execute("INSERT INTO learner_profile (id, level_reading) VALUES (1, 2)")
    c.commit()
    return c


# ── Test 1: is_ollama_available returns False gracefully ──

@patch("mandarin.ai.ollama_client.httpx.get")
def test_ollama_unavailable_returns_false(mock_get):
    mock_get.side_effect = ConnectionError("refused")
    assert is_ollama_available() is False


# ── Test 2: generate falls back to 1.5B when 7B unavailable ──

@patch("mandarin.ai.ollama_client.httpx.post")
@patch("mandarin.ai.ollama_client.is_ollama_available", return_value=True)
def test_generate_fallback(mock_avail, mock_post, conn):
    # First call (7B) fails, second call (1.5B) succeeds
    fail_resp = MagicMock()
    fail_resp.status_code = 500
    fail_resp.text = "model not found"

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {
        "response": "hello",
        "prompt_eval_count": 10,
        "eval_count": 5,
    }

    mock_post.side_effect = [fail_resp, ok_resp]

    result = generate("test prompt", conn=conn, task_type="test")
    assert result.success is True
    assert result.text == "hello"
    assert mock_post.call_count == 2


# ── Test 3: generate returns success=False on timeout ──

@patch("mandarin.ai.ollama_client.httpx.post")
def test_generate_timeout(mock_post, conn):
    import httpx
    mock_post.side_effect = httpx.TimeoutException("timeout")

    result = generate("test", conn=conn, task_type="test")
    assert result.success is False
    assert result.error == "timeout"


# ── Test 4: _parse_drill_response handles markdown fences ──

def test_parse_drill_response_markdown_fences():
    text = '```json\n{"hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello", "drill_type": "mcq"}\n```'
    item = _parse_drill_response(text, "enc-1")
    assert item is not None
    assert item.hanzi == "你好"
    assert item.pinyin == "nǐ hǎo"


# ── Test 5: _parse_drill_response returns None on malformed JSON ──

def test_parse_drill_response_malformed():
    assert _parse_drill_response("not json at all", "enc-1") is None


# ── Test 6: _validate_drill_item flags missing target word ──

def test_validate_flags_missing_target():
    item = GeneratedDrillItem(
        hanzi="你好", pinyin="nǐ hǎo", english="hello",
        drill_type="mcq", example_sentence_hanzi="我很好",
        confidence=0.9,
    )
    issues = _validate_drill_item(item, "你好", 2)
    assert any("target word" in i for i in issues)


# ── Test 7: _validate_drill_item flags low confidence ──

def test_validate_flags_low_confidence():
    item = GeneratedDrillItem(
        hanzi="你好", pinyin="nǐ hǎo", english="hello",
        drill_type="mcq", example_sentence_hanzi="你好世界",
        confidence=0.5,
    )
    issues = _validate_drill_item(item, "你好", 2)
    assert any("confidence" in i for i in issues)


# ── Test 8: validate_generated_content catches duplicate distractors ──

def test_validate_catches_duplicate_distractors():
    content = {
        "hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello",
        "drill_type": "mcq",
        "distractors": ["goodbye", "goodbye", "thanks"],
    }
    result = validate_generated_content("drill", content)
    assert "duplicate distractors" in result["validation_issues"]


# ── Test 9: validate_generated_content catches primary meaning as distractor ──

def test_validate_catches_primary_as_distractor():
    content = {
        "hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello",
        "drill_type": "mcq",
        "distractors": ["hello", "goodbye", "thanks"],
    }
    result = validate_generated_content("drill", content)
    assert "primary meaning appears as distractor" in result["validation_issues"]


# ── Test 10: error_explanation returns None for first-time errors ──

@patch("mandarin.ai.error_explanation.is_ollama_available", return_value=True)
def test_error_explanation_below_threshold(mock_avail, conn):
    result = generate_error_explanation(
        conn, item_id="1", correct_answer="你好", wrong_answer="你们",
        item_content={"hanzi": "你好"}, error_type="vocab",
        times_wrong=1, learner_hsk_level=1,
    )
    assert result is None


# ── Test 11: error_explanation checks cache before generating ──

@patch("mandarin.ai.error_explanation.generate")
@patch("mandarin.ai.error_explanation.is_ollama_available", return_value=True)
def test_error_explanation_uses_cache(mock_avail, mock_gen, conn):
    mock_gen.return_value = OllamaResponse(
        success=True, text="你好 and 你们 look similar but...",
        model_used="qwen2.5:7b", from_cache=True,
    )
    result = generate_error_explanation(
        conn, item_id="1", correct_answer="你好", wrong_answer="你们",
        item_content={"hanzi": "你好"}, error_type="tone",
        times_wrong=1, learner_hsk_level=1,
    )
    assert result is not None
    mock_gen.assert_called_once()


# ── Test 12: process_pending_encounters returns gracefully when Ollama unavailable ──

@patch("mandarin.ai.drill_generator.is_ollama_available", return_value=False)
def test_process_pending_ollama_unavailable(mock_avail, conn):
    result = process_pending_encounters(conn)
    assert result == {"processed": 0, "skipped_reason": "ollama_unavailable"}


# ── Test 13: Review queue populated when validation fails ──

@patch("mandarin.ai.drill_generator.generate")
@patch("mandarin.ai.drill_generator.is_ollama_available", return_value=True)
def test_review_queue_on_validation_failure(mock_avail, mock_gen, conn):
    # Insert a pending encounter
    enc_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO vocab_encounter (id, hanzi, drill_generation_status) VALUES (?, '你好', 'pending')",
        (enc_id,),
    )
    conn.commit()

    # LLM returns item with low confidence → validation fails → goes to review queue
    mock_gen.return_value = OllamaResponse(
        success=True,
        text=json.dumps({
            "hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello",
            "drill_type": "mcq", "confidence": 0.3,
            "example_sentence_hanzi": "我说再见",  # doesn't contain 你好
        }),
        model_used="qwen2.5:7b",
    )

    from mandarin.ai.drill_generator import generate_drill_from_encounter
    generate_drill_from_encounter(conn, enc_id, "你好", learner_hsk_level=2)

    # Should be in review queue
    row = conn.execute("SELECT COUNT(*) as cnt FROM pi_ai_review_queue").fetchone()
    assert row["cnt"] >= 1


# ── Test 14: Generation log populated for every call ──

@patch("mandarin.ai.ollama_client.httpx.post")
def test_generation_log_always_populated(mock_post, conn):
    import httpx
    mock_post.side_effect = httpx.TimeoutException("timeout")

    generate("test prompt", conn=conn, task_type="test_task")

    # Both models fail = 2 log entries (one per model attempt) — but actually
    # the log is written once at the end by generate()
    rows = conn.execute("SELECT * FROM pi_ai_generation_log").fetchall()
    assert len(rows) >= 1
    assert rows[0]["task_type"] == "test_task"


# ── Test 15: check_ollama_health returns valid dict on empty DB ──

@patch("mandarin.ai.health.is_ollama_available", return_value=False)
def test_health_empty_db(mock_avail, conn):
    result = check_ollama_health(conn)
    assert "ollama_available" in result
    assert result["ollama_available"] is False
    assert result["generation_7d"]["total"] == 0
    assert result["pending_reviews"] == 0
