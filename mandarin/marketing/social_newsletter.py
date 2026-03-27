"""Newsletter integration via Resend API.

Reuses the existing Resend infrastructure from mandarin/email.py.
Sends newsletters to the subscriber list with tracking UTMs.

Exports:
    send_newsletter(subject, body_html, conn=None) -> PostResult
    is_newsletter_configured() -> bool
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PostResult:
    success: bool
    platform: str = "newsletter"
    post_id: str = ""  # Resend message ID
    error: str = ""
    data: dict = field(default_factory=dict)


def is_newsletter_configured() -> bool:
    """Check if newsletter sending is configured (Resend API key + from email)."""
    from ..settings import RESEND_API_KEY, FROM_EMAIL
    return bool(RESEND_API_KEY and FROM_EMAIL)


def send_newsletter(
    subject: str,
    body_html: str,
    utm_campaign: str = "",
    conn=None,
) -> PostResult:
    """Send a newsletter to the subscriber audience via Resend.

    Appends UTM parameters to any links in the body for tracking.
    """
    if not is_newsletter_configured():
        return PostResult(success=False, error="Newsletter not configured (RESEND_API_KEY)")

    try:
        import resend

        from ..settings import RESEND_API_KEY, FROM_EMAIL
        resend.api_key = RESEND_API_KEY
        from_email = FROM_EMAIL

        # Add UTM tracking to links if campaign is set
        if utm_campaign:
            import re
            utm_suffix = f"utm_source=newsletter&utm_medium=email&utm_campaign={utm_campaign}"
            body_html = re.sub(
                r'(href=["\'])(https?://aeluapp\.com[^"\']*)',
                lambda m: m.group(1) + m.group(2) + ("&" if "?" in m.group(2) else "?") + utm_suffix,
                body_html,
            )

        # Get newsletter audience ID or use broadcast
        from ..settings import RESEND_AUDIENCE_ID
        audience_id = RESEND_AUDIENCE_ID

        if audience_id:
            # Broadcast to audience
            resp = resend.Broadcasts.send({
                "audience_id": audience_id,
                "from": from_email,
                "subject": subject,
                "html": body_html,
            })
            msg_id = resp.get("id", "") if isinstance(resp, dict) else str(resp)
        else:
            # Fallback: send to a specific list email if no audience configured
            from ..settings import NEWSLETTER_TO
            newsletter_to = NEWSLETTER_TO
            if not newsletter_to:
                return PostResult(success=False, error="No RESEND_AUDIENCE_ID or NEWSLETTER_TO configured")

            resp = resend.Emails.send({
                "from": from_email,
                "to": [newsletter_to],
                "subject": subject,
                "html": body_html,
            })
            msg_id = resp.get("id", "") if isinstance(resp, dict) else str(resp)

        logger.info("Newsletter sent: %s (id=%s)", subject[:50], msg_id)
        return PostResult(success=True, post_id=msg_id)

    except ImportError:
        return PostResult(success=False, error="resend package not installed")
    except Exception as e:
        logger.exception("Newsletter send failed")
        return PostResult(success=False, error=str(e))
