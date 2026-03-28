"""Daily orchestrator — runs all self-healing and maintenance steps.

Executes each step in sequence, tolerating individual failures.
Logs outcomes to daily_task_log for the scheduled task to inspect.

Usage:
    python3 -m mandarin.intelligence.daily_run --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, date, UTC
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _ensure_log_table(conn) -> None:
    """Create daily_task_log if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_task_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL DEFAULT (date('now')),
            step_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'running', 'ok', 'partial', 'failed', 'skipped')),
            started_at TEXT,
            finished_at TEXT,
            summary TEXT,
            details TEXT
        )
    """)
    conn.commit()


def _log_step(conn, step_name: str, status: str, summary: str, details: str = "") -> None:
    """Record a step outcome."""
    conn.execute("""
        INSERT INTO daily_task_log (step_name, status, finished_at, summary, details)
        VALUES (?, ?, datetime('now'), ?, ?)
    """, (step_name, status, summary, details))
    conn.commit()


def step_self_healing(conn, verbose: bool) -> tuple[str, str]:
    """Step 1: Run the self-healing health check."""
    try:
        from .self_healing import run_health_check
        result = run_health_check(conn)
        actions = result.get("actions_taken", [])
        if actions:
            return "ok", f"{len(actions)} remediation actions taken"
        return "ok", "System healthy, no actions needed"
    except Exception as exc:
        return "failed", f"Self-healing error: {exc}"


def step_intelligence_audit(conn, verbose: bool) -> tuple[str, str]:
    """Step 2: Run the product intelligence audit."""
    try:
        from . import run_product_audit
        result = run_product_audit(conn)
        findings = result.get("findings", [])
        new_count = len([f for f in findings if f.get("severity") in ("critical", "high")])
        return "ok", f"{len(findings)} findings ({new_count} critical/high)"
    except Exception as exc:
        return "failed", f"Intelligence audit error: {exc}"


def step_auto_fix(conn, verbose: bool) -> tuple[str, str]:
    """Step 3: Execute auto-fixes for deterministic findings."""
    try:
        from .auto_executor import execute_auto_fixes, EXECUTOR_ENABLED
        if not EXECUTOR_ENABLED:
            return "skipped", "AUTO_FIX_ENABLED is false"
        results = execute_auto_fixes(conn)
        applied = [r for r in results if r.get("status") == "applied"]
        return "ok", f"{len(applied)}/{len(results)} fixes applied"
    except Exception as exc:
        return "failed", f"Auto-fix error: {exc}"


def step_tests(conn, verbose: bool) -> tuple[str, str]:
    """Step 4: Run the test suite."""
    try:
        cmd = [
            sys.executable, "-m", "pytest", "tests/",
            "--ignore=tests/e2e", "-x", "--tb=short", "-q",
            "--timeout=120",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode == 0:
            return "ok", "All tests passed"
        return "partial", f"Tests failed (exit {result.returncode})"
    except subprocess.TimeoutExpired:
        return "partial", "Test suite timed out after 5 minutes"
    except Exception as exc:
        return "failed", f"Test runner error: {exc}"


def step_lint(conn, verbose: bool) -> tuple[str, str]:
    """Step 5: Run ruff lint check."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "."],
            capture_output=True, text=True, timeout=60,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode == 0:
            return "ok", "Lint clean"
        lines = result.stdout.strip().split("\n")
        return "partial", f"{len(lines)} lint issues"
    except Exception as exc:
        return "failed", f"Lint error: {exc}"


def step_email_digest(conn, verbose: bool) -> tuple[str, str]:
    """Step 6: Send the daily intelligence email digest."""
    try:
        from ..email import send_daily_intelligence_digest
        sent = send_daily_intelligence_digest(conn)
        if sent:
            return "ok", "Daily digest sent"
        return "ok", "No digest needed (no findings)"
    except Exception as exc:
        return "failed", f"Email digest error: {exc}"


def run_daily(verbose: bool = False) -> dict:
    """Run all daily steps, tolerating individual failures."""
    from ..db.core import ensure_db

    conn = ensure_db()
    _ensure_log_table(conn)

    steps = [
        ("self_healing", step_self_healing),
        ("intelligence_audit", step_intelligence_audit),
        ("auto_fix", step_auto_fix),
        ("tests", step_tests),
        ("lint", step_lint),
        ("email_digest", step_email_digest),
    ]

    results = {}
    for name, func in steps:
        if verbose:
            print(f"  [{name}] running...")
        t0 = time.monotonic()
        try:
            status, summary = func(conn, verbose)
        except Exception as exc:
            status, summary = "failed", str(exc)
        elapsed = round(time.monotonic() - t0, 1)

        if verbose:
            print(f"  [{name}] {status} ({elapsed}s): {summary}")

        _log_step(conn, name, status, summary)
        results[name] = {"status": status, "summary": summary, "elapsed_s": elapsed}

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Aelu daily orchestrator")
    parser.add_argument("--verbose", action="store_true", help="Print step progress")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    print(f"Aelu daily run — {date.today()}")
    results = run_daily(verbose=args.verbose)

    # Summary
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    failed = sum(1 for r in results.values() if r["status"] == "failed")
    print(f"\nDone: {ok} ok, {failed} failed, {len(results) - ok - failed} other")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
