"""OpenClaw configuration — channel config, timing, agent settings."""

from ..settings import OPENCLAW_SIGNAL_NUMBER, OPENCLAW_TELEGRAM_TOKEN

# Channel configuration
SIGNAL_NUMBER = OPENCLAW_SIGNAL_NUMBER
TELEGRAM_BOT_TOKEN = OPENCLAW_TELEGRAM_TOKEN

# Reminder schedule (hours in user's timezone)
REMINDER_HOURS = [8, 12, 18]

# Review queue debounce (seconds)
REVIEW_QUEUE_DEBOUNCE = 3600  # 1 hour

# Batch review threshold — link to admin panel instead of inline
BATCH_REVIEW_THRESHOLD = 10
