"""Content reaudit system — post-approval quality monitoring.

Periodically samples approved AI-generated content items and verifies they
are still valid. Also flags items where real users consistently fail
(accuracy < 30% across 10+ attempts), indicating a quality issue the
initial review missed.

Feeds into the content_reaudit_failure_rate counter-metric.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def run_scheduled_reaudit(conn: sqlite3.Connection,
                          sample_size: int = 10) -> dict:
    """Run a scheduled reaudit cycle on approved AI-generated items.

    1. Sample `sample_size` approved AI items not recently reaudited
    2. For each, check learner accuracy (if data exists)
    3. Run adversarial debate (if available)
    4. Log results to content_reaudit_log
    5. Downgrade items that fail to pending_review

    Returns summary dict.
    """
    if not _table_exists(conn, "content_reaudit_log"):
        return {"status": "skipped", "reason": "content_reaudit_log table missing"}

    # Sample approved AI-generated items not reaudited in last 30 days
    try:
        items = conn.execute("""
            SELECT ci.id, ci.hanzi, ci.pinyin, ci.english, ci.hsk_level,
                   ci.drill_type, ci.example_sentence_hanzi
            FROM content_item ci
            WHERE ci.is_ai_generated = 1
              AND ci.review_status = 'approved'
              AND ci.status = 'drill_ready'
              AND ci.id NOT IN (
                  SELECT content_item_id FROM content_reaudit_log
                  WHERE audited_at >= datetime('now', '-30 days')
              )
            ORDER BY RANDOM()
            LIMIT ?
        """, (sample_size,)).fetchall()
    except sqlite3.OperationalError as e:
        logger.debug("Reaudit query failed: %s", e)
        return {"status": "skipped", "reason": str(e)}

    results = {"reaudited": 0, "passed": 0, "failed": 0, "downgraded": 0}

    for item in items:
        result = _reaudit_single_item(conn, item)
        results["reaudited"] += 1
        if result["passed"]:
            results["passed"] += 1
        else:
            results["failed"] += 1
            if result.get("downgraded"):
                results["downgraded"] += 1

    return results


def check_learner_accuracy_flags(conn: sqlite3.Connection,
                                 min_attempts: int = 10,
                                 accuracy_threshold: float = 0.30) -> dict:
    """Flag approved items where real users consistently fail.

    Items with accuracy < threshold across min_attempts+ attempts are
    likely to have quality issues the initial review missed.
    """
    if not _table_exists(conn, "content_reaudit_log"):
        return {"status": "skipped", "reason": "content_reaudit_log table missing"}

    try:
        # Find items with low learner accuracy
        flagged = conn.execute("""
            SELECT ci.id, ci.hanzi, ci.english, ci.hsk_level,
                   COUNT(r.id) as attempts,
                   SUM(CASE WHEN r.correct = 1 THEN 1 ELSE 0 END) as correct_count
            FROM content_item ci
            JOIN review_event r ON r.content_item_id = ci.id
            WHERE ci.is_ai_generated = 1
              AND ci.review_status = 'approved'
              AND ci.status = 'drill_ready'
            GROUP BY ci.id
            HAVING attempts >= ? AND CAST(correct_count AS REAL) / attempts < ?
        """, (min_attempts, accuracy_threshold)).fetchall()
    except sqlite3.OperationalError:
        return {"status": "skipped", "reason": "query_failed"}

    results = {"flagged": 0, "downgraded": 0}

    for item in flagged:
        acc = item["correct_count"] / item["attempts"] if item["attempts"] > 0 else 0
        _log_reaudit(
            conn, item["id"], passed=False,
            audit_type="learner_accuracy",
            issues=f"Learner accuracy {acc:.1%} across {item['attempts']} attempts",
            learner_accuracy=acc,
            attempt_count=item["attempts"],
            action="downgraded_to_review",
        )
        # Downgrade to pending_review
        conn.execute(
            "UPDATE content_item SET review_status = 'pending_review' WHERE id = ?",
            (item["id"],),
        )
        results["flagged"] += 1
        results["downgraded"] += 1

    if results["downgraded"] > 0:
        conn.commit()

    return results


def _reaudit_single_item(conn: sqlite3.Connection, item) -> dict:
    """Reaudit a single content item. Returns {passed, issues, downgraded}."""
    issues = []
    item_id = item["id"]

    # Check 1: Learner accuracy if data exists
    try:
        acc_row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct
            FROM review_event
            WHERE content_item_id = ?
        """, (item_id,)).fetchone()

        total = acc_row["total"] or 0
        correct = acc_row["correct"] or 0
        if total >= 10:
            acc = correct / total
            if acc < 0.30:
                issues.append(f"low_learner_accuracy: {acc:.1%} across {total} attempts")
    except sqlite3.OperationalError:
        pass  # review_event may not exist

    # Check 2: Adversarial debate (if available and HSK 5+)
    hsk_level = item["hsk_level"] or 1
    if hsk_level >= 5:
        try:
            from .adversarial import run_adversarial_debate
            content_data = {
                "hanzi": item["hanzi"], "pinyin": item["pinyin"],
                "english": item["english"], "drill_type": item["drill_type"],
                "hsk_level": hsk_level,
                "example_sentence": item["example_sentence_hanzi"] or "",
            }
            debate = run_adversarial_debate(conn, content_data, "drill", item_id)
            if debate.get("status") == "completed" and not debate.get("passed"):
                issues.append(f"adversarial_debate_failed: score {debate.get('overall_score', 0):.2f}")
        except Exception:
            pass  # Graceful degradation

    passed = len(issues) == 0
    action = None

    if not passed:
        # Downgrade to pending_review
        conn.execute(
            "UPDATE content_item SET review_status = 'pending_review' WHERE id = ?",
            (item_id,),
        )
        action = "downgraded_to_review"

    _log_reaudit(
        conn, item_id, passed=passed,
        audit_type="scheduled",
        issues="; ".join(issues) if issues else None,
        action=action,
    )
    conn.commit()

    return {"passed": passed, "issues": issues, "downgraded": not passed}


def _log_reaudit(conn, content_item_id: int, passed: bool,
                 audit_type: str = "scheduled",
                 issues: Optional[str] = None,
                 learner_accuracy: Optional[float] = None,
                 attempt_count: Optional[int] = None,
                 action: Optional[str] = None,
                 notes: Optional[str] = None) -> None:
    """Log a reaudit result."""
    try:
        conn.execute("""
            INSERT INTO content_reaudit_log
            (content_item_id, audit_type, passed, issues_found,
             learner_accuracy, attempt_count, action_taken, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (content_item_id, audit_type, 1 if passed else 0,
              issues, learner_accuracy, attempt_count, action, notes))
    except sqlite3.OperationalError:
        logger.debug("Failed to log reaudit result", exc_info=True)
