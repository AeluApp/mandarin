# Lifecycle Strategy — Aelu

Master lifecycle strategy governing how users move from first awareness through long-term retention. All tactics, benchmarks, and automation rules in this document. If a lifecycle decision contradicts something here, this document wins.

Last updated: 2026-02-17

---

## User Journey Map

### Stage 1: Awareness

**User mindset:** "I need a better way to study Chinese." They are searching Reddit, watching YouTube comparisons, reading blog posts about HSK prep, or scrolling past a social media post. They do not know Aelu exists yet.

**Key actions:**
- Encounter Aelu through content, community, or search
- Click through to landing page or app store listing
- Spend 15-90 seconds forming a first impression

**Success metric:** Landing page visit (unique visitor)

**Drop-off risks:**
- Ad or post does not differentiate from Duolingo/HelloChinese
- Landing page loads slowly on mobile
- Hero copy is too generic ("learn Chinese faster")

**Our response:**
- Lead with the cleanup loop in all top-of-funnel content — it is the most differentiating concept
- Landing page loads in under 2 seconds; hero is three elements only (tagline, one-sentence value prop, pricing)
- Every piece of awareness content includes one specific, verifiable claim (27 drill types, FSRS algorithm, per-skill diagnostics)

**Conversion benchmark:** 2-5% of awareness impressions click through to landing page (varies by channel: Reddit organic 3-7%, paid social 1-3%, SEO 4-8%)

**Timeline:** Ongoing; peak activity during launch window and around HSK exam registration periods (January, May, September)

**Tactics:**
1. Reddit value posts in r/ChineseLanguage, r/LearnChinese, r/MandarinChinese — study tips with subtle product mention
2. SEO blog posts targeting "HSK [level] study plan," "Anki alternatives for Chinese," "how to improve Chinese listening"
3. YouTube comparisons and walkthroughs showing the cleanup loop in action
4. Hacker News Show HN post (solo developer angle, FSRS algorithm, zero AI tokens)
5. Product Hunt launch with "honest diagnostics" positioning

---

### Stage 2: Consideration

**User mindset:** "This looks interesting — is it actually better than what I'm using?" They are on the landing page, reading feature descriptions, looking at the comparison section, checking the price. They may visit 2-3 times before deciding.

**Key actions:**
- Read landing page past the fold (scroll 50%+)
- Visit pricing section
- Read comparison page (vs. Anki, vs. Duolingo)
- Check Reddit or forums for mentions and reviews

**Success metric:** Scroll depth 75%+ and pricing section viewed

**Drop-off risks:**
- Cannot tell how this differs from HelloChinese or Hack Chinese
- Price seems high relative to free alternatives (Anki, Duolingo)
- No social proof (reviews, testimonials, user counts)
- Landing page does not show the product in action

**Our response:**
- Comparison section on landing page with honest, specific differentiators
- Product screenshots or short GIF demos of the cleanup loop, diagnostics dashboard, and drill variety
- "Free for HSK 1-2, no time limit" prominently displayed — removes price as a barrier to trying
- Early user testimonials once available; until then, lean on the founder-user story

**Conversion benchmark:** 15-25% of landing page visitors who scroll 75%+ will proceed to signup

**Timeline:** 1-5 days from first visit; average 2.3 visits before signup

**Tactics:**
1. Landing page comparison table: Aelu vs. Anki vs. Duolingo vs. HelloChinese vs. Hack Chinese
2. 90-second product demo video showing one cleanup loop cycle (read, tap, drill, read again)
3. "Free for HSK 1-2" messaging in three locations on landing page (hero, mid-page, pricing section)
4. FAQ section addressing top objections: "Is it better than Anki?", "What if I don't use it enough?", "Does it work offline?"
5. Founder story section: "I built this for my own Mandarin study" — credibility through use

---

### Stage 3: Signup

**User mindset:** "I'll try it — it's free." They have decided to test the product. The barrier is low (free tier, no credit card). Their primary concern is time investment, not money.

**Key actions:**
- Click signup button
- Create account (email + password, or OAuth)
- Land on post-signup screen

**Success metric:** Account created

**Drop-off risks:**
- Signup form asks for too much information
- OAuth fails or email verification is slow
- Post-signup screen is confusing — user does not know what to do next
- User signs up on mobile but the web app is not mobile-optimized

**Our response:**
- Signup requires only email and password. No name, no phone, no HSK level questionnaire at signup. The system assesses level through the first session.
- Post-signup screen has one CTA: "Start your first session." Nothing else competing for attention.
- Welcome email (Sequence 1, Email 1) sends immediately with clear first-session instructions.
- Mobile web is fully functional from day one.

**Conversion benchmark:** 30-45% of landing page visitors who view pricing will create an account. 60-75% of those who click the signup button will complete registration.

**Timeline:** Same session as consideration, or within 24 hours of last landing page visit

**Tactics:**
1. One-step signup: email + password only, no multi-page onboarding flow
2. Immediate post-signup redirect to first session (not a dashboard, not a settings page)
3. Welcome email within 60 seconds of signup with "Your first session takes 10 minutes"
4. No HSK level self-assessment quiz — the system determines level through adaptive first session
5. Progress bar or step indicator: "Step 1 of 1: Start your first session"

---

### Stage 4: First Session

**User mindset:** "Show me this is worth my time." They are skeptical but willing. They will give the app 5-10 minutes. If the first session is confusing, boring, or feels like every other app, they leave and do not return.

**Key actions:**
- Start first session
- Complete first session (5-15 minutes)
- See initial results (baseline assessment data)

**Success metric:** First session completed (all drills in the initial assessment set answered)

**Drop-off risks:**
- First session feels too easy (experienced learner doing HSK 1 basics)
- First session feels too hard (true beginner overwhelmed by tones)
- Instructions are unclear — user does not understand what to do
- Session takes too long (over 15 minutes) and user abandons mid-session
- User expected flashcards only and is confused by drill variety

**Our response:**
- First session is adaptive: starts at HSK 1 baseline but escalates quickly if answers are correct
- Session length is capped at 12 minutes for the first session; user can extend if desired
- Each drill type includes a brief, one-line instruction on first encounter ("Listen to the audio and select the matching character")
- Post-session summary shows baseline scores across vocabulary, listening, and tones — immediate value from honest data
- "First session completed" milestone email (Sequence 8, Milestone 1) reinforces the value and suggests a second session within 24 hours

**Conversion benchmark:** 55-70% of signups will start their first session within 48 hours. 75-85% of those who start will complete it.

**Timeline:** Within 48 hours of signup (target: same session as signup)

**Tactics:**
1. Adaptive difficulty in first session — no forcing experienced learners through "nihao" for five minutes
2. First-session cap at 12 minutes with clear "session complete" signal
3. Post-session results screen showing per-skill baseline: "Your vocabulary: HSK 1. Your tones: HSK 1. Your listening: not yet assessed."
4. Milestone email within 1 hour of first session completion
5. If no session within 24 hours of signup, trigger Activation Nudge sequence (Sequence 2)

---

### Stage 5: Activation

**User mindset:** "This is actually useful — I can feel it working." They have moved past curiosity into genuine engagement. They are starting to understand the system and seeing how adaptive drilling differs from static flashcards.

**Key actions:**
- Complete 3+ sessions in first 7 days
- Use 2+ drill types
- Return for a second session within 48 hours of the first

**Success metric:** Activated = 3+ sessions in first 7 days with 2+ drill types used. (See Activation Definition section below for full rationale.)

**Drop-off risks:**
- User completes one session but does not return — no habit formed
- User only does vocabulary flashcards and misses the drill variety
- User does not discover the graded reader or cleanup loop
- Session scheduling is not part of their daily routine

**Our response:**
- Onboarding emails (Sequence 1) introduce features progressively: listening drills on day 2, cleanup loop on day 10
- Second session is suggested within 24 hours via milestone email and in-app prompt
- Session variety is enforced by the system: the second session includes different drill types than the first
- If user has not completed 2 sessions by day 3, a targeted email nudges them with a specific 5-minute session prompt

**Conversion benchmark:** 40-55% of users who complete their first session will activate (3+ sessions in 7 days). This is the most critical conversion in the entire funnel.

**Timeline:** Days 1-7 after signup

**Tactics:**
1. Onboarding email sequence paced to introduce one new feature per email
2. In-app suggestion after first session: "Come back tomorrow — your first review is scheduled"
3. System forces drill type variety in sessions 2 and 3 (not all vocabulary flashcards)
4. Day 3 email if under 2 sessions: "Your first session gave us baseline data. Your second session is where the system starts adapting."
5. Day 7 progress email with per-skill breakdown — shows the user what the system learned about them

---

### Stage 6: Habit Formation

**User mindset:** "This is part of my routine now." They study 3-5 times per week. They have a preferred time (usually evening). They check their diagnostics. They notice when they miss a day.

**Key actions:**
- Maintain 3+ sessions per week for 3+ consecutive weeks
- Use the graded reader at least once
- Check diagnostics at least once
- Develop a consistent session time pattern

**Success metric:** 3+ sessions/week for 3 consecutive weeks (weeks 2-4 after signup)

**Drop-off risks:**
- Life disruption breaks the routine (travel, illness, work deadline)
- Progress feels slow — the "intermediate plateau" hits around HSK 2-3
- User gets bored with the same content level (needs to see HSK 2 content unlocking)
- Competing apps or methods pull attention

**Our response:**
- Weekly progress digest (Sequence 9) arrives every Monday with session count, accuracy, and skill breakdown
- If sessions drop below 2 in a week after a period of 3+, a soft re-engagement email (Sequence 5, Email 1) sends value-first content
- Graded reader is surfaced in Email 6 (day 10) of onboarding — the cleanup loop is the strongest habit reinforcer
- Diagnostics page shows concrete progress over time; even small improvements are visible

**Conversion benchmark:** 60-70% of activated users will form a habit (3+ sessions/week for 3 weeks). 30-40% of all signups reach this stage.

**Timeline:** Weeks 2-4 after signup

**Tactics:**
1. Weekly progress digest with accuracy-by-skill breakdown (Monday delivery)
2. Monthly progress report with trend data (1st of each month)
3. Feature discovery email for cleanup loop at day 10 — this is the habit-locking feature
4. In-app "suggested next session" based on SRS scheduling — shows how many items are due
5. Adaptive day profiles: 10-minute sessions for busy days, 30-minute sessions for weekends — the system adapts to available time

---

### Stage 7: Free-to-Paid Conversion

**User mindset:** "I've outgrown the free tier. HSK 3 content is locked. Is this worth $14.99/month?" They have demonstrated commitment through weeks of consistent study. The upgrade ask comes at peak demonstrated value, not at signup.

**Key actions:**
- Reach 80%+ of HSK 2 vocabulary at 75%+ accuracy (the natural boundary trigger)
- View upgrade/pricing page
- Enter payment information
- Complete subscription

**Success metric:** Paid subscription started

**Drop-off risks:**
- User is not convinced $14.99/month is worth it relative to free alternatives
- User does not feel ready for HSK 3 content yet
- Payment friction (too many steps, no preferred payment method)
- User intended to upgrade but "later" becomes "never"

**Our response:**
- Upgrade sequence (Sequence 3) triggers only when user hits the HSK 2/3 boundary — not before
- Sequence shows what HSK 3 includes (600 new words, complex grammar, multi-paragraph reading)
- Value framing: $0.50/day, less than 15 minutes of iTalki tutoring
- 20% discount offer ($12/month for 3 months) as final email after 21 days if user has not converted
- One-step payment with Stripe. No annual upsell during checkout. No hidden tiers.

**Conversion benchmark:** 5-12% of all free users convert to paid. 15-25% of activated free users convert. 20-35% of users who hit the HSK 2/3 boundary convert. See Free-to-Paid Conversion Strategy section for full detail.

**Timeline:** Typically 4-12 weeks after signup, depending on study pace

**Tactics:**
1. Natural paywall at HSK 2/3 boundary — the content limit aligns with demonstrated commitment
2. Upgrade email sequence: milestone celebration, feature preview, value framing, objection handling, discount offer
3. In-app "What's in HSK 3" preview showing locked content the user will encounter next
4. 30-day money-back guarantee — removes risk
5. Cancel-anytime messaging prominent during checkout

---

### Stage 8: Paid Retention

**User mindset:** "This is my Chinese study system. It's worth the $14.99." They are an established paid user. Their concern shifts from "is this worth it?" to "am I making progress?" Retention depends on visible, honest progress.

**Key actions:**
- Maintain 3+ sessions per week
- Engage with diagnostics and HSK projection
- Use multiple features (drills, graded reader, listening, speaking)
- Progress through HSK levels (visible advancement)

**Success metric:** Paid subscription renewal (monthly). Secondary: 4+ sessions/week average.

**Drop-off risks:**
- Plateau: progress feels stagnant, especially at HSK 3-4 boundary
- Feature fatigue: user only uses one drill type and does not explore breadth
- Life disruption: extended break leads to subscription guilt
- Better-seeming alternatives emerge

**Our response:**
- Monthly progress report (Sequence 10) shows trend data and HSK projection updates — visible progress over time
- Churn prevention sequence (Sequence 5) activates after 5+ days of inactivity with value-first content
- Paid user onboarding (Sequence 4) ensures full feature discovery in first 30 days
- Subscription pause option prominently available — better to pause than cancel
- One-month check-in email (Sequence 4, Email 5) asks directly: "What's working and what's not?"

**Conversion benchmark:** Month 1 to Month 2 retention: 80-90%. Month 3 to Month 4: 75-85%. Month 6 to Month 7: 70-80%. Month 12 to Month 13: 65-75%. Median paid lifetime: 8-12 months.

**Timeline:** Month 2 through end of subscription

**Tactics:**
1. Monthly progress reports with per-skill trend data and HSK projection updates
2. Churn prevention sequence triggers at 5 days inactive — value-first, no guilt
3. HSK level progression milestones celebrated with honest, data-backed emails
4. Subscription pause option available from account settings — one click, no friction
5. Quarterly "What's new" email summarizing product improvements since user's last update

---

### Stage 9: Expansion

**User mindset:** "I want more from this system" or "I know someone who should use this." They are a committed user exploring deeper features, providing feedback, or referring friends. Expansion in a single-price product means referrals, community participation, and content contribution.

**Key actions:**
- Share referral link with other Chinese learners
- Join Discord community
- Provide product feedback that shapes development
- Progress to HSK 5-6 (long-term user)

**Success metric:** Referral sent or community joined. Secondary: reaching HSK 5+ content.

**Drop-off risks:**
- No incentive to refer (no referral program in place)
- Discord community is empty or unhelpful
- User feels they have "outgrown" the app at high HSK levels
- Advanced content (HSK 5-6) is insufficient

**Our response:**
- Referral program: give a friend 1 free month, get 1 free month credited. Simple, no tiers, no tracking complexity.
- Discord community seeded with real study discussions, not just product announcements
- HSK 5-6 content depth maintained and expanded based on advanced user feedback
- Advanced users invited to beta-test new features — their feedback is disproportionately valuable

**Conversion benchmark:** 5-10% of paid users send at least one referral. 15-25% of paid users join Discord. 2-5% of referrals convert to paid.

**Timeline:** Month 3+ of paid subscription

**Tactics:**
1. Referral program with symmetric incentive (1 month free for both parties)
2. Discord community with study-group channels organized by HSK level
3. Feature request channel in Discord where Jason responds directly
4. Beta access for users at HSK 5+ — earliest access to new advanced content
5. "Invite a study partner" prompt in monthly progress report email

---

### Stage 10: Win-back

**User mindset:** "I stopped using it. Maybe I should try again." They cancelled weeks or months ago. They may feel guilt about abandoning their Chinese study. They need a reason to return that is not guilt-based.

**Key actions:**
- Open win-back email
- Click through to app
- Start a session
- Optionally resubscribe

**Success metric:** Session completed after 30+ days of inactivity. Secondary: resubscription.

**Drop-off risks:**
- Emails feel like spam — user ignores or unsubscribes
- User has moved to a different tool and is not coming back
- Returning feels overwhelming — too much "catch up" required
- User forgot their login credentials

**Our response:**
- Win-back sequence (Sequence 7) is 3 emails over 30 days, then stops permanently. We do not nag.
- Emails lead with product improvements ("What's new since you left"), not guilt
- Discount offer at day 45 post-cancellation: 20% off for 3 months
- "Your progress is saved" messaging — returning is not starting over
- Final email at day 60 explicitly says "This is the last email I'll send about this"

**Conversion benchmark:** 3-8% of churned paid users reactivate within 90 days. 8-15% of those who open win-back emails reactivate. Win-back users retain at 60-70% of the rate of organic paid users.

**Timeline:** 30-90 days after cancellation

**Tactics:**
1. Win-back email 1 (day 30): product improvements and feature updates since departure
2. Win-back email 2 (day 45): 20% discount offer for 3 months
3. Win-back email 3 (day 60): final message, honest close, no further nudges
4. "Your progress is saved" in every win-back email — removes the "starting over" barrier
5. Free tier remains active permanently — user can return to HSK 1-2 content anytime without resubscribing

---

## Activation Definition

### What "activated" means

**An activated user has completed 3 or more sessions in their first 7 days, using at least 2 different drill types.**

This is not an arbitrary threshold. It is the behavioral milestone that predicts whether a user will still be active at day 30.

### Why these specific criteria

**3 sessions (not 1, not 5):**
- 1 session proves curiosity, not commitment. Users who complete one session and never return are the largest drop-off group (40-50% of all signups).
- 2 sessions prove willingness to return, but the forgetting curve means the SRS algorithm has barely begun to function. Review intervals are not yet calibrated.
- 3 sessions in 7 days means the user has returned at least twice after the initial session. The SRS algorithm has enough data points to begin adapting. The user has experienced the system adjusting to them. This is the point where the product's adaptive behavior becomes visible to the user.
- 5+ sessions in 7 days indicates a power user but sets the bar too high. Requiring daily use in the first week would exclude evening-and-weekend studiers who are good long-term users.

**2+ drill types (not just flashcards):**
- Users who only experience vocabulary flashcards in their first week are seeing 1 of 27 drill types. They have not experienced the product's core differentiator.
- Experiencing 2+ drill types (e.g., vocabulary recognition + tone discrimination, or cloze + listening) gives the user a taste of adaptive variety. They understand that the system is doing something different.
- The system enforces drill type variety in sessions 2 and 3, so this criterion is met automatically for users who complete 3 sessions. It serves as a data validation check: if a user somehow completed 3 sessions with only 1 drill type, something is broken in the session builder.

**7 days (not 3, not 14):**
- 3 days is too short. Users who sign up on Monday and do 3 sessions by Wednesday might have had one enthusiastic evening. The 7-day window captures whether they return after the initial burst.
- 14 days is too long. By day 14, the window for habit formation is closing. Users who take 14 days to complete 3 sessions are already showing weak engagement signals.
- 7 days is one natural week. It captures weekday-and-weekend patterns. It aligns with the weekly progress digest timing.

### Activation funnel with expected conversion rates

| Step | Action | Cumulative conversion (from signup) |
|------|--------|-------------------------------------|
| 1 | Account created | 100% |
| 2 | First session started (within 48 hours) | 55-70% |
| 3 | First session completed | 45-60% |
| 4 | Second session completed (within 72 hours of first) | 30-45% |
| 5 | Third session completed (within 7 days of signup) | 25-40% |
| 6 | 2+ drill types used across sessions 1-3 | 24-39% |
| 7 | **Activated** (criteria met) | 24-39% |

**Target activation rate:** 30% of all signups. This is aggressive for a free app (typical ranges: 15-35%). The combination of a free tier with real content, zero-configuration onboarding, and an adaptive first session should put us at the upper end.

**Activation rate for users who complete first session:** 45-55%. Once a user has completed one session, the odds of activation roughly double compared to all signups.

### What happens to non-activated users

- Users who sign up but never start a session receive the Activation Nudge sequence (Sequence 2): 3 emails over 10 days, then silence.
- Users who complete 1-2 sessions but do not reach 3 in 7 days continue receiving the Free User Onboarding sequence (Sequence 1) but are tagged as "under-activated" for analytics.
- No user is ever deleted or locked out. Free tier access persists indefinitely. The system is patient.

---

## Segmentation Framework

### Behavioral Segments (9 segments)

| Segment | Definition | Population estimate | Priority |
|---------|------------|--------------------:|----------|
| **Never Started** | Signed up, zero sessions completed | 30-45% of signups | Medium — Activation Nudge sequence, then deprioritize |
| **One-and-Done** | Completed exactly 1 session, no return within 7 days | 15-20% of signups | Low — email is only touchpoint; likely lost |
| **Under-Activated** | 2 sessions in first 7 days but did not hit activation threshold | 8-12% of signups | High — closest to activation, worth targeted nudge |
| **Activated Free** | Met activation criteria, still on free tier | 15-25% of signups | Highest — nurture toward conversion |
| **Habitual Free** | 3+ sessions/week for 3+ weeks, still on free tier | 8-15% of signups | High — conversion candidates, approaching HSK 2/3 |
| **New Paid** | Paid subscriber in first 30 days | varies | High — ensure full feature adoption |
| **Established Paid** | Paid subscriber, 30+ days, 3+ sessions/week | varies | Medium — maintain with progress reports |
| **At-Risk Paid** | Paid subscriber, activity dropped below 2 sessions/week after previously maintaining 3+ | varies | Highest — churn prevention sequence |
| **Win-Back Eligible** | Cancelled paid subscription, 30-90 days ago | varies | Medium — win-back sequence, then release |

### HSK Level Segments (5 segments)

| Segment | HSK range | Characteristics | Strategic focus |
|---------|-----------|-----------------|-----------------|
| **Absolute Beginner** | Pre-HSK 1 | Zero prior Chinese. Needs orientation on tones, pinyin, basic characters. | Smooth first session, immediate value from adaptive assessment |
| **Beginner** | HSK 1-2 | Free tier user. Learning foundational vocabulary and grammar. | Activation, habit formation, preparing for HSK 2/3 boundary |
| **Lower Intermediate** | HSK 3 | Paid tier. First encounter with complex grammar, longer passages. Highest churn risk due to difficulty spike. | Retention through progress visibility. Diagnostics become critical. |
| **Intermediate** | HSK 4 | Paid tier. Largest vocabulary jump. Plateau zone. | Feature depth: graded reader, listening practice, speaking drills |
| **Upper Intermediate** | HSK 5-6 | Paid tier. Long-term user. Content depth matters. | Expansion: referrals, community, beta features, advanced diagnostics |

### Engagement Pattern Segments (4 segments)

| Segment | Pattern | Typical user | Response |
|---------|---------|--------------|----------|
| **Daily Practitioner** | 5-7 sessions/week, 10-20 minutes each | Evening routine, high discipline | Weekly digest is enough. Do not over-email. |
| **Weekday Worker** | 3-5 sessions/week, weekdays only | Studies on commute or lunch break | Session-length adaptation for shorter slots (10 min) |
| **Weekend Warrior** | 1-3 sessions/week, mostly weekends | Longer sessions (30-45 min), less frequency | Encourage at least one weekday touchpoint; longer sessions are fine |
| **Sporadic** | 1-2 sessions/week, irregular | At-risk of churning; no routine established | Habit formation emails; minimum viable routine (10 min, 3x/week) |

### Priority Matrix

| | High engagement | Medium engagement | Low engagement |
|--|----------------|-------------------|----------------|
| **Free** | Convert to paid (Sequence 3) | Build habit (Sequence 1) | Activate (Sequence 2) |
| **Paid** | Expand (referrals, community) | Retain (progress reports, feature discovery) | Prevent churn (Sequence 5) |
| **Churned** | Win back (Sequence 7) | Win back with discount | Release after 90 days |

---

## Free-to-Paid Conversion Strategy

### The natural trigger

The free tier covers all HSK 1-2 content — approximately 300 words, foundational grammar, and the full system (27 drill types, diagnostics, graded reader at HSK 1-2 level). The paywall activates when the user approaches HSK 3 content.

This trigger point is deliberate:

- **By the time a user hits the HSK 2/3 boundary, they have invested 4-12 weeks of daily study.** They have demonstrated serious commitment. The upgrade ask comes at the moment of maximum demonstrated value and minimum price sensitivity.
- **The user can see what they are paying for.** HSK 3 content is visible but locked. They know what 600 new words, longer passages, and complex grammar look like because they have completed the HSK 1-2 equivalents.
- **The alternative is going backward.** At this point, switching to a free app means re-entering vocabulary they already know. The switching cost is real.

### Conversion tactics (ranked by expected impact)

**1. Natural content boundary (HSK 2/3 paywall)**
- Impact: Highest. This is not a tactic — it is the product architecture. The paywall is where the content ends, not where an arbitrary gate sits.
- Implementation: When a user reaches 80% of HSK 2 vocabulary at 75%+ accuracy, the system surfaces HSK 3 content previews and the upgrade option.
- Expected contribution: 50-60% of all conversions happen within 14 days of hitting this boundary.

**2. Upgrade email sequence (Sequence 3)**
- Impact: High. Five emails over 21 days, triggered by the HSK 2/3 boundary.
- Sequence: Milestone celebration, feature preview (diagnostics), value framing ($0.50/day), objection handling (time commitment concern), discount offer (20% off for 3 months).
- Expected contribution: 20-30% of conversions are influenced by at least one email in this sequence.

**3. In-app diagnostics preview**
- Impact: Medium-high. Show the user their per-skill breakdown on the free tier but lock the detailed view (HSK projection, specific weakness identification, trend data) behind paid.
- The preview creates a concrete "I want to see this" desire that the upgrade fulfills.
- Expected contribution: 10-15% of conversions cite diagnostics as a factor.

**4. Graded reader depth**
- Impact: Medium. HSK 1-2 graded reading passages are available on the free tier. HSK 3+ passages are locked. Users who have engaged with the cleanup loop on free content want more reading material.
- Expected contribution: 5-10% of conversions are driven by desire for more reading content.

**5. Time-limited discount**
- Impact: Medium, but only for price-sensitive users who have already hit the boundary. The 20% discount ($12/month for 3 months) in Sequence 3, Email 5 converts a specific segment: users who want to upgrade but need a psychological nudge.
- Constraints: Offer is available once per user. Valid for 7 days. Not repeated. Not available at other times.
- Expected contribution: 5-10% of conversions use the discount.

### Anti-patterns: things we never do

1. **Never gate free tier features behind upgrade prompts.** HSK 1-2 is fully functional. No "use this drill type 3 times then upgrade for more." The free tier works as a complete product at its level.
2. **Never show upgrade prompts before the user reaches the HSK 2/3 boundary.** Premature upgrade asks damage trust and reduce conversion rates by training users to dismiss prompts.
3. **Never use countdown timers, fake scarcity, or "only X spots left" language.** The product is digital. There are no spots. Fake urgency violates the Honest Metrics brand pillar.
4. **Never make the free tier worse to make paid look better.** No artificially throttling session lengths, drill variety, or SRS intervals on free.
5. **Never require a credit card at signup.** The free tier is free. Credit card requirement at signup reduces signup rates by 40-60% and attracts users who forget to cancel, not users who want the product.
6. **Never offer more than one discount per user.** The 20% offer happens once. If it does not convert, the price is the price. Repeated discounting trains users to wait for deals.
7. **Never send more than 5 upgrade emails total.** Sequence 3 is 5 emails over 21 days. After that, the user sees in-app upgrade options but receives no more email pressure.

### Expected conversion rates

| Segment | Expected conversion rate |
|---------|------------------------:|
| All free signups | 5-12% |
| Activated free users (3+ sessions in first 7 days) | 15-25% |
| Users who hit HSK 2/3 boundary | 20-35% |
| Users who hit boundary + received full Sequence 3 | 25-40% |
| Users who used the graded reader 5+ times on free tier | 18-28% |
| Users who never activated | <2% |

---

## Retention Framework

### What drives retention in language learning

Language learning retention differs from typical SaaS retention because the product's value proposition depends on the user's effort. A user can have a perfectly working product and still churn because they are not studying. Retention in language learning is driven by:

1. **Visible progress.** Users who can see that their HSK readiness scores are moving, that their accuracy is improving, and that their vocabulary is growing will continue. Users who feel stuck will stop. The diagnostics and progress reports are retention tools, not features.

2. **Routine integration.** Users who study at the same time each day retain at 2-3x the rate of users who study at random times. The product should reinforce routine without creating guilt when it breaks.

3. **Appropriate difficulty.** Too easy and users feel they are wasting time. Too hard and they feel defeated. The adaptive system must keep difficulty in the productive struggle zone: challenging enough to require effort, achievable enough to maintain confidence.

4. **Content freshness.** Users who only do vocabulary flashcards will tire of the format. The 27 drill types and graded reader provide variety, but the system must actively rotate drill types, not wait for users to discover them.

5. **Sunk cost awareness (healthy).** Users who can see that they have 400 words in active rotation, 50 passages read, and 12 weeks of progress data will think twice before switching apps. This is not lock-in through friction — it is honest data about effort invested.

### Retention tactics by phase

#### First 7 days (Signup to Activation)

**Goal:** Get the user to 3 sessions and activation.

| Tactic | Implementation | Metric |
|--------|---------------|--------|
| Welcome email with 10-minute first session prompt | Sequence 1, Email 1 — immediate | First session start rate |
| 24-hour nudge if no session | Sequence 1, Email 2 or Sequence 2, Email 1 | Session start within 48 hours |
| Post-first-session milestone email | Sequence 8, Milestone 1 — suggests second session within 24 hours | Day 1 to Day 2 return rate |
| Drill type variety enforced in sessions 2-3 | System-level: session builder includes listening or tone drill | Drill types used by day 7 |
| Day 7 progress summary email | Sequence 1, Email 5 — shows per-skill data | Day 7 retention |

#### Days 8-30 (Activation to Habit)

**Goal:** Establish a 3+ session/week routine and discover key features (graded reader, diagnostics).

| Tactic | Implementation | Metric |
|--------|---------------|--------|
| Feature discovery: cleanup loop | Sequence 1, Email 6 (day 10) — explains graded reader cycle | Reader open rate within 3 days of email |
| Two-week check-in | Sequence 1, Email 7 (day 14) — asks "What's working?" | Reply rate (target: 5-10%) |
| Weekly progress digest (starts week 2) | Sequence 9 — every Monday if active | Digest open rate; session count following Monday delivery |
| Gentle re-engagement if activity dips | Sequence 5, Email 1 — value-first study tip | Return rate within 48 hours of email |
| HSK 1 mastery milestone | Sequence 8, Milestone 3 — when 150 words at 85%+ accuracy | Progression to HSK 2 content |

#### Days 31-90 (Habit to Commitment)

**Goal:** Solidify the habit, convert free users to paid, retain new paid users through feature adoption.

| Tactic | Implementation | Metric |
|--------|---------------|--------|
| Monthly progress report | Sequence 10 — 1st of each month with trend data | Open rate; session activity in week after delivery |
| Upgrade sequence for users at HSK 2/3 boundary | Sequence 3 — 5 emails over 21 days | Conversion rate |
| Paid user onboarding | Sequence 4 — 5 emails over 30 days covering diagnostics, reader, projection | Feature adoption rates (diagnostics used, reader opened, projection viewed) |
| One-month paid check-in | Sequence 4, Email 5 — "How's it going?" | Reply rate; churn rate in month 2 vs. users who replied |
| HSK level milestones | Sequence 8 — celebrated with honest, data-backed emails | Time between milestones |

#### Days 90+ (Long-term Retention)

**Goal:** Maintain engagement through progress visibility, community, and content depth.

| Tactic | Implementation | Metric |
|--------|---------------|--------|
| Monthly progress reports | Sequence 10 — ongoing, with trend data across months | Open rate; month-over-month retention |
| Quarterly product updates | Email summarizing new features, improvements, content additions | Open rate; feature adoption |
| Community integration (Discord) | Invite in Sequence 4, Email 5 and monthly reports | Discord join rate; correlation with retention |
| Referral program | Prompted in monthly progress reports after month 3 | Referrals sent; referral conversion rate |
| HSK level celebrations | Sequence 8 milestones for HSK 3, 4, 5 | Time to next level; retention at each level |
| Subscription pause option | Available in account settings; surfaced in Sequence 5 if activity drops | Pause rate vs. cancel rate; return rate after pause |

### Retention benchmarks

| Metric | Target range | Notes |
|--------|-------------:|-------|
| Day 1 to Day 2 (return after first session) | 50-60% | Strongest predictor of activation |
| Day 1 to Day 7 (active on day 7) | 35-45% | Aligns with activation rate |
| Day 1 to Day 14 | 25-35% | Post-onboarding sequence retention |
| Day 1 to Day 30 | 20-30% | Habit formation benchmark |
| Day 1 to Day 60 | 15-22% | Conversion window for free users |
| Day 1 to Day 90 | 12-18% | Long-term free user retention |
| Month 1 to Month 2 (paid) | 80-90% | Critical first renewal |
| Month 2 to Month 3 (paid) | 78-88% | Second renewal, slightly lower |
| Month 3 to Month 6 (paid) | 75-85% per month | Stabilizing |
| Month 6 to Month 12 (paid) | 70-80% per month | Mature retention |
| Month 12+ (paid) | 65-75% per month | Long-term steady state |

**Free user retention context:** Free user retention is naturally lower than paid because there is no financial commitment creating accountability. A free user who is active at day 30 is more likely to convert to paid than a free user who was active at day 7 but stopped by day 14. The free tier is a funnel, not a destination.

**Paid user retention context:** Paid retention above 80% at Month 1-2 is achievable because the paywall is at the HSK 2/3 boundary — users have already demonstrated 4-12 weeks of commitment before paying. They are not impulse purchasers.

---

## LTV Model

### Formula

```
LTV = ARPU x (1 / Monthly Churn Rate)
```

Where:
- **ARPU** (Average Revenue Per User per month) = $14.99 (single plan, no tiers)
- **Monthly Churn Rate** = 1 - Monthly Retention Rate

For a blended monthly churn rate of 15% (85% retention):
```
LTV = $14.99 x (1 / 0.15) = $14.99 x 6.67 = $100
```

For adjusted LTV including discounted first-period users (20% use the discount):
```
Adjusted ARPU for month 1-3 = (0.80 x $14.99) + (0.20 x $12) = $11.99 + $2.40 = $14.39
Adjusted LTV = approximately $96
```

### Segmented LTV table

| Segment | Monthly retention | Avg lifetime (months) | LTV | % of paid users |
|---------|------------------:|----------------------:|----:|----------------:|
| **Power User** (5+ sessions/week, uses reader + diagnostics) | 90% | 10.0 | $150 | 15-20% |
| **Regular** (3-4 sessions/week, consistent routine) | 85% | 6.7 | $100 | 35-40% |
| **Moderate** (2-3 sessions/week, some gaps) | 78% | 4.5 | $67 | 20-25% |
| **Light** (1-2 sessions/week, irregular) | 68% | 3.1 | $46 | 10-15% |
| **At-Risk** (<1 session/week after initial period) | 50% | 2.0 | $30 | 5-10% |

**Blended LTV:** Weighted average across segments = approximately $90-102.

### LTV:CAC targets

| Channel | Target CAC | LTV:CAC ratio | Notes |
|---------|----------:|:-------------:|-------|
| Organic (Reddit, SEO, referrals) | $0-5 | 15:1+ | Highest-quality users; invest in content |
| Product Hunt / Hacker News | $2-8 | 10:1+ | One-time launch spikes; technical audience |
| Paid social (Reddit, Twitter) | $15-30 | 3:1 to 5:1 | Minimum viable; test before scaling |
| Paid search (Google) | $20-40 | 2:1 to 4:1 | High intent but expensive for niche |
| Influencer/partner | $10-25 | 3:1 to 8:1 | Variable; depends on partner fit |

**Minimum acceptable LTV:CAC ratio:** 3:1. Below this, the channel is not sustainable for a solo developer without external funding. Target 5:1 or higher for primary channels.

### LTV optimization levers (ranked by impact)

**1. Increase paid retention (highest impact)**
- Every 5 percentage points of monthly retention adds approximately $15-25 to LTV.
- Tactics: progress visibility (diagnostics, monthly reports), churn prevention sequence, subscription pause option, content depth at HSK 4-6.
- Moving retention from 85% to 90% increases blended LTV from ~$100 to ~$150. This is the single most valuable metric to improve.

**2. Increase activation rate**
- Activated users convert to paid at 3-5x the rate of non-activated users. Increasing activation from 30% to 40% of signups has a multiplicative effect on total revenue.
- Tactics: adaptive first session, onboarding email sequence, drill type variety enforcement, day-3 nudge for under-activated users.

**3. Increase free-to-paid conversion rate**
- Directly increases the number of paying users per cohort.
- Tactics: natural HSK 2/3 boundary, upgrade email sequence, diagnostics preview, graded reader content depth.

**4. Decrease CAC (lowest marginal impact but important for sustainability)**
- Organic channels (SEO, Reddit, referrals) have near-zero marginal CAC. Investing in content that ranks and communities that refer is the most capital-efficient growth strategy.
- Tactics: SEO blog posts, Reddit value posts, referral program, Product Hunt and HN launches.

---

## Channel Strategy

### Email (Primary Channel)

**Role:** All lifecycle communication. Onboarding, activation, conversion, retention, win-back. Email is the only channel where we control timing, content, and delivery. It is the backbone of the lifecycle system.

**Tool recommendation:** Buttondown or Resend + custom templates.

Buttondown is preferred for a solo developer because:
- Simple API for transactional and marketing emails
- Markdown-native (matches our plain-text-first approach)
- No visual email builder bloat
- Reasonable pricing for small lists (free up to 100 subscribers, $9/month up to 1,000)
- Audience segmentation via tags
- Simple automation for sequences

Resend is the alternative if Buttondown's automation is insufficient:
- Developer-friendly API
- React Email for templating (if HTML templates are needed)
- Better deliverability infrastructure
- $20/month for 5,000 emails

**Cadence guidelines:**
- Maximum 2 emails per week per user, across all sequences. The weekly digest counts as one.
- Milestone emails (Sequence 8) are exceptions — they can exceed the 2/week cap because they are triggered by user achievement, not by calendar.
- Never send email between 9pm and 7am in the user's local timezone (if timezone is known; default to US Eastern if unknown).
- Sequence priority ordering (see email-sequences.md) resolves conflicts when a user qualifies for multiple sequences.

**Metrics to track:**
- Open rate: target 35-50% for onboarding, 25-40% for recurring (weekly/monthly)
- Click rate: target 8-15% for CTAs in onboarding, 5-10% for recurring
- Unsubscribe rate: keep below 0.5% per email. If any email exceeds 1%, rewrite or remove it.
- Reply rate for check-in emails: target 5-10%

### In-App Messaging (Secondary Channel)

**Role:** Contextual prompts, feature discovery, and conversion nudges that are timed to user behavior within the app. In-app messaging supplements email — it does not replace it.

**Tool recommendation:** Custom implementation (not a third-party tool).

For a solo developer with a Flask-based web app, building in-app messaging is more practical than integrating Intercom or Appcues:
- Simple notification banner at the top of the session screen
- Modal for milestone celebrations (shown once, dismissable, never repeated)
- Upgrade prompt (shown only after HSK 2/3 boundary is reached)
- All messages stored in the database with user_id, message_type, shown_at, dismissed_at

**Cadence guidelines:**
- Maximum 1 in-app message per session. Never interrupt a drill.
- Upgrade prompt appears only after the user has completed their session, not during.
- Milestone celebrations appear at the start of the session following the milestone, not during the milestone session.
- Feature discovery tips appear only once per feature. If dismissed, they do not return.

**Messages to implement:**
1. "Welcome back" with items-due count (every session, subtle, not a modal)
2. "New feature: [feature name]" banner (one-time, after product updates)
3. "You've reached HSK 2 — here's what's in HSK 3" (one-time, at boundary)
4. "Your diagnostics are ready" (one-time, after first 7 sessions)
5. Milestone celebration (one-time per milestone, brief)

### Discord (Tertiary Channel)

**Role:** Community, peer support, and feedback collection. Discord is not a messaging channel — it is a community space. We do not send announcements or promotions in Discord. It exists for learners to connect with each other and with Jason.

**Tool recommendation:** Discord (free tier is sufficient initially).

**Channel structure:**
- `#introductions` — new members share their HSK level and goals
- `#daily-practice` — users share what they studied today (accountability)
- `#hsk-1-2` / `#hsk-3-4` / `#hsk-5-6` — level-specific discussion
- `#study-tips` — general Mandarin study advice (not app-specific)
- `#feedback` — product feedback, feature requests, bug reports
- `#announcements` — Jason posts product updates (low volume, once or twice a month)

**Cadence guidelines:**
- Jason posts in `#announcements` no more than 2x/month
- Jason responds to `#feedback` posts within 48 hours
- No automated bot messages. No scheduled posts. No "engagement" tactics.
- Discord invite is included in Sequence 4 (paid onboarding, Email 5) and monthly progress reports

**Metrics to track:**
- Members: target 50-200 in first 6 months
- Weekly active members (posted at least once): target 15-30% of total members
- Feedback posts per month: target 5-15
- Correlation between Discord membership and paid retention rate

---

## Implementation Priority

### Phase 1: Pre-Launch (Now through Launch Day)

**What to build:**
- Email infrastructure: set up Buttondown (or Resend), configure sender domain, test deliverability
- Email sequences 1, 2, and 8 (free onboarding, activation nudge, milestone celebrations) — these are written and ready in email-sequences.md
- Basic event tracking: signup_complete, first_session_start, first_session_complete, day_7_active (see tracking-plan.md)
- Post-signup redirect to first session (one CTA, nothing else)
- In-app "items due" count on session start screen
- GA4 implementation with core events

**What to measure:**
- Signup rate from landing page
- First session start rate (within 48 hours of signup)
- First session completion rate
- Email deliverability and open rates for sequences 1 and 2

**What to defer:**
- Upgrade sequence (Sequence 3) — not needed until users reach HSK 2/3 boundary, which takes 4-12 weeks
- Paid user onboarding (Sequence 4) — no paid users yet
- Churn prevention (Sequence 5) — no churn to prevent yet
- Win-back (Sequence 7) — no churned users yet
- Discord community — not enough users to sustain a community
- Referral program — need activated users first
- Weekly digest and monthly report — need 2+ weeks of data first

### Phase 2: Launch + 30 Days

**What to build:**
- Weekly progress digest (Sequence 9) — activate for users with 14+ days of data
- Monthly progress report (Sequence 10) — activate for users with 30+ days of data
- In-app feature discovery messages (one-time tips for graded reader, diagnostics, listening drills)
- Activation tracking dashboard: signup to activation funnel, segmented by source
- Free-to-paid upgrade sequence (Sequence 3) — will be needed as first cohort approaches HSK 2/3

**What to measure:**
- Activation rate (3+ sessions in 7 days, 2+ drill types) — the primary metric for this phase
- Day 1 to Day 7 retention
- Day 1 to Day 30 retention
- Email sequence performance (open rates, click rates, unsubscribe rates per email)
- Feature adoption: graded reader opened, diagnostics viewed, listening drill completed

**What to defer:**
- Paid user onboarding (Sequence 4) — build when first paid users appear
- Churn prevention (Sequence 5) — build when paid user activity data exists
- Discord community — wait until 100+ signups
- Referral program — wait until paid users exist
- Paid acquisition channels — organic only in first 30 days

### Phase 3: Launch + 90 Days

**What to build:**
- Paid user onboarding sequence (Sequence 4) — by now, first paid cohort exists
- Churn prevention sequence (Sequence 5) — paid users with declining activity
- Cancellation flow (Sequence 6) — needed for first cancellations
- In-app upgrade prompt (shown after HSK 2/3 boundary, post-session)
- Segmentation infrastructure: tag users by behavioral segment, HSK level, engagement pattern
- Discord community launch — by now there should be 100-500 signups

**What to measure:**
- Free-to-paid conversion rate (overall and by segment)
- Month 1 to Month 2 paid retention
- Churn reasons (cancellation survey data from Sequence 6)
- Feature adoption by paid users (diagnostics, reader, listening, speaking)
- Activation rate trend (is it improving as onboarding improves?)
- LTV:CAC by acquisition source

**What to defer:**
- Win-back sequence (Sequence 7) — not enough time for churn + 30-day wait
- Referral program — can build, but defer if engineering time is needed for retention features
- Paid acquisition — unless organic channels are saturating, which is unlikely at 90 days

### Phase 4: Launch + 6 Months

**What to build:**
- Win-back sequence (Sequence 7) — first cohort of churned paid users now eligible
- Referral program (1 month free for both parties) — infrastructure and tracking
- Subscription pause option — alternative to cancellation
- Quarterly product update email for long-term users
- Automated segmentation and segment-based email routing
- Dashboard: cohort retention curves, LTV by segment, conversion funnel with drop-off analysis

**What to measure:**
- Blended LTV (enough data for reliable calculation)
- Win-back reactivation rate
- Referral program: referrals sent, referral signup rate, referral conversion rate
- Cohort retention curves (are newer cohorts retaining better than launch cohort?)
- 6-month paid retention rate
- Net revenue retention (revenue from existing users, accounting for churn and expansion)

**What to defer:**
- Paid acquisition scaling — only scale if LTV:CAC is proven at 3:1+ on tested channels
- Annual pricing option — evaluate at 6 months based on retention data
- Localization of email content — English only until non-English demand is proven

---

## Lifecycle Automation Architecture

### Trigger Events

Every lifecycle action begins with a trigger event. These are the events the app emits, and each one can activate an email sequence, update a user segment, or record data for analytics.

| Trigger event | Source | Data payload |
|---------------|--------|-------------|
| `signup_complete` | App DB (user created) | user_id, email, signup_source, utm_params, timestamp |
| `first_session_start` | App DB (session record) | user_id, timestamp, time_since_signup |
| `first_session_complete` | App DB (session record) | user_id, drills_completed, accuracy, drill_types_used, timestamp |
| `session_complete` | App DB (session record) | user_id, session_number, drills_completed, accuracy, drill_types_used, duration, timestamp |
| `activation_achieved` | Computed (3+ sessions in 7 days, 2+ drill types) | user_id, timestamp, sessions_count, drill_types_count |
| `hsk_boundary_reached` | Computed (80%+ of HSK 2 vocab at 75%+ accuracy) | user_id, hsk_level_completing, accuracy, timestamp |
| `upgrade_complete` | Stripe webhook | user_id, plan, amount, payment_method, timestamp |
| `milestone_achieved` | Computed (various thresholds) | user_id, milestone_type, milestone_data, timestamp |
| `inactivity_threshold` | Cron job (daily check) | user_id, days_inactive, last_session_date, is_paid |
| `subscription_cancelled` | Stripe webhook | user_id, cancellation_reason, end_date, timestamp |
| `subscription_paused` | Stripe webhook / app action | user_id, pause_date, timestamp |
| `subscription_resumed` | Stripe webhook / app action | user_id, resume_date, timestamp |
| `reader_passage_completed` | App DB | user_id, passage_id, words_looked_up, timestamp |
| `diagnostics_viewed` | App DB | user_id, skill_levels, timestamp |
| `referral_sent` | App DB | user_id, referral_code, channel, timestamp |

### Trigger-to-Sequence Mapping

Each trigger event activates a specific email sequence or action. When triggers conflict, the priority order from email-sequences.md governs.

```
signup_complete
  ├── Start Sequence 1 (Free User Onboarding)
  ├── Tag user: segment = "never_started"
  └── Record: signup source, UTM params

first_session_start
  ├── Stop Sequence 2 (Activation Nudge) if running
  ├── Tag user: segment = "started"
  └── Record: time_since_signup (for funnel analysis)

first_session_complete
  ├── Send Milestone 1 (First Session Complete)
  ├── Update Sequence 1 position (skip to post-first-session emails)
  ├── Tag user: segment = "one_session"
  └── Schedule: check activation criteria at signup + 7 days

session_complete (subsequent sessions)
  ├── Check: activation criteria met? → Send activation_achieved
  ├── Check: milestone thresholds? → Send milestone_achieved
  ├── Check: HSK boundary? → Send hsk_boundary_reached
  ├── Update: user stats (sessions_count, accuracy, drill_types)
  └── Update: engagement pattern segment

activation_achieved
  ├── Tag user: segment = "activated_free"
  ├── Stop Sequence 2 (Activation Nudge) if running
  └── Record: activation data for funnel analysis

hsk_boundary_reached
  ├── Start Sequence 3 (Free-to-Paid Upgrade)
  ├── Tag user: segment = "habitual_free"
  └── Enable: in-app upgrade prompt

upgrade_complete
  ├── Stop Sequence 3 (Upgrade) if running
  ├── Start Sequence 4 (New Paid User Onboarding)
  ├── Tag user: segment = "new_paid"
  └── Record: conversion data (time_since_signup, source, discount_used)

inactivity_threshold (5+ days, paid user)
  ├── Start Sequence 5 (Churn Prevention)
  ├── Tag user: segment = "at_risk_paid"
  └── Record: days_inactive, last_session_date

inactivity_threshold (24+ hours, any user, first 7 days)
  ├── Check: first session completed?
  │     No → Start Sequence 2 (Activation Nudge) if not already running
  │     Yes → Continue Sequence 1 (Free Onboarding)
  └── Tag: at_risk_early = true

subscription_cancelled
  ├── Stop Sequence 5 (Churn Prevention) if running
  ├── Start Sequence 6 (Cancellation Flow)
  ├── Tag user: segment = "cancelled"
  ├── Schedule: Start Sequence 7 (Win-Back) at cancellation + 30 days
  └── Record: cancellation_reason, lifetime, LTV

session_complete (after 30+ days inactivity, previously cancelled)
  ├── Stop Sequence 7 (Win-Back) if running
  ├── Tag user: segment = "reactivated"
  └── Record: win_back data
```

### Segment Transitions

Users move between segments based on trigger events. Each transition is logged with a timestamp for cohort analysis.

```
never_started ──[first_session_start]──→ started
started ──[first_session_complete]──→ one_session
one_session ──[no activity for 7 days]──→ one_and_done
one_session ──[2nd session complete, <7 days]──→ under_activated
under_activated ──[3rd session + 2 drill types, <7 days]──→ activated_free
activated_free ──[3+ sessions/week for 3 weeks]──→ habitual_free
habitual_free ──[upgrade_complete]──→ new_paid
activated_free ──[upgrade_complete]──→ new_paid
new_paid ──[30 days elapsed]──→ established_paid
established_paid ──[activity < 2 sessions/week for 2 weeks]──→ at_risk_paid
at_risk_paid ──[activity resumes to 3+ sessions/week]──→ established_paid
at_risk_paid ──[subscription_cancelled]──→ cancelled
established_paid ──[subscription_cancelled]──→ cancelled
cancelled ──[30 days elapsed, no resubscription]──→ win_back_eligible
win_back_eligible ──[upgrade_complete]──→ new_paid (restart)
win_back_eligible ──[90 days elapsed, no resubscription]──→ churned (no further outreach)
```

### Data Flow: App DB to User Inbox

```
┌─────────────────────────────────────────────────────────────┐
│                         APP DATABASE                         │
│                                                              │
│  Tables:                                                     │
│  - users (id, email, signup_date, segment, is_paid, ...)     │
│  - sessions (user_id, started_at, completed_at, drills, ...) │
│  - drill_results (user_id, drill_type, accuracy, ...)        │
│  - milestones (user_id, milestone_type, achieved_at)         │
│  - email_state (user_id, sequence_id, position, paused)      │
│  - segment_transitions (user_id, from, to, timestamp)        │
│                                                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Trigger events written to
                       │ event_log table on each action
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      LIFECYCLE ENGINE                        │
│                    (Python cron job or worker)                │
│                                                              │
│  Runs every 15 minutes (or on-demand via webhooks):          │
│                                                              │
│  1. Read new events from event_log                           │
│  2. For each event:                                          │
│     a. Determine segment transition (if any)                 │
│     b. Determine sequence action (start/stop/advance)        │
│     c. Check sequence priority (resolve conflicts)           │
│     d. Compute dynamic fields (accuracy, sessions, etc.)     │
│     e. Queue email via email tool API                        │
│                                                              │
│  3. Daily checks (via cron):                                 │
│     a. Inactivity thresholds (5+ days, 8+ days, etc.)        │
│     b. Scheduled sequence emails (day-based timing)          │
│     c. Weekly digest (Monday AM for active users)            │
│     d. Monthly report (1st of month for active users)        │
│                                                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ API calls with dynamic fields
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     EMAIL TOOL (Buttondown)                   │
│                                                              │
│  Receives:                                                   │
│  - Recipient email                                           │
│  - Template ID (maps to specific email in sequence)          │
│  - Dynamic fields (sessions_count, accuracy, etc.)           │
│  - Tags (segment, HSK level, engagement pattern)             │
│                                                              │
│  Handles:                                                    │
│  - Deliverability, SPF/DKIM/DMARC                           │
│  - Unsubscribe management                                   │
│  - Open/click tracking                                       │
│  - Bounce handling                                           │
│                                                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Email delivered
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                        USER INBOX                            │
│                                                              │
│  User receives email. Possible actions:                      │
│  - Opens → tracked by email tool                            │
│  - Clicks CTA → tracked by email tool + UTM → landing/app   │
│  - Replies → goes to hello@aeluapp.com                  │
│  - Unsubscribes → email tool handles, syncs to app DB       │
│  - Ignores → no action; sequence continues on schedule      │
│                                                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ CTA clicks return to app
                       │ with UTM tracking (utm_source=email,
                       │ utm_campaign=sequence_name)
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                         APP (SESSION)                         │
│                                                              │
│  User arrives → starts session → generates new events        │
│  → cycle repeats                                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Notes

**Lifecycle engine options (ranked by simplicity for a solo developer):**

1. **Python script + cron (recommended to start).** A single `lifecycle_worker.py` script that runs every 15 minutes via cron. Reads the event_log table, processes events, makes API calls to Buttondown. Simple, debuggable, no infrastructure beyond the existing server. All state lives in the database.

2. **Celery + Redis (upgrade when needed).** If the cron-based approach hits timing limitations (e.g., milestone emails need to send within minutes, not within 15 minutes), migrate to a Celery task queue. More infrastructure, but handles real-time triggers.

3. **Third-party lifecycle tool (defer).** Tools like Customer.io or Braze are designed for this exact use case but cost $100-500/month and require significant setup. Defer until the user base exceeds 5,000 and the lifecycle engine needs features the custom script cannot provide.

**Database schema additions needed:**

```sql
-- Event log for lifecycle triggers
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT,  -- JSON payload
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Email sequence state per user
CREATE TABLE email_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sequence_id INTEGER NOT NULL,
    position INTEGER DEFAULT 0,  -- which email in the sequence
    started_at TEXT DEFAULT (datetime('now')),
    last_sent_at TEXT,
    paused INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, sequence_id)
);

-- Segment transition log
CREATE TABLE segment_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    from_segment TEXT,
    to_segment TEXT NOT NULL,
    reason TEXT,  -- which event triggered the transition
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**Testing the lifecycle engine:**

Before launch, create 10 test users and simulate the full lifecycle for each:
1. Signup → first session → activation → habit → conversion → paid retention
2. Signup → no session → activation nudge → eventual session → activation
3. Signup → one session → no return → one-and-done
4. Paid user → declining activity → churn prevention → cancellation → win-back
5. Paid user → steady usage → monthly reports → milestone celebrations

Verify that each test user receives exactly the right emails at exactly the right times, that no user receives conflicting sequences, and that segment transitions are logged correctly.

---

## Appendix: Key Numbers Reference

| Metric | Target | Notes |
|--------|--------|-------|
| Landing page to signup | 8-15% | Higher for targeted traffic (Reddit, SEO) |
| Signup to first session | 55-70% | Within 48 hours |
| First session completion | 75-85% | Of those who start |
| Activation rate | 24-39% | Of all signups; 45-55% of first-session completers |
| Habit formation | 60-70% | Of activated users |
| Free-to-paid conversion | 5-12% | Of all free users |
| Free-to-paid (activated) | 15-25% | Of activated free users |
| Free-to-paid (at boundary) | 20-35% | Of users who hit HSK 2/3 |
| Day 1→7 retention | 35-45% | All users |
| Day 1→30 retention | 20-30% | All users |
| Month 1→2 paid retention | 80-90% | Paid users only |
| Month 6→7 paid retention | 70-80% | Paid users only |
| Blended LTV | $72-82 | Across all paid segments |
| Target LTV:CAC | 3:1 minimum | 5:1+ for primary channels |
| Email open rate (onboarding) | 35-50% | First 7 emails |
| Email open rate (recurring) | 25-40% | Weekly/monthly |
| Win-back reactivation | 3-8% | Within 90 days of cancellation |
| Referral conversion | 2-5% | Referral signups to paid |
