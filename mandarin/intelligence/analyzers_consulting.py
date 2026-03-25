"""Marketing & product consulting analyzers — Bain/BCG/McKinsey frameworks.

Covers: NPS Proxy, Customer Effort Score, Customer Journey Map, Brand Health,
Jobs to Be Done, Kano Model, Content ROI.
"""

from __future__ import annotations

import logging
import sqlite3

from ._base import _finding, _safe_scalar, _safe_query, _safe_query_all

logger = logging.getLogger(__name__)


# ── 1. NPS Proxy (Net Promoter Score) ────────────────────────────────


def _analyze_nps_proxy(conn) -> list[dict]:
    """Net Promoter Score from user_feedback ratings (0-10 scale).

    Promoters: 9-10, Passives: 7-8, Detractors: 0-6.
    NPS = %Promoters - %Detractors. Range: -100 to +100.
    """
    findings = []

    try:
        feedback = _safe_query_all(conn, """
            SELECT rating FROM user_feedback
            WHERE feedback_type = 'nps'
              AND rating IS NOT NULL
              AND created_at >= datetime('now', '-90 days')
        """)

        if not feedback or len(feedback) < 5:
            findings.append(_finding(
                "brand_health", "medium" if not feedback else "low",
                f"NPS: insufficient data ({len(feedback or [])} responses in 90 days)",
                "Net Promoter Score requires at least 5 responses for "
                "directional signal. Currently below that threshold.",
                "Prompt NPS feedback after session 10, 25, and 50. One "
                "question: 'How likely would you recommend aelu to a friend?'",
                "Add NPS prompt to post-session flow at milestone sessions.",
                "Cannot measure brand health without NPS data.",
                ["mandarin/runner.py", "mandarin/web/session_routes.py"],
            ))
            return findings

        total = len(feedback)
        promoters = sum(1 for r in feedback if (r["rating"] or 0) >= 9)
        detractors = sum(1 for r in feedback if (r["rating"] or 0) <= 6)
        nps = round((promoters - detractors) / total * 100)

        if nps < 0:
            severity = "critical"
        elif nps < 20:
            severity = "high"
        elif nps < 50:
            severity = "medium"
        else:
            severity = "low"

        findings.append(_finding(
            "brand_health", severity,
            f"NPS: {nps} ({promoters} promoters, {detractors} detractors, {total} total)",
            f"Net Promoter Score is {nps}. "
            f"Promoters (9-10): {promoters} ({promoters/total*100:.0f}%), "
            f"Passives (7-8): {total - promoters - detractors} ({(total-promoters-detractors)/total*100:.0f}%), "
            f"Detractors (0-6): {detractors} ({detractors/total*100:.0f}%).",
            "Focus on converting passives to promoters and reducing detractor drivers."
            if nps < 50 else "Strong NPS. Maintain product quality.",
            "Analyze detractor comments for themes. Cross-reference with churn data.",
            "NPS is the leading indicator of organic growth.",
            ["mandarin/web/session_routes.py"],
        ))

        # Extract detractor themes via LLM if available
        if detractors > 0:
            try:
                detractor_comments = _safe_query_all(conn, """
                    SELECT comment FROM user_feedback
                    WHERE feedback_type = 'nps' AND rating <= 6
                      AND comment IS NOT NULL AND comment != ''
                      AND created_at >= datetime('now', '-90 days')
                    LIMIT 10
                """)
                if detractor_comments and len(detractor_comments) >= 3:
                    from ..ai.ollama_client import generate, is_ollama_available
                    if is_ollama_available():
                        comments = "\n".join(r["comment"] for r in detractor_comments)
                        resp = generate(
                            prompt=f"Summarize the top 3 themes from these detractor comments in 2 sentences:\n{comments}",
                            system="You are a product analyst. Be concise and specific.",
                            temperature=0.2, max_tokens=150,
                            task_type="nps_analysis", conn=conn,
                        )
                        if resp.success:
                            findings.append(_finding(
                                "brand_health", "low",
                                "NPS detractor themes (LLM analysis)",
                                resp.text.strip(),
                                "Address the top detractor theme in the next product cycle.",
                                "Review detractor feedback and create work items.",
                                "Understanding why detractors are unhappy is the path to NPS improvement.",
                                ["mandarin/web/admin_routes.py"],
                            ))
            except Exception:
                pass

    except Exception as e:
        logger.debug("NPS proxy analyzer failed: %s", e)

    return findings


# ── 2. Customer Effort Score (CES) Proxy ─────────────────────────────


def _analyze_ces_proxy(conn) -> list[dict]:
    """Customer Effort Score: how hard is the product to use.

    Composite from: session completion (40%), absence of frustration signals (20%),
    error recovery (20%), hint dependency (20%). Higher = easier to use.
    """
    findings = []

    try:
        # Component 1: Session completion rate (40%)
        sessions = _safe_query(conn, """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN items_completed >= items_planned THEN 1 ELSE 0 END) as completed
            FROM session_log
            WHERE started_at >= datetime('now', '-30 days')
              AND items_planned > 0
        """)
        if not sessions or sessions["total"] < 5:
            return findings  # Not enough data

        completion_rate = sessions["completed"] / sessions["total"] if sessions["total"] > 0 else 0
        completion_score = min(100, completion_rate * 100)

        # Component 2: Absence of rage clicks / frustration (20%)
        # Check client_event for rage_click or error events
        frustration_events = _safe_scalar(conn, """
            SELECT COUNT(*) FROM client_event
            WHERE category = 'ux' AND event IN ('rage_click', 'rapid_back', 'error_encounter')
              AND created_at >= datetime('now', '-30 days')
        """, default=0)
        total_events = _safe_scalar(conn, """
            SELECT COUNT(*) FROM client_event
            WHERE created_at >= datetime('now', '-30 days')
        """, default=1)
        frustration_rate = frustration_events / max(1, total_events)
        frustration_score = max(0, (1 - frustration_rate * 10)) * 100  # 10% frustration = 0 score

        # Component 3: Error recovery (20%)
        # Users who hit errors but still complete sessions
        error_sessions = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT session_id) FROM review_event
            WHERE correct = 0
              AND reviewed_at >= datetime('now', '-30 days')
        """, default=0)
        completed_after_error = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT sl.id) FROM session_log sl
            WHERE sl.items_completed >= sl.items_planned
              AND sl.started_at >= datetime('now', '-30 days')
              AND EXISTS (
                  SELECT 1 FROM review_event re
                  WHERE re.session_id = sl.id AND re.correct = 0
              )
        """, default=0)
        error_recovery = completed_after_error / max(1, error_sessions)
        recovery_score = min(100, error_recovery * 100)

        # Component 4: Hint dependency (20%)
        # Lower hint usage = easier product (users can succeed without help)
        total_reviews = _safe_scalar(conn, """
            SELECT COUNT(*) FROM review_event
            WHERE reviewed_at >= datetime('now', '-30 days')
        """, default=1)
        hint_reviews = _safe_scalar(conn, """
            SELECT COUNT(*) FROM review_event
            WHERE reviewed_at >= datetime('now', '-30 days')
              AND hint_used = 1
        """, default=0)
        hint_rate = hint_reviews / max(1, total_reviews)
        hint_score = max(0, (1 - hint_rate * 5)) * 100  # 20% hint usage = 0 score

        # Composite CES
        ces = round(
            completion_score * 0.4 +
            frustration_score * 0.2 +
            recovery_score * 0.2 +
            hint_score * 0.2
        )

        if ces < 50:
            severity = "high"
            rec = "Product is too effortful. Simplify the hardest interaction points."
        elif ces < 70:
            severity = "medium"
            rec = "Moderate effort. Identify highest-friction drill types and improve them."
        else:
            severity = "low"
            rec = "Low effort — product is easy to use."

        findings.append(_finding(
            "ux", severity,
            f"Customer Effort Score: {ces}/100",
            f"CES composite: completion {completion_score:.0f} (40%), "
            f"low-frustration {frustration_score:.0f} (20%), "
            f"error-recovery {recovery_score:.0f} (20%), "
            f"low-hint-dependency {hint_score:.0f} (20%).",
            rec,
            "Identify lowest-scoring CES component and improve it.",
            "CES predicts retention better than satisfaction scores.",
            ["mandarin/runner.py", "mandarin/drills/base.py"],
        ))

    except Exception as e:
        logger.debug("CES proxy analyzer failed: %s", e)

    return findings


# ── 3. Customer Journey Map ──────────────────────────────────────────


def _analyze_customer_journey(conn) -> list[dict]:
    """Customer journey: drop-off analysis across lifecycle stages."""
    findings = []

    try:
        total_users = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user WHERE is_admin = 0
        """, default=0)

        if total_users < 3:
            return findings

        # Compute drop-off at each stage
        stages = []

        # Signup → First Session
        with_first_session = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE is_admin = 0 AND first_session_at IS NOT NULL
        """, default=0)
        stages.append(("signup → first_session", total_users, with_first_session))

        # First Session → Activation
        activated = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE is_admin = 0 AND activation_at IS NOT NULL
        """, default=0)
        if with_first_session > 0:
            stages.append(("first_session → activation", with_first_session, activated))

        # Activation → D7 Retention
        d7_retained = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT sl.user_id) FROM session_log sl
            JOIN user u ON sl.user_id = u.id
            WHERE u.is_admin = 0
              AND u.first_session_at IS NOT NULL
              AND sl.completed_at >= datetime(u.first_session_at, '+7 days')
        """, default=0)
        if activated > 0:
            stages.append(("activation → D7_retention", activated, d7_retained))

        # D7 → Paid
        paid_users = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user
            WHERE is_admin = 0
              AND subscription_tier IN ('paid', 'premium')
        """, default=0)
        if d7_retained > 0:
            stages.append(("D7_retention → paid", d7_retained, paid_users))

        # Find worst drop-off
        for stage_name, start, end in stages:
            if start == 0:
                continue
            drop_off_pct = round((1 - end / start) * 100, 1)
            conversion_pct = round(end / start * 100, 1)

            if drop_off_pct > 70:
                severity = "high"
            elif drop_off_pct > 50:
                severity = "medium"
            else:
                continue  # Only flag high drop-offs

            findings.append(_finding(
                "journey", severity,
                f"Journey drop-off: {stage_name} ({drop_off_pct}% lost)",
                f"Stage '{stage_name}': {start} entered, {end} continued "
                f"({conversion_pct}% conversion, {drop_off_pct}% drop-off).",
                f"Investigate why users drop off at '{stage_name}'. "
                f"This is the biggest leak in the conversion funnel.",
                f"Analyze user behavior at the '{stage_name}' transition point.",
                "Journey drop-offs directly impact revenue.",
                ["mandarin/web/onboarding_routes.py", "mandarin/marketing_hooks.py"],
            ))

    except Exception as e:
        logger.debug("Customer journey analyzer failed: %s", e)

    return findings


# ── 4. Brand Health Proxy ────────────────────────────────────────────


def _analyze_brand_health(conn) -> list[dict]:
    """Brand health composite: NPS + referral velocity + feedback sentiment."""
    findings = []

    try:
        # Referral velocity (k-factor)
        try:
            from ..marketing_hooks import compute_viral_coefficient
            viral = compute_viral_coefficient(conn=conn)
            k_factor = viral.get("k_factor", 0)
        except Exception:
            k_factor = 0

        # Feedback volume (engagement signal)
        feedback_30d = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user_feedback
            WHERE created_at >= datetime('now', '-30 days')
        """, default=0)

        # Compute composite brand health (0-100)
        # k_factor contribution (40%): k > 0.5 = 100, k = 0 = 0
        k_score = min(100, k_factor * 200)
        # Feedback engagement (30%): >10 feedbacks/month = 100
        feedback_score = min(100, feedback_30d * 10)
        # NPS contribution (30%): delegated to NPS analyzer — just check if measured
        has_nps = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user_feedback
            WHERE feedback_type = 'nps' AND created_at >= datetime('now', '-90 days')
        """, default=0)
        nps_score = 50 if has_nps >= 5 else 0

        brand_health = round(k_score * 0.4 + feedback_score * 0.3 + nps_score * 0.3)

        if brand_health < 30:
            findings.append(_finding(
                "brand_health", "medium",
                f"Brand health composite: {brand_health}/100",
                f"Components: referral velocity {k_score:.0f}/100 (k={k_factor:.3f}), "
                f"feedback engagement {feedback_score:.0f}/100 ({feedback_30d} in 30d), "
                f"NPS measured: {'yes' if has_nps >= 5 else 'no'}.",
                "Increase brand health by encouraging referrals, collecting NPS "
                "feedback, and building word-of-mouth through product quality.",
                "Review referral program visibility, add NPS prompts at milestones.",
                "Brand health predicts sustainable organic growth.",
                ["mandarin/marketing_hooks.py", "mandarin/runner.py"],
            ))

    except Exception as e:
        logger.debug("Brand health analyzer failed: %s", e)

    return findings


# ── 5. Jobs to Be Done (LLM-assisted) ───────────────────────────────


def _analyze_jtbd_coverage(conn) -> list[dict]:
    """JTBD: infer user jobs from behavioral data and check feature coverage."""
    findings = []

    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        if "pi_jtbd_map" not in tables:
            findings.append(_finding(
                "strategic", "low",
                "No Jobs to Be Done mapping",
                "The pi_jtbd_map table does not exist. JTBD analysis infers "
                "what job users are hiring aelu for (exam prep, daily habit, "
                "conversation prep, reading) and ensures feature coverage.",
                "Run migration to create the JTBD table and seed initial jobs.",
                "Create pi_jtbd_map table and seed from behavioral data.",
                "Without JTBD, feature prioritization lacks user intent context.",
                ["mandarin/db/core.py"],
            ))
            return findings

        # Check if JTBD map has entries
        jtbd_count = _safe_scalar(conn, "SELECT COUNT(*) FROM pi_jtbd_map", default=0)
        if jtbd_count == 0:
            # Try to infer jobs from behavioral data
            findings.append(_finding(
                "strategic", "medium",
                "JTBD map is empty — no user jobs identified",
                "The JTBD table exists but has no entries. User jobs should "
                "be seeded from behavioral patterns: session timing, drill "
                "type distribution, and HSK level focus.",
                "Seed the JTBD map with initial jobs: 'HSK exam prep', "
                "'daily vocabulary habit', 'conversation prep', 'reading practice'.",
                "Analyze session patterns to classify users into job segments.",
                "JTBD drives feature priority and marketing positioning.",
                ["mandarin/intelligence/analyzers_consulting.py"],
            ))

    except Exception as e:
        logger.debug("JTBD analyzer failed: %s", e)

    return findings


# ── 6. Kano Model Classification ────────────────────────────────────


def _analyze_kano_classification(conn) -> list[dict]:
    """Kano model: behavioral classification of features."""
    findings = []

    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        if "pi_kano_classification" not in tables:
            findings.append(_finding(
                "strategic", "low",
                "No Kano model feature classification",
                "Features are not classified into must-have, performance, or "
                "delighter categories. Kano classification informs which features "
                "to fix (must-haves), improve (performance), or promote (delighters).",
                "Run migration to create Kano table. Classify features behaviorally.",
                "Create pi_kano_classification and classify from usage/retention data.",
                "Without Kano, feature prioritization is uninformed.",
                ["mandarin/db/core.py"],
            ))
            return findings

        # Check for must-haves with quality issues
        must_haves_with_issues = _safe_query_all(conn, """
            SELECT feature_key, feature_name, usage_rate
            FROM pi_kano_classification
            WHERE category = 'must_have' AND usage_rate < 0.7
        """)
        for mh in (must_haves_with_issues or []):
            findings.append(_finding(
                "ux", "high",
                f"Must-have feature '{mh['feature_name']}' has low usage ({mh['usage_rate']*100:.0f}%)",
                f"Kano must-have feature '{mh['feature_name']}' is used by "
                f"only {mh['usage_rate']*100:.0f}% of retained users. Must-haves "
                f"should be used by >80%. Low usage suggests accessibility or "
                f"discoverability problems.",
                f"Investigate why '{mh['feature_name']}' is underused. "
                f"Consider UX improvements, better onboarding, or feature placement.",
                f"Review feature '{mh['feature_key']}' accessibility and onboarding.",
                "Must-have features with low usage signal fundamental UX issues.",
                ["mandarin/web/static/app.js"],
            ))

    except Exception as e:
        logger.debug("Kano analyzer failed: %s", e)

    return findings


# ── 7. Content ROI ──────────────────────────────────────────────────


def _analyze_content_roi(conn) -> list[dict]:
    """Content ROI: which content types drive retention and conversion."""
    findings = []

    try:
        # Need enough users and sessions for meaningful analysis
        user_count = _safe_scalar(conn, """
            SELECT COUNT(*) FROM user WHERE is_admin = 0 AND first_session_at IS NOT NULL
        """, default=0)

        if user_count < 10:
            return findings  # Not enough data

        # Compare drill type usage between retained and churned users
        retained_types = _safe_query_all(conn, """
            SELECT re.drill_type, COUNT(*) as cnt
            FROM review_event re
            JOIN user u ON re.user_id = u.id
            WHERE u.is_admin = 0
              AND EXISTS (
                  SELECT 1 FROM session_log sl
                  WHERE sl.user_id = u.id
                    AND sl.completed_at >= datetime('now', '-14 days')
              )
            GROUP BY re.drill_type
            ORDER BY cnt DESC
            LIMIT 10
        """)

        churned_types = _safe_query_all(conn, """
            SELECT re.drill_type, COUNT(*) as cnt
            FROM review_event re
            JOIN user u ON re.user_id = u.id
            WHERE u.is_admin = 0
              AND NOT EXISTS (
                  SELECT 1 FROM session_log sl
                  WHERE sl.user_id = u.id
                    AND sl.completed_at >= datetime('now', '-14 days')
              )
              AND u.first_session_at IS NOT NULL
            GROUP BY re.drill_type
            ORDER BY cnt DESC
            LIMIT 10
        """)

        if retained_types and churned_types:
            retained_set = {r["drill_type"] for r in retained_types}
            churned_set = {r["drill_type"] for r in churned_types}

            # Drill types used by retained but NOT churned users = high ROI
            high_roi = retained_set - churned_set
            if high_roi:
                findings.append(_finding(
                    "strategic", "low",
                    f"High-ROI content types: {', '.join(sorted(high_roi))}",
                    f"Drill types {sorted(high_roi)} are used by retained users "
                    f"but not by churned users. These may be features that, "
                    f"once discovered, increase retention.",
                    "Increase visibility and onboarding for high-ROI drill types.",
                    "Promote high-ROI drill types earlier in the learner journey.",
                    "Content ROI analysis: features that correlate with retention.",
                    ["mandarin/scheduler.py"],
                ))

    except Exception as e:
        logger.debug("Content ROI analyzer failed: %s", e)

    return findings


# ── 8. Modality Health (outside core drill loop) ─────────────────────


def _analyze_modality_health(conn) -> list[dict]:
    """Consulting-grade audit of learning features outside the core SRS loop.

    Evaluates: reading passages, listening comprehension, conversation
    practice, grammar study, and media shelf — each as a product line
    within a portfolio (BCG matrix logic applied per modality).

    For each modality: adoption rate, engagement depth, quality signal,
    and contribution to retention. Flags underperforming or abandoned
    modalities as strategic risks.
    """
    findings = []

    try:
        # Total active users (baseline for adoption rate)
        active_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM session_log
            WHERE completed_at >= datetime('now', '-30 days')
        """, default=0)

        if active_users < 3:
            return findings  # Not enough data

        # ── Reading passages ──
        reading_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM reading_progress
            WHERE completed_at >= datetime('now', '-30 days')
        """, default=0)
        reading_adoption = round(reading_users / max(1, active_users) * 100, 1)

        reading_quality = _safe_query(conn, """
            SELECT AVG(CAST(questions_correct AS REAL) / NULLIF(questions_total, 0)) as avg_score,
                   AVG(words_looked_up) as avg_lookups,
                   COUNT(*) as sessions
            FROM reading_progress
            WHERE completed_at >= datetime('now', '-30 days')
              AND questions_total > 0
        """)

        if reading_adoption < 20:
            findings.append(_finding(
                "strategic", "medium",
                f"Reading practice: low adoption ({reading_adoption}% of active users)",
                f"Only {reading_adoption}% of active users engaged with reading "
                f"passages in the last 30 days ({reading_users}/{active_users}). "
                f"DOCTRINE §4 requires modality integration — reading should be a "
                f"core part of the learning journey, not an optional add-on.",
                "Increase reading visibility: ensure the scheduler includes reading "
                "blocks, surface reading in the dashboard, and check if reading is "
                "gated behind a paywall that's too restrictive.",
                "Check scheduler.py reading block allocation and tier_gate.py reading access.",
                "Low reading adoption means most learners miss comprehension practice.",
                ["mandarin/scheduler.py", "mandarin/tier_gate.py"],
            ))
        elif reading_quality and reading_quality["avg_score"] and reading_quality["avg_score"] < 0.5:
            findings.append(_finding(
                "drill_quality", "medium",
                f"Reading comprehension: low average score ({reading_quality['avg_score']*100:.0f}%)",
                f"Average reading comprehension score is {reading_quality['avg_score']*100:.0f}% "
                f"across {reading_quality['sessions']} sessions. Average lookups per "
                f"passage: {reading_quality['avg_lookups']:.1f}. Passages may be too "
                f"difficult for current learner levels.",
                "Review passage difficulty vs. learner HSK level. Ensure passages "
                "match the learner's vocabulary range.",
                "Check passage HSK levels vs. user levels in reading_progress.",
                "Low comprehension signals content-learner mismatch.",
                ["mandarin/web/session_routes.py"],
            ))

        # ── Listening comprehension ──
        listening_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM listening_progress
            WHERE completed_at >= datetime('now', '-30 days')
        """, default=0)
        listening_adoption = round(listening_users / max(1, active_users) * 100, 1)

        listening_quality = _safe_query(conn, """
            SELECT AVG(comprehension_score) as avg_score,
                   AVG(replays) as avg_replays,
                   AVG(playback_speed) as avg_speed,
                   COUNT(*) as sessions
            FROM listening_progress
            WHERE completed_at >= datetime('now', '-30 days')
        """)

        if listening_adoption < 15:
            findings.append(_finding(
                "strategic", "medium",
                f"Listening practice: low adoption ({listening_adoption}% of active users)",
                f"Only {listening_adoption}% of active users engaged with listening "
                f"comprehension in the last 30 days ({listening_users}/{active_users}). "
                f"Listening is critical for real-world Mandarin use.",
                "Increase listening block frequency in scheduler. Check if listening "
                "content exists for all active HSK levels.",
                "Check scheduler.py listening block allocation and content availability.",
                "Low listening adoption limits real-world language skill.",
                ["mandarin/scheduler.py"],
            ))
        elif listening_quality and listening_quality["avg_replays"] and listening_quality["avg_replays"] > 3:
            findings.append(_finding(
                "drill_quality", "low",
                f"Listening: high replay rate (avg {listening_quality['avg_replays']:.1f} replays/session)",
                f"Learners replay listening passages {listening_quality['avg_replays']:.1f} times "
                f"on average, suggesting content is too fast or too difficult. "
                f"Average playback speed: {listening_quality['avg_speed']:.2f}x.",
                "Consider defaulting to slower playback speed for struggling "
                "learners, or reducing passage complexity.",
                "Review listening content difficulty and playback defaults.",
                "High replay rate signals difficulty mismatch.",
                ["mandarin/web/session_routes.py"],
            ))

        # ── Conversation / dialogue ──
        conv_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM review_event
            WHERE drill_type = 'dialogue'
              AND reviewed_at >= datetime('now', '-30 days')
        """, default=0)
        conv_adoption = round(conv_users / max(1, active_users) * 100, 1)

        _safe_query(conn, """
            SELECT AVG(score) as avg_score, COUNT(*) as attempts
            FROM review_event
            WHERE drill_type = 'dialogue'
              AND reviewed_at >= datetime('now', '-30 days')
              AND score IS NOT NULL
        """)

        if conv_adoption < 10:
            findings.append(_finding(
                "strategic", "low",
                f"Conversation practice: low adoption ({conv_adoption}% of active users)",
                f"Only {conv_adoption}% of active users engaged with conversation "
                f"drills in the last 30 days. Conversation is a Three Horizons H2 "
                f"feature — important for differentiation but not yet widely adopted.",
                "Promote conversation practice after learners reach stable mastery "
                "on enough vocabulary. Consider lowering the eligibility threshold.",
                "Check conversation block scheduling and eligibility requirements.",
                "Low conversation adoption limits differentiation value.",
                ["mandarin/scheduler.py", "mandarin/conversation.py"],
            ))

        # ── Grammar study ──
        grammar_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM grammar_progress
            WHERE studied_at >= datetime('now', '-30 days')
        """, default=0)
        grammar_adoption = round(grammar_users / max(1, active_users) * 100, 1)

        _safe_query(conn, """
            SELECT AVG(CAST(drill_correct AS REAL) / NULLIF(drill_attempts, 0)) as avg_accuracy,
                   COUNT(*) as learners
            FROM grammar_progress
            WHERE studied_at >= datetime('now', '-30 days')
              AND drill_attempts > 0
        """)

        if grammar_adoption < 15 and grammar_users > 0:
            findings.append(_finding(
                "strategic", "low",
                f"Grammar study: low adoption ({grammar_adoption}% of active users)",
                f"Only {grammar_adoption}% of active users have grammar progress "
                f"in the last 30 days. DOCTRINE §1: grammar should be introduced "
                f"through sentences already encountered, not in isolation.",
                "Grammar should surface naturally through drills, not as a separate "
                "module. Check if grammar drills are included in standard sessions.",
                "Verify grammar integration in scheduler drill selection.",
                "Grammar adoption reflects curriculum integration depth.",
                ["mandarin/scheduler.py", "mandarin/drills/"],
            ))

        # ── Media shelf ──
        media_users = _safe_scalar(conn, """
            SELECT COUNT(DISTINCT user_id) FROM review_event
            WHERE drill_type = 'media_comprehension'
              AND reviewed_at >= datetime('now', '-30 days')
        """, default=0)
        media_adoption = round(media_users / max(1, active_users) * 100, 1)

        # Media is a delighter — low adoption is expected but track it
        if media_adoption > 0:
            findings.append(_finding(
                "strategic", "low",
                f"Media shelf adoption: {media_adoption}% of active users",
                f"{media_users} active users engaged with media comprehension. "
                f"Media is a Kano 'delighter' — low adoption is expected. "
                f"Track whether media users have higher retention.",
                "Cross-reference media users with D30 retention to validate "
                "delighter hypothesis.",
                "Compare retention of media users vs non-media users.",
                "Media shelf: delighter feature tracking.",
                ["mandarin/media.py"],
            ))

        # ── Portfolio balance (BCG matrix for modalities) ──
        modalities = {
            "core_drills": active_users,  # Everyone does core drills
            "reading": reading_users,
            "listening": listening_users,
            "conversation": conv_users,
            "grammar": grammar_users,
            "media": media_users,
        }

        # Check for modality imbalance
        non_core = {k: v for k, v in modalities.items() if k != "core_drills"}
        if non_core and active_users >= 5:
            max_mod = max(non_core.values())
            min_mod = min(non_core.values())
            if max_mod > 0 and min_mod == 0:
                zero_mods = [k for k, v in non_core.items() if v == 0]
                findings.append(_finding(
                    "strategic", "medium",
                    f"Modality gap: zero adoption for {', '.join(zero_mods)}",
                    f"Active users engage with some non-core modalities but have "
                    f"zero engagement with: {', '.join(zero_mods)}. DOCTRINE §4 "
                    f"requires modality integration — 'a word learned through "
                    f"reading should appear in a listening drill within 3 sessions.'",
                    f"Investigate why {', '.join(zero_mods)} have zero adoption. "
                    f"Check content availability, feature gating, and scheduler allocation.",
                    f"Audit content availability and scheduler for {', '.join(zero_mods)}.",
                    "Modality gaps undermine the integrated learning experience.",
                    ["mandarin/scheduler.py", "mandarin/tier_gate.py"],
                ))

    except Exception as e:
        logger.debug("Modality health analyzer failed: %s", e)

    return findings


ANALYZERS = [
    _analyze_nps_proxy,
    _analyze_ces_proxy,
    _analyze_customer_journey,
    _analyze_brand_health,
    _analyze_jtbd_coverage,
    _analyze_kano_classification,
    _analyze_content_roi,
    _analyze_modality_health,
]
