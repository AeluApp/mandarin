# Pricing Analysis

## Current Pricing

**$14.99/month**, single tier, no annual discount, no free tier (free trial period TBD).

## Competitive Landscape

| App | Monthly Price | Annual Price | Free Tier | Target | Differentiator |
|-----|--------------|-------------|-----------|--------|---------------|
| **Aelu** | $14.99 | N/A | N/A | Serious HSK learners | Custom SRS, zero AI tokens, deterministic grading, HSK 1-9 |
| Hack Chinese | $14.99 | $107.88 ($8.99/mo) | Limited | HSK/vocabulary | Vocabulary-focused SRS, HSK alignment |
| HelloChinese | $9.99 | $59.88 ($4.99/mo) | Generous | Beginners | Gamified, speech recognition, stories |
| Skritter | $14.99 | $107.88 ($8.99/mo) | 7-day trial | Writing practice | Character writing with stroke order |
| Duolingo | $7.99 | $83.88 ($6.99/mo) | Very generous | Casual learners | Gamification, social, 40+ languages |
| Pleco | Free + IAP | $29.99-149.99 (one-time) | Core app free | Dictionary users | Best Chinese dictionary, OCR |
| ChinesePod | $14.99-29.99 | $143.88-287.76 | Some content | Audio learners | Podcast-style lessons, native content |
| The Chairman's Bao | $12.50 | $99 ($8.25/mo) | Limited | Readers | Graded news articles |

### Positioning Map

```
                    Expensive ($20+)
                         |
              ChinesePod |
                         |
         Aelu  Hack Chinese  Skritter
                         |
  Casual -------- HelloChinese --------- Serious
                         |
               Duolingo  |
                         |
                    Cheap ($5)
```

Aelu occupies the **serious + mid-price** quadrant. Direct competitors are Hack Chinese and Skritter at the same price point.

## Van Westendorp Price Sensitivity Analysis

### Survey Design

Ask 20+ target users (serious Mandarin learners, HSK 2-6 level) four questions:

1. **Too cheap** (quality concern): "At what price would you consider this app so inexpensive that you would doubt its quality?"
2. **Cheap** (good value): "At what price would you consider this app a bargain — a great buy for the money?"
3. **Expensive** (getting pricey): "At what price would you consider this app starting to get expensive — not out of the question, but you'd have to think about it?"
4. **Too expensive** (rejected): "At what price would you consider this app too expensive to consider?"

### Survey Distribution

- Target: r/ChineseLanguage, HackChinese forums, MandarinCorner community, personal network of Mandarin learners
- Minimum: 20 respondents for directional insights, 50+ for statistical validity
- Format: Google Forms or Tally, anonymous, 2-minute completion time

### Analysis Method

Plot cumulative distribution of each question. The four curves intersect at key price points:

- **Point of Marginal Cheapness (PMC):** Intersection of "too cheap" and "expensive" curves. Below this, some users doubt quality.
- **Point of Marginal Expensiveness (PME):** Intersection of "cheap" and "too expensive" curves. Above this, you lose price-sensitive users.
- **Optimal Price Point (OPP):** Intersection of "too cheap" and "too expensive" curves. Minimizes the number of users who reject the price in either direction.
- **Indifference Price Point (IDP):** Intersection of "cheap" and "expensive" curves. Equal number think it's cheap vs expensive.

**Acceptable price range: PMC to PME.** Current $14.99 should fall within this range.

```python
"""
Van Westendorp Price Sensitivity analysis.
Run: python scripts/van_westendorp.py
Requires: pandas, numpy, matplotlib
"""

import numpy as np
import matplotlib.pyplot as plt

def van_westendorp(responses):
    """
    Analyze Van Westendorp survey responses.

    responses: list of dicts with keys 'too_cheap', 'cheap', 'expensive', 'too_expensive'
    """
    prices = np.arange(1, 30, 0.50)  # $1 to $30 in $0.50 increments

    too_cheap = np.array([r['too_cheap'] for r in responses])
    cheap = np.array([r['cheap'] for r in responses])
    expensive = np.array([r['expensive'] for r in responses])
    too_expensive = np.array([r['too_expensive'] for r in responses])

    n = len(responses)

    # Cumulative distributions
    cum_too_cheap = np.array([np.sum(too_cheap <= p) / n for p in prices])
    cum_cheap = np.array([np.sum(cheap <= p) / n for p in prices])
    cum_expensive = np.array([np.sum(expensive >= p) / n for p in prices])  # Note: reversed
    cum_too_expensive = np.array([np.sum(too_expensive >= p) / n for p in prices])

    # Actually for VW, we want:
    # "too cheap" = cumulative % who say price is too cheap (decreasing as price rises)
    # "too expensive" = cumulative % who say price is too expensive (increasing as price rises)
    cum_too_cheap_rev = np.array([np.sum(too_cheap >= p) / n for p in prices])
    cum_not_cheap = np.array([np.sum(cheap <= p) / n for p in prices])
    cum_not_expensive = np.array([np.sum(expensive >= p) / n for p in prices])
    cum_too_expensive_fwd = np.array([np.sum(too_expensive <= p) / n for p in prices])

    # Find intersections
    def find_intersection(y1, y2, x):
        diff = y1 - y2
        sign_changes = np.where(np.diff(np.sign(diff)))[0]
        if len(sign_changes) > 0:
            idx = sign_changes[0]
            # Linear interpolation
            x_intersect = x[idx] + (x[idx+1] - x[idx]) * (-diff[idx] / (diff[idx+1] - diff[idx]))
            return x_intersect
        return None

    opp = find_intersection(cum_too_cheap_rev, cum_too_expensive_fwd, prices)
    idp = find_intersection(cum_not_cheap, cum_not_expensive, prices)

    print(f"Optimal Price Point (OPP): ${opp:.2f}" if opp else "OPP: not found")
    print(f"Indifference Price Point (IDP): ${idp:.2f}" if idp else "IDP: not found")

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(prices, cum_too_cheap_rev, label='Too Cheap', color='red', linestyle='--')
    ax.plot(prices, cum_not_cheap, label='Not a Bargain', color='orange')
    ax.plot(prices, cum_not_expensive, label='Not Expensive', color='green')
    ax.plot(prices, cum_too_expensive_fwd, label='Too Expensive', color='darkred', linestyle='--')

    if opp:
        ax.axvline(x=opp, color='blue', linestyle=':', label=f'OPP: ${opp:.2f}')
    ax.axvline(x=14.99, color='purple', linestyle=':', alpha=0.5, label='Current: $14.99')

    ax.set_xlabel('Price ($)')
    ax.set_ylabel('Cumulative Proportion')
    ax.set_title('Van Westendorp Price Sensitivity')
    ax.legend()
    ax.set_xlim(1, 25)

    plt.tight_layout()
    plt.savefig('data/van_westendorp.png', dpi=150)
    print("Plot saved to data/van_westendorp.png")

# Example usage with placeholder data (replace with actual survey responses):
SAMPLE_RESPONSES = [
    {'too_cheap': 3, 'cheap': 8, 'expensive': 15, 'too_expensive': 25},
    {'too_cheap': 5, 'cheap': 10, 'expensive': 18, 'too_expensive': 25},
    {'too_cheap': 2, 'cheap': 7, 'expensive': 13, 'too_expensive': 20},
    # ... add 17+ more actual responses
]

if __name__ == "__main__":
    if len(SAMPLE_RESPONSES) < 20:
        print(f"Only {len(SAMPLE_RESPONSES)} responses. Need 20+ for reliable analysis.")
        print("Update SAMPLE_RESPONSES with actual survey data.")
    van_westendorp(SAMPLE_RESPONSES)
```

## Price Elasticity Analysis

### Revenue Equivalence Tables

If we change price, what user volume change is needed to maintain the same revenue?

**Current baseline: 100 paying users at $14.99 = $1,499 MRR**

| New Price | Revenue per User | Users Needed for $1,499 MRR | Change in Users | Conversion Increase Needed |
|-----------|-----------------|----------------------------|----------------|---------------------------|
| $7.99     | $7.99           | 188                        | +88%           | Conversion must nearly double |
| $9.99     | $9.99           | 150                        | +50%           | Conversion must increase 50% |
| $11.99    | $11.99          | 125                        | +25%           | Moderate increase |
| $14.99    | $14.99          | 100                        | Baseline       | Baseline |
| $17.99    | $17.99          | 83                         | -17%           | Can lose 17 users |
| $19.99    | $19.99          | 75                         | -25%           | Can lose 25 users |
| $24.99    | $24.99          | 60                         | -40%           | Can lose 40 users |

### LTV-Based Pricing

LTV must exceed Customer Acquisition Cost (CAC) by at least 3x for a healthy business.

```
LTV = ARPU * Gross_Margin * (1 / Churn_Rate)
LTV = $14.99 * 0.97 * (1 / 0.15) = $96.93

Required: LTV > 3 * CAC
Therefore: CAC < $32.31
```

At $14.99/month with 15% churn: **maximum sustainable CAC is $32.** This constrains paid acquisition channels.

If churn drops to 10%: LTV = $145.40, max CAC = $48.47.
If price rises to $19.99 (and churn holds): LTV = $129.27, max CAC = $43.09.

## Pricing Tiers (Future Consideration)

Currently single-tier. If conversion rate is low, consider:

### Option A: Freemium

| Tier | Price | Features |
|------|-------|----------|
| Free | $0 | 5 items/day, HSK 1 only, no audio |
| Pro | $14.99/mo | Unlimited items, HSK 1-9, audio, analytics |

Risk: Free tier cannibalizes paid. Many language learners are content with limited free tools.

### Option B: Good/Better/Best

| Tier | Price | Features |
|------|-------|----------|
| Core | $9.99/mo | HSK 1-3, basic drills, no audio |
| Pro | $14.99/mo | HSK 1-6, all drills, audio, analytics |
| Complete | $19.99/mo | HSK 1-9, all features, priority support |

Risk: Decision paralysis. Three tiers require more UI, more support, more testing.

### Option C: Annual Discount

| Tier | Price | Effective Monthly |
|------|-------|-------------------|
| Monthly | $14.99/mo | $14.99 |
| Annual | $119.88/yr | $9.99/mo (33% off) |

This is the most common pattern in the language learning space. Annual plans reduce churn (commitment effect) and improve cash flow.

**Recommendation:** Start with Option C (annual discount) before introducing multiple tiers. It's the simplest change with the highest expected impact on LTV.

## Price Testing Strategy

Do NOT A/B test prices directly (showing different users different prices is ethically and legally problematic, and generates immediate user complaints if discovered).

Instead:
1. **Geographic pricing:** Different prices in different markets (if expanding internationally).
2. **Cohort pricing:** New signups see new price; existing users keep old price (grandfather clause).
3. **Discount testing:** Test with coupon codes that effectively lower the price. Measure conversion at different discount levels.
4. **Survey first:** Run the Van Westendorp survey before any price change to calibrate expectations.

## Decision Framework

Change the price when:
1. Van Westendorp data shows OPP significantly different from $14.99 (>$2 gap)
2. Conversion rate is persistently below 8% (suggests price resistance)
3. Churn rate is above 20% AND exit surveys cite price as top reason
4. A competitor significantly undercuts at similar quality

Do NOT change the price:
1. To match a cheaper competitor with inferior features
2. Without at least 20 survey responses validating the new price
3. Within 90 days of a previous price change
4. For existing customers (grandfather clause)
