"""Video clip comprehension drill — watch a clip, answer comprehension questions.

Links to media_watch table for tracking. Returns None if item has no
associated media clip, allowing graceful fallback.
"""

import logging
import random
import time
from typing import Optional

from .. import db
from .base import (
    DrillResult, format_hanzi, format_hanzi_inline,
    _skip_result, _run_mc_input,
)

logger = logging.getLogger(__name__)


# Pre-built comprehension question templates
_COMPREHENSION_TEMPLATES = [
    {"type": "gist", "prompt": "What was the main topic of this clip?"},
    {"type": "detail", "prompt": "Which word did you hear in the clip?"},
    {"type": "inference", "prompt": "What would most likely happen next?"},
    {"type": "vocabulary", "prompt": "What does '{word}' mean in this context?"},
]


def _get_media_clip(conn, item: dict) -> dict | None:
    """Look up a media clip associated with this content item.

    Checks media_watch for any clip whose vocab overlaps with the item's hanzi.
    Returns dict with media_id, title, hsk_level, media_type or None.
    """
    hanzi = item.get("hanzi", "")
    if not hanzi:
        return None

    # Try to find a media entry that matches
    row = conn.execute(
        """SELECT media_id, title, hsk_level, media_type
           FROM media_watch
           WHERE status = 'available'
           ORDER BY RANDOM() LIMIT 1""",
    ).fetchone()

    if not row:
        return None

    return dict(row)


def _generate_comprehension_questions(item: dict, media_clip: dict,
                                       conn, n: int = 2) -> list:
    """Generate comprehension questions for a video clip.

    Returns a list of dicts: {prompt, options, correct_answer, question_type}.
    """
    questions = []
    hanzi = item.get("hanzi", "")
    english = item.get("english", "")

    # Question 1: vocabulary recognition
    correct = hanzi
    distractors_rows = conn.execute(
        """SELECT hanzi FROM content_item
           WHERE id != ? AND hsk_level = ?
           ORDER BY RANDOM() LIMIT 3""",
        (item["id"], item.get("hsk_level", 1)),
    ).fetchall()
    distractors = [r["hanzi"] for r in distractors_rows if r["hanzi"] != correct][:3]

    if len(distractors) >= 1:
        options = [correct] + distractors
        random.shuffle(options)
        questions.append({
            "prompt": "Which word appeared in this clip?",
            "options": options,
            "correct_answer": correct,
            "question_type": "vocabulary",
        })

    # Question 2: meaning
    if english:
        correct_meaning = english
        meaning_distractors = conn.execute(
            """SELECT english FROM content_item
               WHERE id != ? AND hsk_level = ? AND english != ?
               ORDER BY RANDOM() LIMIT 3""",
            (item["id"], item.get("hsk_level", 1), english),
        ).fetchall()
        m_distractors = [r["english"] for r in meaning_distractors
                         if r["english"] != correct_meaning][:3]

        if len(m_distractors) >= 1:
            m_options = [correct_meaning] + m_distractors
            random.shuffle(m_options)
            questions.append({
                "prompt": f"What does {hanzi} mean in this context?",
                "options": m_options,
                "correct_answer": correct_meaning,
                "question_type": "meaning",
            })

    return questions[:n]


def _update_media_watch(conn, media_clip: dict, questions_correct: int,
                        questions_total: int, user_id: int = 1):
    """Update media_watch tracking for this viewing."""
    media_id = media_clip.get("media_id")
    if not media_id:
        return
    try:
        conn.execute(
            """UPDATE media_watch
               SET times_watched = times_watched + 1,
                   last_watched_at = datetime('now'),
                   total_questions = total_questions + ?,
                   total_correct = total_correct + ?
               WHERE media_id = ? AND user_id = ?""",
            (questions_total, questions_correct, media_id, user_id),
        )
        conn.commit()
    except Exception:
        logger.debug("media_watch update failed", exc_info=True)


def run_video_comprehension_drill(item: dict, conn, show_fn, input_fn,
                                   prominent: bool = True,
                                   english_level: str = "full") -> DrillResult | None:
    """Run a video comprehension drill.

    Shows a video clip reference, then asks comprehension questions.
    Returns None if no media clip is available for the item.
    """
    media_clip = _get_media_clip(conn, item)
    if not media_clip:
        return None

    start_time = time.monotonic()

    # Present the video reference
    show_fn(f"\n  [dim]Video: {media_clip.get('title', 'Untitled')}[/dim]")
    show_fn(f"  [dim]Type: {media_clip.get('media_type', 'clip')} | "
            f"HSK {media_clip.get('hsk_level', '?')}[/dim]")
    show_fn(f"  Watch the clip, then answer the questions.\n")

    # Generate and run questions
    questions = _generate_comprehension_questions(item, media_clip, conn)
    if not questions:
        return None

    total_correct = 0
    total_questions = len(questions)

    for qi, q in enumerate(questions):
        show_fn(f"  Q{qi + 1}: {q['prompt']}\n")
        for oi, opt in enumerate(q["options"], 1):
            show_fn(f"  {oi}. {opt}")

        result = _run_mc_input(
            item, q["options"], q["correct_answer"],
            modality="listening", drill_type="video_comprehension",
            show_fn=show_fn, input_fn=input_fn, english_level=english_level,
        )

        if isinstance(result, DrillResult):
            # User skipped — return immediately
            if result.skipped:
                return result
            # Confidence input — count as incorrect for this question
            continue

        if result == q["correct_answer"]:
            total_correct += 1
            show_fn("  Correct\n")
        else:
            show_fn(f"  Not quite — answer: {q['correct_answer']}\n")

    # Calculate viewing time and comprehension score
    viewing_time = time.monotonic() - start_time
    comprehension_score = total_correct / total_questions if total_questions > 0 else 0.0

    # Update tracking
    _update_media_watch(conn, media_clip, total_correct, total_questions)

    overall_correct = total_correct == total_questions

    return DrillResult(
        content_item_id=item["id"],
        modality="listening",
        drill_type="video_comprehension",
        correct=overall_correct,
        user_answer=f"{total_correct}/{total_questions}",
        expected_answer=f"{total_questions}/{total_questions}",
        score=comprehension_score,
        feedback=f"  {total_correct}/{total_questions} correct "
                 f"({viewing_time:.0f}s viewing time)",
        metadata={
            "media_id": media_clip.get("media_id"),
            "viewing_time_s": round(viewing_time, 1),
            "comprehension_score": round(comprehension_score, 2),
            "questions_correct": total_correct,
            "questions_total": total_questions,
        },
    )
