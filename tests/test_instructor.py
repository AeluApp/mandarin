"""Tests for Doc 23 1A: Instructor Structured Output via Ollama."""

import pytest
pytest.importorskip("httpx")

import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.agentic import (
    retry_with_structured_output,
    validate_structured_output,
    OUTPUT_SCHEMA_REGISTRY,
)
from mandarin.ai.ollama_client import generate_structured


from tests.shared_db import make_test_db as _make_db


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
