"""Delayed Recall Validation — schedule and administer integrity checks.

Anti-Goodhart Layer 2: items that reach mastery get scheduled for re-test at
7, 14, and 30 days. Results feed counter-metrics ONLY, never SRS scheduling.

This is different from normal SRS reviews:
- Normal reviews: scheduled by the spaced repetition algorithm, results feed
  back into the SRS state (progress table, mastery_stage, ease, interval).
- Validation checks: scheduled at fixed delays from mastery promotion,
  results go to counter_metric_delayed_validation table. The SRS never sees
  them. If a "mastered" item fails validation, that's signal for the
  counter-metrics system — not for the SRS to reschedule.
"""

from __future__ import annotations

import logging
import random
import sqlite3
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Validation delays (days after mastery promotion)
VALIDATION_DELAYS = [7, 14, 30]

# Max validations to inject per session (light touch — don't disrupt learning)
MAX_VALIDATIONS_PER_SESSION = 1

# Only schedule for items reaching these stages
PROMOTION_STAGES = {"stable", "durable"}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def schedule_validation_checks(conn: sqlite3.Connection,
                                content_item_id: int,
                                user_id: int = 1,
                                modality: str = "reading",
                                mastery_stage: str = "stable") -> int:
    """Schedule delayed recall validation checks for an item that just got promoted.

    Called from the counter-metrics daemon (not from SRS) when it detects
    newly promoted items. Returns number of checks scheduled.
    """
    if not _table_exists(conn, "counter_metric_delayed_validation"):
        return 0

    if mastery_stage not in PROMOTION_STAGES:
        return 0

    now = datetime.now(UTC)
    scheduled = 0

    for delay in VALIDATION_DELAYS:
        # Don't duplicate: check if already scheduled for this item + delay
        existing = conn.execute("""
            SELECT 1 FROM counter_metric_delayed_validation
            WHERE user_id = ? AND content_item_id = ? AND delay_days = ?
              AND status = 'pending'
        """, (user_id, content_item_id, delay)).fetchone()
        if existing:
            continue

        check_date = now + timedelta(days=delay)
        conn.execute("""
            INSERT INTO counter_metric_delayed_validation
            (user_id, content_item_id, modality, scheduled_at, delay_days,
             status, mastery_at_schedule)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """, (user_id, content_item_id, modality,
              check_date.isoformat(), delay, mastery_stage))
        scheduled += 1

    if scheduled:
        conn.commit()
    return scheduled


def schedule_validations_for_recent_promotions(conn: sqlite3.Connection,
                                                user_id: int = 1,
                                                lookback_days: int = 1) -> int:
    """Scan progress table for recent mastery promotions and schedule validations.

    Called by the counter-metrics daemon. Looks for items that recently
    reached stable/durable and don't yet have pending validations.
    """
    if not _table_exists(conn, "counter_metric_delayed_validation"):
        return 0
    if not _table_exists(conn, "progress"):
        return 0

    rows = conn.execute("""
        SELECT p.content_item_id, p.modality, p.mastery_stage
        FROM progress p
        WHERE p.user_id = ?
          AND p.mastery_stage IN ('stable', 'durable')
          AND p.last_review_date >= date('now', ? || ' days')
          AND NOT EXISTS (
              SELECT 1 FROM counter_metric_delayed_validation dv
              WHERE dv.user_id = p.user_id
                AND dv.content_item_id = p.content_item_id
                AND dv.status = 'pending'
          )
    """, (user_id, f"-{lookback_days}")).fetchall()

    total = 0
    for row in rows:
        total += schedule_validation_checks(
            conn, row["content_item_id"], user_id=user_id,
            modality=row["modality"] or "reading",
            mastery_stage=row["mastery_stage"],
        )
    return total


def get_due_validations(conn: sqlite3.Connection,
                        user_id: int = 1,
                        limit: int = 3) -> list[dict[str, Any]]:
    """Get validation checks that are due for administration.

    Returns validation records enriched with content_item data.
    """
    if not _table_exists(conn, "counter_metric_delayed_validation"):
        return []

    now = datetime.now(UTC).isoformat()
    rows = conn.execute("""
        SELECT dv.*, ci.hanzi, ci.pinyin, ci.english, ci.difficulty
        FROM counter_metric_delayed_validation dv
        JOIN content_item ci ON dv.content_item_id = ci.id
        WHERE dv.user_id = ?
          AND dv.status = 'pending'
          AND dv.scheduled_at <= ?
        ORDER BY dv.scheduled_at ASC
        LIMIT ?
    """, (user_id, now, limit)).fetchall()

    return [dict(r) for r in rows]


def pick_validation_drill_type(item: dict[str, Any], delay_days: int) -> str:
    """Pick a drill type for a validation check.

    Uses harder drills for longer delays — if you truly mastered it,
    you should be able to produce it, not just recognize it.
    """
    if delay_days >= 30:
        return random.choice(["english_to_pinyin", "sentence_build"])
    elif delay_days >= 14:
        return random.choice(["reverse_mc", "english_to_pinyin"])
    else:
        return random.choice(["reverse_mc", "mc"])


def get_session_validations(conn: sqlite3.Connection,
                            user_id: int = 1) -> list[dict[str, Any]]:
    """Get validation probes to inject into a session.

    Returns a list of validation specs ready for the drill runner:
        [{content_item_id, modality, drill_type, hanzi, english, pinyin,
          is_delayed_validation: True, validation_id, delay_days}, ...]
    """
    due = get_due_validations(conn, user_id=user_id,
                              limit=MAX_VALIDATIONS_PER_SESSION + 2)
    if not due:
        return []

    probes = []
    for item in due[:MAX_VALIDATIONS_PER_SESSION]:
        drill_type = pick_validation_drill_type(item, item["delay_days"])
        probes.append({
            "content_item_id": item["content_item_id"],
            "modality": item.get("modality", "reading"),
            "drill_type": drill_type,
            "hanzi": item.get("hanzi"),
            "english": item.get("english"),
            "pinyin": item.get("pinyin"),
            "difficulty": item.get("difficulty", 0.5),
            "is_delayed_validation": True,
            "validation_id": item["id"],
            "delay_days": item["delay_days"],
        })

    return probes


def record_validation_result(conn: sqlite3.Connection,
                              validation_id: int,
                              correct: bool,
                              response_ms: int | None = None,
                              session_id: int | None = None,
                              drill_type: str | None = None) -> None:
    """Record the result of a delayed validation check.

    IMPORTANT: This writes to counter_metric_delayed_validation only.
    Results NEVER feed back into SRS scheduling.
    """
    if not _table_exists(conn, "counter_metric_delayed_validation"):
        return

    now = datetime.now(UTC).isoformat()
    conn.execute("""
        UPDATE counter_metric_delayed_validation
        SET status = 'completed',
            administered_at = ?,
            correct = ?,
            response_ms = ?,
            session_id = ?,
            drill_type = ?
        WHERE id = ?
    """, (now, 1 if correct else 0, response_ms, session_id,
          drill_type, validation_id))
    conn.commit()


def get_validation_summary(conn: sqlite3.Connection,
                           user_id: int = 1,
                           window_days: int = 90) -> dict[str, Any]:
    """Summarize delayed validation performance for a user.

    Returns accuracy overall and by delay bracket.
    """
    if not _table_exists(conn, "counter_metric_delayed_validation"):
        return {"accuracy": None, "by_delay": {}, "sample_size": 0}

    rows = conn.execute("""
        SELECT delay_days, correct
        FROM counter_metric_delayed_validation
        WHERE user_id = ?
          AND status = 'completed'
          AND administered_at >= datetime('now', ? || ' days')
    """, (user_id, f"-{window_days}")).fetchall()

    if not rows:
        return {"accuracy": None, "by_delay": {}, "sample_size": 0}

    total = len(rows)
    correct = sum(1 for r in rows if r["correct"])

    by_delay: dict[int, dict[str, int]] = {}
    for r in rows:
        d = r["delay_days"]
        if d not in by_delay:
            by_delay[d] = {"total": 0, "correct": 0}
        by_delay[d]["total"] += 1
        if r["correct"]:
            by_delay[d]["correct"] += 1

    by_delay_summary = {}
    for d, counts in sorted(by_delay.items()):
        by_delay_summary[f"{d}d"] = {
            "accuracy": round(counts["correct"] / counts["total"], 4)
            if counts["total"] > 0 else None,
            "sample_size": counts["total"],
        }

    return {
        "accuracy": round(correct / total, 4) if total > 0 else None,
        "by_delay": by_delay_summary,
        "sample_size": total,
    }
