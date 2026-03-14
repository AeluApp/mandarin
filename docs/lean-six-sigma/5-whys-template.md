# 5 Whys Root Cause Analysis Template — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10

---

## 1. Purpose

The 5 Whys technique traces a defect from its surface symptom to its systemic root cause by asking "why?" iteratively. The goal is to find a cause that, if fixed, prevents recurrence — not just the immediate trigger.

---

## 2. Template

```
# 5 Whys Analysis — [DEFECT-ID]

**Date:** YYYY-MM-DD
**Analyst:** [name]
**Defect:** [One-sentence description of what went wrong]
**Impact:** [Who was affected, how many times, severity]
**Detection Method:** [How was this discovered? crash_log, grade_appeal, user report, SPC alert]

## Chain of Whys

**Problem Statement:**
[Specific, measurable description. Include: what happened, when, how often, what was expected.]

**Why 1:** [First-level cause — the immediate trigger]
Evidence: [Data, log entry, or observation that supports this]

**Why 2:** [Why did Why 1 happen?]
Evidence: [Data, log entry, or observation]

**Why 3:** [Why did Why 2 happen?]
Evidence: [Data, log entry, or observation]

**Why 4:** [Why did Why 3 happen?]
Evidence: [Data, log entry, or observation]

**Why 5:** [Why did Why 4 happen? — This should be the systemic root cause]
Evidence: [Data, log entry, or observation]

## Root Cause Classification

- [ ] Systemic (will recur unless process/system is changed)
- [ ] One-off (unique circumstance, unlikely to recur)
- [ ] Design gap (feature/capability never existed)
- [ ] Regression (previously working, broken by a change)

## Corrective Action Plan

| Action | Owner | Deadline | Verification Method |
|--------|-------|----------|-------------------|
| [Immediate fix] | | | |
| [Preventive measure] | | | |
| [Process change] | | | |

## Verification

**Verification date:** YYYY-MM-DD
**Verified by:** [name]
**Result:** [Did the corrective action prevent recurrence? Evidence.]
**DPMO impact:** [Did the defect rate for this category decrease?]
```

---

## 3. Guidelines

### When to Use 5 Whys

- After any Rule 1 SPC violation (point beyond 3 sigma)
- After any upheld grade appeal
- After any session crash affecting a user
- When a Pareto category persists as #1 for 2+ months after a fix attempt
- When a defect recurs after a previous corrective action

### When NOT to Use 5 Whys

- For complex multi-cause problems (use fishbone diagram first to identify candidates, then 5 Whys on each candidate)
- When the root cause is obvious and doesn't need structured analysis
- When data is insufficient to answer "why" at each level (collect data first)

### Rules for Good 5 Whys

1. **Stay on one causal chain.** If you branch at any level, pick the most likely branch and follow it. Analyze other branches separately.
2. **Every "why" must have evidence.** "I think..." is not evidence. Show a log entry, a query result, a test case, or a code reference.
3. **Stop when you reach a cause you can change.** If Why 5 is "the laws of physics," you went too far. Back up to the last actionable level.
4. **Don't blame people.** "Jason made a mistake" is not a root cause. Why did the system allow that mistake? Why wasn't there a check?
5. **The root cause should be systemic.** If fixing it only prevents this one instance, you found a symptom, not a root cause.

---

## 4. Worked Example 1: "Correct Pinyin Answer Marked Wrong"

```
# 5 Whys Analysis — DEFECT-2026-03-001

**Date:** 2026-03-10
**Analyst:** Jason Gerson
**Defect:** Learner typed "gao1xing4" for 高兴 on english_to_pinyin drill, marked incorrect
**Impact:** 1 learner, 1 occurrence, but affects all free-text pinyin drills for any word
**Detection Method:** grade_appeal submission

## Chain of Whys

**Problem Statement:**
On 2026-03-08, a learner completed an english_to_pinyin drill for 高兴 (happy).
They typed "gao1xing4" (tone numbers without spaces). The system marked it incorrect.
Expected: "gao1xing4" should be accepted as equivalent to "gāoxìng".

**Why 1:** The pinyin normalizer did not recognize "gao1xing4" as valid pinyin.
Evidence: Unit test `test_normalize_pinyin("gao1xing4")` returns None (no match).

**Why 2:** The normalizer splits on syllable boundaries using a static syllable table,
but "gao1xing4" has tone numbers interleaved with syllables, making boundary detection fail.
Evidence: The syllable splitter expects "gao xing" or "gāoxìng" but not "gao1xing4"
(tone numbers are stripped AFTER splitting, but splitting fails when numbers are present).

**Why 3:** The normalization pipeline applies operations in the wrong order:
strip tone numbers → split syllables → compare. But it should be:
split syllables (treating digits as boundaries) → extract tone numbers → compare.
Evidence: Code in drills/base.py line 142: `clean = re.sub(r'[0-5]', '', raw)`
runs before `split_syllables()`.

**Why 4:** The normalization pipeline was written for tone-mark input (ā, á, ǎ, à)
as the primary format, with tone numbers as an afterthought. The order of operations
was never re-evaluated when tone number support was added.
Evidence: git blame shows tone number support was added in a later commit
that inserted a regex substitution without restructuring the pipeline.

**Why 5:** There is no integration test that exercises the full normalization pipeline
with tone-number input for multi-syllable words. Unit tests only test single-syllable
cases ("mao1") and pre-spaced multi-syllable cases ("gao1 xing4").
Evidence: grep for "gao1xing4" in test suite returns 0 results.

## Root Cause Classification

- [x] Systemic (will recur for any multi-syllable word typed with tone numbers and no spaces)
- [ ] One-off
- [ ] Design gap
- [ ] Regression

## Corrective Action Plan

| Action | Owner | Deadline | Verification Method |
|--------|-------|----------|-------------------|
| Restructure normalization pipeline: use digits as syllable boundary hints before stripping | Jason | 2026-03-15 | Unit tests for "gao1xing4", "ni3hao3", "xie4xie4" all normalize correctly |
| Add integration tests for tone-number multi-syllable input (no spaces) | Jason | 2026-03-15 | Pytest suite includes 10+ multi-syllable tone-number cases |
| Review all grade_appeal entries for similar false negatives | Jason | 2026-03-12 | SQL query: SELECT * FROM grade_appeal WHERE appeal_text LIKE '%tone number%' |
| Add normalization pipeline to Gage R&R study (gage-rr.md Part 4 and 6) | Jason | Next Gage R&R run | Study includes "gao1xing4" format |

## Verification

**Verification date:** [pending]
**Verified by:** [pending]
**Result:** [pending]
**DPMO impact:** Expected to reduce grade_appeal_upheld defects by ~30% (estimated)
```

---

## 5. Worked Example 2: "Session Crashes on First Use After Gap"

```
# 5 Whys Analysis — DEFECT-2026-03-002

**Date:** 2026-03-10
**Analyst:** Jason Gerson
**Defect:** Session start crashes with TypeError when user returns after 7+ day gap
**Impact:** Any user returning after extended absence. crash_log shows 3 occurrences in 2 weeks.
**Detection Method:** crash_log table, error_type = 'TypeError'

## Chain of Whys

**Problem Statement:**
Between 2026-02-25 and 2026-03-08, three users experienced a TypeError crash when
starting their first session after a 7+ day gap. The traceback points to
scheduler.py line 287: `gap_days = (now - last_session).days` where `last_session`
is None.

**Why 1:** `last_session` is None because the query to find the most recent session
returned no rows.
Evidence: crash_log traceback shows `NoneType has no attribute 'days'` at scheduler.py:287.

**Why 2:** The session lookup query filters by `session_outcome != 'started'`, but
the user's last session had `session_outcome = 'started'` (they opened the app but
didn't complete any drills).
Evidence: `SELECT * FROM session_log WHERE user_id = 3 ORDER BY started_at DESC LIMIT 1`
returns a row with session_outcome = 'started', which the gap calculation query excludes.

**Why 3:** The gap calculation query assumes that if a user has any session_log entries,
at least one will have `session_outcome != 'started'`. But a user can have only
'started' sessions if they've opened the app multiple times without completing drills.
Evidence: `SELECT DISTINCT session_outcome FROM session_log WHERE user_id = 3`
returns only 'started'.

**Why 4:** The `session_outcome` field was added in a migration but existing
sessions were not backfilled — they defaulted to 'started'. The gap calculation
query was updated to use session_outcome but the migration didn't verify data consistency.
Evidence: schema_version table shows session_outcome migration applied, but
`SELECT COUNT(*) FROM session_log WHERE session_outcome = 'started'` returns a
higher count than expected.

**Why 5:** There is no defensive coding pattern for SQLite queries that may return
None. The codebase uses `row['field']` directly instead of the safe pattern
`row.get('field') or default_value`, and there is no NULL check before arithmetic
on query results.
Evidence: This is a known pattern documented in MEMORY.md:
"SQLite Row returns can have None for LEFT JOIN fields — use x.get('field') or 0 pattern"
but it is not consistently applied to all queries.

## Root Cause Classification

- [x] Systemic (affects any query result that can be None; this class of bug will recur)
- [ ] One-off
- [ ] Design gap
- [ ] Regression

## Corrective Action Plan

| Action | Owner | Deadline | Verification Method |
|--------|-------|----------|-------------------|
| Fix scheduler.py:287 — add None check before date arithmetic | Jason | Immediate | Crash no longer reproducible with test user who has only 'started' sessions |
| Audit all `scheduler.py` queries for potential None returns | Jason | 2026-03-12 | grep for `row[` and verify each has None handling |
| Add defensive query wrapper that logs WARNING on None where non-None expected | Jason | 2026-03-15 | New utility function used in scheduler, runner, session modules |
| Backfill session_outcome for historical sessions based on items_completed | Jason | 2026-03-12 | UPDATE session_log SET session_outcome = 'completed' WHERE items_completed > 0 AND session_outcome = 'started' |
| Add test case: user with only 'started' sessions starts new session | Jason | 2026-03-12 | Pytest test passes |

## Verification

**Verification date:** [pending]
**Verified by:** [pending]
**Result:** [pending]
**DPMO impact:** Expected to eliminate session_crash defect category for this specific trigger (est. 3 of ~5 monthly crashes)
```

---

## 6. 5 Whys Analysis Log

Track all completed analyses:

| ID | Date | Defect Summary | Root Cause Type | Status | DPMO Impact |
|----|------|---------------|----------------|--------|-------------|
| DEFECT-2026-03-001 | 2026-03-10 | Pinyin tone number false negative | Systemic | Pending fix | Est. -30% grade appeals |
| DEFECT-2026-03-002 | 2026-03-10 | Session crash on gap return | Systemic | Pending fix | Est. -60% session crashes |

---

## 7. Integration with DMAIC

| DMAIC Phase | 5 Whys Role |
|------------|-------------|
| **Define** | Not used — problem is being scoped, not analyzed |
| **Measure** | Not used — establishing baseline measurements |
| **Analyze** | **Primary use.** Apply 5 Whys to top Pareto categories from fishbone analysis |
| **Improve** | Corrective actions from 5 Whys become improvement projects |
| **Control** | Verification step confirms fix held; new defects trigger new 5 Whys |
