"""Tests for Doc 22: Native Speaker Validation Protocol."""

import unittest

from mandarin.db.core import SCHEMA_VERSION
from mandarin.ai.native_speaker_validation import (
    queue_for_native_speaker_review,
    get_validation_batch,
    export_validation_sheet,
    record_validation_result,
    _apply_validation_verdict,
    analyze_native_speaker_validation,
)


from tests.shared_db import make_test_db as _make_db


def _seed_content_item(conn, hanzi="你好", hsk_level=1):
    """Insert a minimal content_item and return its id."""
    conn.execute(
        "INSERT INTO content_item (hanzi, english, pinyin, hsk_level, status) "
        "VALUES (?, 'hello', 'nǐ hǎo', ?, 'drill_ready')",
        (hanzi, hsk_level),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _seed_user(conn, email="test@aelu.app"):
    """Insert a minimal user and return its id."""
    conn.execute(
        "INSERT INTO user (email, password_hash) VALUES (?, 'hash')",
        (email,),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


class TestQueueManagement(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_queue_item_returns_id(self):
        qid = queue_for_native_speaker_review(
            self.conn,
            content_hanzi="这个东西很好吃",
            content_type="example_sentence",
            queue_reason="drift_risk_flagged",
        )
        self.assertIsNotNone(qid)
        self.assertGreater(qid, 0)

    def test_queue_item_with_all_fields(self):
        ci_id = _seed_content_item(self.conn, "吃饭", 2)
        qid = queue_for_native_speaker_review(
            self.conn,
            content_hanzi="我们去吃饭吧",
            content_type="dialogue",
            queue_reason="hsk_high_level",
            content_item_id=ci_id,
            hsk_level=2,
            content_lens="food",
            target_vocabulary="吃饭",
            intended_register="casual",
        )
        row = self.conn.execute(
            "SELECT * FROM native_speaker_validation_queue WHERE id=?", (qid,)
        ).fetchone()
        self.assertEqual(row["content_hanzi"], "我们去吃饭吧")
        self.assertEqual(row["content_type"], "dialogue")
        self.assertEqual(row["queue_reason"], "hsk_high_level")
        self.assertEqual(row["content_item_id"], ci_id)
        self.assertEqual(row["hsk_level"], 2)
        self.assertEqual(row["content_lens"], "food")
        self.assertEqual(row["target_vocabulary"], "吃饭")
        self.assertEqual(row["intended_register"], "casual")

    def test_queue_item_unvalidated(self):
        qid = queue_for_native_speaker_review(
            self.conn,
            content_hanzi="测试",
            content_type="drill_sentence",
            queue_reason="systematic_review",
        )
        row = self.conn.execute(
            "SELECT validated_at FROM native_speaker_validation_queue WHERE id=?",
            (qid,),
        ).fetchone()
        self.assertIsNone(row["validated_at"])


class TestGetValidationBatch(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def _queue(self, reason, hanzi="test"):
        return queue_for_native_speaker_review(
            self.conn,
            content_hanzi=hanzi,
            content_type="example_sentence",
            queue_reason=reason,
        )

    def test_empty_queue_returns_empty(self):
        batch = get_validation_batch(self.conn)
        self.assertEqual(batch, [])

    def test_priority_ordering(self):
        """drift_risk items should come before systematic_review."""
        self._queue("systematic_review", "sys1")
        self._queue("drift_risk_flagged", "drift1")
        self._queue("human_flagged", "human1")

        batch = get_validation_batch(self.conn, n=10)
        reasons = [item["queue_reason"] for item in batch]
        self.assertEqual(reasons[0], "drift_risk_flagged")
        self.assertLess(reasons.index("human_flagged"), reasons.index("systematic_review"))

    def test_limit_respected(self):
        for i in range(10):
            self._queue("systematic_review", f"item{i}")
        batch = get_validation_batch(self.conn, n=3)
        self.assertEqual(len(batch), 3)

    def test_validated_items_excluded(self):
        qid = self._queue("systematic_review", "already done")
        self.conn.execute(
            "UPDATE native_speaker_validation_queue SET validated_at=datetime('now') WHERE id=?",
            (qid,),
        )
        batch = get_validation_batch(self.conn)
        self.assertEqual(len(batch), 0)


class TestExportValidationSheet(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_export_format(self):
        queue_for_native_speaker_review(
            self.conn,
            content_hanzi="你好世界",
            content_type="example_sentence",
            queue_reason="systematic_review",
            hsk_level=1,
            target_vocabulary="你好",
            intended_register="neutral",
        )
        batch = get_validation_batch(self.conn, n=10)
        sheet = export_validation_sheet(self.conn, batch)

        self.assertIn("Aelu Native Speaker Validation Sheet", sheet)
        self.assertIn("你好世界", sheet)
        self.assertIn("Teaching: 你好", sheet)
        self.assertIn("Register: neutral", sheet)
        self.assertIn("N: ___", sheet)
        self.assertIn("R: ___", sheet)
        self.assertIn("V: ___", sheet)

    def test_export_empty_batch(self):
        sheet = export_validation_sheet(self.conn, [])
        self.assertIn("Items: 0", sheet)


class TestRecordValidation(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()
        self.ci_id = _seed_content_item(self.conn, "测试句子", 3)
        self.validator_id = _seed_user(self.conn, "validator@aelu.app")
        self.qid = queue_for_native_speaker_review(
            self.conn,
            content_hanzi="这是测试句子",
            content_type="example_sentence",
            queue_reason="systematic_review",
            content_item_id=self.ci_id,
        )

    def test_approve_marks_validated(self):
        result = record_validation_result(
            self.conn, self.qid, self.validator_id,
            naturalness_score=5, register_correct=True,
            usage_current=True, verdict="approved",
        )
        self.assertEqual(result["verdict"], "approved")
        self.assertEqual(result["action_taken"], "approved_to_srs")

        ci = self.conn.execute(
            "SELECT native_speaker_validated FROM content_item WHERE id=?",
            (self.ci_id,),
        ).fetchone()
        self.assertEqual(ci["native_speaker_validated"], 1)

    def test_approve_with_note(self):
        result = record_validation_result(
            self.conn, self.qid, self.validator_id,
            naturalness_score=4, register_correct=True,
            usage_current=True, verdict="approved_with_note",
            validator_note="Slightly formal but acceptable",
        )
        self.assertEqual(result["action_taken"], "approved_to_srs")

        ci = self.conn.execute(
            "SELECT native_speaker_note FROM content_item WHERE id=?",
            (self.ci_id,),
        ).fetchone()
        self.assertEqual(ci["native_speaker_note"], "Slightly formal but acceptable")

    def test_needs_revision_requeues(self):
        result = record_validation_result(
            self.conn, self.qid, self.validator_id,
            naturalness_score=2, register_correct=False,
            usage_current=True, verdict="needs_revision",
            revised_content="这是修改后的句子",
        )
        self.assertEqual(result["action_taken"], "queued_for_revision")

        ci = self.conn.execute(
            "SELECT suspended_for_revision FROM content_item WHERE id=?",
            (self.ci_id,),
        ).fetchone()
        self.assertEqual(ci["suspended_for_revision"], 1)

        new_entry = self.conn.execute(
            "SELECT * FROM native_speaker_validation_queue WHERE content_hanzi=?",
            ("这是修改后的句子",),
        ).fetchone()
        self.assertIsNotNone(new_entry)
        self.assertEqual(new_entry["queue_reason"], "systematic_review")

    def test_reject_marks_rejected(self):
        result = record_validation_result(
            self.conn, self.qid, self.validator_id,
            naturalness_score=1, register_correct=False,
            usage_current=False, verdict="reject",
        )
        self.assertEqual(result["action_taken"], "rejected")

        ci = self.conn.execute(
            "SELECT rejected_native_speaker FROM content_item WHERE id=?",
            (self.ci_id,),
        ).fetchone()
        self.assertEqual(ci["rejected_native_speaker"], 1)

    def test_validation_timestamps_recorded(self):
        record_validation_result(
            self.conn, self.qid, self.validator_id,
            naturalness_score=4, register_correct=True,
            usage_current=True, verdict="approved",
        )
        row = self.conn.execute(
            "SELECT validated_at, validated_by FROM native_speaker_validation_queue WHERE id=?",
            (self.qid,),
        ).fetchone()
        self.assertIsNotNone(row["validated_at"])
        self.assertEqual(row["validated_by"], str(self.validator_id))

    def test_nonexistent_queue_entry(self):
        result = record_validation_result(
            self.conn, 9999, self.validator_id,
            naturalness_score=3, register_correct=True,
            usage_current=True, verdict="approved",
        )
        self.assertEqual(result["action_taken"], "pending")


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.conn = _make_db()

    def test_empty_db_no_findings(self):
        findings = analyze_native_speaker_validation(self.conn)
        self.assertEqual(findings, [])

    def test_large_backlog_triggers_finding(self):
        for i in range(60):
            queue_for_native_speaker_review(
                self.conn,
                content_hanzi=f"item {i}",
                content_type="example_sentence",
                queue_reason="drift_risk_flagged" if i < 10 else "systematic_review",
            )
        findings = analyze_native_speaker_validation(self.conn)
        backlog_findings = [f for f in findings if "backlog" in f["title"].lower()]
        self.assertEqual(len(backlog_findings), 1)
        self.assertIn("60", backlog_findings[0]["title"])

    def test_high_rejection_rate_triggers_finding(self):
        validator_id = _seed_user(self.conn, email="rejection-test@aelu.app")
        for i in range(25):
            qid = queue_for_native_speaker_review(
                self.conn,
                content_hanzi=f"item {i}",
                content_type="example_sentence",
                queue_reason="systematic_review",
            )
            verdict = "reject" if i < 10 else "approved"
            self.conn.execute("""
                UPDATE native_speaker_validation_queue SET
                    validated_at=datetime('now'),
                    validated_by=?,
                    naturalness_score=?,
                    verdict=?
                WHERE id=?
            """, (str(validator_id), 2 if verdict == "reject" else 4, verdict, qid))

        findings = analyze_native_speaker_validation(self.conn)
        rejection_findings = [f for f in findings if "rejection" in f["title"].lower()]
        self.assertEqual(len(rejection_findings), 1)
        self.assertEqual(rejection_findings[0]["severity"], "high")


class TestSchemaVersion(unittest.TestCase):
    def test_schema_version_includes_doc22(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 77)


if __name__ == "__main__":
    unittest.main()
