# Financial Model: Aelu

## Cost Structure

### Fixed Costs (Monthly)

| Item | Cost | Notes |
|------|------|-------|
| Fly.io hosting (shared-cpu-1x, 256MB) | $5 | Current tier; scales to $20 for dedicated |
| Fly.io volume (1GB SSD) | $0.15 | Database storage |
| Litestream backups (S3-compatible) | $0.50 | ~500MB backup stream |
| Domain (aelu.app) | $1.00 | $12/year amortized |
| Apple Developer Program | $8.25 | $99/year amortized |
| Email sending (Postmark or Resend) | $0 - $10 | Free tier covers <1000 users |
| **Total fixed** | **$14.90 - $39.90** | |

### Variable Costs (Per User)

| Item | Cost per User/Month | Notes |
|------|---------------------|-------|
| LLM API tokens | $0.00 | Zero runtime LLM usage (ADR-006) |
| Database storage | ~$0.001 | ~50KB per user (progress, reviews, sessions) |
| Bandwidth | ~$0.01 | ~5MB per user per month |
| Email | ~$0.01 | ~3 emails per user per month |
| **Total variable** | **~$0.02** | |

### Cost at Scale

| Users (DAU) | Hosting | Storage | Email | Total Monthly | Per-User Cost |
|-------------|---------|---------|-------|---------------|---------------|
| 100 | $5 | $0.15 | $0 | ~$15 | $0.15 |
| 1,000 | $10 | $0.50 | $10 | ~$30 | $0.03 |
| 5,000 | $20 | $2.00 | $25 | ~$60 | $0.012 |
| 10,000 | $40 | $5.00 | $50 | ~$110 | $0.011 |
| 50,000 | $200 | $25.00 | $100 | ~$350 | $0.007 |

The zero-LLM architecture means costs scale with infrastructure, not with AI API consumption. This is Aelu's structural cost advantage over competitors that use GPT/Claude at runtime.

At 10,000 DAU, infrastructure costs would require migrating from SQLite to PostgreSQL (see ADR-001 revisit trigger), adding ~$15-30/mo for a managed PostgreSQL instance.

---

## Revenue Model

### Freemium Tiers

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | Core SRS engine, 5 drill types, HSK 1-2 content, basic progress tracking |
| **Premium** | $9.99/mo or $79.99/yr | All 12 drill types, HSK 1-9 content, graded reader, media shelf, extensive listening, grammar drills, diagnostics, tone grading, export, advanced analytics |
| **Classroom** | $4.99/student/mo | Teacher dashboard, student progress, LTI integration, bulk enrollment, custom content |

### Revenue Projections

Assumptions:
- Free-to-paid conversion rate: 5% (industry average for education apps is 2-8%)
- Annual plan uptake: 40% of paid users (reduces churn, higher LTV)
- Classroom: 10 teachers with 20 students each at launch, growing
- Monthly churn on paid plan: 8% (industry average is 5-12%)

| Metric | Month 3 | Month 6 | Month 12 | Month 24 |
|--------|---------|---------|----------|----------|
| Registered users | 500 | 2,000 | 8,000 | 25,000 |
| DAU (20% of registered) | 100 | 400 | 1,600 | 5,000 |
| Paid users (5% conversion) | 25 | 100 | 400 | 1,250 |
| Monthly revenue (individual) | $250 | $1,000 | $4,000 | $12,500 |
| Classroom revenue | $0 | $500 | $2,000 | $5,000 |
| **Total MRR** | **$250** | **$1,500** | **$6,000** | **$17,500** |
| Monthly costs | $15 | $25 | $60 | $200 |
| **Net margin** | 94% | 98.3% | 99% | 98.9% |

---

## Break-Even Analysis

### Time to Break-Even

Fixed costs (development time excluded): ~$15/month.

```
Break-even users = Fixed costs / (ARPU - Variable cost per user)
                 = $15 / ($0.50 - $0.02)
                 = 32 paid users
```

At 5% conversion rate, break-even requires ~640 registered users. With organic growth (no paid acquisition), this is achievable within 3-6 months of launch.

### Development Cost Recovery

If development time is valued at $150/hour and total development is ~500 hours:
- Total development cost: ~$75,000
- At $6,000 MRR (month 12 projection): payback in ~12.5 months from month 12 = ~24 months total

This is a long payback period. The primary value proposition for the developer is the learning system itself (personal use) with revenue as a secondary benefit.

---

## Unit Economics

### Lifetime Value (LTV)

```
LTV = ARPU / Monthly Churn Rate
```

| Segment | Monthly ARPU | Churn Rate | LTV |
|---------|-------------|-----------|-----|
| Monthly paid | $9.99 | 8% | $125 |
| Annual paid | $6.67/mo ($79.99/yr) | 3%/mo (implicit) | $222 |
| Classroom (per student) | $4.99 | 5% (institutional) | $100 |
| Blended | $7.50 | 6% | $125 |

### Customer Acquisition Cost (CAC)

Without paid acquisition:
- Organic (word of mouth, App Store search): CAC = ~$0 (time investment only)
- Content marketing (blog, YouTube): CAC = ~$5-10 (time to create content)
- Affiliate partners (20% commission): CAC = $2.00 (first-month commission on $9.99)

With paid acquisition (future):
- Apple Search Ads: estimated $3-8 per install, 5% conversion = $60-160 CAC
- Google Ads: estimated $2-5 per click, 10% signup, 5% conversion = $40-100 CAC

### LTV:CAC Ratio

| Channel | CAC | LTV | LTV:CAC | Verdict |
|---------|-----|-----|---------|---------|
| Organic | ~$0 | $125 | infinite | Best channel |
| Affiliate | $2 | $125 | 62.5:1 | Excellent |
| Content marketing | $5-10 | $125 | 12.5-25:1 | Good |
| Apple Search Ads | $60-160 | $125 | 0.8-2.1:1 | Marginal/unprofitable |
| Google Ads | $40-100 | $125 | 1.25-3.1:1 | Marginal |

Paid acquisition is only viable if (a) LTV increases through annual plan incentives or (b) conversion rates improve through better onboarding. Focus on organic and affiliate growth.

---

## Sensitivity Analysis

### Key Levers

| Lever | Current | Optimistic | Impact on Month-12 MRR |
|-------|---------|-----------|----------------------|
| Conversion rate | 5% | 8% | +60% ($9,600) |
| Monthly churn | 8% | 5% | +25% ($7,500) |
| Annual plan uptake | 40% | 60% | +15% ($6,900) |
| Classroom adoption | 10 teachers | 30 teachers | +$2,000 ($8,000) |
| Price increase to $12.99 | -- | -- | +30% ($7,800) |

Conversion rate is the highest-impact lever. Improving onboarding (first-week session count, per survival analysis) is the most cost-effective way to improve conversion.

### Downside Scenario

If growth stalls at 2,000 registered users with 3% conversion:
- 60 paid users x $9.99 = $600/mo MRR
- Costs: $25/mo
- Net: $575/mo -- still profitable, but insufficient to justify ongoing development investment

### Upside Scenario

If a classroom partnership with a university drives 500 students:
- 500 students x $4.99 = $2,495/mo from one contract
- Marginal cost: ~$10/mo
- This is the most capital-efficient growth path: institutional sales with near-zero marginal cost

---

## Key Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Apple rejects Capacitor app | Low | High (lose iOS channel) | Maintain native plugin usage; comply with App Store guidelines |
| SQLite scaling ceiling hit | Medium (at 5K+ DAU) | Medium | PostgreSQL migration path documented in ADR-001 |
| Competitor with LLM features | High | Medium | Lean into deterministic advantage: predictable costs, offline capability, privacy |
| Low conversion rate (<3%) | Medium | High | Invest in onboarding, free tier value, social proof |
| Apple in-app purchase requirement | Medium | Medium (30% revenue cut) | Price to absorb App Store commission; offer web-direct signup |
