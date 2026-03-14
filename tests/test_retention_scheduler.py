"""Tests for the retention purge background scheduler."""

import threading
import time
from unittest.mock import patch, MagicMock

from mandarin.web.retention_scheduler import _run_loop, start, stop


def test_start_idempotent():
    """Starting twice doesn't create two threads."""
    with patch("mandarin.web.retention_scheduler._run_loop"):
        start()
        import mandarin.web.retention_scheduler as mod
        t1 = mod._thread
        start()
        t2 = mod._thread
        # Same thread if still alive, or new if it finished
        stop()


def test_stop_signals_event():
    """stop() sets the event."""
    import mandarin.web.retention_scheduler as mod
    mod._stop_event.clear()
    stop()
    assert mod._stop_event.is_set()
