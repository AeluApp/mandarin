"""Tests for LTI 1.3 routes (mandarin.web.lti_routes).

Covers:
- OIDC login initiation with valid platform config -> redirect
- OIDC login with unregistered platform -> 403
- OIDC login with missing fields -> 403
- OIDC login stores session state and nonce
- OIDC login includes lti_message_hint when provided
- OIDC login via GET method
- LTI launch with missing id_token -> 400
- LTI launch with invalid state -> 403
- LTI launch with malformed JWT -> 400
- LTI launch with unknown platform -> 403
- LTI launch with JWKS fetch failure -> 502
- LTI launch with no matching key -> 403
- LTI launch with invalid signature (verification failure) -> 403
- LTI launch with wrong nonce -> 403
- LTI launch with unsupported message type -> 400
- LTI launch with no email and no mapping -> 400
- LTI launch with valid JWT, new user -> creates user + mapping, redirects
- LTI launch with valid JWT, existing mapping -> logs in, redirects
- LTI launch with valid JWT, email match -> creates mapping, redirects
- LTI launch stores AGS context in session
- Grade passback without authentication -> 401
- Grade passback without LTI context -> 400
- Grade passback with missing lineitem -> 400
- Grade passback with missing score -> 400
- Grade passback with non-numeric score -> 400
- Grade passback with valid request -> 200
- Grade passback clamps score to [0, 1]
- Grade passback with token fetch failure -> 502
- Grade passback with no access_token -> 502
- Grade passback with score post failure -> 502
- Grade passback with missing platform -> 400
- JWKS endpoint returns 200
- JWKS endpoint returns JSON with keys array
- JWKS endpoint content-type is JSON
- @api_error_handler catches internal errors on /lti/jwks
"""

import json
import time
from unittest.mock import patch, MagicMock

import pytest
pytest.importorskip("pylti1p3", reason="LTI dependencies not installed")

from mandarin.auth import create_user


# ---------------------------------------------------------------------------
# Password hashing compat for Python 3.9
# ---------------------------------------------------------------------------

from werkzeug.security import generate_password_hash as _orig_gen


def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


# ---------------------------------------------------------------------------
# Fake DB context-manager wrapper (same pattern as test_classroom_routes)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Wraps a real sqlite3.Connection so it works as both a context manager
    (for ``with db.connection() as conn:``) and as a raw connection object
    (for ``conn = db.ensure_db()``).
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
    """Flask test client with all DB access patched to the test database.

    Yields (client, conn).
    """
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    fake = _FakeConn(conn)
    fake_connection = lambda: fake  # noqa: E731
    fake_ensure_db = lambda: conn  # noqa: E731

    with patch("mandarin.db.connection", fake_connection), \
         patch("mandarin.web.auth_routes.db.connection", fake_connection), \
         patch("mandarin.web.routes.db.connection", fake_connection), \
         patch("mandarin.web.payment_routes.db.connection", fake_connection), \
         patch("mandarin.web.onboarding_routes.db.connection", fake_connection), \
         patch("mandarin.web.admin_routes.db.connection", fake_connection), \
         patch("mandarin.web.classroom_routes.db.connection", fake_connection), \
         patch("mandarin.web.classroom_routes.db.ensure_db", fake_ensure_db):
        with app.test_client() as client:
            yield client, conn


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------

def _login(client, conn, email="student@example.com", password="studentpass123"):
    """Create a student user and log them in. Returns the user dict."""
    user = create_user(conn, email, password, "Student")
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user["id"])
        sess["_fresh"] = True
    return user


# ---------------------------------------------------------------------------
# Platform registration helper
# ---------------------------------------------------------------------------

def _register_platform(conn, issuer="https://lms.example.edu",
                       client_id="mandarin-app-123",
                       auth_url="https://lms.example.edu/auth",
                       token_url="https://lms.example.edu/token",
                       jwks_url="https://lms.example.edu/.well-known/jwks.json"):
    """Insert a platform registration into the test database."""
    conn.execute(
        """INSERT INTO lti_platform (issuer, client_id, auth_url, token_url, jwks_url)
           VALUES (?, ?, ?, ?, ?)""",
        (issuer, client_id, auth_url, token_url, jwks_url),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# JWT mock helpers
# ---------------------------------------------------------------------------

def _build_lti_claims(issuer="https://lms.example.edu",
                      client_id="mandarin-app-123",
                      sub="user-abc-123",
                      nonce="test-nonce",
                      email="ltiuser@example.com",
                      name="LTI User"):
    """Build a standard LTI 1.3 resource link request claims dict."""
    now = int(time.time())
    return {
        "iss": issuer,
        "aud": client_id,
        "sub": sub,
        "nonce": nonce,
        "iat": now,
        "exp": now + 3600,
        "email": email,
        "name": name,
        "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti/claim/resource_link": {
            "id": "resource-link-1",
        },
    }


def _make_mock_pyjwt(claims, kid="test-key-1", decode_error=None,
                     header_error=None, verify_error=None):
    """Create a mock pyjwt module that simulates JWT operations.

    Args:
        claims: The claims dict to return from decode().
        kid: The key ID in the JWT header.
        decode_error: Exception to raise on get_unverified_header.
        header_error: Exception to raise on get_unverified_header.
        verify_error: Exception to raise on verified decode().
    """
    import jwt as real_pyjwt

    mock = MagicMock()
    mock.exceptions = real_pyjwt.exceptions

    if header_error:
        mock.get_unverified_header.side_effect = header_error
    else:
        mock.get_unverified_header.return_value = {"kid": kid, "alg": "RS256"}

    if decode_error:
        mock.decode.side_effect = decode_error
    else:
        # First call is unverified decode, second is verified decode
        def _decode_side_effect(token, *args, **kwargs):
            opts = kwargs.get("options", {})
            if opts.get("verify_signature") is False:
                return claims
            if verify_error:
                raise verify_error
            return claims
        mock.decode.side_effect = _decode_side_effect

    # from_jwk returns a mock public key
    mock.algorithms.RSAAlgorithm.from_jwk.return_value = MagicMock(name="public_key")

    return mock


# ---------------------------------------------------------------------------
# 1. OIDC Login
# ---------------------------------------------------------------------------

class TestOidcLogin:
    """POST /lti/login -- OIDC login initiation."""

    def test_valid_platform_returns_redirect(self, app_client):
        """Registered platform + valid params -> 302 redirect to auth_url."""
        client, conn = app_client
        _register_platform(conn)
        resp = client.post("/lti/login", data={
            "iss": "https://lms.example.edu",
            "client_id": "mandarin-app-123",
            "login_hint": "user-hint",
            "target_link_uri": "https://mandarin.app/lti/launch",
        })
        assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}: {resp.data}"
        location = resp.headers.get("Location", "")
        assert location.startswith("https://lms.example.edu/auth?")
        assert "scope=openid" in location
        assert "response_type=id_token" in location
        assert "client_id=mandarin-app-123" in location
        assert "login_hint=user-hint" in location
        assert "response_mode=form_post" in location
        assert "nonce=" in location
        assert "state=" in location

    def test_unregistered_platform_returns_403(self, app_client):
        """Unknown issuer/client_id -> 403."""
        client, conn = app_client
        resp = client.post("/lti/login", data={
            "iss": "https://unknown-lms.example.edu",
            "client_id": "unknown-client",
            "login_hint": "user-hint",
            "target_link_uri": "https://mandarin.app/lti/launch",
        })
        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert "error" in data

    def test_missing_fields_returns_403(self, app_client):
        """Empty issuer + empty client_id -> no platform match -> 403."""
        client, conn = app_client
        resp = client.post("/lti/login", data={})
        assert resp.status_code == 403

    def test_lti_message_hint_included_in_redirect(self, app_client):
        """When lti_message_hint is provided, it appears in the redirect URL."""
        client, conn = app_client
        _register_platform(conn)
        resp = client.post("/lti/login", data={
            "iss": "https://lms.example.edu",
            "client_id": "mandarin-app-123",
            "login_hint": "user-hint",
            "target_link_uri": "https://mandarin.app/lti/launch",
            "lti_message_hint": "msg-hint-42",
        })
        assert resp.status_code == 302
        location = resp.headers.get("Location", "")
        assert "lti_message_hint=msg-hint-42" in location

    def test_get_method_also_works(self, app_client):
        """OIDC login also accepts GET (some platforms use GET)."""
        client, conn = app_client
        _register_platform(conn)
        resp = client.get("/lti/login", query_string={
            "iss": "https://lms.example.edu",
            "client_id": "mandarin-app-123",
            "login_hint": "user-hint",
            "target_link_uri": "https://mandarin.app/lti/launch",
        })
        assert resp.status_code == 302

    def test_login_sets_session_state_and_nonce(self, app_client):
        """After login initiation, lti_state and lti_nonce are stored in session."""
        client, conn = app_client
        _register_platform(conn)
        resp = client.post("/lti/login", data={
            "iss": "https://lms.example.edu",
            "client_id": "mandarin-app-123",
            "login_hint": "hint",
            "target_link_uri": "https://mandarin.app/lti/launch",
        })
        # The redirect is to the platform; we need to check the session was set
        # before the redirect. The test client follows redirects by default
        # only when follow_redirects=True; here it's False (default).
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert "lti_state" in sess
            assert "lti_nonce" in sess
            assert len(sess["lti_state"]) > 10
            assert len(sess["lti_nonce"]) > 10


# ---------------------------------------------------------------------------
# 2. LTI Launch
# ---------------------------------------------------------------------------

class TestLtiLaunch:
    """POST /lti/launch -- JWT validation and user mapping."""

    def test_missing_id_token_returns_400(self, app_client):
        """POST without id_token -> DecodeError -> 400."""
        client, conn = app_client
        with client.session_transaction() as sess:
            sess["lti_state"] = "expected-state"
            sess["lti_nonce"] = "expected-nonce"
        resp = client.post("/lti/launch", data={
            "state": "expected-state",
        })
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    def test_invalid_state_returns_403(self, app_client):
        """State mismatch -> 403."""
        client, conn = app_client
        with client.session_transaction() as sess:
            sess["lti_state"] = "correct-state"
            sess["lti_nonce"] = "nonce"
        resp = client.post("/lti/launch", data={
            "id_token": "some.jwt.token",
            "state": "wrong-state",
        })
        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["error"] == "Invalid state"

    def test_malformed_jwt_returns_400(self, app_client):
        """Garbage id_token -> DecodeError -> 400."""
        client, conn = app_client
        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = "nonce"
        resp = client.post("/lti/launch", data={
            "id_token": "not-a-valid-jwt",
            "state": "the-state",
        })
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    @patch("mandarin.web.lti_routes.pyjwt")
    def test_unknown_platform_returns_403(self, mock_pyjwt, app_client):
        """Valid JWT header but platform not in DB -> 403."""
        client, conn = app_client
        claims = _build_lti_claims(issuer="https://unknown.lms.edu")
        mock = _make_mock_pyjwt(claims)
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = "test-nonce"
        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["error"] == "Unknown platform"

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_jwks_fetch_failure_returns_502(self, mock_pyjwt, mock_requests, app_client):
        """JWKS endpoint unreachable -> 502."""
        client, conn = app_client
        _register_platform(conn)
        claims = _build_lti_claims()
        mock = _make_mock_pyjwt(claims)
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions

        mock_requests.get.side_effect = ConnectionError("JWKS unreachable")

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = "test-nonce"
        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 502
        data = json.loads(resp.data)
        assert "JWKS" in data["error"]

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_no_matching_key_returns_403(self, mock_pyjwt, mock_requests, app_client):
        """JWKS returns keys but none match the kid -> 403."""
        client, conn = app_client
        _register_platform(conn)
        claims = _build_lti_claims()
        mock = _make_mock_pyjwt(claims, kid="nonexistent-kid")
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        # JWKS has a key with kid="test-key-1" but header says "nonexistent-kid"
        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = "test-nonce"
        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert "key" in data["error"].lower()

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_invalid_signature_returns_403(self, mock_pyjwt, mock_requests, app_client):
        """Token verification fails -> 403."""
        client, conn = app_client
        _register_platform(conn)
        import jwt as real_pyjwt

        claims = _build_lti_claims()
        mock = _make_mock_pyjwt(
            claims,
            verify_error=real_pyjwt.exceptions.InvalidSignatureError("bad sig"),
        )
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = "test-nonce"
        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert "verification" in data["error"].lower() or "token" in data["error"].lower()

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_wrong_nonce_returns_403(self, mock_pyjwt, mock_requests, app_client):
        """Token nonce does not match session nonce -> 403."""
        client, conn = app_client
        _register_platform(conn)
        claims = _build_lti_claims(nonce="wrong-nonce")
        mock = _make_mock_pyjwt(claims)
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = "correct-nonce"
        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["error"] == "Invalid nonce"

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_unsupported_message_type_returns_400(self, mock_pyjwt, mock_requests, app_client):
        """Non-LtiResourceLinkRequest message type -> 400."""
        client, conn = app_client
        _register_platform(conn)
        claims = _build_lti_claims(nonce="the-nonce")
        claims["https://purl.imsglobal.org/spec/lti/claim/message_type"] = "LtiDeepLinkingRequest"
        mock = _make_mock_pyjwt(claims, kid="test-key-1")
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = "the-nonce"
        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "Unsupported" in data["error"] or "message type" in data["error"].lower()

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_valid_launch_new_user_creates_mapping_and_redirects(self, mock_pyjwt, mock_requests, app_client):
        """Full valid launch with new user -> creates user + mapping, redirects to /."""
        client, conn = app_client
        _register_platform(conn)
        nonce = "launch-nonce-123"
        claims = _build_lti_claims(
            nonce=nonce,
            email="newltiuser@example.com",
            name="New LTI User",
        )
        mock = _make_mock_pyjwt(claims)
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = nonce

        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}: {resp.data}"
        assert resp.headers.get("Location", "").endswith("/")

        # Verify user was created
        user_row = conn.execute(
            "SELECT id, email FROM user WHERE email = ?", ("newltiuser@example.com",)
        ).fetchone()
        assert user_row is not None

        # Verify LTI mapping was created
        mapping = conn.execute(
            "SELECT * FROM lti_user_mapping WHERE issuer = ? AND lti_sub = ?",
            ("https://lms.example.edu", "user-abc-123"),
        ).fetchone()
        assert mapping is not None
        assert mapping["user_id"] == user_row["id"]

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_valid_launch_existing_mapping_logs_in(self, mock_pyjwt, mock_requests, app_client):
        """Launch with existing user mapping -> logs in existing user, redirects."""
        client, conn = app_client
        _register_platform(conn)

        # Create a user and mapping ahead of time
        user = create_user(conn, "existing@example.com", "securepassword1", "Existing")
        conn.execute(
            "INSERT INTO lti_user_mapping (user_id, issuer, lti_sub) VALUES (?, ?, ?)",
            (user["id"], "https://lms.example.edu", "existing-sub-456"),
        )
        conn.commit()

        nonce = "existing-nonce"
        claims = _build_lti_claims(
            nonce=nonce,
            sub="existing-sub-456",
            email="existing@example.com",
        )
        mock = _make_mock_pyjwt(claims)
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = nonce

        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 302

        # Verify the session has LTI context
        with client.session_transaction() as sess:
            lti_user = sess.get("lti_user", {})
            assert lti_user.get("sub") == "existing-sub-456"
            assert lti_user.get("issuer") == "https://lms.example.edu"

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_valid_launch_email_match_creates_mapping(self, mock_pyjwt, mock_requests, app_client):
        """Launch with no existing mapping but email matches -> links existing user."""
        client, conn = app_client
        _register_platform(conn)

        # Create user without LTI mapping
        user = create_user(conn, "emailmatch@example.com", "securepassword1", "EmailMatch")

        nonce = "email-nonce"
        claims = _build_lti_claims(
            nonce=nonce,
            sub="new-sub-for-email-match",
            email="emailmatch@example.com",
        )
        mock = _make_mock_pyjwt(claims)
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = nonce

        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 302

        # Verify mapping was created for the existing user
        mapping = conn.execute(
            "SELECT * FROM lti_user_mapping WHERE issuer = ? AND lti_sub = ?",
            ("https://lms.example.edu", "new-sub-for-email-match"),
        ).fetchone()
        assert mapping is not None
        assert mapping["user_id"] == user["id"]

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_launch_no_email_no_mapping_returns_400(self, mock_pyjwt, mock_requests, app_client):
        """No existing mapping and no email in claims -> 400."""
        client, conn = app_client
        _register_platform(conn)
        nonce = "no-email-nonce"
        claims = _build_lti_claims(nonce=nonce, email="", name="No Email User")
        mock = _make_mock_pyjwt(claims)
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = nonce

        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "email" in data["error"].lower()

    @patch("mandarin.web.lti_routes._requests")
    @patch("mandarin.web.lti_routes.pyjwt")
    def test_valid_launch_stores_ags_context(self, mock_pyjwt, mock_requests, app_client):
        """Launch with AGS claim stores lti_ags in session for grade passback."""
        client, conn = app_client
        _register_platform(conn)
        nonce = "ags-nonce"
        claims = _build_lti_claims(nonce=nonce, email="agsuser@example.com")
        claims["https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"] = {
            "lineitems": "https://lms.example.edu/api/lineitems",
            "lineitem": "https://lms.example.edu/api/lineitem/42",
            "scope": ["https://purl.imsglobal.org/spec/lti-ags/scope/score"],
        }
        mock = _make_mock_pyjwt(claims)
        mock_pyjwt.get_unverified_header = mock.get_unverified_header
        mock_pyjwt.decode = mock.decode
        mock_pyjwt.exceptions = mock.exceptions
        mock_pyjwt.algorithms = mock.algorithms

        jwks_resp = MagicMock()
        jwks_resp.json.return_value = {"keys": [{"kid": "test-key-1", "kty": "RSA"}]}
        mock_requests.get.return_value = jwks_resp

        with client.session_transaction() as sess:
            sess["lti_state"] = "the-state"
            sess["lti_nonce"] = nonce

        resp = client.post("/lti/launch", data={
            "id_token": "fake.jwt.token",
            "state": "the-state",
        })
        assert resp.status_code == 302

        with client.session_transaction() as sess:
            ags = sess.get("lti_ags", {})
            assert ags.get("lineitem") == "https://lms.example.edu/api/lineitem/42"
            assert ags.get("lineitems") == "https://lms.example.edu/api/lineitems"


# ---------------------------------------------------------------------------
# 3. Grade Passback
# ---------------------------------------------------------------------------

class TestGradePassback:
    """POST /lti/grade -- AGS grade passback."""

    def test_unauthenticated_returns_401(self, app_client):
        """Grade passback without login -> 401."""
        client, conn = app_client
        resp = client.post("/lti/grade", json={"score": 0.85})
        assert resp.status_code == 401
        data = json.loads(resp.data)
        assert "error" in data

    def test_no_lti_context_returns_400(self, app_client):
        """Authenticated but no LTI session context -> 400."""
        client, conn = app_client
        _login(client, conn)
        resp = client.post("/lti/grade", json={"score": 0.85})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "LTI context" in data["error"] or "No LTI" in data["error"]

    def test_no_lineitem_url_returns_400(self, app_client):
        """LTI context present but no lineitem URL -> 400."""
        client, conn = app_client
        _login(client, conn)
        with client.session_transaction() as sess:
            sess["lti_ags"] = {"lineitems": "https://lms.example.edu/api/lineitems", "lineitem": ""}
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "user@example.com",
                "name": "User",
                "issuer": "https://lms.example.edu",
                "client_id": "mandarin-app-123",
            }
        resp = client.post("/lti/grade", json={"score": 0.85})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "line item" in data["error"].lower()

    def test_missing_score_returns_400(self, app_client):
        """No score in request body -> 400."""
        client, conn = app_client
        _login(client, conn)
        _register_platform(conn)
        with client.session_transaction() as sess:
            sess["lti_ags"] = {
                "lineitem": "https://lms.example.edu/api/lineitem/42",
                "lineitems": "",
                "scope": [],
            }
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "user@example.com",
                "name": "User",
                "issuer": "https://lms.example.edu",
                "client_id": "mandarin-app-123",
            }
        resp = client.post("/lti/grade", json={})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "score" in data["error"].lower()

    def test_non_numeric_score_returns_400(self, app_client):
        """String score -> 400."""
        client, conn = app_client
        _login(client, conn)
        _register_platform(conn)
        with client.session_transaction() as sess:
            sess["lti_ags"] = {
                "lineitem": "https://lms.example.edu/api/lineitem/42",
                "lineitems": "",
                "scope": [],
            }
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "user@example.com",
                "name": "User",
                "issuer": "https://lms.example.edu",
                "client_id": "mandarin-app-123",
            }
        resp = client.post("/lti/grade", json={"score": "high"})
        assert resp.status_code == 400

    @patch("mandarin.web.lti_routes._requests")
    def test_valid_grade_passback_returns_200(self, mock_requests, app_client):
        """Full valid grade passback -> 200 with posted=True."""
        client, conn = app_client
        _login(client, conn)
        _register_platform(conn)

        # Mock OAuth2 token response
        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "mock-access-token"}
        # Mock score post response
        score_resp = MagicMock()
        score_resp.status_code = 200

        mock_requests.post.side_effect = [token_resp, score_resp]

        with client.session_transaction() as sess:
            sess["lti_ags"] = {
                "lineitem": "https://lms.example.edu/api/lineitem/42",
                "lineitems": "https://lms.example.edu/api/lineitems",
                "scope": ["https://purl.imsglobal.org/spec/lti-ags/scope/score"],
            }
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "student@example.com",
                "name": "Student",
                "issuer": "https://lms.example.edu",
                "client_id": "mandarin-app-123",
            }

        resp = client.post("/lti/grade", json={"score": 0.92})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["posted"] is True
        assert data["score"] == 0.92

    @patch("mandarin.web.lti_routes._requests")
    def test_score_clamped_to_range(self, mock_requests, app_client):
        """Score > 1.0 is clamped to 1.0."""
        client, conn = app_client
        _login(client, conn)
        _register_platform(conn)

        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "mock-token"}
        score_resp = MagicMock()
        score_resp.status_code = 200
        mock_requests.post.side_effect = [token_resp, score_resp]

        with client.session_transaction() as sess:
            sess["lti_ags"] = {
                "lineitem": "https://lms.example.edu/api/lineitem/42",
                "lineitems": "",
                "scope": [],
            }
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "student@example.com",
                "name": "Student",
                "issuer": "https://lms.example.edu",
                "client_id": "mandarin-app-123",
            }

        resp = client.post("/lti/grade", json={"score": 5.0})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["score"] == 1.0

    @patch("mandarin.web.lti_routes._requests")
    def test_token_fetch_failure_returns_502(self, mock_requests, app_client):
        """OAuth2 token request fails -> 502."""
        client, conn = app_client
        _login(client, conn)
        _register_platform(conn)

        mock_requests.post.side_effect = ConnectionError("Token endpoint down")

        with client.session_transaction() as sess:
            sess["lti_ags"] = {
                "lineitem": "https://lms.example.edu/api/lineitem/42",
                "lineitems": "",
                "scope": [],
            }
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "student@example.com",
                "name": "Student",
                "issuer": "https://lms.example.edu",
                "client_id": "mandarin-app-123",
            }

        resp = client.post("/lti/grade", json={"score": 0.5})
        assert resp.status_code == 502
        data = json.loads(resp.data)
        assert "error" in data

    @patch("mandarin.web.lti_routes._requests")
    def test_no_access_token_in_response_returns_502(self, mock_requests, app_client):
        """Token endpoint returns but no access_token -> 502."""
        client, conn = app_client
        _login(client, conn)
        _register_platform(conn)

        token_resp = MagicMock()
        token_resp.json.return_value = {"error": "invalid_client"}
        mock_requests.post.return_value = token_resp

        with client.session_transaction() as sess:
            sess["lti_ags"] = {
                "lineitem": "https://lms.example.edu/api/lineitem/42",
                "lineitems": "",
                "scope": [],
            }
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "student@example.com",
                "name": "Student",
                "issuer": "https://lms.example.edu",
                "client_id": "mandarin-app-123",
            }

        resp = client.post("/lti/grade", json={"score": 0.5})
        assert resp.status_code == 502
        data = json.loads(resp.data)
        assert "access token" in data["error"].lower()

    @patch("mandarin.web.lti_routes._requests")
    def test_score_post_http_error_returns_502(self, mock_requests, app_client):
        """Score POST returns non-2xx -> 502."""
        client, conn = app_client
        _login(client, conn)
        _register_platform(conn)

        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "mock-token"}
        score_resp = MagicMock()
        score_resp.status_code = 422
        score_resp.text = "Unprocessable Entity"
        mock_requests.post.side_effect = [token_resp, score_resp]

        with client.session_transaction() as sess:
            sess["lti_ags"] = {
                "lineitem": "https://lms.example.edu/api/lineitem/42",
                "lineitems": "",
                "scope": [],
            }
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "student@example.com",
                "name": "Student",
                "issuer": "https://lms.example.edu",
                "client_id": "mandarin-app-123",
            }

        resp = client.post("/lti/grade", json={"score": 0.75})
        assert resp.status_code == 502
        data = json.loads(resp.data)
        assert "failed" in data["error"].lower()

    def test_platform_not_found_returns_400(self, app_client):
        """LTI context references a platform that no longer exists -> 400."""
        client, conn = app_client
        _login(client, conn)
        # Do NOT register the platform
        with client.session_transaction() as sess:
            sess["lti_ags"] = {
                "lineitem": "https://lms.example.edu/api/lineitem/42",
                "lineitems": "",
                "scope": [],
            }
            sess["lti_user"] = {
                "sub": "user-sub",
                "email": "student@example.com",
                "name": "Student",
                "issuer": "https://gone.lms.edu",
                "client_id": "gone-client",
            }

        resp = client.post("/lti/grade", json={"score": 0.5})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "platform" in data["error"].lower() or "Platform" in data["error"]


# ---------------------------------------------------------------------------
# 4. JWKS Endpoint
# ---------------------------------------------------------------------------

class TestJwks:
    """GET /lti/jwks -- JSON Web Key Set."""

    def test_returns_200(self, app_client):
        """JWKS endpoint responds with 200."""
        client, conn = app_client
        resp = client.get("/lti/jwks")
        assert resp.status_code == 200

    def test_returns_json_with_keys_array(self, app_client):
        """Response is JSON with a 'keys' array."""
        client, conn = app_client
        resp = client.get("/lti/jwks")
        data = json.loads(resp.data)
        assert "keys" in data
        assert isinstance(data["keys"], list)

    def test_content_type_is_json(self, app_client):
        """Response content-type is application/json."""
        client, conn = app_client
        resp = client.get("/lti/jwks")
        assert "application/json" in resp.content_type

    def test_api_error_handler_catches_internal_errors(self, app_client):
        """If lti_jwks raises an exception, api_error_handler returns 500."""
        client, conn = app_client
        # Patch jsonify at the route module level to force an OSError inside
        # the route body. The api_error_handler decorator catches it and returns
        # a structured error via its own jsonify call (which goes through the
        # unpatched flask.jsonify imported by api_errors.py).
        with patch("mandarin.web.lti_routes.jsonify", side_effect=OSError("disk error")):
            resp = client.get("/lti/jwks")
        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "unavailable" in data["error"].lower()
