# Flow Metrics

> Last updated: 2026-03-10

## Metric Definitions

### Lead Time

**Definition:** Calendar days from when an item enters Backlog to when it is deployed to production (moved to Done).

**Measurement:** `Date Done - Date Entered`

**Target by class of service:**
| Class | Target Lead Time |
|-------|-----------------|
| Expedite | <1 day |
| Fixed Date | Completed 3 days before deadline |
| Standard | <14 days |
| Intangible | <30 days |

**Why it matters:** Lead time is what the "customer" (you, users, the business) experiences. Long lead times mean ideas sit idle. Short lead times mean the system is responsive.

### Cycle Time

**Definition:** Calendar days from when work actively starts (moved to In Progress) to when it is deployed to production (moved to Done).

**Measurement:** `Date Done - Date Started`

**Why it matters:** Cycle time is what the developer experiences. It measures how long something takes once you commit to it. Lead time minus cycle time equals queue time — how long items wait before anyone touches them.

### Throughput

**Definition:** Number of items completed per week (moved to Done).

**Measurement:** Count of items with `Date Done` in the target week.

**Current baseline:** ~3-4 items/week during active development (Feb-Mar 2026). Will likely drop to 1-2/week as the system stabilizes and work shifts from building to marketing/growth.

### Flow Efficiency

**Definition:** Percentage of lead time spent in active work versus waiting.

**Formula:** `(Active Work Time / Lead Time) × 100`

**Active work time:** Days an item was in "In Progress" or "Review" columns. **Wait time:** Days in "Backlog" or "Ready" columns.

**Typical benchmarks:**
- 15% — common in large organizations (85% of time is waiting)
- 40% — good for a small team
- 60%+ — realistic target for a solo founder with pull-based flow

---

## Tracking Table

| ID | Title | Type | Class | Entered | Started | Done | Lead Time | Cycle Time | Active Days | Flow Eff. |
|----|-------|------|-------|---------|---------|------|-----------|------------|-------------|-----------|
| B-001 | Session fixation fix (C1) | Bug | Expedite | 2026-02-25 | 2026-02-25 | 2026-02-25 | <1 | <1 | <1 | ~100% |
| B-002 | Lockout bypass fix (C2) | Bug | Expedite | 2026-02-25 | 2026-02-25 | 2026-02-25 | <1 | <1 | <1 | ~100% |
| B-003 | Refresh token bypass (C3) | Bug | Expedite | 2026-02-25 | 2026-02-25 | 2026-02-25 | <1 | <1 | <1 | ~100% |
| D-001 | CI coverage + ruff (H13-H14) | Tech Debt | Standard | 2026-02-25 | 2026-02-26 | 2026-02-27 | 2 | 1 | 1 | 50% |
| D-002 | Schema alignment (H9) | Tech Debt | Standard | 2026-02-25 | 2026-02-26 | 2026-02-26 | 1 | <1 | <1 | ~100% |
| F-004 | MFA (TOTP) | Feature | Standard | 2026-02-19 | 2026-02-20 | 2026-02-25 | 6 | 5 | 4 | 67% |
| F-003 | Stripe payment integration | Feature | Standard | 2026-02-15 | 2026-02-16 | 2026-02-20 | 5 | 4 | 3 | 60% |
| F-002 | Mobile Capacitor phases A-F | Feature | Standard | 2026-02-10 | 2026-02-14 | 2026-02-21 | 11 | 7 | 6 | 55% |
| F-001 | Web UI (Flask+WS) | Feature | Standard | 2026-02-08 | 2026-02-09 | 2026-02-11 | 3 | 2 | 2 | 67% |
| D-000 | 6-stage mastery lifecycle | Tech Debt | Standard | 2026-02-12 | 2026-02-13 | 2026-02-14 | 2 | 1 | 1 | 50% |

---

## Summary Statistics (as of 2026-03-10)

**Lead Time:**
- Mean: 3.1 days
- Median: 2 days
- P85: 6 days (85% of items complete within 6 days)
- Range: <1 day to 11 days

**Cycle Time:**
- Mean: 2.1 days
- Median: 1 day
- P85: 5 days

**Throughput:**
- Week of 2026-02-24: 5 items (security sprint)
- Week of 2026-03-03: 2 items (stabilization)
- 4-week rolling average: ~3 items/week

**Flow Efficiency:**
- Mean: 65%
- Expedite items: ~100% (no queue time)
- Standard features: 55-67%
- Queue time is mostly in Backlog/Ready (1-4 days)

---

## Formulas

```
Lead Time (days) = Date Done - Date Entered
Cycle Time (days) = Date Done - Date Started
Queue Time (days) = Lead Time - Cycle Time
Throughput (items/week) = COUNT(items where Date Done in target week)
Flow Efficiency (%) = (Cycle Time / Lead Time) × 100

# If tracking active vs blocked time within In Progress:
Flow Efficiency (%) = (Active Days / Lead Time) × 100
```

**Example calculation:**

Item F-002 (Mobile Capacitor phases A-F):
- Entered Backlog: 2026-02-10
- Started work: 2026-02-14 (4 days in queue)
- Completed: 2026-02-21
- Lead Time: 11 days
- Cycle Time: 7 days
- Active work: ~6 days (1 day blocked waiting for icon assets)
- Flow Efficiency: 6/11 = 55%

---

## When to Worry

| Signal | What It Means | Action |
|--------|--------------|--------|
| Lead time increasing month-over-month | Items spending more time in queue | Check: is Ready overfull? Is backlog grooming happening? |
| Cycle time increasing | Work is taking longer to finish | Check: are items too large? Is scope creeping within items? Split items. |
| Throughput dropping without explanation | Fewer items finishing | Check: is WIP too high? Are items blocked? Is energy/motivation declining? |
| Flow efficiency below 30% | Most time is waiting, not working | Check: are items being pulled into Ready too early? Is replenishment cadence right? |
| Expedite items >10% of throughput | Too many production emergencies | Invest in quality: testing, monitoring, defensive coding. |
