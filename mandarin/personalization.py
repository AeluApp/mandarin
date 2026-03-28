"""Personalization engine — domain-tagged sentences for contextual learning.

Maps learner interests (civic, governance, urbanism, travel, culture)
to HSK-level-constrained example sentences. All content is deterministic —
no LLM calls at runtime.
"""

import json
import logging
import random
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


INTEREST_DOMAINS = {
    "civic": {
        "label": "Civic life",
        "description": "Community, public spaces, civic participation",
    },
    "governance": {
        "label": "Governance",
        "description": "Institutions, policy, social systems",
    },
    "urbanism": {
        "label": "Urbanism",
        "description": "Cities, architecture, transit, public infrastructure",
    },
    "travel": {
        "label": "Travel",
        "description": "Transportation, navigation, hospitality",
    },
    "culture": {
        "label": "Culture",
        "description": "Literature, philosophy, art, reflection",
    },
    "business": {
        "label": "Business",
        "description": "Commerce, meetings, professional communication",
    },
    "daily_life": {
        "label": "Daily life",
        "description": "Everyday conversation, errands, routines",
    },
    "food_culture": {
        "label": "Food & culture",
        "description": "Cuisine, dining, festivals, traditions",
    },
    "technology": {
        "label": "Technology",
        "description": "Internet, devices, apps, digital life",
    },
}


_DATA_DIR = Path(__file__).parent.parent / "data" / "contexts"

# Cache loaded contexts
_context_cache: dict = {}


def _load_domain(domain: str) -> list:
    """Load sentences for a domain from its JSON file."""
    if domain in _context_cache:
        return _context_cache[domain]

    path = _DATA_DIR / f"{domain}.json"
    if not path.exists():
        return []

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _context_cache[domain] = data.get("sentences", [])
        return _context_cache[domain]
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load personalization domain file: %s", path)
        return []


def get_personalized_sentences(hsk_level: int, domain: str,
                                n: int = 5) -> list[dict]:
    """Get n sentences for a domain at or below the given HSK level.

    Returns list of dicts with keys: hanzi, pinyin, english, hsk_level, domain.
    """
    sentences = _load_domain(domain)
    eligible = [s for s in sentences if s.get("hsk_level", 99) <= hsk_level]

    if not eligible:
        return []

    if len(eligible) <= n:
        return eligible

    return random.sample(eligible, n)


def get_all_domains() -> dict:
    """Return the domain metadata dict."""
    return INTEREST_DOMAINS


def get_available_domains() -> list[str]:
    """Return domains that have data files present."""
    available = []
    for domain in INTEREST_DOMAINS:
        path = _DATA_DIR / f"{domain}.json"
        if path.exists():
            available.append(domain)
    return available


def clear_personalization_cache() -> None:
    """Reset the domain context cache so data reloads on next access."""
    _context_cache.clear()


def clear_caches() -> None:
    """Reset all module-level caches in personalization."""
    clear_personalization_cache()


def get_domain_stats() -> dict:
    """Return sentence counts per domain per HSK level."""
    stats = {}
    for domain in INTEREST_DOMAINS:
        sentences = _load_domain(domain)
        by_level = {}
        for s in sentences:
            level = s.get("hsk_level", 0)
            by_level[level] = by_level.get(level, 0) + 1
        stats[domain] = {
            "total": len(sentences),
            "by_level": by_level,
        }
    return stats
