"""OpenClaw commands — pure functions wrapping MCP tools as direct Python calls.

These bypass the MCP protocol entirely — just call the underlying DB queries
from mcp_server.py tool functions. Each command returns a formatted string
suitable for sending to the user.
"""

import json
import logging
from datetime import datetime, timezone, UTC
from typing import Optional

logger = logging.getLogger(__name__)


def dispatch_intent(intent_result, conn=None) -> str:
    """Execute a classified intent and return the response text.

    Shared by all bot transports (Telegram, Signal, etc.).
    """
    from . import llm_handler
    from ..settings import BASE_URL

    intent = intent_result.intent
    args = intent_result.args

    dispatch = {
        "status": lambda: cmd_status(),
        "review": lambda: cmd_review(),
        "audit": lambda: cmd_audit(),
        "briefing": lambda: cmd_briefing(focus=args.get("focus", "general")),
        "errors": lambda: cmd_error_patterns(),
        "approve": lambda: cmd_approve(item_id=args.get("item_id", 0)),
        "reject": lambda: cmd_reject(
            item_id=args.get("item_id", 0),
            reason=args.get("reason", ""),
        ),
        "session": lambda: f"Ready to study? Open {BASE_URL} to start a session.",
        "findings": lambda: cmd_findings(),
        "approve_finding": lambda: cmd_approve_finding(
            finding_number=int(args.get("number", 0)), notes=args.get("notes", ""),
        ),
        "dismiss_finding": lambda: cmd_dismiss_finding(
            finding_number=int(args.get("number", 0)), notes=args.get("notes", ""),
        ),
        "modify_finding": lambda: cmd_modify_finding(
            finding_number=int(args.get("number", 0)),
            instruction=args.get("instruction", args.get("notes", "")),
        ),
        "help": lambda: (
            "Commands: status, review, audit, briefing, errors, findings\n"
            "Reply 'approve 1' or 'dismiss 1' after findings.\n"
            "Or just type naturally."
        ),
    }

    handler = dispatch.get(intent)
    if handler:
        try:
            return handler()
        except Exception as e:
            logger.error("Command %s failed: %s", intent, e, exc_info=True)
            return f"Error running {intent}: {str(e)[:100]}"

    # Chat / unknown — generate conversational response
    if intent_result.reply:
        return intent_result.reply
    return llm_handler.generate_chat_response(
        intent_result.args.get("original_text", ""), conn=conn,
    )


def _get_conn():
    """Get a DB connection."""
    from .. import db
    return db.connection()


def cmd_status(user_id: int = 1) -> str:
    """Comprehensive learner status: due items, streak, weekly commitment."""
    with _get_conn() as conn:
        # Due items
        due = conn.execute("""
            SELECT COUNT(*) as cnt FROM progress
            WHERE user_id = ? AND next_review_date <= date('now')
        """, (user_id,)).fetchone()
        due_count = due["cnt"] if due else 0

        # Top struggling items
        struggling = conn.execute("""
            SELECT ci.hanzi, ci.english, p.total_correct, p.total_attempts
            FROM progress p
            JOIN content_item ci ON ci.id = p.content_item_id
            WHERE p.user_id = ? AND p.total_attempts > 0
            ORDER BY CAST(p.total_correct AS REAL) / p.total_attempts ASC
            LIMIT 3
        """, (user_id,)).fetchall()

        # Streak
        try:
            user = conn.execute(
                "SELECT streak_days, streak_freezes_available FROM user WHERE id = ?",
                (user_id,),
            ).fetchone()
            streak = user["streak_days"] if user and "streak_days" in user.keys() else 0
            freezes = (user["streak_freezes_available"]
                       if user and "streak_freezes_available" in user.keys() else 0)
        except Exception:
            user, streak, freezes = None, 0, 0

        # Weekly commitment
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

        est_minutes = max(5, (min(due_count, 20) * 15) // 60)

        # Format response
        lines = [f"📊 {due_count} items due (~{est_minutes} min)"]

        if struggling:
            lines.append("")
            lines.append("Needs attention:")
            for s in struggling:
                acc = round(s["total_correct"] / max(1, s["total_attempts"]) * 100)
                lines.append(f"  • {s['hanzi']} ({s['english']}) — {acc}%")

        lines.append("")
        lines.append(f"🔥 {streak}-day streak" + (f" ({freezes} freezes)" if freezes else ""))
        lines.append(f"📅 {done}/{target} sessions this week")

        return "\n".join(lines)


def cmd_review() -> str:
    """Review queue summary."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT gap_type, COUNT(*) as cnt,
                   MIN(created_at) as oldest
            FROM content_generation_queue
            WHERE status = 'pending'
            GROUP BY gap_type
        """).fetchall()

        total = sum(r["cnt"] for r in rows)
        if total == 0:
            return "✅ Review queue is empty."

        lines = [f"📋 {total} items pending review:"]
        for r in rows:
            lines.append(f"  • {r['gap_type']}: {r['cnt']} (oldest: {r['oldest'][:10]})")

        return "\n".join(lines)


def cmd_review_items(limit: int = 5) -> list[dict]:
    """Get individual pending review items for inline review."""
    with _get_conn() as conn:
        try:
            rows = conn.execute("""
                SELECT id, gap_type, created_at
                FROM content_generation_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []


def cmd_approve(item_id: int) -> str:
    """Approve a content generation queue item."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    with _get_conn() as conn:
        result = conn.execute("""
            UPDATE content_generation_queue
            SET status = 'approved', reviewed_at = ?
            WHERE id = ? AND status = 'pending'
        """, (now, item_id))
        conn.commit()
        if result.rowcount > 0:
            return f"✓ Item {item_id} approved."
        return f"⚠ Item {item_id} not found or already reviewed."


def cmd_reject(item_id: int, reason: str = "") -> str:
    """Reject a content generation queue item."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    with _get_conn() as conn:
        result = conn.execute("""
            UPDATE content_generation_queue
            SET status = 'rejected', reviewer_note = ?, reviewed_at = ?
            WHERE id = ? AND status = 'pending'
        """, (reason, now, item_id))
        conn.commit()
        if result.rowcount > 0:
            return f"✓ Item {item_id} rejected." + (f" Reason: {reason}" if reason else "")
        return f"⚠ Item {item_id} not found or already reviewed."


def cmd_audit() -> str:
    """Latest audit summary."""
    with _get_conn() as conn:
        try:
            audit = conn.execute("""
                SELECT grade, score, findings_json, created_at
                FROM product_audit
                ORDER BY created_at DESC LIMIT 1
            """).fetchone()
        except Exception:
            return "No audits recorded yet."

        if not audit:
            return "No audits recorded yet."

        findings = json.loads(audit["findings_json"] or "[]") if audit["findings_json"] else []
        human_action = [f for f in findings if f.get("severity") in ("high", "critical")]

        lines = [
            f"🔍 Latest audit: {audit['grade']} ({audit['score']})",
            f"   Date: {audit['created_at'][:10]}",
            f"   Findings: {len(findings)} total, {len(human_action)} need action",
        ]
        if human_action:
            lines.append("")
            lines.append("Action required:")
            for f in human_action[:5]:
                lines.append(f"  • [{f['severity'].upper()}] {f['title']}")

        return "\n".join(lines)


def cmd_briefing(user_id: int = 1, focus: str = "general") -> str:
    """Learner/tutor prep briefing."""
    with _get_conn() as conn:
        # Recent errors
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

        # Grammar gaps
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

        lines = [f"📋 Briefing ({focus})"]
        if errors:
            lines.append("")
            lines.append("Recent errors:")
            for e in errors[:5]:
                lines.append(f"  • {e['hanzi']} ({e['english']}) — {e['error_type']} via {e['modality']} (×{e['count']})")

        if grammar:
            lines.append("")
            lines.append("Grammar gaps:")
            for g in grammar:
                lines.append(f"  • {g['name']} (HSK {g['hsk_level']}) — {round(g['accuracy'] * 100)}%")

        if not errors and not grammar:
            lines.append("No significant issues in the last 7 days.")

        return "\n".join(lines)


def cmd_error_patterns() -> str:
    """Analyze recent error shape patterns."""
    with _get_conn() as conn:
        lines = []

        # Top error shapes
        try:
            shapes = conn.execute("""
                SELECT ci.hanzi, ci.english, es.error_type, es.error_cause,
                       es.occurrence_count, es.status
                FROM error_shape_summary es
                JOIN content_item ci ON ci.id = es.content_item_id
                WHERE es.status = 'active'
                ORDER BY es.occurrence_count DESC
                LIMIT 10
            """).fetchall()

            if shapes:
                lines.append("Active error patterns:")
                for s in shapes:
                    cause = s["error_cause"] or s["error_type"]
                    lines.append(f"  • {s['hanzi']} ({s['english']}) — {cause} (x{s['occurrence_count']})")
        except Exception:
            pass

        # Interference pairs
        try:
            pairs = conn.execute("""
                SELECT ci_a.hanzi as hanzi_a, ci_b.hanzi as hanzi_b,
                       ip.strength, ip.detected_by
                FROM interference_pairs ip
                JOIN content_item ci_a ON ci_a.id = ip.item_a_id
                JOIN content_item ci_b ON ci_b.id = ip.item_b_id
                WHERE ip.strength IN ('high', 'medium')
                ORDER BY CASE ip.strength WHEN 'high' THEN 0 ELSE 1 END
                LIMIT 5
            """).fetchall()

            if pairs:
                if lines:
                    lines.append("")
                lines.append("Interference pairs:")
                for p in pairs:
                    lines.append(f"  • {p['hanzi_a']} <> {p['hanzi_b']} ({p['strength']}, {p['detected_by']})")
        except Exception:
            pass

        return "\n".join(lines) if lines else "No active error patterns."


def cmd_findings(user_id: int = 1) -> str:
    """Show open findings that need your review, in plain English."""
    with _get_conn() as conn:
        findings = conn.execute("""
            SELECT id, severity, title, analysis, status
            FROM pi_finding
            WHERE status NOT IN ('resolved', 'rejected')
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 WHEN 'low' THEN 3
                END,
                updated_at DESC
            LIMIT 10
        """).fetchall()

        if not findings:
            return "No findings need your attention right now. Everything looks good."

        lines = [f"{len(findings)} finding(s) need your review:\n"]
        for i, f in enumerate(findings, 1):
            severity_icon = {"critical": "!!!", "high": "!!", "medium": "!", "low": ""}.get(f["severity"], "")
            lines.append(f"[{i}] {severity_icon} {f['title']}")
            # Show the plain-English analysis
            analysis = f["analysis"] or ""
            for aline in analysis.split("\n"):
                aline = aline.strip()
                if aline and aline.startswith(("WHAT", "URGENCY", "DETAILS")):
                    lines.append(f"    {aline}")
            lines.append(f"    → 'approve {i}' / 'dismiss {i}' / 'modify {i} do this instead...'")
            lines.append("")

        return "\n".join(lines)


def cmd_approve_finding(finding_number: int, notes: str = "", user_id: int = 1) -> str:
    """Approve a finding fix (mark as resolved)."""
    return _transition_finding(finding_number, "resolved", notes)


def cmd_dismiss_finding(finding_number: int, notes: str = "", user_id: int = 1) -> str:
    """Dismiss a finding (mark as rejected)."""
    return _transition_finding(finding_number, "rejected", notes)


def cmd_modify_finding(finding_number: int, instruction: str, user_id: int = 1) -> str:
    """Modify a finding — add your own instruction for what should be done instead.

    The finding stays open with your instruction attached, so the next
    self-healing cycle (or Claude Code session) picks it up and acts on it.
    """
    with _get_conn() as conn:
        findings = conn.execute("""
            SELECT id, title FROM pi_finding
            WHERE status NOT IN ('resolved', 'rejected')
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 WHEN 'low' THEN 3
                END,
                updated_at DESC
            LIMIT 10
        """).fetchall()

        if finding_number < 1 or finding_number > len(findings):
            return f"No finding #{finding_number}. Use 'findings' to see the list."

        finding = findings[finding_number - 1]

        try:
            conn.execute("""
                UPDATE pi_finding
                SET status = 'owner_modified',
                    analysis = analysis || ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (f"\n\nOWNER INSTRUCTION: {instruction}", finding["id"]))
            conn.commit()
            return (
                f"Got it. Updated: {finding['title']}\n"
                f"Your instruction: {instruction}\n"
                f"This will be picked up on the next self-healing run."
            )
        except Exception as e:
            return f"Failed to update: {e}"


def _transition_finding(finding_number: int, status: str, notes: str = "") -> str:
    """Transition the Nth open finding to the given status."""
    with _get_conn() as conn:
        findings = conn.execute("""
            SELECT id, title FROM pi_finding
            WHERE status NOT IN ('resolved', 'rejected')
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2 WHEN 'low' THEN 3
                END,
                updated_at DESC
            LIMIT 10
        """).fetchall()

        if finding_number < 1 or finding_number > len(findings):
            return f"No finding #{finding_number}. Use 'findings' to see the list."

        finding = findings[finding_number - 1]
        action = "Approved" if status == "resolved" else "Dismissed"

        try:
            conn.execute("""
                UPDATE pi_finding SET status = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (status, finding["id"]))
            if notes:
                conn.execute("""
                    UPDATE pi_finding SET analysis = analysis || ? WHERE id = ?
                """, (f"\n\nOWNER NOTE: {notes}", finding["id"]))
            conn.commit()
            return f"{action}: {finding['title']}"
        except Exception as e:
            return f"Failed to update finding: {e}"
