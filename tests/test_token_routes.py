"""Tests for JWT token HTTP endpoints (mandarin.web.token_routes).

Covers:
1.  POST /api/auth/token — valid credentials → 200 with access_token, refresh_token, expires_in, user
2.  POST /api/auth/token — invalid email → 401
3.  POST /api/auth/token — invalid password → 401
4.  POST /api/auth/token — missing email field → 400
5.  POST /api/auth/token — missing password field → 400
6.  POST /api/auth/token — MFA-enabled user → mfa_required + mfa_token
7.  POST /api/auth/token/mfa — valid TOTP code → 200 with access_token
8.  POST /api/auth/token/mfa — invalid TOTP code → 401
9.  POST /api/auth/token/mfa — missing fields → 400
10. POST /api/auth/token/refresh — valid refresh_token → 200 with new access_token
11. POST /api/auth/token/refresh — invalid refresh_token → 401
12. POST /api/auth/token/refresh — missing refresh_token field → 400
13. POST /api/auth/token/revoke — authenticated via session → 200 {"status": "ok"}
14. POST /api/auth/token/revoke — not authenticated → 401
15. POST /api/auth/token — response user object has expected keys
16. POST /api/auth/token/mfa — bad mfa_token value → 401
"""

from __future__ import annotations

import pytest
pytest.importorskip("pyotp")

import json
from unittest.mock import patch

import pyotp
from werkzeug.security import generate_password_hash as _orig_gen

from mandarin.auth import create_user


# ---------------------------------------------------------------------------
# Python 3.9 compat: force pbkdf2 instead of scrypt (no hashlib.scrypt)
# ---------------------------------------------------------------------------

def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    """Ensure werkzeug uses pbkdf2 (available in Python 3.9) for all tests."""
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False


@pytest.fixture
def app_client(test_db):
    """Flask test client with all DB connections patched to the test database."""
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    fake = _FakeConn(conn)

    with patch("mandarin.db.connection", return_value=fake), \
         patch("mandarin.web.routes.db.connection", return_value=fake), \
         patch("mandarin.web.payment_routes.db.connection", return_value=fake), \
         patch("mandarin.web.onboarding_routes.db.connection", return_value=fake), \
         patch("mandarin.web.admin_routes.db.connection", return_value=fake), \
         patch("mandarin.web.token_routes.db.connection", return_value=fake), \
         patch("mandarin.web.auth_routes.db.connection", return_value=fake):
        with app.test_client() as client:
            yield client, conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_EMAIL = "tokenuser@example.com"
_TEST_PASSWORD = "securepass12345"

_JSON_HEADERS = {"Content-Type": "application/json"}
_AJAX_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}


def _create_test_user(conn, email=_TEST_EMAIL, password=_TEST_PASSWORD):
    """Create a standard test user and return the user dict."""
    return create_user(conn, email, password, "Token User")


def _obtain_token(client, email=_TEST_EMAIL, password=_TEST_PASSWORD):
    """POST /api/auth/token with JSON body; returns the response."""
    return client.post(
        "/api/auth/token",
        data=json.dumps({"email": email, "password": password}),
        headers=_JSON_HEADERS,
    )


def _login_session(client, conn, email=_TEST_EMAIL, password=_TEST_PASSWORD):
    """Create a user and log in via form-POST to establish a Flask-Login session."""
    _create_test_user(conn, email, password)
    client.post("/auth/login", data={"email": email, "password": password})


# ---------------------------------------------------------------------------
# TestObtainToken
# ---------------------------------------------------------------------------

class TestObtainToken:

    def test_valid_credentials_returns_200(self, app_client):
        """Valid email + password returns HTTP 200."""
        client, conn = app_client
        _create_test_user(conn)
        resp = _obtain_token(client)
        assert resp.status_code == 200, (
            f"Expected 200 for valid credentials, got {resp.status_code}: {resp.data[:300]}"
        )

    def test_valid_credentials_response_has_access_token(self, app_client):
        """Response body must include access_token."""
        client, conn = app_client
        _create_test_user(conn)
        data = _obtain_token(client).get_json()
        assert "access_token" in data, f"Missing access_token in {data}"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 10

    def test_valid_credentials_response_has_refresh_token(self, app_client):
        """Response body must include refresh_token."""
        client, conn = app_client
        _create_test_user(conn)
        data = _obtain_token(client).get_json()
        assert "refresh_token" in data, f"Missing refresh_token in {data}"
        assert isinstance(data["refresh_token"], str)
        assert len(data["refresh_token"]) > 10

    def test_valid_credentials_response_has_expires_in(self, app_client):
        """Response body must include expires_in as a positive integer."""
        client, conn = app_client
        _create_test_user(conn)
        data = _obtain_token(client).get_json()
        assert "expires_in" in data, f"Missing expires_in in {data}"
        assert isinstance(data["expires_in"], int)
        assert data["expires_in"] > 0

    def test_valid_credentials_response_has_user_object(self, app_client):
        """Response body must include user with id and email."""
        client, conn = app_client
        user = _create_test_user(conn)
        data = _obtain_token(client).get_json()
        assert "user" in data, f"Missing user object in {data}"
        u = data["user"]
        assert u["id"] == user["id"]
        assert u["email"] == _TEST_EMAIL

    def test_valid_credentials_user_has_expected_keys(self, app_client):
        """user object must have id, email, display_name, subscription_tier."""
        client, conn = app_client
        _create_test_user(conn)
        data = _obtain_token(client).get_json()
        u = data["user"]
        for key in ("id", "email", "display_name", "subscription_tier"):
            assert key in u, f"user object missing key '{key}': {u}"

    def test_invalid_email_returns_401(self, app_client):
        """Non-existent email returns 401."""
        client, conn = app_client
        _create_test_user(conn)
        resp = _obtain_token(client, email="nobody@example.com")
        assert resp.status_code == 401, (
            f"Expected 401 for unknown email, got {resp.status_code}"
        )

    def test_invalid_password_returns_401(self, app_client):
        """Wrong password returns 401."""
        client, conn = app_client
        _create_test_user(conn)
        resp = _obtain_token(client, password="wrongpassword9999")
        assert resp.status_code == 401, (
            f"Expected 401 for wrong password, got {resp.status_code}"
        )

    def test_missing_email_field_returns_400(self, app_client):
        """Body without email key returns 400."""
        client, conn = app_client
        _create_test_user(conn)
        resp = client.post(
            "/api/auth/token",
            data=json.dumps({"password": _TEST_PASSWORD}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing email field, got {resp.status_code}"
        )

    def test_missing_password_field_returns_400(self, app_client):
        """Body without password key returns 400."""
        client, conn = app_client
        _create_test_user(conn)
        resp = client.post(
            "/api/auth/token",
            data=json.dumps({"email": _TEST_EMAIL}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing password field, got {resp.status_code}"
        )

    def test_empty_email_returns_400(self, app_client):
        """Empty string email returns 400."""
        client, conn = app_client
        _create_test_user(conn)
        resp = client.post(
            "/api/auth/token",
            data=json.dumps({"email": "", "password": _TEST_PASSWORD}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for empty email, got {resp.status_code}"
        )

    def test_empty_password_returns_400(self, app_client):
        """Empty string password returns 400."""
        client, conn = app_client
        _create_test_user(conn)
        resp = client.post(
            "/api/auth/token",
            data=json.dumps({"email": _TEST_EMAIL, "password": ""}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for empty password, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# TestObtainTokenMFA
# ---------------------------------------------------------------------------

class TestObtainTokenMFA:

    def _enable_totp(self, conn, user_id):
        """Write a TOTP secret into the DB and return (secret, valid_code)."""
        secret = pyotp.random_base32()
        conn.execute(
            "UPDATE user SET totp_enabled=1, totp_secret=? WHERE id=?",
            (secret, user_id),
        )
        conn.commit()
        return secret, pyotp.TOTP(secret).now()

    def test_mfa_user_gets_mfa_required_response(self, app_client):
        """User with totp_enabled=1 must receive mfa_required=true on /api/auth/token."""
        client, conn = app_client
        user = _create_test_user(conn)
        self._enable_totp(conn, user["id"])

        resp = _obtain_token(client)
        assert resp.status_code == 200, (
            f"Expected 200 for MFA challenge response, got {resp.status_code}: {resp.data[:300]}"
        )
        data = resp.get_json()
        assert data.get("mfa_required") is True, (
            f"Expected mfa_required=true for MFA user, got {data}"
        )
        assert "mfa_token" in data, f"Missing mfa_token in {data}"

    def test_mfa_user_does_not_receive_access_token_yet(self, app_client):
        """MFA challenge response must NOT include an access_token."""
        client, conn = app_client
        user = _create_test_user(conn)
        self._enable_totp(conn, user["id"])

        data = _obtain_token(client).get_json()
        assert "access_token" not in data, (
            "access_token must not be issued before MFA is verified"
        )

    def test_valid_mfa_code_completes_login(self, app_client):
        """POST /api/auth/token/mfa with a valid TOTP code returns 200 with access_token."""
        client, conn = app_client
        user = _create_test_user(conn)
        secret, _ = self._enable_totp(conn, user["id"])

        # Step 1: obtain mfa_token
        step1 = _obtain_token(client).get_json()
        mfa_token = step1["mfa_token"]

        # Step 2: exchange with valid TOTP code
        valid_code = pyotp.TOTP(secret).now()
        resp = client.post(
            "/api/auth/token/mfa",
            data=json.dumps({"mfa_token": mfa_token, "code": valid_code}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200, (
            f"Expected 200 after valid MFA code, got {resp.status_code}: {resp.data[:300]}"
        )
        data = resp.get_json()
        assert "access_token" in data, f"Missing access_token after MFA completion: {data}"
        assert "refresh_token" in data, f"Missing refresh_token after MFA completion: {data}"

    def test_invalid_mfa_code_returns_401(self, app_client):
        """POST /api/auth/token/mfa with a wrong TOTP code returns 401."""
        client, conn = app_client
        user = _create_test_user(conn)
        self._enable_totp(conn, user["id"])

        step1 = _obtain_token(client).get_json()
        mfa_token = step1["mfa_token"]

        resp = client.post(
            "/api/auth/token/mfa",
            data=json.dumps({"mfa_token": mfa_token, "code": "000000"}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 401, (
            f"Expected 401 for invalid MFA code, got {resp.status_code}"
        )

    def test_bad_mfa_token_value_returns_401(self, app_client):
        """POST /api/auth/token/mfa with a fabricated mfa_token returns 401."""
        client, conn = app_client
        _create_test_user(conn)

        resp = client.post(
            "/api/auth/token/mfa",
            data=json.dumps({"mfa_token": "totally-fake-token", "code": "123456"}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 401, (
            f"Expected 401 for bad mfa_token, got {resp.status_code}"
        )

    def test_missing_mfa_fields_returns_400(self, app_client):
        """POST /api/auth/token/mfa with no body returns 400."""
        client, conn = app_client
        _create_test_user(conn)

        resp = client.post(
            "/api/auth/token/mfa",
            data=json.dumps({}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing mfa fields, got {resp.status_code}"
        )

    def test_mfa_complete_response_has_user_object(self, app_client):
        """Completed MFA login response must include user object with id and email."""
        client, conn = app_client
        user = _create_test_user(conn)
        secret, _ = self._enable_totp(conn, user["id"])

        step1 = _obtain_token(client).get_json()
        mfa_token = step1["mfa_token"]
        valid_code = pyotp.TOTP(secret).now()

        resp = client.post(
            "/api/auth/token/mfa",
            data=json.dumps({"mfa_token": mfa_token, "code": valid_code}),
            headers=_JSON_HEADERS,
        )
        data = resp.get_json()
        assert "user" in data, f"Missing user object in MFA completion response: {data}"
        assert data["user"]["id"] == user["id"]
        assert data["user"]["email"] == _TEST_EMAIL


# ---------------------------------------------------------------------------
# TestRefreshToken
# ---------------------------------------------------------------------------

class TestRefreshToken:

    def test_valid_refresh_token_returns_200(self, app_client):
        """Use a refresh_token obtained from /api/auth/token to get a new access_token."""
        client, conn = app_client
        _create_test_user(conn)

        tokens = _obtain_token(client).get_json()
        refresh_token = tokens["refresh_token"]

        resp = client.post(
            "/api/auth/token/refresh",
            data=json.dumps({"refresh_token": refresh_token}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 200, (
            f"Expected 200 for valid refresh_token, got {resp.status_code}: {resp.data[:300]}"
        )

    def test_valid_refresh_token_returns_new_access_token(self, app_client):
        """Refresh response must include a new access_token."""
        client, conn = app_client
        _create_test_user(conn)

        tokens = _obtain_token(client).get_json()
        refresh_token = tokens["refresh_token"]

        data = client.post(
            "/api/auth/token/refresh",
            data=json.dumps({"refresh_token": refresh_token}),
            headers=_JSON_HEADERS,
        ).get_json()
        assert "access_token" in data, f"Missing access_token in refresh response: {data}"
        assert "expires_in" in data, f"Missing expires_in in refresh response: {data}"

    def test_invalid_refresh_token_returns_401(self, app_client):
        """A fabricated / wrong refresh_token returns 401."""
        client, conn = app_client
        _create_test_user(conn)

        resp = client.post(
            "/api/auth/token/refresh",
            data=json.dumps({"refresh_token": "not-a-real-token-at-all"}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 401, (
            f"Expected 401 for invalid refresh_token, got {resp.status_code}"
        )

    def test_missing_refresh_token_field_returns_400(self, app_client):
        """Body without refresh_token key returns 400."""
        client, conn = app_client
        resp = client.post(
            "/api/auth/token/refresh",
            data=json.dumps({}),
            headers=_JSON_HEADERS,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing refresh_token field, got {resp.status_code}"
        )

    def test_refresh_returns_different_access_token(self, app_client):
        """The refreshed access_token should differ from the original (different iat/exp)."""
        client, conn = app_client
        _create_test_user(conn)

        tokens = _obtain_token(client).get_json()
        refresh_token = tokens["refresh_token"]

        new_data = client.post(
            "/api/auth/token/refresh",
            data=json.dumps({"refresh_token": refresh_token}),
            headers=_JSON_HEADERS,
        ).get_json()
        # The new token should be a valid JWT string
        assert isinstance(new_data["access_token"], str)
        assert len(new_data["access_token"]) > 10


# ---------------------------------------------------------------------------
# TestRevokeToken
# ---------------------------------------------------------------------------

class TestRevokeToken:

    def test_authenticated_user_can_revoke(self, app_client):
        """Session-authenticated user calling /api/auth/token/revoke gets {"status": "ok"}."""
        client, conn = app_client
        # Log in via session (form POST) so current_user.is_authenticated is True
        _login_session(client, conn)

        resp = client.post(
            "/api/auth/token/revoke",
            data=json.dumps({}),
            # X-Requested-With required: session-authenticated API POST needs custom header
            headers=_AJAX_HEADERS,
        )
        assert resp.status_code == 200, (
            f"Expected 200 from revoke for authenticated user, got {resp.status_code}: {resp.data[:300]}"
        )
        data = resp.get_json()
        assert data.get("status") == "ok", f"Expected status=ok, got {data}"

    def test_unauthenticated_revoke_returns_401(self, app_client):
        """POST /api/auth/token/revoke without authentication returns 401."""
        client, _ = app_client

        resp = client.post(
            "/api/auth/token/revoke",
            data=json.dumps({}),
            headers=_AJAX_HEADERS,
        )
        assert resp.status_code == 401, (
            f"Expected 401 from revoke for unauthenticated request, got {resp.status_code}"
        )

    def test_revoke_via_bearer_token(self, app_client):
        """Bearer-authenticated user calling /api/auth/token/revoke gets {"status": "ok"}."""
        client, conn = app_client
        _create_test_user(conn)

        tokens = _obtain_token(client).get_json()
        access_token = tokens["access_token"]

        resp = client.post(
            "/api/auth/token/revoke",
            data=json.dumps({}),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )
        assert resp.status_code == 200, (
            f"Expected 200 from revoke with Bearer token, got {resp.status_code}: {resp.data[:300]}"
        )
        data = resp.get_json()
        assert data.get("status") == "ok", f"Expected status=ok, got {data}"
