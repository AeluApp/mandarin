"""GenAI Layer — session intelligence, corpus analysis, generative feedback,
prompt versioning, local embeddings, and Whisper pronunciation feedback.

All LLM-dependent functions are gated on is_ollama_available() and degrade
gracefully. Embedding functions degrade when sentence-transformers is missing.
Zero Claude tokens at runtime.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_llm_json(text: str, conn=None, task_type: str | None = None) -> Optional[dict]:
    """Strip markdown fences and parse JSON. Logs failures via G6 column."""
    if not text:
        return None
    # Strip ```json ... ``` fences
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("JSON parse failure (task=%s): %s", task_type, e)
        if conn and task_type:
            _log_json_parse_failure(conn, task_type)
        return None


def _log_json_parse_failure(conn, task_type: str) -> None:
    """G6: Log a JSON parse failure on the most recent pi_ai_generation_log row."""
    try:
        conn.execute("""
            UPDATE pi_ai_generation_log
            SET json_parse_failure = 1
            WHERE id = (
                SELECT id FROM pi_ai_generation_log
                WHERE task_type = ?
                ORDER BY occurred_at DESC LIMIT 1
            )
        """, (task_type,))
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("json_parse_failure column not available yet")


# ═══════════════════════════════════════════════════════════════════════════════
# Module 1: Session Intelligence
# ═══════════════════════════════════════════════════════════════════════════════

_ERROR_SHAPES = {
    "tonal_confusion": re.compile(r"tone|tōne|声调|shēngdiào", re.IGNORECASE),
    "character_confusion": re.compile(r"char|字|radical|偏旁", re.IGNORECASE),
    "semantic_gap": re.compile(r"meaning|义|semantic|语义", re.IGNORECASE),
    "grammar_slip": re.compile(r"grammar|语法|particle|助词|measure|量词", re.IGNORECASE),
}


def classify_error_shapes(conn, session_id: int, user_id: int = 1) -> dict:
    """Deterministic classification of review_event errors into shapes.

    Returns: {shape_name: count, ...}
    """
    rows = conn.execute("""
        SELECT re.correct_answer, re.given_answer, ci.english, ci.hanzi, ci.pinyin
        FROM review_event re
        JOIN content_item ci ON ci.id = re.content_item_id
        WHERE re.session_id = ? AND re.score = 0
    """, (session_id,)).fetchall()

    shapes = {k: 0 for k in _ERROR_SHAPES}
    shapes["other"] = 0

    for row in rows:
        correct = row["correct_answer"] or ""
        given = row["given_answer"] or ""
        english = row["english"] or ""
        context = f"{correct} {given} {english}"

        matched = False
        for shape_name, pattern in _ERROR_SHAPES.items():
            if pattern.search(context):
                shapes[shape_name] += 1
                matched = True
                break
        if not matched:
            # Check tonal: same base pinyin, different tone
            if _is_tonal_confusion(correct, given):
                shapes["tonal_confusion"] += 1
            else:
                shapes["other"] += 1

    return shapes


def _is_tonal_confusion(correct: str, given: str) -> bool:
    """Check if two answers differ only in tone marks."""
    import unicodedata
    def strip_tones(s):
        return "".join(
            c for c in unicodedata.normalize("NFD", s.lower())
            if unicodedata.category(c) != "Mn"
        )
    return strip_tones(correct) == strip_tones(given) and correct != given


def diagnose_session(conn, session_id: int, user_id: int = 1) -> dict:
    """Aggregate session metrics: accuracy, response_ms percentiles, drill breakdown.

    Deterministic — no LLM calls.
    """
    reviews = conn.execute("""
        SELECT score, response_ms, drill_type
        FROM review_event
        WHERE session_id = ?
    """, (session_id,)).fetchall()

    if not reviews:
        return {"total_reviews": 0, "accuracy": 0.0, "error_shapes": {}}

    total = len(reviews)
    correct = sum(1 for r in reviews if r["score"] == 1)
    accuracy = correct / total if total else 0.0

    response_times = sorted([r["response_ms"] for r in reviews if r["response_ms"]])
    p50 = response_times[len(response_times) // 2] if response_times else 0
    p90 = response_times[int(len(response_times) * 0.9)] if response_times else 0

    drill_counts = {}
    for r in reviews:
        dt = r["drill_type"] or "unknown"
        drill_counts[dt] = drill_counts.get(dt, 0) + 1

    error_shapes = classify_error_shapes(conn, session_id, user_id)

    return {
        "total_reviews": total,
        "correct": correct,
        "accuracy": round(accuracy, 3),
        "response_ms_p50": p50,
        "response_ms_p90": p90,
        "drill_type_breakdown": drill_counts,
        "error_shapes": error_shapes,
    }


def analyze_tutor_session(conn, tutor_session_id: int) -> dict:
    """Analyze tutor corrections. Calls LLM for synthesis when >= 3 corrections."""
    corrections = conn.execute("""
        SELECT wrong_form, correct_form
        FROM tutor_corrections
        WHERE tutor_session_id = ?
    """, (tutor_session_id,)).fetchall()

    result = {
        "tutor_session_id": tutor_session_id,
        "correction_count": len(corrections),
        "corrections": [
            {"wrong": c["wrong_form"], "correct": c["correct_form"]}
            for c in corrections
        ],
    }

    if len(corrections) >= 3:
        try:
            from .ollama_client import generate, is_ollama_available
            if is_ollama_available():
                pairs = "\n".join(
                    f"- {c['wrong_form']} → {c['correct_form']}" for c in corrections
                )
                resp = generate(
                    prompt=f"Analyze these Mandarin corrections and identify patterns:\n{pairs}\n\nReturn JSON: {{\"patterns\": [str], \"recommendation\": str}}",
                    system="You are a Mandarin language analysis assistant. Return valid JSON only.",
                    temperature=0.5,
                    max_tokens=512,
                    conn=conn,
                    task_type="tutor_analysis",
                )
                if resp.success:
                    parsed = _parse_llm_json(resp.text, conn, "tutor_analysis")
                    if parsed:
                        result["llm_synthesis"] = parsed
        except ImportError:
            pass

    return result


def _log_session_analysis(conn, session_id: int, user_id: int,
                          analysis_type: str, result: dict) -> None:
    """Persist analysis to genai_session_analysis table."""
    try:
        conn.execute("""
            INSERT INTO genai_session_analysis (session_id, user_id, analysis_type, result_json)
            VALUES (?, ?, ?, ?)
        """, (session_id, user_id, analysis_type, json.dumps(result)))
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("genai_session_analysis table not available")


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2: Corpus Intelligence
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_corpus_coverage(conn) -> dict:
    """Deterministic corpus coverage analysis: HSK distribution, unreviewed items,
    usage_map population. Returns structured report with static_baselines key (T10).
    """
    # HSK distribution
    hsk_dist = {}
    rows = conn.execute("""
        SELECT hsk_level, COUNT(*) as cnt
        FROM content_item
        WHERE status = 'drill_ready'
        GROUP BY hsk_level
    """).fetchall()
    for r in rows:
        hsk_dist[r["hsk_level"]] = r["cnt"]

    total_items = sum(hsk_dist.values())

    # Unreviewed AI-generated items per HSK level (governance review, not learner activity)
    unreviewed = {}
    try:
        rows = conn.execute("""
            SELECT ci.hsk_level, COUNT(*) as cnt
            FROM content_item ci
            WHERE ci.status = 'drill_ready'
              AND ci.is_ai_generated = 1
              AND ci.review_status = 'pending_review'
            GROUP BY ci.hsk_level
        """).fetchall()
        for r in rows:
            unreviewed[r["hsk_level"]] = r["cnt"]
    except sqlite3.OperationalError:
        pass  # is_ai_generated column may not exist yet

    # Usage map population
    usage_map_count = 0
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM content_item
            WHERE status = 'drill_ready' AND usage_map IS NOT NULL AND usage_map != ''
        """).fetchone()
        usage_map_count = row[0] if row else 0
    except sqlite3.OperationalError:
        pass  # Column may not exist yet

    usage_map_pct = round(usage_map_count / total_items * 100, 1) if total_items else 0.0

    return {
        "total_items": total_items,
        "hsk_distribution": hsk_dist,
        "unreviewed_by_hsk": unreviewed,
        "usage_map_populated": usage_map_count,
        "usage_map_pct": usage_map_pct,
        "static_baselines": {
            "total_items": total_items,
            "usage_map_pct": usage_map_pct,
            "hsk_levels_covered": len(hsk_dist),
            "measured_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def populate_usage_maps(conn, batch_size: int = 10) -> dict:
    """LLM-powered: generate usage contexts for items missing usage_map.

    Gated on is_ollama_available().
    """
    try:
        from .ollama_client import generate, is_ollama_available
    except ImportError:
        return {"status": "skipped", "reason": "ollama_client not available"}

    if not is_ollama_available():
        return {"status": "skipped", "reason": "ollama_unavailable"}

    try:
        rows = conn.execute("""
            SELECT id, hanzi, pinyin, english
            FROM content_item
            WHERE status = 'drill_ready'
              AND (usage_map IS NULL OR usage_map = '')
            LIMIT ?
        """, (batch_size,)).fetchall()
    except sqlite3.OperationalError:
        return {"status": "skipped", "reason": "usage_map column not available"}

    if not rows:
        return {"status": "complete", "processed": 0}

    processed = 0
    for row in rows:
        prompt = (
            f"For the Mandarin word {row['hanzi']} ({row['pinyin']}, \"{row['english']}\"), "
            f"provide common usage contexts and collocations.\n"
            f"Return JSON: {{\"collocations\": [str], \"contexts\": [str], \"register\": str}}"
        )
        resp = generate(
            prompt=prompt,
            system="You are a Mandarin lexicography assistant. Return valid JSON only.",
            temperature=0.5,
            max_tokens=512,
            conn=conn,
            task_type="usage_map_generation",
        )
        if resp.success:
            parsed = _parse_llm_json(resp.text, conn, "usage_map_generation")
            if parsed:
                conn.execute(
                    "UPDATE content_item SET usage_map = ? WHERE id = ?",
                    (json.dumps(parsed), row["id"]),
                )
                processed += 1

    conn.commit()
    return {"status": "complete", "processed": processed, "total_candidates": len(rows)}


def generate_thematic_passage(conn, theme: str, hsk_level: int,
                              target_items: list[str] | None = None) -> Optional[dict]:
    """Thin wrapper over existing reading_content.generate_reading_passage()."""
    try:
        from .reading_content import generate_reading_passage
        return generate_reading_passage(
            conn,
            target_hsk_level=hsk_level,
            target_vocabulary=target_items,
            topic=theme,
        )
    except ImportError:
        logger.warning("reading_content module not available")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Module 3: Generative Feedback
# ═══════════════════════════════════════════════════════════════════════════════

def generate_learning_insight(conn, user_id: int = 1, lookback_days: int = 7) -> Optional[dict]:
    """Weekly LLM insight about error patterns.

    Gated on >= 20 reviews + is_ollama_available().
    """
    review_count = conn.execute("""
        SELECT COUNT(*) FROM review_event
        WHERE user_id = ?
          AND reviewed_at >= datetime('now', ?)
    """, (user_id, f"-{lookback_days} days")).fetchone()[0]

    if review_count < 20:
        return None

    try:
        from .ollama_client import generate, is_ollama_available
    except ImportError:
        return None

    if not is_ollama_available():
        return None

    # Gather error summary
    errors = conn.execute("""
        SELECT ci.hanzi, ci.english, ci.hsk_level, re.given_answer, re.correct_answer
        FROM review_event re
        JOIN content_item ci ON ci.id = re.content_item_id
        WHERE re.user_id = ? AND re.score = 0
          AND re.reviewed_at >= datetime('now', ?)
        ORDER BY re.reviewed_at DESC
        LIMIT 30
    """, (user_id, f"-{lookback_days} days")).fetchall()

    if not errors:
        return None

    error_summary = "\n".join(
        f"- {e['hanzi']} ({e['english']}): answered \"{e['given_answer']}\" instead of \"{e['correct_answer']}\""
        for e in errors
    )

    resp = generate(
        prompt=(
            f"A Mandarin learner made these errors over the past {lookback_days} days:\n"
            f"{error_summary}\n\n"
            f"Identify 2-3 patterns and give brief, actionable advice.\n"
            f"Return JSON: {{\"patterns\": [str], \"advice\": [str], \"focus_areas\": [str]}}"
        ),
        system="You are a Mandarin learning advisor. Be concise and specific. Return valid JSON only.",
        temperature=0.5,
        max_tokens=512,
        conn=conn,
        task_type="learning_insight",
    )

    if not resp.success:
        return None

    parsed = _parse_llm_json(resp.text, conn, "learning_insight")
    if parsed:
        _log_session_analysis(conn, 0, user_id, "learning_insight", parsed)
    return parsed


def explain_error_batch(conn, item_ids: list[int], user_id: int = 1) -> list[dict]:
    """Batch wrapper over existing error_explanation.generate_error_explanation().

    Returns list of {item_id, explanation} dicts.
    """
    try:
        from .error_explanation import generate_error_explanation
    except ImportError:
        return []

    results = []
    for item_id in item_ids:
        row = conn.execute("""
            SELECT ci.hanzi, ci.pinyin, ci.english, ci.hsk_level,
                   re.given_answer, re.correct_answer
            FROM review_event re
            JOIN content_item ci ON ci.id = re.content_item_id
            WHERE ci.id = ? AND re.score = 0
            ORDER BY re.reviewed_at DESC LIMIT 1
        """, (item_id,)).fetchone()

        if not row:
            continue

        item_content = {
            "hanzi": row["hanzi"],
            "pinyin": row["pinyin"],
            "english": row["english"],
        }
        explanation = generate_error_explanation(
            conn,
            item_id=str(item_id),
            correct_answer=row["correct_answer"] or "",
            wrong_answer=row["given_answer"] or "",
            item_content=item_content,
            times_wrong=3,
            learner_hsk_level=row["hsk_level"] or 1,
        )
        if explanation:
            results.append({"item_id": item_id, "explanation": explanation})

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Module 4: Prompt Registry
# ═══════════════════════════════════════════════════════════════════════════════

PROMPT_REGISTRY = {
    # Doc 12 prompts
    "usage_map_generation": {
        "text": (
            "For the Mandarin word {hanzi} ({pinyin}, \"{english}\"), "
            "provide common usage contexts and collocations.\n"
            "Return JSON: {{\"collocations\": [str], \"contexts\": [str], \"register\": str}}"
        ),
        "category": "corpus",
        "version": 1,
    },
    "tutor_analysis": {
        "text": (
            "Analyze these Mandarin corrections and identify patterns:\n{corrections}\n\n"
            "Return JSON: {{\"patterns\": [str], \"recommendation\": str}}"
        ),
        "category": "session",
        "version": 1,
    },
    "learning_insight": {
        "text": (
            "A Mandarin learner made these errors over the past {lookback_days} days:\n"
            "{error_summary}\n\n"
            "Identify 2-3 patterns and give brief, actionable advice.\n"
            "Return JSON: {{\"patterns\": [str], \"advice\": [str], \"focus_areas\": [str]}}"
        ),
        "category": "feedback",
        "version": 1,
    },
    "pronunciation_feedback": {
        "text": (
            "A Mandarin learner attempted to say \"{target_zh}\" but the transcription was \"{transcription}\".\n"
            "Score: {score}. Identify pronunciation issues and give brief correction advice.\n"
            "Return JSON: {{\"issues\": [str], \"advice\": str, \"severity\": str}}"
        ),
        "category": "pronunciation",
        "version": 1,
    },
    # References to existing prompts (reading_content, error_explanation, drill_generator)
    "reading_generation": {
        "text": "See mandarin/ai/reading_content.py",
        "category": "corpus",
        "version": 1,
    },
    "error_explanation": {
        "text": "See mandarin/ai/error_explanation.py",
        "category": "feedback",
        "version": 1,
    },
    "drill_generation": {
        "text": "See mandarin/ai/drill_generator.py",
        "category": "corpus",
        "version": 1,
    },
}


def seed_prompt_registry(conn) -> int:
    """Persist prompts to genai_prompt_registry table. Idempotent."""
    seeded = 0
    for key, info in PROMPT_REGISTRY.items():
        try:
            existing = conn.execute(
                "SELECT version FROM genai_prompt_registry WHERE prompt_key = ?",
                (key,),
            ).fetchone()
            if existing:
                if existing["version"] < info["version"]:
                    conn.execute("""
                        UPDATE genai_prompt_registry
                        SET prompt_text = ?, version = ?, category = ?,
                            updated_at = datetime('now')
                        WHERE prompt_key = ?
                    """, (info["text"], info["version"], info["category"], key))
                    seeded += 1
            else:
                conn.execute("""
                    INSERT INTO genai_prompt_registry (prompt_key, prompt_text, version, category)
                    VALUES (?, ?, ?, ?)
                """, (key, info["text"], info["version"], info["category"]))
                seeded += 1
        except sqlite3.OperationalError:
            logger.debug("genai_prompt_registry table not available")
            return 0

    conn.commit()
    return seeded


def get_prompt(key: str) -> Optional[dict]:
    """Safe lookup from in-memory registry."""
    return PROMPT_REGISTRY.get(key)


def detect_prompt_regressions(conn) -> list[dict]:
    """Compare DB prompt versions vs in-memory. Returns finding dicts."""
    from ..intelligence._base import _finding

    findings = []
    try:
        db_prompts = conn.execute(
            "SELECT prompt_key, version, prompt_text FROM genai_prompt_registry"
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    for row in db_prompts:
        key = row["prompt_key"]
        mem = PROMPT_REGISTRY.get(key)
        if not mem:
            continue
        if row["version"] != mem["version"]:
            findings.append(_finding(
                "genai_governance", "medium",
                f"Prompt version mismatch: {key}",
                f"DB version {row['version']} != code version {mem['version']}",
                f"Run seed_prompt_registry() to sync prompt '{key}'",
                f"Sync prompt registry for '{key}' — DB has v{row['version']}, code has v{mem['version']}.",
                "prompt drift may cause inconsistent LLM outputs",
                ["mandarin/ai/genai_layer.py"],
            ))

    return findings


# ═══════════════════════════════════════════════════════════════════════════════
# Module 5: Local Embedding Layer
# ═══════════════════════════════════════════════════════════════════════════════

_EMBEDDING_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"
_embedding_model = None
_embedding_lock = None


def _get_multilingual_model():
    """Thread-safe singleton for multilingual embedding model.

    Separate from fuzzy_dedup.py's all-MiniLM-L6-v2.
    """
    global _embedding_model, _embedding_lock
    import threading
    if _embedding_lock is None:
        _embedding_lock = threading.Lock()
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer
                _embedding_model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
    return _embedding_model


def compute_item_embeddings(conn, content_item_ids: list[int] | None = None,
                            batch_size: int = 50) -> dict:
    """Compute and store embeddings in genai_item_embeddings."""
    try:
        import numpy as np
        model = _get_multilingual_model()
    except ImportError:
        return {"status": "skipped", "reason": "sentence-transformers not installed"}

    if content_item_ids:
        placeholders = ",".join("?" * len(content_item_ids))
        rows = conn.execute(f"""
            SELECT ci.id, ci.hanzi, ci.pinyin, ci.english
            FROM content_item ci
            LEFT JOIN genai_item_embeddings ge ON ge.content_item_id = ci.id
            WHERE ci.id IN ({placeholders}) AND ge.id IS NULL
        """, content_item_ids).fetchall()
    else:
        rows = conn.execute("""
            SELECT ci.id, ci.hanzi, ci.pinyin, ci.english
            FROM content_item ci
            LEFT JOIN genai_item_embeddings ge ON ge.content_item_id = ci.id
            WHERE ci.status = 'drill_ready' AND ge.id IS NULL
            LIMIT ?
        """, (batch_size,)).fetchall()

    if not rows:
        return {"status": "complete", "computed": 0}

    texts = [f"{r['hanzi']} {r['pinyin']} {r['english']}" for r in rows]
    embeddings = model.encode(texts, show_progress_bar=False)

    computed = 0
    for row, emb in zip(rows, embeddings):
        try:
            conn.execute("""
                INSERT OR IGNORE INTO genai_item_embeddings
                (content_item_id, embedding, model_name)
                VALUES (?, ?, ?)
            """, (row["id"], emb.tobytes(), _EMBEDDING_MODEL_NAME))
            computed += 1
        except sqlite3.OperationalError:
            break

    conn.commit()
    return {"status": "complete", "computed": computed}


def find_similar_items(conn, query_hanzi: str, top_k: int = 5) -> list[dict]:
    """Cosine similarity search against stored embeddings."""
    try:
        import numpy as np
        model = _get_multilingual_model()
    except ImportError:
        return []

    query_emb = model.encode([query_hanzi], show_progress_bar=False)[0]

    try:
        rows = conn.execute("""
            SELECT ge.content_item_id, ge.embedding, ci.hanzi, ci.pinyin, ci.english
            FROM genai_item_embeddings ge
            JOIN content_item ci ON ci.id = ge.content_item_id
        """).fetchall()
    except sqlite3.OperationalError:
        return []

    if not rows:
        return []

    import numpy as np
    results = []
    query_norm = np.linalg.norm(query_emb)
    if query_norm == 0:
        return []

    for row in rows:
        stored_emb = np.frombuffer(row["embedding"], dtype=np.float32)
        stored_norm = np.linalg.norm(stored_emb)
        if stored_norm == 0:
            continue
        similarity = float(np.dot(query_emb, stored_emb) / (query_norm * stored_norm))
        results.append({
            "content_item_id": row["content_item_id"],
            "hanzi": row["hanzi"],
            "pinyin": row["pinyin"],
            "english": row["english"],
            "similarity": round(similarity, 4),
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


# ═══════════════════════════════════════════════════════════════════════════════
# Module 6: Whisper Pronunciation Feedback
# ═══════════════════════════════════════════════════════════════════════════════

def generate_pronunciation_feedback(conn, session_id: int,
                                    practice_session_id: int) -> Optional[dict]:
    """Read speaking_practice_sessions.whisper_transcription, compare to target_zh,
    generate LLM feedback. Gated on overall_score < 0.8 and is_ollama_available().

    Does NOT call Whisper directly.
    """
    row = conn.execute("""
        SELECT target_zh, whisper_transcription, overall_score,
               tone_accuracy, character_accuracy, error_types
        FROM speaking_practice_sessions
        WHERE id = ? AND session_id = ?
    """, (practice_session_id, session_id)).fetchone()

    if not row:
        return None

    score = row["overall_score"] or 1.0
    if score >= 0.8:
        return None  # Good enough, no feedback needed

    try:
        from .ollama_client import generate, is_ollama_available
    except ImportError:
        return None

    if not is_ollama_available():
        return None

    target = row["target_zh"] or ""
    transcription = row["whisper_transcription"] or ""

    resp = generate(
        prompt=(
            f"A Mandarin learner attempted to say \"{target}\" but the transcription was \"{transcription}\".\n"
            f"Score: {score:.2f}. Tone accuracy: {row['tone_accuracy'] or 0:.2f}. "
            f"Character accuracy: {row['character_accuracy'] or 0:.2f}.\n"
            f"Identify pronunciation issues and give brief correction advice.\n"
            f"Return JSON: {{\"issues\": [str], \"advice\": str, \"severity\": str}}"
        ),
        system="You are a Mandarin pronunciation coach. Be specific about tone and articulation issues. Return valid JSON only.",
        temperature=0.4,
        max_tokens=512,
        conn=conn,
        task_type="pronunciation_feedback",
    )

    if not resp.success:
        return None

    parsed = _parse_llm_json(resp.text, conn, "pronunciation_feedback")
    if parsed:
        parsed["practice_session_id"] = practice_session_id
        parsed["target_zh"] = target
        parsed["transcription"] = transcription
        _log_session_analysis(conn, session_id, 1, "pronunciation_feedback", parsed)
    return parsed


def batch_pronunciation_feedback(conn, session_id: int) -> list[dict]:
    """Process all speaking practice sessions for a session."""
    rows = conn.execute("""
        SELECT id FROM speaking_practice_sessions
        WHERE session_id = ? AND overall_score < 0.8
    """, (session_id,)).fetchall()

    results = []
    for row in rows:
        feedback = generate_pronunciation_feedback(conn, session_id, row["id"])
        if feedback:
            results.append(feedback)
    return results
