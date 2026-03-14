#!/usr/bin/env bash
# smoke_test.sh — Post-deploy smoke test for Aelu.
#
# Usage:
#   ./scripts/smoke_test.sh                    # defaults to https://aelu.app
#   ./scripts/smoke_test.sh http://localhost:5001
#
# Exits 0 if all checks pass, 1 on first failure.
# Designed to run in CI after flyctl deploy.

set -euo pipefail

BASE_URL="${1:-https://aelu.app}"
PASS=0
FAIL=0
TOTAL=0

check() {
  local name="$1"
  local url="$2"
  local expected_status="${3:-200}"
  local body_contains="${4:-}"

  TOTAL=$((TOTAL + 1))
  local status body
  body=$(curl -sSf -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || true)
  # Retry once on network failure
  if [ -z "$body" ]; then
    sleep 2
    body=$(curl -sSf -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || true)
  fi

  if [ "$body" = "$expected_status" ]; then
    if [ -n "$body_contains" ]; then
      local response
      response=$(curl -sS --max-time 10 "$url" 2>/dev/null || true)
      if echo "$response" | grep -q "$body_contains"; then
        echo "  PASS  $name"
        PASS=$((PASS + 1))
      else
        echo "  FAIL  $name (missing: $body_contains)"
        FAIL=$((FAIL + 1))
      fi
    else
      echo "  PASS  $name"
      PASS=$((PASS + 1))
    fi
  else
    echo "  FAIL  $name (expected $expected_status, got $body)"
    FAIL=$((FAIL + 1))
  fi
}

check_post() {
  local name="$1"
  local url="$2"
  local data="$3"
  local expected_status="${4:-200}"

  TOTAL=$((TOTAL + 1))
  local status
  status=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
    -X POST -H "Content-Type: application/json" -d "$data" "$url" 2>/dev/null || true)

  if [ "$status" = "$expected_status" ]; then
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name (expected $expected_status, got $status)"
    FAIL=$((FAIL + 1))
  fi
}

echo "Smoke test: $BASE_URL"
echo "==============================="

# --- 1. Health probes ---
echo ""
echo "Health probes:"
check "liveness"  "$BASE_URL/api/health/live"  "200" '"status":"ok"'
check "readiness"  "$BASE_URL/api/health/ready"  "200" '"status":"ok"'
check "full health"  "$BASE_URL/api/health"  "200" '"status":"ok"'

# --- 2. Static assets ---
echo ""
echo "Static assets:"
check "app.js"   "$BASE_URL/static/app.js"   "200"
check "style.css" "$BASE_URL/static/style.css" "200"
check "sw.js"    "$BASE_URL/static/sw.js"    "200"
check "manifest" "$BASE_URL/static/manifest.json" "200"

# --- 3. Page loads ---
echo ""
echo "Page loads:"
check "landing page"    "$BASE_URL/"         "200"
check "login page"      "$BASE_URL/auth/login" "200"

# --- 4. API structure (unauthenticated) ---
echo ""
echo "API structure:"
check "SW status"       "$BASE_URL/api/sw-status" "200" '"active"'

# --- 5. CSRF enforcement ---
echo ""
echo "Security:"
check_post "CSRF blocks bare POST" "$BASE_URL/api/personalization" '{"domains":["test"]}' "403"
check_post "client-events accepts sendBeacon" "$BASE_URL/api/client-events" '{"events":[],"install_id":"smoke"}' "204"
check_post "error-report accepts POST" "$BASE_URL/api/error-report" '{"error_type":"smoke","message":"test"}' "204"

# --- 6. Security headers ---
echo ""
echo "Security headers:"
TOTAL=$((TOTAL + 1))
headers=$(curl -sS -D - -o /dev/null --max-time 10 "$BASE_URL/" 2>/dev/null || true)
csp_ok=true
if ! echo "$headers" | grep -qi "content-security-policy"; then
  echo "  FAIL  CSP header missing"
  FAIL=$((FAIL + 1))
  csp_ok=false
fi
if $csp_ok; then
  if echo "$headers" | grep -i "content-security-policy" | grep -q "nonce-"; then
    echo "  PASS  CSP with nonce present"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  CSP missing nonce"
    FAIL=$((FAIL + 1))
  fi
fi

# --- Summary ---
echo ""
echo "==============================="
echo "Results: $PASS/$TOTAL passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
  echo "SMOKE TEST FAILED"
  exit 1
else
  echo "SMOKE TEST PASSED"
  exit 0
fi
