"""Tests for mandarin.ai.reading_content — reading passage generation."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mandarin.db.core import init_db, _migrate


@pytest.fixture
def conn():
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    path = Path(tf.name)
    c = init_db(path)
    _migrate(c)
    c.execute("INSERT OR IGNORE INTO user (id, email, password_hash, display_name) VALUES (1, 'test@test.com', 'h', 'T')")
    c.commit()
    yield c
    c.close()
    path.unlink(missing_ok=True)


class TestReadingContent:
    def test_import(self):
        import mandarin.ai.reading_content as mod
        assert hasattr(mod, 'generate_reading_passage')
        assert hasattr(mod, 'compute_vocabulary_profile')

    def test_compute_vocabulary_profile(self):
        from mandarin.ai.reading_content import compute_vocabulary_profile
        # Signature: (passage_text: str, known_hanzi: set) -> dict
        profile = compute_vocabulary_profile("这是一个学习测试", {"这", "是", "一"})
        assert isinstance(profile, dict)

    def test_compute_vocabulary_profile_empty(self):
        from mandarin.ai.reading_content import compute_vocabulary_profile
        profile = compute_vocabulary_profile("", set())
        assert isinstance(profile, dict)

    @patch("mandarin.ai.reading_content.is_ollama_available", return_value=False)
    def test_generate_reading_passage_no_ollama(self, _mock, conn):
        from mandarin.ai.reading_content import generate_reading_passage
        result = generate_reading_passage(conn, target_hsk_level=1, topic="food")
        assert result is None or isinstance(result, dict)

    def test_validate_generated_content(self):
        from mandarin.ai.reading_content import validate_generated_content
        content = {"body": "这是一个测试。", "title": "测试", "hsk_level": 1}
        result = validate_generated_content("passage", content)
        assert isinstance(result, dict)
