"""Tests for telemetry trustworthiness — dedup, schema validation, rate limiting."""

import json
import sqlite3

import pytest

from mandarin.telemetry import is_valid_event, VALID_EVENTS, RATE_LIMIT_PER_HOUR, ACTIVATION_EVENTS


class TestCanonicalEventSchema:

    def test_valid_known_event(self):
        assert is_valid_event("paywall", "shown") is True

    def test_valid_open_ended_category(self):
        """Adoption category accepts any event name."""
        assert is_valid_event("adoption", "some_new_feature") is True

    def test_invalid_category(self):
        assert is_valid_event("bogus_category", "test") is False

    def test_invalid_event_in_known_category(self):
        assert is_valid_event("paywall", "nonexistent_event") is False

    def test_all_known_categories_have_entry(self):
        expected = {"paywall", "nav", "session", "ws", "audio", "view",
                    "grammar", "nps", "report", "adoption", "error", "activation",
                    "drill_timing", "ux", "onboarding"}
        assert set(VALID_EVENTS.keys()) == expected

    def test_activation_events_defined(self):
        """Activation events are canonical and include magic moment."""
        assert "first_lookup" in ACTIVATION_EVENTS
        assert "encounter_drilled" in ACTIVATION_EVENTS
        assert "first_encounter_drilled" in ACTIVATION_EVENTS

    def test_activation_client_events_valid(self):
        assert is_valid_event("activation", "first_lookup") is True
        assert is_valid_event("activation", "first_encounter_drilled") is True

    def test_session_events(self):
        assert is_valid_event("session", "start") is True
        assert is_valid_event("session", "complete") is True
        assert is_valid_event("session", "early_exit") is True
        assert is_valid_event("session", "made_up") is False


class TestEventDedup:

    def test_dedup_rejects_duplicate_event_id(self, test_db):
        """INSERT OR IGNORE prevents duplicate event_id."""
        conn, _ = test_db
        event_id = "test-uuid-1234"
        conn.execute(
            """INSERT INTO client_event (event_id, install_id, category, event)
               VALUES (?, 'inst1', 'nav', 'transition')""",
            (event_id,),
        )
        conn.commit()

        # Second insert with same event_id should be silently ignored
        conn.execute(
            """INSERT OR IGNORE INTO client_event (event_id, install_id, category, event)
               VALUES (?, 'inst1', 'nav', 'transition')""",
            (event_id,),
        )
        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM client_event WHERE event_id = ?", (event_id,)
        ).fetchone()[0]
        assert count == 1

    def test_null_event_ids_allowed(self, test_db):
        """Legacy events without event_id can coexist (NULLs are not unique)."""
        conn, _ = test_db
        for _ in range(3):
            conn.execute(
                """INSERT INTO client_event (install_id, category, event)
                   VALUES ('inst1', 'nav', 'transition')"""
            )
        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM client_event WHERE event_id IS NULL AND category = 'nav'"
        ).fetchone()[0]
        assert count == 3

    def test_different_event_ids_both_inserted(self, test_db):
        conn, _ = test_db
        conn.execute(
            """INSERT INTO client_event (event_id, install_id, category, event)
               VALUES ('uuid-a', 'inst1', 'session', 'start')"""
        )
        conn.execute(
            """INSERT OR IGNORE INTO client_event (event_id, install_id, category, event)
               VALUES ('uuid-b', 'inst1', 'session', 'complete')"""
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM client_event").fetchone()[0]
        assert count == 2


class TestRateLimiting:

    def test_rate_limit_constant(self):
        assert RATE_LIMIT_PER_HOUR == 500

    def test_rate_limit_check_query(self, test_db):
        """The rate limit query correctly counts recent events."""
        conn, _ = test_db
        install_id = "rate-test-install"

        # Insert some events
        for i in range(10):
            conn.execute(
                """INSERT INTO client_event (install_id, category, event)
                   VALUES (?, 'nav', 'transition')""",
                (install_id,),
            )
        conn.commit()

        recent = conn.execute(
            """SELECT COUNT(*) FROM client_event
               WHERE install_id = ? AND created_at > datetime('now', '-1 hour')""",
            (install_id,),
        ).fetchone()[0]
        assert recent == 10

    def test_different_installs_counted_separately(self, test_db):
        conn, _ = test_db
        for inst in ["inst-a", "inst-b"]:
            for _ in range(5):
                conn.execute(
                    """INSERT INTO client_event (install_id, category, event)
                       VALUES (?, 'nav', 'transition')""",
                    (inst,),
                )
        conn.commit()

        count_a = conn.execute(
            """SELECT COUNT(*) FROM client_event
               WHERE install_id = 'inst-a' AND created_at > datetime('now', '-1 hour')"""
        ).fetchone()[0]
        assert count_a == 5


class TestEventIdColumn:

    def test_event_id_column_exists(self, test_db):
        """Migration v33->v34 adds event_id column."""
        conn, _ = test_db
        cols = {r[1] for r in conn.execute("PRAGMA table_info(client_event)").fetchall()}
        assert "event_id" in cols

    def test_event_id_unique_index_exists(self, test_db):
        """Unique index on event_id prevents duplicates at DB level."""
        conn, _ = test_db
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='client_event'"
        ).fetchall()
        index_names = {r[0] for r in indexes}
        assert "idx_client_event_id" in index_names
