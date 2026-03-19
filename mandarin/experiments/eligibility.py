"""Eligibility engine — rule-based filtering to decide who may enter an experiment.

Eligibility is evaluated BEFORE assignment.  It must NEVER determine which arm
a user gets — only whether they may enter at all.

Rules are declared as JSON in the experiment's ``eligibility_rules`` column and
are frozen at experiment start.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

from .audit import log_audit_event

logger = logging.getLogger(__name__)

# Default rules applied when an experiment declares none.
DEFAULT_ELIGIBILITY: dict = {
    "min_sessions": 1,
    "exclude_admin": True,
    "exclude_dormant_days": None,
    "max_concurrent_experiments": 3,
}


def check_eligibility(
    conn: sqlite3.Connection,
    experiment_id: int,
    user_id: int,
    rules: dict | None = None,
    *,
    log: bool = True,
) -> tuple[bool, list[str]]:
    """Evaluate whether *user_id* is eligible for *experiment_id*.

    Returns ``(eligible, reasons)`` where *reasons* is a list of exclusion
    reason strings (empty when eligible).

    If *rules* is ``None``, the experiment's stored ``eligibility_rules`` are
    loaded.  Pass rules explicitly to avoid the extra query when you already
    have the experiment row.
    """
    if rules is None:
        rules = _load_rules(conn, experiment_id)

    reasons: list[str] = []

    # ── Core checks ──────────────────────────────────────────────────────

    # Active user
    if not _is_active(conn, user_id):
        reasons.append("user_inactive")

    # Admin / internal tester exclusion
    if rules.get("exclude_admin", True) and _is_admin(conn, user_id):
        reasons.append("admin_excluded")

    # ── Rule-based checks ────────────────────────────────────────────────

    # Minimum completed sessions
    min_sessions = rules.get("min_sessions")
    if min_sessions:
        sessions = _count_sessions(conn, user_id)
        if sessions < min_sessions:
            reasons.append(f"insufficient_sessions:{sessions}<{min_sessions}")

    # Minimum tenure (days since first session or signup)
    min_tenure = rules.get("min_tenure_days")
    if min_tenure:
        tenure = _tenure_days(conn, user_id)
        if tenure is not None and tenure < min_tenure:
            reasons.append(f"insufficient_tenure:{tenure:.0f}<{min_tenure}")

    # HSK band filter
    hsk_band = rules.get("hsk_band")
    if hsk_band and len(hsk_band) == 2:
        hsk = _avg_hsk_level(conn, user_id)
        if hsk is not None and (hsk < hsk_band[0] or hsk > hsk_band[1]):
            reasons.append(f"hsk_out_of_range:{hsk:.1f}")

    # Engagement band filter
    engagement_bands = rules.get("engagement_bands")
    if engagement_bands:
        band = _engagement_band(conn, user_id)
        if band not in engagement_bands:
            reasons.append(f"engagement_band_excluded:{band}")

    # Dormant user exclusion
    exclude_dormant = rules.get("exclude_dormant_days")
    if exclude_dormant:
        days_inactive = _days_since_last_session(conn, user_id)
        if days_inactive is not None and days_inactive > exclude_dormant:
            reasons.append(f"dormant:{days_inactive:.0f}d>{exclude_dormant}d")

    # Platform filter
    platforms = rules.get("platforms")
    if platforms:
        user_platform = _last_platform(conn, user_id)
        if user_platform and user_platform not in platforms:
            reasons.append(f"platform_excluded:{user_platform}")

    # Mutual exclusion with specific experiments
    exclude_experiments = rules.get("exclude_experiments")
    if exclude_experiments:
        for other_name in exclude_experiments:
            if _is_assigned_to(conn, user_id, other_name):
                reasons.append(f"mutual_exclusion:{other_name}")

    # Max concurrent experiments
    max_concurrent = rules.get("max_concurrent_experiments")
    if max_concurrent:
        current = _count_active_assignments(conn, user_id)
        if current >= max_concurrent:
            reasons.append(f"max_concurrent:{current}>={max_concurrent}")

    # Data sufficiency for CUPED
    data_suff = rules.get("min_data_sufficiency")
    if data_suff:
        metric = data_suff.get("metric", "sessions")
        min_count = data_suff.get("min_count", 5)
        lookback = data_suff.get("lookback_days", 30)
        count = _metric_count(conn, user_id, metric, lookback)
        if count < min_count:
            reasons.append(f"data_insufficiency:{metric}:{count}<{min_count}")

    # Feature requirement
    require_features = rules.get("require_features")
    if require_features:
        for feat in require_features:
            if not _has_feature(conn, user_id, feat):
                reasons.append(f"missing_feature:{feat}")

    # Holdout exclusion (global holdout users are excluded from all experiments)
    if _is_in_holdout(conn, user_id):
        reasons.append("global_holdout")

    eligible = len(reasons) == 0

    # Audit log
    if log:
        log_audit_event(
            conn,
            "eligibility_check",
            experiment_id=experiment_id,
            user_id=user_id,
            data={"eligible": eligible, "reasons": reasons},
        )

    return eligible, reasons


# ── Internal helpers ─────────────────────────────────────────────────────────


def _load_rules(conn: sqlite3.Connection, experiment_id: int) -> dict:
    try:
        row = conn.execute(
            "SELECT eligibility_rules FROM experiment WHERE id = ?",
            (experiment_id,),
        ).fetchone()
        if row and row["eligibility_rules"]:
            return json.loads(row["eligibility_rules"])
    except (sqlite3.OperationalError, json.JSONDecodeError):
        pass
    return dict(DEFAULT_ELIGIBILITY)


def _is_active(conn: sqlite3.Connection, user_id: int) -> bool:
    try:
        row = conn.execute(
            "SELECT is_active FROM user WHERE id = ?", (user_id,)
        ).fetchone()
        return bool(row and row["is_active"])
    except sqlite3.OperationalError:
        return True  # No user table yet — assume active


def _is_admin(conn: sqlite3.Connection, user_id: int) -> bool:
    try:
        row = conn.execute(
            "SELECT is_admin, subscription_tier FROM user WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            return False
        return bool(row["is_admin"]) or row["subscription_tier"] == "admin"
    except sqlite3.OperationalError:
        return False


def _count_sessions(conn: sqlite3.Connection, user_id: int) -> int:
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM session_log WHERE user_id = ? AND session_outcome = 'completed'",
            (user_id,),
        ).fetchone()
        return row["cnt"] if row else 0
    except sqlite3.OperationalError:
        return 0


def _tenure_days(conn: sqlite3.Connection, user_id: int) -> float | None:
    try:
        row = conn.execute(
            "SELECT created_at FROM user WHERE id = ?", (user_id,)
        ).fetchone()
        if not row or not row["created_at"]:
            return None
        created = datetime.fromisoformat(row["created_at"])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return (now - created).total_seconds() / 86400
    except (sqlite3.OperationalError, ValueError):
        return None


def _avg_hsk_level(conn: sqlite3.Connection, user_id: int) -> float | None:
    try:
        row = conn.execute(
            """SELECT
                 (COALESCE(level_reading, 1) + COALESCE(level_listening, 1) +
                  COALESCE(level_speaking, 1) + COALESCE(level_ime, 1)) / 4.0 as avg_level
               FROM learner_profile WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        return float(row["avg_level"]) if row and row["avg_level"] else None
    except sqlite3.OperationalError:
        return None


def _engagement_band(conn: sqlite3.Connection, user_id: int) -> str:
    """Return 'low', 'medium', or 'high' based on sessions in last 14 days."""
    try:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM session_log
               WHERE user_id = ? AND started_at >= datetime('now', '-14 days')""",
            (user_id,),
        ).fetchone()
        weekly = (row["cnt"] if row else 0) / 2.0
        if weekly < 2:
            return "low"
        elif weekly < 5:
            return "medium"
        return "high"
    except sqlite3.OperationalError:
        return "low"


def _days_since_last_session(conn: sqlite3.Connection, user_id: int) -> float | None:
    try:
        row = conn.execute(
            "SELECT MAX(started_at) as last_at FROM session_log WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row or not row["last_at"]:
            return None
        last = datetime.fromisoformat(row["last_at"])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return (now - last).total_seconds() / 86400
    except (sqlite3.OperationalError, ValueError):
        return None


def _last_platform(conn: sqlite3.Connection, user_id: int) -> str | None:
    try:
        row = conn.execute(
            "SELECT client_platform FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return row["client_platform"] if row else None
    except sqlite3.OperationalError:
        return None


def _is_assigned_to(conn: sqlite3.Connection, user_id: int, experiment_name: str) -> bool:
    try:
        row = conn.execute(
            """SELECT 1 FROM experiment_assignment ea
               JOIN experiment e ON ea.experiment_id = e.id
               WHERE ea.user_id = ? AND e.name = ? AND e.status IN ('running', 'paused')""",
            (user_id, experiment_name),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False


def _count_active_assignments(conn: sqlite3.Connection, user_id: int) -> int:
    try:
        row = conn.execute(
            """SELECT COUNT(DISTINCT ea.experiment_id) as cnt
               FROM experiment_assignment ea
               JOIN experiment e ON ea.experiment_id = e.id
               WHERE ea.user_id = ? AND e.status IN ('running', 'paused')""",
            (user_id,),
        ).fetchone()
        return row["cnt"] if row else 0
    except sqlite3.OperationalError:
        return 0


def _metric_count(
    conn: sqlite3.Connection, user_id: int, metric: str, lookback_days: int,
) -> int:
    try:
        if metric == "sessions":
            row = conn.execute(
                f"""SELECT COUNT(*) as cnt FROM session_log
                    WHERE user_id = ? AND started_at >= datetime('now', '-{lookback_days} days')""",
                (user_id,),
            ).fetchone()
        elif metric == "review_events":
            row = conn.execute(
                f"""SELECT COUNT(*) as cnt FROM review_event
                    WHERE user_id = ? AND created_at >= datetime('now', '-{lookback_days} days')""",
                (user_id,),
            ).fetchone()
        else:
            return 0
        return row["cnt"] if row else 0
    except sqlite3.OperationalError:
        return 0


def _has_feature(conn: sqlite3.Connection, user_id: int, feature: str) -> bool:
    """Check a learner profile boolean flag."""
    try:
        row = conn.execute(
            f"SELECT {feature} FROM learner_profile WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return bool(row and row[feature])
    except (sqlite3.OperationalError, IndexError):
        return False


def _is_in_holdout(conn: sqlite3.Connection, user_id: int) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM experiment_holdout WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False
