# Service Class Definitions

> Last updated: 2026-03-10

## Purpose

Service classes determine how work items flow through the Kanban board. Each class has a distinct cost-of-delay profile, which drives its target lead time, allocation share, escalation rules, and preemption policy. This document is the operational reference for assigning and managing service classes.

---

## Class Definitions

### Expedite

**Cost of delay profile:** Severe and immediate. Every hour of delay compounds damage.

**Qualifying conditions (any one is sufficient):**
- Security vulnerability in production (auth bypass, credential exposure, injection)
- Data loss or corruption (SQLite WAL corruption, Litestream replication failure)
- Production outage (Fly.io health check failing, app unreachable)
- Active data breach or unauthorized access visible in `security_audit_log`
- Payment processing failure (Stripe webhook errors, subscription state drift)

**Target resolution:** Same day (within 4 hours for 85th percentile, 24 hours absolute ceiling).

**Visual indicator on board:** Red card border. Card moved to top of In Progress immediately.

**Aelu examples:**
| Trigger | Detection | Expected Resolution |
|---------|-----------|-------------------|
| JWT secret exposure | Security scan, `security_audit_log` | Rotate secret, invalidate sessions — 1 hour |
| SQLite `database is locked` spike | `crash_log` > 5 errors/hour | WAL checkpoint, connection pool fix — 2 hours |
| Litestream replication stopped | Health check, monitoring | Restart replication, verify backup — 1 hour |
| Auth bypass in middleware | Penetration test, code review | Patch middleware, deploy — 4 hours |

---

### Fixed Date

**Cost of delay profile:** Binary. No cost until the deadline, then catastrophic.

**Qualifying conditions:**
- GDPR data deletion request (30-day legal requirement from request date)
- Apple App Store submission with a committed launch date
- Apple Developer Program annual renewal (account suspension if missed)
- Regulatory compliance deadline (privacy law changes, accessibility requirements)
- Contractual obligation with partner or institution (LTI integration deadlines)

**Target resolution:** Completed 3 calendar days before the external deadline.

**Visual indicator on board:** Orange card border with deadline date prominently displayed.

**Planning rules:**
- Move to Ready at least 14 calendar days before deadline
- Move to In Progress at least 7 calendar days before deadline
- If not in Review by deadline minus 5 days, escalate

**Aelu examples:**
| Item | External Deadline | Start By | Complete By |
|------|------------------|----------|-------------|
| GDPR deletion for user X | 30 days from request | Day 20 | Day 27 |
| iOS v1.1 App Store submission | 2026-03-30 | 2026-03-20 | 2026-03-27 |
| Apple Developer renewal | February 2027 | 2027-01-15 | 2027-01-28 |
| LTI integration for partner school | Per contract | Contract date minus 14 | Contract date minus 3 |

---

### Standard

**Cost of delay profile:** Linear. Each day of delay reduces the value delivered, but no single day is catastrophic.

**Qualifying conditions:**
- New features (drill types, exposure modes, graded reader content)
- UX improvements (onboarding flow, session completion screen, dashboard refinements)
- Bug fixes that are not production emergencies
- Content additions (HSK levels, dialogue scenarios, context notes)
- Marketing work (landing page, App Store listing, content posts)
- Growth experiments (A/B tests, referral programs)

**Target resolution:** 85th percentile lead time of 5 calendar days (from Ready to Done). 95th percentile: 10 days.

**Visual indicator on board:** Default card style (no special border).

**Aelu examples:**
| Item | Value | Expected Effort |
|------|-------|----------------|
| F-007: Annual pricing tier | Revenue optimization | 3-4 days |
| Listening sub-categories | Learning effectiveness | 4-5 days |
| Reddit content marketing post | Growth | 1-2 days |
| New drill type: measure word matching | Curriculum coverage | 3-4 days |

---

### Intangible

**Cost of delay profile:** Invisible today, compounding over time. You won't feel it this week, but in 3 months it becomes a crisis.

**Qualifying conditions:**
- Tech debt (dead code removal, phantom table references, unused imports)
- Refactoring for maintainability (module restructuring, function decomposition)
- Dependency updates (`pip-audit` findings, security patches, Python 3.9 EOL prep)
- Test coverage improvement (critical paths below 55% floor)
- Performance optimization not yet user-facing
- Infrastructure housekeeping (Fly.io config, Litestream verification, log rotation)
- Documentation updates (`BUILD_STATE.md`, schema docs, API docs)

**Target resolution:** 85th percentile lead time of 15 calendar days. 95th percentile: 25 days.

**Visual indicator on board:** Gray card border. Dashed border if aging past 10 days.

**Aelu examples:**
| Item | Deferred Cost | Time Horizon |
|------|--------------|-------------|
| D-004: Pin transitive dependencies | Unreproducible builds | 3 months |
| D-005: SQLite load test (100 users) | Architecture surprise | 6 months |
| Dead code removal (M1-M2) | Maintenance burden | Ongoing |
| Index optimization for 15 tables | Query performance cliff | 3-6 months |

---

## Allocation Percentages

Target allocation of throughput (items completed per month) across classes:

| Class | Target % | Acceptable Range | Alarm Threshold |
|-------|----------|-----------------|-----------------|
| Expedite | 5% | 0-10% | > 10% means production quality problem |
| Fixed Date | 15% | 5-20% | > 25% means too many external commitments |
| Standard | 60% | 50-70% | < 50% means not enough user value delivery |
| Intangible | 20% | 15-30% | < 15% means tech debt accumulating dangerously |

**Monthly check:** At the service delivery review, compute actual allocation. Record in flow metrics tracking table. Compare to targets and investigate deviations.

---

## Escalation Rules

### Aging Thresholds (triggers for attention)

| Class | Yellow Alert | Red Alert | Action |
|-------|-------------|-----------|--------|
| Expedite | 2 hours | 8 hours | Yellow: check if root cause identified. Red: accept partial fix or revert causing change. |
| Fixed Date | Deadline minus 7 days, not in In Progress | Deadline minus 3 days, not in Review | Yellow: start immediately. Red: scope-cut to minimum viable deliverable. |
| Standard | 7 days in any single column | 12 days total lead time | Yellow: identify blocker. Red: split item or reduce scope. |
| Intangible | 10 days without progress | 20 days total lead time | Yellow: is this still worth doing? Red: either commit this week or return to Backlog. |

### Escalation Path (solo founder context)

Since Aelu is a solo founder operation, "escalation" means structured self-review, not passing to a manager:

1. **Day 1 of alert:** Write a one-sentence note on the card: "Why is this aging?"
2. **Day 3 of alert:** Make a decision: split, descope, unblock, or abandon. Record the decision.
3. **Day 5 of alert (Standard/Intangible):** If no decision made, move to Backlog with a note. It's been effectively abandoned — acknowledge it.
4. **Day 1 of alert (Expedite):** Immediate. Drop everything else. If not solvable in 4 hours, revert the causing change.

---

## Preemption Policy

Preemption means interrupting in-progress work to start something of higher priority.

### Rules

1. **Expedite preempts everything.** Any in-progress item can be paused (not abandoned) when an Expedite item arrives. The paused item returns to its slot when the Expedite is resolved.

2. **Fixed Date preempts Standard and Intangible** — but only when the deadline is within 5 calendar days and the item is not yet in In Progress.

3. **Standard never preempts Standard.** Finish what you started. The pull system handles priority — the highest-priority Ready item gets pulled next.

4. **Intangible is never preempted** for its dedicated slot (slot 3). If a bug arrives, it takes slot 2, not slot 3. Intangible keeps its space.

5. **Preemption is logged.** When an item is preempted, add a note to both cards:
   - Preempted card: "Paused YYYY-MM-DD — preempted by [ITEM-ID] (Expedite)"
   - Preempting card: "Preempted [ITEM-ID] on YYYY-MM-DD"

### Preemption Frequency Review

If preemption happens more than twice per month:
- Review whether Expedite items are truly Expedite (or just urgent-feeling)
- Check if production quality investment is needed to reduce emergencies
- Consider whether WIP limits are too aggressive (items in progress are too easy to interrupt)

---

## Relationship to Other Artifacts

- **Classes of Service** (`classes-of-service.md`): Full qualifying criteria and examples for each class.
- **SLEs** (`sle.md`): Probabilistic targets derived from these service class definitions.
- **WIP Limits** (`wip-limits.md`): How each class interacts with the 3-slot In Progress structure.
- **Blocked Items Policy** (`blocked-items-policy.md`): What happens when a service class item gets blocked.
- **Flow Metrics** (`flow-metrics.md`): Data source for allocation percentage calculations.
