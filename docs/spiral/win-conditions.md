# Win-Win Conditions

> Last updated: 2026-03-10

## Purpose

Every project has multiple stakeholders, and each has different success criteria. The Spiral model's Theory W (Win-Win) requires that all stakeholders' conditions are met — or that conscious trade-offs are negotiated. A project where one stakeholder "wins" at another's expense is unstable.

This document defines what "winning" looks like for each Aelu stakeholder, how to measure it, and how to resolve conflicts when win conditions collide.

---

## Stakeholder: Learner

**Who:** Anyone using Aelu to learn Mandarin. Currently Jason (dogfooding). Future: beta users, paying subscribers, classroom students.

### Win Conditions

| Condition | Definition | Measurement |
|-----------|-----------|-------------|
| Effective acquisition | Measurable improvement in Mandarin reading, listening, and speaking | SRS retention rate >85% at 30-day intervals. HSK level progression (validated by practice tests). |
| Efficient time use | Every minute of study produces meaningful learning | Session completion rate >80%. No "filler" drills. Interleaving enforcement prevents easy-item bias. |
| Appropriate difficulty | Content matches current level — not too easy, not overwhelming | Adaptive difficulty keeps error rate in 15-25% sweet spot. Scaffolded N flow narrows to 2 for struggling items. |
| Authentic content | Chinese that sounds like real Chinese, not textbook Chinese | Content passes the standard: no excessive repetition, natural register, vivid specificity per storytelling standard. |
| Data safety | Learning progress is never lost | Litestream replication. GDPR deletion/export on request. Uptime >99.5%. |
| No anxiety | The system encourages without pressuring | Non-anxious streak counter. No punitive "you missed a day" messaging. Momentum indicator is informational, not judgmental. |

### Measurement Cadence

- **Daily:** Session completion rate, error rate per drill type
- **Weekly:** Retention rate trends, new items learned vs. reviewed
- **Monthly:** HSK progress estimate, content coverage assessment

### BATNA (Best Alternative to a Negotiated Agreement)

If Aelu fails the Learner, the Learner's alternatives are:
- **Anki:** Superior SRS, no curriculum, no grammar integration, manual card creation
- **Duolingo:** Gamified, shallow, broad but not deep for Mandarin tones
- **HelloChinese:** Mandarin-specific but limited SRS sophistication
- **Pleco:** Dictionary and reader, no SRS drilling
- **Textbook + tutor:** Expensive but effective for motivated learners

**Aelu's edge:** No alternative combines SRS + grammar + exposure + tone grading + authentic content in one system with zero LLM dependency. The BATNA is using 3-4 separate tools.

---

## Stakeholder: Developer

**Who:** Jason (sole developer and operator).

### Win Conditions

| Condition | Definition | Measurement |
|-----------|-----------|-------------|
| Sustainable velocity | Work pace that can be maintained indefinitely without burnout | WIP limit of 3 respected. Intangible allocation >15%. No multi-week crunches. |
| Code comprehensibility | Codebase is understandable after a week away | Any module can be read and modified without "archaeology." Function names are clear. No magic numbers. |
| Deployment confidence | Deploys are boring, not scary | Automated deployment. Health checks. Litestream backup verified before each deploy. Rollback documented. |
| Technical learning | Building Aelu teaches transferable skills | Flask, SQLite, SRS algorithms, iOS deployment, security hardening, GDPR compliance — all transferable. |
| Joy in craft | The work is satisfying, not just necessary | Civic Sanctuary aesthetic is a source of pride. Content quality is a source of pride. System design is clean. |

### Measurement Cadence

- **Daily:** Did WIP limits hold? Did I work on what I planned?
- **Weekly:** How many items completed? Was any tech debt addressed?
- **Monthly:** Burnout check: energy level, motivation, code quality trends

### BATNA

If Aelu fails the Developer, the alternatives are:
- **Stop:** Walk away. App runs unattended on Fly.io. Users (if any) keep learning until something breaks.
- **Hire:** Bring on a contractor for specific features. Reduces bus factor but adds coordination cost.
- **Open source:** Release the code. Community maintains it. Developer keeps learning with community support.
- **Sell:** Transfer the product to someone who wants to operate it.

---

## Stakeholder: Platform

**Who:** The technical infrastructure — Fly.io hosting, SQLite database, Litestream backups, iOS app, web interface. "Platform" is an abstraction for system reliability and security.

### Win Conditions

| Condition | Definition | Measurement |
|-----------|-----------|-------------|
| Reliability | System is available when users need it | Uptime >99.5%. Health check passes continuously. Machine restarts are transparent. |
| Security | No unauthorized access, no data exposure | 0 Critical/High security findings. `security_audit_log` shows no unauthorized access. JWT rotation on schedule. |
| Data durability | Data is never lost, even in disaster | Litestream replication lag <60 seconds. Restore tested quarterly. Backup age verified in health check. |
| Performance | Response times are acceptable | P95 API response <500ms. No `database is locked` errors under normal load. WebSocket latency <100ms. |
| Observability | When something breaks, we know immediately | Health check, crash_log, drill_errors.log, session_trace.jsonl all operational. Alert routing for Expedite scenarios. |

### Measurement Cadence

- **Continuous:** Health check, replication status
- **Daily:** crash_log and drill_errors.log review (start of every dev session)
- **Weekly:** Performance metrics review
- **Monthly:** Backup restore test, security scan

### BATNA

If the Platform fails, the alternatives are:
- **Migrate hosting:** Move from Fly.io to Railway, Render, or self-hosted VPS. Litestream makes data portable.
- **Upgrade database:** Move from SQLite to PostgreSQL if scaling demands it. Requires application layer changes.
- **Simplify architecture:** Drop WebSocket in favor of polling. Drop iOS in favor of PWA. Reduce surface area.

---

## Stakeholder: Content

**Who:** The learning content — vocabulary items, grammar points, context notes, dialogue scenarios, graded reader passages. "Content" is an abstraction for learning material quality.

### Win Conditions

| Condition | Definition | Measurement |
|-----------|-----------|-------------|
| Authenticity | Chinese reads like real Chinese, not translated English | Passes the standard. Native speaker review (when available). No excessive repetition or forced parallelism. |
| Pedagogical soundness | Content teaches effectively, not just exposes | HSK level mapping is accurate. Grammar points cover real usage patterns. Drill types match learning objectives. |
| Cultural respect | Content represents Chinese culture accurately | No stereotypes, no orientalism. Context notes provide genuine cultural insight. |
| Consistency | Quality does not degrade as content volume grows | Every item has a context note. Auto-tagging coverage >80%. Quality review before seeding. |
| Progression | Content supports a coherent learning path | HSK 1 before HSK 2 before HSK 3. Grammar points introduce in order of frequency and complexity. Scaffolded difficulty. |

### Measurement Cadence

- **Per content batch:** Quality review before seeding
- **Monthly:** Content coverage assessment (gaps in HSK levels, missing grammar points)
- **Quarterly:** Full content audit against writing standard

### BATNA

If Content quality fails, the alternatives are:
- **License content:** Use existing HSK textbook content (copyright issues, quality variable)
- **Crowdsource:** Community-contributed content with review (quality control challenge)
- **Generate:** Use LLM to draft, human to review (violates "zero LLM tokens at runtime" but acceptable for content creation)
- **Hire:** Native speaker content creator (cost, but highest quality)

---

## Trade-Off Resolution

When win conditions conflict, use this framework to decide.

### Common Conflicts

| Conflict | Stakeholders | Resolution Principle |
|----------|-------------|---------------------|
| New feature vs. tech debt | Learner (wants features) vs. Developer (wants sustainability) | Intangible allocation (20%) is non-negotiable. Features get 60%, but tech debt gets its guaranteed slot. |
| Speed vs. quality | Learner (wants more content) vs. Content (wants authenticity) | Quality wins. 299 excellent items > 1000 mediocre items. "Stop expanding, start hardening." |
| Security vs. velocity | Developer (wants to ship fast) vs. Platform (wants security) | Security wins. Zero tolerance for High/Critical security risk. A feature that ships with a security hole has negative value. |
| Simplicity vs. features | Developer (wants clean code) vs. Learner (wants more drill types) | Each new drill type must justify its pedagogical value. The 13th drill type needs to clear a higher bar than the 3rd. |
| Cost vs. reliability | Developer (budget) vs. Platform (uptime) | Fly.io single-region is acceptable at <100 users. Multi-region only when user base justifies the cost. |
| Authenticity vs. teachability | Content (authentic Chinese) vs. Learner (needs to understand) | Balance point is the writing standard: 贴切 not 华丽. Naturalness balanced against teachability. Neither extreme wins. |

### Resolution Process

When a conflict arises:

1. **Name the conflict.** Which stakeholders are in tension? What does each want?
2. **Quantify the trade-off.** What is the cost of favoring each side? (Time, quality, risk, money)
3. **Check the hierarchy.** Security > Data durability > Learning effectiveness > Developer sustainability > Everything else.
4. **Find the smallest concession.** Can you give 80% to both sides? A feature that ships next week instead of today, with a security review, satisfies both Developer and Platform.
5. **Document the decision.** On the Kanban card or in the spiral cycle log. Not "I decided X" but "I decided X because Y, trading off Z."

### Hierarchy of Concerns

When no creative resolution exists and one stakeholder must lose:

```
1. Security (Platform)       — Non-negotiable. Breach is catastrophic.
2. Data Durability (Platform) — Learning progress lost = trust destroyed.
3. Learning Effectiveness (Learner) — The entire reason the product exists.
4. Content Quality (Content) — Differentiator. Mediocre content = no moat.
5. Developer Sustainability (Developer) — Important but can absorb short-term cost.
6. Feature Breadth (Learner) — Nice to have. Depth > breadth.
7. Performance (Platform) — Acceptable to be slow briefly. Not acceptable to be broken.
```

---

## Win Condition Dashboard

Track win condition health at each monthly review.

| Stakeholder | Condition | Status | Trend | Notes |
|-------------|-----------|--------|-------|-------|
| Learner | Effective acquisition | Green | Stable | Retention >85% in daily use |
| Learner | Efficient time use | Green | Stable | Session completion >80% |
| Learner | Authentic content | Green | Stable | Writing standard enforced |
| Developer | Sustainable velocity | Yellow | Watch | WIP limits holding but IOC work is dense |
| Developer | Deployment confidence | Green | Improving | Automated deploy working |
| Platform | Reliability | Yellow | Watch | 30-day uptime run not yet completed |
| Platform | Security | Green | Stable | No open Critical/High findings |
| Content | Authenticity | Green | Stable | All 299 items reviewed |
| Content | Progression | Green | Stable | HSK 1-3 coverage complete |

---

## Relationship to Other Artifacts

- **Anchor Points** (`anchor-points.md`): Each anchor point requires stakeholder commitment grounded in win conditions.
- **LCM Commitment Reviews** (`lcm-commitment-reviews.md`): Win condition assessment is part of every review.
- **Risk Register** (`risk-register.md`): Risks threaten specific win conditions. M-002 (retention) threatens Learner. O-001 (bus factor) threatens Developer.
- **Service Classes** (`../kanban/service-classes.md`): Allocation percentages reflect win condition balance.
