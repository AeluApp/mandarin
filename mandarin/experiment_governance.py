"""Experiment governance — approval queue for autonomous experiment actions.

All AI-proposed experiment actions (start, conclude, rollout) must pass through
this approval queue. Humans review; AI proposes.
"""
from __future__ import annotations

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def queue_for_approval(
    conn: sqlite3.Connection,
    action_type: str,
    experiment_name: str,
    proposal_data: dict,
    proposed_by: str = "daemon",
) -> int | None:
    """Insert an action into the experiment_approval_queue for human review.

    Returns the row id on success, None on failure.
    """
    try:
        cur = conn.execute(
            """INSERT INTO experiment_approval_queue
               (action_type, experiment_name, proposed_by, proposal_data, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (action_type, experiment_name, proposed_by, json.dumps(proposal_data)),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.OperationalError:
        logger.warning(
            "experiment_approval_queue table not found — skipping governance queue"
        )
        return None
