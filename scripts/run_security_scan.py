#!/usr/bin/env python3
"""Run bandit static security scan and persist results to security_scan_finding table.

Usage:
    python scripts/run_security_scan.py [--db PATH] [--no-fail]

Exit codes:
    0  — no HIGH-severity findings (medium/low findings still written to DB)
    1  — one or more HIGH-severity findings (CI blocking)
    2  — bandit not installed or unexpected error
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DEFAULT_DB = _ROOT / "data" / "mandarin.db"
_SCAN_TARGET = str(_ROOT / "mandarin")


def _run_bandit() -> tuple[list[dict], str]:
    """Run bandit and return (results, raw_json_output)."""
    cmd = [
        sys.executable, "-m", "bandit",
        "-r", _SCAN_TARGET,
        "-f", "json",
        "-ll",           # Report medium + high severity only
        "--quiet",
        "--exit-zero",   # Don't let bandit's exit code interfere; we handle it
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = result.stdout or result.stderr or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # bandit may output warnings before JSON; try to find the JSON block
        start = raw.find("{")
        if start >= 0:
            data = json.loads(raw[start:])
        else:
            raise RuntimeError(f"bandit produced non-JSON output:\n{raw[:500]}")
    return data.get("results", []), raw


def _persist(db_path: Path, results: list[dict], duration_s: float) -> int:
    """Insert scan + findings into DB. Returns count of HIGH findings."""
    if not db_path.exists():
        print(f"[security-scan] DB not found at {db_path} — skipping persistence")
        return 0

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create the scan record
    cur = conn.execute(
        "INSERT INTO security_scan (scan_type, started_at, completed_at, status, summary, duration_seconds) "
        "VALUES ('bandit', datetime('now'), datetime('now'), 'complete', ?, ?)",
        (f"{len(results)} findings", int(duration_s)),
    )
    scan_id = cur.lastrowid

    high_count = 0
    for r in results:
        sev = r.get("issue_severity", "LOW").lower()
        if sev == "high":
            high_count += 1
        conn.execute(
            "INSERT INTO security_scan_finding "
            "(scan_id, severity, category, title, description, file_path, line_number) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                scan_id,
                sev,
                r.get("test_name", "unknown"),
                r.get("issue_text", ""),
                r.get("more_info", ""),
                # Store path relative to project root
                os.path.relpath(r.get("filename", ""), str(_ROOT)),
                r.get("line_number"),
            ),
        )

    conn.commit()
    conn.close()
    return high_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bandit security scan")
    parser.add_argument("--db", default=str(_DEFAULT_DB), help="Path to SQLite DB")
    parser.add_argument("--no-fail", action="store_true",
                        help="Exit 0 even if HIGH findings exist (informational mode)")
    args = parser.parse_args()

    # Verify bandit is installed
    try:
        subprocess.run(
            [sys.executable, "-m", "bandit", "--version"],
            capture_output=True, check=True,
        )
    except subprocess.CalledProcessError:
        print("[security-scan] ERROR: bandit not installed. Run: pip install bandit")
        return 2

    print(f"[security-scan] Scanning {_SCAN_TARGET} ...")
    t0 = time.monotonic()

    try:
        results, _ = _run_bandit()
    except RuntimeError as exc:
        print(f"[security-scan] ERROR: {exc}")
        return 2

    duration = time.monotonic() - t0

    high = [r for r in results if r.get("issue_severity", "").upper() == "HIGH"]
    med  = [r for r in results if r.get("issue_severity", "").upper() == "MEDIUM"]

    print(f"[security-scan] Done in {duration:.1f}s — "
          f"{len(results)} findings: {len(high)} HIGH, {len(med)} MEDIUM")

    high_count = _persist(Path(args.db), results, duration)

    if high_count > 0:
        print(f"[security-scan] {high_count} HIGH-severity finding(s):")
        for r in high:
            rel = os.path.relpath(r.get("filename", ""), str(_ROOT))
            print(f"  [{r['test_id']}] {r['issue_text']}  ({rel}:{r['line_number']})")
        if not args.no_fail:
            print("[security-scan] FAIL — resolve HIGH findings or annotate with # nosec")
            return 1

    print("[security-scan] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
