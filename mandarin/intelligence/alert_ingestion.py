"""Unified alert ingestion — pulls alerts from multiple monitoring sources.

Collects alerts from:
- Sentry (error tracking via API)
- UptimeRobot (uptime monitoring via API)
- GitHub Actions (CI failures via API)
- Intelligence layer (pi_finding table)
- pytest (test failures from local runs)

Each ingestion function returns a list of standardized alert dicts:
    {
        "source": str,          # "sentry", "uptime", "github", "intelligence", "pytest"
        "external_id": str,     # Unique ID from the source (for dedup)
        "title": str,           # Short description
        "description": str,     # Detailed description / stacktrace
        "severity": str,        # "critical", "high", "medium", "low"
        "category": str,        # "code", "data", "infrastructure", "content", "strategy"
        "raw_data": dict,       # Original data from the source
        "files": list[str],     # Affected file paths
        "timestamp": str,       # ISO 8601 timestamp
    }

Safety: All ingestion is read-only. No modifications to source systems.

Exports:
    ingest_all_alerts(conn) -> list[dict]
    ingest_sentry_alerts() -> list[dict]
    ingest_uptime_alerts() -> list[dict]
    ingest_github_alerts() -> list[dict]
    ingest_intelligence_findings(conn) -> list[dict]
    ingest_test_results() -> list[dict]
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone, UTC
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..settings import (
    SENTRY_AUTH_TOKEN,
    SENTRY_ORG,
    SENTRY_PROJECT,
    UPTIMEROBOT_API_KEY,
)
from ._base import _safe_query_all

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REQUEST_TIMEOUT = 30


# ── Standardized alert dict ───────────────────────────────────────────────

def _alert(
    source: str,
    external_id: str,
    title: str,
    description: str,
    severity: str,
    category: str,
    raw_data: dict | None = None,
    files: list[str] | None = None,
    timestamp: str | None = None,
) -> dict:
    """Create a standardized alert dict."""
    return {
        "source": source,
        "external_id": external_id,
        "title": title,
        "description": description,
        "severity": severity,
        "category": category,
        "raw_data": raw_data or {},
        "files": files or [],
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
    }


# ── Sentry ingestion ─────────────────────────────────────────────────────

def ingest_sentry_alerts() -> list[dict]:
    """Fetch recent unresolved Sentry issues and return as standardized alerts.

    Requires SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT environment variables.
    Returns empty list if not configured.
    """
    auth_token = SENTRY_AUTH_TOKEN
    org = SENTRY_ORG
    project = SENTRY_PROJECT

    if not auth_token or not org or not project:
        logger.debug("Sentry alerts: not configured (missing env vars)")
        return []

    url = (
        f"https://sentry.io/api/0/projects/{org}/{project}/issues/"
        f"?query=is:unresolved&sort=freq&limit=25"
    )

    try:
        req = Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {auth_token}")
        req.add_header("Content-Type", "application/json")

        with urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            issues = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Sentry alerts: API request failed: %s", exc)
        return []

    if not isinstance(issues, list):
        return []

    alerts = []
    for issue in issues:
        issue_id = str(issue.get("id", ""))
        if not issue_id:
            continue

        event_count = issue.get("count", 0)
        first_seen = issue.get("firstSeen", "")
        last_seen = issue.get("lastSeen", "")
        title_raw = issue.get("title", "Unknown error")
        level = issue.get("level", "error")

        # Classify severity
        severity = _classify_sentry_severity(event_count, first_seen, last_seen)

        # Extract files from title/metadata heuristically
        files = []
        metadata = issue.get("metadata", {})
        if metadata.get("filename"):
            files.append(metadata["filename"])

        alerts.append(_alert(
            source="sentry",
            external_id=f"sentry:{issue_id}",
            title=f"Sentry: {title_raw[:150]}",
            description=(
                f"Sentry issue #{issue.get('shortId', issue_id)} — "
                f"{event_count} events, level={level}\n"
                f"First seen: {first_seen}\nLast seen: {last_seen}"
            ),
            severity=severity,
            category="code",
            raw_data={"sentry_id": issue_id, "event_count": event_count, "level": level},
            files=files,
            timestamp=last_seen or datetime.now(UTC).isoformat(),
        ))

    logger.info("Sentry alerts: ingested %d issues", len(alerts))
    return alerts


def _classify_sentry_severity(event_count: int, first_seen: str, last_seen: str) -> str:
    """Classify Sentry issue severity based on event frequency."""
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
    if events_per_day > 10:
        return "high"
    if events_per_day > 1:
        return "medium"
    return "low"


# ── UptimeRobot ingestion ────────────────────────────────────────────────

def ingest_uptime_alerts() -> list[dict]:
    """Check UptimeRobot for down monitors and return as standardized alerts.

    Requires UPTIMEROBOT_API_KEY environment variable (or in settings).
    Returns empty list if not configured.
    """
    api_key = UPTIMEROBOT_API_KEY or ""

    if not api_key:
        logger.debug("UptimeRobot alerts: not configured")
        return []

    try:
        import requests
        resp = requests.post(
            "https://api.uptimerobot.com/v2/getMonitors",
            data={
                "api_key": api_key,
                "format": "json",
                "custom_uptime_ratios": "7-30",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("UptimeRobot: API returned status %s", resp.status_code)
            return []

        data = resp.json()
        if data.get("stat") != "ok":
            logger.warning("UptimeRobot: API error: %s",
                           data.get("error", {}).get("message", "unknown"))
            return []
    except Exception as exc:
        logger.warning("UptimeRobot alerts: request failed: %s", exc)
        return []

    _STATUS_DOWN = {8, 9}  # seems_down, down
    _STATUS_LABELS = {0: "paused", 1: "not_checked", 2: "up", 8: "seems_down", 9: "down"}

    alerts = []
    for monitor in data.get("monitors", []):
        status = monitor.get("status", 2)
        name = monitor.get("friendly_name", "Unknown")
        url = monitor.get("url", "")
        ratios = (monitor.get("custom_uptime_ratio") or "100-100").split("-")

        uptime_7d = float(ratios[0]) if len(ratios) > 0 else 100.0
        uptime_30d = float(ratios[1]) if len(ratios) > 1 else 100.0

        # Alert on down monitors
        if status in _STATUS_DOWN:
            alerts.append(_alert(
                source="uptime",
                external_id=f"uptime:{monitor.get('id', name)}",
                title=f"Monitor DOWN: {name}",
                description=(
                    f"Monitor '{name}' is {_STATUS_LABELS.get(status, 'unknown')}.\n"
                    f"URL: {url}\n"
                    f"7-day uptime: {uptime_7d}%\n"
                    f"30-day uptime: {uptime_30d}%"
                ),
                severity="critical",
                category="infrastructure",
                raw_data={"monitor_id": monitor.get("id"), "status": status, "url": url},
            ))
        # Alert on degraded uptime (< 99.5% over 7 days)
        elif uptime_7d < 99.5:
            alerts.append(_alert(
                source="uptime",
                external_id=f"uptime:degraded:{monitor.get('id', name)}",
                title=f"Degraded uptime: {name} ({uptime_7d}% over 7d)",
                description=(
                    f"Monitor '{name}' uptime is below 99.5% threshold.\n"
                    f"URL: {url}\n"
                    f"7-day uptime: {uptime_7d}%\n"
                    f"30-day uptime: {uptime_30d}%"
                ),
                severity="high",
                category="infrastructure",
                raw_data={"monitor_id": monitor.get("id"), "uptime_7d": uptime_7d, "url": url},
            ))

    logger.info("UptimeRobot alerts: ingested %d alerts", len(alerts))
    return alerts


# ── GitHub Actions ingestion ─────────────────────────────────────────────

def ingest_github_alerts() -> list[dict]:
    """Check GitHub Actions for recent failures and Dependabot alerts.

    Uses the `gh` CLI for API access (authenticated via GITHUB_TOKEN or gh auth).
    Returns empty list if `gh` is not available.
    """
    alerts = []

    # 1. Recent failed workflow runs
    alerts.extend(_ingest_github_workflow_failures())

    # 2. Dependabot security alerts
    alerts.extend(_ingest_github_dependabot_alerts())

    logger.info("GitHub alerts: ingested %d total alerts", len(alerts))
    return alerts


def _ingest_github_workflow_failures() -> list[dict]:
    """Fetch recent failed GitHub Actions workflow runs."""
    try:
        result = subprocess.run(
            ["gh", "run", "list", "--status=failure", "--limit=10", "--json",
             "databaseId,name,conclusion,createdAt,headBranch,url"],
            capture_output=True, text=True, timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            logger.debug("GitHub workflow failures: gh CLI failed: %s", result.stderr.strip())
            return []

        runs = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
        logger.debug("GitHub workflow failures: %s", exc)
        return []

    alerts = []
    for run in runs:
        run_id = str(run.get("databaseId", ""))
        name = run.get("name", "Unknown workflow")
        branch = run.get("headBranch", "unknown")
        created_at = run.get("createdAt", "")
        url = run.get("url", "")

        # Severity based on workflow name
        severity = "medium"
        if "deploy" in name.lower():
            severity = "critical"
        elif "security" in name.lower() or "dast" in name.lower():
            severity = "high"

        category = "code"
        if "deploy" in name.lower():
            category = "infrastructure"
        elif "security" in name.lower():
            category = "code"

        alerts.append(_alert(
            source="github",
            external_id=f"github:run:{run_id}",
            title=f"CI failure: {name} on {branch}",
            description=f"Workflow '{name}' failed on branch '{branch}'.\nURL: {url}",
            severity=severity,
            category=category,
            raw_data={"run_id": run_id, "workflow": name, "branch": branch, "url": url},
            timestamp=created_at,
        ))

    return alerts


def _ingest_github_dependabot_alerts() -> list[dict]:
    """Fetch open Dependabot security alerts."""
    try:
        result = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/dependabot/alerts",
             "--jq", '.[] | select(.state == "open") | {number, severity: .security_advisory.severity, summary: .security_advisory.summary, package: .dependency.package.name, created_at}'],
            capture_output=True, text=True, timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            logger.debug("Dependabot alerts: gh CLI failed: %s", result.stderr.strip()[:200])
            return []

        # Parse JSONL output (one JSON object per line)
        alerts_data = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    alerts_data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.debug("Dependabot alerts: %s", exc)
        return []

    _SEVERITY_MAP = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}

    alerts = []
    for item in alerts_data:
        number = str(item.get("number", ""))
        severity = _SEVERITY_MAP.get(item.get("severity", "medium"), "medium")
        summary = item.get("summary", "Security vulnerability")
        package = item.get("package", "unknown")

        alerts.append(_alert(
            source="github",
            external_id=f"github:dependabot:{number}",
            title=f"Dependabot: {summary[:100]} ({package})",
            description=f"Security vulnerability in {package}: {summary}",
            severity=severity,
            category="code",
            raw_data={"alert_number": number, "package": package},
            timestamp=item.get("created_at", ""),
        ))

    return alerts


# ── Intelligence findings ingestion ──────────────────────────────────────

def ingest_intelligence_findings(conn) -> list[dict]:
    """Read open findings from pi_finding that have not been resolved.

    These are findings already generated by the intelligence layer's daily audit.
    We re-surface them as alerts for the self-healing loop to classify and act on.
    """
    rows = _safe_query_all(conn, """
        SELECT id, dimension, severity, title, analysis, status, created_at
        FROM pi_finding
        WHERE status NOT IN ('resolved', 'rejected', 'verified', 'implemented')
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END,
            created_at DESC
        LIMIT 50
    """) or []

    _DIMENSION_TO_CATEGORY = {
        "visual_vibe": "code",
        "copy_drift": "content",
        "runtime_health": "code",
        "ci_health": "code",
        "engineering": "code",
        "security": "code",
        "retention": "strategy",
        "ux": "strategy",
        "onboarding": "strategy",
        "engagement": "strategy",
        "profitability": "strategy",
        "drill_quality": "data",
        "content": "data",
        "srs_funnel": "data",
        "curriculum": "data",
    }

    alerts = []
    for row in rows:
        finding_id = row["id"]
        dimension = row["dimension"] or "unknown"
        category = _DIMENSION_TO_CATEGORY.get(dimension, "strategy")

        alerts.append(_alert(
            source="intelligence",
            external_id=f"intelligence:finding:{finding_id}",
            title=row["title"] or f"Finding #{finding_id}",
            description=row["analysis"] or "",
            severity=row["severity"] or "medium",
            category=category,
            raw_data={
                "finding_id": finding_id,
                "dimension": dimension,
                "status": row["status"],
            },
            files=_extract_files_from_analysis(row["analysis"] or ""),
            timestamp=row["created_at"] or "",
        ))

    logger.info("Intelligence findings: ingested %d open findings", len(alerts))
    return alerts


def _extract_files_from_analysis(analysis: str) -> list[str]:
    """Extract file paths from finding analysis text."""
    files = []
    # Look for "Affected files:" section
    affected_match = re.search(r"Affected files?:\s*(.+?)(?:\n|$)", analysis)
    if affected_match:
        for f in affected_match.group(1).split(","):
            f = f.strip()
            if f.startswith("mandarin/") and not f.endswith("/"):
                files.append(f)

    # Fall back to bare mandarin/ paths
    if not files:
        bare_paths = re.findall(r'(mandarin/\S+\.py)', analysis)
        files.extend(bare_paths[:5])

    return files


# ── pytest results ingestion ─────────────────────────────────────────────

def ingest_test_results() -> list[dict]:
    """Run pytest in dry-run collection mode and report any import/collection errors.

    For actual test failures, runs a fast subset of tests (smoke tests only)
    to avoid long execution times in the self-healing loop.
    """
    alerts = []

    # 1. Check for collection errors (import failures, syntax errors)
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--collect-only", "-q", "--tb=short"],
            capture_output=True, text=True, timeout=60,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            # Parse collection errors
            stderr = result.stderr or result.stdout or ""
            errors = _parse_pytest_collection_errors(stderr)
            for error in errors:
                alerts.append(_alert(
                    source="pytest",
                    external_id=f"pytest:collection:{error['file']}",
                    title=f"Test collection error: {error['file']}",
                    description=error["message"],
                    severity="medium",
                    category="code",
                    files=[error["file"]] if error["file"] else [],
                ))
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.debug("pytest collection check failed: %s", exc)

    # 2. Run quick smoke tests (tests marked as @pytest.mark.smoke or fast tests)
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-x", "--tb=short", "-q",
             "--timeout=30", "-k", "test_smoke or test_import or test_health"],
            capture_output=True, text=True, timeout=120,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            failures = _parse_pytest_failures(result.stdout or "")
            for failure in failures:
                alerts.append(_alert(
                    source="pytest",
                    external_id=f"pytest:failure:{failure['test']}",
                    title=f"Test failure: {failure['test']}",
                    description=failure["message"],
                    severity="medium",
                    category="code",
                    files=[failure["file"]] if failure.get("file") else [],
                ))
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.debug("pytest smoke tests failed or timed out: %s", exc)

    logger.info("pytest alerts: ingested %d alerts", len(alerts))
    return alerts


def _parse_pytest_collection_errors(output: str) -> list[dict]:
    """Parse pytest collection output for import/syntax errors."""
    errors = []
    # Match patterns like: ERROR tests/test_foo.py - ImportError: ...
    for match in re.finditer(r"ERROR\s+([\w/._-]+\.py)\s*[-:]\s*(.+)", output):
        errors.append({
            "file": match.group(1),
            "message": match.group(2).strip(),
        })
    return errors


def _parse_pytest_failures(output: str) -> list[dict]:
    """Parse pytest output for test failures."""
    failures = []
    # Match patterns like: FAILED tests/test_foo.py::test_bar - AssertionError: ...
    for match in re.finditer(r"FAILED\s+([\w/._-]+\.py)::([\w_]+)\s*[-:]\s*(.+)", output):
        failures.append({
            "file": match.group(1),
            "test": f"{match.group(1)}::{match.group(2)}",
            "message": match.group(3).strip(),
        })
    return failures


# ── Unified ingestion ────────────────────────────────────────────────────

def ingest_all_alerts(conn) -> list[dict]:
    """Ingest alerts from all configured sources.

    Each source is called independently — failures in one source do not
    block ingestion from other sources.

    Returns a combined list of standardized alert dicts, deduplicated
    by external_id.
    """
    all_alerts = []
    seen_ids = set()

    sources = [
        ("intelligence", lambda: ingest_intelligence_findings(conn)),
        ("sentry", ingest_sentry_alerts),
        ("uptime", ingest_uptime_alerts),
        ("github", ingest_github_alerts),
        # pytest is intentionally omitted from the default loop —
        # it runs subprocesses and is better triggered explicitly.
    ]

    for source_name, ingest_fn in sources:
        try:
            source_alerts = ingest_fn()
            for alert in source_alerts:
                ext_id = alert.get("external_id", "")
                if ext_id and ext_id not in seen_ids:
                    seen_ids.add(ext_id)
                    all_alerts.append(alert)
        except Exception as exc:
            logger.warning("Alert ingestion from %s failed: %s", source_name, exc)

    logger.info(
        "Unified alert ingestion: %d total alerts from %d sources",
        len(all_alerts), len(sources),
    )
    return all_alerts
