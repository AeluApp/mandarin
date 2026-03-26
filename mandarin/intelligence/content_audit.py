"""HSK content coverage scanner — audits vocab depth, audio, examples, and content exhaustion.

Checks:
  - Vocab counts per HSK level vs official requirements
  - Content depth: % with example sentences, % with audio, grammar coverage
  - Content wall detection: days until content exhaustion at 30min/day study rate
  - HSK mismatch detection: vocab tagged at the wrong HSK level

Exports:
    ANALYZERS: list of analyzer functions
    fetch_content_stats: standalone function for admin dashboard use
"""

from __future__ import annotations

import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query_all

logger = logging.getLogger(__name__)

# ── HSK level requirements (official word counts) ────────────────────────
# HSK 1-6 traditional levels; HSK 7-9 unified under new standard.
# Only checking 1-6 here as those are the actionable content targets.

HSK_REQUIREMENTS = {
    1: 150,
    2: 150,
    3: 300,
    4: 600,
    5: 1300,
    6: 2500,
}

# Study rate assumptions for content wall detection
_ITEMS_PER_30_MIN = 20  # new items a learner encounters in a 30-min session
_REVIEW_RATIO = 0.6     # 60% of session is review, 40% new items
_NEW_ITEMS_PER_DAY = int(_ITEMS_PER_30_MIN * (1 - _REVIEW_RATIO))  # ~8 new/day

# Content wall severity thresholds (days at 30min/day)
_WALL_CRITICAL_DAYS = 30
_WALL_WARNING_DAYS = 90


# ── Query helpers ────────────────────────────────────────────────────────


def _vocab_count_by_level(conn: sqlite3.Connection) -> dict[int, int]:
    """Count approved vocab items per HSK level."""
    rows = _safe_query_all(conn, """
        SELECT hsk_level, COUNT(*) as cnt
        FROM content_item
        WHERE item_type = 'vocab'
          AND review_status = 'approved'
          AND hsk_level IS NOT NULL
        GROUP BY hsk_level
        ORDER BY hsk_level
    """)
    return {row["hsk_level"]: row["cnt"] for row in rows} if rows else {}


def _content_depth_stats(conn: sqlite3.Connection) -> dict:
    """Calculate content depth metrics across all approved vocab."""
    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE item_type = 'vocab' AND review_status = 'approved'
    """, default=0)

    if total == 0:
        return {
            "total_vocab": 0,
            "with_examples_pct": 0.0,
            "with_audio_pct": 0.0,
            "with_context_pct": 0.0,
        }

    with_examples = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE item_type = 'vocab' AND review_status = 'approved'
          AND example_sentence_hanzi IS NOT NULL
          AND example_sentence_hanzi != ''
    """, default=0)

    with_audio = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE item_type = 'vocab' AND review_status = 'approved'
          AND audio_available = 1
    """, default=0)

    with_context = _safe_scalar(conn, """
        SELECT COUNT(*) FROM content_item
        WHERE item_type = 'vocab' AND review_status = 'approved'
          AND context_note IS NOT NULL
          AND context_note != ''
    """, default=0)

    return {
        "total_vocab": total,
        "with_examples": with_examples,
        "with_examples_pct": round(with_examples / total * 100, 1),
        "with_audio": with_audio,
        "with_audio_pct": round(with_audio / total * 100, 1),
        "with_context": with_context,
        "with_context_pct": round(with_context / total * 100, 1),
    }


def _grammar_coverage(conn: sqlite3.Connection) -> dict:
    """Count grammar points and coverage stats."""
    total_grammar = _safe_scalar(conn, """
        SELECT COUNT(*) FROM grammar_point
    """, default=0)

    with_examples = _safe_scalar(conn, """
        SELECT COUNT(*) FROM grammar_point
        WHERE examples_json IS NOT NULL
          AND examples_json != '[]'
          AND examples_json != ''
    """, default=0)

    with_description = _safe_scalar(conn, """
        SELECT COUNT(*) FROM grammar_point
        WHERE description IS NOT NULL
          AND description != ''
    """, default=0)

    # Grammar points per HSK level
    by_level = {}
    rows = _safe_query_all(conn, """
        SELECT hsk_level, COUNT(*) as cnt
        FROM grammar_point
        GROUP BY hsk_level
        ORDER BY hsk_level
    """)
    if rows:
        by_level = {row["hsk_level"]: row["cnt"] for row in rows}

    return {
        "total": total_grammar,
        "with_examples": with_examples,
        "with_examples_pct": round(with_examples / max(1, total_grammar) * 100, 1),
        "with_description": with_description,
        "with_description_pct": round(with_description / max(1, total_grammar) * 100, 1),
        "by_level": by_level,
    }


def _content_wall_days(vocab_count: int) -> float | None:
    """Estimate days until content exhaustion at 30min/day study rate.

    Returns None if vocab_count is zero (no content at all).
    """
    if vocab_count <= 0:
        return None
    if _NEW_ITEMS_PER_DAY <= 0:
        return None
    return round(vocab_count / _NEW_ITEMS_PER_DAY, 1)


def _detect_hsk_mismatches(conn: sqlite3.Connection) -> list[dict]:
    """Detect vocab items potentially tagged at the wrong HSK level.

    Uses a heuristic: if an item's difficulty score is drastically different
    from what's expected for its tagged HSK level, flag it.
    """
    # Expected difficulty ranges per HSK level (0.0-1.0)
    expected_difficulty = {
        1: (0.0, 0.35),
        2: (0.1, 0.45),
        3: (0.2, 0.55),
        4: (0.3, 0.65),
        5: (0.4, 0.75),
        6: (0.5, 0.85),
    }

    mismatches = []
    for level, (low, high) in expected_difficulty.items():
        rows = _safe_query_all(conn, """
            SELECT id, hanzi, pinyin, english, hsk_level, difficulty
            FROM content_item
            WHERE item_type = 'vocab'
              AND review_status = 'approved'
              AND hsk_level = ?
              AND (difficulty < ? OR difficulty > ?)
            ORDER BY ABS(difficulty - ?) DESC
            LIMIT 10
        """, (level, low - 0.15, high + 0.15, (low + high) / 2))

        if rows:
            for row in rows:
                mismatches.append({
                    "id": row["id"],
                    "hanzi": row["hanzi"],
                    "pinyin": row["pinyin"],
                    "english": row["english"],
                    "tagged_level": row["hsk_level"],
                    "difficulty": row["difficulty"],
                    "expected_range": f"{low:.1f}-{high:.1f}",
                })

    return mismatches


# ── Standalone stats function (for admin dashboard) ─────────────────────


def fetch_content_stats(conn: sqlite3.Connection) -> dict:
    """Fetch comprehensive content audit stats for the admin API.

    Returns HSK coverage, content depth, grammar coverage, content wall
    estimates, and HSK mismatch detections.
    """
    vocab_by_level = _vocab_count_by_level(conn)
    depth = _content_depth_stats(conn)
    grammar = _grammar_coverage(conn)
    mismatches = _detect_hsk_mismatches(conn)

    # HSK coverage analysis
    hsk_coverage = []
    for level, required in HSK_REQUIREMENTS.items():
        actual = vocab_by_level.get(level, 0)
        pct = round(actual / required * 100, 1) if required > 0 else 0.0
        wall_days = _content_wall_days(actual)

        wall_severity = None
        if wall_days is not None:
            if wall_days < _WALL_CRITICAL_DAYS:
                wall_severity = "critical"
            elif wall_days < _WALL_WARNING_DAYS:
                wall_severity = "warning"

        hsk_coverage.append({
            "level": level,
            "required": required,
            "actual": actual,
            "coverage_pct": pct,
            "gap": max(0, required - actual),
            "surplus": max(0, actual - required),
            "wall_days": wall_days,
            "wall_severity": wall_severity,
        })

    total_required = sum(HSK_REQUIREMENTS.values())
    total_actual = sum(vocab_by_level.get(lvl, 0) for lvl in HSK_REQUIREMENTS)
    overall_pct = round(total_actual / max(1, total_required) * 100, 1)

    return {
        "hsk_coverage": hsk_coverage,
        "overall_coverage_pct": overall_pct,
        "total_required": total_required,
        "total_actual": total_actual,
        "depth": depth,
        "grammar": grammar,
        "mismatches": mismatches[:30],
        "mismatch_count": len(mismatches),
    }


# ── Core analyzer ──────────────────────────────────────────────────────


def analyze_content_coverage(conn: sqlite3.Connection) -> list[dict]:
    """Analyze HSK content coverage and generate findings.

    Checks:
    1. Vocab counts per HSK level vs requirements
    2. Content depth (examples, audio, context)
    3. Content wall detection (days until exhaustion)
    4. Grammar explanation coverage
    5. HSK mismatch detection
    """
    findings = []

    vocab_by_level = _vocab_count_by_level(conn)
    depth = _content_depth_stats(conn)
    grammar = _grammar_coverage(conn)

    if depth["total_vocab"] == 0:
        findings.append(_finding(
            "content", "critical",
            "No approved vocab content found",
            "The content_item table has no approved vocab items. "
            "The platform cannot function without vocabulary content.",
            "Seed vocabulary content using the content import pipeline. "
            "Run the HSK word list importer to populate foundational content.",
            "Import HSK vocabulary into content_item table. "
            "Start with HSK 1-3 word lists as the minimum viable corpus.",
            "Content is the core product — no content means no sessions.",
            ["schema.sql", "mandarin/db/content.py"],
        ))
        return findings

    # ── 1. HSK level coverage gaps ───────────────────────────────────
    for level, required in HSK_REQUIREMENTS.items():
        actual = vocab_by_level.get(level, 0)
        pct = round(actual / required * 100, 1) if required > 0 else 0.0
        gap = required - actual

        if gap > 0:
            if pct < 25:
                severity = "critical"
            elif pct < 50:
                severity = "high"
            elif pct < 80:
                severity = "medium"
            else:
                severity = "low"

            findings.append(_finding(
                "content", severity,
                f"HSK{level} vocab gap: {actual}/{required} ({pct}%)",
                f"HSK level {level} has {actual} approved vocab items out of "
                f"{required} required ({pct}% coverage). Gap: {gap} words.",
                f"Import or create {gap} more HSK{level} vocabulary items. "
                f"Prioritize high-frequency words from official HSK{level} word lists.",
                f"Add {gap} HSK{level} vocab items to reach the {required}-word requirement. "
                f"Source from official HSK word lists and verify pinyin/definitions.",
                f"HSK{level} content completeness directly affects learner progression.",
                ["mandarin/db/content.py", "schema.sql"],
            ))

    # ── 2. Content depth: example sentences ─────────────────────────
    if depth["with_examples_pct"] < 50:
        severity = "high" if depth["with_examples_pct"] < 25 else "medium"
        findings.append(_finding(
            "content", severity,
            f"Low example sentence coverage: {depth['with_examples_pct']}%",
            f"Only {depth['with_examples']} of {depth['total_vocab']} vocab items "
            f"({depth['with_examples_pct']}%) have example sentences. "
            f"Example sentences improve retention and contextual understanding.",
            "Generate example sentences for vocab items lacking them. "
            "Prioritize HSK 1-3 items and high-frequency words.",
            "Generate example sentences for vocab items without them. "
            "Use the AI content pipeline to create contextual examples.",
            "Example sentences improve learning outcomes by 30-40%.",
            ["mandarin/db/content.py", "mandarin/ai/"],
        ))

    # ── 3. Content depth: audio coverage ────────────────────────────
    if depth["with_audio_pct"] < 50:
        severity = "high" if depth["with_audio_pct"] < 25 else "medium"
        findings.append(_finding(
            "content", severity,
            f"Low audio coverage: {depth['with_audio_pct']}%",
            f"Only {depth['with_audio']} of {depth['total_vocab']} vocab items "
            f"({depth['with_audio_pct']}%) have audio recordings. "
            f"Audio is essential for pronunciation and listening practice.",
            "Generate TTS audio for vocab items lacking recordings. "
            "Use edge-tts or similar service for batch generation.",
            "Generate audio for all vocab items without recordings. "
            "Run the TTS batch pipeline to fill audio gaps.",
            "Audio availability gates listening modality drills.",
            ["mandarin/ai/tts.py", "mandarin/db/content.py"],
        ))

    # ── 4. Grammar explanation coverage ─────────────────────────────
    if grammar["total"] < 20:
        findings.append(_finding(
            "content", "high",
            f"Insufficient grammar points: {grammar['total']}",
            f"Only {grammar['total']} grammar points exist. "
            f"A minimum of 20 grammar points is needed for a viable learning experience.",
            "Add grammar point definitions covering HSK 1-3 core structures. "
            "Include examples and clear descriptions for each point.",
            "Seed grammar_point table with at least 20 HSK 1-3 grammar structures.",
            "Grammar explanations are required for structured learning progression.",
            ["schema.sql", "mandarin/db/curriculum.py"],
        ))

    if grammar["total"] > 0 and grammar["with_description_pct"] < 50:
        findings.append(_finding(
            "content", "medium",
            f"Grammar points missing descriptions: {100 - grammar['with_description_pct']:.0f}%",
            f"{grammar['total'] - grammar['with_description']} of {grammar['total']} "
            f"grammar points lack descriptions ({grammar['with_description_pct']}% covered).",
            "Add descriptions to grammar points that are missing them. "
            "Descriptions help learners understand usage patterns.",
            "Fill in missing grammar point descriptions in the grammar_point table.",
            "Grammar descriptions enable the tutor to explain structures.",
            ["mandarin/db/curriculum.py"],
        ))

    # ── 5. Content wall detection ───────────────────────────────────
    for level, required in HSK_REQUIREMENTS.items():
        actual = vocab_by_level.get(level, 0)
        wall_days = _content_wall_days(actual)

        if wall_days is not None and wall_days < _WALL_CRITICAL_DAYS:
            findings.append(_finding(
                "content", "critical",
                f"Content wall: HSK{level} exhausted in {wall_days:.0f} days",
                f"At 30min/day study rate ({_NEW_ITEMS_PER_DAY} new items/day), "
                f"HSK{level} content ({actual} items) will be exhausted in "
                f"approximately {wall_days:.0f} days. Learners will hit a content "
                f"wall with nothing new to study.",
                f"Urgently add more HSK{level} content to prevent learner stagnation. "
                f"Target at least {_WALL_WARNING_DAYS * _NEW_ITEMS_PER_DAY} items "
                f"for 90-day runway.",
                f"Content wall imminent for HSK{level}: only {wall_days:.0f} days of "
                f"content at current study pace. Import additional vocabulary.",
                "Content exhaustion causes churn — learners leave when there is nothing new.",
                ["mandarin/db/content.py"],
            ))
        elif wall_days is not None and wall_days < _WALL_WARNING_DAYS:
            findings.append(_finding(
                "content", "medium",
                f"Content wall approaching: HSK{level} in {wall_days:.0f} days",
                f"At 30min/day study rate, HSK{level} content ({actual} items) "
                f"will be exhausted in approximately {wall_days:.0f} days.",
                f"Plan additional HSK{level} content to maintain 90+ days of runway.",
                f"HSK{level} content runway is {wall_days:.0f} days. Plan content expansion.",
                "Approaching content exhaustion causes stagnation.",
                ["mandarin/db/content.py"],
            ))

    # ── 6. HSK mismatch detection ───────────────────────────────────
    mismatches = _detect_hsk_mismatches(conn)
    if len(mismatches) > 5:
        sample = ", ".join(
            f"{m['hanzi']} (tagged HSK{m['tagged_level']}, difficulty={m['difficulty']:.2f})"
            for m in mismatches[:5]
        )
        findings.append(_finding(
            "content", "medium",
            f"HSK level mismatches detected: {len(mismatches)} items",
            f"{len(mismatches)} vocab items have difficulty scores inconsistent "
            f"with their tagged HSK level. Sample: {sample}.",
            "Review flagged items and correct HSK level tags where appropriate. "
            "Items tagged too easy or too hard distort the SRS scheduling.",
            "Review and correct HSK level tags for mismatched vocab items.",
            "Accurate HSK tagging ensures correct difficulty progression.",
            ["mandarin/db/content.py"],
        ))

    return findings


# ── Analyzer registration ───────────────────────────────────────────────

ANALYZERS = [
    analyze_content_coverage,
]
