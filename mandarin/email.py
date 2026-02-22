"""Transactional email via Resend REST API.

Uses requests.post directly — no resend SDK dependency.
When RESEND_API_KEY is empty (non-production), logs email content
to console and returns True without sending.
"""

import logging

import requests

from .settings import RESEND_API_KEY, FROM_EMAIL

logger = logging.getLogger(__name__)

RESEND_SEND_URL = "https://api.resend.com/emails"

# ---------------------------------------------------------------------------
# Civic Sanctuary email template
# ---------------------------------------------------------------------------

_STYLE = {
    "bg": "#F2EBE0",
    "accent": "#6B9B8E",
    "terracotta": "#B07156",
    "text": "#3A3A3A",
    "heading_font": "'Cormorant Garamond', Georgia, serif",
    "body_font": "'Source Sans 3', 'Helvetica Neue', Arial, sans-serif",
}


def _wrap_html(heading: str, body_html: str) -> str:
    """Wrap content in the Civic Sanctuary email shell."""
    s = _STYLE
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:{s['bg']};font-family:{s['body_font']};color:{s['text']};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{s['bg']};">
<tr><td align="center" style="padding:40px 20px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0"
       style="background-color:#FFFFFF;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
  <tr><td style="background-color:{s['accent']};padding:28px 32px;">
    <h1 style="margin:0;font-family:{s['heading_font']};font-size:24px;font-weight:600;color:#FFFFFF;">
      {heading}
    </h1>
  </td></tr>
  <tr><td style="padding:32px;">
    {body_html}
  </td></tr>
  <tr><td style="padding:20px 32px;border-top:1px solid #E8E0D5;text-align:center;">
    <p style="margin:0;font-size:13px;color:#999;">Mandarin</p>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    """Render a CTA button in terracotta."""
    s = _STYLE
    return (
        f'<p style="text-align:center;margin:28px 0;">'
        f'<a href="{url}" style="display:inline-block;padding:12px 28px;'
        f"background-color:{s['terracotta']};color:#FFFFFF;text-decoration:none;"
        f'border-radius:6px;font-family:{s["body_font"]};font-size:15px;font-weight:600;">'
        f"{label}</a></p>"
    )


# ---------------------------------------------------------------------------
# Internal send helper
# ---------------------------------------------------------------------------

def _send(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend, or log it when API key is absent."""
    if not RESEND_API_KEY:
        logger.info(
            "[email dev-mode] to=%s subject=%s\n%s",
            to, subject, html,
        )
        return True

    try:
        resp = requests.post(
            RESEND_SEND_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info("Email sent: to=%s subject=%s", to, subject)
            return True
        else:
            logger.error(
                "Resend API error %s: %s", resp.status_code, resp.text
            )
            return False
    except (OSError, ValueError, TypeError, ConnectionError) as e:
        logger.exception("Failed to send email to %s: %s", to, e)
        return False


# ---------------------------------------------------------------------------
# Public email functions
# ---------------------------------------------------------------------------

def send_email_verification(to_email: str, verify_url: str) -> bool:
    """Send email verification link after registration."""
    body = (
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Please verify your email address to complete registration.</p>"
        f"{_button(verify_url, 'Verify Email')}"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"This link expires in 24 hours.</p>"
    )
    html = _wrap_html("Verify Your Email", body)
    return _send(to_email, "Verify your Mandarin email", html)


def send_unsubscribe_confirmation(to_email: str) -> bool:
    """Confirm marketing email opt-out."""
    body = (
        f'<p style="font-size:16px;line-height:1.6;">'
        f"You have been unsubscribed from marketing emails. "
        f"You will still receive account-related notifications.</p>"
    )
    html = _wrap_html("Unsubscribed", body)
    return _send(to_email, "Unsubscribed from Mandarin marketing", html)


def send_alert(to_email: str, subject: str, details: str) -> bool:
    """Send critical security alert to admin."""
    body = (
        f'<p style="font-size:16px;line-height:1.6;font-weight:600;color:#B07156;">'
        f"Critical security event detected:</p>"
        f'<p style="font-size:14px;line-height:1.6;font-family:monospace;'
        f'background:#F5F5F5;padding:12px;border-radius:4px;">{details}</p>'
    )
    html = _wrap_html("Security Alert", body)
    return _send(to_email, subject, html)


def send_welcome(to_email: str, display_name: str) -> bool:
    """Send welcome email after registration."""
    name = display_name or "there"
    body = (
        f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Welcome to Mandarin. Your account is ready.</p>"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Start your first session whenever you like. "
        f"Everything adapts to your pace.</p>"
        f'<p style="font-size:16px;line-height:1.6;color:{_STYLE["accent"]};">'
        f"Good studying.</p>"
    )
    html = _wrap_html("Welcome to Mandarin", body)
    return _send(to_email, "Welcome to Mandarin", html)


def send_password_reset(to_email: str, reset_url: str) -> bool:
    """Send password reset link."""
    body = (
        f'<p style="font-size:16px;line-height:1.6;">'
        f"We received a request to reset your password.</p>"
        f"{_button(reset_url, 'Reset Password')}"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"This link expires in 1 hour. If you did not request this, "
        f"you can safely ignore this email.</p>"
    )
    html = _wrap_html("Reset Your Password", body)
    return _send(to_email, "Reset your Mandarin password", html)


def send_subscription_confirmed(to_email: str, display_name: str) -> bool:
    """Send subscription confirmation."""
    name = display_name or "there"
    body = (
        f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Your subscription is confirmed. You now have full access "
        f"to every feature in Mandarin.</p>"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"You can manage your subscription anytime from your account settings.</p>"
        f'<p style="font-size:16px;line-height:1.6;color:{_STYLE["accent"]};">'
        f"Thanks for supporting the project.</p>"
    )
    html = _wrap_html("Subscription Confirmed", body)
    return _send(to_email, "Your Mandarin subscription is active", html)


def send_subscription_cancelled(to_email: str, display_name: str, access_until: str) -> bool:
    """Send cancellation notice with access-until date."""
    name = display_name or "there"
    body = (
        f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Your subscription has been cancelled. You will continue "
        f"to have full access until <strong>{access_until}</strong>.</p>"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"After that date your account will revert to the free tier. "
        f"You can resubscribe anytime.</p>"
        f'<p style="font-size:16px;line-height:1.6;color:{_STYLE["accent"]};">'
        f"We hope to see you back.</p>"
    )
    html = _wrap_html("Subscription Cancelled", body)
    return _send(to_email, "Your Mandarin subscription has been cancelled", html)
