"""Anti-Goodhart counter-metrics daemon — computes, stores, and actions on counter-metrics.

Runs every 4 hours (background thread, same pattern as experiment_daemon.py):
1. Compute full counter-metric assessment for all active users
2. Save snapshot for trend tracking
3. Evaluate alerts against thresholds
4. Execute automated actions (scheduler adjustments, experiment proposals, notifications)
5. Enforce product rules
6. Weekly digest to admin

Design principle: this is a control system, not a reporting tool.
Alerts trigger actions. Actions are logged. The admin sees a digest.
"""

import json
import logging
import threading
from datetime import datetime, timedelta, timezone, UTC

from .. import db
from ..counter_metrics import compute_full_assessment, save_snapshot
from ..counter_metrics_actions import (
    execute_actions_for_assessment,
    enforce_product_rules,
)

logger = logging.getLogger(__name__)

_CYCLE_SECONDS = 4 * 3600  # 4 hours
_INITIAL_DELAY = 600  # 10 minutes after startup (let other systems settle)

_stop_event = threading.Event()
_thread = None


def start():
    """Start the counter-metrics daemon background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True,
                               name="counter-metrics-daemon")
    _thread.start()
    logger.info("Counter-metrics daemon started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Main daemon loop — acquire lock, run tick, sleep, repeat."""
    from ..scheduler_lock import acquire_lock, release_lock

    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        conn = None
        try:
            conn = db.get_connection()
            if not acquire_lock(conn, "counter_metrics_daemon", ttl_seconds=_CYCLE_SECONDS):
                logger.debug("Counter-metrics daemon: lock held by another instance, skipping")
                if _stop_event.wait(_CYCLE_SECONDS):
                    break
                continue

            _daemon_tick(conn)
            release_lock(conn, "counter_metrics_daemon")

        except Exception:
            logger.exception("Counter-metrics daemon tick failed")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        if _stop_event.wait(_CYCLE_SECONDS):
            break


def _daemon_tick(conn):
    """Single daemon cycle — compute, store, action, enforce."""
    now = datetime.now(UTC)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    digest_entries = []

    # ── 1. Get active users ──
    # For now, single-user system; forward-compatible with multi-user
    user_ids = [1]
    try:
        rows = conn.execute("""
            SELECT DISTINCT id FROM user
            WHERE id IN (
                SELECT user_id FROM session_log
                WHERE started_at >= datetime('now', '-30 days')
            )
        """).fetchall()
        if rows:
            user_ids = [r[0] for r in rows]
    except Exception:
        pass  # Fall back to user_id=1

    for user_id in user_ids:
        try:
            # ── 2. Compute full assessment ──
            assessment = compute_full_assessment(conn, user_id=user_id)
            overall = assessment.get("overall_health", "unknown")
            alert_count = assessment.get("alert_summary", {}).get("total", 0)
            critical_count = assessment.get("alert_summary", {}).get("critical", 0)

            logger.info(
                "Counter-metrics assessment: user=%d health=%s alerts=%d critical=%d",
                user_id, overall, alert_count, critical_count,
            )

            # ── 3. Save snapshot ──
            save_snapshot(conn, assessment, user_id=user_id)
            digest_entries.append(
                f"ASSESSED user={user_id}: {overall} ({alert_count} alerts, {critical_count} critical)"
            )

            # ── 4. Execute automated actions ──
            if alert_count > 0:
                actions = execute_actions_for_assessment(conn, assessment)
                for action in actions:
                    msg = f"ACTION {action.get('type')}: {action.get('action', action.get('name', ''))}"
                    logger.info(msg)
                    digest_entries.append(msg)

            # ── 4b. Schedule delayed recall validations for recent promotions ──
            try:
                from ..delayed_validation import schedule_validations_for_recent_promotions
                dv_count = schedule_validations_for_recent_promotions(conn, user_id=user_id)
                if dv_count > 0:
                    msg = f"SCHEDULED {dv_count} delayed recall validations for user={user_id}"
                    logger.info(msg)
                    digest_entries.append(msg)
            except Exception:
                logger.debug("delayed validation scheduling skipped", exc_info=True)

            # ── 5. Enforce product rules ──
            violations = enforce_product_rules(assessment)
            for v in violations:
                msg = f"RULE {v['rule']} VIOLATION: {v['description']} (metric={v['metric']}, value={v['value']})"
                logger.warning(msg)
                digest_entries.append(msg)

                # Log violation as lifecycle event
                try:
                    conn.execute("""
                        INSERT INTO lifecycle_event
                        (user_id, event_type, metadata, created_at)
                        VALUES (?, 'counter_metric_rule_violation', ?, ?)
                    """, (user_id, json.dumps(v), now_str))
                    conn.commit()
                except Exception:
                    pass

        except Exception:
            logger.exception("Counter-metrics assessment failed for user %d", user_id)

    # ── 6. Weekly digest ──
    try:
        last_digest = conn.execute("""
            SELECT MAX(created_at) as last FROM lifecycle_event
            WHERE event_type = 'counter_metric_digest'
        """).fetchone()
        last_digest_date = last_digest["last"] if last_digest and last_digest["last"] else None

        should_digest = True
        if last_digest_date:
            try:
                last_dt = datetime.fromisoformat(last_digest_date)
                should_digest = (now - last_dt).days >= 7
            except (ValueError, TypeError):
                pass

        if should_digest and digest_entries:
            digest_json = json.dumps({
                "timestamp": now_str,
                "entries": digest_entries,
                "user_count": len(user_ids),
            })
            conn.execute("""
                INSERT INTO lifecycle_event
                (user_id, event_type, metadata, created_at)
                VALUES (1, 'counter_metric_digest', ?, ?)
            """, (digest_json, now_str))
            conn.commit()
            logger.info("Counter-metrics digest logged: %d entries", len(digest_entries))
    except Exception:
        logger.exception("Error generating counter-metrics digest")


def run_once(conn=None):
    """Run a single tick manually (for CLI or admin triggering).

    Returns the assessment result for the primary user.
    """
    close_conn = False
    if conn is None:
        conn = db.get_connection()
        close_conn = True

    try:
        assessment = compute_full_assessment(conn, user_id=1)
        save_snapshot(conn, assessment, user_id=1)

        actions = []
        if assessment.get("alert_summary", {}).get("total", 0) > 0:
            actions = execute_actions_for_assessment(conn, assessment)

        violations = enforce_product_rules(assessment)

        return {
            "assessment": assessment,
            "actions_taken": actions,
            "rule_violations": violations,
        }
    finally:
        if close_conn and conn:
            conn.close()
