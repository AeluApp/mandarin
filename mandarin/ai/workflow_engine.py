"""Durable Workflow Engine (Doc 23 C-03).

Checkpoint + retry for multi-step operations:
- Content generation → validation → debate → review queue
- Research synthesis → scoring → application
Each step's output is checkpointed to DB; resume/retry from failure point.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class DurableWorkflow:
    """Execute multi-step workflows with checkpoint and retry.

    Each step is checkpointed to the workflow_step table after completion.
    On failure, resume() skips completed steps and continues from the
    failure point. retry() re-executes the failed step.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        workflow_type: str,
        workflow_data: Optional[dict] = None,
        max_retries: int = 3,
    ):
        self.conn = conn
        self.workflow_type = workflow_type
        self.workflow_data = workflow_data or {}
        self.max_retries = max_retries
        self._steps: list[dict] = []
        self._execution_id: Optional[int] = None

    def add_step(
        self,
        name: str,
        fn: Callable,
        rollback_fn: Optional[Callable] = None,
    ) -> "DurableWorkflow":
        """Add a step to the workflow. Returns self for chaining."""
        self._steps.append({
            "name": name,
            "fn": fn,
            "rollback_fn": rollback_fn,
            "order": len(self._steps),
        })
        return self

    def execute(self) -> dict:
        """Run all steps, checkpointing after each. Returns result dict."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Create execution record
        cursor = self.conn.execute("""
            INSERT INTO workflow_execution
            (workflow_type, workflow_data, status, max_retries, started_at)
            VALUES (?, ?, 'running', ?, ?)
        """, (
            self.workflow_type,
            json.dumps(self.workflow_data, ensure_ascii=False),
            self.max_retries,
            now,
        ))
        self._execution_id = cursor.lastrowid

        # Create step records
        for step in self._steps:
            self.conn.execute("""
                INSERT INTO workflow_step
                (execution_id, step_name, step_order, status)
                VALUES (?, ?, ?, 'pending')
            """, (self._execution_id, step["name"], step["order"]))
        self.conn.commit()

        return self._run_steps(start_from=0, prior_outputs={})

    def resume(self) -> dict:
        """Resume from last successful step. Requires prior execute()."""
        if self._execution_id is None:
            return {"status": "error", "reason": "no execution to resume"}

        # Load completed step outputs
        rows = self.conn.execute("""
            SELECT step_name, step_order, status, output_data
            FROM workflow_step
            WHERE execution_id = ?
            ORDER BY step_order
        """, (self._execution_id,)).fetchall()

        prior_outputs = {}
        start_from = 0
        for row in rows:
            if row["status"] == "completed" and row["output_data"]:
                prior_outputs[row["step_name"]] = json.loads(row["output_data"])
                start_from = row["step_order"] + 1
            elif row["status"] == "failed":
                start_from = row["step_order"]
                break

        # Update execution status
        self.conn.execute("""
            UPDATE workflow_execution SET status = 'running', current_step = ?
            WHERE id = ?
        """, (self._steps[start_from]["name"] if start_from < len(self._steps) else None,
              self._execution_id))
        self.conn.commit()

        return self._run_steps(start_from=start_from, prior_outputs=prior_outputs)

    def retry(self) -> dict:
        """Retry the failed step. Increments retry_count."""
        if self._execution_id is None:
            return {"status": "error", "reason": "no execution to retry"}

        row = self.conn.execute("""
            SELECT retry_count, max_retries FROM workflow_execution WHERE id = ?
        """, (self._execution_id,)).fetchone()
        if not row:
            return {"status": "error", "reason": "execution not found"}

        if row["retry_count"] >= row["max_retries"]:
            return {"status": "error", "reason": "max retries exceeded"}

        self.conn.execute("""
            UPDATE workflow_execution SET retry_count = retry_count + 1, status = 'retrying'
            WHERE id = ?
        """, (self._execution_id,))
        self.conn.commit()

        return self.resume()

    def _run_steps(self, start_from: int, prior_outputs: dict) -> dict:
        """Execute steps starting from start_from index."""
        outputs = dict(prior_outputs)

        for i in range(start_from, len(self._steps)):
            step = self._steps[i]
            step_name = step["name"]
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            # Mark step as running
            self.conn.execute("""
                UPDATE workflow_step SET status = 'running', started_at = ?
                WHERE execution_id = ? AND step_order = ?
            """, (now, self._execution_id, i))
            self.conn.execute("""
                UPDATE workflow_execution SET current_step = ? WHERE id = ?
            """, (step_name, self._execution_id))
            self.conn.commit()

            try:
                result = step["fn"](self.conn, outputs)
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                # Checkpoint success
                output_json = json.dumps(result, ensure_ascii=False, default=str) if result else None
                self.conn.execute("""
                    UPDATE workflow_step
                    SET status = 'completed', output_data = ?, completed_at = ?
                    WHERE execution_id = ? AND step_order = ?
                """, (output_json, now, self._execution_id, i))
                self.conn.commit()

                outputs[step_name] = result

            except Exception as e:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                error_msg = str(e)
                logger.warning("Workflow %s step '%s' failed: %s",
                               self.workflow_type, step_name, error_msg)

                # Checkpoint failure
                self.conn.execute("""
                    UPDATE workflow_step
                    SET status = 'failed', error_detail = ?, completed_at = ?
                    WHERE execution_id = ? AND step_order = ?
                """, (error_msg, now, self._execution_id, i))
                self.conn.execute("""
                    UPDATE workflow_execution
                    SET status = 'failed', error_detail = ?, current_step = ?
                    WHERE id = ?
                """, (error_msg, step_name, self._execution_id))
                self.conn.commit()

                return {
                    "status": "failed",
                    "execution_id": self._execution_id,
                    "failed_step": step_name,
                    "error": error_msg,
                    "completed_steps": list(outputs.keys()),
                }

        # All steps completed
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute("""
            UPDATE workflow_execution SET status = 'completed', completed_at = ?
            WHERE id = ?
        """, (now, self._execution_id))
        self.conn.commit()

        return {
            "status": "completed",
            "execution_id": self._execution_id,
            "outputs": outputs,
        }

    @property
    def execution_id(self) -> Optional[int]:
        return self._execution_id


def get_stale_workflows(conn: sqlite3.Connection, max_age_hours: int = 24) -> list[dict]:
    """Find workflows stuck in running/retrying state beyond max_age_hours."""
    try:
        rows = conn.execute("""
            SELECT id, workflow_type, current_step, status, started_at, error_detail
            FROM workflow_execution
            WHERE status IN ('running', 'retrying')
            AND started_at < datetime('now', ?)
            ORDER BY started_at
        """, (f"-{max_age_hours} hours",)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def get_workflow_status(conn: sqlite3.Connection, execution_id: int) -> Optional[dict]:
    """Get status of a workflow execution including all step details."""
    try:
        exe = conn.execute(
            "SELECT * FROM workflow_execution WHERE id = ?", (execution_id,)
        ).fetchone()
        if not exe:
            return None

        steps = conn.execute("""
            SELECT step_name, step_order, status, started_at, completed_at, error_detail
            FROM workflow_step WHERE execution_id = ?
            ORDER BY step_order
        """, (execution_id,)).fetchall()

        return {
            "execution": dict(exe),
            "steps": [dict(s) for s in steps],
        }
    except sqlite3.OperationalError:
        return None
