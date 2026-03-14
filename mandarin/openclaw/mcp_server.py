"""MCP Server — Aelu's learner model as a first-class MCP resource.

This is the inversion: not Aelu consuming MCP servers, but Aelu being one.
Any MCP-speaking tool can now query Aelu's learner model — from a tutor's
scheduling software to a university department head's AI assistant.

Tool categories:
1. Learner Model (read-only) — mastery, progress, errors, proficiency
2. Content & Curriculum — grammar, vocabulary, reading, listening
3. Session & Scheduling — due items, recommendations, commitment
4. Admin Operations — review queue, audit, content generation
5. Institutional — class progress, student summaries, engagement
6. Content Gap Analysis — corpus coverage, recommendations

Security: No arbitrary SQL. Each tool is scoped to specific data.
Write operations limited to review approve/reject.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False
    FastMCP = None
    logger.debug("mcp package not installed — Aelu MCP server disabled")


def create_mcp_server():
    """Create and configure the Aelu MCP server.

    Returns a FastMCP instance with all tools registered.
    Run with: mcp.run() for stdio transport.
    """
    if not _HAS_MCP:
        raise ImportError("mcp package required: pip install mcp")

    mcp = FastMCP("aelu")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. LEARNER MODEL — the core value proposition
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @mcp.tool()
    def get_learner_profile(user_id: int) -> str:
        """Full learner profile: levels, confidence, targets, engagement.

        This is the central snapshot of who this learner is. Use it to
        understand their current state before giving advice or planning.
        """
        from .. import db
        with db.connection() as conn:
            profile = conn.execute("""
                SELECT * FROM learner_profile WHERE user_id = ?
            """, (user_id,)).fetchone()

            if not profile:
                return json.dumps({"error": "No learner profile found"})

            # Safe extraction with fallbacks for optional columns
            result = {"user_id": user_id}
            for key in profile.keys():
                try:
                    result[key] = profile[key]
                except Exception:
                    pass

            return json.dumps(result)

    @mcp.tool()
    def get_mastery_overview(user_id: int) -> str:
        """Per-HSK-level mastery breakdown: items seen, accuracy, stages.

        Shows where the learner is strong and where they need work,
        broken down by HSK level. Essential for any progress question.
        """
        from .. import db
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT ci.hsk_level,
                       COUNT(DISTINCT p.content_item_id) as items_seen,
                       SUM(p.total_attempts) as total_attempts,
                       SUM(p.total_correct) as total_correct,
                       SUM(CASE WHEN p.mastery_stage = 'durable' THEN 1 ELSE 0 END) as durable,
                       SUM(CASE WHEN p.mastery_stage = 'stable' THEN 1 ELSE 0 END) as stable,
                       SUM(CASE WHEN p.mastery_stage = 'stabilizing' THEN 1 ELSE 0 END) as stabilizing,
                       SUM(CASE WHEN p.mastery_stage = 'passed_once' THEN 1 ELSE 0 END) as passed_once,
                       SUM(CASE WHEN p.mastery_stage = 'unseen' THEN 1 ELSE 0 END) as unseen
                FROM progress p
                JOIN content_item ci ON ci.id = p.content_item_id
                WHERE p.user_id = ?
                GROUP BY ci.hsk_level
                ORDER BY ci.hsk_level
            """, (user_id,)).fetchall()

            # Total items per HSK level
            totals = conn.execute("""
                SELECT hsk_level, COUNT(*) as cnt
                FROM content_item WHERE review_status = 'approved'
                GROUP BY hsk_level
            """).fetchall()
            total_map = {r["hsk_level"]: r["cnt"] for r in totals}

            levels = {}
            for r in rows:
                lvl = r["hsk_level"]
                attempts = r["total_attempts"] or 0
                correct = r["total_correct"] or 0
                levels[str(lvl)] = {
                    "items_seen": r["items_seen"],
                    "total_in_corpus": total_map.get(lvl, 0),
                    "accuracy": round(correct / max(attempts, 1), 3),
                    "durable": r["durable"] or 0,
                    "stable": r["stable"] or 0,
                    "stabilizing": r["stabilizing"] or 0,
                    "passed_once": r["passed_once"] or 0,
                    "unseen": r["unseen"] or 0,
                }

            return json.dumps({"user_id": user_id, "levels": levels})

    @mcp.tool()
    def get_session_history(user_id: int, limit: int = 20) -> str:
        """Recent session history with duration, accuracy, and outcomes.

        Use this to understand study patterns: when they study, how long,
        how accurate, whether they complete sessions or exit early.
        """
        from .. import db
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT started_at, ended_at, duration_seconds,
                       session_type, items_planned, items_completed,
                       items_correct, session_outcome, early_exit,
                       client_platform
                FROM session_log
                WHERE user_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            """, (user_id, min(limit, 50))).fetchall()

            sessions = []
            for r in rows:
                completed = r["items_completed"] or 0
                correct = r["items_correct"] or 0
                sessions.append({
                    "date": r["started_at"],
                    "duration_seconds": r["duration_seconds"],
                    "type": r["session_type"],
                    "items_completed": completed,
                    "accuracy": round(correct / max(completed, 1), 3),
                    "outcome": r["session_outcome"],
                    "early_exit": bool(r["early_exit"]),
                    "platform": r["client_platform"],
                })

            return json.dumps({"user_id": user_id, "sessions": sessions})

    @mcp.tool()
    def get_error_analysis(user_id: int, days: int = 7) -> str:
        """Error patterns, interference pairs, and grammar gaps.

        The most diagnostic tool: shows exactly what the learner
        struggles with, which items confuse each other, and which
        grammar patterns are weak.
        """
        from .. import db
        with db.connection() as conn:
            # Error type distribution
            errors = conn.execute("""
                SELECT el.error_type, COUNT(*) as cnt
                FROM error_log el
                WHERE el.user_id = ?
                AND el.created_at >= datetime('now', ? || ' days')
                GROUP BY el.error_type
                ORDER BY cnt DESC
            """, (user_id, f"-{days}")).fetchall()

            # Top struggling items
            items = conn.execute("""
                SELECT ci.hanzi, ci.english, ci.pinyin, el.error_type,
                       COUNT(*) as cnt
                FROM error_log el
                JOIN content_item ci ON ci.id = el.content_item_id
                WHERE el.user_id = ?
                AND el.created_at >= datetime('now', ? || ' days')
                GROUP BY ci.id, el.error_type
                ORDER BY cnt DESC
                LIMIT 10
            """, (user_id, f"-{days}")).fetchall()

            # Grammar gaps
            grammar = conn.execute("""
                SELECT gp.name, gp.hsk_level,
                       AVG(CASE WHEN re.correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy,
                       COUNT(*) as attempts
                FROM grammar_point gp
                JOIN content_grammar cg ON cg.grammar_point_id = gp.id
                JOIN review_event re ON re.content_item_id = cg.content_item_id
                WHERE re.user_id = ?
                AND re.created_at >= datetime('now', ? || ' days')
                GROUP BY gp.id
                HAVING accuracy < 0.7
                ORDER BY accuracy ASC
                LIMIT 10
            """, (user_id, f"-{days}")).fetchall()

            # Interference pairs
            pairs = []
            try:
                pair_rows = conn.execute("""
                    SELECT ci_a.hanzi as hanzi_a, ci_b.hanzi as hanzi_b,
                           ip.strength, ip.detected_by
                    FROM interference_pairs ip
                    JOIN content_item ci_a ON ci_a.id = ip.item_a_id
                    JOIN content_item ci_b ON ci_b.id = ip.item_b_id
                    WHERE ip.strength IN ('high', 'medium')
                    ORDER BY CASE ip.strength WHEN 'high' THEN 0 ELSE 1 END
                    LIMIT 10
                """).fetchall()
                pairs = [
                    {"a": p["hanzi_a"], "b": p["hanzi_b"],
                     "strength": p["strength"], "source": p["detected_by"]}
                    for p in pair_rows
                ]
            except Exception:
                pass

            return json.dumps({
                "user_id": user_id,
                "period_days": days,
                "error_distribution": {e["error_type"]: e["cnt"] for e in errors},
                "struggling_items": [
                    {"hanzi": i["hanzi"], "english": i["english"],
                     "pinyin": i["pinyin"], "error_type": i["error_type"],
                     "count": i["cnt"]}
                    for i in items
                ],
                "grammar_gaps": [
                    {"name": g["name"], "hsk_level": g["hsk_level"],
                     "accuracy": round(g["accuracy"], 3), "attempts": g["attempts"]}
                    for g in grammar
                ],
                "interference_pairs": pairs,
            })

    @mcp.tool()
    def get_speaking_progress(user_id: int) -> str:
        """Speaking/tone accuracy trends from audio recordings.

        Shows tone grading results over time — which tones are strong,
        which need work, overall speaking trajectory.
        """
        from .. import db
        with db.connection() as conn:
            # Recent recordings with scores
            recordings = conn.execute("""
                SELECT ar.content_item_id, ci.hanzi, ci.pinyin,
                       ar.overall_score, ar.tone_scores_json
                FROM audio_recording ar
                JOIN content_item ci ON ci.id = ar.content_item_id
                WHERE ar.user_id = ?
                ORDER BY ar.id DESC
                LIMIT 20
            """, (user_id,)).fetchall()

            # Aggregate tone accuracy
            tone_counts = {1: {"correct": 0, "total": 0}, 2: {"correct": 0, "total": 0},
                           3: {"correct": 0, "total": 0}, 4: {"correct": 0, "total": 0}}

            items = []
            for r in recordings:
                items.append({
                    "hanzi": r["hanzi"], "pinyin": r["pinyin"],
                    "score": round(r["overall_score"], 3),
                })
                try:
                    syllables = json.loads(r["tone_scores_json"] or "[]")
                    for s in syllables:
                        expected = s.get("expected", 0)
                        if expected in tone_counts:
                            tone_counts[expected]["total"] += 1
                            if s.get("correct", False):
                                tone_counts[expected]["correct"] += 1
                except (json.JSONDecodeError, TypeError):
                    pass

            tone_accuracy = {}
            for tone, data in tone_counts.items():
                if data["total"] > 0:
                    tone_accuracy[str(tone)] = {
                        "accuracy": round(data["correct"] / data["total"], 3),
                        "attempts": data["total"],
                    }

            avg_score = sum(i["score"] for i in items) / max(len(items), 1)

            return json.dumps({
                "user_id": user_id,
                "recent_recordings": items[:10],
                "tone_accuracy": tone_accuracy,
                "average_score": round(avg_score, 3),
                "total_recordings": len(items),
            })

    @mcp.tool()
    def get_reading_progress(user_id: int) -> str:
        """Reading comprehension stats: passages read, scores, speed.

        Shows how the learner is progressing with reading passages,
        comprehension scores, and vocabulary lookup patterns.
        """
        from .. import db
        with db.connection() as conn:
            stats = conn.execute("""
                SELECT COUNT(*) as total,
                       AVG(comprehension_score) as avg_comp,
                       SUM(words_looked_up) as total_lookups,
                       AVG(reading_time_seconds) as avg_time
                FROM reading_progress WHERE user_id = ?
            """, (user_id,)).fetchone()

            recent = conn.execute("""
                SELECT passage_id, comprehension_score, words_looked_up,
                       reading_time_seconds, completed_at, hsk_level
                FROM reading_progress
                WHERE user_id = ?
                ORDER BY completed_at DESC
                LIMIT 10
            """, (user_id,)).fetchall()

            return json.dumps({
                "user_id": user_id,
                "total_passages": stats["total"] if stats else 0,
                "avg_comprehension": round((stats["avg_comp"] or 0), 3) if stats else 0,
                "total_words_looked_up": stats["total_lookups"] or 0 if stats else 0,
                "avg_reading_time_seconds": round(stats["avg_time"] or 0) if stats else 0,
                "recent_passages": [
                    {"passage_id": r["passage_id"],
                     "comprehension": round((r["comprehension_score"] or 0), 3),
                     "lookups": r["words_looked_up"] or 0,
                     "hsk_level": r["hsk_level"]}
                    for r in recent
                ],
            })

    @mcp.tool()
    def get_listening_progress(user_id: int) -> str:
        """Listening stats: passages completed, comprehension, by level."""
        from .. import db
        with db.connection() as conn:
            stats = conn.execute("""
                SELECT COUNT(*) as total,
                       AVG(comprehension_score) as avg_comp,
                       SUM(words_looked_up) as lookups
                FROM listening_progress WHERE user_id = ?
            """, (user_id,)).fetchone()

            by_level = conn.execute("""
                SELECT hsk_level, COUNT(*) as cnt,
                       AVG(comprehension_score) as avg_comp
                FROM listening_progress
                WHERE user_id = ?
                GROUP BY hsk_level ORDER BY hsk_level
            """, (user_id,)).fetchall()

            return json.dumps({
                "user_id": user_id,
                "total_completed": stats["total"] if stats else 0,
                "avg_comprehension": round((stats["avg_comp"] or 0), 3) if stats else 0,
                "total_lookups": stats["lookups"] or 0 if stats else 0,
                "by_level": [
                    {"hsk_level": r["hsk_level"], "completed": r["cnt"],
                     "avg_comprehension": round((r["avg_comp"] or 0), 3)}
                    for r in by_level
                ],
            })

    @mcp.tool()
    def get_vocabulary_coverage(user_id: int) -> str:
        """Known vs unknown vocabulary by HSK level.

        Shows corpus coverage: how much of each HSK level the learner
        has encountered and mastered. Critical for HSK exam readiness.
        """
        from .. import db
        with db.connection() as conn:
            # Total items per level
            totals = conn.execute("""
                SELECT hsk_level, COUNT(*) as cnt
                FROM content_item WHERE review_status = 'approved'
                GROUP BY hsk_level ORDER BY hsk_level
            """).fetchall()

            # Known items per level
            known = conn.execute("""
                SELECT ci.hsk_level,
                       COUNT(DISTINCT p.content_item_id) as known
                FROM progress p
                JOIN content_item ci ON ci.id = p.content_item_id
                WHERE p.user_id = ?
                AND p.mastery_stage IN ('passed_once', 'stabilizing', 'stable', 'durable')
                GROUP BY ci.hsk_level
            """, (user_id,)).fetchall()
            known_map = {r["hsk_level"]: r["known"] for r in known}

            levels = {}
            for r in totals:
                lvl = r["hsk_level"]
                total = r["cnt"]
                k = known_map.get(lvl, 0)
                levels[str(lvl)] = {
                    "total": total,
                    "known": k,
                    "coverage_pct": round(k / max(total, 1) * 100, 1),
                }

            return json.dumps({"user_id": user_id, "levels": levels})

    @mcp.tool()
    def get_grammar_mastery(user_id: int) -> str:
        """Per-grammar-point mastery: studied, accuracy, drill attempts.

        Shows which grammar patterns the learner has studied and how
        well they've mastered each one. Key for tutor prep.
        """
        from .. import db
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT gp.id, gp.name, gp.name_zh, gp.hsk_level,
                       gp.category,
                       gpr.mastery_score, gpr.drill_attempts,
                       gpr.drill_correct, gpr.studied_at
                FROM grammar_point gp
                LEFT JOIN grammar_progress gpr
                    ON gp.id = gpr.grammar_point_id AND gpr.user_id = ?
                ORDER BY gp.hsk_level, gp.id
            """, (user_id,)).fetchall()

            points = []
            for r in rows:
                attempts = r["drill_attempts"] or 0
                correct = r["drill_correct"] or 0
                points.append({
                    "id": r["id"],
                    "name": r["name"],
                    "name_zh": r["name_zh"] or "",
                    "hsk_level": r["hsk_level"],
                    "category": r["category"] or "",
                    "studied": r["studied_at"] is not None,
                    "mastery_score": round(r["mastery_score"] or 0, 3),
                    "drill_attempts": attempts,
                    "accuracy": round(correct / max(attempts, 1), 3) if attempts else 0,
                })

            studied = sum(1 for p in points if p["studied"])
            return json.dumps({
                "user_id": user_id,
                "total_points": len(points),
                "studied": studied,
                "points": points,
            })

    @mcp.tool()
    def search_vocabulary(query: str, limit: int = 10) -> str:
        """Search vocabulary by hanzi, pinyin, or English meaning.

        Use this when someone asks about a specific word or wants
        to find items matching a pattern.
        """
        from .. import db
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT id, hanzi, pinyin, english, hsk_level, item_type
                FROM content_item
                WHERE review_status = 'approved'
                AND (hanzi LIKE ? OR pinyin LIKE ? OR english LIKE ?)
                ORDER BY hsk_level ASC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%",
                  min(limit, 50))).fetchall()

            return json.dumps({
                "query": query,
                "results": [
                    {"id": r["id"], "hanzi": r["hanzi"], "pinyin": r["pinyin"],
                     "english": r["english"], "hsk_level": r["hsk_level"],
                     "type": r["item_type"]}
                    for r in rows
                ],
            })

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. SESSION & SCHEDULING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @mcp.tool()
    def get_due_items(user_id: int) -> str:
        """Count of due items, top 3 struggling items, estimated session time."""
        from .. import db
        with db.connection() as conn:
            due = conn.execute("""
                SELECT COUNT(*) as cnt FROM progress
                WHERE user_id = ? AND next_review_date <= date('now')
            """, (user_id,)).fetchone()
            due_count = due["cnt"] if due else 0

            struggling = conn.execute("""
                SELECT ci.hanzi, ci.english, p.total_correct, p.total_attempts
                FROM progress p
                JOIN content_item ci ON ci.id = p.content_item_id
                WHERE p.user_id = ? AND p.total_attempts > 0
                ORDER BY CAST(p.total_correct AS REAL) / p.total_attempts ASC
                LIMIT 3
            """, (user_id,)).fetchall()

            est_minutes = max(5, (min(due_count, 20) * 15) // 60)

            return json.dumps({
                "due_count": due_count,
                "struggling_items": [
                    {"hanzi": s["hanzi"], "english": s["english"],
                     "accuracy": round(s["total_correct"] / max(1, s["total_attempts"]), 2)}
                    for s in struggling
                ],
                "estimated_minutes": est_minutes,
            })

    @mcp.tool()
    def get_schedule_recommendation(user_id: int) -> str:
        """What should this learner study next? Returns prioritized recommendations.

        Considers: due items, weak areas, grammar gaps, modality balance.
        This is the answer to "what should I focus on this week?"
        """
        from .. import db
        with db.connection() as conn:
            recommendations = []

            # Due items needing review
            due = conn.execute("""
                SELECT COUNT(*) as cnt FROM progress
                WHERE user_id = ? AND next_review_date <= date('now')
            """, (user_id,)).fetchone()
            due_count = due["cnt"] if due else 0

            if due_count > 0:
                recommendations.append({
                    "priority": 1,
                    "action": "review",
                    "detail": f"{due_count} items due for review",
                    "estimated_minutes": max(5, (min(due_count, 20) * 15) // 60),
                })

            # Weak grammar points
            grammar = conn.execute("""
                SELECT gp.name, gp.hsk_level,
                       COALESCE(gpr.mastery_score, 0) as score
                FROM grammar_point gp
                LEFT JOIN grammar_progress gpr
                    ON gp.id = gpr.grammar_point_id AND gpr.user_id = ?
                WHERE COALESCE(gpr.mastery_score, 0) < 0.5
                ORDER BY score ASC
                LIMIT 3
            """, (user_id,)).fetchall()

            if grammar:
                recommendations.append({
                    "priority": 2,
                    "action": "grammar_practice",
                    "detail": f"Weak grammar: {', '.join(g['name'] for g in grammar)}",
                    "grammar_points": [
                        {"name": g["name"], "hsk_level": g["hsk_level"],
                         "mastery": round(g["score"], 2)}
                        for g in grammar
                    ],
                })

            # Active error patterns
            try:
                active_errors = conn.execute("""
                    SELECT COUNT(*) as cnt FROM error_focus
                    WHERE user_id = ? AND resolved = 0
                """, (user_id,)).fetchone()
                if active_errors and active_errors["cnt"] > 3:
                    recommendations.append({
                        "priority": 2,
                        "action": "error_focus",
                        "detail": f"{active_errors['cnt']} active error patterns — targeted practice recommended",
                    })
            except Exception:
                pass

            # Modality balance check
            modalities = conn.execute("""
                SELECT modality, COUNT(*) as cnt
                FROM review_event
                WHERE user_id = ? AND created_at >= datetime('now', '-7 days')
                GROUP BY modality
            """, (user_id,)).fetchall()
            mod_map = {r["modality"]: r["cnt"] for r in modalities}

            if not mod_map.get("speaking"):
                recommendations.append({
                    "priority": 3,
                    "action": "speaking_practice",
                    "detail": "No speaking practice in the last 7 days",
                })
            if not mod_map.get("listening"):
                recommendations.append({
                    "priority": 3,
                    "action": "listening_practice",
                    "detail": "No listening practice in the last 7 days",
                })

            return json.dumps({
                "user_id": user_id,
                "recommendations": sorted(recommendations, key=lambda r: r["priority"]),
            })

    @mcp.tool()
    def get_commitment_status(user_id: int) -> str:
        """Weekly goal progress (sessions completed vs committed)."""
        from .. import db
        with db.connection() as conn:
            profile = conn.execute(
                "SELECT target_sessions_per_week FROM learner_profile WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            target = profile["target_sessions_per_week"] if profile else 5

            completed = conn.execute("""
                SELECT COUNT(*) as cnt FROM session_log
                WHERE user_id = ? AND session_outcome = 'completed'
                AND started_at >= datetime('now', 'weekday 0', '-7 days')
            """, (user_id,)).fetchone()
            done = completed["cnt"] if completed else 0

            return json.dumps({
                "target": target,
                "completed": done,
                "remaining": max(0, target - done),
                "on_track": done >= target * 0.7,
            })

    @mcp.tool()
    def get_streak_status(user_id: int) -> str:
        """Current streak, freezes available."""
        from .. import db
        with db.connection() as conn:
            user = conn.execute(
                "SELECT streak_days, streak_freezes_available FROM user WHERE id = ?",
                (user_id,),
            ).fetchone()

            if not user:
                return json.dumps({"error": "user not found"})

            streak = user["streak_days"] if "streak_days" in user.keys() else 0
            freezes = user["streak_freezes_available"] if "streak_freezes_available" in user.keys() else 0

            return json.dumps({
                "streak_days": streak,
                "freezes_available": freezes,
            })

    @mcp.tool()
    def queue_session(user_id: int, minutes: int = 10) -> str:
        """Plan a session of given length, return drill count."""
        drill_count = max(5, min(minutes * 4, 40))
        return json.dumps({
            "user_id": user_id,
            "minutes": minutes,
            "estimated_drills": drill_count,
            "message": f"Session planned: ~{drill_count} drills in {minutes} minutes",
        })

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. ADMIN OPERATIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @mcp.tool()
    def get_review_queue_summary() -> str:
        """Count of pending items by gap_type, oldest pending age."""
        from .. import db
        with db.connection() as conn:
            rows = conn.execute("""
                SELECT gap_type, COUNT(*) as cnt,
                       MIN(created_at) as oldest
                FROM content_generation_queue
                WHERE status = 'pending'
                GROUP BY gap_type
            """).fetchall()

            return json.dumps({
                "pending_by_type": {r["gap_type"]: r["cnt"] for r in rows},
                "total_pending": sum(r["cnt"] for r in rows),
                "oldest_pending": rows[0]["oldest"] if rows else None,
            })

    @mcp.tool()
    def get_latest_audit_summary() -> str:
        """Latest audit grade, finding count, findings requiring human action."""
        from .. import db
        with db.connection() as conn:
            audit = conn.execute("""
                SELECT grade, score, findings_json, created_at
                FROM product_audit
                ORDER BY created_at DESC LIMIT 1
            """).fetchone()

            if not audit:
                return json.dumps({"status": "no_audits"})

            findings = json.loads(audit["findings_json"] or "[]") if audit["findings_json"] else []
            human_action = [f for f in findings if f.get("severity") in ("high", "critical")]

            return json.dumps({
                "grade": audit["grade"],
                "score": audit["score"],
                "total_findings": len(findings),
                "human_action_required": len(human_action),
                "top_findings": [
                    {"title": f["title"], "severity": f["severity"]}
                    for f in human_action[:5]
                ],
                "audit_date": audit["created_at"],
            })

    @mcp.tool()
    def get_learner_briefing(user_id: int, focus: str = "general") -> str:
        """Generate tutor prep briefing: errors, grammar gaps, proficiency."""
        from .. import db
        with db.connection() as conn:
            errors = conn.execute("""
                SELECT ci.hanzi, ci.english, el.error_type, el.modality,
                       COUNT(*) as count
                FROM error_log el
                JOIN content_item ci ON ci.id = el.content_item_id
                WHERE el.created_at >= datetime('now', '-7 days')
                GROUP BY ci.hanzi, el.error_type
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()

            grammar = conn.execute("""
                SELECT gp.name, gp.hsk_level,
                       AVG(CASE WHEN re.correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy
                FROM grammar_point gp
                JOIN content_grammar cg ON cg.grammar_point_id = gp.id
                JOIN review_event re ON re.content_item_id = cg.content_item_id
                WHERE re.user_id = ? AND re.created_at >= datetime('now', '-30 days')
                GROUP BY gp.id
                HAVING accuracy < 0.7
                ORDER BY accuracy
                LIMIT 5
            """, (user_id,)).fetchall()

            proficiency = None
            try:
                proficiency = conn.execute(
                    "SELECT * FROM learner_proficiency_zones WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
            except Exception:
                pass

            return json.dumps({
                "focus": focus,
                "recent_errors": [
                    {"hanzi": e["hanzi"], "type": e["error_type"],
                     "modality": e["modality"], "count": e["count"]}
                    for e in errors
                ],
                "grammar_gaps": [
                    {"name": g["name"], "hsk_level": g["hsk_level"],
                     "accuracy": round(g["accuracy"], 2)}
                    for g in grammar
                ],
                "proficiency": {
                    "composite_hsk": proficiency["composite_hsk_estimate"]
                    if proficiency else None,
                    "vocab_hsk": proficiency["vocab_hsk_estimate"]
                    if proficiency else None,
                } if proficiency else None,
            })

    @mcp.tool()
    def approve_review_item(item_id: int) -> str:
        """Approve a content generation queue item."""
        from .. import db
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with db.connection() as conn:
            result = conn.execute("""
                UPDATE content_generation_queue
                SET status = 'approved', reviewed_at = ?
                WHERE id = ? AND status = 'pending'
            """, (now, item_id))
            conn.commit()
            if result.rowcount > 0:
                return json.dumps({"status": "approved", "item_id": item_id})
            return json.dumps({"status": "error", "reason": "item not found or not pending"})

    @mcp.tool()
    def reject_review_item(item_id: int, reason: str = "") -> str:
        """Reject a content generation queue item with reason."""
        from .. import db
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with db.connection() as conn:
            result = conn.execute("""
                UPDATE content_generation_queue
                SET status = 'rejected', reviewer_note = ?, reviewed_at = ?
                WHERE id = ? AND status = 'pending'
            """, (reason, now, item_id))
            conn.commit()
            if result.rowcount > 0:
                return json.dumps({"status": "rejected", "item_id": item_id})
            return json.dumps({"status": "error", "reason": "item not found or not pending"})

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. INSTITUTIONAL — department heads, teachers, class views
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @mcp.tool()
    def get_class_progress(class_id: int) -> str:
        """Aggregate student progress for a class.

        For department heads and teachers: "how are my students doing?"
        Returns per-student summary without exposing individual errors.
        """
        from .. import db
        with db.connection() as conn:
            # Get class members
            students = conn.execute("""
                SELECT cm.user_id, u.email, u.display_name
                FROM classroom_member cm
                JOIN user u ON u.id = cm.user_id
                WHERE cm.classroom_id = ? AND cm.role = 'student'
            """, (class_id,)).fetchall()

            summaries = []
            for s in students:
                uid = s["user_id"]
                # Session count this week
                sessions = conn.execute("""
                    SELECT COUNT(*) as cnt FROM session_log
                    WHERE user_id = ? AND session_outcome = 'completed'
                    AND started_at >= datetime('now', '-7 days')
                """, (uid,)).fetchone()

                # Overall accuracy this week
                accuracy = conn.execute("""
                    SELECT AVG(CASE WHEN correct = 1 THEN 1.0 ELSE 0.0 END) as acc
                    FROM review_event
                    WHERE user_id = ? AND created_at >= datetime('now', '-7 days')
                """, (uid,)).fetchone()

                # Active HSK level
                active = conn.execute("""
                    SELECT MAX(ci.hsk_level) as max_hsk
                    FROM progress p
                    JOIN content_item ci ON ci.id = p.content_item_id
                    WHERE p.user_id = ? AND p.mastery_stage != 'unseen'
                """, (uid,)).fetchone()

                summaries.append({
                    "user_id": uid,
                    "name": s["display_name"] or s["email"],
                    "sessions_this_week": sessions["cnt"] if sessions else 0,
                    "accuracy_this_week": round((accuracy["acc"] or 0), 3) if accuracy else 0,
                    "active_hsk_level": active["max_hsk"] if active and active["max_hsk"] else 1,
                })

            return json.dumps({
                "class_id": class_id,
                "student_count": len(summaries),
                "students": summaries,
            })

    @mcp.tool()
    def get_engagement_metrics(user_id: int = 0) -> str:
        """Engagement metrics: retention, session frequency, churn risk.

        If user_id=0, returns aggregate platform metrics.
        Otherwise returns individual user engagement.
        """
        from .. import db
        with db.connection() as conn:
            if user_id > 0:
                # Individual user
                sessions = conn.execute("""
                    SELECT COUNT(*) as total,
                           COUNT(CASE WHEN started_at >= datetime('now', '-7 days') THEN 1 END) as week,
                           COUNT(CASE WHEN started_at >= datetime('now', '-30 days') THEN 1 END) as month
                    FROM session_log WHERE user_id = ? AND session_outcome = 'completed'
                """, (user_id,)).fetchone()

                # Early exit rate
                exits = conn.execute("""
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN early_exit = 1 THEN 1 ELSE 0 END) as early
                    FROM session_log WHERE user_id = ?
                """, (user_id,)).fetchone()

                early_rate = round((exits["early"] or 0) / max(exits["total"] or 1, 1), 3)

                return json.dumps({
                    "user_id": user_id,
                    "total_sessions": sessions["total"] if sessions else 0,
                    "sessions_this_week": sessions["week"] if sessions else 0,
                    "sessions_this_month": sessions["month"] if sessions else 0,
                    "early_exit_rate": early_rate,
                    "churn_risk": "high" if (sessions["week"] or 0) == 0 and (sessions["month"] or 0) > 0
                                  else "low" if (sessions["week"] or 0) >= 3 else "medium",
                })
            else:
                # Platform aggregate
                totals = conn.execute("""
                    SELECT COUNT(DISTINCT user_id) as users,
                           COUNT(*) as sessions,
                           COUNT(CASE WHEN started_at >= datetime('now', '-7 days') THEN 1 END) as week_sessions,
                           COUNT(DISTINCT CASE WHEN started_at >= datetime('now', '-7 days') THEN user_id END) as wau
                    FROM session_log WHERE session_outcome = 'completed'
                """).fetchone()

                return json.dumps({
                    "total_users": totals["users"] if totals else 0,
                    "total_sessions": totals["sessions"] if totals else 0,
                    "sessions_this_week": totals["week_sessions"] if totals else 0,
                    "weekly_active_users": totals["wau"] if totals else 0,
                })

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. CONTENT GAP ANALYSIS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @mcp.tool()
    def get_content_gaps() -> str:
        """Full corpus gap analysis: HSK coverage, grammar, reading, media.

        Returns actionable recommendations for what content to add.
        Use this when planning curriculum expansion or checking health.
        """
        from .. import db
        from ..ai.content_gap_detector import detect_gaps
        with db.connection() as conn:
            report = detect_gaps(conn)
        return json.dumps(report)

    @mcp.tool()
    def get_user_content_gaps(user_id: int) -> str:
        """Content gaps specific to this user's weak areas.

        Where the user struggles AND the content is thin — the highest
        leverage areas for content expansion.
        """
        from .. import db
        from ..ai.content_gap_detector import detect_user_gaps
        with db.connection() as conn:
            report = detect_user_gaps(conn, user_id)
        return json.dumps(report)

    return mcp


def main():
    """Entry point for running the MCP server via stdio."""
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
