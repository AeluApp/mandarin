"""Tests for MFA HTTP endpoints (mandarin.web.mfa_routes).

Covers:
1.  GET /api/mfa/status without login → 401 or redirect
2.  GET /api/mfa/status logged in, MFA not set up → {"enabled": false}
3.  POST /api/mfa/setup → returns secret + backup_codes, DB has totp_secret
4.  POST /api/mfa/setup when already enabled → 400
5.  POST /api/mfa/verify-setup with valid TOTP code → {"enabled": true}
6.  POST /api/mfa/verify-setup with invalid code → 400
7.  POST /api/mfa/verify-setup without prior setup → 400
8.  Full flow: setup → verify → status shows enabled → disable
9.  POST /api/mfa/disable with valid code → {"enabled": false}, DB cleared
10. POST /api/mfa/disable when not enabled → 400
11. POST /api/mfa/disable with invalid code → 400
12. POST /api/mfa/setup response shape includes all required keys
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pyotp
import pytest
from werkzeug.security import generate_password_hash as _orig_gen

from mandarin.auth import create_user


# ---------------------------------------------------------------------------
# Python 3.9 compat: force pbkdf2 instead of scrypt
# ---------------------------------------------------------------------------

def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
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

    with patch("mandarin.db.connection", return_value=fake):
        with patch("mandarin.web.routes.db.connection", return_value=fake):
            with patch("mandarin.web.payment_routes.db.connection", return_value=fake):
                with patch("mandarin.web.onboarding_routes.db.connection", return_value=fake):
                    with patch("mandarin.web.admin_routes.db.connection", return_value=fake):
                        with patch("mandarin.web.mfa_routes.db.connection", return_value=fake):
                            with app.test_client() as client:
                                yield client, conn


def _login(client, conn, email="test@example.com", password="testpass12345"):
    """Create a user in the DB and log in via the /auth/login endpoint."""
    user = create_user(conn, email, password, "Test User")
    client.post("/auth/login", data={"email": email, "password": password})
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def _setup_mfa(client):
    """Call POST /api/mfa/setup and return the parsed JSON response."""
    resp = client.post(
        "/api/mfa/setup",
        content_type="application/json",
        headers=_AJAX_HEADERS,
        data=json.dumps({}),
    )
    return resp


def _verify_setup(client, code):
    """Call POST /api/mfa/verify-setup with the given code."""
    return client.post(
        "/api/mfa/verify-setup",
        content_type="application/json",
        headers=_AJAX_HEADERS,
        data=json.dumps({"code": code}),
    )


def _disable_mfa(client, code):
    """Call POST /api/mfa/disable with the given code."""
    return client.post(
        "/api/mfa/disable",
        content_type="application/json",
        headers=_AJAX_HEADERS,
        data=json.dumps({"code": code}),
    )


def _get_status(client):
    """Call GET /api/mfa/status."""
    return client.get("/api/mfa/status")


# ---------------------------------------------------------------------------
# Test 1: unauthenticated access is rejected
# ---------------------------------------------------------------------------

class TestUnauthenticated:

    def test_status_without_login_is_rejected(self, app_client):
        """GET /api/mfa/status without a session returns 401 or a redirect."""
        client, _ = app_client
        resp = _get_status(client)
        assert resp.status_code in (401, 302), (
            f"Expected 401 or redirect for unauthenticated /api/mfa/status, "
            f"got {resp.status_code}"
        )

    def test_setup_without_login_is_rejected(self, app_client):
        """POST /api/mfa/setup without a session returns 401 or a redirect."""
        client, _ = app_client
        resp = _setup_mfa(client)
        assert resp.status_code in (401, 302), (
            f"Expected 401 or redirect for unauthenticated /api/mfa/setup, "
            f"got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Test 2: status when MFA not configured
# ---------------------------------------------------------------------------

class TestMFAStatusNotConfigured:

    def test_status_returns_enabled_false_when_not_set_up(self, app_client):
        """Logged-in user with no TOTP configured sees enabled=false."""
        client, conn = app_client
        _login(client, conn)
        resp = _get_status(client)
        assert resp.status_code == 200, (
            f"Expected 200 from /api/mfa/status, got {resp.status_code}"
        )
        data = resp.get_json()
        assert data is not None, "Response must be valid JSON"
        assert data["enabled"] is False, (
            f"Expected enabled=false before MFA setup, got {data}"
        )


# ---------------------------------------------------------------------------
# Tests 3, 12: setup response shape and DB write
# ---------------------------------------------------------------------------

class TestMFASetup:

    def test_setup_returns_required_keys(self, app_client):
        """POST /api/mfa/setup returns secret, provisioning_uri, and backup_codes."""
        client, conn = app_client
        _login(client, conn)
        resp = _setup_mfa(client)
        assert resp.status_code == 200, (
            f"Expected 200 from /api/mfa/setup, got {resp.status_code}: {resp.data[:200]}"
        )
        data = resp.get_json()
        assert "secret" in data, "Setup response must include 'secret'"
        assert "provisioning_uri" in data, "Setup response must include 'provisioning_uri'"
        assert "backup_codes" in data, "Setup response must include 'backup_codes'"

    def test_setup_backup_codes_is_list(self, app_client):
        """backup_codes in the setup response must be a non-empty list."""
        client, conn = app_client
        _login(client, conn)
        resp = _setup_mfa(client)
        data = resp.get_json()
        codes = data.get("backup_codes", None)
        assert isinstance(codes, list), f"backup_codes must be a list, got {type(codes)}"
        assert len(codes) > 0, "backup_codes must not be empty"

    def test_setup_writes_totp_secret_to_db(self, app_client):
        """After setup, totp_secret must be stored in the user row."""
        client, conn = app_client
        user = _login(client, conn)
        resp = _setup_mfa(client)
        assert resp.status_code == 200
        data = resp.get_json()

        row = conn.execute(
            "SELECT totp_secret FROM user WHERE id = ?", (user["id"],)
        ).fetchone()
        assert row is not None, "User row must exist"
        assert row["totp_secret"] is not None, (
            "totp_secret must be stored in DB after /api/mfa/setup"
        )
        assert row["totp_secret"] == data["secret"], (
            "DB totp_secret must match the secret returned in the response"
        )

    def test_setup_does_not_enable_mfa_yet(self, app_client):
        """After setup (before verify-setup), totp_enabled must still be 0."""
        client, conn = app_client
        user = _login(client, conn)
        _setup_mfa(client)

        row = conn.execute(
            "SELECT totp_enabled FROM user WHERE id = ?", (user["id"],)
        ).fetchone()
        assert row["totp_enabled"] in (0, None, False), (
            "totp_enabled must remain 0/false until verify-setup succeeds"
        )


# ---------------------------------------------------------------------------
# Test 4: setup when already enabled returns 400
# ---------------------------------------------------------------------------

class TestMFASetupAlreadyEnabled:

    def test_setup_when_already_enabled_returns_400(self, app_client):
        """POST /api/mfa/setup when MFA is already active must return 400."""
        client, conn = app_client
        user = _login(client, conn)

        # Force-enable MFA directly in the DB
        from mandarin.mfa import generate_totp_secret, generate_backup_codes, hash_backup_codes
        secret = generate_totp_secret()
        codes = generate_backup_codes()
        hashed = hash_backup_codes(codes)
        conn.execute(
            "UPDATE user SET totp_secret = ?, totp_backup_codes = ?, totp_enabled = 1 WHERE id = ?",
            (secret, hashed, user["id"]),
        )
        conn.commit()

        resp = _setup_mfa(client)
        assert resp.status_code == 400, (
            f"Expected 400 when calling setup on already-enabled MFA, "
            f"got {resp.status_code}: {resp.data[:200]}"
        )
        data = resp.get_json()
        assert "error" in data, "400 response must include an 'error' key"


# ---------------------------------------------------------------------------
# Tests 5, 6, 7: verify-setup
# ---------------------------------------------------------------------------

class TestMFAVerifySetup:

    def test_verify_setup_with_valid_code_enables_mfa(self, app_client):
        """POST /api/mfa/verify-setup with a valid TOTP code returns enabled=true."""
        client, conn = app_client
        _login(client, conn)

        setup_resp = _setup_mfa(client)
        assert setup_resp.status_code == 200
        secret = setup_resp.get_json()["secret"]

        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        resp = _verify_setup(client, valid_code)
        assert resp.status_code == 200, (
            f"Expected 200 from verify-setup with valid code, "
            f"got {resp.status_code}: {resp.data[:200]}"
        )
        data = resp.get_json()
        assert data.get("enabled") is True, (
            f"Expected enabled=true after successful verify-setup, got {data}"
        )

    def test_verify_setup_sets_totp_enabled_in_db(self, app_client):
        """After successful verify-setup, totp_enabled=1 must be persisted."""
        client, conn = app_client
        user = _login(client, conn)

        setup_resp = _setup_mfa(client)
        secret = setup_resp.get_json()["secret"]
        valid_code = pyotp.TOTP(secret).now()
        _verify_setup(client, valid_code)

        row = conn.execute(
            "SELECT totp_enabled FROM user WHERE id = ?", (user["id"],)
        ).fetchone()
        assert row["totp_enabled"] == 1, (
            f"totp_enabled must be 1 in DB after verify-setup, got {row['totp_enabled']}"
        )

    def test_verify_setup_with_invalid_code_returns_400(self, app_client):
        """POST /api/mfa/verify-setup with a wrong code must return 400."""
        client, conn = app_client
        _login(client, conn)
        _setup_mfa(client)

        resp = _verify_setup(client, "000000")
        assert resp.status_code == 400, (
            f"Expected 400 for invalid TOTP code in verify-setup, "
            f"got {resp.status_code}: {resp.data[:200]}"
        )
        data = resp.get_json()
        assert "error" in data, "400 response must include an 'error' key"

    def test_verify_setup_without_prior_setup_returns_400(self, app_client):
        """POST /api/mfa/verify-setup before calling setup must return 400."""
        client, conn = app_client
        _login(client, conn)

        # Do NOT call setup first
        resp = _verify_setup(client, "123456")
        assert resp.status_code == 400, (
            f"Expected 400 when verify-setup called without prior setup, "
            f"got {resp.status_code}: {resp.data[:200]}"
        )
        data = resp.get_json()
        assert "error" in data, "400 response must include an 'error' key"


# ---------------------------------------------------------------------------
# Test 8: full end-to-end flow
# ---------------------------------------------------------------------------

class TestMFAFullFlow:

    def test_full_setup_verify_status_disable_flow(self, app_client):
        """setup → verify → status shows enabled → disable → status shows disabled."""
        client, conn = app_client
        _login(client, conn)

        # 1. Setup
        setup_resp = _setup_mfa(client)
        assert setup_resp.status_code == 200, (
            f"Setup failed: {setup_resp.status_code} {setup_resp.data[:200]}"
        )
        secret = setup_resp.get_json()["secret"]

        # 2. Verify setup with valid code
        valid_code = pyotp.TOTP(secret).now()
        verify_resp = _verify_setup(client, valid_code)
        assert verify_resp.status_code == 200, (
            f"verify-setup failed: {verify_resp.status_code} {verify_resp.data[:200]}"
        )

        # 3. Status must now show enabled=true
        status_resp = _get_status(client)
        assert status_resp.status_code == 200
        assert status_resp.get_json()["enabled"] is True, (
            "Status must show enabled=true after verify-setup"
        )

        # 4. Disable with a fresh valid code
        disable_code = pyotp.TOTP(secret).now()
        disable_resp = _disable_mfa(client, disable_code)
        assert disable_resp.status_code == 200, (
            f"disable failed: {disable_resp.status_code} {disable_resp.data[:200]}"
        )
        assert disable_resp.get_json()["enabled"] is False, (
            "disable response must return enabled=false"
        )

        # 5. Status must now show enabled=false
        final_status = _get_status(client)
        assert final_status.status_code == 200
        assert final_status.get_json()["enabled"] is False, (
            "Status must show enabled=false after disable"
        )


# ---------------------------------------------------------------------------
# Tests 9, 10, 11: disable endpoint
# ---------------------------------------------------------------------------

class TestMFADisable:

    def _enable_mfa_for_user(self, conn, user_id, secret):
        """Helper: directly write TOTP state into DB."""
        from mandarin.mfa import generate_backup_codes, hash_backup_codes
        codes = generate_backup_codes()
        hashed = hash_backup_codes(codes)
        conn.execute(
            """UPDATE user SET totp_secret = ?, totp_backup_codes = ?,
               totp_enabled = 1 WHERE id = ?""",
            (secret, hashed, user_id),
        )
        conn.commit()

    def test_disable_with_valid_code_returns_enabled_false(self, app_client):
        """POST /api/mfa/disable with valid TOTP code returns enabled=false."""
        client, conn = app_client
        user = _login(client, conn)

        from mandarin.mfa import generate_totp_secret
        secret = generate_totp_secret()
        self._enable_mfa_for_user(conn, user["id"], secret)

        code = pyotp.TOTP(secret).now()
        resp = _disable_mfa(client, code)
        assert resp.status_code == 200, (
            f"Expected 200 from /api/mfa/disable, got {resp.status_code}: {resp.data[:200]}"
        )
        data = resp.get_json()
        assert data.get("enabled") is False, (
            f"Expected enabled=false after disable, got {data}"
        )

    def test_disable_clears_totp_fields_in_db(self, app_client):
        """After successful disable, totp_secret and totp_backup_codes must be NULL."""
        client, conn = app_client
        user = _login(client, conn)

        from mandarin.mfa import generate_totp_secret
        secret = generate_totp_secret()
        self._enable_mfa_for_user(conn, user["id"], secret)

        code = pyotp.TOTP(secret).now()
        _disable_mfa(client, code)

        row = conn.execute(
            "SELECT totp_enabled, totp_secret, totp_backup_codes FROM user WHERE id = ?",
            (user["id"],),
        ).fetchone()
        assert row["totp_enabled"] == 0, (
            f"totp_enabled must be 0 after disable, got {row['totp_enabled']}"
        )
        assert row["totp_secret"] is None, (
            "totp_secret must be NULL after disable"
        )
        assert row["totp_backup_codes"] is None, (
            "totp_backup_codes must be NULL after disable"
        )

    def test_disable_when_not_enabled_returns_400(self, app_client):
        """POST /api/mfa/disable when MFA is not enabled must return 400."""
        client, conn = app_client
        _login(client, conn)

        # MFA is not enabled — no setup was called
        resp = _disable_mfa(client, "123456")
        assert resp.status_code == 400, (
            f"Expected 400 when disabling MFA that is not enabled, "
            f"got {resp.status_code}: {resp.data[:200]}"
        )
        data = resp.get_json()
        assert "error" in data, "400 response must include an 'error' key"

    def test_disable_with_invalid_code_returns_400(self, app_client):
        """POST /api/mfa/disable with wrong TOTP code must return 400."""
        client, conn = app_client
        user = _login(client, conn)

        from mandarin.mfa import generate_totp_secret
        secret = generate_totp_secret()
        self._enable_mfa_for_user(conn, user["id"], secret)

        resp = _disable_mfa(client, "000000")
        assert resp.status_code == 400, (
            f"Expected 400 for invalid TOTP code in disable, "
            f"got {resp.status_code}: {resp.data[:200]}"
        )
        data = resp.get_json()
        assert "error" in data, "400 response must include an 'error' key"

    def test_disable_with_invalid_code_does_not_clear_db(self, app_client):
        """A failed disable attempt must not modify the user's TOTP state."""
        client, conn = app_client
        user = _login(client, conn)

        from mandarin.mfa import generate_totp_secret
        secret = generate_totp_secret()
        self._enable_mfa_for_user(conn, user["id"], secret)

        _disable_mfa(client, "000000")

        row = conn.execute(
            "SELECT totp_enabled, totp_secret FROM user WHERE id = ?",
            (user["id"],),
        ).fetchone()
        assert row["totp_enabled"] == 1, (
            "totp_enabled must remain 1 after a failed disable attempt"
        )
        assert row["totp_secret"] == secret, (
            "totp_secret must remain unchanged after a failed disable attempt"
        )
