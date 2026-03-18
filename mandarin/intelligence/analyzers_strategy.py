"""Strategy framework analyzers — McKinsey/Bain/BCG consulting best practices."""
import logging
from ._base import _finding

logger = logging.getLogger(__name__)


def _analyze_tam_sam_som(conn):
    """Market sizing: TAM/SAM/SOM estimates vs current user count."""
    findings = []
    try:
        TAM = 180_000_000  # Global Mandarin learners
        SAM = 30_000_000   # English-speaking online learners
        SOM_Y1 = 3_000     # 0.01% capture rate Year 1

        user_count = conn.execute("SELECT COUNT(*) FROM user").fetchone()[0]

        if user_count < SOM_Y1 * 0.01:  # Less than 1% of Y1 SOM
            findings.append(_finding(
                "marketing", "medium",
                f"Market penetration: {user_count} users vs {SOM_Y1:,} Y1 SOM target ({user_count/max(1,SOM_Y1)*100:.2f}%)",
                f"TAM: {TAM/1e6:.0f}M global Mandarin learners. SAM: {SAM/1e6:.0f}M English-speaking online. "
                f"SOM Year 1: {SOM_Y1:,} (0.01% capture). Current: {user_count} users.",
                "Focus customer acquisition on highest-converting channels. Consider product-led growth.",
                "Analyze signup sources and double down on top-performing acquisition channel.",
                "Market sizing (TAM/SAM/SOM)",
                ["mandarin/marketing_hooks.py"],
            ))
    except Exception:
        pass
    return findings


def _analyze_three_horizons(conn):
    """Growth portfolio: H1 (core), H2 (emerging), H3 (future) balance."""
    findings = []
    try:
        # H1: Core drill types (SRS, MC, listening, reading)
        h1_drills = conn.execute("""
            SELECT COUNT(DISTINCT drill_type) FROM review_event
            WHERE drill_type IN ('mc', 'reverse_mc', 'listening', 'reading', 'tone', 'pinyin')
            AND reviewed_at >= datetime('now', '-30 days')
        """).fetchone()[0]

        # H2: Emerging (conversation, minimal_pair, sandhi_contrast, character decomposition)
        h2_drills = conn.execute("""
            SELECT COUNT(DISTINCT drill_type) FROM review_event
            WHERE drill_type IN ('dialogue', 'minimal_pair', 'sandhi_contrast', 'media_comprehension')
            AND reviewed_at >= datetime('now', '-30 days')
        """).fetchone()[0]

        # H3: Future tech (check if LangGraph, DSPy, model_selector are active)
        h3_active = 0
        for table in ['pi_model_registry', 'prescription_execution_log', 'pi_dmadv_log']:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE created_at >= datetime('now', '-30 days')").fetchone()[0]
                if count > 0:
                    h3_active += 1
            except Exception:
                pass

        total = h1_drills + h2_drills + h3_active
        if total > 0:
            h1_pct = h1_drills / total * 100
            if h1_pct > 90:
                findings.append(_finding(
                    "strategic", "low",
                    f"Three Horizons imbalance: {h1_pct:.0f}% core (H1), {100-h1_pct:.0f}% emerging+future",
                    "Over-investing in core features. McKinsey's Three Horizons recommends 70/20/10 split. "
                    "Emerging features (conversation, minimal pairs, tone sandhi) need more adoption.",
                    "Promote H2 features: add conversation blocks to more sessions, surface minimal pairs.",
                    "Increase H2 feature exposure by adjusting session block allocation weights.",
                    "Three Horizons growth portfolio",
                    ["mandarin/scheduler.py"],
                ))
    except Exception:
        pass
    return findings


def _analyze_porter_five_forces(conn):
    """Competitive intensity analysis using Porter's framework."""
    findings = []
    try:
        forces = {
            "rivalry": {"score": 8, "label": "HIGH", "detail": "Duolingo (500M users), HelloChinese, Anki, Busuu all compete in Mandarin learning"},
            "new_entrants": {"score": 6, "label": "MEDIUM", "detail": "Low barriers (web app easy), but AI/SRS moat is growing"},
            "substitutes": {"score": 7, "label": "HIGH", "detail": "YouTube, textbooks, tutors, immersion programs all substitute"},
            "buyer_power": {"score": 8, "label": "HIGH", "detail": "Free alternatives abundant; switching cost near zero"},
            "supplier_power": {"score": 2, "label": "LOW", "detail": "Open-source models, CC-CEDICT, open content; no supplier lock-in"},
        }
        avg_intensity = sum(f["score"] for f in forces.values()) / len(forces)

        findings.append(_finding(
            "competitive", "medium" if avg_intensity > 6 else "low",
            f"Porter's Five Forces: competitive intensity {avg_intensity:.1f}/10 ({('HIGH' if avg_intensity > 6 else 'MEDIUM')})",
            " | ".join(f"{k}: {v['label']} — {v['detail']}" for k, v in forces.items()),
            "Differentiate on AI intelligence and Mandarin depth (supplier power is LOW = advantage). "
            "Reduce buyer power by increasing switching costs (learning history, streaks, social features).",
            "Focus product development on features competitors can't easily replicate: AI-powered tone feedback, "
            "character decomposition, Thompson Sampling drill selection.",
            "Porter's Five Forces competitive analysis",
            ["mandarin/intelligence/analyzers_business.py"],
        ))
    except Exception:
        pass
    return findings


def _analyze_growth_share_matrix(conn):
    """BCG Growth-Share Matrix: classify drill types as Star/Cash Cow/Question Mark/Dog."""
    findings = []
    try:
        # Get drill type usage: last 30d vs prior 30d
        current = conn.execute("""
            SELECT drill_type, COUNT(*) as cnt FROM review_event
            WHERE reviewed_at >= datetime('now', '-30 days')
            GROUP BY drill_type
        """).fetchall()
        prior = conn.execute("""
            SELECT drill_type, COUNT(*) as cnt FROM review_event
            WHERE reviewed_at >= datetime('now', '-60 days') AND reviewed_at < datetime('now', '-30 days')
            GROUP BY drill_type
        """).fetchall()

        current_map = {r["drill_type"]: r["cnt"] for r in current} if current else {}
        prior_map = {r["drill_type"]: r["cnt"] for r in prior} if prior else {}
        total_current = sum(current_map.values()) or 1

        dogs = []
        stars = []
        for dt, cnt in current_map.items():
            share = cnt / total_current
            prior_cnt = prior_map.get(dt, cnt)
            growth = (cnt - prior_cnt) / max(1, prior_cnt)

            if share < 0.05 and growth < 0:
                dogs.append(dt)
            elif share > 0.15 and growth > 0.1:
                stars.append(dt)

        if len(dogs) > 3:
            findings.append(_finding(
                "pm", "low",
                f"BCG Matrix: {len(dogs)} 'Dog' drill types (low usage, declining): {', '.join(dogs[:5])}",
                f"These drill types have <5% usage share AND declining engagement: {dogs}. "
                f"Consider sunsetting or redesigning them to free up development resources.",
                "Review low-usage drill types. Sunset Dogs, invest in Stars.",
                "Analyze why these drill types are underused and either improve or remove them.",
                "BCG Growth-Share Matrix",
                ["mandarin/scheduler.py", "mandarin/drills/"],
            ))
        if stars:
            findings.append(_finding(
                "pm", "low",
                f"BCG Matrix Stars: {', '.join(stars)} — high growth + high share. Invest more.",
                f"These drill types are both popular (>15% share) and growing (>10%): {stars}.",
                "Double down on Star drill types: more content, more variants, better feedback.",
                "Create additional content and variants for high-performing drill types.",
                "BCG Growth-Share Matrix",
                ["mandarin/drills/"],
            ))
    except Exception:
        pass
    return findings


def _analyze_blue_ocean(conn):
    """Blue Ocean Strategy: value curve vs competitors."""
    findings = []
    try:
        # Score aelu vs competitors on 8 dimensions (1-10)
        aelu_scores = {
            "price": 7,            # $14.99/mo vs Duolingo $7/mo -> mid
            "ease_of_use": 5,      # Complex (44 drill types) vs Duolingo simplicity
            "content_variety": 8,  # 44 drill types, reading, listening, conversation
            "immersion": 6,        # Reading passages, but no video/TV integration
            "social_features": 2,  # Minimal (no friends, no leaderboard, no community)
            "ai_intelligence": 9,  # Thompson Sampling, FSRS, Dijkstra, LLM-powered
            "offline_support": 8,  # PWA, service worker, offline queue
            "mandarin_depth": 9,   # Tone sandhi, character decomposition, HSK 1-9
        }

        # Identify leads and lags
        leads = [k for k, v in aelu_scores.items() if v >= 8]
        lags = [k for k, v in aelu_scores.items() if v <= 4]

        if lags:
            findings.append(_finding(
                "competitive", "medium",
                f"Blue Ocean: aelu lags on {', '.join(lags)} (scores <=4/10)",
                f"Value curve analysis: aelu leads on {leads} but lags on {lags}. "
                f"Competitors like Duolingo dominate social features and ease of use.",
                f"Consider {'adding social features' if 'social_features' in lags else 'simplifying UX'} "
                f"to close competitive gap without sacrificing AI/depth advantages.",
                "Address competitive gaps identified in Blue Ocean value curve analysis.",
                "Blue Ocean Strategy value curve",
                ["mandarin/web/static/app.js"],
            ))
    except Exception:
        pass
    return findings


def _analyze_unit_economics(conn):
    """Unit economics: CAC, LTV, LTV/CAC ratio, payback period."""
    findings = []
    try:
        from ..analytics.clv import compute_ltv
        ltv_data = compute_ltv(conn)
        ltv = ltv_data.get("estimated_ltv", 0) or ltv_data.get("arpu", 0)

        # Estimate CAC from referral data
        try:
            from ..marketing_hooks import compute_viral_coefficient
            viral = compute_viral_coefficient(conn, days=90)
            total_users = viral.get("total_users", 1)
            # Rough CAC estimate: if no paid acquisition, CAC ~ $0 (organic only)
            cac = 0.0  # Will be updated when paid channels exist
        except Exception:
            cac = 0.0
            total_users = 1

        if ltv > 0 and cac > 0:
            ratio = ltv / cac
            if ratio < 3:
                findings.append(_finding(
                    "profitability", "high",
                    f"Unit economics: LTV/CAC ratio = {ratio:.1f}x (target: >3x)",
                    f"LTV: ${ltv:.2f}, CAC: ${cac:.2f}. Ratio {ratio:.1f}x is below the 3x threshold "
                    f"needed for scalable growth. Either reduce CAC or increase retention/monetization.",
                    "Improve retention to increase LTV, or reduce acquisition cost.",
                    "Optimize unit economics: increase LTV via retention improvements or reduce CAC.",
                    "Unit economics (CAC/LTV)",
                    ["mandarin/analytics/clv.py"],
                ))
        elif cac == 0 and total_users > 0:
            findings.append(_finding(
                "profitability", "low",
                f"Unit economics: CAC = $0 (organic only), LTV = ${ltv:.2f}. No paid acquisition yet.",
                "All users are organic. When paid channels are added, track CAC to maintain LTV/CAC > 3x.",
                "Prepare CAC tracking for when paid acquisition channels are activated.",
                "Set up UTM tracking and cost-per-channel logging before scaling ad spend.",
                "Unit economics preparation",
                ["mandarin/marketing_hooks.py"],
            ))
    except Exception:
        pass
    return findings


def _analyze_flywheel_health(conn):
    """Growth flywheel: content creation -> engagement -> referral -> more users."""
    findings = []
    try:
        # Content velocity: new items this week
        new_items = 0
        try:
            row = conn.execute("SELECT COUNT(*) FROM content_item WHERE created_at >= datetime('now', '-7 days')").fetchone()
            new_items = row[0] if row else 0
        except Exception:
            pass

        # Engagement: sessions per active user this week
        sessions_per_user = 0
        try:
            row = conn.execute("""
                SELECT CAST(COUNT(*) AS FLOAT) / MAX(1, COUNT(DISTINCT user_id))
                FROM session_log WHERE started_at >= datetime('now', '-7 days')
            """).fetchone()
            sessions_per_user = row[0] if row else 0
        except Exception:
            pass

        # Referral: k-factor
        k_factor = 0
        try:
            from ..marketing_hooks import compute_viral_coefficient
            viral = compute_viral_coefficient(conn, days=30)
            k_factor = viral.get("k_factor", 0)
        except Exception:
            pass

        stalled = []
        if new_items == 0:
            stalled.append("content creation (0 new items this week)")
        if sessions_per_user < 2:
            stalled.append(f"engagement ({sessions_per_user:.1f} sessions/user/week)")
        if k_factor < 0.05:
            stalled.append(f"referral (k={k_factor:.3f})")

        if stalled:
            findings.append(_finding(
                "marketing", "medium" if len(stalled) >= 2 else "low",
                f"Growth flywheel: {len(stalled)} components stalled: {'; '.join(stalled)}",
                "A healthy flywheel needs all components spinning: content creation -> user engagement -> "
                "referrals -> more users -> more content demand. Stalled components break the loop.",
                "Address stalled flywheel components to restore growth momentum.",
                "Restart stalled flywheel components: " + "; ".join(stalled),
                "Growth flywheel health",
                ["mandarin/marketing_hooks.py", "mandarin/scheduler.py"],
            ))
    except Exception:
        pass
    return findings


def _analyze_seven_s(conn):
    """McKinsey 7S alignment check across available elements."""
    findings = []
    try:
        aligned = []
        misaligned = []

        # Strategy: does a strategic thesis exist?
        try:
            thesis = conn.execute("SELECT COUNT(*) FROM pi_strategic_thesis").fetchone()[0]
            if thesis > 0:
                aligned.append("Strategy")
            else:
                misaligned.append("Strategy (no strategic thesis)")
        except Exception:
            misaligned.append("Strategy (thesis table missing)")

        # Systems: methodology coverage
        try:
            from ..intelligence.methodology_coverage import DETECTION_FUNCTIONS
            if len(DETECTION_FUNCTIONS) >= 10:
                aligned.append("Systems")
            else:
                misaligned.append("Systems (methodology coverage incomplete)")
        except Exception:
            misaligned.append("Systems (methodology coverage unavailable)")

        # Shared Values: editorial standard
        try:
            from ..intelligence.strategic_intelligence import EDITORIAL_STANDARD
            if EDITORIAL_STANDARD:
                aligned.append("Shared Values")
        except Exception:
            misaligned.append("Shared Values (editorial standard missing)")

        # Skills: model capability
        try:
            from ..settings import MODEL_SIZE_B
            if MODEL_SIZE_B >= 7:
                aligned.append("Skills (7B+ model)")
            else:
                aligned.append("Skills (limited model)")
        except Exception:
            misaligned.append("Skills (model assessment unavailable)")

        # Structure, Style, Staff -- not applicable for solo dev
        aligned.extend(["Structure (solo dev)", "Style (solo dev)", "Staff (solo dev)"])

        if misaligned:
            findings.append(_finding(
                "pm", "low",
                f"McKinsey 7S: {len(aligned)}/7 aligned, {len(misaligned)} gaps: {', '.join(misaligned)}",
                f"Aligned: {', '.join(aligned)}. Misaligned: {', '.join(misaligned)}.",
                "Address misaligned elements to improve organizational coherence.",
                "Review and fix 7S alignment gaps: " + "; ".join(misaligned),
                "McKinsey 7S organizational alignment",
                [],
            ))
    except Exception:
        pass
    return findings


ANALYZERS = [
    _analyze_tam_sam_som,
    _analyze_three_horizons,
    _analyze_porter_five_forces,
    _analyze_growth_share_matrix,
    _analyze_blue_ocean,
    _analyze_unit_economics,
    _analyze_flywheel_health,
    _analyze_seven_s,
]
