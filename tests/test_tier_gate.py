"""Tests for the authorization/tier gating subsystem.

Covers:
  - tier_gate.check_tier_access (admin, free, paid, logging on denial)
  - feature_flags.is_enabled (100% rollout, 0% rollout, 50% determinism,
    nonexistent flag, disabled flag)
"""

import hashlib
import logging

import pytest

from mandarin import feature_flags, tier_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_user(conn, user_id: int, tier: str) -> None:
    """Insert a test user with the given subscription tier."""
    conn.execute(
        """INSERT OR REPLACE INTO user
               (id, email, password_hash, display_name, subscription_tier)
           VALUES (?, ?, 'x', 'Test', ?)""",
        (user_id, f"user{user_id}@test.local", tier),
    )
    conn.commit()


def _set_flag(conn, name: str, enabled: bool, rollout_pct: int = 100) -> None:
    """Insert or replace a feature flag row directly."""
    conn.execute(
        """INSERT OR REPLACE INTO feature_flag (name, enabled, rollout_pct)
           VALUES (?, ?, ?)""",
        (name, int(enabled), rollout_pct),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# tier_gate.check_tier_access
# ---------------------------------------------------------------------------

class TestCheckTierAccess:
    """check_tier_access behaves correctly for each subscription tier."""

    def test_admin_tier_allowed_for_all_paid_features(self, test_db):
        """Admin tier must have access to every paid-gated feature."""
        conn, _ = test_db
        # user id=1 is seeded as 'admin' by conftest; use a fresh id to be explicit.
        _add_user(conn, 10, "admin")
        for feature in tier_gate.PAID_FEATURES:
            assert tier_gate.check_tier_access(conn, 10, feature), (
                f"admin should be allowed for feature {feature!r}"
            )

    def test_admin_tier_allowed_for_free_features(self, test_db):
        """Admin tier must also have access to features not in PAID_FEATURES."""
        conn, _ = test_db
        _add_user(conn, 11, "admin")
        assert tier_gate.check_tier_access(conn, 11, "some_free_feature") is True

    def test_free_tier_denied_premium_features(self, test_db):
        """Free tier is denied access to every paid-gated feature."""
        conn, _ = test_db
        _add_user(conn, 20, "free")
        for feature in tier_gate.PAID_FEATURES:
            assert tier_gate.check_tier_access(conn, 20, feature) is False, (
                f"free tier should be denied feature {feature!r}"
            )

    def test_free_tier_allowed_non_premium_feature(self, test_db):
        """Free tier is allowed features that are not gated behind paid."""
        conn, _ = test_db
        _add_user(conn, 21, "free")
        # A feature that is not in PAID_FEATURES must pass for free users.
        assert "mc" not in tier_gate.PAID_FEATURES  # sanity
        assert tier_gate.check_tier_access(conn, 21, "mc") is True

    def test_paid_tier_allowed_premium_features(self, test_db):
        """Paid tier has access to every paid-gated feature."""
        conn, _ = test_db
        _add_user(conn, 30, "paid")
        for feature in tier_gate.PAID_FEATURES:
            assert tier_gate.check_tier_access(conn, 30, feature), (
                f"paid tier should be allowed feature {feature!r}"
            )

    def test_denial_is_logged(self, test_db, caplog):
        """Denial for a free user emits an INFO log entry."""
        conn, _ = test_db
        _add_user(conn, 40, "free")
        gated_feature = next(iter(tier_gate.PAID_FEATURES))  # any paid feature

        with caplog.at_level(logging.INFO, logger="mandarin.tier_gate"):
            result = tier_gate.check_tier_access(conn, 40, gated_feature)

        assert result is False
        assert any(
            "Tier gate denied" in record.message
            and "user_id=40" in record.message
            and gated_feature in record.message
            for record in caplog.records
        ), "Expected a 'Tier gate denied' log entry but none was found"

    def test_unknown_user_treated_as_free(self, test_db):
        """A user id that does not exist in the DB defaults to free tier."""
        conn, _ = test_db
        # user id 9999 does not exist — should be denied a paid feature.
        assert tier_gate.check_tier_access(conn, 9999, "export") is False


# ---------------------------------------------------------------------------
# feature_flags.is_enabled
# ---------------------------------------------------------------------------

class TestIsEnabled:
    """is_enabled respects the enabled flag and rollout_pct."""

    def test_100_pct_rollout_returns_true(self, test_db):
        """An enabled flag with 100% rollout is always True for any user."""
        conn, _ = test_db
        _set_flag(conn, "test_full_rollout", enabled=True, rollout_pct=100)
        assert feature_flags.is_enabled(conn, "test_full_rollout", user_id=1) is True
        assert feature_flags.is_enabled(conn, "test_full_rollout", user_id=99) is True

    def test_0_pct_rollout_returns_false(self, test_db):
        """An enabled flag with 0% rollout is always False."""
        conn, _ = test_db
        _set_flag(conn, "test_zero_rollout", enabled=True, rollout_pct=0)
        assert feature_flags.is_enabled(conn, "test_zero_rollout", user_id=1) is False
        assert feature_flags.is_enabled(conn, "test_zero_rollout", user_id=99) is False

    def test_50_pct_rollout_is_deterministic_for_same_user(self, test_db):
        """50% rollout produces the same result on repeated calls for a given user."""
        conn, _ = test_db
        _set_flag(conn, "test_half_rollout", enabled=True, rollout_pct=50)
        user_id = 42
        first = feature_flags.is_enabled(conn, "test_half_rollout", user_id=user_id)
        # The hash-based bucket is purely deterministic — calling again must agree.
        for _ in range(5):
            assert feature_flags.is_enabled(conn, "test_half_rollout", user_id=user_id) == first

    def test_50_pct_rollout_bucket_matches_expected_value(self, test_db):
        """50% rollout result can be predicted from the sha256 bucket formula."""
        conn, _ = test_db
        flag = "test_bucket_check"
        _set_flag(conn, flag, enabled=True, rollout_pct=50)
        user_id = 7
        key = f"{flag}:{user_id}"
        bucket = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 100
        expected = bucket < 50
        assert feature_flags.is_enabled(conn, flag, user_id=user_id) == expected

    def test_nonexistent_flag_returns_false(self, test_db):
        """Querying a flag that does not exist in the DB returns False."""
        conn, _ = test_db
        assert feature_flags.is_enabled(conn, "flag_that_does_not_exist", user_id=1) is False

    def test_disabled_flag_returns_false(self, test_db):
        """A flag with enabled=False returns False regardless of rollout_pct."""
        conn, _ = test_db
        _set_flag(conn, "test_disabled_flag", enabled=False, rollout_pct=100)
        assert feature_flags.is_enabled(conn, "test_disabled_flag", user_id=1) is False
        assert feature_flags.is_enabled(conn, "test_disabled_flag") is False
