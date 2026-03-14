# Anchor Point Milestones

> Last updated: 2026-03-10

## Overview

The Spiral model defines three anchor points — major milestones where the project's viability, architecture, and readiness are formally assessed. Each anchor point requires specific evidence, stakeholder commitments, and success metrics before the project proceeds.

For Aelu, these anchor points map to the actual development trajectory from concept through V2 completion and toward production operation.

---

## Anchor Point 1: Life Cycle Objectives (LCO)

**Question this answers:** "Is there a viable concept worth building?"

**Status:** PASSED (January 2026)

### Entry Criteria

| Criterion | Evidence Required | Aelu Evidence |
|-----------|------------------|---------------|
| Problem identified | Documented learning problem that existing tools don't solve | Serious Mandarin learners need SRS + grammar + exposure in one system, not 4 separate apps |
| Solution concept | High-level approach described | Flask+SQLite deterministic system: 12 drill types, scaffolded progression, no LLM dependency |
| Target user | User persona with specific needs | Jason's learner profile: HSK 2 level, aiming for HSK 6, values depth over gamification |
| Technical feasibility | Proof that the approach works | Python SRS prototype with SM-2 scheduling, CLI drill loop functional |
| Risk assessment | Top 5 risks identified with mitigations | SQLite scaling, solo developer bus factor, content quality, retention, Python 3.9 EOL |

### Deliverables

- [x] Learner profile document (`learner_profile.md`)
- [x] Initial risk register (5+ risks identified)
- [x] Technology stack decision (Flask, SQLite, Litestream, Fly.io)
- [x] HSK 1-3 content scope defined (299 seed items target)
- [x] Writing standard articulated (`chinese_writing_standard.md`)

### Stakeholder Commitments at LCO

| Stakeholder | Commitment |
|-------------|-----------|
| Developer (Jason) | Commit 3+ months of development time to reach LCA |
| Learner (Jason) | Use the system daily to validate the learning model |
| Platform | Accept SQLite as production database for <100 users |

### Success Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| Concept defined | Written description | Complete |
| Technical proof of concept | Working CLI drill loop | Complete (V1) |
| Risk register initialized | 5+ risks | Complete (12 risks) |
| Stakeholder commitment | Development time committed | 3 months committed |

---

## Anchor Point 2: Life Cycle Architecture (LCA)

**Question this answers:** "Is the architecture validated and production-worthy?"

**Status:** PASSED (February 2026, V2 completion)

### Entry Criteria

| Criterion | Evidence Required | Aelu Evidence |
|-----------|------------------|---------------|
| Architecture validated | Core components working together end-to-end | Flask web UI + CLI + iOS Capacitor app all functional. 16-table schema stable. |
| Risk mitigations implemented | Top risks have working mitigations | JWT auth (S-001), Litestream backups (T-005), parameterized queries (S-004), WAL mode (T-001) |
| Content pipeline working | Content can be created and delivered | `content_gen/` pipeline producing items. 299 items, 299 context notes, 134 auto-tagged, 8 dialogues seeded. |
| Quality foundation | Testing and monitoring operational | Test suite, `crash_log` table, `drill_errors.log`, `session_trace.jsonl`, `security_audit_log` |
| Deployment pipeline | Code can be deployed to production | Fly.io deployment working. Litestream replication to S3. Health check endpoint. |

### Deliverables

- [x] 16-table SQLite schema (v13) — stable and migrated
- [x] 12 drill types — all functional with scoring
- [x] 26 grammar points, 14 language skills seeded
- [x] Web UI with Civic Sanctuary aesthetic
- [x] iOS Capacitor app — functional on simulator
- [x] macOS TTS audio integration
- [x] JWT authentication with security audit logging
- [x] GDPR data deletion and export endpoints
- [x] Litestream backup and recovery tested
- [x] 29 CLI commands operational
- [x] Volume exposure features (graded reader, media shelf, extensive listening)
- [x] Content generation pipeline (`content_gen/`)

### Stakeholder Commitments at LCA

| Stakeholder | Commitment |
|-------------|-----------|
| Developer (Jason) | Shift from building to hardening. "Stop expanding. Start hardening." |
| Learner (Jason) | Daily use to validate SRS scheduling and drill effectiveness |
| Platform | Production deployment on Fly.io with monitoring |
| Content | Maintain writing standard for all content additions |

### Success Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| Schema stability | No breaking migrations for 2 weeks | Achieved (v13 stable since Feb 11) |
| Feature completeness | All V2 features operational | 12 drill types, web+CLI+iOS, exposure features — all working |
| Test coverage | > 55% for critical paths | Met (55% floor) |
| Security audit | No Critical findings | C1-C3 fixed same-day. No open Critical. |
| Deployment | Automated deploy to Fly.io | Working |

---

## Anchor Point 3: Initial Operational Capability (IOC)

**Question this answers:** "Is this deployable and usable by real users?"

**Status:** IN PROGRESS (target: Q2 2026)

### Entry Criteria

| Criterion | Evidence Required | Aelu Status |
|-----------|------------------|-------------|
| Production stability | 30 days uptime with <2 incidents | Pending — monitoring in place, need sustained run |
| User onboarding | New user can register, learn, and return | Auth flow works. Onboarding experience needs polish. |
| Payment integration | Users can subscribe and pay | Stripe integration built. Webhook handling tested. Annual pricing pending (F-007). |
| Content sufficiency | Enough content for 30 days of learning | 299 items + 8 dialogues. Sufficient for HSK 1-3 coverage. Graded reader content thin. |
| Monitoring completeness | All failure modes detectable | Health check, crash_log, security_audit_log operational. Alert routing needs work (O-005). |
| Security hardened | Penetration test passed | Self-administered pen test needed. Dependency audit (D-004) pending. |
| Compliance verified | GDPR endpoints tested end-to-end | Endpoints built. End-to-end test with real data deletion pending. |
| Performance validated | Acceptable response times under expected load | Load test (D-005) pending. |

### Deliverables (remaining)

- [ ] 30 days continuous uptime demonstrated
- [ ] Beta user onboarding (F-006: PMF validation — onboard 10 beta users)
- [ ] Annual pricing tier live (F-007)
- [ ] Penetration test completed and findings resolved
- [ ] Load test completed (D-005) — SQLite viability confirmed at target scale
- [ ] GDPR end-to-end test with real deletion
- [ ] Alert routing for all Expedite scenarios
- [ ] App Store submission (iOS)
- [ ] Landing page and marketing site

### Stakeholder Commitments at IOC

| Stakeholder | Commitment |
|-------------|-----------|
| Developer (Jason) | Maintain production operation. Respond to Expedite items within SLA. |
| Learner (beta users) | Provide feedback on learning effectiveness. Use system for 30+ days. |
| Platform | 99.5% uptime target. Automated backup verification. |
| Content | Review and maintain quality standard. Expand to HSK 4 only after HSK 1-3 validated. |

### Success Metrics

| Metric | Target | Status |
|--------|--------|--------|
| Uptime | 99.5% over 30 days | Pending |
| Beta user retention | 5 of 10 users active after 30 days | Not started |
| Payment success rate | >95% of attempted subscriptions succeed | Pending |
| P95 response time | <500ms for API endpoints | Pending (D-005) |
| Security findings | 0 Critical, 0 High | Pending pen test |
| GDPR compliance | Deletion completes in <24 hours | Pending test |

---

## Post-IOC: Full Operational Capability (FOC)

Not formally an anchor point, but the natural next milestone:

- HSK 4-6 content expansion
- Classroom/LTI adoption by institutions
- Multi-region deployment if user base warrants it
- Advanced analytics and learner dashboards
- Community features (if validated by user demand)

---

## Relationship to Other Artifacts

- **LCM Commitment Reviews** (`lcm-commitment-reviews.md`): Formal review process at each anchor point.
- **Win Conditions** (`win-conditions.md`): Each anchor point advances win conditions for all stakeholders.
- **Risk Register** (`risk-register.md`): Anchor point evidence includes risk mitigation proof.
- **Spiral Cycle Template** (`spiral-cycle-template.md`): Cycles advance toward the next anchor point.
