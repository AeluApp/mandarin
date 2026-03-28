"""Tests for mandarin.feature_flags — deterministic rollout, drill gating, CRUD, error handling."""

import sqlite3

import pytest

from mandarin.feature_flags import (
    AI_FEATURE_FLAGS,
    FLAGGED_DRILLS,
    get_all_flags,
    is_drill_enabled,
    is_enabled,
    is_flag_enabled,
    set_flag,
)


@pytest.fixture
def conn():
    """In-memory SQLite with the feature_flag table."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE feature_flag (
            name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            rollout_pct INTEGER NOT NULL DEFAULT 100,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def bare_conn():
    """In-memory SQLite with NO tables — used to test OperationalError paths."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ---------------------------------------------------------------------------
# 1. is_enabled basics
# ---------------------------------------------------------------------------


class TestIsEnabledBasics:
    def test_flag_not_found_returns_false(self, conn):
        """A flag that does not exist in the table returns False."""
        assert is_enabled(conn, "nonexistent_flag") is False

    def test_flag_disabled_returns_false(self, conn):
        """A flag that exists but is disabled returns False regardless of rollout."""
        conn.execute(
            "INSERT INTO feature_flag (name, enabled, rollout_pct) VALUES (?, ?, ?)",
            ("my_flag", 0, 100),
        )
        conn.commit()
        assert is_enabled(conn, "my_flag") is False

    def test_flag_enabled_full_rollout_returns_true(self, conn):
        """A flag that is enabled with 100% rollout returns True."""
        conn.execute(
            "INSERT INTO feature_flag (name, enabled, rollout_pct) VALUES (?, ?, ?)",
            ("my_flag", 1, 100),
        )
        conn.commit()
        assert is_enabled(conn, "my_flag") is True

    def test_flag_enabled_zero_rollout_returns_false(self, conn):
        """A flag at 0% rollout returns False even when enabled."""
        conn.execute(
            "INSERT INTO feature_flag (name, enabled, rollout_pct) VALUES (?, ?, ?)",
            ("my_flag", 1, 0),
        )
        conn.commit()
        assert is_enabled(conn, "my_flag", user_id=1) is False

    def test_flag_enabled_partial_rollout_no_user_returns_true(self, conn):
        """When rollout < 100 but user_id is None, treat as enabled (no rollout check)."""
        conn.execute(
            "INSERT INTO feature_flag (name, enabled, rollout_pct) VALUES (?, ?, ?)",
            ("my_flag", 1, 50),
        )
        conn.commit()
        assert is_enabled(conn, "my_flag", user_id=None) is True


# ---------------------------------------------------------------------------
# 2. Deterministic rollout
# ---------------------------------------------------------------------------


class TestDeterministicRollout:
    def test_same_flag_user_always_same_result(self, conn):
        """Calling is_enabled multiple times with the same flag+user yields the same bool."""
        conn.execute(
            "INSERT INTO feature_flag (name, enabled, rollout_pct) VALUES (?, ?, ?)",
            ("stable_flag", 1, 50),
        )
        conn.commit()
        results = {is_enabled(conn, "stable_flag", user_id=42) for _ in range(20)}
        assert len(results) == 1, "Should be deterministic — same result every call"

    def test_different_users_get_deterministic_different_results(self, conn):
        """Different user IDs produce different hashes, so some get True and some False."""
        conn.execute(
            "INSERT INTO feature_flag (name, enabled, rollout_pct) VALUES (?, ?, ?)",
            ("split_flag", 1, 50),
        )
        conn.commit()
        results = {is_enabled(conn, "split_flag", user_id=uid) for uid in range(200)}
        # At 50% rollout, both True and False must appear among 200 users
        assert True in results and False in results

    def test_rollout_50_splits_roughly_half(self, conn):
        """50% rollout should enable roughly 30-70 out of 100 users (wide tolerance)."""
        conn.execute(
            "INSERT INTO feature_flag (name, enabled, rollout_pct) VALUES (?, ?, ?)",
            ("half_flag", 1, 50),
        )
        conn.commit()
        enabled_count = sum(
            is_enabled(conn, "half_flag", user_id=uid) for uid in range(100)
        )
        assert 20 <= enabled_count <= 80, f"Expected ~50, got {enabled_count}"

    def test_rollout_99_enables_most_users(self, conn):
        """99% rollout should enable the vast majority of users."""
        conn.execute(
            "INSERT INTO feature_flag (name, enabled, rollout_pct) VALUES (?, ?, ?)",
            ("almost_all", 1, 99),
        )
        conn.commit()
        enabled_count = sum(
            is_enabled(conn, "almost_all", user_id=uid) for uid in range(200)
        )
        assert enabled_count >= 170, f"Expected >=170 at 99%, got {enabled_count}"


# ---------------------------------------------------------------------------
# 3. is_drill_enabled
# ---------------------------------------------------------------------------


class TestIsDrillEnabled:
    def test_unflagged_drill_always_true(self, conn):
        """A drill type NOT in FLAGGED_DRILLS is always enabled."""
        assert is_drill_enabled(conn, "tone_pairs") is True
        assert is_drill_enabled(conn, "listening_comp") is True

    def test_flagged_drill_delegates_to_is_enabled(self, conn):
        """A flagged drill type checks the corresponding feature flag."""
        drill_type = next(iter(FLAGGED_DRILLS))
        flag_name = FLAGGED_DRILLS[drill_type]

        # Flag enabled at 100% — drill should be enabled
        set_flag(conn, flag_name, enabled=True, rollout_pct=100)
        assert is_drill_enabled(conn, drill_type) is True

    def test_flagged_drill_disabled_flag_returns_false(self, conn):
        """A flagged drill whose feature flag is disabled returns False."""
        drill_type = next(iter(FLAGGED_DRILLS))
        flag_name = FLAGGED_DRILLS[drill_type]

        set_flag(conn, flag_name, enabled=False)
        assert is_drill_enabled(conn, drill_type) is False


# ---------------------------------------------------------------------------
# 4. set_flag
# ---------------------------------------------------------------------------


class TestSetFlag:
    def test_creates_new_flag(self, conn):
        """set_flag inserts a new row when the flag does not exist."""
        set_flag(conn, "new_feature", enabled=True, rollout_pct=75, description="test desc")
        row = conn.execute("SELECT * FROM feature_flag WHERE name = ?", ("new_feature",)).fetchone()
        assert row is not None
        assert row["enabled"] == 1
        assert row["rollout_pct"] == 75
        assert row["description"] == "test desc"

    def test_updates_existing_flag(self, conn):
        """set_flag updates an existing flag via ON CONFLICT DO UPDATE."""
        set_flag(conn, "toggle_me", enabled=True, rollout_pct=100, description="v1")
        set_flag(conn, "toggle_me", enabled=False, rollout_pct=50, description="v2")
        row = conn.execute("SELECT * FROM feature_flag WHERE name = ?", ("toggle_me",)).fetchone()
        assert row["enabled"] == 0
        assert row["rollout_pct"] == 50
        assert row["description"] == "v2"

    def test_preserves_description_on_update_when_none(self, conn):
        """When description=None on update, COALESCE keeps the existing description."""
        set_flag(conn, "keep_desc", enabled=True, description="original description")
        set_flag(conn, "keep_desc", enabled=False, description=None)
        row = conn.execute("SELECT description FROM feature_flag WHERE name = ?", ("keep_desc",)).fetchone()
        assert row["description"] == "original description"


# ---------------------------------------------------------------------------
# 5. get_all_flags
# ---------------------------------------------------------------------------


class TestGetAllFlags:
    def test_empty_table_returns_empty_list(self, conn):
        """No flags in the table returns an empty list."""
        result = get_all_flags(conn)
        assert result == []

    def test_returns_all_flags_sorted_by_name(self, conn):
        """All flags are returned as dicts, sorted alphabetically by name."""
        set_flag(conn, "zebra", enabled=True)
        set_flag(conn, "alpha", enabled=False)
        set_flag(conn, "middle", enabled=True, rollout_pct=50)
        result = get_all_flags(conn)
        names = [f["name"] for f in result]
        assert names == ["alpha", "middle", "zebra"]
        assert all(isinstance(f, dict) for f in result)

    def test_missing_table_returns_empty_list(self, bare_conn):
        """OperationalError (no table) is caught and returns []."""
        result = get_all_flags(bare_conn)
        assert result == []


# ---------------------------------------------------------------------------
# 6. Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_is_enabled_missing_table_returns_false(self, bare_conn):
        """OperationalError from a missing table makes is_enabled return False."""
        assert is_enabled(bare_conn, "anything") is False

    def test_get_all_flags_missing_table_returns_empty(self, bare_conn):
        """OperationalError from a missing table makes get_all_flags return []."""
        assert get_all_flags(bare_conn) == []


# ---------------------------------------------------------------------------
# 7. is_flag_enabled alias
# ---------------------------------------------------------------------------


class TestIsFlagEnabled:
    def test_alias_delegates_to_is_enabled(self, conn):
        """is_flag_enabled returns the same result as is_enabled."""
        set_flag(conn, "ai_conversation_mode", enabled=True, rollout_pct=100)
        assert is_flag_enabled(conn, "ai_conversation_mode") is True
        assert is_flag_enabled(conn, "ai_conversation_mode") == is_enabled(conn, "ai_conversation_mode")

    def test_alias_respects_rollout(self, conn):
        """is_flag_enabled uses the same deterministic rollout as is_enabled."""
        set_flag(conn, "ai_grammar_explanation", enabled=True, rollout_pct=50)
        for uid in range(50):
            assert is_flag_enabled(conn, "ai_grammar_explanation", user_id=uid) == \
                   is_enabled(conn, "ai_grammar_explanation", user_id=uid)

    def test_alias_disabled_flag(self, conn):
        """is_flag_enabled returns False for a disabled flag."""
        set_flag(conn, "ai_pronunciation_feedback", enabled=False, rollout_pct=100)
        assert is_flag_enabled(conn, "ai_pronunciation_feedback") is False

    def test_alias_missing_flag(self, conn):
        """is_flag_enabled returns False for a flag that does not exist."""
        assert is_flag_enabled(conn, "nonexistent_ai_flag") is False

    def test_alias_missing_table(self, bare_conn):
        """is_flag_enabled returns False when the table does not exist."""
        assert is_flag_enabled(bare_conn, "anything") is False


# ---------------------------------------------------------------------------
# 8. AI_FEATURE_FLAGS constant
# ---------------------------------------------------------------------------


class TestAIFeatureFlags:
    def test_all_expected_flags_present(self):
        """AI_FEATURE_FLAGS contains the five expected AI feature flags."""
        expected = {
            "ai_conversation_mode",
            "ai_content_generation",
            "ai_pronunciation_feedback",
            "ai_grammar_explanation",
            "ai_adaptive_difficulty",
        }
        assert set(AI_FEATURE_FLAGS.keys()) == expected

    def test_all_flags_have_descriptions(self):
        """Every AI feature flag has a non-empty description."""
        for name, desc in AI_FEATURE_FLAGS.items():
            assert isinstance(desc, str) and len(desc) > 0, f"{name} missing description"
