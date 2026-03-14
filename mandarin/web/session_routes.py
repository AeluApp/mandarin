"""WebSocket session routes — full and mini drill sessions."""

import json
import logging
import threading

from flask import request
from flask_login import current_user
from flask_sock import Sock
from simple_websocket import ConnectionClosed

import random

from .. import db
from ..tier_gate import check_session_limit
from ..scheduler import plan_standard_session, plan_minimal_session
from ..runner import run_session
from .bridge import WebBridge
from .session_store import session_store, RESUME_TIMEOUT
from .middleware import _sanitize_error

logger = logging.getLogger(__name__)


def _detect_client_platform():
    """Detect client platform from User-Agent and request params."""
    ua = (request.headers.get("User-Agent") or "").lower()
    if request.args.get("native") == "1" or "capacitor" in ua:
        # Distinguish iOS vs Android
        if "iphone" in ua or "ipad" in ua or "ios" in ua:
            return "ios"
        elif "android" in ua:
            return "android"
        return "ios"  # Capacitor default is iOS for Aelu
    if "tauri" in ua or "__TAURI__" in (request.headers.get("Referer") or ""):
        return "macos"
    # Check if from localhost (dev) vs production domain
    host = request.host or ""
    if "localhost" in host or "127.0.0.1" in host:
        return "web_local"
    return "web"

# ── Per-user session locking ──────────────────────────────────

_user_locks = {}   # int -> threading.Lock
_user_threads = {}  # int -> threading.Thread or None
_lock_mutex = threading.Lock()


def _get_user_lock(user_id: int):
    with _lock_mutex:
        if user_id not in _user_locks:
            _user_locks[user_id] = threading.Lock()
        return _user_locks[user_id], _user_threads.get(user_id)


def _set_user_thread(user_id: int, thread):
    with _lock_mutex:
        if thread is None:
            _user_locks.pop(user_id, None)
            _user_threads.pop(user_id, None)
        else:
            _user_threads[user_id] = thread


# ── WS listen loop ───────────────────────────────────────────

def _ws_listen_loop(ws, bridge, session_thread, *, close_on_disconnect=True):
    """Receive answers from the browser until the session thread ends."""
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
            return
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    logger.debug("[%s] listen loop ended (thread dead)", bridge.session_uuid)


# ── Shared WS session handler ────────────────────────────────

def _handle_ws_session(ws, planner_fn, label):
    """Shared WebSocket session handler for both full and mini sessions."""
    if not current_user.is_authenticated:
        try:
            ws.send(json.dumps({"type": "error", "message": "Authentication required"}))
            ws.close()
        except (ConnectionClosed, OSError):
            pass
        return

    user_id = current_user.id
    user_lock, _ = _get_user_lock(user_id)

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

    # ── Tier gate: check session limit ────────────────────
    try:
        with db.connection() as gate_conn:
            if not check_session_limit(gate_conn, user_id):
                bridge = WebBridge(ws)
                bridge.send_error("You\u2019ve used today\u2019s sessions. Tomorrow brings a fresh set, or upgrade anytime for unlimited.")
                return
    except Exception as e:
        logger.warning("Tier gate check failed (allowing): %s", e)

    # ── New session path ─────────────────────────────────
    if not user_lock.acquire(blocking=False):
        _, stale_thread = _get_user_lock(user_id)
        released = False

        # Case 1: thread is dead — stale lock
        if stale_thread is not None and not stale_thread.is_alive():
            logger.warning("%s user %d: stale lock (thread dead), force-releasing", label, user_id)
            session_store.cleanup_expired()
            try:
                user_lock.release()
                released = True
            except RuntimeError:
                pass

        # Case 2: thread alive but bridge disconnected — orphaned session
        if not released and stale_thread is not None and stale_thread.is_alive():
            orphan = session_store.find_by_user(user_id)
            if orphan and (orphan.bridge._closed or orphan.bridge._disconnected):
                logger.warning("%s user %d: orphaned session (bridge closed), force-closing", label, user_id)
                orphan.bridge.close()
                stale_thread.join(timeout=5)
                session_store.cleanup_expired()
                try:
                    user_lock.release()
                    released = True
                except RuntimeError:
                    pass

        if released:
            if not user_lock.acquire(blocking=False):
                logger.warning("%s rejected for user %d: lock still held after force-release", label, user_id)
                bridge = WebBridge(ws)
                bridge.send_error("A session is already in progress. It should reconnect automatically \u2014 if not, refresh the page.")
                return
        else:
            logger.warning("%s rejected for user %d: session already active", label, user_id)
            bridge = WebBridge(ws)
            bridge.send_error("A session is already in progress. It should reconnect automatically \u2014 if not, refresh the page.")
            return
    bridge = WebBridge(ws)
    has_mic = request.args.get('mic', '1') != '0'
    resume_token = bridge.session_uuid
    logger.info("[%s] %s WS connected user=%d (mic=%s)", bridge.session_uuid, label, user_id, has_mic,
                extra={"user_id": user_id})
    bridge._send({"type": "session_init", "resume_token": resume_token})

    def _show_reading_opener(conn, show_fn, input_fn, user_id):
        """Show a brief level-appropriate reading passage before drills begin."""
        try:
            from ..media import load_reading_passages
            # Determine user's effective HSK level
            mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
            user_hsk = 1
            if mastery:
                active = [k for k, v in mastery.items() if v.get("seen", 0) > 0]
                user_hsk = max(active) if active else 1

            passages = load_reading_passages(user_hsk)
            if not passages:
                passages = load_reading_passages(1)  # Fallback to HSK 1
            if not passages:
                return

            passage = random.choice(passages)
            text = passage.get("text_zh", "")
            if not text:
                return

            # Truncate long passages for the opener (max ~80 chars)
            if len(text) > 80:
                # Cut at sentence boundary
                cut = text[:80].rfind("。")
                if cut > 20:
                    text = text[:cut + 1]
                else:
                    text = text[:80] + "…"

            bridge._send({
                "type": "reading_opener",
                "title": passage.get("title_zh", passage.get("title", "")),
                "text_zh": text,
                "passage_id": passage.get("id", ""),
                "hsk_level": passage.get("hsk_level", 1),
            })
            # Wait for user to dismiss the reading opener
            bridge.input_fn("")
        except Exception as e:
            logger.debug("reading opener skipped: %s", e)

    def _run():
        logger.info("[%s] %s thread started user=%d", bridge.session_uuid, label, user_id)
        from ..audio import set_web_audio_callback, clear_web_audio_callback
        def _on_audio(fname):
            bridge._send({"type": "audio_play", "url": f"/api/audio/{fname}"})
        set_web_audio_callback(_on_audio)

        from ..tone_grading import set_web_recording_callback, clear_web_recording_callback
        def _on_record(duration):
            return bridge.request_recording(duration)
        set_web_recording_callback(_on_record, has_mic=has_mic)

        try:
            with db.connection() as conn:
                # Show a brief reading passage before drills (standard sessions only)
                if label == "session":
                    _show_reading_opener(conn, bridge.show_fn, bridge.input_fn, user_id)

                plan = planner_fn(conn, user_id=user_id)
                logger.info("[%s] %s planned: %d drills", bridge.session_uuid, label, len(plan.drills))

                # Send focus insights to show adaptive intelligence
                if plan.focus_insights:
                    bridge._send({
                        "type": "focus_insight",
                        "insights": plan.focus_insights,
                        "micro_plan": plan.micro_plan,
                    })

                def _progress(sid, idx, total, correct, completed, stype):
                    bridge.send_progress(sid, idx, total, correct, completed, stype)
                def _drill_meta(**kwargs):
                    bridge.send_drill_meta(**kwargs)

                # Suppress CLI _finalize() text output on web — the structured
                # showComplete() screen handles the summary display via API calls.
                # Detect the ─── divider that starts _finalize output and suppress
                # all subsequent show_fn/input_fn calls.
                _suppressing = [False]

                def _web_show_fn(text, end="\n"):
                    if _suppressing[0]:
                        return
                    # _finalize starts with a 25-char box-drawing divider
                    if "\u2500" * 20 in text:
                        _suppressing[0] = True
                        return
                    bridge.show_fn(text, end)

                def _web_input_fn(prompt):
                    if _suppressing[0]:
                        return ""  # Auto-skip post-session nudges on web
                    return bridge.input_fn(prompt)

                state = run_session(conn, plan, _web_show_fn, _web_input_fn,
                                    user_id=user_id, progress_fn=_progress,
                                    drill_meta_fn=_drill_meta,
                                    client_platform=_detect_client_platform())

                # Collect extra summary data for the enriched done message
                done_data = {
                    "items_completed": state.items_completed,
                    "items_correct": state.items_correct,
                    "early_exit": state.early_exit,
                }

                # Error type breakdown from session results
                error_types = {}
                new_count = 0
                for r in state.results:
                    if not r.correct and not r.skipped and r.error_type:
                        error_types[r.error_type] = error_types.get(r.error_type, 0) + 1
                for d in state.plan.drills:
                    if d.is_new:
                        new_count += 1
                if error_types:
                    done_data["error_types"] = error_types
                if new_count > 0:
                    done_data["new_count"] = new_count

                # Response speed from today's progress records
                try:
                    from datetime import date
                    speed_row = conn.execute("""
                        SELECT AVG(p.avg_response_ms) as avg_ms, COUNT(*) as cnt
                        FROM progress p
                        WHERE p.avg_response_ms IS NOT NULL AND p.last_review_date = ?
                          AND p.user_id = ?
                    """, (date.today().isoformat(), user_id)).fetchone()
                    if speed_row and speed_row["avg_ms"] and speed_row["cnt"] >= 3:
                        done_data["speed_avg_s"] = round(speed_row["avg_ms"] / 1000, 1)
                except Exception:
                    pass

                # Streak freeze earning: award a freeze after 7 consecutive days (max 2)
                try:
                    from .middleware import _compute_streak
                    current_streak = _compute_streak(conn, user_id=user_id)
                    if current_streak > 0 and current_streak % 7 == 0:
                        conn.execute("""
                            UPDATE user SET streak_freezes_available = MIN(streak_freezes_available + 1, 2)
                            WHERE id = ? AND streak_freezes_available < 2
                        """, (user_id,))
                        conn.commit()
                except Exception:
                    pass

                bridge.send_done(done_data)
                logger.info("[%s] %s complete: %d/%d", bridge.session_uuid, label, state.items_correct, state.items_completed)
        except Exception as e:
            logger.error("[%s] %s error (%s): %s", bridge.session_uuid, label, type(e).__name__, e)
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
        elif not bridge._closed:
            logger.warning("[%s] %s thread died unexpectedly", bridge.session_uuid, label)
            bridge.send_error("Session ended unexpectedly. Please start a new session.")
        session_store.remove(resume_token)
    finally:
        if not session_thread.is_alive():
            bridge.close()
        _set_user_thread(user_id, None)
        try:
            user_lock.release()
        except RuntimeError:
            pass


def register_session_routes(app):
    """Register WebSocket session routes on the Flask app."""
    sock = Sock(app)

    @sock.route("/ws/session")
    def ws_session(ws):
        """WebSocket endpoint — runs a full drill session over the socket."""
        _handle_ws_session(ws, plan_standard_session, "session")

    @sock.route("/ws/mini")
    def ws_mini(ws):
        """WebSocket endpoint — runs a mini session."""
        _handle_ws_session(ws, plan_minimal_session, "mini")
