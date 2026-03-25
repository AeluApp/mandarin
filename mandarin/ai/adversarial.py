"""Adversarial Multi-Agent Debate (Doc 23 C-01).

Content quality validation via Critic → Defender → Judge pattern.
Each role is a sequential Qwen call with Instructor-enforced structured output.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# Structured output models for debate roles
try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = None
    Field = None

if BaseModel is not None:
    class CriticOutput(BaseModel):
        """Critic role: find every flaw."""
        flaws: list[dict] = Field(default_factory=list,
                                  description="List of flaws found, each with category and detail")
        overall_assessment: str = Field(description="Overall quality assessment")

    class DefenderOutput(BaseModel):
        """Defender role: address each criticism."""
        responses: list[dict] = Field(default_factory=list,
                                      description="Response to each flaw: valid/invalid + evidence")
        conceded_flaws: list[str] = Field(default_factory=list,
                                          description="Flaws the defender concedes are valid")

    class JudgeOutput(BaseModel):
        """Judge role: final verdict."""
        accuracy_score: float = Field(ge=0, le=1, description="Linguistic accuracy 0-1")
        naturalness_score: float = Field(ge=0, le=1, description="Naturalness 0-1")
        pedagogical_score: float = Field(ge=0, le=1, description="Pedagogical value 0-1")
        cultural_score: float = Field(ge=0, le=1, description="Cultural appropriateness 0-1")
        verdict: str = Field(description="pass, fail, or revise")
        reasoning: str = Field(description="Judge's reasoning")


_CRITIC_SYSTEM = """You are a strict Mandarin language critic. Your job is to find EVERY flaw in the given content.
Look for: linguistic errors, tonal mistakes, character misuse, cultural missteps, pedagogical weaknesses,
register mismatches, unnatural phrasing, misleading translations. Be thorough and specific.
Return JSON with 'flaws' (list of {category, detail, severity}) and 'overall_assessment'."""

_DEFENDER_SYSTEM = """You are defending the quality of Mandarin learning content against criticism.
For each flaw raised, determine: is it valid or invalid? Provide evidence.
If valid, concede it. If invalid, explain why with linguistic evidence.
Return JSON with 'responses' (list of {flaw, valid, evidence}) and 'conceded_flaws' (list of strings)."""

_JUDGE_SYSTEM = """You are an impartial judge evaluating Mandarin learning content based on a critic/defender debate.
Score the content 0-1 on: accuracy, naturalness, pedagogical_value, cultural_appropriateness.
Give a verdict: 'pass' (score >= 0.7 on all), 'fail' (any score < 0.4), or 'revise' (otherwise).
Return JSON with accuracy_score, naturalness_score, pedagogical_score, cultural_score, verdict, reasoning."""


def run_adversarial_debate(
    conn: sqlite3.Connection,
    content_data: dict,
    content_type: str,
    content_id: int | None = None,
) -> dict:
    """Run Critic → Defender → Judge debate on content.

    Returns debate result with scores and verdict.
    """
    from .ollama_client import generate as ollama_generate, is_ollama_available
    from .genai_layer import _parse_llm_json

    if not is_ollama_available():
        return {"status": "skipped", "reason": "ollama_unavailable"}

    content_str = json.dumps(content_data, ensure_ascii=False, indent=2)

    # Step 1: Critic
    critic_prompt = f"Critique this {content_type} content:\n\n{content_str}"
    critic_resp = ollama_generate(
        prompt=critic_prompt,
        system=_CRITIC_SYSTEM,
        temperature=0.3,
        conn=conn,
        task_type="adversarial_critic",
    )
    if not critic_resp.success:
        return {"status": "error", "step": "critic", "error": critic_resp.error}

    critic_parsed = _parse_llm_json(critic_resp.text, conn=conn, task_type="adversarial_critic")
    if critic_parsed is None:
        critic_parsed = {"flaws": [], "overall_assessment": critic_resp.text[:500]}

    # Step 2: Defender
    defender_prompt = (
        f"Content under review:\n{content_str}\n\n"
        f"Critic's findings:\n{json.dumps(critic_parsed, ensure_ascii=False, indent=2)}\n\n"
        f"Defend this content against each criticism."
    )
    defender_resp = ollama_generate(
        prompt=defender_prompt,
        system=_DEFENDER_SYSTEM,
        temperature=0.3,
        conn=conn,
        task_type="adversarial_defender",
    )
    if not defender_resp.success:
        return {"status": "error", "step": "defender", "error": defender_resp.error}

    defender_parsed = _parse_llm_json(defender_resp.text, conn=conn, task_type="adversarial_defender")
    if defender_parsed is None:
        defender_parsed = {"responses": [], "conceded_flaws": []}

    # Step 3: Judge
    judge_prompt = (
        f"Content:\n{content_str}\n\n"
        f"Critic:\n{json.dumps(critic_parsed, ensure_ascii=False, indent=2)}\n\n"
        f"Defender:\n{json.dumps(defender_parsed, ensure_ascii=False, indent=2)}\n\n"
        f"Render your verdict."
    )
    judge_resp = ollama_generate(
        prompt=judge_prompt,
        system=_JUDGE_SYSTEM,
        temperature=0.1,
        conn=conn,
        task_type="adversarial_judge",
    )
    if not judge_resp.success:
        return {"status": "error", "step": "judge", "error": judge_resp.error}

    judge_parsed = _parse_llm_json(judge_resp.text, conn=conn, task_type="adversarial_judge")
    if judge_parsed is None:
        judge_parsed = {
            "accuracy_score": 0.5, "naturalness_score": 0.5,
            "pedagogical_score": 0.5, "cultural_score": 0.5,
            "verdict": "revise", "reasoning": "Judge output unparseable",
        }

    # Compute overall score
    scores = [
        judge_parsed.get("accuracy_score", 0.5),
        judge_parsed.get("naturalness_score", 0.5),
        judge_parsed.get("pedagogical_score", 0.5),
        judge_parsed.get("cultural_score", 0.5),
    ]
    overall_score = sum(scores) / len(scores)
    verdict = judge_parsed.get("verdict", "revise")
    passed = verdict == "pass"

    # Log to DB
    try:
        conn.execute("""
            INSERT INTO adversarial_debate
            (content_type, content_id, content_data, critic_output, defender_output,
             judge_verdict, judge_score, dimensions_tested, passed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            content_type,
            content_id,
            content_str,
            json.dumps(critic_parsed, ensure_ascii=False),
            json.dumps(defender_parsed, ensure_ascii=False),
            verdict,
            overall_score,
            json.dumps(["accuracy", "naturalness", "pedagogical", "cultural"]),
            1 if passed else 0,
        ))
        conn.commit()
    except sqlite3.OperationalError:
        pass

    return {
        "status": "completed",
        "verdict": verdict,
        "passed": passed,
        "overall_score": round(overall_score, 3),
        "scores": {
            "accuracy": judge_parsed.get("accuracy_score"),
            "naturalness": judge_parsed.get("naturalness_score"),
            "pedagogical": judge_parsed.get("pedagogical_score"),
            "cultural": judge_parsed.get("cultural_score"),
        },
        "critic": critic_parsed,
        "defender": defender_parsed,
        "judge": judge_parsed,
    }


def batch_debate(
    conn: sqlite3.Connection,
    content_items: list[dict],
    content_type: str,
) -> list[dict]:
    """Run adversarial debate on multiple items."""
    results = []
    for item in content_items:
        content_id = item.get("id")
        result = run_adversarial_debate(conn, item, content_type, content_id)
        results.append(result)
    return results


def get_debate_results(
    conn: sqlite3.Connection,
    content_type: str | None = None,
    passed_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Retrieve debate results from the database."""
    try:
        query = "SELECT * FROM adversarial_debate WHERE 1=1"
        params = []
        if content_type:
            query += " AND content_type = ?"
            params.append(content_type)
        if passed_only:
            query += " AND passed = 1"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
