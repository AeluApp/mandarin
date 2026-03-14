# Service Level Expectations (SLEs)

> Last updated: 2026-03-10

## Definition

An SLE is a probabilistic statement: "X% of items of this class will be completed within Y days." It is not a promise — it is a forecast based on historical data. SLEs set expectations for how long work should take, and trigger reviews when reality deviates.

---

## SLEs by Class of Service

### Expedite (Production Incidents)

**Examples:** Crash loop on Fly.io, SQLite corruption, auth bypass, data loss.

| Metric | Target |
|--------|--------|
| 85th percentile resolution | 4 hours |
| 100th percentile resolution | 24 hours |

**Rationale:** Aelu is a paid product. If the service is down or insecure, every minute erodes trust. 4 hours is achievable for a solo founder who monitors alerts. 24 hours is the absolute ceiling — if it takes longer, something structural is broken.

**Measurement:** Time from alert/discovery to deploy of fix. Tracked in crash_log and security_audit_log tables.

**If breached:** Post-incident review. Ask: Was the issue detectable earlier? Was the fix obvious but deployment was slow? Should monitoring be improved?

---

### Fixed Date (External Deadlines)

**Examples:** Apple App Store submission deadlines, GDPR deletion requests (30-day SLA), annual Apple Developer renewal, Stripe compliance requirements.

| Metric | Target |
|--------|--------|
| Completion | 3 calendar days before deadline |

**Rationale:** Buffer for review rejections, unexpected issues, or personal emergencies. Submitting the day of a deadline is gambling.

**Known fixed dates:**
| Item | Deadline | Buffer Date |
|------|----------|-------------|
| GDPR deletion requests | 30 days from request | Day 27 |
| Apple Developer renewal | Annual (February) | 2027-02-01 |
| iOS app review submissions | Per release cycle | 5 business days before target launch |

**Measurement:** `Deadline - Date Done`. Must be >= 3 days.

**If breached:** Identify why the deadline was missed. Was scope too large? Was the deadline not visible on the board? Add earlier warning (move to Ready 2 weeks before deadline).

---

### Standard (Features, Improvements)

**Examples:** Annual pricing tier, listening sub-categories, content marketing experiments, UX improvements.

| Metric | Target |
|--------|--------|
| 85th percentile lead time | 14 calendar days |

**Rationale:** Two weeks is a reasonable upper bound for any standard feature in a solo-founder context. If a feature takes more than 14 days end-to-end, it was either too large (should have been split) or blocked (should have been flagged).

**Current performance:** Based on 10 tracked items, P85 lead time is 6 days. The 14-day target has significant headroom — this is intentional. As the product matures, cycle times may increase due to integration complexity, testing burden, or marketing/growth work competing for time.

**Measurement:** Lead time per item. Tracked in flow metrics table.

**If breached regularly (>15% of items exceed 14 days):**
- Are items too large? Institute a "split before starting" rule.
- Are items blocked? Improve dependency management.
- Is WIP too high? Enforce limits more strictly.

---

### Intangible (Tech Debt, Refactoring, Housekeeping)

**Examples:** Dead code removal, dependency updates, index optimization, test coverage improvements, documentation.

| Metric | Target |
|--------|--------|
| 85th percentile lead time | 30 calendar days |

**Rationale:** Intangible work is important but not urgent. 30 days acknowledges that it gets deprioritized when features and bugs demand attention. But 30 days is the ceiling — if tech debt sits longer, it's been effectively abandoned and should be removed from the board.

**Measurement:** Lead time per item.

**If breached:** At the monthly operations review, check: is intangible work being starved? Is the intangible slot in WIP actually being used? If intangible items consistently age past 30 days, increase the allocation (give intangible a dedicated slot or timebox one day per week).

---

## SLE Achievement Tracking

Reviewed monthly at the service delivery review cadence.

| Month | Expedite (<4h) | Fixed Date (3d buffer) | Standard (<14d) | Intangible (<30d) | Overall |
|-------|---------------|----------------------|-----------------|-------------------|---------|
| Feb 2026 | 3/3 = 100% | 0/0 = N/A | 3/4 = 75% | 2/2 = 100% | 89% |
| Mar 2026 | — | — | — | — | — |

---

## Escalation Policy

**If SLE achievement drops below 70% in any class for a given month:**

1. **Hold a service delivery review within 3 days.** Not at the next scheduled cadence — this week.
2. **Identify root cause.** Categories:
   - **Scope:** Items are too large. Action: enforce splitting.
   - **Blocking:** External dependencies or unclear requirements. Action: identify and resolve blockers before pulling into In Progress.
   - **Capacity:** More work than one person can handle. Action: reduce Ready queue size, say no to new work.
   - **Quality:** Rework is inflating cycle time. Action: improve testing, add pre-flight checklists.
3. **Implement one specific change.** Not a vague resolution — one concrete process change.
4. **Review at next month's service delivery cadence.** Did the change help?

---

## Relationship to Other Artifacts

- **Classes of Service** (`classes-of-service.md`): Defines what qualifies for each class.
- **Flow Metrics** (`flow-metrics.md`): Provides the raw data for SLE measurement.
- **Aging WIP** (`aging-wip.md`): Early warning system — if items are aging beyond average cycle time, they may breach SLEs.
- **Cadences** (`cadences.md`): Service delivery review is where SLE achievement is formally checked.
