"""Tests for LangGraph prescription executor (mandarin/ai/llm_agent.py).

Verifies AgentState shape, file sandboxing (_resolve_path), graph construction,
sequential fallback, and graceful ImportError handling for langgraph.
"""

import os
import unittest
from unittest.mock import patch, MagicMock


from tests.shared_db import make_test_db as _make_db


class TestAgentStateShape(unittest.TestCase):
    """AgentState TypedDict has all required keys."""

    def test_agent_state_has_required_keys(self):
        from mandarin.ai.llm_agent import AgentState
        # TypedDict annotations define the expected keys
        annotations = AgentState.__annotations__
        expected_keys = {
            "work_order_id", "instruction", "target_files", "allowed_files",
            "plan", "changes", "pre_audit_score", "post_audit_score",
            "status", "error", "platform_actions",
        }
        self.assertEqual(set(annotations.keys()), expected_keys)

    def test_agent_state_is_total_false(self):
        """AgentState uses total=False, so all keys are optional."""
        from mandarin.ai.llm_agent import AgentState
        # total=False means __required_keys__ is empty
        required = getattr(AgentState, "__required_keys__", set())
        self.assertEqual(len(required), 0)


class TestResolvePathSandbox(unittest.TestCase):
    """_resolve_path() rejects paths outside the project root."""

    def test_normal_path_resolves(self):
        from mandarin.ai.llm_agent import _resolve_path, _PROJECT_ROOT
        result = _resolve_path("mandarin/ai/memory.py")
        expected = os.path.join(_PROJECT_ROOT, "mandarin", "ai", "memory.py")
        self.assertEqual(result, expected)

    def test_path_traversal_rejected(self):
        """Paths that escape project root via .. are rejected."""
        from mandarin.ai.llm_agent import _resolve_path
        with self.assertRaises(PermissionError):
            _resolve_path("../../etc/passwd")

    def test_absolute_path_outside_root_rejected(self):
        """Absolute paths outside project root are rejected after normpath."""
        from mandarin.ai.llm_agent import _resolve_path
        # normpath of joining /tmp with project root will likely escape
        with self.assertRaises(PermissionError):
            _resolve_path("../../../tmp/evil")

    def test_path_within_root_accepted(self):
        from mandarin.ai.llm_agent import _resolve_path, _PROJECT_ROOT
        result = _resolve_path("tests/test_llm_agent.py")
        self.assertTrue(result.startswith(_PROJECT_ROOT))


class TestReadFileValidation(unittest.TestCase):
    """_read_file() enforces project-root sandbox."""

    def test_read_file_outside_root_returns_none(self):
        from mandarin.ai.llm_agent import _read_file
        result = _read_file("../../../etc/passwd")
        self.assertIsNone(result)

    def test_read_file_nonexistent_returns_none(self):
        from mandarin.ai.llm_agent import _read_file
        result = _read_file("nonexistent_file_xyz.py")
        self.assertIsNone(result)


class TestWriteFileSyntaxValidation(unittest.TestCase):
    """_write_file() validates Python syntax before writing."""

    def test_write_invalid_python_returns_false(self):
        """Writing syntactically invalid Python should fail."""
        from mandarin.ai.llm_agent import _write_file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            tmppath = f.name

        try:
            # Patch _resolve_path to return our temp file
            with patch("mandarin.ai.llm_agent._resolve_path", return_value=tmppath):
                result = _write_file("dummy.py", "def broken(:\n    pass")
            self.assertFalse(result)
        finally:
            os.unlink(tmppath)


class TestGraphConstruction(unittest.TestCase):
    """build_executor_graph / _run_graph constructs a compilable graph."""

    @patch("mandarin.ai.llm_agent._run_audit", return_value=80.0)
    @patch("mandarin.ai.llm_agent._plan_change")
    @patch("mandarin.ai.llm_agent._apply_changes")
    @patch("mandarin.ai.llm_agent._verify_changes")
    @patch("mandarin.ai.llm_agent._commit_changes")
    def test_run_graph_with_langgraph(self, mock_commit, mock_verify,
                                       mock_apply, mock_plan, mock_audit):
        """When langgraph is installed, _run_graph uses StateGraph."""
        try:
            import langgraph  # noqa: F401
        except ImportError:
            self.skipTest("langgraph not installed")

        from mandarin.ai.llm_agent import _run_graph, AgentState

        # Set up chain: plan -> apply -> verify -> commit
        def plan_side_effect(state, conn=None):
            state["status"] = "planned"
            state["changes"] = [{"file": "f.py", "search": "a", "replace": "b"}]
            return state

        def apply_side_effect(state):
            state["status"] = "applied"
            return state

        def verify_side_effect(state, conn=None):
            state["status"] = "verified"
            state["post_audit_score"] = 82.0
            return state

        def commit_side_effect(state):
            state["status"] = "committed"
            state["platform_actions"] = []
            return state

        mock_plan.side_effect = plan_side_effect
        mock_apply.side_effect = apply_side_effect
        mock_verify.side_effect = verify_side_effect
        mock_commit.side_effect = commit_side_effect

        initial_state: AgentState = {
            "work_order_id": 1,
            "instruction": "test",
            "target_files": ["mandarin/ai/memory.py"],
            "allowed_files": ["mandarin/ai/memory.py"],
            "plan": "",
            "changes": [],
            "pre_audit_score": 80.0,
            "post_audit_score": 0.0,
            "status": "planning",
            "error": "",
            "platform_actions": [],
        }

        conn = _make_db()
        result = _run_graph(initial_state, conn)
        self.assertEqual(result["status"], "committed")


class TestSequentialFallback(unittest.TestCase):
    """When langgraph is not installed, _run_graph falls back to sequential."""

    @patch("mandarin.ai.llm_agent._commit_changes")
    @patch("mandarin.ai.llm_agent._verify_changes")
    @patch("mandarin.ai.llm_agent._apply_changes")
    @patch("mandarin.ai.llm_agent._plan_change")
    def test_sequential_happy_path(self, mock_plan, mock_apply,
                                    mock_verify, mock_commit):
        """Sequential fallback: plan -> apply -> verify -> commit."""
        from mandarin.ai.llm_agent import _run_sequential

        def plan_fn(state, conn=None):
            state["status"] = "planned"
            state["changes"] = [{"file": "f.py"}]
            return state

        def apply_fn(state):
            state["status"] = "applied"
            return state

        def verify_fn(state, conn=None):
            state["status"] = "verified"
            state["post_audit_score"] = 85.0
            return state

        def commit_fn(state):
            state["status"] = "committed"
            state["platform_actions"] = []
            return state

        mock_plan.side_effect = plan_fn
        mock_apply.side_effect = apply_fn
        mock_verify.side_effect = verify_fn
        mock_commit.side_effect = commit_fn

        state = {
            "work_order_id": 1,
            "instruction": "fix bug",
            "target_files": ["mandarin/runner.py"],
            "allowed_files": ["mandarin/runner.py"],
            "plan": "",
            "changes": [],
            "pre_audit_score": 80.0,
            "post_audit_score": 0.0,
            "status": "planning",
            "error": "",
            "platform_actions": [],
        }

        result = _run_sequential(state, conn=None)
        self.assertEqual(result["status"], "committed")

    @patch("mandarin.ai.llm_agent._rollback_changes")
    @patch("mandarin.ai.llm_agent._verify_changes")
    @patch("mandarin.ai.llm_agent._apply_changes")
    @patch("mandarin.ai.llm_agent._plan_change")
    def test_sequential_rollback_on_score_drop(self, mock_plan, mock_apply,
                                                mock_verify, mock_rollback):
        """Sequential fallback rolls back when verify detects score drop."""
        from mandarin.ai.llm_agent import _run_sequential

        mock_plan.side_effect = lambda s, conn=None: dict(s, status="planned", changes=[{"file": "f"}])
        mock_apply.side_effect = lambda s: dict(s, status="applied")
        mock_verify.side_effect = lambda s, conn=None: dict(s, status="score_dropped")
        mock_rollback.side_effect = lambda s: dict(s, status="rolled_back")

        state = {
            "work_order_id": 1, "instruction": "x",
            "target_files": ["f.py"], "allowed_files": ["f.py"],
            "plan": "", "changes": [],
            "pre_audit_score": 80.0, "post_audit_score": 0.0,
            "status": "planning", "error": "", "platform_actions": [],
        }

        result = _run_sequential(state)
        self.assertEqual(result["status"], "rolled_back")

    @patch("mandarin.ai.llm_agent._plan_change")
    def test_sequential_plan_error_short_circuits(self, mock_plan):
        """If planning fails, sequential fallback returns early."""
        from mandarin.ai.llm_agent import _run_sequential

        mock_plan.side_effect = lambda s, conn=None: dict(s, status="error", error="No LLM")

        state = {
            "work_order_id": 1, "instruction": "x",
            "target_files": ["f.py"], "allowed_files": ["f.py"],
            "plan": "", "changes": [],
            "pre_audit_score": 0.0, "post_audit_score": 0.0,
            "status": "planning", "error": "", "platform_actions": [],
        }

        result = _run_sequential(state)
        self.assertEqual(result["status"], "error")


class TestLangGraphImportFallback(unittest.TestCase):
    """When langgraph is not installed, _run_graph uses sequential fallback."""

    @patch("mandarin.ai.llm_agent._run_sequential")
    def test_import_error_falls_back(self, mock_sequential):
        """_run_graph catches ImportError and calls _run_sequential."""
        mock_sequential.return_value = {"status": "committed"}

        # Hide langgraph so the import inside _run_graph fails
        import sys
        saved = sys.modules.get("langgraph")
        saved_graph = sys.modules.get("langgraph.graph")
        sys.modules["langgraph"] = None
        sys.modules["langgraph.graph"] = None
        try:
            from mandarin.ai.llm_agent import _run_graph
            state = {"status": "planning"}
            result = _run_graph(state, conn=None)
            mock_sequential.assert_called_once_with(state, None)
            self.assertEqual(result["status"], "committed")
        finally:
            # Restore
            if saved is None:
                sys.modules.pop("langgraph", None)
            else:
                sys.modules["langgraph"] = saved
            if saved_graph is None:
                sys.modules.pop("langgraph.graph", None)
            else:
                sys.modules["langgraph.graph"] = saved_graph


class TestPlatformImpactDetection(unittest.TestCase):
    """_detect_platform_impact flags web asset changes."""

    def test_web_asset_triggers_cap_sync(self):
        from mandarin.ai.llm_agent import _detect_platform_impact
        state = {
            "changes": [
                {"file": "mandarin/web/static/app.js"},
            ]
        }
        actions = _detect_platform_impact(state)
        platforms = [a["platform"] for a in actions]
        self.assertIn("capacitor", platforms)
        self.assertIn("tauri", platforms)

    def test_css_triggers_flutter_sibling(self):
        from mandarin.ai.llm_agent import _detect_platform_impact
        state = {
            "changes": [
                {"file": "mandarin/web/static/style.css"},
            ]
        }
        actions = _detect_platform_impact(state)
        flutter_actions = [a for a in actions if a["platform"] == "flutter"]
        self.assertGreater(len(flutter_actions), 0)
        self.assertEqual(flutter_actions[0]["action"], "create_sibling_work_order")

    def test_non_web_file_no_impact(self):
        from mandarin.ai.llm_agent import _detect_platform_impact
        state = {"changes": [{"file": "mandarin/ai/memory.py"}]}
        actions = _detect_platform_impact(state)
        self.assertEqual(len(actions), 0)

    def test_empty_changes_no_impact(self):
        from mandarin.ai.llm_agent import _detect_platform_impact
        state = {"changes": []}
        actions = _detect_platform_impact(state)
        self.assertEqual(len(actions), 0)


class TestModuleConstants(unittest.TestCase):
    """Verify module-level constants are sensible."""

    def test_project_root_exists(self):
        from mandarin.ai.llm_agent import _PROJECT_ROOT
        self.assertTrue(os.path.isdir(_PROJECT_ROOT))

    def test_max_per_cycle(self):
        from mandarin.ai.llm_agent import _MAX_PER_CYCLE
        self.assertGreater(_MAX_PER_CYCLE, 0)
        self.assertLessEqual(_MAX_PER_CYCLE, 10)

    def test_score_tolerance(self):
        from mandarin.ai.llm_agent import _SCORE_TOLERANCE
        self.assertGreater(_SCORE_TOLERANCE, 0)


if __name__ == "__main__":
    unittest.main()
