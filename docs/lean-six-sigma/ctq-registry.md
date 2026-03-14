# Critical-to-Quality (CTQ) Registry — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Last Updated:** 2026-03-10

---

## 1. CTQ Tree Overview

```
Learner Need                    Driver                          CTQ Metric
─────────────────────────────── ─────────────────────────────── ───────────────────────────
"I want to learn efficiently"─┬─ Drills test the right thing ──── Drill accuracy (system)
                              ├─ SRS schedules reviews well ──── SRS scheduling precision
                              └─ Sessions feel productive ────── Session completion rate

"I want a smooth experience" ─┬─ Audio plays instantly ────────── Audio/TTS latency
                              ├─ App responds quickly ─────────── API response time
                              └─ App loads fast ───────────────── Session load time

"I can trust the system" ─────┬─ Grading is always correct ───── Grading reproducibility
                              ├─ Streaks reflect reality ─────── Streak integrity
                              └─ Content is well-written ─────── Content quality score

"I want to keep my streak" ───── Streaks never break falsely ─── False streak-break rate
```

---

## 2. CTQ Detail Registry

### CTQ-001: Drill Grading Accuracy (System-Caused Defects)

| Field | Value |
|-------|-------|
| **Learner Need** | "When I answer correctly, the system should mark it correct" |
| **Driver** | Deterministic grading engine must handle all valid answer formats |
| **CTQ Metric** | % of drill presentations where grading produces incorrect result due to system fault (false positive or false negative) |
| **LSL** | 0% (no false negatives — correct answers marked wrong) |
| **USL** | 0.1% (< 1 system-caused error per 1,000 drills) |
| **Current Value** | Not yet measured at scale; Gage R&R = 0% on test suite (see `msa.md`) |
| **Measurement Method** | `grade_appeal` table submissions + automated regression tests (~1,300 tests). Count appeals upheld (system was wrong) / total `review_event` rows. |
| **Data Source** | `SELECT COUNT(*) FROM grade_appeal WHERE status = 'upheld'` / `SELECT COUNT(*) FROM review_event` |
| **Owner** | Jason |
| **Review Cadence** | Weekly |

### CTQ-002: SRS Scheduling Precision

| Field | Value |
|-------|-------|
| **Learner Need** | "Review items when I'm about to forget, not too early or too late" |
| **Driver** | Half-life model predicts recall probability; scheduler surfaces items at optimal time |
| **CTQ Metric** | Absolute deviation between `next_review_date` and actual review date (days) |
| **LSL** | -0.5 days (reviewed slightly early is acceptable) |
| **USL** | +2.0 days (reviewed more than 2 days late indicates scheduling failure or learner absence) |
| **Current Value** | Median ~0.3 days for active users (estimated from `progress.next_review_date` vs `review_event.created_at`) |
| **Measurement Method** | For each review event, compute `julianday(review_event.created_at) - julianday(progress.next_review_date)`. Exclude items with no prior `next_review_date` (first review). |
| **Data Source** | `SELECT AVG(ABS(julianday(re.created_at) - julianday(p.next_review_date))) FROM review_event re JOIN progress p ON re.content_item_id = p.content_item_id AND re.user_id = p.user_id WHERE p.next_review_date IS NOT NULL` |
| **Owner** | Jason |
| **Review Cadence** | Monthly |

### CTQ-003: Audio/TTS Latency

| Field | Value |
|-------|-------|
| **Learner Need** | "Audio should play immediately when I need it" |
| **Driver** | Browser Web Speech API (edge-tts) renders audio client-side |
| **CTQ Metric** | Time from audio request to first audible output (ms) |
| **LSL** | N/A (faster is always better) |
| **USL** | 500ms |
| **Current Value** | ~200-400ms typical (browser/device dependent, not yet instrumented) |
| **Measurement Method** | Client-side `performance.now()` delta from `speechSynthesis.speak()` call to `SpeechSynthesisUtterance.onstart` event. Log via `client_event` category='performance'. |
| **Data Source** | `SELECT AVG(CAST(detail AS REAL)) FROM client_event WHERE category = 'performance' AND event = 'tts_latency'` |
| **Owner** | Jason |
| **Review Cadence** | Monthly |

### CTQ-004: API Response Time

| Field | Value |
|-------|-------|
| **Learner Need** | "The app should feel instant" |
| **Driver** | Flask server processes API requests; SQLite queries must be fast |
| **CTQ Metric** | Server-side response time for API endpoints (ms, p95) |
| **LSL** | N/A |
| **USL** | 500ms (p95) |
| **Current Value** | ~50-150ms typical for grading endpoints (estimated, not systematically instrumented) |
| **Measurement Method** | Flask middleware timing: `time.perf_counter()` before/after request. Log to `client_event` or server-side performance table. |
| **Data Source** | Server request log or `SELECT * FROM client_event WHERE category = 'performance' AND event = 'api_response_time'` |
| **Owner** | Jason |
| **Review Cadence** | Weekly |

### CTQ-005: Session Completion Rate

| Field | Value |
|-------|-------|
| **Learner Need** | "I want to finish what I start" |
| **Driver** | Session planning, drill difficulty calibration, session length |
| **CTQ Metric** | `items_completed / items_planned` per session |
| **LSL** | 0.70 (sessions with < 70% completion indicate design problem or excessive difficulty) |
| **USL** | N/A (100% is ideal) |
| **Current Value** | Measurable now |
| **Measurement Method** | Direct from `session_log` table |
| **Data Source** | `SELECT AVG(CAST(items_completed AS REAL) / NULLIF(items_planned, 0)) FROM session_log WHERE items_planned > 0 AND session_outcome != 'started'` |
| **Owner** | Jason |
| **Review Cadence** | Weekly |

### CTQ-006: Content Quality Score

| Field | Value |
|-------|-------|
| **Learner Need** | "Drill content should be natural, unambiguous, and useful" |
| **Driver** | Seed data quality, context notes, Chinese writing standard (分寸 principle) |
| **CTQ Metric** | % of content items with 0 grade appeals AND 0 error_focus flags of type 'other' (ambiguity signal) |
| **LSL** | 95% of items have zero quality complaints |
| **USL** | N/A |
| **Current Value** | Not yet measured; 299 seed items, 299 context notes (100% coverage for HSK 1-3) |
| **Measurement Method** | Items with grade appeals or recurring 'other' errors flagged for review. `is_mined_out` flag on items with persistent quality issues. |
| **Data Source** | `SELECT COUNT(*) FROM content_item ci WHERE NOT EXISTS (SELECT 1 FROM grade_appeal ga WHERE ga.content_item_id = ci.id AND ga.status = 'upheld') AND NOT EXISTS (SELECT 1 FROM error_focus ef WHERE ef.content_item_id = ci.id AND ef.error_type = 'other' AND ef.error_count >= 3)` / `SELECT COUNT(*) FROM content_item` |
| **Owner** | Jason |
| **Review Cadence** | Monthly |

### CTQ-007: Streak Integrity

| Field | Value |
|-------|-------|
| **Learner Need** | "My streak should only break if I genuinely missed a day" |
| **Driver** | Streak counter logic, timezone handling, server availability |
| **CTQ Metric** | False streak-break rate: streaks broken when user had a valid session that calendar day |
| **LSL** | 0 (zero false breaks) |
| **USL** | 0 (zero false breaks — this is a binary quality characteristic) |
| **Current Value** | 0 (no reports of false breaks, but user base is small) |
| **Measurement Method** | Compare `session_log.started_at` dates against streak reset events. A false break = streak reset on a day where `session_log` has a completed session for that user. |
| **Data Source** | Cross-reference streak counter resets with `session_log` entries by user and calendar date (UTC) |
| **Owner** | Jason |
| **Review Cadence** | On any user report; automated check monthly |

---

## 3. CTQ Priority Matrix

| CTQ ID | Metric | Impact on Learner | Ease of Measurement | Priority |
|--------|--------|------------------|-------------------|----------|
| CTQ-001 | Grading accuracy | Critical — trust in system | High (grade_appeal + tests) | P0 |
| CTQ-005 | Session completion | High — engagement/retention | High (session_log) | P0 |
| CTQ-002 | SRS precision | High — learning efficiency | Medium (requires join query) | P1 |
| CTQ-004 | API response time | Medium — UX quality | Medium (needs instrumentation) | P1 |
| CTQ-007 | Streak integrity | High — motivation | Low (rare event, hard to detect) | P1 |
| CTQ-003 | Audio latency | Medium — listening drill UX | Low (client-side, device-dependent) | P2 |
| CTQ-006 | Content quality | High — long-term trust | Low (requires human review loop) | P2 |

---

## 4. Measurement Instrumentation Status

| CTQ | Instrumented? | Gap |
|-----|--------------|-----|
| CTQ-001 | Partial — test suite covers determinism; grade_appeal table exists but not systematically reviewed | Need: weekly grade_appeal review process |
| CTQ-002 | No — data exists in tables but no scheduled query | Need: monthly SRS deviation report |
| CTQ-003 | No — client_event schema supports it but TTS timing not yet logged | Need: client-side performance instrumentation |
| CTQ-004 | No — no server-side request timing middleware | Need: Flask before/after_request timing |
| CTQ-005 | Yes — directly from session_log columns | Already measurable |
| CTQ-006 | Partial — grade_appeal and error_focus tables exist | Need: content quality dashboard query |
| CTQ-007 | No — streak logic exists but no false-break detection | Need: automated streak audit |

---

## 5. Review and Update Process

1. **Monthly:** Review all CTQ current values against specs
2. **Quarterly:** Re-evaluate LSL/USL based on user feedback (VoC) and system maturity
3. **On incident:** Any grade appeal or streak complaint triggers immediate CTQ review
4. **On feature launch:** New features must map to existing CTQs or justify a new one
