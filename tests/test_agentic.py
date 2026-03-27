"""Tests for Doc 23: Agentic Technology Layer."""

import json
import unittest

from mandarin.db.core import SCHEMA_VERSION
from mandarin.ai.agentic import (
    validate_structured_output,
    run_parallel_audit,
    check_content_pipeline_circuit_breaker,
    detect_content_gaps,
    queue_auto_generation,
    get_focused_learner_context,
    log_competitor_signal,
    log_research_signal,
    classify_prescription,
    execute_prescription,
    analyze_agentic_health,
    OUTPUT_SCHEMA_REGISTRY,
)


from tests.shared_db import make_test_db as _make_db


class TestStructuredOutput(unittest.TestCase):
    def test_validation_passes_for_valid_data(self):
        if not OUTPUT_SCHEMA_REGISTRY:
            self.skipTest("Pydantic not available")
        result, error = validate_structured_output(
            {"usage_context": "greeting", "register": "neutral",
             "example_sentence": "你好"},
            "usage_map_generation",
        )
        self.assertTrue(result)
        self.assertIsNone(error)

    def test_validation_fails_for_missing_fields(self):
        if not OUTPUT_SCHEMA_REGISTRY:
            self.skipTest("Pydantic not available")
        result, error = validate_structured_output(
            {"usage_context": "greeting"},  # missing required fields
            "usage_map_generation",
        )
        self.assertFalse(result)
        self.assertIsNotNone(error)

    def test_unknown_key_passes(self):
        result, error = validate_structured_output(
            {"any": "data"}, "unknown_prompt_key"
        )
        self.assertTrue(result)


class TestParallelAudit(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_runs_analyzers_in_parallel(self):
        def analyzer_a(conn):
            return [{"dimension": "test_a", "severity": "low", "title": "A"}]

        def analyzer_b(conn):
            return [{"dimension": "test_b", "severity": "low", "title": "B"}]

        findings = run_parallel_audit(self.conn, [analyzer_a, analyzer_b])
        self.assertEqual(len(findings), 2)
        dims = {f["dimension"] for f in findings}
        self.assertEqual(dims, {"test_a", "test_b"})

    def test_handles_analyzer_failure(self):
        def good_analyzer(conn):
            return [{"dimension": "good", "severity": "low", "title": "Good"}]

        def bad_analyzer(conn):
            raise ValueError("intentional test error")

        findings = run_parallel_audit(self.conn, [good_analyzer, bad_analyzer])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["dimension"], "good")

    def test_logs_execution(self):
        def noop_analyzer(conn):
            return []

        run_parallel_audit(self.conn, [noop_analyzer])
        row = self.conn.execute(
            "SELECT * FROM agent_task_log WHERE task_type='parallel_audit'"
        ).fetchone()
        self.assertIsNotNone(row)


class TestContentPipeline(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_circuit_breaker_closed_by_default(self):
        self.assertFalse(check_content_pipeline_circuit_breaker(self.conn))

    def test_circuit_breaker_opens_on_high_rejection(self):
        # Insert 10 items: 5 rejected, 5 approved (50% > 40% threshold)
        for i in range(10):
            status = "rejected" if i < 5 else "approved"
            self.conn.execute("""
                INSERT INTO content_generation_queue (gap_type, status)
                VALUES ('test', ?)
            """, (status,))

        self.assertTrue(check_content_pipeline_circuit_breaker(self.conn))

    def test_circuit_breaker_opens_on_too_many_pending(self):
        for i in range(35):
            self.conn.execute("""
                INSERT INTO content_generation_queue (gap_type, status)
                VALUES ('test', 'pending')
            """)
        self.assertTrue(check_content_pipeline_circuit_breaker(self.conn))

    def test_detect_gaps_finds_patterns_without_items(self):
        self.conn.execute(
            "INSERT INTO grammar_point (name, hsk_level) VALUES ('orphan', 3)"
        )
        gaps = detect_content_gaps(self.conn)
        self.assertTrue(len(gaps) > 0)
        self.assertEqual(gaps[0]["gap_type"], "grammar_pattern_no_items")

    def test_queue_auto_generation(self):
        gap = {"gap_type": "test_gap", "name": "test"}
        qid = queue_auto_generation(self.conn, gap, "test brief")
        self.assertIsNotNone(qid)

        row = self.conn.execute(
            "SELECT * FROM content_generation_queue WHERE id=?", (qid,)
        ).fetchone()
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["generation_brief"], "test brief")

    def test_queue_blocked_by_circuit_breaker(self):
        # Fill up pending queue to trigger breaker
        for i in range(35):
            self.conn.execute(
                "INSERT INTO content_generation_queue (gap_type, status) VALUES ('test', 'pending')"
            )
        gap = {"gap_type": "test_gap"}
        result = queue_auto_generation(self.conn, gap, "brief")
        self.assertIsNone(result)


class TestFocusedLearnerContext(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_returns_proficiency(self):
        self.conn.execute("""
            INSERT INTO learner_proficiency_zones
            (user_id, composite_hsk_estimate, vocab_hsk_estimate)
            VALUES (1, 3.5, 3.0)
        """)
        ctx = get_focused_learner_context(self.conn, 1, "drill_generation")
        self.assertEqual(ctx["composite_hsk"], 3.5)

    def test_drill_generation_includes_errors(self):
        ci_id = self.conn.execute(
            "INSERT INTO content_item (hanzi, pinyin, english) VALUES ('书', 'shū', 'book')"
        ).lastrowid
        for _ in range(3):
            self.conn.execute(
                "INSERT INTO review_event (user_id, content_item_id, correct) VALUES (1, ?, 0)",
                (ci_id,),
            )

        ctx = get_focused_learner_context(self.conn, 1, "drill_generation")
        self.assertIn("recent_errors", ctx)
        self.assertTrue(len(ctx["recent_errors"]) > 0)

    def test_usage_map_includes_lenses(self):
        self.conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, content_lens)
            VALUES ('test', 'test', 'test', 'urban_texture')
        """)
        ctx = get_focused_learner_context(self.conn, 1, "usage_map")
        self.assertIn("active_lenses", ctx)
        self.assertIn("urban_texture", ctx["active_lenses"])


class TestCompetitorResearchSignals(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_log_competitor_signal(self):
        sig_id = log_competitor_signal(
            self.conn, source="duolingo_blog",
            signal_type="feature_release",
            title="Duolingo adds character writing",
            detail="New writing practice mode",
            source_url="https://example.com",
        )
        self.assertIsNotNone(sig_id)

    def test_log_research_signal(self):
        sig_id = log_research_signal(
            self.conn, source="arxiv",
            title="Improved FSRS parameters",
            finding="New calibration method improves retention 15%",
            applicability_score=0.85,
            doi="10.1234/test",
        )
        self.assertIsNotNone(sig_id)


class TestPrescriptionExecution(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_classify_generate_content(self):
        result = classify_prescription("Generate content for HSK 3 gaps")
        self.assertEqual(result, "generate_content")

    def test_classify_requires_human(self):
        result = classify_prescription("Review learner feedback and decide")
        self.assertEqual(result, "requires_human")

    def test_classify_fsrs_calibration(self):
        result = classify_prescription("Calibrate FSRS parameters based on data")
        self.assertEqual(result, "recalibrate_fsrs")

    def test_execute_nonexistent_work_order(self):
        result = execute_prescription(self.conn, 9999)
        self.assertEqual(result["status"], "error")

    def test_execute_human_required(self):
        self.conn.execute("""
            INSERT INTO pi_work_order (instruction, status)
            VALUES ('Review and decide manually', 'pending')
        """)
        wo_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        result = execute_prescription(self.conn, wo_id)
        self.assertEqual(result["status"], "requires_human")

    def test_execute_content_generation(self):
        self.conn.execute(
            "INSERT INTO grammar_point (name, hsk_level) VALUES ('test_pattern', 2)"
        )
        self.conn.execute("""
            INSERT INTO pi_work_order (instruction, status)
            VALUES ('Generate content for uncovered patterns', 'pending')
        """)
        wo_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        result = execute_prescription(self.conn, wo_id)
        self.assertEqual(result["status"], "executed")

        # Check execution was logged
        log = self.conn.execute(
            "SELECT * FROM prescription_execution_log WHERE work_order_id=?",
            (wo_id,),
        ).fetchone()
        self.assertIsNotNone(log)
        self.assertEqual(log["action_type"], "generate_content")


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_db_no_findings(self):
        findings = analyze_agentic_health(self.conn)
        self.assertEqual(findings, [])

    def test_circuit_breaker_triggers_finding(self):
        for i in range(10):
            status = "rejected" if i < 5 else "approved"
            self.conn.execute("""
                INSERT INTO content_generation_queue (gap_type, status)
                VALUES ('test', ?)
            """, (status,))

        findings = analyze_agentic_health(self.conn)
        cb_findings = [f for f in findings if "circuit breaker" in f["title"].lower()]
        self.assertEqual(len(cb_findings), 1)

    def test_high_execution_error_rate(self):
        for i in range(10):
            status = "error" if i < 5 else "executed"
            self.conn.execute("""
                INSERT INTO prescription_execution_log
                (work_order_id, action_type, status)
                VALUES (?, 'test', ?)
            """, (i, status))

        findings = analyze_agentic_health(self.conn)
        error_findings = [f for f in findings if "error rate" in f["title"].lower()]
        self.assertEqual(len(error_findings), 1)


class TestSchemaVersion(unittest.TestCase):
    def test_schema_version_includes_doc23(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 84)


if __name__ == "__main__":
    unittest.main()
