"""Lightweight health check scheduler — runs every 15 minutes.

Monitors critical system metrics and triggers immediate self-healing
remediation when issues are detected. Complements the nightly intelligence
audit with more frequent checks for time-sensitive issues.

Checks:
- Memory usage (clear caches, restart if critical)
- Disk pressure (clean temp files, truncate logs)
- Stale scheduler locks (release hung jobs)
- High error rates (disable failing features)
- Slow responses (throttle LLM calls)
- Database WAL size (run checkpoint)
- Core learning loop health (completion rates, error rates, breakpoints)
- External dependency health (LLM, TTS, Stripe, Resend, Plausible)
- Session diagnostics (auto-diagnose failed/abandoned sessions)
"""

import logging
import threading

from .. import db
from ..scheduler_lock import acquire_lock, release_lock

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 900  # 15 minutes
_INITIAL_DELAY = 120  # 2 minutes after startup — let app settle
_LOCK_TTL = 600  # 10 minutes — shorter than interval to avoid overlap

_stop_event = threading.Event()
_thread = None


def start():
    """Start the health check scheduler (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(
        target=_run_loop, daemon=True, name="health-check"
    )
    _thread.start()
    logger.info("Health check scheduler started (every %ds)", _CHECK_INTERVAL_SECONDS)


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Main loop — wait initial delay, then check every 15 minutes."""
    # Initial delay — let the app finish starting up
    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        conn = None
        try:
            conn = db.get_connection()

            # DB-backed lock: skip if another instance is already running
            if not acquire_lock(conn, "health_check", ttl_seconds=_LOCK_TTL):
                logger.debug("Health check: another instance holds the lock, skipping")
                if _stop_event.wait(_CHECK_INTERVAL_SECONDS):
                    break
                continue

            _health_check_tick(conn)
            release_lock(conn, "health_check")

        except Exception:
            logger.exception("Health check tick failed")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        # Wait until next check (or until stop signal)
        if _stop_event.wait(_CHECK_INTERVAL_SECONDS):
            break

    logger.info("Health check scheduler stopped")


def _health_check_tick(conn):
    """Single health check tick — collect metrics and remediate."""
    from ..intelligence.self_healing import run_health_check

    result = run_health_check(conn)

    # Log lifecycle event for observability
    try:
        from ..marketing_hooks import log_lifecycle_event
        log_lifecycle_event(
            "health_check",
            user_id="1",
            conn=conn,
            issues=len(result.get("issues_found", [])),
            actions=len(result.get("actions_taken", [])),
        )
    except Exception:
        pass

    # LLM cost monitoring: enforce spend limits and auto-recover
    try:
        from ..intelligence.cost_monitor import run_cost_check
        cost_result = run_cost_check(conn)
        if cost_result.get("actions"):
            logger.info(
                "Health check: cost monitor took %d action(s): %s",
                len(cost_result["actions"]),
                "; ".join(cost_result["actions"]),
            )
    except ImportError:
        pass
    except Exception:
        logger.debug("Health check: cost monitor failed", exc_info=True)

    # Lightweight analytics check: revert failing changes, advance rollouts
    try:
        from ..intelligence.analytics_auto_executor import run_analytics_actions_lightweight
        analytics_result = run_analytics_actions_lightweight(conn)
        if analytics_result.get("actions"):
            logger.info(
                "Health check: analytics auto-executor took %d action(s)",
                analytics_result.get("actions_count", 0),
            )
    except ImportError:
        pass
    except Exception:
        logger.debug("Health check: analytics auto-executor lightweight failed", exc_info=True)

    # Core learning loop monitor: session completion, drill errors, breakpoints
    try:
        from ..intelligence.core_loop_monitor import run_check as run_core_loop_check
        core_result = run_core_loop_check(conn)
        if core_result.get("actions_taken"):
            logger.info(
                "Health check: core loop monitor took %d action(s): %s",
                len(core_result["actions_taken"]),
                "; ".join(core_result["actions_taken"][:3]),
            )
    except ImportError:
        pass
    except Exception:
        logger.debug("Health check: core loop monitor failed", exc_info=True)

    # External dependency monitor: LLM, TTS, Stripe, Resend, Plausible
    try:
        from ..intelligence.dependency_monitor import run_check as run_dep_check
        dep_result = run_dep_check(conn)
        if dep_result.get("transitions"):
            logger.info(
                "Health check: dependency monitor — %d transition(s): %s",
                len(dep_result["transitions"]),
                "; ".join(t["action"] for t in dep_result["transitions"][:3]),
            )
    except ImportError:
        pass
    except Exception:
        logger.debug("Health check: dependency monitor failed", exc_info=True)

    # Session diagnostics: auto-diagnose failed/abandoned sessions
    try:
        from ..intelligence.session_diagnostics import run_check as run_session_diag
        diag_result = run_session_diag(conn)
        if diag_result.get("diagnosed", 0) > 0:
            logger.info(
                "Health check: session diagnostics diagnosed %d session(s) — %s",
                diag_result["diagnosed"],
                diag_result.get("classifications", {}),
            )
    except ImportError:
        pass
    except Exception:
        logger.debug("Health check: session diagnostics failed", exc_info=True)

    # Action ledger: verify pending actions past their verification window
    try:
        from ..intelligence.action_ledger import verify_pending_actions
        verify_result = verify_pending_actions(conn)
        if verify_result.get("verified", 0) > 0:
            logger.info(
                "Health check: action ledger verified %d action(s) — %d improved, %d regressed",
                verify_result["verified"],
                verify_result.get("improved", 0),
                verify_result.get("regressed", 0),
            )
    except ImportError:
        pass
    except Exception:
        logger.debug("Health check: action ledger verification failed", exc_info=True)

    # Contracts: seed default contracts (idempotent, runs once)
    try:
        from ..intelligence.contracts import seed_contracts
        seed_contracts(conn)
    except ImportError:
        pass
    except Exception:
        logger.debug("Health check: contract seeding failed", exc_info=True)
