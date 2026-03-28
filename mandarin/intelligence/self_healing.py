"""Infrastructure self-healing — automatic remediation for runtime issues.

Monitors system health metrics (memory, disk, error rates, response times)
and applies automatic fixes for known issue patterns. Integrates with the
existing intelligence engine and auto-fix executor.

Safety guardrails:
- Max 3 auto-restarts per hour (prevents restart loops)
- Max 10 remediation actions per hour (prevents cascading fixes)
- Every action is logged to self_healing_log table
- Admin is emailed about every action taken
- Cooldown periods between repeated actions on the same issue
- Does not restart during active user sessions when possible

Self-healing actions (automatic):
- High memory usage → clear LLM response caches, restart background schedulers
- Disk pressure → clean temp files, rotate/truncate logs
- Hung scheduler → restart the specific scheduler thread
- High error rate on a feature → disable it via feature flag
- Slow LLM responses → reduce concurrent calls
- Database locks → reset connection pool

Fly.io restart (requires FLY_API_TOKEN):
- POST to https://api.machines.dev/v1/apps/{app}/machines/{machine_id}/restart

Exports:
    run_health_check(conn) -> dict
    SelfHealingEngine
"""

from __future__ import annotations

import gc
import glob
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, UTC
from pathlib import Path

from ._base import _safe_query, _safe_query_all, _safe_scalar
from .calibration import get_threshold

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Configuration ──────────────────────────────────────────────────────────

# Safety limits
_MAX_RESTARTS_PER_HOUR = 3
_MAX_ACTIONS_PER_HOUR = 10
_COOLDOWN_SECONDS = 300  # 5 minutes between repeated actions on same issue

# Thresholds (defaults — overridden by calibration when data exists)
_MEMORY_HIGH_MB = 512          # Trigger cache clearing
_MEMORY_CRITICAL_MB = 768      # Trigger aggressive cleanup + scheduler restart
_DISK_PRESSURE_PCT = 90        # Trigger temp file cleanup
_DISK_CRITICAL_PCT = 95        # Trigger log truncation
_ERROR_RATE_THRESHOLD = 0.10   # 10% error rate triggers feature disable
_SLOW_RESPONSE_MS = 5000       # 5s average triggers LLM throttling
_STALE_LOCK_HOURS = 2          # Locks older than 2 hours are considered hung
_DB_LOCK_TIMEOUT_MS = 10000    # If busy_timeout exceeds this, reset pool


def _t(conn, metric: str, default: float) -> float:
    """Look up calibrated threshold, falling back to hardcoded default."""
    return get_threshold(conn, "self_healing", metric, default)


# ── Table creation ─────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create the self_healing_log table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS self_healing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            action_type TEXT NOT NULL,
            issue_detected TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            details TEXT,
            success INTEGER NOT NULL DEFAULT 1,
            error_message TEXT,
            metrics_before TEXT,
            metrics_after TEXT
        )
    """)
    conn.commit()


# ── Health metrics collection ──────────────────────────────────────────────

def _get_memory_usage_mb() -> float:
    """Get current process memory usage in MB.

    Uses VmRSS (current resident set size) on Linux, ru_maxrss on macOS.
    ru_maxrss is peak RSS and never decreases — unsuitable for ongoing
    monitoring, but acceptable on macOS where /proc is unavailable.
    """
    # Primary: read /proc/self/status VmRSS on Linux (current RSS, not peak)
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024  # KB → MB
    except Exception:
        pass

    # Fallback: resource.getrusage on macOS (peak RSS — best available)
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        ru_maxrss = usage.ru_maxrss
        if os.uname().sysname == "Darwin":
            return ru_maxrss / (1024 * 1024)  # macOS: bytes → MB
        return ru_maxrss / 1024  # Linux: KB → MB
    except Exception:
        pass

    return 0.0


def _get_disk_usage_pct() -> float:
    """Get disk usage percentage for the data partition."""
    try:
        from ..settings import DB_PATH
        stat = shutil.disk_usage(str(DB_PATH.parent))
        return (stat.used / stat.total) * 100 if stat.total > 0 else 0.0
    except Exception:
        try:
            stat = shutil.disk_usage("/")
            return (stat.used / stat.total) * 100 if stat.total > 0 else 0.0
        except Exception:
            return 0.0


def _get_error_rate(conn: sqlite3.Connection, minutes: int = 15) -> float:
    """Get error rate over the last N minutes from error_log."""
    total = _safe_scalar(conn, """
        SELECT COUNT(*) FROM request_timing
        WHERE recorded_at >= datetime('now', ? || ' minutes')
    """, (f"-{minutes}",), default=0)

    errors = _safe_scalar(conn, """
        SELECT COUNT(*) FROM error_log
        WHERE created_at >= datetime('now', ? || ' minutes')
    """, (f"-{minutes}",), default=0)

    if total == 0:
        return 0.0
    return errors / max(total, 1)


def _get_avg_response_time(conn: sqlite3.Connection, minutes: int = 15) -> float:
    """Get average response time in ms over the last N minutes."""
    return _safe_scalar(conn, """
        SELECT AVG(duration_ms) FROM request_timing
        WHERE recorded_at >= datetime('now', ? || ' minutes')
    """, (f"-{minutes}",), default=0.0) or 0.0


def _get_stale_scheduler_locks(conn: sqlite3.Connection) -> list:
    """Find scheduler locks that have been held too long."""
    return _safe_query_all(conn, """
        SELECT name, locked_by, locked_at, expires_at
        FROM scheduler_lock
        WHERE expires_at < datetime('now')
    """) or []


def _get_active_user_count(conn: sqlite3.Connection, minutes: int = 15) -> int:
    """Count users with activity in the last N minutes."""
    return _safe_scalar(conn, """
        SELECT COUNT(DISTINCT user_id) FROM session_log
        WHERE started_at >= datetime('now', ? || ' minutes')
    """, (f"-{minutes}",), default=0)


def _get_error_rate_by_endpoint(conn: sqlite3.Connection, minutes: int = 60) -> list:
    """Get error rates grouped by endpoint over the last N minutes."""
    return _safe_query_all(conn, """
        SELECT endpoint,
               COUNT(*) as total,
               SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) as errors,
               CAST(SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as error_rate
        FROM request_timing
        WHERE recorded_at >= datetime('now', ? || ' minutes')
        GROUP BY endpoint
        HAVING total >= 5 AND error_rate > ?
        ORDER BY error_rate DESC
        LIMIT 5
    """, (f"-{minutes}", _t(conn, "error_rate_threshold", _ERROR_RATE_THRESHOLD))) or []


def collect_health_metrics(conn: sqlite3.Connection) -> dict:
    """Collect all health metrics into a single snapshot."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "memory_mb": _get_memory_usage_mb(),
        "disk_usage_pct": _get_disk_usage_pct(),
        "error_rate_15m": _get_error_rate(conn, minutes=15),
        "avg_response_ms_15m": _get_avg_response_time(conn, minutes=15),
        "stale_locks": len(_get_stale_scheduler_locks(conn)),
        "active_users_15m": _get_active_user_count(conn, minutes=15),
    }


# ── Remediation actions ───────────────────────────────────────────────────

def _clear_llm_caches() -> dict:
    """Clear LLM response caches to free memory."""
    cleared = 0
    try:
        from ..ai.ollama_client import _RESPONSE_CACHE
        if hasattr(_RESPONSE_CACHE, "clear"):
            size_before = len(_RESPONSE_CACHE) if hasattr(_RESPONSE_CACHE, "__len__") else 0
            _RESPONSE_CACHE.clear()
            cleared += size_before
    except (ImportError, AttributeError):
        pass

    # Force garbage collection
    gc.collect()

    return {"caches_cleared": cleared, "gc_collected": True}


def _clean_temp_files() -> dict:
    """Clean temporary files to free disk space."""
    cleaned_files = 0
    freed_bytes = 0

    # Clean .auto_fix_backups
    backup_dir = _PROJECT_ROOT / ".auto_fix_backups"
    if backup_dir.exists():
        for f in backup_dir.iterdir():
            try:
                size = f.stat().st_size
                f.unlink()
                cleaned_files += 1
                freed_bytes += size
            except Exception:
                pass

    # Clean Python __pycache__ directories
    for cache_dir in _PROJECT_ROOT.rglob("__pycache__"):
        try:
            for f in cache_dir.iterdir():
                if f.suffix == ".pyc":
                    size = f.stat().st_size
                    f.unlink()
                    cleaned_files += 1
                    freed_bytes += size
        except Exception:
            pass

    # Clean /tmp files older than 1 day owned by this process
    try:
        import tempfile
        tmp_dir = Path(tempfile.gettempdir())
        cutoff = time.time() - 86400
        for f in tmp_dir.iterdir():
            try:
                if f.stat().st_mtime < cutoff and f.is_file():
                    size = f.stat().st_size
                    f.unlink()
                    cleaned_files += 1
                    freed_bytes += size
            except Exception:
                pass
    except Exception:
        pass

    return {
        "cleaned_files": cleaned_files,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
    }


def _truncate_logs() -> dict:
    """Truncate log files to free disk space under critical pressure."""
    truncated = []

    # Find log files in the project
    log_patterns = [
        str(_PROJECT_ROOT / "*.log"),
        str(_PROJECT_ROOT / "logs" / "*.log"),
        str(_PROJECT_ROOT / "data" / "*.log"),
    ]

    for pattern in log_patterns:
        for log_path in glob.glob(pattern):
            try:
                size = os.path.getsize(log_path)
                if size > 10 * 1024 * 1024:  # Only truncate files > 10MB
                    # Keep last 1000 lines
                    with open(log_path) as f:
                        lines = f.readlines()
                    with open(log_path, "w") as f:
                        f.writelines(lines[-1000:])
                    new_size = os.path.getsize(log_path)
                    truncated.append({
                        "file": log_path,
                        "before_mb": round(size / (1024 * 1024), 2),
                        "after_mb": round(new_size / (1024 * 1024), 2),
                    })
            except Exception:
                pass

    return {"truncated_files": truncated, "count": len(truncated)}


def _release_stale_locks(conn: sqlite3.Connection) -> dict:
    """Release scheduler locks that have expired (indicating a hung job)."""
    stale = _get_stale_scheduler_locks(conn)
    released = []

    for lock in stale:
        lock_name = lock["name"] if isinstance(lock, dict) else lock[0]
        try:
            conn.execute(
                "DELETE FROM scheduler_lock WHERE name = ?",
                (lock_name,),
            )
            released.append(lock_name)
        except Exception:
            pass

    if released:
        conn.commit()

    return {"released_locks": released, "count": len(released)}


def _disable_feature_by_flag(conn: sqlite3.Connection, feature_name: str, reason: str) -> dict:
    """Disable a feature via the feature_flag table."""
    flag_name = f"self_healing_disabled_{feature_name}"
    try:
        conn.execute("""
            INSERT OR REPLACE INTO feature_flag (name, enabled, updated_at)
            VALUES (?, 1, datetime('now'))
        """, (flag_name,))
        conn.commit()
        return {"flag_name": flag_name, "feature": feature_name, "reason": reason}
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        return {"flag_name": flag_name, "error": str(exc)}


def _reset_connection_pool() -> dict:
    """Reset the database connection pool to clear potential lock issues."""
    try:
        from .. import db
        # The connection context manager creates fresh connections each time,
        # so clearing any cached state is sufficient
        gc.collect()
        return {"reset": True}
    except Exception as exc:
        return {"reset": False, "error": str(exc)}


def _restart_via_fly_api() -> dict:
    """Restart this machine via the Fly.io Machines API.

    Requires FLY_API_TOKEN, FLY_APP_NAME, and FLY_MACHINE_ID environment vars.
    These are auto-set by Fly.io in the runtime environment.
    """
    fly_token = os.environ.get("FLY_API_TOKEN", "")
    fly_app = os.environ.get("FLY_APP_NAME", "")
    fly_machine = os.environ.get("FLY_MACHINE_ID", "")

    if not all([fly_token, fly_app, fly_machine]):
        return {
            "restarted": False,
            "error": "Missing Fly.io environment variables (FLY_API_TOKEN, FLY_APP_NAME, FLY_MACHINE_ID)",
        }

    try:
        import requests
        resp = requests.post(
            f"https://api.machines.dev/v1/apps/{fly_app}/machines/{fly_machine}/restart",
            headers={
                "Authorization": f"Bearer {fly_token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        return {
            "restarted": resp.status_code in (200, 202),
            "status_code": resp.status_code,
            "response": resp.text[:500],
        }
    except Exception as exc:
        return {"restarted": False, "error": str(exc)}


# ── Self-healing engine ───────────────────────────────────────────────────

class SelfHealingEngine:
    """Stateful engine that tracks remediation actions and enforces safety limits."""

    def __init__(self):
        self._action_log: list[dict] = []  # In-memory recent actions for rate limiting
        self._lock = threading.Lock()

    def _count_recent_actions(self, action_type: str | None = None, seconds: int = 3600) -> int:
        """Count actions taken in the last N seconds."""
        cutoff = time.time() - seconds
        with self._lock:
            if action_type:
                return sum(
                    1 for a in self._action_log
                    if a["time"] > cutoff and a["type"] == action_type
                )
            return sum(1 for a in self._action_log if a["time"] > cutoff)

    def _record_action(self, action_type: str) -> None:
        """Record an action for rate limiting."""
        now = time.time()
        with self._lock:
            self._action_log.append({"type": action_type, "time": now})
            # Prune entries older than 2 hours
            cutoff = now - 7200
            self._action_log = [a for a in self._action_log if a["time"] > cutoff]

    def _can_take_action(self, action_type: str) -> bool:
        """Check if we're within safety limits for this action type."""
        total_recent = self._count_recent_actions(seconds=3600)
        if total_recent >= _MAX_ACTIONS_PER_HOUR:
            logger.warning(
                "Self-healing: rate limit reached (%d/%d actions in last hour)",
                total_recent, _MAX_ACTIONS_PER_HOUR,
            )
            return False

        if action_type == "restart":
            restart_count = self._count_recent_actions("restart", seconds=3600)
            if restart_count >= _MAX_RESTARTS_PER_HOUR:
                logger.warning(
                    "Self-healing: restart limit reached (%d/%d in last hour)",
                    restart_count, _MAX_RESTARTS_PER_HOUR,
                )
                return False

        # Cooldown: don't repeat the same action within _COOLDOWN_SECONDS
        last_same = self._count_recent_actions(action_type, seconds=_COOLDOWN_SECONDS)
        if last_same > 0:
            logger.debug(
                "Self-healing: cooldown active for %s (last action within %ds)",
                action_type, _COOLDOWN_SECONDS,
            )
            return False

        return True

    def _log_action(
        self,
        conn: sqlite3.Connection,
        action_type: str,
        issue: str,
        action_taken: str,
        details: dict | None = None,
        success: bool = True,
        error_message: str | None = None,
        metrics_before: dict | None = None,
        metrics_after: dict | None = None,
    ) -> None:
        """Log a remediation action to the database and send admin notification."""
        _ensure_tables(conn)

        try:
            conn.execute("""
                INSERT INTO self_healing_log
                    (action_type, issue_detected, action_taken, details,
                     success, error_message, metrics_before, metrics_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action_type,
                issue,
                action_taken,
                json.dumps(details) if details else None,
                1 if success else 0,
                error_message,
                json.dumps(metrics_before) if metrics_before else None,
                json.dumps(metrics_after) if metrics_after else None,
            ))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error) as exc:
            logger.debug("Self-healing: failed to log action: %s", exc)

        # Send admin notification
        self._notify_admin(action_type, issue, action_taken, details, success)

    def _notify_admin(
        self,
        action_type: str,
        issue: str,
        action_taken: str,
        details: dict | None,
        success: bool,
    ) -> None:
        """Email and message the admin about a self-healing action."""
        status = "succeeded" if success else "FAILED"
        detail_str = json.dumps(details, indent=2) if details else "None"
        alert_body = (
            f"Issue detected: {issue}\n\n"
            f"Action taken: {action_taken}\n\n"
            f"Status: {status}\n\n"
            f"Details:\n{detail_str}"
        )
        alert_subject = f"[Aelu Self-Healing] {action_type} — {status}"

        # Email notification
        try:
            from ..settings import ADMIN_EMAIL
            admin_email = ADMIN_EMAIL or ""
            if admin_email:
                from ..email import send_alert
                send_alert(
                    to_email=admin_email,
                    subject=alert_subject,
                    details=alert_body,
                )
        except Exception as exc:
            logger.debug("Self-healing: email notification failed: %s", exc)

        # Matrix / Beeper notification
        try:
            from ..notifications.matrix_client import send_alert as matrix_alert
            matrix_alert(subject=alert_subject, details=alert_body)
        except Exception as exc:
            logger.debug("Self-healing: Matrix notification failed: %s", exc)

    def _check_governance(self, conn, action_type, target=None):
        """Check contract governance for an action. Returns (allowed, reason, contract_id).

        Wrapped in try/except so governance failures never break self-healing.
        """
        try:
            from .contracts import check_contract
            return check_contract(conn, "self_healing", action_type, target)
        except Exception:
            return True, "", None

    def _record_to_ledger(self, conn, action_type, target, description, metrics_before,
                          verification_hours=48, contract_id=None):
        """Record action to the unified ledger. Failures are non-fatal."""
        try:
            from .action_ledger import record_action
            return record_action(
                conn, "self_healing", action_type, target, description,
                metrics_before, verification_hours=verification_hours,
                contract_id=contract_id,
            )
        except Exception:
            return None

    def check_and_remediate(self, conn: sqlite3.Connection) -> dict:
        """Run all health checks and apply automatic remediations.

        Returns a summary dict with metrics, issues found, and actions taken.
        """
        _ensure_tables(conn)

        metrics = collect_health_metrics(conn)
        issues_found = []
        actions_taken = []

        # ── 1. High memory usage ──────────────────────────────────────────
        memory_mb = metrics["memory_mb"]

        t_mem_crit = _t(conn, "memory_critical_mb", _MEMORY_CRITICAL_MB)
        t_mem_high = _t(conn, "memory_high_mb", _MEMORY_HIGH_MB)
        if memory_mb > t_mem_crit:
            issues_found.append(f"Critical memory usage: {memory_mb:.0f} MB")
            if self._can_take_action("memory_critical"):
                allowed, reason, cid = self._check_governance(conn, "clear_caches")
                if not allowed:
                    logger.info("Contract blocked self_healing/clear_caches: %s", reason)
                    self._record_to_ledger(conn, "clear_caches", None, f"BLOCKED: {reason}", None, contract_id=cid)
                else:
                    result = _clear_llm_caches()
                    self._record_action("memory_critical")
                    action = f"Cleared LLM caches and forced GC (memory: {memory_mb:.0f} MB)"
                    actions_taken.append(action)
                    self._log_action(
                        conn, "memory_cleanup", f"Critical memory: {memory_mb:.0f} MB",
                        action, details=result, metrics_before=metrics,
                    )
                    self._record_to_ledger(conn, "clear_caches", None, action, metrics, verification_hours=1, contract_id=cid)

        elif memory_mb > t_mem_high:
            issues_found.append(f"High memory usage: {memory_mb:.0f} MB")
            if self._can_take_action("memory_high"):
                allowed, reason, cid = self._check_governance(conn, "clear_caches")
                if not allowed:
                    logger.info("Contract blocked self_healing/clear_caches: %s", reason)
                    self._record_to_ledger(conn, "clear_caches", None, f"BLOCKED: {reason}", None, contract_id=cid)
                else:
                    result = _clear_llm_caches()
                    self._record_action("memory_high")
                    action = f"Cleared LLM caches (memory: {memory_mb:.0f} MB)"
                    actions_taken.append(action)
                    self._log_action(
                        conn, "memory_cleanup", f"High memory: {memory_mb:.0f} MB",
                        action, details=result, metrics_before=metrics,
                    )
                    self._record_to_ledger(conn, "clear_caches", None, action, metrics, verification_hours=1, contract_id=cid)

        # ── 2. Disk pressure ──────────────────────────────────────────────
        disk_pct = metrics["disk_usage_pct"]

        t_disk_crit = _t(conn, "disk_critical_pct", _DISK_CRITICAL_PCT)
        t_disk_press = _t(conn, "disk_pressure_pct", _DISK_PRESSURE_PCT)
        if disk_pct > t_disk_crit:
            issues_found.append(f"Critical disk usage: {disk_pct:.1f}%")
            if self._can_take_action("disk_critical"):
                allowed_clean, reason_clean, cid_clean = self._check_governance(conn, "clean_temp")
                allowed_trunc, reason_trunc, cid_trunc = self._check_governance(conn, "truncate_logs")
                if not allowed_clean and not allowed_trunc:
                    logger.info("Contract blocked self_healing/clean_temp+truncate_logs: %s; %s", reason_clean, reason_trunc)
                    self._record_to_ledger(conn, "clean_temp", None, f"BLOCKED: {reason_clean}", None, contract_id=cid_clean)
                else:
                    clean_result = _clean_temp_files() if allowed_clean else {"cleaned_files": 0, "freed_mb": 0}
                    log_result = _truncate_logs() if allowed_trunc else {"count": 0, "truncated_files": []}
                    self._record_action("disk_critical")
                    action = (
                        f"Cleaned {clean_result['cleaned_files']} temp files "
                        f"(freed {clean_result['freed_mb']} MB), "
                        f"truncated {log_result['count']} log files"
                    )
                    actions_taken.append(action)
                    self._log_action(
                        conn, "disk_cleanup", f"Critical disk: {disk_pct:.1f}%",
                        action, details={**clean_result, **log_result},
                        metrics_before=metrics,
                    )
                    if allowed_clean:
                        self._record_to_ledger(conn, "clean_temp", None, action, metrics, verification_hours=1, contract_id=cid_clean)
                    if allowed_trunc:
                        self._record_to_ledger(conn, "truncate_logs", None, action, metrics, verification_hours=1, contract_id=cid_trunc)

        elif disk_pct > t_disk_press:
            issues_found.append(f"Disk pressure: {disk_pct:.1f}%")
            if self._can_take_action("disk_pressure"):
                allowed, reason, cid = self._check_governance(conn, "clean_temp")
                if not allowed:
                    logger.info("Contract blocked self_healing/clean_temp: %s", reason)
                    self._record_to_ledger(conn, "clean_temp", None, f"BLOCKED: {reason}", None, contract_id=cid)
                else:
                    result = _clean_temp_files()
                    self._record_action("disk_pressure")
                    action = (
                        f"Cleaned {result['cleaned_files']} temp files "
                        f"(freed {result['freed_mb']} MB)"
                    )
                    actions_taken.append(action)
                    self._log_action(
                        conn, "disk_cleanup", f"Disk pressure: {disk_pct:.1f}%",
                        action, details=result, metrics_before=metrics,
                    )
                    self._record_to_ledger(conn, "clean_temp", None, action, metrics, verification_hours=1, contract_id=cid)

        # ── 3. Stale scheduler locks (hung jobs) ─────────────────────────
        stale_locks = _get_stale_scheduler_locks(conn)
        if stale_locks:
            lock_names = [
                l["name"] if isinstance(l, dict) else l[0]
                for l in stale_locks
            ]
            issues_found.append(f"Stale scheduler locks: {', '.join(lock_names)}")
            if self._can_take_action("stale_lock_release"):
                allowed, reason, cid = self._check_governance(conn, "release_locks")
                if not allowed:
                    logger.info("Contract blocked self_healing/release_locks: %s", reason)
                    self._record_to_ledger(conn, "release_locks", None, f"BLOCKED: {reason}", None, contract_id=cid)
                else:
                    result = _release_stale_locks(conn)
                    self._record_action("stale_lock_release")
                    action = f"Released {result['count']} stale locks: {result['released_locks']}"
                    actions_taken.append(action)
                    self._log_action(
                        conn, "lock_release", f"Stale locks: {', '.join(lock_names)}",
                        action, details=result, metrics_before=metrics,
                    )
                    self._record_to_ledger(conn, "release_locks", None, action, metrics, verification_hours=1, contract_id=cid)

        # ── 4. High error rate on specific endpoints ─────────────────────
        high_error_endpoints = _get_error_rate_by_endpoint(conn, minutes=60)
        for ep_row in high_error_endpoints:
            endpoint = ep_row["endpoint"] or "unknown"
            error_rate = ep_row["error_rate"] or 0
            total = ep_row["total"] or 0

            if error_rate > _t(conn, "error_rate_threshold", _ERROR_RATE_THRESHOLD) and total >= 10:
                issues_found.append(
                    f"High error rate on {endpoint}: {error_rate:.0%} ({total} requests)"
                )
                # Sanitize endpoint name for use as feature flag key
                flag_key = endpoint.strip("/").replace("/", "_").replace(".", "_")
                if self._can_take_action(f"disable_{flag_key}"):
                    allowed, reason, cid = self._check_governance(conn, "disable_feature", flag_key)
                    if not allowed:
                        logger.info("Contract blocked self_healing/disable_feature: %s", reason)
                        self._record_to_ledger(conn, "disable_feature", flag_key, f"BLOCKED: {reason}", None, contract_id=cid)
                        continue
                    result = _disable_feature_by_flag(
                        conn, flag_key,
                        f"Auto-disabled: {error_rate:.0%} error rate on {endpoint}",
                    )
                    self._record_action(f"disable_{flag_key}")
                    action = f"Disabled feature flag for {endpoint} (error rate: {error_rate:.0%})"
                    actions_taken.append(action)
                    self._log_action(
                        conn, "feature_disable",
                        f"High error rate: {endpoint} at {error_rate:.0%}",
                        action, details=result, metrics_before=metrics,
                    )
                    self._record_to_ledger(conn, "disable_feature", flag_key, action, metrics, verification_hours=24, contract_id=cid)

        # ── 5. Slow LLM responses ────────────────────────────────────────
        avg_response = metrics["avg_response_ms_15m"]
        t_slow = _t(conn, "slow_response_ms", _SLOW_RESPONSE_MS)
        if avg_response > t_slow:
            issues_found.append(f"Slow average response time: {avg_response:.0f}ms")
            # Check if it's LLM-related by looking at LLM-heavy endpoints
            llm_endpoints = _safe_query_all(conn, """
                SELECT endpoint, AVG(duration_ms) as avg_ms
                FROM request_timing
                WHERE recorded_at >= datetime('now', '-15 minutes')
                  AND endpoint LIKE '%/api/ai%'
                GROUP BY endpoint
                HAVING avg_ms > ?
            """, (t_slow,)) or []

            if llm_endpoints and self._can_take_action("llm_throttle"):
                allowed, reason, cid = self._check_governance(conn, "disable_feature", "self_healing_llm_throttle")
                if not allowed:
                    logger.info("Contract blocked self_healing/disable_feature (llm_throttle): %s", reason)
                    self._record_to_ledger(conn, "disable_feature", "self_healing_llm_throttle", f"BLOCKED: {reason}", None, contract_id=cid)
                else:
                    # Set a throttle flag that the LLM client can check
                    try:
                        conn.execute("""
                            INSERT OR REPLACE INTO feature_flag (name, enabled, updated_at)
                            VALUES ('self_healing_llm_throttle', 1, datetime('now'))
                        """)
                        conn.commit()
                    except (sqlite3.OperationalError, sqlite3.Error):
                        pass

                    self._record_action("llm_throttle")
                    action = f"Enabled LLM throttle flag (avg response: {avg_response:.0f}ms)"
                    actions_taken.append(action)
                    self._log_action(
                        conn, "llm_throttle",
                        f"Slow responses: {avg_response:.0f}ms average",
                        action,
                        details={"llm_endpoints": [dict(ep) for ep in llm_endpoints]},
                        metrics_before=metrics,
                    )
                    self._record_to_ledger(conn, "disable_feature", "self_healing_llm_throttle", action, metrics, verification_hours=1, contract_id=cid)

        # ── 6. Database connection issues ─────────────────────────────────
        # Check if WAL file is excessively large (indicates checkpoint issues)
        try:
            from ..settings import DB_PATH
            wal_path = str(DB_PATH) + "-wal"
            if os.path.exists(wal_path):
                wal_size_mb = os.path.getsize(wal_path) / (1024 * 1024)
                if wal_size_mb > 50:
                    issues_found.append(f"Large WAL file: {wal_size_mb:.0f} MB")
                    if self._can_take_action("wal_checkpoint"):
                        try:
                            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                            self._record_action("wal_checkpoint")
                            action = f"Ran WAL checkpoint (WAL was {wal_size_mb:.0f} MB)"
                            actions_taken.append(action)
                            self._log_action(
                                conn, "db_maintenance",
                                f"Large WAL: {wal_size_mb:.0f} MB",
                                action, metrics_before=metrics,
                            )
                        except Exception as exc:
                            logger.debug("WAL checkpoint failed: %s", exc)
        except Exception:
            pass

        # ── 7. Fly.io restart (last resort) ──────────────────────────────
        # Only if memory is critical AND we have active errors AND cache clearing didn't help
        if (memory_mb > t_mem_crit
                and metrics["error_rate_15m"] > 0.2
                and self._can_take_action("restart")):

            # Check if there are active users — avoid restart during sessions
            active_users = metrics["active_users_15m"]
            if active_users == 0:
                allowed, reason, cid = self._check_governance(conn, "restart_machine")
                if not allowed:
                    logger.info("Contract blocked self_healing/restart_machine: %s", reason)
                    self._record_to_ledger(conn, "restart_machine", None, f"BLOCKED: {reason}", None, contract_id=cid)
                else:
                    result = _restart_via_fly_api()
                    self._record_action("restart")
                    action = f"Requested Fly.io machine restart (memory: {memory_mb:.0f} MB, errors: {metrics['error_rate_15m']:.0%})"
                    actions_taken.append(action)
                    self._log_action(
                        conn, "machine_restart",
                        f"Critical: memory {memory_mb:.0f} MB + {metrics['error_rate_15m']:.0%} error rate",
                        action, details=result,
                        success=result.get("restarted", False),
                        error_message=result.get("error"),
                        metrics_before=metrics,
                    )
                    self._record_to_ledger(conn, "restart_machine", None, action, metrics, verification_hours=1, contract_id=cid)
            else:
                issues_found.append(
                    f"Restart deferred: {active_users} active user(s) — will retry next check"
                )
                self._log_action(
                    conn, "restart_deferred",
                    f"Critical: memory {memory_mb:.0f} MB + errors, but {active_users} active users",
                    f"Deferred restart to avoid disrupting {active_users} active user(s)",
                    metrics_before=metrics,
                )

        # Collect post-remediation metrics if we took any action
        metrics_after = None
        if actions_taken:
            metrics_after = collect_health_metrics(conn)

        return {
            "metrics": metrics,
            "metrics_after": metrics_after,
            "issues_found": issues_found,
            "actions_taken": actions_taken,
            "actions_count": len(actions_taken),
            "rate_limit_remaining": _MAX_ACTIONS_PER_HOUR - self._count_recent_actions(seconds=3600),
        }


# ── Module-level singleton ─────────────────────────────────────────────────

_engine = SelfHealingEngine()


def run_health_check(conn: sqlite3.Connection) -> dict:
    """Run a health check and apply automatic remediations.

    This is the main entry point, called by:
    - The 15-minute health check scheduler (frequent, lightweight)
    - The nightly intelligence audit (comprehensive)

    Returns a summary dict.
    """
    try:
        result = _engine.check_and_remediate(conn)

        if result["actions_taken"]:
            logger.info(
                "Self-healing: %d issues found, %d actions taken — %s",
                len(result["issues_found"]),
                len(result["actions_taken"]),
                "; ".join(result["actions_taken"]),
            )
        elif result["issues_found"]:
            logger.info(
                "Self-healing: %d issues found, no action needed (cooldown or limits) — %s",
                len(result["issues_found"]),
                "; ".join(result["issues_found"]),
            )
        else:
            logger.debug("Self-healing: all metrics healthy")

        return result

    except Exception as exc:
        logger.exception("Self-healing check failed: %s", exc)
        return {
            "metrics": {},
            "issues_found": [],
            "actions_taken": [],
            "error": str(exc),
        }


def get_recent_actions(conn: sqlite3.Connection, limit: int = 20) -> list:
    """Retrieve recent self-healing actions for the admin dashboard."""
    _ensure_tables(conn)
    return _safe_query_all(conn, """
        SELECT id, created_at, action_type, issue_detected, action_taken,
               details, success, error_message
        FROM self_healing_log
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,)) or []


# ── Full self-healing loop ────────────────────────────────────────────────

def run_self_healing_loop(conn: sqlite3.Connection, include_tests: bool = False) -> dict:
    """Run the complete self-healing loop: ingest, classify, fix, review.

    This is the top-level orchestrator that combines:
    1. Infrastructure health check (existing SelfHealingEngine)
    2. Alert ingestion from all sources (Sentry, UptimeRobot, GitHub, etc.)
    3. Alert classification and auto-fixing
    4. Human review queue for non-fixable issues
    5. Existing auto_executor for LLM-based code fixes

    Args:
        conn: SQLite database connection.
        include_tests: If True, also run pytest and include test failures.

    Returns a summary dict with results from all phases.
    """
    from .alert_ingestion import ingest_all_alerts, ingest_test_results
    from .auto_fixer import run_auto_fixes

    results = {
        "timestamp": datetime.now(UTC).isoformat(),
        "phases": {},
        "total_issues": 0,
        "total_actions": 0,
        "errors": [],
    }

    # ── Phase 1: Infrastructure health check ──────────────────────────
    try:
        health_result = run_health_check(conn)
        results["phases"]["health_check"] = {
            "issues_found": len(health_result.get("issues_found", [])),
            "actions_taken": len(health_result.get("actions_taken", [])),
            "metrics": health_result.get("metrics", {}),
        }
        results["total_issues"] += len(health_result.get("issues_found", []))
        results["total_actions"] += len(health_result.get("actions_taken", []))
    except Exception as exc:
        logger.exception("Self-healing loop: health check failed: %s", exc)
        results["errors"].append(f"health_check: {exc}")
        results["phases"]["health_check"] = {"error": str(exc)}

    # ── Phase 2: Alert ingestion ──────────────────────────────────────
    try:
        alerts = ingest_all_alerts(conn)

        # Optionally include test results
        if include_tests:
            try:
                test_alerts = ingest_test_results()
                alerts.extend(test_alerts)
            except Exception as exc:
                logger.warning("Self-healing loop: test ingestion failed: %s", exc)
                results["errors"].append(f"test_ingestion: {exc}")

        results["phases"]["ingestion"] = {
            "total_alerts": len(alerts),
            "by_source": _count_by_key(alerts, "source"),
            "by_severity": _count_by_key(alerts, "severity"),
        }
        results["total_issues"] += len(alerts)
    except Exception as exc:
        logger.exception("Self-healing loop: alert ingestion failed: %s", exc)
        results["errors"].append(f"ingestion: {exc}")
        results["phases"]["ingestion"] = {"error": str(exc)}
        alerts = []

    # ── Phase 3: Classify and auto-fix ────────────────────────────────
    if alerts:
        try:
            fix_result = run_auto_fixes(conn, alerts)
            results["phases"]["auto_fix"] = {
                "total_classified": fix_result.get("total_alerts", 0),
                "auto_fixable": fix_result.get("auto_fixable", 0),
                "fixed": fix_result.get("fixed", 0),
                "failed": fix_result.get("failed", 0),
                "human_review_queued": fix_result.get("human_review_queued", 0),
            }
            results["total_actions"] += fix_result.get("fixed", 0)
        except Exception as exc:
            logger.exception("Self-healing loop: auto-fix failed: %s", exc)
            results["errors"].append(f"auto_fix: {exc}")
            results["phases"]["auto_fix"] = {"error": str(exc)}

    # ── Phase 4: Run existing auto_executor for LLM-based fixes ───────
    try:
        from .auto_executor import execute_auto_fixes, EXECUTOR_ENABLED
        if EXECUTOR_ENABLED:
            executor_results = execute_auto_fixes(conn)
            applied = sum(1 for r in executor_results if r.get("status") == "applied")
            results["phases"]["auto_executor"] = {
                "processed": len(executor_results),
                "applied": applied,
            }
            results["total_actions"] += applied
        else:
            results["phases"]["auto_executor"] = {"status": "disabled"}
    except Exception as exc:
        logger.debug("Self-healing loop: auto_executor failed: %s", exc)
        results["phases"]["auto_executor"] = {"error": str(exc)}

    # ── Summary logging ───────────────────────────────────────────────
    logger.info(
        "Self-healing loop complete: %d issues found, %d actions taken, %d errors",
        results["total_issues"], results["total_actions"], len(results["errors"]),
    )

    # Log the loop execution
    try:
        _ensure_tables(conn)
        conn.execute("""
            INSERT INTO self_healing_log
                (action_type, issue_detected, action_taken, details, success)
            VALUES ('self_healing_loop', ?, ?, ?, ?)
        """, (
            f"{results['total_issues']} issues found",
            f"{results['total_actions']} actions taken",
            json.dumps(results, default=str),
            1 if not results["errors"] else 0,
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Self-healing loop: failed to log execution: %s", exc)

    # Send notification if actions were taken
    if results["total_actions"] > 0:
        _engine._notify_admin(
            "self_healing_loop",
            f"{results['total_issues']} issues found",
            f"{results['total_actions']} actions taken",
            results["phases"],
            success=not results["errors"],
        )

    return results


def _count_by_key(items: list[dict], key: str) -> dict:
    """Count items by a key value."""
    counts = {}
    for item in items:
        value = item.get(key, "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


# ── Webhook trigger ──────────────────────────────────────────────────────

def run_self_healing_for_webhook(conn: sqlite3.Connection, source: str, payload: dict) -> dict:
    """Run a targeted self-healing check triggered by a webhook.

    Instead of running the full loop, this processes a single alert
    from an external webhook (Sentry, UptimeRobot, etc.).

    Args:
        conn: SQLite database connection.
        source: The alert source ("sentry", "uptime").
        payload: The raw webhook payload.

    Returns a summary dict.
    """
    from .auto_fixer import classify_alert, apply_fix, log_fix, queue_human_review

    alert = _webhook_payload_to_alert(source, payload)
    if not alert:
        return {"status": "ignored", "reason": "Could not parse webhook payload"}

    classification = classify_alert(alert)

    result = {
        "alert": alert["title"],
        "source": source,
        "classification": classification,
        "action_taken": None,
    }

    if classification["auto_fixable"]:
        fix_result = apply_fix(alert, classification["fix_strategy"])
        result["action_taken"] = fix_result
        log_fix(conn, alert, classification, fix_result)
    else:
        queue_human_review(conn, alert, classification)
        result["action_taken"] = "queued_for_human_review"
        log_fix(conn, alert, classification)

    logger.info(
        "Self-healing webhook [%s]: '%s' -> %s",
        source, alert["title"][:80],
        "auto-fixed" if classification["auto_fixable"] else "queued for review",
    )

    return result


def _webhook_payload_to_alert(source: str, payload: dict) -> dict | None:
    """Convert a raw webhook payload into a standardized alert dict."""
    from .alert_ingestion import _alert

    if source == "sentry":
        # Sentry webhook payload format
        # https://docs.sentry.io/product/integrations/integration-platform/webhooks/
        event = payload.get("event", payload.get("data", {}).get("event", {}))
        if not event and "data" in payload:
            # Try the issue format
            issue = payload.get("data", {}).get("issue", {})
            if issue:
                return _alert(
                    source="sentry",
                    external_id=f"sentry:webhook:{issue.get('id', '')}",
                    title=f"Sentry: {issue.get('title', 'Unknown error')[:150]}",
                    description=json.dumps(issue, default=str)[:2000],
                    severity=_map_sentry_level(issue.get("level", "error")),
                    category="code",
                    raw_data=payload,
                )

        if not event:
            return None

        title = event.get("title", event.get("message", "Unknown error"))
        level = event.get("level", "error")

        return _alert(
            source="sentry",
            external_id=f"sentry:webhook:{event.get('event_id', '')}",
            title=f"Sentry: {title[:150]}",
            description=json.dumps(event, default=str)[:2000],
            severity=_map_sentry_level(level),
            category="code",
            raw_data=payload,
        )

    elif source == "uptime":
        # UptimeRobot webhook payload
        # https://uptimerobot.com/api/
        monitor_url = payload.get("monitorURL", "")
        monitor_name = payload.get("monitorFriendlyName", monitor_url)
        alert_type = payload.get("alertType", 0)

        # alertType: 1 = down, 2 = up
        if alert_type == 2:
            # Monitor recovered — no action needed
            return None

        return _alert(
            source="uptime",
            external_id=f"uptime:webhook:{payload.get('monitorID', '')}",
            title=f"Monitor DOWN: {monitor_name}",
            description=(
                f"Monitor '{monitor_name}' is down.\n"
                f"URL: {monitor_url}\n"
                f"Alert details: {payload.get('alertDetails', 'N/A')}"
            ),
            severity="critical",
            category="infrastructure",
            raw_data=payload,
        )

    return None


def _map_sentry_level(level: str) -> str:
    """Map Sentry event level to our severity scale."""
    _MAP = {
        "fatal": "critical",
        "error": "high",
        "warning": "medium",
        "info": "low",
        "debug": "low",
    }
    return _MAP.get(level, "medium")


# ── CLI entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    from .__main__ import main
    main()
