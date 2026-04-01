"""Content Quality Analyzer — measures and grades every content dimension.

Runs entirely deterministic by default. Optional Qwen2.5 calls via Ollama
for authenticity/naturalness assessment (falls back to score 60 if unavailable).

All DB queries are wrapped in try/except for graceful degradation when
tables don't exist yet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Optional

from .ollama_client import generate, is_ollama_available, OllamaResponse
from mandarin._paths import DATA_DIR

logger = logging.getLogger(__name__)

# ── Grade mapping ────────────────────────────────────────────────────────

_GRADE_THRESHOLDS = [(90, "A"), (80, "B"), (70, "C"), (60, "D")]


def _score_to_grade(score: float) -> str:
    """Map numeric 0-100 score to letter grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ── Standard finding format ──────────────────────────────────────────────

def _make_finding(
    dimension: str,
    title: str,
    severity: str,
    detail: str,
    recommendation: str,
) -> dict:
    """Create a standardized finding dict.

    severity: 'critical' | 'warning' | 'info'
    """
    return {
        "dimension": dimension,
        "title": title,
        "severity": severity,
        "detail": detail,
        "recommendation": recommendation,
    }


# ── Helpers ──────────────────────────────────────────────────────────────

def _get_stabilized_vocab(conn, user_id: int = 1) -> set[str]:
    """Return set of hanzi strings the learner has stabilized (mastery >= 'familiar')."""
    try:
        rows = conn.execute(
            """SELECT DISTINCT ci.hanzi
               FROM progress p
               JOIN content_item ci ON ci.id = p.content_item_id
               WHERE p.user_id = ?
                 AND p.mastery_stage IN ('familiar', 'strong', 'mature', 'mined_out')
            """,
            (user_id,),
        ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        logger.debug("_get_stabilized_vocab failed", exc_info=True)
        return set()


def _tokenize_chinese(text: str) -> list[str]:
    """Split Chinese text into words. Uses jieba if available, char-level fallback."""
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        # Char-level fallback: each CJK character is a token
        return [ch for ch in text if '\u4e00' <= ch <= '\u9fff']


def _safe_query(conn, sql: str, params: tuple = ()) -> list:
    """Execute SQL and return rows, returning [] on any error."""
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        logger.debug("Query failed: %s", sql[:80], exc_info=True)
        return []


def _safe_query_one(conn, sql: str, params: tuple = ()):
    """Execute SQL and return single row, returning None on any error."""
    try:
        return conn.execute(sql, params).fetchone()
    except Exception:
        logger.debug("Query failed: %s", sql[:80], exc_info=True)
        return None


# ── Authenticity via Qwen2.5 (cached, optional) ─────────────────────────

_AUTHENTICITY_SYSTEM = """You are a native Mandarin speaker reviewing learning content.
Rate the naturalness of the following Chinese text on a scale of 0-100.
Consider: Does it sound natural? Would a native speaker say this? Is the register consistent?
Respond with ONLY a JSON object: {"score": <int>, "issues": ["..."]}.
No markdown fences."""


def _assess_authenticity_llm(text: str, conn=None) -> dict:
    """Ask Qwen2.5 to rate authenticity. Returns {"score": int, "issues": list}."""
    if not is_ollama_available():
        return {"score": 60, "issues": ["assessment unavailable: Ollama offline"]}

    response = generate(
        prompt=f"Rate the naturalness of this Chinese text:\n\n{text}",
        system=_AUTHENTICITY_SYSTEM,
        temperature=0.3,
        max_tokens=256,
        use_cache=True,
        conn=conn,
        task_type="content_quality_authenticity",
    )

    if not response.success:
        return {"score": 60, "issues": ["assessment unavailable: generation failed"]}

    try:
        cleaned = response.text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        data = json.loads(cleaned.strip())
        score = max(0, min(100, int(data.get("score", 60))))
        issues = data.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        return {"score": score, "issues": issues}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"score": 60, "issues": ["assessment unavailable: parse error"]}


# ── Individual assessment functions ──────────────────────────────────────

def assess_passage_quality(conn, passage_id: str, user_id: int = 1) -> dict:
    """Assess quality of a reading passage.

    Dimensions: vocabulary density, authenticity, question quality,
    content lens connection, acquisition outcome.
    Returns dict with overall_score (0-100), dimension_scores, grade.
    """
    dimension_scores = {}

    # Load passage data (from reading_passages.json flat file)
    passage = None
    try:
        from pathlib import Path
        passages_path = DATA_DIR / "reading_passages.json"
        if passages_path.exists():
            with open(passages_path, encoding="utf-8") as f:
                raw = json.load(f)
            # Handle both formats: list or {"passages": [...]}
            if isinstance(raw, dict):
                passages = raw.get("passages", [])
            elif isinstance(raw, list):
                passages = raw
            else:
                passages = []
            for p in passages:
                if not isinstance(p, dict):
                    continue
                pid = p.get("id") or p.get("title", "")
                if str(pid) == str(passage_id):
                    passage = p
                    break
    except Exception:
        logger.debug("Failed to load passage %s", passage_id, exc_info=True)

    if passage is None:
        return {
            "overall_score": 0,
            "dimension_scores": {},
            "grade": "F",
            "error": f"Passage {passage_id} not found",
        }

    body = passage.get("body") or passage.get("text_zh", "")

    # 1. Vocabulary density vs stabilized vocab
    tokens = _tokenize_chinese(body)
    stabilized = _get_stabilized_vocab(conn, user_id)
    if tokens:
        known_count = sum(1 for t in tokens if t in stabilized)
        density_ratio = known_count / len(tokens)
        # Ideal: 85-95% known for i+1 reading. Score peaks at 90% known.
        if 0.85 <= density_ratio <= 0.95:
            dimension_scores["vocabulary_density"] = 95
        elif 0.75 <= density_ratio < 0.85:
            dimension_scores["vocabulary_density"] = 75
        elif density_ratio > 0.95:
            dimension_scores["vocabulary_density"] = 70  # too easy
        else:
            dimension_scores["vocabulary_density"] = max(30, int(density_ratio * 100))
    else:
        dimension_scores["vocabulary_density"] = 50

    # 2. Authenticity (via Qwen2.5 or conservative default)
    authenticity = _assess_authenticity_llm(body, conn=conn)
    dimension_scores["authenticity"] = authenticity["score"]

    # 3. Question quality (from linked comprehension questions)
    questions = passage.get("comprehension_questions") or passage.get("questions", [])
    if not isinstance(questions, list):
        questions = []
    if questions:
        # Score based on count and diversity
        q_score = min(100, 60 + len(questions) * 10)
        dimension_scores["question_quality"] = q_score
    else:
        dimension_scores["question_quality"] = 30

    # 4. Content lens connection
    has_lens = bool(passage.get("content_lens"))
    dimension_scores["content_lens_connection"] = 90 if has_lens else 50

    # 5. Acquisition outcome: did reading this passage drive vocab acquisition?
    rp_rows = _safe_query(
        conn,
        "SELECT words_looked_up, questions_correct, questions_total FROM reading_progress WHERE passage_id = ?",
        (str(passage_id),),
    )
    if rp_rows:
        total_lookups = sum(dict(r).get("words_looked_up", 0) or 0 for r in rp_rows)
        total_correct = sum(dict(r).get("questions_correct", 0) or 0 for r in rp_rows)
        total_q = sum(dict(r).get("questions_total", 0) or 0 for r in rp_rows)
        # Lookups indicate engagement; correct answers indicate comprehension
        engagement = min(100, 50 + total_lookups * 5)
        comprehension = (total_correct / total_q * 100) if total_q > 0 else 50
        dimension_scores["acquisition_outcome"] = int((engagement + comprehension) / 2)
    else:
        dimension_scores["acquisition_outcome"] = 50  # No data yet

    # Overall: weighted average
    weights = {
        "vocabulary_density": 0.25,
        "authenticity": 0.25,
        "question_quality": 0.20,
        "content_lens_connection": 0.10,
        "acquisition_outcome": 0.20,
    }
    overall = sum(dimension_scores.get(k, 50) * w for k, w in weights.items())
    overall = max(0, min(100, int(overall)))

    return {
        "overall_score": overall,
        "dimension_scores": dimension_scores,
        "grade": _score_to_grade(overall),
    }


def assess_grammar_quality(conn, grammar_point_id: int) -> dict:
    """Assess quality of a grammar point entry.

    Dimensions: completeness, example quality, prerequisite coverage,
    content integration, drill linkage.
    """
    dimension_scores = {}

    row = _safe_query_one(
        conn,
        "SELECT * FROM grammar_point WHERE id = ?",
        (grammar_point_id,),
    )

    if row is None:
        return {
            "overall_score": 0,
            "dimension_scores": {},
            "grade": "F",
            "error": f"Grammar point {grammar_point_id} not found",
        }

    gp = dict(row)

    # 1. Completeness: description, examples, category
    completeness = 0
    if gp.get("description"):
        completeness += 30
    examples_json = gp.get("examples_json", "[]")
    try:
        examples = json.loads(examples_json) if examples_json else []
    except (json.JSONDecodeError, TypeError):
        examples = []
    if examples:
        completeness += 20
        # Bonus for multiple examples
        if len(examples) >= 3:
            completeness += 15
    if gp.get("name_zh"):
        completeness += 15
    if gp.get("category") and gp["category"] != "other":
        completeness += 10
    # Cap at 100 with bonus for exceptional completeness
    completeness = min(100, completeness + 10)
    dimension_scores["completeness"] = completeness

    # 2. Example quality: pattern-dependent
    if examples:
        # Check if examples contain both Chinese and explanation
        good_examples = 0
        for ex in examples:
            if isinstance(ex, dict):
                if ex.get("hanzi") or ex.get("zh") or ex.get("chinese"):
                    good_examples += 1
            elif isinstance(ex, str) and any('\u4e00' <= c <= '\u9fff' for c in ex):
                good_examples += 1
        example_ratio = good_examples / len(examples) if examples else 0
        dimension_scores["example_quality"] = int(60 + example_ratio * 40)
    else:
        dimension_scores["example_quality"] = 20

    # 3. Prerequisite coverage: lower HSK items exist?
    hsk = gp.get("hsk_level", 1) or 1
    if hsk <= 1:
        dimension_scores["prerequisite_coverage"] = 100  # No prereqs needed
    else:
        lower_count = _safe_query_one(
            conn,
            "SELECT COUNT(*) FROM grammar_point WHERE hsk_level < ?",
            (hsk,),
        )
        count = lower_count[0] if lower_count else 0
        dimension_scores["prerequisite_coverage"] = min(100, 50 + count * 5)

    # 4. Content integration: appears in passages/dialogues via content_grammar link
    linked = _safe_query_one(
        conn,
        "SELECT COUNT(*) FROM content_grammar WHERE grammar_point_id = ?",
        (grammar_point_id,),
    )
    link_count = linked[0] if linked else 0
    if link_count >= 5:
        dimension_scores["content_integration"] = 95
    elif link_count >= 2:
        dimension_scores["content_integration"] = 75
    elif link_count >= 1:
        dimension_scores["content_integration"] = 55
    else:
        dimension_scores["content_integration"] = 30

    # 5. Drill linkage: grammar progress data exists
    drill_data = _safe_query_one(
        conn,
        "SELECT COUNT(*) FROM grammar_progress WHERE grammar_point_id = ?",
        (grammar_point_id,),
    )
    drill_count = drill_data[0] if drill_data else 0
    dimension_scores["drill_linkage"] = min(100, 40 + drill_count * 20)

    # Overall
    weights = {
        "completeness": 0.30,
        "example_quality": 0.25,
        "prerequisite_coverage": 0.15,
        "content_integration": 0.20,
        "drill_linkage": 0.10,
    }
    overall = sum(dimension_scores.get(k, 50) * w for k, w in weights.items())
    overall = max(0, min(100, int(overall)))

    return {
        "overall_score": overall,
        "dimension_scores": dimension_scores,
        "grade": _score_to_grade(overall),
    }


def assess_question_quality(conn, question_data: dict) -> dict:
    """Assess quality of a comprehension question.

    Dimensions: requires_reading, cognitive_level, distractor quality,
    empirical difficulty.
    """
    dimension_scores = {}

    question_text = question_data.get("question", "")
    answer = question_data.get("answer", "")
    distractors = question_data.get("distractors", [])
    passage_body = question_data.get("passage_body", "")

    # 1. Requires reading: can the question be answered without the passage?
    if passage_body and question_text:
        # Heuristic: if question references specific content from passage
        q_tokens = set(_tokenize_chinese(question_text))
        p_tokens = set(_tokenize_chinese(passage_body))
        overlap = q_tokens & p_tokens
        # Higher overlap = more passage-dependent
        if len(q_tokens) > 0:
            overlap_ratio = len(overlap) / len(q_tokens)
            dimension_scores["requires_reading"] = min(100, int(40 + overlap_ratio * 60))
        else:
            dimension_scores["requires_reading"] = 50
    else:
        dimension_scores["requires_reading"] = 50

    # 2. Cognitive level: recall=40, inference=80, synthesis=100
    # Heuristic based on question words
    q_lower = question_text.lower()
    synthesis_markers = ["why", "compare", "evaluate", "analyze",
                         "为什么", "怎么看", "比较", "分析"]
    inference_markers = ["how", "infer", "suggest", "imply",
                         "说明", "暗示", "推断", "怎么"]
    recall_markers = ["what", "when", "where", "who",
                      "什么", "哪里", "谁", "几"]

    if any(m in q_lower for m in synthesis_markers):
        dimension_scores["cognitive_level"] = 100
    elif any(m in q_lower for m in inference_markers):
        dimension_scores["cognitive_level"] = 80
    elif any(m in q_lower for m in recall_markers):
        dimension_scores["cognitive_level"] = 40
    else:
        dimension_scores["cognitive_level"] = 60

    # 3. Distractor quality
    if distractors:
        unique_distractors = set(str(d).strip() for d in distractors)
        # Check for duplicates
        dup_penalty = 0 if len(unique_distractors) == len(distractors) else 30
        # Check answer not in distractors
        answer_in_dist = any(str(d).strip() == str(answer).strip() for d in distractors)
        answer_penalty = 40 if answer_in_dist else 0
        # Base score from count
        base = min(100, 50 + len(distractors) * 15)
        dimension_scores["distractor_quality"] = max(0, base - dup_penalty - answer_penalty)
    else:
        # Open-ended question (no distractors needed)
        dimension_scores["distractor_quality"] = 70

    # 4. Empirical difficulty: from actual learner data if available
    empirical_data = question_data.get("empirical_correct_rate")
    if empirical_data is not None:
        # Ideal difficulty is 60-80% correct rate
        rate = empirical_data
        if 0.60 <= rate <= 0.80:
            dimension_scores["empirical_difficulty"] = 95
        elif 0.40 <= rate < 0.60 or 0.80 < rate <= 0.90:
            dimension_scores["empirical_difficulty"] = 70
        elif rate > 0.90:
            dimension_scores["empirical_difficulty"] = 40  # Too easy
        else:
            dimension_scores["empirical_difficulty"] = 50  # Too hard
    else:
        dimension_scores["empirical_difficulty"] = 60  # No data

    # Overall
    weights = {
        "requires_reading": 0.25,
        "cognitive_level": 0.25,
        "distractor_quality": 0.25,
        "empirical_difficulty": 0.25,
    }
    overall = sum(dimension_scores.get(k, 50) * w for k, w in weights.items())
    overall = max(0, min(100, int(overall)))

    return {
        "overall_score": overall,
        "dimension_scores": dimension_scores,
        "grade": _score_to_grade(overall),
    }


def assess_pronunciation_quality(conn, item_id: int, user_id: int = 1) -> dict:
    """Assess pronunciation content quality for a content item.

    Dimensions: tonal accuracy validated, sandhi marking, minimal pair
    coverage, audio quality.
    """
    dimension_scores = {}

    item = _safe_query_one(conn, "SELECT * FROM content_item WHERE id = ?", (item_id,))
    if item is None:
        return {
            "overall_score": 0,
            "dimension_scores": {},
            "grade": "F",
            "error": f"Item {item_id} not found",
        }

    item_d = dict(item)
    pinyin = item_d.get("pinyin", "")

    # 1. Tonal accuracy validated: check audio_recording results
    recordings = _safe_query(
        conn,
        "SELECT overall_score FROM audio_recording WHERE content_item_id = ? AND user_id = ?",
        (item_id, user_id),
    )
    if recordings:
        avg_score = sum((dict(r).get("overall_score") or 0) for r in recordings) / len(recordings)
        dimension_scores["tonal_accuracy"] = min(100, int(avg_score * 100))
    else:
        dimension_scores["tonal_accuracy"] = 50  # Not yet validated

    # 2. Sandhi marking: pinyin contains tone 3 sequences that need sandhi
    from ..tone_grading import pinyin_to_tones
    tones = pinyin_to_tones(pinyin)
    has_sandhi_context = False
    for i in range(len(tones) - 1):
        if tones[i] == 3 and tones[i + 1] == 3:
            has_sandhi_context = True
            break
    # Items with sandhi get bonus for being pedagogically valuable
    if has_sandhi_context:
        dimension_scores["sandhi_marking"] = 90
    elif len(tones) >= 2:
        dimension_scores["sandhi_marking"] = 70
    else:
        dimension_scores["sandhi_marking"] = 60

    # 3. Minimal pair coverage: are there similar-sounding items?
    hanzi = item_d.get("hanzi", "")
    if hanzi and len(hanzi) == 1:
        # Single character: check for same-pinyin-different-tone items
        base_pinyin = re.sub(r'[1234]', '', pinyin.lower().strip())
        similar = _safe_query(
            conn,
            "SELECT COUNT(*) FROM content_item WHERE pinyin LIKE ? AND id != ?",
            (f"%{base_pinyin}%", item_id),
        )
        similar_count = similar[0][0] if similar else 0
        dimension_scores["minimal_pair_coverage"] = min(100, 40 + similar_count * 15)
    else:
        dimension_scores["minimal_pair_coverage"] = 60

    # 4. Audio quality: audio file exists and is usable
    if item_d.get("audio_available") and item_d.get("audio_file_path"):
        dimension_scores["audio_quality"] = 90
    else:
        dimension_scores["audio_quality"] = 40

    # Overall
    weights = {
        "tonal_accuracy": 0.30,
        "sandhi_marking": 0.20,
        "minimal_pair_coverage": 0.20,
        "audio_quality": 0.30,
    }
    overall = sum(dimension_scores.get(k, 50) * w for k, w in weights.items())
    overall = max(0, min(100, int(overall)))

    return {
        "overall_score": overall,
        "dimension_scores": dimension_scores,
        "grade": _score_to_grade(overall),
    }


def assess_dialogue_quality(conn, scenario_id: int) -> dict:
    """Assess quality of a dialogue scenario.

    Dimensions: turn asymmetry, modal particle presence, naturalness,
    cultural depth, vocabulary integration.
    """
    dimension_scores = {}

    row = _safe_query_one(
        conn, "SELECT * FROM dialogue_scenario WHERE id = ?", (scenario_id,),
    )
    if row is None:
        return {
            "overall_score": 0,
            "dimension_scores": {},
            "grade": "F",
            "error": f"Scenario {scenario_id} not found",
        }

    scenario = dict(row)
    tree_json = scenario.get("tree_json", "{}")
    try:
        tree = json.loads(tree_json) if tree_json else {}
    except (json.JSONDecodeError, TypeError):
        tree = {}

    # Extract all text from the dialogue tree
    all_text = ""
    turn_lengths = []

    def _walk_tree(node):
        nonlocal all_text
        if isinstance(node, dict):
            for key in ("text", "speaker_text", "response", "prompt"):
                if key in node:
                    text = node[key]
                    all_text += text + " "
                    turn_lengths.append(len(text))
            for v in node.values():
                _walk_tree(v)
        elif isinstance(node, list):
            for item in node:
                _walk_tree(item)

    _walk_tree(tree)

    # 1. Turn asymmetry: real conversations aren't symmetric
    if len(turn_lengths) >= 2:
        max_len = max(turn_lengths)
        min_len = min(turn_lengths)
        ratio = min_len / max_len if max_len > 0 else 1.0
        # Perfect symmetry (ratio ~1.0) is unnatural; some asymmetry is good
        if 0.3 <= ratio <= 0.7:
            dimension_scores["turn_asymmetry"] = 90
        elif 0.2 <= ratio <= 0.8:
            dimension_scores["turn_asymmetry"] = 75
        else:
            dimension_scores["turn_asymmetry"] = 55
    else:
        dimension_scores["turn_asymmetry"] = 40  # Too few turns

    # 2. Modal particle presence (吗 吧 呢 啊 嘛 呀 了 的)
    modal_particles = set("吗吧呢啊嘛呀了的哦噢哎哇")
    particle_count = sum(1 for c in all_text if c in modal_particles)
    text_len = len([c for c in all_text if '\u4e00' <= c <= '\u9fff'])
    if text_len > 0:
        particle_density = particle_count / text_len
        if 0.03 <= particle_density <= 0.15:
            dimension_scores["modal_particles"] = 90
        elif particle_density > 0:
            dimension_scores["modal_particles"] = 65
        else:
            dimension_scores["modal_particles"] = 30  # No particles = unnatural
    else:
        dimension_scores["modal_particles"] = 30

    # 3. Naturalness (via Qwen2.5 if available)
    if all_text.strip():
        authenticity = _assess_authenticity_llm(all_text.strip(), conn=conn)
        dimension_scores["naturalness"] = authenticity["score"]
    else:
        dimension_scores["naturalness"] = 30

    # 4. Cultural depth: register awareness, scenario type variety
    register = scenario.get("register", "neutral")
    has_title_zh = bool(scenario.get("title_zh"))
    cultural_score = 50
    if register != "neutral":
        cultural_score += 20  # Non-neutral register shows awareness
    if has_title_zh:
        cultural_score += 15
    if scenario.get("hsk_level", 1) >= 3:
        cultural_score += 15  # Higher HSK often has more cultural depth
    dimension_scores["cultural_depth"] = min(100, cultural_score)

    # 5. Vocabulary integration: how many corpus words appear?
    tokens = _tokenize_chinese(all_text)
    if tokens:
        corpus_items = _safe_query(
            conn,
            "SELECT hanzi FROM content_item WHERE status = 'drill_ready'",
        )
        corpus_set = {dict(r)["hanzi"] for r in corpus_items} if corpus_items else set()
        if corpus_set:
            overlap = sum(1 for t in tokens if t in corpus_set)
            ratio = overlap / len(tokens)
            dimension_scores["vocabulary_integration"] = min(100, int(40 + ratio * 80))
        else:
            dimension_scores["vocabulary_integration"] = 50
    else:
        dimension_scores["vocabulary_integration"] = 30

    # Overall
    weights = {
        "turn_asymmetry": 0.20,
        "modal_particles": 0.20,
        "naturalness": 0.25,
        "cultural_depth": 0.15,
        "vocabulary_integration": 0.20,
    }
    overall = sum(dimension_scores.get(k, 50) * w for k, w in weights.items())
    overall = max(0, min(100, int(overall)))

    return {
        "overall_score": overall,
        "dimension_scores": dimension_scores,
        "grade": _score_to_grade(overall),
    }


def assess_listening_quality(conn, item_id: str, user_id: int = 1) -> dict:
    """Assess quality of a listening content item.

    Dimensions: transcript completeness, speaking rate appropriateness,
    vocabulary density, consumption rate, encounter extraction.
    """
    dimension_scores = {}

    # Check listening_progress for this item
    lp_rows = _safe_query(
        conn,
        "SELECT * FROM listening_progress WHERE passage_id = ? AND user_id = ?",
        (str(item_id), user_id),
    )

    # 1. Consumption rate: has it been listened to?
    if lp_rows:
        dimension_scores["consumption_rate"] = min(100, 50 + len(lp_rows) * 20)
        # Comprehension from data
        total_correct = sum((dict(r).get("questions_correct") or 0) for r in lp_rows)
        total_q = sum((dict(r).get("questions_total") or 0) for r in lp_rows)
        if total_q > 0:
            comp_rate = total_correct / total_q
            dimension_scores["comprehension"] = int(comp_rate * 100)
        else:
            dimension_scores["comprehension"] = 50
    else:
        dimension_scores["consumption_rate"] = 30
        dimension_scores["comprehension"] = 50

    # 2. Encounter extraction: did listening drive vocab encounters?
    encounters = _safe_query(
        conn,
        "SELECT COUNT(*) FROM vocab_encounter WHERE source_type = 'listening' AND source_id = ?",
        (str(item_id),),
    )
    enc_count = encounters[0][0] if encounters else 0
    dimension_scores["encounter_extraction"] = min(100, 30 + enc_count * 15)

    # 3. HSK level appropriateness (from listening_progress)
    if lp_rows:
        hsk = dict(lp_rows[0]).get("hsk_level", 1) or 1
        # Check against learner level
        profile = _safe_query_one(
            conn,
            "SELECT level_listening FROM learner_profile WHERE user_id = ?",
            (user_id,),
        )
        learner_level = dict(profile).get("level_listening", 1.0) if profile else 1.0
        diff = abs(hsk - learner_level)
        if diff <= 1:
            dimension_scores["level_appropriateness"] = 90
        elif diff <= 2:
            dimension_scores["level_appropriateness"] = 70
        else:
            dimension_scores["level_appropriateness"] = 45
    else:
        dimension_scores["level_appropriateness"] = 60

    # Overall
    weights = {
        "consumption_rate": 0.25,
        "comprehension": 0.25,
        "encounter_extraction": 0.25,
        "level_appropriateness": 0.25,
    }
    overall = sum(dimension_scores.get(k, 50) * w for k, w in weights.items())
    overall = max(0, min(100, int(overall)))

    return {
        "overall_score": overall,
        "dimension_scores": dimension_scores,
        "grade": _score_to_grade(overall),
    }


def assess_media_shelf_health(conn, user_id: int = 1) -> dict:
    """Assess health of the media shelf (video/audio content).

    Dimensions: consumption rate, staleness, encounter yield,
    media type diversity.
    """
    dimension_scores = {}

    media_rows = _safe_query(
        conn,
        "SELECT * FROM media_watch WHERE user_id = ?",
        (user_id,),
    )

    if not media_rows:
        return {
            "overall_score": 30,
            "dimension_scores": {
                "consumption_rate": 20,
                "staleness": 50,
                "encounter_yield": 20,
                "media_type_diversity": 20,
            },
            "grade": "F",
            "detail": "No media items tracked",
        }

    media_dicts = [dict(r) for r in media_rows]

    # 1. Consumption rate
    watched_count = sum(1 for m in media_dicts if (m.get("times_watched") or 0) > 0)
    total = len(media_dicts)
    rate = watched_count / total if total > 0 else 0
    dimension_scores["consumption_rate"] = min(100, int(rate * 120))

    # 2. Staleness: when was the last watch?
    last_dates = [m.get("last_watched_at") for m in media_dicts if m.get("last_watched_at")]
    if last_dates:
        latest = max(last_dates)
        try:
            latest_dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
            age_days = (datetime.now(UTC) - latest_dt).days
            if age_days <= 7:
                dimension_scores["staleness"] = 95
            elif age_days <= 30:
                dimension_scores["staleness"] = 70
            elif age_days <= 90:
                dimension_scores["staleness"] = 45
            else:
                dimension_scores["staleness"] = 20
        except (ValueError, TypeError):
            dimension_scores["staleness"] = 50
    else:
        dimension_scores["staleness"] = 20

    # 3. Encounter yield: encounters generated from media
    media_encounters = _safe_query(
        conn,
        "SELECT COUNT(*) FROM vocab_encounter WHERE source_type = 'media'",
    )
    enc_count = media_encounters[0][0] if media_encounters else 0
    dimension_scores["encounter_yield"] = min(100, 20 + enc_count * 5)

    # 4. Media type diversity
    types = set(m.get("media_type", "") for m in media_dicts)
    types.discard("")
    if len(types) >= 3:
        dimension_scores["media_type_diversity"] = 95
    elif len(types) == 2:
        dimension_scores["media_type_diversity"] = 75
    elif len(types) == 1:
        dimension_scores["media_type_diversity"] = 50
    else:
        dimension_scores["media_type_diversity"] = 20

    # Overall
    weights = {
        "consumption_rate": 0.30,
        "staleness": 0.25,
        "encounter_yield": 0.25,
        "media_type_diversity": 0.20,
    }
    overall = sum(dimension_scores.get(k, 50) * w for k, w in weights.items())
    overall = max(0, min(100, int(overall)))

    return {
        "overall_score": overall,
        "dimension_scores": dimension_scores,
        "grade": _score_to_grade(overall),
    }


# ── ContentQualityAnalyzer ───────────────────────────────────────────────

class ContentQualityAnalyzer:
    """Runs all content quality analyses and returns findings."""

    def run(self, conn) -> list[dict]:
        """Run all analysis, return list of findings."""
        findings = []
        findings.extend(self._analyze_corpus_composition(conn))
        findings.extend(self._analyze_question_quality_distribution(conn))
        findings.extend(self._analyze_content_type_coverage(conn))
        findings.extend(self._analyze_acquisition_pipeline(conn))
        findings.extend(self._analyze_voice_health(conn))
        findings.extend(self._analyze_productive_vocabulary_gap(conn))
        return findings

    def _analyze_corpus_composition(self, conn) -> list[dict]:
        """Analyze HSK distribution and content lens coverage."""
        findings = []

        # HSK distribution
        hsk_counts = _safe_query(
            conn,
            "SELECT hsk_level, COUNT(*) as cnt FROM content_item WHERE status = 'drill_ready' GROUP BY hsk_level",
        )
        if hsk_counts:
            hsk_dict = {(dict(r).get("hsk_level") or 0): dict(r)["cnt"] for r in hsk_counts}
            total = sum(hsk_dict.values())

            # Check for HSK level gaps
            for level in range(1, 7):
                count = hsk_dict.get(level, 0)
                if count == 0:
                    findings.append(_make_finding(
                        "corpus_composition",
                        f"No HSK {level} content",
                        "critical",
                        f"HSK level {level} has 0 drill-ready items.",
                        f"Add at least 20 items for HSK {level}.",
                    ))
                elif count < 10 and total > 50:
                    findings.append(_make_finding(
                        "corpus_composition",
                        f"Low HSK {level} coverage",
                        "warning",
                        f"HSK level {level} has only {count} items ({count/total*100:.0f}% of corpus).",
                        f"Target at least 20 items for HSK {level}.",
                    ))
        else:
            findings.append(_make_finding(
                "corpus_composition",
                "Empty corpus",
                "critical",
                "No drill-ready content items found.",
                "Seed the content library with HSK vocabulary.",
            ))

        # Content lens coverage
        lens_counts = _safe_query(
            conn,
            "SELECT content_lens, COUNT(*) as cnt FROM content_item WHERE content_lens IS NOT NULL GROUP BY content_lens",
        )
        if not lens_counts:
            findings.append(_make_finding(
                "corpus_composition",
                "No content lens tagging",
                "warning",
                "No content items have content_lens tags.",
                "Tag items with content lenses for personalization.",
            ))

        return findings

    def _analyze_question_quality_distribution(self, conn) -> list[dict]:
        """Analyze question quality across passages."""
        findings = []

        try:
            from pathlib import Path
            passages_path = DATA_DIR / "reading_passages.json"
            if not passages_path.exists():
                return findings
            with open(passages_path, encoding="utf-8") as f:
                raw = json.load(f)
            # Handle both formats: list or {"passages": [...]}
            if isinstance(raw, dict):
                passages = raw.get("passages", [])
            elif isinstance(raw, list):
                passages = raw
            else:
                passages = []
        except Exception:
            return findings

        no_questions = 0
        total_passages = len(passages)

        for p in passages:
            if not isinstance(p, dict):
                continue
            questions = p.get("comprehension_questions") or p.get("questions", [])
            if not questions:
                no_questions += 1

        if no_questions > 0 and total_passages > 0:
            ratio = no_questions / total_passages
            severity = "critical" if ratio > 0.5 else "warning"
            findings.append(_make_finding(
                "question_quality",
                "Passages without comprehension questions",
                severity,
                f"{no_questions}/{total_passages} passages have no comprehension questions.",
                "Add at least 2 comprehension questions per passage.",
            ))

        return findings

    def _analyze_content_type_coverage(self, conn) -> list[dict]:
        """Check for balanced content types (vocab, sentence, phrase, chunk, grammar)."""
        findings = []

        type_counts = _safe_query(
            conn,
            "SELECT item_type, COUNT(*) as cnt FROM content_item WHERE status = 'drill_ready' GROUP BY item_type",
        )
        if type_counts:
            type_dict = {dict(r)["item_type"]: dict(r)["cnt"] for r in type_counts}
            total = sum(type_dict.values())

            expected_types = {"vocab", "sentence", "phrase"}
            for t in expected_types:
                count = type_dict.get(t, 0)
                if count == 0 and total > 20:
                    findings.append(_make_finding(
                        "content_type_coverage",
                        f"No '{t}' content items",
                        "warning",
                        f"Content type '{t}' has 0 items.",
                        f"Add items of type '{t}' for balanced practice.",
                    ))

            # Check if vocab dominates excessively (>95%)
            vocab_count = type_dict.get("vocab", 0)
            if total > 0 and vocab_count / total > 0.95:
                findings.append(_make_finding(
                    "content_type_coverage",
                    "Vocab-heavy corpus",
                    "warning",
                    f"Vocabulary items are {vocab_count/total*100:.0f}% of corpus. "
                    "Sentences and phrases support contextual learning.",
                    "Add sentence-level and phrase-level content.",
                ))

        return findings

    def _analyze_acquisition_pipeline(self, conn) -> list[dict]:
        """Analyze consumption -> encounters -> drills flow."""
        findings = []

        # Encounters total
        enc_total = _safe_query_one(
            conn, "SELECT COUNT(*) FROM vocab_encounter",
        )
        enc_count = enc_total[0] if enc_total else 0

        # Encounters from reading
        reading_enc = _safe_query_one(
            conn, "SELECT COUNT(*) FROM vocab_encounter WHERE source_type = 'reading'",
        )
        reading_count = reading_enc[0] if reading_enc else 0

        # Encounters from listening
        listening_enc = _safe_query_one(
            conn, "SELECT COUNT(*) FROM vocab_encounter WHERE source_type = 'listening'",
        )
        listening_count = listening_enc[0] if listening_enc else 0

        # Encounters from media
        media_enc = _safe_query_one(
            conn, "SELECT COUNT(*) FROM vocab_encounter WHERE source_type = 'media'",
        )
        media_count = media_enc[0] if media_enc else 0

        if enc_count == 0:
            findings.append(_make_finding(
                "acquisition_pipeline",
                "No vocab encounters logged",
                "warning",
                "The encounter pipeline has produced 0 encounters. "
                "Consumption activities (reading, listening, media) are not feeding the drill queue.",
                "Ensure encounter logging is active in reading and listening modules.",
            ))
        else:
            # Check pipeline balance
            sources = {"reading": reading_count, "listening": listening_count, "media": media_count}
            zero_sources = [s for s, c in sources.items() if c == 0]
            if zero_sources:
                findings.append(_make_finding(
                    "acquisition_pipeline",
                    f"No encounters from: {', '.join(zero_sources)}",
                    "info",
                    f"Encounter sources with 0 entries: {', '.join(zero_sources)}. "
                    f"Total encounters: {enc_count}.",
                    "Encourage learner to use all content consumption modes.",
                ))

        return findings

    def _analyze_voice_health(self, conn) -> list[dict]:
        """Analyze TTS fallback rate and validation failures."""
        findings = []

        # Check audio recordings for quality issues
        recordings = _safe_query(
            conn,
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN overall_score IS NULL THEN 1 ELSE 0 END) as no_score "
            "FROM audio_recording",
        )
        if recordings:
            r = dict(recordings[0])
            total = r.get("total") or 0
            no_score = r.get("no_score") or 0
            if total > 0 and no_score > 0:
                fail_rate = no_score / total
                if fail_rate > 0.3:
                    findings.append(_make_finding(
                        "voice_health",
                        "High tone grading failure rate",
                        "warning",
                        f"{no_score}/{total} recordings ({fail_rate*100:.0f}%) lack tone scores. "
                        "Possible issues: microphone quality, background noise, or grading bugs.",
                        "Review audio recording pipeline and tone grading thresholds.",
                    ))

        # Check content items with audio flags but no files
        broken_audio = _safe_query_one(
            conn,
            "SELECT COUNT(*) FROM content_item WHERE audio_available = 1 AND audio_file_path IS NULL",
        )
        if broken_audio and broken_audio[0] > 0:
            findings.append(_make_finding(
                "voice_health",
                "Broken audio references",
                "warning",
                f"{broken_audio[0]} items marked audio_available=1 but have no audio_file_path.",
                "Regenerate audio files or clear the audio_available flag.",
            ))

        return findings

    def _analyze_productive_vocabulary_gap(self, conn) -> list[dict]:
        """Analyze recognition vs production drill ratio."""
        findings = []

        # Count progress entries by modality
        modality_counts = _safe_query(
            conn,
            "SELECT modality, COUNT(*) as cnt FROM progress GROUP BY modality",
        )
        if modality_counts:
            mod_dict = {dict(r)["modality"]: dict(r)["cnt"] for r in modality_counts}
            reading = mod_dict.get("reading", 0)
            speaking = mod_dict.get("speaking", 0)
            ime = mod_dict.get("ime", 0)

            production = speaking + ime
            recognition = reading

            if recognition > 0 and production == 0:
                findings.append(_make_finding(
                    "productive_vocab_gap",
                    "No production practice",
                    "critical",
                    f"{recognition} reading reviews but 0 speaking/IME reviews. "
                    "Recognition without production creates a passive vocabulary trap.",
                    "Enable speaking and IME drills in session planning.",
                ))
            elif recognition > 0 and production < recognition * 0.2:
                ratio = production / recognition
                findings.append(_make_finding(
                    "productive_vocab_gap",
                    "Low production-to-recognition ratio",
                    "warning",
                    f"Production/recognition ratio is {ratio:.1%}. "
                    f"Reading: {recognition}, Speaking+IME: {production}. "
                    "Target at least 30% production practice.",
                    "Increase speaking and IME drill frequency.",
                ))

        return findings


# ── Corpus audit report ──────────────────────────────────────────────────

def generate_corpus_audit_report(conn) -> dict:
    """Generate monthly corpus audit report.

    Returns dict with coverage, quality grades, pipeline health, HSK gaps.
    """
    analyzer = ContentQualityAnalyzer()
    findings = analyzer.run(conn)

    # Aggregate stats
    total_items = _safe_query_one(
        conn, "SELECT COUNT(*) FROM content_item WHERE status = 'drill_ready'",
    )
    total_count = total_items[0] if total_items else 0

    hsk_dist = {}
    hsk_rows = _safe_query(
        conn,
        "SELECT hsk_level, COUNT(*) as cnt FROM content_item WHERE status = 'drill_ready' GROUP BY hsk_level",
    )
    for r in hsk_rows:
        rd = dict(r)
        hsk_dist[rd.get("hsk_level") or 0] = rd["cnt"]

    # Grammar coverage
    grammar_count_row = _safe_query_one(conn, "SELECT COUNT(*) FROM grammar_point")
    grammar_count = grammar_count_row[0] if grammar_count_row else 0

    # Dialogue coverage
    dialogue_count_row = _safe_query_one(conn, "SELECT COUNT(*) FROM dialogue_scenario")
    dialogue_count = dialogue_count_row[0] if dialogue_count_row else 0

    # Encounter pipeline
    enc_total_row = _safe_query_one(conn, "SELECT COUNT(*) FROM vocab_encounter")
    enc_total = enc_total_row[0] if enc_total_row else 0

    # Severity breakdown
    severity_counts = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Overall health grade
    if severity_counts["critical"] > 0:
        health_grade = "D" if severity_counts["critical"] <= 2 else "F"
    elif severity_counts["warning"] > 3:
        health_grade = "C"
    elif severity_counts["warning"] > 0:
        health_grade = "B"
    else:
        health_grade = "A"

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "corpus_size": total_count,
        "hsk_distribution": hsk_dist,
        "grammar_points": grammar_count,
        "dialogue_scenarios": dialogue_count,
        "total_encounters": enc_total,
        "health_grade": health_grade,
        "severity_counts": severity_counts,
        "findings": findings,
    }
