"""Centralized SRS and scheduling constants.

All magic numbers live here. Import from this module instead of
scattering constants across retention.py, db/progress.py, scheduler.py.
"""

from datetime import date, timedelta


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of weekday in month/year (1-indexed)."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return date(year, month, 1 + offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of weekday in month/year."""
    # Start from the 5th, fall back to 4th if out of range
    for n in (5, 4):
        try:
            return _nth_weekday(year, month, weekday, n)
        except ValueError:
            continue
    return _nth_weekday(year, month, weekday, 4)


def is_us_holiday(d: date = None) -> bool:
    """Check if a date is a US federal holiday (observed).

    Fixed holidays observed on Friday if Saturday, Monday if Sunday.
    """
    if d is None:
        d = date.today()
    y = d.year

    # Fixed-date holidays with observed-date adjustment
    fixed = [
        date(y, 1, 1),    # New Year's Day
        date(y, 6, 19),   # Juneteenth
        date(y, 7, 4),    # Independence Day
        date(y, 11, 11),  # Veterans Day
        date(y, 12, 25),  # Christmas Day
    ]
    observed = set()
    for h in fixed:
        if h.weekday() == 5:    # Saturday → observed Friday
            observed.add(h - timedelta(days=1))
        elif h.weekday() == 6:  # Sunday → observed Monday
            observed.add(h + timedelta(days=1))
        else:
            observed.add(h)

    # Floating holidays
    floating = [
        _nth_weekday(y, 1, 0, 3),   # MLK Day: 3rd Monday in Jan
        _nth_weekday(y, 2, 0, 3),   # Presidents Day: 3rd Monday in Feb
        _last_weekday(y, 5, 0),     # Memorial Day: last Monday in May
        _nth_weekday(y, 9, 0, 1),   # Labor Day: 1st Monday in Sep
        _nth_weekday(y, 10, 0, 2),  # Columbus Day: 2nd Monday in Oct
        _nth_weekday(y, 11, 3, 4),  # Thanksgiving: 4th Thursday in Nov
    ]
    observed.update(floating)

    return d in observed

# ── Retention model (half-life regression) ──

RECALL_THRESHOLD = 0.85    # Review when recall drops below this
MIN_HALF_LIFE = 0.5        # Floor: 12 hours
MAX_HALF_LIFE = 365.0      # Ceiling: 1 year
INITIAL_HALF_LIFE = 1.0    # First encounter: 1 day

# ── SM-2 parameters ──

EASE_FLOOR = 1.3
EASE_CORRECT_BOOST = 0.1
EASE_WRONG_PENALTY = 0.2
EASE_NARROWED_PENALTY = 0.03
EASE_HALF_PENALTY = 0.05

INTERVAL_INITIAL = 1.0     # First correct: 1 day
INTERVAL_SECOND = 3.0      # Second correct: 3 days
INTERVAL_WRONG = 0.5       # Wrong answer: 0.5 days
INTERVAL_NARROWED_MULT = 0.6
INTERVAL_HALF_MULT = 0.5

# ── Interval cap ──

MAX_INTERVAL = MAX_HALF_LIFE  # Never schedule beyond max half-life

# ── Streak cap thresholds ──

STREAK_STABLE_THRESHOLD = 10
STREAK_STABLE_MULT = 1.3    # 30% further out
STREAK_EXTENDED_THRESHOLD = 15
STREAK_EXTENDED_MULT = 1.2   # Extended streak bonus (exclusive with STABLE_MULT)

# ── Mastery stage gates ──

# Promotion thresholds
PROMOTE_PASSED_ONCE_STREAK = 2
PROMOTE_STABILIZING_STREAK = 3
PROMOTE_STABILIZING_DAYS = 2
PROMOTE_STABLE_STREAK = 6
PROMOTE_STABLE_ATTEMPTS = 10
PROMOTE_STABLE_DRILL_TYPES = 2
PROMOTE_STABLE_DAYS = 3
PROMOTE_DURABLE_DAYS_STABLE = 30
PROMOTE_DURABLE_SUCCESSES = 5

# Production direction gate — require at least 1 correct production drill before stable
REQUIRE_PRODUCTION_FOR_STABLE = True

# Demotion thresholds
DEMOTE_STABLE_STREAK_INCORRECT = 3
DEMOTE_STABILIZING_STREAK_INCORRECT = 3
DEMOTE_WEAK_CYCLE_THRESHOLD = 3

# Recovery
RECOVERY_STREAK_CORRECT = 3

# ── Modality half-life multipliers: REMOVED ──
# Previously applied fixed multipliers (listening 0.75×, speaking 0.80×)
# to shrink half-lives for auditory modalities. Removed because:
# 1. The multipliers were unjustified (no empirical data cited)
# 2. The half-life update mechanism already captures modality differences
#    naturally: items drilled via listening that are forgotten faster will
#    accumulate shorter half-lives through the update_half_life() feedback loop
# 3. A fixed multiplier per modality, uniform across all items and learners,
#    is almost certainly wrong for any individual item

# ── Confusable pair scheduling boost ──
CONFUSABLE_BOOST_MULT = 1.3  # 30% priority boost for items with known confusables

# ── Difficulty update ──

DIFFICULTY_CORRECT_ALPHA = 0.05
DIFFICULTY_WRONG_BETA = 0.065  # β ≈ 1.3α: slight asymmetry near 85% recall target
DIFFICULTY_HALF_WRONG_PENALTY = 0.02

# ── Retention model tuning ──

LAG_CLAMP_MIN = 0.3          # Widen from 0.5 — preserve early-review signal
LAG_CLAMP_MAX = 4.0          # Widen from 2.0 — reward overdue correct recalls
PARTIAL_CONFIDENCE_DAMPEN = 0.5  # Deprecated — use CONFIDENCE_DAMPEN dict

# Per-confidence dampening factors for half-life/difficulty updates.
# Higher = more of the full update applied. Lower = signal treated as weaker.
# "full" is handled separately (always 1.0, no dampening).
CONFIDENCE_DAMPEN = {
    "half": 0.5,            # 50/50 guess: ~50% of full 4-option information
    "narrowed": 0.4,        # Got it from 2 choices: weaker signal than half
    "unknown": 0.15,        # Admitted zero retrieval: harsh dampening
    "narrowed_wrong": 0.15, # Failed even with 2 choices: harsh dampening
}

# ── Scheduling ──

DAY_PROFILES = {
    0: {"name": "Monday warmup",   "length_mult": 0.85, "new_mult": 0.5,  "mode": "consolidation"},
    1: {"name": "Standard",        "length_mult": 1.0,  "new_mult": 1.0,  "mode": "standard"},
    2: {"name": "Standard",        "length_mult": 1.0,  "new_mult": 1.0,  "mode": "standard"},
    3: {"name": "Standard",        "length_mult": 1.0,  "new_mult": 1.0,  "mode": "standard"},
    4: {"name": "Friday lighter",  "length_mult": 0.85, "new_mult": 0.75, "mode": "consolidation"},
    5: {"name": "Weekend deep",    "length_mult": 1.4,  "new_mult": 1.5,  "mode": "stretch"},
    6: {"name": "Weekend deep",    "length_mult": 1.3,  "new_mult": 1.5,  "mode": "stretch"},
}

DEFAULT_WEIGHTS = {
    "reading": 0.25,
    "ime": 0.25,
    "listening": 0.35,
    "speaking": 0.15,
}

GAP_WEIGHTS = {
    "reading": 0.25,
    "ime": 0.30,
    "listening": 0.30,
    "speaking": 0.15,
}

# ── Gradient scaffolding (Vygotsky ZPD fading) ──

SCAFFOLD_LEVELS = {
    "seen":        {"pinyin": "full_pinyin", "english": "full"},
    "passed_once": {"pinyin": "tone_marks",  "english": "full"},
    "stabilizing": {"pinyin": "initial",     "english": "feedback_only"},
    "stable":      {"pinyin": "none",        "english": "none"},
    "durable":     {"pinyin": "none",        "english": "none"},
    "decayed":     {"pinyin": "tone_marks",  "english": "feedback_only"},
}

SCAFFOLD_ORDER = ["none", "initial", "tone_marks", "full_pinyin"]
ENGLISH_ORDER = ["none", "feedback_only", "full"]

# ── Time-of-day penalty ──

TOD_MIN_SESSIONS = 3             # Need at least this many sessions to compute penalty
TOD_LOW_ACCURACY_THRESHOLD = 0.6 # Accuracy below this triggers a penalty
TOD_LOW_ACCURACY_PENALTY = 0.75  # Reduce new items to 75% when accuracy is low

# ── Modality mixing ──

MISSING_MODALITY_NEED = 0.8      # Default need score for unseen modalities
MAX_DATA_MIX = 0.5               # Max blend of data-driven vs base weights
MIX_MIN_ATTEMPTS = 20            # Pure base weights below this
MIX_RAMP_RANGE = 360             # Attempts over which mix ramps from 0 → MAX_DATA_MIX
MAX_ERROR_BOOST = 0.15           # Max modality weight boost from errors
ERROR_BOOST_FACTOR = 0.20        # Error boost scaling factor

# ── Bounce detection ──

BOUNCE_ERROR_RATE = 0.4          # Error rate threshold to flag a struggling level
BOUNCE_MIN_ERRORS = 3            # Minimum errors required to trigger bounce

# ── Adaptive day profile ──

ADAPTIVE_MIN_SESSIONS = 10      # Min sessions in last 60 days for adaptive profile
ADAPTIVE_MIN_WEEKS = 2          # Min distinct weeks for adaptive profile
ADAPTIVE_LOOKBACK_DAYS = 60     # Days to look back for adaptive day profile
ADAPTIVE_SKIP_RATE = 0.6        # Skip rate above this → gentle mode
ADAPTIVE_EXIT_RATE = 0.4        # Early exit rate above this → light mode
ADAPTIVE_LOW_COMPLETION = 0.6   # Completion rate below this → light mode
ADAPTIVE_HIGH_ACCURACY = 0.85   # Accuracy above this (with high completion) → stretch
ADAPTIVE_HIGH_COMPLETION = 0.9  # Completion rate above this (with high accuracy) → stretch

# ── Register gate ──

REGISTER_GATE_MIN_ATTEMPTS = 10   # Min intuition attempts before unlocking professional register
REGISTER_GATE_MIN_ACCURACY = 0.6  # Min intuition accuracy to unlock professional register

# ── New item budget ──

NEW_BUDGET_LOW_MASTERY = 30       # Mastery pct below this → 1 new item per session
NEW_BUDGET_MED_MASTERY = 60       # Mastery pct below this → 2 new items per session
NEW_BUDGET_DEFAULT = 3            # Default new items when mastery is above medium

# ── Long gap ──

LONG_GAP_DAYS = 7                 # Days gap threshold for long-gap session behavior

# ── Tone accuracy boost ──

TONE_BOOST_MIN_RECORDINGS = 5     # Min recordings needed before boosting speaking weight
TONE_BOOST_ACCURACY_THRESHOLD = 0.6  # Below this → boost speaking weight
TONE_BOOST_MULTIPLIER = 1.5       # How much to multiply speaking weight
TONE_BOOST_MAX_WEIGHT = 0.35      # Max speaking weight after boost

# ── Error focus ──

ERROR_FOCUS_LIMIT = 3             # Max error-focus items per session

# ── Confusable pair routing ──

CONFUSABLE_ROUTE_PROBABILITY = 0.3  # Probability of routing confusable to homophone drill

# ── Session size ──

MIN_SESSION_ITEMS = 4             # Minimum drills in a session after adjustments

# ── Interleaving ──

MAPPING_GROUPS_PER_SESSION = 3    # Number of mapping groups to pick per session
INTERLEAVE_EXCLUDE_WEIGHT = 0.2   # Fallback weight for groups used last session.
# Adaptive interleave weight thresholds — maps novel-vs-repeated accuracy diff to weight.
# Positive diff = novel groups performed better (deprioritize repeats).
# Negative diff = repeated groups performed better (allow more repetition).
INTERLEAVE_STRONG_NOVEL_DIFF = 0.1    # diff > this → strong deprioritization
INTERLEAVE_MILD_NOVEL_DIFF = 0.05     # diff > this → mild deprioritization
INTERLEAVE_STRONG_REPEAT_DIFF = -0.1  # diff < this → strong repeat preference
INTERLEAVE_MILD_REPEAT_DIFF = -0.05   # diff < this → mild repeat preference
INTERLEAVE_WEIGHT_STRONG_NOVEL = 0.1  # Weight when novel is much better
INTERLEAVE_WEIGHT_MILD_NOVEL = 0.15   # Weight when novel is slightly better
INTERLEAVE_WEIGHT_STRONG_REPEAT = 0.4 # Weight when repeated is much better
INTERLEAVE_WEIGHT_MILD_REPEAT = 0.3   # Weight when repeated is slightly better
INTERLEAVE_WEIGHT_NEUTRAL = 0.25      # Weight when roughly equal
INTERLEAVE_WEIGHT_FLOOR = 0.05        # Minimum interleave weight
INTERLEAVE_WEIGHT_CEILING = 0.5       # Maximum interleave weight
# Used when insufficient data for adaptive computation (<6 sessions with groups).
# Scheduler auto-tunes this from session data: compares accuracy on sessions where
# groups were repeated vs. novel, adjusts weight in [0.05, 0.5] accordingly.

# ── Session planning ──

MAX_NEW_ITEM_RATIO = 0.25       # New items ≤ 25% of session (working memory limit)
MIN_NEW_ITEMS = 2               # Always allow at least this many new items
CONFIDENCE_WINS_NEEDED = 2      # Correct answers needed before moving on
SECONDS_PER_DRILL = 35          # Estimated time per drill item
SECONDS_PER_CONVERSATION = 60  # Estimated time per dialogue scenario
SESSION_PLAN_REDUCTION_FACTOR = 0.60  # Reduce planned items to 60% — matches observed completion rate

# ── Session time cap (hyperfocus guard) ──

SESSION_TIME_CAP_SECONDS = 600  # 10 minutes; auto-finish after this

# ── Adaptive session length ──

ADAPTIVE_LENGTH_MIN_SESSIONS = 2      # Min recent sessions needed for adaptive adjustment
ADAPTIVE_LENGTH_RECENT_SESSIONS = 5   # Number of recent sessions to analyze
ADAPTIVE_LENGTH_LOW_COMPLETION = 0.6  # Avg completion below this → shrink session
ADAPTIVE_LENGTH_SHRINK_FACTOR = 0.6   # Multiply base length by this when shrinking
ADAPTIVE_LENGTH_MIN_ITEMS = 4         # Floor for shrunken session length
ADAPTIVE_LENGTH_HIGH_COMPLETION = 0.95  # Avg completion above this → grow session
ADAPTIVE_LENGTH_HIGH_MIN_SESSIONS = 5   # Need this many sessions for growth
ADAPTIVE_LENGTH_GROW_FACTOR = 1.1     # Multiply base length by this when growing

# ── Encounter → drill boost ──

ENCOUNTER_BOOST_RATIO = 0.40          # Up to 40% of session for encounter items
ENCOUNTER_PRIORITY_WINDOW_DAYS = 7    # Priority window: drill within 7 days of lookup
ENCOUNTER_FULL_WINDOW_DAYS = 30       # Full eligibility window for encounter items

# ── Cross-modality boost ──

CROSS_MODALITY_BOOST_LIMIT = 3        # Max items per session to close modality gaps

# ── Tone sandhi boost ──

TONE_SANDHI_BOOST_WEIGHT = 2.5        # Multiplier for tone_sandhi drill selection probability


# ── Parameter registry declarations ──
# Register tunable constants with the intelligence engine's parameter graph.
# These are used by the influence model to learn which parameters affect which metrics.

def _register_all_parameters():
    """Register all tunable parameters. Called at import time."""
    from .intelligence.parameter_registry import _PARAMETER_REGISTRY_PENDING
    _p = _PARAMETER_REGISTRY_PENDING.append

    # Retention model
    _p({"parameter_name": "RECALL_THRESHOLD", "file_path": "mandarin/config.py",
        "current_value": RECALL_THRESHOLD, "current_value_str": str(RECALL_THRESHOLD),
        "value_type": "ratio", "primary_dimension": "retention",
        "secondary_dimensions": "[]", "min_valid": 0.5, "max_valid": 0.99,
        "soft_min": 0.75, "soft_max": 0.95, "change_direction": "either",
        "notes": "Review when recall drops below this"})

    _p({"parameter_name": "INITIAL_HALF_LIFE", "file_path": "mandarin/config.py",
        "current_value": INITIAL_HALF_LIFE, "current_value_str": str(INITIAL_HALF_LIFE),
        "value_type": "float", "primary_dimension": "retention",
        "secondary_dimensions": "[]", "min_valid": 0.1, "max_valid": 7.0,
        "soft_min": 0.5, "soft_max": 3.0, "change_direction": "either",
        "notes": "Half-life for first encounter (days)"})

    # SM-2 intervals
    _p({"parameter_name": "INTERVAL_INITIAL", "file_path": "mandarin/config.py",
        "current_value": INTERVAL_INITIAL, "current_value_str": str(INTERVAL_INITIAL),
        "value_type": "float", "primary_dimension": "srs_funnel",
        "secondary_dimensions": '["retention"]', "min_valid": 0.25, "max_valid": 7.0,
        "soft_min": 0.5, "soft_max": 3.0, "change_direction": "either",
        "notes": "First correct answer interval (days)"})

    _p({"parameter_name": "INTERVAL_SECOND", "file_path": "mandarin/config.py",
        "current_value": INTERVAL_SECOND, "current_value_str": str(INTERVAL_SECOND),
        "value_type": "float", "primary_dimension": "srs_funnel",
        "secondary_dimensions": '["retention"]', "min_valid": 1.0, "max_valid": 14.0,
        "soft_min": 2.0, "soft_max": 7.0, "change_direction": "either",
        "notes": "Second correct answer interval (days)"})

    # Ease
    _p({"parameter_name": "EASE_FLOOR", "file_path": "mandarin/config.py",
        "current_value": EASE_FLOOR, "current_value_str": str(EASE_FLOOR),
        "value_type": "float", "primary_dimension": "srs_funnel",
        "secondary_dimensions": "[]", "min_valid": 1.0, "max_valid": 2.5,
        "soft_min": 1.1, "soft_max": 1.5, "change_direction": "either",
        "notes": "Minimum ease factor"})

    # Mastery stage promotion
    _p({"parameter_name": "PROMOTE_STABILIZING_STREAK", "file_path": "mandarin/config.py",
        "current_value": PROMOTE_STABILIZING_STREAK, "current_value_str": str(PROMOTE_STABILIZING_STREAK),
        "value_type": "int", "primary_dimension": "srs_funnel",
        "secondary_dimensions": "[]", "min_valid": 1, "max_valid": 10,
        "soft_min": 2, "soft_max": 5, "change_direction": "either",
        "notes": "Correct streak to promote to stabilizing"})

    _p({"parameter_name": "PROMOTE_STABLE_STREAK", "file_path": "mandarin/config.py",
        "current_value": PROMOTE_STABLE_STREAK, "current_value_str": str(PROMOTE_STABLE_STREAK),
        "value_type": "int", "primary_dimension": "srs_funnel",
        "secondary_dimensions": "[]", "min_valid": 2, "max_valid": 15,
        "soft_min": 4, "soft_max": 10, "change_direction": "either",
        "notes": "Correct streak to promote to stable"})

    # Demotion
    _p({"parameter_name": "DEMOTE_WEAK_CYCLE_THRESHOLD", "file_path": "mandarin/config.py",
        "current_value": DEMOTE_WEAK_CYCLE_THRESHOLD, "current_value_str": str(DEMOTE_WEAK_CYCLE_THRESHOLD),
        "value_type": "int", "primary_dimension": "srs_funnel",
        "secondary_dimensions": '["frustration"]', "min_valid": 1, "max_valid": 10,
        "soft_min": 2, "soft_max": 5, "change_direction": "either",
        "notes": "Weak cycles before demotion"})

    # Difficulty
    _p({"parameter_name": "DIFFICULTY_CORRECT_ALPHA", "file_path": "mandarin/config.py",
        "current_value": DIFFICULTY_CORRECT_ALPHA, "current_value_str": str(DIFFICULTY_CORRECT_ALPHA),
        "value_type": "float", "primary_dimension": "drill_quality",
        "secondary_dimensions": "[]", "min_valid": 0.01, "max_valid": 0.2,
        "soft_min": 0.03, "soft_max": 0.1, "change_direction": "either",
        "notes": "Difficulty decrease rate on correct answer"})

    _p({"parameter_name": "DIFFICULTY_WRONG_BETA", "file_path": "mandarin/config.py",
        "current_value": DIFFICULTY_WRONG_BETA, "current_value_str": str(DIFFICULTY_WRONG_BETA),
        "value_type": "float", "primary_dimension": "drill_quality",
        "secondary_dimensions": "[]", "min_valid": 0.01, "max_valid": 0.2,
        "soft_min": 0.04, "soft_max": 0.12, "change_direction": "either",
        "notes": "Difficulty increase rate on wrong answer"})

    # Tone boost
    _p({"parameter_name": "TONE_BOOST_ACCURACY_THRESHOLD", "file_path": "mandarin/config.py",
        "current_value": TONE_BOOST_ACCURACY_THRESHOLD, "current_value_str": str(TONE_BOOST_ACCURACY_THRESHOLD),
        "value_type": "ratio", "primary_dimension": "tone_phonology",
        "secondary_dimensions": "[]", "min_valid": 0.3, "max_valid": 0.9,
        "soft_min": 0.4, "soft_max": 0.7, "change_direction": "decrease",
        "notes": "Below this accuracy → boost speaking weight"})

    _p({"parameter_name": "TONE_BOOST_MULTIPLIER", "file_path": "mandarin/config.py",
        "current_value": TONE_BOOST_MULTIPLIER, "current_value_str": str(TONE_BOOST_MULTIPLIER),
        "value_type": "float", "primary_dimension": "tone_phonology",
        "secondary_dimensions": "[]", "min_valid": 1.0, "max_valid": 3.0,
        "soft_min": 1.2, "soft_max": 2.0, "change_direction": "increase",
        "notes": "Speaking weight multiplier when tone accuracy is low"})

    _p({"parameter_name": "TONE_BOOST_MAX_WEIGHT", "file_path": "mandarin/config.py",
        "current_value": TONE_BOOST_MAX_WEIGHT, "current_value_str": str(TONE_BOOST_MAX_WEIGHT),
        "value_type": "ratio", "primary_dimension": "tone_phonology",
        "secondary_dimensions": "[]", "min_valid": 0.15, "max_valid": 0.6,
        "soft_min": 0.25, "soft_max": 0.45, "change_direction": "increase",
        "notes": "Maximum speaking weight after tone boost"})

    # Session planning
    _p({"parameter_name": "MAX_NEW_ITEM_RATIO", "file_path": "mandarin/config.py",
        "current_value": MAX_NEW_ITEM_RATIO, "current_value_str": str(MAX_NEW_ITEM_RATIO),
        "value_type": "ratio", "primary_dimension": "srs_funnel",
        "secondary_dimensions": '["retention"]', "min_valid": 0.05, "max_valid": 0.6,
        "soft_min": 0.1, "soft_max": 0.4, "change_direction": "either",
        "notes": "Max ratio of new items per session"})

    _p({"parameter_name": "MIN_SESSION_ITEMS", "file_path": "mandarin/config.py",
        "current_value": MIN_SESSION_ITEMS, "current_value_str": str(MIN_SESSION_ITEMS),
        "value_type": "int", "primary_dimension": "engagement",
        "secondary_dimensions": "[]", "min_valid": 2, "max_valid": 15,
        "soft_min": 3, "soft_max": 8, "change_direction": "either",
        "notes": "Minimum drills in a session"})

    _p({"parameter_name": "SESSION_TIME_CAP_SECONDS", "file_path": "mandarin/config.py",
        "current_value": SESSION_TIME_CAP_SECONDS, "current_value_str": str(SESSION_TIME_CAP_SECONDS),
        "value_type": "int", "primary_dimension": "engagement",
        "secondary_dimensions": '["ux"]', "min_valid": 300, "max_valid": 1800,
        "soft_min": 480, "soft_max": 900, "change_direction": "either",
        "notes": "Auto-finish session after this many seconds"})

    # Error focus
    _p({"parameter_name": "ERROR_FOCUS_LIMIT", "file_path": "mandarin/config.py",
        "current_value": ERROR_FOCUS_LIMIT, "current_value_str": str(ERROR_FOCUS_LIMIT),
        "value_type": "int", "primary_dimension": "drill_quality",
        "secondary_dimensions": '["frustration"]', "min_valid": 1, "max_valid": 10,
        "soft_min": 2, "soft_max": 5, "change_direction": "either",
        "notes": "Max error-focus items per session"})

    # Bounce detection
    _p({"parameter_name": "BOUNCE_ERROR_RATE", "file_path": "mandarin/config.py",
        "current_value": BOUNCE_ERROR_RATE, "current_value_str": str(BOUNCE_ERROR_RATE),
        "value_type": "ratio", "primary_dimension": "frustration",
        "secondary_dimensions": '["ux"]', "min_valid": 0.2, "max_valid": 0.7,
        "soft_min": 0.3, "soft_max": 0.5, "change_direction": "decrease",
        "notes": "Error rate threshold for struggling level detection"})

    # Confusable boost
    _p({"parameter_name": "CONFUSABLE_BOOST_MULT", "file_path": "mandarin/config.py",
        "current_value": CONFUSABLE_BOOST_MULT, "current_value_str": str(CONFUSABLE_BOOST_MULT),
        "value_type": "float", "primary_dimension": "drill_quality",
        "secondary_dimensions": "[]", "min_valid": 1.0, "max_valid": 2.0,
        "soft_min": 1.1, "soft_max": 1.6, "change_direction": "increase",
        "notes": "Priority boost for confusable pair items"})

    # Adaptive session
    _p({"parameter_name": "ADAPTIVE_LOW_COMPLETION", "file_path": "mandarin/config.py",
        "current_value": ADAPTIVE_LOW_COMPLETION, "current_value_str": str(ADAPTIVE_LOW_COMPLETION),
        "value_type": "ratio", "primary_dimension": "ux",
        "secondary_dimensions": '["engagement"]', "min_valid": 0.3, "max_valid": 0.8,
        "soft_min": 0.5, "soft_max": 0.7, "change_direction": "either",
        "notes": "Completion rate below this → light mode"})

    _p({"parameter_name": "ADAPTIVE_EXIT_RATE", "file_path": "mandarin/config.py",
        "current_value": ADAPTIVE_EXIT_RATE, "current_value_str": str(ADAPTIVE_EXIT_RATE),
        "value_type": "ratio", "primary_dimension": "ux",
        "secondary_dimensions": '["engagement"]', "min_valid": 0.2, "max_valid": 0.7,
        "soft_min": 0.3, "soft_max": 0.5, "change_direction": "decrease",
        "notes": "Early exit rate above this → light mode"})

    # New item budget
    _p({"parameter_name": "NEW_BUDGET_DEFAULT", "file_path": "mandarin/config.py",
        "current_value": NEW_BUDGET_DEFAULT, "current_value_str": str(NEW_BUDGET_DEFAULT),
        "value_type": "int", "primary_dimension": "srs_funnel",
        "secondary_dimensions": '["retention"]', "min_valid": 1, "max_valid": 10,
        "soft_min": 2, "soft_max": 5, "change_direction": "either",
        "notes": "Default new items when mastery is above medium"})


try:
    _register_all_parameters()
except ImportError:
    pass  # intelligence module not yet available (e.g., during initial setup)
