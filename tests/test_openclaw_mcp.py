"""Tests for the expanded Aelu MCP Server — 25 tools across 5 categories."""

import json
import unittest
from unittest.mock import patch, MagicMock

from tests.shared_db import make_test_db


def _make_db():
    """Create test DB with seed data for MCP server tests."""
    conn = make_test_db()
    conn.executescript("""
        -- Seed users
        UPDATE user SET display_name='Test User', streak_freezes_available=2 WHERE id=1;
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name)
        VALUES (2, 'student2@aelu.app', 'test_hash', 'Student Two');

        INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level)
        VALUES (1, '你好', 'nǐ hǎo', 'hello', 1);
        INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level)
        VALUES (2, '谢谢', 'xiè xie', 'thank you', 1);
        INSERT INTO content_item (id, hanzi, pinyin, english, hsk_level)
        VALUES (3, '学习', 'xué xí', 'to study', 2);

        INSERT INTO grammar_point (id, name, name_zh, hsk_level, category)
        VALUES (1, 'Subject-Verb-Object', '主谓宾', 1, 'structure');
        INSERT INTO grammar_point (id, name, name_zh, hsk_level, category)
        VALUES (2, 'Aspect particle 了', '了', 1, 'particle');

        INSERT INTO grammar_progress (user_id, grammar_point_id, mastery_score, drill_attempts, drill_correct)
        VALUES (1, 1, 0.85, 20, 17);

        INSERT INTO content_grammar (content_item_id, grammar_point_id)
        VALUES (1, 1);

        INSERT INTO progress (user_id, content_item_id, modality, next_review_date, total_attempts, total_correct, mastery_stage)
        VALUES (1, 1, 'reading', date('now'), 10, 8, 'stable');
        INSERT INTO progress (user_id, content_item_id, modality, next_review_date, total_attempts, total_correct, mastery_stage)
        VALUES (1, 2, 'reading', date('now', '+3 days'), 5, 5, 'durable');

        INSERT INTO session_log (user_id, started_at, ended_at, duration_seconds, items_completed, items_correct, session_outcome, client_platform)
        VALUES (1, datetime('now', '-1 hour'), datetime('now'), 1200, 15, 12, 'completed', 'ios');
        INSERT INTO session_log (user_id, started_at, ended_at, duration_seconds, items_completed, items_correct, session_outcome, early_exit, client_platform)
        VALUES (1, datetime('now', '-2 days'), datetime('now', '-2 days', '+600 seconds'), 600, 5, 3, 'early_exit', 1, 'web');

        INSERT INTO error_log (user_id, content_item_id, error_type, modality)
        VALUES (1, 1, 'tone', 'speaking');
        INSERT INTO error_log (user_id, content_item_id, error_type, modality)
        VALUES (1, 1, 'tone', 'speaking');
        INSERT INTO error_log (user_id, content_item_id, error_type, modality)
        VALUES (1, 2, 'vocab', 'reading');

        INSERT INTO review_event (user_id, content_item_id, correct, modality)
        VALUES (1, 1, 1, 'reading');
        INSERT INTO review_event (user_id, content_item_id, correct, modality)
        VALUES (1, 1, 0, 'speaking');
        INSERT INTO review_event (user_id, content_item_id, correct, modality)
        VALUES (1, 2, 1, 'reading');

        INSERT INTO audio_recording (user_id, content_item_id, file_path, overall_score, tone_scores_json)
        VALUES (1, 1, '/tmp/test1.webm', 0.72, '[{"expected": 3, "correct": true}, {"expected": 3, "correct": false}]');
        INSERT INTO audio_recording (user_id, content_item_id, file_path, overall_score, tone_scores_json)
        VALUES (1, 2, '/tmp/test2.webm', 0.85, '[{"expected": 4, "correct": true}, {"expected": 0, "correct": true}]');

        INSERT INTO reading_progress (user_id, passage_id, words_looked_up, reading_time_seconds)
        VALUES (1, 'passage_1', 3, 120);
        INSERT INTO reading_progress (user_id, passage_id, words_looked_up, reading_time_seconds)
        VALUES (1, 'passage_2', 5, 180);

        INSERT INTO listening_progress (user_id, passage_id, comprehension_score, words_looked_up, hsk_level)
        VALUES (1, 'listen_1', 0.9, 1, 1);
        INSERT INTO listening_progress (user_id, passage_id, comprehension_score, words_looked_up, hsk_level)
        VALUES (1, 'listen_2', 0.6, 4, 2);

        INSERT INTO learner_proficiency_zones (user_id, vocab_hsk_estimate, composite_hsk_estimate)
        VALUES (1, 1.8, 1.5);

        INSERT INTO error_focus (user_id, content_item_id, error_type, resolved) VALUES (1, 1, 'tone', 0);
        INSERT INTO error_focus (user_id, content_item_id, error_type, resolved) VALUES (1, 2, 'tone', 0);

        INSERT INTO content_generation_queue (gap_type, status) VALUES ('grammar_pattern_no_items', 'pending');
        INSERT INTO content_generation_queue (gap_type, status) VALUES ('hsk_coverage_gap', 'pending');

        INSERT INTO product_audit (id, overall_grade, overall_score, findings_json, dimension_scores, findings_count)
        VALUES (1, 'B+', 83.2, '[{"title":"Grammar coverage thin","severity":"high"}]', '{}', 1);
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
        self.assertIn(profile["target_sessions_per_week"], (4, 5))

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
        self.assertEqual(errors[0]["error_type"], "tone")
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
        self.assertIn(profile["target_sessions_per_week"], (4, 5))

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
        self.assertEqual(errors[0]["error_type"], "tone")

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
