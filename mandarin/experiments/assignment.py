"""Assignment allocator — deterministic, hash-based, stratified, auditable.

Assignment is the core randomization layer.  It:
1. Checks eligibility (via eligibility engine)
2. Computes the user's stratum
3. Hashes (salt + experiment + stratum + user_id) for within-stratum balance
4. Persists the assignment with full metadata
5. Audit-logs the decision

Assignment NEVER uses predicted uplift, response probability, or any other
model output to determine which arm a user receives.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone

from .audit import log_audit_event
from .eligibility import check_eligibility
from .stratification import compute_stratum

logger = logging.getLogger(__name__)


def get_variant(
    conn: sqlite3.Connection,
    experiment_name: str,
    user_id: int,
    *,
    skip_eligibility: bool = False,
) -> str | None:
    """Get the variant for a user in an experiment.

    Returns ``None`` if the experiment is not running, the user is ineligible,
    or the user falls outside the traffic allocation.

    Assignment is deterministic via SHA-256 within the user's stratum.  The
    result is persisted in ``experiment_assignment`` (INSERT OR IGNORE) so
    subsequent calls return the same variant without recomputation.

    Parameters
    ----------
    skip_eligibility:
        Set ``True`` only in tests or when eligibility has already been checked
        in the current request.  In production, eligibility is always evaluated.
    """
    try:
        row = conn.execute(
            """SELECT id, status, variants, traffic_pct, salt,
                      eligibility_rules, stratification_config
               FROM experiment WHERE name = ?""",
            (experiment_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None

    if not row or row["status"] != "running":
        return None

    experiment_id = row["id"]
    variants = json.loads(row["variants"])
    traffic_pct = row["traffic_pct"]
    salt = row["salt"] or experiment_name

    if not variants:
        return None

    # ── Traffic gating ───────────────────────────────────────────────────
    traffic_pct_clamped = max(0.0, min(100.0, traffic_pct))
    traffic_key = f"traffic:{salt}:{user_id}"
    traffic_bucket = int(hashlib.sha256(traffic_key.encode()).hexdigest()[:8], 16) % 10000
    if traffic_bucket >= traffic_pct_clamped * 100:
        return None

    # ── Check for existing assignment ────────────────────────────────────
    existing = conn.execute(
        "SELECT variant FROM experiment_assignment WHERE experiment_id = ? AND user_id = ?",
        (experiment_id, user_id),
    ).fetchone()
    if existing:
        return existing["variant"]

    # ── Eligibility check ────────────────────────────────────────────────
    if not skip_eligibility:
        eligibility_rules = None
        if row["eligibility_rules"]:
            try:
                eligibility_rules = json.loads(row["eligibility_rules"])
            except json.JSONDecodeError:
                pass
        eligible, reasons = check_eligibility(
            conn, experiment_id, user_id, rules=eligibility_rules, log=True,
        )
        if not eligible:
            logger.debug(
                "User %d ineligible for experiment %r: %s",
                user_id, experiment_name, reasons,
            )
            return None

    # ── Compute stratum ──────────────────────────────────────────────────
    strat_config = None
    if row["stratification_config"]:
        try:
            strat_config = json.loads(row["stratification_config"])
        except json.JSONDecodeError:
            pass
    stratum = compute_stratum(conn, user_id, config=strat_config)

    # ── Deterministic assignment within stratum ──────────────────────────
    assign_key = f"{salt}:{experiment_name}:{stratum}:{user_id}"
    hash_hex = hashlib.sha256(assign_key.encode()).hexdigest()
    variant_index = int(hash_hex[:8], 16) % len(variants)
    variant = variants[variant_index]

    # ── Capture pre-period data for CUPED ────────────────────────────────
    pre_period = _capture_pre_period(conn, user_id)

    # ── Persist assignment ───────────────────────────────────────────────
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            """INSERT OR IGNORE INTO experiment_assignment
               (experiment_id, user_id, variant, assigned_at,
                stratum, hash_value, pre_period_data)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                experiment_id,
                user_id,
                variant,
                now,
                stratum,
                hash_hex[:16],
                json.dumps(pre_period) if pre_period else None,
            ),
        )
        conn.commit()
    except sqlite3.OperationalError:
        # Fallback for older schema without new columns
        conn.execute(
            """INSERT OR IGNORE INTO experiment_assignment
               (experiment_id, user_id, variant, assigned_at)
               VALUES (?, ?, ?, ?)""",
            (experiment_id, user_id, variant, now),
        )
        conn.commit()

    # ── Audit log ────────────────────────────────────────────────────────
    log_audit_event(
        conn,
        "assignment",
        experiment_id=experiment_id,
        user_id=user_id,
        data={
            "variant": variant,
            "stratum": stratum,
            "hash_value": hash_hex[:16],
            "traffic_bucket": traffic_bucket,
        },
    )

    logger.debug(
        "Assigned user %d to variant %r (stratum=%s) in experiment %r",
        user_id, variant, stratum, experiment_name,
    )
    return variant


def _capture_pre_period(conn: sqlite3.Connection, user_id: int) -> dict | None:
    """Capture pre-period metrics for CUPED variance reduction.

    Collects 14-day lookback metrics frozen at assignment time.
    """
    try:
        row = conn.execute(
            """SELECT
                 COUNT(*) as sessions_14d,
                 SUM(CASE WHEN session_outcome = 'completed' THEN 1 ELSE 0 END) as completed_14d,
                 SUM(items_correct) as correct_14d,
                 SUM(items_completed) as items_14d,
                 AVG(duration_seconds) as avg_duration_14d
               FROM session_log
               WHERE user_id = ?
                 AND started_at >= datetime('now', '-14 days')""",
            (user_id,),
        ).fetchone()

        if not row or row["sessions_14d"] == 0:
            return None

        sessions = row["sessions_14d"]
        completed = row["completed_14d"] or 0
        correct = row["correct_14d"] or 0
        items = row["items_14d"] or 0

        return {
            "sessions_14d": sessions,
            "completion_rate_14d": completed / sessions if sessions else 0.0,
            "accuracy_14d": correct / items if items else 0.0,
            "avg_duration_14d": float(row["avg_duration_14d"] or 0),
            "weekly_rate_14d": sessions / 2.0,
        }
    except sqlite3.OperationalError:
        return None
