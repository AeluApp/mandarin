"""Product Intelligence — Operations Research analyzers.

Closes the loop: OR systems detect anomalies → findings emitted →
prescription layer classifies → LangGraph agent acts.

Analyzers:
  1. SPC violations (control chart out-of-control points)
  2. Queue capacity (M/G/1 utilization warnings)
  3. CLV health (high-LTV user decline detection)
  4. Monte Carlo alerts (queue projection overflow)
  5. Price experiments (concluded experiments with unapplied winners)
  6. Curriculum drift (actual study path vs Dijkstra optimal)
  7. Viral health (k-factor and referral system monitoring)
"""

import logging

from ._base import _finding, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── 1. SPC Violations ────────────────────────────────────────────────────────

def _analyze_spc_violations(conn) -> list[dict]:
    """Detect SPC control chart violations and emit findings by rule severity."""
    try:
        from ..quality.spc import get_spc_charts
        charts = get_spc_charts(conn)
        findings = []

        for chart_name, chart in charts.items():
            violations = chart.get("violations", [])
            if not violations:
                continue

            # Rule 1 = 3-sigma breach → HIGH; rules 2-4 → MEDIUM
            has_rule1 = any(v.get("rule") == 1 for v in violations)
            severity = "high" if has_rule1 else "medium"

            rule_descriptions = "; ".join(
                v.get("description", f"rule {v.get('rule')}") for v in violations[:5]
            )
            title_label = chart.get("title", chart_name)

            findings.append(_finding(
                "engineering", severity,
                f"SPC violation in {title_label}: {len(violations)} out-of-control point(s)",
                (
                    f"Control chart '{title_label}' has {len(violations)} "
                    f"out-of-control points. Violations: {rule_descriptions}."
                ),
                (
                    f"Investigate root cause of SPC violations in {title_label}. "
                    f"Rule 1 (3-sigma) breaches indicate special-cause variation."
                ),
                (
                    f"SPC chart '{title_label}' has {len(violations)} violations.\n\n"
                    f"1. Review the control chart data for '{chart_name}'\n"
                    f"2. Identify assignable causes for out-of-control points\n"
                    f"3. Apply corrective action and verify the process returns to control"
                ),
                "Process stability: out-of-control processes produce unpredictable quality",
                ["mandarin/quality/spc.py"],
            ))

        return findings
    except Exception as e:
        logger.debug("SPC violation analysis failed: %s", e)
        return []


# ── 2. Queue Capacity ────────────────────────────────────────────────────────

def _analyze_queue_capacity(conn) -> list[dict]:
    """Monitor M/G/1 queue utilization and emit capacity warnings."""
    try:
        from ..quality.queue_model import queue_model

        # Check each active user's queue
        user_rows = _safe_query_all(conn, """
            SELECT DISTINCT user_id FROM session_log
            WHERE started_at >= datetime('now', '-14 days')
        """)
        if not user_rows:
            return []

        findings = []
        for row in user_rows:
            user_id = row["user_id"]
            metrics = queue_model(conn, user_id=user_id)
            utilization = metrics.get("utilization", 0)

            if utilization > 0.85:
                findings.append(_finding(
                    "scheduler_audit", "high",
                    f"Queue utilization {utilization:.0%} for user {user_id} — overload risk",
                    (
                        f"User {user_id} review queue utilization is {utilization:.0%}. "
                        f"Arrival rate: {metrics.get('arrival_rate', 0):.2f}/day, "
                        f"service rate: {metrics.get('service_rate', 0):.2f}/day. "
                        f"Queue is near saturation."
                    ),
                    (
                        f"Reduce new_item_ceiling for user {user_id} to lower arrival rate. "
                        f"Current recommendation: {metrics.get('recommendation', 'N/A')}"
                    ),
                    (
                        f"Queue overload for user {user_id} (utilization={utilization:.0%}).\n\n"
                        f"1. Reduce new_item_ceiling in mandarin/settings.py\n"
                        f"2. Verify arrival rate drops below service rate\n"
                        f"3. Monitor queue depth over next 7 days"
                    ),
                    "Learner experience: overloaded queues cause review debt and churn",
                    ["mandarin/settings.py", "mandarin/scheduler.py"],
                ))
            elif utilization > 0.70:
                findings.append(_finding(
                    "scheduler_audit", "medium",
                    f"Queue utilization {utilization:.0%} for user {user_id} — early warning",
                    (
                        f"User {user_id} review queue utilization is {utilization:.0%}. "
                        f"Approaching capacity. Arrival rate: "
                        f"{metrics.get('arrival_rate', 0):.2f}/day, "
                        f"service rate: {metrics.get('service_rate', 0):.2f}/day."
                    ),
                    (
                        f"Monitor queue growth for user {user_id}. "
                        f"Consider reducing new item introduction rate if utilization continues rising."
                    ),
                    (
                        f"Queue early warning for user {user_id} (utilization={utilization:.0%}).\n\n"
                        f"1. Check queue depth trend over last 14 days\n"
                        f"2. If rising, reduce new_item_ceiling preemptively\n"
                        f"3. Consider adjusting session length targets"
                    ),
                    "Learner experience: growing queues lead to eventual overwhelm",
                    ["mandarin/settings.py", "mandarin/scheduler.py"],
                ))

        return findings
    except Exception as e:
        logger.debug("Queue capacity analysis failed: %s", e)
        return []


# ── 3. CLV Health ─────────────────────────────────────────────────────────────

def _analyze_clv_health(conn) -> list[dict]:
    """Detect high-LTV users with declining engagement."""
    try:
        from ..analytics.clv import predict_ltv_segment

        # Users with sessions in last 14 days
        active_users = _safe_query_all(conn, """
            SELECT DISTINCT user_id FROM session_log
            WHERE started_at >= datetime('now', '-14 days')
        """)
        if not active_users:
            return []

        findings = []
        for row in active_users:
            user_id = row["user_id"]
            segment = predict_ltv_segment(conn, user_id)
            if segment != "high":
                continue

            # Compare recent 7-day session count vs prior 7-day count
            recent = _safe_scalar(conn, """
                SELECT COUNT(*) FROM session_log
                WHERE user_id = ? AND started_at >= datetime('now', '-7 days')
            """, (user_id,), default=0)

            prior = _safe_scalar(conn, """
                SELECT COUNT(*) FROM session_log
                WHERE user_id = ?
                  AND started_at >= datetime('now', '-14 days')
                  AND started_at < datetime('now', '-7 days')
            """, (user_id,), default=0)

            if prior > 0 and recent < prior:
                findings.append(_finding(
                    "retention", "high",
                    f"High-LTV user {user_id} session decline: {prior} → {recent} sessions/week",
                    (
                        f"User {user_id} is classified as high-LTV but sessions dropped "
                        f"from {prior} (prior week) to {recent} (this week). "
                        f"Declining engagement in high-value users is a leading churn indicator."
                    ),
                    (
                        f"Trigger retention intervention for user {user_id}. "
                        f"Consider personalized re-engagement: adjusted difficulty, "
                        f"fresh content, or direct outreach."
                    ),
                    (
                        f"High-LTV user {user_id} declining ({prior}→{recent} sessions).\n\n"
                        f"1. Check session_log for patterns (time of day, completion rate)\n"
                        f"2. Review content freshness — are they seeing repetitive material?\n"
                        f"3. Consider triggering a re-engagement email or content refresh"
                    ),
                    "Revenue: high-LTV user churn has disproportionate revenue impact",
                    ["mandarin/web/session_routes.py", "mandarin/scheduler.py"],
                ))

        return findings
    except Exception as e:
        logger.debug("CLV health analysis failed: %s", e)
        return []


# ── 4. Monte Carlo Alerts ────────────────────────────────────────────────────

def _analyze_monte_carlo_alerts(conn) -> list[dict]:
    """Run queue projection simulation and alert on overflow risk."""
    try:
        from ..quality.monte_carlo import simulate_review_queue

        result = simulate_review_queue(conn, days=30, n_simulations=500)
        daily_counts = result.get("daily_review_counts", [])
        if not daily_counts:
            return []

        # Check the p95 at day 30
        last_day = daily_counts[-1] if daily_counts else {}
        p95 = last_day.get("p95", 0)

        findings = []
        if p95 >= 1000:
            findings.append(_finding(
                "engineering", "high",
                f"Monte Carlo: p95 queue projection reaches {p95:.0f} items in 30 days",
                (
                    f"Review queue simulation (500 runs) projects p95 queue size "
                    f"of {p95:.0f} items at day 30. This exceeds the 1000-item "
                    f"critical threshold and indicates capacity planning is needed."
                ),
                (
                    "Increase capacity: raise session frequency targets, reduce new "
                    "item introduction, or implement queue overflow policies."
                ),
                (
                    f"Monte Carlo projects p95={p95:.0f} queue items at 30 days.\n\n"
                    f"1. Review current arrival and service rates in queue_model\n"
                    f"2. Adjust new_item_ceiling or session targets in settings.py\n"
                    f"3. Consider implementing a queue overflow policy (auto-retire low-priority items)"
                ),
                "Capacity: unchecked queue growth leads to learner overwhelm",
                ["mandarin/settings.py", "mandarin/quality/queue_model.py"],
            ))
        elif p95 >= 500:
            findings.append(_finding(
                "engineering", "medium",
                f"Monte Carlo: p95 queue projection reaches {p95:.0f} items in 30 days",
                (
                    f"Review queue simulation (500 runs) projects p95 queue size "
                    f"of {p95:.0f} items at day 30. Approaching the capacity comfort zone."
                ),
                (
                    "Monitor queue growth trend. Consider preemptive adjustments to "
                    "new item introduction rate if growth continues."
                ),
                (
                    f"Monte Carlo projects p95={p95:.0f} queue items at 30 days.\n\n"
                    f"1. Check if arrival rate is trending up\n"
                    f"2. Consider reducing new_item_ceiling by 10-20%\n"
                    f"3. Re-run simulation after adjustments to verify improvement"
                ),
                "Capacity: moderate queue growth may require intervention",
                ["mandarin/settings.py", "mandarin/quality/queue_model.py"],
            ))

        return findings
    except Exception as e:
        logger.debug("Monte Carlo alert analysis failed: %s", e)
        return []


# ── 5. Price Experiments ──────────────────────────────────────────────────────

def _analyze_price_experiments(conn) -> list[dict]:
    """Check for concluded price experiments with unapplied winners."""
    try:
        concluded = _safe_query_all(conn, """
            SELECT name, winner, notes FROM experiment
            WHERE status = 'concluded'
              AND winner IS NOT NULL
              AND winner != 'none'
              AND name LIKE '%price%'
        """)
        if not concluded:
            return []

        findings = []
        for exp in concluded:
            name = exp["name"]
            winner = exp["winner"]
            findings.append(_finding(
                "marketing", "low",
                f"Price experiment '{name}' concluded — winner '{winner}' not yet applied",
                (
                    f"Experiment '{name}' concluded with winning variant '{winner}'. "
                    f"The price change has not been applied to production settings. "
                    f"Notes: {exp.get('notes', 'N/A')}"
                ),
                f"Update pricing configuration to reflect experiment winner '{winner}'.",
                (
                    f"Price experiment '{name}' winner='{winner}' is unapplied.\n\n"
                    f"1. Review experiment results and statistical significance\n"
                    f"2. Update pricing in mandarin/settings.py\n"
                    f"3. Verify the change is reflected in the payment flow"
                ),
                "Revenue: unapplied winning prices leave money on the table",
                ["mandarin/settings.py", "mandarin/web/payment_routes.py"],
            ))

        return findings
    except Exception as e:
        logger.debug("Price experiment analysis failed: %s", e)
        return []


# ── 6. Curriculum Drift ──────────────────────────────────────────────────────

def _analyze_curriculum_drift(conn) -> list[dict]:
    """Compare recent items studied vs Dijkstra optimal path for active users."""
    try:
        from ..quality.curriculum_graph import suggest_next_items

        # Active users in last 14 days
        active_users = _safe_query_all(conn, """
            SELECT DISTINCT user_id FROM session_log
            WHERE started_at >= datetime('now', '-14 days')
        """)
        if not active_users:
            return []

        findings = []
        for row in active_users:
            user_id = row["user_id"]

            # Get optimal next items
            optimal = suggest_next_items(conn, user_id, n=20)
            if not optimal:
                continue

            # Get recently studied items
            recent_items = _safe_query_all(conn, """
                SELECT DISTINCT content_item_id FROM review_event
                WHERE user_id = ?
                  AND reviewed_at >= datetime('now', '-14 days')
            """, (user_id,))
            if not recent_items:
                continue

            recent_set = {r["content_item_id"] for r in recent_items}
            optimal_set = set(optimal)

            if not optimal_set:
                continue

            overlap = len(recent_set & optimal_set)
            overlap_pct = overlap / len(optimal_set) * 100

            if overlap_pct < 50:
                findings.append(_finding(
                    "pm", "low",
                    (
                        f"Curriculum drift for user {user_id}: "
                        f"{overlap_pct:.0f}% overlap with optimal path"
                    ),
                    (
                        f"User {user_id} studied {len(recent_set)} items in the last 14 days, "
                        f"but only {overlap} ({overlap_pct:.0f}%) overlap with the "
                        f"Dijkstra-optimal learning path ({len(optimal_set)} items). "
                        f"The learner may be studying suboptimal material."
                    ),
                    (
                        f"Review curriculum recommendations for user {user_id}. "
                        f"Scheduler should prioritize items on the optimal path."
                    ),
                    (
                        f"Curriculum drift for user {user_id} ({overlap_pct:.0f}% overlap).\n\n"
                        f"1. Compare user's recent review_event items with optimal path\n"
                        f"2. Check if scheduler is correctly prioritizing prerequisite items\n"
                        f"3. Consider nudging the learner toward higher-value items"
                    ),
                    "Learning efficiency: suboptimal study order slows progression",
                    ["mandarin/scheduler.py", "mandarin/quality/curriculum_graph.py"],
                ))

        return findings
    except Exception as e:
        logger.debug("Curriculum drift analysis failed: %s", e)
        return []


# ── 7. Viral Health ───────────────────────────────────────────────────────────

def _analyze_viral_health(conn) -> list[dict]:
    """Monitor viral coefficient and referral system activity."""
    try:
        from ..marketing_hooks import compute_viral_coefficient

        viral = compute_viral_coefficient(conn, days=30)
        k_factor = viral.get("k_factor", 0)
        total_users = viral.get("total_users", 0)
        unique_referrers = viral.get("unique_referrers", 0)

        findings = []

        if unique_referrers == 0 and total_users > 5:
            findings.append(_finding(
                "marketing", "low",
                "Referral system inactive: zero referrers in last 30 days",
                (
                    f"Despite {total_users} users in the last 30 days, no one has "
                    f"used the referral system. The referral UX may be undiscoverable "
                    f"or the incentive may be insufficient."
                ),
                (
                    "Improve referral system visibility: add referral prompts after "
                    "milestones, surface referral codes in the dashboard, or add "
                    "referral incentives."
                ),
                (
                    f"Referral system inactive ({total_users} users, 0 referrers).\n\n"
                    f"1. Check if referral code is visible in the dashboard\n"
                    f"2. Add referral prompt after milestone achievements\n"
                    f"3. Consider adding referral incentives (extra content, features)"
                ),
                "Growth: inactive referrals mean zero organic acquisition",
                ["mandarin/marketing_hooks.py", "mandarin/web/templates/dashboard.html"],
            ))
        elif k_factor < 0.1 and total_users > 10:
            findings.append(_finding(
                "marketing", "medium",
                f"Low viral coefficient: k={k_factor:.3f} with {total_users} users",
                (
                    f"Viral k-factor is {k_factor:.3f} over the last 30 days. "
                    f"With {total_users} users and {unique_referrers} active referrers, "
                    f"organic growth is minimal. Sustainable growth typically requires k > 0.3."
                ),
                (
                    "Improve referral conversion: optimize referral landing page, "
                    "add social sharing features, or introduce referral rewards."
                ),
                (
                    f"Low viral coefficient k={k_factor:.3f}.\n\n"
                    f"1. Audit referral funnel: code generation → sharing → signup\n"
                    f"2. Improve referral UX in web/marketing_hooks.py\n"
                    f"3. A/B test referral incentive structures\n"
                    f"4. Target k > 0.3 for meaningful organic growth"
                ),
                "Growth: low virality means acquisition depends entirely on paid channels",
                ["mandarin/marketing_hooks.py", "mandarin/web/marketing_routes.py"],
            ))

        return findings
    except Exception as e:
        logger.debug("Viral health analysis failed: %s", e)
        return []


# ── 8. FMEA Risks ───────────────────────────────────────────────────────────

def _analyze_fmea_risks(conn) -> list[dict]:
    """Emit findings for high-RPN failure modes from FMEA."""
    findings = []
    try:
        from ..quality.fmea import get_critical_fmeas
        critical = get_critical_fmeas(conn, threshold=100)
        for f in critical[:5]:  # Top 5 by RPN
            findings.append(_finding(
                "engineering", "high" if f["rpn"] > 200 else "medium",
                f"FMEA: {f['failure_mode']} (RPN={f['rpn']})",
                f"Process: {f['process']}. Cause: {f.get('cause', '?')}. "
                f"Effect: {f.get('effect', '?')}. "
                f"S={f['severity']} O={f['occurrence']} D={f['detection']}.",
                f"Reduce RPN by improving detection or reducing occurrence. Target RPN < 100.",
                f"Investigate failure mode '{f['failure_mode']}' in {f['process']} and implement controls.",
                "FMEA risk management",
                [],
            ))
    except Exception:
        pass
    return findings


# ── 9. DMAIC Stalls ─────────────────────────────────────────────────────────

def _analyze_dmaic_stalls(conn) -> list[dict]:
    """Emit findings for DMAIC cycles stuck at a tollgate."""
    findings = []
    try:
        stalled = conn.execute("""
            SELECT dimension, gate_blocked, gate_reason, run_at
            FROM pi_dmaic_log
            WHERE gate_blocked IS NOT NULL
            AND run_at >= datetime('now', '-7 days')
            ORDER BY run_at DESC
        """).fetchall()

        seen_dims = set()
        for row in (stalled or []):
            dim = row["dimension"]
            if dim in seen_dims:
                continue
            seen_dims.add(dim)
            findings.append(_finding(
                "pm", "medium",
                f"DMAIC stalled at {row['gate_blocked']} gate for '{dim}'",
                f"DMAIC cycle for dimension '{dim}' is blocked at the {row['gate_blocked']} phase. "
                f"Reason: {row.get('gate_reason', 'unknown')}.",
                f"Address the blocking condition to advance the DMAIC cycle.",
                f"Resolve DMAIC {row['gate_blocked']} gate blocker for dimension '{dim}'.",
                "Six Sigma DMAIC governance",
                [],
            ))
    except Exception:
        pass
    return findings


# ── 10. Post-Improvement Verification Failures ─────────────────────────────

def _analyze_piv_failures(conn) -> list[dict]:
    """Emit findings for post-improvement verifications that failed."""
    findings = []
    try:
        failed = conn.execute("""
            SELECT wo.id, wo.instruction, pf.dimension, pf.title as finding_title
            FROM pi_work_order wo
            JOIN pi_finding pf ON wo.finding_id = pf.id
            WHERE wo.status = 'implemented'
            AND wo.implemented_at <= datetime('now', '-21 days')
            AND wo.id NOT IN (
                SELECT work_order_id FROM prescription_execution_log
                WHERE status IN ('verified', 'succeeded')
            )
        """).fetchall()

        for wo in (failed or [])[:3]:
            findings.append(_finding(
                wo.get("dimension", "engineering"), "high",
                f"Post-improvement verification overdue: {wo.get('finding_title', '?')[:50]}",
                f"Work order #{wo['id']} was implemented 21+ days ago but has not been verified. "
                f"The original issue may not have been resolved.",
                "Re-audit the dimension and verify the improvement actually worked.",
                f"Check if work order #{wo['id']} actually fixed the underlying issue.",
                "Six Sigma Control phase -- post-improvement verification",
                [],
            ))
    except Exception:
        pass
    return findings


# ── Export ────────────────────────────────────────────────────────────────────

ANALYZERS = [
    _analyze_spc_violations,
    _analyze_queue_capacity,
    _analyze_clv_health,
    _analyze_monte_carlo_alerts,
    _analyze_price_experiments,
    _analyze_curriculum_drift,
    _analyze_viral_health,
    _analyze_fmea_risks,
    _analyze_dmaic_stalls,
    _analyze_piv_failures,
]
