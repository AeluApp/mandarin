"""Tests for sync routes (mandarin.web.sync_routes).

Covers:
1.  POST /api/sync/push — unauthenticated returns 401
2.  GET /api/sync/pull — unauthenticated returns 401
3.  GET /api/sync/state — unauthenticated returns 401
4.  POST /api/sync/push — valid drill_result action (correct)
5.  POST /api/sync/push — valid drill_result action (incorrect)
6.  POST /api/sync/push — valid vocab_encounter action
7.  POST /api/sync/push — valid media_watched action
8.  POST /api/sync/push — unknown action type returns error in response
9.  POST /api/sync/push — empty actions list returns processed=0
10. POST /api/sync/push — non-list actions value returns validation error
11. POST /api/sync/push — mixed valid and invalid actions
12. POST /api/sync/push — drill_result with missing content_item_id is skipped
13. POST /api/sync/push — vocab_encounter with empty hanzi is skipped
14. GET /api/sync/pull — basic pull with no data returns empty lists
15. GET /api/sync/pull — pull returns progress data
16. GET /api/sync/pull — pull with since parameter filters old data
17. GET /api/sync/pull — pull returns session data
18. GET /api/sync/state — returns hash, last_updated, item_count
19. GET /api/sync/state — state changes after progress update
20. GET /api/sync/state — state with no progress returns zero count
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest

from mandarin.auth import create_user


# ---------------------------------------------------------------------------
# Python 3.9 compat: force pbkdf2 instead of scrypt
# ---------------------------------------------------------------------------

from werkzeug.security import generate_password_hash as _orig_gen


def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


# ---------------------------------------------------------------------------
# Fake DB context-manager wrapper
# ---------------------------------------------------------------------------

class _FakeConn:
    """Wraps a real sqlite3.Connection so it works as both a context manager
    (for ``with db.connection() as conn:``) and as a raw connection object.
    """

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Test-client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client(test_db):
    """Flask test client with all DB connections patched to the test database.

    Yields (client, conn).
    """
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test"

    fake = _FakeConn(conn)
    fake_connection = lambda: fake  # noqa: E731

    with patch("mandarin.db.connection", fake_connection), \
         patch("mandarin.web.routes.db.connection", fake_connection), \
         patch("mandarin.web.payment_routes.db.connection", fake_connection), \
         patch("mandarin.web.onboarding_routes.db.connection", fake_connection), \
         patch("mandarin.web.admin_routes.db.connection", fake_connection), \
         patch("mandarin.web.auth_routes.db.connection", fake_connection), \
         patch("mandarin.web.sync_routes.db.connection", fake_connection):
        with app.test_client() as client:
            yield client, conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JSON_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}


def _login(client, conn, email="syncuser@example.com", password="syncpass12345"):
    """Create a user and log them in via session. Returns the user dict."""
    user = create_user(conn, email, password, "Sync User")
    client.post(
        "/auth/login",
        data={"email": email, "password": password},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user["id"])
        sess["_fresh"] = True
    return user


def _insert_content_item(conn, hanzi="你好", pinyin="nǐ hǎo", english="hello"):
    """Insert a minimal content_item row and return its id."""
    cursor = conn.execute(
        "INSERT INTO content_item (hanzi, pinyin, english) VALUES (?, ?, ?)",
        (hanzi, pinyin, english),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_progress(conn, user_id, content_item_id, modality="reading",
                     last_review_date="2026-02-20 12:00:00"):
    """Insert a progress row and return its id."""
    cursor = conn.execute(
        """INSERT INTO progress
           (user_id, content_item_id, modality, streak_correct, streak_incorrect,
            total_attempts, total_correct, last_review_date, mastery_stage)
           VALUES (?, ?, ?, 0, 0, 0, 0, ?, 'seen')""",
        (user_id, content_item_id, modality, last_review_date),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_session_log(conn, user_id, started_at="2026-02-20 10:00:00",
                        session_type="standard", items_completed=5, items_correct=4):
    """Insert a session_log row and return its id."""
    cursor = conn.execute(
        """INSERT INTO session_log
           (user_id, started_at, session_type, items_completed, items_correct,
            early_exit, session_outcome)
           VALUES (?, ?, ?, ?, ?, 0, 'completed')""",
        (user_id, started_at, session_type, items_completed, items_correct),
    )
    conn.commit()
    return cursor.lastrowid


# ---------------------------------------------------------------------------
# 1. Authentication required
# ---------------------------------------------------------------------------

class TestAuthRequired:
    """All sync endpoints must return 401 when unauthenticated."""

    def test_push_unauthenticated_returns_401(self, app_client):
        client, _ = app_client
        resp = client.post(
            "/api/sync/push",
            data=json.dumps({"actions": []}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated push, got {resp.status_code}"
        )

    def test_pull_unauthenticated_returns_401(self, app_client):
        client, _ = app_client
        resp = client.get("/api/sync/pull")
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated pull, got {resp.status_code}"
        )

    def test_state_unauthenticated_returns_401(self, app_client):
        client, _ = app_client
        resp = client.get("/api/sync/state")
        assert resp.status_code == 401, (
            f"Expected 401 for unauthenticated state, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 2. sync_push — drill_result
# ---------------------------------------------------------------------------

class TestSyncPushDrillResult:

    def test_correct_drill_result_increments_streak(self, app_client):
        """A correct drill_result should increment streak_correct and total_correct."""
        client, conn = app_client
        user = _login(client, conn)
        item_id = _insert_content_item(conn)
        progress_id = _insert_progress(conn, user["id"], item_id)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({
                "actions": [{
                    "type": "drill_result",
                    "data": {
                        "content_item_id": item_id,
                        "modality": "reading",
                        "correct": True,
                    },
                    "timestamp": "2026-02-25 10:00:00",
                }]
            }),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 1
        assert data["errors"] == []
        assert data["total"] == 1

        # Verify DB state
        row = conn.execute(
            "SELECT streak_correct, total_attempts, total_correct FROM progress WHERE id = ?",
            (progress_id,),
        ).fetchone()
        assert row["streak_correct"] == 1
        assert row["total_attempts"] == 1
        assert row["total_correct"] == 1

    def test_incorrect_drill_result_increments_streak_incorrect(self, app_client):
        """An incorrect drill_result should increment streak_incorrect and reset streak_correct."""
        client, conn = app_client
        user = _login(client, conn)
        item_id = _insert_content_item(conn)
        progress_id = _insert_progress(conn, user["id"], item_id)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({
                "actions": [{
                    "type": "drill_result",
                    "data": {
                        "content_item_id": item_id,
                        "modality": "reading",
                        "correct": False,
                    },
                    "timestamp": "2026-02-25 10:00:00",
                }]
            }),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 1

        row = conn.execute(
            "SELECT streak_correct, streak_incorrect, total_attempts, total_correct FROM progress WHERE id = ?",
            (progress_id,),
        ).fetchone()
        assert row["streak_incorrect"] == 1
        assert row["streak_correct"] == 0
        assert row["total_attempts"] == 1
        assert row["total_correct"] == 0

    def test_drill_result_missing_content_item_id_still_processed(self, app_client):
        """A drill_result with no content_item_id should be counted as processed
        (the processor returns early without error)."""
        client, conn = app_client
        _login(client, conn)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({
                "actions": [{
                    "type": "drill_result",
                    "data": {"modality": "reading", "correct": True},
                    "timestamp": "2026-02-25 10:00:00",
                }]
            }),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 1
        assert data["errors"] == []


# ---------------------------------------------------------------------------
# 3. sync_push — vocab_encounter
# ---------------------------------------------------------------------------

class TestSyncPushVocabEncounter:

    def test_valid_vocab_encounter_creates_row(self, app_client):
        """A vocab_encounter action should insert a row into vocab_encounter."""
        client, conn = app_client
        user = _login(client, conn)
        item_id = _insert_content_item(conn, hanzi="谢谢")

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({
                "actions": [{
                    "type": "vocab_encounter",
                    "data": {
                        "hanzi": "谢谢",
                        "source_type": "reading",
                        "source_id": "passage-1",
                    },
                }]
            }),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 1
        assert data["errors"] == []

        # Verify the encounter was inserted
        row = conn.execute(
            "SELECT hanzi, source_type, source_id, content_item_id FROM vocab_encounter WHERE hanzi = ?",
            ("谢谢",),
        ).fetchone()
        assert row is not None
        assert row["hanzi"] == "谢谢"
        assert row["source_type"] == "reading"
        assert row["source_id"] == "passage-1"
        assert row["content_item_id"] == item_id

    def test_vocab_encounter_unknown_hanzi_creates_row_without_content_item(self, app_client):
        """A vocab_encounter for an unknown hanzi inserts with content_item_id=None."""
        client, conn = app_client
        _login(client, conn)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({
                "actions": [{
                    "type": "vocab_encounter",
                    "data": {
                        "hanzi": "龘",
                        "source_type": "listening",
                    },
                }]
            }),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 1

        row = conn.execute(
            "SELECT content_item_id FROM vocab_encounter WHERE hanzi = ?",
            ("龘",),
        ).fetchone()
        assert row is not None
        assert row["content_item_id"] is None

    def test_vocab_encounter_empty_hanzi_skipped(self, app_client):
        """A vocab_encounter with empty hanzi should be silently processed (early return)."""
        client, conn = app_client
        _login(client, conn)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({
                "actions": [{
                    "type": "vocab_encounter",
                    "data": {"hanzi": "", "source_type": "reading"},
                }]
            }),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 1
        assert data["errors"] == []


# ---------------------------------------------------------------------------
# 4. sync_push — media_watched
# ---------------------------------------------------------------------------

class TestSyncPushMediaWatched:

    def test_valid_media_watched_calls_processor(self, app_client):
        """A media_watched action should call record_media_watched and count as processed."""
        client, conn = app_client
        _login(client, conn)

        with patch("mandarin.web.sync_routes._process_media_watched") as mock_proc:
            resp = client.post(
                "/api/sync/push",
                data=json.dumps({
                    "actions": [{
                        "type": "media_watched",
                        "data": {
                            "media_id": "vid-001",
                            "score": 0.85,
                        },
                    }]
                }),
                headers=_JSON_HEADERS,
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["processed"] == 1
            assert data["errors"] == []
            mock_proc.assert_called_once()

    def test_media_watched_empty_media_id_calls_processor(self, app_client):
        """A media_watched with empty media_id should still be counted as processed
        (the processor handles the empty id internally)."""
        client, conn = app_client
        _login(client, conn)

        with patch("mandarin.web.sync_routes._process_media_watched") as mock_proc:
            resp = client.post(
                "/api/sync/push",
                data=json.dumps({
                    "actions": [{
                        "type": "media_watched",
                        "data": {"media_id": "", "score": 0.0},
                    }]
                }),
                headers=_JSON_HEADERS,
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["processed"] == 1


# ---------------------------------------------------------------------------
# 5. sync_push — edge cases
# ---------------------------------------------------------------------------

class TestSyncPushEdgeCases:

    def test_unknown_action_type_returns_error(self, app_client):
        """An unknown action type should appear in the errors list."""
        client, conn = app_client
        _login(client, conn)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({
                "actions": [{
                    "type": "bogus_type",
                    "data": {},
                }]
            }),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 0
        assert data["total"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["index"] == 0
        assert "bogus_type" in data["errors"][0]["error"]

    def test_empty_actions_list(self, app_client):
        """An empty actions list should return processed=0, total=0, no errors."""
        client, conn = app_client
        _login(client, conn)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({"actions": []}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 0
        assert data["total"] == 0
        assert data["errors"] == []

    def test_non_list_actions_returns_validation_error(self, app_client):
        """If actions is not a list, the endpoint returns a validation error."""
        client, conn = app_client
        _login(client, conn)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({"actions": "not-a-list"}),
            headers=_JSON_HEADERS,
        )
        # The api_error function may return 400 or 422 depending on implementation
        assert resp.status_code in (400, 422), (
            f"Expected 400/422 for non-list actions, got {resp.status_code}"
        )
        data = resp.get_json()
        assert "error" in data or "message" in data

    def test_mixed_valid_and_invalid_actions(self, app_client):
        """A batch with both valid and invalid actions should process valid ones
        and report errors for invalid ones."""
        client, conn = app_client
        user = _login(client, conn)
        item_id = _insert_content_item(conn, hanzi="早上好")
        _insert_progress(conn, user["id"], item_id)

        resp = client.post(
            "/api/sync/push",
            data=json.dumps({
                "actions": [
                    {
                        "type": "drill_result",
                        "data": {
                            "content_item_id": item_id,
                            "modality": "reading",
                            "correct": True,
                        },
                        "timestamp": "2026-02-25 10:00:00",
                    },
                    {
                        "type": "unknown_action",
                        "data": {},
                    },
                    {
                        "type": "vocab_encounter",
                        "data": {
                            "hanzi": "早上好",
                            "source_type": "reading",
                        },
                    },
                ]
            }),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 3
        assert data["processed"] == 2
        assert len(data["errors"]) == 1
        assert data["errors"][0]["index"] == 1

    def test_no_body_returns_processed_zero(self, app_client):
        """POST with no JSON body should still succeed with empty actions."""
        client, conn = app_client
        _login(client, conn)

        resp = client.post(
            "/api/sync/push",
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 0
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# 6. sync_pull
# ---------------------------------------------------------------------------

class TestSyncPull:

    def test_pull_no_data_returns_empty_lists(self, app_client):
        """Pull with no progress or sessions returns empty lists."""
        client, conn = app_client
        _login(client, conn)

        resp = client.get("/api/sync/pull")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["progress"] == []
        assert data["sessions"] == []
        assert "since" in data

    def test_pull_returns_progress_data(self, app_client):
        """Pull should return progress rows for the authenticated user."""
        client, conn = app_client
        user = _login(client, conn)
        item_id = _insert_content_item(conn)
        _insert_progress(conn, user["id"], item_id,
                         last_review_date="2026-02-20 12:00:00")

        resp = client.get("/api/sync/pull")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["progress"]) == 1
        assert data["progress"][0]["content_item_id"] == item_id
        assert data["progress"][0]["modality"] == "reading"

    def test_pull_returns_session_data(self, app_client):
        """Pull should return session_log rows for the authenticated user."""
        client, conn = app_client
        user = _login(client, conn)
        _insert_session_log(conn, user["id"],
                            started_at="2026-02-20 10:00:00")

        resp = client.get("/api/sync/pull")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_type"] == "standard"
        assert data["sessions"][0]["items_completed"] == 5

    def test_pull_since_filters_old_data(self, app_client):
        """The since parameter should filter out data older than the timestamp."""
        client, conn = app_client
        user = _login(client, conn)

        # Old progress — before the since cutoff
        item_old = _insert_content_item(conn, hanzi="旧", pinyin="jiù", english="old")
        _insert_progress(conn, user["id"], item_old,
                         last_review_date="2026-01-01 00:00:00")

        # New progress — after the since cutoff
        item_new = _insert_content_item(conn, hanzi="新", pinyin="xīn", english="new")
        _insert_progress(conn, user["id"], item_new,
                         last_review_date="2026-02-25 12:00:00")

        # Old session
        _insert_session_log(conn, user["id"], started_at="2026-01-01 00:00:00")

        # New session
        _insert_session_log(conn, user["id"], started_at="2026-02-25 14:00:00")

        resp = client.get("/api/sync/pull?since=2026-02-01 00:00:00")
        assert resp.status_code == 200
        data = resp.get_json()

        # Only the new progress should appear
        assert len(data["progress"]) == 1
        assert data["progress"][0]["content_item_id"] == item_new

        # Only the new session should appear
        assert len(data["sessions"]) == 1

    def test_pull_default_since_returns_all(self, app_client):
        """Without a since parameter, all data should be returned."""
        client, conn = app_client
        user = _login(client, conn)
        item_id = _insert_content_item(conn)
        _insert_progress(conn, user["id"], item_id,
                         last_review_date="2020-01-01 00:00:00")

        resp = client.get("/api/sync/pull")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["progress"]) == 1
        assert data["since"] == "1970-01-01 00:00:00"

    def test_pull_does_not_return_other_users_data(self, app_client):
        """Pull should only return data for the authenticated user, not others."""
        client, conn = app_client
        user = _login(client, conn)
        item_id = _insert_content_item(conn)

        # Create a second user and insert progress for them
        other_user = create_user(conn, "other@example.com", "otherpass12345", "Other")
        conn.execute(
            """INSERT INTO progress
               (user_id, content_item_id, modality, streak_correct, streak_incorrect,
                total_attempts, total_correct, last_review_date, mastery_stage)
               VALUES (?, ?, 'reading', 0, 0, 0, 0, '2026-02-20 12:00:00', 'seen')""",
            (other_user["id"], item_id),
        )
        conn.commit()

        resp = client.get("/api/sync/pull")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["progress"]) == 0


# ---------------------------------------------------------------------------
# 7. sync_state
# ---------------------------------------------------------------------------

class TestSyncState:

    def test_state_returns_hash_and_metadata(self, app_client):
        """State endpoint should return hash, last_updated, and item_count."""
        client, conn = app_client
        _login(client, conn)

        resp = client.get("/api/sync/state")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "hash" in data
        assert "last_updated" in data
        assert "item_count" in data
        assert isinstance(data["hash"], str)
        assert len(data["hash"]) == 12  # sha256[:12]

    def test_state_with_no_progress_returns_zero_count(self, app_client):
        """With no progress rows, item_count should be 0."""
        client, conn = app_client
        _login(client, conn)

        resp = client.get("/api/sync/state")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["item_count"] == 0
        assert data["last_updated"] == ""

    def test_state_changes_after_progress_update(self, app_client):
        """Adding a progress row should change the state hash."""
        client, conn = app_client
        user = _login(client, conn)

        # Get initial state
        resp1 = client.get("/api/sync/state")
        state1 = resp1.get_json()

        # Add progress
        item_id = _insert_content_item(conn)
        _insert_progress(conn, user["id"], item_id,
                         last_review_date="2026-02-25 12:00:00")

        # Get new state
        resp2 = client.get("/api/sync/state")
        state2 = resp2.get_json()

        assert state2["item_count"] == 1
        assert state2["last_updated"] == "2026-02-25 12:00:00"
        assert state1["hash"] != state2["hash"], (
            "State hash should change after adding progress"
        )

    def test_state_reflects_correct_count(self, app_client):
        """item_count should reflect the number of progress rows for this user."""
        client, conn = app_client
        user = _login(client, conn)

        item1 = _insert_content_item(conn, hanzi="一", pinyin="yī", english="one")
        item2 = _insert_content_item(conn, hanzi="二", pinyin="èr", english="two")
        item3 = _insert_content_item(conn, hanzi="三", pinyin="sān", english="three")

        _insert_progress(conn, user["id"], item1, last_review_date="2026-02-20 10:00:00")
        _insert_progress(conn, user["id"], item2, last_review_date="2026-02-21 10:00:00")
        _insert_progress(conn, user["id"], item3, last_review_date="2026-02-22 10:00:00")

        resp = client.get("/api/sync/state")
        data = resp.get_json()
        assert data["item_count"] == 3
        assert data["last_updated"] == "2026-02-22 10:00:00"
