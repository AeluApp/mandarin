# Aelu Product Owner Decision Log

**Product Owner:** Jason Gerson
**Last Updated:** 2026-03-10

This log documents significant product decisions made in the PO role. Each entry records the decision, the reasoning, what alternatives were considered, and whether the decision was evidence-based or intuition-based. Honesty about the basis matters more than appearing rigorous.

---

## Decision 001: SQLite Over PostgreSQL
**Date:** 2025 (initial architecture)
**Decision:** Use SQLite as the sole database, even for production on Fly.io.
**Rationale:** SQLite eliminates an entire infrastructure layer (no managed DB service, no connection pooling, no separate backups process). For a solo developer, fewer moving parts means fewer 3am incidents. The app is inherently single-writer (one user per session), so SQLite's write lock is not a bottleneck. WAL mode handles concurrent reads.
**Evidence basis:** Intuition + technical knowledge. No user-facing data drove this. Influenced by Litestream/LiteFS adoption in the Fly.io ecosystem and the "SQLite is not a toy database" discourse.
**Alternatives considered:** PostgreSQL on Fly.io (Supabase, Neon, or self-hosted). Rejected because it adds operational complexity disproportionate to the scale. If Aelu reaches 10,000+ concurrent users, this decision should be revisited.
**Outcome:** Schema is at v41 with 51 tables. No scaling issues encountered. Backups are simple (file copy). The decision has held up well for the current scale.

---

## Decision 002: Zero AI Tokens at Runtime
**Date:** 2025 (core philosophy)
**Decision:** No LLM API calls during study sessions. All grading, scheduling, and content selection is deterministic.
**Rationale:** Latency, cost, and reliability. A learner should not wait 2 seconds for GPT to grade a pinyin answer when a deterministic function can do it in 2ms. Runtime AI costs scale linearly with users and are unpredictable. Deterministic grading is testable — 1343 tests verify behavior, which would be impossible with stochastic LLM output.
**Evidence basis:** Technical conviction, reinforced by experience with LLM latency in other projects. No A/B test was run comparing AI-graded vs deterministic-graded sessions.
**Alternatives considered:** Using Claude/GPT for open-ended grading (e.g., grading free-form sentence production). Deferred, not rejected — if speaking drills require nuanced grading beyond tone detection, AI grading may be reconsidered for specific drill types only.
**Outcome:** The system is fast, cheap to run, and fully testable. The tradeoff is that some drill types (free conversation, essay grading) are harder to implement without AI.

---

## Decision 003: Pricing at $14.99/month
**Date:** 2026
**Decision:** Single pricing tier at $14.99/month. No freemium, no annual discount (initially).
**Rationale:** $14.99 is positioned between Duolingo Super ($12.99) and premium tutoring apps ($20+). It signals that Aelu is a serious tool, not a gamified toy. A single tier simplifies the billing code, the marketing message, and the decision for the user.
**Evidence basis:** Intuition + competitive analysis. No price sensitivity testing was conducted. The price was set by surveying 5 language learning apps and choosing the midpoint of the "serious learner" segment.
**Alternatives considered:** (a) Freemium with paid unlock — rejected because free tiers attract users who never convert and inflate support burden. (b) $9.99 — rejected because it undervalues the product. (c) $19.99 — rejected because the brand isn't established enough to command premium pricing. (d) Annual discount — deferred until monthly churn data establishes a baseline.
**Outcome:** Not yet validated. Need conversion data from real non-Jason users to know whether $14.99 is a barrier.

---

## Decision 004: Built Classroom Management Features
**Date:** 2026-02 (Phase B2)
**Decision:** Build classroom/teacher features (LTI integration, classroom table, student management) before validating individual learner PMF.
**Rationale:** B2B/B2I (business-to-institution) revenue is stickier than B2C. A single school adoption could mean 30-200 paying seats. LTI compatibility makes integration with existing LMS platforms (Canvas, Moodle) low-friction.
**Evidence basis:** Intuition + industry pattern. No teacher or school has requested this. The decision was forward-looking, building the infrastructure before having the demand.
**Alternatives considered:** (a) Focus exclusively on individual learners until PMF is validated. This was the more conservative choice and arguably the correct one. (b) Build a teacher-specific product. Rejected as too much scope.
**Outcome:** The classroom infrastructure exists (classroom table, classroom_routes.py, lti_routes.py, 37+ classroom tests, 35+ LTI tests). No schools are using it yet. This was likely premature — the code works but represents investment in a channel that hasn't been validated. Honest assessment: this should have waited.

---

## Decision 005: Built Affiliate System Before Having Users
**Date:** 2026 (Phase B2)
**Decision:** Build a full affiliate tracking system (affiliate_partner, referral_tracking, affiliate_commission tables) before having paying users.
**Rationale:** Affiliate/referral programs are a common growth channel for edtech. Having the infrastructure ready means partnerships can be activated quickly when demand exists.
**Evidence basis:** Intuition. No affiliate partner has been recruited. No data supports the assumption that affiliates will drive meaningful traffic.
**Alternatives considered:** (a) Manual affiliate tracking via spreadsheet. This would have been sufficient until there were actual affiliates. (b) Using a third-party affiliate platform (PartnerStack, Rewardful). Rejected because adding another SaaS dependency felt unnecessary.
**Outcome:** Three tables and associated routes exist. Zero affiliate partners. This was premature infrastructure. The code is clean and tested but the opportunity cost was 2-3 days that could have gone toward user acquisition.

---

## Decision 006: Deferred Social Features
**Date:** 2026 (ongoing)
**Decision:** No social features (leaderboards, friend lists, study groups, chat) in the current roadmap.
**Rationale:** Social features are high-maintenance, introduce moderation burden, and don't align with Aelu's "calm sanctuary" aesthetic. Duolingo's leaderboards drive engagement but also drive anxiety — the opposite of what Aelu aims for. The product philosophy is "quiet competence," not "competitive gamification."
**Evidence basis:** Philosophy-driven. No user has requested social features (because there are few users). The decision is consistent with the brand but hasn't been validated against actual user needs.
**Alternatives considered:** (a) Study buddies / accountability partners — the least invasive social feature. Still deferred but could be reconsidered if retention data shows isolated learners churning. (b) Community forum. Rejected because moderation is a full-time job.
**Outcome:** Correct for now. Revisit when there are 100+ active users and retention data shows whether social features would help.

---

## Decision 007: Civic Sanctuary Aesthetic
**Date:** 2026
**Decision:** Adopt a warm, library-like visual aesthetic (warm stone, teal, terracotta, serif headings) instead of the bright/gamified look common in language apps.
**Rationale:** Differentiation. Every language app looks like a game (bright colors, mascots, animations). Aelu's target audience is adults who want to be treated like adults. The aesthetic says "this is a place for serious study, not a children's game."
**Evidence basis:** Intuition + aesthetic conviction. One user described it as "calmer than Duolingo" which is directionally validating. No formal preference testing was done.
**Alternatives considered:** (a) Standard SaaS look (white, blue, clean). Rejected as generic. (b) Gamified look with mascot. Rejected as antithetical to the brand.
**Outcome:** The aesthetic is fully implemented in CSS. Dark mode works. The look is distinctive. Whether it attracts or repels the target audience remains unknown.

---

## Decision 008: 27 Drill Types
**Date:** 2025-2026 (accumulated)
**Decision:** Build 27 distinct drill types covering tone, pinyin, character recognition, production, listening, speaking, grammar, and advanced skills.
**Rationale:** Mandarin has more dimensions than most languages (tones, characters, pinyin, measure words, grammar patterns). A small number of drill types would leave gaps. Each drill type targets a specific skill, and the scheduler interleaves them for balanced practice.
**Evidence basis:** Pedagogical reasoning + personal learning experience. No comparative study was done against apps with fewer drill types. The risk is overwhelming new users with variety.
**Alternatives considered:** (a) Start with 5 core drill types and add more later. This would have been simpler but less pedagogically complete. (b) Let users choose which drill types to practice. Partially implemented via personalization module but the system still controls the mix.
**Outcome:** 27 types work for Jason. Whether they work for beginners who don't yet understand why tone drills matter is unvalidated.

---

## Decision 009: HSK 1-9 Scope from Day One
**Date:** 2025-2026
**Decision:** Seed content for all HSK levels (1-9) rather than focusing exclusively on HSK 1-3 and expanding later.
**Rationale:** HSK 7-9 content differentiates Aelu from competitors (most stop at HSK 4-6). Advanced learners have fewer options and may be willing to pay more. Having the content in the database means it's available when users reach those levels.
**Evidence basis:** Competitive gap analysis (informal — browsed competitors' feature pages). The content was generated with Claude (at build time, not runtime), so the marginal cost was time, not money.
**Alternatives considered:** (a) HSK 1-3 only, expand based on demand. More focused, lower risk of wasted content generation time. (b) HSK 1-6 (the old HSK standard). A reasonable middle ground.
**Outcome:** 10,000+ items exist across HSK 1-9. No users are currently studying above HSK 3 (because the only active user is Jason). The advanced content may never be used if the product fails to retain beginners long enough for them to advance.

---

## Decision 010: Capacitor for Mobile (Not React Native / Flutter Native)
**Date:** 2026-02
**Decision:** Use Capacitor to wrap the Flask web app as a mobile app, rather than building a native app or using React Native.
**Rationale:** Aelu is a web app first. Capacitor lets the same Flask templates serve both web and mobile, with native plugins (haptics, push notifications, status bar) bridged via JavaScript. This means one codebase, not two. For a solo developer, maintaining separate web and native codebases is unsustainable.
**Evidence basis:** Technical pragmatism. The alternative (Flutter) was explored — a flutter_app directory exists — but maintaining feature parity across Flask web and Flutter native was too much work for one person.
**Alternatives considered:** (a) Flutter (started, abandoned — directory still exists). (b) React Native. Rejected because the web app is Flask/Jinja, not React. (c) PWA only (no native wrapper). Considered but App Store presence matters for discovery and credibility.
**Outcome:** Capacitor shell is built, JWT auth works, offline sync works. Not yet submitted to App Store. The approach is sound for the current scale.

---

## Decision 011: No Freemium Tier
**Date:** 2026
**Decision:** Do not offer a free tier. Users either pay or they don't use the product.
**Rationale:** Free tiers attract users who will never pay and inflate vanity metrics (signups, MAU) without contributing revenue. For a solo developer, every free user is a support burden without upside. The product should be good enough that $14.99 feels obviously worth it.
**Evidence basis:** Conviction, not data. This is a bet that Aelu's target audience (motivated adult learners) will pay for a good tool without needing to be "freemiumed" into it. The bet is unvalidated.
**Alternatives considered:** (a) 7-day free trial. This is the most likely change if conversion data shows the paywall is too aggressive. (b) Free tier with 1 session/day. Rejected because a limited free experience might give a worse impression than no free experience.
**Outcome:** Unknown. Need real conversion data. If fewer than 5% of landing page visitors sign up, a free trial should be tested.

---

## Decision 012: Invest in Observability Infrastructure Early
**Date:** 2025-2026
**Decision:** Build extensive observability: crash_log, client_error_log, client_event, security_audit_log, session_metrics, telemetry, improvement_log — before having significant user traffic.
**Rationale:** When problems happen in production, the worst situation is having no data. Observability infrastructure is cheap to build, expensive to retrofit, and invaluable when debugging a production issue at 11pm.
**Evidence basis:** Engineering experience. Every production incident Jason has encountered in his career was made worse by insufficient logging.
**Alternatives considered:** (a) Use a third-party observability platform (Sentry, Datadog). Considered but adds cost ($29+/month) and a dependency. The custom tables are sufficient for current scale. (b) Add logging only when problems arise. Rejected — by then it's too late.
**Outcome:** Good decision. The observability tables have already caught issues during development (drill errors, schema migration problems). The crash_log monitoring is part of the Definition of Done.
