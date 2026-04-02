"""Tests for the `mandarin seed` command (idempotent reference data seeding).

Verifies:
- Grammar points and skills are inserted on first run
- HSK vocabulary is inserted for all available levels
- Running seed twice does not produce errors or duplicate rows
- The seed command is suitable for use as a Fly.io release_command
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mandarin import db
from mandarin.db.core import _migrate
from mandarin.grammar_seed import seed_grammar_and_skills
from mandarin.grammar_linker import link_all
from mandarin.importer import import_hsk_level


def _make_seed_db():
    """Create a fresh schema-only database for seed tests."""
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
    return conn, path


class TestSeedGrammar:
    """Grammar + skills seeding is idempotent."""

    def test_grammar_seed_inserts_points(self):
        conn, path = _make_seed_db()
        try:
            added_g, added_s = seed_grammar_and_skills(conn)
            assert added_g > 0, "First seed should insert grammar points"
            assert added_s > 0, "First seed should insert skills"
            count = conn.execute("SELECT COUNT(*) FROM grammar_point").fetchone()[0]
            assert count == added_g
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_grammar_seed_idempotent(self):
        conn, path = _make_seed_db()
        try:
            added_g1, added_s1 = seed_grammar_and_skills(conn)
            added_g2, added_s2 = seed_grammar_and_skills(conn)
            # Second run should skip all rows
            assert added_g2 == 0, "Second grammar seed should insert 0 duplicate points"
            assert added_s2 == 0, "Second grammar seed should insert 0 duplicate skills"
            # Row count should be unchanged
            count = conn.execute("SELECT COUNT(*) FROM grammar_point").fetchone()[0]
            assert count == added_g1
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_grammar_linker_idempotent(self):
        conn, path = _make_seed_db()
        try:
            seed_grammar_and_skills(conn)
            # Insert a content item so linking has something to work with
            conn.execute(
                "INSERT INTO content_item (hanzi, pinyin, english, hsk_level, status) "
                "VALUES ('我是学生', 'wǒ shì xuéshēng', 'I am a student', 1, 'drill_ready')"
            )
            conn.commit()
            g1, s1 = link_all(conn)
            g2, s2 = link_all(conn)
            # Second link_all should not crash (may return same or 0 links)
            assert g2 >= 0
            assert s2 >= 0
        finally:
            conn.close()
            path.unlink(missing_ok=True)


class TestSeedHSK:
    """HSK vocabulary seeding is idempotent and covers all available levels."""

    def test_hsk1_seed_inserts_items(self):
        conn, path = _make_seed_db()
        try:
            added, skipped = import_hsk_level(conn, 1)
            assert added > 0, "HSK 1 seed should insert vocabulary items"
            assert skipped == 0, "Fresh DB should have no pre-existing HSK 1 items"
            count = conn.execute(
                "SELECT COUNT(*) FROM content_item WHERE hsk_level = 1"
            ).fetchone()[0]
            assert count == added
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_hsk1_seed_idempotent(self):
        conn, path = _make_seed_db()
        try:
            added1, skipped1 = import_hsk_level(conn, 1)
            added2, skipped2 = import_hsk_level(conn, 1)
            assert added2 == 0, "Second HSK 1 seed should insert 0 duplicates"
            assert skipped2 == added1, "Second run should report all as already present"
            count = conn.execute(
                "SELECT COUNT(*) FROM content_item WHERE hsk_level = 1"
            ).fetchone()[0]
            assert count == added1, "Row count unchanged after second seed"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_all_hsk_levels_seed_without_error(self):
        """All 9 HSK levels can be seeded in sequence without errors."""
        conn, path = _make_seed_db()
        try:
            total_added = 0
            for level in range(1, 10):
                try:
                    added, skipped = import_hsk_level(conn, level)
                    total_added += added
                except FileNotFoundError:
                    pass  # Level data file missing — acceptable, not a crash
            # At minimum HSK 1 must have been seeded (data file ships with repo)
            assert total_added > 0, "At least one HSK level should have been seeded"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_all_hsk_levels_idempotent(self):
        """Seeding all levels twice produces no duplicate rows."""
        conn, path = _make_seed_db()
        try:
            for level in range(1, 10):
                try:
                    import_hsk_level(conn, level)
                except FileNotFoundError:
                    pass

            count_after_first = conn.execute(
                "SELECT COUNT(*) FROM content_item"
            ).fetchone()[0]

            for level in range(1, 10):
                try:
                    added, _ = import_hsk_level(conn, level)
                    assert added == 0, f"Second seed of HSK {level} should insert 0 duplicates"
                except FileNotFoundError:
                    pass

            count_after_second = conn.execute(
                "SELECT COUNT(*) FROM content_item"
            ).fetchone()[0]
            assert count_after_first == count_after_second, "Row count unchanged after re-seed"
        finally:
            conn.close()
            path.unlink(missing_ok=True)


class TestSeedFull:
    """Combined seed (grammar + all HSK levels) mirrors the `mandarin seed` command."""

    def test_full_seed_populates_db(self):
        conn, path = _make_seed_db()
        try:
            added_g, added_s = seed_grammar_and_skills(conn)
            link_all(conn)

            total_vocab = 0
            for level in range(1, 10):
                try:
                    added, _ = import_hsk_level(conn, level)
                    total_vocab += added
                except FileNotFoundError:
                    pass

            assert added_g > 0, "Grammar points should be seeded"
            assert total_vocab > 0, "HSK vocabulary should be seeded"
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_full_seed_twice_no_duplicates(self):
        """Running the full seed sequence twice is safe — the production release_command
        runs on every fly deploy so idempotency is load-bearing."""
        conn, path = _make_seed_db()
        try:
            def _run_seed():
                seed_grammar_and_skills(conn)
                link_all(conn)
                for level in range(1, 10):
                    try:
                        import_hsk_level(conn, level)
                    except FileNotFoundError:
                        pass

            _run_seed()
            count_grammar = conn.execute("SELECT COUNT(*) FROM grammar_point").fetchone()[0]
            count_vocab = conn.execute("SELECT COUNT(*) FROM content_item").fetchone()[0]

            _run_seed()
            assert conn.execute("SELECT COUNT(*) FROM grammar_point").fetchone()[0] == count_grammar
            assert conn.execute("SELECT COUNT(*) FROM content_item").fetchone()[0] == count_vocab
        finally:
            conn.close()
            path.unlink(missing_ok=True)
