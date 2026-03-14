# Aelu Feedback Loop

**Last Updated:** 2026-03-10

---

## Existing Feedback Mechanisms

### 1. Grade Appeal Table (`grade_appeal`)
**What it captures:** Users can appeal a drill grade they believe is incorrect. Stores the drill context, user answer, expected answer, and appeal reason.
**Where it lives:** `grade_appeal` table in SQLite, accessible via admin dashboard.
**Current status:** Infrastructure exists. Schema supports it. No appeals have been submitted (no external users yet).
**Gap:** No UI prompt encourages users to appeal. The feature exists in the API but may be undiscoverable.

### 2. User Feedback Table + API Endpoint (`user_feedback`, `/api/feedback`)
**What it captures:** Free-text feedback with a `feedback_type` field (general, bug, feature_request, nps).
**Where it lives:** `user_feedback` table, submitted via `POST /api/feedback`.
**Current status:** Table and endpoint exist. No feedback has been submitted.
**Gap:** No in-app UI triggers the feedback submission. The endpoint exists but users have no way to reach it without knowing the API.

### 3. Client Error Log (`client_error_log`)
**What it captures:** JavaScript errors from the web/mobile client. Includes error message, stack trace, URL, user agent.
**Where it lives:** `client_error_log` table, submitted automatically by error handler in app.js.
**Current status:** Active. Captures errors during development and testing.
**Gap:** Errors are logged but not reviewed on a regular cadence. No alerting when error volume spikes.

### 4. NPS Collection Capability
**What it captures:** Net Promoter Score (0-10) with follow-up text.
**Where it lives:** Would use `user_feedback` table with `feedback_type='nps'`.
**Current status:** The storage mechanism exists but no NPS prompt is shown to users. See `nps-framework.md` for the implementation plan.
**Gap:** Not implemented in the UI. No trigger logic exists.

### 5. Crash Log (`crash_log`)
**What it captures:** Server-side unhandled exceptions with traceback, request context, and user ID.
**Where it lives:** `crash_log` table.
**Current status:** Active. Monitored as part of the Definition of Done (24-hour check post-deploy).
**Gap:** No automated alerting. Requires manual SQL query to check.

### 6. Session Metrics (`session_metrics`)
**What it captures:** Per-session aggregate stats: drills attempted, accuracy, time spent, completion status.
**Where it lives:** `session_metrics` table.
**Current status:** Active. Populated for every completed session.
**Gap:** Data exists but is not surfaced in a way that informs product decisions. No dashboard view shows trends.

### 7. Lifecycle Events (`lifecycle_event`)
**What it captures:** Key user lifecycle transitions: signup, onboarding_complete, first_session, subscription_start, churn.
**Where it lives:** `lifecycle_event` table.
**Current status:** Table exists. Events are logged for some transitions.
**Gap:** Not all meaningful transitions are tracked. No funnel analysis view in admin dashboard.

---

## Identified Gaps

| Gap | Severity | Status |
|---|---|---|
| No in-app feedback UI (users can't submit feedback without knowing the API) | High | Open |
| No NPS prompt shown to users | High | Open — see nps-framework.md |
| No automated alerting for crash_log or client_error_log spikes | Medium | Open |
| No regular cadence for reviewing feedback data | High | Open |
| No evidence that any feedback has influenced a product decision | Critical | Open |
| Grade appeal feature exists but is undiscoverable | Medium | Open |
| Session metrics exist but no trend dashboard | Medium | Open |
| Lifecycle funnel analysis not implemented | Medium | Open |

---

## Feedback-to-Action Log

This log tracks the complete lifecycle of feedback: from collection through analysis to product action. Every piece of feedback that results in a product change should be recorded here.

### Format

| # | Source | Date Received | Verbatim Feedback | Category | Action Taken | Backlog Item | Date Resolved |
|---|---|---|---|---|---|---|---|

### Entries

| # | Source | Date Received | Verbatim Feedback | Category | Action Taken | Backlog Item | Date Resolved |
|---|---|---|---|---|---|---|---|
| 1 | Usability test (Sprint 1) | 2026-03-20 | "I don't know if I should guess or skip on the placement test" | UX | Updated placement test copy to say "It's okay to guess — this just helps us start at the right level" | PB-001 (related) | 2026-03-20 |
| 2 | Usability test (Sprint 1) | 2026-03-20 | "Oh, this is calmer than Duolingo" | UX (positive) | No action needed — validates Civic Sanctuary aesthetic | — | — |
| 3 | Self-testing | 2026-02-17 | Audio overlaps when answering drills quickly | Bug | Identified as PB-019 in product backlog | PB-019 | Open |
| 4 | Self-testing | 2026-02-21 | WebSocket drops after laptop sleep, blank screen on wake | Bug | Identified as PB-018 in product backlog | PB-018 | Open |
| 5 | Self-testing | 2026-03-01 | Progress view doesn't break down by HSK level clearly enough | UX | Noted for usability testing validation | PB-003 (related) | Open |
| 6 | grade_appeal (hypothetical) | — | "I typed 'ma1' but it wanted 'mā' — both should be accepted" | Content/Grading | Verify pinyin grading accepts both numbered and diacritical tone formats | — | Open |
| 7 | user_feedback (hypothetical) | — | "I wish I could see which words I keep getting wrong" | Feature Request | Error focus view exists (error_focus table) but may not be surfaced in UI | — | Open |
| 8 | client_error_log (hypothetical) | — | "TypeError: Cannot read property 'hanzi' of null" | Bug | Likely a null content_item in drill rendering — needs investigation | — | Open |
| 9 | NPS detractor (hypothetical) | — | "Too many drill types. I just want flashcards." | UX | Consider adding a "simple mode" with reduced drill variety for users who want that | — | Open |
| 10 | NPS promoter (hypothetical) | — | "The tone drills are incredible. No other app does this." | UX (positive) | Validates tone drill investment. Consider highlighting in marketing. | — | — |

---

## Process: Closing the Loop

### Weekly Review (15 minutes, every Monday)
1. Query `crash_log` and `client_error_log` for new entries since last review
2. Query `user_feedback` for new submissions
3. Query `grade_appeal` for new appeals
4. For each new entry: categorize, add to the Feedback-to-Action Log, create a backlog item if warranted
5. Update this document

### Monthly Review (30 minutes, first Monday of month)
1. Review all Feedback-to-Action Log entries from the past month
2. Count: how many feedback items resulted in product changes? How many are still open?
3. Calculate the feedback-to-action ratio (actions taken / feedback received)
4. If the ratio is below 30%, investigate why feedback is being ignored
5. Review session_metrics trends: is session completion rate improving? Drill accuracy stable?

### Quarterly Review (1 hour, aligned with usability testing)
1. Conduct usability test (see usability-testing-plan.md)
2. Review NPS trend (see nps-framework.md)
3. Synthesize: what are the top 3 user pain points right now?
4. Ensure the top 3 pain points are represented in the product backlog's top 10 items
5. Update user-research-protocol.md if interview questions need refreshing

---

## Success Metrics

| Metric | Target | Current |
|---|---|---|
| Feedback-to-action ratio (% of feedback that results in a change) | >30% | N/A (no external feedback yet) |
| Time from feedback to resolution (median) | <14 days for bugs, <30 days for features | N/A |
| Weekly review completed | 100% of weeks | Not started |
| NPS collected | >30% response rate among prompted users | Not implemented |
| Usability test rounds completed per year | 4 | 0 |
