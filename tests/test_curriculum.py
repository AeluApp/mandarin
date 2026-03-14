"""Tests for Doc 14: Curriculum Architecture and HSK 9 Pathway."""

import sqlite3
import unittest

from mandarin.db.core import SCHEMA_VERSION
from mandarin.ai.curriculum import (
    HSK_MILESTONES,
    get_curriculum_recommendation,
    _get_next_level_ready_patterns,
    _cold_start_recommendation,
    _generate_recommendation_text,
    analyze_curriculum_coverage,
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
            difficulty REAL DEFAULT 0.5,
            content_lens TEXT
        );

        CREATE TABLE grammar_point (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            name_zh TEXT,
            hsk_level INTEGER NOT NULL DEFAULT 1,
            category TEXT NOT NULL DEFAULT 'structure',
            description TEXT,
            prerequisite_patterns TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE content_grammar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_item_id INTEGER NOT NULL,
            grammar_point_id INTEGER NOT NULL,
            FOREIGN KEY (content_item_id) REFERENCES content_item(id),
            FOREIGN KEY (grammar_point_id) REFERENCES grammar_point(id)
        );

        CREATE TABLE memory_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_item_id INTEGER NOT NULL,
            stability REAL DEFAULT 0.4,
            difficulty REAL DEFAULT 0.5,
            reps INTEGER DEFAULT 0,
            state TEXT DEFAULT 'new'
        );

        CREATE TABLE learner_pattern_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            grammar_point_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'untouched',
            encounters INTEGER NOT NULL DEFAULT 0,
            correct_streak INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, grammar_point_id)
        );

        CREATE TABLE learner_proficiency_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            vocab_hsk_estimate REAL,
            vocab_items_mastered INTEGER,
            vocab_coverage_pct REAL,
            grammar_hsk_estimate REAL,
            grammar_patterns_mastered INTEGER,
            grammar_coverage_pct REAL,
            reading_hsk_estimate REAL,
            listening_hsk_estimate REAL,
            composite_hsk_estimate REAL,
            computed_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE product_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT, score REAL, dimension_scores TEXT,
            findings TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


class TestHSKMilestones(unittest.TestCase):
    def test_all_levels_present(self):
        for level in range(1, 10):
            self.assertIn(level, HSK_MILESTONES)
            self.assertIn('vocab_target', HSK_MILESTONES[level])
            self.assertIn('can_do', HSK_MILESTONES[level])

    def test_vocab_targets_increase(self):
        for level in range(1, 9):
            self.assertLess(
                HSK_MILESTONES[level]['vocab_target'],
                HSK_MILESTONES[level + 1]['vocab_target'],
            )


class TestCurriculumRecommendation(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_cold_start_no_proficiency(self):
        rec = get_curriculum_recommendation(self.conn, 1)
        self.assertEqual(rec['current_composite_hsk'], 0.0)
        self.assertIn('HSK 1', rec['recommendation'])

    def test_returns_pattern_gaps(self):
        # Set up proficiency at HSK 2
        self.conn.execute("""
            INSERT INTO learner_proficiency_zones
            (user_id, composite_hsk_estimate, vocab_items_mastered, grammar_patterns_mastered)
            VALUES (1, 2.0, 200, 15)
        """)
        # Add a grammar point at HSK 2 with a content item
        self.conn.execute(
            "INSERT INTO grammar_point (id, name, hsk_level) VALUES (1, '把 construction', 2)"
        )
        ci_id = self.conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES ('把书放下', 'bǎ shū fàng xià', 'put the book down', 2)"
        ).lastrowid
        self.conn.execute(
            "INSERT INTO content_grammar (content_item_id, grammar_point_id) VALUES (?, 1)",
            (ci_id,)
        )

        rec = get_curriculum_recommendation(self.conn, 1)
        self.assertEqual(rec['current_composite_hsk'], 2.0)
        patterns = rec['immediate_priorities']['pattern_gaps_this_level']
        self.assertTrue(len(patterns) > 0)
        self.assertEqual(patterns[0]['name'], '把 construction')

    def test_returns_vocab_gaps(self):
        self.conn.execute("""
            INSERT INTO learner_proficiency_zones
            (user_id, composite_hsk_estimate, vocab_items_mastered, grammar_patterns_mastered)
            VALUES (1, 1.0, 50, 5)
        """)
        self.conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) "
            "VALUES ('你好', 'nǐ hǎo', 'hello', 1)"
        )

        rec = get_curriculum_recommendation(self.conn, 1)
        vocab_gaps = rec['immediate_priorities']['vocabulary_gaps_this_level']
        self.assertTrue(len(vocab_gaps) > 0)

    def test_next_milestone_gap_calculation(self):
        self.conn.execute("""
            INSERT INTO learner_proficiency_zones
            (user_id, composite_hsk_estimate, vocab_items_mastered, grammar_patterns_mastered)
            VALUES (1, 3.0, 400, 30)
        """)
        rec = get_curriculum_recommendation(self.conn, 1)
        self.assertEqual(rec['next_milestone']['level'], 4)
        self.assertGreater(rec['next_milestone']['vocab_gap'], 0)


class TestNextLevelReadyPatterns(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_returns_next_level_patterns(self):
        # Grammar point at level 2 with content
        self.conn.execute(
            "INSERT INTO grammar_point (id, name, hsk_level) VALUES (1, 'test_pattern', 2)"
        )
        ci_id = self.conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES ('test', 'test', 'test', 2)"
        ).lastrowid
        self.conn.execute(
            "INSERT INTO content_grammar (content_item_id, grammar_point_id) VALUES (?, 1)",
            (ci_id,)
        )

        result = _get_next_level_ready_patterns(self.conn, 1, 1)
        self.assertTrue(len(result) > 0)

    def test_empty_when_already_learning(self):
        self.conn.execute(
            "INSERT INTO grammar_point (id, name, hsk_level) VALUES (1, 'test_pattern', 2)"
        )
        ci_id = self.conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english, hsk_level) VALUES ('test', 'test', 'test', 2)"
        ).lastrowid
        self.conn.execute(
            "INSERT INTO content_grammar (content_item_id, grammar_point_id) VALUES (?, 1)",
            (ci_id,)
        )
        self.conn.execute(
            "INSERT INTO learner_pattern_states (user_id, grammar_point_id, status) VALUES (1, 1, 'acquiring')"
        )

        result = _get_next_level_ready_patterns(self.conn, 1, 1)
        self.assertEqual(len(result), 0)


class TestRecommendationText(unittest.TestCase):
    def test_nonempty_when_gaps(self):
        text = _generate_recommendation_text(
            [{'name': 'pattern1'}], [{'hanzi': '你好'}], []
        )
        self.assertIn('pattern1', text)
        self.assertIn('1 uncovered', text)

    def test_continue_when_no_gaps(self):
        text = _generate_recommendation_text([], [], [])
        self.assertEqual(text, 'Continue current review schedule.')


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_db_no_findings(self):
        findings = analyze_curriculum_coverage(self.conn)
        self.assertEqual(findings, [])

    def test_zero_item_patterns_trigger_finding(self):
        # Grammar point at HSK 2 with NO content items linked
        self.conn.execute(
            "INSERT INTO grammar_point (name, hsk_level) VALUES ('orphan_pattern', 3)"
        )
        findings = analyze_curriculum_coverage(self.conn)
        pattern_findings = [f for f in findings if 'grammar pattern' in f['title'].lower()]
        self.assertEqual(len(pattern_findings), 1)
        self.assertEqual(pattern_findings[0]['severity'], 'high')


class TestSchemaVersion(unittest.TestCase):
    def test_schema_version_includes_doc14(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 78)


if __name__ == "__main__":
    unittest.main()
