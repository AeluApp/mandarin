# Classes of Service

> Last updated: 2026-03-10

## Overview

Every item on the Kanban board has a class of service that determines its priority, WIP rules, and service level expectation. The class is assigned when the item enters Ready (or immediately upon discovery for Expedite).

---

## Class Definitions

### Expedite

**Definition:** An unplanned item that requires immediate attention. The cost of delay is severe and immediate.

**Qualifies if ANY of these are true:**
- Production outage (Fly.io app unreachable, health check failing)
- Data loss or corruption (Litestream backup failure, SQLite WAL corruption)
- Security breach (auth bypass, credential exposure, unauthorized access in security_audit_log)
- crash_log spike (>5 unhandled exceptions in 1 hour)
- Stripe webhook failure (payments not processing, subscriptions not updating)

**Does NOT qualify:**
- A bug that annoys you but doesn't affect users
- A test failure in CI that doesn't block deploys
- A cosmetic UI issue
- Performance degradation that doesn't cause errors

**WIP rules:** Bypasses WIP limits. Can start immediately regardless of In Progress count. Must be logged with "WIP override" note on the card.

**SLE:** 85% resolved within 4 hours, 100% within 24 hours.

**Aelu-specific examples:**
| Scenario | Why Expedite |
|----------|-------------|
| `GET /api/health/ready` returning 500 | Users can't access the app. Fly.io may stop the machine. |
| Auth bypass discovered (like C1-C3 from FIX_INVENTORY) | Immediate security risk. All three were fixed same-day. |
| Litestream replication stopped | Backups are the disaster recovery strategy. No backups = data loss risk. |
| SQLite `database is locked` errors in crash_log | Multi-request contention. Users see errors. |
| Stripe `invoice.payment_failed` webhook not processing | Users paying but not getting access, or access not being revoked on failure. |

---

### Fixed Date

**Definition:** Work that must be completed by a specific external deadline. The deadline is not negotiable.

**Qualifies if:**
- Apple App Store review submission with a launch date commitment
- GDPR data deletion request (30-day legal SLA from request date)
- Apple Developer Program annual renewal (account suspension if missed)
- Compliance requirement with a regulatory deadline
- Contractual obligation with a partner (if applicable)

**WIP rules:** Normal WIP limits apply. Plan ahead — move to Ready at least 2 weeks before deadline. Move to In Progress at least 1 week before deadline.

**SLE:** Completed 3 calendar days before the deadline.

**Aelu-specific examples:**
| Scenario | Deadline | Plan Date |
|----------|----------|-----------|
| GDPR deletion request from user@example.com | 30 days from request | Start by day 20, complete by day 27 |
| iOS App Store submission for v1.1 | March 30, 2026 | In Progress by March 20, Review by March 25 |
| Apple Developer renewal | February 2027 | Calendar reminder January 15 |

---

### Standard

**Definition:** Planned work that delivers value to users or the business. Most items fall here. The cost of delay is real but not catastrophic — each day of delay reduces potential value.

**Qualifies if:**
- New feature (annual pricing, listening sub-categories, HSK requirements registry)
- UX improvement (better onboarding flow, session completion screen)
- Content addition (new HSK levels, new dialogue scenarios, graded reader content)
- Marketing initiative (landing page, content marketing post, referral program)
- Bug fix that is not a production emergency

**WIP rules:** Normal WIP limits apply. Pulled from Ready in priority order.

**SLE:** 85th percentile lead time of 14 calendar days.

**Aelu-specific examples:**
| Scenario | Notes |
|----------|-------|
| F-006: PMF validation — onboard 10 beta users | Core business objective right now |
| F-007: Annual pricing tier | Revenue optimization |
| X-001: Reddit content marketing post | Growth experiment |
| B-004: Index optimization for 15 tables | Performance improvement |

---

### Intangible

**Definition:** Work that doesn't deliver direct user value today, but prevents future problems or reduces future costs. The cost of delay is invisible — you won't feel it today, but you'll feel it in 3 months.

**Qualifies if:**
- Test coverage improvement (currently at 55% floor, should be higher for critical paths)
- Documentation updates (BUILD_STATE.md, schema docs)
- Dependency updates (pip-audit findings, security patches)
- Dead code removal (unused imports, phantom table references)
- Performance optimization that isn't user-facing yet
- Refactoring for maintainability
- Infrastructure housekeeping (Fly.io config cleanup, Litestream verification)

**WIP rules:** Normal WIP limits apply. Gets a dedicated slot (slot 3 of 3 in In Progress). If a bug arrives and needs slot 2, intangible work is not displaced — bugs take slot 2, intangible keeps slot 3.

**SLE:** 85th percentile lead time of 30 calendar days.

**Aelu-specific examples:**
| Scenario | Notes |
|----------|-------|
| D-003: Dead code removal | M1-M2 from FIX_INVENTORY |
| D-004: Pin all transitive dependencies | Reproducible builds |
| D-005: SQLite load test for 100 users | Architecture validation |
| L3: Complete _ensure_indexes | Performance safety net |

---

## Allocation Guide

Target allocation of throughput across classes:

| Class | Target % of Throughput | Rationale |
|-------|----------------------|-----------|
| Expedite | ~5% | Should be rare. If >10%, production quality needs investment. |
| Fixed Date | ~10% | Few external deadlines for a solo founder. Mostly GDPR and app store. |
| Standard | ~60% | The majority of work should deliver user/business value. |
| Intangible | ~25% | Generous allocation prevents tech debt accumulation. The "stop expanding, start hardening" philosophy demands this. |

**Monthly check:** At the service delivery review, compute actual allocation. If Intangible drops below 15%, schedule dedicated tech debt time. If Expedite exceeds 10%, hold a risk review.

---

## How to Assign a Class

When an item enters the board:

1. **Is there a production emergency?** → Expedite
2. **Is there an external deadline?** → Fixed Date (record the deadline on the card)
3. **Does it deliver direct user/business value?** → Standard
4. **Is it maintenance, cleanup, or prevention?** → Intangible
5. **Unsure?** → Default to Standard. If it sits in Ready for 2+ weeks without being pulled, reconsider whether it's actually Intangible (or whether it should be removed).

---

## Class Changes

An item's class can change:

- **Standard → Expedite:** A bug that seemed minor turns out to affect production users. Reclassify and apply Expedite rules.
- **Standard → Fixed Date:** An external commitment creates a deadline for something that was previously open-ended.
- **Intangible → Standard:** A tech debt item becomes urgent because it's now blocking a feature.

Document the change on the card with the date and reason.
