# Aelu NPS Framework

**Last Updated:** 2026-03-10

---

## What is NPS and Why It Matters for Aelu

Net Promoter Score measures the likelihood that users would recommend Aelu to others. For a solo-founder product without a marketing budget, word-of-mouth is the most realistic growth channel. NPS directly measures word-of-mouth potential.

NPS is not a vanity metric if you act on it. The score itself is less important than the verbatim comments from detractors (what to fix) and promoters (what to amplify).

---

## Trigger Logic

### When to Show the NPS Prompt
- **Trigger:** After every 10th completed session (session 10, 20, 30, 40, ...)
- **Conditions:**
  - User has NOT seen an NPS prompt in the last 30 days
  - User's session was completed (not abandoned)
  - User is a paying subscriber (free trial users are excluded — their NPS reflects trial friction, not product value)
- **Timing:** Show the prompt on the session completion screen, below the session summary. Not a modal. Not blocking. The user can dismiss and never see it again until the next trigger.

### Implementation

```python
# Pseudocode for NPS trigger check
def should_show_nps(user_id, db):
    completed_sessions = db.execute(
        "SELECT COUNT(*) FROM session_log WHERE user_id = ? AND completed = 1",
        (user_id,)
    ).fetchone()[0]

    if completed_sessions % 10 != 0:
        return False

    last_nps = db.execute(
        "SELECT MAX(created_at) FROM user_feedback WHERE user_id = ? AND feedback_type = 'nps'",
        (user_id,)
    ).fetchone()[0]

    if last_nps and days_since(last_nps) < 30:
        return False

    return True
```

### Storage

Use the existing `user_feedback` table:

```sql
INSERT INTO user_feedback (user_id, feedback_type, rating, feedback_text, created_at)
VALUES (?, 'nps', ?, ?, datetime('now'));
```

- `feedback_type = 'nps'`
- `rating` = 0-10 (the NPS score)
- `feedback_text` = the follow-up comment (nullable)

---

## Prompt Design

### Primary Question
"How likely are you to recommend Aelu to a friend learning Mandarin?"

Scale: 0 (Not at all likely) to 10 (Extremely likely)

Display as a horizontal row of numbered buttons (0-10). Tapping a number submits the score and reveals the follow-up.

### Follow-Up Questions

**For Detractors (0-6):**
"We're sorry to hear that. What would need to change for you to recommend Aelu?"
- Free text input, 500 character limit
- Submit button
- "Skip" option (don't force feedback)

**For Passives (7-8):**
"Thanks! Is there anything that would make Aelu a 9 or 10 for you?"
- Free text input, 500 character limit
- Submit button
- "Skip" option

**For Promoters (9-10):**
"That's great to hear! What do you like most about Aelu?"
- Free text input, 500 character limit
- Submit button
- "Skip" option

### Dismissal
- If the user taps outside the prompt or scrolls past it, the prompt disappears
- A dismissed prompt does NOT count as a response — the user will be prompted again after their next 10th session (subject to the 30-day cooldown)
- A submitted score (even without follow-up text) DOES count as a response

---

## NPS Calculation

### Formula
```
NPS = (% Promoters) - (% Detractors)
```

- **Promoters:** Respondents who scored 9-10
- **Passives:** Respondents who scored 7-8 (not used in calculation)
- **Detractors:** Respondents who scored 0-6

### Example
If 20 users respond:
- 10 score 9-10 (50% promoters)
- 5 score 7-8 (25% passives)
- 5 score 0-6 (25% detractors)
- NPS = 50 - 25 = **25**

### Interpretation

| NPS Range | Interpretation | Typical SaaS |
|---|---|---|
| -100 to 0 | Serious problems. Most users would not recommend. | Bottom quartile |
| 0 to 30 | Mediocre. Some advocacy but significant detraction. | Average |
| 30 to 50 | Good. More promoters than detractors. | Above average |
| 50 to 70 | Excellent. Strong word-of-mouth potential. | Top quartile |
| 70 to 100 | Exceptional. Rare for any product. | Elite |

**Aelu target: NPS > 40 within 6 months of launch.**

---

## Reporting

### Monthly NPS Report (admin dashboard)

| Metric | Value |
|---|---|
| Responses this month | X |
| Promoters (9-10) | X (Y%) |
| Passives (7-8) | X (Y%) |
| Detractors (0-6) | X (Y%) |
| NPS Score | Z |
| Response rate | X% of prompted users |

### SQL for Monthly NPS

```sql
-- Monthly NPS calculation
SELECT
    strftime('%Y-%m', created_at) AS month,
    COUNT(*) AS total_responses,
    SUM(CASE WHEN rating >= 9 THEN 1 ELSE 0 END) AS promoters,
    SUM(CASE WHEN rating BETWEEN 7 AND 8 THEN 1 ELSE 0 END) AS passives,
    SUM(CASE WHEN rating <= 6 THEN 1 ELSE 0 END) AS detractors,
    ROUND(
        (SUM(CASE WHEN rating >= 9 THEN 1.0 ELSE 0 END) / COUNT(*) * 100) -
        (SUM(CASE WHEN rating <= 6 THEN 1.0 ELSE 0 END) / COUNT(*) * 100)
    ) AS nps
FROM user_feedback
WHERE feedback_type = 'nps'
GROUP BY strftime('%Y-%m', created_at)
ORDER BY month;
```

### Trend Tracking

| Month | Responses | Promoters % | Passives % | Detractors % | NPS | Response Rate |
|---|---|---|---|---|---|---|
| (no data yet) | | | | | | |

### Verbatim Review

Every month, read ALL detractor comments. These are the most actionable feedback in the system. For each detractor comment:
1. Categorize: UX, Content, Performance, Pricing, Missing Feature, Other
2. Determine if a backlog item exists for the issue
3. If not, create one
4. Log in the Feedback-to-Action Log (see feedback-loop.md)

Promoter comments are also valuable — they tell you what to protect and amplify in marketing.

---

## Response Rate

### Target: >30% of prompted users submit a score

If response rate is below 30%:
- The prompt may be too easy to dismiss (make it slightly more prominent without being annoying)
- The timing may be wrong (try showing it 5 seconds after session summary loads, not immediately)
- Users may have prompt fatigue (ensure the 30-day cooldown is working)

If response rate is above 60%:
- The prompt may be too aggressive. Verify it's not blocking core functionality.

### Tracking Response Rate

```sql
-- Response rate calculation
-- Requires knowing how many users were prompted (log prompt displays)
SELECT
    (SELECT COUNT(*) FROM user_feedback WHERE feedback_type = 'nps' AND created_at > date('now', '-30 days'))
    * 100.0 /
    NULLIF((SELECT COUNT(*) FROM lifecycle_event WHERE event_type = 'nps_prompted' AND created_at > date('now', '-30 days')), 0)
AS response_rate_percent;
```

This requires logging an `nps_prompted` lifecycle event whenever the prompt is shown (even if dismissed).

---

## Action Protocol

### Weekly (during feedback review)
- Check for new NPS submissions
- Read all verbatim comments
- Flag any score of 0-3 for immediate investigation (these users are likely to churn)

### Monthly
- Calculate NPS score
- Compare to previous month
- Review detractor themes: are the same issues repeating?
- Update the trend table above

### Quarterly
- Analyze NPS by user cohort (signup month) — are newer users happier than older ones?
- Cross-reference NPS with usage data: do high-NPS users have more sessions? Higher accuracy?
- Decide if NPS target needs adjustment based on industry benchmarks and user base composition
