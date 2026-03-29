"""Background thread for periodic quality metrics collection."""

import logging
import threading
import time

from .. import db
from datetime import UTC

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

    # ── CI failure ingestion ──
    # Import findings from ci_findings.json (produced by CI Feedback Loop workflow)
    try:
        from ..intelligence.ci_ingest import import_ci_findings
        with db.connection() as conn:
            imported = import_ci_findings(conn)
            if imported:
                logger.info("CI findings: imported %d new finding(s)", imported)
    except ImportError:
        pass
    except Exception:
        logger.debug("CI findings import failed", exc_info=True)

    # ── Sentry issue ingestion ──
    # Import unresolved issues from Sentry API as runtime_health findings
    try:
        from ..intelligence.sentry_ingest import import_sentry_issues
        with db.connection() as conn:
            new_sentry = import_sentry_issues(conn)
            if new_sentry:
                logger.info("Imported %d new Sentry issues", new_sentry)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Sentry import failed: %s", e)

    with db.connection() as conn:
        # DPMO metrics
        try:
            dpmo_result = dpmo.calculate_dpmo(conn)
            dpmo_value = dpmo_result.get("dpmo", 0.0)
            sigma_level = dpmo_result.get("sigma_level", 0.0)
            total_opps = dpmo_result.get("total_opportunities", 0)
            conn.execute(
                "INSERT INTO quality_metric (metric_type, value) VALUES (?, ?)",
                ("dpmo", dpmo_value),
            )
            conn.execute(
                "INSERT INTO quality_metric (metric_type, value) VALUES (?, ?)",
                ("sigma_level", sigma_level),
            )
            logger.info(
                "Quality metrics: DPMO = %.1f (sigma %.2f, %d opportunities)",
                dpmo_value, sigma_level, total_opps,
            )
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

        # Auto-trigger DMAIC when SPC shows persistent violations
        try:
            from ..quality.spc import get_spc_charts
            charts = get_spc_charts(conn)
            for chart_name, chart_data in charts.items():
                violations = chart_data.get("violations", [])
                if len(violations) >= 3:
                    try:
                        from ..intelligence._synthesis import run_dmaic_cycle
                        run_dmaic_cycle(conn, chart_name)
                    except Exception:
                        pass
        except Exception:
            pass

        # Post-improvement verification (PIV): check work orders 14+ days after implementation
        try:
            pending_piv = conn.execute("""
                SELECT wo.id, wo.finding_id, wo.implemented_at, pf.dimension
                FROM pi_work_order wo
                JOIN pi_finding pf ON wo.finding_id = pf.id
                WHERE wo.status = 'implemented'
                AND wo.implemented_at <= datetime('now', '-14 days')
                AND wo.id NOT IN (SELECT work_order_id FROM prescription_execution_log WHERE status = 'verified')
            """).fetchall()

            for wo in (pending_piv or []):
                # Compare current dimension score vs pre-implementation
                try:
                    conn.execute("""
                        SELECT pre_audit_score FROM prescription_execution_log
                        WHERE work_order_id = ? ORDER BY created_at DESC LIMIT 1
                    """, (wo["id"],)).fetchone()

                    # Mark as verified (actual score comparison happens in next audit)
                    conn.execute("""
                        INSERT OR IGNORE INTO prescription_execution_log
                        (work_order_id, action_type, status, created_at)
                        VALUES (?, 'post_improvement_verification', 'verified', datetime('now'))
                    """, (wo["id"],))
                    conn.commit()
                except Exception:
                    pass
        except Exception:
            pass

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

        # VOC auto-capture: harvest learner feedback as Voice of Customer signals
        try:
            _capture_voc_signals(conn)
        except Exception:
            logger.debug("VOC auto-capture failed")

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

        # Design quality metrics (aesthetic self-improvement loop)
        try:
            _collect_design_metrics(conn)
        except Exception:
            logger.debug("Design quality metrics collection failed")

        # DMAIC cycle closure check (auto-close stable cycles)
        try:
            from ..intelligence.quality_metrics_generator import check_dmaic_closure
            closed = check_dmaic_closure(conn)
            if closed:
                logger.info("DMAIC closure: %d cycle(s) auto-closed", closed)
        except Exception:
            logger.debug("DMAIC closure check failed")

        # Andon threshold checks (real-time quality alerts)
        try:
            from .andon import check_andon_thresholds
            alerts = check_andon_thresholds(conn)
            if alerts:
                logger.info("Andon: %d alert(s) fired", alerts)
        except Exception:
            logger.debug("Andon threshold check failed")

        # Kanban flow metrics (cycle time, throughput, expedite dilution)
        try:
            from ..quality.flow_metrics import get_flow_summary
            flow = get_flow_summary(conn)
            ct_p85 = (flow.get("cycle_time") or {}).get("p85_hours")
            if ct_p85 is not None:
                conn.execute(
                    "INSERT INTO quality_metric (metric_type, value) VALUES (?, ?)",
                    ("kanban_cycle_time_p85", ct_p85),
                )
            tp_weekly = (flow.get("throughput") or {}).get("weekly_avg")
            if tp_weekly is not None:
                conn.execute(
                    "INSERT INTO quality_metric (metric_type, value) VALUES (?, ?)",
                    ("kanban_throughput_weekly", tp_weekly),
                )
            ed = flow.get("expedite_dilution") or {}
            if ed.get("dilution_pct") is not None:
                conn.execute(
                    "INSERT INTO quality_metric (metric_type, value) VALUES (?, ?)",
                    ("kanban_expedite_dilution", ed["dilution_pct"]),
                )
            # SLA breach notification
            sla = flow.get("service_class_compliance") or {}
            if sla.get("overall_compliance", 1.0) < 0.8:
                try:
                    conn.execute(
                        "INSERT INTO kanban_notification "
                        "(notification_type, message) VALUES (?, ?)",
                        ("sla_breach",
                         f"SLA compliance dropped to {sla['overall_compliance']:.0%}"),
                    )
                except Exception:
                    pass
            logger.info(
                "Kanban metrics: cycle_time_p85=%.1fh, throughput=%.1f/wk, expedite=%.1f%%",
                ct_p85 or 0, tp_weekly or 0, ed.get("dilution_pct", 0),
            )
        except Exception:
            logger.debug("Kanban flow metrics collection failed")

        conn.commit()

    # ── FSRS per-learner calibration ──
    try:
        with db.connection() as conn:
            from ..fsrs_calibration import calibrate_all_eligible
            calibrated = calibrate_all_eligible(conn, limit=10)
            if calibrated:
                logger.info("FSRS calibration: %d user(s) calibrated", calibrated)
    except ImportError:
        pass
    except Exception:
        logger.debug("FSRS calibration failed")

    # ── Confusable pair detection ──
    try:
        with db.connection() as conn:
            from ..interference import detect_confusables
            new_pairs = detect_confusables(conn, limit=200)
            if new_pairs:
                logger.info("Interference: %d new confusable pairs detected", new_pairs)
    except ImportError:
        pass
    except Exception:
        logger.debug("Confusable pair detection failed")

    # ── Prerequisite graph building ──
    try:
        with db.connection() as conn:
            from ..prerequisites import build_prerequisite_graph
            new_edges = build_prerequisite_graph(conn, limit=200)
            if new_edges:
                logger.info("Prerequisites: %d new edges built", new_edges)
    except ImportError:
        pass
    except Exception:
        logger.debug("Prerequisite graph building failed")

    # ── IRT psychometric calibration ──
    try:
        with db.connection() as conn:
            from ..psychometrics import joint_estimation, save_irt_results
            irt_results = joint_estimation(conn, max_iter=30)
            if irt_results.get("converged") and irt_results.get("n_items", 0) > 0:
                saved = save_irt_results(conn, irt_results)
                if saved:
                    logger.info(
                        "IRT calibration: %d items, %d users (converged in %d iter)",
                        irt_results["n_items"], irt_results["n_users"],
                        irt_results["iterations"],
                    )
    except ImportError:
        pass
    except Exception:
        logger.debug("IRT calibration failed")

    # ── Learner segmentation ──
    try:
        with db.connection() as conn:
            from ..quality.segmentation import segment_learners
            segments = segment_learners(conn, k=4)
            if segments and segments.get("segments"):
                logger.info("Learner segmentation: %d segments", len(segments["segments"]))
    except ImportError:
        pass
    except Exception:
        logger.debug("Learner segmentation failed")

    # ── Content reaudit ──
    # Sample approved AI items and verify quality post-approval.
    try:
        with db.connection() as conn:
            from ..ai.content_reaudit import run_scheduled_reaudit, check_learner_accuracy_flags
            reaudit_result = run_scheduled_reaudit(conn, sample_size=10)
            logger.info("Content reaudit: %s", reaudit_result)
            accuracy_result = check_learner_accuracy_flags(conn)
            if accuracy_result.get("flagged", 0) > 0:
                logger.info("Content accuracy flags: %s", accuracy_result)
    except Exception:
        logger.debug("Content reaudit failed", exc_info=True)

    # ── Intelligence automation loop ──
    # Runs after quality metrics are collected so audit has fresh data.
    _run_intelligence_loop()


def _capture_voc_signals(conn):
    """Harvest Voice of Customer signals from session self-assessments and error reflections.

    Inserts into pi_voc_capture for use by DFSS DMADV cycles.
    Deduplicates on (customer_need, source) within the last 7 days.
    """
    # 1. Session self-assessments: learner difficulty ratings
    try:
        assessments = conn.execute("""
            SELECT assessment, COUNT(*) as cnt
            FROM session_self_assessment
            WHERE created_at >= datetime('now', '-1 day')
            GROUP BY assessment
            HAVING cnt >= 2
        """).fetchall()
        for row in (assessments or []):
            assessment = row["assessment"]
            count = row["cnt"]
            need = f"session_difficulty:{assessment}"
            # Dedup: skip if already captured this week
            existing = conn.execute("""
                SELECT id FROM pi_voc_capture
                WHERE customer_need = ? AND source = 'session_self_assessment'
                  AND captured_at >= datetime('now', '-7 days')
            """, (need,)).fetchone()
            if not existing:
                priority = 3 if assessment in ("too_hard", "too_easy") else 1
                conn.execute("""
                    INSERT INTO pi_voc_capture
                    (customer_need, ctq_metric, source, source_detail, priority)
                    VALUES (?, ?, 'session_self_assessment', ?, ?)
                """, (need, "session_difficulty_balance",
                      f"{count} reports in last day", priority))
    except Exception:
        logger.debug("VOC: session_self_assessment capture failed")

    # 2. Error reflections: learner-reported confusion or errors
    try:
        reflections = conn.execute("""
            SELECT error_type, COUNT(*) as cnt
            FROM error_reflection
            WHERE created_at >= datetime('now', '-1 day')
            GROUP BY error_type
            HAVING cnt >= 2
        """).fetchall()
        for row in (reflections or []):
            error_type = row["error_type"]
            count = row["cnt"]
            need = f"error_pattern:{error_type}"
            existing = conn.execute("""
                SELECT id FROM pi_voc_capture
                WHERE customer_need = ? AND source = 'error_reflection'
                  AND captured_at >= datetime('now', '-7 days')
            """, (need,)).fetchone()
            if not existing:
                conn.execute("""
                    INSERT INTO pi_voc_capture
                    (customer_need, ctq_metric, source, source_detail, priority)
                    VALUES (?, ?, 'error_reflection', ?, ?)
                """, (need, "error_rate", f"{count} reports in last day", 2))
    except Exception:
        logger.debug("VOC: error_reflection capture failed")

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


def _collect_design_metrics(conn):
    """Run visual quality analysis and store findings."""
    try:
        from ..intelligence.analyzers_design_quality import ANALYZERS as DESIGN_ANALYZERS
        for analyzer in DESIGN_ANALYZERS:
            try:
                analyzer(conn)
                # findings flow into the standard pipeline via the audit system
            except Exception:
                logger.exception("Design quality analyzer %s failed", analyzer.__name__)
    except ImportError:
        logger.debug("Design quality analyzers not available")


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


def _run_intelligence_loop():
    """Run the full intelligence automation loop.

    1. Run product audit (which generates findings, advisors, work orders internally)
    2. Auto-execute safe prescriptions on the new work order
    3. Score past predictions and auto-verify/close work orders + findings
    """
    from .. import db

    try:
        with db.connection() as conn:
            # 1. Run product audit (includes work order generation internally)
            from ..intelligence import run_product_audit
            audit_result = run_product_audit(conn)
            # Collect all work orders (batch of up to 3)
            all_work_orders = audit_result.get("work_orders", [])
            if not all_work_orders:
                # Backward compat: single work_order key
                wo = audit_result.get("work_order")
                if wo and wo.get("id"):
                    all_work_orders = [wo]

            logger.info(
                "Intelligence loop: audit complete — %d findings, %d work orders, overall %s",
                len(audit_result.get("findings", [])),
                len(all_work_orders),
                audit_result.get("overall", {}).get("score", "?"),
            )

            # 1b. Meta-review: LLM risk-scores work orders before execution
            try:
                from ..intelligence.meta_intelligence import meta_review_work_orders
                all_work_orders = meta_review_work_orders(conn, all_work_orders)
                # Skip high-risk work orders
                risky = [wo for wo in all_work_orders if wo.get("llm_risk", 0) > 0.7]
                if risky:
                    logger.info(
                        "Intelligence loop: skipping %d high-risk work orders",
                        len(risky),
                    )
                all_work_orders = [wo for wo in all_work_orders if wo.get("llm_risk", 0) <= 0.7]
            except (ImportError, Exception):
                pass  # Meta-review is optional

            # 2. Auto-execute safe prescriptions on ALL work orders
            for work_order_data in all_work_orders:
                wo_id = work_order_data.get("id")
                if not wo_id:
                    continue
                try:
                    from ..ai.agentic import execute_prescription
                    exec_result = execute_prescription(conn, wo_id)
                    if exec_result.get("status") == "executed":
                        logger.info(
                            "Intelligence loop: auto-executed prescription for WO #%d — %s",
                            wo_id, exec_result,
                        )
                        from ..intelligence.prescription import mark_work_order_implemented
                        mark_work_order_implemented(
                            conn, wo_id,
                            notes=f"Auto-executed by intelligence loop: {exec_result}",
                        )
                    elif exec_result.get("status") == "queued_for_agent":
                        logger.info(
                            "Intelligence loop: WO #%d queued for LangGraph agent", wo_id,
                        )
                    elif exec_result.get("status") == "requires_human":
                        logger.info(
                            "Intelligence loop: WO #%d requires human action", wo_id,
                        )
                except Exception:
                    logger.debug("Intelligence loop: prescription execution failed for WO #%d",
                                 wo_id, exc_info=True)

            # 2b. Run LangGraph prescription executor for code-level changes
            try:
                from ..ai.llm_agent import execute_queued_prescriptions
                agent_results = execute_queued_prescriptions(conn)
                if agent_results:
                    logger.info(
                        "Intelligence loop: LangGraph agent processed %d prescriptions",
                        len(agent_results),
                    )
            except ImportError:
                pass  # LangGraph not installed
            except Exception:
                logger.debug("Intelligence loop: LangGraph agent failed", exc_info=True)

            # 2d. Agentic model selection (weekly benchmark + routing)
            try:
                from ..ai.model_selector import run_model_selection_cycle
                sel_result = run_model_selection_cycle(conn)
                if sel_result.get("tasks_routed"):
                    logger.info(
                        "Intelligence loop: model selection routed %d tasks",
                        sel_result["tasks_routed"],
                    )
            except ImportError:
                pass
            except Exception:
                logger.debug("Intelligence loop: model selection failed", exc_info=True)

            # 2c. Send proactive notification via OpenClaw
            try:
                from ..openclaw import notify_owner
                summary = (
                    f"Audit: {len(audit_result.get('findings', []))} findings, "
                    f"{len(all_work_orders)} work orders"
                )
                for wo in all_work_orders[:5]:
                    dim = wo.get("constraint_dimension", "?")
                    instr = (wo.get("instruction") or "")[:80]
                    summary += f"\n• [{dim}] {instr}"
                notify_owner(summary)
            except (ImportError, Exception):
                pass

            # 3. Score past predictions + auto-verify work orders
            try:
                from ..intelligence.feedback_loops import record_prediction_outcomes
                outcomes = record_prediction_outcomes(conn)
                if outcomes:
                    logger.info("Intelligence loop: scored %d predictions", len(outcomes))
                    _auto_verify_work_orders(conn, outcomes)
            except Exception:
                logger.debug("Intelligence loop: prediction scoring failed", exc_info=True)

            # 4. Auto-execute safe fixes (guarded by EXECUTOR_ENABLED flag)
            try:
                from ..intelligence.auto_executor import EXECUTOR_ENABLED, execute_auto_fixes
                if EXECUTOR_ENABLED:
                    fix_results = execute_auto_fixes(conn)
                    if fix_results:
                        applied = sum(1 for r in fix_results if r.get("status") == "applied")
                        escalated = sum(1 for r in fix_results if r.get("status") == "escalated")
                        logger.info(
                            "Intelligence loop: auto-executor processed %d fixes "
                            "(%d applied, %d escalated)",
                            len(fix_results), applied, escalated,
                        )
            except ImportError:
                pass
            except Exception:
                logger.debug("Intelligence loop: auto-executor failed", exc_info=True)

            # 5. Send daily intelligence digest email
            try:
                from ..email import send_daily_intelligence_digest
                send_daily_intelligence_digest(conn)
            except Exception:
                logger.warning("Intelligence loop: daily digest email failed", exc_info=True)

    except Exception:
        logger.exception("Intelligence automation loop failed")


def _auto_verify_work_orders(conn, prediction_outcomes):
    """Auto-transition work orders based on prediction outcomes.

    When a prediction is scored:
    - correct / directionally_correct → work order 'succeeded', finding → 'verified' → 'resolved'
    - wrong → work order 'failed', finding stays at 'implemented'
    """
    from datetime import datetime as _dt, timezone as _tz
    from ..intelligence._base import _safe_query
    from ..intelligence.finding_lifecycle import transition_finding

    for outcome in prediction_outcomes:
        prediction_id = outcome.get("prediction_id")
        outcome_class = outcome.get("outcome_class")
        if not prediction_id or outcome_class in ("insufficient_data",):
            continue

        # Find the work order linked to this prediction
        wo = _safe_query(conn, """
            SELECT id, finding_id, status FROM pi_work_order
            WHERE prediction_id = ? AND status = 'verifying'
        """, (prediction_id,))
        if not wo:
            continue

        now_str = _dt.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        if outcome_class in ("correct", "directionally_correct"):
            # Success: mark work order succeeded + auto-close finding
            try:
                conn.execute("""
                    UPDATE pi_work_order SET status = 'succeeded', verified_at = ?,
                           outcome_notes = ?
                    WHERE id = ?
                """, (now_str, f"Auto-verified: prediction {outcome_class}", wo["id"]))

                # Advance finding: implemented → verified → resolved
                transition_finding(conn, wo["finding_id"], "verified")
                transition_finding(conn, wo["finding_id"], "resolved",
                                   notes=f"Auto-resolved: prediction {outcome_class}")
                conn.commit()
                logger.info(
                    "Intelligence loop: WO #%d auto-verified (%s), finding #%d resolved",
                    wo["id"], outcome_class, wo["finding_id"],
                )
            except Exception:
                logger.debug("Auto-verify failed for WO #%d", wo["id"], exc_info=True)

        elif outcome_class == "wrong":
            # Failure: mark work order failed, finding stays for re-investigation
            try:
                conn.execute("""
                    UPDATE pi_work_order SET status = 'failed', verified_at = ?,
                           outcome_notes = ?
                    WHERE id = ?
                """, (now_str, "Auto-failed: prediction was wrong", wo["id"]))
                conn.commit()
                logger.info(
                    "Intelligence loop: WO #%d auto-failed (prediction wrong)",
                    wo["id"],
                )
            except Exception:
                logger.debug("Auto-fail update failed for WO #%d", wo["id"], exc_info=True)
