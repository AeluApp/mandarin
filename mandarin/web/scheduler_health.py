"""Scheduler health monitoring — crash recovery and heartbeat tracking.

Tracks all background scheduler threads. A monitor thread checks every 5 minutes
and restarts any that have died silently (up to 5 restarts per scheduler).
"""

import logging
import threading
import time
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Registry of active scheduler threads
_schedulers: dict[str, dict] = {}
_lock = threading.Lock()

MAX_RESTARTS = 5
CHECK_INTERVAL_SECONDS = 300  # 5 minutes


def register(name: str, thread: threading.Thread, start_fn: callable) -> None:
    """Register a scheduler thread for health monitoring.

    Args:
        name: Human-readable scheduler name (used in logs and status).
        thread: The daemon thread to monitor.
        start_fn: Callable to invoke if the thread dies (must be idempotent).
    """
    with _lock:
        _schedulers[name] = {
            "thread": thread,
            "start_fn": start_fn,
            "started_at": datetime.now(UTC),
            "restarts": 0,
            "last_restart": None,
        }


def check_health() -> dict[str, str]:
    """Check all registered schedulers. Restart any that have died.

    Returns:
        Dict of {name: status} where status is 'running', 'restarted', or 'failed'.
    """
    results = {}
    with _lock:
        for name, info in _schedulers.items():
            thread = info["thread"]
            if thread.is_alive():
                results[name] = "running"
                continue

            # Thread died — attempt restart (max MAX_RESTARTS)
            if info["restarts"] >= MAX_RESTARTS:
                results[name] = "failed"
                logger.error(
                    "Scheduler '%s' exceeded max restarts (%d), not restarting",
                    name,
                    MAX_RESTARTS,
                )
                continue

            logger.warning(
                "Scheduler '%s' died, restarting (attempt %d/%d)",
                name,
                info["restarts"] + 1,
                MAX_RESTARTS,
            )
            try:
                info["start_fn"]()
                info["restarts"] += 1
                info["last_restart"] = datetime.now(UTC)
                # Update the thread reference — start() creates a new thread
                # and stores it in the module's _thread global.
                _update_thread_ref(name, info)
                results[name] = "restarted"
            except Exception:
                logger.exception("Failed to restart scheduler '%s'", name)
                results[name] = "failed"

    return results


def _update_thread_ref(name: str, info: dict) -> None:
    """After restart, update the stored thread reference from the module.

    Each scheduler module stores its thread in a module-level _thread global.
    After calling start_fn(), the module will have replaced _thread with the
    new thread. We need to re-read it.
    """
    start_fn = info["start_fn"]
    # start_fn is an imported function — its __module__ tells us where it lives
    import sys

    module_name = getattr(start_fn, "__module__", None)
    if module_name and module_name in sys.modules:
        module = sys.modules[module_name]
        new_thread = getattr(module, "_thread", None)
        if new_thread is not None and isinstance(new_thread, threading.Thread):
            info["thread"] = new_thread


def get_status() -> list[dict]:
    """Return status of all registered schedulers.

    Returns:
        List of dicts with name, alive, restarts, started_at, last_restart.
    """
    with _lock:
        return [
            {
                "name": name,
                "alive": info["thread"].is_alive(),
                "restarts": info["restarts"],
                "started_at": info["started_at"].isoformat(),
                "last_restart": (
                    info["last_restart"].isoformat() if info["last_restart"] else None
                ),
            }
            for name, info in _schedulers.items()
        ]


def start_monitor() -> threading.Thread:
    """Start the health monitor background thread.

    Returns:
        The monitor thread (already started).
    """
    monitor = threading.Thread(
        target=_monitor_loop, daemon=True, name="scheduler-health-monitor"
    )
    monitor.start()
    logger.info("Scheduler health monitor started (interval=%ds)", CHECK_INTERVAL_SECONDS)
    return monitor


def _monitor_loop() -> None:
    """Periodically check scheduler health and restart dead threads."""
    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        try:
            results = check_health()
            # Only log if something interesting happened
            issues = {k: v for k, v in results.items() if v != "running"}
            if issues:
                logger.warning("Scheduler health check: %s", issues)
        except Exception:
            logger.exception("Scheduler health check failed")
