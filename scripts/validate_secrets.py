#!/usr/bin/env python3
"""Validate that all required environment variables are set.

Run in CI or pre-deploy:
    python scripts/validate_secrets.py

Exit code 0 if all required vars are set, 1 if any required are missing.
"""

import os
import sys

# ── Variable definitions by category ────────────────────────────────

CATEGORIES = {
    "Database": {
        "required": [],
        "optional": ["DATA_DIR"],
        "notes": {
            "DATA_DIR": "Defaults to ./data; DB_PATH derived as DATA_DIR/mandarin.db",
        },
    },
    "Auth": {
        "required": ["SECRET_KEY"],
        "optional": [
            "JWT_SECRET",
            "JWT_ACCESS_EXPIRY_HOURS",
            "JWT_REFRESH_EXPIRY_DAYS",
            "SESSION_TIMEOUT_MINUTES",
        ],
        "notes": {
            "SECRET_KEY": "Flask secret key for session signing",
            "JWT_SECRET": "Defaults to SECRET_KEY if unset",
        },
    },
    "Stripe": {
        "required": ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"],
        "optional": [],
        "notes": {
            "STRIPE_SECRET_KEY": "Stripe API secret key (sk_live_... or sk_test_...)",
            "STRIPE_WEBHOOK_SECRET": "Stripe webhook signing secret (whsec_...)",
        },
    },
    "Email": {
        "required": ["RESEND_API_KEY"],
        "optional": [
            "FROM_EMAIL",
            "MAILING_ADDRESS",
            "ADMIN_EMAIL",
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_USER",
            "SMTP_PASSWORD",
            "SMTP_FROM",
        ],
        "notes": {
            "RESEND_API_KEY": "Resend transactional email API key",
        },
    },
    "Sentry": {
        "required": ["SENTRY_DSN"],
        "optional": [],
        "notes": {
            "SENTRY_DSN": "Sentry error monitoring DSN",
        },
    },
    "Push": {
        "required": ["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"],
        "optional": ["VAPID_CLAIMS_EMAIL"],
        "notes": {
            "VAPID_PUBLIC_KEY": "Web push VAPID public key",
            "VAPID_PRIVATE_KEY": "Web push VAPID private key",
        },
    },
    "OpenClaw": {
        "required": [],
        "optional": [
            "OPENCLAW_SIGNAL_NUMBER",
            "OPENCLAW_API_KEY",
            "OPENCLAW_PIPECAT_PORT",
            "OPENCLAW_TELEGRAM_TOKEN",
            "OPENCLAW_TELEGRAM_OWNER_ID",
            "OPENCLAW_WHATSAPP_TOKEN",
            "OPENCLAW_WHATSAPP_PHONE_ID",
            "OPENCLAW_WHATSAPP_VERIFY_TOKEN",
            "OPENCLAW_WHATSAPP_OWNER_NUMBER",
            "OPENCLAW_DISCORD_TOKEN",
            "OPENCLAW_DISCORD_OWNER_ID",
            "OPENCLAW_IMESSAGE_OWNER_ID",
        ],
        "notes": {},
    },
    "MCP": {
        "required": [],
        "optional": [
            "OLLAMA_URL",
            "OLLAMA_MODEL",
            "OLLAMA_FALLBACK_MODEL",
            "OLLAMA_TIMEOUT",
        ],
        "notes": {
            "OLLAMA_URL": "Defaults to http://localhost:11434",
        },
    },
    "Infrastructure": {
        "required": [],
        "optional": [
            "IS_PRODUCTION",
            "BASE_URL",
            "AELU_DOMAIN",
            "AELU_BASE_URL",
            "PORT",
            "FLASK_ENV",
            "PLAUSIBLE_DOMAIN",
            "PLAUSIBLE_SCRIPT_URL",
            "GA4_MEASUREMENT_ID",
            "ALERT_WEBHOOK_URL",
            "OPENAI_API_KEY",
        ],
        "notes": {},
    },
}


def _is_set(name: str) -> bool:
    """A variable is 'set' if it exists in the environment and is non-empty."""
    val = os.environ.get(name, "")
    return val.strip() != ""


def validate(categories: dict | None = None) -> dict:
    """Validate environment variables against the category definitions.

    Returns a dict with:
        - "ok": bool (True if all required vars are set)
        - "missing_required": list of (category, var_name)
        - "set_required": list of (category, var_name)
        - "set_optional": list of (category, var_name)
        - "missing_optional": list of (category, var_name)
    """
    if categories is None:
        categories = CATEGORIES

    missing_required = []
    set_required = []
    set_optional = []
    missing_optional = []

    for cat_name, cat_def in categories.items():
        for var in cat_def.get("required", []):
            if _is_set(var):
                set_required.append((cat_name, var))
            else:
                missing_required.append((cat_name, var))
        for var in cat_def.get("optional", []):
            if _is_set(var):
                set_optional.append((cat_name, var))
            else:
                missing_optional.append((cat_name, var))

    return {
        "ok": len(missing_required) == 0,
        "missing_required": missing_required,
        "set_required": set_required,
        "set_optional": set_optional,
        "missing_optional": missing_optional,
    }


def _print_report(result: dict) -> None:
    """Print a human-readable report to stdout."""
    print("=" * 60)
    print("  Aelu Secrets Validation Report")
    print("=" * 60)

    # Group by category for display
    all_categories = {}
    for cat, var in result["set_required"]:
        all_categories.setdefault(cat, []).append(("required", var, True))
    for cat, var in result["missing_required"]:
        all_categories.setdefault(cat, []).append(("required", var, False))
    for cat, var in result["set_optional"]:
        all_categories.setdefault(cat, []).append(("optional", var, True))
    for cat, var in result["missing_optional"]:
        all_categories.setdefault(cat, []).append(("optional", var, False))

    # Print in definition order
    for cat_name in CATEGORIES:
        if cat_name not in all_categories:
            continue
        entries = all_categories[cat_name]
        print(f"\n  [{cat_name}]")
        for kind, var, is_set in entries:
            if is_set:
                icon = "OK"
            elif kind == "required":
                icon = "MISSING"
            else:
                icon = "-- "
            tag = f"({kind})" if kind == "optional" else ""
            print(f"    {icon:>7}  {var} {tag}")

    print()
    print("-" * 60)
    req_total = len(result["set_required"]) + len(result["missing_required"])
    req_set = len(result["set_required"])
    print(f"  Required: {req_set}/{req_total} set")
    print(f"  Optional: {len(result['set_optional'])} set, "
          f"{len(result['missing_optional'])} unset")

    if result["ok"]:
        print("\n  Result: PASS -- all required variables are set.")
    else:
        print(f"\n  Result: FAIL -- {len(result['missing_required'])} "
              f"required variable(s) missing:")
        for cat, var in result["missing_required"]:
            print(f"    - {var} ({cat})")

    print("=" * 60)


def main() -> int:
    """Run validation and return exit code (0=pass, 1=fail)."""
    result = validate()
    _print_report(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
