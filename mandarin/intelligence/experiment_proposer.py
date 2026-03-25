"""Experiment proposer — template-based + LLM-generative experiment design.

Given a finding from the product intelligence engine, proposes an A/B experiment:
1. First tries to match a template (fast, deterministic, no LLM cost).
2. If no template matches, falls back to LLM-generative design.

The output format matches what experiment_daemon.py and experiment_proposal table expect.
"""

import json
import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Valid scopes for experiment proposals ──────────────────────────────
VALID_SCOPES = {
    "parameter", "ui", "content", "business",
    "marketing", "architecture",
}

# ── Template registry: dimension/keyword → experiment template ─────────
# Each template must include: name, description, hypothesis, variants, scope.
# Templates are checked in order; first match wins.

_TEMPLATES: list[dict[str, Any]] = [
    # Churn-type templates (migrated from experiment_daemon)
    {
        "match": {"dimension": "retention", "keywords": ["boredom"]},
        "name": "auto_drill_variety",
        "description": "Test increased drill type variety for users showing boredom signals",
        "hypothesis": "More varied drill types reduce boredom-driven churn",
        "variants": ["control", "high_variety"],
        "scope": "parameter",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "retention", "keywords": ["frustration"]},
        "name": "auto_difficulty_easing",
        "description": "Test reduced difficulty for users showing frustration signals",
        "hypothesis": "Easier initial difficulty reduces frustration-driven churn",
        "variants": ["control", "easier_start"],
        "scope": "parameter",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "retention", "keywords": ["habit", "fade"]},
        "name": "auto_session_length",
        "description": "Test shorter sessions for users whose study habit is fading",
        "hypothesis": "Shorter sessions maintain habit better than longer ones",
        "variants": ["control", "short_sessions"],
        "scope": "parameter",
        "duration_days": 14,
    },
    # Onboarding templates
    {
        "match": {"dimension": "onboarding", "keywords": ["drop-off", "abandon", "completion"]},
        "name": "auto_onboarding_simplify",
        "description": "Test simplified onboarding flow for higher completion",
        "hypothesis": "Fewer onboarding steps increase completion rate",
        "variants": ["control", "simplified_onboarding"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Engagement templates
    {
        "match": {"dimension": "engagement", "keywords": ["session", "short", "duration"]},
        "name": "auto_session_nudge",
        "description": "Test session extension nudges for low-engagement users",
        "hypothesis": "Gentle nudges to continue studying increase session length",
        "variants": ["control", "session_nudge"],
        "scope": "ui",
        "duration_days": 14,
    },
    # Drill quality templates
    {
        "match": {"dimension": "drill_quality", "keywords": ["error", "accuracy", "wrong"]},
        "name": "auto_hint_system",
        "description": "Test hint-based scaffolding for drills with high error rates",
        "hypothesis": "Progressive hints reduce error rates without reducing learning",
        "variants": ["control", "progressive_hints"],
        "scope": "content",
        "duration_days": 21,
    },
    # Scheduling templates
    {
        "match": {"dimension": "scheduler_audit", "keywords": ["interval", "spacing", "review"]},
        "name": "auto_srs_tuning",
        "description": "Test adjusted SRS intervals for better retention",
        "hypothesis": "Tighter SRS intervals improve long-term retention",
        "variants": ["control", "tighter_intervals"],
        "scope": "parameter",
        "duration_days": 30,
    },
    # Frustration templates
    {
        "match": {"dimension": "frustration", "keywords": ["difficult", "hard", "struggle"]},
        "name": "auto_adaptive_difficulty",
        "description": "Test adaptive difficulty scaling based on recent performance",
        "hypothesis": "Dynamic difficulty reduces frustration without undermining challenge",
        "variants": ["control", "adaptive_difficulty"],
        "scope": "parameter",
        "duration_days": 14,
    },
    # Visual vibe templates — aesthetic A/B tests
    {
        "match": {"dimension": "visual_vibe", "keywords": ["color", "palette", "warmth", "accent"]},
        "name": "auto_color_warmth_test",
        "description": "Test warmer accent palette for improved visual harmony",
        "hypothesis": "Warmer accent tones improve session completion and perceived quality",
        "variants": ["control", "warmer_accent"],
        "scope": "ui",
        "duration_days": 21,
    },
    {
        "match": {"dimension": "visual_vibe", "keywords": ["typography", "size", "scale", "heading"]},
        "name": "auto_type_scale_test",
        "description": "Test adjusted type scale for better reading hierarchy",
        "hypothesis": "Larger heading contrast improves content scanability and engagement",
        "variants": ["control", "larger_headings"],
        "scope": "ui",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "visual_vibe", "keywords": ["motion", "transition", "speed", "animation"]},
        "name": "auto_motion_speed_test",
        "description": "Test adjusted animation timing for smoother perceived quality",
        "hypothesis": "Slightly slower transitions improve perceived craftsmanship",
        "variants": ["control", "slower_motion"],
        "scope": "ui",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "visual_vibe", "keywords": ["shadow", "depth", "elevation", "card"]},
        "name": "auto_card_depth_test",
        "description": "Test increased shadow depth for dimensional richness",
        "hypothesis": "Deeper shadows improve visual hierarchy and perceived premium quality",
        "variants": ["control", "deeper_shadows"],
        "scope": "ui",
        "duration_days": 14,
    },
    {
        "match": {"dimension": "visual_vibe", "keywords": ["texture", "grain", "surface", "noise"]},
        "name": "auto_texture_intensity_test",
        "description": "Test increased paper-grain texture for tactile warmth",
        "hypothesis": "More visible grain texture improves warmth perception without distraction",
        "variants": ["control", "heavier_grain"],
        "scope": "ui",
        "duration_days": 21,
    },
]


def propose_experiment(
    conn: sqlite3.Connection,
    finding: dict[str, Any],
    *,
    source: str = "intelligence",
) -> dict[str, Any] | None:
    """Propose an A/B experiment for a product-intelligence finding.

    Tries template matching first, then falls back to LLM-generative design.

    Args:
        conn: DB connection (used for LLM cache + dedup checks).
        finding: A product-intelligence finding dict with at least
                 dimension, title, analysis, recommendation.
        source: Source label for the proposal (default "intelligence").

    Returns:
        Experiment proposal dict ready for insertion into experiment_proposal,
        or None if no experiment could be designed.
    """
    # 1. Try template match
    proposal = _match_template(finding)

    # 2. Fallback: LLM-generative design
    if proposal is None:
        proposal = _generate_experiment_llm(conn, finding)

    if proposal is None:
        return None

    # Ensure scope is valid
    if proposal.get("scope") not in VALID_SCOPES:
        proposal["scope"] = "parameter"

    # Attach source metadata
    proposal["source"] = source
    proposal["source_detail"] = json.dumps({
        "dimension": finding.get("dimension", ""),
        "title": finding.get("title", ""),
        "severity": finding.get("severity", ""),
    })

    return proposal


def _match_template(finding: dict[str, Any]) -> dict[str, Any] | None:
    """Try to match a finding against the template registry.

    Matching rules:
    - If template specifies a dimension, finding dimension must match.
    - If template specifies keywords, at least one must appear in the
      finding's title, analysis, or recommendation (case-insensitive).
    """
    dimension = finding.get("dimension", "")
    # Build a searchable text blob from the finding
    text_blob = " ".join([
        finding.get("title", ""),
        finding.get("analysis", ""),
        finding.get("recommendation", ""),
    ]).lower()

    for template in _TEMPLATES:
        match_spec = template["match"]

        # Dimension check
        if match_spec.get("dimension") and match_spec["dimension"] != dimension:
            continue

        # Keyword check — at least one keyword must appear
        keywords = match_spec.get("keywords", [])
        if keywords and not any(kw.lower() in text_blob for kw in keywords):
            continue

        # Match found — build proposal
        return {
            "name": template["name"],
            "description": template["description"],
            "hypothesis": template["hypothesis"],
            "variants": template["variants"],
            "scope": template.get("scope", "parameter"),
            "duration_days": template.get("duration_days", 14),
            "llm_generated": False,
        }

    return None


def _generate_experiment_llm(
    conn: sqlite3.Connection,
    finding: dict[str, Any],
) -> dict[str, Any] | None:
    """Use the LLM to design an A/B experiment when no template matches.

    Sends a structured prompt to the LLM asking it to design a 2-variant
    experiment. Parses the JSON response and returns a proposal dict in
    the same format as template matches.

    Returns None on any failure (LLM unavailable, parse error, etc.).
    Never raises.
    """
    try:
        from ..ai.ollama_client import generate
    except ImportError:
        logger.debug("ollama_client not available — skipping LLM experiment design")
        return None

    dimension = finding.get("dimension", "unknown")
    title = finding.get("title", "")
    analysis = finding.get("analysis", "")
    recommendation = finding.get("recommendation", "")

    # Build aesthetic context if this is a visual/aesthetic finding
    aesthetic_ctx = ""
    if dimension in ("visual_vibe", "ui", "brand_health"):
        aesthetic_ctx = (
            "\n\nAESTHETIC CONTEXT:\n"
            "This is a visual/aesthetic finding. The experiment can test ANY visual aspect:\n"
            "- Individual images, illustrations, or assets (swap for a generated alternative)\n"
            "- Animation curves, durations, or easing functions\n"
            "- Color temperature, saturation, or specific hex values\n"
            "- Typography size, weight, line-height, or font choice\n"
            "- Shadow depth, blur, or spread values\n"
            "- Texture intensity (paper grain, noise overlay opacity)\n"
            "- Layout spacing, padding, margins, or grid gaps\n"
            "- Overall page gestalt (the holistic visual impression of a whole screen)\n"
            "- Specific component styling (buttons, cards, inputs, headers)\n"
            "- Dark mode specific adjustments\n"
            "- Scroll-driven animation intensity or parallax speed\n"
            "- WebGL atmosphere opacity, color blending, or mouse sensitivity\n"
            "- AI-generated images vs. current illustrations\n"
            "- Video backgrounds vs. static images\n"
            "- Sound-to-visual synchronization timing\n"
            "The app uses a 'Civic Sanctuary' aesthetic: warm Mediterranean, serif typography, "
            "no decoration without function. Feature flags control variants via CSS custom "
            "properties or JS conditionals.\n"
        )

    prompt = f"""Design a 2-variant A/B experiment for this product finding:

DIMENSION: {dimension}
TITLE: {title}
ANALYSIS: {analysis}
RECOMMENDATION: {recommendation}
{aesthetic_ctx}
The experiment should:
1. Have a clear hypothesis
2. Define variant_a (control) and variant_b (the change)
3. Specify a measurable success metric
4. Be implementable by a solo developer
5. Can be ANY type: parameter change, UI redesign, business model test, marketing copy, content strategy, scheduling algorithm, pricing, onboarding flow, etc.

Respond in JSON only, no other text:
{{"hypothesis": "...", "variant_a": {{"name": "control", "description": "..."}}, "variant_b": {{"name": "...", "description": "...", "changes": ["change 1", "change 2"]}}, "metric": "...", "duration_days": N, "scope": "parameter|ui|content|business|marketing|architecture"}}"""

    system = (
        "You are an A/B experiment designer for a Mandarin learning app. "
        "Respond with valid JSON only. No markdown fences, no explanation."
    )

    try:
        resp = generate(
            prompt=prompt,
            system=system,
            temperature=0.4,
            max_tokens=512,
            use_cache=True,
            conn=conn,
            task_type="experiment_design",
        )
    except Exception:
        logger.debug("LLM call failed for experiment design", exc_info=True)
        return None

    if not resp or not resp.success or not resp.text:
        logger.debug("LLM experiment design returned no usable response")
        return None

    # Parse JSON from response (handle markdown fences if present)
    return _parse_llm_experiment(resp.text, finding)


def _parse_llm_experiment(
    raw_text: str,
    finding: dict[str, Any],
) -> dict[str, Any] | None:
    """Parse and validate LLM JSON response into a proposal dict.

    Handles common LLM quirks: markdown fences, trailing commas, extra text.
    Returns None if parsing fails or required fields are missing.
    """
    try:
        # Strip markdown code fences if present
        text = raw_text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        # Try to find JSON object in the text
        # (LLM may include preamble or trailing text)
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start == -1 or brace_end == -1 or brace_end <= brace_start:
            logger.debug("No JSON object found in LLM response")
            return None

        json_str = text[brace_start:brace_end + 1]
        data = json.loads(json_str)

        # Validate required fields
        hypothesis = data.get("hypothesis", "").strip()
        if not hypothesis:
            logger.debug("LLM experiment missing hypothesis")
            return None

        variant_a = data.get("variant_a", {})
        variant_b = data.get("variant_b", {})
        if not isinstance(variant_a, dict) or not isinstance(variant_b, dict):
            logger.debug("LLM experiment variants not dicts")
            return None

        metric = data.get("metric", "").strip()
        if not metric:
            logger.debug("LLM experiment missing metric")
            return None

        # Extract variant names
        va_name = variant_a.get("name", "control")
        vb_name = variant_b.get("name", "treatment")

        # Sanitize duration
        try:
            duration_days = int(data.get("duration_days", 14))
            duration_days = max(7, min(duration_days, 90))  # clamp 7..90
        except (ValueError, TypeError):
            duration_days = 14

        # Sanitize scope
        scope = data.get("scope", "parameter")
        if isinstance(scope, str) and "|" in scope:
            # LLM may return the template literally "parameter|ui|..."
            scope = scope.split("|")[0]
        if scope not in VALID_SCOPES:
            scope = "parameter"

        # Build description from variant details
        va_desc = variant_a.get("description", "Current behavior (control)")
        vb_desc = variant_b.get("description", "Modified behavior")
        vb_changes = variant_b.get("changes", [])

        description_parts = [
            f"Hypothesis: {hypothesis}",
            f"Control: {va_desc}",
            f"Treatment: {vb_desc}",
            f"Metric: {metric}",
        ]
        if vb_changes:
            description_parts.append("Changes: " + "; ".join(str(c) for c in vb_changes[:5]))

        # Build a safe experiment name from the finding
        dimension = finding.get("dimension", "unknown")
        safe_title = re.sub(r"[^a-z0-9]+", "_", finding.get("title", "experiment").lower())
        safe_title = safe_title[:40].strip("_")
        name = f"llm_{dimension}_{safe_title}"

        return {
            "name": name,
            "description": "\n".join(description_parts),
            "hypothesis": hypothesis,
            "variants": [va_name, vb_name],
            "scope": scope,
            "duration_days": duration_days,
            "metric": metric,
            "llm_generated": True,
            "llm_design": {
                "variant_a": variant_a,
                "variant_b": variant_b,
                "metric": metric,
            },
        }

    except json.JSONDecodeError as e:
        logger.debug("Failed to parse LLM experiment JSON: %s", e)
        return None
    except Exception:
        logger.debug("Unexpected error parsing LLM experiment", exc_info=True)
        return None


def propose_experiments_for_findings(
    conn: sqlite3.Connection,
    findings: list[dict[str, Any]],
    *,
    max_proposals: int = 3,
    source: str = "intelligence",
) -> list[dict[str, Any]]:
    """Batch-propose experiments for a list of findings.

    Skips findings that already have pending/active proposals or experiments.
    Returns up to max_proposals experiment proposals.
    """
    proposals = []

    for finding in findings:
        if len(proposals) >= max_proposals:
            break

        proposal = propose_experiment(conn, finding, source=source)
        if proposal is None:
            continue

        name = proposal["name"]

        # Dedup: skip if already proposed or running
        try:
            existing = conn.execute(
                "SELECT id FROM experiment_proposal WHERE name = ? AND status IN ('pending', 'started')",
                (name,),
            ).fetchone()
            if existing:
                continue

            existing_exp = conn.execute(
                "SELECT id FROM experiment WHERE name = ? AND status IN ('draft', 'running')",
                (name,),
            ).fetchone()
            if existing_exp:
                continue
        except sqlite3.OperationalError:
            # Table may not exist yet
            pass

        proposals.append(proposal)

    return proposals
