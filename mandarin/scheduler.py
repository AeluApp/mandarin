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
        return {"name": "Light",
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
    "tone":           ["tone", "hanzi_to_pinyin", "english_to_pinyin"],
    "segment":        ["ime_type"],
    "ime_confusable": ["ime_type", "hanzi_to_pinyin"],
    "vocab":          ["mc", "reverse_mc"],
    "grammar":        ["intuition"],
    "other":          ["mc"],
}


@dataclass
class SessionPlan:
    """A complete session plan ready for the runner."""
    session_type: str           # 'standard', 'minimal', 'catchup'
    drills: List[DrillItem] = field(default_factory=list)
    micro_plan: str = ""        # One-line summary shown at start
    estimated_seconds: int = 0
    days_since_last: Optional[int] = None
    gap_message: Optional[str] = None
    day_label: Optional[str] = None  # Day-of-week profile name


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
        return base_weights

    total_attempts = sum(r["attempts"] for r in rows)
    if total_attempts < 20:
        return base_weights

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
        "tone": "speaking",
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
        pool = list(zip(all_groups, weights))
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

def _pick_drill_type(modality: str, item: dict, variety_tracker: dict[str, list[str]],
                     allowed_types: set[str] | None = None, mastery_stage: str = "seen") -> str:
    """Pick a drill type for a given modality, adding variety.

    If allowed_types is provided, prefer types in that set.
    Avoids repeating the same drill type too many times in a row.
    Uses mastery_stage for transfer scaffolding: recognition first,
    then production, then context/transfer drills.
    """
    drill_options = {
        "reading": ["mc", "reverse_mc", "tone", "intuition", "english_to_pinyin", "hanzi_to_pinyin", "pinyin_to_hanzi", "transfer", "measure_word", "word_order", "sentence_build", "particle_disc", "homophone", "translation", "cloze_context", "synonym_disc"],
        "ime": ["ime_type", "dictation_sentence"],
        "listening": ["listening_gist", "listening_detail", "listening_tone", "listening_dictation", "listening_passage"],
        "speaking": ["speaking", "mc"],  # speaking drill preferred; mc fallback
    }

    options = drill_options.get(modality, ["mc"])

    # Transfer scaffolding: bias drill type by mastery stage
    # Recognition first -> production -> context/transfer
    if mastery_stage in ("seen", "passed_once") and modality == "reading":
        # Prefer recognition drills for early-stage items
        recognition = [t for t in options if t in ("mc", "reverse_mc", "tone", "measure_word")]
        if recognition:
            options = recognition
    elif mastery_stage in ("stabilizing", "stable", "durable") and modality == "reading":
        # Prefer production/transfer drills for established items
        production = [t for t in options if t in ("transfer", "word_order", "sentence_build",
                      "translation", "english_to_pinyin", "hanzi_to_pinyin", "particle_disc",
                      "synonym_disc", "cloze_context")]
        if production:
            options = production

    # Filter by allowed_types if provided
    if allowed_types:
        filtered = [o for o in options if o in allowed_types]
        if filtered:
            options = filtered
        # If no intersection, fall back to unfiltered

    if len(options) == 1:
        return options[0]

    # Prefer types not recently used
    recent = variety_tracker.get(modality, [])
    for opt in options:
        if opt not in recent[-2:]:  # Not used in last 2 drills of this modality
            variety_tracker.setdefault(modality, []).append(opt)
            return opt

    # All recently used — pick randomly
    choice = random.choice(options)
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
        "quiet_observation": profile.get("lens_quiet_observation") or 0.5,
        "institutions": profile.get("lens_institutions") or 0.5,
        "urban_texture": profile.get("lens_urban_texture") or 0.5,
        "humane_mystery": profile.get("lens_humane_mystery") or 0.5,
        "identity": profile.get("lens_identity") or 0.5,
        "comedy": profile.get("lens_comedy") or 0.5,
        "food_social": profile.get("lens_food") or 0.5,
        "travel": profile.get("lens_travel") or 0.5,
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
        """, (lens,)).fetchone()

        total = row["total"] or 0
        seen = row["seen"] or 0
        if total > 0 and (seen / total) < 0.5:
            # Get unseen items from this lens
            if seen_ids:
                placeholders = ",".join("?" * len(seen_ids))
                unseen = conn.execute(f"""
                    SELECT * FROM content_item
                    WHERE content_lens = ? AND times_shown = 0
                      AND status = 'drill_ready' AND id NOT IN ({placeholders})
                    ORDER BY RANDOM() LIMIT ?
                """, (lens, *seen_ids, limit)).fetchall()
            else:
                unseen = conn.execute("""
                    SELECT * FROM content_item
                    WHERE content_lens = ? AND times_shown = 0
                      AND status = 'drill_ready'
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
    if not mastery:
        return NEW_BUDGET_DEFAULT

    max_level = max(mastery.keys())
    pct = mastery[max_level]["pct"]
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
    if not mastery:
        return 1  # Start with HSK 1

    max_allowed = 1
    for level in sorted(mastery.keys()):
        if mastery[level]["pct"] >= 80:
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
    day_profile = get_day_profile(conn, user_id=user_id)
    target_items = max(MIN_SESSION_ITEMS, round(target_items * day_profile["length_mult"]))

    days_gap = db.get_days_since_last_session(conn, user_id=user_id)
    is_long_gap = days_gap is not None and days_gap >= LONG_GAP_DAYS

    base_weights = GAP_WEIGHTS if is_long_gap else DEFAULT_WEIGHTS
    weights = _adjust_weights_for_errors(conn, base_weights, user_id=user_id) if not is_long_gap else base_weights

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

    bounce_levels = _get_hsk_bounce_levels(conn, user_id=user_id) if not is_long_gap else set()

    return {
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
    }


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


def _plan_encounter_boost_items(conn: sqlite3.Connection, seen_ids: set,
                                 target_items: int, drills: list, user_id: int) -> None:
    """Inject priority review items from recent reading/listening lookups."""
    try:
        encounter_items = conn.execute("""
            SELECT DISTINCT ve.content_item_id, ci.hanzi, ci.pinyin, ci.english,
                   ci.hsk_level, COUNT(*) as lookup_count
            FROM vocab_encounter ve
            JOIN content_item ci ON ve.content_item_id = ci.id
            WHERE ve.looked_up = 1
              AND ve.created_at >= datetime('now', '-7 days')
              AND ci.status = 'drill_ready'
              AND ve.user_id = ?
            GROUP BY ve.content_item_id
            ORDER BY lookup_count DESC
            LIMIT 4
        """, (user_id,)).fetchall()
        for ei in encounter_items:
            if ei["content_item_id"] in seen_ids:
                continue
            if len(drills) >= target_items:
                break
            seen_ids.add(ei["content_item_id"])
            drills.append(DrillItem(
                content_item_id=ei["content_item_id"],
                hanzi=ei["hanzi"],
                pinyin=ei["pinyin"],
                english=ei["english"],
                modality="reading",
                drill_type="mc",
                metadata={"encounter_boost": True, "lookup_count": ei["lookup_count"]},
            ))
    except (sqlite3.Error, KeyError, TypeError) as e:
        logger.debug("encounter boost skipped: %s", e)


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

        for i, item in enumerate(due_items):
            if _has_confusable(item.get("hanzi", "")):
                item["_confusable_boost"] = True

        if is_long_gap or is_consolidation:
            due_items.sort(key=lambda x: x.get("streak_correct") or 0, reverse=True)
        elif is_stretch:
            due_items.sort(key=lambda x: x.get("streak_correct") or 0)

        if is_consolidation:
            due_items = [i for i in due_items if (i.get("difficulty") or 0.5) <= 0.6] or due_items

        items_added = 0
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
                                              mastery_stage=mastery_stage)
            if not _item_is_drillable(item, drill_type):
                continue

            mastery_stage = item.get("mastery_stage") or "seen"
            scaffold_level = SCAFFOLD_LEVELS.get(mastery_stage, "none")

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
                    "hsk_level": item.get("hsk_level", 0),
                },
            )

            if confidence_wins_needed > 0 and (item.get("streak_correct") or 0) >= 2:
                drill.is_confidence_win = True
                confidence_wins_needed -= 1
            drills.append(drill)
            items_added += 1

        # Fill remaining with new items
        if items_added < count and not is_long_gap and new_budget > 0:
            new_limit = min(count - items_added, new_budget)
            hsk_max = _get_hsk_prerequisite_cap(conn, user_id=user_id)
            if is_stretch:
                mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
                if mastery:
                    hsk_max = max(hsk_max, max(mastery.keys()) + 1)
            new_items = db.get_new_items(conn, modality, limit=new_limit + 5, hsk_max=hsk_max, user_id=user_id)
            if bounce_levels:
                new_items = [i for i in new_items if i.get("hsk_level") not in bounce_levels] or new_items
            for item in new_items:
                if items_added >= count or new_budget <= 0:
                    break
                if item["id"] in seen_ids:
                    continue

                drill_type = _pick_drill_type(modality, item, variety_tracker,
                                              allowed_types=allowed_types,
                                              mastery_stage="seen")
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
                        metadata={"reason": "personalized", "domain": domain},
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


def _build_session_plan(drills: list, params: dict, conn: sqlite3.Connection, user_id: int) -> SessionPlan:
    """Finalize drills: interleave, build micro-plan, tier-gate, create SessionPlan."""
    drills = _interleave(drills)
    drills = _add_listen_produce_pairs(drills)

    # Build micro-plan
    modality_summary = {}
    new_count = sum(1 for d in drills if d.is_new)
    conv_count = sum(1 for d in drills if d.drill_type == "dialogue")
    media_count = sum(1 for d in drills if d.drill_type == "media_comprehension")
    for d in drills:
        if d.drill_type not in ("dialogue", "media_comprehension"):
            modality_summary[d.modality] = modality_summary.get(d.modality, 0) + 1

    parts = []
    if modality_summary.get("ime"):
        parts.append(f"{modality_summary['ime']} IME")
    if modality_summary.get("reading"):
        parts.append(f"{modality_summary['reading']} reading")
    if modality_summary.get("listening"):
        parts.append(f"{modality_summary['listening']} listening")
    if modality_summary.get("speaking"):
        parts.append(f"{modality_summary['speaking']} speaking")
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

    plan = SessionPlan(
        session_type="standard",
        drills=drills,
        micro_plan=micro_plan,
        estimated_seconds=len(drills) * SECONDS_PER_DRILL + conv_count * SECONDS_PER_CONVERSATION,
        days_since_last=days_gap,
        gap_message=get_gap_message(days_gap) if days_gap else None,
        day_label=day_profile["name"],
    )
    plan._mapping_groups_used = ",".join(chosen_groups)
    return _validate_plan(plan)


def plan_standard_session(conn: sqlite3.Connection, target_items: int | None = None, user_id: int = 1) -> SessionPlan:
    """Plan a standard session with interleaved modalities, day-of-week aware."""
    random.seed(_session_seed(conn, user_id=user_id))

    params = _plan_session_params(conn, target_items, user_id)
    is_long_gap = params["is_long_gap"]

    drills = []
    seen_ids = set()

    # Error focus + encounter boost (skipped during long gaps)
    if not is_long_gap:
        error_drills = _plan_error_focus_items(conn, seen_ids, user_id)
        drills.extend(error_drills)
        params["target_items"] = max(MIN_SESSION_ITEMS,
                                     params["target_items"] - len(error_drills))
        _plan_encounter_boost_items(conn, seen_ids, params["target_items"], drills, user_id)

    # Fill modality drills (due items + new items)
    params["new_budget"] = _plan_modality_drills(conn, params, drills, seen_ids, user_id)

    # Inject supplementary drills (core lexicon, scenarios, personalization, media)
    if not is_long_gap:
        _plan_injections(conn, drills, seen_ids, user_id)

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
                                      mastery_stage=mastery_stage)
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


def _validate_plan(plan: SessionPlan) -> SessionPlan:
    """Assert invariants on a completed session plan. Returns the plan unchanged.

    Raises AssertionError if invariants are violated — these indicate bugs
    in the scheduler, not user error.
    """
    # All drills have valid modalities
    for d in plan.drills:
        assert d.modality in _VALID_MODALITIES, \
            f"invalid modality {d.modality!r} in drill for {d.hanzi}"
        assert d.drill_type in _VALID_DRILL_TYPES, \
            f"invalid drill_type {d.drill_type!r} in drill for {d.hanzi}"

    # No duplicate content_item_ids (excluding dialogues, personalized items which use id=0,
    # and listen-produce pairs which intentionally reuse the source item's id)
    real_ids = [d.content_item_id for d in plan.drills
                if d.drill_type != "dialogue" and d.content_item_id != 0
                and not d.metadata.get("listen_produce_pair")]
    assert len(real_ids) == len(set(real_ids)), \
        f"duplicate item_ids in plan: {[x for x in real_ids if real_ids.count(x) > 1]}"

    # Session type is known
    assert plan.session_type in ("standard", "minimal", "catchup", "speaking"), \
        f"unknown session_type: {plan.session_type!r}"

    return plan


def _interleave(drills: list[DrillItem]) -> list[DrillItem]:
    """Interleave drills with thematic micro-clustering.

    Phase 1: Group by HSK level into micro-clusters of 2-3 items.
    Phase 2: Interleave clusters (not individual items) for thematic coherence.
    Phase 3: Break same drill_type adjacencies (desirable difficulty).
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

    return result
