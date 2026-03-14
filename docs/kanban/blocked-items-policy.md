# Blocked Items Policy

> Last updated: 2026-03-10

## Purpose

Blocked items are the silent killers of flow. An item that sits in In Progress but can't make progress inflates WIP, distorts cycle time, and wastes cognitive overhead. This policy defines what "blocked" means, how to categorize blockers, when to escalate, and how to prevent recurrence.

---

## Definitions

### Blocked vs. Waiting

| State | Definition | Board Indicator | SLA Impact |
|-------|-----------|-----------------|------------|
| **Blocked** | Work cannot continue. A dependency, decision, or technical obstacle prevents any forward progress. | Red flag icon on card | Clock keeps ticking. Blocked time counts against SLA. |
| **Waiting** | Work is paused for a routine external process (e.g., App Store review, DNS propagation). Progress will resume automatically without intervention. | Yellow flag icon on card | Clock keeps ticking, but waiting is expected and accounted for in SLA targets. |
| **Active** | Work is progressing normally. | No flag | Normal flow. |

**Key distinction:** Blocked items need someone to do something. Waiting items need time to pass.

---

## Blocker Categorization

Every blocked item must have a categorized blocker. This feeds into root cause analysis and process improvement.

### Internal Blockers

Obstacles within Aelu's control. These are the most actionable.

| Category | Description | Aelu Examples |
|----------|-------------|---------------|
| **Scope ambiguity** | Requirements unclear, acceptance criteria missing | "What should the error message say for failed tone grading?" |
| **Technical dependency** | One item blocks another within the system | "Can't build listening sub-categories until reading API is stable" |
| **Design decision** | A choice must be made before work can continue | "FSRS vs. SM-2 for the new drill type — need to decide algorithm" |
| **Knowledge gap** | Don't know how to implement something | "How does Capacitor handle background audio on iOS?" |
| **Test infrastructure** | Can't verify the work | "Need test fixtures for classroom/LTI integration" |

### External Blockers

Obstacles outside Aelu's control. Mitigation focuses on reducing dependency.

| Category | Description | Aelu Examples |
|----------|-------------|---------------|
| **Third-party API** | Waiting on external service behavior | "Stripe API change breaks webhook signature verification" |
| **App Store review** | Apple review process | "iOS build submitted, awaiting review (typically 24-48 hours)" |
| **Dependency update** | Upstream library issue | "parselmouth won't build on Python 3.9 — no fix available" |
| **Regulatory clarification** | Legal/compliance question | "GDPR: does browser TTS count as data processing?" |

### Technical Blockers

System-level obstacles that require investigation or architectural changes.

| Category | Description | Aelu Examples |
|----------|-------------|---------------|
| **Infrastructure** | Hosting, deployment, or environment issue | "Fly.io machine won't start after config change" |
| **Database limitation** | SQLite constraint | "Can't ALTER CHECK constraint — must recreate table" |
| **Platform incompatibility** | Cross-platform issue | "CSP `upgrade-insecure-requests` breaks localhost asset loading" |
| **Performance** | System too slow to proceed | "SQLite concurrent writes causing `database is locked`" |
| **Build/toolchain** | Compilation or packaging failure | "Python 3.9.6 missing `zoneinfo` — need `backports.zoneinfo`" |

---

## Visual Indicators on the Kanban Board

Blocked and waiting items must be visually distinct on the board. Never let a blocked item look like active work.

### Card Markings

```
┌─────────────────────────────┐
│ 🔴 BLOCKED                  │  ← Red flag in top-left
│ F-011: Listening drill types│
│ Class: Standard             │
│ Blocked since: 2026-03-08   │  ← Date blocker was identified
│ Blocker: Technical/Platform │  ← Category
│ Detail: Capacitor iOS audio │
│   playback in background    │
│ Escalation: Day 3 (Mar 11) │  ← Next escalation date
└─────────────────────────────┘

┌─────────────────────────────┐
│ 🟡 WAITING                  │  ← Yellow flag
│ F-012: iOS v1.1 submission  │
│ Class: Fixed Date           │
│ Waiting since: 2026-03-07   │
│ Waiting for: App Store      │
│   review (est. 24-48 hrs)   │
│ Expected resolution: Mar 09 │
└─────────────────────────────┘
```

### Board-Level Summary

Maintain a blocked items count at the top of the board:

```
Blocked: 1 (F-011, 2 days)  |  Waiting: 1 (F-012, App Store review)
```

---

## Escalation Timeline

Blocked items follow a strict escalation clock. The clock starts when the blocker is identified, not when the item entered In Progress.

| Elapsed Time | Action | Details |
|-------------|--------|---------|
| **Immediately** | Flag the card | Mark as Blocked. Record blocker category, description, and date. |
| **Day 1** | Investigate | Spend up to 1 hour attempting to resolve. Document what was tried. If unresolvable, identify who/what can unblock it. |
| **Day 3** | Escalate | For a solo founder, "escalate" means: make a hard decision. Options: (1) Work around the blocker (change approach). (2) Descope the item to avoid the blocker. (3) Park the item — move back to Ready with a note. (4) Accept the delay and document the expected resolution date. |
| **Day 5** | Emergency resolution | The item has been blocked for a full business week. One of these must happen: (a) The blocker is resolved. (b) The item is split — the unblocked portion continues, the blocked portion returns to Backlog. (c) The item is abandoned — moved to Backlog with a "blocked-abandoned" tag and a note explaining why. |
| **Day 10** | Board hygiene | If somehow still blocked after 10 days, the item is removed from In Progress unconditionally. It returns to Backlog. Its WIP slot is freed. A root cause entry is created. |

---

## Blocker Resolution Tracking

Every blocker that occurs is tracked for pattern analysis. Record in this table:

### Blocker Log

| Date Blocked | Item ID | Category | Description | Days Blocked | Resolution | Root Cause |
|-------------|---------|----------|-------------|-------------|------------|------------|
| 2026-02-15 | D-003 | Technical/Database | SQLite ALTER CHECK constraint impossible | 2 | Recreated table with migration script | SQLite limitation — not a bug, document for future |
| 2026-02-20 | F-005 | Internal/Design | FSRS parameter tuning — which values? | 3 | Chose conservative defaults, will tune with data | Insufficient upfront research |
| 2026-03-02 | X-001 | External/Platform | Capacitor 302 redirect opens Safari | 1 | Replaced `redirect()` with `render_template()` | Platform behavior undocumented |

---

## Root Cause Analysis

Blockers are symptoms. Root causes are the disease. At each monthly service delivery review, analyze the blocker log:

### RCA Categories

| Root Cause | Pattern | Preventive Action |
|-----------|---------|-------------------|
| **Insufficient research** | Item started before the approach was understood | Add "spike" (research task) to Ready before the item itself. 30-minute investigation before committing. |
| **Missing test infrastructure** | Can't verify work because test fixtures don't exist | Treat test infrastructure as a prerequisite. Add to Definition of Ready. |
| **Platform surprise** | Cross-platform behavior differs from documentation | Maintain a "platform gotchas" document (see debugging lessons in MEMORY.md). Test on all platforms before moving to Review. |
| **External dependency** | Third-party service behavior blocks progress | Identify external dependencies during planning. Build fallback paths. Never block an item on a single external dependency without a workaround. |
| **Scope ambiguity** | Requirements were unclear when work started | Require acceptance criteria on every card before it enters In Progress. |

### Monthly RCA Summary Template

```
Month: YYYY-MM
Total items blocked this month: N
Total blocked days: N
Average days blocked per item: N
Most common blocker category: [Category]
Most common root cause: [Root Cause]
Preventive action taken: [Action]
```

---

## Definition of Ready (Blocker Prevention)

An item should not move from Ready to In Progress unless:

1. **Acceptance criteria are written** on the card
2. **Dependencies are identified** — no known blockers exist
3. **The approach is understood** — a 30-minute investigation has been done if the implementation is unclear
4. **Test strategy is identified** — how will this be verified?
5. **Platform considerations noted** — does this affect web, iOS, and macOS differently?

If an item in Ready has a known blocker, it stays in Ready (or returns to Backlog) until the blocker is resolved. Moving a known-blocked item into In Progress wastes a WIP slot.

---

## Relationship to Other Artifacts

- **WIP Limits** (`wip-limits.md`): Blocked items consume WIP slots. If an item is blocked for >5 days, it should be removed from In Progress to free the slot.
- **SLA Policy** (`sla-policy.md`): Blocked time counts against SLA targets. Frequent blocking degrades SLA achievement.
- **Service Classes** (`service-classes.md`): Expedite items follow the same blocker escalation but on a compressed timeline (hours, not days).
- **Flow Metrics** (`flow-metrics.md`): Blocked items inflate cycle time and reduce flow efficiency. Track blocked time as a distinct metric.
- **Replenishment Policy** (`replenishment-policy.md`): Items returned to Backlog due to blocking are eligible for re-prioritization at the next replenishment cadence.
