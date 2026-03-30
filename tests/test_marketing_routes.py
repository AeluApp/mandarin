"""Tests for mandarin.web.marketing_routes — marketing, referral, and discount routes.

Covers unauthenticated and authenticated marketing route handlers:
- GET /api/experiment/landing-variant — visitor A/B assignment
- GET /api/experiment/price-variant — default pricing when no experiment running
- GET /api/referral/track — missing ref parameter
- GET /api/discount/validate — code validation
- POST /api/feedback — feedback submission
- GET /api/experiments/my-variants — authenticated variant listing
- POST /api/experiments/expose — exposure logging
"""

import json
from unittest.mock import patch

import pytest

from tests.shared_db import make_test_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
    """Return a context manager class whose __enter__ yields *conn*."""

    class _FakeConnection:
        def __enter__(self):
            return conn

        def __exit__(self, *args):
            return False

    return _FakeConnection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def marketing_client(test_db):
    """Anonymous Flask test client for marketing endpoints."""
    conn, _ = test_db

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def auth_marketing_client(test_db):
    """Authenticated Flask test client (user_id=1) for marketing endpoints."""
    conn, _ = test_db

    # Activate user so Flask-Login's user_loader returns a valid User object
    conn.execute("UPDATE user SET is_active = 1 WHERE id = 1")
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# GET /api/experiment/landing-variant
# ---------------------------------------------------------------------------

class TestLandingVariant:

    def test_no_cookie_returns_control(self, marketing_client):
        """Without a visitor cookie, endpoint returns the control variant."""
        c, _ = marketing_client
        resp = c.get("/api/experiment/landing-variant")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["variant"] == "control"
        assert data["variant_index"] == 0

    def test_with_cookie_returns_valid_variant(self, marketing_client):
        """With a visitor cookie, endpoint deterministically assigns a variant."""
        c, _ = marketing_client
        c.set_cookie("aelu_vid", "test-visitor-stable-42")
        resp = c.get("/api/experiment/landing-variant")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "variant" in data
        assert data["variant"] in ("control", "patient_path")
        assert data["variant_index"] in (0, 1)

    def test_variant_is_deterministic(self, marketing_client):
        """Same visitor cookie always yields the same variant."""
        c, _ = marketing_client
        c.set_cookie("aelu_vid", "deterministic-visitor-99")
        resp1 = c.get("/api/experiment/landing-variant")
        resp2 = c.get("/api/experiment/landing-variant")
        assert json.loads(resp1.data)["variant"] == json.loads(resp2.data)["variant"]


# ---------------------------------------------------------------------------
# GET /api/experiment/price-variant
# ---------------------------------------------------------------------------

class TestPriceVariant:

    def test_no_running_experiment_returns_default(self, marketing_client):
        """When no price_display_test experiment is running, return default price."""
        c, _ = marketing_client
        resp = c.get("/api/experiment/price-variant")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "variant" in data or "price_display" in data


# ---------------------------------------------------------------------------
# GET /api/referral/track
# ---------------------------------------------------------------------------

class TestReferralTrack:

    def test_missing_ref_returns_400(self, marketing_client):
        """Omitting ?ref= parameter returns 400 with error message."""
        c, _ = marketing_client
        resp = c.get("/api/referral/track")
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    def test_unknown_partner_code_returns_error(self, marketing_client):
        """Unknown partner code returns 404 or 500 (no affiliate_partner row)."""
        c, _ = marketing_client
        resp = c.get("/api/referral/track?ref=NONEXISTENTPARTNER")
        assert resp.status_code in (404, 500)


# ---------------------------------------------------------------------------
# GET /api/discount/validate
# ---------------------------------------------------------------------------

class TestDiscountValidate:
    """Discount validate is not in _PUBLIC_PREFIXES — requires authenticated client."""

    def test_missing_code_returns_400(self, auth_marketing_client):
        """Omitting ?code= parameter returns 400."""
        c, _ = auth_marketing_client
        resp = c.get("/api/discount/validate")
        assert resp.status_code == 400

    def test_unknown_code_returns_invalid_or_error(self, auth_marketing_client):
        """Unknown discount code returns valid:False or 500 if table missing."""
        c, _ = auth_marketing_client
        resp = c.get("/api/discount/validate?code=NOSUCHCODE2026")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data["valid"] is False


# ---------------------------------------------------------------------------
# POST /api/feedback
# ---------------------------------------------------------------------------

class TestFeedback:
    """/api/feedback is not in _PUBLIC_PREFIXES — requires authenticated client."""

    def test_missing_rating_returns_400(self, auth_marketing_client):
        """Request with no rating field returns 400."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/feedback",
            data=json.dumps({"comment": "no rating", "type": "nps"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_out_of_range_rating_returns_400(self, auth_marketing_client):
        """Rating outside 1–10 range returns 400."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/feedback",
            data=json.dumps({"rating": 11, "comment": "too high"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_zero_rating_returns_400(self, auth_marketing_client):
        """Rating of 0 (below minimum of 1) returns 400."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/feedback",
            data=json.dumps({"rating": 0}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_invalid_type_returns_400(self, auth_marketing_client):
        """Unknown feedback type returns 400."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/feedback",
            data=json.dumps({"rating": 5, "type": "invalid_type"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_valid_nps_feedback_stored(self, auth_marketing_client):
        """Valid NPS feedback returns {submitted: true}."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/feedback",
            data=json.dumps({"rating": 8, "comment": "Good app", "type": "nps"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("submitted") is True


# ---------------------------------------------------------------------------
# Authenticated marketing routes
# ---------------------------------------------------------------------------

class TestMyVariants:

    def test_my_variants_returns_dict(self, auth_marketing_client):
        """Authenticated user gets experiment variant assignments (empty for fresh user)."""
        c, _ = auth_marketing_client
        resp = c.get("/api/experiments/my-variants")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "variants" in data
        assert isinstance(data["variants"], dict)


class TestExperimentExpose:

    def test_expose_missing_name_returns_400(self, auth_marketing_client):
        """POST without experiment_name returns 400."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/experiments/expose",
            data=json.dumps({"context": "landing"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_expose_valid_logs_silently(self, auth_marketing_client):
        """POST with valid experiment_name returns 200 (errors are swallowed)."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/experiments/expose",
            data=json.dumps({"experiment_name": "landing_headline", "context": "landing"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("status") == "ok"


# ---------------------------------------------------------------------------
# POST /api/referral/signup (public — under /api/referral/ prefix)
# ---------------------------------------------------------------------------

class TestReferralSignup:

    def test_missing_params_returns_400(self, marketing_client):
        """Missing visitor_id or partner_code returns 400."""
        c, _ = marketing_client
        resp = c.post(
            "/api/referral/signup",
            data=json.dumps({"visitor_id": "abc"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_unknown_referral_returns_error(self, marketing_client):
        """Unknown visitor_id+partner_code returns 404 or 500."""
        c, _ = marketing_client
        resp = c.post(
            "/api/referral/signup",
            data=json.dumps({"visitor_id": "no-such-visitor", "partner_code": "NOSUCH"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (404, 500)


# ---------------------------------------------------------------------------
# POST /api/subscription/cancel (authenticated)
# ---------------------------------------------------------------------------

class TestSubscriptionCancel:

    def test_missing_reason_returns_400(self, auth_marketing_client):
        """POST with no reason returns 400."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/subscription/cancel",
            data=json.dumps({}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_invalid_reason_returns_400(self, auth_marketing_client):
        """POST with unrecognised reason returns 400."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/subscription/cancel",
            data=json.dumps({"reason": "not_a_valid_reason"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_valid_cancel_returns_cancelled(self, auth_marketing_client):
        """POST with valid reason returns {cancelled: true}."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/subscription/cancel",
            data=json.dumps({"reason": "not_using", "details": "test"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("cancelled") is True
        assert "access_until" in data


# ---------------------------------------------------------------------------
# POST /api/subscription/pause (authenticated)
# ---------------------------------------------------------------------------

class TestSubscriptionPause:

    def test_invalid_duration_returns_400(self, auth_marketing_client):
        """duration_months not in {1,2,3} returns 400."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/subscription/pause",
            data=json.dumps({"duration_months": 5}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400

    def test_valid_pause_returns_paused(self, auth_marketing_client):
        """POST with duration_months=1 returns {paused: true}."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/subscription/pause",
            data=json.dumps({"duration_months": 1}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("paused") is True
        assert "resume_date" in data


# ---------------------------------------------------------------------------
# GET /api/referral/link (authenticated)
# ---------------------------------------------------------------------------

class TestReferralLink:

    def test_returns_link_and_code(self, auth_marketing_client):
        """Authenticated user gets a referral link."""
        c, _ = auth_marketing_client
        resp = c.get("/api/referral/link")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "link" in data
        assert "ref_code" in data


# ---------------------------------------------------------------------------
# GET /api/referral/stats (authenticated)
# ---------------------------------------------------------------------------

class TestReferralStats:

    def test_returns_stats_dict(self, auth_marketing_client):
        """Authenticated user gets referral stats."""
        c, _ = auth_marketing_client
        resp = c.get("/api/referral/stats")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "referral_count" in data or "ref_code" in data


# ---------------------------------------------------------------------------
# GET /api/account/referral (authenticated — Flutter combined endpoint)
# ---------------------------------------------------------------------------

class TestAccountReferral:

    def test_returns_link_and_count(self, auth_marketing_client):
        """Flutter combined referral endpoint returns link + count."""
        c, _ = auth_marketing_client
        resp = c.get("/api/account/referral")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "link" in data
        assert "count" in data


# ---------------------------------------------------------------------------
# POST /api/subscription/resume (authenticated)
# ---------------------------------------------------------------------------

class TestSubscriptionResume:

    def test_resume_returns_resumed(self, auth_marketing_client):
        """Resuming a subscription returns {resumed: true, next_billing_date}."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/subscription/resume",
            data=json.dumps({}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("resumed") is True
        assert "next_billing_date" in data


# ---------------------------------------------------------------------------
# POST /api/nps/prompted (authenticated)
# ---------------------------------------------------------------------------

class TestNpsPrompted:

    def test_prompted_without_score(self, auth_marketing_client):
        """Recording NPS survey shown (no score) returns ok."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/nps/prompted",
            data=json.dumps({"comment": ""}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("recorded") is True

    def test_prompted_with_score_stores_feedback(self, auth_marketing_client):
        """Recording NPS survey with score stores it and returns ok."""
        c, _ = auth_marketing_client
        resp = c.post(
            "/api/nps/prompted",
            data=json.dumps({"score": 9, "comment": "Great"}),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("recorded") is True


# ---------------------------------------------------------------------------
# GET /api/nps/check (authenticated)
# ---------------------------------------------------------------------------

class TestNpsCheck:

    def test_check_returns_show_field(self, auth_marketing_client):
        """NPS eligibility check returns {show: bool}."""
        c, _ = auth_marketing_client
        resp = c.get("/api/nps/check")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "show" in data
