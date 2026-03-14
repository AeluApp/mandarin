# Tone and Style Audit — Mandarin Learning App Content

**Date**: 2026-03-07
**Auditor**: Claude (systematic sample, not exhaustive)
**Corpus**: 1,127 reading passages, ~300 dialogue scenarios (j-series + gen_series + hsk-labeled), 105 media catalog entries
**Sample size**: 30+ passages across HSK 1-9, 15 dialogue files, 20+ media entries

---

## 1. Overall Tone Assessment

**Verdict: The j-series content (passages + j*_dlg dialogues) is remarkably on-target. It is some of the best iyashikei-aligned language-learning content I have encountered. The gen_ series dialogues are a significant problem. The hsk-labeled formal dialogues are tonally neutral — not warm, not cold.**

The reading passages and the j-series dialogues share a consistent sensibility: quiet observation of ordinary life, gentle humor, emotional specificity without melodrama, and a deep comfort with stillness. The voice is that of someone who sits on a park bench and watches the world with affection. This is the correct voice.

The gen_ prefix dialogues (gen_restaurant, gen_shopping, gen_emergency, etc.) are a completely different product. They are skeletal, robotic, contextless, and tonally dead. They read like auto-generated drill exercises from a 2015 language app. They are the single largest tone failure in the system.

The media catalog is consistently warm, knowledgeable, and curious — Bourdain-adjacent in its food descriptions, Zakaria-adjacent in its cultural framing. Excellent.

---

## 2. HSK 1-3 Band Assessment

### Strengths

The hardest tone challenge is at the lowest vocabulary level: how do you maintain warmth and observational specificity with 500 words? The j-series HSK 1-3 passages solve this remarkably well.

**Evidence of success:**

> "It's raining today. I sit at home looking out the window. The rain isn't heavy, but it's beautiful. There's nobody on the street. A cat sits in front of the shop."
> — `j1_observe_002` "Rain on the Window"

This is iyashikei with HSK 1 vocabulary. The sentence "The rain isn't heavy, but it's beautiful" is doing real emotional work with five words. The cat in front of the shop is a Miyazaki image. Exemplary.

> "One old man brings a cup of tea every day and sits in the same spot."
> — `j1_observe_003` "The Old Man in the Park"

The phrase "the same spot" carries the weight of habit, age, and quiet satisfaction. Not a wasted word.

> "Grandpa felt his head with his hand — the glasses were indeed there. He laughed too."
> — `j1_comedy_013` "Grandpa's Glasses"

Gentle, physical comedy. The word "too" at the end creates shared warmth between grandpa and grandma. This is Mel Brooks territory — comedy as love between old people.

> "Mom said: 'Forget it. These imperfect photos are probably better than perfect ones.'"
> — `j2_comedy_007` "The Photo That Won't Work"

Wisdom delivered without moralizing. The mother is funny and wise at the same time. The observation that imperfect family photos are more authentic is genuinely true and doesn't lecture the reader about it.

> "I think: maybe she's the one who's right."
> — `j2_urban_005` "The Bike Lane at Rush Hour"

A quietly subversive observation about urban speed culture, delivered as a tentative thought rather than a declaration. The narrator doesn't preach — they wonder. This is emotionally steady and socially aware without being preachy.

### Failure modes at HSK 1-3

**1. The gen_ dialogues are catastrophically bad.** Example from `gen_shopping_1_00_v0`:

> Setup: "A shopping scenario at HSK 1 level."
> NPC: "你好！"
> Player options: "再见！" / "我不知道。" / "你好！"
> Feedback on correct: "Correct response."

This is the anti-thesis of the tone standard. The setup is not a scene — it is a database field. "A shopping scenario at HSK 1 level" has zero sensory detail, zero warmth, zero human presence. The feedback "Correct response." is a robot grading a test. Compare with the j-series equivalent (`j1_dlg_001`):

> Setup: "You stop at a small neighborhood shop on your morning walk. The shopkeeper, Auntie Wang, greets you warmly. The shop smells like fresh baozi."
> Feedback on correct: "Simple and clear — exactly what she asked."

The j-series setup has smell, time of day, a named character, warmth. The feedback has personality. The gen_ setup has nothing.

**2. The gen_ emergency dialogues are not even internally coherent.** From `gen_emergency_3_00_v0`:

> Title: "Calling for help" / Setup: "A emergency scenario at HSK 3 level."
> NPC: "为什么你选这个？" (Why did you choose this one?)

This is labeled as an emergency scenario but the NPC asks a shopping question. The content is both tonally dead AND factually broken.

### HSK 1-3 j-series dialogues: Strong

The j-series HSK 1 dialogues (`j1_dlg_001` through `j1_dlg_034`) are warm, grounded, and specific:

> Setup: "You walk into a small bookstore. A cat is sleeping on a stack of books."
> — `j1_dlg_010` "The Bookstore Cat"

> Setup: "You're sitting on a bench in your neighborhood. An elderly neighbor notices you watching a cat on a wall."
> — `j1_dlg_020` "The Old Cat on the Wall"

These setups create tiny, lived-in worlds. Named characters (Auntie Wang, Xiao Hua the cat), sensory details (the smell of baozi, a cat on a stack of books), and low-stakes warmth. The feedback lines are characterful: "Warm and engaging — responds to the shop owner's pride in her cat." This is not grading. This is gentle encouragement.

---

## 3. HSK 4-6 Band Assessment

### Strengths

This is where the voice really opens up. With more vocabulary available, the writing achieves genuine literary quality while remaining pedagogically controlled.

**Evidence of success:**

> "He lays out his tools neatly on a piece of cloth, as if preparing a small exhibition."
> — `j4_observe_001` "The Locksmith's Afternoon"

"A small exhibition" — this is the kind of unexpected simile that gives a passage its soul. The locksmith's tools laid out on cloth become something dignified and intentional. This is observational specificity at its finest.

> "'If I leave, what will these elderly people do? As long as they're still here, I'll be here.'"
> — `j4_inst_006` "The Village Clinic"

Compassion without sentimentality. Uncle Zhao's line is not heroic self-sacrifice — it is simple loyalty stated plainly. The emotional steadiness here is exactly right.

> "'Doing two things well is enough. If you sell everything, you can't do anything well.' She was very serious when she said this."
> — `j4_urban_101` "The Night Market Tofu Stall"

The tag "She was very serious when she said this" elevates a common sentiment into character revelation. We see the tofu seller not as a philosophical mouthpiece but as a specific woman with specific convictions about her work. This is Anthony Bourdain territory — genuine curiosity about food culture, no pretension.

> "I have no idea who this is. This building has over eighty units; I only know two or three. But someone I don't know noticed, and took care of it."
> — `j5_mystery_003` "The Note Under the Windshield"

Quiet urban tenderness. The mystery is not a crime but a kindness. The emotional weight comes from the realization that a stranger cared enough to act. This is gentle, restorative, and deeply humane.

> "I'm not two people, but I do have two doorways for expressing myself."
> — `j5_identity_003` "Speaking Two Languages at Home"

Beautiful metaphor for bilingual identity. Not intellectualized — lived. The passage captures the physical feeling of switching languages (voice softens, word choice becomes more casual) before arriving at the metaphor. Sondheim-level: emotional complexity beneath an elegant surface.

> "The absence of management actually created a deeper order — one based on empathy and shared circumstance."
> — `j6_inst_001` "The Hospital Garden Nobody Planned"

Matt Yglesias-adjacent systems thinking delivered with tenderness. The observation that unplanned spaces can have deeper social order than designed ones is sharp and true, and the passage arrives at it through specific, embodied observation (orthopedic patients in the morning, oncology patients mid-morning, family members in the afternoon).

> "That focus and silence makes me feel their work possesses a severely underestimated dignity."
> — `j6_system_062` "The Recycling Station's Quiet Economy"

The phrase "severely underestimated dignity" is doing real moral work. It doesn't moralize — it names what it sees. Social awareness without preachiness.

### Failure modes at HSK 4-6

Minimal in the j-series. The passages at this level are consistently strong.

The older numbered dialogues (01_restaurant.json through 52_media_interview.json) vary in quality. `01_restaurant.json` is functional but generic:

> Setup: "You walk into a small restaurant for lunch."

Compare with `j4_dlg_010` ("The Quiet Subway"):

> Setup: "It's late evening on a nearly empty subway car. You and a young graphic designer, Xiao Lin, are the only passengers. The train hums softly through the tunnels."

The difference is palpable. The old-style dialogues are serviceable language drills. The j-series dialogues are tiny narrative experiences.

---

## 4. HSK 7-9 Band Assessment

### Strengths

The HSK 7-9 band is where the content becomes genuinely literary. The question is whether increased complexity maintains warmth. The answer: overwhelmingly yes, with some caveats.

**Evidence of success:**

> "I suddenly understood that the meaning of ritual never depends on outcome. What the withered pots hold is not plants but a memory that refuses to leave."
> — `j7_observe_001` "The Woman Who Waters Dead Plants"

This is the best passage in the entire corpus. A woman watering dead plants becomes a meditation on grief, ritual, and love. The final line — "the posture of bending, tilting the can, and waiting is what's truly growing" — is genuinely moving. This is Miyazaki's sensibility: wonder in ordinary life, environmental tenderness, beauty in what others dismiss.

> "Some things are destined to be seen only by the present eye: unrecordable, unsaveable, unshareable. This isn't a regret — it's a privilege."
> — `j7_observe_052` "The Shape of Steam"

A meditation on impermanence that pushes back against Instagram culture without ever mentioning Instagram by name. The critique of "shareability as the standard of value" is sharp but delivered with reflective calm, not snark.

> "I'm not here to catch fish."
> — `j7_observe_024` "The Fishpond in the Park"

Lao Li's empty hook is the best single image in the HSK 7 corpus. The passage then lands on: "what they're really fishing for is a kind of leisure that is vanishing." Observational specificity and quiet social commentary in one sentence.

> "Perfect vibration is mathematics — imperfect vibration is music."
> — `j9_dlg_005` "The Sound of Old Wood"

This HSK 9 dialogue about a guqin maker is staggering. The idea that a crack from a century-old earthquake creates the most moving resonance, and that sanding away scars removes story, is philosophy delivered through craft. The player's response extends the metaphor to human experience without forcing it.

> "A bowl of white rice sits before you, steam rising in delicate wisps. It has no flavor of its own, yet can carry any flavor. This 'taste of tastelessness' is precisely the highest level in Chinese aesthetics — not emptiness, but infinite possibility."
> — `j9_food_067` "The Grammar of Rice"

Cultural essay disguised as a passage about rice. The linguistic observation (吃饭 means "eat" regardless of whether rice is present) opens into cultural analysis, then into aesthetics. Zakaria's global perspective meets Genzaburo Yoshino's gentle philosophical guidance.

### HSK 7-9 caveats

**1. Some HSK 7-9 passages risk over-intellectualization.** The writing is never cold, but a few passages stack metaphors so densely that the warmth becomes secondary to the cleverness. Example:

> "Time here becomes thicker than anywhere else."
> — `j8_inst_004` "The Invisible Hierarchy of Hospital Corridors"

This passage about walking speed in hospital corridors is brilliant systems thinking, but the empathetic core (people waiting during surgery) is reached only at the end. The first three-quarters is taxonomic observation. The warmth arrives, but it has to work harder to land.

**2. The hsk-labeled formal dialogues (hsk7_literary_criticism, hsk9_bioethics_committee, etc.) are intellectually impressive but tonally neutral.** They are debate formats, not human encounters. The off-topic options are hilariously mismatched (a bioethics question answered with geopolitical analysis), which suggests these were generated with cross-contaminated distractor pools. But the primary issue is tone: these dialogues contain no warmth, no humor, no lived-in detail. They are academic performance, not human connection.

This is not necessarily a failure — some HSK 7-9 content should model formal discourse. But the ratio matters. If a learner encounters only debate-format dialogues at HSK 7+, the app loses its soul at precisely the level where advanced learners need it most.

The j-series HSK 7-9 dialogues (`j7_dlg_005` "The Sound Collector", `j8_dlg_005` "The Silent Musician", `j9_dlg_005` "The Sound of Old Wood") are the antidote: they are philosophically rich AND emotionally warm. They prove it is possible to be at HSK 9 vocabulary without becoming a debating society.

---

## 5. Dialogue Tone Assessment

### Three tiers of dialogue quality

**Tier 1: j-series dialogues (j1_dlg through j9_dlg) — Excellent.**

These dialogues are the crown jewels of the system. They have:
- Named characters with personality (Auntie Wang, Xiao Lin the designer, Master Xu the guqin maker)
- Sensory setups ("The shop smells like fresh baozi," "The train hums softly through the tunnels")
- Feedback that is characterful and warm ("Warm and observant — notices the cat's mood," "Nostalgic and true — captures the shift in perspective that comes with growing up")
- Comedy that is gentle and human, never mean

Standout dialogue: `j6_dlg_010` "The Escalating Misunderstanding" — the bookshelf/shoe rack confusion. This is Larry David observational comedy about social friction, without malice. The carpenter's "strangely compelling logic" and the player's response ("We've entered a very dangerous philosophical territory") is genuinely funny. The bed/boat punchline lands perfectly. This is Mel Brooks joyful absurdity meets Elaine May improvisational human truth.

Standout dialogue: `j5_dlg_020` "The Courtyard We Grew Up In" — childhood nostalgia at a parking lot that used to be a soccer field. The fifty-cent popsicle line ("She always gave us an extra one, saying it's hot out, have some more") is lived-in ordinary detail that creates genuine emotional resonance.

**Tier 2: hsk-labeled scenario dialogues (hsk4 through hsk9) — Intellectually strong, tonally neutral.**

These serve a purpose (formal register practice) but lack the warmth of the j-series. The setups are functional ("You are a literary critic participating in a televised roundtable"), the characters are roles not people, and the feedback is evaluative rather than warm. Not a failure per se, but they should not be the primary content at any level.

**Tier 3: gen_ prefix dialogues — Actively harmful to the brand.**

These must be rewritten or removed. Specific failures:

- `gen_restaurant_1_00_v0`: Setup is "A restaurant scenario at HSK 1 level." Setup_zh mixes English and Chinese: "HSK 1 级restaurant场景." The NPC asks "What's your name?" in a takeout ordering scenario. The second NPC line is "How much?" directed at the customer. The dialogue makes no narrative sense.

- `gen_shopping_1_00_v0`: Setup is "A shopping scenario at HSK 1 level." The entire interaction is NPC: "Hello!" → Player: "Hello!" → NPC: "How much?" This is not a scene. It is not a drill. It is nothing.

- `gen_emergency_3_00_v0`: Labeled as "Calling for help" emergency scenario. The actual NPC dialogue asks "Why did you choose this one?" — a shopping question. The content is incoherent.

- Across all gen_ files sampled: Feedback on correct answers is consistently "Correct response." — two words with no personality, no warmth, no teaching.

**Estimated scope of the problem**: There are approximately 150+ gen_ prefix files in the scenarios directory. If they are all of similar quality, this represents a substantial percentage of the dialogue content that is tonally dead and frequently broken.

---

## 6. Media Shelf Tone Assessment

**Verdict: Consistently strong. The best tone-aligned metadata in the system.**

The media catalog entries achieve something difficult: they are pedagogically useful AND genuinely interesting to read. The descriptions, cultural notes, and follow-ups read like recommendations from a well-read friend, not a textbook appendix.

**Evidence of success:**

> "Watch the vendor's hands. Street food prep in China is performance art. The visual context carries you through vocabulary you don't yet know."
> — `m_早餐中国_s01e07_jianbing`, follow-up

This is Bourdain: "Watch the vendor's hands" is a specific, actionable observation that also teaches you how to watch. "Performance art" reframes street food preparation with genuine respect.

> "Chinese suspense series open with slow observational tension, not action. The landscape does the emotional work before a single word of dialogue."
> — `m_隐秘的角落_e01_opening`, cultural note

Sharp media criticism that also functions as a listening strategy. The learner is being taught how to watch Chinese television, not just what vocabulary to extract.

> "许知远's interview style is deliberately awkward. He asks questions that make guests uncomfortable in productive ways. The silences are as important as the words."
> — `m_十三邀_chen_xiaoming`, cultural note

Honest characterization that respects both the host and the learner's intelligence. "Deliberately awkward" is precise. "Productive" is the key qualifier.

> "This film is banned in mainland China. That fact itself teaches you something about the relationship between art and institutions in China."
> — `m_活着_family_dinner`, follow-up

Measured, factual, and teaches cultural context without editorializing. Obama-adjacent: measured thoughtfulness, dignity.

> "Don't expect to understand it now. Bookmark it and return in a year. When you can follow 60% of this, your Mandarin has crossed into genuine fluency."
> — `m_读书_lu_xun`, follow-up

Compassionate toward the learner's current level. No pressure, no shame. "Bookmark it and return in a year" is restorative — it frames difficulty as a future gift, not a current failure.

### One minor media concern

The lower-HSK media entries (HSK 1-2) are slightly more functional and less literary in their cultural notes:

> "Homework pressure is a universal theme in Chinese family life. The comedy here resonates because every Chinese viewer has lived this exact scene."
> — `m_家有儿女_s01e01_homework`, cultural note

This is fine, but "universal theme" and "resonates" are generic media-criticism language. Compare with the HSK 6+ entries which have much more observational specificity. Not a failure — just a slight flatness at the lower levels.

---

## 7. The 10 Strongest Entries (Tone Exemplars)

1. **`j7_observe_001`** "The Woman Who Waters Dead Plants" — Grief expressed through ritual. The best single passage. "The posture of bending, tilting the can, and waiting is what's truly growing."

2. **`j9_dlg_005`** "The Sound of Old Wood" — The guqin maker dialogue. "Perfect vibration is mathematics — imperfect vibration is music." Philosophy through craft, warmth through specificity.

3. **`j1_observe_002`** "Rain on the Window" — Iyashikei at HSK 1. "The rain isn't heavy, but it's beautiful." Proves tone survives vocabulary simplification.

4. **`j6_dlg_010`** "The Escalating Misunderstanding" — The bookshelf/shoe rack comedy. "A shoe rack is just the juvenile form of a bookshelf?" Mel Brooks meets Larry David. Gentle absurdity, zero malice.

5. **`j5_dlg_020`** "The Courtyard We Grew Up In" — "Those small kindnesses are what truly made childhood warm. Nothing big — just someone willing to be a little extra good to you." Lived-in nostalgia.

6. **`j9_food_067`** "The Grammar of Rice" — Cultural essay through food. "A people who grow rice know in their bones that things which cannot be rushed will only be ruined by haste."

7. **`j4_urban_101`** "The Night Market Tofu Stall" — "'Doing two things well is enough.' She was very serious when she said this." Anthony Bourdain on the craft of food.

8. **`j7_observe_024`** "The Fishpond in the Park" — "'I'm not here to catch fish.'" The empty hook as metaphor for vanishing leisure. Observational perfection.

9. **`j5_identity_003`** "Speaking Two Languages at Home" — "I'm not two people, but I do have two doorways for expressing myself." Identity complexity without overwrought drama.

10. **`j8_dlg_005`** "The Silent Musician" — "You don't need to play 'well' — you only need to play 'truly.'" The musician who stopped performing because she got too good. Sondheim-level emotional complexity.

---

## 8. The 10 Weakest Entries (Rewrite Candidates)

1. **`gen_shopping_1_00_v0`** — "A shopping scenario at HSK 1 level." No scene, no character, no warmth. Feedback: "Correct response." Rewrite from scratch using j-series template.

2. **`gen_restaurant_1_00_v0`** — "A restaurant scenario at HSK 1 level." NPC asks customer's name for takeout, then says "How much?" to the customer. Incoherent AND tonally dead. Delete and replace.

3. **`gen_emergency_3_00_v0`** — Labeled emergency, contains shopping dialogue. Factually broken. Delete and replace.

4. **`gen_emergency_2_00_v0`** through **`gen_emergency_6_03_v0`** (entire gen_emergency series) — High likelihood of same structural problems. Audit all and likely replace.

5. **`01_restaurant.json`** — "You walk into a small restaurant for lunch." Functional but generic. Setup has no sensory detail, no character name, no atmosphere. The j-series HSK 1 dialogues prove this level can be warm. Rewrite with named character, sensory detail.

6. **`gen_phone_2_00_v0`** through the gen_phone series — Likely same template-generated issues as other gen_ files. Audit and replace.

7. **`gen_social_1_00_v0`** through gen_social series — Same concerns. "A social scenario at HSK 1 level" is not a setup.

8. **`hsk9_bioethics_committee.json`** — Intellectually impressive but distractor options are from completely different scenarios (geopolitics, Confucian-Daoist synthesis). The cross-contamination is obvious and jarring. Fix distractors, consider adding a moment of human warmth to the setup.

9. **`hsk7_literary_criticism.json`** — Same cross-contaminated distractor issue. Options from a museum negotiation scenario appear as wrong answers in a literary criticism debate. The correct answer is brilliant; the surrounding structure is broken.

10. **All gen_bank_* files** — Likely same template-generated quality. "A bank scenario at HSK X level" is not iyashikei. These need the j-series treatment: a named teller, afternoon light through bank windows, an old woman who comes every month to deposit the same amount.

---

## 9. Specific Failure Mode Instances Found

### Generic textbook voice
- All gen_ prefix dialogues (~150 files)
- `01_restaurant.json` setup
- gen_ feedback pattern: "Correct response." / "Off-topic — you were asked to [task], but this doesn't fit the conversation."

### Emotionally cold or flat writing
- gen_ prefix dialogues universally
- hsk-labeled formal dialogues (tonally neutral rather than cold, but lacking warmth)

### Stiff, unnatural dialogue
- `gen_restaurant_1_00_v0`: NPC says "How much?" to the customer ordering food
- `gen_emergency_3_00_v0`: emergency scenario with shopping dialogue

### English translations that lose warmth
- Not detected in the j-series. The English translations are consistently good — often literary in their own right.
- gen_ translations are technically accurate but affectless

### Over-intellectualization that loses tenderness
- Mild risk in some HSK 8 "system" passages that spend 80% on taxonomy before arriving at emotion
- hsk-labeled debate dialogues are entirely intellectual with no tenderness

### Cross-contaminated content
- hsk7_literary_criticism.json: distractor options from diplomatic negotiation and medical scenarios
- hsk9_bioethics_committee.json: distractor options from geopolitics and Confucian philosophy

### Failure modes NOT found
- Snark, cynicism, meanness, smugness: **None detected** in any content
- Excessive moralizing: **None** — even passages about dignity and ethics avoid preaching
- Melodrama: **None** — emotional moments are consistently understated
- Too much sadness without restoration: **None** — even grief passages (dead plants, demolished homes) find beauty or meaning

---

## 10. Whether the Broader Influence Mix Is Reflected

| Influence | Present? | Where |
|-----------|----------|-------|
| Alan Alda (warm intelligence, conversational grace) | Yes | j-series dialogue feedback, media follow-ups |
| Anthony Bourdain (genuine curiosity about food, no pretension) | Yes, strongly | Food passages across all levels, media food descriptions |
| Barack Obama (measured thoughtfulness, dignity) | Yes | Media cultural notes, recycling station passage |
| Fareed Zakaria (global perspective, clarity) | Yes | "Grammar of Rice," identity passages, media HSK 7+ notes |
| Tina Fey (sharp wit, never mean) | Yes, moderately | Comedy passages, bookshelf/shoe rack dialogue |
| Genzaburo Yoshino (gentle philosophical guidance) | Yes, strongly | The philosophical voice in HSK 7-9 passages is deeply Yoshino |
| Stephen Sondheim (emotional complexity beneath elegant surfaces) | Yes | "Speaking Two Languages," "The Silent Musician," identity theme |
| Mel Brooks (joyful absurdity, comedy as love) | Yes | Grandpa's glasses, family photo, bookshelf/shoe rack |
| Hayao Miyazaki (wonder in ordinary life) | Yes, the dominant aesthetic | Tea shops, rain, cats, park fishermen, dead plants, steam |
| Larry David (observational comedy, no malice) | Yes | Group chat passages, comedy theme across HSK 2-7 |
| Amy Sedaris (eccentric warmth, craft as joy) | Partial | Tofu seller, clockmaker — craft-as-identity is present but "eccentric" energy is lower |
| John Hodgman (deadpan intelligence, gentle pedantry) | Partial | Some HSK 7+ passages have this quality, but it's subtle |
| Elaine May (improvisational human truth) | Yes | j-series dialogue design — the best dialogues feel improvisational |
| Matt Yglesias (accessible systems thinking) | Yes | Hospital garden, recycling station, shared bicycle, institutional passages |

**Overall influence balance**: The Miyazaki/iyashikei strand is dominant, which is correct — it should be the ground note. The Bourdain/food strand is the second strongest, also correct for a China-focused app. The comedy strand (Brooks/Larry David/Fey) is well-represented but could be slightly more present in HSK 4-6, which skews observational/tender. The Hodgman/Sedaris eccentric-warmth energy is the weakest thread — it could be dialed up in a few passages without changing the overall aesthetic.

**The missing element**: The influence list includes people who are sharp about systems and institutions (Yglesias, Zakaria, Obama), and this is well-represented. But there is room for more content that gently names systemic absurdity — not snark, but the quiet "that's odd" of noticing how institutions actually work versus how they claim to work. The HSK 8 "school janitor" passage and the "filing cabinet" passage gesture toward this. More would be welcome.

---

## Summary Recommendations

1. **Highest priority**: Audit and replace all gen_ prefix dialogues (~150 files). These are the single largest tone failure. Replace with j-series style content.

2. **High priority**: Fix cross-contaminated distractor options in hsk-labeled dialogues (hsk7_literary_criticism, hsk9_bioethics_committee, and likely others in that set).

3. **Medium priority**: Rewrite old numbered dialogues (01_restaurant through 08_return_item) with j-series warmth — named characters, sensory detail, characterful feedback.

4. **Low priority**: Consider adding 2-3 more Hodgman/Sedaris-flavored passages at HSK 4-6 (eccentric characters who take small things very seriously, craft-obsessives with endearing quirks).

5. **Protect what's working**: The j-series passages and dialogues are genuinely excellent. Do not homogenize them. The range from "Rain on the Window" to "The Grammar of Rice" is exactly right — same sensibility, scaled to complexity. This is the voice. Everything else should sound like this.
