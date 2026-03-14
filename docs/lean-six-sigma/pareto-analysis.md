# Pareto Analysis Framework — Aelu Mandarin

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Data Source:** `error_log`, `review_event`, `crash_log`, `client_error_log`, `grade_appeal` tables

---

## 1. Principle

The Pareto principle (80/20 rule): approximately 80% of defects come from 20% of causes. For Aelu, this means identifying which defect categories, error types, drill types, or content items account for the majority of quality problems — then fixing those first.

---

## 2. Error Type Taxonomy

The `error_log` table enforces a CHECK constraint with 15 valid error types:

| Error Type | Category | Description |
|-----------|----------|------------|
| `tone` | Phonetic | Wrong tone number on a syllable |
| `segment` | Phonetic | Wrong syllable boundary (e.g., "xi'an" vs "xian") |
| `ime_confusable` | Character | Selected wrong but visually/phonetically similar hanzi in IME |
| `grammar` | Structural | Structural grammar error (word order, missing element) |
| `vocab` | Lexical | Wrong meaning / wrong word selected |
| `register_mismatch` | Pragmatic | Wrong formality level for context |
| `particle_misuse` | Structural | Wrong particle (了/过/着/的/得/地) |
| `function_word_omission` | Structural | Missing required function word |
| `temporal_sequencing` | Structural | Time expression placement error |
| `measure_word` | Lexical | Wrong measure word for noun |
| `politeness_softening` | Pragmatic | Too direct or too indirect for context |
| `reference_tracking` | Discourse | Pronoun/reference ambiguity or error |
| `pragmatics_mismatch` | Pragmatic | Contextually inappropriate response |
| `number` | Lexical | Chinese number system conversion error |
| `other` | Uncategorized | No specific pattern matched |

---

## 3. Data Collection Procedure

### Step 1: Define the Time Window

Choose a measurement period with sufficient data (minimum 200 opportunities):

```sql
-- Verify data volume before running Pareto analysis
SELECT
    COUNT(*) AS total_opportunities,
    MIN(created_at) AS earliest,
    MAX(created_at) AS latest
FROM review_event
WHERE created_at >= datetime('now', '-30 days');
```

If total_opportunities < 200, extend the time window or wait for more data. Pareto with small samples can be misleading.

### Step 2: Collect Defect Data

Run the queries in section 4 for each defect source defined in `dpmo-dashboard.md`.

### Step 3: Categorize and Count

Group defects by category, count occurrences, sort descending, compute cumulative percentage.

### Step 4: Generate Chart

Plot bar chart (count per category) with cumulative percentage line overlay (see section 5).

### Step 5: Identify the Vital Few

Find the cutoff point where cumulative percentage crosses 80%. Categories above this line are the "vital few" — focus improvement here.

### Step 6: Prioritize and Act

Use the action prioritization matrix (section 6) to rank fixes by impact and effort.

---

## 4. SQL Queries for Pareto Data

### 4.1 Overall Error Type Distribution

```sql
SELECT
    error_type,
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct,
    ROUND(100.0 * SUM(COUNT(*)) OVER (
        ORDER BY COUNT(*) DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / SUM(COUNT(*)) OVER (), 1) AS cumulative_pct
FROM error_log
WHERE created_at >= datetime('now', '-30 days')
GROUP BY error_type
ORDER BY count DESC;
```

### 4.2 System Defect Categories (Pareto of DPMO Contributors)

```sql
SELECT
    category,
    count,
    ROUND(100.0 * count / SUM(count) OVER (), 1) AS pct,
    ROUND(100.0 * SUM(count) OVER (
        ORDER BY count DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / SUM(count) OVER (), 1) AS cumulative_pct
FROM (
    SELECT 'grade_appeal_upheld' AS category, COUNT(*) AS count
    FROM grade_appeal WHERE status = 'upheld'
    AND created_at >= datetime('now', '-30 days')

    UNION ALL

    SELECT 'ambiguous_content', COUNT(DISTINCT content_item_id)
    FROM error_focus
    WHERE error_type = 'other' AND error_count >= 3 AND resolved = 0

    UNION ALL

    SELECT 'client_render_error', COUNT(*)
    FROM client_error_log
    WHERE error_type LIKE '%drill%'
    AND timestamp >= datetime('now', '-30 days')

    UNION ALL

    SELECT 'session_crash', COUNT(*)
    FROM crash_log
    WHERE request_path LIKE '/api/session%'
    AND timestamp >= datetime('now', '-30 days')

    UNION ALL

    SELECT 'srs_corruption', COUNT(*)
    FROM progress
    WHERE next_review_date IS NOT NULL
    AND interval_days <= 0 AND repetitions > 0

    UNION ALL

    SELECT 'tts_failure', COUNT(*)
    FROM client_event
    WHERE event = 'tts_error'
    AND created_at >= datetime('now', '-30 days')
)
ORDER BY count DESC;
```

### 4.3 Most Error-Prone Content Items

```sql
SELECT
    ci.id,
    ci.hanzi,
    ci.pinyin,
    ci.english,
    ci.hsk_level,
    COUNT(el.id) AS error_count,
    GROUP_CONCAT(DISTINCT el.error_type) AS error_types,
    ROUND(100.0 * COUNT(el.id) / SUM(COUNT(el.id)) OVER (), 1) AS pct
FROM error_log el
JOIN content_item ci ON el.content_item_id = ci.id
WHERE el.created_at >= datetime('now', '-30 days')
GROUP BY ci.id
ORDER BY error_count DESC
LIMIT 20;
```

### 4.4 Most Error-Prone Drill Types

```sql
SELECT
    re.drill_type,
    COUNT(*) AS total_presentations,
    SUM(CASE WHEN re.correct = 0 THEN 1 ELSE 0 END) AS errors,
    ROUND(100.0 * SUM(CASE WHEN re.correct = 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS error_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN re.correct = 0 THEN 1 ELSE 0 END)
          / SUM(SUM(CASE WHEN re.correct = 0 THEN 1 ELSE 0 END)) OVER (), 1) AS pct_of_all_errors
FROM review_event re
WHERE re.created_at >= datetime('now', '-30 days')
GROUP BY re.drill_type
ORDER BY errors DESC;
```

### 4.5 Error Distribution by HSK Level

```sql
SELECT
    ci.hsk_level,
    el.error_type,
    COUNT(*) AS error_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY ci.hsk_level), 1) AS pct_within_level
FROM error_log el
JOIN content_item ci ON ci.id = el.content_item_id
WHERE el.created_at >= datetime('now', '-30 days')
GROUP BY ci.hsk_level, el.error_type
ORDER BY ci.hsk_level, error_count DESC;
```

### 4.6 Error Distribution by Modality

```sql
SELECT
    modality,
    error_type,
    COUNT(*) AS error_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY modality), 1) AS pct_within_modality
FROM error_log
WHERE created_at >= datetime('now', '-30 days')
GROUP BY modality, error_type
ORDER BY modality, error_count DESC;
```

### 4.7 Crash Types

```sql
SELECT
    error_type,
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct,
    ROUND(100.0 * SUM(COUNT(*)) OVER (
        ORDER BY COUNT(*) DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / SUM(COUNT(*)) OVER (), 1) AS cumulative_pct
FROM crash_log
WHERE timestamp >= datetime('now', '-30 days')
GROUP BY error_type
ORDER BY count DESC;
```

### 4.8 Repeat Offenders (Items with 5+ Errors)

```sql
SELECT
    el.content_item_id,
    ci.hanzi,
    ci.pinyin,
    ci.english,
    ci.hsk_level,
    COUNT(*) AS total_errors,
    GROUP_CONCAT(DISTINCT el.error_type) AS error_types,
    MAX(el.created_at) AS last_error_at
FROM error_log el
JOIN content_item ci ON ci.id = el.content_item_id
GROUP BY el.content_item_id
HAVING total_errors >= 5
ORDER BY total_errors DESC
LIMIT 20;
```

---

## 5. Chart Generation (Python/matplotlib)

```python
"""pareto_chart.py — Generate Pareto charts from Aelu defect data."""

import sqlite3
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

DB_PATH = Path(__file__).parent.parent / "data" / "mandarin.db"
CHART_DIR = Path(__file__).parent.parent / "data" / "pareto_charts"


def generate_pareto_chart(
    categories: list[str],
    counts: list[int],
    title: str,
    output_filename: str,
    highlight_80: bool = True,
) -> Path:
    """Generate a Pareto chart: bars (count per category) + cumulative % line."""
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    output_path = CHART_DIR / output_filename

    total = sum(counts)
    if total == 0:
        return output_path

    cumulative = []
    running = 0
    for c in counts:
        running += c
        cumulative.append(100.0 * running / total)

    fig, ax1 = plt.subplots(figsize=(12, 6))

    # Bar chart (counts)
    x = np.arange(len(categories))
    bars = ax1.bar(x, counts, color='#2196F3', alpha=0.8, edgecolor='white')
    ax1.set_ylabel('Count', fontsize=12)
    ax1.set_xlabel('Category', fontsize=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, rotation=45, ha='right', fontsize=9)

    # Cumulative percentage line (right axis)
    ax2 = ax1.twinx()
    ax2.plot(x, cumulative, 'r-o', markersize=5, linewidth=2, label='Cumulative %')
    ax2.set_ylabel('Cumulative %', fontsize=12, color='red')
    ax2.set_ylim(0, 105)
    ax2.tick_params(axis='y', labelcolor='red')

    # 80% threshold line
    if highlight_80:
        ax2.axhline(y=80, color='red', linestyle='--', alpha=0.5, linewidth=1)
        ax2.text(len(categories) - 1, 82, '80%', color='red', fontsize=10)

        # Color the "vital few" bars red
        cutoff_idx = next(
            (i for i, c in enumerate(cumulative) if c >= 80),
            len(cumulative) - 1,
        )
        for i in range(cutoff_idx + 1):
            bars[i].set_color('#F44336')
            bars[i].set_alpha(0.9)

    # Value labels on bars
    for bar, count in zip(bars, counts):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(counts) * 0.01,
            str(count), ha='center', va='bottom', fontsize=9,
        )

    ax1.set_title(title, fontsize=14, fontweight='bold')
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def run_error_type_pareto(db_path: Path = DB_PATH, days: int = 30) -> Path:
    """Generate Pareto chart for error types from error_log."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("""
        SELECT error_type, COUNT(*) AS count
        FROM error_log
        WHERE created_at >= datetime('now', ?)
        GROUP BY error_type
        ORDER BY count DESC
    """, (f'-{days} days',)).fetchall()
    conn.close()

    if not rows:
        return CHART_DIR / "error_type_pareto.png"

    categories = [r[0] for r in rows]
    counts = [r[1] for r in rows]
    return generate_pareto_chart(
        categories, counts,
        f"Error Type Pareto (Last {days} Days)",
        "error_type_pareto.png",
    )


def run_content_item_pareto(db_path: Path = DB_PATH, days: int = 30) -> Path:
    """Generate Pareto chart for most error-prone content items."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("""
        SELECT ci.hanzi || ' (' || ci.english || ')', COUNT(el.id) AS count
        FROM error_log el
        JOIN content_item ci ON el.content_item_id = ci.id
        WHERE el.created_at >= datetime('now', ?)
        GROUP BY ci.id
        ORDER BY count DESC
        LIMIT 20
    """, (f'-{days} days',)).fetchall()
    conn.close()

    if not rows:
        return CHART_DIR / "content_item_pareto.png"

    categories = [r[0] for r in rows]
    counts = [r[1] for r in rows]
    return generate_pareto_chart(
        categories, counts,
        f"Most Error-Prone Items (Last {days} Days)",
        "content_item_pareto.png",
    )


def run_crash_type_pareto(db_path: Path = DB_PATH, days: int = 30) -> Path:
    """Generate Pareto chart for crash types."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("""
        SELECT error_type, COUNT(*) AS count
        FROM crash_log
        WHERE timestamp >= datetime('now', ?)
        GROUP BY error_type
        ORDER BY count DESC
    """, (f'-{days} days',)).fetchall()
    conn.close()

    if not rows:
        return CHART_DIR / "crash_type_pareto.png"

    categories = [r[0] for r in rows]
    counts = [r[1] for r in rows]
    return generate_pareto_chart(
        categories, counts,
        f"Crash Type Pareto (Last {days} Days)",
        "crash_type_pareto.png",
    )
```

---

## 6. Action Prioritization Matrix

After identifying the Pareto "vital few," prioritize fixes using this matrix:

| Factor | Weight | Scale |
|--------|--------|-------|
| **DPMO impact** | 40% | 3=top 20% of defects, 2=next 30%, 1=bottom 50% |
| **Fix effort** | 30% | 3=< 1 day, 2=1-3 days, 1=> 3 days |
| **User visibility** | 20% | 3=user sees wrong grade, 2=user sees slow response, 1=internal metric |
| **Regression risk** | 10% | 3=isolated change, 2=touches shared code, 1=schema migration |

**Priority score = (DPMO * 0.4) + (Effort * 0.3) + (Visibility * 0.2) + (Risk * 0.1)**

Score range: 1.0 - 3.0. Fix items with score >= 2.5 first.

### Example Prioritization

| Defect | DPMO (40%) | Effort (30%) | Visibility (20%) | Risk (10%) | Score | Rank |
|--------|-----------|-------------|------------------|-----------|-------|------|
| Multi-valid-answer false negatives | 3 | 2 | 3 | 2 | 2.6 | 1 |
| Ambiguous content items | 2 | 3 | 2 | 3 | 2.5 | 2 |
| TTS failure on listening drills | 2 | 3 | 2 | 3 | 2.5 | 2 |
| Regional pinyin variants | 1 | 3 | 3 | 3 | 2.2 | 4 |
| Traditional character support | 1 | 1 | 3 | 1 | 1.4 | 5 |

---

## 7. Expected Distribution (SLA Research Baseline)

Based on second language acquisition research for adult Mandarin learners:

```
Error Type          | Expected % | Cumulative %
--------------------|-----------|-------------
tone                |     38%   |     38%
vocab               |     22%   |     60%
grammar             |     10%   |     70%
particle_misuse     |      8%   |     78%
measure_word        |      6%   |     84%     <-- 80% threshold
function_word_omit  |      4%   |     88%
register_mismatch   |      3%   |     91%
ime_confusable      |      3%   |     94%
other               |      2%   |     96%
segment             |      1%   |     97%
pragmatics_mismatch |      1%   |     98%
politeness_soften   |      1%   |     99%
number              |    0.5%   |   99.5%
temporal_sequencing |    0.3%   |   99.8%
reference_tracking  |    0.2%   |    100%
```

**The vital few:** tone + vocab + grammar + particle_misuse account for ~78% of expected errors. Remediation effort should focus here first.

---

## 8. Remediation Strategies by Error Type

| Error Type | Current Remediation in Aelu | Potential Improvement |
|-----------|---------------------------|---------------------|
| `tone` | Tone drills, listening_tone, tone_sandhi, error_focus boost | Tone pair confusion matrix visualization |
| `vocab` | MC drills, reverse_mc, cloze_context, context notes | Multi-answer acceptance, synonym linking |
| `grammar` | Complement, ba_bei, error_correction drills | More grammar patterns for common confusions |
| `particle_misuse` | particle_disc drill, error_focus re-drilling | Contrastive examples (了 vs 过 minimal pairs) |
| `measure_word` | 4 measure_word drill variants | MW grouping by semantic category |
| `register_mismatch` | register_choice drill | More diverse register scenarios |
| `ime_confusable` | IME drill with similar-character distractors | Radical decomposition drill |

---

## 9. Integration with Error Focus System

The `error_focus` table automatically tracks items with repeated errors. The scheduler (`scheduler.py`) uses `error_focus` to boost priority of items with unresolved error patterns. This is the automated "fix the vital few" mechanism.

```sql
-- Items currently in error focus (unresolved)
SELECT
    ef.content_item_id,
    ci.hanzi,
    ci.pinyin,
    ef.error_type,
    ef.error_count,
    ef.consecutive_correct,
    ef.first_flagged_at,
    ef.last_error_at
FROM error_focus ef
JOIN content_item ci ON ci.id = ef.content_item_id
WHERE ef.resolved = 0
ORDER BY ef.error_count DESC;
```

Resolution criteria: An error focus entry resolves when `consecutive_correct >= 3`.

---

## 10. Pareto Review Cadence

| Activity | Frequency | Output |
|----------|-----------|--------|
| Error type Pareto | Monthly | Chart + top 3 action items |
| Content item Pareto | Monthly | Review top 10 items; rewrite or retire |
| Drill type Pareto | Quarterly | Identify drill types needing grading improvement |
| Crash type Pareto | Weekly (if crashes > 0) | Immediate fix for top crash category |
| Full defect category Pareto | At each DMAIC tollgate | Input to Analyze phase |

---

## 11. Historical Pareto Tracking

Track monthly to verify fixes shift the distribution:

```
Date       | #1 Category | #1 Count | #1 Pct | 80% Cutoff Categories
-----------+-------------+----------+--------+----------------------
2026-03    | (baseline)  |          |        |
2026-04    |             |          |        |
2026-05    |             |          |        |
```

**Success indicator:** The #1 category changes over time. If the same category stays #1 for 3+ months after a fix attempt, the fix was ineffective — re-analyze root cause.
