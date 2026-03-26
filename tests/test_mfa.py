"""Tests for TOTP MFA — setup, verify, login, backup codes, disable."""

import pytest
pyotp = pytest.importorskip("pyotp")

from unittest.mock import patch

from mandarin.mfa import (
    generate_totp_secret,
    get_provisioning_uri,
    verify_totp,
    generate_backup_codes,
    hash_backup_codes,
    verify_backup_code,
)
from mandarin.auth import create_user, authenticate
from werkzeug.security import generate_password_hash as _orig_gen


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
# Unit tests — mfa module
# ---------------------------------------------------------------------------

class TestTOTPSecret:

    def test_generate_secret_returns_base32(self):
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) >= 16

    def test_provisioning_uri_format(self):
        secret = generate_totp_secret()
        uri = get_provisioning_uri(secret, "test@example.com")
        assert uri.startswith("otpauth://totp/")
        assert "Aelu" in uri
        assert "test%40example.com" in uri or "test@example.com" in uri

    def test_verify_correct_code(self):
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True

    def test_verify_wrong_code(self):
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_verify_empty_code(self):
        secret = generate_totp_secret()
        assert verify_totp(secret, "") is False


class TestBackupCodes:

    def test_generate_returns_correct_count(self):
        codes = generate_backup_codes(8)
        assert len(codes) == 8

    def test_codes_are_8_chars(self):
        codes = generate_backup_codes()
        for code in codes:
            assert len(code) == 8

    def test_codes_are_unique(self):
        codes = generate_backup_codes(8)
        assert len(set(codes)) == 8

    def test_hash_returns_json(self):
        codes = generate_backup_codes()
        hashed = hash_backup_codes(codes)
        import json
        parsed = json.loads(hashed)
        assert len(parsed) == len(codes)

    def test_verify_correct_backup_code(self):
        codes = generate_backup_codes()
        hashed = hash_backup_codes(codes)
        success, remaining = verify_backup_code(hashed, codes[0])
        assert success is True
        import json
        remaining_list = json.loads(remaining)
        assert len(remaining_list) == len(codes) - 1

    def test_verify_wrong_backup_code(self):
        codes = generate_backup_codes()
        hashed = hash_backup_codes(codes)
        success, remaining = verify_backup_code(hashed, "wrongcode")
        assert success is False
        assert remaining == hashed  # unchanged

    def test_backup_code_single_use(self):
        codes = generate_backup_codes()
        hashed = hash_backup_codes(codes)
        success, remaining = verify_backup_code(hashed, codes[0])
        assert success is True
        # Try same code again
        success2, _ = verify_backup_code(remaining, codes[0])
        assert success2 is False

    def test_verify_with_empty_json(self):
        success, remaining = verify_backup_code("[]", "anycode")
        assert success is False

    def test_verify_with_none_json(self):
        success, remaining = verify_backup_code(None, "anycode")
        assert success is False


# ---------------------------------------------------------------------------
# Integration tests — MFA with database
# ---------------------------------------------------------------------------

TEST_EMAIL = "mfa@example.com"
TEST_PASSWORD = "securepass1234545"


class TestMFADatabaseIntegration:

    def test_enable_mfa_on_user(self, test_db):
        conn, _ = test_db
        user = create_user(conn, TEST_EMAIL, TEST_PASSWORD)

        secret = generate_totp_secret()
        backup_codes = generate_backup_codes()
        hashed = hash_backup_codes(backup_codes)

        conn.execute(
            "UPDATE user SET totp_secret = ?, totp_backup_codes = ?, totp_enabled = 1 WHERE id = ?",
            (secret, hashed, user["id"]),
        )
        conn.commit()

        row = conn.execute(
            "SELECT totp_enabled, totp_secret FROM user WHERE id = ?",
            (user["id"],),
        ).fetchone()
        assert row["totp_enabled"] == 1
        assert row["totp_secret"] == secret

    def test_disable_mfa_clears_secret(self, test_db):
        conn, _ = test_db
        user = create_user(conn, TEST_EMAIL, TEST_PASSWORD)

        conn.execute(
            "UPDATE user SET totp_secret = 'test', totp_enabled = 1 WHERE id = ?",
            (user["id"],),
        )
        conn.execute(
            "UPDATE user SET totp_enabled = 0, totp_secret = NULL, totp_backup_codes = NULL WHERE id = ?",
            (user["id"],),
        )
        conn.commit()

        row = conn.execute(
            "SELECT totp_enabled, totp_secret FROM user WHERE id = ?",
            (user["id"],),
        ).fetchone()
        assert row["totp_enabled"] == 0
        assert row["totp_secret"] is None

    def test_authenticate_still_works_with_mfa_columns(self, test_db):
        """MFA columns don't break normal authentication."""
        conn, _ = test_db
        create_user(conn, TEST_EMAIL, TEST_PASSWORD)
        result = authenticate(conn, TEST_EMAIL, TEST_PASSWORD)
        assert result is not None
        assert result["email"] == TEST_EMAIL
