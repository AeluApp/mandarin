# Gage R&R Study Design — Aelu Drill Scoring System

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Related:** `msa.md` (grading engine MSA detail)

---

## 1. Study Objective

Verify that Aelu's drill scoring system produces identical results across:
- **Repeated measurements** of the same input (repeatability)
- **Different scoring algorithms** applied to the same input (reproducibility)
- **Different drill items** (part variation)

Because Aelu's grading is deterministic, the expected outcome is 0% Gage R&R. This study formally validates that expectation and identifies any edge cases where it might fail.

---

## 2. Study Design

| Parameter | Value |
|-----------|-------|
| **Parts** | 10 drill items (selected across difficulty levels and drill types) |
| **Appraisers** | 3 scoring algorithms (see section 3) |
| **Trials** | 3 repetitions per part-appraiser combination |
| **Total measurements** | 10 parts x 3 appraisers x 3 trials = 90 |
| **Measurement** | Binary: correct (1) or incorrect (0), plus score (0.0 - 1.0) and error_type |

### Why 3 "Appraisers" for a Deterministic System?

The Aelu grading engine is a single codebase, but different drill types use different grading paths. The 3 "appraisers" represent distinct algorithmic strategies:

| Appraiser | Grading Method | Drill Types |
|-----------|---------------|-------------|
| **A: Exact match** | Direct string comparison after normalization | mc, reverse_mc, ime_type, pinyin_to_hanzi, cloze_context |
| **B: Fuzzy pinyin** | Pinyin normalization (tone marks/numbers, v/u:, spacing) + comparison | english_to_pinyin, hanzi_to_pinyin, listening_dictation, dictation_sentence |
| **C: Rule-based** | Pattern matching, classification logic, multi-step rules | tone, tone_sandhi, error_correction, number_system, sentence_build |

---

## 3. Part Selection

10 items chosen to span the range of difficulty and edge cases:

| Part # | Item | HSK | Drill Type | Appraiser | Answer Tested | Edge Case Being Probed |
|--------|------|-----|-----------|-----------|---------------|----------------------|
| 1 | 你好 (nǐ hǎo, hello) | 1 | mc | A | Correct option selected | Baseline — simplest case |
| 2 | 猫 (māo, cat) | 1 | tone | C | Tone "1" (correct) | Tone number comparison |
| 3 | 猫 (māo, cat) | 1 | tone | C | Tone "3" (incorrect) | Tone error detection |
| 4 | 高兴 (gāoxìng, happy) | 2 | english_to_pinyin | B | "gao1xing4" (tone numbers) | Tone number → mark conversion |
| 5 | 高兴 (gāoxìng, happy) | 2 | english_to_pinyin | B | "gāoxìng" (tone marks) | Direct tone mark input |
| 6 | 女 (nǚ, female) | 1 | hanzi_to_pinyin | B | "nv3" | v→ü conversion |
| 7 | 不 (bù→bú before T4) | 2 | tone_sandhi | C | Correct sandhi application | Tone sandhi rule |
| 8 | 学生 (xuésheng) | 1 | ime_type | A | "学生" (correct hanzi) | Exact hanzi match |
| 9 | 请问 (qǐngwèn) | 2 | listening_dictation | B | "qing3 wen4" (spaced, numbered) | Space + number normalization |
| 10 | 三百五十 (sānbǎi wǔshí, 350) | 3 | number_system | C | "350" | Number conversion rule |

---

## 4. Test Procedure

### 4.1 Execution Script

```python
"""gage_rr_study.py — Formal Gage R&R for Aelu scoring system."""

import json
from dataclasses import dataclass, asdict

# Import grading functions from Aelu codebase
# from mandarin.drills.dispatch import run_drill
# from mandarin.drills.base import classify_error_cause

@dataclass
class Measurement:
    part: int
    appraiser: str  # "A_exact", "B_fuzzy_pinyin", "C_rule_based"
    trial: int
    correct: int  # 0 or 1
    score: float
    error_type: str | None


# Define all 90 measurements
STUDY_PLAN = [
    # Part 1: 你好 MC correct — Appraiser A x 3 trials
    {"part": 1, "appraiser": "A_exact", "drill_type": "mc",
     "item": {"hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello"},
     "answer": "1"},  # correct option index
    # ... (8 more parts, 3 appraisers each, 3 trials each)
]


def run_study(study_plan: list[dict]) -> list[Measurement]:
    """Execute all measurements. Each entry run 3 times."""
    results = []
    for entry in study_plan:
        for trial in range(1, 4):
            # result = _grade_isolated(entry["drill_type"], entry["item"], entry["answer"])
            # For deterministic system, simulated:
            result = Measurement(
                part=entry["part"],
                appraiser=entry["appraiser"],
                trial=trial,
                correct=1,  # Replace with actual grading call
                score=1.0,
                error_type=None,
            )
            results.append(result)
    return results


def analyze_gage_rr(measurements: list[Measurement]) -> dict:
    """Compute Gage R&R statistics from crossed study."""
    # Group measurements
    by_part_appraiser = {}
    for m in measurements:
        key = (m.part, m.appraiser)
        by_part_appraiser.setdefault(key, []).append(m.score)

    # Repeatability: variation within each (part, appraiser) group
    repeatability_ranges = []
    for key, scores in by_part_appraiser.items():
        r = max(scores) - min(scores)
        repeatability_ranges.append(r)

    avg_range = sum(repeatability_ranges) / len(repeatability_ranges)

    # For deterministic system: all ranges should be 0
    repeatability = avg_range  # Should be 0.0

    # Reproducibility: variation between appraisers for same part
    by_part = {}
    for m in measurements:
        by_part.setdefault(m.part, {}).setdefault(m.appraiser, []).append(m.score)

    appraiser_means_by_part = {}
    for part, appraisers in by_part.items():
        means = {a: sum(s)/len(s) for a, s in appraisers.items()}
        appraiser_means_by_part[part] = means

    # Range of appraiser means for each part
    repro_ranges = []
    for part, means in appraiser_means_by_part.items():
        if len(means) > 1:
            r = max(means.values()) - min(means.values())
            repro_ranges.append(r)

    reproducibility = sum(repro_ranges) / len(repro_ranges) if repro_ranges else 0.0

    # Total Gage R&R
    # GRR = sqrt(repeatability² + reproducibility²)
    import math
    grr = math.sqrt(repeatability**2 + reproducibility**2)

    return {
        "repeatability": repeatability,
        "reproducibility": reproducibility,
        "gage_rr": grr,
        "pct_rr": 0.0 if grr == 0 else None,  # Need total variation for %
        "verdict": "PASS" if grr == 0 else "INVESTIGATE",
    }
```

### 4.2 Expected Results

For a deterministic system, every trial of the same (part, appraiser, answer) should return identical `(correct, score, error_type)`:

| Metric | Expected | Implication |
|--------|----------|------------|
| Repeatability | 0.0 | Same algorithm grades same input identically every time |
| Reproducibility | 0.0* | All algorithms agree on the same input |
| Gage R&R (%) | 0.0% | No measurement system variation |
| Part variation | 100% of total variation | All variation is between items (intended) |

*Reproducibility may be > 0 in cases where different appraisers (exact match vs. fuzzy pinyin) apply to the **same answer format**. For example, if Part 4 ("gao1xing4") is graded by both Appraiser A (exact match) and Appraiser B (fuzzy pinyin), Appraiser A would mark it incorrect (no exact match to "gāoxìng") while Appraiser B would mark it correct (tone number normalization). This is **by design** — the algorithms handle different answer formats intentionally. The Gage R&R study must use each appraiser only with its intended drill type.

---

## 5. ANOVA Table Template

For the crossed Gage R&R study (if run with variable measurement data):

```
Source              DF    SS      MS      F       P       % Contribution
──────────────────  ────  ──────  ──────  ──────  ──────  ──────────────
Part (items)        9     SS_P    MS_P    F_P     p_P     % (should be ~100%)
Appraiser           2     SS_A    MS_A    F_A     p_A     % (should be ~0%)
Part × Appraiser    18    SS_PA   MS_PA   F_PA    p_PA    % (should be ~0%)
Repeatability       60    SS_E    MS_E    —       —       % (should be ~0%)
──────────────────  ────  ──────  ──────  ──────  ──────  ──────────────
Total               89    SS_T    —       —       —       100%
```

### ANOVA Formulas

```
DF_Part = k - 1 = 9                    (k = 10 parts)
DF_Appraiser = a - 1 = 2               (a = 3 appraisers)
DF_Interaction = (k-1)(a-1) = 18
DF_Repeatability = ka(n-1) = 60         (n = 3 trials)
DF_Total = kan - 1 = 89

SS_Part = an Σᵢ (X̄ᵢ.. - X̄...)²
SS_Appraiser = kn Σⱼ (X̄.ⱼ. - X̄...)²
SS_Interaction = n Σᵢⱼ (X̄ᵢⱼ. - X̄ᵢ.. - X̄.ⱼ. + X̄...)²
SS_Repeatability = Σᵢⱼₗ (Xᵢⱼₗ - X̄ᵢⱼ.)²
SS_Total = Σᵢⱼₗ (Xᵢⱼₗ - X̄...)²
```

### For Deterministic Systems

When the grading engine is fully deterministic:
- SS_Appraiser = 0 (all appraisers agree on their intended inputs)
- SS_Interaction = 0 (no appraiser-part interaction)
- SS_Repeatability = 0 (no within-trial variation)
- SS_Part = SS_Total (all variation is between parts)
- F-statistics are undefined (MS_E = 0, cannot divide by zero)

This is the **ideal result** — it confirms the measurement system introduces no variation.

---

## 6. Failure Modes

If the study reveals Gage R&R > 0%, investigate these potential causes:

| Cause | Detection | Fix |
|-------|-----------|-----|
| Random.choice affecting grading (not just drill presentation) | Repeated trials produce different scores | Audit all `random` calls in grading paths — ensure none affect `DrillResult` |
| Time-dependent grading logic | Results differ when run at different times | Audit for `datetime.now()` in grading functions |
| Database state dependency | Results differ based on prior drill history | Isolate grading from DB state — grading should be a pure function of input |
| Floating-point arithmetic | Small differences in score values | Pin score values to fixed decimals (0.0, 0.3, 0.5, 1.0) |
| Unicode normalization inconsistency | Same characters compared differently | Ensure NFKC normalization applied before all string comparisons |

---

## 7. Study Schedule

| Step | Timeline | Status |
|------|----------|--------|
| Design study (this document) | 2026-03-10 | Complete |
| Implement `gage_rr_study.py` test script | Phase 0 (baseline) | Not started |
| Execute 90 measurements | Phase 0 (baseline) | Not started |
| Compute ANOVA table | Phase 0 (baseline) | Not started |
| Report results | Phase 0 tollgate review | Not started |
| Re-run on any grading logic change | Ongoing | Continuous |

---

## 8. Acceptance Criteria

| Outcome | %R&R | Verdict | Action |
|---------|------|---------|--------|
| Expected | 0% | PASS | Measurement system is ideal. Proceed with confidence. |
| Marginal | 1-10% | Conditional PASS | Investigate source of variation. Likely a normalization edge case. |
| Unacceptable | > 10% | FAIL | Grading engine has non-deterministic behavior. Stop. Fix before any process capability or DPMO work — the measurement system is unreliable. |
