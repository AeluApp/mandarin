"""Session Diagnostics — auto-diagnose WHY sessions fail or are abandoned.

When a session fails or is abandoned, this module:
1. Queries error_log and review_event for the session
2. Classifies the failure: content_too_hard | content_too_easy | tts_failed |
   llm_timeout | ui_error | user_quit
3. Executes targeted fixes for each classification

Uses deterministic rules first (pattern matching on error types).
Falls back to LLM classification only for ambiguous cases.

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

logger = logging.getLogger(__name__)

# ── Failure classifications ───────────────────────────────────────────────

CONTENT_TOO_HARD = "content_too_hard"
CONTENT_TOO_EASY = "content_too_easy"
TTS_FAILED = "tts_failed"
LLM_TIMEOUT = "llm_timeout"
UI_ERROR = "ui_error"
USER_QUIT = "user_quit"
UNKNOWN = "unknown"

# Lookback: only diagnose recent undiagnosed sessions
_LOOKBACK_HOURS = 24
_BATCH_SIZE = 50  # max sessions to diagnose per run


# ── Table creation ────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create diagnostics tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_diagnosis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            session_id INTEGER NOT NULL,
            user_id INTEGER,
            classification TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            evidence TEXT,
            action_taken TEXT,
            action_details TEXT,
            UNIQUE(session_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_diagnosis_session
        ON session_diagnosis(session_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_diagnosis_class
        ON session_diagnosis(classification)
    """)
    conn.commit()


# ── Session evidence collection ───────────────────────────────────────────

def _get_undiagnosed_sessions(conn, hours: int = _LOOKBACK_HOURS) -> list[dict]:
    """Get failed/abandoned sessions that haven't been diagnosed yet."""
    rows = _safe_query_all(conn, """
        SELECT sl.id as session_id, sl.user_id, sl.session_outcome,
               sl.items_planned, sl.items_completed, sl.items_correct,
               sl.duration_seconds, sl.early_exit, sl.session_type,
               sl.started_at
        FROM session_log sl
        WHERE sl.started_at >= datetime('now', ? || ' hours')
          AND sl.session_outcome IN ('abandoned', 'bounced')
          AND sl.id NOT IN (SELECT session_id FROM session_diagnosis)
        ORDER BY sl.started_at DESC
        LIMIT ?
    """, (f"-{hours}", _BATCH_SIZE))

    return [dict(r) for r in rows] if rows else []


def _get_session_errors(conn, session_id: int) -> list[dict]:
    """Get all errors from error_log for a session."""
    rows = _safe_query_all(conn, """
        SELECT error_type, content_item_id, drill_type, notes,
               user_answer, expected_answer
        FROM error_log
        WHERE session_id = ?
    """, (session_id,))
    return [dict(r) for r in rows] if rows else []


def _get_session_reviews(conn, session_id: int) -> list[dict]:
    """Get all review events for a session."""
    rows = _safe_query_all(conn, """
        SELECT content_item_id, modality, drill_type, correct,
               confidence, response_ms, error_type
        FROM review_event
        WHERE session_id = ?
        ORDER BY id
    """, (session_id,))
    return [dict(r) for r in rows] if rows else []


def _get_session_client_errors(conn, session_id: int, user_id: int,
                                started_at: str) -> list[dict]:
    """Get client-side errors that occurred during this session."""
    rows = _safe_query_all(conn, """
        SELECT error_type, error_message, source_file, page_url
        FROM client_error_log
        WHERE user_id = ?
          AND timestamp >= ?
          AND timestamp <= datetime(?, '+1 hour')
        LIMIT 10
    """, (user_id, started_at, started_at))
    return [dict(r) for r in rows] if rows else []


def _get_llm_errors_during_session(conn, started_at: str) -> list[dict]:
    """Get LLM generation errors that occurred during a session."""
    rows = _safe_query_all(conn, """
        SELECT task_type, model_used, error, generation_time_ms
        FROM pi_ai_generation_log
        WHERE occurred_at >= ?
          AND occurred_at <= datetime(?, '+1 hour')
          AND success = 0
        LIMIT 10
    """, (started_at, started_at))
    return [dict(r) for r in rows] if rows else []


# ── Classification engine ─────────────────────────────────────────────────

def _classify_session(conn, session: dict) -> tuple[str, float, dict]:
    """Classify why a session failed using deterministic rules.

    Returns (classification, confidence, evidence).
    Falls back to LLM classification only for ambiguous cases.
    """
    session_id = session["session_id"]
    user_id = session.get("user_id", 1)
    started_at = session.get("started_at", "")

    # Collect all evidence
    errors = _get_session_errors(conn, session_id)
    reviews = _get_session_reviews(conn, session_id)
    client_errors = _get_session_client_errors(conn, session_id, user_id, started_at)
    llm_errors = _get_llm_errors_during_session(conn, started_at)

    evidence = {
        "errors": len(errors),
        "reviews": len(reviews),
        "client_errors": len(client_errors),
        "llm_errors": len(llm_errors),
        "items_planned": session.get("items_planned", 0),
        "items_completed": session.get("items_completed", 0),
        "items_correct": session.get("items_correct", 0),
        "duration_seconds": session.get("duration_seconds"),
        "early_exit": session.get("early_exit"),
    }

    # ── Rule 1: TTS/audio failure ─────────────────────────────────
    tts_errors = [e for e in errors
                  if e.get("notes") and ("tts" in (e["notes"] or "").lower()
                     or "audio" in (e["notes"] or "").lower()
                     or "speech" in (e["notes"] or "").lower())]
    tts_client = [e for e in client_errors
                  if any(kw in (e.get("error_message") or "").lower()
                         for kw in ("audio", "tts", "speech", "media"))]

    if tts_errors or tts_client:
        evidence["tts_errors"] = len(tts_errors)
        evidence["tts_client_errors"] = len(tts_client)
        return TTS_FAILED, 0.9, evidence

    # ── Rule 2: LLM timeout ──────────────────────────────────────
    timeout_errors = [e for e in llm_errors
                      if "timeout" in (e.get("error") or "").lower()
                      or "timed out" in (e.get("error") or "").lower()]

    if len(timeout_errors) >= 2:
        evidence["timeout_errors"] = len(timeout_errors)
        evidence["llm_models"] = list({e.get("model_used", "?") for e in timeout_errors})
        return LLM_TIMEOUT, 0.9, evidence

    # ── Rule 3: UI/client error ───────────────────────────────────
    js_errors = [e for e in client_errors
                 if e.get("error_type") in ("ReferenceError", "TypeError",
                                             "SyntaxError", "RangeError")]
    if len(js_errors) >= 2:
        evidence["js_errors"] = len(js_errors)
        evidence["error_types"] = list({e.get("error_type", "?") for e in js_errors})
        return UI_ERROR, 0.85, evidence

    # ── Rule 4: Content too hard ──────────────────────────────────
    if reviews:
        correct_count = sum(1 for r in reviews if r.get("correct"))
        total_count = len(reviews)
        accuracy = correct_count / max(total_count, 1)

        if total_count >= 3 and accuracy < 0.3:
            evidence["accuracy"] = round(accuracy, 3)
            evidence["correct"] = correct_count
            evidence["total"] = total_count
            # Additional check: were most errors on high-difficulty items?
            error_types = [e.get("error_type", "other") for e in errors]
            evidence["error_types"] = error_types
            return CONTENT_TOO_HARD, 0.85, evidence

    # ── Rule 5: Content too easy (abandoned due to boredom) ──────
    if reviews:
        correct_count = sum(1 for r in reviews if r.get("correct"))
        total_count = len(reviews)
        accuracy = correct_count / max(total_count, 1)

        # High accuracy + fast responses + early exit = boredom
        if (total_count >= 3 and accuracy > 0.9
                and session.get("early_exit")
                and session.get("items_completed", 0) < session.get("items_planned", 0) * 0.5):
            avg_response_ms = sum(
                r.get("response_ms") or 0 for r in reviews if r.get("response_ms")
            )
            response_count = sum(1 for r in reviews if r.get("response_ms"))
            if response_count > 0:
                avg_response_ms //= response_count
            evidence["accuracy"] = round(accuracy, 3)
            evidence["avg_response_ms"] = avg_response_ms
            return CONTENT_TOO_EASY, 0.7, evidence

    # ── Rule 6: User quit (bounced with no/few reviews) ──────────
    if session.get("session_outcome") == "bounced":
        evidence["outcome"] = "bounced"
        return USER_QUIT, 0.9, evidence

    if (session.get("early_exit") and session.get("items_completed", 0) == 0):
        evidence["outcome"] = "early_exit_no_items"
        return USER_QUIT, 0.85, evidence

    # ── Rule 7: Early exit with some progress (generic quit) ─────
    if session.get("early_exit") and not errors and not client_errors:
        evidence["outcome"] = "early_exit_clean"
        return USER_QUIT, 0.6, evidence

    # ── Ambiguous: try LLM classification ────────────────────────
    llm_result = _classify_with_llm(conn, session, errors, reviews,
                                     client_errors, llm_errors)
    if llm_result:
        return llm_result

    return UNKNOWN, 0.3, evidence


def _classify_with_llm(conn, session: dict, errors: list, reviews: list,
                       client_errors: list, llm_errors: list) -> tuple[str, float, dict] | None:
    """Fall back to LLM classification for ambiguous cases.

    Returns (classification, confidence, evidence) or None if LLM unavailable.
    """
    try:
        from ..ai.ollama_client import generate, is_model_capable
        if not is_model_capable("session_diagnosis"):
            return None

        # Build a concise summary for the LLM
        items = session.get("items_completed", 0)
        planned = session.get("items_planned", 0)
        outcome = session.get("session_outcome", "?")

        review_summary = ""
        if reviews:
            correct = sum(1 for r in reviews if r.get("correct"))
            review_summary = f"Reviews: {correct}/{len(reviews)} correct. "
            drill_types = list({r.get("drill_type", "?") for r in reviews})
            review_summary += f"Drill types: {', '.join(drill_types[:5])}. "

        error_summary = ""
        if errors:
            types = [e.get("error_type", "other") for e in errors[:5]]
            error_summary = f"Errors: {', '.join(types)}. "

        client_summary = ""
        if client_errors:
            msgs = [(e.get("error_type") or "?") for e in client_errors[:3]]
            client_summary = f"Client errors: {', '.join(msgs)}. "

        prompt = (
            f"Classify why this learning session failed.\n\n"
            f"Session: {items}/{planned} items completed, outcome={outcome}. "
            f"{review_summary}{error_summary}{client_summary}\n\n"
            f"Classify as exactly one of: content_too_hard, content_too_easy, "
            f"tts_failed, llm_timeout, ui_error, user_quit\n\n"
            f"Reply with ONLY the classification label, nothing else."
        )

        result = generate(
            prompt=prompt,
            system="You are a diagnostic classifier. Reply with exactly one label.",
            temperature=0.1,
            max_tokens=20,
            use_cache=False,
            conn=conn,
            task_type="session_diagnosis",
        )

        if result.success and result.text:
            label = result.text.strip().lower().replace(" ", "_")
            valid_labels = {CONTENT_TOO_HARD, CONTENT_TOO_EASY, TTS_FAILED,
                           LLM_TIMEOUT, UI_ERROR, USER_QUIT}
            if label in valid_labels:
                return label, 0.5, {"classified_by": "llm", "model": result.model_used}

    except Exception:
        pass

    return None


# ── Remediation actions ───────────────────────────────────────────────────

def _fix_content_too_hard(conn, session: dict, evidence: dict) -> dict:
    """Lower difficulty of items that were too hard and adjust learner profile."""
    session_id = session["session_id"]
    user_id = session.get("user_id", 1)
    fixed_items = []

    # Get items from the session that were answered incorrectly
    hard_items = _safe_query_all(conn, """
        SELECT DISTINCT re.content_item_id, ci.hanzi, ci.difficulty
        FROM review_event re
        JOIN content_item ci ON re.content_item_id = ci.id
        WHERE re.session_id = ? AND re.correct = 0
    """, (session_id,))

    for item in (hard_items or []):
        item_id = item["content_item_id"]
        current_diff = item["difficulty"] or 0.5
        new_diff = max(0.1, current_diff - 0.15)
        if new_diff < current_diff:
            try:
                conn.execute("""
                    UPDATE content_item SET difficulty = ?
                    WHERE id = ?
                """, (new_diff, item_id))
                fixed_items.append({
                    "id": item_id,
                    "hanzi": item["hanzi"],
                    "old_difficulty": current_diff,
                    "new_difficulty": new_diff,
                })
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

    # Also lower the user's level estimate slightly
    level_adjusted = False
    for level_key in ("level_reading", "level_listening", "level_speaking", "level_ime"):
        current = _safe_scalar(conn, f"""
            SELECT {level_key} FROM learner_profile WHERE user_id = ?
        """, (user_id,), default=1.0) or 1.0
        new_level = max(1.0, current - 0.1)
        if new_level < current:
            try:
                conn.execute(f"""
                    UPDATE learner_profile SET {level_key} = ?
                    WHERE user_id = ?
                """, (round(new_level, 2), user_id))
                level_adjusted = True
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

    if fixed_items or level_adjusted:
        conn.commit()

    return {
        "items_adjusted": len(fixed_items),
        "level_adjusted": level_adjusted,
        "items": fixed_items[:10],  # Limit detail size
    }


def _fix_content_too_easy(conn, session: dict, evidence: dict) -> dict:
    """Raise difficulty of items and skip mastered items faster."""
    user_id = session.get("user_id", 1)

    # Increase level estimate
    level_adjusted = False
    for level_key in ("level_reading", "level_listening", "level_speaking", "level_ime"):
        current = _safe_scalar(conn, f"""
            SELECT {level_key} FROM learner_profile WHERE user_id = ?
        """, (user_id,), default=1.0) or 1.0
        new_level = min(9.0, current + 0.2)
        if new_level > current:
            try:
                conn.execute(f"""
                    UPDATE learner_profile SET {level_key} = ?
                    WHERE user_id = ?
                """, (round(new_level, 2), user_id))
                level_adjusted = True
            except (sqlite3.OperationalError, sqlite3.Error):
                pass

    if level_adjusted:
        conn.commit()

    return {"level_adjusted": level_adjusted, "user_id": user_id}


def _fix_tts_failed(conn, session: dict, evidence: dict) -> dict:
    """Mark audio_available=0 on failed items, schedule regeneration."""
    session_id = session["session_id"]
    marked = 0

    # Find items from this session that had audio issues
    items = _safe_query_all(conn, """
        SELECT DISTINCT re.content_item_id
        FROM review_event re
        WHERE re.session_id = ? AND re.modality = 'listening'
    """, (session_id,))

    for item in (items or []):
        try:
            conn.execute("""
                UPDATE content_item SET audio_available = 0
                WHERE id = ? AND audio_available = 1
            """, (item["content_item_id"],))
            marked += 1
        except (sqlite3.OperationalError, sqlite3.Error):
            pass

    if marked:
        conn.commit()

    return {"items_marked_no_audio": marked}


def _fix_llm_timeout(conn, session: dict, evidence: dict) -> dict:
    """Log which model/endpoint timed out for model selector feedback."""
    models = evidence.get("llm_models", [])
    timeout_count = evidence.get("timeout_errors", 0)

    # Record in lifecycle event for model selector
    try:
        from ..marketing_hooks import log_lifecycle_event
        log_lifecycle_event(
            "llm_timeout_session",
            conn=conn,
            session_id=session["session_id"],
            models=models,
            timeout_count=timeout_count,
        )
    except Exception:
        pass

    return {"models_reported": models, "timeout_count": timeout_count}


def _fix_ui_error(conn, session: dict, evidence: dict) -> dict:
    """Log UI error details as a finding for the next audit."""
    error_types = evidence.get("error_types", [])
    js_errors = evidence.get("js_errors", 0)

    # Log lifecycle event so the engineering analyzer picks it up
    try:
        from ..marketing_hooks import log_lifecycle_event
        log_lifecycle_event(
            "ui_error_session",
            conn=conn,
            session_id=session["session_id"],
            error_types=error_types,
            js_error_count=js_errors,
        )
    except Exception:
        pass

    return {"error_types": error_types, "js_errors": js_errors, "logged": True}


# Classification -> fix function mapping
_FIX_FUNCTIONS = {
    CONTENT_TOO_HARD: _fix_content_too_hard,
    CONTENT_TOO_EASY: _fix_content_too_easy,
    TTS_FAILED: _fix_tts_failed,
    LLM_TIMEOUT: _fix_llm_timeout,
    UI_ERROR: _fix_ui_error,
    # USER_QUIT and UNKNOWN: no automatic fix
}


# ── Main check ────────────────────────────────────────────────────────────

def run_check(conn: sqlite3.Connection) -> dict:
    """Diagnose recent failed/abandoned sessions and apply fixes.

    Called by:
    - health_check_scheduler.py (every 15 minutes)
    - quality_scheduler.py (nightly)

    Returns a summary dict.
    """
    _ensure_tables(conn)

    sessions = _get_undiagnosed_sessions(conn)
    if not sessions:
        logger.debug("Session diagnostics: no undiagnosed sessions")
        return {
            "diagnosed": 0,
            "actions_taken": [],
            "classifications": {},
        }

    classifications = {}
    actions_taken = []

    for session in sessions:
        session_id = session["session_id"]

        # Classify
        classification, confidence, evidence = _classify_session(conn, session)

        # Count classifications
        classifications[classification] = classifications.get(classification, 0) + 1

        # Apply fix if available
        action_taken = None
        action_details = None

        fix_fn = _FIX_FUNCTIONS.get(classification)
        if fix_fn:
            try:
                fix_result = fix_fn(conn, session, evidence)
                action_taken = f"{classification}: applied fix"
                action_details = json.dumps(fix_result)
                actions_taken.append(
                    f"Session #{session_id}: {classification} — {fix_result}"
                )
            except Exception as exc:
                action_taken = f"{classification}: fix failed — {exc}"
                logger.debug("Session diagnostics: fix failed for session %d: %s",
                             session_id, exc)

        # Record diagnosis
        try:
            conn.execute("""
                INSERT OR IGNORE INTO session_diagnosis
                    (session_id, user_id, classification, confidence,
                     evidence, action_taken, action_details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                session.get("user_id"),
                classification,
                confidence,
                json.dumps(evidence),
                action_taken,
                action_details,
            ))
        except (sqlite3.OperationalError, sqlite3.Error) as exc:
            logger.debug("Session diagnostics: failed to record diagnosis: %s", exc)

    conn.commit()

    # Log summary
    if actions_taken:
        logger.info(
            "Session diagnostics: diagnosed %d sessions — %s — actions: %s",
            len(sessions), classifications,
            "; ".join(actions_taken[:5]),
        )
    else:
        logger.info(
            "Session diagnostics: diagnosed %d sessions — %s",
            len(sessions), classifications,
        )

    # Admin notification for critical patterns
    _check_patterns(conn, classifications)

    return {
        "diagnosed": len(sessions),
        "classifications": classifications,
        "actions_taken": actions_taken,
    }


def _check_patterns(conn, classifications: dict) -> None:
    """Check for concerning patterns in diagnoses and alert admin."""
    total = sum(classifications.values())
    if total < 3:
        return

    # Alert if >50% of failures are the same type (systematic issue)
    for cls, count in classifications.items():
        if cls == USER_QUIT:
            continue  # Normal user behavior
        if count / total > 0.5:
            try:
                from ..settings import ADMIN_EMAIL
                if not ADMIN_EMAIL:
                    return
                from ..email import send_alert
                send_alert(
                    to_email=ADMIN_EMAIL,
                    subject=f"[Aelu Session Diagnostics] Pattern: {cls} ({count}/{total})",
                    details=(
                        f"Over {count / total:.0%} of recent failed sessions ({count}/{total}) "
                        f"were classified as {cls}.\n\n"
                        f"Full classification breakdown: {json.dumps(classifications, indent=2)}\n\n"
                        f"Automatic fixes have been applied where possible."
                    ),
                )
            except Exception:
                pass
            break


# ── Intelligence analyzer ────────────────────────────────────────────────

def analyze_session_diagnostics(conn) -> list[dict]:
    """Analyzer function for the intelligence engine.

    Summarizes session failure patterns from the diagnostics table.
    """
    _ensure_tables(conn)
    findings = []

    # Get diagnosis distribution over the last 7 days
    rows = _safe_query_all(conn, """
        SELECT classification, COUNT(*) as cnt
        FROM session_diagnosis
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY classification
        ORDER BY cnt DESC
    """)

    if not rows:
        return findings

    total = sum(r[1] for r in rows)
    if total < 5:
        return findings  # Not enough data

    classification_map = {r[0]: r[1] for r in rows}

    # Check for dominant failure mode
    for cls, count in classification_map.items():
        if cls in (USER_QUIT, UNKNOWN):
            continue
        pct = count / total
        if pct > 0.3 and count >= 3:
            severity = "critical" if pct > 0.5 else "high"
            findings.append(_finding(
                "flow", severity,
                f"{pct:.0%} of session failures classified as {cls} (7-day)",
                f"{count}/{total} failed sessions were caused by {cls}. "
                f"This is the dominant failure mode and needs investigation. "
                f"Automatic fixes are applied per-session, but the root cause "
                f"should be addressed.",
                _classification_recommendation(cls),
                f"Check session_diagnosis WHERE classification='{cls}' for "
                f"evidence details. Cross-reference with the affected sessions "
                f"in session_log.",
                f"Session failure root cause ({cls})",
                _classification_files(cls),
            ))

    # Check for high overall failure rate
    total_sessions = _safe_scalar(conn, """
        SELECT COUNT(*) FROM session_log
        WHERE started_at >= datetime('now', '-7 days')
    """, default=0)

    if total_sessions >= 10:
        failure_rate = total / total_sessions
        if failure_rate > 0.3:
            findings.append(_finding(
                "flow", "high",
                f"Session failure rate is {failure_rate:.0%} (7-day)",
                f"{total}/{total_sessions} sessions failed or were abandoned. "
                f"Breakdown: {json.dumps(classification_map)}. "
                f"Session diagnostics is auto-fixing individual cases, but "
                f"the overall rate indicates systemic issues.",
                "Review the classification breakdown. Address the most common "
                "failure modes. Check if recent changes caused regressions.",
                "Review session_diagnosis grouped by classification. "
                "Cross-reference with deployment history.",
                "Session reliability",
                _f("routes", "scheduler"),
            ))

    return findings


def _classification_recommendation(cls: str) -> str:
    """Get recommendation text for a classification."""
    recs = {
        CONTENT_TOO_HARD: (
            "Review content difficulty calibration. Check if the scheduler is "
            "selecting items that are too far above learner levels. Auto-fix: "
            "difficulty is lowered on specific items and learner level estimates "
            "are adjusted down."
        ),
        CONTENT_TOO_EASY: (
            "Review content progression. Ensure the scheduler increases difficulty "
            "when users demonstrate mastery. Auto-fix: learner level estimates are "
            "adjusted up to serve harder content."
        ),
        TTS_FAILED: (
            "Investigate TTS infrastructure. Check edge_tts availability and "
            "network connectivity. Auto-fix: affected items are marked "
            "audio_available=0 for regeneration."
        ),
        LLM_TIMEOUT: (
            "Investigate LLM endpoint performance. Check model latency and "
            "consider switching to a faster model. Auto-fix: timeout incidents "
            "are logged for the model selector."
        ),
        UI_ERROR: (
            "Investigate client-side JavaScript errors. Check client_error_log "
            "for stack traces. Auto-fix: errors are logged as lifecycle events "
            "for the engineering audit."
        ),
    }
    return recs.get(cls, "Investigate the failure pattern in session_diagnosis.")


def _classification_files(cls: str) -> list[str]:
    """Get relevant files for a classification."""
    files = {
        CONTENT_TOO_HARD: _f("scheduler", "drills"),
        CONTENT_TOO_EASY: _f("scheduler", "drills"),
        TTS_FAILED: [],
        LLM_TIMEOUT: [],
        UI_ERROR: _f("app_js"),
    }
    return files.get(cls, [])


ANALYZERS = [analyze_session_diagnostics]
