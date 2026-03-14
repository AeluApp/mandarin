# Evidence-Based Language Learning Pedagogy
## Actionable Principles for a Mandarin Learning App

Research synthesis from SLA (Second Language Acquisition) literature.
Compiled 2026-03-09.

---

## 1. Vocabulary Teaching

### 1a. Nation's Four Strands: Equal Time Across Four Activities

Paul Nation's framework says a balanced program distributes time roughly equally across:

1. **Meaning-focused input** — Reading/listening to material where 95-98% of words are already known. The learner acquires vocabulary incidentally from context.
2. **Meaning-focused output** — Speaking/writing where the learner must use target vocabulary to communicate real meaning.
3. **Language-focused learning** — Deliberate study of word form, meaning, collocations, and usage patterns.
4. **Fluency development** — Practicing *already-known* material at speed, building automaticity.

**What the app should do:**
- Track time spent in each strand. If a learner only does flashcard drills (strand 3), the app should nudge toward reading passages (strand 1) or sentence production tasks (strand 2).
- Fluency drills should use *mastered* items, not new ones. The goal is speed and effortlessness, not learning. Time-pressured recognition drills on well-known words serve this purpose.
- Graded reading passages should be calibrated so the learner knows 95%+ of the vocabulary. Unknown words should be glossed, not left as obstacles.

### 1b. Involvement Load Hypothesis (Laufer & Hulstijn)

Vocabulary retention correlates with the *involvement load* of the task, measured across three factors:

| Factor | Definition | Low | High |
|--------|-----------|-----|------|
| **Need** | Is there a genuine reason to use/understand the word? | Teacher assigns it | Learner encounters it while trying to communicate |
| **Search** | Does the learner have to find the meaning or form? | Meaning is given | Learner must look it up or figure it out |
| **Evaluation** | Does the learner have to decide how the word fits a context? | No decision needed | Must choose between words or construct a sentence |

Higher involvement load = better retention. Systematic reviews confirm this across dozens of studies, though the effect is strongest when all three factors are present simultaneously.

**What the app should do:**
- Avoid pure "show definition, press next" presentation. Even initial teaching should require some search or evaluation.
- Composition tasks (write a sentence using X) beat fill-in-the-blank, which beats reading-with-gloss. The app should escalate through these stages.
- Create genuine *need* by embedding vocabulary in scenarios the learner cares about (ordering food they actually want to order, describing their actual job).
- When a word appears in a graded reader, let the learner tap to reveal meaning (search) rather than pre-glossing everything.

### 1c. The Generation Effect

Information actively generated is remembered ~40% better than information passively read — even when the generated answer is wrong, as long as corrective feedback follows.

**What the app should do:**
- Before showing a new word's meaning, ask the learner to guess. "You've seen 电 (electricity) and 脑 (brain). What might 电脑 mean?" The guess activates related knowledge and creates a "slot" that makes the correct answer stick.
- For review, always require production before showing the answer. Even a failed attempt strengthens the eventual memory trace.
- Wrong answers are not wasted time — they are preparation for learning. The app should not penalize wrong guesses during initial learning phases.

### 1d. Receptive-to-Productive Progression

Learners know words receptively (can recognize) before productively (can use). This is not a binary; it is a continuum:

1. No knowledge
2. Recognize the form as familiar
3. Can select correct meaning from options
4. Can recall meaning when seeing the form
5. Can recall the form when given the meaning
6. Can use the word in a constrained context (fill-in-blank)
7. Can use the word in free production (speaking/writing)
8. Can use the word appropriately across registers and contexts

**What the app should do:**
- Track each word's position on this continuum separately. A word "known" at level 4 is not "known" at level 7.
- Drill types should escalate: recognition → recall → constrained production → free production. Do not skip stages, but do not linger at recognition when the learner is ready for production.
- Productive tasks (sentence writing, cloze with typing, translation from L1) contribute significantly more to moving words up the continuum than receptive tasks (multiple choice, matching).

### 1e. Mandarin-Specific Vocabulary Considerations

- **Characters are not words.** A character (字) is a morpheme; a word (词) is often two characters. The app should teach words in context, not isolated characters, while still building character awareness (radical recognition, component analysis).
- **Tone is part of the word.** A word "known" without correct tone is not known. Tone should be tested from the beginning, not added later.
- **Measure words must be learned with nouns.** Present 一杯咖啡 (a cup of coffee) rather than 咖啡 alone and 杯 alone. The classifier is part of the word's "neighborhood."
- **Homophones are pervasive.** The app must disambiguate via characters and context, not pinyin alone. Drills that present only pinyin are dangerously ambiguous.

---

## 2. Grammar Instruction

### 2a. DeKeyser's Skill Acquisition Theory

Language learning follows the same trajectory as any complex skill:

1. **Declarative stage** — Learn the rule explicitly ("把 moves the object before the verb when the action changes the object's state")
2. **Procedural stage** — Practice applying the rule in controlled exercises until it becomes a ready-made chunk rather than assembled from pieces each time
3. **Automatization stage** — Use the structure fluently in real communication without conscious thought

The transition from declarative to procedural requires *massive amounts of practice with feedback*. The transition to automatization requires *speed pressure and communicative necessity*.

**What the app should do:**
- Present grammar rules explicitly and concisely. Adult learners benefit from knowing the rule before practicing it (unlike children, who can acquire implicitly from input alone).
- Provide graduated practice: first controlled (fill the blank with 了/过/着), then semi-controlled (rewrite this sentence using 把), then free (describe what you did yesterday).
- Add time pressure only *after* accuracy is established. Timed drills on grammar the learner still gets wrong are counterproductive — they proceduralize errors.
- Track accuracy at each stage separately. 80%+ accuracy in controlled practice before advancing to semi-controlled.

### 2b. Schmidt's Noticing Hypothesis

Acquisition requires the learner to *consciously notice* a feature in input. Noticing the gap between their own production and target-language norms drives restructuring of their interlanguage.

**What the app should do:**
- Use input enhancement: bold, color, or otherwise highlight target structures in reading passages. If the lesson is about 把 constructions, make every 把 visually salient in the text.
- After a learner produces an error, show the correct form side-by-side with their attempt. "You wrote: 我吃了饭把. Target: 我把饭吃了." The contrastive display forces noticing.
- Periodically present minimal pairs of sentences that differ only in the target structure: "我吃了三碗饭" vs "我吃过三碗饭." Ask the learner to explain the difference. This is metalinguistic noticing.

### 2c. Explicit vs. Implicit Instruction: The Current Consensus

The Norris & Ortega (2000) meta-analysis and subsequent updates consistently show:

- **Explicit instruction produces larger immediate gains** than implicit instruction for adult learners (d = 0.81 vs d = 0.70).
- **Implicit learning effects are better maintained over time** — explicit knowledge decays faster unless proceduralized through practice.
- **The best approach combines both**: explicit rule presentation followed by meaningful communicative practice (implicit reinforcement).
- **Explicit instruction particularly benefits structures that are non-salient** — features the learner would not notice on their own (e.g., the distinction between 了 as perfective aspect vs. 了 as change of state).

**What the app should do:**
- Lead with a brief, clear rule explanation for each grammar point. Keep it under 3 sentences. Use the learner's L1 for the explanation when disambiguation requires it.
- Follow immediately with practice that requires applying the rule in meaningful contexts, not pattern drills.
- Revisit the same structure in reading passages weeks later, without re-explaining. The implicit exposure reinforces what was explicitly learned.
- For highly salient, simple patterns (e.g., 不/没 negation), less explanation is needed. For opaque patterns (e.g., complement of degree 得), more explicit instruction is needed.

### 2d. Interleaving Grammar Practice

Nakata & Suzuki (2019) demonstrated that interleaved grammar practice (mixing different structures in one session) produces better long-term retention than blocked practice (practicing one structure at a time), despite causing more errors during training.

**What the app should do:**
- After initial blocked introduction of a grammar point, mix it with previously learned structures in subsequent sessions.
- A drill session should intermix 了/过/着 rather than doing 20 了 items, then 20 过 items. This forces discrimination between similar forms.
- Exception: for initial learning of pronunciation/tones, blocked practice may be superior. Start with blocked tone pairs, then interleave.
- Use a "blocked-to-interleaved" transition: introduce new grammar in a focused block, then immediately begin mixing it into the general rotation.

---

## 3. Corrective Feedback

### 3a. Meta-Analytic Findings

Li (2010) meta-analyzed 33 studies on corrective feedback in SLA:

- Corrective feedback has a **medium overall effect** on learning, and the effect persists over time.
- **Explicit feedback** (direct correction + metalinguistic explanation) produces larger *immediate* gains.
- **Implicit feedback** (recasts — repeating the utterance correctly) produces gains that are *better maintained* over time.
- The optimal approach depends on the target structure: simple, salient features benefit from implicit recasts; complex, opaque features benefit from explicit correction.

### 3b. Practical Feedback Principles

**What the app should do:**
- **Immediate feedback on vocabulary:** Show the correct answer immediately after an error. Delayed feedback on vocabulary items does not help; it just causes confusion.
- **Corrective recasts for grammar:** When the learner produces "我昨天去超市了买东西" (incorrect word order), show the correct version first: "我昨天去超市买了东西." Then briefly explain *why* ("了 follows the verb, not 超市"). This is explicit correction with a recast.
- **Don't just mark wrong — show the gap.** Display the learner's attempt and the target side by side. Highlight the specific point of divergence. This leverages Schmidt's noticing hypothesis.
- **Grade the feedback by proficiency:**
  - Beginner: Full explicit correction + L1 explanation + example
  - Intermediate: Recast + brief note ("Word order: 把 + object + verb")
  - Advanced: Recast only, or a prompt to self-correct ("Something's off with the complement — try again")
- **Never give feedback on everything at once.** If a sentence has a tone error, a grammar error, and an awkward word choice, correct the grammar error. Cognitive overload from multi-point correction causes the learner to remember none of it.
- **Praise accuracy on previously difficult items.** If the learner has gotten 把 wrong 5 times and finally gets it right, a brief acknowledgment ("把 structure: correct") is warranted. Not effusive praise — just confirmation.

---

## 4. Retrieval Practice and Spaced Repetition

### 4a. The Testing Effect (Roediger & Karpicke)

Testing (attempting to retrieve from memory) strengthens memory more than restudying — even when the retrieval attempt fails. The effect is:
- Larger for *delayed* tests (days/weeks later) than immediate tests
- Stronger with more retrieval attempts
- Optimal when alternating study and test trials

**What the app should do:**
- Default to testing, not re-presenting. The learner should *always* attempt recall before seeing the answer.
- Never let the learner passively flip through items. Even a 1-second generation attempt before reveal activates the testing effect.
- Increase retrieval difficulty over time: multiple choice → typed recall → free production. Harder retrieval = stronger memory trace (up to a point).

### 4b. Desirable Difficulties (Bjork)

Four evidence-based "desirable difficulties" that slow initial learning but improve long-term retention:

1. **Spacing** — Distribute practice over time rather than massing it. Review a word on day 1, day 3, day 7, day 14...
2. **Interleaving** — Mix different item types and categories within a session.
3. **Retrieval practice** — Test rather than restudy.
4. **Generation** — Produce answers rather than recognize them.

Bjork distinguishes *storage strength* (how deeply embedded) from *retrieval strength* (how easily accessed right now). Desirable difficulties reduce retrieval strength in the short term but build storage strength for the long term.

**What the app should do:**
- Space reviews using expanding intervals. But do NOT use a single fixed algorithm — adjust based on difficulty, error history, and item type (tones need more repetition than meaning).
- When the learner gets an item right easily, *increase* the interval aggressively. When they struggle, *decrease* it modestly. Asymmetric scheduling.
- Make the app slightly harder than the learner expects. If they're getting 95%+ right, the difficulty is too low. Target 80-85% accuracy — the zone where desirable difficulty operates.
- Never let the learner choose "easy/hard" self-ratings as the primary scheduling input. Learners systematically overestimate their knowledge. Use objective accuracy and response time.

### 4c. Productive Failure (Kapur)

Attempting to solve a problem *before* receiving instruction can prepare the learner to learn better from subsequent instruction. The mechanism: the failed attempt activates prior knowledge and highlights gaps, making the instruction more meaningful.

Evidence is strongest for STEM and older learners (secondary school+). Direct evidence in language learning is limited, but the principle aligns with the generation effect and Schmidt's noticing hypothesis.

**What the app should do:**
- Before teaching a new grammar point, present a sentence that uses it and ask the learner to figure out the meaning. Their attempt (even if wrong) primes them for the explanation.
- Before teaching a new word, present it in a sentence and ask the learner to guess its meaning from context + character components. Then provide the actual meaning.
- Frame these as "exploration," not "tests." The learner should understand that wrong guesses are part of the process, not failures.

---

## 5. From Recognition to Active Use

### 5a. Swain's Output Hypothesis

Comprehensible input alone is not enough. Learners who receive years of rich input (e.g., French immersion students in Canada) develop near-native comprehension but lag significantly in production. Output serves three critical functions:

1. **Noticing function** — Producing language forces the learner to notice gaps they would not notice while comprehending ("I don't know how to say this").
2. **Hypothesis testing** — The learner tries a form and observes whether it communicates successfully.
3. **Metalinguistic function** — Producing language requires conscious reflection on form, not just meaning.

**What the app should do:**
- Every session should include production tasks, not just recognition. Even 5 minutes of sentence construction per session is more valuable for production than 20 minutes of reading.
- "Pushed output" tasks: Give the learner a communicative goal that requires a structure they're learning. "Describe what happened at work today using 了." Do not provide a model sentence — force them to construct one.
- When the learner produces output with errors, the error itself is valuable. It revealed a gap. The feedback loop (produce → notice gap → receive correction → try again) is the core acquisition cycle for production skills.
- Scaffold production difficulty:
  1. Sentence unscrambling (arrange given words)
  2. Cloze completion (fill in the missing word)
  3. Guided translation (translate with vocabulary hints)
  4. Free translation (translate without hints)
  5. Free production (express this idea in Chinese)

### 5b. Transfer-Appropriate Processing

Memory is strongest when the conditions at retrieval match the conditions at encoding. Learning to recognize 谢谢 on a flashcard does not automatically enable producing it in conversation.

**What the app should do:**
- If the goal is speaking, test via production (type the pinyin, record audio). If the goal is reading, test via character recognition. Match the drill to the target skill.
- Include audio-to-meaning drills (hear Chinese → select meaning) alongside text-to-meaning drills (see characters → select meaning). These are different skills.
- For words the learner needs to produce in speech, include speaking drills where they must produce the word from an L1 prompt or a picture prompt — not from seeing the characters.

---

## 6. Balancing Explicit Explanation vs. Implicit Acquisition

### 6a. The Current Consensus

The Krashen vs. explicit instruction debate is largely settled for adult learners:

- **Krashen was right** that massive comprehensible input is essential and that acquisition can occur without explicit instruction.
- **Krashen was wrong** that explicit instruction has no lasting effect. Meta-analyses consistently show explicit instruction accelerates acquisition, especially for non-salient features.
- **The synthesis**: Explicit instruction provides the declarative knowledge that makes input more noticeable (Schmidt). Implicit exposure then procedural-izes and automatizes that knowledge (DeKeyser). Neither alone is sufficient.

### 6b. When to Explain vs. When to Expose

| Feature Type | Strategy | Example |
|-------------|----------|---------|
| Simple, salient, regular | Light explanation + heavy exposure | 不 vs 没 (basic negation) |
| Complex, opaque, irregular | Heavy explanation + graduated practice | 把 construction, 得 complement |
| Formulaic / chunk-based | Exposure as unanalyzed chunks first, explain later | 没关系, 不好意思, 对不起 |
| Sociolinguistic / register | Explain the social dimension explicitly | 你/您, formal vs casual 谢谢 vs 感谢 |

### 6c. The Role of L1 in Explanation

For adult learners, using the L1 (English) for grammar explanations is more efficient than target-language-only instruction, especially for abstract or contrastive concepts. The goal is not to avoid English — it is to minimize English in *practice* while using it strategically in *explanation*.

**What the app should do:**
- Grammar explanations: Use English. Keep them concise.
- Grammar practice: All in Chinese. Force processing in L2.
- Vocabulary definitions: Use L1 gloss for initial learning, but transition to L2 definitions and example sentences as proficiency grows.
- Error explanations: Use English for beginners, transition to brief Chinese metalanguage for intermediates (e.g., "语序不对" — "word order incorrect").

---

## 7. Synthesis: The Core Cycle

Based on the research above, the optimal learning cycle for each item (word or grammar point) is:

```
1. ENCOUNTER — Meet the item in meaningful context (reading, listening)
2. NOTICE — Attention is drawn to the item (enhancement, generation attempt)
3. RETRIEVE — Attempt to recall before seeing the answer (testing effect)
4. PRODUCE — Use the item in constrained output (cloze, translation)
5. ELABORATE — Use the item in free production (sentence writing, speaking)
6. SPACE — Re-encounter across expanding intervals
7. INTERLEAVE — Mix with other items to force discrimination
8. AUTOMATE — Use under time pressure with known material (fluency strand)
```

Each item should progress through these stages. The app's job is to move items through this pipeline efficiently, spending more time at the stages where the learner struggles, and not allowing items to stagnate at recognition when they should be progressing toward production.

---

## 8. Anti-Patterns: What the Research Says NOT to Do

1. **Do not present word lists for passive study.** Involvement load is near zero. Retention is terrible.
2. **Do not test only recognition (multiple choice) and call it "known."** Recognition and production are different skills with different neural substrates.
3. **Do not mass practice in single sessions.** Three 10-minute sessions across three days beats one 30-minute session every time.
4. **Do not let learners self-assess difficulty.** They systematically overestimate their knowledge (the fluency illusion). Use objective performance data.
5. **Do not correct every error simultaneously.** Focus on one error type per feedback instance. Prioritize errors that impede communication.
6. **Do not skip explicit instruction for adult learners** in the name of "natural acquisition." Adults are not children. They have metalinguistic awareness and benefit from using it.
7. **Do not teach tones separately from words.** Tones should be integral to every vocabulary encounter, not a separate "pronunciation" module.
8. **Do not stay at i+1 forever.** Some exposure to i+2 or i+3 material (where the learner struggles) creates productive difficulty that strengthens learning, as long as it does not become frustrating.
9. **Do not block practice indefinitely.** Transition from blocked to interleaved practice as soon as initial accuracy is established.
10. **Do not rely on input alone.** Without pushed output, learners develop comprehension without production ability. Every session needs production.

---

## Sources

- [Nation's Four Strands framework (Victoria University)](https://www.victoria.ac.nz/__data/assets/pdf_file/0019/1626121/2007-Four-strands.pdf)
- [Nation's Four Strands and Digital Language Pedagogy](https://cdn.prod.website-files.com/5fa27c3574b213fae018d63e/63c4bc9059c35af7cb43db69_Nation's%20Four%20Strands%20and%20Digital%20Language%20Pedagogy%20with%20ZenGengo.pdf)
- [Involvement Load Hypothesis systematic review (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9598591/)
- [Involvement Load Hypothesis Plus (Cambridge)](https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/involvement-load-hypothesis-plus/5C5984B326F37FBF3A3DDA3C0EB2996C)
- [DeKeyser & Suzuki (2025) Skill Acquisition Theory, Routledge](https://www.taylorfrancis.com/chapters/edit/10.4324/9781003491118-7/skill-acquisition-theory-robert-dekeyser-yuichi-suzuki)
- [Swain's Output Hypothesis review](https://www.hpu.edu/research-publications/tesol-working-papers/2017/2017-new-with-metadata/06pannellpartschfuller_output.pdf)
- [Schmidt's Noticing Hypothesis (Wikipedia)](https://en.wikipedia.org/wiki/Noticing_hypothesis)
- [Schmidt (2010) Attention, Awareness, Individual Differences](https://nflrc.hawaii.edu/PDFs/SCHMIDT%20Attention,%20awareness,%20and%20individual%20differences.pdf)
- [Roediger & Karpicke (2006) The Power of Testing Memory](http://psychnet.wustl.edu/memory/wp-content/uploads/2018/04/Roediger-Karpicke-2006_PPS.pdf)
- [Desirable Difficulties (Bjork, Psychological Science)](https://www.psychologicalscience.org/observer/desirable-difficulties)
- [Li (2010) Corrective Feedback Meta-Analysis](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-9922.2010.00561.x)
- [Corrective Feedback: technique and timing optimization](https://link.springer.com/article/10.1186/s40862-020-00097-9)
- [Nakata & Suzuki (2019) Interleaving grammar practice](https://onlinelibrary.wiley.com/doi/abs/10.1111/modl.12581)
- [Interleaving: blocked-to-interleaved transition for novices (2025)](https://onlinelibrary.wiley.com/doi/10.1111/lang.12659)
- [Productive Failure (Kapur) — core mechanisms](https://www.manukapur.com/productive-failure/)
- [Productive Failure meta-analysis (Sinha & Kapur 2021)](https://journals.sagepub.com/doi/10.3102/00346543211019105)
- [Norris & Ortega revisited: explicit vs implicit instruction](https://benjamins.com/catalog/sibil.48.18goo)
- [Beyond Comprehensible Input: neuro-ecological critique of Krashen (2025)](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1636777/full)
- [Was Krashen Right? Forty Years Later (Lichtman & VanPatten)](https://fluencyfast.com/wp-content/uploads/LichtmanVanPatten2021aKrashen.pdf)
- [Generation Effect (Structural Learning)](https://www.structural-learning.com/post/generation-effect-active-learning)
- [Receptive to Productive vocabulary (Teng & Xu 2025)](https://journals.sagepub.com/doi/abs/10.1177/13621688221077028)
- [Mandarin tone perception research (2024)](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1403816/full)
- [Retrieval practice vs elaborative restudy for vocabulary](https://www.sciencedirect.com/science/article/abs/pii/S2211368114000473)
