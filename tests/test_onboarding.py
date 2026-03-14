"""Tests for Doc 17: Onboarding, Placement, and Activation."""

import sqlite3
import unittest

from mandarin.db.core import SCHEMA_VERSION
from mandarin.ai.onboarding import (
    build_placement_probe,
    estimate_placement_from_probe,
    generate_onboarding_curriculum,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT);
        INSERT INTO user (id, email) VALUES (1, 'test@aelu.app');

        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            hsk_level INTEGER,
            status TEXT DEFAULT 'drill_ready',
            difficulty REAL DEFAULT 0.5
        );

        CREATE TABLE memory_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_item_id INTEGER NOT NULL,
            stability REAL DEFAULT 0.4,
            difficulty REAL DEFAULT 0.5,
            state TEXT DEFAULT 'new',
            UNIQUE(user_id, content_item_id)
        );

        CREATE TABLE onboarding_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            self_reported_level TEXT,
            prior_study_years REAL,
            study_context TEXT,
            primary_goal TEXT,
            placement_hsk_estimate REAL,
            placement_confidence TEXT,
            activation_completed INTEGER NOT NULL DEFAULT 0,
            activation_session_id INTEGER
        );

        CREATE TABLE placement_probe_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            onboarding_id INTEGER NOT NULL,
            content_item_id INTEGER NOT NULL,
            correct INTEGER NOT NULL,
            response_ms INTEGER,
            hsk_level_of_item INTEGER,
            responded_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def _seed_content_items(conn):
    """Seed content items across HSK levels 1-6."""
    items = [
        ('你好', 'nǐ hǎo', 'hello', 1),
        ('谢谢', 'xiè xie', 'thank you', 1),
        ('早上', 'zǎo shang', 'morning', 1),
        ('电脑', 'diàn nǎo', 'computer', 2),
        ('比较', 'bǐ jiào', 'compare', 2),
        ('环境', 'huán jìng', 'environment', 3),
        ('经济', 'jīng jì', 'economy', 3),
        ('普遍', 'pǔ biàn', 'universal', 4),
        ('丰富', 'fēng fù', 'rich', 4),
        ('绝对', 'jué duì', 'absolute', 5),
        ('形势', 'xíng shì', 'situation', 5),
        ('抽象', 'chōu xiàng', 'abstract', 6),
    ]
    for hanzi, pinyin, english, hsk in items:
        conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES (?,?,?,?)",
            (hanzi, pinyin, english, hsk),
        )


class TestBuildPlacementProbe(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_returns_items_spanning_levels(self):
        _seed_content_items(self.conn)
        probe = build_placement_probe(self.conn)
        self.assertTrue(len(probe) > 0)
        levels = {item['hsk_level'] for item in probe}
        self.assertTrue(len(levels) > 1)

    def test_empty_db_returns_empty(self):
        probe = build_placement_probe(self.conn)
        self.assertEqual(probe, [])


class TestEstimatePlacement(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        _seed_content_items(self.conn)

    def test_all_wrong_returns_level_1(self):
        onb_id = self.conn.execute(
            "INSERT INTO onboarding_sessions (user_id) VALUES (1)"
        ).lastrowid

        # All wrong at every level
        for level in range(1, 5):
            for _ in range(3):
                self.conn.execute("""
                    INSERT INTO placement_probe_responses
                    (onboarding_id, content_item_id, correct, hsk_level_of_item)
                    VALUES (?, 1, 0, ?)
                """, (onb_id, level))

        result = estimate_placement_from_probe(self.conn, onb_id)
        self.assertEqual(result['hsk_estimate'], 1.0)

    def test_stops_at_low_accuracy(self):
        onb_id = self.conn.execute(
            "INSERT INTO onboarding_sessions (user_id) VALUES (1)"
        ).lastrowid

        # Level 1-2: 100% correct
        for level in [1, 2]:
            for _ in range(3):
                self.conn.execute("""
                    INSERT INTO placement_probe_responses
                    (onboarding_id, content_item_id, correct, hsk_level_of_item)
                    VALUES (?, 1, 1, ?)
                """, (onb_id, level))

        # Level 3: 0% correct
        for _ in range(3):
            self.conn.execute("""
                INSERT INTO placement_probe_responses
                (onboarding_id, content_item_id, correct, hsk_level_of_item)
                VALUES (?, 1, 0, 3)
            """, (onb_id,))

        result = estimate_placement_from_probe(self.conn, onb_id)
        self.assertEqual(result['hsk_estimate'], 2)

    def test_confidence_medium_with_enough_data(self):
        onb_id = self.conn.execute(
            "INSERT INTO onboarding_sessions (user_id) VALUES (1)"
        ).lastrowid

        for level in range(1, 6):
            for _ in range(2):
                self.conn.execute("""
                    INSERT INTO placement_probe_responses
                    (onboarding_id, content_item_id, correct, hsk_level_of_item)
                    VALUES (?, 1, 1, ?)
                """, (onb_id, level))

        result = estimate_placement_from_probe(self.conn, onb_id)
        self.assertEqual(result['confidence'], 'medium')


class TestGenerateOnboardingCurriculum(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        _seed_content_items(self.conn)

    def test_seeds_memory_states(self):
        onb_id = self.conn.execute("""
            INSERT INTO onboarding_sessions (user_id, placement_hsk_estimate)
            VALUES (1, 2.0)
        """).lastrowid

        result = generate_onboarding_curriculum(self.conn, 1, onb_id)
        self.assertGreater(result['items_seeded'], 0)
        self.assertTrue(result['first_session_ready'])

        # Check memory states were created
        ms_count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM memory_states WHERE user_id=1"
        ).fetchone()['cnt']
        self.assertGreater(ms_count, 0)

    def test_marks_activation_completed(self):
        onb_id = self.conn.execute("""
            INSERT INTO onboarding_sessions (user_id, placement_hsk_estimate)
            VALUES (1, 1.0)
        """).lastrowid

        generate_onboarding_curriculum(self.conn, 1, onb_id)

        row = self.conn.execute(
            "SELECT activation_completed FROM onboarding_sessions WHERE id=?",
            (onb_id,)
        ).fetchone()
        self.assertEqual(row['activation_completed'], 1)

    def test_nonexistent_session_returns_empty(self):
        result = generate_onboarding_curriculum(self.conn, 1, 9999)
        self.assertEqual(result['items_seeded'], 0)
        self.assertFalse(result['first_session_ready'])


class TestSchemaVersion(unittest.TestCase):
    def test_schema_includes_doc17(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 80)


if __name__ == "__main__":
    unittest.main()
