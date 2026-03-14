# Alert Rules

**Service:** Mandarin Learning System (Aelu)
**Owner:** Jason Gerson
**Last updated:** 2026-02-26

---

## Alert Summary

| # | Rule | Condition | Severity | Channel | Runbook |
|---|------|-----------|----------|---------|---------|
| 1 | Health check failure | `/api/health/ready` returns 503 3x in 5min | P1 | Webhook + Email | [runbook-health-check.md](runbook-health-check.md) |
| 2 | High error rate | `crash_log` rows > 10 in 5min | P2 | Email | Check recent deploys, review crash_log |
| 3 | Latency regression | `latency_ms` p95 > 750ms for 10min | P2 | Email | Check DB queries, VACUUM, restart |
| 4 | Session failures | `session_outcome != 'completed'` > 5% in 1h | P2 | Email | Check WebSocket, review session_log |
| 5 | Auth failures (brute force) | `login_failed` > 50 in 1h from single IP | P3 | Log + Review | Check for brute force, verify rate limiter |
| 6 | Error budget warning | Monthly budget > 50% consumed | P3 | Weekly report | Freeze features per SLO policy |
| 7 | Database size | SQLite file > 500MB | P3 | Weekly report | Plan VACUUM, check data retention |
| 8 | Critical security event | Any `CRITICAL` severity in `security_audit_log` | P1 | Webhook + Email | Investigate immediately |
| 9 | Litestream replication lag | No backup in > 1 hour | P2 | Email | Check Litestream, verify `/data` mount |
| 10 | Client error spike | `client_error_log` rows > 20 in 10min | P3 | Email | Check recent JS deploys |

---

## Alert Rule Details

### Rule 1: Health Check Failure

**Condition:** `/api/health/ready` returns HTTP 503 (or times out) 3 times within a 5-minute window.

**Source:** Fly.io health check probes (every 15 seconds per `fly.toml`).

**Why this matters:** The readiness probe (`web/routes.py`, line 370) verifies that the database is accessible and the schema version is current. Three consecutive failures indicate the service cannot serve user requests.

**Detection query:**
```sql
-- Check crash_log for recent DB or schema errors
SELECT COUNT(*) AS recent_crashes
FROM crash_log
WHERE timestamp >= datetime('now', '-5 minutes')
  AND (error_type LIKE '%sqlite%' OR error_type LIKE '%OperationalError%');
```

**Action:** Follow [runbook-health-check.md](runbook-health-check.md).

---

### Rule 2: High Error Rate

**Condition:** More than 10 new rows in `crash_log` within a 5-minute window.

**Source:** The `_log_crash()` function in `web/__init__.py` (line 463) writes to `crash_log` on every unhandled 500 error.

**Detection query:**
```sql
SELECT
    error_type,
    COUNT(*) AS count,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM crash_log
WHERE timestamp >= datetime('now', '-5 minutes')
GROUP BY error_type
ORDER BY count DESC;
```

**Action:**
1. Check `crash_log` for the error type and traceback.
2. Correlate with recent deploys (`fly releases`).
3. If a deploy caused the regression, roll back: `fly deploy --image <previous-image>`.
4. If not deploy-related, investigate the traceback and apply a fix.

---

### Rule 3: Latency Regression

**Condition:** 95th percentile of `latency_ms` exceeds 750ms for 10 consecutive minutes.

**Source:** The `_log_request` after-request handler in `web/__init__.py` (line 93) logs `latency_ms` for every non-static request. Requests over 1000ms also trigger a WARNING log.

**Detection:** Monitor structured log output for `latency_ms` values. The WARNING log `"Slow request: ... took Xms"` provides a quick signal.

**Action:**
1. SSH into the machine: `fly ssh console`.
2. Check if SQLite is under write contention: look for WAL file size (`ls -la /data/mandarin.db-wal`).
3. Run `sqlite3 /data/mandarin.db "PRAGMA integrity_check"` to verify DB health.
4. Check if VACUUM is needed: `sqlite3 /data/mandarin.db "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()"`.
5. If VM memory is exhausted, consider upgrading from `shared-cpu-1x` / `512mb`.
6. Restart the machine if the issue persists: `fly machines restart`.

---

### Rule 4: Session Failures

**Condition:** More than 5% of sessions started in the last hour have `session_outcome` other than `'completed'`.

**Source:** `session_log` table. Sessions start with `session_outcome = 'started'` and should transition to `'completed'`. The orphaned session cleanup in `web/__init__.py` (line 421) marks old `'started'` sessions as `'interrupted'`.

**Detection query:**
```sql
SELECT
    session_outcome,
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM session_log
WHERE started_at >= datetime('now', '-1 hour')
GROUP BY session_outcome;
```

**Action:**
1. Check if WebSocket connections are failing (WebSocket is used for drill sessions).
2. Review `crash_log` for errors during session endpoints.
3. Check `client_error_log` for JavaScript errors that might prevent session completion.
4. Verify Fly.io machine is not being stopped mid-session (`auto_stop_machines = "stop"` in `fly.toml`).

---

### Rule 5: Auth Failures (Brute Force Detection)

**Condition:** More than 50 `login_failed` events from a single IP address within 1 hour.

**Source:** `security_audit_log` table, populated by `log_security_event()` in `security.py`.

**Detection query:**
```sql
SELECT
    ip_address,
    COUNT(*) AS failed_attempts,
    MIN(timestamp) AS first_attempt,
    MAX(timestamp) AS last_attempt,
    COUNT(DISTINCT user_id) AS targeted_users
FROM security_audit_log
WHERE event_type = 'login_failed'
  AND timestamp >= datetime('now', '-1 hour')
GROUP BY ip_address
HAVING COUNT(*) > 50
ORDER BY failed_attempts DESC;
```

**Action:**
1. Verify the rate limiter is working (10/minute on login route, configured in `web/__init__.py` line 257).
2. Check if the IP should be blocked at the Fly.io level.
3. Check if any accounts were locked (`login_locked` events).
4. Review `user.failed_login_attempts` and `user.locked_until` for targeted accounts.
5. If this is a real attack, consider tightening the rate limit or adding IP-based blocking.

---

### Rule 6: Error Budget Warning

**Condition:** Any SLO's monthly error budget exceeds 50% consumed.

**Source:** Calculated from the SLI measurements defined in `slo-definitions.md`.

**Frequency:** Checked weekly (during weekly report generation).

**Action:**
1. Identify which SLO is burning budget.
2. Correlate with recent incidents or changes.
3. Apply error budget policy from `slo-definitions.md`:
   - 50-80% consumed: No new feature deploys.
   - 80%+ consumed: Feature freeze.
4. Schedule immediate investigation of the budget-burning issue.

---

### Rule 7: Database Size

**Condition:** The SQLite database file exceeds 500MB.

**Source:** File system check on `/data/mandarin.db`.

**Frequency:** Checked weekly.

**Detection:**
```bash
# On Fly.io machine
ls -lh /data/mandarin.db
sqlite3 /data/mandarin.db "SELECT page_count * page_size AS db_size_bytes FROM pragma_page_count(), pragma_page_size()"
```

**Action:**
1. Check which tables are consuming the most space:
```sql
SELECT name, SUM(pgsize) AS size_bytes
FROM dbstat
GROUP BY name
ORDER BY size_bytes DESC
LIMIT 10;
```
2. Verify data retention is running (weekly background purge, `web/__init__.py` line 442).
3. Run VACUUM if fragmentation is high: `sqlite3 /data/mandarin.db "VACUUM"`.
4. Consider archiving old `session_log`, `error_log`, and `security_audit_log` entries.

---

### Rule 8: Critical Security Event

**Condition:** Any row in `security_audit_log` with `severity = 'CRITICAL'`.

**Source:** `log_security_event()` in `security.py` with `Severity.CRITICAL`.

**Delivery:** Automated via `_send_critical_alert()` in `security.py` (line 79), which posts to `ALERT_WEBHOOK_URL` and emails `ADMIN_EMAIL`. If both fail, the failure is recorded in `security_audit_log` as `alert_delivery_failure`.

**Detection query:**
```sql
SELECT *
FROM security_audit_log
WHERE severity = 'CRITICAL'
  AND timestamp >= datetime('now', '-1 hour')
ORDER BY timestamp DESC;
```

**Action:**
1. Identify the event type and assess impact.
2. If auth bypass: immediately disable affected accounts and rotate secrets.
3. If data breach: follow data incident procedures.
4. Escalate to P1 if service integrity is at risk.

---

### Rule 9: Litestream Replication Lag

**Condition:** No Litestream backup snapshot in over 1 hour.

**Source:** Litestream replication log / S3 bucket check.

**Action:**
1. SSH into the machine and check Litestream process: `ps aux | grep litestream`.
2. Check Litestream logs for errors.
3. Verify the `/data` mount is accessible and writable.
4. Restart Litestream if needed.
5. Verify the most recent backup in the S3 bucket.

---

### Rule 10: Client Error Spike

**Condition:** More than 20 new rows in `client_error_log` within 10 minutes.

**Source:** `client_error_log` table (schema V24+), populated by the `/api/error-report` endpoint.

**Detection query:**
```sql
SELECT
    error_type,
    source_file,
    COUNT(*) AS count,
    COUNT(DISTINCT user_id) AS affected_users
FROM client_error_log
WHERE timestamp >= datetime('now', '-10 minutes')
GROUP BY error_type, source_file
ORDER BY count DESC;
```

**Action:**
1. Check if a recent deploy introduced a JavaScript regression.
2. Review the `stack_trace` and `page_url` columns for the most common errors.
3. If deploy-related, roll back the static assets.
4. If browser-specific, check `user_agent` distribution.

---

## Webhook Payload Format

When `_send_critical_alert()` in `security.py` fires, it POSTs to `ALERT_WEBHOOK_URL` with the following JSON payload:

```json
{
    "text": "CRITICAL: login_locked user=42 details=Account locked after 5 failed attempts [POST /api/auth/login]",
    "severity": "CRITICAL",
    "event_type": "login_locked",
    "user_id": 42
}
```

### Extended Webhook Payload (for custom alert integrations)

For alerts beyond critical security events (Rules 1-4, 7, 9-10), implement a monitoring script that POSTs:

```json
{
    "alert_rule": "health_check_failure",
    "severity": "P1",
    "service": "mandarin",
    "region": "ewr",
    "description": "/api/health/ready returned 503 3 times in 5 minutes",
    "timestamp": "2026-02-26T14:30:00Z",
    "runbook_url": "https://github.com/<repo>/blob/main/docs/operations/sre/runbook-health-check.md",
    "context": {
        "health_response": {"status": "not_ready", "reason": "schema migration pending: v25 -> v26", "latency_ms": 1200},
        "machine_id": "abc123",
        "region": "ewr"
    }
}
```

---

## Email Alert Template

**Subject:** `[MANDARIN-{P1|P2|P3}] {Alert Rule Name} -- {Brief Description}`

**Body:**

```
Alert: {Rule Name}
Severity: {P1|P2|P3}
Time: {YYYY-MM-DD HH:MM UTC}
Service: Mandarin Learning System
Region: ewr (Fly.io)

CONDITION:
{Description of what triggered the alert}

EVIDENCE:
{Relevant data -- query results, error counts, latency values}

RUNBOOK:
{Link to runbook or inline steps}

DASHBOARD:
- Fly.io: https://fly.io/apps/mandarin
- Sentry: [Sentry project URL]

---
This alert was generated by the Mandarin monitoring system.
To configure alerts, see docs/operations/sre/alert-rules.md.
```

---

## Alert Silencing

Alerts may be silenced during planned maintenance windows. Document all silencing:

| Alert | Silenced From | Silenced To | Reason | Approved By |
|-------|--------------|-------------|--------|-------------|
| [Rule #] | YYYY-MM-DD HH:MM | YYYY-MM-DD HH:MM | [Planned maintenance] | [Name] |

Rules for silencing:
- P1 alerts may only be silenced for a maximum of 1 hour during planned maintenance.
- P2 alerts may be silenced for up to 4 hours.
- All silencing must be documented in this table.
- Never silence all alerts simultaneously.
