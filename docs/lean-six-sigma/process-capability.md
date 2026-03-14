# Process Capability Analysis (Cp/Cpk) — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10

---

## 1. Overview

Process capability measures whether a process can consistently produce output within specification limits. For Aelu, "processes" are system operations (API response, drill rendering, SRS scheduling, session loading) and "specifications" are the CTQ limits from `ctq-registry.md`.

---

## 2. Formulas

### Cp — Process Capability (potential)

Measures spread of process relative to spec width. Assumes process is centered.

```
Cp = (USL - LSL) / (6σ)

Where:
  USL = Upper Specification Limit
  LSL = Lower Specification Limit
  σ = process standard deviation (estimated from sample data)
```

For one-sided specs (only USL or only LSL):

```
Cp_upper = (USL - μ) / (3σ)    — when only USL exists
Cp_lower = (μ - LSL) / (3σ)    — when only LSL exists
```

### Cpk — Process Capability (actual)

Accounts for process centering. Always <= Cp.

```
Cpk = min((USL - μ) / (3σ), (μ - LSL) / (3σ))

For one-sided:
Cpk_upper = (USL - μ) / (3σ)
Cpk_lower = (μ - LSL) / (3σ)
```

### Interpretation

| Cpk Value | Interpretation | Action |
|-----------|---------------|--------|
| < 1.00 | Process is not capable — output frequently exceeds spec | **Immediate action required.** Root cause analysis, process redesign. |
| 1.00 - 1.33 | Marginally capable — some output near spec limits | **Action recommended.** Tighten process, reduce variation. |
| 1.33 - 1.67 | Capable — process comfortably within spec | Monitor. No action unless trending down. |
| > 1.67 | Highly capable — wide margin | Maintain. Consider tightening specs. |

**Aelu trigger: Cpk < 1.33 requires a documented improvement action in `improvement_log`.**

---

## 3. Process: API Response Time

### Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| USL | 500ms (p95) | `ctq-registry.md` CTQ-004 |
| LSL | N/A (faster is always better; 0ms is theoretical minimum) |
| Target | < 200ms (p50) |

### Data Collection Query

```sql
-- Requires timing middleware (see measurement-system-analysis.md section 6)
-- Once instrumented, response times logged to client_event:
SELECT
    CAST(detail AS REAL) AS response_ms
FROM client_event
WHERE category = 'performance'
  AND event = 'api_response_time'
  AND created_at >= datetime('now', '-30 days')
ORDER BY response_ms;
```

### Calculation (One-Sided, USL Only)

```
μ = mean response time (ms)
σ = standard deviation of response times

Cpk = (USL - μ) / (3σ) = (500 - μ) / (3σ)

Example:
  μ = 120ms, σ = 60ms
  Cpk = (500 - 120) / (3 * 60) = 380 / 180 = 2.11  ← Highly capable

Example (degraded):
  μ = 300ms, σ = 100ms
  Cpk = (500 - 300) / (3 * 100) = 200 / 300 = 0.67  ← NOT capable
```

### Notes

- API response times are typically right-skewed (log-normal). Consider using log-transformed data for Cpk calculation or use Ppk (performance index) instead.
- Separate calculation by endpoint category: grading endpoints (`/api/session/grade`), session planning (`/api/session/start`), dashboard (`/api/dashboard`).
- SQLite WAL mode means read queries are fast but write queries can contend. Monitor write-heavy endpoints separately.

---

## 4. Process: Drill Render Time

### Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| USL | 200ms | `ctq-registry.md` |
| LSL | N/A |
| Target | < 100ms |

### Data Collection

Client-side measurement using `performance.now()`:

```javascript
// In drill rendering code:
const t0 = performance.now();
renderDrill(drillData);
const t1 = performance.now();
logEvent('performance', 'drill_render_time', Math.round(t1 - t0));
```

### Calculation

```
Cpk = (200 - μ) / (3σ)

Example:
  μ = 50ms, σ = 30ms
  Cpk = (200 - 50) / (3 * 30) = 150 / 90 = 1.67  ← Capable
```

### Stratification

Calculate Cpk separately for:
- Simple drills (MC, tone) — expected lower render time
- Complex drills (sentence_build, word_order) — more DOM manipulation
- Listening drills — includes TTS synthesis setup

---

## 5. Process: SRS Scheduling Accuracy

### Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| Target | Review on the scheduled day |
| USL | +2.0 days late (review too late → learner may have forgotten) |
| LSL | -0.5 days early (review slightly early is OK; much earlier wastes time) |

### Data Collection Query

```sql
SELECT
    julianday(re.created_at) - julianday(p.next_review_date) AS deviation_days
FROM review_event re
JOIN progress p ON re.content_item_id = p.content_item_id
    AND re.user_id = p.user_id
WHERE p.next_review_date IS NOT NULL
  AND p.repetitions >= 2  -- exclude first reviews (no prior schedule)
  AND re.created_at >= datetime('now', '-30 days');
```

### Calculation (Two-Sided)

```
Cp = (USL - LSL) / (6σ) = (2.0 - (-0.5)) / (6σ) = 2.5 / (6σ)
Cpk = min((USL - μ) / (3σ), (μ - LSL) / (3σ))
    = min((2.0 - μ) / (3σ), (μ + 0.5) / (3σ))

Example (well-centered):
  μ = 0.3 days, σ = 0.5 days
  Cp = 2.5 / (6 * 0.5) = 0.83
  Cpk = min((2.0 - 0.3) / (1.5), (0.3 + 0.5) / (1.5))
      = min(1.13, 0.53)
      = 0.53  ← NOT capable (high variation)

Example (tight):
  μ = 0.1 days, σ = 0.2 days
  Cp = 2.5 / (6 * 0.2) = 2.08
  Cpk = min((2.0 - 0.1) / (0.6), (0.1 + 0.5) / (0.6))
      = min(3.17, 1.0)
      = 1.0  ← Marginally capable
```

### Special Considerations

- **User absence is not a process defect.** If a user doesn't open the app for 5 days, the deviation is user behavior, not system failure. Filter: only include deviations where the user had a session that day (they were active but the scheduler chose other items).
- **Weekday/weekend patterns:** Users may study less on weekends. Stratify by day-of-week.
- **Gap-aware scheduling:** After a long absence, the scheduler deliberately prioritizes overdue items. The first session back will have large positive deviations — exclude these from Cpk (they represent recovery, not failure).

---

## 6. Process: Session Load Time

### Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| USL | 3,000ms (3 seconds) | `ctq-registry.md` |
| LSL | N/A |
| Target | < 2,000ms |

### Data Collection

```sql
SELECT
    CAST(detail AS REAL) AS load_time_ms
FROM client_event
WHERE category = 'performance'
  AND event = 'session_load_time'
  AND created_at >= datetime('now', '-30 days');
```

### Calculation

```
Cpk = (3000 - μ) / (3σ)

Example:
  μ = 1200ms, σ = 400ms
  Cpk = (3000 - 1200) / (3 * 400) = 1800 / 1200 = 1.50  ← Capable
```

### Stratification

- By platform: web vs. iOS (Capacitor) vs. CLI
- By connection quality: if available from client telemetry
- By session type: standard vs. diagnostic vs. catchup (different planning complexity)

---

## 7. Capability Dashboard Query

Run monthly to assess all processes at once:

```sql
-- This is a template. Replace placeholder columns with actual instrumented data.
-- Requires: performance data logged to client_event with appropriate event names.

SELECT
    'api_response_time' AS process,
    AVG(CAST(detail AS REAL)) AS mean_ms,
    -- SQLite doesn't have STDEV; compute in Python or use:
    -- sqrt(avg(x*x) - avg(x)*avg(x)) as approx stdev
    SQRT(AVG(CAST(detail AS REAL) * CAST(detail AS REAL))
         - AVG(CAST(detail AS REAL)) * AVG(CAST(detail AS REAL))) AS stdev_ms,
    500 AS usl_ms,
    ROUND((500 - AVG(CAST(detail AS REAL)))
          / (3 * SQRT(AVG(CAST(detail AS REAL) * CAST(detail AS REAL))
                      - AVG(CAST(detail AS REAL)) * AVG(CAST(detail AS REAL)))), 2) AS cpk
FROM client_event
WHERE category = 'performance' AND event = 'api_response_time'
  AND created_at >= datetime('now', '-30 days')

UNION ALL

SELECT
    'session_load_time',
    AVG(CAST(detail AS REAL)),
    SQRT(AVG(CAST(detail AS REAL) * CAST(detail AS REAL))
         - AVG(CAST(detail AS REAL)) * AVG(CAST(detail AS REAL))),
    3000,
    ROUND((3000 - AVG(CAST(detail AS REAL)))
          / (3 * SQRT(AVG(CAST(detail AS REAL) * CAST(detail AS REAL))
                      - AVG(CAST(detail AS REAL)) * AVG(CAST(detail AS REAL)))), 2)
FROM client_event
WHERE category = 'performance' AND event = 'session_load_time'
  AND created_at >= datetime('now', '-30 days');
```

---

## 8. Improvement Triggers

| Condition | Action | Reference |
|-----------|--------|-----------|
| Cpk < 1.00 | **Stop.** Process is producing out-of-spec output. Immediate root cause analysis. Log to `improvement_log`. | `5-whys-template.md` |
| Cpk 1.00 - 1.33 | **Act.** Schedule improvement within current sprint. Identify largest variance contributor. | `fishbone-diagrams.md` |
| Cpk drops by > 0.3 between measurements | **Investigate.** Something changed. Check recent deploys, data volume, user patterns. | `control-charts.md` |
| Cpk > 2.0 for 6+ months | **Tighten spec.** The process is much better than required. Consider reducing USL to drive further improvement or reallocate effort. | `ctq-registry.md` |

---

## 9. Assumptions and Limitations

1. **Normality assumption:** Cp/Cpk formulas assume normally distributed data. API response times and render times are typically right-skewed. For skewed data, use Box-Cox transformation or report Ppk (performance index using overall standard deviation) instead of Cpk.

2. **Sample size:** Minimum 30 data points for meaningful Cp/Cpk. With < 30 points, report confidence intervals. For n=30, the 95% confidence interval on Cpk is approximately Cpk ± 0.35.

3. **Process stability:** Cp/Cpk are only meaningful for stable processes. Run control chart analysis (`control-charts.md`) first. If the process is out of control, fix assignable causes before computing capability.

4. **SQLite limitation:** SQLite does not have built-in STDEV function. Use `SQRT(AVG(x*x) - AVG(x)*AVG(x))` as population standard deviation approximation, or compute in Python with `statistics.stdev()` for sample standard deviation.
