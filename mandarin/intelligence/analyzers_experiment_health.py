"""Experiment health analyzers — monitor SRM, overdue experiments, guardrails, power, collisions, and more."""

import logging
import sqlite3

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Check 1: SRM detected ──────────────────────────────────────────

def check_srm_detected(conn):
    """Flag running experiments where a sample ratio mismatch (SRM) check has failed."""
    findings = []
    try:
        running = _safe_query_all(conn,
            "SELECT id, name FROM experiment "
            "WHERE status = 'running'")

        if not running:
            return findings

        for row in running:
            exp_id = row["id"] if isinstance(row, dict) else row[0]
            exp_name = row["name"] if isinstance(row, dict) else row[1]

            failed = _safe_scalar(conn,
                "SELECT COUNT(*) FROM experiment_balance_check "
                "WHERE experiment_id = ? AND passed = 0",
                (exp_id,), default=0)

            if failed > 0:
                findings.append(_finding(
                    "experimentation", "critical",
                    f"SRM detected in experiment '{exp_name}'",
                    f"Experiment '{exp_name}' has {failed} failed sample ratio "
                    f"mismatch (SRM) check(s). SRM indicates the randomization "
                    f"unit assignment is biased — treatment and control groups "
                    f"are not balanced. Any causal conclusions from this "
                    f"experiment are invalid.",
                    f"Pause experiment '{exp_name}' immediately. Investigate "
                    f"the assignment mechanism for bugs (bot traffic filtering, "
                    f"redirect loops, conditional loading). Do not draw "
                    f"conclusions until the imbalance is resolved.",
                    f"Query experiment_balance_check WHERE experiment_id={exp_id} "
                    f"AND passed=0. Inspect the assignment counts per variant "
                    f"and identify the source of the imbalance.",
                    "Experiment validity and causal inference integrity",
                    ["mandarin/intelligence/analyzers_experiment_health.py"],
                ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 2: Overdue experiments ────────────────────────────────────

def check_overdue_experiments(conn):
    """Flag running experiments that have exceeded 2x their outcome window."""
    findings = []
    try:
        overdue = _safe_query_all(conn,
            "SELECT id, name, started_at, outcome_window_days, "
            "julianday('now') - julianday(started_at) AS elapsed_days "
            "FROM experiment "
            "WHERE status = 'running' "
            "AND started_at IS NOT NULL "
            "AND outcome_window_days IS NOT NULL "
            "AND julianday('now') - julianday(started_at) > outcome_window_days * 2")

        if not overdue:
            return findings

        items = []
        for row in overdue:
            if isinstance(row, dict):
                name = row.get("name", f"experiment {row.get('id', '?')}")
                elapsed = row.get("elapsed_days", 0)
                window = row.get("outcome_window_days", 0)
            else:
                name = row[1] if len(row) > 1 else f"experiment {row[0]}"
                elapsed = row[4] if len(row) > 4 else 0
                window = row[3] if len(row) > 3 else 0
            items.append((name, elapsed, window))

        names = ", ".join(
            f"'{n}' ({e:.0f}d elapsed, {w}d window)"
            for n, e, w in items[:5]
        )
        findings.append(_finding(
            "experimentation", "high",
            f"{len(items)} experiment(s) overdue (>2x outcome window)",
            f"These experiments have been running more than twice their "
            f"outcome window: {names}. Overdue experiments waste traffic, "
            f"increase collision risk, and delay learning. If the experiment "
            f"has not reached significance by 2x the window, it likely never "
            f"will at the current effect size.",
            "Conclude or stop overdue experiments. If the effect size is too "
            "small to detect, consider redesigning with a larger expected "
            "effect or increasing sample size for a future iteration.",
            "Query experiment WHERE status='running' and elapsed > "
            "outcome_window_days * 2. For each, check if bayesian or "
            "frequentist analysis shows any signal.",
            "Experiment throughput and resource efficiency",
            ["mandarin/intelligence/analyzers_experiment_health.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 3: Guardrail degradation ─────────────────────────────────

def check_guardrail_degradation(conn):
    """Flag recent guardrail violations from andon events or experiment audit logs."""
    findings = []
    try:
        # Check andon_events for guardrail-related entries
        andon_count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM andon_event "
            "WHERE event_type LIKE '%guardrail%' "
            "AND created_at > datetime('now', '-7 days')",
            default=0)

        # Check experiment_audit_log for guardrail check failures
        audit_count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM experiment_audit_log "
            "WHERE event_type = 'guardrail_check' "
            "AND outcome = 'degradation' "
            "AND created_at > datetime('now', '-7 days')",
            default=0)

        total = andon_count + audit_count

        if total > 0:
            findings.append(_finding(
                "experimentation", "high",
                f"{total} guardrail degradation event(s) in the last 7 days",
                f"Detected {andon_count} andon event(s) and {audit_count} "
                f"audit log entries indicating guardrail degradation in the "
                f"last 7 days. Guardrail metrics (error rates, latency, "
                f"completion rates) are designed to catch experiments that "
                f"harm the user experience even if they improve the primary "
                f"metric.",
                "Review the flagged experiments and consider pausing any that "
                "triggered guardrail violations. Investigate whether the "
                "degradation is transient or structural before resuming.",
                "Query andon_event WHERE event_type LIKE '%guardrail%' and "
                "experiment_audit_log WHERE event_type='guardrail_check' AND "
                "outcome='degradation'. Identify the experiments involved and "
                "the specific guardrail metrics that degraded.",
                "User experience protection during experimentation",
                ["mandarin/intelligence/analyzers_experiment_health.py",
                 "mandarin/web/andon.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 4: Underpowered experiments ──────────────────────────────

def check_underpowered(conn):
    """Flag running experiments that are behind on enrollment relative to elapsed time."""
    findings = []
    try:
        running = _safe_query_all(conn,
            "SELECT e.id, e.name, e.min_sample_size, e.outcome_window_days, "
            "e.started_at, "
            "julianday('now') - julianday(e.started_at) AS elapsed_days, "
            "COUNT(a.id) AS assignment_count "
            "FROM experiment e "
            "LEFT JOIN experiment_assignment a ON a.experiment_id = e.id "
            "WHERE e.status = 'running' "
            "AND e.started_at IS NOT NULL "
            "AND e.min_sample_size IS NOT NULL "
            "AND e.outcome_window_days IS NOT NULL "
            "GROUP BY e.id "
            "HAVING elapsed_days > e.outcome_window_days * 0.5 "
            "AND assignment_count < e.min_sample_size * 0.5")

        if not running:
            return findings

        items = []
        for row in running:
            if isinstance(row, dict):
                name = row.get("name", f"experiment {row.get('id', '?')}")
                assigned = row.get("assignment_count", 0)
                needed = row.get("min_sample_size", 0)
                elapsed = row.get("elapsed_days", 0)
                window = row.get("outcome_window_days", 0)
            else:
                name = row[1] if len(row) > 1 else f"experiment {row[0]}"
                needed = row[2] if len(row) > 2 else 0
                window = row[3] if len(row) > 3 else 0
                elapsed = row[5] if len(row) > 5 else 0
                assigned = row[6] if len(row) > 6 else 0
            items.append((name, assigned, needed, elapsed, window))

        names = ", ".join(
            f"'{n}' ({a}/{s} assigned, {e:.0f}d/{w}d elapsed)"
            for n, a, s, e, w in items[:5]
        )
        findings.append(_finding(
            "experimentation", "medium",
            f"{len(items)} experiment(s) underpowered at midpoint",
            f"These experiments are past half their outcome window but have "
            f"less than half the required sample size: {names}. At this "
            f"enrollment rate, they will not reach statistical significance "
            f"within the planned window.",
            "Consider extending the outcome window, increasing traffic "
            "allocation, or narrowing the target population to increase "
            "enrollment density. If the feature has low reach, reconsider "
            "whether an experiment is the right evaluation method.",
            "Query experiment with assignment counts and elapsed time. "
            "For underpowered experiments, estimate the enrollment rate "
            "needed to reach min_sample_size by the deadline.",
            "Statistical power and experiment conclusiveness",
            ["mandarin/intelligence/analyzers_experiment_health.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 5: Counter metric degradation ────────────────────────────

def check_counter_metric_degradation(conn):
    """Flag running experiments where counter metric snapshots show declining health."""
    findings = []
    try:
        running = _safe_query_all(conn,
            "SELECT id, name FROM experiment "
            "WHERE status = 'running'")

        if not running:
            return findings

        degraded = []
        for row in running:
            exp_id = row["id"] if isinstance(row, dict) else row[0]
            exp_name = row["name"] if isinstance(row, dict) else row[1]

            # Get the most recent counter metric snapshot
            snapshot = _safe_query(conn,
                "SELECT overall_health, created_at "
                "FROM counter_metric_snapshot "
                "WHERE experiment_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (exp_id,))

            if snapshot is None:
                continue

            health = snapshot["overall_health"] if isinstance(snapshot, dict) else snapshot[0]

            if health is not None and health < 0:
                degraded.append((exp_name, health))

        if degraded:
            names = ", ".join(
                f"'{n}' (health={h:.2f})" for n, h in degraded[:5]
            )
            findings.append(_finding(
                "experimentation", "high",
                f"{len(degraded)} experiment(s) showing counter metric degradation",
                f"These experiments have negative overall_health in their most "
                f"recent counter metric snapshot: {names}. Counter metrics "
                f"protect against optimizing one metric at the expense of "
                f"others. Declining counter metrics suggest the treatment is "
                f"causing unintended harm.",
                "Review the specific counter metrics that are declining. "
                "Consider pausing the experiment if the degradation is "
                "meaningful. Evaluate whether the primary metric gain "
                "justifies the counter metric cost.",
                "Query counter_metric_snapshot for the flagged experiments. "
                "Break down overall_health into individual counter metrics "
                "to identify which ones are degrading.",
                "Holistic experiment evaluation (primary + counter metrics)",
                ["mandarin/intelligence/analyzers_experiment_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 6: Experiment collisions ─────────────────────────────────

def check_experiment_collisions(conn):
    """Flag pairs of running experiments with >30% user overlap."""
    findings = []
    try:
        running = _safe_query_all(conn,
            "SELECT id, name FROM experiment "
            "WHERE status = 'running'")

        if not running or len(running) < 2:
            return findings

        experiments = []
        for row in running:
            exp_id = row["id"] if isinstance(row, dict) else row[0]
            exp_name = row["name"] if isinstance(row, dict) else row[1]
            experiments.append((exp_id, exp_name))

        collisions = []
        for i in range(len(experiments)):
            for j in range(i + 1, len(experiments)):
                id_a, name_a = experiments[i]
                id_b, name_b = experiments[j]

                # Count users in both experiments
                overlap = _safe_scalar(conn,
                    "SELECT COUNT(DISTINCT a1.user_id) "
                    "FROM experiment_assignment a1 "
                    "INNER JOIN experiment_assignment a2 "
                    "ON a1.user_id = a2.user_id "
                    "WHERE a1.experiment_id = ? AND a2.experiment_id = ?",
                    (id_a, id_b), default=0)

                # Count users in each experiment
                count_a = _safe_scalar(conn,
                    "SELECT COUNT(DISTINCT user_id) "
                    "FROM experiment_assignment "
                    "WHERE experiment_id = ?",
                    (id_a,), default=0)
                count_b = _safe_scalar(conn,
                    "SELECT COUNT(DISTINCT user_id) "
                    "FROM experiment_assignment "
                    "WHERE experiment_id = ?",
                    (id_b,), default=0)

                min_count = min(count_a, count_b)
                if min_count > 0 and overlap / min_count > 0.30:
                    pct = (overlap / min_count) * 100
                    collisions.append((name_a, name_b, pct))

        if collisions:
            pairs = ", ".join(
                f"'{a}' + '{b}' ({p:.0f}% overlap)"
                for a, b, p in collisions[:5]
            )
            findings.append(_finding(
                "experimentation", "medium",
                f"{len(collisions)} experiment collision(s) detected (>30% overlap)",
                f"These experiment pairs share more than 30% of their users: "
                f"{pairs}. High overlap means treatment effects can interact, "
                f"making it impossible to attribute observed changes to a "
                f"single experiment. This violates the independence assumption "
                f"of most statistical tests.",
                "Use mutual exclusion layers or sequential testing to prevent "
                "collisions. If experiments must run concurrently, use "
                "interaction analysis to check for confounding.",
                "Query experiment_assignment to compute user overlap between "
                "all running experiment pairs. For colliding pairs, assess "
                "whether the treatments could interact.",
                "Experiment isolation and causal attribution",
                ["mandarin/intelligence/analyzers_experiment_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 7: Stale proposals ───────────────────────────────────────

def check_stale_proposals(conn):
    """Flag experiment proposals that have been pending for more than 30 days."""
    findings = []
    try:
        stale_count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM experiment_proposal "
            "WHERE status = 'pending' "
            "AND created_at < datetime('now', '-30 days')",
            default=0)

        if stale_count == 0:
            return findings

        stale = _safe_query_all(conn,
            "SELECT id, title, created_at, "
            "julianday('now') - julianday(created_at) AS age_days "
            "FROM experiment_proposal "
            "WHERE status = 'pending' "
            "AND created_at < datetime('now', '-30 days') "
            "ORDER BY created_at ASC LIMIT 10")

        items = []
        for row in (stale or []):
            if isinstance(row, dict):
                title = row.get("title", f"proposal {row.get('id', '?')}")
                age = row.get("age_days", 0)
            else:
                title = row[1] if len(row) > 1 else f"proposal {row[0]}"
                age = row[3] if len(row) > 3 else 0
            items.append((title, age))

        names = ", ".join(
            f"'{t}' ({a:.0f}d old)" for t, a in items[:5]
        )
        findings.append(_finding(
            "experimentation", "low",
            f"{stale_count} experiment proposal(s) pending for 30+ days",
            f"These proposals have been pending review for over 30 days: "
            f"{names}. Stale proposals indicate a decision bottleneck — "
            f"ideas are being generated but not evaluated, which wastes "
            f"the effort of proposal creation and delays learning.",
            "Review or reject stale proposals. Establish a weekly cadence "
            "for proposal triage to prevent future accumulation.",
            "Query experiment_proposal WHERE status='pending' and age > 30 "
            "days. For each, summarize the hypothesis and recommend "
            "approve, modify, or reject.",
            "Experiment velocity and decision throughput",
            ["mandarin/intelligence/analyzers_experiment_health.py",
             "mandarin/intelligence/experiment_proposer.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 8: No Bayesian analysis ──────────────────────────────────

def check_no_bayesian_analysis(conn):
    """Flag recently concluded experiments that have no Bayesian analysis results."""
    findings = []
    try:
        # Concluded experiments in the last 90 days
        concluded = _safe_query_all(conn,
            "SELECT id, name FROM experiment "
            "WHERE status IN ('concluded', 'completed', 'stopped') "
            "AND concluded_at > datetime('now', '-90 days')")

        if not concluded:
            return findings

        missing = []
        for row in concluded:
            exp_id = row["id"] if isinstance(row, dict) else row[0]
            exp_name = row["name"] if isinstance(row, dict) else row[1]

            has_bayesian = _safe_scalar(conn,
                "SELECT COUNT(*) FROM experiment_bayesian_result "
                "WHERE experiment_id = ?",
                (exp_id,), default=0)

            if has_bayesian == 0:
                missing.append(exp_name)

        if missing:
            names = ", ".join(f"'{n}'" for n in missing[:5])
            extra = f" (and {len(missing) - 5} more)" if len(missing) > 5 else ""
            findings.append(_finding(
                "experimentation", "low",
                f"{len(missing)} concluded experiment(s) lack Bayesian analysis",
                f"These recently concluded experiments have no Bayesian "
                f"results stored: {names}{extra}. Bayesian analysis provides "
                f"probability-of-being-best and expected loss estimates that "
                f"complement frequentist p-values. This is informational — "
                f"the Bayesian analysis module is relatively new.",
                "Run Bayesian analysis retroactively on concluded experiments "
                "that have sufficient data. Consider making Bayesian analysis "
                "a standard part of the experiment conclusion workflow.",
                "Query experiment WHERE status IN ('concluded','completed',"
                "'stopped') and check for matching rows in "
                "experiment_bayesian_result. Run bayesian.py for any gaps.",
                "Decision quality (complementary statistical methods)",
                ["mandarin/intelligence/analyzers_experiment_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 9: No active email experiments ───────────────────────────

def check_no_active_email_experiments(conn):
    """Flag if emails are being sent but no email-related experiments are running."""
    findings = []
    try:
        recent_sends = _safe_scalar(conn,
            "SELECT COUNT(*) FROM email_send_log "
            "WHERE sent_at > datetime('now', '-30 days')",
            default=0)

        if recent_sends < 10:
            return findings  # Not enough email volume

        email_experiments = _safe_scalar(conn,
            "SELECT COUNT(*) FROM experiment "
            "WHERE status = 'running' "
            "AND (name LIKE '%email%' OR name LIKE '%Email%' "
            "OR name LIKE '%mail%')",
            default=0)

        if email_experiments == 0:
            findings.append(_finding(
                "experimentation", "low",
                f"No active email experiments ({recent_sends} emails sent in 30d)",
                f"The platform sent {recent_sends} emails in the last 30 days "
                f"but no running experiments target email as a channel. Email "
                f"is a high-leverage touchpoint for re-engagement and "
                f"retention — subject lines, send timing, and content are all "
                f"experimentable.",
                "Consider proposing an email experiment: subject line A/B "
                "test, send-time optimization, or content personalization. "
                "Use the experiment proposer to generate a hypothesis.",
                "Query email_send_log for recent volume and experiment for "
                "email-related running experiments. Propose an email "
                "experiment using experiment_proposer.py.",
                "Experimentation coverage across channels",
                ["mandarin/intelligence/analyzers_experiment_health.py",
                 "mandarin/intelligence/experiment_proposer.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 10: Holdout divergence ───────────────────────────────────

def check_holdout_divergence(conn):
    """Compare holdout users' session metrics vs non-holdout to detect divergence."""
    findings = []
    try:
        # Get holdout user completion rate
        holdout_completion = _safe_query(conn,
            "SELECT "
            "COUNT(CASE WHEN sl.completed = 1 THEN 1 END) AS completed, "
            "COUNT(*) AS total "
            "FROM session_log sl "
            "INNER JOIN experiment_holdout eh ON sl.user_id = eh.user_id "
            "WHERE sl.started_at > datetime('now', '-30 days')")

        if holdout_completion is None:
            return findings

        if isinstance(holdout_completion, dict):
            h_completed = holdout_completion.get("completed", 0)
            h_total = holdout_completion.get("total", 0)
        else:
            h_completed = holdout_completion[0] if holdout_completion[0] is not None else 0
            h_total = holdout_completion[1] if len(holdout_completion) > 1 and holdout_completion[1] is not None else 0

        if h_total < 10:
            return findings  # Not enough holdout data

        # Get non-holdout user completion rate
        non_holdout_completion = _safe_query(conn,
            "SELECT "
            "COUNT(CASE WHEN sl.completed = 1 THEN 1 END) AS completed, "
            "COUNT(*) AS total "
            "FROM session_log sl "
            "WHERE sl.user_id NOT IN (SELECT user_id FROM experiment_holdout) "
            "AND sl.started_at > datetime('now', '-30 days')")

        if non_holdout_completion is None:
            return findings

        if isinstance(non_holdout_completion, dict):
            nh_completed = non_holdout_completion.get("completed", 0)
            nh_total = non_holdout_completion.get("total", 0)
        else:
            nh_completed = non_holdout_completion[0] if non_holdout_completion[0] is not None else 0
            nh_total = non_holdout_completion[1] if len(non_holdout_completion) > 1 and non_holdout_completion[1] is not None else 0

        if nh_total < 10:
            return findings  # Not enough non-holdout data

        holdout_rate = h_completed / h_total
        non_holdout_rate = nh_completed / nh_total

        # Flag if difference exceeds 15 percentage points
        diff = abs(non_holdout_rate - holdout_rate) * 100
        if diff > 15:
            direction = "higher" if non_holdout_rate > holdout_rate else "lower"
            findings.append(_finding(
                "experimentation", "medium",
                f"Holdout divergence: {diff:.0f}pp completion rate gap",
                f"Non-holdout users have a {direction} session completion "
                f"rate than holdout users ({non_holdout_rate*100:.1f}% vs "
                f"{holdout_rate*100:.1f}%, {diff:.1f}pp gap). A large "
                f"holdout divergence suggests that the cumulative effect of "
                f"shipped experiments is meaningfully changing user behavior "
                f"— for {'better' if non_holdout_rate > holdout_rate else 'worse'}.",
                "If non-holdout is better: the experimentation program is "
                "delivering value — consider refreshing the holdout group. "
                "If worse: investigate which shipped experiments may have "
                "had negative long-term effects despite short-term wins.",
                "Compare session_log completion rates between users in "
                "experiment_holdout and those not in holdout. Break down "
                "by time period to identify when the divergence started.",
                "Cumulative experimentation impact measurement",
                ["mandarin/intelligence/analyzers_experiment_health.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Analyzer registry ──────────────────────────────────────────────

ANALYZERS = [
    check_srm_detected,
    check_overdue_experiments,
    check_guardrail_degradation,
    check_underpowered,
    check_counter_metric_degradation,
    check_experiment_collisions,
    check_stale_proposals,
    check_no_bayesian_analysis,
    check_no_active_email_experiments,
    check_holdout_divergence,
]
