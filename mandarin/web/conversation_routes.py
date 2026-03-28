"""Conversation drill routes — guided speaking practice via API."""

import logging

from flask import Blueprint, jsonify, request

from .. import db
from .api_errors import api_error_handler
from .middleware import _get_user_id

logger = logging.getLogger(__name__)

conversation_bp = Blueprint("conversation", __name__)


@conversation_bp.route("/api/conversation/scenarios")
@api_error_handler("ConversationScenarios")
def api_conversation_scenarios():
    """List available conversation scenarios.

    Query params:
        hsk_level (int, optional): Filter to a specific HSK level.
    """
    from ..ai.conversation_drill import list_scenarios
    hsk_level = request.args.get("hsk_level", type=int)
    scenarios = list_scenarios(hsk_level=hsk_level)
    return jsonify({"scenarios": scenarios})


@conversation_bp.route("/api/conversation/start", methods=["POST"])
@api_error_handler("ConversationStart")
def api_conversation_start():
    """Start a new conversation drill.

    Body (JSON):
        hsk_level (int, optional): Target HSK level (default 2).
        scenario_id (str, optional): Specific scenario to use.

    Returns scenario details with the opening prompt.
    """
    data = request.get_json(silent=True) or {}
    hsk_level = data.get("hsk_level", 2)

    with db.connection() as conn:
        from ..ai.conversation_drill import get_scenario, SCENARIOS

        scenario_id = data.get("scenario_id")
        if scenario_id:
            # Find specific scenario
            scenario = None
            for level_scenarios in SCENARIOS.values():
                for s in level_scenarios:
                    if s["id"] == scenario_id:
                        scenario = s
                        break
                if scenario:
                    break
        else:
            scenario = get_scenario(conn, hsk_level=hsk_level)

    if not scenario:
        return jsonify({"error": "No scenarios available"}), 404

    return jsonify({
        "scenario_id": scenario["id"],
        "hsk_level": scenario.get("hsk_level", hsk_level),
        "scenario": {
            "id": scenario["id"],
            "title": scenario["title"],
            "title_zh": scenario["title_zh"],
            "situation": scenario["situation"],
            "prompt_zh": scenario["prompt_zh"],
            "prompt_pinyin": scenario["prompt_pinyin"],
            "prompt_en": scenario["prompt_en"],
            "expected_patterns": scenario.get("expected_patterns", []),
            "grammar_points": scenario.get("grammar_points", []),
            "hsk_level": scenario.get("hsk_level", hsk_level),
        },
        "situation": scenario["situation"],
        "prompt_zh": scenario["prompt_zh"],
        "prompt_pinyin": scenario["prompt_pinyin"],
        "prompt_en": scenario["prompt_en"],
    })


@conversation_bp.route("/api/conversation/respond", methods=["POST"])
@api_error_handler("ConversationRespond")
def api_conversation_respond():
    """Submit a response to a conversation prompt and get evaluation.

    Body (JSON):
        scenario_id (str): The scenario being practiced.
        user_response (str): The learner's response text (typed or transcribed).
        hsk_level (int, optional): Learner's HSK level.

    Returns evaluation with grammar notes, follow-up, and rating.
    """
    data = request.get_json(silent=True) or {}
    scenario_id = data.get("scenario_id")
    user_response = (data.get("user_response") or "").strip()

    if not scenario_id:
        return jsonify({"error": "scenario_id is required"}), 400
    if not user_response:
        return jsonify({"error": "user_response is required"}), 400

    hsk_level = data.get("hsk_level", 2)

    # Find the scenario
    from ..ai.conversation_drill import SCENARIOS, evaluate_response
    scenario = None
    for level_scenarios in SCENARIOS.values():
        for s in level_scenarios:
            if s["id"] == scenario_id:
                scenario = s
                break
        if scenario:
            break

    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404

    with db.connection() as conn:
        evaluation = evaluate_response(
            conn, scenario, user_response, hsk_level=hsk_level,
        )

    return jsonify({"evaluation": evaluation})


@conversation_bp.route("/api/conversation/continue", methods=["POST"])
@api_error_handler("ConversationContinue")
def api_conversation_continue():
    """Continue an ongoing conversation with a follow-up.

    Body (JSON):
        scenario_id (str): The scenario being practiced.
        history (list): Conversation history [{role, text}, ...].
        hsk_level (int, optional): Learner's HSK level.

    Returns the tutor's next line.
    """
    data = request.get_json(silent=True) or {}
    scenario_id = data.get("scenario_id")
    history = data.get("history", [])

    if not scenario_id:
        return jsonify({"error": "scenario_id is required"}), 400

    from ..ai.conversation_drill import SCENARIOS, generate_follow_up
    scenario = None
    for level_scenarios in SCENARIOS.values():
        for s in level_scenarios:
            if s["id"] == scenario_id:
                scenario = s
                break
        if scenario:
            break

    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404

    hsk_level = data.get("hsk_level", 2)

    with db.connection() as conn:
        follow_up = generate_follow_up(
            conn, scenario, history, hsk_level=hsk_level,
        )

    return jsonify({"follow_up": follow_up})


# ── Scaffolding endpoints (FMEA #4: difficulty anxiety) ──────────────

@conversation_bp.route("/api/conversation/hint", methods=["POST"])
@api_error_handler("ConversationHint")
def api_conversation_hint():
    """Get a structural hint for the current conversation turn.

    Returns a suggested response structure (not the answer) to reduce
    difficulty anxiety and help learners get started.

    Body (JSON):
        scenario_id (str): The scenario being practiced.
    """
    data = request.get_json(silent=True) or {}
    scenario_id = data.get("scenario_id")

    from ..ai.conversation_drill import SCENARIOS
    scenario = None
    if scenario_id:
        for level_scenarios in SCENARIOS.values():
            for s in level_scenarios:
                if s["id"] == scenario_id:
                    scenario = s
                    break
            if scenario:
                break

    # Build a structural hint from the scenario's expected patterns
    hint_parts = []
    if scenario:
        patterns = scenario.get("expected_patterns", [])
        grammar = scenario.get("grammar_points", [])
        if patterns:
            hint_parts.append("Try using: " + ", ".join(patterns[:3]))
        if grammar:
            hint_parts.append("Grammar pattern: " + ", ".join(grammar[:2]))
        if not hint_parts:
            hint_parts.append("Start with the subject, then add the verb and object.")
    else:
        hint_parts.append("Use a simple sentence: subject + verb + object.")

    hint_parts.append("It is fine to keep it short.")

    return jsonify({"hint": " ".join(hint_parts)})


@conversation_bp.route("/api/conversation/simplify", methods=["POST"])
@api_error_handler("ConversationSimplify")
def api_conversation_simplify():
    """Simplify the tutor's last message to a lower level.

    Returns a simplified version with full pinyin and translation
    to reduce comprehension anxiety.

    Body (JSON):
        scenario_id (str): The scenario being practiced.
        text (str): The text to simplify.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"simplified": "", "pinyin": "", "english": ""})

    # Try to generate a simplified version using pypinyin for pinyin
    pinyin_text = ""
    try:
        from pypinyin import pinyin, Style
        syllables = pinyin(text, style=Style.TONE)
        pinyin_text = " ".join(s[0] for s in syllables)
    except (ImportError, Exception):
        pinyin_text = ""

    # For simplification, we return the same text with pinyin annotation
    # A more advanced version could use an LLM to rephrase at a lower level
    return jsonify({
        "simplified": text,
        "pinyin": pinyin_text,
        "english": "",  # Would need LLM for translation; omit for now
    })


# ── Whisper transcription endpoint ──────────────────

@conversation_bp.route("/api/conversation/transcribe", methods=["POST"])
@api_error_handler("ConversationTranscribe")
def api_conversation_transcribe():
    """Transcribe uploaded audio to text via Whisper.

    Accepts multipart/form-data with an 'audio' file field.
    Returns transcription result.
    """
    if "audio" not in request.files:
        return jsonify({"error": "audio file is required"}), 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify({"error": "empty filename"}), 400

    import tempfile
    import os

    # Save to temp file
    suffix = os.path.splitext(audio_file.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio_file.save(tmp)
        tmp_path = tmp.name

    try:
        from ..ai.whisper_stt import transcribe, is_whisper_available

        if not is_whisper_available():
            return jsonify({
                "success": False,
                "error": "No Whisper backend available",
                "text": "",
            })

        result = transcribe(tmp_path, language="zh")

        return jsonify({
            "success": result.success,
            "text": result.text,
            "language": result.language,
            "confidence": result.confidence,
            "backend": result.backend,
            "duration_ms": result.duration_ms,
            "segments": [
                {
                    "text": s.text,
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                }
                for s in result.segments
            ],
        })
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
