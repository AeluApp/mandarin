"""Transactional email via Resend REST API.

Uses requests.post directly — no resend SDK dependency.
When RESEND_API_KEY is empty (non-production), logs email content
to console and returns True without sending.
"""

import logging

import requests

from .settings import RESEND_API_KEY, FROM_EMAIL, BASE_URL, MAILING_ADDRESS

logger = logging.getLogger(__name__)

RESEND_SEND_URL = "https://api.resend.com/emails"

# ---------------------------------------------------------------------------
# Civic Sanctuary email template
# ---------------------------------------------------------------------------

_STYLE = {
    "bg": "#F2EBE0",
    "accent": "#946070",
    "text": "#2A3650",
    "text_dim": "#5A6678",
    "divider": "#D8D0C4",
    "heading_font": "'Cormorant Garamond', Georgia, serif",
    "body_font": "'Source Serif 4', Georgia, 'Times New Roman', serif",
    # Dark mode
    "dark_bg": "#1C2028",
    "dark_accent": "#B07888",
    "dark_text": "#E4DDD0",
    "dark_text_dim": "#A09888",
    "dark_divider": "#3A3530",
}


def _wrap_html(heading: str, body_html: str) -> str:
    """Wrap content in the Civic Sanctuary email shell."""
    s = _STYLE
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Source+Serif+4:wght@400;600&display=swap" rel="stylesheet">
<style>
  @media (prefers-color-scheme: dark) {{
    body, .email-bg {{ background-color: {s['dark_bg']} !important; }}
    .email-card {{ background-color: {s['dark_bg']} !important; }}
    .email-header {{ background-color: {s['dark_accent']} !important; }}
    .email-body, .email-body p, .email-body li {{ color: {s['dark_text']} !important; }}
    .email-body td {{ color: {s['dark_text']} !important; }}
    .email-footer p {{ color: {s['dark_text_dim']} !important; }}
    .email-footer a {{ color: {s['dark_text_dim']} !important; }}
    .email-divider {{ border-color: {s['dark_divider']} !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background-color:{s['bg']};font-family:{s['body_font']};color:{s['text']};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="email-bg" style="background-color:{s['bg']};">
<tr><td align="center" style="padding:40px 20px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" class="email-card"
       style="background-color:{s['bg']};overflow:hidden;">
  <tr><td class="email-header" style="background-color:{s['accent']};padding:28px 32px;">
    <p style="margin:0 0 8px 0;font-family:'Noto Serif SC',serif;font-size:32px;color:rgba(255,255,255,0.7);line-height:1;">漫</p>
    <h1 style="margin:0;font-family:{s['heading_font']};font-size:24px;font-weight:600;color:#FFFFFF;">
      {heading}
    </h1>
  </td></tr>
  <tr><td class="email-body" style="padding:32px;">
    {body_html}
  </td></tr>
  <tr><td class="email-footer" style="padding:20px 32px;border-top:1px solid {s['divider']};text-align:center;">
    <p style="margin:0;font-size:13px;color:{s['text_dim']};">Aelu</p>
    <p style="margin:4px 0 0;font-size:11px;color:{s['text_dim']};">{MAILING_ADDRESS}</p>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    """Render a CTA button in brand accent."""
    s = _STYLE
    return (
        f'<p style="text-align:center;margin:28px 0;">'
        f'<a href="{url}" style="display:inline-block;padding:14px 32px;'
        f"background-color:{s['accent']};color:#FFFFFF;text-decoration:none;"
        f'border-radius:4px;font-family:{s["heading_font"]};font-size:16px;'
        f'font-weight:600;letter-spacing:0.03em;">'
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
    return _send(to_email, "Verify your Aelu email", html)


def send_unsubscribe_confirmation(to_email: str) -> bool:
    """Confirm marketing email opt-out."""
    body = (
        f'<p style="font-size:16px;line-height:1.6;">'
        f"You have been unsubscribed from marketing emails. "
        f"You will still receive account-related notifications.</p>"
    )
    html = _wrap_html("Unsubscribed", body)
    return _send(to_email, "Unsubscribed from Aelu marketing", html)


def send_alert(to_email: str, subject: str, details: str) -> bool:
    """Send critical security alert to admin."""
    body = (
        f'<p style="font-size:16px;line-height:1.6;font-weight:600;color:{_STYLE["accent"]};">'
        f"Critical security event detected:</p>"
        f'<p style="font-size:14px;line-height:1.6;font-family:monospace;'
        f'background:{_STYLE["bg"]};padding:12px;">{details}</p>'
    )
    html = _wrap_html("Security Alert", body)
    return _send(to_email, subject, html)


def send_welcome(to_email: str, display_name: str) -> bool:
    """Send welcome email after registration."""
    name = display_name or "there"
    body = (
        f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Welcome to Aelu. Your account is ready.</p>"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Start your first session whenever you like. "
        f"Everything adapts to your pace.</p>"
        f'<p style="font-size:16px;line-height:1.6;color:{_STYLE["accent"]};">'
        f"Good studying.</p>"
    )
    html = _wrap_html("Welcome to Aelu", body)
    return _send(to_email, "Welcome to Aelu", html)


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
    return _send(to_email, "Reset your Aelu password", html)


def send_subscription_confirmed(to_email: str, display_name: str) -> bool:
    """Send subscription confirmation."""
    name = display_name or "there"
    body = (
        f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Your subscription is confirmed. You now have full access "
        f"to every feature in Aelu.</p>"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"You can manage your subscription anytime from your account settings.</p>"
        f'<p style="font-size:16px;line-height:1.6;color:{_STYLE["accent"]};">'
        f"Thanks for supporting the project.</p>"
    )
    html = _wrap_html("Subscription Confirmed", body)
    return _send(to_email, "Your Aelu subscription is active", html)


def send_activation_nudge(to: str, name: str, n: int, user_id: int = None) -> bool:
    """Activation nudge sequence (users who signed up but haven't started).

    n=1: 24h "Account ready", n=2: 5d "5 min to start", n=3: 10d "Still interested?"
    """
    name = name or "there"
    variants = {
        1: {
            "subject": "Your Aelu account is ready",
            "heading": "Your Account Is Ready",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"Your account is set up and waiting. Your first session takes "
                f"about 5 minutes and adapts to whatever you already know.</p>"
            ),
            "cta": "Start Your First Session",
        },
        2: {
            "subject": "5 minutes to start learning Mandarin",
            "heading": "Five Minutes Is All It Takes",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"Just a quick note — your first session is ready whenever you are. "
                f"It takes about 5 minutes, and everything adapts from there.</p>"
            ),
            "cta": "Start Now",
        },
        3: {
            "subject": "Still interested in learning Mandarin?",
            "heading": "Still Interested?",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"We noticed you haven't started yet. No pressure — your account "
                f"is still here whenever the timing is right.</p>"
                f'<p style="font-size:16px;line-height:1.6;">'
                f"If you have questions about getting started, just reply to this email.</p>"
            ),
            "cta": "Open Aelu",
        },
    }
    v = variants.get(n, variants[1])
    body = v["body"] + _button(BASE_URL + "/", v["cta"])
    body += _unsubscribe_footer(user_id)
    html = _wrap_html(v["heading"], body)
    return _send(to, v["subject"], html)


def send_onboarding_tip(to: str, name: str, n: int, user_id: int = None) -> bool:
    """Onboarding drip sequence (users who have started).

    n=3: feature discovery, n=4: study tip, n=5: progress summary,
    n=6: more features, n=7: check-in.
    """
    name = name or "there"
    variants = {
        3: {
            "subject": "Discover what Aelu can do",
            "heading": "Features Worth Knowing",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"Now that you've started, here are a few things worth knowing:</p>"
                f'<ul style="font-size:16px;line-height:1.8;">'
                f"<li>The system adapts drill types to your weak spots automatically</li>"
                f"<li>Context notes explain real-world usage for every word</li>"
                f"<li>Your dashboard tracks progress across all four skills</li></ul>"
            ),
        },
        4: {
            "subject": "A study tip for better retention",
            "heading": "Study Tip",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"Short, frequent sessions beat long, infrequent ones. "
                f"Even 5 minutes a day keeps your spaced repetition intervals tight "
                f"and retention high.</p>"
            ),
        },
        5: {
            "subject": "Your first week of progress",
            "heading": "Your Progress So Far",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"You've been at it for a week. Check your dashboard to see how "
                f"your accuracy and vocabulary are tracking.</p>"
            ),
        },
        6: {
            "subject": "More ways to learn",
            "heading": "Beyond Drills",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"Drills build foundations, but real fluency comes from exposure. "
                f"Try the graded reader or extensive listening features to immerse "
                f"yourself in real Mandarin at your level.</p>"
            ),
        },
        7: {
            "subject": "How's it going?",
            "heading": "Two-Week Check-In",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"You've been studying for two weeks. How's it feeling? "
                f"If anything is unclear or you want to adjust your pace, "
                f"just reply to this email.</p>"
            ),
        },
    }
    v = variants.get(n, variants[3])
    body = v["body"] + _button(BASE_URL + "/", "Open Aelu")
    body += _unsubscribe_footer(user_id)
    html = _wrap_html(v["heading"], body)
    return _send(to, v["subject"], html)


def send_churn_prevention(to: str, name: str, n: int, days: int = 0, user_id: int = None) -> bool:
    """Churn prevention sequence for inactive paid users.

    n=1: gentle (5d), n=2: direct (8d), n=3: honest + pause (12d), n=4: final (19d).
    """
    name = name or "there"
    variants = {
        1: {
            "subject": "A few words are ready for you",
            "heading": "Whenever You're Ready",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"It's been {days} days. Your review queue has some words "
                f"that are at their best recall window right now — a quick session "
                f"would go a long way.</p>"
            ),
            "cta": "Open Your Reviews",
        },
        2: {
            "subject": "Checking in on your progress",
            "heading": "A Gentle Update",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"It's been {days} days. Some of your review intervals are "
                f"stretching — nothing is lost, but the longer you wait, "
                f"the more ground you'll need to re-cover. Even five minutes "
                f"makes a difference.</p>"
            ),
            "cta": "Pick Up Where You Left Off",
        },
        3: {
            "subject": "Need a break? You can pause your subscription",
            "heading": "Honest Check-In",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"It's been {days} days. If life got busy, no judgment — "
                f"you can pause your subscription from your account settings "
                f"and pick back up when you're ready.</p>"
                f'<p style="font-size:16px;line-height:1.6;">'
                f"If something about the app isn't working for you, "
                f"reply to this email. We read every response.</p>"
            ),
            "cta": "Open Settings",
        },
        4: {
            "subject": "Final check-in from Aelu",
            "heading": "Last Note From Us",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"This is our last outreach. You've been away {days} days. "
                f"Your account and all your progress are still here if you "
                f"want to come back.</p>"
                f'<p style="font-size:16px;line-height:1.6;">'
                f"We won't email again unless you return.</p>"
            ),
            "cta": "Come Back",
        },
    }
    v = variants.get(n, variants[1])
    body = v["body"] + _button(BASE_URL + "/", v["cta"])
    body += _unsubscribe_footer(user_id)
    html = _wrap_html(v["heading"], body)
    return _send(to, v["subject"], html)


def send_milestone_reached(to: str, name: str, milestone: str, data: dict = None, user_id: int = None) -> bool:
    """Milestone celebration email."""
    name = name or "there"
    data = data or {}
    milestone_labels = {
        "first_session": "First Session Complete",
        "streak_7": "7-Day Streak",
        "streak_30": "30-Day Streak",
        "hsk1_complete": "HSK 1 Mastered",
        "hsk2_complete": "HSK 2 Mastered",
        "hsk2_boundary": "HSK 2 Boundary Reached",
        "hsk3_complete": "HSK 3 Mastered",
        "vocab_100": "100 Words Mastered",
        "vocab_500": "500 Words Mastered",
        "vocab_1000": "1,000 Words Mastered",
    }
    label = milestone_labels.get(milestone, milestone.replace("_", " ").title())
    body = (
        f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
        f'<p style="font-size:16px;line-height:1.6;">'
        f"You've reached a milestone: <strong>{label}</strong>.</p>"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"This is real progress. Keep going.</p>"
    )
    body += _button(BASE_URL + "/", "See Your Progress")
    body += _unsubscribe_footer(user_id)
    html = _wrap_html("Milestone Reached", body)
    return _send(to, f"Milestone: {label}", html)


def send_classroom_invite(to: str, teacher_name: str, class_name: str, invite_code: str) -> bool:
    """Classroom invite email sent to students."""
    body = (
        f'<p style="font-size:16px;line-height:1.6;">'
        f"<strong>{teacher_name}</strong> has invited you to join "
        f"<strong>{class_name}</strong> on Aelu.</p>"
        f'<p style="font-size:16px;line-height:1.6;">'
        f"Use the code below when you sign up or in your settings:</p>"
        f'<p style="text-align:center;font-size:24px;font-family:monospace;'
        f'letter-spacing:4px;padding:16px;background:{_STYLE["bg"]};">'
        f"<strong>{invite_code}</strong></p>"
    )
    body += _button(BASE_URL + "/auth/register", "Join Classroom")
    html = _wrap_html(f"Join {class_name}", body)
    return _send(to, f"You're invited to {class_name} on Aelu", html)


def _unsubscribe_footer(user_id: int = None) -> str:
    """Render a small unsubscribe link with HMAC token for one-click opt-out."""
    if user_id is not None:
        import hmac as _hmac
        import hashlib as _hashlib
        from .settings import SECRET_KEY as _sk
        uid_str = str(user_id)
        token = _hmac.new(_sk.encode(), uid_str.encode(), _hashlib.sha256).hexdigest()[:32]
        url = f"{BASE_URL}/auth/unsubscribe?uid={uid_str}&token={token}"
    else:
        url = f"{BASE_URL}/auth/unsubscribe"
    return (
        f'<p style="font-size:12px;color:#999;margin-top:24px;text-align:center;">'
        f'<a href="{url}" style="color:#999;">Unsubscribe from marketing emails</a></p>'
    )


def send_winback(to: str, name: str, n: int, user_id: int = None) -> bool:
    """Win-back sequence for cancelled users.

    n=1: 7d post-cancel (gentle), n=2: 30d (progress reminder), n=3: 60d (final).
    """
    name = name or "there"
    variants = {
        1: {
            "subject": "Your progress is still here",
            "heading": "Your Progress Is Waiting",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"It\u2019s been a week since you cancelled. Just wanted you to know \u2014 "
                f"all your progress, scores, and study history are still exactly where "
                f"you left them.</p>"
                f'<p style="font-size:16px;line-height:1.6;">'
                f"If you want to pick back up, everything will be waiting.</p>"
            ),
            "cta": "See Your Progress",
        },
        2: {
            "subject": "30 days later \u2014 a quick update",
            "heading": "A Month Has Passed",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"It\u2019s been a month. Your vocabulary and study data are still "
                f"safe in your account. Spaced repetition works best with consistency, "
                f"and getting back to it sooner means less re-learning.</p>"
                f'<p style="font-size:16px;line-height:1.6;">'
                f"The free tier still gives you HSK 1\u20132 access if you want to "
                f"ease back in.</p>"
            ),
            "cta": "Log Back In",
        },
        3: {
            "subject": "Last note from Aelu",
            "heading": "One Last Note",
            "body": (
                f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
                f'<p style="font-size:16px;line-height:1.6;">'
                f"This is our final check-in. Your account and all your data are still "
                f"here if you ever want to return. We won\u2019t email again after this.</p>"
                f'<p style="font-size:16px;line-height:1.6;">'
                f"If there\u2019s something we could have done better, "
                f"we\u2019d genuinely like to know \u2014 just reply to this email.</p>"
            ),
            "cta": "Resubscribe",
        },
    }
    v = variants.get(n, variants[1])
    body = v["body"] + _button(BASE_URL + "/", v["cta"])
    body += _unsubscribe_footer(user_id)
    html = _wrap_html(v["heading"], body)
    return _send(to, v["subject"], html)


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
    return _send(to_email, "Your Aelu subscription has been cancelled", html)


def send_weekly_progress(to: str, name: str, stats: dict, user_id: int = None) -> bool:
    """Weekly progress digest — sent every Monday.

    stats keys:
        sessions: int, items_reviewed: int, accuracy: float (0-100),
        accuracy_trend: str (up/down/flat), words_long_term: int,
        next_milestone: int|None, sessions_to_milestone: int|None,
        streak_days: int
    """
    name = name or "there"
    sessions = stats.get("sessions", 0)
    items = stats.get("items_reviewed", 0)
    accuracy = stats.get("accuracy")
    trend = stats.get("accuracy_trend", "flat")
    words_lt = stats.get("words_long_term", 0)
    streak = stats.get("streak_days", 0)
    next_ms = stats.get("next_milestone")
    sessions_to = stats.get("sessions_to_milestone")

    # Accuracy trend indicator
    trend_symbol = {"up": "\u2191", "down": "\u2193", "flat": "\u2192"}.get(trend, "")
    acc_text = f"{accuracy:.0f}% {trend_symbol}" if accuracy is not None else "N/A"

    # Milestone line
    milestone_line = ""
    if next_ms and sessions_to:
        milestone_line = (
            f'<tr><td style="padding:8px 12px;color:{_STYLE["text"]};">Next milestone</td>'
            f'<td style="padding:8px 12px;font-weight:600;color:{_STYLE["accent"]};">'
            f'{next_ms} words (~{sessions_to} sessions)</td></tr>'
        )

    body = (
        f'<p style="font-size:16px;line-height:1.6;">Hi {name},</p>'
        f'<p style="font-size:16px;line-height:1.6;">Here\'s your week in review:</p>'
        f'<table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:15px;">'
        f'<tr style="border-bottom:1px solid {_STYLE["divider"]};">'
        f'<td style="padding:8px 12px;color:{_STYLE["text"]};">Sessions</td>'
        f'<td style="padding:8px 12px;font-weight:600;">{sessions}</td></tr>'
        f'<tr style="border-bottom:1px solid {_STYLE["divider"]};">'
        f'<td style="padding:8px 12px;color:{_STYLE["text"]};">Items reviewed</td>'
        f'<td style="padding:8px 12px;font-weight:600;">{items}</td></tr>'
        f'<tr style="border-bottom:1px solid {_STYLE["divider"]};">'
        f'<td style="padding:8px 12px;color:{_STYLE["text"]};">Accuracy</td>'
        f'<td style="padding:8px 12px;font-weight:600;">{acc_text}</td></tr>'
        f'<tr style="border-bottom:1px solid {_STYLE["divider"]};">'
        f'<td style="padding:8px 12px;color:{_STYLE["text"]};">Words in long-term memory</td>'
        f'<td style="padding:8px 12px;font-weight:600;">{words_lt}</td></tr>'
        f'<tr style="border-bottom:1px solid {_STYLE["divider"]};">'
        f'<td style="padding:8px 12px;color:{_STYLE["text"]};">Streak</td>'
        f'<td style="padding:8px 12px;font-weight:600;">{streak} days</td></tr>'
        f'{milestone_line}'
        f'</table>'
    )
    body += _button(BASE_URL + "/", "Continue Studying")
    body += _unsubscribe_footer(user_id)
    html = _wrap_html("Your Week", body)
    return _send(to, f"Your Aelu week: {sessions} sessions, {items} items reviewed", html)
