# Aelu Comedy QA System

Sources: Kalan (*Joke Farming*), Izzard, editorial practice.

## 1. Humor Doctrine

**Core rule:** If it is funny but muddles meaning, it fails. If it is clear but dead, it underperforms. If it is both clear and quietly delightful, it passes.

**Three simultaneous requirements:**
- Be funny enough to create delight
- Be clear enough to teach
- Be human enough not to feel machine-inserted

**Tone:** gentle, humane, lightly observant, emotionally safe, restorative, never smug.

**Style influences:**
- Eddie Izzard — intelligence without coldness, whimsy anchored by confidence, comic narration as companionship, humanity over snark.
- Elliott Kalan — jokes as process discipline, not inspiration. Comedy is producible on demand through craft, not dependent on gut instinct. "Joke farming, not joke hunting."

**Deepest principle:** Comedy is compressed sociology. It lives in the gap between what people feel and what they can safely say. A joke is a "time-released unit of information" (Kalan) — plant ideas in the right order, leave out just enough for the audience to fill in, and that filling-in IS the joke.

## 2. Joke Components (Kalan Framework)

Every joke has six elements:

1. **Voice** — who is telling this? What sensibility, point of view, frame of preference? For Aelu: what is Aelu's voice here? What phrases, rhythms, emotional temperature are characteristic? What would Aelu never say?
2. **Premise** — what is the joke trying to say, and what small story carries that intention? No premise, no joke.
3. **Structure** — how are the elements arranged? Setup plants information; punchline changes understanding. "Pull the two livewires close enough that the electricity arcs between them."
4. **Tone** — the emotional temperature. How sincere or ironic? Is this meant as "this is how I feel" or "this is just a funny idea"?
5. **Wording/Detailing** — precision. Each element specific, clear, tuned. Cut setup words. Replace generalities with one concrete detail. Prefer spoken rhythm over written polish.
6. **Audience** — the most important element. The joke exists when the audience understands it. For Aelu, audience has two layers: learner-as-learner and learner-as-comedy-audience.

## 3. Allowed Mechanisms

One primary mechanism per scene. Choose one:

- understatement
- over-formality
- euphemism
- status drop
- misplaced confidence
- polite aggression
- excessive earnestness
- literal-mindedness
- bureaucratic laundering of nonsense
- self-protective vagueness
- reversal
- politeness masking irritation

**Comic sources for Aelu:** real social behavior, language-learning tension, status mismatch, gap between what someone says and what they mean.

## 4. Where AI Fails at Comedy

1. **Imitates joke texture instead of comic truth.** Generates "quirky" wording with no observed human behavior underneath.
2. **Over-explains.** Comedy depends on omission, implication, letting the audience do one step of work. Kalan: "You're literally understanding what's not being said and filling it in, so you get it as a joke."
3. **Writes completed thoughts, not lived speech.** Dialogue comes out too polished, too essay-like, too correct.
4. **Confuses absurdity with humor.** Randomness is easy. Recognition is harder.
5. **Cannot naturally feel social stakes.** Embarrassment, face-saving, status defense, vanity, mild self-deception — models name these but don't organically feel them in scene construction.
6. **Optimizes legibility over rhythm.** Sensible for most tasks, deadly for comedy.

## 5. Banned Habits

- over-explaining the joke
- "suddenly I realized" moral endings
- polished mini-essays in dialogue
- whimsical nonsense without behavioral grounding
- punchlines depending on weirdness alone
- too many adjectives
- too many conjunctions
- translationese / over-formal support language
- emotional over-signaling
- all-purpose wistfulness
- comedy that sounds written rather than spoken
- "content writer funny" (cute but inert)
- broad sitcom mugging
- sarcasm that makes the learner feel excluded
- humiliating a character instead of observing them
- cartoonishly wrong distractors
- punchlines that require long setup

### Common AI Mistakes → Fixes

| Mistake | Fix |
|---|---|
| Joke-shaped sentence, no premise | Build a scenario first |
| Clever line, no human behavior | Name the recognizable behavior |
| Too many mechanisms | Choose one engine only |
| Over-explained | Remove one sentence, let inference carry |
| Too polished | Make speech more lived-in, less complete |
| Distractors too absurd | Make wrong answers plausible but shallow, tone-deaf, too formal, too literal, or slightly self-serving |

## 6. Generation Process

Order matters. Do not simplify early — it makes scenes flat and juvenile.

### Two-stage pipeline (Kalan: seeds → jokes)

**Stage A: Joke seeds** (raw observations, not finished jokes)
- "person uses formal language to hide annoyance"
- "learner overanswers because nervous"
- "coworker fishing for praise"
- "small inconvenience described like national crisis"

**Stage B: Joke construction** — turn seeds into scenes using the steps below.

### Step 1: Generate the boring truth first

Before writing anything funny, produce:
- the plain comic point
- the emotional/social dynamic
- who is protecting status
- what is being implied rather than said
- what must be left unsaid for the learner to infer

Example:
```
Comic truth: The speaker wants to sound relaxed, but is obviously fishing for praise.
Recognizable human behavior: Indirect self-promotion disguised as casual conversation.
Social tension: The listener can tell, but politely plays along.
Aelu tone: warm, lightly amused, no judgment.
Learning objective: Practice modesty language / implied meaning / soft disagreement.
Premise/scenario: A colleague shows you photos of their weekend calligraphy.
Primary comic mechanism: misplaced confidence.
What must be left unsaid: That the calligraphy is clearly bad.
```

This prevents "ornamental funny."

### Step 2: Choose one named comic mechanism

### Step 3: Build the scene in natural adult logic

### Step 4: Generate social subtext explicitly

Output:
- Literal meaning
- Intended meaning
- What the listener infers
- Why this is funny
- Why a real person would talk this way

This forces jokes around inference instead of surface decoration.

### Step 5: Write three versions at different humor intensity

- Level 1: light smile
- Level 2: clear comic beat
- Level 3: more playful / memorable

Choose the lightest version that still feels alive. Aelu usually wants underplayed humor, not performance comedy.

### Step 6: Simplify language while preserving social logic

### Step 7: Compress

### Step 8: Self-audit

- Is this something a real person might plausibly say?
- Is the wrong answer plausibly wrong, or cartoonishly wrong?
- Does the humor come from recognizable behavior rather than randomness?
- Is anyone speaking like a model answer key instead of a human?
- Is the scene funny because of social reality, or because the wording is merely cute?
- What is the joke point?
- What inferential gap is the learner filling in?
- Which words can be cut?
- Does this preserve comprehension at this level?

## 7. Evaluation Rubric

### Two-axis scoring

| | High learning clarity | Low learning clarity |
|---|---|---|
| **High comic life** | Keep | Simplify |
| **Low comic life** | Enrich | Scrap |

### Nine-dimension rubric (3 points each, 27 max)

**A. Comic truth** — 0: no clear point / 1: vague / 2: clear but familiar / 3: clear, specific, socially sharp

**B. Premise strength** — 0: no real scenario / 1: weak frame / 2: decent situation / 3: compact, vivid, natural

**C. Behavioral recognizability** — 0: random/artificial / 1: partly plausible / 2: mostly recognizable / 3: strongly observed, feels true

**D. Mechanism discipline** — 0: no mechanism/muddled / 1: multiple weak / 2: one main but loose / 3: one clean mechanism doing the work

**E. Compression** — 0: bloated/chatty / 1: somewhat loose / 2: reasonably tight / 3: crisp, spoken, efficient

**F. Dialogue naturalness** — 0: essay-like/robotic / 1: partly unnatural / 2: mostly spoken / 3: fully natural, human, slightly messy in a good way

**G. Tone fit** — 0: snide/cute/muggy/off-brand / 1: mixed / 2: mostly aligned / 3: warm, calm, lightly playful, humane

**H. Learning clarity** — 0: meaning obscured / 1: some confusion risk / 2: mostly clear / 3: immediately clear and instructionally useful

**I. Comic effect** — 0: no smile/lift / 1: idea of a joke / 2: mild smile / 3: reliable small delight

**Thresholds:** 23-27 excellent, keep. 19-22 good, maybe polish. 15-18 salvageable, revise. 0-14 rebuild.

**Hard rule:** Anything below 3 on Learning Clarity cannot ship.

## 8. Content Rules by Format

**Dialogue** — best place for humor. Use polite friction, mild vanity, insecurity, face-saving, overconfidence, tiny status shifts. Do not make every line funny. Usually one comic turn is enough.

**Reading passages** — humor as atmosphere, not joke density. Favor observation, contrast between official language and real life, self-presentation, gently absurd logistics.

**Drill items** — tiny only. One amusing phrase is enough. No layered bits.

**Explanations** — humor should be almost invisible. Use warmth, not punchlines.

**Distractors** — wrong answers should be: too literal, too formal, too self-centered, superficially plausible, missing the social inference.

## 9. Before/After Training Pairs

### A. Over-explained vs implied

**Bad:** "Thank you for your very helpful suggestion. Although it has created several new problems, I appreciate your effort and will try to deal with the consequences."
*Too explicit. Subtext is spoken instead of implied.*

**Better:** "Thanks. I especially enjoyed the new problems."
*Listener fills in the gap. Clear irritation, compact, recognizable.*

### B. Quirk vs behavior

**Bad:** "I am so stressed I might turn into a microwave and marry a cloud."
*Random. No observed human behavior.*

**Better:** "I'm not stressed. I've only checked the email twelve times."
*Recognizable anxiety. Specific. Spoken. Human.*

### C. Polished vs lived speech

**Bad:** "Unfortunately, I have a prior commitment that I must honor, but I appreciate the invitation."
*Too written. No social texture.*

**Better:** "I do, actually. I just already said yes to someone else, which was bad planning on my part."
*Sounds like a person. Slightly messy. Mild self-exposure creates warmth.*

### D. Cartoon distractor vs plausible distractor

**Bad:** Why is the speaker annoyed? A. Because the moon is too loud.
*No one would choose it.*

**Better:** A. Because the other person was slightly too formal. B. Because the other person created extra work while trying to help. C. Because the speaker dislikes all advice.
*Wrong answers are plausible interpretations, not nonsense.*

### E. Stacked mechanisms vs one mechanism

**Bad:** A manager uses bizarre metaphors, dramatic irony, absurd exaggeration, and fake Shakespearean diction to discuss a missing stapler.
*Too many engines. Feels written.*

**Better:** "The stapler is not gone," said the manager. "It's just on an independent journey."
*One mechanism: euphemistic over-formality. Quick. Clear.*

## 10. System Architecture

Comedy is a curated system, not a one-shot generation task.

1. Define tone, forbidden habits, humor levels, evaluation standards (this document)
2. Claude generates multiple candidates following the process above
3. Human editor selects and lightly tunes
4. Best outputs become exemplars for future prompting

Examples are not just illustrations. They are rails.

The goal is not to make Claude "funny." It is to make Claude reliable at generating material that is socially alive, compact, emotionally safe, and pedagogically useful. The path is not inspiration. It's architecture.

## 11. Prompt for Claude

> For each scene, do not start by writing jokes. First identify the plain comic truth, the relevant human behavior, the social tension, and the learning goal. Then choose one comic mechanism only. Build a short, plausible social scenario where the humor arises from recognizable behavior rather than randomness. Keep dialogue spoken, compressed, and slightly messy rather than polished. Do not explain the joke. Do not use whimsical quirk unless grounded in real human behavior. Leave one inferential step for the learner. The final scene must pass two tests: it should create a smile or moment of recognition, and it must preserve immediate comprehension for the learner.

## 12. Best One-Sentence Rule

Do not start with jokes. Start with a clear human truth, build a small plausible social premise around it, choose one comic mechanism, write the scene in Aelu's voice, leave one inferential step for the learner, then compress until the joke feels spoken and clear.
