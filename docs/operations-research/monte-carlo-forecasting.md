# Monte Carlo Forecasting

## Purpose

Use Monte Carlo simulation to generate probabilistic forecasts instead of single-point estimates. Instead of "we'll complete 20 items next month," we say "there's an 85% chance we'll complete at least 15 items and a 50% chance we'll complete at least 22."

## Method

1. Collect historical throughput samples (items completed per week for the last N weeks).
2. Randomly sample from this historical distribution (with replacement) to simulate future weeks.
3. Sum the samples to get a simulated total for the forecast period.
4. Repeat 10,000 times to build a probability distribution.
5. Report percentiles: 50th (likely), 85th (conservative), 95th (very conservative).

This is nonparametric — it makes no assumptions about the shape of the throughput distribution. It uses actual observed variance.

## Development Throughput Forecast

### Data Collection

Track completed items per week. "Items" can be:
- Features shipped
- Bugs fixed
- Test cases written
- Any countable unit of work

```python
# Historical throughput: items completed per week for last 8 weeks
# Update these numbers from actual data
WEEKLY_THROUGHPUT = [
    12,  # Week of 2026-01-13
    8,   # Week of 2026-01-20
    15,  # Week of 2026-01-27
    10,  # Week of 2026-02-03
    14,  # Week of 2026-02-10
    7,   # Week of 2026-02-17 (context: short week, sick)
    11,  # Week of 2026-02-24
    13,  # Week of 2026-03-03
]
```

### Simulation Script

```python
"""
Monte Carlo throughput forecast.
Run: python scripts/monte_carlo_forecast.py
Requires: numpy, matplotlib
"""

import numpy as np
import matplotlib.pyplot as plt

def throughput_forecast(weekly_throughput, forecast_weeks=4, simulations=10_000):
    """
    Monte Carlo simulation of future throughput.

    Args:
        weekly_throughput: list of historical weekly throughput values
        forecast_weeks: number of weeks to forecast
        simulations: number of Monte Carlo trials
    Returns:
        dict with percentile forecasts
    """
    samples = np.array(weekly_throughput)
    results = np.zeros(simulations)

    for i in range(simulations):
        # Sample with replacement from historical data
        simulated_weeks = np.random.choice(samples, size=forecast_weeks, replace=True)
        results[i] = simulated_weeks.sum()

    percentiles = {
        'p5': np.percentile(results, 5),
        'p25': np.percentile(results, 25),
        'p50': np.percentile(results, 50),
        'p75': np.percentile(results, 75),
        'p85': np.percentile(results, 85),
        'p95': np.percentile(results, 95),
        'mean': np.mean(results),
        'std': np.std(results),
    }

    return results, percentiles

def plot_forecast(results, percentiles, forecast_weeks, output_path="data/throughput_forecast.png"):
    """Histogram of Monte Carlo results with percentile markers."""
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.hist(results, bins=50, alpha=0.7, color='steelblue', edgecolor='white')
    ax.axvline(percentiles['p50'], color='green', linestyle='-', linewidth=2,
               label=f"50th: {percentiles['p50']:.0f} items")
    ax.axvline(percentiles['p85'], color='orange', linestyle='--', linewidth=2,
               label=f"85th: {percentiles['p85']:.0f} items")
    ax.axvline(percentiles['p95'], color='red', linestyle='--', linewidth=2,
               label=f"95th: {percentiles['p95']:.0f} items")

    ax.set_xlabel(f'Total Items Completed in {forecast_weeks} Weeks')
    ax.set_ylabel('Frequency (out of 10,000 simulations)')
    ax.set_title(f'Monte Carlo Throughput Forecast ({forecast_weeks}-Week)')
    ax.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Plot saved to {output_path}")

def print_forecast(percentiles, forecast_weeks):
    """Pretty-print the forecast."""
    print(f"\n{'='*50}")
    print(f"  THROUGHPUT FORECAST ({forecast_weeks} weeks)")
    print(f"{'='*50}")
    print(f"  95% confident: at least {percentiles['p95']:.0f} items")
    print(f"  85% confident: at least {percentiles['p85']:.0f} items")
    print(f"  50% likely:    at least {percentiles['p50']:.0f} items")
    print(f"  Best case:     up to    {percentiles['p5']:.0f} items")
    print(f"  Mean: {percentiles['mean']:.1f} +/- {percentiles['std']:.1f}")
    print(f"{'='*50}")

# --- Example usage ---
WEEKLY_THROUGHPUT = [12, 8, 15, 10, 14, 7, 11, 13]

if __name__ == "__main__":
    results, percentiles = throughput_forecast(WEEKLY_THROUGHPUT, forecast_weeks=4)
    print_forecast(percentiles, forecast_weeks=4)
    plot_forecast(results, percentiles, forecast_weeks=4)
```

## Revenue Monte Carlo

Model 12-month revenue with uncertainty in signup rate, conversion rate, and churn rate.

### Revenue Model

```
For each month m:
    new_signups[m] ~ Poisson(signup_rate)
    new_paying[m] = Binomial(new_signups[m], conversion_rate)
    churned[m] = Binomial(total_paying[m-1], monthly_churn_rate)
    total_paying[m] = total_paying[m-1] + new_paying[m] - churned[m]
    revenue[m] = total_paying[m] * $14.99
```

### Simulation Script

```python
"""
Revenue Monte Carlo simulation.
Run: python scripts/revenue_monte_carlo.py
"""

import numpy as np
import matplotlib.pyplot as plt

def revenue_simulation(
    months=12,
    simulations=10_000,
    # Distribution parameters (mean, std for normal; rate for Poisson)
    signup_rate_mean=50,     # Average new signups per month
    signup_rate_std=15,      # Variability in signups
    conversion_rate_mean=0.10,  # 10% free-to-paid conversion
    conversion_rate_std=0.03,   # Uncertainty in conversion
    churn_rate_mean=0.15,    # 15% monthly churn
    churn_rate_std=0.05,     # Uncertainty in churn
    price=14.99,
    monthly_costs=50.0,      # Hosting + Stripe + misc
):
    """
    Simulate 12-month revenue under uncertainty.
    """
    all_revenue = np.zeros((simulations, months))
    all_paying = np.zeros((simulations, months))
    all_cumulative = np.zeros(simulations)

    for sim in range(simulations):
        # Sample rates for this simulation (held constant across months)
        signup_rate = max(1, np.random.normal(signup_rate_mean, signup_rate_std))
        conversion_rate = np.clip(
            np.random.normal(conversion_rate_mean, conversion_rate_std), 0.01, 0.50
        )
        churn_rate = np.clip(
            np.random.normal(churn_rate_mean, churn_rate_std), 0.01, 0.50
        )

        total_paying = 0

        for m in range(months):
            # New signups this month (Poisson)
            new_signups = np.random.poisson(signup_rate)

            # Convert some to paying
            new_paying = np.random.binomial(new_signups, conversion_rate)

            # Some existing users churn
            churned = np.random.binomial(max(0, int(total_paying)), churn_rate)

            # Update totals
            total_paying = max(0, total_paying + new_paying - churned)

            # Revenue
            gross_revenue = total_paying * price
            stripe_fees = gross_revenue * 0.029 + (total_paying * 0.30 if total_paying > 0 else 0)
            net_revenue = gross_revenue - stripe_fees - monthly_costs

            all_revenue[sim, m] = net_revenue
            all_paying[sim, m] = total_paying

        all_cumulative[sim] = all_revenue[sim].sum()

    return all_revenue, all_paying, all_cumulative

def report_revenue(all_revenue, all_paying, all_cumulative, months=12):
    """Print revenue forecast."""
    print(f"\n{'='*60}")
    print(f"  REVENUE FORECAST ({months}-Month)")
    print(f"{'='*60}")

    print(f"\n  Cumulative Net Revenue:")
    for pct, label in [(5, 'Best case'), (25, 'Optimistic'),
                        (50, 'Most likely'), (75, 'Conservative'),
                        (95, 'Worst case')]:
        val = np.percentile(all_cumulative, pct)
        print(f"    {label:15s}: ${val:>8,.0f}")

    print(f"\n  Month-by-Month Paying Users (50th percentile):")
    for m in range(months):
        p50 = np.percentile(all_paying[:, m], 50)
        p85 = np.percentile(all_paying[:, m], 85)
        rev = np.percentile(all_revenue[:, m], 50)
        print(f"    Month {m+1:2d}: {p50:5.0f} paying users "
              f"(85th: {p85:5.0f}) | MRR: ${rev:>7,.0f}")

    # Break-even analysis
    break_even_month = None
    for m in range(months):
        if np.percentile(all_revenue[:, m], 50) > 0:
            break_even_month = m + 1
            break

    if break_even_month:
        print(f"\n  Break-even month (50th pct): Month {break_even_month}")
    else:
        print(f"\n  Break-even: NOT reached in {months} months at 50th percentile")

    # Probability of profitability
    profitable = (all_cumulative > 0).mean()
    print(f"  Probability of cumulative profit in {months} months: {profitable:.1%}")

def plot_revenue(all_revenue, all_paying, months=12,
                 output_path="data/revenue_forecast.png"):
    """Plot revenue fan chart."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    month_labels = range(1, months + 1)

    # Revenue fan chart
    for pct, alpha, color in [(95, 0.1, 'red'), (75, 0.2, 'orange'),
                               (50, 0.4, 'green'), (25, 0.2, 'orange'),
                               (5, 0.1, 'red')]:
        values = [np.percentile(all_revenue[:, m], pct) for m in range(months)]
        ax1.plot(month_labels, values, alpha=0.8)

    p50 = [np.percentile(all_revenue[:, m], 50) for m in range(months)]
    p25 = [np.percentile(all_revenue[:, m], 25) for m in range(months)]
    p75 = [np.percentile(all_revenue[:, m], 75) for m in range(months)]
    p10 = [np.percentile(all_revenue[:, m], 10) for m in range(months)]
    p90 = [np.percentile(all_revenue[:, m], 90) for m in range(months)]

    ax1.fill_between(month_labels, p10, p90, alpha=0.15, color='steelblue')
    ax1.fill_between(month_labels, p25, p75, alpha=0.3, color='steelblue')
    ax1.plot(month_labels, p50, color='steelblue', linewidth=2, label='Median')
    ax1.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    ax1.set_xlabel('Month')
    ax1.set_ylabel('Net Revenue ($)')
    ax1.set_title('Monthly Net Revenue Forecast')
    ax1.legend()

    # Paying users fan chart
    p50_users = [np.percentile(all_paying[:, m], 50) for m in range(months)]
    p25_users = [np.percentile(all_paying[:, m], 25) for m in range(months)]
    p75_users = [np.percentile(all_paying[:, m], 75) for m in range(months)]

    ax2.fill_between(month_labels, p25_users, p75_users, alpha=0.3, color='coral')
    ax2.plot(month_labels, p50_users, color='coral', linewidth=2, label='Median')
    ax2.set_xlabel('Month')
    ax2.set_ylabel('Paying Users')
    ax2.set_title('Paying Users Forecast')
    ax2.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Plot saved to {output_path}")

if __name__ == "__main__":
    # Moderate scenario
    print("MODERATE SCENARIO (50 signups/month):")
    rev, pay, cum = revenue_simulation(signup_rate_mean=50)
    report_revenue(rev, pay, cum)
    plot_revenue(rev, pay, output_path="data/revenue_forecast_moderate.png")

    # Conservative scenario
    print("\n\nCONSERVATIVE SCENARIO (10 signups/month):")
    rev, pay, cum = revenue_simulation(signup_rate_mean=10, signup_rate_std=5)
    report_revenue(rev, pay, cum)

    # Optimistic scenario
    print("\n\nOPTIMISTIC SCENARIO (200 signups/month):")
    rev, pay, cum = revenue_simulation(signup_rate_mean=200, signup_rate_std=50)
    report_revenue(rev, pay, cum)
```

## How to Use These Forecasts

### For Backlog Planning

"Can we complete Feature X, Y, and Z in the next 4 weeks?"

1. Estimate each feature in number of work items (tasks, stories).
2. Sum the estimates: Feature X (8) + Feature Y (12) + Feature Z (5) = 25 items.
3. Check the throughput forecast: 85th percentile for 4 weeks might be 38 items.
4. Since 25 < 38, there's an 85% chance all three features fit. Ship it.

### For Revenue Conversations

"When will we break even?"

Use the revenue Monte Carlo output. If the 50th percentile break-even is Month 8 and the 85th percentile is Month 14, communicate: "Most likely by Month 8, conservative estimate is Month 14."

### For Commitment-Based Delivery

Instead of giving deadlines, give confidence levels:

- "We're 50% confident this ships by March 28."
- "We're 85% confident this ships by April 10."
- "We're 95% confident this ships by April 25."

Let the stakeholder (in this case, Jason) choose the confidence level.

## Updating the Model

Re-run weekly with updated throughput data. The model improves as more historical data is collected. After 12+ weeks of data, the forecasts become significantly more stable.

Key signals that the model needs recalibration:
- Actual throughput falls outside the 5th-95th percentile range for 2+ consecutive weeks (process change)
- New team members or tools change the throughput distribution
- Scope of "item" changes (e.g., stories get larger or smaller)
