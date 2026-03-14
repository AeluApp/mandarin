"""RAG layer and GenAI hardening analyzers for the audit cycle (Doc 21).

Wires analyze_rag_coverage() and analyze_generation_failures() into
the product intelligence system.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def analyze_rag_coverage_findings(conn: sqlite3.Connection) -> list[dict]:
    """RAG knowledge base coverage gaps."""
    try:
        from ..ai.rag_layer import analyze_rag_coverage
        return analyze_rag_coverage(conn)
    except Exception as e:
        logger.warning("rag_coverage analyzer failed: %s", e)
        return []


def analyze_generation_failure_findings(conn: sqlite3.Connection) -> list[dict]:
    """G6: JSON generation failure rate monitoring."""
    try:
        from ..ai.rag_layer import analyze_generation_failures
        return analyze_generation_failures(conn)
    except Exception as e:
        logger.warning("generation_failures analyzer failed: %s", e)
        return []


ANALYZERS = [analyze_rag_coverage_findings, analyze_generation_failure_findings]
