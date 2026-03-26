"""Core Learning Loop Monitor — auto-detect and fix breakdowns in the session flow.

Monitors whether the core learning loop (session start -> drills -> complete)
actually works. When metrics breach thresholds, executes fixes immediately
rather than generating dashboards.

Metrics tracked:
- Session completion rate (start-to-complete)
- Average session duration
- Drill error rate
- TTS failure rate
- LLM grading timeout rate
- Conversation abandonment rate

Breakpoint detection:
- Per-content-item session abandonments -> auto-quarantine
- Per-drill-type failure rates -> auto-propose A/B test

Exports:
    run_check(conn) -> dict
    ANALYZERS: list of analyzer functions for the intelligence engine
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, UTC

from ._base import _safe_query, _safe_query_all, _safe_scalar, _finding, _f
from .calibration import get_threshold

logger = logging.getLogger(__name__)

# ── Thresholds (defaults — overridden by calibration when data exists) ───

_SESSION_COMPLETION_RATE_MIN = 0.70      # 70%
_AVG_SESSION_DURATION_MAX_SEC = 1200     # 20 minutes
_DRILL_ERROR_RATE_MAX = 0.30             # 30%
_TTS_FAILURE_RATE_MAX = 0.05             # 5%
_LLM_TIMEOUT_RATE_MAX = 0.10            # 10%
_CONVERSATION_ABANDONMENT_MAX = 0.50     # 50%

# Breakpoint thresholds
_ITEM_ABANDON_THRESHOLD = 3              # >3 abandonments -> quarantine
_DRILL_TYPE_FAILURE_RATE_MAX = 0.40      # >40% failure -> propose A/B test


def _t(conn, metric: str, default: float) -> float:
    """Look up calibrated threshold, falling back to hardcoded default."""
    return get_threshold(conn, "core_loop_monitor", metric, default)

# Lookback window
_LOOKBACK_HOURS = 24
_LOOKBACK_DAYS = 7


# ── Table creation ────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create monitoring tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS core_loop_action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            metric_name TEXT NOT NULL,
            metric_value REAL,
            threshold REAL,
            action_taken TEXT NOT NULL,
            details TEXT,
            success INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()


def _log_action(conn, metric_name: str, metric_value: float, threshold: float,
                action_taken: str, details: dict = None, success: bool = True) -> None:
    """Log an automated action to the database."""
    try:
        conn.execute("""
            INSERT INTO core_loop_action_log
                (metric_name, metric_value, threshold, action_taken, details, success)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            metric_name, metric_value, threshold, action_taken,
            json.dumps(details) if details else None,
            1 if success else 0,
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Core loop monitor: failed to log action: %s", exc)


def _notify_admin(metric_name: str, metric_value: float, action_taken: str,
                  details: dict = None) -> None:
    """Send admin notification about an automated action."""
    try:
        from ..settings import ADMIN_EMAIL
        if not ADMIN_EMAIL:
            return
        from ..email import send_alert
        detail_str = json.dumps(details, indent=2) if details else "None"
        send_alert(
            to_email=ADMIN_EMAIL,
            subject=f"[Aelu Core Loop] {metric_name} breached — action taken",
            details=(
                f"Metric: {metric_name}\n"
                f"Value: {metric_value:.2f}\n"
                f"Action: {action_taken}\n\n"
                f"Details:\n{detail_str}"
            ),
        )
    except Exception as exc:
        logger.debug("Core loop monitor: admin notification failed: %s", exc)


def _set_feature_flag(conn, flag_name: str, value: int) -> None:
    """Set a feature flag value."""
    try:
        conn.execute("""
            INSERT OR REPLACE INTO feature_flag (name, enabled, updated_at)
            VALUES (?, ?, datetime('now'))
        """, (flag_name, value))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error):
        pass


def _get_feature_flag(conn, flag_name: str, default: int = 0) -> int:
    """Get a feature flag value."""
    return _safe_scalar(conn, """
        SELECT enabled FROM feature_flag WHERE name = ?
    """, (flag_name,), default=default)


# ── Metric queries ────────────────────────────────────────────────────────

def _session_completion_rate(conn, hours: int = _LOOKBACK_HOURS) -> tuple[float, int]:
    """Fraction of sessions that completed (not abandoned/bounced).

    Returns (rate, total_sessions).
    """
    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE started_at >= datetime('now', ? || ' hours')
    """, (f"-{hours}",), default=0)

    if total == 0:
        return 1.0, 0  # No data = healthy

    completed = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE started_at >= datetime('now', ? || ' hours')
          AND session_outcome = 'completed'
    """, (f"-{hours}",), default=0)

    return completed / max(total, 1), total


def _avg_session_duration(conn, hours: int = _LOOKBACK_HOURS) -> tuple[float, int]:
    """Average session duration in seconds.

    Returns (avg_seconds, count).
    """
    row = _safe_query(conn, """
        SELECT AVG(duration_seconds) as avg_dur, COUNT(*) as cnt
        FROM session_log
        WHERE started_at >= datetime('now', ? || ' hours')
          AND duration_seconds IS NOT NULL
          AND duration_seconds > 0
    """, (f"-{hours}",))

    if not row or not row[1]:
        return 0.0, 0
    return (row[0] or 0.0), row[1]


def _drill_error_rate(conn, hours: int = _LOOKBACK_HOURS) -> tuple[float, int]:
    """Fraction of review events that were incorrect.

    Returns (error_rate, total_reviews).
    """
    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE created_at >= datetime('now', ? || ' hours')
    """, (f"-{hours}",), default=0)

    if total == 0:
        return 0.0, 0

    errors = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE created_at >= datetime('now', ? || ' hours')
          AND correct = 0
    """, (f"-{hours}",), default=0)

    return errors / max(total, 1), total


def _tts_failure_rate(conn, hours: int = _LOOKBACK_HOURS) -> tuple[float, int]:
    """Fraction of sessions with TTS-related errors.

    Returns (failure_rate, total_sessions_with_audio).
    """
    # Count sessions that attempted audio
    total = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT session_id) FROM review_event
        WHERE created_at >= datetime('now', ? || ' hours')
          AND modality = 'listening'
    """, (f"-{hours}",), default=0)

    if total == 0:
        return 0.0, 0

    # Count sessions with TTS errors from error_log or client_error_log
    tts_errors = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT session_id) FROM error_log
        WHERE created_at >= datetime('now', ? || ' hours')
          AND (notes LIKE '%tts%' OR notes LIKE '%audio%' OR notes LIKE '%speech%'
               OR error_type = 'other' AND notes LIKE '%edge_tts%')
    """, (f"-{hours}",), default=0)

    # Also check client errors for audio failures
    client_tts = _safe_scalar(conn, """
        SELECT COUNT(*) FROM client_error_log
        WHERE timestamp >= datetime('now', ? || ' hours')
          AND (error_message LIKE '%audio%' OR error_message LIKE '%tts%'
               OR error_message LIKE '%speech%')
    """, (f"-{hours}",), default=0)

    failures = tts_errors + (1 if client_tts > 0 else 0)
    return failures / max(total, 1), total


def _llm_timeout_rate(conn, hours: int = _LOOKBACK_HOURS) -> tuple[float, int]:
    """Fraction of LLM calls that timed out.

    Returns (timeout_rate, total_calls).
    """
    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_generation_log
        WHERE occurred_at >= datetime('now', ? || ' hours')
    """, (f"-{hours}",), default=0)

    if total == 0:
        return 0.0, 0

    timeouts = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_ai_generation_log
        WHERE occurred_at >= datetime('now', ? || ' hours')
          AND success = 0
          AND (error LIKE '%timeout%' OR error LIKE '%timed out%')
    """, (f"-{hours}",), default=0)

    return timeouts / max(total, 1), total


def _conversation_abandonment_rate(conn, hours: int = _LOOKBACK_HOURS) -> tuple[float, int]:
    """Fraction of conversation/dialogue drills abandoned mid-way.

    Returns (abandonment_rate, total_conversations).
    """
    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM review_event
        WHERE created_at >= datetime('now', ? || ' hours')
          AND drill_type = 'dialogue'
    """, (f"-{hours}",), default=0)

    if total == 0:
        return 0.0, 0

    # Abandoned conversations: sessions with dialogue drills that didn't complete
    # (session outcome != completed AND had dialogue drills)
    abandoned = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT re.session_id)
        FROM review_event re
        JOIN session_log sl ON re.session_id = sl.id
        WHERE re.created_at >= datetime('now', ? || ' hours')
          AND re.drill_type = 'dialogue'
          AND sl.session_outcome != 'completed'
    """, (f"-{hours}",), default=0)

    total_sessions = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT re.session_id)
        FROM review_event re
        WHERE re.created_at >= datetime('now', ? || ' hours')
          AND re.drill_type = 'dialogue'
    """, (f"-{hours}",), default=0)

    if total_sessions == 0:
        return 0.0, 0

    return abandoned / max(total_sessions, 1), total_sessions


# ── Breakpoint detection ──────────────────────────────────────────────────

def _find_item_breakpoints(conn, days: int = _LOOKBACK_DAYS) -> list[dict]:
    """Find content items that cause session abandonments.

    Returns items with abandonment count exceeding calibrated threshold.
    """
    threshold = _t(conn, "item_abandon_threshold", _ITEM_ABANDON_THRESHOLD)
    rows = _safe_query_all(conn, """
        SELECT
            re.content_item_id,
            ci.hanzi,
            ci.pinyin,
            ci.hsk_level,
            ci.review_status,
            COUNT(DISTINCT re.session_id) as abandon_count
        FROM review_event re
        JOIN session_log sl ON re.session_id = sl.id
        JOIN content_item ci ON re.content_item_id = ci.id
        WHERE re.created_at >= datetime('now', ? || ' days')
          AND sl.session_outcome IN ('abandoned', 'bounced')
        GROUP BY re.content_item_id
        HAVING abandon_count > ?
        ORDER BY abandon_count DESC
        LIMIT 20
    """, (f"-{days}", threshold))

    return [dict(r) for r in rows] if rows else []


def _find_drill_type_breakpoints(conn, days: int = _LOOKBACK_DAYS) -> list[dict]:
    """Find drill types with high failure rates.

    Returns drill types with failure rate exceeding calibrated threshold.
    """
    threshold = _t(conn, "drill_type_failure_rate_max", _DRILL_TYPE_FAILURE_RATE_MAX)
    rows = _safe_query_all(conn, """
        SELECT
            drill_type,
            COUNT(*) as total,
            SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) as failures,
            CAST(SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as failure_rate
        FROM review_event
        WHERE created_at >= datetime('now', ? || ' days')
          AND drill_type IS NOT NULL
        GROUP BY drill_type
        HAVING total >= 10 AND failure_rate > ?
        ORDER BY failure_rate DESC
    """, (f"-{days}", threshold))

    return [dict(r) for r in rows] if rows else []


# ── Remediation actions ───────────────────────────────────────────────────

def _reduce_session_length(conn) -> dict:
    """Reduce session length via feature flag when completion rate is low."""
    current = _get_feature_flag(conn, "reduced_session_length", default=0)
    if current:
        return {"already_active": True}

    _set_feature_flag(conn, "reduced_session_length", 1)
    return {"flag_set": "reduced_session_length", "enabled": True}


def _reduce_drill_count(conn) -> dict:
    """Reduce drill count per session when sessions run too long."""
    current = _get_feature_flag(conn, "reduced_drill_count", default=0)
    if current:
        return {"already_active": True}

    _set_feature_flag(conn, "reduced_drill_count", 1)
    return {"flag_set": "reduced_drill_count", "enabled": True}


def _quarantine_items(conn, items: list[dict]) -> dict:
    """Set review_status='pending_review' on problematic content items."""
    quarantined = []
    for item in items:
        item_id = item.get("content_item_id")
        if not item_id:
            continue
        # Only quarantine currently approved items
        current_status = _safe_scalar(conn, """
            SELECT review_status FROM content_item WHERE id = ?
        """, (item_id,), default="approved")
        if current_status != "approved":
            continue

        try:
            conn.execute("""
                UPDATE content_item SET review_status = 'pending_review'
                WHERE id = ? AND review_status = 'approved'
            """, (item_id,))
            quarantined.append({
                "content_item_id": item_id,
                "hanzi": item.get("hanzi", "?"),
                "abandon_count": item.get("abandon_count", 0),
            })
        except (sqlite3.OperationalError, sqlite3.Error):
            pass

    if quarantined:
        conn.commit()

    return {"quarantined_count": len(quarantined), "items": quarantined}


def _flag_high_error_items(conn, hours: int = _LOOKBACK_HOURS) -> dict:
    """Find items with >30% error rate and lower their difficulty."""
    rows = _safe_query_all(conn, """
        SELECT
            re.content_item_id,
            ci.hanzi,
            ci.difficulty,
            COUNT(*) as total,
            SUM(CASE WHEN re.correct = 0 THEN 1 ELSE 0 END) as errors,
            CAST(SUM(CASE WHEN re.correct = 0 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as error_rate
        FROM review_event re
        JOIN content_item ci ON re.content_item_id = ci.id
        WHERE re.created_at >= datetime('now', ? || ' hours')
        GROUP BY re.content_item_id
        HAVING total >= 5 AND error_rate > ?
        ORDER BY error_rate DESC
        LIMIT 20
    """, (f"-{hours}", _t(conn, "drill_error_rate_max", _DRILL_ERROR_RATE_MAX)))

    adjusted = []
    for row in (rows or []):
        item_id = row["content_item_id"]
        current_diff = row["difficulty"] or 0.5
        # Lower difficulty by 0.1, floor at 0.1
        new_diff = max(0.1, current_diff - 0.1)
        if new_diff < current_diff:
            try:
                conn.execute("""
                    UPDATE content_item SET difficulty = ?
                    WHERE id = ?
                """, (new_diff, item_id))
                adjusted.append({
                    "content_item_id": item_id,
                    "hanzi": row["hanzi"],
                    "old_difficulty": current_diff,
                    "new_difficulty": new_diff,
                    "error_rate": row["error_rate"],
                })
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

    if adjusted:
        conn.commit()

    return {"adjusted_count": len(adjusted), "items": adjusted}


def _switch_tts_fallback(conn) -> dict:
    """Enable TTS fallback mode when TTS failure rate is high."""
    current = _get_feature_flag(conn, "tts_fallback_mode", default=0)
    if current:
        return {"already_active": True}

    _set_feature_flag(conn, "tts_fallback_mode", 1)
    return {"flag_set": "tts_fallback_mode", "enabled": True}


def _switch_faster_model(conn) -> dict:
    """Switch to faster LLM model when timeout rate is high."""
    current = _get_feature_flag(conn, "llm_use_fast_model", default=0)
    if current:
        return {"already_active": True}

    _set_feature_flag(conn, "llm_use_fast_model", 1)
    return {"flag_set": "llm_use_fast_model", "enabled": True}


def _reduce_conversation_turns(conn) -> dict:
    """Reduce conversation turn count when abandonment is high."""
    current = _get_feature_flag(conn, "reduced_conversation_turns", default=0)
    if current:
        return {"already_active": True}

    _set_feature_flag(conn, "reduced_conversation_turns", 1)
    return {"flag_set": "reduced_conversation_turns", "enabled": True}


def _propose_ab_test(conn, drill_type: str, failure_rate: float) -> dict:
    """Log a proposal for an A/B test on a failing drill type.

    Creates a lifecycle_event so the admin dashboard surfaces it.
    """
    try:
        from ..marketing_hooks import log_lifecycle_event
        log_lifecycle_event(
            "ab_test_proposed",
            conn=conn,
            drill_type=drill_type,
            failure_rate=round(failure_rate, 3),
            reason=f"Drill type '{drill_type}' has {failure_rate:.0%} failure rate",
        )
    except Exception:
        pass

    return {"drill_type": drill_type, "failure_rate": failure_rate, "proposed": True}


# ── Main check ────────────────────────────────────────────────────────────

def run_check(conn: sqlite3.Connection) -> dict:
    """Run all core loop checks and auto-remediate breaches.

    Called by:
    - health_check_scheduler.py (every 15 minutes, lightweight)
    - quality_scheduler.py (nightly, comprehensive)

    Returns a summary dict.
    """
    _ensure_tables(conn)

    actions_taken = []
    issues_found = []
    metrics = {}

    # Governance helpers (non-fatal)
    def _gov_check(action_type, target=None):
        try:
            from .contracts import check_contract
            return check_contract(conn, "core_loop_monitor", action_type, target)
        except Exception:
            return True, "", None

    def _gov_record(action_type, target, description, metrics_before, verification_hours=24, contract_id=None):
        try:
            from .action_ledger import record_action
            record_action(conn, "core_loop_monitor", action_type, target, description,
                          metrics_before, verification_hours=verification_hours, contract_id=contract_id)
        except Exception:
            pass

    # ── 1. Session completion rate ────────────────────────────────────
    comp_rate, comp_total = _session_completion_rate(conn)
    metrics["session_completion_rate"] = comp_rate
    metrics["session_count_24h"] = comp_total

    t_comp = _t(conn, "session_completion_rate_min", _SESSION_COMPLETION_RATE_MIN)
    if comp_total >= 3 and comp_rate < t_comp:
        issue = f"Session completion rate {comp_rate:.0%} < {t_comp:.0%} ({comp_total} sessions)"
        issues_found.append(issue)
        allowed, reason, cid = _gov_check("set_feature_flag", "reduced_session_length")
        if not allowed:
            logger.info("Contract blocked core_loop_monitor/set_feature_flag: %s", reason)
            _gov_record("set_feature_flag", "reduced_session_length", f"BLOCKED: {reason}", None, contract_id=cid)
        else:
            result = _reduce_session_length(conn)
            if not result.get("already_active"):
                action = f"Enabled reduced_session_length flag (completion: {comp_rate:.0%})"
                actions_taken.append(action)
                _log_action(conn, "session_completion_rate", comp_rate,
                            t_comp, action, details=result)
                _notify_admin("session_completion_rate", comp_rate, action, result)
                _gov_record("set_feature_flag", "reduced_session_length", action, metrics, contract_id=cid)

    # ── 2. Average session duration ───────────────────────────────────
    avg_dur, dur_count = _avg_session_duration(conn)
    metrics["avg_session_duration_sec"] = avg_dur
    metrics["session_duration_count"] = dur_count

    t_dur = _t(conn, "avg_session_duration_max_sec", _AVG_SESSION_DURATION_MAX_SEC)
    if dur_count >= 3 and avg_dur > t_dur:
        issue = f"Avg session duration {avg_dur:.0f}s > {t_dur:.0f}s ({dur_count} sessions)"
        issues_found.append(issue)
        allowed, reason, cid = _gov_check("set_feature_flag", "reduced_drill_count")
        if not allowed:
            logger.info("Contract blocked core_loop_monitor/set_feature_flag: %s", reason)
            _gov_record("set_feature_flag", "reduced_drill_count", f"BLOCKED: {reason}", None, contract_id=cid)
        else:
            result = _reduce_drill_count(conn)
            if not result.get("already_active"):
                action = f"Enabled reduced_drill_count flag (avg duration: {avg_dur:.0f}s)"
                actions_taken.append(action)
                _log_action(conn, "avg_session_duration", avg_dur,
                            t_dur, action, details=result)
                _notify_admin("avg_session_duration", avg_dur, action, result)
                _gov_record("set_feature_flag", "reduced_drill_count", action, metrics, contract_id=cid)

    # ── 3. Drill error rate ───────────────────────────────────────────
    err_rate, err_total = _drill_error_rate(conn)
    metrics["drill_error_rate"] = err_rate
    metrics["drill_review_count_24h"] = err_total

    t_err = _t(conn, "drill_error_rate_max", _DRILL_ERROR_RATE_MAX)
    if err_total >= 10 and err_rate > t_err:
        issue = f"Drill error rate {err_rate:.0%} > {t_err:.0%} ({err_total} reviews)"
        issues_found.append(issue)
        allowed, reason, cid = _gov_check("lower_difficulty")
        if not allowed:
            logger.info("Contract blocked core_loop_monitor/lower_difficulty: %s", reason)
            _gov_record("lower_difficulty", None, f"BLOCKED: {reason}", None, contract_id=cid)
        else:
            result = _flag_high_error_items(conn)
            if result["adjusted_count"] > 0:
                action = f"Lowered difficulty on {result['adjusted_count']} items (error rate: {err_rate:.0%})"
                actions_taken.append(action)
                _log_action(conn, "drill_error_rate", err_rate,
                            t_err, action, details=result)
                _notify_admin("drill_error_rate", err_rate, action, result)
                _gov_record("lower_difficulty", None, action, metrics, verification_hours=48, contract_id=cid)

    # ── 4. TTS failure rate ───────────────────────────────────────────
    tts_rate, tts_total = _tts_failure_rate(conn)
    metrics["tts_failure_rate"] = tts_rate
    metrics["tts_session_count_24h"] = tts_total

    t_tts = _t(conn, "tts_failure_rate_max", _TTS_FAILURE_RATE_MAX)
    if tts_total >= 3 and tts_rate > t_tts:
        issue = f"TTS failure rate {tts_rate:.0%} > {t_tts:.0%} ({tts_total} audio sessions)"
        issues_found.append(issue)
        allowed, reason, cid = _gov_check("set_feature_flag", "tts_fallback_mode")
        if not allowed:
            logger.info("Contract blocked core_loop_monitor/set_feature_flag: %s", reason)
            _gov_record("set_feature_flag", "tts_fallback_mode", f"BLOCKED: {reason}", None, contract_id=cid)
        else:
            result = _switch_tts_fallback(conn)
            if not result.get("already_active"):
                action = f"Enabled tts_fallback_mode (failure rate: {tts_rate:.0%})"
                actions_taken.append(action)
                _log_action(conn, "tts_failure_rate", tts_rate,
                            t_tts, action, details=result)
                _notify_admin("tts_failure_rate", tts_rate, action, result)
                _gov_record("set_feature_flag", "tts_fallback_mode", action, metrics, contract_id=cid)

    # ── 5. LLM timeout rate ──────────────────────────────────────────
    llm_rate, llm_total = _llm_timeout_rate(conn)
    metrics["llm_timeout_rate"] = llm_rate
    metrics["llm_call_count_24h"] = llm_total

    t_llm = _t(conn, "llm_timeout_rate_max", _LLM_TIMEOUT_RATE_MAX)
    if llm_total >= 5 and llm_rate > t_llm:
        issue = f"LLM timeout rate {llm_rate:.0%} > {t_llm:.0%} ({llm_total} calls)"
        issues_found.append(issue)
        allowed, reason, cid = _gov_check("set_feature_flag", "llm_use_fast_model")
        if not allowed:
            logger.info("Contract blocked core_loop_monitor/set_feature_flag: %s", reason)
            _gov_record("set_feature_flag", "llm_use_fast_model", f"BLOCKED: {reason}", None, contract_id=cid)
        else:
            result = _switch_faster_model(conn)
            if not result.get("already_active"):
                action = f"Enabled llm_use_fast_model flag (timeout rate: {llm_rate:.0%})"
                actions_taken.append(action)
                _log_action(conn, "llm_timeout_rate", llm_rate,
                            t_llm, action, details=result)
                _notify_admin("llm_timeout_rate", llm_rate, action, result)
                _gov_record("set_feature_flag", "llm_use_fast_model", action, metrics, contract_id=cid)

    # ── 6. Conversation abandonment ──────────────────────────────────
    conv_rate, conv_total = _conversation_abandonment_rate(conn)
    metrics["conversation_abandonment_rate"] = conv_rate
    metrics["conversation_session_count_24h"] = conv_total

    t_conv = _t(conn, "conversation_abandonment_max", _CONVERSATION_ABANDONMENT_MAX)
    if conv_total >= 3 and conv_rate > t_conv:
        issue = f"Conversation abandonment {conv_rate:.0%} > {t_conv:.0%} ({conv_total} sessions)"
        issues_found.append(issue)
        allowed, reason, cid = _gov_check("set_feature_flag", "reduced_conversation_turns")
        if not allowed:
            logger.info("Contract blocked core_loop_monitor/set_feature_flag: %s", reason)
            _gov_record("set_feature_flag", "reduced_conversation_turns", f"BLOCKED: {reason}", None, contract_id=cid)
        else:
            result = _reduce_conversation_turns(conn)
            if not result.get("already_active"):
                action = f"Enabled reduced_conversation_turns (abandonment: {conv_rate:.0%})"
                actions_taken.append(action)
                _log_action(conn, "conversation_abandonment", conv_rate,
                            t_conv, action, details=result)
                _notify_admin("conversation_abandonment", conv_rate, action, result)
                _gov_record("set_feature_flag", "reduced_conversation_turns", action, metrics, contract_id=cid)

    # ── 7. Breakpoint detection: item-level ──────────────────────────
    item_breakpoints = _find_item_breakpoints(conn)
    if item_breakpoints:
        issue = f"{len(item_breakpoints)} content item(s) causing repeated session abandonments"
        issues_found.append(issue)
        allowed, reason, cid = _gov_check("quarantine_content")
        if not allowed:
            logger.info("Contract blocked core_loop_monitor/quarantine_content: %s", reason)
            _gov_record("quarantine_content", None, f"BLOCKED: {reason}", None, contract_id=cid)
        else:
            result = _quarantine_items(conn, item_breakpoints)
            if result["quarantined_count"] > 0:
                action = f"Quarantined {result['quarantined_count']} problematic content items"
                actions_taken.append(action)
                _log_action(conn, "item_breakpoint", len(item_breakpoints),
                            _t(conn, "item_abandon_threshold", _ITEM_ABANDON_THRESHOLD), action, details=result)
                _notify_admin("item_breakpoint", len(item_breakpoints), action, result)
                _gov_record("quarantine_content", None, action, metrics, verification_hours=48, contract_id=cid)

    # ── 8. Breakpoint detection: drill-type-level ────────────────────
    drill_breakpoints = _find_drill_type_breakpoints(conn)
    if drill_breakpoints:
        for bp in drill_breakpoints:
            issue = f"Drill type '{bp['drill_type']}' failure rate {bp['failure_rate']:.0%}"
            issues_found.append(issue)
            result = _propose_ab_test(conn, bp["drill_type"], bp["failure_rate"])
            actions_taken.append(
                f"Proposed A/B test for drill type '{bp['drill_type']}' "
                f"(failure rate: {bp['failure_rate']:.0%})"
            )

    # ── Log summary ──────────────────────────────────────────────────
    if actions_taken:
        logger.info(
            "Core loop monitor: %d issues, %d actions — %s",
            len(issues_found), len(actions_taken),
            "; ".join(actions_taken),
        )
    elif issues_found:
        logger.info(
            "Core loop monitor: %d issues found, no new actions needed — %s",
            len(issues_found), "; ".join(issues_found),
        )
    else:
        logger.debug("Core loop monitor: all metrics healthy")

    return {
        "metrics": metrics,
        "issues_found": issues_found,
        "actions_taken": actions_taken,
        "item_breakpoints": len(item_breakpoints) if item_breakpoints else 0,
        "drill_breakpoints": len(drill_breakpoints) if drill_breakpoints else 0,
    }


# ── Intelligence analyzer ────────────────────────────────────────────────

def analyze_core_loop_health(conn) -> list[dict]:
    """Analyzer function for the intelligence engine.

    Generates findings based on core loop metrics without taking action.
    Actions are taken by run_check() in the scheduler loop.
    """
    findings = []

    # Session completion rate
    comp_rate, comp_total = _session_completion_rate(conn, hours=168)  # 7 days
    if comp_total >= 5 and comp_rate < _t(conn, "session_completion_rate_min", _SESSION_COMPLETION_RATE_MIN):
        findings.append(_finding(
            "flow", "high",
            f"Session completion rate is {comp_rate:.0%} (7-day)",
            f"Only {comp_rate:.0%} of {comp_total} sessions completed in the "
            f"last 7 days. Sessions are being abandoned or bounced before "
            f"completion, indicating friction in the core learning loop.",
            "Investigate session abandonment points. Check drill difficulty, "
            "session length, and UI friction. Auto-fix: reduced_session_length "
            "flag is set when rate drops below 70%.",
            "Analyze session_log for abandonment patterns. Check which drill "
            "index sessions typically stop at. Review error_log for the "
            "abandoned sessions.",
            "Session flow reliability",
            _f("routes", "scheduler"),
        ))

    # Drill error rate
    err_rate, err_total = _drill_error_rate(conn, hours=168)
    if err_total >= 20 and err_rate > _t(conn, "drill_error_rate_max", _DRILL_ERROR_RATE_MAX):
        findings.append(_finding(
            "drill_quality", "high",
            f"Drill error rate is {err_rate:.0%} (7-day)",
            f"{err_rate:.0%} of {err_total} drill attempts failed in the last "
            f"7 days. Content may be too difficult or drill instructions unclear.",
            "Review high-error content items. Check difficulty calibration. "
            "Auto-fix: items with >30% error rate get difficulty lowered.",
            "Query review_event grouped by content_item_id to find worst items. "
            "Cross-reference with content_item difficulty levels.",
            "Learning effectiveness",
            _f("drills", "scheduler"),
        ))

    # Item breakpoints
    item_breakpoints = _find_item_breakpoints(conn, days=14)
    if item_breakpoints:
        top_items = item_breakpoints[:3]
        item_desc = ", ".join(
            f"{i.get('hanzi', '?')} ({i.get('abandon_count', 0)} abandonments)"
            for i in top_items
        )
        findings.append(_finding(
            "content", "high",
            f"{len(item_breakpoints)} content items causing session breaks",
            f"These items caused repeated session abandonments: {item_desc}. "
            f"Auto-quarantine is active for items with >{_t(conn, 'item_abandon_threshold', _ITEM_ABANDON_THRESHOLD):.0f} "
            f"abandonments.",
            "Review quarantined items. Fix or replace problematic content.",
            "Check content_item table for review_status='pending_review' items "
            "that were auto-quarantined by the core loop monitor.",
            "Content reliability",
            _f("schema"),
        ))

    # Drill type breakpoints
    drill_breakpoints = _find_drill_type_breakpoints(conn, days=14)
    if drill_breakpoints:
        bp_desc = ", ".join(
            f"{bp['drill_type']} ({bp['failure_rate']:.0%})"
            for bp in drill_breakpoints[:3]
        )
        findings.append(_finding(
            "drill_quality", "medium",
            f"{len(drill_breakpoints)} drill types with >40% failure rate",
            f"These drill types have high failure rates: {bp_desc}. "
            f"A/B tests have been proposed to improve their UI.",
            "Review proposed A/B tests in lifecycle_event table. Consider "
            "redesigning drill UIs with high failure rates.",
            "Check lifecycle_event WHERE event_type='ab_test_proposed' for "
            "drill types needing UI improvement.",
            "Drill design effectiveness",
            _f("drills"),
        ))

    return findings


ANALYZERS = [analyze_core_loop_health]
