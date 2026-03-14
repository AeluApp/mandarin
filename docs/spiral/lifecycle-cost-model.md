# Lifecycle Cost Model

> Last updated: 2026-03-10
> Review cadence: Monthly (operations review)

## Fixed Monthly Costs

| Item | Cost/Month | Notes |
|------|-----------|-------|
| Fly.io hosting (shared-cpu-1x, 512MB) | $5.70 | $3.19 shared-cpu-1x + $2.51 for 512MB RAM. Auto-stop reduces cost when idle. With min_machines_running=1, expect ~$5-7/month. |
| Fly.io persistent volume (1GB) | $0.15 | mandarin_data volume for SQLite + WAL. |
| Litestream → S3 storage | ~$1.00 | WAL replication to S3. At <1GB database size, storage is negligible. S3 PUT requests dominate cost (~$0.005/1000 PUTs). |
| Domain registration | ~$1.00 | ~$12/year amortized. |
| Apple Developer Program | $8.25 | $99/year amortized. Required for iOS App Store. |
| Resend (email) | $0.00 | Free tier: 100 emails/day, 3,000/month. Sufficient until ~500 active users. |
| **Total fixed** | **~$16.10** | |

## One-Time Costs (Already Paid)

| Item | Cost | Notes |
|------|------|-------|
| Google Play Developer | $25.00 | Lifetime fee. |
| Domain (first year) | ~$12.00 | Recurring annually. |

## Variable Costs (Per User)

| Item | Cost/User/Month | Notes |
|------|----------------|-------|
| Hosting (marginal) | ~$0.01 | SQLite + Flask is remarkably efficient. Each user adds negligible CPU/memory. At 100 users, may need to upgrade to shared-cpu-2x (~$6.38/month extra). |
| Stripe processing | $0.73 | 2.9% + $0.30 on $14.99 = $0.43 + $0.30 = $0.73 per transaction. |
| Email (marginal) | ~$0.001 | Password reset, verification, receipts. At Resend free tier, cost is $0. At paid tier ($20/month for 50K emails), cost is $0.0004/email. |
| **Total variable** | **~$0.74** | |

## Revenue Per User

| Pricing | Gross | Stripe Fee | Net Revenue |
|---------|-------|-----------|-------------|
| Monthly ($14.99) | $14.99 | $0.73 | $14.26 |
| Annual ($119.88 = $9.99/mo) | $119.88 | $3.77 | $116.11 ($9.68/mo) |

---

## Break-Even Analysis

**Fixed costs:** ~$16.10/month
**Net revenue per user (monthly):** $14.26
**Break-even:** 2 paying users (2 × $14.26 = $28.52, minus $16.10 = $12.42 surplus)

Realistically, 3 paying users covers fixed costs with comfortable margin.

---

## Scaling Projections

| Users | Monthly Revenue (Gross) | Stripe Fees | Hosting | Other Fixed | Net Profit | Notes |
|-------|------------------------|-------------|---------|-------------|------------|-------|
| 0 | $0 | $0 | $5.70 | $10.40 | -$16.10 | Current state |
| 3 | $44.97 | $2.19 | $5.70 | $10.40 | $26.68 | Break-even+ |
| 10 | $149.90 | $7.30 | $5.70 | $10.40 | $126.50 | Covers all costs, modest income |
| 25 | $374.75 | $18.25 | $5.70 | $10.40 | $340.40 | |
| 50 | $749.50 | $36.50 | $8.00 | $10.40 | $694.60 | May need CPU upgrade |
| 100 | $1,499.00 | $73.00 | $12.00 | $10.40 | $1,403.60 | shared-cpu-2x, more memory |
| 250 | $3,747.50 | $182.50 | $20.00 | $30.40 | $3,514.60 | Resend paid tier, bigger VM |
| 500 | $7,495.00 | $365.00 | $30.00 | $30.40 | $7,069.60 | May need Postgres migration |
| 1,000 | $14,990.00 | $730.00 | $50.00 | $30.40 | $14,179.60 | Definitely need Postgres |

**Key observations:**
- Gross margins are ~95% at scale because SQLite + Flask on a single machine is absurdly cheap.
- The inflection point for infrastructure cost is ~500 users, where SQLite write contention may force a Postgres migration (~$15-30/month for managed Postgres).
- Stripe fees are the largest per-unit cost at every scale.

---

## 12-Month Projection (Conservative)

Assumes: launch Month 1, slow organic growth, 20% monthly churn.

| Month | New Signups | Conversions (10%) | Active Paying | MRR | Costs | Net |
|-------|------------|-------------------|---------------|-----|-------|-----|
| 1 | 20 | 2 | 2 | $28.52 | $16.10 | $12.42 |
| 2 | 15 | 2 | 3 | $42.78 | $16.10 | $26.68 |
| 3 | 15 | 2 | 4 | $57.04 | $16.10 | $40.94 |
| 4 | 20 | 2 | 5 | $71.30 | $16.10 | $55.20 |
| 5 | 20 | 2 | 6 | $85.56 | $16.10 | $69.46 |
| 6 | 25 | 3 | 7 | $99.82 | $16.10 | $83.72 |
| 7 | 25 | 3 | 8 | $114.08 | $16.10 | $97.98 |
| 8 | 30 | 3 | 9 | $128.34 | $16.10 | $112.24 |
| 9 | 30 | 3 | 10 | $142.60 | $16.10 | $126.50 |
| 10 | 35 | 4 | 12 | $171.12 | $16.10 | $155.02 |
| 11 | 35 | 4 | 14 | $199.64 | $16.10 | $183.54 |
| 12 | 40 | 4 | 16 | $228.16 | $17.00 | $211.16 |

**Year 1 total net:** ~$1,175 (excluding developer time)

**Note:** This is conservative. 20% monthly churn means average user stays ~5 months. Better retention dramatically changes the math — at 10% churn (10-month average), Month 12 active users would be ~25-30 instead of 16.

---

## Developer Time (Opportunity Cost)

This is the elephant in the room. At a market rate of $150/hour for a senior developer:

| Activity | Hours/Week | Monthly Cost (opportunity) |
|----------|-----------|--------------------------|
| Feature development | 10 | $6,000 |
| Bug fixes + maintenance | 3 | $1,800 |
| Marketing + growth | 2 | $1,200 |
| Operations + monitoring | 1 | $600 |
| **Total** | **16** | **$9,600** |

At $9,600/month opportunity cost, break-even on developer time requires:
- $9,600 / $14.26 net per user = **673 paying users**

This is why solo founder projects are either passion projects or need to find PMF fast. The infrastructure costs are trivial. The human time is not.

---

## Cost Reduction Levers

| Lever | Current | Optimized | Savings |
|-------|---------|-----------|---------|
| Fly.io auto-stop | min_machines=1 | min_machines=0 (accept cold starts) | ~$2/month |
| Annual pricing | Not offered yet | 33% of users on annual | Reduces Stripe fees (fewer transactions) |
| Stripe → Paddle/Lemon Squeezy | 2.9% + $0.30 | 5% flat (but includes tax handling) | Net negative on fees but saves tax compliance time |
| Self-host email | Resend | Postfix on Fly.io | Saves $20/month at scale, adds ops burden |
