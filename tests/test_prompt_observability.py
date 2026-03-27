"""Tests for Doc 23 C-02: Prompt Observability."""

import unittest

from mandarin.ai.prompt_observability import (
    trace_prompt_call,
    compute_prompt_spc,
    detect_prompt_regression,
    get_prompt_health_dashboard,
    analyze_prompt_health,
)


from tests.shared_db import make_test_db as _make_db


class TestTracePromptCall(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_basic_trace(self):
        trace_id = trace_prompt_call(
            self.conn,
            prompt_key="test_prompt",
            prompt_text="hello world",
            response_text="response",
            latency_ms=100,
            model_used="qwen2.5:7b",
            success=True,
        )
        self.assertIsNotNone(trace_id)

        row = self.conn.execute(
            "SELECT * FROM prompt_trace WHERE id = ?", (trace_id,)
        ).fetchone()
        self.assertEqual(row["prompt_key"], "test_prompt")
        self.assertEqual(row["latency_ms"], 100)
        self.assertEqual(row["success"], 1)

    def test_trace_failure(self):
        trace_id = trace_prompt_call(
            self.conn,
            prompt_key="fail_prompt",
            prompt_text="test",
            response_text="",
            latency_ms=50,
            model_used="qwen2.5:7b",
            success=False,
            error_type="timeout",
        )
        row = self.conn.execute(
            "SELECT * FROM prompt_trace WHERE id = ?", (trace_id,)
        ).fetchone()
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["error_type"], "timeout")


class TestComputePromptSPC(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_data(self):
        result = compute_prompt_spc(self.conn, "nonexistent")
        self.assertEqual(result["sample_size"], 0)

    def test_spc_with_data(self):
        for i in range(20):
            trace_prompt_call(
                self.conn,
                prompt_key="spc_test",
                prompt_text=f"prompt {i}",
                response_text=f"response {i}",
                latency_ms=100 + i * 10,
                model_used="qwen2.5:7b",
                success=True,
            )

        result = compute_prompt_spc(self.conn, "spc_test")
        self.assertEqual(result["sample_size"], 20)
        self.assertEqual(result["success_rate"], 1.0)
        self.assertGreater(result["latency_p50_ms"], 0)
        self.assertIsNotNone(result["latency_ucl_ms"])

    def test_mixed_success_rate(self):
        for i in range(10):
            trace_prompt_call(
                self.conn, prompt_key="mixed",
                prompt_text=f"p{i}", response_text=f"r{i}",
                latency_ms=100, model_used="test",
                success=i < 7,  # 7 success, 3 failure
            )

        result = compute_prompt_spc(self.conn, "mixed")
        self.assertAlmostEqual(result["success_rate"], 0.7, places=2)


class TestDetectRegression(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_no_data_no_regression(self):
        regressions = detect_prompt_regression(self.conn, "empty")
        self.assertEqual(regressions, [])

    def test_insufficient_data(self):
        for i in range(5):
            trace_prompt_call(
                self.conn, prompt_key="small",
                prompt_text=f"p{i}", response_text=f"r{i}",
                latency_ms=100, model_used="test", success=True,
            )
        regressions = detect_prompt_regression(self.conn, "small")
        self.assertEqual(regressions, [])


class TestPromptHealthDashboard(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_dashboard(self):
        dashboard = get_prompt_health_dashboard(self.conn)
        self.assertEqual(dashboard, [])

    def test_dashboard_with_data(self):
        for i in range(5):
            trace_prompt_call(
                self.conn, prompt_key="dash_test",
                prompt_text=f"p{i}", response_text=f"r{i}",
                latency_ms=100, model_used="test", success=True,
            )

        dashboard = get_prompt_health_dashboard(self.conn)
        self.assertEqual(len(dashboard), 1)
        self.assertEqual(dashboard[0]["prompt_key"], "dash_test")
        self.assertEqual(dashboard[0]["status"], "healthy")


class TestAnalyzePromptHealth(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        # Need intelligence _base for _finding
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS product_audit (
                id INTEGER PRIMARY KEY, grade TEXT, score REAL,
                dimension_scores_json TEXT, findings_json TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)

    def test_no_findings_on_healthy(self):
        for i in range(5):
            trace_prompt_call(
                self.conn, prompt_key="healthy",
                prompt_text=f"p{i}", response_text=f"r{i}",
                latency_ms=100, model_used="test", success=True,
            )
        findings = analyze_prompt_health(self.conn)
        self.assertEqual(findings, [])

    def test_degraded_prompt_produces_finding(self):
        for i in range(10):
            trace_prompt_call(
                self.conn, prompt_key="bad_prompt",
                prompt_text=f"p{i}", response_text=f"r{i}",
                latency_ms=100, model_used="test",
                success=i < 5,  # 50% success = degraded
            )
        findings = analyze_prompt_health(self.conn)
        degraded = [f for f in findings if "degraded" in f["title"].lower()]
        self.assertTrue(len(degraded) > 0)


if __name__ == "__main__":
    unittest.main()
