"""TOTP Multi-Factor Authentication — setup, verify, backup codes.

Implements NIST SP 800-63B MFA (PR.AA-05), CIS Controls 6.3/6.4/6.5.
Uses TOTP (RFC 6238) via pyotp with a 1-step time window for clock skew.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import string

import pyotp


def generate_totp_secret() -> str:
    """Generate a base32-encoded TOTP secret."""
    return pyotp.random_base32()


def get_provisioning_uri(secret: str, email: str) -> str:
    """Return an otpauth:// URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name="Mandarin")


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code with 1-step window for clock skew."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def generate_backup_codes(n: int = 8) -> list[str]:
    """Generate n random 8-character alphanumeric backup codes."""
    alphabet = string.ascii_lowercase + string.digits
    return ["".join(secrets.choice(alphabet) for _ in range(8)) for _ in range(n)]


def hash_backup_codes(codes: list[str]) -> str:
    """Hash a list of backup codes and return as JSON array of SHA-256 hashes."""
    hashed = [hashlib.sha256(c.encode()).hexdigest() for c in codes]
    return json.dumps(hashed)


def verify_backup_code(hashed_json: str, code: str) -> tuple[bool, str]:
    """Verify a backup code against the hashed list.

    Returns (success, remaining_hashes_json). On success, the used code
    is removed from the list to prevent reuse.
    """
    code_hash = hashlib.sha256(code.strip().lower().encode()).hexdigest()
    try:
        hashes = json.loads(hashed_json)
    except (json.JSONDecodeError, TypeError):
        return False, hashed_json or "[]"

    if code_hash in hashes:
        hashes.remove(code_hash)
        return True, json.dumps(hashes)
    return False, hashed_json
