# Aelu Sprint Planning Guide

**Last Updated:** 2026-03-10

Sprint Planning is the ceremony where the sprint backlog is built. For a 2-week sprint, time-box to 2 hours maximum. If planning takes longer, the backlog items are not ready.

---

## Pre-Planning Checklist (15 minutes before)

Before the planning session, verify:

- [ ] `product-backlog.md` is up to date with current priorities
- [ ] Top 15 items in the backlog have been refined (acceptance criteria, estimates, dependencies)
- [ ] Last sprint's retrospective action items are visible
- [ ] Carryover items from the last sprint are identified
- [ ] `velocity-tracker.md` has last sprint's actuals recorded
- [ ] `drill_errors.log` and `session_trace.jsonl` have been checked for new failures that might generate urgent work

---

## Part 1: Sprint Goal Formulation (15 minutes)

The sprint goal is a single sentence describing the value delivered by the end of the sprint. It is not a list of items -- it is the outcome those items produce.

### Sprint Goal Criteria

- **Value-focused:** Describes what will be true for users, not what code will be written
- **Measurable:** You can verify at sprint review whether it was achieved
- **Coherent:** The items in the sprint should collectively serve this goal
- **Concise:** One sentence, no semicolons, no "and also"

### Good Sprint Goals (Aelu examples)

- "Five non-Jason users can complete onboarding and their first session without confusion."
- "The admin dashboard shows trial-to-paid conversion rates by acquisition channel."
- "Learners receive difficulty-calibrated reading passages based on their lookup rate."
- "The iOS app passes Apple review and is downloadable from the App Store."

### Bad Sprint Goals

- "Work on onboarding, fix bugs, and maybe start the email drip." (List, not goal)
- "Improve the app." (Not measurable)
- "Complete PB-001, PB-002, PB-005." (Ticket numbers, not value)

---

## Part 2: Capacity Calculation (10 minutes)

### Formula

```
Sprint Capacity (points) = Available Days x Focus Factor x Points-per-Day

Available Days = 10 weekdays
               - PTO days this sprint
               - Holidays
               - Ops/admin days (default: 2)
               - Tech debt allocation (default: 1 day, 20% rule)

Focus Factor = 0.7 (solo developer baseline)

Points-per-Day = Rolling 3-sprint velocity average / Available days from those sprints
```

### Capacity Worksheet

| Line | Value | Notes |
|---|---|---|
| Total weekdays | 10 | |
| Minus PTO | - ___ | |
| Minus holidays | - ___ | |
| Minus ops/admin | - 2 | Support, monitoring, deploy ops |
| Minus tech debt | - 1 | 20% rule -- non-negotiable |
| = Available days | ___ | |
| x Focus factor | x 0.7 | |
| = Effective days | ___ | |
| x Points-per-day | x ___ | Use rolling average; default 2.5 until Sprint 3 |
| = Sprint capacity | ___ | This is your maximum commitment |

### The 20% Tech Debt Rule

Every sprint allocates 20% of capacity (approximately 1 day per 2-week sprint) to tech debt. This is not optional. Tech debt items are:

- Dependency updates (`pip-audit` findings from the security workflow)
- Dead code removal (vulture audits)
- Test coverage improvements for under-tested modules (`scheduler.py`, `personalization.py`, `churn_detection.py`)
- SQLite schema cleanup (constraint migrations, index optimization)
- `ruff` rule expansion (enabling stricter lint rules incrementally)
- Build/deploy pipeline improvements

Tech debt items come from the backlog (PB-023 through PB-027 are examples) and count toward velocity when completed.

---

## Part 3: Story Selection (30 minutes)

### Selection Criteria (in priority order)

1. **Carryover items first.** Anything that was in-progress last sprint and didn't finish gets top priority. Carryover is debt -- pay it immediately.

2. **Sprint goal alignment.** Select items that directly serve the sprint goal. If an item doesn't contribute to the goal, it doesn't belong in this sprint unless it's a carryover or a critical bug.

3. **Business value.** Prefer High over Medium over Low. The backlog is already sorted by value -- respect that ordering.

4. **Dependencies.** If item B depends on item A, either pull both or pull neither. Don't pull B alone and hope A gets done "somehow."

5. **Size diversity.** Include at least one item under 3 points. Starting the sprint with a quick win builds momentum. Avoid filling the sprint with only 8-point items -- if one slips, the whole sprint fails.

### Story Selection Checklist

For each item considered for the sprint, verify:

- [ ] Meets Definition of Ready (all 7 criteria from `definition-of-ready.md`)
- [ ] Acceptance criteria are specific enough to write tests from
- [ ] No unresolved dependencies (schema migration prepared? new package compatible with Python 3.9.6?)
- [ ] The item can be completed AND deployed within the sprint (not just coded)
- [ ] The item's test strategy is identified (unit, integration, manual)

### What "Sprint-Ready" Means

An item is sprint-ready when you can start coding immediately after planning ends. Specifically:

- The user story answers who, what, and why
- Acceptance criteria can be directly translated into pytest assertions
- You know which files you'll modify (e.g., "add route to `web/routes.py`, update `scheduler.py`, add migration to `db/core.py`")
- You know the test approach (e.g., "3 unit tests for the algorithm, 1 integration test with `create_app` + `test_client`")
- No open questions remain

If you're thinking "I need to investigate before I can start," the item is not ready. Create a spike instead (timeboxed research task, 1-2 points).

---

## Part 4: Task Breakdown (30 minutes)

Break each selected item into tasks. Tasks are not story points -- they are concrete steps.

### Task Breakdown Template

For each backlog item:

```
## PB-XXX: [Title]
Sprint Points: X

Tasks:
1. [ ] [Specific implementation step]
2. [ ] [Write tests for...]
3. [ ] [Update schema/migration if needed]
4. [ ] [Manual testing on web + iOS + macOS]
5. [ ] [Deploy and monitor crash_log for 24h]
```

### Example: PB-012 Passage Difficulty Calibration (5 points)

```
Tasks:
1. [ ] Add `lookup_rate` calculation to reading route (count lookups / total words in passage)
2. [ ] Add difficulty_adjustment logic to passage selection query (filter by HSK range based on user level)
3. [ ] Implement threshold logic: >30% lookup rate -> easier; <5% -> harder
4. [ ] Write 4 unit tests for lookup_rate calculation edge cases (0 words, 0 lookups, all lookups, None values)
5. [ ] Write 2 integration tests with test_client: verify passage filtering respects user HSK level
6. [ ] Write 1 integration test: verify difficulty adjustment after high lookup rate
7. [ ] Test on web reader (#reading view) with HSK 2 and HSK 4 test accounts
8. [ ] Test on iOS simulator (Capacitor reader view)
9. [ ] Deploy, monitor vocab_encounter table for 24h
```

---

## Handling Carryover

When items carry over from the previous sprint:

1. **Ask why it carried over.** Was it under-estimated? Was scope added mid-sprint? Was it blocked?
2. **Re-estimate if needed.** If the remaining work is 2 points of an original 5-point item, commit only 2 points this sprint -- not 5.
3. **Track carryover separately.** In the velocity chart, note which completed items are carryovers. If carryover exceeds 30% of committed points for 2 consecutive sprints, estimation calibration is needed.
4. **Never silently carry over.** Every carryover item must be explicitly re-committed in planning, not assumed.

---

## Sprint Planning Output

By the end of planning, you should have:

1. **Sprint goal:** One sentence, value-focused
2. **Sprint backlog:** 3-7 items totaling no more than the calculated capacity
3. **Task breakdowns:** Each item decomposed into concrete steps
4. **Tech debt item(s):** At least one tech debt task using the 20% allocation
5. **Capacity notes:** Any known capacity reductions (PTO, appointments, etc.)

Record everything in a new sprint entry using `sprint-template.md`.

---

## Sprint Planning Anti-Patterns

**Over-commitment:** Committing to 20 points when your average velocity is 12 because "this sprint feels different." It doesn't. Trust the data.

**Under-commitment:** Committing to 6 points because you're nervous about carryover. This wastes capacity. Commit to 90% of your rolling average.

**No sprint goal:** Pulling a grab-bag of unrelated items with no coherent theme. If you can't articulate the sprint goal in one sentence, the selection is unfocused.

**Skipping tech debt:** "There's too much feature work this sprint." If you skip the 20% allocation more than once, you are borrowing from future sprints. The interest compounds.

**Planning without data:** Not checking `velocity-tracker.md`, not reviewing last sprint's completion rate, not reading `drill_errors.log`. Planning is data-driven, not vibes-driven.

**Infinite planning:** Spending 3 hours on planning for a 2-week sprint. If items aren't ready, stop planning and go refine them. Planning is selection and breakdown, not discovery.

**Hero stories:** Pulling a 13-point item and nothing else. If it slips by one day, the sprint is a zero. Diversify story sizes to derisk.
