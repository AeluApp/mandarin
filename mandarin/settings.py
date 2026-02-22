"""Centralized environment configuration.

DB path is configurable via DATA_DIR env var.
JSON data (passages, scenarios, media) ships with code — always code-relative.
"""

import os
from pathlib import Path

_project_root = Path(__file__).parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "mandarin-local-only")
IS_PRODUCTION = os.environ.get("IS_PRODUCTION", "").lower() in ("1", "true", "yes")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5173")
DATA_DIR = Path(os.environ.get("DATA_DIR", str(_project_root / "data")))
DB_PATH = DATA_DIR / "mandarin.db"

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "Mandarin <noreply@mandarinapp.com>")

PLAUSIBLE_DOMAIN = os.environ.get("PLAUSIBLE_DOMAIN", "")  # e.g. "mandarinapp.com"
PLAUSIBLE_SCRIPT_URL = os.environ.get("PLAUSIBLE_SCRIPT_URL", "https://plausible.io/js/script.js")

JWT_SECRET = os.environ.get("JWT_SECRET", SECRET_KEY)
JWT_ACCESS_EXPIRY_HOURS = int(os.environ.get("JWT_ACCESS_EXPIRY_HOURS", "1"))
JWT_REFRESH_EXPIRY_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRY_DAYS", "30"))
