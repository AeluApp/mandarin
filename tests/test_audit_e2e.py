"""End-to-end test for run_product_audit — validates return dict shape on a populated DB."""

import unittest
from datetime import datetime, timezone, timedelta, UTC

from tests.conftest import make_test_db


def _seed_activity(conn):
    """Seed enough data for analyzers to have signal without hitting noise guards."""
    conn.execute("PRAGMA foreign_keys = OFF")
    now = datetime.now(UTC)

    # Users (20 total)
    for uid in range(2, 22):  # user 1 already exists from fixture
        conn.execute(
            "INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier, created_at) "
            "VALUES (?, ?, 'hash', ?, 'free', ?)",
            (uid, f"u{uid}@test.com", f"User {uid}",
             (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")),
        )

    # Sessions (60 total across users, spread over 14 days)
    for i in range(60):
        uid = (i % 20) + 1
        day_offset = i % 14
        started = (now - timedelta(days=day_offset, hours=i % 8)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO session_log (user_id, started_at, items_planned, items_completed, "
            "duration_seconds, early_exit, boredom_flags, client_platform) "
            "VALUES (?, ?, 10, ?, 300, 0, 0, 'web')",
            (uid, started, 8 + (i % 3)),
        )

    # Content items (50)
    for i in range(1, 51):
        conn.execute(
            "INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, hsk_level, item_type) "
            "VALUES (?, ?, ?, ?, ?, 'word')",
            (i, f"字{i}", f"zi{i}", f"word{i}", (i % 3) + 1),
        )

    # Review events (200)
    for i in range(200):
        uid = (i % 20) + 1
        cid = (i % 50) + 1
        day_offset = i % 14
        created = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO review_event (user_id, content_item_id, drill_type, correct, "
            "response_ms, created_at, session_id, modality) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'reading')",
            (uid, cid, "hanzi_to_english", 1 if i % 4 != 0 else 0,
             2000 + (i * 100), created, (i % 60) + 1),
        )

    # Progress records
    for cid in range(1, 31):
        conn.execute(
            "INSERT OR IGNORE INTO progress (user_id, content_item_id, ease_factor, "
            "interval_days, repetitions, mastery_stage) "
            "VALUES (1, ?, 2.5, 7, 5, 'stabilizing')",
            (cid,),
        )

    conn.commit()


class TestAuditE2E(unittest.TestCase):
    """End-to-end: run_product_audit returns correct structure on a populated DB."""

    @classmethod
    def setUpClass(cls):
        cls.conn, cls.path = make_test_db()
        _seed_activity(cls.conn)
        from mandarin.intelligence import run_product_audit
        cls.result = run_product_audit(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.path.unlink(missing_ok=True)

    def test_all_top_level_keys_present(self):
        expected_keys = {
            "findings", "dimension_scores", "overall", "trends", "synthesis",
            "data_confidence",
            "finding_lifecycle", "feedback_summary", "advisor_opinions",
            "sprint_plan", "decision_queue",
            "constraint", "copq", "false_negatives", "cycle_times", "self_audit",
            "work_order", "external_grounding", "release_regressions",
            "total", "by_severity", "by_dimension", "top_priorities",
        }
        missing = expected_keys - set(self.result.keys())
        self.assertEqual(missing, set(), f"Missing keys: {missing}")

    def test_findings_is_list_of_dicts(self):
        self.assertIsInstance(self.result["findings"], list)
        for f in self.result["findings"]:
            self.assertIsInstance(f, dict)
            self.assertIn("dimension", f)
            self.assertIn("severity", f)
            self.assertIn("title", f)

    def test_dimension_scores_structure(self):
        scores = self.result["dimension_scores"]
        self.assertIsInstance(scores, dict)
        self.assertGreater(len(scores), 0)
        for dim, info in scores.items():
            self.assertIn("score", info)
            self.assertIn("grade", info)
            self.assertIn("finding_count", info)
            self.assertIn("confidence", info)
            self.assertIn("trend", info)

    def test_overall_score_and_grade(self):
        overall = self.result["overall"]
        self.assertIn("score", overall)
        self.assertIn("grade", overall)
        self.assertIsInstance(overall["score"], (int, float))
        self.assertIn(overall["grade"], ("A", "B", "C", "D", "F"))

    def test_total_matches_findings_length(self):
        self.assertEqual(self.result["total"], len(self.result["findings"]))

    def test_by_severity_dict(self):
        by_sev = self.result["by_severity"]
        self.assertIsInstance(by_sev, dict)
        total = sum(by_sev.values())
        self.assertEqual(total, self.result["total"])

    def test_top_priorities_capped_at_five(self):
        self.assertLessEqual(len(self.result["top_priorities"]), 5)

    def test_trends_structure(self):
        trends = self.result["trends"]
        self.assertIsInstance(trends, dict)
        for dim, val in trends.items():
            self.assertIsInstance(val, dict)
            self.assertIn("arrow", val)

    def test_data_confidence_structure(self):
        dc = self.result["data_confidence"]
        self.assertIsInstance(dc, dict)
        for dim, conf in dc.items():
            self.assertIn(conf, ("high", "medium", "low", "none"))

    def test_synthesis_structure(self):
        synthesis = self.result["synthesis"]
        self.assertIsInstance(synthesis, dict)
        self.assertIn("summary", synthesis)
        self.assertIn("top_5", synthesis)

    def test_constraint_is_dict(self):
        self.assertIsInstance(self.result["constraint"], dict)

    def test_work_order_present(self):
        """work_order should be a dict (either a real order or no_actionable_findings)."""
        wo = self.result["work_order"]
        if wo is not None:
            self.assertIsInstance(wo, dict)
            self.assertIn("status", wo)

    def test_external_grounding_present(self):
        eg = self.result["external_grounding"]
        if eg is not None:
            self.assertIsInstance(eg, dict)
            self.assertIn("knowledge_conflicts", eg)
            self.assertIn("benchmark_comparisons", eg)

    def test_finding_lifecycle_is_dict(self):
        self.assertIsInstance(self.result["finding_lifecycle"], dict)

    def test_feedback_summary_is_dict(self):
        self.assertIsInstance(self.result["feedback_summary"], dict)

    def test_advisor_opinions_is_dict(self):
        self.assertIsInstance(self.result["advisor_opinions"], dict)

    def test_decision_queue_is_list(self):
        self.assertIsInstance(self.result["decision_queue"], list)

    def test_severity_ordering(self):
        """Findings should be sorted by severity (critical first)."""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings = self.result["findings"]
        if len(findings) >= 2:
            for i in range(len(findings) - 1):
                cur = severity_order.get(findings[i].get("severity", "low"), 9)
                nxt = severity_order.get(findings[i + 1].get("severity", "low"), 9)
                self.assertLessEqual(cur, nxt,
                    f"Finding '{findings[i]['title']}' ({findings[i]['severity']}) "
                    f"should come before '{findings[i+1]['title']}' ({findings[i+1]['severity']})")


if __name__ == "__main__":
    unittest.main()
