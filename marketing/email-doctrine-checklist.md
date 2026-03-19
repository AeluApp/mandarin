# Email Doctrine Test Suite

Every email must pass ALL of the following before shipping. Any single failure blocks the email.

**Anchor documents:** DOCTRINE.md §6 (Habit Design), BRAND.md (Voice), marketing/churn-prevention.md

---

## Pressure & Manipulation

| # | Question | Pass Criterion |
|---|----------|---------------|
| P1 | Does this email induce guilt about not studying? | No guilt language, no "we miss you," no "you're falling behind" |
| P2 | Does this email create artificial urgency? | No countdown timers, no expiring offers < 30 days, no "last chance" |
| P3 | Does this email use loss framing? | No "you'll lose your streak/progress/data" unless factually true AND actionable |
| P4 | Does this email pressure the learner emotionally? | No sad faces, no emotional manipulation, no manufactured FOMO |
| P5 | Does this email disguise marketing as content? | Marketing emails must be honest about their purpose; tips emails must contain genuine tips |

## Tone & Voice

| # | Question | Pass Criterion |
|---|----------|---------------|
| T1 | Does this sound like a humane guide or like SaaS automation? | First-person singular, calm, specific, no "we're excited to announce" |
| T2 | Does this respect the learner's intelligence? | No oversimplification, no condescension, no "Great job!" |
| T3 | Does this use builder-facing framing? | No "44 drill types" — describe what the learner experiences, not what the system does |
| T4 | Would this still feel respectful to an exhausted learner? | Read it imagining the recipient is overwhelmed, behind, and slightly ashamed |
| T5 | Does this use BRAND.md voice? | Calm adult. Data-grounded. No praise inflation. Forward-directed. |

## Re-Entry & Dignity

| # | Question | Pass Criterion |
|---|----------|---------------|
| R1 | Does this help re-entry feel safe? | Returning learner should feel welcomed, not evaluated |
| R2 | Does this acknowledge that gaps are normal? | Explicitly or implicitly frames breaks as ordinary, not failures |
| R3 | Does this offer genuine options? | Resume, pause, and cancel presented as equally valid choices |
| R4 | Does this avoid counting the learner's absence? | No "It's been X days since..." unless paired with constructive context |

## Progress & Truthfulness

| # | Question | Pass Criterion |
|---|----------|---------------|
| Q1 | Does this exaggerate progress? | All claims must be traceable to real data; no rounding up, no "almost there" without evidence |
| Q2 | Does this include concrete Mandarin? | Progress emails must reference specific characters, words, or skills — not just numbers |
| Q3 | Does this honestly represent the learner's state? | If accuracy is flat or declining, acknowledge it without euphemism |

## Cadence & Consent

| # | Question | Pass Criterion |
|---|----------|---------------|
| C1 | Is this email part of a sequence that's too dense? | No more than 1 email per 5 days during churn prevention; no more than 1 per 2 days during onboarding |
| C2 | Does the learner have a clear, one-click way to stop? | Every email includes unsubscribe; sequence emails include "stop sending these" option |
| C3 | Has this sequence been reviewed for cumulative pressure? | Read the entire sequence as a unit, not just individual emails |

---

## How to Use This Checklist

1. **Before writing:** Review the checklist to internalize constraints.
2. **After drafting:** Walk through every criterion. Mark pass/fail.
3. **Any failure blocks shipping.** Fix the failure, then re-check.
4. **For sequences:** Check individual emails AND the sequence as a whole (C3).
5. **For progress emails:** Q2 is mandatory — abstract stats alone do not pass.
6. **Code review:** Any PR that changes email content or cadence must reference this checklist.

## Automated Enforcement

The following criteria can be partially enforced in `tests/test_email_contract.py`:
- C2: Every HTML template must contain an unsubscribe link
- P2: No template may contain countdown timer markup
- T3: Flag known builder-facing terms ("drill types", "SRS algorithm", "spaced repetition system") in learner-facing copy

The following are enforced in `scripts/audit_check.py`:
- E1: Email template changes require doctrine checklist reference
- E4: This file must exist and be non-empty
