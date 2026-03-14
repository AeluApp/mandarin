# Voice of Customer (VoC) Program — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Cadence:** Monthly batch of 3-5 interviews, rolling analysis

---

## 1. Purpose

Structured discovery of what adult Mandarin learners actually need, want, and struggle with — before building features. Every product decision at Aelu should trace back to a VoC insight or be flagged as assumption-only.

---

## 2. Target Segments

### Segment A — Self-Study Adults (Primary)
- Age 25-55, learning Mandarin independently
- Motivated by career, travel, or personal interest
- Currently using 1-3 apps (Anki, HelloChinese, Duolingo, Pleco)
- Pain: lack of active recall, no system closes the loop from exposure to production
- **Screening:** Currently studying Mandarin, no formal classroom enrollment, 3+ months of study history

### Segment B — Heritage Speakers
- Grew up hearing Mandarin/Cantonese at home
- Can understand spoken Chinese at a basic level but cannot read/write
- Pain: existing apps start too low on listening/speaking, too high on reading
- **Screening:** At least one Chinese-speaking parent/grandparent, self-assessed listening > reading

### Segment C — Classroom Students
- Enrolled in university or community college Mandarin courses
- Using apps to supplement classroom instruction
- Pain: classroom pace doesn't match individual weak spots
- **Screening:** Currently enrolled in a Mandarin course, using at least one supplemental app

### Segment D — Returning Lapsed Learners
- Studied Mandarin 1-5 years ago, stopped, want to resume
- Forgot significant vocabulary but retain some pattern recognition
- Pain: apps force restart from zero, no placement or recovery path
- **Screening:** Previously studied Mandarin for 6+ months, gap of 6+ months since last study

---

## 3. Recruitment Channels

| Channel | Expected Segment | Method | Notes |
|---------|-----------------|--------|-------|
| Reddit r/ChineseLanguage | A, D | Post in weekly thread, DM active posters | Follow subreddit rules, no spam |
| Reddit r/ChineseLearning | A, C | Same approach | Smaller but engaged |
| Discord: Chinese Learning Hub | A, B | #looking-for-participants channel | Ask mods first |
| Discord: Refold Chinese | A | Community channels | Active immersion learners |
| HelloTalk | A, B | In-app language exchange posts | Filter for English-native learners |
| Tandem | A, B | Same as HelloTalk | |
| University Chinese departments | C | Email to department coordinators | Offer gift card |
| Mandarin Blueprint community | A | Facebook group, forums | Higher-level learners |
| Twitter/X: #MandarinLearning | A, D | Direct outreach to active posters | Warm leads only |
| Local Chinese cultural centers | B | Flyers, event attendance | Heritage speaker pipeline |

---

## 4. Screening Questionnaire

Before scheduling, confirm fit with these 5 questions:

1. How long have you been studying Mandarin? (filter: 1+ months)
2. Are you currently enrolled in a Mandarin class? (segment C identifier)
3. Did you grow up hearing Chinese at home? (segment B identifier)
4. Have you taken a break of 6+ months from studying? (segment D identifier)
5. What apps/tools do you currently use for Mandarin? (context)

Disqualify: Professional translators, linguistics researchers, native speakers, anyone under 18.

---

## 5. Interview Guide — 15 Core Questions

**Opening (2 min)**

> "I'm building a Mandarin learning app and want to understand how people actually study. There are no right or wrong answers — I'm trying to learn from your experience."

**Current Practice (Questions 1-4)**

1. **Walk me through a typical study session.** What do you do first? How long does it usually last? What tells you you're done?
   - *Listen for:* session structure, stopping triggers, time investment

2. **What tools do you use, and what role does each one play?** (e.g., Anki for vocab, YouTube for listening, textbook for grammar)
   - *Listen for:* tool fragmentation, gaps between tools, what they wish one tool did

3. **When you encounter a word you don't know in the wild — reading, watching something, conversation — what do you do?**
   - *Listen for:* lookup behavior, retention after lookup, frustration with repeated lookups

4. **How do you decide what to study next?** Is it the app, a textbook sequence, your own judgment, or something else?
   - *Listen for:* agency vs. passivity, trust in recommendations, curriculum awareness

**Pain Points (Questions 5-8)**

5. **What's the most frustrating thing about learning Mandarin right now?**
   - *Listen for:* top-of-mind pain, emotional weight, specific vs. vague complaints

6. **Tell me about a time you felt stuck — like you weren't making progress. What was happening?**
   - *Listen for:* plateau triggers, which skill stalled, what they tried to fix it

7. **What's a word or phrase you've looked up more than 5 times and still can't remember?** Why do you think it won't stick?
   - *Listen for:* specific failure cases, self-theories about why retention fails

8. **Have you ever quit a language app? What made you stop?**
   - *Listen for:* churn triggers, feature gaps, motivation decay patterns

**Tones & Pronunciation (Questions 9-10)**

9. **How confident are you in your tones?** When did you last get corrected on a tone in conversation?
   - *Listen for:* tone awareness, self-assessment accuracy, correction sources

10. **Do you practice speaking out loud when studying alone?** If yes, how? If no, why not?
    - *Listen for:* speaking avoidance, recording behavior, feedback needs

**Retention & Progress (Questions 11-13)**

11. **How do you know if you've actually learned something versus just recognized it in the moment?**
    - *Listen for:* recall vs. recognition awareness, testing strategies, overconfidence

12. **What does "making progress" feel like to you?** What would tell you this week was a good week of study?
    - *Listen for:* progress metrics (intrinsic vs. extrinsic), goal framing

13. **If you could wave a magic wand and fix one thing about your Mandarin study, what would it be?**
    - *Listen for:* #1 unmet need, unprompted feature requests

**Product Concept Probes (Questions 14-15)**

14. **If an app could detect exactly which types of errors you make — tones, word order, measure words — and automatically focus your practice on those patterns, how useful would that be?** (Scale 1-10, then explain why)
    - *Listen for:* value perception of error-focused drilling, trust in automated diagnosis

15. **Would you pay $14.99/month for a Mandarin learning system that tracks your actual gaps and builds every session around closing them?** What would it need to do to be worth that to you?
    - *Listen for:* price sensitivity, feature requirements for willingness to pay, comparison anchors

**Closing (1 min)**

> "Is there anything about learning Mandarin that I should have asked about but didn't?"

---

## 6. Coding Framework for Thematic Analysis

### Primary Codes (apply to every quote)

| Code | Definition | Example |
|------|-----------|---------|
| PAIN-TONE | Difficulty with tones specifically | "I still mix up 2nd and 3rd tone" |
| PAIN-RETAIN | Can't retain vocabulary | "I look up the same word every week" |
| PAIN-PLATEAU | Feeling of stagnation | "I've been HSK 3 for two years" |
| PAIN-FRAGMENT | Tool fragmentation | "I use 4 different apps and nothing connects" |
| PAIN-SPEAK | Fear/avoidance of speaking | "I never practice out loud" |
| PAIN-PASSIVE | Too much passive input, not enough output | "I watch shows but can't say anything" |
| NEED-ACTIVE | Desire for active recall/production drills | "I want to be tested, not just shown" |
| NEED-FEEDBACK | Desire for specific error feedback | "Tell me exactly what I got wrong" |
| NEED-ADAPTIVE | Desire for personalized pacing | "Don't make me review stuff I already know" |
| NEED-PROGRESS | Desire for visible progress metrics | "Show me I'm getting better" |
| NEED-CONTEXT | Desire for real-world context | "I want to learn words I'll actually use" |
| CHURN-BORE | Boredom as exit reason | "It got repetitive" |
| CHURN-HARD | Difficulty as exit reason | "I couldn't keep up" |
| CHURN-LIFE | Life interruption as exit reason | "I just got busy" |
| CHURN-VALUE | Perceived value gap as exit reason | "Wasn't worth the money" |
| WTP-YES | Willing to pay $14.99/month | "That's reasonable" |
| WTP-NO | Not willing to pay $14.99/month | "Too expensive" |
| WTP-COND | Conditionally willing | "Only if it does X" |

### Secondary Codes (apply when relevant)

| Code | Definition |
|------|-----------|
| SEG-HERITAGE | Heritage speaker-specific insight |
| SEG-LAPSED | Returning learner-specific insight |
| SEG-CLASSROOM | Classroom student-specific insight |
| TOOL-ANKI | Mentions Anki specifically |
| TOOL-DUO | Mentions Duolingo specifically |
| TOOL-PLECO | Mentions Pleco specifically |
| HSK-LOW | Currently HSK 1-3 |
| HSK-MID | Currently HSK 4-6 |
| HSK-HIGH | Currently HSK 7-9 |
| FEATURE-REQ | Unprompted feature request |

---

## 7. Interview Notes Template

```
# VoC Interview — [Participant ID]

**Date:** YYYY-MM-DD
**Duration:** XX minutes
**Segment:** A / B / C / D
**Current HSK (self-assessed):** X
**Current tools:** [list]
**Consent:** verbal / written

## Key Quotes (verbatim)

> Q1: "..."
> [Code: PAIN-xxx, NEED-xxx]

> Q5: "..."
> [Code: PAIN-xxx]

> Q15 WTP: "..." (Score: X/10)
> [Code: WTP-xxx]

## Top 3 Insights

1.
2.
3.

## Surprising / Unexpected

-

## Feature Requests (unprompted)

-

## Segment-Specific Notes

-

## Follow-up Actions

- [ ]
```

---

## 8. Analysis Cadence

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Conduct interviews | Monthly (3-5 per batch) | Jason |
| Code transcripts | Within 48 hours of interview | Jason |
| Update theme frequency table | After each batch | Jason |
| Review codes for saturation | Quarterly | Jason |
| Feed insights to backlog | After each batch | Jason |
| Compare themes to current roadmap | Quarterly | Jason |

### Saturation Rule
When 3 consecutive interviews in a segment produce no new primary codes, that segment is saturated. Shift recruitment to under-represented segments.

---

## 9. Insight-to-Action Protocol

Every VoC insight that reaches 3+ mentions across different participants gets:

1. Written up as a one-paragraph problem statement
2. Mapped to existing Aelu features (already addressed? partially? not at all?)
3. If not addressed: added to backlog with VoC tag and participant count
4. If partially addressed: create improvement ticket referencing specific quotes

No feature gets built based on a single interview. Pattern requires N >= 3 mentions across >= 2 segments.
