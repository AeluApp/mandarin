"""Shared CSV export logic — used by both CLI and web API."""

from __future__ import annotations

import csv
import io
import sqlite3
from typing import List, Tuple


def _none_to_empty(val):
    """Convert None to empty string for CSV output."""
    return val if val is not None else ""


def export_progress_csv(conn: sqlite3.Connection) -> tuple[list[str], list[list]]:
    """Query progress data and return (header, rows) for CSV export."""
    rows = conn.execute("""
        SELECT ci.id AS item_id, ci.hanzi, ci.pinyin, ci.english,
               ci.hsk_level,
               p.mastery_stage, p.ease_factor, p.interval_days,
               p.streak_correct, p.half_life_days,
               p.next_review_date, p.last_review_date
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id
        WHERE ci.status = 'drill_ready'
        ORDER BY ci.hsk_level, ci.id
    """).fetchall()
    header = [
        "item_id", "hanzi", "pinyin", "english", "hsk_level",
        "mastery_stage", "ease_factor", "interval_days",
        "streak_correct", "half_life_days", "next_review", "last_review",
    ]
    data = [
        [
            r["item_id"], r["hanzi"], r["pinyin"], r["english"],
            r["hsk_level"] or "",
            r["mastery_stage"] or "",
            _none_to_empty(r["ease_factor"]),
            _none_to_empty(r["interval_days"]),
            _none_to_empty(r["streak_correct"]),
            _none_to_empty(r["half_life_days"]),
            r["next_review_date"] or "",
            r["last_review_date"] or "",
        ]
        for r in rows
    ]
    return header, data


def export_sessions_csv(conn: sqlite3.Connection) -> tuple[list[str], list[list]]:
    """Query session history and return (header, rows) for CSV export."""
    rows = conn.execute("""
        SELECT id AS session_id, started_at, session_type,
               items_completed, items_correct,
               CASE WHEN items_completed > 0
                    THEN ROUND(CAST(items_correct AS REAL) / items_completed * 100, 1)
                    ELSE 0 END AS accuracy_pct,
               duration_seconds, early_exit
        FROM session_log
        ORDER BY started_at DESC
    """).fetchall()
    header = [
        "session_id", "started_at", "session_type",
        "items_completed", "items_correct", "accuracy_pct",
        "duration_seconds", "early_exit",
    ]
    data = [
        [
            r["session_id"], r["started_at"], r["session_type"],
            r["items_completed"], r["items_correct"],
            r["accuracy_pct"],
            r["duration_seconds"] or "",
            r["early_exit"],
        ]
        for r in rows
    ]
    return header, data


def export_errors_csv(conn: sqlite3.Connection) -> tuple[list[str], list[list]]:
    """Query error log and return (header, rows) for CSV export."""
    rows = conn.execute("""
        SELECT el.id, el.content_item_id, ci.hanzi,
               el.error_type, el.user_answer, el.expected_answer,
               el.created_at
        FROM error_log el
        JOIN content_item ci ON el.content_item_id = ci.id
        ORDER BY el.created_at DESC
    """).fetchall()
    header = [
        "id", "content_item_id", "hanzi",
        "error_type", "user_answer", "expected_answer", "created_at",
    ]
    data = [
        [
            r["id"], r["content_item_id"], r["hanzi"],
            r["error_type"], r["user_answer"] or "",
            r["expected_answer"] or "", r["created_at"],
        ]
        for r in rows
    ]
    return header, data


def to_csv_string(header: list[str], data: list[list]) -> str:
    """Convert header + data rows to a CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in data:
        writer.writerow(row)
    return buf.getvalue()
