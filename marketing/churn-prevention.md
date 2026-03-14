# Churn Prevention & Cancellation Playbook

This is the complete playbook for preventing churn and handling cancellations. Every email, flow, and offer described here follows the brand voice defined in `positioning.md`: direct, grounded, calm, respectful. No guilt. No dark patterns. No manipulative urgency.

Price: Free (HSK 1-2), $14.99/month full access. Independent team.

Last updated: 2026-02-17

---

## Churn Signal Detection

### Early Warning Signals

| # | Signal | Threshold | Risk Level | Intervention |
|---|--------|-----------|------------|--------------|
| 1 | Session frequency drop | 30%+ decline over 2 weeks vs. user's trailing 30-day average | Low | In-app: surface a shorter session option ("10-minute focused session available"). No email. |
| 2 | 5+ day gap | No session for 5 consecutive days (for users who averaged 4+ sessions/week) | Medium | Email: gentle check-in with a specific drill suggestion based on their last weak area. |
| 3 | 10+ day gap | No session for 10 consecutive days | High | Email: direct acknowledgment of the gap + offer to adjust session length or focus. |
| 4 | 14+ day gap | No session for 14 consecutive days | Critical | Email: honest "your SRS intervals are stretching" message + pause option. |
| 5 | Session duration drop | Average session under 5 minutes for 2+ weeks (for users who previously averaged 15+ minutes) | Medium | In-app: offer a restructured session — "Your tones need 8 minutes. Want to focus there?" |
| 6 | Accuracy plateau | No accuracy improvement across any skill for 30+ days despite regular sessions | Medium | Email: specific diagnostic insight — "Your listening has been at 67% for a month. Here's what's happening." |
| 7 | Single drill type usage | 80%+ of drills are one type for 3+ weeks | Low | In-app: suggest a different drill type targeting the same content — "Try audio-to-hanzi instead of recognition for these words." |
| 8 | No reading or listening | Zero graded reader or listening sessions for 30+ days despite active drilling | Low | In-app: surface a reading passage at their level — "A new passage matches your HSK 3 vocabulary." |
| 9 | Visited cancel page | User loaded the cancellation page but did not complete | Critical | Email within 2 hours: address the most common cancellation reasons directly. No discount. Ask what's wrong. |
| 10 | Support complaint | User submitted a bug report or complaint via email | High | Personal reply from the team within 24 hours. Fix the issue or explain the timeline. Follow up when resolved. |

### Composite Churn Risk Score

Calculate a 0-100 score weekly for each paying subscriber. Higher = more likely to churn.

**Component weights:**

| Component | Weight | Scoring |
|-----------|--------|---------|
| Days since last session | 30% | 0 pts (today) to 30 pts (14+ days) — linear scale, capped at 14 days |
| Session frequency trend (2-week vs. 4-week avg) | 20% | 0 pts (stable/increasing) to 20 pts (80%+ decline) |
| Session duration trend | 10% | 0 pts (stable/increasing) to 10 pts (dropped below 5 min avg) |
| Accuracy trend (30-day) | 10% | 0 pts (improving) to 10 pts (declining or flat for 30+ days) |
| Drill type diversity (past 2 weeks) | 5% | 0 pts (3+ types used) to 5 pts (1 type only) |
| Cancel page visit (past 30 days) | 15% | 0 pts (no visit) or 15 pts (visited) |
| Support complaint (past 30 days) | 10% | 0 pts (none) or 10 pts (complaint filed) |

**Action thresholds:**

| Score | Risk Level | Action |
|-------|------------|--------|
| 0-25 | Low | Monitor. In-app nudges only. |
| 26-50 | Medium | Trigger re-engagement email sequence. |
| 51-75 | High | Trigger personal outreach email. Offer session restructuring. |
| 76-100 | Critical | Trigger save email with pause offer. Flag for the team's personal review. |

---

## Intervention Playbook

### Low Risk (Score 0-25)

**Intervention:** In-app suggestions only. No email. Respect their rhythm — some users naturally have variable weeks. Surface shorter sessions or different drill types when patterns shift.

**Email 1 — Skill Spotlight (sent only if drill diversity is low)**

Subject: Your tones are 2 levels behind your vocabulary

Body:

> Hi [Name],
>
> Your vocabulary recognition is tracking at HSK 3, but your tone accuracy is still at HSK 1. That gap will slow everything else down as you advance.
>
> Your next session has tone pair drills queued. Ten minutes would make a measurable difference.
>
> — Aelu

**Email 2 — New Content Notice (sent when relevant graded reading matches their level)**

Subject: New HSK 3 reading passage available

Body:

> Hi [Name],
>
> A new graded reading passage just went live at your level. It covers 14 words from your active drill queue — reading them in context will reinforce what you've been drilling.
>
> The passage takes about 6 minutes. Any words you look up will enter your drill queue automatically.
>
> — Aelu

**Email 3 — Progress Snapshot (monthly, for active users)**

Subject: Your February progress

Body:

> Hi [Name],
>
> Here's where you stand as of February 17:
>
> - Vocabulary: HSK 3 (74% readiness)
> - Listening: HSK 2 (89% readiness)
> - Reading: HSK 3 (61% readiness)
> - Tones: HSK 2 (72% readiness)
>
> Your biggest improvement this month: reading accuracy, up 8 points. Your biggest gap: reading is lagging behind your vocabulary — the graded reader will close that faster than drilling alone.
>
> — Aelu

---

### Medium Risk (Score 26-50)

**Intervention:** One email from the sequence below, chosen based on the dominant signal. Maximum one email per week. Never stack multiple emails.

**Email 1 — The Gentle Check-In (triggered by 5-day gap)**

Subject: Quick update on your SRS intervals

Body:

> Hi [Name],
>
> It's been 5 days since your last session. No judgment — life happens.
>
> Here's what's actually going on with your data: you have 23 items approaching their review deadline. If you get to them in the next 2-3 days, your retention stays on track. If not, the algorithm will reschedule them with shorter intervals, which means more reviews later to recover the same ground.
>
> A 10-minute session would cover the most time-sensitive items.
>
> — Aelu

**Email 2 — The Plateau Diagnosis (triggered by accuracy stagnation)**

Subject: Why your listening score hasn't moved

Body:

> Hi [Name],
>
> Your listening accuracy has been at 64-67% for the past month. That's not a failure — it's a signal.
>
> What's likely happening: you've absorbed the vocabulary at this level but your ear hasn't caught up to natural speech speed. This is the most common plateau for HSK 2-3 learners.
>
> What helps: listening drills at 0.75x speed for a week, then stepping back to 1.0x. The app does this automatically if you run a listening-focused session.
>
> If you want to try it, your next session is ready. 15 minutes, listening-heavy.
>
> — Aelu

**Email 3 — The Session Reshape (triggered by duration drop)**

Subject: Shorter sessions are fine — here's how to make them count

Body:

> Hi [Name],
>
> Your sessions have been shorter lately — averaging about 5 minutes over the past two weeks, down from 18. That's enough time to keep your SRS intervals from collapsing, which matters.
>
> To get the most from short sessions: let the app pick the drills. It will prioritize items closest to their review deadline and mix in your weakest skill. Five focused minutes beats fifteen distracted ones.
>
> If your available time has genuinely changed, you can adjust your daily session target in settings. The algorithm adapts to whatever you give it.
>
> — Aelu

---

### High Risk (Score 51-75)

**Intervention:** Personal-tone email from the team. Acknowledge the situation directly. Offer concrete help. If a support complaint is involved, address it specifically.

**Email 1 — The Direct Check-In (triggered by 10-day gap)**

Subject: Checking in — 10 days since your last session

Body:

> Hi [Name],
>
> It's been 10 days. I'm not writing to guilt you — spaced repetition apps that shame you for missing days are the worst part of this category and I refuse to build one.
>
> I'm writing because your data tells me something useful: you were making real progress before the gap. Your vocabulary was tracking toward HSK 4 readiness by April. That timeline shifts by about 2-3 weeks for every week you're away, because intervals reset.
>
> Three options, all fine:
>
> 1. **Come back now.** Your next session is ready — the algorithm has already adjusted for the gap. It will start with shorter intervals to rebuild.
> 2. **Pause your subscription.** If life is busy, pause for 1-3 months. No charge, no penalty. Your data stays exactly where it is. Reply "pause" and I'll set it up.
> 3. **Cancel.** If you're done, the cancellation page is in your account settings. Three clicks, no obstacles.
>
> Whatever you choose is the right call for you right now.
>
> — Aelu

**Email 2 — The Post-Complaint Follow-Up (triggered by support complaint)**

Subject: Following up on your [specific issue]

Body:

> Hi [Name],
>
> You reported [specific issue] on [date]. Here's the status:
>
> [If fixed: "Fixed. It went live on [date]. The issue was [brief explanation]. Sorry it happened."]
>
> [If not yet fixed: "Still working on it. The issue is [brief explanation]. I expect to have it resolved by [date]. I'll email you when it's done."]
>
> If anything else is frustrating, tell me directly. I read every email and I'm the only one building this — your feedback changes the product faster than you'd expect.
>
> — Aelu

**Email 3 — The Honest Assessment (triggered by multiple declining signals)**

Subject: Your Aelu progress — an honest look

Body:

> Hi [Name],
>
> I'm going to be straightforward: your usage data suggests the app isn't working for you right now. Sessions are shorter, less frequent, and your accuracy has been flat.
>
> That could mean a few things:
>
> - **The content isn't matching your needs.** If there's something specific you wish you could practice that isn't available, I want to know. We're a small team — we can adjust.
> - **Your schedule changed.** Totally valid. A pause preserves your data and costs nothing.
> - **The approach isn't clicking.** Some people learn better with tutors, conversation partners, or video courses. That's not a failure — it's a fit question.
>
> If you want to talk through what's not working, reply to this email. I'll respond personally.
>
> — Aelu

---

### Critical Risk (Score 76-100)

**Intervention:** Immediate personal email. Pause offer front and center. If they visited the cancel page, address it directly without pretending you don't know.

**Email 1 — The Cancel Page Follow-Up (triggered within 2 hours of cancel page visit)**

Subject: Before you cancel — a quick question

Body:

> Hi [Name],
>
> I noticed you visited the cancellation page. I'm not going to try to change your mind with a discount or a guilt trip — that's not how this works.
>
> But I would genuinely like to know: what isn't working? Your answer helps me build a better product. One sentence is enough.
>
> If the issue is timing rather than the product itself, you can pause for 1-3 months instead — no charge, your data stays intact, and you pick back up whenever you're ready.
>
> Whatever you decide, thank you for giving the app a real try.
>
> — Aelu

**Email 2 — The 14-Day Gap (triggered by 14+ days of inactivity)**

Subject: Your subscription is still active — here are your options

Body:

> Hi [Name],
>
> It's been two weeks since your last session. Your subscription is still active at $14.99/month, and I don't want you paying for something you're not using.
>
> Your options:
>
> 1. **Come back.** Your data is intact. The algorithm has adjusted intervals for the gap. First session back will be lighter than usual.
> 2. **Pause for 1-3 months.** Free. Your progress is preserved. Reply with how long and I'll set it up immediately.
> 3. **Cancel.** Account Settings → Subscription → Cancel. Three clicks, done.
>
> I'd rather you pause than cancel, and I'd rather you cancel than pay for something unused. No wrong answer here.
>
> — Aelu

**Email 3 — The Final Outreach (7 days after Email 2, if no response and no activity)**

Subject: Last check-in before I stop emailing

Body:

> Hi [Name],
>
> This is my last email about your subscription. I've sent two already and I don't want to become noise in your inbox.
>
> If you want to pause or cancel, you can do either from your account settings anytime. If you come back on your own, your data will be waiting.
>
> If you ever want to talk about what didn't work, I'm at hello@aelu.app. I read everything.
>
> — Aelu

---

## Cancellation Flow Design

Three steps. Maximum three clicks. No dark patterns. No hidden "are you sure?" modals. No guilt copy. No countdown timers. No fake "other users who stayed saw 40% improvement" stats.

### Step 1: Reason Selection

**Page headline:** Cancel your subscription

**Body copy:**

> Your data will be preserved if you ever return. You'll keep access to all HSK 1-2 content on the free tier.
>
> To help me improve the product, would you share why you're leaving?

**Options (radio buttons, one required):**

1. I'm not using the app enough
2. It's too expensive
3. I found a better tool for my needs
4. The content doesn't cover what I need
5. I'm taking a break from studying Mandarin
6. I achieved my learning goal
7. Other reason

**Button:** Continue to cancel

No "Go back to app" button competing for attention. No bright colors on a "stay" option vs. muted colors on "cancel." The continue button is standard, visible, and clearly labeled.

---

### Step 2: Save Offer (varies by reason)

Based on the reason selected in Step 1, show one targeted offer. If the user declines, proceed immediately to Step 3. No second offer. No "are you really sure?"

| Reason | Save Offer | Headline | Body Copy |
|--------|-----------|----------|-----------|
| Not using enough | Pause (1-3 months, free) | Pause instead? | "If the issue is timing, not the product, you can pause for 1, 2, or 3 months. No charge during the pause. Your data and progress stay exactly where they are. Pick back up whenever you're ready." **[Pause for 1 month] [Pause for 2 months] [Pause for 3 months] [No thanks, cancel]** |
| Too expensive | 50% off for 2 months ($7.50/month) | Would $7.50/month work? | "I can offer $7.50/month for the next two months. After that it returns to $14.99/month. If $7.50 still doesn't work, that's fine — HSK 1-2 content remains free forever." **[Accept $7.50/month for 2 months] [No thanks, cancel]** |
| Found better tool | Competitive intel question, no counter-offer | Which tool are you switching to? | "No hard feelings — using the right tool matters more than using this one. If you're willing to share which app or resource you're switching to, it helps me understand where I'm falling short. Totally optional." **[Text field] [Submit and cancel] [Skip and cancel]** |
| Content gap | Roadmap + feedback request | What's missing? | "We're a small team and the content roadmap is directly shaped by user feedback. If you can share what topics, levels, or drill types you wish existed, there's a real chance we'll build them. We can notify you if we add what you need." **[Text field] [Submit and cancel] [Skip and cancel] [Check box: Email me if this content is added]** |
| Taking a break | Pause (1-3 months, free) | Pause instead? | "If you're coming back eventually, a pause keeps your progress intact at no cost. Your SRS intervals freeze — when you return, you pick up where you left off instead of starting recovery drills." **[Pause for 1 month] [Pause for 2 months] [Pause for 3 months] [No thanks, cancel]** |
| Achieved goal | Celebration + testimonial ask | Congratulations — that's the best reason to leave. | "Reaching your goal is the whole point. If you're willing, I'd appreciate a short testimonial about your experience — it helps other learners evaluate the app. Either way, your data stays if you ever want to push to the next HSK level." **[Write a testimonial] [No thanks, cancel]** |
| Other | Free text + optional follow-up | Anything you'd like to share? | "If there's something specific I could fix or build, I'd like to hear it. Totally optional — you can also just cancel." **[Text field] [Submit and cancel] [Skip and cancel]** |

---

### Step 3: Confirmation

**Page headline:** Your subscription has been cancelled.

**Body copy:**

> Your paid access continues through [billing period end date]. After that, you'll have full access to all HSK 1-2 content on the free tier.
>
> Your progress data, drill history, and diagnostics are preserved permanently. If you resubscribe, everything picks up where you left off.
>
> If you change your mind before [billing period end date], you can reactivate from Account Settings with no interruption.
>
> Thank you for using Aelu. I hope the time you spent here moved your Chinese forward.
>
> — Aelu

**Single button:** Return to app

No "resubscribe now" button on the confirmation page. They just cancelled. Respect the decision.

---

## Pause Feature Design

### Why Pause Beats Cancel

The data across SaaS is consistent:

- **Paused users reactivate at 40-60%.** They intended to come back, and the low friction of automatic reactivation converts that intention.
- **Cancelled users reactivate at 10-20%.** The friction of re-entering payment details, remembering the product exists, and re-making the purchase decision kills most return intent.
- **Paused users retain their data context.** When they come back, they see their progress, their diagnostics, their history. That continuity creates re-engagement momentum. A cancelled user who returns sees a cold dashboard.

For a small team with no re-acquisition ad budget, pause is the single highest-leverage retention tool available.

### Pause Options

| Duration | Use Case | Auto-Reactivation |
|----------|----------|-------------------|
| 1 month | Short break, vacation, busy period at work | Yes, with 7-day advance notice |
| 2 months | Extended travel, semester break, new baby | Yes, with 7-day advance notice |
| 3 months | Long hiatus, major life change | Yes, with 7-day advance notice |

**Pause mechanics:**

- Billing stops immediately on pause activation. No prorated charges.
- SRS intervals freeze. Items do not accumulate overdue reviews during the pause.
- All data preserved: drill history, diagnostics, graded reader progress, context notes.
- Free tier access (HSK 1-2) remains available during pause if the user wants to do light practice.
- Auto-reactivation resumes billing at $14.99/month on the scheduled date.
- User can cancel during pause at any time (from account settings).
- User can extend or shorten pause at any time (from account settings).
- User can end pause early and resume immediately (from account settings).

### Pause Emails

**Email 1 — Pause Confirmation (sent immediately)**

Subject: Your subscription is paused

Body:

> Hi [Name],
>
> Your subscription is now paused. Here's what that means:
>
> - **No charges** until your pause ends on [reactivation date].
> - **Your data is frozen.** SRS intervals, drill history, diagnostics, reading progress — all preserved exactly as they are.
> - **HSK 1-2 content is still available** if you want to do light practice during the pause.
> - **Billing resumes automatically** on [reactivation date] at $14.99/month. I'll send you a reminder 7 days before.
>
> You can cancel, extend, shorten, or end your pause anytime from Account Settings.
>
> See you when you're ready.
>
> — Aelu

**Email 2 — Mid-Pause Check-In (sent at the halfway point of the pause)**

Subject: Quick check-in from Aelu

Body:

> Hi [Name],
>
> You're halfway through your [duration] pause. No pressure — just a few things worth knowing:
>
> - Your data is intact. [X] vocabulary items, [Y] drill history entries, diagnostics through HSK [Z].
> - If your schedule has opened up, you can end the pause early from Account Settings and pick up immediately. The algorithm will ease you back in with a recovery session.
> - If you need more time, you can extend the pause from the same page.
>
> Either way, your progress isn't going anywhere.
>
> — Aelu

**Email 3 — 7-Day Reactivation Notice (sent 7 days before pause ends)**

Subject: Your subscription resumes in 7 days

Body:

> Hi [Name],
>
> Your pause ends on [reactivation date]. On that date, billing resumes at $14.99/month and your full access restarts.
>
> What to expect when you come back:
>
> - Your first session will be a recovery session — shorter intervals on items you were drilling before the pause, designed to rebuild retention without overwhelming you.
> - Your diagnostics will update after 3-4 sessions back.
> - Your HSK projections will recalculate based on your new pace.
>
> **If you're not ready to come back:**
> - Extend your pause: Account Settings → Subscription → Extend Pause
> - Cancel instead: Account Settings → Subscription → Cancel
>
> Both options are available right now, no questions asked.
>
> — Aelu

---

## Retention Tactics by User Type

### 1. The Habit Dropper

**Profile:** Had a consistent routine (4-6 sessions/week for 2+ months), then activity dropped to near zero within a 1-2 week window.

**Root cause:** A life event disrupted their routine — new job, travel, illness, family obligation, schedule change. The habit was real but fragile. Once broken, the activation energy to restart feels higher than it actually is.

**Signal:** Sharp session frequency drop (not gradual), no accuracy decline before the drop (they were still performing well when they stopped), and a tenure of 2+ months (proving the habit existed).

**Intervention:** Acknowledge the gap without judgment. Lower the perceived restart barrier by being specific about what their first session back looks like.

**Specific offer:** The "10-minute recovery session" email. Frame the restart as something the algorithm handles — they don't need to figure out where they left off. If inactivity reaches 14+ days, offer a pause.

---

### 2. The Content Exhausted

**Profile:** Has been at the same HSK level for an extended period, drilling the same content. Engagement is declining because they feel like they've seen everything.

**Root cause:** The content at their current level is fully reviewed and they haven't unlocked or engaged with the next tier. Or they've focused heavily on one skill (usually vocabulary) and haven't explored reading, listening, or speaking drills.

**Signal:** High accuracy (80%+) across most drills at their current level, low usage of graded reader or listening features, declining session duration, and comments like "running out of new material."

**Intervention:** Surface underused features — specifically the graded reader, listening passages, and speaking drills. Show them the gap between their vocabulary level and their listening/reading levels, which usually reveals a significant spread they weren't aware of.

**Specific offer:** A personalized "untapped features" email showing their skill balance and specifically pointing to the 15-20 drill types they haven't used. If they've genuinely exhausted their level and the next level's content isn't sufficient, ask what they want and put it on the roadmap.

---

### 3. The Stuck Learner

**Profile:** Sessions are regular but accuracy has been flat for 30+ days. They log in, drill, and see no improvement. Motivation is eroding because the effort feels pointless.

**Root cause:** They've hit a genuine plateau — common at the HSK 2-3 and HSK 4-5 transitions. The material is harder, the intervals are longer, and the progress per session is smaller. Or they're grinding recognition drills when their real bottleneck is listening or production.

**Signal:** Flat accuracy across 30+ days, stable session frequency (they're still trying), and often single-drill-type usage patterns that indicate they're stuck in a comfort zone.

**Intervention:** Diagnose the specific plateau and prescribe a concrete change. This is where the per-skill diagnostics earn their value — show them exactly which skill is the bottleneck and which drill types target it.

**Specific offer:** The "plateau diagnosis" email with a specific 2-week practice plan. "Your vocabulary is HSK 3 but your listening is HSK 2. For the next two weeks, run listening-heavy sessions. Here's what the algorithm will prioritize." Make the path out of the plateau visible and concrete.

---

### 4. The Price Sensitive

**Profile:** Engaged with the product (regular sessions, decent accuracy) but the $14.99/month is a real line item in their budget. They may be a student, early career, or in a country where $14.99 USD is a larger relative cost.

**Root cause:** The value is there but the price-to-budget ratio is high. They like the app but are constantly evaluating whether it's worth it this month.

**Signal:** Regular usage but visits to the cancel page, particularly around billing dates. May also show up as a support email asking about discounts or student pricing.

**Intervention:** Acknowledge that $14.99/month is real money. Do not say "it's less than a coffee a day" — they already know that and it doesn't help. Instead, make the value concrete and specific to their data.

**Specific offer:** The 50% discount ($7.50/month for 2 months) if they reach the cancellation flow. For proactive retention: a billing-date email that shows their specific progress since their last payment — "$14.99 bought you 47 drill sessions, 312 items reviewed, and a 6-point improvement in listening accuracy this month." Let them decide if that's worth it. If it isn't, let them go.

---

### 5. The Competitor Switcher

**Profile:** Found another tool that they believe serves their needs better, or that serves a need we don't cover (conversation practice, video lessons, tutoring).

**Root cause:** Either a genuine gap in our product (we don't offer conversation practice, handwriting, or video instruction) or a perception issue (they didn't discover features that exist). Sometimes they're switching to a complement, not a replacement, and don't realize they can use both.

**Signal:** Often sudden — cancellation with the "found a better tool" reason after steady usage. Sometimes preceded by a decline in usage of our specific features (e.g., they stopped doing listening drills because they found a dedicated listening app).

**Intervention:** No counter-offer. Do not try to match or badmouth the competitor. Ask which tool they're switching to (competitive intel) and wish them well. If they're switching to a complement (iTalki for tutoring, HelloTalk for conversation), mention that pairing works well and they could keep Aelu for drilling.

**Specific offer:** None. Respect the decision. Collect the competitive intelligence. If a pattern emerges (five users switching to the same app for the same reason), that's a product signal, not a retention problem.

---

### 6. The Goal Achiever

**Profile:** Passed their target HSK level, completed their study program, or reached the specific milestone they set out to hit. They're leaving because they succeeded.

**Root cause:** This is the best kind of churn. They got what they came for. The product worked.

**Signal:** High accuracy at their target level, HSK readiness at or above their goal, and cancellation with the "achieved my goal" reason. Often preceded by a period of declining session frequency — they've been winding down naturally.

**Intervention:** Celebrate genuinely. Ask for a testimonial. Mention the next HSK level if relevant, but do not push it. If they're done, they're done.

**Specific offer:** Ask for a testimonial or a brief review. Mention that their data stays if they ever want to push further. That's it. Do not offer discounts to someone who just told you they achieved their goal — it diminishes the achievement.

---

## Save Offer Economics

### When to Offer Discounts

- **Minimum tenure: 3 months.** Users who have been paying for less than 3 months haven't demonstrated enough commitment to warrant a save offer. They're still in the evaluation window. If the product doesn't work for them at 2 months, a discount won't fix that.
- **Maximum frequency: once per 12 months.** A user who accepted a 50% discount 4 months ago does not get another one. The save offer is a one-time bridge, not a permanent pricing tier.
- **Only at the cancellation flow.** Never proactively email discounts to users who haven't indicated they want to leave. Proactive discounts train users to expect them and devalue the product.

### Discount Math

The math is simple:

- A user paying $14.99/month who cancels generates $0/month.
- A user paying $7.50/month (50% off for 2 months) who stays generates $15 over 2 months.
- If even 30% of discount-offered users accept, that's $4.50 in expected revenue per save attempt vs. $0 from letting them go.
- After the 2-month discount period, many users re-anchor at $14.99/month because the habit has been re-established. Industry data suggests 50-70% of discount-retained users stay at full price afterward.

**Break-even analysis:** If the save offer converts at 20%+ acceptance rate, it is profitable. Below 20%, the administrative overhead and brand-dilution cost outweigh the revenue. Track this monthly.

### What to NEVER Offer

- **Free months.** A free month communicates that the product isn't worth paying for. It also creates a perverse incentive: cancel, get free month, cancel again. Pause serves the "I need a break" use case without devaluing the product.
- **Permanent discounts.** No "loyalty pricing" that locks someone in at $7.50/month forever. The product is worth $14.99/month or it isn't. A temporary discount bridges a rough patch. A permanent discount is a pricing mistake.
- **Escalating offers.** Never show a second, better offer after the user declines the first. "We offered you 50% off and you said no, so here's 75% off" teaches users that refusing the first offer is the optimal strategy. One offer, one chance, done.

---

## Involuntary Churn Prevention

Involuntary churn — users who intend to stay but whose payments fail — typically accounts for 20-40% of total churn in subscription businesses. This is the easiest churn to prevent because the user's intent is on your side.

### Failed Payment Retry Schedule

| Attempt | Timing | Action |
|---------|--------|--------|
| 1st retry | Day 1 (payment fails) | Automatic retry by payment processor. Send email #1. |
| 2nd retry | Day 3 | Automatic retry. Send email #2 if first retry failed. |
| 3rd retry | Day 5 | Automatic retry. Send email #3 if second retry failed. |
| 4th retry | Day 7 | Final automatic retry. If this fails, downgrade to free tier. Send final notice. |

**During the retry period:** Full access remains active. Do not restrict features while payment is being resolved. The user is trying to pay — punishing them for a payment processor issue is hostile.

**After Day 7 failure:** Downgrade to free tier (HSK 1-2 access). Do not delete data. Do not lock them out. If they update their payment method, restore full access immediately with no gap.

### Dunning Emails

**Email 1 — Payment Failed, First Notice (Day 1)**

Subject: Your payment didn't go through

Body:

> Hi [Name],
>
> Your $14.99 payment for Aelu failed on [date]. This usually means an expired card, insufficient funds, or a bank hold — nothing on your end to worry about.
>
> We'll retry automatically in 2 days. If you want to update your payment method now:
>
> **[Update Payment Method]** (link to account settings)
>
> Your access is unaffected in the meantime.
>
> — Aelu

**Email 2 — Second Retry Failed (Day 3)**

Subject: Payment still failing — quick update needed

Body:

> Hi [Name],
>
> Your payment has failed twice now. We'll try once more on [Day 5 date] and a final time on [Day 7 date].
>
> The most common fix: update your card in Account Settings. Takes 30 seconds.
>
> **[Update Payment Method]**
>
> Your full access continues while we sort this out. If there's an issue I can help with, reply to this email.
>
> — Aelu

**Email 3 — Final Warning (Day 5)**

Subject: Last payment attempt in 2 days

Body:

> Hi [Name],
>
> Your payment has failed three times. We'll make one final attempt on [Day 7 date]. If it doesn't go through, your account will move to the free tier (HSK 1-2 access). Your data and progress will be fully preserved.
>
> To keep your full access active, update your payment method:
>
> **[Update Payment Method]**
>
> If you update your card after the downgrade, full access restores instantly. Nothing is lost either way.
>
> — Aelu

### Card Expiration Proactive Email

Sent 30 days before a stored card's expiration date. This one email prevents a significant percentage of involuntary churn.

**Subject:** Your card on file expires next month

**Body:**

> Hi [Name],
>
> The card ending in [last 4 digits] expires on [expiration date]. Your next billing date is [billing date].
>
> If you've already received a replacement card with the same number, most banks update this automatically and no action is needed. If your card number changed, you can update it here:
>
> **[Update Payment Method]**
>
> Takes 30 seconds. Prevents any interruption to your access.
>
> — Aelu

---

## Churn Metrics & Reporting

### Monthly Churn Report Template

Generate this report on the 1st of each month, covering the prior calendar month.

**Section 1: Headline Metrics**

| Metric | Value | MoM Change | Target |
|--------|-------|------------|--------|
| Gross churn rate | [X]% | [+/-]% | < 5% |
| Net churn rate (gross minus reactivations) | [X]% | [+/-]% | < 3% |
| Voluntary churn rate | [X]% | [+/-]% | — |
| Involuntary churn rate | [X]% | [+/-]% | < 1% |
| Total subscribers lost | [N] | [+/-N] | — |
| Total subscribers reactivated | [N] | [+/-N] | — |
| MRR lost to churn | $[X] | [+/-]$[X] | — |
| MRR recovered (reactivations) | $[X] | [+/-]$[X] | — |
| Net MRR impact | $[X] | [+/-]$[X] | — |

**Section 2: Churn by Reason**

| Reason | Count | % of Total | MoM Trend |
|--------|-------|-----------|-----------|
| Not using enough | [N] | [X]% | [arrow] |
| Too expensive | [N] | [X]% | [arrow] |
| Found better tool | [N] | [X]% | [arrow] |
| Content gap | [N] | [X]% | [arrow] |
| Taking a break | [N] | [X]% | [arrow] |
| Achieved goal | [N] | [X]% | [arrow] |
| Other | [N] | [X]% | [arrow] |
| Payment failed (involuntary) | [N] | [X]% | [arrow] |

**Section 3: Save Offer Performance**

| Offer Type | Times Shown | Accepted | Acceptance Rate | Revenue Saved |
|------------|-------------|----------|-----------------|---------------|
| Pause (not using enough) | [N] | [N] | [X]% | $[X] |
| Pause (taking a break) | [N] | [N] | [X]% | $[X] |
| 50% discount | [N] | [N] | [X]% | $[X] |
| Content feedback | [N] | [N] | [X]% | N/A |
| Testimonial ask | [N] | [N] | [X]% | N/A |

**Section 4: Pause & Reactivation**

| Metric | Value |
|--------|-------|
| Active pauses (end of month) | [N] |
| Pauses started this month | [N] |
| Pauses ended → reactivated | [N] |
| Pauses ended → cancelled | [N] |
| Pause→reactivation rate (all time) | [X]% |

**Section 5: Cohort Health**

| Cohort (signup month) | Subscribers | Churned This Month | Cohort Churn Rate | Cumulative Retention |
|----------------------|-------------|--------------------|--------------------|---------------------|
| [Month -6] | [N] | [N] | [X]% | [X]% |
| [Month -5] | [N] | [N] | [X]% | [X]% |
| [Month -4] | [N] | [N] | [X]% | [X]% |
| [Month -3] | [N] | [N] | [X]% | [X]% |
| [Month -2] | [N] | [N] | [X]% | [X]% |
| [Month -1] | [N] | [N] | [X]% | [X]% |

**Section 6: Churned User Profile**

| Metric | Value |
|--------|-------|
| Average tenure of churned users | [X] months |
| Median tenure of churned users | [X] months |
| Average sessions before churn | [N] |
| Most common last HSK level | HSK [X] |
| Most common churn reason | [reason] |

### Quarterly Review Questions

Run this review every quarter. These questions force strategic thinking beyond the monthly numbers.

1. **Which churn reason is growing fastest, and what is the product response?** If "content gap" is trending up, that's a roadmap signal. If "too expensive" is trending up, evaluate whether the value delivery has declined or whether the user mix is shifting.

2. **What is the average tenure of churned users, and is it increasing?** Increasing average tenure means you're retaining users longer before they leave — the product is getting stickier even if the churn rate is flat. Decreasing average tenure means newer users are leaving faster — an onboarding or expectation-setting problem.

3. **What percentage of churn is involuntary, and is the dunning sequence improving it?** Involuntary churn above 1.5% of total subscribers means the dunning emails or payment retry schedule need work. This is mechanical — fix it with better emails and card update prompts.

4. **Which save offer has the highest acceptance rate, and which should be retired?** If the pause offer converts at 55% but the 50% discount converts at 12%, consider whether the discount is worth offering or whether a pause-only approach is simpler and equally effective.

5. **Are reactivated users retaining long-term, or churning again within 60 days?** If 40% of reactivated users churn again within 2 months, the reactivation is a delay, not a save. Investigate whether the underlying reason for churn was addressed or just postponed. Adjust intervention tactics accordingly.