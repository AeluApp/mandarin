"""AI health monitoring + intelligence integration."""

from __future__ import annotations

import logging

from .ollama_client import is_ollama_available

logger = logging.getLogger(__name__)


def check_ollama_health(conn) -> dict:
    """Check Ollama status + generation stats."""
    available = is_ollama_available()

    # 7-day generation stats
    stats = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
            SUM(CASE WHEN from_cache = 1 THEN 1 ELSE 0 END) as cache_hits,
            AVG(CASE WHEN success = 1 AND from_cache = 0 THEN generation_time_ms END) as avg_gen_ms
        FROM pi_ai_generation_log
        WHERE occurred_at >= datetime('now', '-7 days')
    """).fetchone()

    # Pending reviews
    pending_reviews = conn.execute(
        "SELECT COUNT(*) as cnt FROM pi_ai_review_queue WHERE reviewed_at IS NULL"
    ).fetchone()

    # Pending encounters
    pending_encounters = conn.execute(
        "SELECT COUNT(*) as cnt FROM vocab_encounter WHERE drill_generation_status = 'pending' AND hanzi IS NOT NULL"
    ).fetchone()

    return {
        "ollama_available": available,
        "generation_7d": {
            "total": stats["total"] or 0,
            "successes": stats["successes"] or 0,
            "cache_hits": stats["cache_hits"] or 0,
            "avg_generation_ms": round(stats["avg_gen_ms"] or 0),
        },
        "pending_reviews": pending_reviews["cnt"] or 0,
        "pending_encounters": pending_encounters["cnt"] or 0,
    }


def generate_ai_health_findings(conn) -> list[dict]:
    """Intelligence findings for AI subsystem health."""
    findings = []
    health = check_ollama_health(conn)

    # Check if Ollama has been unavailable (no successful generations in 7 days)
    gen_stats = health["generation_7d"]
    if gen_stats["total"] > 0 and gen_stats["successes"] == 0:
        findings.append({
            "dimension": "engineering",
            "severity": "medium",
            "title": "Ollama LLM unavailable — all generations failing",
            "analysis": f"{gen_stats['total']} generation attempts in 7 days, 0 successes.",
            "recommendation": "Check Ollama is running: `ollama serve`. Verify model is pulled: `ollama pull qwen2.5:7b`.",
            "claude_prompt": "Diagnose why Ollama generations are failing. Check logs and connectivity.",
            "impact": "AI-generated drills and error explanations unavailable",
            "files": ["mandarin/ai/ollama_client.py"],
        })

    # Review queue backlog
    if health["pending_reviews"] >= 10:
        findings.append({
            "dimension": "content",
            "severity": "medium",
            "title": f"AI review queue has {health['pending_reviews']} pending items",
            "analysis": "Generated content awaiting human review is accumulating.",
            "recommendation": "Review pending items at /admin/ → AI Review Queue.",
            "claude_prompt": "Show me the AI review queue contents and help me process them.",
            "impact": "Generated drills not reaching learners until reviewed",
            "files": ["mandarin/web/admin_routes.py"],
        })

    # High failure rate
    if gen_stats["total"] >= 10:
        failure_rate = 1 - (gen_stats["successes"] / gen_stats["total"])
        if failure_rate > 0.20:
            findings.append({
                "dimension": "engineering",
                "severity": "high",
                "title": f"AI generation failure rate {failure_rate:.0%} in 7 days",
                "analysis": f"{gen_stats['total']} attempts, {gen_stats['successes']} successes ({failure_rate:.0%} failure).",
                "recommendation": "Check model availability and prompt quality. Review error logs.",
                "claude_prompt": "Investigate AI generation failures. Query pi_ai_generation_log for recent errors.",
                "impact": "Encounter→drill pipeline degraded",
                "files": ["mandarin/ai/ollama_client.py", "mandarin/ai/drill_generator.py"],
            })

    return findings


ANALYZERS = [generate_ai_health_findings]
