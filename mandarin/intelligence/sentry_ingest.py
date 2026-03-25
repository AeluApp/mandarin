"""Product Intelligence — Sentry error alert ingestion.

Fetches unresolved issues from Sentry's API and imports them as pi_finding
records with dimension='runtime_health'. Called by quality_scheduler on each
daily run alongside CI findings import.

Also provides classify_sentry_issue() for determining severity and
recommended fix patterns from Sentry error data.

Configuration:
    SENTRY_AUTH_TOKEN  — Bearer token for Sentry API
    SENTRY_ORG         — Sentry organization slug
    SENTRY_PROJECT     — Sentry project slug

Exports:
    import_sentry_issues(conn) -> int
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from ._base import _finding, _safe_query, _safe_query_all

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────

SENTRY_AUTH_TOKEN = os.environ.get("SENTRY_AUTH_TOKEN", "")
SENTRY_ORG = os.environ.get("SENTRY_ORG", "")
SENTRY_PROJECT = os.environ.get("SENTRY_PROJECT", "")

_SENTRY_API_BASE = "https://sentry.io/api/0"
_REQUEST_TIMEOUT = 30  # seconds
_MAX_ISSUES = 50  # max issues to fetch per run


# ── Severity classification ───────────────────────────────────────────────

def _classify_severity(event_count: int, first_seen: str, last_seen: str) -> str:
    """Classify severity based on frequency.

    >100 events/day = critical, >10 = high, >1 = medium, else low.
    """
    if not first_seen or not last_seen:
        return "medium"

    try:
        first_dt = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
        last_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
        span_days = max((last_dt - first_dt).total_seconds() / 86400, 1.0)
        events_per_day = event_count / span_days
    except (ValueError, TypeError):
        events_per_day = event_count

    if events_per_day > 100:
        return "critical"
    elif events_per_day > 10:
        return "high"
    elif events_per_day > 1:
        return "medium"
    return "low"


# ── Fix recommendation patterns ──────────────────────────────────────────

_FIX_PATTERNS = [
    (re.compile(r"NameError.*name '(\w+)' is not defined", re.IGNORECASE),
     "auto_fixable",
     lambda m: f"Add missing import or define '{m.group(1)}' before use."),
    (re.compile(r"ImportError.*No module named '(\S+)'", re.IGNORECASE),
     "auto_fixable",
     lambda m: f"Install or fix import path for '{m.group(1)}'."),
    (re.compile(r"ModuleNotFoundError.*No module named '(\S+)'", re.IGNORECASE),
     "auto_fixable",
     lambda m: f"Install or fix import path for '{m.group(1)}'."),
    (re.compile(r"AttributeError.*'NoneType' object has no attribute '(\w+)'", re.IGNORECASE),
     "auto_fixable",
     lambda m: f"Add None check before accessing '.{m.group(1)}'."),
    (re.compile(r"KeyError:\s*['\"]?(\w+)['\"]?", re.IGNORECASE),
     "auto_fixable",
     lambda m: f"Use .get('{m.group(1)}') with a default instead of direct key access."),
    (re.compile(r"TypeError.*argument", re.IGNORECASE),
     "investigate",
     lambda m: "Check function signatures and argument types at the call site."),
    (re.compile(r"ValueError", re.IGNORECASE),
     "investigate",
     lambda m: "Validate input data before processing."),
    (re.compile(r"ZeroDivisionError", re.IGNORECASE),
     "auto_fixable",
     lambda m: "Add zero-check before division."),
    (re.compile(r"RecursionError", re.IGNORECASE),
     "investigate",
     lambda m: "Check for infinite recursion — add base case or depth limit."),
    (re.compile(r"PermissionError|Forbidden|403", re.IGNORECASE),
     "security",
     lambda m: "Review file/API permissions. May indicate a security issue."),
    (re.compile(r"TimeoutError|timed?\s*out", re.IGNORECASE),
     "investigate",
     lambda m: "Add timeout handling and consider retry with backoff."),
    (re.compile(r"ConnectionError|ConnectionRefused", re.IGNORECASE),
     "investigate",
     lambda m: "Add connection error handling and circuit breaker pattern."),
    (re.compile(r"IntegrityError|UNIQUE constraint", re.IGNORECASE),
     "investigate",
     lambda m: "Add upsert logic or check for existing records before insert."),
]


def _recommend_fix(error_message: str) -> tuple[str, str]:
    """Generate a fix recommendation based on error type.

    Returns (fix_category, recommendation_text).
    fix_category: 'auto_fixable', 'investigate', 'security'
    """
    for pattern, category, recommender in _FIX_PATTERNS:
        match = pattern.search(error_message)
        if match:
            return category, recommender(match)
    return "investigate", "Review the stacktrace and error context to determine root cause."


# ── Stacktrace parsing ────────────────────────────────────────────────────

def _extract_files_from_stacktrace(stacktrace_data: dict) -> list[str]:
    """Extract file paths from a Sentry stacktrace.

    Returns paths relative to the project (strips absolute path prefixes).
    """
    files = []
    if not stacktrace_data:
        return files

    frames = stacktrace_data.get("frames", [])
    for frame in frames:
        filename = frame.get("filename") or frame.get("absPath") or ""
        if not filename or filename.startswith("<"):
            continue
        # Normalize: strip common prefixes, keep paths under mandarin/
        if "mandarin/" in filename:
            idx = filename.index("mandarin/")
            filename = filename[idx:]
        elif filename.startswith("/"):
            continue  # Skip absolute system paths
        if filename not in files:
            files.append(filename)

    return files


def _format_stacktrace(stacktrace_data: dict) -> str:
    """Format a Sentry stacktrace into readable text."""
    if not stacktrace_data:
        return "(no stacktrace available)"

    lines = []
    frames = stacktrace_data.get("frames", [])
    for frame in frames[-10:]:  # Last 10 frames (most relevant)
        filename = frame.get("filename", "?")
        lineno = frame.get("lineNo", "?")
        function = frame.get("function", "?")
        context_line = frame.get("context_line", "").strip()
        lines.append(f"  File \"{filename}\", line {lineno}, in {function}")
        if context_line:
            lines.append(f"    {context_line}")

    return "\n".join(lines) if lines else "(no stacktrace frames)"


# ── Sentry API client ────────────────────────────────────────────────────

def _sentry_get(url: str) -> dict | list | None:
    """Make an authenticated GET request to the Sentry API."""
    if not SENTRY_AUTH_TOKEN:
        return None

    req = Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {SENTRY_AUTH_TOKEN}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("Sentry API HTTP error %d for %s", exc.code, url)
        return None
    except (URLError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Sentry API request failed: %s", exc)
        return None


def _fetch_unresolved_issues() -> list[dict]:
    """Fetch recent unresolved issues from Sentry."""
    if not SENTRY_ORG or not SENTRY_PROJECT:
        logger.debug("Sentry: SENTRY_ORG or SENTRY_PROJECT not configured")
        return []

    url = (
        f"{_SENTRY_API_BASE}/projects/{SENTRY_ORG}/{SENTRY_PROJECT}/issues/"
        f"?query=is:unresolved&sort=freq&limit={_MAX_ISSUES}"
    )
    data = _sentry_get(url)
    return data if isinstance(data, list) else []


def _fetch_latest_event(issue_id: str) -> dict | None:
    """Fetch the latest event for a given issue to get stacktrace details."""
    if not SENTRY_ORG or not SENTRY_PROJECT:
        return None

    url = (
        f"{_SENTRY_API_BASE}/projects/{SENTRY_ORG}/{SENTRY_PROJECT}"
        f"/issues/{issue_id}/events/latest/"
    )
    return _sentry_get(url)


# ── Claude prompt generation ──────────────────────────────────────────────

def _build_claude_prompt(
    error_type: str, error_message: str, files: list[str],
    stacktrace_text: str, recommendation: str,
) -> str:
    """Build a Claude Code prompt for auto-fixing this error."""
    file_context = ""
    if files:
        file_context = f"Affected files: {', '.join(files[:5])}\n"

    return (
        f"Fix the following runtime error:\n\n"
        f"Error: {error_type}: {error_message}\n"
        f"{file_context}\n"
        f"Stacktrace:\n{stacktrace_text}\n\n"
        f"Recommended approach: {recommendation}\n\n"
        f"Make the minimal, targeted fix. Add appropriate error handling "
        f"where needed. Do not change unrelated code."
    )


# ── Main import function ─────────────────────────────────────────────────

def import_sentry_issues(conn) -> int:
    """Fetch unresolved Sentry issues and import new ones as pi_findings.

    Deduplicates against existing open findings in the runtime_health dimension
    by storing the Sentry issue ID in the finding metadata (analysis field).

    Args:
        conn: SQLite database connection.

    Returns:
        Number of new findings imported.
    """
    if not SENTRY_AUTH_TOKEN:
        logger.debug("Sentry: no SENTRY_AUTH_TOKEN configured, skipping import")
        return 0

    if not SENTRY_ORG or not SENTRY_PROJECT:
        logger.debug("Sentry: SENTRY_ORG or SENTRY_PROJECT not configured, skipping")
        return 0

    # Fetch unresolved issues
    issues = _fetch_unresolved_issues()
    if not issues:
        logger.debug("Sentry: no unresolved issues found")
        return 0

    # Get the latest audit_id for linking
    audit_row = conn.execute(
        "SELECT MAX(id) as max_id FROM product_audit"
    ).fetchone()
    audit_id = audit_row["max_id"] if audit_row and audit_row["max_id"] else None

    # Load existing open runtime_health findings for deduplication
    # We store the Sentry issue ID in the analysis field as a marker
    open_findings = _safe_query_all(conn, """
        SELECT id, title, analysis FROM pi_finding
        WHERE dimension = 'runtime_health'
          AND status NOT IN ('resolved', 'rejected')
    """) or []

    # Extract Sentry issue IDs from existing findings
    existing_sentry_ids = set()
    for f in open_findings:
        analysis = f["analysis"] or ""
        match = re.search(r"\[sentry:(\d+)\]", analysis)
        if match:
            existing_sentry_ids.add(match.group(1))

    imported = 0

    for issue in issues:
        sentry_issue_id = str(issue.get("id", ""))
        if not sentry_issue_id:
            continue

        # Dedup: skip if already imported
        if sentry_issue_id in existing_sentry_ids:
            logger.debug("Sentry: skipping duplicate issue #%s", sentry_issue_id)
            continue

        # Extract issue metadata
        error_type = issue.get("type", "Error")
        short_id = issue.get("shortId", sentry_issue_id)
        title_raw = issue.get("title", "Unknown error")
        event_count = issue.get("count", 0)
        first_seen = issue.get("firstSeen", "")
        last_seen = issue.get("lastSeen", "")
        level = issue.get("level", "error")

        # Fetch latest event for stacktrace details
        event = _fetch_latest_event(sentry_issue_id)

        stacktrace_text = "(no stacktrace available)"
        files = []
        error_message = title_raw

        if event:
            # Extract error message
            for entry in event.get("entries", []):
                if entry.get("type") == "exception":
                    exc_data = entry.get("data", {})
                    values = exc_data.get("values", [])
                    if values:
                        last_exc = values[-1]
                        error_type = last_exc.get("type", error_type)
                        error_message = last_exc.get("value", error_message)
                        stacktrace = last_exc.get("stacktrace")
                        if stacktrace:
                            stacktrace_text = _format_stacktrace(stacktrace)
                            files = _extract_files_from_stacktrace(stacktrace)
                    break

        # Classify severity and generate recommendation
        severity = _classify_severity(event_count, first_seen, last_seen)
        fix_category, recommendation = _recommend_fix(
            f"{error_type}: {error_message}"
        )

        # Build finding fields
        title = f"{error_type}: {title_raw[:120]}"
        claude_prompt = _build_claude_prompt(
            error_type, error_message, files, stacktrace_text, recommendation,
        )

        # Build analysis with Sentry ID marker for deduplication
        analysis_parts = [
            f"[sentry:{sentry_issue_id}]",
            f"Sentry issue: {short_id} ({event_count} events)",
            f"First seen: {first_seen}",
            f"Last seen: {last_seen}",
            f"Level: {level}",
            f"Fix category: {fix_category}",
            f"\nStacktrace:\n{stacktrace_text}",
        ]
        if recommendation:
            analysis_parts.append(f"\nRecommendation: {recommendation}")
        if claude_prompt:
            analysis_parts.append(f"\nClaude prompt:\n{claude_prompt}")
        if files:
            analysis_parts.append(f"\nAffected files: {', '.join(files[:10])}")

        full_analysis = "\n".join(analysis_parts)

        try:
            conn.execute("""
                INSERT INTO pi_finding
                    (audit_id, dimension, severity, title, analysis,
                     status, metric_name, last_seen_audit_id)
                VALUES (?, 'runtime_health', ?, ?, ?, 'investigating', 'runtime_health', ?)
            """, (
                audit_id,
                severity,
                title,
                full_analysis,
                audit_id,
            ))
            imported += 1
            existing_sentry_ids.add(sentry_issue_id)
        except (sqlite3.OperationalError, sqlite3.Error) as exc:
            logger.debug("Sentry: failed to insert issue #%s: %s", sentry_issue_id, exc)

    if imported > 0:
        try:
            conn.commit()
        except sqlite3.Error:
            pass
        logger.info("Sentry: imported %d new issue(s)", imported)

    return imported
