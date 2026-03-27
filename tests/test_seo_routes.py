"""Tests for SEO programmatic pages (mandarin.web.seo_routes).

Covers:
- Unauthenticated users are redirected (global require_auth middleware)
- Authenticated users get 200 on tone pair and HSK pages
- Invalid tone pairs and HSK levels return 404
- Pages contain expected content
"""

import json
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
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
def client(test_db):
    """Flask test client with DB patched (unauthenticated)."""
    conn, _ = test_db
    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.seo_routes.db.connection", FakeConn):
        with app.test_client() as c:
            yield c, conn


@pytest.fixture
def auth_client(test_db):
    """Flask test client logged in as a regular user."""
    conn, _ = test_db

    conn.execute("UPDATE user SET is_active = 1 WHERE id = 1")
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.seo_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


# ---------------------------------------------------------------------------
# Access control — unauthenticated redirects (global require_auth middleware)
# ---------------------------------------------------------------------------

class TestUnauthenticatedRedirects:

    def test_tone_pairs_index_redirects_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/learn/tone-pairs/", follow_redirects=False)
        assert resp.status_code == 302

    def test_hsk_review_redirects_unauthenticated(self, client):
        c, _ = client
        resp = c.get("/learn/hsk-1/", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Tone pair index (authenticated)
# ---------------------------------------------------------------------------

class TestTonePairIndex:

    def test_tone_pairs_index_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/tone-pairs/")
        assert resp.status_code == 200

    def test_tone_pairs_index_contains_title(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/tone-pairs/")
        assert b"Tone Pair" in resp.data


# ---------------------------------------------------------------------------
# Tone pair detail (authenticated)
# ---------------------------------------------------------------------------

class TestTonePairDetail:

    def test_valid_tone_pair_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/tone-pairs/1-2/")
        assert resp.status_code == 200

    def test_another_valid_tone_pair_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/tone-pairs/3-4/")
        assert resp.status_code == 200

    def test_neutral_tone_pair_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/tone-pairs/2-5/")
        assert resp.status_code == 200

    def test_invalid_tone_pair_returns_404(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/tone-pairs/0-1/")
        assert resp.status_code == 404

    def test_out_of_range_tone_pair_returns_404(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/tone-pairs/6-1/")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# HSK review pages (authenticated)
# ---------------------------------------------------------------------------

class TestHskReview:

    def test_hsk_level_1_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/hsk-1/")
        assert resp.status_code == 200

    def test_hsk_level_6_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/hsk-6/")
        assert resp.status_code == 200

    def test_hsk_level_9_returns_200(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/hsk-9/")
        assert resp.status_code == 200

    def test_hsk_level_0_returns_404(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/hsk-0/")
        assert resp.status_code == 404

    def test_hsk_level_10_returns_404(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/hsk-10/")
        assert resp.status_code == 404

    def test_hsk_page_contains_hsk_text(self, auth_client):
        c, _ = auth_client
        resp = c.get("/learn/hsk-1/")
        assert b"HSK" in resp.data
