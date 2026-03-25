# Competitive Analysis -- Aelu

*Internal document. Last updated: February 2026.*
*Brutal honesty is the point. If we are worse at something, say so.*

---

## Market Landscape Overview

The Chinese learning app market splits roughly into six categories:

1. **SRS/Vocabulary tools** -- Hack Chinese, Anki, Pleco (flashcards). Focused on memorization. Minimal or no skill integration.
2. **Gamified course apps** -- Duolingo, HelloChinese, LingoDeer. Structured curricula with game mechanics. Strong on onboarding, weak on depth.
3. **Reading-focused tools** -- Du Chinese, The Chairman's Bao, Dong Chinese. Content-first, graded by HSK level. Weak on production skills.
4. **Writing/character tools** -- Skritter. Deep on stroke order and handwriting. Narrow in scope.
5. **Comprehensive courses** -- Mandarin Blueprint, Chinese Zero to Hero. Video-driven, curriculum-heavy. High commitment, high cost (or high time investment).
6. **Dictionary/reference** -- Pleco. The de facto standard. Not really a learning system, but everyone uses it.

**Where Aelu fits:** We sit at the intersection of categories 1, 2, and 3. We have SRS at the core (like Hack Chinese/Anki), structured multi-skill drills (like HelloChinese/LingoDeer), and a graded reader with the cleanup loop (like Du Chinese/TCB). We are not a video course, not a handwriting trainer, and not a dictionary. Our thesis is that these skills should be integrated under one adaptive system, not spread across five apps.

**Market dynamics:** The category is fragmented. Most serious learners use 3-5 tools simultaneously. There is no single dominant product for Mandarin the way Duolingo dominates casual language learning broadly. This fragmentation is both our opportunity (consolidation play) and our challenge (users already have established stacks).

---

## Master Comparison Table

| Feature | Aelu | Hack Chinese | Anki | Duolingo | HelloChinese | Skritter | Pleco | Du Chinese | Mandarin Blueprint | Chinese Zero to Hero | Chairman's Bao | LingoDeer | Dong Chinese |
|---------|----------|-------------|------|----------|-------------|---------|-------|-----------|-------------------|---------------------|---------------|----------|-------------|
| **Price (free tier)** | HSK 1-2 | Trial only | Free (full) | Limited (ads+hearts) | Limited lessons | Guest decks | Free (full dictionary) | Some free lessons | 14-day trial | Free intro course | None | Limited courses | 7-day trial, then 1 lesson/12hr |
| **Price (paid)** | $14.99/mo | $12/mo ($8/mo annual) | Free desktop+Android; $25 iOS one-time | $7/mo (annual) to $13/mo | $12/mo ($6/mo annual) | $15/mo ($8/mo annual) | $30-$60 one-time bundles | $15/mo ($10/mo annual) | $1,499 lifetime or ~$149/mo installments | ~$129 lifetime per bundle | $11/mo ($7/mo annual) | $13/mo ($6/mo annual); $120 lifetime | $10/mo ($7/mo annual) |
| **SRS method** | Adaptive spaced repetition + bayesian confidence + interleaving | SRS (proprietary) | FSRS (or SM-2) | Minimal internal scheduling | Basic SRS | SRS per character | SRS flashcards (paid add-on) | Basic flashcard review | Anki-based (Traverse) | None | Basic flashcard SRS | None (lesson progression) | SRS-like review scheduling |
| **Drill/exercise types** | 27 types | 1 (flashcard + oral mode) | 1 (flashcard) | ~4 (translate, match, tap, speak) | ~8 (translate, fill, speak, write, listen, match, video, reading) | ~3 (write, tone, meaning) | ~4 (flashcard, fill-in, tone, multiple-choice) | 1 (reading + tap-to-translate) | Video lessons + Anki flashcards | Video lessons + quizzes | Reading + comprehension questions | ~6 (translate, fill, match, listen, speak, write) | ~4 (reading, writing, ordering, gap-fill) |
| **Reading component** | Graded reader with cleanup loop | No | No (DIY via shared decks) | Sentence-level only | 1,000+ graded stories | No | Document reader (paid) | Core feature: 1,000+ graded stories | Sentence/passage progression | Lesson transcripts | Core feature: 9,500+ news articles | Sentence-level | Video subtitles + reading exercises |
| **Listening component** | Speed-controlled audio, listening drills | Audio pronunciation per word | Audio per card (if added) | Basic sentence audio | Native speaker videos, listening drills | Audio per character | Audio pronunciation (paid TTS) | Native audio per lesson | Video-based | Video-based | Audio per article | Sentence audio, listening exercises | Video-based listening |
| **Speaking/tone component** | Tone grading, speaking drills | Oral mode (self-graded) | No | Limited (speech recognition, poor tone handling) | Speech recognition + tone feedback | No | No | No | No | No | No | Limited speech recognition | No |
| **HSK alignment** | HSK 1-6 (preparing 7-9) | HSK 1-6 | DIY | Partial/unofficial | HSK 1-6 (new standard) | Textbook/HSK lists | Not structured by HSK | HSK 1-6+ | Not HSK-organized | HSK 1-6 | HSK 1-6+ | HSK 1-4 roughly | HSK 1-6 |
| **Offline capability** | Yes (local data) | No | Yes (syncs via AnkiWeb) | Yes (paid, downloaded lessons) | Yes (downloaded courses) | Yes (downloaded content) | Yes (fully offline) | Yes (downloaded lessons) | No (web-based video) | No (video streaming) | Yes (mobile app) | Yes (downloaded lessons) | No |
| **Platform** | Web (desktop + mobile browser) | Web | Desktop, web, iOS ($25), Android | iOS, Android, web | iOS, Android | iOS, Android, web | iOS, Android | iOS, Android, web | Web (Teachable + Traverse) | Web (Teachable) | Web, iOS, Android | iOS, Android | Web |
| **Target audience** | Serious adult learners, HSK preppers | Vocabulary-focused learners | Power users, customizers | Casual beginners | Structured beginners to intermediate | Character writers | Everyone (as reference) | Reading-focused learners | Committed beginners (high investment) | Budget-conscious structured learners | Reading-focused intermediate+ | Structured beginners | Contextual learners, visual learners |
| **Unique selling point** | Cleanup loop + 44 drill types + adaptive multi-skill | Curated HSK vocab + clean UI + oral mode | Free + infinitely customizable | Massive brand + gamification + mobile-native | Best beginner Chinese app + native video | Handwriting with stroke-level feedback | The Chinese dictionary + OCR + doc reader | Beautiful graded reading content | Hanzi Movie Method mnemonics | Affordable video courses by native speakers | Daily news-based graded reading | Grammar-first approach for Asian languages | Video-based contextual learning |

---

## Individual Competitor Profiles

---

### Hack Chinese

**What they are:** An SRS-based Chinese vocabulary learning platform focused on getting you to remember characters and words efficiently.

**Pricing:** $12/month or $8/month billed annually ($96/year). Free trial available.

**Target audience:** Intermediate learners who want focused vocabulary building. University students studying Chinese. HSK test preppers who need to grind word lists.

**What they do well:**
1. Clean, focused UI -- no distractions, no gamification bloat. You open it, you study.
2. Pre-made HSK and textbook-aligned word lists save setup time vs. Anki.
3. Oral mode for self-assessed speaking practice is a genuine differentiator among flashcard tools.
4. Audio pronunciation for 100,000+ words -- comprehensive coverage.
5. Analytics dashboard gives honest visibility into study consistency and progress.

**What they don't do well:**
1. It is fundamentally a flashcard app. One drill type (recognition/recall) with an oral mode bolted on. No sentence-level, no cloze, no listening comprehension.
2. No reading component. You learn words in isolation, not in context.
3. No listening practice beyond individual word audio.
4. No speaking/tone grading -- oral mode is self-assessed, which means you can fool yourself.
5. No grammar instruction or sentence construction practice.

**Their users say:**
- Praise: "Simple and effective." "Better than Anki for Chinese because everything is pre-built." "The analytics keep me accountable."
- Complaints: "Gets repetitive after a while -- just flashcards." "Wish it had reading or listening." "Expensive for what it is -- $12/month for flashcards."

**How we're different:** We have 44 drill types vs. their 1. We have a graded reader with the cleanup loop. We have tone grading, listening drills with speed control, sentence construction, cloze deletion. They are a vocabulary tool; we are a multi-skill learning system.

**When someone should use BOTH:** If someone wants Hack Chinese's clean vocabulary grinding alongside Mandarin's multi-skill drills. Hack Chinese for pure vocab speed; Aelu for integrating that vocab into reading, listening, and production.

**Switching trigger:** A Hack Chinese user who realizes they can recognize characters but cannot understand sentences, parse listening, or produce speech. The "I know 2,000 words but can't have a conversation" moment.

**Switching barrier:** Hack Chinese users have study history and streaks. They would lose their review schedule data. If they have already memorized the words, starting over in Aelu feels like regression.

**Our honest weakness vs. them:** Their vocabulary coverage is broader (100,000+ words with audio vs. our 10,000+ items across HSK 1-9). Their word lists cover many more textbooks. For pure vocabulary grinding, they have more content. But our gap has narrowed significantly with full HSK 1-9 coverage.

---

### Anki (for Chinese learning)

**What they are:** A free, open-source, infinitely customizable spaced repetition flashcard system. Not Chinese-specific, but the most-used SRS tool among serious Chinese learners.

**Pricing:** Free on desktop, web, and Android. $24.99 one-time purchase on iOS. Community-made decks and add-ons are free.

**Target audience:** Power users. People who want full control over their learning system. Technical learners comfortable with configuration. University students. Long-term committed learners.

**What they do well:**
1. Free (essentially). The economics are unbeatable. $0 on most platforms, $25 one-time on iOS.
2. FSRS algorithm is now state-of-the-art -- Anki adopted it in recent versions and it adapts to individual learners over time.
3. Infinite customization -- card templates, add-ons, plugins, media embedding. You can build exactly the system you want.
4. Massive ecosystem -- thousands of shared Chinese decks, community guides, add-on developers.
5. Offline-first, cross-platform sync via AnkiWeb. Your data is yours.

**What they don't do well:**
1. Brutal learning curve. The settings screen alone deters most people. New users spend hours configuring before studying.
2. Deck quality varies wildly. Finding a good Chinese deck requires research. Many shared decks have errors, bad audio, or poor example sentences.
3. One drill type: flashcard. No listening drills, no cloze (unless you build it yourself), no reading, no speaking, no tone grading.
4. No curriculum. Anki does not tell you what to study next. You must decide or find a deck that imposes order.
5. No reading component. No cleanup loop. No context. Words exist in isolation unless you manually add example sentences.

**Their users say:**
- Praise: "Nothing beats Anki for long-term retention." "Free and I control everything." "FSRS changed the game." "I have 10,000 cards and it just works."
- Complaints: "Took me a week to set it up properly." "Review pile gets overwhelming." "It's ugly." "I know words but can't read or listen." "Making good cards takes forever."

**How we're different:** Aelu is what you get if you take Anki's SRS core, wrap it in a curriculum, add 44 drill types, include a graded reader with the cleanup loop, add listening and speaking drills, and remove the need to build anything yourself. You open Aelu and study. You open Anki and configure.

**When someone should use BOTH:** Anki for supplementary vocabulary outside our HSK scope (specialized topics, university textbook words). Aelu for structured multi-skill practice.

**Switching trigger:** An Anki user who is tired of maintaining decks, wants reading and listening integrated, or wants tone grading. Someone who has used Anki for a year and realizes they have a large passive vocabulary but poor production skills.

**Switching barrier:** This is the biggest one. Anki users have invested enormous time in their decks -- sometimes thousands of cards with custom media. They have review history spanning years. Walking away from that feels like abandoning work. And Anki is free. Asking someone to pay $14.99/month to replace something free requires a strong value proposition.

**Our honest weakness vs. them:** Anki is free. Anki has FSRS (we use adaptive spaced repetition, but theirs is the canonical implementation). Anki's ecosystem is vastly larger. Anki works for any language and any subject -- it is a general-purpose tool. If someone is technically proficient and willing to invest setup time, Anki + a good deck + supplementary reading tools can replicate much of what we do, for free. Our advantage is integration and ease-of-use, not raw capability.

---

### Duolingo (Chinese course)

**What they are:** The world's most popular language learning app, with a Chinese (Simplified) course. Gamified, mobile-native, and designed for habit formation.

**Pricing:** Free with ads and hearts. Super Duolingo: $7/month (annual) to $13/month (monthly). Duolingo Max: $30/month (includes AI features). Family plan: $120/year for up to 6 accounts.

**Target audience:** Absolute beginners. Casual learners. People who want 5-10 minutes/day. People who respond to gamification (streaks, XP, leaderboards). Young learners.

**What they do well:**
1. Habit formation. The streak system, push notifications, and gamification genuinely get people to open the app daily. Whatever we think of it pedagogically, it works for engagement.
2. Brand recognition and trust. "I'm learning Chinese" often means "I'm using Duolingo." They own the mindshare.
3. Mobile-native experience. The app is polished, fast, and designed for phones. Ours is a web app.
4. Low barrier to entry. No account setup friction, no configuration, no decisions. You just start.
5. Community and social features. Leaderboards, friend challenges, and a massive Reddit community create accountability.

**What they don't do well:**
1. Their Chinese course is notably weaker than their European language courses. No Stories feature, limited grammar explanations, fewer exercise types.
2. Tone instruction is poor. Multiple reviewers call this the course's most serious flaw. For a tonal language, this is disqualifying for serious study.
3. Character introduction is confusing -- shows characters without proper explanation of meaning or pronunciation before testing.
4. Limited speaking practice with poor tone recognition. The speech engine does not reliably distinguish tones.
5. Sentence-level only. No connected reading, no passage comprehension, no real listening practice.

**Their users say:**
- Praise: "It got me started." "The streak keeps me coming back." "It's free and I like the owl."
- Complaints: "I did Duolingo Chinese for a year and can barely order food." "The tone teaching is terrible." "Why does Chinese get worse features than Spanish?" "It's a game, not a language course."

**How we're different:** We treat Chinese as a tonal language that requires tone-specific drilling, contextual reading, and listening practice -- none of which Duolingo does well. We have 44 drill types vs. their ~4. We have graded reading. We have tone grading. We do not gamify; we give honest metrics.

**When someone should use BOTH:** Duolingo for the first week to get basic exposure and build the daily habit. Aelu once they are ready to actually learn.

**Switching trigger:** A Duolingo user who tries to speak Chinese to a native speaker and is not understood. The moment they realize the app taught them to tap buttons but not to communicate.

**Switching barrier:** Duolingo's streak. Seriously. People with 200+ day streaks will not abandon them. The gamification that makes Duolingo effective for engagement also creates lock-in. Also, Duolingo is effectively free for most users.

**Our honest weakness vs. them:** Mobile experience. Duolingo is a beautifully designed native app. We are a web app that works in mobile browsers but is not a native app. For someone who wants to study on their phone during a commute, Duolingo is simply better as a mobile experience. Also, their onboarding is frictionless -- ours requires more commitment.

---

### HelloChinese

**What they are:** The most popular Chinese-specific gamified learning app. Structured courses from beginner through intermediate, with a good mix of drill types.

**Pricing:** Free with limited lessons. Premium: $12/month, $26/quarter, or $70/year (~$6/month).

**Target audience:** Beginners to low-intermediate learners who want a structured, app-based Chinese course. People who find Duolingo too shallow for Chinese but still want a gamified experience.

**What they do well:**
1. Best beginner Chinese app, period. The pinyin introduction, tone drills, and progressive character introduction are well-designed.
2. 1,000+ graded stories with native speaker videos -- genuine reading and listening content.
3. Speech recognition that actually provides tone feedback. Better than Duolingo's by a wide margin for Chinese.
4. First app to build courses on the new HSK 3.0 standard. They are ahead on this.
5. Handwriting practice integrated into lessons. Stroke order instruction.

**What they don't do well:**
1. SRS is basic -- not a sophisticated scheduling algorithm. Review scheduling does not adapt well to individual learner patterns.
2. Paywall surprise -- users report feeling baited when free content runs out without warning.
3. Video quality control issues -- native speaker videos sometimes feature mumbling or unclear pronunciation.
4. Limited for learners above HSK 3-4. The app's depth runs out in the intermediate range.
5. Review system is disconnected from the "Immerse" reading feature -- your reading gaps do not feed into your drill schedule.

**Their users say:**
- Praise: "Best app for starting Chinese." "Way better than Duolingo for Chinese." "The speech recognition actually works." "I love the graded stories."
- Complaints: "I outgrew it after 6 months." "The paywall snuck up on me." "Video speakers are sometimes hard to understand." "Review system feels random."

**How we're different:** Our SRS is substantially more sophisticated (adaptive spaced repetition with confidence-weighted scheduling vs. their basic interval scheduling). Our cleanup loop connects reading directly to drill scheduling -- theirs does not. We have 44 drill types vs. their ~8. Our diagnostics track per-skill readiness. We are designed for the full HSK 1-6+ journey; they taper off around HSK 4.

**When someone should use BOTH:** HelloChinese for the first 1-3 months of absolute beginner study (their pinyin and basic character introduction is excellent), then Aelu for the structured HSK progression with deeper SRS.

**Switching trigger:** A HelloChinese user who reaches intermediate level and finds the app has nothing more to offer. Or a user who wants their reading struggles to directly inform their drill schedule (the cleanup loop).

**Switching barrier:** HelloChinese has a beautiful mobile app. Users who prefer native iOS/Android apps will find our web interface less polished on mobile. Their graded story library (1,000+) is larger than our current content set.

**Our honest weakness vs. them:** Their beginner onboarding is better than ours. Their mobile app experience is better than our mobile web experience. Their content library (stories, videos) is significantly larger. For a true beginner on a phone, HelloChinese is currently the better choice.

---

### Skritter

**What they are:** The definitive Chinese/Japanese character handwriting practice app, with stroke-level feedback and SRS.

**Pricing:** $15/month, or $9/month billed annually ($99/year). $299 lifetime. Guest accounts have limited free access.

**Target audience:** Learners who want to write Chinese by hand. Students in Chinese classes that require handwriting. Character enthusiasts. Heritage learners refining writing skills.

**What they do well:**
1. Handwriting recognition with real-time stroke-level feedback. Nothing else comes close for learning to write characters.
2. SRS specifically tuned for character recall -- meaning, tone, pinyin, and writing tested separately.
3. Hundreds of textbook and HSK word lists pre-loaded. Works alongside university courses.
4. Cross-platform with offline support. Polished native apps.
5. Du Chinese integration -- save words in Du Chinese, they appear in Skritter. Smart ecosystem play.

**What they don't do well:**
1. Narrow scope -- it teaches you to write characters. That is mostly it. No reading, no listening comprehension, no sentence construction.
2. Expensive for what it is. $15/month for character writing practice feels steep.
3. Handwriting recognition does not handle cursive or semi-cursive characters. Advanced writers hit a wall.
4. No grammar, no context, no connected reading. Characters learned in isolation.
5. The SRS scheduling can produce overwhelming review piles.

**Their users say:**
- Praise: "Only app that teaches real handwriting." "Stroke feedback is incredibly detailed." "Paired with a textbook, it's unbeatable for characters."
- Complaints: "Too expensive for just writing practice." "I can write characters but still can't read a paragraph." "Review pile gets out of control." "Wish it did more than just characters."

**How we're different:** We do not do handwriting at all. We and Skritter have almost zero overlap. We focus on recognition, listening, speaking, reading, and production -- all the things Skritter does not do. They focus on the one thing we do not do.

**When someone should use BOTH:** Always. Skritter for writing, Aelu for everything else. These are genuinely complementary tools.

**Switching trigger:** This is not really a switching scenario -- it is an adding scenario. A Skritter user might add Aelu when they realize writing ability does not translate to reading fluency or listening comprehension.

**Switching barrier:** None, really. These tools serve different purposes. A user might resist paying for both ($14.99 + $15 = $29.99/month), but there is no functional overlap creating switching friction.

**Our honest weakness vs. them:** We have no handwriting component at all. If someone needs to write Chinese by hand (for classes, for calligraphy, for the HSK written section), they need Skritter or something like it. We cannot replace this.

---

### Pleco

**What they are:** The indispensable Chinese dictionary app. Also includes flashcards, OCR, document reader, and handwriting input. The Swiss Army knife of Chinese learning tools.

**Pricing:** Free (base dictionary + search). Basic Bundle: $30 one-time (OCR, flashcards, stroke order, document reader, audio, Oxford dictionary). Professional Bundle: $60 one-time (multiple premium dictionaries + all add-ons).

**Target audience:** Every Chinese learner. Pleco is the universal tool. Beginners to near-native speakers all use it.

**What they do well:**
1. The best Chinese-English dictionary available. Period. 130,000+ words, 20,000+ example sentences, multiple dictionary sources.
2. OCR -- point your camera at Chinese text and get instant lookup. Transformative for real-world use.
3. Document reader -- open any Chinese text or PDF and tap to look up words. This is essentially a reading tool.
4. One-time pricing. Pay once, use forever. No subscription fatigue.
5. Completely offline. Works anywhere with no internet connection.

**What they don't do well:**
1. The flashcard system, while functional, is not a modern SRS. It is an add-on, not the core product. Review scheduling is adequate but not adaptive.
2. No structured curriculum. Pleco does not tell you what to learn or in what order.
3. No drills beyond basic flashcards (fill-in, multiple-choice, tone test). No listening comprehension, no speaking, no sentence construction.
4. UX is functional but dated. The interface prioritizes information density over aesthetics.
5. No reading content -- you bring your own. The document reader is powerful but requires external text sources.

**Their users say:**
- Praise: "I cannot learn Chinese without Pleco." "Best dictionary, no contest." "OCR changed how I interact with Chinese in the real world." "Worth every penny of the $60."
- Complaints: "Flashcards are clunky compared to Anki." "The app looks like it was designed in 2012." "Pleco 4.0 has been promised for years." "It's a dictionary, not a learning system."

**How we're different:** Pleco is a reference tool; we are a learning system. Pleco helps you look things up; we help you practice, retain, and build skills. They answer "what does this word mean?" We answer "what should you study next, and how?"

**When someone should use BOTH:** Always. Pleco as your dictionary (for reading Chinese in the wild, looking up words in conversation, OCR on signs and menus). Aelu as your daily study system.

**Switching trigger:** Not a switching scenario. No one stops using Pleco. The trigger for adding Aelu is when a Pleco user realizes they keep looking up the same words and wants a system that forces retention.

**Switching barrier:** N/A. These are complementary. Pleco users might resist paying $14.99/month for Aelu when Pleco's flashcards are "good enough" -- even if they are not actually good enough.

**Our honest weakness vs. them:** Pleco's dictionary is vastly superior to anything we offer. Their OCR is a feature we cannot replicate in a web app. Their document reader handles any Chinese text; our graded reader is limited to our curated content. Pleco is a 15+ year product with deep, battle-tested Chinese-specific engineering. We are new.

---

### Du Chinese

**What they are:** A graded reading app for Chinese learners. Beautifully designed, content-rich, focused specifically on improving reading comprehension through stories.

**Pricing:** Free for some lessons. Premium: $15/month, $80/six months, $120/year ($10/month). 50% student discount available.

**Target audience:** Intermediate learners who want to read more Chinese. Learners who are tired of flashcards and want context. People who enjoy stories and cultural content.

**What they do well:**
1. Beautiful design -- widely praised as one of the best-designed Chinese learning apps. The reading experience is genuinely pleasant.
2. Extensive graded content -- hundreds of stories across HSK levels, with cultural relevance and variety.
3. Tap-to-translate with clean gloss UI. Natural reading flow with instant word lookup.
4. Native audio for every lesson -- doubles as listening practice.
5. Skritter integration -- save words from Du Chinese and they appear in Skritter for writing practice. Smart ecosystem thinking.

**What they don't do well:**
1. No SRS. The flashcard system is basic and not spaced repetition. Words you look up do not systematically become practice items.
2. No speaking or tone practice. Reading and listening only.
3. Expensive for a reading app. $15/month is the highest in this category.
4. Content update frequency is slow. Users report wanting more stories more often.
5. No grammar instruction. No production drills. Reading is passive unless you take notes separately.

**Their users say:**
- Praise: "Best reading app for Chinese, hands down." "The stories are interesting and well-graded." "Design is gorgeous." "Audio quality is excellent."
- Complaints: "Too expensive." "Not enough new content." "I read the stories but don't retain the vocab." "No SRS is a real gap." "Short stories -- I want something longer."

**How we're different:** Our graded reader has the cleanup loop -- every word you look up becomes a drill. Du Chinese shows you a word's meaning; we show you the meaning and then make you practice it until you know it. We also have 44 drill types, tone grading, listening drills, and multi-skill diagnostics.

**When someone should use BOTH:** Du Chinese for its larger and more varied story library (cultural content, longer narratives). Aelu for turning reading gaps into active practice.

**Switching trigger:** A Du Chinese user who keeps looking up the same words repeatedly and realizes passive reading is not building retention. The "I've read 200 stories but my vocabulary hasn't grown" realization.

**Switching barrier:** Du Chinese's design and reading experience are genuinely beautiful. Users who love the reading flow may find our reader less polished. Their content library is significantly larger and more varied than ours.

**Our honest weakness vs. them:** Their content library dwarfs ours. Their app design is better. Their reading experience is more immersive. If someone just wants to read Chinese stories at their level with excellent design, Du Chinese is the better product right now. Our advantage is what happens after the reading -- the cleanup loop and multi-skill integration.

---

### Mandarin Blueprint

**What they are:** A comprehensive, premium Chinese course built around the "Hanzi Movie Method" (mnemonic system for characters) and comprehensible input methodology.

**Pricing:** $1,499 lifetime (one-time), or $149/month for 12-month installment plan, or 3 payments of $529. 14-day free trial. $7 extended trial option.

**Target audience:** Committed beginners willing to invest significant money and time. Self-directed adults who want a structured path from zero to advanced. People who respond to mnemonic techniques and video instruction.

**What they do well:**
1. The Hanzi Movie Method is a genuinely creative mnemonic system. Users who click with it report fast character memorization.
2. Comprehensive structure -- 9,000+ lessons from characters to words to sentences to passages. Clear progression.
3. Active community with live events and 24/7 support. Not just an app -- a learning ecosystem.
4. Non-native founders who learned Chinese themselves. Relatable perspective for adult learners.
5. High completion rates for those who commit. Strong testimonials about reaching conversational ability.

**What they don't do well:**
1. Extremely expensive. $1,499 lifetime or $149/month is 10x our pricing. This prices out most casual learners.
2. High time commitment -- the method requires substantial daily study. Not a 10-minutes-a-day tool.
3. SRS is handled through Traverse (formerly Anki import), which users report as unreliable.
4. Not HSK-organized. Does not directly prepare for standardized tests.
5. Video-based means no offline use without caching, and passive video watching can feel slow.

**Their users say:**
- Praise: "The Hanzi Movie Method actually works." "I was reading characters within 5 weeks." "Best course for serious learners." "Community is supportive."
- Complaints: "Way too expensive." "Traverse app is buggy." "Too slow in early phases." "Non-native teachers bother me." "Could take years to finish the full course."

**How we're different:** We are a daily practice tool, not a video course. We cost $14.99/month, not $1,499. We are HSK-aligned. Our SRS is built-in and sophisticated, not bolted on via a third-party tool. We focus on active practice (44 drill types), not passive video consumption.

**When someone should use BOTH:** Mandarin Blueprint for the conceptual framework and mnemonic techniques. Aelu for daily practice, SRS review, and skill-specific drilling.

**Switching trigger:** Someone who bought Mandarin Blueprint, found the early phases too slow or the Traverse SRS too clunky, and wants active practice now rather than watching more videos.

**Switching barrier:** Sunk cost. If someone paid $1,499, they are going to use the product. The financial commitment creates stickiness. Also, the Hanzi Movie Method is specific to their system -- learners invested in those mnemonics may not want to switch approaches.

**Our honest weakness vs. them:** They have 9,000+ lessons. We have 10,000+ vocabulary items but fewer structured lessons. Their mnemonic system provides something we do not offer -- a framework for how to memorize characters. We assume you will learn through exposure and drilling; they give you a specific cognitive technique.

---

### Chinese Zero to Hero

**What they are:** An affordable, structured video course series covering HSK 1-6, taught by native Chinese speakers on Teachable.

**Pricing:** Individual courses ~$40-$60 each. Ultimate Bundle: ~$129 lifetime (all courses). Occasional discounts bring this lower.

**Target audience:** Budget-conscious learners who want structured video instruction. Students preparing for HSK exams. People who prefer learning from native speakers.

**What they do well:**
1. Outstanding value. The Ultimate Bundle at ~$129 is remarkably cheap for HSK 1-6 coverage.
2. Native speaker instructors who explain grammar clearly and engagingly.
3. Well-structured course progression aligned to HSK levels.
4. Constantly updated with new content. Active course development.
5. Language Player tool for immersion with comprehensible input from real Chinese media.

**What they don't do well:**
1. No SRS or adaptive review system. You watch videos and take quizzes, but there is no spaced repetition.
2. Practice opportunities are limited -- quizzes are basic multiple-choice and too easy.
3. Vocabulary lists are missing at higher levels.
4. Video-only format means no active speaking, tone, or writing practice.
5. Not a daily practice tool -- it is a course you watch, not a system that adapts to you.

**Their users say:**
- Praise: "Best value in Chinese learning." "Grammar explanations are the clearest I have found." "Native teachers make a real difference." "Helped my listening enormously."
- Complaints: "Quizzes are too easy." "I need more practice, not more videos." "No SRS means I forget what I learned." "Great for understanding, poor for retention."

**How we're different:** We are a practice system; they are a teaching system. They explain grammar and vocabulary through videos; we drill you on it through 27 exercise types with adaptive scheduling. They are a course you complete; we are a tool you use daily.

**When someone should use BOTH:** Chinese Zero to Hero for grammar instruction and listening to native explanations. Aelu for daily active practice and retention of what you learned in their videos.

**Switching trigger:** A Chinese Zero to Hero user who finishes videos but cannot remember the content a week later. Someone who wants SRS and active drilling.

**Switching barrier:** $129 lifetime is already paid. Free content is also available. Users may not want to add a $14.99/month subscription on top.

**Our honest weakness vs. them:** They have native speaker instruction -- video lessons taught by Chinese people explaining their own language. We do not have video instruction. For grammar understanding and listening to natural Chinese explanation, they are superior. We also cannot match their pricing -- $129 one-time vs. our $14.99/month ongoing.

---

### The Chairman's Bao

**What they are:** A news-based graded reading platform with 9,500+ articles across HSK levels. Daily new content covering current events in China and internationally.

**Pricing:** $11/month, $28/quarter, $50/six months, $88/year, or $154/two years. $385 lifetime.

**Target audience:** Intermediate to advanced learners who want to read real Chinese content. Students who want current events context. Teachers looking for classroom reading material.

**What they do well:**
1. Daily new content. 9,500+ articles and growing. The content never runs out.
2. News-based, which means culturally current and relevant. You learn about real China, not textbook scenarios.
3. HSK-graded from 1 to 6+. Genuinely useful progression.
4. Pop-up dictionary, grammar notes, audio recordings, and comprehension questions per article.
5. Clean, intuitive UI. Available on web, iOS, and Android.

**What they don't do well:**
1. Reading-focused only. No speaking, no tone practice, no production drills.
2. Flashcard SRS is basic and not the core value proposition.
3. News content style can feel dry for learners who prefer stories or dialogue.
4. No cleanup loop -- looking up words does not systematically create practice items.
5. Higher levels assume background knowledge of Chinese current events that foreign learners may lack.

**Their users say:**
- Praise: "Best resource for reading practice." "Love the daily new articles." "HSK grading is accurate." "Great for intermediate learners who need reading material."
- Complaints: "Gets boring -- it's all news." "Flashcards are an afterthought." "I look up the same words every article and nothing happens." "Wish it had more exercise types."

**How we're different:** Our graded reader feeds into the cleanup loop -- looked-up words become drills. We also offer 44 drill types, tone grading, listening practice, and multi-skill diagnostics. They are a reading platform; we are a multi-skill learning system with reading integrated.

**When someone should use BOTH:** TCB for the massive news-based reading library and cultural exposure. Aelu for turning reading gaps into active practice and building other skills.

**Switching trigger:** A TCB user who realizes they keep looking up the same words because there is no retention mechanism. Someone who wants practice beyond reading.

**Switching barrier:** TCB's content library (9,500+ articles) is enormous. Users who love the daily reading habit may not want to give up the content volume.

**Our honest weakness vs. them:** Content volume. 9,500+ articles vs. our limited graded reader content. Daily new content means they never run out of fresh material. Their news-based approach provides cultural education we do not offer. For pure reading volume, they win decisively.

---

### LingoDeer (Chinese)

**What they are:** A structured language learning app originally designed for Asian languages (Chinese, Japanese, Korean), with a grammar-first teaching approach.

**Pricing:** $13/month, $33/quarter, $77/year. Lifetime: $120-$160. Free trial with limited courses.

**Target audience:** Beginners who want structured grammar instruction. Learners who find Duolingo too shallow. People studying multiple Asian languages.

**What they do well:**
1. Grammar explanations are thorough and well-structured. Better than Duolingo and comparable to HelloChinese for grammar clarity.
2. Pinyin instruction is excellent -- comprehensive audio files for all sounds.
3. Character writing practice with stroke order. Integrated handwriting drills.
4. Clean interface that supports simplified and traditional Chinese.
5. LingoDeer Plus supplementary app adds game-based review exercises.

**What they don't do well:**
1. No SRS. Lesson progression is linear, not adaptive. No spaced repetition scheduling.
2. Limited content depth -- effectively covers HSK 1-3 at most. Intermediate and above learners outgrow it quickly.
3. Content ordering issues -- teaches less common vocabulary before common words.
4. Speaking practice is limited. Speech recognition exists but is not reliable.
5. No reading component. Sentence-level exercises only, no passages or stories.

**Their users say:**
- Praise: "Best grammar explanations in any language app." "Pinyin section is outstanding." "Better than Duolingo for Chinese by far." "Character writing is a nice addition."
- Complaints: "I finished the Chinese course in 2 months and there's nothing else." "No SRS means I forget everything." "Drawing characters is glitchy." "Feels incomplete."

**How we're different:** We have SRS (they do not). We cover HSK 1-6+ (they cover roughly 1-3). We have 44 drill types (they have ~6). We have a graded reader (they have none). We have tone grading (they do not). We continue to be useful at intermediate and advanced levels.

**When someone should use BOTH:** LingoDeer for initial grammar instruction and pinyin foundation (their explanations are genuinely good). Aelu for ongoing daily practice with SRS.

**Switching trigger:** A LingoDeer user who finishes the Chinese course content (roughly HSK 3) and needs something for the next level.

**Switching barrier:** LingoDeer's lifetime plan ($120-$160) means users feel they should keep using what they paid for. Their mobile app is better designed for phone use than our web app.

**Our honest weakness vs. them:** Their grammar explanations are more explicit and better structured than ours. We assume grammar is learned through exposure and drilling; they teach it directly with clear explanations. For pure grammar instruction, they are better. Their mobile app experience is also more polished.

---

### Dong Chinese

**What they are:** A web-based Chinese learning tool focused on contextual learning through videos, reading exercises, writing practice, and an adaptive level system.

**Pricing:** Free 7-day trial, then 1 lesson per 12 hours free. Premium: ~$10/month, ~$26/quarter, ~$50/six months, ~$80/year.

**Target audience:** Learners who want context-rich vocabulary learning. Visual/video learners. People who want reading and writing practice integrated with media content.

**What they do well:**
1. Video-based contextual learning -- adds interactive subtitles to YouTube videos matched to your level. Vocabulary learned in natural context.
2. Adaptive level assessment -- a 10-minute quiz places you accurately and adjusts content recommendations.
3. Character writing practice with progressive hints. Teaches stroke order with feedback.
4. Reading exercises include sentence ordering, gap-fill, and word identification -- more varied than basic flashcards.
5. Dictionary with contextual examples, media clips, and images. Rich word profiles.

**What they don't do well:**
1. Web-only. No native mobile app.
2. Content is video-dependent -- if YouTube videos are taken down or geoblocked, lessons break.
3. No structured HSK course progression -- more of a tool than a curriculum.
4. No speaking or tone grading. Listening is passive (via video).
5. Small user base means less community support and fewer reviews to gauge quality.

**Their users say:**
- Praise: "Contextual learning with real videos is engaging." "Writing practice is well-designed." "Level assessment is accurate." "Great for supplementing other study."
- Complaints: "Not enough content at higher levels." "Web-only is limiting." "Sometimes videos disappear." "Hard to use as a primary study tool."

**How we're different:** We have a structured HSK curriculum; they have an adaptive tool. We have 44 drill types; they have ~4. We have tone grading and speaking drills; they do not. Our content does not depend on external video platforms.

**When someone should use BOTH:** Dong Chinese for video-based immersion and contextual vocabulary exposure. Aelu for structured daily practice and SRS review.

**Switching trigger:** A Dong Chinese user who wants a more structured study path and SRS-driven retention.

**Switching barrier:** Users who love the video-based approach may find our text-based drills less engaging. Their writing practice component has no equivalent in Aelu.

**Our honest weakness vs. them:** Their video-based contextual learning is more immersive and engaging than our drill-based approach. They provide writing practice that we lack entirely. Their adaptive level assessment and matching is a smart UX feature we do not have.

---

## Head-to-Head Comparisons

### "Why Aelu over Hack Chinese?"

Both are SRS-based tools for serious Chinese learners at similar price points ($14.99/month vs. $12/month). Here is the honest comparison:

**Choose Aelu if:** You want more than flashcards. Aelu has 44 drill types (reading, listening, speaking, cloze, sentence construction, tone pairs, etc.) vs. Hack Chinese's 1 (flashcard with oral mode). Aelu has a graded reader where looked-up words become drills. Aelu has tone grading. Aelu has multi-skill diagnostics that track vocabulary, listening, reading, and tones separately.

**Choose Hack Chinese if:** You want the largest possible pre-built Chinese vocabulary database with clean UI and minimal friction. Hack Chinese has audio for 100,000+ words. Aelu has 10,000+ items across HSK 1-9. If your primary goal is raw vocabulary acquisition and you do not need reading, listening, or speaking practice integrated, Hack Chinese has broader coverage.

**The real difference:** Hack Chinese is a vocabulary tool. Aelu is a multi-skill learning system. Hack Chinese makes you recognize and recall words. Aelu tries to make you a better reader, listener, speaker, and test-taker. If you define "learning Chinese" as "knowing words," Hack Chinese is efficient. If you define it as "being able to read, listen, speak, and pass HSK," Aelu does more.

**Our honest gap:** Content volume. We need significantly more items, more reading passages, and broader HSK coverage before we can match their breadth. This is our top priority.

---

### "Why Aelu over Anki?"

This is the hardest question we face because Anki is free and extremely capable.

**The $14.99/month is buying you:**
1. **No setup time.** Anki requires finding or building decks, configuring settings, adding media, and maintaining cards. Aelu works out of the box with curated, HSK-aligned content.
2. **44 drill types instead of 1.** Anki shows you a card and you rate yourself. Aelu gives you cloze deletions, sentence construction, listening with speed control, tone pair drills, speaking exercises, and more. Different cognitive skills, different exercise types.
3. **The cleanup loop.** Read graded passages, look up words, and those words automatically enter your SRS queue. Anki cannot do this. You would need to manually create a card for every word you encounter while reading.
4. **Tone grading.** Aelu evaluates your pronunciation. Anki cannot.
5. **Multi-skill diagnostics.** Aelu tells you your listening lags behind your vocabulary and adjusts. Anki tracks card-level recall but has no concept of language skills.
6. **A curriculum.** Aelu decides what you should study next based on HSK progression and your performance data. Anki reviews what you put in it.

**When Anki is genuinely better:**
- If you are technically proficient and enjoy building systems, Anki's customization is unmatched.
- If you study multiple languages or subjects, Anki is a general-purpose tool.
- If you have already invested years in Chinese Anki decks with thousands of cards.
- If $14.99/month matters and you have time to invest in setup.
- If you need specialized vocabulary (medical Chinese, legal Chinese, regional dialects) that we do not cover.

**The honest pitch:** Aelu is Anki for people who want to study Chinese, not maintain a flashcard system. If you enjoy the meta-game of optimizing Anki, you will probably stay with Anki. If you want to sit down and practice Chinese without thinking about deck management, Aelu is worth $14.99/month.

---

### "Why Aelu over Duolingo?"

**Easy wins for us:**
- 44 drill types vs. ~4
- Actual tone instruction and grading vs. effectively none
- Graded reader with cleanup loop vs. sentence-level translation exercises
- Honest metrics vs. gamification theater
- Designed for serious adult learners vs. designed for engagement metrics

**But be honest about Duolingo's strengths:**
- Duolingo's gamification genuinely works for building daily habits. Some people need the streak and the owl. That is not a weakness; it is a different design philosophy.
- Duolingo is free for most practical purposes. Our free tier covers HSK 1-2; their free tier covers everything (with ads and hearts).
- Duolingo has a native mobile app that is genuinely excellent. We have a web app.
- Duolingo's brand recognition means "learning Chinese" and "Duolingo" are synonymous for many people.
- Duolingo's community (subreddit, social features) creates accountability we cannot match.

**The pitch:** If you want to actually learn Chinese -- read it, understand it spoken at you, pronounce tones correctly, pass HSK exams -- Duolingo's Chinese course will not get you there. It is a starting point at best. Aelu is designed to be the tool that actually works.

---

### "Why Aelu over HelloChinese?"

This is our closest competition for structured Chinese learners. Both offer structured courses, drills, reading, listening, and speaking practice.

**Where we win:**
- SRS quality: Adaptive spaced repetition with confidence-weighted scheduling vs. basic interval scheduling. Our scheduling is measurably more efficient.
- Drill variety: 27 types vs. ~8. More cognitive skills targeted.
- Cleanup loop: Our reading feeds directly into SRS. Theirs does not.
- Multi-skill diagnostics: Per-skill tracking with HSK projection. They lack this.
- HSK range: We cover 1-6 with 7-9 in preparation. They taper after HSK 4.
- No gamification: Honest metrics only. No hearts, no streaks, no XP inflation.

**Where they win:**
- Beginner experience: Their pinyin introduction and early-stage progression are better than ours.
- Mobile app: Native iOS/Android app vs. our mobile web.
- Content volume: 1,000+ graded stories, 2,000+ native speaker videos vs. our smaller content set.
- HSK 3.0 readiness: They claim to be the first app built on the new standard.
- Handwriting: They include stroke order practice. We do not.

**The honest answer:** For HSK 1-2 beginners on a phone, HelloChinese is probably the better starting point today. For HSK 3+ learners who want sophisticated scheduling, multi-skill diagnostics, and the cleanup loop, Aelu offers more. We need to close the content gap.

---

### "Why Aelu over Skritter?"

This is not really a versus. Skritter does handwriting. We do not. We do reading, listening, speaking, SRS, and 44 drill types. They do not (beyond character-level).

**If someone can only pick one:** It depends entirely on whether they need to write Chinese by hand. If they are preparing for a written HSK exam or studying in a Chinese university, they need Skritter (or something like it). If they want to read, listen, speak, and pass the computerized HSK, they need Aelu.

**The smart answer:** Use both. Skritter for writing, Aelu for everything else.

---

## Competitive Threats

### Short-term (6 months)

1. **HelloChinese improves their SRS.** They already have the content, the mobile app, the brand, and the user base. If they implement real FSRS-level scheduling and add a cleanup loop, they would cover much of our differentiation while having 10x our content. This is our most dangerous near-term threat.

2. **Hack Chinese adds reading.** They already have the vocabulary database and the SRS engine. Adding a graded reader with integration would directly challenge our cleanup loop USP.

3. **Duolingo invests in Chinese.** If Duolingo ports their Stories feature, grammar exercises, and CEFR tracking to the Chinese course (as they have for European languages), their Chinese offering would improve dramatically overnight. They have the engineering and user base to move fast.

4. **AI-native tools gain traction.** Apps like Novli (snap-to-flashcard with AI), Langua (AI conversation partners), and ChatGPT itself for conversation practice are all nibbling at edges of the market. None are complete learning systems yet, but they are improving rapidly.

### Medium-term (1-2 years)

1. **ChatGPT / Claude / Gemini as conversation partners.** As voice mode improves, LLMs become free infinite tutors for conversation practice. They cannot (yet) do structured SRS or track long-term progress, but they can provide something we do not: open-ended conversation with tone feedback.

2. **Apple/Google translate improves.** As real-time translation gets better, some learners will question why they are memorizing vocabulary when their phone can translate instantly. This affects motivation across the entire category.

3. **Consolidation.** Larger companies may acquire niche Chinese tools. If Duolingo acquired Skritter or Du Chinese, the combined product would be formidable.

4. **HSK 3.0 disruption.** The new HSK standard (expected enforcement from July 2026) reshuffles curriculum for every app. Whoever adapts fastest wins. HelloChinese claims to be first; we need to keep pace.

5. **A well-funded AI-native Chinese app launches.** Think: a team with real NLP expertise builds a Chinese learning system with AI conversation, real-time tone grading via neural network, adaptive reading with comprehension questions generated on the fly, and SRS underneath. This product does not exist yet but could within 18 months.

### Long-term (2-5 years)

1. **Real-time AI tutoring replaces structured apps.** If voice-mode LLMs can reliably grade tones, adjust difficulty, remember what you have learned, and provide comprehensible input -- all in conversation -- the "app with drills" model becomes less compelling. Our SRS and diagnostic infrastructure would still have value, but the drill-centric UX might need to evolve.

2. **AR/immersion tools.** Wearable translation and context-aware language tools could change how people interact with Chinese in the real world. The study session as a separate activity might give way to continuous ambient learning.

3. **Market bifurcation.** Casual learners fully absorbed by Duolingo + AI chatbots. Serious learners use specialized tools like Aelu. The middle market (HelloChinese, LingoDeer) gets squeezed.

4. **Aelu needs to go where the learner goes.** This means: native mobile apps, wearable integration, ambient learning modes. Web-first is defensible now but limiting in 3-5 years.

---

## Where We Lose (Honest Assessment)

### When someone should use Duolingo instead
- They are a complete beginner who has never studied any language and needs gamification to build a daily habit.
- They want to study on their phone during 5-minute commute breaks and need a native app.
- They are casually curious about Chinese (not committed) and do not want to pay.
- They are a child or teenager who responds to game mechanics.

### When someone should use Anki instead
- They study multiple languages and need one SRS system for everything.
- They want specialized vocabulary (medicine, law, dialect) that we do not cover.
- They have invested years in Chinese Anki decks and the migration cost is too high.
- They enjoy customization and system-building as part of their study practice.
- They cannot pay $14.99/month and have time to invest in setup.

### When someone should use HelloChinese instead
- They are an absolute beginner on a phone who needs excellent pinyin instruction.
- They want a native mobile app with a polished touch interface.
- They want handwriting practice integrated with their lessons.
- They are at HSK 1-2 and want the largest possible content library for that level.

### When someone should use a tutor instead
- They need conversation practice. We do not provide conversation.
- They need cultural context and pragmatic instruction beyond textbook phrases.
- They need error correction on free-form speech or writing.
- They learn best through interpersonal interaction, not solo study.

### When someone should use immersion instead
- They are at HSK 4+ and need massive input volume. Watching Chinese TV, reading Chinese internet, and talking to Chinese people will outpace any app at that level.
- They live in or can travel to a Chinese-speaking environment.
- They have the basics down and need real-world exposure to solidify and expand.

---

## Competitive Response Playbook

### If Hack Chinese adds reading features
**Threat level:** High. They have the vocabulary database and SRS to make it work.
**Response:** Emphasize our drill variety (27 types) and multi-skill diagnostics. Reading + flashcards is not the same as reading + 44 drill types + tone grading + listening + diagnostics. Accelerate our content pipeline to close the vocabulary gap.

### If Duolingo improves their Chinese course
**Threat level:** Medium. Duolingo improving Chinese would mostly affect the casual beginner market, which is not our core target. But it could reduce the pipeline of "people who outgrow Duolingo and look for something better."
**Response:** Position explicitly for the post-Duolingo learner. Marketing message: "Ready for real Chinese? You've finished Duolingo. Now try Aelu." Focus on what they still will not do: real SRS, tone grading, cleanup loop, honest metrics.

### If a new AI-native Chinese app launches
**Threat level:** Medium-high, depending on execution.
**Response:** Emphasize deterministic, data-grounded approach. "We don't hallucinate your progress." AI-native tools will have accuracy problems with tone grading, grammar correction, and progress tracking. Our deterministic approach means every metric is verifiable. Position AI as a complement (conversation practice) and us as the structured foundation.

### If Anki gets a major UX overhaul
**Threat level:** Low-medium. Anki improving UX would make it more accessible but would not add Chinese-specific features (reading, tone grading, HSK curriculum).
**Response:** No panic. Our differentiation is not "we're easier Anki" -- it's "we're a Chinese learning system." Better Anki UX does not give Anki a cleanup loop, tone grading, or multi-skill diagnostics. Continue emphasizing Chinese-specific features.

### If HelloChinese adds real SRS
**Threat level:** Very high. This is the scenario that keeps us up at night.
**Response:** Emphasize transparency and metrics honesty (no gamification, no praise inflation). Emphasize the cleanup loop specifically (reading-to-SRS pipeline). Emphasize per-skill diagnostics and HSK projection. Accelerate content development to close the gap. Consider adding features they lack: advanced drill types, detailed session analytics, data export.

---

## Win/Loss Analysis Framework

### When a user signs up, ask:
1. What were you using before Aelu?
2. What made you look for something new?
3. What is the one thing you need most from a Chinese learning tool?
4. How would you describe your current level?
5. Are you preparing for HSK? If so, which level?

### When a user cancels, ask:
1. What are you switching to? (Or are you stopping Chinese study entirely?)
2. What was the main thing that did not work for you?
3. Was there a specific feature you wanted that we did not have?
4. Would anything bring you back?
5. How would you rate the value for $14.99/month? (1-10)

### When a user stays past 3 months, ask:
1. What is the one feature you use most?
2. What other Chinese tools do you use alongside Aelu?
3. What is the one thing you wish we did better?
4. Would you recommend Aelu to a friend learning Chinese? Why or why not?

### How to use the data:
- Track win/loss by previous tool (e.g., "40% of signups come from Anki, 25% from Duolingo, 15% from HelloChinese").
- Track cancellation reasons by category (content depth, missing features, price, UX, switched to competitor).
- Track NPS by user segment (beginner vs. intermediate, HSK prepper vs. casual).
- Review quarterly. Identify patterns. Feed into product roadmap.
- If 30%+ of cancellations cite the same reason, that is a product priority, not a marketing problem.

### Key metrics to track:
- **Conversion rate by source:** Which competitors' users convert best?
- **Retention by source:** Which competitors' users retain best after switching?
- **Feature usage by source:** Do Anki converts use SRS features more? Do Duolingo converts use the graded reader more?
- **Cancellation reason distribution:** What percentage is content depth vs. price vs. UX vs. feature gaps?
- **Complementary usage:** What percentage of active users also use Anki, Pleco, HelloChinese, etc.? What does this tell us about gaps?

---

*This document should be updated quarterly as competitor features and pricing change. Research dates and sources should be verified before any external use.*
