# SRS Parameter Optimization

## Current Parameters

Aelu's SRS engine uses FSRS-inspired half-life regression with these defaults:

| Parameter        | Default Value | Source                    |
|------------------|---------------|---------------------------|
| `half_life_days` | 1.0           | Conservative default      |
| `difficulty`     | 0.5           | Midpoint of [0, 1] scale  |
| `ease_factor`    | 2.5           | SM-2 default              |

The scheduling formula determines when to next review an item:

```
predicted_recall = 2^(-elapsed_days / half_life_days)
next_interval = half_life_days * ease_factor * (1 - difficulty)
```

If `predicted_recall` at review time is close to `actual_recall` (measured as binary correct/incorrect across many reviews), the parameters are well-calibrated. If not, we need to optimize.

## Problem Statement

The parameters were set from literature defaults, not from Aelu user data. As data accumulates, we should:

1. **Measure calibration**: Is `predicted_recall` close to `actual_recall`?
2. **Optimize parameters**: Find values that minimize prediction error.
3. **Personalize**: Allow per-user parameter tuning.

## Data Extraction

### Predicted vs Actual Recall Pairs

```sql
-- Extract (predicted_recall, actual_correct) pairs
-- Each row is one review event with the prediction that was made at scheduling time
SELECT
    re.id as review_id,
    re.item_id,
    re.correct as actual_correct,
    re.created_at as review_time,
    p.half_life_days,
    p.difficulty,
    p.ease_factor,
    p.last_reviewed,
    -- Calculate elapsed time since last review
    CAST(
        (julianday(re.created_at) - julianday(p.last_reviewed)) AS REAL
    ) as elapsed_days,
    -- Calculate what the predicted recall was
    POWER(2.0, -(
        (julianday(re.created_at) - julianday(p.last_reviewed))
        / p.half_life_days
    )) as predicted_recall
FROM review_event re
JOIN progress p ON re.item_id = p.item_id AND re.user_id = p.user_id
WHERE p.last_reviewed IS NOT NULL
  AND p.half_life_days > 0
  AND re.created_at > datetime('now', '-180 days')
ORDER BY re.created_at;
```

### Calibration Check

```sql
-- Group predictions into bins and compare with actual accuracy
WITH recall_pairs AS (
    SELECT
        re.correct as actual,
        POWER(2.0, -(
            (julianday(re.created_at) - julianday(p.last_reviewed))
            / p.half_life_days
        )) as predicted
    FROM review_event re
    JOIN progress p ON re.item_id = p.item_id AND re.user_id = p.user_id
    WHERE p.last_reviewed IS NOT NULL AND p.half_life_days > 0
)
SELECT
    CASE
        WHEN predicted >= 0.9 THEN '0.90-1.00'
        WHEN predicted >= 0.8 THEN '0.80-0.89'
        WHEN predicted >= 0.7 THEN '0.70-0.79'
        WHEN predicted >= 0.6 THEN '0.60-0.69'
        WHEN predicted >= 0.5 THEN '0.50-0.59'
        WHEN predicted >= 0.4 THEN '0.40-0.49'
        WHEN predicted >= 0.3 THEN '0.30-0.39'
        ELSE '0.00-0.29'
    END as predicted_bin,
    COUNT(*) as n,
    ROUND(AVG(actual) * 100, 1) as actual_accuracy_pct,
    ROUND(AVG(predicted) * 100, 1) as avg_predicted_pct
FROM recall_pairs
GROUP BY predicted_bin
ORDER BY predicted_bin DESC;
```

**Good calibration** means each bin's `actual_accuracy_pct` is close to `avg_predicted_pct`. Example:
- Predicted 0.80-0.89 → Actual 82% (good)
- Predicted 0.80-0.89 → Actual 65% (model overestimates retention)

## Optimization Method

### Loss Function

Binary cross-entropy between predicted recall and actual outcome:

```
L = -1/N * SUM[ y_i * log(p_i) + (1 - y_i) * log(1 - p_i) ]
```

Where:
- `y_i` = 1 if correct, 0 if incorrect
- `p_i` = predicted recall for that review

Lower is better. Perfect calibration minimizes this loss.

### Grid Search

Search space:

| Parameter        | Values                          | Rationale                      |
|------------------|---------------------------------|--------------------------------|
| `half_life_days` | [0.25, 0.5, 1.0, 2.0, 4.0]    | Initial forgetting rate        |
| `difficulty`     | [0.3, 0.5, 0.7]                | Item inherent difficulty       |
| `ease_factor`    | [1.5, 1.8, 2.0, 2.5, 3.0, 3.5]| Interval growth multiplier    |

Total combinations: 5 x 3 x 6 = 90 parameter sets.

**Sample size requirement:** Minimum 500 review events total for global optimization. For per-item or per-user optimization, need 30+ reviews per item/user.

### Optimization Script

```python
"""
SRS parameter optimization via grid search.
Run: python scripts/srs_optimize.py
Requires: numpy, pandas, scipy
"""

import sqlite3
import numpy as np
import pandas as pd
from itertools import product

DB_PATH = "data/mandarin.db"

def extract_review_data(db_path):
    """Extract review events with timing data."""
    conn = sqlite3.connect(db_path)
    query = """
    SELECT
        re.item_id,
        re.user_id,
        re.correct,
        julianday(re.created_at) - julianday(p.last_reviewed) as elapsed_days,
        p.review_count
    FROM review_event re
    JOIN progress p ON re.item_id = p.item_id AND re.user_id = p.user_id
    WHERE p.last_reviewed IS NOT NULL
      AND p.half_life_days > 0
      AND julianday(re.created_at) > julianday(p.last_reviewed)
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df = df.dropna(subset=['elapsed_days'])
    df = df[df['elapsed_days'] > 0]
    return df

def predicted_recall(elapsed_days, half_life):
    """Exponential forgetting curve."""
    return np.power(2.0, -elapsed_days / half_life)

def cross_entropy_loss(y_true, y_pred):
    """Binary cross-entropy. Clip to avoid log(0)."""
    y_pred = np.clip(y_pred, 1e-7, 1 - 1e-7)
    return -np.mean(
        y_true * np.log(y_pred) + (1 - y_true) * np.log(1 - y_pred)
    )

def grid_search(df):
    """Find optimal parameters via grid search."""
    half_lives = [0.25, 0.5, 1.0, 2.0, 4.0]
    difficulties = [0.3, 0.5, 0.7]
    ease_factors = [1.5, 1.8, 2.0, 2.5, 3.0, 3.5]

    y_true = df['correct'].values
    elapsed = df['elapsed_days'].values

    best_loss = float('inf')
    best_params = None
    results = []

    for hl, diff, ef in product(half_lives, difficulties, ease_factors):
        # Effective half-life adjusted by difficulty and review count
        effective_hl = hl * ef * (1 - diff)
        if effective_hl <= 0:
            continue

        y_pred = predicted_recall(elapsed, effective_hl)
        loss = cross_entropy_loss(y_true, y_pred)

        results.append({
            'half_life': hl,
            'difficulty': diff,
            'ease_factor': ef,
            'effective_hl': effective_hl,
            'loss': loss,
            'mean_predicted': np.mean(y_pred),
            'mean_actual': np.mean(y_true)
        })

        if loss < best_loss:
            best_loss = loss
            best_params = (hl, diff, ef)

    results_df = pd.DataFrame(results).sort_values('loss')
    return best_params, best_loss, results_df

def calibration_report(df, half_life, difficulty, ease_factor):
    """Generate calibration report for given parameters."""
    effective_hl = half_life * ease_factor * (1 - difficulty)
    y_pred = predicted_recall(df['elapsed_days'].values, effective_hl)
    y_true = df['correct'].values

    bins = [0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    indices = np.digitize(y_pred, bins)

    print("\nCalibration Report:")
    print(f"Parameters: half_life={half_life}, difficulty={difficulty}, ease_factor={ease_factor}")
    print(f"Effective half-life: {effective_hl:.2f} days")
    print(f"\n{'Predicted Bin':<15} {'N':>6} {'Actual %':>10} {'Predicted %':>12} {'Gap':>8}")
    print("-" * 55)

    for i in range(1, len(bins)):
        mask = indices == i
        if mask.sum() == 0:
            continue
        actual_pct = y_true[mask].mean() * 100
        pred_pct = y_pred[mask].mean() * 100
        gap = actual_pct - pred_pct
        bin_label = f"{bins[i-1]:.1f}-{bins[i]:.1f}"
        print(f"{bin_label:<15} {mask.sum():>6} {actual_pct:>9.1f}% {pred_pct:>11.1f}% {gap:>+7.1f}%")

def continuous_optimization(df):
    """
    Refine parameters using scipy.optimize after grid search
    identifies the promising region.
    """
    from scipy.optimize import minimize

    y_true = df['correct'].values
    elapsed = df['elapsed_days'].values

    def objective(params):
        hl, diff, ef = params
        effective_hl = hl * ef * (1 - diff)
        if effective_hl <= 0.01:
            return 100.0  # Penalty for invalid params
        y_pred = predicted_recall(elapsed, effective_hl)
        return cross_entropy_loss(y_true, y_pred)

    # Start from grid search best
    best_grid, _, _ = grid_search(df)
    result = minimize(
        objective,
        x0=best_grid,
        method='Nelder-Mead',
        bounds=[(0.1, 10.0), (0.1, 0.9), (1.0, 5.0)]
    )

    if result.success:
        print(f"\nOptimized parameters: half_life={result.x[0]:.3f}, "
              f"difficulty={result.x[1]:.3f}, ease_factor={result.x[2]:.3f}")
        print(f"Loss: {result.fun:.6f}")
    return result

if __name__ == "__main__":
    df = extract_review_data(DB_PATH)
    print(f"Loaded {len(df)} review events")

    if len(df) < 500:
        print(f"Insufficient data ({len(df)} events). Need 500+ for reliable optimization.")
        print("Keeping default parameters.")
    else:
        best_params, best_loss, results_df = grid_search(df)
        print(f"\nBest parameters: half_life={best_params[0]}, "
              f"difficulty={best_params[1]}, ease_factor={best_params[2]}")
        print(f"Best loss: {best_loss:.6f}")

        print("\nTop 10 parameter combinations:")
        print(results_df.head(10).to_string(index=False))

        calibration_report(df, *best_params)

        print("\nRunning continuous optimization...")
        continuous_optimization(df)
```

## Per-Item Difficulty Estimation

Beyond global parameters, each vocabulary item has its own intrinsic difficulty. After 30+ reviews of an item across users, we can estimate item-specific difficulty:

```sql
-- Item-level difficulty estimation
SELECT
    p.item_id,
    vi.hanzi,
    vi.english,
    vi.hsk_level,
    COUNT(*) as total_reviews,
    ROUND(AVG(re.correct) * 100, 1) as accuracy_pct,
    -- Empirical difficulty: 1 - accuracy (higher = harder)
    ROUND(1 - AVG(re.correct), 3) as empirical_difficulty,
    -- Current assigned difficulty
    AVG(p.difficulty) as assigned_difficulty,
    -- Gap between empirical and assigned
    ROUND((1 - AVG(re.correct)) - AVG(p.difficulty), 3) as difficulty_gap
FROM review_event re
JOIN progress p ON re.item_id = p.item_id AND re.user_id = p.user_id
JOIN vocab_item vi ON re.item_id = vi.id
GROUP BY p.item_id
HAVING total_reviews >= 30
ORDER BY ABS(difficulty_gap) DESC
LIMIT 50;
```

Items with large `difficulty_gap` are miscalibrated: the SRS is scheduling them as if they're easier or harder than they actually are.

## Modality-Specific Parameters

Different drill types have different accuracy profiles. Tone production drills are harder than character recognition. The SRS should account for this:

```sql
-- Accuracy by drill type
SELECT
    re.drill_type,
    COUNT(*) as n,
    ROUND(AVG(re.correct) * 100, 1) as accuracy_pct
FROM review_event re
GROUP BY re.drill_type
ORDER BY accuracy_pct;
```

**Proposal:** Maintain separate difficulty modifiers per drill type. If tone_production accuracy is 15% lower than character_recognition, apply a +0.15 difficulty adjustment when scheduling tone drills.

## Implementation Roadmap

1. **Milestone 1 (500 review events):** Run calibration check. Report predicted vs actual accuracy by bin. If calibration gap > 5% in any bin, proceed to optimization.
2. **Milestone 2 (2,000 review events):** Run global grid search. Update default parameters if improvement > 3% in cross-entropy loss.
3. **Milestone 3 (5,000 review events):** Run per-item difficulty estimation. Update items with >30 reviews to use empirical difficulty.
4. **Milestone 4 (10,000+ review events):** Per-user parameter optimization. Each user gets personalized ease_factor based on their review history.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Overfitting to small dataset | Require minimum 500 events; use cross-validation |
| Parameter instability over time | Re-run optimization monthly; track drift |
| User behavior change after parameter update | Use A/B test for any parameter change (see ab-testing-framework.md) |
| Difficulty estimates biased by drill type mix | Stratify analysis by drill type |
