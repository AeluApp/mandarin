"""Goodhart health analyzers — detect metric gaming, integrity erosion, and counter-metric failures."""

import json
import logging
import sqlite3

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)

# Thresholds for distortion flags
_SUSPICIOUS_FAST_CRITICAL = 0.20
_SUSPICIOUS_FAST_WARN = 0.10
_EASY_OVERUSE_CRITICAL = 0.80
_EASY_OVERUSE_WARN = 0.60
_RECOGNITION_ONLY_CRITICAL = 0.40
_RECOGNITION_ONLY_WARN = 0.20


# ── Check 1: Product rule violations ────────────────────────────────

# Minimum number of active users (review events in last 30 days) required before
# product-rule alerts are meaningful.  Below this threshold, a single bad session
# from one user can tank every metric — suppress rather than false-alarm.
_MIN_USERS_FOR_ALERT = 10


def check_product_rule_violations(conn):
    """Flag product rule violations from recent counter-metric snapshots."""
    findings = []

    # Guard: insufficient data makes all product-rule metrics unreliable.
    try:
        active_users = _safe_scalar(
            conn,
            "SELECT COUNT(DISTINCT user_id) FROM review_event "
            "WHERE created_at > datetime('now', '-30 days')",
            default=0,
        ) or 0
        if active_users < _MIN_USERS_FOR_ALERT:
            return findings  # Too few users for reliable counter-metrics
    except Exception:
        pass  # If query fails, proceed anyway (schema may differ)

    try:
        # Get the most recent snapshot with alerts
        row = _safe_query(conn,
            "SELECT alerts_json, computed_at FROM counter_metric_snapshot "
            "ORDER BY computed_at DESC LIMIT 1")

        if not row or not row[0]:
            return findings

        alerts_json = row[0]
        computed_at = row[1] if len(row) > 1 else "unknown"

        try:
            alerts = json.loads(alerts_json)
        except (json.JSONDecodeError, TypeError):
            return findings

        if not isinstance(alerts, list):
            return findings

        # Check for critical alerts in last 24 hours
        critical_alerts = [a for a in alerts if a.get("severity") == "critical"]
        warn_alerts = [a for a in alerts if a.get("severity") == "warn"]

        # Also check recent snapshots for product rule violation patterns:
        # delayed recall critically low (Rule 2), transfer accuracy low (Rule 2),
        # progress honesty low (Rule 3)
        recent_critical = _safe_scalar(conn,
            "SELECT COUNT(*) FROM counter_metric_snapshot "
            "WHERE critical_count > 0 "
            "AND computed_at > datetime('now', '-1 day')",
            default=0)

        if critical_alerts or recent_critical > 0:
            alert_names = ", ".join(
                a.get("metric", "unknown") for a in critical_alerts[:5]
            ) if critical_alerts else "see snapshot"
            findings.append(_finding(
                "goodhart", "critical",
                f"Product rule violations detected ({len(critical_alerts)} critical alert(s))",
                f"The most recent counter-metric assessment (at {computed_at}) "
                f"contains {len(critical_alerts)} critical alert(s): {alert_names}. "
                f"Critical alerts indicate fundamental integrity violations — "
                f"features may be optimizing vanity metrics at the expense of "
                f"genuine learning outcomes.",
                "Immediately review counter-metric dashboard. Block any feature "
                "launches until critical alerts are resolved. Check if recent "
                "changes caused the regression.",
                "Query counter_metric_snapshot ORDER BY computed_at DESC. "
                "Parse alerts_json for critical alerts. Cross-reference with "
                "counter_metric_action_log for recent actions taken.",
                "Learning integrity and product rule compliance",
                ["mandarin/counter_metrics.py", "mandarin/counter_metrics_actions.py"],
            ))
        elif warn_alerts:
            alert_names = ", ".join(
                a.get("metric", "unknown") for a in warn_alerts[:5]
            )
            findings.append(_finding(
                "goodhart", "high",
                f"{len(warn_alerts)} counter-metric warning(s) active",
                f"The most recent assessment has {len(warn_alerts)} warning-level "
                f"alert(s): {alert_names}. Warnings indicate early signs of "
                f"metric gaming or integrity erosion that could become critical.",
                "Review warning alerts and ensure automated actions are taking "
                "effect. Monitor trends over the next 48 hours.",
                "Query counter_metric_snapshot for recent alerts_json. "
                "Check counter_metric_action_log for actions already taken.",
                "Early warning for Goodhart drift",
                ["mandarin/counter_metrics.py", "mandarin/counter_metrics_actions.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 2: Unresolved alerts ──────────────────────────────────────

def check_unresolved_alerts(conn):
    """Flag counter-metric alerts older than 7 days without resolution."""
    findings = []
    try:
        # Actions logged more than 7 days ago — check if the same metric
        # still has active alerts (i.e. the action did not resolve it)
        old_actions = _safe_query_all(conn,
            "SELECT DISTINCT metric_name, severity, created_at "
            "FROM counter_metric_action_log "
            "WHERE created_at < datetime('now', '-7 days') "
            "ORDER BY created_at DESC")

        if not old_actions:
            return findings

        # Get the latest snapshot's alerts to see what is still active
        latest = _safe_query(conn,
            "SELECT alerts_json FROM counter_metric_snapshot "
            "ORDER BY computed_at DESC LIMIT 1")

        if not latest or not latest[0]:
            return findings

        try:
            current_alerts = json.loads(latest[0])
        except (json.JSONDecodeError, TypeError):
            return findings

        if not isinstance(current_alerts, list):
            return findings

        current_metric_names = {a.get("metric") for a in current_alerts}

        # Find metrics that had actions 7+ days ago but still have alerts
        unresolved = []
        for row in old_actions:
            metric = row["metric_name"] if isinstance(row, dict) else row[0]
            severity = row["severity"] if isinstance(row, dict) else row[1]
            created = row["created_at"] if isinstance(row, dict) else row[2]
            if metric in current_metric_names:
                unresolved.append((metric, severity, created))

        if not unresolved:
            return findings

        metric_names = ", ".join(f"'{u[0]}'" for u in unresolved[:5])
        findings.append(_finding(
            "goodhart", "high",
            f"{len(unresolved)} counter-metric alert(s) unresolved for 7+ days",
            f"These metrics had automated actions taken 7+ days ago but still "
            f"show active alerts: {metric_names}. Persistent alerts indicate "
            f"that automated interventions are insufficient — the underlying "
            f"issue requires structural changes.",
            "Escalate unresolved alerts for manual review. Evaluate whether "
            "the automated actions are targeting the right root cause. "
            "Consider experiment-based interventions.",
            "Query counter_metric_action_log WHERE created_at < "
            "datetime('now', '-7 days'). Cross-reference with latest "
            "counter_metric_snapshot alerts_json to find still-active alerts.",
            "Counter-metric response effectiveness",
            ["mandarin/counter_metrics_actions.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 3: Progress honesty ───────────────────────────────────────

def check_progress_honesty(conn):
    """Flag low progress honesty — mastery claims not backed by holdout evidence."""
    findings = []
    try:
        row = _safe_query(conn,
            "SELECT outcome_json FROM counter_metric_snapshot "
            "ORDER BY computed_at DESC LIMIT 1")

        if not row or not row[0]:
            return findings

        try:
            outcome = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return findings

        # Navigate to progress_honesty_score.honesty_score
        honesty_data = outcome.get("progress_honesty_score", {})
        if isinstance(honesty_data, dict):
            score = honesty_data.get("honesty_score")
        else:
            score = None

        if score is None:
            return findings

        if score < 50:
            findings.append(_finding(
                "goodhart", "critical",
                f"Progress honesty critically low ({score:.0f}/100)",
                f"The progress honesty score is {score:.0f}/100. This means "
                f"user-visible mastery claims are poorly correlated with actual "
                f"holdout performance. Users are being told they know material "
                f"they cannot demonstrate on unannounced tests — a fundamental "
                f"Goodhart violation.",
                "Audit mastery promotion criteria. Tighten the threshold for "
                "marking items as 'mastered'. Consider demoting items that "
                "fail holdout probes. Prioritize production-type drills.",
                "Query counter_metric_snapshot for outcome_json. Parse "
                "progress_honesty_score. Cross-reference with holdout probe "
                "results by mastery level.",
                "User trust and learning authenticity",
                ["mandarin/counter_metrics.py"],
            ))
        elif score < 70:
            findings.append(_finding(
                "goodhart", "high",
                f"Progress honesty below target ({score:.0f}/100)",
                f"The progress honesty score is {score:.0f}/100 (target: 70+). "
                f"Mastery claims are only weakly correlated with holdout "
                f"performance. Some users may see inflated progress that does "
                f"not reflect genuine retention.",
                "Review mastery promotion criteria. Ensure production drills "
                "are weighted in mastery decisions. Monitor trend over the "
                "next 7 days.",
                "Query counter_metric_snapshot outcome_json for "
                "progress_honesty_score trend over recent snapshots.",
                "User trust and learning authenticity",
                ["mandarin/counter_metrics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 4: Holdout divergence ─────────────────────────────────────

def check_holdout_divergence(conn):
    """Flag low holdout probe accuracy — the ground truth check for real learning."""
    findings = []
    try:
        row = _safe_query(conn,
            "SELECT outcome_json FROM counter_metric_snapshot "
            "ORDER BY computed_at DESC LIMIT 1")

        if not row or not row[0]:
            return findings

        try:
            outcome = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return findings

        holdout_data = outcome.get("holdout_probe_performance", {})
        if isinstance(holdout_data, dict):
            accuracy = holdout_data.get("holdout_accuracy")
            sample = holdout_data.get("sample_size", 0)
        else:
            accuracy = None
            sample = 0

        if accuracy is None or sample < 5:
            return findings  # Not enough holdout data

        if accuracy < 0.40:
            findings.append(_finding(
                "goodhart", "critical",
                f"Holdout accuracy critically low ({accuracy*100:.0f}%)",
                f"Holdout probe accuracy is {accuracy*100:.1f}% (n={sample}). "
                f"Users are performing near or below chance on unannounced "
                f"holdout items. The primary metrics (accuracy, mastery rate) "
                f"are almost certainly inflated — the system is optimizing "
                f"for recognition, not retention.",
                "Freeze mastery promotions. Audit the scheduler for spacing "
                "errors. Increase production drill ratio. Consider a full "
                "mastery demotion sweep for items that fail holdout.",
                "Query counter_metric_snapshot outcome_json for "
                "holdout_probe_performance. Also query counter_metric_holdout "
                "for raw probe results by content item.",
                "Ground truth learning verification",
                ["mandarin/counter_metrics.py", "mandarin/holdout_probes.py"],
            ))
        elif accuracy < 0.55:
            findings.append(_finding(
                "goodhart", "high",
                f"Holdout accuracy below target ({accuracy*100:.0f}%)",
                f"Holdout probe accuracy is {accuracy*100:.1f}% (n={sample}). "
                f"Target is 55%+. Users are struggling on unannounced tests, "
                f"suggesting the primary metrics may overstate actual learning.",
                "Review scheduler spacing intervals. Ensure holdout items "
                "are representative. Increase production drill ratio to "
                "build deeper encoding.",
                "Query counter_metric_holdout for accuracy by modality and "
                "drill_type. Identify which content areas have lowest holdout.",
                "Ground truth learning verification",
                ["mandarin/counter_metrics.py", "mandarin/holdout_probes.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 5: Business integrity ─────────────────────────────────────

def check_business_integrity(conn):
    """Flag high conversion but low retention — a sign of misleading onboarding."""
    findings = []
    try:
        # Count users by subscription tier
        total_users = _safe_scalar(conn,
            "SELECT COUNT(*) FROM user WHERE is_admin = 0 AND is_active = 1",
            default=0)

        if total_users < 10:
            return findings  # Not enough users

        paid_users = _safe_scalar(conn,
            "SELECT COUNT(*) FROM user "
            "WHERE is_admin = 0 AND is_active = 1 "
            "AND subscription_tier = 'paid'",
            default=0)

        conversion_rate = paid_users / total_users if total_users > 0 else 0

        # 30-day retention: users who had a session in the last 30 days
        # among those who had their first session 30+ days ago
        eligible = _safe_scalar(conn,
            "SELECT COUNT(*) FROM user "
            "WHERE is_admin = 0 AND first_session_at IS NOT NULL "
            "AND first_session_at < datetime('now', '-30 days')",
            default=0)

        if eligible < 5:
            return findings  # Not enough mature users

        retained = _safe_scalar(conn,
            "SELECT COUNT(DISTINCT u.id) FROM user u "
            "JOIN session_log s ON s.user_id = u.id "
            "WHERE u.is_admin = 0 "
            "AND u.first_session_at < datetime('now', '-30 days') "
            "AND s.started_at > datetime('now', '-30 days')",
            default=0)

        retention_rate = retained / eligible if eligible > 0 else 0

        if conversion_rate > 0.10 and retention_rate < 0.40:
            findings.append(_finding(
                "goodhart", "high",
                f"High conversion ({conversion_rate*100:.0f}%) but low "
                f"30d retention ({retention_rate*100:.0f}%)",
                f"Conversion rate is {conversion_rate*100:.1f}% "
                f"({paid_users}/{total_users} paid) but 30-day retention is "
                f"only {retention_rate*100:.1f}% ({retained}/{eligible}). "
                f"This pattern suggests the product converts well (possibly "
                f"through early gratification) but fails to deliver lasting "
                f"value — a classic Goodhart symptom where conversion metrics "
                f"are optimized at the expense of genuine learning outcomes.",
                "Audit onboarding for false-progress signals. Check if early "
                "sessions inflate mastery. Review churn reasons. Ensure the "
                "free-to-paid transition is based on demonstrated learning, "
                "not gamified hooks.",
                "Query user for subscription_tier distribution. Query "
                "session_log for 30-day retention by cohort. Cross-reference "
                "with counter_metric_snapshot for learning integrity.",
                "Business model alignment with learning integrity",
                ["mandarin/web/payment_routes.py", "mandarin/counter_metrics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 6: Alert precision ────────────────────────────────────────

def check_alert_precision(conn):
    """Flag if many counter-metric actions are taken but metrics do not improve."""
    findings = []
    try:
        # Count actions in the last 90 days
        action_count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM counter_metric_action_log "
            "WHERE created_at > datetime('now', '-90 days')",
            default=0)

        if action_count < 5:
            return findings  # Not enough actions to evaluate

        # Compare alert counts: 90 days ago vs now
        oldest_snapshot = _safe_query(conn,
            "SELECT alert_count, critical_count FROM counter_metric_snapshot "
            "WHERE computed_at > datetime('now', '-90 days') "
            "ORDER BY computed_at ASC LIMIT 1")

        newest_snapshot = _safe_query(conn,
            "SELECT alert_count, critical_count FROM counter_metric_snapshot "
            "ORDER BY computed_at DESC LIMIT 1")

        if not oldest_snapshot or not newest_snapshot:
            return findings

        old_alerts = oldest_snapshot[0] if oldest_snapshot[0] is not None else 0
        new_alerts = newest_snapshot[0] if newest_snapshot[0] is not None else 0

        # If we have many actions but alert count has not decreased
        if action_count >= 10 and new_alerts >= old_alerts and old_alerts > 0:
            findings.append(_finding(
                "goodhart", "medium",
                f"Alert precision concern: {action_count} actions taken, "
                f"alert count unchanged ({old_alerts} -> {new_alerts})",
                f"{action_count} automated counter-metric actions were taken "
                f"in the last 90 days, but the alert count has not decreased "
                f"(was {old_alerts}, now {new_alerts}). Either the actions are "
                f"not targeting root causes, or new issues are appearing as "
                f"fast as old ones resolve.",
                "Review the action log for repeated actions on the same metric. "
                "If a metric has received 3+ actions without improvement, the "
                "automated intervention is insufficient — manual investigation "
                "is needed.",
                "Query counter_metric_action_log for action_type and "
                "metric_name frequency. Compare with counter_metric_snapshot "
                "alert_count trend.",
                "Counter-metric system effectiveness",
                ["mandarin/counter_metrics_actions.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 7: Action effectiveness ───────────────────────────────────

def check_action_effectiveness(conn):
    """Flag metrics with 3+ actions taken but no improvement."""
    findings = []
    try:
        # Group actions by metric, count per metric
        metric_actions = _safe_query_all(conn,
            "SELECT metric_name, COUNT(*) AS action_cnt, "
            "MIN(created_at) AS first_action, MAX(created_at) AS last_action "
            "FROM counter_metric_action_log "
            "GROUP BY metric_name "
            "HAVING COUNT(*) >= 3 "
            "ORDER BY action_cnt DESC")

        if not metric_actions:
            return findings

        # For each metric with 3+ actions, check if the latest snapshot
        # still has an alert for it
        latest = _safe_query(conn,
            "SELECT alerts_json FROM counter_metric_snapshot "
            "ORDER BY computed_at DESC LIMIT 1")

        if not latest or not latest[0]:
            return findings

        try:
            current_alerts = json.loads(latest[0])
        except (json.JSONDecodeError, TypeError):
            return findings

        if not isinstance(current_alerts, list):
            return findings

        current_metric_names = {a.get("metric") for a in current_alerts}

        ineffective = []
        for row in metric_actions:
            metric = row["metric_name"] if isinstance(row, dict) else row[0]
            count = row["action_cnt"] if isinstance(row, dict) else row[1]
            if metric in current_metric_names:
                ineffective.append((metric, count))

        if not ineffective:
            return findings

        details = ", ".join(
            f"'{m}' ({c} actions)" for m, c in ineffective[:5]
        )
        findings.append(_finding(
            "goodhart", "medium",
            f"{len(ineffective)} metric(s) not improving despite repeated actions",
            f"These metrics have received 3+ automated actions but still show "
            f"active alerts: {details}. Repeated ineffective actions suggest "
            f"the automated response is not addressing the root cause.",
            "For each ineffective metric, review the action types taken and "
            "consider alternative interventions. Propose an A/B test or "
            "manual investigation.",
            "Query counter_metric_action_log GROUP BY metric_name. For "
            "metrics with 3+ actions, check if alerts_json in latest "
            "snapshot still contains them.",
            "Automated intervention effectiveness",
            ["mandarin/counter_metrics_actions.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 8: Gaming flags ───────────────────────────────────────────

def check_gaming_flags(conn):
    """Flag behavioral distortion signals from counter-metric snapshots."""
    findings = []
    try:
        row = _safe_query(conn,
            "SELECT distortion_json FROM counter_metric_snapshot "
            "ORDER BY computed_at DESC LIMIT 1")

        if not row or not row[0]:
            return findings

        try:
            distortion = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return findings

        # Check suspicious fast rate
        latency = distortion.get("answer_latency_suspiciousness", {})
        fast_rate = latency.get("suspicious_fast_rate") if isinstance(latency, dict) else None

        # Check easy overuse
        easy = distortion.get("easy_overuse_collapse", {})
        low_challenge = easy.get("low_challenge_rate") if isinstance(easy, dict) else None

        # Check recognition-only progress
        rec = distortion.get("recognition_only_progress", {})
        rec_rate = rec.get("recognition_only_rate") if isinstance(rec, dict) else None

        critical_flags = []
        warn_flags = []

        if fast_rate is not None:
            if fast_rate >= _SUSPICIOUS_FAST_CRITICAL:
                critical_flags.append(f"suspicious_fast_rate={fast_rate*100:.0f}%")
            elif fast_rate >= _SUSPICIOUS_FAST_WARN:
                warn_flags.append(f"suspicious_fast_rate={fast_rate*100:.0f}%")

        if low_challenge is not None:
            if low_challenge >= _EASY_OVERUSE_CRITICAL:
                critical_flags.append(f"low_challenge_rate={low_challenge*100:.0f}%")
            elif low_challenge >= _EASY_OVERUSE_WARN:
                warn_flags.append(f"low_challenge_rate={low_challenge*100:.0f}%")

        if rec_rate is not None:
            if rec_rate >= _RECOGNITION_ONLY_CRITICAL:
                critical_flags.append(f"recognition_only_rate={rec_rate*100:.0f}%")
            elif rec_rate >= _RECOGNITION_ONLY_WARN:
                warn_flags.append(f"recognition_only_rate={rec_rate*100:.0f}%")

        if critical_flags:
            findings.append(_finding(
                "goodhart", "high",
                f"Gaming flags detected: {len(critical_flags)} critical distortion(s)",
                f"Critical behavioral distortion signals: "
                f"{', '.join(critical_flags)}. These patterns suggest users "
                f"may be gaming the system — answering too fast (random "
                f"clicking), avoiding challenging content, or advancing "
                f"through recognition-only drills without production practice.",
                "Increase production drill ratio. Add minimum response time "
                "validation. Review difficulty distribution in the scheduler. "
                "Ensure mastery requires demonstrated production ability.",
                "Query counter_metric_snapshot distortion_json. Parse "
                "answer_latency_suspiciousness, easy_overuse_collapse, and "
                "recognition_only_progress for threshold violations.",
                "Behavioral integrity and anti-gaming",
                ["mandarin/counter_metrics.py"],
            ))
        elif warn_flags:
            findings.append(_finding(
                "goodhart", "medium",
                f"Early gaming signals: {len(warn_flags)} distortion warning(s)",
                f"Warning-level behavioral distortion signals: "
                f"{', '.join(warn_flags)}. These are early indicators of "
                f"potential gaming behavior that should be monitored.",
                "Monitor distortion trends. If warnings persist for 7+ days, "
                "consider tightening drill selection criteria.",
                "Query counter_metric_snapshot distortion_json for trend "
                "analysis over recent snapshots.",
                "Behavioral integrity early warning",
                ["mandarin/counter_metrics.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 9: Delayed validation failure ─────────────────────────────

def check_delayed_validation_failure(conn):
    """Flag high failure rates on delayed recall validations."""
    findings = []
    try:
        # Count completed delayed validations with 30-day delay
        total = _safe_scalar(conn,
            "SELECT COUNT(*) FROM counter_metric_delayed_validation "
            "WHERE status = 'completed' "
            "AND delay_days >= 30 "
            "AND administered_at > datetime('now', '-90 days')",
            default=0)

        if total < 5:
            return findings  # Not enough data

        failures = _safe_scalar(conn,
            "SELECT COUNT(*) FROM counter_metric_delayed_validation "
            "WHERE status = 'completed' "
            "AND delay_days >= 30 "
            "AND correct = 0 "
            "AND administered_at > datetime('now', '-90 days')",
            default=0)

        failure_rate = failures / total if total > 0 else 0

        if failure_rate > 0.40:
            findings.append(_finding(
                "goodhart", "high",
                f"Delayed validation failure rate critically high "
                f"({failure_rate*100:.0f}%)",
                f"{failures} of {total} delayed validations (30-day delay) "
                f"failed in the last 90 days ({failure_rate*100:.1f}%). "
                f"Users are failing more than 40% of delayed recall tests, "
                f"meaning knowledge marked as 'learned' is not surviving "
                f"long-term — the core Goodhart failure mode.",
                "Tighten mastery criteria to require delayed validation "
                "success. Increase spacing intervals for fragile items. "
                "Consider resetting mastery for items with high delayed "
                "failure rates.",
                "Query counter_metric_delayed_validation WHERE "
                "status='completed' AND delay_days >= 30. Group by "
                "content_item_id to find items with highest failure rates.",
                "Long-term retention integrity",
                ["mandarin/delayed_validation.py", "mandarin/counter_metrics.py"],
            ))
        elif failure_rate > 0.25:
            findings.append(_finding(
                "goodhart", "medium",
                f"Delayed validation failure rate elevated ({failure_rate*100:.0f}%)",
                f"{failures} of {total} delayed validations (30-day delay) "
                f"failed in the last 90 days ({failure_rate*100:.1f}%). "
                f"Target is <25%. Elevated failure rates suggest spacing "
                f"intervals may be too aggressive or mastery thresholds "
                f"too lenient.",
                "Review spacing multipliers for items that fail delayed "
                "validation. Ensure the scheduler respects counter-metric "
                "signals to slow down mastery progression.",
                "Query counter_metric_delayed_validation for failure "
                "patterns. Group by modality and drill_type.",
                "Long-term retention health",
                ["mandarin/delayed_validation.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 10: Meta-honesty ──────────────────────────────────────────

def check_meta_honesty(conn):
    """Flag if the counter-metric system itself may be missing problems."""
    findings = []
    try:
        # Check if there are active users
        active_users = _safe_scalar(conn,
            "SELECT COUNT(*) FROM user "
            "WHERE is_admin = 0 AND first_session_at IS NOT NULL "
            "AND first_session_at > datetime('now', '-90 days')",
            default=0)

        if active_users < 3:
            return findings  # Not enough active users to worry about

        # Check if alert_count has been 0 for 30+ consecutive days
        # by looking at snapshots from the last 30 days
        snapshots_last_30d = _safe_scalar(conn,
            "SELECT COUNT(*) FROM counter_metric_snapshot "
            "WHERE computed_at > datetime('now', '-30 days')",
            default=0)

        if snapshots_last_30d == 0:
            # No snapshots at all — that is itself a problem
            findings.append(_finding(
                "goodhart", "medium",
                "No counter-metric snapshots in 30 days",
                f"There are {active_users} active user(s) but no "
                f"counter-metric assessments have been recorded in the last "
                f"30 days. Without counter-metrics, the system has no way to "
                f"detect Goodhart drift — primary metrics could be optimized "
                f"without any integrity check.",
                "Ensure the counter-metric scheduler is running. Check "
                "counter_metrics_scheduler.py for errors. Run a manual "
                "assessment.",
                "Check if counter_metric_snapshot has any recent rows. "
                "If not, investigate why the scheduler is not running.",
                "Counter-metric system availability",
                ["mandarin/web/counter_metrics_scheduler.py"],
            ))
            return findings

        # Count snapshots in last 30 days with zero alerts
        zero_alert_count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM counter_metric_snapshot "
            "WHERE computed_at > datetime('now', '-30 days') "
            "AND alert_count = 0",
            default=0)

        # If ALL snapshots in last 30 days show zero alerts, that is suspicious
        if zero_alert_count == snapshots_last_30d and snapshots_last_30d >= 4:
            findings.append(_finding(
                "goodhart", "medium",
                f"Counter-metrics report zero alerts for 30+ days "
                f"({snapshots_last_30d} clean snapshots)",
                f"All {snapshots_last_30d} counter-metric snapshots in the "
                f"last 30 days show alert_count=0, despite {active_users} "
                f"active user(s). While this could mean everything is "
                f"genuinely healthy, it could also mean the alerting "
                f"thresholds are too lenient, holdout probes are not running, "
                f"or the system is not collecting enough data to trigger "
                f"alerts.",
                "Audit counter-metric thresholds. Verify holdout probes are "
                "being administered. Check if delayed validations are "
                "scheduled and completing. Run a manual assessment with "
                "tighter thresholds to sanity-check.",
                "Query counter_metric_snapshot WHERE computed_at > "
                "datetime('now', '-30 days') and verify alert_count. "
                "Check counter_metric_holdout and "
                "counter_metric_delayed_validation for recent activity.",
                "Counter-metric system integrity (meta-level)",
                ["mandarin/counter_metrics.py", "mandarin/web/counter_metrics_scheduler.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Analyzer registry ────────────────────────────────────────────────

ANALYZERS = [
    check_product_rule_violations,
    check_unresolved_alerts,
    check_progress_honesty,
    check_holdout_divergence,
    check_business_integrity,
    check_alert_precision,
    check_action_effectiveness,
    check_gaming_flags,
    check_delayed_validation_failure,
    check_meta_honesty,
]
