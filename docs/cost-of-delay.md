# Cost of Delay Analysis Framework

## Overview

Cost of Delay (CoD) quantifies the economic impact of not delivering a feature per unit of time. Combined with estimated duration, CD3 (Cost of Delay Divided by Duration) provides a prioritization score: higher CD3 = more urgent to deliver.

```
CD3 = Cost of Delay per Week / Duration in Weeks
```

CD3 normalizes for feature size: a small feature with moderate CoD can rank higher than a large feature with high CoD, because it delivers value sooner.

---

## Urgency Profiles

### 1. Standard

Value accrues linearly over time. Delay costs a fixed amount per week. Most features fall here.

```
CoD(t) = c * t   (constant rate)
```

### 2. Fixed-Date

Value depends on hitting a specific deadline (App Store launch, semester start, conference demo). Missing the date causes a large step-function loss.

```
CoD(t) = 0           if t < deadline
CoD(t) = penalty      if t >= deadline
```

### 3. Expedite

Value decays rapidly. Delay causes compounding harm (security vulnerability, data loss bug, production outage).

```
CoD(t) = c * t^2   (accelerating rate)
```

---

## Worked Examples

### Example 1: Onboarding Email Sequence

**Feature**: Automated email sequence (Day 1, Day 3, Day 7) for new signups to drive first-week session count.

**Urgency profile**: Standard

**Cost of Delay calculation**:
- Survival analysis shows first-week session count is the strongest churn predictor (HR ~0.55 per SD increase)
- Without onboarding emails, estimated 35% of signups complete 3+ sessions in week 1
- With onboarding emails, estimated 50% complete 3+ sessions (industry benchmark: +15pp from email onboarding)
- At 100 signups/month, that's 15 additional retained users/month
- At 5% conversion and $125 LTV: 15 * 0.05 * $125 = $93.75/month in future LTV
- **CoD: ~$23/week** (prorated monthly LTV impact)

**Duration**: 1 week (email templates, scheduler integration, testing)

**CD3 = $23 / 1 = 23**

---

### Example 2: Stripe Payment Integration

**Feature**: Premium subscription billing via Stripe.

**Urgency profile**: Standard (no fixed date, but every week without payments = zero revenue)

**Cost of Delay calculation**:
- Cannot collect any revenue without payments
- At launch with 500 registered users and 5% conversion: 25 paid users * $9.99 = $250/month
- **CoD: $62.50/week** (forgone revenue)

**Duration**: 2 weeks (Stripe integration, webhook handling, tier gating, testing)

**CD3 = $62.50 / 2 = 31.25**

---

### Example 3: Security Vulnerability Fix (bandit finding)

**Feature**: Fix a high-severity finding from bandit scan (e.g., SQL injection in a route).

**Urgency profile**: Expedite

**Cost of Delay calculation**:
- Data breach cost for a small SaaS: $5,000-50,000 (legal, notification, reputation)
- Probability of exploitation per week with known vulnerability: ~1-5%
- Expected loss per week: 0.03 * $20,000 = $600/week
- **CoD: ~$600/week** (expected loss)

**Duration**: 0.5 weeks (fix the query, add parameterization, test, deploy)

**CD3 = $600 / 0.5 = 1200**

This should be fixed immediately. Expedite urgency profile confirmed.

---

### Example 4: Classroom/LTI Integration

**Feature**: Teacher accounts, classroom management, LTI integration for university LMS.

**Urgency profile**: Fixed-date (semester start dates are immovable; missing fall semester means waiting until spring)

**Cost of Delay calculation**:
- One university partnership: 200 students * $4.99/mo * 4 months = $3,992/semester
- If classroom feature misses fall semester start (September), delay cost is one full semester of revenue
- **CoD if before deadline: $0/week**
- **CoD if after deadline: $3,992 step function (one semester lost)**

**Duration**: 3 weeks (classroom model, invite codes, teacher dashboard, LTI integration)

**CD3 = $3,992 / 3 = 1331** (if approaching deadline)
**CD3 = $0 / 3 = 0** (if deadline is far away)

Schedule this to complete 2 weeks before semester start.

---

### Example 5: Graded Reader Content Expansion

**Feature**: Add 50 new graded reader passages (HSK 3-4 level).

**Urgency profile**: Standard

**Cost of Delay calculation**:
- Current content (50 passages) supports ~2 months of reading engagement
- After exhaustion, engaged readers have nothing new, increasing churn risk
- Estimated 10% of premium users are active readers = 10 users at month 6
- Lost revenue from reader churn: 10 * 0.15 (incremental churn) * $125 LTV = $187.50
- Spread over remaining engagement window: **CoD: ~$15/week**

**Duration**: 2 weeks (content generation with Claude, review against writing standard, database seeding)

**CD3 = $15 / 2 = 7.5**

Low priority. Content expansion is important but not urgent relative to revenue-generating features.

---

## Current Priority Stack (CD3 Ranked)

| Rank | Feature | CoD/Week | Duration (weeks) | CD3 | Urgency |
|------|---------|----------|-------------------|-----|---------|
| 1 | Security vulnerability fix | $600 | 0.5 | 1200 | Expedite |
| 2 | Classroom (before semester) | $1331 | 3 | 1331* | Fixed-date |
| 3 | Stripe payments | $62.50 | 2 | 31.25 | Standard |
| 4 | Onboarding emails | $23 | 1 | 23 | Standard |
| 5 | Reader content expansion | $15 | 2 | 7.5 | Standard |

*CD3 for fixed-date features is only relevant when approaching the deadline. Far from the deadline, CD3 = 0.

---

## CD3 Calculation Template

Use this template for ongoing prioritization:

```
Feature: ___________________________________

Urgency Profile: [ ] Standard  [ ] Fixed-date  [ ] Expedite

1. Who is affected?
   - Number of users impacted: ____
   - Segment: [ ] All  [ ] Premium  [ ] Classroom  [ ] New signups

2. What is the impact of NOT having this feature?
   - Forgone revenue per week: $____
   - Increased churn per week: ____% of affected users
   - Risk exposure per week: $____ (probability * impact)
   - Other quantifiable impact: ____

3. Cost of Delay per week: $____
   (Sum of forgone revenue + churn LTV impact + risk exposure)

4. Estimated duration: ____ weeks

5. CD3 = CoD / Duration = ____

6. Context:
   - Dependencies: ____
   - Fixed deadline (if any): ____
   - Confidence in estimates: [ ] High  [ ] Medium  [ ] Low
```

---

## Guidelines

1. **Estimate honestly**. A rough estimate is better than no estimate, but do not inflate CoD to justify a pet feature. If you cannot quantify the impact, say so.

2. **Revisit weekly**. CoD changes as the user base grows, as deadlines approach, and as new information arrives. Re-rank the priority stack every Monday.

3. **Security is always expedite**. Any finding rated "high" or "critical" by bandit or pip-audit gets expedite urgency regardless of probability estimates.

4. **Fixed-date features need lead time**. Start calculating CD3 for semester-dependent features 8 weeks before the deadline. Before that, CD3 = 0 and the feature should not displace standard-urgency work.

5. **CD3 is a guide, not a rule**. A feature with CD3 = 5 that takes 30 minutes should be done immediately. A feature with CD3 = 50 that has deep technical risk may need investigation before commitment. Use judgment.
