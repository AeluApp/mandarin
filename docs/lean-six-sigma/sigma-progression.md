# Sigma Progression Roadmap — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Goal:** Current ~2.1σ → 4.5σ by 2026 Q4

---

## 1. Current State Assessment

### Estimated Baseline: ~2.1σ (~308,000 DPMO)

This is a conservative estimate based on known defect sources before systematic measurement:

| Defect Source | Estimated Frequency | Evidence |
|--------------|-------------------|----------|
| Multi-valid-answer gaps (e.g., 高兴 = "happy" but not "glad") | ~5% of free-text drills | `msa.md` section 3.3 — known gap |
| Ambiguous content items | ~2-3% of items (est. 6-9 of 299 items) | `error_focus` entries with `error_type = 'other'` |
| TTS failures on some browsers/devices | ~1-2% of listening drills | Anecdotal, not yet instrumented |
| Client rendering errors | Unknown | `client_error_log` exists but not analyzed |
| Session crashes | < 0.5% of sessions | `crash_log` — low volume |

**Estimated total:** ~8% of drill presentations have some system-caused quality issue → ~80,000 DPMO → ~2.9σ. But without instrumentation, the true number could be higher. We assume 2.1σ as a floor.

---

## 2. Phase Gates

### Phase 0: Baseline (2026 March — 4 weeks)

**Objective:** Establish rigorous DPMO measurement before improving anything.

| Deliverable | Exit Criteria | Status |
|------------|--------------|--------|
| Instrument all defect sources per `dpmo-dashboard.md` | All 7 defect type queries return valid data | Not started |
| Flask request timing middleware | p50/p95/p99 latency logged per endpoint | Not started |
| Client-side TTS latency logging | `client_event` records TTS timing | Not started |
| Client-side drill render timing | `client_event` records render timing | Not started |
| Baseline DPMO calculated | Single number with confidence interval | Not started |
| Baseline Cp/Cpk for API latency | See `process-capability.md` | Not started |
| MSA verification | Gage R&R test executed (see `msa.md`) | Designed, not run |

**Statistical requirement:** Minimum 500 drill presentations (opportunities) before declaring baseline valid. At ~15 drills/session and ~3 sessions/week per user, this requires ~11 user-weeks of data.

**Phase gate review:** Present baseline DPMO, defect Pareto, and Cp/Cpk to tollgate (self-review per `tollgate-reviews.md`).

---

### Phase 1: Quick Wins → 3.0σ (2026 Q2 — 12 weeks)

**Objective:** Fix the top defect categories identified in Pareto analysis to reach < 66,807 DPMO.

| Improvement Project | Expected DPMO Impact | Effort | Priority |
|--------------------|---------------------|--------|----------|
| **P1-A: Multi-valid-answer support** — Allow alternative English translations for `content_item.english` (e.g., "happy"/"glad"/"pleased" for 高兴) | High — eliminates largest false-negative source | Medium (schema change + grading logic) | 1 |
| **P1-B: Ambiguous item remediation** — Review all items with `error_focus.error_type = 'other' AND error_count >= 3`. Rewrite or retire. | Medium — removes content ambiguity defects | Low (content editing, no code) | 2 |
| **P1-C: TTS error handling** — Graceful fallback when Web Speech API fails. Log failure, skip audio requirement, don't count as wrong. | Medium — eliminates audio-related false negatives | Low (client-side JS) | 3 |
| **P1-D: Regional pinyin variants** — Accept shéi/shuí, nǎ/nǎr variants | Low-medium — affects handful of items | Low (add to normalizer) | 4 |

**Exit Criteria:**
- DPMO < 66,807 (3.0σ) measured over rolling 30-day window
- All P1-A through P1-D deployed and verified
- Pareto chart shows top defect category shifted (new #1 is different from baseline #1)
- Statistical significance: p < 0.05 on before/after DPMO comparison (two-proportion z-test)

**Validation method:**

```
H₀: DPMO_after >= DPMO_before (no improvement)
H₁: DPMO_after < DPMO_before

z = (p̂_before - p̂_after) / sqrt(p̂_pooled * (1 - p̂_pooled) * (1/n_before + 1/n_after))

where p̂ = defects / opportunities for each period
Reject H₀ if z > 1.645 (one-tailed, α = 0.05)
```

---

### Phase 2: Systematic Improvement → 4.0σ (2026 Q3 — 12 weeks)

**Objective:** Address structural defect sources. Reach < 6,210 DPMO.

| Improvement Project | Expected DPMO Impact | Effort | Priority |
|--------------------|---------------------|--------|----------|
| **P2-A: Automated SPC monitoring** — Implement `spc-automation.md` for continuous defect detection | Prevention — catches regressions before users see them | Medium (Python + cron) | 1 |
| **P2-B: Content quality gate** — All new content items must pass a checklist: unambiguous, single correct answer or multi-answer configured, context note present, difficulty calibrated | Prevention — stops defects at source | Low (process, not code) | 2 |
| **P2-C: Traditional/simplified normalization** — Accept 學 for 学, 說 for 说 | Low — affects heritage speakers | Medium (normalization layer) | 3 |
| **P2-D: Drill-type-specific DPMO analysis** — Identify which of 27+ drill types has highest DPMO. Fix top 3. | Variable — depends on findings | Medium | 4 |
| **P2-E: SRS scheduling audit** — Verify half-life predictions match actual recall rates. Calibrate if Cpk < 1.33. | Medium — improves learning efficiency | Medium (statistical analysis) | 5 |

**Exit Criteria:**
- DPMO < 6,210 (4.0σ) measured over rolling 30-day window
- SPC control charts operational for API latency and drill accuracy
- No drill type has individual DPMO > 20,000
- All new content passes quality gate checklist
- p < 0.05 on Phase 1 → Phase 2 DPMO comparison

---

### Phase 3: Control → 4.5σ (2026 Q4 — 12 weeks)

**Objective:** Sustain gains. Reach < 1,350 DPMO. Shift focus from improvement to control.

| Control Activity | Mechanism | Frequency |
|-----------------|-----------|-----------|
| **SPC chart review** | X-bar/R charts for API latency, session accuracy, daily review_event volume | Weekly |
| **Defect triage** | Every grade_appeal and crash_log entry reviewed within 48 hours | Per event |
| **Content audit** | Random sample of 20 items per month checked against quality gate | Monthly |
| **Regression test gate** | ~1,300+ tests must pass before any deploy | Every deploy |
| **DPMO trend review** | Rolling 30-day DPMO plotted, compared to 4.5σ target | Weekly |
| **Process documentation** | All grading rules, normalization rules, and scheduling parameters documented | Maintained continuously |

**Exit Criteria:**
- DPMO < 1,350 (4.5σ) for 8 consecutive weeks
- No out-of-control signals on SPC charts for 4 consecutive weeks
- All CTQ metrics within spec (see `ctq-registry.md`)
- Control plan documented and operational

**Sustainability Plan:**
1. SPC alerts auto-fire on out-of-control conditions (see `spc-automation.md`)
2. New drill types must include grading tests before merge
3. Content expansion (HSK 4-9) follows quality gate process from P2-B
4. Monthly DPMO review is a standing calendar item
5. Any regression (DPMO exceeds 1,350 for 2 consecutive weeks) triggers immediate root cause analysis

---

## 3. Risk to Progression

| Risk | Phase Affected | Mitigation |
|------|---------------|-----------|
| Insufficient data volume (< 500 opportunities/month) | All — can't compute valid DPMO | Ensure 3+ active users during measurement phases; supplement with automated test runs |
| Multi-valid-answer fix introduces new bugs | Phase 1 | Extensive test coverage for new normalization; canary rollout |
| Content expansion (HSK 4-9) introduces defect spike | Phase 3 | Quality gate (P2-B) must be active before expansion |
| Solo founder capacity — can't sustain weekly SPC review | Phase 3 | Automate SPC chart generation and alerting |
| Users don't submit grade appeals (defects go undetected) | All | Add passive defect detection: flag items where experienced users (mastery_stage >= 'solid') answer wrong at unusually high rate |

---

## 4. Measurement Calendar

| Week | Activity |
|------|----------|
| W1 (March 10) | Begin instrumentation (Phase 0) |
| W4 (March 31) | Baseline DPMO calculated |
| W5 (April 7) | Phase 0 tollgate review |
| W6-W17 (April-June) | Phase 1 improvements |
| W17 (June 30) | Phase 1 tollgate review |
| W18-W29 (July-Sept) | Phase 2 improvements |
| W29 (Sept 30) | Phase 2 tollgate review |
| W30-W42 (Oct-Dec) | Phase 3 control |
| W42 (Dec 31) | Phase 3 tollgate review — 4.5σ verification |
