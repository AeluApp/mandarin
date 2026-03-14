# ADR-002: FSRS-Inspired Half-Life Regression for SRS

## Status

Accepted (2025-11)

## Context

Aelu's core learning loop is spaced repetition: present vocabulary items at increasing intervals, timed so the learner reviews just before forgetting. The scheduling algorithm determines when each item is next reviewed. Poor scheduling wastes learner time (reviewing too early) or causes forgetting (reviewing too late).

The system needed an adaptive scheduler that improves predictions as more review data accumulates, rather than relying on fixed parameters.

## Decision Drivers

- Must predict optimal review timing with limited initial data (cold-start problem)
- Must adapt to individual learner and item differences
- Must be fully deterministic (zero LLM tokens at runtime)
- Must be computationally cheap (scheduling runs during session start, ~80ms budget)
- Existing research (FSRS by open-spaced-repetition) provides a validated model

## Considered Options

### Option 1: SM-2 (SuperMemo 2)

The classic algorithm used by Anki. Fixed ease factor with simple multiplier updates.

- **Pros**: Well-understood, simple implementation, battle-tested by millions of Anki users
- **Cons**: Ease factor converges to minimum ("ease hell"), no forgetting curve model, no difficulty estimation, parameters don't adapt to individual items, ignores review history beyond the last review

### Option 2: FSRS (Free Spaced Repetition Scheduler)

Machine-learned model using exponential forgetting curve with stability and difficulty parameters. Published by open-spaced-repetition project.

- **Pros**: State-of-the-art retention prediction, adapts per item, backed by published research and benchmark data, models both stability (how well-learned) and difficulty (intrinsic item hardness)
- **Cons**: Full FSRS requires neural network parameter optimization, complex implementation, may be overkill for initial data volume

### Option 3: Leitner System

Simple box-based system: correct answers move items to the next box (longer interval), incorrect answers reset to box 1.

- **Pros**: Very simple, easy to explain to users
- **Cons**: Coarse intervals (discrete boxes, not continuous), no adaptation to individual items, no forgetting curve model

### Option 4: Custom Half-Life Regression (chosen)

Inspired by FSRS but simplified: model the forgetting curve as an exponential decay with a per-item half-life that adapts based on review outcomes.

- **Pros**: Grounded in FSRS research, simpler implementation than full FSRS, per-item adaptation, continuous interval calculation, computationally trivial
- **Cons**: Fewer parameters than full FSRS (may be less accurate), no neural network optimization (uses heuristic updates)

## Decision

Implement a half-life regression model inspired by FSRS. Each item tracks three parameters:

1. **half_life_days**: The time for predicted recall to drop to 50%. Starts at 1.0 day.
2. **difficulty**: Intrinsic item difficulty on [0, 1] scale. Starts at 0.5.
3. **ease_factor**: Interval growth multiplier. Starts at 2.5 (SM-2 default).

The predicted recall at any time is:

```
p_recall = 2^(-elapsed_days / half_life_days)
```

After each review, parameters update:

```python
if correct:
    half_life *= ease_factor * (1 - 0.2 * difficulty)
    difficulty = max(0.1, difficulty - 0.02)  # slightly easier
    ease_factor = min(3.5, ease_factor + 0.05)
else:
    half_life = max(0.25, half_life * 0.5)
    difficulty = min(0.9, difficulty + 0.05)  # harder
    ease_factor = max(1.3, ease_factor - 0.15)
```

The next review is scheduled when predicted recall drops to 85% (configurable):

```
next_interval = half_life * log2(1 / 0.85) = half_life * 0.2345
```

## Consequences

### Positive

- **Better than SM-2**: The forgetting curve model predicts recall probability at any point in time, not just at the scheduled review date. This enables intelligent queue prioritization (review items with lowest predicted recall first).
- **Per-item adaptation**: Items that are consistently easy get longer intervals; items that are consistently hard get shorter intervals. This eliminates SM-2's "ease hell" problem.
- **Computationally trivial**: A scheduling calculation is a single exponential evaluation. No neural network inference, no optimization loop. Fits within the 80ms session-start budget.
- **Data foundation for optimization**: The half-life/difficulty/ease parameters create a rich dataset for future optimization (see `docs/operations-research/srs-optimization.md`). Grid search and continuous optimization can tune global defaults as review data accumulates.
- **Calibration-measurable**: Predicted recall can be compared to actual accuracy in bins, providing a clear calibration metric. If the model says "80% recall" but actual accuracy is 65%, the model is overconfident and parameters need adjustment.

### Negative

- **Less accurate than full FSRS**: The heuristic update rules are simpler than FSRS's neural network-optimized parameters. The accuracy gap is meaningful only with 10,000+ review events, which is far beyond current data volume.
- **Cold-start**: Initial parameters are literature defaults (half_life=1.0, difficulty=0.5, ease_factor=2.5). For a new item with no reviews, scheduling is a guess. This is mitigated by conservative initial intervals (review within 6 hours for first review).
- **No cross-item learning**: Unlike full FSRS, the model doesn't learn that "tone-related items are harder for this user." Each item adapts independently. A future extension could add modality-specific difficulty modifiers.

### Migration Path

When review data exceeds 10,000 events, run the optimization pipeline (`docs/operations-research/srs-optimization.md`) to compare current heuristic parameters against grid-search-optimized parameters. If the optimized parameters show >3% improvement in cross-entropy loss, update defaults and consider implementing full FSRS with per-user parameter training.
