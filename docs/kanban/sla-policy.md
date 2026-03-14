# Service Level Agreements (SLA Policy)

> Last updated: 2026-03-10

## SLA vs. SLE Distinction

- **SLE (Service Level Expectation):** A probabilistic forecast based on historical data. "We expect 85% of Standard items to finish in 14 days." See `sle.md`.
- **SLA (Service Level Agreement):** A commitment with consequences. This document defines the commitments Aelu makes to its stakeholders — users, the platform, and the developer — with explicit breach handling.

SLAs are stricter than SLEs. An SLE informs planning. An SLA triggers action when breached.

---

## SLA Targets by Service Class

### Expedite (Security, Data Loss, Outages)

| Percentile | Lead Time Target | Measurement Start | Measurement End |
|------------|-----------------|-------------------|-----------------|
| 50th | 1 hour | Alert fired or issue discovered | Fix deployed to production |
| 85th | 4 hours | Alert fired or issue discovered | Fix deployed to production |
| 95th | 8 hours | Alert fired or issue discovered | Fix deployed to production |
| 100th (ceiling) | 24 hours | Alert fired or issue discovered | Fix deployed or causing change reverted |

**Data sources:** `crash_log` table, `security_audit_log` table, Fly.io health check logs, Stripe webhook failure logs.

**Breach consequence:** Post-incident review within 48 hours. If the 85th percentile SLA is breached more than once per quarter, invest in monitoring/alerting improvements before new feature work.

---

### Fixed Date (Compliance, Releases)

| Percentile | Lead Time Target | Measurement Start | Measurement End |
|------------|-----------------|-------------------|-----------------|
| 50th | Deadline minus 7 days | Item enters Ready | Deployed to production |
| 85th | Deadline minus 5 days | Item enters Ready | Deployed to production |
| 95th | Deadline minus 3 days | Item enters Ready | Deployed to production |
| 100th (ceiling) | Deadline minus 1 day | Item enters Ready | Deployed to production |

**Critical fixed-date items with hard SLAs:**

| Item Type | Legal/External Deadline | Aelu SLA |
|-----------|----------------------|----------|
| GDPR deletion request | 30 days from request | Completed by day 25 |
| GDPR data export request | 30 days from request | Completed by day 25 |
| Apple App Store submission | Per release plan | Submitted 5 business days before target |
| Apple Developer renewal | Annual (February) | Renewed by January 25 |

**Breach consequence:** If a legal deadline (GDPR) is at risk of breach, all other work stops until it is resolved. Legal compliance is non-negotiable.

---

### Standard (Features, Improvements)

| Percentile | Lead Time Target | Measurement Start | Measurement End |
|------------|-----------------|-------------------|-----------------|
| 50th | 3 days | Item moves to Ready | Item moves to Done |
| 85th | 5 days | Item moves to Ready | Item moves to Done |
| 95th | 10 days | Item moves to Ready | Item moves to Done |

**Note:** Lead time here is measured from Ready (commitment point), not from Backlog entry. Time in Backlog is pre-commitment and not subject to SLA.

**Breach consequence:** If >15% of Standard items breach the 85th percentile target in a given month, hold a service delivery review. Investigate: scope too large? Blockers? Capacity?

---

### Intangible (Tech Debt, Refactoring)

| Percentile | Lead Time Target | Measurement Start | Measurement End |
|------------|-----------------|-------------------|-----------------|
| 50th | 5 days | Item moves to Ready | Item moves to Done |
| 85th | 15 days | Item moves to Ready | Item moves to Done |
| 95th | 25 days | Item moves to Ready | Item moves to Done |

**Breach consequence:** If Intangible items consistently exceed 25 days, they are effectively abandoned. At the monthly review, decide: commit to finishing this week, or return to Backlog with a note.

---

## Measurement Method

### Commitment Point

The SLA clock starts when an item moves from **Backlog to Ready**. This is the commitment point — the moment the team (solo founder) commits to delivering this item in the near term.

Items in Backlog are options, not commitments. No SLA applies to Backlog residence time.

### Completion Point

The SLA clock stops when an item moves to **Done**, which means:
1. Code is deployed to production (Fly.io)
2. Any necessary database migration has run
3. The feature is accessible to users (not behind a disabled flag)
4. Manual verification confirms basic functionality

### Time Tracking

For each item, track these timestamps on the Kanban card:

```
Date Entered Backlog:  YYYY-MM-DD
Date Moved to Ready:   YYYY-MM-DD  ← SLA clock starts
Date Started:          YYYY-MM-DD  ← Cycle time starts
Date Moved to Review:  YYYY-MM-DD
Date Done:             YYYY-MM-DD  ← SLA clock stops
Lead Time (SLA):       [Date Done - Date Moved to Ready] days
Cycle Time:            [Date Done - Date Started] days
Queue Time:            [Date Started - Date Moved to Ready] days
```

---

## Breach Notification Process

Since Aelu is a solo founder operation, "notification" means structured self-alerting:

### Real-Time Alerts (Expedite only)

1. **Health check failure:** Fly.io alerts via webhook. Check within 15 minutes.
2. **Security scan finding:** `pip-audit` or `bandit` finding in CI. Triage within 1 hour.
3. **crash_log spike:** >5 unhandled exceptions in 1 hour. Investigate immediately.

### Daily Check (all classes)

During the daily standup (even solo, review the board daily):
1. Check aging items against SLA thresholds
2. Any item within 2 days of its SLA target gets a yellow flag
3. Any item past its 85th percentile SLA target gets a red flag
4. Red-flagged items require a same-day decision: finish, split, descope, or return to Backlog

### Weekly Review

At the weekly replenishment meeting:
1. Calculate SLA achievement rate per class for the past 7 days
2. Identify any items approaching breach
3. Adjust priorities if SLA compliance is trending down

---

## SLA Review Frequency

| Review Type | Frequency | Scope | Output |
|-------------|-----------|-------|--------|
| Daily board scan | Daily | All in-progress items | Flag aging items |
| Weekly SLA check | Weekly | Items completed + in progress | Achievement rate snapshot |
| Monthly service delivery review | Monthly | Full month of data | Formal SLA achievement report |
| Quarterly SLA adjustment | Quarterly | Historical trends | SLA target revisions if warranted |

---

## Historical Data Tracking Template

Record monthly SLA performance in this table. Update at each service delivery review.

### Monthly SLA Achievement

| Month | Expedite P85 (<4h) | Fixed Date (buffer>=3d) | Standard P85 (<5d) | Intangible P85 (<15d) | Overall % |
|-------|--------------------|-----------------------|--------------------|-----------------------|-----------|
| Feb 2026 | 3/3 = 100% | 0/0 = N/A | 3/4 = 75% | 2/2 = 100% | 89% |
| Mar 2026 | — | — | — | — | — |
| Apr 2026 | — | — | — | — | — |
| May 2026 | — | — | — | — | — |
| Jun 2026 | — | — | — | — | — |

### Lead Time Distribution (days)

| Month | Class | P50 | P85 | P95 | Sample Size | Notes |
|-------|-------|-----|-----|-----|-------------|-------|
| Feb 2026 | Standard | 3 | 6 | 9 | 4 | Early data, small sample |
| Feb 2026 | Intangible | 4 | 8 | — | 2 | Too few items for P95 |
| Mar 2026 | — | — | — | — | — | — |

### Breach Log

| Date | Item ID | Class | SLA Target | Actual | Root Cause | Corrective Action |
|------|---------|-------|------------|--------|------------|-------------------|
| 2026-02-18 | F-005 | Standard | 5 days | 7 days | Scope underestimated (FSRS tuning) | Split FSRS changes into sub-tasks |

---

## SLA Adjustment Policy

SLA targets are not permanent. They should reflect actual capability and evolve with the system.

**Tighten SLAs when:**
- Achievement rate exceeds 95% for 3 consecutive months (targets are too easy)
- System stability improves (fewer Expedite items)
- Tooling improvements reduce cycle time

**Loosen SLAs when:**
- Achievement rate drops below 70% for 2 consecutive months despite process improvements
- Scope of work has genuinely changed (e.g., shift from building to marketing)
- External factors increase lead time (e.g., App Store review delays)

**Process:** Propose change at quarterly review. Document the old target, new target, and rationale. Never adjust SLAs retroactively — they apply going forward.

---

## Relationship to Other Artifacts

- **SLEs** (`sle.md`): Probabilistic forecasts that inform SLA targets.
- **Service Classes** (`service-classes.md`): Defines the classes to which SLAs apply.
- **Flow Metrics** (`flow-metrics.md`): Provides raw data for SLA measurement.
- **Blocked Items Policy** (`blocked-items-policy.md`): Blocked time counts against the SLA — blocking extends lead time.
