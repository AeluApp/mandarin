"""Tests for Doc 23 C-03: Durable Workflow Engine."""

import json
import sqlite3
import unittest

from mandarin.ai.workflow_engine import (
    DurableWorkflow,
    get_stale_workflows,
    get_workflow_status,
)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE workflow_execution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_type TEXT NOT NULL,
            workflow_data TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            current_step TEXT,
            max_retries INTEGER NOT NULL DEFAULT 3,
            retry_count INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            error_detail TEXT
        );
        CREATE TABLE workflow_step (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            step_order INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            input_data TEXT,
            output_data TEXT,
            started_at TEXT,
            completed_at TEXT,
            error_detail TEXT
        );
    """)
    return conn


class TestDurableWorkflow(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_execute_all_steps_pass(self):
        def step_a(conn, outputs):
            return {"result": "a_done"}

        def step_b(conn, outputs):
            return {"result": "b_done", "from_a": outputs.get("step_a", {}).get("result")}

        wf = DurableWorkflow(self.conn, "test_workflow")
        wf.add_step("step_a", step_a)
        wf.add_step("step_b", step_b)
        result = wf.execute()

        self.assertEqual(result["status"], "completed")
        self.assertIn("step_a", result["outputs"])
        self.assertIn("step_b", result["outputs"])
        self.assertEqual(result["outputs"]["step_b"]["from_a"], "a_done")

    def test_execute_step_failure(self):
        def step_ok(conn, outputs):
            return {"ok": True}

        def step_fail(conn, outputs):
            raise ValueError("intentional failure")

        wf = DurableWorkflow(self.conn, "fail_workflow")
        wf.add_step("ok_step", step_ok)
        wf.add_step("fail_step", step_fail)
        result = wf.execute()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_step"], "fail_step")
        self.assertIn("ok_step", result["completed_steps"])

    def test_resume_from_failure(self):
        call_count = {"n": 0}

        def step_ok(conn, outputs):
            return {"ok": True}

        def step_flaky(conn, outputs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError("first call fails")
            return {"recovered": True}

        wf = DurableWorkflow(self.conn, "resume_workflow")
        wf.add_step("ok_step", step_ok)
        wf.add_step("flaky_step", step_flaky)

        result = wf.execute()
        self.assertEqual(result["status"], "failed")

        result = wf.resume()
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["outputs"]["flaky_step"]["recovered"])

    def test_retry_increments_count(self):
        def step_always_fails(conn, outputs):
            raise ValueError("always fails")

        wf = DurableWorkflow(self.conn, "retry_workflow", max_retries=2)
        wf.add_step("fail_step", step_always_fails)
        wf.execute()

        # Retry once
        result = wf.retry()
        self.assertEqual(result["status"], "failed")

        # Check retry count
        exe = self.conn.execute(
            "SELECT retry_count FROM workflow_execution WHERE id = ?",
            (wf.execution_id,),
        ).fetchone()
        self.assertEqual(exe["retry_count"], 1)

    def test_max_retries_exceeded(self):
        def step_fail(conn, outputs):
            raise ValueError("fail")

        wf = DurableWorkflow(self.conn, "max_retry", max_retries=1)
        wf.add_step("fail", step_fail)
        wf.execute()

        wf.retry()  # retry_count = 1
        result = wf.retry()  # exceeds max_retries = 1
        self.assertEqual(result["status"], "error")
        self.assertIn("max retries", result["reason"])

    def test_workflow_status(self):
        def step_ok(conn, outputs):
            return {"done": True}

        wf = DurableWorkflow(self.conn, "status_test")
        wf.add_step("s1", step_ok)
        wf.execute()

        status = get_workflow_status(self.conn, wf.execution_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["execution"]["status"], "completed")
        self.assertEqual(len(status["steps"]), 1)
        self.assertEqual(status["steps"][0]["status"], "completed")

    def test_stale_workflows_empty(self):
        stale = get_stale_workflows(self.conn)
        self.assertEqual(stale, [])

    def test_chaining(self):
        wf = DurableWorkflow(self.conn, "chain")
        result = wf.add_step("a", lambda c, o: {"a": 1})
        self.assertIs(result, wf)  # Returns self for chaining


class TestNoExecution(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_resume_without_execute(self):
        wf = DurableWorkflow(self.conn, "no_exec")
        result = wf.resume()
        self.assertEqual(result["status"], "error")

    def test_retry_without_execute(self):
        wf = DurableWorkflow(self.conn, "no_exec")
        result = wf.retry()
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
