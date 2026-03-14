# Risk Retirement Criteria

> Last updated: 2026-03-10

## Purpose

Not every risk stays active forever. Risks that have been fully mitigated, become irrelevant, or are accepted should be retired from active tracking to keep the risk register focused. But retirement is not deletion — retired risks are monitored for reactivation.

---

## Retirement vs. Active vs. Dormant

| State | Definition | Review Frequency | Board Visibility |
|-------|-----------|------------------|-----------------|
| **Active** | Risk is real and requires ongoing attention. Mitigations are in progress or need monitoring. | Monthly | Visible on risk register |
| **Dormant** | Risk has been retired but could reactivate. Conditions that would reactivate it are defined. | Quarterly | Archived section of risk register |
| **Deleted** | Risk is no longer applicable (e.g., deprecated technology was removed). | Never | Removed entirely (with note in review log) |

---

## Evidence Requirements for Retirement

A risk cannot be retired based on feeling. It requires concrete evidence.

### General Retirement Criteria

All of these must be true:

1. **Mitigation implemented:** The planned mitigation is fully deployed, not just planned.
2. **Mitigation verified:** Testing confirms the mitigation works (not just "it didn't break").
3. **Clean period:** N consecutive days/scans without the risk materializing (N depends on risk type).
4. **No upstream changes:** The conditions that created the risk haven't changed (e.g., a dependency hasn't introduced new vulnerability surface).

### Clean Period Requirements by Category

| Risk Category | Clean Period | Evidence Type |
|--------------|-------------|---------------|
| Security (auth, injection, XSS) | 90 days without incident + penetration test pass | `security_audit_log` shows 0 unauthorized access attempts succeeding. Pen test report clean. |
| Technical (database, platform) | 60 days without incident | No `database is locked` errors in `crash_log`. No migration failures. No platform bugs in `drill_errors.log`. |
| Performance | 30 days within SLA targets | P95 response time <500ms for 30 consecutive days. No `database is locked` under normal load. |
| Compliance (GDPR, App Store) | Successful compliance action + 30 days | GDPR deletion processed within SLA. App Store review approved. |
| Operational | 60 days without incident | No outages requiring manual intervention. Backups verified weekly. |
| Market | N/A — market risks rarely retire | Market risks are accepted or mitigated, not eliminated. They go dormant when the specific threat passes. |

---

## Retirement Approval Process

Since Aelu is a solo founder operation, "approval" means structured self-review with documentation:

### Retirement Checklist

```
Risk ID:        [e.g., S-004]
Risk Title:     [e.g., SQL injection]
Current Score:  [P x I]
Retirement Date: YYYY-MM-DD

Evidence of Mitigation:
□ Mitigation implemented: [describe what was done]
□ Mitigation verified: [describe how it was tested]
□ Clean period met: [N days, date range, evidence source]
□ No upstream changes: [confirm dependencies/environment unchanged]

Reactivation Triggers:
- [Condition 1 that would reactivate this risk]
- [Condition 2]

Dormant Review Schedule: [Quarterly / Annually]

Decision: [RETIRE TO DORMANT / KEEP ACTIVE / DELETE]
Rationale: [Why this risk can be safely retired]
```

---

## Dormant Risk Monitoring

Retired risks don't disappear — they go dormant. Dormant risks are reviewed on a schedule and reactivated if conditions change.

### Quarterly Dormant Risk Review

At each quarterly review, scan all dormant risks:

| Check | Question | Action If Yes |
|-------|----------|--------------|
| Environment changed? | Has the technology, dependency, or platform changed? | Re-assess probability and impact. Consider reactivation. |
| New incident? | Has an event related to this risk occurred? | Reactivate immediately. Investigate the incident. |
| Mitigation degraded? | Has the mitigation been weakened (e.g., test removed, config changed)? | Reactivate and restore mitigation. |
| Category trend? | Are related risks in the same category increasing? | Consider reactivation as part of a trend. |

### Dormant Risk Register

| ID | Risk | Retired Date | Last Reviewed | Reactivation Triggers | Status |
|----|------|-------------|---------------|----------------------|--------|
| _(none yet — all risks are currently active)_ | | | | | |

---

## Risk Reactivation Triggers

Each dormant risk has explicit conditions that would bring it back to active status.

### Generic Reactivation Triggers

These apply to all dormant risks:

1. **Incident:** Any production incident related to the risk category.
2. **Dependency change:** The risk's mitigation depends on a library, platform, or configuration that changed.
3. **Scope expansion:** New features introduce new attack surface or failure modes in the risk's domain.
4. **Clean period violation:** A recurrence after retirement.
5. **External notification:** CVE alert, security advisory, or regulatory change related to the risk.

### Risk-Specific Reactivation Triggers (Examples)

| Risk | Reactivation Trigger |
|------|---------------------|
| S-004 (SQL injection) | Any new database query that doesn't use parameterized statements. New user input field added. |
| T-006 (macOS TTS) | Decision to support Linux desktop. Server-side TTS feature requested. |
| S-007 (Stripe webhook) | Stripe API version change. New webhook event type handled. |
| T-008 (Flask WebSocket state) | Addition of server-side session state. WebSocket protocol change. |

---

## Worked Examples

### Example 1: S-004 (SQL Injection) — Retirement Path

**Current state:** Active, Score 5 (P=1, I=5), Status: Mitigated.

**Retirement assessment:**

```
Risk ID:        S-004
Risk Title:     SQL injection — unsanitized input reaches SQLite queries
Current Score:  5 (P=1, I=5)
Retirement Date: [target after pen test]

Evidence of Mitigation:
[x] Mitigation implemented: Parameterized queries throughout codebase.
    No string concatenation for SQL. bandit static analysis in CI.
[x] Mitigation verified: bandit scan clean. Manual code review of all
    db.execute() calls confirms parameterization.
[x] Clean period met: 90 days (2026-01-10 to 2026-04-10). 0 injection
    attempts in security_audit_log. Pen test passed.
[ ] No upstream changes: No new user input fields added since review.

Reactivation Triggers:
- Any new db.execute() call added without parameterized query
- New user input field that reaches a database query
- bandit scan finds SQL injection pattern

Dormant Review Schedule: Quarterly

Decision: RETIRE TO DORMANT (pending pen test completion)
Rationale: All queries parameterized, static analysis enforces pattern,
90-day clean period with pen test verification.
```

### Example 2: Auth Bypass Risk — Why It Stays Active

**Risk S-001 (Auth bypass)** should NOT be retired despite fixing C1-C3, because:

1. **Auth is a living surface.** Every new endpoint is a potential bypass.
2. **Clean period resets** with each new route added.
3. **Impact is catastrophic** (score 5) — the cost of a false retirement is too high.
4. **Continuous testing required** — pen test quarterly, not once.

This risk will likely never retire. It should be permanently active with regular mitigation verification.

### Example 3: T-006 (macOS TTS) — Already Mitigated, Retirement Candidate

**Current state:** Active, Score 4 (P=2, I=2), Status: Mitigated.

**Assessment:** TTS was moved entirely client-side. Server has no TTS dependency. The original risk (server needs macOS `say` command) no longer applies.

```
Risk ID:        T-006
Risk Title:     macOS TTS dependency
Current Score:  4 (P=2, I=2)
Retirement Date: 2026-03-10

Evidence:
[x] TTS is browser SpeechSynthesis API (web) and macOS say (CLI only)
[x] Server deployment on Fly.io (Linux) has no TTS code paths
[x] 60 days without any TTS-related error
[x] No plans to add server-side TTS

Reactivation: Decision to support server-side TTS or Linux desktop app.
Review: Annually (low concern)

Decision: RETIRE TO DORMANT
```

---

## Retirement Anti-Patterns

| Anti-Pattern | Why It's Dangerous | Correct Approach |
|-------------|-------------------|-----------------|
| Retiring because "we haven't seen it" | Absence of evidence is not evidence of absence | Require positive evidence (pen test, clean scan), not just "nothing happened" |
| Retiring to make the register shorter | Aesthetic motivation, not risk-based | Keep active if the risk is real. A long register is better than a false sense of security. |
| Retiring after a single fix | One fix doesn't prove the risk is gone | Require clean period + verification + no upstream changes |
| Retiring market risks | Market risks don't go away | Move to dormant at best. Market risks are accepted, not eliminated. |
| Retiring without reactivation triggers | No way to know when to bring it back | Every retirement must define explicit reactivation conditions |

---

## Relationship to Other Artifacts

- **Risk Register** (`risk-register.md`): Active risks are tracked here. Retired risks move to the dormant section.
- **Risk Taxonomy** (`risk-taxonomy.md`): Category determines clean period requirements.
- **LCM Commitment Reviews** (`lcm-commitment-reviews.md`): Risk retirements are reviewed at anchor point reviews.
- **Spiral Cycle Template** (`spiral-cycle-template.md`): Risk retirement is a valid Phase 2 outcome (risk resolved).
