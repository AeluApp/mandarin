"""Software engineering health analyzers — migration integrity, error rates, performance, infra hygiene."""

import logging
import os
import sqlite3

from ._base import _finding, _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Check 1: Migration integrity ────────────────────────────────────

def check_migration_integrity(conn):
    """Verify SCHEMA_VERSION matches the number of entries in MIGRATIONS dict."""
    findings = []
    try:
        from mandarin.db.core import SCHEMA_VERSION, MIGRATIONS

        migration_count = len(MIGRATIONS)

        if SCHEMA_VERSION != migration_count:
            findings.append(_finding(
                "engineering", "critical",
                f"Schema version mismatch: SCHEMA_VERSION={SCHEMA_VERSION}, "
                f"MIGRATIONS has {migration_count} entries",
                f"SCHEMA_VERSION ({SCHEMA_VERSION}) does not equal the number "
                f"of MIGRATIONS entries ({migration_count}). This means either "
                f"a migration was added without bumping the version, or the "
                f"version was bumped without a corresponding migration. "
                f"Database upgrades will fail or skip steps.",
                "Align SCHEMA_VERSION with len(MIGRATIONS). Every migration "
                "must have a corresponding version bump, and vice versa.",
                "Open mandarin/db/core.py and compare SCHEMA_VERSION to "
                "len(MIGRATIONS). Add the missing migration or fix the version.",
                "Database migration safety and upgrade reliability",
                ["mandarin/db/core.py"],
            ))
    except ImportError:
        pass
    except Exception as e:
        logger.debug("Migration integrity check error: %s", e)
    return findings


# ── Check 2: API error rate ─────────────────────────────────────────

def check_api_error_rate(conn):
    """Flag elevated API error rates in the last 24 hours."""
    findings = []
    try:
        count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM error_log "
            "WHERE created_at > datetime('now', '-24 hours')",
            default=0)

        if count > 50:
            findings.append(_finding(
                "engineering", "high",
                f"{count} API errors in last 24h (threshold: 50)",
                f"The error_log table recorded {count} errors in the last "
                f"24 hours. This elevated error rate may indicate a regression, "
                f"infrastructure issue, or unhandled edge case affecting users.",
                "Review recent error_log entries grouped by error type. "
                "Identify the most frequent errors and deploy fixes for the "
                "top contributors.",
                "Query error_log WHERE created_at > datetime('now', '-24 hours') "
                "GROUP BY error_type ORDER BY COUNT(*) DESC. Fix top offenders.",
                "API reliability and user experience",
                ["mandarin/web/__init__.py"],
            ))
        elif count > 20:
            findings.append(_finding(
                "engineering", "medium",
                f"{count} API errors in last 24h (threshold: 20)",
                f"The error_log table recorded {count} errors in the last "
                f"24 hours. While not critical, this is above the baseline "
                f"and warrants investigation before it escalates.",
                "Review error_log entries for patterns. Check if a recent "
                "deployment introduced new failure modes.",
                "Query error_log WHERE created_at > datetime('now', '-24 hours') "
                "GROUP BY error_type. Identify trending error types.",
                "API reliability monitoring",
                ["mandarin/web/__init__.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 3: Slow requests / crash indicators ──────────────────────

def check_slow_requests(conn):
    """Flag slow operations or sessions with suspiciously short durations (potential crashes)."""
    findings = []
    try:
        # Check error_log for timeout/slow entries
        slow_errors = _safe_scalar(conn,
            "SELECT COUNT(*) FROM error_log "
            "WHERE created_at > datetime('now', '-24 hours') "
            "AND (error_type LIKE '%timeout%' OR error_type LIKE '%slow%')",
            default=0)

        if slow_errors > 10:
            findings.append(_finding(
                "engineering", "medium",
                f"{slow_errors} timeout/slow errors in last 24h",
                f"Found {slow_errors} timeout or slow-request errors in the "
                f"last 24 hours. Slow responses degrade user experience and "
                f"can cascade into further failures.",
                "Profile the slowest endpoints. Check for missing database "
                "indexes, N+1 queries, or external service latency.",
                "Query error_log for timeout/slow entries. Identify the "
                "endpoints involved and profile their execution.",
                "Response time and user experience",
                ["mandarin/web/__init__.py"],
            ))
            return findings
    except (sqlite3.OperationalError, sqlite3.Error):
        pass

    try:
        # Fallback: check session_log for very short sessions (potential crashes)
        crash_candidates = _safe_scalar(conn,
            "SELECT COUNT(*) FROM session_log "
            "WHERE started_at > datetime('now', '-7 days') "
            "AND duration_seconds IS NOT NULL "
            "AND duration_seconds < 2",
            default=0)

        if crash_candidates > 20:
            findings.append(_finding(
                "engineering", "medium",
                f"{crash_candidates} sub-2-second sessions in last 7 days",
                f"Found {crash_candidates} sessions lasting under 2 seconds "
                f"in the past week. Very short sessions may indicate crashes, "
                f"immediate errors on page load, or broken redirects.",
                "Investigate sub-2-second sessions to determine if they "
                "represent crashes or legitimate quick interactions.",
                "Query session_log WHERE duration_seconds < 2 AND "
                "started_at > datetime('now', '-7 days'). Check corresponding "
                "error_log entries for the same time windows.",
                "Application stability and crash detection",
                ["mandarin/web/__init__.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 4: Dependency freshness (security scan findings) ─────────

def check_dependency_freshness(conn):
    """Flag unresolved high/critical security scan findings."""
    findings = []
    try:
        unresolved = _safe_scalar(conn,
            "SELECT COUNT(*) FROM security_scan_finding "
            "WHERE resolved_at IS NULL "
            "AND severity IN ('high', 'critical')",
            default=0)

        if unresolved > 0:
            findings.append(_finding(
                "engineering", "high",
                f"{unresolved} unresolved high/critical security finding(s)",
                f"There are {unresolved} unresolved security scan findings "
                f"with severity 'high' or 'critical'. Unpatched dependencies "
                f"with known vulnerabilities expose the application to attack.",
                "Prioritize resolving critical findings first, then high. "
                "Update affected dependencies or apply mitigations.",
                "Query security_scan_finding WHERE resolved_at IS NULL "
                "AND severity IN ('high','critical'). For each, check if a "
                "patched version is available and update.",
                "Security posture and dependency hygiene",
                ["mandarin/db/core.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 5: Feature flag staleness ─────────────────────────────────

def check_feature_flag_staleness(conn):
    """Flag feature flags at 100% rollout for 90+ days that should be cleaned up."""
    findings = []
    try:
        stale_flags = _safe_query_all(conn,
            "SELECT name, created_at FROM feature_flag "
            "WHERE rollout_pct = 100 "
            "AND created_at < datetime('now', '-90 days')")

        if not stale_flags:
            return findings

        names = []
        for row in stale_flags:
            if isinstance(row, dict):
                names.append(row.get("name", "?"))
            else:
                names.append(row[0] if row else "?")

        flag_list = ", ".join(f"'{n}'" for n in names[:10])
        findings.append(_finding(
            "engineering", "low",
            f"{len(names)} feature flag(s) fully rolled out for 90+ days",
            f"These flags have been at 100% rollout for over 90 days and "
            f"should be cleaned up: {flag_list}. Stale feature flags add "
            f"code complexity, confuse developers, and slow down testing.",
            "Remove stale flags by inlining the enabled code path and "
            "deleting the flag checks. Update tests accordingly.",
            "Query feature_flag WHERE rollout_pct=100 AND created_at < "
            "datetime('now', '-90 days'). For each flag, find all code "
            "references and remove the conditional branches.",
            "Code hygiene and maintainability",
            ["mandarin/db/core.py"],
        ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 6: Database file size ─────────────────────────────────────

def check_database_size(conn):
    """Flag if the database file exceeds size thresholds."""
    findings = []
    try:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "mandarin.db",
        )

        if not os.path.exists(db_path):
            return findings

        size_bytes = os.path.getsize(db_path)
        size_mb = size_bytes / (1024 * 1024)

        if size_bytes > 1_073_741_824:  # 1 GB
            findings.append(_finding(
                "engineering", "high",
                f"Database file is {size_mb:.0f} MB (threshold: 1024 MB)",
                f"mandarin.db is {size_mb:.0f} MB, exceeding the 1 GB "
                f"threshold. Large database files slow down backups, "
                f"increase migration time, and may cause disk pressure.",
                "Investigate large tables with SELECT name, "
                "SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC. "
                "Archive old data, VACUUM, or enable WAL compaction.",
                "Run PRAGMA page_count and PRAGMA page_size to compute "
                "actual DB size. Use dbstat to find largest tables. "
                "Propose archival or cleanup strategies.",
                "Infrastructure capacity and operational health",
                ["data/mandarin.db"],
            ))
        elif size_bytes > 524_288_000:  # 500 MB
            findings.append(_finding(
                "engineering", "medium",
                f"Database file is {size_mb:.0f} MB (approaching 1 GB threshold)",
                f"mandarin.db is {size_mb:.0f} MB. While not yet critical, "
                f"the database is growing and should be monitored. Consider "
                f"archival strategies before it reaches 1 GB.",
                "Monitor growth rate. Identify tables growing fastest and "
                "plan data retention policies.",
                "Run dbstat analysis to identify largest tables. Check "
                "growth rate by comparing with previous audit results.",
                "Database capacity planning",
                ["data/mandarin.db"],
            ))
    except OSError:
        pass
    return findings


# ── Check 7: Scheduler health ───────────────────────────────────────

def check_scheduler_health(conn):
    """Flag if quality_metric data is stale, indicating schedulers may have stopped."""
    findings = []
    try:
        latest = _safe_query(conn,
            "SELECT MAX(measured_at) FROM quality_metric")

        if latest is None or latest[0] is None:
            findings.append(_finding(
                "engineering", "high",
                "No quality_metric data found — schedulers may never have run",
                "The quality_metric table is empty. The background quality "
                "schedulers may not be configured or may have failed to start. "
                "Without regular metric collection, the intelligence system "
                "operates blind.",
                "Verify that quality_scheduler is running. Check logs for "
                "startup errors. Manually trigger a metric collection run.",
                "Check mandarin/web/quality_scheduler.py for configuration. "
                "Verify the scheduler thread starts on app boot. Check "
                "application logs for scheduler errors.",
                "Intelligence system health and data freshness",
                ["mandarin/web/quality_scheduler.py"],
            ))
            return findings

        # Check if most recent entry is older than 48 hours
        hours_old = _safe_scalar(conn,
            "SELECT (julianday('now') - julianday(MAX(measured_at))) * 24 "
            "FROM quality_metric",
            default=0)

        if hours_old and hours_old > 48:
            findings.append(_finding(
                "engineering", "high",
                f"quality_metric data is {hours_old:.0f}h old (threshold: 48h)",
                f"The most recent quality_metric entry is {hours_old:.0f} hours "
                f"old. The background schedulers may have stopped, crashed, "
                f"or failed to write results. Stale metrics mean the "
                f"intelligence engine is working with outdated data.",
                "Check scheduler logs for errors. Restart the application "
                "if the scheduler thread has died. Verify database write "
                "permissions.",
                "Check quality_scheduler.py run loop. Look for exceptions "
                "in application logs since the last successful metric write.",
                "Intelligence system data freshness",
                ["mandarin/web/quality_scheduler.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 8: Test coverage ──────────────────────────────────────────

def check_test_coverage(conn):
    """Note test coverage floor configuration status."""
    findings = []
    try:
        coverage_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "scripts", "coverage_floors.py",
        )

        if not os.path.exists(coverage_path):
            findings.append(_finding(
                "engineering", "low",
                "No coverage_floors.py found — coverage ratchet not configured",
                "The scripts/coverage_floors.py file was not found. Without "
                "per-module coverage floors, test coverage can silently "
                "regress as new code is added.",
                "Create scripts/coverage_floors.py with per-module coverage "
                "thresholds. Integrate it into CI to prevent regressions.",
                "Check if scripts/coverage_floors.py exists. If not, create "
                "it with baseline floors from current coverage levels.",
                "Test coverage discipline and regression prevention",
                ["scripts/coverage_floors.py"],
            ))
        else:
            # Coverage floors exist — informational note
            findings.append(_finding(
                "engineering", "low",
                "Coverage floor ratchet is configured",
                "scripts/coverage_floors.py exists, enforcing per-module "
                "coverage thresholds. This prevents silent coverage regression. "
                "Remember: never lower coverage floors — write tests instead.",
                "Periodically review floor values and ratchet them upward "
                "as coverage improves.",
                "Read scripts/coverage_floors.py and compare floors to "
                "current coverage. Identify modules where floors can be raised.",
                "Test coverage discipline",
                ["scripts/coverage_floors.py"],
            ))
    except OSError:
        pass
    return findings


# ── Check 9: Connection reuse ───────────────────────────────────────

def check_connection_reuse(conn):
    """Check whether connection pooling metrics are being recorded."""
    findings = []
    try:
        # Check if any connection pool metrics exist in quality_metric
        pool_metrics = _safe_scalar(conn,
            "SELECT COUNT(*) FROM quality_metric "
            "WHERE metric_name LIKE '%pool%' OR metric_name LIKE '%connection%'",
            default=0)

        if pool_metrics == 0:
            findings.append(_finding(
                "engineering", "low",
                "No connection pool metrics found",
                "No quality_metric entries related to connection pooling were "
                "found. Without pool metrics, it is unclear whether database "
                "connections are being efficiently reused or if each request "
                "opens a new connection.",
                "Instrument the database layer to record pool size, active "
                "connections, and wait times. Add these to the quality_metric "
                "collection cycle.",
                "Check mandarin/db/core.py for connection pooling setup. "
                "If pooling is active, add metrics. If not, evaluate whether "
                "a pool would reduce connection overhead.",
                "Database connection efficiency",
                ["mandarin/db/core.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Check 10: Schema table count ────────────────────────────────────

def check_schema_table_count(conn):
    """Verify the database has the expected number of tables."""
    findings = []
    try:
        table_count = _safe_scalar(conn,
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'",
            default=0)

        if table_count == 0:
            findings.append(_finding(
                "engineering", "critical",
                "No tables found in database",
                "sqlite_master reports 0 tables. The database may be "
                "uninitialized, corrupted, or pointing to the wrong file.",
                "Run database initialization. Check that the application "
                "startup runs all migrations.",
                "Check mandarin/db/core.py init_db() and verify it creates "
                "all expected tables. Check the database file path.",
                "Database integrity",
                ["mandarin/db/core.py"],
            ))
        elif table_count < 70:
            findings.append(_finding(
                "engineering", "medium",
                f"Only {table_count} tables found (expected 86+)",
                f"The database has {table_count} tables, significantly fewer "
                f"than the expected 86+. Some migrations may have failed to "
                f"run, or the schema is incomplete.",
                "Run pending migrations. Compare the table list against "
                "schema.sql to identify missing tables.",
                "Query sqlite_master WHERE type='table'. Compare the table "
                "list against MIGRATIONS in mandarin/db/core.py. Identify "
                "and run any missing migrations.",
                "Schema completeness and migration reliability",
                ["mandarin/db/core.py"],
            ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass
    return findings


# ── Analyzer registry ────────────────────────────────────────────────

ANALYZERS = [
    check_migration_integrity,
    check_api_error_rate,
    check_slow_requests,
    check_dependency_freshness,
    check_feature_flag_staleness,
    check_database_size,
    check_scheduler_health,
    check_test_coverage,
    check_connection_reuse,
    check_schema_table_count,
]
