"""Guardrail metrics — safety checks that prevent harmful experiments.

If any guardrail metric degrades beyond the threshold, the experiment should
be auto-paused.  Guardrails check things like session completion rate, crash
rate, and churn days.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3

logger = logging.getLogger(__name__)

DEFAULT_GUARDRAILS = ["session_completion_rate", "crash_rate", "churn_days"]
GUARDRAIL_DEGRADATION_THRESHOLD = 0.05  # 5% relative degradation triggers alert


def check_guardrails(conn: sqlite3.Connection, experiment_name: str) -> dict:
    """Check guardrail metrics for an experiment.

    Returns ``{metric_name: {control_value, treatment_value, degraded: bool}}``.
    """
    try:
        exp = conn.execute(
            "SELECT id, variants, guardrail_metrics FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {}

    if not exp:
        return {}

    experiment_id = exp["id"]
    variant_names = json.loads(exp["variants"])
    guardrails_config = json.loads(exp["guardrail_metrics"] or "[]") or DEFAULT_GUARDRAILS

    if len(variant_names) < 2:
        return {}

    control_name = variant_names[0]
    treatment_name = variant_names[1]

    control_users = [
        r["user_id"] for r in conn.execute(
            "SELECT user_id FROM experiment_assignment WHERE experiment_id = ? AND variant = ?",
            (experiment_id, control_name),
        ).fetchall()
    ]
    treatment_users = [
        r["user_id"] for r in conn.execute(
            "SELECT user_id FROM experiment_assignment WHERE experiment_id = ? AND variant = ?",
            (experiment_id, treatment_name),
        ).fetchall()
    ]

    results = {}

    for metric in guardrails_config:
        control_val = _compute_guardrail_metric(conn, metric, control_users)
        treatment_val = _compute_guardrail_metric(conn, metric, treatment_users)

        # Determine degradation direction per metric
        if metric in ("crash_rate", "churn_days"):
            # Higher is worse
            degraded = (
                control_val > 0
                and treatment_val > control_val * (1 + GUARDRAIL_DEGRADATION_THRESHOLD)
            )
        else:
            # Higher is better (completion rate, etc.)
            degraded = (
                control_val > 0
                and treatment_val < control_val * (1 - GUARDRAIL_DEGRADATION_THRESHOLD)
            )

        results[metric] = {
            "control_value": round(control_val, 4),
            "treatment_value": round(treatment_val, 4),
            "degraded": degraded,
        }

    return results


def _compute_guardrail_metric(
    conn: sqlite3.Connection, metric: str, user_ids: list[int],
) -> float:
    """Compute a single guardrail metric for a set of users."""
    if not user_ids:
        return 0.0

    placeholders = ",".join("?" * len(user_ids))

    if metric == "session_completion_rate":
        row = conn.execute(
            f"""SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN session_outcome = 'completed' THEN 1 ELSE 0 END) as completed
                FROM session_log WHERE user_id IN ({placeholders})""",
            user_ids,
        ).fetchone()
        total = row["total"] or 0
        completed = row["completed"] or 0
        return completed / total if total > 0 else 0.0

    elif metric == "crash_rate":
        try:
            row = conn.execute(
                f"""SELECT COUNT(*) as cnt FROM error_log
                    WHERE session_id IN (
                        SELECT id FROM session_log WHERE user_id IN ({placeholders})
                    ) AND error_type LIKE '%crash%'""",
                user_ids,
            ).fetchone()
            crashes = row["cnt"] or 0
            session_row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM session_log WHERE user_id IN ({placeholders})",
                user_ids,
            ).fetchone()
            sessions = session_row["cnt"] or 0
            return crashes / sessions if sessions > 0 else 0.0
        except sqlite3.OperationalError:
            return 0.0

    elif metric == "churn_days":
        # FIX: The original implementation used GROUP BY + fetchone() which
        # only returned the first group's average.  This subquery correctly
        # computes per-user last-session date then averages across all users.
        try:
            row = conn.execute(
                f"""SELECT AVG(gap) as avg_gap FROM (
                        SELECT julianday('now') - julianday(MAX(started_at)) as gap
                        FROM session_log
                        WHERE user_id IN ({placeholders})
                        GROUP BY user_id
                    )""",
                user_ids,
            ).fetchone()
            return float(row["avg_gap"]) if row and row["avg_gap"] else 0.0
        except (sqlite3.OperationalError, TypeError):
            return 0.0

    return 0.0
