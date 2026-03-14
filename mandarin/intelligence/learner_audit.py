"""Learner model health analyzers for the audit cycle (Doc 16).

Wires analyze_learner_model() into the product intelligence system.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def analyze_learner_model_findings(conn: sqlite3.Connection) -> list[dict]:
    """Learner model health — stale patterns, missing proficiency, untagged grammar."""
    try:
        from ..ai.learner_model import analyze_learner_model
        return analyze_learner_model(conn)
    except Exception as e:
        logger.warning("learner_model analyzer failed: %s", e)
        return []


ANALYZERS = [analyze_learner_model_findings]
