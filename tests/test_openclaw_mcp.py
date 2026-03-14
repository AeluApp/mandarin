"""Tests for the expanded Aelu MCP Server — 25 tools across 5 categories."""

import json
import sqlite3
import unittest
from unittest.mock import patch, MagicMock


def _make_db():
    """Create in-memory DB with all tables the MCP server queries."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY, email TEXT, display_name TEXT,
            streak_days INTEGER DEFAULT 0,
            streak_freezes_available INTEGER DEFAULT 0,
            subscription_tier TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            subscription_status TEXT,
            subscription_end_date TEXT
        );
        CREATE TABLE learner_profile (
            user_id INTEGER UNIQUE,
            target_sessions_per_week INTEGER DEFAULT 5
        );
        CREATE TABLE content_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hanzi TEXT NOT NULL, pinyin TEXT, english TEXT,
            hsk_level INTEGER, item_type TEXT DEFAULT 'vocab',
            status TEXT DEFAULT 'drill_ready',
            review_status TEXT DEFAULT 'approved'
        );
        CREATE TABLE progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, content_item_id INTEGER,
            next_review_date TEXT DEFAULT (date('now')),
            total_attempts INTEGER DEFAULT 0,
            total_correct INTEGER DEFAULT 0,
            mastery_stage TEXT DEFAULT 'unseen'
        );
        CREATE TABLE session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, started_at TEXT DEFAULT (datetime('now')),
            ended_at TEXT, duration_seconds INTEGER,
            session_type TEXT DEFAULT 'mixed',
            items_planned INTEGER DEFAULT 10,
            items_completed INTEGER DEFAULT 0, items_correct INTEGER DEFAULT 0,
            session_outcome TEXT DEFAULT 'completed',
            early_exit INTEGER DEFAULT 0,
            client_platform TEXT DEFAULT 'web'
        );
        CREATE TABLE content_generation_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gap_type TEXT NOT NULL, gap_data TEXT,
            generation_brief TEXT,
            status TEXT DEFAULT 'pending',
            generated_content TEXT, reviewer_note TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            reviewed_at TEXT
        );
        CREATE TABLE product_audit (
            id INTEGER PRIMARY KEY, grade TEXT, score REAL,
            dimension_scores_json TEXT, findings_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            audit_timestamp TEXT
        );
        CREATE TABLE error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content_item_id INTEGER, error_type TEXT,
            modality TEXT, session_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE grammar_point (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, name_zh TEXT,
            hsk_level INTEGER, category TEXT
        );
        CREATE TABLE grammar_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, grammar_point_id INTEGER,
            mastery_score REAL DEFAULT 0,
            drill_attempts INTEGER DEFAULT 0,
            drill_correct INTEGER DEFAULT 0,
            studied_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE content_grammar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_item_id INTEGER, grammar_point_id INTEGER
        );
        CREATE TABLE review_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, content_item_id INTEGER,
            correct INTEGER, modality TEXT DEFAULT 'reading',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE learner_proficiency_zones (
            id INTEGER PRIMARY KEY,
            user_id INTEGER UNIQUE,
            vocab_hsk_estimate REAL,
            composite_hsk_estimate REAL,
            computed_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE audio_recording (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, content_item_id INTEGER,
            overall_score REAL, tone_scores_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE reading_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, passage_id TEXT,
            comprehension_score REAL, words_looked_up INTEGER DEFAULT 0,
            reading_time_seconds INTEGER, hsk_level INTEGER,
            completed_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE listening_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, passage_id TEXT,
            comprehension_score REAL, words_looked_up INTEGER DEFAULT 0,
            hsk_level INTEGER,
            completed_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE classroom_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classroom_id INTEGER, user_id INTEGER,
            role TEXT DEFAULT 'student'
        );
        CREATE TABLE error_focus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, content_item_id INTEGER,
            resolved INTEGER DEFAULT 0
        );

        -- Seed data
        INSERT INTO user (id, email, display_name, streak_days, streak_freezes_available)
        VALUES (1, 'test@aelu.app', 'Test User', 7, 2);
        INSERT INTO user (id, email, display_name, streak_days, streak_freezes_available)
        VALUES (2, 'student2@aelu.app', 'Student Two', 3, 0);

        INSERT INTO learner_profile (user_id, target_sessions_per_week)
        VALUES (1, 5);

        INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level)
        VALUES (1, '你好', 'nǐ hǎo', 'hello', 1);
        INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level)
        VALUES (2, '谢谢', 'xiè xie', 'thank you', 1);
        INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level)
        VALUES (3, '学习', 'xué xí', 'to study', 2);

        INSERT INTO grammar_point (id, name, name_zh, hsk_level, category)
        VALUES (1, 'Subject-Verb-Object', '主谓宾', 1, 'sentence_structure');
        INSERT INTO grammar_point (id, name, name_zh, hsk_level, category)
        VALUES (2, 'Aspect particle 了', '了', 1, 'particles');

        INSERT INTO grammar_progress (user_id, grammar_point_id, mastery_score, drill_attempts, drill_correct)
        VALUES (1, 1, 0.85, 20, 17);

        INSERT INTO content_grammar (content_item_id, grammar_point_id)
        VALUES (1, 1);

        INSERT INTO progress (user_id, content_item_id, next_review_date, total_attempts, total_correct, mastery_stage)
        VALUES (1, 1, date('now'), 10, 8, 'stable');
        INSERT INTO progress (user_id, content_item_id, next_review_date, total_attempts, total_correct, mastery_stage)
        VALUES (1, 2, date('now', '+3 days'), 5, 5, 'durable');

        INSERT INTO session_log (user_id, started_at, ended_at, duration_seconds, items_completed, items_correct, session_outcome, client_platform)
        VALUES (1, datetime('now', '-1 hour'), datetime('now'), 1200, 15, 12, 'completed', 'ios');
        INSERT INTO session_log (user_id, started_at, ended_at, duration_seconds, items_completed, items_correct, session_outcome, early_exit, client_platform)
        VALUES (1, datetime('now', '-2 days'), datetime('now', '-2 days', '+600 seconds'), 600, 5, 3, 'early_exit', 1, 'web');

        INSERT INTO error_log (user_id, content_item_id, error_type, modality)
        VALUES (1, 1, 'tone_error', 'speaking');
        INSERT INTO error_log (user_id, content_item_id, error_type, modality)
        VALUES (1, 1, 'tone_error', 'speaking');
        INSERT INTO error_log (user_id, content_item_id, error_type, modality)
        VALUES (1, 2, 'meaning_error', 'reading');

        INSERT INTO review_event (user_id, content_item_id, correct, modality)
        VALUES (1, 1, 1, 'reading');
        INSERT INTO review_event (user_id, content_item_id, correct, modality)
        VALUES (1, 1, 0, 'speaking');
        INSERT INTO review_event (user_id, content_item_id, correct, modality)
        VALUES (1, 2, 1, 'reading');

        INSERT INTO audio_recording (user_id, content_item_id, overall_score, tone_scores_json)
        VALUES (1, 1, 0.72, '[{"expected": 3, "correct": true}, {"expected": 3, "correct": false}]');
        INSERT INTO audio_recording (user_id, content_item_id, overall_score, tone_scores_json)
        VALUES (1, 2, 0.85, '[{"expected": 4, "correct": true}, {"expected": 0, "correct": true}]');

        INSERT INTO reading_progress (user_id, passage_id, comprehension_score, words_looked_up, reading_time_seconds, hsk_level)
        VALUES (1, 'passage_1', 0.8, 3, 120, 1);
        INSERT INTO reading_progress (user_id, passage_id, comprehension_score, words_looked_up, reading_time_seconds, hsk_level)
        VALUES (1, 'passage_2', 0.65, 5, 180, 2);

        INSERT INTO listening_progress (user_id, passage_id, comprehension_score, words_looked_up, hsk_level)
        VALUES (1, 'listen_1', 0.9, 1, 1);
        INSERT INTO listening_progress (user_id, passage_id, comprehension_score, words_looked_up, hsk_level)
        VALUES (1, 'listen_2', 0.6, 4, 2);

        INSERT INTO learner_proficiency_zones (id, user_id, vocab_hsk_estimate, composite_hsk_estimate)
        VALUES (1, 1, 1.8, 1.5);

        INSERT INTO error_focus (user_id, content_item_id, resolved) VALUES (1, 1, 0);
        INSERT INTO error_focus (user_id, content_item_id, resolved) VALUES (1, 2, 0);
        INSERT INTO error_focus (user_id, content_item_id, resolved) VALUES (1, 1, 0);
        INSERT INTO error_focus (user_id, content_item_id, resolved) VALUES (1, 2, 1);

        INSERT INTO classroom_member (classroom_id, user_id, role) VALUES (1, 1, 'student');
        INSERT INTO classroom_member (classroom_id, user_id, role) VALUES (1, 2, 'student');

        INSERT INTO content_generation_queue (gap_type, status) VALUES ('grammar_pattern_no_items', 'pending');
        INSERT INTO content_generation_queue (gap_type, status) VALUES ('hsk_coverage_gap', 'pending');

        INSERT INTO product_audit (id, grade, score, findings_json)
        VALUES (1, 'B+', 83.2, '[{"title":"Grammar coverage thin","severity":"high"}]');
    """)
    return conn


class TestMCPServerCreation(unittest.TestCase):
    def test_import_graceful_without_mcp(self):
        from mandarin.openclaw import mcp_server
        self.assertTrue(hasattr(mcp_server, 'create_mcp_server'))

    @patch.dict("sys.modules", {"mcp": None, "mcp.server": None, "mcp.server.fastmcp": None})
    def test_create_fails_without_mcp(self):
        import importlib
        from mandarin.openclaw import mcp_server
        if not mcp_server._HAS_MCP:
            with self.assertRaises(ImportError):
                mcp_server.create_mcp_server()


# ── Learner Model Tools ──────────────────────────────────────

class TestLearnerModelQueries(unittest.TestCase):
    """Test the DB queries underlying the 10 Learner Model MCP tools."""

    def setUp(self):
        self.conn = _make_db()

    def test_learner_profile(self):
        profile = self.conn.execute(
            "SELECT * FROM learner_profile WHERE user_id = ?", (1,)
        ).fetchone()
        self.assertIsNotNone(profile)
        self.assertEqual(profile["target_sessions_per_week"], 5)

    def test_mastery_overview_by_hsk(self):
        rows = self.conn.execute("""
            SELECT ci.hsk_level,
                   COUNT(DISTINCT p.content_item_id) as items_seen,
                   SUM(p.total_attempts) as total_attempts,
                   SUM(p.total_correct) as total_correct,
                   SUM(CASE WHEN p.mastery_stage = 'durable' THEN 1 ELSE 0 END) as durable,
                   SUM(CASE WHEN p.mastery_stage = 'stable' THEN 1 ELSE 0 END) as stable
            FROM progress p
            JOIN content_item ci ON ci.id = p.content_item_id
            WHERE p.user_id = 1
            GROUP BY ci.hsk_level
        """).fetchall()
        self.assertGreater(len(rows), 0)
        # Both items are HSK 1
        hsk1 = rows[0]
        self.assertEqual(hsk1["hsk_level"], 1)
        self.assertEqual(hsk1["items_seen"], 2)
        self.assertEqual(hsk1["durable"], 1)
        self.assertEqual(hsk1["stable"], 1)

    def test_session_history(self):
        rows = self.conn.execute("""
            SELECT started_at, duration_seconds, items_completed, items_correct,
                   session_outcome, early_exit, client_platform
            FROM session_log WHERE user_id = 1
            ORDER BY started_at DESC
        """).fetchall()
        self.assertEqual(len(rows), 2)
        # Most recent session
        self.assertEqual(rows[0]["session_outcome"], "completed")
        self.assertEqual(rows[0]["client_platform"], "ios")
        # Older session was early exit
        self.assertEqual(rows[1]["early_exit"], 1)

    def test_error_analysis_distribution(self):
        errors = self.conn.execute("""
            SELECT el.error_type, COUNT(*) as cnt
            FROM error_log el WHERE el.user_id = 1
            GROUP BY el.error_type ORDER BY cnt DESC
        """).fetchall()
        self.assertEqual(len(errors), 2)
        self.assertEqual(errors[0]["error_type"], "tone_error")
        self.assertEqual(errors[0]["cnt"], 2)

    def test_error_analysis_struggling_items(self):
        items = self.conn.execute("""
            SELECT ci.hanzi, ci.english, el.error_type, COUNT(*) as cnt
            FROM error_log el
            JOIN content_item ci ON ci.id = el.content_item_id
            WHERE el.user_id = 1
            GROUP BY ci.id, el.error_type ORDER BY cnt DESC
        """).fetchall()
        self.assertGreater(len(items), 0)
        self.assertEqual(items[0]["hanzi"], "你好")
        self.assertEqual(items[0]["cnt"], 2)

    def test_error_analysis_grammar_gaps(self):
        grammar = self.conn.execute("""
            SELECT gp.name, gp.hsk_level,
                   AVG(CASE WHEN re.correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy,
                   COUNT(*) as attempts
            FROM grammar_point gp
            JOIN content_grammar cg ON cg.grammar_point_id = gp.id
            JOIN review_event re ON re.content_item_id = cg.content_item_id
            WHERE re.user_id = 1
            GROUP BY gp.id
            HAVING accuracy < 0.7
        """).fetchall()
        # SVO pattern: 1 correct, 1 incorrect = 0.5 accuracy (out of 2 reviews on item 1)
        self.assertEqual(len(grammar), 1)
        self.assertEqual(grammar[0]["name"], "Subject-Verb-Object")
        self.assertLess(grammar[0]["accuracy"], 0.7)

    def test_speaking_progress(self):
        recordings = self.conn.execute("""
            SELECT ar.content_item_id, ci.hanzi, ar.overall_score, ar.tone_scores_json
            FROM audio_recording ar
            JOIN content_item ci ON ci.id = ar.content_item_id
            WHERE ar.user_id = 1
            ORDER BY ar.id DESC
        """).fetchall()
        self.assertEqual(len(recordings), 2)
        scores = [r["overall_score"] for r in recordings]
        self.assertIn(0.85, scores)
        self.assertIn(0.72, scores)

    def test_speaking_tone_aggregation(self):
        recordings = self.conn.execute(
            "SELECT tone_scores_json FROM audio_recording WHERE user_id = 1"
        ).fetchall()
        tone_counts = {3: {"correct": 0, "total": 0}, 4: {"correct": 0, "total": 0}}
        for r in recordings:
            syllables = json.loads(r["tone_scores_json"] or "[]")
            for s in syllables:
                expected = s.get("expected", 0)
                if expected in tone_counts:
                    tone_counts[expected]["total"] += 1
                    if s.get("correct", False):
                        tone_counts[expected]["correct"] += 1
        # Tone 3: 1 correct, 1 incorrect
        self.assertEqual(tone_counts[3]["total"], 2)
        self.assertEqual(tone_counts[3]["correct"], 1)
        # Tone 4: 1 correct
        self.assertEqual(tone_counts[4]["total"], 1)
        self.assertEqual(tone_counts[4]["correct"], 1)

    def test_reading_progress(self):
        stats = self.conn.execute("""
            SELECT COUNT(*) as total,
                   AVG(comprehension_score) as avg_comp,
                   SUM(words_looked_up) as total_lookups,
                   AVG(reading_time_seconds) as avg_time
            FROM reading_progress WHERE user_id = 1
        """).fetchone()
        self.assertEqual(stats["total"], 2)
        self.assertAlmostEqual(stats["avg_comp"], 0.725, places=2)
        self.assertEqual(stats["total_lookups"], 8)

    def test_listening_progress(self):
        stats = self.conn.execute("""
            SELECT COUNT(*) as total,
                   AVG(comprehension_score) as avg_comp,
                   SUM(words_looked_up) as lookups
            FROM listening_progress WHERE user_id = 1
        """).fetchone()
        self.assertEqual(stats["total"], 2)
        self.assertAlmostEqual(stats["avg_comp"], 0.75, places=2)
        self.assertEqual(stats["lookups"], 5)

    def test_listening_by_level(self):
        by_level = self.conn.execute("""
            SELECT hsk_level, COUNT(*) as cnt,
                   AVG(comprehension_score) as avg_comp
            FROM listening_progress WHERE user_id = 1
            GROUP BY hsk_level ORDER BY hsk_level
        """).fetchall()
        self.assertEqual(len(by_level), 2)
        self.assertEqual(by_level[0]["hsk_level"], 1)
        self.assertAlmostEqual(by_level[0]["avg_comp"], 0.9, places=2)

    def test_vocabulary_coverage(self):
        totals = self.conn.execute("""
            SELECT hsk_level, COUNT(*) as cnt
            FROM content_item WHERE review_status = 'approved'
            GROUP BY hsk_level
        """).fetchall()
        # 2 HSK1 items, 1 HSK2 item
        total_map = {r["hsk_level"]: r["cnt"] for r in totals}
        self.assertEqual(total_map[1], 2)
        self.assertEqual(total_map[2], 1)

        known = self.conn.execute("""
            SELECT ci.hsk_level, COUNT(DISTINCT p.content_item_id) as known
            FROM progress p
            JOIN content_item ci ON ci.id = p.content_item_id
            WHERE p.user_id = 1
            AND p.mastery_stage IN ('passed_once', 'stabilizing', 'stable', 'durable')
            GROUP BY ci.hsk_level
        """).fetchall()
        known_map = {r["hsk_level"]: r["known"] for r in known}
        self.assertEqual(known_map[1], 2)  # Both HSK1 items known

    def test_grammar_mastery(self):
        rows = self.conn.execute("""
            SELECT gp.id, gp.name, gp.name_zh, gp.hsk_level, gp.category,
                   gpr.mastery_score, gpr.drill_attempts, gpr.drill_correct, gpr.studied_at
            FROM grammar_point gp
            LEFT JOIN grammar_progress gpr
                ON gp.id = gpr.grammar_point_id AND gpr.user_id = 1
            ORDER BY gp.hsk_level, gp.id
        """).fetchall()
        self.assertEqual(len(rows), 2)
        # First point has progress
        self.assertIsNotNone(rows[0]["studied_at"])
        self.assertAlmostEqual(rows[0]["mastery_score"], 0.85, places=2)
        # Second point unstudied
        self.assertIsNone(rows[1]["studied_at"])

    def test_search_vocabulary_by_hanzi(self):
        rows = self.conn.execute("""
            SELECT id, hanzi, pinyin, english, hsk_level
            FROM content_item
            WHERE review_status = 'approved'
            AND (hanzi LIKE ? OR pinyin LIKE ? OR english LIKE ?)
            LIMIT 10
        """, ("%你%", "%你%", "%你%")).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hanzi"], "你好")

    def test_search_vocabulary_by_english(self):
        rows = self.conn.execute("""
            SELECT id, hanzi FROM content_item
            WHERE review_status = 'approved'
            AND (hanzi LIKE ? OR pinyin LIKE ? OR english LIKE ?)
        """, ("%thank%", "%thank%", "%thank%")).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hanzi"], "谢谢")


# ── Session & Scheduling Tools ───────────────────────────────

class TestSessionSchedulingQueries(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()

    def test_due_items(self):
        due = self.conn.execute("""
            SELECT COUNT(*) as cnt FROM progress
            WHERE user_id = 1 AND next_review_date <= date('now')
        """).fetchone()
        self.assertEqual(due["cnt"], 1)  # Only item 1 is due today

    def test_due_struggling_items(self):
        struggling = self.conn.execute("""
            SELECT ci.hanzi, ci.english, p.total_correct, p.total_attempts
            FROM progress p
            JOIN content_item ci ON ci.id = p.content_item_id
            WHERE p.user_id = 1 AND p.total_attempts > 0
            ORDER BY CAST(p.total_correct AS REAL) / p.total_attempts ASC
            LIMIT 3
        """).fetchall()
        self.assertGreater(len(struggling), 0)
        # Item 1 has 80% accuracy, item 2 has 100%
        self.assertEqual(struggling[0]["hanzi"], "你好")

    def test_schedule_recommendation_due_items(self):
        due = self.conn.execute("""
            SELECT COUNT(*) as cnt FROM progress
            WHERE user_id = 1 AND next_review_date <= date('now')
        """).fetchone()
        self.assertGreater(due["cnt"], 0)

    def test_schedule_recommendation_weak_grammar(self):
        grammar = self.conn.execute("""
            SELECT gp.name, gp.hsk_level, COALESCE(gpr.mastery_score, 0) as score
            FROM grammar_point gp
            LEFT JOIN grammar_progress gpr
                ON gp.id = gpr.grammar_point_id AND gpr.user_id = 1
            WHERE COALESCE(gpr.mastery_score, 0) < 0.5
            ORDER BY score ASC
        """).fetchall()
        # Aspect particle 了 has no progress (mastery=0)
        self.assertEqual(len(grammar), 1)
        self.assertEqual(grammar[0]["name"], "Aspect particle 了")

    def test_schedule_recommendation_active_errors(self):
        active = self.conn.execute("""
            SELECT COUNT(*) as cnt FROM error_focus
            WHERE user_id = 1 AND resolved = 0
        """).fetchone()
        self.assertEqual(active["cnt"], 3)

    def test_schedule_recommendation_modality_balance(self):
        modalities = self.conn.execute("""
            SELECT modality, COUNT(*) as cnt
            FROM review_event WHERE user_id = 1
            GROUP BY modality
        """).fetchall()
        mod_map = {r["modality"]: r["cnt"] for r in modalities}
        self.assertIn("reading", mod_map)
        self.assertIn("speaking", mod_map)

    def test_commitment_status(self):
        profile = self.conn.execute(
            "SELECT target_sessions_per_week FROM learner_profile WHERE user_id = 1"
        ).fetchone()
        self.assertEqual(profile["target_sessions_per_week"], 5)

        completed = self.conn.execute("""
            SELECT COUNT(*) as cnt FROM session_log
            WHERE user_id = 1 AND session_outcome = 'completed'
        """).fetchone()
        self.assertEqual(completed["cnt"], 1)

    def test_streak_status(self):
        user = self.conn.execute(
            "SELECT streak_days, streak_freezes_available FROM user WHERE id = 1"
        ).fetchone()
        self.assertEqual(user["streak_days"], 7)
        self.assertEqual(user["streak_freezes_available"], 2)

    def test_streak_status_missing_user(self):
        user = self.conn.execute(
            "SELECT streak_days FROM user WHERE id = 999"
        ).fetchone()
        self.assertIsNone(user)

    def test_queue_session_calculation(self):
        minutes = 10
        drill_count = max(5, min(minutes * 4, 40))
        self.assertEqual(drill_count, 40)

        minutes = 1
        drill_count = max(5, min(minutes * 4, 40))
        self.assertEqual(drill_count, 5)


# ── Admin Operations Tools ───────────────────────────────────

class TestAdminOperationsQueries(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()

    def test_review_queue_summary(self):
        rows = self.conn.execute("""
            SELECT gap_type, COUNT(*) as cnt, MIN(created_at) as oldest
            FROM content_generation_queue WHERE status = 'pending'
            GROUP BY gap_type
        """).fetchall()
        self.assertEqual(len(rows), 2)
        total = sum(r["cnt"] for r in rows)
        self.assertEqual(total, 2)

    def test_latest_audit_summary(self):
        audit = self.conn.execute("""
            SELECT grade, score, findings_json
            FROM product_audit ORDER BY created_at DESC LIMIT 1
        """).fetchone()
        self.assertEqual(audit["grade"], "B+")
        findings = json.loads(audit["findings_json"])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")

    def test_learner_briefing_errors(self):
        errors = self.conn.execute("""
            SELECT ci.hanzi, el.error_type, el.modality, COUNT(*) as count
            FROM error_log el
            JOIN content_item ci ON ci.id = el.content_item_id
            GROUP BY ci.hanzi, el.error_type
            ORDER BY count DESC LIMIT 10
        """).fetchall()
        self.assertGreater(len(errors), 0)
        self.assertEqual(errors[0]["hanzi"], "你好")
        self.assertEqual(errors[0]["error_type"], "tone_error")

    def test_learner_briefing_proficiency(self):
        proficiency = self.conn.execute(
            "SELECT * FROM learner_proficiency_zones WHERE user_id = 1"
        ).fetchone()
        self.assertIsNotNone(proficiency)
        self.assertAlmostEqual(proficiency["composite_hsk_estimate"], 1.5)
        self.assertAlmostEqual(proficiency["vocab_hsk_estimate"], 1.8)

    def test_approve_review_item(self):
        item_id = self.conn.execute(
            "SELECT id FROM content_generation_queue WHERE status = 'pending' LIMIT 1"
        ).fetchone()[0]

        result = self.conn.execute("""
            UPDATE content_generation_queue
            SET status = 'approved', reviewed_at = datetime('now')
            WHERE id = ? AND status = 'pending'
        """, (item_id,))
        self.conn.commit()
        self.assertEqual(result.rowcount, 1)

        row = self.conn.execute(
            "SELECT status FROM content_generation_queue WHERE id = ?", (item_id,)
        ).fetchone()
        self.assertEqual(row["status"], "approved")

    def test_reject_review_item(self):
        item_id = self.conn.execute(
            "SELECT id FROM content_generation_queue WHERE status = 'pending' LIMIT 1"
        ).fetchone()[0]

        result = self.conn.execute("""
            UPDATE content_generation_queue
            SET status = 'rejected', reviewer_note = 'inaccurate', reviewed_at = datetime('now')
            WHERE id = ? AND status = 'pending'
        """, (item_id,))
        self.conn.commit()
        self.assertEqual(result.rowcount, 1)

    def test_approve_nonexistent_item(self):
        result = self.conn.execute("""
            UPDATE content_generation_queue
            SET status = 'approved', reviewed_at = datetime('now')
            WHERE id = 99999 AND status = 'pending'
        """)
        self.assertEqual(result.rowcount, 0)


# ── Institutional Tools ──────────────────────────────────────

class TestInstitutionalQueries(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()

    def test_class_progress_students(self):
        students = self.conn.execute("""
            SELECT cm.user_id, u.email, u.display_name
            FROM classroom_member cm
            JOIN user u ON u.id = cm.user_id
            WHERE cm.classroom_id = 1 AND cm.role = 'student'
        """).fetchall()
        self.assertEqual(len(students), 2)

    def test_class_progress_session_counts(self):
        for uid in (1, 2):
            sessions = self.conn.execute("""
                SELECT COUNT(*) as cnt FROM session_log
                WHERE user_id = ? AND session_outcome = 'completed'
            """, (uid,)).fetchone()
            if uid == 1:
                self.assertEqual(sessions["cnt"], 1)
            else:
                self.assertEqual(sessions["cnt"], 0)

    def test_class_progress_accuracy(self):
        accuracy = self.conn.execute("""
            SELECT AVG(CASE WHEN correct = 1 THEN 1.0 ELSE 0.0 END) as acc
            FROM review_event WHERE user_id = 1
        """).fetchone()
        # 2 correct out of 3 = 0.667
        self.assertAlmostEqual(accuracy["acc"], 0.667, places=2)

    def test_engagement_individual_user(self):
        sessions = self.conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN started_at >= datetime('now', '-7 days') THEN 1 END) as week,
                   COUNT(CASE WHEN started_at >= datetime('now', '-30 days') THEN 1 END) as month
            FROM session_log WHERE user_id = 1 AND session_outcome = 'completed'
        """).fetchone()
        self.assertEqual(sessions["total"], 1)
        self.assertEqual(sessions["week"], 1)
        self.assertEqual(sessions["month"], 1)

    def test_engagement_early_exit_rate(self):
        exits = self.conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN early_exit = 1 THEN 1 ELSE 0 END) as early
            FROM session_log WHERE user_id = 1
        """).fetchone()
        early_rate = round((exits["early"] or 0) / max(exits["total"] or 1, 1), 3)
        self.assertAlmostEqual(early_rate, 0.5, places=2)

    def test_engagement_churn_risk(self):
        sessions = self.conn.execute("""
            SELECT COUNT(CASE WHEN started_at >= datetime('now', '-7 days') THEN 1 END) as week,
                   COUNT(CASE WHEN started_at >= datetime('now', '-30 days') THEN 1 END) as month
            FROM session_log WHERE user_id = 1 AND session_outcome = 'completed'
        """).fetchone()
        week = sessions["week"] or 0
        month = sessions["month"] or 0
        risk = "high" if week == 0 and month > 0 else "low" if week >= 3 else "medium"
        self.assertEqual(risk, "medium")  # 1 session this week

    def test_engagement_platform_aggregate(self):
        totals = self.conn.execute("""
            SELECT COUNT(DISTINCT user_id) as users,
                   COUNT(*) as sessions,
                   COUNT(DISTINCT CASE WHEN started_at >= datetime('now', '-7 days') THEN user_id END) as wau
            FROM session_log WHERE session_outcome = 'completed'
        """).fetchone()
        self.assertEqual(totals["users"], 1)
        self.assertGreaterEqual(totals["sessions"], 1)

    def test_engagement_no_sessions_user(self):
        sessions = self.conn.execute("""
            SELECT COUNT(*) as total FROM session_log
            WHERE user_id = 2 AND session_outcome = 'completed'
        """).fetchone()
        self.assertEqual(sessions["total"], 0)


# ── Security Scoping ─────────────────────────────────────────

class TestMCPSecurityScoping(unittest.TestCase):

    def test_no_arbitrary_sql_tool(self):
        from mandarin.openclaw import mcp_server
        self.assertFalse(hasattr(mcp_server, 'execute_sql'))
        self.assertFalse(hasattr(mcp_server, 'run_query'))

    def test_module_has_create_mcp_server(self):
        from mandarin.openclaw import mcp_server
        self.assertTrue(hasattr(mcp_server, 'create_mcp_server'))
        self.assertTrue(hasattr(mcp_server, 'main'))

    def test_expected_tool_names_in_source(self):
        """All 25 tool names should appear in the module source."""
        import inspect
        from mandarin.openclaw import mcp_server
        source = inspect.getsource(mcp_server)
        expected_tools = [
            "get_learner_profile", "get_mastery_overview", "get_session_history",
            "get_error_analysis", "get_speaking_progress", "get_reading_progress",
            "get_listening_progress", "get_vocabulary_coverage", "get_grammar_mastery",
            "search_vocabulary",
            "get_due_items", "get_schedule_recommendation", "get_commitment_status",
            "get_streak_status", "queue_session",
            "get_review_queue_summary", "get_latest_audit_summary",
            "get_learner_briefing", "approve_review_item", "reject_review_item",
            "get_class_progress", "get_engagement_metrics",
            "get_content_gaps", "get_user_content_gaps",
        ]
        for tool_name in expected_tools:
            self.assertIn(f"def {tool_name}", source, f"Tool {tool_name} not found in mcp_server.py")

    def test_write_ops_limited(self):
        """Only approve/reject are write operations."""
        import inspect
        from mandarin.openclaw import mcp_server
        source = inspect.getsource(mcp_server)
        # Should not have DELETE or DROP
        self.assertNotIn("DELETE FROM", source)
        self.assertNotIn("DROP TABLE", source)
        # UPDATE only in approve/reject
        update_count = source.count("UPDATE content_generation_queue")
        self.assertEqual(update_count, 2)  # approve + reject


if __name__ == "__main__":
    unittest.main()
