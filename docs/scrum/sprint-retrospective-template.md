# Aelu Sprint Retrospective Template

**Last Updated:** 2026-03-10

Use this template at the end of every 2-week sprint. Time-box: 45 minutes for a solo developer, 90 minutes for a team.

---

## Pre-Retro: Safety Check

Before discussing anything, rate how safe you feel being honest about this sprint. For solo development this is a self-honesty check -- are you willing to look at what actually happened, or are you rationalizing?

| Score | Meaning |
|---|---|
| 1 | I'm avoiding looking at this sprint's data entirely |
| 2 | I'll note what went wrong but won't change anything |
| 3 | I'll acknowledge problems and consider changes |
| 4 | I'll commit to at least one concrete change |
| 5 | I'm genuinely curious about what the data says, even if it's uncomfortable |

**If your score is 1 or 2:** Stop. Take a walk. Come back when you're at least a 3. A retrospective where you won't act on findings is worse than no retrospective -- it builds a habit of ignoring signals.

---

## Sprint Timeline

Fill in actual events from the sprint. This grounds the retro in facts rather than feelings.

| Day | Date | Key Events | Notes |
|---|---|---|---|
| 1 | | Sprint planning completed | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
| 8 | | | |
| 9 | | | |
| 10 | | Sprint review, retrospective | |

**Unplanned work this sprint:**
- Production incidents:
- Urgent bug fixes:
- Support requests:
- Hours spent on unplanned work: ___

---

## 4Ls Framework

### Liked
What went well? What do you want to keep doing?

- [ ] _Example: SRS scheduler changes were well-tested before deploy -- zero crash_log entries._
- [ ]
- [ ]
- [ ]

### Learned
What new knowledge or insight did you gain?

- [ ] _Example: Discovered that SQLite Row LEFT JOIN fields return None, not missing keys -- need `x.get("field") or 0` pattern everywhere._
- [ ]
- [ ]
- [ ]

### Lacked
What was missing that would have helped?

- [ ] _Example: No integration test for the vocab_encounter cleanup loop -- had to debug manually in production._
- [ ]
- [ ]
- [ ]

### Longed For
What do you wish existed but doesn't yet?

- [ ] _Example: Automated Capacitor build + iOS simulator smoke test in CI so I stop losing time to Xcode version mismatches._
- [ ]
- [ ]
- [ ]

---

## Dot Voting (Prioritization)

From all 4L items above, pick the top 3 issues that would have the highest impact if addressed. For solo development, this replaces team dot voting -- the discipline is forcing yourself to pick only 3.

| Rank | Item (from 4Ls) | Category | Estimated Effort to Address |
|---|---|---|---|
| 1 | | Liked / Learned / Lacked / Longed For | |
| 2 | | Liked / Learned / Lacked / Longed For | |
| 3 | | Liked / Learned / Lacked / Longed For | |

---

## Metrics Review

Pull these numbers for every retro. Trends matter more than absolutes.

| Metric | This Sprint | Last Sprint | Trend |
|---|---|---|---|
| Points committed | | | |
| Points completed | | | |
| Completion rate | | | |
| Unplanned work (hours) | | | |
| Production incidents | | | |
| New crash_log entries | | | |
| Test count (pytest) | | | |
| Coverage % | | | |
| Bandit HIGH findings | | | |
| Deploy count | | | |

**Data sources:**
- Points: `docs/scrum/velocity-tracker.md`
- Crash log: `SELECT count(*) FROM crash_log WHERE created_at > datetime('now', '-14 days')`
- Tests: `pytest --co -q | tail -1`
- Coverage: `pytest --cov=mandarin --cov-report=term-missing | grep TOTAL`
- Bandit: `bandit -r mandarin/ -ll -q`

---

## Action Items

Every retro must produce at least 1 and at most 3 action items. Each must have an owner, a deadline, and a verification method.

| # | Action Item | Owner | Deadline | How to Verify Done |
|---|---|---|---|---|
| 1 | | Jason | Sprint N+1, Day X | |
| 2 | | Jason | Sprint N+1, Day X | |
| 3 | | Jason | Sprint N+1, Day X | |

**Carryover check:** Were last sprint's action items completed?

| Last Sprint's Action Item | Status | If Not Done, Why? |
|---|---|---|
| | Done / Not Done | |
| | Done / Not Done | |

If the same action item carries over for 3 consecutive sprints, it is either not important (remove it) or not actionable (rewrite it with a smaller scope).

---

## Aelu-Specific Retro Prompts

Use these when the generic 4Ls feel stale. Pick 1-2 per retro.

1. **SRS/Algorithm:** Did any scheduler or drill logic changes produce unexpected results in `session_trace.jsonl`? Did learner metrics (mastery_stage progression, accuracy) move in the expected direction?

2. **Content Quality:** Did any new context notes, grammar points, or dialogue scenarios get flagged by users or fail the `chinese_writing_standard.md` bar? Was there textbook smell?

3. **Platform Parity:** Did a change work on web but break on iOS (Capacitor) or macOS? Are all three platforms tested before deploy?

4. **Security Posture:** Did the security workflow (bandit, gitleaks, pip-audit) catch anything real? Were there any near-misses with secrets or credentials?

5. **Tech Debt Budget:** Was the 20% tech debt allocation honored? What tech debt was addressed? What was deferred and why?

6. **MEMORY.md Accuracy:** Is the project memory still accurate? Are there stale entries that should be updated or removed?

---

## Retro Anti-Patterns to Avoid

**The Blame Game:** Even solo, blaming tools ("SQLite is the problem") instead of identifying what you can change ("I need a pre-commit check for SQLite datetime consistency") is unproductive.

**The Wish List:** Listing 15 things you want without prioritizing is the same as listing zero. Force-rank to 3 action items.

**The Happy Path:** Only noting what went well. If every retro says "everything was great," you're not looking hard enough. Check `drill_errors.log` and `session_trace.jsonl` -- the data will be honest even when you aren't.

**The Amnesia Retro:** Not reviewing last sprint's action items. If you don't check carryover, action items are performative. They must be verified.

**The Scope Creep Retro:** Turning action items into full features ("build a CI/CD dashboard"). Action items should be achievable within a single sprint -- preferably within a day.

**The Never-ending Retro:** Going past 45 minutes solo. Diminishing returns set in fast. If you haven't identified 3 action items in 45 minutes, the problem isn't time -- it's clarity. Stop, sleep on it, revisit tomorrow for 15 minutes.

**The Feelings-Only Retro:** "I felt frustrated" without connecting it to data. Why were you frustrated? Was it because 3 of 8 items carried over? Was it because a production bug took 4 hours to diagnose? Ground feelings in facts.
