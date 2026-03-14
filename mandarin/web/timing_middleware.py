"""Request timing middleware — samples /api/ route durations."""

import logging
import random
import time

from flask import g, request

logger = logging.getLogger(__name__)

_SAMPLE_RATE_FAST = 0.5   # Record 50% of fast requests (<200ms)
_SAMPLE_RATE_SLOW = 1.0   # Record 100% of slow requests (>=200ms)


def init_timing(app):
    """Register before/after request hooks for timing."""

    @app.before_request
    def _start_timer():
        g.request_start_time = time.monotonic()

    @app.after_request
    def _record_timing(response):
        start = getattr(g, "request_start_time", None)
        if start is None:
            return response

        # Only record /api/ routes (skip static, health checks)
        path = request.path
        if not path.startswith("/api/"):
            return response

        # Skip health check endpoints
        if path in ("/api/health", "/api/ping"):
            return response

        duration_ms = (time.monotonic() - start) * 1000.0

        # Sample: 100% of slow requests, 50% of fast ones
        sample_rate = _SAMPLE_RATE_SLOW if duration_ms >= 200 else _SAMPLE_RATE_FAST
        if random.random() >= sample_rate:
            return response

        try:
            from mandarin import db
            with db.connection() as conn:
                conn.execute(
                    "INSERT INTO request_timing (path, method, status_code, duration_ms) "
                    "VALUES (?, ?, ?, ?)",
                    (path, request.method, response.status_code, duration_ms),
                )
                conn.commit()
        except Exception:
            logger.debug("Failed to record request timing", exc_info=True)

        return response
