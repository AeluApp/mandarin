"""Tests for GenAI admin routes — corpus coverage, usage maps, prompt registry, session analysis.

All endpoints require admin + MFA.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from mandarin.web import create_app
from mandarin.web.auth_routes import User
from mandarin.auth import create_user
from werkzeug.security import generate_password_hash as _orig_gen


class _FakeConn:
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
    """Unauthenticated Flask test client."""
    conn, _ = test_db
    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)
    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def admin_client(test_db):
    """Flask test client logged in as admin with TOTP enabled."""
    conn, _ = test_db

    # Promote bootstrap user to admin with TOTP
    conn.execute(
        "UPDATE user SET is_admin = 1, totp_enabled = 1, is_active = 1 WHERE id = 1"
    )
    conn.commit()

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)

    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


@pytest.fixture
def nonadmin_client(test_db):
    """Flask test client logged in as a regular (non-admin) user."""
    conn, _ = test_db

    conn.execute("UPDATE user SET is_active = 1, is_admin = 0 WHERE id = 1")
    conn.commit()

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    fake = _FakeConn(conn)

    with patch("mandarin.db.connection", return_value=fake):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# Access control — unauthenticated
# ---------------------------------------------------------------------------

class TestGenaiUnauthenticated:

    def test_corpus_coverage_unauthenticated(self, app_client):
        c, _ = app_client
        resp = c.get("/api/admin/genai/corpus-coverage")
        assert resp.status_code in (302, 401)

    def test_prompt_registry_unauthenticated(self, app_client):
        c, _ = app_client
        resp = c.get("/api/admin/genai/prompt-registry")
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Access control — non-admin
# ---------------------------------------------------------------------------

class TestGenaiNonAdmin:

    def test_corpus_coverage_nonadmin_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/genai/corpus-coverage")
        assert resp.status_code == 403

    def test_prompt_registry_nonadmin_403(self, nonadmin_client):
        c, _ = nonadmin_client
        resp = c.get("/api/admin/genai/prompt-registry")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin access — successful
# ---------------------------------------------------------------------------

class TestGenaiCorpusCoverage:

    def test_corpus_coverage_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/genai/corpus-coverage")
        assert resp.status_code == 200

    def test_corpus_coverage_returns_json(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/genai/corpus-coverage")
        data = resp.get_json()
        assert isinstance(data, dict)


class TestGenaiPromptRegistry:

    def test_prompt_registry_returns_200(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/genai/prompt-registry")
        assert resp.status_code == 200

    def test_prompt_registry_has_registry_key(self, admin_client):
        c, _ = admin_client
        resp = c.get("/api/admin/genai/prompt-registry")
        data = resp.get_json()
        assert "registry" in data
        assert isinstance(data["registry"], dict)


class TestGenaiSessionAnalysis:

    def test_session_analysis_unauthenticated(self, app_client):
        """Unauthenticated requests are blocked."""
        c, _ = app_client
        resp = c.get("/api/admin/genai/session-analysis/1")
        assert resp.status_code in (302, 401)

    def test_session_analysis_nonadmin_403(self, nonadmin_client):
        """Non-admin users get 403."""
        c, _ = nonadmin_client
        resp = c.get("/api/admin/genai/session-analysis/1")
        assert resp.status_code == 403
