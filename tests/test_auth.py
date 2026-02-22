"""Comprehensive tests for the auth module (mandarin.auth).

Covers:
- create_user: success, duplicate email, invalid email, short password
- authenticate: correct creds, wrong password, nonexistent email
- get_user_by_id: existing user, nonexistent user
- Data isolation: two users get separate learner_profiles and progress
- Password reset: full flow, expired/invalid token
- Flask web auth routes: login, register, logout via test client
"""

import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash as _orig_gen, check_password_hash

from mandarin.auth import (
    create_user,
    authenticate,
    get_user_by_id,
    create_reset_token,
    reset_password,
)


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
# Helpers
# ---------------------------------------------------------------------------

TEST_EMAIL = "alice@example.com"
TEST_PASSWORD = "securepass1234545"
TEST_NAME = "Alice"


def _create_test_user(conn, email=TEST_EMAIL, password=TEST_PASSWORD, name=TEST_NAME):
    """Shortcut to create a user and return the dict."""
    return create_user(conn, email, password, name)


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------

class TestCreateUser:

    def test_success_returns_dict_with_expected_keys(self, test_db):
        conn, _ = test_db
        user = _create_test_user(conn)

        assert isinstance(user, dict)
        assert "id" in user
        assert user["email"] == TEST_EMAIL
        assert user["display_name"] == TEST_NAME
        assert user["subscription_tier"] == "free"

    def test_id_is_positive_integer(self, test_db):
        conn, _ = test_db
        user = _create_test_user(conn)
        assert isinstance(user["id"], int)
        assert user["id"] > 0

    def test_creates_learner_profile(self, test_db):
        conn, _ = test_db
        user = _create_test_user(conn)

        profile = conn.execute(
            "SELECT * FROM learner_profile WHERE user_id = ?", (user["id"],)
        ).fetchone()
        assert profile is not None

    def test_email_normalized_to_lowercase(self, test_db):
        conn, _ = test_db
        user = create_user(conn, "ALICE@Example.COM", TEST_PASSWORD, TEST_NAME)
        assert user["email"] == "alice@example.com"

    def test_display_name_defaults_to_email_prefix(self, test_db):
        conn, _ = test_db
        user = create_user(conn, "bob@example.com", TEST_PASSWORD)
        assert user["display_name"] == "bob"

    def test_duplicate_email_raises_valueerror(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        with pytest.raises(ValueError, match="Could not create account"):
            _create_test_user(conn)

    def test_duplicate_email_case_insensitive(self, test_db):
        conn, _ = test_db
        _create_test_user(conn, email="alice@example.com")

        with pytest.raises(ValueError, match="Could not create account"):
            _create_test_user(conn, email="ALICE@example.com")

    def test_invalid_email_no_at_raises_valueerror(self, test_db):
        conn, _ = test_db
        with pytest.raises(ValueError, match="Invalid email"):
            create_user(conn, "notanemail", TEST_PASSWORD)

    def test_invalid_email_empty_raises_valueerror(self, test_db):
        conn, _ = test_db
        with pytest.raises(ValueError, match="Invalid email"):
            create_user(conn, "", TEST_PASSWORD)

    def test_invalid_email_whitespace_only_raises_valueerror(self, test_db):
        conn, _ = test_db
        with pytest.raises(ValueError, match="Invalid email"):
            create_user(conn, "   ", TEST_PASSWORD)

    def test_short_password_raises_valueerror(self, test_db):
        conn, _ = test_db
        with pytest.raises(ValueError, match="at least 12 characters"):
            create_user(conn, TEST_EMAIL, "short")

    def test_password_exactly_12_chars_succeeds(self, test_db):
        conn, _ = test_db
        user = create_user(conn, TEST_EMAIL, "xk7m9pq2w4z!")
        assert user is not None

    def test_common_password_rejected(self, test_db):
        conn, _ = test_db
        with pytest.raises(ValueError, match="too common"):
            create_user(conn, TEST_EMAIL, "password123456")

    def test_email_without_tld_rejected(self, test_db):
        conn, _ = test_db
        with pytest.raises(ValueError, match="Invalid email"):
            create_user(conn, "user@localhost", TEST_PASSWORD)

    def test_email_with_valid_format_succeeds(self, test_db):
        conn, _ = test_db
        user = create_user(conn, "user.name+tag@example.co.uk", TEST_PASSWORD)
        assert user is not None

    def test_email_with_spaces_rejected(self, test_db):
        conn, _ = test_db
        with pytest.raises(ValueError, match="Invalid email"):
            create_user(conn, "user @example.com", TEST_PASSWORD)


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------

class TestAuthenticate:

    def test_correct_credentials_returns_user_dict(self, test_db):
        conn, _ = test_db
        created = _create_test_user(conn)

        result = authenticate(conn, TEST_EMAIL, TEST_PASSWORD)
        assert result is not None
        assert result["id"] == created["id"]
        assert result["email"] == TEST_EMAIL
        assert result["display_name"] == TEST_NAME
        assert result["subscription_tier"] == "free"

    def test_updates_last_login_at(self, test_db):
        conn, _ = test_db
        created = _create_test_user(conn)

        authenticate(conn, TEST_EMAIL, TEST_PASSWORD)

        row = conn.execute(
            "SELECT last_login_at FROM user WHERE id = ?", (created["id"],)
        ).fetchone()
        assert row["last_login_at"] is not None

    def test_wrong_password_returns_none(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        result = authenticate(conn, TEST_EMAIL, "wrongpassword")
        assert result is None

    def test_nonexistent_email_returns_none(self, test_db):
        conn, _ = test_db
        result = authenticate(conn, "nobody@example.com", TEST_PASSWORD)
        assert result is None

    def test_inactive_user_returns_none(self, test_db):
        conn, _ = test_db
        created = _create_test_user(conn)
        conn.execute("UPDATE user SET is_active = 0 WHERE id = ?", (created["id"],))
        conn.commit()

        result = authenticate(conn, TEST_EMAIL, TEST_PASSWORD)
        assert result is None

    def test_email_case_insensitive(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        result = authenticate(conn, "ALICE@Example.COM", TEST_PASSWORD)
        assert result is not None
        assert result["email"] == TEST_EMAIL


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------

class TestGetUserById:

    def test_existing_user_returns_dict(self, test_db):
        conn, _ = test_db
        created = _create_test_user(conn)

        result = get_user_by_id(conn, created["id"])
        assert result is not None
        assert result["id"] == created["id"]
        assert result["email"] == TEST_EMAIL
        assert result["display_name"] == TEST_NAME
        assert result["subscription_tier"] == "free"

    def test_nonexistent_user_returns_none(self, test_db):
        conn, _ = test_db
        result = get_user_by_id(conn, 99999)
        assert result is None

    def test_inactive_user_returns_none(self, test_db):
        conn, _ = test_db
        created = _create_test_user(conn)
        conn.execute("UPDATE user SET is_active = 0 WHERE id = ?", (created["id"],))
        conn.commit()

        result = get_user_by_id(conn, created["id"])
        assert result is None


# ---------------------------------------------------------------------------
# Data isolation — two users, separate profiles + progress
# ---------------------------------------------------------------------------

class TestDataIsolation:

    def test_two_users_get_separate_ids(self, test_db):
        conn, _ = test_db
        alice = create_user(conn, "alice@example.com", TEST_PASSWORD, "Alice")
        bob = create_user(conn, "bob@example.com", TEST_PASSWORD, "Bob")

        assert alice["id"] != bob["id"]

    def test_each_user_gets_own_learner_profile(self, test_db):
        conn, _ = test_db
        alice = create_user(conn, "alice@example.com", TEST_PASSWORD, "Alice")
        bob = create_user(conn, "bob@example.com", TEST_PASSWORD, "Bob")

        alice_profile = conn.execute(
            "SELECT * FROM learner_profile WHERE user_id = ?", (alice["id"],)
        ).fetchone()
        bob_profile = conn.execute(
            "SELECT * FROM learner_profile WHERE user_id = ?", (bob["id"],)
        ).fetchone()

        assert alice_profile is not None
        assert bob_profile is not None
        assert alice_profile["id"] != bob_profile["id"]
        assert alice_profile["user_id"] == alice["id"]
        assert bob_profile["user_id"] == bob["id"]

    def test_user_count_after_two_creates(self, test_db):
        conn, _ = test_db
        create_user(conn, "alice@example.com", TEST_PASSWORD, "Alice")
        create_user(conn, "bob@example.com", TEST_PASSWORD, "Bob")

        # Bootstrap user (id=1) + 2 new = 3
        count = conn.execute("SELECT COUNT(*) as c FROM user").fetchone()["c"]
        assert count == 3

    def test_profiles_dont_leak_across_users(self, test_db):
        conn, _ = test_db
        alice = create_user(conn, "alice@example.com", TEST_PASSWORD, "Alice")
        bob = create_user(conn, "bob@example.com", TEST_PASSWORD, "Bob")

        alice_profiles = conn.execute(
            "SELECT COUNT(*) as c FROM learner_profile WHERE user_id = ?",
            (alice["id"],)
        ).fetchone()["c"]
        bob_profiles = conn.execute(
            "SELECT COUNT(*) as c FROM learner_profile WHERE user_id = ?",
            (bob["id"],)
        ).fetchone()["c"]

        assert alice_profiles == 1
        assert bob_profiles == 1


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

class TestPasswordReset:

    def test_full_reset_flow(self, test_db):
        """Create token -> reset password -> authenticate with new password."""
        conn, _ = test_db
        _create_test_user(conn)

        token = create_reset_token(conn, TEST_EMAIL)
        assert isinstance(token, str)
        assert len(token) > 0

        new_password = "newpassword456"
        result = reset_password(conn, token, new_password)
        assert result is True

        # Old password no longer works
        assert authenticate(conn, TEST_EMAIL, TEST_PASSWORD) is None
        # New password works
        user = authenticate(conn, TEST_EMAIL, new_password)
        assert user is not None
        assert user["email"] == TEST_EMAIL

    def test_token_is_single_use(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        token = create_reset_token(conn, TEST_EMAIL)
        assert reset_password(conn, token, "newpassword1") is True

        # Same token should fail the second time (cleared after use)
        assert reset_password(conn, token, "newpassword2") is False

    def test_invalid_token_returns_false(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        # Create a real token first so the reset_token columns exist
        create_reset_token(conn, TEST_EMAIL)

        result = reset_password(conn, "totally-fake-token", "newpassword1")
        assert result is False

    def test_expired_token_returns_false(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        token = create_reset_token(conn, TEST_EMAIL)

        # Manually expire the token by setting expiry to the past
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        conn.execute(
            "UPDATE user SET reset_token_expires = ? WHERE reset_token_hash = ?",
            (past, token_hash),
        )
        conn.commit()

        result = reset_password(conn, token, "newpassword1")
        assert result is False

    def test_create_token_unknown_email_returns_none(self, test_db):
        conn, _ = test_db
        result = create_reset_token(conn, "unknown@example.com")
        assert result is None

    def test_reset_short_password_raises_valueerror(self, test_db):
        conn, _ = test_db
        _create_test_user(conn)
        token = create_reset_token(conn, TEST_EMAIL)

        with pytest.raises(ValueError, match="at least 12 characters"):
            reset_password(conn, token, "short")


# ---------------------------------------------------------------------------
# Flask web auth routes
# ---------------------------------------------------------------------------

class TestWebAuthRoutes:
    """Test login/register/logout via the Flask test client.

    These tests patch `db.connection` so the web routes use the test DB
    instead of the real one.
    """

    @pytest.fixture
    def client(self, test_db):
        """Create a Flask test client with patched DB connection."""
        conn, _ = test_db

        from mandarin.web import create_app

        app = create_app()
        app.config["TESTING"] = True
        # Disable CSRF for test POSTs (WTForms not used, but just in case)
        app.config["WTF_CSRF_ENABLED"] = False

        # Patch db.connection context manager to return the test conn
        class _FakeConnection:
            def __enter__(self):
                return conn
            def __exit__(self, *args):
                return False

        with patch("mandarin.db.connection", _FakeConnection):
            with patch("mandarin.web.auth_routes.db.connection", _FakeConnection):
                with app.test_client() as client:
                    yield client

    # ---- Register ----

    def test_register_get_returns_200(self, client):
        resp = client.get("/auth/register")
        assert resp.status_code == 200

    def test_register_success_redirects(self, client, test_db):
        conn, _ = test_db
        resp = client.post("/auth/register", data={
            "email": "newuser@example.com",
            "password": "securepass12345",
            "confirm": "securepass12345",
            "display_name": "New User",
        }, follow_redirects=False)

        # Should redirect to index on success
        assert resp.status_code in (302, 303)

    def test_register_password_mismatch_stays_on_page(self, client):
        resp = client.post("/auth/register", data={
            "email": "newuser@example.com",
            "password": "securepass12345",
            "confirm": "differentpass",
            "display_name": "New User",
        }, follow_redirects=False)

        # Should re-render register page (200) with flash error
        assert resp.status_code == 200
        assert b"do not match" in resp.data

    def test_register_missing_fields_stays_on_page(self, client):
        resp = client.post("/auth/register", data={
            "email": "",
            "password": "",
            "confirm": "",
        }, follow_redirects=False)

        assert resp.status_code == 200
        assert b"required" in resp.data

    def test_register_duplicate_email_shows_error(self, client, test_db):
        conn, _ = test_db
        # Create user directly
        _create_test_user(conn)

        resp = client.post("/auth/register", data={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "confirm": TEST_PASSWORD,
            "display_name": TEST_NAME,
        }, follow_redirects=False)

        assert resp.status_code == 200
        assert b"Could not create account" in resp.data

    # ---- Login ----

    def test_login_get_returns_200(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code == 200

    def test_login_success_redirects(self, client, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        resp = client.post("/auth/login", data={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        }, follow_redirects=False)

        assert resp.status_code in (302, 303)

    def test_login_wrong_password_stays_on_page(self, client, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        resp = client.post("/auth/login", data={
            "email": TEST_EMAIL,
            "password": "wrongpassword",
        }, follow_redirects=False)

        assert resp.status_code == 200
        assert b"Invalid" in resp.data

    def test_login_nonexistent_email_stays_on_page(self, client):
        resp = client.post("/auth/login", data={
            "email": "nobody@example.com",
            "password": "somepassword",
        }, follow_redirects=False)

        assert resp.status_code == 200
        assert b"Invalid" in resp.data

    def test_login_empty_fields_shows_error(self, client):
        resp = client.post("/auth/login", data={
            "email": "",
            "password": "",
        }, follow_redirects=False)

        assert resp.status_code == 200
        assert b"required" in resp.data

    # ---- Logout ----

    def test_logout_redirects_to_login(self, client, test_db):
        conn, _ = test_db
        _create_test_user(conn)

        # Log in first
        client.post("/auth/login", data={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        })

        resp = client.post("/auth/logout", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "/auth/login" in resp.headers.get("Location", "")

    def test_logout_unauthenticated_redirects(self, client):
        resp = client.post("/auth/logout", follow_redirects=False)
        # Flask-Login redirects unauthenticated users to login
        assert resp.status_code in (302, 401)
