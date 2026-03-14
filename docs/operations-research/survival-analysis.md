# Survival Analysis: Learner Retention

## Purpose

Survival analysis models "time to event" data where some observations are censored (the event hasn't happened yet). For Aelu, the events of interest are churn (learner stops using the app) and mastery (learner reaches an HSK level). Active users who haven't churned are right-censored observations.

This document covers three survival analyses: time-to-churn by acquisition channel, time-to-first-mastery by HSK level, and streak survival curves. It also specifies a Cox proportional hazards model for identifying churn risk factors.

---

## Definitions

- **Event**: Churn, defined as no session activity for 14 consecutive days.
- **Survival time**: Number of days from first session to churn event.
- **Censoring**: Users who are still active (last session within 14 days of analysis date) are right-censored -- we know they survived *at least* this long, but we don't know when they'll churn.

Why 14 days, not 7 or 30? Aelu is a daily-practice app, but real learners take breaks. 7 days is too aggressive (vacations, busy weeks). 30 days is too lenient (a user gone for 3 weeks has almost certainly churned). 14 days balances false positives and false negatives.

---

## 1. Time-to-Churn by Acquisition Channel

### Data Extraction

```sql
-- Extract survival data with acquisition channel
WITH user_activity AS (
    SELECT
        u.id as user_id,
        u.created_at as signup_date,
        u.utm_source,
        u.utm_medium,
        u.utm_campaign,
        MIN(sl.started_at) as first_session,
        MAX(sl.started_at) as last_session,
        COUNT(DISTINCT DATE(sl.started_at)) as active_days,
        COUNT(DISTINCT sl.id) as total_sessions,
        CASE
            WHEN julianday(MAX(sl.started_at)) - julianday(MIN(sl.started_at)) > 7
            THEN COUNT(DISTINCT sl.id) * 7.0 /
                 (julianday(MAX(sl.started_at)) - julianday(MIN(sl.started_at)))
            ELSE COUNT(DISTINCT sl.id)
        END as sessions_per_week,
        AVG(CASE WHEN re.correct IS NOT NULL THEN re.correct ELSE NULL END) as avg_accuracy,
        SUM(CASE WHEN re.drill_type IN ('tone_production', 'listening', 'speaking')
            THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(re.id), 0) as audio_usage_pct
    FROM user u
    LEFT JOIN session_log sl ON u.id = sl.user_id
    LEFT JOIN review_event re ON sl.id = re.session_id
    WHERE u.is_active = 1
      AND u.email != 'local@localhost'
    GROUP BY u.id
)
SELECT
    user_id,
    signup_date,
    COALESCE(utm_source, 'direct') as channel,
    total_sessions,
    sessions_per_week,
    COALESCE(avg_accuracy, 0) as avg_accuracy,
    COALESCE(audio_usage_pct, 0) as audio_usage_pct,
    CAST(julianday(last_session) - julianday(first_session) AS INTEGER) as survival_days,
    CASE
        WHEN julianday('now') - julianday(last_session) > 14 THEN 1
        ELSE 0
    END as churned,
    CASE
        WHEN julianday('now') - julianday(last_session) > 14
        THEN CAST(julianday(last_session) - julianday(first_session) + 14 AS INTEGER)
        ELSE CAST(julianday('now') - julianday(first_session) AS INTEGER)
    END as observation_days
FROM user_activity
WHERE first_session IS NOT NULL
ORDER BY survival_days DESC;
```

### Kaplan-Meier Estimator

The Kaplan-Meier estimator calculates the survival function S(t) -- the probability that a learner is still active at time t:

```
S(t) = PRODUCT over all t_i <= t of [(n_i - d_i) / n_i]
```

Where:
- `t_i` = time of the i-th churn event
- `n_i` = number of learners still active (at risk) just before `t_i`
- `d_i` = number of learners who churned at `t_i`

### Pseudocode: Overall and by Channel

```python
import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter
from lifelines.statistics import logrank_test, multivariate_logrank_test

def load_survival_data(db_path):
    """Load survival dataset from Aelu SQLite database."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    # Use the extraction query above
    df = pd.read_sql_query(SURVIVAL_QUERY, conn)
    conn.close()
    df['observation_days'] = df['observation_days'].clip(lower=1)
    return df

def kaplan_meier_overall(df):
    """Fit overall survival curve."""
    kmf = KaplanMeierFitter()
    kmf.fit(
        durations=df['observation_days'],
        event_observed=df['churned'],
        label='All Users'
    )

    print("Kaplan-Meier Retention Estimates:")
    for t in [7, 14, 30, 60, 90, 180, 365]:
        s = kmf.predict(t)
        print(f"  S({t:>3} days) = {s:.3f}  "
              f"({(1 - s) * 100:.1f}% cumulative churn)")

    median = kmf.median_survival_time_
    ci = kmf.confidence_interval_survival_function_
    print(f"\nMedian survival time: {median:.1f} days")

    return kmf

def kaplan_meier_by_channel(df):
    """Compare survival curves by acquisition channel."""
    channels = df['channel'].unique()
    kmfs = {}

    for channel in channels:
        mask = df['channel'] == channel
        if mask.sum() < 10:
            continue  # skip channels with too few users
        kmf = KaplanMeierFitter()
        kmf.fit(
            durations=df.loc[mask, 'observation_days'],
            event_observed=df.loc[mask, 'churned'],
            label=channel
        )
        kmfs[channel] = kmf

        print(f"\n{channel} (n={mask.sum()}):")
        for t in [7, 30, 90]:
            print(f"  S({t}) = {kmf.predict(t):.3f}")
        print(f"  Median: {kmf.median_survival_time_:.0f} days")

    # Pairwise log-rank tests
    channel_list = list(kmfs.keys())
    print("\nLog-rank tests (channel comparisons):")
    for i in range(len(channel_list)):
        for j in range(i + 1, len(channel_list)):
            c1, c2 = channel_list[i], channel_list[j]
            m1 = df['channel'] == c1
            m2 = df['channel'] == c2
            result = logrank_test(
                df.loc[m1, 'observation_days'],
                df.loc[m2, 'observation_days'],
                df.loc[m1, 'churned'],
                df.loc[m2, 'churned']
            )
            sig = "*" if result.p_value < 0.05 else ""
            print(f"  {c1} vs {c2}: chi2={result.test_statistic:.2f}, "
                  f"p={result.p_value:.4f} {sig}")

    # Multivariate test (all channels simultaneously)
    if len(channel_list) > 2:
        result = multivariate_logrank_test(
            df['observation_days'], df['channel'], df['churned']
        )
        print(f"\nMultivariate log-rank: chi2={result.test_statistic:.2f}, "
              f"p={result.p_value:.4f}")

    return kmfs
```

### Expected Survival Curves

| Days | S(t) Overall | S(t) Organic | S(t) Paid Ads | S(t) Referral | S(t) Classroom |
|------|-------------|-------------|--------------|--------------|----------------|
| 7 | 0.75 | 0.80 | 0.60 | 0.85 | 0.90 |
| 14 | 0.55 | 0.62 | 0.40 | 0.70 | 0.82 |
| 30 | 0.35 | 0.42 | 0.22 | 0.50 | 0.70 |
| 60 | 0.22 | 0.28 | 0.12 | 0.35 | 0.58 |
| 90 | 0.15 | 0.20 | 0.08 | 0.25 | 0.50 |

Referral and classroom users retain best due to social accountability. Paid acquisition retains worst due to lower intent. These estimates are based on consumer education app benchmarks; actual values will differ.

---

## 2. Time-to-First-Mastery by HSK Level

### Definition

First mastery = the first date when a learner has 50+ items at `mastery_stage = 'stable'` within a given HSK level.

### Data Extraction

```sql
-- Time to first mastery per user per HSK level
WITH mastery_dates AS (
    SELECT
        p.user_id,
        ci.hsk_level,
        p.stable_since_date,
        ROW_NUMBER() OVER (
            PARTITION BY p.user_id, ci.hsk_level
            ORDER BY p.stable_since_date
        ) as stable_rank,
        COUNT(*) OVER (
            PARTITION BY p.user_id, ci.hsk_level
            ORDER BY p.stable_since_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_stable
    FROM progress p
    JOIN content_item ci ON p.content_item_id = ci.id
    WHERE p.mastery_stage = 'stable'
      AND p.stable_since_date IS NOT NULL
),
first_mastery AS (
    SELECT
        user_id,
        hsk_level,
        MIN(stable_since_date) as mastery_date
    FROM mastery_dates
    WHERE cumulative_stable >= 50
    GROUP BY user_id, hsk_level
)
SELECT
    u.id as user_id,
    fm.hsk_level,
    CAST(julianday(fm.mastery_date) - julianday(u.created_at) AS INTEGER) as days_to_mastery,
    CASE WHEN fm.mastery_date IS NOT NULL THEN 1 ELSE 0 END as achieved
FROM user u
CROSS JOIN (SELECT DISTINCT hsk_level FROM content_item WHERE hsk_level IS NOT NULL) levels
LEFT JOIN first_mastery fm ON u.id = fm.user_id AND levels.hsk_level = fm.hsk_level
WHERE u.email != 'local@localhost';
```

### Kaplan-Meier for Mastery

```python
def mastery_survival_by_hsk(df):
    """
    Survival analysis for time-to-mastery.
    Event = achieving 50-item mastery in an HSK level.
    Censored = user hasn't achieved mastery yet (still active or churned before).
    """
    for level in sorted(df['hsk_level'].unique()):
        mask = df['hsk_level'] == level
        subset = df[mask].copy()

        # For users who haven't achieved mastery, duration is time since signup
        subset['duration'] = subset['days_to_mastery'].fillna(
            (pd.Timestamp.now() - pd.to_datetime(subset['signup_date'])).dt.days
        ).clip(lower=1)

        kmf = KaplanMeierFitter()
        kmf.fit(
            durations=subset['duration'],
            event_observed=subset['achieved'],
            label=f'HSK {level}'
        )

        median = kmf.median_survival_time_
        print(f"HSK {level}: Median time to mastery = {median:.0f} days")
        print(f"  P(mastery by day 90) = {1 - kmf.predict(90):.3f}")
        print(f"  P(mastery by day 180) = {1 - kmf.predict(180):.3f}")
```

### Expected Mastery Timelines

| HSK Level | Vocab Items | Median Days to 50-Item Mastery | 95% CI | P(mastery by day 90) |
|-----------|------------|-------------------------------|--------|---------------------|
| HSK 1 | 150 | ~45 | [25, 90] | 0.55 |
| HSK 2 | 150 | ~120 | [70, 200] | 0.18 |
| HSK 3 | 300 | ~240 | [150, 400] | 0.05 |
| HSK 4 | 600 | ~400 | [250, 650] | <0.01 |
| HSK 5 | 1300 | ~700 | [450, 1000] | <0.01 |

These estimates assume 4 sessions/week at 12 items/session. The wide confidence intervals reflect variation in learner aptitude and consistency.

---

## 3. Streak Survival Curves

### Definition

A streak is a sequence of consecutive calendar days where the learner completed at least one session. A streak ends when a day passes with no session.

### Data Extraction

```sql
-- Extract streaks from session_log
WITH session_days AS (
    SELECT
        user_id,
        DATE(started_at) as session_date,
        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY DATE(started_at)) as rn
    FROM session_log
    WHERE ended_at IS NOT NULL
    GROUP BY user_id, DATE(started_at)
),
streak_groups AS (
    SELECT
        user_id,
        session_date,
        DATE(session_date, '-' || rn || ' days') as streak_group
    FROM session_days
),
streaks AS (
    SELECT
        user_id,
        streak_group,
        COUNT(*) as streak_length,
        MIN(session_date) as streak_start,
        MAX(session_date) as streak_end,
        -- Is this streak still ongoing? (last day is today or yesterday)
        CASE
            WHEN julianday('now') - julianday(MAX(session_date)) <= 1 THEN 0
            ELSE 1
        END as streak_ended
    FROM streak_groups
    GROUP BY user_id, streak_group
)
SELECT streak_length, streak_ended
FROM streaks
ORDER BY streak_length DESC;
```

### Streak Survival Analysis

```python
def streak_survival(df):
    """Analyze streak length distribution as a survival process."""
    kmf = KaplanMeierFitter()
    kmf.fit(
        durations=df['streak_length'],
        event_observed=df['streak_ended'],
        label='Streak Survival'
    )

    print("Streak Survival Probabilities:")
    for t in [3, 5, 7, 14, 21, 30, 60]:
        s = kmf.predict(t)
        print(f"  P(streak >= {t:>2} days) = {s:.3f}")

    median = kmf.median_survival_time_
    print(f"\nMedian streak length: {median:.1f} days")

    return kmf
```

### Expected Streak Survival

| Streak Length | P(streak >= t) | Interpretation |
|--------------|---------------|----------------|
| 3 days | ~0.60 | 40% break within 3 days |
| 5 days | ~0.40 | Workweek barrier |
| 7 days | ~0.28 | One full week is a milestone |
| 14 days | ~0.12 | Two weeks = strong habit signal |
| 21 days | ~0.07 | Habit formation threshold |
| 30 days | ~0.04 | Rare; these users are committed |
| 60 days | ~0.01 | Exceptional consistency |

### Design Implication

Most streaks die within the first week. The Civic Sanctuary aesthetic explicitly avoids streak anxiety (no flame counters, no guilt messaging). The survival data should inform whether gentle streak-aware encouragement (not gamified streaks) improves retention. The current momentum indicator shows a quiet upward-drift animation rather than a number, which is consistent with the anti-anxiety design philosophy.

---

## 4. Cox Proportional Hazards Model

### Purpose

Identify which learner behaviors are associated with higher or lower churn risk.

```
h(t|X) = h_0(t) * exp(beta_1*X_1 + beta_2*X_2 + ... + beta_k*X_k)
```

Where:
- `h(t|X)` = hazard rate (instantaneous churn risk) at time t given covariates X
- `h_0(t)` = baseline hazard (estimated nonparametrically)
- `exp(beta_i)` = hazard ratio for covariate i (HR > 1 = higher churn risk)

### Covariates

| Covariate | Source Table | Hypothesis |
|-----------|------------|-----------|
| `sessions_first_week` | session_log | More early sessions = lower churn (strongest predictor) |
| `accuracy_first_week` | review_event | Higher accuracy = lower frustration = lower churn |
| `drill_types_seen` | review_event | More variety = higher engagement |
| `encounter_count` | vocab_encounter | Reading/listening exposure = deeper engagement |
| `hsk_level` | learner_profile | Higher level = more committed |
| `audio_usage_pct` | review_event | Audio drills deepen learning |
| `utm_source` | user | Acquisition channel effects |
| `platform` | client_event | iOS vs web retention differences |

### Feature Engineering

```python
def prepare_cox_features(db_path):
    """Extract features for Cox PH model from Aelu database."""
    import sqlite3
    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        u.id as user_id,
        -- First-week engagement (critical window)
        (SELECT COUNT(*) FROM session_log sl
         WHERE sl.user_id = u.id
         AND sl.started_at <= datetime(u.created_at, '+7 days')
        ) as sessions_first_week,

        (SELECT COALESCE(AVG(re.correct), 0) FROM review_event re
         WHERE re.user_id = u.id
         AND re.created_at <= datetime(u.created_at, '+7 days')
        ) as accuracy_first_week,

        -- Overall engagement depth
        (SELECT COUNT(DISTINCT re.drill_type) FROM review_event re
         WHERE re.user_id = u.id
        ) as drill_types_seen,

        (SELECT COUNT(*) FROM vocab_encounter ve
         WHERE ve.user_id = u.id
        ) as encounter_count,

        -- Audio engagement
        (SELECT SUM(CASE WHEN re.drill_type IN ('tone_production','listening','speaking')
                    THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(re.id), 0)
         FROM review_event re WHERE re.user_id = u.id
        ) as audio_usage_pct,

        -- Current level
        COALESCE(lp.level_reading, 1.0) as hsk_level,

        -- Channel
        COALESCE(u.utm_source, 'direct') as channel

    FROM user u
    LEFT JOIN learner_profile lp ON u.id = lp.user_id
    WHERE u.email != 'local@localhost'
      AND u.created_at IS NOT NULL
    """

    features = pd.read_sql_query(query, conn)
    conn.close()
    return features

def fit_cox_model(survival_df, features_df):
    """Fit Cox PH model and report results."""
    from lifelines import CoxPHFitter

    merged = survival_df.merge(features_df, on='user_id', how='inner')

    covariates = [
        'sessions_first_week', 'accuracy_first_week',
        'drill_types_seen', 'encounter_count',
        'audio_usage_pct', 'hsk_level'
    ]

    cox_df = merged[['observation_days', 'churned'] + covariates].dropna()

    # Standardize continuous variables for interpretable coefficients
    for col in covariates:
        std = cox_df[col].std()
        if std > 0:
            cox_df[col] = (cox_df[col] - cox_df[col].mean()) / std

    cph = CoxPHFitter()
    cph.fit(cox_df, duration_col='observation_days', event_col='churned')

    cph.print_summary()

    # Interpretation
    print("\nHazard Ratio Interpretation:")
    for cov in covariates:
        hr = np.exp(cph.params_[cov])
        p = cph.summary.loc[cov, 'p']
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        direction = "protective" if hr < 1 else "risk factor"
        pct = abs(1 - hr) * 100
        print(f"  {cov}: HR={hr:.3f} {sig} ({direction}, {pct:.0f}%)")

    # Check proportional hazards assumption
    cph.check_assumptions(cox_df, p_value_threshold=0.05)

    return cph
```

### Expected Hazard Ratios

| Covariate | Expected HR | 95% CI | Interpretation |
|-----------|------------|--------|----------------|
| sessions_first_week (+1 SD) | ~0.55 | [0.40, 0.75] | 45% lower churn risk. **Strongest predictor.** |
| accuracy_first_week (+1 SD) | ~0.75 | [0.58, 0.95] | 25% lower churn risk |
| drill_types_seen (+1 SD) | ~0.80 | [0.65, 0.98] | 20% lower churn risk |
| encounter_count (+1 SD) | ~0.85 | [0.70, 1.03] | 15% lower churn risk (may not be significant) |
| audio_usage_pct (+1 SD) | ~0.82 | [0.65, 1.02] | 18% lower churn risk |
| hsk_level (+1 SD) | ~0.70 | [0.52, 0.94] | 30% lower churn risk (committed learners) |

**Key finding:** First-week session count is expected to be the strongest predictor. Interventions should focus on driving 3+ sessions in the first 7 days through onboarding emails, push notifications (via the push_token system), and in-app nudges.

---

## 5. Censoring Considerations

### Right Censoring

Active users are right-censored: we know they haven't churned yet but not when they will. Both Kaplan-Meier and Cox PH handle right censoring natively.

### Left Truncation

Users who signed up before data collection began are left-truncated. They must enter the risk set at their first observed session, not at t=0.

```python
# Handle left truncation in lifelines
kmf.fit(
    durations=df['observation_days'],
    event_observed=df['churned'],
    entry=df['entry_time'],  # days from signup to first observation
    label='Truncation-adjusted'
)
```

### Informative Censoring Warning

If users reduce session frequency gradually before churning (rather than stopping abruptly), the 14-day threshold may create informative censoring. Monitor pre-churn behavior:

```sql
-- Check for gradual session frequency decline before churn
WITH churned_users AS (
    SELECT user_id, MAX(started_at) as last_session
    FROM session_log
    GROUP BY user_id
    HAVING julianday('now') - julianday(MAX(started_at)) > 14
),
pre_churn_sessions AS (
    SELECT
        sl.user_id,
        CAST(julianday(cu.last_session) - julianday(sl.started_at) AS INTEGER) as days_before_last,
        COUNT(*) as sessions_that_day
    FROM session_log sl
    JOIN churned_users cu ON sl.user_id = cu.user_id
    GROUP BY sl.user_id, DATE(sl.started_at)
)
SELECT
    CASE
        WHEN days_before_last <= 3 THEN 'last 3 days'
        WHEN days_before_last <= 7 THEN '4-7 days before'
        WHEN days_before_last <= 14 THEN '8-14 days before'
        ELSE '15+ days before'
    END as period,
    AVG(sessions_that_day) as avg_daily_sessions,
    COUNT(DISTINCT user_id) as n_users
FROM pre_churn_sessions
GROUP BY period
ORDER BY days_before_last;
```

If there is a gradual decline, consider using a continuous engagement score rather than a binary churn threshold.

---

## 6. Churn Risk Scoring (Production Integration)

Use the fitted Cox model to generate per-user churn risk scores for the email scheduler and retention scheduler:

```python
def daily_churn_risk_check(db_path, cph_model):
    """
    Daily job: identify at-risk users and trigger interventions.
    Integrates with email_scheduler.py and retention_scheduler.py.
    """
    features = prepare_cox_features(db_path)

    for _, user in features.iterrows():
        risk = cph_model.predict_partial_hazard(
            user[['sessions_first_week', 'accuracy_first_week',
                   'drill_types_seen', 'encounter_count',
                   'audio_usage_pct', 'hsk_level']]
        )
        risk_score = min(100, max(0, float(risk) * 50))

        if risk_score > 70:
            # High risk: queue re-engagement email
            queue_lifecycle_event('churn_risk_high', user['user_id'],
                                 metadata={'risk_score': risk_score})
        elif risk_score > 50:
            # Medium risk: set in-app nudge for next visit
            queue_lifecycle_event('churn_risk_medium', user['user_id'],
                                 metadata={'risk_score': risk_score})
```

---

## Implementation Roadmap

| Milestone | Users Needed | Analysis | Action |
|-----------|-------------|----------|--------|
| 1 | 50 | Kaplan-Meier overall | Report median survival in admin dashboard |
| 2 | 200 | KM by channel + log-rank tests | Identify worst acquisition channels; stop spending on channels with <20% day-30 retention |
| 3 | 500 | Cox PH model (5 covariates) | Build early warning system; trigger re-engagement emails |
| 4 | 1,000 | Streak survival + mastery curves | A/B test gentle retention nudges vs. no nudges |
| 5 | 5,000 | Time-varying Cox + competing risks | Model churn vs. mastery as competing risks; optimize for mastery |

## Dependencies

- `lifelines` (Python survival analysis library): `pip install lifelines`
- `pandas`, `numpy`: already in requirements
- Minimum data: 50 churn events for Kaplan-Meier; 10 events per covariate for Cox PH (with 6 covariates, need ~60 churn events)

## Limitations

1. **Small sample**: With <100 users, confidence intervals will be wide. Report them honestly.
2. **Survivorship bias**: Users who churn on Day 0-1 may never generate enough data for covariate measurement. Treat Day 1 separately.
3. **Time-varying covariates**: Sessions per week changes over time, but standard Cox PH uses a single value. For more accuracy, use extended Cox models (requires lifelines `CoxTimeVaryingFitter`).
4. **Confounding**: Users who practice more may be intrinsically more motivated. Correlation is not causation. Use A/B tests to establish causal effects.
