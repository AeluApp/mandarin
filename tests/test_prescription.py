"""Tests for Intelligence Engine Prescription Layer.

Covers: generate_work_order, candidate selection, FINDING_TO_ACTION lookup,
subordination, success conditions, mark_work_order_implemented,
stale detection, check_subordination, work order history.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone, UTC
from unittest.mock import patch


from tests.shared_db import make_test_db as _make_db


def _insert_finding(conn, **kwargs):
    """Insert a pi_finding row and return its id."""
    defaults = dict(
        audit_id=None, dimension="retention", severity="medium",
        title="Test finding", analysis="Some analysis",
        status="investigating", metric_name="retention",
        times_seen=1,
    )
    defaults.update(kwargs)
    cur = conn.execute("""
        INSERT INTO pi_finding (audit_id, dimension, severity, title, analysis,
                                status, metric_name, times_seen)
        VALUES (:audit_id, :dimension, :severity, :title, :analysis,
                :status, :metric_name, :times_seen)
    """, defaults)
    conn.commit()
    return cur.lastrowid


def _insert_audit(conn, dimension_scores=None):
    """Insert a product_audit row and return its id."""
    scores = dimension_scores or {
        "retention": {"score": 55.0, "grade": "C", "finding_count": 2, "confidence": "medium"},
        "ux": {"score": 72.0, "grade": "B", "finding_count": 1, "confidence": "medium"},
        "engineering": {"score": 80.0, "grade": "B", "finding_count": 0, "confidence": "high"},
    }
    cur = conn.execute("""
        INSERT INTO product_audit (overall_grade, overall_score, dimension_scores,
                                    findings_json, findings_count)
        VALUES ('C', 65.0, ?, '[]', 0)
    """, (json.dumps(scores),))
    conn.commit()
    return cur.lastrowid


class TestGenerateWorkOrder(unittest.TestCase):
    """1. generate_work_order returns exactly one WorkOrder."""

    def test_returns_single_work_order(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="D7 retention below target")

        from mandarin.intelligence.prescription import generate_work_order, WorkOrder
        wo = generate_work_order(conn, 1)

        self.assertIsInstance(wo, WorkOrder)
        self.assertEqual(wo.audit_cycle_id, 1)
        self.assertIn("retention", wo.instruction.lower())

        # Verify persisted to DB
        row = conn.execute("SELECT COUNT(*) FROM pi_work_order").fetchone()
        self.assertEqual(row[0], 1)


class TestConstraintDimensionSelection(unittest.TestCase):
    """2. Selects constraint-dimension finding over non-constraint."""

    def test_prefers_constraint_dimension(self):
        conn = _make_db()
        # retention is the constraint (lowest score, highest marginal improvement)
        _insert_audit(conn)
        _insert_finding(conn, dimension="ux", severity="high",
                        title="UX issue", times_seen=5)
        _insert_finding(conn, dimension="retention", severity="medium",
                        title="Churn rate elevated", times_seen=1)

        from mandarin.intelligence.prescription import generate_work_order
        wo = generate_work_order(conn, 1)

        # Should pick retention (constraint dim) even though ux has higher times_seen
        self.assertEqual(wo.constraint_dimension, "retention")
        self.assertIn("retention", wo.instruction.lower())


class TestFallbackSelection(unittest.TestCase):
    """3. Falls back when no constraint-dim finding exists."""

    def test_fallback_to_any_dimension(self):
        conn = _make_db()
        _insert_audit(conn)
        # No retention findings — only ux
        _insert_finding(conn, dimension="ux", severity="high",
                        title="UX completion rate low")

        from mandarin.intelligence.prescription import generate_work_order
        wo = generate_work_order(conn, 1)

        # Should still produce a work order using ux finding as fallback
        self.assertEqual(wo.finding_id, 1)


class TestNoActionableFindings(unittest.TestCase):
    """4. NoActionableFindings when all findings resolved/in-progress."""

    def test_raises_when_all_resolved(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Resolved thing", status="resolved")
        _insert_finding(conn, dimension="ux", severity="medium",
                        title="Rejected thing", status="rejected")

        from mandarin.intelligence.prescription import generate_work_order, NoActionableFindings
        with self.assertRaises(NoActionableFindings):
            generate_work_order(conn, 1)

    def test_raises_when_no_findings(self):
        conn = _make_db()
        _insert_audit(conn)

        from mandarin.intelligence.prescription import generate_work_order, NoActionableFindings
        with self.assertRaises(NoActionableFindings):
            generate_work_order(conn, 1)


class TestFindingToActionKeyword(unittest.TestCase):
    """5. _FINDING_TO_ACTION keyword match returns correct file/param."""

    def test_churn_keyword(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Churn rate elevated")

        from mandarin.intelligence.prescription import generate_work_order
        wo = generate_work_order(conn, 1)

        self.assertEqual(wo.target_file, "mandarin/scheduler.py")
        self.assertEqual(wo.target_parameter, "RETENTION_THRESHOLD")
        self.assertEqual(wo.direction, "increase")

    def test_crash_keyword(self):
        conn = _make_db()
        _insert_audit(conn, dimension_scores={
            "engineering": {"score": 40.0, "grade": "D", "finding_count": 2, "confidence": "high"},
        })
        _insert_finding(conn, dimension="engineering", severity="critical",
                        title="Crash rate exceeds threshold")

        from mandarin.intelligence.prescription import generate_work_order
        wo = generate_work_order(conn, 1)

        self.assertEqual(wo.target_file, "mandarin/web/routes.py")
        self.assertEqual(wo.target_parameter, "crash_rate")
        self.assertEqual(wo.direction, "decrease")


class TestFallbackInstruction(unittest.TestCase):
    """6. Fallback instruction when no keyword match."""

    def test_dimension_fallback(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="medium",
                        title="Unusual metric pattern xyz")

        from mandarin.intelligence.prescription import generate_work_order
        wo = generate_work_order(conn, 1)

        # Should use dimension fallback ("retention", "")
        self.assertEqual(wo.target_file, "mandarin/scheduler.py")
        self.assertEqual(wo.target_parameter, "retention_policy")


class TestSubordinationCount(unittest.TestCase):
    """7. Subordination count correct (only non-constraint dims counted)."""

    def test_counts_non_constraint_findings(self):
        conn = _make_db()
        _insert_audit(conn)
        # Constraint-dim finding (retention)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="D7 retention low")
        # Non-constraint findings
        _insert_finding(conn, dimension="ux", severity="medium",
                        title="UX issue 1")
        _insert_finding(conn, dimension="engineering", severity="high",
                        title="Eng issue 1")
        _insert_finding(conn, dimension="marketing", severity="low",
                        title="Marketing issue")  # low severity — not counted

        from mandarin.intelligence.prescription import generate_work_order
        wo = generate_work_order(conn, 1)

        # Should count ux (medium) + engineering (high) = 2, not marketing (low)
        self.assertEqual(wo.subordinated_count, 2)
        self.assertEqual(len(wo.subordinated_finding_ids), 2)


class TestSuccessConditionErrorDimension(unittest.TestCase):
    """8. Success condition: error dimension threshold below baseline."""

    def test_error_dimension_threshold_below_baseline(self):
        conn = _make_db()
        _insert_audit(conn, dimension_scores={
            "engineering": {"score": 40.0, "grade": "D", "finding_count": 2, "confidence": "high"},
        })
        # Add model confidence for engineering
        conn.execute("""
            INSERT INTO pi_model_confidence (model_id, dimension, current_confidence)
            VALUES ('engineering', 'engineering', 0.6)
        """)
        _insert_finding(conn, dimension="engineering", severity="critical",
                        title="Error rate too high")
        conn.commit()

        from mandarin.intelligence.prescription import generate_work_order
        wo = generate_work_order(conn, 1)

        # For error dimensions, threshold should be BELOW baseline
        self.assertLessEqual(wo.success_threshold, wo.success_baseline)


class TestMarkWorkOrderImplemented(unittest.TestCase):
    """9. mark_work_order_implemented advances status and finding."""

    def test_implements_and_advances_finding(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Churn issue")

        from mandarin.intelligence.prescription import generate_work_order, mark_work_order_implemented
        wo = generate_work_order(conn, 1)

        ok = mark_work_order_implemented(conn, wo.id)
        self.assertTrue(ok)

        # Work order should be 'verifying'
        row = conn.execute("SELECT status FROM pi_work_order WHERE id = ?", (wo.id,)).fetchone()
        self.assertEqual(row["status"], "verifying")

        # Finding should be 'implemented'
        finding = conn.execute("SELECT status FROM pi_finding WHERE id = ?", (wo.finding_id,)).fetchone()
        self.assertEqual(finding["status"], "implemented")

    def test_cannot_implement_non_pending(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Churn issue")

        from mandarin.intelligence.prescription import generate_work_order, mark_work_order_implemented
        wo = generate_work_order(conn, 1)

        # First implementation succeeds
        mark_work_order_implemented(conn, wo.id)
        # Second should fail (already verifying)
        ok = mark_work_order_implemented(conn, wo.id)
        self.assertFalse(ok)


class TestStaleDetection(unittest.TestCase):
    """10. Stale detection after 2x verification window."""

    def test_marks_stale_after_double_window(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Old finding")

        from mandarin.intelligence.prescription import generate_work_order, check_stale_work_orders
        wo = generate_work_order(conn, 1)

        # Backdate created_at to beyond 2x window
        window = wo.verification_window_days
        old_date = (datetime.now(UTC) - timedelta(days=window * 2 + 1)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE pi_work_order SET created_at = ? WHERE id = ?", (old_date, wo.id))
        conn.commit()

        stale_ids = check_stale_work_orders(conn)
        self.assertIn(wo.id, stale_ids)

        # Verify status changed
        row = conn.execute("SELECT status FROM pi_work_order WHERE id = ?", (wo.id,)).fetchone()
        self.assertEqual(row["status"], "stale")

    def test_not_stale_within_window(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Recent finding")

        from mandarin.intelligence.prescription import generate_work_order, check_stale_work_orders
        generate_work_order(conn, 1)

        stale_ids = check_stale_work_orders(conn)
        self.assertEqual(stale_ids, [])


class TestCheckSubordination(unittest.TestCase):
    """11. _check_subordination returns warning for subordinated finding."""

    def test_subordinated_finding_gets_warning(self):
        conn = _make_db()
        _insert_audit(conn)
        # Constraint-dim finding
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Main constraint")
        # Non-constraint finding
        non_constraint_id = _insert_finding(conn, dimension="ux", severity="medium",
                                             title="UX issue")

        from mandarin.intelligence.prescription import generate_work_order, _check_subordination
        generate_work_order(conn, 1)

        warning = _check_subordination(conn, non_constraint_id)
        self.assertIsNotNone(warning)
        self.assertTrue(warning["subordination_warning"])
        self.assertEqual(warning["constraint_dimension"], "retention")

    def test_constraint_finding_no_warning(self):
        conn = _make_db()
        _insert_audit(conn)
        constraint_id = _insert_finding(conn, dimension="retention", severity="high",
                                         title="Main constraint")

        from mandarin.intelligence.prescription import generate_work_order, _check_subordination
        generate_work_order(conn, 1)

        # The constraint finding itself should not be subordinated
        warning = _check_subordination(conn, constraint_id)
        self.assertIsNone(warning)


class TestWorkOrderHistory(unittest.TestCase):
    """12. Work order history returns completed orders."""

    def test_returns_history(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="First finding")

        from mandarin.intelligence.prescription import (
            generate_work_order, mark_work_order_implemented, get_work_order_history,
        )

        wo1 = generate_work_order(conn, 1)
        mark_work_order_implemented(conn, wo1.id)

        history = get_work_order_history(conn)
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["finding_title"], "First finding")

    def test_supersedes_previous_pending(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Finding A")
        _insert_finding(conn, dimension="retention", severity="medium",
                        title="Finding B")

        from mandarin.intelligence.prescription import generate_work_order

        wo1 = generate_work_order(conn, 1)
        wo2 = generate_work_order(conn, 2)

        # wo1 should be superseded
        row = conn.execute("SELECT status FROM pi_work_order WHERE id = ?", (wo1.id,)).fetchone()
        self.assertEqual(row["status"], "superseded")

        # wo2 should be pending
        row2 = conn.execute("SELECT status FROM pi_work_order WHERE id = ?", (wo2.id,)).fetchone()
        self.assertEqual(row2["status"], "pending")


class TestGetCurrentWorkOrder(unittest.TestCase):
    """get_current_work_order returns active order or None."""

    def test_returns_current(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Active finding")

        from mandarin.intelligence.prescription import generate_work_order, get_current_work_order
        wo = generate_work_order(conn, 1)

        current = get_current_work_order(conn)
        self.assertIsNotNone(current)
        self.assertEqual(current["id"], wo.id)
        self.assertEqual(current["status"], "pending")

    def test_returns_none_when_all_terminal(self):
        conn = _make_db()
        _insert_audit(conn)
        _insert_finding(conn, dimension="retention", severity="high",
                        title="Done finding")

        from mandarin.intelligence.prescription import (
            generate_work_order, mark_work_order_implemented, get_current_work_order,
        )

        wo = generate_work_order(conn, 1)
        # Mark as stale (terminal)
        conn.execute("UPDATE pi_work_order SET status = 'stale' WHERE id = ?", (wo.id,))
        conn.commit()

        current = get_current_work_order(conn)
        self.assertIsNone(current)


if __name__ == "__main__":
    unittest.main()
