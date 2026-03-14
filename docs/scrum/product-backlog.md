# Aelu Product Backlog

**Product:** Aelu Mandarin Learning System
**Product Owner:** Jason Gerson
**Last Updated:** 2026-03-10

---

## Prioritization Rationale

Items are ordered by PMF-validation urgency first, revenue protection second, infrastructure third. The top of the backlog focuses on getting real users through the funnel and learning whether the product works for people who are not Jason. Infrastructure and nice-to-haves sit at the bottom.

---

## Backlog Items

### PB-001: Guided First Session Experience
**User Story:** As a new user who just signed up, I want the first study session to feel guided and low-stakes so that I don't abandon the app before understanding what it does.
**Acceptance Criteria:**
- Given a user has completed onboarding, When they start their first session, Then the system presents a 3-drill warm-up with inline explanations of how drills work
- Given a user completes the warm-up, When they finish, Then they see a brief summary showing what they learned and what comes next
- Given a user abandons mid-warm-up, When they return, Then they resume from where they left off, not from scratch
**Story Points:** 5
**Business Value:** High
**Status:** Ready

---

### PB-002: Onboarding Completion Rate Tracking
**User Story:** As the product owner, I want to see what percentage of signups complete onboarding and their first session so that I can identify where users drop off.
**Acceptance Criteria:**
- Given a user starts onboarding, When they complete each step, Then a lifecycle_event is logged with step name and timestamp
- Given the admin dashboard is loaded, When I view the onboarding funnel, Then I see step-by-step completion rates (signup -> profile -> placement -> first session -> second session)
- Given I have funnel data for 30+ users, When I view the report, Then I see both aggregate percentages and per-cohort (weekly) breakdowns
**Story Points:** 3
**Business Value:** High
**Status:** Ready

---

### PB-003: Trial-to-Paid Conversion Dashboard
**User Story:** As the product owner, I want to see trial-to-paid conversion rates segmented by acquisition channel so that I know which channels are worth investing in.
**Acceptance Criteria:**
- Given a user converts from trial to paid, When I view the admin dashboard, Then I see the conversion rate by source (organic, affiliate, invite code)
- Given I have conversion data, When I view the cohort analysis, Then I see 7-day, 14-day, and 30-day conversion rates
- Given a user churns during trial, When I review the data, Then I can see their last session date and total sessions completed
**Story Points:** 5
**Business Value:** High
**Status:** Ready

---

### PB-004: Email Onboarding Drip Sequence
**User Story:** As a new user who signed up but hasn't completed a session in 3 days, I want to receive a helpful reminder email so that I'm nudged back before I forget about the app entirely.
**Acceptance Criteria:**
- Given a user signed up but has 0 completed sessions, When 3 days have passed, Then they receive a "Getting Started" email with a direct link to their first session
- Given a user completed 1 session but not 2, When 5 days have passed since session 1, Then they receive a "Your second session" email
- Given a user has completed 5+ sessions, When the drip sequence would fire, Then it does not send (they're already engaged)
- Given a user has unsubscribed, When any drip would fire, Then no email is sent
**Story Points:** 8
**Business Value:** High
**Status:** Ready

---

### PB-005: Session Completion Rate Improvement
**User Story:** As a learner mid-session, I want a visible progress indicator so that I know how many drills remain and don't abandon out of uncertainty.
**Acceptance Criteria:**
- Given a session is in progress, When a drill is completed, Then a progress bar shows "X of Y drills complete"
- Given a user is on the last drill, When they see the progress bar, Then it clearly indicates this is the final drill
- Given a user abandons a session, When they return, Then the abandoned session is logged with the drill number where they stopped
**Story Points:** 2
**Business Value:** High
**Status:** Ready

---

### PB-006: User Interview Recruitment Flow
**User Story:** As the product owner, I want to recruit active users for 15-minute feedback calls so that I get qualitative input on what's working and what's confusing.
**Acceptance Criteria:**
- Given a user has completed 10+ sessions, When they finish a session, Then they see a non-intrusive "Share feedback?" prompt (dismissable, shown once per 30 days)
- Given a user clicks the prompt, When the form appears, Then they can enter their email and preferred time for a call
- Given a user submits the form, When I check the admin dashboard, Then their contact info and usage stats appear in an interview candidates list
**Story Points:** 3
**Business Value:** High
**Status:** Ready

---

### PB-007: Churn Prediction Alerts
**User Story:** As the product owner, I want to be alerted when a paying user shows churn signals so that I can intervene before they cancel.
**Acceptance Criteria:**
- Given a paying user's session frequency drops by 50% week-over-week, When the churn_detection module runs, Then an alert is logged and visible in the admin dashboard
- Given a user has not logged in for 7 days, When the detection runs, Then they are flagged as "at risk"
- Given a user is flagged as at risk, When I view the dashboard, Then I see their usage history, last session date, and subscription renewal date
**Story Points:** 5
**Business Value:** High
**Status:** Ready

---

### PB-008: Referral/Invite System Polish
**User Story:** As an active user, I want to share Aelu with a friend and get credit when they subscribe so that I feel rewarded for spreading the word.
**Acceptance Criteria:**
- Given a user is on the settings page, When they click "Invite a friend," Then a unique invite link is generated and copyable
- Given a new user signs up via an invite link, When they subscribe, Then the referrer receives a 1-month credit applied to their next billing cycle
- Given a referrer has earned credits, When they view their account, Then they see a history of successful referrals and credits earned
**Story Points:** 8
**Business Value:** High
**Status:** Ready

---

### PB-009: NPS Collection Implementation
**User Story:** As the product owner, I want to collect Net Promoter Scores from active users so that I have a quantitative measure of satisfaction over time.
**Acceptance Criteria:**
- Given a user completes their 10th session, When the session ends, Then an NPS prompt appears (0-10 scale)
- Given a user selects 0-6 (detractor), When they submit, Then a follow-up text box asks "What would need to change?"
- Given a user selects 9-10 (promoter), When they submit, Then a follow-up asks "What do you like most?"
- Given NPS data exists, When I view the admin dashboard, Then I see monthly NPS score, trend, and verbatim comments
**Story Points:** 5
**Business Value:** High
**Status:** Ready

---

### PB-010: Payment Recovery for Failed Charges
**User Story:** As a subscribed user whose payment failed, I want to be notified and given a grace period so that my learning streak isn't interrupted by a billing hiccup.
**Acceptance Criteria:**
- Given a Stripe webhook reports a failed charge, When the system processes it, Then the user receives an email with a payment update link
- Given a user's payment has failed, When they log in, Then they see a non-blocking banner asking them to update payment info
- Given 7 days pass without payment resolution, When the grace period expires, Then the user's access is downgraded to free tier (not deleted)
**Story Points:** 5
**Business Value:** High
**Status:** Ready

---

### PB-011: HSK Level Completion Celebration
**User Story:** As a learner who just mastered all HSK 1 vocabulary, I want a meaningful celebration moment so that I feel a sense of accomplishment and am motivated to continue.
**Acceptance Criteria:**
- Given a user achieves mastery_stage >= 4 on all HSK 1 items, When this threshold is crossed, Then a celebration screen appears with stats: time invested, accuracy trend, items mastered
- Given the celebration is shown, When the user dismisses it, Then the milestone is logged and the user sees the next HSK level's preview
- Given the user has already seen a celebration for a level, When they view it again in progress, Then they see a static "completed" badge, not the animation again
**Story Points:** 3
**Business Value:** Medium
**Status:** Ready

---

### PB-012: Passage Difficulty Calibration
**User Story:** As a learner reading graded passages, I want passage difficulty to match my current level so that I'm challenged but not overwhelmed.
**Acceptance Criteria:**
- Given a user's active HSK level is 3, When they open the reader, Then passages are filtered to HSK 2-3 range by default
- Given a user looks up more than 30% of words in a passage, When they finish, Then the system adjusts to show easier passages next time
- Given a user looks up fewer than 5% of words, When they finish, Then the system suggests a harder passage
**Story Points:** 5
**Business Value:** Medium
**Status:** Ready

---

### PB-013: Mobile App Store Submission (iOS)
**User Story:** As a potential user browsing the App Store, I want to find Aelu and install it so that I can learn Mandarin on my phone.
**Acceptance Criteria:**
- Given the Capacitor shell is built, When the app is submitted to App Store Connect, Then it passes Apple review on first submission
- Given the app is approved, When a user searches "mandarin learning" on the App Store, Then Aelu appears in results (ASO keywords set)
- Given a user installs the app, When they open it, Then the onboarding flow works identically to the web version
**Story Points:** 13
**Business Value:** High
**Status:** Ready

---

### PB-014: Offline Mode Polish
**User Story:** As a commuter without reliable internet, I want to complete a study session offline so that my practice isn't interrupted by connectivity gaps.
**Acceptance Criteria:**
- Given a user loses internet mid-session, When they continue, Then drills continue to function with locally cached content
- Given a user completes drills offline, When connectivity is restored, Then the offline-queue syncs automatically and progress appears on the server
- Given a sync conflict occurs, When the system resolves it, Then the user's local progress wins (optimistic merge)
**Story Points:** 5
**Business Value:** Medium
**Status:** Ready

---

### PB-015: Grade Appeal UX Improvement
**User Story:** As a learner who believes a drill was graded incorrectly, I want to appeal with one tap so that I don't lose momentum debating the system.
**Acceptance Criteria:**
- Given a drill result is shown, When the user taps "Appeal," Then the appeal is logged with the drill context, user answer, and expected answer
- Given an appeal is submitted, When the system processes it, Then the user sees a confirmation and the drill is removed from their error queue pending review
- Given I review appeals in the admin dashboard, When I view an appeal, Then I see full context: drill type, user answer, correct answer, and can approve/deny
**Story Points:** 3
**Business Value:** Medium
**Status:** Ready

---

### PB-016: Session Length Customization
**User Story:** As a busy learner, I want to choose between 5-minute, 10-minute, and 15-minute sessions so that I can fit practice into whatever time I have.
**Acceptance Criteria:**
- Given a user opens settings, When they select session length, Then options are 5, 10, and 15 minutes
- Given a user selects 5 minutes, When they start a session, Then the session contains approximately 5-7 drills (calibrated to average completion time)
- Given a user changes their preference mid-day, When they start the next session, Then the new length applies immediately
**Story Points:** 3
**Business Value:** Medium
**Status:** Ready

---

### PB-017: Drill Type Preference Learning
**User Story:** As a learner who enjoys tone drills but dislikes multiple choice, I want the system to gradually favor drill types I engage with more so that sessions feel less tedious.
**Acceptance Criteria:**
- Given a user consistently scores high on tone drills and low on MC drills, When the scheduler builds a session, Then tone drills appear slightly more often (within pedagogical bounds)
- Given the system adjusts drill mix, When it logs the adjustment, Then the personalization module records the rationale
- Given a user's preferences shift over time, When new data accumulates, Then the system adapts within 5 sessions
**Story Points:** 5
**Business Value:** Medium
**Status:** Ready

---

### PB-018: BUG - Stale WebSocket After Sleep
**User Story:** As a learner who puts my laptop to sleep mid-session, I want the session to recover gracefully when I wake the laptop so that I don't lose my drill state.
**Acceptance Criteria:**
- Given a WebSocket connection drops due to sleep, When the user wakes the device, Then the client detects the stale connection and reconnects within 5 seconds
- Given the reconnection succeeds, When the session resumes, Then the user sees their current drill (not a blank screen)
- Given the reconnection fails after 3 retries, When the user sees an error, Then they can tap "Restart Session" to begin a new session without losing previous progress
**Story Points:** 3
**Business Value:** Medium
**Status:** Ready

---

### PB-019: BUG - Audio Timing Overlap on Fast Drill Completion
**User Story:** As a learner who answers drills quickly, I want audio prompts to not overlap so that I can hear each one clearly.
**Acceptance Criteria:**
- Given a user submits an answer, When audio feedback plays, Then any previously playing audio is stopped first
- Given audio is playing, When the next drill loads, Then the new drill's audio waits until the previous audio completes or is cancelled
- Given the user is on a speaking drill, When they record, Then no system audio plays during recording
**Story Points:** 2
**Business Value:** Medium
**Status:** Ready

---

### PB-020: Landing Page A/B Test - Hero Copy
**User Story:** As the product owner, I want to test two versions of the landing page hero headline so that I can learn which message resonates with potential users.
**Acceptance Criteria:**
- Given a visitor lands on aelu.app, When the page loads, Then they are randomly assigned to variant A ("Master Mandarin at your own pace") or variant B ("The Mandarin learning system that adapts to you")
- Given a user is assigned a variant, When they return, Then they see the same variant (cookie-based)
- Given both variants have 200+ visitors, When I check the analytics, Then I see signup conversion rate per variant with statistical significance indicator
**Story Points:** 5
**Business Value:** High
**Status:** Ready

---

### PB-021: Classroom Teacher Dashboard Improvements
**User Story:** As a Mandarin teacher using Aelu's classroom features, I want to see per-student progress at a glance so that I can identify students who need help.
**Acceptance Criteria:**
- Given I am logged in as a teacher, When I view my classroom, Then I see a table of students with columns: name, sessions this week, items mastered, current HSK level, last active
- Given a student hasn't been active in 5 days, When I view the table, Then their row is highlighted in amber
- Given I click a student's name, When the detail view loads, Then I see their mastery breakdown by HSK level and recent drill accuracy
**Story Points:** 5
**Business Value:** Medium
**Status:** Ready

---

### PB-022: Content Expansion - HSK 4-5 Context Notes
**User Story:** As a learner studying HSK 4-5 vocabulary, I want context notes that explain nuance and usage so that I understand words beyond their dictionary definition.
**Acceptance Criteria:**
- Given an HSK 4-5 content item is displayed, When a context note exists, Then it appears below the definition with usage examples
- Given context notes are written, When they are reviewed, Then each note follows the chinese_writing_standard.md (no textbook smell, natural register)
- Given 200+ HSK 4-5 items exist, When all notes are written, Then at least 150 have context notes
**Story Points:** 13
**Business Value:** Medium
**Status:** Ready

---

### PB-023: Test Coverage Floor Enforcement
**User Story:** As the solo developer, I want the CI pipeline to fail if test coverage drops below the current floor so that I never accidentally ship undertested code.
**Acceptance Criteria:**
- Given the current coverage is X%, When a commit reduces coverage below X%, Then the test suite fails with a clear message showing which module lost coverage
- Given the coverage floor is met, When tests pass, Then the new floor is recorded in coverage_floors.py
- Given a new module is added, When it has 0% coverage, Then the overall check still catches the regression
**Story Points:** 3
**Business Value:** Medium
**Status:** Ready

---

### PB-024: Load Testing with Locust
**User Story:** As the solo developer, I want to know how many concurrent users the Fly.io deployment can handle so that I'm not surprised by a traffic spike.
**Acceptance Criteria:**
- Given a Locust test file exists, When I run it against staging, Then it simulates 50 concurrent users completing sessions
- Given the test runs for 5 minutes, When it completes, Then I see p50, p95, p99 response times and error rates
- Given response times exceed 500ms at p95, When the test flags this, Then I have a baseline for performance optimization
**Story Points:** 5
**Business Value:** Medium
**Status:** Ready

---

### PB-025: GDPR Data Export Performance
**User Story:** As a user who requests their data export, I want the export to complete within 30 seconds so that I'm not left waiting.
**Acceptance Criteria:**
- Given a user requests a data export, When the system generates it, Then the ZIP file is ready within 30 seconds for users with up to 10,000 review events
- Given the export is ready, When the user downloads it, Then it contains all tables: progress, sessions, review_events, feedback, settings
- Given a user has a large history (50,000+ events), When they request an export, Then the system queues it and emails a download link rather than timing out
**Story Points:** 3
**Business Value:** Low
**Status:** Ready

---

### PB-026: Dead Code Audit
**User Story:** As the solo developer, I want to identify and remove dead code so that the codebase stays maintainable and I don't waste time reading unused functions.
**Acceptance Criteria:**
- Given vulture or a similar tool runs against the codebase, When it reports unused functions/classes, Then each is verified as truly dead (not dynamically called)
- Given dead code is confirmed, When it is removed, Then all tests still pass
- Given the audit is complete, When the results are logged, Then the improvement_log records bytes removed and modules cleaned
**Story Points:** 3
**Business Value:** Low
**Status:** Ready

---

### PB-027: Dependency Update Sweep
**User Story:** As the solo developer, I want all Python dependencies to be on their latest compatible versions so that I don't accumulate security vulnerabilities.
**Acceptance Criteria:**
- Given pip-audit runs against requirements, When vulnerabilities are found, Then each is categorized as critical/high/medium/low
- Given a critical vulnerability exists, When it is found, Then it is patched within 24 hours
- Given all updates are applied, When the full test suite runs, Then it passes without new failures
**Story Points:** 3
**Business Value:** Low
**Status:** Ready

---

### PB-028: Admin Dashboard - Subscription Analytics
**User Story:** As the product owner, I want to see MRR, churn rate, and LTV estimates on the admin dashboard so that I can track business health weekly.
**Acceptance Criteria:**
- Given paying users exist, When I view the admin dashboard, Then I see current MRR (count of active subscriptions x $14.99)
- Given users have cancelled, When I view churn, Then I see monthly churn rate (cancellations / active at start of month)
- Given 3+ months of data exist, When I view LTV, Then I see estimated LTV (average revenue per user / churn rate)
**Story Points:** 5
**Business Value:** Medium
**Status:** Ready

---

### PB-029: Accessibility Audit (WCAG 2.1 AA)
**User Story:** As a user with visual impairments, I want Aelu to meet WCAG 2.1 AA standards so that I can use the app with a screen reader.
**Acceptance Criteria:**
- Given the web app is audited with axe-core, When violations are found, Then each is logged with severity and element
- Given critical violations exist (missing alt text, insufficient contrast, no ARIA labels), When they are fixed, Then a re-audit shows 0 critical violations
- Given the audit passes, When a screen reader (VoiceOver) is used, Then all drill interactions are navigable
**Story Points:** 8
**Business Value:** Low
**Status:** Ready

---

### PB-030: Automated Backup Verification
**User Story:** As the solo developer, I want weekly automated verification that database backups are restorable so that I know disaster recovery actually works.
**Acceptance Criteria:**
- Given a backup runs on Fly.io, When verification runs, Then a test restore to a temporary volume succeeds
- Given the restore succeeds, When a basic query runs against it, Then it returns the expected row count for the user table
- Given a restore fails, When the verification detects this, Then an alert is sent to Jason's email
**Story Points:** 3
**Business Value:** Low
**Status:** Ready

---

### PB-031: Social Proof on Landing Page
**User Story:** As a potential user visiting the landing page, I want to see testimonials or usage stats so that I feel confident the product is real and used by others.
**Acceptance Criteria:**
- Given the landing page loads, When testimonials are shown, Then at least 3 real user quotes are displayed (with permission)
- Given no testimonials exist yet, When the section renders, Then it shows aggregate stats instead ("X drills completed by learners this month")
- Given stats are displayed, When they update, Then they reflect real data from the past 30 days (not hardcoded)
**Story Points:** 3
**Business Value:** Medium
**Status:** Ready

---

### PB-032: Dialogue Scenario Expansion (HSK 3-5)
**User Story:** As an intermediate learner, I want dialogue scenarios that cover everyday situations at my level so that I can practice realistic conversations.
**Acceptance Criteria:**
- Given the current 30 dialogue scenarios exist, When 20 new scenarios are added for HSK 3-5, Then each follows the storytelling_standard.md
- Given new dialogues are added, When they are loaded, Then each has correct pinyin, translations, and grammar tagging
- Given a user is at HSK 4, When they access dialogues, Then they see scenarios appropriate to their level
**Story Points:** 13
**Business Value:** Medium
**Status:** Ready

---

### PB-033: Experiment: Spaced Repetition Interval Tuning
**User Story:** As the product owner, I want to test whether shorter initial SRS intervals (1h, 4h, 1d) improve next-day retention compared to the current schedule so that the core algorithm is evidence-based.
**Acceptance Criteria:**
- Given the experiment is enabled via feature_flag, When a user is assigned to the test group, Then their first three intervals are 1h, 4h, 1d (instead of the default)
- Given both groups have 20+ users with 7+ days of data, When I analyze retention rates, Then I can compare next-day recall accuracy between groups
- Given the experiment shows a statistically significant difference, When the decision is made, Then the winning schedule is rolled out to all users
**Story Points:** 8
**Business Value:** High
**Status:** Ready

---

## Backlog Health Metrics

| Metric | Current |
|---|---|
| Total items | 33 |
| Ready items | 33 |
| In Progress | 0 |
| Done | 0 |
| Total story points | 168 |
| High business value items | 14 |
| Medium business value items | 14 |
| Low business value items | 5 |
| Bugs | 2 |
| Tech debt | 4 |
| Experiments | 2 |
| Features | 25 |
