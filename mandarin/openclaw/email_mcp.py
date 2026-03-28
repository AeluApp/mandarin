"""Email/Calendar MCP integration — teacher communication without Composio.

Replaces Composio dependency for teacher communication workflows:
- Weekly progress summaries (auto-drafted, human-approved)
- Parent/guardian progress reports
- Class engagement alerts
- Calendar scheduling for tutoring sessions

Uses Gmail and Google Calendar MCP servers when available,
falls back to SMTP for sending.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def draft_weekly_summary(conn, user_id: int) -> dict:
    """Draft a weekly progress summary email for a student.

    Returns a structured email draft with subject, body (HTML + text),
    and metadata. Does NOT send — requires human approval first.
    """
    # Gather student data
    user = conn.execute(
        "SELECT email, display_name FROM user WHERE id = ?",
        (user_id,),
    ).fetchone()

    if not user:
        return {"error": "User not found"}

    name = user["display_name"] or user["email"].split("@")[0]

    # Session stats this week
    sessions = conn.execute("""
        SELECT COUNT(*) as cnt,
               SUM(items_correct) as correct,
               SUM(items_completed) as completed,
               SUM(duration_seconds) as total_seconds
        FROM session_log
        WHERE user_id = ? AND session_outcome = 'completed'
        AND started_at >= datetime('now', '-7 days')
    """, (user_id,)).fetchone()

    session_count = sessions["cnt"] if sessions else 0
    items_correct = sessions["correct"] or 0 if sessions else 0
    items_completed = sessions["completed"] or 0 if sessions else 0
    total_minutes = round((sessions["total_seconds"] or 0) / 60) if sessions else 0
    accuracy = round(items_correct / max(items_completed, 1) * 100)

    # Streak (computed from session_log, not stored as a column)
    from mandarin.web.middleware import _compute_streak
    streak = _compute_streak(conn, user_id=user_id)

    # Grammar progress
    grammar_rows = conn.execute("""
        SELECT gp.name, gpr.mastery_score
        FROM grammar_progress gpr
        JOIN grammar_point gp ON gp.id = gpr.grammar_point_id
        WHERE gpr.user_id = ?
        ORDER BY gpr.studied_at DESC
        LIMIT 5
    """, (user_id,)).fetchall()

    grammar_items = [
        {"name": g["name"], "mastery": round((g["mastery_score"] or 0) * 100)}
        for g in grammar_rows
    ]

    # Build email
    subject = f"Aelu Weekly Progress — {name}"

    text_body = f"""Hi {name},

Here's your Mandarin learning summary for this week:

Sessions completed: {session_count}
Total study time: {total_minutes} minutes
Items practiced: {items_completed}
Accuracy: {accuracy}%
Current streak: {streak} days

"""
    if grammar_items:
        text_body += "Grammar progress:\n"
        for g in grammar_items:
            text_body += f"  - {g['name']}: {g['mastery']}% mastery\n"

    text_body += "\nKeep going — steady practice makes all the difference.\n\n— Aelu"

    html_body = f"""
<div style="font-family: 'Source Sans 3', sans-serif; max-width: 600px; margin: 0 auto; color: #2d2d2d;">
  <h2 style="color: #1a7a6d; font-family: 'Cormorant Garamond', serif;">Weekly Progress</h2>
  <p>Hi {name},</p>
  <p>Here's your Mandarin learning summary for this week:</p>
  <table style="border-collapse: collapse; width: 100%; margin: 16px 0;">
    <tr><td style="padding: 8px; border-bottom: 1px solid #e5e5e5;"><strong>Sessions</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #e5e5e5;">{session_count}</td></tr>
    <tr><td style="padding: 8px; border-bottom: 1px solid #e5e5e5;"><strong>Study time</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #e5e5e5;">{total_minutes} min</td></tr>
    <tr><td style="padding: 8px; border-bottom: 1px solid #e5e5e5;"><strong>Items practiced</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #e5e5e5;">{items_completed}</td></tr>
    <tr><td style="padding: 8px; border-bottom: 1px solid #e5e5e5;"><strong>Accuracy</strong></td>
        <td style="padding: 8px; border-bottom: 1px solid #e5e5e5;">{accuracy}%</td></tr>
    <tr><td style="padding: 8px;"><strong>Streak</strong></td>
        <td style="padding: 8px;">{streak} days</td></tr>
  </table>
  <p style="color: #666; font-size: 14px;">Keep going — steady practice makes all the difference.</p>
  <p style="color: #999; font-size: 12px;">— Aelu</p>
</div>
"""

    return {
        "status": "drafted",
        "to": user["email"],
        "subject": subject,
        "text_body": text_body,
        "html_body": html_body,
        "metadata": {
            "user_id": user_id,
            "session_count": session_count,
            "accuracy": accuracy,
            "streak": streak,
        },
    }


def draft_class_report(conn, class_id: int) -> dict:
    """Draft a class progress report for the teacher.

    Summarizes all students' progress, highlights struggling students,
    and suggests focus areas for the next week.
    """
    # Get class info
    classroom = conn.execute(
        "SELECT name, teacher_user_id FROM classroom WHERE id = ?",
        (class_id,),
    ).fetchone()

    if not classroom:
        return {"error": "Class not found"}

    teacher = conn.execute(
        "SELECT email, display_name FROM user WHERE id = ?",
        (classroom["teacher_user_id"],),
    ).fetchone()

    # Get student summaries
    students = conn.execute("""
        SELECT cs.user_id, u.display_name, u.email
        FROM classroom_student cs
        JOIN user u ON u.id = cs.user_id
        WHERE cs.classroom_id = ?
    """, (class_id,)).fetchall()

    summaries = []
    struggling = []
    for s in students:
        uid = s["user_id"]
        name = s["display_name"] or s["email"].split("@")[0]

        week = conn.execute("""
            SELECT COUNT(*) as sessions,
                   SUM(items_correct) as correct,
                   SUM(items_completed) as completed
            FROM session_log
            WHERE user_id = ? AND session_outcome = 'completed'
            AND started_at >= datetime('now', '-7 days')
        """, (uid,)).fetchone()

        sessions = week["sessions"] if week else 0
        correct = week["correct"] or 0 if week else 0
        completed = week["completed"] or 0 if week else 0
        acc = round(correct / max(completed, 1) * 100)

        summaries.append({
            "name": name,
            "sessions": sessions,
            "accuracy": acc,
            "items": completed,
        })

        if sessions == 0 or acc < 60:
            struggling.append({"name": name, "sessions": sessions, "accuracy": acc})

    teacher_name = teacher["display_name"] if teacher else "Teacher"
    class_name = classroom["name"]

    subject = f"Aelu Class Report — {class_name}"

    text_body = f"""Hi {teacher_name},

Weekly report for {class_name} ({len(summaries)} students):

"""
    for s in summaries:
        text_body += f"  {s['name']}: {s['sessions']} sessions, {s['accuracy']}% accuracy\n"

    if struggling:
        text_body += "\nNeeds attention:\n"
        for s in struggling:
            if s["sessions"] == 0:
                text_body += f"  - {s['name']}: No sessions this week\n"
            else:
                text_body += f"  - {s['name']}: {s['accuracy']}% accuracy\n"

    text_body += "\n— Aelu"

    return {
        "status": "drafted",
        "to": teacher["email"] if teacher else "",
        "subject": subject,
        "text_body": text_body,
        "metadata": {
            "class_id": class_id,
            "student_count": len(summaries),
            "struggling_count": len(struggling),
        },
    }


def send_email(
    to: str,
    subject: str,
    text_body: str,
    html_body: str = "",
) -> dict:
    """Send an email via SMTP. Requires SMTP_* env vars.

    This is the fallback when Gmail MCP is not available.
    Returns send status.
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user:
        return {
            "status": "not_sent",
            "reason": "SMTP not configured (set SMTP_HOST, SMTP_USER, SMTP_PASSWORD)",
        }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to

        msg.attach(MIMEText(text_body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to], msg.as_string())

        return {"status": "sent", "to": to}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def create_email_tools() -> list[dict]:
    """Return tool definitions for agent integration."""
    return [
        {
            "name": "draft_weekly_summary",
            "description": "Draft a weekly progress email for a student (requires approval to send)",
            "function": draft_weekly_summary,
            "parameters": {"user_id": "int"},
        },
        {
            "name": "draft_class_report",
            "description": "Draft a class progress report for the teacher",
            "function": draft_class_report,
            "parameters": {"class_id": "int"},
        },
        {
            "name": "send_email",
            "description": "Send a drafted email (requires prior approval)",
            "function": send_email,
            "parameters": {"to": "str", "subject": "str", "text_body": "str", "html_body": "str (optional)"},
            "requires_confirmation": True,
        },
    ]
