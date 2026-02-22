"""Tests for WebSocket session resumption: SessionStore + WebBridge reconnect logic.

Covers:
- SessionStore register/lookup/remove/cleanup lifecycle
- WebBridge disconnect vs close semantics
- WebBridge swap_ws reconnect handshake
"""

import sys
import os
import threading

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mandarin.web.session_store import SessionStore, ActiveSession, RESUME_TIMEOUT
from mandarin.web.bridge import WebBridge


# ── Mock helpers ──────────────────────────────────

class MockWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    def send(self, data):
        self.sent.append(data)

    def receive(self, timeout=None):
        return None

    def close(self):
        self.closed = True


class MockThread:
    def __init__(self, alive=True):
        self._alive = alive

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        pass


# ── SessionStore tests ────────────────────────────

def test_session_store_register_lookup():
    """Register a session and verify lookup returns it."""
    store = SessionStore()
    ws = MockWebSocket()
    bridge = WebBridge(ws)
    thread = MockThread(alive=True)

    store.register("tok-1", bridge, thread)
    session = store.lookup("tok-1")

    assert session is not None, "lookup should return a session"
    assert isinstance(session, ActiveSession)
    assert session.resume_token == "tok-1"
    assert session.bridge is bridge
    assert session.session_thread is thread


def test_session_store_remove():
    """Register then remove. Lookup should return None."""
    store = SessionStore()
    ws = MockWebSocket()
    bridge = WebBridge(ws)
    thread = MockThread(alive=True)

    store.register("tok-2", bridge, thread)
    store.remove("tok-2")

    assert store.lookup("tok-2") is None, "removed session should not be found"


def test_session_store_lookup_missing():
    """Lookup a token that was never registered returns None."""
    store = SessionStore()
    assert store.lookup("nonexistent") is None


def test_session_store_cleanup_expired():
    """Sessions with dead threads are removed by cleanup_expired."""
    store = SessionStore()
    ws = MockWebSocket()
    bridge = WebBridge(ws)
    dead_thread = MockThread(alive=False)

    store.register("tok-dead", bridge, dead_thread)
    assert store.lookup("tok-dead") is not None, "session should exist before cleanup"

    store.cleanup_expired()
    assert store.lookup("tok-dead") is None, "dead-thread session should be cleaned up"


# ── WebBridge disconnect / close / swap tests ─────

def test_bridge_disconnect_is_resumable():
    """disconnect() marks transport lost but keeps session alive."""
    ws = MockWebSocket()
    bridge = WebBridge(ws)

    bridge.disconnect()

    assert bridge._disconnected is True, "_disconnected should be True after disconnect()"
    assert bridge._closed is False, "_closed should remain False — session is resumable"


def test_bridge_close_is_terminal():
    """close() ends the session permanently."""
    ws = MockWebSocket()
    bridge = WebBridge(ws)

    bridge.close()

    assert bridge._closed is True, "_closed should be True after close()"
    assert bridge._disconnected is True, "_disconnected should also be True after close()"


def test_bridge_swap_ws():
    """swap_ws replaces the transport and clears disconnected state."""
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    bridge = WebBridge(ws1)

    bridge.disconnect()
    assert bridge._disconnected is True

    bridge.swap_ws(ws2)

    assert bridge._disconnected is False, "_disconnected should be cleared after swap"
    assert bridge.ws is ws2, "ws should point to the new WebSocket"


def test_bridge_reconnect_event_set_on_swap():
    """swap_ws sets _reconnect_event so blocked input_fn can wake up."""
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    bridge = WebBridge(ws1)

    bridge._disconnected = True
    assert not bridge._reconnect_event.is_set(), "event should not be set before swap"

    bridge.swap_ws(ws2)
    assert bridge._reconnect_event.is_set(), "event should be set after swap_ws"


# ── claim_for_resume tests ────────────────────────

def test_claim_for_resume_success():
    """claim_for_resume returns session and marks it as resuming."""
    store = SessionStore()
    ws = MockWebSocket()
    bridge = WebBridge(ws)
    thread = MockThread(alive=True)

    store.register("tok-claim", bridge, thread, user_id=42)
    result = store.claim_for_resume("tok-claim", user_id=42)

    assert result is not None, "claim should succeed"
    assert result.resume_token == "tok-claim"
    assert getattr(result, '_resuming', False) is True


def test_claim_for_resume_wrong_user():
    """claim_for_resume rejects a different user."""
    store = SessionStore()
    ws = MockWebSocket()
    bridge = WebBridge(ws)
    thread = MockThread(alive=True)

    store.register("tok-wrong-user", bridge, thread, user_id=42)
    result = store.claim_for_resume("tok-wrong-user", user_id=99)

    assert result is None, "claim should fail for wrong user"


def test_claim_for_resume_double_claim():
    """Second claim_for_resume on same token returns None (race protection)."""
    store = SessionStore()
    ws = MockWebSocket()
    bridge = WebBridge(ws)
    thread = MockThread(alive=True)

    store.register("tok-double", bridge, thread, user_id=42)
    first = store.claim_for_resume("tok-double", user_id=42)
    second = store.claim_for_resume("tok-double", user_id=42)

    assert first is not None, "first claim should succeed"
    assert second is None, "second claim should fail (already resuming)"


def test_claim_for_resume_dead_thread():
    """claim_for_resume returns None and removes session if thread is dead."""
    store = SessionStore()
    ws = MockWebSocket()
    bridge = WebBridge(ws)
    thread = MockThread(alive=False)

    store.register("tok-dead-claim", bridge, thread)
    result = store.claim_for_resume("tok-dead-claim", user_id=1)

    assert result is None, "claim should fail for dead thread"
    assert store.lookup("tok-dead-claim") is None, "session should be removed"


def test_release_claim():
    """release_claim clears the _resuming flag."""
    store = SessionStore()
    ws = MockWebSocket()
    bridge = WebBridge(ws)
    thread = MockThread(alive=True)

    store.register("tok-release", bridge, thread, user_id=42)
    store.claim_for_resume("tok-release", user_id=42)
    store.release_claim("tok-release")

    # Should be claimable again
    result = store.claim_for_resume("tok-release", user_id=42)
    assert result is not None, "claim should succeed after release"


