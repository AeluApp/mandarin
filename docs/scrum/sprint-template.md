# Aelu Sprint Template

Use this template for each 2-week sprint. Copy the template section and fill in the details.

---

## Template

```
# Sprint [NUMBER]
**Dates:** [START] - [END]
**Sprint Goal:** [One sentence, value-focused. What will be true at the end of this sprint that isn't true now?]

## Sprint Backlog

| ID | Item | Points | Status |
|---|---|---|---|
| PB-XXX | [Title] | X | Not Started / In Progress / Done |

**Total committed:** X points
**Capacity:** X available working days (minus holidays, appointments, admin)

## Daily Log

### Day 1 (Mon)
- What I did:
- Blockers:

### Day 2 (Tue)
- What I did:
- Blockers:

[...continue for each working day...]

## Sprint Review
**Date:** [END date]
**What was demoed:**
-

**Demoed to whom:**
-

**Feedback received:**
-

**Items completed:** X of Y

## Sprint Retrospective
**What went well:**
-

**What didn't go well:**
-

**Action items for next sprint:**
- [ ]

## Velocity
**Points committed:** X
**Points completed:** Y
**Completion rate:** Y/X = Z%
```

---

## Sprint 1 (Example)

**Dates:** 2026-03-10 - 2026-03-21
**Sprint Goal:** Validate that 5 non-Jason users can complete onboarding and first session without confusion.

## Sprint Backlog

| ID | Item | Points | Status |
|---|---|---|---|
| PB-001 | Guided First Session Experience | 5 | In Progress |
| PB-002 | Onboarding Completion Rate Tracking | 3 | Not Started |
| PB-005 | Session Completion Rate Improvement (progress bar) | 2 | Not Started |
| PB-006 | User Interview Recruitment Flow | 3 | Not Started |

**Total committed:** 13 points
**Capacity:** 8 available working days (10 weekdays minus 2 days for ops/admin/support)

## Daily Log

### Day 1 (Mon 3/10)
- What I did: Sprint planning. Reviewed all 4 items against Definition of Ready. Broke PB-001 into subtasks: (a) design warm-up drill sequence, (b) add inline explanation overlay component, (c) wire up resume-from-abandonment logic.
- Blockers: None.

### Day 2 (Tue 3/11)
- What I did: Implemented warm-up drill sequence (3 drills, fixed order: tone recognition, character-meaning match, pinyin typing). Added inline tooltip component.
- Blockers: None.

### Day 3 (Wed 3/12)
- What I did: Wrote 8 tests for warm-up flow. Fixed edge case where placement test completion was being counted as a warm-up. Started PB-002 lifecycle_event logging.
- Blockers: None.

### Day 4 (Thu 3/13)
- What I did: Completed PB-002 lifecycle event logging. Added onboarding funnel view to admin dashboard (5 steps, percentages, weekly cohorts).
- Blockers: None.

### Day 5 (Fri 3/14)
- What I did: Started PB-005 progress bar. Simple "X of Y" indicator in session view. Tested on web and iOS simulator.
- Blockers: Capacitor build took 20 minutes to troubleshoot — Xcode version mismatch.

### Day 6 (Mon 3/17)
- What I did: Completed PB-005. Wrote 3 tests for progress bar rendering. Started PB-006 — added feedback prompt component (shown after 10th session).
- Blockers: None.

### Day 7 (Tue 3/18)
- What I did: Completed PB-006 feedback form and admin view. Deployed all changes to production.
- Blockers: None.

### Day 8 (Wed 3/19)
- What I did: Recruited 5 test users (2 friends, 1 colleague, 2 from language learning subreddit). Sent them signup links. Monitored lifecycle_events for their onboarding progress.
- Blockers: 1 user reported confusion about placement test — unclear whether to guess or skip.

### Day 9 (Thu 3/20)
- What I did: Fixed placement test copy based on feedback ("It's okay to guess — this just helps us start at the right level"). Watched 2 users complete their first session over Zoom. Both completed without confusion. One user said "oh, this is calmer than Duolingo."
- Blockers: None.

### Day 10 (Fri 3/21)
- What I did: Sprint review and retrospective. All 5 users completed onboarding. 4 of 5 completed first session. 1 dropped off after placement (followed up — they ran out of time, not confused). Monitored crash_log — 0 new entries.
- Blockers: None.

## Sprint Review
**Date:** 2026-03-21
**What was demoed:**
- Guided first session with inline explanations
- Onboarding funnel in admin dashboard (showing 5/5 signup, 5/5 profile, 5/5 placement, 4/5 first session)
- Session progress bar
- Feedback recruitment prompt

**Demoed to whom:**
- Self-review (recorded Loom walkthrough for future reference)
- Showed onboarding funnel numbers to 1 advisor

**Feedback received:**
- Placement test copy was confusing (fixed mid-sprint)
- One user wanted to skip placement entirely (noted for backlog — PB-XXX)
- Advisor: "Good. Now get 20 more users through it."

**Items completed:** 4 of 4

## Sprint Retrospective
**What went well:**
- All items completed. Scope was realistic for 8 working days.
- Getting real users through the flow surfaced a real usability issue (placement test copy).
- Lifecycle event tracking immediately provided actionable data.

**What didn't go well:**
- Capacitor build issues cost ~1 hour. Need a documented build checklist.
- Recruiting test users took more time than expected (3 hours of DMs and emails for 5 users).

**Action items for next sprint:**
- [ ] Create a Capacitor build checklist to avoid Xcode version surprises
- [ ] Set up a standing "test user" recruitment channel (subreddit post, language exchange Discord)
- [ ] Add "skip placement" option to backlog

## Velocity
**Points committed:** 13
**Points completed:** 13
**Completion rate:** 100%
