"""OpenClaw — autonomous operations layer for Aelu.

Messaging bots:
- telegram_bot: Telegram bot with owner-only auth
- whatsapp_bot: WhatsApp via Meta Cloud API (webhook-based)
- discord_bot: Discord bot with !commands + natural language DMs
- imessage_bot: iMessage via AppleScript (macOS only, zero deps)
- voice_agent: Pipecat real-time voice pipeline (admin + tone practice)

Core infrastructure:
- commands: Pure-function wrappers for MCP tools
- llm_handler: Intent classification via Ollama (keyword fallback)
- security: Prompt injection defense, rate limiting, audit trail
- config: Shared configuration

MCP integrations:
- mcp_server: MCP server (25 tools) — Aelu's learner model as a first-class MCP resource
- stripe_mcp: Stripe payment management (subscription, payments, refunds)
- supabase_mcp: Supabase migration preparation (schema, integrity, export)
- email_mcp: Teacher communication (weekly summaries, class reports, SMTP fallback)

Business automation:
- support_agent: Customer support (FAQ matching, DB troubleshooting, escalation routing)
- onboarding_agent: Adaptive onboarding + churn prevention (lifecycle detection, risk signals)
- changelog_agent: Automated release notes from git commits
- seo_agent: Content marketing (keyword research, blog drafting, SEO metadata)
- directory_agent: App store/directory listing (30+ directories, copy generation, tracking)
- financial_monitor: Revenue metrics, churn analysis, payment anomaly detection
- compliance_monitor: AI regulatory monitoring (EU AI Act, GDPR, FERPA, COPPA, 10 surfaces)
"""

import logging

_logger = logging.getLogger(__name__)


def notify_owner(message: str) -> bool:
    """Send a proactive notification to the product owner via the best available channel.

    Tries channels in priority order: Matrix/Beeper → iMessage → Telegram → Discord.
    Returns True if any channel delivered successfully.
    """
    # Try Matrix/Beeper first (delivers to iMessage via Beeper bridge)
    try:
        from ..notifications.matrix_client import send_notification, _is_configured
        if _is_configured():
            if send_notification(message):
                return True
    except (ImportError, Exception):
        pass

    # Try iMessage directly (macOS only, zero deps)
    try:
        from .imessage_bot import send_to_owner
        if send_to_owner(message):
            return True
    except (ImportError, Exception):
        pass

    # Try Telegram
    try:
        from .telegram_bot import send_telegram_notification
        if send_telegram_notification(message):
            return True
    except (ImportError, Exception):
        pass

    # Try Discord
    try:
        from .discord_bot import send_discord_notification
        if send_discord_notification(message):
            return True
    except (ImportError, Exception):
        pass

    _logger.debug("notify_owner: no channel available for message: %s", message[:100])
    return False
