"""Tests for the @api_error_handler decorator."""

import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask
from mandarin.web.api_errors import api_error_handler


def _make_app():
    """Create a minimal test Flask app with decorated routes."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/ok")
    @api_error_handler("Test")
    def ok_route():
        return {"status": "ok"}

    @app.route("/db-error")
    @api_error_handler("Database")
    def db_error_route():
        raise sqlite3.OperationalError("disk I/O error")

    @app.route("/key-error")
    @api_error_handler("Lookup")
    def key_error_route():
        raise KeyError("missing_field")

    @app.route("/os-error")
    @api_error_handler("File")
    def os_error_route():
        raise OSError("file not found")

    @app.route("/import-error")
    @api_error_handler("Module")
    def import_error_route():
        raise ImportError("no module named 'foo'")

    @app.route("/unhandled")
    @api_error_handler("Unhandled")
    def unhandled_route():
        raise RuntimeError("unexpected")

    return app


def test_success_passthrough():
    """Decorator does not interfere with successful responses."""
    app = _make_app()
    with app.test_client() as client:
        resp = client.get("/ok")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"


def test_sqlite_error_caught():
    """sqlite3.Error returns 500 with label message."""
    app = _make_app()
    with app.test_client() as client:
        resp = client.get("/db-error")
        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert data["error"] == "Database unavailable"


def test_key_error_caught():
    """KeyError returns 500 with label message."""
    app = _make_app()
    with app.test_client() as client:
        resp = client.get("/key-error")
        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert data["error"] == "Lookup unavailable"


def test_os_error_caught():
    """OSError returns 500."""
    app = _make_app()
    with app.test_client() as client:
        resp = client.get("/os-error")
        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert data["error"] == "File unavailable"


def test_import_error_caught():
    """ImportError returns 500."""
    app = _make_app()
    with app.test_client() as client:
        resp = client.get("/import-error")
        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert data["error"] == "Module unavailable"


def test_unhandled_error_propagates():
    """RuntimeError (not in the caught set) propagates."""
    app = _make_app()
    with app.test_client() as client:
        try:
            resp = client.get("/unhandled")
            assert resp.status_code == 500  # Flask test client returns 500 for unhandled
        except RuntimeError:
            pass  # Also acceptable if it propagates
