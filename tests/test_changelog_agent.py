"""Tests for mandarin.openclaw.changelog_agent — commit parsing, classification, drafting, formatting."""

import json
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from mandarin.openclaw.changelog_agent import (
    ChangeCategory,
    ChangeClassifier,
    ChangelogDrafter,
    ChangelogEntry,
    ChangelogFormatter,
    ChangelogManager,
    CommitParser,
    ParsedCommit,
)


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _commit(msg="update thing", files=None, hash_val=None):
    return ParsedCommit(
        hash=hash_val or "a" * 40,
        author="dev",
        date="2026-03-10 12:00:00 +0000",
        message=msg,
        files_changed=files or [],
        insertions=10,
        deletions=2,
    )


# ── Enum coverage ─────────────────────────────────────────

class TestChangeCategoryEnum(unittest.TestCase):
    def test_all_values(self):
        expected = {"feature", "improvement", "fix", "content", "infrastructure", "internal"}
        actual = {c.value for c in ChangeCategory}
        self.assertEqual(expected, actual)


# ── ParsedCommit dataclass ────────────────────────────────

class TestParsedCommit(unittest.TestCase):
    def test_defaults(self):
        c = ParsedCommit(hash="abc", author="me", date="now", message="hi")
        self.assertEqual(c.files_changed, [])
        self.assertEqual(c.insertions, 0)
        self.assertEqual(c.deletions, 0)


# ── ChangelogEntry dataclass ─────────────────────────────

class TestChangelogEntry(unittest.TestCase):
    def test_construction(self):
        e = ChangelogEntry(
            date="2026-03-10", version_hint="v2.1",
            sections={"feature": ["New drill type"]},
            summary="1 new feature", commit_count=3,
        )
        self.assertEqual(e.commit_count, 3)
        self.assertIn("feature", e.sections)


# ── CommitParser ──────────────────────────────────────────

class TestCommitParser(unittest.TestCase):
    def setUp(self):
        self.parser = CommitParser()

    def test_parse_git_log_single_commit(self):
        output = (
            "a" * 40 + "|Alice|2026-03-10 12:00:00 +0000|Add tone drill\n"
            " mandarin/drills/tone.py | 42 ++++\n"
            " 1 file changed, 42 insertions(+)\n"
        )
        commits = self.parser._parse_git_log(output)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0].author, "Alice")
        self.assertEqual(commits[0].message, "Add tone drill")
        self.assertIn("mandarin/drills/tone.py", commits[0].files_changed)
        self.assertEqual(commits[0].insertions, 42)

    def test_parse_git_log_multiple_commits(self):
        h1 = "a" * 40
        h2 = "b" * 40
        output = (
            f"{h1}|Alice|2026-03-10|First commit\n"
            " file1.py | 10 ++\n"
            " 1 file changed, 10 insertions(+)\n"
            f"{h2}|Bob|2026-03-11|Second commit\n"
            " file2.py | 5 ++\n"
            " 1 file changed, 5 insertions(+)\n"
        )
        commits = self.parser._parse_git_log(output)
        self.assertEqual(len(commits), 2)
        self.assertEqual(commits[0].hash, h1)
        self.assertEqual(commits[1].hash, h2)

    def test_parse_git_log_empty(self):
        commits = self.parser._parse_git_log("")
        self.assertEqual(commits, [])

    @patch("subprocess.run")
    def test_parse_recent_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="a" * 40 + "|Dev|2026-03-10|Test\n 1 file changed\n"
        )
        commits = self.parser.parse_recent("/tmp/repo")
        self.assertEqual(len(commits), 1)

    @patch("subprocess.run")
    def test_parse_recent_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        commits = self.parser.parse_recent("/tmp/repo")
        self.assertEqual(commits, [])

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_parse_recent_git_not_found(self, mock_run):
        commits = self.parser.parse_recent("/tmp/repo")
        self.assertEqual(commits, [])

    @patch("subprocess.run", side_effect=OSError("timeout"))
    def test_parse_recent_os_error(self, mock_run):
        commits = self.parser.parse_recent("/tmp/repo")
        self.assertEqual(commits, [])


# ── ChangeClassifier ──────────────────────────────────────

class TestChangeClassifier(unittest.TestCase):
    def setUp(self):
        self.cls = ChangeClassifier()

    def test_fix_keyword(self):
        c = _commit("fix crash in scheduler")
        self.assertEqual(self.cls.classify(c), ChangeCategory.FIX)

    def test_bug_keyword(self):
        c = _commit("bug: handle None in drill runner")
        self.assertEqual(self.cls.classify(c), ChangeCategory.FIX)

    def test_internal_files(self):
        c = _commit("update test coverage", files=["tests/test_foo.py"])
        self.assertEqual(self.cls.classify(c), ChangeCategory.INTERNAL)

    def test_infra_files(self):
        c = _commit("update deployment", files=["Dockerfile"])
        self.assertEqual(self.cls.classify(c), ChangeCategory.INFRASTRUCTURE)

    def test_content_files(self):
        c = _commit("add scenarios", files=["data/scenarios/new.json"])
        self.assertEqual(self.cls.classify(c), ChangeCategory.CONTENT)

    def test_feature_message_and_path(self):
        c = _commit("add new drill type", files=["mandarin/drills/tone.py"])
        self.assertEqual(self.cls.classify(c), ChangeCategory.FEATURE)

    def test_ui_files_improvement(self):
        c = _commit("update layout", files=["mandarin/web/templates/base.html"])
        self.assertEqual(self.cls.classify(c), ChangeCategory.IMPROVEMENT)

    def test_feature_keyword_no_files(self):
        c = _commit("add support for HSK 7")
        self.assertEqual(self.cls.classify(c), ChangeCategory.FEATURE)

    def test_default_improvement(self):
        c = _commit("tweak spacing")
        self.assertEqual(self.cls.classify(c), ChangeCategory.IMPROVEMENT)

    def test_is_user_facing_true(self):
        for cat in (ChangeCategory.FEATURE, ChangeCategory.IMPROVEMENT,
                    ChangeCategory.FIX, ChangeCategory.CONTENT):
            self.assertTrue(ChangeClassifier.is_user_facing(cat))

    def test_is_user_facing_false(self):
        for cat in (ChangeCategory.INFRASTRUCTURE, ChangeCategory.INTERNAL):
            self.assertFalse(ChangeClassifier.is_user_facing(cat))

    def test_content_with_py_not_content(self):
        c = _commit("update loader", files=["data/contexts/new.json", "mandarin/loader.py"])
        result = self.cls.classify(c)
        self.assertNotEqual(result, ChangeCategory.CONTENT)


# ── ChangelogDrafter ──────────────────────────────────────

class TestChangelogDrafter(unittest.TestCase):
    def setUp(self):
        self.drafter = ChangelogDrafter()

    def test_draft_single_feature(self):
        commits = [_commit("add tone drill", files=["mandarin/drills/tone.py"])]
        cats = [ChangeCategory.FEATURE]
        entry = self.drafter.draft_entry(commits, cats)
        self.assertIn("feature", entry.sections)
        self.assertEqual(entry.commit_count, 1)

    def test_internal_excluded(self):
        commits = [_commit("update test", files=["tests/foo.py"])]
        cats = [ChangeCategory.INTERNAL]
        entry = self.drafter.draft_entry(commits, cats)
        self.assertEqual(entry.sections, {})

    def test_humanize_fix_npe(self):
        c = _commit("fix NPE in scheduler")
        result = self.drafter._humanize_commit(c, ChangeCategory.FIX)
        self.assertIn("fail unexpectedly", result.lower())

    def test_humanize_add_hsk_scenario(self):
        c = _commit("add HSK3 scenario for dining")
        result = self.drafter._humanize_commit(c, ChangeCategory.CONTENT)
        self.assertIn("HSK 3", result)

    def test_humanize_add_drill(self):
        c = _commit("add dictation drill type")
        result = self.drafter._humanize_commit(c, ChangeCategory.FEATURE)
        self.assertIn("drill type", result.lower())

    def test_humanize_default_capitalize(self):
        c = _commit("chore: bump version")
        result = self.drafter._humanize_commit(c, ChangeCategory.IMPROVEMENT)
        self.assertTrue(result[0].isupper())
        self.assertTrue(result.endswith("."))

    def test_summary_generation(self):
        sections = {"feature": ["a", "b"], "fix": ["c"]}
        summary = self.drafter._generate_summary(sections)
        self.assertIn("2 new feature", summary)
        self.assertIn("1 bug fix", summary)

    def test_summary_empty(self):
        summary = self.drafter._generate_summary({})
        self.assertEqual(summary, "Maintenance update")

    def test_deduplication(self):
        commits = [_commit("add thing"), _commit("add thing")]
        cats = [ChangeCategory.FEATURE, ChangeCategory.FEATURE]
        entry = self.drafter.draft_entry(commits, cats)
        # Should deduplicate within sections
        if "feature" in entry.sections:
            self.assertEqual(len(entry.sections["feature"]),
                             len(set(entry.sections["feature"])))


# ── ChangelogFormatter ────────────────────────────────────

class TestChangelogFormatter(unittest.TestCase):
    def setUp(self):
        self.fmt = ChangelogFormatter()
        self.entry = ChangelogEntry(
            date="2026-03-10", version_hint="",
            sections={"feature": ["New tone drill"], "fix": ["Fixed crash"]},
            summary="1 feature, 1 fix", commit_count=5,
        )

    def test_markdown(self):
        md = self.fmt.format_markdown(self.entry)
        self.assertIn("## 2026-03-10", md)
        self.assertIn("### New Features", md)
        self.assertIn("- New tone drill", md)

    def test_html(self):
        html = self.fmt.format_html(self.entry)
        self.assertIn("<h2>2026-03-10</h2>", html)
        self.assertIn("<li>New tone drill</li>", html)

    def test_plain(self):
        txt = self.fmt.format_plain(self.entry)
        self.assertIn("New Features:", txt)
        self.assertIn("- New tone drill", txt)


# ── ChangelogManager (integration) ────────────────────────

class TestChangelogManager(unittest.TestCase):
    @patch("subprocess.run")
    def test_generate_returns_none_no_commits(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mgr = ChangelogManager("/tmp/repo")
        result = mgr.generate()
        self.assertIsNone(result)

    @patch("subprocess.run")
    def test_generate_all_internal_returns_none(self, mock_run):
        h = "a" * 40
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f"{h}|Dev|2026-03-10|update tests\n tests/foo.py | 5 ++\n 1 file changed, 5 insertions(+)\n"
        )
        mgr = ChangelogManager("/tmp/repo")
        result = mgr.generate()
        self.assertIsNone(result)

    def test_queue_for_review(self):
        conn = _make_conn()
        entry = ChangelogEntry(
            date="2026-03-10", version_hint="",
            sections={"feature": ["New thing"]},
            summary="1 feature", commit_count=1,
        )
        mgr = ChangelogManager()
        mgr.queue_for_review(conn, entry)
        pending = mgr.get_pending(conn)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "pending")

    def test_approve_and_publish(self):
        conn = _make_conn()
        entry = ChangelogEntry(
            date="2026-03-10", version_hint="",
            sections={"feature": ["New thing"]},
            summary="1 feature", commit_count=1,
        )
        mgr = ChangelogManager()
        mgr.queue_for_review(conn, entry)
        pending = mgr.get_pending(conn)
        result = mgr.approve_and_publish(conn, pending[0]["id"])
        self.assertIn("markdown", result)
        self.assertIn("html", result)
        self.assertIn("plain", result)

    def test_approve_nonexistent(self):
        conn = _make_conn()
        mgr = ChangelogManager()
        # Create the table first
        entry = ChangelogEntry(date="x", version_hint="", sections={}, summary="", commit_count=0)
        mgr.queue_for_review(conn, entry)
        result = mgr.approve_and_publish(conn, 9999)
        self.assertIn("error", result)

    def test_get_published(self):
        conn = _make_conn()
        entry = ChangelogEntry(
            date="2026-03-10", version_hint="",
            sections={"fix": ["Fixed thing"]},
            summary="1 fix", commit_count=1,
        )
        mgr = ChangelogManager()
        mgr.queue_for_review(conn, entry)
        pending = mgr.get_pending(conn)
        mgr.approve_and_publish(conn, pending[0]["id"])
        published = mgr.get_published(conn)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["status"], "published")

    def test_get_pending_no_table(self):
        conn = _make_conn()
        mgr = ChangelogManager()
        result = mgr.get_pending(conn)
        self.assertEqual(result, [])

    def test_get_published_no_table(self):
        conn = _make_conn()
        mgr = ChangelogManager()
        result = mgr.get_published(conn)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
