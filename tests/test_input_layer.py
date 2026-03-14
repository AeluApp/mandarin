"""Tests for Doc 15: Input Acquisition Layer."""

import json
import sqlite3
import unittest

from mandarin.db.core import SCHEMA_VERSION
from mandarin.ai.input_layer import (
    analyze_text_difficulty,
    recommend_reading_texts,
    process_inline_lookup,
    analyze_input_layer,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY, email TEXT);
        INSERT INTO user (id, email) VALUES (1, 'test@aelu.app');

        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            english TEXT NOT NULL,
            hsk_level INTEGER,
            status TEXT DEFAULT 'drill_ready',
            review_status TEXT NOT NULL DEFAULT 'approved'
        );

        CREATE TABLE memory_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_item_id INTEGER NOT NULL,
            stability REAL DEFAULT 0.4,
            reps INTEGER DEFAULT 0,
            state TEXT DEFAULT 'new'
        );

        CREATE TABLE learner_proficiency_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            vocab_hsk_estimate REAL,
            composite_hsk_estimate REAL,
            computed_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE reading_texts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content_hanzi TEXT NOT NULL,
            content_pinyin TEXT,
            word_count INTEGER NOT NULL DEFAULT 0,
            hsk_ceiling INTEGER NOT NULL DEFAULT 1,
            above_ceiling_words TEXT,
            content_lens TEXT,
            source TEXT NOT NULL DEFAULT 'generated',
            approved INTEGER NOT NULL DEFAULT 0,
            difficulty_score REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE reading_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text_id INTEGER NOT NULL,
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            completion_pct REAL DEFAULT 0.0,
            lookups TEXT,
            comprehension_score REAL,
            time_on_text_seconds INTEGER
        );

        CREATE TABLE pending_srs_additions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_item_id INTEGER NOT NULL,
            encounter_source TEXT DEFAULT 'reading_lookup',
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, content_item_id)
        );

        CREATE TABLE product_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT, score REAL, dimension_scores TEXT,
            findings TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def _seed_reading_text(conn, title="Test", hsk_ceiling=3, word_count=100,
                       above_ceiling=None, approved=1):
    above = json.dumps(above_ceiling or [], ensure_ascii=False)
    conn.execute("""
        INSERT INTO reading_texts (title, content_hanzi, word_count, hsk_ceiling,
                                   above_ceiling_words, approved, difficulty_score)
        VALUES (?, '内容', ?, ?, ?, ?, 0.5)
    """, (title, word_count, hsk_ceiling, above, approved))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


class TestTextDifficulty(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_comprehensible_input_under_5pct(self):
        text_id = _seed_reading_text(
            self.conn, word_count=100,
            above_ceiling=["word1", "word2"]  # 2%
        )
        result = analyze_text_difficulty(self.conn, text_id)
        self.assertTrue(result['is_comprehensible_input'])
        self.assertEqual(result['i_plus_one_rating'], 'optimal')

    def test_too_difficult_over_10pct(self):
        text_id = _seed_reading_text(
            self.conn, word_count=100,
            above_ceiling=[f"w{i}" for i in range(15)]  # 15%
        )
        result = analyze_text_difficulty(self.conn, text_id)
        self.assertFalse(result['is_comprehensible_input'])
        self.assertEqual(result['i_plus_one_rating'], 'too_difficult')

    def test_too_easy_under_1pct(self):
        text_id = _seed_reading_text(
            self.conn, word_count=200, above_ceiling=[]  # 0%
        )
        result = analyze_text_difficulty(self.conn, text_id)
        self.assertEqual(result['i_plus_one_rating'], 'too_easy')

    def test_nonexistent_text(self):
        result = analyze_text_difficulty(self.conn, 9999)
        self.assertEqual(result, {})


class TestRecommendReadingTexts(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_recommends_at_vocab_plus_one(self):
        self.conn.execute("""
            INSERT INTO learner_proficiency_zones (user_id, vocab_hsk_estimate)
            VALUES (1, 3.0)
        """)
        _seed_reading_text(self.conn, "Level 4 text", hsk_ceiling=4)
        _seed_reading_text(self.conn, "Level 2 text", hsk_ceiling=2)

        texts = recommend_reading_texts(self.conn, 1)
        self.assertTrue(len(texts) > 0)
        self.assertEqual(texts[0]['hsk_ceiling'], 4)

    def test_excludes_completed_texts(self):
        text_id = _seed_reading_text(self.conn, hsk_ceiling=2)
        self.conn.execute("""
            INSERT INTO reading_events (user_id, text_id, completion_pct)
            VALUES (1, ?, 0.95)
        """, (text_id,))

        texts = recommend_reading_texts(self.conn, 1)
        text_ids = [t['id'] for t in texts]
        self.assertNotIn(text_id, text_ids)

    def test_default_ceiling_no_proficiency(self):
        _seed_reading_text(self.conn, hsk_ceiling=2)
        texts = recommend_reading_texts(self.conn, 1)
        # Should default to ceiling 2
        if texts:
            self.assertEqual(texts[0]['hsk_ceiling'], 2)


class TestInlineLookup(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_queues_unknown_word_for_srs(self):
        ci_id = self.conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) "
            "VALUES ('书', 'shū', 'book', 1)"
        ).lastrowid

        re_id = self.conn.execute(
            "INSERT INTO reading_events (user_id, text_id, lookups) VALUES (1, 1, '[]')"
        ).lastrowid

        result = process_inline_lookup(self.conn, 1, re_id, '书')
        self.assertTrue(result['item_found'])
        self.assertTrue(result['queued_for_srs'])

        pending = self.conn.execute(
            "SELECT * FROM pending_srs_additions WHERE content_item_id=?",
            (ci_id,)
        ).fetchone()
        self.assertIsNotNone(pending)

    def test_does_not_requeue_existing_srs(self):
        ci_id = self.conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english) VALUES ('书', 'shū', 'book')"
        ).lastrowid
        self.conn.execute(
            "INSERT INTO memory_states (user_id, content_item_id) VALUES (1, ?)",
            (ci_id,)
        )
        re_id = self.conn.execute(
            "INSERT INTO reading_events (user_id, text_id, lookups) VALUES (1, 1, '[]')"
        ).lastrowid

        result = process_inline_lookup(self.conn, 1, re_id, '书')
        self.assertTrue(result['item_found'])
        self.assertFalse(result['queued_for_srs'])

    def test_logs_lookup_in_event(self):
        self.conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english) VALUES ('水', 'shuǐ', 'water')"
        )
        re_id = self.conn.execute(
            "INSERT INTO reading_events (user_id, text_id, lookups) VALUES (1, 1, '[]')"
        ).lastrowid

        process_inline_lookup(self.conn, 1, re_id, '水')
        row = self.conn.execute(
            "SELECT lookups FROM reading_events WHERE id=?", (re_id,)
        ).fetchone()
        lookups = json.loads(row['lookups'])
        self.assertEqual(len(lookups), 1)
        self.assertEqual(lookups[0]['hanzi'], '水')


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_db_generates_findings_for_missing_levels(self):
        findings = analyze_input_layer(self.conn)
        level_findings = [f for f in findings if 'Insufficient' in f['title']]
        self.assertTrue(len(level_findings) > 0)

    def test_sufficient_texts_no_finding(self):
        for level in range(3, 8):
            for i in range(10):
                _seed_reading_text(self.conn, f"L{level}_{i}", hsk_ceiling=level)
        findings = analyze_input_layer(self.conn)
        level_findings = [f for f in findings if 'Insufficient' in f['title']]
        self.assertEqual(len(level_findings), 0)


class TestSchemaVersion(unittest.TestCase):
    def test_schema_includes_doc15(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 79)


if __name__ == "__main__":
    unittest.main()
