# Service Level Objectives (SLOs)

**Service:** Mandarin Learning System (Aelu)
**Owner:** Jason Gerson
**Last reviewed:** 2026-02-26
**Review cadence:** Monthly (first Monday)

---

## SLO Summary

| SLO | Target | SLI Measurement | Error Budget (30d) |
|-----|--------|-----------------|-------------------|
| Availability | 99.5% | `/api/health/ready` 200 responses | 3.6 hours downtime |
| API Latency (p95) | < 500ms | `latency_ms` from request logging | 5% of requests |
| API Latency (p99) | < 2000ms | `latency_ms` from request logging | 1% of requests |
| Session Completion | 99.0% | `session_outcome='completed'` / total started | 1% of sessions |
| Auth Success | 99.9% | `LOGIN_SUCCESS` / total login attempts | 0.1% of attempts |

---

## SLO 1: Availability

**Target:** 99.5% of `/api/health/ready` probes return HTTP 200 over a rolling 30-day window.

**Error budget:** 3.6 hours of downtime per 30-day period (0.5% of 720 hours).

### SLI Measurement

Fly.io performs health checks against `/api/health/ready` every 15 seconds (configured in `fly.toml`). The endpoint verifies:

1. SQLite database is readable (`SELECT 1`)
2. Schema version is current (`_schema_meta.version >= SCHEMA_VERSION`)

A 503 response or timeout (>5s) counts as a failure.

**SQL query for manual SLI calculation (against structured logs):**

```sql
-- Availability over the last 30 days from crash_log and health check data.
-- Proxy: measure uptime by checking for gaps in session_log activity
-- combined with crash_log entries.
SELECT
    ROUND(
        100.0 * (1.0 - (
            CAST(COUNT(CASE WHEN severity IN ('ERROR', 'CRITICAL') THEN 1 END) AS REAL)
            / NULLIF(COUNT(*), 0)
        )), 2
    ) AS availability_pct
FROM crash_log
WHERE timestamp >= datetime('now', '-30 days');
```

**Application-level measurement:** The `api_health_ready()` handler in `web/routes.py` (line 370) returns `latency_ms` in every response. Any response with HTTP 503 or a `latency_ms > 5000` is counted as unavailable.

### Fly.io Health Check Configuration

From `fly.toml`:

```toml
[[http_service.checks]]
  grace_period = "10s"
  interval = "15s"
  method = "GET"
  path = "/api/health/ready"
  timeout = "5s"
```

Fly.io will route traffic away from a machine that fails this check and restart it if failures persist.

---

## SLO 2: API Latency (p95)

**Target:** 95th percentile of API request latency < 500ms over a rolling 30-day window.

**Error budget:** 5% of requests may exceed 500ms.

### SLI Measurement

Every non-static request is timed by the `_log_request` after-request handler in `web/__init__.py` (line 93). The handler emits structured log entries with the `latency_ms` field:

```
INFO GET /api/session 200 42.3ms
```

Requests exceeding 1000ms are also logged at WARNING level:

```
WARNING Slow request: GET /api/session took 1203.0ms
```

**SQL query (if latency data is captured to a table or exported from logs):**

```sql
-- p95 latency from application logs (requires log aggregation)
-- Proxy measurement from crash_log response times:
SELECT
    COUNT(*) AS total_requests,
    -- Manual p95: sort and pick the 95th percentile entry
    -- (requires log export to a queryable format)
    'See structured log output for latency_ms values' AS note
FROM crash_log
WHERE timestamp >= datetime('now', '-30 days');
```

**Primary measurement method:** Parse structured log output for `latency_ms` values. The `extra` dict in the log record contains `request_method`, `request_path`, `status_code`, and `latency_ms`.

---

## SLO 3: API Latency (p99)

**Target:** 99th percentile of API request latency < 2000ms over a rolling 30-day window.

**Error budget:** 1% of requests may exceed 2000ms.

### SLI Measurement

Same data source as SLO 2. The `_log_request` handler captures `latency_ms` for every API request. Requests exceeding 1000ms trigger an explicit WARNING log.

**Threshold:** Any request with `latency_ms >= 2000` is a p99 SLO violation.

---

## SLO 4: Session Completion

**Target:** 99.0% of started sessions reach `session_outcome = 'completed'` over a rolling 30-day window.

**Error budget:** 1% of sessions may fail to complete (abandoned, interrupted, or crashed).

### SLI Measurement

The `session_log` table tracks every learning session. A session begins with `session_outcome = 'started'` and transitions to `'completed'` on successful finish. Orphaned sessions (started but never ended) are cleaned up on app startup and marked as `'interrupted'` (see `web/__init__.py`, line 421).

**SQL query:**

```sql
SELECT
    COUNT(*) AS total_sessions,
    COUNT(CASE WHEN session_outcome = 'completed' THEN 1 END) AS completed,
    COUNT(CASE WHEN session_outcome != 'completed' THEN 1 END) AS incomplete,
    ROUND(
        100.0 * COUNT(CASE WHEN session_outcome = 'completed' THEN 1 END)
        / NULLIF(COUNT(*), 0), 2
    ) AS completion_rate_pct
FROM session_log
WHERE started_at >= datetime('now', '-30 days')
  AND session_outcome IS NOT NULL;
```

**Session outcome values:**
- `started` -- session in progress (or orphaned if `ended_at IS NULL` and old)
- `completed` -- normal completion
- `interrupted` -- orphaned session cleaned up by startup handler
- Other values may indicate early exits (`early_exit = 1`)

---

## SLO 5: Auth Success

**Target:** 99.9% of legitimate login attempts succeed over a rolling 30-day window.

**Error budget:** 0.1% of login attempts may fail due to system error (not user error).

### SLI Measurement

The `security_audit_log` table records all authentication events via the `SecurityEvent` enum in `security.py`. Relevant event types:

- `login_success` -- successful authentication
- `login_failed` -- failed authentication (wrong password, locked account)
- `login_locked` -- account locked due to repeated failures

**SQL query:**

```sql
SELECT
    COUNT(*) AS total_attempts,
    COUNT(CASE WHEN event_type = 'login_success' THEN 1 END) AS successes,
    COUNT(CASE WHEN event_type = 'login_failed' THEN 1 END) AS failures,
    COUNT(CASE WHEN event_type = 'login_locked' THEN 1 END) AS lockouts,
    ROUND(
        100.0 * COUNT(CASE WHEN event_type = 'login_success' THEN 1 END)
        / NULLIF(COUNT(*), 0), 2
    ) AS success_rate_pct
FROM security_audit_log
WHERE event_type IN ('login_success', 'login_failed', 'login_locked')
  AND timestamp >= datetime('now', '-30 days');
```

**Important:** This SLO measures system-caused auth failures (infrastructure, DB errors, bugs), not user-caused failures (wrong password). To isolate system failures, exclude events where `details` contains credential-related reasons. A sustained drop in success rate below 99.9% indicates a system problem, not a user behavior change.

---

## Error Budget Policy

### Budget Consumption Thresholds

| Budget Consumed | Policy |
|----------------|--------|
| 0-50% | Normal operations. Feature development proceeds. |
| 50-80% | **No new feature deploys.** Bug fixes, reliability work, and rollbacks only. Engineering focus shifts to identifying and resolving the budget-burning issue. |
| 80-100% | **Feature freeze.** All engineering effort directed at reliability. On-call reviews active incidents daily. No code changes that are not directly fixing the SLO violation. |
| >100% | **Budget exhausted.** Post-incident review mandatory. No deploys until budget recovers below 80%. Leadership notified. |

### Budget Calculation

```
budget_consumed_pct = (actual_failures / allowed_failures) * 100

# Example for Availability (99.5% target, 30-day window):
allowed_downtime_minutes = 30 * 24 * 60 * 0.005  # = 216 minutes (3.6 hours)
actual_downtime_minutes = <measured from health check failures>
budget_consumed_pct = (actual_downtime_minutes / 216) * 100
```

---

## Monthly Review Process

**When:** First Monday of each month.
**Duration:** 30 minutes.
**Participants:** System owner (Jason).

### Review Agenda

1. **SLI dashboard review** -- Review each SLO's actual performance over the past 30 days.
2. **Error budget status** -- Calculate remaining budget for each SLO. Flag any that exceeded 50%.
3. **Incident correlation** -- Map any incidents from the past month to their SLO impact.
4. **Trend analysis** -- Compare this month to prior months. Identify regressions or improvements.
5. **Action items** -- Create tasks for any SLO at risk. Update alert thresholds if needed.
6. **SLO relevance check** -- Are the current targets still appropriate? Adjust if the system's usage patterns have changed.

### Review Output

Document the review in a dated entry under `docs/operations/sre/reviews/YYYY-MM.md` with:
- SLI values for each SLO
- Budget consumption percentages
- Any incidents that burned budget
- Action items with owners and due dates
- Any SLO target adjustments (with justification)

---

## Data Sources Reference

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `session_log` | Session completion tracking | `session_outcome`, `started_at`, `ended_at`, `early_exit` |
| `security_audit_log` | Auth event tracking | `event_type`, `timestamp`, `user_id`, `severity` |
| `crash_log` | Server error tracking | `error_type`, `timestamp`, `severity`, `request_path` |
| `client_error_log` | Client-side error tracking | `error_type`, `timestamp`, `page_url` |
| Application logs | Request latency | `latency_ms` in structured log `extra` dict |
| Fly.io metrics | Health check pass/fail | `/api/health/ready` probe results |
