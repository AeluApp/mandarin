"""Scenario loader — import and manage dialogue scenarios."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Support level constants ──────────────────────────────

SUPPORT_REMOVAL_AVG_SCORE = 0.75
SUPPORT_REMOVAL_MIN_PRESENTATIONS = 3


def determine_support_level(scenario: dict) -> str:
    """Determine dialogue support level based on presentation history.

    Returns "full_support", "pinyin_support", or "hanzi_only".
    - full_support: hanzi + pinyin + english (NPC lines and player options)
    - pinyin_support: hanzi + pinyin only (no english)
    - hanzi_only: hanzi only (P key reveals pinyin)
    """
    times = scenario.get("times_presented", 0) or 0
    avg = scenario.get("avg_score") or 0.0
    if times >= 4 and avg >= 0.80:
        return "hanzi_only"
    if times >= 2 and avg >= 0.65:
        return "pinyin_support"
    return "full_support"


def _validate_scenario(data: dict, file_path: str) -> list:
    """Validate scenario JSON structure. Returns list of error strings (empty = valid)."""
    errors = []
    if not data.get("title"):
        errors.append("missing 'title'")

    tree = data.get("tree", data)
    if not isinstance(tree, dict):
        errors.append("'tree' must be a dict")
        return errors

    turns = tree.get("turns")
    if not isinstance(turns, list) or len(turns) == 0:
        errors.append("'tree.turns' must be a non-empty list")
        return errors

    for i, turn in enumerate(turns):
        if not isinstance(turn, dict):
            errors.append(f"turn {i}: must be a dict")
            continue
        if "speaker" not in turn:
            errors.append(f"turn {i}: missing 'speaker'")
        if turn.get("speaker") == "player":
            options = turn.get("options")
            if not isinstance(options, list) or len(options) == 0:
                errors.append(f"turn {i}: player turn must have 'options' list")
            elif options:
                for j, opt in enumerate(options):
                    if not opt.get("text_zh"):
                        errors.append(f"turn {i}, option {j}: missing 'text_zh'")
                    if opt.get("score") is None:
                        errors.append(f"turn {i}, option {j}: missing 'score'")
        elif turn.get("speaker") == "npc":
            if not turn.get("text_zh"):
                errors.append(f"turn {i}: NPC turn missing 'text_zh'")

    hsk = data.get("hsk_level")
    if hsk is not None and not isinstance(hsk, int):
        errors.append(f"'hsk_level' must be an integer, got {type(hsk).__name__}")

    return errors


def load_scenario_file(conn, file_path: str, update_existing: bool = False) -> dict:
    """Load a single scenario JSON file into the database.

    If update_existing=True, updates tree_json on existing rows while
    preserving times_presented and avg_score. This lets us re-import
    enriched scenario files.

    Returns {"added": bool, "updated": bool, "title": str, "reason": str}.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON in scenario file %s: %s", file_path, e)
            return {"added": False, "updated": False, "title": "", "reason": f"invalid JSON: {e}"}

    # Validate structure before inserting
    validation_errors = _validate_scenario(data, file_path)
    if validation_errors:
        return {
            "added": False, "updated": False,
            "title": data.get("title", ""),
            "reason": f"validation failed: {'; '.join(validation_errors)}",
        }

    title = data["title"]

    tree_json = json.dumps(data.get("tree", data), ensure_ascii=False)

    # Check for duplicate
    existing = conn.execute(
        "SELECT id FROM dialogue_scenario WHERE title = ?", (title,)
    ).fetchone()
    if existing:
        if update_existing:
            conn.execute("""
                UPDATE dialogue_scenario SET
                    tree_json = ?,
                    title_zh = ?,
                    hsk_level = ?,
                    register = ?,
                    scenario_type = ?,
                    difficulty = ?
                WHERE id = ?
            """, (
                tree_json,
                data.get("title_zh", ""),
                data.get("hsk_level", 1),
                data.get("register", "neutral"),
                data.get("scenario_type", "dialogue"),
                data.get("difficulty", 0.5),
                existing["id"],
            ))
            conn.commit()
            return {"added": False, "updated": True, "title": title, "reason": "updated"}
        return {"added": False, "updated": False, "title": title, "reason": "duplicate"}

    conn.execute("""
        INSERT INTO dialogue_scenario
            (title, title_zh, hsk_level, register, scenario_type,
             tree_json, difficulty, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
    """, (
        title,
        data.get("title_zh", ""),
        data.get("hsk_level", 1),
        data.get("register", "neutral"),
        data.get("scenario_type", "dialogue"),
        tree_json,
        data.get("difficulty", 0.5),
    ))
    conn.commit()
    return {"added": True, "updated": False, "title": title, "reason": "ok"}


def load_scenario_dir(conn, dir_path: str, update_existing: bool = False) -> tuple:
    """Load all .json scenario files from a directory.

    Returns (added_count, skipped_count, updated_count).
    """
    added = 0
    skipped = 0
    updated = 0
    path = Path(dir_path)
    if not path.is_dir():
        raise FileNotFoundError(f"Directory not found: {dir_path}")

    for f in sorted(path.glob("*.json")):
        result = load_scenario_file(conn, str(f), update_existing=update_existing)
        if result["added"]:
            added += 1
        elif result.get("updated"):
            updated += 1
        else:
            skipped += 1

    return added, skipped, updated


def get_available_scenarios(conn, hsk_max: int = 9, limit: int = 50) -> list:
    """Get active scenarios at or below the learner's level."""
    rows = conn.execute("""
        SELECT * FROM dialogue_scenario
        WHERE status = 'active' AND hsk_level <= ?
        ORDER BY times_presented ASC, hsk_level ASC
        LIMIT ?
    """, (hsk_max, limit)).fetchall()
    return [dict(r) for r in rows]


def get_scenario_by_id(conn, scenario_id: int) -> dict:
    """Get a single scenario by ID."""
    row = conn.execute(
        "SELECT * FROM dialogue_scenario WHERE id = ?", (scenario_id,)
    ).fetchone()
    return dict(row) if row else None


def record_scenario_attempt(conn, scenario_id: int, score: float):
    """Update scenario stats after a presentation."""
    conn.execute("""
        UPDATE dialogue_scenario SET
            times_presented = times_presented + 1,
            avg_score = CASE
                WHEN avg_score IS NULL THEN ?
                ELSE (avg_score * times_presented + ?) / (times_presented + 1)
            END
        WHERE id = ?
    """, (score, score, scenario_id))
    conn.commit()
