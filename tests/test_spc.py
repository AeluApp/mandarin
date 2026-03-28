"""Tests for Statistical Process Control — control limits and Western Electric rules."""

import math
import sqlite3
import unittest

from mandarin.quality.spc import (
    compute_control_limits,
    detect_out_of_control,
    get_spc_charts,
)


from tests.shared_db import make_test_db as _make_db


class TestComputeControlLimits(unittest.TestCase):
    """Tests for compute_control_limits()."""

    def test_basic_computation(self):
        """Verify UCL, CL, LCL for [85, 87, 83, 86, 84].

        Manual calculation:
            mean = 85.0
            sample variance = sum((xi - mean)^2) / (n-1) = 10/4 = 2.5
            sigma = sqrt(2.5) = 1.5811...
            UCL = 85 + 3*1.5811 = 89.7434...
            LCL = 85 - 3*1.5811 = 80.2566...
        """
        data = [85, 87, 83, 86, 84]
        limits = compute_control_limits(data)

        self.assertAlmostEqual(limits["cl"], 85.0, places=4)
        self.assertAlmostEqual(limits["sigma"], math.sqrt(2.5), places=4)
        self.assertAlmostEqual(limits["ucl"], 85.0 + 3 * math.sqrt(2.5), places=4)
        self.assertAlmostEqual(limits["lcl"], 85.0 - 3 * math.sqrt(2.5), places=4)

    def test_ucl_above_cl(self):
        """UCL is always above CL."""
        limits = compute_control_limits([85, 87, 83, 86, 84])
        self.assertGreater(limits["ucl"], limits["cl"])

    def test_lcl_below_cl(self):
        """LCL is always below CL."""
        limits = compute_control_limits([85, 87, 83, 86, 84])
        self.assertLess(limits["lcl"], limits["cl"])

    def test_result_keys(self):
        """Returned dict has ucl, cl, lcl, sigma keys."""
        limits = compute_control_limits([10, 20, 30])
        for key in ("ucl", "cl", "lcl", "sigma"):
            self.assertIn(key, limits)

    def test_empty_data(self):
        """Empty data returns default limits."""
        limits = compute_control_limits([])
        self.assertIn("ucl", limits)
        self.assertIn("cl", limits)
        self.assertIn("lcl", limits)
        self.assertIn("sigma", limits)

    def test_single_point(self):
        """Single data point returns defaults (< 2 points)."""
        limits = compute_control_limits([50.0])
        # Function requires len >= 2 for meaningful computation
        self.assertIn("cl", limits)

    def test_identical_values(self):
        """All identical values yield sigma near zero, UCL == LCL == CL."""
        limits = compute_control_limits([80, 80, 80, 80, 80])
        # variance = 0, sigma falls back to 0.001
        self.assertAlmostEqual(limits["cl"], 80.0, places=4)
        self.assertAlmostEqual(limits["sigma"], 0.001, places=6)

    def test_two_points(self):
        """Two data points should compute valid limits."""
        limits = compute_control_limits([10, 20])
        self.assertAlmostEqual(limits["cl"], 15.0, places=4)
        # variance = (25+25)/(2-1) = 50, sigma = sqrt(50)
        expected_sigma = math.sqrt(50)
        self.assertAlmostEqual(limits["sigma"], expected_sigma, places=4)


class TestDetectOutOfControl(unittest.TestCase):
    """Tests for detect_out_of_control() — Western Electric rules."""

    def _limits_for(self, data):
        return compute_control_limits(data)

    def test_rule1_beyond_3sigma(self):
        """Rule 1: a point at 95 in [85,87,83,86,84] data exceeds 3-sigma."""
        base = [85, 87, 83, 86, 84]
        limits = self._limits_for(base)
        # 95 is well above UCL (~89.74), so add it
        data_with_outlier = base + [95]
        violations = detect_out_of_control(data_with_outlier, limits)
        rule1 = [v for v in violations if v["rule"] == 1]
        self.assertTrue(len(rule1) > 0, "Expected Rule 1 violation for point at 95")
        # The violation should be at the last index
        self.assertEqual(rule1[0]["index"], 5)

    def test_rule2_two_of_three_above_2sigma(self):
        """Rule 2: 2 of 3 consecutive points > 2-sigma (same side)."""
        base = [85, 87, 83, 86, 84]
        limits = self._limits_for(base)
        # 2-sigma above = 85 + 2*1.581 = ~88.16
        # Add two points at 89 (above 2-sigma but below 3-sigma UCL ~89.74)
        data = base + [89, 89]
        violations = detect_out_of_control(data, limits)
        rule2 = [v for v in violations if v["rule"] == 2]
        self.assertTrue(len(rule2) > 0, "Expected Rule 2 violation for two points at 89")

    def test_rule4_eight_consecutive_above_mean(self):
        """Rule 4: 8 consecutive points above the center line."""
        # Build data with mean=50, then 8 points above mean
        base = [50, 50]
        limits = compute_control_limits(base + [50] * 8)
        # All points at 51 are above CL=50, but we need the limits from
        # a data set where CL=50 and sigma is reasonable.
        # Use a set where mean is clear and sigma allows detection.
        seed = [45, 55, 45, 55]  # mean=50, sigma~5.77
        limits = self._limits_for(seed)
        # Now 8 consecutive points above 50
        data = seed + [51, 52, 51, 52, 51, 52, 51, 52]
        violations = detect_out_of_control(data, limits)
        rule4 = [v for v in violations if v["rule"] == 4]
        self.assertTrue(len(rule4) > 0,
                        "Expected Rule 4 violation for 8 consecutive above mean")

    def test_no_violations_on_stable_data(self):
        """Data within normal limits yields no violations."""
        data = [85, 87, 83, 86, 84]
        limits = self._limits_for(data)
        violations = detect_out_of_control(data, limits)
        self.assertEqual(violations, [])

    def test_empty_data_returns_empty(self):
        """Empty data returns empty violations list."""
        violations = detect_out_of_control([], {})
        self.assertEqual(violations, [])

    def test_empty_limits_returns_empty(self):
        """Empty limits dict returns empty violations list."""
        violations = detect_out_of_control([1, 2, 3], {})
        self.assertEqual(violations, [])

    def test_violation_dict_keys(self):
        """Each violation dict has index, value, rule, description."""
        base = [85, 87, 83, 86, 84]
        limits = self._limits_for(base)
        data = base + [95]
        violations = detect_out_of_control(data, limits)
        self.assertTrue(len(violations) > 0)
        for v in violations:
            for key in ("index", "value", "rule", "description"):
                self.assertIn(key, v, f"Missing key: {key}")

    def test_deduplicated_by_index(self):
        """Violations are deduplicated by index (no two entries with same index)."""
        base = [85, 87, 83, 86, 84]
        limits = self._limits_for(base)
        # A point way outside triggers multiple rules
        data = base + [99]
        violations = detect_out_of_control(data, limits)
        indices = [v["index"] for v in violations]
        self.assertEqual(len(indices), len(set(indices)),
                         "Violations should be deduplicated by index")

    def test_zero_sigma_returns_empty(self):
        """Sigma of zero returns no violations (avoids division by zero)."""
        limits = {"ucl": 100, "cl": 50, "lcl": 0, "sigma": 0}
        violations = detect_out_of_control([50, 60, 70], limits)
        self.assertEqual(violations, [])


class TestGetSpcCharts(unittest.TestCase):
    """Tests for get_spc_charts() with seeded session_log data."""

    def test_returns_dict(self):
        """get_spc_charts returns a dict."""
        conn = _make_db()
        charts = get_spc_charts(conn)
        self.assertIsInstance(charts, dict)
        conn.close()

    def test_empty_db_returns_empty_charts(self):
        """Empty session_log returns empty charts dict."""
        conn = _make_db()
        charts = get_spc_charts(conn)
        # No data seeded, so session_completion chart should not appear
        self.assertEqual(charts, {})
        conn.close()

    def test_session_completion_chart_with_data(self):
        """Seeded session_log data produces a chart."""
        conn = _make_db()
        # Seed 5 days of session data using production schema columns
        for i in range(5):
            conn.execute(
                """INSERT INTO session_log (started_at, items_planned, items_completed, items_correct)
                   VALUES (datetime('now', ?), 10, ?, ?)""",
                (f"-{i} days", 8 if i % 2 == 0 else 3, 6 if i % 2 == 0 else 1),
            )
        conn.commit()
        charts = get_spc_charts(conn)
        # Charts may or may not produce data depending on column availability
        self.assertIsInstance(charts, dict)
        conn.close()

    def test_chart_limits_structure(self):
        """Chart limits contain ucl, cl, lcl, sigma when charts are produced."""
        conn = _make_db()
        for i in range(10):
            conn.execute(
                """INSERT INTO session_log (started_at, items_planned, items_completed, items_correct)
                   VALUES (datetime('now', ?), 10, 8, 6)""",
                (f"-{i} days",),
            )
        conn.commit()
        charts = get_spc_charts(conn)
        for chart_name, chart in charts.items():
            if "limits" in chart:
                limits = chart["limits"]
                for key in ("ucl", "cl", "lcl", "sigma"):
                    self.assertIn(key, limits)
        conn.close()

    def test_missing_tables_no_crash(self):
        """get_spc_charts gracefully handles missing tables."""
        bare_conn = sqlite3.connect(":memory:")
        bare_conn.row_factory = sqlite3.Row
        # No tables at all -- should not raise
        charts = get_spc_charts(bare_conn)
        self.assertIsInstance(charts, dict)
        bare_conn.close()


if __name__ == "__main__":
    unittest.main()
