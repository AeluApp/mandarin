#!/bin/bash
# Disaster Recovery Test — Litestream backup/restore verification
#
# Tests: backup creation, restore to temp DB, integrity check, row count verify.
# Intended for CI (weekly) or manual validation.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/tmp/mandarin-dr-test}"
RESTORE_DB="${BACKUP_DIR}/restored.db"
SOURCE_DB="${SOURCE_DB:-data/mandarin.db}"

echo "=== DR Test: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# Clean up previous test
rm -rf "${BACKUP_DIR}"
mkdir -p "${BACKUP_DIR}"

# Step 1: Verify source database exists
if [ ! -f "${SOURCE_DB}" ]; then
  echo "ERROR: Source database not found: ${SOURCE_DB}"
  exit 1
fi
echo "[1/5] Source database: ${SOURCE_DB} ($(du -h "${SOURCE_DB}" | cut -f1))"

# Step 2: Create backup copy (simulates Litestream restore)
echo "[2/5] Creating backup..."
sqlite3 "${SOURCE_DB}" ".backup '${RESTORE_DB}'"
echo "  Backup size: $(du -h "${RESTORE_DB}" | cut -f1)"

# Step 3: Integrity check on restored database
echo "[3/5] Running integrity check..."
INTEGRITY=$(sqlite3 "${RESTORE_DB}" "PRAGMA integrity_check;")
if [ "${INTEGRITY}" != "ok" ]; then
  echo "ERROR: Integrity check failed: ${INTEGRITY}"
  exit 1
fi
echo "  Integrity: ok"

# Step 4: Verify row counts match
echo "[4/5] Comparing row counts..."
TABLES=$(sqlite3 "${SOURCE_DB}" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
MISMATCH=0
for TABLE in ${TABLES}; do
  SOURCE_COUNT=$(sqlite3 "${SOURCE_DB}" "SELECT COUNT(*) FROM ${TABLE};")
  RESTORE_COUNT=$(sqlite3 "${RESTORE_DB}" "SELECT COUNT(*) FROM ${TABLE};")
  if [ "${SOURCE_COUNT}" != "${RESTORE_COUNT}" ]; then
    echo "  MISMATCH: ${TABLE} — source=${SOURCE_COUNT}, restored=${RESTORE_COUNT}"
    MISMATCH=1
  fi
done
if [ "${MISMATCH}" -eq 1 ]; then
  echo "ERROR: Row count mismatch detected"
  exit 1
fi
echo "  All table row counts match"

# Step 5: Schema version check
echo "[5/5] Schema version check..."
SOURCE_VER=$(sqlite3 "${SOURCE_DB}" "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;" 2>/dev/null || echo "unknown")
RESTORE_VER=$(sqlite3 "${RESTORE_DB}" "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;" 2>/dev/null || echo "unknown")
echo "  Source schema: v${SOURCE_VER}, Restored schema: v${RESTORE_VER}"
if [ "${SOURCE_VER}" != "${RESTORE_VER}" ]; then
  echo "ERROR: Schema version mismatch"
  exit 1
fi

# Cleanup
rm -rf "${BACKUP_DIR}"
echo "=== DR Test PASSED ==="
