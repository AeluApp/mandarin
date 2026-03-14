# Aelu Velocity Measurement Framework

**Last Updated:** 2026-03-10

---

## What Velocity Measures

Velocity is the number of story points completed per sprint, where "completed" means meeting the full Definition of Done (all tests pass, deployed to production, no new crash_log entries for 24 hours, etc.). Velocity is a forecasting tool, not a performance metric.

---

## Story Point Definitions for Aelu

Story points measure relative complexity, not time. The reference stories below anchor each point value to real Aelu work.

| Points | Complexity | Reference Story | Typical Scope |
|---|---|---|---|
| 1 | Trivial | Update `ui_labels.py` copy for a drill prompt | 1 file, no schema change, no new tests needed |
| 2 | Small | Add session progress bar (PB-005) | 2-3 files, 1-3 new tests, single module |
| 3 | Moderate | Onboarding funnel tracking via `lifecycle_event` (PB-002) | 3-5 files, new route + admin view, 5-8 tests |
| 5 | Significant | Passage difficulty calibration (PB-012) | Schema touch (`vocab_encounter`), new algorithm in `scheduler.py`, 10+ tests |
| 8 | Large | Email onboarding drip sequence (PB-004) | New module (`email.py` expansion), external integration (SMTP), background job, 15+ tests |
| 13 | Epic-sized | iOS App Store submission (PB-013) | Multi-day, cross-platform, external dependency (Apple review), should be split |

**Rule:** If an item feels bigger than 13, it must be split before it enters a sprint. No item over 13 points is ever sprint-ready.

**Calibration:** After every 3 sprints, revisit these reference stories. If a "3" consistently takes as long as what used to be a "5," the scale is drifting -- recalibrate.

---

## Historical Velocity Chart Template

Update this table after each sprint closes. Only count points for items that meet the full Definition of Done.

| Sprint | Dates | Committed | Completed | Carry-over | Unplanned Work (hrs) | Completion % |
|---|---|---|---|---|---|---|
| 1 | 2026-03-10 to 2026-03-21 | 13 | -- | -- | -- | -- |
| 2 | 2026-03-24 to 2026-04-04 | -- | -- | -- | -- | -- |
| 3 | 2026-04-07 to 2026-04-18 | -- | -- | -- | -- | -- |
| 4 | 2026-04-21 to 2026-05-02 | -- | -- | -- | -- | -- |
| 5 | 2026-05-05 to 2026-05-16 | -- | -- | -- | -- | -- |
| 6 | 2026-05-18 to 2026-05-29 | -- | -- | -- | -- | -- |

**Velocity trend visualization** (ASCII chart, update after Sprint 3):

```
Points
  |
20|
18|
16|
14|
12|
10|
 8|
 6|
 4|
 2|
  +---+---+---+---+---+---+
    S1  S2  S3  S4  S5  S6
```

Plot completed points per sprint. Draw a horizontal line at the rolling 3-sprint average.

---

## Capacity Planning Formula

```
Sprint Capacity = Available Days x Focus Factor x Points-per-Day

Where:
  Available Days    = 10 weekdays - PTO - holidays - ops/admin days
  Focus Factor      = 0.7 (accounts for context switching, support, meetings)
  Points-per-Day    = Average velocity / Available days (from last 3 sprints)
```

**Aelu baseline (solo developer):**

| Parameter | Value | Notes |
|---|---|---|
| Weekdays per sprint | 10 | 2-week sprint |
| Ops/admin days | 2 | Support emails, deploy monitoring, admin dashboard review |
| Tech debt allocation | 1 day | 20% rule (see sprint-planning-guide.md) |
| Net available days | 7 | 10 - 2 - 1 |
| Focus factor | 0.7 | Accounts for context switching, interruptions |
| Effective capacity | 4.9 days | 7 x 0.7 |
| Estimated points-per-day | ~2.5 | Calibrate after Sprint 3 |
| Expected velocity | 10-13 points | 4.9 x 2.5 = ~12.3 |

**Capacity adjustments:**
- Sprint with 1 day PTO: reduce by ~2.5 points
- Sprint with conference/travel: reduce by 50%
- Sprint following a production incident: reduce by 20% (incident follow-up consumes capacity)

---

## Sprint Commitment Guidelines

### Before Sprint 3 (Insufficient Data)
- Commit conservatively: 10-12 points
- Expect high variance -- first sprints calibrate estimation skill
- Do not draw conclusions from a single sprint's velocity

### After Sprint 3 (Emerging Pattern)
- Commit to 90% of the rolling 3-sprint average
- The 10% buffer absorbs unplanned work and estimation error
- If the previous sprint had significant carryover, commit to 80% of average

### After Sprint 6 (Stable Velocity)
- Commit to 95% of the rolling 5-sprint average
- Velocity should be stabilized (see criteria below)
- Adjust only for known capacity changes (PTO, holidays)

### Commitment Rules
1. Never commit to more than 110% of the rolling average. Optimism is the enemy of reliable delivery.
2. Always include at least one item under 3 points. Small wins early in the sprint build momentum.
3. If the last sprint had >20% unplanned work, reduce this sprint's commitment by the same percentage.
4. Never pad estimates to hit a velocity target. Velocity is observed, not engineered.

---

## Velocity Stabilization Criteria

Velocity is "stable" when ALL of the following are true:

1. **Variance check:** The standard deviation of the last 6 sprints is less than 20% of the mean.
   ```
   Example: If mean velocity = 12, std dev must be < 2.4
   Sprints: [11, 13, 12, 10, 14, 12] -> mean=12, std=1.4 -> STABLE (1.4 < 2.4)
   Sprints: [8, 15, 10, 18, 7, 14]  -> mean=12, std=4.1 -> UNSTABLE (4.1 > 2.4)
   ```

2. **No outliers:** No single sprint deviates more than 40% from the rolling average.

3. **Estimation accuracy:** Committed vs. completed ratio is between 85% and 110% for 4 of the last 6 sprints.

4. **Carryover pattern:** No more than 1 item carried over per sprint in the last 3 sprints.

**If velocity is unstable after Sprint 6:**
- Review estimation calibration -- are reference stories still accurate?
- Check for recurring unplanned work -- should it be budgeted as capacity reduction?
- Check for scope creep within stories -- are acceptance criteria tight enough?
- Consider whether the tech debt allocation is sufficient -- accumulated debt creates unpredictable sprints

---

## What Counts Toward Velocity

| Scenario | Counts? | Rationale |
|---|---|---|
| Item meets full Definition of Done | Yes | This is velocity |
| Item partially done, will finish next sprint | No (0 this sprint, full points next sprint) | Partial credit masks reality |
| Unplanned production bug fix | No | Track separately as unplanned work |
| Tech debt item in sprint backlog | Yes | It was planned and committed to |
| Spike/research task with clear deliverable | Yes (if estimated and in backlog) | Spikes produce knowledge, which is value |
| Item completed but not deployed | No | DoD requires deployment |
| Item deployed but crash_log shows regression | No | DoD requires 24hr clean monitoring |

---

## Velocity vs. Throughput

Velocity (story points per sprint) tells you about estimation reliability. Throughput (items completed per sprint) tells you about delivery cadence. Track both.

| Sprint | Velocity (points) | Throughput (items) | Avg Points/Item |
|---|---|---|---|
| 1 | -- | -- | -- |
| 2 | -- | -- | -- |
| 3 | -- | -- | -- |

If throughput is stable but velocity fluctuates, the problem is estimation inconsistency, not delivery inconsistency. If both fluctuate, the problem is capacity or scope.

---

## Backlog Burn-down Projection

Update after each sprint using the rolling 3-sprint velocity average.

```
Remaining Points = Total Backlog Points - Cumulative Completed Points
Sprints Remaining = Remaining Points / Rolling 3-Sprint Average Velocity
Target Date = Current Date + (Sprints Remaining x 14 days)
```

**Current backlog:** 168 points across 33 items (PB-001 through PB-033).

This projection assumes a static backlog. Real backlogs grow. If the backlog grows faster than velocity consumes it, the project timeline is expanding, not contracting. Monitor the ratio: `new points added per sprint / velocity per sprint`. If this ratio exceeds 0.5 for 3 consecutive sprints, backlog grooming is overdue.
