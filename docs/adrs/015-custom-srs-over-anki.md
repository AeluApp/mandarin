# ADR-007: Custom SRS Engine Instead of Anki Algorithm

## Status

Accepted (2025-01)

## Context

Aelu's core learning loop depends on spaced repetition scheduling — deciding when to review each vocabulary item. Options:

1. **SM-2 (SuperMemo 2):** The classic algorithm used by Anki. Well-understood, widely validated.
2. **FSRS (Free Spaced Repetition Scheduler):** Modern algorithm by Jarrett Ye, adopted by Anki in v23.10. Uses half-life regression with 19 parameters.
3. **Custom FSRS-inspired engine:** Half-life regression with Aelu-specific extensions for drill modality, error types, and adaptive difficulty.
4. **Leitner boxes:** Simpler box-based system. Less optimal but easier to implement.

## Decision

Build a **custom SRS engine inspired by FSRS** with half-life regression, extended to support:

- Modality-specific scheduling (different intervals for recognition vs production)
- Error-type tracking (tone errors vs meaning errors affect scheduling differently)
- Adaptive difficulty per item per user
- Integration with drill selection optimizer

## Rationale

### Why Custom Over SM-2/Anki

1. **Modality awareness.** SM-2 treats all reviews equally. But recalling a character's meaning (recognition) and producing its tone (production) are different cognitive tasks with different forgetting curves. A custom engine can maintain separate half-lives per (item, modality) pair.

2. **Error-type granularity.** When a user gets a tone drill wrong, SM-2 just records "incorrect." Aelu's engine records *which* tone they produced, enabling targeted re-scheduling of specific tone confusion pairs (e.g., Tone 2 vs Tone 3).

3. **Drill selection integration.** The SRS engine feeds directly into the content scheduling optimizer (see `content-scheduling-formalization.md`). Custom parameters allow the optimizer to make better item selection decisions.

4. **No Anki dependency.** Anki's scheduling library is tightly coupled to Anki's card model. Integrating it would require adapting Aelu's data model to fit Anki's expectations. Building custom is cleaner.

### Why FSRS-Inspired Over Pure FSRS

1. **Simpler parameter space.** FSRS has 19 parameters that require 1,000+ reviews to optimize. Aelu starts with 3 core parameters (half_life, difficulty, ease_factor) and adds complexity as data accumulates.

2. **Transparency.** Every scheduling decision is explainable: "This item is scheduled for review in 3 days because its half-life is 4.2 days and we want to review at 60% predicted recall." No black-box model.

3. **Zero AI runtime.** The SRS engine is pure math — exponential decay, simple arithmetic. No ML inference, no model loading, no GPU. This aligns with Aelu's "zero AI tokens at runtime" philosophy (see ADR-008).

### Core Algorithm

```python
def predicted_recall(elapsed_days, half_life):
    """Exponential forgetting curve."""
    return 2 ** (-elapsed_days / half_life)

def update_after_review(progress, correct, response_time_ms):
    """Update SRS parameters after a review."""
    if correct:
        # Successful recall: increase half-life
        progress.half_life *= progress.ease_factor
        progress.ease_factor = min(3.5, progress.ease_factor + 0.05)
        # Adjust difficulty down slightly
        progress.difficulty = max(0.1, progress.difficulty - 0.02)
    else:
        # Failed recall: decrease half-life
        progress.half_life = max(0.5, progress.half_life * 0.5)
        progress.ease_factor = max(1.3, progress.ease_factor - 0.15)
        # Adjust difficulty up
        progress.difficulty = min(0.9, progress.difficulty + 0.05)

    # Response time adjustment: very fast correct = well-known
    if correct and response_time_ms < 2000:
        progress.half_life *= 1.1  # Slight boost for fast recall

    progress.last_reviewed = now()
    progress.review_count += 1
    return progress

def next_review_date(progress):
    """Calculate when to next review this item."""
    # Target recall rate: 85% (review when predicted recall drops to 85%)
    target_recall = 0.85
    interval_days = -progress.half_life * log2(target_recall)
    return progress.last_reviewed + timedelta(days=interval_days)
```

## Consequences

### Positive

- Full control over scheduling behavior
- Modality-specific intervals (recognition drills spaced wider than production drills)
- Error-type data feeds back into scheduling (specific weakness targeting)
- Parameters can be optimized from Aelu's own data (see `srs-optimization.md`)
- No external dependencies for core scheduling logic

### Negative

- **Must maintain own scheduling code.** No community to report and fix bugs. No academic validation of the specific parameter choices.
- **Risk of miscalibration.** If parameters are wrong, users review too early (wasting time) or too late (forgetting). Mitigated by calibration monitoring (see `srs-optimization.md`).
- **No community benchmarks.** Can't compare Aelu's scheduling quality against Anki or FSRS benchmarks without significant analysis effort.

### Neutral

- The algorithm is simple enough to rewrite in any language if needed (porting from Python to Rust, for example, would be trivial)
- Parameter optimization is a separate concern from the core algorithm (see `srs-optimization.md`)

## Revisit Triggers

1. **User complaints about scheduling quality** — items reviewed too often or not often enough
2. **Academic research invalidates half-life regression** — unlikely, as it's well-established in memory science
3. **FSRS becomes an easy-to-integrate library** — if FSRS publishes a standalone Python package with clean API, consider adopting it to benefit from community optimization
4. **Calibration analysis** (see `srs-optimization.md`) shows significant prediction error that custom parameter tuning cannot resolve
