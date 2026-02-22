"""Real-world media recommendations and comprehension drills.

Loads a curated catalog of native Chinese media segments (TV, film, YouTube,
Douyin, Bilibili) calibrated by HSK level and content lens. Recommends
segments, runs pre-written comprehension questions, and tracks watch history.

Zero Claude tokens at runtime — all questions are pre-authored in the catalog.
"""

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import display
from .drills import DrillResult

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent.parent / "data" / "media_catalog.json"
PASSAGES_PATH = Path(__file__).parent.parent / "data" / "reading_passages.json"

# Content lens mapping — catalog tags → DB lens column names
LENS_MAP = {
    "humane_mystery": "lens_humane_mystery",
    "quiet_observation": "lens_quiet_observation",
    "urban_texture": "lens_urban_texture",
    "institutions": "lens_institutions",
    "identity": "lens_identity",
    "structural_comedy": "lens_comedy",
    "comedy": "lens_comedy",
    "food": "lens_food",
    "travel": "lens_travel",
    "explainers": "lens_explainers",
}


# ── Data loading ─────────────────────────────────────────


_media_catalog_cache = None


def load_media_catalog() -> list:
    """Load the media catalog from JSON. Returns empty list if missing.

    Cached after first load — the catalog is static seed data.
    """
    global _media_catalog_cache
    if _media_catalog_cache is not None:
        return _media_catalog_cache
    if not CATALOG_PATH.exists():
        logger.warning("media catalog not found at %s", CATALOG_PATH)
        _media_catalog_cache = []
        return _media_catalog_cache
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Support both bare list and {"entries": [...]} wrapper
    if isinstance(data, dict):
        _media_catalog_cache = data.get("entries", [])
    else:
        _media_catalog_cache = data
    return _media_catalog_cache


_reading_passages_cache = None

def load_reading_passages(hsk_level: Optional[int] = None) -> list:
    """Load reading passages from JSON, optionally filtered by HSK level.

    Returns a list of passage dicts with text_zh, text_pinyin, text_en,
    questions, etc. Used for reading comprehension practice.
    """
    global _reading_passages_cache
    if _reading_passages_cache is None:
        if not PASSAGES_PATH.exists():
            logger.debug("reading passages not found at %s", PASSAGES_PATH)
            _reading_passages_cache = []
        else:
            try:
                with open(PASSAGES_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _reading_passages_cache = data.get("passages", [])
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to load reading passages: %s", e)
                _reading_passages_cache = []
    if hsk_level is not None:
        return [p for p in _reading_passages_cache
                if p.get("hsk_level") == hsk_level]
    return _reading_passages_cache


def get_media_entry(media_id: str) -> Optional[dict]:
    """Get a single catalog entry by ID."""
    for entry in load_media_catalog():
        if entry["id"] == media_id:
            return entry
    return None


def _ensure_media_rows(conn, entries: list) -> int:
    """Upsert DB rows for catalog entries. Returns count of new rows created."""
    created = 0
    for entry in entries:
        existing = conn.execute(
            "SELECT id FROM media_watch WHERE media_id = ?",
            (entry["id"],)
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO media_watch (media_id, title, hsk_level, media_type)
                   VALUES (?, ?, ?, ?)""",
                (entry["id"], entry.get("title", ""), entry.get("hsk_level", 1),
                 entry.get("media_type", "other"))
            )
            created += 1
    conn.commit()
    return created


# ── Recommendation ───────────────────────────────────────


def _estimate_time_budget() -> int:
    """Estimate how many minutes the user likely has right now.

    Uses day-of-week and time-of-day as signals:
    - Weekday mornings (before work): ~5 min → short clips
    - Weekday evenings: ~15 min → medium content
    - Weekend mornings/afternoons: ~40 min → movies/episodes OK
    - Late night (any day): ~10 min → short-medium

    Returns estimated available minutes.
    """
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Mon, 6=Sun
    is_weekend = weekday >= 5

    if is_weekend:
        if 8 <= hour < 12:
            return 40      # Weekend morning — time for a film segment
        elif 12 <= hour < 18:
            return 30      # Weekend afternoon
        elif 18 <= hour < 22:
            return 20      # Weekend evening
        else:
            return 10      # Late night
    else:
        if 6 <= hour < 9:
            return 5       # Weekday morning — quick clip before work
        elif 9 <= hour < 17:
            return 5       # Working hours — just a clip
        elif 17 <= hour < 20:
            return 15      # Weekday evening
        elif 20 <= hour < 23:
            return 20      # Weekday late evening — some room
        else:
            return 5       # Late night weekday


def _get_duration_minutes(entry: dict) -> int:
    """Extract duration in minutes from a catalog entry."""
    # Use explicit field if present
    if "duration_minutes" in entry:
        return entry["duration_minutes"]
    # Parse from segment times
    seg = entry.get("segment", {})
    start = seg.get("start_time", "00:00:00")
    end = seg.get("end_time", "00:05:00")
    try:
        def _to_seconds(t):
            parts = t.split(":")
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return max(1, (_to_seconds(end) - _to_seconds(start)) // 60)
    except (ValueError, IndexError):
        return 5  # Default 5 min


def recommend_media(conn, hsk_max: int = 9, lens_weights: Optional[dict] = None,
                    limit: int = 3, time_budget: Optional[int] = None,
                    user_id: int = 1) -> list:
    """Recommend media entries sorted by relevance.

    Priority: unwatched at/below level > lens match > time fit > skip penalty.
    time_budget: available minutes (auto-estimated if None).
    Returns list of (entry_dict, watch_row_dict) tuples.
    """
    catalog = load_media_catalog()
    if not catalog:
        return []

    # Ensure all catalog entries have DB rows
    _ensure_media_rows(conn, catalog)

    if time_budget is None:
        time_budget = _estimate_time_budget()

    # Get all watch rows keyed by media_id
    rows = conn.execute("SELECT * FROM media_watch WHERE user_id = ?", (user_id,)).fetchall()
    watch_map = {dict(r)["media_id"]: dict(r) for r in rows}

    scored = []
    for entry in catalog:
        mid = entry["id"]
        hsk = entry.get("hsk_level", 1)
        if hsk > hsk_max:
            continue

        watch = watch_map.get(mid, {})
        if watch.get("status") == "hidden":
            continue

        score = 0.0

        # Unwatched bonus
        if (watch.get("times_watched") or 0) == 0:
            score += 10.0

        # Level proximity bonus (prefer content at or just below level)
        level_diff = hsk_max - hsk
        if 0 <= level_diff <= 1:
            score += 5.0
        elif level_diff == 2:
            score += 3.0
        else:
            score += 1.0

        # Lens match bonus
        if lens_weights:
            for lens_tag in entry.get("content_lenses", []):
                db_col = LENS_MAP.get(lens_tag, "")
                if db_col and db_col in lens_weights:
                    score += lens_weights[db_col] * 3.0

        # Skip penalty
        skips = watch.get("skipped") or 0
        score -= skips * 2.0

        # Liked bonus
        if watch.get("liked") == 1:
            score += 2.0

        # Cost preference — free content gets a boost
        cost = entry.get("cost", "free")
        if cost == "free":
            score += 2.0
        elif cost == "subscription":
            score += 1.0
        # rental/purchase get no bonus (still shown, just ranked lower)

        # Time fit — boost content that matches available time
        duration = _get_duration_minutes(entry)
        if duration <= time_budget:
            # Fits within budget — bonus proportional to how well it fills the time
            fill_ratio = duration / time_budget if time_budget > 0 else 1.0
            score += fill_ratio * 4.0   # Best score for content that fills the window
        else:
            # Too long — penalty proportional to overshoot
            overshoot = (duration - time_budget) / time_budget if time_budget > 0 else 1.0
            score -= min(overshoot * 6.0, 8.0)  # Strong penalty but don't eliminate

        scored.append((score, entry, watch))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(entry, watch) for _, entry, watch in scored[:limit]]


# ── Tone practice ───────────────────────────────────────


def _run_tone_practice(vocab_preview: list, show_fn, input_fn,
                       conn=None, max_words: int = 3) -> list:
    """Run tone speaking practice on vocab from a media entry.

    Picks up to max_words items from vocab_preview that have tonal pinyin,
    plays reference audio, records the learner, and grades tone accuracy.

    Returns list of {"hanzi", "pinyin", "score", "feedback"} dicts.
    Silently returns [] if mic unavailable or vocab empty.
    """
    if not vocab_preview:
        return []

    try:
        from .tone_grading import (is_recording_available, record_audio,
                                   save_recording, grade_tones, pinyin_to_tones)
        from .audio import speak_and_wait, is_audio_available
    except ImportError:
        return []

    if not is_recording_available():
        return []

    # Filter to vocab that has tonal pinyin
    candidates = []
    for v in vocab_preview:
        pinyin = v.get("pinyin", "")
        tones = pinyin_to_tones(pinyin)
        if tones:
            candidates.append((v, tones))

    if not candidates:
        return []

    # Pick up to max_words
    if len(candidates) > max_words:
        candidates = random.sample(candidates, max_words)

    show_fn("\n  ── Tone Practice ──")
    show_fn(display.dim("Say each word aloud. S = skip tone practice, Q = quit.") + "\n")

    audio_ok = is_audio_available()
    results = []

    for v, expected_tones in candidates:
        hanzi = v["hanzi"]
        pinyin = v.get("pinyin", "")
        english = v.get("english", "")

        show_fn(f"  {display.hanzi(hanzi)}  "
                f"{pinyin}  —  {english}")
        show_fn(f"  Tones: {' '.join(str(t) for t in expected_tones)}")

        # Play reference audio
        if audio_ok:
            show_fn(display.dim("Listen..."))
            speak_and_wait(hanzi)

        prompt = input_fn("  Press Enter to record (S=skip, Q=quit) ").strip().upper()

        if prompt == "Q":
            break
        if prompt == "S":
            break

        show_fn(display.dim("Recording (3 seconds)..."))
        audio = record_audio(duration=3.0)

        if audio is None:
            show_fn(display.hint("Recording failed — skipping"))
            continue

        show_fn(display.dim("Analyzing..."))
        result = grade_tones(audio, expected_tones)
        score = result["overall_score"]
        feedback = result["feedback"]

        # Save recording to disk
        file_path = save_recording(audio, 0, 0)

        # Persist to audio_recording if hanzi maps to a content_item
        if conn and file_path:
            row = conn.execute(
                "SELECT id FROM content_item WHERE hanzi = ?", (hanzi,)
            ).fetchone()
            if row:
                import json as _json
                conn.execute("""
                    INSERT INTO audio_recording (content_item_id, file_path,
                                                 tone_scores_json, overall_score)
                    VALUES (?, ?, ?, ?)
                """, (row[0], str(file_path),
                      _json.dumps(result["syllable_scores"]), score))
                conn.commit()

        # Show result
        show_fn(display.tone_score(score))

        if feedback:
            show_fn(display.dim(feedback))

        show_fn("")
        results.append({
            "hanzi": hanzi,
            "pinyin": pinyin,
            "score": score,
            "feedback": feedback,
        })

    return results


# ── Comprehension drill ─────────────────────────────────


def run_media_comprehension(entry: dict, show_fn, input_fn,
                            conn=None) -> DrillResult:
    """Run comprehension questions for a media entry.

    Shows MC + vocab_check questions with shuffled options.
    Returns DrillResult with score 0.0-1.0.
    """
    media_id = entry["id"]
    title = entry.get("title", "")
    questions = entry.get("questions", [])

    if not questions:
        return DrillResult(
            content_item_id=0, modality="listening",
            drill_type="media_comprehension", correct=False,
            skipped=True, feedback="  (No questions for this entry)",
        )

    # Show header
    show_fn(f"\n  ── Comprehension: {title} ──")

    # Show vocab preview
    vocab_preview = entry.get("vocab_preview", [])
    if vocab_preview:
        show_fn(f"\n{display.dim('Vocab preview:')}")
        for v in vocab_preview:
            show_fn(display.hanzi_with_detail(v['hanzi'], v.get('pinyin', ''), v.get('english', '')))
        show_fn("")

    total = 0
    correct = 0

    for i, q in enumerate(questions, 1):
        q_type = q.get("type", "mc")
        q_text = q.get("q_zh", "")
        q_en = q.get("q_en", "")

        show_fn(f"  Q{i}. {q_text}")
        if q_en:
            show_fn(f"      {q_en}")

        if q_type == "mc":
            options = list(q.get("options", []))
            random.shuffle(options)
            for j, opt in enumerate(options, 1):
                text = opt.get("text", "")
                text_en = opt.get("text_en", "")
                show_fn(f"    {j}. {text}  ({text_en})")

            answer = input_fn("  > ").strip()

            # Handle quit/skip
            if answer.upper() == "Q":
                return DrillResult(
                    content_item_id=0, modality="listening",
                    drill_type="media_comprehension", correct=False,
                    skipped=True, user_answer="Q",
                )

            try:
                choice_idx = int(answer) - 1
                chosen = options[choice_idx]
            except (ValueError, IndexError):
                show_fn(display.hint("Invalid choice"))
                total += 1
                continue

            total += 1
            if chosen.get("correct"):
                correct += 1
                show_fn(display.correct_mark())
            else:
                # Find the correct answer
                right = next((o for o in options if o.get("correct")), None)
                right_text = right["text"] if right else "?"
                show_fn(display.wrong_mark(right_text))

        elif q_type == "vocab_check":
            answer_key = q.get("answer", "")
            distractors = list(q.get("distractors", []))
            all_options = [answer_key] + distractors
            random.shuffle(all_options)

            for j, opt in enumerate(all_options, 1):
                show_fn(f"    {j}. {opt}")

            answer = input_fn("  > ").strip()

            if answer.upper() == "Q":
                return DrillResult(
                    content_item_id=0, modality="listening",
                    drill_type="media_comprehension", correct=False,
                    skipped=True, user_answer="Q",
                )

            try:
                choice_idx = int(answer) - 1
                chosen = all_options[choice_idx]
            except (ValueError, IndexError):
                show_fn(display.hint("Invalid choice"))
                total += 1
                continue

            total += 1
            if chosen == answer_key:
                correct += 1
                show_fn(display.correct_mark())
            else:
                show_fn(display.wrong_mark(answer_key))

    # ── Tone practice round ──────────────────────────────
    tone_scores = _run_tone_practice(vocab_preview, show_fn, input_fn, conn)

    # Cultural note
    cultural_note = entry.get("cultural_note", "")
    if cultural_note:
        show_fn(f"\n{display.dim('Cultural note: ' + cultural_note)}")

    # Follow-up
    follow_up = entry.get("follow_up", "")
    if follow_up:
        show_fn(display.dim(follow_up))

    # Ask liked
    liked = None
    if conn:
        like_input = input_fn("\n  Liked? (y/n/Enter to skip) ").strip().lower()
        if like_input == "y":
            liked = True
        elif like_input == "n":
            liked = False

    # Calculate score
    score = correct / total if total > 0 else 0.0

    show_fn(f"\n  Score: {correct}/{total} ({score:.0%})")
    if tone_scores:
        avg_tone = sum(t["score"] for t in tone_scores) / len(tone_scores)
        show_fn(f"  Tone accuracy: {avg_tone:.0%}")

    # Record to DB
    if conn:
        record_media_watched(conn, media_id, score, total, correct)
        if liked is not None:
            record_media_liked(conn, media_id, liked)

    metadata = {"media_id": media_id}
    if tone_scores:
        metadata["tone_scores"] = tone_scores

    return DrillResult(
        content_item_id=0,
        modality="listening",
        drill_type="media_comprehension",
        correct=score >= 0.5,
        score=score,
        feedback=f"  {correct}/{total}",
        metadata=metadata,
    )


# ── Tracking ─────────────────────────────────────────────


def record_media_presentation(conn, media_id: str):
    """Bump times_presented and set last_presented_at."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE media_watch
           SET times_presented = times_presented + 1, last_presented_at = ?
           WHERE media_id = ?""",
        (now, media_id)
    )
    conn.commit()


def record_media_watched(conn, media_id: str, score: float,
                         q_total: int, q_correct: int):
    """Record a completed watch + comprehension attempt."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE media_watch
           SET times_watched = times_watched + 1,
               last_watched_at = ?,
               total_questions = total_questions + ?,
               total_correct = total_correct + ?,
               avg_score = CASE
                   WHEN times_watched = 0 THEN ?
                   ELSE (avg_score * times_watched + ?) / (times_watched + 1)
               END,
               best_score = CASE
                   WHEN best_score IS NULL OR ? > best_score THEN ?
                   ELSE best_score
               END,
               status = 'watched'
           WHERE media_id = ?""",
        (now, q_total, q_correct, score, score, score, score, media_id)
    )
    conn.commit()


def record_media_skip(conn, media_id: str):
    """Increment skip count."""
    conn.execute(
        "UPDATE media_watch SET skipped = skipped + 1 WHERE media_id = ?",
        (media_id,)
    )
    conn.commit()


def record_media_liked(conn, media_id: str, liked: bool):
    """Record whether the user liked this media."""
    conn.execute(
        "UPDATE media_watch SET liked = ? WHERE media_id = ?",
        (1 if liked else 0, media_id)
    )
    conn.commit()


def get_watch_history(conn, limit: int = 20) -> list:
    """Get recently watched media, newest first."""
    rows = conn.execute(
        """SELECT * FROM media_watch
           WHERE times_watched > 0
           ORDER BY last_watched_at DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_watch_stats(conn) -> dict:
    """Aggregate watch statistics."""
    row = conn.execute("""
        SELECT
            COUNT(*) as total_entries,
            SUM(CASE WHEN times_watched > 0 THEN 1 ELSE 0 END) as watched,
            SUM(CASE WHEN skipped > 0 AND times_watched = 0 THEN 1 ELSE 0 END) as skipped_only,
            AVG(CASE WHEN avg_score IS NOT NULL THEN avg_score END) as overall_avg,
            SUM(total_questions) as total_q,
            SUM(total_correct) as total_correct,
            SUM(CASE WHEN liked = 1 THEN 1 ELSE 0 END) as liked_count
        FROM media_watch
    """).fetchone()
    return dict(row) if row else {}


def get_pending_comprehension(conn) -> Optional[str]:
    """Find a media_id that was presented but never watched (pending quiz).

    Returns media_id or None.
    """
    row = conn.execute(
        """SELECT media_id FROM media_watch
           WHERE times_presented > 0 AND times_watched = 0
                 AND skipped = 0 AND status = 'available'
           ORDER BY last_presented_at DESC
           LIMIT 1"""
    ).fetchone()
    return row[0] if row else None
