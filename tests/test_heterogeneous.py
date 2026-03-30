"""Tests for mandarin.experiments.heterogeneous — subgroup analysis."""

from mandarin.experiments.heterogeneous import (
    _get_subgroup_sql,
    _test_heterogeneity,
    _norm_sf,
)


# ── Pure function: _get_subgroup_sql ─────────────────────────


def test_subgroup_sql_hsk_band():
    sql = _get_subgroup_sql("hsk_band")
    assert sql is not None
    assert "hsk_low" in sql
    assert "hsk_mid" in sql
    assert "hsk_high" in sql


def test_subgroup_sql_engagement_band():
    sql = _get_subgroup_sql("engagement_band")
    assert sql is not None
    assert "low_engagement" in sql


def test_subgroup_sql_tenure_band():
    sql = _get_subgroup_sql("tenure_band")
    assert sql is not None
    assert "new_user" in sql
    assert "veteran" in sql


def test_subgroup_sql_unknown():
    assert _get_subgroup_sql("nonexistent") is None


# ── Pure function: _test_heterogeneity ───────────────────────


def test_heterogeneity_single_effect():
    result = _test_heterogeneity([0.5])
    assert result["q_statistic"] == 0
    assert result["heterogeneous"] is False


def test_heterogeneity_identical_effects():
    result = _test_heterogeneity([0.1, 0.1, 0.1])
    assert result["q_statistic"] == 0.0
    assert result["heterogeneous"] is False


def test_heterogeneity_varied_effects():
    result = _test_heterogeneity([0.5, -0.5, 0.3, -0.3])
    assert result["q_statistic"] > 0
    assert result["df"] == 3
    assert "interpretation" in result


def test_heterogeneity_empty():
    result = _test_heterogeneity([])
    assert result["heterogeneous"] is False


# ── Pure function: _norm_sf ──────────────────────────────────


def test_norm_sf_zero():
    assert abs(_norm_sf(0.0) - 0.5) < 0.01


def test_norm_sf_extreme():
    assert _norm_sf(10.0) == 0.0
    assert _norm_sf(-10.0) == 1.0
