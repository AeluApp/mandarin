"""Tests for half-life retention model, observability, and integration.

Covers:
- Core retention math (predict_recall, update_half_life, update_difficulty)
- Scheduling helpers (days_until_threshold, scheduling_priority)
- Retention stats computation (compute_retention_stats)
- Session metrics (compute_session_metrics, save_session_metrics)
- Integration with record_attempt (half_life/difficulty updated)
- Forecast includes retention data
- Report includes retention section
- Session summary includes retention
"""

import sys
import os
import tempfile
import math
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mandarin import db
from mandarin.db.core import init_db, _migrate
from mandarin.db.content import insert_content_item
from mandarin.db.progress import record_attempt
from mandarin.db.session import start_session
from mandarin.retention import (
    predict_recall, update_half_life, update_difficulty,
    days_until_threshold, scheduling_priority,
    compute_retention_stats, compute_session_metrics, save_session_metrics,
    RECALL_THRESHOLD, MIN_HALF_LIFE, MAX_HALF_LIFE, INITIAL_HALF_LIFE,
)


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = init_db(path)
    _migrate(conn)
    conn.execute("INSERT OR IGNORE INTO learner_profile (id) VALUES (1)")
    conn.commit()
    return conn


def _add_items(conn, n, hsk_level=1):
    ids = []
    for i in range(n):
        item_id = insert_content_item(
            conn, hanzi=f"\u6d4b{i}_{hsk_level}", pinyin=f"ce{i}",
            english=f"test{i}", hsk_level=hsk_level,
        )
        ids.append(item_id)
    return ids


# ── Core math ──

def test_predict_recall_at_zero():
    """At 0 days since review, recall should be 1.0."""
    assert predict_recall(1.0, 0) == 1.0
    assert predict_recall(10.0, 0) == 1.0


def test_predict_recall_at_half_life():
    """At exactly the half-life, recall should be 0.5."""
    p = predict_recall(5.0, 5.0)
    assert abs(p - 0.5) < 0.001, f"expected ~0.5, got {p}"


def test_predict_recall_decay():
    """Recall should decrease as days_since_review increases."""
    p1 = predict_recall(3.0, 1.0)
    p2 = predict_recall(3.0, 3.0)
    p3 = predict_recall(3.0, 6.0)
    assert p1 > p2 > p3 > 0
    assert abs(p2 - 0.5) < 0.001  # At half-life


def test_predict_recall_edge_cases():
    """Edge cases: zero/negative half-life."""
    assert predict_recall(0, 5) == 0.0
    assert predict_recall(-1, 5) == 0.0
    assert predict_recall(5, -1) == 1.0


def test_update_half_life_correct():
    """Correct answer should increase half-life."""
    new_hl = update_half_life(1.0, True, 1.0, 0.5)
    assert new_hl > 1.0, f"correct answer should increase HL, got {new_hl}"


def test_update_half_life_incorrect():
    """Incorrect answer should decrease half-life."""
    new_hl = update_half_life(5.0, False, 1.0, 0.5)
    assert new_hl < 5.0, f"incorrect answer should decrease HL, got {new_hl}"


def test_update_half_life_clamped():
    """Half-life should be clamped to [MIN_HALF_LIFE, MAX_HALF_LIFE]."""
    # Very wrong, very hard item
    new_hl = update_half_life(MIN_HALF_LIFE, False, 0, 1.0)
    assert new_hl >= MIN_HALF_LIFE

    # Massively correct, easy item, way overdue
    new_hl = update_half_life(MAX_HALF_LIFE, True, MAX_HALF_LIFE * 2, 0.0)
    assert new_hl <= MAX_HALF_LIFE


def test_update_half_life_lag_ratio():
    """Overdue reviews (high lag ratio) should give bigger boost."""
    early_hl = update_half_life(5.0, True, 2.0, 0.3)  # reviewed early
    ontime_hl = update_half_life(5.0, True, 5.0, 0.3)  # reviewed on time
    late_hl = update_half_life(5.0, True, 10.0, 0.3)   # reviewed late

    assert late_hl > ontime_hl >= early_hl, \
        f"later reviews should boost more: early={early_hl}, on={ontime_hl}, late={late_hl}"


def test_update_difficulty_correct_decreases():
    """Correct answer should decrease difficulty."""
    new_diff = update_difficulty(0.5, True, 0.7)
    assert new_diff < 0.5, f"correct should decrease diff, got {new_diff}"


def test_update_difficulty_incorrect_increases():
    """Incorrect answer should increase difficulty."""
    new_diff = update_difficulty(0.5, False, 0.7)
    assert new_diff > 0.5, f"incorrect should increase diff, got {new_diff}"


def test_update_difficulty_asymmetric():
    """Errors should move difficulty more than correct answers."""
    d_correct = abs(update_difficulty(0.5, True, 0.5) - 0.5)
    d_incorrect = abs(update_difficulty(0.5, False, 0.5) - 0.5)
    assert d_incorrect > d_correct, \
        f"errors should impact more: correct delta={d_correct}, incorrect delta={d_incorrect}"


def test_update_difficulty_clamped():
    """Difficulty should stay in [0.05, 0.95]."""
    # Push very low
    d = 0.1
    for _ in range(50):
        d = update_difficulty(d, True, 0.9)
    assert d >= 0.05

    # Push very high
    d = 0.9
    for _ in range(50):
        d = update_difficulty(d, False, 0.1)
    assert d <= 0.95


def test_update_difficulty_surprise_effect():
    """High-confidence errors should increase difficulty more than low-confidence ones."""
    # High predicted recall but got it wrong → surprise → bigger increase
    d_surprise = update_difficulty(0.5, False, 0.9)
    d_expected = update_difficulty(0.5, False, 0.3)
    assert d_surprise > d_expected, \
        f"surprise error should increase more: surprise={d_surprise}, expected={d_expected}"


# ── Scheduling helpers ──

def test_days_until_threshold():
    """days_until_threshold should match the formula Δ = -h * log2(p)."""
    h = 5.0
    threshold = 0.85
    expected = -h * math.log2(threshold)
    result = days_until_threshold(h, threshold)
    assert abs(result - expected) < 0.001, f"expected {expected}, got {result}"


def test_days_until_threshold_edge():
    """Edge cases should return 0."""
    assert days_until_threshold(0, 0.85) == 0.0
    assert days_until_threshold(5.0, 0) == 0.0
    assert days_until_threshold(5.0, 1.0) == 0.0


def test_scheduling_priority():
    """Higher priority for lower recall and higher difficulty."""
    # Item with low recall, high difficulty
    p1 = scheduling_priority(1.0, 5.0, 0.9)
    # Item with high recall, low difficulty
    p2 = scheduling_priority(10.0, 1.0, 0.1)
    assert p1 > p2, f"urgent item should have higher priority: {p1} vs {p2}"


# ── Retention stats ──

def test_compute_retention_stats_empty():
    """compute_retention_stats on empty DB should return zeros."""
    conn = _fresh_db()
    _add_items(conn, 5)
    try:
        stats = compute_retention_stats(conn)
        assert stats["total_items"] == 0
        assert stats["retention_pct"] == 0.0
        assert stats["avg_recall"] == 0.0
    finally:
        conn.close()


def test_compute_retention_stats_with_data():
    """compute_retention_stats with progress data should return valid stats."""
    conn = _fresh_db()
    ids = _add_items(conn, 5)
    sid = start_session(conn)

    for item_id in ids:
        record_attempt(conn, item_id, "reading", True, session_id=sid,
                       drill_type="mc")

    stats = compute_retention_stats(conn)
    assert stats["total_items"] > 0
    assert 0 <= stats["retention_pct"] <= 100
    assert 0 <= stats["avg_recall"] <= 1.0
    assert stats["avg_half_life"] > 0
    assert isinstance(stats["by_modality"], dict)
    assert isinstance(stats["by_hsk"], dict)
    conn.close()


def test_compute_retention_stats_per_modality():
    """Retention stats should break down by modality."""
    conn = _fresh_db()
    ids = _add_items(conn, 6)
    sid = start_session(conn)

    # Reading attempts
    for item_id in ids[:3]:
        record_attempt(conn, item_id, "reading", True, session_id=sid,
                       drill_type="mc")
    # Listening attempts
    for item_id in ids[3:]:
        record_attempt(conn, item_id, "listening", True, session_id=sid,
                       drill_type="listening_gist")

    stats = compute_retention_stats(conn)
    assert "reading" in stats["by_modality"]
    assert "listening" in stats["by_modality"]
    assert stats["by_modality"]["reading"]["count"] >= 3
    assert stats["by_modality"]["listening"]["count"] >= 3
    conn.close()


# ── Session metrics ──

def test_compute_session_metrics():
    """compute_session_metrics should return valid structure."""
    conn = _fresh_db()
    ids = _add_items(conn, 5)
    sid = start_session(conn)

    for item_id in ids:
        record_attempt(conn, item_id, "reading", True, session_id=sid,
                       drill_type="mc")

    metrics = compute_session_metrics(conn, sid)
    assert isinstance(metrics, dict)
    assert "recall_above_threshold" in metrics
    assert "recall_below_threshold" in metrics
    assert "avg_recall" in metrics
    assert "items_strengthened" in metrics
    assert "items_weakened" in metrics
    assert "transfer_events" in metrics
    conn.close()


def test_save_session_metrics():
    """save_session_metrics should persist without crash."""
    conn = _fresh_db()
    ids = _add_items(conn, 3)
    sid = start_session(conn)

    record_attempt(conn, ids[0], "reading", True, session_id=sid,
                   drill_type="mc")

    metrics = compute_session_metrics(conn, sid)
    save_session_metrics(conn, sid, metrics)

    # Verify saved
    row = conn.execute(
        "SELECT * FROM session_metrics WHERE session_id = ?", (sid,)
    ).fetchone()
    assert row is not None
    assert row["session_id"] == sid
    conn.close()


def test_session_metrics_strengthened_weakened():
    """Session metrics should count strengthened/weakened items from error log."""
    conn = _fresh_db()
    ids = _add_items(conn, 4)
    sid = start_session(conn)

    # 2 items all correct (strengthened) — error_log won't have entries for these
    for item_id in ids[:2]:
        record_attempt(conn, item_id, "reading", True, session_id=sid,
                       drill_type="mc")

    # 2 items all wrong (weakened) — will appear in error_log
    for item_id in ids[2:]:
        record_attempt(conn, item_id, "reading", False, session_id=sid,
                       drill_type="mc", error_type="vocab",
                       user_answer="wrong", expected_answer="right")

    metrics = compute_session_metrics(conn, sid)
    # Only items with error_log entries are counted by the query
    # Items with all errors (correct_count=0) → weakened
    assert metrics["items_weakened"] >= 2, \
        f"expected >=2 weakened, got {metrics['items_weakened']}"
    conn.close()


# ── Integration with record_attempt ──

def test_record_attempt_updates_half_life():
    """record_attempt should update half_life_days in progress table."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    sid = start_session(conn)
    item_id = ids[0]

    record_attempt(conn, item_id, "reading", True, session_id=sid,
                   drill_type="mc")

    row = conn.execute(
        "SELECT half_life_days, difficulty, last_p_recall FROM progress "
        "WHERE content_item_id = ? AND modality = 'reading'",
        (item_id,)
    ).fetchone()

    assert row is not None
    assert row["half_life_days"] is not None
    assert row["half_life_days"] > 0
    assert row["difficulty"] is not None
    assert 0 <= row["difficulty"] <= 1
    assert row["last_p_recall"] is not None
    conn.close()


def test_record_attempt_half_life_increases_on_correct():
    """Correct answers should increase half_life over time."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    sid = start_session(conn)
    item_id = ids[0]

    # First attempt
    record_attempt(conn, item_id, "reading", True, session_id=sid,
                   drill_type="mc")
    row1 = conn.execute(
        "SELECT half_life_days FROM progress WHERE content_item_id = ?",
        (item_id,)
    ).fetchone()
    hl1 = row1["half_life_days"]

    # Simulate next day
    conn.execute(
        "UPDATE progress SET last_review_date = ? WHERE content_item_id = ?",
        ((date.today() - timedelta(days=1)).isoformat(), item_id)
    )
    conn.commit()

    # Second correct attempt
    record_attempt(conn, item_id, "reading", True, session_id=sid,
                   drill_type="mc")
    row2 = conn.execute(
        "SELECT half_life_days FROM progress WHERE content_item_id = ?",
        (item_id,)
    ).fetchone()
    hl2 = row2["half_life_days"]

    assert hl2 > hl1, f"HL should increase after correct: {hl1} → {hl2}"
    conn.close()


def test_record_attempt_half_life_decreases_on_incorrect():
    """Incorrect answers should decrease half_life."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    sid = start_session(conn)
    item_id = ids[0]

    # Build up half-life first
    for _ in range(3):
        record_attempt(conn, item_id, "reading", True, session_id=sid,
                       drill_type="mc")
        conn.execute(
            "UPDATE progress SET last_review_date = ? WHERE content_item_id = ?",
            ((date.today() - timedelta(days=1)).isoformat(), item_id)
        )
        conn.commit()

    row_before = conn.execute(
        "SELECT half_life_days FROM progress WHERE content_item_id = ?",
        (item_id,)
    ).fetchone()
    hl_before = row_before["half_life_days"]

    # Wrong answer
    record_attempt(conn, item_id, "reading", False, session_id=sid,
                   drill_type="mc", error_type="vocab",
                   user_answer="wrong", expected_answer="right")
    row_after = conn.execute(
        "SELECT half_life_days FROM progress WHERE content_item_id = ?",
        (item_id,)
    ).fetchone()
    hl_after = row_after["half_life_days"]

    assert hl_after < hl_before, f"HL should decrease after incorrect: {hl_before} → {hl_after}"
    conn.close()


def test_record_attempt_partial_confidence_no_hl_change():
    """Unknown confidence applies dampened HL update (not full, not zero)."""
    conn = _fresh_db()
    ids = _add_items(conn, 1)
    sid = start_session(conn)
    item_id = ids[0]

    # Initial attempt
    record_attempt(conn, item_id, "reading", True, session_id=sid,
                   drill_type="mc")
    row1 = conn.execute(
        "SELECT half_life_days, difficulty FROM progress WHERE content_item_id = ?",
        (item_id,)
    ).fetchone()
    hl1, diff1 = row1["half_life_days"], row1["difficulty"]

    # "unknown" confidence attempt — should apply dampened update
    record_attempt(conn, item_id, "reading", True, session_id=sid,
                   drill_type="mc", confidence="unknown")
    row2 = conn.execute(
        "SELECT half_life_days, difficulty FROM progress WHERE content_item_id = ?",
        (item_id,)
    ).fetchone()
    hl2, diff2 = row2["half_life_days"], row2["difficulty"]

    # Unknown confidence now applies a dampened update (treats as failed recall)
    assert hl2 != hl1, f"unknown confidence should apply dampened HL update: {hl1} → {hl2}"
    assert hl2 < hl1, f"unknown confidence should reduce HL (failed recall): {hl1} → {hl2}"
    assert diff2 != diff1, f"unknown confidence should apply dampened difficulty update"
    conn.close()


# ── Forecast integration ──

def test_forecast_includes_retention():
    """project_forecast should include retention key when data exists."""
    conn = _fresh_db()
    ids = _add_items(conn, 10)
    sid = start_session(conn)

    for item_id in ids:
        record_attempt(conn, item_id, "reading", True, session_id=sid,
                       drill_type="mc")

    from mandarin.diagnostics import project_forecast
    fc = project_forecast(conn)

    assert "retention" in fc, "forecast should include retention key"
    if fc["retention"] is not None:
        ret = fc["retention"]
        assert "total_items" in ret
        assert "retention_pct" in ret
        assert "avg_recall" in ret
        assert "avg_half_life" in ret
    conn.close()


def test_forecast_no_retention_on_fresh_db():
    """Forecast on fresh DB should have retention=None."""
    conn = _fresh_db()
    _add_items(conn, 5)

    from mandarin.diagnostics import project_forecast
    fc = project_forecast(conn)
    assert fc.get("retention") is None
    conn.close()


# ── Report integration ──

def test_report_includes_memory_model():
    """Report should include Memory Model section when retention data exists."""
    conn = _fresh_db()
    ids = _add_items(conn, 10)

    # Need enough sessions for report to reach retention section
    for i in range(3):
        sid = start_session(conn)
        for item_id in ids[:5]:
            record_attempt(conn, item_id, "reading", True, session_id=sid,
                           drill_type="mc")
        db.end_session(conn, sid, items_completed=5, items_correct=5)

    from mandarin.reports import generate_status_report
    report = generate_status_report(conn)

    assert "Memory Model" in report, f"report should include Memory Model section:\n{report}"
    assert "recall" in report.lower()
    conn.close()


# ── Constants sanity ──

def test_retention_constants():
    """Retention constants should have sane values."""
    assert 0 < RECALL_THRESHOLD < 1
    assert MIN_HALF_LIFE > 0
    assert MAX_HALF_LIFE > MIN_HALF_LIFE
    assert MIN_HALF_LIFE <= INITIAL_HALF_LIFE <= MAX_HALF_LIFE


# ── Wilson CI Tests ─────────────────────────────────────────────────────────

from mandarin.retention import wilson_ci


def test_wilson_ci_zero_total():
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_ci_all_success():
    low, high = wilson_ci(100, 100)
    assert high == 1.0
    assert low > 0.9


def test_wilson_ci_no_success():
    low, high = wilson_ci(0, 100)
    assert low == 0.0
    assert high > 0.0
    assert high < 0.1


def test_wilson_ci_half():
    low, high = wilson_ci(50, 100)
    assert low < 0.5 < high
    # Roughly symmetric around 0.5
    assert abs((low + high) / 2 - 0.5) < 0.05


def test_wilson_ci_small_sample_wider():
    low_small, high_small = wilson_ci(1, 2)
    low_large, high_large = wilson_ci(50, 100)
    width_small = high_small - low_small
    width_large = high_large - low_large
    assert width_small > width_large


def test_wilson_ci_bounds_always_valid():
    """Lower and upper must satisfy 0 <= lower <= p <= upper <= 1."""
    test_cases = [(0, 10), (3, 10), (10, 10), (1, 1), (7, 15), (50, 100)]
    for s, t in test_cases:
        low, high = wilson_ci(s, t)
        assert 0.0 <= low <= high <= 1.0, f"Failed for ({s}, {t}): ({low}, {high})"


# ── Calibration tests ─────────────────────────────────────────────────────────

from mandarin.retention import compute_calibration


class TestComputeCalibration:
    """Tests for compute_calibration() — predicted recall vs actual accuracy."""

    @staticmethod
    def _insert_progress_row(conn, user_id, item_id, correct, attempts, p_recall):
        """Insert a content_item and matching progress row."""
        conn.execute(
            "INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english) VALUES (?, ?, ?, ?)",
            (item_id, f"\u6d4b{item_id}", f"ce{item_id}", f"test{item_id}"),
        )
        conn.execute(
            "INSERT INTO progress (user_id, content_item_id, total_correct, total_attempts, "
            "last_p_recall, modality) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, item_id, correct, attempts, p_recall, "reading"),
        )
        conn.commit()

    def test_empty_data(self, test_db):
        """No matching rows → empty bins, None brier_score."""
        conn, _path = test_db
        result = compute_calibration(conn, n_bins=5, user_id=1)
        assert result["bins"] == []
        assert result["brier_score"] is None
        assert result["n_items"] == 0
        assert result["calibration_error"] is None

    def test_with_data(self, test_db):
        """10+ progress rows with various last_p_recall → bins, brier_score, calibration_error."""
        conn, _path = test_db
        # Insert 12 progress rows with varying predicted recalls and accuracy
        test_data = [
            # (item_id, total_correct, total_attempts, last_p_recall)
            (100, 2, 3, 0.1),
            (101, 1, 3, 0.15),
            (102, 3, 5, 0.3),
            (103, 2, 4, 0.35),
            (104, 4, 5, 0.5),
            (105, 3, 5, 0.55),
            (106, 5, 6, 0.7),
            (107, 6, 7, 0.75),
            (108, 8, 9, 0.85),
            (109, 9, 10, 0.9),
            (110, 7, 8, 0.6),
            (111, 10, 10, 0.95),
        ]
        for item_id, correct, attempts, p_recall in test_data:
            self._insert_progress_row(conn, 1, item_id, correct, attempts, p_recall)

        result = compute_calibration(conn, n_bins=5, user_id=1)
        assert len(result["bins"]) > 0
        assert result["n_items"] == 12
        assert result["brier_score"] is not None
        assert result["brier_score"] >= 0
        assert result["calibration_error"] is not None
        assert result["calibration_error"] >= 0
        # Each bin should have predicted, actual, count
        for b in result["bins"]:
            assert "predicted" in b
            assert "actual" in b
            assert "count" in b
            assert b["count"] > 0
            assert 0 <= b["predicted"] <= 1
            assert 0 <= b["actual"] <= 1

    def test_perfectly_calibrated(self, test_db):
        """When predicted recall matches actual accuracy, brier_score should be near 0."""
        conn, _path = test_db
        # Insert items where predicted recall closely matches actual accuracy
        calibrated_data = [
            # (item_id, total_correct, total_attempts, last_p_recall)
            # actual = correct/attempts matches p_recall
            (200, 2, 10, 0.2),
            (201, 2, 10, 0.2),
            (202, 5, 10, 0.5),
            (203, 5, 10, 0.5),
            (204, 8, 10, 0.8),
            (205, 8, 10, 0.8),
        ]
        for item_id, correct, attempts, p_recall in calibrated_data:
            self._insert_progress_row(conn, 1, item_id, correct, attempts, p_recall)

        result = compute_calibration(conn, n_bins=5, user_id=1)
        assert result["brier_score"] is not None
        assert result["brier_score"] < 0.01, \
            f"perfectly calibrated predictions should have near-zero brier: {result['brier_score']}"
        assert result["calibration_error"] is not None
        assert result["calibration_error"] < 0.01, \
            f"perfectly calibrated should have near-zero cal error: {result['calibration_error']}"

    def test_different_n_bins(self, test_db):
        """Different n_bins parameter should produce different bin counts."""
        conn, _path = test_db
        test_data = [
            (300, 3, 5, 0.1),
            (301, 2, 4, 0.3),
            (302, 4, 5, 0.5),
            (303, 5, 6, 0.7),
            (304, 9, 10, 0.9),
            (305, 1, 3, 0.2),
            (306, 7, 8, 0.8),
            (307, 4, 6, 0.4),
            (308, 6, 7, 0.6),
            (309, 8, 9, 0.85),
        ]
        for item_id, correct, attempts, p_recall in test_data:
            self._insert_progress_row(conn, 1, item_id, correct, attempts, p_recall)

        result_3 = compute_calibration(conn, n_bins=3, user_id=1)
        result_10 = compute_calibration(conn, n_bins=10, user_id=1)

        # Both should return valid results with same n_items
        assert result_3["n_items"] == 10
        assert result_10["n_items"] == 10
        # More bins can produce more non-empty bin entries (up to available data)
        assert len(result_10["bins"]) >= len(result_3["bins"]), \
            f"10 bins should produce >= bin entries than 3 bins: {len(result_10['bins'])} vs {len(result_3['bins'])}"

    def test_rows_below_threshold_excluded(self, test_db):
        """Rows with total_attempts < 2 or last_p_recall IS NULL are excluded."""
        conn, _path = test_db
        # Row with only 1 attempt — should be excluded
        self._insert_progress_row(conn, 1, 400, 1, 1, 0.5)
        # Row with NULL last_p_recall — insert manually
        conn.execute(
            "INSERT OR IGNORE INTO content_item (id, hanzi, pinyin, english) VALUES (?, ?, ?, ?)",
            (401, "\u6d4b401", "ce401", "test401"),
        )
        conn.execute(
            "INSERT INTO progress (user_id, content_item_id, total_correct, total_attempts, "
            "last_p_recall, modality) VALUES (?, ?, ?, ?, ?, ?)",
            (1, 401, 3, 5, None, "reading"),
        )
        conn.commit()

        result = compute_calibration(conn, n_bins=5, user_id=1)
        assert result["n_items"] == 0
        assert result["bins"] == []


# ── Retention edge cases ──────────────────────────────────────────────────────


class TestRetentionEdgeCases:
    """Edge case tests for retention functions."""

    def test_update_half_life_zero_input(self):
        """update_half_life with zero half-life should clamp to MIN_HALF_LIFE."""
        # Zero half-life, correct answer
        new_hl = update_half_life(0.0, True, 1.0, 0.5)
        assert new_hl >= MIN_HALF_LIFE, \
            f"zero input should clamp to at least MIN_HALF_LIFE ({MIN_HALF_LIFE}), got {new_hl}"

        # Zero half-life, incorrect answer
        new_hl = update_half_life(0.0, False, 1.0, 0.5)
        assert new_hl >= MIN_HALF_LIFE, \
            f"zero input should clamp to at least MIN_HALF_LIFE ({MIN_HALF_LIFE}), got {new_hl}"

    def test_update_half_life_negative_input(self):
        """update_half_life with negative half-life should clamp to MIN_HALF_LIFE."""
        new_hl = update_half_life(-5.0, True, 1.0, 0.5)
        assert new_hl >= MIN_HALF_LIFE

        new_hl = update_half_life(-5.0, False, 1.0, 0.5)
        assert new_hl >= MIN_HALF_LIFE

    def test_compute_retention_stats_malformed_date(self, test_db):
        """compute_retention_stats should skip rows with unparseable review dates."""
        conn, _path = test_db
        # Insert a content item and progress row with a malformed date
        conn.execute(
            "INSERT INTO content_item (id, hanzi, pinyin, english) VALUES (?, ?, ?, ?)",
            (500, "\u6d4b500", "ce500", "test500"),
        )
        conn.execute(
            "INSERT INTO progress (user_id, content_item_id, modality, half_life_days, "
            "difficulty, last_review_date, total_attempts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 500, "reading", 5.0, 0.5, "not-a-date", 3),
        )
        conn.commit()

        # Should not raise, should skip the malformed row gracefully
        stats = compute_retention_stats(conn)
        assert stats["total_items"] == 0  # The malformed row is skipped

    def test_compute_retention_stats_none_date(self, test_db):
        """compute_retention_stats should handle None review date via SQL filter."""
        conn, _path = test_db
        conn.execute(
            "INSERT INTO content_item (id, hanzi, pinyin, english) VALUES (?, ?, ?, ?)",
            (501, "\u6d4b501", "ce501", "test501"),
        )
        conn.execute(
            "INSERT INTO progress (user_id, content_item_id, modality, half_life_days, "
            "difficulty, last_review_date, total_attempts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 501, "reading", 5.0, 0.5, None, 3),
        )
        conn.commit()

        stats = compute_retention_stats(conn)
        # NULL last_review_date is filtered out by the WHERE clause
        assert stats["total_items"] == 0

    def test_compute_session_metrics_transfer_events(self, test_db):
        """Transfer events should count items correct in a new modality."""
        conn, _path = test_db
        from mandarin.db.content import insert_content_item
        from mandarin.db.progress import record_attempt
        from mandarin.db.session import start_session

        # Create item
        item_id = insert_content_item(conn, hanzi="\u8bfb", pinyin="du",
                                       english="read", hsk_level=1)

        # Build up reading progress first (multiple attempts so it's established)
        sid1 = start_session(conn)
        for _ in range(3):
            record_attempt(conn, item_id, "reading", True, session_id=sid1,
                           drill_type="mc")
        # Backdate reading progress so it's not from today
        conn.execute(
            "UPDATE progress SET last_review_date = ? "
            "WHERE content_item_id = ? AND modality = 'reading'",
            ((date.today() - timedelta(days=5)).isoformat(), item_id),
        )
        conn.commit()

        # Now do a listening attempt today (first time in this modality)
        sid2 = start_session(conn)
        record_attempt(conn, item_id, "listening", True, session_id=sid2,
                       drill_type="listening_gist")

        metrics = compute_session_metrics(conn, sid2)
        # The item was correct in listening (new modality) with reading history
        assert metrics["transfer_events"] >= 1, \
            f"expected >=1 transfer event, got {metrics['transfer_events']}"


