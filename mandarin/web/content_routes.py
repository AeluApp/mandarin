"""Content management routes — gap detection and reading generation."""

import logging

from flask import Blueprint, jsonify, request

from .. import db
from .api_errors import api_error_handler
from .middleware import _get_user_id

logger = logging.getLogger(__name__)

content_bp = Blueprint("content_mgmt", __name__)


@content_bp.route("/api/content/gaps")
@api_error_handler("ContentGaps")
def api_content_gaps():
    """Run full content gap analysis.

    Returns coverage scores for HSK levels, grammar, reading, media,
    and actionable recommendations.
    """
    with db.connection() as conn:
        from ..ai.content_gap_detector import detect_gaps
        report = detect_gaps(conn)

    return jsonify(report)


@content_bp.route("/api/content/gaps/user")
@api_error_handler("ContentUserGaps")
def api_content_user_gaps():
    """Detect content gaps relative to the current user's progress.

    Shows areas where the user is studying but content is thin.
    """
    user_id = _get_user_id()

    with db.connection() as conn:
        from ..ai.content_gap_detector import detect_user_gaps
        report = detect_user_gaps(conn, user_id)

    return jsonify(report)


@content_bp.route("/api/reading/generate", methods=["POST"])
@api_error_handler("ReadingGenerate")
def api_reading_generate():
    """Generate a new reading passage on demand.

    Body (JSON):
        hsk_level (int, optional): Target HSK level (default 2).
        topic (str, optional): Topic hint.
        vocabulary (list, optional): Words to include.

    Requires Ollama. Returns generated passage or error.
    """
    data = request.get_json(silent=True) or {}
    hsk_level = data.get("hsk_level", 2)
    topic = data.get("topic", "")
    vocabulary = data.get("vocabulary", [])

    with db.connection() as conn:
        from ..ai.reading_content import generate_reading_passage
        passage = generate_reading_passage(
            conn,
            target_hsk_level=hsk_level,
            target_vocabulary=vocabulary,
            topic=topic,
        )

    if passage is None:
        return jsonify({
            "error": "Could not generate passage. Ollama may be unavailable.",
        }), 503

    return jsonify({"passage": passage})


@content_bp.route("/api/reading/comprehension", methods=["POST"])
@api_error_handler("ReadingComprehension")
def api_reading_comprehension():
    """Generate comprehension questions for a reading passage.

    Body (JSON):
        text_zh (str): The Chinese text to generate questions for.
        hsk_level (int, optional): Target difficulty.

    Returns questions with answers. Deterministic when Ollama unavailable.
    """
    data = request.get_json(silent=True) or {}
    text_zh = (data.get("text_zh") or "").strip()
    if not text_zh:
        return jsonify({"error": "text_zh is required"}), 400

    # NIST AI RMF: input length validation on Chinese text endpoints
    if len(text_zh) > 2000:
        return jsonify({"error": "text_zh exceeds maximum length of 2000 characters"}), 400

    hsk_level = data.get("hsk_level", 2)

    questions = _generate_comprehension_questions(text_zh, hsk_level)
    return jsonify({"questions": questions})


def _generate_comprehension_questions(text_zh: str, hsk_level: int) -> list:
    """Generate comprehension questions for Chinese text.

    Deterministic: extracts question types based on content analysis.
    """
    questions = []

    # Gist question (always)
    questions.append({
        "type": "gist",
        "question_zh": "这篇文章主要说了什么？",
        "question_en": "What is this passage mainly about?",
    })

    # Detail questions based on content patterns
    import re

    # Number detection
    if re.search(r'[一二三四五六七八九十百千万亿\d]+', text_zh):
        questions.append({
            "type": "detail",
            "question_zh": "文章中提到了什么数字？",
            "question_en": "What numbers are mentioned?",
        })

    # Time/date detection
    time_words = ["今天", "昨天", "明天", "早上", "下午", "晚上", "星期", "月", "年"]
    if any(w in text_zh for w in time_words):
        questions.append({
            "type": "detail",
            "question_zh": "这件事什么时候发生的？",
            "question_en": "When did this happen?",
        })

    # Person detection
    person_markers = ["他", "她", "我", "老师", "朋友", "同学", "妈妈", "爸爸"]
    if any(w in text_zh for w in person_markers):
        questions.append({
            "type": "detail",
            "question_zh": "文章中提到了谁？",
            "question_en": "Who is mentioned in the passage?",
        })

    # Location detection
    location_words = ["学校", "医院", "公司", "家", "图书馆", "商店", "餐厅"]
    if any(w in text_zh for w in location_words):
        questions.append({
            "type": "detail",
            "question_zh": "这件事在什么地方？",
            "question_en": "Where does this take place?",
        })

    # Cause/reason detection (HSK 2+)
    if hsk_level >= 2 and ("因为" in text_zh or "所以" in text_zh):
        questions.append({
            "type": "inference",
            "question_zh": "为什么会这样？",
            "question_en": "Why did this happen?",
        })

    # Opinion/feeling detection (HSK 2+)
    feeling_words = ["觉得", "认为", "喜欢", "讨厌", "高兴", "难过", "担心"]
    if hsk_level >= 2 and any(w in text_zh for w in feeling_words):
        questions.append({
            "type": "inference",
            "question_zh": "文章中的人有什么感受？",
            "question_en": "How does the person feel?",
        })

    return questions[:5]  # Cap at 5 questions
