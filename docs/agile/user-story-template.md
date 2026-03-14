# Aelu User Story Template

**Last Updated:** 2026-03-10

---

## User Story Format

```
As a [persona],
I want [action/capability],
so that [benefit/outcome].
```

Every user story must have all three clauses. "As a user, I want a button" is not a story -- it has no benefit. "I want faster loading" is not a story -- it has no persona.

---

## Aelu Personas

| Persona | Description | Key Concerns |
|---|---|---|
| **Learner** | Someone actively studying Mandarin with Aelu | Session quality, drill relevance, progress visibility, SRS accuracy |
| **New user** | Someone who just signed up, hasn't completed onboarding | Clarity, low-stakes introduction, not feeling overwhelmed |
| **Teacher** | A Mandarin teacher using classroom features | Per-student visibility, assignment control, progress reports |
| **Admin (Jason)** | Product owner reviewing analytics and system health | Conversion rates, churn signals, crash_log, revenue metrics |
| **Solo developer (Jason)** | Engineer maintaining the codebase | Test coverage, deploy reliability, tech debt, security posture |

---

## INVEST Criteria Checklist

Every user story must pass all six INVEST criteria before it is considered ready.

| Criterion | Question | Fail Example | Pass Example |
|---|---|---|---|
| **I**ndependent | Can this be built and deployed without waiting for another story? | "Build the email system" (needs SMTP config story first) | "Log lifecycle_event when user completes onboarding" (self-contained) |
| **N**egotiable | Can the scope be adjusted without losing the core value? | "Implement exact Duolingo-style streaks" (locked to specific implementation) | "Show learner their practice consistency" (allows design flexibility) |
| **V**aluable | Does completing this story deliver value to the persona? | "Refactor scheduler.py into smaller functions" (developer benefit, not user value -- reframe as tech debt) | "Learner receives drills calibrated to their weakest tone pairs" |
| **E**stimable | Can you estimate this in story points? | "Make the app better" (too vague to estimate) | "Add progress bar to session view showing X of Y drills complete" |
| **S**mall | Can this be completed within a single sprint? | "Build the entire classroom feature" (multi-sprint epic) | "Teacher can view per-student session count and last-active date" |
| **T**estable | Can you write acceptance criteria with Given/When/Then? | "The app should feel smooth" (untestable) | "Given a session is in progress, When drill 5 of 8 completes, Then the progress bar shows 5/8" |

---

## Acceptance Criteria Format

Use Given/When/Then (Gherkin) for every acceptance criterion.

```
Given [precondition / initial state],
When [action / trigger],
Then [expected outcome / observable result].
```

### Rules for Acceptance Criteria

- **Minimum 2 per story, maximum 7.** Fewer than 2 means the story is under-specified. More than 7 means it should be split.
- **Each criterion must be independently testable.** You should be able to write a single pytest function for each.
- **No ambiguous adjectives.** Replace "fast" with "under 500ms." Replace "easy" with "completable in under 3 taps." Replace "intuitive" with a specific flow description.
- **Include at least one edge case.** What happens when the data is empty? When the user has no sessions? When the network drops?

---

## Story Splitting Techniques

When a story is too large (estimated at 13+ points or can't be completed in a sprint), split it using one of these techniques.

### 1. Split by Workflow Step

Original: "As a learner, I want to complete a full reading session with lookup tracking and difficulty adjustment."

Split:
- "As a learner, I want to read a graded passage filtered to my HSK level." (3 pts)
- "As a learner, I want to look up unknown words and have lookups recorded in `vocab_encounter`." (3 pts)
- "As a learner, I want passage difficulty to adjust based on my lookup rate." (5 pts)

### 2. Split by Business Rule

Original: "As the admin, I want churn prediction alerts for at-risk users."

Split:
- "As the admin, I want users flagged as at-risk when they haven't logged in for 7 days." (3 pts)
- "As the admin, I want users flagged when session frequency drops 50% week-over-week." (5 pts)
- "As the admin, I want at-risk users visible on the admin dashboard with usage history." (3 pts)

### 3. Split by Data Variation

Original: "As a learner, I want context notes for all vocabulary items."

Split:
- "As a learner, I want context notes for HSK 1-3 items (299 items, existing)." (Done)
- "As a learner, I want context notes for HSK 4-5 items (PB-022)." (13 pts -- split further by HSK level)
- "As a learner, I want context notes for HSK 6-9 items." (Future backlog)

### 4. Split by Interface

Original: "As a learner, I want offline mode so I can study without internet."

Split:
- "As a learner using the web app, I want drills cached in localStorage for offline use." (5 pts)
- "As a learner using the iOS app, I want Capacitor offline queue to sync when connectivity returns." (5 pts)
- "As a learner using the macOS app, I want the same offline behavior as the web app." (3 pts -- shares implementation)

---

## Real Aelu Examples

### Example 1: Learner Story (Drill)

```
As a learner studying tone pairs,
I want the speaking drill to play audio of the target word before I record my attempt,
so that I have a clear pronunciation model to imitate.

Acceptance Criteria:
1. Given the user is on a speaking drill, When the drill loads, Then macOS TTS plays
   the target hanzi with correct tones before the record button activates.
2. Given TTS playback is complete, When the record button becomes active, Then a
   visual indicator shows the user they can now speak.
3. Given the user is on a speaking drill, When previous drill audio is still playing,
   Then the previous audio is cancelled before the new drill's TTS begins.

Story Points: 3
```

### Example 2: Learner Story (SRS)

```
As a learner reviewing vocabulary,
I want items I looked up during reading practice to appear sooner in my SRS reviews,
so that exposure during reading reinforces long-term retention.

Acceptance Criteria:
1. Given a user looks up a word in the graded reader, When the vocab_encounter is
   logged with looked_up=1, Then the scheduler boosts that item's priority for the
   next session.
2. Given a boosted item is reviewed, When the user answers correctly, Then the boost
   is consumed and the item returns to its normal SRS interval.
3. Given a user looks up the same word 3+ times across different reading sessions,
   When the cleanup loop runs, Then the item is flagged for focused review (not just
   boosted, but added to a dedicated review set).

Story Points: 5
```

### Example 3: Teacher Story (Classroom)

```
As a teacher managing a classroom of 15 students,
I want to see which students haven't completed a session in the last 5 days,
so that I can reach out to them before they fall behind.

Acceptance Criteria:
1. Given I am logged in as a teacher, When I view my classroom dashboard, Then I see
   a table with columns: student name, sessions this week, items mastered, current
   HSK level, last active date.
2. Given a student's last_active date is more than 5 days ago, When I view the table,
   Then their row is highlighted in amber.
3. Given I click a student's name, When the detail view loads, Then I see their
   mastery breakdown by HSK level, recent drill accuracy, and a timeline of session
   activity.

Story Points: 5
```

### Example 4: Admin Story (Analytics)

```
As the product owner,
I want to see monthly Net Promoter Score trends on the admin dashboard,
so that I can track whether product changes improve user satisfaction over time.

Acceptance Criteria:
1. Given a user completes their 10th session, When the session ends, Then an NPS
   prompt (0-10 scale) appears once, dismissable, not shown again for 90 days.
2. Given a user selects 0-6 (detractor), When they submit, Then a text box asks
   "What would need to change?" and the response is stored in the nps_response table.
3. Given NPS data exists for 3+ months, When I view the admin dashboard, Then I see
   monthly NPS score, trend line, and verbatim comments grouped by
   detractor/passive/promoter.

Story Points: 5
```

### Example 5: Developer Story (Infrastructure)

```
As the solo developer,
I want the CI pipeline to fail if test coverage drops below the current floor,
so that I never accidentally ship undertested code to production.

Acceptance Criteria:
1. Given the current coverage is X%, When a commit reduces coverage below X%, Then
   the pytest run fails with a message identifying which module lost coverage.
2. Given the coverage floor is met, When the test job passes, Then
   scripts/coverage_floors.py records the new floor per module.
3. Given a new module is added with 0% coverage, When the coverage check runs, Then
   the overall check catches the regression (new modules are not excluded by default).

Story Points: 3
```

---

## Story Writing Anti-Patterns

**The Solution Story:** "As a developer, I want to add a column to the user table." This describes implementation, not value. Rewrite: "As a learner, I want my session preferences saved so that I don't have to reconfigure every time."

**The Persona-less Story:** "I want the app to load faster." Who wants this? A learner on mobile? A teacher with 30 students? The persona determines the acceptance criteria.

**The Kitchen Sink:** A story with 12 acceptance criteria touching 8 modules. Split it.

**The Vague Benefit:** "...so that the experience is better." Better how? For whom? Measurably? If you can't test the benefit, you can't verify the story is done.

**The Technical Task Disguised as a Story:** "As a developer, I want to refactor the scheduler." This is tech debt, not a user story. Track it in the tech debt budget, not as a story. If it must be a story, connect it to user value: "As a learner, I want consistent drill scheduling so that my review intervals are reliable" (and the implementation happens to require a refactor).
