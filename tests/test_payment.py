"""Tests for the payment subsystem — checkout, classroom checkout, billing portal,
Stripe webhooks, and subscription status.

Routes under test (mandarin/web/payment_routes.py):
  POST /api/checkout
  POST /api/checkout/classroom
  POST /api/billing-portal
  POST /api/webhook/stripe
  GET  /api/subscription/status
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from werkzeug.security import generate_password_hash as _orig_gen

from mandarin.auth import create_user


# ---------------------------------------------------------------------------
# Python 3.9 compat: werkzeug defaults to scrypt which requires hashlib.scrypt
# — not available in all Python 3.9 builds. Force pbkdf2.
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
    """Thin context-manager wrapper so `with db.connection() as conn` works."""
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False


@pytest.fixture
def app_client(test_db):
    """Flask test client wired to the in-memory test database."""
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
                        with app.test_client() as client:
                            yield client, conn


def _login(client, conn, email="pay_test@example.com", password="paypass12345"):
    """Create a test user in *conn* and log them in via the Flask test client."""
    user = create_user(conn, email, password, "Pay Test User")
    client.post("/auth/login", data={"email": email, "password": password})
    return user


# ---------------------------------------------------------------------------
# POST /api/checkout
# ---------------------------------------------------------------------------

class TestCheckout:

    # The app requires X-Requested-With on all API POSTs when using cookie auth
    # (prevents cross-origin form submission attacks; see mandarin/web/__init__.py).
    _API_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

    def test_monthly_plan_returns_url(self, app_client):
        client, conn = app_client
        _login(client, conn)
        with patch("mandarin.payment.stripe.checkout.Session.create") as mock_stripe:
            mock_stripe.return_value = MagicMock(url="https://checkout.stripe.com/test_monthly")
            resp = client.post(
                "/api/checkout",
                data=json.dumps({"plan": "monthly"}),
                content_type="application/json",
                headers=self._API_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "url" in data
        assert data["url"] == "https://checkout.stripe.com/test_monthly"

    def test_annual_plan_returns_url(self, app_client):
        client, conn = app_client
        _login(client, conn)
        with patch("mandarin.payment.stripe.checkout.Session.create") as mock_stripe:
            mock_stripe.return_value = MagicMock(url="https://checkout.stripe.com/test_annual")
            resp = client.post(
                "/api/checkout",
                data=json.dumps({"plan": "annual"}),
                content_type="application/json",
                headers=self._API_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "url" in data
        assert data["url"] == "https://checkout.stripe.com/test_annual"

    def test_invalid_plan_returns_400(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/checkout",
            data=json.dumps({"plan": "lifetime"}),
            content_type="application/json",
            headers=self._API_HEADERS,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "monthly" in data["error"] or "annual" in data["error"] or "Invalid" in data["error"]

    def test_unauthenticated_redirects(self, app_client):
        client, conn = app_client
        # Include the custom header so we hit login_required, not CSRF guard
        resp = client.post(
            "/api/checkout",
            data=json.dumps({"plan": "monthly"}),
            content_type="application/json",
            headers=self._API_HEADERS,
        )
        assert resp.status_code in (302, 401)

    def test_stripe_error_returns_500(self, app_client):
        client, conn = app_client
        _login(client, conn)
        with patch("mandarin.payment.stripe.checkout.Session.create", side_effect=OSError("Stripe down")):
            resp = client.post(
                "/api/checkout",
                data=json.dumps({"plan": "monthly"}),
                content_type="application/json",
                headers=self._API_HEADERS,
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data


# ---------------------------------------------------------------------------
# POST /api/checkout/classroom
# ---------------------------------------------------------------------------

class TestClassroomCheckout:

    _API_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

    def test_per_student_billing_returns_url(self, app_client):
        client, conn = app_client
        _login(client, conn)
        with patch("mandarin.payment.stripe.checkout.Session.create") as mock_stripe:
            mock_stripe.return_value = MagicMock(url="https://checkout.stripe.com/classroom_ps")
            resp = client.post(
                "/api/checkout/classroom",
                data=json.dumps({"billing": "per_student", "student_count": 10}),
                content_type="application/json",
                headers=self._API_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "url" in data

    def test_semester_billing_returns_url(self, app_client):
        client, conn = app_client
        _login(client, conn)
        with patch("mandarin.payment.stripe.checkout.Session.create") as mock_stripe:
            mock_stripe.return_value = MagicMock(url="https://checkout.stripe.com/classroom_sem")
            resp = client.post(
                "/api/checkout/classroom",
                data=json.dumps({"billing": "semester", "student_count": 25}),
                content_type="application/json",
                headers=self._API_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "url" in data

    def test_invalid_billing_type_returns_400(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/checkout/classroom",
            data=json.dumps({"billing": "quarterly", "student_count": 10}),
            content_type="application/json",
            headers=self._API_HEADERS,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_invalid_student_count_returns_400(self, app_client):
        client, conn = app_client
        _login(client, conn)
        resp = client.post(
            "/api/checkout/classroom",
            data=json.dumps({"billing": "per_student", "student_count": 0}),
            content_type="application/json",
            headers=self._API_HEADERS,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_unauthenticated_redirects(self, app_client):
        client, conn = app_client
        resp = client.post(
            "/api/checkout/classroom",
            data=json.dumps({"billing": "per_student", "student_count": 5}),
            content_type="application/json",
            headers=self._API_HEADERS,
        )
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# POST /api/billing-portal
# ---------------------------------------------------------------------------

class TestBillingPortal:

    _API_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

    def test_with_stripe_customer_returns_url(self, app_client):
        client, conn = app_client
        user = _login(client, conn)
        # Give the user a stripe_customer_id
        conn.execute(
            "UPDATE user SET stripe_customer_id = ? WHERE id = ?",
            ("cus_test_portal", user["id"]),
        )
        conn.commit()
        with patch("mandarin.payment.stripe.billing_portal.Session.create") as mock_portal:
            mock_portal.return_value = MagicMock(url="https://billing.stripe.com/portal_test")
            resp = client.post(
                "/api/billing-portal",
                content_type="application/json",
                headers=self._API_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "url" in data
        assert data["url"] == "https://billing.stripe.com/portal_test"

    def test_without_stripe_customer_returns_400(self, app_client):
        client, conn = app_client
        _login(client, conn)
        # No stripe_customer_id set for this user
        resp = client.post(
            "/api/billing-portal",
            content_type="application/json",
            headers=self._API_HEADERS,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "No active subscription" in data["error"]

    def test_unauthenticated_redirects(self, app_client):
        client, conn = app_client
        resp = client.post(
            "/api/billing-portal",
            content_type="application/json",
            headers=self._API_HEADERS,
        )
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# POST /api/webhook/stripe
# ---------------------------------------------------------------------------

class TestStripeWebhook:

    def _post_webhook(self, client, event_dict, sig="valid_sig"):
        """Helper: POST a JSON-serialised event to the webhook endpoint.

        Patches STRIPE_WEBHOOK_SECRET so the guard clause in handle_webhook()
        doesn't reject the request before construct_event is reached.
        """
        payload = json.dumps(event_dict).encode()
        with patch("mandarin.payment.STRIPE_WEBHOOK_SECRET", "whsec_test"):
            return client.post(
                "/api/webhook/stripe",
                data=payload,
                content_type="application/json",
                headers={"Stripe-Signature": sig},
            )

    def test_checkout_completed_upgrades_user_to_paid(self, app_client):
        client, conn = app_client
        # Create a real user so the webhook UPDATE has a target row
        user = create_user(conn, "webhook_paid@example.com", "webhookpass12345", "Webhook Paid")

        mock_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"user_id": str(user["id"])},
                    "customer": "cus_webhook_paid",
                    "subscription": "sub_webhook_paid",
                }
            },
        }
        with patch("mandarin.payment.stripe.Webhook.construct_event", return_value=mock_event):
            with patch("mandarin.payment.send_subscription_confirmed"):
                resp = self._post_webhook(client, mock_event)

        assert resp.status_code == 200
        row = conn.execute(
            "SELECT subscription_tier FROM user WHERE id = ?", (user["id"],)
        ).fetchone()
        assert row["subscription_tier"] == "paid"

    def test_subscription_deleted_resets_to_free(self, app_client):
        client, conn = app_client
        user = create_user(conn, "webhook_cancel@example.com", "cancelpass12345", "Webhook Cancel")
        conn.execute(
            "UPDATE user SET stripe_customer_id = ?, subscription_tier = 'paid' WHERE id = ?",
            ("cus_cancel_test", user["id"]),
        )
        conn.commit()

        mock_event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": "cus_cancel_test",
                    "current_period_end": None,
                }
            },
        }
        with patch("mandarin.payment.stripe.Webhook.construct_event", return_value=mock_event):
            with patch("mandarin.payment.send_subscription_cancelled"):
                resp = self._post_webhook(client, mock_event)

        assert resp.status_code == 200
        row = conn.execute(
            "SELECT subscription_tier FROM user WHERE id = ?", (user["id"],)
        ).fetchone()
        assert row["subscription_tier"] == "free"

    def test_invoice_paid_sets_status_active(self, app_client):
        client, conn = app_client
        user = create_user(conn, "webhook_renew@example.com", "renewpass12345", "Webhook Renew")
        conn.execute(
            "UPDATE user SET stripe_customer_id = ?, subscription_status = 'past_due' WHERE id = ?",
            ("cus_renew_test", user["id"]),
        )
        conn.commit()

        mock_event = {
            "type": "invoice.paid",
            "data": {"object": {"customer": "cus_renew_test"}},
        }
        with patch("mandarin.payment.stripe.Webhook.construct_event", return_value=mock_event):
            resp = self._post_webhook(client, mock_event)

        assert resp.status_code == 200
        row = conn.execute(
            "SELECT subscription_status FROM user WHERE id = ?", (user["id"],)
        ).fetchone()
        assert row["subscription_status"] == "active"

    def test_invoice_payment_failed_sets_status_past_due(self, app_client):
        client, conn = app_client
        user = create_user(conn, "webhook_fail@example.com", "failpass12345xx", "Webhook Fail")
        conn.execute(
            "UPDATE user SET stripe_customer_id = ?, subscription_status = 'active' WHERE id = ?",
            ("cus_fail_test", user["id"]),
        )
        conn.commit()

        mock_event = {
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": "cus_fail_test"}},
        }
        with patch("mandarin.payment.stripe.Webhook.construct_event", return_value=mock_event):
            resp = self._post_webhook(client, mock_event)

        assert resp.status_code == 200
        row = conn.execute(
            "SELECT subscription_status FROM user WHERE id = ?", (user["id"],)
        ).fetchone()
        assert row["subscription_status"] == "past_due"

    def test_invalid_signature_returns_400(self, app_client):
        client, conn = app_client
        import stripe as stripe_lib

        mock_event = {"type": "checkout.session.completed", "data": {"object": {}}}
        with patch(
            "mandarin.payment.stripe.Webhook.construct_event",
            side_effect=stripe_lib.error.SignatureVerificationError("bad sig", "sig_header"),
        ):
            resp = self._post_webhook(client, mock_event, sig="bad_sig")

        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data


# ---------------------------------------------------------------------------
# GET /api/subscription/status
# ---------------------------------------------------------------------------

class TestSubscriptionStatus:

    def test_paid_user_returns_correct_tier(self, app_client):
        client, conn = app_client
        user = _login(client, conn)
        conn.execute(
            """UPDATE user
               SET subscription_tier = 'paid', subscription_status = 'active',
                   stripe_customer_id = 'cus_status_test'
               WHERE id = ?""",
            (user["id"],),
        )
        conn.commit()

        resp = client.get("/api/subscription/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tier"] == "paid"
        assert data["status"] == "active"
        assert data["has_stripe"] is True

    def test_free_user_returns_free_tier(self, app_client):
        client, conn = app_client
        _login(client, conn)

        resp = client.get("/api/subscription/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tier"] == "free"
        assert data["has_stripe"] is False

    def test_unauthenticated_redirects(self, app_client):
        client, conn = app_client
        resp = client.get("/api/subscription/status")
        assert resp.status_code in (302, 401)
