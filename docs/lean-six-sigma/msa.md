# Measurement System Analysis (MSA) — Aelu Grading Engine

**Owner:** Jason Gerson
**Created:** 2026-03-10
**System Under Test:** Deterministic drill grading engine (`mandarin/drills/`)

---

## 1. Executive Summary

The Aelu grading engine is **fully deterministic**. It uses zero AI tokens at runtime. Every grading decision is the result of exact string matching, rule-based classification, or deterministic fuzzy matching with fixed thresholds. This means:

- **Gage R&R = 0%** — The same input always produces the same output. There is no operator variation, no measurement uncertainty, and no instrument drift.
- **Reproducibility = 100%** — Any drill, graded at any time, on any machine, with the same input, will produce the identical `DrillResult`.
- **Repeatability = 100%** — The same grader (the code) produces the same result on repeated measurements of the same part (drill response).

This is not a probabilistic grading system. There is no LLM, no neural network, no sampling. The grading engine is a pure function: `f(drill_type, user_answer, expected_answer, item_metadata) -> DrillResult`.

---

## 2. Grading Methods by Drill Type

The dispatch registry in `mandarin/drills/dispatch.py` defines 27+ drill types. Below is the grading method for each category.

### 2.1 Multiple Choice Drills (Recognition)

| Drill Type | Grading Method | Notes |
|-----------|---------------|-------|
| `mc` | Exact match: `user_picked == correct_answer` | 4 options, English-to-Hanzi |
| `reverse_mc` | Exact match: `user_picked == correct_answer` | 4 options, Hanzi-to-English |
| `intuition` | Exact match on selected option | Word order / naturalness judgment |
| `register_choice` | Exact match on selected register level | Casual/neutral/professional |
| `pragmatic` | Exact match on selected response | Contextual appropriateness |
| `measure_word` | Exact match on selected measure word | 4 options |
| `measure_word_disc` | Exact match on selected discriminator | Which MW fits |
| `particle_disc` | Exact match on selected particle | 了/过/着/的/得/地 |
| `homophone` | Exact match on selected character | Same-sound different-character |
| `synonym_disc` | Exact match on selected synonym | Near-synonym discrimination |
| `minimal_pair` | Exact match on selected option | Phonetically similar pairs |

**Gage R&R for MC drills: 0%.** The user selects an option index (1-4). The grader compares the selected option to the correct answer. No ambiguity.

### 2.2 Free-Text Drills (Production)

| Drill Type | Grading Method | Edge Cases |
|-----------|---------------|-----------|
| `ime_type` | Exact hanzi match after normalization | Simplified/traditional variants not currently accepted |
| `english_to_pinyin` | Pinyin normalization + comparison | Tone marks OR tone numbers accepted (see below) |
| `hanzi_to_pinyin` | Pinyin normalization + comparison | Same fuzzy matching as above |
| `pinyin_to_hanzi` | Exact hanzi match | Must type correct characters |
| `translation` | Exact hanzi match after normalization | Multiple valid translations not yet supported |
| `sentence_build` | Exact hanzi match on assembled sentence | Character-by-character comparison |
| `word_order` | Exact match on reordered sequence | All characters must be in correct order |
| `listening_dictation` | Pinyin normalization + comparison | Accepts tone numbers |
| `dictation_sentence` | Pinyin normalization + comparison | Full sentence dictation |
| `passage_dictation` | Pinyin normalization + comparison | Multi-sentence |

**Pinyin normalization rules (deterministic):**
1. Strip whitespace, lowercase
2. Accept tone marks (ā á ǎ à) or tone numbers (a1 a2 a3 a4)
3. Accept with or without spaces between syllables
4. `v` accepted for `ü` (e.g., `nv3` = `nǚ`)
5. Neutral tone: `0` or `5` or unmarked all accepted

**Gage R&R for free-text drills: 0%.** The normalization is deterministic. The comparison is exact after normalization. The same input always maps to the same normalized form.

### 2.3 Tone Drills

| Drill Type | Grading Method | Edge Cases |
|-----------|---------------|-----------|
| `tone` | Tone number comparison after extraction | Tone 0 vs 5 (both = neutral) |
| `listening_tone` | Exact match on identified tone number | 1-4 selection |
| `tone_sandhi` | Rule-based sandhi application check | 3-3 → 2-3, 不/一 rules |

**Tone contour data** is defined in `TONE_CONTOURS` (drills/tone.py). The grader extracts tone numbers from pinyin using `pinyin_to_tones()` and compares integer values. No ambiguity.

### 2.4 Listening Drills

| Drill Type | Grading Method | Notes |
|-----------|---------------|-------|
| `listening_gist` | MC selection match | "What does this mean?" |
| `listening_detail` | MC selection match | Specific detail question |
| `listening_passage` | MC selection match | Passage-level comprehension |

All listening drills are MC format — same grading as section 2.1.

### 2.5 Speaking/Shadowing Drills

| Drill Type | Grading Method | Notes |
|-----------|---------------|-------|
| `speaking` | Self-report (user rates own accuracy) | No automated speech recognition |
| `shadowing` | Self-report | Listen-and-repeat format |

**Note:** Speaking drills currently rely on user self-assessment, not automated speech recognition. This is the one area where measurement is subjective. Parselmouth integration was deferred (build fails on Python 3.9). When implemented, tone grading will use F0 contour analysis against `speaker_calibration` data, which will be deterministic.

### 2.6 Advanced Drills

| Drill Type | Grading Method | Notes |
|-----------|---------------|-------|
| `slang_exposure` | Exposure-only (always "correct") | No grading — recognition drill |
| `cloze_context` | Exact match on fill-in character/word | Single correct answer |
| `collocation` | MC selection match | Verb-noun pairing |
| `radical` | MC selection match | Radical identification |
| `chengyu` | MC selection match | Four-character idiom |
| `complement` | MC or free-text match | Result complement |
| `ba_bei` | MC selection match | 把/被 construction choice |
| `error_correction` | Exact match on corrected sentence | Grammar error fix |
| `number_system` | Exact numeric match | Chinese number conversion |
| `measure_word_cloze` | Exact match on fill-in MW | Cloze format |
| `measure_word_production` | Exact match on typed MW | Free production |
| `transfer` | Exact match on target expression | Context transfer |

---

## 3. Edge Cases and Multi-Valid-Answer Handling

### 3.1 Fuzzy Pinyin Matching
The pinyin normalizer handles these equivalences deterministically:

| User Input | Accepted As | Rule |
|-----------|------------|------|
| `nü` | `nǚ` | Tone mark + umlaut |
| `nv3` | `nǚ` | `v` = `ü`, number = tone mark |
| `nu:3` | `nǚ` | Colon-umlaut notation |
| `lv4` | `lǜ` | Same pattern |
| `xi1 huan1` | `xīhuān` | Spaces between syllables |
| `xihuan` | `xīhuān` | Missing tones (marked incorrect on tone-sensitive drills) |

### 3.2 Tone Number Acceptance
For drills where the user types pinyin, both formats are accepted:
- Tone marks: `māo` (correct)
- Tone numbers: `mao1` (correct)
- No tones: `mao` (incorrect on tone-sensitive drills, correct on pinyin-only drills)

### 3.3 Multiple Valid Answers
Currently, most drills expect a single canonical answer. Known cases where multiple answers should be valid but are not yet handled:

| Case | Example | Status |
|------|---------|--------|
| Alternative English translations | 高兴 = "happy" / "glad" / "pleased" | Not yet: only one `english` value per content_item |
| Regional pinyin variants | 谁 = "shéi" / "shuí" | Partially: some items have both in seed data |
| Simplified/traditional | 学/學 | Not yet: system assumes simplified |

These are documented defects, not measurement uncertainty. The grading engine is deterministic on its current rules — the question is whether the rules are correct, not whether they are consistently applied.

---

## 4. Error Classification System

When a drill answer is incorrect, the error is classified into one of 15 types. Classification uses `classify_error_cause()` in `drills/base.py` with deterministic rules:

| Error Type | Classification Rule |
|-----------|-------------------|
| `tone` | Tone numbers differ, consonants/vowels match |
| `segment` | Syllable boundary error (different length) |
| `ime_confusable` | IME drill, similar-looking character selected |
| `grammar` | Grammar drill types (complement, ba_bei, error_correction) |
| `vocab` | MC drill, selected wrong meaning |
| `register_mismatch` | Register choice drill, wrong formality level |
| `particle_misuse` | Particle discrimination drill, wrong particle |
| `function_word_omission` | Missing function word in production |
| `temporal_sequencing` | Word order error involving time expressions |
| `measure_word` | Wrong measure word selected/produced |
| `politeness_softening` | Pragmatic drill, too direct/indirect |
| `reference_tracking` | Pronoun/reference error |
| `pragmatics_mismatch` | Pragmatic drill, contextually inappropriate |
| `number` | Number system drill, wrong conversion |
| `other` | No specific pattern matched |

Classification is rule-based: `cause_to_error_type()` maps detailed cause strings to these 15 DB-valid types. The mapping is a static dictionary — deterministic, no randomness.

---

## 5. Gage R&R Test Plan

### 5.1 Objective
Verify 100% reproducibility of grading decisions across 50 representative drill instances.

### 5.2 Test Design

| Parameter | Value |
|-----------|-------|
| Sample size | 50 drill instances |
| Drill types covered | All 27 types (at least 1 per type, weighted by usage frequency) |
| Repetitions per sample | 3 (same input graded 3 times) |
| Total measurements | 150 |
| Operators | 1 (the code — there is only one "appraiser") |
| Expected variation | 0% |

### 5.3 Sample Selection

| Category | Count | Drill Types |
|----------|-------|------------|
| MC (correct answers) | 5 | mc, reverse_mc, listening_gist, measure_word, homophone |
| MC (incorrect answers) | 5 | mc, reverse_mc, listening_detail, particle_disc, synonym_disc |
| Free-text (correct, exact match) | 5 | ime_type, hanzi_to_pinyin, english_to_pinyin, translation, sentence_build |
| Free-text (correct, fuzzy match) | 5 | english_to_pinyin (tone numbers), hanzi_to_pinyin (v=ü), listening_dictation (spaced) |
| Free-text (incorrect) | 5 | ime_type (wrong char), pinyin_to_hanzi (wrong char), translation (wrong word) |
| Tone (correct) | 3 | tone (exact), listening_tone (correct ID), tone_sandhi (correct rule) |
| Tone (incorrect) | 3 | tone (wrong tone number), listening_tone (wrong ID), tone_sandhi (wrong application) |
| Confidence inputs | 4 | ? (half credit), N (unknown), N→narrow→correct, N→narrow→wrong |
| Skip/quit inputs | 2 | Q, B |
| Edge cases | 5 | Empty string, whitespace-only, very long input, unicode edge, neutral tone |
| Speaking (self-report) | 3 | speaking, shadowing (self-assessed correct/incorrect) |
| Advanced | 5 | cloze_context, complement, ba_bei, radical, chengyu |

### 5.4 Execution

```python
# test_gage_rr.py — run within pytest suite
import pytest
from mandarin.drills.dispatch import run_drill, DRILL_REGISTRY

SAMPLES = [
    # (drill_type, item_dict, user_answer, expected_correct, expected_error_type)
    ("mc", {"id": 1, "hanzi": "你好", "pinyin": "nǐ hǎo", "english": "hello"}, "1", True, None),
    ("tone", {"id": 2, "hanzi": "猫", "pinyin": "māo", "english": "cat"}, "1", True, None),
    ("tone", {"id": 2, "hanzi": "猫", "pinyin": "māo", "english": "cat"}, "3", False, "tone"),
    # ... 47 more samples
]

@pytest.mark.parametrize("drill_type,item,answer,expected_correct,expected_error", SAMPLES)
def test_gage_rr_reproducibility(drill_type, item, answer, expected_correct, expected_error, test_db):
    """Each sample graded 3 times must produce identical results."""
    results = []
    for _ in range(3):
        result = _grade_isolated(drill_type, item, answer, test_db)
        results.append((result.correct, result.error_type, result.score, result.confidence))

    # All 3 repetitions must be identical
    assert results[0] == results[1] == results[2], (
        f"Gage R&R failure: {drill_type} produced varying results: {results}"
    )
    assert results[0][0] == expected_correct
    if expected_error:
        assert results[0][1] == expected_error
```

### 5.5 Expected Results

| Metric | Expected Value |
|--------|---------------|
| Total variation | 0% |
| Part-to-part variation | N/A (we're measuring the instrument, not the parts) |
| Repeatability (within-appraiser) | 0% variation |
| Reproducibility (between-appraiser) | N/A (single appraiser = the code) |
| Gage R&R % | 0.00% |
| NDC (Number of Distinct Categories) | N/A (binary grading: correct/incorrect) |

### 5.6 Conditions That Would Indicate a Gage R&R Failure

A Gage R&R > 0% would mean the grading engine has non-deterministic behavior. Possible causes:

1. **Random.choice in grading logic** — The distractor selection uses `random.choice` but this affects drill *presentation*, not *grading*. Grading does not use randomness.
2. **Time-dependent logic** — If grading used `datetime.now()` to affect correctness decisions. It does not.
3. **External API calls** — If grading queried an LLM or external service. It does not.
4. **Floating-point rounding** — If `score` computation used floats with platform-dependent rounding. Current scores are fixed values (0.0, 0.3, 0.5, 1.0).

None of these conditions exist in the current codebase. The test plan is a verification of this claim, not an exploratory investigation.

---

## 6. Known Measurement Gaps

| Gap | Impact | Mitigation |
|-----|--------|-----------|
| Speaking drills use self-report, not automated grading | Self-assessment data may not reflect actual pronunciation accuracy | Deferred: parselmouth F0 analysis would provide deterministic tone grading |
| Multiple valid English translations not accepted | Correct answers may be graded wrong (false negatives) | Log as `grade_appeal`; expand `content_item.english` to support alternatives |
| Traditional character variants not accepted | Heritage speakers may type traditional and be graded wrong | Add traditional-to-simplified normalization layer |
| Very long free-text answers not tested | Unknown behavior with paragraph-length input | Add edge case tests for inputs > 200 characters |

---

## 7. Measurement System Maintenance

The grading engine is maintained through:

1. **~1,300 automated tests** — Run on every commit via pre-commit hooks
2. **Pre-commit hooks** — Ruff linting + gitleaks secret scanning
3. **DrillResult dataclass** — Typed output contract prevents silent schema drift
4. **Error type CHECK constraint** — SQLite enforces valid `error_type` values at the database level
5. **Drill registry validation** — `_validate_drill_inputs()` logs warnings for suspect data before grading

No calibration is needed because the system has no drift mechanism. Unlike a physical measurement instrument, software grading logic does not wear out, lose calibration, or vary with environmental conditions. The only change vector is code changes, which are covered by the test suite.
