"""Contract tests for the Resend email boundary.

Tests that mandarin/email.py correctly handles various Resend API responses
(success, rate limit, invalid API key, network error) and that the email
scheduler correctly dispatches triggers.

Does NOT send real emails. All HTTP calls to Resend are mocked.

Covers:
- _send() success (200, 201)
- _send() rate limit (429)
- _send() invalid API key (401/403)
- _send() network error (ConnectionError, Timeout)
- _send() dev mode (no API key)
- Public email functions produce valid HTML and call _send()
- Email scheduler _send_trigger() dispatch logic
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock

import pytest
from werkzeug.security import generate_password_hash as _orig_gen

from mandarin.auth import create_user


# ---------------------------------------------------------------------------
# Python 3.9 compat: force pbkdf2 for password hashing
# ---------------------------------------------------------------------------

def _compat_generate_password_hash(password, **kwargs):
    return _orig_gen(password, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def _patch_password_hashing():
    with patch("mandarin.auth.generate_password_hash", _compat_generate_password_hash):
        yield


# ---------------------------------------------------------------------------
# _send() — the core Resend HTTP call
# ---------------------------------------------------------------------------

class TestResendSend:
    """Tests for the internal _send() function that talks to Resend."""

    def test_success_200(self):
        """Resend returns 200 -> _send returns True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "email_123"}'

        with patch("mandarin.email.RESEND_API_KEY", "re_test_key"):
            with patch("mandarin.email.requests.post", return_value=mock_resp) as mock_post:
                from mandarin.email import _send
                result = _send("user@example.com", "Test Subject", "<p>body</p>")

        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["to"] == ["user@example.com"]
        assert call_kwargs[1]["json"]["subject"] == "Test Subject"

    def test_success_201(self):
        """Resend returns 201 -> _send returns True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.text = '{"id": "email_456"}'

        with patch("mandarin.email.RESEND_API_KEY", "re_test_key"):
            with patch("mandarin.email.requests.post", return_value=mock_resp):
                from mandarin.email import _send
                result = _send("user@example.com", "Test", "<p>body</p>")

        assert result is True

    def test_rate_limit_429(self):
        """Resend returns 429 (rate limit) -> _send returns False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = '{"message": "Rate limit exceeded"}'

        with patch("mandarin.email.RESEND_API_KEY", "re_test_key"):
            with patch("mandarin.email.requests.post", return_value=mock_resp):
                from mandarin.email import _send
                result = _send("user@example.com", "Test", "<p>body</p>")

        assert result is False

    def test_invalid_api_key_401(self):
        """Resend returns 401 (unauthorized) -> _send returns False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"message": "Invalid API key"}'

        with patch("mandarin.email.RESEND_API_KEY", "re_bad_key"):
            with patch("mandarin.email.requests.post", return_value=mock_resp):
                from mandarin.email import _send
                result = _send("user@example.com", "Test", "<p>body</p>")

        assert result is False

    def test_forbidden_403(self):
        """Resend returns 403 (forbidden) -> _send returns False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = '{"message": "Forbidden"}'

        with patch("mandarin.email.RESEND_API_KEY", "re_test_key"):
            with patch("mandarin.email.requests.post", return_value=mock_resp):
                from mandarin.email import _send
                result = _send("user@example.com", "Test", "<p>body</p>")

        assert result is False

    def test_server_error_500(self):
        """Resend returns 500 (server error) -> _send returns False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = '{"message": "Internal server error"}'

        with patch("mandarin.email.RESEND_API_KEY", "re_test_key"):
            with patch("mandarin.email.requests.post", return_value=mock_resp):
                from mandarin.email import _send
                result = _send("user@example.com", "Test", "<p>body</p>")

        assert result is False

    def test_network_error_connection(self):
        """ConnectionError during send -> _send returns False (no crash)."""
        with patch("mandarin.email.RESEND_API_KEY", "re_test_key"):
            with patch("mandarin.email.requests.post",
                        side_effect=ConnectionError("DNS resolution failed")):
                from mandarin.email import _send
                result = _send("user@example.com", "Test", "<p>body</p>")

        assert result is False

    def test_network_error_oserror(self):
        """OSError during send -> _send returns False (no crash)."""
        with patch("mandarin.email.RESEND_API_KEY", "re_test_key"):
            with patch("mandarin.email.requests.post",
                        side_effect=OSError("Network unreachable")):
                from mandarin.email import _send
                result = _send("user@example.com", "Test", "<p>body</p>")

        assert result is False

    def test_dev_mode_no_api_key(self):
        """When RESEND_API_KEY is empty, _send logs and returns True (dev mode)."""
        with patch("mandarin.email.RESEND_API_KEY", ""):
            with patch("mandarin.email.requests.post") as mock_post:
                from mandarin.email import _send
                result = _send("user@example.com", "Test", "<p>body</p>")

        assert result is True
        mock_post.assert_not_called()  # Should NOT call Resend in dev mode

    def test_timeout_header(self):
        """_send sets a timeout on the HTTP request."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "email_789"}'

        with patch("mandarin.email.RESEND_API_KEY", "re_test_key"):
            with patch("mandarin.email.requests.post", return_value=mock_resp) as mock_post:
                from mandarin.email import _send
                _send("user@example.com", "Test", "<p>body</p>")

        call_kwargs = mock_post.call_args[1]
        assert "timeout" in call_kwargs
        assert call_kwargs["timeout"] > 0

    def test_authorization_header(self):
        """_send sends the correct Authorization header."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "email_auth"}'

        with patch("mandarin.email.RESEND_API_KEY", "re_test_key_abc"):
            with patch("mandarin.email.requests.post", return_value=mock_resp) as mock_post:
                from mandarin.email import _send
                _send("user@example.com", "Test", "<p>body</p>")

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer re_test_key_abc"


# ---------------------------------------------------------------------------
# Public email functions — template generation
# ---------------------------------------------------------------------------

class TestEmailTemplates:
    """Tests that public email functions produce HTML and call _send()."""

    def test_send_welcome_calls_send(self):
        """send_welcome should call _send with welcome subject and HTML."""
        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.email import send_welcome
            result = send_welcome("new@example.com", "Alice")

        assert result is True
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "new@example.com"
        assert "Welcome" in args[1]  # subject
        assert "Alice" in args[2]     # HTML body

    def test_send_password_reset_includes_url(self):
        """send_password_reset should embed the reset URL in the email body."""
        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.email import send_password_reset
            result = send_password_reset("reset@example.com", "https://example.com/reset/abc")

        assert result is True
        html = mock_send.call_args[0][2]
        assert "https://example.com/reset/abc" in html

    def test_send_email_verification_includes_url(self):
        """send_email_verification should embed the verification URL."""
        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.email import send_email_verification
            result = send_email_verification("verify@example.com", "https://example.com/verify/xyz")

        assert result is True
        html = mock_send.call_args[0][2]
        assert "https://example.com/verify/xyz" in html

    def test_send_subscription_confirmed(self):
        """send_subscription_confirmed should include user's name."""
        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.email import send_subscription_confirmed
            result = send_subscription_confirmed("sub@example.com", "Bob")

        assert result is True
        html = mock_send.call_args[0][2]
        assert "Bob" in html

    def test_send_subscription_cancelled_includes_date(self):
        """send_subscription_cancelled should include the access-until date."""
        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.email import send_subscription_cancelled
            result = send_subscription_cancelled("cancel@example.com", "Carol", "March 15, 2026")

        assert result is True
        html = mock_send.call_args[0][2]
        assert "March 15, 2026" in html

    def test_send_activation_nudge_variants(self):
        """send_activation_nudge should produce different content for each n."""
        subjects = []
        for n in [1, 2, 3]:
            with patch("mandarin.email._send", return_value=True) as mock_send:
                from mandarin.email import send_activation_nudge
                send_activation_nudge("nudge@example.com", "Dave", n)
            subjects.append(mock_send.call_args[0][1])
        # Each variant should have a different subject line
        assert len(set(subjects)) == 3, f"Expected 3 different subjects, got: {subjects}"

    def test_send_churn_prevention_includes_days(self):
        """send_churn_prevention should include the days-inactive count."""
        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.email import send_churn_prevention
            send_churn_prevention("churn@example.com", "Eve", 1, days=7)

        html = mock_send.call_args[0][2]
        assert "7" in html

    def test_send_milestone_reached_includes_label(self):
        """send_milestone_reached should include the milestone label."""
        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.email import send_milestone_reached
            send_milestone_reached("mile@example.com", "Frank", "streak_7")

        html = mock_send.call_args[0][2]
        assert "7-Day Streak" in html

    def test_send_winback_variants(self):
        """send_winback should produce different content for each n."""
        subjects = []
        for n in [1, 2, 3]:
            with patch("mandarin.email._send", return_value=True) as mock_send:
                from mandarin.email import send_winback
                send_winback("wb@example.com", "Grace", n)
            subjects.append(mock_send.call_args[0][1])
        assert len(set(subjects)) == 3, f"Expected 3 different subjects, got: {subjects}"

    def test_send_classroom_invite_includes_code(self):
        """send_classroom_invite should include the invite code."""
        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.email import send_classroom_invite
            send_classroom_invite("student@example.com", "Ms. Chen", "Mandarin 101", "ABC123")

        html = mock_send.call_args[0][2]
        assert "ABC123" in html
        assert "Ms. Chen" in html
        assert "Mandarin 101" in html


# ---------------------------------------------------------------------------
# Email scheduler _send_trigger dispatch
# ---------------------------------------------------------------------------

class TestEmailSchedulerDispatch:
    """Tests that the email scheduler's _send_trigger correctly dispatches."""

    def _make_conn_with_user(self, test_db, email="sched@example.com",
                              display_name="Sched User", opt_out=False):
        """Create a test user in the DB for scheduler tests."""
        conn, _ = test_db
        user = create_user(conn, email, "schedpass12345", display_name)
        if opt_out:
            conn.execute(
                "UPDATE user SET marketing_opt_out = 1 WHERE id = ?",
                (user["id"],)
            )
            conn.commit()
        return conn, user

    def test_activation_nudge_trigger(self, test_db):
        """_send_trigger dispatches activation_nudge to the correct template."""
        conn, user = self._make_conn_with_user(test_db)

        with patch("mandarin.email._send", return_value=True):
            from mandarin.web.email_scheduler import _send_trigger
            result = _send_trigger({
                "user_id": user["id"],
                "email_sequence": "activation_nudge",
                "email_number": 1,
            }, conn)

        assert result is True

    def test_onboarding_trigger(self, test_db):
        """_send_trigger dispatches onboarding to the correct template."""
        conn, user = self._make_conn_with_user(test_db)

        with patch("mandarin.email._send", return_value=True):
            from mandarin.web.email_scheduler import _send_trigger
            result = _send_trigger({
                "user_id": user["id"],
                "email_sequence": "onboarding",
                "email_number": 3,
            }, conn)

        assert result is True

    def test_churn_prevention_trigger_extracts_days(self, test_db):
        """_send_trigger for churn_prevention should extract days from reason."""
        conn, user = self._make_conn_with_user(test_db)

        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.web.email_scheduler import _send_trigger
            result = _send_trigger({
                "user_id": user["id"],
                "email_sequence": "churn_prevention",
                "email_number": 1,
                "reason": "Inactive for 7 days",
            }, conn)

        assert result is True
        # Check that 7 days appears in the email body
        html = mock_send.call_args[0][2]
        assert "7" in html

    def test_milestone_trigger(self, test_db):
        """_send_trigger dispatches milestone to the correct template."""
        conn, user = self._make_conn_with_user(test_db)

        with patch("mandarin.email._send", return_value=True):
            from mandarin.web.email_scheduler import _send_trigger
            result = _send_trigger({
                "user_id": user["id"],
                "email_sequence": "milestone",
                "email_number": 1,
                "reason": "Milestone reached: streak_7",
            }, conn)

        assert result is True

    def test_winback_trigger(self, test_db):
        """_send_trigger dispatches winback to the correct template."""
        conn, user = self._make_conn_with_user(test_db)

        with patch("mandarin.email._send", return_value=True):
            from mandarin.web.email_scheduler import _send_trigger
            result = _send_trigger({
                "user_id": user["id"],
                "email_sequence": "winback",
                "email_number": 1,
            }, conn)

        assert result is True

    def test_marketing_opt_out_prevents_send(self, test_db):
        """_send_trigger should return False when user has opted out."""
        conn, user = self._make_conn_with_user(
            test_db, email="optout@example.com", opt_out=True
        )

        with patch("mandarin.email._send", return_value=True) as mock_send:
            from mandarin.web.email_scheduler import _send_trigger
            result = _send_trigger({
                "user_id": user["id"],
                "email_sequence": "activation_nudge",
                "email_number": 1,
            }, conn)

        assert result is False
        mock_send.assert_not_called()

    def test_unknown_sequence_returns_false(self, test_db):
        """_send_trigger with unknown email_sequence should return False."""
        conn, user = self._make_conn_with_user(
            test_db, email="unknown_seq@example.com"
        )

        from mandarin.web.email_scheduler import _send_trigger
        result = _send_trigger({
            "user_id": user["id"],
            "email_sequence": "nonexistent_sequence",
            "email_number": 1,
        }, conn)

        assert result is False

    def test_nonexistent_user_returns_false(self, test_db):
        """_send_trigger for a nonexistent user_id should return False."""
        conn, _ = test_db

        from mandarin.web.email_scheduler import _send_trigger
        result = _send_trigger({
            "user_id": 99999,
            "email_sequence": "activation_nudge",
            "email_number": 1,
        }, conn)

        assert result is False
