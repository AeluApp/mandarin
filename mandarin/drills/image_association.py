"""Image association drill — show an image, pick the matching hanzi.

Returns None if the item has no image_url, allowing the dispatcher to
gracefully fall back to another drill type.
"""

import logging
import random
from typing import Optional

from .. import db
from .base import (
    DrillResult, format_hanzi_option, format_answer_feedback,
    _skip_result, _handle_confidence, _run_mc_input,
    cause_to_error_type, classify_error_cause, elaborate_error,
)

logger = logging.getLogger(__name__)


def _get_same_level_distractors(conn, correct_item: dict, n: int = 3) -> list:
    """Fetch distractor hanzi from the same HSK level, excluding the correct item."""
    hsk = correct_item.get("hsk_level")
    item_id = correct_item["id"]
    if not hsk:
        # Fall back to any items with image_url set
        rows = conn.execute(
            """SELECT hanzi FROM content_item
               WHERE id != ? AND image_url IS NOT NULL AND image_url != ''
               ORDER BY RANDOM() LIMIT ?""",
            (item_id, n),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT hanzi FROM content_item
               WHERE id != ? AND hsk_level = ?
               ORDER BY RANDOM() LIMIT ?""",
            (item_id, hsk, n),
        ).fetchall()
    # If not enough from same level, supplement from nearby levels
    if len(rows) < n and hsk:
        extra = conn.execute(
            """SELECT hanzi FROM content_item
               WHERE id != ? AND hsk_level BETWEEN ? AND ?
               AND hanzi NOT IN (SELECT hanzi FROM content_item WHERE id = ?)
               ORDER BY RANDOM() LIMIT ?""",
            (item_id, max(1, hsk - 1), hsk + 1, item_id, n - len(rows)),
        ).fetchall()
        rows = list(rows) + list(extra)
    return [r["hanzi"] for r in rows]


def run_image_association_drill(item: dict, conn, show_fn, input_fn,
                                prominent: bool = True,
                                english_level: str = "full") -> Optional[DrillResult]:
    """Run an image association drill: show image, pick matching hanzi.

    Returns None if the item has no image_url — caller should fall back to
    another drill type.
    """
    image_url = item.get("image_url")
    if not image_url:
        return None

    correct_hanzi = item["hanzi"]

    # Generate distractors
    distractors = _get_same_level_distractors(conn, item, n=3)
    # Ensure we have enough unique distractors
    distractors = [d for d in distractors if d != correct_hanzi]
    if len(distractors) < 1:
        # Not enough distractors to make a meaningful drill
        return None

    # Build options (up to 4)
    options = [correct_hanzi] + distractors[:3]
    random.shuffle(options)

    # Present the drill
    show_fn(f"\n  [dim]Image: {image_url}[/dim]")
    show_fn("  Which character matches this image?\n")
    for i, opt in enumerate(options, 1):
        show_fn(f"  {i}. {format_hanzi_option(opt)}")

    # Get input using standard MC pattern
    result = _run_mc_input(
        item, options, correct_hanzi,
        modality="reading", drill_type="image_association",
        show_fn=show_fn, input_fn=input_fn, english_level=english_level,
    )

    # _run_mc_input returns a DrillResult for skip/confidence, or a string for the pick
    if isinstance(result, DrillResult):
        return result

    user_picked = result
    correct = user_picked == correct_hanzi

    if correct:
        feedback = "  Correct"
    else:
        cause = classify_error_cause(user_picked, correct_hanzi, "image_association", item)
        error_detail = elaborate_error(cause, user_picked, correct_hanzi, item, "image_association")
        feedback = format_answer_feedback(item, english_level)
        if error_detail:
            feedback += "\n" + error_detail
        show_fn(feedback)

    return DrillResult(
        content_item_id=item["id"],
        modality="reading",
        drill_type="image_association",
        correct=correct,
        user_answer=user_picked,
        expected_answer=correct_hanzi,
        feedback=feedback if not correct else "",
    )
