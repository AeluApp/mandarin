"""Daily self-healing orchestrator — runs all maintenance steps in-process.

Usage:
    python3 -m mandarin.intelligence.daily_run [--verbose]

Each step is wrapped in try/except so one failure does not block the rest.
Results are written to daily_task_log for the email digest to read.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import traceback
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# daily_task_log table
# ---------------------------------------------------------------------------

_CREATE_TASK_LOG = """\
CREATE TABLE IF NOT EXISTS daily_task_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL DEFAULT (date('now')),
    step_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success','partial','failed','skipped')),
    summary TEXT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def _log_step(conn, step_name: str, status: str, summary: str = "",
              details: str = "") -> None:
    """Insert a row into daily_task_log."""
    try:
        conn.execute(
            "INSERT INTO daily_task_log (step_name, status, summary, details) "
            "VALUES (?, ?, ?, ?)",
            (step_name, status, summary, details),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("Could not log step %s: %s", step_name, exc)


# ---------------------------------------------------------------------------
# Individual steps
# ---------------------------------------------------------------------------

def _step_self_healing(conn) -> dict:
    """Step 1: Run the self-healing loop (local Ollama only, no metered API)."""
    from .self_healing import run_self_healing_loop
    result = run_self_healing_loop(conn)
    total = result.get("total_actions", 0)
    errors = len(result.get("errors", []))
    if errors:
        return {
            "status": "partial",
            "summary": f"{total} actions, {errors} errors",
            "details": "\n".join(result.get("errors", [])),
        }
    return {
        "status": "success",
        "summary": f"{total} actions taken, {result.get('total_issues', 0)} issues found",
    }


def _step_owner_modified_findings(conn) -> dict:
    """Step 2: Check for owner-modified findings that need follow-up."""
    try:
        rows = conn.execute(
            "SELECT id, title, dimension FROM pi_finding WHERE status = 'owner_modified'"
        ).fetchall()
    except Exception:
        rows = []

    if not rows:
        return {"status": "success", "summary": "No owner-modified findings"}

    lines = []
    for r in rows:
        lines.append(f"  #{r['id']} [{r['dimension'] or '?'}] {r['title'] or 'Untitled'}")
    detail_text = "\n".join(lines)
    print(f"\nOwner-modified findings ({len(rows)}):")
    print(detail_text)
    return {
        "status": "success",
        "summary": f"{len(rows)} owner-modified findings",
        "details": detail_text,
    }


def _step_tests(conn) -> dict:
    """Step 3: Run the test suite (excluding e2e tests)."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "--ignore=tests/e2e",
             "-x", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "summary": "Test suite timed out after 300s"}
    except FileNotFoundError:
        return {"status": "skipped", "summary": "pytest not found"}

    passed = "passed" in result.stdout
    output = (result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.returncode == 0:
        return {"status": "success", "summary": "All tests passed", "details": output}
    return {
        "status": "failed" if not passed else "partial",
        "summary": f"Exit code {result.returncode}",
        "details": output + "\n" + result.stderr[-1000:] if result.stderr else output,
    }


def _step_lint(conn) -> dict:
    """Step 4: Run ruff linter with auto-fix."""
    try:
        result = subprocess.run(
            ["python3", "-m", "ruff", "check", "--fix", "."],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "summary": "Lint timed out after 60s"}
    except FileNotFoundError:
        return {"status": "skipped", "summary": "ruff not found"}

    output = (result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.returncode == 0:
        return {"status": "success", "summary": "No lint issues", "details": output}
    return {
        "status": "partial",
        "summary": f"Lint issues found (exit {result.returncode})",
        "details": output,
    }


def _step_intelligence_digest(conn) -> dict:
    """Step 5: Send the daily intelligence email digest."""
    from mandarin.email import send_daily_intelligence_digest
    ok = send_daily_intelligence_digest(conn)
    if ok:
        return {"status": "success", "summary": "Intelligence digest sent"}
    return {"status": "failed", "summary": "Intelligence digest send failed"}


def _step_openclaw_digest(conn) -> dict:
    """Step 6: Send OpenClaw daily digest via owner notification channel."""
    try:
        from mandarin.openclaw.commands import cmd_daily_digest
    except ImportError:
        return {"status": "skipped", "summary": "cmd_daily_digest not available yet"}

    try:
        digest_text = cmd_daily_digest()
    except Exception as exc:
        return {"status": "failed", "summary": f"cmd_daily_digest error: {exc}"}

    try:
        from mandarin.openclaw import notify_owner
        ok = notify_owner(digest_text)
    except Exception as exc:
        return {"status": "partial", "summary": f"Digest generated but notify failed: {exc}"}

    if ok:
        return {"status": "success", "summary": "OpenClaw digest sent"}
    return {
        "status": "partial",
        "summary": "Digest generated, no notification channel available",
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_STEPS = [
    ("Self-healing loop", _step_self_healing),
    ("Owner-modified findings", _step_owner_modified_findings),
    ("Test suite", _step_tests),
    ("Lint (ruff)", _step_lint),
    ("Intelligence digest", _step_intelligence_digest),
    ("OpenClaw digest", _step_openclaw_digest),
]


def run_all(conn, verbose: bool = False) -> list[dict]:
    """Execute every step, logging results to daily_task_log."""
    results = []
    for name, fn in _STEPS:
        logger.info("Running step: %s", name)
        try:
            result = fn(conn)
        except Exception as exc:
            tb = traceback.format_exc()
            result = {
                "status": "failed",
                "summary": str(exc)[:200],
                "details": tb,
            }
            logger.error("Step '%s' failed: %s", name, exc)

        result.setdefault("status", "failed")
        result.setdefault("summary", "")
        result.setdefault("details", "")
        results.append({"name": name, **result})

        _log_step(conn, name, result["status"], result["summary"], result["details"])

        if verbose:
            print(f"  [{result['status']:7s}] {name}: {result['summary']}")

    return results


def _print_summary(results: list[dict]) -> None:
    """Print a plain-English summary of the daily run."""
    auto_fixed = []
    needs_decision = []
    everything_ok = []

    for r in results:
        if r["status"] == "success":
            everything_ok.append(r)
        elif r["status"] in ("partial", "skipped"):
            needs_decision.append(r)
        else:
            needs_decision.append(r)

    # Also separate auto-fixed items from self-healing step
    for r in results:
        if r["name"] == "Self-healing loop" and r["status"] in ("success", "partial"):
            if "actions taken" in r.get("summary", "") and "0 actions" not in r.get("summary", ""):
                auto_fixed.append(r)
                if r in everything_ok:
                    everything_ok.remove(r)

    print()
    print("=" * 60)
    print("Daily Run Summary")
    print("=" * 60)

    if auto_fixed:
        print("\n**Auto-fixed (no action needed):**")
        for r in auto_fixed:
            print(f"  - {r['name']} -> {r['summary']}")

    if needs_decision:
        print("\n**Needs your decision:**")
        for r in needs_decision:
            print(f"  - {r['name']}: {r['summary']}")

    if everything_ok:
        print("\n**Everything OK:**")
        for r in everything_ok:
            print(f"  - {r['name']}: {r['summary']}")

    print()
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run the Aelu daily self-healing orchestrator",
        prog="python3 -m mandarin.intelligence.daily_run",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging and per-step output",
    )
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    logger.info("Starting daily run at %s", datetime.now(UTC).isoformat())

    # Get DB connection
    try:
        from mandarin.db.core import ensure_db
        conn = ensure_db()
    except Exception as exc:
        logger.error("Cannot connect to database: %s", exc)
        sys.exit(1)

    # Create daily_task_log table if it doesn't exist
    try:
        conn.executescript(_CREATE_TASK_LOG)
        conn.commit()
    except Exception as exc:
        logger.warning("Could not create daily_task_log table: %s", exc)

    try:
        results = run_all(conn, verbose=args.verbose)
        _print_summary(results)
    except Exception as exc:
        logger.exception("Daily run failed: %s", exc)
        sys.exit(1)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
