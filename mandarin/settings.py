"""Centralized environment configuration.

DB path is configurable via DATA_DIR env var.
JSON data (passages, scenarios, media) ships with code — always code-relative.
"""

import json
import os
from pathlib import Path

_project_root = Path(__file__).parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY") or "mandarin-local-only"
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
RESEND_AUDIENCE_ID = os.environ.get("RESEND_AUDIENCE_ID", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", f"Aelu <noreply@{CANONICAL_DOMAIN}>")
MAILING_ADDRESS = os.environ.get("MAILING_ADDRESS", "Aelu")
NEWSLETTER_TO = os.environ.get("NEWSLETTER_TO", "")
MARKETING_NOTIFY_EMAIL = os.environ.get("MARKETING_NOTIFY_EMAIL", "")

# ── Notifications — Matrix / Beeper ───────────────────
MATRIX_HOMESERVER   = os.environ.get("MATRIX_HOMESERVER", "")
MATRIX_ACCESS_TOKEN = os.environ.get("MATRIX_ACCESS_TOKEN", "")
MATRIX_USER_ID      = os.environ.get("MATRIX_USER_ID", "")

PLAUSIBLE_DOMAIN = os.environ.get("PLAUSIBLE_DOMAIN", "")  # e.g. "aeluapp.com"
PLAUSIBLE_API_KEY = os.environ.get("PLAUSIBLE_API_KEY", "")

# ── LLM spend cap ─────────────────────────────────────
# Monthly USD cap for cloud LLM token spend. Once reached, all non-critical
# LLM calls return failure (callers hit rule-based fallback). Critical tasks
# (user-facing drill generation, error explanation) are exempt.
# Set to 0 for unlimited. Default: $25/month.
try:
    LLM_MONTHLY_SPEND_CAP_USD = float(os.environ.get("LLM_MONTHLY_SPEND_CAP_USD", "25.0"))
except (ValueError, TypeError):
    LLM_MONTHLY_SPEND_CAP_USD = 25.0
# ── SMTP (fallback email transport) ──────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", "")
try:
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
except (ValueError, TypeError):
    SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

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
ANDON_WEBHOOK_URL = os.environ.get("ANDON_WEBHOOK_URL", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

# ── UptimeRobot (uptime monitoring) ──────────────────
UPTIMEROBOT_API_KEY = os.environ.get("UPTIMEROBOT_API_KEY", "")

# ── Sentry (error monitoring) ────────────────────────
SENTRY_AUTH_TOKEN = os.environ.get("SENTRY_AUTH_TOKEN", "")
SENTRY_ORG = os.environ.get("SENTRY_ORG", "")
SENTRY_PROJECT = os.environ.get("SENTRY_PROJECT", "")
SENTRY_WEBHOOK_SECRET = os.environ.get("SENTRY_WEBHOOK_SECRET", "")

# ── Fly.io / Infrastructure ─────────────────────────
FLY_API_TOKEN = os.environ.get("FLY_API_TOKEN", "")
FLY_APP_NAME = os.environ.get("FLY_APP_NAME", "")
FLY_MACHINE_ID = os.environ.get("FLY_MACHINE_ID", "")
HOSTNAME = os.environ.get("HOSTNAME", "local")

# ── Service Worker ───────────────────────────────────
SW_KILL = os.environ.get("SW_KILL", "0") == "1"

# ── Intelligence auto-fixers ─────────────────────────
AUTO_FIX_ENABLED = os.environ.get("AUTO_FIX_ENABLED", "").lower() in ("true", "1", "yes")
ANALYTICS_EXECUTOR_ENABLED = os.environ.get("ANALYTICS_EXECUTOR_ENABLED", "").lower() in ("true", "1", "yes")

# ── Marketing scheduler ─────────────────────────────
MARKETING_SCHEDULER_ENABLED = os.environ.get("MARKETING_SCHEDULER_ENABLED", "").lower() in ("true", "1", "yes")
MARKETING_LAUNCH_DATE = os.environ.get("MARKETING_LAUNCH_DATE", "")

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

# ── LLM (cloud-first via LiteLLM, local Ollama as fallback) ──
# Cloud providers serve 70B+ open-source models (Llama, Qwen, DeepSeek).
# model_selector.py auto-discovers and benchmarks — these are starting defaults.
# Provider API keys: set GROQ_API_KEY, TOGETHER_API_KEY, FIREWORKS_API_KEY,
# SILICONFLOW_API_KEY, DEEPSEEK_API_KEY, or MISTRAL_API_KEY as needed.

# ── Cloud LLM provider API keys ─────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY", "")
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── AI / ComfyUI ────────────────────────────────────
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://localhost:8188")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── Social media API keys ────────────────────────────
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET", "")

TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
TIKTOK_ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN", "")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD", "")
REDDIT_ALT_USERNAME = os.environ.get("REDDIT_ALT_USERNAME", "")
REDDIT_ALT_PASSWORD = os.environ.get("REDDIT_ALT_PASSWORD", "")

# ── Ollama / LLM ────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

try:
    OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))
except (ValueError, TypeError):
    OLLAMA_TIMEOUT = 60

# Cloud model defaults — override with env vars
_DEFAULT_CLOUD_MODEL = "groq/llama-3.3-70b-versatile"
_DEFAULT_CLOUD_FALLBACK = "together_ai/Qwen/Qwen2.5-72B-Instruct"

# Local Ollama fallback (RAM-based auto-selection for when cloud is unavailable)
_QWEN_TIERS = [
    (8,  "qwen2.5:1.5b"),   # 8GB RAM
    (16, "qwen2.5:7b"),     # 16GB RAM
    (99, "qwen2.5:14b"),    # 32GB+
]

def _auto_select_local_model() -> tuple[str, str]:
    """Pick local Ollama fallback model based on system memory."""
    try:
        import subprocess
        mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
        mem_gb = mem_bytes / (1024 ** 3)
    except Exception:
        mem_gb = 8
    primary = "qwen2.5:1.5b"
    for threshold, model in _QWEN_TIERS:
        if mem_gb <= threshold:
            primary = model
            break
    fallback = "qwen2.5:1.5b"
    for threshold, model in _QWEN_TIERS:
        if model == primary:
            break
        fallback = model
    return primary, fallback

_local_primary, _local_fallback = _auto_select_local_model()

def _has_cloud_api_key() -> bool:
    """Check if any cloud LLM provider API key is configured."""
    _CLOUD_KEY_NAMES = (
        "GROQ_API_KEY", "TOGETHER_API_KEY", "FIREWORKS_API_KEY",
        "SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY",
        "OPENAI_API_KEY",
    )
    return any(os.environ.get(k) for k in _CLOUD_KEY_NAMES)

# Primary model: cloud if any provider key is set, else local Ollama
if os.environ.get("LITELLM_MODEL"):
    LITELLM_MODEL = os.environ["LITELLM_MODEL"]
elif _has_cloud_api_key():
    LITELLM_MODEL = os.environ.get("OLLAMA_MODEL", _DEFAULT_CLOUD_MODEL)
else:
    LITELLM_MODEL = f"ollama/{os.environ.get('OLLAMA_MODEL', _local_primary)}"

# Fallback model
if os.environ.get("LITELLM_FALLBACK"):
    LITELLM_FALLBACK = os.environ["LITELLM_FALLBACK"]
elif _has_cloud_api_key():
    LITELLM_FALLBACK = _DEFAULT_CLOUD_FALLBACK
else:
    LITELLM_FALLBACK = f"ollama/{_local_fallback}"

# Backward-compat: OLLAMA_PRIMARY_MODEL still used by some call sites
OLLAMA_PRIMARY_MODEL = LITELLM_MODEL
OLLAMA_FALLBACK_MODEL = LITELLM_FALLBACK

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

    Cloud OSS models: parses size from name (llama-3.3-70b → 70, Qwen2.5-72B → 72)
    Cloud proprietary: assigns effective capability based on known model families.
    Local models: parses 'qwen2.5:14b' → 14.0
    """
    import re
    name = model_name.lower()

    # Strip provider prefix for matching (groq/, together_ai/, fireworks_ai/, etc.)
    base_name = name.split("/")[-1] if "/" in name else name

    # Check mid/small BEFORE frontier (gpt-4o-mini must not match gpt-4o)
    _CLOUD_SMALL = ("mistral-small", "mistral-tiny")
    if any(f in base_name for f in _CLOUD_SMALL):
        return 5.0

    _CLOUD_MID = ("gpt-4o-mini", "gpt-3.5", "claude-3-haiku", "claude-haiku",
                  "gemini-1.5-flash", "gemini-flash",
                  "deepseek-reasoner")
    if any(f in base_name for f in _CLOUD_MID):
        return 20.0

    # Cloud frontier — capable of everything
    _CLOUD_FRONTIER = ("gpt-4", "claude-3-opus", "claude-3.5-sonnet",
                       "claude-sonnet-4", "claude-opus-4",
                       "gemini-1.5-pro", "gemini-2", "deepseek-r1",
                       "deepseek-v3", "llama-4-maverick")
    if any(f in base_name for f in _CLOUD_FRONTIER):
        return 200.0

    # Mixtral special case: 8x7b = ~47b effective, 8x22b = ~141b
    # Must check BEFORE generic size extraction to avoid matching "7b" in "8x7b"
    if "mixtral" in base_name:
        if "8x22b" in base_name:
            return 141.0
        if "8x7b" in base_name:
            return 47.0

    # Known large cloud models without size in name
    _CLOUD_LARGE = ("mistral-large", "deepseek-chat")
    if any(f in base_name for f in _CLOUD_LARGE):
        return 123.0  # Mistral Large = 123b, DeepSeek Chat ≈ V3

    # Extract explicit size from model name — handles both cloud OSS and local formats:
    # "llama-3.3-70b-versatile" → 70, "Qwen2.5-72B-Instruct" → 72, "qwen2.5:14b" → 14
    match = re.search(r"(\d+(?:\.\d+)?)\s*[bB](?:\b|-)", model_name)
    if match:
        size = float(match.group(1))
        if size > 0:
            return size

    return 7.0  # assume 7b if unparseable


def _is_cloud_model(model_name: str) -> bool:
    """Check if the model routes through a cloud provider (not local Ollama)."""
    name = model_name.lower()
    _CLOUD_PREFIXES = (
        "gpt-", "claude-", "gemini", "anthropic/", "openai/",
        "mistral/", "deepseek", "together_ai/", "groq/",
        "fireworks_ai/", "siliconflow/",
    )
    # Model is cloud if it matches a cloud prefix or doesn't have the ollama/ prefix
    if name.startswith("ollama/"):
        return False
    return any(name.startswith(p) or f"/{p.rstrip('/')}" in name for p in _CLOUD_PREFIXES)


IS_CLOUD_MODEL = _is_cloud_model(LITELLM_MODEL)
MODEL_SIZE_B = _extract_model_size_b(LITELLM_MODEL)

# LLM_ENABLED: true when an LLM is intentionally configured for this environment.
# Defaults to true if a cloud API key is present; false for local dev without Ollama.
# Set LLM_ENABLED=true in production env to ensure health checks fire correctly.
LLM_ENABLED = (
    bool(os.environ.get("LLM_ENABLED", ""))
    or bool(ANTHROPIC_API_KEY)
    or bool(OPENAI_API_KEY)
    or IS_CLOUD_MODEL
)


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
