"""Shared test fixtures for the mandarin test suite."""

import os

# TEST-ONLY SAFEGUARD — do not replicate in production config.
#
# PyTorch (via sentence-transformers/fuzzy_dedup) and LightGBM (difficulty_model)
# each bundle their own libomp.  When both are loaded in the same process on
# Python 3.14, competing multi-threaded OpenMP initialisation races and produces
# a SIGSEGV.  Constraining OpenMP to 1 thread serialises initialisation and
# eliminates the race.
#
# This is a runtime constraint workaround for a library-interaction conflict in
# the Python 3.14 + PyTorch + LightGBM stack.  The upstream libraries themselves
# are unchanged.  CI runs Python 3.12 where this conflict does not occur;
# setdefault() means any CI-level override (e.g. OMP_NUM_THREADS=4) is preserved.
#
# Must be set before any C-extension is imported — module load time here ensures
# that.  Related: librosa/sounddevice tests are separately quarantined under the
# @pytest.mark.tone_audio marker pending a librosa Python 3.14 release.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import sqlite3
import tempfile
from pathlib import Path

import pytest
from hypothesis import settings as hypothesis_settings, HealthCheck

from mandarin import db
from mandarin.db.core import _migrate


# ── Hypothesis profiles ──
# "ci" profile: 30 examples per property for speed (~15s vs ~67s)
# "default" profile: 100 examples for thorough nightly runs
# Select via: HYPOTHESIS_PROFILE=ci pytest ...
hypothesis_settings.register_profile(
    "ci",
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow],
)
hypothesis_settings.register_profile(
    "default",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
hypothesis_settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "ci"))


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


@pytest.fixture
def light_db():
    """Lightweight in-memory DB with only core tables — no migrations.

    ~10x faster than test_db. Use for tests that only need user, content_item,
    progress, and session_log — not the full 71-table schema.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            subscription_tier TEXT NOT NULL DEFAULT 'free'
                CHECK (subscription_tier IN ('free', 'paid', 'admin', 'teacher')),
            subscription_status TEXT DEFAULT 'active',
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE learner_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES user(id),
            current_level REAL NOT NULL DEFAULT 1.0
        );
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL,
            pinyin TEXT NOT NULL DEFAULT '',
            english TEXT NOT NULL DEFAULT '',
            hsk_level INTEGER NOT NULL DEFAULT 1,
            scale_level TEXT DEFAULT 'word',
            content_type TEXT DEFAULT 'vocabulary',
            audio_available INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            content_item_id INTEGER NOT NULL REFERENCES content_item(id),
            modality TEXT NOT NULL DEFAULT 'reading',
            ease_factor REAL NOT NULL DEFAULT 2.5,
            interval_days REAL NOT NULL DEFAULT 1.0,
            repetitions INTEGER NOT NULL DEFAULT 0,
            streak_correct INTEGER NOT NULL DEFAULT 0,
            streak_incorrect INTEGER NOT NULL DEFAULT 0,
            mastery_stage TEXT NOT NULL DEFAULT 'seen',
            total_attempts INTEGER NOT NULL DEFAULT 0,
            total_correct INTEGER NOT NULL DEFAULT 0,
            half_life_days REAL DEFAULT 4.0,
            difficulty REAL DEFAULT 0.5,
            last_review_date TEXT,
            historically_weak INTEGER DEFAULT 0,
            weak_cycle_count INTEGER DEFAULT 0,
            stable_since_date TEXT,
            successes_while_stable INTEGER DEFAULT 0,
            avg_response_ms REAL,
            drill_types_seen TEXT DEFAULT '',
            distinct_review_days INTEGER DEFAULT 0,
            modality_history TEXT DEFAULT '{}',
            UNIQUE(user_id, content_item_id, modality)
        );
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            items_studied INTEGER DEFAULT 0,
            items_correct INTEGER DEFAULT 0,
            session_type TEXT DEFAULT 'standard',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            duration_seconds INTEGER,
            experiment_variant TEXT
        );
        CREATE TABLE error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            content_item_id INTEGER,
            error_type TEXT,
            modality TEXT,
            session_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO user (id, email, password_hash, display_name, subscription_tier)
        VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin');
        INSERT INTO learner_profile (id, user_id) VALUES (1, 1);
    """)
    yield conn
    conn.close()


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
