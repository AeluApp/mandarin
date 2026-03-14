# WIP Limit Policy

> Last updated: 2026-03-10

## Limits by Column

| Column | WIP Limit | Composition | Rationale |
|--------|-----------|-------------|-----------|
| Backlog | Unlimited | Any mix | Capture everything. Cost of holding an idea is near zero. Unbounded backlog is fine because replenishment cadence controls what gets promoted to Ready. |
| Ready | 10 | Any mix | Prevents over-commitment. If Ready has 10 items, no new items can be promoted from Backlog until something is pulled into In Progress. Forces prioritization decisions. 10 is ~2-3 weeks of work at current throughput. |
| In Progress | 3 | 1 feature + 1 bug + 1 tech debt/experiment | Solo founder context-switching tax is real. Three items lets you make progress on a feature while having a bug fix and a housekeeping task as cognitive breaks. More than 3 means nothing finishes. |
| Review | 2 | Any mix | Review for a solo founder means: final testing, deploy verification, documentation update. Two items in review is manageable. More means things pile up before deploy. |
| Done | Unlimited | Any mix | Archive. Items stay visible for 30 days for flow metrics, then archived. |

---

## Composition Rules for In Progress

The 3-slot In Progress limit is not "any 3 items." It is structured:

1. **Slot 1 — Feature or Experiment:** The main creative/building work. One at a time forces focus.
2. **Slot 2 — Bug:** Reactive work. Bugs from real usage get their own slot so they don't block features but also don't languish.
3. **Slot 3 — Tech Debt or Experiment:** Housekeeping. Dead code removal, dependency updates, test coverage. This slot prevents the "I'll do it later" trap.

If no bugs exist, slot 2 can hold a second feature or tech debt item. But if a bug arrives, it displaces the non-bug item (which returns to Ready).

---

## Policy for Exceeding WIP Limits

**Rule: If at WIP limit, you must move an item to Done or explicitly abandon it before starting new work.**

"Abandon" means:
- Move back to Backlog with a note explaining why
- Or remove from the board entirely with a note in the spiral log

No silent displacement. Every item that leaves In Progress without reaching Done gets a note.

---

## Emergency Override: P1 Incidents

Production incidents (Expedite class of service) bypass WIP limits. Conditions:

1. **Qualifies as Expedite:** Production outage, data loss, security breach, or crash_log spike. Not "this annoys me" — actual user-facing breakage.
2. **Logged:** Create a card with class "Expedite" and a note: "WIP override — [reason]."
3. **Temporary:** The override item must be resolved within 24 hours or escalated (for a solo founder, "escalated" means: accept the outage and timebox the fix, or revert the causing change).
4. **Post-incident:** After resolution, review whether the override was justified. If overrides happen more than once per month, something is structurally wrong — hold a risk review.

---

## Why These Numbers

| Limit | Alternative Considered | Why Rejected |
|-------|----------------------|--------------|
| In Progress: 3 | 5 (more flexibility) | At 5 items, a solo founder is guaranteed to have 2+ items stalled. Tested this informally during V2 development — 5 concurrent streams meant nothing shipped for a week. |
| In Progress: 3 | 1 (pure single-piece flow) | Too rigid. Bug fixes and tech debt are genuinely different cognitive modes. Having one bug fix as a "break" from feature work is productive, not wasteful. |
| Review: 2 | 1 | Sometimes you finish a feature and a bug fix on the same day. Both need deploy verification. 1 would create an artificial bottleneck. |
| Ready: 10 | 5 | 5 is too few — leads to frequent replenishment interruptions. 10 gives ~2-3 weeks of runway between replenishment sessions. |
| Ready: 10 | 20 | 20 means you're not actually prioritizing. If you have 20 "ready" items, you haven't made real choices about what matters next. |

---

## Monthly Review

At each operations review cadence, check:

- How many times was In Progress at limit? (Target: >80% of the time — means you're focused)
- How many times did an item get abandoned from In Progress? (Target: <1/month — means you're choosing well)
- How many emergency overrides? (Target: 0 — means production is stable)
- Is the Ready queue refilling naturally? (If it's always empty, backlog grooming is insufficient. If it's always at 10, you're planning more than you can execute.)
