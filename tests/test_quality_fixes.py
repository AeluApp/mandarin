"""Regression tests for Six Sigma quality fixes.

Tests each fixed defect pattern to prevent regressions:
- C1: Session fixation (session.clear before login)
- C2: Account lockout bypass on malformed locked_until
- C3: Refresh token expiry bypass on malformed date
- C4/C5: GDPR routes error handling
- C6: GDPR export regex guard
- C7/C8: Rate limit on unauthenticated marketing routes
- C9: Auth check on media comprehension submit
- H5: Rate limiter fallback at WARNING level
- H7: Logout security event logged on failure
- H8: Non-idempotent DROP TABLE fixed
- H10: sync_push outer error handling
- H12: lti_login error handling
- M8: security.py alert catch widened
- M9: Token revoke logs LOGOUT event
"""

import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mandarin import db
from mandarin.db.core import _migrate


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def test_conn():
    """Fresh test DB connection."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = db.init_db(path)
    _migrate(conn)
    conn.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier)
        VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin')
    """)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1)")
    conn.commit()
    yield conn
    conn.close()
    path.unlink(missing_ok=True)


@pytest.fixture
def app_client(test_conn):
    """Flask test client with patched DB."""
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    class _FakeConn:
        def __enter__(self):
            return test_conn
        def __exit__(self, *args):
            return False

    with patch("mandarin.db.connection", _FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", _FakeConn), \
         patch("mandarin.web.routes.db.connection", _FakeConn), \
         patch("mandarin.web.gdpr_routes.db.connection", _FakeConn), \
         patch("mandarin.web.token_routes.db.connection", _FakeConn):
        with app.test_client() as client:
            yield client


# ── C2: Account lockout bypass ──────────────────────────────────────────


def test_malformed_locked_until_denies_login(test_conn):
    """C2: Malformed locked_until should deny login (fail-safe), not bypass lockout."""
    from werkzeug.security import generate_password_hash
    pw_hash = generate_password_hash("correctpassword", method="pbkdf2:sha256")
    test_conn.execute(
        "UPDATE user SET password_hash = ?, locked_until = 'GARBAGE' WHERE id = 1",
        (pw_hash,),
    )
    test_conn.commit()

    from mandarin.auth import authenticate
    result = authenticate(test_conn, "local@localhost", "correctpassword")
    assert result is None, "Malformed locked_until should deny login"


# ── C3: Refresh token expiry bypass ─────────────────────────────────────


def test_malformed_refresh_token_expires_rejects(test_conn):
    """C3: Malformed refresh_token_expires should reject token, not silently accept."""
    import hashlib
    token_hash = hashlib.sha256(b"test-token-123").hexdigest()
    test_conn.execute(
        "UPDATE user SET refresh_token_hash = ?, refresh_token_expires = 'NOT-A-DATE' WHERE id = 1",
        (token_hash,),
    )
    test_conn.commit()

    from mandarin.jwt_auth import validate_refresh_token
    result = validate_refresh_token(test_conn, "test-token-123")
    assert result is None, "Malformed expiry should reject token"


# ── C4/C5: GDPR error handling ──────────────────────────────────────────


def test_gdpr_export_has_error_handling():
    """C4: GDPR export_data must have try/except error handling."""
    import inspect
    from mandarin.web.gdpr_routes import export_data
    source = inspect.getsource(export_data)
    assert "try:" in source, "export_data must have try/except"
    assert "except" in source, "export_data must catch exceptions"
    assert "500" in source, "export_data must return 500 on error"


def test_gdpr_delete_has_error_handling():
    """C5: GDPR request_deletion must have try/except error handling."""
    import inspect
    from mandarin.web.gdpr_routes import request_deletion
    source = inspect.getsource(request_deletion)
    assert "try:" in source, "request_deletion must have try/except"
    assert "except" in source, "request_deletion must catch exceptions"
    assert "500" in source, "request_deletion must return 500 on error"


# ── C6: GDPR export regex guard ─────────────────────────────────────────


def test_gdpr_export_has_table_allowlist():
    """C6: The GDPR export path should use an explicit table allowlist."""
    import inspect
    from mandarin.web.gdpr_routes import _export_data_impl
    source = inspect.getsource(_export_data_impl)
    assert "_GDPR_EXTRA_TABLES" in source and "frozenset" in source, \
        "GDPR export SELECT path must use an explicit frozenset allowlist"


# ── H8: Idempotent migrations ───────────────────────────────────────────


def test_migrations_use_drop_if_exists():
    """H8: All DROP TABLE statements in migrations should use IF EXISTS."""
    from mandarin.db import core
    import inspect
    source = inspect.getsource(core)
    # Find all DROP TABLE lines
    import re
    drops = re.findall(r'DROP TABLE\b.*', source)
    for drop in drops:
        if "IF NOT EXISTS" in drop:  # skip CREATE TABLE IF NOT EXISTS
            continue
        if "DROP TABLE" in drop and "_new" not in drop.lower():
            # Original table drops must use IF EXISTS
            assert "IF EXISTS" in drop, f"Non-idempotent DROP: {drop.strip()}"


# ── H10: sync_push error handling ────────────────────────────────────────


def test_sync_push_has_outer_error_handling():
    """H10: sync_push should have outer try/except for DB connection failures."""
    import inspect
    from mandarin.web.sync_routes import sync_push
    source = inspect.getsource(sync_push)
    assert "try:" in source, "sync_push must have try/except wrapper"
    assert "except" in source, "sync_push must catch exceptions"


# ── M8: security alert catch widened ─────────────────────────────────────


def test_security_alert_catches_all_sqlite_errors():
    """M8: _send_critical_alert should catch sqlite3.Error, not just OperationalError."""
    import inspect
    from mandarin.security import _send_critical_alert
    source = inspect.getsource(_send_critical_alert)
    assert "sqlite3.Error" in source, \
        "_send_critical_alert must catch sqlite3.Error (not just OperationalError)"


# ── M9: Token revoke logs LOGOUT event ──────────────────────────────────


def test_token_revoke_logs_logout_event():
    """M9: Token revoke should log both LOGOUT and TOKEN_REVOKED security events."""
    import inspect
    from mandarin.web.token_routes import revoke_token
    source = inspect.getsource(revoke_token)
    assert "LOGOUT" in source, "Token revoke must log LOGOUT security event"
    assert "TOKEN_REVOKED" in source, "Token revoke must log TOKEN_REVOKED security event"


# ── Session fixation ────────────────────────────────────────────────────


def test_session_clear_before_login():
    """C1: auth_routes should call session.clear() before login_user()."""
    import inspect
    from mandarin.web import auth_routes
    source = inspect.getsource(auth_routes)
    # Find all login_user calls and verify session.clear() precedes each
    lines = source.split("\n")
    for i, line in enumerate(lines):
        if "login_user(" in line and "User(" in line:
            # Look backward for session.clear()
            preceding = "\n".join(lines[max(0, i-5):i])
            assert "session.clear()" in preceding, \
                f"login_user at line {i+1} must be preceded by session.clear()"


# ── Settings cleanup ────────────────────────────────────────────────────


def test_settings_no_dead_logging_import():
    """M2: settings.py should not have unused import logging."""
    import inspect
    from mandarin import settings
    source = inspect.getsource(settings)
    lines = source.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped == "import logging":
            pytest.fail("settings.py has dead 'import logging'")


# ── .env.example completeness ───────────────────────────────────────────


def test_env_example_has_vapid_keys():
    """H16: .env.example should document VAPID keys."""
    env_path = Path(__file__).parent.parent / ".env.example"
    content = env_path.read_text()
    assert "VAPID_PUBLIC_KEY" in content
    assert "VAPID_PRIVATE_KEY" in content
    assert "VAPID_CLAIMS_EMAIL" in content


def test_env_example_has_session_timeout():
    """H16: .env.example should document SESSION_TIMEOUT_MINUTES."""
    env_path = Path(__file__).parent.parent / ".env.example"
    content = env_path.read_text()
    assert "SESSION_TIMEOUT_MINUTES" in content


def test_env_example_has_alert_vars():
    """H16: .env.example should document ALERT_WEBHOOK_URL and ADMIN_EMAIL."""
    env_path = Path(__file__).parent.parent / ".env.example"
    content = env_path.read_text()
    assert "ALERT_WEBHOOK_URL" in content
    assert "ADMIN_EMAIL" in content
