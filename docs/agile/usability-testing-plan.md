# Aelu Usability Testing Plan

**Last Updated:** 2026-03-10
**Frequency:** Quarterly (every 3 months), or after any major UX change
**Participants per round:** 5 (the Nielsen threshold — 5 users find ~85% of usability problems)

---

## Objectives

1. Measure whether new users can complete core tasks without guidance
2. Identify specific interaction points where users get confused, stuck, or frustrated
3. Track usability improvements over time via SUS scores and task completion rates
4. Generate concrete, prioritized fixes for the product backlog

---

## Participant Recruitment

### Target Profile
- Age 18-55
- Currently studying or interested in studying Mandarin
- Owns a smartphone and/or laptop
- Has NOT used Aelu before (for fresh onboarding data)
- Mix of: complete beginners (2), HSK 1-2 (2), HSK 3+ (1)

### Exclusion Criteria
- UX designers or developers (too much domain knowledge about app conventions)
- People who have seen Aelu's marketing materials or received a demo
- Non-English speakers (test instructions are in English)

### Recruitment Sources
- Reddit language learning communities (post offering $25 gift card for 45-minute session)
- University Mandarin classes (ask professors to share with students)
- Personal network (friends-of-friends who are learning Mandarin, NOT friends who will be polite)

### Compensation
$25 Amazon gift card per session. Paid regardless of whether they complete all tasks.

---

## Test Environment

- **Web:** Fresh browser profile (no cookies, no saved passwords). URL: production aelu.app or staging.
- **Mobile (iOS):** TestFlight build on participant's device, or screen-share of iOS simulator.
- **Account:** Provide a fresh test account for each participant. Do not reuse accounts.
- **Recording:** Zoom with screen share. Record the session (with consent). Enable transcription.

---

## Tasks

### Task 1: Create Account and Complete Onboarding
**Instructions to participant:** "Imagine a friend recommended this app for learning Mandarin. Go to the website, create an account, and set everything up until you reach the main screen."

**Success criteria:**
- Account created with email and password
- Learner profile completed (name, level selection or placement)
- Placement test completed (or skipped, if that option exists)
- Dashboard/main screen visible

**Time limit:** 3 minutes

**Failure modes to watch for:**
- Confusion about what information is required vs. optional
- Placement test: Do they understand the purpose? Do they guess or skip?
- Password requirements: Do they fail validation and get frustrated?
- Email verification: Does the flow break if they don't verify immediately?

**Severity if failed:** Critical. If users can't onboard, nothing else matters.

---

### Task 2: Start and Complete a Study Session
**Instructions to participant:** "Now try doing a study session. Just go through it as you naturally would."

**Success criteria:**
- User finds and clicks "Start Session" (or equivalent)
- User completes at least 5 drills
- User reaches the session complete screen
- Session is logged in session_log

**Time limit:** 10 minutes

**Failure modes to watch for:**
- Can't find the start button (buried in navigation, unclear labeling)
- Confused by a drill type (doesn't understand what's being asked)
- Submits wrong answer format (types pinyin without tones, or tones without pinyin)
- Audio doesn't play (browser permission, volume, or timing issue)
- Gets stuck between drills (WebSocket stall, loading spinner that never resolves)
- Abandons mid-session (note which drill they abandoned on and why)

**Severity if failed:** Critical. The study session IS the product.

---

### Task 3: Find Progress for a Specific HSK Level
**Instructions to participant:** "Can you find out how you're doing with HSK 2 vocabulary? I want to see what percentage you've mastered."

**Success criteria:**
- User navigates to progress/report view
- User identifies HSK 2 specifically (not just overall progress)
- User can state their mastery percentage or item count

**Time limit:** 1 minute

**Failure modes to watch for:**
- Can't find the progress section (unclear navigation)
- Progress view exists but doesn't break down by HSK level
- Data is shown but in a format the user can't interpret (e.g., raw numbers without context)
- User confuses "items seen" with "items mastered"

**Severity if failed:** Medium. Progress visibility drives motivation but isn't blocking core usage.

---

### Task 4: Look Up a Word During Reading
**Instructions to participant:** "Go to the reading section and read a passage. If you see a word you don't know, try to look it up."

**Success criteria:**
- User finds the reading section
- User opens a passage
- User taps/clicks on a word and sees its definition
- The looked-up word is logged in vocab_encounter

**Time limit:** 5 minutes

**Failure modes to watch for:**
- Can't find the reading section (navigation issue)
- No passages available at their level
- Tap/click target is too small or not obvious (user doesn't realize words are tappable)
- Lookup popup is too small, obscured, or disappears too quickly
- Word is looked up but encounter is not logged (backend bug)

**Severity if failed:** Medium. Reading is a secondary feature but vocab encounter logging feeds the cleanup loop.

---

### Task 5: Change a Setting
**Instructions to participant:** "Can you change how long your study sessions are? Maybe make them shorter or longer."

**Success criteria:**
- User navigates to settings
- User finds the session length option
- User changes the value
- Change is persisted (visible on reload)

**Time limit:** 1 minute

**Failure modes to watch for:**
- Settings page is hard to find (buried, no gear icon, unclear label)
- Session length option doesn't exist or is labeled ambiguously
- Change appears to save but doesn't persist
- No confirmation that the change was saved

**Severity if failed:** Low. Settings are important but infrequently used.

---

## Post-Test Questionnaire

### System Usability Scale (SUS)
Administer immediately after the last task. Read each statement and ask the participant to rate 1 (Strongly Disagree) to 5 (Strongly Agree).

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

**SUS Scoring:**
- For odd items (1,3,5,7,9): score = response - 1
- For even items (2,4,6,8,10): score = 5 - response
- Sum all scores, multiply by 2.5
- Result is 0-100. Target: 75+

### Open-Ended Questions
11. What was the most confusing part of using Aelu?
12. What did you like most?
13. Is there anything you expected to find but didn't?
14. Would you use this app to study Mandarin? Why or why not?
15. Any other thoughts?

---

## Analysis and Reporting

### Per-Round Report Template

**Round:** [number]
**Date:** [date]
**Participants:** [count]

#### Task Completion Matrix

| Participant | Task 1 (Onboard) | Task 2 (Session) | Task 3 (Progress) | Task 4 (Lookup) | Task 5 (Setting) |
|---|---|---|---|---|---|
| P1 | Pass / Fail / Partial | ... | ... | ... | ... |
| P2 | ... | ... | ... | ... | ... |
| P3 | ... | ... | ... | ... | ... |
| P4 | ... | ... | ... | ... | ... |
| P5 | ... | ... | ... | ... | ... |
| **Completion %** | X% | X% | X% | X% | X% |

#### Time on Task (seconds)

| Participant | Task 1 | Task 2 | Task 3 | Task 4 | Task 5 |
|---|---|---|---|---|---|
| P1 | | | | | |
| P2 | | | | | |
| P3 | | | | | |
| P4 | | | | | |
| P5 | | | | | |
| **Median** | | | | | |

#### SUS Scores

| Participant | SUS Score |
|---|---|
| P1 | |
| P2 | |
| P3 | |
| P4 | |
| P5 | |
| **Average** | |

#### Top Usability Issues (ranked by severity)

| # | Issue | Tasks Affected | Participants Hit | Severity | Backlog Item |
|---|---|---|---|---|---|
| 1 | | | | Critical/Major/Minor | PB-XXX |
| 2 | | | | | |
| 3 | | | | | |

#### SUS Trend (across rounds)

| Round | Date | Average SUS | Target |
|---|---|---|---|
| 1 | | | 75 |
| 2 | | | 75 |
| 3 | | | 75 |

---

## Schedule

| Quarter | Dates | Focus Area |
|---|---|---|
| Q2 2026 | April | Baseline: first round with 5 external users |
| Q3 2026 | July | Post-onboarding improvements |
| Q4 2026 | October | Mobile app usability (Capacitor build) |
| Q1 2027 | January | Advanced features (reading, listening, dialogues) |
