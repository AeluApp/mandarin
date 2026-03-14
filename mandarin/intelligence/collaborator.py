"""Product Intelligence — Collaborator Model.

Models the human's decision-making patterns, adapts presentation to work
with their grain, and calibrates trust by domain — all while making every
adaptation visible and reversible.

Transparency constraint: every behavioral adaptation is attributable,
visible, contestable, reversible, and non-manipulative.
"""

import json
import logging
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ._base import _safe_query, _safe_query_all, _safe_scalar

logger = logging.getLogger(__name__)

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ── Interaction Logging ──────────────────────────────────────────────────────

def log_interaction(
    conn, interaction_type: str,
    work_order_id=None, finding_id=None, dimension=None,
    severity=None, model_confidence=None,
    was_constraint_dimension=None, notes=None,
):
    """Record an interaction in pi_interaction_log.

    Only called from admin route handlers — never from analyzers or background jobs.
    """
    now = datetime.now(timezone.utc)
    day_of_week = now.weekday()
    hour_of_day = now.hour

    # Compute days since work order issued
    days_since = None
    if work_order_id:
        wo = _safe_query(conn, """
            SELECT created_at FROM pi_work_order WHERE id = ?
        """, (work_order_id,))
        if wo and wo["created_at"]:
            try:
                created = datetime.strptime(wo["created_at"], "%Y-%m-%d %H:%M:%S")
                days_since = (now - created.replace(tzinfo=timezone.utc)).days
            except (ValueError, TypeError):
                pass

    try:
        conn.execute("""
            INSERT INTO pi_interaction_log
                (id, interaction_type, work_order_id, finding_id, dimension,
                 day_of_week, hour_of_day, days_since_work_order_issued,
                 model_confidence_at_time, severity_at_time,
                 was_constraint_dimension, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid4()), interaction_type,
            work_order_id, finding_id, dimension,
            day_of_week, hour_of_day, days_since,
            model_confidence, severity,
            was_constraint_dimension, notes,
        ))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.warning("Failed to log interaction: %s", e)


# ── Collaborator Model Building ──────────────────────────────────────────────

def rebuild_collaborator_model(conn) -> dict:
    """Rebuild the collaborator model from pi_interaction_log.

    Called weekly or after significant batches of new interactions.
    Returns the model dict.
    """
    obs = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_interaction_log", default=0)

    if obs < 10:
        model = {
            "observation_count": obs,
            "data_quality": "insufficient",
            "model_notes": (
                f"Only {obs} interactions recorded. "
                f"Collaborator model requires at least 10 interactions "
                f"before any patterns can be inferred. "
                f"No adaptations are active."
            ),
        }
        _write_model(conn, model)
        return model

    timing = _compute_timing_patterns(conn)
    overrides = _compute_override_patterns(conn)
    prefs = _compute_presentation_preferences(conn)
    quality = _assess_data_quality(obs, timing, overrides, prefs)
    notes = _generate_model_notes(obs, timing, overrides, prefs, quality)

    model = {
        "observation_count": obs,
        "data_quality": quality,
        "model_notes": notes,
        **timing,
        **overrides,
        **prefs,
    }

    # Snapshot before overwriting
    old = _safe_query(conn, """
        SELECT model_json, observation_count_at_snapshot
        FROM pi_collaborator_model_history
        ORDER BY snapshot_at DESC LIMIT 1
    """)

    if old and old["model_json"]:
        try:
            old_model = json.loads(old["model_json"])
            change = _describe_significant_change(old_model, model)
        except (json.JSONDecodeError, TypeError):
            change = "Model rebuild (prior snapshot unreadable)."
    else:
        change = "Initial model build."

    _write_model(conn, model)
    _snapshot_model(conn, model, obs, change)

    return model


def _compute_timing_patterns(conn) -> dict:
    """Compute implementation timing patterns from interaction log."""
    rows = _safe_query_all(conn, """
        SELECT dimension, day_of_week, hour_of_day, days_since_work_order_issued
        FROM pi_interaction_log
        WHERE interaction_type = 'work_order_implemented'
          AND days_since_work_order_issued IS NOT NULL
    """)

    if not rows or len(rows) < 5:
        return {
            "median_implementation_days": None,
            "fastest_dimension": None,
            "slowest_dimension": None,
            "preferred_day_of_week": None,
            "preferred_hour_of_day": None,
            "timing_confidence": 0.1,
        }

    days = [r["days_since_work_order_issued"] for r in rows]
    median_days = sorted(days)[len(days) // 2]

    by_dim = defaultdict(list)
    for r in rows:
        if r["dimension"]:
            by_dim[r["dimension"]].append(r["days_since_work_order_issued"])

    dim_medians = {
        dim: sorted(vals)[len(vals) // 2]
        for dim, vals in by_dim.items()
        if len(vals) >= 3
    }

    fastest = min(dim_medians, key=dim_medians.get) if dim_medians else None
    slowest = max(dim_medians, key=dim_medians.get) if dim_medians else None

    day_counts = Counter(r["day_of_week"] for r in rows if r["day_of_week"] is not None)
    preferred_day = day_counts.most_common(1)[0][0] if day_counts else None

    hour_counts = Counter(r["hour_of_day"] for r in rows if r["hour_of_day"] is not None)
    preferred_hour = hour_counts.most_common(1)[0][0] if hour_counts else None

    confidence = min(0.90, 0.1 + 0.8 * (1 - 1 / (len(rows) + 1)))

    return {
        "median_implementation_days": median_days,
        "fastest_dimension": fastest,
        "slowest_dimension": slowest,
        "preferred_day_of_week": preferred_day,
        "preferred_hour_of_day": preferred_hour,
        "timing_confidence": round(confidence, 3),
    }


def _compute_override_patterns(conn) -> dict:
    """Compute override patterns from interaction log."""
    total_wo = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_log
        WHERE interaction_type IN ('work_order_implemented', 'work_order_overridden')
    """, default=0)

    overridden = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_log
        WHERE interaction_type = 'work_order_overridden'
    """, default=0)

    override_rate = overridden / total_wo if total_wo > 0 else 0.0

    # Override accuracy: did the overridden findings turn out to be correctly dismissed?
    override_outcomes = _safe_query_all(conn, """
        SELECT subsequent_outcome_class FROM pi_interaction_log
        WHERE interaction_type IN ('work_order_overridden', 'finding_dismissed')
          AND subsequent_outcome_class IS NOT NULL
    """)

    correct_overrides = sum(
        1 for r in (override_outcomes or [])
        if r["subsequent_outcome_class"] in ("correct", "directionally_correct")
    )
    total_scored = len(override_outcomes or [])
    override_accuracy = correct_overrides / total_scored if total_scored > 0 else None

    # Domain-level override analysis
    domain_overrides = _safe_query_all(conn, """
        SELECT dimension,
               SUM(CASE WHEN subsequent_outcome_class IN ('correct', 'directionally_correct') THEN 1 ELSE 0 END) as correct,
               COUNT(*) as total
        FROM pi_interaction_log
        WHERE interaction_type IN ('work_order_overridden', 'finding_dismissed')
          AND subsequent_outcome_class IS NOT NULL
          AND dimension IS NOT NULL
        GROUP BY dimension
        HAVING total >= 3
    """)

    human_leads = []
    engine_leads = []
    for r in (domain_overrides or []):
        accuracy = r["correct"] / r["total"] if r["total"] > 0 else 0
        if accuracy > 0.60:
            human_leads.append(r["dimension"])
        elif accuracy < 0.40:
            engine_leads.append(r["dimension"])

    confidence = min(0.90, 0.1 + 0.8 * (1 - 1 / (total_wo + 1))) if total_wo > 0 else 0.1

    return {
        "override_rate_overall": round(override_rate, 3),
        "override_accuracy_overall": round(override_accuracy, 3) if override_accuracy is not None else None,
        "domains_where_human_leads": json.dumps(human_leads),
        "domains_where_engine_leads": json.dumps(engine_leads),
        "override_confidence": round(confidence, 3),
    }


def _compute_presentation_preferences(conn) -> dict:
    """Learn presentation preferences from implementation patterns."""
    reads_self_audit = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_log
        WHERE interaction_type = 'self_audit_viewed'
    """, default=0) > 0

    reads_parameter_graph = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_log
        WHERE interaction_type = 'parameter_graph_viewed'
    """, default=0) > 0

    provides_reasons = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_log
        WHERE interaction_type = 'override_reason_provided'
    """, default=0)
    total_overrides = _safe_scalar(conn, """
        SELECT COUNT(*) FROM pi_interaction_log
        WHERE interaction_type IN ('work_order_overridden', 'finding_dismissed')
    """, default=0)
    provides_override_reasons = (
        provides_reasons > 0 and total_overrides > 0
        and provides_reasons / total_overrides >= 0.5
    )

    # Presentation preference: do work orders with parameter values get implemented faster?
    # Compare implementation rates for work orders with vs without target_parameter
    with_param = _safe_query(conn, """
        SELECT AVG(il.days_since_work_order_issued) as avg_days, COUNT(*) as cnt
        FROM pi_interaction_log il
        JOIN pi_work_order wo ON il.work_order_id = wo.id
        WHERE il.interaction_type = 'work_order_implemented'
          AND wo.target_parameter IS NOT NULL
          AND il.days_since_work_order_issued IS NOT NULL
    """)
    without_param = _safe_query(conn, """
        SELECT AVG(il.days_since_work_order_issued) as avg_days, COUNT(*) as cnt
        FROM pi_interaction_log il
        JOIN pi_work_order wo ON il.work_order_id = wo.id
        WHERE il.interaction_type = 'work_order_implemented'
          AND wo.target_parameter IS NULL
          AND il.days_since_work_order_issued IS NOT NULL
    """)

    responds_to_params = False
    if (with_param and without_param
            and (with_param["cnt"] or 0) >= 3 and (without_param["cnt"] or 0) >= 3
            and with_param["avg_days"] is not None and without_param["avg_days"] is not None):
        responds_to_params = with_param["avg_days"] < without_param["avg_days"]

    # Confidence based on total interactions
    total = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_interaction_log", default=0)
    pres_confidence = min(0.90, 0.1 + 0.8 * (1 - 1 / (total + 1))) if total > 10 else 0.1

    return {
        "reads_self_audit": int(reads_self_audit),
        "reads_parameter_graph": int(reads_parameter_graph),
        "provides_override_reasons": int(provides_override_reasons),
        "responds_to_specific_parameters": int(responds_to_params),
        "responds_to_rationale": 0,  # requires more data to determine
        "responds_to_confidence_labels": 0,  # requires more data to determine
        "presentation_confidence": round(pres_confidence, 3),
    }


def _assess_data_quality(obs: int, timing: dict, overrides: dict, prefs: dict) -> str:
    """Assess overall data quality for model confidence."""
    if obs < 10:
        return "insufficient"
    elif obs < 20:
        return "thin"
    elif obs < 50:
        return "adequate"
    else:
        return "good"


def _generate_model_notes(obs: int, timing: dict, overrides: dict,
                           prefs: dict, quality: str) -> str:
    """Generate plain language summary of what the model knows about you."""
    if quality == "insufficient":
        return "Not enough data yet to describe patterns."

    lines = []

    if timing.get("median_implementation_days") is not None:
        lines.append(
            f"You typically implement work orders within "
            f"{timing['median_implementation_days']:.0f} days of receiving them."
        )

    if timing.get("fastest_dimension"):
        lines.append(
            f"You act fastest on {timing['fastest_dimension']} findings "
            f"and slowest on {timing['slowest_dimension']} findings."
        )

    if timing.get("preferred_day_of_week") is not None:
        lines.append(
            f"You most often implement changes on "
            f"{_DAYS[timing['preferred_day_of_week']]}s."
        )

    human_leads = json.loads(overrides.get("domains_where_human_leads", "[]"))
    engine_leads = json.loads(overrides.get("domains_where_engine_leads", "[]"))

    if human_leads:
        lines.append(
            f"Your judgment outperforms the engine in: "
            f"{', '.join(human_leads)}. "
            f"The engine defers more in these dimensions."
        )

    if engine_leads:
        lines.append(
            f"The engine outperforms your overrides in: "
            f"{', '.join(engine_leads)}. "
            f"The engine escalates more persistently in these dimensions."
        )

    if prefs.get("responds_to_specific_parameters"):
        lines.append(
            "You implement work orders faster when specific parameter "
            "values are shown upfront. The engine leads with these."
        )

    lines.append(
        f"\nAll of the above is based on {obs} "
        f"observed interactions. You can correct any of it."
    )

    return " ".join(lines)


def _describe_significant_change(old_model: dict, new_model: dict) -> str:
    """Describe what changed between model snapshots."""
    changes = []

    old_fastest = old_model.get("fastest_dimension")
    new_fastest = new_model.get("fastest_dimension")
    if old_fastest != new_fastest and new_fastest:
        changes.append(f"Fastest dimension changed from {old_fastest} to {new_fastest}.")

    old_day = old_model.get("preferred_day_of_week")
    new_day = new_model.get("preferred_day_of_week")
    if old_day != new_day and new_day is not None:
        changes.append(f"Preferred day changed to {_DAYS[new_day]}.")

    old_quality = old_model.get("data_quality")
    new_quality = new_model.get("data_quality")
    if old_quality != new_quality:
        changes.append(f"Data quality: {old_quality} → {new_quality}.")

    old_obs = old_model.get("observation_count", 0)
    new_obs = new_model.get("observation_count", 0)
    if new_obs > old_obs:
        changes.append(f"{new_obs - old_obs} new interactions since last snapshot.")

    return " ".join(changes) if changes else "No significant changes."


def _write_model(conn, model: dict):
    """Upsert the singleton collaborator model row."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Check if exists
    existing = _safe_query(conn, "SELECT id FROM pi_collaborator_model WHERE id = 'singleton'")

    if existing:
        conn.execute("""
            UPDATE pi_collaborator_model SET
                last_updated = ?,
                observation_count = ?,
                median_implementation_days = ?,
                fastest_dimension = ?,
                slowest_dimension = ?,
                preferred_day_of_week = ?,
                preferred_hour_of_day = ?,
                timing_confidence = ?,
                override_rate_overall = ?,
                override_accuracy_overall = ?,
                domains_where_human_leads = ?,
                domains_where_engine_leads = ?,
                override_confidence = ?,
                reads_self_audit = ?,
                reads_parameter_graph = ?,
                provides_override_reasons = ?,
                responds_to_specific_parameters = ?,
                responds_to_rationale = ?,
                responds_to_confidence_labels = ?,
                presentation_confidence = ?,
                data_quality = ?,
                model_notes = ?
            WHERE id = 'singleton'
        """, (
            now,
            model.get("observation_count", 0),
            model.get("median_implementation_days"),
            model.get("fastest_dimension"),
            model.get("slowest_dimension"),
            model.get("preferred_day_of_week"),
            model.get("preferred_hour_of_day"),
            model.get("timing_confidence", 0.1),
            model.get("override_rate_overall"),
            model.get("override_accuracy_overall"),
            model.get("domains_where_human_leads", "[]"),
            model.get("domains_where_engine_leads", "[]"),
            model.get("override_confidence", 0.1),
            model.get("reads_self_audit", 0),
            model.get("reads_parameter_graph", 0),
            model.get("provides_override_reasons", 0),
            model.get("responds_to_specific_parameters", 0),
            model.get("responds_to_rationale", 0),
            model.get("responds_to_confidence_labels", 0),
            model.get("presentation_confidence", 0.1),
            model.get("data_quality", "insufficient"),
            model.get("model_notes", ""),
        ))
    else:
        conn.execute("""
            INSERT INTO pi_collaborator_model
                (id, generated_at, last_updated, observation_count,
                 median_implementation_days, fastest_dimension, slowest_dimension,
                 preferred_day_of_week, preferred_hour_of_day, timing_confidence,
                 override_rate_overall, override_accuracy_overall,
                 domains_where_human_leads, domains_where_engine_leads,
                 override_confidence,
                 reads_self_audit, reads_parameter_graph, provides_override_reasons,
                 responds_to_specific_parameters, responds_to_rationale,
                 responds_to_confidence_labels, presentation_confidence,
                 data_quality, model_notes)
            VALUES ('singleton', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now, now,
            model.get("observation_count", 0),
            model.get("median_implementation_days"),
            model.get("fastest_dimension"),
            model.get("slowest_dimension"),
            model.get("preferred_day_of_week"),
            model.get("preferred_hour_of_day"),
            model.get("timing_confidence", 0.1),
            model.get("override_rate_overall"),
            model.get("override_accuracy_overall"),
            model.get("domains_where_human_leads", "[]"),
            model.get("domains_where_engine_leads", "[]"),
            model.get("override_confidence", 0.1),
            model.get("reads_self_audit", 0),
            model.get("reads_parameter_graph", 0),
            model.get("provides_override_reasons", 0),
            model.get("responds_to_specific_parameters", 0),
            model.get("responds_to_rationale", 0),
            model.get("responds_to_confidence_labels", 0),
            model.get("presentation_confidence", 0.1),
            model.get("data_quality", "insufficient"),
            model.get("model_notes", ""),
        ))
    conn.commit()


def _snapshot_model(conn, model: dict, obs: int, change: str):
    """Save a snapshot of the model for history."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            INSERT INTO pi_collaborator_model_history
                (id, snapshot_at, model_json, observation_count_at_snapshot, significant_change)
            VALUES (?, ?, ?, ?, ?)
        """, (str(uuid4()), now, json.dumps(model), obs, change))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.warning("Failed to snapshot collaborator model: %s", e)


# ── Collaborator Model Read ──────────────────────────────────────────────────

def get_collaborator_model(conn) -> dict:
    """Return the current collaborator model as a dict."""
    row = _safe_query(conn, "SELECT * FROM pi_collaborator_model WHERE id = 'singleton'")
    if not row:
        return {
            "observation_count": 0,
            "data_quality": "insufficient",
            "model_notes": "No collaborator model built yet.",
            "adaptations_disabled": 0,
        }

    return {
        "observation_count": row["observation_count"],
        "data_quality": row["data_quality"],
        "model_notes": row["model_notes"],
        "median_implementation_days": row["median_implementation_days"],
        "fastest_dimension": row["fastest_dimension"],
        "slowest_dimension": row["slowest_dimension"],
        "preferred_day_of_week": row["preferred_day_of_week"],
        "preferred_hour_of_day": row["preferred_hour_of_day"],
        "timing_confidence": row["timing_confidence"],
        "override_rate_overall": row["override_rate_overall"],
        "override_accuracy_overall": row["override_accuracy_overall"],
        "domains_where_human_leads": row["domains_where_human_leads"],
        "domains_where_engine_leads": row["domains_where_engine_leads"],
        "override_confidence": row["override_confidence"],
        "reads_self_audit": row["reads_self_audit"],
        "reads_parameter_graph": row["reads_parameter_graph"],
        "provides_override_reasons": row["provides_override_reasons"],
        "responds_to_specific_parameters": row["responds_to_specific_parameters"],
        "responds_to_rationale": row["responds_to_rationale"],
        "responds_to_confidence_labels": row["responds_to_confidence_labels"],
        "presentation_confidence": row["presentation_confidence"],
        "adaptations_disabled": row["adaptations_disabled"],
        "last_updated": row["last_updated"],
    }


def get_collaborator_model_history(conn, limit: int = 20) -> list:
    """Return model snapshots with significant_change notes."""
    rows = _safe_query_all(conn, """
        SELECT * FROM pi_collaborator_model_history
        ORDER BY snapshot_at DESC LIMIT ?
    """, (limit,))
    return [
        {
            "id": r["id"],
            "snapshot_at": r["snapshot_at"],
            "observation_count": r["observation_count_at_snapshot"],
            "significant_change": r["significant_change"],
            "model": json.loads(r["model_json"]) if r["model_json"] else {},
        }
        for r in (rows or [])
    ]


# ── Adaptive Presentation Layer ──────────────────────────────────────────────

def build_adaptive_presentation(conn, work_order: dict) -> dict:
    """Build presentation config for a work order.

    Adapts presentation only — never content. All adaptations are labeled.
    Returns dict with lead_element, rationale_collapsed, timing, adaptations list.
    """
    model = get_collaborator_model(conn)
    adaptations = []

    # If adaptations disabled, return neutral presentation
    if model.get("adaptations_disabled"):
        return {
            "lead_element": "instruction",
            "rationale_collapsed": True,
            "queue_for_preferred_time": False,
            "queued_until": None,
            "adaptations": [],
            "model_data_quality": model.get("data_quality", "insufficient"),
            "adaptations_disabled": True,
        }

    # Leading element
    lead_element = "instruction"
    if (model.get("responds_to_specific_parameters")
            and (model.get("presentation_confidence") or 0) >= 0.50):
        lead_element = "specific_change"
        adaptations.append({
            "id": "lead_with_parameters",
            "what": "Leading with parameter values",
            "why": "You implement faster when specific values are shown first",
            "confidence": model["presentation_confidence"],
        })

    # Rationale visibility
    rationale_collapsed = True
    if (model.get("responds_to_rationale")
            and (model.get("presentation_confidence") or 0) >= 0.50):
        rationale_collapsed = False
        adaptations.append({
            "id": "rationale_expanded",
            "what": "Rationale shown expanded",
            "why": "You implement faster when rationale is visible",
            "confidence": model["presentation_confidence"],
        })

    # Timing: queue for preferred day
    queue = False
    queued_until = None
    if (model.get("timing_confidence") or 0) >= 0.60:
        preferred_day = model.get("preferred_day_of_week")
        if preferred_day is not None:
            now = datetime.now(timezone.utc)
            days_until = (preferred_day - now.weekday()) % 7
            if days_until > 0:  # not today
                surface_at = now + timedelta(days=days_until)
                queue = True
                queued_until = surface_at.strftime("%Y-%m-%d")
                adaptations.append({
                    "id": "queue_preferred_day",
                    "what": f"Queued for {_DAYS[preferred_day]}",
                    "why": f"{_DAYS[preferred_day]} is your most common implementation day",
                    "confidence": model["timing_confidence"],
                })

    return {
        "lead_element": lead_element,
        "rationale_collapsed": rationale_collapsed,
        "queue_for_preferred_time": queue,
        "queued_until": queued_until,
        "adaptations": adaptations,
        "model_data_quality": model.get("data_quality", "insufficient"),
        "adaptations_disabled": False,
    }


# ── Bidirectional Trust Calibration ──────────────────────────────────────────

def update_domain_trust(conn, dimension: str, was_correct: bool) -> dict:
    """Update trust calibration after an override outcome is known.

    Returns the updated trust state for the dimension.
    """
    row = _safe_query(conn, "SELECT * FROM pi_domain_trust WHERE dimension = ?", (dimension,))

    if not row:
        try:
            conn.execute("INSERT INTO pi_domain_trust (dimension) VALUES (?)", (dimension,))
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.Error):
            pass
        row = _safe_query(conn, "SELECT * FROM pi_domain_trust WHERE dimension = ?", (dimension,))
        if not row:
            return {}

    total = row["human_override_count"] + 1
    correct = row["human_correct_count"] + (1 if was_correct else 0)
    wrong = row["human_wrong_count"] + (0 if was_correct else 1)

    # Beta-Binomial with Laplace smoothing
    human_conf = (correct + 1) / (total + 2)

    # Determine trust leader
    engine_conf = row["engine_confidence"]
    margin = abs(engine_conf - human_conf)

    if total < 5:
        leader = "insufficient_data"
    elif margin < 0.10:
        leader = "tied"
    elif engine_conf > human_conf:
        leader = "engine"
    else:
        leader = "human"

    # Behavioral consequences
    if leader == "engine" and margin >= 0.20:
        override_requires_reason = 1
        persistence = "high"
    elif leader == "human" and margin >= 0.20:
        override_requires_reason = 0
        persistence = "low"
    else:
        override_requires_reason = 0
        persistence = "normal"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("""
            UPDATE pi_domain_trust
            SET human_override_count = ?,
                human_correct_count = ?,
                human_wrong_count = ?,
                human_confidence = ?,
                trust_leader = ?,
                trust_margin = ?,
                override_requires_reason = ?,
                escalation_persistence = ?,
                last_updated = ?
            WHERE dimension = ?
        """, (total, correct, wrong, round(human_conf, 4), leader,
              round(margin, 4), override_requires_reason, persistence,
              now, dimension))
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to update domain trust: %s", e)
        return {}

    return {
        "dimension": dimension,
        "human_confidence": round(human_conf, 4),
        "engine_confidence": engine_conf,
        "trust_leader": leader,
        "trust_margin": round(margin, 4),
        "override_requires_reason": override_requires_reason,
        "escalation_persistence": persistence,
    }


def get_domain_trust(conn) -> list:
    """Return trust calibration for all dimensions."""
    rows = _safe_query_all(conn, """
        SELECT * FROM pi_domain_trust ORDER BY dimension
    """)
    return [
        {
            "dimension": r["dimension"],
            "engine_confidence": r["engine_confidence"],
            "human_confidence": r["human_confidence"],
            "trust_leader": r["trust_leader"],
            "trust_margin": r["trust_margin"],
            "human_override_count": r["human_override_count"],
            "human_correct_count": r["human_correct_count"],
            "override_requires_reason": r["override_requires_reason"],
            "escalation_persistence": r["escalation_persistence"],
        }
        for r in (rows or [])
    ]


def get_trust_for_dimension(conn, dimension: str) -> dict:
    """Return trust state for a specific dimension."""
    row = _safe_query(conn, "SELECT * FROM pi_domain_trust WHERE dimension = ?", (dimension,))
    if not row:
        return {
            "dimension": dimension,
            "trust_leader": "insufficient_data",
            "override_requires_reason": 0,
            "escalation_persistence": "normal",
        }
    return {
        "dimension": dimension,
        "engine_confidence": row["engine_confidence"],
        "human_confidence": row["human_confidence"],
        "trust_leader": row["trust_leader"],
        "trust_margin": row["trust_margin"],
        "override_requires_reason": row["override_requires_reason"],
        "escalation_persistence": row["escalation_persistence"],
    }


# ── Correction Interface ─────────────────────────────────────────────────────

def record_correction(conn, correction_type: str, dimension=None, notes="") -> str:
    """Record a correction to the collaborator model.

    Logged permanently as an interaction. Model rebuild picks it up.
    Returns the interaction log entry id.
    """
    log_interaction(
        conn,
        interaction_type="correction",
        dimension=dimension,
        notes=f"[{correction_type}] {notes}",
    )
    # Trigger model rebuild
    rebuild_collaborator_model(conn)
    return "correction_recorded"


def disable_all_adaptations(conn):
    """Disable all presentation adaptations without deleting model data."""
    try:
        existing = _safe_query(conn, "SELECT id FROM pi_collaborator_model WHERE id = 'singleton'")
        if existing:
            conn.execute("""
                UPDATE pi_collaborator_model SET adaptations_disabled = 1 WHERE id = 'singleton'
            """)
        else:
            conn.execute("""
                INSERT INTO pi_collaborator_model (id, generated_at, last_updated, adaptations_disabled)
                VALUES ('singleton', datetime('now'), datetime('now'), 1)
            """)
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to disable adaptations: %s", e)


def enable_adaptations(conn):
    """Re-enable presentation adaptations."""
    try:
        conn.execute("""
            UPDATE pi_collaborator_model SET adaptations_disabled = 0 WHERE id = 'singleton'
        """)
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.Error) as e:
        logger.error("Failed to enable adaptations: %s", e)
