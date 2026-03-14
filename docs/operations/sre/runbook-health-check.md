# Runbook: Health Check Failure

**Alert:** Rule 1 -- Health check failure
**Severity:** P1
**Trigger:** `/api/health/ready` returns 503 or times out 3x in 5 minutes
**Last updated:** 2026-02-26

---

## Overview

The `/api/health/ready` endpoint (defined in `mandarin/web/routes.py`, line 370) performs two checks:

1. **Database connectivity:** Executes `SELECT 1` against the SQLite database.
2. **Schema currency:** Verifies `_schema_meta.version >= SCHEMA_VERSION` (the expected schema version compiled into the application).

A 503 response means one of these checks failed. The response body includes `reason` and `latency_ms` fields for diagnosis.

### Possible 503 Responses

```json
{"status": "not_ready", "reason": "schema migration pending: v25 -> v26", "latency_ms": 12.3}
```

```json
{"status": "not_ready", "reason": "database is locked", "latency_ms": 5001.0}
```

---

## Step 1: Check Fly.io Dashboard

**Goal:** Determine if the machine is running and reachable.

1. Open the Fly.io dashboard: `https://fly.io/apps/mandarin`
2. Check machine status: is the machine `started`, `stopped`, or `crashed`?
3. Check recent events for restart loops or OOM kills.
4. Check the region (`ewr`) for any Fly.io platform incidents: `https://status.flyio.net`

**Command-line alternative:**
```bash
fly status --app mandarin
fly machines list --app mandarin
```

**If the machine is stopped:**
```bash
fly machines start <machine-id>
```

**If the machine is in a restart loop:** Proceed to Step 3 (check process) and Step 5 (check logs) to identify the crash cause before restarting again.

---

## Step 2: SSH Into the Machine

**Goal:** Get a shell on the running machine for direct investigation.

```bash
fly ssh console --app mandarin
```

If SSH fails with "no machines running":
```bash
fly machines list --app mandarin
# If all stopped, start one:
fly machines start <machine-id>
# Wait for it to boot, then retry SSH
fly ssh console --app mandarin
```

---

## Step 3: Check the Application Process

**Goal:** Verify gunicorn is running and not stuck.

```bash
ps aux | grep gunicorn
```

**Expected output:** You should see a gunicorn master process and one or more worker processes.

```
root     123  0.1  2.3  gunicorn: master [mandarin]
root     124  0.5  4.1  gunicorn: worker [mandarin]
```

**If gunicorn is not running:**
- Check the entrypoint: `cat /app/docker-entrypoint.sh`
- Try starting manually: `cd /app && gunicorn mandarin.web:create_app() --bind 0.0.0.0:8080`
- If it crashes on startup, the error will be printed to stderr. Capture it and proceed to diagnosis.

**If gunicorn is running but unresponsive:**
- Check worker count and memory: `ps aux | grep gunicorn | grep worker | wc -l`
- Check system memory: `free -m` or `cat /proc/meminfo`
- If the VM is out of memory (512MB limit on `shared-cpu-1x`), workers may be killed silently. Check `dmesg` for OOM kill messages.

---

## Step 4: Check the Database

**Goal:** Verify the SQLite database is intact and accessible.

### 4a: Check database file exists and is accessible

```bash
ls -la /data/mandarin.db
ls -la /data/mandarin.db-wal
ls -la /data/mandarin.db-shm
```

**Expected:** The `.db` file should exist with a reasonable size. The `-wal` (Write-Ahead Log) and `-shm` (Shared Memory) files are normal for WAL mode.

**If the database file is missing:** The `/data` volume mount may have failed. Check:
```bash
mount | grep /data
df -h /data
```

### 4b: Run integrity check

```bash
sqlite3 /data/mandarin.db "PRAGMA integrity_check"
```

**Expected output:** `ok`

**If integrity check fails:** The database is corrupted. Options:
1. Attempt recovery: `sqlite3 /data/mandarin.db ".recover" | sqlite3 /data/mandarin_recovered.db`
2. Restore from Litestream backup (see Step 4e).
3. If neither works, this is a data loss incident -- escalate immediately.

### 4c: Check schema version

```bash
sqlite3 /data/mandarin.db "SELECT value FROM _schema_meta WHERE key='version'"
```

Compare the output to the expected `SCHEMA_VERSION` in the deployed code. If the schema is behind, a migration is needed.

**If schema migration is pending:**
- Check if the migration ran and failed: look for errors in the application log (Step 5).
- Migrations run automatically on app startup. A restart may resolve a stalled migration.
- If the migration is stuck, check for SQLite locks: `sqlite3 /data/mandarin.db "PRAGMA lock_status"`.

### 4d: Check for database locks

```bash
# Check WAL file size -- a very large WAL file indicates write contention
ls -lh /data/mandarin.db-wal

# Check if any processes have the DB locked
fuser /data/mandarin.db 2>/dev/null
```

**If the database is locked:**
- Identify the locking process and determine if it is stuck.
- A checkpoint may be needed: `sqlite3 /data/mandarin.db "PRAGMA wal_checkpoint(TRUNCATE)"`.
- As a last resort, restart the application (Step 7).

### 4e: Check Litestream backup status

```bash
# Check Litestream process
ps aux | grep litestream

# Check most recent generation
litestream generations /data/mandarin.db
```

If the database needs to be restored from backup:
```bash
# Stop the application first
kill $(pgrep gunicorn)

# Restore from Litestream
litestream restore -o /data/mandarin.db s3://<bucket>/mandarin.db

# Restart the application
# (Fly.io will restart it automatically if the process exits)
```

---

## Step 5: Check Application Logs

**Goal:** Find error messages that explain the health check failure.

```bash
# Recent application logs (on the machine)
tail -100 /data/app.log
```

**From your local machine (Fly.io log streaming):**
```bash
fly logs --app mandarin
```

**Key patterns to look for:**

| Log Pattern | Meaning |
|------------|---------|
| `readiness check failed:` | The `/api/health/ready` handler caught an exception (logged at ERROR in `routes.py` line 396) |
| `health check failed:` | The `/api/health` handler caught an exception (logged at ERROR in `routes.py` line 442) |
| `Slow request:` | Request latency exceeded 1000ms (logged at WARNING in `web/__init__.py` line 114) |
| `SECURITY_EVENT` | Security-related events from `security.py` |
| `crash_log DB insert failed` | A 500 error occurred AND the crash_log insert also failed (double failure, logged at CRITICAL in `web/__init__.py` line 511) |
| `schema migration` | Migration in progress or failed |
| `Marked X orphaned session(s)` | Orphaned sessions cleaned up on startup (normal after restart) |
| `SECRET_KEY must be set` | Production secret not configured -- app will refuse to start |
| `JWT_SECRET must be set` | JWT secret not configured -- app will refuse to start |

---

## Step 6: Check Schema Version and Required Tables

**Goal:** Verify the database schema is complete and current.

```bash
sqlite3 /data/mandarin.db "SELECT value FROM _schema_meta WHERE key='version'"
```

Check that all required tables exist (these are verified by the `/api/health` endpoint in `routes.py` line 413):

```bash
sqlite3 /data/mandarin.db "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
```

**Required tables (checked by health endpoint):**
- `learner_profile`
- `content_item`
- `progress`
- `session_log`
- `error_log`

**Additional important tables:**
- `user` (authentication)
- `security_audit_log` (audit trail)
- `crash_log` (error tracking)
- `_schema_meta` (schema versioning)

**If tables are missing:** The database may have been partially initialized. The safest fix is to restore from a Litestream backup (Step 4e). If no backup is available, the schema can be applied from `schema.sql`, but this will not restore data.

---

## Step 7: Restart the Machine

**Goal:** Recover service by restarting the Fly.io machine.

**Only restart after completing Steps 3-6.** A restart without diagnosis may mask the root cause and delay a proper fix.

```bash
# Restart the specific machine
fly machines restart <machine-id> --app mandarin

# Or restart all machines
fly apps restart mandarin
```

**After restarting:**
1. Wait 30 seconds for the machine to boot and run migrations.
2. Verify the health check passes:
```bash
curl -s https://mandarin.fly.dev/api/health/ready | python3 -m json.tool
```
3. Verify the full health check:
```bash
curl -s https://mandarin.fly.dev/api/health | python3 -m json.tool
```

**Expected healthy response from `/api/health`:**
```json
{
    "status": "ok",
    "schema_version": 26,
    "schema_current": true,
    "item_count": 299,
    "tables": 16,
    "uptime_seconds": 42,
    "latency_ms": 3.2
}
```

4. Monitor for 15 minutes to confirm the issue does not recur.

---

## Step 8: If the Issue Persists After Restart

If the health check continues to fail after a restart:

1. **Check for persistent database corruption** (Step 4b). If `PRAGMA integrity_check` fails, restore from backup.
2. **Check for volume mount issues.** The `/data` mount (configured in `fly.toml`) may be degraded:
```bash
fly volumes list --app mandarin
```
3. **Check for Fly.io platform issues** at `https://status.flyio.net`.
4. **Try a fresh deploy** to rule out a stale image:
```bash
fly deploy --app mandarin
```
5. **If all else fails,** create a new volume and restore from Litestream backup:
```bash
fly volumes create mandarin_data --region ewr --size 1
# Update the machine to use the new volume
# Restore database from Litestream
```

---

## Verification Checklist

After resolving the issue, verify all of the following:

- [ ] `/api/health/ready` returns 200 with `{"status": "ok"}`
- [ ] `/api/health` returns 200 with `schema_current: true` and correct `item_count`
- [ ] `/api/health/live` returns 200 with reasonable `uptime_seconds`
- [ ] Fly.io dashboard shows machine as `started` with passing health checks
- [ ] Application logs show no new errors for 15 minutes
- [ ] A test login succeeds (auth system functional)
- [ ] A test drill session can be started and completed (core feature functional)
- [ ] Litestream replication is active (if applicable)

---

## Escalation

If you cannot resolve the health check failure within 1 hour:

1. Document everything you have tried and what you observed.
2. Check if this matches a known issue pattern (see related postmortems).
3. Consider whether a full redeploy or volume recreation is needed.
4. File the incident per the postmortem template (`postmortem-template.md`).

---

## Related Documents

- [SLO Definitions](slo-definitions.md) -- Availability SLO (99.5% target)
- [Alert Rules](alert-rules.md) -- Rule 1 (health check failure)
- [Incident Severity](incident-severity.md) -- P1 definition and response protocol
- [Postmortem Template](postmortem-template.md) -- Required within 48 hours for P1
- `fly.toml` -- Health check configuration (interval: 15s, timeout: 5s, path: `/api/health/ready`)
- `mandarin/web/routes.py` lines 350-443 -- Health check endpoint implementations
- `mandarin/web/__init__.py` -- Error handlers, request logging, crash logging
