"""Background thread for periodic quality metrics collection."""

import logging
import threading
import time

from .. import db

logger = logging.getLogger(__name__)

_DAILY_SECONDS = 86400
_INITIAL_DELAY = 300  # Wait 300s after startup before first collection

_stop_event = threading.Event()
_thread = None


def start():
    """Start the quality metrics background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="quality-metrics")
    _thread.start()
    logger.info("Quality metrics scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Collect quality metrics on startup + daily."""
    from ..scheduler_lock import acquire_lock, release_lock

    # Initial delay — let the app finish starting up
    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        # DB-backed lock: skip if another instance is already running
        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "quality_metrics", ttl_seconds=_DAILY_SECONDS):
                    logger.debug("Quality metrics: another instance holds the lock, skipping")
                    if _stop_event.wait(_DAILY_SECONDS):
                        break
                    continue
        except Exception:
            logger.exception("Quality metrics: lock acquisition failed")

        try:
            _collect_metrics()
        except Exception:
            logger.exception("Quality metrics collection failed")

        # Release lock after work completes
        try:
            with db.connection() as conn:
                release_lock(conn, "quality_metrics")
        except Exception:
            pass

        # Wait one day (or until stop signal)
        if _stop_event.wait(_DAILY_SECONDS):
            break

    logger.info("Quality metrics scheduler stopped")


def _collect_metrics():
    """Calculate and store quality metrics."""
    from ..quality import dpmo, spc, capability, retention

    with db.connection() as conn:
        # DPMO metrics
        try:
            dpmo_value = dpmo.calculate(conn)
            conn.execute(
                "INSERT INTO quality_metric (metric_type, value) VALUES (?, ?)",
                ("dpmo", dpmo_value),
            )
            logger.info("Quality metrics: DPMO = %.1f", dpmo_value)
        except Exception:
            logger.exception("Quality metrics: DPMO calculation failed")

        # SPC observations + auto-create work items on out-of-control
        for chart_type in ("drill_accuracy", "response_time", "session_completion"):
            try:
                value = spc.observe(conn, chart_type)
                if value is not None:
                    cur = conn.execute(
                        "INSERT INTO spc_observation (chart_type, value) VALUES (?, ?)",
                        (chart_type, value),
                    )
                    obs_id = cur.lastrowid

                    # SPC-to-action: check for out-of-control and auto-create work item
                    try:
                        from ..quality.spc import get_spc_chart_data
                        chart_data = get_spc_chart_data(conn, chart_type, days=30)
                        if chart_data.get("status") == "out_of_control":
                            violations = chart_data.get("violations", [])
                            violation_desc = "; ".join(
                                v.get("description", "unknown") for v in violations[:3]
                            )
                            # Check if we already have an open work item for this SPC violation
                            existing = conn.execute(
                                """SELECT id FROM work_item
                                   WHERE title LIKE ? AND status NOT IN ('done')""",
                                (f"SPC violation: {chart_type}%",),
                            ).fetchone()
                            if not existing:
                                conn.execute(
                                    """INSERT INTO work_item
                                       (title, description, item_type, status, service_class, ready_at)
                                       VALUES (?, ?, 'standard', 'ready', 'expedite', datetime('now'))""",
                                    (
                                        f"SPC violation: {chart_type}",
                                        f"Auto-created by SPC monitor.\n"
                                        f"Observation ID: {obs_id}\n"
                                        f"Violations: {violation_desc}\n"
                                        f"Chart status: out_of_control\n"
                                        f"- [ ] Investigate root cause\n"
                                        f"- [ ] Implement fix\n"
                                        f"- [ ] Verify SPC returns to in_control",
                                    ),
                                )
                                logger.info("SPC-to-action: created work item for %s violation", chart_type)

                            # Spiral: Link SPC violations to risk register
                            _link_spc_to_risk(conn, chart_type, violations, obs_id)
                    except Exception:
                        logger.debug("SPC-to-action check failed for %s", chart_type)
            except Exception:
                logger.exception("Quality metrics: SPC observation failed for %s", chart_type)

        # Capability metrics
        try:
            cap_metrics = capability.calculate(conn)
            for metric_name, metric_value in cap_metrics.items():
                conn.execute(
                    "INSERT INTO quality_metric (metric_type, value) VALUES (?, ?)",
                    (f"capability_{metric_name}", metric_value),
                )
        except Exception:
            logger.exception("Quality metrics: capability calculation failed")

        # Retention metrics
        try:
            ret_metrics = retention.calculate(conn)
            for metric_name, metric_value in ret_metrics.items():
                conn.execute(
                    "INSERT INTO quality_metric (metric_type, value) VALUES (?, ?)",
                    (f"retention_{metric_name}", metric_value),
                )
        except Exception:
            logger.exception("Quality metrics: retention calculation failed")

        # Risk appetite enforcement: auto-create work items for high-risk items
        try:
            high_risks = conn.execute("""
                SELECT id, title, description, category, probability, impact, mitigation,
                       (probability * impact) AS risk_score
                FROM risk_item
                WHERE status = 'active'
                  AND (probability * impact) >= 15
            """).fetchall()
            for risk in high_risks:
                # Check if mitigation work item already exists
                existing = conn.execute(
                    """SELECT id FROM work_item
                       WHERE title LIKE ? AND status NOT IN ('done')""",
                    (f"Mitigate risk: {risk['title']}%",),
                ).fetchone()
                if not existing:
                    risk_score = risk["risk_score"]
                    service_class = "expedite" if risk_score >= 20 else "standard"
                    conn.execute(
                        """INSERT INTO work_item
                           (title, description, item_type, status, service_class, ready_at)
                           VALUES (?, ?, 'standard', 'ready', ?, datetime('now'))""",
                        (
                            f"Mitigate risk: {risk['title']}",
                            f"Auto-created by risk monitor (score: {risk_score})\n"
                            f"Risk ID: {risk['id']}\n"
                            f"Category: {risk['category']}\n"
                            f"- [ ] Implement mitigation: {risk['mitigation'] or 'TBD'}\n"
                            f"- [ ] Verify risk reduced\n"
                            f"- [ ] Update risk register",
                            service_class,
                        ),
                    )
                    logger.info("Risk auto-mitigation: created work item for risk #%d (score %d)",
                                risk["id"], risk_score)
        except Exception:
            logger.debug("Risk auto-mitigation check failed")

        # Audio coherence check (Doc 23 B-03)
        try:
            from ..ai.audio_coherence import batch_check_coherence
            results = batch_check_coherence(conn, limit=20)
            if results:
                passed = sum(1 for r in results if r.get("passed"))
                logger.info("Audio coherence: %d/%d passed", passed, len(results))
        except ImportError:
            pass
        except Exception:
            logger.debug("Audio coherence check failed")

        # Data-driven risk identification (Spiral)
        try:
            _auto_identify_risks(conn)
        except Exception:
            logger.debug("Data-driven risk identification failed")

        conn.commit()


def _auto_identify_risks(conn):
    """Check system metrics and auto-create risk_item entries.

    Categories checked:
    - reliability: response time p95 increasing
    - retention: churn rate rising (session frequency drop)
    - quality: error rate spiking
    - security: security event count rising

    Only creates if no active risk of that category+title exists.
    """
    risk_checks = []

    # 1. Reliability risk: p95 response time increasing
    try:
        recent_p95 = conn.execute("""
            SELECT duration_ms FROM request_timing
            WHERE recorded_at >= datetime('now', '-1 day')
            ORDER BY duration_ms DESC
            LIMIT 1 OFFSET (
                SELECT MAX(0, CAST(COUNT(*) * 0.05 AS INTEGER))
                FROM request_timing WHERE recorded_at >= datetime('now', '-1 day')
            )
        """).fetchone()
        prior_p95 = conn.execute("""
            SELECT duration_ms FROM request_timing
            WHERE recorded_at >= datetime('now', '-8 days')
              AND recorded_at < datetime('now', '-1 day')
            ORDER BY duration_ms DESC
            LIMIT 1 OFFSET (
                SELECT MAX(0, CAST(COUNT(*) * 0.05 AS INTEGER))
                FROM request_timing
                WHERE recorded_at >= datetime('now', '-8 days')
                  AND recorded_at < datetime('now', '-1 day')
            )
        """).fetchone()
        if recent_p95 and prior_p95:
            recent_val = recent_p95["duration_ms"]
            prior_val = prior_p95["duration_ms"]
            if prior_val > 0 and recent_val > prior_val * 1.5:
                risk_checks.append({
                    "category": "technical",
                    "title": "Reliability risk: p95 response time increasing",
                    "description": (
                        f"p95 response time increased from {prior_val:.0f}ms to "
                        f"{recent_val:.0f}ms (+{((recent_val/prior_val)-1)*100:.0f}%)"
                    ),
                    "probability": 4,
                    "impact": 3,
                })
    except Exception:
        pass

    # 2. Retention risk: churn rate rising (session frequency drop)
    try:
        recent_sessions = conn.execute("""
            SELECT COUNT(DISTINCT user_id) as users FROM session_log
            WHERE started_at >= datetime('now', '-7 days')
        """).fetchone()
        prior_sessions = conn.execute("""
            SELECT COUNT(DISTINCT user_id) as users FROM session_log
            WHERE started_at >= datetime('now', '-14 days')
              AND started_at < datetime('now', '-7 days')
        """).fetchone()
        recent_users = (recent_sessions["users"] or 0) if recent_sessions else 0
        prior_users = (prior_sessions["users"] or 0) if prior_sessions else 0
        if prior_users >= 2 and recent_users < prior_users * 0.5:
            risk_checks.append({
                "category": "engagement",
                "title": "Retention risk: active users declining",
                "description": (
                    f"Active users dropped from {prior_users} to {recent_users} "
                    f"({(1 - recent_users/prior_users)*100:.0f}% decrease week-over-week)"
                ),
                "probability": 4,
                "impact": 4,
            })
    except Exception:
        pass

    # 3. Quality risk: error rate spiking
    try:
        recent_errors = conn.execute("""
            SELECT COUNT(*) as cnt FROM error_log
            WHERE created_at >= datetime('now', '-7 days')
        """).fetchone()
        prior_errors = conn.execute("""
            SELECT COUNT(*) as cnt FROM error_log
            WHERE created_at >= datetime('now', '-14 days')
              AND created_at < datetime('now', '-7 days')
        """).fetchone()
        recent_err = (recent_errors["cnt"] or 0) if recent_errors else 0
        prior_err = (prior_errors["cnt"] or 0) if prior_errors else 0
        if prior_err > 0 and recent_err > prior_err * 2:
            risk_checks.append({
                "category": "content",
                "title": "Quality risk: error rate spiking",
                "description": (
                    f"Error count increased from {prior_err} to {recent_err} "
                    f"({(recent_err/prior_err - 1)*100:.0f}% increase week-over-week)"
                ),
                "probability": 4,
                "impact": 3,
            })
    except Exception:
        pass

    # 4. Security risk: security event count rising
    try:
        recent_sec = conn.execute("""
            SELECT COUNT(*) as cnt FROM security_event
            WHERE created_at >= datetime('now', '-7 days')
              AND severity IN ('WARNING', 'HIGH', 'CRITICAL')
        """).fetchone()
        prior_sec = conn.execute("""
            SELECT COUNT(*) as cnt FROM security_event
            WHERE created_at >= datetime('now', '-14 days')
              AND created_at < datetime('now', '-7 days')
              AND severity IN ('WARNING', 'HIGH', 'CRITICAL')
        """).fetchone()
        recent_sec_cnt = (recent_sec["cnt"] or 0) if recent_sec else 0
        prior_sec_cnt = (prior_sec["cnt"] or 0) if prior_sec else 0
        if recent_sec_cnt > 5 and (prior_sec_cnt == 0 or recent_sec_cnt > prior_sec_cnt * 2):
            risk_checks.append({
                "category": "technical",
                "title": "Security risk: elevated security events",
                "description": (
                    f"Security events (WARNING+): {recent_sec_cnt} this week "
                    f"vs {prior_sec_cnt} prior week"
                ),
                "probability": 3,
                "impact": 5,
            })
    except Exception:
        pass

    # Create risk_item entries for any triggered checks (if no active duplicate)
    for risk in risk_checks:
        existing = conn.execute(
            """SELECT id FROM risk_item
               WHERE title = ? AND status = 'active'""",
            (risk["title"],),
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO risk_item (category, title, description, probability, impact, status)
                   VALUES (?, ?, ?, ?, ?, 'active')""",
                (risk["category"], risk["title"], risk["description"],
                 risk["probability"], risk["impact"]),
            )
            logger.info("Auto-created risk: %s", risk["title"])


def _link_spc_to_risk(conn, chart_type, violations, obs_id):
    """Link SPC violations to the risk register.

    When an out-of-control signal is found, auto-create or escalate a risk_item.
    Severity is based on SPC signal type (rule number).
    """
    try:
        # Determine severity from violation rules
        # Rule 1 (beyond 3-sigma) = highest severity
        rules_seen = {v.get("rule") for v in violations if v.get("rule")}
        if 1 in rules_seen:
            # Beyond 3-sigma — high severity
            probability = 4
            impact = 4
        elif 4 in rules_seen:
            # 2 of 3 beyond 2-sigma
            probability = 3
            impact = 4
        else:
            # Trend or run rules (2, 3) — moderate
            probability = 3
            impact = 3

        violation_desc = "; ".join(
            v.get("description", f"rule {v.get('rule', '?')}") for v in violations[:3]
        )

        # Check if an active risk already exists for this chart type
        existing = conn.execute(
            """SELECT id, probability, impact FROM risk_item
               WHERE title LIKE ? AND status = 'active'""",
            (f"SPC violation: {chart_type}%",),
        ).fetchone()

        if existing:
            # Escalate: increase probability if new violation is more severe
            new_prob = max(existing["probability"], probability)
            new_impact = max(existing["impact"], impact)
            if new_prob > existing["probability"] or new_impact > existing["impact"]:
                conn.execute(
                    """UPDATE risk_item SET probability = ?, impact = ?,
                              description = description || '\n' || ?,
                              updated_at = datetime('now')
                       WHERE id = ?""",
                    (new_prob, new_impact,
                     f"Escalated: obs #{obs_id} — {violation_desc}",
                     existing["id"]),
                )
                logger.info("SPC-to-risk: escalated risk #%d for %s", existing["id"], chart_type)
        else:
            # Create new risk item
            conn.execute(
                """INSERT INTO risk_item
                   (category, title, description, probability, impact, mitigation, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'active')""",
                (
                    "technical",
                    f"SPC violation: {chart_type}",
                    f"Auto-created from SPC out-of-control signal.\n"
                    f"Observation ID: {obs_id}\n"
                    f"Violations: {violation_desc}",
                    probability,
                    impact,
                    f"Investigate root cause via 5-Why analysis for {chart_type}",
                ),
            )
            logger.info("SPC-to-risk: created risk item for %s violation", chart_type)
    except Exception:
        logger.debug("SPC-to-risk linking failed for %s", chart_type)
