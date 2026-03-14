# Email Sequences — Aelu

All lifecycle emails for the Aelu app. Every email is written in full: subject line, preview text, body, CTA. Copy-paste ready for email tool setup.

**From:** Aelu <hello@aeluapp.com>
**Reply-to:** hello@aeluapp.com (real inbox, not a void)
**Format:** Plain text or minimal HTML. Mobile-friendly. One CTA per email.
**Voice:** First person singular. Calm, honest, personal. No hype, no guilt.
**Footer (every email):** One-click unsubscribe. No friction.

Last updated: 2026-02-17

---

## Sequence 1: Free User Onboarding

**Trigger:** User creates a free account
**Emails:** 7 over 14 days
**Suppression:** If user upgrades to paid, move to Sequence 4 instead.

---

### Email 1: Welcome (immediately after signup)

**Subject:** Your account is ready — here's how to start
**Preview text:** Your first session takes about 10 minutes.

Hey —

Welcome to Aelu. This app was built for our own Mandarin study, and we're glad you're trying it.

Here's what to expect:

**Your first session** takes about 10 minutes. The system assesses your starting level across vocabulary, listening, and tone recognition, then adapts from there. You don't need to configure anything.

**What happens after that:** Every session targets what you're weakest at. The system picks from 44 drill types — recognition, production, listening, tone pairs, cloze, sentence construction — based on where your gaps are. You just answer the question in front of you.

**One feature to know about:** The graded reader. When you read a Chinese passage and tap a word you don't know, that word enters your drill queue automatically. Reading and drilling are connected — not two separate activities.

Your free account includes all HSK 1-2 content with no time limit. Not a trial. The full system.

[Start your first session →]

— Aelu

---

### Email 2: Day 1 (24 hours after signup — only if NO session completed)

**Subject:** Your first session takes 10 minutes
**Preview text:** Start with just 5 minutes if that's easier.

Hey —

I noticed you signed up but haven't started a session yet. No rush — just wanted to make sure you know what the first one looks like.

It's 10 minutes. The system gives you a mix of drill types to gauge where you are. You don't need to prepare anything or know any Chinese to start — HSK 1 begins at zero.

If 10 minutes feels like a lot right now, try 5. Open the app, answer a few questions, and close it. That's enough data for the system to start adapting to you.

[Start a quick session →]

— Aelu

---

### Email 3: Day 2 (after first session completed)

**Subject:** First session done — one thing to try next
**Preview text:** You've given the system its first data. Here's what to do with it.

Hey —

You completed your first session. The system now has baseline data on your vocabulary and can start adapting your practice.

One thing you might not have tried yet: **listening drills.**

Most Chinese learners find that their listening lags behind their reading — sometimes by a full HSK level. The listening drills play audio at adjustable speed (start at 0.5x if natural speed feels fast) and test whether you can match what you hear to the right characters.

If your first session was vocabulary-focused, a listening drill will work a completely different part of your Chinese. That variety is intentional — the system interleaves drill types because mixed practice produces stronger retention than doing one type repeatedly.

[Try a listening drill →]

— Aelu

---

### Email 4: Day 4 (study tip — no product pitch)

**Subject:** The 10-minute drill that improved my listening more than anything
**Preview text:** Tone pairs, not individual tones. Here's why.

Hey —

Quick study tip — this one changed how I practice.

Most Mandarin learners practice individual tones: 1st tone, 2nd tone, 3rd tone, 4th tone. That's useful for about a week. In real speech, you almost never hear a tone in isolation. You hear pairs: 2nd + 3rd, 1st + 4th, 3rd + 3rd (with tone sandhi).

Some combinations are easy for English speakers. Some are consistently hard:

- **2nd + 3rd** (rising then dipping): like renmin. The two tones blur together.
- **3rd + 3rd** (tone sandhi): nihao is actually pronounced nihao with a 2nd tone on the first syllable. The rule is simple; hearing it in real speech is not.
- **4th + 2nd** (falling then rising): like daxue. The sharp fall into a rise trips most people up.

Try this: spend 10 minutes drilling tone pairs specifically. Not passively listening — actively identifying which combination you're hearing. After 2-3 weeks of this, you'll notice a difference in how much you catch in natural-speed audio.

This works with any tool. It's just a good way to study.

— Aelu

---

### Email 5: Day 7 (first week progress summary)

**Subject:** Your first week: {{sessions_completed}} sessions, {{words_practiced}} words practiced
**Preview text:** Here's where you stand after 7 days.

Hey —

You've been on Aelu for a week. Here's your summary:

**Sessions completed:** {{sessions_completed}}
**Words practiced:** {{words_practiced}}
**Overall accuracy:** {{accuracy}}%
**Drill types encountered:** {{drill_types_count}} of 27

{{#if active_user}}
A consistent first week. The system now has enough data to start narrowing your focus. Your next few sessions will shift toward the skill where your accuracy is lowest — for most learners at this stage, that's listening or tone discrimination.

One thing to look at: your diagnostics page. It breaks your progress down by skill (vocabulary, listening, reading, tones) so you can see exactly where you stand. The numbers might not all be where you want them — that's the point. Honest data helps you focus.

[See your full progress →]
{{/if}}

{{#if inactive_user}}
Looks like you started but haven't kept a regular schedule yet. That's normal — building a study habit takes time.

Here's what works for most people: pick a time (after dinner, before bed, during lunch), set it for 10-15 minutes, and just do it at that same time for a week. The content doesn't matter as much as the consistency. Even 10 minutes of drilling, done daily, produces measurable results within 2-3 weeks.

Your progress is saved. You can pick up exactly where you left off.

[Start this week strong →]
{{/if}}

— Aelu

---

### Email 6: Day 10 (feature discovery)

**Subject:** The cleanup loop — the feature that connects reading to drilling
**Preview text:** Every word you look up becomes practice. Here's how.

Hey —

There's a feature we want to make sure you know about. It's called the cleanup loop, and it's the reason this app was built.

**How it works:**

1. Open the graded reader and read a Chinese passage at your level.
2. When you hit a word you don't know, tap it. You get the pinyin and definition inline.
3. Every word you tap gets logged automatically.
4. Your next drill session prioritizes those exact words — across multiple drill types.
5. After drilling, go back to reading. You'll recognize more. Repeat.

**Why this matters:**

Most study apps give you a generic word list. "Here are 600 words for HSK 3 — drill them." The problem: those are words the average learner needs. Not necessarily your gaps.

The cleanup loop inverts this. You're drilling the specific words you actually encountered and didn't know. The context from reading makes the memory richer, and the drilling makes the next reading session easier. It's a cycle, and it compounds.

If you haven't tried the graded reader yet, try it this week. Read one passage. Look up a few words. Then do your next drill session and notice what shows up.

[Open the graded reader →]

— Aelu

---

### Email 7: Day 14 (two-week check-in)

**Subject:** Quick question about your experience
**Preview text:** Genuine question — I read every reply.

Hey —

You've been using Aelu for two weeks. I wanted to check in.

Is the app working for you? Is there something that's confusing, or missing, or not quite right?

This app was built for our own Mandarin study, and we're still learning what works for other people. Your feedback directly shapes what we build next. We're a small team reading every reply.

If something is working well, I'd like to know that too. But I'm especially interested in what's not working. The honest answer helps more than the polite one.

Hit reply. I read every response and I'll write back.

— Aelu

P.S. No sales pitch in this email. Just a genuine question from the team that built the thing you're using.

---

## Sequence 2: Activation Nudge

**Trigger:** User signed up but has not completed a single session
**Emails:** 3 over 10 days
**Suppression:** If user completes a session at any point, stop this sequence and move them to Sequence 1 at the appropriate email.

---

### Email 1: Day 2 (no session yet)

**Subject:** Here's what your first 5 minutes look like
**Preview text:** A walkthrough of your first session — nothing to prepare.

Hey —

Your Aelu account is ready. I wanted to walk you through exactly what happens when you start your first session, so there's no guesswork.

**Minutes 0-1:** The system gives you a few vocabulary items at the HSK 1 level. Simple characters, pinyin displayed. You're just matching meanings. This is the baseline.

**Minutes 1-3:** Drill types start to vary. You might get a tone discrimination task (listen to two words, identify which tone you heard) or a cloze task (fill in the missing word in a sentence). The system is testing which skills are strong and which need work.

**Minutes 3-5:** Based on your first answers, the session adapts. If your tone recognition is shaky, you'll get more tone drills. If vocabulary is weak, more vocabulary. You don't choose — the system picks what you need.

That's it. Five minutes, and the system knows enough to start building your study plan.

No Chinese knowledge required. No preparation. Just open it and start.

[Start now →]

— Aelu

---

### Email 2: Day 5 (still no session)

**Subject:** One session is all it takes to see how this works
**Preview text:** Most people who try one session come back for a second.

Hey —

I know starting something new takes activation energy. Here's a data point that might help:

Most people who complete one session come back for a second one within 48 hours. Not because the app nags them — it doesn't send push notifications or streak reminders. They come back because after one session, they can see exactly where their Chinese stands, and that clarity is useful.

While I have your attention, here's a study tip you can use regardless of what app or method you prefer:

**Review new words within 24 hours of first encountering them.** Research on the forgetting curve shows you lose roughly 60% of new material within 48 hours without review. That first review — even just once — dramatically flattens the decay. If you learned 5 new words today from a textbook, podcast, or conversation, quiz yourself on them tomorrow.

Your Aelu account is waiting whenever you're ready. One session, 5-10 minutes.

[Try one session →]

— Aelu

---

### Email 3: Day 10 (last attempt)

**Subject:** Should I keep sending these emails?
**Preview text:** Honest question. No hard feelings either way.

Hey —

You signed up for Aelu 10 days ago but haven't started a session yet. I don't want to keep filling your inbox if you're not interested.

**If you want to try it:** Your account is active and ready. One session takes 5-10 minutes. Here's a direct link:

[Start your first session →]

**If you're not interested right now:** No hard feelings. Your account stays active forever — free tier, no expiration. Whenever you're ready, everything will be there.

**If you'd rather not hear from me:** The unsubscribe link is at the bottom of this email. One click, no guilt.

I'll stop sending nudge emails after this one. If you do start studying later, you'll still get useful content like study tips and progress summaries — but no more "hey, you haven't started yet" messages.

— Aelu

---

## Sequence 3: Free-to-Paid Upgrade

**Trigger:** User approaches HSK 2/3 boundary (80%+ of HSK 2 vocabulary at 75%+ accuracy)
**Emails:** 5 over 21 days
**Suppression:** If user upgrades at any point, stop this sequence and begin Sequence 4.

---

### Email 1: Milestone celebration (triggered by progress)

**Subject:** You've covered {{hsk2_percent}}% of HSK 2 vocabulary
**Preview text:** Here's what's ahead in HSK 3.

Hey —

You've reached a real milestone: {{hsk2_percent}}% of HSK 2 vocabulary at {{accuracy}}% accuracy. That's not a manufactured achievement — it means you've demonstrated solid recall across the foundational 300 words.

Here's what HSK 3 looks like:

- **600 new words** — the vocabulary roughly doubles at each level
- **Longer reading passages** — multi-paragraph stories and dialogues
- **More complex grammar** — complement structures, conditional sentences, comparison patterns
- **Listening at natural speed** — passages assume you can follow conversational-pace audio

The full Aelu system covers all of this: HSK 3-6 content, advanced diagnostics, HSK projection, context notes for every word, and all 44 drill types adapted to intermediate content.

When you're ready, full access is $14.99/month. Cancel anytime.

No rush. Your HSK 1-2 progress is yours permanently, and the free tier never expires.

[See what HSK 3 includes →]

— Aelu

---

### Email 2: Day +5 (feature preview)

**Subject:** What the diagnostics actually look like
**Preview text:** The feature that tells you where you stand — even when the answer is uncomfortable.

Hey —

One of the features that unlocks with full access is the multi-skill diagnostics dashboard. I want to show you what it does, because it's the feature I use most in my own study.

**What it shows:**

- Your HSK readiness broken down by skill: vocabulary, listening, reading, and tone accuracy — tracked separately
- Specific weaknesses: not just "your listening is weak" but which types of listening tasks and which tone combinations
- A projection of when you'll be ready for each HSK level, based on your current pace and accuracy, with confidence intervals

**Why this matters:**

Most Chinese learners have a hidden skill gap. Their vocabulary might be HSK 3, but their listening is HSK 2 and their tones are HSK 1. Without separate tracking, they'd call themselves "HSK 3" and be blindsided by the exam.

The diagnostics exist to tell you exactly where you stand — even when the answer isn't what you want to hear. That honesty is the point. You can't fix a gap you don't know about.

[Unlock full diagnostics →]

— Aelu

---

### Email 3: Day +10 (social proof + value framing)

**Subject:** What $14.99/month actually gets you
**Preview text:** A breakdown of what the subscription includes — and what it costs per day.

Hey —

I want to be straightforward about what the paid tier includes and what it costs.

**What you get for $14.99/month:**

- HSK 3-6 content (4,700+ additional words, graded passages, dialogue scenarios)
- Full multi-skill diagnostics with HSK projection
- Context notes for every vocabulary item (usage, collocations, register, common mistakes)
- All 44 drill types at all levels
- Speaking drills with tone grading
- Adaptive day profiles (sessions adjust to your available time)
- Everything in the free tier, obviously

**What it costs in context:**

- $14.99/month = $0.50/day
- Less than a single baozi
- Less than 15 minutes of iTalki tutoring
- One price. No annual upsell. No "premium plus." No hidden tiers.

**What I can tell you from the data:** learners who practice consistently at HSK 3 and above — 15 minutes a day, 5 days a week — see measurable progress within 3-4 weeks. The subscription pays for itself if it keeps you studying regularly, because consistency matters more than method.

[Get full access — $14.99/month →]

— Aelu

---

### Email 4: Day +16 (objection handling)

**Subject:** Not sure you'll use it enough to justify $14.99/month?
**Preview text:** Here's what the data says about 15 minutes a day.

Hey —

The most common reason people hesitate to upgrade isn't the price — it's the concern that they won't use it enough to justify the cost.

Fair concern. Here's what I can tell you:

**15 minutes a day, 5 days a week is enough.** That's 75 minutes per week. The system adapts to your available time — a 10-minute session focuses differently than a 30-minute one, but both are useful. You don't need to find an hour. You need to find the space between dinner and bed.

**The data shows it works at small doses.** Spaced repetition is specifically designed for short, frequent sessions. The forgetting curve doesn't care about marathon study sessions — it cares about timely review. 15 minutes at the right time beats 2 hours at the wrong time.

**If it still doesn't work out:**

- Cancel anytime. One click. No phone call, no retention flow, no guilt.
- 30-day refund if you're not satisfied. Email me and I'll process it personally.
- Your free tier access (HSK 1-2) remains active permanently.

[Try full access risk-free →]

— Aelu

---

### Email 5: Day +21 (discount offer)

**Subject:** 20% off your first 3 months — if you want it
**Preview text:** $12/month for 3 months. Offer good for 7 days.

Hey —

You've been studying consistently on the free tier, and you're close to outgrowing HSK 2. I'd like to offer you a discount to try the full system:

**20% off for your first 3 months: $12/month instead of $14.99.**

This offer is good for 7 days. After that, the standard price applies. I'm not going to pretend it's "the last chance ever" — it's just a one-time offer for new subscribers who've shown they're serious about studying.

**What you get:** Everything. HSK 3-6, diagnostics, projection, context notes, speaking drills, all 44 drill types. Cancel anytime.

**If $14.99/month (or $12/month) isn't right for you:** The free tier is yours forever. HSK 1-2, full features, no expiration. No hard feelings.

[Claim your discount →]

— Aelu

---

## Sequence 4: New Paid User Onboarding

**Trigger:** User upgrades to paid subscription
**Emails:** 5 over 30 days

---

### Email 1: Welcome to full access (immediately)

**Subject:** Full access is active — here's where to start
**Preview text:** What's unlocked and what to do first.

Hey —

Thank you for upgrading. Your full access is active now.

**What's unlocked:**

- HSK 3-6 content (4,700+ words, graded reading passages, dialogue scenarios)
- Multi-skill diagnostics with HSK projection
- Context notes for every vocabulary item
- Speaking drills with tone grading
- Adaptive day profiles
- Advanced drill types for intermediate and advanced content

**What to do first:**

Run the diagnostics. It takes about 5 minutes and gives you a baseline across vocabulary, listening, reading, and tone accuracy. This is the data the system uses to prioritize your sessions — the more accurate the baseline, the better your sessions will be.

Don't be surprised if the numbers are uneven. Almost everyone has a gap between their strongest and weakest skill. The gap is the information. It tells you (and the system) where to focus.

[Run your first diagnostic →]

— Aelu

---

### Email 2: Day 3 (feature discovery)

**Subject:** The graded reader and the cleanup loop — how they work together
**Preview text:** Reading and drilling, connected. This is the core of the system.

Hey —

If you haven't tried the graded reader yet, this is the feature I'd point you to first.

Here's why: the cleanup loop is what makes the subscription worth it.

**The cycle:**
1. Open a graded reading passage at your level. The system suggests passages based on your HSK diagnostics.
2. Read. When you hit a word you don't know, tap it. Pinyin and definition appear inline.
3. Every word you tap is logged and enters your drill queue.
4. Your next session drills those exact words — not just as flashcards, but across multiple drill types (tone discrimination, cloze, sentence construction, audio matching).
5. After drilling, read another passage. You'll recognize more. The cycle compounds.

This is the difference between drilling a generic word list and drilling the specific words you actually struggled with in context. The context makes the memory richer. The drilling makes the next reading session easier.

Try it: open one passage, read for 5 minutes, look up whatever you need. Then do a drill session tomorrow and watch those words appear.

[Open the graded reader →]

— Aelu

---

### Email 3: Day 7 (first week as paid user)

**Subject:** Your first week with full access: {{sessions_count}} sessions, {{accuracy}}% accuracy
**Preview text:** How your progress compares to your free tier baseline.

Hey —

One week on the full system. Here's your summary:

**Sessions this week:** {{sessions_count}}
**Overall accuracy:** {{accuracy}}%
**Words practiced:** {{words_practiced}}
**New words from graded reading:** {{cleanup_words}}

{{#if diagnostics_completed}}
**Your diagnostics show:**
- Vocabulary: HSK {{vocab_level}}
- Listening: HSK {{listening_level}}
- Reading: HSK {{reading_level}}
- Tones: HSK {{tone_level}}

Your weakest skill is {{weakest_skill}}. The system is already adjusting — you'll see more {{weakest_skill}} drills in your upcoming sessions. This is by design. The gap between your strongest and weakest skill is where the most progress is available.
{{/if}}

{{#if no_diagnostics}}
You haven't run the diagnostics yet. I'd recommend it this week — it gives the system a per-skill baseline that makes your sessions more targeted. Takes about 5 minutes.

[Run your diagnostics →]
{{/if}}

[Start this week's first session →]

— Aelu

---

### Email 4: Day 14 (deeper features)

**Subject:** Your HSK projection is ready
**Preview text:** The system now has enough data to estimate your timeline.

Hey —

After two weeks of paid sessions, the system has enough data to generate your HSK projection.

**What this is:** A data-driven estimate of when you'll be ready for each HSK level, based on your demonstrated pace and accuracy across all four skills. It's not a promise — it's a forecast with confidence intervals, and it updates after every session.

**What to expect:** The projection might be further out than you'd like. That's normal. Chinese is a multi-year project, and the system doesn't round down to make you feel better. If your projection says 14 weeks to HSK 3, that's based on your actual data — not an optimistic average.

**How to use it:** The projection also shows which skill is gating your progress. If your vocabulary is on track for HSK 3 in 10 weeks but your listening won't be ready for 18 weeks, you know exactly where extra time would have the most impact.

One more feature to know about: adaptive day profiles. The system adjusts your session composition based on your available time. A 10-minute session before bed focuses on high-priority items. A 30-minute weekend session includes reading, listening, and broader review. Tell the system how much time you have, and it builds the session.

[View your HSK projection →]

— Aelu

---

### Email 5: Day 30 (one-month check-in)

**Subject:** One month in — how's it going?
**Preview text:** Your monthly progress, plus a genuine question.

Hey —

You've been a paid subscriber for one month. Here's your summary:

**Sessions this month:** {{monthly_sessions}}
**Average accuracy:** {{monthly_accuracy}}%
**Words in active rotation:** {{active_words}}
**Graded passages read:** {{passages_read}}
**Strongest skill:** {{strongest_skill}}
**Weakest skill:** {{weakest_skill}}

{{#if improved}}
Your {{improved_skill}} has improved since your initial diagnostic — from HSK {{old_level}} to HSK {{new_level}}. That's measurable progress.
{{/if}}

{{#if plateaued}}
Your progress has been steady but slow this month. That's common at the {{current_level}} level — the vocabulary gets harder and the listening passages get longer. Consistency matters more than speed here. Keep showing up.
{{/if}}

I want to ask you directly: **what's working, and what's not?**

I read every reply and I use the feedback to decide what to build next. If a feature is confusing, if something is missing, if a drill type isn't useful — tell me. The honest answer helps more than the polite one.

Also: if you're looking for other learners to connect with, there's a Discord community where people share progress and study tips. No obligation, just a place to talk about Chinese with people who are doing the same thing.

[View your full diagnostics →]

— Aelu

P.S. Your next billing date is {{billing_date}}. If you ever need to cancel or pause, there's a link in your account settings. One click. No hoops.

---

## Sequence 5: Churn Prevention

**Trigger:** Declining activity (specific thresholds below)
**Emails:** 4 over 14 days
**Suppression:** If user resumes studying (completes a session), stop the sequence.

---

### Email 1: Gentle re-engagement (5+ days no activity)

**Subject:** Study tip: why your listening lags behind your reading (and how to close the gap)
**Preview text:** The most common skill imbalance in Chinese learners.

Hey —

Quick study insight from the data I see across learners:

**Your listening almost certainly lags behind your reading.** This is the most common skill imbalance in Chinese, and it's structural — not a personal failing.

Here's why: when you read, you control the pace. You can linger on a character, reread a sentence, process grammar at your speed. When you listen, the audio controls the pace. Your brain has to decode tones, segment words, and parse meaning in real time. It's a harder cognitive task.

**The fix is specific, not general:**

1. Listen to graded passages at your level, not above it. Challenge is good. Overwhelm isn't.
2. Start at 0.5x-0.75x speed. There's no shame in slowing down.
3. Listen first without a transcript. Then reveal it and check what you missed.
4. Drill the words you missed. (The cleanup loop does this automatically if you use the graded reader.)

10 minutes of targeted listening practice, 3 times a week, closes the gap within a month for most learners.

Your session is ready whenever you are.

[Resume studying →]

— Aelu

---

### Email 2: Day +3 (8+ days no activity)

**Subject:** The minimum viable Mandarin routine
**Preview text:** 10 minutes, 3 times a week. Here's why that works.

Hey —

Building a study habit is hard. I've fallen off the wagon myself more than once. Here's what the research says about making it stick:

**The habit that survives is the one that's small enough to do on your worst day.**

For Chinese, that means:

- **10 minutes, 3 times a week.** Not every day. Not an hour. Just 10 minutes, three times.
- **Same time each day.** After dinner, before bed, during lunch — pick one and protect it.
- **Start with drills, not reading.** Drills have a clear start and end. Reading can feel open-ended, which makes it easier to postpone.

At 10 minutes, 3 times a week, you're doing 30 minutes of spaced repetition per week. That's enough for the SRS algorithm to function. Your review intervals hold. Your vocabulary doesn't decay. And on the weeks you do more, it compounds.

Perfectionism kills language study. "I'll study when I have a real block of time" means you never study. 10 minutes is real.

[Start a 10-minute session →]

— Aelu

---

### Email 3: Day +7 (12+ days no activity)

**Subject:** Your progress is saved
**Preview text:** Pick up right where you left off. Everything is waiting.

Hey —

It's been about two weeks since your last session. A few things I want you to know:

**Your progress is saved.** Every word you've drilled, every accuracy score, every diagnostic result — all still there. You don't lose anything by taking a break.

**Your last session:** {{last_session_date}}
**Words in your active rotation:** {{active_words}}
**Your accuracy before the break:** {{last_accuracy}}%

**What to expect when you come back:** Some rust. Words you had at 85% accuracy two weeks ago might be at 60% now. That's normal — the forgetting curve is real, and the system accounts for it. Your first session back will include more review of recent material. After 2-3 sessions, you'll be back up to speed.

Life gets busy. Chinese will be here when you're ready.

[Continue from where you left off →]

— Aelu

---

### Email 4: Day +14 (19+ days no activity — paid users only)

**Subject:** An honest question about your subscription
**Preview text:** Is it still worth it? Here are your options.

Hey —

It's been about three weeks since your last session. I want to ask you an honest question: **is the subscription still worth it for you?**

I'd rather you make the right call for yourself than pay for something you're not using. Here are your options:

**1. Resume studying.** Your progress is saved. Pick up where you left off. Even 10 minutes this week would keep your review intervals from decaying further.

[Resume studying →]

**2. Pause your subscription.** Take a break without canceling. Your data stays, your progress stays, and you can reactivate whenever you're ready. No charge while paused.

[Pause my subscription →]

**3. Cancel.** Your HSK 1-2 access remains free forever. Your progress data is saved locally on your device. No hard feelings, genuinely.

[Cancel my subscription →]

If something specific isn't working — the content, the drill types, the interface, anything — reply to this email and tell us. We built this app and we fix things quickly. We'd rather solve the problem than lose a learner.

— Aelu

---

## Sequence 6: Cancellation Flow

**Trigger:** User cancels their paid subscription
**Emails:** 2 (confirmation + optional follow-up)

---

### Email 1: Cancellation confirmation (immediately)

**Subject:** Your cancellation is confirmed
**Preview text:** Access continues through {{end_date}}. Free tier is yours permanently.

Hey —

Your cancellation has been processed. Here's what happens now:

- **Your paid access continues through {{end_date}}** (the end of your current billing period). You won't be charged again.
- **After {{end_date}}, your account reverts to the free tier.** All HSK 1-2 content, all 44 drill types at that level, full functionality. No expiration.
- **Your progress data stays on your device.** Nothing is deleted.

One question, if you have a moment — it helps me improve:

**Why did you cancel?**

- [ ] Not using it enough
- [ ] Too expensive
- [ ] Found a better tool
- [ ] Content gaps (missing what I needed)
- [ ] The app didn't fit my learning style
- [ ] Other

[Answer with one click →]

No guilt, no "are you sure?" — just trying to understand what didn't work.

Thanks for trying Aelu. I hope the time you spent studying was genuinely useful.

— Aelu

---

### Email 2: Day +7 post-cancellation (only if cancellation reason NOT answered)

**Subject:** One quick question to help me improve
**Preview text:** 30 seconds. Just one question.

Hey —

I sent a cancellation survey last week but didn't hear back. If you have 30 seconds, one question:

**What would have made you stay?**

You can reply to this email with a sentence. Or a word. Or just hit one of these:

- Cheaper price
- More content
- Better mobile experience
- More drill variety
- Didn't have time to study
- Something else (just reply)

Either way, good luck with your Chinese studies. Your free account is active whenever you want it.

— Aelu

---

## Sequence 7: Win-Back

**Trigger:** 30 days after cancellation (only for users who were previously paid)
**Emails:** 3 over 30 days (days 30, 45, 60 post-cancellation)
**Suppression:** If user resubscribes at any point, stop sequence and begin Sequence 4.

---

### Email 1: Day 30 post-cancellation

**Subject:** What's new in Aelu since you left
**Preview text:** A few real improvements since your last session.

Hey —

It's been a month since you cancelled. I've been building. Here's what's changed:

{{#recent_features}}
- **{{feature_name}}:** {{feature_description}}
{{/recent_features}}

These aren't cosmetic changes — each one came from feedback from learners like you. The app is measurably better than it was when you left.

Your account still has all your progress data. Every word you drilled, every diagnostic score, every accuracy record. You can pick up exactly where you left off.

The free tier is still active if you want to check things out without resubscribing. And if you want full access again, it's the same $14.99/month.

[Come back and see what's new →]

— Aelu

---

### Email 2: Day 45 (only if they haven't returned)

**Subject:** 20% off if you want to give it another try
**Preview text:** $12/month for 3 months. Your progress is still saved.

Hey —

If you've been thinking about picking your Chinese study back up, I'd like to offer:

**20% off for 3 months: $12/month instead of $14.99.**

Your progress data is still saved. You wouldn't start over — you'd continue from exactly where you stopped. The system remembers your skill levels, your weak spots, and your review history.

If you've found something that works better for you, I'm genuinely happy for you. Chinese is hard enough without using the wrong tool.

[Reactivate with discount →]

— Aelu

---

### Email 3: Day 60 (final — only if they haven't returned)

**Subject:** Last email from me about this
**Preview text:** Your account and progress are saved. No more nudges after this.

Hey —

This is the last email I'll send about coming back. I don't want to be that app that keeps asking.

Your account is still active on the free tier. Your progress data is saved on your device. If you ever want to resubscribe, the option is there.

I'll still send the occasional newsletter with study tips and Chinese learning insights — you can unsubscribe from those separately if you'd like.

Good luck with your Chinese. 加油.

— Aelu

---

## Sequence 8: Milestone Celebrations

**Trigger:** Individual milestone achievements
**Format:** Short, one-off emails. Under 150 words each. Honest, not inflated. One forward-looking element per email.

---

### Milestone 1: First session completed

**Subject:** First session complete — the system is adapting
**Preview text:** Baseline data recorded. Here's what happens next.

Hey —

You completed your first session. The system now has baseline data on your vocabulary level and drill accuracy.

What happens next: your second session will already be different from your first. The system uses your answers to select drill types and vocabulary that target your specific gaps. No two sessions are identical after the first.

A suggestion: try a second session within 24 hours. Research on the forgetting curve shows that a first review within 24 hours dramatically improves retention. The sooner you reinforce what you practiced today, the more it sticks.

[Start your second session →]

— Aelu

---

### Milestone 2: 7-day study streak

**Subject:** 7 sessions in 7 days
**Preview text:** Consistency data and what it means for your learning.

Hey —

You've studied 7 days in a row. A few things worth noting:

After 7 consecutive sessions, the spaced repetition algorithm has enough data to schedule reviews with higher precision. Your intervals are now calibrated to your actual recall patterns — not generic estimates.

This is also the point where consistency starts compounding. Words you drilled on Day 1 are coming back for their first scheduled review. If you remember them, the intervals expand. The system is working.

One thing to watch: don't let the streak become pressure. If you miss a day, nothing bad happens. The system adjusts. Consistency matters. Perfectionism doesn't.

[Keep studying →]

— Aelu

---

### Milestone 3: HSK 1 vocabulary mastered (150 words at 85%+ accuracy)

**Subject:** HSK 1 vocabulary: 150 words at {{accuracy}}% accuracy
**Preview text:** The foundation is solid. Here's what HSK 2 introduces.

Hey —

You've reached 85%+ accuracy across the 150 core HSK 1 words. That's a real foundation — not inflated by the system, and not rounded up to make you feel good.

What HSK 2 introduces: 150 more words, slightly longer sentences, more grammar patterns, and drills that test production (not just recognition). The shift from "I can recognize this" to "I can produce this" is where real competence starts.

Your HSK 1 words will continue appearing in review at expanding intervals. They're not "done" — retention requires maintenance. But the hard part of learning them is behind you.

[Continue to HSK 2 →]

— Aelu

---

### Milestone 4: HSK 2 vocabulary mastered

**Subject:** HSK 2 complete: 300 words at {{accuracy}}% accuracy
**Preview text:** You've covered the free tier content. Here's what's ahead.

Hey —

300 words at 85%+ accuracy. You now have a working foundation of the most common Chinese vocabulary — enough to handle basic conversations, read simple signs and menus, and understand the structure of the language.

What's different about HSK 3: the vocabulary gets more abstract, the grammar introduces complement structures and conditional sentences, and reading passages become multi-paragraph. It's a real step up.

HSK 3-6 is available with full access ($14.99/month). Your progress carries over — nothing resets.

If you're not ready to upgrade, your HSK 1-2 content and review schedule remain active on the free tier. No expiration.

[See what HSK 3 includes →]

— Aelu

---

### Milestone 5: HSK 3 vocabulary mastered

**Subject:** HSK 3: {{word_count}} words at {{accuracy}}% accuracy
**Preview text:** You've crossed from beginner to intermediate. The data says so.

Hey —

HSK 3 marks the transition from beginner to intermediate. You can now read graded passages with real narrative, understand conversations at moderate speed, and produce Chinese beyond survival phrases.

This is where many learners plateau. The jump from HSK 3 to HSK 4 is the largest in the system — more new vocabulary, more complex grammar, longer passages. The learners who push through it are the ones who stay consistent through the discomfort of not understanding.

Your diagnostics can show you exactly which skills need attention for HSK 4. Check them before your next session.

[View your HSK 4 readiness →]

— Aelu

---

### Milestone 6: First graded reading passage completed

**Subject:** First passage read — here's how to get the most from reading
**Preview text:** The words you looked up are now in your drill queue.

Hey —

You just read your first graded passage. Every word you tapped for a definition has been added to your drill queue automatically.

Your next session will include those words across multiple drill types — tone discrimination, cloze, audio matching, and more. You didn't have to create a single flashcard. The cleanup loop handles it.

One reading tip: read the same passage twice. First time, look up everything you need. Second time (a day or two later), try to read without tapping. You'll be surprised how many words you recognize on the second pass.

[Read another passage →]

— Aelu

---

### Milestone 7: First listening exercise completed

**Subject:** First listening drill complete
**Preview text:** A harder skill to build. Here's how to keep going.

Hey —

You completed your first listening exercise. Listening is consistently the hardest skill for Chinese learners — if it felt difficult, that's expected.

A few things that help: start at slower speeds (0.5x or 0.75x) and work up gradually. Listen without the transcript first, then reveal it to see what you missed. And focus on tone pairs, not individual words — your brain needs to learn the rhythm of connected speech, not just isolated syllables.

The system will increase your listening drill frequency if your accuracy is below your other skills. Let it push you. That discomfort is where the progress happens.

[Try another listening drill →]

— Aelu

---

### Milestone 8: 100th drill session

**Subject:** Session 100
**Preview text:** 100 sessions of data. Here's what it reveals.

Hey —

100 sessions. The system now has substantial data on your learning patterns — your strongest and weakest skills, your accuracy by drill type, your retention curves, and your pace.

This is the point where the diagnostics become most useful. With 100 sessions of data, your HSK projection has real statistical grounding. Check your diagnostics this week — the picture it paints is worth 5 minutes.

For perspective: 100 sessions at 15 minutes each is 25 hours of focused practice. That's more deliberate Chinese study than most people do in a year.

[View your diagnostics →]

— Aelu

---

### Milestone 9: Cleanup loop first use

**Subject:** Your first cleanup loop word just entered the drill queue
**Preview text:** You looked it up while reading. Now it's a drill.

Hey —

You just looked up a word during graded reading, and it's been added to your drill queue. This is the cleanup loop in action.

Tomorrow (or whenever your next session is), that word will appear in a drill — not as a flashcard, but as a tone discrimination task, a cloze question, or an audio matching exercise. The system picks the drill type based on which cognitive skill needs the most work.

Over time, this cycle — read, look up, drill, read again — means you're always practicing the exact words you actually need. Not a generic word list. Your gaps.

This is the core of the app. The more you read, the better it works.

[Continue reading →]

— Aelu

---

### Milestone 10: 30-day subscription anniversary

**Subject:** One month of full access — your data so far
**Preview text:** 30 days of paid usage. Here's the summary.

Hey —

It's been one month since you upgraded. Here's what the data shows:

**Sessions:** {{monthly_sessions}}
**Words in active rotation:** {{active_words}}
**Accuracy trend:** {{accuracy_trend}}
**Strongest skill:** {{strongest_skill}}
**Weakest skill:** {{weakest_skill}}
**HSK projection:** {{projection_summary}}

If your progress feels slow, look at where you started versus where you are now. A month of consistent practice — even 15 minutes a day — moves the numbers. The system has adjusted to your patterns and is targeting your weakest areas.

If your progress feels fast, don't get overconfident. The Bayesian dampening means the system won't promote words to "mastered" until it has multiple data points. What feels easy now will be tested again at longer intervals.

Thank you for using the app. I'll check in again in a month.

[View your full diagnostics →]

— Aelu

---

## Sequence 9: Weekly Progress Digest

**Trigger:** Recurring, sent every Monday morning
**Suppression:** Only sent if user had at least 1 session in the past 14 days. If no sessions in 14+ days, user enters Sequence 5 instead.

---

### Weekly Progress Digest Template

**Subject:** Your week: {{sessions}} sessions, {{accuracy}}% accuracy, {{new_words}} new words
**Preview text:** Weekly summary and suggested focus for next week.

Hey —

Here's your week:

```
SESSIONS         {{sessions}} ({{sessions_change}} vs last week)
ACCURACY         {{accuracy}}% overall
WORDS PRACTICED  {{words_practiced}}
NEW WORDS        {{new_words}}
PASSAGES READ    {{passages_read}}

ACCURACY BY SKILL
─────────────────────────────────────
Vocabulary    {{vocab_accuracy}}%  {{vocab_bar}}
Listening     {{listen_accuracy}}%  {{listen_bar}}
Reading       {{reading_accuracy}}%  {{reading_bar}}
Tones         {{tone_accuracy}}%  {{tone_bar}}
─────────────────────────────────────
```

**Weakest skill this week:** {{weakest_skill}} ({{weakest_accuracy}}%)

**Suggested focus for next week:** {{suggested_focus}}

{{#if cleanup_words}}
**Cleanup loop:** {{cleanup_words}} words entered your drill queue from reading this week.
{{/if}}

{{#if streak_data}}
**Consistency:** {{days_active}} of 7 days active this week.
{{/if}}

[Start this week's first session →]

— Aelu

[View full progress dashboard →]

---

## Sequence 10: Monthly Progress Report

**Trigger:** Recurring, sent on the 1st of each month
**Suppression:** Only sent to users with at least 1 session in the past 30 days.

---

### Monthly Progress Report Template

**Subject:** Your {{month}} report: {{summary_stat}}
**Preview text:** Monthly progress, skill breakdown, and HSK projection update.

Hey —

Your {{month}} summary:

```
OVERVIEW
─────────────────────────────────────
Sessions this month    {{monthly_sessions}}
Last month             {{prev_sessions}}
Change                 {{session_change}}

Average accuracy       {{monthly_accuracy}}%
Last month             {{prev_accuracy}}%
Change                 {{accuracy_change}}

Words in rotation      {{active_words}}
New words added        {{new_words_added}}
Words "stable" (5+ reviews, 85%+)  {{stable_words}}

SKILL BREAKDOWN
─────────────────────────────────────
              This Month    Last Month    Change
Vocabulary    HSK {{v_now}}          HSK {{v_prev}}          {{v_change}}
Listening     HSK {{l_now}}          HSK {{l_prev}}          {{l_change}}
Reading       HSK {{r_now}}          HSK {{r_prev}}          {{r_change}}
Tones         HSK {{t_now}}          HSK {{t_prev}}          {{t_change}}
─────────────────────────────────────

HSK PROJECTION (updated)
─────────────────────────────────────
HSK {{next_level}} readiness: ~{{projection_weeks}} weeks
  (at current pace of {{sessions_per_week}} sessions/week)
  Gating skill: {{gating_skill}}
─────────────────────────────────────

CONSISTENCY
─────────────────────────────────────
Days active        {{days_active}} of {{days_in_month}}
Longest streak     {{longest_streak}} days
Average session    {{avg_session_length}} minutes
─────────────────────────────────────

CONTENT CONSUMED
─────────────────────────────────────
Passages read      {{passages_read}}
Listening minutes  {{listening_minutes}}
Cleanup loop words {{cleanup_words}}
─────────────────────────────────────
```

{{#if progress_up}}
**Assessment:** Your accuracy improved across {{improved_count}} of 4 skills this month. Your consistency ({{days_active}} active days) is driving this — the SRS algorithm works best with regular input. Your gating skill for HSK {{next_level}} is {{gating_skill}}. Targeting that in your sessions would have the biggest impact on your projection.
{{/if}}

{{#if progress_flat}}
**Assessment:** Your progress held steady this month. No significant movement in accuracy or skill levels. This isn't necessarily bad — consolidation phases are real, especially at the {{current_level}} level. But if you've been doing the same routine for several weeks, consider adding listening or reading variety. The system adapts, but it adapts faster with diverse input.
{{/if}}

{{#if progress_down}}
**Assessment:** Your accuracy slipped this month, likely due to fewer sessions ({{monthly_sessions}} vs {{prev_sessions}} last month). Spaced repetition depends on timely review — when sessions drop off, intervals break and words decay. The fix is straightforward: resume your regular schedule and the numbers will recover within 1-2 weeks.
{{/if}}

[View full diagnostics →]

— Aelu

{{#if paid_user}}
Your next billing date is {{billing_date}}. [Manage subscription →]
{{/if}}

---

## Email Design Guidelines

### Technical Specs

- **Format:** Plain text or minimal HTML (no heavy templates, no image-heavy layouts)
- **From name:** Aelu
- **From address:** hello@aeluapp.com
- **Reply-to:** hello@aeluapp.com (real inbox — replies go to the team, not a void)
- **Unsubscribe:** One-click, in every email footer, no friction, no "are you sure?" confirmation
- **Mobile:** All emails readable on a phone without zooming or horizontal scrolling
- **Width:** Max 600px for HTML emails
- **Font:** System font stack — no custom web fonts in email
- **Links:** One primary CTA button per email. Secondary links as inline text, never as competing buttons.

### Voice Rules

- **Brand voice.** Calm, direct, personal. This is from the Aelu team, not a faceless corporation.
- **Short paragraphs.** 2-3 sentences max. White space is your friend.
- **One CTA per email.** Never present competing actions. If the email is about the graded reader, the CTA goes to the graded reader — not to "start a session" or "view diagnostics."
- **No exclamation marks in subject lines.** Period.
- **No emoji in subject lines.** Period.
- **No ALL CAPS.** Not in subject lines, not in body text, not in CTAs.
- **No "Don't miss out" / "Act now" / "Limited time" language.** The only exceptions are the time-limited discount in Sequence 3 Email 5 and Sequence 7 Email 2, and even those are framed honestly, not urgently.
- **No praise inflation.** Never "Great job!" or "Amazing progress!" — report the data and let the learner assess it.
- **No guilt.** Never "We miss you!" or "Don't lose your streak!" or "You're falling behind!" — acknowledge the break, offer value, and respect their autonomy.
- **No fake personalization.** Don't use the learner's name in every sentence. One "Hey" at the top is enough.

### Subject Line Formulas

**Progress-based:**
- "Your week: {{X}} sessions, {{Y}}% accuracy"
- "HSK {{X}} vocabulary: {{Y}} words at {{Z}}% accuracy"
- "{{X}} sessions in — here's what the data shows"

**Value-based:**
- "Study tip: [specific insight]"
- "The 10-minute drill that improved my listening more than anything"
- "Why your listening lags behind your reading"

**Personal:**
- "Quick question about your experience"
- "One month in — how's it going?"
- "Should I keep sending these emails?"

**Feature-based:**
- "The cleanup loop — the feature that connects reading to drilling"
- "Your HSK projection is ready"
- "What the diagnostics actually look like"

**Never:**
- "We miss you!"
- "Don't lose your streak!"
- "URGENT: Your progress is at risk"
- "You won't believe your progress"
- "Limited time offer!!!"
- "Last chance to save"
- Any subject line with an exclamation mark
- Any subject line with emoji

### Sequence Priority / Conflict Resolution

When a user qualifies for multiple sequences simultaneously, use this priority order:

1. **Cancellation flow** (Sequence 6) — always takes precedence
2. **Churn prevention** (Sequence 5) — overrides onboarding and upgrade sequences
3. **New paid user onboarding** (Sequence 4) — overrides free user sequences
4. **Free-to-paid upgrade** (Sequence 3) — only runs if user is active
5. **Free user onboarding** (Sequence 1) — default for new free users
6. **Activation nudge** (Sequence 2) — only for users with zero sessions
7. **Win-back** (Sequence 7) — only for churned paid users, 30+ days post-cancellation
8. **Milestone celebrations** (Sequence 8) — always send, regardless of other sequences
9. **Weekly digest** (Sequence 9) — always send if active, regardless of other sequences
10. **Monthly report** (Sequence 10) — always send if active, regardless of other sequences

### Dynamic Fields Reference

All dynamic fields used across sequences:

| Field | Description | Example |
|-------|-------------|---------|
| `{{sessions_completed}}` | Total sessions completed | 5 |
| `{{words_practiced}}` | Total unique words drilled | 87 |
| `{{accuracy}}` | Overall accuracy percentage | 74 |
| `{{drill_types_count}}` | Number of distinct drill types encountered | 12 |
| `{{hsk2_percent}}` | Percentage of HSK 2 vocabulary at 75%+ accuracy | 82 |
| `{{sessions_count}}` | Sessions in current period | 7 |
| `{{cleanup_words}}` | Words added via cleanup loop | 14 |
| `{{vocab_level}}` | Current vocabulary HSK level | 3 |
| `{{listening_level}}` | Current listening HSK level | 2 |
| `{{reading_level}}` | Current reading HSK level | 3 |
| `{{tone_level}}` | Current tone accuracy HSK level | 2 |
| `{{weakest_skill}}` | Name of weakest skill | listening |
| `{{strongest_skill}}` | Name of strongest skill | vocabulary |
| `{{monthly_sessions}}` | Sessions in current month | 22 |
| `{{monthly_accuracy}}` | Average accuracy this month | 76 |
| `{{active_words}}` | Words currently in active SRS rotation | 340 |
| `{{passages_read}}` | Graded passages completed | 8 |
| `{{billing_date}}` | Next billing date | March 15, 2026 |
| `{{end_date}}` | Subscription end date after cancellation | March 15, 2026 |
| `{{last_session_date}}` | Date of most recent session | February 3, 2026 |
| `{{last_accuracy}}` | Accuracy in most recent session | 71 |
| `{{projection_weeks}}` | Weeks until next HSK level readiness | 14 |
| `{{gating_skill}}` | Skill that's delaying next HSK level | listening |
| `{{month}}` | Current or report month name | February |
| `{{summary_stat}}` | Key stat for monthly subject line | "HSK 3 projection moved up 2 weeks" |
| `{{sessions_per_week}}` | Average sessions per week | 4.5 |
| `{{days_active}}` | Days with at least one session | 18 |
| `{{days_in_month}}` | Total days in the reporting month | 28 |
| `{{longest_streak}}` | Longest consecutive days active | 9 |
| `{{avg_session_length}}` | Average session duration in minutes | 14 |
| `{{listening_minutes}}` | Total listening practice minutes | 32 |
| `{{improved_skill}}` | Skill that improved most | tones |
| `{{old_level}}` | Previous diagnostic level for improved skill | 1 |
| `{{new_level}}` | New diagnostic level for improved skill | 2 |
| `{{accuracy_trend}}` | Direction of accuracy over time | "up 4% from last month" |
| `{{word_count}}` | Words mastered at milestone | 600 |
| `{{sessions_change}}` | Change in session count vs prior period | "+2" |
| `{{suggested_focus}}` | System-generated focus recommendation | "Add 2 listening sessions this week" |
