"""Rosenbaum sensitivity analysis — how much hidden confounding could overturn a result.

Uses only stdlib math.  The Gamma approximation gives a quick, interpretable
bound without requiring full matching or permutation inference.
"""

from __future__ import annotations

import math


# Z_alpha for two-sided alpha = 0.05
_Z_ALPHA = 1.96


def compute_sensitivity(effect_size: float, p_value: float, n: int) -> dict:
    """Compute Rosenbaum sensitivity bounds.

    For a given effect size and sample size, estimate the maximum Gamma (odds
    ratio of differential treatment assignment due to an unobserved confounder)
    at which the result would still be statistically significant.

    Approximation::

        Gamma ~ exp(2 * |effect_size| * sqrt(n) / Z_alpha)

    Args:
        effect_size: Observed effect size (e.g. Cohen's d or proportion diff).
        p_value: Observed p-value of the treatment effect.
        n: Total sample size (both groups combined).

    Returns:
        {
            "gamma": float,
            "interpretation": str,
            "robust": bool,  # True if gamma > 2.0
        }
    """
    if n <= 0 or not math.isfinite(effect_size):
        return {
            "gamma": 1.0,
            "interpretation": "Insufficient data — cannot assess sensitivity.",
            "robust": False,
        }

    abs_effect = abs(effect_size)

    if abs_effect == 0:
        return {
            "gamma": 1.0,
            "interpretation": (
                "Zero effect size — any amount of hidden confounding "
                "could explain this result."
            ),
            "robust": False,
        }

    # Gamma ~ exp(2 * |d| * sqrt(n) / Z_alpha)
    exponent = 2.0 * abs_effect * math.sqrt(n) / _Z_ALPHA
    # Clamp to avoid overflow for very large exponents
    exponent = min(exponent, 500.0)
    gamma = math.exp(exponent)

    if gamma > 5.0:
        interpretation = (
            f"Gamma = {gamma:.1f} — this result is robust to strong hidden "
            f"confounding.  An unobserved confounder would need to change the "
            f"odds of treatment by a factor of {gamma:.1f}x to overturn the finding."
        )
    elif gamma > 2.0:
        interpretation = (
            f"Gamma = {gamma:.1f} — this result is robust to moderate hidden "
            f"confounding.  An unobserved confounder would need to change the "
            f"odds of treatment by {gamma:.1f}x to overturn the finding."
        )
    else:
        interpretation = (
            f"Gamma = {gamma:.1f} — this result is sensitive to hidden "
            f"confounding.  A relatively small unobserved confounder "
            f"(odds ratio {gamma:.1f}x) could explain away the effect. "
            f"Interpret with caution."
        )

    return {
        "gamma": round(gamma, 2),
        "interpretation": interpretation,
        "robust": gamma > 2.0,
    }
