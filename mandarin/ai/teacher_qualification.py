"""Teacher Pilot Qualification (Doc 23 B-02).

Multi-agent research to discover and score teacher candidates.
Never contacts anyone — discovery and scoring only.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def discover_candidates(
    conn: sqlite3.Connection,
    platforms: Optional[list[str]] = None,
) -> list[dict]:
    """Crawl public teacher listings to discover candidates.

    Uses web_crawler infrastructure. Only processes publicly available data.
    """
    if platforms is None:
        platforms = ["italki", "preply"]

    from .web_crawler import crawl_source, get_sources_due_for_crawl

    discovered = []
    # Look for teacher-related crawl sources
    try:
        sources = conn.execute("""
            SELECT * FROM crawl_source
            WHERE active = 1
            AND source_type = 'competitor'
            AND (name LIKE '%teacher%' OR name LIKE '%tutor%')
        """).fetchall()

        for source in sources:
            result = crawl_source(conn, source["id"])
            if result.get("status") == "completed":
                discovered.append(result)
    except sqlite3.OperationalError:
        pass

    return discovered


def add_lead(
    conn: sqlite3.Connection,
    name: str,
    platform: str,
    profile_url: Optional[str] = None,
    language_pair: str = "zh-en",
    teaching_style_tags: Optional[list[str]] = None,
    platform_rating: Optional[float] = None,
    estimated_students: Optional[int] = None,
    source_crawl_id: Optional[int] = None,
) -> Optional[int]:
    """Add a teacher lead to the database."""
    try:
        tags_json = json.dumps(teaching_style_tags) if teaching_style_tags else None
        cursor = conn.execute("""
            INSERT INTO teacher_lead
            (name, platform, profile_url, language_pair, teaching_style_tags,
             platform_rating, estimated_students, source_crawl_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, platform, profile_url, language_pair, tags_json,
            platform_rating, estimated_students, source_crawl_id,
        ))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.OperationalError:
        return None


def score_candidate(
    conn: sqlite3.Connection,
    lead_id: int,
) -> Optional[float]:
    """Multi-criteria scoring via Qwen.

    Scores: teaching style alignment, HSK experience, ratings, tech comfort.
    Returns score 0-1 or None if scoring unavailable.
    """
    from .ollama_client import generate as ollama_generate, is_ollama_available
    from .genai_layer import _parse_llm_json

    lead = conn.execute(
        "SELECT * FROM teacher_lead WHERE id = ?", (lead_id,)
    ).fetchone()
    if not lead:
        return None

    if not is_ollama_available():
        # Deterministic fallback scoring
        score = _deterministic_score(lead)
        _update_lead_score(conn, lead_id, score, "deterministic scoring (Ollama unavailable)")
        return score

    prompt = (
        f"Teacher candidate:\n"
        f"Name: {lead['name']}\n"
        f"Platform: {lead['platform']}\n"
        f"Language pair: {lead['language_pair']}\n"
        f"Rating: {lead['platform_rating'] or 'unknown'}\n"
        f"Students: {lead['estimated_students'] or 'unknown'}\n"
        f"Style tags: {lead['teaching_style_tags'] or 'none'}\n\n"
        f"Score this teacher 0-1 for Aelu pilot suitability. Return JSON:\n"
        f"- score: 0-1 overall\n"
        f"- teaching_alignment: how well style matches adaptive SRS approach\n"
        f"- hsk_experience: experience with HSK curriculum\n"
        f"- tech_comfort: likelihood of being comfortable with technology\n"
        f"- notes: brief qualification notes"
    )

    resp = ollama_generate(
        prompt=prompt,
        system="You are evaluating teacher candidates for a Mandarin learning technology pilot. Return JSON.",
        temperature=0.2,
        conn=conn,
        task_type="teacher_qualification",
    )

    if not resp.success:
        score = _deterministic_score(lead)
        _update_lead_score(conn, lead_id, score, "fallback scoring (LLM failed)")
        return score

    parsed = _parse_llm_json(resp.text, conn=conn, task_type="teacher_qualification")
    if not parsed:
        score = _deterministic_score(lead)
        _update_lead_score(conn, lead_id, score, "fallback scoring (parse failed)")
        return score

    score = parsed.get("score", 0.5)
    notes = parsed.get("notes", "")
    _update_lead_score(conn, lead_id, score, notes)
    return score


def _deterministic_score(lead) -> float:
    """Compute a basic score without LLM."""
    score = 0.5

    # Platform rating boost
    rating = lead["platform_rating"]
    if rating is not None:
        if rating >= 4.8:
            score += 0.2
        elif rating >= 4.5:
            score += 0.1

    # Student count boost
    students = lead["estimated_students"]
    if students is not None:
        if students >= 100:
            score += 0.15
        elif students >= 30:
            score += 0.1

    # Language pair match
    if lead["language_pair"] and "zh" in (lead["language_pair"] or ""):
        score += 0.1

    return min(1.0, round(score, 3))


def _update_lead_score(
    conn: sqlite3.Connection,
    lead_id: int,
    score: float,
    notes: str,
) -> None:
    """Update lead's qualification score and notes."""
    status = "qualified" if score >= 0.7 else "disqualified"
    try:
        conn.execute("""
            UPDATE teacher_lead
            SET qualification_score = ?, qualification_notes = ?, status = ?
            WHERE id = ?
        """, (score, notes, status, lead_id))
        conn.commit()
    except sqlite3.OperationalError:
        pass


def get_qualified_leads(
    conn: sqlite3.Connection,
    min_score: float = 0.7,
) -> list[dict]:
    """Retrieve ranked qualified candidates."""
    try:
        rows = conn.execute("""
            SELECT * FROM teacher_lead
            WHERE qualification_score >= ?
            AND status IN ('qualified', 'discovered')
            ORDER BY qualification_score DESC
        """, (min_score,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def get_all_leads(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Retrieve all teacher leads, optionally filtered by status."""
    try:
        query = "SELECT * FROM teacher_lead"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
