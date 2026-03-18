"""Grammar tutor — "ask why" and contextual teaching via Ollama.

Provides two capabilities:
1. answer_grammar_question(): Free-form Q&A about Chinese grammar
2. explain_in_context(): Targeted explanation after drill errors

Both have deterministic fallbacks when Ollama is unavailable —
returns stored grammar_point data directly from the DB.
"""

import json
import logging
from typing import Optional

from .ollama_client import generate, is_ollama_available

logger = logging.getLogger(__name__)

GRAMMAR_QA_SYSTEM = """You are a knowledgeable Mandarin Chinese grammar tutor.
Answer the learner's question clearly and concisely.

Rules:
- Use the provided grammar reference as your primary source
- Give concrete examples with pinyin and English translations
- Explain the "why" — the underlying logic, not just the rule
- Compare to English patterns when helpful
- Write naturally — no textbook smell (教材味)
- Keep answers under 200 words
- If the question is outside the provided grammar context, say so honestly

Grammar reference:
{grammar_context}
"""

CONTEXT_EXPLAIN_SYSTEM = """You are a patient Mandarin tutor giving a brief explanation after a mistake.

The learner just got this wrong:
- Item: {hanzi} ({pinyin}) — {english}
- Their answer: {user_answer}
- Correct answer: {expected_answer}
- Grammar rule: {grammar_name} — {grammar_pattern}

Give a 2-3 sentence explanation of why the correct answer is right.
Be encouraging but honest. No fluff. Include one example sentence.
"""


def answer_grammar_question(
    conn,
    question: str,
    grammar_point_id: Optional[int] = None,
    content_item_id: Optional[int] = None,
    user_hsk_level: int = 2,
) -> dict:
    """Answer a free-form grammar question.

    Returns:
        {"answer": str, "grammar_point_id": int|None,
         "examples": list, "source": "llm"|"db"}
    """
    # Find relevant grammar point
    gp = None
    if grammar_point_id:
        gp = _get_grammar_point(conn, grammar_point_id)
    elif content_item_id:
        gp = _get_grammar_for_item(conn, content_item_id)
    else:
        gp = _search_grammar_point(conn, question)

    # Build context from grammar point
    grammar_context = _format_grammar_context(gp) if gp else "No specific grammar point found."
    examples = _get_examples(gp) if gp else []

    # Try LLM
    if is_ollama_available():
        system = GRAMMAR_QA_SYSTEM.format(grammar_context=grammar_context)
        response = generate(
            prompt=question,
            system=system,
            temperature=0.3,
            max_tokens=512,
            use_cache=True,
            conn=conn,
            task_type="grammar_qa",
        )
        if response.success:
            return {
                "answer": response.text.strip(),
                "grammar_point_id": gp["id"] if gp else None,
                "examples": examples,
                "source": "llm",
            }

    # Deterministic fallback
    if gp:
        answer = _deterministic_answer(gp, question)
        return {
            "answer": answer,
            "grammar_point_id": gp["id"],
            "examples": examples,
            "source": "db",
        }

    return {
        "answer": "I don't have specific information about that grammar point. "
                  "Try asking about a specific pattern like 把, 了, or 的.",
        "grammar_point_id": None,
        "examples": [],
        "source": "db",
    }


def explain_in_context(
    conn,
    content_item_id: int,
    user_answer: str = "",
    expected_answer: str = "",
    error_count: int = 1,
    user_hsk_level: int = 2,
) -> Optional[dict]:
    """Generate a contextual explanation after a drill error.

    Only triggers when the learner has gotten this grammar pattern wrong 2+ times.
    Returns None if no grammar point is linked or error_count < 2.
    """
    if error_count < 2:
        return None

    # Get item and linked grammar
    item = _get_content_item(conn, content_item_id)
    if not item:
        return None

    gp = _get_grammar_for_item(conn, content_item_id)
    if not gp:
        return None

    examples = _get_examples(gp)

    # Try LLM
    if is_ollama_available():
        system = CONTEXT_EXPLAIN_SYSTEM.format(
            hanzi=item.get("hanzi", ""),
            pinyin=item.get("pinyin", ""),
            english=item.get("english", ""),
            user_answer=user_answer[:100],
            expected_answer=expected_answer[:100],
            grammar_name=gp.get("name", ""),
            grammar_pattern=gp.get("pattern", ""),
        )
        response = generate(
            prompt="Explain this mistake briefly.",
            system=system,
            temperature=0.3,
            max_tokens=256,
            use_cache=True,
            conn=conn,
            task_type="grammar_explain",
        )
        if response.success:
            return {
                "explanation": response.text.strip(),
                "grammar_point_id": gp["id"],
                "grammar_name": gp["name"],
                "examples": examples[:2],
                "source": "llm",
            }

    # Deterministic fallback
    explanation = gp.get("explanation") or gp.get("description") or ""
    pattern = gp.get("pattern") or ""
    fallback = f"{gp['name']}: {pattern}" if pattern else gp["name"]
    if explanation:
        fallback += f"\n{explanation}"

    return {
        "explanation": fallback,
        "grammar_point_id": gp["id"],
        "grammar_name": gp["name"],
        "examples": examples[:2],
        "source": "db",
    }


def generate_mini_lesson(conn, grammar_point_id: int) -> dict:
    """Generate a structured mini-lesson for a grammar point.

    Always deterministic — no LLM needed. Returns structured lesson data
    from the DB: overview, rule, graduated examples, common mistakes.
    """
    gp = _get_grammar_point(conn, grammar_point_id)
    if not gp:
        return {"error": "Grammar point not found"}

    examples = _get_examples(gp)
    linked = _get_linked_items(conn, grammar_point_id)

    # Build graduated examples (simple to complex)
    graduated = []
    for ex in examples:
        graduated.append({
            "chinese": ex.get("chinese") or ex.get("zh", ""),
            "pinyin": ex.get("pinyin", ""),
            "english": ex.get("english") or ex.get("en", ""),
        })

    # Common mistakes from error_log
    common_mistakes = conn.execute("""
        SELECT el.user_answer, el.expected_answer, COUNT(*) as cnt
        FROM error_log el
        JOIN content_grammar cg ON cg.content_item_id = el.content_item_id
        WHERE cg.grammar_point_id = ?
        GROUP BY el.user_answer, el.expected_answer
        ORDER BY cnt DESC
        LIMIT 3
    """, (grammar_point_id,)).fetchall()

    return {
        "grammar_point_id": gp["id"],
        "name": gp["name"],
        "name_zh": gp.get("name_zh") or "",
        "hsk_level": gp["hsk_level"],
        "overview": gp.get("description") or "",
        "rule": gp.get("pattern") or "",
        "explanation": gp.get("explanation") or "",
        "examples": graduated,
        "practice_items": [
            {"hanzi": i["hanzi"], "pinyin": i["pinyin"], "english": i["english"]}
            for i in linked[:5]
        ],
        "common_mistakes": [
            {"wrong": m["user_answer"], "correct": m["expected_answer"], "count": m["cnt"]}
            for m in common_mistakes
        ],
    }


# ── Prerequisite checking (Pienemann's Processability Theory) ──────

def check_prerequisites(conn, user_id: int, grammar_point_id: int) -> dict:
    """Check if prerequisites for a grammar point are met.

    Uses the grammar_prerequisites DAG to determine whether the learner
    has sufficient mastery of prerequisite grammar points before advancing.

    Returns:
        {
            'all_met': bool,
            'blocking': list of {id, title, mastery_score, relationship},
            'met': list of {id, title, mastery_score, relationship},
        }
    """
    try:
        prereqs = conn.execute("""
            SELECT gp_req.grammar_point_id, gp_req.prerequisite_id,
                   gp_req.relationship,
                   g.name as prereq_title
            FROM grammar_prerequisites gp_req
            JOIN grammar_point g ON gp_req.prerequisite_id = g.id
            WHERE gp_req.grammar_point_id = ?
        """, (grammar_point_id,)).fetchall()
    except Exception:
        # Table may not exist yet (pre-migration)
        return {'all_met': True, 'blocking': [], 'met': []}

    if not prereqs:
        return {'all_met': True, 'blocking': [], 'met': []}

    blocking = []
    met = []
    for prereq in prereqs:
        # Check learner's mastery of this prerequisite via grammar_progress
        mastery = conn.execute("""
            SELECT mastery_score FROM grammar_progress
            WHERE user_id = ? AND grammar_point_id = ?
        """, (user_id, prereq['prerequisite_id'])).fetchone()

        score = mastery['mastery_score'] if mastery else 0.0
        info = {
            'id': prereq['prerequisite_id'],
            'title': prereq['prereq_title'],
            'mastery_score': score,
            'relationship': prereq['relationship'],
        }

        # Threshold depends on relationship type
        if prereq['relationship'] == 'requires' and score < 0.7:
            blocking.append(info)
        elif prereq['relationship'] == 'recommended' and score < 0.5:
            blocking.append(info)
        else:
            met.append(info)

    return {
        'all_met': len(blocking) == 0,
        'blocking': blocking,
        'met': met,
    }


# ── Helpers ───────────────────────────────────────────────

def _get_grammar_point(conn, grammar_point_id: int) -> Optional[dict]:
    row = conn.execute("""
        SELECT id, name, name_zh, hsk_level, category, pattern,
               description, explanation, examples_json, examples
        FROM grammar_point WHERE id = ?
    """, (grammar_point_id,)).fetchone()
    return dict(row) if row else None


def _get_grammar_for_item(conn, content_item_id: int) -> Optional[dict]:
    row = conn.execute("""
        SELECT gp.id, gp.name, gp.name_zh, gp.hsk_level, gp.category,
               gp.pattern, gp.description, gp.explanation,
               gp.examples_json, gp.examples
        FROM content_grammar cg
        JOIN grammar_point gp ON gp.id = cg.grammar_point_id
        WHERE cg.content_item_id = ?
        LIMIT 1
    """, (content_item_id,)).fetchone()
    return dict(row) if row else None


def _search_grammar_point(conn, question: str) -> Optional[dict]:
    """Simple keyword search for a relevant grammar point."""
    # Try exact name match first
    keywords = question.lower().split()
    for kw in keywords:
        if len(kw) < 2:
            continue
        row = conn.execute("""
            SELECT id, name, name_zh, hsk_level, category, pattern,
                   description, explanation, examples_json, examples
            FROM grammar_point
            WHERE LOWER(name) LIKE ? OR LOWER(pattern) LIKE ?
                  OR name_zh LIKE ?
            LIMIT 1
        """, (f"%{kw}%", f"%{kw}%", f"%{kw}%")).fetchone()
        if row:
            return dict(row)
    return None


def _get_content_item(conn, content_item_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, hanzi, pinyin, english FROM content_item WHERE id = ?",
        (content_item_id,),
    ).fetchone()
    return dict(row) if row else None


def _get_examples(gp: dict) -> list:
    """Parse examples from grammar point data."""
    for field in ("examples_json", "examples"):
        raw = gp.get(field)
        if raw and isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
        elif raw and isinstance(raw, list):
            return raw
    return []


def _get_linked_items(conn, grammar_point_id: int) -> list:
    rows = conn.execute("""
        SELECT ci.hanzi, ci.pinyin, ci.english
        FROM content_grammar cg
        JOIN content_item ci ON ci.id = cg.content_item_id
        WHERE cg.grammar_point_id = ?
        ORDER BY ci.hsk_level ASC
        LIMIT 10
    """, (grammar_point_id,)).fetchall()
    return [dict(r) for r in rows]


def _format_grammar_context(gp: dict) -> str:
    """Format a grammar point as context for LLM prompts."""
    parts = [f"Grammar point: {gp['name']}"]
    if gp.get("name_zh"):
        parts[0] += f" ({gp['name_zh']})"
    parts.append(f"HSK Level: {gp['hsk_level']}")
    if gp.get("pattern"):
        parts.append(f"Pattern: {gp['pattern']}")
    if gp.get("explanation"):
        parts.append(f"Explanation: {gp['explanation']}")
    if gp.get("description"):
        parts.append(f"Description: {gp['description']}")
    examples = _get_examples(gp)
    if examples:
        parts.append("Examples:")
        for ex in examples[:3]:
            zh = ex.get("chinese") or ex.get("zh", "")
            en = ex.get("english") or ex.get("en", "")
            parts.append(f"  - {zh} — {en}")
    return "\n".join(parts)


def _deterministic_answer(gp: dict, question: str) -> str:
    """Build an answer from DB data without LLM."""
    parts = []
    if gp.get("pattern"):
        parts.append(f"Pattern: {gp['pattern']}")
    if gp.get("explanation"):
        parts.append(gp["explanation"])
    elif gp.get("description"):
        parts.append(gp["description"])
    examples = _get_examples(gp)
    if examples:
        parts.append("\nExamples:")
        for ex in examples[:3]:
            zh = ex.get("chinese") or ex.get("zh", "")
            pin = ex.get("pinyin", "")
            en = ex.get("english") or ex.get("en", "")
            line = zh
            if pin:
                line += f" ({pin})"
            if en:
                line += f" — {en}"
            parts.append(f"  {line}")
    return "\n".join(parts) if parts else f"See the grammar reference for {gp['name']}."
