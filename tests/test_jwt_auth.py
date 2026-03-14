"""Tests for mandarin.jwt_auth — access tokens, refresh tokens, expiry, revocation."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import jwt
import pytest

from mandarin.jwt_auth import (
    create_access_token,
    decode_access_token,
    is_token_expired,
    create_refresh_token,
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
)
from mandarin.settings import JWT_SECRET


# ── Access token tests ────────────────────────────────────────────────────────

class TestCreateAccessToken:
    def test_returns_string(self, test_db):
        token = create_access_token(1)
        assert isinstance(token, str)

    def test_three_part_jwt_structure(self, test_db):
        token = create_access_token(1)
        parts = token.split(".")
        assert len(parts) == 3, "JWT must have header.payload.signature"

    def test_uses_hs256_algorithm(self, test_db):
        token = create_access_token(1)
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "HS256"


class TestDecodeAccessToken:
    def test_round_trip_returns_user_id(self, test_db):
        token = create_access_token(1)
        result = decode_access_token(token)
        assert result == 1

    def test_round_trip_with_arbitrary_user_id(self, test_db):
        token = create_access_token(42)
        result = decode_access_token(token)
        assert result == 42

    def test_expired_token_returns_none(self, test_db):
        # Back-date exp to 2 seconds ago.
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "1",
            "iat": now - timedelta(seconds=10),
            "exp": now - timedelta(seconds=2),
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        result = decode_access_token(expired_token)
        assert result is None

    def test_tampered_signature_returns_none(self, test_db):
        token = create_access_token(1)
        # Replace the entire signature with a different one.
        header, payload_seg, _sig = token.rsplit(".", 2)
        tampered = f"{header}.{payload_seg}.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        result = decode_access_token(tampered)
        assert result is None

    def test_wrong_secret_returns_none(self, test_db):
        token = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                           "wrong-secret", algorithm="HS256")
        result = decode_access_token(token)
        assert result is None

    def test_algorithm_restriction_rejects_none_alg(self, test_db):
        """PyJWT must not accept the 'none' algorithm bypass."""
        # PyJWT >=2 raises InvalidAlgorithmError for alg='none' when algorithms=['HS256'].
        # We verify the attack surface is closed: decoding always returns None.
        try:
            none_token = jwt.encode({"sub": "1"}, "", algorithm="none")
        except Exception:
            # Some PyJWT versions refuse to encode with 'none' at all — that's also a pass.
            return
        result = decode_access_token(none_token)
        assert result is None, "Algorithm 'none' must not be accepted by decode_access_token"

    def test_completely_garbage_token_returns_none(self, test_db):
        result = decode_access_token("not.a.token")
        assert result is None

    def test_empty_string_returns_none(self, test_db):
        result = decode_access_token("")
        assert result is None


# ── is_token_expired tests ────────────────────────────────────────────────────

class TestIsTokenExpired:
    def test_valid_token_is_not_expired(self, test_db):
        token = create_access_token(1)
        assert is_token_expired(token) is False

    def test_expired_token_is_expired(self, test_db):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "1",
            "iat": now - timedelta(seconds=10),
            "exp": now - timedelta(seconds=2),
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        assert is_token_expired(expired_token) is True

    def test_invalid_token_is_not_expired(self, test_db):
        # A bad token is invalid, not expired — is_token_expired must return False.
        assert is_token_expired("garbage.garbage.garbage") is False


# ── Refresh token tests ───────────────────────────────────────────────────────

class TestStoreRefreshToken:
    def test_persists_hash_to_db(self, test_db):
        conn, _ = test_db
        raw, token_hash = create_refresh_token()
        store_refresh_token(conn, 1, token_hash)
        row = conn.execute(
            "SELECT refresh_token_hash FROM user WHERE id = 1"
        ).fetchone()
        assert row["refresh_token_hash"] == token_hash

    def test_replaces_existing_token(self, test_db):
        conn, _ = test_db
        _, hash1 = create_refresh_token()
        _, hash2 = create_refresh_token()
        store_refresh_token(conn, 1, hash1)
        store_refresh_token(conn, 1, hash2)
        row = conn.execute(
            "SELECT refresh_token_hash FROM user WHERE id = 1"
        ).fetchone()
        assert row["refresh_token_hash"] == hash2


class TestValidateRefreshToken:
    def test_valid_token_returns_user_id(self, test_db):
        conn, _ = test_db
        raw, token_hash = create_refresh_token()
        store_refresh_token(conn, 1, token_hash)
        result = validate_refresh_token(conn, raw)
        assert result == 1

    def test_wrong_raw_token_returns_none(self, test_db):
        conn, _ = test_db
        _, token_hash = create_refresh_token()
        store_refresh_token(conn, 1, token_hash)
        # Different raw token — hash won't match.
        other_raw, _ = create_refresh_token()
        result = validate_refresh_token(conn, other_raw)
        assert result is None

    def test_expired_token_returns_none(self, test_db):
        conn, _ = test_db
        raw, token_hash = create_refresh_token()
        # Write token with an expiry in the past.
        past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE user SET refresh_token_hash = ?, refresh_token_expires = ? WHERE id = 1",
            (token_hash, past),
        )
        conn.commit()
        result = validate_refresh_token(conn, raw)
        assert result is None

    def test_malformed_expires_returns_none(self, test_db):
        """Regression: garbled expiry string must be rejected, not crash (fix from C3)."""
        conn, _ = test_db
        raw, token_hash = create_refresh_token()
        conn.execute(
            "UPDATE user SET refresh_token_hash = ?, refresh_token_expires = ? WHERE id = 1",
            (token_hash, "not-a-date"),
        )
        conn.commit()
        result = validate_refresh_token(conn, raw)
        assert result is None

    def test_token_not_in_db_returns_none(self, test_db):
        conn, _ = test_db
        raw, _ = create_refresh_token()
        # Nothing stored — lookup should find nothing.
        result = validate_refresh_token(conn, raw)
        assert result is None


class TestRevokeRefreshToken:
    def test_clears_hash_and_expiry(self, test_db):
        conn, _ = test_db
        raw, token_hash = create_refresh_token()
        store_refresh_token(conn, 1, token_hash)
        revoke_refresh_token(conn, 1)
        row = conn.execute(
            "SELECT refresh_token_hash, refresh_token_expires FROM user WHERE id = 1"
        ).fetchone()
        assert row["refresh_token_hash"] is None
        assert row["refresh_token_expires"] is None

    def test_revoked_token_no_longer_validates(self, test_db):
        conn, _ = test_db
        raw, token_hash = create_refresh_token()
        store_refresh_token(conn, 1, token_hash)
        revoke_refresh_token(conn, 1)
        result = validate_refresh_token(conn, raw)
        assert result is None
