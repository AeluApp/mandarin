# Aelu Operating Doctrine
## Gold-Standard Principles for a Mandarin Learning App

Compiled 2026-03-09. Research synthesis across SLA, cognitive science, UX, and product design.

This document defines the constitution of Aelu — the operating principles that govern how learning works, how users stay, how trust is earned, how quality is measured, and how product choices compound. It complements the existing standards for [Chinese writing](chinese_writing_standard.md), [storytelling](storytelling_standard.md), and [brand identity](../BRAND.md).

---

## Table of Contents

1. [Pedagogy](#1-pedagogy)
2. [Assessment](#2-assessment)
3. [Feedback](#3-feedback)
4. [Curriculum Design](#4-curriculum-design)
5. [Onboarding](#5-onboarding)
6. [Habit Design](#6-habit-design)
7. [Motivation Design](#7-motivation-design)
8. [Personalization](#8-personalization)
9. [Trust and Authority](#9-trust-and-authority)
10. [Premium Product Feel](#10-premium-product-feel)
11. [UX Writing and Interaction Design](#11-ux-writing-and-interaction-design)
12. [Instrumentation](#12-instrumentation)
13. [Retention Diagnostics](#13-retention-diagnostics)

---

## 1. Pedagogy

Full research: [sla_pedagogy_research.md](../sla_pedagogy_research.md)

### Core Cycle

Every learnable item progresses through this pipeline:

```
ENCOUNTER → NOTICE → RETRIEVE → PRODUCE → ELABORATE → SPACE → INTERLEAVE → AUTOMATE
```

The app's job is to move items through this pipeline efficiently, spending more time at stages where the learner struggles.

### Vocabulary

- **Nation's Four Strands**: Balance time across meaning-focused input (reading/listening), meaning-focused output (production tasks), deliberate study (drills), and fluency development (speed practice on mastered items). Track time in each strand and nudge toward balance.
- **Involvement Load**: Avoid "show definition, press next." Even initial teaching should require search (tap to reveal) or evaluation (choose between options). Composition beats cloze beats reading-with-gloss.
- **Generation Effect**: Before showing a new word's meaning, ask the learner to guess. Wrong guesses are preparation, not failure. ~40% retention boost.
- **Receptive-to-Productive Continuum**: Track each word across 8 stages (no knowledge → flexible cross-register use). Drill types escalate: recognition → recall → constrained production → free production.
- **Mandarin-specific**: Characters are not words (teach words in context). Tone is part of the word (test from day one). Measure words paired with nouns. Homophones disambiguated via characters, never pinyin alone.

### Grammar

- **Skill Acquisition (DeKeyser)**: Declarative rule → procedural practice → automatization. Add time pressure only after accuracy is established. Never proceduralize errors.
- **Noticing (Schmidt)**: Highlight target structures in reading. Show learner's attempt vs. target side-by-side. Use minimal pairs to force discrimination.
- **Explicit + Implicit**: Lead with brief, clear rule (≤3 sentences). Follow with meaningful practice. Revisit via reading exposure weeks later without re-explaining.
- **Interleaving**: Block for initial learning (5-8 focused reps), then immediately interleave with prior structures. Never let a session be all one type.

### Retrieval Practice

- Default to testing, never re-presenting. Even a 1-second generation attempt before reveal activates the testing effect.
- Target 80-85% accuracy — the desirable difficulty zone. If >90%, increase difficulty. If <65%, reduce it.
- Never let learners self-assess difficulty. They systematically overestimate knowledge. Use objective data.
- Use Bjork's four desirable difficulties: spacing, interleaving, retrieval practice, generation.

### Anti-Patterns

No passive word lists. No recognition-only testing called "known." No massed single-session practice. No correcting every error simultaneously. No teaching tones separately from words. No input without output.

---

## 2. Assessment

### Philosophy

Every drill IS learning. Retrieval practice strengthens memory. The system is not "testing" — it is providing structured retrieval opportunities. Remove all testing language from UI.

### Multi-Dimensional Mastery

A word is not "known" until demonstrated across multiple dimensions of Nation's framework:

| Dimension | Receptive | Productive |
|-----------|-----------|------------|
| Form | Recognize when heard/seen | Pronounce/write correctly |
| Meaning | Select meaning from options | Supply meaning from memory |
| Use | Recognize collocations/patterns | Use in appropriate context |

**Vocabulary strength hierarchy** (Laufer & Goldstein):
1. Passive recognition (see word → select meaning)
2. Active recognition (see meaning → select word)
3. Passive recall (see word → supply meaning)
4. Active recall (see meaning → supply word)

A word marked "mastered" must pass recall (levels 3-4), not just recognition.

### Mastery Criteria

A word is considered "known" only when:
- Correctly recalled (not just recognized) at least twice at intervals ≥14 days apart
- Demonstrated in at least two different drill formats
- No incorrect responses in the most recent 3+ encounters

### Separate Constructs

- **Tone vs. meaning**: Score and track separately. Knowing a character means "horse" but marking it tone 2 instead of tone 3 = meaning knowledge without tone knowledge.
- **Character vs. word**: A learner may know 高兴 as a unit but not 高 or 兴 independently.
- **Recognition vs. production**: Track per item AND per format independently.

### MC Question Design

- Stem must be answerable without seeing options.
- Distractors from real confusion categories: tonal neighbors (买/卖), visual similarity (大/太/犬), semantic field (高兴/开心/快乐), L1 false friends.
- All options same length, form, specificity. 4 options. No negatively stated stems.
- Log which distractor was chosen — this diagnoses the error type.

### Adaptive Difficulty

- Target 50-70% chance of correct answer for maximum information gain.
- Track difficulty per item AND per format (recognition vs. recall have different difficulty).
- Enforce minimum intervals between exposures of the same item.
- Multi-stage structure: warm-up block, then branch up/down based on performance.

### System Health Metric

Track the rate at which "mastered" items subsequently fail. If this exceeds ~10%, the mastery threshold is too low.

---

## 3. Feedback

### The Three Questions (Hattie & Timperley)

Every feedback message answers at least one:
1. Where am I going? (What was expected?)
2. How am I going? (Where does my answer diverge?)
3. Where to next? (What should I pay attention to?)

If a feedback message answers none of these, delete it.

### Feedback Levels

| Level | Use | Example |
|-------|-----|---------|
| Task | Every drill | Correct/incorrect + correct answer |
| Process | When error reveals systematic confusion | "买 is tone 3. Buy/sell differ by tone." |
| Self-regulation | After repeated failure | Strategy suggestion |
| Self ("You're smart") | Never | Proven detrimental in 1/3 of cases |

### Format

Every incorrect feedback has exactly two parts:
1. **The correction** (max 8 words)
2. **The explanation** (max 15 words)

Total: one line, ~20-25 words. If it needs more, it belongs in a grammar note.

### Hard Rules

1. Never show only the correct answer — always explain the distinction.
2. The error is in the answer, not in the learner. Subject = the language item.
3. No empty praise. Positive feedback is specific and process-level: "3 for 3 on tone 3 today."
4. No emotional language in either direction. No celebration, no consolation.
5. No "Don't worry" or "That's okay" — these presuppose worry and are patronizing.
6. Immediate feedback, always. Learner controls advance on errors.
7. Bold the correct form. Pinyin always has tone marks. No exclamation marks.

### Near-Misses

Acknowledge what is right before correcting what is wrong: "Right character. Tone is 3, not 2."

### Repeated Failure Escalation

| Tier | Trigger | Response |
|------|---------|----------|
| 1 | Failures 1-2 | Standard correction + explanation |
| 2 | Failure 3 | Change explanation angle. Add strategy suggestion. |
| 3 | Failure 4+ | Stop drilling current form. Decompose to simpler sub-skill. |

Never repeat the identical feedback string. Never increase emotional intensity.

---

## 4. Curriculum Design

### Sequencing

- **Communicative utility first**, not linguistic simplicity. "Order food" > "master measure words."
- **Vocabulary before grammar**, high-frequency before low-frequency. First 150 items by corpus frequency.
- **Recognition before production**, always. New items appear in recognition drills first (3-5 exposures), then production.
- **Dependency graphs**, not linear lists. Each grammar point lists prerequisites. Never introduce a point whose prerequisites aren't at comfortable recognition level.

### Spiraling Review

- **Same item, different angle** each return. Recognition → cloze → production → discrimination → contextual use.
- **Expand context** on each return. Definition → dialogue use → pragmatic nuance → register contrast.
- **SRS handles timing; curriculum handles the "how."** SRS alone = flat repetition. Spiral + SRS = expanding depth at expanding intervals.
- **Retrieval, not re-exposure.** Every review requires active recall before showing the answer.

### Introducing Difficulty

- **i+1 operationalized**: Drills where exactly one element is new; everything else within the learner's 80%+ accuracy set. Reading passages: no more than 5-8% unknown vocabulary.
- **One dimension at a time.** New grammar = familiar vocabulary. New vocabulary = simple grammar. New speed = familiar content.
- **Productive ambiguity.** After stable model of 了 as completion, introduce change-of-state use. Let the learner notice the mismatch before explaining.

### Multimodal Integration

Sequence: listen first → read second → recognize third → produce fourth → contextual use last.

All modalities hit the same item within 48 hours. Mix modalities within sessions (max 3 consecutive drills of same type). Audio quality is non-negotiable for a tonal language.

### HSK Alignment

- Use HSK as vocabulary pool, not curriculum skeleton. Sequence by communicative utility, dependency, and frequency.
- Allow strategic out-of-level items for practical need.
- Track HSK coverage as one metric among several, not the primary goal.
- Supplement HSK gaps with corpus frequency data (SUBTLEX-CH, BCC).

---

## 5. Onboarding

### First 60 Seconds

Respect time. First interactive element within 30 seconds. Account creation = email + password only. Everything else after value. Never force a tutorial.

### Time-to-Wow: Under 90 Seconds

The first "wow" must be a genuine learning moment, not a UI trick. Within 90 seconds of active interaction, the learner should have learned something real.

### First Session Design (5 Minutes)

**Must happen:**
1. One genuine learning moment
2. One successful production
3. One demonstration of system intelligence ("You hesitated on third-tone sandhi — tomorrow includes more practice")
4. One clear forward path
5. One identity signal ("built for someone like me")

**Must NOT happen:**
- Mandatory tutorials
- Extensive preference collection before value
- Feature overwhelm (show the drill, not the dashboard)
- Artificial urgency (no streak mentions)
- Cultural/linguistic overwhelm ("Mandarin has four tones" — let them hear tones before explaining tones)

### Session Contract

State duration upfront. Deliver precisely. After first session, ask: "How many minutes per day?" Design every session to fit.

### Second Session

Must prove the system remembers. Open with review of session 1 items, adapted to their performance. Introduce items that connect to session 1. End with: "You now know X items."

### Identity + Competence

- **Identity signals**: Clean adult design, direct copy, real scenarios (business, travel, not "the cat is on the table"), metalinguistic insights.
- **Competence signals**: Debunk difficulty myths early (no conjugation!), normalize tone difficulty, show concrete progress. Include one moment of productive struggle → success.

---

## 6. Habit Design

### Build for the Worst Day

Minimum viable session: 2-3 items, under 90 seconds. If the behavior fires, people often do more voluntarily. Never require more.

### Anchor to Routines, Not Notifications

The prompt lives in the learner's life, not in the app's notification system. Help learners identify their anchor moment.

### Emotion Creates the Habit

The feeling of "I actually remembered that" wires the habit faster than 100 joyless repetitions. The moment of recall success should feel clean and real, not buried under animations.

### Streaks: Show Consistency, Not Counters

A heatmap or rhythm pattern ("5 of 7 days this week") respects effort without creating a fragile counter. No number to protect. No guilt when broken.

### Reminders

- Informational only: "12 items ready — 5 minutes." Never emotional: "We miss you!"
- Learner controls frequency and tone.
- No sad faces, no "you're falling behind," no loss framing.

### Progress Visibility

- Show retention, not completion. "187 items reliably recalled" > "62% of HSK 2 complete."
- Show trajectories, not snapshots. Graphs over time.
- Distinguish short-term from long-term memory. "Active items" vs. "stable items."
- Make the forgetting curve visible. The learner becomes a partner in the process.

### Supporting the Human Side

- **Burnout**: Design for sustainable rhythm. Suggest shorter sessions when detecting long ones. Show spacing data — rest is how memory consolidates.
- **Shame**: Normalize errors structurally. Never compare to other learners. Frame difficulty as a property of the material.
- **Inconsistency**: Make re-entry frictionless. Show what survived the gap. No catch-up guilt.
- **Perfectionism**: Show native speakers make mistakes too. Reward approximation. Decouple speed from mastery.

---

## 7. Motivation Design

### Self-Determination Theory (Deci & Ryan)

| Need | Design response |
|------|----------------|
| **Autonomy** | Learner chooses what, when, how much. System suggests, never dictates. Skip/defer without penalty. Show rationale for scheduling. |
| **Competence** | Stay in flow zone. Show concrete evidence of growing ability. Scaffolding invisible. |
| **Relatedness** | Connect to real-world use, Chinese culture, learner's own goals. Storytelling creates emotional connection. |

### Dignity in Design

- No baby talk. "Great job!" → "Correct. Moving to 7-day interval."
- Explain the system. Partners, not subjects.
- Use adult language throughout. Data, not interpretations.
- Respect time explicitly. Show estimated duration.
- Give real data. Let the learner draw conclusions.

### Delight Without Childishness

- Delight through insight (radical meaning connections, tone sandhi logic), not decoration.
- Sensory quality over sensory volume. One well-chosen session-complete sound > 50 effects.
- Surprise through content (unexpected cultural notes, fascinating etymology).
- The absence of noise is itself a pleasure.

### Identity Over Achievement

Dornyei's L2 Motivational Self System: motivation driven by the gap between actual self and "Ideal L2 Self."

- "You can now understand 73% of basic conversational Mandarin" > "You completed 50 lessons."
- "You can" language, not "You did" language.
- Functional milestones ("order food, give directions") > achievement trophies.
- Connect to learner's stated reasons.

### The Intermediate Plateau

- Change the metrics. Stop emphasizing vocab count; start emphasizing listening speed, tone accuracy, register range.
- Introduce new content types. Graded readers, media, dialogues.
- Make the plateau visible and expected. "You are in the intermediate consolidation phase."
- Show micro-gains. "Response time dropped from 3.2s to 2.1s this month."

---

## 8. Personalization

### What Stays Stable

- Linguistic accuracy (never simplify to the point of wrong)
- Sequencing dependencies (structural, hardcoded)
- Assessment standards (what counts as "known")

### What Adapts

- Presentation order within a level (based on learner interests)
- Drill type distribution (shift toward weaknesses)
- Pacing and session density (based on fatigue curves)
- Scaffolding intensity (more for struggling, less for quick mastery)

### What the Learner Controls

- Learning goals (HSK prep vs. conversational vs. reading)
- Content register preference (formal vs. colloquial)
- Review intensity (hammer weaknesses vs. balanced)
- Difficulty feel (challenge me more ↔ consolidate)

### Transparency Over Stealth

- Tell the learner when adapting: "More tone-pair drills because your 2/3 accuracy is below average."
- "Why this item?" expandable on any drill.
- Never hide regression. Show it honestly with context.

### Noise Prevention

- Don't personalize on insufficient data. Require ≥50 data points before adapting intervals.
- Cold start explicit: "First 2 weeks use standard intervals. Then we calibrate."
- Don't overreact to single sessions. Weight at max 20% of running average.
- Max one personalized suggestion per session.

### Empowerment Over Dependency

- Teach the learner to self-diagnose via their error patterns.
- Gradually reduce scaffolding. Goal: learner studies from raw Chinese text.
- "Study without adaptation" mode available. Confidence to let users override signals confidence.

---

## 9. Trust and Authority

### Earning Trust

- **Show the human skeleton.** Name methodology. Credit sources. Distinguish authored from generated content. Surface curation: "299 items from HSK 1-3, cross-referenced with SUBTLEX-CH."
- **The uncanny valley of correctness.** Never generate unvalidated sentences. For tone grading limitations, acknowledge them. Provide "check this" escape valves to real corpus examples.
- **Earned authority through specificity.** "Recall rate for tone pairs 2/4: 73% across 41 exposures" > "You're doing great with tones!" Quantify. Name limitations. Date content.

### Signals of Rigor

- **The syllabus test.** "Why am I learning this now?" must have a real answer. Make sequencing logic inspectable.
- **Research lineage.** Reference SLA principles by name, briefly, in context. 2-3 well-placed references > a bibliography.
- **Assessment that teaches.** Separate testing from practicing. Grade on dimensions (hanzi, pinyin, tone, meaning, measure word). Show error patterns, not just counts.

### Trust Killers

- **Inconsistency.** Single romanization standard. Consistent simplified/traditional. Consistent translation register. One "Congrats!" in an otherwise calm app breaks voice.
- **Praise inflation.** The single most common trust killer. "Great job!" after 3/10 correct is insulting.
- **Stale content.** Rotate example sentences. Acknowledge thin content. Never show placeholder text.

### Voice

Knowledgeable peer, not teacher. Second person sparingly. Explain the "why" without being asked. Direct about difficulty. Calibrated confidence — hedge for debatable things, distinguish prescriptive from descriptive.

Warmth through substance: a carefully written context note > "You can do it! 💪"

---

## 10. Premium Product Feel

### Premium = Confidence in Every Detail

- Pixel-perfect alignment across screen sizes.
- Consistent spacing scale (4/8/16/24/32/48px).
- Loading states (skeleton/fade-in), never blank screens.

### Premium = Respect for Time

- Studying begins within 2 taps.
- No unnecessary screens or animations.
- Session length user-controlled, not app-dictated.

### Restraint as Luxury

- Two typefaces + hanzi face (Cormorant Garamond, Source Sans 3, Noto Serif SC). Maximum.
- 3 functional colors + neutrals. If reaching for a new color, you've found a design problem.
- Limit motion vocabulary. Define exactly which motions the app uses (fade-in, slide-up). Every animation uses one of these.
- Remove before adding. The courage to leave space empty.

### Emotional Texture

- **Session start**: Sitting down at a desk. Brief orientation, then begin. Not a fanfare.
- **Session end**: Closing a book. Summary without judgment. No "Come back tomorrow!"
- **Error moments**: Gentle correction. Subtle warm salmon/coral, not aggressive red. 1-2 seconds for processing, learner controls advance.
- **Sound**: Rare and meaningful. Session start bell, session complete chord, silence during drills. Silence is a sound design choice.
- **Pacing**: Vary within session. Fast drills → slower grammar → medium mixed → contemplative reading → reflective review. 150-250ms transitions.

### Intelligence Signals

- **Typography**: Hanzi ≥32px for drills. Proper tone mark positioning. Correct quotation marks and punctuation per language.
- **Data as luxury**: Diagnostics presented like a Bloomberg terminal for language learning. Forecast confidence intervals. Personal item histories as narrative.
- **Anticipation**: Proactively note common confusions when presenting new items. Contextual grammar notes appearing only when relevant.
- **Smart defaults**: Temporal awareness (8 PM regular study time → straight to session; 2 PM unusual → show dashboard).

---

## 11. UX Writing and Interaction Design

### Voice

Calm, direct, specific. Knowledgeable peer. Assumes adult intelligence. Short by default, expandable on demand.

| Context | Approach |
|---------|----------|
| Drill prompt | Neutral, clear, 3-8 words |
| Correct answer | Factual, quiet. Confirm + one fact |
| Wrong answer | Specific, constructive. What was wrong + why |
| Session summary | Data-grounded. Numbers + one insight |
| Encouragement | Earned, rare. Only at real milestones |

### Cognitive Load

- **Single-task screens.** One job per screen. No streak/score/leaderboard during drills.
- **Chunk by linguistic unit.** New vocabulary in groups of 3-5, never 10-20.
- **Consistent spatial mapping.** Elements always in the same position.
- **No split attention.** Grammar explanation and referenced sentence must be visually adjacent.
- **Redundancy control.** Let the learner control which scaffolding layers are visible.

### Progressive Disclosure

| Layer | Visible | Content |
|-------|---------|---------|
| L1: Essential | Always | Hanzi, prompt, answer input |
| L2: Contextual | On tap | Pinyin, English, example sentence, grammar note |
| L3: Deep | On navigation | Full grammar, frequency data, related words, etymology |

L1 must be sufficient for any interaction. L2 discoverable without instruction. L3 rewards curiosity with genuine depth. Disclosure state remembered per learner.

### Microinteractions

**Intelligent** (information-carrying):
- Pinyin input showing matching hanzi candidates in real time
- Confidence-calibrated transitions (subtle cues for fluent vs. hesitant correct answers)
- Difficulty-aware pacing (silently insert easier items after error strings)
- Context-carrying transitions (highlight words seen in recent drills when they appear in reading)

**Avoid** (decorative/judgmental):
- Confetti, fireworks, particle effects
- Animated characters reacting to performance
- Sound effects encoding judgment
- Shake/vibrate on errors
- Badge pop-ups during active learning

---

## 12. Instrumentation

### Measure Learning, Not Usage

| Priority | Category | Key metric |
|----------|----------|------------|
| 1 | Learning outcomes | Items retained at 30-day interval with >80% accuracy |
| 2 | Learning behavior | Session accuracy trends, error type distributions |
| 3 | Product experience | Voluntary session extension, organic initiation |
| 4 | Business | D1/D7/D30 retention, conversion |

### Day-One Events

**Learning signal**: drill.answered (item, correct, response_time, attempt_number), review.scheduled→completed (interval, outcome), item.graduated (exposures, days to graduate)

**Behavior quality**: session timing, content exploration depth, help-seeking, skip patterns, error type patterns

**Product experience**: UI interactions at decision points, onboarding steps, settings changes

### Leading Indicators

| Domain | Indicator |
|--------|-----------|
| Efficacy | Graduation rate, retention curve slope, response time trend |
| Delight | Voluntary session extension, L3 exploration rate, organic session initiation |
| Trust | Skip rate on reviews, settings override rate, persistence through difficulty |
| Retention | D1/D7/D30/D90, session frequency trend, reactivation success rate |

### Vanity Metrics (Avoid)

- **DAU/MAU**: Gamed by notifications/streaks. Use active learning minutes per session.
- **Total items learned**: Only goes up. Use items retained at ≥14-day interval.
- **Streak length**: Measures app opens, not learning. Use rolling 14-day active session count.
- **Time in app**: More time can mean stuck. Use learning events per minute.
- **Completion rate**: Structurally determined by course design. Use proficiency gain per unit consumed.
- **NPS in isolation**: Measures enthusiasm, not efficacy. Segment by objective learning outcomes.

---

## 13. Retention Diagnostics

### Six Churn Types

| Type | Signal | Cause | Intervention |
|------|--------|-------|--------------|
| **Life** | Sudden stop, no prior decline | Job, travel, illness | Graceful dormancy. One message. Then silence. On return: cap re-entry at 10-15 items. |
| **Overwhelm** | Declining accuracy + declining frequency | Material too hard, review backlog | Pause new items automatically. Cap daily reviews. Surface message explaining the pause. |
| **Boredom** | High accuracy, declining frequency | Not challenged | Challenge injection: harder drill types, higher level content, new content types. |
| **Distrust** | Increasing skips, settings changes | Doesn't believe it's working | Show transfer evidence. Expose algorithm logic. Offer real-world diagnostic. Acknowledge plateau. |
| **Confusion** | Low feature adoption, wandering | UX failure | Guided reorientation. Simplify entry point. Usually first 7 days only. |
| **Low perceived progress** | Declining frequency despite adequate accuracy | Progress invisible | Reframe in tangible terms. Real-world benchmarks. "Look how far you've come" exercise. |

### Decision Tree

```
Accuracy declining?
├─ YES + Frequency declining → OVERWHELM
├─ YES + Frequency stable → Recalibrate difficulty
└─ NO
    └─ Frequency declining?
        ├─ YES + Depth declining → BOREDOM or LOW PROGRESS
        ├─ YES + Depth stable → LIFE CHURN
        └─ NO → Not at risk
```

### Intervention Principles

- Match intervention to diagnosis. "We miss you!" is wrong for every type.
- No guilt, ever. Not on exit, not on return.
- On reactivation: cap re-entry session at 10-15 items. Show what survived the gap. Gradually rebuild over 5-7 sessions.
- Track reactivation cohorts separately.

### Habit Zone Timing

| Phase | Days | Priority |
|-------|------|----------|
| Activation | 1-7 | Remove friction, deliver early wins |
| Formation | 7-30 | Optimize for "did they come back?" over "did they do a lot?" |
| Consolidation | 30-90 | Most vigilant about overwhelm/boredom signals |
| Committed | 90+ | Shift from retention to efficacy. Distrust is primary risk. |

---

## Summary: The Ten Commandments

1. **Every drill is a learning event.** Assessment and instruction are the same activity.
2. **Honest data over flattering signals.** Show real retention, real trajectories, real difficulty.
3. **Identity over achievement.** "I am a Mandarin speaker" > "I completed Level 3."
4. **Autonomy over compliance.** The learner chooses. The system suggests.
5. **Dignity in every interaction.** Calm, precise, respectful. No baby talk, no praise inflation.
6. **Transparency over magic.** Show the algorithm. Explain the scheduling. Partners, not subjects.
7. **Restraint as luxury.** Remove before adding. Silence is a feature.
8. **Difficulty as information.** Hard items are hard because Mandarin is hard, not because the learner is failing.
9. **Sustainable rhythm over maximum engagement.** Short sessions, flexible scheduling, graceful gaps.
10. **Earned trust through specificity.** Quantify. Name limitations. Date content. Credit sources.

---

## Sources

### Pedagogy & SLA
- Nation's Four Strands (Victoria University)
- Laufer & Hulstijn — Involvement Load Hypothesis
- DeKeyser — Skill Acquisition Theory
- Schmidt — Noticing Hypothesis
- Swain — Output Hypothesis
- Bjork — Desirable Difficulties
- Roediger & Karpicke — Testing Effect
- Kapur — Productive Failure
- Norris & Ortega — Explicit vs. Implicit Instruction
- Nakata & Suzuki — Interleaving Grammar Practice

### Assessment
- Nation — Word Knowledge Framework (9 dimensions, 18 aspects)
- Laufer & Goldstein — Vocabulary Strength Hierarchy
- Messick — Construct Validity
- Hattie & Timperley — Feedback Model

### Feedback
- Lyster & Ranta — Corrective Feedback Taxonomy
- Kluger & DeNisi — Feedback Meta-Analysis
- Dweck — Growth Mindset
- Li (2010) — Corrective Feedback Meta-Analysis

### Motivation & Habit
- Deci & Ryan — Self-Determination Theory
- Csikszentmihalyi — Flow Theory
- Dornyei — L2 Motivational Self System
- Fogg — Tiny Habits / Behavior Model
- Clear — Atomic Habits

### Curriculum
- Bruner — Spiral Curriculum
- Krashen — Input Hypothesis (i+1)
- Vygotsky — Zone of Proximal Development
- Cepeda et al. — Spacing Effect

### UX & Design
- Sweller — Cognitive Load Theory
- Mayer — Multimedia Learning
- Google HEART Framework
- Hattie & Timperley — Three Feedback Questions

Full citations in [sla_pedagogy_research.md](../sla_pedagogy_research.md) and individual research agent outputs.
