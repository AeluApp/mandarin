"""Metacognition -- calibration tracking, feedback, and reflection prompts.

Tracks the alignment between a learner's confidence and actual performance.
Provides calibration feedback to help learners develop accurate self-assessment.

References:
- Dunlosky & Rawson (2012): Self-regulated comprehension
- Koriat (2007): Metacognitive monitoring and regulation
- Bjork, Dunlosky & Kornell (2013): Self-regulated learning
"""

import logging
import sqlite3
from datetime import datetime, timezone, UTC

logger = logging.getLogger(__name__)

# Confidence levels from Aelu's system — maps confidence tags to predicted
# probabilities of a correct answer at that confidence level.
CONFIDENCE_LEVELS = {
    "full": 1.0,      # "I know this"
    "half": 0.5,      # "50/50 guess"
    "narrowed": 0.4,  # "Narrowed to 2"
    "unknown": 0.15,  # "No idea"
}

# Human-readable labels for each confidence level.
_CONFIDENCE_LABELS = {
    "full": "confident",
    "half": "guessing",
    "narrowed": "unsure",
    "unknown": "unknown",
}

# Minimum reviews before generating calibration feedback.
_MIN_REVIEWS_FOR_FEEDBACK = 20

# Calibration gap threshold — only generate feedback when gap exceeds this.
_CALIBRATION_GAP_THRESHOLD = 0.15

REFLECTION_PROMPTS = [
    "Which item surprised you most today?",
    "What pattern did you notice across today's items?",
    "Was anything easier than you expected?",
    "What would you like to practice more?",
    "Did you use any memory tricks today?",
]


def track_calibration(conn: sqlite3.Connection, user_id: int, days: int = 30) -> dict:
    """Compute calibration metrics for a user over recent reviews.

    Queries review_event for the last ``days`` days, groups by confidence
    level, and computes actual accuracy vs predicted probability for each.

    Returns:
        {
            "brier_score": float,  # 0 = perfect, 1 = worst
            "calibration_curve": {
                "full": {"predicted": 1.0, "actual": float, "n": int},
                "half": {"predicted": 0.5, "actual": float, "n": int},
                ...
            },
            "overconfident": bool,  # actual < predicted on average
            "underconfident": bool, # actual > predicted on average
            "calibration_gap": float, # weighted avg |predicted - actual|
            "total_reviews": int,
        }
    """
    rows = conn.execute(
        """
        SELECT confidence, correct
        FROM review_event
        WHERE user_id = ?
          AND created_at >= datetime('now', ?)
        """,
        (user_id, f"-{days} days"),
    ).fetchall()

    if not rows:
        return {
            "brier_score": 0.25,
            "calibration_curve": {},
            "overconfident": False,
            "underconfident": False,
            "calibration_gap": 0.0,
            "total_reviews": 0,
        }

    # Accumulate per-confidence-level stats.
    buckets: dict[str, dict] = {}
    predictions: list[tuple[float, float]] = []

    for confidence_tag, correct in rows:
        predicted = CONFIDENCE_LEVELS.get(confidence_tag)
        if predicted is None:
            # Unknown confidence tag — skip.
            continue

        actual = 1.0 if correct else 0.0
        predictions.append((predicted, actual))

        if confidence_tag not in buckets:
            buckets[confidence_tag] = {"correct": 0, "total": 0}
        buckets[confidence_tag]["total"] += 1
        if correct:
            buckets[confidence_tag]["correct"] += 1

    brier = compute_brier_score(predictions)

    # Build calibration curve.
    calibration_curve: dict[str, dict] = {}
    weighted_gap_sum = 0.0
    total_weighted = 0

    for tag, predicted in CONFIDENCE_LEVELS.items():
        if tag in buckets:
            b = buckets[tag]
            actual_rate = b["correct"] / b["total"] if b["total"] > 0 else 0.0
            calibration_curve[tag] = {
                "predicted": predicted,
                "actual": round(actual_rate, 3),
                "n": b["total"],
            }
            weighted_gap_sum += abs(predicted - actual_rate) * b["total"]
            total_weighted += b["total"]

    calibration_gap = weighted_gap_sum / total_weighted if total_weighted > 0 else 0.0

    # Determine over/under-confidence from the weighted gap direction.
    # Over-predicted means predicted > actual on average.
    weighted_direction_sum = 0.0
    for tag, predicted in CONFIDENCE_LEVELS.items():
        if tag in buckets:
            b = buckets[tag]
            actual_rate = b["correct"] / b["total"] if b["total"] > 0 else 0.0
            weighted_direction_sum += (predicted - actual_rate) * b["total"]

    avg_direction = weighted_direction_sum / total_weighted if total_weighted > 0 else 0.0

    return {
        "brier_score": round(brier, 4),
        "calibration_curve": calibration_curve,
        "overconfident": avg_direction > _CALIBRATION_GAP_THRESHOLD,
        "underconfident": avg_direction < -_CALIBRATION_GAP_THRESHOLD,
        "calibration_gap": round(calibration_gap, 3),
        "total_reviews": len(predictions),
    }


def compute_brier_score(predictions: list[tuple[float, float]]) -> float:
    """Brier score: mean squared difference between predicted probability and outcome.

    Args:
        predictions: list of (predicted_probability, actual_outcome) where
            actual is 0 or 1.

    Lower is better. 0 = perfect. 0.25 = random for binary outcomes.
    """
    if not predictions:
        return 0.25
    return sum((p - a) ** 2 for p, a in predictions) / len(predictions)


def generate_calibration_feedback(calibration: dict) -> str | None:
    """Generate a brief, gentle calibration insight.

    Only generates feedback when calibration gap > 15% and there is
    sufficient data (>= 20 reviews). Returns None if calibration is
    good or insufficient data.
    """
    total = calibration.get("total_reviews", 0)
    if total < _MIN_REVIEWS_FOR_FEEDBACK:
        return None

    gap = calibration.get("calibration_gap", 0.0)
    if gap <= _CALIBRATION_GAP_THRESHOLD:
        return None

    curve = calibration.get("calibration_curve", {})

    if calibration.get("overconfident"):
        # Find the "full" confidence bucket for the specific feedback.
        full = curve.get("full")
        if full and full["n"] >= 5:
            actual_pct = round(full["actual"] * 100)
            return (
                f"You said 'confident' on {full['n']} items and got "
                f"{actual_pct}% right. Consider slowing down on items "
                f"that feel easy."
            )
        # Fallback: use overall gap.
        return (
            "Your confidence tends to run ahead of your accuracy. "
            "Try pausing a moment before committing to answers that "
            "feel certain."
        )

    if calibration.get("underconfident"):
        # Find the confidence level where they underestimate most.
        for tag in ("half", "narrowed", "unknown"):
            bucket = curve.get(tag)
            if bucket and bucket["n"] >= 5:
                actual_pct = round(bucket["actual"] * 100)
                label = _CONFIDENCE_LABELS[tag]
                return (
                    f"You said '{label}' on {bucket['n']} items but got "
                    f"{actual_pct}% right! You know more than you think."
                )
        return (
            "Your accuracy is better than your confidence suggests. "
            "Trust your instincts a little more."
        )

    return None


def get_reflection_prompt(conn: sqlite3.Connection, user_id: int) -> str:
    """Get the next reflection prompt (rotating, avoids recent repeats).

    Uses a rotating index based on the count of past reflections mod the
    number of available prompts, so the learner cycles through all prompts
    before repeating.
    """
    _ensure_reflection_table(conn)

    row = conn.execute(
        "SELECT COUNT(*) FROM reflection_log WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    count = row[0] if row else 0
    idx = count % len(REFLECTION_PROMPTS)
    return REFLECTION_PROMPTS[idx]


def save_reflection(
    conn: sqlite3.Connection,
    user_id: int,
    session_id: int,
    prompt: str,
    response: str,
) -> None:
    """Save a learner's reflection response."""
    _ensure_reflection_table(conn)

    conn.execute(
        """
        INSERT INTO reflection_log (user_id, session_id, prompt, response, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            session_id,
            prompt,
            response,
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


def save_calibration_snapshot(
    conn: sqlite3.Connection,
    user_id: int,
    calibration: dict,
) -> None:
    """Persist calibration metrics for tracking over time.

    Stores a snapshot of the Brier score, calibration gap, and directional
    flags so that calibration trends can be visualized over weeks/months.
    """
    _ensure_calibration_table(conn)

    import json

    conn.execute(
        """
        INSERT INTO calibration_snapshot
            (user_id, brier_score, calibration_gap, overconfident,
             underconfident, total_reviews, curve_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            calibration["brier_score"],
            calibration["calibration_gap"],
            1 if calibration["overconfident"] else 0,
            1 if calibration["underconfident"] else 0,
            calibration["total_reviews"],
            json.dumps(calibration["calibration_curve"]),
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


# ── Private helpers ──


def _ensure_reflection_table(conn: sqlite3.Connection) -> None:
    """Create reflection_log table if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reflection_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id INTEGER,
            prompt TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES user(id),
            FOREIGN KEY (session_id) REFERENCES session_log(id)
        )
    """)


def _ensure_calibration_table(conn: sqlite3.Connection) -> None:
    """Create calibration_snapshot table if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibration_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            brier_score REAL NOT NULL,
            calibration_gap REAL NOT NULL,
            overconfident INTEGER NOT NULL DEFAULT 0,
            underconfident INTEGER NOT NULL DEFAULT 0,
            total_reviews INTEGER NOT NULL DEFAULT 0,
            curve_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES user(id)
        )
    """)
