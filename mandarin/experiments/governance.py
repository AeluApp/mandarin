"""Governance — pre-registration enforcement, config validation, and freeze logic.

Ensures experiments cannot be silently modified after they start running.
The pre-registration is frozen at the moment the experiment transitions from
draft to running, and most fields become immutable after that point.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC

from .audit import log_audit_event

logger = logging.getLogger(__name__)

# Fields required for pre-registration
REQUIRED_FIELDS = {
    "hypothesis": "What do you expect to happen and why?",
    "primary_metric": "The single metric that determines success",
    "min_sample_size": "Per-arm sample size from power analysis",
    "outcome_window_days": "Days after exposure to measure the primary metric",
}

# Fields recommended (warning if missing, not blocking)
RECOMMENDED_FIELDS = {
    "mde": "Minimum detectable effect size",
    "goodhart_risks": "What could go right on the metric but wrong for learning?",
    "contamination_risks": "What cross-experiment contamination could occur?",
    "outcome_horizon": "short, medium, or delayed",
}

# Fields that become immutable after experiment start
FROZEN_FIELDS = {
    "hypothesis",
    "primary_metric",
    "variants",
    "eligibility_rules",
    "stratification_config",
    "predeclared_subgroups",
    "guardrail_metrics",
    "outcome_window_days",
    "randomization_unit",
}

# Fields that can only increase (not decrease) after start
MONOTONIC_FIELDS = {"min_sample_size"}


def validate_pre_registration(
    conn: sqlite3.Connection,
    experiment_id: int,
) -> tuple[bool, list[str], list[str]]:
    """Validate that an experiment has a sufficient pre-registration.

    Returns ``(valid, errors, warnings)`` where *errors* block launch and
    *warnings* are informational.
    """
    try:
        exp = conn.execute(
            "SELECT * FROM experiment WHERE id = ?",
            (experiment_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return False, ["experiment table not found"], []

    if not exp:
        return False, ["experiment not found"], []

    errors: list[str] = []
    warnings: list[str] = []

    # Required fields
    for field, desc in REQUIRED_FIELDS.items():
        val = exp[field] if field in exp.keys() else None
        if not val:
            errors.append(f"Missing required field '{field}': {desc}")

    # Recommended fields
    for field, desc in RECOMMENDED_FIELDS.items():
        val = exp[field] if field in exp.keys() else None
        if not val:
            warnings.append(f"Missing recommended field '{field}': {desc}")

    # Variants must have at least 2
    try:
        variants = json.loads(exp["variants"])
        if len(variants) < 2:
            errors.append("Experiment must have at least 2 variants")
    except (json.JSONDecodeError, TypeError):
        errors.append("Invalid variants JSON")

    # Min sample size must be reasonable
    min_sample = exp["min_sample_size"]
    if min_sample and min_sample < 10:
        warnings.append(f"min_sample_size={min_sample} is very small — results may be unreliable")

    valid = len(errors) == 0
    return valid, errors, warnings


def freeze_config(
    conn: sqlite3.Connection,
    experiment_id: int,
) -> dict:
    """Freeze the experiment configuration at launch time.

    Captures a snapshot of the pre-registration and stores it, along with a
    ``config_frozen_at`` timestamp.  After this point, frozen fields cannot be
    changed.

    Returns the frozen snapshot dict.
    """
    try:
        exp = conn.execute(
            "SELECT * FROM experiment WHERE id = ?",
            (experiment_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {}

    if not exp:
        return {}

    # Build pre-registration snapshot
    snapshot = {}
    for field in list(REQUIRED_FIELDS) + list(RECOMMENDED_FIELDS) + list(FROZEN_FIELDS):
        try:
            val = exp[field]
            # Try to parse JSON fields
            if isinstance(val, str) and val.startswith(("{", "[")):
                try:
                    val = json.loads(val)
                except json.JSONDecodeError:
                    pass
            snapshot[field] = val
        except (IndexError, KeyError):
            pass

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn.execute(
            "UPDATE experiment SET pre_registration = ?, config_frozen_at = ? WHERE id = ?",
            (json.dumps(snapshot), now, experiment_id),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass

    log_audit_event(
        conn,
        "config_change",
        experiment_id=experiment_id,
        data={"action": "freeze", "snapshot_keys": list(snapshot.keys())},
    )

    return snapshot


def check_config_change_allowed(
    conn: sqlite3.Connection,
    experiment_id: int,
    field: str,
    new_value,
) -> tuple[bool, str]:
    """Check whether changing *field* to *new_value* is allowed.

    Returns ``(allowed, reason)``.
    """
    try:
        exp = conn.execute(
            "SELECT * FROM experiment WHERE id = ?",
            (experiment_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return True, ""

    if not exp:
        return False, "experiment not found"

    # Draft experiments can be freely modified
    if exp["status"] == "draft":
        return True, ""

    # After start: check frozen fields
    if field in FROZEN_FIELDS:
        return False, f"Field '{field}' is frozen after experiment start"

    # Monotonic fields
    if field in MONOTONIC_FIELDS:
        try:
            current = exp[field]
            if current is not None and new_value < current:
                return False, f"Field '{field}' can only increase after start (current={current})"
        except (IndexError, KeyError, TypeError):
            pass

    return True, ""


def log_ramp_change(
    conn: sqlite3.Connection,
    experiment_id: int,
    old_pct: float,
    new_pct: float,
    reason: str = "",
) -> None:
    """Log a traffic percentage change."""
    log_audit_event(
        conn,
        "ramp_change",
        experiment_id=experiment_id,
        data={
            "old_pct": old_pct,
            "new_pct": new_pct,
            "reason": reason,
        },
    )
