# Prototyping Strategy

> Last updated: 2026-03-10

## Purpose

Not every risk is best addressed by building production code. Some risks need a throwaway sketch. Others need an evolutionary prototype that becomes the real thing. This document defines which prototyping approach to use based on the risk being addressed, with concrete Aelu examples.

---

## Prototype Types

### Throwaway Prototypes

**Definition:** Built to learn, then discarded. The code never ships. The insight does.

**Characteristics:**
- Quick (hours, not days)
- Minimal quality standards — no tests, no error handling, no edge cases
- Single-purpose: answers one specific question
- Deleted after the question is answered
- Lives in a scratch directory (`/tmp/aelu-proto/` or a branch that gets deleted)

**When to use:**
- UI/UX uncertainty ("Will this layout confuse learners?")
- Algorithm exploration ("Does this scoring formula produce reasonable intervals?")
- API feasibility ("Can this third-party API do what we need?")
- Content format testing ("Does this dialogue structure read naturally?")

**Aelu examples:**

| Risk | Prototype | Question Answered | Time |
|------|-----------|-------------------|------|
| New drill type unclear | HTML mockup of "measure word matching" drill with hardcoded data | "Is this interaction pattern learnable in 10 seconds?" | 2 hours |
| Tone grading accuracy | Python script comparing `sounddevice` + pitch detection against known tone samples | "Can we distinguish tone 2 from tone 3 with >80% accuracy?" | 4 hours |
| Graded reader readability | Static HTML page with sample passage, hanzi sizing, and gloss popup | "Is the reading experience comfortable on iOS?" | 1 hour |
| Context note format | 5 sample context notes in different styles (story, etymology, mnemonic) | "Which format does the learner actually read?" | 1 hour |

---

### Evolutionary Prototypes

**Definition:** Built to ship. Starts simple, iterates toward production quality. The prototype becomes the product.

**Characteristics:**
- Production code from day one (tests, error handling, schema migrations)
- Incremental: v1 is minimal, v2 adds depth, v3 is complete
- Lives in the main codebase on a feature branch
- Merged when it meets Definition of Done

**When to use:**
- Architecture decisions that need real-world validation
- Features with clear requirements but uncertain implementation complexity
- Algorithm changes where the only way to know if it works is to run it with real data
- Infrastructure changes (deployment, database, hosting)

**Aelu examples:**

| Risk | Prototype | Evolution Path | Time |
|------|-----------|---------------|------|
| FSRS algorithm change | Shadow scoring — new algorithm runs alongside SM-2, both produce intervals, compare | v1: shadow scores logged. v2: A/B test with real reviews. v3: full cutover if metrics improve. | 1 week per version |
| WebSocket session sync | Flask-Sock integration with basic ping/pong | v1: connection management. v2: drill state sync. v3: audio timing sync. | 3 days per version |
| Classroom/LTI integration | LTI 1.3 launch endpoint with hardcoded course | v1: LTI launch works. v2: grade passback. v3: roster sync. | 1 week per version |
| Vocab encounter cleanup loop | Log lookups, query for boost candidates | v1: encounter logging. v2: scheduler integration. v3: cleanup recommendations in CLI. | 2-3 days per version |

---

### Operational Prototypes

**Definition:** Tests the deployment, infrastructure, or operational aspects of a feature — not the feature itself.

**Characteristics:**
- Validates that the system works in the real environment (not just locally)
- Tests deployment pipelines, database migrations, monitoring, backup/restore
- May use simplified or stub functionality
- Often done in a staging environment or on a separate Fly.io machine

**When to use:**
- Database migration risk (will this migration work on production SQLite?)
- Deployment process changes (new Fly.io config, Litestream changes)
- Monitoring gaps (will we detect this failure mode?)
- Performance under load (will this query work at 100 concurrent users?)

**Aelu examples:**

| Risk | Prototype | What It Validates | Time |
|------|-----------|-------------------|------|
| SQLite table recreation | Run migration on copy of production DB | "Does the 16-table schema migrate cleanly? Any data loss?" | 2 hours |
| Fly.io machine restart recovery | Stop and restart machine, check state | "Does Litestream restore correctly? How long is downtime?" | 1 hour |
| Load testing (D-005) | `locust` script simulating 100 concurrent users | "At what point does SQLite contention become unacceptable?" | 4 hours |
| Litestream backup restoration | Destroy local DB, restore from S3 | "How long does full restore take? Is data complete?" | 1 hour |

---

## Prototyping Criteria by Risk Type

Use this matrix to decide which prototype type is appropriate for a given risk:

| Risk Category | Sub-Category | Default Prototype | Rationale |
|--------------|-------------|-------------------|-----------|
| Technical / Architecture | — | Operational | Architecture risks manifest in production, not localhost |
| Technical / Data Integrity | — | Operational | Data risks need real data to validate |
| Technical / Platform Compat. | — | Throwaway | Quick HTML/CSS test on target device is sufficient |
| Technical / Dependency | — | Throwaway | Spike: can we even import/build this library? |
| Technical / Algorithm | — | Evolutionary | Algorithm correctness needs real data over time |
| Security / Authentication | — | Evolutionary | Auth code must be production-quality from start |
| Security / Input Validation | — | Throwaway | Quick fuzzing script to test boundaries |
| Performance / Database | — | Operational | Performance is environment-specific |
| Performance / Client-Side | — | Throwaway | Quick page with performance.now() measurements |
| Compliance / GDPR | — | Evolutionary | Compliance code ships to production |
| Market / Retention | — | Throwaway | Mockup or A/B test before building |
| Market / Content Quality | — | Throwaway | Sample content before committing to a format |
| Operational / Infrastructure | — | Operational | By definition |

---

## Evaluation Metrics

Every prototype must answer a question. Define the question and success metric before building.

### Throwaway Prototype Evaluation

```
Question:     [One specific question this prototype answers]
Success:      [Measurable criterion — e.g., "tone detection accuracy >80%"]
Failure:      [What would make us abandon this direction]
Time Budget:  [Maximum hours to spend — stop and reassess if exceeded]
Output:       [Decision made, documented in spiral cycle log]
```

### Evolutionary Prototype Evaluation

```
Question:     [What risk does this address?]
v1 Success:   [Minimum viable — does the basic approach work?]
v2 Success:   [Integration — does it work with existing system?]
v3 Success:   [Production — does it meet quality and performance requirements?]
Go/No-Go:     [After each version, decide: continue, pivot, or abandon]
```

### Operational Prototype Evaluation

```
Question:     [Will this work in production?]
Environment:  [Where this prototype runs — staging, copy of prod, separate machine]
Success:      [Production-like behavior verified — e.g., "migration completes in <30s"]
Failure:      [Unacceptable behavior — e.g., "data loss during migration"]
Cleanup:      [How to clean up after the test — delete machine, restore backup]
```

---

## Go/No-Go Decision Framework

After each prototype, make an explicit decision:

| Signal | Decision | Action |
|--------|----------|--------|
| Prototype succeeds, question answered clearly | **Go** | For throwaway: delete prototype, create production card. For evolutionary: continue to next version. |
| Prototype partially succeeds, concerns remain | **Conditional Go** | Identify remaining risks. Create a follow-up prototype or add risk mitigations. |
| Prototype fails, approach is fundamentally wrong | **No-Go** | Delete prototype. Document what was learned. Consider alternative approach or accept the risk. |
| Time budget exceeded, question still unanswered | **Pivot** | Stop building. Reassess whether the question is the right one. Consider a simpler experiment. |

---

## Worked Examples

### Example 1: Prototype New Drill Type — Throwaway

**Risk:** T-007 variant — "Will a measure word matching drill be pedagogically effective?"

**Approach:** Throwaway HTML prototype.

```
1. Create /tmp/aelu-proto/measure-word-drill.html
2. Hardcode 5 measure word pairs (e.g., 一杯咖啡, 一本书)
3. Simple drag-and-drop matching interface
4. No backend, no database, no authentication
5. Test on iOS simulator and desktop browser
6. Time: 2 hours maximum
```

**Evaluation:**
- Question: "Can learners match measure words to nouns in <10 seconds per pair?"
- Success: Self-test completes comfortably. Interaction feels natural on mobile.
- Failure: Drag-and-drop unusable on mobile. Matching paradigm doesn't teach association.
- Output: Decision documented. If Go, create F-card for production implementation.

### Example 2: Prototype FSRS Algorithm Change — Evolutionary + A/B Test

**Risk:** T-007 — "Will FSRS parameter changes improve retention without destabilizing scheduling?"

**Approach:** Shadow scoring with A/B comparison.

```
v1 (3 days):
  - Add shadow_fsrs_score column to review table
  - Compute alternative interval on every review, log but don't use
  - Compare shadow vs. actual intervals in diagnostics

v2 (5 days):
  - Route 50% of new reviews to shadow algorithm
  - Track retention rate for both groups
  - Dashboard showing retention comparison

v3 (2 days):
  - If shadow algorithm shows >=2% retention improvement, cutover
  - If not, revert shadow column, document findings
```

**Go/No-Go after v1:** Are shadow intervals in a reasonable range (1-365 days)? If many intervals are <1 or >365, the parameters are wrong — stop and recalibrate.

---

## Relationship to Other Artifacts

- **Risk Register** (`risk-register.md`): Risks that score High or Critical should have a prototyping plan.
- **Risk Taxonomy** (`risk-taxonomy.md`): Risk category determines default prototype type.
- **Spiral Cycle Template** (`spiral-cycle-template.md`): Prototyping is Phase 3 (Develop/Verify) of every cycle.
- **Kanban Board** (`../kanban/board.md`): Evolutionary prototypes generate In Progress cards. Throwaway prototypes are Experiment cards.
