"""Memory model health analyzers for the audit cycle (Doc 13).

Wires analyze_memory_model() into the product intelligence system.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def analyze_memory_model_findings(conn: sqlite3.Connection) -> list[dict]:
    """Memory model health — lapse rates, load violations, stability anomalies."""
    try:
        from ..ai.memory_model import analyze_memory_model
        return analyze_memory_model(conn)
    except Exception as e:
        logger.warning("memory_model analyzer failed: %s", e)
        return []


ANALYZERS = [analyze_memory_model_findings]
