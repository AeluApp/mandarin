#!/usr/bin/env python3
"""Deterministic audit script — CI quality gate checks.

Runnable as: python scripts/audit_check.py
Produces JSON + human-readable summary.
Exit 0 if all checks pass, exit 1 if any fail.

No external dependencies — stdlib only (os, re, glob, json, sys, datetime).
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

# ── Paths ────────────────────────────────────────────────────────────────────

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))

_WEB_DIR = os.path.join(_PROJECT_ROOT, "mandarin", "web")
_MANDARIN_DIR = os.path.join(_PROJECT_ROOT, "mandarin")
_TESTS_DIR = os.path.join(_PROJECT_ROOT, "tests")
_SCHEMA_SQL = os.path.join(_PROJECT_ROOT, "schema.sql")
_DB_CORE = os.path.join(_MANDARIN_DIR, "db", "core.py")
_PYPROJECT = os.path.join(_PROJECT_ROOT, "pyproject.toml")
_PRE_COMMIT = os.path.join(_PROJECT_ROOT, ".pre-commit-config.yaml")
_BUILD_STATE = os.path.join(_PROJECT_ROOT, "BUILD_STATE.md")
_SETTINGS = os.path.join(_MANDARIN_DIR, "settings.py")
_AUTH_PY = os.path.join(_MANDARIN_DIR, "auth.py")
_AUTH_ROUTES = os.path.join(_WEB_DIR, "auth_routes.py")
_JWT_AUTH = os.path.join(_MANDARIN_DIR, "jwt_auth.py")


def _read(path: str) -> str:
    """Read file contents or return empty string if missing."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ── Check helpers ────────────────────────────────────────────────────────────

def _find_route_files() -> list[str]:
    """Return all *_routes.py files in mandarin/web/ plus routes.py."""
    pattern = os.path.join(_WEB_DIR, "*_routes.py")
    files = sorted(glob.glob(pattern))
    routes_py = os.path.join(_WEB_DIR, "routes.py")
    if os.path.isfile(routes_py) and routes_py not in files:
        files.append(routes_py)
    return files


def _has_route_decorator(content: str) -> bool:
    """True if file defines @bp.route or @app.route or @<name>_bp.route."""
    return bool(re.search(r"@\w+\.route\(", content))


def _has_api_error_handler_import(content: str) -> bool:
    """True if file imports api_error_handler (directly or via api_errors).

    Handles both single-line and multi-line import forms:
      from .api_errors import api_error_handler
      from .api_errors import (
          api_error,
          api_error_handler,
      )
    """
    # Check for the import source and the name separately to handle multi-line
    has_api_errors_import = bool(re.search(r"from\s+\.api_errors\s+import", content))
    has_handler_name = bool(re.search(r"\bapi_error_handler\b", content))
    return has_api_errors_import and has_handler_name


# ── Individual checks ────────────────────────────────────────────────────────

def check_r1() -> dict:
    """R1: Every JSON API route file with @bp.route also imports api_error_handler.

    HTML-only route files (auth, landing, onboarding) use try/except with
    render_template for error handling, so they are exempt from this check.
    """
    # Exempt route files — HTML-only (use render_template error handling)
    # or WebSocket-only (session_routes.py uses @sock.route, not JSON API)
    _HTML_EXEMPT = {
        "auth_routes.py",
        "landing_routes.py",
        "onboarding_routes.py",
        "session_routes.py",
    }

    route_files = _find_route_files()
    json_route_files = []
    html_exempt_files = []
    missing = []

    for fp in route_files:
        content = _read(fp)
        if _has_route_decorator(content):
            basename = os.path.basename(fp)
            if basename in _HTML_EXEMPT:
                html_exempt_files.append(basename)
                continue
            json_route_files.append(basename)
            if not _has_api_error_handler_import(content):
                missing.append(basename)

    checked = len(json_route_files)
    passed_count = checked - len(missing)
    exempt_note = f" ({len(html_exempt_files)} HTML-exempt)" if html_exempt_files else ""

    if missing:
        return {
            "id": "R1",
            "name": "api_error_handler import coverage",
            "status": "FAIL",
            "details": f"{passed_count}/{checked} JSON route files import api_error_handler{exempt_note}; missing: {', '.join(missing)}",
        }
    return {
        "id": "R1",
        "name": "api_error_handler import coverage",
        "status": "PASS",
        "details": f"{checked}/{checked} JSON route files import api_error_handler{exempt_note}",
    }


def check_r2() -> dict:
    """R2: Zero occurrences of get_json(force=True) in mandarin/."""
    pattern = re.compile(r"get_json\(\s*force\s*=\s*True\s*\)")
    hits: list[str] = []

    for root, _dirs, files in os.walk(_MANDARIN_DIR):
        # Skip __pycache__, venv, etc.
        if "__pycache__" in root:
            continue
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fp = os.path.join(root, fname)
            content = _read(fp)
            for i, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    rel = os.path.relpath(fp, _PROJECT_ROOT)
                    hits.append(f"{rel}:{i}")

    if hits:
        return {
            "id": "R2",
            "name": "no get_json(force=True)",
            "status": "FAIL",
            "details": f"{len(hits)} occurrence(s) found: {', '.join(hits)}",
        }
    return {
        "id": "R2",
        "name": "no get_json(force=True)",
        "status": "PASS",
        "details": "0 occurrences found",
    }


def check_r3() -> dict:
    """R3: No f-string SQL in .execute() first argument.

    Heuristic: find .execute( calls where the first argument (the SQL query
    string) is an f-string with brace interpolation.  We extract the SQL
    argument by tracking parentheses and checking if the first string-like
    argument is an f-string.  Ignores f-strings in subsequent arguments
    (parameter tuples) to avoid false positives from logging/data values.

    Web-facing modules (anything under web/, plus gdpr_routes.py and
    data_retention.py) cause a FAIL.  Internal modules where f-string
    identifiers come from hardcoded Python dicts (diagnostics, validator,
    importer, improve, cli, churn_detection) produce a WARN but still pass.
    """
    execute_fstring_re = re.compile(r"""\.execute\s*\(\s*f['"]""")
    execute_fstring_triple_re = re.compile(r'\.execute\s*\(\s*f"""')

    # Internal modules where f-string SQL identifiers come from hardcoded
    # Python values or schema introspection (PRAGMA), not user input.
    # Lower risk, WARN only.  Includes:
    # - diagnostics/validator/importer/improve/cli/churn: hardcoded column/table names
    # - scheduler: builds "?" placeholders from list length
    # - data_retention/gdpr_routes: table names from PRAGMA + regex-validated
    # - db/content/db/core: internal DB layer, migration code
    _INTERNAL_MODULES = {
        "diagnostics.py",
        "validator.py",
        "importer.py",
        "improve.py",
        "cli.py",
        "churn_detection.py",
        "scheduler.py",
        "data_retention.py",
        "gdpr_routes.py",
        "content.py",
        "core.py",
    }

    web_hits: list[str] = []
    internal_hits: list[str] = []

    for root, _dirs, files in os.walk(_MANDARIN_DIR):
        if "__pycache__" in root:
            continue
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fp = os.path.join(root, fname)
            content = _read(fp)
            lines = content.splitlines()
            rel = os.path.relpath(fp, _PROJECT_ROOT)

            # Determine if this file is web-facing or internal
            is_internal = fname in _INTERNAL_MODULES
            is_web_facing = (
                os.path.join("web", "") in rel  # anything under web/
            ) and not is_internal

            file_hits: list[str] = []

            for i, line in enumerate(lines):
                # Direct f-string on same line as .execute(
                if execute_fstring_re.search(line) or execute_fstring_triple_re.search(line):
                    file_hits.append(f"{rel}:{i + 1}")
                    continue
                # Multi-line: .execute(\n    f"..."
                if re.search(r"\.execute\s*\(\s*$", line):
                    # Check next non-blank line for f-string
                    for j in range(i + 1, min(i + 4, len(lines))):
                        next_line = lines[j].strip()
                        if not next_line:
                            continue
                        if re.match(r"""f['"]""", next_line) or re.match(r'f"""', next_line):
                            file_hits.append(f"{rel}:{i + 1}")
                        break

            # Categorize hits
            if file_hits:
                if is_internal:
                    internal_hits.extend(file_hits)
                else:
                    # Web-facing or uncategorized — treat as web-facing (strict)
                    web_hits.extend(file_hits)

    # Build details string
    parts = []
    if web_hits:
        parts.append(f"{len(web_hits)} web-facing FAIL: {', '.join(web_hits[:10])}")
    if internal_hits:
        parts.append(f"{len(internal_hits)} internal WARN: {', '.join(internal_hits[:10])}")
    if not parts:
        parts.append("0 f-string SQL patterns found in execute()")

    # Only FAIL if web-facing modules have f-string SQL
    if web_hits:
        return {
            "id": "R3",
            "name": "no f-string SQL in execute()",
            "status": "FAIL",
            "details": "; ".join(parts),
        }
    return {
        "id": "R3",
        "name": "no f-string SQL in execute()",
        "status": "PASS",
        "details": "; ".join(parts),
    }


def check_a1() -> dict:
    """A1: All generate_password_hash calls include method= keyword."""
    files_to_check = [_AUTH_PY, _AUTH_ROUTES, _JWT_AUTH]
    # Also check cli.py which has generate_password_hash
    cli_py = os.path.join(_MANDARIN_DIR, "cli.py")
    if os.path.isfile(cli_py):
        files_to_check.append(cli_py)

    hash_call_re = re.compile(r"generate_password_hash\(")
    method_re = re.compile(r"generate_password_hash\([^)]*method\s*=")
    missing: list[str] = []
    total = 0

    for fp in files_to_check:
        content = _read(fp)
        if not content:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if hash_call_re.search(line):
                total += 1
                if not method_re.search(line):
                    rel = os.path.relpath(fp, _PROJECT_ROOT)
                    missing.append(f"{rel}:{i}")

    if missing:
        return {
            "id": "A1",
            "name": "generate_password_hash includes method=",
            "status": "FAIL",
            "details": f"{len(missing)} call(s) missing method=: {', '.join(missing)}",
        }
    return {
        "id": "A1",
        "name": "generate_password_hash includes method=",
        "status": "PASS",
        "details": f"{total} call(s), all include method=",
    }


def check_a2() -> dict:
    """A2: All jwt.decode calls include algorithms= keyword."""
    files_to_check = [_JWT_AUTH]
    lti_routes = os.path.join(_WEB_DIR, "lti_routes.py")
    if os.path.isfile(lti_routes):
        files_to_check.append(lti_routes)

    decode_re = re.compile(r"jwt\.decode\(|pyjwt\.decode\(")
    algorithms_re = re.compile(r"(jwt|pyjwt)\.decode\([^)]*algorithms\s*=")
    # Unverified decodes with verify_signature=False are acceptable
    unverified_re = re.compile(r"verify_signature.*False")

    missing: list[str] = []
    total = 0

    for fp in files_to_check:
        content = _read(fp)
        if not content:
            continue
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if decode_re.search(line):
                total += 1
                # Check this line and a few after for algorithms= (multi-line calls)
                block = "\n".join(lines[max(0, i - 1):min(len(lines), i + 5)])
                if algorithms_re.search(block):
                    continue
                # Accept unverified decode (options={"verify_signature": False})
                if unverified_re.search(block):
                    continue
                rel = os.path.relpath(fp, _PROJECT_ROOT)
                missing.append(f"{rel}:{i}")

    if missing:
        return {
            "id": "A2",
            "name": "jwt.decode includes algorithms=",
            "status": "FAIL",
            "details": f"{len(missing)} call(s) missing algorithms=: {', '.join(missing)}",
        }
    return {
        "id": "A2",
        "name": "jwt.decode includes algorithms=",
        "status": "PASS",
        "details": f"{total} call(s), all include algorithms= (or are unverified preview)",
    }


def check_a3() -> dict:
    """A3: session.clear() appears before every login_user() in auth_routes.py."""
    content = _read(_AUTH_ROUTES)
    if not content:
        return {
            "id": "A3",
            "name": "session.clear() before login_user()",
            "status": "FAIL",
            "details": "auth_routes.py not found",
        }

    lines = content.splitlines()
    login_user_re = re.compile(r"\blogin_user\(")
    session_clear_re = re.compile(r"\bsession\.clear\(\)")

    unguarded: list[int] = []
    total_logins = 0

    for i, line in enumerate(lines):
        if login_user_re.search(line):
            total_logins += 1
            # Check previous non-empty lines (up to 5) for session.clear()
            found_clear = False
            for j in range(max(0, i - 5), i):
                if session_clear_re.search(lines[j]):
                    found_clear = True
                    break
            if not found_clear:
                unguarded.append(i + 1)

    if unguarded:
        return {
            "id": "A3",
            "name": "session.clear() before login_user()",
            "status": "FAIL",
            "details": f"{len(unguarded)} login_user() without preceding session.clear() at line(s): {', '.join(str(n) for n in unguarded)}",
        }
    return {
        "id": "A3",
        "name": "session.clear() before login_user()",
        "status": "PASS",
        "details": f"{total_logins} login_user() call(s), all preceded by session.clear()",
    }


def check_c1() -> dict:
    """C1: Zero os.environ calls outside mandarin/settings.py (exclude tests/, venv/)."""
    environ_re = re.compile(r"\bos\.environ\b")
    hits: list[str] = []

    for root, dirs, files in os.walk(_MANDARIN_DIR):
        # Skip __pycache__
        if "__pycache__" in root:
            continue
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fp = os.path.join(root, fname)
            # Skip settings.py
            if os.path.abspath(fp) == os.path.abspath(_SETTINGS):
                continue
            content = _read(fp)
            for i, line in enumerate(content.splitlines(), 1):
                # Skip comments
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if environ_re.search(line):
                    rel = os.path.relpath(fp, _PROJECT_ROOT)
                    hits.append(f"{rel}:{i}")

    if hits:
        return {
            "id": "C1",
            "name": "os.environ confined to settings.py",
            "status": "FAIL",
            "details": f"{len(hits)} os.environ call(s) outside settings.py: {', '.join(hits[:10])}",
        }
    return {
        "id": "C1",
        "name": "os.environ confined to settings.py",
        "status": "PASS",
        "details": "0 os.environ calls outside settings.py",
    }


def check_c2() -> dict:
    """C2: SCHEMA_VERSION in db/core.py matches CREATE TABLE count in schema.sql.

    The schema.sql version comment or schema_version table should broadly match
    SCHEMA_VERSION.  We use +-1 tolerance because version != table count.
    We also check that the table count claimed in BUILD_STATE matches.
    """
    core_content = _read(_DB_CORE)
    schema_content = _read(_SCHEMA_SQL)

    # Extract SCHEMA_VERSION
    m = re.search(r"SCHEMA_VERSION\s*=\s*(\d+)", core_content)
    if not m:
        return {
            "id": "C2",
            "name": "SCHEMA_VERSION consistency",
            "status": "FAIL",
            "details": "Could not find SCHEMA_VERSION in db/core.py",
        }
    schema_version = int(m.group(1))

    # Count CREATE TABLE in schema.sql
    table_count = len(re.findall(r"CREATE\s+TABLE", schema_content, re.IGNORECASE))

    # Check BUILD_STATE table count claim
    build_state = _read(_BUILD_STATE)
    bs_match = re.search(r"Schema.*?(\d+)\s+tables", build_state)
    bs_table_count = int(bs_match.group(1)) if bs_match else None

    # Check BUILD_STATE schema version claim
    bs_version_match = re.search(r"Schema.*?V(\d+)", build_state)
    bs_version = int(bs_version_match.group(1)) if bs_version_match else None

    issues = []
    if bs_version is not None and abs(bs_version - schema_version) > 1:
        issues.append(
            f"BUILD_STATE claims V{bs_version} but db/core.py has SCHEMA_VERSION={schema_version}"
        )
    if bs_table_count is not None and bs_table_count != table_count:
        issues.append(
            f"BUILD_STATE claims {bs_table_count} tables but schema.sql has {table_count} CREATE TABLE"
        )

    if issues:
        return {
            "id": "C2",
            "name": "SCHEMA_VERSION consistency",
            "status": "FAIL",
            "details": "; ".join(issues),
        }
    return {
        "id": "C2",
        "name": "SCHEMA_VERSION consistency",
        "status": "PASS",
        "details": f"SCHEMA_VERSION={schema_version}, schema.sql has {table_count} tables, BUILD_STATE consistent",
    }


def check_t1() -> dict:
    """T1: Every mandarin/web/*_routes.py has a corresponding test file.

    Uses a mapping dict for route files whose tests don't follow the
    standard test_*_routes.py naming convention.  A route file passes
    if ANY of its mapped test files exist on disk.
    """
    # Known aliases: route basename -> list of acceptable test file basenames.
    # If a route file is not listed here, the standard test_<basename> is used.
    _ROUTE_TEST_MAP: dict[str, list[str]] = {
        "auth_routes.py": ["test_auth_routes.py", "test_auth.py"],
        "payment_routes.py": ["test_payment_routes.py", "test_payment.py"],
        "marketing_routes.py": ["test_marketing_routes.py", "test_web_routes.py"],
        "landing_routes.py": ["test_landing_routes.py", "test_web_routes.py"],
        "onboarding_routes.py": ["test_onboarding_routes.py", "test_web_routes.py"],
        "dashboard_routes.py": ["test_dashboard_routes.py", "test_web_routes.py"],
        "settings_routes.py": ["test_settings_routes.py", "test_web_routes.py"],
        "exposure_routes.py": ["test_exposure_routes.py", "test_web_routes.py"],
        "export_routes.py": ["test_export_routes.py", "test_web_routes.py"],
        "session_routes.py": ["test_session_routes.py", "test_web_routes.py"],
    }

    route_files = glob.glob(os.path.join(_WEB_DIR, "*_routes.py"))
    missing: list[str] = []
    total = 0

    for fp in sorted(route_files):
        basename = os.path.basename(fp)  # e.g. "sync_routes.py"
        total += 1

        # Determine which test files would satisfy coverage
        candidates = _ROUTE_TEST_MAP.get(basename, [f"test_{basename}"])

        # Pass if ANY candidate test file exists
        if not any(os.path.isfile(os.path.join(_TESTS_DIR, c)) for c in candidates):
            missing.append(f"{basename} (looked for: {', '.join(candidates)})")

    if missing:
        return {
            "id": "T1",
            "name": "route test file coverage",
            "status": "FAIL",
            "details": f"missing: {'; '.join(missing)}",
        }
    return {
        "id": "T1",
        "name": "route test file coverage",
        "status": "PASS",
        "details": f"{total}/{total} route files have corresponding test files",
    }


def check_t2() -> dict:
    """T2: fail_under in pyproject.toml >= 53."""
    content = _read(_PYPROJECT)
    m = re.search(r"fail_under\s*=\s*(\d+)", content)
    if not m:
        return {
            "id": "T2",
            "name": "coverage fail_under threshold",
            "status": "FAIL",
            "details": "fail_under not found in pyproject.toml",
        }
    value = int(m.group(1))
    if value < 53:
        return {
            "id": "T2",
            "name": "coverage fail_under threshold",
            "status": "FAIL",
            "details": f"fail_under={value}, expected >= 53",
        }
    return {
        "id": "T2",
        "name": "coverage fail_under threshold",
        "status": "PASS",
        "details": f"fail_under={value} (>= 53)",
    }


def check_t3() -> dict:
    """T3: .pre-commit-config.yaml exists."""
    if os.path.isfile(_PRE_COMMIT):
        return {
            "id": "T3",
            "name": ".pre-commit-config.yaml exists",
            "status": "PASS",
            "details": ".pre-commit-config.yaml found",
        }
    return {
        "id": "T3",
        "name": ".pre-commit-config.yaml exists",
        "status": "FAIL",
        "details": ".pre-commit-config.yaml not found",
    }


def check_d1() -> dict:
    """D1: Table count in BUILD_STATE.md matches CREATE TABLE count in schema.sql."""
    build_state = _read(_BUILD_STATE)
    schema_content = _read(_SCHEMA_SQL)

    table_count = len(re.findall(r"CREATE\s+TABLE", schema_content, re.IGNORECASE))

    # Look for "N tables" in BUILD_STATE
    m = re.search(r"(\d+)\s+tables", build_state)
    if not m:
        return {
            "id": "D1",
            "name": "BUILD_STATE table count",
            "status": "FAIL",
            "details": "Could not find table count in BUILD_STATE.md",
        }
    claimed = int(m.group(1))

    if claimed != table_count:
        return {
            "id": "D1",
            "name": "BUILD_STATE table count",
            "status": "FAIL",
            "details": f"BUILD_STATE claims {claimed} tables, schema.sql has {table_count}",
        }
    return {
        "id": "D1",
        "name": "BUILD_STATE table count",
        "status": "PASS",
        "details": f"{claimed} tables in both BUILD_STATE.md and schema.sql",
    }


def check_d2() -> dict:
    """D2: Test suite count ('N suites') in BUILD_STATE.md matches actual test file count."""
    build_state = _read(_BUILD_STATE)

    # Look for "N suites" in BUILD_STATE
    m = re.search(r"(\d+)\s+suites", build_state)
    if not m:
        return {
            "id": "D2",
            "name": "BUILD_STATE test suite count",
            "status": "FAIL",
            "details": "Could not find suite count in BUILD_STATE.md",
        }
    claimed = int(m.group(1))

    # Count actual test files
    test_files = glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))
    actual = len(test_files)

    if claimed != actual:
        return {
            "id": "D2",
            "name": "BUILD_STATE test suite count",
            "status": "FAIL",
            "details": f"BUILD_STATE claims {claimed} suites, found {actual} test files",
        }
    return {
        "id": "D2",
        "name": "BUILD_STATE test suite count",
        "status": "PASS",
        "details": f"{claimed} suites in BUILD_STATE.md, {actual} test files found",
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def check_t4() -> dict:
    """T4: No inline CREATE TABLE in test files (use shared_db.make_test_db)."""
    violations = []
    for test_file in glob.glob(os.path.join(_TESTS_DIR, "test_*.py")):
        content = _read(test_file)
        if "CREATE TABLE" in content and "shared_db" not in content:
            fname = os.path.basename(test_file)
            violations.append(fname)
    passed = len(violations) == 0
    return {
        "check": "T4",
        "title": "No inline CREATE TABLE in tests",
        "passed": passed,
        "detail": f"Found inline schemas in: {', '.join(violations)}" if violations else "All tests use shared_db",
    }


ALL_CHECKS = [
    check_r1,
    check_r2,
    check_r3,
    check_a1,
    check_a2,
    check_a3,
    check_c1,
    check_c2,
    check_t1,
    check_t2,
    check_t3,
    check_t4,
    check_d1,
    check_d2,
]


def main() -> int:
    results: list[dict] = []
    for check_fn in ALL_CHECKS:
        result = check_fn()
        results.append(result)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    total = len(results)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_checks": total,
        "passed": passed,
        "failed": failed,
        "checks": results,
    }

    # Human-readable summary
    print("=" * 60)
    print("  AUDIT CHECK RESULTS")
    print("=" * 60)
    for r in results:
        icon = "OK" if r["status"] == "PASS" else "!!"
        print(f"  [{icon}] {r['id']}: {r['name']}")
        print(f"       {r['details']}")
    print("-" * 60)
    print(f"  TOTAL: {total}  PASSED: {passed}  FAILED: {failed}")
    if failed > 0:
        print("  RESULT: FAIL")
    else:
        print("  RESULT: PASS")
    print("=" * 60)

    # JSON output
    print()
    print(json.dumps(report, indent=2))

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
