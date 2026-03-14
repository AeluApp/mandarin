# DMAIC Tollgate Review Criteria — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10

---

## 1. Overview

Tollgate reviews are formal checkpoints at the end of each DMAIC phase. For Aelu (solo-founder operation), these are self-reviews with documented evidence. The discipline of formally reviewing deliverables prevents skipping steps and ensures each phase is complete before moving on.

### Review Protocol

1. Complete the checklist for the current phase
2. Write a brief (1 paragraph) tollgate summary documenting what was found
3. Record go/no-go decision with rationale
4. Log the review date and decision in the table at the bottom of this document
5. If no-go: document what's missing and a remediation plan with target date

---

## 2. Define Phase Tollgate

### Required Deliverables

| # | Deliverable | Document | Status |
|---|------------|----------|--------|
| D1 | Project charter with problem statement, scope, timeline, success criteria | `project-charter.md` | Complete |
| D2 | SIPOC diagram mapping suppliers, inputs, process, outputs, customers | `sipoc.md` | Complete |
| D3 | Voice of Customer program with interview guide and coding framework | `voc-program.md` | Complete |
| D4 | CTQ tree mapping customer needs to measurable metrics with specs | `ctq-registry.md` | Complete |
| D5 | Stakeholder identification (even if solo — document the roles) | `project-charter.md` section 4 | Complete |

### Exit Criteria

| Criterion | Evidence Required | Met? |
|-----------|------------------|------|
| Problem statement is specific, measurable, and scoped | Charter section 1 has concrete metrics, not vague aspirations | |
| CTQ metrics have defined LSL/USL or target values | Every CTQ in registry has numeric spec | |
| At least 3 VoC interviews completed OR interview guide ready with first interview scheduled | `voc-program.md` + interview notes or scheduled date | |
| SIPOC covers the core learning loop end-to-end | All 6 process steps documented with systems, data reads/writes | |
| Scope excludes explicitly documented out-of-scope items | Charter section 3 "Out of Scope" list | |

### Review Checklist

- [ ] Is the problem statement about the customer's problem, not the solution?
- [ ] Do CTQ metrics trace directly back to VoC needs (not internal assumptions)?
- [ ] Are specification limits defensible (based on industry benchmarks, user research, or competitive analysis)?
- [ ] Is the timeline realistic for a solo founder?
- [ ] Are risks documented with mitigation plans?

### Go/No-Go Framework

| Decision | Condition |
|----------|-----------|
| **GO** | All D1-D5 complete. All exit criteria met. No critical gaps. |
| **CONDITIONAL GO** | D1-D3 complete. D4 or D5 has minor gaps that can be addressed in Measure phase. Document what's missing. |
| **NO-GO** | Problem statement is vague. CTQs not defined. No VoC evidence. Return to Define. |

---

## 3. Measure Phase Tollgate

### Required Deliverables

| # | Deliverable | Document | Status |
|---|------------|----------|--------|
| M1 | Measurement system analysis (MSA) — Gage R&R for drill scoring | `msa.md`, `gage-rr.md` | Designed |
| M2 | MSA for all key metrics (SRS, API timing, content quality) | `measurement-system-analysis.md` | Designed |
| M3 | Baseline DPMO calculation with data | `dpmo-dashboard.md` | Framework ready |
| M4 | Process capability (Cp/Cpk) for key processes | `process-capability.md` | Framework ready |
| M5 | Data collection plan with instrumentation status | `ctq-registry.md` section 4 | Gaps identified |
| M6 | Control chart baseline (initial X-bar/R charts) | `control-charts.md` | Specified |

### Exit Criteria

| Criterion | Evidence Required | Met? |
|-----------|------------------|------|
| Gage R&R executed and %R&R < 10% for all measured metrics | Test results from `gage_rr_study.py` | |
| Baseline DPMO calculated from at least 500 opportunities | SQL query output with n >= 500 | |
| Cpk calculated for at least 2 key processes | Cpk values with sample sizes documented | |
| All defect types defined and detectable | Each defect type in `dpmo-dashboard.md` has a working SQL query | |
| Measurement instrumentation gaps documented with remediation plan | Missing instrumentation listed with timeline | |

### Review Checklist

- [ ] Has the measurement system been validated BEFORE measuring the process?
- [ ] Is the baseline period long enough (2+ weeks of data)?
- [ ] Are the data sources automated (not manual counting)?
- [ ] Can the same DPMO calculation be reproduced by running the same queries?
- [ ] Are there enough data points for statistical validity (n >= 30 for Cpk)?

### Go/No-Go Framework

| Decision | Condition |
|----------|-----------|
| **GO** | M1-M4 complete with data. Gage R&R < 10%. Baseline DPMO established. |
| **CONDITIONAL GO** | Gage R&R = 0% (expected for deterministic system). Baseline DPMO exists but sample size < 500 (small user base). Document plan to accumulate data. |
| **NO-GO** | Gage R&R > 30%. Measurement system unreliable. Cannot trust DPMO baseline. Fix measurement first. |

---

## 4. Analyze Phase Tollgate

### Required Deliverables

| # | Deliverable | Document | Status |
|---|------------|----------|--------|
| A1 | Pareto analysis of defect categories | `pareto-analysis.md` | Framework ready |
| A2 | Fishbone diagrams for top 3 defect categories | `fishbone-diagrams.md` | Templates ready |
| A3 | 5 Whys root cause analysis for top defects | `5-whys-template.md` | Templates ready |
| A4 | Statistical hypothesis tests confirming root causes | In analysis notes | Not started |
| A5 | Improvement opportunities ranked by DPMO impact | `sigma-progression.md` Phase 1 projects | Listed |

### Exit Criteria

| Criterion | Evidence Required | Met? |
|-----------|------------------|------|
| Top 3 defect categories identified (Pareto 80/20) | Pareto chart showing cumulative % | |
| Root cause identified for each top-3 category | Fishbone + 5 Whys analysis completed | |
| Root causes validated with data (not just theory) | SQL query or test case demonstrating the causal link | |
| Improvement projects scoped with expected DPMO impact | Each project has estimated defect reduction | |
| No "solutions looking for problems" — every improvement traces to a measured defect | Traceability from defect → root cause → improvement project | |

### Review Checklist

- [ ] Does the Pareto chart use the same defect definitions as the DPMO dashboard?
- [ ] Were fishbone diagrams built with real data, not just brainstorming?
- [ ] Do the 5 Whys reach a systemic root cause, not just an immediate cause?
- [ ] Is there a statistical test (chi-squared, t-test, or proportion test) confirming at least one root cause?
- [ ] Are proposed improvements reversible if they don't work?

### Go/No-Go Framework

| Decision | Condition |
|----------|-----------|
| **GO** | Top 3 root causes identified and validated. Improvement projects scoped with measurable targets. |
| **CONDITIONAL GO** | Root causes identified but statistical validation incomplete (insufficient data). Proceed with improvements but plan for post-hoc validation. |
| **NO-GO** | Cannot identify root causes. Defect categories unclear. Return to Measure for better data. |

---

## 5. Improve Phase Tollgate

### Required Deliverables

| # | Deliverable | Document | Status |
|---|------------|----------|--------|
| I1 | Implemented improvements for top defect categories | Code changes, PRs, deploy records | Not started |
| I2 | Before/after DPMO comparison | Updated `dpmo-dashboard.md` calculations | Not started |
| I3 | Statistical validation of improvement (p < 0.05) | Two-proportion z-test results | Not started |
| I4 | Updated process capability (Cpk) | `process-capability.md` post-improvement values | Not started |
| I5 | Regression test results confirming no new defects introduced | Pytest results, ~1,300+ tests passing | Continuous |

### Exit Criteria

| Criterion | Evidence Required | Met? |
|-----------|------------------|------|
| DPMO decreased by target amount | Before/after DPMO with dates and sample sizes | |
| Improvement is statistically significant (p < 0.05) | z-test or chi-squared test output | |
| No regression — test suite passes completely | pytest output showing 0 failures | |
| Cpk improved or maintained for affected processes | Cpk values post-improvement | |
| Improvement is documented (what changed, why, expected vs. actual impact) | Entry in `improvement_log` with status = 'applied' | |

### Statistical Validation Template

```
Improvement: [description]
Period before: [start_date] to [end_date], n₁ = [opportunities], d₁ = [defects]
Period after: [start_date] to [end_date], n₂ = [opportunities], d₂ = [defects]

p̂₁ = d₁/n₁ = [before defect rate]
p̂₂ = d₂/n₂ = [after defect rate]

H₀: p₂ >= p₁ (no improvement)
H₁: p₂ < p₁ (improvement)

p̂_pooled = (d₁ + d₂) / (n₁ + n₂)
z = (p̂₁ - p̂₂) / sqrt(p̂_pooled × (1 - p̂_pooled) × (1/n₁ + 1/n₂))

z = [computed value]
p-value = [computed value]

Decision: Reject/Fail to reject H₀ at α = 0.05
```

### Go/No-Go Framework

| Decision | Condition |
|----------|-----------|
| **GO** | DPMO decreased. p < 0.05. No regressions. Ready for Control phase. |
| **CONDITIONAL GO** | DPMO decreased but p > 0.05 (insufficient sample size). Proceed to Control but continue monitoring for statistical significance. |
| **NO-GO** | DPMO did not decrease OR regressions introduced. Return to Analyze to re-examine root causes. |

---

## 6. Control Phase Tollgate

### Required Deliverables

| # | Deliverable | Document | Status |
|---|------------|----------|--------|
| C1 | SPC control charts operational | `control-charts.md`, `spc-automation.md` | Not started |
| C2 | Automated violation detection and alerting | `spc_monitor.py` running on schedule | Not started |
| C3 | Control plan documenting what to monitor, how, and reaction procedures | `control-charts.md` section 4 | Specified |
| C4 | Updated CTQ registry with current values | `ctq-registry.md` with measured values | Not started |
| C5 | Process documentation updated | All LSS docs reflect actual implemented state | Ongoing |
| C6 | 8 consecutive weeks at target sigma level | DPMO trend data | Not started |

### Exit Criteria

| Criterion | Evidence Required | Met? |
|-----------|------------------|------|
| SPC charts show process in control for 4+ consecutive weeks | Control chart screenshots or `spc_report.json` | |
| No unresolved critical (Rule 1) violations | `improvement_log` entries all resolved | |
| DPMO at target sigma for 8+ consecutive weeks | Weekly DPMO calculations | |
| Automated monitoring runs daily without manual intervention | Cron/scheduled job logs | |
| All CTQ metrics have current measured values (not just targets) | `ctq-registry.md` updated with real numbers | |
| Knowledge transfer documentation complete (even if solo — future-proofing) | This doc suite is complete and accurate | |

### Go/No-Go Framework

| Decision | Condition |
|----------|-----------|
| **COMPLETE** | All C1-C6 met. Process sustained at target sigma. DMAIC cycle closed. |
| **EXTEND** | Control charts show instability. Extend Control phase by 4 weeks. If still unstable, return to Improve. |
| **RECYCLE** | New defect categories emerged. Start new DMAIC cycle targeting the new top defects. |

---

## 7. Tollgate Review Log

| Phase | Review Date | Decision | Reviewer | Notes |
|-------|-----------|----------|----------|-------|
| Define | 2026-03-10 | GO | Jason | All deliverables complete. VoC interviews not yet conducted but guide is ready. |
| Measure | — | — | — | — |
| Analyze | — | — | — | — |
| Improve | — | — | — | — |
| Control | — | — | — | — |

---

## 8. Solo-Founder Adaptations

Traditional tollgate reviews involve a review board. For Aelu:

1. **Self-review with evidence.** The checklist serves as the "review board." Every box must have documented evidence, not self-assessed judgments.
2. **Written summary required.** Even for a solo founder, write a 1-paragraph tollgate summary. Future you will thank present you.
3. **No skipping phases.** The temptation for a solo developer is to jump from "I see the problem" to "I'll just fix it." The DMAIC structure prevents fixing the wrong problem or fixing without measuring.
4. **Calendar commitment.** Schedule tollgate reviews as calendar events. They will not happen otherwise.
