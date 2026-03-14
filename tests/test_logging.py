"""Tests for centralized logging configuration (log_config.py)."""

import json
import logging
import logging.handlers
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ── utc_now_iso ──────────────────────────────────────────────

def testutc_now_iso_ends_with_z():
    from mandarin.log_config import utc_now_iso
    ts = utc_now_iso()
    assert ts.endswith("Z"), f"Expected trailing Z, got: {ts}"


def testutc_now_iso_format():
    from mandarin.log_config import utc_now_iso
    ts = utc_now_iso()
    # Should match YYYY-MM-DDTHH:MM:SSZ
    assert len(ts) == 20
    assert ts[4] == "-"
    assert ts[7] == "-"
    assert ts[10] == "T"
    assert ts[13] == ":"
    assert ts[16] == ":"


# ── JSONFormatter ──────────────────────────────────────────────

def test_json_formatter_produces_valid_json():
    from mandarin.log_config import JSONFormatter
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger", level=logging.INFO, pathname="", lineno=0,
        msg="hello world", args=(), exc_info=None,
    )
    output = fmt.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["msg"] == "hello world"
    assert parsed["ts"].endswith("Z")


def test_json_formatter_includes_extra_fields():
    from mandarin.log_config import JSONFormatter
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="request", args=(), exc_info=None,
    )
    record.request_method = "GET"
    record.request_path = "/api/test"
    record.status_code = 200
    record.latency_ms = 42.5
    output = fmt.format(record)
    parsed = json.loads(output)
    assert parsed["request_method"] == "GET"
    assert parsed["request_path"] == "/api/test"
    assert parsed["status_code"] == 200
    assert parsed["latency_ms"] == 42.5


def test_json_formatter_includes_exception():
    from mandarin.log_config import JSONFormatter
    import sys
    fmt = JSONFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=0,
        msg="boom", args=(), exc_info=exc_info,
    )
    output = fmt.format(record)
    parsed = json.loads(output)
    assert "exception" in parsed
    assert "ValueError" in parsed["exception"]
    assert "test error" in parsed["exception"]


def test_json_formatter_omits_missing_extras():
    from mandarin.log_config import JSONFormatter
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="simple", args=(), exc_info=None,
    )
    output = fmt.format(record)
    parsed = json.loads(output)
    assert "request_method" not in parsed
    assert "user_id" not in parsed
    assert "exception" not in parsed


# ── configure_logging ──────────────────────────────────────────

def test_configure_logging_cli_installs_handlers():
    from mandarin.log_config import configure_logging
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("mandarin.log_config._DATA_DIR", Path(tmpdir)), \
             patch("mandarin.log_config.APP_LOG", Path(tmpdir) / "app.log"):
            configure_logging(mode="cli")
            root = logging.getLogger()
            handler_types = [type(h) for h in root.handlers]
            assert logging.StreamHandler in handler_types
            assert logging.handlers.RotatingFileHandler in handler_types
            assert root.level == logging.INFO


def test_configure_logging_test_mode():
    from mandarin.log_config import configure_logging
    configure_logging(mode="test")
    root = logging.getLogger()
    assert root.level == logging.WARNING
    # Should not have any RotatingFileHandler
    for h in root.handlers:
        assert not isinstance(h, logging.handlers.RotatingFileHandler)


def test_configure_logging_clears_previous_handlers():
    from mandarin.log_config import configure_logging
    root = logging.getLogger()
    root.addHandler(logging.StreamHandler())
    root.addHandler(logging.StreamHandler())
    initial_count = len(root.handlers)
    configure_logging(mode="test")
    # Should have cleared and added exactly one handler
    assert len(root.handlers) < initial_count or len(root.handlers) == 1


# ── UTCFormatter ──────────────────────────────────────────────

def test_utc_formatter_uses_gmtime():
    from mandarin.log_config import UTCFormatter
    import time
    assert UTCFormatter.converter is time.gmtime


# ── get_rotating_handler ──────────────────────────────────────

def test_get_rotating_handler_creates_handler():
    from mandarin.log_config import get_rotating_handler, JSONFormatter
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.log"
        handler = get_rotating_handler(path)
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert handler.maxBytes == 2 * 1024 * 1024
        assert handler.backupCount == 3
        assert isinstance(handler.formatter, JSONFormatter)
        handler.close()


# ── get_rotating_handler with custom formatter ────────────────

def test_get_rotating_handler_accepts_custom_formatter():
    from mandarin.log_config import get_rotating_handler
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "custom.log"
        raw_fmt = logging.Formatter("%(message)s")
        handler = get_rotating_handler(path, formatter=raw_fmt)
        assert handler.formatter is raw_fmt
        handler.close()


# ── Dedicated log format compatibility ────────────────────────

def test_trace_logger_produces_parseable_jsonl():
    """session_trace.jsonl must produce raw JSON lines (not double-wrapped)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "session_trace.jsonl"
        raw_fmt = logging.Formatter("%(message)s")
        from mandarin.log_config import get_rotating_handler
        handler = get_rotating_handler(trace_path, formatter=raw_fmt)

        test_logger = logging.getLogger("test.trace_format")
        test_logger.handlers.clear()
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)
        test_logger.propagate = False

        entry = {"ts": "2026-02-25T00:00:00Z", "session": 42, "event": "drill_done"}
        test_logger.info("%s", json.dumps(entry))
        handler.flush()

        lines = trace_path.read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        # Must have session/event at top level (not buried in a "msg" field)
        assert parsed["session"] == 42
        assert parsed["event"] == "drill_done"
        assert "msg" not in parsed  # Not double-wrapped
        handler.close()


def test_drill_error_logger_preserves_separator():
    """drill_errors.log must contain '====...' separators for cli.py parser."""
    with tempfile.TemporaryDirectory() as tmpdir:
        err_path = Path(tmpdir) / "drill_errors.log"
        raw_fmt = logging.Formatter("%(message)s")
        from mandarin.log_config import get_rotating_handler
        handler = get_rotating_handler(err_path, formatter=raw_fmt)

        test_logger = logging.getLogger("test.drill_err_format")
        test_logger.handlers.clear()
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)
        test_logger.propagate = False

        test_logger.error(
            "\n%s\n%s  drill_type=%s  item_id=%s\n%s",
            "=" * 60, "2026-02-25T00:00:00Z", "mc", 1, "Traceback...",
        )
        handler.flush()

        content = err_path.read_text()
        assert content.count("=" * 60) == 1
        assert "drill_type=mc" in content
        assert "item_id=1" in content
        handler.close()


def test_configure_logging_idempotent():
    """Calling configure_logging twice should not double handlers."""
    from mandarin.log_config import configure_logging
    configure_logging(mode="test")
    count_after_first = len(logging.getLogger().handlers)
    configure_logging(mode="test")
    count_after_second = len(logging.getLogger().handlers)
    assert count_after_first == count_after_second


# ── dispatch.py uses logger not stderr ────────────────────────

def test_dispatch_validate_uses_logger(caplog):
    """Verify _validate_drill_inputs logs via logger, not stderr."""
    from mandarin.drills.dispatch import _validate_drill_inputs
    item = {"id": 999, "hanzi": "", "pinyin": "", "english": ""}
    with caplog.at_level(logging.WARNING, logger="mandarin.drills.dispatch"):
        _validate_drill_inputs(item, "mc")
    assert any("drill-integrity" in r.message for r in caplog.records)


# ── mc.py uses logger not stderr ──────────────────────────────

def test_mc_module_has_logger():
    """Verify mc.py has a logger attribute (not using print to stderr)."""
    from mandarin.drills import mc
    assert hasattr(mc, "logger")
    assert isinstance(mc.logger, logging.Logger)
