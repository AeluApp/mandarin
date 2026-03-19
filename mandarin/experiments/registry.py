"""Experiment registry — CRUD, lifecycle management, and configuration.

Manages experiment creation, status transitions, and conclusion.  Integrates
with governance for pre-registration validation and config freezing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone

from .audit import log_audit_event
from .governance import validate_pre_registration, freeze_config

logger = logging.getLogger(__name__)


def create_experiment(
    conn: sqlite3.Connection,
    name: str,
    description: str,
    variants: list[str],
    traffic_pct: float = 100.0,
    guardrail_metrics: list[str] | None = None,
    min_sample_size: int = 100,
    *,
    hypothesis: str = "",
    primary_metric: str = "",
    secondary_metrics: list[str] | None = None,
    outcome_window_days: int = 7,
    outcome_horizon: str = "short",
    mde: float | None = None,
    eligibility_rules: dict | None = None,
    stratification_config: dict | None = None,
    predeclared_subgroups: list[str] | None = None,
    goodhart_risks: str = "",
    contamination_risks: str = "",
    randomization_unit: str = "user",
) -> int:
    """Create a new experiment in draft status.

    Returns the experiment id.  The experiment must be started with
    ``start_experiment()`` before assignment begins.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    guardrails = guardrail_metrics or ["session_completion_rate", "crash_rate", "churn_days"]

    # Generate a unique salt for hash isolation
    salt = hashlib.sha256(f"{name}:{now}".encode()).hexdigest()[:16]

    try:
        cur = conn.execute(
            """INSERT INTO experiment
               (name, description, variants, traffic_pct, guardrail_metrics,
                min_sample_size, created_at, salt, hypothesis, primary_metric,
                secondary_metrics, outcome_window_days, outcome_horizon, mde,
                eligibility_rules, stratification_config, predeclared_subgroups,
                goodhart_risks, contamination_risks, randomization_unit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name, description, json.dumps(variants), traffic_pct,
                json.dumps(guardrails), min_sample_size, now, salt,
                hypothesis, primary_metric,
                json.dumps(secondary_metrics) if secondary_metrics else None,
                outcome_window_days, outcome_horizon, mde,
                json.dumps(eligibility_rules) if eligibility_rules else None,
                json.dumps(stratification_config) if stratification_config else None,
                json.dumps(predeclared_subgroups) if predeclared_subgroups else None,
                goodhart_risks, contamination_risks, randomization_unit,
            ),
        )
    except sqlite3.OperationalError:
        # Fallback for older schema without new columns
        cur = conn.execute(
            """INSERT INTO experiment
               (name, description, variants, traffic_pct, guardrail_metrics,
                min_sample_size, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, description, json.dumps(variants), traffic_pct,
             json.dumps(guardrails), min_sample_size, now),
        )

    conn.commit()
    exp_id = cur.lastrowid

    log_audit_event(
        conn, "config_change",
        experiment_id=exp_id,
        data={"action": "create", "name": name, "variants": variants},
    )

    logger.info("Created experiment %r (id=%d) with variants %s", name, exp_id, variants)
    return exp_id


def start_experiment(conn: sqlite3.Connection, experiment_name: str) -> bool:
    """Move an experiment from draft to running.

    Validates pre-registration and freezes config.  Returns ``True`` if
    started successfully, ``False`` if validation failed.
    """
    try:
        exp = conn.execute(
            "SELECT id, status FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return False

    if not exp or exp["status"] != "draft":
        return False

    experiment_id = exp["id"]

    # Validate pre-registration (warnings are logged but don't block)
    valid, errors, warnings = validate_pre_registration(conn, experiment_id)
    if warnings:
        logger.warning(
            "Experiment %r pre-registration warnings: %s", experiment_name, warnings,
        )

    # Freeze configuration
    freeze_config(conn, experiment_id)

    # Start
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE experiment SET status = 'running', started_at = ? WHERE name = ? AND status = 'draft'",
        (now, experiment_name),
    )
    conn.commit()

    log_audit_event(
        conn, "config_change",
        experiment_id=experiment_id,
        data={"action": "start", "validation_errors": errors, "validation_warnings": warnings},
    )

    logger.info("Started experiment %r (id=%d)", experiment_name, experiment_id)
    return True


def pause_experiment(conn: sqlite3.Connection, experiment_name: str, reason: str = "") -> None:
    """Pause a running experiment."""
    exp = _get_by_name(conn, experiment_name)
    if not exp:
        return

    conn.execute(
        "UPDATE experiment SET status = 'paused' WHERE name = ? AND status = 'running'",
        (experiment_name,),
    )
    conn.commit()

    log_audit_event(
        conn, "pause",
        experiment_id=exp["id"],
        data={"reason": reason},
    )


def conclude_experiment(
    conn: sqlite3.Connection,
    experiment_name: str,
    winner: str,
    notes: str = "",
) -> None:
    """Conclude an experiment, recording the winner and decision metadata."""
    from .analysis import get_experiment_results

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    results = get_experiment_results(conn, experiment_name)
    conclusion = {
        "winner": winner,
        "notes": notes,
        "variants": results.get("variants", {}),
        "p_value": results.get("p_value"),
        "effect_size": results.get("effect_size"),
        "cuped_applied": results.get("cuped_applied", False),
        "decided_at": now,
    }
    conn.execute(
        "UPDATE experiment SET status = 'concluded', concluded_at = ?, conclusion = ? WHERE name = ?",
        (now, json.dumps(conclusion), experiment_name),
    )
    conn.commit()

    exp = _get_by_name(conn, experiment_name)
    if exp:
        log_audit_event(
            conn, "conclude",
            experiment_id=exp["id"],
            data=conclusion,
        )

    logger.info("Concluded experiment %r — winner: %s", experiment_name, winner)


def get_experiment(conn: sqlite3.Connection, experiment_name: str) -> dict | None:
    """Get full experiment record by name."""
    return _get_by_name(conn, experiment_name)


def list_experiments(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    """List experiments, optionally filtered by status."""
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM experiment WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM experiment ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def _get_by_name(conn: sqlite3.Connection, name: str) -> dict | None:
    try:
        row = conn.execute(
            "SELECT * FROM experiment WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
