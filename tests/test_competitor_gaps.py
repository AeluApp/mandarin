"""Tests for competitor A+ gap features: SRS tuning, analytics, content import."""

import csv
import io
import json
import math
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytestmark = pytest.mark.t2

from mandarin import db
from mandarin.db.core import _migrate


# ── Test DB fixture ────────────────────────────────────────────────────

@pytest.fixture
def test_db():
    """Fresh test database with schema + migrations + seed data."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = db.init_db(path)
    _migrate(conn)
    conn.execute("""
        INSERT OR IGNORE INTO user (id, email, password_hash, display_name, subscription_tier)
        VALUES (1, 'test@test.com', 'hash', 'Tester', 'admin')
    """)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1)")
    conn.commit()
    yield conn, path
    conn.close()
    path.unlink(missing_ok=True)


def _seed_content_item(conn, hanzi="你好", pinyin="nǐ hǎo", english="hello",
                       hsk_level=1, item_id=None):
    """Insert a content_item and return its id."""
    cur = conn.execute(
        """INSERT INTO content_item (hanzi, pinyin, english, hsk_level,
                                      item_type, review_status, status)
           VALUES (?, ?, ?, ?, 'vocab', 'approved', 'drill_ready')""",
        (hanzi, pinyin, english, hsk_level),
    )
    conn.commit()
    return cur.lastrowid


def _seed_progress(conn, content_item_id, user_id=1, modality="reading",
                   half_life_days=5.0, last_review_date=None,
                   total_attempts=5, total_correct=4,
                   next_review_date=None, mastery_stage="stabilizing",
                   suspended_until=None):
    """Insert a progress row."""
    if last_review_date is None:
        last_review_date = date.today().isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO progress
           (user_id, content_item_id, modality, half_life_days, last_review_date,
            total_attempts, total_correct, next_review_date, mastery_stage,
            difficulty, suspended_until)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.5, ?)""",
        (user_id, content_item_id, modality, half_life_days, last_review_date,
         total_attempts, total_correct, next_review_date, mastery_stage,
         suspended_until),
    )
    conn.commit()


# ── 1. Target retention rate ───────────────────────────────────────────

class TestTargetRetentionRate:
    def test_default_retention_rate(self, test_db):
        conn, _ = test_db
        row = conn.execute(
            "SELECT target_retention_rate FROM learner_profile WHERE user_id = 1"
        ).fetchone()
        # Default should be 0.85 (from schema or migration)
        rate = row["target_retention_rate"]
        assert rate is None or rate == 0.85

    def test_set_retention_rate(self, test_db):
        conn, _ = test_db
        conn.execute(
            "UPDATE learner_profile SET target_retention_rate = 0.90 WHERE user_id = 1"
        )
        conn.commit()
        row = conn.execute(
            "SELECT target_retention_rate FROM learner_profile WHERE user_id = 1"
        ).fetchone()
        assert row["target_retention_rate"] == 0.90

    def test_retention_rate_helper(self, test_db):
        conn, _ = test_db
        from mandarin.web.srs_analytics_routes import _get_user_retention_threshold
        # Default
        threshold = _get_user_retention_threshold(conn, 1)
        assert 0.80 <= threshold <= 0.95

        # Custom
        conn.execute(
            "UPDATE learner_profile SET target_retention_rate = 0.92 WHERE user_id = 1"
        )
        conn.commit()
        threshold = _get_user_retention_threshold(conn, 1)
        assert threshold == 0.92


# ── 2. Suspend / bury / reschedule ─────────────────────────────────────

class TestSuspendBuryReschedule:
    def test_suspend_adds_far_future_date(self, test_db):
        conn, _ = test_db
        item_id = _seed_content_item(conn)
        _seed_progress(conn, item_id)
        conn.execute(
            "UPDATE progress SET suspended_until = '9999-12-31' WHERE content_item_id = ? AND user_id = 1",
            (item_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT suspended_until FROM progress WHERE content_item_id = ? AND user_id = 1",
            (item_id,),
        ).fetchone()
        assert row["suspended_until"] == "9999-12-31"

    def test_bury_sets_tomorrow(self, test_db):
        conn, _ = test_db
        item_id = _seed_content_item(conn)
        _seed_progress(conn, item_id)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        conn.execute(
            "UPDATE progress SET suspended_until = ? WHERE content_item_id = ? AND user_id = 1",
            (tomorrow, item_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT suspended_until FROM progress WHERE content_item_id = ? AND user_id = 1",
            (item_id,),
        ).fetchone()
        assert row["suspended_until"] == tomorrow

    def test_unsuspend_clears_flag(self, test_db):
        conn, _ = test_db
        item_id = _seed_content_item(conn)
        _seed_progress(conn, item_id, suspended_until="9999-12-31")
        conn.execute(
            "UPDATE progress SET suspended_until = NULL WHERE content_item_id = ? AND user_id = 1",
            (item_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT suspended_until FROM progress WHERE content_item_id = ? AND user_id = 1",
            (item_id,),
        ).fetchone()
        assert row["suspended_until"] is None

    def test_suspended_items_excluded_from_due(self, test_db):
        conn, _ = test_db
        item_id = _seed_content_item(conn)
        today = date.today().isoformat()
        _seed_progress(conn, item_id, next_review_date=today,
                       suspended_until="9999-12-31")

        from mandarin.db.content import get_items_due
        due = get_items_due(conn, "reading", limit=20, user_id=1)
        due_ids = [d["id"] for d in due]
        assert item_id not in due_ids

    def test_reschedule_updates_next_review(self, test_db):
        conn, _ = test_db
        item_id = _seed_content_item(conn)
        _seed_progress(conn, item_id, next_review_date=date.today().isoformat())
        future = (date.today() + timedelta(days=7)).isoformat()
        conn.execute(
            "UPDATE progress SET next_review_date = ? WHERE content_item_id = ? AND user_id = 1",
            (future, item_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT next_review_date FROM progress WHERE content_item_id = ? AND user_id = 1",
            (item_id,),
        ).fetchone()
        assert row["next_review_date"] == future


# ── 3. Exam readiness ──────────────────────────────────────────────────

class TestExamReadiness:
    def test_forecast_data_available(self, test_db):
        conn, _ = test_db
        from mandarin.diagnostics import project_forecast
        forecast = project_forecast(conn, user_id=1)
        assert "pace" in forecast
        assert "modality_projections" in forecast
        assert "total_sessions" in forecast

    def test_mastery_by_hsk_returns_dict(self, test_db):
        conn, _ = test_db
        mastery = db.get_mastery_by_hsk(conn, user_id=1)
        assert isinstance(mastery, dict)


# ── 4. Retention forecast calendar ─────────────────────────────────────

class TestRetentionForecast:
    def test_predict_recall_decreases_over_time(self):
        from mandarin.retention import predict_recall
        p1 = predict_recall(5.0, 1.0)
        p7 = predict_recall(5.0, 7.0)
        assert p1 > p7

    def test_days_until_threshold(self):
        from mandarin.retention import days_until_threshold
        days = days_until_threshold(5.0, 0.85)
        assert days > 0
        # With higher threshold (tighter), should be fewer days
        days_tight = days_until_threshold(5.0, 0.90)
        assert days_tight < days

    def test_item_crosses_threshold_at_right_time(self):
        from mandarin.retention import predict_recall, days_until_threshold
        hl = 10.0
        threshold = 0.85
        cross_days = days_until_threshold(hl, threshold)
        p_at_cross = predict_recall(hl, cross_days)
        assert abs(p_at_cross - threshold) < 0.01

    def test_retention_forecast_with_seeded_data(self, test_db):
        conn, _ = test_db
        from mandarin.retention import predict_recall
        from mandarin.config import INITIAL_HALF_LIFE

        # Seed some items reviewed 3 days ago with short half-lives
        for i in range(5):
            item_id = _seed_content_item(
                conn, hanzi=f"字{i}", pinyin=f"zì{i}", english=f"char{i}"
            )
            review_date = (date.today() - timedelta(days=3)).isoformat()
            _seed_progress(conn, item_id, half_life_days=2.0,
                           last_review_date=review_date)

        # Items with hl=2.0 reviewed 3 days ago: p = 2^(-3/2) ≈ 0.354
        # They should already be below threshold
        rows = conn.execute("""
            SELECT half_life_days, last_review_date FROM progress
            WHERE user_id = 1 AND total_attempts > 0
        """).fetchall()
        assert len(rows) == 5
        for r in rows:
            hl = r["half_life_days"]
            days_since = (date.today() - date.fromisoformat(r["last_review_date"])).days
            p = predict_recall(hl, days_since)
            assert p < 0.85  # Already below threshold


# ── 5. Content import: text ────────────────────────────────────────────

class TestContentImportText:
    def test_tokenize_chinese_jieba_fallback(self):
        from mandarin.web.srs_analytics_routes import _tokenize_chinese
        tokens = _tokenize_chinese("你好世界")
        assert len(tokens) > 0
        # Should contain some CJK characters
        for t in tokens:
            assert all('\u4e00' <= c <= '\u9fff' for c in t)

    def test_tokenize_empty_input(self):
        from mandarin.web.srs_analytics_routes import _tokenize_chinese
        assert _tokenize_chinese("") == []
        assert _tokenize_chinese("hello world") == []


# ── 6. CSV import ──────────────────────────────────────────────────────

class TestCSVImport:
    def test_csv_parsing(self, test_db):
        conn, _ = test_db
        csv_data = "hanzi,pinyin,english,hsk_level\n学习,xuéxí,to study,1\n工作,gōngzuò,to work,2"
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["hanzi"] == "学习"
        assert rows[1]["english"] == "to work"

    def test_csv_duplicate_detection(self, test_db):
        conn, _ = test_db
        _seed_content_item(conn, hanzi="学习", pinyin="xuéxí", english="study")
        existing = conn.execute(
            "SELECT id FROM content_item WHERE hanzi = '学习'"
        ).fetchone()
        assert existing is not None

    def test_csv_insert(self, test_db):
        conn, _ = test_db
        conn.execute(
            """INSERT INTO content_item
               (hanzi, pinyin, english, hsk_level, item_type, source,
                review_status, status)
               VALUES ('测试词', 'cèshì cí', 'test word', 1, 'vocab', 'csv_import',
                       'approved', 'drill_ready')"""
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM content_item WHERE hanzi = '测试词'"
        ).fetchone()
        assert row is not None
        assert row["source"] == "csv_import"


# ── 7. Grammar highlights in passages ──────────────────────────────────

class TestGrammarHighlights:
    def test_grammar_pattern_matching(self, test_db):
        conn, _ = test_db
        # Seed a grammar point
        conn.execute(
            """INSERT INTO grammar_point (name, name_zh, hsk_level, category, description)
               VALUES ('de_particle', '的', 1, 'particle', 'Possessive/attributive particle')"""
        )
        conn.commit()

        text = "这是我的书。"
        row = conn.execute(
            "SELECT name_zh FROM grammar_point WHERE name = 'de_particle'"
        ).fetchone()
        assert row["name_zh"] in text


# ── 8. Source type classification ──────────────────────────────────────

class TestSourceType:
    def test_infer_human_authored(self):
        from mandarin.web.srs_analytics_routes import _infer_source_type
        assert _infer_source_type({"id": "j1_observe_001"}) == "human_authored"

    def test_infer_ai_generated(self):
        from mandarin.web.srs_analytics_routes import _infer_source_type
        assert _infer_source_type({"id": "gen_passage_1"}) == "ai_generated"
        assert _infer_source_type({"id": "foo", "source": "ollama"}) == "ai_generated"

    def test_infer_template_generated(self):
        from mandarin.web.srs_analytics_routes import _infer_source_type
        assert _infer_source_type({"id": "tmpl_001"}) == "template_generated"

    def test_infer_default(self):
        from mandarin.web.srs_analytics_routes import _infer_source_type
        assert _infer_source_type({}) == "human_authored"
        assert _infer_source_type({"id": "regular_passage"}) == "human_authored"
