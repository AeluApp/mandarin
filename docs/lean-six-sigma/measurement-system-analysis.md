# Measurement System Analysis (MSA) — Full Framework

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Related:** `msa.md` (grading engine Gage R&R detail)

---

## 1. Purpose

This document defines the MSA framework for all key quality metrics in Aelu, not just the grading engine. The grading engine MSA is covered in depth in `msa.md`; this document extends MSA to SRS half-life estimation, difficulty ratings, performance metrics, and content quality scoring.

---

## 2. MSA Summary by Metric

| Metric | Measurement Type | MSA Method | Expected %R&R | Status |
|--------|-----------------|------------|---------------|--------|
| Drill grading (correct/incorrect) | Deterministic attribute | Gage R&R (attribute agreement) | 0% | Designed in `msa.md` |
| Error classification (15 types) | Deterministic attribute | Gage R&R (attribute agreement) | 0% | Designed in `msa.md` |
| SRS half-life estimate | Continuous variable | Bias analysis | N/A — bias study | Not started |
| Content difficulty rating | Continuous variable | Linearity analysis | N/A — linearity study | Not started |
| API response time | Continuous variable | Gage R&R (variable) | < 10% target | Not started |
| Session completion rate | Ratio (computed) | Accuracy verification | 0% (formula-based) | Trivial |
| Streak count | Discrete count | Accuracy verification | 0% (logic-based) | Not started |

### Acceptance Criteria (per AIAG MSA 4th Edition)

| %R&R (of total variation) | Assessment |
|---------------------------|-----------|
| < 10% | Excellent — measurement system acceptable |
| 10% - 30% | Acceptable — may be suitable depending on application |
| > 30% | Unacceptable — measurement system needs improvement |

---

## 3. Gage R&R for Drill Scoring

**Full detail in `msa.md`.** Summary:

- The grading engine is a pure deterministic function
- Gage R&R = 0% by design (no randomness, no external state, no time dependence)
- Test plan: 50 samples x 3 repetitions = 150 measurements
- Expected result: 100% agreement across all repetitions
- The only measurement gap is speaking/shadowing drills (self-report, not automated)

---

## 4. Bias Analysis: SRS Half-Life Estimates

### 4.1 What We're Measuring

The `progress.half_life_days` field estimates how many days until a learner's recall probability for an item drops to 50%. This drives scheduling: items are surfaced for review when predicted recall approaches the threshold.

### 4.2 Reference Standard

The "true" half-life is unknowable — we can only estimate it from observed recall performance. The bias question is: **does our half-life model systematically over- or under-estimate actual recall?**

### 4.3 Bias Detection Method

```
For each item where a learner has 5+ review events:

1. At each review, the model predicted a recall probability (last_p_recall)
2. The learner either recalled correctly (correct=1) or not (correct=0)
3. Group reviews by predicted recall probability into buckets:
   [0.0-0.2), [0.2-0.4), [0.4-0.6), [0.6-0.8), [0.8-1.0]
4. For each bucket, compute actual recall rate = correct / total
5. Compare predicted vs. actual

If the model is unbiased:
   - Bucket [0.6-0.8) should have actual recall rate ~0.7
   - Bucket [0.8-1.0] should have actual recall rate ~0.9

If the model overestimates:
   - Actual recall < predicted for most buckets → items scheduled too late
   → Learner sees items they've already forgotten → frustrating

If the model underestimates:
   - Actual recall > predicted for most buckets → items scheduled too early
   → Learner reviews items they still remember → wasted time, less efficient
```

### 4.4 Bias Analysis Query

```sql
SELECT
    CASE
        WHEN last_p_recall < 0.2 THEN '0.0-0.2'
        WHEN last_p_recall < 0.4 THEN '0.2-0.4'
        WHEN last_p_recall < 0.6 THEN '0.4-0.6'
        WHEN last_p_recall < 0.8 THEN '0.6-0.8'
        ELSE '0.8-1.0'
    END AS predicted_bucket,
    COUNT(*) AS n_reviews,
    ROUND(AVG(correct), 3) AS actual_recall_rate,
    ROUND(AVG(last_p_recall), 3) AS avg_predicted_recall
FROM (
    SELECT
        re.correct,
        p.last_p_recall
    FROM review_event re
    JOIN progress p ON re.content_item_id = p.content_item_id
        AND re.user_id = p.user_id
    WHERE p.last_p_recall IS NOT NULL
        AND p.repetitions >= 5
)
GROUP BY predicted_bucket
ORDER BY predicted_bucket;
```

### 4.5 Acceptance Criteria

| Condition | Interpretation | Action |
|-----------|---------------|--------|
| Actual recall within ±0.10 of predicted for all buckets | No significant bias | None — model is well-calibrated |
| Actual recall consistently > predicted by 0.10+ | Model underestimates (conservative) | Acceptable but inefficient — items reviewed too early. Reduce review frequency. |
| Actual recall consistently < predicted by 0.10+ | Model overestimates (optimistic) | **Action required** — items reviewed too late. Shorten half-life estimates. |
| Mixed over/under across buckets | Non-linear bias | Investigate specific recall ranges; may need piecewise calibration |

---

## 5. Linearity Analysis: Difficulty Ratings Across HSK Levels

### 5.1 What We're Measuring

Each `content_item` has a `difficulty` rating (0.0 = trivial, 1.0 = very hard). HSK level provides an independent difficulty proxy (HSK 1 = easy, HSK 9 = hard). The linearity question: **does our difficulty rating scale linearly with observed difficulty across HSK levels?**

### 5.2 Method

```
1. For each HSK level (1-9), compute:
   - Average content_item.difficulty (the assigned rating)
   - Average actual error rate from review_event (observed difficulty)
2. Plot assigned difficulty (x-axis) vs. observed error rate (y-axis)
3. Fit linear regression: observed = a + b * assigned
4. Check:
   - R² > 0.80 → acceptable linearity
   - Slope b ≈ 1.0 → no compression or expansion
   - Intercept a ≈ 0.0 → no offset bias
```

### 5.3 Linearity Query

```sql
SELECT
    ci.hsk_level,
    ROUND(AVG(ci.difficulty), 3) AS avg_assigned_difficulty,
    COUNT(re.id) AS total_reviews,
    ROUND(1.0 - AVG(re.correct), 3) AS observed_error_rate
FROM content_item ci
JOIN review_event re ON re.content_item_id = ci.id
WHERE ci.hsk_level IS NOT NULL
GROUP BY ci.hsk_level
ORDER BY ci.hsk_level;
```

### 5.4 Acceptance Criteria

| Metric | Target | Interpretation |
|--------|--------|---------------|
| R² | > 0.80 | Difficulty ratings are meaningfully predictive |
| Slope | 0.7 - 1.3 | No severe compression or expansion |
| Residual pattern | Random | No systematic bias at specific HSK levels |

If linearity fails:
- Recalibrate `difficulty` values using observed error rates
- Consider per-HSK-level difficulty adjustment factors

---

## 6. API Response Time Measurement

### 6.1 Measurement System

API response time is measured server-side using Flask middleware:

```python
@app.before_request
def start_timer():
    g.start_time = time.perf_counter()

@app.after_request
def log_response_time(response):
    if hasattr(g, 'start_time'):
        elapsed_ms = (time.perf_counter() - g.start_time) * 1000
        # Log to performance tracking
    return response
```

### 6.2 Potential Measurement Errors

| Source | Risk | Mitigation |
|--------|------|-----------|
| Python GIL blocking `perf_counter()` | Low — GIL release is fast | Monitor for outliers > 10x median |
| SQLite lock wait included in timing | Medium — WAL mode reduces but doesn't eliminate | Separate DB query time from total response time |
| Network latency not captured | High — server-side timing excludes network | Add client-side `performance.now()` measurement |
| Cold start after idle | Low — Fly.io keeps machine warm | Exclude first request after > 5 min idle |

### 6.3 Gage R&R Applicability

For automated timing measurements:
- **Repeatability:** Same request should produce similar timing (within ~10% due to system load variance)
- **Reproducibility:** N/A — single measurement system (the server)
- **Resolution:** `time.perf_counter()` has microsecond resolution — more than sufficient for millisecond-scale measurements
- **Expected %R&R:** < 10% (measurement variation is small relative to actual response time variation across endpoints)

---

## 7. Session Completion Rate Measurement

### 7.1 Formula

```
completion_rate = items_completed / items_planned
```

Both values are stored in `session_log`. This is a deterministic calculation with no measurement uncertainty.

### 7.2 Potential Issues

| Issue | Impact | Mitigation |
|-------|--------|-----------|
| `items_planned = 0` | Division by zero | Filter: `WHERE items_planned > 0` |
| Session not properly closed (`ended_at IS NULL`) | `items_completed` may be stale | Exclude sessions where `session_outcome = 'started'` |
| User quits and re-starts (double session) | Inflates incomplete session count | Group by user + day for daily completion view |

---

## 8. MSA Review Schedule

| Analysis | Frequency | Trigger for Re-evaluation |
|----------|-----------|--------------------------|
| Gage R&R (grading) | Annually or on grading logic change | Any new drill type added, normalization rules changed |
| Bias analysis (SRS) | Quarterly | Half-life model parameters changed, user complaints about review timing |
| Linearity (difficulty) | Quarterly | New HSK levels seeded, difficulty recalibration applied |
| API timing validation | On infrastructure change | Server migration, database schema change, new middleware |
| All MSAs | On sigma phase gate | Required for tollgate review (see `tollgate-reviews.md`) |
