"""Tests for personalization module wiring.

Tests verify:
- Context data files load correctly
- get_personalized_sentences filters by HSK level
- Domain stats return correct counts
- Available domains match data files
"""

from pathlib import Path

from mandarin.personalization import (
    get_personalized_sentences,
    get_all_domains,
    get_available_domains,
    get_domain_stats,
    INTEREST_DOMAINS,
    _context_cache,
)


# ---- TestPersonalizationData ----

DATA_DIR = Path(__file__).parent.parent / "data" / "contexts"


def test_all_five_domains_have_data():
    """All 5 interest domains should have JSON data files."""
    for domain in INTEREST_DOMAINS:
        path = DATA_DIR / f"{domain}.json"
        assert path.exists(), f"Missing data file for domain: {domain}"


def test_available_domains_returns_all_five():
    available = get_available_domains()
    for domain in INTEREST_DOMAINS:
        assert domain in available


def test_domain_stats_non_empty():
    stats = get_domain_stats()
    for domain in INTEREST_DOMAINS:
        assert domain in stats
        assert stats[domain]["total"] > 0, f"Domain {domain} has no sentences"


# ---- TestPersonalizedSentences ----

def test_filter_by_hsk_level():
    """Only sentences at or below the given HSK level should be returned."""
    _context_cache.clear()
    sentences = get_personalized_sentences(2, "travel", n=50)
    for s in sentences:
        assert s["hsk_level"] <= 2, (
            f"Sentence '{s['hanzi']}' is HSK {s['hsk_level']}, above limit 2")


def test_returns_requested_count():
    """Should return at most n sentences."""
    _context_cache.clear()
    sentences = get_personalized_sentences(3, "civic", n=3)
    assert len(sentences) <= 3
    assert len(sentences) > 0


def test_sentence_has_required_fields():
    """Each sentence dict should have hanzi, pinyin, english, hsk_level."""
    _context_cache.clear()
    sentences = get_personalized_sentences(3, "culture", n=5)
    for s in sentences:
        assert "hanzi" in s
        assert "pinyin" in s
        assert "english" in s
        assert "hsk_level" in s


def test_unknown_domain_returns_empty():
    _context_cache.clear()
    sentences = get_personalized_sentences(3, "nonexistent_domain", n=5)
    assert sentences == []


# ---- TestDomainMetadata ----

def test_all_domains_returns_five():
    domains = get_all_domains()
    assert len(domains) == 9


def test_each_domain_has_label_and_description():
    for key, meta in INTEREST_DOMAINS.items():
        assert "label" in meta
        assert "description" in meta
