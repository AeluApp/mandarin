# Aelu Operating Doctrine

What follows is not a brainstorm. It is a set of binding standards — the constitution that governs how Aelu teaches, measures, communicates, and earns trust. Every decision in the product should be traceable to one of these principles.

---

## 1. Pedagogy

**Standard: Durable learning through retrieval, not exposure.**

- **Vocabulary**: Teach through spaced retrieval with increasing generative demand. Recognition first (hanzi → English), then recall (English → hanzi), then production (compose a sentence using the word). The sequence matters — skipping stages creates the illusion of knowledge.
- **Grammar**: Never explain grammar in isolation. Every grammar point is introduced through a sentence the learner has already encountered in a passage or dialogue. Explanation follows noticing, not the reverse. The gold standard is Focus on Form (Long, 1991): draw attention to form when it arises naturally in meaning-focused input.
- **Corrective feedback**: Recasts over explicit correction. When the learner makes an error, show the correct form alongside their attempt without labeling it "wrong." The comparison teaches; the label shames.
- **Retrieval practice**: Every session must include retrieval from memory, not just recognition from options. At least one drill per session should require the learner to produce the answer without seeing it (typing pinyin, completing a sentence, translating without choices).
- **Recognition → active use**: The transition happens through graduated output demands: MC → fill-in-blank → sentence completion → free production. Aelu must track which stage each item is at and not credit "mastery" until the learner can produce it.
- **Explicit vs. implicit**: Default to implicit acquisition through comprehensible input (passages, dialogues). Use explicit explanation only when: (a) the learner has encountered the pattern 3+ times and still errors, or (b) the pattern is genuinely unintuitable from input alone (e.g., 把 construction).

**The enemy**: Coverage without retention. A learner who has "seen" 500 words but can produce 50 has been failed by the system.

---

## 2. Assessment

**Standard: Measure what the learner can do, not what the learner has seen.**

- **Fair assessment**: Never test vocabulary the learner hasn't encountered in context. Never test grammar the learner hasn't seen in at least two different contexts. Assessment should feel like a natural extension of practice, not a gotcha.
- **MC design**: Every distractor must be plausible at the learner's level. One distractor should be the most common confusion (tone pair, similar meaning, false friend). One should be from the same semantic field. One should differ in one specific dimension. If a distractor is never chosen, it is not doing its job — replace it.
- **True mastery vs. familiarity**: An item is not mastered until: (a) correct across 3+ drill types, (b) correct after a 7+ day gap, (c) correct in a productive context, not just recognition. The 6-stage mastery lifecycle (seen → passed_once → stabilizing → stable → durable → decayed) enforces this.
- **Adaptive difficulty**: Difficulty adjusts per-item based on the learner's history with that specific item, not globally. A learner who struggles with third-tone sandhi but excels at vocabulary should get harder tone drills and appropriately-leveled vocab drills simultaneously.
- **"Really knows"**: A word is really known when the learner can: recognize it in a new context, produce it without cues, and use it with correct tones. Fewer than three data points on any of these dimensions means the assessment is inconclusive.

**The enemy**: Inflated mastery metrics. A dashboard that shows 80% mastered when the learner can only recognize 80% and produce 30% is lying.

---

## 3. Feedback

**Standard: Exact, warm, and brief.**

- **Instructional feedback**: Tell the learner exactly what was wrong and exactly what's right, in one sentence. "你好 (nǐ hǎo) — you wrote ní hào. The first tone is third (falling-rising), not second (rising)." No padding. No "great try!"
- **Motivating correction**: Normalize error. "This tone pair confuses most learners at this stage." Frame errors as information about what to practice next, not as failures.
- **Brief explanations**: One sentence for the correction. One sentence for the pattern. If they need more, link to the grammar unit. Never lecture inside a drill.
- **Repeated failure**: After 3 consecutive failures on the same item, stop drilling it. Show the answer, explain the pattern, schedule it for review in 24 hours. Continuing to drill a stuck item teaches frustration, not Chinese.
- **Protecting confidence**: Never use words like "wrong," "incorrect," "failed," or "mistake" in learner-facing text. Use "not quite," "the expected answer was," "this one is tricky." The distinction matters emotionally even when it seems trivial.

**The enemy**: Robotic feedback ("Incorrect! The answer is X.") and saccharine feedback ("Amazing effort! You're doing great!"). Both destroy trust for different reasons.

---

## 4. Curriculum Design

**Standard: A coherent journey, not a pile of good moments.**

- **Sequencing**: HSK levels provide the skeleton. Within each level: high-frequency words first, grammar patterns introduced through those words, reading passages that use both, dialogues that model real use. The learner should never encounter a grammar drill for a pattern they haven't seen in context.
- **Spiraling review**: Every session contains 60% review and 40% new material. Review items are selected by retention urgency (half-life model), not recency. This prevents the common pattern of perpetually introducing new material while older material decays.
- **Introducing difficulty**: One new dimension at a time. New vocabulary in familiar grammar. New grammar with familiar vocabulary. New tones in familiar words. Never stack novelty.
- **Modality integration**: Reading, listening, speaking, and typing are not separate tracks. A word learned through reading should appear in a listening drill within 3 sessions, a typing drill within 5, and a speaking drill within 7. The scheduler enforces this through modality rotation.
- **HSK alignment without HSK imprisonment**: HSK word lists define the vocabulary corpus. HSK levels define the difficulty progression. But the learning experience is organized around themes and contexts (content lenses), not HSK numbers. The learner should feel they're learning to navigate a restaurant, not "doing HSK 2."

**The enemy**: A curriculum that is technically complete but emotionally incoherent — where the learner can't explain what they're learning or why it comes in this order.

---

## 5. Onboarding

**Standard: First session proves the product's thesis in under 5 minutes.**

- **Time-to-wow**: The learner should learn a real word, hear it pronounced correctly, and successfully recall it — all within the first 2 minutes. No setup screens. No preference questionnaires. No level selection (assess through doing). The thesis is: "you can learn Mandarin with this app, starting now."
- **First-session design**: 5 words. 3 drill types. 1 passage. 1 audio playback. The learner exits with something they didn't have before. Everything else (settings, profile, goals) comes after the first win.
- **"This is for me" + "I can do this"**: The first items should be at the learner's level (use a 3-question calibration, not a form). The aesthetic should communicate seriousness without intimidation. The Civic Sanctuary design does this: warm, quiet, adult.
- **What to never do in onboarding**: Never show empty states. Never ask questions the system could infer. Never show a dashboard before there's data to fill it. Never use the word "beginner" — use "starting from" instead.

**The enemy**: An onboarding that optimizes for information collection over learning experience. Every screen before the first drill is a screen where the learner might leave.

---

## 6. Habit Design

**Standard: Build return behavior through progress visibility, not manipulation.**

- **Healthy habits**: A study streak is a trailing indicator, not a goal. What matters is whether the learner is retaining what they've studied. Show retention metrics, not streak counts. If the streak counter exists, never make breaking it feel like failure.
- **Reminders**: One notification per day maximum. Content: "X items ready for review (~Y minutes)." Never guilt. Never urgency. Never "Your streak is about to break!"
- **Progress visibility**: Show what the learner can do now that they couldn't do a week ago. "Last week you knew 45 words. This week: 62. You can now understand basic restaurant conversations." Concrete, functional progress — not abstract numbers.
- **Supporting struggle**: When a learner's accuracy drops, the system should respond by reducing difficulty, not by sending motivational messages. When a learner goes inactive, the welcome-back message should acknowledge the gap without commenting on it: "Your schedule has been adjusted. Pick up whenever you're ready."

**The enemy**: Duolingo's streak anxiety model — effective for engagement metrics, corrosive for the relationship between learner and tool.

---

## 7. Personalization

**Standard: Adapt what matters. Leave stable what doesn't.**

- **What to adapt**: Review intervals (per-item, per-learner), drill type selection (based on accuracy by type), content difficulty (based on demonstrated level), session length (based on available time and day of week).
- **What to keep stable**: The curriculum sequence within a level. The assessment criteria for mastery. The feedback tone. The visual design. Stability in these areas builds trust — the learner knows what to expect.
- **Invisible adaptation**: The learner should feel that the app "just works" — items appear at the right time, difficulty feels right, sessions end when they should. They should never feel surveilled or manipulated by the algorithm.
- **Learner modeling**: Track per-item accuracy, per-drill-type accuracy, time-of-day performance, session length preferences, accuracy trend, and content lens engagement. Use these to inform scheduling. Never surface raw model parameters to the learner — translate them into actionable insights.

**The enemy**: Over-personalization of noise (adjusting to random session-to-session variation) and under-personalization of signal (ignoring a persistent weakness in tones).

---

## 8. Trust and Authority

**Standard: Warm but rigorous. Humble but precise.**

- **Building trust**: Aelu earns trust by being consistently correct. Every pinyin must be accurate. Every tone mark must be right. Every English translation must be natural. One error in pronunciation guidance destroys more trust than ten features build.
- **Serious pedagogy signals**: Show the learner's data honestly. Never hide poor performance behind euphemism. Say "your accuracy on third tones is 45% — here's targeted practice" rather than "you're making great progress!" Trust comes from treating the learner as an adult who can handle truth.
- **What undermines trust**: Inaccurate tones in TTS. Unnatural translations. Gamification that makes the experience feel childish. Empty praise. Inconsistency between what the system says and what the data shows.
- **Balance**: Authority ("this scheduling algorithm is based on memory research") + humility ("your experience may differ — adjust your targets anytime") + warmth ("learning is hard; this system is designed to make it less hard").

**The enemy**: Either clinical coldness (the system feels like a spreadsheet) or performative warmth (the system feels like it's trying too hard to be your friend).

---

## 9. Premium Product Feel

**Standard: Crafted, not decorated.**

- **What makes premium**: Consistency. Every screen uses the same type hierarchy, the same color palette, the same spacing system. No element looks like it was added later. Transitions are smooth. Loading states are designed, not default spinners.
- **Emotional texture**: The Civic Sanctuary aesthetic (warm stone, teal, terracotta) should feel like a place you want to spend time, not a tool you use and leave. Sound design matters — the session start chime, the correct answer tone, the session complete sound. These create ritual.
- **Intelligence signals**: The system should feel smart. Scheduling that adapts. Feedback that's specific. Diagnostics that explain themselves. Users should think "this knows what it's doing" without thinking "this is watching me."
- **What to avoid**: Decoration without purpose (gradients, shadows, animations that don't communicate state). Feature density that overwhelms. Settings pages with 50 options. Anything that makes the product feel "configurable" rather than "considered."

**The enemy**: Over-design (every element competing for attention) and under-design (functional but soulless). Premium lives in the middle: everything intentional, nothing gratuitous.

---

## 10. Instrumentation

**Standard: Track what changes decisions. Ignore what doesn't.**

- **Day-one events**: Session started, session completed, session abandoned (with timestamp and last drill index), drill answered (correct/incorrect/skipped, drill type, response time), item scheduled, item mastered (stage transition), reading passage opened/completed, audio played, error logged (with error type).
- **Leading indicators of efficacy**: 7-day retention rate (% of items still known after 7 days), session completion rate, accuracy trend (improving/stable/declining), modality coverage (% of items drilled in 2+ modalities).
- **Leading indicators of delight**: Session-to-session return rate, voluntary extra session rate (user studies beyond daily target), feature discovery rate (first use of diagnostics, reading, listening).
- **Leading indicators of trust**: Settings change rate (low = either trust or disengagement), error report rate (high = engaged enough to report), help page visits (high = confused or curious).
- **Vanity metrics**: Total registered users (says nothing about retention), total words "learned" (says nothing about mastery), streak length (says nothing about actual knowledge), session count (says nothing about quality).

**The enemy**: Tracking everything and analyzing nothing. Or worse: optimizing for vanity metrics that feel good in investor decks but don't predict learning outcomes.

---

## 11. Founder Operating Model

**Standard: Build in focused blocks. Review in honest retrospectives. Ship when ready, not when anxious.**

- **Weekly cadence**: Monday — review metrics, run diagnostics, plan the week. Tuesday-Thursday — build (code, content, design). Friday — test, review, write changelog. Weekend — optional study session as a user (dogfooding).
- **What to decide quickly**: Bug fixes, small UX improvements, content additions, test fixes. If it takes less than 2 hours and doesn't change architecture, just do it.
- **What deserves review**: Architecture changes, new dependencies, pricing changes, public-facing copy, anything that affects data integrity. Sleep on these.
- **Common traps**: Perpetual polish (the product is never "ready"). Feature creep disguised as user empathy. Building for hypothetical users instead of real ones. Comparing to competitors who have 50-person teams. Conflating "I enjoy building this" with "users need this."

**The enemy**: The builder's trap — spending all time building and no time learning whether what you built matters.

---

## Summary

These 11 standards define what Aelu is:

1. A **learning outcomes** company, not a content company
2. A system that measures **what learners can do**, not what they've seen
3. Feedback that is **exact, warm, and brief**
4. A **coherent journey**, not a feature collection
5. Onboarding that **proves the thesis in 5 minutes**
6. Habits built through **progress visibility**, not manipulation
7. Personalization that is **invisible and accurate**
8. Trust earned through **consistent correctness**
9. Premium that means **crafted, not decorated**
10. Instrumentation that **changes decisions**
11. A founder who **builds in blocks and reviews honestly**

Every feature, every design choice, every piece of content should be defensible against one of these standards. If it isn't, it doesn't belong in Aelu.
