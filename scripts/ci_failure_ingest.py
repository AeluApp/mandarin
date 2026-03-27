#!/usr/bin/env python3
"""CI Failure Ingest — extract failures from GitHub Actions and write findings JSON.

Runs in CI (no database access). Fetches the failed workflow run's logs via
the GitHub API, parses error details, and writes a ci_findings.json file.
The quality_scheduler picks up this file on the next daily run and imports
the findings into the pi_finding table via mandarin.intelligence.ci_ingest.

Environment variables (set by the CI Feedback Loop workflow):
    GITHUB_TOKEN        — GitHub API token
    WORKFLOW_NAME       — name of the failed workflow (e.g. "Tests")
    WORKFLOW_RUN_ID     — numeric run ID
    WORKFLOW_CONCLUSION — "failure" (only runs on failure)

Usage:
    python scripts/ci_failure_ingest.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, UTC

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
WORKFLOW_NAME = os.environ.get("WORKFLOW_NAME", "")
WORKFLOW_RUN_ID = os.environ.get("WORKFLOW_RUN_ID", "")
WORKFLOW_CONCLUSION = os.environ.get("WORKFLOW_CONCLUSION", "")

OUTPUT_FILE = "ci_findings.json"

# Severity mapping: workflow name -> default severity
_WORKFLOW_SEVERITY = {
    "Tests": "medium",
    "E2E Tests": "medium",
    "Security": "high",
    "Deploy": "critical",
}


# ---------------------------------------------------------------------------
# GitHub API helpers (using gh CLI)
# ---------------------------------------------------------------------------

def _gh_api(endpoint: str) -> dict | list | None:
    """Call the GitHub REST API via `gh api`."""
    try:
        result = subprocess.run(
            ["gh", "api", endpoint, "--paginate"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"gh api error: {result.stderr.strip()}", file=sys.stderr)
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
        print(f"gh api call failed: {exc}", file=sys.stderr)
        return None


def _gh_log_text(run_id: str, job_id: int) -> str:
    """Fetch the raw log text for a specific job in a workflow run."""
    try:
        result = subprocess.run(
            ["gh", "api",
             f"repos/{{owner}}/{{repo}}/actions/jobs/{job_id}/logs",
             "--method", "GET"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            # Fallback: try run-level logs
            result = subprocess.run(
                ["gh", "run", "view", run_id, "--log-failed"],
                capture_output=True, text=True, timeout=120,
            )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def fetch_failed_jobs(run_id: str) -> list[dict]:
    """Fetch metadata for all failed jobs in a workflow run."""
    data = _gh_api(f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs")
    if not data or "jobs" not in data:
        return []

    failed = []
    for job in data["jobs"]:
        if job.get("conclusion") == "failure":
            failed.append({
                "id": job["id"],
                "name": job.get("name", "unknown"),
                "started_at": job.get("started_at", ""),
                "completed_at": job.get("completed_at", ""),
            })
    return failed


def fetch_failed_logs(run_id: str) -> str:
    """Fetch the combined failed log output for a workflow run."""
    try:
        result = subprocess.run(
            ["gh", "run", "view", run_id, "--log-failed"],
            capture_output=True, text=True, timeout=120,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

# Common patterns for extracting file + line from error output
_FILE_LINE_PATTERNS = [
    # Python traceback: File "mandarin/foo.py", line 42
    re.compile(r'File "([^"]+)", line (\d+)'),
    # pytest: mandarin/foo.py::test_bar FAILED
    re.compile(r'^([a-zA-Z_][\w/\\.-]+\.py)::(\w+)', re.MULTILINE),
    # ruff / flake8: mandarin/foo.py:42:10 E501
    re.compile(r'^([a-zA-Z_][\w/\\.-]+\.py):(\d+):\d+', re.MULTILINE),
    # Generic: at mandarin/foo.py:42
    re.compile(r'at\s+([a-zA-Z_][\w/\\.-]+\.py):(\d+)'),
    # TypeScript / JS: src/foo.ts(42,10)
    re.compile(r'([a-zA-Z_][\w/\\.-]+\.[tj]sx?)\((\d+),\d+\)'),
]

# Patterns that indicate the type of failure
_FAILURE_TYPE_PATTERNS = [
    (re.compile(r'AssertionError', re.IGNORECASE), "assertion_failure"),
    (re.compile(r'FAILED\s+tests/', re.IGNORECASE), "test_failure"),
    (re.compile(r'ModuleNotFoundError|ImportError', re.IGNORECASE), "import_error"),
    (re.compile(r'SyntaxError', re.IGNORECASE), "syntax_error"),
    (re.compile(r'TypeError|ValueError|AttributeError', re.IGNORECASE), "type_error"),
    (re.compile(r'TimeoutError|timed?\s*out', re.IGNORECASE), "timeout"),
    (re.compile(r'PermissionError|permission denied', re.IGNORECASE), "permission_error"),
    (re.compile(r'ConnectionError|ConnectionRefused', re.IGNORECASE), "connection_error"),
    (re.compile(r'bandit|security|vulnerability|CVE-', re.IGNORECASE), "security_finding"),
    (re.compile(r'ruff|lint|E\d{3}|W\d{3}', re.IGNORECASE), "lint_error"),
    (re.compile(r'coverage.*fail|cov-fail-under', re.IGNORECASE), "coverage_failure"),
    (re.compile(r'deploy|fly\.io|flyctl', re.IGNORECASE), "deploy_failure"),
]

# Error message extraction: capture the most informative line
_ERROR_MSG_PATTERNS = [
    # Python exceptions: ExceptionType: message
    re.compile(r'^(\w*Error\w*:\s*.+)$', re.MULTILINE),
    # AssertionError with context
    re.compile(r'^(assert\s+.+)$', re.MULTILINE),
    # FAILED line from pytest
    re.compile(r'^(FAILED\s+.+)$', re.MULTILINE),
    # E   lines from pytest
    re.compile(r'^E\s+(.+)$', re.MULTILINE),
    # Generic "error:" prefix
    re.compile(r'^.*error:\s*(.+)$', re.MULTILINE | re.IGNORECASE),
]


def parse_failure_details(log_text: str, job_name: str = "") -> dict:
    """Parse a CI log to extract structured failure information.

    Returns:
        {
            "job_name": str,
            "failure_type": str,
            "error_messages": list[str],
            "files": list[str],
            "file_lines": list[dict],  # [{file, line}]
            "log_excerpt": str,  # last ~80 lines
        }
    """
    result = {
        "job_name": job_name,
        "failure_type": "unknown",
        "error_messages": [],
        "files": [],
        "file_lines": [],
        "log_excerpt": "",
    }

    if not log_text:
        return result

    # Detect failure type
    for pattern, ftype in _FAILURE_TYPE_PATTERNS:
        if pattern.search(log_text):
            result["failure_type"] = ftype
            break

    # Extract file + line references
    seen_files = set()
    for pattern in _FILE_LINE_PATTERNS:
        for match in pattern.finditer(log_text):
            filepath = match.group(1)
            # Normalize: skip venv, site-packages, system paths
            if any(skip in filepath for skip in (
                "site-packages", "venv/", ".venv/", "/usr/", "/lib/python",
                "node_modules/", ".tox/",
            )):
                continue
            if filepath not in seen_files:
                seen_files.add(filepath)
                result["files"].append(filepath)
                try:
                    line_num = int(match.group(2))
                    result["file_lines"].append({"file": filepath, "line": line_num})
                except (IndexError, ValueError):
                    pass

    # Extract error messages
    seen_msgs = set()
    for pattern in _ERROR_MSG_PATTERNS:
        for match in pattern.finditer(log_text):
            msg = match.group(1).strip() if match.lastindex else match.group(0).strip()
            if msg and msg not in seen_msgs and len(msg) < 500:
                seen_msgs.add(msg)
                result["error_messages"].append(msg)
                if len(result["error_messages"]) >= 10:
                    break

    # Log excerpt: last 80 non-empty lines
    lines = [ln for ln in log_text.splitlines() if ln.strip()]
    result["log_excerpt"] = "\n".join(lines[-80:])

    return result


# ---------------------------------------------------------------------------
# Finding generation
# ---------------------------------------------------------------------------

def _classify_failure(workflow_name: str, failure_type: str) -> dict:
    """Determine severity and decision class for a CI failure.

    Uses mandarin.intelligence.ci_ingest.classify_ci_failure if available,
    otherwise falls back to local rules.
    """
    try:
        from mandarin.intelligence.ci_ingest import classify_ci_failure
        return classify_ci_failure(
            f"{workflow_name}: {failure_type}",
        )
    except ImportError:
        pass

    # Fallback classification
    base_severity = _WORKFLOW_SEVERITY.get(workflow_name, "medium")

    severity_overrides = {
        "security_finding": "high",
        "deploy_failure": "critical",
        "syntax_error": "medium",
        "lint_error": "low",
        "import_error": "medium",
        "coverage_failure": "low",
    }

    severity = severity_overrides.get(failure_type, base_severity)

    # Decision class: lint and coverage failures are auto-fixable
    auto_fix_types = {"lint_error", "coverage_failure"}
    decision_class = "auto_fix" if failure_type in auto_fix_types else "informed_fix"

    return {
        "severity": severity,
        "decision_class": decision_class,
    }


def build_finding(
    workflow_name: str,
    job_name: str,
    failure_details: dict,
    run_id: str,
) -> dict:
    """Build a pi_finding-compatible dict from parsed CI failure details."""
    failure_type = failure_details["failure_type"]
    error_msgs = failure_details["error_messages"]
    files = failure_details["files"]

    classification = _classify_failure(workflow_name, failure_type)
    severity = classification["severity"]
    decision_class = classification.get("decision_class", "informed_fix")

    # Build descriptive title
    primary_error = error_msgs[0] if error_msgs else failure_type
    # Truncate for title
    if len(primary_error) > 100:
        primary_error = primary_error[:97] + "..."
    title = f"CI {workflow_name}/{job_name}: {primary_error}"

    # Build analysis
    analysis_parts = [
        f"Workflow: {workflow_name}",
        f"Job: {job_name}",
        f"Failure type: {failure_type}",
        f"Run ID: {run_id}",
        "",
    ]
    if error_msgs:
        analysis_parts.append("Error messages:")
        for msg in error_msgs[:5]:
            analysis_parts.append(f"  - {msg}")
        analysis_parts.append("")
    if failure_details["file_lines"]:
        analysis_parts.append("Affected locations:")
        for fl in failure_details["file_lines"][:10]:
            analysis_parts.append(f"  - {fl['file']}:{fl['line']}")
        analysis_parts.append("")
    analysis = "\n".join(analysis_parts)

    # Build recommendation
    recs = {
        "test_failure": "Investigate the failing test. Check if the test expectations are correct or if the implementation has regressed.",
        "assertion_failure": "Review the assertion that failed. The expected value may have changed due to a recent code change.",
        "import_error": "Check that all required modules are installed and import paths are correct.",
        "syntax_error": "Fix the syntax error in the identified file.",
        "type_error": "Review the type mismatch. Check function signatures and argument types.",
        "timeout": "Investigate why the operation timed out. Check for infinite loops, slow queries, or network issues.",
        "security_finding": "Address the security finding. Review the Bandit/SAST report for details.",
        "lint_error": "Fix the linting errors reported by ruff. Run `ruff check --fix` locally.",
        "coverage_failure": "Increase test coverage for the identified modules to meet the coverage threshold.",
        "deploy_failure": "Check deploy logs. Verify that the Fly.io configuration and secrets are correct.",
        "connection_error": "Check network connectivity and service dependencies in the CI environment.",
        "permission_error": "Review file permissions and CI runner configuration.",
    }
    recommendation = recs.get(failure_type,
        "Investigate the CI failure and fix the underlying issue.")

    # Build claude_prompt
    file_list = ", ".join(files[:5]) if files else "unknown files"
    claude_prompt = (
        f"CI failure in {workflow_name}/{job_name}.\n\n"
        f"Failure type: {failure_type}\n"
        f"Files: {file_list}\n\n"
    )
    if error_msgs:
        claude_prompt += "Errors:\n"
        for msg in error_msgs[:3]:
            claude_prompt += f"  {msg}\n"
        claude_prompt += "\n"
    claude_prompt += (
        f"1. Read the affected files: {file_list}\n"
        f"2. Identify the root cause of the {failure_type}\n"
        f"3. Fix the issue and verify the fix locally\n"
        f"4. Run the relevant tests to confirm the fix"
    )

    return {
        "dimension": "ci_health",
        "severity": severity,
        "title": title,
        "analysis": analysis,
        "recommendation": recommendation,
        "claude_prompt": claude_prompt,
        "impact": f"CI pipeline ({workflow_name}) is broken — blocks merges and deploys",
        "files": files,
        "decision_class": decision_class,
        "workflow_name": workflow_name,
        "workflow_run_id": run_id,
        "job_name": job_name,
        "failure_type": failure_type,
        "created_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not WORKFLOW_RUN_ID:
        print("ERROR: WORKFLOW_RUN_ID not set. This script should be run by the CI Feedback Loop workflow.",
              file=sys.stderr)
        sys.exit(1)

    if WORKFLOW_CONCLUSION != "failure":
        print(f"Workflow conclusion is '{WORKFLOW_CONCLUSION}', not 'failure'. Nothing to ingest.")
        sys.exit(0)

    print(f"Ingesting CI failure for workflow '{WORKFLOW_NAME}' (run {WORKFLOW_RUN_ID})")

    # Fetch failed job metadata
    failed_jobs = fetch_failed_jobs(WORKFLOW_RUN_ID)

    # Fetch combined failed logs
    log_text = fetch_failed_logs(WORKFLOW_RUN_ID)

    if not failed_jobs and not log_text:
        print("WARNING: Could not retrieve failure details. Creating a generic finding.",
              file=sys.stderr)
        failed_jobs = [{"id": 0, "name": "unknown"}]

    findings = []

    if failed_jobs:
        # Parse per-job if we have job-level data
        for job in failed_jobs:
            job_name = job["name"]
            # Try to extract job-specific log section
            job_log = _extract_job_log(log_text, job_name) if log_text else ""
            if not job_log:
                job_log = log_text  # Fall back to full log

            details = parse_failure_details(job_log, job_name)
            finding = build_finding(WORKFLOW_NAME, job_name, details, WORKFLOW_RUN_ID)
            findings.append(finding)
    else:
        # Single finding from the full log
        details = parse_failure_details(log_text, "unknown")
        finding = build_finding(WORKFLOW_NAME, "unknown", details, WORKFLOW_RUN_ID)
        findings.append(finding)

    # Deduplicate by title
    seen_titles = set()
    unique_findings = []
    for f in findings:
        if f["title"] not in seen_titles:
            seen_titles.add(f["title"])
            unique_findings.append(f)

    # Write output
    output = {
        "workflow_name": WORKFLOW_NAME,
        "workflow_run_id": WORKFLOW_RUN_ID,
        "ingested_at": datetime.now(UTC).isoformat(),
        "findings": unique_findings,
    }

    with open(OUTPUT_FILE, "w") as fh:
        json.dump(output, fh, indent=2)

    print(f"Wrote {len(unique_findings)} finding(s) to {OUTPUT_FILE}")


def _extract_job_log(full_log: str, job_name: str) -> str:
    """Extract the log section for a specific job from combined output.

    gh run view --log-failed prefixes lines with the job name, e.g.:
        test<tab>Run tests<tab>FAILED tests/test_foo.py::test_bar
    """
    if not full_log or not job_name:
        return ""

    lines = []
    in_job = False
    job_prefix = job_name.lower()

    for line in full_log.splitlines():
        # gh formats: "jobname\tstepname\toutput"
        parts = line.split("\t", 2)
        if len(parts) >= 2:
            line_job = parts[0].strip().lower()
            if line_job == job_prefix:
                in_job = True
                lines.append(parts[-1] if len(parts) == 3 else parts[1])
            elif in_job and line_job and line_job != job_prefix:
                # Moved to a different job section
                in_job = False
        elif in_job:
            lines.append(line)

    return "\n".join(lines)


if __name__ == "__main__":
    main()
