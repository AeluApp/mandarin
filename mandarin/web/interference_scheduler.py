"""Background thread for periodic interference detection and density computation."""

import logging
import threading

from .. import db

logger = logging.getLogger(__name__)

_DAILY_SECONDS = 86400
_INITIAL_DELAY = 900  # Wait 900s after startup before first run

_stop_event = threading.Event()
_thread = None

# Strength weights for interference_density calculation
_STRENGTH_WEIGHTS = {"high": 1.0, "medium": 0.5, "low": 0.25}
_MAX_PARTNERS = 5.0  # Cap for normalization to [0, 1]


def start():
    """Start the interference detection background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="interference-detect")
    _thread.start()
    logger.info("Interference detection scheduler started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Detect interference pairs on startup + daily."""
    from ..scheduler_lock import acquire_lock, release_lock

    # Initial delay — let the app finish starting up
    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        # DB-backed lock: skip if another instance is already running
        try:
            with db.connection() as conn:
                if not acquire_lock(conn, "interference_detection", ttl_seconds=_DAILY_SECONDS):
                    logger.debug("Interference detection: another instance holds the lock, skipping")
                    if _stop_event.wait(_DAILY_SECONDS):
                        break
                    continue
        except Exception:
            logger.exception("Interference detection: lock acquisition failed")

        try:
            _run_detection()
        except Exception:
            logger.exception("Interference detection failed")

        # Release lock after work completes
        try:
            with db.connection() as conn:
                release_lock(conn, "interference_detection")
        except Exception:
            pass

        # Wait one day (or until stop signal)
        if _stop_event.wait(_DAILY_SECONDS):
            break

    logger.info("Interference detection scheduler stopped")


def _run_detection():
    """Run interference pair detection and update interference_density on progress rows."""
    from ..ai.memory_model import detect_interference_pairs

    with db.connection() as conn:
        # Step 1: Detect new interference pairs
        pairs = detect_interference_pairs(conn)
        logger.info("Interference detection: found %d pairs", len(pairs))

        # Step 2: Compute interference_density for each content_item with pairs
        _update_interference_density(conn)

        conn.commit()


def _update_interference_density(conn):
    """Compute and store interference_density on progress rows.

    For each content_item that has interference pairs, count partners weighted
    by strength (high=1.0, medium=0.5, low=0.25). Normalize to [0, 1] range
    (cap at 5 partners = 1.0).
    """
    try:
        rows = conn.execute("""
            SELECT item_id_a, item_id_b, interference_strength
            FROM interference_pairs
        """).fetchall()
    except Exception:
        logger.exception("Interference density: failed to read interference_pairs")
        return

    if not rows:
        logger.info("Interference density: no pairs to process")
        return

    # Accumulate weighted partner counts per content_item
    density_map = {}  # content_item_id -> weighted sum
    for row in rows:
        weight = _STRENGTH_WEIGHTS.get(row["interference_strength"], 0.25)
        for item_id in (row["item_id_a"], row["item_id_b"]):
            density_map[item_id] = density_map.get(item_id, 0.0) + weight

    # Normalize to [0, 1] and update progress rows
    updated = 0
    for content_item_id, raw_density in density_map.items():
        normalized = min(1.0, raw_density / _MAX_PARTNERS)
        try:
            cur = conn.execute(
                "UPDATE progress SET interference_density = ? WHERE content_item_id = ?",
                (round(normalized, 4), content_item_id),
            )
            if cur.rowcount > 0:
                updated += 1
        except Exception:
            logger.debug("Interference density: failed to update progress for item %d",
                         content_item_id)

    logger.info("Interference density: updated %d/%d progress rows",
                updated, len(density_map))
