# Risk Monitoring Dashboard

> Last updated: 2026-03-10
> Review cadence: Monthly (risk review cadence)

---

## Top 5 Risks by Current Score

| Rank | ID | Risk | Score | Trend | Last Action | Next Review |
|------|-----|------|-------|-------|------------|-------------|
| 1 | R2 | Key person dependency (solo founder) | 25 | → Stable | Documented all systems in BUILD_STATE.md, automated CI/CD, structured cadences | 2026-04-07 |
| 2 | R1 | No evidence of PMF | 20 | → Stable | Created go-no-go criteria, started beta onboarding effort (F-006) | 2026-04-07 |
| 3 | R10 | Burnout | 20 | → Stable | Implemented WIP limits (max 3), structured weekly cadences, 25% intangible allocation | 2026-04-07 |
| 4 | R3 | SQLite scaling ceiling | 12 | → Stable | No user growth yet to test. Load test (D-005) in backlog. | 2026-04-07 |
| 5 | R7 | COPPA compliance | 10 | → Stable | ToS requires 13+. No age verification implemented. | 2026-04-07 |

**Trend Legend:**
- ↑ Increasing — risk is getting worse, needs urgent attention
- → Stable — no change since last review
- ↓ Decreasing — mitigation is working, risk is reducing

---

## Risk Heatmap

Probability (Y) vs Impact (X). Risk IDs plotted in cells.

```
        │ Impact
   P    │  1          2          3          4          5
   r    │ Negligible  Minor      Moderate   Major      Catastrophic
   o    │
   b  5 │             ·          ·          ·          R2
      A │             ·          ·          ·          ·
      l │             ·          ·          ·          ·
   i  4 │             ·          ·          ·          R1, R10
      m │             ·          ·          ·          ·
      o │             ·          ·          ·          ·
   s  3 │             ·          R5, R13    R3         ·
      t │             ·          R17        ·          ·
        │             ·          ·          ·          ·
   C  2 │             ·          R4, R9     R6, R11    R7, R16
   e    │             ·          R14        ·          ·
   r    │             ·          ·          ·          ·
   t  1 │             ·          ·          R12        R8, R15
   .    │             ·          ·          ·          ·
        └──────────────────────────────────────────────────
```

**Reading the heatmap:**
- Upper-right quadrant (high probability + high impact) = Critical. **R1, R2, R10** live here.
- Middle band = High/Medium. **R3** is the main technical risk here.
- Lower-left = Low priority. No risks here currently (good).
- Empty upper-left = expected. High probability + low impact items are annoyances, not risks.

---

## Risk Movement Log

Track when risks change score or status.

| Date | Risk ID | Change | From | To | Reason |
|------|---------|--------|------|----|--------|
| 2026-03-10 | All | Initial assessment | — | Current scores | Risk register created |

*(Update this table at each monthly risk review.)*

---

## Mitigation Action Tracker

Active mitigation actions with deadlines.

| Risk ID | Action | Owner | Deadline | Status |
|---------|--------|-------|----------|--------|
| R1 | Onboard 10 beta users (F-006) | Jason | 2026-04-10 | In Progress |
| R1 | Publish Reddit post (X-001) | Jason | 2026-03-15 | In Progress |
| R2 | Complete BUILD_STATE.md and all documentation | Jason | 2026-03-10 | Done |
| R2 | Automate deploy (CI/CD → Fly.io) | Jason | 2026-03-31 | Not Started |
| R3 | Load test for 100 concurrent users (D-005) | Jason | 2026-04-30 | Backlog |
| R7 | Add age verification gate if minor usage detected | Jason | Triggered by evidence | Monitoring |
| R8 | Monthly Litestream restore test | Jason | 2026-04-07 | Not Started |
| R10 | Maintain WIP limits, weekly cadences | Jason | Ongoing | Active |
| R13 | Evaluate Python 3.12 migration | Jason | 2026-06-30 | Backlog |

---

## Monthly Review Template

Copy this template for each monthly risk review:

```markdown
### Risk Review — [YYYY-MM-DD]

**Reviewer:** Jason

**Top 5 risks (any changes from last month?):**
1. R__ — Score: __ — Trend: __ — Notes:
2. R__ — Score: __ — Trend: __ — Notes:
3. R__ — Score: __ — Trend: __ — Notes:
4. R__ — Score: __ — Trend: __ — Notes:
5. R__ — Score: __ — Trend: __ — Notes:

**New risks identified:**
-

**Risks resolved or retired:**
-

**Mitigation actions completed:**
-

**Mitigation actions overdue:**
-

**FIX_INVENTORY check:**
- New defects since last review:
- DEFER items to reconsider:

**Security scan results:**
- pip-audit: [clean / N vulnerabilities]
- crash_log review: [clean / patterns found]
- security_audit_log review: [clean / anomalies found]

**Overall risk posture:** [Improving / Stable / Deteriorating]
```

---

## Risk Posture Summary

**Current posture: Pre-Launch / High Uncertainty**

The three critical risks (R1, R2, R10) are all existential and structural — they won't be resolved by writing code. R1 (no PMF evidence) can only be resolved by external users. R2 (key person dependency) can only be resolved by either: reducing scope to what one person can sustain, or growing enough to hire. R10 (burnout) is managed through process discipline (WIP limits, cadences) but remains a constant pressure.

The technical risks (R3, R6, R7, R8, R9, R13) are all manageable and well-understood. None of them are likely to cause failure in the next 6 months. They become relevant only if PMF is achieved and user growth creates scaling pressure.

**Bottom line:** The risk profile is dominated by market and operational risks, not technical risks. The code works. The question is whether anyone besides Jason wants it.
