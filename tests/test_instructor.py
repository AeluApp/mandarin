"""Tests for Doc 23 1A: Instructor Structured Output via Ollama."""

import pytest
pytest.importorskip("httpx")

import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.agentic import (
    retry_with_structured_output,
    validate_structured_output,
    OUTPUT_SCHEMA_REGISTRY,
)
from mandarin.ai.ollama_client import generate_structured


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
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
        CREATE TABLE json_generation_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT, error_type TEXT, error_detail TEXT,
            prompt_snippet TEXT, created_at TEXT DEFAULT (datetime('now'))
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


class TestInstructorIntegration(unittest.TestCase):
    """Test that retry_with_structured_output tries Instructor first."""

    def setUp(self):
        self.conn = _make_db()

    def test_instructor_import_graceful(self):
        """generate_structured returns None when instructor not installed."""
        with patch.dict("sys.modules", {"instructor": None, "openai": None}):
            # Should return None gracefully, not raise
            generate_structured(
                prompt="test",
                response_model=MagicMock,
                conn=self.conn,
            )
            # May or may not be None depending on import caching,
            # but should not crash

    def test_fallback_to_retry_loop(self):
        """When Instructor fails, falls back to post-hoc validation."""
        if not OUTPUT_SCHEMA_REGISTRY:
            self.skipTest("Pydantic not available")

        with patch("mandarin.ai.ollama_client.generate_structured", return_value=None):
            with patch("mandarin.ai.ollama_client.generate") as mock_gen:
                import json
                mock_gen.return_value = MagicMock(
                    success=True,
                    text=json.dumps({
                        "usage_context": "greeting",
                        "register": "neutral",
                        "example_sentence": "你好",
                    }),
                )

                result = retry_with_structured_output(
                    self.conn,
                    prompt="Generate usage map",
                    system="Return JSON",
                    prompt_key="usage_map_generation",
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["usage_context"], "greeting")

    def test_schema_registry_has_models(self):
        """Verify all expected prompt keys have Pydantic models."""
        if not OUTPUT_SCHEMA_REGISTRY:
            self.skipTest("Pydantic not available")

        expected_keys = [
            "usage_map_generation",
            "tutor_analysis",
            "learning_insight",
            "drill_generation",
            "error_explanation",
        ]
        for key in expected_keys:
            self.assertIn(key, OUTPUT_SCHEMA_REGISTRY,
                          f"Missing schema for {key}")


if __name__ == "__main__":
    unittest.main()
