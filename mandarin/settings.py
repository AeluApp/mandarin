"""Centralized environment configuration.

DB path is configurable via DATA_DIR env var.
JSON data (passages, scenarios, media) ships with code — always code-relative.
"""

import json
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

# ── A/B pricing variants ────────────────────────────
# Maps experiment variant names to price overrides.
# Only monthly/annual individual plans are A/B-testable;
# classroom and student-upgrade prices are fixed.
PRICING_VARIANTS = {
    "control_14.99": {
        "monthly_cents": 1499,
        "annual_cents": 14900,
        "monthly_display": "14.99",
        "annual_display": "149",
        "annual_monthly_equiv": "12.42",
        "annual_savings": "30",
    },
    "lower_9.99": {
        "monthly_cents": 999,
        "annual_cents": 9900,
        "monthly_display": "9.99",
        "annual_display": "99",
        "annual_monthly_equiv": "8.25",
        "annual_savings": "21",
    },
}

def get_variant_pricing(variant_name: str) -> dict:
    """Return pricing dict for a given experiment variant, falling back to defaults."""
    if variant_name and variant_name in PRICING_VARIANTS:
        merged = dict(PRICING)
        merged.update(PRICING_VARIANTS[variant_name])
        return merged
    return PRICING

# ── Stripe fee model ─────────────────────────────────
STRIPE_FEE_PERCENT = 0.029        # 2.9%
STRIPE_FEE_FIXED_CENTS = 30       # $0.30 per transaction
HOSTING_COST_MONTHLY = 7.00       # $/mo estimate

# ── External services ────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_TAX_ENABLED = os.environ.get("STRIPE_TAX_ENABLED", "").lower() in ("1", "true", "yes")
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
OPENCLAW_REMINDER_HOURS = json.loads(os.environ.get("OPENCLAW_REMINDER_HOURS", "[8, 12, 18]"))
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

# Model tier auto-selection: picks best Qwen model for available system memory.
# Override with OLLAMA_MODEL env var to pin a specific model.
# Tiers: <=8GB → 1.5b, <=16GB → 7b, >16GB → 14b
_QWEN_TIERS = [
    (8,  "qwen2.5:1.5b"),   # 8GB RAM (e.g. M2 MacBook Air)
    (16, "qwen2.5:7b"),     # 16GB RAM
    (99, "qwen2.5:14b"),    # 32GB+ RAM or cloud GPU
]

def _auto_select_model() -> tuple[str, str]:
    """Pick primary + fallback Qwen model based on system memory."""
    try:
        import subprocess
        mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
        mem_gb = mem_bytes / (1024 ** 3)
    except Exception:
        mem_gb = 8  # conservative default
    primary = "qwen2.5:1.5b"
    for threshold, model in _QWEN_TIERS:
        if mem_gb <= threshold:
            primary = model
            break
    # Fallback is one tier down, or same if already smallest
    fallback = "qwen2.5:1.5b"
    for threshold, model in _QWEN_TIERS:
        if model == primary:
            break
        fallback = model
    return primary, fallback

_auto_primary, _auto_fallback = _auto_select_model()
OLLAMA_PRIMARY_MODEL = os.environ.get("OLLAMA_MODEL", _auto_primary)
OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", _auto_fallback)

try:
    OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))
except (ValueError, TypeError):
    OLLAMA_TIMEOUT = 60

# ── LiteLLM (unified LLM gateway) ────────────────────
LITELLM_MODEL = f"ollama/{OLLAMA_PRIMARY_MODEL}"
LITELLM_FALLBACK = f"ollama/{OLLAMA_FALLBACK_MODEL}"

# ── Task-to-model capability gating ──────────────────
# Minimum billion parameters for reliable output per task type.
# Tasks below their tier skip the LLM → callers hit rule-based fallback.
_TASK_COMPLEXITY = {
    # Tier 1: Simple extraction/classification — any model
    "openclaw_intent": 1.0,
    "openclaw_chat": 1.0,
    "classify_prescription": 1.0,
    "error_explanation": 1.0,
    "drill_generation": 1.0,
    "voice_audit": 1.0,
    "interference_detection": 1.0,
    "unknown": 1.0,

    # Tier 2: Structured generation — needs 7b+
    "reading_generation": 5.0,
    "reading_generation_retry": 5.0,
    "conversation_eval": 5.0,
    "conversation_followup": 5.0,
    "teacher_comms": 5.0,
    "rag_faithfulness": 5.0,
    "research_synthesis": 5.0,
    "teacher_qualification": 5.0,
    "aesthetic_quality_evaluation": 5.0,
    "copy_drift_review": 5.0,

    # Tier 3: Complex reasoning — needs 14b+
    "experiment_design": 10.0,
    "meta_intelligence": 10.0,
    "agent_plan": 10.0,
    "editorial_critic": 10.0,
}


def _extract_model_size_b(model_name: str) -> float:
    """Extract effective parameter count in billions from model name.

    Local models: parses 'qwen2.5:14b' → 14.0
    Cloud models: assigns effective capability based on known model families.
    """
    import re
    name = model_name.lower()

    # Check mid/small BEFORE frontier (gpt-4o-mini must not match gpt-4o)
    _CLOUD_SMALL = ("mistral-small", "mistral-tiny")
    if any(f in name for f in _CLOUD_SMALL):
        return 5.0

    _CLOUD_MID = ("gpt-4o-mini", "gpt-3.5", "claude-3-haiku", "claude-haiku",
                  "gemini-1.5-flash", "gemini-flash", "mistral-large",
                  "deepseek-chat", "deepseek-reasoner")
    if any(f in name for f in _CLOUD_MID):
        return 20.0

    # Cloud frontier — capable of everything
    _CLOUD_FRONTIER = ("gpt-4", "claude-3-opus", "claude-3.5-sonnet",
                       "claude-sonnet-4", "claude-opus-4",
                       "gemini-1.5-pro", "gemini-2", "deepseek-r1")
    if any(f in name for f in _CLOUD_FRONTIER):
        return 200.0

    # Local model with explicit size (e.g. qwen2.5:14b, llama3:70b)
    match = re.search(r"(\d+(?:\.\d+)?)\s*[bB]", model_name)
    if match:
        return float(match.group(1))

    return 7.0  # assume 7b if unparseable


def _is_cloud_model(model_name: str) -> bool:
    """Check if the model routes through a cloud provider (not local Ollama)."""
    name = model_name.lower()
    _CLOUD_PREFIXES = ("gpt-", "claude-", "gemini", "anthropic/", "openai/",
                       "mistral/", "deepseek", "together_ai/", "groq/")
    return any(name.startswith(p) or f"/{p.rstrip('/')}" in name for p in _CLOUD_PREFIXES)


IS_CLOUD_MODEL = _is_cloud_model(OLLAMA_PRIMARY_MODEL)
MODEL_SIZE_B = _extract_model_size_b(OLLAMA_PRIMARY_MODEL)


def validate_production_config() -> dict[str, list[str]]:
    """Check that all required production env vars are set.

    Returns a dict with three keys — ``critical``, ``important``, ``optional`` —
    each mapping to a list of human-readable problem descriptions.

    * **critical** – secrets that must never use defaults in production.
      The app MUST NOT start if any of these are missing.
    * **important** – service keys whose absence degrades major features
      (payments, email) but does not compromise security.
    * **optional** – observability / analytics integrations that are
      nice-to-have but not essential.

    Called at startup in create_app() when IS_PRODUCTION is True.
    """
    issues: dict[str, list[str]] = {"critical": [], "important": [], "optional": []}

    # ── CRITICAL: app must not start without these ───────
    if SECRET_KEY == "mandarin-local-only":
        issues["critical"].append(
            "SECRET_KEY is still the default — must be set to a unique secret in production"
        )
    if JWT_SECRET == "mandarin-local-only":
        issues["critical"].append(
            "JWT_SECRET is still the default — must be set to a unique secret in production"
        )

    # ── IMPORTANT: feature-critical but not a security emergency ──
    if not STRIPE_SECRET_KEY:
        issues["important"].append("STRIPE_SECRET_KEY is empty — payment features will fail")
    if not STRIPE_WEBHOOK_SECRET:
        issues["important"].append("STRIPE_WEBHOOK_SECRET is empty — webhook signature verification disabled")
    if not RESEND_API_KEY:
        issues["important"].append("RESEND_API_KEY is empty — transactional emails will fail")
    if not VAPID_PRIVATE_KEY:
        issues["important"].append("VAPID_PRIVATE_KEY is empty — push notifications disabled")

    # ── OPTIONAL: observability / analytics ───────────────
    if not SENTRY_DSN:
        issues["optional"].append("SENTRY_DSN is empty — error monitoring disabled")
    if not PLAUSIBLE_DOMAIN:
        issues["optional"].append("PLAUSIBLE_DOMAIN is empty — Plausible analytics disabled")
    if not GA4_MEASUREMENT_ID:
        issues["optional"].append("GA4_MEASUREMENT_ID is empty — Google Analytics disabled")

    return issues
