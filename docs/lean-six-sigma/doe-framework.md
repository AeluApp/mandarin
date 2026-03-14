# Design of Experiments (DoE) Framework — Aelu

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Experimentation Infrastructure:** `feature_flag` table + deterministic rollout

---

## 1. Hypothesis Template

Every experiment at Aelu follows this structure:

> **If** we change **[independent variable]**,
> **then** **[dependent variable]** will improve by **[magnitude]%**
> **for** **[target segment]**,
> **measured by** **[metric + query]**,
> **over** **[time period]**.

---

## 2. Experimentation Infrastructure

### 2.1 Feature Flag Table (Randomization Mechanism)

The `feature_flag` table provides the randomization mechanism for A/B tests:

```sql
CREATE TABLE IF NOT EXISTS feature_flag (
    name TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    rollout_pct INTEGER DEFAULT 100,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

**Randomization method:** Deterministic hashing. For a given `(flag_name, user_id)`, the assignment is computed as:

```python
bucket = int(hashlib.sha256(f"{flag_name}:{user_id}".encode()).hexdigest()[:8], 16) % 100
in_treatment = bucket < rollout_pct
```

This ensures:
- **Deterministic:** Same user always gets the same assignment for a given flag
- **Uniform:** SHA-256 distribution is effectively uniform across buckets
- **Independent:** Different flags produce different assignments for the same user
- **Reproducible:** No random seed to track; assignment is a pure function of inputs

### 2.2 Flag Management API

```python
from mandarin.feature_flags import set_flag, is_enabled, get_all_flags

# Create experiment
set_flag(conn, "exp_session_length_15", enabled=True, rollout_pct=50,
         description="Test 15-item sessions vs 12-item default")

# Check assignment
if is_enabled(conn, "exp_session_length_15", user_id=user.id):
    session_length = 15  # Treatment
else:
    session_length = 12  # Control

# List all flags
flags = get_all_flags(conn)
```

### 2.3 Experiment Logging

All review events and session logs include the user_id, which can be joined with feature flag assignments to segment results:

```sql
-- Segment session data by experiment assignment
SELECT
    CASE WHEN (CAST('0x' || SUBSTR(HEX(ZEROBLOB(32)), 1, 8) AS INTEGER) % 100) < ff.rollout_pct
         THEN 'treatment' ELSE 'control' END AS variant,
    AVG(1.0 * sl.items_completed / NULLIF(sl.items_planned, 0)) AS completion_rate,
    COUNT(*) AS sessions
FROM session_log sl
CROSS JOIN feature_flag ff
WHERE ff.name = 'exp_session_length_15'
    AND sl.started_at >= '2026-03-01'
GROUP BY variant;
```

Note: The actual assignment uses Python's `hashlib.sha256`, not SQLite's `HEX`. For analysis, either:
1. Compute assignments in Python and join, or
2. Add a `user_experiment_assignment` table for direct SQL analysis.

---

## 3. Statistical Requirements

### 3.1 Significance Threshold
- **p-value:** < 0.05 (two-tailed)
- **Confidence level:** 95%
- **Multiple comparison correction:** Bonferroni when running > 2 simultaneous experiments

### 3.2 Minimum Sample Size
- **Minimum observations per variant:** 30 (for central limit theorem to apply)
- **Recommended observations per variant:** 100+ for effect sizes < 10%
- **Practical minimum:** At current scale (< 10 users), formal A/B testing requires patience. With 1 active user doing 4 sessions/week, it takes ~8 weeks to accumulate 30 sessions per variant with a 50/50 split.

### 3.3 Sample Size Calculator

For a given desired effect size and baseline:

```python
import math

def min_sample_size(baseline_rate: float, effect_size_pct: float,
                    alpha: float = 0.05, power: float = 0.80) -> int:
    """Minimum observations per variant for a two-proportion z-test.

    baseline_rate: current metric (e.g., 0.70 for 70% completion)
    effect_size_pct: relative improvement to detect (e.g., 10 for 10%)
    """
    p1 = baseline_rate
    p2 = baseline_rate * (1 + effect_size_pct / 100)
    p_bar = (p1 + p2) / 2

    # z-scores for alpha/2 and power
    z_alpha = 1.96  # 95% confidence
    z_beta = 0.84   # 80% power

    numerator = (z_alpha * math.sqrt(2 * p_bar * (1 - p_bar)) +
                 z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    denominator = (p2 - p1) ** 2

    return math.ceil(numerator / denominator)

# Examples:
# Detect 10% relative improvement in 70% completion rate:
# min_sample_size(0.70, 10) → ~356 per variant
# Detect 20% relative improvement: ~95 per variant
# Detect 30% relative improvement: ~45 per variant
```

### 3.4 Practical Implications for Aelu

| Users | Sessions/week (total) | Time to 30 sessions/variant (50/50) | Time to 100 sessions/variant |
|-------|----------------------|-------------------------------------|------------------------------|
| 1 | 4 | 15 weeks | 50 weeks |
| 10 | 40 | 2 weeks | 5 weeks |
| 100 | 400 | 1-2 days | 4 days |
| 1,000 | 4,000 | < 1 day | < 1 day |

**Pre-PMF reality:** With < 10 users, formal A/B tests are impractical for small effect sizes. Instead:
- Use **sequential testing** (monitor as data accumulates, stop early if effect is large)
- Use **before/after comparisons** for the single primary user (weaker evidence but available now)
- Reserve formal A/B tests for post-PMF (100+ users)

---

## 4. Experiment Designs

### Experiment A: Session Length

**Hypothesis:** If we increase session length from 12 to 15 items, then session completion rate will decrease by no more than 5%, but weekly items reviewed will increase by 20%, for self-study adult learners, measured by `session_log.items_completed / items_planned` and weekly `SUM(items_completed)`, over 4 weeks.

| Parameter | Value |
|-----------|-------|
| Flag name | `exp_session_length` |
| Variants | Control: 12 items, Treatment A: 15 items, Treatment B: 20 items |
| Rollout | 33/33/34 split (use 3 flags with non-overlapping bucket ranges) |
| Primary metric | Session completion rate |
| Secondary metric | Weekly items reviewed, accuracy rate |
| Guard metric | Early exit rate (must not increase > 10 percentage points) |
| Duration | 4 weeks minimum |
| Minimum N | 30 sessions per variant |

**Implementation:**
```python
# In scheduler.py, get_day_profile() or plan_session()
if is_enabled(conn, "exp_session_length_15", user_id):
    target_length = 15
elif is_enabled(conn, "exp_session_length_20", user_id):
    target_length = 20
else:
    target_length = profile.get("preferred_session_length", 12)
```

**Analysis query:**
```sql
SELECT
    CASE
        WHEN sl.items_planned BETWEEN 14 AND 16 THEN '15-item'
        WHEN sl.items_planned BETWEEN 19 AND 21 THEN '20-item'
        ELSE '12-item (control)'
    END AS variant,
    COUNT(*) AS sessions,
    AVG(1.0 * items_completed / NULLIF(items_planned, 0)) AS avg_completion,
    AVG(items_completed) AS avg_items_done,
    SUM(CASE WHEN early_exit = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS early_exit_pct,
    AVG(1.0 * items_correct / NULLIF(items_completed, 0)) AS avg_accuracy
FROM session_log sl
WHERE sl.started_at >= :experiment_start
    AND sl.user_id = :user_id
GROUP BY variant;
```

---

### Experiment B: Interleaving Ratio

**Hypothesis:** If we switch from strict modality interleaving (no same-modality back-to-back) to blocked practice (3-4 items of same modality, then switch), then short-term accuracy will increase by 10% but long-term retention (7-day recall) will decrease by 15%, for HSK 1-3 learners, measured by `review_event.correct` rate and 7-day recall rate, over 6 weeks.

| Parameter | Value |
|-----------|-------|
| Flag name | `exp_blocked_practice` |
| Variants | Control: strict interleaving (current), Treatment: blocked (3-4 same modality) |
| Rollout | 50/50 |
| Primary metric | 7-day recall rate (items reviewed 7+ days after last review) |
| Secondary metric | Within-session accuracy, user-reported difficulty |
| Guard metric | Session completion rate (must not drop > 10pp) |
| Duration | 6 weeks minimum (need 7-day recall data) |
| Minimum N | 50 sessions per variant (need enough items for recall analysis) |

**SLA research context:** Interleaving is well-established to improve long-term retention at the cost of short-term performance. This experiment validates whether the effect holds for Aelu's specific drill types and user population.

**Implementation:**
```python
# In scheduler.py, apply_interleaving()
if is_enabled(conn, "exp_blocked_practice", user_id):
    # Group items by modality, deliver in blocks of 3-4
    planned = _group_by_modality(planned, block_size=3)
else:
    # Current behavior: enforce modality switching
    planned = _apply_interleaving_constraints(planned)
```

**Analysis query:**
```sql
-- 7-day recall rate by variant
WITH recall_data AS (
    SELECT
        re.user_id,
        re.content_item_id,
        re.correct,
        julianday(re.created_at) - julianday(
            (SELECT MAX(re2.created_at) FROM review_event re2
             WHERE re2.content_item_id = re.content_item_id
               AND re2.user_id = re.user_id
               AND re2.created_at < re.created_at)
        ) AS days_since_last
    FROM review_event re
    WHERE re.created_at >= :experiment_start
)
SELECT
    -- Variant assignment computed in Python, joined here
    ROUND(AVG(CASE WHEN correct = 1 THEN 1.0 ELSE 0.0 END), 3) AS recall_rate,
    COUNT(*) AS reviews
FROM recall_data
WHERE days_since_last BETWEEN 6 AND 8  -- 7-day window
GROUP BY user_id;
```

---

### Experiment C: Context Notes Visibility

**Hypothesis:** If we show context notes (etymology, usage tips, cultural context) during drill feedback for incorrect answers, then repeat error rate on those items will decrease by 25%, for all learners, measured by `error_focus.error_count` growth rate, over 4 weeks.

| Parameter | Value |
|-----------|-------|
| Flag name | `exp_context_notes_feedback` |
| Variants | Control: context notes shown only in reader/review, Treatment: context notes shown in drill feedback on incorrect answers |
| Rollout | 50/50 |
| Primary metric | Repeat error rate (same item + same error_type within 14 days) |
| Secondary metric | Error focus resolution rate (consecutive_correct reaching threshold faster) |
| Guard metric | Session duration (must not increase > 30s per session due to reading notes) |
| Duration | 4 weeks |
| Minimum N | 50 incorrect answers per variant |

**Implementation:**
```python
# In drills/base.py or runner.py, post-grading feedback
if not result.correct and is_enabled(conn, "exp_context_notes_feedback", user_id):
    note = item.get("context_note")
    if note:
        show_fn(f"\n  [dim]{note}[/dim]")
```

**Analysis query:**
```sql
-- Repeat error rate: how often does the same item + error_type recur within 14 days?
WITH error_pairs AS (
    SELECT
        e1.content_item_id,
        e1.error_type,
        e1.created_at AS first_error,
        MIN(e2.created_at) AS next_error
    FROM error_log e1
    LEFT JOIN error_log e2
        ON e2.content_item_id = e1.content_item_id
        AND e2.error_type = e1.error_type
        AND e2.user_id = e1.user_id
        AND e2.created_at > e1.created_at
        AND julianday(e2.created_at) - julianday(e1.created_at) <= 14
    WHERE e1.user_id = :user_id
        AND e1.created_at >= :experiment_start
    GROUP BY e1.id
)
SELECT
    COUNT(CASE WHEN next_error IS NOT NULL THEN 1 END) * 100.0 / COUNT(*) AS repeat_error_pct,
    COUNT(*) AS total_errors
FROM error_pairs;
```

---

## 5. Experiment Lifecycle

### 5.1 Pre-Experiment Checklist

- [ ] Hypothesis documented with specific metric, magnitude, and timeframe
- [ ] Feature flag created with `set_flag()`
- [ ] Minimum sample size calculated
- [ ] Guard metrics defined (what would cause early termination)
- [ ] Analysis queries written and tested on historical data
- [ ] No interaction with other running experiments (check `get_all_flags()`)

### 5.2 During Experiment

- [ ] Monitor guard metrics daily
- [ ] Do not change the feature flag rollout percentage mid-experiment
- [ ] Do not deploy code changes that affect the measured metric
- [ ] Log any anomalies (server outages, content changes) that could confound results

### 5.3 Post-Experiment

- [ ] Run analysis queries
- [ ] Compute p-value and confidence interval
- [ ] Document results (including null results — they're informative)
- [ ] Decision: roll out to 100%, roll back to 0%, or extend experiment
- [ ] Update feature flag accordingly
- [ ] Archive experiment documentation

### 5.4 Early Stopping Rules

Stop the experiment early if:
1. **Guard metric violation:** Any guard metric crosses its threshold → roll back immediately
2. **Overwhelming effect:** p < 0.001 with > 20% effect size before target N reached → consider early rollout
3. **Implementation bug:** Treatment group experiences errors caused by the experiment code → roll back, fix, restart

---

## 6. Experiment Registry

| ID | Flag Name | Status | Start | End | Result |
|----|-----------|--------|-------|-----|--------|
| A1 | `exp_session_length_15` | Planned | — | — | — |
| A2 | `exp_session_length_20` | Planned | — | — | — |
| B1 | `exp_blocked_practice` | Planned | — | — | — |
| C1 | `exp_context_notes_feedback` | Planned | — | — | — |

---

## 7. Limitations and Honest Assessment

1. **Current sample size is N=1.** No experiment can reach statistical significance with a single user. All pre-PMF "experiments" are really structured before/after observations on a single user. Document them honestly as such.

2. **No randomization with N=1.** Feature flags provide the mechanism, but with one user, they're just toggles. True randomization requires multiple users.

3. **Carryover effects.** With a single user, switching from treatment to control (or vice versa) means the user carries learning effects from the prior condition. This confounds comparison.

4. **Value of the framework now:** The purpose of building this infrastructure pre-PMF is to be ready when users arrive. The flag system, analysis queries, and experiment templates will work immediately at N=10, N=100, N=1000. Building them now means the first real experiment can launch on day 1 of user growth.
