# Aelu User Research Protocol

**Last Updated:** 2026-03-10
**Cadence:** 3-5 interviews per month (minimum). Research is not a one-time event.

---

## Phase 1: Screening (5 minutes)

### Purpose
Filter for people who match Aelu's target persona: motivated adult Mandarin learners who are willing to pay for tools.

### Screening Survey (Google Form or Typeform)

1. **What is your current Mandarin level?**
   - [ ] Complete beginner (0 knowledge)
   - [ ] Beginner (know some words/phrases, HSK 1-2)
   - [ ] Intermediate (can have basic conversations, HSK 3-4)
   - [ ] Upper intermediate (can read news articles with help, HSK 5-6)
   - [ ] Advanced (can function professionally in Mandarin, HSK 7+)

2. **Why are you learning Mandarin?** (select all that apply)
   - [ ] Career / business
   - [ ] Travel
   - [ ] Heritage / family connection
   - [ ] Academic requirement
   - [ ] Personal interest / challenge
   - [ ] Partner / spouse speaks Mandarin
   - [ ] Other: ___

3. **How many minutes per day do you typically practice Mandarin?**
   - [ ] 0 (not currently practicing)
   - [ ] 1-10 minutes
   - [ ] 10-30 minutes
   - [ ] 30-60 minutes
   - [ ] 60+ minutes

4. **What tools do you currently use?** (select all that apply)
   - [ ] Duolingo
   - [ ] HelloChinese
   - [ ] Anki
   - [ ] Pleco
   - [ ] Skritter
   - [ ] Private tutor
   - [ ] University/school class
   - [ ] Textbook (self-study)
   - [ ] YouTube / podcasts
   - [ ] None currently
   - [ ] Other: ___

5. **How much do you spend per month on Mandarin learning tools?**
   - [ ] $0
   - [ ] $1-10
   - [ ] $10-20
   - [ ] $20-50
   - [ ] $50+

6. **Would you be willing to do a 45-minute video interview about your Mandarin learning experience? ($25 Amazon gift card as thank-you.)**
   - [ ] Yes — Email: ___
   - [ ] No

### Screening Criteria
Prioritize participants who:
- Are HSK 1-4 (the beginner-intermediate range where Aelu has the strongest content)
- Actively practice (not "planning to start someday")
- Have tried at least one other tool (can compare experiences)
- Spend or are willing to spend money on learning tools

Deprioritize (but don't exclude):
- Complete beginners with no prior study (they haven't experienced pain points yet)
- HSK 7+ (Aelu's advanced content is less validated)
- People who only use free tools and are unwilling to pay

---

## Phase 2: Interview (45 minutes)

### Setup
- **Platform:** Zoom or Google Meet with recording enabled (get consent)
- **Recording consent script:** "I'd like to record this conversation so I can review it later. The recording won't be shared publicly. Is that okay?"
- **Notetaker:** If solo, use Zoom's transcript or Otter.ai. Don't try to take notes and conduct the interview simultaneously.

### Interview Guide (15 questions)

**Warm-up (5 min)**
1. Tell me about yourself and how you got interested in learning Mandarin.
2. Where are you in your Mandarin journey right now? What can you do in Mandarin today?

**Current Practice (10 min)**
3. Walk me through what a typical Mandarin study session looks like for you. What do you do, step by step?
4. What tools or apps do you use? What do you like about each one?
5. What frustrates you about the tools you use? What's missing?
6. Have you switched from one tool to another in the past year? What prompted the switch?

**Motivation and Goals (10 min)**
7. What would "success" in Mandarin look like for you? When would you feel like you'd "made it"?
8. What's the hardest part of learning Mandarin specifically? (Not language learning generally — Mandarin specifically.)
9. How do you stay motivated when progress feels slow?
10. Have you ever quit studying Mandarin for a stretch? What made you stop, and what brought you back?

**Product Concept (10 min)**
11. [Show Aelu briefly — 2-minute demo or screenshots] What are your first impressions?
12. What stands out to you, positively or negatively?
13. How does this compare to what you're currently using?
14. If this cost $14.99/month, what would need to be true for you to subscribe?

**Closing (5 min)**
15. If you could wave a magic wand and fix one thing about how you study Mandarin, what would it be?

### Probing Techniques
- "Tell me more about that."
- "Can you give me a specific example?"
- "What happened next?"
- "Why do you think that is?"
- Silence. Let the participant fill the gap. Don't rush to the next question.

### Things to Avoid
- Leading questions ("Don't you think X is great?")
- Asking about future behavior ("Would you use feature X?") — people are terrible at predicting their own behavior
- Showing excitement about your own product — stay neutral
- Defending design choices if the participant criticizes something

---

## Phase 3: Usability Test (30 minutes, can combine with interview)

### Purpose
Observe whether people can actually use Aelu without guidance. What they say matters less than what they do.

### Setup
- Participant shares their screen
- Give them a test account (not their own, to test onboarding from scratch)
- Use the think-aloud protocol: "As you go through this, please say out loud whatever you're thinking."

### 5 Tasks

**Task 1: Sign up and complete onboarding** (target: <3 minutes)
- Instructions: "Imagine you just heard about this app and want to try it. Go to [URL] and set up an account."
- Observe: Where do they hesitate? Do they understand the placement test? Do they complete it?
- Success: Account created, profile set, placement completed.

**Task 2: Start and complete a study session** (target: <10 minutes)
- Instructions: "Now try doing a study session."
- Observe: Do they find the "Start Session" button? Do they understand the drill types? Do they get confused by any drill?
- Success: Session completed, results shown.

**Task 3: Find progress for a specific HSK level** (target: <1 minute)
- Instructions: "Can you find out how you're doing with HSK 2 vocabulary?"
- Observe: Do they know where to look? Is the progress view intuitive?
- Success: They navigate to the progress/report view and identify HSK 2 stats.

**Task 4: Look up a word during reading** (target: <5 minutes)
- Instructions: "Go to the reading section and read a passage. If you see a word you don't know, look it up."
- Observe: Do they find the reader? Do they know how to tap/click a word? Does the lookup feel natural?
- Success: They open a passage, look up at least one word, and the word appears in vocab_encounter.

**Task 5: Change a setting** (target: <1 minute)
- Instructions: "Can you change how long your study sessions are?"
- Observe: Do they find settings? Is the option clear?
- Success: Setting changed.

### Metrics
- **Task completion rate:** % of participants who complete each task without help
- **Time on task:** Seconds from start to completion (or abandonment)
- **Error rate:** Number of wrong turns, misclicks, or confused pauses per task
- **SUS score:** Administer the System Usability Scale (10 questions, 5-point Likert) after all tasks

### SUS Questionnaire (post-test)
Administer the standard 10-item SUS. Score ranges:
- 68+ = above average usability
- 80+ = good
- 90+ = exceptional
- Below 50 = significant usability problems

---

## Phase 4: Diary Study (2 weeks)

### Purpose
Understand real-world usage patterns over time, not just one-time impressions.

### Setup
- Recruit 5-10 participants from interview pool
- Provide a daily log template (Google Form, 2 minutes to complete)
- Compensate: $50 gift card for completing all 14 days

### Daily Log Questions
1. Did you practice Mandarin today? (Yes / No)
2. If yes, what did you do? (free text, 1-2 sentences)
3. If yes, how long? (minutes)
4. Did you use Aelu today? (Yes / No)
5. If yes, what did you do in Aelu? (free text)
6. If no, why not? (free text)
7. Anything notable today about your Mandarin learning? (optional)

### Analysis
After 14 days, look for:
- **Usage frequency:** How many days did they use Aelu out of 14?
- **Session patterns:** Do they use it at the same time each day? Morning? Evening?
- **Drop-off point:** If they stopped using Aelu, when and why?
- **Complementary tools:** What else do they use alongside Aelu?
- **Aha moments:** Any entry where they express surprise, delight, or frustration

---

## Deliverables

### After Each Interview Round (3-5 interviews)
1. **Interview summary** (1 page per participant): Key quotes, observed behavior, pain points, feature requests
2. **Pattern analysis** (1 page): Themes that appeared across multiple participants
3. **Action items** (bulleted list): Specific product changes suggested by the research, linked to backlog items

### After Each Usability Test Round
1. **Task completion matrix:** Participants x Tasks, pass/fail/partial
2. **SUS score:** Aggregate and per-participant
3. **Top 3 usability issues:** Ranked by severity (how many participants hit it x how blocked they were)

### After Each Diary Study
1. **Usage heatmap:** Days x participants, colored by usage intensity
2. **Retention curve:** What % of participants are still using Aelu on day 7? Day 14?
3. **Verbatim review:** Notable quotes from daily logs, categorized by theme

---

## Recruitment Channels

- Reddit: r/ChineseLanguage, r/MandarinChinese, r/languagelearning (post or DM active users)
- Discord: Mandarin learning servers (Refold, Comprehensible Chinese)
- HelloTalk / Tandem: Language exchange communities
- University language departments (bulletin boards, professor referrals)
- Existing Aelu users (once user base exists)

### Compensation
- Screening survey: Free (no compensation needed)
- 45-minute interview: $25 Amazon gift card
- Usability test (if combined with interview): Included in interview compensation
- Diary study (14 days): $50 Amazon gift card
