"""Tests for mandarin.ai.drill_generator — deterministic drill creation."""

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


class TestDrillGenerator:
    def test_import(self):
        import mandarin.ai.drill_generator as mod
        assert hasattr(mod, 'generate_drill_from_encounter')
        assert hasattr(mod, 'validate_generated_content')
        assert hasattr(mod, 'GeneratedDrillItem')

    def test_generated_drill_item_dataclass(self):
        from mandarin.ai.drill_generator import GeneratedDrillItem
        item = GeneratedDrillItem(
            hanzi="你好", pinyin="nǐ hǎo", english="hello",
            drill_type="mc",
        )
        assert item.drill_type == "mc"
        assert item.hanzi == "你好"
        assert item.confidence == 0.0

    def test_validate_generated_content(self):
        from mandarin.ai.drill_generator import validate_generated_content
        content = {"hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello",
                    "drill_type": "mc", "distractors": ["goodbye", "thanks"]}
        result = validate_generated_content("vocab", content)
        assert isinstance(result, dict)

    @patch("mandarin.ai.drill_generator.is_ollama_available", return_value=False)
    def test_process_pending_encounters_no_ollama(self, _mock, conn):
        from mandarin.ai.drill_generator import process_pending_encounters
        result = process_pending_encounters(conn)
        assert isinstance(result, (list, dict, int)) or result is None
