"""Holdout Probe System — hidden benchmark tasks outside the main SRS loop.

Anti-Goodhart Rule 4: Benchmark sets must include hidden/holdout tasks
not directly optimized in the main loop.

This module:
1. Selects holdout items from the user's studied vocabulary
2. Administers them in novel drill formats or transformed contexts
3. Records results in counter_metric_holdout (NOT in the main progress table)
4. Never feeds results back into SRS scheduling

The holdout set is rotated periodically so items don't become stale.
Holdout probes are injected into sessions at a low rate (1-2 per session)
to avoid disrupting the learning flow.
"""

from __future__ import annotations

import hashlib
import logging
import random
import sqlite3
from datetime import datetime, timedelta, timezone, UTC
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────

HOLDOUT_INJECTION_RATE = 0.1  # 10% of session items are holdout probes
MAX_PROBES_PER_SESSION = 2
MIN_MASTERY_FOR_HOLDOUT = "stabilizing"  # Only probe items at this stage+
HOLDOUT_ROTATION_DAYS = 14  # Rotate holdout set every 2 weeks

# Drill types used for holdout (intentionally different from what user trains)
HOLDOUT_DRILL_TYPES = [
    "reverse_mc",           # English → Hanzi (if trained hanzi → english)
    "english_to_pinyin",    # Production from English
    "listening_detail",     # Comprehension from audio
    "sentence_build",       # Constructive use
]

_MASTERY_ORDER = ["seen", "passed_once", "stabilizing", "stable", "durable"]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def select_holdout_items(conn: sqlite3.Connection,
                         user_id: int = 1,
                         count: int = 20,
                         holdout_set: str = "standard") -> list[dict[str, Any]]:
    """Select items for the holdout benchmark set.

    Criteria:
    - User has studied the item (exists in progress)
    - Mastery stage >= MIN_MASTERY_FOR_HOLDOUT
    - Not suspended
    - Deterministic selection based on user_id + rotation period
      (so the set is stable within a rotation window)

    Returns list of {content_item_id, modality, hanzi, english, difficulty}.
    """
    if not _table_exists(conn, "progress") or not _table_exists(conn, "content_item"):
        return []

    min_idx = _MASTERY_ORDER.index(MIN_MASTERY_FOR_HOLDOUT)
    eligible_stages = _MASTERY_ORDER[min_idx:]
    placeholders = ",".join("?" * len(eligible_stages))

    today = datetime.now(UTC).strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT p.content_item_id, p.modality,
               ci.hanzi, ci.english, ci.pinyin, ci.difficulty
        FROM progress p
        JOIN content_item ci ON p.content_item_id = ci.id
        WHERE p.user_id = ?
          AND p.mastery_stage IN ({})
          AND (p.suspended_until IS NULL OR p.suspended_until < ?)
          AND p.total_attempts >= 3
        ORDER BY p.content_item_id
    """.format(placeholders), [user_id] + eligible_stages + [today]).fetchall()

    if not rows:
        return []

    # Deterministic selection: hash user_id + rotation window
    rotation_window = datetime.now(UTC).strftime("%Y-%W")
    seed_str = f"{user_id}:{holdout_set}:{rotation_window}"
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    items = [dict(r) for r in rows]
    rng.shuffle(items)
    selected = items[:count]

    return selected


def pick_holdout_drill_type(item: dict[str, Any],
                            user_id: int = 1) -> str:
    """Pick a drill type for a holdout probe that's DIFFERENT from
    what the user normally trains on.

    This tests transfer, not recognition.
    """
    # Deterministic but varied per item
    seed_str = f"{user_id}:{item.get('content_item_id', 0)}:holdout"
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
    return HOLDOUT_DRILL_TYPES[seed % len(HOLDOUT_DRILL_TYPES)]


def get_session_probes(conn: sqlite3.Connection,
                       user_id: int = 1,
                       session_item_count: int = 12) -> list[dict[str, Any]]:
    """Get holdout probes to inject into a session.

    Returns a list of probe specs ready for the drill runner:
        [{content_item_id, modality, drill_type, hanzi, english, pinyin,
          is_holdout: True}, ...]
    """
    probe_count = min(
        MAX_PROBES_PER_SESSION,
        max(1, int(session_item_count * HOLDOUT_INJECTION_RATE))
    )

    holdout_items = select_holdout_items(conn, user_id=user_id, count=probe_count * 3)
    if not holdout_items:
        return []

    probes = []
    for item in holdout_items[:probe_count]:
        drill_type = pick_holdout_drill_type(item, user_id=user_id)
        probes.append({
            "content_item_id": item["content_item_id"],
            "modality": item.get("modality", "reading"),
            "drill_type": drill_type,
            "hanzi": item.get("hanzi"),
            "english": item.get("english"),
            "pinyin": item.get("pinyin"),
            "difficulty": item.get("difficulty", 0.5),
            "is_holdout": True,
        })

    return probes


def record_holdout_result(conn: sqlite3.Connection,
                          user_id: int,
                          content_item_id: int,
                          modality: str,
                          drill_type: str,
                          correct: bool,
                          response_ms: int | None = None,
                          session_id: int | None = None,
                          holdout_set: str = "standard") -> int:
    """Record a holdout probe result.

    IMPORTANT: This writes to counter_metric_holdout, NOT to the main
    progress table. Holdout results must never feed back into SRS scheduling.

    Returns the holdout record ID.
    """
    if not _table_exists(conn, "counter_metric_holdout"):
        return -1

    now = datetime.now(UTC).isoformat()
    cursor = conn.execute("""
        INSERT INTO counter_metric_holdout
        (user_id, content_item_id, modality, drill_type, correct,
         response_ms, administered_at, session_id, holdout_set)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, content_item_id, modality, drill_type,
          1 if correct else 0, response_ms, now, session_id, holdout_set))
    conn.commit()
    return cursor.lastrowid


def get_holdout_summary(conn: sqlite3.Connection,
                        user_id: int = 1,
                        window_days: int = 30) -> dict[str, Any]:
    """Summarize holdout performance for a user.

    Returns accuracy overall and by drill type.
    """
    if not _table_exists(conn, "counter_metric_holdout"):
        return {"accuracy": None, "by_drill_type": {}, "sample_size": 0}

    rows = conn.execute("""
        SELECT drill_type, correct
        FROM counter_metric_holdout
        WHERE user_id = ?
          AND administered_at >= datetime('now', ? || ' days')
    """, (user_id, f"-{window_days}")).fetchall()

    if not rows:
        return {"accuracy": None, "by_drill_type": {}, "sample_size": 0}

    total = len(rows)
    correct = sum(1 for r in rows if r["correct"])

    by_type: dict[str, dict[str, int]] = {}
    for r in rows:
        dt = r["drill_type"] or "unknown"
        if dt not in by_type:
            by_type[dt] = {"total": 0, "correct": 0}
        by_type[dt]["total"] += 1
        if r["correct"]:
            by_type[dt]["correct"] += 1

    by_type_acc = {}
    for dt, counts in by_type.items():
        by_type_acc[dt] = {
            "accuracy": round(counts["correct"] / counts["total"], 4)
                if counts["total"] > 0 else None,
            "sample_size": counts["total"],
        }

    return {
        "accuracy": round(correct / total, 4) if total > 0 else None,
        "by_drill_type": by_type_acc,
        "sample_size": total,
    }
