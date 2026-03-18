"""Autonomous A/B testing daemon — monitors, concludes, rolls out, and proposes experiments.

Runs every 6 hours (background thread, same pattern as email_scheduler.py):
1. Monitor active experiments — auto-conclude winners, auto-pause on guardrail degradation
2. Advance graduated rollouts — pending → 25% → 50% → 100% → complete
3. Create rollouts for concluded experiments with a winning treatment variant
4. Propose new experiments from churn signals
5. Auto-start top proposal when no conflicting experiments are running
6. Weekly digest — compile experiment status summary

Design principle: aelu decides, acts, and moves on. Guardrails are the safety net.
The admin receives a digest, not a decision queue.
"""

import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from .. import db
from ..experiments import (
    list_experiments,
    sequential_test,
    check_guardrails,
    conclude_experiment,
    pause_experiment,
    create_experiment,
    start_experiment,
    get_experiment_results,
)
from ..feature_flags import set_flag
from ..churn_detection import get_at_risk_users

logger = logging.getLogger(__name__)

_CYCLE_SECONDS = 6 * 3600  # 6 hours
_INITIAL_DELAY = 300  # 5 minutes after startup
_ROLLOUT_STAGE_DAYS = 3  # days between rollout stages

_ROLLOUT_STAGES = ["pending", "25pct", "50pct", "100pct", "complete"]
_ROLLOUT_PCT = {"pending": 0, "25pct": 25, "50pct": 50, "100pct": 100, "complete": 100}

# Churn type → experiment template
_CHURN_EXPERIMENT_TEMPLATES = {
    "boredom": {
        "name": "auto_drill_variety",
        "description": "Test increased drill type variety for users showing boredom signals",
        "hypothesis": "More varied drill types reduce boredom-driven churn",
        "variants": ["control", "high_variety"],
    },
    "frustration": {
        "name": "auto_difficulty_easing",
        "description": "Test reduced difficulty for users showing frustration signals",
        "hypothesis": "Easier initial difficulty reduces frustration-driven churn",
        "variants": ["control", "easier_start"],
    },
    "habit_fade": {
        "name": "auto_session_length",
        "description": "Test shorter sessions for users whose study habit is fading",
        "hypothesis": "Shorter sessions maintain habit better than longer ones",
        "variants": ["control", "short_sessions"],
    },
}

# Marketing experiment templates (scope = "marketing")
_MARKETING_EXPERIMENT_TEMPLATES = {
    "price_display_test": {
        "template_id": "price_display_test",
        "type": "marketing",
        "hypothesis": "Lower displayed price increases signup conversion",
        "variant_a_name": "control_14.99",
        "variant_a_config": {"price_display": "$14.99/mo"},
        "variant_b_name": "lower_9.99",
        "variant_b_config": {"price_display": "$9.99/mo"},
        "metric": "signup_conversion_rate",
        "guardrail_metrics": ["session_completion_rate"],
        "duration_days": 30,
        "scope": "marketing",
    },
}

_stop_event = threading.Event()
_thread = None


def start():
    """Start the experiment daemon background thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, daemon=True, name="experiment-daemon")
    _thread.start()
    logger.info("Experiment daemon started")


def stop():
    """Signal the background thread to stop."""
    _stop_event.set()


def _run_loop():
    """Main daemon loop — acquire lock, run tick, sleep, repeat."""
    from ..scheduler_lock import acquire_lock, release_lock

    if _stop_event.wait(_INITIAL_DELAY):
        return

    while not _stop_event.is_set():
        conn = None
        try:
            conn = db.get_connection()
            if not acquire_lock(conn, "experiment_daemon", ttl_seconds=_CYCLE_SECONDS):
                logger.debug("Experiment daemon: lock held by another instance, skipping")
                if _stop_event.wait(_CYCLE_SECONDS):
                    break
                continue

            _daemon_tick(conn)
            release_lock(conn, "experiment_daemon")

        except Exception:
            logger.exception("Experiment daemon tick failed")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        if _stop_event.wait(_CYCLE_SECONDS):
            break


def _daemon_tick(conn):
    """Single daemon cycle — the core autonomous loop."""
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    digest_entries = []

    # ── 1. Monitor active experiments ──
    running = list_experiments(conn, status="running")
    for exp in running:
        exp_name = exp["name"]
        try:
            seq = sequential_test(conn, exp_name)
            guardrails = check_guardrails(conn, exp_name)
            any_degraded = any(g.get("degraded") for g in guardrails.values())

            if any_degraded:
                pause_experiment(conn, exp_name)
                msg = f"PAUSED {exp_name}: guardrail degradation detected"
                logger.warning(msg)
                digest_entries.append(msg)
                continue

            recommendation = seq.get("recommendation", "continue")
            if recommendation == "stop_winner":
                results = get_experiment_results(conn, exp_name)
                variants = results.get("variants", {})
                variant_names = json.loads(exp.get("variants", "[]"))
                if len(variant_names) >= 2:
                    # Pick the variant with higher completion rate
                    best = max(variant_names, key=lambda v: variants.get(v, {}).get("completion_rate", 0))
                    conclude_experiment(conn, exp_name, winner=best,
                                        notes=f"Auto-concluded by daemon. p={seq.get('current_p')}")
                    msg = f"CONCLUDED {exp_name}: winner={best}, p={seq.get('current_p')}"
                    logger.info(msg)
                    digest_entries.append(msg)

            elif recommendation == "stop_futility":
                variant_names = json.loads(exp.get("variants", "[]"))
                control = variant_names[0] if variant_names else "control"
                conclude_experiment(conn, exp_name, winner=control,
                                    notes="Auto-concluded by daemon: futility (no significant difference)")
                msg = f"CONCLUDED {exp_name}: futility, defaulting to {control}"
                logger.info(msg)
                digest_entries.append(msg)

            else:
                digest_entries.append(f"RUNNING {exp_name}: {recommendation}, info_frac={seq.get('information_fraction', 0)}")

        except Exception:
            logger.exception("Error monitoring experiment %s", exp_name)

    # ── 2. Create rollouts for concluded experiments ──
    concluded = list_experiments(conn, status="concluded")
    for exp in concluded:
        exp_id = exp["id"]
        exp_name = exp["name"]
        conclusion = json.loads(exp.get("conclusion") or "{}")
        winner = conclusion.get("winner")
        variant_names = json.loads(exp.get("variants", "[]"))

        if not winner or winner == variant_names[0] if variant_names else True:
            continue  # Control won or no winner — no rollout needed

        # Check if rollout already exists
        existing = conn.execute(
            "SELECT id FROM experiment_rollout WHERE experiment_id = ?",
            (exp_id,)
        ).fetchone()
        if existing:
            continue

        flag_name = f"exp_{exp_name}_rollout"
        set_flag(conn, flag_name, enabled=True, rollout_pct=0,
                 description=f"Graduated rollout for experiment {exp_name}")
        conn.execute("""
            INSERT INTO experiment_rollout
            (experiment_id, winner_variant, rollout_stage, current_pct,
             stage_started_at, next_stage_at, feature_flag_name)
            VALUES (?, ?, 'pending', 0, ?, ?, ?)
        """, (exp_id, winner, now_str,
              (now + timedelta(days=_ROLLOUT_STAGE_DAYS)).strftime("%Y-%m-%d %H:%M:%S"),
              flag_name))
        conn.commit()
        msg = f"ROLLOUT CREATED for {exp_name}: winner={winner}"
        logger.info(msg)
        digest_entries.append(msg)

    # ── 3. Advance graduated rollouts ──
    rollouts = conn.execute("""
        SELECT * FROM experiment_rollout
        WHERE rollout_stage != 'complete'
          AND next_stage_at <= ?
    """, (now_str,)).fetchall()

    for rollout in rollouts:
        rollout = dict(rollout)
        current_stage = rollout["rollout_stage"]
        stage_idx = _ROLLOUT_STAGES.index(current_stage) if current_stage in _ROLLOUT_STAGES else 0
        next_idx = stage_idx + 1

        if next_idx >= len(_ROLLOUT_STAGES):
            continue

        next_stage = _ROLLOUT_STAGES[next_idx]
        next_pct = _ROLLOUT_PCT[next_stage]
        next_advance = (now + timedelta(days=_ROLLOUT_STAGE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

        conn.execute("""
            UPDATE experiment_rollout SET
                rollout_stage = ?, current_pct = ?,
                stage_started_at = ?, next_stage_at = ?
            WHERE id = ?
        """, (next_stage, next_pct, now_str, next_advance, rollout["id"]))

        if rollout["feature_flag_name"]:
            set_flag(conn, rollout["feature_flag_name"], enabled=True, rollout_pct=next_pct)

        conn.commit()
        msg = f"ROLLOUT ADVANCED {rollout['feature_flag_name']}: {current_stage} → {next_stage} ({next_pct}%)"
        logger.info(msg)
        digest_entries.append(msg)

    # ── 4. Propose experiments from churn signals ──
    try:
        at_risk = get_at_risk_users(conn, min_risk=50)
        churn_types = {}
        for user in at_risk:
            ct = user.get("churn_type", "unknown")
            churn_types[ct] = churn_types.get(ct, 0) + 1

        for churn_type, count in churn_types.items():
            if count < 5:
                continue  # Not enough signal
            template = _CHURN_EXPERIMENT_TEMPLATES.get(churn_type)

            if template:
                # Check for existing proposal or running experiment with this name
                existing = conn.execute(
                    "SELECT id FROM experiment_proposal WHERE name = ? AND status IN ('pending', 'started')",
                    (template["name"],)
                ).fetchone()
                if existing:
                    continue
                existing_exp = conn.execute(
                    "SELECT id FROM experiment WHERE name = ? AND status IN ('draft', 'running')",
                    (template["name"],)
                ).fetchone()
                if existing_exp:
                    continue

                scope = "parameter"  # churn templates default to parameter scope
                conn.execute("""
                    INSERT INTO experiment_proposal
                    (name, description, hypothesis, source, source_detail, variants,
                     traffic_pct, priority, scope, status)
                    VALUES (?, ?, ?, 'churn_signal', ?, ?, 50.0, ?, ?, 'pending')
                """, (
                    template["name"],
                    template["description"],
                    template["hypothesis"],
                    json.dumps({"churn_type": churn_type, "at_risk_count": count}),
                    json.dumps(template["variants"]),
                    count,  # priority = number of affected users
                    scope,
                ))
                conn.commit()
                msg = f"PROPOSED {template['name']}: {churn_type} signal from {count} users"
                logger.info(msg)
                digest_entries.append(msg)
            else:
                # No template — try LLM-generative experiment design
                try:
                    from ..intelligence.experiment_proposer import propose_experiment
                    finding = {
                        "dimension": "retention",
                        "title": f"Churn signal: {churn_type}",
                        "analysis": f"{count} at-risk users showing {churn_type} churn pattern",
                        "recommendation": f"Investigate and mitigate {churn_type} churn",
                        "severity": "high",
                    }
                    proposal = propose_experiment(conn, finding, source="churn_signal")
                    if proposal:
                        # Dedup check
                        existing = conn.execute(
                            "SELECT id FROM experiment_proposal WHERE name = ? AND status IN ('pending', 'started')",
                            (proposal["name"],)
                        ).fetchone()
                        if existing:
                            continue

                        conn.execute("""
                            INSERT INTO experiment_proposal
                            (name, description, hypothesis, source, source_detail, variants,
                             traffic_pct, priority, scope, status)
                            VALUES (?, ?, ?, ?, ?, ?, 50.0, ?, ?, 'pending')
                        """, (
                            proposal["name"],
                            proposal["description"],
                            proposal["hypothesis"],
                            proposal.get("source", "churn_signal"),
                            proposal.get("source_detail", json.dumps({"churn_type": churn_type})),
                            json.dumps(proposal["variants"]),
                            count,
                            proposal.get("scope", "parameter"),
                        ))
                        conn.commit()
                        msg = f"PROPOSED (LLM) {proposal['name']}: {churn_type} signal from {count} users"
                        logger.info(msg)
                        digest_entries.append(msg)
                except Exception:
                    logger.debug("LLM experiment proposal failed for churn type %s", churn_type)

    except Exception:
        logger.exception("Error in churn-based experiment proposal")

    # ── 5. Auto-start top proposal (if no conflicts) ──
    if not running:  # No running experiments
        top_proposal = conn.execute("""
            SELECT * FROM experiment_proposal
            WHERE status = 'pending'
            ORDER BY priority DESC
            LIMIT 1
        """).fetchone()

        if top_proposal:
            top_proposal = dict(top_proposal)
            try:
                variants = json.loads(top_proposal["variants"])
                exp_id = create_experiment(
                    conn,
                    name=top_proposal["name"],
                    description=top_proposal["description"],
                    variants=variants,
                    traffic_pct=top_proposal["traffic_pct"],
                    min_sample_size=top_proposal["min_sample_size"],
                )
                start_experiment(conn, top_proposal["name"])
                conn.execute("""
                    UPDATE experiment_proposal SET
                        status = 'started', reviewed_at = ?, started_experiment_id = ?
                    WHERE id = ?
                """, (now_str, exp_id, top_proposal["id"]))
                conn.commit()
                msg = f"AUTO-STARTED {top_proposal['name']} from proposal (priority={top_proposal['priority']})"
                logger.info(msg)
                digest_entries.append(msg)
            except Exception:
                logger.exception("Error auto-starting proposal %s", top_proposal["name"])

    # ── 6. Weekly digest ──
    try:
        last_digest = conn.execute("""
            SELECT MAX(created_at) as last FROM lifecycle_event
            WHERE event_type = 'experiment_digest'
        """).fetchone()
        last_digest_date = last_digest["last"] if last_digest and last_digest["last"] else None

        should_digest = True
        if last_digest_date:
            try:
                last_dt = datetime.fromisoformat(last_digest_date)
                should_digest = (now - last_dt).days >= 7
            except (ValueError, TypeError):
                pass

        if should_digest and digest_entries:
            digest_json = json.dumps({
                "timestamp": now_str,
                "entries": digest_entries,
                "running_count": len(running),
                "concluded_count": len(concluded),
            })
            conn.execute("""
                INSERT INTO lifecycle_event (user_id, event_type, event_data, created_at)
                VALUES (1, 'experiment_digest', ?, ?)
            """, (digest_json, now_str))
            conn.commit()
            logger.info("Experiment digest logged: %d entries", len(digest_entries))
    except Exception:
        logger.exception("Error generating experiment digest")
