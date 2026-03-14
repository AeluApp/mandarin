# Post-Launch Monitoring Guide

Operational monitoring for Aelu. Each section: what to check, how often, what is normal, what needs action.

---

## 1. Health Checks

### Endpoints

| Endpoint | Purpose | Check Frequency |
|----------|---------|-----------------|
| `/api/health/live` | Liveness probe (process alive) | Every 10s (Fly.io) |
| `/api/health/ready` | Readiness probe (DB writable, schema current) | Every 15s (Fly.io) |
| `/api/health` | Full health (DB + schema + content + uptime + error rate) | Every 60s (external monitor) |

### Expected Responses

**`/api/health/live`** (200 OK):
```json
{"status": "ok", "uptime_seconds": 86400}
```

**`/api/health/ready`** (200 OK):
```json
{"status": "ok", "latency_ms": 1.2}
```
Returns 503 with `"status": "not_ready"` if schema migration is pending or DB is unreachable.

**`/api/health`** (200 OK):
```json
{
  "status": "ok",
  "schema_version": 45,
  "schema_current": true,
  "item_count": 299,
  "tables": 16,
  "uptime_seconds": 86400,
  "latency_ms": 2.5,
  "database_size_mb": 12.5,
  "error_rate_5m": 0
}
```

### Alert Thresholds

| Condition | Severity | Action |
|-----------|----------|--------|
| `/api/health/live` non-200 | P1 | Restart container immediately |
| `/api/health/ready` returns 503 | P2 | Check if migration is running; if stuck, check logs |
| `latency_ms` > 100 on `/api/health` | P3 | Investigate slow queries, consider VACUUM |
| `error_rate_5m` > 5 | P2 | Check Sentry, review recent deploys |
| `database_size_mb` > 500 | P3 | Schedule VACUUM, review data retention |
| `schema_current` is false | P2 | Migration pending -- check application logs |

### Checking Health Manually

```bash
# From local
curl -s https://aelu.app/api/health | python -m json.tool

# From Fly.io
fly ssh console -C "curl -s localhost:8080/api/health"
```

---

## 2. Sentry

### Setup

Sentry is initialized in `mandarin/web/__init__.py` when `SENTRY_DSN` is set. The integration uses `FlaskIntegration()` with a configurable `traces_sample_rate` (from `settings.py`). A `before_send` filter (`_sentry_filter`) drops 401 and 404 errors to reduce noise.

### How to Review Errors

1. Open the Sentry dashboard for the Aelu project.
2. Check the **Issues** tab, sorted by "Last Seen" or "Events" count.
3. Priority issues: anything with severity "error" or "fatal" that appeared after a deploy.
4. Ignore issues: 401/404 (filtered by `_sentry_filter`), rate limit 429 (expected behavior).

### Configuring Alerts

Set up Sentry alert rules for:

| Alert | Condition | Channel |
|-------|-----------|---------|
| New issue | First occurrence of an error type | Email + Slack |
| Regression | Previously resolved issue reappears | Email + Slack |
| Spike | > 10 events in 5 minutes for any issue | Slack (urgent) |
| Performance | p95 transaction time > 2s | Email |

### How Often

- **Daily**: Glance at the Sentry dashboard for new issues. Takes 2 minutes.
- **After each deploy**: Watch Sentry for 15 minutes for regressions.
- **Weekly**: Review unresolved issues, close stale ones, assign priorities.

### What Needs Action

- Any new "fatal" or "error" issue that appeared after a deploy: investigate immediately.
- Crash rate above 0.1% of sessions: roll back the deploy.
- Repeated `sqlite3.OperationalError` in Sentry: database may be locked or corrupted.

---

## 3. Database (Litestream Replication)

### Architecture

Aelu uses SQLite with Litestream for continuous replication to object storage (S3-compatible). The database file lives at the path configured in `settings.DB_PATH`.

### Checking Replication Status

```bash
# On the Fly.io machine
fly ssh console -C "litestream replicas list /data/mandarin.db"

# Check replication lag (should be < 10s)
fly ssh console -C "litestream wal list /data/mandarin.db"
```

### Verifying Backups

```bash
# List available snapshots
litestream snapshots list s3://your-bucket/mandarin.db

# Restore to a test location to verify integrity
litestream restore -o /tmp/mandarin-test.db s3://your-bucket/mandarin.db
sqlite3 /tmp/mandarin-test.db "PRAGMA integrity_check"
```

### How Often

| Check | Frequency |
|-------|-----------|
| Replication lag | Daily (automated) |
| Backup restore test | Weekly |
| Integrity check | Weekly |
| DB file size | Daily (via `/api/health` `database_size_mb`) |

### What Is Normal

- Replication lag < 10 seconds
- DB size grows ~1-5 MB/week with normal usage
- `PRAGMA integrity_check` returns "ok"
- WAL mode enabled (`PRAGMA journal_mode` returns "wal")

### What Needs Action

- Replication lag > 60 seconds: check network, storage quota
- `integrity_check` returns anything other than "ok": stop writes, restore from backup
- DB file > 500 MB: run `VACUUM`, review data retention policies
- WAL file larger than DB file: run checkpoint (`PRAGMA wal_checkpoint(TRUNCATE)`)

---

## 4. Financial Monitoring

### Location

`mandarin/openclaw/financial_monitor.py`

### Running the Weekly Digest

```python
from mandarin import db
from mandarin.openclaw.financial_monitor import FinancialMonitor

with db.connection() as conn:
    monitor = FinancialMonitor(conn)
    digest = monitor.weekly_digest()
    print(monitor.format_digest(digest))
```

Or via the admin API: `GET /api/admin/revenue` (requires admin + MFA).

### How Often

- **Weekly**: Run the full digest on Monday morning.
- **Daily**: Check the admin dashboard revenue tab.
- **Immediately**: If anomaly alerts fire.

### What the Digest Contains

| Section | Content |
|---------|---------|
| Revenue snapshot | MRR, ARR, paying customers, conversion rate, ARPU |
| Churn report | Churn rate, churned user list, at-risk users, reason breakdown |
| Anomalies | Failed payment spikes, refund clusters, revenue drops, suspicious signups |
| Action items | Auto-generated from anomalies and churn data |

### Anomaly Types and Responses

| Anomaly | Threshold | Response |
|---------|-----------|----------|
| `FAILED_PAYMENT_SPIKE` | 2x baseline failed payments | Check Stripe dashboard for processor issues; verify webhook delivery |
| `REFUND_CLUSTER` | 3+ refunds in 24h | Review refund reasons; check for service quality issues |
| `REVENUE_DROP` | 10%+ WoW new subscription decline | Check marketing channels, landing page conversion, trial experience |
| `SUSPICIOUS_SIGNUPS` | 20+ signups in 24h | Check for bot registrations; review signup sources; verify invite code enforcement |

### What Is Normal

- MRR grows or stays flat week-over-week
- Churn rate < 5% monthly for early-stage
- 0-1 anomalies per week
- At-risk users < 20% of paying base

### What Needs Action

- Churn rate > 10%: run win-back campaign, review onboarding flow
- Any "high" or "critical" severity anomaly: investigate within 4 hours
- Revenue drop > 20% WoW: treat as P2 incident

---

## 5. Compliance Monitoring

### Location

`mandarin/openclaw/compliance_monitor.py`

### Running the Weekly Brief

```python
from mandarin.openclaw.compliance_monitor import ComplianceMonitor

monitor = ComplianceMonitor()
print(monitor.weekly_brief())
```

For full audit:
```python
report = monitor.audit()
print(monitor.format_report(report))
```

### How Often

- **Weekly**: Run the brief to check overall posture and upcoming deadlines.
- **Monthly**: Run the full audit to review all compliance surfaces.
- **On regulatory news**: Use `assess_change()` to evaluate impact of new developments.

### What the Brief Contains

- Overall compliance posture (compliant / attention_needed / action_required)
- Top action items by urgency
- Upcoming regulatory deadlines (EU AI Act milestones, Colorado AI Act, CPRA rules)

### Compliance Surfaces Monitored

| Surface | Risk Level | Key Frameworks |
|---------|-----------|----------------|
| Learner data collection | Medium | GDPR, CPRA, FERPA |
| Audio recordings | High | GDPR, CPRA, state AI laws |
| AI-generated content | Low | EU AI Act |
| Learning analytics | Medium | EU AI Act, GDPR |
| Institutional data | High | FERPA |
| Payment processing | Low | GDPR, CPRA |
| Marketing emails | Low | GDPR, CPRA |
| Children's data | Medium | COPPA, GDPR |
| Cross-border transfer | Medium | GDPR |
| Automated decisions | Low | GDPR, EU AI Act |

### What Action Items Mean

- **High urgency**: Regulatory gap with compliance deadline approaching. Address within 2 weeks.
- **Medium urgency**: Known gap without immediate deadline. Address within 30 days.
- **Low urgency**: Recommendation for improving posture. Address when convenient.

### Key Known Gaps

1. **No age verification** (COPPA risk): Terms require 13+, but no enforcement mechanism.
2. **Cross-border data transfer**: EU-US transfer mechanism needs documentation.

### Responding to Action Items

1. Read the full description to understand the gap.
2. Check whether existing controls already cover it (the checker may flag theoretical gaps).
3. For regulatory changes, use `monitor.assess_change(description, framework)` to evaluate Aelu-specific impact.
4. File a work item in the admin kanban (`POST /api/admin/work-items`) with the remediation plan.

---

## 6. Support Queue

### Architecture

The support agent (`mandarin/openclaw/support_agent.py`) handles customer support by:
- Matching incoming tickets against a knowledge base
- Attempting automated resolution (FAQ matching, DB troubleshooting)
- Escalating unresolved tickets for human review

### How to Review Escalated Tickets

Check the admin dashboard notifications tab, which includes a "Support escalation" alert source. Escalated tickets require human judgment -- the agent could not confidently resolve them.

### How Often

- **Daily**: Check the admin notifications tab for escalated tickets.
- **Within 4 hours**: Respond to any P1/P2 escalations.
- **Weekly**: Review resolved tickets for patterns that could be added to the knowledge base.

### What Is Normal

- Most tickets resolved automatically by FAQ matching
- 1-5 escalations per week for an early-stage product
- Common topics: password reset issues, billing questions, feature requests

### What Needs Action

- Escalation volume > 10/day: likely a systemic issue (bug, outage, confusing UX)
- Repeated escalations about the same topic: add to knowledge base, fix the root cause
- Any ticket mentioning data loss or security concern: treat as P1

---

## 7. Onboarding

### Architecture

The onboarding agent (`mandarin/openclaw/onboarding_agent.py`) tracks user lifecycle, detects churn risk signals, and plans interventions.

### How to Review Intervention History

```python
from mandarin import db
from mandarin.openclaw.onboarding_agent import OnboardingAgent

agent = OnboardingAgent()
with db.connection() as conn:
    history = agent.get_intervention_history(conn, user_id=123)
    for h in history:
        print(h)
```

Or via admin API: `GET /api/admin/student/{student_id}` shows individual learner intervention data.

### How Often

- **Weekly**: Review the admin notifications for "inactive students" and "struggling students" alerts.
- **Monthly**: Audit intervention effectiveness -- are users who received interventions retained?

### When to Manually Reach Out

| Signal | Action |
|--------|--------|
| Paid user inactive > 7 days | Send a personal check-in email |
| User completed 0 sessions after signup (3+ days) | Trigger welcome drip sequence |
| User's accuracy dropped below 50% for 3 sessions | Review their content level; may need HSK adjustment |
| User submitted grade appeal | Review within 48 hours |
| User used "streak freeze" twice in a month | Engagement is declining; consider personal outreach |

### What Is Normal

- 60-70% of signups complete their first session within 48 hours
- Activation rate (signup to activated): varies by channel, 20-40% is reasonable early
- D7 retention: 30-50% for engaged users
- D30 retention: 15-30%

### What Needs Action

- Activation rate drops below 15%: review the first-session experience
- D7 retention drops below 20%: investigate session quality and difficulty calibration
- Churn risk users accumulating: run the intervention pipeline more aggressively

---

## 8. Performance

### Request Latency

The Flask app logs every request with `latency_ms` (in `mandarin/web/__init__.py`). Requests exceeding `SLOW_REQUEST_THRESHOLD_MS` (from `settings.py`) are logged at WARNING level.

### What Is Normal

| Endpoint Type | Normal p50 | Normal p95 | Investigate If |
|---------------|-----------|-----------|----------------|
| Health checks | 1-5 ms | < 20 ms | > 100 ms |
| API JSON endpoints | 10-50 ms | < 200 ms | > 500 ms |
| Dashboard page | 50-200 ms | < 500 ms | > 1000 ms |
| WebSocket session | N/A (persistent) | N/A | > 5s to first drill |

### How to Investigate

1. Check the `/api/health` `latency_ms` field for DB query time.
2. Search application logs for "Slow request" warnings.
3. Check DB file size (`database_size_mb` from health endpoint).
4. Common causes: missing indexes, large result sets, WAL file bloat.

```bash
# Check for slow queries in logs
fly logs --app mandarin | grep "Slow request"

# Check DB indexes
fly ssh console -C "sqlite3 /data/mandarin.db '.indexes'"

# Run ANALYZE to update query planner stats
fly ssh console -C "sqlite3 /data/mandarin.db 'ANALYZE'"
```

### How Often

- **Continuously**: Slow request warnings are logged automatically.
- **Daily**: Check the admin dashboard for latency trends.
- **After deploys**: Watch p95 for 15 minutes.

### SLO Targets (from operations/sre/slo-sli.md)

- Availability: 99.5% (< 3.6h/month downtime)
- Latency: p95 < 500ms, p99 < 2000ms
- Session reliability: 99% of WebSocket sessions complete successfully

---

## 9. Security

### Audit Log Location

Security events are logged to the `security_audit_log` table. They are queryable via:
- Admin API: `GET /api/admin/security-events` (paginated)
- Admin dashboard: Security tab
- Direct DB query (for incident response)

### What Events Are Logged

| Event Type | Severity | What It Means |
|------------|----------|---------------|
| `LOGIN` | INFO | Successful login |
| `LOGOUT` | INFO | User logged out |
| `MFA_VERIFIED` | INFO | MFA code accepted |
| `MFA_FAILED` | WARNING | Invalid MFA code at login |
| `PASSWORD_CHANGED` | INFO | User changed password |
| `PASSWORD_RESET_FAILED` | WARNING | Wrong old password on change-password |
| `ADMIN_ACCESS` | INFO | Admin page or API accessed |
| `ACCESS_DENIED` | WARNING | Non-admin tried admin route |
| `CSRF_VIOLATION` | WARNING | Missing X-Requested-With header on API POST |
| `RATE_LIMIT_HIT` | WARNING | Request rate limit exceeded |
| `OPEN_REDIRECT_BLOCKED` | WARNING | Attempted redirect to external URL |
| `DATA_EXPORT_REQUESTED` | INFO | GDPR data export |
| `DATA_DELETION_REQUESTED` | INFO | GDPR deletion initiated |
| `DATA_DELETION_COMPLETED` | INFO | GDPR deletion completed |

### What to Look For

- **Brute force**: Multiple `MFA_FAILED` or failed login attempts from same IP.
- **Privilege escalation**: `ACCESS_DENIED` events from authenticated users.
- **CSRF attacks**: `CSRF_VIOLATION` events, especially from unfamiliar origins.
- **Data exfiltration**: Unusual volume of `DATA_EXPORT_REQUESTED` events.
- **Account takeover**: `PASSWORD_CHANGED` followed by unusual activity.

### How Often

- **Daily**: Review WARNING and higher severity events in the admin dashboard.
- **Weekly**: Run the security scan (`POST /api/admin/security-scans/trigger`) and review findings.
- **After any security incident**: Full audit log review for the affected time window.

### Security Scan

The automated security scanner (triggered via admin API or the `security_scan_scheduler`) checks for:
- Weak passwords, unverified emails
- Stale sessions, orphaned data
- Configuration issues

```bash
# View recent scans
curl -s https://aelu.app/api/admin/security-scans -H "Cookie: ..."

# Trigger a manual scan
curl -s -X POST https://aelu.app/api/admin/security-scans/trigger -H "Cookie: ..."
```

---

## 10. Uptime Monitoring (External)

### Why External Monitoring

Internal health checks verify the app is healthy from inside. External monitoring verifies it is reachable from the internet and responding correctly.

### Recommended Setup: UptimeRobot (Free Tier)

1. Create an account at [uptimerobot.com](https://uptimerobot.com).
2. Add three monitors:

| Monitor | Type | URL | Interval | Alert |
|---------|------|-----|----------|-------|
| Liveness | HTTP(s) | `https://aelu.app/api/health/live` | 60s | Expect 200 + body contains `"ok"` |
| Readiness | HTTP(s) | `https://aelu.app/api/health/ready` | 60s | Expect 200 |
| Full health | HTTP(s) | `https://aelu.app/api/health` | 300s | Expect 200 + body contains `"ok"` |

3. Configure alert contacts: email + Slack webhook.

### Alternative: Pingdom

Same configuration as above. Pingdom offers real-user monitoring (RUM) and multi-location checks.

### Alternative: Fly.io Built-in

Fly.io health checks (configured in `fly.toml`) handle liveness/readiness for the platform. These are sufficient for container restart decisions but do not provide external uptime reporting or historical SLA data.

### Status Page

Consider setting up a public status page (e.g., Instatus, Atlassian Statuspage, or UptimeRobot's built-in page) that shows:
- Current uptime percentage
- Incident history
- Scheduled maintenance windows

### What Is Normal

- 99.5%+ uptime over 30 days (per SLO)
- Brief blips during deploys (< 30s) are expected with zero-downtime deploys
- Health check latency from external monitors: < 500ms from US/EU

### What Needs Action

- Downtime > 5 minutes: check Fly.io status, verify deploy succeeded, check Sentry
- Repeated 503 from readiness probe: schema migration stuck or DB issue
- Latency > 2s from external monitors: check Fly.io region, consider adding regions

---

## Quick Daily Checklist (5 minutes)

1. Open Sentry: any new issues since yesterday?
2. Check `/api/health` response: status ok, latency < 50ms, error_rate_5m = 0?
3. Glance at admin dashboard: any notification badges?
4. Check UptimeRobot: any downtime reported overnight?

## Weekly Review Checklist (30 minutes)

1. Run financial digest and review anomalies
2. Run compliance brief and check upcoming deadlines
3. Review Sentry unresolved issues: close stale, prioritize new
4. Check admin security events for anomalies
5. Run or review automated security scan
6. Review onboarding metrics: activation rate, D7 retention
7. Verify Litestream backup by test-restoring to a temp file
8. Check DB size trend (is it growing abnormally?)
