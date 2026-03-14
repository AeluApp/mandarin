# Risk Register

> Last updated: 2026-03-10
> Owner: Jason (sole developer/operator)
> Review cadence: Monthly at service delivery review, or immediately upon risk event

## Scoring Criteria

- **Probability (P):** 1 = Rare, 2 = Unlikely, 3 = Possible, 4 = Likely, 5 = Almost Certain
- **Impact (I):** 1 = Negligible, 2 = Minor, 3 = Moderate, 4 = Major, 5 = Catastrophic
- **Risk Score:** P x I (1-25). Critical: 15-25, High: 10-14, Medium: 5-9, Low: 1-4

---

## Technical Risks

| ID | Risk | P | I | Score | Mitigation | Contingency | Owner | Status |
|----|------|---|---|-------|------------|-------------|-------|--------|
| T-001 | SQLite scaling — concurrent writes cause `database is locked` under load (>50 concurrent users) | 3 | 4 | 12 | WAL mode enabled, connection pooling, write serialization via queue. Load test planned (D-005). | Migrate to PostgreSQL on Fly.io. Migration path: SQLAlchemy abstraction layer. | Jason | Active |
| T-002 | Python 3.9 EOL (October 2025, already past) — no security patches, dependency compatibility degrading | 4 | 3 | 12 | Monitor `pip-audit` for 3.9-specific CVEs. Test against Python 3.11+ in CI. | Upgrade to Python 3.11. Known blocker: verify all deps (sounddevice, numpy) build cleanly. | Jason | Active |
| T-003 | iOS Capacitor compatibility — WKWebView behavioral differences break features silently | 3 | 3 | 9 | Test on iOS simulator after every web UI change. Document platform gotchas (MEMORY.md). | Fall back to Safari redirect for broken features. Accept degraded native experience. | Jason | Active |
| T-004 | SQLite schema migration failure — ALTER TABLE limitations (no DROP COLUMN pre-3.35, no ALTER CHECK) | 2 | 4 | 8 | Use table recreation pattern for schema changes. Test migrations on copy of production DB. | Restore from Litestream backup. Replay migration manually. | Jason | Active |
| T-005 | Litestream replication lag or failure — backup gap during write-heavy periods | 2 | 5 | 10 | Health check monitors replication status. Alert on replication age > 60 seconds. | Manual SQLite backup via `sqlite3 .backup`. Worst case: lose data since last successful replication. | Jason | Active |
| T-006 | macOS TTS dependency — `say` command unavailable on Linux/deployed Fly.io environment | 2 | 2 | 4 | TTS is client-side (browser SpeechSynthesis API for web, macOS `say` for CLI only). Server has no TTS dependency. | Use browser-based TTS everywhere. Remove CLI TTS if server deployment required. | Jason | Mitigated |
| T-007 | FSRS algorithm instability — edge cases in spaced repetition produce nonsensical intervals | 2 | 3 | 6 | Interval clamping (min 1 day, max 365 days). Diagnostic commands (`./run diagnostics`) verify scheduling sanity. | Revert to SM-2 algorithm. Historical review data is algorithm-agnostic. | Jason | Active |
| T-008 | Flask session/WebSocket state loss on Fly.io machine restart | 3 | 2 | 6 | JWT-based auth (stateless). WebSocket reconnection logic in client. No server-side session state. | Client detects disconnect, re-authenticates, resumes. Worst case: user refreshes page. | Jason | Mitigated |

---

## Security Risks

| ID | Risk | P | I | Score | Mitigation | Contingency | Owner | Status |
|----|------|---|---|-------|------------|-------------|-------|--------|
| S-001 | Auth bypass — JWT validation flaw allows unauthorized access | 2 | 5 | 10 | JWT middleware validates on every request. `security_audit_log` tracks auth events. Penetration testing. Fixed C1-C3 (same-day, Feb 2026). | Invalidate all JWTs (rotate secret). Force re-login. Audit `security_audit_log` for unauthorized access. | Jason | Active |
| S-002 | Data breach — unauthorized access to SQLite database file | 2 | 5 | 10 | Fly.io volume encryption at rest. Application-level access control. No direct DB exposure. Litestream backups encrypted. | Notify affected users (GDPR Article 33: 72 hours). Rotate all secrets. Forensic analysis of access logs. | Jason | Active |
| S-003 | GDPR violation — failure to process deletion/export request within 30 days | 2 | 4 | 8 | Fixed Date class of service for all GDPR requests. `gdpr_deletion_request` and `gdpr_data_export` endpoints implemented. Calendar reminders. | Process immediately upon discovery. Document delay reason. Self-report to supervisory authority if >30 days. | Jason | Active |
| S-004 | SQL injection — unsanitized input reaches SQLite queries | 1 | 5 | 5 | Parameterized queries throughout codebase. No string concatenation for SQL. `bandit` static analysis in CI. | Patch immediately. Audit affected tables for data corruption. | Jason | Mitigated |
| S-005 | XSS in web UI — user-generated content rendered without escaping | 2 | 3 | 6 | Jinja2 auto-escaping enabled. CSP headers restrict inline scripts. Content is system-generated (not user-generated for now). | Patch template. Invalidate cached pages. Review CSP policy. | Jason | Active |
| S-006 | Credential exposure — JWT secret, Stripe keys, or DB path leaked in logs or git | 2 | 5 | 10 | Environment variables for all secrets. `.gitignore` covers `.env`. Log sanitization. No secrets in error messages. | Rotate exposed credential immediately. Check git history for exposure. | Jason | Active |
| S-007 | Stripe webhook signature bypass — payment events processed without verification | 1 | 4 | 4 | Webhook signature validation using Stripe library. Replay protection via event ID deduplication. | Disable webhook endpoint. Process payments manually until fixed. | Jason | Mitigated |

---

## Market Risks

| ID | Risk | P | I | Score | Mitigation | Contingency | Owner | Status |
|----|------|---|---|-------|------------|-------------|-------|--------|
| M-001 | Competitor apps (Duolingo, HelloChinese, Pleco) — feature parity impossible as solo dev | 4 | 3 | 12 | Differentiate on depth (SRS + grammar + exposure + tone grading), not breadth. Target serious learners, not casual. 分寸 writing standard as moat. | Narrow focus to HSK 1-3 mastery. Own one niche completely rather than competing on features. | Jason | Active |
| M-002 | Learner retention — users drop off after initial enthusiasm | 4 | 4 | 16 | Streak counter (non-anxious), momentum indicator, adaptive session length, interleaving enforcement, context notes for engagement. | Analyze dropout points. Implement re-engagement (email, push notifications). Shorten default session length. | Jason | Active |
| M-003 | Content quality — 分寸 standard is expensive to maintain as content scales beyond HSK 3 | 3 | 3 | 9 | Content generation pipeline (`content_gen/`). Quality review before seeding. 299 items with 299 context notes — quality over quantity. | Accept slower content growth. Partner with native speakers for content review. Prioritize breadth only after depth is solid. | Jason | Active |
| M-004 | Pricing sensitivity — $9.99/month too high for individual learners, too low for institutions | 3 | 2 | 6 | Annual pricing tier ($119.88/yr = 2 months free). Classroom/LTI features for institutional pricing. Free tier for evaluation. | Experiment with pricing. Usage-based pricing as alternative. | Jason | Active |

---

## Operational Risks

| ID | Risk | P | I | Score | Mitigation | Contingency | Owner | Status |
|----|------|---|---|-------|------------|-------------|-------|--------|
| O-001 | Bus factor = 1 — sole developer incapacitated, project halts | 3 | 5 | 15 | Documentation (BUILD_STATE.md, schema docs, this risk register). Automated deploys. Litestream backups run without intervention. | If short-term: app continues running on Fly.io indefinitely. If long-term: documented enough for another developer to take over. | Jason | Active |
| O-002 | Fly.io hosting reliability — machine restarts, region outages | 2 | 3 | 6 | Health checks with auto-restart. Litestream replication to S3 for data durability. Single-region (acceptable for current scale). | Restore from Litestream backup to new Fly.io machine or alternative host. Data recovery time: ~30 minutes. | Jason | Active |
| O-003 | Development burnout — solo founder overwork degrades code quality and judgment | 3 | 4 | 12 | WIP limits (3 items max). Intangible allocation (20%) for sustainable pace. "Stop expanding, start hardening" philosophy. | Take a break. The app runs unattended. Users continue learning. Return when ready. | Jason | Active |
| O-004 | Secret rotation failure — expired or compromised credentials not rotated promptly | 2 | 4 | 8 | Calendar reminders for credential expiry. JWT secret rotation procedure documented. Stripe key rotation documented. | Rotate immediately. Accept brief downtime during rotation. | Jason | Active |
| O-005 | Monitoring blind spot — production issue occurs but no alert fires | 3 | 3 | 9 | Health check endpoint (`/api/health/ready`). `crash_log` table. `drill_errors.log` reviewed at start of every dev session. | Proactive log review catches issues. User reports via support channel. | Jason | Active |

---

## Risk Heat Map

```
Impact ->   1         2         3         4         5
         Negligible Minor   Moderate  Major    Catastrophic
    5    |         |         |         |         |
Almost   |         |         |         |         |
Certain  |         |         |         |         |
    4    |         |         | M-001   | M-002   |
Likely   |         |         |         |         |
    3    |         | T-008   | T-003   | O-003   | O-001
Possible |         | T-007   | M-003   | T-001   |
         |         |         | O-005   | T-002   |
    2    |         | T-006   | S-005   | S-003   | S-001,S-002
Unlikely |         | M-004   |         | T-004   | S-006
         |         |         |         | O-004   |
    1    |         |         |         | S-007   | S-004
Rare     |         |         |         |         |
```

---

## Review Log

| Date | Reviewer | Changes | Next Review |
|------|----------|---------|-------------|
| 2026-03-10 | Jason | Initial risk register created | 2026-04-10 |

---

## Relationship to Other Artifacts

- **Risk Taxonomy** (`risk-taxonomy.md`): Classification system for risk categories.
- **Risk Retirement Criteria** (`risk-retirement-criteria.md`): When to stop actively tracking a risk.
- **Spiral Cycle Template** (`spiral-cycle-template.md`): Each cycle identifies and resolves risks from this register.
- **Kanban Board** (`../kanban/board.md`): Risk mitigations generate Backlog items.
- **SLA Policy** (`../kanban/sla-policy.md`): Security risk events trigger Expedite SLA.
