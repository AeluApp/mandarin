"""Centralized environment configuration.

DB path is configurable via DATA_DIR env var.
JSON data (passages, scenarios, media) ships with code — always code-relative.
"""

import os
from pathlib import Path

_project_root = Path(__file__).parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "mandarin-local-only")
IS_PRODUCTION = os.environ.get("IS_PRODUCTION", "").lower() in ("1", "true", "yes")

# ── Domain / URL ──────────────────────────────────────
CANONICAL_DOMAIN = os.environ.get("AELU_DOMAIN", "aeluapp.com")
CANONICAL_URL = os.environ.get("AELU_BASE_URL", f"https://{CANONICAL_DOMAIN}")

# ── Network ───────────────────────────────────────────
DEFAULT_PORT = 5173
try:
    PORT = int(os.environ.get("PORT", "0"))
except (ValueError, TypeError):
    PORT = 0

BASE_URL = os.environ.get("BASE_URL", f"http://localhost:{PORT or DEFAULT_PORT}")

# ── Data / DB ─────────────────────────────────────────
DATA_DIR = Path(os.environ.get("DATA_DIR", str(_project_root / "data")))
DB_PATH = DATA_DIR / "mandarin.db"

# ── Pricing (cents unless noted) ──────────────────────
PRICING = {
    "monthly_cents": 1499,         # $14.99/mo
    "annual_cents": 14900,         # $149/year
    "monthly_display": "14.99",    # for revenue calculations & display
    "annual_display": "149",
    "annual_monthly_equiv": "12.42",  # $149/12
    "annual_savings": "30",        # ~$180-$149
    "classroom_per_student_cents": 800,   # $8/student/mo
    "classroom_semester_cents": 20000,    # $200 flat
    "classroom_min_students": 5,
    "classroom_max_students_semester": 30,
    "student_upgrade_cents": 499,  # $4.99/mo
}

# ── Stripe fee model ─────────────────────────────────
STRIPE_FEE_PERCENT = 0.029        # 2.9%
STRIPE_FEE_FIXED_CENTS = 30       # $0.30 per transaction
HOSTING_COST_MONTHLY = 7.00       # $/mo estimate

# ── External services ────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", f"Aelu <noreply@{CANONICAL_DOMAIN}>")
MAILING_ADDRESS = os.environ.get("MAILING_ADDRESS", "Aelu")

PLAUSIBLE_DOMAIN = os.environ.get("PLAUSIBLE_DOMAIN", "")  # e.g. "aeluapp.com"
PLAUSIBLE_SCRIPT_URL = os.environ.get("PLAUSIBLE_SCRIPT_URL", "https://plausible.io/js/script.js")
GA4_MEASUREMENT_ID = os.environ.get("GA4_MEASUREMENT_ID", "")  # e.g. "G-XXXXXXXXXX"

JWT_SECRET = os.environ.get("JWT_SECRET", SECRET_KEY)

try:
    JWT_ACCESS_EXPIRY_HOURS = int(os.environ.get("JWT_ACCESS_EXPIRY_HOURS", "1"))
except (ValueError, TypeError):
    JWT_ACCESS_EXPIRY_HOURS = 1

try:
    JWT_REFRESH_EXPIRY_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRY_DAYS", "30"))
except (ValueError, TypeError):
    JWT_REFRESH_EXPIRY_DAYS = 30

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", f"mailto:admin@{CANONICAL_DOMAIN}")

ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

# ── Sentry ────────────────────────────────────────────
SENTRY_TRACES_SAMPLE_RATE = 0.1

# ── Cookie / session ─────────────────────────────────
REMEMBER_COOKIE_DURATION_SECONDS = 30 * 24 * 3600  # 30 days
CSRF_TOKEN_LIFETIME_SECONDS = 86400  # 24 hours
STATIC_CACHE_MAX_AGE = 31536000  # 1 year (immutable assets)
SLOW_REQUEST_THRESHOLD_MS = 1000  # Log warning when request exceeds this

try:
    SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "30"))
except (ValueError, TypeError):
    SESSION_TIMEOUT_MINUTES = 30

FLASK_ENV = os.environ.get("FLASK_ENV", "")

# ── OpenClaw (messaging-first admin) ──────────────
OPENCLAW_SIGNAL_NUMBER = os.environ.get("OPENCLAW_SIGNAL_NUMBER", "")
OPENCLAW_API_KEY = os.environ.get("OPENCLAW_API_KEY", "")
OPENCLAW_REMINDER_HOURS = [8, 12, 18]
OPENCLAW_REVIEW_DEBOUNCE_SECONDS = 3600
try:
    OPENCLAW_PIPECAT_PORT = int(os.environ.get("OPENCLAW_PIPECAT_PORT", "8765"))
except (ValueError, TypeError):
    OPENCLAW_PIPECAT_PORT = 8765

# Telegram
OPENCLAW_TELEGRAM_TOKEN = os.environ.get("OPENCLAW_TELEGRAM_TOKEN", "")
OPENCLAW_TELEGRAM_OWNER_ID = os.environ.get("OPENCLAW_TELEGRAM_OWNER_ID", "0")

# WhatsApp (Meta Cloud API)
OPENCLAW_WHATSAPP_TOKEN = os.environ.get("OPENCLAW_WHATSAPP_TOKEN", "")
OPENCLAW_WHATSAPP_PHONE_ID = os.environ.get("OPENCLAW_WHATSAPP_PHONE_ID", "")
OPENCLAW_WHATSAPP_VERIFY_TOKEN = os.environ.get("OPENCLAW_WHATSAPP_VERIFY_TOKEN", "")
OPENCLAW_WHATSAPP_OWNER_NUMBER = os.environ.get("OPENCLAW_WHATSAPP_OWNER_NUMBER", "")

# Discord
OPENCLAW_DISCORD_TOKEN = os.environ.get("OPENCLAW_DISCORD_TOKEN", "")
OPENCLAW_DISCORD_OWNER_ID = os.environ.get("OPENCLAW_DISCORD_OWNER_ID", "0")

# iMessage (macOS only)
OPENCLAW_IMESSAGE_OWNER_ID = os.environ.get("OPENCLAW_IMESSAGE_OWNER_ID", "")

# ── Kanban / methodology ──────────────────────────────
WIP_LIMIT_IN_PROGRESS = 5
ESTIMATE_POINTS = {"S": 1, "M": 3, "L": 5, "XL": 8}

# ── Ollama (local LLM) ─────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_PRIMARY_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:1.5b")
try:
    OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "30"))
except (ValueError, TypeError):
    OLLAMA_TIMEOUT = 30


def validate_production_config() -> list[str]:
    """Check that all required production env vars are set.

    Returns a list of warning messages (empty = all good).
    Called at startup in create_app() when IS_PRODUCTION is True.
    """
    warnings = []
    if not STRIPE_SECRET_KEY:
        warnings.append("STRIPE_SECRET_KEY is empty — payment features will fail")
    if not STRIPE_WEBHOOK_SECRET:
        warnings.append("STRIPE_WEBHOOK_SECRET is empty — webhook signature verification disabled")
    if not RESEND_API_KEY:
        warnings.append("RESEND_API_KEY is empty — transactional emails will fail")
    if not VAPID_PRIVATE_KEY:
        warnings.append("VAPID_PRIVATE_KEY is empty — push notifications disabled")
    if not SENTRY_DSN:
        warnings.append("SENTRY_DSN is empty — error monitoring disabled")
    return warnings
