# SPC Control Chart Specifications — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Implementation:** See `spc-automation.md` for Python automation

---

## 1. Control Chart Types

| Chart Type | What It Monitors | Subgroup Size | Use Case |
|-----------|-----------------|---------------|----------|
| X-bar / R | Subgroup means and ranges | n = 5-10 | API latency per hour, drill accuracy per session |
| X-bar / S | Subgroup means and std dev | n > 10 | Daily review_event counts |
| I-MR (Individuals) | Individual values + moving range | n = 1 | Daily metrics where subgrouping isn't natural |
| p-chart | Proportion defective | Variable | Session completion rate, daily defect rate |

---

## 2. Chart Specifications

### 2.1 API Latency — X-bar / R Chart

| Parameter | Value |
|-----------|-------|
| **Metric** | Server-side API response time (ms) for `/api/session/*` endpoints |
| **Subgroup** | Each hour of operation; n = number of requests in that hour |
| **Subgroup size target** | n ≈ 5-25 requests per hour (varies with traffic) |
| **Sampling frequency** | Continuous (every request logged), charted hourly |
| **USL** | 500ms (from `ctq-registry.md` CTQ-004) |

**Control limit formulas:**

```
X-bar chart:
  Center line (CL) = X̿ (grand mean of subgroup means)
  UCL = X̿ + A₂ × R̄
  LCL = X̿ - A₂ × R̄

R chart:
  Center line (CL) = R̄ (mean of subgroup ranges)
  UCL = D₄ × R̄
  LCL = D₃ × R̄

Constants (from statistical tables):
  n=5:  A₂=0.577, D₃=0, D₄=2.114
  n=10: A₂=0.308, D₃=0.223, D₄=1.777
  n=25: A₂=0.153, D₃=0.459, D₄=1.541
```

**Data source:**

```sql
SELECT
    strftime('%Y-%m-%d %H:00', ce.created_at) AS hour_bucket,
    COUNT(*) AS n,
    AVG(CAST(ce.detail AS REAL)) AS x_bar,
    MAX(CAST(ce.detail AS REAL)) - MIN(CAST(ce.detail AS REAL)) AS range_val
FROM client_event ce
WHERE ce.category = 'performance'
  AND ce.event = 'api_response_time'
  AND ce.created_at >= datetime('now', '-7 days')
GROUP BY hour_bucket
HAVING COUNT(*) >= 3
ORDER BY hour_bucket;
```

---

### 2.2 Drill Accuracy Per Session — p-Chart

| Parameter | Value |
|-----------|-------|
| **Metric** | Proportion of drills answered correctly per session |
| **Subgroup** | Each completed session |
| **Subgroup size** | n = `items_completed` per session (typically 10-20) |
| **Sampling frequency** | Every session |

**Control limit formulas:**

```
p-chart (variable subgroup size):
  Center line (CL) = p̄ = total correct / total attempts (across all sessions)
  UCL_i = p̄ + 3 × sqrt(p̄(1-p̄)/nᵢ)
  LCL_i = max(0, p̄ - 3 × sqrt(p̄(1-p̄)/nᵢ))

  where nᵢ = number of drills in session i
```

**Note:** Drill accuracy is a function of learner ability AND content difficulty. The SRS scheduler targets ~70-85% accuracy by design (items are surfaced when recall probability is near threshold). A shift in the p-chart likely indicates a scheduling parameter change, not a learner behavior change.

**Data source:**

```sql
SELECT
    sl.id AS session_id,
    sl.started_at,
    sl.items_completed AS n,
    sl.items_correct,
    ROUND(CAST(sl.items_correct AS REAL) / NULLIF(sl.items_completed, 0), 3) AS p
FROM session_log sl
WHERE sl.items_completed > 0
  AND sl.session_outcome != 'started'
  AND sl.started_at >= datetime('now', '-30 days')
ORDER BY sl.started_at;
```

---

### 2.3 Daily Active Sessions — I-MR Chart

| Parameter | Value |
|-----------|-------|
| **Metric** | Number of completed sessions per day |
| **Subgroup** | n = 1 (one data point per day) |
| **Sampling frequency** | Daily |

**Control limit formulas:**

```
Individuals (I) chart:
  CL = X̄ (mean of daily session counts)
  UCL = X̄ + 2.66 × MR̄
  LCL = max(0, X̄ - 2.66 × MR̄)

Moving Range (MR) chart:
  CL = MR̄ (mean of absolute differences between consecutive days)
  UCL = 3.267 × MR̄
  LCL = 0

  where MR = |Xᵢ - Xᵢ₋₁|
```

**Data source:**

```sql
SELECT
    DATE(started_at) AS day,
    COUNT(*) AS sessions
FROM session_log
WHERE session_outcome != 'started'
  AND started_at >= datetime('now', '-60 days')
GROUP BY day
ORDER BY day;
```

---

### 2.4 Daily Defect Rate — p-Chart

| Parameter | Value |
|-----------|-------|
| **Metric** | Daily DPMO (defects per day / opportunities per day) |
| **Subgroup** | All review_events in a calendar day |
| **Subgroup size** | n = daily review_event count |
| **Sampling frequency** | Daily |

**Data source:**

```sql
-- Opportunities per day
SELECT
    DATE(created_at) AS day,
    COUNT(*) AS opportunities
FROM review_event
WHERE created_at >= datetime('now', '-30 days')
GROUP BY day;

-- Defects per day (grade appeals + crashes)
SELECT
    DATE(created_at) AS day,
    COUNT(*) AS defects
FROM grade_appeal
WHERE status = 'upheld'
  AND created_at >= datetime('now', '-30 days')
GROUP BY day

UNION ALL

SELECT
    DATE(timestamp) AS day,
    COUNT(*) AS defects
FROM crash_log
WHERE request_path LIKE '/api/session%'
  AND timestamp >= datetime('now', '-30 days')
GROUP BY day;
```

---

## 3. Out-of-Control Rules (Western Electric)

Apply these rules to detect non-random patterns. Any rule violation triggers the reaction plan (section 4).

| Rule | Condition | What It Indicates |
|------|-----------|------------------|
| **Rule 1** | 1 point beyond 3σ (outside UCL or LCL) | Outlier — assignable cause likely |
| **Rule 2** | 9 consecutive points on same side of center line | Shift — process mean has moved |
| **Rule 3** | 6 consecutive points steadily increasing or decreasing | Trend — process is drifting |
| **Rule 4** | 14 consecutive points alternating up and down | Oscillation — two interleaved processes |
| **Rule 5** | 2 out of 3 consecutive points beyond 2σ (same side) | Early warning of shift |
| **Rule 6** | 4 out of 5 consecutive points beyond 1σ (same side) | Early warning of shift |
| **Rule 7** | 15 consecutive points within 1σ of center (either side) | Stratification — data may be artificially grouped |
| **Rule 8** | 8 consecutive points beyond 1σ (either side) | Mixture — two distinct populations |

### Rule Detection in Aelu Context

| Rule | Most Likely Aelu Cause |
|------|----------------------|
| Rule 1 (outlier) on API latency | Database lock contention, Fly.io resource spike, unoptimized query |
| Rule 2 (shift) on drill accuracy | Scheduler parameter change, new content items with different difficulty |
| Rule 3 (trend) on daily sessions | User growth (up) or churn (down) |
| Rule 5 (early shift) on defect rate | Recent deploy introduced a subtle bug |

---

## 4. Reaction Plan

When an out-of-control condition is detected:

### Severity 1: Rule 1 Violation (Point Beyond 3σ)

| Step | Action | Timeline |
|------|--------|----------|
| 1 | Log `WARNING` to `improvement_log` with chart name, rule violated, data point value | Automated (immediate) |
| 2 | Check `crash_log` and `client_error_log` for correlated errors | Within 1 hour |
| 3 | Check recent deploys (`git log --since='2 days ago'`) | Within 1 hour |
| 4 | If assignable cause found: fix and verify point returns to control | Within 24 hours |
| 5 | If no assignable cause: monitor next 3 data points. If in control, record as isolated incident. | Next 3 subgroups |
| 6 | Update `improvement_log` with resolution | On resolution |

### Severity 2: Rule 2/3 Violation (Shift or Trend)

| Step | Action | Timeline |
|------|--------|----------|
| 1 | Log `WARNING` to `improvement_log` | Automated (immediate) |
| 2 | Identify when the shift/trend began (which data point) | Within 4 hours |
| 3 | Correlate with: deploys, content changes, user behavior changes, infrastructure changes | Within 4 hours |
| 4 | Apply 5 Whys analysis (see `5-whys-template.md`) | Within 24 hours |
| 5 | Implement corrective action | Within 1 week |
| 6 | Recalculate control limits if process has genuinely improved (not just returned to baseline) | After 20+ data points post-fix |

### Severity 3: Rule 5/6 Violation (Early Warning)

| Step | Action | Timeline |
|------|--------|----------|
| 1 | Log `INFO` to `improvement_log` | Automated (immediate) |
| 2 | Monitor — wait for next 5 data points | Next 5 subgroups |
| 3 | If escalates to Rule 1 or 2: follow Severity 1/2 plan | As needed |
| 4 | If returns to normal: no action, record as noise | After 5 in-control points |

---

## 5. Control Limit Recalculation

Control limits should be recalculated when:

1. **Process improvement confirmed** — After a sigma phase gate (see `sigma-progression.md`), recalculate limits using post-improvement data only. The improved process has new natural variation.

2. **Minimum data points:** 20-25 subgroups for initial limits. Recalculate after 50+ subgroups for stability.

3. **Exclude out-of-control points** from limit calculations (they represent assignable causes, not natural variation).

4. **Never recalculate to hide problems.** If the process is producing out-of-control points because it has genuinely degraded, fix the process rather than widening the limits.

---

## 6. Chart Review Cadence

| Chart | Review Frequency | Reviewer |
|-------|-----------------|----------|
| API latency X-bar/R | Weekly (automated alerts for violations) | Jason |
| Drill accuracy p-chart | Weekly | Jason |
| Daily sessions I-MR | Weekly | Jason |
| Daily defect rate p-chart | Weekly | Jason |
| All charts comprehensive review | Monthly (at sigma review) | Jason |

---

## 7. Implementation Reference

See `spc-automation.md` for:
- Python script to generate charts from SQLite data
- Automated rule violation detection
- Alert mechanism (log + notification)
- matplotlib chart templates
