"""Anti-Goodhart Counter-Metrics — a control system, not a dashboard add-on.

For every primary KPI, at least one "shadow metric" watches for the ways
that metric can be faked, hollowed out, or made locally better while
globally worse.

Five layers:
    1. Performance  — the numbers you want to improve (reference only)
    2. Integrity    — whether performance metrics still mean anything
    3. Cost         — what users pay to achieve headline metrics
    4. Behavioral distortion — gaming by users or by the product itself
    5. Real-world outcome   — does the app improve actual Mandarin ability

Operating principle (per KPI):
    1. How could this go up for the wrong reason?
    2. What user harm would that create?
    3. What metric would detect that distortion early?

Product rules enforced here:
    Rule 1 — No learning KPI ships alone. It ships with ≥1 integrity + ≥1 cost metric.
    Rule 2 — No feature is called successful if it improves immediate performance
              while degrading delayed recall, transfer, or trust.
    Rule 3 — User-visible progress claims must be anchored to evidence that
              survives time and context shift.
    Rule 4 — Benchmark sets must include hidden/holdout tasks not directly
              optimized in the main loop.
    Rule 5 — Any growth/monetization experiment must be reviewed for
              educational integrity, not just business lift.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Helper utilities ──────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    try:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        return col in cols
    except Exception:
        return False


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator > 0 else default


def _safe_median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    k = (p / 100) * (n - 1)
    lo = int(k)
    hi = min(lo + 1, n - 1)
    frac = k - lo
    return s[lo] + frac * (s[hi] - s[lo])


# ═══════════════════════════════════════════════════════════════════════
# LAYER 2: INTEGRITY METRICS
# ═══════════════════════════════════════════════════════════════════════

def delayed_recall_accuracy(conn: sqlite3.Connection, delay_days: int = 7,
                            user_id: Optional[int] = None,
                            window_days: int = 90) -> Dict[str, Any]:
    """Accuracy on items reviewed after ≥delay_days since last review.

    Counter-metric for: review accuracy.
    Detects: items that look mastered but fail when spacing is real.
    """
    if not _table_exists(conn, "review_event") or not _table_exists(conn, "progress"):
        return {"accuracy": None, "sample_size": 0, "delay_days": delay_days}

    user_clause = "AND re.user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    rows = conn.execute(f"""
        SELECT re.correct, re.created_at,
               p.last_review_date, p.half_life_days
        FROM review_event re
        JOIN progress p ON re.user_id = p.user_id
            AND re.content_item_id = p.content_item_id
            AND re.modality = p.modality
        WHERE re.created_at >= datetime('now', '-{window_days} days')
          {user_clause}
        ORDER BY re.created_at
    """, params).fetchall()

    correct = 0
    total = 0
    for r in rows:
        if not r["last_review_date"]:
            continue
        try:
            review_dt = datetime.fromisoformat(r["created_at"])
            last_dt = datetime.fromisoformat(r["last_review_date"])
            gap_days = (review_dt - last_dt).total_seconds() / 86400
        except (ValueError, TypeError):
            continue
        if gap_days >= delay_days:
            total += 1
            if r["correct"]:
                correct += 1

    return {
        "accuracy": round(correct / total, 4) if total > 0 else None,
        "sample_size": total,
        "delay_days": delay_days,
    }


def transfer_accuracy(conn: sqlite3.Connection,
                      user_id: Optional[int] = None,
                      window_days: int = 60) -> Dict[str, Any]:
    """Accuracy on items in drill types NOT previously seen for that item.

    Counter-metric for: review accuracy, items mastered.
    Detects: mastery that only works in the trained format.
    """
    if not _table_exists(conn, "review_event") or not _table_exists(conn, "progress"):
        return {"accuracy": None, "sample_size": 0}

    user_clause = "AND re.user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    rows = conn.execute(f"""
        SELECT re.user_id, re.content_item_id, re.modality,
               re.drill_type, re.correct, p.drill_types_seen
        FROM review_event re
        JOIN progress p ON re.user_id = p.user_id
            AND re.content_item_id = p.content_item_id
            AND re.modality = p.modality
        WHERE re.created_at >= datetime('now', '-{window_days} days')
          {user_clause}
    """, params).fetchall()

    correct = 0
    total = 0
    for r in rows:
        seen = set((r["drill_types_seen"] or "").split(","))
        if r["drill_type"] and r["drill_type"] not in seen:
            total += 1
            if r["correct"]:
                correct += 1

    return {
        "accuracy": round(correct / total, 4) if total > 0 else None,
        "sample_size": total,
    }


def production_vs_recognition_gap(conn: sqlite3.Connection,
                                  user_id: Optional[int] = None,
                                  window_days: int = 60) -> Dict[str, Any]:
    """Gap between recognition drill accuracy and production drill accuracy.

    Counter-metric for: review accuracy, items mastered.
    Detects: "knowing" a word only in recognition mode.
    """
    if not _table_exists(conn, "review_event"):
        return {"recognition_accuracy": None, "production_accuracy": None, "gap": None}

    # Production drill types (must match dispatch.py PRODUCTION_DRILL_TYPES)
    production_types = (
        'ime_type', 'pinyin_to_hanzi', 'english_to_pinyin', 'intuition',
        'speaking', 'word_order', 'sentence_build', 'shadowing',
    )
    prod_placeholders = ",".join("?" * len(production_types))

    user_clause = "AND user_id = ?" if user_id else ""
    base_params: list = []
    if user_id:
        base_params.append(user_id)

    # Recognition accuracy
    rec_row = conn.execute(f"""
        SELECT COUNT(*) as total, SUM(CASE WHEN correct=1 THEN 1 ELSE 0 END) as correct
        FROM review_event
        WHERE created_at >= datetime('now', '-{window_days} days')
          AND drill_type NOT IN ({prod_placeholders})
          AND drill_type IS NOT NULL
          {user_clause}
    """, list(production_types) + base_params).fetchone()

    # Production accuracy
    prod_row = conn.execute(f"""
        SELECT COUNT(*) as total, SUM(CASE WHEN correct=1 THEN 1 ELSE 0 END) as correct
        FROM review_event
        WHERE created_at >= datetime('now', '-{window_days} days')
          AND drill_type IN ({prod_placeholders})
          {user_clause}
    """, list(production_types) + base_params).fetchone()

    rec_acc = _safe_ratio(rec_row["correct"] or 0, rec_row["total"] or 0) if rec_row else None
    prod_acc = _safe_ratio(prod_row["correct"] or 0, prod_row["total"] or 0) if prod_row else None

    gap = None
    if rec_acc is not None and prod_acc is not None:
        gap = round(rec_acc - prod_acc, 4)

    return {
        "recognition_accuracy": round(rec_acc, 4) if rec_acc is not None else None,
        "production_accuracy": round(prod_acc, 4) if prod_acc is not None else None,
        "gap": gap,
        "recognition_sample": (rec_row["total"] or 0) if rec_row else 0,
        "production_sample": (prod_row["total"] or 0) if prod_row else 0,
    }


def mastery_reversal_rate(conn: sqlite3.Connection,
                          user_id: Optional[int] = None,
                          window_days: int = 90) -> Dict[str, Any]:
    """Percentage of items promoted to stable/durable that later got demoted.

    Counter-metric for: items mastered.
    Detects: inflated mastery labels.
    """
    if not _table_exists(conn, "progress"):
        return {"reversal_rate": None, "reversals": 0, "mastered_ever": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    # Items that reached stable/durable
    mastered = conn.execute(f"""
        SELECT COUNT(*) as cnt FROM progress
        WHERE (mastery_stage IN ('stable', 'durable')
               OR stable_since_date IS NOT NULL)
          {user_clause}
    """, params).fetchone()
    mastered_count = (mastered["cnt"] or 0) if mastered else 0

    # Items currently in decayed that had been stable
    reversed_items = conn.execute(f"""
        SELECT COUNT(*) as cnt FROM progress
        WHERE mastery_stage = 'decayed'
          AND stable_since_date IS NOT NULL
          {user_clause}
    """, params).fetchone()
    reversal_count = (reversed_items["cnt"] or 0) if reversed_items else 0

    # Also count items with high weak_cycle_count
    weak_cycles = conn.execute(f"""
        SELECT COUNT(*) as cnt FROM progress
        WHERE weak_cycle_count >= 3
          {user_clause}
    """, params).fetchone()
    chronic_weak = (weak_cycles["cnt"] or 0) if weak_cycles else 0

    return {
        "reversal_rate": round(reversal_count / mastered_count, 4) if mastered_count > 0 else None,
        "reversals": reversal_count,
        "mastered_ever": mastered_count,
        "chronic_weak_items": chronic_weak,
    }


def mastery_survival_curve(conn: sqlite3.Connection,
                           user_id: Optional[int] = None) -> Dict[str, Any]:
    """Survival rate of mastered items at 7, 14, 30, 60 day checkpoints.

    Counter-metric for: items mastered.
    Detects: mastery that doesn't stick.
    """
    if not _table_exists(conn, "progress"):
        return {"checkpoints": {}, "sample_size": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    rows = conn.execute(f"""
        SELECT mastery_stage, stable_since_date, successes_while_stable
        FROM progress
        WHERE stable_since_date IS NOT NULL
          {user_clause}
    """, params).fetchall()

    if not rows:
        return {"checkpoints": {}, "sample_size": 0}

    now = datetime.now(timezone.utc)
    checkpoints = {7: {"eligible": 0, "survived": 0},
                   14: {"eligible": 0, "survived": 0},
                   30: {"eligible": 0, "survived": 0},
                   60: {"eligible": 0, "survived": 0}}

    for r in rows:
        try:
            stable_dt = datetime.fromisoformat(r["stable_since_date"])
            if stable_dt.tzinfo is None:
                stable_dt = stable_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        days_since_stable = (now - stable_dt).total_seconds() / 86400
        stage = r["mastery_stage"]
        survived = stage in ("stable", "durable")

        for day_mark, bucket in checkpoints.items():
            if days_since_stable >= day_mark:
                bucket["eligible"] += 1
                if survived:
                    bucket["survived"] += 1

    result = {}
    for day_mark, bucket in checkpoints.items():
        result[f"{day_mark}d"] = {
            "survival_rate": round(bucket["survived"] / bucket["eligible"], 4) if bucket["eligible"] > 0 else None,
            "eligible": bucket["eligible"],
            "survived": bucket["survived"],
        }

    return {"checkpoints": result, "sample_size": len(rows)}


def hint_dependence_rate(conn: sqlite3.Connection,
                         user_id: Optional[int] = None,
                         window_days: int = 60) -> Dict[str, Any]:
    """Proportion of correct answers that relied on partial confidence.

    Counter-metric for: review accuracy.
    Detects: accuracy inflated by hints/narrowing.
    """
    if not _table_exists(conn, "review_event"):
        return {"dependence_rate": None, "hint_correct": 0, "total_correct": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    row = conn.execute(f"""
        SELECT
            SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as total_correct,
            SUM(CASE WHEN correct = 1 AND confidence IN ('half', 'narrowed') THEN 1 ELSE 0 END) as hint_correct
        FROM review_event
        WHERE created_at >= datetime('now', '-{window_days} days')
          {user_clause}
    """, params).fetchone()

    total_correct = (row["total_correct"] or 0) if row else 0
    hint_correct = (row["hint_correct"] or 0) if row else 0

    return {
        "dependence_rate": round(hint_correct / total_correct, 4) if total_correct > 0 else None,
        "hint_correct": hint_correct,
        "total_correct": total_correct,
    }


# ═══════════════════════════════════════════════════════════════════════
# LAYER 3: COST METRICS
# ═══════════════════════════════════════════════════════════════════════

def session_fatigue_signals(conn: sqlite3.Connection,
                            user_id: Optional[int] = None,
                            window_days: int = 30) -> Dict[str, Any]:
    """Burnout/fatigue signals from session data.

    Counter-metric for: session completion, streaks, engagement.
    Detects: completion driven by guilt/coercion, not growth.
    """
    if not _table_exists(conn, "session_log"):
        return {"early_exit_rate": None, "boredom_rate": None,
                "avg_duration_trend": None, "fatigue_score": None}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    rows = conn.execute(f"""
        SELECT early_exit, boredom_flags, duration_seconds,
               items_planned, items_completed, items_correct,
               started_at
        FROM session_log
        WHERE started_at >= datetime('now', '-{window_days} days')
          AND items_planned > 0
          {user_clause}
        ORDER BY started_at
    """, params).fetchall()

    if not rows:
        return {"early_exit_rate": None, "boredom_rate": None,
                "avg_duration_trend": None, "fatigue_score": 0}

    total = len(rows)
    early_exits = sum(1 for r in rows if r["early_exit"])
    bored = sum(1 for r in rows if (r["boredom_flags"] or 0) > 0)

    # Duration trend: compare first half vs second half
    mid = total // 2
    first_half_dur = [r["duration_seconds"] for r in rows[:mid] if r["duration_seconds"]]
    second_half_dur = [r["duration_seconds"] for r in rows[mid:] if r["duration_seconds"]]
    avg_first = sum(first_half_dur) / len(first_half_dur) if first_half_dur else 0
    avg_second = sum(second_half_dur) / len(second_half_dur) if second_half_dur else 0
    dur_trend = round((avg_second - avg_first) / avg_first, 4) if avg_first > 0 else None

    # Quit-mid-session: items_completed < 50% of items_planned
    quit_mid = sum(1 for r in rows
                   if r["items_completed"] and r["items_planned"]
                   and r["items_completed"] < r["items_planned"] * 0.5)

    # Composite fatigue score (0-100)
    fatigue = 0.0
    fatigue += (early_exits / total) * 30 if total > 0 else 0
    fatigue += (bored / total) * 20 if total > 0 else 0
    fatigue += (quit_mid / total) * 25 if total > 0 else 0
    if dur_trend is not None and dur_trend < -0.2:
        fatigue += min(25, abs(dur_trend) * 50)

    return {
        "early_exit_rate": round(early_exits / total, 4) if total > 0 else None,
        "boredom_rate": round(bored / total, 4) if total > 0 else None,
        "quit_mid_session_rate": round(quit_mid / total, 4) if total > 0 else None,
        "avg_duration_trend": dur_trend,
        "fatigue_score": int(round(min(100, max(0, fatigue)))),
        "session_count": total,
    }


def backlog_burden(conn: sqlite3.Connection,
                   user_id: Optional[int] = None) -> Dict[str, Any]:
    """Review backlog size and growth rate.

    Counter-metric for: items mastered, session completion.
    Detects: progress that creates unsustainable review load.
    """
    if not _table_exists(conn, "progress"):
        return {"overdue_items": 0, "overdue_rate": None, "avg_overdue_days": None}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    overdue = conn.execute(f"""
        SELECT COUNT(*) as cnt,
               AVG(julianday('now') - julianday(next_review_date)) as avg_overdue
        FROM progress
        WHERE next_review_date IS NOT NULL
          AND next_review_date < ?
          AND (suspended_until IS NULL OR suspended_until < ?)
          {user_clause}
    """, [today, today] + params).fetchone()

    total_active = conn.execute(f"""
        SELECT COUNT(*) as cnt FROM progress
        WHERE next_review_date IS NOT NULL
          AND (suspended_until IS NULL OR suspended_until < ?)
          {user_clause}
    """, [today] + params).fetchone()

    overdue_count = (overdue["cnt"] or 0) if overdue else 0
    avg_overdue_days = round(overdue["avg_overdue"] or 0, 1) if overdue else 0
    total_count = (total_active["cnt"] or 0) if total_active else 0

    return {
        "overdue_items": overdue_count,
        "overdue_rate": round(overdue_count / total_count, 4) if total_count > 0 else None,
        "avg_overdue_days": avg_overdue_days,
        "total_active_items": total_count,
    }


def learning_efficiency(conn: sqlite3.Connection,
                        user_id: Optional[int] = None,
                        window_days: int = 30) -> Dict[str, Any]:
    """Learning per minute: mastery promotions per minute of study.

    Counter-metric for: time spent.
    Detects: draggy UX, compulsive use without learning gains.
    """
    if not _table_exists(conn, "session_log"):
        return {"promotions_per_minute": None, "minutes_studied": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    # Total study minutes
    dur_row = conn.execute(f"""
        SELECT SUM(duration_seconds) as total_secs
        FROM session_log
        WHERE started_at >= datetime('now', '-{window_days} days')
          AND duration_seconds > 0
          {user_clause}
    """, params).fetchone()
    total_minutes = ((dur_row["total_secs"] or 0) / 60.0) if dur_row else 0

    # Count mastery promotions (items that moved UP in stage during the window)
    # We approximate via session_metrics if available, or count stable/durable items
    promotions = 0
    if _table_exists(conn, "session_metrics"):
        prom_row = conn.execute(f"""
            SELECT SUM(items_strengthened) as strengthened
            FROM session_metrics sm
            JOIN session_log sl ON sm.session_id = sl.id
            WHERE sl.started_at >= datetime('now', '-{window_days} days')
              {user_clause.replace('user_id', 'sl.user_id')}
        """, params).fetchone()
        promotions = (prom_row["strengthened"] or 0) if prom_row else 0

    return {
        "promotions_per_minute": round(promotions / total_minutes, 4) if total_minutes > 0 else None,
        "promotions": promotions,
        "minutes_studied": round(total_minutes, 1),
    }


def post_break_recovery(conn: sqlite3.Connection,
                        user_id: Optional[int] = None,
                        min_break_days: int = 3,
                        window_days: int = 90) -> Dict[str, Any]:
    """Accuracy in first session after a break of N+ days.

    Counter-metric for: streaks.
    Detects: streak breaks that destroy progress (fragile learning).
    """
    if not _table_exists(conn, "session_log"):
        return {"post_break_accuracy": None, "break_count": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    rows = conn.execute(f"""
        SELECT started_at, items_correct, items_completed
        FROM session_log
        WHERE started_at >= datetime('now', '-{window_days} days')
          AND items_completed > 0
          {user_clause}
        ORDER BY started_at
    """, params).fetchall()

    if len(rows) < 2:
        return {"post_break_accuracy": None, "break_count": 0}

    post_break_accuracies = []
    for i in range(1, len(rows)):
        try:
            curr = datetime.fromisoformat(rows[i]["started_at"])
            prev = datetime.fromisoformat(rows[i - 1]["started_at"])
            gap = (curr - prev).total_seconds() / 86400
        except (ValueError, TypeError):
            continue

        if gap >= min_break_days:
            completed = rows[i]["items_completed"] or 0
            correct = rows[i]["items_correct"] or 0
            if completed > 0:
                post_break_accuracies.append(correct / completed)

    return {
        "post_break_accuracy": round(sum(post_break_accuracies) / len(post_break_accuracies), 4)
            if post_break_accuracies else None,
        "break_count": len(post_break_accuracies),
        "min_break_days": min_break_days,
    }


# ═══════════════════════════════════════════════════════════════════════
# LAYER 4: BEHAVIORAL DISTORTION METRICS
# ═══════════════════════════════════════════════════════════════════════

def answer_latency_suspiciousness(conn: sqlite3.Connection,
                                  user_id: Optional[int] = None,
                                  window_days: int = 30) -> Dict[str, Any]:
    """Detect suspiciously fast answers suggesting click-through gaming.

    Counter-metric for: review accuracy.
    Detects: fast self-ratings, reflexive tapping without thought.
    """
    if not _table_exists(conn, "review_event"):
        return {"suspicious_fast_rate": None, "suspicious_count": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    rows = conn.execute(f"""
        SELECT response_ms, correct, drill_type
        FROM review_event
        WHERE created_at >= datetime('now', '-{window_days} days')
          AND response_ms IS NOT NULL AND response_ms > 0
          {user_clause}
    """, params).fetchall()

    if not rows:
        return {"suspicious_fast_rate": None, "suspicious_count": 0,
                "total_reviews": 0, "median_response_ms": None}

    # Sub-500ms correct answers are suspicious (except simple tone ID)
    fast_threshold = 500
    suspicious = sum(1 for r in rows
                     if r["correct"] and r["response_ms"] < fast_threshold
                     and r["drill_type"] not in ('tone',))
    response_times = [r["response_ms"] for r in rows]

    return {
        "suspicious_fast_rate": round(suspicious / len(rows), 4),
        "suspicious_count": suspicious,
        "total_reviews": len(rows),
        "median_response_ms": round(_safe_median(response_times)),
        "p25_response_ms": round(_percentile(response_times, 25)),
    }


def easy_overuse_collapse(conn: sqlite3.Connection,
                          user_id: Optional[int] = None,
                          window_days: int = 60) -> Dict[str, Any]:
    """Items rated 'easy' repeatedly that later collapsed in accuracy.

    Counter-metric for: review accuracy, items mastered.
    Detects: users gaming by choosing easy then failing later.
    """
    if not _table_exists(conn, "progress"):
        return {"collapse_rate": None, "collapsed_count": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    # Items with high ease_factor (was repeatedly easy) but now struggling
    rows = conn.execute(f"""
        SELECT ease_factor, streak_incorrect, mastery_stage, total_attempts
        FROM progress
        WHERE total_attempts >= 5
          {user_clause}
    """, params).fetchall()

    if not rows:
        return {"collapse_rate": None, "collapsed_count": 0, "total_items": 0}

    # High ease (>2.7) but currently struggling (streak_incorrect >= 2 or decayed)
    high_ease_items = [r for r in rows if (r["ease_factor"] or 2.5) > 2.7]
    collapsed = [r for r in high_ease_items
                 if (r["streak_incorrect"] or 0) >= 2
                 or r["mastery_stage"] == "decayed"]

    return {
        "collapse_rate": round(len(collapsed) / len(high_ease_items), 4)
            if high_ease_items else None,
        "collapsed_count": len(collapsed),
        "high_ease_count": len(high_ease_items),
        "total_items": len(rows),
    }


def recognition_only_progress(conn: sqlite3.Connection,
                              user_id: Optional[int] = None) -> Dict[str, Any]:
    """Items advancing in mastery without any production drills.

    Counter-metric for: items mastered.
    Detects: mastery earned through recognition-only pathways.
    """
    if not _table_exists(conn, "progress"):
        return {"recognition_only_rate": None, "recognition_only_count": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    production_types = {
        'ime_type', 'pinyin_to_hanzi', 'english_to_pinyin', 'intuition',
        'speaking', 'word_order', 'sentence_build', 'shadowing',
    }

    rows = conn.execute(f"""
        SELECT mastery_stage, drill_types_seen
        FROM progress
        WHERE mastery_stage IN ('stabilizing', 'stable', 'durable')
          {user_clause}
    """, params).fetchall()

    if not rows:
        return {"recognition_only_rate": None, "recognition_only_count": 0,
                "advanced_count": 0}

    recognition_only = 0
    for r in rows:
        seen = set((r["drill_types_seen"] or "").split(","))
        if not seen.intersection(production_types):
            recognition_only += 1

    return {
        "recognition_only_rate": round(recognition_only / len(rows), 4),
        "recognition_only_count": recognition_only,
        "advanced_count": len(rows),
    }


def difficulty_avoidance(conn: sqlite3.Connection,
                         user_id: Optional[int] = None,
                         window_days: int = 30) -> Dict[str, Any]:
    """Percentage of progress earned from low-challenge items.

    Counter-metric for: items mastered, session completion.
    Detects: system (or user) quietly improving numbers by serving easy content.
    """
    if not _table_exists(conn, "review_event") or not _table_exists(conn, "content_item"):
        return {"low_challenge_rate": None}

    user_clause = "AND re.user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    row = conn.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN ci.difficulty < 0.3 AND re.correct = 1 THEN 1 ELSE 0 END) as easy_correct,
            SUM(CASE WHEN ci.difficulty >= 0.5 AND re.correct = 1 THEN 1 ELSE 0 END) as hard_correct,
            SUM(CASE WHEN re.correct = 1 THEN 1 ELSE 0 END) as total_correct
        FROM review_event re
        JOIN content_item ci ON re.content_item_id = ci.id
        WHERE re.created_at >= datetime('now', '-{window_days} days')
          {user_clause}
    """, params).fetchone()

    if not row or not row["total_correct"]:
        return {"low_challenge_rate": None, "easy_correct_pct": None,
                "hard_correct_pct": None}

    total_correct = row["total_correct"] or 0
    easy_correct = row["easy_correct"] or 0
    hard_correct = row["hard_correct"] or 0

    return {
        "low_challenge_rate": round(easy_correct / total_correct, 4) if total_correct > 0 else None,
        "easy_correct_pct": round(easy_correct / total_correct * 100, 1) if total_correct > 0 else None,
        "hard_correct_pct": round(hard_correct / total_correct * 100, 1) if total_correct > 0 else None,
        "total_reviews": row["total"] or 0,
    }


def repeated_exposure_dependence(conn: sqlite3.Connection,
                                 user_id: Optional[int] = None,
                                 window_days: int = 60) -> Dict[str, Any]:
    """Items that succeed only through very high repetition.

    Counter-metric for: review accuracy, items mastered.
    Detects: improvement concentrated only on repeated items.
    """
    if not _table_exists(conn, "progress"):
        return {"high_rep_rate": None}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    rows = conn.execute(f"""
        SELECT total_attempts, total_correct, mastery_stage
        FROM progress
        WHERE mastery_stage IN ('stabilizing', 'stable', 'durable')
          AND total_attempts >= 3
          {user_clause}
    """, params).fetchall()

    if not rows:
        return {"high_rep_rate": None, "high_rep_count": 0, "advanced_count": 0}

    # Items needing 3x+ the median attempts to reach mastery
    attempts = [r["total_attempts"] for r in rows]
    median_attempts = _safe_median(attempts)
    threshold = max(median_attempts * 3, 20)

    high_rep = sum(1 for r in rows if r["total_attempts"] >= threshold)

    return {
        "high_rep_rate": round(high_rep / len(rows), 4),
        "high_rep_count": high_rep,
        "advanced_count": len(rows),
        "median_attempts_to_mastery": round(median_attempts, 1),
        "threshold": round(threshold, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# LAYER 5: REAL-WORLD OUTCOME METRICS
# ═══════════════════════════════════════════════════════════════════════

def holdout_probe_performance(conn: sqlite3.Connection,
                              user_id: Optional[int] = None,
                              window_days: int = 90) -> Dict[str, Any]:
    """Performance on holdout probes — hidden benchmark items outside
    the main optimization loop.

    Counter-metric for: ALL performance metrics.
    Detects: overfitting the product to visible metrics.
    """
    if not _table_exists(conn, "counter_metric_holdout"):
        return {"holdout_accuracy": None, "sample_size": 0}

    user_clause = "AND user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    row = conn.execute(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct
        FROM counter_metric_holdout
        WHERE administered_at >= datetime('now', '-{window_days} days')
          {user_clause}
    """, params).fetchone()

    total = (row["total"] or 0) if row else 0
    correct = (row["correct"] or 0) if row else 0

    return {
        "holdout_accuracy": round(correct / total, 4) if total > 0 else None,
        "sample_size": total,
    }


def progress_honesty_score(conn: sqlite3.Connection,
                           user_id: Optional[int] = None) -> Dict[str, Any]:
    """Correlation between user-visible mastery claims and holdout performance.

    Counter-metric for: product honesty.
    Detects: the product becoming dishonest about user progress.
    """
    if not _table_exists(conn, "counter_metric_holdout") or not _table_exists(conn, "progress"):
        return {"honesty_score": None, "mastered_holdout_accuracy": None,
                "unmastered_holdout_accuracy": None}

    user_clause = "AND h.user_id = ?" if user_id else ""
    params: list = []
    if user_id:
        params.append(user_id)

    # Holdout accuracy for items the user has "mastered" in the main loop
    mastered_row = conn.execute(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN h.correct = 1 THEN 1 ELSE 0 END) as correct
        FROM counter_metric_holdout h
        JOIN progress p ON h.user_id = p.user_id AND h.content_item_id = p.content_item_id
        WHERE p.mastery_stage IN ('stable', 'durable')
          {user_clause}
    """, params).fetchone()

    # Holdout accuracy for items NOT yet mastered
    unmastered_row = conn.execute(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN h.correct = 1 THEN 1 ELSE 0 END) as correct
        FROM counter_metric_holdout h
        JOIN progress p ON h.user_id = p.user_id AND h.content_item_id = p.content_item_id
        WHERE p.mastery_stage NOT IN ('stable', 'durable')
          {user_clause}
    """, params).fetchone()

    m_total = (mastered_row["total"] or 0) if mastered_row else 0
    m_correct = (mastered_row["correct"] or 0) if mastered_row else 0
    u_total = (unmastered_row["total"] or 0) if unmastered_row else 0
    u_correct = (unmastered_row["correct"] or 0) if unmastered_row else 0

    m_acc = m_correct / m_total if m_total > 0 else None
    u_acc = u_correct / u_total if u_total > 0 else None

    # Honesty score: mastered items should perform MUCH better on holdouts
    # If they don't, mastery labels are lying
    honesty = None
    if m_acc is not None and u_acc is not None and m_total >= 5:
        gap = m_acc - u_acc
        # We expect a gap of at least 0.3 (30pp). Honesty = gap / 0.3 * 100, capped
        honesty = round(min(100, max(0, (gap / 0.3) * 100)))

    return {
        "honesty_score": honesty,
        "mastered_holdout_accuracy": round(m_acc, 4) if m_acc is not None else None,
        "unmastered_holdout_accuracy": round(u_acc, 4) if u_acc is not None else None,
        "mastered_holdout_sample": m_total,
        "unmastered_holdout_sample": u_total,
    }


# ═══════════════════════════════════════════════════════════════════════
# LAYER 6: CONTENT QUALITY METRICS
# ═══════════════════════════════════════════════════════════════════════

def content_duplicate_rate(conn: sqlite3.Connection,
                           window_days: int = 30) -> Dict[str, Any]:
    """Rate of generated items caught as duplicates.

    Counter-metric for: corpus expansion.
    Detects: generation prompts wasting compute on items the corpus already has.
    """
    if not _table_exists(conn, "pi_ai_review_queue"):
        return {"duplicate_rate": None, "total_generated": 0, "duplicates_caught": 0}

    total = _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE queued_at >= datetime('now', '-{window_days} days')
    """, default=0) or 0

    dupes = _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE queued_at >= datetime('now', '-{window_days} days')
          AND validation_issues LIKE '%duplicate%'
    """, default=0) or 0

    return {
        "duplicate_rate": round(dupes / total, 4) if total > 0 else None,
        "total_generated": total,
        "duplicates_caught": dupes,
    }


def content_rejection_rate(conn: sqlite3.Connection,
                           window_days: int = 30) -> Dict[str, Any]:
    """Rate of reviewed items rejected by human reviewer.

    Counter-metric for: generation quality.
    Detects: LLM prompts producing low-quality output that fails human review.
    """
    if not _table_exists(conn, "pi_ai_review_queue"):
        return {"rejection_rate": None, "reviewed": 0, "rejected": 0}

    reviewed = _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE reviewed_at IS NOT NULL
          AND reviewed_at >= datetime('now', '-{window_days} days')
    """, default=0) or 0

    rejected = _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE review_decision = 'rejected'
          AND reviewed_at >= datetime('now', '-{window_days} days')
    """, default=0) or 0

    return {
        "rejection_rate": round(rejected / reviewed, 4) if reviewed > 0 else None,
        "reviewed": reviewed,
        "rejected": rejected,
    }


def content_review_queue_depth(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Number of items awaiting human review.

    Counter-metric for: governance throughput.
    Detects: generation outpacing review capacity — content governance bottleneck.
    """
    if not _table_exists(conn, "pi_ai_review_queue"):
        return {"queue_depth": 0}

    depth = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE reviewed_at IS NULL
    """, default=0) or 0

    return {"queue_depth": depth}


def content_approval_latency(conn: sqlite3.Connection,
                             window_days: int = 60) -> Dict[str, Any]:
    """Median days from generation to review decision.

    Counter-metric for: governance responsiveness.
    Detects: review backlog growing stale.
    """
    if not _table_exists(conn, "pi_ai_review_queue"):
        return {"median_latency_days": None, "sample_size": 0}

    # pi_ai_review_queue uses `queued_at` for creation timestamp
    rows = conn.execute(f"""
        SELECT julianday(reviewed_at) - julianday(queued_at) as latency_days
        FROM pi_ai_review_queue
        WHERE reviewed_at IS NOT NULL
          AND reviewed_at >= datetime('now', '-{window_days} days')
    """).fetchall()

    if not rows:
        return {"median_latency_days": None, "sample_size": 0}

    latencies = [r["latency_days"] for r in rows if r["latency_days"] is not None]
    return {
        "median_latency_days": round(_safe_median(latencies), 1) if latencies else None,
        "sample_size": len(latencies),
    }


def content_reaudit_failure_rate(conn: sqlite3.Connection,
                                 window_days: int = 90) -> Dict[str, Any]:
    """Rate of previously approved items that fail reaudit.

    Counter-metric for: initial approval quality.
    Detects: rubber-stamping in the review process.
    """
    if not _table_exists(conn, "content_reaudit_log"):
        return {"failure_rate": None, "reaudited": 0, "failed": 0}

    reaudited = _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM content_reaudit_log
        WHERE audited_at >= datetime('now', '-{window_days} days')
    """, default=0) or 0

    failed = _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM content_reaudit_log
        WHERE audited_at >= datetime('now', '-{window_days} days')
          AND passed = 0
    """, default=0) or 0

    return {
        "failure_rate": round(failed / reaudited, 4) if reaudited > 0 else None,
        "reaudited": reaudited,
        "failed": failed,
    }


def approval_rubber_stamping(conn: sqlite3.Connection,
                             window_days: int = 60) -> Dict[str, Any]:
    """Rate of reviews completed in under 5 seconds.

    Counter-metric for: review quality.
    Detects: reviewer not actually reading content before approving.
    """
    if not _table_exists(conn, "pi_ai_review_queue"):
        return {"rubber_stamp_rate": None, "total_reviews": 0}

    total = _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE reviewed_at IS NOT NULL
          AND reviewed_at >= datetime('now', '-{window_days} days')
    """, default=0) or 0

    # Reviews where reviewed_at - queued_at < 5 seconds
    fast = _safe_scalar(conn, f"""
        SELECT COUNT(*) FROM pi_ai_review_queue
        WHERE reviewed_at IS NOT NULL
          AND reviewed_at >= datetime('now', '-{window_days} days')
          AND (julianday(reviewed_at) - julianday(queued_at)) * 86400 < 5
    """, default=0) or 0

    return {
        "rubber_stamp_rate": round(fast / total, 4) if total > 0 else None,
        "total_reviews": total,
        "fast_reviews": fast,
    }


def _safe_scalar(conn, sql, params=(), default=None):
    """Execute a query returning a single scalar value."""
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else default
    except (sqlite3.OperationalError, sqlite3.Error):
        return default


# ═══════════════════════════════════════════════════════════════════════
# COUNTER-METRIC MAPPING TABLE
# ═══════════════════════════════════════════════════════════════════════

COUNTER_METRIC_MAP = {
    "review_accuracy": {
        "likely_failure": "Easier items, stronger hints, memorized patterns",
        "integrity": ["delayed_recall", "transfer_accuracy", "hint_dependence",
                       "production_vs_recognition_gap"],
        "distortion": ["answer_latency_suspiciousness", "easy_overuse_collapse"],
        "cost": ["session_fatigue"],
    },
    "streak_length": {
        "likely_failure": "Guilt-driven opens, shallow activity",
        "integrity": ["delayed_recall"],
        "distortion": [],
        "cost": ["session_fatigue", "post_break_recovery"],
    },
    "items_mastered": {
        "likely_failure": "Inflated mastery labels",
        "integrity": ["mastery_survival_curve", "mastery_reversal_rate",
                       "production_vs_recognition_gap"],
        "distortion": ["recognition_only_progress", "repeated_exposure_dependence",
                        "difficulty_avoidance"],
        "cost": ["backlog_burden"],
    },
    "session_completion": {
        "likely_failure": "Low challenge or over-structured flow",
        "integrity": ["transfer_accuracy", "delayed_recall"],
        "distortion": ["difficulty_avoidance"],
        "cost": ["session_fatigue", "learning_efficiency"],
    },
    "time_spent": {
        "likely_failure": "Draggy UX, compulsive use",
        "integrity": [],
        "distortion": [],
        "cost": ["learning_efficiency", "session_fatigue"],
    },
    "conversion": {
        "likely_failure": "Manipulative nudges, false hope",
        "integrity": ["mastery_survival_curve", "progress_honesty"],
        "distortion": [],
        "cost": [],
    },
    "corpus_expansion": {
        "likely_failure": "Duplicate/low-quality AI content, rubber-stamped reviews",
        "integrity": ["content_rejection_rate", "content_reaudit_failure_rate"],
        "distortion": ["content_duplicate_rate", "approval_rubber_stamping"],
        "cost": ["content_review_queue_depth", "content_approval_latency"],
    },
}


# ═══════════════════════════════════════════════════════════════════════
# ALERT THRESHOLDS — when a counter-metric value triggers concern
# ═══════════════════════════════════════════════════════════════════════

ALERT_THRESHOLDS = {
    # Integrity
    "delayed_recall_7d": {"warn": 0.65, "critical": 0.50, "direction": "below"},
    "delayed_recall_30d": {"warn": 0.50, "critical": 0.35, "direction": "below"},
    "transfer_accuracy": {"warn": 0.55, "critical": 0.40, "direction": "below"},
    "production_accuracy": {"warn": 0.50, "critical": 0.35, "direction": "below"},
    "recognition_production_gap": {"warn": 0.20, "critical": 0.35, "direction": "above"},
    "mastery_reversal_rate": {"warn": 0.15, "critical": 0.25, "direction": "above"},
    "mastery_survival_30d": {"warn": 0.70, "critical": 0.50, "direction": "below"},
    "hint_dependence_rate": {"warn": 0.30, "critical": 0.50, "direction": "above"},

    # Cost
    "fatigue_score": {"warn": 40, "critical": 60, "direction": "above"},
    "early_exit_rate": {"warn": 0.15, "critical": 0.25, "direction": "above"},
    "overdue_rate": {"warn": 0.30, "critical": 0.50, "direction": "above"},

    # Distortion
    "suspicious_fast_rate": {"warn": 0.10, "critical": 0.20, "direction": "above"},
    "recognition_only_rate": {"warn": 0.20, "critical": 0.40, "direction": "above"},
    "low_challenge_rate": {"warn": 0.60, "critical": 0.80, "direction": "above"},

    # Outcome
    "holdout_accuracy": {"warn": 0.60, "critical": 0.45, "direction": "below"},
    "progress_honesty_score": {"warn": 50, "critical": 30, "direction": "below"},

    # Content quality
    "content_duplicate_rate": {"warn": 0.30, "critical": 0.50, "direction": "above"},
    "content_rejection_rate": {"warn": 0.20, "critical": 0.35, "direction": "above"},
    "content_review_queue_depth": {"warn": 30, "critical": 50, "direction": "above"},
    "content_approval_latency_days": {"warn": 7, "critical": 14, "direction": "above"},
    "content_reaudit_failure_rate": {"warn": 0.10, "critical": 0.25, "direction": "above"},
    "content_rubber_stamp_rate": {"warn": 0.30, "critical": 0.50, "direction": "above"},
}


def evaluate_threshold(metric_name: str, value) -> Optional[str]:
    """Return 'critical', 'warn', or None for a given metric value."""
    if value is None:
        return None
    thresh = ALERT_THRESHOLDS.get(metric_name)
    if not thresh:
        return None

    if thresh["direction"] == "below":
        if value <= thresh["critical"]:
            return "critical"
        elif value <= thresh["warn"]:
            return "warn"
    else:  # above
        if value >= thresh["critical"]:
            return "critical"
        elif value >= thresh["warn"]:
            return "warn"
    return None


# ═══════════════════════════════════════════════════════════════════════
# FULL ASSESSMENT — run all layers and return structured report
# ═══════════════════════════════════════════════════════════════════════

def compute_full_assessment(conn: sqlite3.Connection,
                            user_id: Optional[int] = None) -> Dict[str, Any]:
    """Run all counter-metric computations and return a layered report.

    Returns:
        {
            "computed_at": ISO timestamp,
            "integrity": {...},
            "cost": {...},
            "distortion": {...},
            "outcome": {...},
            "alerts": [...],
            "overall_health": "healthy" | "warning" | "critical",
            "counter_metric_map": {...},
        }
    """
    now = datetime.now(timezone.utc).isoformat()
    alerts = []

    # ── Layer 2: Integrity ──
    dr_7 = delayed_recall_accuracy(conn, delay_days=7, user_id=user_id)
    dr_14 = delayed_recall_accuracy(conn, delay_days=14, user_id=user_id)
    dr_30 = delayed_recall_accuracy(conn, delay_days=30, user_id=user_id)
    transfer = transfer_accuracy(conn, user_id=user_id)
    prod_rec_gap = production_vs_recognition_gap(conn, user_id=user_id)
    reversal = mastery_reversal_rate(conn, user_id=user_id)
    survival = mastery_survival_curve(conn, user_id=user_id)
    hint_dep = hint_dependence_rate(conn, user_id=user_id)

    integrity = {
        "delayed_recall_7d": dr_7,
        "delayed_recall_14d": dr_14,
        "delayed_recall_30d": dr_30,
        "transfer_accuracy": transfer,
        "production_vs_recognition_gap": prod_rec_gap,
        "mastery_reversal_rate": reversal,
        "mastery_survival_curve": survival,
        "hint_dependence_rate": hint_dep,
    }

    # Check integrity thresholds
    _check_alert(alerts, "delayed_recall_7d", dr_7.get("accuracy"))
    _check_alert(alerts, "delayed_recall_30d", dr_30.get("accuracy"))
    _check_alert(alerts, "transfer_accuracy", transfer.get("accuracy"))
    _check_alert(alerts, "production_accuracy", prod_rec_gap.get("production_accuracy"))
    _check_alert(alerts, "recognition_production_gap", prod_rec_gap.get("gap"))
    _check_alert(alerts, "mastery_reversal_rate", reversal.get("reversal_rate"))
    _check_alert(alerts, "hint_dependence_rate", hint_dep.get("dependence_rate"))

    survival_30d = survival.get("checkpoints", {}).get("30d", {})
    _check_alert(alerts, "mastery_survival_30d", survival_30d.get("survival_rate"))

    # ── Layer 3: Cost ──
    fatigue = session_fatigue_signals(conn, user_id=user_id)
    backlog = backlog_burden(conn, user_id=user_id)
    efficiency = learning_efficiency(conn, user_id=user_id)
    recovery = post_break_recovery(conn, user_id=user_id)

    cost = {
        "session_fatigue": fatigue,
        "backlog_burden": backlog,
        "learning_efficiency": efficiency,
        "post_break_recovery": recovery,
    }

    _check_alert(alerts, "fatigue_score", fatigue.get("fatigue_score"))
    _check_alert(alerts, "early_exit_rate", fatigue.get("early_exit_rate"))
    _check_alert(alerts, "overdue_rate", backlog.get("overdue_rate"))

    # ── Layer 4: Behavioral distortion ──
    latency = answer_latency_suspiciousness(conn, user_id=user_id)
    easy_collapse = easy_overuse_collapse(conn, user_id=user_id)
    rec_only = recognition_only_progress(conn, user_id=user_id)
    diff_avoid = difficulty_avoidance(conn, user_id=user_id)
    rep_dep = repeated_exposure_dependence(conn, user_id=user_id)

    distortion = {
        "answer_latency_suspiciousness": latency,
        "easy_overuse_collapse": easy_collapse,
        "recognition_only_progress": rec_only,
        "difficulty_avoidance": diff_avoid,
        "repeated_exposure_dependence": rep_dep,
    }

    _check_alert(alerts, "suspicious_fast_rate", latency.get("suspicious_fast_rate"))
    _check_alert(alerts, "recognition_only_rate", rec_only.get("recognition_only_rate"))
    _check_alert(alerts, "low_challenge_rate", diff_avoid.get("low_challenge_rate"))

    # ── Layer 5: Real-world outcome ──
    holdout = holdout_probe_performance(conn, user_id=user_id)
    honesty = progress_honesty_score(conn, user_id=user_id)

    outcome = {
        "holdout_probe_performance": holdout,
        "progress_honesty_score": honesty,
    }

    _check_alert(alerts, "holdout_accuracy", holdout.get("holdout_accuracy"))
    _check_alert(alerts, "progress_honesty_score", honesty.get("honesty_score"))

    # ── Layer 6: Content quality ──
    cq_dup = content_duplicate_rate(conn)
    cq_reject = content_rejection_rate(conn)
    cq_queue = content_review_queue_depth(conn)
    cq_latency = content_approval_latency(conn)
    cq_reaudit = content_reaudit_failure_rate(conn)
    cq_rubber = approval_rubber_stamping(conn)

    content_quality = {
        "content_duplicate_rate": cq_dup,
        "content_rejection_rate": cq_reject,
        "content_review_queue_depth": cq_queue,
        "content_approval_latency": cq_latency,
        "content_reaudit_failure_rate": cq_reaudit,
        "approval_rubber_stamping": cq_rubber,
    }

    _check_alert(alerts, "content_duplicate_rate", cq_dup.get("duplicate_rate"))
    _check_alert(alerts, "content_rejection_rate", cq_reject.get("rejection_rate"))
    _check_alert(alerts, "content_review_queue_depth", cq_queue.get("queue_depth"))
    _check_alert(alerts, "content_approval_latency_days", cq_latency.get("median_latency_days"))
    _check_alert(alerts, "content_reaudit_failure_rate", cq_reaudit.get("failure_rate"))
    _check_alert(alerts, "content_rubber_stamp_rate", cq_rubber.get("rubber_stamp_rate"))

    # ── Overall health ──
    critical_count = sum(1 for a in alerts if a["severity"] == "critical")
    warn_count = sum(1 for a in alerts if a["severity"] == "warn")

    if critical_count > 0:
        overall = "critical"
    elif warn_count >= 3:
        overall = "warning"
    elif warn_count > 0:
        overall = "caution"
    else:
        overall = "healthy"

    # ── Trend drift detection ──
    # Analyze snapshot history to detect multi-cycle declining trends.
    # A metric can be within thresholds individually but drifting toward danger.
    trend_alerts = _detect_trend_drift(conn, user_id=user_id)
    for ta in trend_alerts:
        alerts.append(ta)

    # Recalculate after trend alerts
    critical_count = sum(1 for a in alerts if a["severity"] == "critical")
    warn_count = sum(1 for a in alerts if a["severity"] == "warn")

    if critical_count > 0:
        overall = "critical"
    elif warn_count >= 3:
        overall = "warning"
    elif warn_count > 0:
        overall = "caution"
    else:
        overall = "healthy"

    # ── Delayed validation summary ──
    dv_summary = None
    try:
        from .delayed_validation import get_validation_summary
        dv_summary = get_validation_summary(conn, user_id=user_id or 1)
    except (ImportError, Exception):
        pass

    return {
        "computed_at": now,
        "integrity": integrity,
        "cost": cost,
        "distortion": distortion,
        "outcome": outcome,
        "content_quality": content_quality,
        "alerts": alerts,
        "alert_summary": {
            "critical": critical_count,
            "warn": warn_count,
            "total": len(alerts),
        },
        "overall_health": overall,
        "counter_metric_map": COUNTER_METRIC_MAP,
        "delayed_validation": dv_summary,
    }


# ═══════════════════════════════════════════════════════════════════════
# TREND DRIFT DETECTION — multi-cycle declining trend analysis
# ═══════════════════════════════════════════════════════════════════════

# Metrics to track trends for, with the JSON path to extract from snapshots
_TREND_METRICS = {
    "delayed_recall_7d": ("integrity_json", ["delayed_recall_7d", "accuracy"], "below"),
    "transfer_accuracy": ("integrity_json", ["transfer_accuracy", "accuracy"], "below"),
    "mastery_reversal_rate": ("integrity_json", ["mastery_reversal_rate", "reversal_rate"], "above"),
    "fatigue_score": ("cost_json", ["session_fatigue", "fatigue_score"], "above"),
    "overdue_rate": ("cost_json", ["backlog_burden", "overdue_rate"], "above"),
    "holdout_accuracy": ("outcome_json", ["holdout_probe_performance", "holdout_accuracy"], "below"),
}

# Minimum snapshots needed for trend detection
_TREND_MIN_SNAPSHOTS = 3
# Number of consecutive declining cycles to trigger alert
_TREND_CONSECUTIVE_DECLINE = 3


def _extract_nested(data: dict, keys: list):
    """Extract a value from nested dicts using a key path."""
    current = data
    for k in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(k)
    return current


def _detect_trend_drift(conn: sqlite3.Connection,
                        user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Detect multi-cycle declining trends in counter-metric snapshots.

    Returns list of trend-based alerts. A trend alert fires when a metric
    has been getting worse for _TREND_CONSECUTIVE_DECLINE consecutive
    snapshots, even if no single value crosses a threshold.
    """
    if not _table_exists(conn, "counter_metric_snapshot"):
        return []

    uid = user_id or 1
    rows = conn.execute("""
        SELECT integrity_json, cost_json, distortion_json, outcome_json,
               computed_at
        FROM counter_metric_snapshot
        WHERE user_id = ?
        ORDER BY computed_at DESC
        LIMIT ?
    """, (uid, _TREND_CONSECUTIVE_DECLINE + 2)).fetchall()

    if len(rows) < _TREND_MIN_SNAPSHOTS:
        return []

    trend_alerts = []

    for metric_name, (json_col, key_path, direction) in _TREND_METRICS.items():
        values = []
        for row in rows:
            raw = row[json_col]
            if not raw:
                continue
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                continue
            val = _extract_nested(data, key_path)
            if val is not None:
                values.append(val)

        if len(values) < _TREND_MIN_SNAPSHOTS:
            continue

        # Values are in reverse chronological order (newest first)
        # Check for consecutive decline: each value worse than the next older one
        consecutive_worse = 0
        for i in range(len(values) - 1):
            newer, older = values[i], values[i + 1]
            if direction == "below":
                # Lower is worse for "below" metrics
                if newer < older:
                    consecutive_worse += 1
                else:
                    break
            else:
                # Higher is worse for "above" metrics
                if newer > older:
                    consecutive_worse += 1
                else:
                    break

        if consecutive_worse >= _TREND_CONSECUTIVE_DECLINE:
            # Calculate total drift magnitude
            drift = values[0] - values[consecutive_worse]
            trend_alerts.append({
                "metric": f"trend_{metric_name}",
                "value": values[0],
                "severity": "warn",
                "threshold": f"{consecutive_worse} consecutive declining cycles",
                "direction": direction,
                "drift": round(drift, 4),
                "cycles": consecutive_worse,
                "trend_type": "declining",
            })

    return trend_alerts


def _check_alert(alerts: list, metric_name: str, value) -> None:
    """Evaluate a metric and append to alerts if threshold crossed."""
    severity = evaluate_threshold(metric_name, value)
    if severity:
        thresh = ALERT_THRESHOLDS[metric_name]
        alerts.append({
            "metric": metric_name,
            "value": value,
            "severity": severity,
            "threshold": thresh[severity],
            "direction": thresh["direction"],
        })


# ═══════════════════════════════════════════════════════════════════════
# SNAPSHOT STORAGE — persist assessments to DB for trend tracking
# ═══════════════════════════════════════════════════════════════════════

def save_snapshot(conn: sqlite3.Connection, assessment: Dict[str, Any],
                  user_id: int = 1) -> int:
    """Persist a counter-metric assessment snapshot to the database.

    Returns the snapshot ID.
    """
    if not _table_exists(conn, "counter_metric_snapshot"):
        return -1

    now = assessment.get("computed_at", datetime.now(timezone.utc).isoformat())
    overall = assessment.get("overall_health", "unknown")
    alert_count = assessment.get("alert_summary", {}).get("total", 0)
    critical_count = assessment.get("alert_summary", {}).get("critical", 0)

    cursor = conn.execute("""
        INSERT INTO counter_metric_snapshot
        (user_id, computed_at, overall_health, alert_count, critical_count,
         integrity_json, cost_json, distortion_json, outcome_json, alerts_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, now, overall, alert_count, critical_count,
        json.dumps(assessment.get("integrity", {})),
        json.dumps(assessment.get("cost", {})),
        json.dumps(assessment.get("distortion", {})),
        json.dumps(assessment.get("outcome", {})),
        json.dumps(assessment.get("alerts", [])),
    ))
    conn.commit()
    return cursor.lastrowid


def get_snapshot_history(conn: sqlite3.Connection,
                         user_id: int = 1,
                         limit: int = 30) -> List[Dict[str, Any]]:
    """Return recent counter-metric snapshots for trend analysis."""
    if not _table_exists(conn, "counter_metric_snapshot"):
        return []

    rows = conn.execute("""
        SELECT * FROM counter_metric_snapshot
        WHERE user_id = ?
        ORDER BY computed_at DESC
        LIMIT ?
    """, (user_id, limit)).fetchall()

    return [dict(r) for r in rows]
