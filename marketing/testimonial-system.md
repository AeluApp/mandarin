# Testimonial Collection & Display System

**Product:** Ming (明) -- Mandarin Learning System
**Document type:** Internal operations guide
**Last updated:** 2026-02-21

---

## 1. Philosophy

Testimonials for Ming should read like field notes from one serious learner to another. They are not marketing copy. They are evidence.

The goal is not to persuade through enthusiasm but to let real learning outcomes speak plainly. A learner who says "I finally stopped confusing second and third tones after the scaffolded review caught the pattern I was missing" is worth more than a hundred "This app is amazing!" quotes.

**Principles:**

- Five genuine testimonials outweigh fifty generic ones. Do not chase volume.
- Testimonials should describe specific, observable changes in the learner's Mandarin ability or study habits. Vague praise ("great app") has no place here.
- Never manufacture enthusiasm. If a learner's honest assessment is "solid tool, not flashy," that is a valid testimonial. The right users will recognize authenticity.
- Every claim in a displayed testimonial should be defensible. If someone says "I passed HSK 3 in four months," we should be able to verify they were an active user for that period. We do not display claims we cannot reasonably corroborate.
- Testimonials are a mirror, not a megaphone. They reflect what the product actually does, not what we wish it did.

**Tone alignment:** The same calm, adult, data-grounded voice that defines Ming's learning experience should define how we present learner voices. No exclamation marks added in editing. No superlatives inserted. The Civic Sanctuary aesthetic -- warm, unhurried, respectful -- extends to how we handle other people's words.

This document exists to formalize restraint, not to optimize extraction.

---

## 2. Collection Methods

Testimonials are gathered through six channels, ordered by signal quality. No collection method should ever interrupt an active learning session.

### In-App Prompt Triggers

Triggered after meaningful milestones, not arbitrary usage counts. The prompt appears on the dashboard after the session ends, never during.

| Trigger | Prompt |
|---|---|
| 50th completed session | "You've completed 50 sessions. What has changed about your Mandarin since you started?" |
| First HSK level completed | "You've finished all HSK [N] material. What stood out about the process?" |
| 30-day streak | "You've studied 30 days in a row. What keeps you coming back?" |
| First context note created | "You've started adding your own context. How has that affected your retention?" |

Rules:
- Each trigger fires at most once per user, ever. No repeat prompts.
- Prompt is dismissible with a single tap/click. No "Are you sure?" confirmation on dismiss.
- Prompt disappears permanently after 7 days if not acted on.
- Prompt never appears if the user has previously submitted a testimonial through any channel.
- Maximum one prompt per 90 days regardless of milestones reached.
- Appears as a quiet card in the session summary, not as a modal or popup.

### Post-Session Micro-Feedback

After every 10th session, an optional single-question card appears on the session summary screen. This is not a testimonial request -- it is lightweight sentiment data that may surface testimonial candidates.

Questions rotate from a pool:
- "What is one thing that clicked for you recently?"
- "Is there a specific word or pattern you feel solid on now?"
- "What would you tell someone considering studying Mandarin seriously?"

Responses under 15 words are stored as feedback data only. Responses of 15+ words are flagged as potential testimonial candidates for manual review.

### Email Follow-Up

Sent at 30, 90, and 180 days after account creation. Plain text emails, no HTML templates. Subject lines are direct:

- 30 days: "Quick question about your first month with Ming"
- 90 days: "How is your Mandarin study going?"
- 180 days: "Six months in -- what has the experience been like?"

Each email contains one open-ended question and a reply link. No surveys, no rating scales, no NPS. If the user has unsubscribed from marketing emails, these do not send. These are marketing emails and must respect that opt-out.

### Beta Tester Structured Interviews

Five questions, conducted asynchronously (written) or via 15-minute call:

1. What were you using for Mandarin study before Ming? What was missing?
2. Describe a specific moment where something clicked that hadn't before.
3. What does your typical study session look like?
4. What would you change about the product?
5. Who would you recommend this to, and who would you not?

Question 4 is critical. It builds trust (we are not fishing for praise) and surfaces real feedback. Answers to question 4 are never displayed as testimonials but may inform product development.

### Community Channels

Monitor (do not solicit) mentions on:
- Discord server (if/when launched)
- Reddit: r/ChineseLanguage, r/MandarinChinese, r/languagelearning
- Twitter/X mentions
- Blog posts or YouTube reviews by users

When a genuine, unprompted mention is found:
1. Screenshot and archive the original with URL and date.
2. Contact the user directly to ask if we may quote them.
3. Do not quote without explicit written permission, even for public posts.

### The Non-Negotiable Rule

**Never interrupt a learning session to request a testimonial.** The learning space is sacred. No modals, no banners, no "How are we doing?" popups during active study. Collection happens on the dashboard, in email, or in community spaces. Never inside the session flow.

### Never

- Incentivized reviews (free months, discounts, feature unlocks)
- Review swaps with other apps or creators
- Paid testimonials or sponsored endorsements
- AI-generated testimonials
- Screenshots from fake accounts
- Asking friends or family to post reviews
- Timing review requests to coincide with positive in-app moments to game sentiment

---

## 3. Permission & Consent System

Every displayed testimonial requires explicit, informed, documented consent. There are no exceptions.

### Permission Levels

| Level | What is displayed | Example |
|---|---|---|
| `anonymous` | Quote text only, with HSK level and time range | "After three months at HSK 2..." |
| `first_name_level` | First name, HSK level, time range | "-- Sarah, HSK 3, 6 months" |
| `full_attribution` | Full name and any details the user approves | "-- Sarah Chen, HSK 4, Beijing-based software engineer" |

The user selects their permission level at submission time. They may change it at any time. Default is `anonymous`.

### Consent Flow

1. User submits testimonial text through any collection channel.
2. System sends a consent form (email or in-app) that states clearly:
   - Exactly where the testimonial may appear (marketing site, app store, social media, partner materials).
   - The permission level they are granting.
   - That they may withdraw consent at any time.
   - How to withdraw (one-click link, or email to a specific address).
3. User confirms by clicking a single confirmation link. No account login required to confirm.
4. System records: `consent_date`, `permission_level`, `consent_method` (email_link, in_app_button), `testimonial_version_hash`.

### Right to Withdraw

Withdrawal must be trivially easy. Acceptable methods:
- One-click link in the original consent confirmation email (link never expires).
- Email to a designated privacy address with any identifying information.
- In-app setting under account preferences (if the user still has an account).

Upon withdrawal:
- Testimonial is removed from all display locations within 48 hours.
- `withdrawn_date` is recorded.
- Testimonial text is retained in the database for audit purposes but flagged as `withdrawn` and excluded from all queries that power display.
- User receives confirmation that their testimonial has been removed.

### Data Storage

```sql
CREATE TABLE testimonials (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER,
    quote_text          TEXT NOT NULL,
    source              TEXT NOT NULL,     -- 'in_app_milestone', 'micro_feedback', 'email', 'beta_interview', 'community'
    source_url          TEXT,              -- link to original if public
    permission_level    TEXT NOT NULL DEFAULT 'anonymous',
                                          -- 'anonymous', 'first_name_level', 'full_attribution'
    consent_date        TEXT,
    consent_method      TEXT,              -- 'email_link', 'in_app_button'
    permission_proof    TEXT,              -- email thread ID, screenshot path, etc.
    withdrawn_date      TEXT,
    display_name        TEXT,              -- what the user approved for display
    hsk_level           INTEGER,
    months_using        INTEGER,
    study_duration      TEXT,              -- e.g., "6 months", "1 year"
    tags                TEXT,              -- comma-separated: 'retention,methodology,tone-practice'
    formatted_text      TEXT,              -- approved-for-display version
    format_approved_date TEXT,
    is_active           INTEGER NOT NULL DEFAULT 0,
                                          -- only 1 if consent given and not withdrawn
    status              TEXT NOT NULL DEFAULT 'new',
                                          -- new / active / rotated / retired
    retire_reason       TEXT,              -- user_request / reconfirm_failed / outdated / churned
    last_reconfirm      TEXT,              -- date of last annual re-confirmation
    notes               TEXT,              -- internal notes, never displayed
    collected_date      TEXT NOT NULL,     -- when the quote was originally given
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_testimonials_active ON testimonials(is_active);
CREATE INDEX idx_testimonials_status ON testimonials(status);
CREATE INDEX idx_testimonials_tags ON testimonials(tags);
```

### GDPR / CCPA Compliance Notes

- Testimonials are personal data. They must be included in any data export request (GDPR Article 20) and any deletion request (GDPR Article 17).
- The consent form must be separate from the app's general terms of service. Bundled consent is not valid consent under GDPR.
- For users in California, the consent form must disclose that testimonial data may be used for marketing purposes (CCPA category: commercial information).
- Retain consent records (date, method, version) for at least 3 years after withdrawal.
- If Ming expands to serve users in the EU, conduct a Data Protection Impact Assessment for the testimonial system before launching it in that market.
- Minors (under 16 in the EU, under 13 in the US): do not collect or display testimonials from users identified as minors. If age is unknown, the `anonymous` permission level with no identifying details is the only acceptable option.

---

## 4. Formatting Standards

### Length

- **Display cards:** Maximum 2 sentences. If the original is longer, extract the strongest 2 sentences and get approval for the shortened version.
- **Long-form (blog embeds, case studies):** Up to 1 paragraph (4-5 sentences). Used sparingly.
- **App store listings:** 1-2 sentences, under 200 characters.

### Required Metadata

Every displayed testimonial must include:
- Learner's HSK level at time of writing (HSK 1-6, or "pre-HSK" / "HSK 7-9" if applicable).
- Approximate time using the app (in months, rounded to nearest month).
- What specifically helped (embedded in the quote itself or surfaced through a tag).

### Editing Rules

- **Allowed:** Fix typos, correct grammar, adjust punctuation for readability.
- **Allowed with approval:** Shorten by removing sentences (but not by cutting within a sentence). The shortened version must be sent back to the user for approval before display.
- **Never allowed:** Adding words or phrases the user did not write. Changing "good" to "great." Adding specificity the user did not provide. Rewriting for enthusiasm. Adding emphasis (bold, caps, exclamation marks) that was not in the original.

If a testimonial needs more than light copyediting to be usable, it is not the right testimonial to display. Move on.

### Tag Categories

Each testimonial receives one or more tags from this controlled list:

| Tag | Covers |
|---|---|
| `retention` | SRS effectiveness, long-term recall, forgetting curve |
| `methodology` | Study approach, drill variety, scaffolding, interleaving |
| `tone-practice` | Tone drills, tone grading, pronunciation confidence |
| `reading` | Graded reader, character recognition, reading fluency |
| `ui-ux` | Interface design, session flow, aesthetic experience |
| `value` | Price-to-quality ratio, comparison to free alternatives |
| `comparison` | Direct comparison to a named competitor |
| `habit` | Consistency, streak, daily routine, session length |

### Example: Good vs. Bad Testimonials

**Good:**

> "I kept confusing 买 and 卖 for months on Anki. Ming's interleaved tone drills forced me to distinguish them in context, and I stopped mixing them up within two weeks."
> -- HSK 3, 4 months

Why this works: Specific problem. Specific feature. Specific outcome. Timeframe given. No hyperbole.

**Good:**

> "The graded reader passages are the first reading practice I've found that matches my actual level instead of being either trivially easy or impossibly hard."
> -- HSK 2, 2 months

Why this works: Describes a real frustration with alternatives. Points to a specific feature. Honest in scope (does not claim fluency).

**Bad:**

> "Best language app ever! I'm basically fluent now."

Why this fails: Vague. Unverifiable claim ("basically fluent"). Manufactured enthusiasm. No specifics.

**Bad:**

> "Ming is way better than Duolingo and HelloChinese combined."

Why this fails: Unsubstantiated comparison. No specific observation. Reads like astroturfing.

**Borderline (needs editing request):**

> "I really like the app, it's been super helpful for my tones, I used to get them wrong all the time but the drills helped me get way better at second tone especially."

This has a real observation buried inside informal language. With the user's permission, this could become:

> "I used to get tones wrong constantly. The tone drills helped me lock in second tone specifically."

---

## 5. Display Locations

### Marketing Site

| Page | Quantity | Purpose | Selection Criteria |
|---|---|---|---|
| Homepage | 3, rotating | First impression -- show breadth of learner types | One beginner (HSK 1-2), one intermediate (HSK 3-4), one long-term user (6+ months) |
| Pricing | 2 | Handle objections -- "Is $12/month worth it?" | Both must have `value` or `comparison` tag |
| About | 1 | Align with product philosophy | Should reference methodology or learning approach, not just praise |

Rotation: Homepage testimonials rotate on page load from a pool of 6-9 approved quotes. Pricing and About testimonials are static, reviewed quarterly.

### App Store Listings

- 3 testimonials per platform (iOS, Android if applicable).
- Refreshed quarterly, aligned with version updates.
- Must comply with platform-specific review guidelines (Apple and Google both have rules about testimonial formatting in store descriptions).
- Prioritize testimonials that mention the free tier or the transition from free to paid, since app store browsers are pre-purchase.

### Blog Posts

- Embed testimonials only where they add context to the post's topic. Never insert them as filler.
- Format as a blockquote with attribution below.
- Link to the relevant feature or methodology being referenced, not to a generic testimonials page.

### Social Media

- Format as quote cards using the Civic Sanctuary design language: warm stone background, Cormorant Garamond heading font for the quote, Source Sans 3 for attribution. Teal accent on the quotation mark.
- One testimonial per card. No collages.
- Post frequency: no more than one testimonial post per week. Testimonials are supporting content, not the core social strategy.
- Always include an identifier so the original speaker can find and verify their quote is displayed correctly.

### Partner Kit

- 3 pre-approved quotes available for affiliates, reviewers, and partners.
- Provided in a simple text document with formatting guidelines.
- Partners may not edit the quotes. They may only use the approved text verbatim.
- Partner kit is updated every 6 months.

### Email Sequences

- 1 testimonial in the trial-ending email (social proof at the decision point).
- Should be from a user who converted from Free to Pro and can speak to why.
- No testimonials in onboarding emails -- too early, feels manipulative.

### Where Testimonials Do Not Appear

**Inside the learning app itself.** The study environment is a focused space. No social proof banners, no "See what others are saying" cards, no testimonial carousels on the dashboard. When a user is inside Ming, the only voice they should hear is the system's instructional voice and their own learning data. Marketing has no place in the session flow.

Also never display testimonials in:
- Popup modals
- Notification bars or banners
- Interstitial screens
- Push notifications
- Loading screens
- Error pages

---

## 6. Testimonial Lifecycle

### Stages

```
Collection --> Review --> Permission --> Formatting --> Placement --> Quarterly Review
    |            |            |              |              |               |
  User       Internal     Consent        Edit +         Assign to      Freshness
  submits    quality      request        approve        location(s)    check
             check        sent           shortened
                                         version
```

### Stage Details

**1. Collection.** Testimonial arrives through one of the six channels described in Section 2. It enters the database with `is_active = 0` and `status = 'new'`.

**2. Review.** Within 5 business days, review the testimonial for:
- Specificity (does it describe something concrete?).
- Authenticity (does it match this user's actual usage data?).
- Usability (can it be displayed in 2 sentences or fewer, or excerpted with approval?).

If it fails review, mark `notes` with the reason and leave `is_active = 0`. Do not delete it -- it is still feedback data.

**3. Permission.** Send consent request per Section 3. If no response within 14 days, send one follow-up. If still no response, mark as `no_consent` in notes and do not use. Never assume consent from silence.

**4. Formatting.** Apply formatting standards from Section 4. If edits beyond typo fixes are needed, send the formatted version back to the user for approval. Record `format_approved_date` only after explicit approval.

**5. Placement.** Assign the testimonial to one or more display locations. Record placement in a `testimonial_placements` table or a notes field tracking where each version appears.

**6. Quarterly Review.** Every quarter, audit all active testimonials:
- Is the user still an active subscriber? (See Section 7 on churned users.)
- Has the testimonial been displayed for more than 6 months? If so, rotate it out and bring in a fresher one.
- Has the user's situation changed? (e.g., they were HSK 2 when they wrote it and are now HSK 5 -- consider asking for an updated testimonial.)
- Does the displayed version still match the approved version?
- Verify all active testimonials still have valid permission records.
- Check that no active testimonial is more than 2 years old without re-confirmation.

### Staleness Policy

| Age | Action |
|---|---|
| 0-6 months | Active display. No action needed. |
| 6-12 months | Rotate out of primary display locations (homepage, app store). May remain in blog posts and partner kit. |
| 12+ months | Archive. Remove from all display locations. Retain in database. |
| Annually | Contact user to confirm continued consent, regardless of display status. |

### Re-Confirmation Process

- Once per year, email each quoted user to confirm they are still comfortable being quoted.
- Email text: "We're still displaying your quote on our site: '[first 10 words...]' Are you still comfortable with this? Reply yes or let us know if you'd like it removed."
- If no response after 30 days, send one follow-up.
- If no response after 60 days total, set status to `retired` with reason `reconfirm_failed`.
- If the user's email bounces, retire immediately.

### Removal Requests

- If a user requests removal, remove within 24 hours. No questions, no "are you sure," no delay.
- Set status to `retired`, reason to `user_request`.
- Confirm removal to the user by email.

### Version Control

Maintain a record of:
- Original submitted text.
- Each formatted/shortened version with approval date.
- Which version is displayed at each location.
- When a version was swapped or removed.

This does not need to be a formal version control system. A `testimonial_versions` table or a structured notes field is sufficient at launch scale.

---

## 7. Anti-Patterns to Avoid

These are the rules that protect the integrity of the testimonial system. Violating them degrades trust -- both the user's trust in Ming and the team's trust in its own data.

**No incentivized testimonials.** Do not offer free months, discounts, extended trials, premium features, or any other incentive in exchange for testimonials. "Leave a review and get a free month" is a disqualifying practice. If a testimonial was influenced by an incentive, it is not a testimonial -- it is paid endorsement, and it must be disclosed as such under FTC guidelines. Ming does not do paid endorsements.

**No cherry-picking only positive sentiment.** If the collection system consistently surfaces negative or neutral feedback, that is a product signal, not a marketing problem. Display testimonials that are genuinely positive, but do not suppress the existence of mixed feedback. The internal quarterly report (Section 9) should include sentiment distribution, not just the highlights. If a 4-star review makes a valid criticism alongside praise, that mixed review is more credible than a 5-star rave.

**No editing to add claims.** If a user says "The tone drills are useful," do not edit it to "The tone drills dramatically improved my pronunciation." The word "dramatically" was not theirs. The claim "improved my pronunciation" was not theirs. Display what they said.

**No fabricated testimonials.** No fake users. No composite quotes assembled from multiple users. No "inspired by real feedback" paraphrases attributed to fictional people. This includes AI-generated testimonials, even if based on real sentiment data.

**No testimonials from churned users.** If a user has cancelled their subscription and not returned within 60 days, their testimonial should be removed from display at the next quarterly review. Someone who no longer uses the product should not be implicitly endorsing it. Exception: if the testimonial specifically describes a completed, self-contained experience (e.g., "I used Ming to prepare for and pass HSK 3"), it may remain with a note that it reflects a past experience.

**No learning speed promises.** Do not display testimonials that claim or imply specific learning timelines unless the claim can be verified against the user's actual data. "I learned 500 characters in a month" is a claim that can be checked. If it cannot be verified, it cannot be displayed. Even if verified, add context: the user's prior experience, study hours per day, and other factors that make their timeline non-generalizable.

**No pressure tactics during collection.** Do not send more than one follow-up per collection channel. Do not display guilt-inducing messages ("Help us grow!"). Do not tie testimonial submission to any app functionality. If the user does not want to provide a testimonial, that is the end of the interaction.

**No emotional manipulation.** Never pair testimonials with countdown timers, limited-time offers, or scarcity messaging. Never display testimonials only to users who are about to churn or cancel -- social proof should be ambient, not targeted.

**No stock photos.** Never use stock photos for testimonial avatars. Text-only attribution or no avatar at all.

**No vanity counts.** Never display a testimonial count as a metric. "10,000 happy learners!" is not social proof; it is noise.

If you find yourself considering any of these, the product needs work, not the marketing.

---

## 8. Video / Audio Testimonials

Video testimonials are a secondary format. Text testimonials are the primary format because they are easier to consent to, easier to edit with approval, easier to display accessibly, and less likely to make learners uncomfortable.

That said, video testimonials -- when they happen naturally -- carry a different kind of credibility.

### Format

- **Length:** 60-90 seconds maximum. Shorter is better. A 30-second clip of someone describing one specific moment of progress is more valuable than 3 minutes of general praise.
- **Structure (suggested, not required):**
  - What they were struggling with before (10-15 seconds).
  - What specifically helped (20-30 seconds).
  - Where they are now (10-15 seconds).
- **Language:** The learner should speak in whatever language they are comfortable in. If they want to include a few sentences of Mandarin to demonstrate progress, that is welcome but not expected.

### Production Quality

Authenticity matters more than production value. A phone recording at a desk is preferable to a studio-lit setup that feels staged. Guidelines for the user:

- Good lighting (face a window).
- Quiet environment.
- Horizontal orientation.
- No need for multiple takes -- first genuine attempt is usually best.

Do not offer to send a camera crew, hire a videographer, or provide a script. If it feels produced, it fails.

### Permission

Video testimonials require a separate video/audio release form in addition to the standard testimonial consent. The release form must cover:

- Where the video may be displayed (marketing site, social media, partner materials).
- Whether the video may be excerpted (shorter clips pulled from the full recording).
- Whether a still frame may be used as a thumbnail.
- Duration of the license (recommend: 2 years, renewable with re-consent).
- Right to withdraw: same as text testimonials, removal within 48 hours of request.

### Hosting

- Self-hosted MP4 files served from Ming's own infrastructure or a privacy-respecting CDN.
- Do not embed YouTube, Vimeo, or other third-party players on the marketing site. Third-party embeds introduce tracking cookies, which conflicts with the user's consent scope.
- Video files should be optimized for web: H.264 codec, max 720p, target file size under 15MB for a 90-second clip.
- Provide manual play controls. No autoplay.

### Accessibility

- Every video testimonial must have a full text transcript displayed alongside or below the video.
- Captions (subtitles burned into the video or provided as a WebVTT track) are required.
- The transcript alone should be sufficient to understand the testimonial. If the video adds nothing beyond the transcript, consider whether text-only would be the better format.

---

## 9. Metrics & Measurement

Track the testimonial system's health with the same rigor applied to learning metrics. Vanity numbers are not useful. Diagnostic numbers are.

### Core Metrics

**Testimonial Conversion Rate**
- Definition: (Testimonials submitted) / (Testimonial prompts shown) over a given period.
- Segmented by collection channel (in-app milestone, micro-feedback, email, etc.).
- Healthy range: 5-15% for in-app prompts, 2-8% for email. Below 2% across all channels suggests the prompts are poorly timed or poorly worded. Above 20% suggests the sample is biased (only highly engaged users are being prompted).

**Placement-to-Signup Correlation**
- Definition: For each display location, compare signup rates for pages with vs. without testimonials, or before vs. after testimonial placement.
- This is correlation, not causation. Do not claim "testimonials increased signups by X%." Instead, track whether there is a measurable association and use it to inform placement decisions.
- If no measurable association exists after 3 months, the testimonials may be in the wrong locations or the wrong testimonials may be selected.
- Conversion lift should only be tested with real statistical significance. Do not declare a winner at n=50.

**Category Performance**
- Track which testimonial tags (retention, methodology, tone-practice, etc.) appear on pages with the highest engagement or conversion.
- This informs which types of testimonials to prioritize in collection and display, not which types to manufacture.

**Permission Withdrawal Rate**
- Definition: (Withdrawals in period) / (Active consented testimonials at start of period).
- A withdrawal rate above 5% per quarter is a warning sign. Investigate whether collection methods are too aggressive, whether testimonials are being displayed in contexts the user did not expect, or whether the consent form was unclear.

**Sentiment Distribution**
- Of all testimonials received (not just displayed), what is the sentiment breakdown?
- Track: clearly positive, mixed/neutral, clearly negative.
- If positive sentiment drops below 60% of submissions, that is a product signal, not a testimonial system problem.

**Retention of Quoted Users**
- Track whether users who provided testimonials continue using the product.
- This is a health signal: if your happiest users leave, something is wrong beyond testimonials.

### Quarterly Report Template

```
TESTIMONIAL SYSTEM QUARTERLY REPORT -- Q[N] [YEAR]

Collection
- Total testimonials received: [N]
- By channel: in-app [N], micro-feedback [N], email [N], beta [N], community [N]
- Conversion rate by channel: [table]

Consent
- Permission requests sent: [N]
- Consents received: [N] ([%])
- Withdrawals this quarter: [N]
- Cumulative active consented testimonials: [N]

Display
- Testimonials currently displayed: [N]
- By location: homepage [N], pricing [N], about [N], app store [N], blog [N], social [N], partner [N]
- Testimonials rotated out (staleness): [N]
- Testimonials removed (churn audit): [N]

Sentiment
- Positive: [N] ([%])
- Mixed/Neutral: [N] ([%])
- Negative: [N] ([%])

Performance
- Placement-to-signup correlation: [summary]
- Top-performing category tags: [list]

Health
- Retention rate of quoted users: [%]
- Permission withdrawal rate: [%]
- Median testimonial age: [months]

Actions
- [List specific actions for next quarter]
```

### What Not to Measure

Do not track or optimize for "testimonials per user" or "average testimonial rating." These metrics incentivize volume and positivity over authenticity. The system's success is measured by whether displayed testimonials are genuine, current, consented, and correlated with informed signups -- not by whether there are a lot of them.

If collected testimonials per month drops to zero for 3+ months, that is a product signal, not a marketing problem. Investigate what changed in the user experience.

---

## 10. Launch Timing

Roll out the testimonial system in three phases, matched to user base size and product maturity. Do not rush to display testimonials before there are enough genuine ones to be credible.

### Phase 1: Pre-Launch and Early Beta (before 100 users)

**Collection:** Beta tester structured interviews only (Section 2). These are the earliest users who have the deepest context on the product.

**Display:** None. Do not display testimonials during this phase. The marketing site may describe the product's methodology and features but should not include social proof until it is genuinely earned.

**Activity:**
- Accumulate 8-12 raw testimonials from beta testers. Expect 3-5 of these to be usable after review and formatting.
- Set up the `testimonials` table in the database.
- Build the in-app prompt mechanism (disabled, but ready to activate).
- Set up monitoring for organic community mentions (manual check weekly).

### Phase 2: Early Growth (0-100 active users)

**Collection:** Add in-app micro-feedback and email follow-ups. In-app milestone prompts can be enabled once the milestone triggers are calibrated (i.e., enough users have hit them to verify the prompts fire at the right moments).

**Display:** Begin displaying testimonials only when at least 5 genuine, consented, formatted testimonials are available. Start with the marketing site homepage (3 rotating) and pricing page (2). Do not add to app store listings until you have platform-specific quotes that reference the mobile experience (if applicable).

**Activity:**
- Activate the 30/90/180-day email follow-ups.
- Enable micro-feedback after every 10th session.
- Begin the quarterly review cycle.
- Reach 10-15 active displayed testimonials across marketing site and app store.

### Phase 3: Established (100+ users)

**Collection:** Full system with all six collection channels active. Community monitoring begins in earnest as the user base is large enough to generate organic mentions.

**Display:** All display locations described in Section 5 are active. Quarterly review cycle is running. Partner kit is assembled.

**Activity:**
- Maintain a rolling pool of 15-25 active consented testimonials, with quarterly rotation keeping the displayed set fresh.
- Assemble the partner kit with 3 pre-approved quotes.
- Begin creating social media quote cards.
- Add the annual re-confirmation email to scheduled tasks.
- Produce quarterly reports per Section 9 template.

### The Threshold Rule

**Do not display any testimonials until you have at least 5 genuine ones.** Displaying 1-2 testimonials on a marketing site looks worse than displaying none. A small number reads as "this is all we could find," which undermines credibility. Either have enough to demonstrate a pattern of learner satisfaction, or let the product speak for itself until you do.

An empty testimonial section is worse than no testimonial section. A section with placeholder text is worse than both. Remove the section entirely until you have the goods.

### What to Do Before You Have Testimonials

- Focus on the product promise and feature descriptions. Let the app's design and specificity do the work.
- Let the free tier be the social proof. If someone can use HSK 1-2 for free and see the system working, that is more persuasive than any quote.
- Everything else can wait until there are actual testimonials to manage.

---

## Implementation Priority

1. Create the `testimonials` table in the schema.
2. Add the post-milestone prompt to the web UI (non-blocking, dismissible, rate-limited).
3. Set up monitoring for organic mentions (manual check weekly until volume justifies automation).
4. Build the testimonial display component for the landing page (hidden until 5 quotes exist).
5. Add the annual re-confirmation email to the scheduled tasks.
6. Everything else can wait until there are actual testimonials to manage.
