# Aelu Velocity Tracker

**Last Updated:** 2026-03-10

---

## Velocity Log

| Sprint # | Dates | Sprint Goal | Points Committed | Points Completed | Notes |
|---|---|---|---|---|---|
| 1 | 2026-03-10 to 2026-03-21 | Validate 5 non-Jason users through onboarding and first session | 13 | — | In progress |
| 2 | 2026-03-24 to 2026-04-04 | — | — | — | Not started |
| 3 | 2026-04-07 to 2026-04-18 | — | — | — | Not started |
| 4 | 2026-04-21 to 2026-05-02 | — | — | — | Not started |
| 5 | 2026-05-05 to 2026-05-16 | — | — | — | Not started |
| 6 | 2026-05-18 to 2026-05-29 | — | — | — | Not started |

---

## Rolling Averages

| Metric | Value |
|---|---|
| Average velocity (last 3 sprints) | Not yet available — need 3 completed sprints |
| Average velocity (last 5 sprints) | Not yet available — need 5 completed sprints |
| Velocity trend | Not yet available |

---

## Backlog Projection

**Total backlog points remaining:** 168 (as of 2026-03-10, Product Backlog PB-001 through PB-033)

**Projection formula:**
```
Remaining sprints = Total remaining points / Average velocity (last 3 sprints)
```

**Current projection:** Cannot calculate until Sprint 1 is complete. After Sprint 1, an initial (unreliable) estimate will be available. After Sprint 3, the rolling average becomes meaningful.

**Example projections at different velocities:**

| If velocity is... | Sprints to clear backlog | Calendar time |
|---|---|---|
| 8 pts/sprint | 21 sprints | ~42 weeks |
| 10 pts/sprint | 17 sprints | ~34 weeks |
| 13 pts/sprint | 13 sprints | ~26 weeks |
| 15 pts/sprint | 11 sprints | ~22 weeks |

These projections assume the backlog is static (no new items added). In practice, the backlog grows as new work is discovered. A sustainable product has a backlog that grows slower than it is consumed.

---

## Capacity Notes

**Solo developer context:** Jason is the only developer, product owner, designer, QA, devops, and support. Realistic capacity per 2-week sprint:

- 10 weekdays per sprint
- Minus ~2 days for: ops, support emails, admin, meetings, errands
- Minus ~1 day for: tech debt (20% budget per tech-debt-budget.md)
- **Net capacity: ~7 productive coding days per sprint**

At ~2 points per productive day (rough calibration), expected velocity is **10-14 points per sprint**. This will be refined after the first 3 sprints produce real data.

---

## Guidance: How to Use Velocity

**Velocity is for forecasting, not performance measurement.**

- Do NOT try to increase velocity sprint over sprint. Velocity is a measurement, not a target. Goodhart's Law applies: when a measure becomes a target, it ceases to be a good measure.
- Do NOT compare velocity across teams or across projects. There is no team here — this is purely for self-forecasting.
- DO use velocity to answer: "Can I realistically commit to these items this sprint?"
- DO use velocity to answer: "When will feature X likely be ready?"
- DO notice trends: if velocity is declining, ask why (burnout? scope creep? too much support?). If velocity is stable, trust it for planning.

**Velocity stabilization:** Expect high variance in the first 3 sprints as estimation calibration improves. By Sprint 5, velocity should stabilize within +/- 20% of the average.

**What counts toward velocity:**
- Only items that meet the full Definition of Done count.
- Partially completed items count as 0 points in the sprint they started and full points in the sprint they finish.
- Bug fixes that were not in the sprint backlog do not count (they are unplanned work and should be tracked separately).

**Unplanned work tracking:**
Add a row to each sprint's notes tracking unplanned work (production bugs, urgent support, etc.). If unplanned work consistently exceeds 20% of capacity, the sprint commitment should be reduced accordingly.
