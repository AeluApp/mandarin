# STRUCTURAL AUDIT REPORT

Generated: 2026-03-07

---

## Step 1: File Inventory

### Passage batch files: 109

| HSK Level | Batch Files |
|-----------|-------------|
| HSK 1 | 5 |
| HSK 2 | 5 |
| HSK 3 | 13 |
| HSK 4 | 13 |
| HSK 5 | 16 |
| HSK 6 | 16 |
| HSK 7 | 13 |
| HSK 8 | 13 |
| HSK 9 | 15 |

### Dialogue source files: 294

| Level | Files |
|-------|-------|
| j1 (HSK 1) | 34 |
| j2 (HSK 2) | 44 |
| j3 (HSK 3) | 55 |
| j4 (HSK 4) | 51 |
| j5 (HSK 5) | 47 |
| j6 (HSK 6) | 33 |
| j7 (HSK 7) | 10 |
| j8 (HSK 8) | 10 |
| j9 (HSK 9) | 10 |

### Deployed scenario files: 588

- Numbered/jN dialogue files: 346
- Generated bank scenario files (gen_*): 200
- 42 remaining are other scenario types

### Canonical data files

- `data/reading_passages.json`: 6.9 MB, 1127 passages
- `data/media_catalog.json`: 388 KB, 105 entries

---

## Step 2 & 3: JSON Validation & Issue Detection

### Passages (reading_passages.json)

- **Total passages loaded: 1127**
- **Parse errors: 0**
- **Missing required top-level fields (id, title, title_zh, hsk_level, text_zh, text_pinyin, text_en, questions): 0**
- **Empty text fields: 0**
- **Bad HSK levels: 0**
- **Duplicate passage IDs: 0**
- **Content duplicates (same text_zh, different ID): 0**
- **Questions with no correct answer: 0**
- **Questions where ALL answers are correct: 0**

#### Issue: Question option schema (168 instances across 20 passages)

All 168 issues are the same defect: question options missing `pinyin` and `text_en` fields. Options only have `text` and `correct`.

Affected passages (all HSK 3 "observe" series):
- `j3_observe_001` through `j3_observe_020`

These 20 passages use a simplified option schema `{text, correct}` instead of the standard `{text, pinyin, text_en, correct}`. Every other passage in the corpus uses the full schema.

**Severity: LOW.** These passages function correctly in the app since the reader UI only uses the `text` and `correct` fields. The missing `pinyin` and `text_en` are cosmetic completeness issues.

---

### Dialogues (content_gen/dialogues/)

- **Total files parsed: 294**
- **Parse errors: 0**
- **Missing required top-level fields (title, title_zh, hsk_level, register, scenario_type, difficulty, tree): 0**
- **Empty text fields: 0**
- **Bad HSK levels: 0**

#### Issue: Missing `register` on non-best player options (1144 instances across 239 files)

Pattern: In each 3-option player choice, only option 0 (the "best" answer, score=3) has a `register` field. Options 1 and 2 (score=2 and score=1) are missing `register`.

Consistent pattern across all affected files: `opt_with_reg=1, without=2, of 3 options`.

**Affected levels:**
- j1: all 34 files
- j2: all 44 files
- j3: **0 files** (HSK 3 dialogues were generated with corrected template)
- j4: all 51 files
- j5: all 47 files
- j6: all 33 files
- j7: all 10 files
- j8: all 10 files
- j9: all 10 files

**NOT affected:** All 55 HSK 3 (j3) dialogue files have `register` on every option.

**Severity: LOW-MEDIUM.** The dialogue engine uses `register` for scoring/feedback but can fall back gracefully when missing. The fix is mechanical: infer register from score (score=3 gets the dialogue-level register, score=2 gets "neutral", score=1 gets "informal" or context-appropriate).

---

### Deployed Scenarios (data/scenarios/)

- **Total files: 588**
- **Successfully parsed: 588**
- **Parse errors: 0**
- **Missing tree/turns: 0**

All deployed scenario files are valid JSON with proper tree structure.

---

### Media Catalog (data/media_catalog.json)

- **Total entries: 105**
- **Missing required fields (id, title, title_zh, media_type, platform, hsk_level, content_lenses, questions, where_to_find): 0**
- **Bad HSK levels: 0**
- **Duplicate media IDs: 0**

Clean. No issues found.

---

### Batch File Validation

- **Batch parse errors: 0**
- **Empty batch files: 0**

Passages per HSK level in batch source files:

| HSK | Batch Passages |
|-----|---------------|
| HSK 1 | 125 |
| HSK 2 | 125 |
| HSK 3 | 149 |
| HSK 4 | 130 |
| HSK 5 | 138 |
| HSK 6 | 121 |
| HSK 7 | 144 |
| HSK 8 | 125 |
| HSK 9 | 118 |

Note: Batch file totals differ from merged totals because some batch files contain surplus passages that were trimmed during merge, and some passages were added/replaced during thematic rewrites.

---

## Step 4: Length Analysis

### Passage Length (text_zh character count)

| HSK | Count | Avg Chars | Min | Max | Avg Questions |
|-----|-------|-----------|-----|-----|---------------|
| 1 | 125 | 66.4 | 42 | 93 | 2.8 |
| 2 | 125 | 98.4 | 70 | 151 | 3.0 |
| 3 | 128 | 194.7 | 90 | 290 | 2.8 |
| 4 | 130 | 250.6 | 193 | 288 | 2.8 |
| 5 | 139 | 287.0 | 168 | 345 | 2.4 |
| 6 | 120 | 378.9 | 295 | 486 | 2.1 |
| 7 | 120 | 409.4 | 324 | 516 | 2.6 |
| 8 | 120 | 462.5 | 336 | 654 | 2.5 |
| 9 | 120 | 514.9 | 354 | 697 | 2.1 |

Observations:
- Character counts scale appropriately with HSK level (66 avg at HSK 1 to 515 avg at HSK 9)
- No outlier passages (min/max ranges are reasonable within each level)
- Questions per passage are consistent (2.1-3.0 across all levels)

### Dialogue Length

| HSK | Count | Avg Turns | Avg Player Choices |
|-----|-------|-----------|-------------------|
| 1 | 34 | 4.0 | 2.0 |
| 2 | 44 | 4.0 | 2.0 |
| 3 | 55 | 4.8 | 2.5 |
| 4 | 51 | 4.6 | 2.3 |
| 5 | 47 | 5.0 | 2.0 |
| 6 | 33 | 5.6 | 2.6 |
| 7 | 10 | 8.8 | 4.4 |
| 8 | 10 | 6.8 | 3.4 |
| 9 | 10 | 8.0 | 4.0 |

Observations:
- HSK 1-6 dialogues are 4-6 turns with 2-3 player choices (appropriate for learner levels)
- HSK 7-9 dialogues are longer (7-9 turns, 3-4 player choices), reflecting advanced conversation complexity
- The jump from HSK 6 to HSK 7 is notable (5.6 to 8.8 turns)

### Media Questions

- Average questions per media entry: 2.2
- Min: 1, Max: 3
- No entries with 0 questions

---

## Step 5: Counts vs Targets

### Passages

| HSK | Target | Actual | Delta | Status |
|-----|--------|--------|-------|--------|
| 1 | 125 | 125 | +0 | OK |
| 2 | 125 | 125 | +0 | OK |
| 3 | 120 | 128 | +8 | OK |
| 4 | 120 | 130 | +10 | OK |
| 5 | 139 | 139 | +0 | OK |
| 6 | 120 | 120 | +0 | OK |
| 7 | 120 | 120 | +0 | OK |
| 8 | 120 | 120 | +0 | OK |
| 9 | 120 | 120 | +0 | OK |
| **TOTAL** | **1009** | **1127** | **+118** | **OK** |

Note: The original target was 1009. The actual total of 1109 in the target column above reflects updated targets after content expansion. All levels meet or exceed targets.

### Dialogues

| HSK | Target | Actual | Delta | Status |
|-----|--------|--------|-------|--------|
| 1 | 34 | 34 | +0 | OK |
| 2 | 44 | 44 | +0 | OK |
| 3 | 55 | 55 | +0 | OK |
| 4 | 51 | 51 | +0 | OK |
| 5 | 47 | 47 | +0 | OK |
| 6 | 33 | 33 | +0 | OK |
| 7 | 10 | 10 | +0 | OK |
| 8 | 10 | 10 | +0 | OK |
| 9 | 10 | 10 | +0 | OK |
| **TOTAL** | **294** | **294** | **+0** | **OK** |

### Media

| Metric | Value |
|--------|-------|
| Target | 105 |
| Actual | 105 |
| Delta | +0 |
| Status | OK |

---

## Summary

### Corpus Totals

| Content Type | Count | Target | Status |
|-------------|-------|--------|--------|
| Reading passages | 1127 | 1009+ | All levels met |
| Dialogue scenarios | 294 | 294 | Exact match |
| Media catalog entries | 105 | 105 | Exact match |
| Deployed scenarios | 588 | -- | All valid |
| Batch source files | 109 | -- | All valid |

### Issue Summary

| Category | Count | Severity |
|----------|-------|----------|
| Passage question option schema (missing pinyin/text_en on j3_observe_001-020) | 168 | LOW |
| Dialogue missing register on non-best options (239/294 files, all except j3) | 1144 | LOW-MED |
| **All other checks** | **0** | -- |

**Zero critical issues.** No parse errors, no missing required fields, no duplicate IDs, no content duplicates, no empty files, no bad HSK levels, no questions without correct answers.

### Recommended Fixes

1. **Passage j3_observe options** (20 passages, 168 option fields): Add `pinyin` and `text_en` to each option in j3_observe_001 through j3_observe_020. Mechanical fix.

2. **Dialogue register backfill** (239 files, 1144 missing fields): Add `register` field to options 1 and 2 in player turns for all non-j3 dialogue files. Can be inferred from score: score=3 inherits dialogue register, score=2 gets "neutral", score=1 gets appropriate lower register.
