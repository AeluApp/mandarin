# Ishikawa (Fishbone) Diagram Templates — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10

---

## 1. Category Framework

Aelu uses a modified 5M framework adapted for software + educational content:

| Category | Aelu Equivalent | What It Covers |
|----------|----------------|---------------|
| **People** | Learner / Developer | Learner confusion, developer error, misunderstood requirements |
| **Process** | SRS / Scheduling / Grading | Algorithm miscalibration, workflow gaps, logic errors |
| **Technology** | Infrastructure / Client | Server latency, SQLite contention, browser compatibility, Capacitor shell |
| **Content** | Curriculum / Drill Items | Ambiguous items, missing alternatives, difficulty miscalibration |
| **Environment** | Network / Device / Context | Connection quality, device capabilities, study context (noise, interruptions) |

---

## 2. Blank Template

```
                         ┌──────────────┐
            People       │              │      Technology
           ╱             │   DEFECT:    │              ╲
          ╱              │   [describe  │               ╲
    ─────╱───────────────│    here]     │────────────────╲─────
         ╲               │              │               ╱
          ╲              │              │              ╱
           ╲             └──────────────┘             ╱
            Process              │              Content
                                 │
                            Environment
```

For each category, list 2-5 potential causes. For each cause, ask "why?" to drill deeper. The fishbone identifies candidates; the 5 Whys (see `5-whys-template.md`) confirms root cause.

---

## 3. Worked Example 1: "Drill Shows Wrong Answer"

**Defect:** Learner answers correctly but system marks it wrong (false negative).

```
                              ┌──────────────────────────┐
               People         │                          │      Technology
              ╱               │  DEFECT: Drill shows     │               ╲
             ╱                │  wrong answer (false      │                ╲
            ╱                 │  negative)                │                 ╲
           ╱                  │                          │                  ╲
──────────╱───────────────────│                          │───────────────────╲──────
          ╲                   │                          │                  ╱
           ╲                  │                          │                 ╱
            ╲                 └──────────────────────────┘                ╱
             ╲                             │                            ╱
              Process                      │                      Content
                                      Environment
```

### People
- **Learner used valid alternative phrasing** → System only accepts one English translation
  - Why: `content_item.english` is a single TEXT field, not a list
  - Why: Schema designed for simplicity in V1, never expanded
- **Learner used traditional characters** → System expects simplified only
  - Why: No traditional-to-simplified normalization layer
- **Developer didn't anticipate input format** → Edge case in pinyin normalization
  - Why: Test suite didn't cover this specific combination

### Process
- **Pinyin normalizer doesn't handle edge case** → e.g., "nv" without tone number
  - Why: Normalizer handles "nv3" but not bare "nv"
- **Grading logic uses exact match where fuzzy match is appropriate** → translation drills
  - Why: Free-text grading defaulted to exact match for safety
- **Grade appeal process not systematically reviewed** → False negatives persist unreported
  - Why: No weekly review cadence for grade_appeal table

### Technology
- **Unicode normalization inconsistency** → Same-looking characters have different byte sequences
  - Why: NFKC normalization not applied before string comparison
- **IME input adds invisible characters** → Zero-width joiner, BOM bytes
  - Why: Input sanitization strips whitespace but not all invisible Unicode

### Content
- **Content item has only one valid English translation** → "happy" but not "glad" or "pleased"
  - Why: Seed data uses single English value per item
  - Why: Multi-valid-answer support not yet implemented
- **Pinyin in seed data uses non-standard notation** → Inconsistent tone mark placement
  - Why: Manual data entry, no automated validation at seed time
- **Context note missing** → Learner doesn't understand which meaning is expected
  - Why: Context notes only cover HSK 1-3 (299 items); HSK 4-9 items lack them

### Environment
- **Mobile keyboard auto-corrects pinyin input** → "nǐ" auto-corrected to "ni" or "Ni"
  - Why: iOS/Android keyboard treats pinyin tone marks as special characters
- **Copy-paste from dictionary includes hidden formatting** → Rich text pasted into plain text field
  - Why: Input field doesn't strip formatting on paste

### Most Likely Root Causes (to validate with data)
1. Single English translation field (Content) — high impact, known gap
2. Missing NFKC normalization (Technology) — unknown impact, needs investigation
3. No grade appeal review cadence (Process) — allows defects to persist

---

## 4. Worked Example 2: "SRS Overdue Items Spike"

**Defect:** Large number of items past their `next_review_date` without being reviewed. Learner opens app and faces an overwhelming review queue.

```
                              ┌──────────────────────────┐
               People         │                          │      Technology
              ╱               │  DEFECT: SRS overdue     │               ╲
             ╱                │  items spike (50+ items   │                ╲
            ╱                 │  past review date)        │                 ╲
           ╱                  │                          │                  ╲
──────────╱───────────────────│                          │───────────────────╲──────
          ╲                   │                          │                  ╱
           ╲                  │                          │                 ╱
            ╲                 └──────────────────────────┘                ╱
             ╲                             │                            ╱
              Process                      │                      Content
                                      Environment
```

### People
- **Learner took a multi-day break** → Items accumulate past review date
  - Why: Life interruption (travel, illness, busy period)
  - This is user behavior, not a system defect — BUT the system's response to it is a process concern
- **Learner does partial sessions** → Completes 5 of 15 items, exits early
  - Why: Session too long, content too difficult, or lack of time
  - Why: Session length not adapted to learner's available time

### Process
- **Scheduler doesn't cap overdue queue** → After 3-day gap, queue has 45+ items
  - Why: Gap-aware scheduling prioritizes overdue items but doesn't limit batch size
  - Why: No maximum session size for catch-up mode
- **New item budget not paused during overdue** → Scheduler still adds new items while overdue queue is large
  - Why: New item budget is static (not responsive to overdue count)
- **Half-life estimates too short for early items** → Items scheduled too frequently
  - Why: Initial half-life (1.0 day) may be too aggressive
  - Why: No calibration of initial half-life against observed recall data
- **Interleaving enforcement spreads reviews across modalities** → Can't clear overdue reading items because scheduler forces listening items
  - Why: Interleaving constraints are rigid, not relaxed during catch-up

### Technology
- **Session planning takes too long with large overdue queue** → Planning latency > 1s with 50+ candidates
  - Why: Scheduler queries become expensive with many eligible items
  - Why: No index on `next_review_date < current_date AND user_id = ?`
- **UTC timezone mismatch** → Items due "today" in user's timezone are not due in UTC
  - Why: `datetime('now')` returns UTC; user may be UTC-8 (PST)
  - Why: No user timezone setting in `learner_profile`

### Content
- **Too many items at same HSK level** → All seeded at once, all come due at once
  - Why: Batch seeding creates cohorts of items with similar review schedules
  - Why: No staggered introduction of new items
- **Difficulty distribution creates a "wall"** → Many items at difficulty 0.5 (default)
  - Why: Default difficulty not calibrated per item

### Environment
- **Weekend/weekday study pattern mismatch** → User studies Mon-Fri, items scheduled for Saturday go overdue
  - Why: Adaptive day profiles exist but may not have enough data to model weekend patterns
- **Notifications not sent** → User doesn't know items are due
  - Why: Push notification system exists (`push_token` field) but not yet implemented

### Most Likely Root Causes (to validate with data)
1. Scheduler doesn't cap catch-up queue (Process) — directly causes overwhelm
2. New item budget not paused during overdue (Process) — compounds the problem
3. UTC timezone mismatch (Technology) — may cause phantom overdue items

---

## 5. Worked Example 3: "Session Fails to Load"

**Defect:** User opens app, starts a session, and gets an error or blank screen instead of drills.

```
                              ┌──────────────────────────┐
               People         │                          │      Technology
              ╱               │  DEFECT: Session fails   │               ╲
             ╱                │  to load (error screen   │                ╲
            ╱                 │  or blank page)           │                 ╲
           ╱                  │                          │                  ╲
──────────╱───────────────────│                          │───────────────────╲──────
          ╲                   │                          │                  ╱
           ╲                  │                          │                 ╱
            ╲                 └──────────────────────────┘                ╱
             ╲                             │                            ╱
              Process                      │                      Content
                                      Environment
```

### People
- **New user with no content items available** → Scheduler has nothing to plan
  - Why: Placement test not completed, no items seeded for their level
  - Why: Onboarding flow doesn't ensure minimum content before first session
- **Developer deployed breaking change** → Route handler raises unhandled exception
  - Why: Insufficient test coverage for session start endpoint
  - Why: No staging environment; deploys go directly to production

### Process
- **Session planning returns empty plan** → No items eligible (all reviewed recently, none due)
  - Why: Small content pool (< 20 items) + frequent study = nothing left to schedule
  - Why: No "filler" drill fallback when primary queue is empty
- **JWT token expired** → API returns 401, client shows blank screen
  - Why: Token refresh logic fails silently
  - Why: Client doesn't distinguish auth error from content error
- **Scheduler raises exception on edge case** → e.g., division by zero when `total_attempts = 0`
  - Why: `avg_response_ms` or `half_life_days` can be NULL/0 on first review
  - Why: SQLite Row returns None for LEFT JOIN fields (known pattern)

### Technology
- **CSP blocks resource loading** → CSS/JS fail to load, page renders blank
  - Why: `upgrade-insecure-requests` directive applied on HTTP localhost
  - Why: CSP configuration not conditional on `IS_PRODUCTION`
  - **Note:** This exact bug has occurred before — see MEMORY.md debugging lessons
- **Capacitor iOS redirect opens Safari** → `redirect()` response triggers external browser
  - Why: WKWebView doesn't follow 302 redirects to same-origin
  - Why: Should use `render_template()` instead of `redirect()`
  - **Note:** This exact bug has occurred before — see MEMORY.md debugging lessons
- **SQLite database locked** → Write operation blocks read during session planning
  - Why: WAL mode not enabled, or another process holds a write lock
  - Why: Litestream restoration may leave DB in rollback journal mode
- **Flask server not running on expected port** → Port 5173 conflict or server crash
  - Why: AirTunes uses port 5000 on macOS Monterey+; misconfiguration defaults to 5000

### Content
- **All content items have `status != 'drill_ready'`** → No eligible items for drills
  - Why: Bulk status update accidentally marked items inactive
  - Why: No validation that at least N items are drill_ready after migrations

### Environment
- **Network timeout** → Server unreachable from client
  - Why: Fly.io machine scaled to zero, cold start > 5 seconds
  - Why: Health check endpoint not keeping machine warm
- **iOS app cannot reach HTTP localhost** → ATS blocks insecure connections
  - Why: `NSAllowsLocalNetworking` not in Info.plist
  - **Note:** This exact bug has occurred before — see MEMORY.md debugging lessons
- **Browser cache serving stale JS** → New API contract, old client code
  - Why: No cache-busting strategy (version hash in asset URLs)

### Most Likely Root Causes (to validate with data)
1. CSP `upgrade-insecure-requests` on localhost (Technology) — known, previously fixed
2. Scheduler exception on NULL fields (Process) — systematic, affects edge cases
3. Empty content pool for new users (Process) — affects onboarding

---

## 6. How to Use These Diagrams

### For a New Defect

1. Start with the blank template (section 2)
2. Write the defect description in the center
3. For each of the 5 categories, brainstorm 2-5 potential causes
4. For each cause, ask "why?" once to identify a deeper cause
5. Mark the 2-3 most likely root causes based on available data
6. Validate with data: run SQL queries, check logs, reproduce the defect
7. Apply 5 Whys (see `5-whys-template.md`) to the most likely candidates
8. Implement fix for confirmed root cause

### Common Pitfalls

- **Don't stop at symptoms.** "The server crashed" is not a root cause. Why did it crash?
- **Don't blame the user.** "Learner typed wrong input" is not actionable. Why didn't the system handle that input?
- **Don't skip categories.** Even if Content seems irrelevant to a Technology defect, check anyway. Cross-category causes are often the most insightful.
- **Don't brainstorm in isolation.** Check `crash_log`, `client_error_log`, `error_log`, and `grade_appeal` for data to support or refute each candidate cause.

---

## 7. Category-Specific Investigation Queries

### People — Learner Confusion Signals

```sql
-- Items where experienced learners (mastery_stage >= 'solid') still get wrong
SELECT ci.hanzi, ci.english, p.mastery_stage, el.error_type, COUNT(*) AS errors
FROM error_log el
JOIN content_item ci ON ci.id = el.content_item_id
JOIN progress p ON p.content_item_id = el.content_item_id AND p.user_id = el.user_id
WHERE p.mastery_stage IN ('solid', 'strong', 'mastered')
GROUP BY ci.id, el.error_type
HAVING errors >= 2
ORDER BY errors DESC;
```

### Process — Scheduler Anomalies

```sql
-- Sessions with 0 items planned (scheduler returned empty)
SELECT id, started_at, session_type, items_planned, plan_snapshot
FROM session_log
WHERE items_planned = 0
ORDER BY started_at DESC
LIMIT 10;
```

### Technology — Error Patterns

```sql
-- Most common crash types in last 30 days
SELECT error_type, error_message, COUNT(*) AS occurrences
FROM crash_log
WHERE timestamp >= datetime('now', '-30 days')
GROUP BY error_type, error_message
ORDER BY occurrences DESC
LIMIT 10;
```

### Content — Quality Signals

```sql
-- Items with high error rate AND high presentation count (not just new items)
SELECT
    ci.id, ci.hanzi, ci.english, ci.hsk_level,
    ci.times_shown, ci.times_correct,
    ROUND(100.0 * ci.times_correct / NULLIF(ci.times_shown, 0), 1) AS accuracy_pct
FROM content_item ci
WHERE ci.times_shown >= 10
  AND CAST(ci.times_correct AS REAL) / ci.times_shown < 0.5
ORDER BY accuracy_pct ASC
LIMIT 20;
```
