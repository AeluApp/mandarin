# Replenishment Policy

> Last updated: 2026-03-10

## Purpose

Replenishment is the process of pulling new work into the system. It answers: "When do we pull work from Backlog to Ready?" and "Which items get pulled first?" Without a replenishment policy, the board either starves (nothing in Ready when you finish something) or overflows (Ready becomes a second Backlog).

---

## Commitment Point

The **commitment point** is the boundary between options and commitments.

```
  Backlog          │         Ready → In Progress → Review → Done
  (options)        │         (commitments)
                   │
           Commitment Point
```

- **Before the commitment point (Backlog):** Items are options. They cost nothing to hold. No SLA applies. They can be reordered, modified, or removed without consequence.
- **After the commitment point (Ready):** Items are commitments. The SLA clock starts. The team (solo founder) has committed to delivering this item in the near term. Removing a committed item requires a note.

**Implication:** Be deliberate about what crosses the commitment point. Moving something to Ready is a promise to yourself.

---

## Options vs. Commitments

| Aspect | Options (Backlog) | Commitments (Ready+) |
|--------|-------------------|---------------------|
| SLA applies | No | Yes |
| Can be reordered freely | Yes | Yes, but with justification |
| Can be removed silently | Yes | No — requires a note |
| Counts toward throughput | No | Yes (when completed) |
| Scope can change | Yes, freely | Yes, but scope changes reset SLA |
| WIP impact | None | Counts against Ready limit (10) |

---

## Replenishment Triggers

New items are pulled from Backlog to Ready when either of these conditions is met:

### Trigger 1: WIP Below Limit (Pull-Based)

When Ready column drops below a threshold, pull new items to replenish.

| Condition | Action |
|-----------|--------|
| Ready has fewer than 5 items | Pull items from Backlog to bring Ready to 7-8 items |
| Ready has 0 items and In Progress has open slots | Pull directly into Ready and then into In Progress |

**Rationale:** Ready should have 5-10 items (about 1-2 weeks of work) to provide selection flexibility. Below 5 means the pipeline is thin. Above 10 triggers the WIP limit.

### Trigger 2: Cadence-Based (Time-Based)

Regardless of Ready count, review and replenish at regular intervals.

| Cadence | Action |
|---------|--------|
| **Weekly (Monday)** | Review Backlog. Promote 2-3 highest-priority items to Ready if space permits. Remove stale items from Backlog (>60 days with no interest). |
| **After each item completes** | When an item moves to Done and a slot opens in Ready, immediately check if a high-priority Backlog item should be promoted. |

---

## Prioritization: Weighted Shortest Job First (WSJF)

When multiple Backlog items compete for promotion to Ready, use WSJF to determine order.

### WSJF Formula

```
WSJF = Cost of Delay / Job Duration

Cost of Delay = User/Business Value + Time Criticality + Risk Reduction
```

Each factor is scored 1-5 (Fibonacci: 1, 2, 3, 5, 8 for finer granularity if needed):

| Factor | 1 (Low) | 3 (Medium) | 5 (High) |
|--------|---------|------------|----------|
| **User/Business Value** | Nice-to-have, few users affected | Noticeable improvement, moderate user impact | Core feature, high user impact, revenue impact |
| **Time Criticality** | No deadline, value doesn't decay | Value decays slowly, competitive pressure | Urgent deadline, value drops sharply with delay |
| **Risk Reduction** | No risk addressed | Moderate technical or security risk | Critical security, data integrity, or compliance risk |
| **Job Duration** | 5+ days | 2-4 days | 0.5-1 day |

### WSJF Scoring Example (Aelu Backlog Items)

| Item | Value | Time Crit. | Risk Red. | CoD | Duration | WSJF | Priority |
|------|-------|-----------|-----------|-----|----------|------|----------|
| F-008: Listening sub-categories | 3 | 2 | 1 | 6 | 3 (3d) | 2.0 | 3rd |
| F-009: Distractor length normalization | 2 | 1 | 2 | 5 | 2 (2d) | 2.5 | 2nd |
| D-005: SQLite load test | 1 | 2 | 4 | 7 | 2 (2d) | 3.5 | 1st |
| X-002: Session length A/B test | 2 | 1 | 1 | 4 | 3 (3d) | 1.3 | 4th |

**Result:** D-005 (SQLite load test) has the highest WSJF because it addresses a significant risk and is relatively quick. It should be promoted to Ready first, despite being "just" tech debt.

### Override Conditions

WSJF is a guide, not a law. Override the ranking when:

1. **Expedite items** always go first regardless of WSJF score.
2. **Fixed Date items** must be promoted by their planning date regardless of score.
3. **Emotional load matters.** If you've done 3 tech debt items in a row and need a creative break, pulling a feature is legitimate. Sustainable pace > optimal sequencing.
4. **Dependencies.** If Item A unblocks Items B and C, promote A even if its individual WSJF is lower.

---

## Input Queue Management

The Backlog is the input queue. Without hygiene, it becomes a graveyard of good intentions.

### Backlog Hygiene Rules

| Rule | Action | Frequency |
|------|--------|-----------|
| **Age limit** | Items in Backlog for >90 days without being promoted get reviewed. If still relevant, add a note why. If not, remove. | Monthly |
| **Size limit** | If Backlog exceeds 30 items, prune the bottom 10. Be honest about what you'll never do. | Monthly |
| **Duplicate check** | Before adding a new item, search for existing items that cover the same ground. | At creation time |
| **Decomposition check** | Items estimated at >5 days should be split before entering Ready. | At promotion time |

### Sources of New Items

| Source | Entry Process | Typical Class |
|--------|--------------|---------------|
| Personal idea/observation | Add directly to Backlog | Standard or Intangible |
| User feedback (when launched) | Triage: bug → Backlog with Bug type, feature request → Backlog with Feature type | Standard |
| Monitoring/alerting | If Expedite, bypass Backlog entirely. Otherwise, add to Backlog. | Expedite or Standard |
| Security scan (`pip-audit`, `bandit`) | Critical findings → Expedite. Others → Backlog as Tech Debt. | Expedite or Intangible |
| Spiral risk review | Risk mitigations → Backlog with appropriate type | Standard or Intangible |
| Session trace / drill errors | Bugs from `drill_errors.log` or `session_trace.jsonl` → Backlog as Bug | Standard |

---

## Stakeholder Input Process

For a solo founder, "stakeholder input" means structured self-review from multiple perspectives:

### Hats Exercise (Weekly, during replenishment)

When prioritizing Backlog items, briefly consider each stakeholder perspective:

1. **Learner hat:** "What would make the learning experience measurably better this week?"
2. **Developer hat:** "What tech debt is closest to causing a real problem?"
3. **Business hat:** "What moves the needle on revenue, retention, or growth?"
4. **Security hat:** "What is the most dangerous unmitigated risk right now?"

If all four hats agree on an item, it's the obvious next pull. If they conflict, WSJF breaks the tie.

### Future: External Stakeholder Input

When Aelu has beta users or institutional partners:
- Feature requests go to Backlog with "User Request" source tag
- Classroom/LTI integration requests from partners get Fixed Date class if contractually committed
- Aggregate user feedback monthly to identify patterns (not individual requests)

---

## Replenishment Checklist

Use this checklist every Monday and whenever an item moves to Done:

```
□ Ready column item count: ___  (target: 5-10)
□ If < 5: review Backlog for items to promote
□ WSJF scoring for promotion candidates (if multiple)
□ Promoted items have acceptance criteria written
□ Promoted items have no known blockers (see blocked-items-policy.md)
□ Backlog size: ___  (if > 30: prune bottom 10)
□ Any items > 90 days in Backlog? Review or remove.
□ Class of service assigned to all promoted items
□ Any Fixed Date items approaching their planning date? Promote now.
```

---

## Relationship to Other Artifacts

- **Board** (`board.md`): Shows current state of Ready and Backlog columns.
- **WIP Limits** (`wip-limits.md`): Ready column WIP limit (10) governs maximum replenishment.
- **Service Classes** (`service-classes.md`): Class assignment happens at replenishment time.
- **SLA Policy** (`sla-policy.md`): SLA clock starts at the commitment point (Backlog → Ready).
- **Blocked Items Policy** (`blocked-items-policy.md`): Items returned to Backlog due to blocking re-enter the replenishment queue.
- **Risk Register** (`../spiral/risk-register.md`): Risk mitigations generate Backlog items.
