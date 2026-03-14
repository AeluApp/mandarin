# A/B Testing Statistical Framework

## Principles

1. **Pre-register everything.** Decide hypothesis, metric, sample size, and duration *before* looking at data.
2. **One primary metric per experiment.** Secondary metrics are exploratory, not confirmatory.
3. **No peeking without alpha spending.** Early stopping must use O'Brien-Fleming bounds to control false positive rate.
4. **Ship or kill.** Every experiment ends with a decision: roll out to 100% or revert. No indefinite experiments.

## Randomization

Assignment uses deterministic hashing to ensure:
- Users always see the same variant (no flickering)
- No database lookup required at runtime
- Reproducible for debugging

```python
import hashlib

def get_variant(user_id: int, experiment_name: str, rollout_pct: int = 50) -> str:
    """
    Deterministic assignment to A/B variant.

    Returns 'control' or 'treatment' based on SHA256 hash of user_id + experiment_name.
    rollout_pct: percentage of users in treatment (0-100).
    """
    key = f"{user_id}|{experiment_name}"
    hash_val = int(hashlib.sha256(key.encode()).hexdigest(), 16)
    bucket = hash_val % 100

    if bucket < rollout_pct:
        return "treatment"
    return "control"
```

**Integration with feature flags:**

```sql
-- feature_flag table (already exists in schema)
-- experiment_name TEXT UNIQUE NOT NULL
-- rollout_pct INTEGER DEFAULT 0
-- is_active BOOLEAN DEFAULT 0
-- created_at DATETIME DEFAULT (datetime('now'))
-- ended_at DATETIME

SELECT rollout_pct FROM feature_flag
WHERE experiment_name = 'session_length_15' AND is_active = 1;
```

## Statistical Methods

### Binary Outcomes (e.g., retention, completion)

**Two-proportion z-test:**

```python
import numpy as np
from scipy import stats

def two_proportion_z_test(successes_a, n_a, successes_b, n_b):
    """
    Test whether treatment proportion differs from control.
    Returns z-statistic and two-sided p-value.
    """
    p_a = successes_a / n_a
    p_b = successes_b / n_b
    p_pool = (successes_a + successes_b) / (n_a + n_b)

    se = np.sqrt(p_pool * (1 - p_pool) * (1/n_a + 1/n_b))
    z = (p_b - p_a) / se
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    return {
        'control_rate': p_a,
        'treatment_rate': p_b,
        'absolute_lift': p_b - p_a,
        'relative_lift': (p_b - p_a) / p_a if p_a > 0 else None,
        'z_statistic': z,
        'p_value': p_value,
        'significant': p_value < 0.05
    }
```

### Continuous Outcomes (e.g., accuracy, session duration)

**Welch's t-test** (does not assume equal variances):

```python
def welch_t_test(values_a, values_b):
    """
    Test whether treatment mean differs from control.
    """
    t_stat, p_value = stats.ttest_ind(values_a, values_b, equal_var=False)
    return {
        'control_mean': np.mean(values_a),
        'treatment_mean': np.mean(values_b),
        'difference': np.mean(values_b) - np.mean(values_a),
        't_statistic': t_stat,
        'p_value': p_value,
        'significant': p_value < 0.05
    }
```

### Power Analysis & Sample Size

```python
def required_sample_size(baseline_rate, mde, alpha=0.05, power=0.80):
    """
    Calculate required sample size per group for a two-proportion test.

    baseline_rate: current conversion/retention rate
    mde: minimum detectable effect (absolute change, e.g., 0.05 for 5%)
    alpha: significance level
    power: 1 - beta (probability of detecting true effect)
    """
    p1 = baseline_rate
    p2 = baseline_rate + mde

    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)

    n = ((z_alpha * np.sqrt(2 * p1 * (1 - p1)) +
          z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) /
         (p2 - p1)) ** 2

    return int(np.ceil(n))
```

### Sequential Testing (Early Stopping)

Use **O'Brien-Fleming alpha spending** to allow periodic checks without inflating false positive rate:

```python
def obrien_fleming_boundary(total_looks, current_look, alpha=0.05):
    """
    Calculate the critical z-value for the current interim look
    using O'Brien-Fleming spending function.

    O'Brien-Fleming is conservative early (hard to stop early)
    and liberal late (easy to stop at the end).
    """
    info_fraction = current_look / total_looks

    # O'Brien-Fleming spending function
    # alpha_spent = 2 * (1 - Phi(z_alpha/2 / sqrt(info_fraction)))
    z_boundary = stats.norm.ppf(1 - alpha / 2) / np.sqrt(info_fraction)

    return z_boundary

# Example: 4 planned looks at 25%, 50%, 75%, 100% of sample
# Look 1 (25%): z > 4.05 needed to stop (very conservative)
# Look 2 (50%): z > 2.86 needed to stop
# Look 3 (75%): z > 2.34 needed to stop
# Look 4 (100%): z > 2.02 needed to stop (close to standard z)
```

### Multiple Comparison Correction

When running multiple experiments simultaneously, use **Benjamini-Hochberg FDR**:

```python
def benjamini_hochberg(p_values, fdr=0.05):
    """
    Benjamini-Hochberg procedure for controlling false discovery rate.
    Returns which hypotheses are rejected.
    """
    n = len(p_values)
    sorted_indices = np.argsort(p_values)
    sorted_pvals = np.array(p_values)[sorted_indices]

    thresholds = [(i + 1) / n * fdr for i in range(n)]

    rejected = [False] * n
    max_k = -1
    for k in range(n):
        if sorted_pvals[k] <= thresholds[k]:
            max_k = k

    if max_k >= 0:
        for k in range(max_k + 1):
            rejected[sorted_indices[k]] = True

    return rejected
```

---

## Pre-Registered Experiments

### Experiment A: Session Length (12 vs 15 Items)

| Field | Value |
|-------|-------|
| **Experiment Name** | `session_length_15` |
| **Hypothesis** | Increasing session length from 12 to 15 drills improves 7-day retention without increasing session abandonment |
| **Primary Metric** | 7-day retention rate (% of users who complete a session within 7 days of a given session) |
| **Secondary Metrics** | Session completion rate, average accuracy, session duration (minutes) |
| **Control** | 12 drills per session (current default) |
| **Treatment** | 15 drills per session |
| **Baseline Rate** | Estimated 7-day retention: 60% |
| **MDE** | 5% absolute improvement (60% -> 65%) |
| **Sample Size** | `required_sample_size(0.60, 0.05)` = **1,568 users per group** (3,136 total) |
| **Duration** | At 50 signups/month: ~63 months. At 200 signups/month: ~16 months. **Consider reducing MDE to 8% for faster results (n=614 per group).** |
| **Rollout** | 50% treatment |
| **Segments** | Analyze by HSK level (1-3 vs 4+), sessions per week (1-3 vs 4+) |
| **Guardrail Metrics** | Session abandonment rate must not increase by >5% absolute |
| **Decision Rule** | Ship if p < 0.05 and guardrail holds. Kill if p > 0.05 at full sample or guardrail violated. |

```sql
-- Extract data for Experiment A
WITH user_sessions AS (
    SELECT
        s.user_id,
        s.id as session_id,
        s.created_at,
        s.completed,
        COUNT(re.id) as drill_count,
        LEAD(s.created_at) OVER (PARTITION BY s.user_id ORDER BY s.created_at) as next_session_at
    FROM session s
    LEFT JOIN review_event re ON s.id = re.session_id
    WHERE s.created_at > '2026-03-01'  -- experiment start date
    GROUP BY s.id
)
SELECT
    us.user_id,
    CASE
        WHEN (abs(cast(hex(substr(us.user_id, 1, 4)) as integer)) % 100) < 50
        THEN 'control'
        ELSE 'treatment'
    END as variant,
    COUNT(DISTINCT us.session_id) as total_sessions,
    SUM(CASE WHEN us.next_session_at IS NOT NULL
         AND julianday(us.next_session_at) - julianday(us.created_at) <= 7
         THEN 1 ELSE 0 END) as retained_sessions,
    AVG(us.completed) as completion_rate
FROM user_sessions us
GROUP BY us.user_id;
```

### Experiment B: Audio Auto-Play (On vs Off)

| Field | Value |
|-------|-------|
| **Experiment Name** | `audio_autoplay` |
| **Hypothesis** | Auto-playing audio for each drill improves tone accuracy scores |
| **Primary Metric** | Average tone accuracy on tone-graded drills (0-100 scale) |
| **Secondary Metrics** | Session duration, user satisfaction (if surveyed), listening drill accuracy |
| **Control** | Audio plays only when user taps the speaker icon |
| **Treatment** | Audio auto-plays when each drill is presented |
| **Baseline** | Estimated mean tone accuracy: 65/100 |
| **MDE** | 5-point improvement (65 -> 70) |
| **Sample Size** | For continuous outcome with estimated SD=20: `n = 2 * ((z_alpha + z_beta) * SD / MDE)^2 = 2 * ((1.96 + 0.84) * 20 / 5)^2` = **502 users per group** |
| **Duration** | At 50 signups/month: ~20 months. Reduce to tone drill users only for faster convergence. |
| **Rollout** | 50% treatment |
| **Guardrail** | Session duration must not increase by >50% (audio adds time) |

### Experiment C: Context Notes Visibility

| Field | Value |
|-------|-------|
| **Experiment Name** | `context_notes_visible` |
| **Hypothesis** | Showing context notes by default (instead of behind a tap) improves session completion rate |
| **Primary Metric** | Session completion rate (% of started sessions that are completed) |
| **Secondary Metrics** | Average accuracy, time per drill, context note engagement rate |
| **Control** | Context notes hidden behind "Show context" button |
| **Treatment** | Context notes displayed automatically below each drill |
| **Baseline Rate** | Estimated session completion: 85% |
| **MDE** | 3% absolute improvement (85% -> 88%) |
| **Sample Size** | `required_sample_size(0.85, 0.03)` = **2,828 users per group**. Large because baseline is high and MDE is small. Consider raising MDE to 5% (n=1,020 per group). |
| **Duration** | Depends on signup rate. With MDE=5%: ~41 months at 50 signups/month. |
| **Rollout** | 50% treatment |
| **Guardrail** | Drill accuracy must not drop (context notes might make drills too easy, reducing learning) |

---

## Analysis Template

```python
"""
A/B test analysis template.
Usage: python scripts/ab_analysis.py --experiment session_length_15
"""

import argparse
import sqlite3
import numpy as np
from scipy import stats

DB_PATH = "data/mandarin.db"

def analyze_experiment(experiment_name, db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. Get experiment config
    flag = conn.execute(
        "SELECT * FROM feature_flag WHERE experiment_name = ?",
        [experiment_name]
    ).fetchone()

    if not flag:
        print(f"Experiment '{experiment_name}' not found in feature_flag table.")
        return

    print(f"Experiment: {experiment_name}")
    print(f"Rollout: {flag['rollout_pct']}%")
    print(f"Active: {flag['is_active']}")
    print()

    # 2. Get per-user outcomes (customize per experiment)
    # This example assumes binary outcome (retained / not retained)
    query = """
    WITH user_variant AS (
        SELECT
            u.id as user_id,
            -- Deterministic assignment (simplified for SQL)
            CASE WHEN abs(u.id * 2654435761 % 100) < ?
                THEN 'treatment' ELSE 'control'
            END as variant
        FROM user u
        WHERE u.created_at > ?
    ),
    user_outcome AS (
        SELECT
            uv.user_id,
            uv.variant,
            CASE WHEN COUNT(DISTINCT s.id) > 0 THEN 1 ELSE 0 END as converted
        FROM user_variant uv
        LEFT JOIN session s ON uv.user_id = s.user_id
            AND s.created_at > datetime(uv.user_id, '+7 days')  -- 7-day retention
        GROUP BY uv.user_id
    )
    SELECT variant, COUNT(*) as n, SUM(converted) as successes
    FROM user_outcome
    GROUP BY variant
    """

    rows = conn.execute(query, [flag['rollout_pct'], flag['created_at']]).fetchall()
    conn.close()

    if len(rows) != 2:
        print("Error: Expected exactly 2 variants (control, treatment).")
        return

    data = {row['variant']: {'n': row['n'], 'successes': row['successes']} for row in rows}

    control = data.get('control', {})
    treatment = data.get('treatment', {})

    if not control or not treatment:
        print("Missing control or treatment data.")
        return

    # 3. Run test
    result = two_proportion_z_test(
        control['successes'], control['n'],
        treatment['successes'], treatment['n']
    )

    # 4. Report
    print(f"Control:   {control['successes']}/{control['n']} = {result['control_rate']:.1%}")
    print(f"Treatment: {treatment['successes']}/{treatment['n']} = {result['treatment_rate']:.1%}")
    print(f"Absolute lift: {result['absolute_lift']:+.1%}")
    print(f"Relative lift: {result['relative_lift']:+.1%}" if result['relative_lift'] else "")
    print(f"Z-statistic: {result['z_statistic']:.3f}")
    print(f"P-value: {result['p_value']:.4f}")
    print(f"Significant at alpha=0.05: {'YES' if result['significant'] else 'NO'}")
    print()

    # 5. Confidence interval
    diff = result['absolute_lift']
    se = np.sqrt(
        result['control_rate'] * (1 - result['control_rate']) / control['n'] +
        result['treatment_rate'] * (1 - result['treatment_rate']) / treatment['n']
    )
    ci_lower = diff - 1.96 * se
    ci_upper = diff + 1.96 * se
    print(f"95% CI for difference: [{ci_lower:+.1%}, {ci_upper:+.1%}]")

    # 6. Decision
    print()
    if result['significant'] and result['absolute_lift'] > 0:
        print("RECOMMENDATION: Ship treatment to 100%.")
    elif result['significant'] and result['absolute_lift'] < 0:
        print("RECOMMENDATION: Kill experiment. Treatment is worse.")
    else:
        print("RECOMMENDATION: No significant difference. Continue collecting data or kill.")

def two_proportion_z_test(s_a, n_a, s_b, n_b):
    p_a = s_a / n_a
    p_b = s_b / n_b
    p_pool = (s_a + s_b) / (n_a + n_b)
    se = np.sqrt(p_pool * (1 - p_pool) * (1/n_a + 1/n_b))
    z = (p_b - p_a) / se if se > 0 else 0
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    return {
        'control_rate': p_a,
        'treatment_rate': p_b,
        'absolute_lift': p_b - p_a,
        'relative_lift': (p_b - p_a) / p_a if p_a > 0 else None,
        'z_statistic': z,
        'p_value': p_value,
        'significant': p_value < 0.05
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    args = parser.parse_args()
    analyze_experiment(args.experiment, DB_PATH)
```

## Experiment Lifecycle

1. **Design** (this document): Write pre-registration.
2. **Implement**: Add feature flag, implement treatment variant, add logging.
3. **Launch**: Set `is_active = 1` and `rollout_pct` in feature_flag table.
4. **Monitor**: Check daily for SRE issues (error rates, latency). Do NOT check for significance.
5. **Analyze**: At planned sample size or interim look, run analysis script.
6. **Decide**: Ship, kill, or extend (with pre-registered justification for extending).
7. **Document**: Record result in experiment log. Update this document.

## Anti-Patterns to Avoid

- **Peeking**: Checking results daily and stopping when p < 0.05. This inflates false positive rate to 20-30%.
- **Post-hoc subgroups**: "It didn't work overall, but it worked for HSK 3+ users!" Unless pre-registered, this is noise.
- **Changing the metric**: "Retention didn't improve, but accuracy did!" The primary metric was pre-registered.
- **Running too many experiments**: With 3 simultaneous experiments, use Benjamini-Hochberg correction.
- **Too small MDE**: Setting MDE to 1% requires 30,000+ users per group. Be realistic about what matters.
