# Risk Taxonomy

> Last updated: 2026-03-10

## Purpose

A consistent classification system for identifying, categorizing, and assessing risks across Aelu. This taxonomy ensures risks are not missed due to blind spots and provides a shared vocabulary for the risk register.

---

## Top-Level Categories

```
Risk
├── Technical
│   ├── Architecture
│   ├── Data Integrity
│   ├── Platform Compatibility
│   ├── Dependency
│   └── Algorithm
├── Security
│   ├── Authentication
│   ├── Authorization
│   ├── Data Protection
│   ├── Input Validation
│   └── Infrastructure
├── Performance
│   ├── Database
│   ├── Network
│   ├── Client-Side
│   └── Scalability
├── Compliance
│   ├── GDPR
│   ├── App Store
│   ├── Accessibility
│   └── Payment (PCI)
├── Market
│   ├── Competition
│   ├── Retention
│   ├── Content Quality
│   └── Pricing
└── Operational
    ├── Bus Factor
    ├── Infrastructure
    ├── Monitoring
    ├── Burnout
    └── Process
```

---

## Second-Level Breakdown

### Technical Risks

| Sub-Category | Scope | Aelu-Specific Concerns |
|-------------|-------|----------------------|
| **Architecture** | System design decisions that constrain future options | SQLite as production database, monolithic Flask app, no microservices |
| **Data Integrity** | Correctness and durability of stored data | SRS scheduling state, learner progress, vocab encounter logs, Litestream replication fidelity |
| **Platform Compatibility** | Cross-platform behavioral differences | Capacitor iOS vs. web vs. macOS CLI. WKWebView quirks, CSP differences, audio API differences |
| **Dependency** | Third-party library risks | Python 3.9 EOL, parselmouth build failures, Flask/Jinja2 security patches, numpy compatibility |
| **Algorithm** | Correctness of learning algorithms | FSRS interval calculation, tone grading accuracy, adaptive difficulty, interleaving enforcement |

### Security Risks

| Sub-Category | Scope | Aelu-Specific Concerns |
|-------------|-------|----------------------|
| **Authentication** | Identity verification | JWT validation, token expiry, secret rotation, session management |
| **Authorization** | Access control | Role-based access (learner/teacher/admin), classroom isolation, API endpoint protection |
| **Data Protection** | Data at rest and in transit | SQLite encryption (Fly.io volume), HTTPS enforcement, Litestream backup encryption, GDPR data handling |
| **Input Validation** | Untrusted input handling | SQL injection prevention (parameterized queries), XSS prevention (Jinja2 escaping), API parameter validation |
| **Infrastructure** | Hosting and deployment security | Fly.io secrets management, SSH access, deployment pipeline integrity, DNS security |

### Performance Risks

| Sub-Category | Scope | Aelu-Specific Concerns |
|-------------|-------|----------------------|
| **Database** | Query and write performance | SQLite concurrent writes, missing indexes (15 tables flagged), WAL checkpoint timing, large table scans |
| **Network** | Latency and throughput | Fly.io single-region deployment, WebSocket connection stability, API response times |
| **Client-Side** | Browser and app rendering performance | Web Audio API latency, CSS animation performance, Capacitor bridge overhead, large DOM rendering (graded reader) |
| **Scalability** | Behavior under growth | SQLite connection limits, Fly.io machine size, Litestream replication under write load |

### Compliance Risks

| Sub-Category | Scope | Aelu-Specific Concerns |
|-------------|-------|----------------------|
| **GDPR** | EU data protection regulation | Data deletion within 30 days, data export, consent management, privacy policy accuracy, data processing records |
| **App Store** | Apple review guidelines | In-app purchase requirements, content guidelines, privacy nutrition labels, App Tracking Transparency |
| **Accessibility** | Disability access requirements | Screen reader compatibility, color contrast ratios, keyboard navigation, hanzi rendering at accessible sizes |
| **Payment (PCI)** | Payment card data handling | Stripe handles card data (PCI scope minimized). Webhook security, subscription state accuracy. |

### Market Risks

| Sub-Category | Scope | Aelu-Specific Concerns |
|-------------|-------|----------------------|
| **Competition** | Competitive landscape | Duolingo (scale), HelloChinese (Mandarin-specific), Pleco (dictionary), Anki (SRS). Differentiation: depth over breadth. |
| **Retention** | User engagement over time | Session completion rates, streak maintenance (non-anxious), content freshness, difficulty progression |
| **Content Quality** | Learning material standards | 分寸 writing standard adherence, authenticity vs. teachability balance, context notes quality, grammar point accuracy |
| **Pricing** | Revenue model viability | $9.99/month individual, annual tier, institutional pricing, free tier scope |

### Operational Risks

| Sub-Category | Scope | Aelu-Specific Concerns |
|-------------|-------|----------------------|
| **Bus Factor** | Key person dependency | Solo developer. Documentation quality determines recoverability. |
| **Infrastructure** | Hosting and operations | Fly.io availability, Litestream backup reliability, DNS management, SSL certificate renewal |
| **Monitoring** | Observability and alerting | `crash_log` coverage, `drill_errors.log` review, `security_audit_log` completeness, health check gaps |
| **Burnout** | Developer sustainability | WIP limits as protection, intangible allocation, "stop expanding, start hardening" as guardrail |
| **Process** | Development workflow | Kanban discipline, commit quality, testing rigor, deployment safety |

---

## Risk Identification Methods

Risks don't announce themselves. Use these methods systematically to find them before they find you.

| Method | Frequency | What It Catches | Aelu Implementation |
|--------|-----------|----------------|-------------------|
| **Code review** | Every change | Technical, Security, Algorithm | Self-review before commit. `bandit` static analysis for security. |
| **Threat modeling** | Quarterly | Security, Compliance | STRIDE analysis on new features. Review auth flows, data flows, trust boundaries. |
| **User feedback** | Ongoing (when launched) | Market, Performance, Content Quality | Support channel triage. Categorize by risk taxonomy. |
| **Monitoring** | Continuous | Performance, Operational, Security | `crash_log`, `drill_errors.log`, `session_trace.jsonl`, Fly.io metrics, Litestream status. |
| **Dependency scanning** | Weekly | Technical (Dependency), Security | `pip-audit` in CI. Review CVE databases for Python 3.9 and direct dependencies. |
| **Penetration testing** | Quarterly | Security (all sub-categories) | Self-administered. Test auth bypass, injection, privilege escalation, GDPR endpoints. |
| **Architecture review** | Per spiral cycle | Technical (Architecture), Performance (Scalability) | Question: "If we 10x users tomorrow, what breaks first?" |
| **Retrospective** | Monthly | All categories | Blocker root cause analysis feeds risk identification. See `../kanban/blocked-items-policy.md`. |

---

## Risk Assessment Criteria

### Probability Scale

| Score | Label | Frequency Guideline | Aelu Context |
|-------|-------|-------------------|-------------|
| 1 | Rare | Less than once per year | Event has never occurred and requires multiple failures to trigger |
| 2 | Unlikely | Once per year | Event could happen but safeguards exist |
| 3 | Possible | Once per quarter | Event is plausible given current state |
| 4 | Likely | Once per month | Event is expected without active prevention |
| 5 | Almost Certain | Weekly or more | Event is happening or has recently happened |

### Impact Scale

| Score | Label | User Impact | Business Impact | Technical Impact |
|-------|-------|-------------|-----------------|-----------------|
| 1 | Negligible | No user notices | No revenue impact | Cosmetic issue only |
| 2 | Minor | Some users mildly inconvenienced | <$100 revenue impact | Workaround exists |
| 3 | Moderate | Feature degraded for all users | $100-1000 revenue impact | Requires code fix within a week |
| 4 | Major | Core feature broken | $1000+ revenue impact or churn | Requires immediate fix, possible data loss |
| 5 | Catastrophic | All users affected, data loss | Business viability threatened | System unrecoverable without backup restore |

---

## Risk Appetite Statement

Aelu's risk appetite reflects its position as a solo-founder product handling personal learning data:

**We accept medium technical risk** (score 5-9). SQLite as a production database is a calculated bet — it simplifies operations at the cost of scaling headroom. We accept this trade-off at current scale and monitor for the threshold where it breaks.

**We accept zero tolerance for security risk** above Low (score >4). Any security risk scoring High or Critical triggers Expedite class of service. Auth bypass, data breach, and credential exposure are never acceptable, regardless of probability.

**We accept medium market risk** (score 5-9). Competition is fierce and retention is hard. We differentiate on depth and quality, not features. We accept that most users will not choose Aelu — we optimize for the serious learners who do.

**We accept low operational risk** (score 1-4) for data durability. Litestream replication, health checks, and automated restarts are non-negotiable. The bus factor risk (O-001, score 15) is acknowledged as the single highest risk — mitigation is documentation, not hiring.

---

## Relationship to Other Artifacts

- **Risk Register** (`risk-register.md`): Individual risk entries classified using this taxonomy.
- **Risk Retirement Criteria** (`risk-retirement-criteria.md`): Conditions under which risks are moved from active tracking.
- **Prototyping Strategy** (`prototyping-strategy.md`): Risk type determines prototyping approach.
- **Spiral Cycle Template** (`spiral-cycle-template.md`): Risk identification is Phase 2 of every cycle.
