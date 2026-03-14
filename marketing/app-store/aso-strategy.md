# App Store Optimization Strategy

## Overview

Aelu occupies a specific niche: serious adult Chinese learners who are underserved by gamified apps. The ASO strategy targets this audience directly rather than competing for the broadest possible search terms. The approach favors high-intent, lower-volume keywords over high-volume, low-intent ones.

---

## Primary Keywords

| Keyword | Est. Monthly Search (iOS US) | Competition | Strategy |
|---------|------------------------------|-------------|----------|
| learn chinese | 45,000 | Very High | Compete via subtitle + description; do not waste keyword field |
| mandarin | 12,000 | High | Owned via app name |
| hsk | 5,500 | Medium | High intent, strong fit — keyword field priority |
| chinese study | 3,200 | Medium | Exact match in subtitle ("Patient Chinese Study") |
| learn mandarin | 8,000 | High | Covered by name + description |
| pinyin | 4,800 | Medium | Keyword field |
| chinese characters | 3,500 | Medium | Keyword field |
| hanzi | 1,200 | Low | Keyword field — low competition, high intent |
| spaced repetition | 2,100 | Medium | Keyword field — captures method-aware learners |
| chinese vocabulary | 2,800 | Medium | Keyword field |
| tones chinese | 900 | Low | Keyword field |

### iOS Keyword Field (100 chars)

```
chinese,mandarin,hsk,learn chinese,study,pinyin,tones,characters,vocabulary,hanzi,spaced repetition
```

**Rationale:** "Aelu" is in the app name and "Chinese Study" is in the subtitle, so the keyword field avoids redundancy with those. Every character counts.

---

## Long-Tail Keyword Combinations

These are combinations that users actually search for. They are targeted through description text and metadata alignment.

| Long-tail phrase | Est. Monthly Search | Notes |
|------------------|---------------------|-------|
| hsk 1 vocabulary | 1,400 | High conversion intent |
| hsk 2 practice | 800 | Direct feature match |
| learn chinese for adults | 600 | Exact audience fit |
| chinese flashcards no ads | 400 | Frustration-driven search |
| mandarin tone practice | 350 | Specific feature search |
| chinese reading practice | 500 | Graded reader feature match |
| chinese listening practice | 450 | Extensive listening feature match |
| spaced repetition chinese | 300 | Method-aware learner |
| hsk prep app | 700 | High intent |
| chinese study app no games | 200 | Exact positioning match — small but perfectly targeted |

---

## Competitor Keyword Gaps

### Duolingo
- **Their strength:** Brand recognition, "learn [language]" searches, casual learner market
- **Their gap:** "serious," "adult," "no gamification," "no streaks," "HSK prep," "advanced Chinese"
- **Our play:** We do not compete with Duolingo for casual learners. We capture the learners who outgrow Duolingo or are frustrated by it. Target frustration keywords: "duolingo alternative," "chinese app no hearts," "better than duolingo chinese"

### HelloChinese
- **Their strength:** Chinese-specific, gamified but less aggressive than Duolingo, decent content
- **Their gap:** Limited advanced content, still gamified, less transparent progress tracking
- **Our play:** Compete directly on depth (HSK 1-9 vs. their more limited range), honest metrics, and the adult tone. Target: "hellochinese alternative," "advanced chinese app"

### Pleco
- **Their strength:** Best Chinese dictionary, deep reference tool, established reputation
- **Their gap:** Not a study system — it is a dictionary with study features bolted on. No structured curriculum.
- **Our play:** We are complementary to Pleco, not competitive. Many Pleco users want a structured study system. Target: "chinese study app," "structured chinese learning," "chinese curriculum app"

### Anki
- **Their strength:** Flexible SRS, large user-created deck library, free on Android
- **Their gap:** Ugly, steep learning curve, no curated content, requires user to build their own system
- **Our play:** Capture Anki users who want curation and structure. Target: "anki alternative chinese," "curated chinese flashcards," "chinese spaced repetition app"

---

## Localization Recommendations

### Priority Markets (Phase 1)

| Market | Language | Rationale |
|--------|----------|-----------|
| United States | English | Primary market. Largest English-speaking Chinese learner population. |
| United Kingdom | English (UK) | Second largest. Minimal localization needed — just spelling variants. |
| Canada | English + French | Growing Chinese learner population. French metadata opens Quebec. |
| Australia | English | Strong Chinese-learning demand due to economic ties. |

### Phase 2 Markets

| Market | Language | Rationale |
|--------|----------|-----------|
| Germany | German | Large HSK test-taking population. Significant Chinese learner community. |
| France | French | Growing interest. HSK adoption increasing. |
| Japan | Japanese | Large number of kanji-literate learners with Chinese interest. Heritage overlap. |
| South Korea | Korean | Similar to Japan — cultural proximity drives interest. |
| Indonesia | Indonesian | Huge heritage Chinese population. Underserved market. |
| Singapore | English | High Chinese literacy baseline. Heritage learner market. |

### Phase 3 Markets

| Market | Language | Rationale |
|--------|----------|-----------|
| Brazil | Portuguese | Emerging Chinese learner market. Low competition. |
| Spain | Spanish | Growing interest, especially for business. |
| Thailand | Thai | Large heritage Chinese population. |
| Malaysia | Malay + English | Heritage learner market similar to Indonesia/Singapore. |

**Localization notes:**
- Metadata only first (title, subtitle, description, keywords). Do not localize the app UI until market traction is established.
- For each locale, research local keyword volumes independently. "HSK" is universal but phrasing varies.
- Heritage learner messaging resonates strongly in Southeast Asian markets.

---

## Rating and Review Solicitation Strategy

### Principles

Aelu does not manipulate users into leaving reviews. The strategy is: build something worth reviewing, then ask at the right moment in the right way.

### When to Ask

**Trigger conditions (ALL must be true):**
1. User has completed at least 10 study sessions
2. User's most recent session had a positive outcome (mastery improved or maintained)
3. At least 14 days since first session
4. User has not been asked in the last 90 days
5. User has not dismissed the prompt twice before (lifetime — after two dismissals, never ask again)

**Never ask:**
- During a study session (interrupting flow)
- After a poor performance session
- On the first day
- More than 4 times per year
- After the user has already left a review

### How to Ask

Use Apple's native `SKStoreReviewController` / Google's in-app review API. Do not build a custom prompt. The native dialog is less intrusive and more trusted.

**Pre-prompt (optional, shown before the native dialog):**
> "You have been studying for [X] days. If Aelu is useful to you, a review helps other learners find it. No pressure — study comes first."

If the user taps "Not now," respect it silently. No guilt. No follow-up. No "Are you sure?"

### Response Strategy

- Respond to every 1-2 star review within 48 hours. Be helpful, not defensive.
- Respond to thoughtful 3-star reviews to show engagement.
- Thank 4-5 star reviews briefly. Do not be effusive.
- Never offer incentives for reviews. Never ask users to change their rating.

---

## Seasonal Trends

| Period | Trend | Action |
|--------|-------|--------|
| January | New Year resolution spike. "Learn Chinese" searches peak. | Update promotional text to emphasize fresh starts (without being cheesy). Increase ASA spend. |
| February | Chinese New Year. Cultural interest peaks. | Update What's New with CNY acknowledgment. Cultural content resonance. |
| May-June | Summer study planning. University students preparing. | Emphasize self-study structure. HSK prep messaging. |
| August-September | Back to school. New semester enrollments in Chinese classes. | Target "supplement" and "practice" keywords. Messaging: "The study tool your class does not give you." |
| October-November | HSK exam season (major test dates). | HSK prep messaging front and center. Update screenshots to show HSK features. |
| December | Holiday downtime. People have time to start new things. | Softer messaging. "A quiet place to start." Gift messaging if applicable. |

---

## A/B Test Roadmap

### Quarter 1: Foundation

| Test | Variable | Variants | Duration | Success Metric |
|------|----------|----------|----------|----------------|
| 1.1 | Promotional text | 5 variants (see ios-metadata.md) | 5 weeks (1 per variant) | Conversion rate (impressions to installs) |
| 1.2 | Screenshot 1 headline | "Study Chinese honestly." vs. "No streaks. No gimmicks." vs. "Chinese study for adults." | 6 weeks (2 per variant) | Conversion rate |
| 1.3 | Google Play short description | 5 variants (see google-play-metadata.md) | 5 weeks | Conversion rate |

### Quarter 2: Visual Optimization

| Test | Variable | Variants | Duration | Success Metric |
|------|----------|----------|----------|----------------|
| 2.1 | Screenshot order | Default order vs. leading with drill screenshot vs. leading with reading screenshot | 6 weeks | Conversion rate |
| 2.2 | Screenshot background | Warm stone (#F2EBE0) vs. White (#FFFFFF) vs. Warm dark | 6 weeks | Conversion rate |
| 2.3 | Feature graphic (Play) | Three options from google-play-metadata.md | 6 weeks | Conversion rate |

### Quarter 3: Messaging

| Test | Variable | Variants | Duration | Success Metric |
|------|----------|----------|----------|----------------|
| 3.1 | Subtitle | "Patient Chinese Study" vs. "Honest Chinese Study" vs. "Calm Chinese Study" | 6 weeks | Search conversion + browse conversion |
| 3.2 | Description opening line | Feature-led vs. differentiator-led vs. audience-led | 6 weeks | Conversion rate (read-more tap rate if measurable) |

### Quarter 4: Refinement

| Test | Variable | Variants | Duration | Success Metric |
|------|----------|----------|----------|----------------|
| 4.1 | Winner validation | Re-test Q1-Q3 winners against new challengers | 8 weeks | Sustained conversion rate |
| 4.2 | Localized metadata | English default vs. localized for top 3 Phase 2 markets | 8 weeks | Per-market conversion rate |

---

## Measurement

### Key Metrics

- **Conversion rate:** Impressions to first-time downloads (primary)
- **Keyword ranking:** Track top 20 keywords weekly
- **Search vs. browse split:** Understand where installs come from
- **Retention correlation:** Do different acquisition keywords predict different 7-day retention? Optimize for keywords that bring users who stay.

### Tools

- App Store Connect analytics (iOS)
- Google Play Console (Android)
- Consider: AppFollow, Sensor Tower, or AppTweak for competitive keyword tracking (evaluate cost vs. value at scale)

### Review Cadence

- Weekly: Check keyword rankings, conversion rate
- Monthly: Review A/B test results, adjust metadata
- Quarterly: Full ASO audit — keywords, screenshots, description, competitor analysis
- Annually: Complete metadata refresh based on accumulated data

---

## Anti-Patterns to Avoid

These are common ASO tactics that conflict with the Aelu brand:

1. **Keyword stuffing** in the description. Write for humans. Search algorithms reward relevance, not density.
2. **Fake urgency** in promotional text ("Limited time!" "Start today!"). This is streak anxiety in marketing form.
3. **Misleading screenshots** showing features that do not exist or data that is not representative.
4. **Review manipulation** of any kind — incentivized reviews, review swaps, fake reviews.
5. **Copying competitor names** into keywords. Referencing competitors in strategy documents is fine; putting "duolingo" in your keyword field is not.
6. **Excessive A/B testing velocity.** Each test needs enough time to reach statistical significance. Rushing tests produces noise, not signal.
7. **Dark pattern CTAs** in the app that funnel to the review prompt. The review ask should feel optional because it is optional.
