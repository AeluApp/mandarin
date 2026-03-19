# Experiment Assignment Architecture — Design Document

> Aelu's upgraded experiment assignment and allocation system.
> Designed for statistical validity, causal inference, auditability,
> and a principled path to personalization.

---

## 1. Executive Summary

Aelu's current experimentation system is a solid foundation: deterministic hash-based assignment, persisted assignments, O'Brien-Fleming sequential testing, guardrail monitoring with auto-pause, autonomous daemon, and graduated rollout. It is better than most early-stage products.

But it has structural gaps that will cause problems as experimentation scales:

- **No eligibility layer** — any user can enter any experiment regardless of readiness, data sufficiency, or conflicting experiments
- **No stratification** — assignment ignores learner stage, engagement, or tenure, producing unnecessarily noisy estimates
- **No sample ratio mismatch (SRM) detection** — broken experiments can run undetected
- **No covariate balance checks** — no way to verify randomization is working
- **No outcome-window discipline** — analysis looks at all sessions with no maturation requirement
- **No CUPED or variance reduction** — experiments need larger samples than necessary
- **No audit trail** — eligibility decisions, ramp changes, and overrides are unlogged
- **No mutual exclusion** — users can be in multiple conflicting experiments
- **No pre-registration enforcement** — experiment config can be changed mid-flight
- **No Goodhart failure mode declaration** — no forced thinking about what could go wrong
- **No heterogeneous treatment effect framework** — subgroup analysis is ad-hoc
- **Churn-days guardrail has a SQL bug** — GROUP BY returns only first row's average

This document designs the upgraded system. The governing principle: **intelligence before randomization (eligibility, design) and after randomization (analysis, learning) — but not in the assignment itself.**

---

## 2. Diagnosis of Current Assignment Weaknesses

### What works well
1. **Deterministic hash assignment** — sticky, reproducible, no DB lookup at runtime
2. **Persisted assignments** — audit trail for who got what
3. **O'Brien-Fleming sequential testing** — ethical early stopping
4. **Autonomous daemon** — monitors, concludes, rolls out without human bottleneck
5. **Guardrail auto-pause** — safety net against harmful experiments
6. **Graduated rollout** — safe winner deployment
7. **User-level analysis** — avoids Simpson's paradox

### What needs fixing

| Gap | Severity | Current Impact |
|-----|----------|---------------|
| No eligibility layer | High | New users with 0 sessions enter retention experiments |
| No SRM detection | High | Broken randomization runs silently |
| No stratification | Medium | Noisier estimates, longer experiments |
| No CUPED | Medium | 20-40% more sample needed than necessary |
| No outcome-window discipline | High | Mixing mature and immature observations |
| No mutual exclusion | Medium | Cross-experiment contamination |
| No audit logging | Medium | Cannot reconstruct decisions |
| No balance checks | Medium | Cannot verify randomization quality |
| No config freeze | Medium | Post-hoc changes can corrupt experiments |
| Churn-days guardrail bug | Low | Guardrail reports wrong value |
| No HTE framework | Low | Subgroup analysis is fishing |

### Specific bugs

**churn_days guardrail** (`experiments.py:519-531`): The query uses `GROUP BY user_id` but `fetchone()` returns only the first group's average, not the cross-user average. Fix: use a subquery to first compute per-user max session dates, then average across users.

**Traffic check arithmetic** (`experiments.py:131-132`): `traffic_bucket >= traffic_pct * 100` — when `traffic_pct=100.0`, this is `>= 10000` which correctly includes everyone (bucket range is 0-9999). When `traffic_pct=50.0`, this is `>= 5000` which correctly includes ~50%. The arithmetic is correct but fragile; `traffic_pct=100.1` would exclude everyone. Should clamp.

---

## 3. Recommended Assignment Architecture

### Architecture layers

```
┌─────────────────────────────────────────────────────────┐
│                    Experiment Registry                    │
│  (config, lifecycle, pre-registration, outcome windows)  │
├─────────────────────────────────────────────────────────┤
│                    Eligibility Engine                     │
│  (rules, mutual exclusion, data sufficiency, filtering)  │
├─────────────────────────────────────────────────────────┤
│                  Stratification Layer                     │
│  (stratum computation, dynamic collapsing, validation)   │
├─────────────────────────────────────────────────────────┤
│                  Assignment Allocator                     │
│  (hash-based within strata, traffic gating, persistence) │
├─────────────────────────────────────────────────────────┤
│                   Exposure Logger                         │
│  (context-aware logging, deduplication)                   │
├─────────────────────────────────────────────────────────┤
│                  Balance Monitor                          │
│  (SRM, covariate balance, drift, exposure imbalance)     │
├─────────────────────────────────────────────────────────┤
│                   Analysis Engine                         │
│  (CUPED, sequential testing, guardrails, HTE)            │
├─────────────────────────────────────────────────────────┤
│                     Audit Log                             │
│  (eligibility decisions, assignments, overrides, ramps)  │
└─────────────────────────────────────────────────────────┘
```

### Data flow for a single assignment

```
User arrives → Eligibility check (logged) →
  Eligible? NO → return None, log exclusion reason
  Eligible? YES →
    Compute stratum (HSK band × engagement band) →
    Hash-based assignment within stratum →
    Persist assignment (with stratum, hash_value, config version) →
    Return variant
```

---

## 4. Randomization Unit Decision Framework

### Decision rules for Aelu

| Experiment Category | Unit | Rationale |
|---|---|---|
| **Pedagogy** (spacing algorithm, SRS parameters, drill mix, difficulty curve) | **User** | Learning is cumulative; session-level would create inconsistent learning trajectories |
| **Session planning** (session length, composition, warm-up structure) | **User** | Habit formation requires consistency; switching mid-user corrupts learning signal |
| **Onboarding flow** | **User** | First impressions are one-shot; must be consistent |
| **Email/notification cadence** | **User** | Communication strategy is inherently user-level |
| **Content selection** (passage difficulty, topic variety, content lens weighting) | **User** | Content shapes the learning trajectory |
| **Drill presentation micro-detail** (font size, color, animation timing) | **User** (default) | Even "tiny" UI changes can affect concentration and learning. Use user-level unless you can prove zero carryover |
| **Drill type gating** (enabling new drill types) | **User** | Feature availability should be consistent |
| **Classroom/social features** | **Cluster** (classroom) | Spillover within classrooms; randomize at classroom level |
| **Pricing/paywall** | **User** | Must be consistent per user (legal and trust reasons) |

### Why session-level is almost never right for Aelu

In a language-learning product:
- Sessions are not independent — what you practiced in session N affects session N+1
- Carryover effects are the norm, not the exception
- Users would notice inconsistency (e.g., session length changing randomly)
- Most outcomes worth measuring (retention, mastery) are user-level

**Session-level is acceptable only when**: the intervention is invisible to the learner, has zero effect on learning content, and the outcome is measured within the same session.

### Why item-level requires extreme caution

Item-level randomization (different treatment per drill item within a session) is tempting for drill-format experiments but dangerous because:
- Within-session items are not independent (fatigue, learning within session)
- Must cluster standard errors by user
- Can create confusing user experiences
- Suitable only for: audio speed variations, distractor quality, visual presentation details

### Staged rollout (already implemented)

Use for deploying experiment winners. Current graduated rollout (pending → 25% → 50% → 100% → complete) is appropriate.

---

## 5. Eligibility Framework

### Rule schema

Each experiment declares eligibility rules as a JSON config:

```json
{
  "min_sessions": 3,
  "min_tenure_days": 7,
  "hsk_band": [1, 9],
  "engagement_band": ["low", "medium", "high"],
  "status": ["active"],
  "platforms": ["web", "cli"],
  "exclude_admin": true,
  "exclude_experiments": ["conflicting_exp_name"],
  "max_concurrent_experiments": 2,
  "min_data_sufficiency": {
    "metric": "sessions",
    "min_count": 5,
    "lookback_days": 30
  },
  "require_features": ["audio_enabled"],
  "exclude_dormant_days": 14,
  "custom_sql": null
}
```

### Default eligibility (applied to all experiments)

- User must have `is_active = 1`
- User must not be admin/tester (unless experiment explicitly includes them)
- User must have at least 1 completed session (avoids assigning users who signed up but never started)
- User must not be in a paused/cancelled subscription state (unless experiment targets reactivation)

### Eligibility evaluation

```python
def check_eligibility(conn, experiment, user_id) -> (bool, list[str]):
    """Returns (eligible, [reasons_for_exclusion])."""
    reasons = []
    rules = experiment.eligibility_rules

    # Default checks
    if not _is_active(conn, user_id):
        reasons.append("user_inactive")
    if _is_admin(conn, user_id) and rules.get("exclude_admin", True):
        reasons.append("admin_excluded")

    # Rule-based checks
    if rules.get("min_sessions"):
        sessions = _count_sessions(conn, user_id)
        if sessions < rules["min_sessions"]:
            reasons.append(f"insufficient_sessions:{sessions}<{rules['min_sessions']}")

    if rules.get("min_tenure_days"):
        tenure = _tenure_days(conn, user_id)
        if tenure < rules["min_tenure_days"]:
            reasons.append(f"insufficient_tenure:{tenure}<{rules['min_tenure_days']}")

    # Mutual exclusion
    if rules.get("exclude_experiments"):
        for other_exp in rules["exclude_experiments"]:
            if _is_assigned(conn, user_id, other_exp):
                reasons.append(f"mutual_exclusion:{other_exp}")

    if rules.get("max_concurrent_experiments"):
        current = _count_active_assignments(conn, user_id)
        if current >= rules["max_concurrent_experiments"]:
            reasons.append(f"max_concurrent:{current}")

    # HSK band check
    if rules.get("hsk_band"):
        hsk = _get_hsk_level(conn, user_id)
        lo, hi = rules["hsk_band"]
        if hsk < lo or hsk > hi:
            reasons.append(f"hsk_out_of_range:{hsk}")

    # Data sufficiency for CUPED
    if rules.get("min_data_sufficiency"):
        suff = rules["min_data_sufficiency"]
        count = _count_metric(conn, user_id, suff["metric"], suff["lookback_days"])
        if count < suff["min_count"]:
            reasons.append(f"data_insufficiency:{suff['metric']}:{count}<{suff['min_count']}")

    eligible = len(reasons) == 0
    return eligible, reasons
```

### Critical principle

**Eligibility filtering is allowed. Predictive targeting for assignment is NOT.**

Eligibility determines *who may enter*. It must not determine *which arm they get*. The eligibility rules must be:
- Declared before the experiment starts
- Based on pre-treatment characteristics only
- Not based on predicted uplift or response probability
- Logged for every evaluation

---

## 6. Stratification and Balance Strategy

### 6a. Stratification variables

**Recommended default strata (2 variables, 6 cells):**

| Variable | Levels | Rationale |
|---|---|---|
| HSK band | Low (1-2), Mid (3-4), High (5+) | Proficiency fundamentally changes learning behavior, outcomes, and content |
| Engagement band | Low (<2 sess/wk), Medium (2-4), High (5+) | Usage intensity is the strongest predictor of most outcomes |

This produces 3 × 3 = 9 strata. With small experiments, collapse to:
- HSK band (3 levels) × Engagement (2 levels: <3 vs 3+) = 6 strata
- Or just HSK band (3 levels) if n < 200

**Not recommended for stratification (use as CUPED covariates instead):**
- Tenure: correlated with engagement, adds strata without much independent value
- Platform: too few mobile users currently to justify a stratum
- Locale/timezone: insufficient diversity for separate strata
- Content lens affinity: too many levels, unstable

### 6b. When stratification helps vs. hurts

| Condition | Recommendation |
|---|---|
| n > 500 total | Stratify on HSK × Engagement (9 cells) |
| 200 < n ≤ 500 | Stratify on HSK × Engagement (6 cells, collapsed) |
| 100 < n ≤ 200 | Stratify on HSK only (3 cells) |
| n ≤ 100 | No stratification; use CUPED for post-hoc adjustment |
| Any stratum has < 10 users | Collapse with adjacent stratum |

### 6c. Stratum computation

```python
def compute_stratum(conn, user_id) -> str:
    """Compute the stratification stratum for a user.
    Returns a string like 'hsk:low|eng:med'."""
    profile = get_learner_profile(conn, user_id)

    # HSK band
    avg_level = _avg_proficiency(profile)
    if avg_level <= 2.5:
        hsk = "low"
    elif avg_level <= 4.5:
        hsk = "mid"
    else:
        hsk = "high"

    # Engagement band (sessions in last 14 days / 2)
    recent_sessions = _sessions_last_n_days(conn, user_id, 14)
    weekly_rate = recent_sessions / 2.0
    if weekly_rate < 2:
        eng = "low"
    elif weekly_rate < 5:
        eng = "med"
    else:
        eng = "high"

    return f"hsk:{hsk}|eng:{eng}"
```

### 6d. Assignment within strata

Within each stratum, use the same deterministic hash approach but with the stratum included in the hash:

```python
assign_key = f"{salt}:{experiment_name}:{stratum}:{user_id}"
variant_index = int(hashlib.sha256(assign_key.encode()).hexdigest()[:8], 16) % len(variants)
```

This ensures that balance is maintained within each stratum, even if the overall user population shifts.

### 6e. Balance diagnostics

**Automated checks (run by daemon):**

| Check | Frequency | Threshold | Action |
|---|---|---|---|
| **Sample Ratio Mismatch (SRM)** | Every daemon tick (6h) | Chi-squared p < 0.001 | **Auto-pause** + alert |
| **Covariate balance (SMD)** | Launch + 1 day, then weekly | Any covariate SMD > 0.15 | Log warning |
| **Assignment drift** | Every daemon tick | Cumulative ratio off by > 3pp for > 48h | Alert |
| **Exposure imbalance** | Weekly | Differential exposure > 5% | Alert |
| **Missingness imbalance** | Weekly | Differential outcome missingness > 5% | Alert |
| **Stratum depletion** | Weekly | Any stratum < 5 users in either arm | Log warning |

**SRM detection implementation:**

```python
def check_srm(conn, experiment_id, expected_ratio=0.5) -> dict:
    """Chi-squared test for sample ratio mismatch."""
    counts = conn.execute("""
        SELECT variant, COUNT(*) as n
        FROM experiment_assignment WHERE experiment_id = ?
        GROUP BY variant
    """, (experiment_id,)).fetchall()

    if len(counts) != 2:
        return {"passed": True, "reason": "not_two_variants"}

    n1, n2 = counts[0]["n"], counts[1]["n"]
    total = n1 + n2
    expected_n1 = total * expected_ratio
    expected_n2 = total * (1 - expected_ratio)

    chi2 = ((n1 - expected_n1)**2 / expected_n1 +
            (n2 - expected_n2)**2 / expected_n2)

    # Chi-squared with 1 df, p < 0.001 threshold
    # chi2 > 10.83 corresponds to p < 0.001
    p_value = 1 - 0.5 * (1 + math.erf(math.sqrt(chi2 / 2)))  # approximation
    passed = p_value >= 0.001

    return {
        "passed": passed,
        "chi2": round(chi2, 4),
        "p_value": round(p_value, 6),
        "n_control": n1,
        "n_treatment": n2,
        "observed_ratio": round(n1 / total, 4) if total > 0 else None,
        "expected_ratio": expected_ratio,
    }
```

**SRM is a HARD stop.** If SRM is detected, the experiment is auto-paused and flagged for investigation. SRM almost always indicates a bug in the assignment pipeline, not bad luck.

### 6f. Rerandomization

**Recommendation: Support later, not now.**

Rationale:
- Aelu uses streaming assignment (users arrive one at a time), not batch assignment
- Rerandomization is most valuable for batch designs where all units are known upfront
- The combination of stratification + CUPED provides most of the balance benefits
- Rerandomization introduces governance complexity (how many attempts? what criterion?)

**If implemented later:**
- Only for batch-assigned cohort experiments
- Maximum 100 rerandomization attempts
- Mahalanobis distance criterion: M < 0.001 quantile of chi-squared(p) where p = number of covariates
- All attempts logged with balance metrics
- Criterion declared before any randomization

---

## 7. Advanced-Methods Policy Table

| Method | Status | Value to Aelu | Risk to Validity | Implementation Complexity | Governance Constraints | Worth the Effort? |
|---|---|---|---|---|---|---|
| **Simple randomized A/B** | Use now (current) | Baseline causal inference | Low | Already built | Standard pre-registration | Yes — foundation |
| **Stratified assignment** | **Use now (new)** | Better balance, shorter experiments, more precise estimates | Low if strata are pre-declared | Medium — needs stratum computation | Strata must be declared before launch | **Yes — clear win** |
| **CUPED** | **Use now (new)** | 20-40% variance reduction; dramatically improves power at Aelu's scale | Low if pre-period is clean | Medium — regression adjustment | Pre-period must end before assignment | **Yes — high value for small n** |
| **Sequential monitoring (OBF)** | Use now (improve) | Ethical early stopping, saves time | Low | Already built; improve maturation handling | Must use information fraction, not raw n | **Yes — already exists, improve it** |
| **SRM detection** | **Use now (new)** | Catches broken experiments before they corrupt results | None | Low — simple chi-squared test | Auto-pause on detection | **Yes — essential** |
| **Holdout groups** | **Use now (new)** | Long-run truth verification; detect treatment interaction effects | Small sample reduction | Low — reserve 5-10% of users as global holdout | Holdout must be persistent across experiments | **Yes — cheap insurance** |
| **Rerandomization** | Support later | Better balance in batch designs | P-hacking if uncontrolled | Medium | Attempts logged, criterion pre-declared | Maybe — only for batch designs |
| **Minimization** | Avoid | Marginal over stratification | Not fully random; inference requires simulation | High | Complex governance | **No — stratification + CUPED is better** |
| **Response-adaptive** | Avoid | Faster winner finding | Breaks exchangeability; biased effect estimates | Very high | Cannot use for causal inference | **No — wrong tool for Aelu's goals** |
| **Thompson sampling / bandits** | Shadow mode later | Regret minimization for personalization | Not for causal inference; estimates are biased | Very high | Must run alongside, not instead of, A/B | **Later — for policy learning only** |
| **Contextual bandits** | Shadow mode later | Personalization policy learning | Contamination if used for assignment | Very high | Shadow mode only; never affects current assignment | **Later — when scale justifies it** |
| **Personalized policy learning** | Shadow mode later | Long-term personalization | Overfitting, Goodhart, contamination | Very high | Shadow predictions logged but not acted on | **Later — requires maturity** |
| **Switchback designs** | Avoid | Time-based effect estimation | Very complex analysis; stationarity assumptions | Very high | Rarely applicable to learning products | **No — not worth the complexity** |

### Decision heuristic

```
Is the experiment primarily for causal inference (learning what works)?
  → Use stratified A/B with CUPED and sequential monitoring.

Is the experiment primarily for optimization (finding the best arm fastest)?
  → This is rarely the right frame for Aelu. Learning products need
    truth more than speed. Use A/B.

Is this for personalization development (learning who benefits from what)?
  → Run a standard A/B first. After conclusion, analyze HTEs.
    If HTEs are real, consider shadow-mode policy learning.

Is the experiment too small to detect the MDE?
  → Either: (a) increase the MDE (accept you can only detect larger effects),
    (b) use CUPED to reduce variance, (c) extend the experiment duration,
    or (d) don't run it yet.
  → Do NOT use adaptive methods to compensate for insufficient power.
```

---

## 8. Statistical Efficiency Upgrades Worth Implementing

### 8a. CUPED (Controlled-experiment Using Pre-Experiment Data)

**Implement now.** This is the single highest-value improvement for Aelu's scale.

**How it works:**
For each user, compute a pre-experiment covariate X (e.g., completion rate in the 14 days before assignment). The CUPED-adjusted outcome is:

```
Y_adj = Y - θ(X - X̄)
where θ = Cov(Y, X) / Var(X)
```

This removes variance explained by pre-existing differences, improving power.

**Pre-period covariates to use (ordered by expected variance reduction):**
1. Pre-period session completion rate (strongest predictor of post-period completion)
2. Pre-period sessions per week
3. Pre-period accuracy rate
4. Pre-period average session duration

**Implementation rules:**
- Pre-period = 14 days before assignment (configurable per experiment)
- Pre-period data is frozen at assignment time (stored in `experiment_assignment`)
- Pre-period must strictly end before assignment — no overlap
- θ is estimated from the pooled data (not per-arm) to avoid bias
- Only users with sufficient pre-period data are included (see eligibility `min_data_sufficiency`)

**Expected improvement:** 20-40% variance reduction, equivalent to 25-67% more users for free.

**Leakage prevention:**
- Pre-period end date is recorded per user
- Any session that overlaps with the experiment period is excluded from pre-period computation
- θ estimation uses both arms pooled (not separate)

### 8b. Sequential testing improvements

Current O'Brien-Fleming implementation is sound. Three improvements:

1. **Maturation-aware information fraction**: Currently uses `current_n / planned_n`. Should instead use the count of users whose outcome window has closed:

```python
# Instead of:
information_fraction = current_n / planned_n

# Use:
mature_n = count_users_with_closed_outcome_window(conn, experiment_id, outcome_window_days)
information_fraction = mature_n / planned_n
```

2. **Futility boundary**: Current futility check (`p > 0.2 at 100% information`) is reasonable but could use a proper conditional power calculation.

3. **Always-valid confidence sequences**: Consider implementing for continuous monitoring without pre-declared analysis times. Lower priority — the current discrete-look O'Brien-Fleming approach is adequate.

### 8c. Small-sample and delayed-outcome design

Aelu's reality: experiments may have 50-500 users, and the most important outcomes (retention, mastery progression, delayed recall) take 7-30 days to observe.

**Design adaptations:**

| Challenge | Solution |
|---|---|
| Small n | CUPED (already reduces variance by ~30%); accept larger MDE; use continuous outcomes where possible (they have more power than binary) |
| Delayed outcomes | Declare outcome window per experiment (e.g., 7-day, 14-day, 30-day); only include users whose window has closed in analysis |
| Repeated measures | Use mixed-effects models for session-level metrics, collapsing to user-level for the primary test |
| Within-user correlation | Always analyze at user level (already done); report ICC for session-level analyses |
| Attrition | Track differential attrition between arms; report both ITT (all assigned) and per-protocol (those who were exposed) |
| Informative missingness | If treatment causes more users to stop using the app, that IS the treatment effect; ITT captures this correctly |

**Outcome window configuration:**

```json
{
  "primary_outcome": {
    "metric": "retention_7d",
    "window_days": 7,
    "measurement_start": "first_exposure"
  },
  "delayed_guardrails": [
    {
      "metric": "retention_30d",
      "window_days": 30,
      "check_after_primary": true
    }
  ]
}
```

### 8d. Heterogeneous treatment effect (HTE) analysis

**Framework for learning subgroup effects after randomization:**

**Pre-declared subgroups (confirmatory):**
- Each experiment may declare up to 3 subgroups at registration
- Typical choices: HSK band, engagement band, tenure
- These get proper multiple-testing correction (Bonferroni or Holm)
- Minimum 30 users per arm per subgroup
- Results are reported with both uncorrected and corrected p-values

**Exploratory subgroups (hypothesis-generating):**
- After the primary analysis, additional subgroups may be explored
- These are explicitly flagged as exploratory — not confirmatory
- Use Bayesian shrinkage: subgroup estimates are shrunk toward the overall mean
- Minimum 20 users per arm per subgroup
- Results are reported with uncertainty intervals, not p-values

**From interesting pattern to personalized rule:**

```
1. Primary A/B result: treatment is better overall
2. Pre-declared HTE analysis: treatment helps HSK 1-2 more than HSK 5+
3. Exploratory HTE: treatment helps evening users more than morning users
4. Hypothesis generation: "Treatment is especially valuable for beginners
   who study in the evening"
5. Next step: Run a NEW experiment specifically testing this hypothesis
   in the identified subgroup
6. NEVER: Ship a personalized rule based on exploratory HTE from one experiment
```

---

## 9. Governance / Anti-Self-Deception Rules

### Pre-registration requirements

Every experiment MUST declare before starting:

| Field | Required | Description |
|---|---|---|
| `hypothesis` | Yes | What do you expect to happen and why? |
| `primary_metric` | Yes | The single metric that determines success |
| `secondary_metrics` | Optional | Exploratory metrics (not for decision-making) |
| `guardrail_metrics` | Yes | Metrics that must not degrade (auto-filled with defaults) |
| `outcome_window_days` | Yes | How many days after exposure to measure the primary metric |
| `min_sample_size` | Yes | Per-arm sample size (from power analysis) |
| `mde` | Yes | Minimum detectable effect size |
| `eligibility_rules` | Yes | Who enters the experiment |
| `stratification_config` | If applicable | Which variables to stratify on |
| `predeclared_subgroups` | Optional | Up to 3 confirmatory subgroups |
| `goodhart_risks` | Yes | What could go right on the metric but wrong for learning? |
| `contamination_risks` | Yes | What cross-experiment or cross-session contamination could occur? |
| `outcome_horizon` | Yes | Is the outcome short-run (<7d), medium-run (7-30d), or delayed (30d+)? |

### Config freeze

Once an experiment transitions from `draft` to `running`:
- The `pre_registration` JSON is frozen (stored as `config_frozen_at` timestamp)
- Eligibility rules cannot be changed
- Stratification config cannot be changed
- Primary metric cannot be changed
- Variants cannot be changed
- `min_sample_size` can only be increased, not decreased

### Anti-self-deception rules

1. **Assignment cannot use predicted uplift.** The allocator does not have access to any model that predicts which users will benefit from treatment.

2. **Churn labels cannot determine arm assignment.** A user flagged as "at risk of churn" can be *eligible* for a churn-intervention experiment, but the label cannot influence *which arm* they receive (unless the experiment is explicitly a policy experiment with declared design).

3. **No silent reassignment.** Once a user is assigned, they stay in their arm. If an experiment is paused and restarted, existing assignments persist.

4. **Ramp changes must be logged.** Changing `traffic_pct` mid-experiment is allowed (for safety ramps) but every change is logged with timestamp, old value, new value, and reason.

5. **Every experiment declares Goodhart failure modes.** Examples:
   - "Better completion rate could mean we made sessions too easy, reducing learning"
   - "Higher retention could mean users feel obligated but aren't enjoying learning"
   - "Faster session completion could mean users are rushing through"

6. **Every experiment declares contamination risks.** Examples:
   - "Users in the treatment arm of experiment X may also be in experiment Y"
   - "Session length changes affect future SRS scheduling"
   - "Drill mix changes affect mastery trajectory"

7. **No metric shopping.** The primary metric is pre-registered. If the primary metric is null, the experiment is null — regardless of what secondary metrics show.

### Goodhart failure modes for common Aelu metrics

| Metric | Goodhart Risk | Guardrail |
|---|---|---|
| Session completion rate | Sessions made too easy or too short | Accuracy must not drop; mastery progression must not slow |
| 7-day retention | Guilt-driven return (nagging), not genuine value | Session quality metrics; NPS if available |
| Average accuracy | Drill difficulty reduced; less learning | Mastery progression rate; delayed recall |
| Sessions per week | Shorter sessions counted; quality drops | Items completed per session; duration |
| Mastery progression | Thresholds lowered; promotion too easy | Delayed recall rate; error recurrence |

---

## 10. Monitoring and Audit Framework

### Audit log events

| Event Type | Logged Fields | Trigger |
|---|---|---|
| `eligibility_check` | user_id, experiment_id, eligible, exclusion_reasons, rules_version | Every eligibility evaluation |
| `assignment` | user_id, experiment_id, variant, hash_value, stratum, traffic_check, config_version | Every assignment |
| `exposure` | user_id, experiment_id, variant, context, timestamp | Every exposure |
| `exclusion` | user_id, experiment_id, reason | Eligibility exclusion |
| `balance_check` | experiment_id, check_type, metrics, passed, details | Every balance check run |
| `srm_check` | experiment_id, chi2, p_value, n_control, n_treatment, passed | Every SRM check |
| `guardrail_check` | experiment_id, metric, control_value, treatment_value, degraded | Every guardrail evaluation |
| `pause` | experiment_id, reason, triggered_by (daemon/admin) | Experiment pause |
| `resume` | experiment_id, reason, resumed_by | Experiment resume |
| `ramp_change` | experiment_id, old_pct, new_pct, reason | Traffic percentage change |
| `conclude` | experiment_id, winner, p_value, effect_size, method, notes | Experiment conclusion |
| `config_change` | experiment_id, field, old_value, new_value, changed_by | Any config modification (must be pre-start) |
| `analysis_snapshot` | experiment_id, results_json, analysis_method | Each formal analysis |

### Audit log schema

```sql
CREATE TABLE experiment_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER,
    event_type TEXT NOT NULL,
    user_id INTEGER,
    data TEXT NOT NULL,  -- JSON
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (experiment_id) REFERENCES experiment(id)
);
CREATE INDEX idx_audit_experiment ON experiment_audit_log(experiment_id);
CREATE INDEX idx_audit_event_type ON experiment_audit_log(event_type);
CREATE INDEX idx_audit_created ON experiment_audit_log(created_at);
```

### Balance check storage

```sql
CREATE TABLE experiment_balance_check (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    check_type TEXT NOT NULL,  -- 'srm', 'covariate', 'drift', 'exposure', 'missingness'
    passed INTEGER NOT NULL,  -- 0 or 1
    details TEXT NOT NULL,  -- JSON with metrics
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (experiment_id) REFERENCES experiment(id)
);
CREATE INDEX idx_balance_experiment ON experiment_balance_check(experiment_id);
```

### Admin dashboard requirements

The experiment admin dashboard should display:

1. **Experiment list** with status badges (draft, running, paused, concluded)
2. **Per-experiment detail view:**
   - Pre-registration summary (hypothesis, primary metric, MDE)
   - Current enrollment by arm and stratum
   - SRM check status (pass/fail with chi-squared)
   - Covariate balance heatmap (SMD per covariate per arm)
   - Sequential test status (information fraction, adjusted alpha, recommendation)
   - Guardrail status (per metric, with degradation indicator)
   - Primary metric results (CUPED-adjusted if applicable)
   - Outcome window maturation progress
   - Goodhart risk declarations
3. **Balance monitoring tab:**
   - SRM history over time
   - Assignment drift chart (cumulative ratio over time)
   - Covariate balance table
4. **Audit log tab:**
   - Filterable by event type
   - Sortable by timestamp
   - JSON detail expandable

---

## 11. Concrete Code Change Plan

### Module structure

Refactor `mandarin/experiments.py` (663 lines) into a package:

```
mandarin/experiments/
├── __init__.py          # Re-exports for backward compatibility
├── registry.py          # Experiment CRUD, lifecycle, config validation
├── eligibility.py       # Eligibility rules engine
├── assignment.py        # Hash-based assignment with stratification
├── stratification.py    # Stratum computation and management
├── balance.py           # SRM, covariate balance, drift detection
├── exposure.py          # Exposure logging
├── analysis.py          # Results, CUPED, z-tests, effect sizes, CIs
├── sequential.py        # O'Brien-Fleming, alpha spending
├── guardrails.py        # Guardrail metric computation
├── hte.py               # Heterogeneous treatment effect analysis
├── audit.py             # Audit log writing and reading
├── governance.py        # Pre-registration enforcement, config freeze
└── holdout.py           # Global holdout group management
```

### Schema changes (new migration V102 → V103)

**Extend `experiment` table:**
```sql
ALTER TABLE experiment ADD COLUMN salt TEXT;
ALTER TABLE experiment ADD COLUMN hypothesis TEXT;
ALTER TABLE experiment ADD COLUMN primary_metric TEXT;
ALTER TABLE experiment ADD COLUMN secondary_metrics TEXT;  -- JSON
ALTER TABLE experiment ADD COLUMN outcome_window_days INTEGER DEFAULT 7;
ALTER TABLE experiment ADD COLUMN outcome_horizon TEXT DEFAULT 'short';  -- short/medium/delayed
ALTER TABLE experiment ADD COLUMN mde REAL;
ALTER TABLE experiment ADD COLUMN eligibility_rules TEXT;  -- JSON
ALTER TABLE experiment ADD COLUMN stratification_config TEXT;  -- JSON
ALTER TABLE experiment ADD COLUMN predeclared_subgroups TEXT;  -- JSON
ALTER TABLE experiment ADD COLUMN goodhart_risks TEXT;
ALTER TABLE experiment ADD COLUMN contamination_risks TEXT;
ALTER TABLE experiment ADD COLUMN pre_registration TEXT;  -- JSON (frozen snapshot)
ALTER TABLE experiment ADD COLUMN config_frozen_at TEXT;
ALTER TABLE experiment ADD COLUMN randomization_unit TEXT DEFAULT 'user';
```

**Extend `experiment_assignment` table:**
```sql
ALTER TABLE experiment_assignment ADD COLUMN stratum TEXT;
ALTER TABLE experiment_assignment ADD COLUMN hash_value TEXT;
ALTER TABLE experiment_assignment ADD COLUMN eligibility_version TEXT;
ALTER TABLE experiment_assignment ADD COLUMN pre_period_data TEXT;  -- JSON (for CUPED)
```

**New tables:**
```sql
CREATE TABLE experiment_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER,
    event_type TEXT NOT NULL,
    user_id INTEGER,
    data TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (experiment_id) REFERENCES experiment(id)
);

CREATE TABLE experiment_balance_check (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    check_type TEXT NOT NULL,
    passed INTEGER NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (experiment_id) REFERENCES experiment(id)
);

CREATE TABLE experiment_eligibility_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    eligible INTEGER NOT NULL,
    reasons TEXT,  -- JSON
    checked_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (experiment_id) REFERENCES experiment(id)
);

CREATE TABLE experiment_holdout (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    assigned_at TEXT DEFAULT (datetime('now')),
    holdout_group TEXT DEFAULT 'global'
);
```

**Indexes:**
```sql
CREATE INDEX idx_audit_experiment ON experiment_audit_log(experiment_id);
CREATE INDEX idx_audit_event_type ON experiment_audit_log(event_type);
CREATE INDEX idx_audit_created ON experiment_audit_log(created_at);
CREATE INDEX idx_balance_experiment ON experiment_balance_check(experiment_id);
CREATE INDEX idx_eligibility_experiment ON experiment_eligibility_log(experiment_id);
CREATE INDEX idx_eligibility_user ON experiment_eligibility_log(user_id);
CREATE INDEX idx_holdout_user ON experiment_holdout(user_id);
```

### File-by-file implementation plan

| File | Action | Description |
|---|---|---|
| `mandarin/experiments/__init__.py` | Create | Re-export all public functions for backward compat |
| `mandarin/experiments/registry.py` | Create | Experiment CRUD migrated from experiments.py + governance |
| `mandarin/experiments/eligibility.py` | Create | Eligibility rules engine |
| `mandarin/experiments/assignment.py` | Create | Stratified hash assignment |
| `mandarin/experiments/stratification.py` | Create | Stratum computation |
| `mandarin/experiments/balance.py` | Create | SRM, covariate balance, drift |
| `mandarin/experiments/exposure.py` | Create | Exposure logging (migrated + improved) |
| `mandarin/experiments/analysis.py` | Create | Results computation + CUPED |
| `mandarin/experiments/sequential.py` | Create | O'Brien-Fleming (migrated + improved) |
| `mandarin/experiments/guardrails.py` | Create | Guardrail checks (migrated + fixed) |
| `mandarin/experiments/hte.py` | Create | Heterogeneous treatment effects |
| `mandarin/experiments/audit.py` | Create | Audit log |
| `mandarin/experiments/governance.py` | Create | Config validation and freeze |
| `mandarin/experiments/holdout.py` | Create | Global holdout management |
| `mandarin/experiments.py` | Replace | Thin shim importing from package |
| `mandarin/db/core.py` | Modify | Add V103 migration |
| `mandarin/web/experiment_daemon.py` | Modify | Add SRM checks, balance monitoring |
| `mandarin/web/admin_routes.py` | Modify | Extend admin API |
| `tests/test_experiments.py` | Modify | Update imports + add new tests |
| `tests/test_eligibility.py` | Create | Eligibility engine tests |
| `tests/test_stratification.py` | Create | Stratification tests |
| `tests/test_balance.py` | Create | SRM and balance check tests |
| `tests/test_cuped.py` | Create | CUPED variance reduction tests |
| `tests/test_governance.py` | Create | Pre-registration and config freeze tests |
| `tests/test_audit.py` | Create | Audit log tests |

---

## 12. Test Plan

### Unit tests

| Module | Test Cases |
|---|---|
| `eligibility.py` | Minimum sessions check; tenure check; HSK band filter; mutual exclusion; max concurrent; data sufficiency; admin exclusion; dormant exclusion; combined rules; edge cases (new user, no profile) |
| `assignment.py` | Deterministic assignment; within-stratum balance; salt isolation (different experiments produce independent assignments); traffic gating; sticky assignment (same user always gets same variant); assignment with eligibility |
| `stratification.py` | HSK band computation; engagement band computation; stratum string format; dynamic collapsing when cells too small; edge cases (no sessions, no profile) |
| `balance.py` | SRM detection (balanced case passes, imbalanced case fails); covariate balance computation; drift detection; threshold calibration |
| `analysis.py` | CUPED variance reduction (synthetic data where true reduction is known); z-test correctness; CI computation; effect size; handling missing pre-period data |
| `sequential.py` | O'Brien-Fleming boundary values match known tables; maturation-aware information fraction; recommendation logic |
| `guardrails.py` | Session completion rate; crash rate; churn days (with fixed bug); threshold behavior; higher-is-worse vs lower-is-worse |
| `governance.py` | Config freeze enforcement; required fields validation; config change rejection after start; allowed changes (increase min_sample) |
| `audit.py` | Event logging; event retrieval; filtering by type; JSON serialization |
| `holdout.py` | Holdout assignment persistence; holdout exclusion from experiments |

### Integration tests

1. **Full lifecycle**: Create experiment → check eligibility → assign users → log exposure → check balance → run analysis → conclude → verify audit trail
2. **Daemon integration**: Daemon tick triggers SRM check, balance check, sequential test, guardrail check
3. **CUPED integration**: Users with pre-period data get variance-reduced estimates
4. **Stratification integration**: Users assigned across strata with correct within-stratum balance
5. **Mutual exclusion**: User in experiment A is excluded from experiment B
6. **Config freeze**: Attempting to change primary metric after start raises error

### Property-based tests (if time permits)

- Assignment uniformity: for any seed, variant distribution within a stratum is within expected bounds
- Salt isolation: changing the experiment name produces independent assignment
- CUPED: adjusted estimates have lower variance than unadjusted (on synthetic data)

---

## 13. Phased Roadmap

### Phase 1: Foundation (implement now)
- Refactor `experiments.py` into package structure
- Schema migration V103
- Eligibility engine with basic rules
- Stratified assignment (HSK × engagement)
- SRM detection with auto-pause
- Audit logging for all assignment decisions
- Fix churn_days guardrail bug
- Basic covariate balance checks
- Config freeze / pre-registration enforcement
- Update daemon with SRM and balance monitoring
- Comprehensive tests for all new modules

### Phase 2: Analysis upgrades (implement next)
- CUPED implementation
- Maturation-aware sequential testing
- Outcome-window configuration and enforcement
- HTE framework (pre-declared subgroups)
- Holdout group management
- Admin dashboard enhancements

### Phase 3: Advanced capabilities (support later)
- Exploratory HTE with Bayesian shrinkage
- Rerandomization for batch designs
- Shadow-mode policy learning
- Always-valid confidence sequences
- Multi-metric experiment support
- Experiment interaction detection

---

## 14. Risks / Failure Modes / What Could Go Wrong

### Implementation risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Breaking backward compatibility | Medium | High | Thin shim layer in `experiments.py`; all existing imports continue to work |
| Migration fails on production DB | Low | High | Test migration on copy of prod DB; make all ALTERs idempotent |
| Stratification creates very small cells | Medium | Medium | Dynamic collapsing; minimum cell size checks |
| CUPED leakage (pre-period contaminated) | Low | High | Strict pre-period end date enforcement; pre-period frozen at assignment |
| SRM false alarms (auto-pausing good experiments) | Low | Medium | Conservative threshold (p < 0.001); require sustained signal |
| Over-engineering slows experiment velocity | Medium | Medium | Phase 1 focuses on essentials; fancy methods deferred |
| Eligibility rules too restrictive (no one is eligible) | Medium | Low | Admin warning when eligible population < 50 users |

### Statistical risks

| Risk | Description | Mitigation |
|---|---|---|
| Stratification paradox | Stratifying on a post-treatment variable would introduce bias | Only stratify on pre-treatment characteristics |
| CUPED bias | If theta is estimated per-arm instead of pooled, estimates are biased | Pool theta estimation across both arms |
| Multiple testing | Running many experiments simultaneously inflates false positives | Benjamini-Hochberg correction; limit concurrent experiments |
| Peeking | Checking results frequently without alpha spending | O'Brien-Fleming spending function (already implemented) |
| Survivorship bias | Analyzing only users who remain active | ITT analysis (analyze all assigned users) |
| Goodhart failure | Optimizing a metric while degrading what it's supposed to measure | Mandatory Goodhart risk declarations; guardrail metrics |
| Small-sample noise | With n=100, results are noisy and effect sizes are exaggerated | Minimum sample sizes enforced; power analysis required |

### Organizational risks

| Risk | Description | Mitigation |
|---|---|---|
| Complexity discourages experimentation | System is so rigorous that no one bothers | Sensible defaults; most fields auto-filled; only hypothesis and primary_metric are truly burdensome |
| False sense of security | "We have stratification and CUPED so our results must be right" | Balance checks, SRM detection, and guardrails provide ongoing validity monitoring |
| Daemon over-autonomy | Daemon auto-starts/auto-concludes experiments without sufficient human review | Weekly digest; all auto-decisions are audit-logged; admin can override |
