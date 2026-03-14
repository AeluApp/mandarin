# Content Generation Status Report

**Date**: 2026-03-07
**Scope**: Full reconciliation, structural validation, tone audit, and length benchmark

---

## 1. Counts: Done vs Target

### Reading Passages

| HSK | Target | Actual | Status |
|-----|--------|--------|--------|
| 1 | 125 | 125 | DONE |
| 2 | 125 | 125 | DONE |
| 3 | 120 | 128 | DONE (+8) |
| 4 | 120 | 130 | DONE (+10) |
| 5 | 139 | 139 | DONE |
| 6 | 120 | 120 | DONE |
| 7 | 120 | 120 | DONE |
| 8 | 120 | 120 | DONE |
| 9 | 120 | 120 | DONE |
| **Total** | **1,009** | **1,127** | **DONE (+118)** |

### Dialogue Scenarios (j-series only)

| HSK | Target | Actual | Status |
|-----|--------|--------|--------|
| 1 | 34 | 34 | DONE |
| 2 | 44 | 44 | DONE |
| 3 | 55 | 55 | DONE |
| 4 | 51 | 51 | DONE |
| 5 | 47 | 47 | DONE |
| 6 | 33 | 33 | DONE |
| 7 | 10 | 10 | DONE |
| 8 | 10 | 10 | DONE |
| 9 | 10 | 10 | DONE |
| **Total** | **294** | **294** | **DONE** |

### Media Catalog

| Metric | Value |
|--------|-------|
| Target | 105 |
| Actual | 105 |
| Status | DONE |

### Deployed Scenarios (all types in data/scenarios/)

588 total files (294 j-series + ~150 gen_ prefix + ~42 numbered/hsk-labeled). All valid JSON.

---

## 2. Structural Validation

### Zero critical issues

- **Parse errors**: 0 across all 1,127 passages, 294 j-dialogues, 588 deployed scenarios, 105 media entries
- **Missing required fields**: 0 (top-level passage/dialogue/media fields)
- **Empty text fields**: 0
- **Bad HSK levels**: 0
- **Duplicate IDs**: 0
- **Content duplicates**: 0
- **Questions without correct answer**: 0
- **Questions with all-correct answers**: 0

### Two low-severity structural issues

1. **Passage question option schema** (20 passages): `j3_observe_001` through `j3_observe_020` use simplified option format `{text, correct}` instead of full `{text, pinyin, text_en, correct}`. Functional but incomplete.

2. **Dialogue missing register field** (239/294 j-series files): Options 1 and 2 in player turns lack `register` field. Only option 0 (best answer) has it. All 55 HSK 3 dialogues are correct. Mechanical fix: infer from score.

---

## 3. Length Analysis vs Competitors

### Passage Length

| HSK | Current Avg | Industry Target | Verdict |
|-----|------------|----------------|---------|
| 1 | 66 chars | 50-120 | GOOD |
| 2 | 98 chars | 100-200 | GOOD (low end) |
| 3 | 194 chars | 150-350 | GOOD |
| 4 | 250 chars | 250-450 | BORDERLINE |
| 5 | 286 chars | 400-700 | **SHORT (30-50% below)** |
| 6 | 378 chars | 500-900 | **SHORT** |
| 7 | 409 chars | 600-1,200 | **SHORT** |
| 8 | 462 chars | 600-1,200 | **SHORT** |
| 9 | 514 chars | 600-1,200 | **SHORT** |

**Key finding**: HSK 1-3 are well-calibrated. HSK 5-9 passages are consistently 30-50% shorter than Du Chinese, HSK Standard Course, and The Chairman's Bao benchmarks. The HSK 5 exam uses 600-1,000 char passages; ours average 286.

### Comprehension Questions

| HSK | Current Avg | Recommended | Verdict |
|-----|------------|-------------|---------|
| 1 | 2.8 | 1-2 | OVER |
| 2 | 3.0 | 2-3 | GOOD |
| 3 | 2.8 | 2-3 | GOOD |
| 4 | 2.8 | 3-4 | LOW |
| 5 | 2.4 | 3-4 | LOW |
| 6 | 2.1 | 4-5 | **LOW** |
| 7 | 2.6 | 4-5 | **LOW** |
| 8 | 2.5 | 4-5 | **LOW** |
| 9 | 2.1 | 5-6 | **LOW** |

**Key finding**: Question counts are inverted — more at low levels, fewer at high levels. Should be the opposite.

### Dialogue Length

| HSK | Current Turns | Target | Current Choices | Target | Verdict |
|-----|--------------|--------|----------------|--------|---------|
| 1 | 4.4 | 4-6 | 2.2 | 2-3 | GOOD |
| 2 | 4.4 | 5-8 | 2.2 | 2-3 | LOW-END |
| 3 | 6.0 | 6-10 | 3.0 | 3-4 | GOOD |
| 4 | 6.2 | 8-12 | 3.1 | 3-5 | SHORT |
| 5 | 7.1 | 10-14 | 3.3 | 4-6 | SHORT |
| 6 | 7.2 | 12-16 | 3.5 | 5-7 | SHORT |
| 7 | 6.4 | 12-20 | 3.2 | 5-8 | **SHORT (regression)** |
| 8 | 5.4 | 12-20 | 2.7 | 5-8 | **SHORT (regression)** |
| 9 | 5.7 | 12-20 | 2.9 | 5-8 | **SHORT (regression)** |

**Key finding**: Dialogue turns peak at HSK 5-6 then regress at 7-9. HSK 8 dialogues (5.4 turns avg) are shorter than HSK 2 (4.4). ChinesePod advanced dialogues run 15-20+ turns.

---

## 4. Tone & Style Audit

### Overall Verdict

**The j-series content (passages + j-dialogues) is excellent.** It consistently achieves the iyashikei/healing tone with humane warmth, observational specificity, and quiet intelligence. The gen_ prefix dialogues (~150 files in deployed scenarios) are a significant tone failure and need replacement.

### Tone by HSK Band

**HSK 1-3: Strong.** Warmth survives vocabulary simplification remarkably well.

Successes:
> "The rain isn't heavy, but it's beautiful. There's nobody on the street. A cat sits in front of the shop." — j1_observe_002

> "Mom said: 'Forget it. These imperfect photos are probably better than perfect ones.'" — j2_comedy_007

> "Grandpa felt his head with his hand — the glasses were indeed there. He laughed too." — j1_comedy_013

**HSK 4-6: The sweet spot.** Literary quality opens up with more vocabulary.

Successes:
> "He lays out his tools neatly on a piece of cloth, as if preparing a small exhibition." — j4_observe_001

> "'Doing two things well is enough. If you sell everything, you can't do anything well.' She was very serious when she said this." — j4_urban_101

> "The absence of management actually created a deeper order — one based on empathy and shared circumstance." — j6_inst_001

**HSK 7-9: Intellectually ambitious, warmth maintained.** Minor risk of over-intellectualization in a few passages.

Successes:
> "I suddenly understood that the meaning of ritual never depends on outcome. What the withered pots hold is not plants but a memory that refuses to leave." — j7_observe_001

> "Perfect vibration is mathematics — imperfect vibration is music." — j9_dlg_005

> "A bowl of white rice sits before you, steam rising in delicate wisps. It has no flavor of its own, yet can carry any flavor." — j9_food_067

### Influence Mix Assessment

| Influence | Present? | Strength |
|-----------|----------|----------|
| Hayao Miyazaki (ordinary wonder) | Yes | Dominant ground note — correct |
| Anthony Bourdain (food/culture curiosity) | Yes | Second strongest — correct for China app |
| Genzaburo Yoshino (gentle philosophical guidance) | Yes | Strong in HSK 7-9 |
| Stephen Sondheim (emotional complexity, elegant surfaces) | Yes | Identity passages, musician dialogues |
| Mel Brooks (joyful absurdity) | Yes | Comedy passages, grandpa's glasses |
| Larry David (social friction observation) | Yes | Group chat, bookshelf/shoe rack dialogue |
| Tina Fey (sharp wit, never mean) | Yes | Comedy dialogues |
| Matt Yglesias (accessible systems thinking) | Yes | Institutional passages |
| Barack Obama (measured thoughtfulness) | Yes | Media cultural notes |
| Fareed Zakaria (global perspective) | Yes | Identity, "Grammar of Rice" |
| Elaine May (improvisational human truth) | Yes | Best dialogues feel improvisational |
| John Hodgman (deadpan intelligence) | Partial | Subtle, could be stronger |
| Amy Sedaris (eccentric warmth, craft as joy) | Partial | Tofu seller, clockmaker — could be more |
| Alan Alda (conversational grace) | Yes | Dialogue feedback lines |

### Failure Modes Found

| Mode | Found? | Where |
|------|--------|-------|
| Generic textbook voice | YES | All gen_ prefix dialogues (~150 files) |
| Emotionally cold/flat | YES | gen_ dialogues, hsk-labeled formal scenarios |
| Stiff/unnatural dialogue | YES | gen_restaurant, gen_emergency (incoherent NPC lines) |
| Cross-contaminated content | YES | hsk7_literary_criticism, hsk9_bioethics_committee (wrong distractors) |
| Snark/cynicism/meanness | No | Not detected anywhere |
| Excessive moralizing | No | Not detected |
| Melodrama | No | Not detected |
| Too much sadness without restoration | No | Even grief passages find beauty |
| Over-intellectualization | Minor | A few HSK 8 passages delay the emotional core |

### Three Tiers of Dialogue Quality

**Tier 1 — j-series (294 files): Excellent.** Named characters, sensory setups, characterful feedback. Crown jewels.

**Tier 2 — hsk-labeled formal scenarios (~42 files): Neutral.** Intellectually strong, tonally flat. Serve a purpose (formal register practice) but lack warmth.

**Tier 3 — gen_ prefix dialogues (~150 files): Actively harmful.** Skeletal, robotic, sometimes factually broken. "A shopping scenario at HSK 1 level" is not a setup. "Correct response." is not feedback. These must be replaced.

---

## 5. The 10 Strongest Entries (Tone Exemplars)

1. **j7_observe_001** "The Woman Who Waters Dead Plants" — "The posture of bending, tilting the can, and waiting is what's truly growing."
2. **j9_dlg_005** "The Sound of Old Wood" — "Perfect vibration is mathematics — imperfect vibration is music."
3. **j1_observe_002** "Rain on the Window" — Proves tone survives HSK 1 vocabulary.
4. **j6_dlg_010** "The Escalating Misunderstanding" — "A shoe rack is just the juvenile form of a bookshelf?"
5. **j5_dlg_020** "The Courtyard We Grew Up In" — "Those small kindnesses are what truly made childhood warm."
6. **j9_food_067** "The Grammar of Rice" — Cultural essay through the lens of a bowl of rice.
7. **j4_urban_101** "The Night Market Tofu Stall" — "'Doing two things well is enough.' She was very serious."
8. **j7_observe_024** "The Fishpond in the Park" — "'I'm not here to catch fish.'"
9. **j5_identity_003** "Speaking Two Languages at Home" — "I'm not two people, but I do have two doorways."
10. **j8_dlg_005** "The Silent Musician" — "You don't need to play 'well' — you only need to play 'truly.'"

---

## 6. The 10 Weakest Entries (Rewrite First)

1. **gen_shopping_1_00_v0** — "A shopping scenario at HSK 1 level." No scene, no warmth. Feedback: "Correct response."
2. **gen_restaurant_1_00_v0** — NPC asks "How much?" to the customer. Incoherent.
3. **gen_emergency_3_00_v0** — Emergency scenario with shopping dialogue. Factually broken.
4. **gen_emergency_2_00_v0 through gen_emergency series** — High probability of same issues.
5. **gen_phone series** — Same template-generated problems.
6. **gen_social series** — "A social scenario at HSK X level" is not a setup.
7. **gen_bank series** — Same pattern.
8. **01_restaurant.json** — "You walk into a small restaurant for lunch." Functional but generic.
9. **hsk9_bioethics_committee.json** — Cross-contaminated distractor options from unrelated scenarios.
10. **hsk7_literary_criticism.json** — Same cross-contamination problem.

---

## 7. Near-Duplicate Titles/Themes

HSK 3 has 128 passages (target 120) — 8 surplus, likely some thematic overlap with other levels. HSK 4 has 130 (target 120) — 10 surplus. No exact duplicate titles detected. Some thematic clustering around rain, tea shops, and park benches is intentional (iyashikei motifs) rather than accidental duplication.

---

## 8. Level-by-Level Tone Consistency Ranking

| Rank | Band | Notes |
|------|------|-------|
| 1st | HSK 4-6 | Sweet spot: complex enough for nuance, constrained enough to stay grounded |
| 2nd | HSK 1-3 | Impressive that warmth survives vocabulary simplification |
| 3rd | HSK 7-9 | Intellectually ambitious, warmth maintained, minor over-intellectualization risk |

All three bands are strong in the j-series content. The weakness is concentrated in the non-j content (gen_, numbered, hsk-labeled).

---

## 9. Priority Actions

### Critical (before release)
1. **Replace or remove gen_ prefix dialogues** (~150 files). These are the single largest quality problem.
2. **Fix cross-contaminated distractors** in hsk-labeled dialogues.

### High Priority (content quality)
3. **Lengthen HSK 5-9 passages** to match competitor benchmarks (target: HSK 5 avg 500 chars → HSK 9 avg 1,000 chars). Current passages are 30-50% short.
4. **Fix HSK 7-9 dialogue turn regression**. Extend to 12-18 turns with 5-8 player choices.
5. **Add more comprehension questions to HSK 5-9** (target: 3-5 per passage).

### Medium Priority (polish)
6. **Extend HSK 4-6 dialogues** to 8-14 turns.
7. **Backfill register field** on dialogue options (mechanical).
8. **Add pinyin/text_en to j3_observe question options** (mechanical).
9. **Increase HSK 7-9 dialogue volume** (20 per level is thin vs 68-110 at lower levels).

### Low Priority
10. Trim HSK 1 questions to 2 per passage.
11. Add 2-3 Hodgman/Sedaris-flavored passages at HSK 4-6.

---

## 10. Release Recommendation

### Another rewrite pass is needed — but it is targeted, not wholesale.

The j-series content is genuinely excellent. The tone is consistent, the influence mix is well-reflected, and the iyashikei aesthetic is maintained across all HSK levels. This content should be protected and not homogenized.

The problems are:
1. **gen_ dialogues** (~150 files) are actively harmful to the brand and must be replaced
2. **HSK 5-9 passages are too short** for competitive standing (30-50% below industry norms)
3. **HSK 7-9 dialogues are too short** (regression below lower levels)
4. **Comprehension question counts are inverted** (more at low levels, fewer at high)

### The single best next prompt:

> "Replace all gen_ prefix dialogue scenarios with j-series quality content. Then lengthen all HSK 5-9 passages to match competitor benchmarks (HSK 5: ~500 chars, HSK 6: ~650, HSK 7: ~750, HSK 8: ~850, HSK 9: ~1,000 avg), adding 1-2 additional comprehension questions to each lengthened passage. Finally, extend HSK 7-9 dialogues to 12-18 turns with 5-8 player choice points."
