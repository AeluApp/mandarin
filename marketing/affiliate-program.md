# Affiliate Program Design

---

## Program Overview

**Name:** Aelu Partner Program
**Commission:** 25% recurring, capped at 24 months per referred user (pilot rate — see escalation criteria)
**Cookie duration:** 90 days
**Payout threshold:** $50 minimum
**Payment method:** PayPal or Stripe Connect
**Tracking:** Unique referral links with UTM parameters + first-party cookie

---

## Commission Structure

### Standard Tier (all partners)
- **25% recurring commission** on all payments from referred users, **for up to 24 months** per referred user
- At $14.99/month, that's **$3.75/month per referred paying user**
- After 24 months, the commission for that user ends — the partner has earned up to **$90 per user** over 2 years
- 10 referred paying users = **$37.50/month passive income** for the partner (during the commission window)

### Why 25% Recurring with a 24-Month Cap

- **Industry standard for SaaS affiliates is 20-30%.** 25% is competitive enough to attract partners while protecting long-term margins. Most SaaS affiliate programs cap recurring commissions at 12-24 months — lifetime is the outlier, not the norm.
- **Recurring beats one-time.** A one-time $10 bounty sounds fine initially, but $3.75/month x 24 months = $90. Partners who understand recurring commissions prefer this.
- **The cap protects margins on loyal users.** A user who stays 5 years generates $900 in revenue. Without a cap, $270 goes to a partner who may have stopped promoting 4 years ago. With a 24-month cap, the partner earns $90 — still generous — and the remaining $630+ in margin fuels product development.
- **It aligns incentives.** Partners are motivated to send quality traffic (users who stick around) because their commission depends on retention, not just signups. The 24-month window is long enough that this incentive fully applies.
- **Your margins stay healthy.** At $14.99/month with ~$0.50 infrastructure + $0.45 payment processing, paying $3.75 in commission leaves $10.29/user/month. After 24 months: $14.04/user/month.

### Data-Driven Escalation to 30%

The 25% rate is a **pilot rate** for the first 6 months of the program. After 6 months, review these metrics:
- Referred user 30-day retention: target >40%
- Referred user free-to-paid conversion: target >8%
- Average partner engagement: target >20% of partners making 1+ referral/month

If all three metrics hit targets, escalate to **30% recurring (still capped at 24 months)**. This gives you data before locking in a more generous rate. Announce the increase to existing partners — it applies to all new referrals going forward.

### Upgrade Tier (top partners, manual invitation only)
- **35% recurring** (capped at 24 months) for partners who refer 50+ paying users
- **Custom landing page** co-branded with their name/brand
- **Early access** to new features for their audience
- **Direct line** to you for feature requests from their community
- **Priority support** for their referred users (faster response times)

### Teacher Partner Track

Teachers are the highest-leverage partners: they have direct, recurring access to new cohorts of Chinese learners every semester. They deserve a dedicated track.

**Teacher Partner Commission:**
- **35% recurring** on classroom subscriptions (per-student and semester), capped at 24 months
- At $8/student/month: **$2.80/student/month** to the teacher
- 30 students = **$84/month** — meaningful supplemental income for a Chinese teacher
- New cohorts each semester create a self-renewing pipeline

**Additional Teacher Benefits:**
- 5 free student accounts (3 months each) to trial with their class before committing
- Input on curriculum priorities — teachers shape what gets built next
- "Recommended by [Teacher Name]" badge on their profile
- Invitation to annual Teacher Advisory call (feedback session with the developer)

**Why Teachers Get 35% From Day One:**
- Highest conversion rate of any partner type (students are told to use it)
- Lowest churn (semester-long commitment, class accountability)
- Self-renewing (new cohort every semester without re-promoting)
- The 35% on classroom pricing ($8/student) still yields $5.20/student/month margin — healthy for a B2B channel

---

## Cookie & Attribution

### How Tracking Works

1. Partner shares their unique link: `aeluapp.com/?ref=PARTNER_CODE`
2. Visitor clicks link → first-party cookie set with `ref=PARTNER_CODE`, expires in 90 days
3. If visitor signs up (free), the partner code is stored in the user record
4. If user upgrades to paid within 90 days of clicking the link, the partner gets commission
5. Commission continues for up to 24 months from the user's first payment date

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
    commission_rate REAL NOT NULL DEFAULT 0.25,
    payment_date TEXT NOT NULL,
    first_payment_date TEXT,  -- tracks when 24-month window started
    paid_out INTEGER DEFAULT 0,
    payout_date TEXT,
    FOREIGN KEY (user_id) REFERENCES user(id)
);
CREATE INDEX idx_commission_partner ON affiliate_commission(partner_code);
CREATE INDEX idx_commission_user ON affiliate_commission(user_id);
```

Commission calculation logic:
```python
# Before recording a commission, check 24-month cap
first_payment = get_first_payment_date(partner_code, user_id)
if first_payment and (now - first_payment).days > 730:  # 24 months
    # Commission window expired for this user — no commission recorded
    return
commission = payment_amount * commission_rate  # 0.25 standard, 0.35 upgrade/teacher
```

---

## Partner Discount Codes (Opt-In)

Partners may **optionally** request a discount code for their audience. This is not standard — some partners prefer to recommend the product on its merits alone, and we respect that.

**If a partner requests a discount code:**
- **15% off first 3 months**
- Code format: `PARTNER15` (e.g., `OLLEH15` for Olle from Hacking Chinese)
- This reduces price from $14.99 to $12.74/month for months 1-3
- Partner earns 25% of the discounted amount ($3.19/month for months 1-3, then $3.75/month ongoing)

### Why Opt-In, Not Standard

- **The partner's endorsement is the real value.** If a genuine recommendation isn't enough to convert, a discount won't fix the underlying mismatch. Making it opt-in lets partners decide whether their audience needs a sweetener.
- **Discounts anchor users to a lower price.** The jump from $12.74 to $14.99 at month 4 creates a friction point that increases churn. Partners who understand retention prefer clean pricing.
- **It reduces both revenue and partner commission simultaneously.** Everyone earns less during the discount window. Partners who skip the discount earn more per user from day one.

### Why 15% (Not 20% or More)

- **15% is enough to feel meaningful ($2.25/month savings) without signaling desperation.** 20%+ off a $14.99 product suggests you don't believe the price is justified.
- **3 months is long enough** for users to build a habit and see results. After 3 months at full price, they stay because the app works — not because of a discount.

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

### Type 2: Teacher / Tutor (→ Teacher Partner Track)
**See the Teacher Partner Track above for dedicated commission rates (35% on classroom pricing).**

**What they get:**
- Free lifetime full-access account
- 5 free accounts for their students (3 months each)
- Unique referral link + optional discount code
- "Recommended by [Teacher Name]" badge for their profile
- Input on curriculum priorities (we want to build what teachers need)
- Invitation to annual Teacher Advisory call

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
- Optional: in-app recommendation ("for SRS practice, try Aelu")

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
2. **No paid advertising on branded terms.** Partners may not bid on "Aelu" or similar branded keywords in paid ads.
3. **No spam.** No unsolicited bulk email, no fake reviews, no review manipulation.
4. **Disclosure required.** Partners must disclose the affiliate relationship per FTC guidelines. "I earn a commission if you sign up through my link" is sufficient.
5. **We can terminate.** Either party can end the relationship with 30 days notice. Earned commissions are still paid out.
6. **Commission rate can change.** With 60 days notice. Existing referred users keep their original rate. Rate increases (e.g., 25% → 30% escalation) apply to new referrals only by default, but may be retroactively applied to all active referrals as a goodwill gesture.
7. **Cookie window can change.** With 30 days notice.
8. **Commission cap is per referred user.** Each referred user generates commissions for up to 24 months from their first payment. This window is fixed at partner onboarding and does not change retroactively.

---

## Metrics to Track

| Metric | Target | Red Flag | Escalation Trigger |
|--------|--------|----------|--------------------|
| Partner signup → first referral | Within 60 days | No referral after 90 days (dormant partner) | — |
| Click → signup conversion | 10-20% | < 5% (partner audience mismatch) | — |
| Signup → paid conversion | 5-12% | < 3% (same as organic baseline) | >8% triggers rate escalation review |
| Referred user retention (30-day) | 40-60% | < 30% (low quality traffic) | >40% triggers rate escalation review |
| Average commission per partner/month | $10-40 | — | — |
| Active partners (1+ referral/month) | 20-30% of total partners | < 10% (program not compelling) | >20% triggers rate escalation review |
| Commission cap utilization | Track how many users hit 24-month cap | — | If <5% hit cap in year 1, cap is working as intended |

### When to Promote a Partner to Upgrade Tier (35%)
- 50+ paying referrals
- Consistent monthly referrals for 3+ months
- High retention on their referred users (>50% 30-day retention)
- Proactive engagement (gives feedback, creates content regularly)
- Note: upgrade to 35% still subject to 24-month cap per referred user

---

## Timeline

| Phase | When | What |
|-------|------|------|
| Design | Pre-launch | This document (done) |
| Build tracking | With multi-user auth | Referral link tracking, cookie, commission table with 24-month cap |
| Soft launch | Launch week | Invite 5-10 partners manually at 25% pilot rate |
| Application page | Launch + 2 weeks | Public affiliate signup page |
| Teacher outreach | Launch + 4 weeks | Dedicated outreach to Chinese teachers (35% teacher track) |
| First payouts | Launch + 3 months | First $50+ balances hit payout |
| Rate review | Launch + 6 months | Review escalation metrics; if targets met, increase to 30% |
| Scale | Launch + 6 months | Actively recruit, upgrade top partners to 35% tier |
