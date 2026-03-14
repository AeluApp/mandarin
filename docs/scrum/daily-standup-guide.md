# Aelu Daily Standup Guide

**Last Updated:** 2026-03-10

---

## Purpose

The daily standup synchronizes work, surfaces impediments early, and maintains sprint momentum. For a solo developer, this is a structured self-check that prevents drift -- catching problems on Day 2 instead of discovering them at sprint review on Day 10.

---

## Format: Three Questions

Every standup answers exactly three questions. Nothing more.

### 1. What did I complete since the last standup?

Completed means done-done -- tests written, code reviewed (by Claude Code or self-review), and ready for deploy. Not "worked on" or "made progress." Name the specific task or sub-task from the sprint backlog.

**Good:** "Completed PB-012 task 3: lookup_rate threshold logic with 4 unit tests passing."
**Bad:** "Worked on the reader feature." (Which part? What's the state?)

### 2. What will I work on next?

Name the specific task from the sprint backlog. If you're switching items, say why (blocked, need a break from context, etc.).

**Good:** "Starting PB-012 task 5: integration test for passage filtering with test_client."
**Bad:** "More reader stuff." (Unactionable)

### 3. Is anything blocking me?

An impediment is something you cannot resolve alone within 30 minutes. See the impediment definition section below.

**Good:** "Blocked on PB-004: need SMTP credentials for email drip testing. Waiting on Fly.io secret configuration."
**Bad:** "Things are going slow." (Not an impediment, just a feeling)

---

## What Constitutes an Impediment vs. a Task

This distinction matters. Impediments get escalated. Tasks get worked.

### Impediments (require action outside normal work)

| Category | Example | Escalation |
|---|---|---|
| External dependency | Apple review rejected the Capacitor build; need to fix and resubmit | Log in sprint notes, adjust sprint scope |
| Environment failure | Fly.io deploy fails due to platform issue | Check Fly.io status page, file support ticket |
| Missing access | Need Stripe test API key to implement PB-010 payment recovery | Configure in Fly.io secrets, then unblock |
| Architectural uncertainty | Unsure if `scheduler.py` locking mechanism handles concurrent sessions | Time-box a 2-hour spike, log findings |
| Broken CI | GitHub Actions workflow fails on a dependency that was working yesterday | Fix immediately -- broken CI blocks all deploys |
| Data dependency | Need 30+ real users through onboarding funnel to validate PB-002, but only have 5 | Recruit more test users, adjust sprint goal if needed |

### Not Impediments (just work that takes effort)

| Situation | Why It's Not an Impediment | What to Do |
|---|---|---|
| "This is harder than I estimated" | Difficulty is expected; re-estimate if needed | Continue working, note for retro |
| "I don't know how to implement this" | That's a task (research/spike), not a block | Time-box investigation, read code, ask Claude Code |
| "The test is failing" | Failing tests are the work, not a block | Debug it |
| "I'm tired / unmotivated" | Personal state, not a project impediment | Take a break, come back fresh |
| "SQLite can't ALTER CHECK constraints" | Known constraint, documented workaround exists | Use the table recreation pattern from MEMORY.md |

---

## Impediment Escalation Path

For a solo developer, "escalation" means structured problem-solving, not handing it to someone else.

```
1. Can I resolve this in < 30 minutes?
   YES -> It's a task, not an impediment. Do it.
   NO  -> Continue to step 2.

2. Is this blocking the current sprint goal?
   NO  -> Park it. Work on something else. Log it for retro.
   YES -> Continue to step 3.

3. Can I work around it?
   YES -> Implement the workaround. Log the tech debt for later.
   NO  -> Continue to step 4.

4. Time-box: spend 2 hours investigating.
   RESOLVED -> Continue sprint.
   NOT RESOLVED -> Adjust sprint scope. Remove the blocked item.
                   Log the impediment and root cause in sprint notes.
```

---

## Parking Lot

Topics that come up during standup but don't answer the three questions go in the parking lot. Review the parking lot at the end of the day (not during standup).

### Parking Lot Template

| Date | Topic | Follow-up Action | Resolved? |
|---|---|---|---|
| | | | |

**Common parking lot items for Aelu:**
- "Should the reading passage filter include HSK level N-1 or just N?" (Design decision -- schedule 15 min to decide)
- "The `vocab_encounter` cleanup loop might need a batch size limit." (Potential optimization -- add to tech debt backlog)
- "CSP headers might need updating for the new font CDN." (Security consideration -- check before deploy)

---

## Async Standup: Daily Log Template

For days when a formal standup isn't practical (deep focus day, travel, or simply preferring async), use this markdown template. Write it at the end of each working day.

### Template

Copy this into the sprint's daily log section:

```markdown
### Day X (Weekday MM/DD)

**Completed:**
- [ ] [Task with PB-XXX reference]
- [ ] [Task with PB-XXX reference]

**Next:**
- [ ] [Task with PB-XXX reference]

**Blockers:**
- None / [Description + escalation step taken]

**Unplanned work:**
- None / [Description + time spent]

**Notes:**
- [Anything relevant: debugging insight, user feedback, architecture decision]
```

### Example: Real Aelu Standup Log

```markdown
### Day 3 (Wed 3/12)

**Completed:**
- [x] PB-002 task 1: Added lifecycle_event logging to auth.py (signup, profile_complete, placement_complete, first_session, second_session)
- [x] PB-002 task 2: Admin route for onboarding funnel view with weekly cohort breakdown
- [x] 8 tests for lifecycle event logging (test_auth.py)

**Next:**
- [ ] PB-005 task 1: Session progress bar component in web/templates/session.html
- [ ] PB-005 task 2: WebSocket message for drill count update

**Blockers:**
- None

**Unplanned work:**
- drill_errors.log showed a KeyError in tone_grading.py for items without pinyin. Fixed with `item.get("pinyin") or ""` pattern. 25 minutes.

**Notes:**
- lifecycle_event table uses datetime('now') for UTC timestamps. Confirmed Python code uses datetime.now(timezone.utc) to match.
- Funnel query uses LEFT JOIN on session table -- remember to handle None with `row.get("count") or 0`.
```

---

## Standup Timing

| Context | When | Duration |
|---|---|---|
| Solo developer, in flow | End of day (async log) | 5 minutes to write |
| Solo developer, sprint start | Start of day (sync self-check) | 5 minutes |
| With collaborator (e.g., Claude Code session) | Start of session | 2 minutes verbal |

The standup is never longer than 5 minutes. If it takes longer, you're problem-solving during standup -- stop and move it to the parking lot.

---

## Weekly Pulse Check

Every Friday, in addition to the daily log, answer these four questions:

1. **Sprint goal progress:** On a scale of 1-5, how confident am I that the sprint goal will be met? If < 3, what needs to change?
2. **Velocity pace:** How many points are completed vs. committed? Am I on track, ahead, or behind?
3. **Unplanned work load:** How many hours went to unplanned work this week? Is it within the budgeted buffer?
4. **Energy level:** Am I maintaining sustainable pace, or am I grinding? (Burnout produces bad code and bad estimates.)

```markdown
### Friday Pulse (Week X of Sprint Y)

- Sprint goal confidence: X/5
- Points completed / committed: X / Y
- Unplanned work this week: X hours
- Sustainable pace: Yes / Warning / No
```
