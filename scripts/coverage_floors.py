#!/usr/bin/env python3
"""Risk-weighted coverage floors — enforce minimum coverage on critical packages.

Each entry defines a package path and minimum coverage percentage.
Run after pytest --cov to verify floors are met. Exits non-zero on failure.

Usage:
    pytest tests/ --cov=mandarin --cov-report=json
    python scripts/coverage_floors.py
"""

import json
import sys
from pathlib import Path

# Risk-weighted coverage floors: package → minimum coverage %
# These target real user-facing logic, not just infra.
# Ratchet upward as coverage improves — never lower these.
FLOORS = {
    "mandarin/drills": 36,      # Drill logic — user-facing, currently 37%
    "mandarin/web": 48,         # Web routes + bridge — user-facing, currently 49%
    "mandarin/db": 70,          # Database layer — data integrity, currently 72%
    "mandarin/auth.py": 95,     # Auth — security-critical, currently 100%
    "mandarin/jwt_auth.py": 95, # JWT — security-critical, currently 100%
    "mandarin/mfa.py": 95,      # MFA — security-critical, currently 100%
    "mandarin/security.py": 88, # Security events — critical, currently 91%
    "mandarin/scheduler.py": 75,# Scheduler — core learning algorithm, currently 77%
    "mandarin/conversation.py": 88, # Conversation — user-facing, currently 90%
    "mandarin/experiments": 70,     # A/B testing — product-critical (package, not monolithic)
    "mandarin/retention.py": 80,    # Retention model — core learning, wilson_ci tested
}


def main():
    cov_file = Path("coverage.json")
    if not cov_file.exists():
        print("ERROR: coverage.json not found. Run: pytest --cov=mandarin --cov-report=json")
        return 1

    data = json.loads(cov_file.read_text())
    files = data.get("files", {})

    failures = []
    for package, floor in FLOORS.items():
        # Aggregate coverage for all files in this package
        total_stmts = 0
        total_miss = 0
        for filepath, info in files.items():
            if filepath == package or filepath.startswith(package + "/"):
                summary = info.get("summary", {})
                total_stmts += summary.get("num_statements", 0)
                total_miss += summary.get("missing_lines", 0)

        if total_stmts == 0:
            print(f"  SKIP {package}: no statements found")
            continue

        covered = total_stmts - total_miss
        pct = round(covered / total_stmts * 100, 1)

        if pct < floor:
            failures.append((package, pct, floor))
            print(f"  FAIL {package}: {pct}% < {floor}% floor")
        else:
            print(f"  PASS {package}: {pct}% >= {floor}% floor")

    if failures:
        print(f"\n{len(failures)} coverage floor(s) not met.")
        return 1

    print("\nAll coverage floors met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
