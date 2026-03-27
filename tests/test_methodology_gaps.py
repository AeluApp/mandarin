"""Tests for methodology A+ gap items.

Covers:
1. Kanban: WIP limit enforcement with rejection and force override
2. Kanban: Aging alerts with escalation tiers
3. Kanban: Pull system suggestion after done
4. Kanban: Blocked work visibility
5. Lean Six Sigma: Pp/Ppk process performance indices
6. Lean Six Sigma: Pareto analysis of defect types
7. Spiral: Link SPC violations to risk register
8. Spiral: Prototype tracking on work items
9. Agile: Story points (estimate) on work items
10. Spiral: Risk taxonomy checklist
"""

import json
import math
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta, UTC
from unittest.mock import patch, MagicMock

import pytest

pytestmark = pytest.mark.t2

from mandarin.web.auth_routes import User


# ---------------------------------------------------------------------------
# Helpers (duplicated from test_admin_routes for isolation)
# ---------------------------------------------------------------------------

def _make_fake_connection(conn):
    class _FakeConnection:
        def __enter__(self):
            return conn
        def __exit__(self, *args):
            return False
    return _FakeConnection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(test_db):
    """Flask test client logged in as admin with TOTP enabled."""
    conn, _ = test_db

    conn.execute(
        "UPDATE user SET is_admin = 1, totp_enabled = 1, is_active = 1 WHERE id = 1"
    )
    conn.commit()

    from mandarin.web import create_app

    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False

    FakeConn = _make_fake_connection(conn)

    with patch("mandarin.db.connection", FakeConn), \
         patch("mandarin.web.auth_routes.db.connection", FakeConn), \
         patch("mandarin.web.admin_routes.db.connection", FakeConn):
        with app.test_client() as c:
            with app.test_request_context():
                from flask_login import login_user
                login_user(User({
                    "id": 1, "email": "local@localhost", "display_name": "Local",
                    "subscription_tier": "admin", "is_admin": True,
                }))
            with c.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            yield c, conn


def _create_work_item(conn, title="Test item", status="backlog", service_class="standard",
                      estimate=None, implementation_type=None, started_at=None):
    """Insert a work item directly for test setup."""
    conn.execute(
        """INSERT INTO work_item
           (title, description, item_type, status, service_class, estimate,
            implementation_type, started_at)
           VALUES (?, '', 'standard', ?, ?, ?, ?, ?)""",
        (title, status, service_class, estimate, implementation_type, started_at),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ===========================================================================
# 1. Kanban: WIP limit enforcement
# ===========================================================================

class TestWIPLimitEnforcement:

    def test_wip_limit_rejects_transition(self, admin_client):
        """Moving to in_progress should be rejected when WIP limit reached."""
        c, conn = admin_client
        # Fill WIP to limit (5 items in_progress)
        for i in range(5):
            _create_work_item(conn, title=f"WIP item {i}", status="in_progress")

        # Create item to move
        item_id = _create_work_item(conn, title="New item", status="ready")

        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"status": "in_progress"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 409
        data = json.loads(resp.data)
        assert "WIP limit reached" in data["error"]
        assert data["wip_count"] == 5
        assert data["wip_limit"] == 5

    def test_wip_limit_force_override(self, admin_client):
        """Force override should allow transition past WIP limit."""
        c, conn = admin_client
        for i in range(5):
            _create_work_item(conn, title=f"WIP item {i}", status="in_progress")

        item_id = _create_work_item(conn, title="Urgent item", status="ready")

        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"status": "in_progress", "force": True,
                           "force_reason": "Critical production issue"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "updated"
        assert "wip_warning" in data
        assert "overridden" in data["wip_warning"]

    def test_wip_limit_allows_below_limit(self, admin_client):
        """Transition should succeed when WIP count is below limit."""
        c, conn = admin_client
        for i in range(3):
            _create_work_item(conn, title=f"WIP item {i}", status="in_progress")

        item_id = _create_work_item(conn, title="New item", status="ready")

        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"status": "in_progress"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200


# ===========================================================================
# 2. Kanban: Aging alerts with escalation tiers
# ===========================================================================

class TestAgingAlerts:
    """Test aging alert tier logic directly (notifications route is nested in code).

    The aging tier logic is:
    - Expedite: >2d = warning, >5d = critical
    - Standard/other: >14d = warning, >21d = critical
    """

    @staticmethod
    def _compute_aging_alerts(conn):
        """Replicate the aging notification logic from admin_routes for testing."""
        alerts = []
        rows = conn.execute("""
            SELECT id, title,
                   CAST(julianday('now') - julianday(started_at) AS INTEGER) AS age_days,
                   COALESCE(service_class, 'standard') AS service_class
            FROM work_item
            WHERE status IN ('in_progress', 'blocked')
              AND started_at IS NOT NULL
        """).fetchall()
        for r in rows:
            age = r["age_days"]
            sc = r["service_class"]
            severity = None
            if sc == "expedite":
                if age > 5:
                    severity = "critical"
                elif age > 2:
                    severity = "warning"
            else:
                if age > 21:
                    severity = "critical"
                elif age > 14:
                    severity = "warning"
            if severity:
                alerts.append({
                    "id": r["id"],
                    "title": r["title"],
                    "age_days": age,
                    "service_class": sc,
                    "severity": severity,
                })
        return alerts

    def test_expedite_aging_warning(self, test_db):
        """Expedite items >2d should trigger warning."""
        conn, _ = test_db
        three_days_ago = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        _create_work_item(conn, title="Expedite aging",
                          status="in_progress", service_class="expedite",
                          started_at=three_days_ago)

        alerts = self._compute_aging_alerts(conn)
        found = [a for a in alerts if a["title"] == "Expedite aging"]
        assert len(found) == 1
        assert found[0]["severity"] == "warning"

    def test_expedite_aging_critical(self, test_db):
        """Expedite items >5d should trigger critical."""
        conn, _ = test_db
        six_days_ago = (datetime.now(UTC) - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S")
        _create_work_item(conn, title="Expedite critical",
                          status="in_progress", service_class="expedite",
                          started_at=six_days_ago)

        alerts = self._compute_aging_alerts(conn)
        found = [a for a in alerts if a["title"] == "Expedite critical"]
        assert len(found) == 1
        assert found[0]["severity"] == "critical"

    def test_standard_aging_warning(self, test_db):
        """Standard items >14d should trigger warning."""
        conn, _ = test_db
        fifteen_days_ago = (datetime.now(UTC) - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
        _create_work_item(conn, title="Standard aging",
                          status="in_progress", service_class="standard",
                          started_at=fifteen_days_ago)

        alerts = self._compute_aging_alerts(conn)
        found = [a for a in alerts if a["title"] == "Standard aging"]
        assert len(found) == 1
        assert found[0]["severity"] == "warning"

    def test_standard_aging_critical(self, test_db):
        """Standard items >21d should trigger critical."""
        conn, _ = test_db
        twenty_two_days_ago = (datetime.now(UTC) - timedelta(days=22)).strftime("%Y-%m-%d %H:%M:%S")
        _create_work_item(conn, title="Standard critical",
                          status="in_progress", service_class="standard",
                          started_at=twenty_two_days_ago)

        alerts = self._compute_aging_alerts(conn)
        found = [a for a in alerts if a["title"] == "Standard critical"]
        assert len(found) == 1
        assert found[0]["severity"] == "critical"

    def test_no_alert_for_young_items(self, test_db):
        """Items within thresholds should not trigger alerts."""
        conn, _ = test_db
        one_day_ago = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        _create_work_item(conn, title="Young item",
                          status="in_progress", service_class="standard",
                          started_at=one_day_ago)

        alerts = self._compute_aging_alerts(conn)
        found = [a for a in alerts if a["title"] == "Young item"]
        assert len(found) == 0

    def test_blocked_items_included(self, test_db):
        """Blocked items should also trigger aging alerts."""
        conn, _ = test_db
        twenty_days_ago = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
        _create_work_item(conn, title="Blocked aging",
                                    status="blocked", service_class="standard",
                                    started_at=twenty_days_ago)

        alerts = self._compute_aging_alerts(conn)
        found = [a for a in alerts if a["title"] == "Blocked aging"]
        assert len(found) == 1
        assert found[0]["severity"] == "warning"


# ===========================================================================
# 3. Kanban: Pull system suggestion
# ===========================================================================

class TestPullSuggestion:

    def test_pull_suggestion_on_done(self, admin_client):
        """Marking an item done should return a pull suggestion from ready items."""
        c, conn = admin_client
        # Create ready items with different service classes
        _create_work_item(conn, title="Standard ready", status="ready", service_class="standard")
        _create_work_item(conn, title="Expedite ready", status="ready", service_class="expedite")
        item_id = _create_work_item(conn, title="In progress", status="in_progress")

        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"status": "done"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "pull_suggestion" in data
        # Expedite should be suggested first
        assert data["pull_suggestion"]["service_class"] == "expedite"
        assert data["pull_suggestion"]["title"] == "Expedite ready"

    def test_no_pull_suggestion_when_empty(self, admin_client):
        """No suggestion when no items in ready status."""
        c, conn = admin_client
        item_id = _create_work_item(conn, title="In progress", status="in_progress")

        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"status": "done"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("pull_suggestion") is None


# ===========================================================================
# 4. Kanban: Blocked work visibility
# ===========================================================================

class TestBlockedWorkVisibility:

    def test_set_item_to_blocked(self, admin_client):
        """Setting status to blocked should record reason and timestamp."""
        c, conn = admin_client
        item_id = _create_work_item(conn, title="Blockable item", status="in_progress")

        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"status": "blocked", "blocked_reason": "Waiting for API key"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200

        # Verify via blocked endpoint
        resp = c.get("/api/admin/work-items/blocked")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["count"] >= 1
        blocked = [i for i in data["blocked_items"] if i["title"] == "Blockable item"]
        assert len(blocked) == 1
        assert blocked[0]["blocked_reason"] == "Waiting for API key"
        assert blocked[0]["blocked_at"] is not None

    def test_unblock_records_timestamp(self, admin_client):
        """Moving from blocked to in_progress should set unblocked_at."""
        c, conn = admin_client
        item_id = _create_work_item(conn, title="Unblockable", status="in_progress")

        # Block it
        c.put(f"/api/admin/work-items/{item_id}",
              json={"status": "blocked", "blocked_reason": "Waiting"},
              content_type="application/json",
              headers={"X-Requested-With": "XMLHttpRequest"})

        # Unblock it
        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"status": "in_progress"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200

        row = conn.execute(
            "SELECT unblocked_at FROM work_item WHERE id = ?", (item_id,)
        ).fetchone()
        assert row["unblocked_at"] is not None

    def test_blocked_endpoint_empty(self, admin_client):
        """Blocked endpoint returns empty when no blocked items."""
        c, conn = admin_client
        resp = c.get("/api/admin/work-items/blocked")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["count"] == 0


# ===========================================================================
# 5. Lean Six Sigma: Pp/Ppk process performance
# ===========================================================================

class TestProcessPerformance:

    def test_pp_ppk_calculation(self):
        """Verify Pp/Ppk calculation uses total variation."""
        from mandarin.quality.capability import calculate_process_performance

        # Known values: mean=0.85, total std ≈ 0.05
        values = [0.80, 0.82, 0.85, 0.87, 0.90, 0.83, 0.86, 0.88, 0.84, 0.85]
        result = calculate_process_performance(values, lsl=0.70, usl=1.0)

        assert result["n"] == 10
        assert result["pp"] is not None
        assert result["ppk"] is not None
        assert result["ppu"] is not None
        assert result["ppl"] is not None
        # Pp = (USL - LSL) / (6 * sigma_overall)
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        sigma = math.sqrt(variance)
        expected_pp = (1.0 - 0.70) / (6 * sigma)
        assert abs(result["pp"] - round(expected_pp, 4)) < 0.001

    def test_pp_ppk_interpretation(self):
        """Check interpretation labels."""
        from mandarin.quality.capability import calculate_process_performance

        # Capable process (very tight distribution, well-centered)
        values = [0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85,
                  0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85]
        result = calculate_process_performance(values, lsl=0.70, usl=1.0)
        # With zero or near-zero variation, should be perfect or capable
        assert result["interpretation"] in ("perfect", "capable")

        # Not capable (wide distribution spanning outside spec limits)
        values = [0.60, 0.65, 0.70, 0.75, 0.95, 1.0, 0.50, 0.55]
        result = calculate_process_performance(values, lsl=0.70, usl=1.0)
        assert result["interpretation"] == "not_capable"

    def test_performance_endpoint_assess(self):
        """assess_accuracy_performance returns Pp/Ppk data from DB."""
        from mandarin.quality.capability import assess_accuracy_performance
        from tests.conftest import make_test_db

        conn, path = make_test_db()
        try:
            # Insert some session data for the performance calc
            for i in range(10):
                conn.execute(
                    """INSERT INTO session_log
                       (user_id, items_completed, items_correct, started_at, duration_seconds)
                       VALUES (1, 10, ?, datetime('now', ?), 300)""",
                    (7 + (i % 3), f"-{i} days"),
                )
            conn.commit()
            result = assess_accuracy_performance(conn, days=30)
            assert result["metric"] == "drill_accuracy_performance"
            assert result["n"] == 10
            assert result["pp"] is not None or result["ppk"] is not None
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ===========================================================================
# 6. Lean Six Sigma: Pareto analysis
# ===========================================================================

class TestParetoAnalysis:

    def test_pareto_calculation(self):
        """Verify Pareto analysis ranks errors and finds vital few."""
        from mandarin.quality.flow_metrics import calculate_error_pareto
        from tests.conftest import make_test_db

        conn, path = make_test_db()
        try:
            # Ensure a content_item exists for FK
            conn.execute("PRAGMA foreign_keys = OFF")
            # Insert test errors using the actual error_log schema
            error_types = [
                ("tone", 50),
                ("segment", 30),
                ("grammar", 10),
                ("vocab", 5),
                ("other", 5),
            ]
            for etype, count in error_types:
                for _ in range(count):
                    conn.execute(
                        """INSERT INTO error_log
                           (user_id, content_item_id, modality, error_type, created_at)
                           VALUES (1, 1, 'reading', ?, datetime('now'))""",
                        (etype,),
                    )
            conn.commit()

            result = calculate_error_pareto(conn, days=30)
            assert result["total_errors"] == 100
            assert len(result["items"]) == 5
            # First item should be the most frequent
            assert result["items"][0]["error_type"] == "tone"
            assert result["items"][0]["count"] == 50
            # Cumulative should reach 100
            assert result["items"][-1]["cumulative_percentage"] >= 99.9
            # Vital few: tone (50%) + segment (30%) = 80%
            assert "tone" in result["vital_few"]
            assert "segment" in result["vital_few"]
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_pareto_empty_db(self):
        """Pareto returns empty result when no errors exist."""
        from mandarin.quality.flow_metrics import calculate_error_pareto
        from tests.conftest import make_test_db

        conn, path = make_test_db()
        try:
            result = calculate_error_pareto(conn, days=30)
            assert result["total_errors"] == 0
            assert result["items"] == []
            assert result["vital_few"] == []
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ===========================================================================
# 7. Spiral: Link SPC violations to risk register
# ===========================================================================

class TestSPCRiskLinking:

    def test_link_creates_risk_item(self):
        """SPC violation should create a risk_item when none exists."""
        from mandarin.web.quality_scheduler import _link_spc_to_risk
        from tests.conftest import make_test_db

        conn, path = make_test_db()
        try:
            violations = [
                {"index": 5, "value": 0.45, "rule": 1, "description": "Beyond 3-sigma (lower)"},
            ]
            _link_spc_to_risk(conn, "drill_accuracy", violations, obs_id=42)
            conn.commit()

            risks = conn.execute(
                "SELECT * FROM risk_item WHERE title LIKE 'SPC violation:%'"
            ).fetchall()
            assert len(risks) == 1
            risk = risks[0]
            assert risk["category"] == "technical"
            assert risk["probability"] == 4  # Rule 1 = high
            assert risk["impact"] == 4
            assert "drill_accuracy" in risk["title"]
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_link_escalates_existing_risk(self):
        """SPC violation should escalate existing active risk."""
        from mandarin.web.quality_scheduler import _link_spc_to_risk
        from tests.conftest import make_test_db

        conn, path = make_test_db()
        try:
            # Create existing low-severity risk
            conn.execute(
                """INSERT INTO risk_item (category, title, description, probability, impact, status)
                   VALUES ('technical', 'SPC violation: drill_accuracy', 'initial', 2, 2, 'active')"""
            )
            conn.commit()

            violations = [
                {"index": 5, "value": 0.45, "rule": 1, "description": "Beyond 3-sigma"},
            ]
            _link_spc_to_risk(conn, "drill_accuracy", violations, obs_id=99)
            conn.commit()

            risk = conn.execute(
                "SELECT * FROM risk_item WHERE title LIKE 'SPC violation: drill_accuracy%' AND status = 'active'"
            ).fetchone()
            # Should be escalated to higher values
            assert risk["probability"] == 4
            assert risk["impact"] == 4
            assert "Escalated" in risk["description"]
        finally:
            conn.close()
            path.unlink(missing_ok=True)

    def test_link_moderate_severity_for_trend_rules(self):
        """Trend violations (rule 2, 3) should create moderate severity."""
        from mandarin.web.quality_scheduler import _link_spc_to_risk
        from tests.conftest import make_test_db

        conn, path = make_test_db()
        try:
            violations = [
                {"index": 10, "value": 0.72, "rule": 2, "description": "7 consecutive increasing"},
            ]
            _link_spc_to_risk(conn, "response_time", violations, obs_id=50)
            conn.commit()

            risk = conn.execute(
                "SELECT * FROM risk_item WHERE title LIKE 'SPC violation: response_time%'"
            ).fetchone()
            assert risk["probability"] == 3
            assert risk["impact"] == 3
        finally:
            conn.close()
            path.unlink(missing_ok=True)


# ===========================================================================
# 8. Spiral: Prototype tracking
# ===========================================================================

class TestPrototypeTracking:

    def test_create_prototype_work_item(self, admin_client):
        """Can create a work item with implementation_type=prototype."""
        c, conn = admin_client
        resp = c.post("/api/admin/work-items",
                      json={"title": "Test prototype", "implementation_type": "prototype"},
                      content_type="application/json",
                      headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 201
        data = json.loads(resp.data)
        item_id = data["id"]

        row = conn.execute(
            "SELECT implementation_type FROM work_item WHERE id = ?", (item_id,)
        ).fetchone()
        assert row["implementation_type"] == "prototype"

    def test_prototype_done_prompts_evaluation(self, admin_client):
        """Marking a prototype done should return prototype_prompt."""
        c, conn = admin_client
        item_id = _create_work_item(conn, title="Proto item",
                                    status="in_progress", implementation_type="prototype")

        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"status": "done"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "prototype_prompt" in data
        assert data["prototype_prompt"]["message"].startswith("Prototype complete")
        assert "promote" in data["prototype_prompt"]["options"]
        assert "discard" in data["prototype_prompt"]["options"]
        assert "iterate" in data["prototype_prompt"]["options"]

    def test_filter_by_implementation_type(self, admin_client):
        """Can filter work items by implementation type."""
        c, conn = admin_client
        _create_work_item(conn, title="Proto A", implementation_type="prototype")
        _create_work_item(conn, title="Full B", implementation_type="full")
        _create_work_item(conn, title="No type C")

        resp = c.get("/api/admin/work-items/by-type?implementation_type=prototype")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["count"] == 1
        assert data["items"][0]["title"] == "Proto A"

    def test_filter_all_typed_items(self, admin_client):
        """Without filter, return all items with non-null implementation_type."""
        c, conn = admin_client
        _create_work_item(conn, title="Proto A", implementation_type="prototype")
        _create_work_item(conn, title="Full B", implementation_type="full")
        _create_work_item(conn, title="No type C")

        resp = c.get("/api/admin/work-items/by-type")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["count"] == 2


# ===========================================================================
# 9. Agile: Story points on work items
# ===========================================================================

class TestStoryPoints:

    def test_create_work_item_with_estimate(self, admin_client):
        """Can create work item with estimate field."""
        c, conn = admin_client
        resp = c.post("/api/admin/work-items",
                      json={"title": "Estimated item", "estimate": "M"},
                      content_type="application/json",
                      headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 201
        item_id = json.loads(resp.data)["id"]

        row = conn.execute(
            "SELECT estimate FROM work_item WHERE id = ?", (item_id,)
        ).fetchone()
        assert row["estimate"] == "M"

    def test_update_estimate(self, admin_client):
        """Can update estimate on existing work item."""
        c, conn = admin_client
        item_id = _create_work_item(conn, title="No estimate")

        resp = c.put(f"/api/admin/work-items/{item_id}",
                     json={"estimate": "XL"},
                     content_type="application/json",
                     headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200

        row = conn.execute(
            "SELECT estimate FROM work_item WHERE id = ?", (item_id,)
        ).fetchone()
        assert row["estimate"] == "XL"

    def test_estimate_in_list_response(self, admin_client):
        """Estimate field appears in work items list."""
        c, conn = admin_client
        _create_work_item(conn, title="S item", estimate="S")

        resp = c.get("/api/admin/work-items")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        items = [i for i in data["items"] if i["title"] == "S item"]
        assert len(items) == 1
        assert items[0]["estimate"] == "S"

    def test_estimate_points_mapping(self):
        """Verify the estimate-to-points mapping."""
        from mandarin.settings import ESTIMATE_POINTS
        assert ESTIMATE_POINTS == {"S": 1, "M": 3, "L": 5, "XL": 8}


# ===========================================================================
# 10. Spiral: Risk taxonomy checklist
# ===========================================================================

class TestRiskTaxonomyCoverage:

    def test_coverage_all_gaps(self, admin_client):
        """All categories show as gaps when no risks exist."""
        c, conn = admin_client
        resp = c.get("/api/admin/risks/coverage")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["all_covered"] is False
        assert len(data["gaps"]) == 5
        for cat in ["technical", "operational", "business", "security", "compliance"]:
            assert cat in data["gaps"]

    def test_coverage_partial(self, admin_client):
        """Partially covered categories."""
        c, conn = admin_client
        conn.execute(
            """INSERT INTO risk_item (category, title, probability, impact, status)
               VALUES ('technical', 'DB backup', 3, 4, 'active')"""
        )
        conn.execute(
            """INSERT INTO risk_item (category, title, probability, impact, status)
               VALUES ('security', 'Auth bypass', 4, 5, 'active')"""
        )
        conn.commit()

        resp = c.get("/api/admin/risks/coverage")
        data = json.loads(resp.data)
        assert data["all_covered"] is False
        assert "technical" not in data["gaps"]
        assert "security" not in data["gaps"]
        assert "operational" in data["gaps"]
        assert "business" in data["gaps"]
        assert "compliance" in data["gaps"]

    def test_coverage_full(self, admin_client):
        """All categories covered."""
        c, conn = admin_client
        for cat in ["technical", "operational", "business", "security", "compliance"]:
            conn.execute(
                """INSERT INTO risk_item (category, title, probability, impact, status)
                   VALUES (?, ?, 3, 3, 'active')""",
                (cat, f"Risk in {cat}"),
            )
        conn.commit()

        resp = c.get("/api/admin/risks/coverage")
        data = json.loads(resp.data)
        assert data["all_covered"] is True
        assert len(data["gaps"]) == 0

    def test_coverage_ignores_retired(self, admin_client):
        """Retired risks should not count toward coverage."""
        c, conn = admin_client
        conn.execute(
            """INSERT INTO risk_item (category, title, probability, impact, status)
               VALUES ('technical', 'Old risk', 3, 3, 'retired')"""
        )
        conn.commit()

        resp = c.get("/api/admin/risks/coverage")
        data = json.loads(resp.data)
        assert "technical" in data["gaps"]


# ===========================================================================
# Schema migration test
# ===========================================================================

class TestMigrationV94:

    def test_new_columns_exist(self, test_db):
        """Migration v93->v94 should add estimate, implementation_type, blocked_reason."""
        conn, _ = test_db
        cols = {r[1] for r in conn.execute("PRAGMA table_info(work_item)").fetchall()}
        assert "estimate" in cols
        assert "implementation_type" in cols
        assert "blocked_reason" in cols
