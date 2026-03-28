"""Tests for methodology A+ gap closures — Phase 2.

Covers:
1. Scrum: Sprint table + admin endpoints
2. Agile: Standalone retrospectives
3. Agile: WSJF backlog prioritization on work_items
4. Lean Six Sigma: 5 Why / Root cause analysis
5. Lean Six Sigma: Ishikawa categories
6. Spiral: Risk review with burndown
7. Spiral: Data-driven risk identification
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.t2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_db


# ═══════════════════════════════════════════════════════════════════════════
# Schema / Migration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaMigration:
    """Verify that migration v95->v96 creates the expected tables and columns."""

    def setup_method(self):
        self.conn, self.path = make_test_db()

    def teardown_method(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)

    def _col_set(self, table):
        return {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _table_set(self):
        return {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

    def test_sprint_has_retro_columns(self):
        cols = self._col_set("sprint")
        for col in ("review_notes", "retro_went_well", "retro_improve", "retro_action_items"):
            assert col in cols, f"sprint table missing column: {col}"

    def test_work_item_has_sprint_id(self):
        cols = self._col_set("work_item")
        assert "sprint_id" in cols

    def test_work_item_has_wsjf_fields(self):
        cols = self._col_set("work_item")
        for col in ("business_value", "time_criticality", "risk_reduction", "job_size"):
            assert col in cols, f"work_item table missing column: {col}"

    def test_retrospective_table_exists(self):
        assert "retrospective" in self._table_set()

    def test_root_cause_analysis_table_exists(self):
        assert "root_cause_analysis" in self._table_set()

    def test_risk_review_table_exists(self):
        assert "risk_review" in self._table_set()


# ═══════════════════════════════════════════════════════════════════════════
# Sprint CRUD Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSprintCRUD:
    """Test sprint creation, listing, completion, and retrospective storage."""

    def setup_method(self):
        self.conn, self.path = make_test_db()

    def teardown_method(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)

    def test_create_sprint(self):
        self.conn.execute("""
            INSERT INTO sprint (user_id, sprint_number, goal, started_at, status, planned_points)
            VALUES (1, 1, 'Test sprint goal', datetime('now'), 'active', 20)
        """)
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM sprint WHERE sprint_number = 1").fetchone()
        assert row is not None
        assert row["goal"] == "Test sprint goal"
        assert row["status"] == "active"
        assert row["planned_points"] == 20

    def test_complete_sprint_with_retro(self):
        self.conn.execute("""
            INSERT INTO sprint (user_id, sprint_number, goal, started_at, status)
            VALUES (1, 1, 'Sprint 1', datetime('now'), 'active')
        """)
        self.conn.commit()
        sprint_id = self.conn.execute("SELECT id FROM sprint WHERE sprint_number = 1").fetchone()["id"]

        # Complete it
        self.conn.execute("""
            UPDATE sprint SET status = 'completed', ended_at = datetime('now'),
                   completed_items = 10, completed_points = 20, velocity = 3.3,
                   retro_went_well = 'Good progress on HSK 2',
                   retro_improve = 'Need more speaking drills',
                   retro_action_items = 'Add 5 speaking items next sprint'
            WHERE id = ?
        """, (sprint_id,))
        self.conn.commit()

        row = self.conn.execute("SELECT * FROM sprint WHERE id = ?", (sprint_id,)).fetchone()
        assert row["status"] == "completed"
        assert row["retro_went_well"] == "Good progress on HSK 2"
        assert row["retro_improve"] == "Need more speaking drills"
        assert row["retro_action_items"] == "Add 5 speaking items next sprint"

    def test_work_item_sprint_association(self):
        self.conn.execute("""
            INSERT INTO sprint (user_id, sprint_number, goal, started_at, status)
            VALUES (1, 1, 'Sprint 1', datetime('now'), 'active')
        """)
        self.conn.commit()
        sprint_id = self.conn.execute("SELECT id FROM sprint WHERE sprint_number = 1").fetchone()["id"]

        self.conn.execute("""
            INSERT INTO work_item (title, status, sprint_id) VALUES ('Task A', 'backlog', ?)
        """, (sprint_id,))
        self.conn.execute("""
            INSERT INTO work_item (title, status, sprint_id) VALUES ('Task B', 'done', ?)
        """, (sprint_id,))
        self.conn.commit()

        count = self.conn.execute(
            "SELECT COUNT(*) as c FROM work_item WHERE sprint_id = ?", (sprint_id,)
        ).fetchone()["c"]
        assert count == 2


# ═══════════════════════════════════════════════════════════════════════════
# Retrospective Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRetrospective:
    """Test standalone retrospective storage."""

    def setup_method(self):
        self.conn, self.path = make_test_db()

    def teardown_method(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)

    def test_create_standalone_retro(self):
        self.conn.execute("""
            INSERT INTO retrospective (period, went_well, improve, action_items)
            VALUES ('2026-W10', 'Good accuracy trend', 'Need more HSK 3 items', 'Expand content pool')
        """)
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM retrospective WHERE period = '2026-W10'").fetchone()
        assert row is not None
        assert row["went_well"] == "Good accuracy trend"
        assert row["improve"] == "Need more HSK 3 items"

    def test_retro_linked_to_sprint(self):
        self.conn.execute("""
            INSERT INTO sprint (user_id, sprint_number, goal, started_at, status)
            VALUES (1, 1, 'Sprint 1', datetime('now'), 'completed')
        """)
        self.conn.commit()
        sprint_id = self.conn.execute("SELECT id FROM sprint").fetchone()["id"]

        self.conn.execute("""
            INSERT INTO retrospective (period, went_well, improve, action_items, sprint_id)
            VALUES ('Sprint 1', 'Fast progress', 'Too many errors', 'Focus on tones', ?)
        """, (sprint_id,))
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM retrospective WHERE sprint_id = ?", (sprint_id,)
        ).fetchone()
        assert row is not None
        assert row["went_well"] == "Fast progress"


# ═══════════════════════════════════════════════════════════════════════════
# WSJF Prioritization Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestWSJFPrioritization:
    """Test WSJF scoring on work_item table."""

    def setup_method(self):
        self.conn, self.path = make_test_db()

    def teardown_method(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)

    def test_wsjf_default_values(self):
        self.conn.execute("INSERT INTO work_item (title, status) VALUES ('Test item', 'backlog')")
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM work_item WHERE title = 'Test item'").fetchone()
        assert row["business_value"] == 5
        assert row["time_criticality"] == 5
        assert row["risk_reduction"] == 5
        assert row["job_size"] == 5

    def test_wsjf_calculation(self):
        """WSJF = (bv + tc + rr) / js"""
        self.conn.execute("""
            INSERT INTO work_item (title, status, business_value, time_criticality,
                                   risk_reduction, job_size)
            VALUES ('High priority', 'backlog', 10, 8, 6, 2)
        """)
        self.conn.execute("""
            INSERT INTO work_item (title, status, business_value, time_criticality,
                                   risk_reduction, job_size)
            VALUES ('Low priority', 'backlog', 2, 2, 1, 10)
        """)
        self.conn.commit()

        rows = self.conn.execute("""
            SELECT title, business_value, time_criticality, risk_reduction, job_size
            FROM work_item WHERE title IN ('High priority', 'Low priority')
        """).fetchall()

        items = []
        for r in rows:
            bv = r["business_value"]
            tc = r["time_criticality"]
            rr = r["risk_reduction"]
            js = max(r["job_size"], 1)
            wsjf = (bv + tc + rr) / js
            items.append({"title": r["title"], "wsjf": wsjf})

        items.sort(key=lambda x: x["wsjf"], reverse=True)
        assert items[0]["title"] == "High priority"
        assert items[0]["wsjf"] == 12.0  # (10+8+6)/2
        assert items[1]["title"] == "Low priority"
        assert items[1]["wsjf"] == 0.5  # (2+2+1)/10

    def test_wsjf_zero_job_size_clamped(self):
        """Job size of 0 should be treated as 1 to avoid division by zero."""
        self.conn.execute("""
            INSERT INTO work_item (title, status, business_value, time_criticality,
                                   risk_reduction, job_size)
            VALUES ('Zero size', 'backlog', 5, 5, 5, 0)
        """)
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM work_item WHERE title = 'Zero size'").fetchone()
        js = max(row["job_size"] or 1, 1)
        wsjf = (row["business_value"] + row["time_criticality"] + row["risk_reduction"]) / js
        assert wsjf == 15.0


# ═══════════════════════════════════════════════════════════════════════════
# Root Cause Analysis (5 Whys + Ishikawa) Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRootCauseAnalysis:
    """Test root_cause_analysis table and Ishikawa categories."""

    def setup_method(self):
        self.conn, self.path = make_test_db()

    def teardown_method(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)

    def test_create_five_why(self):
        self.conn.execute("""
            INSERT INTO root_cause_analysis
                (why_1, why_2, why_3, why_4, why_5, root_cause, category)
            VALUES ('Accuracy dropped', 'Too many new items', 'Scheduler too aggressive',
                    'No throttle on new item rate', 'Missing adaptive logic',
                    'Scheduler lacks new-item throttle', 'method')
        """)
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM root_cause_analysis").fetchone()
        assert row is not None
        assert row["why_1"] == "Accuracy dropped"
        assert row["root_cause"] == "Scheduler lacks new-item throttle"
        assert row["category"] == "method"

    def test_rca_linked_to_work_item(self):
        self.conn.execute("INSERT INTO work_item (title, status) VALUES ('Fix accuracy', 'backlog')")
        self.conn.commit()
        wi_id = self.conn.execute("SELECT id FROM work_item WHERE title = 'Fix accuracy'").fetchone()["id"]

        self.conn.execute("""
            INSERT INTO root_cause_analysis (work_item_id, why_1, root_cause, category)
            VALUES (?, 'Accuracy low', 'Bad calibration', 'measurement')
        """, (wi_id,))
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM root_cause_analysis WHERE work_item_id = ?", (wi_id,)
        ).fetchone()
        assert row is not None
        assert row["category"] == "measurement"

    def test_ishikawa_category_constraint(self):
        """Only the 6 Ishikawa categories are allowed."""
        valid_cats = ('method', 'measurement', 'material', 'machine', 'man', 'environment')
        for cat in valid_cats:
            self.conn.execute("""
                INSERT INTO root_cause_analysis (why_1, category) VALUES ('test', ?)
            """, (cat,))
        self.conn.commit()
        count = self.conn.execute("SELECT COUNT(*) as c FROM root_cause_analysis").fetchone()["c"]
        assert count == 6

        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute("""
                INSERT INTO root_cause_analysis (why_1, category) VALUES ('test', 'invalid_category')
            """)

    def test_ishikawa_distribution(self):
        """Group root causes by category."""
        data = [
            ("method", "Bad process"),
            ("method", "Wrong sequence"),
            ("man", "Training gap"),
            ("machine", "Server slow"),
        ]
        for cat, cause in data:
            self.conn.execute("""
                INSERT INTO root_cause_analysis (why_1, root_cause, category)
                VALUES ('why', ?, ?)
            """, (cause, cat))
        self.conn.commit()

        rows = self.conn.execute("""
            SELECT category, COUNT(*) as count
            FROM root_cause_analysis
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
        """).fetchall()
        dist = {r["category"]: r["count"] for r in rows}
        assert dist["method"] == 2
        assert dist["man"] == 1
        assert dist["machine"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Risk Review / Burndown Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRiskReview:
    """Test risk_review table and burndown aggregation."""

    def setup_method(self):
        self.conn, self.path = make_test_db()

    def teardown_method(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)

    def test_create_risk_review(self):
        # Create a risk item first
        self.conn.execute("""
            INSERT INTO risk_item (category, title, probability, impact, status)
            VALUES ('technical', 'DB corruption risk', 3, 5, 'active')
        """)
        self.conn.commit()
        risk_id = self.conn.execute("SELECT id FROM risk_item").fetchone()["id"]

        # Record a review
        self.conn.execute("""
            INSERT INTO risk_review (risk_item_id, previous_score, new_score, notes)
            VALUES (?, 15, 10, 'Implemented backups, reduced impact')
        """, (risk_id,))
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM risk_review WHERE risk_item_id = ?", (risk_id,)
        ).fetchone()
        assert row is not None
        assert row["previous_score"] == 15
        assert row["new_score"] == 10
        assert row["notes"] == "Implemented backups, reduced impact"

    def test_risk_burndown_aggregation(self):
        """Verify burndown aggregation by date."""
        self.conn.execute("""
            INSERT INTO risk_item (category, title, probability, impact, status)
            VALUES ('technical', 'Risk A', 5, 5, 'active')
        """)
        self.conn.commit()
        risk_id = self.conn.execute("SELECT id FROM risk_item").fetchone()["id"]

        # Insert reviews on different dates
        self.conn.execute("""
            INSERT INTO risk_review (risk_item_id, previous_score, new_score, notes, reviewed_at)
            VALUES (?, 25, 20, 'Review 1', '2026-03-01 10:00:00')
        """, (risk_id,))
        self.conn.execute("""
            INSERT INTO risk_review (risk_item_id, previous_score, new_score, notes, reviewed_at)
            VALUES (?, 20, 15, 'Review 2', '2026-03-08 10:00:00')
        """, (risk_id,))
        self.conn.execute("""
            INSERT INTO risk_review (risk_item_id, previous_score, new_score, notes, reviewed_at)
            VALUES (?, 15, 9, 'Review 3', '2026-03-13 10:00:00')
        """, (risk_id,))
        self.conn.commit()

        rows = self.conn.execute("""
            SELECT date(reviewed_at) as review_date,
                   SUM(new_score) as total_score,
                   COUNT(*) as review_count,
                   AVG(new_score) as avg_score
            FROM risk_review
            GROUP BY date(reviewed_at)
            ORDER BY review_date ASC
        """).fetchall()

        assert len(rows) == 3
        assert rows[0]["review_date"] == "2026-03-01"
        assert rows[0]["total_score"] == 20
        assert rows[2]["review_date"] == "2026-03-13"
        assert rows[2]["total_score"] == 9


# ═══════════════════════════════════════════════════════════════════════════
# Data-Driven Risk Identification Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDataDrivenRiskIdentification:
    """Test _auto_identify_risks function."""

    def setup_method(self):
        self.conn, self.path = make_test_db()
        # Ensure a content_item exists for FK references
        self.conn.execute("""
            INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english, hsk_level)
            VALUES (1, '你好', 'nǐ hǎo', 'hello', 1)
        """)
        self.conn.commit()

    def teardown_method(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)

    def test_no_risks_when_data_empty(self):
        """With no data, no auto-risks should be created."""
        from mandarin.web.quality_scheduler import _auto_identify_risks
        _auto_identify_risks(self.conn)
        self.conn.commit()
        count = self.conn.execute(
            "SELECT COUNT(*) as c FROM risk_item WHERE title LIKE '%risk:%'"
        ).fetchone()["c"]
        assert count == 0

    def test_quality_risk_on_error_spike(self):
        """When error count doubles week-over-week, a quality risk is created."""
        from mandarin.web.quality_scheduler import _auto_identify_risks

        # Insert prior week errors (small)
        for i in range(5):
            self.conn.execute("""
                INSERT INTO error_log (user_id, content_item_id, modality, user_answer,
                                       expected_answer, drill_type, error_type, created_at)
                VALUES (1, 1, 'reading', 'wrong', 'right', 'hanzi_to_pinyin', 'tone',
                        datetime('now', '-10 days'))
            """)
        # Insert current week errors (more than 2x)
        for i in range(15):
            self.conn.execute("""
                INSERT INTO error_log (user_id, content_item_id, modality, user_answer,
                                       expected_answer, drill_type, error_type, created_at)
                VALUES (1, 1, 'reading', 'wrong', 'right', 'hanzi_to_pinyin', 'tone',
                        datetime('now', '-1 hour'))
            """)
        self.conn.commit()

        _auto_identify_risks(self.conn)
        self.conn.commit()

        row = self.conn.execute(
            "SELECT * FROM risk_item WHERE title = 'Quality risk: error rate spiking'"
        ).fetchone()
        assert row is not None
        assert row["status"] == "active"
        assert row["category"] == "content"

    def test_duplicate_risk_not_created(self):
        """If an active risk already exists, don't create a duplicate."""
        from mandarin.web.quality_scheduler import _auto_identify_risks

        # Pre-create the risk
        self.conn.execute("""
            INSERT INTO risk_item (category, title, probability, impact, status)
            VALUES ('content', 'Quality risk: error rate spiking', 4, 3, 'active')
        """)
        # Insert error data that would trigger
        for i in range(5):
            self.conn.execute("""
                INSERT INTO error_log (user_id, content_item_id, modality, user_answer,
                                       expected_answer, drill_type, error_type, created_at)
                VALUES (1, 1, 'reading', 'wrong', 'right', 'hanzi_to_pinyin', 'tone',
                        datetime('now', '-10 days'))
            """)
        for i in range(15):
            self.conn.execute("""
                INSERT INTO error_log (user_id, content_item_id, modality, user_answer,
                                       expected_answer, drill_type, error_type, created_at)
                VALUES (1, 1, 'reading', 'wrong', 'right', 'hanzi_to_pinyin', 'tone',
                        datetime('now', '-1 hour'))
            """)
        self.conn.commit()

        _auto_identify_risks(self.conn)
        self.conn.commit()

        count = self.conn.execute(
            "SELECT COUNT(*) as c FROM risk_item WHERE title = 'Quality risk: error rate spiking'"
        ).fetchone()["c"]
        assert count == 1  # Still just the original, no duplicate
