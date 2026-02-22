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
    "seen":        "full_pinyin",   # Show full pinyin above hanzi
    "passed_once": "tone_marks",    # Show tone numbers only: "3 3"
    "stabilizing": "initial",       # Show first letter of each syllable: "n h"
    "stable":      "none",
    "durable":     "none",
    "decayed":     "tone_marks",    # Re-scaffold on decay
}

SCAFFOLD_ORDER = ["none", "initial", "tone_marks", "full_pinyin"]

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

# ── Session time cap (hyperfocus guard) ──

SESSION_TIME_CAP_SECONDS = 600  # 10 minutes; auto-finish after this

# ── Adaptive session length ──

ADAPTIVE_LENGTH_MIN_SESSIONS = 3      # Min recent sessions needed for adaptive adjustment
ADAPTIVE_LENGTH_RECENT_SESSIONS = 5   # Number of recent sessions to analyze
ADAPTIVE_LENGTH_LOW_COMPLETION = 0.8  # Avg completion below this → shrink session
ADAPTIVE_LENGTH_SHRINK_FACTOR = 0.8   # Multiply base length by this when shrinking
ADAPTIVE_LENGTH_MIN_ITEMS = 4         # Floor for shrunken session length
ADAPTIVE_LENGTH_HIGH_COMPLETION = 0.95  # Avg completion above this → grow session
ADAPTIVE_LENGTH_HIGH_MIN_SESSIONS = 5   # Need this many sessions for growth
ADAPTIVE_LENGTH_GROW_FACTOR = 1.1     # Multiply base length by this when growing
