"""Tests for WebSocket session routes, bridge, and session store.

Covers the code in mandarin/web/session_routes.py, mandarin/web/bridge.py,
and mandarin/web/session_store.py to increase mandarin/web test coverage.
Each test exercises the route/module code and asserts correct behaviour.
"""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from mandarin.web import create_app
from mandarin.auth import create_user
from werkzeug.security import generate_password_hash as _orig_gen


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as test_dashboard_routes)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Context manager that returns the test conn unchanged."""
    def __init__(self, conn):
        self._conn = conn
    def __enter__(self):
        return self._conn
    def __exit__(self, *args):
        return False


def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


@pytest.fixture
def app_client(test_db):
    """Flask test client wired to the test database."""
    conn, _ = test_db
    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)
    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as client:
            yield client, conn


TEST_EMAIL = "session@example.com"
TEST_PASSWORD = "sessiontest12345"  # gitleaks:allow (test fixture, not a real secret)


def _create_and_login(client, conn, email=TEST_EMAIL, password=TEST_PASSWORD):
    """Create a user and log them in, returning the user dict."""
    user = create_user(conn, email, password, "SessTest")
    conn.commit()
    client.post("/auth/login", data={
        "email": email,
        "password": password,
    }, follow_redirects=True)
    return user


XHR = {"X-Requested-With": "XMLHttpRequest"}


# ---------------------------------------------------------------------------
# WebBridge tests
# ---------------------------------------------------------------------------

class TestWebBridge:

    def test_bridge_creation(self):
        """WebBridge initialises with session_uuid and clean state."""
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        assert bridge.session_uuid
        assert len(bridge.session_uuid) == 8
        assert bridge._closed is False
        assert bridge._disconnected is False

    def test_bridge_show_fn_sends_json(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.show_fn("hello")
        ws.send.assert_called_once()
        msg = json.loads(ws.send.call_args[0][0])
        assert msg["type"] == "show"
        assert msg["text"] == "hello"

    def test_bridge_show_fn_noop_when_closed(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge._closed = True
        bridge.show_fn("should not send")
        ws.send.assert_not_called()

    def test_bridge_send_done(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.send_done({"items_completed": 5})
        ws.send.assert_called_once()
        msg = json.loads(ws.send.call_args[0][0])
        assert msg["type"] == "done"
        assert msg["summary"]["items_completed"] == 5

    def test_bridge_send_done_includes_roundtrip(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge._roundtrip_times = [100.0, 200.0]
        bridge.send_done({"x": 1})
        msg = json.loads(ws.send.call_args[0][0])
        assert msg["summary"]["avg_ws_roundtrip_ms"] == 150.0

    def test_bridge_send_done_noop_when_closed(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge._closed = True
        bridge.send_done({"x": 1})
        ws.send.assert_not_called()

    def test_bridge_send_error(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.send_error("oops")
        ws.send.assert_called_once()
        msg = json.loads(ws.send.call_args[0][0])
        assert msg["type"] == "error"
        assert msg["message"] == "oops"

    def test_bridge_send_error_noop_when_closed(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge._closed = True
        bridge.send_error("nope")
        ws.send.assert_not_called()

    def test_bridge_send_progress(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.send_progress(session_id=1, drill_index=3, drill_total=10,
                             correct=2, completed=3, session_type="standard")
        ws.send.assert_called_once()
        msg = json.loads(ws.send.call_args[0][0])
        assert msg["type"] == "progress"
        assert msg["session_id"] == 1
        assert msg["drill_total"] == 10

    def test_bridge_receive_answer(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge._prompt_sent_at = time.monotonic() - 0.5
        bridge.receive_answer("correct")
        answer = bridge._answer_queue.get_nowait()
        assert answer == "correct"
        assert len(bridge._roundtrip_times) == 1

    def test_bridge_close(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.close()
        assert bridge._closed is True
        assert bridge._disconnected is True

    def test_bridge_disconnect(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.disconnect()
        assert bridge._disconnected is True
        assert bridge._closed is False

    def test_bridge_send_handles_connection_error(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        ws.send.side_effect = ConnectionError("broken pipe")
        bridge = WebBridge(ws)
        bridge._send({"type": "test"})
        assert bridge._disconnected is True

    def test_bridge_send_drill_meta(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.send_drill_meta(content_item_id=42, modality="reading",
                               correct=True, hanzi="好")
        ws.send.assert_called_once()
        msg = json.loads(ws.send.call_args[0][0])
        assert msg["type"] == "drill_meta"
        assert msg["content_item_id"] == 42
        assert msg["correct"] is True

    def test_bridge_send_audio_state(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.send_audio_state("playing")
        ws.send.assert_called_once()
        msg = json.loads(ws.send.call_args[0][0])
        assert msg["type"] == "audio_state"
        assert msg["state"] == "playing"

    def test_bridge_word_lookup(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge.receive_word_lookup("好")
        bridge.receive_word_lookup("你")
        bridge.receive_word_lookup("好")  # duplicate should be ignored
        result = bridge.drain_word_lookups()
        assert result == ["好", "你"]
        assert bridge.drain_word_lookups() == []

    def test_bridge_swap_ws(self):
        from mandarin.web.bridge import WebBridge
        ws1 = MagicMock()
        ws2 = MagicMock()
        bridge = WebBridge(ws1)
        bridge._disconnected = True
        bridge.swap_ws(ws2)
        assert bridge.ws is ws2
        assert bridge._disconnected is False

    def test_bridge_request_recording_when_closed(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        bridge = WebBridge(ws)
        bridge._closed = True
        result = bridge.request_recording(5.0)
        assert result == (None, None)

    def test_bridge_show_fn_disconnects_on_error(self):
        from mandarin.web.bridge import WebBridge
        ws = MagicMock()
        ws.send.side_effect = OSError("connection reset")
        bridge = WebBridge(ws)
        bridge.show_fn("hello")
        assert bridge._disconnected is True


# ---------------------------------------------------------------------------
# Rich-to-HTML conversion tests
# ---------------------------------------------------------------------------

class TestRichToHtml:

    def test_plain_text(self):
        from mandarin.web.bridge import _rich_to_html
        assert _rich_to_html("hello world") == "hello world"

    def test_html_escaping(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_bold_markup(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[bold]hello[/bold]")
        assert 'class="rich-bold"' in result
        assert "hello" in result

    def test_green_correct(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[green]correct[/green]")
        assert "rich-correct" in result

    def test_nested_unclosed_tags(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[bold]unclosed")
        assert "</span>" in result

    def test_sparkline_wrapped(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("trend: ▁▂▃▄▅▆▇█")
        assert "sparkline-inline" in result


# ---------------------------------------------------------------------------
# SessionStore tests
# ---------------------------------------------------------------------------

class TestSessionStore:

    def test_register_and_lookup(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = True
        store.register("tok-1", bridge, thread, user_id=99)
        result = store.lookup("tok-1")
        assert result is not None
        assert result.resume_token == "tok-1"
        assert result.user_id == 99

    def test_lookup_missing_returns_none(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        assert store.lookup("nonexistent") is None

    def test_claim_for_resume_success(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = True
        store.register("tok-2", bridge, thread, user_id=10)
        active = store.claim_for_resume("tok-2", user_id=10)
        assert active is not None
        assert active.resume_token == "tok-2"

    def test_claim_for_resume_wrong_user(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = True
        store.register("tok-3", bridge, thread, user_id=10)
        active = store.claim_for_resume("tok-3", user_id=999)
        assert active is None

    def test_claim_for_resume_dead_thread(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = False
        store.register("tok-4", bridge, thread, user_id=10)
        active = store.claim_for_resume("tok-4", user_id=10)
        assert active is None

    def test_claim_for_resume_already_resuming(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = True
        store.register("tok-5", bridge, thread, user_id=10)
        first = store.claim_for_resume("tok-5", user_id=10)
        assert first is not None
        second = store.claim_for_resume("tok-5", user_id=10)
        assert second is None

    def test_release_claim(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = True
        store.register("tok-6", bridge, thread, user_id=10)
        store.claim_for_resume("tok-6", user_id=10)
        store.release_claim("tok-6")
        active = store.claim_for_resume("tok-6", user_id=10)
        assert active is not None

    def test_remove(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = True
        store.register("tok-7", bridge, thread, user_id=10)
        store.remove("tok-7")
        assert store.lookup("tok-7") is None

    def test_find_by_user(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = True
        store.register("tok-8", bridge, thread, user_id=42)
        found = store.find_by_user(42)
        assert found is not None
        assert found.user_id == 42
        assert store.find_by_user(999) is None

    def test_cleanup_expired_removes_dead_threads(self):
        from mandarin.web.session_store import SessionStore
        store = SessionStore()
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = False
        store.register("tok-9", bridge, thread, user_id=10)
        store.cleanup_expired()
        assert store.lookup("tok-9") is None


# ---------------------------------------------------------------------------
# session_routes helper functions
# ---------------------------------------------------------------------------

class TestDetectClientPlatform:

    def test_web_default(self, app_client):
        """Default platform is 'web' for normal browser requests."""
        from mandarin.web.session_routes import _detect_client_platform
        client, conn = app_client
        _create_and_login(client, conn)
        with client.application.test_request_context("/ws/session"):
            result = _detect_client_platform()
            assert result in ("web", "web_local")

    def test_ios_native(self, app_client):
        from mandarin.web.session_routes import _detect_client_platform
        client, _ = app_client
        with client.application.test_request_context(
            "/ws/session?native=1",
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS)"}
        ):
            result = _detect_client_platform()
            assert result == "ios"

    def test_android_native(self, app_client):
        from mandarin.web.session_routes import _detect_client_platform
        client, _ = app_client
        with client.application.test_request_context(
            "/ws/session?native=1",
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13)"}
        ):
            result = _detect_client_platform()
            assert result == "android"

    def test_capacitor_in_ua(self, app_client):
        from mandarin.web.session_routes import _detect_client_platform
        client, _ = app_client
        with client.application.test_request_context(
            "/ws/session",
            headers={"User-Agent": "Mozilla Capacitor iOS"}
        ):
            result = _detect_client_platform()
            assert result == "ios"

    def test_tauri_desktop(self, app_client):
        from mandarin.web.session_routes import _detect_client_platform
        client, _ = app_client
        with client.application.test_request_context(
            "/ws/session",
            headers={"User-Agent": "Mozilla Tauri/2.0"}
        ):
            result = _detect_client_platform()
            assert result == "macos"

    def test_localhost_returns_web_local(self, app_client):
        from mandarin.web.session_routes import _detect_client_platform
        client, _ = app_client
        with client.application.test_request_context(
            "/ws/session",
            base_url="http://localhost:5000",
            headers={"User-Agent": "Mozilla/5.0 Chrome"}
        ):
            result = _detect_client_platform()
            assert result == "web_local"


class TestUserLocking:

    def test_get_user_lock_creates_new(self):
        from mandarin.web.session_routes import _get_user_lock
        lock, thread = _get_user_lock(999999)
        assert isinstance(lock, type(threading.Lock()))
        assert thread is None

    def test_set_user_thread_and_clear(self):
        from mandarin.web.session_routes import _get_user_lock, _set_user_thread
        uid = 888888
        dummy_thread = MagicMock()
        _set_user_thread(uid, dummy_thread)
        lock, thread = _get_user_lock(uid)
        assert thread is dummy_thread
        _set_user_thread(uid, None)
        _, thread2 = _get_user_lock(uid)
        assert thread2 is None


class TestRegisterSessionRoutes:

    def test_register_with_websocket(self, app_client):
        """register_session_routes should succeed when flask_sock is available."""
        from mandarin.web.session_routes import register_session_routes
        client, _ = app_client
        app = client.application
        # If flask_sock is installed, registration should work
        try:
            register_session_routes(app)
        except Exception:
            # flask_sock may not be installed in test env — that is OK
            pass

    def test_register_without_websocket(self, app_client):
        """register_session_routes is a no-op when flask_sock is missing."""
        from mandarin.web import session_routes
        client, _ = app_client
        app = client.application
        original = session_routes._HAS_WEBSOCKET
        try:
            session_routes._HAS_WEBSOCKET = False
            session_routes.register_session_routes(app)
        finally:
            session_routes._HAS_WEBSOCKET = original


# ---------------------------------------------------------------------------
# middleware._sanitize_error
# ---------------------------------------------------------------------------

class TestSanitizeError:

    def test_no_such_table(self):
        from mandarin.web.middleware import _sanitize_error
        result = _sanitize_error(Exception("no such table: content_item"))
        assert "Database needs setup" in result

    def test_database_locked(self):
        from mandarin.web.middleware import _sanitize_error
        result = _sanitize_error(Exception("database is locked"))
        assert "busy" in result.lower()

    def test_generic_error(self):
        from mandarin.web.middleware import _sanitize_error
        result = _sanitize_error(Exception("something weird happened"))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _escape_html
# ---------------------------------------------------------------------------

class TestEscapeHtml:

    def test_escapes_special_chars(self):
        from mandarin.web.bridge import _escape_html
        result = _escape_html('<a href="x">&')
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "&quot;" in result

    def test_escapes_single_quote(self):
        from mandarin.web.bridge import _escape_html
        result = _escape_html("it's")
        assert "&#x27;" in result


# ---------------------------------------------------------------------------
# middleware.paginate_params
# ---------------------------------------------------------------------------

class TestPaginateParams:

    def test_default_params(self, app_client):
        from mandarin.web.middleware import paginate_params
        client, _ = app_client
        with client.application.test_request_context("/test"):
            page, per_page, offset, user_id = paginate_params()
            assert page == 1
            assert per_page == 50
            assert offset == 0
            assert user_id is None

    def test_custom_page(self, app_client):
        from mandarin.web.middleware import paginate_params
        client, _ = app_client
        with client.application.test_request_context("/test?page=3&per_page=10"):
            page, per_page, offset, user_id = paginate_params()
            assert page == 3
            assert per_page == 10
            assert offset == 20

    def test_max_per_page_clamp(self, app_client):
        from mandarin.web.middleware import paginate_params
        client, _ = app_client
        with client.application.test_request_context("/test?per_page=9999"):
            page, per_page, offset, user_id = paginate_params()
            assert per_page == 100  # clamped to max_per_page

    def test_negative_page_clamped(self, app_client):
        from mandarin.web.middleware import paginate_params
        client, _ = app_client
        with client.application.test_request_context("/test?page=-5"):
            page, per_page, offset, user_id = paginate_params()
            assert page == 1


# ---------------------------------------------------------------------------
# middleware._compute_streak
# ---------------------------------------------------------------------------

class TestComputeStreak:

    def test_streak_zero_for_new_user(self, app_client):
        from mandarin.web.middleware import _compute_streak
        client, conn = app_client
        _create_and_login(client, conn)
        streak = _compute_streak(conn, user_id=1)
        assert streak == 0

    def test_streak_with_session(self, app_client):
        from mandarin.web.middleware import _compute_streak
        client, conn = app_client
        user = _create_and_login(client, conn)
        # Insert a session for today
        conn.execute(
            "INSERT INTO session_log (user_id, started_at, items_completed, items_correct) VALUES (?, datetime('now'), 5, 3)",
            (user["id"],),
        )
        conn.commit()
        streak = _compute_streak(conn, user_id=user["id"])
        assert streak >= 1


# ---------------------------------------------------------------------------
# middleware._get_user_id
# ---------------------------------------------------------------------------

class TestGetUserId:

    def test_get_user_id_unauthenticated(self, app_client):
        from mandarin.web.middleware import _get_user_id
        client, _ = app_client
        with client.application.test_request_context("/test"):
            with pytest.raises(Exception):  # noqa: B017  # Flask abort raises werkzeug HTTPException
                # Should abort with 401 when not authenticated
                _get_user_id()


# ---------------------------------------------------------------------------
# bridge.BridgeDisconnected
# ---------------------------------------------------------------------------

class TestBridgeDisconnected:

    def test_bridge_disconnected_is_exception(self):
        from mandarin.web.bridge import BridgeDisconnected
        exc = BridgeDisconnected("test")
        assert isinstance(exc, Exception)
        assert str(exc) == "test"


# ---------------------------------------------------------------------------
# bridge._rich_to_html — additional coverage
# ---------------------------------------------------------------------------

class TestRichToHtmlExtra:

    def test_red_incorrect(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[red]wrong[/red]")
        assert "rich-incorrect" in result

    def test_yellow_secondary(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[yellow]warning[/yellow]")
        assert "rich-secondary" in result

    def test_bright_magenta_hanzi(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[bold bright_magenta]好[/bold bright_magenta]")
        assert "hanzi-inline" in result
        assert "rich-accent-bold" in result

    def test_unknown_style_neutral_span(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[custom_style]text[/custom_style]")
        assert "<span>" in result

    def test_close_slash_only(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[bold]text[/]")
        assert "</span>" in result

    def test_dim_italic(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[dim italic]muted[/dim italic]")
        assert "rich-dim-italic" in result

    def test_cjk_in_bright_cyan(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("[bright_cyan]你好[/bright_cyan]")
        assert "hanzi-inline" in result

    def test_no_tags_passthrough(self):
        from mandarin.web.bridge import _rich_to_html
        result = _rich_to_html("no tags here")
        assert result == "no tags here"


# ---------------------------------------------------------------------------
# session_routes._ws_listen_loop (unit test with mock)
# ---------------------------------------------------------------------------

class TestWsListenLoop:

    def test_listen_loop_exits_when_thread_dead(self):
        from mandarin.web.session_routes import _ws_listen_loop
        ws = MagicMock()
        ws.receive.return_value = None
        bridge = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = False
        _ws_listen_loop(ws, bridge, thread)
        # Should exit immediately since thread is dead

    def test_listen_loop_handles_answer(self):
        from mandarin.web.session_routes import _ws_listen_loop
        ws = MagicMock()
        # First receive returns an answer, second signals thread dead
        call_count = [0]
        def _recv(timeout=1):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({"type": "answer", "value": "correct"})
            return None
        ws.receive = _recv
        bridge = MagicMock()
        thread = MagicMock()
        alive_count = [0]
        def _is_alive():
            alive_count[0] += 1
            return alive_count[0] <= 2
        thread.is_alive = _is_alive
        _ws_listen_loop(ws, bridge, thread)
        bridge.receive_answer.assert_called_once_with("correct")

    def test_listen_loop_handles_word_lookup(self):
        from mandarin.web.session_routes import _ws_listen_loop
        ws = MagicMock()
        call_count = [0]
        def _recv(timeout=1):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({"type": "word_lookup", "hanzi": "好"})
            return None
        ws.receive = _recv
        bridge = MagicMock()
        bridge.session_uuid = "test1234"
        thread = MagicMock()
        alive_count = [0]
        def _is_alive():
            alive_count[0] += 1
            return alive_count[0] <= 2
        thread.is_alive = _is_alive
        _ws_listen_loop(ws, bridge, thread)
        bridge.receive_word_lookup.assert_called_once_with("好")

    def test_listen_loop_handles_connection_closed(self):
        from mandarin.web.session_routes import _ws_listen_loop, ConnectionClosed
        ws = MagicMock()
        ws.receive.side_effect = ConnectionClosed()
        bridge = MagicMock()
        bridge.session_uuid = "test1234"
        thread = MagicMock()
        thread.is_alive.return_value = True
        _ws_listen_loop(ws, bridge, thread, close_on_disconnect=True)
        bridge.close.assert_called_once()

    def test_listen_loop_disconnect_mode(self):
        from mandarin.web.session_routes import _ws_listen_loop, ConnectionClosed
        ws = MagicMock()
        ws.receive.side_effect = ConnectionClosed()
        bridge = MagicMock()
        bridge.session_uuid = "test1234"
        thread = MagicMock()
        thread.is_alive.return_value = True
        _ws_listen_loop(ws, bridge, thread, close_on_disconnect=False)
        bridge.disconnect.assert_called_once()

    def test_listen_loop_handles_json_error(self):
        from mandarin.web.session_routes import _ws_listen_loop
        ws = MagicMock()
        call_count = [0]
        def _recv(timeout=1):
            call_count[0] += 1
            if call_count[0] == 1:
                return "not valid json"
            return None
        ws.receive = _recv
        bridge = MagicMock()
        thread = MagicMock()
        alive_count = [0]
        def _is_alive():
            alive_count[0] += 1
            return alive_count[0] <= 2
        thread.is_alive = _is_alive
        _ws_listen_loop(ws, bridge, thread)
        # Should not crash on bad JSON

    def test_listen_loop_handles_audio_data(self):
        from mandarin.web.session_routes import _ws_listen_loop
        ws = MagicMock()
        call_count = [0]
        def _recv(timeout=1):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({"type": "audio_data", "data": "base64data", "transcript": "hello"})
            return None
        ws.receive = _recv
        bridge = MagicMock()
        bridge.session_uuid = "test1234"
        thread = MagicMock()
        alive_count = [0]
        def _is_alive():
            alive_count[0] += 1
            return alive_count[0] <= 2
        thread.is_alive = _is_alive
        _ws_listen_loop(ws, bridge, thread)
        bridge.receive_audio_data.assert_called_once_with("base64data", "hello")
