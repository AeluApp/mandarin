"""Content gap detector — identifies what's missing from the corpus.

Analyzes the content library to find:
1. HSK level coverage gaps (which levels are thin)
2. Topic coverage gaps (which topics lack material)
3. Grammar point coverage (which patterns have no practice items)
4. Drill type coverage (which modalities are under-served)
5. Difficulty distribution issues (too easy/hard for current learners)

All deterministic — no LLM needed. Reads from DB and data files.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"

# Minimum thresholds for "adequate" coverage
MIN_ITEMS_PER_HSK_LEVEL = 30
MIN_ITEMS_PER_GRAMMAR_POINT = 2
MIN_READING_PASSAGES_PER_LEVEL = 10
MIN_MEDIA_PER_LEVEL = 3


def detect_gaps(conn) -> dict:
    """Run full gap analysis. Returns structured report.

    Returns:
        {
            "hsk_coverage": {...},
            "grammar_coverage": {...},
            "topic_coverage": {...},
            "reading_coverage": {...},
            "media_coverage": {...},
            "drill_distribution": {...},
            "recommendations": [...],
            "overall_score": float (0-1, 1 = no gaps),
        }
    """
    hsk = _analyze_hsk_coverage(conn)
    grammar = _analyze_grammar_coverage(conn)
    topics = _analyze_topic_coverage(conn)
    reading = _analyze_reading_coverage()
    media = _analyze_media_coverage()
    drills = _analyze_drill_distribution(conn)

    recommendations = _generate_recommendations(
        hsk, grammar, topics, reading, media, drills,
    )

    # Overall score: weighted average of sub-scores
    scores = [
        hsk.get("score", 0),
        grammar.get("score", 0),
        reading.get("score", 0),
        media.get("score", 0),
    ]
    overall = sum(scores) / max(len(scores), 1)

    return {
        "hsk_coverage": hsk,
        "grammar_coverage": grammar,
        "topic_coverage": topics,
        "reading_coverage": reading,
        "media_coverage": media,
        "drill_distribution": drills,
        "recommendations": recommendations,
        "overall_score": round(overall, 3),
    }


def detect_user_gaps(conn, user_id: int) -> dict:
    """Detect content gaps relative to a specific user's progress.

    Finds areas where the user is studying but content is thin.
    """
    # Get user's active HSK levels
    levels = conn.execute("""
        SELECT DISTINCT ci.hsk_level
        FROM progress p
        JOIN content_item ci ON ci.id = p.content_item_id
        WHERE p.user_id = ?
        ORDER BY ci.hsk_level
    """, (user_id,)).fetchall()
    active_levels = [r["hsk_level"] for r in levels]

    # Get user's weakest grammar points
    weak_grammar = conn.execute("""
        SELECT gp.id, gp.name, gp.hsk_level,
               COUNT(el.id) as error_count,
               COALESCE(gpr.mastery_score, 0) as mastery
        FROM grammar_point gp
        LEFT JOIN content_grammar cg ON cg.grammar_point_id = gp.id
        LEFT JOIN error_log el ON el.content_item_id = cg.content_item_id
            AND el.user_id = ?
        LEFT JOIN grammar_progress gpr ON gpr.grammar_point_id = gp.id
            AND gpr.user_id = ?
        WHERE gp.hsk_level IN ({})
        GROUP BY gp.id
        HAVING error_count > 0 OR mastery < 0.5
        ORDER BY error_count DESC, mastery ASC
        LIMIT 10
    """.format(",".join("?" * len(active_levels))),
        (user_id, user_id, *active_levels),
    ).fetchall() if active_levels else []

    # Check if weak grammar points have enough practice items
    grammar_gaps = []
    for gp in weak_grammar:
        item_count = conn.execute("""
            SELECT COUNT(*) as cnt FROM content_grammar
            WHERE grammar_point_id = ?
        """, (gp["id"],)).fetchone()["cnt"]

        if item_count < MIN_ITEMS_PER_GRAMMAR_POINT:
            grammar_gaps.append({
                "grammar_point_id": gp["id"],
                "name": gp["name"],
                "hsk_level": gp["hsk_level"],
                "error_count": gp["error_count"],
                "mastery": round(gp["mastery"], 3),
                "available_items": item_count,
                "needed": MIN_ITEMS_PER_GRAMMAR_POINT,
            })

    return {
        "active_levels": active_levels,
        "grammar_gaps": grammar_gaps,
        "weak_grammar_count": len(weak_grammar),
        "gaps_with_thin_content": len(grammar_gaps),
    }


# ── Sub-analyzers ────────────────────────────────────

def _analyze_hsk_coverage(conn) -> dict:
    """Check content item count per HSK level."""
    rows = conn.execute("""
        SELECT hsk_level, COUNT(*) as cnt
        FROM content_item
        WHERE review_status = 'approved'
        GROUP BY hsk_level
        ORDER BY hsk_level
    """).fetchall()

    levels = {}
    gaps = []
    total = 0
    for r in rows:
        level = r["hsk_level"]
        count = r["cnt"]
        total += count
        adequate = count >= MIN_ITEMS_PER_HSK_LEVEL
        levels[str(level)] = {"count": count, "adequate": adequate}
        if not adequate:
            gaps.append({
                "level": level,
                "count": count,
                "needed": MIN_ITEMS_PER_HSK_LEVEL,
                "deficit": MIN_ITEMS_PER_HSK_LEVEL - count,
            })

    # Check for missing levels (1-6 should all exist)
    for lvl in range(1, 7):
        if str(lvl) not in levels:
            gaps.append({
                "level": lvl, "count": 0,
                "needed": MIN_ITEMS_PER_HSK_LEVEL,
                "deficit": MIN_ITEMS_PER_HSK_LEVEL,
            })

    score = 1.0 - (len(gaps) / 6.0) if total > 0 else 0.0

    return {
        "levels": levels,
        "total_items": total,
        "gaps": gaps,
        "score": round(max(0.0, score), 3),
    }


def _analyze_grammar_coverage(conn) -> dict:
    """Check which grammar points lack linked content items."""
    rows = conn.execute("""
        SELECT gp.id, gp.name, gp.hsk_level,
               COUNT(cg.content_item_id) as item_count
        FROM grammar_point gp
        LEFT JOIN content_grammar cg ON cg.grammar_point_id = gp.id
        GROUP BY gp.id
        ORDER BY item_count ASC
    """).fetchall()

    total = len(rows)
    gaps = []
    for r in rows:
        if r["item_count"] < MIN_ITEMS_PER_GRAMMAR_POINT:
            gaps.append({
                "grammar_point_id": r["id"],
                "name": r["name"],
                "hsk_level": r["hsk_level"],
                "item_count": r["item_count"],
                "needed": MIN_ITEMS_PER_GRAMMAR_POINT,
            })

    score = 1.0 - (len(gaps) / max(total, 1))

    return {
        "total_grammar_points": total,
        "under_served": len(gaps),
        "gaps": gaps[:20],  # Top 20 worst
        "score": round(max(0.0, score), 3),
    }


def _analyze_topic_coverage(conn) -> dict:
    """Analyze topic distribution in content items."""
    # Use content_lens or tags if available
    rows = conn.execute("""
        SELECT content_lens, COUNT(*) as cnt
        FROM content_item
        WHERE content_lens IS NOT NULL AND content_lens != ''
        GROUP BY content_lens
        ORDER BY cnt DESC
    """).fetchall()

    topics = {r["content_lens"]: r["cnt"] for r in rows}

    # Also check context_notes for topic diversity
    try:
        note_rows = conn.execute("""
            SELECT context_note, COUNT(*) as cnt
            FROM content_item
            WHERE context_note IS NOT NULL AND context_note != ''
            GROUP BY context_note
            ORDER BY cnt DESC
            LIMIT 20
        """).fetchall()
        note_topics = {r["context_note"][:50]: r["cnt"] for r in note_rows}
    except Exception:
        note_topics = {}

    return {
        "by_lens": topics,
        "by_context": note_topics,
        "unique_lenses": len(topics),
    }


def _analyze_reading_coverage() -> dict:
    """Check reading passage distribution by HSK level."""
    path = _DATA_DIR / "reading_passages.json"
    if not path.exists():
        return {"total": 0, "by_level": {}, "gaps": [], "score": 0.0}

    try:
        with open(path) as f:
            data = json.load(f)
        passages = data if isinstance(data, list) else data.get("passages", [])
    except (OSError, json.JSONDecodeError):
        return {"total": 0, "by_level": {}, "gaps": [], "score": 0.0}

    by_level = Counter()
    for p in passages:
        by_level[p.get("hsk_level", 0)] += 1

    gaps = []
    for lvl in range(1, 7):
        count = by_level.get(lvl, 0)
        if count < MIN_READING_PASSAGES_PER_LEVEL:
            gaps.append({
                "level": lvl,
                "count": count,
                "needed": MIN_READING_PASSAGES_PER_LEVEL,
            })

    score = 1.0 - (len(gaps) / 6.0) if passages else 0.0

    return {
        "total": len(passages),
        "by_level": dict(sorted(by_level.items())),
        "gaps": gaps,
        "score": round(max(0.0, score), 3),
    }


def _analyze_media_coverage() -> dict:
    """Check media catalog distribution by HSK level."""
    path = _DATA_DIR / "media_catalog.json"
    if not path.exists():
        return {"total": 0, "by_level": {}, "gaps": [], "score": 0.0}

    try:
        with open(path) as f:
            data = json.load(f)
        entries = data if isinstance(data, list) else data.get("catalog", [])
    except (OSError, json.JSONDecodeError):
        return {"total": 0, "by_level": {}, "gaps": [], "score": 0.0}

    by_level = Counter()
    for e in entries:
        by_level[e.get("hsk_level", 0)] += 1

    gaps = []
    for lvl in range(1, 7):
        count = by_level.get(lvl, 0)
        if count < MIN_MEDIA_PER_LEVEL:
            gaps.append({
                "level": lvl,
                "count": count,
                "needed": MIN_MEDIA_PER_LEVEL,
            })

    score = 1.0 - (len(gaps) / 6.0) if entries else 0.0

    return {
        "total": len(entries),
        "by_level": dict(sorted(by_level.items())),
        "gaps": gaps,
        "score": round(max(0.0, score), 3),
    }


def _analyze_drill_distribution(conn) -> dict:
    """Check which drill types are under-represented in recent sessions."""
    try:
        rows = conn.execute("""
            SELECT drill_type, COUNT(*) as cnt
            FROM work_item
            WHERE created_at >= datetime('now', '-30 days')
            GROUP BY drill_type
            ORDER BY cnt DESC
        """).fetchall()
    except Exception:
        rows = []

    distribution = {r["drill_type"]: r["cnt"] for r in rows}

    # Check for modalities with zero activity
    expected_modalities = [
        "reading", "listening", "speaking", "ime", "mc", "reverse_mc",
        "tone", "translation", "sentence_build",
    ]
    missing = [m for m in expected_modalities if m not in distribution]

    return {
        "by_drill_type": distribution,
        "inactive_modalities": missing,
        "total_drills_30d": sum(distribution.values()),
    }


def _generate_recommendations(
    hsk: dict, grammar: dict, topics: dict,
    reading: dict, media: dict, drills: dict,
) -> list[dict]:
    """Generate actionable recommendations from gap analysis."""
    recs = []

    # HSK level gaps
    for gap in hsk.get("gaps", []):
        recs.append({
            "priority": "high" if gap["deficit"] > 20 else "medium",
            "area": "vocabulary",
            "action": f"Add {gap['deficit']} more HSK {gap['level']} items",
            "command": f"./run add-hsk {gap['level']}",
        })

    # Grammar coverage gaps
    for gap in grammar.get("gaps", [])[:5]:
        recs.append({
            "priority": "high" if gap["item_count"] == 0 else "medium",
            "area": "grammar",
            "action": f"Link content items to grammar point '{gap['name']}' "
                     f"(HSK {gap['hsk_level']}, currently {gap['item_count']} items)",
            "command": None,
        })

    # Reading passage gaps
    for gap in reading.get("gaps", []):
        recs.append({
            "priority": "medium",
            "area": "reading",
            "action": f"Generate {gap['needed'] - gap['count']} more HSK {gap['level']} "
                     f"reading passages",
            "command": f"python scripts/expand_content.py --hsk-levels {gap['level']} "
                      f"--count {gap['needed'] - gap['count']}",
        })

    # Media gaps
    for gap in media.get("gaps", []):
        recs.append({
            "priority": "low",
            "area": "media",
            "action": f"Add {gap['needed'] - gap['count']} more HSK {gap['level']} "
                     f"media entries",
            "command": None,
        })

    # Inactive drill modalities
    for mod in drills.get("inactive_modalities", []):
        recs.append({
            "priority": "low",
            "area": "drills",
            "action": f"No '{mod}' drills in last 30 days — consider scheduler adjustment",
            "command": None,
        })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 3))

    return recs
