"""Product Intelligence — CI failure ingestion.

Imports CI findings from the JSON file produced by scripts/ci_failure_ingest.py
into the pi_finding table. Called by quality_scheduler on each daily run.

Also provides classify_ci_failure() for determining severity and decision class
from raw error text.

Exports:
    import_ci_findings(conn, json_path: str) -> int
    classify_ci_failure(error_text: str) -> dict
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from pathlib import Path

from ._base import _safe_query, _safe_query_all

logger = logging.getLogger(__name__)

# Default path for ci_findings.json relative to the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_JSON_PATH = str(_PROJECT_ROOT / "ci_findings.json")


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Patterns for classifying error text into failure types
_CLASSIFICATION_PATTERNS = [
    (re.compile(r"security|bandit|CVE-|vulnerability|SAST", re.IGNORECASE), "security"),
    (re.compile(r"deploy|fly\.io|flyctl|production", re.IGNORECASE), "deploy"),
    (re.compile(r"lint|ruff|flake8|E\d{3}|W\d{3}", re.IGNORECASE), "lint"),
    (re.compile(r"coverage.*fail|cov-fail-under", re.IGNORECASE), "coverage"),
    (re.compile(r"SyntaxError", re.IGNORECASE), "syntax"),
    (re.compile(r"ImportError|ModuleNotFoundError", re.IGNORECASE), "import"),
    (re.compile(r"AssertionError|FAILED\s+tests/", re.IGNORECASE), "test"),
    (re.compile(r"TypeError|ValueError|AttributeError", re.IGNORECASE), "runtime"),
    (re.compile(r"TimeoutError|timed?\s*out", re.IGNORECASE), "timeout"),
]

# Severity and decision class per failure category
_FAILURE_CLASSIFICATION = {
    "security": {"severity": "high", "decision_class": "informed_fix"},
    "deploy": {"severity": "critical", "decision_class": "informed_fix"},
    "lint": {"severity": "low", "decision_class": "auto_fix"},
    "coverage": {"severity": "low", "decision_class": "auto_fix"},
    "syntax": {"severity": "medium", "decision_class": "informed_fix"},
    "import": {"severity": "medium", "decision_class": "informed_fix"},
    "test": {"severity": "medium", "decision_class": "informed_fix"},
    "runtime": {"severity": "medium", "decision_class": "informed_fix"},
    "timeout": {"severity": "medium", "decision_class": "informed_fix"},
    "unknown": {"severity": "medium", "decision_class": "informed_fix"},
}


def classify_ci_failure(error_text: str) -> dict:
    """Determine severity, decision class, and failure category from error text.

    Args:
        error_text: raw error output or a descriptive string about the failure.

    Returns:
        {
            "severity": "low" | "medium" | "high" | "critical",
            "decision_class": "auto_fix" | "informed_fix",
            "failure_category": str,
        }
    """
    category = "unknown"
    for pattern, cat in _CLASSIFICATION_PATTERNS:
        if pattern.search(error_text):
            category = cat
            break

    classification = _FAILURE_CLASSIFICATION.get(category, _FAILURE_CLASSIFICATION["unknown"])
    return {
        "severity": classification["severity"],
        "decision_class": classification["decision_class"],
        "failure_category": category,
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_ci_findings(conn, json_path: str = None) -> int:
    """Read the CI findings JSON file and import new findings into pi_finding.

    Deduplicates against existing open findings with the same title in the
    ci_health dimension. Skips findings that already exist and are not resolved
    or rejected.

    After successful import, the JSON file is renamed with a .imported suffix
    to prevent re-processing.

    Args:
        conn: SQLite database connection.
        json_path: path to ci_findings.json. Defaults to project root.

    Returns:
        Number of new findings imported.
    """
    if json_path is None:
        json_path = _DEFAULT_JSON_PATH

    path = Path(json_path)
    if not path.exists():
        logger.debug("CI findings file not found at %s — nothing to import", json_path)
        return 0

    # Read and validate JSON
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("CI findings: failed to read %s: %s", json_path, exc)
        return 0

    findings = data.get("findings", [])
    if not findings:
        logger.debug("CI findings file contains no findings")
        _archive_file(path)
        return 0

    # Get the latest audit_id for linking
    audit_row = _safe_query(conn, "SELECT MAX(id) as max_id FROM product_audit")
    audit_id = audit_row["max_id"] if audit_row and audit_row["max_id"] else None

    # Load existing open ci_health findings for deduplication
    open_findings = _safe_query_all(conn, """
        SELECT id, title FROM pi_finding
        WHERE dimension = 'ci_health'
          AND status NOT IN ('resolved', 'rejected')
    """) or []
    open_titles = {f["title"] for f in open_findings}

    imported = 0
    for finding in findings:
        title = finding.get("title", "")
        if not title:
            continue

        # Dedup: skip if an open finding with same title exists
        if title in open_titles:
            logger.debug("CI findings: skipping duplicate '%s'", title[:80])
            continue

        severity = finding.get("severity", "medium")
        analysis = finding.get("analysis", "")
        recommendation = finding.get("recommendation", "")
        claude_prompt = finding.get("claude_prompt", "")
        files = finding.get("files", [])

        try:
            conn.execute("""
                INSERT INTO pi_finding
                    (audit_id, dimension, severity, title, analysis,
                     status, metric_name, last_seen_audit_id)
                VALUES (?, 'ci_health', ?, ?, ?, 'investigating', 'ci_health', ?)
            """, (
                audit_id,
                severity,
                title,
                _build_full_analysis(analysis, recommendation, claude_prompt, files),
                audit_id,
            ))
            imported += 1
            open_titles.add(title)  # prevent duplicates within same batch
        except (sqlite3.OperationalError, sqlite3.Error) as exc:
            logger.debug("CI findings: failed to insert '%s': %s", title[:80], exc)

    if imported > 0:
        try:
            conn.commit()
        except sqlite3.Error:
            pass
        logger.info("CI findings: imported %d new finding(s) from %s", imported, json_path)

    # Archive the file so it is not re-processed
    _archive_file(path)

    return imported


def _build_full_analysis(
    analysis: str, recommendation: str, claude_prompt: str, files: list
) -> str:
    """Combine analysis fields into a single text block for the pi_finding.analysis column."""
    parts = []
    if analysis:
        parts.append(analysis)
    if recommendation:
        parts.append(f"\nRecommendation: {recommendation}")
    if claude_prompt:
        parts.append(f"\nClaude prompt:\n{claude_prompt}")
    if files:
        parts.append(f"\nAffected files: {', '.join(files[:10])}")
    return "\n".join(parts)


def _archive_file(path: Path) -> None:
    """Rename the findings file to prevent re-processing."""
    try:
        archived = path.with_suffix(".json.imported")
        # If a previous .imported file exists, remove it first
        if archived.exists():
            archived.unlink()
        path.rename(archived)
        logger.debug("CI findings: archived %s -> %s", path, archived)
    except OSError as exc:
        logger.debug("CI findings: failed to archive %s: %s", path, exc)
