"""JWT authentication — stateless access tokens + single refresh token per user."""

from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta

import jwt

from .settings import JWT_SECRET, JWT_ACCESS_EXPIRY_HOURS, JWT_REFRESH_EXPIRY_DAYS

logger = logging.getLogger(__name__)


# ── Access tokens (stateless, short-lived) ───────────────────────────────────

def create_access_token(user_id: int) -> str:
    """Create a signed JWT access token (HS256, configurable expiry)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=JWT_ACCESS_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> int | None:
    """Decode and validate a JWT access token.

    Returns user_id on success, None on any failure.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except jwt.ExpiredSignatureError:
        logger.info("JWT access token expired")
        return None
    except (jwt.InvalidTokenError, KeyError, TypeError) as e:
        logger.warning("JWT access token invalid: %s", type(e).__name__)
        return None


def is_token_expired(token: str) -> bool:
    """Check if a token is specifically expired (vs. other invalid states)."""
    try:
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return False
    except jwt.ExpiredSignatureError:
        return True
    except (jwt.InvalidTokenError, KeyError, TypeError):
        return False


# ── Refresh tokens (hashed, stored in DB, one per user) ─────────────────────

def create_refresh_token() -> tuple[str, str]:
    """Generate a refresh token pair.

    Returns (raw_token, sha256_hash) — store the hash, send the raw to client.
    """
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def store_refresh_token(conn: sqlite3.Connection, user_id: int, token_hash: str) -> None:
    """Store a refresh token hash for a user. Replaces any existing token."""
    expires = (datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_EXPIRY_DAYS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn.execute(
        "UPDATE user SET refresh_token_hash = ?, refresh_token_expires = ? WHERE id = ?",
        (token_hash, expires, user_id),
    )
    conn.commit()
    logger.info("Refresh token stored for user_id=%d, expires=%s", user_id, expires)


def validate_refresh_token(conn: sqlite3.Connection, raw_token: str) -> int | None:
    """Validate a raw refresh token against stored hashes.

    Returns user_id on success, None on failure (invalid, expired, or not found).
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    row = conn.execute(
        "SELECT id, refresh_token_expires FROM user WHERE refresh_token_hash = ?",
        (token_hash,),
    ).fetchone()
    if not row:
        logger.info("Refresh token validation failed: token not found")
        return None
    # Check expiry
    expires_str = row["refresh_token_expires"]
    if expires_str:
        try:
            expires = datetime.strptime(expires_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires:
                logger.info("Refresh token expired for user_id=%d", row["id"])
                return None
        except (ValueError, TypeError):
            # Malformed expiry — reject token (fail-safe)
            logger.warning("Malformed refresh_token_expires for user_id=%d: %r", row["id"], expires_str)
            return None
    return row["id"]


def revoke_refresh_token(conn: sqlite3.Connection, user_id: int) -> None:
    """Clear the refresh token for a user (logout / revoke)."""
    conn.execute(
        "UPDATE user SET refresh_token_hash = NULL, refresh_token_expires = NULL WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    logger.info("Refresh token revoked for user_id=%d", user_id)
