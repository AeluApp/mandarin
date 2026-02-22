# Referral Program Design

**Program type:** User-to-user referrals (regular learners inviting friends)
**Distinct from:** [Affiliate Program](affiliate-program.md) (content creator/partner affiliates, 30% recurring commission)

---

## 1. Philosophy

The most credible growth channel for a language learning app is one serious learner telling another: "This is what I actually use." Not an ad. Not an influencer read. A real person who has done real study sessions saying, "This helped me."

Referrals fit this brand because they are the organic version of what we already want: people who care about learning Chinese finding us through people who care about learning Chinese. The signal-to-noise ratio is high. The intent is genuine.

But most referral programs are manipulation wearing a friendly mask. "Get 5 friends and earn a free month!" creates pressure to spam your contacts. Leaderboards turn sharing into competition. Points systems make the referral itself the goal, detaching it from the product entirely.

We do none of that.

Our referral system operates on one principle: **if you genuinely think someone would benefit from this tool, make it easy to share it with them.** The incentive exists to say thank you, not to manufacture behavior. Both parties receive equal value. There is no escalating reward tier that turns learners into salespeople. There is no urgency. The link is there when you want it, invisible when you don't.

If someone never refers a single person, that is completely fine. The app works the same.

---

## 2. Referral Mechanics

### Referral Link

Every user with an account gets a unique referral link:

```
mandarin.app/r/ABC123
```

The code is auto-generated at account creation. Users do not choose or customize it. The link is accessible from the Settings page.

### Qualification Threshold

A referral counts as **qualified** when the referred user completes **5 study sessions on 3 or more different calendar days.** Until that threshold is met, the referral remains pending and no rewards are issued.

This threshold exists for one reason: it proves genuine intent. Someone who shows up three different days and completes five sessions is actually trying to learn Chinese. A throwaway account created to game a reward will not do this.

### Reward Trigger

Once the referred user hits the qualification threshold:

1. The system marks the referral as qualified.
2. Rewards are applied automatically to both accounts.
3. Both parties receive a single notification.

No manual claiming. No "redeem your reward" button. It just happens.

---

## 3. Reward Structure

### For the Referrer
- **1 free month of Pro** added to their account per qualified referral.
- Months are banked and applied sequentially. If you have 3 months banked and you're a paying subscriber, your next 3 billing cycles are skipped.
- **Cap: 6 months banked at any time.** Once you have 6 months stored, new referrals do not add more until banked months are consumed. This prevents abuse without punishing normal sharing.

### For the Referred User
- **30 days of full Pro access** starting from the day they sign up through a referral link.
- This means they experience HSK 1-9 content, all drill types, diagnostics, forecasting, and every feature from day one.
- After 30 days, they revert to the free tier (HSK 1-2) unless they subscribe.

### What We Do Not Do
- No cash payouts. This is not a side hustle.
- No points system. There is nothing to accumulate or optimize.
- No leaderboards. We do not rank users by how many friends they recruited.
- No tiered rewards. The first referral and the twelfth referral earn the same thing.
- Rewards never expire once earned. A banked month from January is still valid in December.

---

## 4. Anti-Gaming Rules

### Self-Referral Detection
- Same device fingerprint (browser + OS + screen resolution hash) used for both referrer and referred accounts: blocked.
- Same IP address creating a referred account within 24 hours of the referrer's last session: flagged for review.
- Same payment method across referrer and referred accounts: blocked.

### Session Validity
- The 5 study sessions must occur on **3 or more different calendar days** (UTC).
- Each session must involve actual study activity (drill completion, review, reading), not just opening and closing the app.
- Sessions shorter than 2 minutes do not count toward the threshold.

### Rate Limits
- **Maximum 12 qualified referrals per user per rolling 12-month period.**
- This is generous for genuine sharing (one friend per month) and restrictive enough to prevent spam campaigns.
- The limit resets on a rolling basis, not calendar-year.

### Automated Review
- Accounts that trigger 3+ referral signups in a single day are flagged for manual review.
- Accounts whose referred users have an unusually low qualification rate (<20% across 5+ referrals) are flagged.
- Flagged accounts are not penalized automatically. A human reviews them. If the pattern is legitimate, no action is taken.

---

## 5. User Experience Flow

### Where the Link Lives

The referral link is on the **Settings page**, under a section labeled "Invite a Friend." It is not a persistent banner. It is not a popup. It does not appear after completing a session. It does not appear on the dashboard.

If you go looking for it, you will find it. If you don't, it stays out of the way.

### Sharing

One option: **Copy Link.**

That's it. No "Share to Twitter" button. No "Share to WeChat" button. No auto-generated social media post. Those integrations feel desperate and the pre-written social posts are always embarrassing.

The user copies the link and shares it however they want: text message, email, group chat, handwritten note on a napkin. Their choice.

### Notifications

When a referred user qualifies:

> **Your friend [first name] qualified. You've earned a free month of Pro.**

Sent once. In-app notification + email. No follow-up. No "you're 2 referrals away from your next reward!" nudge.

When a referred user signs up (but hasn't qualified yet): no notification to the referrer. We do not create a situation where the referrer is watching their friend's progress and wondering why they haven't done enough sessions yet.

### Referral Dashboard

Available on the Settings page, same location as the referral link. Shows:

- **Successful referrals:** a count (e.g., "3 friends joined and qualified").
- **Banked months:** how many free months are stored (e.g., "2 months banked").
- **Pending:** number of referred signups who haven't qualified yet, shown as a single number without names or details.

No graph. No history timeline. No leaderboard position. No "share more to unlock" messaging.

---

## 6. Technical Implementation Spec

### Database Schema

```sql
CREATE TABLE referral (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL,
    referred_id INTEGER,
    referral_code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sessions_started', 'qualified', 'rewarded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    signup_at TEXT,
    qualified_at TEXT,
    reward_applied_at TEXT,
    FOREIGN KEY (referrer_id) REFERENCES user(id),
    FOREIGN KEY (referred_id) REFERENCES user(id)
);

CREATE INDEX idx_referral_code ON referral(referral_code);
CREATE INDEX idx_referral_referrer ON referral(referrer_id);
CREATE INDEX idx_referral_referred ON referral(referred_id);
CREATE INDEX idx_referral_status ON referral(status);
```

The `referral_code` is generated once per user at account creation and stored in the `user` table as well:

```sql
ALTER TABLE user ADD COLUMN referral_code TEXT UNIQUE;
```

### Status Flow

```
pending          User clicked referral link but hasn't signed up yet
                 (referral_code set, referred_id NULL)
      |
      v
sessions_started Referred user signed up and completed at least 1 session
                 (referred_id set, signup_at set)
      |
      v
qualified        Referred user completed 5 sessions on 3+ calendar days
                 (qualified_at set)
      |
      v
rewarded         Both accounts credited
                 (reward_applied_at set)
```

### API Endpoints

**POST /api/referral/generate**
- Called at account creation to generate the user's referral code.
- Returns: `{ "referral_code": "ABC123", "referral_url": "mandarin.app/r/ABC123" }`
- Idempotent: if the user already has a code, returns the existing one.

**GET /api/referral/status**
- Returns the authenticated user's referral summary.
- Response:
```json
{
    "referral_code": "ABC123",
    "referral_url": "mandarin.app/r/ABC123",
    "successful_referrals": 3,
    "banked_months": 2,
    "pending_referrals": 1,
    "yearly_referrals_used": 4,
    "yearly_referrals_remaining": 8
}
```

**POST /api/referral/check-qualification** (internal, called by session completion logic)
- After each study session, check if the user was referred and whether they now meet the 5-session / 3-day threshold.
- If qualified, update referral status and apply rewards to both accounts.
- Not exposed publicly. Triggered internally by the session completion handler.

### Attribution

When a user visits `mandarin.app/r/ABC123`:

1. The referral code `ABC123` is stored in `localStorage` under key `ref_code`.
2. A first-party cookie `ref` is also set with the same value, expiring in 30 days.
3. If the user signs up within 30 days, the stored code is sent with the registration request.
4. The referral record is updated: `referred_id` is set, `signup_at` is recorded, status moves to `pending` (or `sessions_started` if they immediately complete a session during onboarding).

**30-day attribution window.** If someone clicks a referral link but doesn't sign up within 30 days, the attribution expires. This is shorter than the affiliate program's 90-day window because user-to-user sharing has a faster decision cycle than content creator recommendations.

**First-click attribution.** Consistent with the affiliate program: the first referral link clicked gets credit.

**No conflict with affiliate attribution.** If a user clicks both an affiliate link and a referral link, the affiliate link takes precedence (because the affiliate has a commercial relationship and commission obligations). The referral is not created.

---

## 7. Messaging Templates

### Share Message (Pre-Filled for Copy)

```
I've been using Mandarin to study Chinese. It's the most honest learning tool
I've found -- no streaks, no games, just real progress tracking. Try it:
[referral_url]
```

This is the default text placed on the clipboard when the user clicks "Copy Link." They can edit it before sending. We do not track whether they modify it.

### Qualification Email to Referrer

**Subject:** Your friend joined.

```
[First name],

[Referred user's first name] completed enough study sessions to qualify
your referral. One month of Pro has been added to your account.

Banked months: [count]

No action needed.

— Mandarin
```

### Qualification Email to Referred User

**Subject:** Your extended trial is active.

```
[First name],

You now have 30 days of full Pro access. Here's what that includes:

- All HSK levels (1-9)
- Full diagnostics and progress forecasting
- Every drill type, including speaking and context practice
- Graded reading and listening content

Your trial runs through [date]. After that, you'll have
free access to HSK 1-2 content, or you can subscribe to Pro
for $12/month.

No rush. Study at your own pace.

— Mandarin
```

### One-Time Referral Reminder

**Conditions:** Sent only if ALL of the following are true:
- User has been active for 30+ days
- User has 0 successful referrals
- User has never been sent this message before

**Subject:** Know someone studying Chinese?

```
[First name],

If you know someone studying Chinese (or thinking about it),
you can share your referral link:

[referral_url]

If they sign up and stick with it, you both get a free month
of Pro.

That's the whole pitch. No pressure.

— Mandarin
```

This message is sent **once.** If the user ignores it, we do not follow up. We do not send a second reminder at 60 days, 90 days, or ever.

---

## 8. Metrics to Track

| Metric | What It Tells You | Review Frequency |
|--------|-------------------|------------------|
| Referral links generated per month | How many users are even aware of the feature | Monthly |
| Click-through rate on referral links | Whether shared links actually get clicked | Monthly |
| Signup conversion from referral clicks | Whether the landing experience converts referred visitors | Monthly |
| Qualification rate (% of referred signups completing 5 sessions) | Whether referred users are genuinely interested or just doing a favor | Monthly |
| Time to qualification (median days from signup to 5th session) | How quickly referred users engage | Monthly |
| Retention of referred users vs. organic at 30/60/90 days | Whether referrals bring higher-quality users | Quarterly |
| Referred user free-to-paid conversion rate | Whether the extended trial leads to subscriptions | Quarterly |
| Revenue impact: Pro months given away vs. referred users who convert to paid | Whether the program is net-positive financially | Quarterly |
| Referral source concentration (% of referrals from top 10% of referrers) | Whether a small group is driving disproportionate volume (potential gaming) | Quarterly |

### Financial Model (Rough)

- Cost per qualified referral to the referrer: 1 month of Pro = $12 in forgone revenue.
- Cost per qualified referral to the referred user: 30 days of Pro trial = ~$12 in forgone revenue.
- Total cost per qualified referral: ~$24.
- If 30% of referred users convert to paid after their trial, each referral generates $12/month ongoing.
- Breakeven: ~2 months of paid subscription per referred user who converts.
- At 30% conversion, expected value per referral: 0.30 x $12/month x 12 months = $43.20/year, against a $24 cost. Net positive within the first year.

---

## 9. Launch Timing

### When to Launch

**Not at app launch.** The referral program launches after the app has **100+ active users** (defined as users who have completed at least 5 study sessions in the past 30 days).

Reasons:
- A referral program with 20 users feels performative. With 100+, there is a genuine community that can authentically recommend the product.
- Early users are still stress-testing the app. Referred users should arrive to a stable experience.
- It gives time to validate that the qualification threshold and anti-gaming rules work correctly before real volume hits.

### How to Announce

1. **In-app notification** to all active users: "You can now invite friends to Mandarin. Find your referral link in Settings."
2. **One email** to all registered users with the same message.
3. No blog post. No social media campaign. No "launch event."

### What We Never Do

- Referral contests ("refer the most friends this month and win...").
- Seasonal referral promotions ("double referral rewards for the holidays!").
- Referral milestones ("you've referred 5 friends — unlock a badge!").
- Public referral counts ("Jason has referred 12 friends" visible to others).
- Any mechanic that makes referrals feel like a game within the app.

The referral program is infrastructure, not a feature. It exists to make sharing easy. It does not ask for attention.
