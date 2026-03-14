# Waste Register — Aelu Muda Tracking

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Status:** Living document — update when waste is identified or eliminated

---

## Legend

| Column | Description |
|--------|-----------|
| ID | Unique identifier (W###) |
| Waste Type | TIM WOODS category |
| Description | What the waste is |
| Date Identified | When first noticed |
| Date Eliminated | When fixed (blank = open) |
| Impact | H (High), M (Medium), L (Low) |
| Effort | Estimated fix time |
| Status | Open, In Progress, Eliminated, Accepted |

**TIM WOODS categories:**
- **T** = Transport (unnecessary data movement)
- **I** = Inventory (pre-built work not used)
- **M** = Motion (unnecessary user/dev actions)
- **W** = Waiting (idle time)
- **O** = Overproduction (building before need)
- **O** = Over-processing (more than needed)
- **D** = Defects (errors, rework)
- **S** = Skills (underutilized talent)

---

## Eliminated Waste

| ID | Waste Type | Description | Date Identified | Date Eliminated | Impact | Notes |
|----|-----------|-------------|----------------|-----------------|--------|-------|
| W001 | D (Defect) | Dead loggers — logging modules imported but never used, adding import overhead | 2026-02 | 2026-02 | L | Removed unused logger imports across multiple files |
| W002 | D (Defect) | Schema.sql drift — schema file and actual database could diverge during migrations | 2026-01 | 2026-02 | H | Migration system now reconciles schema.sql with actual DB state. Schema version table tracks applied migrations. |
| W003 | D (Defect) | Flaky tests — scheduler race condition caused intermittent test failures | 2026-01 | 2026-02 | M | Root cause: scheduler_lock.py was not properly handling concurrent access in test environment. Fixed with proper lock isolation in tests. |
| W004 | O (Over-processing) | Redundant TESTING config — duplicate configuration for test environment that was never used | 2026-02 | 2026-02 | L | Removed redundant config; tests use standard config with test DB path |
| W005 | D (Defect) | CSP `upgrade-insecure-requests` breaks localhost — Content Security Policy header silently upgraded http://localhost to https://localhost, causing all CSS/JS/font loads to fail | 2026-02 | 2026-02 | H | Fixed with `IS_PRODUCTION` guard — CSP directive only applied when `IS_PRODUCTION=true` |
| W006 | D (Defect) | Capacitor iOS redirects open Safari — Flask `redirect()` responses caused WKWebView to hand off to external Safari instead of navigating within the app | 2026-02 | 2026-02 | H | Replaced `redirect()` with `render_template()` in all routes accessed from iOS |
| W007 | I (Inventory) | Unused imports (2) — imported modules not referenced in code | 2026-02 | 2026-02 | L | Detected by ruff, removed |

---

## Open Waste

| ID | Waste Type | Description | Date Identified | Impact | Effort | Status | Priority |
|----|-----------|-------------|----------------|--------|--------|--------|----------|
| W008 | I (Inventory) | 10 grammar_extra_*.py files — unclear which are active (R1, R2, R3 revisions). Some may be superseded. | 2026-03 | M | 2h | Open | 1 |
| W009 | O (Overproduction) | Classroom system built without teacher users — `classroom`, `classroom_student` tables, `lti_routes.py`, `lti_platform`, `lti_user_mapping` — no teacher users exist | 2026-02 | M | 0h (freeze) | Accepted | — |
| W010 | O (Overproduction) | Affiliate system built without affiliates — `affiliate_partner`, `referral_tracking`, `affiliate_commission`, `discount_code` tables — no affiliate partners exist | 2026-02 | M | 0h (freeze) | Accepted | — |
| W011 | O (Over-processing) | 51 DB tables for < 10 users — schema complexity exceeds operational need at current scale | 2026-03 | L | 0h (accept) | Accepted | — |
| W012 | I (Inventory) | Flutter app prototype (`flutter_app/` directory) — not in production, not being developed | 2026-03 | L | 30m | Open | 3 |
| W013 | I (Inventory) | Desktop app code (`desktop/` directory) — status unclear | 2026-03 | L | 30m | Open | 4 |
| W014 | I (Inventory) | Kubernetes configs (`k8s/` directory) — not used, Fly.io is the deployment platform | 2026-03 | L | 15m | Open | 5 |
| W015 | M (Motion) | Dashboard required before drilling — users must navigate through dashboard to start a session, adding 2-5 seconds of non-learning time | 2026-03 | L | 4h | Open | 6 |
| W016 | W (Waiting) | TTS latency 200-500ms — Browser Web Speech API pause before audio playback | 2026-03 | L | 0h (accept) | Accepted | — |
| W017 | T (Transport) | Full page reloads between drills in some web flows — entire page reloaded instead of SPA transition | 2026-03 | M | 8h | Open | 7 |
| W018 | D (Defect) | Multiple valid English translations not accepted — correct answers graded wrong for items with synonyms (e.g., 高兴 = "happy" / "glad" / "pleased") | 2026-03 | H | 8h | Open | 2 |
| W019 | O (Overproduction) | xAPI export (`xapi.py`) — LRS integration with no LRS consumers | 2026-03 | L | 0h (freeze) | Accepted | — |
| W020 | O (Overproduction) | Caliper export (`caliper.py`) — learning analytics standard with no consumers | 2026-03 | L | 0h (freeze) | Accepted | — |
| W021 | S (Skills) | Solo dev doing marketing/ops/product/engineering — Jason is doing low-leverage tasks (ops, content, marketing) instead of high-leverage tasks (product/engineering) | 2026-03 | H | — | Structural | — |
| W022 | D (Defect) | Traditional character variants not accepted — heritage speakers who type traditional characters are graded wrong | 2026-03 | M | 4h | Open | 8 |
| W023 | O (Over-processing) | 6-stage mastery model may be more granularity than needed — seen/shaky/fair/solid/strong/mastered could be simplified to 3-4 stages | 2026-03 | L | 16h | Open | 10 |
| W024 | M (Motion) | Login required on every visit with expired JWT — re-authentication friction | 2026-03 | L | 2h | Open | 9 |
| W025 | I (Inventory) | Pre-planned drill items never shown — session plans 15 items, user quits at item 8, remaining 7 planned for nothing | 2026-03 | L | 0h (accept) | Accepted | — |
| W026 | W (Waiting) | Fly.io cold start — machine spin-up from stopped state takes 3-8 seconds | 2026-03 | M | 0h (mitigated) | Accepted | — |
| W027 | T (Transport) | Redundant DB queries — dashboard and session planning both query progress table independently | 2026-03 | L | 2h | Open | 11 |

---

## Waste by Category Summary

| Category | Eliminated | Open | Accepted | Total |
|----------|-----------|------|----------|-------|
| Transport (T) | 0 | 2 | 0 | 2 |
| Inventory (I) | 1 | 4 | 1 | 6 |
| Motion (M) | 0 | 2 | 0 | 2 |
| Waiting (W) | 0 | 0 | 2 | 2 |
| Overproduction (O) | 0 | 0 | 4 | 4 |
| Over-processing (O) | 1 | 1 | 1 | 3 |
| Defects (D) | 5 | 2 | 0 | 7 |
| Skills (S) | 0 | 0 | 1 | 1 |
| **Total** | **7** | **11** | **9** | **27** |

---

## Decision Framework: Eliminate vs. Accept

Waste is **eliminated** when:
- Fix is < 4 hours effort AND impact is M or H
- The waste causes user-facing errors (all defects)
- The waste blocks a priority workflow

Waste is **accepted** when:
- Fix requires architectural change AND current scale doesn't justify it
- The waste has negligible runtime cost (unused tables, extra code)
- The waste is structural (solo founder doing everything)
- The waste is already mitigated (Fly.io cold start → min_machines_running=1)

Waste is **frozen** (a form of acceptance) when:
- Features were built prematurely but removing them is more work than leaving them
- The code is stable and not causing bugs
- No new development investment is made until demand appears

---

## Monthly Review Template

```
# Waste Register Review — YYYY-MM

## New Waste Identified This Month
- W###: [description]

## Waste Eliminated This Month
- W###: [how it was fixed]

## Status Changes
- W###: [status change and rationale]

## Top Priority for Next Month
1. W###: [why]
2. W###: [why]

## Cumulative Stats
- Total identified: __
- Total eliminated: __
- Total accepted: __
- Total open: __
- Elimination rate: __% (eliminated / (eliminated + open))
```
