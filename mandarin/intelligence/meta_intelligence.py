"""Meta-intelligence — GenAI validates the intelligence system itself.

Uses the LLM to review dimensions, findings, scoring, and work orders
for completeness, accuracy, and calibration.  Produces findings with
dimension="meta" that appear in the dashboard alongside product findings.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from ._base import _finding, _safe_scalar

logger = logging.getLogger(__name__)


def _llm_call(prompt: str, system: str = "", conn=None, max_tokens: int = 800) -> str | None:
    """Call the LLM. Returns response text or None on failure."""
    try:
        from ..ai.ollama_client import generate
        resp = generate(
            prompt=prompt, system=system,
            temperature=0.3, max_tokens=max_tokens,
            use_cache=True, conn=conn, task_type="meta_intelligence",
        )
        return resp.text if resp.success else None
    except Exception:
        logger.debug("Meta-intelligence LLM call failed", exc_info=True)
        return None


def _parse_json(text: str) -> dict | list | None:
    """Extract JSON from LLM response (may be wrapped in markdown code blocks)."""
    if not text:
        return None
    try:
        # Try direct parse first
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Try extracting from code blocks
    match = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding JSON object/array in the text
    for pattern in [r"(\{.*\})", r"(\[.*\])"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    return None


# ─── 1. Validate Dimensions ────────────────────────────────────

def meta_validate_dimensions(conn, dimension_scores: dict) -> list[dict]:
    """Ask LLM whether the dimension set is complete for a Mandarin learning app."""
    findings = []
    if not dimension_scores:
        return findings

    dim_summary = ", ".join(sorted(dimension_scores.keys()))

    prompt = (
        "You are auditing the quality intelligence system of a Mandarin Chinese learning app "
        "(web + iOS + Android + macOS + Flutter). The app has spaced repetition, tone grading, "
        "reading passages, AI-generated drills, and a multi-channel bot (iMessage, Telegram, etc.).\n\n"
        f"Current dimensions being tracked ({len(dimension_scores)}):\n{dim_summary}\n\n"
        "What important quality dimensions are MISSING? Consider: accessibility, localization, "
        "data privacy, learner motivation, social features, offline capability, etc.\n\n"
        "Respond in JSON: {\"missing\": [{\"name\": \"dim_name\", \"reason\": \"why it matters\"}], "
        "\"redundant\": [{\"name\": \"dim_name\", \"reason\": \"why it overlaps\"}]}\n"
        "Only include dimensions that are genuinely important. Be selective, not exhaustive."
    )

    text = _llm_call(prompt, system="You are a product quality expert. Be concise and specific.", conn=conn)
    data = _parse_json(text)
    if not data:
        return findings

    for item in (data.get("missing") or [])[:3]:
        name = item.get("name", "unknown")
        reason = item.get("reason", "")
        findings.append(_finding(
            "meta", "low",
            f"Missing dimension: {name}",
            f"The intelligence system does not track '{name}'. {reason}",
            f"Add an analyzer for '{name}' that inspects relevant code, data, or user behavior.",
            f"Create a new analyzer function in mandarin/intelligence/ that checks for {name} criteria.",
            "Intelligence completeness",
            [],
        ))

    for item in (data.get("redundant") or [])[:2]:
        name = item.get("name", "unknown")
        reason = item.get("reason", "")
        if name in dimension_scores:
            findings.append(_finding(
                "meta", "low",
                f"Potentially redundant dimension: {name}",
                f"The dimension '{name}' may overlap with others. {reason}",
                f"Consider merging '{name}' with its overlapping dimension to reduce noise.",
                f"Review whether {name} findings duplicate findings from related dimensions.",
                "Intelligence efficiency",
                [],
            ))

    return findings


# ─── 2. Validate Findings (false positive detection) ───────────

def meta_validate_findings(conn, findings: list[dict]) -> list[dict]:
    """Ask LLM to review high-severity findings for false positives."""
    meta_findings = []
    if not findings:
        return meta_findings

    # Only review top-10 highest severity findings
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.get("severity", "low"), 9))
    top_findings = sorted_findings[:10]

    findings_text = ""
    for i, f in enumerate(top_findings):
        findings_text += (
            f"\n{i+1}. [{f.get('severity', '?')}] {f.get('dimension', '?')}: "
            f"{f.get('title', '?')}\n   Analysis: {f.get('analysis', '')[:150]}\n"
        )

    prompt = (
        "You are reviewing the top findings from a Mandarin learning app's quality audit. "
        "This is a PRE-LAUNCH app with 0 real users (only admin testing).\n\n"
        f"FINDINGS:{findings_text}\n\n"
        "For each finding, rate confidence (0.0-1.0) that it's a REAL problem, not a false positive. "
        "Consider: Is this relevant pre-launch? Does it make sense for a solo-dev app? "
        "Could it be a measurement artifact?\n\n"
        "Respond in JSON: [{\"index\": 1, \"confidence\": 0.8, \"note\": \"why\"}]"
    )

    text = _llm_call(prompt, system="You are a product quality reviewer. Be calibrated.", conn=conn)
    data = _parse_json(text)
    if not data or not isinstance(data, list):
        return meta_findings

    low_confidence = []
    for item in data:
        idx = item.get("index", 0)
        conf = item.get("confidence", 1.0)
        note = item.get("note", "")
        if 0 < idx <= len(top_findings) and conf < 0.4:
            finding = top_findings[idx - 1]
            low_confidence.append(f"{finding.get('title', '?')[:50]} (conf={conf:.1f}: {note})")

    if low_confidence:
        meta_findings.append(_finding(
            "meta", "low",
            f"{len(low_confidence)} findings may be false positives",
            "LLM review flagged these findings as potentially not real problems:\n" +
            "\n".join(f"  - {lc}" for lc in low_confidence),
            "Review these findings manually. Consider adjusting analyzer thresholds.",
            "Review the flagged findings and suppress or adjust the relevant analyzers.",
            "Intelligence accuracy",
            [],
        ))

    return meta_findings


# ─── 3. Validate Scoring Calibration ───────────────────────────

def meta_validate_scoring(conn, dimension_scores: dict) -> list[dict]:
    """Ask LLM if the grading is well-calibrated for the lifecycle phase."""
    findings = []
    if not dimension_scores:
        return findings

    # Build grade distribution
    grade_dist = {}
    suspicious = []
    for dim, info in dimension_scores.items():
        grade = info.get("grade", "?")
        grade_dist[grade] = grade_dist.get(grade, 0) + 1
        # Flag dimensions that score A with 0 findings
        if info.get("score", 0) >= 90 and info.get("finding_count", 0) == 0:
            suspicious.append(dim)

    summary = (
        f"Grade distribution: {json.dumps(grade_dist)}\n"
        f"Total dimensions: {len(dimension_scores)}\n"
        f"Dimensions scoring A with 0 findings: {', '.join(suspicious) if suspicious else 'none'}\n"
    )

    # Add some specific dimension details
    for dim in list(dimension_scores.keys())[:15]:
        info = dimension_scores[dim]
        summary += f"  {dim}: {info.get('grade', '?')} ({info.get('score', 0):.0f}) - {info.get('finding_count', 0)} findings\n"

    prompt = (
        "You are calibrating the grading system of a pre-launch Mandarin learning app's "
        "quality dashboard. Grade thresholds: A=90+, B=80+, C=70+, D=60+, F=<60.\n\n"
        f"SCORING SUMMARY:\n{summary}\n\n"
        "Is this grading well-calibrated? Specifically:\n"
        "1. Are dimensions scoring A/100 with 0 findings actually perfect, or is the system not looking?\n"
        "2. Is the overall grade distribution realistic for a pre-launch solo-dev app?\n"
        "3. Are any dimensions graded too harshly or too leniently?\n\n"
        "Respond in JSON: {\"calibration\": \"good|too_lenient|too_harsh|mixed\", "
        "\"issues\": [{\"dimension\": \"...\", \"current_grade\": \"...\", \"issue\": \"...\"}]}"
    )

    text = _llm_call(prompt, system="You are a measurement calibration expert.", conn=conn)
    data = _parse_json(text)
    if not data:
        return findings

    calibration = data.get("calibration", "good")
    issues = data.get("issues", [])

    if calibration != "good" and issues:
        issue_text = "\n".join(
            f"  - {i.get('dimension', '?')} ({i.get('current_grade', '?')}): {i.get('issue', '')}"
            for i in issues[:5]
        )
        findings.append(_finding(
            "meta", "medium" if calibration in ("too_lenient", "mixed") else "low",
            f"Scoring calibration: {calibration}",
            f"LLM review of the grading system found calibration issues:\n{issue_text}",
            "Adjust grade thresholds, confidence caps, or add missing analyzer criteria.",
            "Review the flagged dimensions and adjust scoring in _base.py or add new analyzers.",
            "Intelligence calibration",
            ["mandarin/intelligence/_base.py"],
        ))

    return findings


# ─── 4. Suggest Missing Criteria for 100/A Dimensions ──────────

def meta_suggest_criteria(conn, dimension: str, all_findings: list[dict]) -> list[dict]:
    """For dimensions scoring 100/A with 0 findings, ask LLM what SHOULD be checked."""
    findings = []

    prompt = (
        f"The quality dimension '{dimension}' in a Mandarin learning app scores 100/A "
        f"with 0 findings. This likely means the analyzers aren't checking enough criteria.\n\n"
        f"The app has: Flask web backend, Capacitor iOS/Android, Tauri macOS, Flutter native, "
        f"spaced repetition, tone grading, AI drills, multi-channel bots, LightGBM difficulty model.\n\n"
        f"What 3-5 specific criteria should the '{dimension}' analyzer check that it's probably missing? "
        f"Be very specific — name files, metrics, or patterns to look for.\n\n"
        f"Respond in JSON: {{\"criteria\": [\"criterion 1\", \"criterion 2\", ...]}}"
    )

    text = _llm_call(prompt, system="You are a quality engineering expert.", conn=conn, max_tokens=400)
    data = _parse_json(text)
    if not data or not data.get("criteria"):
        return findings

    criteria = data["criteria"][:5]
    findings.append(_finding(
        "meta", "low",
        f"Dimension '{dimension}' scores 100/A — {len(criteria)} unchecked criteria suggested",
        f"The '{dimension}' dimension has 0 findings but the LLM suggests these criteria "
        f"should be checked:\n" + "\n".join(f"  - {c}" for c in criteria),
        f"Add analyzer checks for these criteria in the {dimension} analyzer.",
        f"Add checks for: {'; '.join(criteria[:3])} to the {dimension} analyzer.",
        "Intelligence coverage",
        [],
    ))

    return findings


# ─── 5. Review Work Orders Before Execution ────────────────────

def meta_review_work_orders(conn, work_orders: list[dict]) -> list[dict]:
    """Annotate work orders with LLM confidence and risk scores.

    Returns the same work orders with added 'llm_confidence' and 'llm_risk' fields.
    Work orders with llm_risk > 0.7 should be skipped by the auto-executor.
    """
    if not work_orders:
        return work_orders

    wo_text = ""
    for i, wo in enumerate(work_orders):
        wo_text += (
            f"\n{i+1}. [{wo.get('constraint_dimension', '?')}] "
            f"{wo.get('instruction', '?')[:200]}\n"
            f"   Target: {wo.get('target_file', '?')}\n"
        )

    prompt = (
        "Review these work orders that will be auto-executed by an autonomous agent "
        "on a Mandarin learning app. The agent can modify source files.\n\n"
        f"WORK ORDERS:{wo_text}\n\n"
        "For each, rate:\n"
        "- confidence (0-1): How clear and well-defined is the instruction?\n"
        "- risk (0-1): Could autonomous execution break something?\n\n"
        "Respond in JSON: [{\"index\": 1, \"confidence\": 0.8, \"risk\": 0.2, \"note\": \"...\"}]"
    )

    text = _llm_call(prompt, system="You are a code review expert assessing autonomous execution risk.",
                     conn=conn, max_tokens=500)
    data = _parse_json(text)

    # Annotate work orders with LLM scores
    annotated = []
    llm_scores = {}
    if data and isinstance(data, list):
        for item in data:
            idx = item.get("index", 0)
            if 0 < idx <= len(work_orders):
                llm_scores[idx - 1] = item

    for i, wo in enumerate(work_orders):
        wo = dict(wo)  # Don't mutate original
        if i in llm_scores:
            wo["llm_confidence"] = llm_scores[i].get("confidence", 0.5)
            wo["llm_risk"] = llm_scores[i].get("risk", 0.3)
            wo["llm_note"] = llm_scores[i].get("note", "")
        else:
            wo["llm_confidence"] = 0.5
            wo["llm_risk"] = 0.3
        annotated.append(wo)

    return annotated
