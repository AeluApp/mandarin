"""Runtime health analyzers — detect runtime issues from local data.

Works from local database tables (error_log, request_timing, webhook_event,
etc.) without requiring Sentry API access. Run daily as part of the product
audit cycle.

Exports:
    ANALYZERS: list of analyzer functions
"""

import json
import logging
import os
import re
import sqlite3

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 1. Error log spike detection ─────────────────────────────────────────

def _check_error_log_spikes(conn):
    """Query the local error_log table for error count trends.

    If today's count > 2x the 7-day average, create a finding.
    """
    findings = []

    # Today's error count
    today_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM error_log
        WHERE created_at >= datetime('now', '-1 day')
    """, default=0)

    # 7-day average (excluding today)
    avg_row = _safe_query(conn, """
        SELECT COUNT(*) * 1.0 / 7 as daily_avg FROM error_log
        WHERE created_at >= datetime('now', '-8 days')
          AND created_at < datetime('now', '-1 day')
    """)
    daily_avg = (avg_row["daily_avg"] or 0) if avg_row else 0

    if daily_avg > 0 and today_count > daily_avg * 2:
        spike_ratio = today_count / daily_avg

        # Check which error types are spiking
        top_errors = _safe_query_all(conn, """
            SELECT error_type, COUNT(*) as cnt
            FROM error_log
            WHERE created_at >= datetime('now', '-1 day')
            GROUP BY error_type
            ORDER BY cnt DESC
            LIMIT 5
        """) or []
        error_summary = ", ".join(
            f"{r['error_type']} ({r['cnt']})" for r in top_errors
        ) if top_errors else "unknown types"

        severity = "critical" if spike_ratio > 5 else "high" if spike_ratio > 3 else "medium"

        findings.append(_finding(
            "runtime_health", severity,
            f"Error log spike: {today_count} errors today ({spike_ratio:.1f}x above average)",
            f"Today's error count ({today_count}) is {spike_ratio:.1f}x the 7-day "
            f"average ({daily_avg:.1f}/day). Top error types: {error_summary}.",
            "Investigate the top error types and recent deployments that may have introduced regressions.",
            f"Investigate error spike: {today_count} errors today vs {daily_avg:.1f} average. "
            f"Top types: {error_summary}. Check recent commits for regressions.",
            "Application reliability",
            [],
        ))

    return findings


# ── 2. Slow endpoint detection ───────────────────────────────────────────

def _check_slow_endpoints(conn):
    """Query request_timing for response times > 2 seconds.

    Flag endpoints that are consistently slow.
    """
    findings = []

    slow_endpoints = _safe_query_all(conn, """
        SELECT endpoint, COUNT(*) as cnt,
               AVG(duration_ms) as avg_ms,
               MAX(duration_ms) as max_ms,
               MIN(duration_ms) as min_ms
        FROM request_timing
        WHERE recorded_at >= datetime('now', '-7 days')
          AND duration_ms > 2000
        GROUP BY endpoint
        HAVING cnt >= 3
        ORDER BY avg_ms DESC
        LIMIT 10
    """) or []

    for ep in slow_endpoints:
        endpoint = ep["endpoint"] or "unknown"
        avg_ms = ep["avg_ms"] or 0
        max_ms = ep["max_ms"] or 0
        count = ep["cnt"] or 0

        severity = "high" if avg_ms > 5000 else "medium"

        findings.append(_finding(
            "runtime_health", severity,
            f"Slow endpoint: {endpoint} (avg {avg_ms:.0f}ms, {count} slow requests)",
            f"Endpoint '{endpoint}' has {count} requests exceeding 2s in the last 7 days. "
            f"Average: {avg_ms:.0f}ms, max: {max_ms:.0f}ms.",
            f"Profile {endpoint} for database queries, external API calls, or computation bottlenecks.",
            f"Profile and optimize slow endpoint '{endpoint}'. "
            f"Average response time: {avg_ms:.0f}ms. "
            f"Check for N+1 queries, missing indexes, or expensive computations.",
            "Performance",
            [],
        ))

    return findings


# ── 3. Failed webhook detection ──────────────────────────────────────────

def _check_failed_webhooks(conn):
    """Check webhook_event table for failed/missing webhook processing."""
    findings = []

    # Count failed webhooks in last 7 days
    failed_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM webhook_event
        WHERE created_at >= datetime('now', '-7 days')
          AND (status = 'failed' OR status = 'error')
    """, default=0)

    total_count = _safe_scalar(conn, """
        SELECT COUNT(*) FROM webhook_event
        WHERE created_at >= datetime('now', '-7 days')
    """, default=0)

    if failed_count > 0 and total_count > 0:
        failure_rate = failed_count / total_count

        if failure_rate > 0.1 or failed_count > 10:
            # Get details of failed webhook types
            failed_types = _safe_query_all(conn, """
                SELECT event_type, COUNT(*) as cnt
                FROM webhook_event
                WHERE created_at >= datetime('now', '-7 days')
                  AND (status = 'failed' OR status = 'error')
                GROUP BY event_type
                ORDER BY cnt DESC
                LIMIT 5
            """) or []
            type_summary = ", ".join(
                f"{r['event_type']} ({r['cnt']})" for r in failed_types
            ) if failed_types else "unknown types"

            severity = "critical" if failure_rate > 0.5 else "high" if failure_rate > 0.2 else "medium"

            findings.append(_finding(
                "runtime_health", severity,
                f"Webhook failures: {failed_count}/{total_count} failed ({failure_rate:.0%})",
                f"{failed_count} of {total_count} webhooks failed in the last 7 days "
                f"({failure_rate:.0%} failure rate). Failed types: {type_summary}.",
                "Check webhook handler error logs. Verify endpoint URLs and authentication. "
                "Consider adding retry logic for transient failures.",
                f"Investigate {failed_count} webhook failures. Types: {type_summary}. "
                f"Check handler code and external service connectivity.",
                "Payment/service reliability",
                ["mandarin/web/payment_routes.py"],
            ))

    return findings


# ── 4. Scheduled job failure detection ───────────────────────────────────

def _check_job_failures(conn):
    """Check if scheduled jobs (quality_scheduler, etc.) have failed recently."""
    findings = []

    # Check scheduler_lock for stale locks (indicating a crash during execution)
    stale_locks = _safe_query_all(conn, """
        SELECT lock_name, acquired_at, ttl_seconds
        FROM scheduler_lock
        WHERE released_at IS NULL
          AND datetime(acquired_at, '+' || ttl_seconds || ' seconds') < datetime('now')
    """) or []

    for lock in stale_locks:
        lock_name = lock["lock_name"] or "unknown"
        acquired_at = lock["acquired_at"] or "unknown"

        findings.append(_finding(
            "runtime_health", "high",
            f"Stale scheduler lock: {lock_name} (acquired {acquired_at})",
            f"Scheduler lock '{lock_name}' was acquired at {acquired_at} and never released. "
            f"This indicates the scheduled job crashed or hung during execution.",
            f"Check logs for {lock_name} crashes. Release the stale lock and investigate root cause.",
            f"Investigate stale scheduler lock for '{lock_name}'. "
            f"Check application logs for crash stacktraces around {acquired_at}.",
            "Background job reliability",
            [],
        ))

    # Check for quality_metric gaps (no recent entries = scheduler not running)
    latest_metric = _safe_query(conn, """
        SELECT MAX(recorded_at) as latest FROM quality_metric
    """)
    if latest_metric and latest_metric["latest"]:
        # Check if more than 2 days since last metric collection
        gap_check = _safe_scalar(conn, """
            SELECT julianday('now') - julianday(?) as gap_days
        """, (latest_metric["latest"],), default=0)
        if gap_check and gap_check > 2:
            findings.append(_finding(
                "runtime_health", "high",
                f"Quality metrics gap: no collection for {gap_check:.1f} days",
                f"Last quality metric was recorded at {latest_metric['latest']}. "
                f"The quality_scheduler may not be running.",
                "Check if the application process is running and the quality_scheduler thread is alive.",
                "Check quality_scheduler health. Last metric collection: "
                f"{latest_metric['latest']}. Verify the background thread is running.",
                "Monitoring health",
                ["mandarin/web/quality_scheduler.py"],
            ))

    return findings


# ── 5. Database health check ─────────────────────────────────────────────

def _check_database_health(conn):
    """Run PRAGMA integrity_check and check database size growth rate."""
    findings = []

    # Integrity check
    try:
        result = conn.execute("PRAGMA integrity_check(1)").fetchone()
        if result and result[0] != "ok":
            findings.append(_finding(
                "runtime_health", "critical",
                "Database integrity check failed",
                f"PRAGMA integrity_check returned: {result[0]}. "
                f"The database may be corrupted.",
                "Back up the database immediately. Run full integrity check and consider "
                "restoring from a known-good backup.",
                "URGENT: Database integrity check failed. Back up data/mandarin.db immediately "
                "and investigate corruption.",
                "Data integrity",
                ["data/mandarin.db"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Database integrity check failed: %s", exc)

    # Check database page count growth (proxy for size growth)
    try:
        page_count = conn.execute("PRAGMA page_count").fetchone()
        page_size = conn.execute("PRAGMA page_size").fetchone()
        if page_count and page_size:
            db_size_mb = (page_count[0] * page_size[0]) / (1024 * 1024)
            if db_size_mb > 500:
                findings.append(_finding(
                    "runtime_health", "medium",
                    f"Database size: {db_size_mb:.0f} MB",
                    f"The database has grown to {db_size_mb:.0f} MB. "
                    f"Large databases may slow down queries and backups.",
                    "Consider archiving old data, running VACUUM, or implementing data retention policies.",
                    "Review database size ({:.0f} MB). Consider archiving old session_log, "
                    "review_event, and request_timing records.".format(db_size_mb),
                    "Infrastructure",
                    ["schema.sql"],
                ))

        # Check for excessive WAL size
        try:
            from ..settings import DB_PATH
            import os as _os
            wal_path = str(DB_PATH) + "-wal"
            if _os.path.exists(wal_path):
                wal_size_mb = _os.path.getsize(wal_path) / (1024 * 1024)
                if wal_size_mb > 100:
                    findings.append(_finding(
                        "runtime_health", "medium",
                        f"WAL file size: {wal_size_mb:.0f} MB",
                        f"The SQLite WAL file is {wal_size_mb:.0f} MB. "
                        f"This may indicate incomplete checkpointing.",
                        "Run PRAGMA wal_checkpoint(TRUNCATE) during low-traffic period.",
                        "Run PRAGMA wal_checkpoint(TRUNCATE) to reduce WAL file size.",
                        "Database maintenance",
                        [],
                    ))
        except Exception:
            pass

    except (sqlite3.OperationalError, sqlite3.Error):
        pass

    return findings


# ── 6. Ollama LLM assessment ─────────────────────────────────────────────

def _check_ollama_assessment(conn):
    """When Ollama is available, send recent error patterns to LLM for root cause analysis."""
    findings = []

    # Only attempt if we have significant errors to analyze
    recent_errors = _safe_query_all(conn, """
        SELECT error_type, error_message, COUNT(*) as cnt
        FROM error_log
        WHERE created_at >= datetime('now', '-3 days')
        GROUP BY error_type, error_message
        HAVING cnt >= 3
        ORDER BY cnt DESC
        LIMIT 5
    """) or []

    if not recent_errors or len(recent_errors) < 2:
        return findings

    # Check if Ollama is available
    try:
        from ..ai.ollama_client import generate, is_ollama_available
        if not is_ollama_available():
            return findings
    except ImportError:
        return findings

    # Build error summary for LLM
    error_summary_lines = []
    for row in recent_errors:
        error_summary_lines.append(
            f"- {row['error_type']}: {(row['error_message'] or '')[:200]} ({row['cnt']} occurrences)"
        )
    error_summary = "\n".join(error_summary_lines)

    prompt = (
        f"Analyze these recurring application errors from the last 3 days and identify "
        f"potential root causes. Are any of these errors related to each other? "
        f"What is the most impactful fix to prioritize?\n\n"
        f"Errors:\n{error_summary}\n\n"
        f"Respond concisely in 2-3 sentences. Focus on root cause, not symptoms."
    )

    try:
        response = generate(
            prompt=prompt,
            system="You are a senior backend engineer doing root cause analysis on production errors.",
            temperature=0.3,
            max_tokens=300,
            conn=conn,
            task_type="error_explanation",
        )

        if response.success and response.text:
            llm_analysis = response.text.strip()
            total_errors = sum(r["cnt"] for r in recent_errors)

            findings.append(_finding(
                "runtime_health", "medium",
                f"[LLM] Root cause analysis: {total_errors} recurring errors in 3 days",
                f"LLM analysis of {len(recent_errors)} recurring error patterns "
                f"({total_errors} total occurrences):\n\n{llm_analysis}\n\n"
                f"Error patterns analyzed:\n{error_summary}",
                llm_analysis,
                f"Investigate recurring errors based on LLM root cause analysis. "
                f"Patterns: {error_summary[:500]}",
                "Root cause analysis",
                [],
            ))
    except Exception as exc:
        logger.debug("Ollama error analysis failed: %s", exc)

    return findings


# ── Exported analyzer list ────────────────────────────────────────────────

ANALYZERS = [
    _check_error_log_spikes,
    _check_slow_endpoints,
    _check_failed_webhooks,
    _check_job_failures,
    _check_database_health,
    _check_ollama_assessment,
]
