# Sensitivity Analysis

## Purpose

Identify which business parameters have the largest impact on outcomes, so we focus effort where it matters most. A parameter with high sensitivity deserves investment; a parameter with low sensitivity can be ignored.

## Revenue Model

### Base Case Parameters

| Parameter | Symbol | Base Value | Source |
|-----------|--------|------------|--------|
| Monthly signups | S | 50 | Estimate |
| Free-to-paid conversion rate | c | 10% | Industry benchmark for SaaS |
| Monthly price | P | $14.99 | Current pricing |
| Monthly churn rate | r | 15% | Aggressive for early-stage consumer |
| Stripe fee rate | f | 2.9% + $0.30/txn | Stripe standard |
| Monthly hosting cost | H | $15 | Fly.io shared-cpu-1x |
| Monthly misc costs | M | $35 | Domain, email, Apple dev amortized |

### Revenue Formula

```
For month m (m = 1, 2, ..., 12):
    new_paying[m] = S * c
    churned[m] = total_paying[m-1] * r
    total_paying[m] = total_paying[m-1] + new_paying[m] - churned[m]
    gross_revenue[m] = total_paying[m] * P
    net_revenue[m] = gross_revenue[m] * (1 - f) - H - M

Cumulative_12mo = SUM(net_revenue[m] for m=1..12)
```

### Base Case 12-Month Projection

Steady-state paying users = S * c / r = 50 * 0.10 / 0.15 = **33.3 users**

At steady state: MRR = 33.3 * $14.99 * (1 - 0.029) - $50 = **$435/month**

12-month cumulative (accounting for ramp-up): approximately **$3,200 net revenue**

## Tornado Analysis

Vary each parameter by +/-50% from base case, holding all others constant. Measure impact on 12-month cumulative net revenue.

```python
"""
Sensitivity analysis — tornado diagram.
Run: python scripts/sensitivity_analysis.py
"""

import numpy as np
import matplotlib.pyplot as plt

def revenue_model(months=12, signups=50, conversion=0.10, price=14.99,
                  churn=0.15, stripe_rate=0.029, hosting=15, misc=35):
    """Calculate 12-month cumulative net revenue."""
    total_paying = 0
    cumulative = 0

    for m in range(months):
        new_paying = signups * conversion
        churned = total_paying * churn
        total_paying = max(0, total_paying + new_paying - churned)
        gross = total_paying * price
        stripe_fees = gross * stripe_rate + total_paying * 0.30
        net = gross - stripe_fees - hosting - misc
        cumulative += net

    return cumulative

def tornado_analysis():
    """Vary each parameter +/-50% and measure impact."""
    base = revenue_model()

    params = {
        'Monthly Signups': {'kwarg': 'signups', 'base': 50, 'unit': ''},
        'Conversion Rate': {'kwarg': 'conversion', 'base': 0.10, 'unit': '%'},
        'Monthly Price': {'kwarg': 'price', 'base': 14.99, 'unit': '$'},
        'Monthly Churn': {'kwarg': 'churn', 'base': 0.15, 'unit': '%'},
        'Hosting Cost': {'kwarg': 'hosting', 'base': 15, 'unit': '$'},
    }

    results = {}
    for name, config in params.items():
        low_val = config['base'] * 0.5
        high_val = config['base'] * 1.5

        low_result = revenue_model(**{config['kwarg']: low_val})
        high_result = revenue_model(**{config['kwarg']: high_val})

        results[name] = {
            'low_val': low_val,
            'high_val': high_val,
            'low_result': low_result,
            'high_result': high_result,
            'range': abs(high_result - low_result),
            'base_result': base,
        }

    return results, base

def plot_tornado(results, base, output_path="data/tornado_diagram.png"):
    """Plot tornado diagram."""
    sorted_params = sorted(results.items(), key=lambda x: x[1]['range'], reverse=True)

    fig, ax = plt.subplots(figsize=(10, 6))

    y_pos = range(len(sorted_params))
    for i, (name, data) in enumerate(sorted_params):
        low = data['low_result'] - base
        high = data['high_result'] - base

        # For churn, low churn = high revenue (invert direction)
        left = min(low, high)
        width = abs(high - low)

        color_low = 'coral' if low < high else 'steelblue'
        color_high = 'steelblue' if low < high else 'coral'

        ax.barh(i, low, color=color_low, alpha=0.7, height=0.6)
        ax.barh(i, high, color=color_high, alpha=0.7, height=0.6)

        # Label the range
        ax.text(max(abs(low), abs(high)) + 50, i,
                f"${data['range']:,.0f} range", va='center', fontsize=9)

    ax.set_yticks(y_pos)
    ax.set_yticklabels([name for name, _ in sorted_params])
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.set_xlabel('Change in 12-Month Cumulative Revenue vs Base Case ($)')
    ax.set_title('Sensitivity Analysis: Tornado Diagram')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Plot saved to {output_path}")

def print_sensitivity(results, base):
    """Print sensitivity table."""
    sorted_params = sorted(results.items(), key=lambda x: x[1]['range'], reverse=True)

    print(f"\nBase case 12-month cumulative: ${base:,.0f}")
    print(f"\n{'Parameter':<20} {'Low (-50%)':<12} {'High (+50%)':<12} {'Range':<10} {'Impact'}")
    print("-" * 75)

    for name, data in sorted_params:
        print(f"{name:<20} ${data['low_result']:>8,.0f}   ${data['high_result']:>8,.0f}   "
              f"${data['range']:>7,.0f}   "
              f"{'HIGH' if data['range'] > base * 0.5 else 'medium' if data['range'] > base * 0.2 else 'low'}")

if __name__ == "__main__":
    results, base = tornado_analysis()
    print_sensitivity(results, base)
    plot_tornado(results, base)
```

## Expected Findings

### Parameter Sensitivity Ranking (Predicted)

1. **Monthly Churn (HIGHEST IMPACT):** Small changes in churn have outsized impact on LTV. At 15% monthly churn, average customer lifetime = 1/0.15 = 6.7 months, LTV = $100. At 10% churn, lifetime = 10 months, LTV = $150. At 20% churn, lifetime = 5 months, LTV = $75. A 5% absolute change in churn rate changes LTV by $25-50 per user.

2. **Monthly Signups:** Linear impact on revenue. More signups = more revenue, but only if conversion and churn are healthy. Doubling signups doubles revenue.

3. **Conversion Rate:** Linear impact, but bounded by user acquisition. At 10% conversion, you need 10 signups per paying user. At 20% conversion, you need 5.

4. **Monthly Price:** Direct multiplier on all revenue. But price is constrained by market (competitors at $10-15/month) and elasticity.

5. **Hosting Cost (LOWEST IMPACT):** At $15/month, hosting is noise compared to revenue. Even 3x hosting cost ($45) is trivially small. Do not optimize hosting costs at this scale.

## SLO Sensitivity

### Availability Impact Model

Current SLO: 99.5% availability (3.6 hours downtime/month).

| Availability | Monthly Downtime | Impact |
|-------------|------------------|--------|
| 99.9%       | 43 minutes       | Negligible user impact |
| 99.5%       | 3.6 hours        | 1-2 users might notice during peak hours |
| 99.0%       | 7.2 hours        | 4-5 users likely see errors during peak |
| 98.0%       | 14.4 hours       | Multiple users per day see failures |
| 95.0%       | 36 hours         | Unusable. Users churn. |

### Downtime-to-Churn Model

```
failed_sessions = daily_active_users * sessions_per_day * downtime_fraction_during_active_hours
churned_from_downtime = failed_sessions * P(churn | failed_session)
```

Assumptions:
- Active hours: 6pm-10pm (4 hours = 17% of day)
- If downtime occurs randomly: 17% chance it hits active hours
- P(churn | failed_session) = 5% for a single failure, increasing with repeat failures

At 100 DAU, 99.5% availability:
- Expected failed sessions/month: 100 * 1.5 * (3.6/720) * (4/24) = **0.21 failed sessions**
- Expected churn from downtime: 0.21 * 0.05 = **0.01 users** (negligible)

At 99.0% availability:
- Expected failed sessions/month: **0.42** — still negligible

**Conclusion:** At current scale, the difference between 99.0% and 99.9% availability is immaterial to user retention. Investing in availability beyond 99.5% is waste at <1,000 users. Focus on churn rate, conversion rate, and signups instead.

## Elasticity Quick Reference

### Price Elasticity

```
Revenue = Users * Price
If price changes by x%, users must change by y% to maintain revenue:
y = -x / (1 + x)
```

| Price Change | User Change Needed | Example |
|-------------|-------------------|---------|
| $14.99 -> $9.99 (-33%) | +50% more users | Need 150 users instead of 100 |
| $14.99 -> $12.99 (-13%) | +15% more users | Need 115 users instead of 100 |
| $14.99 -> $17.99 (+20%) | Can lose 17% of users | Keep 83 of 100 users |
| $14.99 -> $19.99 (+33%) | Can lose 25% of users | Keep 75 of 100 users |

### Churn Elasticity

```
LTV = Price / Churn_Rate
Revenue_12mo ~ Signups * Conversion * LTV (simplified)
```

| Churn Rate | Average Lifetime | LTV at $14.99 |
|-----------|-----------------|---------------|
| 5%        | 20 months       | $300          |
| 10%       | 10 months       | $150          |
| 15%       | 6.7 months      | $100          |
| 20%       | 5 months        | $75           |
| 25%       | 4 months        | $60           |

**Reducing churn from 15% to 10% increases LTV by 50%.** This is the single highest-leverage activity for Aelu's business model.

## Action Items

1. **Primary focus: Reduce churn.** Every 1% reduction in monthly churn adds ~$7 to LTV. At 100 paying users, that's $700/month in steady state.
2. **Secondary focus: Increase signups.** Content marketing, SEO for "learn Mandarin" queries, App Store optimization.
3. **Tertiary focus: Conversion rate.** Improve onboarding flow, free tier value proposition, paywall design.
4. **Do not optimize:** Hosting costs, Stripe fees, or availability beyond 99.5% at current scale.
