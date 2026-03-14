# ADR-010: Disciplined Aptness as Content Quality Standard

## Status

Accepted (2026-01)

## Context

Aelu generates Chinese language content (vocabulary sentences, context notes, dialogue scenarios, graded reader passages) at build time using Claude. Without a principled quality standard, generated content tends toward two failure modes: textbook-stiff ("Please sit down. Thank you very much.") or artificially colloquial ("Dude, this hotpot is fire!"). Neither reflects how Chinese is actually spoken by real people in real situations.

A content quality standard was needed to guide both LLM prompting and human review.

## Decision Drivers

- Content must be pedagogically useful (clear, graduated, appropriate to HSK level)
- Content must sound natural to native speakers (not 教材味 / textbook smell)
- Content must be culturally authentic without exoticizing
- The standard must be communicable to LLM prompts (it guides content generation)
- Must complement the Civic Sanctuary aesthetic (calm, grounded, respectful)

## Considered Options

### Option 1: Textbook-Formal

Use CCTV-standard Mandarin, formal register, complete sentences, proper grammar.

- **Pros**: Safe, correct, appropriate for beginners
- **Cons**: Sounds like a textbook. Nobody talks like this. Learners who study only textbook Chinese are confused by real conversations. The enemy: 教材味.

### Option 2: Colloquial-Only

Use internet slang, casual speech, contractions, filler words.

- **Pros**: Sounds "real," engaging for younger learners
- **Cons**: Inappropriate for beginners who need foundations, may teach incorrect usage patterns, difficult to grade, alienates learners who want formal proficiency

### Option 3: Disciplined Aptness (chosen)

Apply the principle of 分寸 (fen cun) -- the disciplined sense of proportion. Content should be natural enough to sound like something a real person would say, but controlled enough to be teachable. Every word choice must be 贴切 (apt), not 华丽 (showy).

- **Pros**: Produces content that sounds real without being chaotic, teachable without being sterile, culturally grounded without being exotic
- **Cons**: Higher content production cost (more review iterations), harder to communicate the standard to LLM prompts, subjective (requires taste)

## Decision

Adopt 分寸 (disciplined aptness) as the content quality standard. Documented in `chinese_writing_standard.md` with specific guidelines:

### Core Principles

1. **贴切 not 华丽** (apt, not showy): Every word earns its place. No decoration for decoration's sake.

2. **Enemy: 教材味** (textbook smell): Content that could appear in a standardized test is suspect. Real Chinese uses particles, ellipsis, word-order flexibility, and pragmatic markers that textbooks omit.

3. **Register awareness**: Content is tagged with register (`casual`, `neutral`, `professional`, `mixed`). Each register has its own naturalness standards. Casual register allows 呢, 嘛, 啊; professional register demands complete sentences and formal vocabulary.

4. **Naturalness balanced against teachability**: A perfectly natural sentence may be unteachable (too many unknown words, ambiguous grammar). Naturalness is the goal; teachability is the constraint.

5. **Cultural grounding without exoticism**: Content references real Chinese contexts (ordering at a restaurant, navigating the metro, workplace small talk) without reducing Chinese culture to stereotypes (martial arts, dragons, ancient wisdom).

### Application to Content Types

| Content Type | 分寸 Standard |
|-------------|--------------|
| Vocab sentences | Would a real person say this? In what situation? |
| Context notes | Explain usage, not just definition. "Used when..." not "Means..." |
| Dialogue scenarios | Characters have motivations. Conversations have stakes. |
| Graded reader passages | Stories with real emotional weight at the learner's level |
| Grammar examples | Show the grammar point in a natural sentence, not a grammar exercise |

### Quality Checklist (for content review)

1. Would a native speaker say this in the given context? (If not, revise or discard.)
2. Does it teach something beyond the target vocabulary? (Context, pragmatics, culture.)
3. Is the register consistent? (No mixing formal and slang without reason.)
4. Does it avoid 教材味? (No "Please open your textbook to page 5.")
5. Is it at the right HSK level? (Known words + 1-2 new words max.)

## Consequences

### Positive

- **Distinctive content voice**: Aelu's Chinese content has a recognizable quality -- calm, natural, slightly literary. This reflects the Civic Sanctuary aesthetic in content, not just design.
- **Pedagogical integrity**: Learners who study with Aelu hear Chinese that matches what they'll encounter in real life. The gap between "study Chinese" and "use Chinese" is smaller.
- **Storytelling standard complement**: The 分寸 principle extends to the storytelling standard (`storytelling_standard.md`): tiny stories with real stakes, vivid specificity, spoken-natural voice, one meaningful turn. No melodrama, no fake uplift.
- **LLM prompt guidance**: The standard can be communicated to Claude during content generation: "Apply 分寸. Avoid 教材味. Make it 贴切, not 华丽." This produces measurably better content than generic "write a Chinese sentence" prompts.

### Negative

- **Slower content production**: Each content item goes through multiple review iterations. A vocab sentence that "sounds a bit textbook-y" gets revised. This limits content velocity.
- **Subjectivity**: "Naturalness" is partly subjective. Two reviewers may disagree on whether a sentence has 教材味. Mitigated by the checklist above, but taste is inherently personal.
- **Beginner tension**: HSK 1 content must use very simple vocabulary, which naturally tends toward textbook patterns. Achieving 分寸 at HSK 1 is harder than at HSK 3+. The compromise: HSK 1 content is allowed to be more structured, with naturalness increasing as HSK level rises.
