"""Tests for mandarin.experiments.bayesian — pure-function Bayesian analysis."""

from mandarin.experiments.bayesian import (
    _beta_mean,
    _beta_mode,
    _beta_sample,
    _beta_credible_interval,
    _norm_sf,
    benjamini_hochberg,
    compute_bayesian_results,
    test_equivalence as tost_equivalence,
)
import random


# ── Beta helpers ──────────────────────────────────────────────


def test_beta_mean_uniform():
    assert _beta_mean(1.0, 1.0) == 0.5


def test_beta_mean_skewed():
    assert abs(_beta_mean(10.0, 2.0) - 10 / 12) < 1e-9


def test_beta_mean_zero_params():
    assert _beta_mean(0.0, 0.0) == 0.5


def test_beta_mode_uniform_fallback():
    # alpha=1, beta=1: mode undefined, falls back to mean
    assert _beta_mode(1.0, 1.0) == 0.5


def test_beta_mode_peaked():
    # Beta(10, 2): mode = 9/10 = 0.9
    assert abs(_beta_mode(10.0, 2.0) - 0.9) < 1e-9


def test_beta_sample_invalid_params():
    rng = random.Random(42)
    assert _beta_sample(-1, 1, rng) == 0.5
    assert _beta_sample(1, -1, rng) == 0.5


def test_beta_sample_valid():
    rng = random.Random(42)
    s = _beta_sample(10.0, 2.0, rng)
    assert 0.0 < s < 1.0


def test_beta_credible_interval_bounds():
    lo, hi = _beta_credible_interval(50.0, 50.0)
    assert 0.0 < lo < 0.5 < hi < 1.0
    assert hi - lo < 0.3  # should be narrow for n=100


# ── Normal survival ──────────────────────────────────────────


def test_norm_sf_zero():
    assert abs(_norm_sf(0.0) - 0.5) < 0.01


def test_norm_sf_large_positive():
    assert _norm_sf(10.0) == 0.0


def test_norm_sf_large_negative():
    assert _norm_sf(-10.0) == 1.0


def test_norm_sf_symmetry():
    assert abs(_norm_sf(1.96) + _norm_sf(-1.96) - 1.0) < 1e-6


# ── compute_bayesian_results ─────────────────────────────────


def test_compute_bayesian_too_few_variants():
    result = compute_bayesian_results({"a": {"successes": 10, "trials": 100}})
    assert "error" in result


def test_compute_bayesian_empty():
    result = compute_bayesian_results({})
    assert "error" in result


def test_compute_bayesian_two_variants():
    data = {
        "control": {"successes": 40, "trials": 100},
        "treatment": {"successes": 60, "trials": 100},
    }
    result = compute_bayesian_results(data, seed=42)
    assert "posteriors" in result
    assert "control" in result["posteriors"]
    assert "treatment" in result["posteriors"]
    assert "prob_best" in result
    assert "expected_loss" in result
    assert "recommended_variant" in result
    assert result["prob_treatment_wins"] is not None
    assert isinstance(result["can_stop"], bool)
    # Treatment clearly better — should have high prob_best
    assert result["prob_best"]["treatment"] > 0.9


def test_compute_bayesian_percentage_input():
    data = {
        "control": {"users": 100, "completion_rate": 40.0},
        "treatment": {"users": 100, "completion_rate": 60.0},
    }
    result = compute_bayesian_results(data, seed=42)
    assert "posteriors" in result
    assert result["posteriors"]["control"]["trials"] == 100


def test_compute_bayesian_invalid_data_format():
    data = {
        "a": {"foo": 1},
        "b": {"bar": 2},
    }
    result = compute_bayesian_results(data)
    assert "error" in result


def test_compute_bayesian_stopping():
    # Overwhelmingly clear winner should allow stopping
    data = {
        "control": {"successes": 10, "trials": 1000},
        "treatment": {"successes": 500, "trials": 1000},
    }
    result = compute_bayesian_results(data, seed=42)
    assert result["can_stop"] is True


# ── Benjamini-Hochberg ───────────────────────────────────────


def test_bh_empty():
    assert benjamini_hochberg([]) == []


def test_bh_all_significant():
    pvals = [("a", 0.001), ("b", 0.005), ("c", 0.01)]
    results = benjamini_hochberg(pvals, alpha=0.05)
    assert len(results) == 3
    assert all(r["significant"] for r in results)


def test_bh_none_significant():
    pvals = [("a", 0.8), ("b", 0.9)]
    results = benjamini_hochberg(pvals, alpha=0.05)
    assert not any(r["significant"] for r in results)


def test_bh_monotonicity():
    pvals = [("a", 0.01), ("b", 0.04), ("c", 0.03)]
    results = benjamini_hochberg(pvals, alpha=0.05)
    sorted_by_rank = sorted(results, key=lambda r: r["rank"])
    for i in range(len(sorted_by_rank) - 1):
        assert sorted_by_rank[i]["adjusted_p"] <= sorted_by_rank[i + 1]["adjusted_p"]


# ── TOST equivalence ─────────────────────────────────────────


def test_equivalence_identical():
    # Need large n for TOST to confirm equivalence within ±0.02 margin
    result = tost_equivalence(0.5, 10000, 0.5, 10000)
    assert result["equivalent"] is True
    assert result["difference"] == 0.0


def test_equivalence_clearly_different():
    result = tost_equivalence(0.3, 1000, 0.7, 1000, margin=0.02)
    assert result["equivalent"] is False


def test_equivalence_zero_variance():
    result = tost_equivalence(0.0, 100, 0.0, 100)
    assert result["equivalent"] is True
    assert "Zero variance" in result["interpretation"]


def test_equivalence_borderline():
    result = tost_equivalence(0.50, 500, 0.51, 500, margin=0.02)
    assert "tost_p_value" in result
    assert "ci_90" in result
    assert len(result["ci_90"]) == 2
