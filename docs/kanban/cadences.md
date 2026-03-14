# Kanban Cadences

> Last updated: 2026-03-10
> Adapted for solo founder context

## Overview

Kanban defines 7 cadences (regular meetings/reviews). For a solo founder, "meetings" become structured self-reviews. The discipline is the same — the cadence creates rhythm, and the rhythm prevents drift.

---

## 1. Daily Standup (Self-Check)

**When:** Every workday, first 5 minutes before opening code editor.
**Duration:** 5 minutes maximum. Set a timer.

**Protocol:**

1. Open `docs/kanban/board.md`.
2. Answer three questions:
   - **What's In Progress?** Read the 3 (max) items. Are they still the right things to work on today?
   - **Any blockers?** Is anything stuck? Waiting on an external response? Unclear requirements?
   - **Pull next item?** If an In Progress slot is open, pull the top item from Ready.
3. Check `data/drill_errors.log` and `data/session_trace.jsonl` (tail recent entries). Any new failures?
4. If a failure is found, create a card (or escalate an existing one to Expedite if warranted).

**Output:** Updated board.md if anything changed. Mental clarity on the day's focus.

**Anti-pattern to avoid:** Turning the standup into a planning session. 5 minutes. Answer the questions. Start working.

---

## 2. Replenishment

**When:** Monday morning, after daily standup.
**Duration:** 15-30 minutes.

**Protocol:**

1. **Review Backlog:** Are there new items to add? Ideas from the weekend, user feedback (once users exist), monitoring alerts from the past week.
2. **Prioritize Ready:** Is the Ready queue well-ordered? Move the most important items to the top. Remove items that no longer matter.
3. **Check Ready count:** If Ready < 5 items, promote from Backlog. If Ready = 10 (at limit), do NOT add more — either wait or remove lower-priority items.
4. **Assign classes of service:** New items in Ready should have a class assigned (Standard, Intangible, etc.).
5. **Check for Fixed Date items:** Any upcoming deadlines in the next 2 weeks? If so, ensure they're in Ready or In Progress.

**Output:** Updated board.md with fresh Ready queue.

---

## 3. Delivery Planning

**When:** Friday afternoon.
**Duration:** 10-15 minutes.

**Protocol:**

1. **What shipped this week?** List items moved to Done. Update the flow metrics tracking table.
2. **What's ready to ship?** Are there items in Review that can be deployed? If so, deploy them now (Friday deploys are fine for a single-user app; reconsider after PMF).
3. **What will carry over?** Any In Progress items that won't finish this week? Note expected completion.
4. **Update flow-data.csv** with this week's column counts for CFD generation.
5. **Compute weekly throughput.** Add to the running log.

**Output:** Updated flow-metrics.md and flow-data.csv. Deployed items if any are in Review.

---

## 4. Service Delivery Review

**When:** Bi-weekly (every other Friday, after delivery planning).
**Duration:** 20-30 minutes.

**Protocol:**

1. **SLE achievement:** For each class of service, what percentage of items met their SLE this period?
   - Expedite: Were all incidents resolved within 4 hours / 24 hours?
   - Fixed Date: Were deadlines met with 3-day buffer?
   - Standard: What's the P85 lead time? Is it under 14 days?
   - Intangible: What's the P85 lead time? Is it under 30 days?
2. **Throughput trend:** Is throughput stable, increasing, or decreasing? Why?
3. **Cycle time trend:** Are items taking longer to complete? If so, investigate.
4. **Aging WIP check:** Any items In Progress longer than 2x average cycle time?
5. **If any SLE < 70%:** Trigger the escalation policy (see sle.md).

**Output:** Updated SLE tracking table in sle.md. Action items if SLEs are breached.

---

## 5. Operations Review

**When:** Monthly (first Monday of the month).
**Duration:** 30-45 minutes.

**Protocol:**

1. **Capacity vs. demand:**
   - How many items entered the board this month? (Demand)
   - How many items were completed? (Capacity)
   - If demand > capacity: are you saying "no" enough? Is the backlog growing unboundedly?
2. **Infrastructure health:**
   - Fly.io: check machine status, recent deploys, any incidents.
   - Litestream: verify backups are running (`fly ssh console` → check litestream logs).
   - SQLite: check database size, WAL file size.
   - Costs: review Fly.io billing. Check Stripe fees.
3. **Cost tracking:**
   - Update lifecycle-cost-model.md with actual costs.
   - Compare actuals to projections.
4. **Dependency health:**
   - Run `pip-audit`. Any new vulnerabilities?
   - Check for major version updates in key dependencies (Flask, Stripe, PyJWT).

**Output:** Updated lifecycle-cost-model.md. Infrastructure action items if any.

---

## 6. Risk Review

**When:** Monthly (same session as operations review, or second Monday if operations review runs long).
**Duration:** 20-30 minutes.

**Protocol:**

1. **Review top 5 risks** from risk-register.md.
   - Has the probability or impact changed?
   - Have mitigation actions been taken?
   - Are there new risks to add?
2. **FIX_INVENTORY status:**
   - Any new defects discovered? Add to FIX_INVENTORY.
   - Any DEFER items that should be reconsidered?
3. **Security scan results:**
   - Review security_audit_log for anomalies.
   - Check crash_log and client_error_log for patterns.
   - Run `pip-audit` if not done in operations review.
4. **Update risk-monitoring-dashboard.md** with current scores and trend arrows.

**Output:** Updated risk-register.md and risk-monitoring-dashboard.md.

---

## 7. Strategy Review

**When:** Quarterly (first week of January, April, July, October).
**Duration:** 60-90 minutes. Block the morning. No coding.

**Protocol:**

1. **Is the product strategy working?**
   - Review go-no-go-criteria.md against current milestone.
   - Are we on track to hit the current milestone's criteria?
   - If not, why not? What changed?
2. **Pivot or persevere?**
   - If go-no-go says "no-go": What are the pivot options? Different audience? Different modality? Different language? Different pricing?
   - If go-no-go says "go": What's the next milestone? What needs to change to hit it?
3. **Backlog re-prioritization:**
   - Read the entire Backlog top to bottom.
   - Remove anything that no longer aligns with strategy.
   - Re-order based on current strategic priorities.
4. **Spiral cycle review:**
   - Update spiral-log.md with the current cycle's outcomes.
   - Define objectives for the next cycle.
5. **Personal check-in:**
   - Energy level? Burnout risk? (See risk R10.)
   - Is this still the right project?
   - What would make the next quarter more sustainable?

**Output:** Updated go-no-go-criteria.md, spiral-log.md, board.md (backlog re-prioritized). Possibly a strategic pivot decision.

---

## Cadence Calendar Summary

| Cadence | Frequency | Day | Duration | Key Output |
|---------|-----------|-----|----------|------------|
| Daily standup | Daily | Every workday | 5 min | Mental clarity, blocker identification |
| Replenishment | Weekly | Monday | 15-30 min | Fresh Ready queue |
| Delivery planning | Weekly | Friday | 10-15 min | Flow metrics update, deploys |
| Service delivery review | Bi-weekly | Friday | 20-30 min | SLE tracking |
| Operations review | Monthly | 1st Monday | 30-45 min | Infrastructure + cost health |
| Risk review | Monthly | 1st or 2nd Monday | 20-30 min | Risk register update |
| Strategy review | Quarterly | 1st week | 60-90 min | Go/no-go decision, backlog reset |

**Total time per week:** ~45-60 minutes of structured review. The rest is building.
