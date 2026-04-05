"""Session scheduler — gap-aware, skip-tolerant, error-weighted, interleaved."""

from __future__ import annotations

import hashlib
import logging
import random
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from . import db
from .ui_labels import MODALITY_LABELS
from .config import (
    TOD_MIN_SESSIONS, TOD_LOW_ACCURACY_THRESHOLD, TOD_LOW_ACCURACY_PENALTY,
    MISSING_MODALITY_NEED, MAX_DATA_MIX, MIX_MIN_ATTEMPTS, MIX_RAMP_RANGE,
    MAX_ERROR_BOOST, ERROR_BOOST_FACTOR,
    BOUNCE_ERROR_RATE, BOUNCE_MIN_ERRORS,
    MAX_NEW_ITEM_RATIO, MIN_NEW_ITEMS, CONFIDENCE_WINS_NEEDED,
    SECONDS_PER_DRILL, SECONDS_PER_CONVERSATION,
    ADAPTIVE_MIN_SESSIONS, ADAPTIVE_MIN_WEEKS, ADAPTIVE_LOOKBACK_DAYS,
    ADAPTIVE_SKIP_RATE, ADAPTIVE_EXIT_RATE, ADAPTIVE_LOW_COMPLETION,
    ADAPTIVE_HIGH_ACCURACY, ADAPTIVE_HIGH_COMPLETION,
    REGISTER_GATE_MIN_ATTEMPTS, REGISTER_GATE_MIN_ACCURACY,
    NEW_BUDGET_LOW_MASTERY, NEW_BUDGET_MED_MASTERY, NEW_BUDGET_DEFAULT,
    LONG_GAP_DAYS,
    TONE_BOOST_MIN_RECORDINGS, TONE_BOOST_ACCURACY_THRESHOLD,
    TONE_BOOST_MULTIPLIER, TONE_BOOST_MAX_WEIGHT,
    ERROR_FOCUS_LIMIT, CONFUSABLE_ROUTE_PROBABILITY, MIN_SESSION_ITEMS,
    MAPPING_GROUPS_PER_SESSION, INTERLEAVE_EXCLUDE_WEIGHT,
    INTERLEAVE_STRONG_NOVEL_DIFF, INTERLEAVE_MILD_NOVEL_DIFF,
    INTERLEAVE_STRONG_REPEAT_DIFF, INTERLEAVE_MILD_REPEAT_DIFF,
    INTERLEAVE_WEIGHT_STRONG_NOVEL, INTERLEAVE_WEIGHT_MILD_NOVEL,
    INTERLEAVE_WEIGHT_STRONG_REPEAT, INTERLEAVE_WEIGHT_MILD_REPEAT,
    INTERLEAVE_WEIGHT_NEUTRAL, INTERLEAVE_WEIGHT_FLOOR, INTERLEAVE_WEIGHT_CEILING,
    ADAPTIVE_LENGTH_MIN_SESSIONS, ADAPTIVE_LENGTH_RECENT_SESSIONS,
    ADAPTIVE_LENGTH_LOW_COMPLETION, ADAPTIVE_LENGTH_SHRINK_FACTOR,
    ADAPTIVE_LENGTH_MIN_ITEMS, ADAPTIVE_LENGTH_HIGH_COMPLETION,
    ADAPTIVE_LENGTH_HIGH_MIN_SESSIONS, ADAPTIVE_LENGTH_GROW_FACTOR,
    SESSION_PLAN_REDUCTION_FACTOR,
    ENCOUNTER_BOOST_RATIO, ENCOUNTER_PRIORITY_WINDOW_DAYS, ENCOUNTER_FULL_WINDOW_DAYS,
    TONE_SANDHI_BOOST_WEIGHT,
    CROSS_MODALITY_BOOST_LIMIT,
)

logger = logging.getLogger(__name__)


def _session_seed(conn: sqlite3.Connection, user_id: int = 1) -> int:
    """Deterministic seed for this session: date + total_sessions.

    Makes scheduling reproducible for debugging while varying per session.
    """
    profile = db.get_profile(conn, user_id=user_id)
    total = profile.get("total_sessions") or 0
    key = f"{user_id}:{date.today().isoformat()}:{total}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


# ── Day-of-week profiles (canonical source: config.py) ──

from .config import DAY_PROFILES, is_us_holiday


def get_day_profile(conn: sqlite3.Connection | None = None, user_id: int = 1) -> dict:
    """Get today's session profile — adaptive if enough data, else defaults.

    US federal holidays on weekdays are treated as weekends (Saturday profile).
    """
    if conn is not None:
        adaptive = get_adaptive_day_profile(conn, user_id=user_id)
        if adaptive is not None:
            return adaptive
    today = date.today()
    # Treat weekday holidays as weekends (use Saturday profile)
    if today.weekday() < 5 and is_us_holiday(today):
        return DAY_PROFILES[5]
    return DAY_PROFILES[today.weekday()]


def get_adaptive_day_profile(conn: sqlite3.Connection, user_id: int = 1) -> dict | None:
    """Compute day profile from actual usage patterns over last N days.

    Returns None if insufficient data.
    """
    today_dow = date.today().weekday()

    # Get all sessions from lookback window
    rows = conn.execute("""
        SELECT session_day_of_week, items_planned, items_completed, items_correct,
               duration_seconds, early_exit, started_at
        FROM session_log
        WHERE started_at >= date('now', ? || ' days')
          AND session_day_of_week IS NOT NULL
          AND user_id = ?
    """, (f"-{ADAPTIVE_LOOKBACK_DAYS}", user_id)).fetchall()

    if len(rows) < ADAPTIVE_MIN_SESSIONS:
        return None  # not enough data

    # Count distinct weeks observed
    weeks_seen = set()
    for r in rows:
        if r["started_at"]:
            try:
                d = date.fromisoformat(r["started_at"][:10])
                weeks_seen.add(d.isocalendar()[1])
            except (ValueError, TypeError):
                pass

    if len(weeks_seen) < ADAPTIVE_MIN_WEEKS:
        return None  # need at least 2 weeks

    # Aggregate per day-of-week
    day_stats = {}
    for r in rows:
        dow = r["session_day_of_week"]
        if dow is None:
            continue
        if dow not in day_stats:
            day_stats[dow] = {
                "sessions": 0, "total_planned": 0, "total_completed": 0,
                "total_correct": 0, "early_exits": 0, "durations": [],
            }
        s = day_stats[dow]
        s["sessions"] += 1
        s["total_planned"] += r["items_planned"] or 0
        s["total_completed"] += r["items_completed"] or 0
        s["total_correct"] += r["items_correct"] or 0
        s["early_exits"] += r["early_exit"] or 0
        if r["duration_seconds"]:
            s["durations"].append(r["duration_seconds"])

    # If today's DOW has no data, fall back to defaults
    if today_dow not in day_stats:
        return None

    s = day_stats[today_dow]
    n_weeks = len(weeks_seen)
    n_sessions = s["sessions"]

    # Compute metrics
    skip_rate = max(0.0, 1.0 - (n_sessions / n_weeks))
    completion_rate = (s["total_completed"] / s["total_planned"]) if s["total_planned"] > 0 else 1.0
    accuracy = (s["total_correct"] / s["total_completed"]) if s["total_completed"] > 0 else 0.5
    early_exit_rate = (s["early_exits"] / n_sessions) if n_sessions > 0 else 0.0

    # Classify with hysteresis: require minimum sample size per mode
    # to prevent flipping from noise. Need at least 3 sessions on this
    # day-of-week before departing from standard mode.
    if n_sessions < 3:
        return {"name": "Standard", "length_mult": 1.0, "new_mult": 1.0, "mode": "standard"}
    if skip_rate > ADAPTIVE_SKIP_RATE:
        return {"name": "Gentle",
                "length_mult": 0.7, "new_mult": 0.3, "mode": "gentle"}
    elif early_exit_rate > ADAPTIVE_EXIT_RATE or completion_rate < ADAPTIVE_LOW_COMPLETION:
        return {"name": "Lighter day",
                "length_mult": 0.8, "new_mult": 0.5, "mode": "consolidation"}
    elif accuracy > ADAPTIVE_HIGH_ACCURACY and completion_rate > ADAPTIVE_HIGH_COMPLETION:
        return {"name": "Strong day",
                "length_mult": 1.3, "new_mult": 1.5, "mode": "stretch"}
    else:
        return {"name": "Standard", "length_mult": 1.0, "new_mult": 1.0, "mode": "standard"}


def _time_of_day_penalty(conn: sqlite3.Connection, user_id: int = 1) -> float:
    """Check if current hour tends to produce lower accuracy. Returns 0.75 or 1.0."""
    from datetime import datetime as dt_class
    current_hour = dt_class.now().hour

    # Bucket into 4-hour windows
    window_start = (current_hour // 4) * 4
    window_end = window_start + 4

    rows = conn.execute("""
        SELECT items_correct, items_completed
        FROM session_log
        WHERE session_started_hour >= ? AND session_started_hour < ?
          AND started_at >= date('now', '-30 days')
          AND items_completed > 0
          AND user_id = ?
    """, (window_start, window_end, user_id)).fetchall()

    if len(rows) < TOD_MIN_SESSIONS:
        return 1.0  # not enough data

    total_correct = sum(r["items_correct"] or 0 for r in rows)
    total_completed = sum(r["items_completed"] or 0 for r in rows)
    if total_completed == 0:
        return 1.0

    accuracy = total_correct / total_completed
    if accuracy < TOD_LOW_ACCURACY_THRESHOLD:
        return TOD_LOW_ACCURACY_PENALTY
    return 1.0


# ── Item validation ──────────────────────────────

def _item_is_drillable(item: dict[str, object], drill_type: str) -> bool:
    """Check if an item has the required fields for a given drill type.

    Returns False (skip this item) rather than letting empty data reach drills.
    """
    hanzi = (item.get("hanzi") or "").strip()
    pinyin = (item.get("pinyin") or "").strip()
    english = (item.get("english") or "").strip()

    if not hanzi:
        return False

    if drill_type in ("mc", "reverse_mc", "listening_gist", "intuition"):
        return bool(hanzi and english)

    if drill_type == "ime_type":
        return bool(hanzi and pinyin)

    if drill_type == "tone":
        if not pinyin:
            return False
        # Must have at least one tone mark
        return bool(re.search(r'[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]', pinyin))

    if drill_type == "english_to_pinyin":
        return bool(hanzi and pinyin and english)

    if drill_type == "hanzi_to_pinyin":
        return bool(hanzi and pinyin)

    if drill_type == "pinyin_to_hanzi":
        return bool(hanzi and pinyin and english)

    if drill_type == "listening_detail":
        # Detail questions need sentence-level items
        item_type = (item.get("item_type") or "").strip()
        return bool(hanzi and english and item_type in ("sentence", "phrase", "chunk"))

    if drill_type == "listening_tone":
        # Need pinyin with tone marks
        if not pinyin:
            return False
        return bool(re.search(r'[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]', pinyin))

    if drill_type == "listening_dictation":
        return bool(hanzi and pinyin)

    if drill_type == "measure_word":
        return bool(hanzi and english)

    if drill_type == "word_order":
        # Need sentence/phrase items with enough characters to shuffle
        item_type = (item.get("item_type") or "").strip()
        return bool(hanzi and english and item_type in ("sentence", "phrase", "chunk"))

    if drill_type == "sentence_build":
        item_type = (item.get("item_type") or "").strip()
        return bool(hanzi and english and item_type in ("sentence", "phrase", "chunk"))

    if drill_type == "particle_disc":
        # Item must contain at least one particle from known sets
        return bool(hanzi)

    if drill_type == "homophone":
        # Item must contain a character from a known homophone set
        from .drills.advanced import _get_homophone_sets
        for hset in _get_homophone_sets().values():
            for entry in hset["chars"]:
                if entry["hanzi"] in hanzi:
                    return True
        return False

    if drill_type == "translation":
        return bool(hanzi and english)

    if drill_type == "cloze_context":
        return bool(hanzi)

    if drill_type == "synonym_disc":
        return bool(hanzi)

    if drill_type == "listening_passage":
        # HSK 3+ items
        hsk = item.get("hsk_level", 0)
        return bool(hanzi) and hsk >= 3

    if drill_type == "dictation_sentence":
        # Sentence/phrase/chunk items, HSK 2+
        item_type = (item.get("item_type") or "").strip()
        hsk = item.get("hsk_level", 0)
        return bool(hanzi and pinyin) and hsk >= 2 and item_type in ("sentence", "phrase", "chunk")

    # Unknown drill type — require all fields
    return bool(hanzi and pinyin and english)


@dataclass
class DrillItem:
    """A single drill within a session."""
    content_item_id: int
    hanzi: str
    pinyin: str
    english: str
    modality: str       # 'reading', 'listening', 'speaking', 'ime'
    drill_type: str     # 'mc', 'reverse_mc', 'ime_type', 'tone', 'listening_gist'
    is_new: bool = False
    is_confidence_win: bool = False
    is_error_focus: bool = False
    metadata: dict = field(default_factory=dict)


# ── Error-informed drill preferences ──────────────────────────────

ERROR_DRILL_PREFERENCE = {
    "tone":           ["tone", "hanzi_to_pinyin", "english_to_pinyin", "tone_sandhi"],
    "segment":        ["ime_type"],
    "ime_confusable": ["ime_type", "hanzi_to_pinyin"],
    "vocab":          ["mc", "reverse_mc", "collocation", "radical", "chengyu"],
    "grammar":        ["intuition", "complement", "ba_bei", "error_correction"],
    "measure_word":   ["measure_word", "measure_word_cloze", "measure_word_disc"],
    "number":         ["number_system"],
    "other":          ["mc"],
}


@dataclass
class DrillBlock:
    """Sequence of atomic drills (existing behavior, wrapped in a block)."""
    block_type: str = "drills"
    items: list[DrillItem] = field(default_factory=list)
    target_seconds: int = 180


@dataclass
class ReadingBlock:
    """A reading passage — exposure (tap unknowns) or re-read (see progress).

    Cleanup loop: exposure → drills → re-read same passage.
    """
    block_type: str = "reading"
    passage_id: int = 0
    passage: dict = field(default_factory=dict)
    questions: list = field(default_factory=list)
    target_seconds: int = 240
    is_reread: bool = False
    looked_up_words: list = field(default_factory=list)  # populated at runtime


@dataclass
class ConversationBlock:
    """A guided conversation scenario with multi-turn dialogue."""
    block_type: str = "conversation"
    scenario_id: str = ""
    scenario: dict = field(default_factory=dict)
    max_turns: int = 3
    target_seconds: int = 180
    hsk_level: int = 1


@dataclass
class ListeningBlock:
    """A listening comprehension block -- audio plays, user answers MC questions."""
    block_type: str = "listening"
    passage_id: int = 0
    audio_url: str = ""
    transcript_zh: str = ""
    transcript_pinyin: str = ""
    questions: list = field(default_factory=list)
    playback_speed: float = 1.0
    target_seconds: int = 180


@dataclass
class GrammarBlock:
    """A grammar mini-lesson triggered by encountered grammar patterns.

    Shown when a user encounters a grammar pattern in drills that they
    haven't studied yet, or when their mastery is low.
    """
    block_type: str = "grammar"
    grammar_point_id: int = 0
    grammar_point: dict = field(default_factory=dict)
    target_seconds: int = 120


@dataclass
class SessionPlan:
    """A complete session plan ready for the runner.

    Sessions are organized as blocks: DrillBlock (atomic drills),
    ReadingBlock (passage + comprehension), ConversationBlock (dialogue),
    ListeningBlock (audio + comprehension questions), GrammarBlock (mini-lesson).
    The planner allocates by time budget, not item count.
    """
    session_type: str           # 'standard', 'minimal', 'catchup'
    blocks: list = field(default_factory=list)  # [DrillBlock, ReadingBlock, ConversationBlock, ListeningBlock, ...]
    micro_plan: str = ""        # One-line summary shown at start
    estimated_seconds: int = 0
    days_since_last: int | None = None
    gap_message: str | None = None
    day_label: str | None = None
    focus_insights: list[str] = field(default_factory=list)
    experiment_variant: str | None = None

    @property
    def drills(self) -> list[DrillItem]:
        """Backward compat: flat list of DrillItems from all DrillBlocks."""
        items = []
        for block in self.blocks:
            if isinstance(block, DrillBlock):
                items.extend(block.items)
        return items

    @drills.setter
    def drills(self, value):
        """Backward compat: set drills by wrapping in a DrillBlock."""
        # Find existing DrillBlock or create one
        for block in self.blocks:
            if isinstance(block, DrillBlock):
                block.items = value
                return
        self.blocks.insert(0, DrillBlock(items=value))


# Backward compat: allow SessionPlan(drills=[...]) as __init__ kwarg
_SessionPlan_orig_init = SessionPlan.__init__

def _session_plan_init(self, *args, drills=None, **kwargs):
    _SessionPlan_orig_init(self, *args, **kwargs)
    if drills is not None:
        self.drills = drills

SessionPlan.__init__ = _session_plan_init


# ── Gap messages (humane, not shaming) ──────────────

GAP_MESSAGES = {
    0: None,
    1: None,
    2: None,
    3: "3 days since last. Starting with review.",
    7: "7 days since last. Starting with familiar items.",
    14: "14 days since last. Warmup first, then review.",
    30: "30 days since last. Short session, all familiar items.",
    60: "60+ days since last. Starting with early material.",
}


def get_gap_message(days: int | None) -> str | None:
    """Get the appropriate gap message for the number of days since last session."""
    if days is None or days <= 2:
        return None
    thresholds = sorted(GAP_MESSAGES.keys(), reverse=True)
    for t in thresholds:
        if days >= t and GAP_MESSAGES[t]:
            return GAP_MESSAGES[t]
    return None


# ── Modality weights (canonical source: config.py) ──

from .config import DEFAULT_WEIGHTS, GAP_WEIGHTS


def _pick_modality_distribution(total_items: int, weights: dict[str, float]) -> dict[str, int]:
    """Distribute N items across modalities by weight."""
    counts = {}
    remaining = total_items
    modalities = list(weights.keys())
    for mod in modalities[:-1]:
        n = max(1, round(total_items * weights[mod]))
        counts[mod] = n
        remaining -= n
    counts[modalities[-1]] = max(1, remaining)
    return counts


def _derive_data_driven_weights(conn: sqlite3.Connection, base_weights: dict[str, float], user_id: int = 1) -> dict[str, float]:
    """Derive modality weights from historical per-modality accuracy.

    Modalities with lower accuracy get higher weight (more practice
    where the learner is weakest). Blends with base weights using
    a mixing factor that increases with data volume.

    Falls back to base_weights if insufficient data (<20 attempts).
    """
    rows = conn.execute("""
        SELECT modality,
               SUM(total_attempts) as attempts,
               SUM(total_correct) as correct
        FROM progress
        WHERE total_attempts > 0
          AND user_id = ?
        GROUP BY modality
    """, (user_id,)).fetchall()

    if not rows:
        return dict(base_weights)

    total_attempts = sum(r["attempts"] for r in rows)
    if total_attempts < 20:
        return dict(base_weights)

    # Compute per-modality accuracy; invert to get "need" weights
    accuracy = {}
    for r in rows:
        mod = r["modality"]
        if mod in base_weights:
            acc = r["correct"] / r["attempts"] if r["attempts"] > 0 else 0.5
            accuracy[mod] = acc

    if not accuracy:
        return base_weights

    # Need = 1 - accuracy (lower accuracy → higher need)
    need = {mod: max(0.05, 1.0 - acc) for mod, acc in accuracy.items()}
    # Fill missing modalities with high need
    for mod in base_weights:
        if mod not in need:
            need[mod] = MISSING_MODALITY_NEED

    need_total = sum(need.values())
    need_weights = {mod: n / need_total for mod, n in need.items()}

    # Mixing factor: ramp from 0 (pure base) to MAX_DATA_MIX (data-driven)
    mix = min(MAX_DATA_MIX, (total_attempts - MIX_MIN_ATTEMPTS) / MIX_RAMP_RANGE)

    blended = {}
    for mod in base_weights:
        blended[mod] = (1 - mix) * base_weights[mod] + mix * need_weights.get(mod, base_weights[mod])

    # Renormalize
    total = sum(blended.values())
    return {mod: round(w / total, 3) for mod, w in blended.items()}


def _adjust_weights_for_errors(conn: sqlite3.Connection, base_weights: dict[str, float], user_id: int = 1) -> dict[str, float]:
    """Adjust modality weights based on recent error patterns and historical accuracy.

    Two-stage: first derive data-driven base from accuracy history,
    then apply error-type-specific boosts from recent sessions.
    """
    # Stage 1: data-driven base
    data_weights = _derive_data_driven_weights(conn, base_weights, user_id=user_id)

    # Stage 2: error-type boosts from recent sessions
    errors = db.get_error_summary(conn, last_n_sessions=10, user_id=user_id)
    if not errors:
        return data_weights

    error_modality_map = {
        "tone": "reading",
        "segment": "ime",
        "ime_confusable": "ime",
        "vocab": "reading",
        "grammar": "reading",
    }

    modality_error_counts = {}
    total_errors = sum(errors.values())
    for etype, count in errors.items():
        mod = error_modality_map.get(etype, "reading")
        modality_error_counts[mod] = modality_error_counts.get(mod, 0) + count

    if total_errors == 0:
        return data_weights

    # Boost modalities with more errors
    adjusted = dict(data_weights)
    for mod, err_count in modality_error_counts.items():
        if mod in adjusted:
            boost = min(MAX_ERROR_BOOST, (err_count / total_errors) * ERROR_BOOST_FACTOR)
            adjusted[mod] += boost

    # Renormalize
    total = sum(adjusted.values())
    return {mod: round(w / total, 3) for mod, w in adjusted.items()}


# ── Mapping groups (cognitive direction clusters) ──────────────────

MAPPING_GROUPS = {
    "hanzi_to_english": ["mc", "measure_word", "cloze_context"],
    "english_to_hanzi": ["reverse_mc", "intuition", "word_order", "sentence_build", "translation"],
    "pinyin_to_english": ["listening_gist"],
    "english_to_pinyin": ["english_to_pinyin"],
    "hanzi_to_pinyin": ["hanzi_to_pinyin", "tone", "ime_type"],
    "pinyin_to_hanzi": ["pinyin_to_hanzi", "dictation_sentence"],
    "discrimination": ["particle_disc", "homophone", "synonym_disc"],
    "pragmatic": ["register_choice", "pragmatic", "slang_exposure"],
    "listening_detail": ["listening_detail", "listening_passage"],
    "listening_tone": ["listening_tone"],
    "listening_dictation": ["listening_dictation"],
    "grammar_particles": ["particle_disc"],
}


def _compute_interleave_weight(conn: sqlite3.Connection, user_id: int = 1) -> float:
    """Compute optimal interleave weight from session data.

    Compares accuracy on sessions where mapping groups were repeated from the
    prior session vs. sessions where groups were novel. If repeating groups
    correlates with lower accuracy, use a lower weight (stronger deprioritization).
    If no difference or insufficient data, fall back to INTERLEAVE_EXCLUDE_WEIGHT.

    Returns a weight in [0.05, 0.5] — never fully bans or fully includes.
    """
    try:
        rows = conn.execute("""
            SELECT id, mapping_groups_used, items_correct, items_completed
            FROM session_log
            WHERE mapping_groups_used IS NOT NULL
              AND items_completed >= 4
              AND user_id = ?
            ORDER BY started_at DESC LIMIT 20
        """, (user_id,)).fetchall()
    except (sqlite3.Error, KeyError):
        return INTERLEAVE_EXCLUDE_WEIGHT

    if len(rows) < 6:
        return INTERLEAVE_EXCLUDE_WEIGHT  # Not enough data

    # Compare consecutive sessions: did repeating groups help or hurt?
    repeated_acc = []
    novel_acc = []
    for i in range(len(rows) - 1):
        current = rows[i]
        previous = rows[i + 1]
        cur_groups = set(current["mapping_groups_used"].split(","))
        prev_groups = set(previous["mapping_groups_used"].split(","))
        acc = (current["items_correct"] or 0) / (current["items_completed"] or 1)

        overlap = cur_groups & prev_groups
        if overlap:
            repeated_acc.append(acc)
        else:
            novel_acc.append(acc)

    if len(repeated_acc) < 2 or len(novel_acc) < 2:
        return INTERLEAVE_EXCLUDE_WEIGHT

    avg_repeated = sum(repeated_acc) / len(repeated_acc)
    avg_novel = sum(novel_acc) / len(novel_acc)
    diff = avg_novel - avg_repeated  # Positive = novel groups performed better

    # Map the difference to a weight:
    # If novel is much better, use low weight — strong deprioritization of repeats.
    # If repeated is better, use higher weight — allow more repetition.
    # If roughly equal, use moderate weight.
    if diff > INTERLEAVE_STRONG_NOVEL_DIFF:
        weight = INTERLEAVE_WEIGHT_STRONG_NOVEL
    elif diff > INTERLEAVE_MILD_NOVEL_DIFF:
        weight = INTERLEAVE_WEIGHT_MILD_NOVEL
    elif diff < INTERLEAVE_STRONG_REPEAT_DIFF:
        weight = INTERLEAVE_WEIGHT_STRONG_REPEAT
    elif diff < INTERLEAVE_MILD_REPEAT_DIFF:
        weight = INTERLEAVE_WEIGHT_MILD_REPEAT
    else:
        weight = INTERLEAVE_WEIGHT_NEUTRAL

    weight = max(INTERLEAVE_WEIGHT_FLOOR, min(INTERLEAVE_WEIGHT_CEILING, weight))
    logger.debug("adaptive interleave weight: %.2f (novel_acc=%.2f, repeated_acc=%.2f, diff=%.2f)",
                 weight, avg_novel, avg_repeated, diff)
    return weight


def _pick_mapping_groups(n: int = 3, exclude_groups: set[str] | None = None,
                         interleave_weight: float | None = None) -> tuple[set[str], list[str]]:
    """Pick n mapping groups and return (allowed_drill_types, group_names).

    exclude_groups: groups from last session get reduced weight (deprioritized, not banned).
    interleave_weight: adaptive weight for excluded groups (default: INTERLEAVE_EXCLUDE_WEIGHT).
    """
    all_groups = list(MAPPING_GROUPS.keys())
    weight = interleave_weight if interleave_weight is not None else INTERLEAVE_EXCLUDE_WEIGHT

    if exclude_groups:
        # Weighted sampling: excluded groups get reduced weight (deprioritized, not banned)
        weights = [weight if g in exclude_groups else 1.0 for g in all_groups]
        groups = []
        pool = list(zip(all_groups, weights, strict=False))
        for _ in range(min(n, len(all_groups))):
            if not pool:
                break
            total = sum(w for _, w in pool)
            r = random.random() * total
            cumulative = 0
            for i, (g, w) in enumerate(pool):
                cumulative += w
                if r <= cumulative:
                    groups.append(g)
                    pool.pop(i)
                    break
    else:
        groups = random.sample(all_groups, min(n, len(all_groups)))

    allowed = set()
    for g in groups:
        allowed.update(MAPPING_GROUPS[g])
    return allowed, groups


# ── Drill type variety ──────────────────────────────

def _thompson_sample_drill_type(conn, user_id: int, item_id: int, eligible_types: list[str]) -> str:
    """Select drill type via Thompson Sampling (Beta-Bernoulli bandit).

    Each (user, item, drill_type) has Beta(alpha, beta) posterior.
    Sample from each, pick highest. Textbook MAB solution.
    """
    if not eligible_types:
        return "mc"

    try:
        rows = conn.execute("""
            SELECT drill_type, alpha, beta FROM drill_type_posterior
            WHERE user_id = ? AND content_item_id = ?
        """, (user_id, item_id)).fetchall()
        posteriors = {r["drill_type"]: (r["alpha"], r["beta"]) for r in rows}
    except Exception:
        posteriors = {}

    best_type = eligible_types[0]
    best_sample = -1.0
    for dt in eligible_types:
        a, b = posteriors.get(dt, (1.0, 1.0))
        sample = random.betavariate(a, b)
        if sample > best_sample:
            best_sample = sample
            best_type = dt
    return best_type


def _update_drill_type_posterior(conn, user_id: int, item_id: int, drill_type: str, correct: bool):
    """Update Beta posterior after a drill attempt."""
    try:
        conn.execute("""
            INSERT INTO drill_type_posterior (user_id, content_item_id, drill_type, alpha, beta)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id, content_item_id, drill_type)
            DO UPDATE SET
                alpha = alpha + ?,
                beta = beta + ?,
                updated_at = datetime('now')
        """, (user_id, item_id, drill_type,
              2.0 if correct else 1.0, 1.0 if correct else 2.0,
              1.0 if correct else 0.0, 0.0 if correct else 1.0))
        conn.commit()
    except Exception:
        pass


def _bandit_drill_selection(conn: sqlite3.Connection, item: dict,
                            mastery_stage: str, user_id: int = 1,
                            eligible_types: list[str] | None = None) -> str | None:
    """Thompson Sampling bandit: pick drill type using per-item Beta posteriors.

    Delegates to _thompson_sample_drill_type which uses the drill_type_posterior
    table for per-(user, item, drill_type) Beta(alpha, beta) posteriors.

    Falls back to aggregate review_event stats when the posterior table is empty
    and there are at least 30 observations per arm.
    """
    if not eligible_types or len(eligible_types) < 2:
        return None  # Need at least 2 arms to make a choice

    item_id = item.get("id", 0)

    # Try per-item Thompson Sampling from drill_type_posterior table first
    try:
        row_count = conn.execute("""
            SELECT COUNT(*) AS cnt FROM drill_type_posterior
            WHERE user_id = ? AND content_item_id = ?
        """, (user_id, item_id)).fetchone()
        if row_count and (row_count["cnt"] or 0) >= 2:
            return _thompson_sample_drill_type(conn, user_id, item_id, list(eligible_types))
    except Exception:
        pass

    # Fallback: aggregate stats from review_event (original approach)
    MIN_OBS_PER_ARM = 30

    try:
        rows = conn.execute(
            """
            SELECT drill_type,
                   SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) AS successes,
                   SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS failures
            FROM review_event
            WHERE user_id = ?
              AND drill_type IN ({})
            GROUP BY drill_type
            """.format(",".join("?" for _ in eligible_types)),
            [user_id] + list(eligible_types),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    arm_stats = {}
    for r in rows:
        dt = r["drill_type"]
        s = (r["successes"] or 0)
        f = (r["failures"] or 0)
        if s + f >= MIN_OBS_PER_ARM:
            arm_stats[dt] = (s, f)

    # Need at least 2 arms with enough data
    if len(arm_stats) < 2:
        return None

    # Thompson Sampling: sample from Beta(successes + 1, failures + 1)
    best_type = None
    best_sample = -1.0
    for dt, (s, f) in arm_stats.items():
        sample = random.betavariate(s + 1, f + 1)
        if sample > best_sample:
            best_sample = sample
            best_type = dt

    return best_type


_RECOGNITION_DRILL_TYPES = {"mc", "reverse_mc", "tone", "measure_word", "measure_word_disc",
                            "number_system", "radical", "error_correction", "chengyu",
                            "listening_gist", "listening_tone"}


def _item_has_production_history(conn: sqlite3.Connection,
                                  content_item_id: int,
                                  user_id: int = 1) -> bool:
    """Check if an item has ever been correctly answered with a production drill type.

    Used by the anti-Goodhart production bias: items that have only been tested
    with recognition drills are forced onto production drills.
    """
    try:
        row = conn.execute("""
            SELECT 1 FROM review_event
            WHERE user_id = ? AND content_item_id = ?
              AND correct = 1
              AND drill_type NOT IN ('mc', 'reverse_mc', 'tone', 'measure_word',
                  'measure_word_disc', 'number_system', 'radical', 'error_correction',
                  'chengyu', 'listening_gist', 'listening_tone')
            LIMIT 1
        """, (user_id, content_item_id)).fetchone()
        return row is not None
    except Exception:
        return True  # Assume production history exists on error (safe default)


def _pick_drill_type(modality: str, item: dict, variety_tracker: dict[str, list[str]],
                     allowed_types: set[str] | None = None, mastery_stage: str = "seen",
                     conn: sqlite3.Connection | None = None,
                     user_id: int = 1) -> str:
    """Pick a drill type for a given modality, adding variety.

    If allowed_types is provided, prefer types in that set.
    Avoids repeating the same drill type too many times in a row.
    Uses mastery_stage for transfer scaffolding: recognition first,
    then production, then context/transfer drills.
    Feature-flagged drill types are filtered out when conn is provided.
    """
    drill_options = {
        "reading": ["mc", "reverse_mc", "tone", "intuition", "english_to_pinyin", "hanzi_to_pinyin", "pinyin_to_hanzi", "transfer", "measure_word", "measure_word_cloze", "measure_word_production", "measure_word_disc", "word_order", "sentence_build", "particle_disc", "homophone", "translation", "cloze_context", "synonym_disc", "number_system", "tone_sandhi", "complement", "ba_bei", "collocation", "radical", "error_correction", "chengyu"],
        "ime": ["ime_type", "dictation_sentence"],
        "listening": ["listening_gist", "listening_detail", "listening_tone", "listening_dictation", "listening_passage"],
        "speaking": ["speaking", "mc"],  # speaking drill preferred; mc fallback
    }

    options = drill_options.get(modality, ["mc"])

    # Filter out feature-flagged drill types that are disabled
    if conn is not None:
        from .feature_flags import is_drill_enabled
        filtered = [o for o in options if is_drill_enabled(conn, o)]
        if filtered:
            options = filtered

    # Transfer scaffolding: bias drill type by mastery stage
    # Recognition first -> production -> context/transfer
    PRODUCTION_TYPES = {"transfer", "word_order", "sentence_build",
                        "translation", "english_to_pinyin", "hanzi_to_pinyin", "particle_disc",
                        "synonym_disc", "cloze_context", "measure_word_cloze", "measure_word_production",
                        "tone_sandhi", "complement", "ba_bei", "collocation"}
    if mastery_stage in ("seen", "passed_once") and modality == "reading":
        # Prefer recognition drills for early-stage items
        recognition = [t for t in options if t in ("mc", "reverse_mc", "tone", "measure_word", "measure_word_disc", "number_system", "radical", "error_correction", "chengyu")]
        if recognition:
            options = recognition
    elif mastery_stage in ("stabilizing", "stable", "durable") and modality == "reading":
        # Prefer production/transfer drills for established items
        production = [t for t in options if t in PRODUCTION_TYPES]
        if production:
            options = production

    # Anti-Goodhart: force production drills for items that have only been
    # tested with recognition types. This prevents recognition-only advancement.
    if (conn is not None and modality == "reading"
            and mastery_stage in ("stabilizing", "stable", "durable")):
        production_options = [t for t in options if t in PRODUCTION_TYPES]
        if production_options:
            try:
                has_production = _item_has_production_history(
                    conn, item.get("id", 0), user_id)
                if not has_production:
                    options = production_options
            except Exception:
                pass

    # Filter by allowed_types if provided
    if allowed_types:
        filtered = [o for o in options if o in allowed_types]
        if filtered:
            options = filtered
        # If no intersection, fall back to unfiltered

    if len(options) == 1:
        return options[0]

    # Thompson Sampling bandit: try learned drill selection first
    if conn is not None and len(options) >= 2:
        bandit_pick = _bandit_drill_selection(
            conn, item, mastery_stage, user_id=user_id, eligible_types=options
        )
        if bandit_pick and bandit_pick not in variety_tracker.get(modality, [])[-2:]:
            variety_tracker.setdefault(modality, []).append(bandit_pick)
            return bandit_pick

    # Prefer types not recently used — with tone_sandhi weight boost
    recent = variety_tracker.get(modality, [])
    # Build weighted candidates for random fallback
    weighted_options = []
    for opt in options:
        if opt not in recent[-2:]:
            w = TONE_SANDHI_BOOST_WEIGHT if opt == "tone_sandhi" else 1.0
            weighted_options.append((opt, w))
    if weighted_options:
        # Weighted random selection among non-recent options
        total_w = sum(w for _, w in weighted_options)
        r = random.random() * total_w
        cumulative = 0.0
        for opt, w in weighted_options:
            cumulative += w
            if r <= cumulative:
                variety_tracker.setdefault(modality, []).append(opt)
                return opt
        # Fallback
        choice = weighted_options[0][0]
        variety_tracker.setdefault(modality, []).append(choice)
        return choice

    # All recently used — pick randomly with tone_sandhi boost
    weights = [TONE_SANDHI_BOOST_WEIGHT if o == "tone_sandhi" else 1.0 for o in options]
    choice = random.choices(options, weights=weights, k=1)[0]
    variety_tracker.setdefault(modality, []).append(choice)
    return choice


# ── Listen-produce pairing ──────────────────────────────

def _add_listen_produce_pairs(drills: list[DrillItem], max_pairs: int = 2) -> list[DrillItem]:
    """After listening drills, insert a speaking drill for the same item 3 positions later.

    Implements listen-then-produce scaffolding (Slamecka & Graf 1978).
    Caps at max_pairs per session to avoid over-scheduling.
    """
    from dataclasses import replace as dc_replace
    listening_types = {"listening_gist", "listening_detail", "listening_tone"}
    insertions = []  # (position, drill) pairs
    pairs = 0

    for idx, drill in enumerate(drills):
        if (pairs < max_pairs
                and drill.drill_type in listening_types
                and not drill.metadata.get("listen_produce_pair")):
            produce = dc_replace(drill,
                drill_type="speaking",
                modality="speaking",
                metadata={**drill.metadata, "listen_produce_pair": True},
            )
            insert_at = min(idx + 4, len(drills))
            insertions.append((insert_at, produce))
            pairs += 1

    # Insert in reverse order to preserve positions
    result = list(drills)
    for pos, d in reversed(sorted(insertions, key=lambda x: x[0])):
        result.insert(pos, d)
    return result


# ── Scheduler awareness ──────────────────────────────

def _get_underrepresented_registers(conn: sqlite3.Connection, user_id: int = 1) -> list[str]:
    """Find registers the learner hasn't practiced recently.

    Returns registers that are underrepresented in the last 3 sessions.
    """
    recent_items = conn.execute("""
        SELECT DISTINCT ci.register FROM error_log el
        JOIN content_item ci ON el.content_item_id = ci.id
        WHERE el.session_id IN (
            SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 3
        )
        UNION
        SELECT DISTINCT ci.register FROM progress p
        JOIN content_item ci ON p.content_item_id = ci.id
        WHERE p.last_review_date >= date('now', '-7 days')
          AND p.user_id = ?
    """, (user_id, user_id)).fetchall()
    recent_registers = {r["register"] for r in recent_items if r["register"]}

    all_registers = {"casual", "neutral", "professional", "mixed"}
    return list(all_registers - recent_registers)


def _get_lens_weights(conn: sqlite3.Connection, user_id: int = 1) -> dict[str, float]:
    """Get content lens engagement scores from learner profile for weighting."""
    profile = db.get_profile(conn, user_id=user_id)
    if not profile:
        return {}
    lens_map = {
        "lens_quiet_observation": profile.get("lens_quiet_observation") or 0.5,
        "lens_institutions": profile.get("lens_institutions") or 0.5,
        "lens_urban_texture": profile.get("lens_urban_texture") or 0.5,
        "lens_humane_mystery": profile.get("lens_humane_mystery") or 0.5,
        "lens_identity": profile.get("lens_identity") or 0.5,
        "lens_comedy": profile.get("lens_comedy") or 0.5,
        "lens_food": profile.get("lens_food") or 0.5,
        "lens_travel": profile.get("lens_travel") or 0.5,
        "lens_explainers": profile.get("lens_explainers") or 0.5,
        "lens_wit": profile.get("lens_wit") or 0.5,
        "lens_ensemble_comedy": profile.get("lens_ensemble_comedy") or 0.5,
        "lens_sharp_observation": profile.get("lens_sharp_observation") or 0.5,
        "lens_satire": profile.get("lens_satire") or 0.5,
        "lens_moral_texture": profile.get("lens_moral_texture") or 0.5,
    }
    return lens_map


def _get_core_injection_items(conn: sqlite3.Connection, seen_ids: set[int], limit: int = 2, user_id: int = 1) -> list[dict]:
    """Get items from low-coverage core lenses that need injection.

    Core lenses: time_sequence, numbers_measure, function_words.
    Inject items if their coverage is below 50%.
    """
    core_lenses = ["time_sequence", "numbers_measure", "function_words"]
    items = []

    for lens in core_lenses:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN times_shown > 0 THEN 1 ELSE 0 END) as seen
            FROM content_item WHERE content_lens = ? AND status = 'drill_ready'
              AND review_status = 'approved'
        """, (lens,)).fetchone()

        total = row["total"] or 0
        seen = row["seen"] or 0
        if total > 0 and (seen / total) < 0.5:
            # Get unseen items from this lens
            if seen_ids:
                placeholders = ",".join("?" * len(seen_ids))
                unseen = conn.execute("""
                    SELECT * FROM content_item
                    WHERE content_lens = ? AND times_shown = 0
                      AND status = 'drill_ready' AND review_status = 'approved'
                      AND id NOT IN ({placeholders})
                    ORDER BY RANDOM() LIMIT ?
                """.format(placeholders=placeholders), (lens, *seen_ids, limit)).fetchall()
            else:
                unseen = conn.execute("""
                    SELECT * FROM content_item
                    WHERE content_lens = ? AND times_shown = 0
                      AND status = 'drill_ready' AND review_status = 'approved'
                    ORDER BY RANDOM() LIMIT ?
                """, (lens, limit)).fetchall()
            items.extend([dict(r) for r in unseen])

        if len(items) >= limit:
            break

    return items[:limit]


# ── New-item budget ──────────────────────────────

def _check_register_gate(conn: sqlite3.Connection, user_id: int = 1) -> bool:
    """Check if the learner's intuition is strong enough for professional-register items.

    Returns True if professional register items should be included.
    Gate: average intuition accuracy >= 60% with at least 10 attempts.
    """
    row = conn.execute("""
        SELECT SUM(intuition_attempts) as total, SUM(intuition_correct) as correct
        FROM progress WHERE intuition_attempts > 0
          AND user_id = ?
    """, (user_id,)).fetchone()
    total = (row["total"] or 0) if row else 0
    correct = (row["correct"] or 0) if row else 0
    if total < REGISTER_GATE_MIN_ATTEMPTS:
        return False  # Not enough data — keep gated
    return (correct / total) >= REGISTER_GATE_MIN_ACCURACY


def _new_item_budget(conn: sqlite3.Connection, user_id: int = 1) -> int:
    """Determine how many new items to allow per session based on mastery.

    If mastery at current max level < NEW_BUDGET_LOW_MASTERY: 1 new/session
    < NEW_BUDGET_MED_MASTERY: 2 new/session
    else: NEW_BUDGET_DEFAULT (standard)
    """
    mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
    if not mastery or not mastery.keys():
        return NEW_BUDGET_DEFAULT

    max_level = max(mastery.keys())
    pct = (mastery[max_level] or {}).get("pct", 0)
    if pct < NEW_BUDGET_LOW_MASTERY:
        return 1
    elif pct < NEW_BUDGET_MED_MASTERY:
        return 2
    return NEW_BUDGET_DEFAULT


def _get_hsk_prerequisite_cap(conn: sqlite3.Connection, user_id: int = 1) -> int:
    """Return the highest HSK level that can have new items introduced.

    Gate: HSK N+1 items only available if HSK N mastery >= 80%.
    """
    mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
    if not mastery or not mastery.keys():
        return 1  # Start with HSK 1

    max_allowed = 1
    for level in sorted(mastery.keys()):
        pct = (mastery[level] or {}).get("pct", 0)
        if pct >= 80:
            max_allowed = level + 1
        else:
            break
    return max_allowed


# ── Per-HSK bounce detection ──────────────────────────────

def _get_hsk_bounce_levels(conn: sqlite3.Connection, user_id: int = 1) -> set[int]:
    """Detect HSK levels where error rate is too high over last 5 sessions.

    Uses errors/attempts ratio (not absolute error count) for statistical
    meaning. Returns a set of HSK levels that should have fewer new items.
    """
    # Count errors per HSK level from last 5 sessions
    error_rows = conn.execute("""
        SELECT ci.hsk_level, COUNT(*) as errors
        FROM error_log el
        JOIN content_item ci ON el.content_item_id = ci.id
        WHERE el.session_id IN (
            SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 5
        ) AND ci.hsk_level IS NOT NULL
        GROUP BY ci.hsk_level
    """, (user_id,)).fetchall()

    if not error_rows:
        return set()

    hsk_errors = {r["hsk_level"]: r["errors"] for r in error_rows}

    # Get total attempts per HSK level from progress table for items
    # that were drilled in the last 5 sessions
    attempt_rows = conn.execute("""
        SELECT ci.hsk_level, SUM(p.total_attempts) as attempts
        FROM progress p
        JOIN content_item ci ON p.content_item_id = ci.id
        WHERE ci.hsk_level IS NOT NULL
          AND p.user_id = ?
          AND p.content_item_id IN (
              SELECT DISTINCT el.content_item_id
              FROM error_log el
              WHERE el.session_id IN (
                  SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 5
              )
          )
        GROUP BY ci.hsk_level
    """, (user_id, user_id)).fetchall()

    # Flag levels where error rate exceeds threshold
    bounce_levels = set()
    for r in attempt_rows:
        level = r["hsk_level"]
        error_count = hsk_errors.get(level, 0)
        attempts = r["attempts"] or 0
        if attempts == 0:
            continue
        error_rate = error_count / attempts
        if error_rate > BOUNCE_ERROR_RATE and error_count >= BOUNCE_MIN_ERRORS:
            bounce_levels.add(level)

    return bounce_levels


# ── Confusable pair awareness ──────────────────────────────

_confusable_chars_cache = None
_confusable_lock = threading.Lock()

def _load_confusable_chars() -> set[str]:
    """Load set of characters that have known confusable pairs.

    Items containing these characters get a scheduling priority boost
    (CONFUSABLE_BOOST_MULT from config) to ensure more practice on
    visually/phonetically similar characters.
    """
    global _confusable_chars_cache
    if _confusable_chars_cache is not None:
        return _confusable_chars_cache

    with _confusable_lock:
        if _confusable_chars_cache is not None:
            return _confusable_chars_cache
        import json
        from pathlib import Path
        path = Path(__file__).parent.parent / "data" / "confusable_pairs.json"
        chars = set()
        try:
            with open(path) as f:
                pairs = json.load(f)
            for pair in pairs:
                for ch in pair.get("pair", []):
                    chars.add(ch)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        _confusable_chars_cache = chars
        return chars


def clear_confusable_cache() -> None:
    """Reset the confusable characters cache so it reloads on next access."""
    global _confusable_chars_cache
    _confusable_chars_cache = None


def _has_confusable(hanzi: str) -> bool:
    """Check if a hanzi string contains any character with known confusables."""
    chars = _load_confusable_chars()
    return any(ch in chars for ch in hanzi)


# ── Adaptive session length ──────────────────────────────

def _adaptive_session_length(conn: sqlite3.Connection, base_length: int, user_id: int = 1) -> int:
    """Adjust session length based on recent completion patterns.

    If learner consistently doesn't finish sessions, reduce length.
    If consistently completing fully, allow slight increase.
    """
    rows = conn.execute("""
        SELECT items_planned, items_completed FROM session_log
        WHERE items_planned > 0
          AND user_id = ?
        ORDER BY started_at DESC LIMIT ?
    """, (user_id, ADAPTIVE_LENGTH_RECENT_SESSIONS)).fetchall()

    if len(rows) < ADAPTIVE_LENGTH_MIN_SESSIONS:
        return base_length  # Not enough data

    completion_rates = []
    for r in rows:
        planned = r["items_planned"] or 1
        completed = r["items_completed"] or 0
        completion_rates.append(min(1.0, completed / planned))

    avg_completion = sum(completion_rates) / len(completion_rates)

    if avg_completion < ADAPTIVE_LENGTH_LOW_COMPLETION:
        # Learner isn't finishing — shrink session
        adjusted = max(ADAPTIVE_LENGTH_MIN_ITEMS, round(base_length * ADAPTIVE_LENGTH_SHRINK_FACTOR))
        logger.debug("adaptive length: reduced %d -> %d (avg completion %.0f%%)",
                     base_length, adjusted, avg_completion * 100)
        return adjusted
    elif avg_completion >= ADAPTIVE_LENGTH_HIGH_COMPLETION and len(rows) >= ADAPTIVE_LENGTH_HIGH_MIN_SESSIONS:
        # Consistently completing — allow growth
        adjusted = round(base_length * ADAPTIVE_LENGTH_GROW_FACTOR)
        return adjusted

    return base_length


# ── Session planning ──────────────────────────────

def _plan_session_params(conn: sqlite3.Connection, target_items: int | None, user_id: int) -> dict:
    """Compute session parameters: target length, weights, day profile, gap info."""
    if target_items is None:
        profile = db.get_profile(conn, user_id=user_id)
        target_items = profile.get("preferred_session_length") or 12

    target_items = _adaptive_session_length(conn, target_items, user_id=user_id)

    # A/B test: session length experiment — apply variant BEFORE day_profile multiplier
    experiment_variant = None
    try:
        from . import experiments
        variant = experiments.get_variant(conn, "session_length", user_id)
        if variant:
            experiment_variant = variant
            if variant == "12_items":
                target_items = 12
            # "control" variant: keep adaptive target_items as-is
            experiments.log_exposure(conn, "session_length", user_id, context="session_planning")
    except Exception:
        pass

    day_profile = get_day_profile(conn, user_id=user_id)
    target_items = max(MIN_SESSION_ITEMS, round(
        target_items * day_profile["length_mult"] * SESSION_PLAN_REDUCTION_FACTOR
    ))

    days_gap = db.get_days_since_last_session(conn, user_id=user_id)
    is_long_gap = days_gap is not None and days_gap >= LONG_GAP_DAYS

    # Cap reactivation sessions at 12 items (doctrine: 10-15 items on re-entry)
    if is_long_gap:
        target_items = min(target_items, 12)

    base_weights = GAP_WEIGHTS if is_long_gap else DEFAULT_WEIGHTS
    weights = _adjust_weights_for_errors(conn, base_weights, user_id=user_id) if not is_long_gap else dict(base_weights)

    # Boost speaking weight when recent tone accuracy is low
    try:
        from .tone_grading import get_tone_accuracy
        tone_acc = get_tone_accuracy(conn, days=14)
        if tone_acc["total_recordings"] >= TONE_BOOST_MIN_RECORDINGS and tone_acc["overall_accuracy"] < TONE_BOOST_ACCURACY_THRESHOLD:
            weights["speaking"] = min(weights.get("speaking", 0.15) * TONE_BOOST_MULTIPLIER, TONE_BOOST_MAX_WEIGHT)
            total_w = sum(weights.values())
            weights = {m: round(w / total_w, 3) for m, w in weights.items()}
    except (ImportError, KeyError, TypeError) as e:
        logger.debug("tone accent adjustment skipped: %s", e)

    distribution = _pick_modality_distribution(target_items, weights)

    # Cross-session interleaving
    last_groups_used = set()
    try:
        last_row = conn.execute("""
            SELECT mapping_groups_used FROM session_log
            WHERE mapping_groups_used IS NOT NULL
              AND user_id = ?
            ORDER BY started_at DESC LIMIT 1
        """, (user_id,)).fetchone()
        if last_row and last_row["mapping_groups_used"]:
            last_groups_used = set(last_row["mapping_groups_used"].split(","))
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("cross-session interleaving lookup failed: %s", e)

    interleave_weight = _compute_interleave_weight(conn, user_id=user_id)
    allowed_types, chosen_groups = _pick_mapping_groups(
        n=MAPPING_GROUPS_PER_SESSION, exclude_groups=last_groups_used,
        interleave_weight=interleave_weight)

    # New item budget
    new_budget = _new_item_budget(conn, user_id=user_id) if not is_long_gap else 0
    tod_mult = _time_of_day_penalty(conn, user_id=user_id)
    new_budget = max(0, round(new_budget * day_profile["new_mult"] * tod_mult))
    max_new = max(MIN_NEW_ITEMS, round(target_items * MAX_NEW_ITEM_RATIO))
    new_budget = min(new_budget, max_new)

    # Kanban WIP enforcement: block new items if learning WIP exceeds limit
    wip_exceeded = False
    if not is_long_gap:
        new_budget, wip_exceeded = _enforce_wip_limit(conn, new_budget, user_id=user_id)

    bounce_levels = _get_hsk_bounce_levels(conn, user_id=user_id) if not is_long_gap else set()

    profile = db.get_profile(conn, user_id=user_id)
    total_sessions = profile.get("total_sessions") or 0

    plan = {
        "target_items": target_items,
        "day_profile": day_profile,
        "days_gap": days_gap,
        "is_long_gap": is_long_gap,
        "distribution": distribution,
        "weights": weights,
        "allowed_types": allowed_types,
        "chosen_groups": chosen_groups,
        "new_budget": new_budget,
        "bounce_levels": bounce_levels,
        "total_sessions": total_sessions,
        "experiment_variant": experiment_variant,
        "wip_exceeded": wip_exceeded,
    }

    # Apply metrics-to-scheduler feedback loop (skip for long-gap reactivation sessions)
    if not is_long_gap:
        try:
            plan = _apply_metrics_feedback(conn, user_id, plan)
        except Exception as e:
            logger.debug("metrics feedback skipped: %s", e)

    return plan


def _get_metrics_snapshot(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Compute a lightweight metrics snapshot for scheduler feedback.

    Returns dict with:
        retention_7d: float (0.0-1.0) — 7-day vocabulary retention rate
        modality_coverage: dict[str, float] — fraction of sessions covering each modality
        accuracy_trend: str — "improving", "stable", or "declining"
    """
    import json

    snapshot = {
        "retention_7d": None,
        "modality_coverage": {},
        "accuracy_trend": "stable",
    }

    # 7-day retention: fraction of items reviewed in last 7 days that are at 85%+ accuracy
    try:
        total_row = conn.execute("""
            SELECT COUNT(*) AS total FROM progress
            WHERE total_attempts >= 3
              AND last_review_date >= date('now', '-7 days')
              AND user_id = ?
        """, (user_id,)).fetchone()
        retained_row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM progress
            WHERE total_attempts >= 3
              AND (total_correct * 1.0 / total_attempts) >= 0.85
              AND last_review_date >= date('now', '-7 days')
              AND user_id = ?
        """, (user_id,)).fetchone()
        total = (total_row["total"] or 0) if total_row else 0
        retained = (retained_row["cnt"] or 0) if retained_row else 0
        snapshot["retention_7d"] = (retained / total) if total > 0 else None
    except Exception:
        pass

    # Modality coverage: for each modality, fraction of last 7 days' sessions that used it
    try:
        rows = conn.execute("""
            SELECT modality_counts FROM session_log
            WHERE started_at >= datetime('now', '-7 days')
              AND items_completed > 0
              AND modality_counts IS NOT NULL
              AND user_id = ?
        """, (user_id,)).fetchall()
        total_sessions = len(rows)
        if total_sessions > 0:
            modality_counts = {"reading": 0, "listening": 0, "speaking": 0, "ime": 0}
            for r in rows:
                try:
                    mc = json.loads(r["modality_counts"])
                    for mod in modality_counts:
                        if mc.get(mod, 0) > 0:
                            modality_counts[mod] += 1
                except (json.JSONDecodeError, TypeError):
                    pass
            snapshot["modality_coverage"] = {
                mod: cnt / total_sessions for mod, cnt in modality_counts.items()
            }
    except Exception:
        pass

    # Accuracy trend: compare this week vs last week
    try:
        tw = conn.execute("""
            SELECT SUM(items_completed) AS items, SUM(items_correct) AS correct
            FROM session_log
            WHERE started_at >= datetime('now', '-7 days')
              AND items_completed > 0
              AND user_id = ?
        """, (user_id,)).fetchone()
        lw = conn.execute("""
            SELECT SUM(items_completed) AS items, SUM(items_correct) AS correct
            FROM session_log
            WHERE started_at >= datetime('now', '-14 days')
              AND started_at < datetime('now', '-7 days')
              AND items_completed > 0
              AND user_id = ?
        """, (user_id,)).fetchone()
        tw_items = (tw["items"] or 0) if tw else 0
        tw_correct = (tw["correct"] or 0) if tw else 0
        lw_items = (lw["items"] or 0) if lw else 0
        lw_correct = (lw["correct"] or 0) if lw else 0
        tw_acc = tw_correct / tw_items if tw_items > 0 else None
        lw_acc = lw_correct / lw_items if lw_items > 0 else None
        if tw_acc is not None and lw_acc is not None:
            delta = tw_acc - lw_acc
            if delta < -0.05:
                snapshot["accuracy_trend"] = "declining"
            elif delta > 0.05:
                snapshot["accuracy_trend"] = "improving"
            else:
                snapshot["accuracy_trend"] = "stable"
    except Exception:
        pass

    return snapshot


def _apply_metrics_feedback(conn: sqlite3.Connection, user_id: int, plan: dict) -> dict:
    """Adjust session plan based on computed metrics snapshot.

    Rules:
    - If 7-day retention rate < 60%, reduce new_item_budget by 50%
    - If modality coverage < 50% for any modality, boost that modality's weight by 1.5x
    - If accuracy trend is "declining", reduce session length by 20%

    Modifies plan dict in-place and returns it.
    """
    snapshot = _get_metrics_snapshot(conn, user_id)
    adjustments = []

    # Rule 1: Low retention → cut new items
    retention = snapshot.get("retention_7d")
    if retention is not None and retention < 0.60:
        old_budget = plan["new_budget"]
        plan["new_budget"] = max(0, round(old_budget * 0.5))
        adjustments.append(f"retention {retention:.0%} < 60%: new_budget {old_budget} -> {plan['new_budget']}")

    # Rule 2: Low modality coverage → boost underrepresented modality weights
    coverage = snapshot.get("modality_coverage", {})
    weights = plan.get("weights", {})
    boosted = False
    for mod, cov in coverage.items():
        if cov < 0.50 and mod in weights:
            weights[mod] = weights[mod] * 1.5
            boosted = True
            adjustments.append(f"{mod} coverage {cov:.0%} < 50%: weight boosted 1.5x")
    if boosted:
        # Renormalize weights
        total_w = sum(weights.values())
        if total_w > 0:
            plan["weights"] = {m: round(w / total_w, 3) for m, w in weights.items()}
        # Recompute distribution with adjusted weights
        plan["distribution"] = _pick_modality_distribution(plan["target_items"], plan["weights"])

    # Rule 3: Declining accuracy → reduce session length
    if snapshot.get("accuracy_trend") == "declining":
        old_target = plan["target_items"]
        plan["target_items"] = max(MIN_SESSION_ITEMS, round(old_target * 0.8))
        adjustments.append(f"accuracy declining: target_items {old_target} -> {plan['target_items']}")
        # Recompute distribution with reduced target
        plan["distribution"] = _pick_modality_distribution(plan["target_items"], plan["weights"])

    # ── Counter-metric scheduler adjustments ──
    # Read recent scheduler_adjust lifecycle events from the counter-metrics daemon
    cm_adjustments = _apply_counter_metric_adjustments(conn, user_id, plan)
    adjustments.extend(cm_adjustments)

    # ── Metacognitive data integration (Dunlosky 2013) ──
    # Adjust new item budget based on last session's self-assessment
    try:
        recent_assessment = conn.execute("""
            SELECT difficulty_rating FROM session_self_assessment
            WHERE user_id = ? ORDER BY created_at DESC LIMIT 1
        """, (user_id,)).fetchone()
        if recent_assessment:
            old_budget = plan["new_budget"]
            if recent_assessment["difficulty_rating"] == "too_hard":
                plan["new_budget"] = max(2, plan["new_budget"] - 1)
                if plan["new_budget"] != old_budget:
                    adjustments.append(f"metacog:too_hard: new_budget {old_budget} -> {plan['new_budget']}")
            elif recent_assessment["difficulty_rating"] == "too_easy":
                plan["new_budget"] = min(8, plan["new_budget"] + 1)
                if plan["new_budget"] != old_budget:
                    adjustments.append(f"metacog:too_easy: new_budget {old_budget} -> {plan['new_budget']}")
    except Exception:
        pass

    # Identify overconfident items (high confidence + wrong, 2+ times in 14 days)
    # These are stored on the plan dict so the modality drill planner can boost them
    try:
        rows = conn.execute("""
            SELECT item_id FROM confidence_calibration
            WHERE user_id = ? AND confidence = 'high' AND was_correct = 0
            AND created_at >= datetime('now', '-14 days')
            GROUP BY item_id HAVING COUNT(*) >= 2
        """, (user_id,)).fetchall()
        overconfident_ids = {r["item_id"] for r in rows}
        if overconfident_ids:
            plan["_overconfident_ids"] = overconfident_ids
            adjustments.append(f"metacog:overconfident: {len(overconfident_ids)} items flagged for priority review")
    except Exception:
        pass

    if adjustments:
        logger.info("metrics feedback adjustments for user %d: %s", user_id, "; ".join(adjustments))

    plan["_metrics_snapshot"] = snapshot
    plan["_metrics_adjustments"] = adjustments
    return plan


def _apply_counter_metric_adjustments(conn: sqlite3.Connection, user_id: int,
                                       plan: dict) -> list[str]:
    """Read counter_metric_scheduler_adjust lifecycle events and apply them to the plan.

    Returns list of adjustment descriptions for logging.
    """
    import json as _json

    adjustments = []

    try:
        rows = conn.execute("""
            SELECT metadata FROM lifecycle_event
            WHERE event_type = 'counter_metric_scheduler_adjust'
              AND user_id = ?
              AND created_at >= datetime('now', '-24 hours')
            ORDER BY created_at DESC
        """, (user_id,)).fetchall()
    except Exception:
        return adjustments

    # Deduplicate: only apply the most recent action of each type
    seen_actions = set()
    for row in rows:
        try:
            data = _json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
        except (TypeError, ValueError):
            continue

        action = data.get("action")
        if not action or action in seen_actions:
            continue
        seen_actions.add(action)
        params = data.get("params", {})

        if action == "reduce_new_item_budget":
            mult = params.get("multiplier", 0.7)
            old = plan["new_budget"]
            plan["new_budget"] = max(0, round(old * mult))
            adjustments.append(f"CM:{action}: new_budget {old} -> {plan['new_budget']}")

        elif action == "pause_new_items":
            plan["new_budget"] = 0
            adjustments.append(f"CM:{action}: new_budget -> 0 (paused)")

        elif action == "increase_spacing_multiplier":
            # Store on plan so modality drill planner can read it
            plan["_cm_spacing_factor"] = params.get("factor", 0.85)
            adjustments.append(f"CM:{action}: spacing factor {plan['_cm_spacing_factor']}")

        elif action == "shorten_sessions":
            mult = params.get("multiplier", params.get("factor", 0.75))
            old_target = plan["target_items"]
            plan["target_items"] = max(MIN_SESSION_ITEMS, round(old_target * mult))
            plan["distribution"] = _pick_modality_distribution(
                plan["target_items"], plan["weights"])
            adjustments.append(f"CM:{action}: target {old_target} -> {plan['target_items']}")

        elif action == "switch_to_minimal_mode":
            plan["target_items"] = MIN_SESSION_ITEMS
            plan["new_budget"] = 0
            plan["distribution"] = _pick_modality_distribution(
                plan["target_items"], plan["weights"])
            adjustments.append("CM:switch_to_minimal_mode: target -> minimal, new_budget -> 0")

        elif action == "boost_production_drills":
            plan["_cm_production_boost"] = params.get("production_weight", 2.0)
            adjustments.append(f"CM:{action}: production weight {plan['_cm_production_boost']}x")

        elif action == "enforce_production_gate":
            plan["_cm_production_gate"] = True
            adjustments.append("CM:enforce_production_gate: block recognition-only promotion")

        elif action == "increase_drill_diversity":
            plan["_cm_min_drill_types"] = params.get("min_types", 3)
            adjustments.append(f"CM:{action}: min {plan['_cm_min_drill_types']} drill types per item")

        elif action == "increase_difficulty_floor":
            plan["_cm_difficulty_floor"] = params.get("min_difficulty", 0.3)
            adjustments.append(f"CM:{action}: min difficulty {plan['_cm_difficulty_floor']}")

        elif action == "increase_long_term_reviews":
            plan["_cm_lt_review_boost"] = params.get("boost_factor", 1.3)
            adjustments.append(f"CM:{action}: long-term review boost {plan['_cm_lt_review_boost']}x")

        elif action == "add_response_floor":
            plan["_cm_response_floor_ms"] = params.get("floor_ms", 800)
            adjustments.append(f"CM:{action}: response floor {plan['_cm_response_floor_ms']}ms")

    return adjustments


def _plan_error_focus_items(conn: sqlite3.Connection, seen_ids: set, user_id: int) -> list:
    """Reserve error-focus drills (items the learner keeps getting wrong)."""
    drills = []
    error_focus_items = db.get_error_focus_items(conn, limit=ERROR_FOCUS_LIMIT, user_id=user_id)
    for ef_item in error_focus_items:
        if ef_item["id"] in seen_ids:
            continue
        error_type = ef_item.get("focus_error_type", "other")
        preferred_types = ERROR_DRILL_PREFERENCE.get(error_type, ["mc"])
        chosen_type = None
        for dt in preferred_types:
            if _item_is_drillable(ef_item, dt):
                chosen_type = dt
                break
        if not chosen_type:
            continue
        ef_modality = "ime" if chosen_type == "ime_type" else "reading"
        seen_ids.add(ef_item["id"])
        drills.append(DrillItem(
            content_item_id=ef_item["id"],
            hanzi=ef_item["hanzi"],
            pinyin=ef_item["pinyin"],
            english=ef_item["english"],
            modality=ef_modality,
            drill_type=chosen_type,
            is_error_focus=True,
        ))
    return drills


def _plan_contrastive_drills(conn, seen_ids, user_id=1):
    """Schedule up to 2 contrastive drills for high-interference pairs.

    Picks unresolved high-strength pairs where both items have progress rows
    (i.e. the learner has seen both items before).
    """
    drills = []
    try:
        rows = conn.execute("""
            SELECT ip.item_id_a, ip.item_id_b
            FROM interference_pairs ip
            JOIN progress pa ON pa.content_item_id = ip.item_id_a AND pa.user_id = ?
            JOIN progress pb ON pb.content_item_id = ip.item_id_b AND pb.user_id = ?
            JOIN content_item ca ON ca.id = ip.item_id_a
            JOIN content_item cb ON cb.id = ip.item_id_b
            WHERE ip.interference_strength = 'high'
              AND ip.item_id_a NOT IN ({seen})
              AND ip.item_id_b NOT IN ({seen})
            ORDER BY RANDOM()
            LIMIT 4
        """.format(seen=",".join(str(s) for s in seen_ids) if seen_ids else "0"),
            (user_id, user_id)).fetchall()
    except Exception:
        return drills

    for row in rows:
        if len(drills) >= 2:
            break
        id_a, id_b = row["item_id_a"], row["item_id_b"]
        if id_a in seen_ids or id_b in seen_ids:
            continue
        # Look up item A's data for the DrillItem
        item_a = conn.execute(
            "SELECT id, hanzi, pinyin, english FROM content_item WHERE id = ?",
            (id_a,)
        ).fetchone()
        if not item_a:
            continue
        seen_ids.add(id_a)
        seen_ids.add(id_b)
        drills.append(DrillItem(
            content_item_id=id_a,
            hanzi=item_a["hanzi"],
            pinyin=item_a["pinyin"],
            english=item_a["english"],
            modality="reading",
            drill_type="contrastive",
            metadata={"contrastive_partner_id": id_b},
        ))
    return drills


def _plan_minimal_pair_drills(conn, drills, seen_ids, user_id=1):
    """Inject minimal-pair contrast drills at ~30% probability.

    Queries high-interference pairs where both items are known by the learner,
    then creates 'minimal_pair' drill items that show both items side-by-side
    and ask the learner to distinguish them.
    """
    try:
        from .ai.memory_model import get_active_contrast_pairs
        contrast_pairs = get_active_contrast_pairs(conn, user_id, limit=3)
    except Exception:
        return

    for pair in contrast_pairs:
        if random.random() >= 0.3:
            continue
        id_a, id_b = pair["item_id_a"], pair["item_id_b"]
        if id_a in seen_ids and id_b in seen_ids:
            continue
        seen_ids.add(id_a)
        seen_ids.add(id_b)
        drills.append(DrillItem(
            content_item_id=id_a,
            hanzi=pair["hanzi_a"],
            pinyin=pair["pinyin_a"],
            english=pair["english_a"],
            modality="reading",
            drill_type="minimal_pair",
            metadata={
                "item_a": {
                    "id": id_a,
                    "hanzi": pair["hanzi_a"],
                    "pinyin": pair["pinyin_a"],
                    "english": pair["english_a"],
                },
                "item_b": {
                    "id": id_b,
                    "hanzi": pair["hanzi_b"],
                    "pinyin": pair["pinyin_b"],
                    "english": pair["english_b"],
                },
                "interference_type": pair["interference_type"],
            },
        ))


def _apply_cross_session_interference_penalty(conn, due_items):
    """Soft-deprioritize items whose interference partner was drilled in the last session.

    Moves recently-conflicted items toward the end of the list rather than
    hard-blocking them, giving the learner spacing between confusable pairs.
    """
    if not due_items:
        return
    item_ids = [i["id"] for i in due_items]
    if not item_ids:
        return
    placeholders = ",".join("?" * len(item_ids))
    try:
        recent_partners = conn.execute("""
            SELECT ip.item_id_a, ip.item_id_b
            FROM interference_pairs ip
            WHERE ip.interference_strength = 'high'
              AND (ip.item_id_a IN ({placeholders}) OR ip.item_id_b IN ({placeholders}))
              AND (ip.last_item_a_drilled >= datetime('now', '-1 day')
                   OR ip.last_item_b_drilled >= datetime('now', '-1 day'))
        """.format(placeholders=placeholders), item_ids + item_ids).fetchall()
    except sqlite3.OperationalError:
        return

    if not recent_partners:
        return

    # Build set of items that should be deprioritized
    item_set = set(item_ids)
    penalized = set()
    for row in recent_partners:
        a, b = row["item_id_a"], row["item_id_b"]
        # If partner A was drilled recently, penalize B (and vice versa)
        if a in item_set:
            penalized.add(a)
        if b in item_set:
            penalized.add(b)

    if penalized:
        # Stable sort: penalized items move to end, preserving relative order
        due_items.sort(key=lambda x: 1 if x["id"] in penalized else 0)


def _check_grammar_prerequisite(conn: sqlite3.Connection, user_id: int,
                                 grammar_point_id: int) -> dict | None:
    """Check if a grammar point's prerequisites are met; return substitution info if not.

    Returns None if prerequisites are met (or checking fails).
    Returns {'substitute_id': int, 'original_name': str, 'blocking_name': str}
    if a prerequisite is blocking.
    """
    try:
        from .ai.grammar_tutor import check_prerequisites
        result = check_prerequisites(conn, user_id, grammar_point_id)
        if result['all_met'] or not result['blocking']:
            return None
        blocker = result['blocking'][0]
        # Get original grammar point name
        orig = conn.execute(
            "SELECT name FROM grammar_point WHERE id = ?", (grammar_point_id,)
        ).fetchone()
        orig_name = orig['name'] if orig else ''
        return {
            'substitute_id': blocker['id'],
            'original_name': orig_name,
            'blocking_name': blocker['title'],
            'blocking_mastery': blocker['mastery_score'],
        }
    except Exception:
        return None


def _get_substitute_drill_items(conn: sqlite3.Connection, substitute_grammar_id: int,
                                 user_id: int, seen_ids: set, limit: int = 2) -> list:
    """Get content items linked to a substitute grammar point for prerequisite drills."""
    try:
        rows = conn.execute("""
            SELECT DISTINCT ci.id, ci.hanzi, ci.pinyin, ci.english,
                   gp.name as grammar_name,
                   COALESCE(p.mastery_stage, 'unseen') as stage
            FROM content_grammar cg
            JOIN content_item ci ON ci.id = cg.content_item_id
            JOIN grammar_point gp ON gp.id = cg.grammar_point_id
            LEFT JOIN progress p ON p.content_item_id = ci.id
                AND p.modality = 'reading' AND p.user_id = ?
            WHERE cg.grammar_point_id = ?
              AND ci.status = 'drill_ready'
              AND ci.review_status = 'approved'
            ORDER BY RANDOM()
            LIMIT ?
        """, (user_id, substitute_grammar_id, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _plan_grammar_boost_items(conn: sqlite3.Connection, seen_ids: set,
                               target_items: int, drills: list, user_id: int) -> None:
    """Boost scheduling weight for items linked to recently-studied grammar points.

    When a user studies a grammar point, the linked vocabulary items get
    priority in the next few sessions, reinforcing both grammar understanding
    and vocabulary mastery simultaneously.

    Prerequisite gating: before boosting items for a grammar point, checks
    whether prerequisites are met. If not, substitutes drills for the
    blocking prerequisite instead (Pienemann's Processability Theory).
    """
    try:
        boost_limit = max(2, target_items // 6)  # Up to ~16% of session
        # Find content items linked to grammar points studied in last 3 days
        grammar_items = conn.execute("""
            SELECT DISTINCT ci.id, ci.hanzi, ci.pinyin, ci.english, ci.hsk_level,
                   gp.name as grammar_name, gp.id as grammar_point_id,
                   COALESCE(p.mastery_stage, 'unseen') as stage
            FROM grammar_progress gpr
            JOIN content_grammar cg ON cg.grammar_point_id = gpr.grammar_point_id
            JOIN content_item ci ON ci.id = cg.content_item_id
            JOIN grammar_point gp ON gp.id = gpr.grammar_point_id
            LEFT JOIN progress p ON p.content_item_id = ci.id
                AND p.modality = 'reading' AND p.user_id = ?
            WHERE gpr.user_id = ?
              AND gpr.studied_at >= datetime('now', '-3 days')
              AND ci.status = 'drill_ready'
              AND ci.review_status = 'approved'
            ORDER BY gpr.studied_at DESC
            LIMIT ?
        """, (user_id, user_id, boost_limit * 2)).fetchall()

        added = 0
        checked_grammar_ids = {}  # Cache prerequisite checks per grammar_point_id
        for gi in grammar_items:
            if gi["id"] in seen_ids or added >= boost_limit:
                break
            if len(drills) >= target_items:
                break

            # ── Prerequisite gate ──
            gp_id = gi["grammar_point_id"]
            if gp_id not in checked_grammar_ids:
                checked_grammar_ids[gp_id] = _check_grammar_prerequisite(
                    conn, user_id, gp_id
                )
            sub_info = checked_grammar_ids[gp_id]

            if sub_info:
                # Substitute with prerequisite drills instead
                sub_items = _get_substitute_drill_items(
                    conn, sub_info['substitute_id'], user_id, seen_ids, limit=1
                )
                for si in sub_items:
                    if si["id"] in seen_ids or added >= boost_limit:
                        break
                    seen_ids.add(si["id"])
                    stage = si.get("stage", "unseen")
                    drill_type = "mc" if stage in ("unseen", "seen") else "reverse_mc"
                    drills.append(DrillItem(
                        content_item_id=si["id"],
                        hanzi=si["hanzi"],
                        pinyin=si["pinyin"],
                        english=si["english"],
                        modality="reading",
                        drill_type=drill_type,
                        metadata={
                            "grammar_boost": True,
                            "grammar_name": si.get("grammar_name", ""),
                            "prerequisite_substitute": True,
                            "original_grammar": sub_info['original_name'],
                            "blocking_grammar": sub_info['blocking_name'],
                        },
                    ))
                    added += 1
                continue  # Skip the original item

            seen_ids.add(gi["id"])
            # Drill type based on mastery stage
            stage = gi["stage"]
            if stage in ("unseen", "seen"):
                drill_type = "mc"
            elif stage == "passed_once":
                drill_type = "reverse_mc"
            else:
                drill_type = "cloze_context"
            drills.append(DrillItem(
                content_item_id=gi["id"],
                hanzi=gi["hanzi"],
                pinyin=gi["pinyin"],
                english=gi["english"],
                modality="reading",
                drill_type=drill_type,
                metadata={"grammar_boost": True,
                          "grammar_name": gi["grammar_name"]},
            ))
            added += 1
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("grammar boost skipped: %s", e)


def _plan_encounter_boost_items(conn: sqlite3.Connection, seen_ids: set,
                                 target_items: int, drills: list, user_id: int) -> None:
    """Inject priority review items from recent reading/listening lookups.

    Scales with session length (up to ENCOUNTER_BOOST_RATIO of target).
    Prioritizes items within ENCOUNTER_PRIORITY_WINDOW_DAYS (3 days) to
    consolidate within the optimal 24-48 hour window, then falls back to
    the full ENCOUNTER_FULL_WINDOW_DAYS (14 days) window.
    """
    try:
        boost_limit = max(4, int(target_items * ENCOUNTER_BOOST_RATIO))
        # Priority: recent lookups first (within 3 days), then older (up to 14 days)
        encounter_items = conn.execute("""
            SELECT DISTINCT ve.content_item_id, ci.hanzi, ci.pinyin, ci.english,
                   ci.hsk_level, COUNT(*) as lookup_count,
                   COALESCE(p.mastery_stage, 'unseen') as stage,
                   COALESCE(p.total_attempts, 0) as attempts,
                   MAX(ve.created_at) as last_lookup
            FROM vocab_encounter ve
            JOIN content_item ci ON ve.content_item_id = ci.id
            LEFT JOIN progress p ON p.content_item_id = ci.id
                AND p.modality = 'reading' AND p.user_id = ?
            WHERE ve.looked_up = 1
              AND ve.created_at >= datetime('now', ? || ' days')
              AND ci.status = 'drill_ready'
              AND ci.review_status = 'approved'
              AND ve.user_id = ?
            GROUP BY ve.content_item_id
            ORDER BY
                CASE WHEN MAX(ve.created_at) >= datetime('now', ? || ' days')
                     THEN 0 ELSE 1 END,
                lookup_count DESC
            LIMIT ?
        """, (user_id, f"-{ENCOUNTER_FULL_WINDOW_DAYS}", user_id,
              f"-{ENCOUNTER_PRIORITY_WINDOW_DAYS}", boost_limit)).fetchall()
        for ei in encounter_items:
            if ei["content_item_id"] in seen_ids:
                continue
            if len(drills) >= target_items:
                break
            seen_ids.add(ei["content_item_id"])
            # Vary drill type by mastery stage
            stage = ei["stage"]
            if stage in ("unseen", "seen"):
                drill_type = "mc"  # Recognition for new items
            elif stage == "passed_once":
                drill_type = "reverse_mc"  # Reverse recognition
            else:
                drill_type = "ime_type"  # Production for familiar items
            drills.append(DrillItem(
                content_item_id=ei["content_item_id"],
                hanzi=ei["hanzi"],
                pinyin=ei["pinyin"],
                english=ei["english"],
                modality="reading",
                drill_type=drill_type,
                metadata={"encounter_boost": True, "lookup_count": ei["lookup_count"]},
            ))

        # Log activation event: encounter→drill loop completed
        boosted = [d for d in drills if d.metadata.get("encounter_boost")]
        if boosted:
            try:
                from .marketing_hooks import log_lifecycle_event
                # Check if this is the user's first magic moment
                first = conn.execute(
                    """SELECT 1 FROM lifecycle_event
                       WHERE event_type = 'first_encounter_drilled'
                       AND user_id = ? LIMIT 1""",
                    (str(user_id),),
                ).fetchone()
                if not first:
                    log_lifecycle_event(
                        "first_encounter_drilled",
                        user_id=str(user_id),
                        conn=conn,
                        items=[d.hanzi for d in boosted[:5]],
                    )
                log_lifecycle_event(
                    "encounter_drilled",
                    user_id=str(user_id),
                    conn=conn,
                    count=len(boosted),
                )
            except Exception:
                pass  # Don't break session planning for telemetry
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("encounter boost skipped: %s", e)


def _plan_reading_struggle_boost(conn: sqlite3.Connection, seen_ids: set,
                                  target_items: int, drills: list, user_id: int) -> None:
    """Boost items encountered in passages where comprehension was low.

    If a user scored < 60% on reading comprehension questions in the last 7 days,
    the words they encountered in those passages need reinforcement through drills.
    """
    try:
        boost_limit = max(2, target_items // 6)  # Up to ~16% of session
        struggle_items = conn.execute("""
            SELECT DISTINCT ve.content_item_id, ci.hanzi, ci.pinyin, ci.english,
                   ci.hsk_level,
                   COALESCE(p.mastery_stage, 'unseen') as stage,
                   rp.questions_correct, rp.questions_total
            FROM reading_progress rp
            JOIN vocab_encounter ve ON ve.source_type = 'reading'
                AND ve.source_id = rp.passage_id AND ve.user_id = ?
            JOIN content_item ci ON ci.id = ve.content_item_id
            LEFT JOIN progress p ON p.content_item_id = ci.id
                AND p.modality = 'reading' AND p.user_id = ?
            WHERE rp.user_id = ?
              AND rp.completed_at >= datetime('now', '-7 days')
              AND rp.questions_total > 0
              AND CAST(rp.questions_correct AS REAL) / rp.questions_total < 0.6
              AND ci.status = 'drill_ready'
              AND ci.review_status = 'approved'
            ORDER BY rp.completed_at DESC
            LIMIT ?
        """, (user_id, user_id, user_id, boost_limit * 3)).fetchall()

        added = 0
        for si in struggle_items:
            if si["content_item_id"] in seen_ids or added >= boost_limit:
                break
            if len(drills) >= target_items:
                break
            seen_ids.add(si["content_item_id"])
            stage = si["stage"]
            if stage in ("unseen", "seen"):
                drill_type = "mc"
            elif stage == "passed_once":
                drill_type = "reverse_mc"
            else:
                drill_type = "cloze_context"
            drills.append(DrillItem(
                content_item_id=si["content_item_id"],
                hanzi=si["hanzi"],
                pinyin=si["pinyin"],
                english=si["english"],
                modality="reading",
                drill_type=drill_type,
                metadata={"reading_struggle_boost": True},
            ))
            added += 1
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("reading struggle boost skipped: %s", e)


def _pick_least_recent_drill_type(modality_history: dict, weak_modality: str,
                                  weak_stage: str) -> str:
    """Choose a drill type that hasn't been practiced recently for this item.

    Uses the modality_history JSON (drill_type -> last_date) to pick the drill
    type with the oldest (or missing) timestamp, ensuring variety.
    """
    import json as _json

    # Candidate drill types per modality, ordered by stage progression
    _MODALITY_DRILL_TYPES = {
        "reading": ["mc", "reverse_mc", "hanzi_to_pinyin", "english_to_pinyin",
                     "pinyin_to_hanzi", "translation", "contrastive"],
        "listening": ["listening_gist", "listening_detail", "listening_tone",
                      "listening_dictation"],
        "speaking": ["speaking", "shadowing"],
        "ime": ["ime_type"],
    }

    candidates = _MODALITY_DRILL_TYPES.get(weak_modality, ["mc"])
    if not candidates:
        return "mc"

    if isinstance(modality_history, str):
        try:
            modality_history = _json.loads(modality_history)
        except (_json.JSONDecodeError, TypeError):
            modality_history = {}

    # Sort candidates by their last practice date (oldest first, missing = highest priority)
    def sort_key(dt):
        return modality_history.get(dt, "")  # empty string sorts before any date

    candidates_sorted = sorted(candidates, key=sort_key)

    # For early stages, restrict to simpler drill types
    if weak_stage == "seen":
        simple = [c for c in candidates_sorted if c in ("mc", "listening_gist", "speaking", "ime_type")]
        if simple:
            return simple[0]

    return candidates_sorted[0]


def _plan_cross_modality_boost_items(conn: sqlite3.Connection, seen_ids: set,
                                      target_items: int, drills: list, user_id: int) -> None:
    """Boost items mastered in one modality but weak in another.

    The cross-modality audit found items where reading is 'stable'/'durable'
    but listening (or vice versa) is still 'seen'/'passed_once'. These items
    are low-hanging fruit: the learner already knows the vocabulary, they just
    need practice in the weak modality to close the gap.

    Uses modality_history to prefer drill types the item hasn't been practiced
    in recently, ensuring cross-modal variety.

    Injects up to CROSS_MODALITY_BOOST_LIMIT items per session, drilled in
    the weak modality.
    """
    try:
        # Find items with a strong modality (stable/durable) and a weak one (seen/passed_once)
        gap_items = conn.execute("""
            SELECT strong.content_item_id,
                   strong.modality AS strong_modality,
                   weak.modality AS weak_modality,
                   weak.mastery_stage AS weak_stage,
                   weak.modality_history AS modality_history,
                   ci.hanzi, ci.pinyin, ci.english
            FROM progress strong
            JOIN progress weak
                ON strong.content_item_id = weak.content_item_id
                AND strong.user_id = weak.user_id
                AND strong.modality != weak.modality
            JOIN content_item ci ON ci.id = strong.content_item_id
            WHERE strong.user_id = ?
              AND strong.mastery_stage IN ('stable', 'durable')
              AND weak.mastery_stage IN ('seen', 'passed_once')
              AND ci.status = 'drill_ready'
              AND ci.review_status = 'approved'
            ORDER BY
                -- Prioritise bigger gaps (durable vs seen > stable vs passed_once)
                CASE strong.mastery_stage WHEN 'durable' THEN 2 ELSE 1 END
                + CASE weak.mastery_stage WHEN 'seen' THEN 2 ELSE 1 END
                DESC
            LIMIT ?
        """, (user_id, CROSS_MODALITY_BOOST_LIMIT * 3)).fetchall()

        added = 0
        for row in gap_items:
            if added >= CROSS_MODALITY_BOOST_LIMIT:
                break
            if row["content_item_id"] in seen_ids:
                continue
            if len(drills) >= target_items:
                break

            weak_modality = row["weak_modality"]
            weak_stage = row["weak_stage"]
            history = row["modality_history"] if "modality_history" in row.keys() else "{}"

            # Pick a drill type the item hasn't been practiced in recently
            drill_type = _pick_least_recent_drill_type(
                history or "{}", weak_modality, weak_stage)

            seen_ids.add(row["content_item_id"])
            drills.append(DrillItem(
                content_item_id=row["content_item_id"],
                hanzi=row["hanzi"],
                pinyin=row["pinyin"],
                english=row["english"],
                modality=weak_modality,
                drill_type=drill_type,
                metadata={
                    "cross_modality_boost": True,
                    "strong_modality": row["strong_modality"],
                    "weak_modality": weak_modality,
                },
            ))
            added += 1

        if added:
            logger.debug("cross-modality boost: injected %d items", added)
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("cross-modality boost skipped: %s", e)


# ── Operations Research: Formal Objective Function ──────────────────────
#
# The composite score ranks items for selection by combining four factors:
#   1. Retention urgency:  How overdue is this item? (higher = more urgent)
#   2. Difficulty match:   How close is the item difficulty to the learner's sweet spot?
#   3. Variety penalty:    Have we recently drilled this item/type? (penalize repeats)
#   4. Error weight:       Items with recent errors get priority
#
# Weights are tuned so that urgency dominates but variety prevents staleness.

OBJECTIVE_WEIGHTS = {
    "retention_urgency": 0.40,
    "difficulty_match": 0.20,
    "variety_bonus": 0.15,
    "error_weight": 0.25,
}


def _compute_item_priority(item: dict, recent_ids: set, recent_drill_types: list,
                           target_difficulty: float = 0.6) -> float:
    """Compute composite priority score for a single item using formal objective function.

    Returns a float in [0, 1] where higher = should be scheduled sooner.
    """
    w = OBJECTIVE_WEIGHTS

    # 1. Retention urgency: days overdue / (interval * 2)
    interval = max(item.get("current_interval") or 1.0, 0.1)
    days_since = item.get("days_since_review") or 0
    urgency = min(1.0, days_since / (interval * 2))

    # 2. Difficulty match: use ML prediction if available, else static difficulty
    diff = item.get("difficulty") or 0.5
    ml_predicted_acc = item.get("_ml_predicted_accuracy")
    if ml_predicted_acc is not None:
        # ML model: score highest when predicted accuracy is in 70-85% zone
        if 0.70 <= ml_predicted_acc <= 0.85:
            match_score = 1.0
        else:
            distance = min(abs(ml_predicted_acc - 0.70), abs(ml_predicted_acc - 0.85))
            match_score = max(0.0, 1.0 - distance * 4)
    else:
        match_score = max(0.0, 1.0 - abs(diff - target_difficulty) * 2.5)

    # 3. Variety: penalize items already seen in this session
    variety = 0.0 if item.get("id") in recent_ids else 1.0
    drill_type = item.get("_candidate_drill_type", "mc")
    if drill_type in recent_drill_types[-3:]:
        variety *= 0.5

    # 4. Error weight: items with errors or low streak get boost
    error_count = item.get("error_count") or 0
    streak = item.get("streak_correct") or 0
    error_score = min(1.0, error_count * 0.2) if error_count > 0 else 0.0
    if streak == 0 and (item.get("total_attempts") or 0) > 0:
        error_score = max(error_score, 0.3)

    score = (w["retention_urgency"] * urgency +
             w["difficulty_match"] * match_score +
             w["variety_bonus"] * variety +
             w["error_weight"] * error_score)

    return round(score, 4)


def _annotate_ml_predictions(conn: sqlite3.Connection, items: list,
                              user_id: int = 1, session_id=None,
                              position: int = 0) -> None:
    """Annotate items with ML difficulty predictions (in-place, best effort).

    Sets _ml_predicted_accuracy on each item dict. Skips silently if model
    unavailable or prediction fails.
    """
    try:
        from .ml.difficulty_model import predict_difficulty, load_model, MODEL_PATH
        if load_model(MODEL_PATH) is None:
            return
        for item in items:
            try:
                pred = predict_difficulty(
                    conn, item_id=item.get("id"), user_id=user_id,
                    session_id=session_id, position_in_session=position,
                    modality=item.get("_candidate_modality", "reading"),
                )
                if pred.get("model_available"):
                    item["_ml_predicted_accuracy"] = pred["predicted_accuracy"]
            except Exception:
                pass
    except (ImportError, Exception):
        pass


def rank_items_by_objective(items: list, recent_ids: set,
                            recent_drill_types: list,
                            target_difficulty: float = 0.6) -> list:
    """Rank candidate items by the formal objective function (descending priority)."""
    scored = []
    for item in items:
        score = _compute_item_priority(item, recent_ids, recent_drill_types,
                                       target_difficulty)
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ── Operations Research: Decision Table ──────────────────────────────

SCHEDULING_DECISION_TABLE = [
    {
        "rule": "long_gap_reactivation",
        "description": "User returning after extended absence",
        "conditions": {"days_gap": ">= 7"},
        "actions": {"new_items": 0, "max_difficulty": 0.5, "session_type": "catchup",
                     "priority": "familiar_first"},
    },
    {
        "rule": "high_wip_block",
        "description": "Too many items in learning state — consolidate before adding new",
        "conditions": {"wip_count": "> wip_limit"},
        "actions": {"new_items": 0, "priority": "overdue_first"},
    },
    {
        "rule": "bounce_detected",
        "description": "Error rate at an HSK level exceeds threshold",
        "conditions": {"bounce_levels": "non-empty"},
        "actions": {"new_items_at_level": "reduce_50%", "priority": "error_focus"},
    },
    {
        "rule": "consolidation_day",
        "description": "Day profile indicates lighter session",
        "conditions": {"day_mode": "in (consolidation, gentle)"},
        "actions": {"new_items_mult": 0.5, "max_difficulty": 0.6, "length_mult": 0.8},
    },
    {
        "rule": "stretch_day",
        "description": "Day profile indicates strong performance window",
        "conditions": {"day_mode": "== stretch"},
        "actions": {"new_items_mult": 1.5, "length_mult": 1.3, "hsk_cap": "+1"},
    },
    {
        "rule": "standard_session",
        "description": "Normal scheduling — balanced new and review",
        "conditions": {"default": True},
        "actions": {"new_items": "budget", "priority": "objective_function"},
    },
]


def evaluate_decision_table(params: dict) -> dict:
    """Evaluate the scheduling decision table against current session params.

    Returns the merged actions from all matching rules.
    """
    matched_rules = []
    merged_actions = {}

    is_long_gap = params.get("is_long_gap", False)
    bounce_levels = params.get("bounce_levels", set())
    day_mode = params.get("day_profile", {}).get("mode", "standard")
    wip_count = params.get("wip_count", 0)
    wip_limit = params.get("wip_limit", 999)

    for rule in SCHEDULING_DECISION_TABLE:
        conditions = rule["conditions"]
        match = False

        if "days_gap" in conditions and is_long_gap:
            match = True
        elif "wip_count" in conditions and wip_count > wip_limit:
            match = True
        elif "bounce_levels" in conditions and bounce_levels:
            match = True
        elif "day_mode" in conditions:
            if day_mode in ("consolidation", "gentle") and "consolidation" in conditions["day_mode"]:
                match = True
            elif day_mode == "stretch" and "stretch" in conditions["day_mode"]:
                match = True
        elif "default" in conditions:
            match = True

        if match:
            matched_rules.append(rule["rule"])
            merged_actions.update(rule["actions"])

    return {"matched_rules": matched_rules, "actions": merged_actions}


def sensitivity_analysis(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Test how session outcomes change when key parameters vary +/-20%.

    Identifies which parameters have the most impact on session quality.
    """
    from .config import MAX_NEW_ITEM_RATIO, NEW_BUDGET_DEFAULT

    profile = db.get_profile(conn, user_id=user_id)
    base_target = profile.get("preferred_session_length") or 12

    results = {}

    for param_name, base_val in [
        ("target_items", base_target),
        ("new_item_ratio", MAX_NEW_ITEM_RATIO),
        ("new_budget", NEW_BUDGET_DEFAULT),
    ]:
        low_val = max(1, round(base_val * 0.8)) if isinstance(base_val, int) else round(base_val * 0.8, 3)
        high_val = round(base_val * 1.2) if isinstance(base_val, int) else round(base_val * 1.2, 3)

        if param_name == "target_items":
            low_effect = {"total_drills": low_val, "est_duration_s": low_val * SECONDS_PER_DRILL}
            high_effect = {"total_drills": high_val, "est_duration_s": high_val * SECONDS_PER_DRILL}
        elif param_name == "new_item_ratio":
            low_new = max(1, round(base_target * low_val))
            high_new = round(base_target * high_val)
            low_effect = {"max_new_items": low_new, "review_items": base_target - low_new}
            high_effect = {"max_new_items": high_new, "review_items": base_target - high_new}
        else:
            low_effect = {"new_budget": low_val}
            high_effect = {"new_budget": high_val}

        impact = abs(high_val - low_val) / max(base_val, 0.001)
        sensitivity = "high" if impact > 0.3 else ("medium" if impact > 0.15 else "low")

        results[param_name] = {
            "base_value": base_val, "low_value": low_val, "high_value": high_val,
            "low_effect": low_effect, "high_effect": high_effect,
            "sensitivity": sensitivity,
        }

    return results


# ── Kanban: WIP Enforcement ──────────────────────────────────────────

LEARNING_WIP_LIMIT = 30

# Register with parameter graph
try:
    from .intelligence.parameter_registry import _PARAMETER_REGISTRY_PENDING
    _PARAMETER_REGISTRY_PENDING.append({
        "parameter_name": "LEARNING_WIP_LIMIT", "file_path": "mandarin/scheduler.py",
        "current_value": LEARNING_WIP_LIMIT, "current_value_str": str(LEARNING_WIP_LIMIT),
        "value_type": "int", "primary_dimension": "srs_funnel",
        "secondary_dimensions": '["retention"]', "min_valid": 10, "max_valid": 200,
        "soft_min": 20, "soft_max": 60, "change_direction": "either",
        "notes": "Kanban WIP limit for items in active learning",
    })
except ImportError:
    pass


def _get_learning_wip(conn: sqlite3.Connection, user_id: int = 1) -> int:
    """Count items currently in active learning (short interval, recently reviewed)."""
    try:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM progress
            WHERE user_id = ?
              AND current_interval < 7
              AND last_review_date >= date('now', '-14 days')
              AND mastery_stage NOT IN ('durable', 'stable')
        """, (user_id,)).fetchone()
        return (row["cnt"] or 0) if row else 0
    except Exception:
        return 0


def _enforce_wip_limit(conn: sqlite3.Connection, new_budget: int,
                       user_id: int = 1) -> tuple[int, bool]:
    """Enforce Kanban WIP limit on new item introduction.

    Returns (adjusted_new_budget, wip_exceeded).
    """
    wip = _get_learning_wip(conn, user_id)
    if wip >= LEARNING_WIP_LIMIT:
        logger.info("WIP limit enforced: %d items in learning (limit: %d), blocking new items",
                    wip, LEARNING_WIP_LIMIT)
        return 0, True
    if wip > LEARNING_WIP_LIMIT * 0.8:
        reduction = (wip - LEARNING_WIP_LIMIT * 0.8) / (LEARNING_WIP_LIMIT * 0.2)
        adjusted = max(0, round(new_budget * (1 - reduction)))
        return adjusted, False
    return new_budget, False


# ── Kanban: Aging Escalation Tiers ──────────────────────────────────

AGING_TIERS = {
    "green": {"min_days": 0, "max_days": 0, "label": "On time", "priority_mult": 1.0},
    "yellow": {"min_days": 1, "max_days": 2, "label": "Slightly overdue", "priority_mult": 1.3},
    "orange": {"min_days": 3, "max_days": 7, "label": "Overdue", "priority_mult": 1.6},
    "red": {"min_days": 8, "max_days": 999, "label": "Critical overdue", "priority_mult": 2.0},
}


def _get_aging_tier(days_overdue: int) -> str:
    """Classify an item's overdue status into an aging tier."""
    if days_overdue <= 0:
        return "green"
    elif days_overdue <= 2:
        return "yellow"
    elif days_overdue <= 7:
        return "orange"
    else:
        return "red"


def get_aging_summary(conn: sqlite3.Connection, user_id: int = 1) -> dict:
    """Summarize item aging tiers for the admin dashboard."""
    try:
        rows = conn.execute("""
            SELECT content_item_id,
                   CAST(julianday('now') - julianday(
                       datetime(last_review_date, '+' || CAST(ROUND(current_interval) AS TEXT) || ' days')
                   ) AS INTEGER) AS days_overdue
            FROM progress
            WHERE user_id = ?
              AND last_review_date IS NOT NULL
              AND current_interval IS NOT NULL
        """, (user_id,)).fetchall()
    except Exception:
        return {"green": 0, "yellow": 0, "orange": 0, "red": 0, "total": 0}

    counts = {"green": 0, "yellow": 0, "orange": 0, "red": 0}
    for r in rows:
        days = r["days_overdue"] or 0
        tier = _get_aging_tier(days)
        counts[tier] += 1

    counts["total"] = sum(counts.values())
    return counts


# ── Kanban: Explicit Policies ────────────────────────────────────────

KANBAN_POLICIES = {
    "definition_of_done": {
        "mc": "Correct answer selected within 15 seconds",
        "reverse_mc": "Correct answer selected within 15 seconds",
        "ime_type": "Correct hanzi typed within 30 seconds",
        "tone": "Correct tone mark identified",
        "listening_gist": "Main meaning captured correctly",
        "speaking": "Tone accuracy >= 60% on graded recording",
        "dialogue": "Completed all turns with appropriate responses",
    },
    "entry_criteria": {
        "hsk1": "No prerequisite",
        "hsk2": "HSK 1 mastery >= 80%",
        "hsk3": "HSK 2 mastery >= 80%",
        "hsk4": "HSK 3 mastery >= 80%",
    },
    "exit_criteria": {
        "mastery_stage_durable": "5+ consecutive correct, interval >= 21 days",
        "mastery_stage_stable": "3+ consecutive correct, interval >= 7 days",
        "hsk_level_complete": "90% of items at durable stage",
    },
    "escalation_rules": {
        "error_focus_trigger": "3+ errors on same item within 5 sessions",
        "error_focus_resolve": "3 consecutive correct answers",
        "hsk_bounce": f"Error rate > {BOUNCE_ERROR_RATE*100}% at a level with >= {BOUNCE_MIN_ERRORS} errors",
    },
    "wip_limit": LEARNING_WIP_LIMIT,
}


def _plan_modality_drills(conn: sqlite3.Connection, params: dict,
                           drills: list, seen_ids: set, user_id: int) -> int:
    """Fill drills from due items per modality. Returns remaining new_budget."""
    from .config import SCAFFOLD_LEVELS
    distribution = params["distribution"]
    is_long_gap = params["is_long_gap"]
    is_consolidation = params["day_profile"]["mode"] in ("consolidation", "gentle")
    is_stretch = params["day_profile"]["mode"] == "stretch"
    allowed_types = params["allowed_types"]
    bounce_levels = params["bounce_levels"]
    new_budget = params["new_budget"]

    intuition_gate = _check_register_gate(conn, user_id=user_id)
    confidence_wins_needed = CONFIDENCE_WINS_NEEDED
    variety_tracker = {}

    for modality, count in distribution.items():
        due_items = db.get_items_due(conn, modality, limit=count + 10, user_id=user_id)

        if not intuition_gate:
            due_items = [i for i in due_items
                         if i.get("register") != "professional"] or due_items

        for _i, item in enumerate(due_items):
            if _has_confusable(item.get("hanzi", "")):
                item["_confusable_boost"] = True

        if is_long_gap or is_consolidation:
            due_items.sort(key=lambda x: x.get("streak_correct") or 0, reverse=True)
        elif is_stretch:
            due_items.sort(key=lambda x: x.get("streak_correct") or 0)
        else:
            # Normal session: use ML difficulty predictions as soft preference
            _annotate_ml_predictions(conn, due_items, user_id=user_id)
            due_items.sort(
                key=lambda x: abs((x.get("_ml_predicted_accuracy") or 0.75) - 0.775),
            )

        if is_consolidation:
            due_items = [i for i in due_items if (i.get("difficulty") or 0.5) <= 0.6] or due_items

        # Boost overconfident items to front of queue (metacognitive calibration)
        overconfident_ids = params.get("_overconfident_ids", set())
        if overconfident_ids:
            due_items.sort(key=lambda x: 0 if x["id"] in overconfident_ids else 1)

        items_added = 0
        # Interference-aware filtering (within-session + cross-session)
        try:
            from .ai.memory_model import apply_interference_separation
            session_item_ids = [d.content_item_id for d in drills]
            # Within-session: hard block high-interference pairs
            if session_item_ids:
                candidate_ids = [i["id"] for i in due_items]
                filtered_set = set(apply_interference_separation(
                    conn, user_id, candidate_ids, session_item_ids))
                due_items = [i for i in due_items if i["id"] in filtered_set]
            # Cross-session: soft deprioritize items whose partner was drilled recently
            _apply_cross_session_interference_penalty(conn, due_items)
        except Exception:
            pass  # Interference data may not exist yet

        for item in due_items:
            if items_added >= count:
                break
            if item["id"] in seen_ids:
                continue

            if (item.get("_confusable_boost") and modality == "reading"
                    and random.random() < CONFUSABLE_ROUTE_PROBABILITY
                    and _item_is_drillable(item, "homophone")):
                drill_type = "homophone"
            else:
                mastery_stage = item.get("mastery_stage") or "seen"
                drill_type = _pick_drill_type(modality, item, variety_tracker,
                                              allowed_types=allowed_types,
                                              mastery_stage=mastery_stage,
                                              conn=conn)

            # Generation effect (Slamecka & Graf 1978): mastered items switch
            # to production-type drills to force deeper retrieval processing.
            # Items with half_life > 14 days have a 50% chance of override.
            item_half_life = item.get("half_life_days") or 0
            if item_half_life > 14 and random.random() < 0.5:
                _GENERATION_PROD_TYPES = (
                    'ime_type', 'english_to_pinyin', 'hanzi_to_pinyin',
                    'pinyin_to_hanzi', 'translation', 'word_order',
                    'sentence_build', 'cloze_context',
                )
                gen_candidates = [
                    t for t in _GENERATION_PROD_TYPES
                    if (not allowed_types or t in allowed_types)
                    and _item_is_drillable(item, t)
                ]
                if gen_candidates:
                    drill_type = random.choice(gen_candidates)

            if not _item_is_drillable(item, drill_type):
                continue

            mastery_stage = item.get("mastery_stage") or "seen"
            levels = SCAFFOLD_LEVELS.get(mastery_stage, {"pinyin": "none", "english": "full"})
            scaffold_level = levels["pinyin"]
            english_level = levels["english"]

            # Annotate difficulty data for difficulty interleaving (Phase 4)
            item_difficulty = item.get("item_difficulty") or item.get("difficulty")
            ml_acc = item.get("_ml_predicted_accuracy")

            seen_ids.add(item["id"])
            drill = DrillItem(
                content_item_id=item["id"],
                hanzi=item["hanzi"],
                pinyin=item["pinyin"],
                english=item["english"],
                modality=modality,
                drill_type=drill_type,
                metadata={
                    "scaffold_level": scaffold_level,
                    "english_level": english_level,
                    "hsk_level": item.get("hsk_level", 0),
                    "item_difficulty": item_difficulty,
                    "_ml_predicted_accuracy": ml_acc,
                },
            )

            if confidence_wins_needed > 0 and (item.get("streak_correct") or 0) >= 2:
                drill.is_confidence_win = True
                confidence_wins_needed -= 1
            drills.append(drill)
            items_added += 1

        # Fill remaining with new items — Dijkstra-guided then HSK fallback
        if items_added < count and not is_long_gap and new_budget > 0:
            new_limit = min(count - items_added, new_budget)
            hsk_max = _get_hsk_prerequisite_cap(conn, user_id=user_id)
            if is_stretch:
                mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
                if mastery:
                    hsk_max = max(hsk_max, max(mastery.keys()) + 1)

            # Try Dijkstra-guided selection first (shortest path to next HSK level)
            dijkstra_items = []
            try:
                from mandarin.quality.curriculum_graph import suggest_next_items
                path_ids = suggest_next_items(conn, user_id, goal=None, n=new_limit + 5)
                if path_ids:
                    placeholders = ",".join("?" * len(path_ids))
                    rows = conn.execute(
                        "SELECT * FROM content_item WHERE id IN ({}) AND drill_ready=1".format(placeholders),
                        path_ids,
                    ).fetchall()
                    dijkstra_items = [dict(r) for r in rows] if rows else []
            except Exception:
                pass

            # HSK-level fallback
            hsk_items = db.get_new_items(conn, modality, limit=new_limit + 5, hsk_max=hsk_max, user_id=user_id)

            # Merge: Dijkstra first, then HSK items not already in Dijkstra set
            dijkstra_ids = {i["id"] for i in dijkstra_items}
            new_items = dijkstra_items + [i for i in hsk_items if i["id"] not in dijkstra_ids]
            if bounce_levels:
                new_items = [i for i in new_items if i.get("hsk_level") not in bounce_levels] or new_items
            for item in new_items:
                if items_added >= count or new_budget <= 0:
                    break
                if item["id"] in seen_ids:
                    continue

                drill_type = _pick_drill_type(modality, item, variety_tracker,
                                              allowed_types=allowed_types,
                                              mastery_stage="seen",
                                              conn=conn)
                if not _item_is_drillable(item, drill_type):
                    continue

                seen_ids.add(item["id"])
                drill = DrillItem(
                    content_item_id=item["id"],
                    hanzi=item["hanzi"],
                    pinyin=item["pinyin"],
                    english=item["english"],
                    modality=modality,
                    drill_type=drill_type,
                    is_new=True,
                )
                drills.append(drill)
                items_added += 1
                new_budget -= 1

    return new_budget


def _plan_injections(conn: sqlite3.Connection, drills: list, seen_ids: set, user_id: int) -> None:
    """Inject core lexicon, conversation, personalization, and media drills."""
    # Core lexicon safety check
    core_coverage = db.get_core_lexicon_coverage(conn)
    any_below_50 = any(c["pct"] < 50 for c in core_coverage.values() if c["total"] > 0)
    if any_below_50:
        catchup_items = db.get_core_catchup_items(conn, limit=3)
        for item in catchup_items:
            if item["id"] in seen_ids:
                continue
            drill_type = "mc"
            if not _item_is_drillable(item, drill_type):
                continue
            seen_ids.add(item["id"])
            drills.append(DrillItem(
                content_item_id=item["id"],
                hanzi=item["hanzi"],
                pinyin=item["pinyin"],
                english=item["english"],
                modality="reading",
                drill_type=drill_type,
                is_new=item.get("times_shown", 0) == 0,
            ))
    else:
        core_items = _get_core_injection_items(conn, seen_ids, limit=2, user_id=user_id)
        for item in core_items:
            if item["id"] in seen_ids:
                continue
            drill_type = "mc"
            if not _item_is_drillable(item, drill_type):
                continue
            seen_ids.add(item["id"])
            drills.append(DrillItem(
                content_item_id=item["id"],
                hanzi=item["hanzi"],
                pinyin=item["pinyin"],
                english=item["english"],
                modality="reading",
                drill_type=drill_type,
                is_new=True,
            ))

    # Conversation drills
    try:
        from .scenario_loader import get_available_scenarios, determine_support_level
        profile = db.get_profile(conn, user_id=user_id)
        max_hsk = max(int(profile.get("level_reading", 1) or 1), 1) + 1
        scenarios = get_available_scenarios(conn, hsk_max=max_hsk, limit=5)
        conv_added = 0
        for scenario in scenarios:
            if conv_added >= 2:
                break
            support_level = determine_support_level(scenario)
            drills.append(DrillItem(
                content_item_id=0,
                hanzi="",
                pinyin="",
                english=scenario["title"],
                modality="reading",
                drill_type="dialogue",
                metadata={"scenario_id": scenario["id"], "support_level": support_level, "reason": "dialogue"},
            ))
            conv_added += 1
    except (ImportError, sqlite3.Error, KeyError, TypeError, ValueError) as e:
        logger.debug("scenario injection skipped: %s", e)

    # Personalized context sentences
    try:
        profile = db.get_profile(conn, user_id=user_id)
        pref_domains = (profile.get("preferred_domains") or "").strip()
        if pref_domains:
            from .personalization import get_personalized_sentences
            domains = [d.strip() for d in pref_domains.split(",") if d.strip()]
            max_hsk = max(int(profile.get("level_reading", 1) or 1), 1) + 1
            for domain in domains[:1]:
                sentences = get_personalized_sentences(max_hsk, domain, n=1)
                for sent in sentences:
                    drills.append(DrillItem(
                        content_item_id=0,
                        hanzi=sent["hanzi"],
                        pinyin=sent.get("pinyin", ""),
                        english=sent.get("english", ""),
                        modality="reading",
                        drill_type="mc",
                        metadata={"reason": "personalized", "domain": domain, "ai_generated": True, "source": "qwen2.5-7b"},
                    ))
    except (ImportError, sqlite3.Error, KeyError, TypeError, ValueError) as e:
        logger.debug("personalization injection skipped: %s", e)

    # Media comprehension
    try:
        from .media import get_pending_comprehension, get_media_entry
        pending_mid = get_pending_comprehension(conn)
        if pending_mid:
            entry = get_media_entry(pending_mid)
            if entry:
                drills.append(DrillItem(
                    content_item_id=0,
                    hanzi="",
                    pinyin="",
                    english=entry.get("title", "Media quiz"),
                    modality="listening",
                    drill_type="media_comprehension",
                    metadata={"media_id": pending_mid, "reason": "media_pending"},
                ))
    except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("media comprehension injection skipped: %s", e)


def _build_focus_insights(drills: list, params: dict, conn: sqlite3.Connection, user_id: int) -> list[str]:
    """Build human-readable insights explaining why the session is composed this way.

    Returns up to 3 short insight strings showing the adaptive intelligence at work.
    """
    insights = []

    # 1. Error focus items (highest priority — most actionable)
    error_drills = [d for d in drills if d.is_error_focus]
    if error_drills:
        error_types = {}
        for d in error_drills:
            et = d.metadata.get("error_type", "other")
            error_types[et] = error_types.get(et, 0) + 1
        type_parts = []
        for et, cnt in sorted(error_types.items(), key=lambda x: -x[1]):
            label = {"tone": "tone", "segment": "segmentation", "ime_confusable": "typing",
                     "vocab": "vocabulary", "grammar": "grammar"}.get(et, et)
            type_parts.append(f"{cnt} {label}")
        insights.append(f"Targeting {len(error_drills)} items you keep missing ({', '.join(type_parts)})")

    # 2. Encounter boost items (shows cross-feature learning)
    encounter_drills = [d for d in drills if d.metadata.get("encounter_boost")]
    if encounter_drills:
        insights.append(f"Reinforcing {len(encounter_drills)} words you looked up while reading")

    # 3. Tone accuracy boost (shows adaptive weighting)
    try:
        from .tone_grading import get_tone_accuracy
        tone_acc = get_tone_accuracy(conn, days=14, user_id=user_id)
        if (tone_acc["total_recordings"] >= 5
                and tone_acc["overall_accuracy"] < 0.65):
            pct = round(tone_acc["overall_accuracy"] * 100)
            insights.append(f"Extra speaking practice — tone accuracy at {pct}%")
    except (ImportError, KeyError, TypeError):
        pass

    # 4. Day profile mode (shows schedule awareness)
    day_profile = params.get("day_profile", {})
    mode = day_profile.get("mode", "normal")
    if mode == "consolidation":
        insights.append("Consolidation day — shorter session, familiar items")
    elif mode == "gentle":
        insights.append("Light day — review-focused, no new items")
    elif mode == "stretch":
        insights.append("Stretch day — extra items and new material")

    # 5. Bounce levels (shows level awareness)
    bounce_levels = params.get("bounce_levels", set())
    if bounce_levels:
        levels_str = ", ".join(str(l) for l in sorted(bounce_levels))
        insights.append(f"HSK {levels_str} accuracy dipping — adding reinforcement")

    # 6. New items (shows pacing awareness)
    new_count = sum(1 for d in drills if d.is_new)
    if new_count > 0 and not any("new" in i.lower() for i in insights):
        insights.append(f"Introducing {new_count} new item{'s' if new_count != 1 else ''}")

    # 7. Long gap (already shown via gap_message, but add context)
    if params.get("is_long_gap"):
        params.get("days_gap", 0)
        insights.append(f"Welcome back — starting with familiar items to rebuild confidence")

    # 8. WIP limit (Kanban enforcement transparency)
    if params.get("wip_exceeded"):
        insights.append("Consolidating — many items in active learning, no new items this session")

    # 9. Cold start transparency — tell the learner when personalization hasn't started
    total_sessions = params.get("total_sessions", 0)
    if total_sessions < 10 and not insights:
        insights.append("Standard intervals for now — personalization begins after ~10 sessions")

    return insights[:1]  # One insight per session (doctrine: max one personalized suggestion)


def _plan_holdout_probes(conn: sqlite3.Connection, drills: list,
                         seen_ids: set, user_id: int) -> None:
    """Inject holdout probes into the session (anti-Goodhart Rule 4).

    Holdout probes are hidden benchmark items presented in novel drill formats.
    Results are recorded in counter_metric_holdout, NEVER in the main progress
    table, so the SRS optimizer cannot see them.
    """
    try:
        from .holdout_probes import get_session_probes
    except ImportError:
        return

    probes = get_session_probes(conn, user_id=user_id,
                                session_item_count=len(drills))
    for probe in probes:
        cid = probe["content_item_id"]
        if cid in seen_ids:
            continue
        if not _item_is_drillable_by_fields(
            probe.get("hanzi"), probe.get("pinyin"), probe.get("english"),
            probe["drill_type"]
        ):
            continue
        seen_ids.add(cid)
        drills.append(DrillItem(
            content_item_id=cid,
            hanzi=probe.get("hanzi", ""),
            pinyin=probe.get("pinyin", ""),
            english=probe.get("english", ""),
            modality=probe.get("modality", "reading"),
            drill_type=probe["drill_type"],
            metadata={"is_holdout": True, "holdout_set": "standard"},
        ))


def _plan_delayed_validations(conn: sqlite3.Connection, drills: list,
                              seen_ids: set, user_id: int) -> None:
    """Inject delayed recall validation probes into the session.

    These are integrity checks for items that recently reached mastery.
    Results feed counter-metrics only, NEVER the SRS.
    """
    try:
        from .delayed_validation import get_session_validations
    except ImportError:
        return

    validations = get_session_validations(conn, user_id=user_id)
    for v in validations:
        cid = v["content_item_id"]
        if cid in seen_ids:
            continue
        if not _item_is_drillable_by_fields(
            v.get("hanzi"), v.get("pinyin"), v.get("english"),
            v["drill_type"]
        ):
            continue
        seen_ids.add(cid)
        drills.append(DrillItem(
            content_item_id=cid,
            hanzi=v.get("hanzi", ""),
            pinyin=v.get("pinyin", ""),
            english=v.get("english", ""),
            modality=v.get("modality", "reading"),
            drill_type=v["drill_type"],
            metadata={
                "is_delayed_validation": True,
                "validation_id": v["validation_id"],
                "delay_days": v["delay_days"],
            },
        ))


def _item_is_drillable_by_fields(hanzi: str | None, pinyin: str | None,
                                  english: str | None, drill_type: str) -> bool:
    """Check if item fields are sufficient for a given drill type (no DB row needed)."""
    if drill_type in ("mc", "reverse_mc", "tone", "intuition", "listening_gist",
                       "listening_detail", "sentence_build"):
        return bool(hanzi and english)
    if drill_type in ("english_to_pinyin", "hanzi_to_pinyin", "pinyin_to_hanzi"):
        return bool(hanzi and pinyin and english)
    return bool(hanzi and pinyin and english)


def _build_session_plan(drills: list, params: dict, conn: sqlite3.Connection, user_id: int) -> SessionPlan:
    """Finalize drills: LP-optimize, interleave, build micro-plan, tier-gate, create SessionPlan."""
    # LP optimization: reorder drills for maximum retention gain per minute
    try:
        from mandarin.quality.optimization import optimize_session
        lp_result = optimize_session(conn, user_id, drills, params.get("session_length_minutes", 10) * 60)
        if lp_result and lp_result.get("success") and lp_result.get("order"):
            id_order = lp_result["order"]
            id_to_drill = {d.item_id: d for d in drills}
            reordered = [id_to_drill[i] for i in id_order if i in id_to_drill]
            remaining = [d for d in drills if d.item_id not in {i for i in id_order}]
            if reordered:
                drills = reordered + remaining
    except Exception:
        pass  # Keep heuristic ordering

    drills = _interleave(drills)
    drills = _add_listen_produce_pairs(drills)
    drills = _apply_peak_end_ordering(drills, conn, user_id)

    # Build micro-plan
    modality_summary = {}
    new_count = sum(1 for d in drills if d.is_new)
    conv_count = sum(1 for d in drills if d.drill_type == "dialogue")
    media_count = sum(1 for d in drills if d.drill_type == "media_comprehension")
    for d in drills:
        if d.drill_type not in ("dialogue", "media_comprehension"):
            modality_summary[d.modality] = modality_summary.get(d.modality, 0) + 1

    parts = []
    for mod_key in ("ime", "reading", "listening", "speaking"):
        if modality_summary.get(mod_key):
            label = MODALITY_LABELS.get(mod_key, mod_key).lower()
            parts.append(f"{modality_summary[mod_key]} {label}")
    if conv_count:
        parts.append(f"{conv_count} dialogue")
    if media_count:
        parts.append(f"{media_count} media")
    if new_count:
        parts.append(f"{new_count} new")

    micro_plan = " · ".join(parts)

    # Tier gating
    from .tier_gate import get_user_tier, filter_items_by_tier, filter_drills_by_tier
    tier = get_user_tier(conn, user_id)
    drills = filter_drills_by_tier(drills, tier)

    days_gap = params["days_gap"]
    day_profile = params["day_profile"]
    chosen_groups = params["chosen_groups"]

    # Build focus insights before tier-gating (uses full drill list)
    try:
        focus_insights = _build_focus_insights(drills, params, conn, user_id)
    except Exception as e:
        logger.debug("focus insights skipped: %s", e)
        focus_insights = []

    # Build blocks using the cleanup loop pattern:
    #   ReadingBlock(exposure) -> DrillBlock -> ReadingBlock(reread) -> ConversationBlock
    # The exposure reading collects unknown words; drills reinforce them;
    # the re-read lets the user see their progress on the same passage.
    drill_seconds = len(drills) * SECONDS_PER_DRILL + conv_count * SECONDS_PER_CONVERSATION

    profile = db.get_profile(conn, user_id=user_id)
    hsk_level = profile.get("hsk_level", 1) if profile else 1

    # Alternate reading and listening by session: odd sessions get reading,
    # even sessions get listening. Falls back to the other if one is unavailable.
    total_sessions = (profile.get("total_sessions") or 0) if profile else 0
    is_listening_session = total_sessions % 2 == 0  # even = listening, odd = reading

    reading_block = None
    listening_block = None

    if drill_seconds >= 180:
        if is_listening_session:
            listening_block = _pick_listening_block(conn, user_id, hsk_level)
            if not listening_block:
                # Fallback to reading if no listening passage available
                reading_block = _pick_reading_block(conn, user_id, hsk_level)
        else:
            reading_block = _pick_reading_block(conn, user_id, hsk_level)
            if not reading_block:
                # Fallback to listening if no reading passage available
                listening_block = _pick_listening_block(conn, user_id, hsk_level)

    if reading_block:
        # Cleanup loop: exposure -> drills -> re-read
        exposure_block = reading_block  # is_reread=False by default
        exposure_block.target_seconds = 180  # exposure is exploratory, not timed test

        reread_block = ReadingBlock(
            passage_id=reading_block.passage_id,
            passage=reading_block.passage,
            questions=[],  # no questions on re-read
            target_seconds=75,  # short reinforcement (~60-90s)
            is_reread=True,
        )

        blocks = [
            exposure_block,
            DrillBlock(items=drills, target_seconds=drill_seconds),
            reread_block,
        ]
        micro_plan += " · 1 reading"

        conv_block = _pick_conversation_block(conn, user_id, hsk_level)
        if conv_block:
            blocks.append(conv_block)
            micro_plan += " · 1 conversation"
    elif listening_block:
        # Listening block: drills first, then listening comprehension
        blocks = [DrillBlock(items=drills, target_seconds=drill_seconds)]
        blocks.append(listening_block)
        micro_plan += " · 1 listening"

        conv_block = _pick_conversation_block(conn, user_id, hsk_level)
        if conv_block:
            blocks.append(conv_block)
            micro_plan += " · 1 conversation"
    else:
        # No reading or listening available — drills only (+ conversation if eligible)
        blocks = [DrillBlock(items=drills, target_seconds=drill_seconds)]
        remaining = max(0, params.get("target_items", 12) * SECONDS_PER_DRILL - drill_seconds)
        if remaining >= 120 or drill_seconds >= 180:
            conv_block = _pick_conversation_block(conn, user_id, hsk_level)
            if conv_block:
                blocks.append(conv_block)
                micro_plan += " · 1 conversation"

    total_seconds = sum(
        getattr(b, "target_seconds", 0) for b in blocks
    )

    plan = SessionPlan(
        session_type="standard",
        blocks=blocks,
        micro_plan=micro_plan,
        estimated_seconds=total_seconds,
        days_since_last=days_gap,
        gap_message=get_gap_message(days_gap) if days_gap else None,
        day_label=day_profile["name"],
        focus_insights=focus_insights,
        experiment_variant=params.get("experiment_variant"),
    )
    plan._mapping_groups_used = ",".join(chosen_groups)
    return _validate_plan(plan)


def _scaffold_first_session(drills: list) -> list:
    """Reorder drills for a user's very first session: recognition-first.

    Moves easy recognition drills (MC, reverse MC, tone discrimination,
    listening gist, measure word) to the front so the user builds confidence
    before encountering production drills (typing, speaking, free-text).
    """
    RECOGNITION_TYPES = {"mc", "reverse_mc", "tone", "listening_gist", "measure_word", "measure_word_disc", "number_system", "radical", "chengyu"}
    recognition = [d for d in drills if d.drill_type in RECOGNITION_TYPES]
    production = [d for d in drills if d.drill_type not in RECOGNITION_TYPES]
    # Put recognition first, then production
    return recognition + production


def _apply_peak_end_ordering(drills: list[DrillItem], conn: sqlite3.Connection, user_id: int = 1) -> list[DrillItem]:
    """Reorder drills so the session ends on a high note (Kahneman peak-end rule).

    Memory of an experience is dominated by its peak moment and its ending.
    This moves 2 high-confidence items to the end of the drill list so the
    learner finishes with items they're likely to get correct.

    High-confidence = mastery_stage >= 'stable' or streak >= 3 consecutive correct.
    Only rearranges if there are 6+ drills (small sessions stay as-is).
    """
    if len(drills) < 6:
        return drills

    try:
        # Get mastery data for items in this session
        item_ids = [d.content_item_id for d in drills]
        placeholders = ",".join("?" * len(item_ids))
        rows = conn.execute(
            """SELECT content_item_id, mastery_stage, streak
                FROM progress
                WHERE user_id = ? AND content_item_id IN ({placeholders})""".format(placeholders=placeholders),
            [user_id] + item_ids,
        ).fetchall()

        mastery = {r["content_item_id"]: r for r in rows}

        # Find high-confidence drills (stable/durable OR streak >= 3)
        high_conf_indices = []
        for i, d in enumerate(drills):
            m = mastery.get(d.content_item_id)
            if m and (
                m["mastery_stage"] in ("stable", "durable")
                or (m["streak"] or 0) >= 3
            ):
                high_conf_indices.append(i)

        if len(high_conf_indices) < 2:
            return drills

        # Move 2 high-confidence items to the last 2 positions
        # Pick from the middle of the session (not already at the end)
        end_candidates = [
            i for i in high_conf_indices
            if i < len(drills) - 2
        ]
        if len(end_candidates) < 2:
            return drills

        # Take the first 2 candidates (closest to middle)
        mid = len(drills) // 2
        end_candidates.sort(key=lambda i: abs(i - mid))
        to_move = end_candidates[:2]

        # Rebuild: everything except the 2 chosen, then append them at end
        remaining = [d for i, d in enumerate(drills) if i not in to_move]
        peak_end = [drills[i] for i in to_move]
        return remaining + peak_end

    except Exception as e:
        logger.debug("peak-end ordering skipped: %s", e)
        return drills


def preview_next_session(conn: sqlite3.Connection, user_id: int = 1, n: int = 3) -> list[dict]:
    """Preview the top N items that would appear in the next session.

    Used for Zeigarnik effect — showing upcoming words at session end
    creates anticipation to return. Returns a list of dicts with hanzi,
    pinyin, english, and is_new flag.
    """
    try:
        # Get items due for review with highest urgency
        rows = conn.execute(
            """SELECT ci.id, ci.hanzi, ci.pinyin, ci.english,
                      p.mastery_stage, p.next_review
               FROM progress p
               JOIN content_item ci ON p.content_item_id = ci.id
               WHERE p.user_id = ?
                 AND p.mastery_stage NOT IN ('durable')
                 AND p.next_review IS NOT NULL
               ORDER BY p.next_review ASC
               LIMIT ?""",
            (user_id, n + 5),  # Fetch extra to filter
        ).fetchall()

        preview = []
        for r in rows:
            if len(preview) >= n:
                break
            preview.append({
                "hanzi": r["hanzi"],
                "pinyin": r["pinyin"],
                "english": r["english"],
                "is_new": r["mastery_stage"] == "seen",
            })

        # If not enough review items, check for new items
        if len(preview) < n:
            new_rows = conn.execute(
                """SELECT ci.id, ci.hanzi, ci.pinyin, ci.english
                   FROM content_item ci
                   WHERE ci.id NOT IN (
                       SELECT content_item_id FROM progress WHERE user_id = ?
                   )
                   ORDER BY ci.hsk_level, ci.frequency_rank
                   LIMIT ?""",
                (user_id, n - len(preview)),
            ).fetchall()
            for r in new_rows:
                preview.append({
                    "hanzi": r["hanzi"],
                    "pinyin": r["pinyin"],
                    "english": r["english"],
                    "is_new": True,
                })

        return preview[:n]

    except Exception as e:
        logger.debug("next session preview failed: %s", e)
        return []


def plan_standard_session(conn: sqlite3.Connection, target_items: int | None = None, user_id: int = 1) -> SessionPlan:
    """Plan a standard session with interleaved modalities, day-of-week aware."""
    random.seed(_session_seed(conn, user_id=user_id))

    params = _plan_session_params(conn, target_items, user_id)
    is_long_gap = params["is_long_gap"]

    drills = []
    seen_ids = set()

    # Error focus + contrastive + encounter boost + grammar boost (skipped during long gaps)
    if not is_long_gap:
        error_drills = _plan_error_focus_items(conn, seen_ids, user_id)
        drills.extend(error_drills)
        contrastive_drills = _plan_contrastive_drills(conn, seen_ids, user_id)
        drills.extend(contrastive_drills)
        params["target_items"] = max(MIN_SESSION_ITEMS,
                                     params["target_items"] - len(error_drills) - len(contrastive_drills))
        _plan_encounter_boost_items(conn, seen_ids, params["target_items"], drills, user_id)
        _plan_reading_struggle_boost(conn, seen_ids, params["target_items"], drills, user_id)
        _plan_grammar_boost_items(conn, seen_ids, params["target_items"], drills, user_id)
        _plan_cross_modality_boost_items(conn, seen_ids, params["target_items"], drills, user_id)

    # Fill modality drills (due items + new items)
    params["new_budget"] = _plan_modality_drills(conn, params, drills, seen_ids, user_id)

    # Inject supplementary drills (core lexicon, scenarios, personalization, media)
    if not is_long_gap:
        _plan_injections(conn, drills, seen_ids, user_id)

    # Inject minimal pair drills for high-interference items (~30% probability each)
    if not is_long_gap:
        _plan_minimal_pair_drills(conn, drills, seen_ids, user_id)

    # Inject holdout probes (anti-Goodhart Rule 4: hidden benchmark tasks)
    if not is_long_gap:
        _plan_holdout_probes(conn, drills, seen_ids, user_id)

    # Inject delayed recall validations (anti-Goodhart Layer 2: integrity checks)
    if not is_long_gap:
        _plan_delayed_validations(conn, drills, seen_ids, user_id)

    # Hard cap: trim to 120% of target to prevent injection bloat
    cap = max(MIN_SESSION_ITEMS, int(params["target_items"] * 1.2))
    if len(drills) > cap:
        drills = drills[:cap]

    # First-session scaffolding: recognition drills first for brand-new users
    profile = db.get_profile(conn, user_id=user_id)
    if (profile.get("total_sessions") or 0) == 0:
        drills = _scaffold_first_session(drills)

    return _build_session_plan(drills, params, conn, user_id)


def plan_minimal_session(conn: sqlite3.Connection, user_id: int = 1) -> SessionPlan:
    """Plan a 90-second minimal session. Always runnable."""
    random.seed(_session_seed(conn, user_id=user_id))
    drills = []
    seen_ids = set()

    # 3 IME recognition tasks (high-frequency, familiar)
    ime_items = db.get_items_due(conn, "ime", limit=10, user_id=user_id)
    ime_items.sort(key=lambda x: x.get("total_attempts") or 0, reverse=True)
    ime_added = 0
    for item in ime_items:
        if ime_added >= 3:
            break
        if item["id"] in seen_ids or not _item_is_drillable(item, "ime_type"):
            continue
        seen_ids.add(item["id"])
        drills.append(DrillItem(
            content_item_id=item["id"], hanzi=item["hanzi"],
            pinyin=item["pinyin"], english=item["english"],
            modality="ime", drill_type="ime_type",
            is_confidence_win=True,
        ))
        ime_added += 1

    if ime_added < 3:
        new_ime = db.get_new_items(conn, "ime", limit=5, user_id=user_id)
        for item in new_ime:
            if ime_added >= 3:
                break
            if item["id"] in seen_ids or not _item_is_drillable(item, "ime_type"):
                continue
            seen_ids.add(item["id"])
            drills.append(DrillItem(
                content_item_id=item["id"], hanzi=item["hanzi"],
                pinyin=item["pinyin"], english=item["english"],
                modality="ime", drill_type="ime_type",
            ))
            ime_added += 1

    # 1 listening gist
    listen_items = db.get_items_due(conn, "listening", limit=5, user_id=user_id)
    for item in listen_items:
        if item["id"] in seen_ids or not _item_is_drillable(item, "listening_gist"):
            continue
        seen_ids.add(item["id"])
        drills.append(DrillItem(
            content_item_id=item["id"], hanzi=item["hanzi"],
            pinyin=item["pinyin"], english=item["english"],
            modality="listening", drill_type="listening_gist",
        ))
        break

    # 1 tone discrimination
    tone_items = db.get_items_due(conn, "reading", limit=10, user_id=user_id)
    for item in tone_items:
        if item["id"] in seen_ids or not _item_is_drillable(item, "tone"):
            continue
        seen_ids.add(item["id"])
        drills.append(DrillItem(
            content_item_id=item["id"], hanzi=item["hanzi"],
            pinyin=item["pinyin"], english=item["english"],
            modality="reading", drill_type="tone",
        ))
        break

    days_gap = db.get_days_since_last_session(conn, user_id=user_id)

    return _validate_plan(SessionPlan(
        session_type="minimal",
        drills=drills,
        micro_plan=f"Quick session: {len(drills)} items, ~90 seconds",
        estimated_seconds=90,
        days_since_last=days_gap,
        gap_message=get_gap_message(days_gap) if days_gap else None,
    ))


def plan_catchup_session(conn: sqlite3.Connection, user_id: int = 1) -> SessionPlan:
    """Plan a core catch-up session (≥70% core material, contextualized).

    Triggered when low-affinity domains are lagging.
    """
    random.seed(_session_seed(conn, user_id=user_id))
    drills = []
    variety_tracker = {}
    seen_ids = set()

    # Get items with highest error rates
    problem_items = conn.execute("""
        SELECT ci.*, p.total_attempts, p.total_correct,
               CASE WHEN p.total_attempts > 0
                    THEN CAST(p.total_correct AS REAL) / p.total_attempts
                    ELSE 0.5 END as accuracy
        FROM content_item ci
        JOIN progress p ON ci.id = p.content_item_id
        WHERE p.total_attempts >= 2 AND p.total_correct < p.total_attempts
          AND p.user_id = ?
          AND ci.review_status = 'approved'
        ORDER BY accuracy ASC
        LIMIT 15
    """, (user_id,)).fetchall()

    for item in problem_items:
        if len(drills) >= 8:
            break
        item = dict(item)
        if item["id"] in seen_ids:
            continue
        modality = "ime" if random.random() < 0.4 else "reading"
        mastery_stage = item.get("mastery_stage") or "seen"
        drill_type = _pick_drill_type(modality, item, variety_tracker,
                                      mastery_stage=mastery_stage,
                                      conn=conn)
        if not _item_is_drillable(item, drill_type):
            continue
        seen_ids.add(item["id"])
        drills.append(DrillItem(
            content_item_id=item["id"], hanzi=item["hanzi"],
            pinyin=item["pinyin"], english=item["english"],
            modality=modality, drill_type=drill_type,
        ))

    # Add a few confidence wins
    easy_items = db.get_items_due(conn, "reading", limit=10, user_id=user_id)
    easy_items.sort(key=lambda x: x.get("streak_correct") or 0, reverse=True)
    for item in easy_items[:6]:
        if item["id"] in seen_ids:
            continue
        if not _item_is_drillable(item, "mc"):
            continue
        seen_ids.add(item["id"])
        drills.append(DrillItem(
            content_item_id=item["id"], hanzi=item["hanzi"],
            pinyin=item["pinyin"], english=item["english"],
            modality="reading", drill_type="mc",
            is_confidence_win=True,
        ))
        if len(drills) >= 12:
            break

    drills = _interleave(drills)
    days_gap = db.get_days_since_last_session(conn, user_id=user_id)

    return _validate_plan(SessionPlan(
        session_type="catchup",
        drills=drills,
        micro_plan=f"Catch-up: {len(drills)} items focused on weak spots",
        estimated_seconds=len(drills) * SECONDS_PER_DRILL,
        days_since_last=days_gap,
        gap_message=get_gap_message(days_gap) if days_gap else None,
    ))


def plan_speaking_session(conn: sqlite3.Connection, user_id: int = 1) -> SessionPlan:
    """Plan a speaking practice session — all speaking drills."""
    drills = []
    seen_ids = set()

    # Pick items that have pinyin (needed for tone grading)
    items = conn.execute("""
        SELECT ci.* FROM content_item ci
        WHERE ci.status = 'drill_ready'
          AND ci.review_status = 'approved'
          AND ci.pinyin IS NOT NULL AND ci.pinyin != ''
        ORDER BY RANDOM()
        LIMIT 8
    """).fetchall()

    for item in items:
        item = dict(item)
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])
        drills.append(DrillItem(
            content_item_id=item["id"], hanzi=item["hanzi"],
            pinyin=item["pinyin"], english=item["english"],
            modality="speaking", drill_type="speaking",
        ))

    return _validate_plan(SessionPlan(
        session_type="speaking",
        drills=drills,
        micro_plan=f"Speaking practice: {len(drills)} items, record & grade tones",
        estimated_seconds=len(drills) * 20,
    ))


_VALID_MODALITIES = {"reading", "listening", "speaking", "ime"}

# Derive valid drill types from the canonical registry + dialogue (scenario-based)
from .drills import DRILL_REGISTRY
_VALID_DRILL_TYPES = set(DRILL_REGISTRY.keys()) | {"dialogue", "media_comprehension"}


def _pick_reading_block(conn, user_id: int, hsk_level: int) -> ReadingBlock | None:
    """Pick a reading passage using vocabulary coverage (Krashen's i+1).

    Target: user knows 85-95% of unique characters in the passage.
    Falls back to HSK ceiling matching if coverage scoring isn't possible.
    """
    if hsk_level < 3:
        return None
    try:
        # Get candidate passages not completed recently
        candidates = conn.execute("""
            SELECT rt.id, rt.title, rt.content_hanzi, rt.content_pinyin,
                   rt.hsk_ceiling, rt.word_count
            FROM reading_texts rt
            LEFT JOIN reading_progress rp
                ON rt.id = rp.passage_id AND rp.user_id = ?
            WHERE rt.hsk_ceiling <= ? + 1
            AND (rp.id IS NULL OR rp.completed_at < datetime('now', '-7 days'))
            ORDER BY RANDOM() LIMIT 10
        """, (user_id, hsk_level)).fetchall()
        if not candidates:
            return None

        # Build the user's known character set efficiently (single query)
        known_chars = set()
        try:
            known_rows = conn.execute("""
                SELECT DISTINCT ci.hanzi
                FROM progress p
                JOIN content_item ci ON p.content_item_id = ci.id
                WHERE p.user_id = ?
                  AND (p.retention >= 0.7
                       OR p.last_review_date >= date('now', '-30 days'))
                  AND LENGTH(ci.hanzi) = 1
            """, (user_id,)).fetchall()
            # Filter to CJK characters in Python (more reliable than SQLite GLOB)
            known_chars = {r["hanzi"] for r in known_rows
                           if re.match(r'[\u4e00-\u9fff\u3400-\u4dbf]', r["hanzi"])}
        except Exception:
            pass

        # Score each candidate by vocabulary coverage (Nation 2006)
        # Prefer word-level (jieba) coverage; fall back to character-level
        best_row = None
        best_score = -1.0
        _vocab_profile_fn = None
        try:
            from mandarin.ai.reading_content import compute_vocabulary_profile
            _vocab_profile_fn = compute_vocabulary_profile
        except ImportError:
            pass

        for row in candidates:
            text = row["content_hanzi"] or ""
            if not text:
                continue

            # Word-level coverage via Nation's vocabulary profile
            if _vocab_profile_fn and known_chars:
                profile = _vocab_profile_fn(text, known_chars)
                coverage = profile["token_coverage"]
                verdict = profile["verdict"]
                density = profile["new_word_density"]

                # Hard reject: too hard or too easy
                if verdict == "too_hard":
                    continue  # < 85% — even glossing won't save it
                if verdict == "too_easy" and len(candidates) > 3:
                    score = 0.2  # > 98% — nothing new to learn

                # Optimal: 90-95% with glossing (Nation's sweet spot)
                elif verdict == "optimal":
                    score = 2.0 - abs(coverage - 0.92) * 10  # peaks at 92%
                    # Bonus if density is within Nation's threshold (≤1 new word per 20 tokens)
                    if density <= 1.2:
                        score += 0.3
                elif verdict == "challenging":
                    score = 0.6  # 85-90% — harder but acceptable with glossing
                else:
                    score = 0.2
            elif known_chars:
                # Fallback: character-level coverage
                unique_chars = set(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
                if not unique_chars:
                    continue
                coverage = len(unique_chars & known_chars) / len(unique_chars)
                if 0.85 <= coverage <= 0.95:
                    score = 1.0 - abs(coverage - 0.90) * 10
                elif coverage > 0.95:
                    score = 0.3
                elif coverage >= 0.70:
                    score = 0.2
                else:
                    continue
            else:
                # No known chars — HSK ceiling proximity
                score = 0.9 if row["hsk_ceiling"] <= hsk_level else 0.5

            # Small random jitter
            score += random.random() * 0.1

            if score > best_score:
                best_score = score
                best_row = row

        if not best_row:
            # Fallback: just use the first candidate (HSK ceiling match)
            best_row = candidates[0]

        row = best_row

        # Load comprehension questions if stored
        import json as _json
        questions = []
        try:
            q_rows = conn.execute("""
                SELECT question_json FROM reading_comprehension_questions
                WHERE passage_id = ? ORDER BY question_order
            """, (row["id"],)).fetchall()
            for qr in q_rows:
                questions.append(_json.loads(qr["question_json"]))
        except Exception:
            pass

        return ReadingBlock(
            passage_id=row["id"],
            passage={
                "id": row["id"],
                "title": row["title"],
                "content_hanzi": row["content_hanzi"],
                "content_pinyin": row["content_pinyin"],
                "hsk_ceiling": row["hsk_ceiling"],
                "word_count": row["word_count"],
            },
            questions=questions,
            target_seconds=240,
        )
    except Exception:
        logger.debug("_pick_reading_block failed", exc_info=True)
        return None


def _pick_conversation_block(conn, user_id: int, hsk_level: int) -> ConversationBlock | None:
    """Pick a conversation scenario matching user's HSK level."""
    try:
        from .ai.conversation_drill import SCENARIOS
        level_key = min(hsk_level, max(SCENARIOS.keys())) if SCENARIOS else 1
        chosen_level = level_key
        available = SCENARIOS.get(level_key, [])
        if not available:
            # Try one level down
            for lvl in range(level_key - 1, 0, -1):
                available = SCENARIOS.get(lvl, [])
                if available:
                    chosen_level = lvl
                    break
        if not available:
            return None

        scenario = random.choice(available)
        return ConversationBlock(
            scenario_id=scenario.get("id", scenario.get("title", "")),
            scenario=scenario,
            max_turns=3,
            target_seconds=180,
            hsk_level=chosen_level,
        )
    except Exception:
        logger.debug("_pick_conversation_block failed", exc_info=True)
        return None


def _pick_listening_block(conn, user_id: int, hsk_level: int) -> ListeningBlock | None:
    """Pick a listening passage the user hasn't heard recently (HSK 2+).

    Reuses reading_texts passages but checks against listening_progress
    to avoid repeats. Generates an audio URL via the existing TTS endpoint
    and loads comprehension questions from reading_comprehension_questions.
    """
    if hsk_level < 2:
        return None
    try:
        row = conn.execute("""
            SELECT rt.id, rt.title, rt.content_hanzi, rt.content_pinyin,
                   rt.hsk_ceiling, rt.word_count
            FROM reading_texts rt
            LEFT JOIN listening_progress lp
                ON CAST(rt.id AS TEXT) = lp.passage_id AND lp.user_id = ?
            WHERE rt.hsk_ceiling <= ?
              AND rt.approved = 1
              AND (lp.id IS NULL OR lp.completed_at < datetime('now', '-7 days'))
            ORDER BY RANDOM() LIMIT 1
        """, (user_id, hsk_level)).fetchone()
        if not row:
            # Fallback: try without the approved filter
            row = conn.execute("""
                SELECT rt.id, rt.title, rt.content_hanzi, rt.content_pinyin,
                       rt.hsk_ceiling, rt.word_count
                FROM reading_texts rt
                LEFT JOIN listening_progress lp
                    ON CAST(rt.id AS TEXT) = lp.passage_id AND lp.user_id = ?
                WHERE rt.hsk_ceiling <= ?
                  AND (lp.id IS NULL OR lp.completed_at < datetime('now', '-7 days'))
                ORDER BY RANDOM() LIMIT 1
            """, (user_id, hsk_level)).fetchone()
        if not row:
            return None

        # Load comprehension questions
        import json as _json
        questions = []
        try:
            q_rows = conn.execute("""
                SELECT question_json FROM reading_comprehension_questions
                WHERE passage_id = ? ORDER BY question_order
            """, (row["id"],)).fetchall()
            for qr in q_rows:
                questions.append(_json.loads(qr["question_json"]))
        except Exception:
            pass

        from urllib.parse import quote
        audio_url = f"/api/tts?text={quote(row['content_hanzi'][:500])}"

        # Use learner's preferred playback speed (choice architecture)
        speed = 1.0
        try:
            profile = db.get_profile(conn, user_id=user_id)
            speed = float(profile.get("preferred_playback_speed") or 1.0)
            speed = max(0.5, min(2.0, speed))  # Clamp to safe range
        except Exception:
            pass

        return ListeningBlock(
            passage_id=row["id"],
            audio_url=audio_url,
            transcript_zh=row["content_hanzi"] or "",
            transcript_pinyin=row["content_pinyin"] or "",
            questions=questions,
            playback_speed=speed,
            target_seconds=180,
        )
    except Exception:
        logger.debug("_pick_listening_block failed", exc_info=True)
        return None


def _validate_plan(plan: SessionPlan) -> SessionPlan:
    """Validate invariants on a completed session plan. Returns the plan unchanged.

    Logs warnings and filters out invalid drills rather than crashing.
    """
    # Filter out drills with invalid modalities or drill types
    valid_drills = []
    for d in plan.drills:
        if d.modality not in _VALID_MODALITIES:
            logger.error("_validate_plan: dropping drill with invalid modality %r for %s",
                         d.modality, d.hanzi)
            continue
        if d.drill_type not in _VALID_DRILL_TYPES:
            logger.error("_validate_plan: dropping drill with invalid drill_type %r for %s",
                         d.drill_type, d.hanzi)
            continue
        valid_drills.append(d)
    plan.drills = valid_drills

    # Deduplicate content_item_ids (excluding dialogues, personalized items which use id=0,
    # and listen-produce pairs which intentionally reuse the source item's id)
    real_ids = [d.content_item_id for d in plan.drills
                if d.drill_type != "dialogue" and d.content_item_id != 0
                and not d.metadata.get("listen_produce_pair")]
    if len(real_ids) != len(set(real_ids)):
        dupes = {x for x in real_ids if real_ids.count(x) > 1}
        logger.warning("_validate_plan: duplicate item_ids in plan: %s — deduplicating", dupes)
        seen_ids = set()
        deduped = []
        for d in plan.drills:
            key = d.content_item_id
            if (d.drill_type == "dialogue" or key == 0
                    or d.metadata.get("listen_produce_pair")
                    or key not in dupes or key not in seen_ids):
                deduped.append(d)
                if key in dupes:
                    seen_ids.add(key)
        plan.drills = deduped

    # Session type validation
    valid_types = ("standard", "minimal", "catchup", "speaking")
    if plan.session_type not in valid_types:
        logger.error("_validate_plan: unknown session_type %r, defaulting to 'standard'",
                     plan.session_type)
        plan.session_type = "standard"

    return plan


def _interleave(drills: list[DrillItem]) -> list[DrillItem]:
    """Interleave drills with thematic micro-clustering and difficulty alternation.

    Phase 1: Group by HSK level into micro-clusters of 2-3 items.
    Phase 2: Interleave clusters (not individual items) for thematic coherence.
    Phase 3: Break same drill_type adjacencies (desirable difficulty).
    Phase 4: Difficulty interleaving (Rohrer & Taylor) — alternate easy/hard items.
    """
    if len(drills) <= 2:
        return drills

    # Phase 1: Group by HSK level for micro-clustering
    by_hsk = {}
    for d in drills:
        level = d.metadata.get("hsk_level", 0)
        by_hsk.setdefault(level, []).append(d)

    # Create clusters of 2-3 items from same HSK level
    clusters = []
    for level, items in by_hsk.items():
        random.shuffle(items)
        for i in range(0, len(items), 2):
            clusters.append(items[i:i + 2])
    random.shuffle(clusters)

    # Phase 2: Interleave clusters by modality
    # Flatten clusters while maintaining cluster order
    result = [d for cluster in clusters for d in cluster]

    # Phase 3: Break same drill_type adjacencies
    if len(result) > 2:
        for i in range(1, len(result) - 1):
            if result[i].drill_type == result[i - 1].drill_type:
                # Try swapping with a later drill of different type
                for j in range(i + 1, len(result)):
                    if result[j].drill_type != result[i - 1].drill_type:
                        result[i], result[j] = result[j], result[i]
                        break

    # Phase 4: Difficulty interleaving (Rohrer & Taylor 2007)
    # Alternate easy and hard items to maximize the interleaving effect.
    # Uses ML-predicted accuracy or item difficulty as the difficulty proxy.
    try:
        result = _difficulty_interleave(result)
    except Exception:
        pass  # Graceful degradation — keep Phase 3 ordering

    return result


def _difficulty_interleave(drills: list[DrillItem]) -> list[DrillItem]:
    """Reorder drills to alternate easy and hard items.

    Rohrer & Taylor (2007): interleaving different difficulty levels
    during practice improves long-term retention vs. blocked practice.

    Uses _ml_predicted_accuracy (if annotated) or item difficulty metadata
    as the difficulty proxy. Items without difficulty data stay in place.
    """
    if len(drills) <= 3:
        return drills

    def _difficulty_score(drill: DrillItem) -> float:
        """Lower score = harder item."""
        # Prefer ML prediction if available
        ml_acc = drill.metadata.get("_ml_predicted_accuracy")
        if ml_acc is not None:
            return ml_acc
        # Fall back to item difficulty (higher difficulty = harder = lower score)
        item_diff = drill.metadata.get("item_difficulty")
        if item_diff is not None:
            return 1.0 - min(1.0, item_diff)
        # Fall back to HSK level as rough proxy (higher HSK = harder)
        hsk = drill.metadata.get("hsk_level", 3)
        return max(0.0, 1.0 - hsk / 10.0)

    # Sort by difficulty score
    scored = sorted(drills, key=_difficulty_score)

    # Split into easy pile (top half) and hard pile (bottom half)
    mid = len(scored) // 2
    hard_pile = scored[:mid]       # low scores = hard
    easy_pile = scored[mid:]       # high scores = easy

    # Interleave: alternate easy, hard, easy, hard...
    interleaved = []
    ei, hi = 0, 0
    pick_easy = True
    while ei < len(easy_pile) or hi < len(hard_pile):
        if pick_easy and ei < len(easy_pile):
            interleaved.append(easy_pile[ei])
            ei += 1
        elif hi < len(hard_pile):
            interleaved.append(hard_pile[hi])
            hi += 1
        elif ei < len(easy_pile):
            interleaved.append(easy_pile[ei])
            ei += 1
        pick_easy = not pick_easy

    return interleaved
