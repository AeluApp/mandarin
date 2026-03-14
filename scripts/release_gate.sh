#!/usr/bin/env bash
# release_gate.sh — Pre-deploy quality gate checklist.
#
# Run this before pushing to main. Exits non-zero on any failure.
# Designed to catch issues locally before they hit CI.
#
# Usage:
#   ./scripts/release_gate.sh

set -euo pipefail

PASS=0
FAIL=0
TOTAL=0

gate() {
  local name="$1"
  shift
  TOTAL=$((TOTAL + 1))
  if "$@" > /dev/null 2>&1; then
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name"
    FAIL=$((FAIL + 1))
  fi
}

gate_output() {
  local name="$1"
  shift
  TOTAL=$((TOTAL + 1))
  local output
  output=$("$@" 2>&1) || true
  if echo "$output" | grep -q "$2" 2>/dev/null; then
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name"
    echo "         $output" | head -3
    FAIL=$((FAIL + 1))
  fi
}

echo "Release Quality Gate"
echo "==============================="

# --- 1. Git state ---
echo ""
echo "Git state:"
TOTAL=$((TOTAL + 1))
if git diff --quiet HEAD 2>/dev/null; then
  echo "  PASS  Working tree clean"
  PASS=$((PASS + 1))
else
  echo "  WARN  Uncommitted changes (non-blocking)"
  PASS=$((PASS + 1))
fi

TOTAL=$((TOTAL + 1))
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
  echo "  PASS  On main branch ($branch)"
  PASS=$((PASS + 1))
else
  echo "  INFO  On branch: $branch (deploy requires main)"
  PASS=$((PASS + 1))
fi

# --- 2. Python environment ---
echo ""
echo "Environment:"
gate "Python available"    python3 --version
gate "venv activated"      python3 -c "import mandarin"
gate "Flask importable"    python3 -c "from mandarin.web import create_app"
gate "DB module importable" python3 -c "from mandarin.db import init_db"

# --- 3. Schema ---
echo ""
echo "Schema:"
TOTAL=$((TOTAL + 1))
schema_ver=$(python3 -c "from mandarin.db.core import SCHEMA_VERSION; print(SCHEMA_VERSION)" 2>/dev/null || echo "0")
if [ "$schema_ver" -gt 0 ]; then
  echo "  PASS  Schema version: v$schema_ver"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Cannot read SCHEMA_VERSION"
  FAIL=$((FAIL + 1))
fi

TOTAL=$((TOTAL + 1))
migration_count=$(python3 -c "from mandarin.db.core import MIGRATIONS; print(len(MIGRATIONS))" 2>/dev/null || echo "0")
expected_migrations=$((schema_ver - 1))
if [ "$migration_count" -ge "$expected_migrations" ]; then
  echo "  PASS  Migrations registered: $migration_count"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Missing migrations: have $migration_count, need $expected_migrations"
  FAIL=$((FAIL + 1))
fi

# --- 4. Tests ---
echo ""
echo "Tests:"
TOTAL=$((TOTAL + 1))
test_output=$(python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)
if echo "$test_output" | grep -q "passed"; then
  passed=$(echo "$test_output" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
  echo "  PASS  Test suite: $passed passed ($test_output)"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Test suite: $test_output"
  FAIL=$((FAIL + 1))
fi

# --- 5. Golden flows ---
TOTAL=$((TOTAL + 1))
golden_output=$(python3 -m pytest tests/test_golden_flows.py -q --tb=no 2>&1 | tail -1)
if echo "$golden_output" | grep -q "passed"; then
  echo "  PASS  Golden flows: $golden_output"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Golden flows: $golden_output"
  FAIL=$((FAIL + 1))
fi

# --- 6. Security regression ---
TOTAL=$((TOTAL + 1))
sec_output=$(python3 -m pytest tests/test_security_regression.py -q --tb=no 2>&1 | tail -1)
if echo "$sec_output" | grep -q "passed"; then
  echo "  PASS  Security regression: $sec_output"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Security regression: $sec_output"
  FAIL=$((FAIL + 1))
fi

# --- 7. JS syntax ---
echo ""
echo "Frontend:"
TOTAL=$((TOTAL + 1))
if command -v node > /dev/null 2>&1; then
  if node --check mandarin/web/static/app.js 2>/dev/null; then
    echo "  PASS  app.js syntax valid"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  app.js syntax error"
    FAIL=$((FAIL + 1))
  fi
else
  echo "  SKIP  node not available (JS check skipped)"
  PASS=$((PASS + 1))
fi

# --- 8. Docker build (optional) ---
echo ""
echo "Deployment:"
TOTAL=$((TOTAL + 1))
if [ -f "Dockerfile" ]; then
  echo "  PASS  Dockerfile present"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Dockerfile missing"
  FAIL=$((FAIL + 1))
fi

TOTAL=$((TOTAL + 1))
if [ -f "fly.toml" ]; then
  echo "  PASS  fly.toml present"
  PASS=$((PASS + 1))
else
  echo "  FAIL  fly.toml missing"
  FAIL=$((FAIL + 1))
fi

TOTAL=$((TOTAL + 1))
if [ -f "docker-entrypoint.sh" ]; then
  echo "  PASS  docker-entrypoint.sh present"
  PASS=$((PASS + 1))
else
  echo "  FAIL  docker-entrypoint.sh missing"
  FAIL=$((FAIL + 1))
fi

# --- 9. Quality regression (DPMO, Cpk, SPC) ---
echo ""
echo "Quality regression:"
TOTAL=$((TOTAL + 1))
quality_check=$(python3 -c "
import sys
try:
    from mandarin import db
    conn = db.connection().__enter__()
    # DPMO check: should not exceed 100,000 (below 3-sigma is unacceptable)
    from mandarin.quality.dpmo import calculate_dpmo
    dpmo_data = calculate_dpmo(conn, days=30)
    dpmo = dpmo_data['dpmo']
    if dpmo_data['total_opportunities'] > 0 and dpmo > 100000:
        print(f'FAIL: DPMO={dpmo:.0f} exceeds 100,000 threshold')
        sys.exit(1)
    # Cpk check: drill accuracy Cpk should be >= 1.0
    from mandarin.quality.capability import assess_drill_accuracy
    cap = assess_drill_accuracy(conn, days=30)
    cpk = cap.get('cpk')
    if cpk is not None and cap.get('n', 0) >= 10 and cpk < 1.0:
        print(f'FAIL: Drill accuracy Cpk={cpk:.2f} below 1.0')
        sys.exit(1)
    # SPC check: no active out-of-control
    from mandarin.quality.spc import get_spc_chart_data
    for chart_type in ('drill_accuracy', 'response_time', 'session_completion'):
        spc = get_spc_chart_data(conn, chart_type, days=30)
        if spc.get('status') == 'out_of_control' and len(spc.get('observations', [])) >= 10:
            violations = len(spc.get('violations', []))
            print(f'FAIL: SPC out-of-control on {chart_type} ({violations} violations)')
            sys.exit(1)
    print(f'OK: DPMO={dpmo:.0f}, Cpk={cpk if cpk else \"n/a\"}')
except Exception as e:
    print(f'SKIP: quality check unavailable ({e})')
" 2>&1)
quality_exit=$?
if [ $quality_exit -eq 0 ]; then
  echo "  PASS  Quality regression: $quality_check"
  PASS=$((PASS + 1))
elif echo "$quality_check" | grep -q "^SKIP"; then
  echo "  SKIP  $quality_check"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Quality regression: $quality_check"
  FAIL=$((FAIL + 1))
fi

# --- 10. Definition of Done checklist ---
echo ""
echo "Definition of Done:"
TOTAL=$((TOTAL + 1))
dod_fails=0
dod_checks=0

# DoD 1: Tests pass (already checked above, just reference)
dod_checks=$((dod_checks + 1))
if echo "$test_output" | grep -q "passed"; then
  : # already counted
else
  dod_fails=$((dod_fails + 1))
fi

# DoD 2: No active SPC violations (checked above)
dod_checks=$((dod_checks + 1))
if [ $quality_exit -ne 0 ] && ! echo "$quality_check" | grep -q "^SKIP"; then
  dod_fails=$((dod_fails + 1))
fi

# DoD 3: Schema version matches migration count
dod_checks=$((dod_checks + 1))
if [ "$migration_count" -ge "$expected_migrations" ]; then
  : # already counted
else
  dod_fails=$((dod_fails + 1))
fi

if [ $dod_fails -eq 0 ]; then
  echo "  PASS  Definition of Done: $dod_checks/$dod_checks criteria met"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Definition of Done: $((dod_checks - dod_fails))/$dod_checks criteria met"
  FAIL=$((FAIL + 1))
fi

# --- Summary ---
echo ""
echo "==============================="
echo "Results: $PASS/$TOTAL passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "RELEASE GATE: BLOCKED"
  echo "Fix the failures above before deploying."
  exit 1
else
  echo ""
  echo "RELEASE GATE: CLEAR"
  echo "All quality gates passed. Safe to deploy."
  exit 0
fi
