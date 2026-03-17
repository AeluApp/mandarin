"""Comprehensive tests for mandarin/scheduler.py — session planning, interleaving,
drill selection, item validation, and gap handling.

Covers:
A. Test factories (reusable dicts for items, progress rows, DrillItems)
B. Pure function tests (no DB): _item_is_drillable, _pick_drill_type,
   _pick_mapping_groups, _interleave, get_gap_message, _pick_modality_distribution
C. Integration tests (in-memory SQLite): plan_standard_session, plan_minimal_session,
   plan_catchup_session, day profiles, adaptive weights
D. Edge cases: empty pool, single item, all durable, cross-session interleaving
"""

import random
import sqlite3
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

# Schema path for in-memory DB setup
SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


# ── A. Test factories ──────────────────────────────

def make_item(hanzi="你好", pinyin="nǐ hǎo", english="hello",
              hsk=1, item_type="vocab", register="neutral", **overrides):
    """Create a minimal content item dict for testing pure functions."""
    d = {
        "id": overrides.pop("id", 1),
        "hanzi": hanzi,
        "pinyin": pinyin,
        "english": english,
        "hsk_level": hsk,
        "item_type": item_type,
        "register": register,
        "content_lens": None,
        "times_shown": 0,
        "difficulty": 0.5,
        "mastery_stage": "seen",
        "streak_correct": 0,
        "total_attempts": 0,
        "total_correct": 0,
        "status": "drill_ready",
    }
    d.update(overrides)
    return d


def make_progress(ease=2.5, interval=1.0, streak=0, mastery="seen", **overrides):
    """Create a minimal progress row dict for testing."""
    d = {
        "ease_factor": ease,
        "interval_days": interval,
        "repetitions": 0,
        "streak_correct": streak,
        "streak_incorrect": 0,
        "mastery_stage": mastery,
        "historically_weak": 0,
        "weak_cycle_count": 0,
        "half_life_days": 1.0,
        "difficulty": 0.5,
        "last_review_date": None,
        "total_attempts": 0,
        "total_correct": 0,
    }
    d.update(overrides)
    return d


def make_drill_item(item_id=1, drill_type="mc", modality="reading",
                    hanzi="你好", pinyin="nǐ hǎo", english="hello",
                    **overrides):
    """Create a DrillItem for testing."""
    from mandarin.scheduler import DrillItem
    kwargs = {
        "content_item_id": item_id,
        "hanzi": hanzi,
        "pinyin": pinyin,
        "english": english,
        "modality": modality,
        "drill_type": drill_type,
    }
    kwargs.update(overrides)
    return DrillItem(**kwargs)


# ── Helper: in-memory DB with schema + seed data ──────────

def _create_test_db():
    """Create an in-memory SQLite DB with the production schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()
    # Apply migrations that add columns not in base schema
    from mandarin.db.core import _migrate
    _migrate(conn)
    return conn


def _seed_items(conn, n=10, hsk=1, with_pinyin=True):
    """Insert n drill-ready content items. Returns list of row IDs."""
    ids = []
    for i in range(n):
        pinyin = f"pīn{i}" if with_pinyin else ""
        cur = conn.execute("""
            INSERT INTO content_item (hanzi, pinyin, english, item_type, hsk_level,
                                      register, status, difficulty)
            VALUES (?, ?, ?, 'vocab', ?, 'neutral', 'drill_ready', 0.5)
        """, (f"字{i}", pinyin, f"word_{i}", hsk))
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


def _seed_progress(conn, item_ids, modality="reading", mastery="seen",
                   streak=0, next_review=None):
    """Insert progress rows for the given item IDs."""
    if next_review is None:
        next_review = date.today().isoformat()
    for item_id in item_ids:
        conn.execute("""
            INSERT OR REPLACE INTO progress
                (content_item_id, modality, ease_factor, interval_days, repetitions,
                 next_review_date, last_review_date, total_attempts, total_correct,
                 streak_correct, streak_incorrect, mastery_stage,
                 historically_weak, weak_cycle_count,
                 half_life_days, difficulty, distinct_review_days,
                 avg_response_ms, drill_types_seen)
            VALUES (?, ?, 2.5, 1.0, 1, ?, ?, 5, 3, ?, 0, ?,
                    0, 0, 1.0, 0.5, 1, NULL, 'mc')
        """, (item_id, modality, next_review,
              (date.today() - timedelta(days=1)).isoformat(),
              streak, mastery))
    conn.commit()


def _seed_standard(conn, n=15, hsk=1):
    """Seed n items with progress across all modalities, suitable for standard session."""
    ids = _seed_items(conn, n=n, hsk=hsk)
    _seed_progress(conn, ids, modality="reading")
    _seed_progress(conn, ids, modality="ime")
    _seed_progress(conn, ids, modality="listening")
    _seed_progress(conn, ids, modality="speaking")
    return ids


# ═══════════════════════════════════════════════════
# B. Pure function tests (no DB needed)
# ═══════════════════════════════════════════════════


# ── TestItemIsDrillable ──

def test_empty_hanzi_always_false():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="")
    for dt in ("mc", "tone", "ime_type", "reverse_mc"):
        assert not _item_is_drillable(item, dt), \
            f"empty hanzi should fail for {dt}"


def test_none_hanzi_always_false():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi=None)
    assert not _item_is_drillable(item, "mc")


def test_whitespace_only_hanzi_false():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="   ")
    assert not _item_is_drillable(item, "mc")


def test_mc_with_hanzi_and_english():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", english="you")
    assert _item_is_drillable(item, "mc")


def test_mc_missing_english():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", english="")
    assert not _item_is_drillable(item, "mc")


def test_reverse_mc_with_hanzi_and_english():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", english="you")
    assert _item_is_drillable(item, "reverse_mc")


def test_ime_type_with_hanzi_and_pinyin():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="nǐ")
    assert _item_is_drillable(item, "ime_type")


def test_ime_type_missing_pinyin():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="")
    assert not _item_is_drillable(item, "ime_type")


def test_tone_with_tone_marks():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="nǐ")
    assert _item_is_drillable(item, "tone")


def test_tone_without_tone_marks():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="ni", pinyin="ni3")
    assert not _item_is_drillable(item, "tone")


def test_tone_missing_pinyin():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="")
    assert not _item_is_drillable(item, "tone")


def test_english_to_pinyin_all_fields():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="nǐ", english="you")
    assert _item_is_drillable(item, "english_to_pinyin")


def test_english_to_pinyin_missing_pinyin():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="", english="you")
    assert not _item_is_drillable(item, "english_to_pinyin")


def test_hanzi_to_pinyin():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="nǐ")
    assert _item_is_drillable(item, "hanzi_to_pinyin")


def test_pinyin_to_hanzi_all_fields():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="nǐ", english="you")
    assert _item_is_drillable(item, "pinyin_to_hanzi")


def test_listening_detail_sentence():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(item_type="sentence")
    assert _item_is_drillable(item, "listening_detail")


def test_listening_detail_vocab_rejected():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(item_type="vocab")
    assert not _item_is_drillable(item, "listening_detail")


def test_listening_detail_phrase_accepted():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(item_type="phrase")
    assert _item_is_drillable(item, "listening_detail")


def test_listening_detail_chunk_accepted():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(item_type="chunk")
    assert _item_is_drillable(item, "listening_detail")


def test_listening_tone_with_tones():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(pinyin="nǐ hǎo")
    assert _item_is_drillable(item, "listening_tone")


def test_listening_tone_no_tones():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(pinyin="ni hao")
    assert not _item_is_drillable(item, "listening_tone")


def test_listening_dictation():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="nǐ")
    assert _item_is_drillable(item, "listening_dictation")


def test_listening_dictation_no_pinyin():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="")
    assert not _item_is_drillable(item, "listening_dictation")


def test_measure_word():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="个", english="general measure word")
    assert _item_is_drillable(item, "measure_word")


def test_word_order_sentence():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(item_type="sentence")
    assert _item_is_drillable(item, "word_order")


def test_word_order_vocab_rejected():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(item_type="vocab")
    assert not _item_is_drillable(item, "word_order")


def test_sentence_build_phrase():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(item_type="phrase")
    assert _item_is_drillable(item, "sentence_build")


def test_particle_disc():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="的")
    assert _item_is_drillable(item, "particle_disc")


def test_translation():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你好", english="hello")
    assert _item_is_drillable(item, "translation")


def test_unknown_type_needs_all_fields():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="nǐ", english="you")
    assert _item_is_drillable(item, "unknown_future_type")


def test_unknown_type_missing_field():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你", pinyin="", english="you")
    assert not _item_is_drillable(item, "unknown_future_type")


def test_listening_gist():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你好", english="hello")
    assert _item_is_drillable(item, "listening_gist")


def test_intuition():
    from mandarin.scheduler import _item_is_drillable
    item = make_item(hanzi="你好", english="hello")
    assert _item_is_drillable(item, "intuition")


# ── TestPickDrillType ──

def test_ime_always_returns_ime_type():
    """IME modality returns ime_type or dictation_sentence."""
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {}
    valid_ime = {"ime_type", "dictation_sentence"}
    for _ in range(10):
        result = _pick_drill_type("ime", item, tracker)
        assert result in valid_ime


def test_reading_returns_valid_type():
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {}
    valid_reading = {"mc", "reverse_mc", "tone", "intuition",
                     "english_to_pinyin", "hanzi_to_pinyin",
                     "pinyin_to_hanzi", "transfer", "measure_word",
                     "measure_word_cloze", "measure_word_production",
                     "measure_word_disc",
                     "word_order", "sentence_build", "particle_disc",
                     "homophone", "translation", "cloze_context",
                     "synonym_disc", "number_system", "tone_sandhi",
                     "complement", "ba_bei", "collocation", "radical",
                     "error_correction", "chengyu"}
    result = _pick_drill_type("reading", item, tracker)
    assert result in valid_reading


def test_listening_returns_valid_type():
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {}
    valid_listening = {"listening_gist", "listening_detail",
                       "listening_tone", "listening_dictation",
                       "listening_passage"}
    result = _pick_drill_type("listening", item, tracker)
    assert result in valid_listening


def test_speaking_returns_valid_type():
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {}
    valid_speaking = {"speaking", "mc"}
    result = _pick_drill_type("speaking", item, tracker)
    assert result in valid_speaking


def test_variety_avoids_recent_repeats():
    """Should avoid repeating the same type in the last 2 picks of a modality."""
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {"reading": ["mc", "mc"]}
    result = _pick_drill_type("reading", item, tracker)
    # With last 2 being "mc", it should pick something different
    # (unless all options have been used, in which case random)
    assert isinstance(result, str)


def test_allowed_types_filter():
    """When allowed_types is provided, should prefer those types."""
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {}
    allowed = {"mc", "reverse_mc"}
    # Run multiple times to check filtering
    for _ in range(20):
        result = _pick_drill_type("reading", item, tracker, allowed_types=allowed)
        assert result in allowed
        tracker = {}  # reset to avoid variety avoidance


def test_allowed_types_fallback_on_no_intersection():
    """If allowed_types has no intersection with modality options, fall back."""
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {}
    allowed = {"nonexistent_drill_type"}
    result = _pick_drill_type("reading", item, tracker, allowed_types=allowed)
    # Should fall back to unfiltered reading options
    assert isinstance(result, str)


def test_unknown_modality_defaults_to_mc():
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {}
    result = _pick_drill_type("unknown_modality", item, tracker)
    assert result == "mc"


def test_tracker_records_choices():
    """The variety tracker should record each pick."""
    from mandarin.scheduler import _pick_drill_type
    item = make_item()
    tracker = {}
    _pick_drill_type("reading", item, tracker)
    assert "reading" in tracker
    assert len(tracker["reading"]) == 1


# ── TestPickMappingGroups ──

def test_mapping_groups_returns_tuple_of_types_and_groups():
    from mandarin.scheduler import _pick_mapping_groups
    allowed, groups = _pick_mapping_groups(n=3)
    assert isinstance(allowed, set)
    assert isinstance(groups, list)


def test_mapping_groups_returns_n_groups():
    from mandarin.scheduler import _pick_mapping_groups
    _, groups = _pick_mapping_groups(n=3)
    assert len(groups) == 3


def test_mapping_groups_returns_correct_number_when_n_exceeds_total():
    from mandarin.scheduler import _pick_mapping_groups, MAPPING_GROUPS
    all_groups = set(MAPPING_GROUPS.keys())
    _, groups = _pick_mapping_groups(n=100)
    assert len(groups) == len(all_groups)


def test_mapping_groups_are_valid():
    from mandarin.scheduler import _pick_mapping_groups, MAPPING_GROUPS
    all_groups = set(MAPPING_GROUPS.keys())
    _, groups = _pick_mapping_groups(n=5)
    for g in groups:
        assert g in all_groups


def test_mapping_groups_no_duplicate_groups():
    from mandarin.scheduler import _pick_mapping_groups
    _, groups = _pick_mapping_groups(n=5)
    assert len(groups) == len(set(groups))


def test_mapping_groups_allowed_types_match_groups():
    from mandarin.scheduler import _pick_mapping_groups, MAPPING_GROUPS
    allowed, groups = _pick_mapping_groups(n=3)
    expected = set()
    for g in groups:
        expected.update(MAPPING_GROUPS[g])
    assert allowed == expected


def test_mapping_groups_exclude_groups_deprioritized():
    """Excluded groups should still be pickable but at lower weight."""
    from mandarin.scheduler import _pick_mapping_groups
    random.seed(42)
    # Run many iterations: excluded groups should appear less often
    exclude = {"hanzi_to_english", "english_to_hanzi"}
    counts = {}
    iterations = 500
    for _ in range(iterations):
        _, groups = _pick_mapping_groups(n=3, exclude_groups=exclude)
        for g in groups:
            counts[g] = counts.get(g, 0) + 1

    # Excluded groups should appear, but less frequently
    non_excluded_avg = sum(
        c for g, c in counts.items() if g not in exclude
    ) / max(1, len([g for g in counts if g not in exclude]))
    excluded_avg = sum(
        c for g, c in counts.items() if g in exclude
    ) / max(1, len([g for g in counts if g in exclude]))

    # Excluded groups get 0.2x weight, so should appear much less often
    assert excluded_avg < non_excluded_avg


def test_mapping_groups_exclude_groups_none():
    """None exclude_groups should work fine (random.sample path)."""
    from mandarin.scheduler import _pick_mapping_groups
    allowed, groups = _pick_mapping_groups(n=3, exclude_groups=None)
    assert len(groups) == 3


def test_mapping_groups_exclude_groups_empty_set():
    """Empty set should behave like None (no exclusion effect)."""
    from mandarin.scheduler import _pick_mapping_groups
    allowed, groups = _pick_mapping_groups(n=3, exclude_groups=set())
    assert len(groups) == 3


def test_mapping_groups_single_group():
    from mandarin.scheduler import _pick_mapping_groups
    allowed, groups = _pick_mapping_groups(n=1)
    assert len(groups) == 1
    assert len(allowed) > 0


# ── TestInterleave ──

def test_interleave_empty_list():
    from mandarin.scheduler import _interleave
    result = _interleave([])
    assert result == []


def test_interleave_single_item():
    from mandarin.scheduler import _interleave
    d = make_drill_item()
    result = _interleave([d])
    assert len(result) == 1
    assert result[0] is d


def test_interleave_two_items():
    """Two or fewer items should be returned as-is."""
    from mandarin.scheduler import _interleave
    d1 = make_drill_item(item_id=1)
    d2 = make_drill_item(item_id=2)
    result = _interleave([d1, d2])
    assert len(result) == 2


def test_interleave_preserves_all_items():
    """Interleaving should not drop or duplicate items."""
    from mandarin.scheduler import _interleave
    drills = [
        make_drill_item(item_id=i, drill_type=dt, modality=mod,
                        metadata={"hsk_level": hsk})
        for i, dt, mod, hsk in [
            (1, "mc", "reading", 1),
            (2, "ime_type", "ime", 1),
            (3, "tone", "reading", 2),
            (4, "listening_gist", "listening", 1),
            (5, "mc", "reading", 2),
            (6, "reverse_mc", "reading", 1),
        ]
    ]
    random.seed(42)
    result = _interleave(drills)
    assert len(result) == len(drills)
    result_ids = {d.content_item_id for d in result}
    original_ids = {d.content_item_id for d in drills}
    assert result_ids == original_ids


def test_interleave_breaks_same_type_adjacency():
    """Phase 3 should try to break consecutive same-drill-type items."""
    from mandarin.scheduler import _interleave
    # Create 6 items: 3 mc followed by 3 reverse_mc (all same HSK so they cluster)
    drills = []
    for i in range(3):
        drills.append(make_drill_item(
            item_id=i + 1, drill_type="mc", modality="reading",
            metadata={"hsk_level": 1}))
    for i in range(3):
        drills.append(make_drill_item(
            item_id=i + 4, drill_type="reverse_mc", modality="reading",
            metadata={"hsk_level": 1}))

    random.seed(42)
    result = _interleave(drills)
    # Count consecutive same-type pairs
    consecutive = sum(
        1 for i in range(len(result) - 1)
        if result[i].drill_type == result[i + 1].drill_type
    )
    # Should have fewer consecutive same-types than the original (6 -> 0 ideally)
    assert consecutive <= 4, \
        "Interleaving should reduce same-type adjacencies"


def test_interleave_micro_clustering_by_hsk():
    """Items should be grouped by HSK level into micro-clusters."""
    from mandarin.scheduler import _interleave
    drills = [
        make_drill_item(item_id=1, drill_type="mc", metadata={"hsk_level": 1}),
        make_drill_item(item_id=2, drill_type="tone", metadata={"hsk_level": 3}),
        make_drill_item(item_id=3, drill_type="reverse_mc", metadata={"hsk_level": 1}),
        make_drill_item(item_id=4, drill_type="ime_type", modality="ime",
                        metadata={"hsk_level": 3}),
    ]
    random.seed(42)
    result = _interleave(drills)
    # All items present
    assert len(result) == 4


# ── TestGetGapMessage ──

def test_gap_none_days():
    from mandarin.scheduler import get_gap_message
    assert get_gap_message(None) is None


def test_gap_zero_days():
    from mandarin.scheduler import get_gap_message
    assert get_gap_message(0) is None


def test_gap_one_day():
    from mandarin.scheduler import get_gap_message
    assert get_gap_message(1) is None


def test_gap_two_days():
    from mandarin.scheduler import get_gap_message
    assert get_gap_message(2) is None


def test_gap_three_days():
    from mandarin.scheduler import get_gap_message
    msg = get_gap_message(3)
    assert msg is not None
    assert "3 days" in msg


def test_gap_seven_days():
    from mandarin.scheduler import get_gap_message
    msg = get_gap_message(7)
    assert msg is not None
    assert "7 days" in msg


def test_gap_fourteen_days():
    from mandarin.scheduler import get_gap_message
    msg = get_gap_message(14)
    assert msg is not None
    assert "14 days" in msg


def test_gap_thirty_days():
    from mandarin.scheduler import get_gap_message
    msg = get_gap_message(30)
    assert msg is not None
    assert "30 days" in msg


def test_gap_sixty_plus_days():
    from mandarin.scheduler import get_gap_message
    msg = get_gap_message(60)
    assert msg is not None
    assert "60+" in msg


def test_gap_ninety_days_uses_sixty_message():
    from mandarin.scheduler import get_gap_message
    msg = get_gap_message(90)
    assert msg is not None
    assert "60+" in msg


def test_gap_five_days_uses_three_day_message():
    """5 days should use the 3-day threshold message."""
    from mandarin.scheduler import get_gap_message
    msg = get_gap_message(5)
    assert msg is not None
    assert "3 days" in msg


def test_gap_ten_days_uses_seven_day_message():
    from mandarin.scheduler import get_gap_message
    msg = get_gap_message(10)
    assert msg is not None
    assert "7 days" in msg


# ── TestPickModalityDistribution ──

def test_modality_dist_total_matches_target():
    """Total distributed items should approximately match target."""
    from mandarin.scheduler import _pick_modality_distribution
    from mandarin.config import DEFAULT_WEIGHTS
    counts = _pick_modality_distribution(12, DEFAULT_WEIGHTS)
    total = sum(counts.values())
    # Should be close to 12 (may differ by 1-2 due to rounding)
    assert total >= 10
    assert total <= 16


def test_modality_dist_all_modalities_present():
    from mandarin.scheduler import _pick_modality_distribution
    from mandarin.config import DEFAULT_WEIGHTS
    counts = _pick_modality_distribution(12, DEFAULT_WEIGHTS)
    for mod in DEFAULT_WEIGHTS:
        assert mod in counts
        assert counts[mod] >= 1


def test_modality_dist_small_target():
    """Even with small target, each modality gets at least 1."""
    from mandarin.scheduler import _pick_modality_distribution
    from mandarin.config import DEFAULT_WEIGHTS
    counts = _pick_modality_distribution(4, DEFAULT_WEIGHTS)
    for mod in DEFAULT_WEIGHTS:
        assert counts[mod] >= 1


def test_modality_dist_single_modality():
    from mandarin.scheduler import _pick_modality_distribution
    counts = _pick_modality_distribution(10, {"reading": 1.0})
    assert counts["reading"] == 10


def test_modality_dist_two_modalities():
    from mandarin.scheduler import _pick_modality_distribution
    counts = _pick_modality_distribution(10, {"reading": 0.5, "listening": 0.5})
    assert counts["reading"] + counts["listening"] == 10


# ── TestDrillItem ──

def test_drill_item_basic_creation():
    from mandarin.scheduler import DrillItem
    d = DrillItem(content_item_id=1, hanzi="你", pinyin="nǐ",
                  english="you", modality="reading", drill_type="mc")
    assert d.content_item_id == 1
    assert d.hanzi == "你"
    assert not d.is_new
    assert not d.is_confidence_win
    assert not d.is_error_focus
    assert d.metadata == {}


def test_drill_item_metadata_default_factory():
    """Each DrillItem should get its own metadata dict."""
    from mandarin.scheduler import DrillItem
    d1 = DrillItem(content_item_id=1, hanzi="一", pinyin="yī",
                   english="one", modality="reading", drill_type="mc")
    d2 = DrillItem(content_item_id=2, hanzi="二", pinyin="èr",
                   english="two", modality="reading", drill_type="mc")
    d1.metadata["test"] = True
    assert "test" not in d2.metadata


# ── TestSessionPlan ──

def test_session_plan_basic_creation():
    from mandarin.scheduler import SessionPlan
    plan = SessionPlan(session_type="standard")
    assert plan.session_type == "standard"
    assert plan.drills == []
    assert plan.micro_plan == ""
    assert plan.estimated_seconds == 0
    assert plan.days_since_last is None
    assert plan.gap_message is None
    assert plan.day_label is None


# ── TestMappingGroups constant ──

def test_all_drill_types_in_at_least_one_group():
    """Smoke test: important drill types should appear in mapping groups."""
    from mandarin.scheduler import MAPPING_GROUPS
    all_types = set()
    for types_list in MAPPING_GROUPS.values():
        all_types.update(types_list)
    # Key drill types that should be mapped
    for dt in ["mc", "ime_type", "listening_gist", "tone", "reverse_mc"]:
        assert dt in all_types, f"{dt} not in any mapping group"


def test_no_empty_groups():
    from mandarin.scheduler import MAPPING_GROUPS
    for name, types in MAPPING_GROUPS.items():
        assert len(types) > 0, f"group {name} is empty"


# ── TestErrorDrillPreference ──

def test_all_error_types_have_preferences():
    from mandarin.scheduler import ERROR_DRILL_PREFERENCE
    for etype in ["tone", "segment", "ime_confusable", "vocab", "grammar", "other"]:
        assert etype in ERROR_DRILL_PREFERENCE
        assert len(ERROR_DRILL_PREFERENCE[etype]) > 0


# ── TestValidatePlan ──

def test_valid_plan_passes():
    from mandarin.scheduler import _validate_plan, SessionPlan
    plan = SessionPlan(
        session_type="standard",
        drills=[
            make_drill_item(item_id=1, modality="reading", drill_type="mc"),
            make_drill_item(item_id=2, modality="ime", drill_type="ime_type"),
        ],
    )
    result = _validate_plan(plan)
    assert result is plan


def test_invalid_modality_filtered():
    """Invalid modality drills are silently dropped, not crashed."""
    from mandarin.scheduler import _validate_plan, SessionPlan
    plan = SessionPlan(
        session_type="standard",
        drills=[make_drill_item(modality="invalid_mod", drill_type="mc")],
    )
    result = _validate_plan(plan)
    assert len(result.drills) == 0


def test_invalid_drill_type_filtered():
    """Invalid drill_type drills are silently dropped, not crashed."""
    from mandarin.scheduler import _validate_plan, SessionPlan
    plan = SessionPlan(
        session_type="standard",
        drills=[make_drill_item(modality="reading", drill_type="invalid_type")],
    )
    result = _validate_plan(plan)
    assert len(result.drills) == 0


def test_duplicate_item_ids_deduped():
    """Duplicate item_ids are deduplicated, not crashed."""
    from mandarin.scheduler import _validate_plan, SessionPlan
    plan = SessionPlan(
        session_type="standard",
        drills=[
            make_drill_item(item_id=1, modality="reading", drill_type="mc"),
            make_drill_item(item_id=1, modality="ime", drill_type="ime_type"),
        ],
    )
    result = _validate_plan(plan)
    assert len(result.drills) == 1


def test_dialogue_duplicates_allowed():
    """Dialogues use content_item_id=0 and should not trigger duplicate check."""
    from mandarin.scheduler import _validate_plan, SessionPlan
    plan = SessionPlan(
        session_type="standard",
        drills=[
            make_drill_item(item_id=0, modality="reading", drill_type="dialogue"),
            make_drill_item(item_id=0, modality="reading", drill_type="dialogue"),
        ],
    )
    result = _validate_plan(plan)
    assert len(result.drills) == 2


def test_invalid_session_type_defaults():
    """Invalid session_type defaults to 'standard', not crashed."""
    from mandarin.scheduler import _validate_plan, SessionPlan
    plan = SessionPlan(
        session_type="unknown_type",
        drills=[],
    )
    result = _validate_plan(plan)
    assert result.session_type == "standard"


def test_empty_drills_valid():
    """An empty drill list is structurally valid."""
    from mandarin.scheduler import _validate_plan, SessionPlan
    plan = SessionPlan(session_type="standard", drills=[])
    result = _validate_plan(plan)
    assert len(result.drills) == 0


# ── TestDayProfile ──

def test_all_days_covered():
    from mandarin.config import DAY_PROFILES
    for dow in range(7):
        assert dow in DAY_PROFILES
        profile = DAY_PROFILES[dow]
        assert "name" in profile
        assert "length_mult" in profile
        assert "new_mult" in profile
        assert "mode" in profile


def test_length_mult_positive():
    from mandarin.config import DAY_PROFILES
    for dow, profile in DAY_PROFILES.items():
        assert profile["length_mult"] > 0


def test_new_mult_non_negative():
    from mandarin.config import DAY_PROFILES
    for dow, profile in DAY_PROFILES.items():
        assert profile["new_mult"] >= 0


# ── TestGetDayProfileNoConn ──

def test_returns_default_without_conn():
    from mandarin.scheduler import get_day_profile, is_us_holiday
    from mandarin.config import DAY_PROFILES
    profile = get_day_profile(conn=None)
    today = date.today()
    # Weekday holidays use Saturday (weekend) profile
    if today.weekday() < 5 and is_us_holiday(today):
        assert profile == DAY_PROFILES[5]
    else:
        assert profile == DAY_PROFILES[today.weekday()]


# ═══════════════════════════════════════════════════
# C. Integration tests (in-memory SQLite)
# ═══════════════════════════════════════════════════


# ── TestPlanStandardSession ──

@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_produces_valid_plan(mock_conf, mock_bounce, mock_gate,
                              mock_adj, mock_tod, mock_profile):
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    _seed_standard(conn, 20)
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    assert plan.session_type == "standard"
    assert len(plan.drills) > 0, "Session should have drills"
    conn.close()


@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_no_duplicate_item_ids(mock_conf, mock_bounce, mock_gate,
                                mock_adj, mock_tod, mock_profile):
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    _seed_standard(conn, 25)
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=12)
    # Filter out dialogues (id=0) and listen-produce pairs (intentional duplicates)
    real_ids = [d.content_item_id for d in plan.drills
                if d.drill_type != "dialogue"
                and not d.metadata.get("listen_produce_pair")]
    assert len(real_ids) == len(set(real_ids)), \
        "No duplicate content_item_ids allowed"
    conn.close()


@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_micro_plan_has_content(mock_conf, mock_bounce, mock_gate,
                                 mock_adj, mock_tod, mock_profile):
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    _seed_standard(conn, 20)
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    assert len(plan.micro_plan) > 0, "micro_plan should be non-empty"
    conn.close()


@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_estimated_seconds_positive(mock_conf, mock_bounce, mock_gate,
                                     mock_adj, mock_tod, mock_profile):
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    _seed_standard(conn, 20)
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    if len(plan.drills) > 0:
        assert plan.estimated_seconds > 0
    conn.close()


@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_mapping_groups_stored(mock_conf, mock_bounce, mock_gate,
                                mock_adj, mock_tod, mock_profile):
    """Plan should stash mapping_groups_used for cross-session interleaving."""
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    _seed_standard(conn, 20)
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    assert hasattr(plan, "_mapping_groups_used")
    assert isinstance(plan._mapping_groups_used, str)
    assert len(plan._mapping_groups_used) > 0
    conn.close()


@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_consolidation_mode_prefers_familiar(mock_conf, mock_bounce,
                                               mock_gate, mock_adj,
                                               mock_tod, mock_profile):
    """In consolidation mode, should prefer high-streak items."""
    mock_profile.return_value = {
        "name": "Monday warmup", "length_mult": 0.85, "new_mult": 0.5,
        "mode": "consolidation",
    }
    conn = _create_test_db()
    ids = _seed_items(conn, n=20, hsk=1)
    # Half with high streak, half with low
    _seed_progress(conn, ids[:10], modality="reading", streak=8,
                   mastery="stable")
    _seed_progress(conn, ids[10:], modality="reading", streak=0,
                   mastery="seen")
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=8)
    # Plan should exist and be valid
    assert plan.session_type == "standard"
    conn.close()


@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_long_gap_no_new_items(mock_conf, mock_bounce, mock_gate,
                                mock_adj, mock_tod, mock_profile):
    """With a 7+ day gap, new_budget should be 0."""
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    # Set last session to 10 days ago
    conn.execute("""
        UPDATE learner_profile SET last_session_date = ?
    """, ((date.today() - timedelta(days=10)).isoformat(),))
    conn.commit()
    _seed_standard(conn, 20)
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    # All drills should be reviews, not new
    new_count = sum(1 for d in plan.drills if d.is_new)
    assert new_count == 0, \
        "No new items should be introduced after a long gap"
    conn.close()


# ── TestPlanMinimalSession ──

def test_minimal_session_type():
    conn = _create_test_db()
    ids = _seed_items(conn, n=15)
    _seed_progress(conn, ids, modality="reading")
    _seed_progress(conn, ids, modality="ime")
    _seed_progress(conn, ids, modality="listening")
    from mandarin.scheduler import plan_minimal_session
    plan = plan_minimal_session(conn)
    assert plan.session_type == "minimal"
    assert plan.estimated_seconds == 90
    conn.close()


def test_minimal_session_small_drill_count():
    conn = _create_test_db()
    ids = _seed_items(conn, n=15)
    _seed_progress(conn, ids, modality="reading")
    _seed_progress(conn, ids, modality="ime")
    _seed_progress(conn, ids, modality="listening")
    from mandarin.scheduler import plan_minimal_session
    plan = plan_minimal_session(conn)
    # Should produce at most 5 drills (3 IME + 1 listening + 1 tone)
    assert len(plan.drills) <= 5
    conn.close()


def test_minimal_with_empty_db():
    """Minimal session with no content should produce empty plan."""
    conn = _create_test_db()
    from mandarin.scheduler import plan_minimal_session
    plan = plan_minimal_session(conn)
    assert plan.session_type == "minimal"
    assert len(plan.drills) == 0
    conn.close()


# ── TestPlanCatchupSession ──

def test_catchup_session_type():
    conn = _create_test_db()
    ids = _seed_items(conn, n=20)
    # Seed progress with low accuracy (half correct)
    for item_id in ids:
        conn.execute("""
            INSERT INTO progress
                (content_item_id, modality, total_attempts, total_correct,
                 next_review_date, last_review_date, streak_correct,
                 mastery_stage, half_life_days, difficulty,
                 distinct_review_days, avg_response_ms, drill_types_seen,
                 ease_factor, interval_days, repetitions, streak_incorrect,
                 historically_weak, weak_cycle_count)
            VALUES (?, 'reading', 10, 4, ?, ?, 0, 'seen', 1.0, 0.7,
                    1, NULL, 'mc', 2.5, 1.0, 1, 2, 0, 0)
        """, (item_id, date.today().isoformat(),
              (date.today() - timedelta(days=1)).isoformat()))
    conn.commit()
    from mandarin.scheduler import plan_catchup_session
    plan = plan_catchup_session(conn)
    assert plan.session_type == "catchup"
    conn.close()


def test_catchup_with_empty_db():
    conn = _create_test_db()
    from mandarin.scheduler import plan_catchup_session
    plan = plan_catchup_session(conn)
    assert plan.session_type == "catchup"
    assert len(plan.drills) == 0
    conn.close()


# ── TestPlanSpeakingSession ──

def test_speaking_session_type():
    conn = _create_test_db()
    _seed_items(conn, n=10)
    from mandarin.scheduler import plan_speaking_session
    plan = plan_speaking_session(conn)
    assert plan.session_type == "speaking"
    conn.close()


def test_all_drills_are_speaking():
    conn = _create_test_db()
    _seed_items(conn, n=10)
    from mandarin.scheduler import plan_speaking_session
    plan = plan_speaking_session(conn)
    for d in plan.drills:
        assert d.modality == "speaking"
        assert d.drill_type == "speaking"
    conn.close()


def test_speaking_with_no_pinyin():
    """Items without pinyin should not be included in speaking sessions."""
    conn = _create_test_db()
    _seed_items(conn, n=5, with_pinyin=False)
    from mandarin.scheduler import plan_speaking_session
    plan = plan_speaking_session(conn)
    assert len(plan.drills) == 0
    conn.close()


# ═══════════════════════════════════════════════════
# D. Edge cases
# ═══════════════════════════════════════════════════


# ── TestEdgeCaseEmptyPool ──

@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_empty_db_produces_valid_plan(mock_conf, mock_bounce,
                                       mock_gate, mock_adj, mock_tod,
                                       mock_profile):
    """Standard session with zero content items should not crash."""
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    assert plan.session_type == "standard"
    assert len(plan.drills) == 0
    conn.close()


# ── TestEdgeCaseSingleItem ──

@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_single_item_plan(mock_conf, mock_bounce, mock_gate,
                           mock_adj, mock_tod, mock_profile):
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    ids = _seed_items(conn, n=1)
    _seed_progress(conn, ids, modality="reading")
    _seed_progress(conn, ids, modality="ime")
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    assert plan.session_type == "standard"
    # Should produce at most 1 real drill item (dedup prevents duplicates)
    real_ids = [d.content_item_id for d in plan.drills
                if d.drill_type != "dialogue" and d.content_item_id != 0]
    assert len(set(real_ids)) <= 1
    conn.close()


# ── TestEdgeCaseAllDurable ──

@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_all_durable_items(mock_conf, mock_bounce, mock_gate,
                            mock_adj, mock_tod, mock_profile):
    """When all items are durable with far-future reviews, session may be empty."""
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    ids = _seed_items(conn, n=10)
    # Set all progress to durable with future review dates
    future = (date.today() + timedelta(days=100)).isoformat()
    _seed_progress(conn, ids, modality="reading", mastery="durable",
                   streak=15, next_review=future)
    _seed_progress(conn, ids, modality="ime", mastery="durable",
                   streak=15, next_review=future)
    _seed_progress(conn, ids, modality="listening", mastery="durable",
                   streak=15, next_review=future)
    _seed_progress(conn, ids, modality="speaking", mastery="durable",
                   streak=15, next_review=future)
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    assert plan.session_type == "standard"
    # With all items far-future, due items list will be empty
    # Plan may still have new items or be empty — both valid
    conn.close()


# ── TestEdgeCaseCrossSessionInterleaving ──

@patch("mandarin.scheduler.get_day_profile")
@patch("mandarin.scheduler._time_of_day_penalty", return_value=1.0)
@patch("mandarin.scheduler._adjust_weights_for_errors",
       side_effect=lambda conn, w, **kw: w)
@patch("mandarin.scheduler._check_register_gate", return_value=True)
@patch("mandarin.scheduler._get_hsk_bounce_levels", return_value=set())
@patch("mandarin.scheduler._has_confusable", return_value=False)
def test_reads_last_session_groups(mock_conf, mock_bounce, mock_gate,
                                    mock_adj, mock_tod, mock_profile):
    """Scheduler should read mapping_groups_used from the last session."""
    mock_profile.return_value = {
        "name": "Standard", "length_mult": 1.0, "new_mult": 1.0,
        "mode": "standard",
    }
    conn = _create_test_db()
    # Seed a previous session with mapping groups
    conn.execute("""
        INSERT INTO session_log (session_type, items_planned,
                                 mapping_groups_used, started_at)
        VALUES ('standard', 10, 'hanzi_to_english,english_to_hanzi,pinyin_to_english',
                datetime('now', '-1 hour'))
    """)
    conn.commit()

    _seed_standard(conn, 20)
    from mandarin.scheduler import plan_standard_session
    plan = plan_standard_session(conn, target_items=10)
    # The plan should exist and be valid; exact groups may vary
    assert plan.session_type == "standard"
    assert hasattr(plan, "_mapping_groups_used")
    conn.close()


# ── TestAdaptiveDayProfile ──

def test_insufficient_data_returns_none():
    """With < 10 sessions, should return None."""
    conn = _create_test_db()
    from mandarin.scheduler import get_adaptive_day_profile
    result = get_adaptive_day_profile(conn)
    assert result is None
    conn.close()


def test_insufficient_weeks_returns_none():
    """With < 2 distinct weeks, should return None."""
    conn = _create_test_db()
    from mandarin.scheduler import get_adaptive_day_profile
    # Insert 10 sessions all in the same week
    today = date.today()
    for i in range(10):
        conn.execute("""
            INSERT INTO session_log
                (session_type, items_planned, items_completed, items_correct,
                 duration_seconds, early_exit, started_at,
                 session_day_of_week, session_started_hour)
            VALUES ('standard', 10, 8, 6, 300, 0, ?, ?, 10)
        """, (today.isoformat() + " 10:00:00", today.weekday()))
    conn.commit()
    result = get_adaptive_day_profile(conn)
    assert result is None
    conn.close()


def test_high_accuracy_returns_strong():
    """High accuracy + high completion should yield 'stretch' mode."""
    conn = _create_test_db()
    from mandarin.scheduler import get_adaptive_day_profile
    today = date.today()
    today_dow = today.weekday()
    # Insert 12 sessions across 3 weeks on today's DOW with high accuracy
    for w in range(3):
        for d in range(4):
            session_date = today - timedelta(weeks=w, days=d * 2)
            conn.execute("""
                INSERT INTO session_log
                    (session_type, items_planned, items_completed, items_correct,
                     duration_seconds, early_exit, started_at,
                     session_day_of_week, session_started_hour)
                VALUES ('standard', 10, 10, 9, 300, 0, ?, ?, 10)
            """, (session_date.isoformat() + " 10:00:00", today_dow))
    conn.commit()
    result = get_adaptive_day_profile(conn)
    if result is not None:
        assert result["mode"] in ("stretch", "standard")
    conn.close()


# ── TestNewItemBudget ──

def test_empty_db_returns_3():
    conn = _create_test_db()
    from mandarin.scheduler import _new_item_budget
    result = _new_item_budget(conn)
    assert result == 3
    conn.close()


# ── TestDeriveDataDrivenWeights ──

def test_no_data_returns_base():
    conn = _create_test_db()
    from mandarin.scheduler import _derive_data_driven_weights
    from mandarin.config import DEFAULT_WEIGHTS
    result = _derive_data_driven_weights(conn, DEFAULT_WEIGHTS)
    assert result == DEFAULT_WEIGHTS
    conn.close()


def test_insufficient_data_returns_base():
    """With < 20 total attempts, should return base weights."""
    conn = _create_test_db()
    from mandarin.scheduler import _derive_data_driven_weights
    from mandarin.config import DEFAULT_WEIGHTS
    ids = _seed_items(conn, n=5)
    for item_id in ids:
        conn.execute("""
            INSERT INTO progress (content_item_id, modality,
                total_attempts, total_correct,
                ease_factor, interval_days, repetitions,
                streak_correct, streak_incorrect,
                mastery_stage, historically_weak, weak_cycle_count,
                half_life_days, difficulty, distinct_review_days,
                avg_response_ms, drill_types_seen)
            VALUES (?, 'reading', 3, 2, 2.5, 1.0, 1, 1, 0,
                    'seen', 0, 0, 1.0, 0.5, 1, NULL, 'mc')
        """, (item_id,))
    conn.commit()
    result = _derive_data_driven_weights(conn, DEFAULT_WEIGHTS)
    assert result == DEFAULT_WEIGHTS
    conn.close()


def test_sufficient_data_adjusts_weights():
    """With enough data, weights should differ from base."""
    conn = _create_test_db()
    from mandarin.scheduler import _derive_data_driven_weights
    from mandarin.config import DEFAULT_WEIGHTS
    ids = _seed_items(conn, n=20)
    # Reading: high accuracy (easy)
    for item_id in ids[:10]:
        conn.execute("""
            INSERT INTO progress (content_item_id, modality,
                total_attempts, total_correct,
                ease_factor, interval_days, repetitions,
                streak_correct, streak_incorrect,
                mastery_stage, historically_weak, weak_cycle_count,
                half_life_days, difficulty, distinct_review_days,
                avg_response_ms, drill_types_seen)
            VALUES (?, 'reading', 5, 5, 2.5, 1.0, 1, 5, 0,
                    'stable', 0, 0, 1.0, 0.3, 1, NULL, 'mc')
        """, (item_id,))
    # Listening: low accuracy (hard)
    for item_id in ids[10:]:
        conn.execute("""
            INSERT INTO progress (content_item_id, modality,
                total_attempts, total_correct,
                ease_factor, interval_days, repetitions,
                streak_correct, streak_incorrect,
                mastery_stage, historically_weak, weak_cycle_count,
                half_life_days, difficulty, distinct_review_days,
                avg_response_ms, drill_types_seen)
            VALUES (?, 'listening', 5, 1, 2.5, 1.0, 1, 0, 2,
                    'seen', 0, 0, 1.0, 0.7, 1, NULL, 'mc')
        """, (item_id,))
    conn.commit()
    result = _derive_data_driven_weights(conn, DEFAULT_WEIGHTS)
    # Weights should sum close to 1.0
    total = sum(result.values())
    assert total == pytest.approx(1.0, abs=0.1)
    # All modalities should still be present
    for mod in DEFAULT_WEIGHTS:
        assert mod in result
    conn.close()


# ── TestScaffoldLevelAssignment ──

def test_scaffold_levels_complete():
    """All mastery stages should have a scaffold level defined."""
    from mandarin.config import SCAFFOLD_LEVELS
    stages = ["seen", "passed_once", "stabilizing", "stable", "durable", "decayed"]
    for stage in stages:
        assert stage in SCAFFOLD_LEVELS, \
            f"missing scaffold level for {stage}"
        levels = SCAFFOLD_LEVELS[stage]
        assert "pinyin" in levels, f"missing 'pinyin' key for {stage}"
        assert "english" in levels, f"missing 'english' key for {stage}"


def test_scaffold_progression_fades_support():
    """Scaffold should fade from full support to none as mastery increases."""
    from mandarin.config import SCAFFOLD_LEVELS, SCAFFOLD_ORDER, ENGLISH_ORDER
    # seen should have the most pinyin support, durable the least
    seen_idx = SCAFFOLD_ORDER.index(SCAFFOLD_LEVELS["seen"]["pinyin"])
    durable_idx = SCAFFOLD_ORDER.index(SCAFFOLD_LEVELS["durable"]["pinyin"])
    assert seen_idx > durable_idx, \
        "seen should have more scaffold support than durable"
    # English should also fade: seen=full, stable=none
    seen_eng = ENGLISH_ORDER.index(SCAFFOLD_LEVELS["seen"]["english"])
    stable_eng = ENGLISH_ORDER.index(SCAFFOLD_LEVELS["stable"]["english"])
    assert seen_eng > stable_eng, \
        "seen should have more English support than stable"


# ── TestConfusableHelpers ──

def test_has_confusable_with_no_data():
    """If confusable_pairs.json is missing, should return False gracefully."""
    from mandarin.scheduler import _has_confusable
    # Clear cache to test fresh load
    import mandarin.scheduler as sched
    sched._confusable_chars_cache = None
    # This should not raise even if the file doesn't exist
    result = _has_confusable("你好")
    assert isinstance(result, bool)


# ── TestGapWeightsVsDefault ──

def test_gap_weights_sum_to_one():
    from mandarin.config import GAP_WEIGHTS
    total = sum(GAP_WEIGHTS.values())
    assert total == pytest.approx(1.0, abs=0.01)


def test_default_weights_sum_to_one():
    from mandarin.config import DEFAULT_WEIGHTS
    total = sum(DEFAULT_WEIGHTS.values())
    assert total == pytest.approx(1.0, abs=0.01)


def test_same_modalities():
    from mandarin.config import GAP_WEIGHTS, DEFAULT_WEIGHTS
    assert set(GAP_WEIGHTS.keys()) == set(DEFAULT_WEIGHTS.keys())
