# Incident Postmortem: [Title]

**Date:** YYYY-MM-DD
**Severity:** P1/P2/P3/P4
**Duration:** X minutes
**Author:** [Name]
**Reviewers:** [Names]
**Status:** Draft / Final

---

## Summary

[1-2 sentence description of what happened, what broke, and who was affected.]

---

## Timeline (UTC)

| Time | Event |
|------|-------|
| HH:MM | Alert triggered: [which alert, from which system] |
| HH:MM | Alert acknowledged by [name] |
| HH:MM | Investigation started |
| HH:MM | [Key investigation finding] |
| HH:MM | Root cause identified: [brief] |
| HH:MM | Mitigation applied: [what was done] |
| HH:MM | Service recovered (health check passing) |
| HH:MM | Monitoring confirmed stable for 30 minutes |
| HH:MM | Incident closed |

---

## Impact

- **Users affected:** X out of Y total (Z%)
- **Sessions interrupted:** X
- **Requests failed:** X (Y% error rate during incident)
- **Data lost:** None / [description of any data loss]
- **SLO budget consumed by this incident:**
  - Availability: X minutes of Y-minute monthly budget (Z%)
  - Latency p95: X violations
  - Session completion: X incomplete sessions
  - Auth success: X failures

---

## Root Cause

[Technical description of what went wrong. Be specific about the chain of causation.]

[Include relevant code references, e.g.:]
- File: `mandarin/web/routes.py`, line X
- Table: `session_log`, column `session_outcome`
- Configuration: `fly.toml` health check settings

[If applicable, distinguish between the trigger (what initiated the failure) and the underlying cause (why the system was vulnerable to this trigger).]

---

## Detection

- **How was this detected?** (Fly.io health check / Sentry alert / Application log / User report / Manual observation)
- **Detection delay:** X minutes from incident start to first alert
- **Could we have detected sooner?** [Yes/No, and how]
- **Were existing alerts effective?** [Which alerts fired, which did not fire but should have]

### Detection Data Sources

| Source | What it showed | Useful? |
|--------|---------------|---------|
| `/api/health/ready` | [Response code, latency] | Yes/No |
| `crash_log` table | [Error type, count] | Yes/No |
| `security_audit_log` | [Event types seen] | Yes/No |
| Application logs | [Key log lines] | Yes/No |
| Sentry | [Exception details] | Yes/No |
| Fly.io dashboard | [Machine status] | Yes/No |

---

## Resolution

[Step-by-step description of what was done to resolve the incident.]

1. [First action taken]
2. [Second action taken]
3. [Verification step]

**Was a rollback performed?** Yes/No
**Was a deploy required?** Yes/No
**Fly.io commands used:**
```bash
# Example commands used during resolution
fly ssh console
fly machines restart
fly deploy
```

---

## Contributing Factors

[List factors that contributed to the incident occurring or being worse than it could have been. These are not "blame" items -- they are system weaknesses.]

- [ ] Missing test coverage for [specific scenario]
- [ ] No alert for [specific condition]
- [ ] Configuration not validated at startup
- [ ] Error handling swallowed the original exception
- [ ] SQLite-specific behavior (e.g., WAL mode, file locking, `datetime('now')` vs Python `datetime.now(timezone.utc)`)

---

## Action Items

| # | Action | Type | Owner | Due Date | Status |
|---|--------|------|-------|----------|--------|
| 1 | [Preventive fix to address root cause] | Prevent | | YYYY-MM-DD | TODO |
| 2 | [Improve detection -- add/tune alert] | Detect | | YYYY-MM-DD | TODO |
| 3 | [Add test coverage for failure mode] | Test | | YYYY-MM-DD | TODO |
| 4 | [Update runbook with new procedure] | Process | | YYYY-MM-DD | TODO |
| 5 | [Improve monitoring dashboard] | Observe | | YYYY-MM-DD | TODO |

### Action Item Types
- **Prevent:** Stop this class of incident from happening again
- **Detect:** Find this problem faster next time
- **Test:** Prove the fix works and prevent regression
- **Process:** Update documentation or procedures
- **Observe:** Improve visibility into system behavior

---

## Lessons Learned

### What went well?

- [Things that worked as designed]
- [Fast detection, good runbooks, effective communication]

### What went poorly?

- [Things that made the incident worse or slower to resolve]
- [Missing alerts, unclear runbooks, slow investigation]

### Where did we get lucky?

- [Things that could have been worse but were not]
- [Incidents that were mitigated by coincidence rather than design]

---

## Appendix

### Relevant Queries

```sql
-- Crash log entries during the incident window
SELECT timestamp, error_type, error_message, request_path
FROM crash_log
WHERE timestamp BETWEEN 'YYYY-MM-DD HH:MM:SS' AND 'YYYY-MM-DD HH:MM:SS'
ORDER BY timestamp;

-- Session outcomes during the incident window
SELECT session_outcome, COUNT(*) as count
FROM session_log
WHERE started_at BETWEEN 'YYYY-MM-DD HH:MM:SS' AND 'YYYY-MM-DD HH:MM:SS'
GROUP BY session_outcome;

-- Security events during the incident window
SELECT event_type, severity, COUNT(*) as count
FROM security_audit_log
WHERE timestamp BETWEEN 'YYYY-MM-DD HH:MM:SS' AND 'YYYY-MM-DD HH:MM:SS'
GROUP BY event_type, severity;
```

### Relevant Log Snippets

```
[Paste relevant application log lines here]
```

### Related Incidents

- [Link to prior postmortems for similar issues, if any]

---

**Postmortem completed:** YYYY-MM-DD
**Action items tracked in:** [location]
**Next review date:** [date to verify action items are complete]
