"""Product Intelligence — External Grounding.

Gives the engine external reference points:
1. Pedagogical knowledge base — SLA literature findings the engine checks against
2. Longitudinal benchmarks — population priors for learner trajectories
3. Goal coherence checker — whether optimized metrics match HSK 9 trajectory

Transparency: evidence quality and applicability confidence are always shown.
Knowledge entries can only be added by humans — hard constraint.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC
from uuid import uuid4

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)


# ── Initial Knowledge Entries ────────────────────────────────────────────────

INITIAL_KNOWLEDGE = [
    {
        "domain": "spacing",
        "finding_text": (
            "Optimal spacing intervals for vocabulary retention increase "
            "with item stability. New items benefit from short intervals "
            "(1-3 days). Stable items benefit from longer intervals "
            "(14-60 days). Intervals shorter than optimal produce "
            "over-review without retention benefit."
        ),
        "source_author": "Cepeda et al.",
        "source_year": 2006,
        "source_title": "Distributed practice in verbal recall tasks",
        "evidence_quality": "meta_analysis",
        "applicable_metric": "base_interval_days",
        "applicable_dimension": "srs_funnel",
        "implied_threshold_low": 1.0,
        "implied_threshold_high": 3.0,
        "implied_direction": "range_optimal",
        "applicability_notes": (
            "Applies to new items. Stable items should use longer intervals. "
            "Aelu should check this against current BASE_INTERVAL_DAYS."
        ),
        "applicability_confidence": 0.85,
    },
    {
        "domain": "desirable_difficulty",
        "finding_text": (
            "Target accuracy of 70-85% per session is associated with "
            "optimal learning outcomes. Accuracy above 90% indicates "
            "under-challenge; below 60% indicates over-challenge. "
            "Both extremes reduce long-term retention relative to "
            "the productive difficulty zone."
        ),
        "source_author": "Bjork",
        "source_year": 1994,
        "source_title": "Memory and metamemory considerations in training",
        "evidence_quality": "longitudinal",
        "applicable_metric": "session_accuracy",
        "applicable_dimension": "drill_quality",
        "implied_threshold_low": 0.70,
        "implied_threshold_high": 0.85,
        "implied_direction": "range_optimal",
        "applicability_notes": (
            "This is a general finding. Mandarin tone drills may have "
            "different optimal ranges — tone acquisition is less well studied."
        ),
        "applicability_confidence": 0.75,
    },
    {
        "domain": "tone_acquisition",
        "finding_text": (
            "Non-tonal language speakers learning Mandarin show a "
            "characteristic plateau in tone accuracy at approximately "
            "65-70% during the first 12-18 months. Plateau persists "
            "until learners develop consistent auditory discrimination, "
            "typically requiring explicit tone contrast training rather "
            "than production repetition alone."
        ),
        "source_author": "Miracle & Zhao",
        "source_year": 2014,
        "source_title": "Tone acquisition in Mandarin L2 learners",
        "evidence_quality": "longitudinal",
        "applicable_metric": "tone_accuracy",
        "applicable_dimension": "tone_phonology",
        "implied_threshold_low": 0.65,
        "implied_threshold_high": 0.70,
        "implied_direction": "range_optimal",
        "applicability_notes": (
            "Plateau is normal, not a defect. Engine should not flag "
            "tone accuracy of 65-70% as critical during first 18 months. "
            "Explicit contrast training is the recommended intervention, "
            "not simply more production drills."
        ),
        "applicability_confidence": 0.70,
    },
    {
        "domain": "vocabulary_load",
        "finding_text": (
            "Working memory constraints limit effective new vocabulary "
            "acquisition to approximately 10-15 new items per session "
            "for adult learners. Sessions exceeding this threshold show "
            "diminishing retention for items introduced later in the session."
        ),
        "source_author": "Nation",
        "source_year": 2001,
        "source_title": "Learning Vocabulary in Another Language",
        "evidence_quality": "expert_consensus",
        "applicable_metric": "first_session_item_count",
        "applicable_dimension": "onboarding",
        "implied_threshold_low": 10.0,
        "implied_threshold_high": 15.0,
        "implied_direction": "range_optimal",
        "applicability_notes": (
            "Strong prior for FIRST_SESSION_ITEM_COUNT upper bound. "
            "Engine should flag any recommendation to exceed 15 items "
            "as conflicting with this finding."
        ),
        "applicability_confidence": 0.80,
    },
    {
        "domain": "advanced_acquisition",
        "finding_text": (
            "At advanced proficiency levels (C1/C2 equivalent), "
            "reading fluency and production accuracy become the "
            "primary distinguishing factors. Recognition-based metrics "
            "(recall accuracy, retention rate) lose predictive validity "
            "for advanced outcomes. Production-focused metrics and "
            "reading speed become more relevant."
        ),
        "source_author": "DeKeyser",
        "source_year": 2007,
        "source_title": "Practice in a Second Language",
        "evidence_quality": "theoretical",
        "applicable_metric": None,
        "applicable_dimension": "curriculum",
        "implied_threshold_low": None,
        "implied_threshold_high": None,
        "implied_direction": "context_dependent",
        "applicability_notes": (
            "Critical for goal coherence checking. When Jason reaches "
            "HSK 6+, the engine should flag that its current metric "
            "suite (retention-focused) may need to shift toward "
            "production and fluency metrics."
        ),
        "applicability_confidence": 0.65,
    },
]


# ── Initial Benchmarks ──────────────────────────────────────────────────────

INITIAL_BENCHMARKS = [
    {
        "benchmark_name": "d7_retention_hsk1_3",
        "description": "D7 retention rate for HSK 1-3 learners, non-tonal native speakers",
        "applicable_hsk_range_low": 1,
        "applicable_hsk_range_high": 3,
        "learner_profile": "non_tonal_native",
        "population_median": 0.55,
        "population_p25": 0.42,
        "population_p75": 0.67,
        "population_n": None,
        "aelu_metric_name": "d7_retention",
        "aelu_dimension": "retention",
        "source": "Hardcoded estimate — replace with empirical data when available",
        "source_year": 2024,
        "evidence_quality": "expert_consensus",
    },
    {
        "benchmark_name": "session_accuracy_productive_zone",
        "description": "Session accuracy in productive difficulty zone (Bjork)",
        "applicable_hsk_range_low": 1,
        "applicable_hsk_range_high": 9,
        "learner_profile": "all",
        "population_median": 0.775,
        "population_p25": 0.70,
        "population_p75": 0.85,
        "population_n": None,
        "aelu_metric_name": "session_accuracy",
        "aelu_dimension": "drill_quality",
        "source": "Bjork desirable difficulties framework",
        "source_year": 1994,
        "evidence_quality": "longitudinal",
    },
    {
        "benchmark_name": "tone_accuracy_plateau_phase",
        "description": "Expected tone accuracy during plateau phase (months 6-18)",
        "applicable_hsk_range_low": 1,
        "applicable_hsk_range_high": 3,
        "learner_profile": "non_tonal_native",
        "population_median": 0.675,
        "population_p25": 0.60,
        "population_p75": 0.73,
        "population_n": None,
        "aelu_metric_name": "tone_accuracy",
        "aelu_dimension": "tone_phonology",
        "source": "Miracle & Zhao tone acquisition research",
        "source_year": 2014,
        "evidence_quality": "longitudinal",
    },
]


# ── HSK Progression Model ───────────────────────────────────────────────────

HSK_PROGRESSION_MODEL = {
    (1, 3): {
        "primary": ["d7_retention", "session_accuracy", "stabilization_rate"],
        "secondary": ["tone_accuracy", "onboarding_completion"],
        "watch": ["d30_retention"],
        "not_yet_relevant": ["reading_speed", "production_accuracy", "listening_comprehension"],
        "rationale": (
            "Early acquisition. Recognition and retention are the right targets. "
            "Production and fluency metrics are not meaningful yet."
        ),
    },
    (4, 6): {
        "primary": ["d30_retention", "error_rate_by_type", "curriculum_coverage"],
        "secondary": ["session_accuracy", "tone_accuracy"],
        "watch": ["production_accuracy", "reading_speed"],
        "not_yet_relevant": ["listening_comprehension_native_speed"],
        "rationale": (
            "Intermediate acquisition. Retention remains important but "
            "error type distribution and curriculum coverage become primary. "
            "Production accuracy starts to matter."
        ),
    },
    (7, 9): {
        "primary": ["production_accuracy", "reading_speed", "error_rate_by_type"],
        "secondary": ["d30_retention", "curriculum_coverage"],
        "watch": ["listening_comprehension_native_speed"],
        "not_yet_relevant": ["d7_retention"],
        "rationale": (
            "Advanced acquisition. Production and fluency are the distinguishing "
            "factors. D7 retention is no longer the primary signal — the question "
            "is whether you can use what you know, not whether you remember it."
        ),
    },
}

# Map from metric name to dimension (for goal coherence)
_METRIC_TO_DIMENSION = {
    "d7_retention": "retention",
    "d30_retention": "retention",
    "session_accuracy": "drill_quality",
    "stabilization_rate": "srs_funnel",
    "tone_accuracy": "tone_phonology",
    "onboarding_completion": "onboarding",
    "production_accuracy": "tone_phonology",
    "reading_speed": "curriculum",
    "error_rate_by_type": "drill_quality",
    "curriculum_coverage": "curriculum",
    "listening_comprehension": "engagement",
    "listening_comprehension_native_speed": "engagement",
}

_DIMENSION_TO_PRIMARY_METRIC = {
    "retention": "d7_retention",
    "drill_quality": "session_accuracy",
    "srs_funnel": "stabilization_rate",
    "tone_phonology": "tone_accuracy",
    "onboarding": "onboarding_completion",
    "curriculum": "curriculum_coverage",
    "engagement": "engagement",
    "ux": "ux",
    "engineering": "engineering",
    "frustration": "frustration",
}


# ── Seed Functions ───────────────────────────────────────────────────────────

def seed_knowledge_base(conn) -> int:
    """Seed the pedagogical knowledge base with initial entries.

    Idempotent — skips entries whose source_author+source_year already exist.
    Returns count of entries created.
    """
    count = 0
    for entry in INITIAL_KNOWLEDGE:
        existing = _safe_query(conn, """
            SELECT id FROM pi_pedagogical_knowledge
            WHERE source_author = ? AND source_year = ? AND domain = ?
        """, (entry["source_author"], entry["source_year"], entry["domain"]))
        if existing:
            continue

        try:
            conn.execute("""
                INSERT INTO pi_pedagogical_knowledge
                    (id, domain, finding_text, source_author, source_year,
                     source_title, evidence_quality, applicable_metric,
                     applicable_dimension, implied_threshold_low,
                     implied_threshold_high, implied_direction,
                     applicability_notes, applicability_confidence,
                     encoded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'human')
            """, (
                str(uuid4()), entry["domain"], entry["finding_text"],
                entry["source_author"], entry["source_year"],
                entry["source_title"], entry["evidence_quality"],
                entry["applicable_metric"], entry["applicable_dimension"],
                entry["implied_threshold_low"], entry["implied_threshold_high"],
                entry["implied_direction"],
                entry["applicability_notes"], entry["applicability_confidence"],
            ))
            count += 1
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.warning("Failed to seed knowledge entry %s: %s",
                           entry["source_author"], e)

    if count:
        conn.commit()
    return count


def seed_benchmark_registry(conn) -> int:
    """Seed the benchmark registry with initial entries.

    Idempotent — skips entries whose benchmark_name already exists.
    Returns count of entries created.
    """
    count = 0
    for bm in INITIAL_BENCHMARKS:
        existing = _safe_query(conn, """
            SELECT id FROM pi_benchmark_registry WHERE benchmark_name = ?
        """, (bm["benchmark_name"],))
        if existing:
            continue

        try:
            conn.execute("""
                INSERT INTO pi_benchmark_registry
                    (id, benchmark_name, description,
                     applicable_hsk_range_low, applicable_hsk_range_high,
                     learner_profile, population_median, population_p25,
                     population_p75, population_n, aelu_metric_name,
                     aelu_dimension, source, source_year, evidence_quality)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid4()), bm["benchmark_name"], bm["description"],
                bm["applicable_hsk_range_low"], bm["applicable_hsk_range_high"],
                bm["learner_profile"], bm["population_median"],
                bm["population_p25"], bm["population_p75"],
                bm["population_n"], bm["aelu_metric_name"],
                bm["aelu_dimension"], bm["source"], bm["source_year"],
                bm["evidence_quality"],
            ))
            count += 1
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.warning("Failed to seed benchmark %s: %s",
                           bm["benchmark_name"], e)

    if count:
        conn.commit()
    return count


# ── Knowledge Conflict Detection ─────────────────────────────────────────────

def detect_knowledge_conflicts(conn) -> list:
    """Detect conflicts between engine calibration and pedagogical knowledge.

    For every active knowledge entry with an applicable_metric:
    1. Pull engine's current threshold for that metric/dimension
    2. Compare against literature's implied range
    3. If outside range: log conflict, determine severity, apply resolution rule

    Returns list of conflict dicts.
    """
    findings = []
    knowledge = _safe_query_all(conn, """
        SELECT * FROM pi_pedagogical_knowledge
        WHERE active = 1
          AND applicable_metric IS NOT NULL
          AND superseded_by IS NULL
    """)

    if not knowledge:
        return findings

    for k in knowledge:
        # Get engine's current calibrated threshold
        engine_row = _safe_query(conn, """
            SELECT threshold_value FROM pi_threshold_calibration
            WHERE metric_name = ?
        """, (k["applicable_dimension"],))

        if not engine_row:
            continue

        et = engine_row["threshold_value"]
        lo = k["implied_threshold_low"]
        hi = k["implied_threshold_high"]

        in_range = True
        if lo is not None and et < lo:
            in_range = False
        if hi is not None and et > hi:
            in_range = False

        if in_range:
            continue

        # Check for existing unresolved conflict
        existing = _safe_query(conn, """
            SELECT id FROM pi_knowledge_conflicts
            WHERE knowledge_id = ? AND resolution = 'unresolved'
        """, (k["id"],))
        if existing:
            continue

        severity = _assess_conflict_severity(et, lo, hi, k["evidence_quality"])
        resolution, rationale = _resolve_conflict(
            et, lo, hi, severity, k["evidence_quality"],
            k["applicability_confidence"] or 0.5,
        )

        conflict_id = str(uuid4())
        try:
            conn.execute("""
                INSERT INTO pi_knowledge_conflicts
                    (id, knowledge_id, dimension, metric_name,
                     engine_threshold, literature_threshold_low,
                     literature_threshold_high, literature_direction,
                     evidence_quality, conflict_severity,
                     resolution, resolution_rationale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conflict_id, k["id"], k["applicable_dimension"],
                k["applicable_metric"], et, lo, hi,
                k["implied_direction"], k["evidence_quality"],
                severity, resolution, rationale,
            ))

            # If engine defers, mark as resolved immediately
            if resolution == "engine_defers_to_literature":
                now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("""
                    UPDATE pi_knowledge_conflicts
                    SET resolved_at = ?, resolved_by = 'engine'
                    WHERE id = ?
                """, (now, conflict_id))

            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.warning("Failed to log knowledge conflict: %s", e)
            continue

        findings.append({
            "conflict_id": conflict_id,
            "knowledge_id": k["id"],
            "dimension": k["applicable_dimension"],
            "metric": k["applicable_metric"],
            "severity": severity,
            "resolution": resolution,
            "engine_threshold": et,
            "literature_range": [lo, hi],
            "evidence_quality": k["evidence_quality"],
        })

    return findings


def _assess_conflict_severity(engine_val, lit_low, lit_high, evidence_quality):
    """Assess how severe a conflict is based on gap and evidence quality."""
    # Compute gap magnitude
    if lit_low is not None and engine_val < lit_low:
        gap = abs(engine_val - lit_low)
        ref = lit_low
    elif lit_high is not None and engine_val > lit_high:
        gap = abs(engine_val - lit_high)
        ref = lit_high
    else:
        return "minor"

    gap_pct = gap / ref if ref > 0 else 0

    if evidence_quality in ("meta_analysis", "rct"):
        if gap_pct > 0.30:
            return "critical"
        elif gap_pct > 0.15:
            return "significant"
        else:
            return "moderate"
    elif evidence_quality == "longitudinal":
        if gap_pct > 0.30:
            return "significant"
        elif gap_pct > 0.15:
            return "moderate"
        else:
            return "minor"
    else:
        if gap_pct > 0.30:
            return "moderate"
        else:
            return "minor"


def _resolve_conflict(engine_val, lit_low, lit_high, severity,
                      evidence_quality, applicability_confidence):
    """Apply resolution rules.

    1. Critical severity → human_review_required always
    2. meta_analysis/rct + applicability >= 0.70 → engine defers
    3. longitudinal + applicability >= 0.60 → literature noted, engine proceeds
    4. Otherwise → literature noted, engine proceeds
    """
    if severity == "critical":
        return (
            "human_review_required",
            "Critical conflict requires human review before engine proceeds.",
        )

    if evidence_quality in ("meta_analysis", "rct") and applicability_confidence >= 0.70:
        return (
            "engine_defers_to_literature",
            f"High-quality evidence ({evidence_quality}) with strong applicability "
            f"(confidence: {applicability_confidence:.0%}). Engine adjusts threshold "
            f"toward literature range.",
        )

    if evidence_quality == "longitudinal" and applicability_confidence >= 0.60:
        return (
            "literature_noted_engine_proceeds",
            f"Longitudinal evidence with moderate applicability "
            f"(confidence: {applicability_confidence:.0%}). Conflict flagged for "
            f"human review but engine proceeds with current threshold.",
        )

    return (
        "literature_noted_engine_proceeds",
        f"Lower-quality evidence or uncertain applicability "
        f"(confidence: {applicability_confidence:.0%}). Conflict logged, "
        f"engine proceeds.",
    )


# ── Benchmark Comparison ────────────────────────────────────────────────────

def compare_against_benchmarks(conn) -> list:
    """Compare current metrics against population benchmarks.

    For each active benchmark:
    1. Pull current value for that metric
    2. Compare against population statistics
    3. Estimate percentile
    4. Determine if a finding is warranted

    Returns list of comparison dicts.
    """
    from .feedback_loops import _measure_current_metric

    results = []
    benchmarks = _safe_query_all(conn, """
        SELECT * FROM pi_benchmark_registry WHERE active = 1
    """)

    if not benchmarks:
        return results

    for bm in benchmarks:
        your_value = _measure_current_metric(
            conn, bm["aelu_dimension"], bm["aelu_metric_name"],
        )
        if your_value is None:
            continue

        # Normalize: _measure_current_metric returns percentages (0-100)
        # but benchmarks store as fractions (0-1)
        # Convert your_value to fraction for comparison
        your_value_frac = your_value / 100.0 if your_value > 1.0 else your_value

        p25 = bm["population_p25"]
        p75 = bm["population_p75"]
        median = bm["population_median"]

        if p25 is None or p75 is None or median is None:
            continue

        # Estimate percentile from p25/p75
        if your_value_frac <= p25:
            percentile = 25.0 * (your_value_frac / p25) if p25 > 0 else 0
        elif your_value_frac <= median:
            denom = median - p25
            percentile = 25.0 + 25.0 * (your_value_frac - p25) / denom if denom > 0 else 50.0
        elif your_value_frac <= p75:
            denom = p75 - median
            percentile = 50.0 + 25.0 * (your_value_frac - median) / denom if denom > 0 else 75.0
        else:
            denom = p75 - median
            percentile = 75.0 + 25.0 * min(1.0, (your_value_frac - p75) / denom) if denom > 0 else 100.0

        percentile = max(0.0, min(100.0, percentile))

        # Interpretation
        gap_from_median = your_value_frac - median
        gap_pct = abs(gap_from_median) / median if median > 0 else 0

        # Include population_n uncertainty note
        n_note = ""
        if bm["population_n"] is None:
            n_note = " Note: Population sample size unknown — treat as directional."

        if gap_pct < 0.05:
            interpretation = f"At population median ({median:.1%}).{n_note}"
            finding_warranted = False
        elif gap_from_median > 0:
            interpretation = (
                f"Above population median by {gap_pct:.0%}. "
                f"Approximately {percentile:.0f}th percentile.{n_note}"
            )
            finding_warranted = False
        else:
            interpretation = (
                f"Below population median by {gap_pct:.0%}. "
                f"Approximately {percentile:.0f}th percentile. "
                f"Population median: {median:.1%}, your value: {your_value_frac:.1%}.{n_note}"
            )
            finding_warranted = gap_pct >= 0.15

        try:
            conn.execute("""
                INSERT INTO pi_benchmark_comparisons
                    (id, benchmark_id, your_value, population_median,
                     your_percentile, interpretation, finding_warranted)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid4()), bm["id"], your_value_frac, median,
                round(percentile, 1), interpretation, int(finding_warranted),
            ))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error) as e:
            logger.warning("Failed to record benchmark comparison: %s", e)

        results.append({
            "benchmark": bm["benchmark_name"],
            "your_value": your_value_frac,
            "population_median": median,
            "percentile": round(percentile, 1),
            "finding_warranted": finding_warranted,
            "interpretation": interpretation,
            "evidence_quality": bm["evidence_quality"],
            "population_n": bm["population_n"],
        })

    return results


# ── Goal Coherence Checker ───────────────────────────────────────────────────

def _estimate_current_hsk_level(conn) -> int:
    """Estimate current HSK level from mastery data.

    Uses proportion of content mastered at each HSK level.
    """
    rows = _safe_query_all(conn, """
        SELECT ci.hsk_level,
               COUNT(*) as total,
               SUM(CASE WHEN p.mastery_stage IN ('stable', 'maturing') THEN 1 ELSE 0 END) as mastered
        FROM content_item ci
        LEFT JOIN progress p ON p.content_item_id = ci.id
        WHERE ci.hsk_level IS NOT NULL
        GROUP BY ci.hsk_level
        ORDER BY ci.hsk_level
    """)

    if not rows:
        return 1

    for row in rows:
        total = row["total"] or 0
        mastered = row["mastered"] or 0
        if total > 0 and mastered / total < 0.50:
            return max(1, row["hsk_level"] - 1) if row["hsk_level"] > 1 else 1

    # All levels at 50%+, return the highest level seen
    return rows[-1]["hsk_level"] if rows else 1


def check_goal_coherence(conn) -> dict:
    """Check whether engine optimization targets align with HSK trajectory.

    Runs monthly. Compares currently optimized dimensions against
    what the HSK progression model says should be primary.

    Returns coherence check result dict.
    """
    current_hsk = _estimate_current_hsk_level(conn)

    # Find applicable stage
    stage = None
    stage_range = None
    for (lo, hi), config in HSK_PROGRESSION_MODEL.items():
        if lo <= current_hsk <= hi:
            stage = config
            stage_range = (lo, hi)
            break

    if not stage:
        return {
            "coherent": True,
            "current_hsk": current_hsk,
            "message": "No progression model for current HSK level.",
        }

    # What is the engine currently treating as primary?
    # Proxy: dimensions with the most open findings in the last 30 days
    active_dimensions = _safe_query_all(conn, """
        SELECT dimension, COUNT(*) as cnt
        FROM pi_finding
        WHERE created_at >= datetime('now', '-30 days')
          AND status NOT IN ('resolved', 'rejected')
        GROUP BY dimension
        ORDER BY cnt DESC
        LIMIT 5
    """)

    engine_primary_dims = [r["dimension"] for r in (active_dimensions or [])]

    model_primary = stage["primary"]
    model_not_relevant = stage["not_yet_relevant"]

    coherence_issues = []

    # Metrics engine is optimizing that shouldn't be primary at this stage
    for dim in engine_primary_dims:
        metric = _DIMENSION_TO_PRIMARY_METRIC.get(dim)
        if metric and metric in model_not_relevant:
            coherence_issues.append({
                "type": "optimizing_wrong_metric",
                "dimension": dim,
                "metric": metric,
                "reason": (
                    f"At HSK {current_hsk} (stage {stage_range[0]}-{stage_range[1]}), "
                    f"'{metric}' is not a primary signal for HSK 9 progress. "
                    f"Continuing to optimize it may not advance your actual goal."
                ),
            })

    # Metrics that should be primary but engine isn't tracking
    for metric in model_primary:
        dim = _METRIC_TO_DIMENSION.get(metric)
        if dim and dim not in engine_primary_dims:
            coherence_issues.append({
                "type": "missing_primary_metric",
                "dimension": dim,
                "metric": metric,
                "reason": (
                    f"At HSK {current_hsk}, '{metric}' should be a primary signal. "
                    f"The engine is not currently tracking or optimizing it."
                ),
            })

    coherent = len(coherence_issues) == 0
    if coherent:
        message = (
            f"Engine optimization targets are coherent with HSK {current_hsk} "
            f"acquisition stage (HSK {stage_range[0]}-{stage_range[1]}). "
            f"No adjustment recommended."
        )
    else:
        lines = [
            f"Goal coherence check: {len(coherence_issues)} issue(s) detected "
            f"at estimated HSK {current_hsk}.",
        ]
        for issue in coherence_issues:
            lines.append(f"  - {issue['reason']}")
        lines.append(
            f"Source: HSK progression model + DeKeyser skill acquisition framework."
        )
        message = "\n".join(lines)

    # Persist
    check_id = str(uuid4())
    try:
        conn.execute("""
            INSERT INTO pi_goal_coherence_check
                (id, estimated_hsk_level, stage_range_low, stage_range_high,
                 coherent, issues_json, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            check_id, current_hsk, stage_range[0], stage_range[1],
            int(coherent), json.dumps(coherence_issues) if coherence_issues else None,
            message,
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.warning("Failed to persist goal coherence check: %s", e)

    return {
        "id": check_id,
        "coherent": coherent,
        "current_hsk": current_hsk,
        "stage": stage_range,
        "rationale": stage["rationale"],
        "issues": coherence_issues,
        "message": message,
    }


# ── External Grounding Summary (for self-audit) ─────────────────────────────

def get_external_grounding_summary(conn) -> dict:
    """Generate external grounding section for the self-audit report.

    Covers: knowledge conflicts, benchmark comparisons, goal coherence,
    knowledge base health.
    """
    # Knowledge conflicts (last 30 days)
    active_conflicts = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_knowledge_conflicts
        WHERE resolution = 'unresolved'
    """, default=0)

    deferred = _safe_query_all(conn, """
        SELECT kc.dimension, kc.engine_threshold,
               kc.literature_threshold_low, kc.literature_threshold_high,
               kc.evidence_quality, kc.resolution_rationale,
               pk.source_author
        FROM pi_knowledge_conflicts kc
        JOIN pi_pedagogical_knowledge pk ON pk.id = kc.knowledge_id
        WHERE kc.resolution = 'engine_defers_to_literature'
          AND kc.resolved_at >= datetime('now', '-30 days')
    """) or []

    human_review = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_knowledge_conflicts
        WHERE resolution = 'human_review_required'
          AND resolved_at IS NULL
    """, default=0)

    engine_proceeds = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_knowledge_conflicts
        WHERE resolution = 'literature_noted_engine_proceeds'
          AND detected_at >= datetime('now', '-30 days')
    """, default=0)

    # Benchmark comparisons (most recent per benchmark)
    above_median = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT bc.benchmark_id)
        FROM pi_benchmark_comparisons bc
        INNER JOIN (
            SELECT benchmark_id, MAX(compared_at) as latest
            FROM pi_benchmark_comparisons GROUP BY benchmark_id
        ) latest ON bc.benchmark_id = latest.benchmark_id
            AND bc.compared_at = latest.latest
        WHERE bc.your_percentile >= 50
    """, default=0)

    below_median = _safe_scalar(conn, """
        SELECT COUNT(DISTINCT bc.benchmark_id)
        FROM pi_benchmark_comparisons bc
        INNER JOIN (
            SELECT benchmark_id, MAX(compared_at) as latest
            FROM pi_benchmark_comparisons GROUP BY benchmark_id
        ) latest ON bc.benchmark_id = latest.benchmark_id
            AND bc.compared_at = latest.latest
        WHERE bc.your_percentile < 50
    """, default=0)

    significant_gaps = _safe_query_all(conn, """
        SELECT bc.your_value, bc.population_median, bc.your_percentile,
               bc.interpretation, br.benchmark_name
        FROM pi_benchmark_comparisons bc
        JOIN pi_benchmark_registry br ON br.id = bc.benchmark_id
        INNER JOIN (
            SELECT benchmark_id, MAX(compared_at) as latest
            FROM pi_benchmark_comparisons GROUP BY benchmark_id
        ) latest ON bc.benchmark_id = latest.benchmark_id
            AND bc.compared_at = latest.latest
        WHERE bc.finding_warranted = 1
    """) or []

    # Goal coherence
    latest_coherence = _safe_query(conn, """
        SELECT * FROM pi_goal_coherence_check
        ORDER BY checked_at DESC LIMIT 1
    """)

    # Knowledge base health
    active_entries = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_pedagogical_knowledge WHERE active = 1
    """, default=0)

    stale_entries = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_pedagogical_knowledge
        WHERE active = 1
          AND (last_reviewed IS NULL AND encoded_at <= datetime('now', '-365 days'))
          OR (last_reviewed IS NOT NULL AND last_reviewed <= datetime('now', '-365 days'))
    """, default=0)

    superseded = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_pedagogical_knowledge
        WHERE superseded_by IS NOT NULL
    """, default=0)

    return {
        "knowledge_conflicts": {
            "active_unresolved": active_conflicts,
            "engine_deferred_count": len(deferred),
            "engine_deferred_details": [
                {
                    "dimension": d["dimension"],
                    "engine_threshold": d["engine_threshold"],
                    "literature_range": [d["literature_threshold_low"],
                                         d["literature_threshold_high"]],
                    "source": d["source_author"],
                    "evidence_quality": d["evidence_quality"],
                }
                for d in deferred
            ],
            "human_review_required": human_review,
            "engine_proceeded_count": engine_proceeds,
        },
        "benchmark_comparisons": {
            "above_median": above_median,
            "below_median": below_median,
            "significant_gaps": [
                {
                    "benchmark": g["benchmark_name"],
                    "your_value": g["your_value"],
                    "population_median": g["population_median"],
                    "percentile": g["your_percentile"],
                }
                for g in significant_gaps
            ],
        },
        "goal_coherence": {
            "last_checked": latest_coherence["checked_at"] if latest_coherence else None,
            "status": "coherent" if (latest_coherence and latest_coherence["coherent"]) else (
                f"{len(json.loads(latest_coherence['issues_json'] or '[]'))} issues detected"
                if latest_coherence else "never_checked"
            ),
            "estimated_hsk": latest_coherence["estimated_hsk_level"] if latest_coherence else None,
        },
        "knowledge_base_health": {
            "active_entries": active_entries,
            "stale_entries": stale_entries,
            "superseded_entries": superseded,
        },
    }


# ── Knowledge Base Read/Write ────────────────────────────────────────────────

def get_knowledge_base(conn) -> list:
    """Return all active pedagogical knowledge entries."""
    rows = _safe_query_all(conn, """
        SELECT * FROM pi_pedagogical_knowledge
        WHERE active = 1
        ORDER BY domain, source_year DESC
    """)
    return [dict(r) for r in (rows or [])]


def get_knowledge_entry(conn, knowledge_id: str) -> dict:
    """Return a single knowledge entry."""
    row = _safe_query(conn, """
        SELECT * FROM pi_pedagogical_knowledge WHERE id = ?
    """, (knowledge_id,))
    return dict(row) if row else None


def add_knowledge_entry(conn, entry: dict) -> str:
    """Add a new knowledge entry. Only callable by humans.

    Returns the entry id.
    """
    entry_id = str(uuid4())
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT INTO pi_pedagogical_knowledge
                (id, domain, finding_text, source_author, source_year,
                 source_title, evidence_quality, applicable_metric,
                 applicable_dimension, implied_threshold_low,
                 implied_threshold_high, implied_direction,
                 applicability_notes, applicability_confidence,
                 encoded_at, encoded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'human')
        """, (
            entry_id, entry["domain"], entry["finding_text"],
            entry["source_author"], entry["source_year"],
            entry["source_title"], entry["evidence_quality"],
            entry.get("applicable_metric"),
            entry.get("applicable_dimension"),
            entry.get("implied_threshold_low"),
            entry.get("implied_threshold_high"),
            entry.get("implied_direction"),
            entry.get("applicability_notes"),
            entry.get("applicability_confidence"),
            now,
        ))
        conn.commit()
        return entry_id
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to add knowledge entry: %s", e)
        return None


def get_knowledge_conflicts(conn, include_resolved=False) -> list:
    """Return knowledge conflicts."""
    if include_resolved:
        rows = _safe_query_all(conn, """
            SELECT kc.*, pk.source_author, pk.source_title, pk.finding_text,
                   pk.evidence_quality as knowledge_evidence_quality
            FROM pi_knowledge_conflicts kc
            JOIN pi_pedagogical_knowledge pk ON pk.id = kc.knowledge_id
            ORDER BY kc.detected_at DESC
        """)
    else:
        rows = _safe_query_all(conn, """
            SELECT kc.*, pk.source_author, pk.source_title, pk.finding_text,
                   pk.evidence_quality as knowledge_evidence_quality
            FROM pi_knowledge_conflicts kc
            JOIN pi_pedagogical_knowledge pk ON pk.id = kc.knowledge_id
            WHERE kc.resolution != 'unresolved'
               OR kc.resolved_at IS NULL
            ORDER BY kc.detected_at DESC
        """)
    return [dict(r) for r in (rows or [])]


def resolve_conflict(conn, conflict_id: str, resolution: str,
                     rationale: str) -> bool:
    """Human resolves a knowledge conflict."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            UPDATE pi_knowledge_conflicts
            SET resolution = ?, resolution_rationale = ?,
                resolved_at = ?, resolved_by = 'human'
            WHERE id = ?
        """, (resolution, rationale, now, conflict_id))
        conn.commit()
        return True
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to resolve conflict: %s", e)
        return False


def get_benchmark_comparisons(conn) -> list:
    """Return benchmark registry with most recent comparisons."""
    benchmarks = _safe_query_all(conn, """
        SELECT * FROM pi_benchmark_registry WHERE active = 1
        ORDER BY aelu_dimension, benchmark_name
    """)

    result = []
    for bm in (benchmarks or []):
        latest = _safe_query(conn, """
            SELECT * FROM pi_benchmark_comparisons
            WHERE benchmark_id = ?
            ORDER BY compared_at DESC LIMIT 1
        """, (bm["id"],))

        item = dict(bm)
        if latest:
            item["latest_comparison"] = {
                "your_value": latest["your_value"],
                "percentile": latest["your_percentile"],
                "interpretation": latest["interpretation"],
                "finding_warranted": latest["finding_warranted"],
                "compared_at": latest["compared_at"],
            }
        else:
            item["latest_comparison"] = None
        result.append(item)

    return result


def get_latest_goal_coherence(conn) -> dict:
    """Return the most recent goal coherence check."""
    row = _safe_query(conn, """
        SELECT * FROM pi_goal_coherence_check
        ORDER BY checked_at DESC LIMIT 1
    """)
    if not row:
        return {"status": "never_checked"}

    return {
        "id": row["id"],
        "checked_at": row["checked_at"],
        "estimated_hsk_level": row["estimated_hsk_level"],
        "stage_range": [row["stage_range_low"], row["stage_range_high"]],
        "coherent": bool(row["coherent"]),
        "issues": json.loads(row["issues_json"]) if row["issues_json"] else [],
        "message": row["message"],
    }


def get_stale_knowledge_entries(conn) -> list:
    """Return knowledge entries that need review (> 365 days since last review)."""
    rows = _safe_query_all(conn, """
        SELECT * FROM pi_pedagogical_knowledge
        WHERE active = 1
          AND (
            (last_reviewed IS NULL AND encoded_at <= datetime('now', '-365 days'))
            OR (last_reviewed IS NOT NULL AND last_reviewed <= datetime('now', '-365 days'))
          )
        ORDER BY encoded_at
    """)
    return [dict(r) for r in (rows or [])]
