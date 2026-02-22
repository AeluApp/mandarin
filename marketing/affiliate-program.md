# Affiliate Program Design

---

## Program Overview

**Name:** Mandarin Partner Program
**Commission:** 30% recurring for the lifetime of referred customers
**Cookie duration:** 90 days
**Payout threshold:** $50 minimum
**Payment method:** PayPal or Stripe Connect
**Tracking:** Unique referral links with UTM parameters + first-party cookie

---

## Commission Structure

### Standard Tier (all partners)
- **30% recurring commission** on all payments from referred users
- At $12/month, that's **$3.60/month per referred paying user**
- Recurring means: as long as the user stays subscribed, the partner earns
- 10 referred paying users = **$36/month passive income** for the partner

### Why 30% Recurring

- **Industry standard for SaaS affiliates is 20-30%.** 30% is on the generous end, which matters when you're unknown and need partners to take a chance on you.
- **Recurring beats one-time.** A one-time $10 bounty sounds better initially, but $3.60/month × 12 months = $43.20. Partners who understand recurring commissions prefer this.
- **Your margins support it.** At $12/month with ~$0.50 in infrastructure costs, paying $3.60 in commission still leaves you $7.90/user/month. That's a healthy margin.
- **It aligns incentives.** Partners are motivated to send quality traffic (users who stick around) because their commission depends on retention, not just signups.

### Upgrade Tier (top partners, manual invitation only)
- **40% recurring** for partners who refer 50+ paying users
- **Custom landing page** co-branded with their name/brand
- **Early access** to new features for their audience
- **Direct line** to you for feature requests from their community

---

## Cookie & Attribution

### How Tracking Works

1. Partner shares their unique link: `mandarinapp.com/?ref=PARTNER_CODE`
2. Visitor clicks link → first-party cookie set with `ref=PARTNER_CODE`, expires in 90 days
3. If visitor signs up (free), the partner code is stored in the user record
4. If user upgrades to paid within 90 days of clicking the link, the partner gets commission
5. Commission continues for as long as the user remains a paying subscriber

### Attribution Rules
- **First-click attribution**: the first partner link clicked gets credit (not the last)
- **90-day cookie window**: if a user clicks a partner link, signs up 60 days later, and upgrades 29 days after that — the partner still gets credit (89 days total < 90)
- **No self-referrals**: partners cannot refer themselves
- **No coupon stacking**: partner discount codes don't stack with other promotions

### Technical Implementation (when you build this)

Store in your users table:
```sql
ALTER TABLE user ADD COLUMN referred_by_partner TEXT;
ALTER TABLE user ADD COLUMN referral_clicked_at TEXT;
```

Track in a commissions table:
```sql
CREATE TABLE affiliate_commission (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_code TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    payment_date TEXT NOT NULL,
    paid_out INTEGER DEFAULT 0,
    payout_date TEXT,
    FOREIGN KEY (user_id) REFERENCES user(id)
);
```

---

## Partner Discount Codes

Each partner gets a unique discount code their audience can use:

- **Standard discount: 20% off first 3 months**
- Code format: `PARTNER20` (e.g., `OLLEH20` for Olle from Hacking Chinese)
- This reduces price from $12 to $9.60/month for months 1-3
- Partner still earns 30% of the discounted amount ($2.88/month for months 1-3, then $3.60/month ongoing)

### Why 20% Off (Not More)

- **20% is meaningful but not desperate.** 50% off signals low confidence in the product.
- **3 months is long enough** for users to build a habit and see results. After 3 months at full price, they stay because the app works — not because of a discount.
- **The partner's endorsement is the real value.** The discount is a sweetener, not the pitch.

---

## Partner Types & What They Get

### Type 1: Content Creator (YouTuber, Blogger, Podcaster)
**What they get:**
- Free lifetime full-access account
- Unique referral link + discount code
- Partner content kit (see partner-kit.md) with talking points, screenshots, comparison data
- Early access to new features (2 weeks before public)
- Featured on "recommended by" section of landing page (with permission)

**What they do:**
- Mention the app in a video/post/episode (how and when is 100% their choice)
- Include referral link in description/show notes
- Optional: dedicated review video/post

### Type 2: Teacher / Tutor
**What they get:**
- Free lifetime full-access account
- 5 free accounts for their students (3 months each)
- Unique referral link + discount code
- "Recommended by [Teacher Name]" badge for their profile
- Input on curriculum priorities (we want to build what teachers need)

**What they do:**
- Recommend the app to their students as supplemental practice
- Include referral link in course materials or student communications
- Optional: provide a testimonial

### Type 3: Complementary App/Tool
**What they get:**
- Technical integration discussion (API access, data sharing where appropriate)
- Cross-promotion: we mention them, they mention us
- Co-branded content (blog post, comparison guide)

**What they do:**
- Link to us from their app/site where relevant
- Optional: in-app recommendation ("for SRS practice, try Mandarin")

### Type 4: Course Creator / Online School
**What they get:**
- Bulk licensing discounts (10+ seats: 25% off per seat)
- Custom onboarding for their students (pre-set HSK level, curriculum alignment)
- Analytics dashboard showing their students' aggregate progress
- White-label option (future — their branding on our platform)

**What they do:**
- Bundle the app with their courses
- Recommend as required or optional supplemental tool
- Include in course materials

---

## Onboarding Flow

### Step 1: Application
Partner fills out a form (on affiliates landing page):
- Name / brand name
- Platform (YouTube, blog, podcast, classroom, etc.)
- Audience size (approximate)
- Content focus
- Why they're interested

### Step 2: Review (manual — you review every application)
- Check their content — is it real? Is it Chinese-learning related?
- Check audience — does it overlap with your target users?
- Reject: spam, unrelated content, fake accounts
- Accept: anyone with genuine Chinese learning content and a real audience (even small)

### Step 3: Welcome Email
Send the welcome email from partner-outreach.md with:
- Their unique referral link
- Their unique discount code
- Link to the partner content kit
- Their free lifetime account credentials

### Step 4: First Check-in (Day 14)
- Email asking if they've had a chance to try the app
- Ask if they need anything for a review/mention
- Offer a screen recording walkthrough call (15 min) if helpful

### Step 5: Ongoing
- Monthly email with their commission stats (referred users, earnings, payout)
- Quarterly check-in: anything they'd like to see in the product?
- Annual: personal thank-you note if they've been an active partner

---

## Payout Schedule

| Event | Timeline |
|-------|----------|
| Commission earned | When referred user makes a payment |
| Commission confirmed | 30 days after payment (refund window) |
| Payout eligible | When confirmed balance reaches $50 |
| Payout issued | 1st of each month for previous month's confirmed commissions |
| Payment method | PayPal or Stripe Connect (partner's choice) |

### Refund Handling
- If a referred user requests a refund within 30 days, the commission is reversed
- This is why there's a 30-day confirmation window before commissions become eligible
- After 30 days, the commission is final regardless of future refunds or cancellations

---

## Terms & Conditions (Key Points)

Draft these into a proper legal document before launch. Key provisions:

1. **No misleading claims.** Partners may not claim the app does things it doesn't. No "guarantees fluency" or "pass HSK in 2 weeks."
2. **No paid advertising on branded terms.** Partners may not bid on "Mandarin app" or similar branded keywords in paid ads.
3. **No spam.** No unsolicited bulk email, no fake reviews, no review manipulation.
4. **Disclosure required.** Partners must disclose the affiliate relationship per FTC guidelines. "I earn a commission if you sign up through my link" is sufficient.
5. **We can terminate.** Either party can end the relationship with 30 days notice. Earned commissions are still paid out.
6. **Commission rate can change.** With 60 days notice. Existing referred users keep their original rate.
7. **Cookie window can change.** With 30 days notice.

---

## Metrics to Track

| Metric | Target | Red Flag |
|--------|--------|----------|
| Partner signup → first referral | Within 60 days | No referral after 90 days (dormant partner) |
| Click → signup conversion | 10-20% | < 5% (partner audience mismatch) |
| Signup → paid conversion | 5-12% | < 3% (same as organic baseline) |
| Referred user retention (30-day) | 40-60% | < 30% (low quality traffic) |
| Average commission per partner/month | $10-50 | — |
| Active partners (1+ referral/month) | 20-30% of total partners | < 10% (program not compelling) |

### When to Promote a Partner to Upgrade Tier
- 50+ paying referrals
- Consistent monthly referrals for 3+ months
- High retention on their referred users (>50% 30-day retention)
- Proactive engagement (gives feedback, creates content regularly)

---

## Timeline

| Phase | When | What |
|-------|------|------|
| Design | Pre-launch | This document (done) |
| Build tracking | With multi-user auth | Referral link tracking, cookie, commission table |
| Soft launch | Launch week | Invite 5-10 partners manually |
| Application page | Launch + 2 weeks | Public affiliate signup page |
| First payouts | Launch + 3 months | First $50+ balances hit payout |
| Scale | Launch + 6 months | Actively recruit, upgrade top partners |
