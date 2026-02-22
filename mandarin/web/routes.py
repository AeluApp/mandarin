"""Flask routes — pages + WebSocket session endpoint."""

import csv
import io
import json
import logging
import os
import sqlite3
import threading
from datetime import date as dt_date, timedelta

import secrets as _secrets
from flask import render_template, jsonify, request, Response, send_from_directory, abort, redirect, url_for, g
from flask_login import current_user, login_required
from flask_sock import Sock
from simple_websocket import ConnectionClosed

from .. import db
from ..settings import IS_PRODUCTION, BASE_URL
from ..tier_gate import check_tier_access, check_session_limit
from ..display import STAGE_LABELS
from ..audio import get_audio_cache_dir
from ..scheduler import plan_standard_session, plan_minimal_session, get_day_profile
from ..runner import run_session
from .bridge import WebBridge
from .session_store import session_store, RESUME_TIMEOUT
from .api_errors import api_error_handler

logger = logging.getLogger(__name__)


def _ws_listen_loop(ws, bridge, session_thread, *, close_on_disconnect=True):
    """Receive answers from the browser until the session thread ends.

    If close_on_disconnect=False, a dropped WS marks the bridge as
    disconnected (resumable) rather than closed (terminal).
    """
    while session_thread.is_alive():
        try:
            raw = ws.receive(timeout=1)
            if raw is None:
                if not session_thread.is_alive():
                    break
                continue
            data = json.loads(raw)
            if data.get("type") == "answer":
                logger.debug("[%s] answer received: %r", bridge.session_uuid, data.get("value", ""))
                bridge.receive_answer(data.get("value", ""))
            elif data.get("type") == "audio_data":
                logger.debug("[%s] audio data received (%s bytes, transcript=%s)",
                           bridge.session_uuid,
                           len(data.get("data", "") or "") if data.get("data") else "null",
                           repr(data.get("transcript", "")[:30]) if data.get("transcript") else "null")
                bridge.receive_audio_data(data.get("data"), data.get("transcript"))
        except ConnectionClosed:
            logger.info("[%s] connection closed by client", bridge.session_uuid)
            if close_on_disconnect:
                bridge.close()
            else:
                bridge.disconnect()
            break
        except TimeoutError:
            if not session_thread.is_alive():
                break
            continue
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("[%s] listen loop error: %s", bridge.session_uuid, e)
            if close_on_disconnect:
                bridge.close()
            else:
                bridge.disconnect()
            break
    if not session_thread.is_alive():
        session_thread.join(timeout=5)
    logger.debug("[%s] listen loop ended", bridge.session_uuid)


def _sanitize_error(e: Exception) -> str:
    """Convert an exception to a user-friendly message.

    Never expose stack traces or internal details to the browser.
    """
    msg = str(e)
    # Common errors with friendly messages
    if "no such table" in msg:
        return "Database needs setup. Run: ./run add-hsk 1"
    if "database is locked" in msg:
        return "Database is busy. Try again in a moment."
    if "no drills" in msg.lower() or "no items" in msg.lower():
        return "No items available for drilling. Import some content first."
    # Generic fallback — never show raw exception
    logger.error("session error (sanitized): %s", msg)
    return "Something went wrong. Reload to try again."


# Per-user session locks: {user_id: (Lock, Thread or None)}
_user_locks: dict = {}
_lock_guard = threading.Lock()


def _get_user_lock(user_id: int):
    """Get or create a per-user session lock. Returns (Lock, thread_or_None)."""
    with _lock_guard:
        if user_id not in _user_locks:
            _user_locks[user_id] = (threading.Lock(), None)
        return _user_locks[user_id]


def _set_user_thread(user_id: int, thread):
    """Set the active session thread for a user."""
    with _lock_guard:
        lock, _ = _user_locks.get(user_id, (threading.Lock(), None))
        _user_locks[user_id] = (lock, thread)


def _compute_streak(conn) -> int:
    """Count consecutive days with completed sessions, ending today or yesterday."""
    rows = conn.execute("""
        SELECT DISTINCT date(started_at) as d
        FROM session_log
        WHERE items_completed > 0
        ORDER BY d DESC
    """).fetchall()
    if not rows:
        return 0
    dates = []
    for r in rows:
        try:
            dates.append(dt_date.fromisoformat(r["d"]))
        except (ValueError, TypeError):
            pass
    if not dates:
        return 0
    today = dt_date.today()
    # Streak must start from today or yesterday
    if dates[0] < today - timedelta(days=1):
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if (dates[i - 1] - dates[i]).days == 1:
            streak += 1
        else:
            break
    return streak


def _get_user_id():
    """Get user_id from current_user. Aborts 401 if unauthenticated."""
    if current_user.is_authenticated:
        return current_user.id
    abort(401)


# Routes that don't require authentication
_PUBLIC_PREFIXES = ("/auth/", "/api/health", "/api/health/live", "/api/health/ready", "/api/webhook/", "/api/auth/token", "/static/")

# Landing-page paths served to unauthenticated visitors
_LANDING_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "marketing", "landing"))


def register_routes(app):
    """Register all routes on the Flask app."""
    sock = Sock(app)

    @app.before_request
    def _generate_csp_nonce():
        """Generate a per-request CSP nonce for inline style blocks."""
        g.csp_nonce = _secrets.token_urlsafe(16)

    @app.before_request
    def require_auth():
        """Redirect unauthenticated users to login for protected routes.

        Landing-page blueprint routes and the root "/" are public —
        unauthenticated visitors see marketing content.
        """
        path = request.path
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return None
        # Allow landing blueprint routes (and root "/") through for everyone
        if request.endpoint and request.endpoint.startswith("landing."):
            return None
        # Root "/" is handled by index() which checks auth itself
        if path == "/":
            return None
        if not current_user.is_authenticated:
            if request.is_json or path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login", next=request.url))
        return None

    @app.after_request
    def set_security_headers(response):
        # Prevent PWA/webview from caching HTML — ensures fresh assets on restart
        if response.content_type and 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        # Long-lived cache for static assets (content-hash busted)
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        # Prevent caching of authenticated API responses (Zero Trust: no data leakage)
        elif request.path.startswith('/api/') and response.status_code == 200:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response.headers['Pragma'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), geolocation=(), payment=(self), microphone=(self)'
        if IS_PRODUCTION:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        nonce = getattr(g, 'csp_nonce', '')
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' https://plausible.io; "
            f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "media-src 'self'; "
            "connect-src 'self' ws: wss:; "
            "worker-src 'self'; "
            "frame-ancestors 'none'"
        )
        return response

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get('Origin', '')
        if IS_PRODUCTION:
            # Production: only allow the configured base URL origin
            if origin and origin.rstrip('/') == BASE_URL.rstrip('/'):
                response.headers['Access-Control-Allow-Origin'] = origin
        else:
            # Dev: allow localhost origins (any port)
            if origin and any(origin.startswith(scheme) for scheme in (
                'http://localhost:', 'http://127.0.0.1:',
                'https://localhost:', 'https://127.0.0.1:',
                'tauri://localhost',
            )):
                response.headers['Access-Control-Allow-Origin'] = origin
            else:
                response.headers['Access-Control-Allow-Origin'] = f'http://localhost:{request.host.split(":")[-1]}'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.route("/")
    def index():
        """Main page — landing for visitors, dashboard for authenticated users."""
        if not current_user.is_authenticated:
            return send_from_directory(_LANDING_DIR, "index.html")
        user_id = _get_user_id()
        with db.connection() as conn:
            profile = db.get_profile(conn, user_id=user_id)
            item_count = db.content_count(conn)

            day_profile = get_day_profile(conn)

            # HSK mastery
            mastery = db.get_mastery_by_hsk(conn, user_id=user_id)

            # Recent sessions
            sessions = db.get_session_history(conn, limit=5, user_id=user_id)

            # Error summary
            errors = db.get_error_summary(conn)

            # Streak
            streak_days = _compute_streak(conn)

            # Accuracy trend for last 10 sessions (sparkline in template)
            trend_sessions = db.get_session_history(conn, limit=10, user_id=user_id)
            accuracy_trend = []
            for s in reversed(trend_sessions):  # oldest first
                total = s.get("items_completed") or 0
                correct = s.get("items_correct") or 0
                pct = round(correct / total * 100) if total > 0 else 0
                accuracy_trend.append(pct)

            # Pre-compute sparkline string server-side for template
            spark_chars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
            accuracy_sparkline = ""
            for pct in accuracy_trend:
                idx = min(7, max(0, round(pct / 100 * 7)))
                accuracy_sparkline += spark_chars[idx]

            return render_template("index.html",
                                   profile=profile,
                                   item_count=item_count,
                                   day_profile=day_profile,
                                   mastery=mastery,
                                   sessions=sessions,
                                   errors=errors,
                                   streak_days=streak_days,
                                   accuracy_trend=accuracy_trend,
                                   accuracy_sparkline=accuracy_sparkline,
                                   stage_labels=STAGE_LABELS)

    @app.route("/api/status")
    def api_status():
        """JSON status endpoint."""
        user_id = _get_user_id()
        with db.connection() as conn:
            profile = db.get_profile(conn, user_id=user_id)
            item_count = db.content_count(conn)
            days_gap = db.get_days_since_last_session(conn)
            mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
            items_due = db.get_items_due_count(conn)
            return jsonify({
                "item_count": item_count,
                "total_sessions": profile.get("total_sessions") or 0,
                "days_since_last": days_gap,
                "items_due": items_due,
                "mastery": {str(k): v for k, v in mastery.items()} if mastery else {},
            })

    # ── SRE Health Endpoints ──────────────────────────────────────────
    # /api/health       — full readiness check (DB + schema)
    # /api/health/live  — liveness probe (process alive, no dependency check)
    # /api/health/ready — readiness probe (DB writable, schema valid)
    #
    # SLI: health check latency measured on every call; >500ms = degraded.
    # SLO target: 99.5% of /api/health responses < 500ms over 30-day window.

    @app.route("/api/health/live")
    def api_health_live():
        """Liveness probe — process is alive, no dependency checks.

        Use for Fly.io/Kubernetes liveness probes. A failure here means
        the process should be restarted.
        """
        from ..web import _SERVER_START_TIME
        import time as _time
        uptime_seconds = int(_time.time()) - int(_SERVER_START_TIME)
        return jsonify({"status": "ok", "uptime_seconds": uptime_seconds})

    @app.route("/api/health/ready")
    def api_health_ready():
        """Readiness probe — DB writable, schema current.

        Use for Fly.io/Kubernetes readiness probes. A failure here means
        traffic should be routed away until the issue is resolved.
        """
        import time as _time
        t0 = _time.monotonic()
        try:
            with db.connection() as conn:
                # Verify DB is writable (not just readable)
                conn.execute("SELECT 1")
                from ..db.core import _get_schema_version, SCHEMA_VERSION
                schema_version = _get_schema_version(conn)
                if schema_version < SCHEMA_VERSION:
                    elapsed_ms = round((_time.monotonic() - t0) * 1000, 1)
                    return jsonify({
                        "status": "not_ready",
                        "reason": f"schema migration pending: v{schema_version} → v{SCHEMA_VERSION}",
                        "latency_ms": elapsed_ms,
                    }), 503
                elapsed_ms = round((_time.monotonic() - t0) * 1000, 1)
                return jsonify({"status": "ok", "latency_ms": elapsed_ms})
        except (sqlite3.Error, OSError) as e:
            elapsed_ms = round((_time.monotonic() - t0) * 1000, 1)
            logger.error("readiness check failed: %s", e)
            return jsonify({"status": "not_ready", "reason": _sanitize_error(e), "latency_ms": elapsed_ms}), 503

    @app.route("/api/health")
    def api_health():
        """Full health check — DB connectivity, schema, content stats.

        SLI: response latency. SLO target: p95 < 500ms.
        """
        import time as _time
        t0 = _time.monotonic()
        try:
            with db.connection() as conn:
                # Verify core tables exist
                tables = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()}
                required = {"learner_profile", "content_item", "progress", "session_log", "error_log"}
                missing = required - tables
                item_count = db.content_count(conn)
                from ..db.core import _get_schema_version, SCHEMA_VERSION
                schema_version = _get_schema_version(conn)
                elapsed_ms = round((_time.monotonic() - t0) * 1000, 1)

                if missing:
                    return jsonify({
                        "error": "Database schema incomplete — missing tables: " + ", ".join(sorted(missing)),
                        "missing_tables": list(missing),
                        "schema_version": schema_version,
                        "latency_ms": elapsed_ms,
                    }), 503

                from ..web import _SERVER_START_TIME
                uptime_seconds = int(_time.time()) - int(_SERVER_START_TIME)

                return jsonify({
                    "status": "ok",
                    "schema_version": schema_version,
                    "schema_current": schema_version >= SCHEMA_VERSION,
                    "item_count": item_count,
                    "tables": len(tables),
                    "uptime_seconds": uptime_seconds,
                    "latency_ms": elapsed_ms,
                })
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            elapsed_ms = round((_time.monotonic() - t0) * 1000, 1)
            logger.error("health check failed: %s", e)
            return jsonify({"error": _sanitize_error(e), "latency_ms": elapsed_ms}), 503

    @app.route("/api/forecast")
    @api_error_handler("Forecast")
    def api_forecast():
        """JSON forecast — pace, milestones, HSK projections."""
        with db.connection() as conn:
            from ..diagnostics import project_forecast
            forecast = project_forecast(conn)
            return jsonify(forecast)

    @app.route("/api/progress")
    @api_error_handler("Progress")
    def api_progress():
        """JSON progress — retention stats + mastery by HSK."""
        user_id = _get_user_id()
        with db.connection() as conn:
            mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
            mastery_json = {str(k): v for k, v in mastery.items()} if mastery else {}

            retention = {}
            try:
                from ..retention import compute_retention_stats
                retention = compute_retention_stats(conn)
            except (ImportError, sqlite3.Error, KeyError, TypeError) as e:
                logger.debug("retention stats unavailable: %s", e)

            return jsonify({
                "mastery": mastery_json,
                "retention": retention,
            })

    @app.route("/api/diagnostics")
    @api_error_handler("Diagnostics")
    def api_diagnostics():
        """JSON diagnostics — quick assessment."""
        with db.connection() as conn:
            from ..diagnostics import assess_quick
            result = assess_quick(conn)
            return jsonify(result)

    @app.route("/api/personalization")
    @api_error_handler("Personalization")
    def api_personalization():
        """JSON — personalization domains and current preference."""
        user_id = _get_user_id()
        with db.connection() as conn:
            from ..personalization import INTEREST_DOMAINS, get_available_domains, get_domain_stats
            profile = db.get_profile(conn, user_id=user_id)
            current = (profile.get("preferred_domains") or "").strip()
            available = get_available_domains()
            stats = get_domain_stats()

            domains = {}
            for key, meta in INTEREST_DOMAINS.items():
                domains[key] = {
                    "label": meta["label"],
                    "description": meta["description"],
                    "active": key in current.split(",") if current else False,
                    "available": key in available,
                    "sentence_count": stats.get(key, {}).get("total", 0),
                }
            return jsonify({
                "preferred_domains": current,
                "domains": domains,
            })

    @app.route("/api/sessions")
    @api_error_handler("Sessions")
    def api_sessions():
        """JSON — last 20 sessions with scores + 14-day study streak data."""
        user_id = _get_user_id()
        with db.connection() as conn:
            sessions = db.get_session_history(conn, limit=20, user_id=user_id)
            result = []
            for s in sessions:
                result.append({
                    "id": s["id"],
                    "started_at": s.get("started_at"),
                    "session_type": s.get("session_type"),
                    "items_completed": s.get("items_completed") or 0,
                    "items_correct": s.get("items_correct") or 0,
                    "early_exit": bool(s.get("early_exit")),
                    "duration_seconds": s.get("duration_seconds"),
                })

            # 14-day study frequency data
            today = dt_date.today()
            streak_data = []
            day_counts = {}
            rows = conn.execute("""
                SELECT date(started_at) as d, COUNT(*) as cnt
                FROM session_log
                WHERE started_at >= date('now', '-13 days')
                  AND items_completed > 0
                GROUP BY date(started_at)
            """).fetchall()
            for r in rows:
                day_counts[r["d"]] = r["cnt"]
            for i in range(13, -1, -1):
                d = today - timedelta(days=i)
                d_str = d.isoformat()
                streak_data.append({
                    "date": d_str,
                    "sessions": day_counts.get(d_str, 0),
                })

            return jsonify({"sessions": result, "study_streak_data": streak_data})

    # ── CSV export endpoints ──────────────────────────────

    def _csv_response(export_fn, label):
        """Helper to generate CSV download responses using shared export module."""
        from ..export import to_csv_string
        try:
            with db.connection() as conn:
                header, data = export_fn(conn)
            csv_text = to_csv_string(header, data)
            filename = f"mandarin_{label}_{dt_date.today().isoformat()}.csv"
            return Response(
                csv_text,
                mimetype="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("export %s error: %s", label, e)
            return jsonify({"error": "Export failed"}), 500

    @app.route("/api/export/progress")
    def export_progress():
        """Download progress data as CSV."""
        from ..export import export_progress_csv
        return _csv_response(export_progress_csv, "progress")

    @app.route("/api/export/sessions")
    def export_sessions():
        """Download session history as CSV."""
        from ..export import export_sessions_csv
        return _csv_response(export_sessions_csv, "sessions")

    @app.route("/api/export/errors")
    def export_errors():
        """Download error log as CSV."""
        from ..export import export_errors_csv
        return _csv_response(export_errors_csv, "errors")

    @app.route("/api/audio/<filename>")
    def serve_audio(filename):
        """Serve generated TTS audio files."""
        # Sanitize: only allow alnum + dot + dash
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+\.aiff$', filename):
            abort(404)
        cache_dir = get_audio_cache_dir()
        return send_from_directory(cache_dir, filename, mimetype="audio/aiff")

    def _handle_ws_session(ws, planner_fn, label):
        """Shared WebSocket session handler for both full and mini sessions.

        Handles resume-token protocol, session acquisition, thread management,
        and the listen loop. Only the planner function differs.
        """
        # Auth check — WebSocket upgrade carries session cookies
        if not current_user.is_authenticated:
            try:
                ws.send(json.dumps({"type": "error", "message": "Authentication required"}))
                ws.close()
            except (ConnectionClosed, OSError):
                pass
            return

        user_id = current_user.id
        user_lock, _ = _get_user_lock(user_id)

        # Check for resume token in first message (short timeout — client
        # sends immediately on connect if it has one, otherwise sends "new")
        try:
            first_raw = ws.receive(timeout=0.5)
        except (ConnectionClosed, TimeoutError, OSError):
            first_raw = None
        first_data = {}
        if first_raw:
            try:
                first_data = json.loads(first_raw)
            except (json.JSONDecodeError, TypeError):
                pass

        # ── Resume path ──────────────────────────────────────
        if first_data.get("type") == "resume" and first_data.get("resume_token"):
            token = first_data["resume_token"]
            # Atomic claim: prevents two WS connections from racing to resume
            active = session_store.claim_for_resume(token, user_id)
            if active:
                logger.info("[%s] resuming %s via token %s", active.bridge.session_uuid, label, token)
                try:
                    active.bridge.swap_ws(ws)
                    session_store.release_claim(token)
                    active.bridge._send({"type": "session_init", "resume_token": token, "resumed": True})
                    _ws_listen_loop(ws, active.bridge, active.session_thread, close_on_disconnect=False)
                    if active.session_thread.is_alive():
                        active.bridge.disconnect()
                except (ConnectionClosed, OSError, ConnectionError) as e:
                    logger.exception("%s resume path error for token %s: %s", label, token, e)
                    session_store.release_claim(token)
                finally:
                    if not active.session_thread.is_alive():
                        session_store.remove(token)
                        _set_user_thread(user_id, None)
                        try:
                            user_lock.release()
                        except RuntimeError:
                            pass
                return
            else:
                logger.info("resume token %s not found or session dead, starting new %s", token, label)
                session_store.remove(token)
                # Fall through to new session

        # ── Tier gate: check session limit ────────────────────
        try:
            with db.connection() as gate_conn:
                if not check_session_limit(gate_conn, user_id):
                    bridge = WebBridge(ws)
                    bridge.send_error("Daily session limit reached. Upgrade for unlimited sessions.")
                    return
        except Exception as e:
            logger.warning("Tier gate check failed (allowing): %s", e)

        # ── New session path ─────────────────────────────────
        if not user_lock.acquire(blocking=False):
            # Check if the lock is stale (held by a dead thread)
            _, stale_thread = _get_user_lock(user_id)
            if stale_thread is not None and not stale_thread.is_alive():
                logger.warning("%s user %d: stale lock detected (thread dead), force-releasing", label, user_id)
                session_store.cleanup_expired()
                try:
                    user_lock.release()
                except RuntimeError:
                    pass
                if not user_lock.acquire(blocking=False):
                    logger.warning("%s rejected for user %d: lock still held after force-release", label, user_id)
                    bridge = WebBridge(ws)
                    bridge.send_error("You already have a session running. Close it first.")
                    return
            else:
                logger.warning("%s rejected for user %d: session already active", label, user_id)
                bridge = WebBridge(ws)
                bridge.send_error("You already have a session running. Close it first.")
                return
        bridge = WebBridge(ws)
        has_mic = request.args.get('mic', '1') != '0'
        resume_token = bridge.session_uuid
        logger.info("[%s] %s WS connected user=%d (mic=%s)", bridge.session_uuid, label, user_id, has_mic)
        bridge.show_fn(f"[dim]session {bridge.session_uuid}[/dim]")
        bridge._send({"type": "session_init", "resume_token": resume_token})

        def _run():
            logger.info("[%s] %s thread started user=%d", bridge.session_uuid, label, user_id)
            # Redirect audio playback to browser instead of Mac speakers
            from ..audio import set_web_audio_callback, clear_web_audio_callback
            def _on_audio(fname):
                bridge._send({"type": "audio_play", "url": f"/api/audio/{fname}"})
            set_web_audio_callback(_on_audio)

            # Redirect recording to browser microphone
            from ..tone_grading import set_web_recording_callback, clear_web_recording_callback
            def _on_record(duration):
                return bridge.request_recording(duration)
            set_web_recording_callback(_on_record, has_mic=has_mic)

            try:
                with db.connection() as conn:
                    plan = planner_fn(conn, user_id=user_id)
                    logger.info("[%s] %s planned: %d drills", bridge.session_uuid, label, len(plan.drills))
                    state = run_session(conn, plan, bridge.show_fn, bridge.input_fn, user_id=user_id)
                    bridge.send_done({
                        "items_completed": state.items_completed,
                        "items_correct": state.items_correct,
                        "early_exit": state.early_exit,
                    })
                    logger.info("[%s] %s complete: %d/%d", bridge.session_uuid, label, state.items_correct, state.items_completed)
            except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
                logger.error("[%s] %s error: %s", bridge.session_uuid, label, e)
                bridge.send_error(_sanitize_error(e))
            finally:
                clear_web_audio_callback()
                clear_web_recording_callback()

        try:
            session_thread = threading.Thread(target=_run, daemon=True)
            session_thread.start()
            _set_user_thread(user_id, session_thread)
            session_store.register(resume_token, bridge, session_thread, user_id=user_id)
            _ws_listen_loop(ws, bridge, session_thread, close_on_disconnect=False)
            logger.info("[%s] %s WS handler exiting", bridge.session_uuid, label)
            if session_thread.is_alive():
                bridge.disconnect()
                session_thread.join(timeout=RESUME_TIMEOUT + 5)
            session_store.remove(resume_token)
        finally:
            if not session_thread.is_alive():
                bridge.close()
            _set_user_thread(user_id, None)
            try:
                user_lock.release()
            except RuntimeError:
                pass

    # ── Reading / Graded Reader endpoints ──────────────────

    @app.route("/api/reading/passages")
    def api_reading_passages():
        """Return reading passages, optionally filtered by HSK level."""
        try:
            user_id = _get_user_id()
            with db.connection() as gate_conn:
                if not check_tier_access(gate_conn, user_id, "reading"):
                    return jsonify({"error": "upgrade_required", "feature": "reading"}), 403
            from ..media import load_reading_passages
            hsk_level = request.args.get("hsk_level", type=int)
            passages = load_reading_passages(hsk_level)
            result = []
            for p in passages:
                result.append({
                    "id": p.get("id"),
                    "title": p.get("title", ""),
                    "title_zh": p.get("title_zh", ""),
                    "hsk_level": p.get("hsk_level", 1),
                })
            return jsonify({"passages": result})
        except (OSError, KeyError, TypeError) as e:
            logger.error("reading passages API error: %s", e)
            return jsonify({"error": "Passages unavailable"}), 500

    @app.route("/api/reading/passage/<passage_id>")
    def api_reading_passage(passage_id):
        """Return a single passage with full text and glosses."""
        try:
            from ..media import load_reading_passages
            passages = load_reading_passages()
            passage = next((p for p in passages if p.get("id") == passage_id), None)
            if not passage:
                return jsonify({"error": "Passage not found"}), 404
            return jsonify(passage)
        except (OSError, KeyError, TypeError) as e:
            logger.error("reading passage API error: %s", e)
            return jsonify({"error": "Passage unavailable"}), 500

    @app.route("/api/reading/lookup", methods=["POST"])
    def api_reading_lookup():
        """Look up a word during reading. Logs a vocab_encounter and returns definition."""
        try:
            data = request.get_json(force=True)
            hanzi = (data.get("hanzi") or "").strip()
            passage_id = data.get("passage_id", "")
            if not hanzi:
                return jsonify({"error": "hanzi required"}), 400

            with db.connection() as conn:
                # Look up definition from content_item
                row = conn.execute(
                    "SELECT id, pinyin, english FROM content_item WHERE hanzi = ? LIMIT 1",
                    (hanzi,)
                ).fetchone()
                content_item_id = row["id"] if row else None
                pinyin = row["pinyin"] if row else ""
                english = row["english"] if row else ""

                # Log the encounter
                conn.execute(
                    """INSERT INTO vocab_encounter
                       (content_item_id, hanzi, source_type, source_id, looked_up)
                       VALUES (?, ?, 'reading', ?, 1)""",
                    (content_item_id, hanzi, passage_id)
                )
                conn.commit()

                return jsonify({
                    "hanzi": hanzi,
                    "pinyin": pinyin,
                    "english": english,
                    "found": row is not None,
                })
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("reading lookup API error: %s", e)
            return jsonify({"error": "Lookup failed"}), 500

    # ── Media Shelf endpoints ──────────────────────────────

    @app.route("/api/media/recommendations")
    def api_media_recommendations():
        """Return media recommendations."""
        try:
            user_id = _get_user_id()
            with db.connection() as gate_conn:
                if not check_tier_access(gate_conn, user_id, "media"):
                    return jsonify({"error": "upgrade_required", "feature": "media"}), 403
            from ..media import recommend_media, record_media_presentation
            limit = request.args.get("limit", 6, type=int)
            with db.connection() as conn:
                recs = recommend_media(conn, limit=limit)
                result = []
                for entry, watch in recs:
                    record_media_presentation(conn, entry.get("id", ""))
                    has_quiz = bool(entry.get("questions"))
                    result.append({
                        "id": entry.get("id"),
                        "title": entry.get("title", ""),
                        "hsk_level": entry.get("hsk_level", 1),
                        "media_type": entry.get("media_type", ""),
                        "cost": entry.get("cost", "free"),
                        "content_lenses": entry.get("content_lenses", []),
                        "segment": entry.get("segment", {}),
                        "where_to_find": entry.get("where_to_find", ""),
                        "cultural_note": entry.get("cultural_note", ""),
                        "times_watched": watch.get("times_watched") or 0,
                        "avg_score": watch.get("avg_score"),
                        "liked": watch.get("liked"),
                        "has_quiz": has_quiz,
                    })
                return jsonify({"recommendations": result})
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("media recommendations API error: %s", e)
            return jsonify({"error": "Recommendations unavailable"}), 500

    @app.route("/api/media/history")
    @api_error_handler("History")
    def api_media_history():
        """Return watch history."""
        from ..media import get_watch_history, get_watch_stats
        with db.connection() as conn:
            history = get_watch_history(conn)
            stats = get_watch_stats(conn)
            return jsonify({"history": history, "stats": stats})

    @app.route("/api/media/watched", methods=["POST"])
    def api_media_watched():
        """Record a media entry as watched."""
        try:
            from ..media import record_media_watched
            data = request.get_json(force=True)
            media_id = data.get("media_id", "")
            score = data.get("score", 0.0)
            if not media_id:
                return jsonify({"error": "media_id required"}), 400
            with db.connection() as conn:
                record_media_watched(conn, media_id, score, 0, 0)
                return jsonify({"status": "ok"})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("media watched API error: %s", e)
            return jsonify({"error": "Recording failed"}), 500

    @app.route("/api/media/skip", methods=["POST"])
    def api_media_skip():
        """Record a media skip."""
        try:
            from ..media import record_media_skip
            data = request.get_json(force=True)
            media_id = data.get("media_id", "")
            if not media_id:
                return jsonify({"error": "media_id required"}), 400
            with db.connection() as conn:
                record_media_skip(conn, media_id)
                return jsonify({"status": "ok"})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("media skip API error: %s", e)
            return jsonify({"error": "Skip recording failed"}), 500

    @app.route("/api/media/liked", methods=["POST"])
    def api_media_liked():
        """Record media liked/disliked."""
        try:
            from ..media import record_media_liked
            data = request.get_json(force=True)
            media_id = data.get("media_id", "")
            liked = data.get("liked")
            if not media_id:
                return jsonify({"error": "media_id required"}), 400
            with db.connection() as conn:
                record_media_liked(conn, media_id, bool(liked))
                return jsonify({"status": "ok"})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("media liked API error: %s", e)
            return jsonify({"error": "Like recording failed"}), 500

    @app.route("/api/media/comprehension/<media_id>")
    def api_media_comprehension(media_id):
        """Return full media entry with questions for comprehension quiz."""
        try:
            from ..media import load_media_catalog
            catalog = load_media_catalog()
            entry = next((e for e in catalog if e.get("id") == media_id), None)
            if not entry:
                return jsonify({"error": "Media entry not found"}), 404
            return jsonify({
                "id": entry.get("id"),
                "title": entry.get("title", ""),
                "title_zh": entry.get("title_zh", ""),
                "hsk_level": entry.get("hsk_level", 1),
                "vocab_preview": entry.get("vocab_preview", []),
                "questions": entry.get("questions", []),
                "cultural_note": entry.get("cultural_note", ""),
                "follow_up": entry.get("follow_up", ""),
            })
        except (OSError, KeyError, TypeError) as e:
            logger.error("media comprehension API error: %s", e)
            return jsonify({"error": "Quiz unavailable"}), 500

    @app.route("/api/media/comprehension/submit", methods=["POST"])
    def api_media_comprehension_submit():
        """Submit comprehension quiz results."""
        try:
            from ..media import record_media_watched
            data = request.get_json(force=True)
            media_id = data.get("media_id", "")
            score = data.get("score", 0.0)
            total = data.get("total", 0)
            correct = data.get("correct", 0)
            if not media_id:
                return jsonify({"error": "media_id required"}), 400
            with db.connection() as conn:
                record_media_watched(conn, media_id, score, total, correct)
                return jsonify({"status": "ok", "score": score})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("media comprehension submit error: %s", e)
            return jsonify({"error": "Submit failed"}), 500

    # ── Listening endpoints ────────────────────────────────

    @app.route("/api/listening/passage")
    def api_listening_passage():
        """Return a random passage for listening practice."""
        try:
            user_id = _get_user_id()
            with db.connection() as gate_conn:
                if not check_tier_access(gate_conn, user_id, "listening"):
                    return jsonify({"error": "upgrade_required", "feature": "listening"}), 403
            from ..media import load_reading_passages
            import random as _random
            hsk_level = request.args.get("hsk_level", type=int)
            passages = load_reading_passages(hsk_level)
            if not passages:
                return jsonify({"error": "No passages at this level"}), 404
            passage = _random.choice(passages)
            # Return just enough for the listening UI — no text until reveal
            return jsonify({
                "id": passage.get("id"),
                "title": passage.get("title", ""),
                "title_zh": passage.get("title_zh", ""),
                "hsk_level": passage.get("hsk_level", 1),
                "text_zh": passage.get("text_zh", ""),
                "text_pinyin": passage.get("text_pinyin", ""),
                "text_en": passage.get("text_en", ""),
                "questions": passage.get("questions", []),
            })
        except (OSError, KeyError, TypeError) as e:
            logger.error("listening passage API error: %s", e)
            return jsonify({"error": "Passage unavailable"}), 500

    @app.route("/api/listening/complete", methods=["POST"])
    def api_listening_complete():
        """Record listening session completion and log encounters."""
        try:
            data = request.get_json(force=True)
            passage_id = data.get("passage_id", "")
            words_looked_up = data.get("words_looked_up", [])

            with db.connection() as conn:
                for hanzi in words_looked_up:
                    hanzi = (hanzi or "").strip()
                    if not hanzi:
                        continue
                    row = conn.execute(
                        "SELECT id FROM content_item WHERE hanzi = ? LIMIT 1",
                        (hanzi,)
                    ).fetchone()
                    content_item_id = row["id"] if row else None
                    conn.execute(
                        """INSERT INTO vocab_encounter
                           (content_item_id, hanzi, source_type, source_id, looked_up)
                           VALUES (?, ?, 'listening', ?, 1)""",
                        (content_item_id, hanzi, passage_id)
                    )
                conn.commit()
                return jsonify({"status": "ok", "encounters_logged": len(words_looked_up)})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("listening complete API error: %s", e)
            return jsonify({"error": "Completion recording failed"}), 500

    # ── Encounter stats endpoint ───────────────────────────

    @app.route("/api/encounters/summary")
    @api_error_handler("Encounters")
    def api_encounters_summary():
        """Return vocab encounter summary for dashboard."""
        with db.connection() as conn:
            # Total lookups in last 7 days
            total = conn.execute(
                """SELECT COUNT(*) as cnt FROM vocab_encounter
                   WHERE looked_up = 1
                     AND created_at >= datetime('now', '-7 days')"""
            ).fetchone()
            total_count = total["cnt"] if total else 0

            # Top looked-up words
            top_words = conn.execute(
                """SELECT hanzi, COUNT(*) as cnt
                   FROM vocab_encounter
                   WHERE looked_up = 1
                     AND created_at >= datetime('now', '-7 days')
                   GROUP BY hanzi
                   ORDER BY cnt DESC
                   LIMIT 10"""
            ).fetchall()

            # Source breakdown
            sources = conn.execute(
                """SELECT source_type, COUNT(*) as cnt
                   FROM vocab_encounter
                   WHERE looked_up = 1
                     AND created_at >= datetime('now', '-7 days')
                   GROUP BY source_type"""
            ).fetchall()

            return jsonify({
                "total_lookups_7d": total_count,
                "top_words": [{"hanzi": r["hanzi"], "count": r["cnt"]} for r in top_words],
                "sources": {r["source_type"]: r["cnt"] for r in sources},
            })

    # ── Settings API (Items 27, 28) ─────────────────────────────────

    @app.route("/api/settings/anonymous-mode", methods=["GET", "POST"])
    def api_anonymous_mode():
        """Get or toggle anonymous learning mode (Item 28)."""
        user_id = _get_user_id()
        with db.connection() as conn:
            if request.method == "POST":
                from ..feature_flags import is_enabled
                if not is_enabled(conn, "anonymous_mode", user_id):
                    return jsonify({"error": "Feature not available"}), 403
                data = request.get_json(force=True)
                enabled = bool(data.get("enabled", False))
                conn.execute(
                    "UPDATE user SET anonymous_mode = ? WHERE id = ?",
                    (int(enabled), user_id),
                )
                conn.commit()
                return jsonify({"anonymous_mode": enabled})
            else:
                row = conn.execute(
                    "SELECT anonymous_mode FROM user WHERE id = ?", (user_id,)
                ).fetchone()
                return jsonify({"anonymous_mode": bool(row["anonymous_mode"]) if row else False})

    @app.route("/api/settings/marketing-opt-out", methods=["GET", "POST"])
    def api_marketing_opt_out():
        """Get or toggle marketing email opt-out (Item 27)."""
        user_id = _get_user_id()
        with db.connection() as conn:
            if request.method == "POST":
                data = request.get_json(force=True)
                opted_out = bool(data.get("opted_out", True))
                conn.execute(
                    "UPDATE user SET marketing_opt_out = ? WHERE id = ?",
                    (int(opted_out), user_id),
                )
                conn.commit()
                return jsonify({"marketing_opt_out": opted_out})
            else:
                row = conn.execute(
                    "SELECT marketing_opt_out FROM user WHERE id = ?", (user_id,)
                ).fetchone()
                return jsonify({"marketing_opt_out": bool(row["marketing_opt_out"]) if row else False})

    # ── Push Notification Token Registration ─────────────────────────

    @app.route("/api/push/register", methods=["POST"])
    def api_push_register():
        """Register a push notification token for the current user."""
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.get_json(force=True)
            platform = (data.get("platform") or "").strip()
            token = (data.get("token") or "").strip()
            if not platform or not token:
                return jsonify({"error": "platform and token required"}), 400
            if platform not in ("ios", "android"):
                return jsonify({"error": "platform must be 'ios' or 'android'"}), 400

            with db.connection() as conn:
                conn.execute(
                    """INSERT INTO push_token (user_id, platform, token)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id, platform) DO UPDATE SET token = excluded.token,
                       created_at = datetime('now')""",
                    (current_user.id, platform, token),
                )
                conn.commit()
                return jsonify({"status": "ok"})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("push register error: %s", e)
            return jsonify({"error": "Registration failed"}), 500

    @app.route("/api/push/unregister", methods=["POST"])
    def api_push_unregister():
        """Remove push notification token on logout."""
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.get_json(force=True)
            platform = (data.get("platform") or "").strip()

            with db.connection() as conn:
                if platform:
                    conn.execute(
                        "DELETE FROM push_token WHERE user_id = ? AND platform = ?",
                        (current_user.id, platform),
                    )
                else:
                    conn.execute(
                        "DELETE FROM push_token WHERE user_id = ?",
                        (current_user.id,),
                    )
                conn.commit()
                return jsonify({"status": "ok"})
        except (sqlite3.Error, OSError, KeyError, TypeError, ValueError) as e:
            logger.error("push unregister error: %s", e)
            return jsonify({"error": "Unregistration failed"}), 500

    # ── Onboarding Status ────────────────────────────────────────────

    @app.route("/api/onboarding/status")
    def api_onboarding_status():
        """Return which onboarding milestones the user has hit.

        Milestones:
          first_session: completed at least 1 session
          first_week: studied on 3+ different days in first 7 days
          first_reading: used the graded reader at least once (vocab_encounter with source_type='reading')
          drill_variety: used 3+ different drill types
          first_streak: achieved a 3-day streak
        """
        try:
            with db.connection() as conn:
                milestones = {}

                # first_session: at least 1 completed session
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM session_log WHERE items_completed > 0"
                ).fetchone()
                milestones["first_session"] = (row["cnt"] if row else 0) >= 1

                # first_week: 3+ different days in first 7 calendar days since first session
                first_session_row = conn.execute(
                    "SELECT MIN(date(started_at)) as first_day FROM session_log WHERE items_completed > 0"
                ).fetchone()
                if first_session_row and first_session_row["first_day"]:
                    first_day = first_session_row["first_day"]
                    distinct_days_row = conn.execute(
                        """SELECT COUNT(DISTINCT date(started_at)) as cnt
                           FROM session_log
                           WHERE items_completed > 0
                             AND date(started_at) >= ?
                             AND date(started_at) <= date(?, '+6 days')""",
                        (first_day, first_day)
                    ).fetchone()
                    milestones["first_week"] = (distinct_days_row["cnt"] if distinct_days_row else 0) >= 3
                else:
                    milestones["first_week"] = False

                # first_reading: at least one vocab_encounter with source_type='reading'
                try:
                    reading_row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM vocab_encounter WHERE source_type = 'reading'"
                    ).fetchone()
                    milestones["first_reading"] = (reading_row["cnt"] if reading_row else 0) >= 1
                except sqlite3.OperationalError:
                    # vocab_encounter table may not exist
                    milestones["first_reading"] = False

                # drill_variety: 3+ different drill types (session_type values)
                try:
                    variety_row = conn.execute(
                        "SELECT COUNT(DISTINCT session_type) as cnt FROM session_log WHERE items_completed > 0"
                    ).fetchone()
                    milestones["drill_variety"] = (variety_row["cnt"] if variety_row else 0) >= 3
                except sqlite3.OperationalError:
                    milestones["drill_variety"] = False

                # first_streak: achieved a 3-day streak at any point
                streak = _compute_streak(conn)
                # Also check historical streaks by scanning all session dates
                if streak >= 3:
                    milestones["first_streak"] = True
                else:
                    # Check if there was ever a 3-day streak historically
                    all_days = conn.execute(
                        """SELECT DISTINCT date(started_at) as d
                           FROM session_log
                           WHERE items_completed > 0
                           ORDER BY d ASC"""
                    ).fetchall()
                    dates = []
                    for r in all_days:
                        try:
                            dates.append(dt_date.fromisoformat(r["d"]))
                        except (ValueError, TypeError):
                            pass
                    max_streak = 0
                    current_s = 1
                    for i in range(1, len(dates)):
                        if (dates[i] - dates[i - 1]).days == 1:
                            current_s += 1
                            max_streak = max(max_streak, current_s)
                        else:
                            current_s = 1
                    if len(dates) >= 1:
                        max_streak = max(max_streak, 1)
                    milestones["first_streak"] = max_streak >= 3

                milestones["all_complete"] = all(milestones.values())

                return jsonify(milestones)
        except (sqlite3.Error, OSError, KeyError, TypeError) as e:
            logger.error("onboarding status error: %s", e)
            return jsonify({"error": "Onboarding status unavailable"}), 500

    # ── Session Explainability (Item 6) ─────────────────────────────

    @app.route("/api/session/explain")
    def api_session_explain():
        """Return readable rationale for how the next session would be planned."""
        user_id = _get_user_id()
        try:
            with db.connection() as conn:
                from ..scheduler import (
                    get_day_profile, _adjust_weights_for_errors,
                    _new_item_budget, _get_hsk_bounce_levels,
                    _adaptive_session_length, _time_of_day_penalty,
                    _compute_interleave_weight, DEFAULT_WEIGHTS, GAP_WEIGHTS,
                )
                from ..config import LONG_GAP_DAYS

                profile = db.get_profile(conn, user_id=user_id)
                day_profile = get_day_profile(conn, user_id=user_id)
                days_gap = db.get_days_since_last_session(conn, user_id=user_id)
                is_long_gap = days_gap is not None and days_gap >= LONG_GAP_DAYS

                base_length = profile.get("preferred_session_length") or 12
                adaptive_length = _adaptive_session_length(conn, base_length, user_id=user_id)
                final_length = max(4, round(adaptive_length * day_profile["length_mult"]))

                base_weights = GAP_WEIGHTS if is_long_gap else DEFAULT_WEIGHTS
                weights = _adjust_weights_for_errors(conn, base_weights, user_id=user_id) if not is_long_gap else base_weights

                new_budget = _new_item_budget(conn, user_id=user_id) if not is_long_gap else 0
                tod_mult = _time_of_day_penalty(conn, user_id=user_id)
                bounce_levels = list(_get_hsk_bounce_levels(conn, user_id=user_id)) if not is_long_gap else []
                interleave_weight = _compute_interleave_weight(conn, user_id=user_id)

                return jsonify({
                    "day_profile": day_profile,
                    "gap_days": days_gap,
                    "is_long_gap": is_long_gap,
                    "base_session_length": base_length,
                    "adaptive_session_length": adaptive_length,
                    "final_session_length": final_length,
                    "modality_weights": weights,
                    "new_item_budget": new_budget,
                    "time_of_day_penalty": tod_mult,
                    "bounce_levels": bounce_levels,
                    "interleave_weight": round(interleave_weight, 3),
                    "focus_areas": [
                        f"{'Long gap recovery' if is_long_gap else 'Standard review'}",
                        f"Day profile: {day_profile.get('name', 'Standard')} ({day_profile.get('mode', 'standard')})",
                        f"New items budget: {new_budget}",
                    ] + ([f"Bounce-detected HSK levels: {bounce_levels}"] if bounce_levels else []),
                })
        except (sqlite3.Error, ImportError, KeyError, TypeError, ValueError) as e:
            logger.error("session explain error: %s", e)
            return jsonify({"error": "Explanation unavailable"}), 500

    # ── Mastery Criteria (Item 7) ─────────────────────────────────

    @app.route("/api/mastery/<int:item_id>/criteria")
    def api_mastery_criteria(item_id):
        """Return 4-gate mastery status for a specific content item."""
        user_id = _get_user_id()
        try:
            with db.connection() as conn:
                from ..config import (
                    PROMOTE_STABLE_STREAK, PROMOTE_STABLE_ATTEMPTS,
                    PROMOTE_STABLE_DRILL_TYPES, PROMOTE_STABLE_DAYS,
                )

                # Get progress across all modalities
                rows = conn.execute("""
                    SELECT mastery_stage, streak_correct, total_attempts,
                           drill_types_seen, distinct_review_days, difficulty
                    FROM progress
                    WHERE content_item_id = ? AND user_id = ?
                """, (item_id, user_id)).fetchall()

                if not rows:
                    return jsonify({"error": "No progress data for this item"}), 404

                # Aggregate across modalities
                best_streak = max(r["streak_correct"] or 0 for r in rows)
                total_attempts = sum(r["total_attempts"] or 0 for r in rows)
                all_types = set()
                for r in rows:
                    for t in (r["drill_types_seen"] or "").split(","):
                        if t.strip():
                            all_types.add(t.strip())
                max_days = max(r["distinct_review_days"] or 0 for r in rows)
                current_stage = rows[0]["mastery_stage"] or "seen"
                difficulty = rows[0]["difficulty"] or 0.5

                # Scale thresholds by difficulty
                diff_scale = 0.5 + difficulty
                scaled_streak = max(3, round(PROMOTE_STABLE_STREAK * diff_scale))
                scaled_attempts = max(5, round(PROMOTE_STABLE_ATTEMPTS * diff_scale))

                gates = {
                    "streak": {
                        "current": best_streak,
                        "needed": scaled_streak,
                        "met": best_streak >= scaled_streak,
                    },
                    "attempts": {
                        "current": total_attempts,
                        "needed": scaled_attempts,
                        "met": total_attempts >= scaled_attempts,
                    },
                    "diversity": {
                        "current": len(all_types),
                        "needed": PROMOTE_STABLE_DRILL_TYPES,
                        "met": len(all_types) >= PROMOTE_STABLE_DRILL_TYPES,
                    },
                    "days": {
                        "current": max_days,
                        "needed": PROMOTE_STABLE_DAYS,
                        "met": max_days >= PROMOTE_STABLE_DAYS,
                    },
                }

                gates_met = sum(1 for g in gates.values() if g["met"])
                summary = f"{current_stage}: {gates_met}/4 gates met"
                if gates_met >= 4:
                    summary = f"{current_stage}: all gates met — eligible for promotion"

                return jsonify({
                    "item_id": item_id,
                    "mastery_stage": current_stage,
                    "difficulty": round(difficulty, 3),
                    "gates": gates,
                    "gates_met": gates_met,
                    "summary": summary,
                })
        except (sqlite3.Error, ImportError, KeyError, TypeError, ValueError) as e:
            logger.error("mastery criteria error: %s", e)
            return jsonify({"error": "Criteria unavailable"}), 500

    # ── xAPI Statements (Item 13) ─────────────────────────────────

    @app.route("/api/xapi/statements")
    @api_error_handler("xAPI statements")
    def api_xapi_statements():
        """Return xAPI statements for the authenticated user."""
        user_id = _get_user_id()
        from ..xapi import get_statements
        with db.connection() as conn:
            since = request.args.get("since")
            until = request.args.get("until")
            statements = get_statements(conn, user_id, since=since, until=until)
            return jsonify({"statements": statements})

    # ── Caliper Events (Item 15) ──────────────────────────────────

    @app.route("/api/caliper/events")
    @api_error_handler("Caliper events")
    def api_caliper_events():
        """Return Caliper 1.2 events for the authenticated user."""
        user_id = _get_user_id()
        from ..caliper import get_events
        with db.connection() as conn:
            since = request.args.get("since")
            events = get_events(conn, user_id, since=since)
            return jsonify({"events": events})

    # ── Common Cartridge Export (Item 26) ──────────────────────────

    @app.route("/api/export/common-cartridge")
    def api_export_cc():
        """Export vocabulary as Common Cartridge ZIP."""
        user_id = _get_user_id()
        level = request.args.get("level", 1, type=int)
        try:
            from ..cc_export import export_cc
            with db.connection() as conn:
                zip_bytes = export_cc(conn, user_id, level)
                return Response(
                    zip_bytes,
                    mimetype="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="mandarin-hsk{level}.imscc"'},
                )
        except (sqlite3.Error, ImportError, KeyError, TypeError, ValueError) as e:
            logger.error("CC export error: %s", e)
            return jsonify({"error": "Export failed"}), 500

    @sock.route("/ws/session")
    def ws_session(ws):
        """WebSocket endpoint — runs a full drill session over the socket."""
        _handle_ws_session(ws, plan_standard_session, "session")

    @sock.route("/ws/mini")
    def ws_mini(ws):
        """WebSocket endpoint — runs a mini session."""
        _handle_ws_session(ws, plan_minimal_session, "mini")
