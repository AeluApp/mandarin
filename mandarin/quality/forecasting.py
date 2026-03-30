"""Time series forecasting — exponential smoothing and seasonal decomposition.

Implements Simple Exponential Smoothing, Holt's Linear, and Holt-Winters
Additive methods. All stdlib only (no statsmodels, no numpy).
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mean(values: list[float]) -> float:
    """Arithmetic mean, guarded against empty input."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float], ddof: int = 1) -> float:
    """Sample standard deviation."""
    if len(values) < ddof + 1:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - ddof))


def _moving_average(values: list[float], window: int) -> list[float | None]:
    """Centered moving average.  Returns list same length as *values*;
    positions where the window doesn't fit are filled with None."""
    n = len(values)
    result: list[float | None] = [None] * n
    half = window // 2

    if window % 2 == 1:
        # Odd window: simple centered average
        for i in range(half, n - half):
            result[i] = sum(values[i - half: i + half + 1]) / window
    else:
        # Even window (e.g. period=12): 2x moving average (2x MA)
        # First pass: MA of length *window*
        ma1: list[float | None] = [None] * n
        for i in range(n - window + 1):
            ma1[i + half] = sum(values[i: i + window]) / window
        # Second pass: average successive pairs to center
        for i in range(1, n):
            if ma1[i] is not None and ma1[i - 1] is not None:
                result[i] = (ma1[i] + ma1[i - 1]) / 2.0

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def exponential_smoothing(
    observations: list[float],
    alpha: float = 0.3,
) -> dict[str, Any]:
    """Simple exponential smoothing (level only).

    Args:
        observations: time series values (at least 2).
        alpha: smoothing parameter in (0, 1).

    Returns: {"forecast": float, "fitted": list[float], "residuals": list[float]}
    """
    if not observations:
        logger.warning("exponential_smoothing: empty input")
        return {"forecast": 0.0, "fitted": [], "residuals": []}

    if len(observations) == 1:
        return {"forecast": observations[0], "fitted": [observations[0]], "residuals": [0.0]}

    alpha = max(0.01, min(0.99, alpha))

    # Initialize level to first observation
    level = observations[0]
    fitted: list[float] = [level]
    residuals: list[float] = [0.0]

    for t in range(1, len(observations)):
        forecast_t = level
        fitted.append(forecast_t)
        residuals.append(observations[t] - forecast_t)
        level = alpha * observations[t] + (1 - alpha) * level

    # One-step-ahead forecast beyond the series
    forecast = level

    return {"forecast": forecast, "fitted": fitted, "residuals": residuals}


def holt_linear(
    observations: list[float],
    alpha: float = 0.3,
    beta: float = 0.1,
) -> dict[str, Any]:
    """Holt's linear method (level + trend).

    Args:
        observations: time series values (at least 3).
        alpha: level smoothing in (0, 1).
        beta: trend smoothing in (0, 1).

    Returns: {"forecast": float, "trend": float, "level": float,
              "fitted": list[float], "forecast_horizon": list (next 12 periods)}
    """
    if not observations:
        logger.warning("holt_linear: empty input")
        return {"forecast": 0.0, "trend": 0.0, "level": 0.0,
                "fitted": [], "forecast_horizon": []}

    if len(observations) < 2:
        val = observations[0]
        return {"forecast": val, "trend": 0.0, "level": val,
                "fitted": [val], "forecast_horizon": [val] * 12}

    alpha = max(0.01, min(0.99, alpha))
    beta = max(0.01, min(0.99, beta))

    # Initialize: level = first obs, trend = second - first
    level = observations[0]
    trend = observations[1] - observations[0]

    fitted: list[float] = [level]
    residuals: list[float] = [0.0]

    for t in range(1, len(observations)):
        forecast_t = level + trend
        fitted.append(forecast_t)
        residuals.append(observations[t] - forecast_t)

        new_level = alpha * observations[t] + (1 - alpha) * (level + trend)
        new_trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
        trend = new_trend

    forecast = level + trend
    forecast_horizon = [level + (h + 1) * trend for h in range(12)]

    return {
        "forecast": forecast,
        "trend": trend,
        "level": level,
        "fitted": fitted,
        "forecast_horizon": forecast_horizon,
    }


def holt_winters_additive(
    observations: list[float],
    period: int,
    alpha: float = 0.3,
    beta: float = 0.1,
    gamma: float = 0.3,
) -> dict[str, Any]:
    """Holt-Winters additive method (level + trend + seasonality).

    Requires at least 2 full periods of data.

    Args:
        observations: time series values.
        period: seasonal period length (e.g. 7 for weekly, 12 for monthly).
        alpha: level smoothing in (0, 1).
        beta: trend smoothing in (0, 1).
        gamma: seasonal smoothing in (0, 1).

    Returns: {"forecast_horizon": list, "level": float, "trend": float,
              "seasonal": list, "fitted": list}
    """
    if not observations:
        logger.warning("holt_winters_additive: empty input")
        return {"forecast_horizon": [], "level": 0.0, "trend": 0.0,
                "seasonal": [], "fitted": []}

    n = len(observations)

    if period < 2:
        logger.warning("holt_winters_additive: period must be >= 2, falling back to holt_linear")
        result = holt_linear(observations, alpha, beta)
        return {"forecast_horizon": result["forecast_horizon"], "level": result["level"],
                "trend": result["trend"], "seasonal": [0.0] * max(period, 1),
                "fitted": result["fitted"]}

    if n < 2 * period:
        logger.warning("holt_winters_additive: need >= 2*period observations (%d), got %d; "
                        "falling back to holt_linear", 2 * period, n)
        result = holt_linear(observations, alpha, beta)
        return {"forecast_horizon": result["forecast_horizon"], "level": result["level"],
                "trend": result["trend"], "seasonal": [0.0] * period,
                "fitted": result["fitted"]}

    alpha = max(0.01, min(0.99, alpha))
    beta = max(0.01, min(0.99, beta))
    gamma = max(0.01, min(0.99, gamma))

    # ---- Initialization ----
    # Level: average of first period
    level = _mean(observations[:period])

    # Trend: average slope across first two periods
    trend = 0.0
    for i in range(period):
        trend += (observations[i + period] - observations[i])
    trend /= (period * period)

    # Seasonal components: deviation from level in first period
    seasonal = [observations[i] - level for i in range(period)]

    # ---- Fit ----
    fitted: list[float] = []
    for t in range(n):
        s_idx = t % period
        if t < period:
            # Within initialization period — use initial values for fitted
            fitted.append(level + t * trend + seasonal[s_idx])
        else:
            forecast_t = level + trend + seasonal[s_idx]
            fitted.append(forecast_t)

            new_level = alpha * (observations[t] - seasonal[s_idx]) + (1 - alpha) * (level + trend)
            new_trend = beta * (new_level - level) + (1 - beta) * trend
            new_seasonal = gamma * (observations[t] - new_level) + (1 - gamma) * seasonal[s_idx]

            level = new_level
            trend = new_trend
            seasonal[s_idx] = new_seasonal

    # ---- Forecast horizon (next period) ----
    forecast_horizon: list[float] = []
    for h in range(1, period + 1):
        s_idx = (n + h - 1) % period
        forecast_horizon.append(level + h * trend + seasonal[s_idx])

    return {
        "forecast_horizon": forecast_horizon,
        "level": level,
        "trend": trend,
        "seasonal": list(seasonal),
        "fitted": fitted,
    }


def decompose(
    observations: list[float],
    period: int,
) -> dict[str, Any]:
    """Additive time series decomposition: trend + seasonal + residual.

    Uses centered moving average for trend extraction, then averages the
    detrended values by season position to get the seasonal component.

    Returns: {"trend": list, "seasonal": list, "residual": list}
    Values at edges where trend cannot be computed are None.
    """
    if not observations:
        return {"trend": [], "seasonal": [], "residual": []}

    n = len(observations)
    if period < 2 or n < 2 * period:
        logger.warning("decompose: need period >= 2 and length >= 2*period; "
                        "period=%d, length=%d", period, n)
        return {
            "trend": [None] * n,
            "seasonal": [0.0] * n,
            "residual": list(observations),
        }

    # Step 1: Trend via centered moving average
    trend = _moving_average(observations, period)

    # Step 2: Detrend
    detrended: list[float | None] = [None] * n
    for i in range(n):
        if trend[i] is not None:
            detrended[i] = observations[i] - trend[i]

    # Step 3: Average detrended values per season position
    season_sums: dict[int, list[float]] = {p: [] for p in range(period)}
    for i in range(n):
        if detrended[i] is not None:
            season_sums[i % period].append(detrended[i])

    season_avg = [0.0] * period
    for p in range(period):
        if season_sums[p]:
            season_avg[p] = _mean(season_sums[p])

    # Normalize seasonal so it sums to zero over one period
    s_mean = _mean(season_avg)
    season_avg = [s - s_mean for s in season_avg]

    # Step 4: Seasonal component (repeated) and residual
    seasonal = [season_avg[i % period] for i in range(n)]
    residual: list[float | None] = [None] * n
    for i in range(n):
        if trend[i] is not None:
            residual[i] = observations[i] - trend[i] - seasonal[i]

    return {"trend": trend, "seasonal": seasonal, "residual": residual}


def prediction_interval(
    fitted: list[float],
    residuals: list[float],
    horizon: int,
    alpha: float = 0.05,
) -> list[tuple[float, float]]:
    """Compute prediction interval for forecasted values.

    Uses residual standard error and grows the interval with sqrt(horizon step).

    Args:
        fitted: fitted values from a forecasting method.
        residuals: in-sample residuals.
        horizon: number of future periods.
        alpha: significance level (0.05 for 95 % interval).

    Returns: list of (lower, upper) tuples for each horizon step.
    """
    if not residuals or horizon <= 0:
        return []

    # Filter out None residuals
    clean_residuals = [r for r in residuals if r is not None and math.isfinite(r)]
    if not clean_residuals:
        logger.warning("prediction_interval: no valid residuals")
        return [(0.0, 0.0)] * horizon

    sigma = _std(clean_residuals, ddof=1)
    if sigma == 0:
        sigma = 0.001  # fallback

    # z-critical value (normal approximation for large samples)
    # Use Abramowitz & Stegun rational approximation
    z = _normal_ppf_internal(1.0 - alpha / 2.0)

    # Last fitted value as base (if available)
    last_fitted = fitted[-1] if fitted else 0.0

    intervals: list[tuple[float, float]] = []
    for h in range(1, horizon + 1):
        # Prediction error grows with sqrt(h) for additive models
        se = sigma * math.sqrt(h)
        lower = last_fitted - z * se
        upper = last_fitted + z * se
        intervals.append((lower, upper))

    return intervals


def _normal_ppf_internal(p: float) -> float:
    """Inverse standard normal CDF (Abramowitz & Stegun 26.2.23)."""
    if p <= 0:
        return -10.0
    if p >= 1:
        return 10.0
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -_normal_ppf_internal(1.0 - p)

    t = math.sqrt(-2.0 * math.log(1.0 - p))
    c0 = 2.515517
    c1 = 0.802853
    c2 = 0.010328
    d1 = 1.432788
    d2 = 0.189269
    d3 = 0.001308
    return t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
