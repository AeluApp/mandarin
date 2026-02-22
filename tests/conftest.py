"""Shared test fixtures for the mandarin test suite."""

import tempfile
from pathlib import Path

import pytest

from mandarin import db
from mandarin.db.core import _migrate


@pytest.fixture
def test_db():
    """Create a fresh test database with schema + migrations + seed profile.

    Returns (conn, path). The connection is closed and file cleaned up after the test.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = db.init_db(path)
    _migrate(conn)
    # Ensure bootstrap user exists (v15+ schema creates it, but migration path may not)
    conn.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier)
        VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin')
    """)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1)")
    conn.commit()
    yield conn, path
    conn.close()
    path.unlink(missing_ok=True)


def make_test_db():
    """Create a fresh test database (function form for non-fixture use).

    Returns (conn, path). Caller is responsible for cleanup.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = db.init_db(path)
    _migrate(conn)
    conn.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier)
        VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin')
    """)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1)")
    conn.commit()
    return conn, path


class OutputCapture:
    """Captures show_fn output for test assertions."""
    def __init__(self):
        self.lines = []

    def __call__(self, text="", **kwargs):
        self.lines.append(text)


class InputSequence:
    """Provides pre-programmed answers to input_fn calls."""
    def __init__(self, answers):
        self.answers = list(answers)
        self.idx = 0
        self.prompts = []

    def __call__(self, prompt=""):
        self.prompts.append(prompt)
        if self.idx < len(self.answers):
            ans = self.answers[self.idx]
            self.idx += 1
            return ans
        return ""
