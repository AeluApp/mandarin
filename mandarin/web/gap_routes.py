"""Routes for previously-deferred features: OCR, widget, study lists."""

import json
import logging
import secrets
import sqlite3

from flask import Blueprint, jsonify, request
from flask_login import current_user

from .. import db
from .api_errors import api_error_handler
from .middleware import _get_user_id, _compute_streak

logger = logging.getLogger(__name__)

gap_bp = Blueprint("gap", __name__)


# ── OCR Dictionary Lookup ────────────────────────────────────────────

@gap_bp.route("/api/dictionary/ocr", methods=["POST"])
@api_error_handler("DictionaryOCR")
def api_dictionary_ocr():
    """Accept a base64-encoded image, run OCR to detect hanzi, return definitions.

    Uses pytesseract if available; returns graceful fallback otherwise.
    Request JSON: {image_base64: "...", format: "jpeg"}
    Response JSON: {hanzi: "...", definitions: [...]} or {error: "..."}
    """
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image_base64", "")
    if not image_b64:
        return jsonify({"error": "No image data provided"}), 400

    # Cap image size at 2MB base64
    if len(image_b64) > 2 * 1024 * 1024:
        return jsonify({"error": "Image too large (max 2MB)"}), 400

    # Attempt OCR
    try:
        import pytesseract
        from PIL import Image
        import base64
        import io

        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes))

        # Run tesseract with Chinese simplified language pack
        detected_text = pytesseract.image_to_string(img, lang="chi_sim")
        detected_text = detected_text.strip()

        if not detected_text:
            return jsonify({"error": "No text detected in image"}), 200

        # Extract only Chinese characters
        import re
        hanzi_chars = re.findall(r'[\u4e00-\u9fff]+', detected_text)
        hanzi = "".join(hanzi_chars)

        if not hanzi:
            return jsonify({"error": "No Chinese characters detected"}), 200

        # Look up definitions
        definitions = []
        with db.connection() as conn:
            for char_group in hanzi_chars[:10]:  # Limit to first 10 groups
                row = conn.execute(
                    "SELECT hanzi, pinyin, english FROM content_item WHERE hanzi = ? LIMIT 1",
                    (char_group,),
                ).fetchone()
                if row:
                    definitions.append({
                        "hanzi": row["hanzi"],
                        "pinyin": row["pinyin"],
                        "english": row["english"],
                    })

        return jsonify({
            "hanzi": hanzi,
            "raw_text": detected_text,
            "definitions": definitions,
        })

    except ImportError:
        return jsonify({
            "error": "OCR not available. Install pytesseract and Pillow: "
                     "pip install pytesseract Pillow",
            "ocr_available": False,
        }), 200
    except Exception as e:
        logger.warning("OCR processing failed: %s", e, exc_info=True)
        return jsonify({"error": f"OCR processing failed: {type(e).__name__}"}), 500


# ── iOS Widget Data Endpoint ─────────────────────────────────────────

@gap_bp.route("/api/widget/data")
@api_error_handler("WidgetData")
def api_widget_data():
    """Return minimal JSON for an iOS Home Screen widget.

    Returns: {due_count, streak_days, next_review_in_minutes, accuracy_today}
    Lightweight — no heavy DB joins. Uses current_user if authenticated,
    otherwise returns safe defaults.
    """
    user_id = None
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
    except (AttributeError, RuntimeError):
        pass

    if not user_id:
        # Unauthenticated fallback — still useful for widget skeleton
        return jsonify({
            "due_count": 0,
            "streak_days": 0,
            "next_review_in_minutes": None,
            "accuracy_today": None,
            "authenticated": False,
        })

    try:
        with db.connection() as conn:
            # Due count: items where next_review_date <= now
            due_row = conn.execute(
                """SELECT COUNT(*) as cnt FROM progress
                   WHERE user_id = ? AND next_review_date <= datetime('now')""",
                (user_id,),
            ).fetchone()
            due_count = due_row["cnt"] if due_row else 0

            # Streak
            streak_days = _compute_streak(conn, user_id=user_id)

            # Next review: minutes until next due item
            next_row = conn.execute(
                """SELECT MIN(next_review_date) as next_due FROM progress
                   WHERE user_id = ? AND next_review_date > datetime('now')""",
                (user_id,),
            ).fetchone()
            next_review_minutes = None
            if next_row and next_row["next_due"]:
                from datetime import datetime, timezone
                try:
                    next_dt = datetime.fromisoformat(next_row["next_due"])
                    now = datetime.now(timezone.utc)
                    if next_dt.tzinfo is None:
                        next_dt = next_dt.replace(tzinfo=timezone.utc)
                    diff = (next_dt - now).total_seconds() / 60
                    next_review_minutes = max(0, round(diff))
                except (ValueError, TypeError):
                    pass

            # Accuracy today
            today_row = conn.execute(
                """SELECT
                     SUM(items_completed) as total,
                     SUM(items_correct) as correct
                   FROM session_log
                   WHERE user_id = ?
                     AND date(start_time) = date('now')""",
                (user_id,),
            ).fetchone()
            accuracy_today = None
            if today_row and (today_row["total"] or 0) > 0:
                accuracy_today = round(
                    (today_row["correct"] or 0) / today_row["total"] * 100
                )

            return jsonify({
                "due_count": due_count,
                "streak_days": streak_days,
                "next_review_in_minutes": next_review_minutes,
                "accuracy_today": accuracy_today,
                "authenticated": True,
            })

    except sqlite3.Error as e:
        logger.warning("widget data query failed: %s", e)
        return jsonify({
            "due_count": 0,
            "streak_days": 0,
            "next_review_in_minutes": None,
            "accuracy_today": None,
            "authenticated": True,
            "error": "temporary",
        })


# ── Shareable Study Lists ────────────────────────────────────────────

@gap_bp.route("/api/study-lists", methods=["POST"])
@api_error_handler("StudyListCreate")
def api_create_study_list():
    """Create a new study list.

    Request JSON: {name, description?, item_ids: [int], public?: bool}
    """
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}

    name = (str(data.get("name") or "")).strip()
    if not name or len(name) > 200:
        return jsonify({"error": "Name is required (max 200 chars)"}), 400

    description = (str(data.get("description") or "")).strip()[:1000]
    item_ids = data.get("item_ids", [])
    if not isinstance(item_ids, list):
        return jsonify({"error": "item_ids must be a list"}), 400
    # Validate item IDs are integers
    try:
        item_ids = [int(i) for i in item_ids]
    except (ValueError, TypeError):
        return jsonify({"error": "item_ids must contain integers"}), 400

    is_public = bool(data.get("public", False))
    share_code = secrets.token_urlsafe(12) if is_public else None

    try:
        with db.connection() as conn:
            # Verify item_ids exist
            if item_ids:
                placeholders = ",".join("?" * len(item_ids))
                existing = conn.execute(
                    f"SELECT id FROM content_item WHERE id IN ({placeholders})",
                    item_ids,
                ).fetchall()
                existing_ids = {r["id"] for r in existing}
                item_ids = [i for i in item_ids if i in existing_ids]

            cursor = conn.execute(
                """INSERT INTO study_list (user_id, name, description, item_ids, public, share_code)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, name, description, json.dumps(item_ids),
                 1 if is_public else 0, share_code),
            )
            conn.commit()
            list_id = cursor.lastrowid

            return jsonify({
                "id": list_id,
                "name": name,
                "description": description,
                "item_ids": item_ids,
                "public": is_public,
                "share_code": share_code,
            }), 201

    except sqlite3.Error as e:
        logger.warning("study list creation failed: %s", e)
        return jsonify({"error": "Could not create study list"}), 500


@gap_bp.route("/api/study-lists", methods=["GET"])
@api_error_handler("StudyListGet")
def api_get_study_lists():
    """Get the current user's study lists."""
    user_id = _get_user_id()
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT id, name, description, item_ids, public, share_code, created_at
                   FROM study_list WHERE user_id = ?
                   ORDER BY created_at DESC""",
                (user_id,),
            ).fetchall()

            lists = []
            for r in rows:
                try:
                    ids = json.loads(r["item_ids"])
                except (json.JSONDecodeError, TypeError):
                    ids = []
                lists.append({
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"] or "",
                    "item_count": len(ids),
                    "item_ids": ids,
                    "public": bool(r["public"]),
                    "share_code": r["share_code"],
                    "created_at": r["created_at"],
                })

            return jsonify({"lists": lists})

    except sqlite3.Error as e:
        logger.warning("study lists query failed: %s", e)
        return jsonify({"lists": []})


@gap_bp.route("/api/study-lists/shared/<code>")
@api_error_handler("StudyListShared")
def api_get_shared_list(code):
    """Get a shared study list by share code. No auth required."""
    if not code or len(code) > 50:
        return jsonify({"error": "Invalid share code"}), 400

    try:
        with db.connection() as conn:
            row = conn.execute(
                """SELECT sl.id, sl.name, sl.description, sl.item_ids,
                          sl.created_at, u.display_name as author
                   FROM study_list sl
                   LEFT JOIN user u ON u.id = sl.user_id
                   WHERE sl.share_code = ? AND sl.public = 1""",
                (code,),
            ).fetchone()

            if not row:
                return jsonify({"error": "Study list not found"}), 404

            try:
                ids = json.loads(row["item_ids"])
            except (json.JSONDecodeError, TypeError):
                ids = []

            # Fetch item details
            items = []
            if ids:
                placeholders = ",".join("?" * len(ids))
                item_rows = conn.execute(
                    f"""SELECT id, hanzi, pinyin, english, hsk_level
                        FROM content_item WHERE id IN ({placeholders})""",
                    ids,
                ).fetchall()
                items = [dict(r) for r in item_rows]

            return jsonify({
                "id": row["id"],
                "name": row["name"],
                "description": row["description"] or "",
                "author": row["author"] or "Anonymous",
                "items": items,
                "item_count": len(items),
                "created_at": row["created_at"],
            })

    except sqlite3.Error as e:
        logger.warning("shared list query failed: %s", e)
        return jsonify({"error": "Could not load shared list"}), 500


@gap_bp.route("/api/study-lists/<int:list_id>/import", methods=["POST"])
@api_error_handler("StudyListImport")
def api_import_study_list(list_id):
    """Import a shared study list's items into the current user's progress.

    Creates progress entries for items the user hasn't seen yet.
    """
    user_id = _get_user_id()

    try:
        with db.connection() as conn:
            # Fetch the list (must be public or owned by user)
            row = conn.execute(
                """SELECT item_ids FROM study_list
                   WHERE id = ? AND (public = 1 OR user_id = ?)""",
                (list_id, user_id),
            ).fetchone()

            if not row:
                return jsonify({"error": "Study list not found or not accessible"}), 404

            try:
                ids = json.loads(row["item_ids"])
            except (json.JSONDecodeError, TypeError):
                ids = []

            if not ids:
                return jsonify({"imported": 0, "skipped": 0})

            imported = 0
            skipped = 0

            for item_id in ids:
                # Check if progress already exists for this user+item (any modality)
                exists = conn.execute(
                    """SELECT 1 FROM progress
                       WHERE user_id = ? AND content_item_id = ?
                       LIMIT 1""",
                    (user_id, item_id),
                ).fetchone()

                if exists:
                    skipped += 1
                    continue

                # Create a reading progress entry (default modality for imports)
                try:
                    conn.execute(
                        """INSERT INTO progress (user_id, content_item_id, modality,
                                                 next_review_date, mastery_stage)
                           VALUES (?, ?, 'reading', datetime('now'), 'unseen')""",
                        (user_id, item_id),
                    )
                    imported += 1
                except sqlite3.IntegrityError:
                    skipped += 1

            conn.commit()
            return jsonify({"imported": imported, "skipped": skipped})

    except sqlite3.Error as e:
        logger.warning("study list import failed: %s", e)
        return jsonify({"error": "Import failed"}), 500
