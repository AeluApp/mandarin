"""Tests for Doc 23 B-03: Audio Coherence Verification."""

import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from mandarin.ai.audio_coherence import (
    check_audio_coherence,
    batch_check_coherence,
    get_coherence_failures,
    _levenshtein_similarity,
    _hanzi_to_pinyin,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL, pinyin TEXT, english TEXT,
            hsk_level INTEGER, status TEXT DEFAULT 'drill_ready'
        );
        CREATE TABLE audio_coherence_check (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_item_id INTEGER NOT NULL,
            tts_engine TEXT NOT NULL DEFAULT 'edge-tts',
            expected_pinyin TEXT,
            transcribed_text TEXT,
            transcribed_pinyin TEXT,
            similarity_score REAL,
            passed INTEGER,
            checked_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE work_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, description TEXT, item_type TEXT,
            status TEXT DEFAULT 'ready', service_class TEXT,
            ready_at TEXT
        );

        INSERT INTO content_item (hanzi, pinyin, english, hsk_level)
        VALUES ('你好', 'nǐ hǎo', 'hello', 1);
        INSERT INTO content_item (hanzi, pinyin, english, hsk_level)
        VALUES ('谢谢', 'xiè xiè', 'thank you', 1);
    """)
    return conn


class TestLevenshteinSimilarity(unittest.TestCase):
    def test_identical_strings(self):
        self.assertEqual(_levenshtein_similarity("hello", "hello"), 1.0)

    def test_empty_strings(self):
        self.assertEqual(_levenshtein_similarity("", ""), 1.0)

    def test_one_empty(self):
        self.assertEqual(_levenshtein_similarity("hello", ""), 0.0)

    def test_similar_pinyin(self):
        sim = _levenshtein_similarity("nǐ hǎo", "nǐ hǎo")
        self.assertEqual(sim, 1.0)

    def test_different_pinyin(self):
        sim = _levenshtein_similarity("nǐ hǎo", "nǐ hào")
        self.assertLess(sim, 1.0)
        self.assertGreater(sim, 0.0)

    def test_completely_different(self):
        sim = _levenshtein_similarity("aaa bbb ccc", "xxx yyy zzz")
        self.assertEqual(sim, 0.0)


class TestHanziToPinyin(unittest.TestCase):
    def test_basic_conversion(self):
        try:
            import pypinyin
        except ImportError:
            self.skipTest("pypinyin not installed")

        result = _hanzi_to_pinyin("你好")
        self.assertIn("nǐ", result.lower())

    def test_empty_input(self):
        result = _hanzi_to_pinyin("")
        self.assertEqual(result, "")


class TestCheckAudioCoherence(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_missing_pypinyin(self):
        with patch("mandarin.ai.audio_coherence._HAS_PYPINYIN", False):
            result = check_audio_coherence(self.conn, 1)
            self.assertEqual(result["status"], "skipped")

    def test_missing_whisper(self):
        with patch("mandarin.ai.audio_coherence._HAS_WHISPER", False):
            result = check_audio_coherence(self.conn, 1)
            self.assertEqual(result["status"], "skipped")

    def test_nonexistent_item(self):
        with patch("mandarin.ai.audio_coherence._HAS_PYPINYIN", True), \
             patch("mandarin.ai.audio_coherence._HAS_WHISPER", True):
            result = check_audio_coherence(self.conn, 9999)
            self.assertEqual(result["status"], "error")
            self.assertIn("not found", result["reason"])


class TestBatchCheckCoherence(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_batch_skips_already_checked(self):
        # Mark one item as already checked
        self.conn.execute("""
            INSERT INTO audio_coherence_check
            (content_item_id, expected_pinyin, similarity_score, passed)
            VALUES (1, 'nǐ hǎo', 0.95, 1)
        """)

        with patch("mandarin.ai.audio_coherence.check_audio_coherence") as mock_check:
            mock_check.return_value = {"status": "skipped"}
            results = batch_check_coherence(self.conn, limit=10)
            # Only unchecked item (id=2) should be processed
            self.assertEqual(len(results), 1)


class TestGetCoherenceFailures(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_no_failures(self):
        failures = get_coherence_failures(self.conn)
        self.assertEqual(failures, [])

    def test_with_failures(self):
        self.conn.execute("""
            INSERT INTO audio_coherence_check
            (content_item_id, expected_pinyin, transcribed_pinyin,
             similarity_score, passed)
            VALUES (1, 'nǐ hǎo', 'nǐ hào', 0.5, 0)
        """)
        failures = get_coherence_failures(self.conn)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["passed"], 0)


if __name__ == "__main__":
    unittest.main()
