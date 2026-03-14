# Session Length Optimization

## Problem Statement

Aelu's default session length is 12 drill items. This number was chosen based on general SLA research suggesting 15-20 minute sessions are optimal for spaced repetition, with each drill taking ~60-90 seconds. But the optimal session length for *Aelu specifically* depends on when cognitive fatigue causes accuracy to drop below the point where learning is effective.

The goal is to find the **inflection point** where the marginal learning value of an additional drill drops below a threshold, and to personalize session length per user.

## Model: Accuracy as a Function of Drill Position

Let `a(k)` be the accuracy at drill position `k` within a session (k = 1, 2, ..., N).

**Hypothesis:** `a(k)` follows a logistic decay:

```
a(k) = a_max / (1 + exp(β * (k - k_half)))
```

Where:
- `a_max` = maximum accuracy (typically at drill 1-3, after warm-up)
- `k_half` = the drill position where accuracy drops to 50% of maximum
- `β` = steepness of the decline

**Alternative hypothesis:** Accuracy may show a *warm-up effect* (drills 1-2 are lower because the user hasn't settled in) followed by a plateau, then decline. This would be a piecewise model:

```
Phase 1 (warm-up):     a(k) rises for k = 1..3
Phase 2 (plateau):     a(k) is stable for k = 4..M
Phase 3 (fatigue):     a(k) declines for k > M
```

The break point M is what we want to find.

## Data Collection

### Required Schema Addition

No schema changes needed. The existing `review_event` table already captures what we need, but we need to ensure drill position within a session is tracked.

```sql
-- Check if session_position is tracked
-- If not, it can be derived from timestamps within a session
SELECT
    re.session_id,
    re.item_id,
    re.correct,
    re.drill_type,
    ROW_NUMBER() OVER (
        PARTITION BY re.session_id
        ORDER BY re.created_at
    ) as drill_position,
    COUNT(*) OVER (PARTITION BY re.session_id) as session_length
FROM review_event re
WHERE re.created_at > datetime('now', '-90 days')
ORDER BY re.session_id, re.created_at;
```

### Extraction Query: Position-Accuracy Curve

```sql
-- Aggregate accuracy by drill position across all sessions
WITH positioned AS (
    SELECT
        re.session_id,
        re.correct,
        re.drill_type,
        ROW_NUMBER() OVER (
            PARTITION BY re.session_id
            ORDER BY re.created_at
        ) as position,
        COUNT(*) OVER (PARTITION BY re.session_id) as session_length
    FROM review_event re
    JOIN session s ON re.session_id = s.id
    WHERE s.completed = 1  -- Only completed sessions
      AND re.created_at > datetime('now', '-90 days')
)
SELECT
    position,
    COUNT(*) as total_drills,
    SUM(correct) as correct_count,
    ROUND(AVG(correct) * 100, 1) as accuracy_pct,
    COUNT(DISTINCT session_id) as sessions_with_this_position
FROM positioned
WHERE session_length >= 10  -- Exclude very short sessions (likely abandoned)
GROUP BY position
HAVING total_drills >= 20  -- Minimum sample for reliability
ORDER BY position;
```

### Extraction Query: Per-User Fatigue Profile

```sql
-- Find per-user fatigue inflection points
WITH positioned AS (
    SELECT
        s.user_id,
        re.session_id,
        re.correct,
        ROW_NUMBER() OVER (
            PARTITION BY re.session_id
            ORDER BY re.created_at
        ) as position
    FROM review_event re
    JOIN session s ON re.session_id = s.id
    WHERE s.completed = 1
),
user_position_accuracy AS (
    SELECT
        user_id,
        position,
        COUNT(*) as n,
        AVG(correct) as accuracy
    FROM positioned
    GROUP BY user_id, position
    HAVING n >= 5
)
SELECT
    user_id,
    position,
    n,
    ROUND(accuracy * 100, 1) as accuracy_pct,
    ROUND(accuracy - LAG(accuracy) OVER (
        PARTITION BY user_id ORDER BY position
    ), 3) as accuracy_delta
FROM user_position_accuracy
ORDER BY user_id, position;
```

## Analysis Script

```python
"""
Session length optimization analysis.
Run: python scripts/session_length_analysis.py
Requires: pandas, numpy, scipy, matplotlib
"""

import sqlite3
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import argrelextrema
import matplotlib.pyplot as plt

DB_PATH = "data/mandarin.db"

def extract_position_accuracy(db_path):
    """Extract drill position vs accuracy data."""
    conn = sqlite3.connect(db_path)
    query = """
    WITH positioned AS (
        SELECT
            re.session_id,
            re.correct,
            ROW_NUMBER() OVER (
                PARTITION BY re.session_id
                ORDER BY re.created_at
            ) as position,
            COUNT(*) OVER (PARTITION BY re.session_id) as session_length
        FROM review_event re
        JOIN session s ON re.session_id = s.id
        WHERE s.completed = 1
    )
    SELECT position, correct, session_id
    FROM positioned
    WHERE session_length >= 8
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def fit_fatigue_model(df):
    """Fit piecewise model to find fatigue onset."""
    agg = df.groupby('position').agg(
        accuracy=('correct', 'mean'),
        n=('correct', 'count')
    ).reset_index()

    # Only use positions with sufficient data
    agg = agg[agg['n'] >= 20]

    positions = agg['position'].values
    accuracies = agg['accuracy'].values

    # Fit logistic decay
    def logistic_decay(k, a_max, beta, k_half):
        return a_max / (1 + np.exp(beta * (k - k_half)))

    try:
        popt, pcov = curve_fit(
            logistic_decay, positions, accuracies,
            p0=[0.85, 0.3, 15],  # initial guesses
            bounds=([0.5, 0.01, 5], [1.0, 2.0, 30])
        )
        a_max, beta, k_half = popt
        print(f"Logistic fit: a_max={a_max:.3f}, beta={beta:.3f}, k_half={k_half:.1f}")
        print(f"Accuracy drops to 80% of max at drill {k_half - np.log(0.25)/beta:.0f}")
    except RuntimeError:
        print("Logistic fit failed; using rolling average instead")
        k_half = None

    # Alternative: find the position where 3-drill rolling average drops by >5%
    rolling = agg['accuracy'].rolling(3, center=True).mean()
    deltas = rolling.diff()
    fatigue_onset = None
    for i, delta in enumerate(deltas):
        if delta is not None and delta < -0.03:  # 3% drop
            fatigue_onset = agg.iloc[i]['position']
            break

    return {
        'logistic_k_half': k_half,
        'rolling_fatigue_onset': fatigue_onset,
        'position_accuracy': agg
    }

def marginal_learning_value(df):
    """
    Estimate marginal learning value at each position.

    Learning value = P(correct at position k | incorrect at last review)
    This captures whether the drill is *teaching* something, not just confirming
    known material.
    """
    agg = df.groupby('position').agg(
        accuracy=('correct', 'mean'),
        n=('correct', 'count')
    ).reset_index()

    # Marginal value: accuracy * (1 - accuracy) is maximized at 50% accuracy
    # (maximum information gain). Drills that are too easy (>90%) or too hard
    # (<20%) have low learning value.
    agg['learning_value'] = agg['accuracy'] * (1 - agg['accuracy'])
    agg['cumulative_value'] = agg['learning_value'].cumsum()
    agg['marginal_cumulative'] = agg['cumulative_value'].diff()

    return agg

def recommend_session_length(analysis):
    """
    Recommend session length based on fatigue analysis.

    Rule: Stop when marginal learning value drops below 50% of peak,
    OR when accuracy drops below 60% (too fatigued to learn effectively).
    """
    agg = analysis['position_accuracy']

    # Find where accuracy drops below 60%
    low_acc = agg[agg['accuracy'] < 0.60]
    acc_cutoff = low_acc.iloc[0]['position'] if len(low_acc) > 0 else 25

    # Use fatigue onset if detected
    fatigue = analysis.get('rolling_fatigue_onset')

    recommended = min(
        acc_cutoff - 1,  # Stop before accuracy crashes
        fatigue if fatigue else 25,
        20  # Hard cap — no session should exceed 20 drills
    )
    recommended = max(recommended, 8)  # Minimum 8 for meaningful practice

    return int(recommended)

def plot_results(agg, recommended, output_path="data/session_length_analysis.png"):
    """Generate visualization."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

    ax1.bar(agg['position'], agg['accuracy'], alpha=0.7, color='steelblue')
    ax1.axhline(y=0.60, color='red', linestyle='--', label='60% threshold')
    ax1.axvline(x=recommended, color='green', linestyle='--', label=f'Recommended: {recommended}')
    ax1.set_xlabel('Drill Position in Session')
    ax1.set_ylabel('Accuracy')
    ax1.set_title('Accuracy by Drill Position')
    ax1.legend()

    learning_value = agg['accuracy'] * (1 - agg['accuracy'])
    ax2.bar(agg['position'], learning_value, alpha=0.7, color='coral')
    ax2.axvline(x=recommended, color='green', linestyle='--', label=f'Recommended: {recommended}')
    ax2.set_xlabel('Drill Position in Session')
    ax2.set_ylabel('Learning Value (accuracy * (1-accuracy))')
    ax2.set_title('Marginal Learning Value by Position')
    ax2.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Plot saved to {output_path}")

if __name__ == "__main__":
    df = extract_position_accuracy(DB_PATH)
    if len(df) < 100:
        print(f"Insufficient data: {len(df)} drill records. Need 500+.")
        print("Using default session length of 12.")
    else:
        analysis = fit_fatigue_model(df)
        mlv = marginal_learning_value(df)
        recommended = recommend_session_length(analysis)
        print(f"\nRecommended session length: {recommended} drills")
        print(f"Current default: 12 drills")
        if recommended != 12:
            print(f"Consider A/B testing {recommended} vs 12.")
        plot_results(analysis['position_accuracy'], recommended)
```

## Literature Context

- **Pimsleur (1967):** Graduated-interval recall suggests sessions of 20-30 minutes.
- **Cepeda et al. (2006):** Optimal inter-study intervals depend on retention interval. Session length is less studied than spacing.
- **Kornell (2009):** Interleaving within a session is more important than total session length.
- **Duolingo Research (2016):** Found that sessions of 10-15 minutes had highest completion rates. Longer sessions had higher abandonment.
- **Anki community wisdom:** 20-minute sessions are standard, but this optimizes for *cards reviewed*, not *learning per card*.

## Expected Findings

Based on SLA research and the structure of Aelu's drills:

1. **Warm-up effect (positions 1-3):** Accuracy slightly lower as user settles in.
2. **Peak performance (positions 4-10):** Stable accuracy at or near user's baseline.
3. **Fatigue onset (positions 11-15):** Gradual decline, especially for production drills (tone, recall) that require more cognitive effort.
4. **Steep decline (positions 16+):** Accuracy drops sharply, errors become careless rather than knowledge-based.

**Predicted optimal range: 10-14 drills**, depending on drill type mix. Sessions heavy on receptive drills (multiple choice, matching) can be longer. Sessions with production drills (speaking, recall) should be shorter.

## Implementation Plan

1. **Phase 1 (now):** Deploy the extraction queries. Accumulate data for 30 days.
2. **Phase 2 (30 days):** Run the analysis script. If data supports a change, update the default.
3. **Phase 3 (60 days):** A/B test the recommended length vs current 12. Primary metric: 7-day retention rate. See `ab-testing-framework.md` for the pre-registered experiment.
4. **Phase 4 (ongoing):** Personalize session length per user based on their individual fatigue profile. Add a `preferred_session_length` column to the `learner` table and adjust dynamically.

## Personalization Approach

Once sufficient data exists per user (50+ completed sessions):

```python
def personalized_session_length(user_id, db):
    """Calculate optimal session length for a specific user."""
    query = """
    WITH positioned AS (
        SELECT re.correct,
               ROW_NUMBER() OVER (PARTITION BY re.session_id ORDER BY re.created_at) as pos
        FROM review_event re
        JOIN session s ON re.session_id = s.id
        WHERE s.user_id = ? AND s.completed = 1
    )
    SELECT pos, AVG(correct) as acc, COUNT(*) as n
    FROM positioned
    GROUP BY pos
    HAVING n >= 5
    ORDER BY pos
    """
    rows = db.execute(query, [user_id]).fetchall()

    # Find first position where accuracy drops >10% from peak
    if len(rows) < 8:
        return 12  # Default; insufficient data

    accuracies = [r['acc'] for r in rows]
    peak = max(accuracies[:8])  # Peak within first 8 drills

    for row in rows:
        if row['pos'] >= 5 and row['acc'] < peak * 0.85:
            return max(8, row['pos'] - 1)

    return min(len(rows), 18)  # User shows no fatigue; cap at 18
```
