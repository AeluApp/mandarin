# Conversion Tracking & Analytics Plan

## GA4 Setup

### Property Configuration
- Property name: Mandarin App
- Currency: USD
- Time zone: US/Eastern (or your local)
- Enhanced measurement: ON (page views, scrolls, outbound clicks, site search)

### Custom Events to Configure

Track these events in GA4 → Admin → Events → Create Event:

| Event Name | Trigger | Parameters | Purpose |
|------------|---------|------------|---------|
| `waitlist_signup` | Email form submission | `source` (hero/bottom/variant) | Measure email capture rate |
| `page_variant_view` | Landing page variant loads | `variant` (main/hsk/anki/serious) | Track which landing pages get traffic |
| `cta_click` | Any CTA button click | `cta_location`, `cta_text` | Identify highest-performing CTAs |
| `scroll_75` | User scrolls 75% of page | `page_path` | Content engagement depth |
| `pricing_view` | Pricing section enters viewport | `variant` | How many visitors see pricing |
| `outbound_click` | Click to app.mandarinapp.com | `link_url` | Track landing → app conversion |

### Post-Launch Events (add when app is live)

| Event Name | Trigger | Parameters | Purpose |
|------------|---------|------------|---------|
| `signup_complete` | Account creation | `source`, `utm_campaign` | Registration conversion |
| `first_session_start` | First drill session begins | `time_since_signup` | Activation rate |
| `first_session_complete` | First session finished | `drills_completed`, `accuracy` | First-session completion |
| `day_7_active` | User active on day 7 | `sessions_count`, `items_drilled` | Early retention |
| `day_30_active` | User active on day 30 | `sessions_count`, `hsk_level` | Retention |
| `upgrade_click` | Clicks upgrade/payment CTA | `current_plan`, `source` | Payment intent |
| `payment_complete` | Stripe payment succeeds | `plan`, `amount`, `utm_source` | Revenue |
| `reader_open` | Opens graded reader | `hsk_level` | Feature adoption |
| `reader_lookup` | Taps word in reader | `word`, `passage_id` | Cleanup loop engagement |
| `listening_start` | Starts listening exercise | `hsk_level`, `speed` | Feature adoption |
| `referral_sent` | Shares referral link | `channel` | Viral loop |

### GA4 Implementation

Add this to every page (landing pages + app):

```html
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

Track custom events:
```javascript
// Waitlist signup
gtag('event', 'waitlist_signup', { source: 'hero' });

// CTA click
gtag('event', 'cta_click', { cta_location: 'pricing', cta_text: 'Get early access' });

// Pricing section visible (use IntersectionObserver)
const pricingObserver = new IntersectionObserver((entries) => {
  if (entries[0].isIntersecting) {
    gtag('event', 'pricing_view', { variant: 'main' });
    pricingObserver.disconnect();
  }
}, { threshold: 0.5 });
pricingObserver.observe(document.querySelector('.pricing'));
```

---

## UTM Parameter Strategy

### Structure
All external links to your landing pages must use UTM parameters:
```
https://mandarinapp.com/?utm_source=SOURCE&utm_medium=MEDIUM&utm_campaign=CAMPAIGN&utm_content=CONTENT
```

### UTM Taxonomy

| Parameter | Values | Usage |
|-----------|--------|-------|
| `utm_source` | `reddit`, `google`, `meta`, `twitter`, `hn`, `producthunt`, `email`, `youtube`, `discord`, `direct` | Where the traffic comes from |
| `utm_medium` | `organic`, `paid`, `social`, `email`, `referral`, `cpc` | How they got there |
| `utm_campaign` | `launch`, `hsk3-blog`, `anki-comparison`, `founder-story`, `ph-launch`, `hn-showhn`, `retarget-v1` | Which campaign |
| `utm_content` | `hero-cta`, `bottom-cta`, `sidebar`, `ad-v1`, `ad-v2` | Which creative/placement |

### Pre-Built UTM Links

**Reddit posts:**
```
https://mandarinapp.com/?utm_source=reddit&utm_medium=organic&utm_campaign=launch&utm_content=r-chineselanguage
https://mandarinapp.com/?utm_source=reddit&utm_medium=organic&utm_campaign=value-post&utm_content=r-learnchinese
```

**Blog post CTAs:**
```
https://mandarinapp.com/?utm_source=blog&utm_medium=organic&utm_campaign=hsk3-study-plan&utm_content=bottom-cta
https://mandarinapp.com/?utm_source=blog&utm_medium=organic&utm_campaign=anki-comparison&utm_content=bottom-cta
```

**Google Ads:**
```
https://mandarinapp.com/hsk?utm_source=google&utm_medium=cpc&utm_campaign=hsk-study-intent&utm_content=ad-v1
https://mandarinapp.com/srs?utm_source=google&utm_medium=cpc&utm_campaign=anki-alternative&utm_content=ad-v1
```

**Meta Ads:**
```
https://mandarinapp.com/?utm_source=meta&utm_medium=paid&utm_campaign=cleanup-loop&utm_content=story-v1
https://mandarinapp.com/?utm_source=meta&utm_medium=paid&utm_campaign=anti-duolingo&utm_content=feed-v1
```

**Product Hunt:**
```
https://mandarinapp.com/?utm_source=producthunt&utm_medium=referral&utm_campaign=ph-launch
```

**Hacker News:**
```
https://mandarinapp.com/?utm_source=hackernews&utm_medium=referral&utm_campaign=showhn
```

**Email sequence:**
```
https://mandarinapp.com/?utm_source=email&utm_medium=email&utm_campaign=welcome-sequence&utm_content=email-1-cta
https://mandarinapp.com/?utm_source=email&utm_medium=email&utm_campaign=welcome-sequence&utm_content=email-3-reader
```

---

## Funnel Metrics — What to Track

### The Funnel

```
Visit → Signup → First Session → Day 7 Active → Paid → Day 30 Active
```

### Target Benchmarks (realistic for indie SaaS)

| Stage | Metric | Target | Red Flag |
|-------|--------|--------|----------|
| Visit → Waitlist signup | Landing page conversion | 8-15% | < 5% |
| Visit → Account creation | Post-launch signup rate | 5-10% | < 3% |
| Signup → First session | Activation rate | 60-80% | < 40% |
| First session → Day 7 active | Early retention | 30-50% | < 20% |
| Day 7 → Day 30 active | Retention | 40-60% | < 25% |
| Free → Paid | Conversion rate | 5-12% | < 3% |
| Paid → Month 2 | Paid retention | 85-95% | < 80% |
| Monthly churn (paid) | Churn rate | 5-10% | > 15% |

### Weekly Dashboard (check every Monday)

1. **Traffic**: Total visits by source (UTM), landing page variant performance
2. **Signups**: New waitlist/account signups, conversion rate by source
3. **Activation**: % who complete first session within 24h of signup
4. **Engagement**: Sessions per user, drills per session, reader opens, listening starts
5. **Retention**: Day 7 / Day 30 cohort retention
6. **Revenue**: New paid, churned paid, MRR, LTV estimate

### GA4 Exploration Reports to Build

1. **Funnel exploration**: Visit → Signup → First Session → Day 7 → Paid
2. **User acquisition**: Breakdown by utm_source + utm_campaign
3. **Cohort analysis**: Weekly cohorts, retention over 4 weeks
4. **Path exploration**: What pages do users visit before signing up?

---

## Retargeting Pixel Setup

### Meta Pixel

Add to all pages:
```html
<!-- Meta Pixel Code -->
<script>
!function(f,b,e,v,n,t,s)
{if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', 'YOUR_PIXEL_ID');
fbq('track', 'PageView');
</script>
```

Fire events:
```javascript
// On waitlist signup
fbq('track', 'Lead', { content_name: 'waitlist' });

// On account creation (post-launch)
fbq('track', 'CompleteRegistration');

// On payment (post-launch)
fbq('track', 'Purchase', { value: 12.00, currency: 'USD' });
```

### Retargeting Audiences to Create (in Meta Ads Manager)

| Audience | Definition | Use For |
|----------|-----------|---------|
| All visitors (30 days) | Anyone who visited any page | Broad retargeting |
| Visited but didn't sign up | Visited landing page, no `Lead` event | "Still thinking about it?" ads |
| Signed up, no first session | `CompleteRegistration` but no `first_session` event | Activation nudge ads |
| Free users, no upgrade | Active users without `Purchase` event | Upgrade ads |
| Lookalike: Signups | 1% lookalike of all signups | Prospecting |
| Lookalike: Paid users | 1% lookalike of paid users | High-value prospecting |

### Retargeting Ad Copy

**Visited but didn't sign up:**
> Still looking for a better way to study Chinese? Mandarin adapts to your weak spots — no deck-building required. Free to start.

**Signed up but not activated:**
> Your Mandarin account is waiting. Your first session takes 10 minutes and the system calibrates to your level. [Start now →]

**Free user upgrade:**
> You've been learning for [X] weeks. Ready for the full curriculum? HSK 3-6, all 27 drill types, speaking practice. $12/month.

---

## Attribution Model

Use **last-click attribution** for simplicity at your scale. When a user signs up:
1. Record their `utm_source`, `utm_medium`, `utm_campaign` from the signup visit
2. Store in your user record (add columns to your users table when you build multi-user auth)
3. When they convert to paid, you know which channel drove the revenue

At 200-500 users, multi-touch attribution is overkill. Last-click tells you what's working.

---

## Cost Per Acquisition Tracking

| Metric | Formula | Target |
|--------|---------|--------|
| CAC (all channels) | Total spend / New paid users | < $15 |
| CAC (Google Ads) | Google spend / Paid users from Google | < $25 |
| CAC (Meta Ads) | Meta spend / Paid users from Meta | < $20 |
| CAC (organic) | $0 + your time / Paid users from organic | Track time spent |
| LTV | ARPU × (1 / monthly churn rate) | > $100 |
| LTV:CAC ratio | LTV / CAC | > 3:1 |

### When to Kill a Channel

- CAC > $40: Pause immediately, investigate
- CAC > $30 for 2 consecutive weeks: Reduce budget, test new creative
- No conversions after $100 spend: Pause, try different targeting
- LTV:CAC < 2:1: Not sustainable at your price point
