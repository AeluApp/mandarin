# Project Charter — Aelu Mandarin Learning System

**Project Name:** Aelu
**Owner:** Jason Gerson (Founder, Sole Developer)
**Created:** 2026-03-10
**Charter Version:** 1.0

---

## 1. Problem Statement

Adult Mandarin learners lack a system that closes the loop between passive exposure and active recall. Existing tools fall into two camps:

1. **Flashcard apps** (Anki, Pleco) — strong on spaced repetition but weak on drill diversity, error classification, and adaptive session planning. Users must build their own decks and have no visibility into error patterns.

2. **Gamified apps** (Duolingo, HelloChinese) — strong on engagement but weak on diagnostic rigor. Sessions are difficulty-flat, errors are counted but not classified, and the system cannot distinguish a tone error from a grammar error from a vocabulary gap.

Neither category offers:
- Deterministic, classified error tracking (tone vs. segment vs. measure word vs. register)
- Error-focused re-drilling (the system automatically builds sessions around your weakest patterns)
- 27+ drill types that exercise different cognitive pathways (recognition, production, listening, speaking, pragmatic judgment)
- Adaptive session planning based on gap analysis, time-of-day patterns, and interleaving research
- HSK 1-9 curriculum alignment with grammar point and skill provenance

The result: adult learners plateau at intermediate levels, churn within 30 days, and never develop the active production skills needed for real-world Mandarin use.

---

## 2. Business Case

| Metric | Value |
|--------|-------|
| Subscription price | $14.99/month |
| Target users (12-month) | 1,000 paying subscribers |
| Target ARR | $179,880 |
| Gross margin target | > 85% (infrastructure < $300/month at scale) |
| Current infrastructure cost | ~$7/month (Fly.io shared-cpu-1x + S3 replication) |
| Breakeven point | ~2 paying users (covers infrastructure) |
| AI token cost at runtime | $0 (fully deterministic grading engine) |

### Competitive Advantage
- **Zero AI token cost** — grading is deterministic string matching + rule-based classification. Every correct/incorrect decision is reproducible (Gage R&R = 0%). This means unit economics improve as users scale, unlike AI-powered competitors whose COGS scale linearly.
- **Deep error taxonomy** — 15 error types (tone, segment, ime_confusable, grammar, vocab, register_mismatch, particle_misuse, function_word_omission, temporal_sequencing, measure_word, politeness_softening, reference_tracking, pragmatics_mismatch, number, other) enable targeted re-drilling that generic apps cannot do.
- **Solo-founder operational simplicity** — SQLite + Litestream eliminates database ops overhead. No Postgres, no Redis, no message queues.

---

## 3. Scope

### In Scope
- **Curriculum:** HSK levels 1-9 (Chinese Ministry of Education 3.0 standard)
- **Platforms:** Web (Flask, all browsers), iOS (Capacitor shell), CLI (typer)
- **Drill types:** 27 drill types across reading, listening, speaking, IME, production, and advanced categories
- **Scheduling:** FSRS-based spaced repetition with gap-aware adaptive session planning
- **Error tracking:** Classified error logging, error focus system, Pareto analysis
- **Exposure features:** Graded reader, media shelf, extensive listening, vocab encounter log
- **Assessment:** Placement test, diagnostic sessions, HSK projection forecasting
- **Commerce:** Stripe subscriptions ($14.99/month), invite codes, affiliate system, discount codes
- **Classroom:** Teacher dashboards, student enrollment, LTI 1.3 integration
- **Security:** JWT auth, MFA (TOTP), rate limiting, GDPR data deletion, security audit log
- **Ops:** Crash logging, client error reporting, data retention policies, churn detection
- **Self-improvement:** System self-diagnosis and parameter adjustment proposals

### Out of Scope
- Real-time AI-powered conversation practice
- Native mobile app rewrite (Flutter prototype exists but is not production)
- Speech recognition / pronunciation scoring (parselmouth deferred — build fails on Python 3.9)
- Video content hosting (media recommendations link to external platforms)
- Marketplace / user-generated content
- Multi-language support (Mandarin only)

---

## 4. Team

| Role | Person | Allocation |
|------|--------|-----------|
| Founder / Product / Engineering / Design / Marketing / Ops | Jason Gerson | 100% |

This is a solo-founder operation. There is no team to delegate to. Every decision — product, engineering, design, marketing, operations, support — is made by one person. This is both the constraint and the advantage: zero coordination overhead, instant decision-making, but also zero redundancy and single-point-of-failure risk on the bus factor.

---

## 5. Timeline

| Milestone | Date | Status |
|-----------|------|--------|
| V1: Core SRS + drill engine + CLI | 2025 | Complete |
| V1 R2: Error classification, diagnostics, forecasting | 2025 | Complete |
| V2: Web UI, audio, tone grading, context notes, speaking drills | 2026-02-11 | Complete |
| V2+: Volume exposure (reader, media, listening, encounters) | 2026-02-17 | Complete |
| Cloud deploy: Fly.io, Litestream, Stripe, auth, security | 2026-03 | In progress |
| V3: Content expansion (HSK 4-9 full seed), advanced drills | 2026 Q2 | Planned |
| PMF validation: First 10 paying users | 2026 Q2-Q3 | Planned |
| Growth: 100 paying users | 2026 Q4 | Planned |
| Scale: 1,000 paying users | 2027 | Planned |

---

## 6. Expected Impact

### Retention
- **Industry benchmark:** ~20% 30-day retention for language learning apps (Duolingo ~25% for active learners, most others < 15%)
- **Aelu target:** 60% 30-day retention
- **Mechanism:** Error-focused sessions mean every session addresses the learner's actual weakest points. No wasted drills on already-mastered material. This should reduce the "I'm not making progress" churn trigger.

### Learning Outcomes
- **Target:** Measurable HSK level progression of 0.5 levels per 3 months for learners studying 4 sessions/week
- **Measurement:** Pre/post accuracy on level-appropriate content, mastery stage distribution progression
- **Differentiation:** Unlike self-reported progress in most apps, Aelu tracks per-item, per-modality, per-error-type accuracy with full audit trail

### Operational
- **Target:** < 1 crash per 1,000 sessions (crash_log monitoring)
- **Target:** < 500ms p95 API latency
- **Target:** 100% grading reproducibility (deterministic engine)
- **Target:** < 2 hours/week on operations and support (solo founder constraint)

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| SQLite single-writer becomes bottleneck | Low (< 1,000 users) | High | WAL mode handles concurrent reads; monitor write latency; plan Turso migration at 5,000+ users |
| Solo founder burnout / bus factor | Medium | Critical | Automate everything possible; minimize operational toil; no features without PMF evidence |
| Content quality insufficient for HSK 4-9 | Medium | High | Invest in content generation pipeline; consider paid content partnerships |
| Price too high for market | Medium | Medium | VoC interviews to validate; A/B test pricing; offer annual discount |
| Classroom/LTI features built without teacher users | Already happened | Low (sunk cost) | Stop investing until first teacher prospect; treat as overproduction waste |
| iOS Capacitor shell breaks on OS update | Low | Medium | Minimal native code; test on each iOS release |

---

## 8. Success Criteria

| Criterion | Metric | Target | Measurement |
|-----------|--------|--------|-------------|
| Product-market fit | 30-day retention | >= 60% | `session_log` analysis: % of users with session in days 25-35 after first session |
| Revenue | MRR | $1,000 within 6 months of launch | Stripe dashboard |
| Quality | Grading accuracy | 100% reproducible | Automated test suite (currently ~1,300 tests) |
| Operational health | Crash rate | < 1 per 1,000 sessions | `crash_log` table |
| User satisfaction | NPS | >= 40 | `user_feedback` table |
| Learning efficacy | Mastery progression | 0.5 HSK levels per quarter | `progress.mastery_stage` distribution analysis |

---

## 9. Stakeholder Sign-off

| Stakeholder | Role | Sign-off |
|-------------|------|---------|
| Jason Gerson | Everything | Approved (sole decision-maker) |

---

## 10. Governing Principles

1. **Stop expanding. Start hardening.** — No new features without evidence of user need (VoC) or measured quality gap.
2. **Zero AI tokens at runtime.** — Grading must be deterministic. This is a competitive advantage, not a limitation.
3. **Every metric defensible.** — If you can't explain how a number was computed from raw data, don't show it.
4. **Bugs from real usage are top priority.** — Production errors trump roadmap items.
5. **No praise inflation.** — The system tells learners the truth about their progress. Calm adult tone, data-grounded feedback.
