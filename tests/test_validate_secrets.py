"""Tests for scripts/validate_secrets.py."""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from validate_secrets import CATEGORIES, validate, _is_set


# ── Helpers ──────────────────────────────────────────────────────────

def _all_required_vars():
    """Collect every required var name from CATEGORIES."""
    out = []
    for cat_def in CATEGORIES.values():
        out.extend(cat_def.get("required", []))
    return out


def _all_optional_vars():
    """Collect every optional var name from CATEGORIES."""
    out = []
    for cat_def in CATEGORIES.values():
        out.extend(cat_def.get("optional", []))
    return out


def _env_with_all_required(overrides=None):
    """Return an env dict with every required var set to a placeholder."""
    env = {var: "test-value" for var in _all_required_vars()}
    if overrides:
        env.update(overrides)
    return env


# ── Tests ────────────────────────────────────────────────────────────

class TestAllSet:
    """When all required vars are set, validation passes."""

    def test_all_required_set(self):
        env = _env_with_all_required()
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        assert result["ok"] is True
        assert result["missing_required"] == []

    def test_all_required_set_returns_set_list(self):
        env = _env_with_all_required()
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        required_vars = _all_required_vars()
        set_vars = [var for _, var in result["set_required"]]
        for var in required_vars:
            assert var in set_vars, f"{var} should be in set_required"


class TestMissingRequired:
    """When required vars are missing, validation fails."""

    def test_missing_secret_key(self):
        env = _env_with_all_required()
        del env["SECRET_KEY"]
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        assert result["ok"] is False
        missing_vars = [var for _, var in result["missing_required"]]
        assert "SECRET_KEY" in missing_vars

    def test_missing_stripe_keys(self):
        env = _env_with_all_required()
        del env["STRIPE_SECRET_KEY"]
        del env["STRIPE_WEBHOOK_SECRET"]
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        assert result["ok"] is False
        missing_vars = [var for _, var in result["missing_required"]]
        assert "STRIPE_SECRET_KEY" in missing_vars
        assert "STRIPE_WEBHOOK_SECRET" in missing_vars

    def test_missing_all_required(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = validate()
        assert result["ok"] is False
        assert len(result["missing_required"]) == len(_all_required_vars())

    def test_missing_vapid_keys(self):
        env = _env_with_all_required()
        del env["VAPID_PUBLIC_KEY"]
        del env["VAPID_PRIVATE_KEY"]
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        assert result["ok"] is False
        missing_vars = [var for _, var in result["missing_required"]]
        assert "VAPID_PUBLIC_KEY" in missing_vars
        assert "VAPID_PRIVATE_KEY" in missing_vars


class TestOptionalMissing:
    """Missing optional vars should not cause failure."""

    def test_optional_missing_is_ok(self):
        env = _env_with_all_required()
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        assert result["ok"] is True
        # There should be missing optional vars since we only set required
        assert len(result["missing_optional"]) > 0

    def test_optional_set_shows_in_result(self):
        env = _env_with_all_required({"OLLAMA_URL": "http://localhost:11434"})
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        set_opt_vars = [var for _, var in result["set_optional"]]
        assert "OLLAMA_URL" in set_opt_vars


class TestEmptyString:
    """Empty strings should count as missing."""

    def test_empty_string_is_missing(self):
        env = _env_with_all_required()
        env["SECRET_KEY"] = ""
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        assert result["ok"] is False
        missing_vars = [var for _, var in result["missing_required"]]
        assert "SECRET_KEY" in missing_vars

    def test_whitespace_only_is_missing(self):
        env = _env_with_all_required()
        env["SENTRY_DSN"] = "   "
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        assert result["ok"] is False
        missing_vars = [var for _, var in result["missing_required"]]
        assert "SENTRY_DSN" in missing_vars

    def test_is_set_helper_empty(self):
        with mock.patch.dict(os.environ, {"FOO": ""}, clear=True):
            assert _is_set("FOO") is False

    def test_is_set_helper_present(self):
        with mock.patch.dict(os.environ, {"FOO": "bar"}, clear=True):
            assert _is_set("FOO") is True


class TestCategoryGrouping:
    """Variables appear under the correct category."""

    def test_stripe_vars_in_stripe_category(self):
        env = _env_with_all_required()
        with mock.patch.dict(os.environ, env, clear=True):
            result = validate()
        stripe_set = [(cat, var) for cat, var in result["set_required"]
                       if cat == "Stripe"]
        stripe_vars = [var for _, var in stripe_set]
        assert "STRIPE_SECRET_KEY" in stripe_vars
        assert "STRIPE_WEBHOOK_SECRET" in stripe_vars

    def test_categories_cover_all_required_in_spec(self):
        """Verify the spec's required list is present in CATEGORIES."""
        spec_required = {
            "SECRET_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
            "RESEND_API_KEY", "SENTRY_DSN", "VAPID_PUBLIC_KEY",
            "VAPID_PRIVATE_KEY",
        }
        all_req = set(_all_required_vars())
        for var in spec_required:
            assert var in all_req, f"{var} from spec not in CATEGORIES required"
