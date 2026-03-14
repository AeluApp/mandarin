# Aelu Acceptance Criteria Standards

**Last Updated:** 2026-03-10

---

## Format: Given/When/Then (Gherkin)

Every acceptance criterion follows the Given/When/Then structure. No exceptions.

```
Given [a precondition or initial state],
When [an action is performed or an event occurs],
Then [an observable, testable outcome].
```

### Why This Format

- **Given** establishes context -- what must be true before the test runs. This maps to test setup (`setUp`, fixtures, `conftest.py`).
- **When** describes the trigger -- the user action or system event. This maps to the function call or HTTP request.
- **Then** describes the assertion -- what must be true after. This maps directly to `assert` statements in pytest.

If you can't translate a criterion directly into a pytest function, the criterion is too vague.

---

## How Many Scenarios Per Story

| Story Points | Minimum Scenarios | Maximum Scenarios |
|---|---|---|
| 1-2 | 2 | 3 |
| 3-5 | 3 | 5 |
| 8 | 4 | 7 |
| 13 | 5 | 7 (split the story if you need more) |

**Fewer than the minimum** means the story is under-specified. You will discover missing requirements during implementation.

**More than the maximum** means the story is too large. Split it into smaller stories, each with their own criteria.

---

## What Every Set of Criteria Must Cover

### 1. Happy Path (Required)
The main success scenario. The user does the expected thing and gets the expected result.

### 2. Edge Case (Required)
At least one scenario covering unusual but valid input: empty data, boundary values, None/null fields, first-time vs. returning user.

### 3. Error/Failure Path (Required for 3+ point stories)
What happens when something goes wrong: network failure, invalid input, missing permissions, database constraint violation.

### 4. Performance Criterion (Required for user-facing features)
Measurable performance expectation: response time, page load time, query execution time. Use concrete numbers, not "fast" or "responsive."

### 5. Security Criterion (Required for auth/data features)
For any feature touching `jwt_auth.py`, `auth.py`, `mfa.py`, `payment.py`, `data_retention.py`, or `security.py`: include a criterion verifying that unauthorized access is rejected.

---

## Criterion Quality Checklist

Before accepting a criterion, verify:

- [ ] **Testable:** Can you write a single pytest function for this criterion?
- [ ] **Specific:** No ambiguous adjectives (fast, easy, intuitive, nice, smooth)
- [ ] **Independent:** This criterion can be verified without relying on another criterion's outcome
- [ ] **Atomic:** This criterion tests one thing, not two things joined by "and"
- [ ] **Observable:** The "Then" clause describes something you can see, measure, or query -- not an internal implementation detail

### Common Failures

| Bad Criterion | Problem | Better Version |
|---|---|---|
| "Then the page loads quickly" | "Quickly" is unmeasurable | "Then the page loads in under 500ms (p95)" |
| "Then the user sees a nice UI" | "Nice" is subjective | "Then the progress bar shows X/Y format with current drill highlighted" |
| "Then the data is saved correctly" | "Correctly" is vague | "Then the `review_event` table contains a row with item_id, user_id, score, and reviewed_at within 1 second of submission" |
| "Then everything works on mobile" | "Everything" is untestable | "Then the session view renders without horizontal scroll on 375px viewport width" |
| "Then the algorithm improves" | No measurable definition of "improves" | "Then next-day recall accuracy for the test group exceeds the control group by >= 5 percentage points" |

---

## Real Aelu Examples

### Example 1: Drill Completion Flow

**Story:** As a learner, I want to see my drill result immediately after answering so that I can learn from my mistakes.

```
Scenario 1: Correct answer on character-meaning drill
Given a learner is in an active session with a character-meaning drill,
When they select the correct meaning from 4 options,
Then the interface shows a green "correct" indicator within 200ms,
  and the correct answer is highlighted,
  and a review_event row is inserted with score=1.

Scenario 2: Incorrect answer on character-meaning drill
Given a learner is in an active session with a character-meaning drill,
When they select an incorrect meaning,
Then the interface shows a red "incorrect" indicator within 200ms,
  and both the selected (wrong) answer and the correct answer are highlighted,
  and a review_event row is inserted with score=0,
  and the item's next_review date is recalculated to a shorter interval.

Scenario 3: Timeout on drill (no answer submitted)
Given a learner is on a drill and 60 seconds have elapsed,
When no answer has been submitted,
Then the drill auto-advances to the next drill,
  and a review_event row is inserted with score=0 and timed_out=1,
  and the session progress bar increments.

Scenario 4: Performance under load
Given a session contains 15 drills,
When the learner completes all 15 drills,
Then total session duration overhead (excluding user think-time) is under 3 seconds,
  and all 15 review_event rows are present in the database.
```

**Test mapping:**
- Scenario 1 -> `test_drill_correct_answer_inserts_review_event()`
- Scenario 2 -> `test_drill_incorrect_answer_recalculates_interval()`
- Scenario 3 -> `test_drill_timeout_records_timed_out_flag()`
- Scenario 4 -> `test_full_session_overhead_under_3_seconds()`

---

### Example 2: SRS Review Scheduling

**Story:** As a learner, I want my SRS review intervals to adapt based on my accuracy so that I spend more time on items I struggle with.

```
Scenario 1: Correct review increases interval
Given a learner has item X at mastery_stage 2 with next_review due now,
When they review item X and answer correctly,
Then mastery_stage increments to 3,
  and next_review is set to current_time + interval_for_stage_3,
  and the interval_for_stage_3 is longer than interval_for_stage_2.

Scenario 2: Incorrect review decreases interval
Given a learner has item X at mastery_stage 4 with next_review due now,
When they review item X and answer incorrectly,
Then mastery_stage decrements to max(1, mastery_stage - 1),
  and next_review is set to current_time + interval_for_stage_3,
  and the item appears in the next session's review queue.

Scenario 3: New item starts at stage 1
Given a learner encounters item X for the first time in a session,
When the drill is completed (correct or incorrect),
Then a progress row is created with mastery_stage=1,
  and next_review is set to current_time + interval_for_stage_1.

Scenario 4: Items at max mastery stage
Given a learner has item X at mastery_stage=6 (maximum),
When they answer correctly,
Then mastery_stage remains at 6,
  and next_review is set to current_time + max_interval (30 days).

Scenario 5: Concurrent session handling
Given a learner has two browser tabs with active sessions,
When both sessions attempt to update the same item's mastery_stage simultaneously,
Then scheduler_lock.py prevents a race condition,
  and the final mastery_stage reflects exactly one update.
```

---

### Example 3: Session Management

**Story:** As a learner, I want to resume an interrupted session so that I don't lose progress if my connection drops.

```
Scenario 1: Resume after WebSocket disconnect
Given a learner is on drill 5 of 10 in an active session,
When the WebSocket connection drops and reconnects within 30 seconds,
Then the session resumes at drill 5 (not drill 1),
  and all 4 previously completed drill results are preserved.

Scenario 2: Resume after browser close
Given a learner closes the browser on drill 5 of 10,
When they reopen the app within 2 hours,
Then they are offered the option to resume the interrupted session,
  and if they choose to resume, they start at drill 5.

Scenario 3: Session expiration
Given a learner abandoned a session more than 2 hours ago,
When they return to the app,
Then the abandoned session is marked as incomplete in the session table,
  and a new session is started from scratch,
  and the incomplete session's drill results are still preserved in review_event.

Scenario 4: No session to resume
Given a learner has no interrupted sessions,
When they open the app and tap "Start Session,"
Then a new session is created with drills selected by the scheduler,
  and no resume prompt is shown.
```

---

### Example 4: Authentication Flow

**Story:** As a returning user, I want to log in with my email and password so that I can access my learning progress.

```
Scenario 1: Successful login
Given a user has a verified account with email "test@aelu.app",
When they submit correct credentials,
Then a JWT access token is returned with a 24-hour expiry,
  and a refresh token is set as an HTTP-only cookie,
  and the response includes the user's current HSK level and last session date.

Scenario 2: Incorrect password
Given a user has a verified account,
When they submit an incorrect password,
Then the response is 401 with message "Invalid credentials",
  and no JWT is issued,
  and the failed attempt is logged in the auth_event table.

Scenario 3: Account lockout after repeated failures
Given a user has failed login 5 times within 15 minutes,
When they attempt a 6th login (even with correct credentials),
Then the response is 429 with message "Account temporarily locked",
  and the lockout duration is 15 minutes,
  and the lockout event is logged.

Scenario 4: JWT expiration
Given a user's access token has expired,
When they make an API request with the expired token,
Then the response is 401 with message "Token expired",
  and the client can use the refresh token to obtain a new access token
  without re-entering credentials.

Scenario 5: MFA-enabled account
Given a user has MFA enabled via mfa.py,
When they submit correct credentials,
Then a partial auth response is returned requesting the MFA code,
  and the JWT is not issued until the MFA code is verified.
```

---

### Example 5: Admin Dashboard

**Story:** As the product owner, I want to see system health metrics on the admin dashboard so that I can spot problems before users report them.

```
Scenario 1: Dashboard loads with current data
Given I am authenticated as an admin user,
When I load the admin dashboard,
Then I see: active users (last 7 days), total sessions (last 7 days),
  average drill accuracy (last 7 days), crash_log count (last 24 hours),
  and all metrics load within 1 second.

Scenario 2: Crash log alert
Given there are 3+ new crash_log entries in the last 24 hours,
When I load the admin dashboard,
Then a red alert banner appears at the top showing the count and most recent error message,
  and I can click through to view full crash details.

Scenario 3: No data state
Given the application was just deployed and no users have created sessions,
When I load the admin dashboard,
Then all metrics show 0 (not "N/A", not an error, not a blank page),
  and the dashboard renders without JavaScript errors.

Scenario 4: Non-admin access rejected
Given I am authenticated as a regular learner (not admin),
When I attempt to access the admin dashboard URL,
Then the response is 403 Forbidden,
  and the attempt is logged as a security_event.

Scenario 5: Client error log display
Given client_error_log has entries from the last 48 hours,
When I view the error section of the admin dashboard,
Then I see errors grouped by type with counts,
  and each error shows: timestamp, user_id (if authenticated), error message, URL.
```

---

## Writing Criteria for Non-Functional Requirements

For performance, security, and reliability stories, the criteria must include specific thresholds.

### Performance Criteria Template
```
Given [workload description],
When [action under test],
Then [metric] is [operator] [threshold] at [percentile].
```

Example: "Given 50 concurrent users are completing sessions, When each submits a drill answer, Then response time is under 200ms at p95."

### Security Criteria Template
```
Given [attacker scenario],
When [attack vector],
Then [defensive outcome] and [logging outcome].
```

Example: "Given an unauthenticated request targets /api/admin/metrics, When the request is received, Then a 401 response is returned and the attempt is logged in security_event."

### Reliability Criteria Template
```
Given [failure scenario],
When [the system detects the failure],
Then [recovery action] within [time bound] and [data preservation guarantee].
```

Example: "Given the SQLite database file is locked by a concurrent writer, When a session attempts to write a review_event, Then the write retries up to 3 times with 100ms backoff and no data is lost."
