"""Tests for mandarin.quality.retention — retention quality checks."""

import sqlite3
import tempfile
from pathlib import Path

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


class TestRetention:
    def test_import(self):
        import mandarin.quality.retention as mod
        assert hasattr(mod, '__file__')
        public = [x for x in dir(mod) if not x.startswith('_')]
        assert len(public) > 0
