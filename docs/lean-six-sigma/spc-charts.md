# Statistical Process Control (SPC) Plan — Aelu

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Monitoring Cadence:** Daily extraction, monthly control limit recalculation

---

## 1. Control Charts Overview

| Metric | Chart Type | Subgroup | Target | UCL Basis | LCL Basis | Sampling |
|--------|-----------|----------|--------|-----------|-----------|----------|
| Session completion rate | p-chart (proportion) | Daily | 85% | X-bar + 3 sigma | X-bar - 3 sigma | All sessions |
| Drill accuracy | p-chart (proportion) | Daily | 70% | Dynamic (see below) | Dynamic (see below) | All review events |
| API latency p95 | Individuals (I-MR) chart | Per request | < 500ms | X-bar + 3*MR-bar/d2 | X-bar - 3*MR-bar/d2 | Sampled from server logs |
| Error focus resolution rate | p-chart | Weekly | 50% | X-bar + 3 sigma | X-bar - 3 sigma | All resolved error_focus entries |

---

## 2. Chart 1: Session Completion Rate

### Definition
Proportion of planned drill items completed per session: `items_completed / items_planned`.

### Specification
- **Target (center line):** 85%
- **UCL warning:** 98% (suspiciously high — sessions may be too easy or too short)
- **LCL warning:** 65% (too many early exits — sessions may be too hard or too long)
- **Out-of-control signal:** 3 consecutive points below LCL, or 1 point below 50%

### Data Extraction Query

```sql
-- Daily session completion rate (p-chart data)
SELECT
    DATE(started_at) AS day,
    COUNT(*) AS sessions,
    SUM(items_completed) AS total_completed,
    SUM(items_planned) AS total_planned,
    ROUND(100.0 * SUM(items_completed) / NULLIF(SUM(items_planned), 0), 1) AS completion_pct,
    SUM(CASE WHEN early_exit = 1 THEN 1 ELSE 0 END) AS early_exits,
    AVG(items_planned) AS avg_planned,
    AVG(items_completed) AS avg_completed
FROM session_log
WHERE user_id = :user_id
    AND started_at >= date('now', '-30 days')
    AND items_planned > 0
GROUP BY day
ORDER BY day;
```

### Control Limit Calculation

```sql
-- Compute p-bar and control limits from historical data (monthly recalculation)
WITH daily AS (
    SELECT
        DATE(started_at) AS day,
        SUM(items_completed) AS completed,
        SUM(items_planned) AS planned
    FROM session_log
    WHERE user_id = :user_id
        AND started_at >= date('now', '-30 days')
        AND items_planned > 0
    GROUP BY day
)
SELECT
    ROUND(100.0 * SUM(completed) / NULLIF(SUM(planned), 0), 1) AS p_bar,
    -- For p-chart: UCL = p_bar + 3 * sqrt(p_bar * (1-p_bar) / n_bar)
    -- LCL = p_bar - 3 * sqrt(p_bar * (1-p_bar) / n_bar)
    AVG(planned) AS n_bar,  -- average subgroup size
    COUNT(*) AS num_subgroups
FROM daily;
```

Python calculation for limits:
```python
import math

def p_chart_limits(p_bar: float, n_bar: float):
    """Compute UCL and LCL for a p-chart."""
    sigma = math.sqrt(p_bar * (1 - p_bar) / n_bar)
    ucl = min(1.0, p_bar + 3 * sigma)
    lcl = max(0.0, p_bar - 3 * sigma)
    return ucl, lcl
```

### Reaction Plan
| Signal | Meaning | Action |
|--------|---------|--------|
| Point below LCL (65%) | Abnormally low completion | Check: was session too long? Were error-focus items dominating? Was there a bug? |
| 3 consecutive below target (85%) | Systematic decline | Review scheduler parameters, check for content difficulty spike |
| Point above UCL (98%) | Suspiciously high | Check: is the session too short? Too easy? Are hard items being filtered out? |
| Trend of 7+ consecutive rising or falling | Process drift | Investigate: is the adaptive length algorithm over-adjusting? |

---

## 3. Chart 2: Drill Accuracy

### Definition
Proportion of drill responses graded correct: `items_correct / items_completed` per session.

### Specification
- **Target (center line):** 70% (optimal difficulty per desirable difficulty theory)
- **UCL warning:** 90% (too easy — learner is being under-challenged)
- **LCL warning:** 50% (too hard — learner is being overwhelmed)
- **Ideal range:** 65-80% (Goldilocks zone for learning)

### Data Extraction Query

```sql
-- Daily drill accuracy (p-chart data)
SELECT
    DATE(created_at) AS day,
    COUNT(*) AS total_drills,
    SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) AS correct,
    ROUND(100.0 * SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS accuracy_pct
FROM review_event
WHERE user_id = :user_id
    AND created_at >= date('now', '-30 days')
GROUP BY day
ORDER BY day;
```

### Accuracy by Modality (Sub-Charts)

```sql
-- Accuracy breakdown by modality (separate control charts per modality)
SELECT
    modality,
    DATE(created_at) AS day,
    COUNT(*) AS drills,
    ROUND(100.0 * SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS accuracy_pct
FROM review_event
WHERE user_id = :user_id
    AND created_at >= date('now', '-30 days')
GROUP BY modality, day
ORDER BY modality, day;
```

### Reaction Plan
| Signal | Meaning | Action |
|--------|---------|--------|
| Accuracy > 90% for 3+ sessions | Too easy | Increase new item ratio (`MAX_NEW_ITEM_RATIO`), reduce review of mastered items |
| Accuracy < 50% for 3+ sessions | Too hard | Reduce new items, increase scaffold hints, check if HSK level is too high |
| Accuracy < 50% on single modality | Modality-specific difficulty | Check if specific drill types are poorly calibrated |
| Sudden accuracy drop (> 15pp day-over-day) | Possible bug or content issue | Check error_log for new error patterns, review recent content changes |

### Accuracy Zone Interpretation

```
100% ─────────── Too easy (system failure: not challenging enough)
 90% ─ ─ ─ ─ ─ ─ UCL warning
 80% ┄┄┄┄┄┄┄┄┄┄┄ Upper Goldilocks
 70% ━━━━━━━━━━━ TARGET (optimal challenge)
 65% ┄┄┄┄┄┄┄┄┄┄┄ Lower Goldilocks
 50% ─ ─ ─ ─ ─ ─ LCL warning
  0% ─────────── Complete failure
```

---

## 4. Chart 3: API Latency p95

### Definition
95th percentile response time for API requests, measured server-side.

### Specification
- **Target:** < 500ms
- **UCL:** 1000ms (degraded but functional)
- **Critical threshold:** 3000ms (unacceptable — user will perceive lag)
- **Chart type:** Individuals chart (I-MR) — each data point is the p95 for a time window

### Data Extraction

Currently, API latency is not instrumented in the database. Proposed implementation:

```python
# In middleware.py — add response time logging
import time

@app.before_request
def _start_timer():
    g.start_time = time.monotonic()

@app.after_request
def _log_response_time(response):
    elapsed_ms = (time.monotonic() - g.start_time) * 1000
    if elapsed_ms > 100:  # Only log slow requests to avoid noise
        app.logger.info("LATENCY path=%s method=%s ms=%.0f status=%d",
                        request.path, request.method, elapsed_ms, response.status_code)
    return response
```

Alternatively, use Fly.io's built-in metrics:
```bash
# Fly.io provides request latency metrics via Prometheus
fly metrics --app mandarin --query 'histogram_quantile(0.95, rate(fly_app_http_response_time_seconds_bucket[5m]))'
```

### Control Limit Calculation (I-MR Chart)

```python
def imr_limits(data: list):
    """Compute control limits for an Individuals-Moving Range chart."""
    n = len(data)
    x_bar = sum(data) / n

    # Moving ranges
    mrs = [abs(data[i] - data[i-1]) for i in range(1, n)]
    mr_bar = sum(mrs) / len(mrs)

    d2 = 1.128  # constant for subgroup size 2

    ucl_x = x_bar + 3 * mr_bar / d2
    lcl_x = max(0, x_bar - 3 * mr_bar / d2)

    ucl_mr = 3.267 * mr_bar  # D4 * MR-bar for n=2

    return {
        "x_bar": x_bar,
        "ucl": ucl_x,
        "lcl": lcl_x,
        "mr_bar": mr_bar,
        "ucl_mr": ucl_mr,
    }
```

### Reaction Plan
| Signal | Meaning | Action |
|--------|---------|--------|
| p95 > 500ms | Approaching threshold | Check: database query performance, Fly.io machine health |
| p95 > 1000ms | Degraded performance | Investigate: SQLite lock contention, slow queries, memory pressure |
| p95 > 3000ms | Unacceptable latency | Emergency: check Fly.io machine state, restart if needed, check for runaway queries |
| Trend of 5+ consecutive increases | Performance degradation trend | Proactive: review recent code changes, check DB size growth, consider indexing |

---

## 5. Chart 4: Error Focus Resolution Rate

### Definition
Proportion of error_focus entries that reach `resolved = 1` within 14 days of `first_flagged_at`.

### Specification
- **Target:** 50% resolved within 14 days
- **UCL:** 90% (suspiciously high — may indicate error_focus is too easy to resolve)
- **LCL:** 20% (too few resolved — error remediation is not working)

### Data Extraction Query

```sql
-- Weekly error focus resolution rate
SELECT
    strftime('%Y-W%W', first_flagged_at) AS week_flagged,
    COUNT(*) AS total_flagged,
    SUM(CASE WHEN resolved = 1
         AND julianday(resolved_at) - julianday(first_flagged_at) <= 14
         THEN 1 ELSE 0 END) AS resolved_14d,
    ROUND(100.0 * SUM(CASE WHEN resolved = 1
         AND julianday(resolved_at) - julianday(first_flagged_at) <= 14
         THEN 1 ELSE 0 END) / COUNT(*), 1) AS resolution_rate_pct
FROM error_focus
WHERE user_id = :user_id
    AND first_flagged_at >= date('now', '-12 weeks')
GROUP BY week_flagged
ORDER BY week_flagged;
```

---

## 6. SPC Operating Procedures

### 6.1 Daily Check (2 minutes)
1. Run completion rate and accuracy queries
2. Check for any out-of-control signals
3. If signal found: investigate before next session

### 6.2 Weekly Review (10 minutes)
1. Plot weekly data points for all 4 charts
2. Check for trends (7-point rule: 7 consecutive above or below center line)
3. Check for patterns (oscillation, clustering)
4. Update error focus resolution tracking

### 6.3 Monthly Recalculation (30 minutes)
1. Recalculate control limits from last 30 days of data
2. Exclude any known special-cause points from limit calculation
3. Compare new limits to previous month's limits
4. Document any limit changes and rationale

### 6.4 Nelson Rules for Out-of-Control Detection

Apply these rules to all control charts:

| Rule | Description | Detection |
|------|-----------|-----------|
| 1 | Single point beyond 3-sigma | 1 point outside UCL or LCL |
| 2 | 9 consecutive on same side of center | Shift in process mean |
| 3 | 6 consecutive increasing or decreasing | Trend |
| 4 | 14 consecutive alternating up/down | Over-adjustment |
| 5 | 2 of 3 consecutive beyond 2-sigma | Near-violation pattern |

---

## 7. Special Cause vs. Common Cause Log

When an out-of-control signal is detected, classify it:

```
# SPC Signal Log — YYYY-MM-DD

**Chart:** [which chart]
**Signal:** [which Nelson rule]
**Value:** [observed value]
**Limits:** UCL=X, CL=X, LCL=X

**Classification:** Special cause / Common cause

**If special cause:**
- Root cause: [what happened]
- Action taken: [fix applied]
- Date resolved: [when fixed]

**If common cause:**
- Process change needed: [what to adjust]
- New target: [if target should change]
```

---

## 8. Automation Roadmap

Current state: Manual SQL queries, manual chart plotting.

| Phase | Capability | Status |
|-------|-----------|--------|
| Phase 1 | SQL queries documented and tested | Complete (this document) |
| Phase 2 | CLI command: `./run spc` to generate current data | Not started |
| Phase 3 | Automated daily extraction to JSON | Not started |
| Phase 4 | Web dashboard with control charts | Not started |
| Phase 5 | Automated alerting on Nelson rule violations | Not started |
