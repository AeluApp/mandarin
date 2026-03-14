# Incident Severity Levels

**Service:** Mandarin Learning System (Aelu)
**Owner:** Jason Gerson
**Last updated:** 2026-02-26

---

## Severity Definitions

| Level | Definition | Response Time | Resolution Target | Examples |
|-------|-----------|--------------|-------------------|----------|
| **P1 -- Critical** | Service completely down or data loss risk | 15 minutes | 1 hour | Health check failing, DB corruption, auth bypass, data deletion bug |
| **P2 -- Major** | Service degraded, partial user impact | 1 hour | 4 hours | p95 latency > 1s, error rate > 5%, sessions failing to complete, WebSocket broken |
| **P3 -- Minor** | Limited impact, workaround available | 4 hours | 24 hours | Single endpoint slow, UI rendering bug, non-critical feature broken, TTS not working |
| **P4 -- Low** | Cosmetic or minor inconvenience | Next business day | 1 week | Typo in UI, style inconsistency, documentation error, minor alignment issue |

---

## P1 -- Critical

### Criteria (any one qualifies)

- `/api/health/ready` returns 503 or times out for 3+ consecutive checks (45+ seconds)
- Database integrity check fails (`PRAGMA integrity_check` returns anything other than `ok`)
- Authentication bypass detected (users accessing protected resources without valid credentials)
- Data loss or corruption confirmed (missing rows, garbled content, schema mismatch)
- Security breach: unauthorized access, credential leak, or `CSRF_VIOLATION`/`ACCESS_DENIED` events spiking
- Fly.io machine cannot start or crashes repeatedly (restart loop)
- Litestream replication failure with no recent backup (data durability at risk)

### Examples

- SQLite database file is locked or missing on the `/data` volume
- Schema migration fails partway through, leaving tables in an inconsistent state
- `crash_log` shows the same fatal error recurring every few seconds
- `security_audit_log` shows `login_success` events for a locked or deactivated account

### Response Protocol

1. **Acknowledge** within 15 minutes.
2. **Assess** the blast radius: how many users are affected, is data at risk?
3. **Mitigate** immediately: restart the machine, roll back the last deploy, or disable the affected feature.
4. **Communicate** status via the incident communication template (see below).
5. **Resolve** root cause within 1 hour. If not possible, escalate.
6. **Postmortem** required within 48 hours (see `postmortem-template.md`).

---

## P2 -- Major

### Criteria (any one qualifies)

- p95 API latency exceeds 1000ms for 10+ consecutive minutes
- Error rate (5xx responses) exceeds 5% of total requests over a 5-minute window
- Session completion rate drops below 95% over a 1-hour window
- `crash_log` accumulates more than 10 new entries in 5 minutes
- WebSocket connections failing (drill sessions cannot function)
- Auth failure rate spikes (50+ `login_failed` events from a single IP in 1 hour)
- Sentry alert fires for a new, previously unseen exception class

### Examples

- A slow SQL query causes all `/api/session` responses to take 3+ seconds
- A deploy introduces a bug that crashes 1 in 10 drill completions
- Rate limiter misconfigured, blocking legitimate users
- Memory pressure on the `shared-cpu-1x` Fly.io VM causing swap thrashing

### Response Protocol

1. **Acknowledge** within 1 hour.
2. **Investigate** using the relevant runbook (see `alert-rules.md` for runbook links).
3. **Mitigate** by rolling back the recent deploy or applying a targeted fix.
4. **Monitor** for 30 minutes after mitigation to confirm recovery.
5. **Postmortem** required within 5 business days for P2 incidents that consumed >10% of any SLO error budget.

---

## P3 -- Minor

### Criteria (any one qualifies)

- A single non-critical endpoint is slow or returning errors
- UI rendering issue that does not block core functionality (drills, sessions, auth)
- A specific drill type is broken but others work fine
- TTS audio not playing (macOS `say` command issue)
- Non-critical background task failing (email scheduler, retention scheduler)
- Client-side JavaScript error logged to `client_error_log` but not blocking usage
- Alert for error budget consumption crossing 50%

### Examples

- `/api/reading/passages` returns 500 but the rest of the app works
- Dark mode CSS variables rendering incorrectly in one browser
- The `encounters` CLI command throws an error
- Weekly email digest fails to send

### Response Protocol

1. **Acknowledge** within 4 hours.
2. **Triage** and add to the work queue with appropriate priority.
3. **Fix** within 24 hours during normal working hours.
4. **No postmortem required** unless the issue recurs 3+ times.

---

## P4 -- Low

### Criteria

- Cosmetic issues: typos, minor spacing, color inconsistencies
- Documentation errors or omissions
- Feature requests that surface during incident investigation
- Performance improvements that are nice-to-have but not SLO-impacting

### Examples

- Typo in a drill prompt
- Pinyin tone mark slightly misaligned in one font size
- Missing context note for a content item
- A log message has a misleading format string

### Response Protocol

1. **Log** the issue in the backlog.
2. **Fix** at next convenience, within 1 week.
3. **No formal incident process required.**

---

## Escalation Matrix

| Trigger | Action | Who |
|---------|--------|-----|
| P1 detected | Immediate page/notification | System owner (Jason) |
| P1 not acknowledged in 15 min | Alert delivery failure logged to `security_audit_log` | Automated (`_send_critical_alert` in `security.py`) |
| P2 not acknowledged in 1 hour | Re-send alert, bump to P1 consideration | System owner |
| P2 consuming >20% error budget | Schedule immediate investigation | System owner |
| P3 recurring 3+ times | Promote to P2, require postmortem | System owner |
| Any severity with data loss confirmed | Immediately promote to P1 | System owner |

### Alert Delivery Channels

| Channel | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| Webhook (Slack/Discord) | Yes | Yes | No | No |
| Email (`ADMIN_EMAIL`) | Yes | Yes | Yes (digest) | No |
| Application log | Yes | Yes | Yes | Yes |
| `security_audit_log` table | Yes (security events) | Yes (security events) | Yes (security events) | No |
| Sentry | Yes | Yes | Yes | No |

Alert delivery is implemented in `security.py` via `_send_critical_alert()`, which attempts both webhook (`ALERT_WEBHOOK_URL` env var) and email (`ADMIN_EMAIL` env var). If both fail, the failure itself is logged to `security_audit_log` with event type `alert_delivery_failure` and severity `CRITICAL`.

---

## Communication Templates

### P1 -- Initial Notification

```
INCIDENT: P1 -- [Brief description]
STATUS: Investigating
IMPACT: [Service down / Data at risk / Auth broken]
STARTED: YYYY-MM-DD HH:MM UTC
NEXT UPDATE: [15 minutes from now]

We are aware of [description]. The on-call engineer is investigating.
User impact: [X users affected / all users / specific feature].
```

### P1/P2 -- Status Update

```
INCIDENT UPDATE: P[1/2] -- [Brief description]
STATUS: [Investigating / Identified / Mitigating / Resolved]
DURATION: X minutes so far
IMPACT: [Updated impact assessment]
NEXT UPDATE: [Time]

[What we know so far]
[What we are doing about it]
[Expected resolution time, if known]
```

### P1/P2 -- Resolution

```
INCIDENT RESOLVED: P[1/2] -- [Brief description]
DURATION: X minutes
IMPACT: [Final impact assessment]
ROOT CAUSE: [1-sentence summary]

The incident has been resolved. [Brief description of the fix].
A postmortem will be published within [48 hours / 5 business days].
```

---

## Severity Reclassification

Incidents may be reclassified during investigation:

- **Upgrade:** If investigation reveals broader impact than initially assessed (e.g., a P3 endpoint failure is actually caused by DB corruption -- upgrade to P1).
- **Downgrade:** If mitigation reduces impact significantly (e.g., a P2 latency issue is resolved by restarting the machine and only affected 2 requests -- downgrade to P3).

Document all reclassifications in the incident timeline with the reason.
