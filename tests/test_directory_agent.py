"""Tests for mandarin.openclaw.directory_agent — registry, listing copy, submission tracking, reviews."""

import sqlite3
import unittest

from mandarin.openclaw.directory_agent import (
    Directory,
    DirectoryManager,
    DirectoryRegistry,
    ListingCopy,
    ListingCopyGenerator,
    Review,
    ReviewMonitor,
    SubmissionTracker,
)


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── Directory dataclass ───────────────────────────────────

class TestDirectoryDataclass(unittest.TestCase):
    def test_defaults(self):
        d = Directory("Test", "https://test.com", "app_store")
        self.assertEqual(d.submission_url, "")
        self.assertEqual(d.requirements, [])
        self.assertEqual(d.priority, 3)
        self.assertEqual(d.status, "not_submitted")
        self.assertEqual(d.submitted_date, "")
        self.assertEqual(d.listed_date, "")

    def test_full_construction(self):
        d = Directory("Store", "https://store.com", "edtech",
                      "https://store.com/submit", ["req1"], 1, "submitted", "2026-03-01", "")
        self.assertEqual(d.priority, 1)
        self.assertEqual(d.requirements, ["req1"])


class TestListingCopy(unittest.TestCase):
    def test_construction(self):
        lc = ListingCopy("Title", "Short desc", "Long desc", ["kw"], ["cat"], ["ss1"])
        self.assertIn("1024x1024", lc.icon_spec)


class TestReview(unittest.TestCase):
    def test_defaults(self):
        r = Review("app_store", 5, "Great", "2026-03-10")
        self.assertFalse(r.responded)
        self.assertEqual(r.response, "")


# ── DirectoryRegistry ─────────────────────────────────────

class TestDirectoryRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = DirectoryRegistry()

    def test_at_least_30_directories(self):
        dirs = self.reg.get_directories()
        self.assertGreaterEqual(len(dirs), 30)

    def test_all_have_name_and_url(self):
        for d in self.reg.get_directories():
            self.assertTrue(d.name, f"Directory missing name")
            self.assertTrue(d.url, f"Directory {d.name} missing url")

    def test_categories_present(self):
        cats = self.reg.get_categories()
        expected = {"app_store", "product_hunt", "edtech", "language",
                    "university", "review_site", "developer"}
        self.assertEqual(set(cats), expected)

    def test_get_by_category_app_store(self):
        stores = self.reg.get_by_category("app_store")
        self.assertGreater(len(stores), 0)
        names = [d.name for d in stores]
        self.assertIn("Apple App Store", names)
        self.assertIn("Google Play Store", names)

    def test_get_by_category_empty(self):
        result = self.reg.get_by_category("nonexistent_category")
        self.assertEqual(result, [])

    def test_get_by_priority(self):
        high_priority = self.reg.get_by_priority(2)
        self.assertGreater(len(high_priority), 0)
        for d in high_priority:
            self.assertLessEqual(d.priority, 2)
        # Should be sorted by priority
        priorities = [d.priority for d in high_priority]
        self.assertEqual(priorities, sorted(priorities))

    def test_priority_1_includes_app_stores(self):
        p1 = self.reg.get_by_priority(1)
        names = {d.name for d in p1}
        self.assertIn("Apple App Store", names)
        self.assertIn("Google Play Store", names)
        self.assertIn("ProductHunt", names)

    def test_all_priorities_1_to_5(self):
        for d in self.reg.get_directories():
            self.assertIn(d.priority, (1, 2, 3, 4, 5),
                          f"Directory {d.name} has invalid priority {d.priority}")


# ── ListingCopyGenerator ─────────────────────────────────

class TestListingCopyGenerator(unittest.TestCase):
    def setUp(self):
        self.gen = ListingCopyGenerator()

    def test_product_hunt_listing(self):
        d = Directory("ProductHunt", "https://producthunt.com", "product_hunt")
        copy = self.gen.generate_listing(d)
        self.assertIn("aelu", copy.title.lower())
        self.assertLessEqual(len(copy.short_description), 80)
        self.assertIn("mandarin", copy.keywords)

    def test_app_store_listing(self):
        d = Directory("Apple App Store", "https://apps.apple.com", "app_store")
        copy = self.gen.generate_listing(d)
        self.assertIn("Mandarin", copy.title)
        self.assertIn("HSK", copy.description)
        self.assertIn("Language Learning", copy.categories)

    def test_edtech_listing(self):
        d = Directory("EdSurge", "https://edsurge.com", "edtech")
        copy = self.gen.generate_listing(d)
        self.assertIn("institutional", copy.description.lower())
        self.assertIn("FERPA", copy.keywords)

    def test_review_site_listing(self):
        d = Directory("TrustPilot", "https://trustpilot.com", "review_site")
        copy = self.gen.generate_listing(d)
        self.assertEqual(copy.title, "Aelu")

    def test_default_listing(self):
        d = Directory("Unknown", "https://example.com", "some_other_category")
        copy = self.gen.generate_listing(d)
        self.assertIn("Aelu", copy.title)

    def test_short_description_under_80_chars(self):
        # Test all category types
        categories = ["product_hunt", "app_store", "edtech", "review_site", "language"]
        for cat in categories:
            d = Directory("Test", "https://x.com", cat)
            copy = self.gen.generate_listing(d)
            self.assertLessEqual(len(copy.short_description), 80,
                                 f"Category {cat} short_description too long")

    def test_screenshots_needed_present(self):
        d = Directory("Apple App Store", "https://apps.apple.com", "app_store")
        copy = self.gen.generate_listing(d)
        self.assertGreater(len(copy.screenshots_needed), 0)


# ── SubmissionTracker ─────────────────────────────────────

class TestSubmissionTracker(unittest.TestCase):
    def test_no_conn(self):
        tracker = SubmissionTracker(conn=None)
        status = tracker.get_submission_status()
        self.assertEqual(status, {"error": "no connection"})

    def test_record_and_retrieve(self):
        conn = _make_conn()
        tracker = SubmissionTracker(conn)
        tracker.record_submission("ProductHunt", "submitted", "first try")
        status = tracker.get_submission_status()
        self.assertEqual(status["submitted"], 1)

    def test_update_status(self):
        conn = _make_conn()
        tracker = SubmissionTracker(conn)
        tracker.record_submission("ProductHunt", "submitted")
        tracker.update_status("ProductHunt", "listed", "https://producthunt.com/posts/aelu")
        row = conn.execute(
            "SELECT * FROM directory_submission WHERE directory_name = 'ProductHunt'"
        ).fetchone()
        self.assertEqual(row["status"], "listed")
        self.assertEqual(row["listing_url"], "https://producthunt.com/posts/aelu")

    def test_upsert_on_duplicate(self):
        conn = _make_conn()
        tracker = SubmissionTracker(conn)
        tracker.record_submission("ProductHunt", "submitted", "v1")
        tracker.record_submission("ProductHunt", "pending", "v2")
        rows = conn.execute("SELECT * FROM directory_submission WHERE directory_name = 'ProductHunt'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "pending")

    def test_get_next_submissions(self):
        conn = _make_conn()
        tracker = SubmissionTracker(conn)
        next_dirs = tracker.get_next_submissions(5)
        self.assertGreater(len(next_dirs), 0)
        self.assertLessEqual(len(next_dirs), 5)
        # Should be sorted by priority
        priorities = [d.priority for d in next_dirs]
        self.assertEqual(priorities, sorted(priorities))

    def test_get_next_excludes_submitted(self):
        conn = _make_conn()
        tracker = SubmissionTracker(conn)
        tracker.record_submission("Apple App Store", "submitted")
        next_dirs = tracker.get_next_submissions(50)
        names = [d.name for d in next_dirs]
        self.assertNotIn("Apple App Store", names)

    def test_record_submission_no_conn(self):
        tracker = SubmissionTracker(conn=None)
        # Should not raise
        tracker.record_submission("Test", "submitted")

    def test_update_status_no_conn(self):
        tracker = SubmissionTracker(conn=None)
        tracker.update_status("Test", "listed")


# ── ReviewMonitor ─────────────────────────────────────────

class TestReviewMonitor(unittest.TestCase):
    def setUp(self):
        self.rm = ReviewMonitor()

    def test_unresponded_empty(self):
        self.assertEqual(self.rm.get_unresponded_reviews(), [])

    def test_draft_response_positive(self):
        r = Review("app_store", 5, "Love it", "2026-03-10")
        resp = self.rm.draft_response(r)
        self.assertIn("thank", resp.lower())

    def test_draft_response_neutral(self):
        r = Review("app_store", 3, "It's ok", "2026-03-10")
        resp = self.rm.draft_response(r)
        self.assertIn("feedback", resp.lower())

    def test_draft_response_negative(self):
        r = Review("app_store", 1, "Terrible", "2026-03-10")
        resp = self.rm.draft_response(r)
        self.assertIn("sorry", resp.lower())
        self.assertIn("support@aelu.app", resp)

    def test_draft_response_boundary_4(self):
        r = Review("play_store", 4, "Pretty good", "2026-03-10")
        resp = self.rm.draft_response(r)
        self.assertIn("thank", resp.lower())

    def test_draft_response_boundary_2(self):
        r = Review("play_store", 2, "Meh", "2026-03-10")
        resp = self.rm.draft_response(r)
        self.assertIn("sorry", resp.lower())


# ── DirectoryManager (integration) ────────────────────────

class TestDirectoryManager(unittest.TestCase):
    def test_audit_no_conn(self):
        mgr = DirectoryManager()
        audit = mgr.audit()
        self.assertGreaterEqual(audit["total_directories"], 30)
        self.assertIn("by_category", audit)
        self.assertIn("submission_status", audit)

    def test_audit_with_conn(self):
        conn = _make_conn()
        mgr = DirectoryManager(conn)
        audit = mgr.audit()
        self.assertGreaterEqual(audit["total_directories"], 30)

    def test_prepare_submissions(self):
        conn = _make_conn()
        mgr = DirectoryManager(conn)
        subs = mgr.prepare_submissions(3)
        self.assertLessEqual(len(subs), 3)
        for s in subs:
            self.assertIn("directory", s)
            self.assertIn("copy", s)
            self.assertIn("title", s["copy"])

    def test_submission_checklist(self):
        mgr = DirectoryManager()
        checklist = mgr.get_submission_checklist()
        self.assertGreater(len(checklist), 0)
        for item in checklist:
            self.assertLessEqual(item["priority"], 3)

    def test_track_submission(self):
        conn = _make_conn()
        mgr = DirectoryManager(conn)
        mgr.track_submission("ProductHunt", "submitted")
        status = mgr.tracker.get_submission_status()
        self.assertEqual(status["submitted"], 1)

    def test_monitor_reviews(self):
        mgr = DirectoryManager()
        reviews = mgr.monitor_reviews()
        self.assertEqual(reviews, [])


if __name__ == "__main__":
    unittest.main()
