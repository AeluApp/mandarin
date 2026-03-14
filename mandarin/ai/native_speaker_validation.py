"""Native Speaker Validation Protocol (Doc 22).

Queue management, validation recording, and analytics for
native speaker review of generated Chinese content.

Targets content that automated systems cannot reliably assess:
naturalness, register appropriateness, drift-risk vocabulary.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# QUEUE MANAGEMENT
# ─────────────────────────────────────────────

def queue_for_native_speaker_review(
    conn: sqlite3.Connection,
    content_hanzi: str,
    content_type: str,
    queue_reason: str,
    content_item_id: int = None,
    hsk_level: int = None,
    content_lens: str = None,
    target_vocabulary: str = None,
    intended_register: str = None,
) -> int:
    """Add an item to the native speaker validation queue. Returns queue entry ID."""
    cursor = conn.execute("""
        INSERT INTO native_speaker_validation_queue
        (content_hanzi, content_type, queue_reason,
         content_item_id, hsk_level, content_lens,
         target_vocabulary, intended_register)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        content_hanzi, content_type, queue_reason,
        content_item_id, hsk_level, content_lens,
        target_vocabulary, intended_register,
    ))
    return cursor.lastrowid


def get_validation_batch(
    conn: sqlite3.Connection,
    n: int = 20,
    priority_reasons: list = None,
) -> list[dict]:
    """Return next batch of items for native speaker review.

    Priority order: drift_risk > human_flagged > hsk_high_level > systematic.
    """
    if priority_reasons is None:
        priority_reasons = [
            "drift_risk_flagged",
            "human_flagged",
            "hsk_high_level",
            "new_content_type",
            "register_mismatch",
            "systematic_review",
        ]

    all_items = []
    for reason in priority_reasons:
        if len(all_items) >= n:
            break
        remaining = n - len(all_items)
        items = conn.execute("""
            SELECT * FROM native_speaker_validation_queue
            WHERE validated_at IS NULL
            AND queue_reason = ?
            ORDER BY queued_at ASC
            LIMIT ?
        """, (reason, remaining)).fetchall()
        all_items.extend([dict(i) for i in items])

    return all_items


def export_validation_sheet(conn: sqlite3.Connection, batch: list[dict]) -> str:
    """Export validation batch as structured plain text for tutor session."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Aelu Native Speaker Validation Sheet",
        f"# Generated: {now}",
        f"# Items: {len(batch)}",
        "",
        "Instructions:",
        "For each item, please provide:",
        "  N (1-5): Naturalness score. 1=clearly unnatural, 3=acceptable, 5=sounds native",
        "  R (Y/N): Register correct for intended use?",
        "  V (Y/N): Is this usage current/not dated?",
        "  Note: Any specific issue or suggested revision",
        "",
    ]

    for i, item in enumerate(batch, 1):
        hsk = item.get("hsk_level", "?")
        ctype = item.get("content_type", "")
        reason = item.get("queue_reason", "")
        lines.extend([
            f"Item {i} [{reason}] HSK {hsk} | {ctype}",
            f"Content: {item['content_hanzi']}",
        ])
        if item.get("target_vocabulary"):
            lines.append(f"Teaching: {item['target_vocabulary']}")
        if item.get("intended_register"):
            lines.append(f"Register: {item['intended_register']}")
        lines.extend([
            "N: ___ R: ___ V: ___",
            "Note: _______________________",
            "Revision (if needed): _______________________",
            "",
        ])

    return "\n".join(lines)


# ─────────────────────────────────────────────
# VALIDATION RECORDING
# ─────────────────────────────────────────────

def record_validation_result(
    conn: sqlite3.Connection,
    queue_entry_id: int,
    validator_id: int,
    naturalness_score: int,
    register_correct: bool,
    usage_current: bool,
    verdict: str,
    validator_note: str = None,
    revised_content: str = None,
) -> dict:
    """Record a validation result and trigger downstream actions."""
    conn.execute("""
        UPDATE native_speaker_validation_queue SET
            validated_at=datetime('now'),
            validated_by=?,
            naturalness_score=?,
            register_correct=?,
            usage_current=?,
            verdict=?,
            validator_note=?,
            revised_content=?
        WHERE id=?
    """, (
        str(validator_id), naturalness_score,
        int(register_correct), int(usage_current),
        verdict, validator_note, revised_content,
        queue_entry_id,
    ))

    entry = conn.execute(
        "SELECT * FROM native_speaker_validation_queue WHERE id=?",
        (queue_entry_id,),
    ).fetchone()

    if not entry:
        return {"verdict": verdict, "action_taken": "pending"}

    action = _apply_validation_verdict(conn, dict(entry))
    return {"verdict": verdict, "action_taken": action}


def _apply_validation_verdict(conn: sqlite3.Connection, entry: dict) -> str:
    """Apply validation verdict to the content item."""
    verdict = entry["verdict"]
    content_item_id = entry.get("content_item_id")

    if verdict == "approved":
        if content_item_id:
            conn.execute(
                "UPDATE content_item SET native_speaker_validated=1 WHERE id=?",
                (content_item_id,),
            )
        action = "approved_to_srs"

    elif verdict == "approved_with_note":
        if content_item_id:
            conn.execute(
                "UPDATE content_item SET native_speaker_validated=1, "
                "native_speaker_note=? WHERE id=?",
                (entry.get("validator_note"), content_item_id),
            )
        action = "approved_to_srs"

    elif verdict == "needs_revision" and entry.get("revised_content"):
        queue_for_native_speaker_review(
            conn,
            content_hanzi=entry["revised_content"],
            content_type=entry["content_type"],
            queue_reason="systematic_review",
            content_item_id=content_item_id,
            hsk_level=entry.get("hsk_level"),
            target_vocabulary=entry.get("target_vocabulary"),
        )
        if content_item_id:
            conn.execute(
                "UPDATE content_item SET suspended_for_revision=1 WHERE id=?",
                (content_item_id,),
            )
        action = "queued_for_revision"

    elif verdict == "reject":
        if content_item_id:
            conn.execute(
                "UPDATE content_item SET rejected_native_speaker=1 WHERE id=?",
                (content_item_id,),
            )
        action = "rejected"

    else:
        action = "pending"

    conn.execute(
        "UPDATE native_speaker_validation_queue SET action_taken=? WHERE id=?",
        (action, entry["id"]),
    )
    return action


# ─────────────────────────────────────────────
# ANALYZER
# ─────────────────────────────────────────────

def analyze_native_speaker_validation(conn: sqlite3.Connection) -> list[dict]:
    """Audit cycle analyzer for validation quality and queue health."""
    from ..intelligence._base import _finding
    findings = []

    # 1. Queue backlog
    try:
        backlog = conn.execute("""
            SELECT COUNT(*) as cnt,
                   COUNT(CASE WHEN queue_reason='drift_risk_flagged' THEN 1 END) as drift_count,
                   COUNT(CASE WHEN queue_reason='human_flagged' THEN 1 END) as human_count
            FROM native_speaker_validation_queue
            WHERE validated_at IS NULL
        """).fetchone()

        total = (backlog["cnt"] or 0) if backlog else 0
        if total > 50:
            drift = (backlog["drift_count"] or 0) if backlog else 0
            human = (backlog["human_count"] or 0) if backlog else 0
            findings.append(_finding(
                dimension="native_speaker_validation",
                severity="high" if total > 100 else "medium",
                title=f"Validation queue backlog: {total} items awaiting review",
                analysis=f"{drift} drift-risk items, {human} learner-flagged items in queue. "
                         "Quality gate not keeping pace with generation volume.",
                recommendation="Schedule native speaker validation session. "
                               "Target: clear queue below 50 items.",
                claude_prompt="Check native_speaker_validation_queue for pending items.",
                impact="Unvalidated content reaching learners without naturalness check.",
                files=["mandarin/ai/native_speaker_validation.py"],
            ))
    except sqlite3.OperationalError:
        pass

    # 2. Rejection rate
    try:
        stats = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN verdict='reject' THEN 1 ELSE 0 END) as rejected,
                   SUM(CASE WHEN verdict='needs_revision' THEN 1 ELSE 0 END) as needs_revision,
                   AVG(naturalness_score) as avg_naturalness
            FROM native_speaker_validation_queue
            WHERE validated_at >= datetime('now','-60 days')
            AND validated_at IS NOT NULL
        """).fetchone()

        total = (stats["total"] or 0) if stats else 0
        if total >= 20:
            rejected = (stats["rejected"] or 0)
            needs_rev = (stats["needs_revision"] or 0)
            rate = (rejected + needs_rev) / total
            avg_nat = stats["avg_naturalness"]

            if rate > 0.25:
                findings.append(_finding(
                    dimension="native_speaker_validation",
                    severity="high",
                    title=f"High native speaker rejection rate: {rate:.0%}",
                    analysis=f"{rate:.0%} of validated items rejected or needing revision. "
                             f"Avg naturalness: {avg_nat:.1f}/5.",
                    recommendation="Review rejection patterns. Check prompt keys and RAG quality.",
                    claude_prompt="Analyze native_speaker_validation_queue verdict patterns.",
                    impact="Generation quality below acceptable threshold for naturalness.",
                    files=["mandarin/ai/native_speaker_validation.py"],
                ))
            elif avg_nat and avg_nat < 3.5:
                findings.append(_finding(
                    dimension="native_speaker_validation",
                    severity="medium",
                    title=f"Average naturalness score low: {avg_nat:.1f}/5",
                    analysis="Content technically acceptable but not natural-sounding.",
                    recommendation="Improve example sentences in RAG knowledge base.",
                    claude_prompt="Check average naturalness by content_type and hsk_level.",
                    impact="Learners may internalize slightly unnatural patterns.",
                    files=["mandarin/ai/native_speaker_validation.py", "mandarin/ai/rag_layer.py"],
                ))
    except sqlite3.OperationalError:
        pass

    # 3. Unvalidated HSK 6+ in active SRS
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt
            FROM content_item ci
            JOIN memory_states ms ON ms.content_item_id = ci.id
            WHERE ci.hsk_level >= 6
            AND ci.status = 'drill_ready'
            AND (ci.native_speaker_validated IS NULL OR ci.native_speaker_validated = 0)
            AND ms.reps >= 5
        """).fetchone()
        unvalidated = (row["cnt"] or 0) if row else 0

        if unvalidated > 20:
            findings.append(_finding(
                dimension="native_speaker_validation",
                severity="medium",
                title=f"{unvalidated} HSK 6+ items actively studied without native speaker validation",
                analysis="High-level content reaching learners without naturalness check.",
                recommendation="Prioritize HSK 6+ items in next validation batch.",
                claude_prompt="Find content_item with hsk_level>=6 and no native_speaker_validated.",
                impact="Potential for unnatural patterns at advanced level.",
                files=["mandarin/ai/native_speaker_validation.py"],
            ))
    except sqlite3.OperationalError:
        pass

    return findings
