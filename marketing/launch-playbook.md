# Launch Playbook — Product Hunt, Hacker News, and Day-of Plan

---

## Product Hunt Launch

### Why It Matters
Product Hunt is the single highest-ROI launch event for indie dev tools. A top-5 finish on your launch day can drive 500-2,000 qualified visitors in 24 hours. Your "builder learning Chinese" story is exactly what PH voters love.

### Pre-Launch Prep (2-4 weeks before)

**1. Create your maker profile**
- Sign up at producthunt.com
- Fill out bio: "Learning Mandarin. Building the app I wish existed."
- Add your Twitter/X handle
- Start engaging: upvote and comment on 5-10 products over the next 2 weeks (PH penalizes ghost accounts that only show up to launch)

**2. Find a hunter (optional but helpful)**
- A "hunter" with followers gives you more visibility
- Look for hunters who've posted language learning or dev tools before
- Reach out with a short pitch: "We built an adaptive Chinese learning app as an independent team. Would you be interested in hunting it?"
- If you can't find one, self-hunting is fine — many successful launches are self-hunted

**3. Prepare assets**
- **Tagline** (60 chars max): `Adaptive Chinese drills that learn what you struggle with`
- **Description** (260 chars): `27 drill types that adapt to your weak spots. Read real Chinese with instant glosses — every word you look up becomes your next drill. HSK 1-6 aligned. Built by a learner, not a corporation.`
- **First comment** (you post this immediately after launch — see below)
- **Gallery images** (1270x760px):
  1. Hero shot: app dashboard with a reading passage open
  2. Drill in action: showing a tone pair drill with feedback
  3. The cleanup loop: diagram showing read → lookup → drill cycle
  4. HSK projection: diagnostics screen showing multi-skill readiness
  5. Before/after: "Day 1 vs Day 30" progress screenshot
- **Video** (optional, max 2 min): Screen recording walking through a session — read a passage, look up words, start a drill session, see those words appear. No voiceover needed; captions work.
- **Logo**: 240x240px app icon
- **Topics**: `Productivity`, `Education`, `Developer Tools`, `Artificial Intelligence` (even though no AI at runtime — it gets more eyes)

**4. Write your maker's comment**

This goes live immediately after your product is posted. It's the most-read text on your PH page.

```
Hey Product Hunt! We're the team behind Mandarin, and we're learning Mandarin ourselves.

Mandarin was built because we got frustrated with the gap between studying flashcards and actually understanding Chinese. Most apps drill you on random word lists. We wanted something that drills the words we actually struggled with.

The core idea is the "cleanup loop":
1. Read a graded Chinese passage
2. Tap any word you don't know
3. Your next drill session focuses on those exact words

The system has 27 drill types (not just flashcards), adapts to your weak spots, and tracks your readiness across listening, reading, speaking, and tone accuracy.

Some things I'm proud of:
- Zero AI tokens at runtime — everything is deterministic and instant
- Built in Python, running on SQLite
- Every word has handwritten context notes, not AI-generated descriptions

I'd love feedback from other language learners. What would make this more useful? What's missing?

Free for HSK 1-2. Full access is $12/month.
```

### Launch Day Protocol

**Timing**: Launch at 12:01 AM PT (PH resets at midnight Pacific). This gives you the full 24 hours.

**Hour 0 (midnight PT)**:
- Product goes live
- Post your maker's comment immediately
- Share the PH link on your Twitter/X with a brief thread

**Hour 1-3 (early morning PT)**:
- Text/DM 10-20 people you know personally and ask them to check it out on PH
- Do NOT say "upvote me" — PH detects vote rings. Say "I launched on Product Hunt today, would love your feedback"
- Post in any Discord servers you're in (language learning, indie hackers)

**Hour 6-8 (morning PT)**:
- Share on Twitter/X again: "Launched on PH today. Here's the story behind it: [link to PH page]"
- Post in r/SideProject and r/indiehackers (link to PH page, not your app)
- Respond to every single PH comment within 30 minutes

**Hour 12-18 (afternoon/evening PT)**:
- Keep responding to comments
- If you're in the top 5, post an update: "Blown away by the response. Here are the top 3 feature requests so far: [...]"
- Share on LinkedIn if you have a tech network there

**Hour 24**:
- Launch day ends
- Post a "thank you + what's next" comment on your PH page
- Write down every piece of feedback received

### What "Success" Looks Like

| Outcome | What It Means |
|---------|---------------|
| Top 5 of the day | Great — 500-2,000 visits, 50-200 signups likely |
| Top 10 | Good — 200-500 visits, 30-80 signups |
| Top 20 | Decent — 100-200 visits, 15-40 signups |
| Didn't rank | Normal — most launches don't rank. You still got a PH page for SEO |

---

## Hacker News "Show HN" Launch

### Why It Matters
HN "Show HN" posts get seen by technical builders who respect craft. Your "solo dev, Python, SQLite, zero AI tokens" story resonates here. A front-page Show HN can drive 5,000-20,000 visits in a day.

### The Post

**Title**: `Show HN: An adaptive Chinese learning app with 27 drill types and zero AI`

**Body** (keep it short — HN readers click first, read second):
```
I'm learning Mandarin and built an app around a concept I call the "cleanup loop":

1. Read graded Chinese passages at your level
2. Tap any word you don't know
3. Your next drill session prioritizes those exact words

The system has 27 drill types across reading, listening, speaking, and tone accuracy. It adapts to what you get wrong and adjusts session difficulty.

Tech: Python, Flask, SQLite. No AI API calls at runtime — all scheduling and scoring is deterministic. The adaptive algorithm uses modified FSRS with bayesian confidence dampening and interleaving enforcement.

HSK 1-6 aligned. Free for HSK 1-2, $12/month for full access.

Feedback welcome — especially from other language learners or people building educational tools.
```

### HN Strategy

**Timing**: Post between 8-10 AM ET on a Tuesday or Wednesday (highest HN traffic)

**Engagement rules**:
- Respond to every comment, especially technical ones
- Be honest about limitations ("yes, the tone grading uses heuristic pitch analysis, not ML — parselmouth wouldn't compile on my Python version")
- HN values humility and technical depth — lean into the engineering, not the marketing
- If someone asks "why not just use Anki?" — give a thoughtful, non-defensive answer

**What NOT to do**:
- Don't ask friends to upvote (HN detects this aggressively and will kill your post)
- Don't use marketing language ("revolutionary," "disruptive," "game-changing")
- Don't compare to Duolingo in the title (sounds like an ad)

### What "Success" Looks Like

| Outcome | What It Means |
|---------|---------------|
| Front page (top 30) | Exceptional — 5,000-20,000 visits |
| 50+ points | Great — 1,000-5,000 visits |
| 10-50 points | Good — 200-1,000 visits, valuable feedback |
| < 10 points | Normal — most Show HNs get < 10. Try again in 3 months with new features |

---

## Social Proof Collection Plan

### Phase 1: Pre-Launch (before you have users)

You can't fake social proof, but you can have it ready:

**Your own data:**
- Screenshot your own progress stats (HSK readiness projection, sessions completed, words mastered)
- Write 2-3 sentences about your own learning experience using the tool
- "I've drilled 1,200 items and my HSK 3 reading projection went from 42% to 78% in 6 weeks"

**Beta testers (get 5-10):**
- Post in r/ChineseLanguage: "We built a Chinese learning app — looking for 5-10 beta testers to give honest feedback before launch"
- Offer free lifetime access to beta testers
- After 2-4 weeks, ask each for a 2-sentence testimonial
- Ask permission to use their Reddit username or first name

### Phase 2: Post-Launch (first 30 days)

**In-app feedback prompt:**
After a user completes their 10th session, show:
> "How's it going? If Mandarin is helping, a quick testimonial would mean the world. If it's not, I want to know that too."
> [Write a testimonial] [Something's not working]

**Email ask (Day 14 email):**
> "Quick question: if you had to tell a friend what Mandarin does in one sentence, what would you say? Hit reply — I read every response."

Responses become testimonials (with permission).

**Reddit/PH comments:**
- Screenshot positive comments from your PH launch and Reddit posts
- These are public and don't need permission
- Display on landing page with source attribution

### Phase 3: Ongoing

**Review solicitation flow:**
- After 30 days of active use: prompt to leave a review on Product Hunt page
- After 60 days: prompt for App Store review (when mobile launches)
- Never prompt more than once per 30-day period

### Where to Display Social Proof

Add a testimonials section to the landing page between "features" and "how it works":
- 3-4 short quotes with first name and context ("HSK 3 learner", "Anki convert", "2 months in")
- No photos needed (text is more authentic for indie apps)
- Rotate quotes quarterly

---

## Referral Mechanism

### Keep It Simple

At your scale, a complex referral system isn't worth building. Start with the simplest version:

**How it works:**
1. Every paid user gets a unique referral code: `mandarinapp.com/ref/USER123`
2. When someone signs up through that link, both the referrer and the new user get 1 free month
3. Referral code is stored in a cookie and captured at signup

**Implementation (add to your users table later):**
```sql
ALTER TABLE user ADD COLUMN referral_code TEXT UNIQUE;
ALTER TABLE user ADD COLUMN referred_by TEXT;
ALTER TABLE user ADD COLUMN referral_credits INTEGER DEFAULT 0;
```

**Display:**
- In user settings/profile: "Share Mandarin: [your referral link] — you both get a free month"
- In the Day 14 email: "Know someone else learning Chinese? Share your link: [referral link]"

**Caps:**
- Max 6 free months from referrals (prevents gaming)
- Referral credit applied at next billing cycle

**Why this works at your scale:**
- No viral coefficient needed — even 10% of users referring 1 friend doubles your organic growth
- The incentive (free month) costs you nothing (marginal cost is near zero)
- Simple to build, simple to explain

### Share Prompts (in-app moments)

Trigger a "share with a friend" prompt at these moments (high-satisfaction points):
- After the user achieves a new HSK level milestone
- After a session with >90% accuracy
- After 7-day streak
- After completing all passages at an HSK level

---

## Launch Day Timeline (Combined)

### Week -4: Pre-launch content
- Publish origin story blog post (Post 6 from seo-blog-posts.md)
- Share on Reddit r/ChineseLanguage (value post format, not promotional)
- Start engaging on Product Hunt (upvoting, commenting)

### Week -3: HSK content + beta
- Publish HSK 3 study plan blog post
- Recruit 5-10 beta testers from Reddit
- Set up GA4, Meta Pixel, Formspree

### Week -2: Listening content + testimonials
- Publish listening practice blog post
- Collect beta tester feedback
- Prepare PH assets (gallery images, video, copy)

### Week -1: Final prep
- Publish characters blog post
- Finalize testimonials from beta testers
- Add testimonials to landing page
- Prepare HN Show HN post
- Line up 10-20 people to "check out your PH launch"

### Launch Day (Tuesday or Wednesday)
- **12:01 AM PT**: Product Hunt goes live
- **8:00 AM ET**: Show HN post goes live
- **9:00 AM ET**: Reddit launch post in r/ChineseLanguage
- **10:00 AM ET**: Twitter/X thread
- **All day**: Respond to every comment on PH + HN + Reddit

### Week +1
- Publish Anki comparison blog post
- Share on Reddit r/LearnChinese
- Write "lessons from launch day" post for indie hacker communities
- Start retargeting ads for visitors who didn't sign up ($5-10/day)

### Week +2
- Publish HSK levels blog post
- Review all feedback from launch
- Prioritize top 3 feature requests
- If PH drove signups, post a "1 week later" update
