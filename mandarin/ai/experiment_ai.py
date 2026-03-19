"""AI Experiment Advisor — uses local LLM to generate hypotheses, design variants,
analyze qualitative feedback, prioritize experiments, and recommend rollout decisions.

All AI recommendations flow through the experiment governance approval queue as
review_required actions. The advisor proposes; humans decide.

Degrades gracefully when Ollama is unavailable — returns empty results, never blocks.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .ollama_client import generate, is_ollama_available

logger = logging.getLogger(__name__)

# Task types for generation logging
TASK_HYPOTHESIS = "experiment_hypothesis"
TASK_VARIANT_DESIGN = "experiment_variant_design"
TASK_FEEDBACK_ANALYSIS = "experiment_feedback_analysis"
TASK_PRIORITIZATION = "experiment_prioritization"
TASK_ROLLOUT_RECOMMENDATION = "experiment_rollout_recommendation"

# ── System Prompts ──────────────────────────────────────────────────────────

_HYPOTHESIS_SYSTEM = """\
You are an experiment advisor for a Mandarin Chinese learning app called Aelu.
You analyze learner data patterns and propose A/B experiment hypotheses.

Rules:
- Propose experiments that could improve learning outcomes (retention, accuracy, engagement).
- Each hypothesis must be testable with a clear primary metric.
- Never propose changes to mastery thresholds, SRS parameters, or difficulty ratings — these are blocked.
- Respect the learner: no dark patterns, artificial urgency, or manipulative nudges.
- Prefer small, low-risk experiments over sweeping changes.
- Be specific about what the control and treatment would look like.

Respond in JSON format with this structure:
{
  "hypotheses": [
    {
      "name": "short_snake_case_name",
      "description": "One sentence describing the experiment",
      "hypothesis": "If we [change], then [outcome] because [reasoning]",
      "primary_metric": "session_completion_rate|accuracy|retention_7d|drill_variety_usage",
      "expected_direction": "increase|decrease",
      "risk_level": "low|medium",
      "variants": ["control", "treatment_name"],
      "rationale": "Why this experiment matters based on the data"
    }
  ]
}
"""

_VARIANT_DESIGN_SYSTEM = """\
You are an experiment advisor for a Mandarin Chinese learning app called Aelu.
You design specific A/B test variants based on a hypothesis.

Rules:
- Describe exactly what each variant does, concretely enough for a developer to implement.
- Keep the control identical to current behavior.
- Ensure the treatment is a minimal change — isolate the variable being tested.
- Never change mastery thresholds, SRS parameters, or difficulty ratings.
- No dark patterns. No artificial urgency. No manipulative nudges.
- Include guardrail metrics to monitor for harm.

Respond in JSON format:
{
  "control": {
    "name": "control",
    "description": "Current behavior — no changes",
    "implementation_notes": "No code changes needed"
  },
  "treatment": {
    "name": "treatment_name",
    "description": "What changes for the treatment group",
    "implementation_notes": "Specific code changes needed"
  },
  "guardrail_metrics": ["metrics that should NOT degrade"],
  "suggested_traffic_pct": 50,
  "suggested_min_sample": 100,
  "doctrine_compliance": "Why this respects the learner"
}
"""

_FEEDBACK_ANALYSIS_SYSTEM = """\
You are an experiment advisor for a Mandarin Chinese learning app called Aelu.
You analyze qualitative signals from an experiment to supplement quantitative results.

Look for:
- Behavioral anomalies (session length changes, unusual drill patterns)
- Session quality signals (accuracy trends, completion patterns)
- Engagement changes (reading/listening usage shifts)
- Signs of gaming or Goodhart's law (metric improving but learning degrading)

Respond in JSON format:
{
  "summary": "One paragraph synthesis of qualitative findings",
  "signals": [
    {
      "signal": "What was observed",
      "interpretation": "What it likely means",
      "confidence": "high|medium|low",
      "sentiment": "positive|negative|neutral"
    }
  ],
  "concerns": ["Any red flags or counter-metric worries"],
  "recommendation": "proceed|caution|pause"
}
"""

_PRIORITIZATION_SYSTEM = """\
You are an experiment advisor for a Mandarin Chinese learning app called Aelu.
You rank experiment hypotheses by expected information value.

Consider:
- Predicted impact on learning outcomes (not just engagement metrics)
- Uncertainty — prioritize experiments where we know the least
- Available user traffic — can we run this with enough power?
- Conflicts with running experiments
- Risk level — prefer low-risk experiments when impact is similar

Respond in JSON format:
{
  "ranked": [
    {
      "name": "experiment_name",
      "priority_score": 0.0-1.0,
      "reasoning": "Why this rank"
    }
  ],
  "traffic_budget_note": "Assessment of total traffic available for experiments",
  "conflict_warnings": ["Any experiments that shouldn't run concurrently"]
}
"""

_ROLLOUT_SYSTEM = """\
You are an experiment advisor for a Mandarin Chinese learning app called Aelu.
You recommend whether a concluded experiment's winning treatment should be rolled out.

Consider:
- Primary metric improvement (effect size and significance)
- Counter-metric health (delayed recall, difficulty integrity, unsubscribe rate)
- Qualitative behavioral signals
- Doctrine compliance (does the change respect the learner?)
- Long-term sustainability (will this improvement persist?)

Respond in JSON format:
{
  "recommendation": "rollout|hold|reject",
  "confidence": "high|medium|low",
  "reasoning": "Multi-sentence explanation of the recommendation",
  "conditions": ["Any conditions that should be met before rollout"],
  "monitoring_plan": "What to watch during graduated rollout"
}
"""


# ── Data Gathering Helpers ──────────────────────────────────────────────────


def _gather_learner_signals(conn: sqlite3.Connection) -> dict:
    """Gather aggregate learner data patterns for hypothesis generation."""
    signals = {}

    try:
        # Session frequency and recency
        sessions = conn.execute(
            """SELECT COUNT(*) as total_sessions,
                      AVG(duration_seconds) as avg_duration,
                      AVG(items_completed) as avg_items,
                      AVG(CASE WHEN items_completed > 0
                           THEN CAST(items_correct AS FLOAT) / items_completed
                           ELSE 0 END) as avg_accuracy
               FROM session_log
               WHERE started_at >= datetime('now', '-30 days')
                 AND items_completed > 0"""
        ).fetchone()
        if sessions and sessions["total_sessions"] and sessions["total_sessions"] > 0:
            signals["recent_sessions"] = {
                "total_30d": sessions["total_sessions"],
                "avg_duration_sec": round(sessions["avg_duration"] or 0, 1),
                "avg_items_per_session": round(sessions["avg_items"] or 0, 1),
                "avg_accuracy": round((sessions["avg_accuracy"] or 0) * 100, 1),
            }
    except sqlite3.OperationalError:
        pass

    try:
        # Drill modality distribution
        modalities = conn.execute(
            """SELECT modality_counts FROM session_log
               WHERE started_at >= datetime('now', '-30 days')
                 AND modality_counts IS NOT NULL"""
        ).fetchall()
        mod_totals = {}
        for row in modalities:
            try:
                mc = json.loads(row["modality_counts"])
                for k, v in mc.items():
                    mod_totals[k] = mod_totals.get(k, 0) + (v or 0)
            except (json.JSONDecodeError, TypeError):
                pass
        if mod_totals:
            signals["modality_distribution"] = mod_totals
    except sqlite3.OperationalError:
        pass

    try:
        # Churn risk signals
        from ..churn_detection import get_at_risk_users
        at_risk = get_at_risk_users(conn, min_risk=40)
        if at_risk:
            churn_types = {}
            for u in at_risk:
                ct = u.get("churn_type", "unknown")
                churn_types[ct] = churn_types.get(ct, 0) + 1
            signals["churn_risk"] = {
                "at_risk_count": len(at_risk),
                "by_type": churn_types,
                "avg_risk_score": round(
                    sum(u.get("score", 0) for u in at_risk) / len(at_risk), 1
                ),
            }
    except Exception:
        pass

    try:
        # Recent experiment track record
        from ..intelligence_audit import compute_proposal_win_rate
        win_rate = compute_proposal_win_rate(conn)
        if win_rate.get("n_started", 0) > 0:
            signals["experiment_track_record"] = win_rate
    except Exception:
        pass

    try:
        # Completion rate trends (weekly)
        weekly = conn.execute(
            """SELECT
                strftime('%Y-W%W', started_at) as week,
                AVG(CASE WHEN session_outcome = 'completed' THEN 1.0 ELSE 0.0 END) as completion_rate,
                COUNT(*) as sessions
               FROM session_log
               WHERE started_at >= datetime('now', '-56 days')
                 AND items_completed > 0
               GROUP BY week
               ORDER BY week"""
        ).fetchall()
        if weekly:
            signals["weekly_completion_trend"] = [
                {"week": w["week"], "rate": round(w["completion_rate"] * 100, 1),
                 "sessions": w["sessions"]}
                for w in weekly
            ]
    except sqlite3.OperationalError:
        pass

    return signals


def _gather_experiment_context(conn: sqlite3.Connection, experiment_name: str) -> dict:
    """Gather quantitative and behavioral context for a specific experiment."""
    context = {}

    try:
        from ..experiments import get_experiment_results, list_experiments
        results = get_experiment_results(conn, experiment_name)
        context["results"] = results
    except Exception:
        pass

    try:
        from ..counter_metrics import check_counter_metrics
        counter = check_counter_metrics(conn, experiment_name)
        context["counter_metrics"] = counter
    except Exception:
        pass

    try:
        # Per-variant session patterns
        exp = conn.execute(
            "SELECT id, variants FROM experiment WHERE name = ?",
            (experiment_name,),
        ).fetchone()
        if exp:
            exp_id = exp["id"]
            variants = json.loads(exp["variants"])
            variant_patterns = {}
            for variant in variants:
                users = conn.execute(
                    """SELECT user_id FROM experiment_assignment
                       WHERE experiment_id = ? AND variant = ?""",
                    (exp_id, variant),
                ).fetchall()
                user_ids = [u["user_id"] for u in users]
                if not user_ids:
                    continue
                placeholders = ",".join("?" * len(user_ids))
                stats = conn.execute(
                    f"""SELECT
                        AVG(duration_seconds) as avg_duration,
                        AVG(items_completed) as avg_items,
                        COUNT(DISTINCT user_id) as active_users
                    FROM session_log
                    WHERE user_id IN ({placeholders})
                      AND started_at >= datetime('now', '-14 days')
                      AND items_completed > 0""",
                    user_ids,
                ).fetchone()
                if stats:
                    variant_patterns[variant] = {
                        "avg_duration": round(stats["avg_duration"] or 0, 1),
                        "avg_items": round(stats["avg_items"] or 0, 1),
                        "active_users_14d": stats["active_users"],
                    }
            if variant_patterns:
                context["variant_session_patterns"] = variant_patterns
    except Exception:
        pass

    return context


# ── Core Advisor Functions ──────────────────────────────────────────────────


def generate_hypotheses(conn: sqlite3.Connection, max_hypotheses: int = 3) -> list[dict]:
    """Scan learner data and generate experiment hypotheses using local LLM.

    Returns list of hypothesis dicts, empty if Ollama unavailable.
    All hypotheses are proposals only — they must go through governance.
    """
    if not is_ollama_available():
        logger.info("Ollama unavailable — skipping AI hypothesis generation")
        return []

    signals = _gather_learner_signals(conn)
    if not signals:
        logger.info("No learner signals available for hypothesis generation")
        return []

    # Build the prompt from gathered signals
    prompt = (
        f"Analyze these learner data patterns and propose up to {max_hypotheses} "
        f"experiment hypotheses:\n\n{json.dumps(signals, indent=2)}\n\n"
        f"Also consider currently running experiments to avoid conflicts:\n"
    )

    try:
        from ..experiments import list_experiments
        running = list_experiments(conn, status="running")
        if running:
            prompt += json.dumps(
                [{"name": e["name"], "variants": e.get("variants")} for e in running],
                indent=2,
            )
        else:
            prompt += "No experiments currently running."
    except Exception:
        prompt += "Unable to check running experiments."

    response = generate(
        prompt=prompt,
        system=_HYPOTHESIS_SYSTEM,
        temperature=0.7,
        max_tokens=2048,
        use_cache=False,  # Always fresh analysis
        conn=conn,
        task_type=TASK_HYPOTHESIS,
    )

    if not response.success:
        logger.warning("AI hypothesis generation failed: %s", response.error)
        return []

    return _parse_hypotheses(response.text)


def design_variants(
    conn: sqlite3.Connection,
    hypothesis_name: str,
    hypothesis_text: str,
) -> dict | None:
    """Design specific A/B variants for a hypothesis using local LLM.

    Returns variant design dict, None if Ollama unavailable.
    """
    if not is_ollama_available():
        return None

    signals = _gather_learner_signals(conn)

    prompt = (
        f"Design A/B test variants for this hypothesis:\n\n"
        f"Name: {hypothesis_name}\n"
        f"Hypothesis: {hypothesis_text}\n\n"
        f"Current learner data context:\n{json.dumps(signals, indent=2)}"
    )

    response = generate(
        prompt=prompt,
        system=_VARIANT_DESIGN_SYSTEM,
        temperature=0.5,
        max_tokens=1024,
        use_cache=True,
        conn=conn,
        task_type=TASK_VARIANT_DESIGN,
    )

    if not response.success:
        logger.warning("AI variant design failed: %s", response.error)
        return None

    return _parse_json_response(response.text)


def analyze_experiment_feedback(
    conn: sqlite3.Connection,
    experiment_name: str,
) -> dict | None:
    """Analyze qualitative behavioral signals from an experiment using local LLM.

    Synthesizes session patterns, engagement shifts, and counter-metric data
    into a structured qualitative assessment.

    Returns analysis dict, None if Ollama unavailable.
    """
    if not is_ollama_available():
        return None

    context = _gather_experiment_context(conn, experiment_name)
    if not context:
        logger.info("No experiment context available for %s", experiment_name)
        return None

    prompt = (
        f"Analyze the qualitative signals from experiment '{experiment_name}':\n\n"
        f"{json.dumps(context, indent=2, default=str)}"
    )

    response = generate(
        prompt=prompt,
        system=_FEEDBACK_ANALYSIS_SYSTEM,
        temperature=0.4,
        max_tokens=1024,
        use_cache=False,
        conn=conn,
        task_type=TASK_FEEDBACK_ANALYSIS,
    )

    if not response.success:
        logger.warning("AI feedback analysis failed for %s: %s", experiment_name, response.error)
        return None

    return _parse_json_response(response.text)


def prioritize_experiments(
    conn: sqlite3.Connection,
    hypotheses: list[dict],
) -> list[dict]:
    """Rank experiment hypotheses by expected information value using local LLM.

    Args:
        conn: Database connection.
        hypotheses: List of hypothesis dicts (from generate_hypotheses or manual).

    Returns ranked list with priority scores, empty if Ollama unavailable.
    """
    if not is_ollama_available() or not hypotheses:
        return []

    # Gather context about current experiment load
    context = {}
    try:
        from ..experiments import list_experiments
        running = list_experiments(conn, status="running")
        context["running_experiments"] = len(running)
        context["running_names"] = [e["name"] for e in running]
    except Exception:
        pass

    try:
        # Rough user count for traffic estimation
        user_count = conn.execute(
            "SELECT COUNT(DISTINCT user_id) as n FROM session_log WHERE started_at >= datetime('now', '-30 days')"
        ).fetchone()
        context["active_users_30d"] = user_count["n"] if user_count else 0
    except sqlite3.OperationalError:
        pass

    prompt = (
        f"Prioritize these experiment hypotheses by expected information value:\n\n"
        f"Hypotheses:\n{json.dumps(hypotheses, indent=2)}\n\n"
        f"Current context:\n{json.dumps(context, indent=2)}"
    )

    response = generate(
        prompt=prompt,
        system=_PRIORITIZATION_SYSTEM,
        temperature=0.3,
        max_tokens=1024,
        use_cache=False,
        conn=conn,
        task_type=TASK_PRIORITIZATION,
    )

    if not response.success:
        logger.warning("AI experiment prioritization failed: %s", response.error)
        return []

    result = _parse_json_response(response.text)
    return result.get("ranked", []) if result else []


def recommend_rollout(
    conn: sqlite3.Connection,
    experiment_name: str,
) -> dict | None:
    """Synthesize quantitative + qualitative signals to recommend rollout decision.

    Called for concluded experiments where treatment won. The recommendation
    flows through governance as review_required — the admin makes the final call.

    Returns recommendation dict, None if Ollama unavailable.
    """
    if not is_ollama_available():
        return None

    context = _gather_experiment_context(conn, experiment_name)
    if not context:
        return None

    # Add qualitative analysis if available
    feedback = analyze_experiment_feedback(conn, experiment_name)
    if feedback:
        context["qualitative_analysis"] = feedback

    prompt = (
        f"Recommend whether to roll out the winning treatment from experiment "
        f"'{experiment_name}':\n\n{json.dumps(context, indent=2, default=str)}"
    )

    response = generate(
        prompt=prompt,
        system=_ROLLOUT_SYSTEM,
        temperature=0.3,
        max_tokens=1024,
        use_cache=False,
        conn=conn,
        task_type=TASK_ROLLOUT_RECOMMENDATION,
    )

    if not response.success:
        logger.warning("AI rollout recommendation failed for %s: %s",
                        experiment_name, response.error)
        return None

    return _parse_json_response(response.text)


# ── Daemon Integration ──────────────────────────────────────────────────────


def propose_ai_hypotheses(conn: sqlite3.Connection) -> list[dict]:
    """Generate AI hypotheses and submit them to the governance approval queue.

    Called by the experiment daemon. All proposals are review_required.
    Returns list of submitted proposals.
    """
    hypotheses = generate_hypotheses(conn)
    if not hypotheses:
        return []

    # Prioritize
    ranked = prioritize_experiments(conn, hypotheses)

    submitted = []
    for hypothesis in (ranked or hypotheses):
        name = hypothesis.get("name", "")
        if not name:
            continue

        # Check for duplicates — don't re-propose existing experiments
        try:
            existing = conn.execute(
                """SELECT id FROM experiment
                   WHERE name = ? AND status IN ('draft', 'running', 'paused')""",
                (name,),
            ).fetchone()
            if existing:
                continue

            existing_proposal = conn.execute(
                """SELECT id FROM experiment_proposal
                   WHERE name = ? AND status IN ('pending', 'started')""",
                (name,),
            ).fetchone()
            if existing_proposal:
                continue

            existing_queue = conn.execute(
                """SELECT id FROM experiment_approval_queue
                   WHERE experiment_name = ? AND status = 'pending'""",
                (name,),
            ).fetchone()
            if existing_queue:
                continue
        except sqlite3.OperationalError:
            continue

        # Create proposal record
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        variants = hypothesis.get("variants", ["control", "treatment"])

        try:
            conn.execute(
                """INSERT INTO experiment_proposal
                   (name, description, hypothesis, source, source_detail,
                    variants, traffic_pct, priority, status)
                   VALUES (?, ?, ?, 'ai_advisor', ?, ?, 50.0, ?, 'pending')""",
                (
                    name,
                    hypothesis.get("description", ""),
                    hypothesis.get("hypothesis", ""),
                    json.dumps({
                        "rationale": hypothesis.get("rationale", ""),
                        "primary_metric": hypothesis.get("primary_metric", ""),
                        "expected_direction": hypothesis.get("expected_direction", ""),
                        "risk_level": hypothesis.get("risk_level", "low"),
                        "priority_score": hypothesis.get("priority_score"),
                        "reasoning": hypothesis.get("reasoning", ""),
                    }),
                    json.dumps(variants),
                    hypothesis.get("priority_score", 50),
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            continue

        # Queue for governance approval
        from ..experiment_governance import queue_for_approval
        queue_for_approval(
            conn,
            action_type="start_experiment",
            experiment_name=name,
            proposal_data={
                "source": "ai_advisor",
                "hypothesis": hypothesis.get("hypothesis", ""),
                "description": hypothesis.get("description", ""),
                "variants": variants,
                "traffic_pct": 50.0,
                "primary_metric": hypothesis.get("primary_metric", ""),
                "rationale": hypothesis.get("rationale", ""),
                "risk_level": hypothesis.get("risk_level", "low"),
            },
            proposed_by="ai_advisor",
        )

        submitted.append(hypothesis)
        logger.info(
            "AI advisor proposed experiment %s (queued for review)", name
        )

    return submitted


def advise_on_concluded(conn: sqlite3.Connection, experiment_name: str) -> dict | None:
    """Generate an AI rollout recommendation for a concluded experiment.

    Called by the daemon or admin. The recommendation is logged and attached
    to the governance queue entry for the admin to consider.
    Returns the recommendation dict.
    """
    recommendation = recommend_rollout(conn, experiment_name)
    if not recommendation:
        return None

    # Log the recommendation as a lifecycle event
    try:
        from ..marketing_hooks import log_lifecycle_event
        log_lifecycle_event(
            "ai_rollout_recommendation",
            user_id="1",
            conn=conn,
            experiment_name=experiment_name,
            recommendation=recommendation.get("recommendation"),
            confidence=recommendation.get("confidence"),
            reasoning=recommendation.get("reasoning", "")[:500],
        )
    except Exception:
        pass

    return recommendation


# ── JSON Parsing Helpers ────────────────────────────────────────────────────


def _parse_json_response(text: str) -> dict | None:
    """Extract JSON from LLM response text, handling markdown code blocks."""
    if not text:
        return None

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    for marker in ("```json", "```"):
        if marker in text:
            start = text.index(marker) + len(marker)
            end = text.index("```", start) if "```" in text[start:] else len(text)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

    # Try finding first { ... } block
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    logger.debug("Failed to parse JSON from AI response: %s", text[:200])
    return None


def _parse_hypotheses(text: str) -> list[dict]:
    """Parse hypothesis list from LLM response."""
    parsed = _parse_json_response(text)
    if not parsed:
        return []

    hypotheses = parsed.get("hypotheses", [])
    if not isinstance(hypotheses, list):
        return []

    # Validate required fields
    valid = []
    for h in hypotheses:
        if isinstance(h, dict) and h.get("name") and h.get("hypothesis"):
            valid.append(h)

    return valid
