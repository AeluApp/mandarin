"""Product Intelligence — Change Generator.

Traverses the influence model to produce specific parameter change
recommendations. Replaces the curated _FINDING_TO_ACTION lookup table.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChangeRecommendation:
    parameter_name: Optional[str]
    file_path: Optional[str]
    current_value: Optional[float]
    recommended_value: Optional[float]
    direction: Optional[str]
    direction_source: str  # 'learned_from_data', 'partially_learned', 'prior_knowledge_only', 'no_data'
    influence_weight: float
    influence_confidence: float
    observation_count: int
    mean_effect_size: Optional[float]
    specific_change: str  # Human-readable instruction
    alternative_parameters: list = field(default_factory=list)
    confidence_note: str = ""


# Maps dimension → primary metric name (aligns with _measure_current_metric)
_DIMENSION_METRICS = {
    "retention": "retention",
    "ux": "ux",
    "engineering": "engineering",
    "frustration": "frustration",
    "profitability": "profitability",
    "onboarding": "onboarding",
    "engagement": "engagement",
    "security": "security",
    "drill_quality": "drill_quality",
    "srs_funnel": "srs_funnel",
    "flow": "flow",
    "curriculum": "curriculum",
    "tone_phonology": "tone_phonology",
    "scheduler_audit": "scheduler_audit",
    "platform": "platform",
    "encounter_loop": "encounter_loop",
    "content": "content",
    "pm": "pm",
    "competitive": "competitive",
    "marketing": "marketing",
    "copy": "copy",
    "ui": "ui",
}


def _direction_source(edge) -> str:
    """Label where the directional recommendation comes from."""
    confidence = edge["weight_confidence"]
    observations = edge["observation_count"]

    if confidence >= 0.70 and observations >= 10:
        return "learned_from_data"
    elif confidence >= 0.40:
        return "partially_learned"
    else:
        return "prior_knowledge_only"


def _confidence_note(edge) -> str:
    """Generate a confidence note for the recommendation."""
    source = _direction_source(edge)
    obs = edge["observation_count"]
    pos = edge["positive_effect_count"]

    if source == "learned_from_data":
        total = pos + edge["negative_effect_count"] + edge["null_effect_count"]
        pct = round(pos * 100 / total) if total > 0 else 0
        return f"Learned from data — {obs} observations, {pct}% positive effect"
    elif source == "partially_learned":
        return f"Partially learned — {obs} observations, confidence building"
    else:
        return "Prior knowledge only — not yet validated by observed outcomes"


def _minimum_step(edge) -> float:
    """Compute minimum recommended change step based on value type."""
    current = edge["current_value"]
    if current is None or current == 0:
        return 0.0

    value_type = edge["value_type"]
    if value_type == "int":
        return 1.0
    elif value_type == "ratio":
        return 0.05
    elif value_type == "bool":
        return 1.0
    else:
        # float — 10% step
        return abs(current) * 0.1


def _edge_to_alternative(edge) -> dict:
    """Convert an influence edge to an alternative parameter summary."""
    source = _direction_source(edge)
    return {
        "parameter_name": edge["parameter_name"],
        "file_path": edge["file_path"],
        "current_value": edge["current_value"],
        "influence_weight": edge["weight"],
        "influence_confidence": edge["weight_confidence"],
        "observations": edge["observation_count"],
        "direction": edge["learned_direction"],
        "direction_source": source,
    }


def _explain_direction(edge, gap: float) -> str:
    """Build a direction explanation from learned data."""
    direction = edge["learned_direction"]
    source = _direction_source(edge)
    obs = edge["observation_count"]

    if source == "learned_from_data":
        return (
            f"Direction ({direction}) learned from {obs} observations. "
            f"Mean effect per change: {edge['mean_delta_achieved']:.2f}."
        )
    elif source == "partially_learned":
        return (
            f"Direction ({direction}) partially learned from {obs} observations. "
            f"Confidence is building."
        )
    else:
        return (
            f"Direction ({direction}) from prior knowledge — "
            f"not yet validated by observed outcomes."
        )


def generate_specific_change(conn, finding) -> ChangeRecommendation:
    """Traverse influence model to generate a specific parameter change.

    Given a finding, finds the highest-confidence parameter to adjust,
    computes direction and magnitude, and returns a structured recommendation.
    Returns an honest fallback if no confident path exists.
    """
    from .feedback_loops import _measure_current_metric

    dimension = finding["dimension"] if isinstance(finding, dict) else finding.get("dimension", "")

    # Find edges relevant to this finding's dimension
    edges = _safe_query_all(conn, """
        SELECT ie.*, pr.parameter_name, pr.file_path,
               pr.current_value, pr.soft_min, pr.soft_max,
               pr.value_type, pr.min_valid, pr.max_valid
        FROM pi_influence_edges ie
        JOIN pi_parameter_registry pr ON pr.id = ie.parameter_id
        WHERE ie.dimension = ?
          AND ie.weight_confidence >= 0.10
        ORDER BY (ie.weight * ie.weight_confidence) DESC
        LIMIT 5
    """, (dimension,))

    if not edges:
        return _honest_fallback(finding)

    best = edges[0]

    # Measure current metric
    metric_name = _DIMENSION_METRICS.get(dimension, dimension)
    current_metric = _measure_current_metric(conn, dimension, metric_name)

    if current_metric is None:
        current_metric = 0.0

    # Get calibrated threshold (target metric value)
    target_metric = _get_target_metric(conn, dimension, current_metric)

    gap = target_metric - current_metric
    mean_effect = best["mean_delta_achieved"] or 0.0

    if best["current_value"] is None:
        return _honest_fallback(finding)

    if mean_effect == 0:
        recommended_delta = _minimum_step(best)
        # Apply direction from prior
        if best["learned_direction"] == "decrease":
            recommended_delta = -recommended_delta
    else:
        # Scale parameter change to close approximately half the gap
        scale_factor = (gap * 0.5) / mean_effect if mean_effect != 0 else 0
        recommended_delta = best["current_value"] * scale_factor
        # Clamp magnitude
        max_delta = abs(best["current_value"]) * 0.5  # max 50% change
        recommended_delta = max(-max_delta, min(max_delta, recommended_delta))

    new_value = best["current_value"] + recommended_delta

    # Clamp to valid range
    if best["soft_max"] is not None:
        new_value = min(new_value, best["soft_max"])
    if best["soft_min"] is not None:
        new_value = max(new_value, best["soft_min"])
    if best["max_valid"] is not None:
        new_value = min(new_value, best["max_valid"])
    if best["min_valid"] is not None:
        new_value = max(new_value, best["min_valid"])

    # Round for value type
    if best["value_type"] == "int":
        new_value = round(new_value)
    elif best["value_type"] == "ratio":
        new_value = round(new_value, 3)
    else:
        new_value = round(new_value, 4)

    # Don't recommend no-op
    if new_value == best["current_value"]:
        step = _minimum_step(best)
        if best["learned_direction"] == "decrease":
            new_value = best["current_value"] - step
        else:
            new_value = best["current_value"] + step
        # Re-clamp
        if best["soft_max"] is not None:
            new_value = min(new_value, best["soft_max"])
        if best["soft_min"] is not None:
            new_value = max(new_value, best["soft_min"])

    direction_explanation = _explain_direction(best, gap)
    direction = "increase" if new_value > best["current_value"] else "decrease"

    return ChangeRecommendation(
        parameter_name=best["parameter_name"],
        file_path=best["file_path"],
        current_value=best["current_value"],
        recommended_value=new_value,
        direction=direction,
        direction_source=_direction_source(best),
        influence_weight=best["weight"],
        influence_confidence=best["weight_confidence"],
        observation_count=best["observation_count"],
        mean_effect_size=mean_effect,
        specific_change=(
            f"In `{best['file_path']}`, change `{best['parameter_name']}` "
            f"from {best['current_value']} to {new_value}. "
            f"{direction_explanation}"
        ),
        alternative_parameters=[
            _edge_to_alternative(e) for e in edges[1:3]
        ],
        confidence_note=_confidence_note(best),
    )


def _honest_fallback(finding) -> ChangeRecommendation:
    """When the influence model has no confident path.

    Returns explicit, typed fallback — never vague advice.
    """
    dimension = finding.get("dimension", "unknown") if isinstance(finding, dict) else "unknown"
    title = finding.get("title", "") if isinstance(finding, dict) else ""

    return ChangeRecommendation(
        parameter_name=None,
        file_path=None,
        current_value=None,
        recommended_value=None,
        direction=None,
        direction_source="no_data",
        influence_weight=0,
        influence_confidence=0,
        observation_count=0,
        mean_effect_size=None,
        specific_change=(
            f"Influence model has no observed interventions for dimension "
            f"'{dimension}' with sufficient confidence. "
            f"Finding: {title}. "
            f"This requires manual investigation before a specific "
            f"parameter change can be recommended. "
            f"After you investigate and act, record the parameter you changed "
            f"and its old/new values so the engine can learn."
        ),
        alternative_parameters=[],
        confidence_note="insufficient_data",
    )


def _get_target_metric(conn, dimension: str, current: float) -> float:
    """Get the target metric value for a dimension.

    Uses calibrated thresholds if available, otherwise a default improvement target.
    """
    # Check for calibrated threshold
    row = _safe_query(conn, """
        SELECT threshold_value FROM pi_threshold_calibration
        WHERE metric_name = ?
    """, (dimension,))

    if row and row["threshold_value"] is not None:
        return row["threshold_value"]

    # Default: aim for 10% improvement (or 10% reduction for error dims)
    from .prescription import _ERROR_DIMENSIONS
    if dimension in _ERROR_DIMENSIONS:
        return current * 0.9  # 10% less errors
    else:
        return current * 1.1 if current > 0 else 10.0  # 10% improvement
