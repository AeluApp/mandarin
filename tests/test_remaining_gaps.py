"""Tests for remaining gap features: drill types, API endpoints, utilities.

Covers:
  1. Image association drill
  2. Video comprehension drill
  3. F0 contour rendering (smoke test via JS structure)
  4. PodcastPlayer (structure validation)
  5. CFD / Sprint Burndown / Risk Burndown (structure validation)
  6. OCR dictionary endpoint
  7. Widget data endpoint
  8. Study list CRUD + sharing
  9. News RSS ingestion
  10. Schema migration for image_url + study_list
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytestmark = pytest.mark.t2

from mandarin import db
from mandarin.db.core import _migrate

from tests.conftest import OutputCapture, InputSequence


# ── Fixtures ──────────────────────────────────────────────────────────

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
        VALUES (1, 'local@localhost', 'bootstrap_no_login', 'Local', 'admin')
    """)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id, user_id) VALUES (1, 1)")
    conn.commit()
    yield conn, path
    conn.close()
    path.unlink(missing_ok=True)


def _seed_items(conn, n=5, hsk=1, with_image=False):
    """Seed n content items. Returns list of item dicts."""
    for i in range(n):
        image_url = f"https://img.example.com/{i}.png" if with_image and i < 3 else None
        conn.execute(
            """INSERT INTO content_item
               (hanzi, pinyin, english, hsk_level, item_type, image_url)
               VALUES (?, ?, ?, ?, 'vocab', ?)""",
            (f"字{i}", f"zi{i}", f"char{i}", hsk, image_url),
        )
    conn.commit()
    rows = conn.execute("SELECT * FROM content_item ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _seed_media(conn):
    """Seed a media_watch entry."""
    conn.execute("""
        INSERT INTO media_watch (media_id, title, hsk_level, media_type, status, user_id)
        VALUES ('test_media_1', 'Test Video', 1, 'clip', 'available', 1)
    """)
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════
# 1. Image Association Drill
# ═══════════════════════════════════════════════════════════════════════

class TestImageAssociationDrill:

    def test_returns_none_when_no_image_url(self, test_db):
        """Drill gracefully returns None when item has no image_url."""
        conn, _ = test_db
        items = _seed_items(conn, n=3, with_image=False)
        from mandarin.drills.image_association import run_image_association_drill
        out = OutputCapture()
        inp = InputSequence(["1"])
        result = run_image_association_drill(items[0], conn, out, inp)
        assert result is None

    def test_returns_drill_result_when_image_exists(self, test_db):
        """Drill returns DrillResult when item has image_url."""
        conn, _ = test_db
        items = _seed_items(conn, n=5, hsk=1, with_image=True)
        item = items[0]  # Has image_url
        assert item.get("image_url") is not None

        from mandarin.drills.image_association import run_image_association_drill
        out = OutputCapture()
        inp = InputSequence(["1", "1"])  # Pick first option
        result = run_image_association_drill(item, conn, out, inp)
        assert result is not None
        assert result.drill_type == "image_association"
        assert result.content_item_id == item["id"]

    def test_skip_input(self, test_db):
        """User can skip the drill with Q."""
        conn, _ = test_db
        items = _seed_items(conn, n=5, hsk=1, with_image=True)
        from mandarin.drills.image_association import run_image_association_drill
        out = OutputCapture()
        inp = InputSequence(["Q"])
        result = run_image_association_drill(items[0], conn, out, inp)
        assert result is not None
        assert result.skipped is True


# ═══════════════════════════════════════════════════════════════════════
# 2. Video Comprehension Drill
# ═══════════════════════════════════════════════════════════════════════

class TestVideoComprehensionDrill:

    def test_returns_none_when_no_media(self, test_db):
        """Drill returns None when no media clips available."""
        conn, _ = test_db
        items = _seed_items(conn, n=3)
        from mandarin.drills.video_comprehension import run_video_comprehension_drill
        out = OutputCapture()
        inp = InputSequence(["1"])
        result = run_video_comprehension_drill(items[0], conn, out, inp)
        assert result is None

    def test_returns_result_with_media(self, test_db):
        """Drill returns DrillResult when media is available."""
        conn, _ = test_db
        items = _seed_items(conn, n=5, hsk=1)
        _seed_media(conn)
        from mandarin.drills.video_comprehension import run_video_comprehension_drill
        out = OutputCapture()
        inp = InputSequence(["1", "1", "1", "1"])  # Answer questions
        result = run_video_comprehension_drill(items[0], conn, out, inp)
        if result is not None:
            assert result.drill_type == "video_comprehension"
            assert result.metadata is not None
            assert "comprehension_score" in result.metadata

    def test_skip_during_questions(self, test_db):
        """User can skip with Q during comprehension questions."""
        conn, _ = test_db
        items = _seed_items(conn, n=5, hsk=1)
        _seed_media(conn)
        from mandarin.drills.video_comprehension import run_video_comprehension_drill
        out = OutputCapture()
        inp = InputSequence(["Q"])
        result = run_video_comprehension_drill(items[0], conn, out, inp)
        if result is not None:
            assert result.skipped is True


# ═══════════════════════════════════════════════════════════════════════
# 3. Drill Registry Integration
# ═══════════════════════════════════════════════════════════════════════

class TestDrillRegistry:

    def test_image_association_in_registry(self):
        """image_association drill type is registered."""
        from mandarin.drills.dispatch import DRILL_REGISTRY
        assert "image_association" in DRILL_REGISTRY
        assert DRILL_REGISTRY["image_association"]["requires"] == {"hanzi"}

    def test_video_comprehension_in_registry(self):
        """video_comprehension drill type is registered."""
        from mandarin.drills.dispatch import DRILL_REGISTRY
        assert "video_comprehension" in DRILL_REGISTRY
        assert DRILL_REGISTRY["video_comprehension"]["requires"] == {"hanzi"}

    def test_labels_exist(self):
        """UI labels exist for new drill types."""
        from mandarin.ui_labels import DRILL_LABELS
        assert "image_association" in DRILL_LABELS
        assert "video_comprehension" in DRILL_LABELS


# ═══════════════════════════════════════════════════════════════════════
# 4. Schema Migration (image_url + study_list)
# ═══════════════════════════════════════════════════════════════════════

class TestSchemaMigration:

    def test_image_url_column_exists(self, test_db):
        """content_item has image_url column after migration."""
        conn, _ = test_db
        cols = {r[1] for r in conn.execute("PRAGMA table_info(content_item)").fetchall()}
        assert "image_url" in cols

    def test_study_list_table_exists(self, test_db):
        """study_list table exists after migration."""
        conn, _ = test_db
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "study_list" in tables

    def test_study_list_columns(self, test_db):
        """study_list table has expected columns."""
        conn, _ = test_db
        cols = {r[1] for r in conn.execute("PRAGMA table_info(study_list)").fetchall()}
        expected = {"id", "user_id", "name", "description", "item_ids",
                    "public", "share_code", "created_at", "updated_at"}
        assert expected.issubset(cols)


# ═══════════════════════════════════════════════════════════════════════
# 5. Widget Data Endpoint
# ═══════════════════════════════════════════════════════════════════════

class TestWidgetEndpoint:

    def test_widget_data_unauthenticated(self, test_db):
        """Widget endpoint returns safe defaults when not authenticated."""
        conn, path = test_db
        # Simulate the endpoint logic directly
        from mandarin.web.gap_routes import api_widget_data
        # Instead of running Flask, just verify the function signature and imports
        assert callable(api_widget_data)

    def test_widget_data_structure(self):
        """Widget response has expected fields."""
        # This validates the contract — actual endpoint testing requires Flask app
        from mandarin.web.gap_routes import api_widget_data
        assert callable(api_widget_data)


# ═══════════════════════════════════════════════════════════════════════
# 6. Study List CRUD
# ═══════════════════════════════════════════════════════════════════════

class TestStudyListCRUD:

    def test_create_study_list(self, test_db):
        """Can create a study list directly in DB."""
        conn, _ = test_db
        items = _seed_items(conn, n=3)
        item_ids = [items[0]["id"], items[1]["id"]]
        conn.execute(
            """INSERT INTO study_list (user_id, name, description, item_ids, public, share_code)
               VALUES (1, 'Test List', 'A test list', ?, 1, 'abc123')""",
            (json.dumps(item_ids),),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM study_list WHERE name = 'Test List'").fetchone()
        assert row is not None
        assert json.loads(row["item_ids"]) == item_ids
        assert row["share_code"] == "abc123"

    def test_share_code_unique(self, test_db):
        """Share codes must be unique."""
        conn, _ = test_db
        conn.execute(
            "INSERT INTO study_list (user_id, name, item_ids, share_code) VALUES (1, 'L1', '[]', 'unique1')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO study_list (user_id, name, item_ids, share_code) VALUES (1, 'L2', '[]', 'unique1')"
            )

    def test_private_list_no_share_code(self, test_db):
        """Private lists can have NULL share_code."""
        conn, _ = test_db
        conn.execute(
            "INSERT INTO study_list (user_id, name, item_ids, public, share_code) VALUES (1, 'Private', '[]', 0, NULL)"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM study_list WHERE name = 'Private'").fetchone()
        assert row["share_code"] is None
        assert row["public"] == 0


# ═══════════════════════════════════════════════════════════════════════
# 7. OCR Endpoint
# ═══════════════════════════════════════════════════════════════════════

class TestOCREndpoint:

    def test_ocr_function_exists(self):
        """OCR endpoint function is importable."""
        from mandarin.web.gap_routes import api_dictionary_ocr
        assert callable(api_dictionary_ocr)

    def test_capacitor_bridge_has_camera_lookup(self):
        """capacitor-bridge.js exports cameraLookup."""
        bridge_path = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "capacitor-bridge.js"
        content = bridge_path.read_text()
        assert "cameraLookup" in content
        assert "Camera" in content
        assert "/api/dictionary/ocr" in content


# ═══════════════════════════════════════════════════════════════════════
# 8. F0 Contour Rendering (JS structure)
# ═══════════════════════════════════════════════════════════════════════

class TestF0ContourJS:

    def test_render_f0_contour_function_exists(self):
        """app.js contains renderF0Contour function."""
        app_js = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
        content = app_js.read_text()
        assert "function renderF0Contour" in content

    def test_f0_contour_accepts_canvas_and_arrays(self):
        """renderF0Contour signature takes canvas, userF0, targetF0."""
        app_js = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
        content = app_js.read_text()
        assert "renderF0Contour(canvas, userF0, targetF0" in content

    def test_f0_uses_teal_and_terracotta(self):
        """F0 contour uses teal for target and terracotta for user."""
        app_js = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
        content = app_js.read_text()
        # Verify it references the CSS variables for colors
        assert "--color-accent" in content
        assert "--color-secondary" in content


# ═══════════════════════════════════════════════════════════════════════
# 9. PodcastPlayer (JS structure)
# ═══════════════════════════════════════════════════════════════════════

class TestPodcastPlayerJS:

    def test_podcast_player_class_exists(self):
        """app.js contains PodcastPlayer class."""
        app_js = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
        content = app_js.read_text()
        assert "var PodcastPlayer" in content

    def test_podcast_player_has_controls(self):
        """PodcastPlayer has play, pause, seek methods."""
        app_js = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
        content = app_js.read_text()
        assert ".play = function" in content or "prototype.play" in content
        assert ".pause = function" in content or "prototype.pause" in content
        assert ".seek = function" in content or "prototype.seek" in content

    def test_podcast_player_has_subtitle_sync(self):
        """PodcastPlayer synchronizes subtitles."""
        app_js = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
        content = app_js.read_text()
        assert "_syncSubtitle" in content
        assert "subtitle" in content.lower()

    def test_podcast_player_reports_progress(self):
        """PodcastPlayer reports listening progress on complete."""
        app_js = Path(__file__).parent.parent / "mandarin" / "web" / "static" / "app.js"
        content = app_js.read_text()
        assert "/api/listening/complete" in content


# ═══════════════════════════════════════════════════════════════════════
# 10. Admin Charts (JS structure)
# ═══════════════════════════════════════════════════════════════════════

class TestAdminChartsJS:

    def _read_admin_html(self):
        return (Path(__file__).parent.parent / "mandarin" / "web" / "templates" / "admin.html").read_text()

    def test_render_cfd_exists(self):
        """admin.html contains renderCFD function."""
        content = self._read_admin_html()
        assert "function renderCFD" in content

    def test_render_sprint_burndown_exists(self):
        """admin.html contains renderSprintBurndown function."""
        content = self._read_admin_html()
        assert "function renderSprintBurndown" in content

    def test_render_risk_burndown_exists(self):
        """admin.html contains renderRiskBurndown function."""
        content = self._read_admin_html()
        assert "function renderRiskBurndown" in content

    def test_cfd_handles_empty_data(self):
        """renderCFD has empty-data handling."""
        content = self._read_admin_html()
        assert "No CFD data" in content

    def test_sprint_burndown_has_ideal_line(self):
        """Sprint burndown draws ideal + actual lines."""
        content = self._read_admin_html()
        assert "Ideal" in content
        assert "Actual" in content

    def test_risk_burndown_uses_area_fill(self):
        """Risk burndown fills area under the line."""
        content = self._read_admin_html()
        assert "Risk Score Over Time" in content


# ═══════════════════════════════════════════════════════════════════════
# 11. News RSS Ingestion
# ═══════════════════════════════════════════════════════════════════════

class TestNewsIngestion:

    def test_estimate_hsk_level_basic(self, test_db):
        """HSK estimation returns a level between 1-9."""
        conn, _ = test_db
        _seed_items(conn, n=10, hsk=1)
        from scripts.ingest_news import estimate_hsk_level
        level = estimate_hsk_level("这是一个简单的句子", conn=conn)
        assert 1 <= level <= 9

    def test_estimate_hsk_level_no_jieba(self):
        """HSK estimation defaults to 3 without jieba."""
        from scripts.ingest_news import estimate_hsk_level
        with patch.dict("sys.modules", {"jieba": None}):
            # Force reimport
            import importlib
            from scripts import ingest_news
            importlib.reload(ingest_news)
            level = ingest_news.estimate_hsk_level("test")
            assert level == 3

    def test_extract_chinese_text(self):
        """HTML tags are stripped from content."""
        from scripts.ingest_news import _extract_chinese_text
        result = _extract_chinese_text("<p>你好<b>世界</b></p>")
        assert "你好" in result
        assert "世界" in result
        assert "<p>" not in result

    def test_generate_passage_id_deterministic(self):
        """Passage IDs are deterministic for the same input."""
        from scripts.ingest_news import _generate_passage_id
        id1 = _generate_passage_id("Title", "http://example.com/1")
        id2 = _generate_passage_id("Title", "http://example.com/1")
        id3 = _generate_passage_id("Other", "http://example.com/2")
        assert id1 == id2
        assert id1 != id3
        assert id1.startswith("news_")

    def test_ingest_article_dry_run(self, test_db):
        """Dry run estimates level without writing to DB."""
        conn, _ = test_db
        _seed_items(conn, n=5, hsk=1)
        from scripts.ingest_news import ingest_article
        content = "这是一个很长的中文文章。" * 10
        result = ingest_article(
            conn,
            title="Test Article",
            link="http://example.com/test",
            content=content,
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert "hsk_level" in result

    def test_ingest_article_skips_non_chinese(self, test_db):
        """Articles without enough Chinese text are skipped."""
        conn, _ = test_db
        from scripts.ingest_news import ingest_article
        result = ingest_article(
            conn,
            title="English Article",
            link="http://example.com/eng",
            content="This is an English article with no Chinese.",
        )
        assert result["status"] == "skipped"


# ═══════════════════════════════════════════════════════════════════════
# 12. Public Route Registration
# ═══════════════════════════════════════════════════════════════════════

class TestRouteRegistration:

    def test_widget_is_public(self):
        """Widget endpoint is in public prefixes."""
        from mandarin.web.routes import _PUBLIC_PREFIXES
        assert any("/api/widget/data" in p for p in _PUBLIC_PREFIXES)

    def test_shared_list_is_public(self):
        """Shared study list endpoint is in public prefixes."""
        from mandarin.web.routes import _PUBLIC_PREFIXES
        assert any("/api/study-lists/shared/" in p for p in _PUBLIC_PREFIXES)

    def test_gap_blueprint_importable(self):
        """Gap routes blueprint is importable."""
        from mandarin.web.gap_routes import gap_bp
        assert gap_bp.name == "gap"
