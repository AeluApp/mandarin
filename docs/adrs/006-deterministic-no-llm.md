# ADR-006: Zero LLM Tokens at Runtime

## Status

Accepted (2025-11)

## Context

Many language learning apps use LLM APIs (GPT-4, Claude) at runtime for features like dynamic sentence generation, conversation practice, grammar explanations, and content adaptation. This introduces variable costs, API dependency, latency, and non-deterministic behavior.

Aelu needed to decide whether to use LLM APIs at runtime for any feature.

## Decision Drivers

- Cost predictability: LLM API costs scale with usage and are hard to forecast
- Determinism: SRS scheduling, drill grading, and mastery tracking must produce identical results given identical inputs
- Offline capability: CLI mode and potential offline mobile mode require no network dependency
- Latency: LLM API calls add 500ms-3s to every request that uses them
- Content quality: Pre-generated content can be reviewed and curated; runtime-generated content cannot

## Considered Options

### Option 1: LLM-Generated Content at Runtime

Use GPT-4 or Claude to generate example sentences, grammar explanations, and conversation responses dynamically.

- **Pros**: Infinite content variety, personalized examples, conversational practice
- **Cons**: $0.01-0.10 per request (at scale: $100-1000/mo for 1000 users), non-deterministic outputs, API downtime breaks the app, latency degrades UX, content quality varies, hallucinated Chinese is a pedagogical hazard

### Option 2: LLM-Assisted Drills

Use LLMs for specific features (conversation practice, writing feedback) while keeping core SRS deterministic.

- **Pros**: Best of both worlds for some features
- **Cons**: Partial LLM dependency still creates cost unpredictability and API risk, conversation practice is the highest-cost feature (long context windows)

### Option 3: Fully Deterministic (chosen)

All content is pre-generated during development (using Claude for content generation, which is a build-time cost, not runtime). All scoring, scheduling, and drill logic is deterministic Python code.

- **Pros**: Zero marginal cost per user, fully offline-capable, deterministic behavior, no API dependency, content is curated and reviewed before shipping
- **Cons**: Limited content variety (299 seed items, finite passages), no dynamic conversation practice, content updates require new releases

## Decision

Zero LLM tokens at runtime. All content (vocabulary, sentences, passages, dialogue scenarios, grammar points, media recommendations) is pre-generated and stored in the SQLite database or JSON files. All scoring, scheduling, and drill logic is deterministic Python code.

Build-time LLM usage is acceptable and encouraged:
- Claude generates vocabulary items, context notes, dialogue scenarios, and graded reader passages during development
- Content is reviewed against the Chinese writing standard (see ADR-010) before inclusion
- The `content_gen/` directory contains generation scripts that use Claude API

Runtime LLM usage is prohibited:
- No API calls to any LLM during user-facing requests
- No "ask Claude" buttons or dynamic generation features
- All drill grading is rule-based (string matching, pinyin comparison, tone checking)

## Consequences

### Positive

- **Zero marginal cost**: Adding 1,000 users costs $0 in LLM API fees. The only scaling costs are server compute and storage.
- **Predictable behavior**: Given the same user state and the same drill, the system produces the same result every time. This makes debugging, testing, and quality assurance straightforward.
- **No API dependency**: Aelu works even if OpenAI/Anthropic APIs are down, rate-limited, or deprecated. The app has no external runtime dependencies beyond its own server.
- **Offline potential**: The deterministic engine can run entirely client-side if embedded in a mobile app with a local SQLite database.
- **Content quality**: Every Chinese sentence, every context note, every dialogue tree has been reviewed by a human. No hallucinated tones, no unnatural phrasing, no textbook smell (see ADR-010).

### Negative

- **Finite content**: 299 seed items, ~50 graded reader passages, 8 dialogue scenarios, 26 grammar points. Users who study intensively will exhaust content faster than new content can be generated. Mitigated by SRS cycling (the same items are reviewed at increasing intervals, providing ongoing value).
- **No conversation practice**: The most-requested feature in language learning apps is free-form conversation with an AI tutor. Aelu cannot offer this without breaking the zero-LLM rule. The dialogue scenario system provides structured conversation practice as a partial substitute.
- **Content production bottleneck**: Every new item requires a content generation session (using Claude at build time), human review, and a database migration. This limits content growth to ~50-100 items per development cycle.

### Revisit Trigger

Consider adding runtime LLM usage if:
- A specific feature (e.g., writing feedback, pronunciation coaching) has clear pedagogical value that cannot be replicated deterministically
- LLM costs drop to <$0.001 per request (making cost a non-issue)
- A local LLM (e.g., Llama, Phi) can run on-device with acceptable latency and quality for Chinese language tasks
