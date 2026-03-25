"""LangGraph prescription executor — autonomous code change agent.

Reads queued prescriptions from prescription_execution_log, plans changes
via LLM, applies them, verifies the audit score didn't drop, and commits
or rolls back.  Runs on the daily scheduler after the intelligence loop.

Safety:
- File whitelist: only modify files listed in the work order's target_file
  and the finding's files[] list.
- Score guard: rollback if post_audit_score < pre_audit_score - 2.0.
- Syntax validation on every Python file write (ast.parse).
- Max 3 prescriptions per execution cycle.
- Each change is a separate git commit; rollback via git checkout.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
from typing import TypedDict

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Maximum prescriptions to process per scheduler cycle
_MAX_PER_CYCLE = 3

# Score drop tolerance — rollback if audit score drops by more than this
_SCORE_TOLERANCE = 2.0


# ─── Agent State ────────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    work_order_id: int
    instruction: str
    target_files: list[str]
    allowed_files: list[str]
    plan: str
    changes: list[dict]       # [{file, original, modified, description}]
    pre_audit_score: float
    post_audit_score: float
    status: str               # planning | applied | verified | committed | rolled_back | error
    error: str
    platform_actions: list[dict]


# ─── File Tools (sandboxed) ─────────────────────────────────────

def _resolve_path(rel_path: str) -> str:
    """Resolve a project-relative path to absolute, within project root."""
    abs_path = os.path.normpath(os.path.join(_PROJECT_ROOT, rel_path))
    if not abs_path.startswith(_PROJECT_ROOT):
        raise PermissionError(f"Path escapes project root: {rel_path}")
    return abs_path


def _read_file(path: str) -> str | None:
    """Read a source file. Only allowed within project root."""
    try:
        abs_path = _resolve_path(path)
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (PermissionError, FileNotFoundError, OSError) as e:
        logger.debug("Agent read_file failed for %s: %s", path, e)
        return None


def _write_file(path: str, content: str) -> bool:
    """Write to a file. Validates syntax for Python files."""
    try:
        abs_path = _resolve_path(path)
        # Syntax validation for Python
        if abs_path.endswith(".py"):
            ast.parse(content)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except SyntaxError as e:
        logger.warning("Agent syntax check failed for %s: %s", path, e)
        return False
    except (PermissionError, OSError) as e:
        logger.warning("Agent write_file failed for %s: %s", path, e)
        return False


def _git_commit(message: str) -> bool:
    """Commit staged changes."""
    try:
        subprocess.run(
            ["git", "add", "-A"], cwd=_PROJECT_ROOT,
            capture_output=True, timeout=30,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message], cwd=_PROJECT_ROOT,
            capture_output=True, timeout=30,
        )
        return result.returncode == 0
    except Exception as e:
        logger.debug("git commit failed: %s", e)
        return False


def _git_rollback(files: list[str]) -> bool:
    """Discard changes to specific files."""
    try:
        abs_files = [_resolve_path(f) for f in files]
        subprocess.run(
            ["git", "checkout", "--"] + abs_files, cwd=_PROJECT_ROOT,
            capture_output=True, timeout=30,
        )
        return True
    except Exception as e:
        logger.debug("git rollback failed: %s", e)
        return False


def _run_audit(conn) -> float:
    """Run product audit and return overall score."""
    try:
        from ..intelligence import run_product_audit
        result = run_product_audit(conn)
        return result.get("overall", {}).get("score", 0.0)
    except Exception as e:
        logger.debug("Agent audit failed: %s", e)
        return 0.0


# ─── Graph Nodes ────────────────────────────────────────────────

def _plan_change(state: AgentState, conn=None) -> AgentState:
    """Read target files and plan the change using LLM."""
    from .ollama_client import generate

    # Read each target file
    file_contents = {}
    for f in state.get("target_files", []):
        content = _read_file(f)
        if content:
            # Truncate very large files to keep prompt manageable
            file_contents[f] = content[:8000]

    if not file_contents:
        state["status"] = "error"
        state["error"] = "No target files readable"
        return state

    plan_prompt = (
        f"You are a code modification agent. Your task:\n"
        f"{state['instruction']}\n\n"
        f"Files available:\n"
    )
    for path, content in file_contents.items():
        plan_prompt += f"\n--- {path} ---\n{content}\n"

    plan_prompt += (
        "\n\nRespond with JSON only:\n"
        '{"changes": [{"file": "path", "search": "exact text to find", '
        '"replace": "replacement text", "description": "what this does"}]}\n'
        "Use EXACT strings from the file for the search field."
    )

    resp = generate(
        prompt=plan_prompt,
        system="You are a precise code modification agent. Return valid JSON only.",
        temperature=0.2,
        max_tokens=2048,
        use_cache=False,
        conn=conn,
        task_type="agent_plan",
    )

    if not resp.success:
        state["status"] = "error"
        state["error"] = f"LLM plan failed: {resp.error}"
        return state

    # Parse the plan
    try:
        text = resp.text.strip()
        # Extract JSON from markdown code blocks if present
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        plan_data = json.loads(text)
        state["changes"] = plan_data.get("changes", [])
        state["plan"] = text
        state["status"] = "planned"
    except (json.JSONDecodeError, KeyError) as e:
        state["status"] = "error"
        state["error"] = f"Failed to parse LLM plan: {e}"

    return state


def _apply_changes(state: AgentState) -> AgentState:
    """Apply the planned changes to files."""
    if state.get("status") != "planned" or not state.get("changes"):
        state["status"] = "error"
        state["error"] = "No valid plan to apply"
        return state

    allowed = set(state.get("allowed_files", []))
    applied = []

    for change in state["changes"]:
        file_path = change.get("file", "")
        search = change.get("search", "")
        replace = change.get("replace", "")

        if not file_path or not search:
            continue

        # Security: only modify allowed files
        if allowed and file_path not in allowed:
            logger.warning("Agent blocked from modifying %s (not in allowed list)", file_path)
            continue

        # Read current content
        content = _read_file(file_path)
        if content is None:
            continue

        # Save original for rollback
        change["original"] = content

        # Apply search/replace
        if search in content:
            new_content = content.replace(search, replace, 1)
            if _write_file(file_path, new_content):
                change["modified"] = new_content
                applied.append(change)
            else:
                # Syntax error — restore original
                _write_file(file_path, content)
        else:
            logger.debug("Agent: search text not found in %s", file_path)

    if applied:
        state["changes"] = applied
        state["status"] = "applied"
    else:
        state["status"] = "error"
        state["error"] = "No changes could be applied"

    return state


def _verify_changes(state: AgentState, conn=None) -> AgentState:
    """Run audit and compare score to pre-change baseline."""
    if state.get("status") != "applied":
        return state

    post_score = _run_audit(conn)
    state["post_audit_score"] = post_score
    pre_score = state.get("pre_audit_score", 0.0)

    if post_score < pre_score - _SCORE_TOLERANCE:
        state["status"] = "score_dropped"
        state["error"] = f"Score dropped: {pre_score:.1f} → {post_score:.1f}"
    else:
        state["status"] = "verified"

    return state


def _commit_changes(state: AgentState) -> AgentState:
    """Commit verified changes and detect platform impact."""
    if state.get("status") != "verified":
        return state

    instruction_short = (state.get("instruction") or "")[:80]
    _git_commit(f"auto: {instruction_short}")
    state["status"] = "committed"

    # Detect platform impact
    state["platform_actions"] = _detect_platform_impact(state)

    return state


def _rollback_changes(state: AgentState) -> AgentState:
    """Rollback all changes on failure."""
    modified_files = [c["file"] for c in state.get("changes", []) if "original" in c]

    # Restore original content
    for change in state.get("changes", []):
        if "original" in change:
            _write_file(change["file"], change["original"])

    if modified_files:
        _git_rollback(modified_files)

    state["status"] = "rolled_back"
    return state


# ─── Platform Impact Detection ──────────────────────────────────

def _detect_platform_impact(state: AgentState) -> list[dict]:
    """When web assets change, note which platforms need sync."""
    actions = []
    for change in state.get("changes", []):
        file_path = change.get("file", "")
        if any(file_path.startswith(p) for p in (
            "mandarin/web/static/", "mandarin/web/templates/",
        )):
            actions.append({
                "platform": "capacitor",
                "action": "cap_sync",
                "reason": f"Web asset changed: {file_path}",
            })
            actions.append({
                "platform": "tauri",
                "action": "rebuild",
                "reason": f"Web asset changed: {file_path}",
            })
            # UI changes need Flutter equivalent
            if file_path.endswith((".css", ".html")):
                actions.append({
                    "platform": "flutter",
                    "action": "create_sibling_work_order",
                    "reason": f"UI change needs Flutter equivalent: {file_path}",
                })
    return actions


def _create_platform_work_orders(conn, parent_wo_id: int, audit_cycle_id: int,
                                  finding_id: int, actions: list[dict]) -> None:
    """Create sibling work orders for platform-specific follow-up."""
    for action in actions:
        if action.get("action") != "create_sibling_work_order":
            continue
        try:
            conn.execute("""
                INSERT INTO pi_work_order
                (audit_cycle_id, finding_id, instruction, target_file,
                 constraint_dimension, slot, status, platform_status)
                VALUES (?, ?, ?, ?, 'platform', 'TERTIARY', 'pending', '{}')
            """, (
                audit_cycle_id, finding_id,
                f"[{action['platform'].upper()}] {action['reason']}",
                action.get("target_dir", "flutter_app/"),
            ))
        except Exception:
            logger.debug("Failed to create platform work order", exc_info=True)
    try:
        conn.commit()
    except Exception:
        pass


# ─── LangGraph Execution (or sequential fallback) ──────────────

def _run_graph(state: AgentState, conn=None) -> AgentState:
    """Execute the agent graph. Uses LangGraph if available, else sequential."""
    try:
        from langgraph.graph import StateGraph, END

        graph = StateGraph(AgentState)
        graph.add_node("plan", lambda s: _plan_change(s, conn))
        graph.add_node("apply", _apply_changes)
        graph.add_node("verify", lambda s: _verify_changes(s, conn))
        graph.add_node("commit", _commit_changes)
        graph.add_node("rollback", _rollback_changes)

        graph.set_entry_point("plan")
        graph.add_edge("plan", "apply")
        graph.add_edge("apply", "verify")
        graph.add_conditional_edges(
            "verify",
            lambda s: "commit" if s.get("status") == "verified" else "rollback",
            {"commit": "commit", "rollback": "rollback"},
        )
        graph.add_edge("commit", END)
        graph.add_edge("rollback", END)

        compiled = graph.compile()
        return compiled.invoke(state)

    except ImportError:
        # Sequential fallback when LangGraph not installed
        logger.debug("LangGraph not installed, using sequential fallback")
        return _run_sequential(state, conn)


def _run_sequential(state: AgentState, conn=None) -> AgentState:
    """Sequential fallback for when LangGraph is not installed."""
    state = _plan_change(state, conn)
    if state.get("status") == "error":
        return state

    state = _apply_changes(state)
    if state.get("status") == "error":
        return state

    state = _verify_changes(state, conn)
    if state.get("status") in ("score_dropped", "error"):
        state = _rollback_changes(state)
        return state

    state = _commit_changes(state)
    return state


# ─── Entry Point ────────────────────────────────────────────────

def execute_queued_prescriptions(conn) -> list[dict]:
    """Process queued prescriptions through the LangGraph agent.

    Called by _run_intelligence_loop() in quality_scheduler.py after
    the standard auto-execute pass.
    """
    results = []

    # Get queued prescriptions
    try:
        rows = conn.execute("""
            SELECT pel.id as log_id, pel.work_order_id, pel.action_type,
                   pel.result_data,
                   wo.instruction, wo.target_file, wo.finding_id,
                   wo.audit_cycle_id
            FROM prescription_execution_log pel
            JOIN pi_work_order wo ON pel.work_order_id = wo.id
            WHERE pel.status = 'queued_for_agent'
            ORDER BY pel.created_at ASC
            LIMIT ?
        """, (_MAX_PER_CYCLE,)).fetchall()
    except Exception:
        logger.debug("Failed to query queued prescriptions", exc_info=True)
        return results

    if not rows:
        return results

    logger.info("LangGraph agent: processing %d queued prescriptions", len(rows))

    # Get baseline audit score once
    pre_score = _run_audit(conn)

    for row in rows:
        log_id = row["log_id"]
        wo_id = row["work_order_id"]

        # Parse target files from result_data
        try:
            data = json.loads(row["result_data"] or "{}")
        except json.JSONDecodeError:
            data = {}

        target_file = row["target_file"] or data.get("target_file", "")
        target_files = [target_file] if target_file else []

        # Also get files from the finding
        try:
            finding = conn.execute(
                "SELECT files FROM pi_finding WHERE id = ?",
                (row["finding_id"],),
            ).fetchone()
            if finding and finding["files"]:
                extra_files = json.loads(finding["files"])
                target_files.extend(f for f in extra_files if f not in target_files)
        except Exception:
            pass

        if not target_files:
            _mark_log(conn, log_id, "error", error="No target files")
            results.append({"work_order_id": wo_id, "status": "error", "error": "no target files"})
            continue

        # Mark as in-progress
        _mark_log(conn, log_id, "in_progress")

        # Build initial state
        state: AgentState = {
            "work_order_id": wo_id,
            "instruction": row["instruction"] or "",
            "target_files": target_files,
            "allowed_files": target_files,
            "plan": "",
            "changes": [],
            "pre_audit_score": pre_score,
            "post_audit_score": 0.0,
            "status": "planning",
            "error": "",
            "platform_actions": [],
        }

        # Execute the graph
        try:
            result_state = _run_graph(state, conn)
        except Exception as e:
            logger.debug("LangGraph execution failed for WO #%d: %s", wo_id, e)
            result_state = {"status": "error", "error": str(e)}

        final_status = result_state.get("status", "error")

        # Update log
        _mark_log(
            conn, log_id, final_status,
            pre_score=pre_score,
            post_score=result_state.get("post_audit_score"),
            error=result_state.get("error"),
        )

        # Update work order status
        if final_status == "committed":
            try:
                from ..intelligence.prescription import mark_work_order_implemented
                mark_work_order_implemented(
                    conn, wo_id,
                    notes=f"Auto-applied by LangGraph agent",
                )
            except Exception:
                pass

            # Update platform_status on work order
            platform_status = {}
            platform_status["web"] = "done"
            for pa in result_state.get("platform_actions", []):
                platform_status[pa["platform"]] = pa["action"]
            try:
                conn.execute(
                    "UPDATE pi_work_order SET platform_status = ? WHERE id = ?",
                    (json.dumps(platform_status), wo_id),
                )
                conn.commit()
            except Exception:
                pass

            # Create sibling work orders for platform follow-up
            _create_platform_work_orders(
                conn, wo_id,
                row.get("audit_cycle_id", 0),
                row.get("finding_id", 0),
                result_state.get("platform_actions", []),
            )

        results.append({
            "work_order_id": wo_id,
            "status": final_status,
            "pre_score": pre_score,
            "post_score": result_state.get("post_audit_score"),
        })

        logger.info(
            "LangGraph agent: WO #%d → %s (score: %.1f → %.1f)",
            wo_id, final_status, pre_score,
            result_state.get("post_audit_score", 0),
        )

    return results


def _mark_log(conn, log_id: int, status: str, *,
              pre_score: float = None, post_score: float = None,
              error: str = None) -> None:
    """Update prescription_execution_log status."""
    try:
        conn.execute("""
            UPDATE prescription_execution_log
            SET status = ?,
                pre_audit_score = COALESCE(?, pre_audit_score),
                post_audit_score = COALESCE(?, post_audit_score),
                result_data = COALESCE(?, result_data),
                completed_at = CASE WHEN ? IN ('committed', 'rolled_back', 'error')
                               THEN datetime('now') ELSE completed_at END
            WHERE id = ?
        """, (status, pre_score, post_score,
              json.dumps({"error": error}) if error else None,
              status, log_id))
        conn.commit()
    except Exception:
        logger.debug("Failed to update log %d", log_id, exc_info=True)
