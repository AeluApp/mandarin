"""External Dependency Monitor — check all external services, auto-switch fallbacks.

Checks every 15 minutes (via health_check_scheduler):
- LLM endpoint (Ollama/LiteLLM): POST test prompt, measure latency
- TTS (edge_tts): generate test audio, measure latency
- Stripe: list prices, measure latency
- Resend: check domains, measure latency
- Plausible: aggregate stats, measure latency

Each dependency gets three states: healthy, degraded, dead.
When degraded -> preemptive alert. When dead -> auto-switch fallback.
When recovered -> auto-switch back. All transitions logged + emailed.

Exports:
    run_check(conn) -> dict
    ANALYZERS: list of analyzer functions for the intelligence engine
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, UTC

from ._base import _safe_query, _safe_query_all, _safe_scalar, _finding

logger = logging.getLogger(__name__)

# ── Health states ─────────────────────────────────────────────────────────

HEALTHY = "healthy"
DEGRADED = "degraded"
DEAD = "dead"

# ── Dependency definitions ────────────────────────────────────────────────

DEPENDENCIES = {
    "llm": {
        "healthy_threshold_ms": 5000,
        "degraded_threshold_ms": 15000,
        "fallback_flag": "dep_llm_fallback",
        "dead_flag": "dep_llm_dead",
        "description": "LLM endpoint (Ollama/LiteLLM)",
    },
    "tts": {
        "healthy_threshold_ms": 3000,
        "degraded_threshold_ms": 10000,
        "fallback_flag": "dep_tts_fallback",
        "dead_flag": "dep_tts_dead",
        "description": "Text-to-speech (edge_tts)",
    },
    "stripe": {
        "healthy_threshold_ms": 2000,
        "degraded_threshold_ms": 8000,
        "fallback_flag": "dep_stripe_fallback",
        "dead_flag": "dep_stripe_dead",
        "description": "Stripe payment API",
    },
    "resend": {
        "healthy_threshold_ms": 2000,
        "degraded_threshold_ms": 8000,
        "fallback_flag": "dep_resend_fallback",
        "dead_flag": "dep_resend_dead",
        "description": "Resend email API",
    },
    "plausible": {
        "healthy_threshold_ms": 3000,
        "degraded_threshold_ms": 10000,
        "fallback_flag": "dep_plausible_fallback",
        "dead_flag": "dep_plausible_dead",
        "description": "Plausible analytics API",
    },
}

# Consecutive degraded checks before preemptive alert
_TREND_ALERT_COUNT = 3


# ── Table creation ────────────────────────────────────────────────────────

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create dependency monitoring tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dependency_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            dep_name TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms INTEGER,
            error_message TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_dep_health_name_ts
        ON dependency_health(dep_name, created_at)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dependency_transition_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            dep_name TEXT NOT NULL,
            old_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            action_taken TEXT,
            details TEXT
        )
    """)
    conn.commit()


def _log_health(conn, dep_name: str, status: str, latency_ms: int = None,
                error_message: str = None) -> None:
    """Record a health check result."""
    try:
        conn.execute("""
            INSERT INTO dependency_health (dep_name, status, latency_ms, error_message)
            VALUES (?, ?, ?, ?)
        """, (dep_name, status, latency_ms, error_message))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Dependency monitor: failed to log health: %s", exc)


def _log_transition(conn, dep_name: str, old_status: str, new_status: str,
                    action_taken: str, details: dict = None) -> None:
    """Record a status transition."""
    try:
        conn.execute("""
            INSERT INTO dependency_transition_log
                (dep_name, old_status, new_status, action_taken, details)
            VALUES (?, ?, ?, ?, ?)
        """, (dep_name, old_status, new_status, action_taken,
              json.dumps(details) if details else None))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as exc:
        logger.debug("Dependency monitor: failed to log transition: %s", exc)


def _notify_admin(dep_name: str, old_status: str, new_status: str,
                  action_taken: str, details: dict = None) -> None:
    """Email admin about a dependency status change."""
    try:
        from ..settings import ADMIN_EMAIL
        if not ADMIN_EMAIL:
            return
        from ..email import send_alert
        dep_desc = DEPENDENCIES.get(dep_name, {}).get("description", dep_name)
        detail_str = json.dumps(details, indent=2) if details else "None"
        send_alert(
            to_email=ADMIN_EMAIL,
            subject=f"[Aelu Dependency] {dep_desc}: {old_status} -> {new_status}",
            details=(
                f"Dependency: {dep_desc} ({dep_name})\n"
                f"Transition: {old_status} -> {new_status}\n"
                f"Action: {action_taken}\n\n"
                f"Details:\n{detail_str}"
            ),
        )
    except Exception as exc:
        logger.debug("Dependency monitor: admin notification failed: %s", exc)


def _set_feature_flag(conn, flag_name: str, value: int) -> None:
    """Set a feature flag value."""
    try:
        conn.execute("""
            INSERT OR REPLACE INTO feature_flag (name, enabled, updated_at)
            VALUES (?, ?, datetime('now'))
        """, (flag_name, value))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error):
        pass


def _get_feature_flag(conn, flag_name: str, default: int = 0) -> int:
    """Get a feature flag value."""
    return _safe_scalar(conn, """
        SELECT enabled FROM feature_flag WHERE name = ?
    """, (flag_name,), default=default)


def _get_last_status(conn, dep_name: str) -> str:
    """Get the most recent status for a dependency."""
    row = _safe_query(conn, """
        SELECT status FROM dependency_health
        WHERE dep_name = ?
        ORDER BY created_at DESC LIMIT 1
    """, (dep_name,))
    if row:
        return row[0]
    return HEALTHY


def _get_recent_statuses(conn, dep_name: str, count: int = 3) -> list[str]:
    """Get the N most recent statuses for a dependency."""
    rows = _safe_query_all(conn, """
        SELECT status FROM dependency_health
        WHERE dep_name = ?
        ORDER BY created_at DESC LIMIT ?
    """, (dep_name, count))
    return [r[0] for r in rows] if rows else []


# ── Health check functions ────────────────────────────────────────────────

def _check_llm() -> tuple[str, int, str | None]:
    """Check LLM endpoint health.

    Returns (status, latency_ms, error_message).
    """
    from ..settings import OLLAMA_URL

    start = time.monotonic()
    try:
        import httpx
        resp = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": "test",
                "prompt": "Say hello",
                "stream": False,
                "options": {"num_predict": 5},
            },
            timeout=15.0,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        # 404 means Ollama is up but model not found — still alive
        if resp.status_code in (200, 404):
            thresholds = DEPENDENCIES["llm"]
            if latency_ms <= thresholds["healthy_threshold_ms"]:
                return HEALTHY, latency_ms, None
            if latency_ms <= thresholds["degraded_threshold_ms"]:
                return DEGRADED, latency_ms, f"Slow response: {latency_ms}ms"
            return DEAD, latency_ms, f"Extremely slow: {latency_ms}ms"

        return DEAD, latency_ms, f"HTTP {resp.status_code}"

    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return DEAD, latency_ms, str(exc)[:200]


def _check_tts() -> tuple[str, int, str | None]:
    """Check TTS (edge_tts) health."""
    start = time.monotonic()
    try:
        import asyncio
        import edge_tts

        async def _test():
            communicate = edge_tts.Communicate("你好", "zh-CN-XiaoxiaoNeural")
            try:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        return True
                return False
            finally:
                # Close internal aiohttp session to prevent "Unclosed client session"
                # errors. edge_tts stores the session in different attributes depending
                # on version; try all known locations.
                for attr in ("session", "_session", "ws", "_ws"):
                    sess = getattr(communicate, attr, None)
                    if sess is not None and hasattr(sess, "close"):
                        try:
                            await sess.close()
                        except Exception:
                            pass
                # Give the event loop a tick to finalize any pending callbacks
                await asyncio.sleep(0)

        def _run_in_fresh_loop():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_test())
            finally:
                # Properly shut down to avoid "Task was destroyed" warnings
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(_run_in_fresh_loop).result(timeout=10)
            else:
                result = _run_in_fresh_loop()
        except RuntimeError:
            result = _run_in_fresh_loop()

        latency_ms = int((time.monotonic() - start) * 1000)

        if result:
            thresholds = DEPENDENCIES["tts"]
            if latency_ms <= thresholds["healthy_threshold_ms"]:
                return HEALTHY, latency_ms, None
            if latency_ms <= thresholds["degraded_threshold_ms"]:
                return DEGRADED, latency_ms, f"Slow: {latency_ms}ms"
            return DEAD, latency_ms, f"Extremely slow: {latency_ms}ms"

        return DEAD, latency_ms, "No audio generated"

    except ImportError:
        latency_ms = int((time.monotonic() - start) * 1000)
        return DEAD, latency_ms, "edge_tts not installed"
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return DEAD, latency_ms, str(exc)[:200]


def _check_stripe() -> tuple[str, int, str | None]:
    """Check Stripe API health."""
    start = time.monotonic()
    try:
        import stripe
        from ..settings import STRIPE_SECRET_KEY
        if not STRIPE_SECRET_KEY:
            return HEALTHY, 0, "No Stripe key configured (skip)"

        stripe.api_key = STRIPE_SECRET_KEY
        stripe.Price.list(limit=1)
        latency_ms = int((time.monotonic() - start) * 1000)

        thresholds = DEPENDENCIES["stripe"]
        if latency_ms <= thresholds["healthy_threshold_ms"]:
            return HEALTHY, latency_ms, None
        if latency_ms <= thresholds["degraded_threshold_ms"]:
            return DEGRADED, latency_ms, f"Slow: {latency_ms}ms"
        return DEAD, latency_ms, f"Extremely slow: {latency_ms}ms"

    except ImportError:
        return HEALTHY, 0, "stripe SDK not installed (skip)"
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return DEAD, latency_ms, str(exc)[:200]


def _check_resend() -> tuple[str, int, str | None]:
    """Check Resend email API health."""
    start = time.monotonic()
    try:
        import requests
        from ..settings import RESEND_API_KEY
        if not RESEND_API_KEY:
            return HEALTHY, 0, "No Resend key configured (skip)"

        resp = requests.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            timeout=8.0,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            thresholds = DEPENDENCIES["resend"]
            if latency_ms <= thresholds["healthy_threshold_ms"]:
                return HEALTHY, latency_ms, None
            if latency_ms <= thresholds["degraded_threshold_ms"]:
                return DEGRADED, latency_ms, f"Slow: {latency_ms}ms"
            return DEAD, latency_ms, f"Extremely slow: {latency_ms}ms"

        return DEAD, latency_ms, f"HTTP {resp.status_code}"

    except ImportError:
        return HEALTHY, 0, "requests not installed (skip)"
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return DEAD, latency_ms, str(exc)[:200]


def _check_plausible() -> tuple[str, int, str | None]:
    """Check Plausible analytics API health."""
    start = time.monotonic()
    try:
        import requests
        from ..settings import PLAUSIBLE_API_KEY, PLAUSIBLE_DOMAIN
        if not PLAUSIBLE_API_KEY or not PLAUSIBLE_DOMAIN:
            return HEALTHY, 0, "No Plausible config (skip)"

        resp = requests.get(
            "https://plausible.io/api/v1/stats/aggregate",
            headers={"Authorization": f"Bearer {PLAUSIBLE_API_KEY}"},
            params={"site_id": PLAUSIBLE_DOMAIN, "period": "day"},
            timeout=10.0,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            thresholds = DEPENDENCIES["plausible"]
            if latency_ms <= thresholds["healthy_threshold_ms"]:
                return HEALTHY, latency_ms, None
            if latency_ms <= thresholds["degraded_threshold_ms"]:
                return DEGRADED, latency_ms, f"Slow: {latency_ms}ms"
            return DEAD, latency_ms, f"Extremely slow: {latency_ms}ms"

        return DEAD, latency_ms, f"HTTP {resp.status_code}"

    except ImportError:
        return HEALTHY, 0, "requests not installed (skip)"
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return DEAD, latency_ms, str(exc)[:200]


_CHECK_FUNCTIONS = {
    "llm": _check_llm,
    "tts": _check_tts,
    "stripe": _check_stripe,
    "resend": _check_resend,
    "plausible": _check_plausible,
}


# ── Fallback actions ──────────────────────────────────────────────────────

def _activate_fallback(conn, dep_name: str) -> dict:
    """Switch to fallback mode for a dependency."""
    dep_config = DEPENDENCIES[dep_name]
    _set_feature_flag(conn, dep_config["fallback_flag"], 1)

    actions = {"flag_set": dep_config["fallback_flag"]}

    if dep_name == "llm":
        # Switch to smaller/faster model
        _set_feature_flag(conn, "llm_use_fast_model", 1)
        actions["llm_fast_model"] = True
    elif dep_name == "tts":
        # Enable aggressive audio caching
        _set_feature_flag(conn, "tts_aggressive_cache", 1)
        actions["tts_aggressive_cache"] = True
    elif dep_name == "stripe":
        # Queue payments for retry
        actions["payment_queueing"] = True
    elif dep_name == "resend":
        # Queue emails for retry
        actions["email_queueing"] = True
    elif dep_name == "plausible":
        # Use cached analytics data
        actions["analytics_cached"] = True

    return actions


def _activate_dead_mode(conn, dep_name: str) -> dict:
    """Fully disable a dependency's features."""
    dep_config = DEPENDENCIES[dep_name]
    _set_feature_flag(conn, dep_config["dead_flag"], 1)
    _set_feature_flag(conn, dep_config["fallback_flag"], 1)

    actions = {
        "dead_flag_set": dep_config["dead_flag"],
        "fallback_flag_set": dep_config["fallback_flag"],
    }

    if dep_name == "llm":
        _set_feature_flag(conn, "dep_llm_features_disabled", 1)
        actions["llm_features_disabled"] = True
    elif dep_name == "tts":
        _set_feature_flag(conn, "dep_audio_disabled", 1)
        actions["audio_disabled"] = True
    elif dep_name == "stripe":
        _set_feature_flag(conn, "dep_payments_unavailable", 1)
        actions["payments_unavailable"] = True
    elif dep_name == "resend":
        # Log emails to DB for manual review
        _set_feature_flag(conn, "dep_email_to_db", 1)
        actions["email_to_db"] = True
    elif dep_name == "plausible":
        _set_feature_flag(conn, "dep_analytics_disabled", 1)
        actions["analytics_disabled"] = True

    return actions


def _deactivate_fallback(conn, dep_name: str) -> dict:
    """Switch back from fallback mode when dependency recovers."""
    dep_config = DEPENDENCIES[dep_name]
    _set_feature_flag(conn, dep_config["fallback_flag"], 0)
    _set_feature_flag(conn, dep_config["dead_flag"], 0)

    actions = {
        "fallback_cleared": dep_config["fallback_flag"],
        "dead_cleared": dep_config["dead_flag"],
    }

    # Clear dependency-specific flags
    dep_flags = {
        "llm": ["llm_use_fast_model", "dep_llm_features_disabled"],
        "tts": ["tts_aggressive_cache", "dep_audio_disabled", "tts_fallback_mode"],
        "stripe": ["dep_payments_unavailable"],
        "resend": ["dep_email_to_db"],
        "plausible": ["dep_analytics_disabled"],
    }

    for flag in dep_flags.get(dep_name, []):
        _set_feature_flag(conn, flag, 0)
        actions[f"cleared_{flag}"] = True

    return actions


# ── Latency trend detection ──────────────────────────────────────────────

def _check_latency_trend(conn, dep_name: str) -> bool:
    """Check if the last 3 checks show increasing latency.

    Returns True if latency is trending up (preemptive alert needed).
    """
    rows = _safe_query_all(conn, """
        SELECT latency_ms FROM dependency_health
        WHERE dep_name = ? AND latency_ms IS NOT NULL AND latency_ms > 0
        ORDER BY created_at DESC
        LIMIT ?
    """, (dep_name, _TREND_ALERT_COUNT))

    if not rows or len(rows) < _TREND_ALERT_COUNT:
        return False

    latencies = [r[0] for r in rows]
    # Check if each successive check is slower
    # (latencies are ordered newest-first, so reverse for chronological)
    chronological = list(reversed(latencies))
    return all(chronological[i] < chronological[i + 1]
               for i in range(len(chronological) - 1))


# ── Main check ────────────────────────────────────────────────────────────

def run_check(conn: sqlite3.Connection) -> dict:
    """Check all external dependencies and auto-switch fallbacks.

    Called by health_check_scheduler.py every 15 minutes.

    Returns a summary dict.
    """
    _ensure_tables(conn)

    results = {}
    transitions = []
    actions_taken = []

    for dep_name, check_fn in _CHECK_FUNCTIONS.items():
        _dep_config = DEPENDENCIES[dep_name]  # noqa: F841

        # Run the health check
        try:
            new_status, latency_ms, error_msg = check_fn()
        except Exception as exc:
            new_status = DEAD
            latency_ms = 0
            error_msg = f"Check itself failed: {exc}"

        # Record the check result
        _log_health(conn, dep_name, new_status, latency_ms, error_msg)

        # Get previous status
        old_status = _get_last_status(conn, dep_name)

        results[dep_name] = {
            "status": new_status,
            "latency_ms": latency_ms,
            "error": error_msg,
            "previous_status": old_status,
        }

        # Handle transitions
        if new_status != old_status:
            action_desc = ""
            details = {"latency_ms": latency_ms, "error": error_msg}

            if new_status == DEGRADED and old_status == HEALTHY:
                # Governance: contract check for fallback switch
                dep_allowed, dep_reason, dep_cid = True, "", None
                try:
                    from .contracts import check_contract
                    dep_allowed, dep_reason, dep_cid = check_contract(
                        conn, "dependency_monitor", "switch_fallback", dep_name)
                except Exception:
                    pass

                if not dep_allowed:
                    logger.info("Contract blocked dependency_monitor/switch_fallback for %s: %s", dep_name, dep_reason)
                    try:
                        from .action_ledger import record_action
                        record_action(conn, "dependency_monitor", "switch_fallback", dep_name,
                                      f"BLOCKED: {dep_reason}", None, contract_id=dep_cid)
                    except Exception:
                        pass
                else:
                    # Healthy -> Degraded: activate fallback
                    fallback_result = _activate_fallback(conn, dep_name)
                    action_desc = f"Activated fallback for {dep_name}"
                    details.update(fallback_result)
                    actions_taken.append(action_desc)
                    try:
                        from .action_ledger import record_action
                        record_action(conn, "dependency_monitor", "switch_fallback", dep_name,
                                      action_desc, {"latency_ms": latency_ms}, verification_hours=1, contract_id=dep_cid)
                    except Exception:
                        pass

            elif new_status == DEAD:
                # Governance: contract check for disable_feature
                dep_allowed, dep_reason, dep_cid = True, "", None
                try:
                    from .contracts import check_contract
                    dep_allowed, dep_reason, dep_cid = check_contract(
                        conn, "dependency_monitor", "disable_feature", dep_name)
                except Exception:
                    pass

                if not dep_allowed:
                    logger.info("Contract blocked dependency_monitor/disable_feature for %s: %s", dep_name, dep_reason)
                    try:
                        from .action_ledger import record_action
                        record_action(conn, "dependency_monitor", "disable_feature", dep_name,
                                      f"BLOCKED: {dep_reason}", None, contract_id=dep_cid)
                    except Exception:
                        pass
                else:
                    # Anything -> Dead: full disable
                    dead_result = _activate_dead_mode(conn, dep_name)
                    action_desc = f"Activated dead mode for {dep_name} — features disabled"
                    details.update(dead_result)
                    actions_taken.append(action_desc)
                    try:
                        from .action_ledger import record_action
                        record_action(conn, "dependency_monitor", "disable_feature", dep_name,
                                      action_desc, {"latency_ms": latency_ms}, verification_hours=1, contract_id=dep_cid)
                    except Exception:
                        pass

            elif new_status == HEALTHY and old_status in (DEGRADED, DEAD):
                # Recovery: deactivate fallback (enable_feature)
                dep_allowed, dep_reason, dep_cid = True, "", None
                try:
                    from .contracts import check_contract
                    dep_allowed, dep_reason, dep_cid = check_contract(
                        conn, "dependency_monitor", "enable_feature", dep_name)
                except Exception:
                    pass

                if not dep_allowed:
                    logger.info("Contract blocked dependency_monitor/enable_feature for %s: %s", dep_name, dep_reason)
                else:
                    recovery_result = _deactivate_fallback(conn, dep_name)
                    action_desc = f"Recovered {dep_name} — fallbacks deactivated"
                    details.update(recovery_result)
                    actions_taken.append(action_desc)
                    try:
                        from .action_ledger import record_action
                        record_action(conn, "dependency_monitor", "enable_feature", dep_name,
                                      action_desc, {"latency_ms": latency_ms}, verification_hours=1, contract_id=dep_cid)
                    except Exception:
                        pass

            if action_desc:
                _log_transition(conn, dep_name, old_status, new_status,
                                action_desc, details)
                _notify_admin(dep_name, old_status, new_status,
                              action_desc, details)
                transitions.append({
                    "dep": dep_name,
                    "from": old_status,
                    "to": new_status,
                    "action": action_desc,
                })

        # Check for latency trend (preemptive alert)
        if new_status == HEALTHY and _check_latency_trend(conn, dep_name):
            recent = _get_recent_statuses(conn, dep_name, count=_TREND_ALERT_COUNT)
            trend_action = f"Latency trending up for {dep_name} — preemptive alert"
            actions_taken.append(trend_action)
            _notify_admin(
                dep_name, HEALTHY, "trending_up",
                trend_action,
                {"recent_statuses": recent, "latency_ms": latency_ms},
            )

    # Log summary
    if transitions:
        logger.info(
            "Dependency monitor: %d transition(s) — %s",
            len(transitions),
            "; ".join(t["action"] for t in transitions),
        )
    else:
        statuses = {k: v["status"] for k, v in results.items()}
        if all(s == HEALTHY for s in statuses.values()):
            logger.debug("Dependency monitor: all dependencies healthy")
        else:
            unhealthy = {k: v for k, v in statuses.items() if v != HEALTHY}
            logger.info("Dependency monitor: unhealthy — %s", unhealthy)

    return {
        "results": results,
        "transitions": transitions,
        "actions_taken": actions_taken,
    }


# ── Intelligence analyzer ────────────────────────────────────────────────

def analyze_dependency_health(conn) -> list[dict]:
    """Analyzer function for the intelligence engine.

    Checks historical dependency health data for persistent issues.
    """
    _ensure_tables(conn)
    findings = []

    for dep_name, dep_config in DEPENDENCIES.items():
        # Check how many dead checks in the last 24 hours
        dead_count = _safe_scalar(conn, """
            SELECT COUNT(*) FROM dependency_health
            WHERE dep_name = ? AND status = 'dead'
              AND created_at >= datetime('now', '-24 hours')
        """, (dep_name,), default=0)

        total_checks = _safe_scalar(conn, """
            SELECT COUNT(*) FROM dependency_health
            WHERE dep_name = ? AND created_at >= datetime('now', '-24 hours')
        """, (dep_name,), default=0)

        if total_checks >= 3 and dead_count > 0:
            dead_pct = dead_count / total_checks
            dep_desc = dep_config["description"]

            if dead_pct > 0.5:
                findings.append(_finding(
                    "engineering", "critical",
                    f"{dep_desc} down >50% of checks (24h)",
                    f"{dep_desc} was dead in {dead_count}/{total_checks} health "
                    f"checks ({dead_pct:.0%}) over the last 24 hours. Automatic "
                    f"fallbacks are active but the dependency needs attention.",
                    f"Investigate {dep_name} outage. Check provider status page. "
                    f"Review dependency_transition_log for details.",
                    f"Check dependency_health WHERE dep_name='{dep_name}' for "
                    f"error patterns. Review dependency_transition_log for "
                    f"automatic actions taken.",
                    f"External dependency reliability ({dep_name})",
                    [],
                ))
            elif dead_pct > 0.1:
                findings.append(_finding(
                    "engineering", "high",
                    f"{dep_desc} intermittently failing (24h)",
                    f"{dep_desc} was dead in {dead_count}/{total_checks} health "
                    f"checks ({dead_pct:.0%}) over the last 24 hours.",
                    f"Monitor {dep_name} stability. Check for network issues or "
                    f"rate limiting.",
                    f"Review dependency_health for error_message patterns on "
                    f"'{dep_name}' failures.",
                    f"External dependency stability ({dep_name})",
                    [],
                ))

        # Check for persistent degradation
        degraded_count = _safe_scalar(conn, """
            SELECT COUNT(*) FROM dependency_health
            WHERE dep_name = ? AND status = 'degraded'
              AND created_at >= datetime('now', '-24 hours')
        """, (dep_name,), default=0)

        if total_checks >= 6 and degraded_count >= total_checks * 0.5:
            dep_desc = dep_config["description"]
            findings.append(_finding(
                "engineering", "medium",
                f"{dep_desc} persistently degraded (24h)",
                f"{dep_desc} was degraded in {degraded_count}/{total_checks} "
                f"checks over the last 24 hours. Latency is above healthy "
                f"thresholds consistently.",
                f"Investigate {dep_name} performance. Consider infrastructure "
                f"changes or provider migration.",
                f"Review dependency_health for {dep_name} latency_ms trends.",
                f"External dependency performance ({dep_name})",
                [],
            ))

    return findings


ANALYZERS = [analyze_dependency_health]
