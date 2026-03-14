# Metrics & KPI Framework

## North Star Metric

**Weekly Active Studying Users (WASU)** -- users who completed at least one drill session in the last 7 days.

### Why This Metric

Not "registered users" (vanity). Not "daily active" (too volatile for a study app where 3-4 sessions/week is healthy). Not "revenue" (lagging, and ignores the free tier that feeds the funnel). WASU captures the one thing that matters: people actually studying Mandarin with the app on a regular basis.

A user who opens the app but doesn't start a session doesn't count. A user who did one session 8 days ago doesn't count. This metric rewards genuine, recurring study behavior.

### How to Measure

```sql
SELECT COUNT(DISTINCT user_id)
FROM session_log
WHERE started_at >= datetime('now', '-7 days')
  AND items_completed > 0;
```

### Target Range

| Stage | WASU Target | Context |
|-------|-------------|---------|
| Pre-launch / beta | 20-50 | Friends, testers, waitlist converts |
| Month 1 post-launch | 50-150 | First organic growth |
| Month 3 | 150-400 | Channel experiments running |
| Month 6 | 400-1,000 | Product-market fit signal if retention holds |
| Month 12 | 1,000-3,000 | Sustainable indie business territory |

**Red flag:** WASU declining for 3+ consecutive weeks while signups are stable or growing. That means retention is broken -- stop acquiring and fix the product.

---

## KPI Hierarchy

Four levels, from business outcomes down to learning quality. Higher levels change slowly and are checked less frequently. Lower levels are leading indicators.

### Level 1 -- Business Health (check weekly)

| KPI | Formula | Target | Red Flag | Notes |
|-----|---------|--------|----------|-------|
| MRR | Sum of all active subscriptions | Growth trajectory | Flat or declining 3+ weeks | Stripe dashboard, reconcile monthly |
| Paying users | Count of active paid subscriptions | Steady growth | Net negative (more churn than new) | Stripe |
| Free users | Registered accounts minus paid | Growing but converting | Growing with zero conversion | Monitor ratio to paid |
| Gross churn rate | Cancellations this month / Paying users at start of month | < 8% monthly | > 12% monthly | Measures raw loss |
| Net revenue churn | (Lost MRR - expansion MRR) / Starting MRR | < 5% monthly | > 10% monthly | Negative net churn = expansion exceeds losses |
| Free-to-paid ratio | Free users / Paying users | 8:1 to 15:1 | > 25:1 (free users not converting) | Healthy ratio narrows over time |

**Revenue milestones to track:**
- $100 MRR -- first validation
- $500 MRR -- covers hosting and tools
- $1,000 MRR -- real indie SaaS territory
- $5,000 MRR -- sustainable solo business

### Level 2 -- Funnel (check weekly)

| Stage | Metric | Target | Red Flag | Fix Priority |
|-------|--------|--------|----------|--------------|
| Visitor -> Signup | Landing page conversion rate | 8-15% | < 5% | Messaging, page design, CTA clarity |
| Signup -> First session | Onboarding completion | 60-75% | < 40% | Onboarding flow, email nudge sequence |
| First session -> Activated | Completes 3+ sessions in first 14 days | 40-55% | < 25% | First-session experience, early content quality |
| Activated -> Paid | Converts to $14.99/month plan | 15-25% | < 8% | Paywall placement, value demonstration |
| Free -> Paid (overall) | All free users who eventually convert | 5-12% | < 3% | Entire funnel needs audit |

**Funnel math example at 1,000 visitors/month:**
```
1,000 visitors
  x 10% signup rate     = 100 signups
  x 65% first session   = 65 activated-ish
  x 45% truly activated = 29 activated
  x 20% convert to paid = 6 new paying users/month

At $14.99/month: $90 new MRR/month from 1,000 visitors
```

This is why retention and churn matter more than top-of-funnel at this scale.

### Level 3 -- Engagement (check weekly)

| KPI | How to Measure | Target | Red Flag | Why It Matters |
|-----|---------------|--------|----------|----------------|
| WAU (Weekly Active Users) | Distinct users with 1+ session, last 7 days | Steady or growing | 2+ weeks decline | The north star denominator |
| Sessions/user/week | Total sessions / WAU | 3-5 | < 2 | Below 2 = not building a habit |
| Avg session duration | Mean of `duration_seconds` for completed sessions | 12-20 min | < 8 min or > 30 min | Too short = not engaging; too long = might be frustration |
| Drill accuracy | `items_correct / items_completed` | 70-85% | < 60% or > 92% | Too low = content too hard; too high = not challenging enough |
| Drill type diversity | Distinct `drill_type` values used per user per week | 5+ types | < 3 types | Stuck in one mode = not developing balanced skills |
| Reading feature adoption | Users opening graded reader / WAU | 30-50% | < 15% | Key differentiator; low adoption = discoverability problem |
| Listening feature adoption | Users starting listening drill / WAU | 25-40% | < 12% | Second differentiator |
| Cleanup loop engagement | Users who look up a word in reader, then drill it | 40-60% of reader users | < 20% | This is the core learning loop -- if it's broken, the product thesis is broken |
| Early exit rate | Sessions with `early_exit = 1` / total sessions | < 15% | > 25% | Users bailing mid-session = frustration or boredom |
| Boredom flag rate | Sessions with `boredom_flags > 0` / total sessions | < 10% | > 20% | Direct signal of content staleness |

### Level 4 -- Learning Outcomes (check monthly)

| KPI | How to Measure | Target | Red Flag | Notes |
|-----|---------------|--------|----------|-------|
| HSK progression rate | Users advancing 1 HSK sub-level per 8-12 weeks | 60%+ of active users on pace | < 30% progressing | Requires sufficient session volume |
| Vocabulary retention (30-day) | Items reviewed 30+ days ago with `streak_correct >= 2` / total items at that age | 70-85% | < 55% | SRS effectiveness check |
| Skill balance score | Std dev of per-modality accuracy across reading/listening/speaking/IME | Low spread (< 15pts) | One modality 25+ pts behind others | Users should develop evenly |
| Words encountered via reading | `vocab_encounter` rows with `source_type = 'reader'` per active reader user/month | 30-60 new words | < 10 | Reader is generating new vocabulary |
| Cleanup loop completion | Encountered words that appear in a subsequent drill session | 50-70% of encountered words | < 25% | Loop must close for learning to stick |
| Mature vocabulary | Items at `mastery_stage = 'mature'` or `'intuitive'` per user | Growing monthly | Plateaued despite active study | Long-term SRS health |

---

## Cohort Analysis Framework

### Building Signup Cohorts

Group users by the **ISO week** they created their account. Every user belongs to exactly one cohort forever. Track what percentage of each cohort is still active in subsequent weeks.

```sql
-- Assign each user to their signup cohort (ISO week)
SELECT
    user_id,
    strftime('%Y-W%W', created_at) AS signup_cohort,
    date(created_at, 'weekday 1', '-7 days') AS cohort_week_start
FROM users
ORDER BY created_at;
```

### Cohort Retention Table Format

| Cohort | Size | Week 0 | Week 1 | Week 2 | Week 4 | Week 8 | Week 12 |
|--------|------|--------|--------|--------|--------|--------|---------|
| 2026-W08 | 42 | 100% | 48% | 38% | 30% | 24% | 21% |
| 2026-W09 | 55 | 100% | 52% | 42% | 35% | -- | -- |
| 2026-W10 | 61 | 100% | 45% | 37% | -- | -- | -- |
| 2026-W11 | 48 | 100% | 50% | -- | -- | -- | -- |
| 2026-W12 | 53 | 100% | -- | -- | -- | -- | -- |

"Active" = at least one completed session (`items_completed > 0`) during that week.

### Target Retention Benchmarks

| Transition | Healthy Range | Good | Exceptional |
|------------|--------------|------|-------------|
| Week 0 -> Week 1 | 40-55% | 50% | > 55% |
| Week 1 -> Week 4 | 50-65% of Week 1 | 60% | > 65% |
| Week 4 -> Week 12 | 50-70% of Week 4 | 60% | > 70% |
| Week 12 -> Week 24 | 60-80% of Week 12 | 70% | > 80% |

The curve should flatten over time. Users who survive to Week 12 are highly likely to stay. If the curve never flattens, there is a structural retention problem.

### Channel Cohorts

Split retention by `utm_source` to see which channels bring the stickiest users:

| Channel | Cohort Size | Week 1 | Week 4 | Week 12 | Notes |
|---------|-------------|--------|--------|---------|-------|
| Reddit organic | 85 | 52% | 35% | 23% | High intent, forums self-select |
| Google Ads (HSK intent) | 120 | 45% | 28% | 16% | Broad; test keyword segments |
| Product Hunt | 200 | 38% | 18% | 8% | Spike-and-fade, tourists |
| Content/SEO | 60 | 55% | 40% | 28% | Highest quality but slow to build |
| Partner referrals | 30 | 58% | 42% | 30% | Best retention, smallest volume |

**Action rule:** If a channel's Week 4 retention is less than half the best channel's Week 4, investigate the mismatch between channel messaging and product experience.

### HSK Level Cohorts

Split by the HSK level users self-select (or are assessed at) during onboarding:

| Starting Level | Cohort Size | Week 1 | Week 4 | Week 12 | Paid Conversion |
|----------------|-------------|--------|--------|---------|-----------------|
| HSK 1 (true beginner) | 150 | 42% | 25% | 14% | 4% |
| HSK 1-2 (some basics) | 200 | 50% | 35% | 24% | 10% |
| HSK 2-3 (intermediate) | 100 | 55% | 42% | 32% | 18% |
| HSK 3+ (advancing) | 50 | 48% | 38% | 28% | 22% |

Beginners churn hardest because learning a tonal language from zero is daunting. Users with some foundation get value faster. This informs both marketing targeting (focus on HSK 1-3 audience) and product investment (make the beginner experience stickier).

---

## LTV Calculation

### Simple Formula

```
LTV = ARPU x (1 / Monthly Churn Rate)
```

Where:
- **ARPU** (Average Revenue Per User) = MRR / Paying users
- **Monthly churn rate** = Users who cancelled this month / Paying users at start of month

Example: $14.99 ARPU x (1 / 0.08) = $14.99 x 12.5 = **$187 LTV**

### Segmented LTV

Not all users are equal. Segment by behavior to understand where lifetime value concentrates:

| Segment | % of Users | Avg Tenure (months) | Monthly ARPU | Estimated LTV | Notes |
|---------|-----------|---------------------|--------------|---------------|-------|
| Power learner (5+ sessions/week) | 10% | 18+ | $14.99 | $270+ | Core audience, protect at all costs |
| Steady learner (3-4 sessions/week) | 25% | 12 | $14.99 | $180 | Ideal users, optimize for this group |
| Casual learner (1-2 sessions/week) | 35% | 6 | $14.99 | $90 | Acceptable but at churn risk |
| Fading (< 1 session/week) | 20% | 3 | $14.99 | $45 | Intervention candidates |
| Churned within trial/month 1 | 10% | 1 | $14.99 | $15 | Onboarding failure or bad fit |

**Weighted average LTV:** ~$108 (if distribution holds)

### LTV:CAC Ratio Targets

| Ratio | Status | Action |
|-------|--------|--------|
| > 5:1 | Excellent | You may be under-investing in growth |
| 3:1 - 5:1 | Healthy | Sustainable, keep optimizing |
| 2:1 - 3:1 | Marginal | Acceptable for new channels being tested |
| 1:1 - 2:1 | Unsustainable | Reduce spend, fix retention or conversion |
| < 1:1 | Losing money | Kill the channel immediately |

At $14.99/month and ~$135 LTV, your CAC ceiling is $45 (for 3:1). But aim for < $25 CAC to maintain healthy margins as a solo operation with no VC buffer.

### Optimization Levers (ranked by impact)

1. **Reduce churn** -- Moving monthly churn from 10% to 7% increases LTV from $150 to $214. Single highest-leverage action. Focus on the Week 2-6 danger zone where most churn happens.
2. **Increase activation rate** -- Getting more signups to their third session. Doesn't increase per-user LTV but increases total lifetime revenue by expanding the paying base.
3. **Improve free-to-paid conversion** -- Better paywall timing, clearer value demonstration at the gate. Directly increases paying user count without more traffic.
4. **Reduce CAC** -- Shift spend from paid channels to organic/content. Doesn't change LTV but improves the ratio.

---

## CAC by Channel

### Channel Performance Table

| Channel | Monthly Spend | Signups | Paid Conversions | CAC (per paid) | Target CAC | Kill Threshold |
|---------|--------------|---------|------------------|----------------|------------|----------------|
| Reddit organic | $0 (time: ~6 hrs/mo) | 30-50 | 3-5 | $0 cash / ~$15 time-adjusted | < $20 | N/A (free, but track time) |
| Google Ads | $200-400 | 40-80 | 4-8 | $25-50 | < $30 | > $50 for 2 consecutive weeks |
| Partner referrals | $0-50 (rev share or credits) | 10-20 | 3-6 | $8-17 | < $20 | N/A (usually best economics) |
| Content/SEO | $0 (time: ~10 hrs/mo) | 15-40 | 3-8 | $0 cash / ~$12 time-adjusted | < $15 | N/A (compounds over time) |
| Product Hunt | $0 (one-time effort) | 100-300 (spike) | 5-15 | $0 cash | N/A | One-shot, measure 30-day retained |

### Time-Based CAC for Organic Channels

For channels where the cost is your time rather than dollars, calculate honestly:

```
Time-adjusted CAC = (Hours spent x Your hourly rate) / Paid conversions from that channel
```

Use a reasonable hourly rate for your time. $25-50/hour is fair for a solo developer. If you're spending 10 hours/month on Reddit for 4 paid conversions at $30/hour:

```
Time-adjusted CAC = (10 x $30) / 4 = $75
```

That is worse than Google Ads. Be honest about where your time goes.

**Rules:**
- Track time spent on each organic channel in a simple spreadsheet (date, channel, minutes)
- Re-evaluate monthly: is this channel worth your time at the current conversion rate?
- Content/SEO has a compounding return -- the same blog post generates traffic for months. Reddit posts decay in 48 hours. Weight accordingly.

### When to Kill a Paid Channel

| Signal | Action |
|--------|--------|
| No conversions after $100 spend | Pause. Test different creative or targeting before restarting. |
| CAC > kill threshold for 2 consecutive weeks | Cut budget by 50%. If still above threshold after 2 more weeks, pause entirely. |
| LTV:CAC < 2:1 for the channel | Not sustainable. Pause or radically restructure. |
| Channel cohort Week 4 retention < 15% | Users from this channel aren't sticking. The traffic quality is bad regardless of CAC. |

---

## Reporting Cadence

### Daily -- 2-Minute Glance

Open once per day. Do not act on daily data unless something is obviously broken.

**What to check:**
- [ ] Stripe dashboard: any new subscriptions? Any cancellations?
- [ ] GA4 Realtime: is traffic flowing? Any unusual spikes or drops?
- [ ] Error monitoring: any 500 errors or crashes?

**What NOT to do:** React to a single bad day. One day of low signups is noise. Three days is a pattern worth investigating.

### Weekly -- 15-Minute Review (Monday mornings)

The core operating rhythm. Fill in the weekly report template (below).

**What to check:**
- [ ] WASU (north star): up, down, or flat vs. last week?
- [ ] New signups and source breakdown (UTM)
- [ ] Funnel conversion rates at each stage
- [ ] Sessions/user/week and session duration
- [ ] Drill accuracy (global and by type)
- [ ] Feature adoption rates (reader, listening, cleanup loop)
- [ ] MRR and net new paying users
- [ ] Any churn? Check cancellation reasons if available.
- [ ] Early exit rate and boredom flag rate

**Action rule:** Pick at most ONE thing to improve this week. Do not try to fix everything at once.

### Monthly -- 1-Hour Deep Dive (first Monday of the month)

Fill in the monthly report template. This is where you look at trends, not snapshots.

**What to check:**
- [ ] All weekly metrics with month-over-month comparison
- [ ] Cohort retention curves: are newer cohorts retaining better than older ones?
- [ ] LTV calculation update with fresh churn data
- [ ] LTV:CAC ratio by channel
- [ ] HSK progression rates: are users actually learning?
- [ ] Vocabulary retention at 30 days: is the SRS working?
- [ ] Feature adoption trends: are new features getting used?
- [ ] Churn analysis: who left, why, at what point in their lifecycle?
- [ ] SQL queries from the section below for detailed diagnostics

### Quarterly -- 2-Hour Strategic Review

Step back from the numbers. Think about direction.

**What to assess:**
- [ ] Are we growing? At what rate? Is the rate accelerating or decelerating?
- [ ] Which channels should we double down on? Which should we cut?
- [ ] What does the LTV:CAC picture look like? Can we afford to invest more in growth?
- [ ] Are learning outcomes improving? Is the product actually teaching Mandarin effectively?
- [ ] What's the biggest single bottleneck in the funnel? What would it take to fix it?
- [ ] Competitive landscape: has anything changed? New entrants? Pricing shifts?
- [ ] Product roadmap: are we building features that move the metrics that matter?
- [ ] Revenue trajectory: are we on track for the next milestone?

---

## Report Templates

### Weekly Report Template

```
WEEKLY REPORT: Week of [DATE]
============================================================

NORTH STAR
  WASU:                    [___] (last week: [___], delta: [+/-___])

BUSINESS HEALTH
  MRR:                     $[___] (last week: $[___])
  New paying users:        [___]
  Churned paying users:    [___]
  Net new paying:          [+/-___]
  Total paying users:      [___]
  Total free users:        [___]

FUNNEL (this week's cohort)
  Visitors:                [___]
  Signups:                 [___] ([___]% of visitors)
  First session:           [___] ([___]% of signups)
  Activated (3+ sessions): [___] ([___]% of first session)
  Converted to paid:       [___] ([___]% of activated)

ENGAGEMENT
  Sessions/user/week:      [___] (target: 3-5)
  Avg session duration:    [___] min (target: 12-20)
  Drill accuracy:          [___]% (target: 70-85%)
  Drill types used (avg):  [___] (target: 5+)
  Early exit rate:         [___]% (target: < 15%)
  Boredom flag rate:       [___]% (target: < 10%)

FEATURE ADOPTION (% of WAU)
  Reading (graded reader): [___]%
  Listening drills:        [___]%
  Cleanup loop:            [___]%
  Speaking drills:         [___]%

CHANNELS (signups / paid conversions this week)
  Reddit organic:          [___] / [___]
  Google Ads:              [___] / [___]  (spend: $[___])
  Content/SEO:             [___] / [___]
  Partner referrals:       [___] / [___]
  Other/direct:            [___] / [___]

NOTABLE
  Best thing this week:    [one sentence]
  Worst thing this week:   [one sentence]
  Surprise:                [one sentence]

ACTION ITEMS (max 3)
  1. [___]
  2. [___]
  3. [___]
```

### Monthly Report Template

```
MONTHLY REPORT: [MONTH YEAR]
============================================================

EXECUTIVE SUMMARY
  [2-3 sentences: how did the month go? What moved? What didn't?]

BUSINESS HEALTH (month-over-month)
                          This Month    Last Month    Delta     Trend
  MRR:                    $[___]        $[___]        [+/-]%    [arrow]
  Paying users:           [___]         [___]         [+/-]%    [arrow]
  Free users:             [___]         [___]         [+/-]%    [arrow]
  Gross churn rate:       [___]%        [___]%        [+/-]pp   [arrow]
  Net revenue churn:      [___]%        [___]%        [+/-]pp   [arrow]
  New subscriptions:      [___]         [___]         [+/-]%    [arrow]
  Cancellations:          [___]         [___]         [+/-]%    [arrow]

FUNNEL (month-over-month)
                          This Month    Last Month    Delta
  Visitors:               [___]         [___]         [+/-]%
  Visitor -> Signup:      [___]%        [___]%        [+/-]pp
  Signup -> First session:[___]%        [___]%        [+/-]pp
  First -> Activated:     [___]%        [___]%        [+/-]pp
  Activated -> Paid:      [___]%        [___]%        [+/-]pp
  Free -> Paid (overall): [___]%        [___]%        [+/-]pp

COHORT DATA
  [Paste updated cohort retention table here]

  Cohort quality trend:   [Are newer cohorts retaining better or worse?]
  Best-performing cohort:  Week [___] ([___]% Week 4 retention)
  Worst-performing cohort: Week [___] ([___]% Week 4 retention)

LTV & CAC
  Current LTV estimate:   $[___] (last month: $[___])
  Blended CAC:            $[___] (last month: $[___])
  LTV:CAC ratio:          [___]:1

  By channel:
    Reddit organic:        LTV:CAC = [___]:1
    Google Ads:            LTV:CAC = [___]:1
    Content/SEO:           LTV:CAC = [___]:1
    Partner referrals:     LTV:CAC = [___]:1

ENGAGEMENT (monthly averages)
                          This Month    Last Month    Delta
  WASU (avg):             [___]         [___]         [+/-]%
  Sessions/user/week:     [___]         [___]         [+/-]
  Avg session duration:   [___] min     [___] min     [+/-]
  Drill accuracy:         [___]%        [___]%        [+/-]pp
  Feature adoption (read):[___]%        [___]%        [+/-]pp
  Feature adoption (list):[___]%        [___]%        [+/-]pp
  Cleanup loop:           [___]%        [___]%        [+/-]pp

CHURN ANALYSIS
  Total cancellations:    [___]
  MRR lost to churn:      $[___]
  Top cancellation reason:[___]
  Avg tenure at churn:    [___] months
  Churn by lifecycle:
    Month 1 churners:     [___] ([___]%)
    Month 2-3 churners:   [___] ([___]%)
    Month 4-6 churners:   [___] ([___]%)
    Month 7+ churners:    [___] ([___]%)

LEARNING OUTCOMES
  HSK progression rate:   [___]% of active users on pace
  Vocab retention (30d):  [___]%
  Skill balance (std dev):[___] pts
  Words via reader/month: [___] avg per reader user
  Cleanup loop closure:   [___]%

KEY DECISIONS
  1. [What will you change based on this month's data?]
  2. [What will you keep doing?]
  3. [What will you stop doing?]

NEXT MONTH PRIORITIES
  1. [___]
  2. [___]
  3. [___]
```

### Churn Report Template

Generate this whenever churn exceeds the red flag threshold (> 12% monthly) or as part of the monthly deep dive.

```
CHURN REPORT: [MONTH YEAR]
============================================================

SUMMARY
  Cancellations this period:     [___]
  MRR impact:                    -$[___]
  Gross churn rate:              [___]%
  Net churn rate:                [___]% (after expansion/reactivation)

CANCELLATION BREAKDOWN
  By reason (if captured via cancellation survey):
    Too expensive:               [___] ([___]%)
    Not using enough:            [___] ([___]%)
    Switched to competitor:      [___] ([___]%)
    Achieved goal / done:        [___] ([___]%)
    Technical issues:            [___] ([___]%)
    No reason given:             [___] ([___]%)

  By tenure at cancellation:
    < 1 month:                   [___] ([___]%)  -- Onboarding failure
    1-3 months:                  [___] ([___]%)  -- Value not demonstrated
    3-6 months:                  [___] ([___]%)  -- Plateau / boredom
    6-12 months:                 [___] ([___]%)  -- Goal achieved or life change
    12+ months:                  [___] ([___]%)  -- Investigate individually

  By last activity before churn:
    Active within 7 days:        [___] ([___]%)  -- Sudden departure (price/competitor)
    Inactive 7-30 days:          [___] ([___]%)  -- Gradual disengagement
    Inactive 30+ days:           [___] ([___]%)  -- Already gone, just cancelled billing

  By HSK level at churn:
    HSK 1:                       [___] ([___]%)
    HSK 2:                       [___] ([___]%)
    HSK 3:                       [___] ([___]%)
    HSK 4+:                      [___] ([___]%)

SAVE OFFER PERFORMANCE
  Save offers presented:         [___]
  Accepted (stayed):             [___] ([___]% save rate)
  Offer type breakdown:
    Discount (1 month free):     [___] presented / [___] accepted
    Pause (1-3 months):          [___] presented / [___] accepted
    Downgrade suggestion:        [___] presented / [___] accepted

PAUSE & REACTIVATION
  Users currently paused:        [___]
  Paused users reactivated:      [___] ([___]% reactivation rate)
  Avg pause duration:            [___] days
  MRR recovered from reactivation: $[___]

INVOLUNTARY CHURN (payment failures)
  Failed payments this month:    [___]
  Recovered after retry:         [___] ([___]%)
  Lost to failed payment:        [___] ([___]%)
  Action: [Are dunning emails working? Update retry logic?]

ACTIONS
  1. [What will you do about the top churn reason?]
  2. [Any save offer changes?]
  3. [Any product changes to reduce churn?]
```

---

## Tool Recommendations

### The Simplest Stack (start here, stay here until 1,000+ users)

| Tool | Purpose | Cost | Notes |
|------|---------|------|-------|
| **GA4** | Traffic analytics, funnel, cohorts | Free | Already set up per tracking-plan.md. Use Explorations for cohort and funnel reports. |
| **Google Sheets** | Metrics tracking, weekly/monthly reports | Free | One sheet per report type. Manual entry forces you to actually look at the numbers. Automate later. |
| **Stripe Dashboard** | MRR, churn, subscription metrics | Included with Stripe | Stripe's built-in analytics cover 90% of business health metrics. Use their Revenue and Subscription tabs. |
| **Buttondown or Loops** | Email sequences, churn recovery | Free tier / $20-30/month | Transactional + marketing email. Buttondown for simplicity, Loops for automation flows. |
| **SQLite queries** | Learning outcomes, engagement deep dives | Free | Your database already has everything. Run the queries below directly. |

### What to Add at 500-1,000 Users

| Tool | Purpose | When to Add | Cost |
|------|---------|-------------|------|
| **PostHog** (self-hosted or cloud) | Product analytics, feature flags | When GA4 event limits feel constraining | Free tier generous |
| **Stripe Sigma** or **ChartMogul** | Advanced subscription analytics | When manual MRR tracking in Sheets becomes tedious | $0-100/month |
| **Simple email automation** | Churn prevention, onboarding drips | When you have enough data to segment | Included in email tool |

### What NOT to Buy Yet

| Tool | Why Not Yet | When It Makes Sense |
|------|------------|---------------------|
| **Mixpanel** | Overkill under 1,000 users. GA4 + your SQLite does the same thing. You will spend more time configuring Mixpanel than learning from it. | 5,000+ users, multiple product surfaces, team of 2+ |
| **Amplitude** | Same as Mixpanel. Powerful but you don't need behavioral cohort analysis when you can just read your database. | 5,000+ users, need advanced funnel analysis |
| **Customer.io** | Sophisticated lifecycle email. You have < 500 users -- a 5-email sequence in Buttondown handles it. | 2,000+ users, complex lifecycle stages, multiple segments |
| **Segment** | Data pipeline tool. You have one data source (your app) and one destination (your database). Segment solves a problem you don't have. | Multiple data sources, multiple analytics tools, team of 3+ |
| **Tableau / Looker** | Visualization tools for teams. You are one person looking at one spreadsheet. | Never, probably. Google Sheets + SQL covers solo dev needs. |

**The rule:** If you can get the answer by running a SQL query and looking at a Sheets chart, you don't need another tool. Add tools when the pain of NOT having them is obvious, not when you imagine you might need them someday.

---

## SQL Queries

Ten ready-to-run queries for your SQLite database. These reference the actual schema: `content_item`, `session_log`, `error_log`, `progress`, `vocab_encounter`, plus a `users` table (to be added for multi-user) with columns `id`, `created_at`, `email`, `plan` (`'free'`/`'paid'`), `utm_source`, `utm_medium`, `utm_campaign`, `cancelled_at`.

For the current single-user system, remove the `user_id` clauses and the `users` table joins. These are written for the multi-user version you will ship.

### 1. Daily Active Users (trailing 7 days, by day)

```sql
-- Daily active users for the past 7 days.
-- "Active" = completed at least one drill item in a session that day.
SELECT
    date(s.started_at) AS day,
    COUNT(DISTINCT s.user_id) AS active_users
FROM session_log s
WHERE s.started_at >= datetime('now', '-7 days')
  AND s.items_completed > 0
GROUP BY date(s.started_at)
ORDER BY day;
```

### 2. Weekly Sessions Per User (current week vs. last week)

```sql
-- Sessions per user for the current and previous ISO week.
-- Helps spot engagement trends before they show up in churn.
WITH weekly AS (
    SELECT
        s.user_id,
        CASE
            WHEN s.started_at >= date('now', 'weekday 1', '-7 days')
                 THEN 'this_week'
            WHEN s.started_at >= date('now', 'weekday 1', '-14 days')
                 AND s.started_at < date('now', 'weekday 1', '-7 days')
                 THEN 'last_week'
        END AS week_label,
        COUNT(*) AS sessions
    FROM session_log s
    WHERE s.started_at >= date('now', 'weekday 1', '-14 days')
      AND s.items_completed > 0
    GROUP BY s.user_id, week_label
)
SELECT
    week_label,
    COUNT(DISTINCT user_id) AS active_users,
    ROUND(AVG(sessions), 1) AS avg_sessions_per_user,
    MIN(sessions) AS min_sessions,
    MAX(sessions) AS max_sessions
FROM weekly
WHERE week_label IS NOT NULL
GROUP BY week_label;
```

### 3. New Signups (last 30 days, by day, by source)

```sql
-- New signups per day, broken down by acquisition source.
-- Use this to see which channels are producing volume.
SELECT
    date(u.created_at) AS signup_date,
    COALESCE(u.utm_source, 'direct') AS source,
    COUNT(*) AS signups
FROM users u
WHERE u.created_at >= datetime('now', '-30 days')
GROUP BY signup_date, source
ORDER BY signup_date DESC, signups DESC;
```

### 4. Activation Rate (signups who complete 3+ sessions within 14 days)

```sql
-- Activation rate by signup week.
-- Activated = completed 3+ sessions within 14 days of account creation.
WITH signup_cohort AS (
    SELECT
        u.id AS user_id,
        u.created_at AS signup_date,
        strftime('%Y-W%W', u.created_at) AS cohort_week
    FROM users u
    WHERE u.created_at >= datetime('now', '-60 days')
),
session_counts AS (
    SELECT
        sc.user_id,
        sc.cohort_week,
        COUNT(*) AS sessions_in_14d
    FROM signup_cohort sc
    JOIN session_log s
        ON s.user_id = sc.user_id
       AND s.started_at BETWEEN sc.signup_date
           AND datetime(sc.signup_date, '+14 days')
       AND s.items_completed > 0
    GROUP BY sc.user_id, sc.cohort_week
)
SELECT
    sc.cohort_week,
    COUNT(DISTINCT sc.user_id) AS total_signups,
    COUNT(DISTINCT CASE WHEN COALESCE(sn.sessions_in_14d, 0) >= 1 THEN sc.user_id END) AS had_first_session,
    COUNT(DISTINCT CASE WHEN COALESCE(sn.sessions_in_14d, 0) >= 3 THEN sc.user_id END) AS activated,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN COALESCE(sn.sessions_in_14d, 0) >= 3 THEN sc.user_id END)
        / COUNT(DISTINCT sc.user_id), 1) AS activation_pct
FROM signup_cohort sc
LEFT JOIN session_counts sn ON sn.user_id = sc.user_id AND sn.cohort_week = sc.cohort_week
GROUP BY sc.cohort_week
ORDER BY sc.cohort_week;
```

### 5. Feature Adoption (last 7 days)

```sql
-- Feature adoption rates among weekly active users.
-- Measures what percentage of active users engage each feature.
WITH active_users AS (
    SELECT DISTINCT user_id
    FROM session_log
    WHERE started_at >= datetime('now', '-7 days')
      AND items_completed > 0
),
feature_usage AS (
    SELECT
        s.user_id,
        -- Reading: sessions containing reading-modality drills
        MAX(CASE WHEN json_extract(s.modality_counts, '$.reading') > 0 THEN 1 ELSE 0 END) AS used_reading,
        -- Listening: sessions containing listening drills
        MAX(CASE WHEN json_extract(s.modality_counts, '$.listening') > 0 THEN 1 ELSE 0 END) AS used_listening,
        -- Speaking: speaking session type
        MAX(CASE WHEN s.session_type = 'speaking' THEN 1 ELSE 0 END) AS used_speaking,
        -- IME: sessions containing IME drills
        MAX(CASE WHEN json_extract(s.modality_counts, '$.ime') > 0 THEN 1 ELSE 0 END) AS used_ime
    FROM session_log s
    WHERE s.started_at >= datetime('now', '-7 days')
      AND s.items_completed > 0
    GROUP BY s.user_id
)
SELECT
    COUNT(*) AS wau,
    SUM(f.used_reading) AS reading_users,
    ROUND(100.0 * SUM(f.used_reading) / COUNT(*), 1) AS reading_pct,
    SUM(f.used_listening) AS listening_users,
    ROUND(100.0 * SUM(f.used_listening) / COUNT(*), 1) AS listening_pct,
    SUM(f.used_speaking) AS speaking_users,
    ROUND(100.0 * SUM(f.used_speaking) / COUNT(*), 1) AS speaking_pct,
    SUM(f.used_ime) AS ime_users,
    ROUND(100.0 * SUM(f.used_ime) / COUNT(*), 1) AS ime_pct
FROM active_users a
LEFT JOIN feature_usage f ON f.user_id = a.user_id;
```

### 6. Drill Accuracy by Type (last 30 days)

```sql
-- Accuracy breakdown by drill type.
-- Identifies which drill types are too easy or too hard.
-- Uses error_log to count misses and session_log for totals.
SELECT
    e.drill_type,
    COUNT(*) AS total_errors,
    -- Get total attempts from session data for context
    (SELECT SUM(s2.items_completed)
     FROM session_log s2
     WHERE s2.started_at >= datetime('now', '-30 days')
    ) AS total_items_all_types,
    -- Error rate approximation per drill type
    ROUND(100.0 * COUNT(*) / NULLIF(
        (SELECT SUM(s3.items_completed)
         FROM session_log s3
         WHERE s3.started_at >= datetime('now', '-30 days')), 0
    ), 1) AS error_share_pct
FROM error_log e
WHERE e.created_at >= datetime('now', '-30 days')
GROUP BY e.drill_type
ORDER BY total_errors DESC;

-- Alternatively, per-item accuracy from the progress table:
SELECT
    p.modality,
    COUNT(*) AS items_tracked,
    ROUND(AVG(CASE WHEN p.total_attempts > 0
        THEN 100.0 * p.total_correct / p.total_attempts
        ELSE NULL END), 1) AS avg_accuracy_pct,
    SUM(CASE WHEN p.mastery_stage IN ('mature', 'intuitive') THEN 1 ELSE 0 END) AS mastered,
    SUM(CASE WHEN p.historically_weak = 1 THEN 1 ELSE 0 END) AS historically_weak
FROM progress p
WHERE p.total_attempts > 0
GROUP BY p.modality;
```

### 7. Churn Risk Signals (users likely to cancel)

```sql
-- Users showing churn risk signals.
-- Flags: declining session frequency, low accuracy, long gaps.
-- Run weekly; reach out to at-risk paid users.
WITH user_recent AS (
    SELECT
        s.user_id,
        COUNT(*) AS sessions_last_14d,
        MAX(s.started_at) AS last_session,
        AVG(s.items_correct * 1.0 / NULLIF(s.items_completed, 0)) AS avg_accuracy,
        SUM(s.early_exit) AS early_exits,
        SUM(s.boredom_flags) AS boredom_total
    FROM session_log s
    WHERE s.started_at >= datetime('now', '-14 days')
    GROUP BY s.user_id
),
user_prior AS (
    SELECT
        s.user_id,
        COUNT(*) AS sessions_prior_14d
    FROM session_log s
    WHERE s.started_at >= datetime('now', '-28 days')
      AND s.started_at < datetime('now', '-14 days')
    GROUP BY s.user_id
)
SELECT
    u.id AS user_id,
    u.email,
    u.plan,
    COALESCE(ur.sessions_last_14d, 0) AS sessions_last_14d,
    COALESCE(up.sessions_prior_14d, 0) AS sessions_prior_14d,
    ROUND(COALESCE(ur.avg_accuracy, 0) * 100, 1) AS accuracy_pct,
    COALESCE(ur.early_exits, 0) AS early_exits,
    COALESCE(ur.boredom_total, 0) AS boredom_flags,
    ur.last_session,
    ROUND(julianday('now') - julianday(COALESCE(ur.last_session, u.created_at)), 1) AS days_since_active,
    -- Risk score: higher = more at risk
    CASE
        WHEN COALESCE(ur.sessions_last_14d, 0) = 0 THEN 'HIGH'
        WHEN COALESCE(ur.sessions_last_14d, 0) < COALESCE(up.sessions_prior_14d, 0) * 0.5 THEN 'HIGH'
        WHEN COALESCE(ur.avg_accuracy, 0) < 0.55 THEN 'MEDIUM'
        WHEN COALESCE(ur.early_exits, 0) >= 3 THEN 'MEDIUM'
        WHEN COALESCE(ur.boredom_total, 0) >= 3 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS churn_risk
FROM users u
LEFT JOIN user_recent ur ON ur.user_id = u.id
LEFT JOIN user_prior up ON up.user_id = u.id
WHERE u.plan = 'paid'
  AND u.cancelled_at IS NULL
ORDER BY
    CASE
        WHEN COALESCE(ur.sessions_last_14d, 0) = 0 THEN 1
        WHEN COALESCE(ur.sessions_last_14d, 0) < COALESCE(up.sessions_prior_14d, 0) * 0.5 THEN 2
        ELSE 3
    END,
    days_since_active DESC;
```

### 8. Cohort Retention (weekly signup cohorts)

```sql
-- Weekly cohort retention table.
-- Shows what % of each signup cohort was active in weeks 1, 2, 4, 8, 12.
WITH cohorts AS (
    SELECT
        u.id AS user_id,
        date(u.created_at, 'weekday 1', '-7 days') AS cohort_start,
        strftime('%Y-W%W', u.created_at) AS cohort_label
    FROM users u
    WHERE u.created_at >= datetime('now', '-90 days')
),
activity AS (
    SELECT
        c.user_id,
        c.cohort_label,
        c.cohort_start,
        -- Week number relative to signup
        CAST((julianday(date(s.started_at)) - julianday(c.cohort_start)) / 7 AS INTEGER) AS week_number
    FROM cohorts c
    JOIN session_log s ON s.user_id = c.user_id
    WHERE s.items_completed > 0
)
SELECT
    a.cohort_label,
    COUNT(DISTINCT CASE WHEN week_number = 0 THEN a.user_id END) AS week_0,
    COUNT(DISTINCT CASE WHEN week_number = 1 THEN a.user_id END) AS week_1,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN week_number = 1 THEN a.user_id END)
        / NULLIF(COUNT(DISTINCT CASE WHEN week_number = 0 THEN a.user_id END), 0), 1) AS w1_pct,
    COUNT(DISTINCT CASE WHEN week_number = 2 THEN a.user_id END) AS week_2,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN week_number = 2 THEN a.user_id END)
        / NULLIF(COUNT(DISTINCT CASE WHEN week_number = 0 THEN a.user_id END), 0), 1) AS w2_pct,
    COUNT(DISTINCT CASE WHEN week_number BETWEEN 3 AND 4 THEN a.user_id END) AS week_4,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN week_number BETWEEN 3 AND 4 THEN a.user_id END)
        / NULLIF(COUNT(DISTINCT CASE WHEN week_number = 0 THEN a.user_id END), 0), 1) AS w4_pct,
    COUNT(DISTINCT CASE WHEN week_number BETWEEN 7 AND 8 THEN a.user_id END) AS week_8,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN week_number BETWEEN 7 AND 8 THEN a.user_id END)
        / NULLIF(COUNT(DISTINCT CASE WHEN week_number = 0 THEN a.user_id END), 0), 1) AS w8_pct,
    COUNT(DISTINCT CASE WHEN week_number BETWEEN 11 AND 12 THEN a.user_id END) AS week_12,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN week_number BETWEEN 11 AND 12 THEN a.user_id END)
        / NULLIF(COUNT(DISTINCT CASE WHEN week_number = 0 THEN a.user_id END), 0), 1) AS w12_pct
FROM activity a
GROUP BY a.cohort_label
ORDER BY a.cohort_label;
```

### 9. Revenue by Month

```sql
-- Monthly revenue summary.
-- Tracks new MRR, churned MRR, and net MRR movement.
WITH monthly_subs AS (
    SELECT
        strftime('%Y-%m', u.created_at) AS month,
        'new' AS type,
        COUNT(*) AS users,
        COUNT(*) * 14.99 AS mrr  -- $14.99/month per user
    FROM users u
    WHERE u.plan = 'paid'
    GROUP BY month

    UNION ALL

    SELECT
        strftime('%Y-%m', u.cancelled_at) AS month,
        'churned' AS type,
        COUNT(*) AS users,
        COUNT(*) * -12 AS mrr
    FROM users u
    WHERE u.cancelled_at IS NOT NULL
    GROUP BY month
)
SELECT
    month,
    SUM(CASE WHEN type = 'new' THEN users ELSE 0 END) AS new_paid,
    SUM(CASE WHEN type = 'churned' THEN users ELSE 0 END) AS churned,
    SUM(CASE WHEN type = 'new' THEN mrr ELSE 0 END) AS new_mrr,
    SUM(CASE WHEN type = 'churned' THEN mrr ELSE 0 END) AS churned_mrr,
    SUM(mrr) AS net_mrr_change
FROM monthly_subs
GROUP BY month
ORDER BY month;

-- Running MRR total:
SELECT
    month,
    net_mrr_change,
    SUM(net_mrr_change) OVER (ORDER BY month) AS running_mrr
FROM (
    SELECT
        strftime('%Y-%m', created_at) AS month,
        SUM(CASE
            WHEN plan = 'paid' AND cancelled_at IS NULL THEN 12
            WHEN cancelled_at IS NOT NULL THEN -12
            ELSE 0
        END) AS net_mrr_change
    FROM users
    GROUP BY month
)
ORDER BY month;
```

### 10. Most-Failed Vocabulary Items (last 30 days)

```sql
-- Top 30 most-failed vocabulary items in the last 30 days.
-- These are candidates for: content revision, hint addition,
-- easier scaffolding, or extra review scheduling.
SELECT
    ci.id AS item_id,
    ci.hanzi,
    ci.pinyin,
    ci.english,
    ci.hsk_level,
    ci.item_type,
    COUNT(e.id) AS error_count,
    -- Get the dominant error type for this item
    (SELECT e2.error_type
     FROM error_log e2
     WHERE e2.content_item_id = ci.id
       AND e2.created_at >= datetime('now', '-30 days')
     GROUP BY e2.error_type
     ORDER BY COUNT(*) DESC
     LIMIT 1
    ) AS primary_error_type,
    -- Get the dominant drill type where errors occur
    (SELECT e3.drill_type
     FROM error_log e3
     WHERE e3.content_item_id = ci.id
       AND e3.created_at >= datetime('now', '-30 days')
     GROUP BY e3.drill_type
     ORDER BY COUNT(*) DESC
     LIMIT 1
    ) AS hardest_drill_type,
    -- Overall accuracy for this item from progress table
    ROUND(100.0 * COALESCE(
        (SELECT SUM(p.total_correct) * 1.0 / NULLIF(SUM(p.total_attempts), 0)
         FROM progress p
         WHERE p.content_item_id = ci.id), 0
    ), 1) AS overall_accuracy_pct,
    -- Is it historically weak?
    MAX(COALESCE(
        (SELECT p2.historically_weak
         FROM progress p2
         WHERE p2.content_item_id = ci.id
         LIMIT 1), 0
    )) AS historically_weak
FROM error_log e
JOIN content_item ci ON ci.id = e.content_item_id
WHERE e.created_at >= datetime('now', '-30 days')
GROUP BY ci.id
ORDER BY error_count DESC
LIMIT 30;
```

---

## Appendix: Metrics Glossary

| Term | Definition |
|------|-----------|
| **MRR** | Monthly Recurring Revenue. Sum of all active subscription amounts. |
| **ARPU** | Average Revenue Per User. MRR / paying users. For this app, $14.99 flat until tiers are added. |
| **LTV** | Lifetime Value. Total revenue expected from a user over their entire subscription. |
| **CAC** | Customer Acquisition Cost. Total spend to acquire one paying user. |
| **WASU** | Weekly Active Studying Users. The north star metric. |
| **WAU** | Weekly Active Users. Broader than WASU -- includes any app interaction. |
| **Gross churn** | Percentage of paying users who cancel in a period, ignoring new additions. |
| **Net revenue churn** | MRR lost to cancellations minus MRR gained from expansion, as a percentage of starting MRR. |
| **Activation** | A new user who completes 3+ sessions in their first 14 days. |
| **Cleanup loop** | The reader-to-drill pipeline: user encounters unknown word in reading, looks it up, then drills it in a subsequent session. |
| **Cohort** | A group of users who share a common start date (signup week). Used to compare retention across time. |
