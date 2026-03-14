"""System self-improvement — pattern detection, proposals, rollback.

The system may RECOMMEND changes but MUST NOT modify itself automatically.
Every recommendation must include:
- Observed pattern (with data)
- Why it matters
- Specific proposed change
- Expected benefit (testable within 5 sessions)
- Rollback plan
"""

import json
import logging
from datetime import date, datetime, timezone
from . import db

logger = logging.getLogger(__name__)

# Allowlist of valid lens columns for dynamic SQL in apply_proposal
_VALID_LENS_COLS = frozenset({
    "lens_quiet_observation", "lens_institutions", "lens_urban_texture",
    "lens_humane_mystery", "lens_identity", "lens_comedy",
    "lens_food", "lens_travel", "lens_explainers", "lens_wit",
    "lens_ensemble_comedy", "lens_sharp_observation", "lens_satire",
    "lens_moral_texture",
})


def detect_patterns(conn, user_id: int = 1) -> list:
    """Detect patterns that might warrant system changes.

    Triggers:
    - 3+ consecutive early exits on same task type
    - Persistent error-shape patterns
    - Modality imbalance
    - Engagement decay
    - Boredom clustering
    """
    proposals = []
    sessions = db.get_session_history(conn, limit=20, user_id=user_id)
    profile = db.get_profile(conn, user_id=user_id)

    if len(sessions) < 5:
        return []

    # Check: consecutive early exits
    _check_early_exits(sessions, proposals)

    # Check: persistent error types
    _check_persistent_errors(conn, proposals, user_id=user_id)

    # Check: boredom clustering
    _check_boredom(sessions, proposals)

    # Check: session duration trending down
    _check_duration_trend(sessions, proposals)

    # Check: accuracy plateau
    _check_accuracy_plateau(sessions, proposals)

    # Check: learning velocity decline
    _check_velocity_decline(conn, proposals, user_id=user_id)

    # Check: interest drift (lens engagement decay)
    _check_interest_drift(conn, sessions, proposals, user_id=user_id)

    return proposals


def _check_early_exits(sessions: list, proposals: list):
    """Detect consecutive early exits."""
    consecutive = 0
    for s in sessions[:10]:
        if s.get("early_exit"):
            consecutive += 1
        else:
            break

    if consecutive >= 3:
        proposals.append({
            "id": "early_exit_pattern",
            "trigger": "consecutive_early_exits",
            "observation": f"{consecutive} consecutive early exits detected.",
            "why_it_matters": "Repeated early exits suggest session length doesn't match "
                            "available time or energy.",
            "proposed_change": "Reduce default session from 12 items to 8 for the next 2 weeks. "
                             "If completion rate improves, gradually increase back.",
            "expected_benefit": "Session completion rate should reach 80%+ within 5 sessions.",
            "rollback": "Revert to 12 items per session.",
            "severity": "high",
        })


def _check_persistent_errors(conn, proposals: list, user_id: int = 1):
    """Detect error types that aren't improving."""
    # Compare last 5 sessions to 5 before that
    recent = conn.execute("""
        SELECT error_type, COUNT(*) as count FROM error_log
        WHERE user_id = ?
          AND session_id IN (SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 5)
        GROUP BY error_type
    """, (user_id, user_id)).fetchall()

    older = conn.execute("""
        SELECT error_type, COUNT(*) as count FROM error_log
        WHERE user_id = ?
          AND session_id IN (
            SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 5 OFFSET 5
        )
        GROUP BY error_type
    """, (user_id, user_id)).fetchall()

    recent_map = {r["error_type"]: r["count"] for r in recent}
    older_map = {r["error_type"]: r["count"] for r in older}

    for etype, count in recent_map.items():
        old_count = older_map.get(etype, 0)
        if count >= 5 and old_count > 0 and count >= old_count:
            proposals.append({
                "id": f"persistent_{etype}",
                "trigger": "persistent_error_type",
                "observation": f"'{etype}' errors not improving: {old_count} → {count} over last 10 sessions.",
                "why_it_matters": f"Persistent {etype} errors suggest the current drill format "
                                 "isn't helping. Different practice angle needed.",
                "proposed_change": _suggest_error_fix(etype),
                "expected_benefit": f"{etype} errors drop by 30% within 5 sessions.",
                "rollback": "Revert to default drill distribution.",
                "severity": "medium",
            })


def _suggest_error_fix(error_type: str) -> str:
    """Suggest a specific fix for a persistent error type."""
    fixes = {
        "tone": "Add tone-pair minimal pairs as warm-up: present two words "
                "differing only in tone, ask which matches a meaning. "
                "Add 1 extra tone drill per session.",
        "segment": "Slow down typing drills: show the pinyin syllable-by-syllable "
                   "before asking for full input. Add more listening-then-type exercises.",
        "ime_confusable": "Create a 'confusable pairs' drill set: present the two "
                         "confusable options side by side with meanings, then test.",
        "vocab": "Reduce new vocabulary introduction. Increase review cycles for "
                "struggling items. Consider adding reverse MC (english→hanzi) drills.",
        "grammar": "Embed grammar items in sentence contexts instead of isolation. "
                  "Add pattern-completion drills.",
        "register_mismatch": "Practice register awareness: present the same phrase "
                            "in casual vs formal contexts. Focus on 你/您 and similar pairs.",
        "particle_misuse": "Drill sentence-final particles (了/的/吗/呢) in context. "
                          "Present minimal pairs with different particles to build intuition.",
        "function_word_omission": "Increase exposure to function words in sentence drills. "
                                 "Inject items from the function_words content lens.",
        "temporal_sequencing": "Practice time expressions in sentence order. "
                              "Focus on 先...然后, 以前/以后 placement patterns.",
        "measure_word": "Pair measure words with their nouns in MC drills. "
                       "Create targeted drills: 'which measure word for X?'",
        "politeness_softening": "Practice polite request patterns (请, 能不能, 可以...吗). "
                               "Compare direct vs softened forms side by side.",
    }
    return fixes.get(error_type, "Adjust drill format for this error type.")


def _check_boredom(sessions: list, proposals: list):
    """Detect boredom clustering."""
    recent_boredom = sum(s.get("boredom_flags", 0) for s in sessions[:7])
    if recent_boredom >= 3:
        proposals.append({
            "id": "boredom_cluster",
            "trigger": "boredom_flags",
            "observation": f"{recent_boredom} boredom flags in last 7 sessions.",
            "why_it_matters": "Boredom signals suggest content or format staleness. "
                            "Engagement drives retention.",
            "proposed_change": "Rotate to highest-engagement content lens for next 3 sessions. "
                             "Introduce reverse MC and tone-pair drills for variety. "
                             "Offer 'confidence wins' mode as an option.",
            "expected_benefit": "Boredom flags drop to 0 within 3 sessions.",
            "rollback": "Revert to standard content selection.",
            "severity": "medium",
        })


def _check_duration_trend(sessions: list, proposals: list):
    """Detect sessions getting shorter (engagement declining)."""
    durations = [s.get("duration_seconds", 0) for s in sessions[:10] if s.get("duration_seconds")]
    if len(durations) < 5:
        return

    recent_avg = sum(durations[:5]) / 5
    older_avg = sum(durations[5:]) / max(len(durations[5:]), 1)

    if older_avg > 0 and recent_avg < older_avg * 0.6:
        proposals.append({
            "id": "duration_decline",
            "trigger": "session_duration",
            "observation": f"Average session duration dropped from {older_avg:.0f}s to {recent_avg:.0f}s.",
            "why_it_matters": "Shorter sessions mean less practice per sitting. "
                            "Could indicate fatigue or format issues.",
            "proposed_change": "Switch to mini sessions (90s) for 1 week as a reset, "
                             "then gradually increase. Consider time-of-day optimization.",
            "expected_benefit": "Session duration stabilizes within 1 week.",
            "rollback": "Return to standard session length.",
            "severity": "low",
        })


def _check_interest_drift(conn, sessions: list, proposals: list, user_id: int = 1):
    """Detect interest drift — when lens engagement scores decay.

    Compares boredom/early-exit rates per content lens over recent sessions.
    If a lens is getting consistently skipped or bored-through, suggest rotating away.
    """
    if len(sessions) < 7:
        return

    # Get lens engagement from profile
    profile = db.get_profile(conn, user_id=user_id)
    lens_keys = [
        ("lens_quiet_observation", "quiet_observation"),
        ("lens_institutions", "institutions"),
        ("lens_urban_texture", "urban_texture"),
        ("lens_humane_mystery", "humane_mystery"),
        ("lens_identity", "identity"),
        ("lens_comedy", "comedy"),
        ("lens_food", "food"),
        ("lens_travel", "travel"),
    ]

    # Check which lenses have items that are getting low accuracy
    low_engagement_lenses = []
    for db_key, lens_name in lens_keys:
        score = profile.get(db_key) or 0.5
        # Check accuracy on this lens's items in recent sessions
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN el.id IS NOT NULL THEN 1 ELSE 0 END) as errors
            FROM progress p
            JOIN content_item ci ON p.content_item_id = ci.id
            LEFT JOIN error_log el ON el.content_item_id = ci.id
                AND el.user_id = ?
                AND el.session_id IN (SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 7)
            WHERE ci.content_lens = ? AND p.user_id = ? AND p.last_review_date >= date('now', '-14 days')
        """, (user_id, user_id, lens_name, user_id)).fetchone()

        total = row["total"] or 0
        errors = row["errors"] or 0
        if total >= 3 and errors / total > 0.5:
            low_engagement_lenses.append(lens_name)

    if low_engagement_lenses:
        proposals.append({
            "id": "interest_drift",
            "trigger": "interest_drift",
            "observation": f"High error rates on content lenses: {', '.join(low_engagement_lenses)}. "
                          "This may indicate disengagement or difficulty mismatch.",
            "why_it_matters": "When a content area consistently produces errors, it may be "
                            "because the learner has lost interest or the material doesn't "
                            "match their current level. Forcing it reduces motivation.",
            "proposed_change": f"Reduce weight of {', '.join(low_engagement_lenses)} lenses by 30% "
                             "for 2 weeks. Increase weight of highest-engagement lenses. "
                             "Re-evaluate after 10 sessions.",
            "expected_benefit": "Overall accuracy improves as content better matches interest.",
            "rollback": "Restore default lens weights.",
            "severity": "medium",
        })

    # Also check for lenses with high engagement that could use more items
    high_lenses = []
    for db_key, lens_name in lens_keys:
        score = profile.get(db_key) or 0.5
        if score >= 0.8:
            row = conn.execute(
                "SELECT COUNT(*) FROM content_item WHERE content_lens = ? AND status = 'drill_ready'",
                (lens_name,)
            ).fetchone()
            item_count = row[0] if row else 0
            row = conn.execute("""
                SELECT COUNT(*) FROM progress p
                JOIN content_item ci ON p.content_item_id = ci.id
                WHERE ci.content_lens = ? AND p.user_id = ? AND p.streak_correct >= 3
            """, (lens_name, user_id)).fetchone()
            mastered = row[0] if row else 0
            if item_count > 0 and mastered / item_count > 0.8:
                high_lenses.append(lens_name)

    if high_lenses:
        proposals.append({
            "id": "content_expansion",
            "trigger": "interest_drift",
            "observation": f"High-engagement lenses nearly mastered: {', '.join(high_lenses)}. "
                          "Learner may benefit from new content in these areas.",
            "why_it_matters": "When a learner's favorite content areas run dry, "
                            "motivation can drop. Feed the interest.",
            "proposed_change": f"Source new content for: {', '.join(high_lenses)}. "
                             "Consider importing subtitles or new vocabulary sets.",
            "expected_benefit": "Sustained engagement through interest-aligned content.",
            "rollback": "No rollback needed — additive change only.",
            "severity": "low",
        })


def _check_accuracy_plateau(sessions: list, proposals: list):
    """Detect accuracy plateau (not improving over 6+ sessions)."""
    recent = sessions[:3]
    older = sessions[3:6]

    if len(recent) < 3 or len(older) < 3:
        return

    def avg_accuracy(sess_list):
        total = sum(s.get("items_completed", 0) for s in sess_list)
        correct = sum(s.get("items_correct", 0) for s in sess_list)
        return correct / total if total > 0 else 0

    recent_acc = avg_accuracy(recent)
    older_acc = avg_accuracy(older)

    if abs(recent_acc - older_acc) < 0.05 and recent_acc < 0.85:
        proposals.append({
            "id": "accuracy_plateau",
            "trigger": "accuracy_stall",
            "observation": f"Accuracy flat at ~{recent_acc:.0%} over 6 sessions "
                         f"(was {older_acc:.0%}, now {recent_acc:.0%}).",
            "why_it_matters": "A plateau below 85% suggests the difficulty mix needs adjustment.",
            "proposed_change": "Temporarily reduce new items to 0 for 3 sessions. "
                             "Focus exclusively on items with <70% accuracy. "
                             "Add catch-up sessions targeting weak spots.",
            "expected_benefit": "Accuracy breaks 80% within 5 sessions.",
            "rollback": "Resume normal new-item introduction.",
            "severity": "medium",
        })


def _check_velocity_decline(conn, proposals: list, user_id: int = 1):
    """Detect when mastery stage transition rate has dropped significantly.

    Compares items advancing a mastery stage in last 5 sessions vs. 5 before that.
    """
    recent_ids = conn.execute("""
        SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 5
    """, (user_id,)).fetchall()
    older_ids = conn.execute("""
        SELECT id FROM session_log WHERE user_id = ? ORDER BY started_at DESC LIMIT 5 OFFSET 5
    """, (user_id,)).fetchall()

    if len(recent_ids) < 5 or len(older_ids) < 5:
        return

    recent_session_ids = tuple(r["id"] for r in recent_ids)
    older_session_ids = tuple(r["id"] for r in older_ids)

    def count_transitions(session_ids):
        placeholders = ",".join("?" * len(session_ids))
        row = conn.execute(f"""
            SELECT COUNT(DISTINCT content_item_id) as cnt
            FROM progress
            WHERE user_id = ?
              AND last_review_date IN (
                SELECT date(started_at) FROM session_log WHERE id IN ({placeholders})
            ) AND mastery_stage NOT IN ('seen', 'weak')
              AND streak_correct >= 2
        """, (user_id,) + session_ids).fetchone()
        return row["cnt"] if row else 0

    recent_transitions = count_transitions(recent_session_ids)
    older_transitions = count_transitions(older_session_ids)

    if older_transitions >= 3 and recent_transitions < older_transitions * 0.5:
        proposals.append({
            "id": "velocity_decline",
            "trigger": "velocity_decline",
            "observation": f"Learning velocity dropped: {older_transitions} stage advances "
                          f"in older sessions vs {recent_transitions} recently.",
            "why_it_matters": "Slower progress can indicate difficulty mismatch or fatigue. "
                            "Reviewing weak items before adding new ones can restore momentum.",
            "proposed_change": "Reduce new items to 0 for 3 sessions. Focus on items "
                             "stuck at 'seen' or 'passed_once' stages.",
            "expected_benefit": "Stage transition rate recovers within 5 sessions.",
            "rollback": "Resume normal new-item introduction.",
            "severity": "medium",
        })


# ── Proposal management ──────────────────────────────

def save_proposal(conn, proposal: dict, user_id: int = 1):
    """Save a proposal to the improvement_log."""
    conn.execute("""
        INSERT INTO improvement_log (user_id, trigger_reason, observation, proposed_change, status)
        VALUES (?, ?, ?, ?, 'proposed')
    """, (user_id, proposal["trigger"], proposal["observation"],
          json.dumps(proposal)))
    conn.commit()


def get_proposals(conn, status: str = "proposed", user_id: int = 1) -> list:
    """Get all proposals with a given status."""
    rows = conn.execute("""
        SELECT * FROM improvement_log WHERE user_id = ? AND status = ?
        ORDER BY created_at DESC
    """, (user_id, status)).fetchall()
    return [dict(r) for r in rows]


def apply_proposal(conn, proposal_id: int, user_id: int = 1):
    """Mark a proposal as applied and execute its changes."""
    row = conn.execute(
        "SELECT * FROM improvement_log WHERE id = ? AND user_id = ?", (proposal_id, user_id)
    ).fetchone()

    if row:
        # Execute proposal-specific changes
        proposal_data = {}
        try:
            proposal_data = json.loads(row["proposed_change"]) if row["proposed_change"] else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse proposed_change JSON for proposal %d", proposal_id)

        trigger = row["trigger_reason"]
        _execute_proposal(conn, trigger, proposal_data, user_id=user_id)

    conn.execute("""
        UPDATE improvement_log SET status = 'approved', applied_at = ?
        WHERE id = ? AND user_id = ?
    """, (datetime.now(timezone.utc).isoformat(), proposal_id, user_id))
    conn.commit()


def _execute_proposal(conn, trigger: str, proposal_data: dict, user_id: int = 1):
    """Execute the actual system changes for a proposal."""
    if trigger == "consecutive_early_exits":
        # Reduce session length to 8
        conn.execute(
            "UPDATE learner_profile SET preferred_session_length = 8 WHERE user_id = ?",
            (user_id,)
        )
    elif trigger == "session_duration":
        # Switch to shorter sessions (mini-like)
        conn.execute(
            "UPDATE learner_profile SET preferred_session_length = 6 WHERE user_id = ?",
            (user_id,)
        )
    elif trigger == "boredom_flags":
        # Boost highest-engagement lens, reduce least-engaged
        profile = db.get_profile(conn, user_id=user_id)
        lens_cols = [
            "lens_quiet_observation", "lens_institutions", "lens_urban_texture",
            "lens_humane_mystery", "lens_identity", "lens_comedy",
            "lens_food", "lens_travel",
        ]
        scores = {c: profile.get(c) or 0.5 for c in lens_cols}
        if scores:
            top = max(scores, key=scores.get)
            bottom = min(scores, key=scores.get)
            assert top in _VALID_LENS_COLS and bottom in _VALID_LENS_COLS
            conn.execute(
                f"UPDATE learner_profile SET {top} = MIN(1.0, {top} + 0.2) WHERE user_id = ?",
                (user_id,)
            )
            conn.execute(
                f"UPDATE learner_profile SET {bottom} = MAX(0.1, {bottom} - 0.2) WHERE user_id = ?",
                (user_id,)
            )
    elif trigger == "persistent_error_type":
        # Increase error_focus limit for that error type
        # Extract error type from proposal observation if available
        obs = proposal_data.get("observation", "") if isinstance(proposal_data, dict) else ""
        # Set a session override: more error-focus items
        conn.execute(
            "UPDATE learner_profile SET preferred_session_length = "
            "CASE WHEN preferred_session_length < 15 THEN preferred_session_length + 2 "
            "ELSE preferred_session_length END WHERE user_id = ?",
            (user_id,)
        )
    elif trigger == "accuracy_stall":
        # Pause new items for 3 sessions by setting a temp override
        # Use preferred_session_length as signal (reduce to consolidation mode)
        profile = db.get_profile(conn, user_id=user_id)
        current = profile.get("preferred_session_length") or 12
        conn.execute(
            "UPDATE learner_profile SET preferred_session_length = ? WHERE user_id = ?",
            (max(6, current - 2), user_id)
        )
    elif trigger == "interest_drift":
        # Reduce weight of low-engagement lenses
        profile = db.get_profile(conn, user_id=user_id)
        lens_cols = [
            "lens_quiet_observation", "lens_institutions", "lens_urban_texture",
            "lens_humane_mystery", "lens_identity", "lens_comedy",
            "lens_food", "lens_travel",
        ]
        for col in lens_cols:
            assert col in _VALID_LENS_COLS
            score = profile.get(col) or 0.5
            if score < 0.4:
                conn.execute(
                    f"UPDATE learner_profile SET {col} = MAX(0.1, {col} - 0.1) WHERE user_id = ?",
                    (user_id,)
                )


def rollback_proposal(conn, proposal_id: int, user_id: int = 1):
    """Mark a proposal as rolled back."""
    conn.execute("""
        UPDATE improvement_log SET status = 'rolled_back', rolled_back_at = ?
        WHERE id = ? AND user_id = ?
    """, (datetime.now(timezone.utc).isoformat(), proposal_id, user_id))
    conn.commit()


def reject_proposal(conn, proposal_id: int, user_id: int = 1):
    """Mark a proposal as rejected."""
    conn.execute("""
        UPDATE improvement_log SET status = 'rejected' WHERE id = ? AND user_id = ?
    """, (proposal_id, user_id))
    conn.commit()
