"""Centralized logging configuration for Aelu.

Provides UTC-consistent formatters, JSON structured logging, and
rotating file handlers.  All entry points call configure_logging()
once at startup; individual modules just use logging.getLogger(__name__).
"""

import json
import logging
import logging.handlers
import time
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Canonical log paths — importable by any module that needs them
DRILL_ERROR_LOG = _DATA_DIR / "drill_errors.log"
SESSION_TRACE_LOG = _DATA_DIR / "session_trace.jsonl"
CRASH_LOG = _DATA_DIR / "crash.log"
APP_LOG = _DATA_DIR / "app.log"


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 with trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UTCFormatter(logging.Formatter):
    """Logging formatter that always uses UTC timestamps."""
    converter = time.gmtime


class JSONFormatter(logging.Formatter):
    """Structured JSON-line formatter for log aggregation.

    Always emits: ts, level, logger, msg.
    Includes optional extra fields when present on the record.
    Includes exception tracebacks when exc_info is set.
    """

    _EXTRA_FIELDS = (
        "request_method", "request_path", "status_code",
        "latency_ms", "user_id", "drill_type", "item_id",
    )

    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in self._EXTRA_FIELDS:
            val = getattr(record, field, None)
            if val is not None:
                entry[field] = val
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def get_rotating_handler(path: Path, formatter=None) -> logging.handlers.RotatingFileHandler:
    """Create a RotatingFileHandler (2 MB, 3 backups).

    Uses JSONFormatter by default.  Pass formatter=<instance> to override
    (e.g. for dedicated log files that format their own content).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        str(path), maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(formatter or JSONFormatter())
    return handler


def configure_logging(mode: str = "cli") -> None:
    """Set up root logger for the given entry-point mode.

    Modes:
        cli  — stderr console (UTCFormatter) + rotating file (JSONFormatter)
        web  — same as cli + JSON stdout in production
        test — WARNING level, no file handlers
    """
    root = logging.getLogger()

    # Clear any existing handlers (safe to call multiple times)
    root.handlers.clear()

    if mode == "test":
        root.setLevel(logging.WARNING)
        handler = logging.StreamHandler()
        handler.setFormatter(UTCFormatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
        root.addHandler(handler)
        return

    root.setLevel(logging.INFO)

    # Console (stderr) — human-readable, UTC
    console = logging.StreamHandler()
    console.setFormatter(UTCFormatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    root.addHandler(console)

    # Rotating app.log — structured JSON
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    root.addHandler(get_rotating_handler(APP_LOG))

    # Rotating crash.log — ERROR+ only (server crashes, unhandled exceptions)
    crash_handler = get_rotating_handler(CRASH_LOG)
    crash_handler.setLevel(logging.ERROR)
    root.addHandler(crash_handler)

    if mode == "web":
        from .settings import FLASK_ENV, IS_PRODUCTION
        is_prod = FLASK_ENV == "production" or IS_PRODUCTION
        if is_prod:
            import sys
            stdout_handler = logging.StreamHandler(sys.stdout)
            stdout_handler.setFormatter(JSONFormatter())
            root.addHandler(stdout_handler)
