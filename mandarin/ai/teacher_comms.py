"""Teacher Communication Drafts (Doc 23 B-04).

Human-approved email draft queue for teacher outreach.
All drafts require explicit human approval before sending — no automated sending.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone, UTC
from typing import Optional

logger = logging.getLogger(__name__)


def draft_teacher_outreach(
    conn: sqlite3.Connection,
    lead_id: int,
    purpose: str,
) -> int | None:
    """Generate a personalized email draft for a teacher lead.

    Returns draft ID or None on failure.
    """
    from .ollama_client import generate as ollama_generate, is_ollama_available
    from .genai_layer import _parse_llm_json

    lead = conn.execute(
        "SELECT * FROM teacher_lead WHERE id = ?", (lead_id,)
    ).fetchone()
    if not lead:
        return None

    if not is_ollama_available():
        # Create a template-based draft without LLM
        return _create_template_draft(conn, lead, purpose)

    prompt = (
        f"Draft an email to a Mandarin teacher for the following purpose: {purpose}\n\n"
        f"Teacher info:\n"
        f"Name: {lead['name']}\n"
        f"Platform: {lead['platform']}\n"
        f"Rating: {lead['platform_rating'] or 'N/A'}\n"
        f"Language pair: {lead['language_pair']}\n"
        f"Style: {lead['teaching_style_tags'] or 'N/A'}\n\n"
        f"Aelu is a Mandarin learning app using spaced repetition and adaptive technology.\n"
        f"Tone: professional, warm, respectful. Not salesy.\n\n"
        f"Return JSON with: subject, body_text (plain text email body)"
    )

    resp = ollama_generate(
        prompt=prompt,
        system="You are drafting professional emails for an educational technology company. "
               "Write with warmth and respect. Keep it concise. Return JSON.",
        temperature=0.5,
        conn=conn,
        task_type="teacher_comms",
    )

    if not resp.success:
        return _create_template_draft(conn, lead, purpose)

    parsed = _parse_llm_json(resp.text, conn=conn, task_type="teacher_comms")
    if not parsed:
        return _create_template_draft(conn, lead, purpose)

    subject = parsed.get("subject", f"Aelu — {purpose}")
    body_text = parsed.get("body_text", "")

    return _store_draft(conn, lead_id, subject, body_text, purpose)


def draft_pilot_invitation(
    conn: sqlite3.Connection,
    lead_id: int,
) -> int | None:
    """Specific template for pilot program invitations."""
    return draft_teacher_outreach(conn, lead_id, purpose="pilot_invitation")


def _create_template_draft(
    conn: sqlite3.Connection,
    lead,
    purpose: str,
) -> int | None:
    """Create a basic template-based draft without LLM."""
    name = lead["name"]
    platform = lead["platform"]

    if purpose == "pilot_invitation":
        subject = "Invitation: Aelu Teacher Pilot Program"
        body = (
            f"Dear {name},\n\n"
            f"We noticed your teaching profile on {platform} and were impressed "
            f"by your approach to Mandarin instruction.\n\n"
            f"Aelu is building adaptive Mandarin learning technology, and we're "
            f"looking for experienced teachers to participate in our pilot program.\n\n"
            f"Would you be open to a brief conversation about how we might collaborate?\n\n"
            f"Best regards,\nThe Aelu Team"
        )
    else:
        subject = f"Aelu — {purpose}"
        body = (
            f"Dear {name},\n\n"
            f"We're reaching out from Aelu, a Mandarin learning platform. "
            f"We'd love to connect regarding: {purpose}.\n\n"
            f"Best regards,\nThe Aelu Team"
        )

    return _store_draft(conn, lead["id"], subject, body, purpose)


def _store_draft(
    conn: sqlite3.Connection,
    lead_id: int,
    subject: str,
    body_text: str,
    purpose: str,
) -> int | None:
    """Store an email draft in the database."""
    try:
        cursor = conn.execute("""
            INSERT INTO email_draft
            (recipient_type, recipient_id, subject, body_text, purpose, tone_directive)
            VALUES ('teacher_lead', ?, ?, ?, ?, 'professional, warm, respectful')
        """, (lead_id, subject, body_text, purpose))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.OperationalError:
        return None


def get_pending_drafts(conn: sqlite3.Connection) -> list[dict]:
    """Get drafts awaiting human approval."""
    try:
        rows = conn.execute("""
            SELECT ed.*, tl.name as recipient_name, tl.platform, tl.profile_url
            FROM email_draft ed
            LEFT JOIN teacher_lead tl ON tl.id = ed.recipient_id
                AND ed.recipient_type = 'teacher_lead'
            WHERE ed.status = 'draft'
            ORDER BY ed.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def approve_draft(
    conn: sqlite3.Connection,
    draft_id: int,
    approved_by: int,
) -> bool:
    """Approve a draft. Does NOT auto-send."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor = conn.execute("""
            UPDATE email_draft
            SET status = 'approved', approved_by = ?, approved_at = ?
            WHERE id = ? AND status = 'draft'
        """, (approved_by, now, draft_id))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.OperationalError:
        return False


def reject_draft(
    conn: sqlite3.Connection,
    draft_id: int,
    reason: str = "",
) -> bool:
    """Reject a draft with optional reason."""
    try:
        cursor = conn.execute("""
            UPDATE email_draft
            SET status = 'rejected'
            WHERE id = ? AND status = 'draft'
        """, (draft_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.OperationalError:
        return False


def edit_draft(
    conn: sqlite3.Connection,
    draft_id: int,
    subject: str | None = None,
    body_text: str | None = None,
) -> bool:
    """Edit a draft's subject and/or body."""
    try:
        draft = conn.execute(
            "SELECT * FROM email_draft WHERE id = ? AND status = 'draft'",
            (draft_id,),
        ).fetchone()
        if not draft:
            return False

        new_subject = subject if subject is not None else draft["subject"]
        new_body = body_text if body_text is not None else draft["body_text"]

        conn.execute("""
            UPDATE email_draft SET subject = ?, body_text = ?
            WHERE id = ?
        """, (new_subject, new_body, draft_id))
        conn.commit()
        return True
    except sqlite3.OperationalError:
        return False


def mark_sent(
    conn: sqlite3.Connection,
    draft_id: int,
) -> bool:
    """Mark a draft as sent (separate step from approve)."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor = conn.execute("""
            UPDATE email_draft
            SET status = 'sent', sent_at = ?
            WHERE id = ? AND status = 'approved'
        """, (now, draft_id))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.OperationalError:
        return False
