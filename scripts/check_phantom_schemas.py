#!/usr/bin/env python3
"""CI lint: detect unannotated inline CREATE TABLE statements in test files.

Test files should use the shared fixtures (test_db, light_db, make_test_db)
from tests/conftest.py or tests/shared_db.py instead of creating inline schemas.

Exceptions must be annotated with one of these markers (anywhere in the file
or within 30 lines above the CREATE TABLE):
  - "PHANTOM TABLE:" — table not yet in production schema (tracked debt)
  - "PHANTOM COLUMN:" — column not yet in production schema (tracked debt)
  - "Inline schemas are intentional" — legitimate use (migration tests, edge cases)
  - "# phantom-schema-checked" — file-level marker acknowledging all inline schemas

Usage:
    python scripts/check_phantom_schemas.py
"""

import re
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent.parent / "tests"

CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE", re.IGNORECASE)

# File-level marker that suppresses all violations in the file
FILE_LEVEL_MARKER = "# phantom-schema-checked"

# Per-occurrence markers (checked within 30 lines above the CREATE TABLE)
EXCEPTION_MARKERS = [
    "PHANTOM TABLE:",
    "PHANTOM COLUMN:",
    "Inline schemas are intentional",
    "phantom-schema-checked",
]


def check_file(path: Path) -> list[str]:
    """Return list of violation messages for a single test file."""
    if path.name in ("conftest.py", "shared_db.py"):
        return []

    text = path.read_text(encoding="utf-8")

    # File-level suppression
    if FILE_LEVEL_MARKER in text:
        return []

    violations = []
    lines = text.splitlines()

    for i, line in enumerate(lines, 1):
        if CREATE_TABLE_RE.search(line):
            # Check surrounding context (30 lines above) for exception markers
            context_start = max(0, i - 31)
            context = "\n".join(lines[context_start : i])
            if any(marker in context for marker in EXCEPTION_MARKERS):
                continue
            violations.append(
                f"  {path.relative_to(TESTS_DIR.parent)}:{i}: "
                f"Unannotated CREATE TABLE — use make_test_db() or annotate exception"
            )

    return violations


def main():
    all_violations = []
    for py_file in sorted(TESTS_DIR.glob("test_*.py")):
        all_violations.extend(check_file(py_file))

    if all_violations:
        print("Phantom schema violations found:\n")
        for v in all_violations:
            print(v)
        print(f"\n{len(all_violations)} violation(s). "
              "Use make_test_db() or annotate with PHANTOM TABLE: / "
              "Inline schemas are intentional / # phantom-schema-checked")
        return 1

    print("No phantom schema violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
