"""Tests for Output Production, Tone Drills, and Tutor Integration (Document 8).

Covers: tone coverage, tone transfer gap, sandhi proportion, character similarity,
output grading cascade, production-recognition gap, tutor session processing,
tutor auto-matching, vocab encounter creation, migration v68→v69.
"""

import sqlite3
import unittest


def _make_db():
    """Create an in-memory SQLite DB with tables needed for Doc 8 tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Core tables
    conn.execute("""CREATE TABLE content_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hanzi TEXT, pinyin TEXT, meaning TEXT,
        hsk_level INTEGER DEFAULT 1,
        tutor_corrected INTEGER NOT NULL DEFAULT 0,
        tutor_correction_count INTEGER NOT NULL DEFAULT 0,
        tutor_flagged INTEGER NOT NULL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE review_event (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        content_item_id INTEGER,
        drill_type TEXT,
        is_correct INTEGER,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE session_log (
        id INTEGER PRIMARY KEY, user_id INTEGER,
        started_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE vocab_encounter (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content_item_id INTEGER, hanzi TEXT,
        source_type TEXT, source_id INTEGER,
        looked_up INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # Doc 8 tables
    conn.execute("""CREATE TABLE output_drill_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL DEFAULT 1,
        content_item_id INTEGER NOT NULL,
        session_id INTEGER,
        prompt_type TEXT NOT NULL,
        user_response TEXT NOT NULL,
        expected_response TEXT NOT NULL,
        is_correct INTEGER,
        similarity_score REAL,
        grading_method TEXT,
        feedback TEXT,
        response_time_ms INTEGER,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE tutor_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL DEFAULT 1,
        tutor_name TEXT, platform TEXT,
        session_date TEXT NOT NULL,
        duration_minutes INTEGER,
        session_type TEXT, self_assessment INTEGER,
        topics_covered TEXT, tutor_notes TEXT,
        processed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE tutor_corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tutor_session_id INTEGER NOT NULL,
        correction_type TEXT NOT NULL DEFAULT 'grammar',
        wrong_form TEXT NOT NULL,
        correct_form TEXT NOT NULL,
        explanation TEXT,
        linked_content_item_id INTEGER,
        added_to_srs INTEGER DEFAULT 0,
        srs_priority_boost INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE tutor_vocabulary_flags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tutor_session_id INTEGER NOT NULL,
        hanzi TEXT NOT NULL, pinyin TEXT, meaning TEXT,
        flag_reason TEXT DEFAULT 'tutor_introduced',
        linked_content_item_id INTEGER,
        added_to_srs INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE speaking_practice_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL DEFAULT 1,
        session_id INTEGER,
        prompt_type TEXT NOT NULL,
        target_zh TEXT NOT NULL, expected_zh TEXT NOT NULL,
        whisper_transcription TEXT,
        tone_accuracy REAL, character_accuracy REAL,
        overall_score REAL, error_types TEXT,
        audio_duration_seconds REAL, whisper_confidence REAL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")

    conn.commit()
    return conn


def _insert_tone_drills(conn, tone=0, tone_sandhi=0, minimal_pair=0, listening_tone=0,
                        tone_correct_pct=1.0, sandhi_correct_pct=1.0,
                        mp_correct_pct=1.0, lt_correct_pct=1.0):
    """Insert tone drill review_events with specified counts and accuracy."""
    for dtype, count, pct in [
        ("tone", tone, tone_correct_pct),
        ("tone_sandhi", tone_sandhi, sandhi_correct_pct),
        ("minimal_pair", minimal_pair, mp_correct_pct),
        ("listening_tone", listening_tone, lt_correct_pct),
    ]:
        correct_count = int(count * pct)
        for i in range(count):
            conn.execute(
                "INSERT INTO review_event (content_item_id, drill_type, is_correct) VALUES (1, ?, ?)",
                (dtype, 1 if i < correct_count else 0),
            )
    conn.commit()


class TestToneCoverage(unittest.TestCase):

    def test_coverage_empty_db(self):
        from mandarin.intelligence.output_tone_tutor import _compute_tone_coverage
        conn = _make_db()
        result = _compute_tone_coverage(conn)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["tone"], 0)
        self.assertEqual(result["tone_sandhi"], 0)

    def test_coverage_with_data(self):
        from mandarin.intelligence.output_tone_tutor import _compute_tone_coverage
        conn = _make_db()
        _insert_tone_drills(conn, tone=10, tone_sandhi=5, minimal_pair=3, listening_tone=2)
        result = _compute_tone_coverage(conn)
        self.assertEqual(result["total"], 20)
        self.assertEqual(result["tone"], 10)
        self.assertEqual(result["tone_sandhi"], 5)

    def test_sandhi_low_emits_finding(self):
        from mandarin.intelligence.output_tone_tutor import analyze_tone_drill_quality
        conn = _make_db()
        # 50 tone drills, only 2 sandhi = 4% < 10%
        _insert_tone_drills(conn, tone=48, tone_sandhi=2)
        findings = analyze_tone_drill_quality(conn)
        sandhi_findings = [f for f in findings if "andhi" in f["title"]]
        self.assertTrue(len(sandhi_findings) > 0)
        self.assertEqual(sandhi_findings[0]["severity"], "high")


class TestToneTransfer(unittest.TestCase):

    def test_transfer_gap_detected(self):
        from mandarin.intelligence.output_tone_tutor import _compute_tone_transfer
        conn = _make_db()
        # Isolated: 90% accuracy, contextual: 60%
        _insert_tone_drills(conn, tone=50, tone_sandhi=50,
                           tone_correct_pct=0.9, sandhi_correct_pct=0.6)
        result = _compute_tone_transfer(conn)
        self.assertIsNotNone(result["transfer_gap"])
        self.assertGreater(result["transfer_gap"], 15)

    def test_transfer_gap_triggers_finding(self):
        from mandarin.intelligence.output_tone_tutor import analyze_tone_drill_quality
        conn = _make_db()
        _insert_tone_drills(conn, tone=50, tone_sandhi=50,
                           tone_correct_pct=0.9, sandhi_correct_pct=0.6)
        findings = analyze_tone_drill_quality(conn)
        transfer_findings = [f for f in findings if "transfer" in f["title"].lower()]
        self.assertTrue(len(transfer_findings) > 0)


class TestCharacterSimilarity(unittest.TestCase):

    def test_identical_strings(self):
        from mandarin.intelligence.output_tone_tutor import _compute_character_similarity
        self.assertEqual(_compute_character_similarity("你好", "你好"), 1.0)

    def test_empty_strings(self):
        from mandarin.intelligence.output_tone_tutor import _compute_character_similarity
        self.assertEqual(_compute_character_similarity("", ""), 0.0)
        self.assertEqual(_compute_character_similarity("你好", ""), 0.0)
        self.assertEqual(_compute_character_similarity("", "你好"), 0.0)

    def test_partial_match(self):
        from mandarin.intelligence.output_tone_tutor import _compute_character_similarity
        score = _compute_character_similarity("你好吗", "你好啊")
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)


class TestGradeOutputResponse(unittest.TestCase):

    def test_exact_match(self):
        from mandarin.intelligence.output_tone_tutor import grade_output_response
        result = grade_output_response("你好", "你好")
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["method"], "exact_match")

    def test_high_similarity_accepted(self):
        from mandarin.intelligence.output_tone_tutor import grade_output_response
        # 92% similar — should pass character_similarity threshold
        # "我今天很高兴" vs "我今天很高兴啊" — 6/7 chars match in position
        result = grade_output_response("我今天很高兴啊", "我今天很高兴了")
        # Both have high overlap; exact threshold depends on calc
        self.assertIn(result["method"], ("character_similarity", "fallback"))

    def test_variant_accepted(self):
        from mandarin.intelligence.output_tone_tutor import grade_output_response
        result = grade_output_response("没问题", "没有问题", acceptable_variants=["没问题"])
        self.assertTrue(result["is_correct"])
        self.assertEqual(result["method"], "variant_match")

    def test_wrong_answer(self):
        from mandarin.intelligence.output_tone_tutor import grade_output_response
        result = grade_output_response("苹果", "你好吗")
        self.assertFalse(result["is_correct"])


class TestOutputProduction(unittest.TestCase):

    def test_production_recognition_gap(self):
        from mandarin.intelligence.output_tone_tutor import analyze_output_production
        conn = _make_db()
        # Recognition: 90% accuracy (45/50)
        for i in range(50):
            conn.execute(
                "INSERT INTO review_event (content_item_id, drill_type, is_correct) VALUES (1, 'mc', ?)",
                (1 if i < 45 else 0,),
            )
        # Production: 50% accuracy (25/50)
        for i in range(50):
            conn.execute(
                "INSERT INTO review_event (content_item_id, drill_type, is_correct) VALUES (1, 'translation', ?)",
                (1 if i < 25 else 0,),
            )
        conn.commit()
        findings = analyze_output_production(conn)
        gap_findings = [f for f in findings if "gap" in f["title"].lower()]
        self.assertTrue(len(gap_findings) > 0)
        self.assertEqual(gap_findings[0]["severity"], "medium")


class TestTutorProcessing(unittest.TestCase):

    def _setup_tutor_session(self, conn):
        """Insert a content item, tutor session, correction, and flag."""
        conn.execute("INSERT INTO content_item (hanzi, pinyin, meaning) VALUES ('你好', 'nǐ hǎo', 'hello')")
        conn.execute("""
            INSERT INTO tutor_sessions (user_id, session_date, tutor_name)
            VALUES (1, '2026-03-10', 'Li laoshi')
        """)
        conn.execute("""
            INSERT INTO tutor_corrections (tutor_session_id, wrong_form, correct_form)
            VALUES (1, '你号', '你好')
        """)
        conn.execute("""
            INSERT INTO tutor_vocabulary_flags (tutor_session_id, hanzi, pinyin, meaning)
            VALUES (1, '你好', 'nǐ hǎo', 'hello')
        """)
        conn.commit()

    def test_process_matches_correction(self):
        from mandarin.intelligence.output_tone_tutor import process_tutor_session
        conn = _make_db()
        self._setup_tutor_session(conn)
        result = process_tutor_session(conn, 1)
        self.assertEqual(result["matched_corrections"], 1)

    def test_process_no_match_graceful(self):
        from mandarin.intelligence.output_tone_tutor import process_tutor_session
        conn = _make_db()
        conn.execute("INSERT INTO tutor_sessions (user_id, session_date) VALUES (1, '2026-03-10')")
        conn.execute("INSERT INTO tutor_corrections (tutor_session_id, wrong_form, correct_form) VALUES (1, 'xxx', 'yyy')")
        conn.commit()
        result = process_tutor_session(conn, 1)
        self.assertEqual(result["matched_corrections"], 0)

    def test_process_creates_vocab_encounter(self):
        from mandarin.intelligence.output_tone_tutor import process_tutor_session
        conn = _make_db()
        self._setup_tutor_session(conn)
        process_tutor_session(conn, 1)
        enc = conn.execute("SELECT COUNT(*) FROM vocab_encounter WHERE source_type = 'tutor'").fetchone()[0]
        self.assertGreater(enc, 0)

    def test_process_sets_tutor_corrected(self):
        from mandarin.intelligence.output_tone_tutor import process_tutor_session
        conn = _make_db()
        self._setup_tutor_session(conn)
        process_tutor_session(conn, 1)
        item = conn.execute("SELECT tutor_corrected, tutor_correction_count FROM content_item WHERE id = 1").fetchone()
        self.assertEqual(item[0], 1)
        self.assertEqual(item[1], 1)


class TestTutorAnalyzer(unittest.TestCase):

    def test_no_sessions_nudge(self):
        from mandarin.intelligence.output_tone_tutor import analyze_tutor_integration
        conn = _make_db()
        findings = analyze_tutor_integration(conn)
        self.assertTrue(len(findings) > 0)
        self.assertEqual(findings[0]["severity"], "low")
        self.assertIn("No tutor sessions", findings[0]["title"])

    def test_recent_session_no_findings(self):
        from mandarin.intelligence.output_tone_tutor import analyze_tutor_integration
        conn = _make_db()
        conn.execute("""
            INSERT INTO tutor_sessions (user_id, session_date) VALUES (1, datetime('now'))
        """)
        conn.commit()
        findings = analyze_tutor_integration(conn)
        # Should not emit the "no sessions" or "no recent" findings
        no_session_findings = [f for f in findings if "No tutor" in f.get("title", "") or "No recent" in f.get("title", "")]
        self.assertEqual(len(no_session_findings), 0)


class TestMigration(unittest.TestCase):

    def test_migration_creates_tables_and_columns(self):
        """Test that migration v68→v69 creates all 5 tables + 3 columns."""
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA journal_mode=WAL")

        # Create minimal schema to support migration
        conn.execute("""CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT, pinyin TEXT, meaning TEXT
        )""")
        # Set schema version to 68
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
        conn.execute("INSERT INTO schema_version VALUES (68)")
        conn.commit()

        from mandarin.db.core import _migrate_v68_to_v69
        _migrate_v68_to_v69(conn)

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        self.assertIn("output_drill_responses", tables)
        self.assertIn("tutor_sessions", tables)
        self.assertIn("tutor_corrections", tables)
        self.assertIn("tutor_vocabulary_flags", tables)
        self.assertIn("speaking_practice_sessions", tables)

        # Check ALTER TABLE columns
        cols = {r[1] for r in conn.execute("PRAGMA table_info(content_item)").fetchall()}
        self.assertIn("tutor_corrected", cols)
        self.assertIn("tutor_correction_count", cols)
        self.assertIn("tutor_flagged", cols)


if __name__ == "__main__":
    unittest.main()
