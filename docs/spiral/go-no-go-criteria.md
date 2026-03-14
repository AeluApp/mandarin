# Go/No-Go Criteria — PMF Decision Framework

> Last updated: 2026-03-10
> Review cadence: At each milestone checkpoint

## Purpose

This document defines three milestones with explicit go/no-go criteria. At each checkpoint, the decision is binary: go (continue investing) or no-go (pivot or wind down). No ambiguity. No "let's give it another month and see."

---

## Milestone 1: Proof of Interest (Month 3)

**Target date:** 3 months after public launch (TBD)
**Question:** Do people care enough to try it?

### Go Criteria (ALL must be met)

| Criterion | Metric | How to Measure |
|-----------|--------|---------------|
| Signups | 20+ accounts created | `SELECT COUNT(*) FROM user` |
| Engagement | 5+ users completing 10+ sessions | `SELECT COUNT(DISTINCT user_id) FROM session_log GROUP BY user_id HAVING COUNT(*) >= 10` |
| Organic reach | 1+ user who found Aelu without direct outreach | `user.utm_source` or ask via feedback form |
| Retention signal | 3+ users active in week 4 (30-day retention) | `SELECT COUNT(DISTINCT user_id) FROM session_log WHERE created_at > date('now', '-7 days') AND user_id IN (SELECT id FROM user WHERE created_at < date('now', '-23 days'))` |

### No-Go Actions

If criteria are NOT met:

1. **Diagnose:** Where did the funnel break?
   - No signups → Marketing problem. Nobody knows Aelu exists. Try different channels (ProductHunt, HackerNews, language learning forums).
   - Signups but no engagement → Onboarding problem. Users signed up but didn't complete a session. Check: is the first session experience clear? Is the value proposition immediate?
   - Engagement but no retention → Product problem. Users tried it but didn't come back. Check: is the learning experience compelling? Is the feedback honest or discouraging?
2. **Pivot options:**
   - Different audience: Target heritage speakers instead of adult beginners. Target HSK test preppers instead of general learners.
   - Different pricing: Free tier with premium upgrade. Or lifetime access for $99.
   - Different modality: Focus on reading only (graded reader as primary product). Or focus on listening only.
3. **Timeline:** 2 weeks to diagnose and decide. Then either pivot (reset Milestone 1 clock) or wind down.

---

## Milestone 2: Proof of Value (Month 6)

**Target date:** 6 months after public launch
**Question:** Will people pay for this, and do they get value from it?

### Go Criteria (ALL must be met)

| Criterion | Metric | How to Measure |
|-----------|--------|---------------|
| Total signups | 100+ accounts | `SELECT COUNT(*) FROM user` |
| Paying users | 20+ active subscriptions | `SELECT COUNT(*) FROM user WHERE subscription_tier = 'paid' AND subscription_status = 'active'` |
| 30-day retention | 40%+ of Month 5 users still active in Month 6 | Cohort analysis on session_log |
| Learning outcomes | 10+ users with items in "stable" or "durable" mastery stage | `SELECT COUNT(DISTINCT user_id) FROM progress WHERE mastery_stage IN ('stable', 'durable')` |
| Satisfaction | NPS > 20 (measured via in-app survey or email) | Manual survey |
| Revenue | $285+ MRR (20 users × $14.26 net) | Stripe dashboard |

### No-Go Actions

If criteria are NOT met:

1. **Diagnose:** What's failing?
   - Not enough signups → Growth problem. Organic isn't enough. Consider: small paid experiment ($100 on Google Ads), partnership with a Mandarin teacher, guest post on a popular language learning blog.
   - Signups but low conversion to paid → Value proposition problem. Users don't see enough value to pay $14.99/month. Check: is the free experience too good (no reason to upgrade)? Or too bad (no proof of value)?
   - Paying users but low retention → Product-market fit not proven. Users pay but leave. Why? Exit survey. Is the content repetitive? Is progress too slow? Is the interface frustrating?
   - Low NPS → Identify detractors. What do they dislike? Fix the top complaint.
2. **Pivot options:**
   - Pricing: Drop to $9.99/month (lower barrier). Or offer $4.99/month "maintenance mode" for users who learned what they need and just want spaced repetition.
   - Feature: Double down on whatever feature users mention most in feedback. If it's the graded reader, make that the product. If it's the SRS engine, make that the product.
   - Market: Pivot to B2B (sell to Chinese language schools as a supplementary tool). Different sales motion but potentially higher LTV.
3. **Wind-down protocol:** If no path forward is identified within 2 weeks:
   - Notify existing paying users: "Aelu will shut down in 60 days."
   - Stop billing immediately.
   - Export user data (GDPR compliance).
   - Open-source the codebase (optional — depends on IP considerations).

---

## Milestone 3: Proof of Sustainability (Month 12)

**Target date:** 12 months after public launch
**Question:** Is this a viable business?

### Go Criteria (ALL must be met)

| Criterion | Metric | How to Measure |
|-----------|--------|---------------|
| Total signups | 500+ accounts | `SELECT COUNT(*) FROM user` |
| Paying users | 100+ active subscriptions | Stripe dashboard |
| MRR | $1,500+ | Stripe dashboard |
| 30-day retention | 50%+ | Cohort analysis |
| 90-day retention | 30%+ | Cohort analysis |
| NPS | > 40 | Survey |
| Monthly churn | < 15% | (Churned users / start-of-month users) |
| Organic growth | 20%+ of new users from referral or organic search | UTM tracking |
| LTV:CAC | > 3:1 | Computed |

### Go → Scale Actions

If all criteria are met:

1. **Invest in growth:**
   - Allocate budget for paid acquisition ($500-1,000/month to start).
   - Build referral program (affiliate_partner, referral_tracking tables are ready).
   - Hire a part-time content writer for SEO/blog posts.
2. **Invest in product:**
   - Listening with real audio (edge-tts pre-generation pipeline).
   - Android app (Capacitor shell already staged).
   - Community features? Only if users ask for it. Don't build speculatively.
3. **Invest in infrastructure:**
   - Load test for 500+ users (D-005 from board).
   - Evaluate Postgres migration timeline.
   - Add monitoring (Sentry is already integrated, add dashboards).

### No-Go → Wind Down or Pivot

If criteria are NOT met at Month 12:

1. **Honest assessment:** Has there been consistent improvement month-over-month? If growth is steady but below targets, consider extending the timeline by 3 months.
2. **If stagnant or declining:** Execute wind-down protocol.
3. **Pivot options at this stage are limited.** 12 months of data should make the diagnosis clear. Either the market wants this (growth is happening, just slowly) or it doesn't (no organic traction despite a working product).

---

## What "Pivot" Means

A pivot is not "change everything." It's changing one fundamental assumption while keeping what works.

| Pivot Type | What Changes | What Stays |
|-----------|-------------|-----------|
| Audience pivot | Target heritage speakers, not beginners | SRS engine, content, infrastructure |
| Pricing pivot | Freemium model or lower price point | All product features |
| Modality pivot | Focus on reading-only (graded reader product) | SQLite, Flask, SRS engine, content library |
| Language pivot | Add Japanese/Korean, become multi-language | All infrastructure, SRS engine, UI |
| Business model pivot | B2B (sell to schools/tutors) | Product, add admin/classroom features (lti_routes.py exists) |
| Technology pivot | Native app instead of web-wrapped | Content, SRS engine, business logic |

**Rule:** Only pivot on ONE dimension at a time. Changing audience AND pricing AND modality simultaneously is not a pivot — it's a new product.

---

## Milestone Tracking

| Milestone | Target Date | Status | Go/No-Go | Decision Date |
|-----------|-------------|--------|----------|---------------|
| M1: Proof of Interest | TBD (Launch + 3 months) | NOT STARTED | — | — |
| M2: Proof of Value | TBD (Launch + 6 months) | NOT STARTED | — | — |
| M3: Proof of Sustainability | TBD (Launch + 12 months) | NOT STARTED | — | — |

**Current status:** Pre-launch. Product is built. Cloud deployment works. No external users yet. The clock starts when the first non-Jason user signs up.
