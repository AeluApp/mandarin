"""Thread-safe store for resumable WebSocket sessions.

When a browser disconnects (network blip, tab switch on mobile), the session
thread keeps running — it blocks in input_fn waiting for a reconnect.  The
SessionStore maps resume tokens to live sessions so a fresh WebSocket can be
swapped into the existing bridge.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

RESUME_TIMEOUT = 60  # seconds to wait for a reconnect before giving up


@dataclass
class ActiveSession:
    resume_token: str
    bridge: "WebBridge"  # noqa: F821  — forward ref, avoid circular import
    session_thread: threading.Thread
    created_at: float  # time.monotonic()
    user_id: int = 1


class SessionStore:
    """Thread-safe registry of live sessions that can be resumed."""

    def __init__(self):
        self._sessions: dict = {}  # resume_token -> ActiveSession
        self._lock = threading.Lock()

    def register(self, token: str, bridge, thread: threading.Thread, user_id: int = 1) -> None:
        self.cleanup_expired()
        with self._lock:
            self._sessions[token] = ActiveSession(
                resume_token=token,
                bridge=bridge,
                session_thread=thread,
                created_at=time.monotonic(),
                user_id=user_id,
            )
        logger.info("[store] registered session %s", token)

    def lookup(self, token: str):
        with self._lock:
            return self._sessions.get(token)

    def claim_for_resume(self, token: str, user_id: int) -> Optional[ActiveSession]:
        """Atomically look up and claim a session for resume.

        Returns the ActiveSession if:
        - Token exists in store
        - Session thread is still alive
        - Session is not already being resumed
        - User ID matches the session owner

        Returns None otherwise. This prevents two WS connections from
        racing to resume the same session.
        """
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if not session.session_thread.is_alive():
                self._sessions.pop(token, None)
                return None
            if hasattr(session, 'user_id') and session.user_id != user_id:
                return None
            if getattr(session, '_resuming', False):
                return None
            session._resuming = True
            return session

    def release_claim(self, token: str) -> None:
        """Release a resume claim (call on error or after swap)."""
        with self._lock:
            session = self._sessions.get(token)
            if session:
                session._resuming = False

    def find_by_user(self, user_id: int) -> Optional[ActiveSession]:
        """Find an active session for the given user."""
        with self._lock:
            for sess in self._sessions.values():
                if sess.user_id == user_id:
                    return sess
        return None

    def remove(self, token: str) -> None:
        with self._lock:
            removed = self._sessions.pop(token, None)
        if removed:
            logger.info("[store] removed session %s", token)

    def cleanup_expired(self) -> None:
        """Remove sessions whose threads have died and resume window has passed."""
        now = time.monotonic()
        to_remove = []
        with self._lock:
            for token, sess in self._sessions.items():
                if not sess.session_thread.is_alive():
                    to_remove.append(token)
                elif now - sess.created_at > 3600:  # 1-hour hard cap
                    to_remove.append(token)
            for token in to_remove:
                self._sessions.pop(token, None)
        if to_remove:
            logger.info("[store] cleaned up %d expired sessions", len(to_remove))


# Module-level singleton
session_store = SessionStore()
