# Email System & Experimentation Governance: Audit, Critique, and Redesign

**Date:** 2026-03-16
**Scope:** Aelu email lifecycle, experimentation daemon, churn detection, autonomy governance
**Doctrine anchor:** DOCTRINE.md, BRAND.md, marketing/churn-prevention.md

---

## 1. Executive Summary

Aelu's email and experimentation systems are substantially more mature than most products at this stage. The email copy is unusually good — first-person, calm, guilt-free, with real study tips woven in. The experiment daemon is architecturally sound: O'Brien-Fleming sequential testing, guardrails, graduated rollouts. The churn detection system differentiates by type (boredom, frustration, habit_fade, life_event) rather than treating churn as monolithic.

**What works well:**
- Email copy tone is excellent and doctrine-aligned
- Churn type classification is a genuine differentiator
- Sequential testing with guardrails prevents shipping harm
- One-click unsubscribe, no-guilt pause, explicit cancellation options
- Deterministic trigger detection (no runtime ML, no guessing)

**What needs attention:**
1. **Email cadence is too dense for churn prevention** — 4 emails in 14 days to a paid user who stopped is aggressive, especially given the doctrine
2. **The experiment daemon has too much unreviewed autonomy** — it auto-proposes, auto-starts, and auto-concludes without human checkpoints on pedagogy-affecting changes
3. **Churn type labels are treated as conclusions** — the daemon maps them directly to experiment templates without acknowledging uncertainty
4. **No counter-metrics exist** — guardrails measure shallow engagement (completion_rate, crash_rate, churn_days) but nothing about learning quality, trust, or pressure
5. **Weekly progress emails report stats but not Mandarin artifacts** — they tell you "37 words practiced" but not which words, missing a chance to make progress feel real
6. **The intelligence engine has no self-audit** — no measurement of prediction accuracy, false positive rates, or calibration
7. **Several onboarding emails are builder-facing** — they explain how the system works technically rather than what the learner gets

**Recommendation:** Tighten email cadence, add human review gates for pedagogy-affecting experiments, introduce counter-metrics and self-audit, and make progress emails show concrete Mandarin.

---

## 2. Findings on Current Email System

### 2.1 Architecture

The email system is well-structured:

- **Provider:** Resend REST API (`mandarin/email.py`)
- **Trigger detection:** Deterministic SQL rules in `mandarin/marketing_hooks.py` (14 rules)
- **Scheduler:** Hourly daemon thread in `mandarin/web/email_scheduler.py`
- **Deduplication:** `lifecycle_event` table with `check_already_sent()` using JSON metadata extraction
- **Opt-out:** `marketing_opt_out` flag on user table, HMAC-signed one-click unsubscribe
- **Templates:** HTML in `marketing/email-templates/`, full copy in `marketing/email-sequences.md`

### 2.2 Email Sequences

| Sequence | Trigger | Emails | Window | Target |
|---|---|---|---|---|
| Free onboarding | Signup | 7 | 14 days | All free users |
| Activation nudge | Signup, no session | 3 | 10 days | Non-starters |
| Free-to-paid upgrade | HSK 2 boundary | 5 | 21 days | Free users at boundary |
| Paid onboarding | Upgrade | 5 | 30 days | New paid users |
| Churn prevention | Inactivity (paid) | 4 | 14 days | Inactive paid users |
| Cancellation | Cancel event | 2 | 7 days | Cancelled users |
| Win-back | Post-cancellation | 3 | 30 days | Former paid users |
| Weekly progress | Monday, active | 1/week | Ongoing | Users with sessions |

**Total email capacity:** A user who signs up free, activates on day 3, reaches HSK 2 boundary at week 6, upgrades, then churns could receive ~25 emails over 3 months. That's reasonable in aggregate, but the churn prevention sequence is dense.

### 2.3 Positive Findings

**Tone is doctrine-aligned.** The copy reads like a real person who built the product and studies Mandarin themselves. Examples:
- Activation nudge #3: "Should I keep sending these emails?" — honest, no guilt
- Churn prevention #4: "I'd rather you make the right call for yourself than pay for something you're not using" — genuinely respectful
- Cancellation: "No guilt, no 'are you sure?'" — matches doctrine exactly

**Study tips are woven into marketing.** Churn prevention email #1 isn't a "come back" email — it's a real tip about listening vs. reading skill gaps. Email #2 is about the minimum viable routine. This is the right instinct: value-first, not ask-first.

**Pause is prominently offered.** Churn prevention #3 and #4 both offer pause as a first-class option. The churn-prevention.md playbook explicitly rejects "we miss you" language.

**Transactional emails are clean.** Cancellation confirmation is matter-of-fact. Receipt emails (not fully reviewed but template exists) appear standard.

---

## 3. Doctrine-Based Critique of Each Email Category

### 3.1 Activation Nudge Sequence (3 emails over 10 days)

**Verdict: Good, with one concern.**

- Email 1 (day 2): Good — walks through what the first session looks like. Value-first.
- Email 2 (day 5): Mixed — "Most people who try one session come back for a second" is technically social proof, which is fine, but edges toward persuasion. The forgetting curve tip is excellent and redeems it.
- Email 3 (day 10): Excellent — "Should I keep sending these?" is the gold standard for respectful final outreach.

**Concern:** The sequence starts at day 2 (24 hours). For a free product with no time pressure, contacting someone 24 hours after signup feels slightly eager. Some people sign up and intend to start on the weekend.

**Recommendation:** Shift email 1 to day 3, email 2 to day 7, email 3 to day 14. This is less dense and respects the fact that free users have no urgency.

### 3.2 Free User Onboarding (7 emails over 14 days)

**Verdict: Strong, with builder-facing framing issues.**

The study tips (email 4: tone pairs, email 6: cleanup loop) are genuinely excellent — the kind of content that makes someone glad they're subscribed to these emails.

**Issues:**

1. **Email 1 (welcome):** "The system picks from 44 drill types" is builder-facing. The learner doesn't care about the number 44. They care that practice feels varied and targets their weaknesses. Reframe: "Each session adapts to your weakest skill. You'll get a mix of recognition, listening, speaking, and reading drills — different each time."

2. **Email 3 (after first session):** "mixed practice produces stronger retention than doing one type repeatedly" — this is true but reads like a research paper summary. Reframe in learner terms: "Your sessions deliberately mix things up because your brain retains more when practice varies."

3. **Email 5 (week 1 progress):** Reports `{{drill_types_count}} of 27` — the learner doesn't know what "27 drill types" means or why they should care about encountering more of them. Replace with something the learner recognizes: specific characters they got right, or a tone pair they improved on.

4. **Cadence:** 7 emails in 14 days = one every 2 days. This is slightly dense for a user who is already engaged (they're doing sessions). Consider dropping email 4 (day 4 study tip) to the newsletter cadence instead, reducing to 6 in 14 days.

**Recommendation:** Reframe feature descriptions in learner-facing terms. Replace abstract stats with concrete Mandarin artifacts. Consider reducing to 6 emails.

### 3.3 Free-to-Paid Upgrade (5 emails over 21 days)

**Verdict: Competent but with two doctrine tensions.**

This sequence is well-constructed — it leads with a real milestone, explains features in terms of learning value, and offers a genuine discount. But:

1. **Email 5 (discount):** "Offer good for 7 days" introduces a time constraint. The very next sentence tries to defuse it ("I'm not going to pretend it's 'the last chance ever'"), but the 7-day window is still manufactured urgency. The doctrine says: no fake scarcity, no manipulative urgency. A 7-day expiring offer walks the line.

   **Recommendation:** Either make the discount available indefinitely with a fixed code, or remove the time constraint and say "this code works whenever you're ready." The loss in conversion is small; the gain in trust alignment is real.

2. **Email 3 (value framing):** "Less than a single baozi" — this is the "$X per day" framing that marketing departments use to make prices feel small. It's not dishonest, but it's a technique. The doctrine says the product should feel like a sage, not a marketer.

   **Recommendation:** Keep the price comparison to tutoring (which is genuinely relevant — $0.50/day vs. $15/15-min tutoring session). Drop the baozi comparison.

### 3.4 Weekly Progress Emails

**Verdict: Needs significant improvement.**

Current stats reported: sessions, items reviewed, accuracy, accuracy trend, words in long-term memory, streak, next milestone. These are all abstract numbers.

**Doctrine test failure:** These emails speak like SaaS automation, not like a humane guide. "3 sessions, 37 items, 82% accuracy" tells you that something happened but doesn't make learning feel real.

**What's missing:**
- **Concrete Mandarin artifacts.** Show the learner 2-3 specific words they moved from "shaky" to "stable" this week. Show a sentence they can now read that they couldn't a week ago. Show a tone pair they improved on.
- **Evidence of progress that feels personal.** Not "82% accuracy" but "你 correctly recalled 说服 (persuade) after a 12-day gap — that's durable memory."
- **Honest acknowledgment when progress is flat.** If accuracy didn't change, say "steady week — you reviewed 37 items and kept them from decaying, which is what consistency looks like."

**Recommendation:** Redesign the weekly progress email to lead with 2-3 concrete Mandarin moments (specific characters/words/sentences), followed by summary stats. Pull from `review_event` and `progress` tables to identify items that crossed mastery thresholds this week.

### 3.5 Churn Prevention (4 emails over 14 days)

**Verdict: Tone is excellent. Cadence is too dense.**

The copy itself is among the best in the system. Email #1 is a genuine study tip. Email #3 explicitly says "I'm not writing to guilt you." Email #4 offers pause, cancel, and resume as equal options.

**The problem is density.** 4 emails in 14 days to someone who has *stopped using the product* means:
- Day 5: email
- Day 8: email (3 days later)
- Day 12: email (4 days later)
- Day 19: email (7 days later)

A paid user who takes a 2-week break receives 3 emails in that window. For someone dealing with a life event, illness, travel, or burnout, receiving 3 emails in 2 weeks from a product they're not using creates ambient pressure, even if each individual email is respectful.

**Doctrine test:** Would this feel respectful to an exhausted or embarrassed learner? Each email individually: yes. The sequence as a cadence: borderline. The cumulative effect of "I see you're not here" repeated 4 times in 2 weeks is a form of pressure, regardless of how gently each message is worded.

**Recommendation:**
- Reduce to 3 emails over 21 days: day 7, day 14, day 21
- Email 1 (day 7): Study tip (value-first, no mention of absence)
- Email 2 (day 14): Honest check-in with pause offer
- Email 3 (day 21): Final outreach with all options (resume, pause, cancel)
- Drop the day 5 email entirely — 5 days is too short for a meaningful signal of churn in a learning product

### 3.6 Cancellation Emails

**Verdict: Excellent. No changes needed.**

The cancellation confirmation is a model of how to do this right: clear about what happens, no retention flow, one-question survey, explicit "no guilt."

### 3.7 Win-Back (3 emails over 30 days post-cancel)

**Verdict: Reasonable, with one concern.**

The win-back sequence is spaced appropriately (30, 45, 60 days post-cancel). However:

**Concern:** The code triggers win-back emails starting at day 7 post-cancellation, not day 30 as documented in email-sequences.md. In `marketing_hooks.py` line 397: `if days >= 7 and not check_already_sent(uid, "winback", 1, conn)`. The documented sequence says "30 days after cancellation." This is a code-documentation mismatch that should be fixed.

**Recommendation:** Align code to documentation: start win-back at day 30 post-cancel. Day 7 is too soon after cancellation — the user *just* made an active decision to leave.

### 3.8 Push Notifications

**Verdict: Needs scrutiny.**

The streak reminder (`email_scheduler.py` line 176-217) sends push notifications to users who studied yesterday but not today and have `streak_reminders` enabled. The message is: `"{streak_days}-day streak"` + `"Items ready for review. About 5 minutes."`

The daily reminder (`email_scheduler.py` line 334-368) sends: `"Ready to practice?"` + `"A quick session keeps your memory fresh."`

**Doctrine tension:** DOCTRINE.md §6 says "Reminders: informational only, never emotional." The streak notification mentions the streak count, which creates implicit pressure ("don't break it"). BRAND.md explicitly says: "Not a streak machine (noted, not celebrated)."

**Recommendation:** Change streak notification to just `"Items ready for review. About 5 minutes."` — drop the streak count. The daily reminder is acceptable as-is (informational, not emotional).

---

## 4. Email Doctrine Test Suite

Every email must pass ALL of the following before shipping. Any single failure blocks the email.

### Pressure & Manipulation

| # | Question | Pass Criterion |
|---|----------|---------------|
| P1 | Does this email induce guilt about not studying? | No guilt language, no "we miss you," no "you're falling behind" |
| P2 | Does this email create artificial urgency? | No countdown timers, no expiring offers < 30 days, no "last chance" |
| P3 | Does this email use loss framing? | No "you'll lose your streak/progress/data" unless factually true AND actionable |
| P4 | Does this email pressure the learner emotionally? | No sad faces, no emotional manipulation, no manufactured FOMO |
| P5 | Does this email disguise marketing as content? | Marketing emails must be honest about their purpose; tips emails must contain genuine tips |

### Tone & Voice

| # | Question | Pass Criterion |
|---|----------|---------------|
| T1 | Does this sound like a humane guide or like SaaS automation? | First-person singular, calm, specific, no "we're excited to announce" |
| T2 | Does this respect the learner's intelligence? | No oversimplification, no condescension, no "Great job!" |
| T3 | Does this use builder-facing framing? | No "44 drill types" — describe what the learner experiences, not what the system does |
| T4 | Would this still feel respectful to an exhausted learner? | Read it imagining the recipient is overwhelmed, behind, and slightly ashamed |
| T5 | Does this use BRAND.md voice? | Calm adult. Data-grounded. No praise inflation. Forward-directed. |

### Re-Entry & Dignity

| # | Question | Pass Criterion |
|---|----------|---------------|
| R1 | Does this help re-entry feel safe? | Returning learner should feel welcomed, not evaluated |
| R2 | Does this acknowledge that gaps are normal? | Explicitly or implicitly frames breaks as ordinary, not failures |
| R3 | Does this offer genuine options? | Resume, pause, and cancel presented as equally valid choices |
| R4 | Does this avoid counting the learner's absence? | No "It's been X days since..." unless paired with constructive context |

### Progress & Truthfulness

| # | Question | Pass Criterion |
|---|----------|---------------|
| Q1 | Does this exaggerate progress? | All claims must be traceable to real data; no rounding up, no "almost there" without evidence |
| Q2 | Does this include concrete Mandarin? | Progress emails must reference specific characters, words, or skills — not just numbers |
| Q3 | Does this honestly represent the learner's state? | If accuracy is flat or declining, acknowledge it without euphemism |

### Cadence & Consent

| # | Question | Pass Criterion |
|---|----------|---------------|
| C1 | Is this email part of a sequence that's too dense? | No more than 1 email per 5 days during churn prevention; no more than 1 per 2 days during onboarding |
| C2 | Does the learner have a clear, one-click way to stop? | Every email includes unsubscribe; sequence emails include "stop sending these" option |
| C3 | Has this sequence been reviewed for cumulative pressure? | Read the entire sequence as a unit, not just individual emails |

### Implementation

This test suite should be stored as a checklist in `marketing/email-doctrine-checklist.md` and referenced in code review for any email change. Automated enforcement is possible for some criteria (cadence limits, unsubscribe link presence) via the existing `test_email_contract.py`.

---

## 5. Findings on Current Experimentation/Autonomy System

### 5.1 Architecture

The experimentation system is architecturally strong:

- **Experiment lifecycle:** draft → running → paused → concluded (`mandarin/experiments.py`)
- **Assignment:** Deterministic SHA256 hashing (same user, same variant every time)
- **Statistical analysis:** User-level aggregation, two-proportion z-test, Cohen's d, Wilson score CIs
- **Sequential testing:** O'Brien-Fleming spending function with adaptive alpha
- **Guardrails:** session_completion_rate, crash_rate, churn_days; auto-pause on 5% degradation
- **Daemon:** 6-hour cycle (`mandarin/web/experiment_daemon.py`) — monitor, conclude, rollout, propose, auto-start
- **Graduated rollout:** pending → 25% → 50% → 100% → complete (3 days per stage)

### 5.2 What Works

- **Sequential testing is the right call.** O'Brien-Fleming is conservative early (prevents premature stopping on noise) and appropriate late. This is better than most A/B testing implementations.
- **User-level aggregation** prevents Simpson's paradox. This is correct and often overlooked.
- **Graduated rollouts** reduce blast radius of bad winners. 12 days from conclusion to 100% is reasonable.
- **Guardrail auto-pause** is a genuine safety net. If completion rate drops 5%+ in treatment, the experiment pauses automatically.

### 5.3 What's Wrong

**Problem 1: The daemon treats churn type labels as ground truth.**

`experiment_daemon.py` line 241-288: The daemon calls `get_at_risk_users(min_risk=50)`, aggregates by `churn_type`, and directly creates experiment proposals from templates:
- boredom → `auto_drill_variety`
- frustration → `auto_difficulty_easing`
- habit_fade → `auto_session_length`

But `churn_type` is a deterministic decision tree classification (`churn_detection.py` line 448-470) that makes hard calls based on thresholds. A user with duration declining 41% and low drill diversity gets classified as "boredom," but the actual cause could be anything — they got a new job, their commute changed, they're sick. The classification is a *hypothesis*, not a diagnosis.

**The daemon doesn't know this.** It treats "5 users classified as boredom" as sufficient evidence to propose and auto-start an experiment changing drill variety. The system interprets its own signal, generates an intervention, and evaluates the result — a closed loop with no external check.

**Problem 2: Auto-start has no human review gate.**

`experiment_daemon.py` line 290-322: If no experiments are running, the daemon auto-starts the top pending proposal. There is no distinction between low-risk experiments (changing a subject line) and high-risk experiments (changing drill variety, which affects what learners practice and therefore what they learn).

**Problem 3: Guardrails measure engagement, not learning quality.**

The three guardrail metrics are:
- `session_completion_rate` — did the user finish the session?
- `crash_rate` — did the app crash?
- `churn_days` — days since last session

None of these measure:
- Did the learner actually retain what they practiced?
- Did the difficulty of content change (did we make things easier just to boost completion)?
- Did the learner feel more pressured or more at ease?
- Did unsubscribe or pause rates change?
- Was the experience of re-entry affected?

A treatment variant could boost completion_rate by making sessions easier, pass all guardrails, and get auto-concluded as a winner — while actually degrading learning quality.

**Problem 4: No counter-metrics.**

Every optimization metric can be gamed. Without counter-metrics, the system is vulnerable to Goodhart's Law: the metric becomes the target, and the thing the metric was supposed to measure stops being measured.

**Problem 5: The intelligence engine has no self-audit.**

There is no measurement of:
- How often the churn type classification is correct
- How often the daemon's experiment proposals actually produce wins
- The false positive rate of guardrail alerts
- Calibration of the sequential test (do experiments that reach p=0.04 actually replicate?)

---

## 6. Recommended Governed-Autonomy Architecture

### 6.1 Design Principles

1. **Observation is always safe.** Measuring things can't hurt anyone.
2. **Evaluation should be stable.** Metrics should be computed the same way every time.
3. **Diagnosis is a hypothesis.** Every diagnosis must carry confidence, evidence, and risk-if-wrong.
4. **Action must be risk-tiered.** Low-risk reversible actions can be autonomous. High-risk or pedagogy-affecting actions require review.

### 6.2 Four-Layer Architecture

```
Layer 1: OBSERVATION (always autonomous)
  ├── Session metrics (accuracy, duration, completion, modality mix)
  ├── Review event logs (per-item recall, response time, error type)
  ├── Retention statistics (half-life, predicted recall, calibration)
  ├── Engagement snapshots (risk score, risk factors)
  └── Email/push delivery and response tracking

Layer 2: EVALUATION (always autonomous)
  ├── Churn risk score (0-100, weighted signals)
  ├── Abandonment risk score (0-1, 5-factor model)
  ├── Experiment results (completion, accuracy, per-variant stats)
  ├── Guardrail checks (completion, crash, churn, PLUS new counter-metrics)
  ├── Cohort snapshots (classroom-level aggregates)
  └── Retention cohort analysis (Kaplan-Meier survival)

Layer 3: DIAGNOSIS (autonomous with mandatory uncertainty)
  ├── Churn type classification → HYPOTHESIS, not conclusion
  │   Must include: evidence, confidence (0-1), affected_count, risk_if_wrong
  ├── Experiment interim reads → statistical interpretation with alpha spending
  ├── Guardrail violation detection → must distinguish real signal from noise
  └── Engagement trend analysis → must include confidence interval

Layer 4: ACTION (risk-tiered)
  ├── auto_safe: can execute without human review
  ├── review_required: must be proposed, logged, and reviewed before execution
  └── blocked: cannot be automated; requires explicit human decision
```

### 6.3 Risk-Tiered Autonomy

**auto_safe** — the daemon can do these without asking:
- Monitor running experiments and compute interim results
- Log observations and compute evaluations
- Auto-pause experiments when guardrails are violated
- Advance graduated rollouts that have already been concluded
- Generate weekly digests
- Send emails that pass the doctrine test and are within approved cadence

**review_required** — the daemon can propose these but not execute:
- Start any new experiment (all experiments, not just high-risk ones — at this stage of the product, human review is appropriate for all experiments)
- Conclude experiments where the winner is a treatment variant (control wins can be auto-concluded since they mean "do nothing different")
- Any experiment affecting pedagogy: drill variety, difficulty, content ordering, mastery thresholds, progress claims
- Any experiment affecting email tone, cadence, or content
- Rollout of treatment winners beyond 25%

**blocked** — cannot be automated under any circumstances:
- Changes to mastery stage definitions or thresholds
- Changes to what constitutes "truthful" progress claims
- Changes to the SRS algorithm parameters (ease factor, interval calculation)
- Changes to content difficulty ratings
- Changes to the email doctrine test suite itself
- Changes that would increase email cadence beyond current limits

---

## 7. Action Taxonomy Table

| Action | Current Autonomy | Recommended Autonomy | Rationale |
|--------|-----------------|---------------------|-----------|
| **Observation & Evaluation** | | | |
| Compute churn risk scores | auto | auto_safe | Pure measurement, no side effects |
| Generate engagement snapshots | auto | auto_safe | Pure measurement |
| Compute experiment results | auto | auto_safe | Pure measurement |
| Check guardrails | auto | auto_safe | Pure measurement |
| Log lifecycle events | auto | auto_safe | Pure observation |
| **Experiment Lifecycle** | | | |
| Auto-pause on guardrail violation | auto | auto_safe | Protective action, always safe to stop |
| Conclude experiment (control wins) | auto | auto_safe | "Do nothing different" is low-risk |
| Conclude experiment (treatment wins) | auto | **review_required** | Treatment win means changing default behavior |
| Propose experiment from churn signals | auto | auto_safe (propose only) | Proposing is safe; starting is not |
| Auto-start experiment | auto | **review_required** | All experiments should be reviewed before launch |
| Create graduated rollout | auto | auto_safe | Just creates the record; doesn't roll out |
| Advance rollout: 0% → 25% | auto | auto_safe | Low blast radius |
| Advance rollout: 25% → 50% | auto | **review_required** | Significant population affected |
| Advance rollout: 50% → 100% | auto | **review_required** | Full rollout should be deliberate |
| **Pedagogy-Affecting** | | | |
| Change drill variety mix | auto (via experiment) | **review_required** | Affects what learners practice |
| Change difficulty calibration | auto (via experiment) | **blocked** | Affects truthfulness of mastery claims |
| Change session length | auto (via experiment) | **review_required** | Affects learning dose |
| Change SRS parameters | not automated | **blocked** | Core algorithm, requires manual review |
| Change mastery thresholds | not automated | **blocked** | Affects truthfulness of progress claims |
| **Email** | | | |
| Send scheduled lifecycle email | auto | auto_safe | Within approved cadence and templates |
| Change email content/copy | not automated | **review_required** | Must pass doctrine test |
| Change email cadence | not automated | **blocked** | Cadence is a doctrine-level decision |
| Send weekly progress | auto | auto_safe | Within approved template |
| **Notifications** | | | |
| Send push reminder | auto | auto_safe | User has opted in via streak_reminders |
| Change push notification content | not automated | **review_required** | Must pass doctrine test |

---

## 8. Metrics + Counter-Metrics Framework

For every optimization metric, define a counter-metric that detects gaming or shallow wins.

| Primary Metric | What It Measures | Counter-Metric | What It Catches |
|---------------|-----------------|----------------|-----------------|
| Session completion rate | Did user finish? | Post-session delayed recall (24h) | Sessions that feel complete but don't produce learning |
| Session completion rate | Did user finish? | Difficulty integrity (avg difficulty of completed items) | Completion boosted by making sessions easier |
| Accuracy | Did user answer correctly? | Delayed retention (7-day recall of items marked correct) | Correct answers that don't stick |
| Accuracy | Did user answer correctly? | Transfer rate (correct in new modality for known items) | Accuracy in one modality that doesn't generalize |
| Retention (day 7/30) | Did user come back? | Unsubscribe + pause rate | Users who come back but are unhappy |
| Retention (day 7/30) | Did user come back? | Session quality (accuracy * items * duration) | Users who come back but do less |
| Engagement (sessions/week) | Is user active? | Complaint/feedback signal (negative feedback count) | Active but frustrated users |
| Engagement (sessions/week) | Is user active? | Re-entry burden (accuracy drop after gap) | Users whose return is punishing |
| Email open rate | Did user see the email? | Unsubscribe rate post-email | Emails that get opened but cause opt-out |
| Email click rate | Did user engage? | Session quality post-click | Clicks that don't lead to meaningful sessions |
| Experiment completion rate | Is treatment "winning"? | Counter-metric composite: delayed recall + difficulty integrity + unsubscribe rate | Experiments that win on shallow metrics but degrade learning |

### Implementation

Add to the guardrail check in `experiments.py`:

```python
GUARDRAIL_METRICS = {
    "session_completion_rate": {"direction": "higher_better", "threshold": 0.05},
    "crash_rate": {"direction": "lower_better", "threshold": 0.05},
    "churn_days": {"direction": "lower_better", "threshold": 0.05},
    # NEW counter-metric guardrails:
    "delayed_recall_24h": {"direction": "higher_better", "threshold": 0.05},
    "difficulty_integrity": {"direction": "neutral", "threshold": 0.10},
    "unsubscribe_rate": {"direction": "lower_better", "threshold": 0.02},
    "pause_rate": {"direction": "lower_better", "threshold": 0.03},
}
```

The `difficulty_integrity` metric measures whether the average difficulty of items shown in treatment differs from control by more than 10%. If treatment is "winning" because it's showing easier items, the guardrail catches it.

---

## 9. Intelligence Engine Self-Audit Framework

The intelligence engine (churn detection, experiment daemon, engagement scoring) must be judged on the quality of its reasoning, not just whether it produces activity.

### 9.1 Metrics to Track

| Metric | What It Measures | How to Compute | Target |
|--------|-----------------|----------------|--------|
| Churn classification accuracy | Does the churn_type match actual re-engagement pattern? | Compare predicted type to actual behavior 30 days later | >60% agreement |
| Churn score calibration | When we say "70% risk," do 70% actually churn? | Bin users by risk score, compare predicted vs. actual churn at 14 days | Brier score <0.20 |
| Guardrail false positive rate | How often do we pause experiments that didn't actually have a problem? | Track paused experiments that, on re-analysis with more data, show no degradation | <20% |
| Guardrail false negative rate | How often do we miss degradation? | Periodic retrospective: compare experiment-period metrics to post-experiment baseline | <10% |
| Experiment proposal win rate | How often do daemon-proposed experiments produce a winner? | Track proposals → started experiments → conclusions; compute win rate | >30% (above random chance for 2-variant) |
| Intervention lift | Do churn interventions actually reduce churn? | Compare intervened users to matched controls (same risk score, no intervention) | Measurable positive lift |
| Prediction drift | Is the churn model getting worse over time? | Monthly recalculation of Brier score; alert on >0.05 increase | Stable or improving |
| Confidence calibration | Are "high confidence" diagnoses more accurate than "low confidence" ones? | Bin diagnoses by stated confidence; compare to actual outcomes | Monotonically increasing accuracy by confidence band |

### 9.2 Audit Schedule

| Frequency | Action | Output |
|-----------|--------|--------|
| Every experiment conclusion | Log predicted vs. actual outcome | Row in `intelligence_audit` table |
| Weekly (daemon digest) | Summarize: experiments monitored, proposals made, guardrail triggers | Digest entry in `lifecycle_event` |
| Monthly | Compute Brier score, win rate, false positive/negative rates | Monthly audit row in `intelligence_audit` |
| Quarterly | Manual review: read all experiment proposals and conclusions; assess reasoning quality | Human review document |

### 9.3 Self-Audit Table

New table: `intelligence_audit`

```sql
CREATE TABLE intelligence_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_type TEXT NOT NULL,  -- 'churn_calibration', 'experiment_outcome', 'guardrail_accuracy', 'monthly_summary'
    audit_period TEXT,         -- '2026-03' or specific experiment name
    metrics TEXT NOT NULL,     -- JSON: { brier_score, win_rate, false_positive_rate, ... }
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 10. Trigger Architecture

### 10.1 Post-Session Hook

**Current:** `db/session.py` → `end_session()` logs `session_complete` lifecycle event, checks for activation (3+ sessions in 14 days). `runner.py` → `_post_session_nudges()` handles implementation intention + pre-commitment.

**Recommended scope:**

| Capability | Allowed? | Notes |
|-----------|----------|-------|
| Observe: log session metrics | Yes | Always |
| Observe: compute session retention stats | Yes | `compute_session_metrics()` |
| Evaluate: update engagement snapshot | Yes | Only if >1 hour since last snapshot |
| Evaluate: update churn risk score | Yes | Recompute, log if changed significantly |
| Diagnose: classify churn type | No | Too early; wait for nightly batch |
| Act: trigger email | No | Emails are cadence-controlled via scheduler |
| Act: modify next session plan | No | Session planning is separate concern |

**Audit logging:** Every post-session hook invocation should log to `lifecycle_event` with `event_type='session_complete'` (already done) plus session_id in metadata.

### 10.2 Nightly Batch Job

**Current:** No single "nightly batch." Work is distributed across 10 scheduler threads with varying intervals.

**Recommended: Consolidate into a single nightly batch** that runs once daily at 03:00 UTC:

| Step | Capability | Allowed? |
|------|-----------|----------|
| 1 | Generate engagement snapshots for all active users | Yes (observe) |
| 2 | Compute churn risk scores for all users | Yes (evaluate) |
| 3 | Run churn type classification | Yes (diagnose — but log as hypothesis with confidence) |
| 4 | Check email triggers | Yes (evaluate — identify pending emails) |
| 5 | Compute intelligence self-audit metrics | Yes (evaluate) |
| 6 | Propose experiments from accumulated signals | Yes (propose only — not start) |
| 7 | Score intervention effectiveness (7+ day old interventions) | Yes (evaluate) |

**Audit logging:** Log batch start, each step completion, and batch end to `lifecycle_event` with `event_type='nightly_batch'` and step details in metadata.

### 10.3 Experiment Daemon (every 6 hours)

**Current:** Monitors, concludes, proposes, auto-starts, rolls out.

**Recommended scope (revised):**

| Step | Current | Recommended | Change |
|------|---------|-------------|--------|
| Monitor active experiments | auto | auto_safe | No change |
| Auto-pause on guardrail violation | auto | auto_safe | No change |
| Auto-conclude (treatment wins) | auto | **review_required** | Daemon proposes conclusion; admin confirms |
| Auto-conclude (control wins / futility) | auto | auto_safe | No change (no action = safe) |
| Create rollout records | auto | auto_safe | Just a record, no user impact |
| Advance rollout 0→25% | auto | auto_safe | Low blast radius |
| Advance rollout 25%+ | auto | **review_required** | Significant population |
| Propose experiments | auto | auto_safe | Proposing is always safe |
| Auto-start experiments | auto | **review_required** | All starts require review |
| Weekly digest | auto | auto_safe | No change |

**Audit logging:** Every daemon tick should log a structured entry to `lifecycle_event` with `event_type='experiment_daemon_tick'` containing: experiments_monitored, actions_taken (list of {action, experiment, rationale}), proposals_made, errors_encountered.

### 10.4 CI / Release Gate

**Current:** `scripts/audit_check.py` runs 13 deterministic checks (SQL injection, auth patterns, schema consistency, test coverage).

**Recommended additions:**

| Check | What It Verifies |
|-------|-----------------|
| E1 | No email template changes without doctrine test suite entry in PR description |
| E2 | No changes to `_CHURN_EXPERIMENT_TEMPLATES` without explicit approval comment |
| E3 | No changes to `GUARDRAIL_DEGRADATION_THRESHOLD` without explicit approval comment |
| E4 | `email-doctrine-checklist.md` exists and is not empty |
| E5 | Experiment daemon `_daemon_tick` logs audit entry (check that logging call exists in code) |

### 10.5 Admin / Manual Run

**Current:** `python -m mandarin.churn_detection` runs CLI report. No admin CLI for experiments.

**Recommended CLI additions:**

```
mandarin experiment list [--status running|concluded|paused]
mandarin experiment results <name>
mandarin experiment approve-start <proposal-name>
mandarin experiment approve-conclude <name> --winner <variant>
mandarin experiment approve-rollout <name> --stage <25pct|50pct|100pct>
mandarin experiment pause <name> --reason <text>
mandarin audit intelligence --period <YYYY-MM>
mandarin email test-doctrine <template-name>
```

**Audit logging:** Every manual admin action logs to `lifecycle_event` with `event_type='admin_action'` and the action details in metadata.

---

## 11. Concrete Code Change Plan

### 11.1 Files to Create

| File | Purpose |
|------|---------|
| `mandarin/experiment_governance.py` | Governance layer: risk-tier classification, approval queue, review_required enforcement |
| `mandarin/counter_metrics.py` | Counter-metric computation: delayed_recall_24h, difficulty_integrity, unsubscribe_rate, pause_rate |
| `mandarin/intelligence_audit.py` | Self-audit: Brier score, classification accuracy, win rate, calibration |
| `marketing/email-doctrine-checklist.md` | The doctrine test suite from Section 4, formatted as a checklist |
| `tests/test_experiment_governance.py` | Tests for governance layer |
| `tests/test_counter_metrics.py` | Tests for counter-metrics |
| `tests/test_intelligence_audit.py` | Tests for self-audit |

### 11.2 Files to Modify

| File | Changes |
|------|---------|
| `mandarin/web/experiment_daemon.py` | (1) Replace auto-start with proposal-only (queue for review). (2) Replace auto-conclude for treatment wins with proposal-to-conclude (queue for review). (3) Add audit logging for every tick. (4) Add counter-metric checks to guardrail evaluation. |
| `mandarin/experiments.py` | (1) Expand guardrail metrics to include counter-metrics. (2) Add `difficulty_integrity` guardrail. (3) Add `delayed_recall` guardrail. |
| `mandarin/churn_detection.py` | (1) Add confidence score to `_classify_churn_type()` output. (2) Add `risk_if_wrong` field. (3) Add `evidence` list. |
| `mandarin/marketing_hooks.py` | (1) Fix win-back trigger: change day 7 to day 30 to match documentation. (2) Add cadence validation. |
| `mandarin/web/email_scheduler.py` | (1) Reduce churn prevention cadence: day 7, 14, 21 instead of day 5, 8, 12, 19. (2) Remove streak count from push notification copy. (3) Add weekly progress email enhancement: include concrete Mandarin artifacts. |
| `mandarin/email.py` | (1) Add `send_weekly_progress_v2()` that accepts specific word/character data. (2) Keep backward compatibility with existing `send_weekly_progress()`. |
| `marketing/email-sequences.md` | (1) Update churn prevention cadence to match new day 7/14/21. (2) Update activation nudge cadence to day 3/7/14. (3) Reframe builder-facing language in onboarding emails. (4) Redesign weekly progress template to lead with Mandarin artifacts. |
| `marketing/email-templates/weekly-progress.html` | (1) Add section for "Words you strengthened this week" with actual hanzi/pinyin. (2) Add "This week's best recall" showing a specific item with its retention trajectory. |
| `scripts/audit_check.py` | Add checks E1-E5 from Section 10.4 |

### 11.3 Database Changes

New migration (V103):

```sql
-- Intelligence audit table
CREATE TABLE IF NOT EXISTS intelligence_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_type TEXT NOT NULL,
    audit_period TEXT,
    metrics TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_intelligence_audit_type ON intelligence_audit(audit_type);
CREATE INDEX IF NOT EXISTS idx_intelligence_audit_period ON intelligence_audit(audit_period);

-- Experiment governance: approval queue
CREATE TABLE IF NOT EXISTS experiment_approval_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,  -- 'start', 'conclude', 'rollout_advance'
    experiment_name TEXT NOT NULL,
    proposed_by TEXT NOT NULL DEFAULT 'daemon',
    proposal_data TEXT,  -- JSON: winner, evidence, confidence, risk_tier
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'rejected'
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_approval_queue_status ON experiment_approval_queue(status);

-- Add confidence and evidence to churn risk detection
-- (Already stored as JSON in lifecycle_event metadata, so no schema change needed —
--  just enrich the metadata in churn_detection.py)

-- Counter-metric tracking: delayed recall samples
CREATE TABLE IF NOT EXISTS delayed_recall_sample (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    content_item_id INTEGER NOT NULL,
    experiment_name TEXT,
    variant TEXT,
    initial_correct INTEGER NOT NULL,  -- was the item correct in the original session?
    recall_correct INTEGER,  -- was it correct 24h later? NULL until measured
    initial_session_id INTEGER,
    recall_session_id INTEGER,
    initial_at TEXT NOT NULL,
    recall_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_delayed_recall_user ON delayed_recall_sample(user_id, recall_correct);
CREATE INDEX IF NOT EXISTS idx_delayed_recall_exp ON delayed_recall_sample(experiment_name, variant);
```

### 11.4 Cron / Scheduler Design

Consolidate the nightly batch into a single scheduler entry:

| Scheduler | Frequency | Thread Name | Lock Name |
|-----------|-----------|-------------|-----------|
| Email scheduler | Hourly | email-scheduler | email_scheduler |
| Experiment daemon | 6 hours | experiment-daemon | experiment_daemon |
| **Nightly intelligence batch** (new) | Daily at 03:00 UTC | nightly-intelligence | nightly_intelligence |
| Quality metrics | Daily | quality-scheduler | quality_scheduler |
| AI feedback | Daily | ai-feedback | ai_feedback_scheduler |
| Stale session cleanup | Hourly | stale-session | stale_session_scheduler |
| Retention purge | Weekly | retention-purge | retention_scheduler |
| Interference detection | Daily | interference | interference_scheduler |
| Security scan | Weekly | security-scan | security_scan_scheduler |
| Web crawl | 6 hours | crawl | crawl_scheduler |
| OpenClaw | Hourly | openclaw | openclaw_scheduler |

The new `nightly_intelligence` scheduler consolidates: engagement snapshots, churn scoring, intelligence self-audit, and delayed recall measurement.

### 11.5 Admin Visibility

Add to `mandarin/web/admin_routes.py`:

1. **`GET /api/admin/approval-queue`** — List pending approvals (experiment starts, conclusions, rollout advances)
2. **`POST /api/admin/approval-queue/<id>/approve`** — Approve a pending action
3. **`POST /api/admin/approval-queue/<id>/reject`** — Reject with reason
4. **`GET /api/admin/intelligence-audit`** — View self-audit metrics by period
5. **`GET /api/admin/counter-metrics/<experiment_name>`** — View counter-metrics for a specific experiment

The admin dashboard should surface:
- Pending approval count (badge in nav)
- Intelligence health: Brier score trend, win rate, false positive rate
- Experiment counter-metrics alongside primary metrics

---

## 12. Phased Implementation Roadmap

### Phase 1: Measurement Integrity (Week 1-2)
**Goal:** Measure before you automate. Don't change behavior yet.

1. Create `marketing/email-doctrine-checklist.md` (Section 4)
2. Create `mandarin/counter_metrics.py` — compute delayed_recall_24h, difficulty_integrity
3. Create `delayed_recall_sample` table (V103 migration)
4. Add delayed recall sampling to post-session hook: after each session, randomly sample 3-5 items and flag them for 24h recall check
5. Create `mandarin/intelligence_audit.py` — Brier score, classification accuracy
6. Create `intelligence_audit` table
7. Add confidence + evidence fields to churn type classification output
8. **Ship. Measure for 2 weeks before changing anything else.**

### Phase 2: Doctrine Protection (Week 2-3)
**Goal:** Fix emails that violate doctrine. These are safe, reversible changes.

1. Fix win-back trigger: change day 7 to day 30 in `marketing_hooks.py`
2. Reduce churn prevention cadence: day 7, 14, 21 in email scheduler
3. Shift activation nudge cadence: day 3, 7, 14
4. Remove streak count from push notification copy
5. Reframe builder-facing language in onboarding emails 1, 3, 5
6. Redesign weekly progress email to include concrete Mandarin artifacts
7. Update `email-sequences.md` to match code changes
8. Remove discount time constraint from upgrade email #5 (or make it evergreen)

### Phase 3: Governance Gates (Week 3-4)
**Goal:** Add human review gates to the experiment daemon.

1. Create `experiment_approval_queue` table
2. Create `mandarin/experiment_governance.py` — risk-tier classification, approval enforcement
3. Modify experiment daemon: replace auto-start with proposal-to-queue
4. Modify experiment daemon: replace auto-conclude (treatment wins) with proposal-to-queue
5. Add admin API endpoints for approval queue
6. Add approval queue visibility to admin dashboard
7. Add counter-metric guardrails to experiment monitoring

### Phase 4: Safe Automation (Week 4-5)
**Goal:** With measurement and governance in place, enable safe automation.

1. Integrate counter-metrics into guardrail checks
2. Add nightly intelligence batch scheduler
3. Add intelligence self-audit monthly computation
4. Add admin CLI commands (experiment list, approve, audit)
5. Add CI/release gate checks E1-E5
6. Enable delayed recall measurement in nightly batch

### Phase 5: Continuous Improvement (Ongoing)
**Goal:** Use measurement to improve the system over time.

1. After 1 month: review intelligence audit metrics; adjust churn classification weights if calibration is poor
2. After 2 months: review experiment proposal win rate; if <30%, tighten proposal criteria
3. Quarterly: manual review of all experiment proposals and conclusions
4. Quarterly: review email doctrine compliance across all sequences
5. Consider relaxing governance gates as confidence in the system grows (but start tight)

---

## 13. Risks / Failure Modes / What Could Go Wrong

### Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Approval queue becomes a bottleneck (proposals pile up, no one reviews) | Medium | Medium — experiments don't run, no learning | Set max queue age (7 days); if unreviewd, auto-reject and log. Weekly admin nudge. |
| Delayed recall sampling changes session experience (learners notice "why am I seeing this again?") | Low | Low — items would have been scheduled for review anyway | Sample items that are *already due* for review within 24-48h, not random items |
| Counter-metrics are noisy at small sample sizes | High | Medium — false guardrail triggers | Set minimum sample size for counter-metric guardrails (n=50 per variant before enforcing) |
| Intelligence audit shows churn classification is poorly calibrated | Medium | Low — we just learn the system needs work | This is a *feature*, not a bug. The whole point of self-audit is to detect this. |

### Doctrine Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Governance gates get loosened over time ("let's just auto-approve low-risk ones") | Medium | High — gradual erosion of review discipline | Document in DOCTRINE.md that governance gate changes are blocked-tier actions |
| Email cadence reductions hurt reactivation rate | Low | Low — the current cadence is slightly aggressive; slight reduction is net positive for trust | Monitor reactivation rate as counter-metric; if it drops >20%, investigate |
| Weekly progress emails with Mandarin artifacts are less engaging than stat-based ones | Low | Low — Mandarin artifacts *are* the product; showing them should increase engagement | A/B test the new format before full rollout |

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| V103 migration fails on existing databases | Low | High — blocks deployment | Write idempotent migration with IF NOT EXISTS; test on production copy |
| Nightly intelligence batch overlaps with other schedulers | Low | Low — all schedulers use DB locks | Use existing `scheduler_lock` pattern |
| Counter-metric computation is too expensive for hourly runs | Medium | Low — counter-metrics don't need to be real-time | Compute counter-metrics in nightly batch only, not during experiment daemon ticks |

### Philosophical Risks

| Risk | Description | Mitigation |
|------|-------------|------------|
| Over-governance | Adding so many review gates that the system can't improve itself at all | Start with review gates on everything; relax specific gates as confidence grows, with explicit justification |
| Under-governance | The approval queue gets rubber-stamped without real review | Monthly audit of approval decisions; require written rationale for approvals |
| Metric worship | The self-audit framework becomes the new thing to optimize, rather than actual learning quality | The self-audit is a diagnostic tool, not a scorecard. Frame it as "how well do we understand what's happening?" not "are our numbers good?" |
| Closed-loop reasoning | The system diagnoses "boredom," intervenes for boredom, measures that the intervention "worked" (user came back), concludes that the diagnosis was correct — without checking if "boredom" was actually the right label | The intelligence audit framework explicitly measures classification accuracy against behavioral outcomes, not intervention success. A user who comes back after a "boredom" intervention might have come back anyway. |
