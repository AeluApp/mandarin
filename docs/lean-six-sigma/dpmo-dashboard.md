# DPMO Dashboard — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Measurement Frequency:** Weekly

---

## 1. Definitions

| Term | Aelu Definition |
|------|----------------|
| **Unit** | One drill session (a complete session_log entry with `session_outcome != 'started'`) |
| **Opportunity** | Each drill presentation within a session (one row in `review_event` per opportunity) |
| **Defect** | A drill graded incorrectly due to **system fault** — NOT a learner error. A defect is a case where the system's grading, content, scheduling, or rendering caused a wrong outcome. |
| **DPMO** | Defects Per Million Opportunities = `(defects / opportunities) * 1,000,000` |

### What Counts as a Defect

| Defect Type | How Detected | Table/Source |
|-------------|-------------|-------------|
| **False negative** — correct answer graded wrong | Upheld `grade_appeal` | `grade_appeal WHERE status = 'upheld'` |
| **False positive** — wrong answer graded correct | Content audit finds accepted-answer bug | Manual review, logged to `improvement_log` |
| **Ambiguous content** — drill question is unanswerable or misleading | Grade appeal + error_focus with `error_type = 'other'` recurring 3+ times on same item | `error_focus WHERE error_type = 'other' AND error_count >= 3` |
| **Rendering failure** — drill fails to display correctly | Client error log | `client_error_log WHERE error_type LIKE '%drill%'` |
| **Audio failure** — TTS fails to play on listening drill | Client event | `client_event WHERE event = 'tts_error'` |
| **Session crash** — session terminates unexpectedly | Crash log | `crash_log WHERE request_path LIKE '/api/session%'` |
| **SRS misfire** — item scheduled but data is corrupted | Progress table audit | `progress WHERE next_review_date IS NOT NULL AND interval_days <= 0` |

### What Does NOT Count as a Defect

- Learner answers incorrectly (this is normal learning, not a system defect)
- Learner quits session early by choice (`early_exit = 1` is user behavior, not system fault)
- Learner presses B (boredom flag) — this is feedback signal, not defect
- Network timeout on user's side (device/connectivity issue)

---

## 2. DPMO Calculation Queries

### 2.1 Total Opportunities (All Time)

```sql
SELECT COUNT(*) AS total_opportunities
FROM review_event;
```

### 2.2 Total Opportunities (Rolling 30 Days)

```sql
SELECT COUNT(*) AS opportunities_30d
FROM review_event
WHERE created_at >= datetime('now', '-30 days');
```

### 2.3 Defect Count — Grade Appeals Upheld

```sql
SELECT COUNT(*) AS grading_defects
FROM grade_appeal
WHERE status = 'upheld'
  AND created_at >= datetime('now', '-30 days');
```

### 2.4 Defect Count — Ambiguous Content Items

```sql
SELECT COUNT(DISTINCT ef.content_item_id) AS ambiguous_items
FROM error_focus ef
WHERE ef.error_type = 'other'
  AND ef.error_count >= 3
  AND ef.resolved = 0;
```

To convert ambiguous items to opportunity-level defects, count how many times those items were presented:

```sql
SELECT COUNT(*) AS ambiguous_drill_presentations
FROM review_event re
WHERE re.content_item_id IN (
    SELECT content_item_id FROM error_focus
    WHERE error_type = 'other' AND error_count >= 3 AND resolved = 0
)
AND re.created_at >= datetime('now', '-30 days');
```

### 2.5 Defect Count — Rendering/Client Errors During Drills

```sql
SELECT COUNT(*) AS render_defects
FROM client_error_log
WHERE error_type LIKE '%drill%'
  AND timestamp >= datetime('now', '-30 days');
```

### 2.6 Defect Count — Session Crashes

```sql
SELECT COUNT(*) AS session_crashes
FROM crash_log
WHERE request_path LIKE '/api/session%'
  AND timestamp >= datetime('now', '-30 days');
```

### 2.7 Defect Count — SRS Data Corruption

```sql
SELECT COUNT(*) AS srs_corruption
FROM progress
WHERE next_review_date IS NOT NULL
  AND interval_days <= 0
  AND repetitions > 0;
```

### 2.8 Combined DPMO Calculation

```sql
-- Run each defect query above, sum results, then:
-- DPMO = (total_defects / total_opportunities) * 1,000,000

-- Example with hypothetical values:
-- total_defects = 5 (2 grade appeals + 1 render error + 2 crashes)
-- total_opportunities = 1,500 (review_event rows in 30 days)
-- DPMO = (5 / 1,500) * 1,000,000 = 3,333 DPMO
-- Sigma level: ~4.2σ (see conversion table below)
```

---

## 3. Sigma Conversion Table

| DPMO | Sigma Level | Yield (%) | Aelu Context |
|------|-------------|-----------|-------------|
| 691,462 | 1.0 | 30.85% | Unusable — 7 out of 10 drills have system issues |
| 308,538 | 2.0 | 69.15% | Very poor — 1 in 3 drills affected |
| 66,807 | 3.0 | 93.32% | Minimum viable — 1 in 15 drills affected |
| 6,210 | 4.0 | 99.38% | Good — 1 in 161 drills affected |
| 1,350 | 4.5 | 99.87% | **Aelu target** — 1 in 741 drills affected |
| 233 | 5.0 | 99.977% | Excellent — 1 in 4,292 drills affected |
| 3.4 | 6.0 | 99.99966% | World class — effectively defect-free |

**Note:** These are standard sigma levels with 1.5σ process shift per industry convention.

---

## 4. Target Progression

| Phase | Target Date | DPMO Target | Sigma Target | Key Actions |
|-------|-----------|-------------|-------------|-------------|
| **Baseline** | 2026-03 (now) | Measure current | ~2.1σ (estimated) | Instrument all defect sources; establish baseline |
| **Phase 1** | 2026 Q2 | < 66,807 | 3.0σ | Fix top 3 Pareto defect categories; add client error instrumentation |
| **Phase 2** | 2026 Q3 | < 6,210 | 4.0σ | Resolve all ambiguous content items; automated SPC alerts |
| **Phase 3** | 2026 Q4 | < 1,350 | 4.5σ | Control phase — sustained improvement, all CTQs within spec |

### Baseline Estimation Rationale

Current sigma is estimated at ~2.1σ based on:
- Small user base (mostly developer testing) means defect detection rate is low
- No systematic grade appeal review process in place
- Client error instrumentation exists but TTS/render errors not categorized as defects yet
- Known content gaps (multiple valid English translations not accepted — see `msa.md` section 3.3)
- The 2.1σ estimate is deliberately conservative to avoid optimism bias

---

## 5. Dashboard Views

### 5.1 Weekly DPMO Trend

```sql
SELECT
    strftime('%Y-W%W', re.created_at) AS week,
    COUNT(*) AS opportunities,
    -- Defects must be joined from multiple sources
    -- This is a simplified view counting only grade appeals
    (SELECT COUNT(*) FROM grade_appeal ga
     WHERE ga.status = 'upheld'
     AND strftime('%Y-W%W', ga.created_at) = strftime('%Y-W%W', re.created_at)
    ) AS defects_grading,
    (SELECT COUNT(*) FROM crash_log cl
     WHERE cl.request_path LIKE '/api/session%'
     AND strftime('%Y-W%W', cl.timestamp) = strftime('%Y-W%W', re.created_at)
    ) AS defects_crash
FROM review_event re
GROUP BY week
ORDER BY week DESC
LIMIT 12;
```

### 5.2 DPMO by Defect Category

```sql
-- Category breakdown for Pareto analysis (see pareto-analysis.md)
SELECT 'grade_appeal' AS category, COUNT(*) AS defects
FROM grade_appeal WHERE status = 'upheld'
UNION ALL
SELECT 'ambiguous_content', COUNT(DISTINCT content_item_id)
FROM error_focus WHERE error_type = 'other' AND error_count >= 3 AND resolved = 0
UNION ALL
SELECT 'client_render_error', COUNT(*)
FROM client_error_log WHERE error_type LIKE '%drill%'
UNION ALL
SELECT 'session_crash', COUNT(*)
FROM crash_log WHERE request_path LIKE '/api/session%'
UNION ALL
SELECT 'srs_corruption', COUNT(*)
FROM progress WHERE next_review_date IS NOT NULL AND interval_days <= 0 AND repetitions > 0
ORDER BY defects DESC;
```

### 5.3 DPMO by Drill Type

```sql
SELECT
    re.drill_type,
    COUNT(*) AS opportunities,
    SUM(CASE WHEN ga.id IS NOT NULL AND ga.status = 'upheld' THEN 1 ELSE 0 END) AS defects,
    ROUND(CAST(SUM(CASE WHEN ga.id IS NOT NULL AND ga.status = 'upheld' THEN 1 ELSE 0 END) AS REAL)
          / COUNT(*) * 1000000, 0) AS dpmo
FROM review_event re
LEFT JOIN grade_appeal ga ON ga.content_item_id = re.content_item_id
    AND ga.session_id = re.session_id
GROUP BY re.drill_type
ORDER BY dpmo DESC;
```

---

## 6. Defect Logging Protocol

When a new defect is identified:

1. **Classify** — Which defect type from section 1?
2. **Log** — Ensure it appears in the appropriate table (`grade_appeal`, `crash_log`, `client_error_log`, or `improvement_log`)
3. **Count** — Verify it will be captured by the DPMO queries above
4. **Root cause** — Apply 5 Whys (see `5-whys-template.md`)
5. **Fix** — Implement corrective action
6. **Verify** — Confirm DPMO decreases in next measurement cycle

---

## 7. Exclusion Rules

To avoid inflating or deflating DPMO:

- **Exclude test/dev sessions:** Only count `review_event` rows where `user_id` corresponds to a real user (not test accounts)
- **Exclude first-ever baseline period:** The first 2 weeks after instrumentation are calibration, not counted toward sigma targets
- **Do not double-count:** An ambiguous content item is one defect regardless of how many learners encounter it (count the item once, not once per presentation, for the ambiguous_items metric; use presentation count for DPMO calculation)
