"""General-purpose statistical tests and effect sizes — stdlib only.

Implements Welch's t-test, paired t-test, ANOVA, effect sizes (Cohen's d),
and non-parametric alternatives (Mann-Whitney U, Kruskal-Wallis).
Uses regularized incomplete beta function for t-distribution CDF.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers — regularized incomplete beta via continued fraction
# ---------------------------------------------------------------------------

_EPS = 1e-14
_MAX_ITER = 300


def _log_beta(a: float, b: float) -> float:
    """ln(B(a, b)) = ln(Gamma(a)) + ln(Gamma(b)) - ln(Gamma(a+b))."""
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _beta_cf(a: float, b: float, x: float) -> float:
    """Evaluate continued fraction for I_x(a, b) using modified Lentz's method.

    Uses the recurrence:
      d_{2m+1} = -(a+m)(a+b+m) x / ((a+2m)(a+2m+1))
      d_{2m}   =  m(b-m) x / ((a+2m-1)(a+2m))
    """
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0

    # Initial values for Lentz's method
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _EPS:
        d = _EPS
    d = 1.0 / d
    h = d

    for m in range(1, _MAX_ITER + 1):
        m2 = 2 * m

        # Even step  d_{2m}
        num = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + num * d
        if abs(d) < _EPS:
            d = _EPS
        c = 1.0 + num / c
        if abs(c) < _EPS:
            c = _EPS
        d = 1.0 / d
        h *= d * c

        # Odd step  d_{2m+1}
        num = -((a + m) * (qab + m) * x) / ((a + m2) * (qap + m2))
        d = 1.0 + num * d
        if abs(d) < _EPS:
            d = _EPS
        c = 1.0 + num / c
        if abs(c) < _EPS:
            c = _EPS
        d = 1.0 / d
        delta = d * c
        h *= delta

        if abs(delta - 1.0) < _EPS:
            return h

    logger.warning("_beta_cf: continued fraction did not converge (a=%s, b=%s, x=%s)", a, b, x)
    return h


def _regularized_beta(x: float, a: float, b: float) -> float:
    """Regularized incomplete beta function I_x(a, b).

    I_x(a,b) = x^a * (1-x)^b / (a * B(a,b)) * CF(a,b,x)

    Uses the symmetry relation I_x(a,b) = 1 - I_{1-x}(b,a) when
    x > (a+1)/(a+b+2) for faster convergence.
    """
    if x < 0.0 or x > 1.0:
        raise ValueError(f"x must be in [0, 1], got {x}")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0

    # Use symmetry relation for better convergence
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _regularized_beta(1.0 - x, b, a)

    log_prefix = a * math.log(x) + b * math.log(1.0 - x) - _log_beta(a, b)
    prefix = math.exp(log_prefix)
    return prefix * _beta_cf(a, b, x) / a


# ---------------------------------------------------------------------------
# Distribution CDFs
# ---------------------------------------------------------------------------


def _t_cdf(t_val: float, df: float) -> float:
    """CDF of Student's t-distribution via regularized incomplete beta function.

    Uses the identity:
        F(t, df) = 1 - 0.5 * I_x(df/2, 1/2)   for t >= 0
    where x = df / (df + t^2).
    For t < 0, F(t, df) = 1 - F(-t, df).
    """
    if df <= 0:
        return 0.5
    if t_val == 0.0:
        return 0.5

    x = df / (df + t_val * t_val)
    beta_val = 0.5 * _regularized_beta(x, df / 2.0, 0.5)

    if t_val >= 0:
        return 1.0 - beta_val
    return beta_val


def _t_sf(t_val: float, df: float) -> float:
    """Survival function (1 - CDF) for t-distribution."""
    return 1.0 - _t_cdf(t_val, df)


def _f_cdf(f_val: float, d1: float, d2: float) -> float:
    """CDF of F-distribution via regularized incomplete beta.

    F_cdf(f, d1, d2) = I_x(d1/2, d2/2) where x = d1*f / (d1*f + d2).
    """
    if f_val <= 0:
        return 0.0
    x = d1 * f_val / (d1 * f_val + d2)
    return _regularized_beta(x, d1 / 2.0, d2 / 2.0)


def _chi2_cdf(x: float, k: float) -> float:
    """CDF of chi-squared distribution.

    chi2 with k dof is the same as Gamma(k/2, 2).
    Use: P(X <= x) = regularized lower incomplete gamma = I_x(k/2, ...).
    Equivalently, chi2 CDF = I_{x/2}(k/2) = regularized_beta(x/(x+k?))...
    Actually: chi2(k) = 2*Gamma(k/2, 1/2), so
    P(X <= x; k) = regularized_gamma_lower(k/2, x/2).

    We implement the regularized lower incomplete gamma via series expansion.
    """
    if x <= 0:
        return 0.0
    return _regularized_gamma_lower(k / 2.0, x / 2.0)


def _regularized_gamma_lower(a: float, x: float) -> float:
    """Regularized lower incomplete gamma function P(a, x) = gamma(a, x) / Gamma(a).

    Uses series expansion for x < a + 1, continued fraction otherwise.
    """
    if x < 0:
        return 0.0
    if x == 0:
        return 0.0

    if x < a + 1.0:
        return _gamma_series(a, x)
    else:
        return 1.0 - _gamma_cf(a, x)


def _gamma_series(a: float, x: float) -> float:
    """Series expansion for P(a, x)."""
    term = 1.0 / a
    total = term
    for n in range(1, _MAX_ITER + 1):
        term *= x / (a + n)
        total += term
        if abs(term) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_cf(a: float, x: float) -> float:
    """Continued fraction for Q(a, x) = 1 - P(a, x) via modified Lentz's."""
    b_val = x + 1.0 - a
    c = 1.0 / _EPS
    d = 1.0 / b_val if abs(b_val) > _EPS else 1.0 / _EPS
    h = d

    for i in range(1, _MAX_ITER + 1):
        an = -i * (i - a)
        b_val += 2.0
        d = an * d + b_val
        if abs(d) < _EPS:
            d = _EPS
        c = b_val + an / c
        if abs(c) < _EPS:
            c = _EPS
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break

    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def _normal_cdf(z: float) -> float:
    """Standard normal CDF via error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _normal_ppf(p: float) -> float:
    """Inverse standard normal (percent-point function) via rational approximation.

    Abramowitz & Stegun approximation 26.2.23, accurate to ~4.5e-4.
    """
    if p <= 0:
        return -math.inf
    if p >= 1:
        return math.inf
    if p == 0.5:
        return 0.0

    if p < 0.5:
        return -_normal_ppf(1.0 - p)

    # Rational approximation for 0.5 < p < 1
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    c0 = 2.515517
    c1 = 0.802853
    c2 = 0.010328
    d1 = 1.432788
    d2 = 0.189269
    d3 = 0.001308
    return t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)


def _t_ppf(p: float, df: float) -> float:
    """Inverse t-distribution CDF via bisection search."""
    if p <= 0:
        return -math.inf
    if p >= 1:
        return math.inf
    if p == 0.5:
        return 0.0

    # Start with normal approximation
    z = _normal_ppf(p)

    # Bisection refinement
    lo, hi = z - 10.0, z + 10.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if _t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < _EPS:
            break
    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# Core helper: mean, variance, std
# ---------------------------------------------------------------------------


def _mean(x: list[float]) -> float:
    return sum(x) / len(x)


def _var(x: list[float], ddof: int = 1) -> float:
    m = _mean(x)
    return sum((xi - m) ** 2 for xi in x) / (len(x) - ddof)


def _std(x: list[float], ddof: int = 1) -> float:
    return math.sqrt(_var(x, ddof))


# ---------------------------------------------------------------------------
# Public API — t-tests
# ---------------------------------------------------------------------------


def welch_t_test(x: list[float], y: list[float]) -> dict[str, Any]:
    """Two-sample Welch's t-test (unequal variance).

    Returns: {"t": float, "df": float, "p_value": float, "ci_95": (lower, upper),
              "mean_diff": float, "se": float}
    """
    if len(x) < 2 or len(y) < 2:
        logger.warning("welch_t_test: need >= 2 observations per group")
        return {"t": 0.0, "df": 0.0, "p_value": 1.0, "ci_95": (0.0, 0.0),
                "mean_diff": 0.0, "se": 0.0}

    n1, n2 = len(x), len(y)
    m1, m2 = _mean(x), _mean(y)
    v1, v2 = _var(x), _var(y)

    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return {"t": 0.0, "df": float(n1 + n2 - 2), "p_value": 1.0,
                "ci_95": (m1 - m2, m1 - m2), "mean_diff": m1 - m2, "se": 0.0}

    t_val = (m1 - m2) / se

    # Welch-Satterthwaite degrees of freedom
    num = (v1 / n1 + v2 / n2) ** 2
    denom = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = num / denom if denom > 0 else 1.0

    # Two-tailed p-value
    p_value = 2.0 * _t_sf(abs(t_val), df)
    p_value = min(p_value, 1.0)

    # 95 % CI on the difference
    t_crit = _t_ppf(0.975, df)
    ci_lower = (m1 - m2) - t_crit * se
    ci_upper = (m1 - m2) + t_crit * se

    return {
        "t": t_val,
        "df": df,
        "p_value": p_value,
        "ci_95": (ci_lower, ci_upper),
        "mean_diff": m1 - m2,
        "se": se,
    }


def paired_t_test(x: list[float], y: list[float]) -> dict[str, Any]:
    """Paired t-test for matched samples.

    Returns: {"t": float, "df": int, "p_value": float, "ci_95": (lower, upper),
              "mean_diff": float, "se": float}
    """
    if len(x) != len(y):
        raise ValueError("paired_t_test: x and y must have the same length")
    if len(x) < 2:
        logger.warning("paired_t_test: need >= 2 paired observations")
        return {"t": 0.0, "df": 0, "p_value": 1.0, "ci_95": (0.0, 0.0),
                "mean_diff": 0.0, "se": 0.0}

    diffs = [xi - yi for xi, yi in zip(x, y, strict=False)]
    return one_sample_t_test(diffs, mu=0)


def one_sample_t_test(x: list[float], mu: float = 0) -> dict[str, Any]:
    """One-sample t-test against hypothesized mean.

    Returns: {"t": float, "df": int, "p_value": float, "ci_95": (lower, upper),
              "mean_diff": float, "se": float}
    """
    if len(x) < 2:
        logger.warning("one_sample_t_test: need >= 2 observations")
        return {"t": 0.0, "df": 0, "p_value": 1.0, "ci_95": (0.0, 0.0),
                "mean_diff": 0.0, "se": 0.0}

    n = len(x)
    m = _mean(x)
    s = _std(x)
    se = s / math.sqrt(n) if s > 0 else 0.0
    df = n - 1

    if se == 0:
        p_value = 0.0 if m != mu else 1.0
        return {"t": float("inf") if m > mu else float("-inf") if m < mu else 0.0,
                "df": df, "p_value": p_value, "ci_95": (m, m),
                "mean_diff": m - mu, "se": 0.0}

    t_val = (m - mu) / se
    p_value = 2.0 * _t_sf(abs(t_val), df)
    p_value = min(p_value, 1.0)

    t_crit = _t_ppf(0.975, df)
    ci_lower = m - t_crit * se
    ci_upper = m + t_crit * se

    return {
        "t": t_val,
        "df": df,
        "p_value": p_value,
        "ci_95": (ci_lower, ci_upper),
        "mean_diff": m - mu,
        "se": se,
    }


# ---------------------------------------------------------------------------
# Effect sizes
# ---------------------------------------------------------------------------


def cohens_d(x: list[float], y: list[float]) -> dict[str, Any]:
    """Cohen's d effect size with pooled standard deviation.

    Returns: {"d": float, "magnitude": str ("small"/"medium"/"large"/"very large")}
    """
    if len(x) < 2 or len(y) < 2:
        logger.warning("cohens_d: need >= 2 observations per group")
        return {"d": 0.0, "magnitude": "negligible"}

    n1, n2 = len(x), len(y)
    m1, m2 = _mean(x), _mean(y)
    v1, v2 = _var(x), _var(y)

    # Pooled standard deviation
    sp = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    d = (m1 - m2) / sp if sp > 0 else 0.0

    abs_d = abs(d)
    if abs_d < 0.2:
        magnitude = "negligible"
    elif abs_d < 0.5:
        magnitude = "small"
    elif abs_d < 0.8:
        magnitude = "medium"
    elif abs_d < 1.2:
        magnitude = "large"
    else:
        magnitude = "very large"

    return {"d": d, "magnitude": magnitude}


def cohens_d_ci(d: float, n1: int, n2: int, alpha: float = 0.05) -> dict[str, Any]:
    """Confidence interval on Cohen's d.

    Uses non-central t approximation:
    SE(d) ~ sqrt((n1+n2)/(n1*n2) + d^2/(2*(n1+n2)))

    Returns: {"d": float, "ci": (lower, upper), "se": float}
    """
    if n1 < 2 or n2 < 2:
        return {"d": d, "ci": (d, d), "se": 0.0}

    se = math.sqrt((n1 + n2) / (n1 * n2) + d * d / (2.0 * (n1 + n2)))
    z = _normal_ppf(1.0 - alpha / 2.0)
    ci_lower = d - z * se
    ci_upper = d + z * se

    return {"d": d, "ci": (ci_lower, ci_upper), "se": se}


def cramers_v(contingency_table: list[list[int]]) -> dict[str, Any]:
    """Cramer's V effect size for chi-squared tests.

    contingency_table: list of lists (2D matrix of counts).
    Returns: {"v": float, "chi2": float, "p_value": float, "df": int, "magnitude": str}
    """
    if not contingency_table or not contingency_table[0]:
        return {"v": 0.0, "chi2": 0.0, "p_value": 1.0, "df": 0, "magnitude": "negligible"}

    nrows = len(contingency_table)
    ncols = len(contingency_table[0])

    # Row totals, column totals, grand total
    row_totals = [sum(row) for row in contingency_table]
    col_totals = [sum(contingency_table[r][c] for r in range(nrows)) for c in range(ncols)]
    n = sum(row_totals)

    if n == 0:
        return {"v": 0.0, "chi2": 0.0, "p_value": 1.0, "df": 0, "magnitude": "negligible"}

    # Chi-squared statistic
    chi2 = 0.0
    for r in range(nrows):
        for c in range(ncols):
            expected = row_totals[r] * col_totals[c] / n
            if expected > 0:
                chi2 += (contingency_table[r][c] - expected) ** 2 / expected

    df = (nrows - 1) * (ncols - 1)
    k = min(nrows, ncols)

    # Cramer's V
    v = math.sqrt(chi2 / (n * (k - 1))) if k > 1 and n > 0 else 0.0

    # p-value from chi2 distribution
    p_value = 1.0 - _chi2_cdf(chi2, df) if df > 0 else 1.0

    if v < 0.1:
        magnitude = "negligible"
    elif v < 0.3:
        magnitude = "small"
    elif v < 0.5:
        magnitude = "medium"
    else:
        magnitude = "large"

    return {"v": v, "chi2": chi2, "p_value": p_value, "df": df, "magnitude": magnitude}


def pearsons_r_ci(r: float, n: int, alpha: float = 0.05) -> dict[str, Any]:
    """Fisher z-transformed confidence interval on Pearson's r.

    Returns: {"r": float, "ci": (lower, upper), "z_transform": float}
    """
    if n < 4:
        return {"r": r, "ci": (-1.0, 1.0), "z_transform": 0.0}

    # Clamp r to avoid domain errors
    r_clamped = max(-0.9999, min(0.9999, r))

    # Fisher z-transform
    z = 0.5 * math.log((1 + r_clamped) / (1 - r_clamped))
    se_z = 1.0 / math.sqrt(n - 3)
    z_crit = _normal_ppf(1.0 - alpha / 2.0)

    z_lower = z - z_crit * se_z
    z_upper = z + z_crit * se_z

    # Back-transform to r scale
    ci_lower = (math.exp(2 * z_lower) - 1) / (math.exp(2 * z_lower) + 1)
    ci_upper = (math.exp(2 * z_upper) - 1) / (math.exp(2 * z_upper) + 1)

    return {"r": r, "ci": (ci_lower, ci_upper), "z_transform": z}


# ---------------------------------------------------------------------------
# ANOVA
# ---------------------------------------------------------------------------


def one_way_anova(*groups: list[float]) -> dict[str, Any]:
    """One-way ANOVA F-test for 3+ group comparison.

    Returns: {"F": float, "df_between": int, "df_within": int, "p_value": float,
              "eta_squared": float}
    """
    if len(groups) < 2:
        logger.warning("one_way_anova: need >= 2 groups")
        return {"F": 0.0, "df_between": 0, "df_within": 0, "p_value": 1.0,
                "eta_squared": 0.0}

    # Filter out empty groups
    groups = [g for g in groups if len(g) > 0]
    if len(groups) < 2:
        return {"F": 0.0, "df_between": 0, "df_within": 0, "p_value": 1.0,
                "eta_squared": 0.0}

    k = len(groups)
    ns = [len(g) for g in groups]
    n_total = sum(ns)
    grand_mean = sum(sum(g) for g in groups) / n_total

    # Between-group sum of squares
    ss_between = sum(ni * (_mean(g) - grand_mean) ** 2 for g, ni in zip(groups, ns, strict=False))
    df_between = k - 1

    # Within-group sum of squares
    ss_within = sum(sum((xi - _mean(g)) ** 2 for xi in g) for g in groups)
    df_within = n_total - k

    if df_within <= 0 or df_between <= 0:
        return {"F": 0.0, "df_between": df_between, "df_within": df_within,
                "p_value": 1.0, "eta_squared": 0.0}

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within

    f_val = ms_between / ms_within if ms_within > 0 else 0.0

    p_value = 1.0 - _f_cdf(f_val, df_between, df_within)
    p_value = max(0.0, min(1.0, p_value))

    ss_total = ss_between + ss_within
    eta_squared = ss_between / ss_total if ss_total > 0 else 0.0

    return {
        "F": f_val,
        "df_between": df_between,
        "df_within": df_within,
        "p_value": p_value,
        "eta_squared": eta_squared,
    }


# ---------------------------------------------------------------------------
# Non-parametric tests
# ---------------------------------------------------------------------------


def mann_whitney_u(x: list[float], y: list[float]) -> dict[str, Any]:
    """Mann-Whitney U test (non-parametric alternative to t-test).

    For large samples (n > 20), uses normal approximation with tie correction.
    Returns: {"U": float, "z": float, "p_value": float}
    """
    if not x or not y:
        logger.warning("mann_whitney_u: empty input")
        return {"U": 0.0, "z": 0.0, "p_value": 1.0}

    n1, n2 = len(x), len(y)

    # Rank all values together
    combined = [(val, 0) for val in x] + [(val, 1) for val in y]
    combined.sort(key=lambda t: t[0])

    # Assign ranks with tie handling (average rank for ties)
    ranks: list[float] = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2.0  # 1-based average rank
        for idx in range(i, j):
            ranks[idx] = avg_rank
        i = j

    # Sum of ranks for group x
    r1 = sum(ranks[idx] for idx in range(len(combined)) if combined[idx][1] == 0)

    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    # Normal approximation (with tie correction)
    mu_u = n1 * n2 / 2.0

    # Tie correction factor
    n = n1 + n2
    tie_groups: dict[float, int] = {}
    for val, _ in combined:
        tie_groups[val] = tie_groups.get(val, 0) + 1

    tie_correction = sum(t ** 3 - t for t in tie_groups.values() if t > 1)
    sigma_u = math.sqrt(
        n1 * n2 / 12.0 * ((n + 1) - tie_correction / (n * (n - 1)))
    ) if n > 1 else 0.0

    if sigma_u > 0:
        z = (u - mu_u) / sigma_u
        # Two-tailed p using normal approximation
        p_value = 2.0 * (1.0 - _normal_cdf(abs(z)))
    else:
        z = 0.0
        p_value = 1.0

    return {"U": u, "z": z, "p_value": min(p_value, 1.0)}


def kruskal_wallis(*groups: list[float]) -> dict[str, Any]:
    """Kruskal-Wallis H test (non-parametric ANOVA).

    Returns: {"H": float, "df": int, "p_value": float}
    """
    groups = [g for g in groups if len(g) > 0]
    if len(groups) < 2:
        logger.warning("kruskal_wallis: need >= 2 non-empty groups")
        return {"H": 0.0, "df": 0, "p_value": 1.0}

    k = len(groups)
    ns = [len(g) for g in groups]
    n_total = sum(ns)

    # Combine and rank all observations
    combined: list[tuple[float, int]] = []
    for group_idx, g in enumerate(groups):
        for val in g:
            combined.append((val, group_idx))
    combined.sort(key=lambda t: t[0])

    # Assign average ranks for ties
    ranks: list[float] = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2.0
        for idx in range(i, j):
            ranks[idx] = avg_rank
        i = j

    # Sum of ranks per group
    rank_sums = [0.0] * k
    for idx, (_, group_idx) in enumerate(combined):
        rank_sums[group_idx] += ranks[idx]

    # H statistic
    h = (12.0 / (n_total * (n_total + 1))) * sum(
        rs ** 2 / ni for rs, ni in zip(rank_sums, ns, strict=False)
    ) - 3.0 * (n_total + 1)

    # Tie correction
    tie_groups: dict[float, int] = {}
    for val, _ in combined:
        tie_groups[val] = tie_groups.get(val, 0) + 1

    tie_correction_denom = 1.0 - sum(
        t ** 3 - t for t in tie_groups.values() if t > 1
    ) / (n_total ** 3 - n_total) if n_total > 1 else 1.0

    if tie_correction_denom > 0:
        h /= tie_correction_denom

    df = k - 1
    p_value = 1.0 - _chi2_cdf(h, df) if h > 0 else 1.0
    p_value = max(0.0, min(1.0, p_value))

    return {"H": h, "df": df, "p_value": p_value}
