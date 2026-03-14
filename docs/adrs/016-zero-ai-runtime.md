# ADR-008: Zero AI Tokens at Runtime

## Status

Accepted (2025-01)

## Context

Many language learning apps use LLMs at runtime for:
- Grading free-form answers (ChatGPT evaluating a user's translation)
- Generating dynamic content (personalized sentences, adaptive explanations)
- Conversation practice (chatbot-style dialogue)

Aelu must decide whether to use AI/LLM calls during user sessions.

## Decision

**Zero AI tokens at runtime.** All grading is rule-based. All content is pre-authored. No LLM API calls occur during user sessions.

## Rationale

### Why Zero AI Runtime

1. **Deterministic grading is more trustworthy.** When a user answers a tone drill, the grading should be binary and immediate: correct or incorrect, with a specific reason. LLM-based grading introduces randomness — the same answer might be graded differently on two attempts. This erodes user trust.

2. **No API costs.** At $0.01-0.03 per API call (GPT-4 pricing), 100 users doing 40 drills/day = 4,000 calls/day = $40-120/day = **$1,200-3,600/month**. This is 80-240x the hosting cost and would consume the entire subscription revenue.

3. **No latency.** Rule-based grading returns in <1ms. An LLM API call takes 500-3,000ms. For a rapid-fire drill interaction (answer → grade → next drill), this latency destroys the flow.

4. **Works offline.** The mobile app (Capacitor) can function without network for pre-cached content. LLM calls would require connectivity for every drill.

5. **Predictable costs.** Hosting cost is fixed (~$4/month). AI API costs scale with usage and are hard to cap. A viral moment could generate thousands of dollars in API costs overnight.

6. **Privacy.** User drill responses are never sent to third-party AI providers. All data stays between the client and Aelu's server.

### What AI IS Used For (Offline/Build-Time)

AI is used during **content generation** (not runtime):

- **Claude generates seed content**: vocabulary items, example sentences, context notes, dialogue scenarios. This happens during development, not during user sessions.
- **Content review**: Claude assists in reviewing Chinese writing quality against the 分寸 standard.
- **Code assistance**: Claude helps write and debug Aelu's codebase.

These are build-time costs, amortized over all users, not per-request costs.

### Grading Approach

| Drill Type | Grading Method | Accuracy |
|-----------|----------------|----------|
| Multiple choice | Exact match | 100% |
| Pinyin input | Normalized string comparison + tone number matching | 99%+ |
| Character recognition | Exact hanzi match | 100% |
| Tone production | Rule-based tone contour analysis (pitch direction) | ~85% |
| Fill in the blank | Acceptable answer set (pre-authored) | 95%+ |
| Translation | Acceptable answer set + fuzzy matching | 90%+ |
| Sentence ordering | Exact sequence match | 100% |

The 90-95% accuracy on translation/fill-in-the-blank drills is the main limitation. Some valid answers are marked incorrect because they weren't in the pre-authored acceptable set. This is mitigated by:

- Expanding acceptable answer sets based on user feedback
- Using fuzzy matching (Levenshtein distance) for minor typos
- Providing "Report incorrect grading" button

## Consequences

### Positive

- Hosting cost is fixed and predictable ($4/month regardless of user count)
- Drill grading is instant (<1ms)
- No third-party API dependency (no OpenAI outage = Aelu outage)
- User data never leaves Aelu's infrastructure
- Works offline for cached content

### Negative

- **Limited flexibility.** Cannot grade creative answers (free-form translation, open-ended conversation). Some valid user answers are marked incorrect.
- **Content must be pre-authored.** Every vocabulary item, example sentence, and acceptable answer must be written in advance. Cannot dynamically generate content tailored to individual users.
- **No conversation practice.** Cannot offer chatbot-style free-form conversation, which some users want.
- **Tone grading ceiling.** Without ML-based pitch analysis (parselmouth, etc.), tone grading accuracy tops out at ~85%. Mitigated by providing clear feedback on why a tone was marked wrong.

### Neutral

- Content generation (build-time AI) is a separate cost from runtime AI
- The acceptable-answer-set approach improves over time as more valid answers are added
- If AI costs drop 10x in the future, the economics change significantly

## Revisit Triggers

1. **User demand for free-form conversation practice** — survey data showing >30% of users want this feature
2. **Grading accuracy complaints** — if >5% of support tickets are about incorrect grading
3. **AI API costs drop below $0.001/call** — changes the cost math fundamentally
4. **On-device LLM capability** — if phones can run capable LLMs locally (Apple Intelligence, etc.), the latency and cost concerns disappear
5. **Competitive pressure** — if all competitors offer AI-powered features and Aelu loses users as a result
