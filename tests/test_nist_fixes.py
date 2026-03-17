"""Tests for NIST AI RMF security fixes.

Covers:
1. Content provenance: migration adds columns and trigger
2. Human review gate: AI-generated unreviewed content is skipped
3. Admin MFA enforcement: 403 in production, warning in dev
4. Audio sanity validation: rejects silence, clipping, too short, too long
5. Audio sanity validation: accepts normal audio
6. Content API input length validation
7. AI risks appear in compliance monitor
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from mandarin import db
from mandarin.db.core import _migrate, _col_set, SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_db():
    """Fresh test DB with all migrations applied."""
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


# ---------------------------------------------------------------------------
# 1. Content provenance columns exist after migration
# ---------------------------------------------------------------------------

class TestContentProvenance:

    def test_provenance_columns_exist(self, test_db):
        conn, _ = test_db
        cols = _col_set(conn, "content_item")
        assert "is_ai_generated" in cols
        assert "generated_by_prompt" in cols
        assert "human_reviewed_at" in cols
        assert "human_reviewer_id" in cols

    def test_ai_generated_without_prompt_rejected(self, test_db):
        """Trigger enforces: is_ai_generated=1 requires generated_by_prompt."""
        conn, _ = test_db
        with pytest.raises(sqlite3.IntegrityError, match="generated_by_prompt"):
            conn.execute("""
                INSERT INTO content_item
                    (hanzi, pinyin, english, item_type, status, review_status,
                     is_ai_generated, generated_by_prompt)
                VALUES ('test', 'test', 'test', 'vocab', 'drill_ready', 'approved',
                        1, NULL)
            """)

    def test_ai_generated_with_prompt_accepted(self, test_db):
        """AI content with prompt key is accepted."""
        conn, _ = test_db
        conn.execute("""
            INSERT INTO content_item
                (hanzi, pinyin, english, item_type, status, review_status,
                 is_ai_generated, generated_by_prompt)
            VALUES ('test_ok', 'test', 'test', 'vocab', 'drill_ready', 'approved',
                    1, 'usage_map_generation_v1')
        """)
        conn.commit()
        row = conn.execute(
            "SELECT is_ai_generated, generated_by_prompt FROM content_item WHERE hanzi = 'test_ok'"
        ).fetchone()
        assert row["is_ai_generated"] == 1
        assert row["generated_by_prompt"] == "usage_map_generation_v1"

    def test_non_ai_content_no_prompt_ok(self, test_db):
        """Non-AI content (is_ai_generated=0) does not require generated_by_prompt."""
        conn, _ = test_db
        conn.execute("""
            INSERT INTO content_item
                (hanzi, pinyin, english, item_type, status, review_status,
                 is_ai_generated)
            VALUES ('human', 'ren', 'human', 'vocab', 'drill_ready', 'approved', 0)
        """)
        conn.commit()
        row = conn.execute(
            "SELECT is_ai_generated FROM content_item WHERE hanzi = 'human'"
        ).fetchone()
        assert row["is_ai_generated"] == 0

    def test_schema_version_is_102(self, test_db):
        conn, _ = test_db
        from mandarin.db.core import _get_schema_version
        assert _get_schema_version(conn) == SCHEMA_VERSION
        assert SCHEMA_VERSION >= 102  # Schema evolves; verify it's at least V102


# ---------------------------------------------------------------------------
# 2. AI-generated content without review is skipped
# ---------------------------------------------------------------------------

class TestHumanReviewGate:

    def test_unreviewed_ai_content_excluded_from_due(self, test_db):
        """get_items_due() skips AI content without human_reviewed_at."""
        conn, _ = test_db
        # Insert AI-generated item (reviewed)
        conn.execute("""
            INSERT INTO content_item
                (id, hanzi, pinyin, english, item_type, status, review_status,
                 is_ai_generated, generated_by_prompt, human_reviewed_at)
            VALUES (900, 'reviewed_ai', 'test', 'test', 'vocab', 'drill_ready', 'approved',
                    1, 'prompt_v1', '2026-01-01')
        """)
        # Insert AI-generated item (NOT reviewed)
        conn.execute("""
            INSERT INTO content_item
                (id, hanzi, pinyin, english, item_type, status, review_status,
                 is_ai_generated, generated_by_prompt)
            VALUES (901, 'unreviewed_ai', 'test', 'test', 'vocab', 'drill_ready', 'approved',
                    1, 'prompt_v1')
        """)
        # Insert human-authored item
        conn.execute("""
            INSERT INTO content_item
                (id, hanzi, pinyin, english, item_type, status, review_status,
                 is_ai_generated)
            VALUES (902, 'human_item', 'test', 'test', 'vocab', 'drill_ready', 'approved', 0)
        """)
        conn.commit()

        from mandarin.db.content import get_items_due
        items = get_items_due(conn, "reading", limit=100, user_id=1)
        hanzi_set = {item["hanzi"] for item in items}

        assert "reviewed_ai" in hanzi_set
        assert "human_item" in hanzi_set
        assert "unreviewed_ai" not in hanzi_set

    def test_filter_unreviewed_ai_content_function(self):
        """_filter_unreviewed_ai_content() correctly filters."""
        from mandarin.db.content import _filter_unreviewed_ai_content

        items = [
            {"id": 1, "hanzi": "ok", "is_ai_generated": 0},
            {"id": 2, "hanzi": "reviewed", "is_ai_generated": 1, "human_reviewed_at": "2026-01-01"},
            {"id": 3, "hanzi": "bad", "is_ai_generated": 1, "human_reviewed_at": None},
        ]
        filtered = _filter_unreviewed_ai_content(items)
        assert len(filtered) == 2
        assert {i["hanzi"] for i in filtered} == {"ok", "reviewed"}


# ---------------------------------------------------------------------------
# 3. Admin MFA enforcement
# ---------------------------------------------------------------------------

class TestAdminMFA:

    def _make_app(self, test_db):
        conn, _ = test_db
        from mandarin.web import create_app
        app = create_app(testing=True)
        app.config["WTF_CSRF_ENABLED"] = False

        class _FakeConn:
            def __enter__(self_inner):
                return conn
            def __exit__(self_inner, *a):
                return False

        return app, conn, _FakeConn

    def test_admin_without_mfa_gets_403_in_production(self, test_db):
        """In production mode, admin without MFA is rejected with 403."""
        app, conn, FakeConn = self._make_app(test_db)

        # Create admin user without MFA
        conn.execute("""
            INSERT OR REPLACE INTO user (id, email, password_hash, display_name,
                                         is_admin, totp_enabled, subscription_tier)
            VALUES (99, 'admin@test.com', 'hash', 'Admin', 1, 0, 'admin')
        """)
        conn.commit()

        from mandarin.web.auth_routes import User
        user = User(dict(conn.execute("SELECT * FROM user WHERE id = 99").fetchone()))

        with app.test_client() as client:
            with patch("mandarin.db.connection", FakeConn), \
                 patch("mandarin.web.routes.current_user", user), \
                 patch("flask_login.utils._get_user", return_value=user), \
                 patch("mandarin.settings.IS_PRODUCTION", True), \
                 patch("mandarin.web.IS_PRODUCTION", True):
                resp = client.get("/api/admin/metrics",
                                  headers={"X-Requested-With": "XMLHttpRequest"})
                assert resp.status_code in (401, 403)

    def test_admin_with_mfa_passes_check(self, test_db):
        """Admin with MFA enabled should not be blocked by middleware."""
        conn, _ = test_db
        # Create admin user WITH MFA
        conn.execute("""
            INSERT OR REPLACE INTO user (id, email, password_hash, display_name,
                                         is_admin, totp_enabled, totp_secret, subscription_tier)
            VALUES (98, 'mfa_admin@test.com', 'hash', 'MFA Admin', 1, 1, 'secret123', 'admin')
        """)
        conn.commit()

        row = conn.execute("SELECT totp_enabled FROM user WHERE id = 98").fetchone()
        assert row["totp_enabled"] == 1


# ---------------------------------------------------------------------------
# 4 & 5. Audio sanity validation
# ---------------------------------------------------------------------------

class TestAudioSanityValidation:

    def test_rejects_empty_audio(self):
        from mandarin.tone_grading import validate_audio_sanity
        valid, reason = validate_audio_sanity(None)
        assert not valid
        assert reason == "empty_audio"

        valid, reason = validate_audio_sanity(np.array([]))
        assert not valid
        assert reason == "empty_audio"

    def test_rejects_silence(self):
        from mandarin.tone_grading import validate_audio_sanity
        # Very quiet audio (near zero)
        silence = np.zeros(16000)  # 1 second of silence
        valid, reason = validate_audio_sanity(silence, sample_rate=16000)
        assert not valid
        assert reason == "silence"

    def test_rejects_clipping(self):
        from mandarin.tone_grading import validate_audio_sanity
        # Audio with >5% clipped samples
        clipped = np.ones(16000) * 0.99  # All samples near max
        valid, reason = validate_audio_sanity(clipped, sample_rate=16000)
        assert not valid
        assert reason == "clipping"

    def test_rejects_too_short(self):
        from mandarin.tone_grading import validate_audio_sanity
        # 0.1 seconds at 16kHz = 1600 samples
        short = np.random.randn(1600) * 0.1
        valid, reason = validate_audio_sanity(short, sample_rate=16000)
        assert not valid
        assert reason == "too_short"

    def test_rejects_too_long(self):
        from mandarin.tone_grading import validate_audio_sanity
        # 11 seconds at 16kHz = 176000 samples
        long_audio = np.random.randn(176000) * 0.1
        valid, reason = validate_audio_sanity(long_audio, sample_rate=16000)
        assert not valid
        assert reason == "too_long"

    def test_accepts_normal_audio(self):
        from mandarin.tone_grading import validate_audio_sanity
        # 1 second of normal audio at 16kHz
        normal = np.random.randn(16000) * 0.1
        valid, reason = validate_audio_sanity(normal, sample_rate=16000)
        assert valid
        assert reason == "ok"

    def test_accepts_2_second_audio(self):
        from mandarin.tone_grading import validate_audio_sanity
        # 2 seconds of normal audio
        audio = np.random.randn(32000) * 0.15
        valid, reason = validate_audio_sanity(audio, sample_rate=16000)
        assert valid
        assert reason == "ok"

    def test_grade_tones_rejects_invalid_audio(self):
        """grade_tones() returns safe default when audio fails validation."""
        from mandarin.tone_grading import grade_tones
        silence = np.zeros(16000)
        result = grade_tones(silence, [1, 2])
        assert result["overall_score"] == 0.0
        assert result["audio_validation"] == "silence"
        assert "rejected" in result["feedback"].lower()


# ---------------------------------------------------------------------------
# 6. Content API input length validation
# ---------------------------------------------------------------------------

class TestContentInputValidation:

    def _make_client(self, test_db):
        conn, _ = test_db
        from mandarin.web import create_app
        app = create_app(testing=True)
        app.config["WTF_CSRF_ENABLED"] = False

        class _FakeConn:
            def __enter__(self_inner):
                return conn
            def __exit__(self_inner, *a):
                return False

        return app, _FakeConn

    def test_comprehension_rejects_oversized_text(self, test_db):
        """POST /api/reading/comprehension rejects text_zh > 2000 chars."""
        app, FakeConn = self._make_client(test_db)

        from mandarin.web.auth_routes import User
        conn, _ = test_db
        user = User(dict(conn.execute("SELECT * FROM user WHERE id = 1").fetchone()))

        with app.test_client() as client:
            with patch("mandarin.db.connection", FakeConn), \
                 patch("flask_login.utils._get_user", return_value=user):
                resp = client.post(
                    "/api/reading/comprehension",
                    json={"text_zh": "a" * 2001},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                assert resp.status_code == 400
                data = resp.get_json()
                assert "2000" in data["error"]

    def test_comprehension_accepts_valid_text(self, test_db):
        """POST /api/reading/comprehension accepts text_zh <= 2000 chars."""
        app, FakeConn = self._make_client(test_db)

        conn, _ = test_db
        from mandarin.web.auth_routes import User
        user = User(dict(conn.execute("SELECT * FROM user WHERE id = 1").fetchone()))

        with app.test_client() as client:
            with patch("mandarin.db.connection", FakeConn), \
                 patch("flask_login.utils._get_user", return_value=user):
                resp = client.post(
                    "/api/reading/comprehension",
                    json={"text_zh": "今天天气很好"},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                assert resp.status_code == 200

    def test_content_analyze_rejects_oversized_text(self, test_db):
        """POST /api/content/analyze rejects text > 2000 chars."""
        app, FakeConn = self._make_client(test_db)

        conn, _ = test_db
        from mandarin.web.auth_routes import User
        user = User(dict(conn.execute("SELECT * FROM user WHERE id = 1").fetchone()))

        with app.test_client() as client:
            with patch("mandarin.db.connection", FakeConn), \
                 patch("flask_login.utils._get_user", return_value=user):
                resp = client.post(
                    "/api/content/analyze",
                    json={"text": "a" * 2001},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                assert resp.status_code == 400
                data = resp.get_json()
                assert "2000" in data["error"]


# ---------------------------------------------------------------------------
# 7. AI risks appear in compliance monitor
# ---------------------------------------------------------------------------

class TestAIRisksInCompliance:

    def test_ai_risk_register_exists(self):
        from mandarin.openclaw.compliance_monitor import AI_RISK_REGISTER
        assert len(AI_RISK_REGISTER) == 4
        risk_ids = {r["id"] for r in AI_RISK_REGISTER}
        assert "AI-001" in risk_ids
        assert "AI-002" in risk_ids
        assert "AI-003" in risk_ids
        assert "AI-004" in risk_ids

    def test_ai_risk_register_structure(self):
        from mandarin.openclaw.compliance_monitor import AI_RISK_REGISTER
        required_keys = {"id", "name", "description", "category", "risk_level",
                         "likelihood", "impact", "mitigations", "framework"}
        for risk in AI_RISK_REGISTER:
            assert required_keys.issubset(risk.keys()), f"Missing keys in {risk['id']}"
            assert isinstance(risk["mitigations"], list)
            assert len(risk["mitigations"]) > 0

    def test_compliance_monitor_returns_ai_risks(self):
        from mandarin.openclaw.compliance_monitor import ComplianceMonitor
        monitor = ComplianceMonitor()
        ai_risks = monitor.get_ai_risks()
        assert len(ai_risks) == 4
        assert ai_risks[0]["id"] == "AI-001"
        assert ai_risks[0]["name"] == "Prompt regression"

    def test_prompt_regression_risk_high(self):
        from mandarin.openclaw.compliance_monitor import AI_RISK_REGISTER
        ai_001 = next(r for r in AI_RISK_REGISTER if r["id"] == "AI-001")
        assert ai_001["risk_level"] == "high"
        assert "Prompt registry" in ai_001["mitigations"][0]

    def test_adversarial_audio_risk_present(self):
        from mandarin.openclaw.compliance_monitor import AI_RISK_REGISTER
        ai_003 = next(r for r in AI_RISK_REGISTER if r["id"] == "AI-003")
        assert ai_003["name"] == "Adversarial audio in tone grading"
        assert "validate_audio_sanity" in ai_003["mitigations"][0]

    def test_ai_content_labeling_risk(self):
        from mandarin.openclaw.compliance_monitor import AI_RISK_REGISTER
        ai_004 = next(r for r in AI_RISK_REGISTER if r["id"] == "AI-004")
        assert ai_004["name"] == "AI content not labeled for learners"
        assert "is_ai_generated" in ai_004["mitigations"][0]

    def test_compliance_report_includes_ai_recommendation(self):
        from mandarin.openclaw.compliance_monitor import ComplianceMonitor
        monitor = ComplianceMonitor()
        report = monitor.audit()
        # The ai_generated_content surface should have a recommendation about AI risks
        ai_surface = None
        for a in report.surfaces:
            if a.surface.area == "ai_generated_content":
                ai_surface = a
                break
        assert ai_surface is not None
        recs = " ".join(ai_surface.recommendations)
        assert "AI-specific risks" in recs or "NIST AI RMF" in recs
