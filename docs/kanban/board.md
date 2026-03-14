# Aelu Kanban Board

> Last updated: 2026-03-10
> Board owner: Jason (solo founder)

## Board Structure

**Columns:** Backlog → Ready → In Progress (WIP: 3) → Review (WIP: 2) → Done
**Swimlanes:** Features | Bugs | Tech Debt | Experiments

---

## Card Template

```
ID:          [TYPE]-[SEQ] (e.g., F-012, B-003, D-007, X-001)
Title:       Short imperative description
Type:        Feature | Bug | Tech Debt | Experiment
Class:       Standard | Expedite | Fixed Date | Intangible
Requester:   Jason | User Feedback | Monitoring
Date Entered:  YYYY-MM-DD
Date Started:  YYYY-MM-DD (when moved to In Progress)
Date Done:     YYYY-MM-DD (when moved to Done)
Blocked-By:  [Item ID or external dependency, if any]
Notes:       Context, acceptance criteria, links
```

---

## Current Board State (2026-03-10)

### Backlog

| ID | Title | Type | Class | Entered |
|----|-------|------|-------|---------|
| F-008 | Listening sub-categories (gist, detail, inference) | Feature | Standard | 2026-02-14 |
| F-009 | Anti-gaming: distractor length normalization | Feature | Standard | 2026-02-14 |
| F-010 | HSK requirements registry per level | Feature | Standard | 2026-02-14 |
| D-005 | SQLite load test (simulate 100 concurrent users) | Tech Debt | Intangible | 2026-03-01 |
| X-002 | A/B test: 12-min vs 8-min default session length | Experiment | Standard | 2026-03-05 |

### Ready

| ID | Title | Type | Class | Entered |
|----|-------|------|-------|---------|
| F-007 | Annual pricing tier ($119.88/yr = 2 months free) | Feature | Standard | 2026-03-01 |
| B-004 | L3: _ensure_indexes incomplete for ~15 tables | Bug | Intangible | 2026-02-25 |
| D-004 | Dependency audit: pin all transitive deps | Tech Debt | Intangible | 2026-03-01 |

### In Progress (WIP: 3 — limit 3)

| ID | Title | Type | Class | Started | Notes |
|----|-------|------|-------|---------|-------|
| F-006 | PMF validation: onboard 10 external beta users | Feature | Standard | 2026-03-08 | Landing page live, collecting signups |
| D-003 | Dead code removal pass (unused imports, phantom tables) | Tech Debt | Intangible | 2026-03-07 | M1-M2 from FIX_INVENTORY done |
| X-001 | Content marketing: r/ChineseLanguage post with demo | Experiment | Standard | 2026-03-09 | Draft written |

### Review (WIP: 2 — limit 2)

| ID | Title | Type | Class | Started | Notes |
|----|-------|------|-------|---------|-------|
| F-005 | GDPR data export/deletion hardening | Feature | Fixed Date | 2026-02-26 | C4-C6 fixed, testing edge cases |

### Done (Recent)

| ID | Title | Type | Class | Started | Done | Lead Time |
|----|-------|------|-------|---------|------|-----------|
| B-001 | Session fixation on login (C1) | Bug | Expedite | 2026-02-25 | 2026-02-25 | <1 day |
| B-002 | Account lockout bypass (C2) | Bug | Expedite | 2026-02-25 | 2026-02-25 | <1 day |
| B-003 | Refresh token expiry bypass (C3) | Bug | Expedite | 2026-02-25 | 2026-02-25 | <1 day |
| D-001 | CI: add coverage floor + ruff (H13-H14) | Tech Debt | Standard | 2026-02-26 | 2026-02-27 | 2 days |
| D-002 | Schema: add migration-only tables to schema.sql (H9) | Tech Debt | Standard | 2026-02-26 | 2026-02-26 | 1 day |
| F-004 | MFA (TOTP) with rate limiting | Feature | Standard | 2026-02-20 | 2026-02-25 | 6 days |

---

## ASCII Board Visualization

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              AELU KANBAN BOARD                                      │
├──────────────┬──────────────┬──────────────┬──────────────┬──────────────────────────┤
│   BACKLOG    │    READY     │ IN PROGRESS  │   REVIEW     │          DONE            │
│  (no limit)  │  (max: 10)   │  (max: 3)    │  (max: 2)    │                          │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────────────────┤
│              │              │              │              │                          │
│ Features:    │ Features:    │ Features:    │ Features:    │ Features:                │
│  F-008       │  F-007       │  F-006       │  F-005       │  F-004                   │
│  F-009       │              │              │              │                          │
│  F-010       │              │              │              │                          │
│              │              │              │              │                          │
│ Bugs:        │ Bugs:        │ Bugs:        │ Bugs:        │ Bugs:                    │
│              │  B-004       │              │              │  B-001, B-002, B-003     │
│              │              │              │              │                          │
│ Tech Debt:   │ Tech Debt:   │ Tech Debt:   │ Tech Debt:   │ Tech Debt:               │
│  D-005       │  D-004       │  D-003       │              │  D-001, D-002            │
│              │              │              │              │                          │
│ Experiments: │ Experiments: │ Experiments: │ Experiments: │ Experiments:             │
│  X-002       │              │  X-001       │              │                          │
│              │              │              │              │                          │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────────────────┤
│    5 items   │   3 items    │   3 items    │   1 item     │        6 items           │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────────────────┘

WIP Status: In Progress 3/3 (AT LIMIT) │ Review 1/2 (OK)
```

---

## Policies

- **Pull-based:** Items move left to right. Only pull new work when capacity opens.
- **Done definition:** Deployed to Fly.io, tested in production, no open regressions.
- **Abandoned items:** If an item has been In Progress for >14 days with no activity, discuss whether to split, deprioritize, or kill.
- **Board review:** Every Monday during replenishment cadence.
