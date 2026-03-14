"""Auto-link grammar points and skills to content items.

Uses hanzi substring matching + HSK level proximity to populate
content_grammar and content_skill tables that are currently empty.

Excludes lexicalized expressions where grammatical characters (不, 了, 的, etc.)
are fused into fixed compounds rather than functioning as live grammar markers.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _load_json(filename):
    try:
        with open(os.path.join(_DATA_DIR, filename)) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load grammar data file %s: %s", filename, e)
        raise


# ── Lazy-loaded data caches ──────────────────────────────
_GRAMMAR_DATA_CACHE = None


def _get_grammar_data():
    """Load grammar_patterns.json and return (patterns, exclusions, skill_patterns).

    Converts JSON arrays back to sets where the original code expected sets.
    """
    global _GRAMMAR_DATA_CACHE
    if _GRAMMAR_DATA_CACHE is not None:
        return _GRAMMAR_DATA_CACHE

    raw = _load_json("grammar_patterns.json")

    grammar_patterns = raw["grammar_patterns"]

    # Convert exclusion lists from JSON arrays to Python sets
    grammar_exclusions = {
        k: set(v) for k, v in raw["grammar_exclusions"].items()
    }

    # Convert skill keyword lists from JSON arrays to Python sets
    skill_patterns = {
        k: set(v) for k, v in raw["skill_patterns"].items()
    }

    _GRAMMAR_DATA_CACHE = (grammar_patterns, grammar_exclusions, skill_patterns)
    return _GRAMMAR_DATA_CACHE


def link_grammar_to_content(conn):
    """Auto-link grammar points to content items based on hanzi patterns.

    Returns the number of links created.
    """
    grammar_patterns, grammar_exclusions, _ = _get_grammar_data()

    grammar_points = conn.execute(
        "SELECT id, name, hsk_level FROM grammar_point"
    ).fetchall()

    gp_map = {row["name"]: (row["id"], row["hsk_level"]) for row in grammar_points}
    links_created = 0

    for gp_name, patterns in grammar_patterns.items():
        if gp_name not in gp_map:
            continue
        gp_id, gp_hsk = gp_map[gp_name]

        # Match items within HSK level range (gp_level-1 .. gp_level+1)
        hsk_min = max(1, gp_hsk - 1)
        hsk_max = gp_hsk + 1

        items = conn.execute("""
            SELECT id, hanzi FROM content_item
            WHERE status = 'drill_ready' AND hsk_level BETWEEN ? AND ?
        """, (hsk_min, hsk_max)).fetchall()

        # Get exclusion set for this grammar point
        exclusions = grammar_exclusions.get(gp_name, set())

        for item in items:
            hanzi = item["hanzi"]

            # Skip lexicalized compounds (short items where the character
            # is fused into a fixed expression, not an active grammar marker)
            if len(hanzi) <= 4 and hanzi in exclusions:
                continue

            # For "是...的 emphasis" — require BOTH 是 and 的,
            # but exclude items that are just possessive or simple 是-sentences
            if gp_name == "\u662f...\u7684 emphasis":
                if "\u662f" in hanzi and "\u7684" in hanzi and len(hanzi) >= 4:
                    conn.execute(
                        "INSERT OR IGNORE INTO content_grammar (content_item_id, grammar_point_id) VALUES (?, ?)",
                        (item["id"], gp_id)
                    )
                    links_created += 1
                continue

            # For direction complements — need multi-char patterns
            if gp_name == "Direction complement (\u6765/\u53bb/\u4e0a/\u4e0b)":
                # Only link if hanzi contains a direction compound
                if any(p in hanzi for p in patterns):
                    conn.execute(
                        "INSERT OR IGNORE INTO content_grammar (content_item_id, grammar_point_id) VALUES (?, ?)",
                        (item["id"], gp_id)
                    )
                    links_created += 1
                continue

            # Standard pattern: any pattern substring matches
            if any(p in hanzi for p in patterns):
                conn.execute(
                    "INSERT OR IGNORE INTO content_grammar (content_item_id, grammar_point_id) VALUES (?, ?)",
                    (item["id"], gp_id)
                )
                links_created += 1

    conn.commit()
    return links_created


def link_skills_to_content(conn):
    """Auto-link skills to content items based on english keyword matching.

    Returns the number of links created.
    """
    _, _, skill_patterns = _get_grammar_data()

    skills = conn.execute(
        "SELECT id, name, hsk_level FROM skill"
    ).fetchall()

    skill_map = {row["name"]: (row["id"], row["hsk_level"]) for row in skills}
    links_created = 0

    for skill_name, keywords in skill_patterns.items():
        if skill_name not in skill_map or not keywords:
            continue
        skill_id, skill_hsk = skill_map[skill_name]

        hsk_min = max(1, skill_hsk - 1)
        hsk_max = skill_hsk + 1

        items = conn.execute("""
            SELECT id, english FROM content_item
            WHERE status = 'drill_ready' AND hsk_level BETWEEN ? AND ?
        """, (hsk_min, hsk_max)).fetchall()

        for item in items:
            english_lower = (item["english"] or "").lower()
            if any(kw in english_lower for kw in keywords):
                conn.execute(
                    "INSERT OR IGNORE INTO content_skill (content_item_id, skill_id) VALUES (?, ?)",
                    (item["id"], skill_id)
                )
                links_created += 1

    conn.commit()
    return links_created


def link_all(conn):
    """Run both grammar and skill linking. Returns (grammar_links, skill_links)."""
    g = link_grammar_to_content(conn)
    s = link_skills_to_content(conn)
    return g, s
