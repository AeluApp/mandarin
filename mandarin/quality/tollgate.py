"""Tollgate review enforcement — phase-gate checks for DMAIC cycles."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

_PHASE_ORDER = ["define", "measure", "analyze", "improve", "control"]


def record_tollgate_review(conn, dmaic_id, phase, decision, notes=""):
    """Record a tollgate review decision for a DMAIC phase.

    Args:
        dmaic_id: ID from pi_dmaic_log
        phase: 'define', 'measure', 'analyze', 'improve', or 'control'
        decision: 'go', 'conditional_go', or 'no_go'
        notes: Optional reviewer notes

    Returns:
        Review ID or None if failed.
    """
    if phase not in _PHASE_ORDER:
        logger.warning("Invalid tollgate phase: %s", phase)
        return None
    if decision not in ("go", "conditional_go", "no_go"):
        logger.warning("Invalid tollgate decision: %s", decision)
        return None

    try:
        cursor = conn.execute(
            "INSERT INTO pi_tollgate_review (dmaic_id, phase, decision, notes) "
            "VALUES (?, ?, ?, ?)",
            (dmaic_id, phase, decision, notes),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.warning("Failed to record tollgate review: %s", e)
        return None


def get_tollgate_status(conn, dmaic_id):
    """Return which phases have been reviewed for a DMAIC cycle.

    Returns:
        dict mapping phase name to latest decision, e.g.:
        {"define": "go", "measure": "conditional_go"}
    """
    try:
        rows = conn.execute(
            "SELECT phase, decision FROM pi_tollgate_review "
            "WHERE dmaic_id = ? ORDER BY reviewed_at",
            (dmaic_id,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    except sqlite3.Error:
        return {}


def enforce_phase_sequence(conn, dmaic_id, target_phase):
    """Check that all prerequisite phases have passed tollgate.

    Returns:
        (allowed: bool, reason: str)
    """
    if target_phase not in _PHASE_ORDER:
        return False, f"Invalid phase: {target_phase}"

    target_idx = _PHASE_ORDER.index(target_phase)
    if target_idx == 0:
        return True, "Define phase has no prerequisites"

    status = get_tollgate_status(conn, dmaic_id)
    for i in range(target_idx):
        prev_phase = _PHASE_ORDER[i]
        decision = status.get(prev_phase)
        if decision not in ("go", "conditional_go"):
            return False, f"Phase '{prev_phase}' must pass tollgate before '{target_phase}'"

    return True, "All prerequisites met"
