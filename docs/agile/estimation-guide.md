# Aelu Estimation Guide

**Last Updated:** 2026-03-10

---

## Core Principle: Relative Sizing, Not Time Estimates

Story points measure complexity relative to other stories. They are not hours, not days, not "ideal developer time." A 5-point story is roughly 2.5x the complexity of a 2-point story -- not 2.5x the hours. Complexity includes code changes, test effort, risk, and number of modules touched.

Never convert story points to hours. If someone asks "how many hours is 5 points?", the answer is "5 points." The translation from points to calendar time happens through velocity, not through per-story hour estimates.

---

## Fibonacci Scale

Use only these values: **1, 2, 3, 5, 8, 13**.

The Fibonacci sequence enforces imprecision at larger sizes, which is honest -- a 13-point story has far more uncertainty than a 2-point story, and the scale reflects that. You cannot estimate a large item with the same precision as a small one.

Estimates of 0 or 21+ are not allowed. If it's trivial enough to be 0, just do it -- don't put it in the backlog. If it's 21+, split it.

---

## Reference Stories by Point Value

These are real Aelu stories that anchor each point value. When estimating a new story, compare it to these references.

### 1 Point -- Trivial Change

**Reference:** Update drill prompt copy in `ui_labels.py`
- Scope: 1 file modified, no logic change
- Tests: Existing tests cover it (or a 1-line assertion)
- Risk: Near zero -- it's a string change
- Modules: `ui_labels.py` only
- Deploy concern: None

**Other 1-point examples:**
- Fix a typo in a context note
- Add a new entry to `config.py` defaults
- Update CSP header to allow a new font CDN

### 2 Points -- Small, Clear Scope

**Reference:** PB-005 Session progress bar ("X of Y drills complete")
- Scope: 2-3 files (template + WebSocket message + minor route change)
- Tests: 1-3 new tests
- Risk: Low -- display-only, no data model changes
- Modules: `web/templates/session.html`, `web/routes.py`
- Deploy concern: Visual check on web + iOS

**Other 2-point examples:**
- PB-019 Audio timing overlap fix (stop previous audio before new drill)
- Add a new column to an existing admin dashboard table
- Implement a single new drill type variation within the existing drill framework

### 3 Points -- Moderate, Touches Multiple Files

**Reference:** PB-002 Onboarding completion rate tracking
- Scope: 3-5 files (new `lifecycle_event` logging in `auth.py`, new admin route, new template section)
- Tests: 5-8 new tests (unit + integration with `test_client`)
- Risk: Moderate -- touches auth flow, but additive (no existing behavior changed)
- Modules: `auth.py`, `web/routes.py`, `web/templates/admin.html`, `db/core.py`
- Deploy concern: Verify lifecycle events are logged correctly in production

**Other 3-point examples:**
- PB-006 User interview recruitment flow
- PB-011 HSK level completion celebration
- PB-018 Stale WebSocket reconnection after sleep

### 5 Points -- Significant, New Algorithm or Schema Touch

**Reference:** PB-012 Passage difficulty calibration
- Scope: 5-8 files, includes algorithm logic and possibly `vocab_encounter` schema interaction
- Tests: 10+ tests (unit tests for algorithm, integration tests for route behavior)
- Risk: Moderate-high -- algorithmic change affects learning outcomes, needs careful thresholds
- Modules: `scheduler.py`, `web/routes.py`, `db/core.py`, reading templates
- Deploy concern: Monitor `vocab_encounter` data and passage selection patterns for 48h

**Other 5-point examples:**
- PB-003 Trial-to-paid conversion dashboard
- PB-007 Churn prediction alerts
- PB-014 Offline mode polish

### 8 Points -- Large, Multiple Integration Points

**Reference:** PB-004 Email onboarding drip sequence
- Scope: 8-12 files, new external integration (SMTP), background scheduling, unsubscribe handling
- Tests: 15+ tests (unit for email logic, integration for trigger conditions, manual for actual email delivery)
- Risk: High -- external dependency (email delivery), timing-sensitive logic, GDPR compliance (unsubscribe)
- Modules: `email.py`, `scheduler.py`, `auth.py`, `data_retention.py`, `web/routes.py`, templates
- Deploy concern: Test with real email addresses, verify unsubscribe works, monitor bounce rates

**Other 8-point examples:**
- PB-008 Referral/invite system polish
- PB-029 WCAG 2.1 AA accessibility audit
- PB-033 SRS interval tuning experiment (feature flag + cohort tracking)

### 13 Points -- Epic, Should Be Split

**Reference:** PB-013 iOS App Store submission
- Scope: Full cross-platform effort, Capacitor build, Apple review process, ASO setup
- Tests: E2E tests on iOS simulator, full onboarding flow verification
- Risk: Very high -- external dependency (Apple review), unpredictable timeline
- Modules: Nearly everything (web, auth, sessions, drills, payment, onboarding)
- Deploy concern: App Store review is a black box

**Other 13-point examples:**
- PB-022 HSK 4-5 context notes (150+ items, content creation + review + quality check)
- PB-032 Dialogue scenario expansion (20 new scenarios following `storytelling_standard.md`)

**Rule:** 13-point stories should be split before entering a sprint. If they cannot be split, they consume the entire sprint and leave no buffer for unplanned work.

---

## Planning Poker Process (Solo + Claude Code)

For a solo developer using AI-assisted development, planning poker adapts as follows:

### Step 1: Read the Story Aloud
Read the user story and acceptance criteria. Don't skim. The act of reading forces you to confront what's actually being asked.

### Step 2: Identify Complexity Dimensions
For each story, assess these five dimensions:

| Dimension | Low (1-2) | Medium (3-5) | High (8-13) |
|---|---|---|---|
| Files touched | 1-2 | 3-5 | 6+ |
| New tests needed | 0-3 | 4-10 | 10+ |
| Schema changes | None | Add column/index | New table or constraint migration |
| External dependencies | None | Internal API change | Third-party service (Stripe, Apple, SMTP) |
| Uncertainty | Clear path | Some unknowns | Significant unknowns or research needed |

### Step 3: Compare to Reference Stories
Find the reference story (above) that feels most similar in complexity. Start from there.

### Step 4: Adjust Up or Down
- If it has more uncertainty than the reference: +1 Fibonacci step
- If it touches more modules than the reference: +1 Fibonacci step
- If it's purely additive (no existing behavior changes): -1 Fibonacci step
- If you've done something nearly identical before: -1 Fibonacci step

### Step 5: Commit to a Number
Pick a Fibonacci number. Don't deliberate for more than 2 minutes per story. If you're stuck between two numbers, pick the higher one. Optimism is the most common estimation failure mode.

---

## Estimation Anti-Patterns

**Anchoring to time:** "This will take 2 days, so it's 5 points." No. Points are relative complexity. A 5-point story might take 1 day or 4 days depending on interruptions, debugging time, and deploy complications.

**Precision theater:** "This is exactly 4 points." There is no 4 on the Fibonacci scale. If it's between 3 and 5, pick one. The gap is intentional.

**Sandbagging:** Consistently over-estimating to guarantee completion. This inflates velocity and makes forecasting unreliable. If you complete 20 "points" every sprint but the stories were really 12 points of work, your velocity is lying.

**Heroic estimation:** Consistently under-estimating to pack more into a sprint. This creates carryover, which demoralizes and destabilizes velocity.

**Estimating in a vacuum:** Not looking at reference stories or past velocity. Every estimate should be grounded in comparison to known work.

**Re-estimating completed stories:** "That 5-pointer was really only a 3." Don't retroactively change estimates. The gap between estimate and reality is useful information -- it calibrates future estimates.

**Conflating effort with complexity:** A story that requires writing 200 context notes is high-effort but low-complexity per note. Estimate the complexity of the system, not the tedium of the content.

---

## Re-Estimation Triggers

Re-estimate a story (before pulling it into a sprint) when:

1. **Scope changed.** Acceptance criteria were added or modified since the original estimate.
2. **Dependencies changed.** A dependency was resolved or a new one was discovered (e.g., turns out a schema migration is needed).
3. **Codebase changed.** The relevant module was refactored since the estimate, making the work easier or harder.
4. **3+ sprints old.** If an item was estimated more than 6 weeks ago and hasn't been pulled, re-estimate. Context fades.
5. **Carryover.** If an item carried over from a previous sprint, re-estimate the remaining work (not the total -- just what's left).

Do NOT re-estimate:
- Mid-sprint (commit to the estimate you planned with)
- After completion (leave the original estimate for velocity tracking)
- Because velocity looks bad (velocity is observed, not managed)

---

## Estimation Checklist

Before finalizing an estimate, verify:

- [ ] Compared to at least one reference story
- [ ] Considered all five complexity dimensions
- [ ] Accounted for test writing effort (not just implementation)
- [ ] Accounted for cross-platform testing (web + iOS + macOS if user-facing)
- [ ] Accounted for deploy + 24h monitoring requirement from Definition of Done
- [ ] If estimated at 13: confirmed it cannot be split further
- [ ] If estimated at 1: confirmed it's truly trivial (not just optimism)
