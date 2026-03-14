#!/usr/bin/env python3
"""Check for documentation drift — verifies BUILD_STATE.md and SECURITY.md
match the actual schema version and table count in the codebase.

Exit 0 if everything matches, exit 1 if any mismatch found.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ERRORS: list[str] = []


def extract_schema_version() -> int:
    """Read SCHEMA_VERSION from mandarin/db/core.py."""
    core_py = ROOT / "mandarin" / "db" / "core.py"
    text = core_py.read_text()
    match = re.search(r"^SCHEMA_VERSION\s*=\s*(\d+)", text, re.MULTILINE)
    if not match:
        ERRORS.append("Could not find SCHEMA_VERSION in mandarin/db/core.py")
        return -1
    return int(match.group(1))


def count_tables_in_schema() -> int:
    """Count CREATE TABLE statements in schema.sql."""
    schema_sql = ROOT / "schema.sql"
    if not schema_sql.exists():
        ERRORS.append("schema.sql not found at repo root")
        return -1
    text = schema_sql.read_text()
    return len(re.findall(r"CREATE TABLE", text, re.IGNORECASE))


def check_build_state(schema_version: int, table_count: int) -> None:
    """Verify BUILD_STATE.md references the correct schema version and table count."""
    build_state = ROOT / "BUILD_STATE.md"
    if not build_state.exists():
        ERRORS.append("BUILD_STATE.md not found at repo root")
        return
    text = build_state.read_text()

    # Check schema version — look for patterns like "V42", "Schema V42",
    # "**Schema:** V42", "Schema (43 tables, V28)", "SCHEMA_VERSION=42"
    version_matches = re.findall(
        r"Schema[:\s*]+\s*V(\d+)|SCHEMA_VERSION\s*=\s*(\d+)|Schema\s*\(\d+\s+tables,\s*V(\d+)\)",
        text,
    )
    if not version_matches:
        ERRORS.append("BUILD_STATE.md does not mention any schema version")
    else:
        # Flatten matches (re.findall with groups returns tuples)
        found_versions = set()
        for groups in version_matches:
            for g in groups:
                if g:
                    found_versions.add(int(g))
        if schema_version not in found_versions:
            ERRORS.append(
                f"BUILD_STATE.md mentions schema version(s) {found_versions} "
                f"but actual SCHEMA_VERSION is {schema_version}"
            )

    # Check table count — look for patterns like "56 tables" or "(56 tables"
    table_matches = re.findall(r"(\d+)\s+tables", text)
    if not table_matches:
        ERRORS.append("BUILD_STATE.md does not mention a table count")
    else:
        found_counts = {int(m) for m in table_matches}
        if table_count not in found_counts:
            ERRORS.append(
                f"BUILD_STATE.md mentions table count(s) {found_counts} "
                f"but schema.sql has {table_count} tables"
            )


def check_security_md(schema_version: int) -> None:
    """Verify SECURITY.md references the correct schema version."""
    security_md = ROOT / "SECURITY.md"
    if not security_md.exists():
        ERRORS.append("SECURITY.md not found at repo root")
        return
    text = security_md.read_text()

    version_matches = re.findall(r"Schema V(\d+)|V\d+\s*\(Schema V(\d+)\)", text)
    if not version_matches:
        ERRORS.append("SECURITY.md does not mention any schema version")
    else:
        found_versions = set()
        for groups in version_matches:
            for g in groups:
                if g:
                    found_versions.add(int(g))
        if schema_version not in found_versions:
            ERRORS.append(
                f"SECURITY.md mentions schema version(s) {found_versions} "
                f"but actual SCHEMA_VERSION is {schema_version}"
            )


def main() -> int:
    schema_version = extract_schema_version()
    table_count = count_tables_in_schema()

    if schema_version > 0 or table_count > 0:
        check_build_state(schema_version, table_count)
    if schema_version > 0:
        check_security_md(schema_version)

    if ERRORS:
        # Deduplicate
        seen = set()
        for err in ERRORS:
            if err not in seen:
                print(f"FAIL: {err}")
                seen.add(err)
        return 1

    print(
        f"OK: schema version V{schema_version}, "
        f"{table_count} tables — docs match"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
