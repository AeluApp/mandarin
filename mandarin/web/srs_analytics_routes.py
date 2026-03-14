"""SRS, analytics, and content import routes — competitor A+ gap closures."""

import csv
import io
import logging
import math
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from .. import db
from .api_errors import api_error_handler
from .middleware import _get_user_id

logger = logging.getLogger(__name__)

srs_analytics_bp = Blueprint("srs_analytics", __name__)


# ── Helpers ────────────────────────────────────────────────────────────

def _get_user_retention_threshold(conn, user_id: int) -> float:
    """Get the user's target retention rate, falling back to RECALL_THRESHOLD."""
    from ..config import RECALL_THRESHOLD
    row = conn.execute(
        "SELECT target_retention_rate FROM learner_profile WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row and row["target_retention_rate"] is not None:
        return float(row["target_retention_rate"])
    return RECALL_THRESHOLD


# ── 1. User-adjustable target retention rate ───────────────────────────

@srs_analytics_bp.route("/api/settings/retention-target", methods=["GET", "PUT"])
@api_error_handler("RetentionTarget")
def api_retention_target():
    """Get or set the user's target retention rate (0.80-0.95)."""
    user_id = _get_user_id()
    with db.connection() as conn:
        if request.method == "PUT":
            data = request.get_json(silent=True) or {}
            rate = data.get("target_retention_rate")
            if rate is None:
                return jsonify({"error": "target_retention_rate is required"}), 400
            try:
                rate = float(rate)
            except (TypeError, ValueError):
                return jsonify({"error": "target_retention_rate must be a number"}), 400
            if rate < 0.80 or rate > 0.95:
                return jsonify({"error": "target_retention_rate must be between 0.80 and 0.95"}), 400
            conn.execute(
                "UPDATE learner_profile SET target_retention_rate = ? WHERE user_id = ?",
                (round(rate, 2), user_id),
            )
            conn.commit()
            return jsonify({"target_retention_rate": round(rate, 2)})
        else:
            threshold = _get_user_retention_threshold(conn, user_id)
            return jsonify({"target_retention_rate": threshold})


# ── 2. Suspend / bury / reschedule individual items ────────────────────

@srs_analytics_bp.route("/api/items/<int:item_id>/suspend", methods=["POST"])
@api_error_handler("ItemSuspend")
def api_item_suspend(item_id):
    """Suspend an item indefinitely — excluded from scheduling until resumed."""
    user_id = _get_user_id()
    with db.connection() as conn:
        # Verify item exists
        item = conn.execute(
            "SELECT id FROM content_item WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            return jsonify({"error": "Item not found"}), 404

        # Set suspended_until to far future for all modalities
        updated = conn.execute(
            """UPDATE progress SET suspended_until = '9999-12-31'
               WHERE content_item_id = ? AND user_id = ?""",
            (item_id, user_id),
        ).rowcount

        # If no progress rows exist yet, create them so the suspension is recorded
        if updated == 0:
            for modality in ("reading", "listening", "speaking", "ime"):
                conn.execute(
                    """INSERT OR IGNORE INTO progress
                       (user_id, content_item_id, modality, suspended_until)
                       VALUES (?, ?, ?, '9999-12-31')""",
                    (user_id, item_id, modality),
                )

        conn.commit()
        return jsonify({"status": "suspended", "item_id": item_id})


@srs_analytics_bp.route("/api/items/<int:item_id>/unsuspend", methods=["POST"])
@api_error_handler("ItemUnsuspend")
def api_item_unsuspend(item_id):
    """Remove suspension from an item."""
    user_id = _get_user_id()
    with db.connection() as conn:
        conn.execute(
            """UPDATE progress SET suspended_until = NULL
               WHERE content_item_id = ? AND user_id = ?""",
            (item_id, user_id),
        )
        conn.commit()
        return jsonify({"status": "unsuspended", "item_id": item_id})


@srs_analytics_bp.route("/api/items/<int:item_id>/bury", methods=["POST"])
@api_error_handler("ItemBury")
def api_item_bury(item_id):
    """Bury an item — skip until tomorrow."""
    user_id = _get_user_id()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    with db.connection() as conn:
        item = conn.execute(
            "SELECT id FROM content_item WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            return jsonify({"error": "Item not found"}), 404

        updated = conn.execute(
            """UPDATE progress SET suspended_until = ?
               WHERE content_item_id = ? AND user_id = ?""",
            (tomorrow, item_id, user_id),
        ).rowcount

        if updated == 0:
            for modality in ("reading", "listening", "speaking", "ime"):
                conn.execute(
                    """INSERT OR IGNORE INTO progress
                       (user_id, content_item_id, modality, suspended_until)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, item_id, modality, tomorrow),
                )

        conn.commit()
        return jsonify({"status": "buried", "item_id": item_id, "until": tomorrow})


@srs_analytics_bp.route("/api/items/<int:item_id>/reschedule", methods=["POST"])
@api_error_handler("ItemReschedule")
def api_item_reschedule(item_id):
    """Reschedule an item to a custom date.

    Body: {"next_review_date": "2026-03-20"}
    """
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    next_date_str = data.get("next_review_date")
    if not next_date_str:
        return jsonify({"error": "next_review_date is required"}), 400

    # Validate date format
    try:
        next_date = date.fromisoformat(next_date_str)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if next_date < date.today():
        return jsonify({"error": "Date must be today or in the future"}), 400

    with db.connection() as conn:
        item = conn.execute(
            "SELECT id FROM content_item WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            return jsonify({"error": "Item not found"}), 404

        updated = conn.execute(
            """UPDATE progress SET next_review_date = ?, suspended_until = NULL
               WHERE content_item_id = ? AND user_id = ?""",
            (next_date.isoformat(), item_id, user_id),
        ).rowcount

        if updated == 0:
            return jsonify({"error": "No progress records for this item"}), 404

        conn.commit()
        return jsonify({
            "status": "rescheduled",
            "item_id": item_id,
            "next_review_date": next_date.isoformat(),
        })


# ── 3. Exam readiness timeline ─────────────────────────────────────────

@srs_analytics_bp.route("/api/analytics/exam-readiness")
@api_error_handler("ExamReadiness")
def api_exam_readiness():
    """Return HSK exam readiness projections for charting.

    Response shape:
    {
        "levels": [
            {
                "hsk_level": 1,
                "coverage_pct": 92.5,
                "projected_date": "2026-04-15",
                "sessions_remaining": 12,
                "confidence": "good",
                "status": "ready" | "in_progress" | "not_started"
            }, ...
        ],
        "pace": { ... },
        "total_sessions": N
    }
    """
    user_id = _get_user_id()
    with db.connection() as conn:
        from ..diagnostics import project_forecast, HSK_CUMULATIVE

        forecast = project_forecast(conn, user_id=user_id)
        pace = forecast.get("pace", {})
        spw = pace.get("sessions_per_week", 0)
        effective_spw = max(spw, 0.5) if pace.get("reliable") else 4.0

        mastery_by_hsk = db.get_mastery_by_hsk(conn, user_id=user_id)

        levels = []
        for hsk_level in range(1, 10):
            target_vocab = HSK_CUMULATIVE.get(hsk_level, hsk_level * 500)
            m = mastery_by_hsk.get(hsk_level, {})
            mastered = m.get("mastered", 0) or 0
            seen = m.get("seen", 0) or 0
            coverage = round(mastered / target_vocab * 100, 1) if target_vocab > 0 else 0.0

            if coverage >= 80:
                status = "ready"
            elif seen > 0:
                status = "in_progress"
            else:
                status = "not_started"

            # Project date from modality projections
            projected_date = None
            sessions_remaining = None
            confidence = pace.get("confidence_label", "insufficient")

            # Use aspirational milestones if available
            aspirational = forecast.get("aspirational", {})
            for key, asp in aspirational.items():
                if isinstance(asp, dict) and asp.get("hsk_target"):
                    target_str = str(asp["hsk_target"])
                    # Match level range like "4-5" or exact "6"
                    if str(hsk_level) in target_str.split("-"):
                        sessions_data = asp.get("sessions", {})
                        expected = sessions_data.get("expected")
                        if expected and effective_spw > 0:
                            weeks = expected / effective_spw
                            projected_date = (
                                date.today() + timedelta(weeks=weeks)
                            ).isoformat()
                            sessions_remaining = expected

            levels.append({
                "hsk_level": hsk_level,
                "coverage_pct": coverage,
                "mastered": mastered,
                "target_vocab": target_vocab,
                "projected_date": projected_date,
                "sessions_remaining": sessions_remaining,
                "confidence": confidence,
                "status": status,
            })

        return jsonify({
            "levels": levels,
            "pace": pace,
            "total_sessions": forecast.get("total_sessions", 0),
        })


# ── 4. Retention forecast calendar ─────────────────────────────────────

@srs_analytics_bp.route("/api/analytics/retention-forecast")
@api_error_handler("RetentionForecast")
def api_retention_forecast():
    """Return items grouped by predicted 'forgotten by' week.

    For each upcoming week (next 8 weeks), lists how many items will drop
    below the retention threshold.
    """
    user_id = _get_user_id()
    weeks_ahead = request.args.get("weeks", 8, type=int)
    weeks_ahead = min(max(1, weeks_ahead), 26)

    with db.connection() as conn:
        from ..retention import predict_recall
        from ..config import INITIAL_HALF_LIFE

        threshold = _get_user_retention_threshold(conn, user_id)

        rows = conn.execute("""
            SELECT p.content_item_id, p.half_life_days, p.last_review_date,
                   ci.hanzi, ci.pinyin, ci.english, ci.hsk_level
            FROM progress p
            JOIN content_item ci ON p.content_item_id = ci.id
            WHERE p.user_id = ?
              AND p.total_attempts > 0
              AND p.half_life_days IS NOT NULL
              AND p.last_review_date IS NOT NULL
              AND (p.suspended_until IS NULL OR p.suspended_until <= date('now'))
        """, (user_id,)).fetchall()

        today = date.today()
        # Build weekly buckets
        weekly_forecast = []
        for week_offset in range(weeks_ahead):
            week_start = today + timedelta(weeks=week_offset)
            week_end = week_start + timedelta(days=6)
            week_items = []

            for r in rows:
                hl = r["half_life_days"] or INITIAL_HALF_LIFE
                try:
                    review_date = date.fromisoformat(r["last_review_date"][:10])
                except (ValueError, TypeError):
                    continue

                # Days from review to end of this week
                days_to_end = max(0, (week_end - review_date).days)
                days_to_start = max(0, (week_start - review_date).days)

                p_at_start = predict_recall(hl, days_to_start)
                p_at_end = predict_recall(hl, days_to_end)

                # Item crosses threshold during this week
                if p_at_start >= threshold and p_at_end < threshold:
                    # Compute exact crossover day
                    crossover_days = -hl * math.log2(threshold) if hl > 0 else 0
                    crossover_date = review_date + timedelta(days=crossover_days)
                    week_items.append({
                        "content_item_id": r["content_item_id"],
                        "hanzi": r["hanzi"],
                        "pinyin": r["pinyin"] or "",
                        "english": r["english"] or "",
                        "hsk_level": r["hsk_level"],
                        "predicted_drop_date": crossover_date.isoformat(),
                        "recall_at_week_end": round(p_at_end, 3),
                    })

            weekly_forecast.append({
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "items_dropping": len(week_items),
                "items": week_items[:20],  # Cap detail at 20 per week
            })

        # Summary
        total_reviewed = len(rows)
        currently_above = 0
        for r in rows:
            hl = r["half_life_days"] or INITIAL_HALF_LIFE
            try:
                review_date = date.fromisoformat(r["last_review_date"][:10])
            except (ValueError, TypeError):
                continue
            days_since = max(0, (today - review_date).days)
            if predict_recall(hl, days_since) >= threshold:
                currently_above += 1

        return jsonify({
            "threshold": threshold,
            "total_reviewed": total_reviewed,
            "currently_above_threshold": currently_above,
            "weekly_forecast": weekly_forecast,
        })


# ── 5. Content import: paste text -> create study items ────────────────

@srs_analytics_bp.route("/api/content/import-text", methods=["POST"])
@api_error_handler("ContentImportText")
def api_content_import_text():
    """Tokenize Chinese text and identify unknown words for study.

    Body: {"text": "...", "create_items": false}

    Returns unknown words found in the corpus. If create_items is true,
    creates new content_item records for words not already in the database
    (only if they have pinyin/english from jieba or corpus lookup).
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    create_items = bool(data.get("create_items", False))

    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(text) > 10000:
        return jsonify({"error": "Text too long (max 10000 characters)"}), 400
    if len(text) < 2:
        return jsonify({"error": "Text too short"}), 400

    user_id = _get_user_id()

    # Tokenize: try jieba, fall back to character-level
    tokens = _tokenize_chinese(text)

    with db.connection() as conn:
        unknown_words = []
        known_words = []
        not_in_db = []

        for word in tokens:
            # Look up in content_item
            row = conn.execute(
                """SELECT ci.id, ci.hanzi, ci.pinyin, ci.english, ci.hsk_level
                   FROM content_item ci
                   WHERE ci.hanzi = ? AND ci.review_status = 'approved'
                   LIMIT 1""",
                (word,),
            ).fetchone()

            if row:
                # Check if user has mastered it
                mastery = conn.execute(
                    """SELECT mastery_stage FROM progress
                       WHERE user_id = ? AND content_item_id = ?
                       AND total_attempts > 0
                       ORDER BY total_correct DESC LIMIT 1""",
                    (user_id, row["id"]),
                ).fetchone()

                stage = mastery["mastery_stage"] if mastery else "unseen"
                entry = {
                    "content_item_id": row["id"],
                    "hanzi": row["hanzi"],
                    "pinyin": row["pinyin"] or "",
                    "english": row["english"] or "",
                    "hsk_level": row["hsk_level"],
                    "stage": stage,
                }
                if stage in ("stable", "durable"):
                    known_words.append(entry)
                else:
                    unknown_words.append(entry)
            else:
                not_in_db.append(word)

        created_count = 0
        if create_items and not_in_db:
            # Try to create items from dictionary_entry table
            for word in not_in_db[:50]:  # Cap at 50
                dict_row = conn.execute(
                    """SELECT simplified, pinyin, english
                       FROM dictionary_entry
                       WHERE simplified = ?
                       LIMIT 1""",
                    (word,),
                ).fetchone()
                if dict_row and dict_row["pinyin"] and dict_row["english"]:
                    try:
                        conn.execute(
                            """INSERT OR IGNORE INTO content_item
                               (hanzi, pinyin, english, item_type, source,
                                review_status, status)
                               VALUES (?, ?, ?, 'vocab', 'user_import',
                                       'approved', 'drill_ready')""",
                            (dict_row["simplified"], dict_row["pinyin"],
                             dict_row["english"]),
                        )
                        created_count += 1
                    except sqlite3.Error:
                        pass
            conn.commit()

        return jsonify({
            "unknown_words": unknown_words[:100],
            "known_words": known_words[:100],
            "not_in_database": not_in_db[:50],
            "created_count": created_count,
            "summary": {
                "total_tokens": len(tokens),
                "known": len(known_words),
                "unknown_in_corpus": len(unknown_words),
                "not_in_database": len(not_in_db),
            },
        })


def _tokenize_chinese(text: str) -> list:
    """Tokenize Chinese text. Uses jieba if available, else character-level."""
    # Filter to CJK characters only
    cjk_text = "".join(c for c in text if '\u4e00' <= c <= '\u9fff')
    if not cjk_text:
        return []

    try:
        import jieba
        tokens = list(jieba.cut(cjk_text))
        # Filter single-char non-words and dedup while preserving order
        seen = set()
        result = []
        for t in tokens:
            t = t.strip()
            if t and t not in seen and len(t) >= 1:
                seen.add(t)
                result.append(t)
        return result
    except ImportError:
        # Character-level fallback
        seen = set()
        result = []
        for c in cjk_text:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return result


# ── 6. CSV/TSV import ──────────────────────────────────────────────────

@srs_analytics_bp.route("/api/content/import-csv", methods=["POST"])
@api_error_handler("ContentImportCSV")
def api_content_import_csv():
    """Import vocabulary from CSV/TSV data.

    Accepts JSON body: {"csv_data": "hanzi,pinyin,english,hsk_level\\n..."}
    Or multipart file upload with key "file".

    Required columns: hanzi, pinyin, english
    Optional: hsk_level (default 1)

    Returns counts of imported, skipped (duplicate), and errored rows.
    """
    csv_text = None

    # Try JSON body first
    data = request.get_json(silent=True)
    if data and data.get("csv_data"):
        csv_text = data["csv_data"]
    else:
        # Try file upload
        f = request.files.get("file")
        if f:
            try:
                csv_text = f.read().decode("utf-8-sig")
            except (UnicodeDecodeError, AttributeError):
                return jsonify({"error": "Could not decode file as UTF-8"}), 400

    if not csv_text:
        return jsonify({"error": "No CSV data provided. Send csv_data in JSON body or upload a file."}), 400

    if len(csv_text) > 500000:
        return jsonify({"error": "CSV data too large (max 500KB)"}), 400

    # Detect delimiter (tab or comma)
    first_line = csv_text.split("\n")[0]
    delimiter = "\t" if "\t" in first_line else ","

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)

    # Validate header
    fieldnames = reader.fieldnames or []
    fieldnames_lower = [f.lower().strip() for f in fieldnames]
    if "hanzi" not in fieldnames_lower:
        return jsonify({
            "error": "CSV must have a 'hanzi' column. Found: " + ", ".join(fieldnames),
        }), 400

    # Build column index map (case-insensitive)
    col_map = {}
    for orig, lower in zip(fieldnames, fieldnames_lower):
        col_map[lower] = orig

    imported = 0
    skipped = 0
    errors = []

    with db.connection() as conn:
        for row_num, row in enumerate(reader, start=2):  # start=2 (header is row 1)
            try:
                hanzi = (row.get(col_map.get("hanzi", "hanzi")) or "").strip()
                pinyin = (row.get(col_map.get("pinyin", "pinyin")) or "").strip()
                english = (row.get(col_map.get("english", "english")) or "").strip()
                hsk_raw = (row.get(col_map.get("hsk_level", "hsk_level")) or "1").strip()

                if not hanzi:
                    errors.append({"row": row_num, "error": "missing hanzi"})
                    continue
                if not pinyin:
                    errors.append({"row": row_num, "error": "missing pinyin", "hanzi": hanzi})
                    continue
                if not english:
                    errors.append({"row": row_num, "error": "missing english", "hanzi": hanzi})
                    continue

                try:
                    hsk_level = int(hsk_raw)
                    if hsk_level < 1 or hsk_level > 9:
                        hsk_level = 1
                except ValueError:
                    hsk_level = 1

                # Check duplicate
                existing = conn.execute(
                    "SELECT id FROM content_item WHERE hanzi = ?", (hanzi,)
                ).fetchone()
                if existing:
                    skipped += 1
                    continue

                conn.execute(
                    """INSERT INTO content_item
                       (hanzi, pinyin, english, hsk_level, item_type, source,
                        review_status, status)
                       VALUES (?, ?, ?, ?, 'vocab', 'csv_import',
                               'approved', 'drill_ready')""",
                    (hanzi, pinyin, english, hsk_level),
                )
                imported += 1

            except (KeyError, TypeError, ValueError) as e:
                errors.append({"row": row_num, "error": str(e)})

            if row_num > 1002:  # Cap at 1000 data rows
                break

        conn.commit()

    return jsonify({
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:50],
        "total_processed": imported + skipped + len(errors),
    })


# ── 7. Grammar highlights in reading passages ──────────────────────────

@srs_analytics_bp.route("/api/reading/passage/<passage_id>/grammar")
@api_error_handler("PassageGrammar")
def api_passage_grammar(passage_id):
    """Return grammar patterns found in a reading passage.

    Matches grammar_point patterns against the passage text_zh.
    Returns grammar points with their locations in the text.
    """
    from ..media import load_reading_passages

    passages = load_reading_passages()
    passage = next((p for p in passages if p.get("id") == passage_id), None)
    if not passage:
        return jsonify({"error": "Passage not found"}), 404

    text_zh = passage.get("text_zh", "")
    hsk_level = passage.get("hsk_level", 1)

    with db.connection() as conn:
        # Get grammar points at or below the passage's HSK level
        grammar_rows = conn.execute("""
            SELECT id, name, name_zh, hsk_level, category, description,
                   examples_json
            FROM grammar_point
            WHERE hsk_level <= ?
            ORDER BY hsk_level ASC
        """, (hsk_level + 1,)).fetchall()

        highlights = []
        for gp in grammar_rows:
            # Check if any example patterns appear in the text
            name_zh = gp["name_zh"] or ""
            # Try matching the grammar name_zh in the passage text
            if name_zh and name_zh in text_zh:
                highlights.append({
                    "grammar_point_id": gp["id"],
                    "name": gp["name"],
                    "name_zh": name_zh,
                    "hsk_level": gp["hsk_level"],
                    "category": gp["category"],
                    "description": gp["description"] or "",
                    "match_text": name_zh,
                })
                continue

            # Also check example sentences for pattern fragments
            examples = []
            try:
                import json
                examples = json.loads(gp["examples_json"] or "[]")
            except (ValueError, TypeError):
                pass

            for ex in examples:
                pattern = ""
                if isinstance(ex, dict):
                    pattern = ex.get("pattern_zh") or ex.get("zh") or ""
                elif isinstance(ex, str):
                    pattern = ex

                if pattern and len(pattern) >= 2 and pattern in text_zh:
                    highlights.append({
                        "grammar_point_id": gp["id"],
                        "name": gp["name"],
                        "name_zh": name_zh,
                        "hsk_level": gp["hsk_level"],
                        "category": gp["category"],
                        "description": gp["description"] or "",
                        "match_text": pattern,
                    })
                    break  # One match per grammar point is enough

        # Deduplicate by grammar_point_id
        seen_ids = set()
        unique_highlights = []
        for h in highlights:
            if h["grammar_point_id"] not in seen_ids:
                seen_ids.add(h["grammar_point_id"])
                unique_highlights.append(h)

        return jsonify({
            "passage_id": passage_id,
            "grammar_highlights": unique_highlights,
            "count": len(unique_highlights),
        })


# ── 8. Reading content quality flag / source_type filter ───────────────

@srs_analytics_bp.route("/api/reading/passages/filtered")
@api_error_handler("ReadingPassagesFiltered")
def api_reading_passages_filtered():
    """Return reading passages with optional source_type filter.

    Query params:
        source_type: 'human_authored' | 'ai_generated' | 'template_generated'
        hsk_level: int (optional)

    Each passage includes a source_type field derived from its ID pattern.
    """
    from ..media import load_reading_passages

    hsk_level = request.args.get("hsk_level", type=int)
    source_type_filter = request.args.get("source_type", "").strip()
    valid_source_types = ("human_authored", "ai_generated", "template_generated")
    if source_type_filter and source_type_filter not in valid_source_types:
        return jsonify({
            "error": f"Invalid source_type. Must be one of: {', '.join(valid_source_types)}"
        }), 400

    passages = load_reading_passages(hsk_level)

    result = []
    for p in passages:
        st = _infer_source_type(p)
        if source_type_filter and st != source_type_filter:
            continue
        result.append({
            "id": p.get("id", ""),
            "title": p.get("title", ""),
            "title_zh": p.get("title_zh", ""),
            "hsk_level": p.get("hsk_level", 1),
            "source_type": st,
        })

    return jsonify({"passages": result, "count": len(result)})


def _infer_source_type(passage: dict) -> str:
    """Infer content source type from passage metadata.

    Convention:
    - IDs containing 'gen_' or 'generated' -> ai_generated
    - IDs containing 'tmpl_' or 'template' -> template_generated
    - Passages with source field containing 'ollama' or 'ai' -> ai_generated
    - Everything else -> human_authored
    """
    pid = (passage.get("id") or "").lower()
    source = (passage.get("source") or "").lower()

    if "gen_" in pid or "generated" in pid or "ollama" in source or "ai" in source:
        return "ai_generated"
    if "tmpl_" in pid or "template" in pid or "template" in source:
        return "template_generated"
    return "human_authored"
