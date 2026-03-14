"""Real-world capability milestones — maps learning progress to life abilities.

Milestone definitions are loaded from data/milestones.json.
Each milestone has:
    key:       unique identifier
    label:     what the learner can now do (embodied competence)
    requires:  dict of {criterion: threshold}
        hsk_stable:    HSK level where mastered% >= threshold
        lens_pct:      content_lens coverage >= threshold
        scenario_avg:  scenario avg_score >= threshold
        sessions:      total sessions completed >=
        items_seen:    total distinct items attempted >=
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_VALID_REQUIREMENT_KEYS = {"sessions", "items_seen", "hsk_stable", "lens_pct", "scenario_avg"}
_VALID_PHASES = {"foundation", "emerging", "growing", "strengthening",
                 "intermediate", "advanced", "proficient", "mastery"}


def _load_milestones() -> list:
    """Load milestones from data/milestones.json with validation."""
    path = Path(__file__).parent.parent / "data" / "milestones.json"
    try:
        with open(path) as f:
            milestones = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load milestones from %s: %s", path, e)
        return []

    validated = []
    seen_keys = set()
    for i, m in enumerate(milestones):
        # Required fields
        for field in ("key", "label", "requires", "phase"):
            if field not in m:
                logger.warning("Milestone %d missing required field '%s', skipping", i, field)
                continue

        # Unique key check
        if m["key"] in seen_keys:
            logger.warning("Duplicate milestone key '%s', skipping", m["key"])
            continue
        seen_keys.add(m["key"])

        # Phase validation
        if m["phase"] not in _VALID_PHASES:
            logger.warning("Milestone '%s' has invalid phase '%s'", m["key"], m["phase"])

        # Requirement key validation
        bad_keys = set(m["requires"].keys()) - _VALID_REQUIREMENT_KEYS
        if bad_keys:
            logger.warning("Milestone '%s' has unknown requirement keys: %s", m["key"], bad_keys)

        # Convert hsk_stable keys from string to int (JSON keys are always strings)
        if "hsk_stable" in m["requires"]:
            m["requires"]["hsk_stable"] = {
                int(k): v for k, v in m["requires"]["hsk_stable"].items()
            }

        validated.append(m)

    logger.debug("Loaded %d milestones from %s", len(validated), path)
    return validated


MILESTONES = _load_milestones()

_REAL_WORLD_TASKS = None

def _load_real_world_tasks() -> list:
    """Load real-world task examples from data/real_world_tasks.json."""
    global _REAL_WORLD_TASKS
    if _REAL_WORLD_TASKS is not None:
        return _REAL_WORLD_TASKS
    path = Path(__file__).parent.parent / "data" / "real_world_tasks.json"
    try:
        with open(path) as f:
            data = json.load(f)
        _REAL_WORLD_TASKS = data.get("tasks", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.debug("Could not load real_world_tasks.json: %s", e)
        _REAL_WORLD_TASKS = []
    return _REAL_WORLD_TASKS


def get_real_world_tasks(hsk_level: int, limit: int = 3) -> list:
    """Return real-world tasks appropriate for the given HSK level.

    Returns up to `limit` tasks at or below the specified level,
    prioritizing the highest level tasks the learner can handle.
    """
    tasks = _load_real_world_tasks()
    eligible = [t for t in tasks if t.get("hsk_level", 99) <= hsk_level]
    # Prioritize highest-level tasks
    eligible.sort(key=lambda t: t.get("hsk_level", 0), reverse=True)
    return eligible[:limit]


def _get_growth_stats(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Gather all stats needed for milestone evaluation."""
    from .db.progress import get_mastery_by_hsk
    from .db.profile import get_profile

    profile = get_profile(conn, user_id=user_id)
    mastery = get_mastery_by_hsk(conn, user_id=user_id)

    # Items seen (distinct items with at least 1 attempt)
    row = conn.execute("""
        SELECT COUNT(DISTINCT content_item_id) as cnt
        FROM progress WHERE total_attempts > 0 AND user_id = ?
    """, (user_id,)).fetchone()
    items_seen = row["cnt"] if row else 0

    # Lens coverage: % of lens items with streak_correct >= 3
    lens_pct = {}
    lens_rows = conn.execute("""
        SELECT ci.content_lens,
               COUNT(DISTINCT ci.id) as total,
               COUNT(DISTINCT CASE WHEN p.streak_correct >= 3 THEN ci.id END) as stable
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.user_id = ?
        WHERE ci.content_lens IS NOT NULL AND ci.status = 'drill_ready'
        GROUP BY ci.content_lens
    """, (user_id,)).fetchall()
    for r in lens_rows:
        total = r["total"] or 0
        stable = r["stable"] or 0
        lens_pct[r["content_lens"]] = (stable / total * 100) if total > 0 else 0

    # Scenario avg scores
    scenario_rows = conn.execute("""
        SELECT id, avg_score, times_presented
        FROM dialogue_scenario WHERE times_presented > 0
    """).fetchall()
    scenario_avgs = {r["id"]: r["avg_score"] or 0 for r in scenario_rows}

    return {
        "sessions": profile.get("total_sessions", 0) or 0,
        "items_seen": items_seen,
        "mastery": mastery,  # {hsk_level: {pct, ...}}
        "lens_pct": lens_pct,
        "scenario_avgs": scenario_avgs,
    }


def _milestone_met(milestone: dict, stats: dict) -> bool:
    """Check if a milestone's requirements are all met."""
    reqs = milestone["requires"]

    if "sessions" in reqs:
        if stats["sessions"] < reqs["sessions"]:
            return False

    if "items_seen" in reqs:
        if stats["items_seen"] < reqs["items_seen"]:
            return False

    if "hsk_stable" in reqs:
        for hsk_level, min_pct in reqs["hsk_stable"].items():
            level_data = stats["mastery"].get(hsk_level, {})
            if level_data.get("mastered_pct", level_data.get("pct", 0)) < min_pct:
                return False

    if "lens_pct" in reqs:
        for lens, min_pct in reqs["lens_pct"].items():
            if stats["lens_pct"].get(lens, 0) < min_pct:
                return False

    if "scenario_avg" in reqs:
        for scenario_id, min_score in reqs["scenario_avg"].items():
            if stats["scenario_avgs"].get(scenario_id, 0) < min_score:
                return False

    return True


def get_unlocked_milestones(conn: sqlite3.Connection, user_id: int = 1) -> List[dict]:
    """Return all milestones the learner has currently unlocked."""
    stats = _get_growth_stats(conn, user_id=user_id)
    return [m for m in MILESTONES if _milestone_met(m, stats)]


def get_growth_summary(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Return a growth summary with unlocked milestones and current phase.

    Returns:
        {
            "unlocked": [milestone_dicts],
            "latest": milestone_dict or None,
            "next": milestone_dict or None,
            "phase": "foundation"|"emerging"|"growing"|"strengthening",
            "phase_label": "Building foundation" | "Skills emerging" | ...
            "items_seen": int,
            "total_sessions": int,
        }
    """
    stats = _get_growth_stats(conn, user_id=user_id)
    unlocked = [m for m in MILESTONES if _milestone_met(m, stats)]
    locked = [m for m in MILESTONES if not _milestone_met(m, stats)]

    latest = unlocked[-1] if unlocked else None
    next_milestone = locked[0] if locked else None

    phase = latest["phase"] if latest else "foundation"
    phase_labels = {
        "foundation": "Building foundation",
        "emerging": "Skills emerging",
        "growing": "Growing steadily",
        "strengthening": "Strengthening fluency",
        "intermediate": "Intermediate fluency",
        "advanced": "Advanced proficiency",
        "proficient": "Professional proficiency",
        "mastery": "Approaching mastery",
    }

    return {
        "unlocked": unlocked,
        "latest": latest,
        "next": next_milestone,
        "phase": phase,
        "phase_label": phase_labels.get(phase, phase),
        "items_seen": stats["items_seen"],
        "total_sessions": stats["sessions"],
    }


def get_stage_counts(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Return counts of items at each mastery stage.

    Returns all 6 stages + unseen. Also includes backward-compat aliases
    'weak' (seen + passed_once) and 'improving' (stabilizing).
    """
    row = conn.execute("""
        SELECT
            COUNT(DISTINCT CASE WHEN p.mastery_stage = 'seen' THEN ci.id END) as seen_stage,
            COUNT(DISTINCT CASE WHEN p.mastery_stage = 'passed_once' THEN ci.id END) as passed_once,
            COUNT(DISTINCT CASE WHEN p.mastery_stage = 'stabilizing' THEN ci.id END) as stabilizing,
            COUNT(DISTINCT CASE WHEN p.mastery_stage = 'stable' THEN ci.id END) as stable,
            COUNT(DISTINCT CASE WHEN p.mastery_stage = 'durable' THEN ci.id END) as durable,
            COUNT(DISTINCT CASE WHEN p.mastery_stage = 'decayed' THEN ci.id END) as decayed,
            COUNT(DISTINCT CASE WHEN p.total_attempts IS NULL OR p.total_attempts = 0 THEN ci.id END) as unseen
        FROM content_item ci
        LEFT JOIN progress p ON ci.id = p.content_item_id AND p.user_id = ?
        WHERE ci.status = 'drill_ready'
    """, (user_id,)).fetchone()
    seen_stage = row["seen_stage"] or 0
    passed_once = row["passed_once"] or 0
    stabilizing = row["stabilizing"] or 0
    stable = row["stable"] or 0
    durable = row["durable"] or 0
    decayed = row["decayed"] or 0
    return {
        "seen": seen_stage,
        "passed_once": passed_once,
        "stabilizing": stabilizing,
        "stable": stable,
        "durable": durable,
        "decayed": decayed,
        "unseen": row["unseen"] or 0,
        # Backward-compat aliases
        "weak": seen_stage + passed_once,
        "improving": stabilizing,
    }
