"""GenAI governance audit — corpus coverage and prompt performance analyzers.

Emits findings for the product intelligence engine (Doc 12).
"""

from __future__ import annotations

import logging
import sqlite3

from ._base import _finding, _safe_scalar

logger = logging.getLogger(__name__)


def analyze_corpus_coverage_findings(conn) -> list[dict]:
    """Emit findings for HSK levels with >30% unreviewed items and low usage_map population."""
    findings = []

    try:
        from ..ai.genai_layer import analyze_corpus_coverage
        report = analyze_corpus_coverage(conn)
    except (ImportError, Exception) as e:
        logger.debug("corpus coverage analysis unavailable: %s", e)
        return []

    total = report.get("total_items", 0)
    if total == 0:
        return []

    hsk_dist = report.get("hsk_distribution", {})
    unreviewed = report.get("unreviewed_by_hsk", {})

    for level, count in hsk_dist.items():
        unreview_count = unreviewed.get(level, 0)
        if unreview_count > 0:
            round(unreview_count / count * 100, 1) if count > 0 else 100.0
            findings.append(_finding(
                "genai_governance", "medium",
                f"HSK {level}: {unreview_count} AI-generated items pending review",
                f"{unreview_count} AI-generated HSK {level} items await governance review.",
                f"Review pending AI-generated content in the AI Review Queue.",
                f"Review {unreview_count} pending AI items at HSK {level} in admin > AI Review Queue.",
                "unreviewed AI content may contain errors or duplicates",
                ["mandarin/web/admin_routes.py"],
            ))

    usage_pct = report.get("usage_map_pct", 0)
    if usage_pct < 20:
        findings.append(_finding(
            "genai_governance", "low",
            f"Usage map population low ({usage_pct}%)",
            f"Only {usage_pct}% of drill-ready items have usage context populated.",
            "Run populate_usage_maps() to generate collocations via LLM.",
            "Populate usage maps for content items missing usage context.",
            "usage context enriches drill quality and error explanations",
            ["mandarin/ai/genai_layer.py"],
        ))

    return findings


def analyze_prompt_performance(conn) -> list[dict]:
    """Check json_parse_failure rate and prompt version drift."""
    findings = []

    # G6: JSON parse failure rate
    try:
        total_gen = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_ai_generation_log", default=0)
        failures = _safe_scalar(
            conn,
            "SELECT COUNT(*) FROM pi_ai_generation_log WHERE json_parse_failure = 1",
            default=0,
        )
    except (sqlite3.OperationalError, Exception):
        total_gen = 0
        failures = 0

    if total_gen > 0:
        failure_rate = failures / total_gen
        if failure_rate > 0.15:
            pct = round(failure_rate * 100, 1)
            findings.append(_finding(
                "genai_governance", "high",
                f"JSON parse failure rate: {pct}%",
                f"{failures} of {total_gen} LLM generations had unparseable JSON output.",
                "Review and tighten prompts that produce malformed JSON. Check prompt registry.",
                f"Fix JSON parse failures ({pct}% rate) — inspect pi_ai_generation_log for task_types with highest failure counts.",
                "unparseable LLM output wastes compute and degrades features",
                ["mandarin/ai/genai_layer.py", "mandarin/ai/ollama_client.py"],
            ))

    # Prompt version drift
    try:
        from ..ai.genai_layer import detect_prompt_regressions
        drift_findings = detect_prompt_regressions(conn)
        findings.extend(drift_findings)
    except (ImportError, Exception) as e:
        logger.debug("prompt regression check unavailable: %s", e)

    return findings


ANALYZERS = [analyze_corpus_coverage_findings, analyze_prompt_performance]
