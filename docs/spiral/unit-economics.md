# Unit Economics

> Last updated: 2026-03-10
> Review cadence: Monthly (operations review)

## Revenue Per User

| Plan | Price | Stripe Fee | Net Revenue/Transaction | Effective Monthly |
|------|-------|-----------|------------------------|-------------------|
| Monthly | $14.99/mo | $0.73 (2.9% + $0.30) | $14.26 | $14.26 |
| Annual (if offered) | $119.88/yr ($9.99/mo) | $3.77 | $116.11 | $9.68 |

**Blended estimate:** If 70% monthly / 30% annual, effective net = (0.70 × $14.26) + (0.30 × $9.68) = **$12.88/month**

---

## Cost of Goods Sold (COGS) Per User

| Item | Cost/User/Month | Notes |
|------|----------------|-------|
| Hosting (marginal compute) | $0.01 | SQLite + Flask is <1ms per request. Each user does ~50-200 requests/month. Negligible. |
| Stripe payment processing | $0.73 | Per monthly transaction. Annual billing reduces this to $0.31/month ($3.77/12). |
| Email (transactional) | $0.001 | ~2-3 emails/user/month (welcome, receipt, reset). Resend free tier. |
| TTS audio generation | $0.00 | edge-tts is free. If migrating to cloud TTS: ~$0.004/user/month (est. 1000 chars/user/month at $4/1M chars). |
| Data storage | $0.001 | ~100KB per user in SQLite (progress records, session logs). S3 backup cost negligible. |
| **Total COGS** | **$0.74** | |

**Gross margin:** ($14.26 - $0.74) / $14.26 = **94.8%**

This is a software business with near-zero marginal costs. The constraint is never COGS — it's customer acquisition and retention.

---

## Customer Acquisition Cost (CAC)

### Current State: $0 (Organic Only)

No paid acquisition. Channels:
- Reddit (r/ChineseLanguage, r/languagelearning)
- Personal network
- Content marketing (blog posts, HSK guides)
- Word of mouth (once users exist)

**Estimated cost of organic acquisition:** ~$0 in cash, ~2-4 hours/week in time. At $150/hr opportunity cost, this is $300-600/week, but since it's founder time that's already being spent, the marginal cash cost is $0.

### Target CAC at Scale

| Channel | Est. CAC | Payback Period |
|---------|---------|----------------|
| Reddit/community (organic) | $0 | Immediate |
| Content marketing (SEO) | $5-15 | 1 month |
| Google Ads (language learning keywords) | $20-40 | 2-3 months |
| Facebook/Instagram Ads | $15-30 | 1-2 months |
| Affiliate/referral | $10-20 (commission) | 1 month |

**Target:** CAC < $30, which gives a 2-month payback at $14.26/month net revenue.

---

## Lifetime Value (LTV)

LTV = Monthly Net Revenue / Monthly Churn Rate

| Monthly Churn Rate | Avg Lifetime (months) | LTV (monthly plan) | LTV (blended) |
|-------------------|----------------------|--------------------|-|
| 30% | 3.3 | $47.06 | $42.50 |
| 20% | 5.0 | $71.30 | $64.40 |
| 15% | 6.7 | $95.54 | $86.30 |
| 10% | 10.0 | $142.60 | $128.80 |
| 5% | 20.0 | $285.20 | $257.60 |

**Industry benchmarks for language learning apps:**
- Duolingo: ~50% 30-day retention (but free tier inflates this)
- Paid-only apps: 15-25% monthly churn is typical
- Niche paid apps with engaged users: 5-10% monthly churn is achievable

**Target:** 10% monthly churn (10-month average lifetime, $142.60 LTV). This requires genuine learning outcomes — users who feel progress stay.

---

## LTV:CAC Ratio

| Scenario | LTV | CAC | LTV:CAC | Verdict |
|----------|-----|-----|---------|---------|
| Organic acquisition, 20% churn | $71.30 | $0 | ∞ | Unsustainable at scale (can't grow on organic alone forever) |
| Organic acquisition, 10% churn | $142.60 | $0 | ∞ | Same |
| Content marketing, 20% churn | $71.30 | $10 | 7.1:1 | Excellent |
| Content marketing, 10% churn | $142.60 | $10 | 14.3:1 | Excellent |
| Google Ads, 20% churn | $71.30 | $30 | 2.4:1 | Below target |
| Google Ads, 10% churn | $142.60 | $30 | 4.8:1 | Good |
| Facebook Ads, 20% churn | $71.30 | $20 | 3.6:1 | Acceptable |

**Target: LTV:CAC > 3:1.** Below 3:1, acquisition is too expensive relative to value extracted. Above 10:1, you're under-investing in growth.

---

## Payback Period

Payback = CAC / Monthly Net Revenue

| CAC | Monthly Net | Payback |
|-----|------------|---------|
| $0 | $14.26 | 0 months (organic) |
| $10 | $14.26 | 0.7 months |
| $20 | $14.26 | 1.4 months |
| $30 | $14.26 | 2.1 months |
| $50 | $14.26 | 3.5 months |

**Target: Payback < 3 months.** At $14.99/month pricing, this means CAC must stay below ~$43.

---

## Contribution Margin by Segment

Once users exist, segment by behavior:

| Segment | Expected % | Revenue/User/Mo | COGS/User/Mo | Contribution Margin |
|---------|-----------|----------------|-------------|-------------------|
| Power users (daily sessions) | 15% | $14.26 | $0.74 | $13.52 (94.8%) |
| Regular users (3-4x/week) | 35% | $14.26 | $0.74 | $13.52 (94.8%) |
| Casual users (1-2x/week) | 30% | $14.26 | $0.74 | $13.52 (94.8%) |
| Churning (will cancel next month) | 20% | $14.26 | $0.74 | $13.52 (94.8%) |

**Observation:** COGS is so low that all segments have the same contribution margin. The variable is retention, not cost. This means the entire business strategy reduces to: **acquire users cheaply, and retain them by delivering real learning outcomes.**

---

## Key Metrics to Track Post-Launch

| Metric | How to Measure | Target | Danger Zone |
|--------|---------------|--------|-------------|
| Monthly churn | Users who cancel / total users at start of month | <15% | >25% |
| Net revenue retention | Revenue this month from last month's users / last month's revenue | >85% | <75% |
| CAC | Total acquisition spend / new paying users | <$30 | >$50 |
| LTV:CAC | Computed from churn and CAC | >3:1 | <2:1 |
| Payback period | CAC / monthly net revenue | <3 months | >6 months |
| Gross margin | (Revenue - COGS) / Revenue | >90% | <80% |

---

## What Changes the Math

| Event | Impact on Unit Economics |
|-------|------------------------|
| Raising price to $19.99/month | LTV increases 33%. Break-even on developer time drops from 673 to 505 users. Risk: higher churn. |
| Lowering price to $9.99/month | LTV decreases 33%. More accessible but need 50% more users for same revenue. |
| Adding annual plan | Reduces Stripe fees per transaction. Improves cash flow (paid upfront). May reduce churn (sunk cost psychology). |
| Moving to Postgres | COGS increases ~$0.15/user/month. Negligible impact on margins. |
| Hiring a contractor | Transforms opportunity cost into real cost. Must be funded by revenue. At $50/hr part-time (10 hrs/week), adds $2,000/month. Need ~140 paying users to cover. |
