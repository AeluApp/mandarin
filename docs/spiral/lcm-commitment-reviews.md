# Life Cycle Model Commitment Reviews

> Last updated: 2026-03-10

## Purpose

A commitment review is the formal gate at each anchor point (LCO, LCA, IOC). It asks: "Do we have sufficient evidence to proceed, and are all stakeholders willing to commit to the next phase?" The review is not a rubber stamp — it requires concrete evidence and explicit go/no-go decisions.

---

## Review Structure

Each commitment review follows the same structure regardless of anchor point:

```
1. Present evidence against entry criteria
2. Review risk status (new, mitigated, retired, escalated)
3. Assess stakeholder win conditions
4. Make go/no-go decision
5. Document commitments for next phase
```

**Duration:** 1-2 hours of focused self-review (solo founder context).

**Output:** Written review record appended to this document.

---

## Review Criteria by Anchor Point

### LCO Review — "Should we build this?"

| Criterion | Evidence Required | Pass Threshold |
|-----------|------------------|---------------|
| Problem-solution fit | Written problem statement + proposed solution | Problem is real (not imagined), solution is technically feasible |
| Target user identified | User persona with specific learning goals | At least one real person (Jason) matches the persona |
| Technical feasibility | Proof of concept or prior art | Core algorithm (SRS) demonstrated in prototype |
| Top risks identified | Risk register with 5+ entries | No showstopper risks (score 20+) without mitigation |
| Resource commitment | Time and budget available | 3+ months of development time allocated |
| Competitive analysis | Awareness of alternatives | Know what Duolingo/HelloChinese/Pleco/Anki do and don't do |

**If review fails:** Pivot the concept or shelve the project. Do not proceed to building without a clear problem-solution fit.

---

### LCA Review — "Is the architecture sound?"

| Criterion | Evidence Required | Pass Threshold |
|-----------|------------------|---------------|
| End-to-end functionality | Working system (not just components) | User can log in, complete a drill session, see progress — across web, CLI, and iOS |
| Schema stability | No breaking migrations recently | 2+ weeks without schema changes |
| Security baseline | Critical security risks mitigated | 0 Critical findings in security scan. Auth bypass scenarios tested and blocked. |
| Content pipeline | Content creation is repeatable | At least 100 items seeded via pipeline (not manually) |
| Deployment proven | Production deploy works | Fly.io deployment succeeds. Litestream replication verified. Health check passes. |
| Quality infrastructure | Tests and monitoring exist | Test suite runs. `crash_log`, `drill_errors.log`, `security_audit_log` operational. |
| Risk reduction | Top 5 risks have working mitigations | Each top risk has at least one mitigation implemented (not just planned) |

**If review fails:** Identify the gap. Options: (1) Fix the gap and re-review in 1-2 weeks. (2) Accept the gap as a known risk and document why proceeding is justified. (3) Revert to LCO — the architecture needs rethinking.

---

### IOC Review — "Is this ready for real users?"

| Criterion | Evidence Required | Pass Threshold |
|-----------|------------------|---------------|
| Production stability | Uptime data | 99.5% over 30 consecutive days |
| User onboarding | End-to-end user journey tested | New user can register, complete first session, return next day — on all platforms |
| Payment flow | Subscription lifecycle tested | Successful payment, access granted, renewal, cancellation, webhook handling |
| Security hardened | Penetration test results | 0 Critical, 0 High findings. All Medium findings have mitigations. |
| Performance validated | Load test results | P95 response time <500ms at target concurrency (100 users for D-005) |
| Compliance verified | GDPR end-to-end test | Data deletion request processed within 24 hours. Data export produces complete file. |
| Content sufficiency | Learning path assessment | 30 days of content available for HSK 1-3 learner without repetition |
| Monitoring complete | All Expedite scenarios detectable | Each Expedite trigger (see `classes-of-service.md`) has a corresponding alert |
| Documentation complete | Runbook and operations docs | Deployment, backup, restore, and incident response documented |

**If review fails:** Do not launch to users. Identify gaps. Create Kanban cards for each gap. Re-review when gaps are closed. There is no "soft launch" — either the IOC criteria are met or they aren't.

---

## Evidence Documentation

For each criterion, evidence must be concrete and verifiable. Not "we think this works" — "here is proof it works."

### Evidence Types

| Type | Description | Aelu Example |
|------|-------------|-------------|
| **Working software** | Feature demonstrated end-to-end | Screenshot of completed drill session on iOS simulator |
| **Test results** | Automated or manual test pass | `pytest` output showing 55%+ coverage on critical paths |
| **Monitoring data** | Production metrics over time | Fly.io uptime dashboard showing 30 days at 99.5%+ |
| **Security scan** | Tool output showing findings | `bandit` report with 0 High/Critical. `pip-audit` clean. |
| **Load test** | Performance under simulated load | `locust` report showing P95 <500ms at 100 concurrent users |
| **Compliance test** | Regulatory requirement verified | GDPR deletion request processed, verified data removed from all 16 tables |
| **Risk assessment** | Updated risk register | Risk register showing mitigations implemented for top risks |

### Evidence Checklist Template

```
Anchor Point: [LCO / LCA / IOC]
Review Date:  YYYY-MM-DD
Reviewer:     Jason

Criteria Evidence:
□ [Criterion 1]: [evidence location/description]
□ [Criterion 2]: [evidence location/description]
...

Risks Reviewed:
□ New risks identified: [list]
□ Risks mitigated since last review: [list]
□ Risks escalated: [list]

Stakeholder Win Conditions:
□ Learner: [status]
□ Developer: [status]
□ Platform: [status]
□ Content: [status]

Decision: [GO / NO-GO / CONDITIONAL GO]
Conditions (if conditional): [list]
Commitments for next phase: [list]
```

---

## Stakeholder Sign-Off Process

In a solo founder context, "stakeholder sign-off" is structured self-review from each perspective. The discipline is in actually wearing each hat and being honest about whether the criteria are met.

### Sign-Off Hats

| Hat | Question to Answer | Sign-Off Means |
|-----|-------------------|---------------|
| **Learner** | "Would I trust this system with my learning progress?" | The SRS scheduling is reliable. Drill quality is high. Data won't be lost. |
| **Developer** | "Can I maintain and operate this system sustainably?" | The codebase is understandable. Deployment is automated. Monitoring catches problems. |
| **Platform** | "Is this system reliable and secure enough to serve real users?" | Uptime meets targets. Security is hardened. Backups are verified. |
| **Content** | "Does the content meet the quality standard?" | Writing follows the standard. Content is accurate. Progression is pedagogically sound. |

Each hat can give one of three responses:
- **Approve:** Criteria fully met.
- **Approve with conditions:** Criteria mostly met, specific gaps identified with a timeline.
- **Block:** Criteria not met. Must be resolved before proceeding.

One block from any hat stops the review.

---

## Go/No-Go Decision Framework

| Signal | Decision | Action |
|--------|----------|--------|
| All criteria met, all hats approve | **Go** | Proceed to next phase. Document commitments. |
| Most criteria met, minor gaps with clear timeline | **Conditional Go** | Proceed with conditions. Create Kanban cards for each condition. Re-verify conditions within 2 weeks. |
| Critical criteria unmet, or any hat blocks | **No-Go** | Do not proceed. Identify gaps. Create action plan. Schedule re-review in 1-4 weeks. |
| Fundamental concerns about viability | **Abort/Pivot** | Re-evaluate whether the project should continue in its current form. Return to LCO. |

---

## Commitment Escalation for Failed Reviews

When a review results in No-Go:

1. **Day 1:** Document the specific criteria that failed and why.
2. **Day 2-3:** Create a remediation plan. Each failed criterion gets a Kanban card with a target date.
3. **Week 1-2:** Execute remediation. Focus on failed criteria only — no new features.
4. **Re-review:** Schedule within 2-4 weeks. Only review the previously failed criteria (passed criteria don't need re-review unless something changed).

If a review fails twice:
- Reassess whether the criteria are realistic or whether the project needs a fundamental change.
- Consider: is this an architecture problem (back to LCO) or an execution problem (more time)?

If a review fails three times:
- The project should not proceed without a significant change in approach, scope, or resources.

---

## Review Records

### LCO Review Record

```
Anchor Point: LCO
Review Date:  2026-01-15
Reviewer:     Jason

Evidence:
[x] Problem statement: Serious Mandarin learners lack integrated SRS+grammar+exposure
[x] Solution concept: Flask+SQLite, 12 drill types, deterministic (0 LLM tokens)
[x] Target user: Jason — HSK 2, targeting HSK 6
[x] Technical feasibility: SM-2 prototype working in CLI
[x] Top 5 risks: T-001 (SQLite), O-001 (bus factor), M-002 (retention),
    T-002 (Python 3.9), M-001 (competition)
[x] Competitive analysis: Duolingo (gamified, shallow), HelloChinese
    (Mandarin-specific but limited SRS), Pleco (dictionary, no SRS),
    Anki (SRS only, no curriculum)

Decision: GO
Commitments: 3 months development. Daily dogfooding. SQLite accepted for <100 users.
```

### LCA Review Record

```
Anchor Point: LCA
Review Date:  2026-02-11
Reviewer:     Jason

Evidence:
[x] End-to-end: Web UI, CLI, iOS app all functional
[x] Schema: v13, stable for 2+ weeks
[x] Security: C1-C3 auth bypass fixed same-day. bandit clean.
[x] Content: 299 items via pipeline, 299 context notes, 134 auto-tagged
[x] Deployment: Fly.io deployment working, Litestream verified
[x] Quality: Test suite, crash_log, drill_errors.log, security_audit_log
[x] Risk reduction: JWT auth, Litestream, parameterized queries, WAL mode

Decision: GO
Commitments: "Stop expanding. Start hardening." Daily use. Production monitoring.
```

### IOC Review Record

```
Anchor Point: IOC
Review Date:  [PENDING — target Q2 2026]
Reviewer:     Jason

Evidence:
[ ] Production stability: [pending 30-day run]
[ ] User onboarding: [pending polish]
[ ] Payment flow: [pending F-007 annual pricing]
[ ] Security: [pending pen test]
[ ] Performance: [pending D-005 load test]
[ ] Compliance: [pending GDPR end-to-end test]
[ ] Content: [pending graded reader expansion]
[ ] Monitoring: [pending alert routing]
[ ] Documentation: [pending runbook completion]

Decision: [PENDING]
```

---

## Relationship to Other Artifacts

- **Anchor Points** (`anchor-points.md`): Defines the criteria that this review process evaluates.
- **Win Conditions** (`win-conditions.md`): Stakeholder sign-off is grounded in win conditions.
- **Risk Register** (`risk-register.md`): Risk status is reviewed at every commitment review.
- **Kanban Board** (`../kanban/board.md`): Failed review criteria generate Kanban cards.
