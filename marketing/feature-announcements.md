# Feature Announcement System — Aelu

A ready-to-use playbook for announcing features at every scale. Copy-paste from this document; adapt the bracketed details.

---

## Announcement Tiers

### Tier 1: Major Feature

**Criteria (must meet at least one):**
- Entirely new capability the app did not have before (e.g., graded reader, listening practice, new HSK level band)
- Opens the app to a meaningfully new audience (e.g., HSK 7-9 content brings advanced learners)
- Represents 2+ weeks of development effort AND is user-facing
- Would change how a reviewer describes the app in a comparison table

**Assets to produce:**
- Full blog post (600-900 words)
- Dedicated email to all users
- Social media campaign (3-5 posts over one week)
- Partner notification email (sent 1 week before public launch)
- Landing page update (feature added to marketing site)
- Changelog entry

**Examples:** Graded Reader, Listening Practice, Cleanup Loop, HSK 7-9 Content, Speaking Drills with Tone Grading

---

### Tier 2: Significant Enhancement

**Criteria (must meet at least one):**
- Meaningful improvement to an existing feature that changes how users interact with it
- Addition of multiple new items within an existing feature category (e.g., 3 new drill types)
- Visual or performance overhaul that users will notice immediately
- Requires a user to learn something new to benefit from the change

**Assets to produce:**
- Blog post (300-500 words)
- Mention in next scheduled newsletter
- 2-3 social posts
- Changelog entry

**Examples:** 3 New Drill Types, Dark Mode, UI Overhaul, Speed Improvements, Interleaving Enforcement, Adaptive Day Profiles

---

### Tier 3: Minor Update

**Criteria:**
- Everything that does not meet Tier 1 or Tier 2 criteria
- Bug fixes, small UX improvements, data corrections, content additions under 50 items, backend optimizations invisible to users

**Assets to produce:**
- Changelog entry only
- Optional single tweet if the fix is interesting or widely requested

**Examples:** Typo corrections in vocabulary data, fixed a crash on session end, adjusted spacing in drill view, added 12 context notes, corrected pinyin for 3 items

---

## Templates

---

### Blog Post Template -- Major Feature

```
Title: [Feature Name]: [What It Does For You]

[HOOK — 1-2 sentences. State the problem this feature solves or the
opportunity it creates. Write from the learner's perspective.]

[PROBLEM — 1 paragraph. Describe the gap. Why did this need to exist?
What were learners doing before, and why was it insufficient?]

[SOLUTION — 1-2 paragraphs. Describe the feature. What does it do?
How does a learner use it? Be specific and concrete. Avoid abstractions.]

[HOW IT WORKS — 1-2 paragraphs. Walk through the experience step by step.
Include a numbered list if there are distinct steps. This is where you
show, not tell.]

[SCREENSHOT PLACEHOLDER]
Alt text: [Describe what the screenshot shows]

[WHAT THIS MEANS FOR YOU — 1 paragraph. Connect the feature back to
the learner's goals. What changes in their study routine? What becomes
possible that wasn't before?]

[LIMITATIONS / WHAT'S NEXT — 1-2 sentences. Be honest about what v1
does not yet do. Mention what's planned.]

[CTA — Try it now. Link to the feature. One sentence.]

[RELATED — "If you like this, you might also want to check out [related
feature 1] and [related feature 2]."]
```

**Tone guidance:**
- Calm excitement. You built something useful and you're sharing it.
- Lead with the learner's experience, not your development process.
- Include at least one specific, concrete example (a real word, a real passage, a real scenario).
- No superlatives. No "revolutionary" or "game-changing."

---

#### Complete Example: "Graded Reader" Launch

**Title:** Graded Reader: Read Real Chinese From Day One

Every Chinese learner hits the same wall. You can recognize words on flashcards, but open anything written in actual Chinese and you're lost. The jump from "I know this word" to "I can read this sentence" is larger than most apps acknowledge.

That gap is why I built the graded reader.

**The problem with flashcard-only study**

Flashcards train one skill: isolated word recognition. That's necessary but not sufficient. Reading requires you to recognize words in context, parse grammar on the fly, and maintain comprehension across a full passage. These are different cognitive demands, and they need their own practice.

Most learners wait too long to start reading. They think they need to "know enough words first." I made this mistake myself -- I did flashcards exclusively for my first two months, and my reading ability lagged far behind my vocabulary count.

**What the graded reader does**

The graded reader gives you Chinese passages matched to your HSK level. HSK 1 passages use only HSK 1 vocabulary -- roughly 150 words. They're simple, but they're real Chinese in sentence form.

As you read, tap any word you don't know. You get instant pinyin and a definition, right there in the passage. No app-switching, no dictionary lookup. The reading flow stays intact.

Here's what happens behind the scenes: every word you tap gets logged. Those words become your drill material for the next session. This is the cleanup loop -- your real gaps become your real practice.

**How it works, step by step**

1. Open the graded reader and select a passage at your current HSK level.
2. Read through the passage. When you hit a word you don't recognize, tap it.
3. A tooltip shows pinyin, definition, and HSK level for that word.
4. Finish the passage. Your looked-up words are now queued.
5. Start your next drill session. The words you tapped appear as drills -- in context.

[SCREENSHOT: Graded reader view showing a Chinese passage with one word highlighted and the pinyin/definition tooltip visible]

**What this changes**

If you've been doing flashcard-only study, adding graded reading changes the quality of your vocabulary knowledge. You stop learning words as isolated facts and start learning them as parts of sentences. The memory is richer, and the retention is measurably better.

In my own study, words I encountered through reading stuck at roughly 40% higher retention than words I drilled from a list. That's not a controlled experiment -- it's internal data from a small sample. But the cognitive science on contextual encoding supports the pattern.

**What's coming**

This is v1 of the graded reader. It does passage-level reading with word glossing well. Sentence-by-sentence audio playback is next. Passage difficulty ratings beyond HSK level (accounting for grammar complexity, not just vocabulary) are on the roadmap.

**Try it now.** Open the app, navigate to the graded reader, and read your first passage. It takes about 3 minutes.

If you're using the graded reader, you might also want to explore [listening practice](/features/listening) for the audio side of comprehension, and [the cleanup loop](/features/cleanup-loop) to understand how looked-up words feed back into your drills.

---

### Blog Post Template -- Enhancement

```
Title: [Category] just got better: [Specific improvement]

[WHAT CHANGED — 1-2 paragraphs. Describe the enhancement concretely.
What's new or different? Be specific.]

[WHY — 1 paragraph. What problem did this solve? What feedback or data
motivated the change?]

[HOW TO USE IT — 1 paragraph or numbered list. What does the user need
to do (if anything) to benefit?]

[CTA — One line. Link if applicable.]
```

---

#### Complete Example: "3 New Drill Types Added"

**Title:** Drills just got better: 3 new practice types for reading and listening

Three new drill types are live today: **sentence reordering**, **listening cloze**, and **register identification**.

**Sentence reordering** gives you a Chinese sentence broken into shuffled segments. You drag them into the correct order. This drills grammar intuition -- you need to feel where the subject, verb, and object belong, not just recognize individual words. It's available for HSK 2 and above.

**Listening cloze** plays a sentence with one word blanked out in the transcript. You hear the full audio and fill in the missing word. This bridges listening and vocabulary -- you need both your ears and your word knowledge working together.

**Register identification** shows you a phrase and asks whether it's formal, informal, or slang. Knowing that 您好 is formal and 咋了 is colloquial matters in real conversations. This drill builds pragmatic awareness.

**Why these three?** Session data showed that learners with strong vocabulary recognition were still struggling with sentence-level comprehension and real-world register awareness. These drills target the gap between "I know words" and "I understand Chinese."

All three are active now. They'll appear automatically in your adaptive sessions when the scheduler determines they're relevant to your current level and weak areas. No action needed on your part -- just start a session.

The app now has 30 drill types. [See the full list.](/features/drills)

---

### Email Template -- Major Feature

```
Subject line options (pick one, adapt for the feature):
  1. [Feature name] is live — here's what it does
  2. New in Aelu: [one-line description]
  3. I built [feature name] because [personal reason]

Preview text: [One sentence that completes the subject line — this shows
in email clients before opening]

---

Hey —

[One-line summary: what shipped and what it does for the reader.]

[SCREENSHOT or GIF placeholder — the feature in action]

Three things to know:

- [Benefit 1 — what it does, stated as a user outcome]
- [Benefit 2 — how it's different from alternatives or previous behavior]
- [Benefit 3 — one specific, concrete detail]

[CTA button: Try it now →]

[1-2 sentences of personal context. Why I built this. Optional.]

— Aelu

P.S. [One sentence — either a limitation acknowledgment, a teaser for
what's next, or an invitation to reply with feedback.]
```

**Tone guidance:**
- From "Aelu" as the brand voice.
- Concise. The reader should be able to scan in 30 seconds.
- One CTA, not three. Don't dilute.

---

#### Complete Example: "Listening Practice" Launch

**Subject line options:**
1. Listening practice is live -- here's what it does
2. New in Aelu: adjustable-speed listening with transcript reveal
3. I built listening practice because my ears were two HSK levels behind my eyes

**Preview text:** Practice listening at your pace, then check what you actually caught.

---

Hey --

Listening practice is live in Aelu. You can now listen to graded Chinese passages at adjustable speed, with transcript reveal after you've listened.

[SCREENSHOT: Listening view showing the speed slider at 0.8x, play button, and hidden transcript area]

Three things to know:

- **Speed control from 0.5x to 1.5x.** Start slower than you think you need. Work up to natural speed over sessions.
- **Transcript stays hidden until you choose to reveal it.** This matters -- if the text is visible, your brain reads instead of listens. The learning happens in the gap between what you heard and what was actually said.
- **Words you missed feed into your drill queue.** After revealing the transcript, mark the words you didn't catch. They become drill material for your next session, just like the graded reader's cleanup loop.

[Try listening practice now -->]

I built this because my own diagnostics showed my listening at HSK 2 while my vocabulary was at HSK 3. That gap is common -- most learners I've talked to have it. Listening is slow to build, but targeted practice at the right difficulty level makes it measurable.

-- Aelu

P.S. This is v1. Speed control and transcript reveal work well. Sentence-by-sentence playback is next. If you have feedback after trying it, just reply to this email.

---

### Email Template -- Newsletter Mention

Format: a short block that slots into the regular biweekly newsletter.

```
**New this month: [Feature name].** [One sentence describing what it does
and why it matters.] [Try it →](link)
```

---

#### 3 Complete Examples

**Example 1:**
**New this month: Dark mode.** The app now follows your system preference for light or dark appearance -- warm stone tones in light mode, deep charcoal with teal accents in dark. [See it in action -->](/settings/appearance)

**Example 2:**
**New this month: Sentence reordering drills.** A new drill type that gives you a shuffled Chinese sentence and asks you to put it back in order -- grammar intuition, not just word recognition. [Start a session -->](/drill)

**Example 3:**
**New this month: HSK projection improvements.** The readiness forecast now factors in all four skills separately (vocabulary, listening, reading, tones) instead of a single blended score. Your projected date may have shifted -- check your diagnostics. [View your projection -->](/diagnostics)

---

### Social Media Templates

---

#### Twitter/X -- Major Feature (3-post sequence)

**Post 1: Announcement (what + why)**
```
[Feature name] is live in Aelu.

[2-3 sentences: what it does, stated as a user benefit. One concrete detail.]

[Link]
```

**Post 2: Demo/screenshot (how it works)**
```
Here's what [feature name] looks like in practice:

[Screenshot or GIF]

[2-3 sentences walking through what's shown in the image. Specific.]
```

**Post 3: User benefit (what this means for you)**
```
Why [feature name] matters if you're learning Chinese:

[2-3 bullet points, each one a specific user outcome]

[Link]
```

---

##### Complete Examples: "Cleanup Loop" Launch

**Post 1:**
The cleanup loop is live in Aelu.

Every word you look up while reading a graded passage now becomes a drill in your next session. Real gaps become real practice -- no generic word lists, just the vocabulary you actually struggled with.

aeluapp.com/features/cleanup-loop

**Post 2:**
Here's what the cleanup loop looks like in practice:

[SCREENSHOT: Side-by-side of the graded reader with a highlighted word, and the next day's drill session showing that same word as a drill item]

Left: I tapped 看见 while reading a story about visiting an old friend. Right: the next morning, 看见 appeared in my tone pair drill. The context from the story was still in my head. It stuck.

**Post 3:**
Why the cleanup loop matters if you're learning Chinese:

- You stop drilling random vocabulary lists and start drilling YOUR actual gaps
- Words come with context because you encountered them in a real passage first
- Retention improves because the memory has a richer association

This is the feature that changed my own study the most. aeluapp.com/features/cleanup-loop

---

#### Twitter/X -- Enhancement (single post)

**Template options:**

**Option A (what changed):**
```
Just shipped: [specific improvement].

[1-2 sentences on what it does and why it matters.]

[Link or "live now in Aelu"]
```

**Option B (data-driven):**
```
[Data point about the problem].

[1 sentence about the fix/improvement].

[Feature name] is live now. [Link]
```

**Option C (personal):**
```
I kept running into [problem] during my own study, so I built [solution].

[1 sentence on how it works.]

Live now in Aelu. [Link]
```

---

##### 3 Complete Examples

**Example 1 (Option A -- Adaptive Day Profiles):**
Just shipped: adaptive day profiles.

The app now adjusts session content based on time of day. Morning sessions lean toward new material when your brain is fresh. Evening sessions focus on review. No configuration needed -- it reads the clock.

Live now in Aelu.

**Example 2 (Option B -- Speed Improvement):**
Average drill session load time was 2.3 seconds. Now it's 0.4 seconds.

Rebuilt the session scheduler to precompute drill queues. Same adaptive logic, no more waiting.

aeluapp.com

**Example 3 (Option C -- Interleaving Enforcement):**
I kept doing the same drill type five times in a row, so I built interleaving enforcement.

The app now mixes drill types within a session -- vocabulary recognition, then a cloze, then a tone pair -- because varied practice produces better retention than blocked practice. The research is clear on this.

Live now in Aelu.

---

#### LinkedIn -- Major Feature

```
[Opening line — a specific, relatable observation about language learning.
Not a platitude. Something that makes the reader nod.]

[1-2 paragraphs: what the feature is, why it exists, how it works.
More context than Twitter, but still concise.]

[1 paragraph: the broader principle. Connect the feature to a learning
science concept, a product philosophy, or a personal insight. LinkedIn
readers want the "so what."]

[CTA — understated. "If you're learning Chinese..." or "Free for HSK 1-2."]

[3-5 hashtags, placed at the bottom, not inline]
```

---

##### Complete Example: "HSK Projection" Launch

Most Chinese learners know their HSK level as a single number. "I'm HSK 3." But that number hides a lot.

Your vocabulary might be HSK 3. Your listening might be HSK 2. Your tone accuracy might be barely HSK 1. If you walked into the HSK 3 exam with that profile, you'd pass the reading section and fail the listening section. The single number gave you false confidence.

I built HSK projection into Aelu to fix this. The system tracks four skills independently -- vocabulary recognition, listening comprehension, reading fluency, and tone accuracy -- and projects when you'll reach a given HSK level in each one. Not a single date. Four dates.

Here's what mine looks like right now: vocabulary is on track for HSK 4 by September. Listening won't get there until December. That three-month gap tells me exactly where to focus.

The projection updates after every session based on your actual performance data. It's not a guess -- it's a forecast, and it adjusts as your study patterns change.

The broader point: any skill assessment that collapses multiple dimensions into one number is lying to you. Language proficiency isn't one thing. Measuring it as one thing leads to studying the wrong skills.

If you're learning Mandarin and want an honest read on where you actually stand, Aelu is free for HSK 1-2 content.

#MandarinChinese #LanguageLearning #HSK #EdTech #SpacedRepetition

---

#### Instagram -- Major Feature

```
Caption:

[1-2 sentences: what the feature is, stated simply.]

[2-3 sentences: why it matters, written conversationally.]

[1 sentence: personal touch from Aelu.]

[CTA: link in bio, free tier mention.]

---

Hashtag set (copy-paste):
#MandarinChinese #LearnChinese #HSK #ChineseLanguage
#LanguageLearning #StudyChinese #MandarinLearning
#SRS #SpacedRepetition #LanguageApp
```

---

##### Complete Example: Graded Reader Launch

**Caption:**

The graded reader is live. Read Chinese passages at your HSK level, tap any word for instant pinyin and definition, and every word you look up becomes a drill.

Most learners wait too long to start reading because they think they need more vocabulary first. You don't. HSK 1 passages use about 150 words. Start reading now and let the gaps tell you what to drill next.

I built this because I spent two months doing nothing but flashcards and my reading went nowhere. This is the fix.

Free for HSK 1-2. Link in bio.

#MandarinChinese #LearnChinese #HSK #ChineseLanguage #LanguageLearning #StudyChinese #MandarinLearning #SRS #SpacedRepetition #LanguageApp #GradedReader #ChineseReading

---

#### Reddit -- Major Feature

**r/ChineseLanguage post template:**
```
Title: [Descriptive title — what you did or learned, not a product pitch]

Body:
[2-3 paragraphs of genuine value. Share the insight, the method, or the
data. The post should be useful even if the reader never clicks a link.]

[1 paragraph: mention the app naturally, as "something I built" not
"check out my product." Describe what it does, not what it's called.]

[Closing question: invite discussion. Make it about the community's
experience, not your product.]

[No link in the body. If someone asks, reply with the link.]
```

**r/languagelearning post template:**
```
Title: [Broader learning principle — applicable beyond Chinese]

Body:
[Frame the post around a learning method, insight, or data point.
Make it relevant to learners of ANY language.]

[Describe how you applied the principle to Chinese specifically.]

[Mention the app only if directly relevant, and only as context
("I built a tool to test this"), not as a pitch.]

[Closing question: broader than Chinese. Invite multi-language discussion.]
```

---

##### Complete Example: "27 Drill Types" Announcement

**r/ChineseLanguage post:**

**Title:** Why I stopped using flashcards as my only drill type (and what I replaced them with)

**Body:**

For my first few months studying Mandarin, my entire practice routine was flashcard reviews. Show character, recall pinyin and meaning. It worked for building vocabulary -- I could recognize HSK 2 words reliably.

But I couldn't do anything else with them. I couldn't hear them at natural speed. I couldn't use them in a sentence. I couldn't produce the correct tone. Flashcards were training one narrow skill and I was mistaking it for "knowing Chinese."

So I started categorizing what "knowing a word" actually requires and building drills for each dimension:

- **Recognition** (flashcard, multiple choice) -- can you identify it?
- **Production** (cloze deletion, sentence construction) -- can you use it?
- **Auditory** (listening cloze, tone pair, dictation) -- can you hear it?
- **Contextual** (register identification, collocation matching) -- do you know how it's used?
- **Tonal** (tone pair drills, minimal pair discrimination) -- can you distinguish and produce the tones?

I ended up with 27 distinct drill types across these categories. The system I built picks which type to use for each word based on where your weakness is. If you can recognize a word visually but can't hear it, you get listening drills for that word, not more flashcards.

The difference has been significant. Words I practice across multiple drill types stick better and transfer to real reading and listening. Words I only ever flashcarded... don't.

Has anyone else moved beyond pure flashcard practice? What other practice formats have helped your Chinese?

---

**r/languagelearning post:**

**Title:** Varied practice types improved my retention more than optimizing my SRS algorithm

**Body:**

I've been studying Mandarin for a while and went deep on SRS optimization -- intervals, ease factors, the whole FSRS rabbit hole. My retention improved, but it plateaued.

What broke the plateau wasn't a better algorithm. It was practicing the same vocabulary in different ways.

A flashcard tests recognition. A cloze deletion tests production. A listening exercise tests auditory processing. A sentence construction drill tests grammar and word order. These are genuinely different cognitive tasks, and practicing all of them for the same word creates a more durable memory than practicing one of them many times.

The research backs this up -- it's called "interleaving" and "varied practice." The idea is that mixing practice types forces your brain to reconstruct the memory from different angles, which strengthens it.

I built a system with 27 drill types across five categories (recognition, production, auditory, contextual, tonal) for my Chinese study. The scheduler picks the drill type based on which skill dimension is weakest for each word. The result: words practiced across 3+ drill types have roughly 35% higher 7-day retention than words practiced with only one type.

This principle isn't specific to Chinese. If you're studying any language and your only practice is flashcards, try adding even one other format -- cloze deletion, listening discrimination, or sentence construction. The variety itself is the intervention.

What practice formats do you use beyond flashcards? Curious whether this matches other people's experience across different languages.

---

### Partner Notification Email

**When to send:** Tier 1 features only. Send 7 days before public announcement.

**Template:**

```
Subject: Heads up: [feature name] launches [date]

Hey [partner name] —

Quick heads up: [feature name] goes live on [date]. I wanted you to
know before the public announcement so you can plan content if you
want to.

**What it is:**
[2-3 sentences describing the feature.]

**Talking points you can use:**
- [Point 1 — user benefit, stated simply]
- [Point 2 — what makes it different from alternatives]
- [Point 3 — specific detail or data point]

**Screenshot:**
[Attached or linked — high-res, both light and dark mode]

**Your affiliate link reminder:**
Your referral link is [link]. Cookie lasts 90 days. You earn [X]%
recurring on any paid signups.

**Timeline:**
- [Date]: Public blog post + email to all users
- [Date]: Social media campaign begins
- [Date]: Feature goes live (if not already live)

No pressure to post about this. Just keeping you informed. If you want
early access to test the feature before launch, reply and I'll set
you up.

— Aelu
```

---

#### Complete Example: Listening Practice Partner Notification

**Subject:** Heads up: Listening practice launches March 15

Hey --

Quick heads up: listening practice goes live in Aelu on March 15. I wanted you to know before the public announcement so you can plan content if you want to.

**What it is:**
Graded listening practice with adjustable speed (0.5x to 1.5x) and transcript reveal. Learners listen to a passage at their HSK level, then reveal the transcript to check what they caught. Words they missed feed into their drill queue through the cleanup loop.

**Talking points you can use:**
- Most Chinese learners have stronger reading than listening. This targets the gap with focused, level-appropriate audio practice.
- Speed control lets learners start below natural speed and work up gradually -- no more "too fast, can't understand anything" frustration.
- Integrates with the cleanup loop: words you miss while listening become drills, just like words you look up while reading.

**Screenshot:**
[Attached: listening-practice-light.png, listening-practice-dark.png -- 1920x1080]

**Your affiliate link reminder:**
Your referral link is aeluapp.com/?ref=[CODE]. Cookie lasts 90 days. You earn 20% recurring on any paid signups through your link.

**Timeline:**
- March 8: This email (you're getting it now)
- March 14: Teaser post on social media
- March 15: Public blog post + email to all users + feature goes live
- March 15-22: Social media campaign (3 posts)

No pressure to post about this. Just keeping you informed. If you want early access to test listening practice before launch, reply and I'll set you up.

-- Aelu

---

### Changelog Entry

**Format:**
```
[YYYY-MM-DD] — [Category] — [Title] — [Description (1-2 sentences)]
```

**Categories:**
- **New Feature** — entirely new capability
- **Enhancement** — improvement to existing feature
- **Fix** — bug fix
- **Content** — vocabulary, passages, or other learning content additions/corrections
- **Performance** — speed, efficiency, or resource usage improvements

---

#### 10 Complete Examples

```
2026-02-15 — New Feature — Graded Reader — Read Chinese passages at your HSK level with tap-to-gloss. Every word you look up feeds into your drill queue.

2026-02-12 — New Feature — Listening Practice — Adjustable-speed audio for graded passages with transcript reveal. Speed range: 0.5x to 1.5x.

2026-02-10 — Enhancement — 3 New Drill Types — Added sentence reordering, listening cloze, and register identification drills. Total drill types: 30.

2026-02-08 — Enhancement — Dark Mode — App now respects system appearance preference. Warm dark theme with charcoal base and teal accents.

2026-02-06 — Fix — Session Timer Accuracy — Fixed a bug where the session timer counted time spent on the summary screen. Timer now stops when the last drill is answered.

2026-02-04 — Content — 45 New Context Notes — Added usage context notes for HSK 3 vocabulary items covering register, common collocations, and example sentences.

2026-02-02 — Performance — Drill Queue Precomputation — Session load time reduced from 2.3s to 0.4s by precomputing drill queues during idle time.

2026-01-30 — Fix — Tone Pair Scoring — Corrected an issue where 3rd-3rd tone sandhi pairs were being scored as incorrect when the learner correctly identified the sandhi pattern.

2026-01-28 — Content — HSK 7-9 Vocabulary — Added 1,200 HSK 7-9 vocabulary items with pinyin, definitions, and HSK level tags.

2026-01-25 — Enhancement — HSK Projection Overhaul — Readiness forecast now projects four separate dates (vocabulary, listening, reading, tones) instead of one blended estimate.
```

---

## Announcement Calendar Framework

### Pre-launch (1 week before)

| Day | Action | Owner | Notes |
|-----|--------|-------|-------|
| Day -7 | Partner notification email | Aelu | Tier 1 only. Use partner template above. |
| Day -3 | Teaser post on social media | Aelu | One post. "Something's coming" framing. No details, just a hint. Example: "Been working on something for the listening gap. More on [date]." |
| Day -1 | Preview email to existing users | Aelu | Short. "Tomorrow: [feature name]. Here's a 1-sentence preview." Builds anticipation without spoiling the full announcement. |

### Launch day

| Hour | Action | Notes |
|------|--------|-------|
| Hour 0 | Blog post goes live | Publish to blog/site. Ensure screenshots are loaded and links work. |
| Hour 0 | Email sent to all users | Use major feature email template. Send within 30 minutes of blog post. |
| Hour 1 | Social post #1 (announcement) | Twitter/X. The "what + why" post. |
| Hour 4 | Social post #2 (demo/screenshot) | Twitter/X. The "how it works" post with visual. |
| Hour 8 | Reddit/community post | r/ChineseLanguage or r/languagelearning. Only if the feature provides genuine community value. Use value-first template. |

### Post-launch (1 week after)

| Day | Action | Notes |
|-----|--------|-------|
| Day +2 | Social post #3 (user angle) | Twitter/X. The "what this means for you" post. Or a tip about how to use the feature effectively. |
| Day +5 | Partner reminder | Short email: "Listening practice launched 5 days ago. Here's early feedback: [data point]. Reminder that your affiliate link is [link]." |
| Day +7 | Metrics review | Internal. Check: adoption rate (% of active users who tried the feature), completion rate, feedback received, social engagement. Document and file. |

---

## Feature Naming Conventions

### Rules

1. **Use plain English.** The user-facing name should be immediately understandable to someone who has never used the app. Exception: technical audiences (developers, SRS enthusiasts) can get the technical name as additional context, but the primary name is always plain English.

2. **Describe what the user does, not the internal architecture.** The user doesn't "engage the encounter-aware scheduling subsystem." They "start a drill session." Name features from the user's perspective.

3. **Prefer verbs and action-oriented nouns.** "Cleanup Loop" (describes a cycle of action). "Tone Trainer" (describes what you do). "Graded Reader" (describes the activity). Avoid passive or abstract names.

4. **Two words maximum for the feature name.** If it takes more than two words, the name is too complicated. The description can be longer; the name is short.

5. **No version numbers in user-facing names.** Internally it might be "scheduler v3." Externally it's "adaptive scheduling" or "smart scheduling."

6. **Test: can you explain the feature in one sentence using its name?** "The cleanup loop turns words you look up into drills." If the name doesn't fit naturally into a sentence like that, rename it.

### Current Feature Name Registry

| # | Internal Name | User-Facing Name | One-Line Description |
|---|---------------|-----------------|---------------------|
| 1 | cleanup_loop | Cleanup Loop | Words you look up while reading become drills in your next session. |
| 2 | graded_reader | Graded Reader | Read Chinese passages matched to your HSK level with tap-to-gloss. |
| 3 | listening_practice | Listening Practice | Listen to graded audio at adjustable speed with transcript reveal. |
| 4 | tone_grading | Tone Trainer | Speaking drills that grade your tone accuracy using audio analysis. |
| 5 | hsk_projection | HSK Projection | Forecast when you'll reach a given HSK level across four skill dimensions. |
| 6 | diagnostics | Diagnostics | See your strengths and weaknesses across vocabulary, listening, reading, and tones. |
| 7 | adaptive_scheduler | Adaptive Sessions | The system picks what you need to practice based on your performance data. |
| 8 | context_notes | Context Notes | Usage notes, collocations, and register information attached to vocabulary items. |
| 9 | interleaving | Drill Mixing | Drills alternate between types within a session for better retention. |
| 10 | day_profiles | Day Profiles | Session content adjusts based on time of day -- new material in the morning, review in the evening. |
| 11 | streak_counter | Streak Counter | Tracks consecutive days of study. Displayed without pressure or gamification. |
| 12 | momentum_indicator | Momentum | Shows whether your study consistency is building, steady, or fading. |
| 13 | focus_command | Focus Mode | Narrow your session to a specific HSK level, skill, or weak area. |
| 14 | speaking_drill | Speaking Practice | Record yourself and get tone accuracy feedback. |
| 15 | web_ui | Web Interface | Browser-based interface with the Civic Sanctuary visual design. |
| 16 | dark_mode | Dark Mode | Warm dark theme that follows your system appearance preference. |
| 17 | hsk_7_9 | HSK 7-9 Content | Advanced vocabulary and content for the new HSK 3.0 upper levels. |
| 18 | register_drills | Register Drills | Practice identifying formal, informal, and slang usage. |
| 19 | self_improvement | Self-Improvement | The system identifies its own scheduling weaknesses and adjusts. |
| 20 | forecasting | Forecasting | Data-driven projections for skill development and session planning. |

---

## Example Announcements -- Complete Campaigns

---

### Campaign 1: "The Cleanup Loop" (Tier 1 -- Major)

---

#### Blog Post

**Title:** The Cleanup Loop: Every Word You Look Up Becomes Practice

There's a gap in how most people study Chinese. You drill vocabulary from a list. You read something in Chinese. The words on the list and the words in the passage barely overlap. You're studying one version of the language and encountering another.

The cleanup loop closes that gap.

**The problem with separate study and reading**

Here's a pattern I fell into for months: I'd drill my Anki deck in the morning (HSK 3 vocabulary, neatly organized by lesson). Then I'd try to read a Chinese article or graded passage and hit words I didn't know -- words that weren't in my deck, or words I'd "learned" but couldn't recognize in context.

Two study activities. Almost zero connection between them. The flashcards didn't know what I was reading. The reading didn't inform my flashcards.

This is how most language apps work. The curriculum is generic. It doesn't adapt to what you're actually encountering.

**What the cleanup loop does**

The cleanup loop connects reading and drilling into a single cycle:

1. You read a graded Chinese passage at your HSK level.
2. When you hit a word you don't know, you tap it for instant pinyin and definition.
3. Every word you tap gets logged by the system.
4. Your next drill session prioritizes those exact words.
5. After drilling, you go back to reading. The cycle continues.

The result: you're never drilling random vocabulary. You're drilling the specific words you actually struggled with, in the order you encountered them, with the reading context still fresh in your memory.

**Why context changes everything**

When I drill the word 看见 after reading a story where someone "看见了一个老朋友" (saw an old friend), the memory has texture. There's a scene attached to it -- a person, a situation, an emotional register. When I drill 看见 from a flat word list, it's just characters mapped to a definition. The contextual version sticks. The flat version fades.

This isn't just my experience. Cognitive science calls this "encoding specificity" -- memories are stronger when retrieval conditions match encoding conditions. You encountered the word while reading; drilling it in a reading-adjacent context reinforces the original memory trace.

**What this looks like in practice**

I read a passage about a student's morning routine yesterday. I tapped three words: 刷牙 (brush teeth), 出门 (go out / leave the house), and 公交车 (bus). This morning, all three appeared in my drill session. One as a cloze deletion in a sentence, one as a tone pair, one as a multiple choice recognition drill.

I got 刷牙 right immediately -- the image of someone brushing their teeth before school was vivid. I missed the tone on 公交车 -- I'll see it again tomorrow.

That's the loop: exposure, gap identification, targeted practice, return to exposure.

[SCREENSHOT: Split view showing a graded reader passage with a highlighted word on the left, and the next day's drill session featuring that same word on the right]

**What this means for your study**

If you've been doing flashcard-only study, adding the cleanup loop changes the relevance of every drill. You stop asking "why am I drilling this word?" because the answer is always "because you didn't know it yesterday." The motivation shifts from "the curriculum says so" to "I actually need this."

For my own study, words that entered my drill queue through the cleanup loop had roughly 40% higher 7-day retention than words from the standard HSK curriculum list. Same algorithm, same drill types -- the only difference was how the word entered the system.

**Limitations and what's next**

This is the cleanup loop as it exists today. It works for words looked up during graded reading. Support for words missed during listening practice is coming -- same principle, different input channel. I'm also working on surfacing the cleanup loop data in the diagnostics view so you can see patterns in what you're looking up over time.

**Try it now.** Open the graded reader, read a passage, tap the words you don't know, then start a drill session tomorrow morning. You'll see the loop in action.

If you're using the cleanup loop, you might also want to explore [graded reading](/features/reader) for more passages at your level, and [diagnostics](/features/diagnostics) to see how your reading gaps map to your overall skill profile.

---

#### Email

**Subject:** The cleanup loop is live -- your reading now feeds your drills

**Preview text:** Every word you look up becomes practice. Here's how.

Hey --

The cleanup loop is live in Aelu. Every word you look up while reading a graded passage now automatically becomes a drill in your next session.

[SCREENSHOT: Graded reader with a tapped word flowing into the next day's drill queue]

Three things to know:

- **Your drills are now personalized to your actual gaps.** No more generic vocabulary lists. You drill the words YOU didn't know, from the passages YOU were reading.
- **The context carries over.** Because you encountered the word in a real sentence first, the drill association is richer. Retention is measurably higher.
- **It works automatically.** Read a passage, tap the words you don't know, and the system handles the rest. Your next session will include those words.

[Try the cleanup loop now -->]

I built this because I was frustrated with the disconnect between my reading and my drills. I'd read Chinese and hit words I didn't know, then open my drill session and practice completely different words. The cleanup loop is the fix I wanted for my own study.

-- Aelu

P.S. This is the foundation for a lot of what's coming next. Listening practice will feed into the same loop -- words you miss while listening will become drills too. More on that soon.

---

#### 3 Tweets

**Tweet 1:**
The cleanup loop is live in Aelu.

Read a Chinese passage. Tap words you don't know. Those exact words become drills in your next session.

No generic word lists. Just: the words YOU struggled with yesterday are today's practice.

aeluapp.com/features/cleanup-loop

**Tweet 2:**
Here's the cleanup loop in action:

[SCREENSHOT: Before/after showing a tapped word in the reader becoming a drill item]

Yesterday I tapped 公交车 (bus) while reading a passage about a student's commute. This morning it appeared as a tone drill. I could still picture the passage. It stuck.

**Tweet 3:**
Why the cleanup loop works:

- Drilling words you actually encountered > drilling a generic list
- Context from reading makes the memory richer
- You stop asking "why am I learning this word?" because the answer is always "because I didn't know it yesterday"

Words from the cleanup loop retain ~40% better in my own data.

---

#### LinkedIn Post

Every language learning app has the same architecture problem: the study curriculum and the reading experience are disconnected.

You drill vocabulary from a preset list. You read content that uses different vocabulary. The overlap is partial at best. You're studying one version of the language and encountering another.

I built the cleanup loop in Aelu to fix this. The concept is simple: every word you look up while reading a graded Chinese passage automatically becomes a drill in your next study session. Your reading gaps directly inform your practice. No curation needed -- the system watches what you don't know and builds your next session around it.

The results from my own study: words that entered my drill queue through reading context had roughly 40% higher 7-day retention than words from the standard HSK curriculum list. Same scheduling algorithm, same drill types. The only variable was whether the word had a reading context attached to it.

The principle behind this -- that memory is stronger when encoding and retrieval contexts match -- is well-established in cognitive science. The cleanup loop is just the implementation: exposure, gap identification, targeted practice, return to exposure.

If you're learning Mandarin, the app is free for HSK 1-2 content. The cleanup loop works across all levels.

#MandarinChinese #LanguageLearning #SpacedRepetition #EdTech #SRS

---

#### Reddit Post (r/ChineseLanguage)

**Title:** Connecting reading practice to SRS drilling changed my retention significantly

**Body:**

I want to share a study approach that's made a noticeable difference in my Chinese retention.

For months, my routine was: drill Anki deck in the morning, try to read graded Chinese content separately. The problem was that the words on my flashcards and the words I was struggling with in passages barely overlapped. Two study activities with almost no connection.

What I changed: I started tracking every word I had to look up while reading, then drilling those specific words in my next SRS session. The word enters the drill system with reading context attached -- I remember the sentence, the situation, the story. When the drill comes up, I'm not retrieving a bare definition; I'm retrieving a scene.

The difference in retention has been significant. For my own data (not a controlled study, just internal tracking), words that I first encountered in a reading passage and then drilled had roughly 40% higher recall at 7 days compared to words from a standard HSK word list.

I think the mechanism is straightforward: the reading context gives the memory more hooks. 看见 isn't just "to see" -- it's the moment in a story where someone saw an old friend. The richer encoding makes for a more durable memory.

I built a system that automates this cycle -- tap a word while reading, it enters the drill queue. But the principle works with any combination of reading material and SRS tool. Read something at your level, note the words you looked up, add them to your Anki deck or whatever you use, and drill them within 24 hours while the context is fresh.

Has anyone else tried bridging reading and SRS this way? Curious whether the retention difference holds up for other people or if I'm just pattern-matching on my own data.

---

#### Changelog Entry

```
2026-03-01 — New Feature — Cleanup Loop — Words looked up during graded reading now automatically enter the drill queue for the next session. Drill type is selected based on the learner's weakest skill dimension for that word.
```

---

#### Partner Notification

**Subject:** Heads up: The cleanup loop launches March 1

Hey --

Quick heads up: the cleanup loop goes live in Aelu on March 1. This is probably the feature I'd most want you to know about -- it's the app's key differentiator.

**What it is:**
Every word a learner looks up while reading a graded Chinese passage automatically becomes a drill in their next session. Reading gaps feed directly into SRS practice. No manual deck-building, no generic word lists -- just the words the learner actually struggled with.

**Talking points you can use:**
- "Every word you look up becomes practice" -- the simplest way to explain it.
- Unlike standard SRS apps where you drill a preset curriculum, the cleanup loop drills YOUR actual gaps from YOUR actual reading.
- Words from the cleanup loop retain ~40% better than words from generic lists (developer's own data, not a formal study -- be clear about this if you cite it).

**Screenshot:**
[Attached: cleanup-loop-light.png, cleanup-loop-dark.png -- 1920x1080, showing the graded reader with a tapped word and the corresponding drill in the next session]

**Your affiliate link reminder:**
Your referral link is aeluapp.com/?ref=[CODE]. Cookie lasts 90 days. You earn 20% recurring on paid signups.

**Timeline:**
- February 22: This email (you're getting it now)
- February 27: Teaser post on social media
- March 1: Public blog post + email to all users + feature goes live
- March 1-8: Social media campaign (3 posts)

No pressure to post about this. If you want early access to test the cleanup loop before launch, reply and I'll set you up.

-- Aelu

---

### Campaign 2: "HSK 7-9 Content" (Tier 1 -- Major)

---

#### Blog Post

**Title:** HSK 7-9 Content: Advanced Chinese for the New Standard

The HSK exam is being overhauled. Starting July 2026, the level structure expands from 1-6 to 1-9, with significantly more vocabulary at the upper levels and mandatory speaking from Level 3 onward.

If you're an advanced learner or planning to reach advanced proficiency, this matters. And Aelu now has content for it.

**What's changing with HSK 3.0**

The current HSK tops out at Level 6 with roughly 5,000 words. The new HSK 3.0 adds three upper levels:

- **HSK 7:** ~5,636 words. Roughly equivalent to old HSK 5-6 but with revised vocabulary.
- **HSK 8:** ~8,840 words. Specialized vocabulary including academic and professional Chinese.
- **HSK 9:** ~11,092 words and 6,000 characters. Near-native proficiency target.

The new standard also restructures the lower levels. Old HSK 1-2 maps roughly to new HSK 1-3. Old HSK 3-4 maps to new HSK 4-6. The transitions aren't one-to-one, but the direction is clear: the new test is more granular and more demanding.

**What we added**

Aelu now includes 1,200 HSK 7-9 vocabulary items, each with:

- Pinyin and definitions
- HSK 3.0 level tags (7, 8, or 9)
- Context notes for high-frequency items
- Integration with all 27 drill types

These items work exactly like the rest of the vocabulary system. They appear in your adaptive sessions, they participate in the cleanup loop when you encounter them in advanced reading passages, and they're factored into your HSK projection.

**Who this is for**

If you're currently at HSK 5-6 (old scale) or HSK 6+ (new scale), this content gives you a clear path forward. The HSK projection now extends through Level 9, so you can see a realistic timeline for reaching advanced proficiency.

If you're earlier in your studies, this content won't appear in your sessions yet. The adaptive scheduler surfaces material at your level, so HSK 7-9 vocabulary stays out of your way until you're ready for it.

**Preparing for the new exam**

The biggest shift in HSK 3.0 isn't the vocabulary count -- it's the mandatory speaking component. From Level 3 onward, HSKK (the speaking test) is no longer optional. Tone accuracy in spoken production matters more than ever.

Aelu already includes speaking drills with tone grading. If you're targeting HSK 7+ on the new scale, building tone accuracy now will pay off. The content is in place; the practice tools are ready.

**What's next**

This is the initial HSK 7-9 vocabulary set. Content will expand as the HSK 3.0 specifications are finalized. Advanced graded reading passages (beyond HSK 6 difficulty) are in development. If you're at this level and have feedback on what vocabulary or content is missing, I want to hear it.

**Try it now.** If you're on a paid plan, HSK 7-9 content is available in your sessions. Check your HSK projection in diagnostics to see the updated timeline.

For more on the HSK 3.0 changes, see [HSK 3.0 overview](/resources/hsk-3) and [speaking practice](/features/speaking) for tone grading drills.

---

#### Email

**Subject line options:**
1. HSK 7-9 content is live -- advanced Chinese, new standard
2. New in Aelu: 1,200 vocabulary items for HSK 7-9
3. The new HSK goes to Level 9. Aelu is ready.

**Preview text:** 1,200 advanced vocabulary items for the new HSK 3.0 upper levels.

Hey --

HSK 7-9 content is live in Aelu. 1,200 advanced vocabulary items, tagged for the new HSK 3.0 standard, integrated with all 27 drill types and the adaptive scheduler.

[SCREENSHOT: HSK projection view showing projections through Level 9]

Three things to know:

- **1,200 items covering HSK 7, 8, and 9.** Each with pinyin, definitions, level tags, and context notes. Ready for drilling, cleanup loop, and diagnostics.
- **HSK projection now extends through Level 9.** You can see a realistic timeline for reaching advanced proficiency based on your current pace and performance.
- **Built for the new standard.** HSK 3.0 launches July 2026 with a 1-9 level structure and mandatory speaking. This content aligns with the new specifications.

[Check your updated HSK projection -->]

I added this because the new HSK timeline is coming fast and advanced learners shouldn't have to wait for content. This is the initial set -- it'll expand as the 3.0 specs are finalized.

-- Aelu

P.S. If you're at the HSK 7-9 level and find vocabulary that's missing or incorrectly tagged, reply to this email. Your feedback directly improves the content.

---

#### 3 Tweets

**Tweet 1:**
HSK 7-9 content is live in Aelu.

1,200 advanced vocabulary items for the new HSK 3.0 upper levels. Pinyin, definitions, context notes, integrated with all 27 drill types.

The new HSK goes to Level 9. Now the app does too.

aeluapp.com

**Tweet 2:**
What HSK 7-9 actually means:

HSK 7: ~5,636 words
HSK 8: ~8,840 words
HSK 9: ~11,092 words, 6,000 characters

The new standard launches July 2026. If you're an advanced learner, the vocabulary is in Aelu and ready to drill now.

**Tweet 3:**
HSK 3.0's biggest change isn't the vocabulary -- it's mandatory speaking from Level 3 onward.

Aelu already has speaking drills with tone grading. The HSK 7-9 vocabulary is now live too.

If you're preparing for the new exam, both the content and the practice tools are ready.

---

#### Changelog Entry

```
2026-02-15 — Content — HSK 7-9 Vocabulary — Added 1,200 vocabulary items for HSK Levels 7, 8, and 9 (new HSK 3.0 standard). Includes pinyin, definitions, level tags, and context notes. HSK projection now extends through Level 9.
```

---

### Campaign 3: "Dark Mode" (Tier 2 -- Enhancement)

---

#### Short Blog Post

**Title:** The app just got better: dark mode is here

Dark mode is live in Aelu. The app now follows your system appearance preference -- if your OS is set to dark, the app goes dark. No toggle needed.

**What it looks like**

The dark theme uses a warm charcoal base with teal accents and terracotta highlights. Chinese characters render in Noto Serif SC on a dark surface with enough contrast for comfortable reading without the harshness of pure black-on-white inverted.

This isn't a quick CSS invert. The entire color system was rebuilt for dark mode with dedicated tokens: surfaces, text, accents, correct/incorrect indicators, and interactive elements all have dark-specific values. Charts, diagnostics, and the graded reader all adapt.

Light mode is unchanged -- the same warm stone tones and teal accents. If you prefer light, nothing changes for you.

**Why it took this long**

Dark mode sounds simple. It's not, when you have inline styles, SVG elements, and a graded reader that needs to render Chinese text legibly at multiple sizes. Getting the contrast ratios right for character recognition -- not just readability, but the ability to distinguish similar characters like 己 and 已 in low-light conditions -- took more iteration than I expected.

The result is worth it. Studying at night or in dim environments is now comfortable without reaching for your brightness slider.

**How to use it**

Set your operating system to dark mode. The app follows automatically. On macOS: System Settings, Appearance, Dark. On most browsers, this is inherited from the OS.

Dark mode is live now for all users, free and paid.

---

#### 2 Tweets

**Tweet 1:**
Dark mode is live in Aelu.

Warm charcoal base, teal accents, and Noto Serif SC hanzi rendering designed for low-light character recognition. Follows your system preference automatically.

[SCREENSHOT: Side-by-side of light and dark mode showing the same drill]

**Tweet 2:**
The hardest part of dark mode wasn't the CSS. It was getting the contrast right for Chinese character recognition.

己 and 已 need to be clearly distinguishable at any size, in any lighting. That meant custom contrast ratios for the hanzi font, not just inverting the palette.

Worth the effort. Dark mode is live now.

---

#### Changelog Entry

```
2026-02-08 — Enhancement — Dark Mode — App now follows system appearance preference with a warm dark theme. Dedicated color tokens for all surfaces, text, accents, and interactive elements. Designed for comfortable Chinese character recognition in low-light conditions.
```

---

## Voice Notes for Feature Announcements

These rules apply to every piece of announcement content. Print this section and keep it visible when writing.

### What to do

- **Lead with the user benefit.** "You can now listen to graded passages at adjustable speed" not "I implemented a Web Audio API-based playback system with variable rate control."
- **Be specific about what shipped.** "27 drill types" not "many drill types." "0.4-second load time" not "faster loading."
- **Acknowledge limitations honestly.** "This is v1 of listening practice. Speed control and transcript reveal work well. Sentence-by-sentence playback is coming." Users trust you more when you're honest about boundaries.
- **Use the brand voice.** "We built this because..." not "We're excited to announce..." Aelu is the voice. Direct and personal.
- **Include concrete examples.** A real word, a real passage, a real scenario. Abstract descriptions of features don't land.
- **Be proud when warranted, and be specific about what you're proud of.** "I'm proud of how the cleanup loop turned out -- it's the feature that most changed my own study" is honest. "I'm thrilled to announce our revolutionary new feature" is hollow.

### What not to do

- **Never oversell.** "I added listening practice" not "I'm thrilled to announce the revolutionary new listening experience." If you catch yourself using "thrilled," "excited," "revolutionary," "game-changing," or "delighted" -- delete the sentence and start over.
- **No superlatives unless literally true.** "The only Chinese learning app with a cleanup loop" is fine if you've verified it. "The best Chinese learning app" is never fine.
- **No artificial urgency.** "Try it now" is a fine CTA. "Don't miss out!" is not. "Limited time" is never used. "Act now" is never used.
- **No praise inflation.** The app doesn't tell users "Great job!" and the announcements don't tell users "You're going to love this!" Respect the reader's ability to evaluate for themselves.
- **Keep it direct.** "We built this" not "We're thrilled to announce." The independent team voice is a strength — personal, not corporate.
- **No jargon in user-facing content without explanation.** "Spaced repetition" is fine -- most of the audience knows it. "FSRS with bayesian confidence dampening" belongs in technical-audience content only, and always with a plain-language explanation alongside it.

### Brand voice summary

- Calm, adult, data-grounded
- No praise inflation ("Great job!" becomes "Session complete. 14/16 correct.")
- No artificial urgency
- Honest about what works and what doesn't yet
- Aelu is the voice -- direct and personal, not corporate
- Every metric is defensible; every claim is specific
- It's okay to be proud. It's not okay to be hyperbolic.