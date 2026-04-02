"""Real-world media recommendations and comprehension drills.

Loads a curated catalog of native Chinese media segments (TV, film, YouTube,
Douyin, Bilibili) calibrated by HSK level and content lens. Recommends
segments, runs pre-written comprehension questions, and tracks watch history.

Zero Claude tokens at runtime — all questions are pre-authored in the catalog.
"""

import json
import logging
import random
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import List, Optional

from . import display
from .drills import DrillResult
from mandarin._paths import DATA_DIR

logger = logging.getLogger(__name__)

CATALOG_PATH = DATA_DIR / "media_catalog.json"
PASSAGES_PATH = DATA_DIR / "reading_passages.json"

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
    "wit": "lens_wit",
    "ensemble_comedy": "lens_ensemble_comedy",
    "sharp_observation": "lens_sharp_observation",
    "satire": "lens_satire",
    "moral_texture": "lens_moral_texture",
}


# ── Data loading ─────────────────────────────────────────


_media_catalog_cache = None


def _validate_catalog_entry(entry: dict) -> None:
    """Log warnings for catalog entries that may have copyright or quality issues.

    Checks social_media and podcast entries for:
    - Missing copyright_model: "link_only"
    - Missing attribution dict
    - description_zh over 200 chars (social_media only — prevents reproducing posts)
    - Missing or empty url
    """
    eid = entry.get("id", "?")
    mtype = entry.get("media_type", "")
    if mtype not in ("social_media", "podcast"):
        return
    if entry.get("copyright_model") != "link_only":
        logger.warning("catalog %s: social_media/podcast missing copyright_model: 'link_only'", eid)
    if not entry.get("attribution"):
        logger.warning("catalog %s: social_media/podcast missing attribution dict", eid)
    if not entry.get("url"):
        logger.warning("catalog %s: missing or empty url", eid)
    if mtype == "social_media":
        desc_zh = entry.get("segment", {}).get("description_zh", "")
        if len(desc_zh) > 200:
            logger.warning("catalog %s: description_zh is %d chars (max 200 for social_media)", eid, len(desc_zh))


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
    with open(CATALOG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Support both bare list and {"entries": [...]} wrapper
    if isinstance(data, dict):
        _media_catalog_cache = data.get("entries", [])
    else:
        _media_catalog_cache = data
    for entry in _media_catalog_cache:
        _validate_catalog_entry(entry)
    return _media_catalog_cache


_reading_passages_cache = None

def load_reading_passages(hsk_level: int | None = None) -> list:
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
                with open(PASSAGES_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                _reading_passages_cache = data.get("passages", [])
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to load reading passages: %s", e)
                _reading_passages_cache = []
    if hsk_level is not None:
        return [p for p in _reading_passages_cache
                if p.get("hsk_level") == hsk_level]
    return _reading_passages_cache


def validate_media_urls(timeout: int = 10) -> list:
    """Check all media catalog URLs for accessibility.

    Returns a list of dicts with {id, title, url, status, error} for each
    entry. Status is 'ok', 'broken', 'search_url', or 'error'.
    """
    import urllib.request
    import urllib.error
    catalog = load_media_catalog()
    results = []
    _BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    for entry in catalog:
        url = entry.get("url", "")
        result = {
            "id": entry.get("id", ""),
            "title": entry.get("title", ""),
            "url": url,
            "hsk_level": entry.get("hsk_level", 0),
        }
        if not url:
            result["status"] = "missing"
            result["error"] = "No URL"
            results.append(result)
            continue
        # Flag search/results pages separately
        if any(k in url.lower() for k in ("/search", "/results?", "keyword=")):
            result["status"] = "search_url"
            results.append(result)
            continue
        try:
            # Use GET with browser UA — many streaming sites block HEAD
            req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
            resp = urllib.request.urlopen(req, timeout=timeout)
            result["status"] = "ok" if resp.status < 400 else "broken"
            result["http_status"] = resp.status
        except urllib.error.HTTPError as e:
            # 403/405 from streaming sites (Netflix, Prime) are false positives
            if e.code in (403, 405):
                result["status"] = "ok_restricted"
                result["http_status"] = e.code
            else:
                result["status"] = "broken"
                result["http_status"] = e.code
                result["error"] = str(e.reason)
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:100]
        results.append(result)
    return results


def get_media_entry(media_id: str) -> dict | None:
    """Get a single catalog entry by ID."""
    for entry in load_media_catalog():
        if entry["id"] == media_id:
            return entry
    return None


def _ensure_media_rows(conn, entries: list, user_id: int = 1) -> int:
    """Upsert DB rows for catalog entries per user. Returns count of new rows created."""
    created = 0
    for entry in entries:
        existing = conn.execute(
            "SELECT id FROM media_watch WHERE user_id = ? AND media_id = ?",
            (user_id, entry["id"])
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO media_watch (user_id, media_id, title, hsk_level, media_type)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, entry["id"], entry.get("title", ""), entry.get("hsk_level", 1),
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


def recommend_media(conn, hsk_max: int = 9, lens_weights: dict | None = None,
                    limit: int = 3, time_budget: int | None = None,
                    user_id: int = 1) -> list:
    """Recommend media entries sorted by relevance.

    Priority: unwatched at/below level > lens match > time fit > skip penalty
              > recently-drilled vocab overlap.
    time_budget: available minutes (auto-estimated if None).
    Returns list of (entry_dict, watch_row_dict) tuples.
    """
    catalog = load_media_catalog()
    if not catalog:
        return []

    # Ensure all catalog entries have DB rows for this user
    _ensure_media_rows(conn, catalog, user_id=user_id)

    if time_budget is None:
        time_budget = _estimate_time_budget()

    # Get all watch rows keyed by media_id
    rows = conn.execute("SELECT * FROM media_watch WHERE user_id = ?", (user_id,)).fetchall()
    watch_map = {dict(r)["media_id"]: dict(r) for r in rows}

    # Build set of recently-drilled hanzi (last 7 days, stabilizing/stable/durable)
    recently_drilled = set()
    try:
        drilled_rows = conn.execute("""
            SELECT DISTINCT ci.hanzi FROM progress p
            JOIN content_item ci ON ci.id = p.content_item_id
            WHERE p.user_id = ?
              AND p.last_review_date >= date('now', '-7 days')
              AND p.mastery_stage IN ('stabilizing', 'stable', 'durable')
        """, (user_id,)).fetchall()
        recently_drilled = {r["hanzi"] for r in drilled_rows if r["hanzi"]}
    except Exception:
        pass  # Graceful degradation — skip boost if query fails

    scored = []
    for entry in catalog:
        # Only show verified entries with real URLs
        if not entry.get("verified") or not entry.get("url"):
            continue

        mid = entry["id"]
        hsk = entry.get("hsk_level", 1)
        if hsk > hsk_max:
            continue

        # Skip non-Mandarin content (ambient/silent, English-only)
        audio_lang = entry.get("audio_language", "mandarin")
        if audio_lang != "mandarin":
            continue

        watch = watch_map.get(mid, {})
        if watch.get("status") == "hidden":
            continue

        # Exclude fully-consumed items: watched at least once AND scored
        # well enough (>=70%) that re-watching adds little value.
        times_w = watch.get("times_watched") or 0
        avg_sc = watch.get("avg_score")
        if times_w > 0 and avg_sc is not None and avg_sc >= 0.7:
            continue

        score = 0.0

        # Unwatched bonus
        if times_w == 0:
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

        # Recently-drilled vocab overlap — bridge from drills to exposure
        if recently_drilled:
            vocab_preview = entry.get("vocab_preview", [])
            for vp in vocab_preview:
                hanzi = vp.get("hanzi", "") if isinstance(vp, dict) else str(vp)
                if hanzi in recently_drilled:
                    score += 2.0

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
        show_fn(f"  Tones: {', '.join(str(t) for t in expected_tones)}")

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
        audio, _transcript = record_audio(duration=3.0)

        if audio is None:
            show_fn(display.hint("Recording failed — skipping"))
            break  # Don't keep trying if mic isn't working

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

    # Show passage context
    segment = entry.get("segment", {})
    passage_zh = segment.get("description_zh", "")
    passage_en = segment.get("description", "")
    if passage_zh:
        show_fn(f"  {display.dim('Passage:')}")
        show_fn(f"  {passage_zh}")
        if passage_en:
            show_fn(f"  {display.dim(passage_en)}")
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
        like_input = input_fn("\n  Was this helpful? (y/n/Enter to skip) ").strip().lower()
        if like_input == "y":
            liked = True
        elif like_input == "n":
            liked = False

    # Calculate score — only display if there were actual questions
    score = correct / total if total > 0 else 0.0

    if total > 0:
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


def record_media_presentation(conn, media_id: str, user_id: int = 1):
    """Bump times_presented and set last_presented_at."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """UPDATE media_watch
           SET times_presented = times_presented + 1, last_presented_at = ?
           WHERE user_id = ? AND media_id = ?""",
        (now, user_id, media_id)
    )
    conn.commit()


def record_media_watched(conn, media_id: str, score: float,
                         q_total: int, q_correct: int, user_id: int = 1):
    """Record a completed watch + comprehension attempt."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
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
           WHERE user_id = ? AND media_id = ?""",
        (now, q_total, q_correct, score, score, score, score, user_id, media_id)
    )
    conn.commit()


def record_media_skip(conn, media_id: str, user_id: int = 1):
    """Increment skip count."""
    conn.execute(
        "UPDATE media_watch SET skipped = skipped + 1 WHERE user_id = ? AND media_id = ?",
        (user_id, media_id)
    )
    conn.commit()


def record_media_liked(conn, media_id: str, liked: bool, user_id: int = 1):
    """Record whether the user liked this media."""
    conn.execute(
        "UPDATE media_watch SET liked = ? WHERE user_id = ? AND media_id = ?",
        (1 if liked else 0, user_id, media_id)
    )
    conn.commit()


def get_watch_history(conn, limit: int = 20, user_id: int = 1) -> list:
    """Get recently watched media, newest first."""
    rows = conn.execute(
        """SELECT * FROM media_watch
           WHERE user_id = ? AND times_watched > 0
           ORDER BY last_watched_at DESC
           LIMIT ?""",
        (user_id, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def get_watch_stats(conn, user_id: int = 1) -> dict:
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
        WHERE user_id = ?
    """, (user_id,)).fetchone()
    return dict(row) if row else {}


def get_pending_comprehension(conn, user_id: int = 1) -> str | None:
    """Find a media_id that was presented but never watched (pending quiz).

    Returns media_id or None.
    """
    row = conn.execute(
        """SELECT media_id FROM media_watch
           WHERE user_id = ? AND times_presented > 0 AND times_watched = 0
                 AND skipped = 0 AND status = 'available'
           ORDER BY last_presented_at DESC
           LIMIT 1""",
        (user_id,)
    ).fetchone()
    return row[0] if row else None


def generate_comprehension_questions(passage: dict) -> list:
    """Generate comprehension questions for a reading passage.

    Produces deterministic, zero-LLM questions from passage structure:
    - Vocabulary check: "What does X mean in context?"
    - Main idea: "What is this passage about?"
    - Detail recall: questions about specific details

    Returns a list of question dicts with:
      question, choices (list), answer (index), type, difficulty
    """
    questions = []
    passage.get("text_zh", "")
    text_en = passage.get("text_en", "")
    passage.get("title", "")
    passage.get("title_zh", "")
    vocab = passage.get("vocab_preview", passage.get("key_vocab", []))
    passage.get("hsk_level", 1)

    # 1. Vocabulary check questions from key_vocab / vocab_preview
    for v in vocab[:3]:
        hanzi = v if isinstance(v, str) else v.get("hanzi", "")
        english = "" if isinstance(v, str) else v.get("english", "")
        "" if isinstance(v, str) else v.get("pinyin", "")
        if not hanzi or not english:
            continue

        # Build distractors from other vocab items
        distractors = []
        for other in vocab:
            other_en = "" if isinstance(other, str) else other.get("english", "")
            other_hz = other if isinstance(other, str) else other.get("hanzi", "")
            if other_hz != hanzi and other_en and other_en != english:
                distractors.append(other_en)
        # Pad with generic distractors if needed
        generic = ["hello", "goodbye", "very", "big", "small", "person", "water", "eat"]
        while len(distractors) < 3:
            for g in generic:
                if g != english and g not in distractors:
                    distractors.append(g)
                    break
            else:
                break

        choices = [english] + distractors[:3]
        random.shuffle(choices)
        answer_idx = choices.index(english)

        questions.append({
            "question": f"What does 「{hanzi}」mean in this passage?",
            "question_zh": f"「{hanzi}」在这篇文章中是什么意思？",
            "choices": choices,
            "answer": answer_idx,
            "type": "vocab_check",
            "difficulty": 0.3,
        })

    # 2. Main idea question (if we have English translation)
    if text_en and len(text_en) > 20:
        # Extract a summary from the first sentence of the translation
        first_sentence = text_en.split(".")[0].strip()
        if len(first_sentence) > 10:
            main_idea = first_sentence[:80] + ("..." if len(first_sentence) > 80 else "")
            generic_wrong = [
                "A recipe for traditional Chinese food",
                "Directions to the nearest train station",
                "A phone conversation about weekend plans",
                "A description of someone's daily routine",
            ]
            # Pick 3 distractors that don't overlap with the main idea
            distractors = [d for d in generic_wrong if d.lower() not in main_idea.lower()][:3]
            while len(distractors) < 3:
                distractors.append("An unrelated topic")

            choices = [main_idea] + distractors
            random.shuffle(choices)
            answer_idx = choices.index(main_idea)

            questions.append({
                "question": "What is this passage mainly about?",
                "question_zh": "这篇文章主要讲的是什么？",
                "choices": choices,
                "answer": answer_idx,
                "type": "main_idea",
                "difficulty": 0.5,
            })

    # 3. Detail recall — character/place questions from passage metadata
    details = passage.get("details", [])
    for detail in details[:2]:
        q = detail.get("question", "")
        correct = detail.get("answer", "")
        wrong = detail.get("distractors", [])
        if q and correct and len(wrong) >= 2:
            choices = [correct] + wrong[:3]
            random.shuffle(choices)
            questions.append({
                "question": q,
                "choices": choices,
                "answer": choices.index(correct),
                "type": "detail_recall",
                "difficulty": 0.6,
            })

    # Sort by difficulty
    questions.sort(key=lambda q: q.get("difficulty", 0.5))
    return questions


def generate_listening_passage(conn, user_id: int = 1,
                               hsk_level: int | None = None) -> dict | None:
    """Pick a random reading passage for listening practice via browser TTS.

    Reuses reading passages — the listening view plays text_zh aloud and then
    lets the user reveal the transcript and answer comprehension questions.
    """
    passages = load_reading_passages(hsk_level=hsk_level)
    if not passages:
        # Fall back to all passages if none match the requested level
        passages = load_reading_passages()
    if not passages:
        return None
    return random.choice(passages)
