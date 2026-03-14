# Spiral Cycle Template

> Last updated: 2026-03-10

## Overview

Each spiral cycle moves through four phases: determine objectives, identify and resolve risks, develop and verify, and plan the next cycle. This template provides the structure for planning and executing a cycle, with guidelines, required artifacts, and a worked example.

---

## Cycle Duration

| Cycle Size | Duration | When to Use |
|-----------|----------|-------------|
| **Mini** | 3-5 days | Single feature, bug fix, or risk spike. Low complexity. |
| **Standard** | 1-2 weeks | Feature with moderate complexity, or a risk mitigation requiring development + testing. |
| **Major** | 2-4 weeks | Architecture change, multi-component feature, or high-risk mitigation requiring prototyping. |

**Default:** Standard (1-2 weeks). Use Mini for quick wins and Major only when justified by risk or scope.

**Rule:** If a cycle exceeds 4 weeks, it's too big. Split it.

---

## Phase 1: Determine Objectives

**Question:** "What are we trying to achieve in this cycle, and why?"

### Required Artifacts

| Artifact | Description |
|----------|-------------|
| **Cycle goal statement** | One sentence: "This cycle will [achieve X] to [address risk Y / deliver value Z]." |
| **Success criteria** | 2-5 measurable criteria that define "done" for this cycle. |
| **Stakeholder win conditions** | Which stakeholders benefit? (See `win-conditions.md`) |
| **Constraints** | Time budget, technology constraints, dependencies. |
| **Scope boundary** | Explicitly state what is NOT in scope for this cycle. |

### Phase 1 Template

```
Cycle ID:      YYYY-MM-[SEQ] (e.g., 2026-03-01)
Cycle Size:    Mini / Standard / Major
Target Duration: [N days/weeks]
Start Date:    YYYY-MM-DD

Goal: This cycle will [VERB] [WHAT] to [WHY].

Success Criteria:
1. [Measurable criterion]
2. [Measurable criterion]
3. [Measurable criterion]

Stakeholder Benefits:
- Learner: [benefit or N/A]
- Developer: [benefit or N/A]
- Platform: [benefit or N/A]
- Content: [benefit or N/A]

Constraints:
- [time, tech, dependency constraints]

Out of Scope:
- [explicitly excluded items]
```

---

## Phase 2: Identify and Resolve Risks

**Question:** "What could go wrong, and how do we reduce that risk before building?"

### Required Artifacts

| Artifact | Description |
|----------|-------------|
| **Risk list** | Risks specific to this cycle's objectives. Reference risk register IDs where applicable. |
| **Risk assessment** | Probability and impact for each risk (using risk register scoring). |
| **Mitigation plan** | For each High/Critical risk: how to reduce it before Phase 3. |
| **Prototype decision** | Does any risk warrant a prototype? (See `prototyping-strategy.md`) |
| **Go/no-go checkpoint** | After risk analysis: proceed, pivot, or abandon the cycle? |

### Phase 2 Template

```
Risks Identified:
| # | Risk | P | I | Score | Mitigation | Prototype? |
|---|------|---|---|-------|------------|------------|
| 1 | [description] | [1-5] | [1-5] | [PxI] | [plan] | [Y/N + type] |
| 2 | [description] | [1-5] | [1-5] | [PxI] | [plan] | [Y/N + type] |

Existing Register Risks Affected:
- [Risk ID]: [how this cycle affects it — increases, decreases, or neutral]

Go/No-Go after Risk Analysis:
- [ ] All Critical risks have mitigations or prototypes planned
- [ ] No showstopper risks identified
- [ ] Decision: GO / PIVOT / ABANDON
```

---

## Phase 3: Develop and Verify

**Question:** "Build the thing. Does it work?"

### Required Artifacts

| Artifact | Description |
|----------|-------------|
| **Implementation** | Working code, deployed or deployable. |
| **Tests** | Automated tests covering the new functionality. Manual test plan for what can't be automated. |
| **Prototype results** | If prototypes were built in Phase 2, document results and decisions. |
| **Verification against success criteria** | Check each criterion from Phase 1. |
| **Risk register update** | Did this cycle create, mitigate, or retire any risks? |

### Phase 3 Template

```
Implementation:
- [List of changes: files modified, features added, bugs fixed]
- [Kanban card IDs completed: F-XXX, B-XXX, D-XXX]

Tests:
- [Automated tests added/modified]
- [Manual test results]

Prototype Results (if applicable):
- [Prototype type: throwaway/evolutionary/operational]
- [Question answered]
- [Decision: proceed/pivot/abandon]

Success Criteria Verification:
| # | Criterion | Met? | Evidence |
|---|-----------|------|----------|
| 1 | [criterion] | Yes/No/Partial | [evidence] |
| 2 | [criterion] | Yes/No/Partial | [evidence] |
| 3 | [criterion] | Yes/No/Partial | [evidence] |

Risk Register Updates:
- [Risk ID] status changed to [new status]
- New risk identified: [description]
```

---

## Phase 4: Plan Next Cycle

**Question:** "What did we learn, and what should we do next?"

### Required Artifacts

| Artifact | Description |
|----------|-------------|
| **Retrospective** | What went well, what didn't, what to change. |
| **Velocity assessment** | Was the cycle sized correctly? Adjust for next cycle. |
| **Next cycle objectives** | Preliminary goal for the next cycle (feeds into next Phase 1). |
| **Risk register review** | Any risks changed? New risks discovered during this cycle? |
| **Anchor point progress** | How does this cycle move toward the next anchor point? |

### Phase 4 Template

```
Retrospective:
- Went well: [list]
- Didn't go well: [list]
- Change for next cycle: [one specific process change]

Velocity:
- Planned duration: [N days]
- Actual duration: [N days]
- Sizing assessment: [Too big / About right / Too small]

Next Cycle Objectives (preliminary):
- Goal: [one sentence]
- Priority risks to address: [list]
- Anchor point: [LCO/LCA/IOC] — progress: [description]

Cycle Completed: YYYY-MM-DD
```

---

## Review Checkpoints

Within each cycle, check in at these points:

| Checkpoint | When | Purpose | Duration |
|-----------|------|---------|----------|
| **Kick-off** | Day 1 | Confirm Phase 1 and Phase 2 are complete. Ensure clarity on goal and risks. | 15 minutes |
| **Mid-cycle** | Halfway point | Are we on track? Any new risks? Scope creep? | 15 minutes |
| **Pre-verification** | Before Phase 3 is "done" | Review success criteria. Identify any gaps before declaring done. | 15 minutes |
| **Cycle close** | Last day | Phase 4 retrospective. Plan next cycle. | 30 minutes |

For a solo founder, these are structured self-check-ins, not meetings. Write the answers down.

---

## Cycle Retrospective Template

Used in Phase 4. Keep it short and honest.

```
## Cycle [YYYY-MM-SEQ] Retrospective

### What went well?
- [item]

### What didn't go well?
- [item]

### What surprised us?
- [item — unexpected risk, unexpected ease, unexpected learning]

### One thing to change next cycle:
[One specific, actionable change. Not "be better" — something concrete.]

### Time tracking:
- Phase 1 (objectives): [hours]
- Phase 2 (risks): [hours]
- Phase 3 (develop): [hours]
- Phase 4 (plan): [hours]
- Total: [hours]

### Did this cycle advance an anchor point?
[Yes/No. If yes, which criteria? If no, why not?]
```

---

## Worked Example: "Add New Drill Type — Measure Word Matching"

### Phase 1: Determine Objectives

```
Cycle ID:      2026-03-02
Cycle Size:    Standard
Target Duration: 7 days
Start Date:    2026-03-15

Goal: This cycle will add a measure word matching drill to improve
learners' ability to pair measure words with nouns, addressing a
gap in the current 12 drill types.

Success Criteria:
1. Drill type "measure_word_match" is functional in web UI and CLI
2. 20+ measure word pairs seeded from HSK 1-3 vocab
3. Scoring integrates with existing SRS scheduler
4. Drill appears in interleaved sessions when measure word items are due

Stakeholder Benefits:
- Learner: Fills a real gap — measure words are a common error source
- Developer: Extends drill framework (reusable pattern for future drill types)
- Content: Measure word data already exists in vocab table, just needs drill exposure

Constraints:
- Must work within existing drill framework (no new tables)
- iOS Capacitor must render correctly (test on simulator)
- 7-day time budget

Out of Scope:
- Audio pronunciation of measure words (future cycle)
- Measure word explanation/teaching content (context notes can be added later)
- New measure word vocabulary (use existing HSK 1-3 items only)
```

### Phase 2: Identify and Resolve Risks

```
Risks Identified:
| # | Risk | P | I | Score | Mitigation | Prototype? |
|---|------|---|---|-------|------------|------------|
| 1 | UI interaction (drag-and-drop) may not work on iOS | 3 | 3 | 9 | Use tap-to-select instead of drag-and-drop | Y — throwaway HTML |
| 2 | Insufficient measure word data in current vocab | 2 | 2 | 4 | Audit vocab table for measure word coverage before starting | N |
| 3 | Scoring integration may break existing SRS intervals | 2 | 4 | 8 | Use shadow scoring for first 20 reviews | N — but verify carefully |

Existing Register Risks Affected:
- T-003 (iOS compat): Increased — new UI element on iOS
- T-007 (FSRS): Neutral — using same scoring, just new drill type

Prototype Plan:
- Throwaway: measure-word-match.html in /tmp/aelu-proto/
- Test tap-to-select interaction on iOS simulator
- Time budget: 2 hours
- Go/no-go: if tap-to-select is usable on mobile, proceed

Go/No-Go after Risk Analysis:
- [x] All Critical risks have mitigations (no Critical risks)
- [x] No showstopper risks
- [x] Decision: GO (after throwaway prototype confirms UI approach)
```

### Phase 3: Develop and Verify

```
Throwaway Prototype Result:
- Built /tmp/aelu-proto/measure-word-match.html
- Tap-to-select works well on iOS simulator
- Drag-and-drop rejected — too finicky on mobile
- Decision: Proceed with tap-to-select

Implementation:
- Added drill type "measure_word_match" to drill_engine.py
- Added template web/templates/drills/measure_word_match.html
- Added CLI rendering in drills.py
- Seeded 24 measure word pairs from existing HSK 1-3 vocab
- SRS scoring integrated via standard review_item() pathway

Tests:
- test_measure_word_drill.py: 8 tests (generation, scoring, display)
- Manual test: completed 5 drill sessions on web, CLI, and iOS simulator
- Interleaving: verified measure word drills appear in mixed sessions

Success Criteria Verification:
| # | Criterion | Met? | Evidence |
|---|-----------|------|----------|
| 1 | Drill functional in web + CLI | Yes | Screenshots, manual test |
| 2 | 20+ pairs seeded | Yes | 24 pairs from HSK 1-3 |
| 3 | SRS integration | Yes | review_item() logs show intervals |
| 4 | Interleaving works | Yes | Mixed session includes measure word drills |

Risk Register Updates:
- T-003: Tested on iOS simulator, no issues. Score unchanged.
- No new risks identified.
```

### Phase 4: Plan Next Cycle

```
Retrospective:
- Went well: Throwaway prototype saved time — confirmed UI approach in 2 hours
  before committing to production code.
- Didn't go well: Seeding took longer than expected — had to manually verify
  measure word accuracy for 24 items.
- Change for next cycle: Pre-audit data availability before cycle starts.
  Add to Phase 1 checklist.

Velocity:
- Planned: 7 days
- Actual: 6 days
- Sizing: About right

Next Cycle Objectives (preliminary):
- Goal: Add audio pronunciation to measure word drill (voice cue before selection)
- Priority risks: T-003 (iOS audio API behavior), T-006 (TTS availability)
- Anchor point: IOC — advances content sufficiency criterion

Cycle Completed: 2026-03-21
```

---

## Relationship to Other Artifacts

- **Risk Register** (`risk-register.md`): Phase 2 references and updates the register.
- **Prototyping Strategy** (`prototyping-strategy.md`): Phase 2 determines prototyping approach.
- **Anchor Points** (`anchor-points.md`): Phase 4 tracks progress toward anchor points.
- **Risk Retirement Criteria** (`risk-retirement-criteria.md`): Phase 3 may produce evidence for risk retirement.
- **Win Conditions** (`win-conditions.md`): Phase 1 maps cycle objectives to stakeholder benefits.
- **Kanban Board** (`../kanban/board.md`): Cycle objectives generate Kanban cards. Completed cycle items move to Done.
