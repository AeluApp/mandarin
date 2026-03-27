# Security Policy

**Platform:** Aelu Learning System
**Version:** V2 (Schema V121)
**Last reviewed:** 2026-02-22
**Owner:** Jason Gerson
**Classification:** Internal / Compliance Reference

---

## 1. Security Architecture Overview

The Aelu Learning System is a Flask-based web application for spaced-repetition Mandarin Chinese learning, deployed on Fly.io with a Capacitor-based mobile shell for iOS/Android.

**Architecture summary:**

- **Runtime:** Python 3.12, Flask, Gunicorn (2 workers, 100 connections/worker, max-requests=1000 with jitter), behind Fly.io's Anycast proxy (automatic TLS termination)
- **Database:** Single-tenant SQLite with WAL journal mode, persisted on Fly.io mounted volume (`/data`), replicated to S3 via Litestream
- **Authentication:** Dual-path: Flask-Login server-side sessions (web) + JWT HS256 access/refresh tokens (mobile/API); TOTP MFA (RFC 6238) with backup codes
- **Payments:** Stripe Checkout + Billing Portal; webhook signature verification; no card data stored locally
- **Monitoring:** Sentry (error tracking), Plausible (privacy-respecting analytics), structured JSON logging in production
- **Mobile:** Capacitor shell wrapping the web app; JWT token auth; API versioning via `/api/v1/` prefix rewrite

**Security posture:** The system is designed as a single-tenant, low-attack-surface application. It does not process health data, financial data beyond Stripe delegation, or high-sensitivity PII. The primary data assets are email addresses, hashed passwords, and learning progress records. Security controls are calibrated to this risk profile.

---

## 2. NIST Cybersecurity Framework (CSF) 2.0 Mapping

### GV — Govern

| Category | Subcategory | Implementation | Status |
|----------|-------------|----------------|--------|
| GV.OC-01 | Organizational context understood | Single-developer SaaS; risk profile documented in this file | Implemented |
| GV.RM-01 | Risk management objectives established | Data classification (see Section 6); controls proportional to risk | Implemented |
| GV.RM-02 | Risk appetite determined | Low-sensitivity PII (email, display name); payment delegated to Stripe; no health/financial data stored | Implemented |
| GV.RR-01 | Organizational leadership accountable | Owner (Jason Gerson) is sole operator and accountable party | Implemented |
| GV.PO-01 | Security policy established | This document; MEMORY.md operational constraints; code-enforced defaults | Implemented |
| GV.PO-02 | Policy communicated to workforce | Single operator; no delegation gap | Implemented |
| GV.SC-01 | Supply chain risk management | Third-party deps: Stripe, Fly.io, Sentry, Plausible, Litestream, PyPI packages; no formal SCA policy | Partial |
| GV.SC-02 | Supplier due diligence | Stripe PCI DSS Level 1; Fly.io SOC 2; Sentry SOC 2; Plausible EU-hosted, no cookies; no formal review cycle | Partial |

### ID — Identify

| Category | Subcategory | Implementation | Status |
|----------|-------------|----------------|--------|
| ID.AM-01 | Hardware assets inventoried | Single Fly.io VM (`shared-cpu-1x`, 512MB); mounted volume `/data`; no physical hardware | Implemented |
| ID.AM-02 | Software assets inventoried | `pyproject.toml` dependency list; Dockerfile pins Python 3.12-slim and Litestream 0.3.13; pinned `requirements.txt` | Implemented |
| ID.AM-03 | Data flows mapped | User -> Fly.io TLS -> Flask -> SQLite; Stripe webhooks -> signature verification -> DB; Litestream -> S3 | Implemented |
| ID.AM-05 | Assets prioritized by criticality | SQLite database (learning data, credentials); S3 replica (backup); Stripe customer IDs | Implemented |
| ID.RA-01 | Vulnerabilities identified | Manual code review; Bandit SAST on push/PR; OWASP ZAP DAST on push/PR (`.github/workflows/dast.yml`) | Implemented |
| ID.RA-02 | Threat intelligence received | GitHub Dependabot advisories (pip + Docker, weekly scanning) on PyPI packages; no formal threat intel feed | Implemented |
| ID.RA-03 | Threats identified | OWASP Top 10 addressed in application layer (see Section 7) | Implemented |
| ID.RA-05 | Risk responses determined | Accept residual risk for low-value data; mitigate auth/injection/XSS risks | Implemented |

### PR — Protect

| Category | Subcategory | Implementation | Status |
|----------|-------------|----------------|--------|
| PR.AA-01 | Identities and credentials managed | Email/password accounts; passwords hashed with PBKDF2-SHA256 (werkzeug); reset tokens hashed with SHA-256 and time-limited (1 hour) | Implemented |
| PR.AA-02 | Access authenticated | Flask-Login sessions (HttpOnly, Secure, SameSite=Lax cookies); JWT HS256 access tokens (1-hour expiry); refresh tokens (30-day expiry, hashed in DB, single token per user) | Implemented |
| PR.AA-03 | Access authorized | `@login_required` on all authenticated routes; admin role check on admin routes; subscription tier gating | Implemented |
| PR.AA-05 | Multi-factor authentication | TOTP (RFC 6238) via pyotp with backup codes; JWT MFA flow and web MFA flow; SecurityEvent logging for MFA_ENABLED, MFA_DISABLED, MFA_VERIFIED, MFA_FAILED | Implemented |
| PR.AT-01 | Security awareness training | Single operator; no formal program required | N/A |
| PR.DS-01 | Data-at-rest confidentiality | SQLite on Fly.io encrypted volume; S3 replica uses server-side encryption; passwords hashed, reset tokens hashed | Partial |
| PR.DS-02 | Data-in-transit confidentiality | Fly.io forces HTTPS (`force_https = true` in fly.toml); HSTS header (`max-age=31536000; includeSubDomains; preload`); TLS termination at edge; Litestream to S3 over TLS | Implemented |
| PR.DS-10 | Data-in-use confidentiality | Secrets loaded from environment variables; SECRET_KEY runtime check prevents default in production | Implemented |
| PR.IP-01 | Configuration baselines maintained | Dockerfile, fly.toml, litestream.yml, schema.sql version-controlled | Implemented |
| PR.IP-04 | Backups maintained | Litestream continuous replication to S3; see Section 11 | Implemented |
| PR.PS-01 | Security in SDLC | Manual code review; Bandit SAST on push/PR (`.github/workflows/security.yml`); OWASP ZAP DAST on push/PR (`.github/workflows/dast.yml`); Dependabot for dependency scanning | Implemented |
| PR.IR-01 | Incident response plan | Documented in Section 9 | Implemented |

### DE — Detect

| Category | Subcategory | Implementation | Status |
|----------|-------------|----------------|--------|
| DE.CM-01 | Networks monitored | Fly.io platform metrics; no custom network IDS/IPS | Partial |
| DE.CM-03 | Computing platforms monitored | Sentry error monitoring with Flask integration (filters 401/404 noise); structured JSON logging to stdout | Implemented |
| DE.CM-06 | External service provider activity monitored | Stripe webhook signature verification; Sentry dashboard alerts | Implemented |
| DE.AE-02 | Anomalous activity detected | Rate limiting on auth endpoints (10/min login, 5/hr register, 3/hr forgot-password) with 429 events logged (RATE_LIMIT_HIT); account lockout after 5 failed attempts (15-minute lockout); security audit logging of all auth events including CSRF violations; admin access logging (ADMIN_ACCESS, ACCESS_DENIED) | Implemented |
| DE.AE-03 | Events correlated | Structured JSON logs (timestamp, level, logger, message); security_audit_log table with severity levels; structured log emission for SIEM ingestion | Implemented |

### RS — Respond

| Category | Subcategory | Implementation | Status |
|----------|-------------|----------------|--------|
| RS.MA-01 | Incident management process executed | See Section 9; single-operator triage | Implemented |
| RS.AN-03 | Incidents categorized | Sentry issue grouping; structured log filtering | Implemented |
| RS.MI-01 | Incidents contained | Fly.io machine stop/restart; user deactivation (`is_active` flag); refresh token revocation | Implemented |
| RS.MI-02 | Incidents eradicated | Database migration capability; Fly.io redeployment; secret rotation via environment variables | Implemented |

### RC — Recover

| Category | Subcategory | Implementation | Status |
|----------|-------------|----------------|--------|
| RC.RP-01 | Recovery plan executed | Litestream restore from S3; Fly.io volume restore; see Section 11 | Implemented |
| RC.CO-01 | Recovery communicated | Single operator; user notification via email (Resend integration) | Partial |

---

## 3. ISO 27001:2022 Annex A Control Mapping

### A.5 — Organizational Controls

| Control | Title | Implementation | Status |
|---------|-------|----------------|--------|
| A.5.1 | Policies for information security | This SECURITY.md document; MEMORY.md operational constraints | Implemented |
| A.5.2 | Information security roles and responsibilities | Single operator with full accountability | Implemented |
| A.5.7 | Threat intelligence | GitHub Dependabot (pip + Docker, weekly scanning via `.github/dependabot.yml`); manual monitoring of Flask/PyJWT/werkzeug CVEs | Implemented |
| A.5.8 | Information security in project management | Security considered in feature development; no formal gate process | Partial |
| A.5.9 | Inventory of information and other associated assets | schema.sql defines all data tables; pyproject.toml defines dependencies; fly.toml defines infrastructure | Implemented |
| A.5.10 | Acceptable use of information and other associated assets | Single-purpose system; no shared infrastructure | Implemented |
| A.5.12 | Classification of information | See Section 6 (Data Classification) | Implemented |
| A.5.15 | Access control | Flask-Login + JWT dual-path auth; TOTP MFA (mandatory for admins); role-based (user/admin) authorization; admin access logging | Implemented |
| A.5.17 | Authentication information | PBKDF2-SHA256 password hashing; common password screening (NIST SP 800-63B); SHA-256 reset token hashing; JWT HS256 signing; TOTP MFA with backup codes | Implemented |
| A.5.23 | Information security for use of cloud services | Fly.io (SOC 2); AWS S3 (SOC 2/3, ISO 27001) for Litestream backups | Implemented |
| A.5.24 | Information security incident management planning | See Section 9 | Implemented |
| A.5.25 | Assessment and decision on information security events | Sentry alerting; structured logging; security audit log with severity classification; manual triage | Implemented |
| A.5.26 | Response to information security incidents | See Section 9 | Implemented |
| A.5.29 | Information security during disruption | Litestream S3 backup; Fly.io auto-restart; see Section 11 | Implemented |
| A.5.30 | ICT readiness for business continuity | See Section 11 | Implemented |
| A.5.31 | Legal, statutory, regulatory and contractual requirements | GDPR data export (JSON via `/api/account/export`); account deletion with anonymization (`/api/account/delete`); `data_deletion_request` table for audit trail; no formal DPA with sub-processors | Partial |
| A.5.34 | Privacy and protection of PII | Minimal PII collection (email, display name); Plausible analytics (no cookies, no PII); see Section 6 | Implemented |
| A.5.36 | Compliance with policies, rules and standards for information security | This document; periodic self-review | Partial |

### A.6 — People Controls

| Control | Title | Implementation | Status |
|---------|-------|----------------|--------|
| A.6.1 | Screening | Single operator; N/A | N/A |
| A.6.5 | Responsibilities after termination or change of employment | N/A for single operator | N/A |

### A.7 — Physical Controls

| Control | Title | Implementation | Status |
|---------|-------|----------------|--------|
| A.7.1 | Physical security perimeters | Fly.io managed data center (EWR region); no self-hosted infrastructure | Implemented (delegated) |
| A.7.9 | Security of assets off-premises | Development machine uses FileVault; no production data on local machine | Implemented |
| A.7.10 | Storage media | SQLite DB on Fly.io encrypted volumes; S3 server-side encryption | Implemented |

### A.8 — Technological Controls

| Control | Title | Implementation | Status |
|---------|-------|----------------|--------|
| A.8.1 | User endpoint devices | Capacitor mobile shell; web browser; no MDM | Partial |
| A.8.2 | Privileged access rights | Admin role (`is_admin` flag) separate from user role; mandatory MFA for admin access (CIS 6.5); bootstrap user deactivated (`is_active=0`); bootstrap admin has `subscription_tier = 'admin'` | Implemented |
| A.8.3 | Information access restriction | User data scoped by `user_id` foreign key; queries filtered by authenticated user | Implemented |
| A.8.4 | Access to source code | Private repository; single developer | Implemented |
| A.8.5 | Secure authentication | PBKDF2-SHA256 hashing; 12-char minimum password; common password screening (NIST SP 800-63B, `data/common_passwords.txt`); email validation (regex); account lockout (5 failed → 15-min); TOTP MFA with backup codes; JWT HS256 with expiry (sessionStorage, no URL query params); HttpOnly/Secure/SameSite cookies; refresh token rotation (single token per user, hashed); session invalidation on password change | Implemented |
| A.8.6 | Capacity management | Fly.io auto-start/auto-stop machines; single `shared-cpu-1x` with 512MB; SQLite WAL mode for concurrency | Implemented |
| A.8.7 | Protection against malware | Docker base image `python:3.12-slim`; non-root `appuser`; no file upload endpoints; no user-supplied executable content | Implemented |
| A.8.8 | Management of technical vulnerabilities | Dependabot (pip + Docker, weekly); Bandit SAST on push/PR; OWASP ZAP DAST on push/PR; manual dependency review | Implemented |
| A.8.9 | Configuration management | Infrastructure as code: Dockerfile, fly.toml, litestream.yml, schema.sql; SECRET_KEY production check | Implemented |
| A.8.10 | Information deletion | GDPR Art. 17 account deletion implemented (`/api/account/delete`); anonymizes user record, deletes all personal data from all tables, records in `data_deletion_request` table; full data export via `/api/account/export` (JSON) | Implemented |
| A.8.11 | Data masking | Passwords stored as hashes only; reset tokens stored as SHA-256 hashes; refresh tokens stored as SHA-256 hashes; no plaintext secrets in DB | Implemented |
| A.8.12 | Data leakage prevention | CSP headers restrict script/style/font/image sources; `frame-ancestors 'none'`; `Cache-Control: no-store` on API responses; service worker excludes authenticated API data from cache; JWT removed from URL query strings; PII excluded from logs; no data exfiltration vectors identified | Implemented |
| A.8.13 | Information backup | Litestream continuous WAL replication to S3; see Section 11 | Implemented |
| A.8.14 | Redundancy of information processing facilities | Fly.io multi-region available but currently single-region (EWR); auto-restart on failure | Partial |
| A.8.15 | Logging | Structured JSON logging in production; Sentry error tracking; Flask request logging; security audit log (`security_audit_log` table with 30+ event types including MFA/token/admin/rate-limit/CSRF events, severity, IP, user-agent, request path/method); structured SIEM-ready log emission | Implemented |
| A.8.16 | Monitoring activities | Sentry dashboards; Fly.io metrics; rate limit counters; security audit log with severity-based event classification; structured log emission for SIEM ingestion | Implemented |
| A.8.20 | Networks security | Fly.io managed networking; HTTPS-only; CORS restricted to BASE_URL in production | Implemented |
| A.8.21 | Security of network services | TLS termination at Fly.io edge; ProxyFix middleware for accurate client IP behind proxy | Implemented |
| A.8.22 | Segregation of networks | Single application VM; no internal network segmentation needed | N/A |
| A.8.23 | Web filtering | CSP headers; no outbound web requests from application except Stripe API, Sentry, Resend email | Implemented |
| A.8.24 | Use of cryptography | PBKDF2-SHA256 (password hashing); SHA-256 (token hashing, static file hashing, sync state hashing, audio file hashing — MD5 fully eliminated); HS256 (JWT signing); TOTP (RFC 6238, pyotp); TLS 1.2+ (transit); HSTS with preload; S3 SSE (backup at rest) | Implemented |
| A.8.25 | Secure development life cycle | Version-controlled schema migrations; manual code review; Bandit SAST on push/PR; Dependabot weekly scanning; deterministic runtime (zero LLM tokens) | Implemented |
| A.8.26 | Application security requirements | See Section 7 | Implemented |
| A.8.28 | Secure coding | Parameterized SQL queries throughout (SQLite `?` placeholders); dynamic table names validated via regex assertions; `_ALLOWED_FIELDS` allowlist in mc.py; `validator.py format()` safety-annotated; Jinja2 auto-escaping; input validation on all form/API inputs; `innerHTML` hardened (textContent/createElement where possible, escapeHtml() for HTML builders); bridge.py uses CSS classes instead of inline styles | Implemented |

---

## 4. CIS Controls v8 Mapping (IG2)

| Control | Safeguard | Implementation | Status |
|---------|-----------|----------------|--------|
| **1 — Inventory and Control of Enterprise Assets** | | | |
| 1.1 | Establish and maintain detailed enterprise asset inventory | fly.toml (VM spec), Dockerfile (image), litestream.yml (backup config), schema.sql (data assets) | Implemented |
| 1.2 | Address unauthorized assets | Single VM on Fly.io; no rogue assets possible in managed PaaS | Implemented |
| **2 — Inventory and Control of Software Assets** | | | |
| 2.1 | Establish and maintain a software inventory | pyproject.toml with pinned dependencies; Dockerfile pins Python 3.12 and Litestream version; pinned `requirements.txt` for Docker builds | Implemented |
| 2.2 | Ensure authorized software is currently supported | Python 3.12 (supported through Oct 2028); Flask, PyJWT, werkzeug are actively maintained | Implemented |
| 2.3 | Address unauthorized software | Docker container restricts to installed packages only; no shell access in production | Implemented |
| 2.5 | Allowlist authorized software | Dockerfile `pip install --no-cache-dir .` installs only declared dependencies | Implemented |
| **3 — Data Protection** | | | |
| 3.1 | Establish and maintain a data management process | Data classification in Section 6; SQLite schema version-controlled | Implemented |
| 3.2 | Establish and maintain a data inventory | schema.sql documents all tables and columns; 56 tables (including `security_audit_log`, `data_deletion_request`, `crash_log`, `client_error_log`) with foreign key relationships | Implemented |
| 3.3 | Configure data access control lists | User data scoped by `user_id` FK; admin routes require `is_admin` flag | Implemented |
| 3.4 | Enforce data retention | GDPR account deletion with anonymization and full data purge; JSON/CSV export for data portability; no automated time-based retention policy | Partial |
| 3.6 | Encrypt data on end-user devices | Capacitor mobile app uses platform keychain for JWT storage; web uses HttpOnly cookies | Partial |
| 3.7 | Establish and maintain a data classification scheme | See Section 6 | Implemented |
| 3.9 | Encrypt data on removable media | N/A — no removable media | N/A |
| 3.10 | Encrypt sensitive data in transit | Fly.io `force_https = true`; all API calls over TLS; Litestream to S3 over TLS | Implemented |
| 3.11 | Encrypt sensitive data at rest | Fly.io volumes use encrypted storage; S3 server-side encryption; passwords/tokens hashed | Partial |
| 3.12 | Segment data processing and storage based on sensitivity | Single-tenant SQLite; no multi-tenant data mixing; Stripe handles all payment card data | Implemented |
| **4 — Secure Configuration of Enterprise Assets and Software** | | | |
| 4.1 | Establish and maintain a secure configuration process | Dockerfile, fly.toml, security headers in after_request; SECRET_KEY production guard | Implemented |
| 4.2 | Establish and maintain a secure configuration for network infrastructure | Fly.io managed; HTTPS-only; no open ports except 8080 (internal) | Implemented |
| 4.4 | Implement and manage a firewall on servers | Fly.io platform firewall; only port 8080 exposed internally; HTTPS edge termination | Implemented (delegated) |
| 4.6 | Securely manage enterprise assets and software | Environment variables for secrets (SECRET_KEY, JWT_SECRET, STRIPE_SECRET_KEY, AWS credentials); no secrets in code; `.env` in `.gitignore` | Implemented |
| 4.7 | Manage default accounts | Bootstrap user (`local@localhost`) deactivated (`is_active=0` in migration v17→v18); has `bootstrap_no_login` as password hash (cannot authenticate); production requires invite code for registration | Implemented |
| **5 — Account Management** | | | |
| 5.1 | Establish and maintain an account inventory | `user` table with `created_at`, `last_login_at`, `is_active` fields | Implemented |
| 5.2 | Use unique passwords | Enforced at registration; no password reuse check | Partial |
| 5.3 | Disable dormant accounts | `is_active` flag available; no automated dormancy detection | Partial |
| 5.4 | Restrict administrator privileges | `is_admin` boolean flag; admin routes separated in `admin_routes.py` | Implemented |
| **6 — Access Control Management** | | | |
| 6.1 | Establish an access granting process | Registration requires invite code in production; admin role manually assigned | Implemented |
| 6.2 | Establish an access revoking process | `is_active` flag deactivation; refresh token revocation endpoint | Implemented |
| 6.3 | Require MFA for externally-exposed applications | TOTP MFA (RFC 6238) implemented via pyotp; user-optional enrollment with backup codes | Implemented |
| 6.4 | Require MFA for remote network access | TOTP MFA available for all users; mandatory for admin users | Implemented |
| 6.5 | Require MFA for administrative access | TOTP MFA enforced for all admin users via `admin_required` decorator; admin access blocked until MFA enabled (CIS 6.5) | Implemented |
| **7 — Continuous Vulnerability Management** | | | |
| 7.1 | Establish and maintain a vulnerability management process | Dependabot weekly scanning (pip + Docker); Bandit SAST on push/PR; manual dependency review | Implemented |
| 7.2 | Establish and maintain a remediation process | Dependabot PRs for dependency updates; manual patching via `pip install --upgrade`; re-deploy via Fly.io | Implemented |
| 7.4 | Perform automated application patch management | Dependabot creates PRs for outdated/vulnerable dependencies weekly | Implemented |
| 7.5 | Perform automated vulnerability scans on internal assets | Bandit SAST on push/PR (`.github/workflows/security.yml`); OWASP ZAP DAST on push/PR (`.github/workflows/dast.yml`) | Implemented |
| 7.7 | Remediate detected vulnerabilities | Manual remediation on advisory review | Partial |
| **8 — Audit Log Management** | | | |
| 8.1 | Establish and maintain an audit log management process | Structured JSON logging to stdout; Sentry error tracking; session_log, error_log, and security_audit_log tables in DB; `mandarin/security.py` defines SecurityEvent enum (30+ event types including MFA, token, admin, rate limit, CSRF, logout) with severity levels | Implemented |
| 8.2 | Collect audit logs | Flask request logging; Sentry captures exceptions with request context; `session_log` tracks all learning sessions; `security_audit_log` captures all auth events (login, logout, register, reset, lockout, MFA, token issuance/refresh/revocation, admin access, rate limit hits, CSRF violations) with IP, user-agent, request path/method, and details | Implemented |
| 8.3 | Ensure adequate audit log storage | Fly.io stdout logs (72-hour retention); Sentry (90-day retention on paid plan); SQLite session_log and security_audit_log (indefinite) | Partial |
| 8.5 | Collect detailed audit logs | JSON format: `{ts, level, logger, msg}`; Sentry includes stack traces, request data, user context; security_audit_log includes timestamp, event_type, user_id, ip_address, user_agent, details, severity | Implemented |
| 8.9 | Centralize audit logs | Sentry as centralized error/exception store; security_audit_log emits structured logs for SIEM ingestion; Fly.io log drain available for forwarding | Partial |
| 8.11 | Conduct audit log reviews | Manual review via Sentry dashboard and security_audit_log queries; no automated log analysis | Partial |
| **9 — Email and Web Browser Protections** | | | |
| 9.1 | Ensure use of only fully supported browsers and email clients | No browser restriction enforced; modern browsers required by CSS/JS features | Partial |
| 9.2 | Use DNS filtering services | Not implemented; delegated to Fly.io platform | Planned |
| **10 — Malware Defenses** | | | |
| 10.1 | Deploy and maintain anti-malware software | Docker container with no shell access; no file upload endpoints; minimal attack surface | Implemented |
| 10.2 | Configure automatic anti-malware signature updates | N/A — no file upload or execution from user input | N/A |
| 10.4 | Configure automatic anti-malware scanning of removable media | N/A | N/A |
| **11 — Data Recovery** | | | |
| 11.1 | Establish and maintain a data recovery process | Litestream continuous replication to S3; documented recovery procedure in Section 11 | Implemented |
| 11.2 | Perform automated backups | Litestream replicates SQLite WAL changes to S3 continuously (sub-second RPO) | Implemented |
| 11.3 | Protect recovery data | S3 bucket with IAM-restricted access; credentials in environment variables | Implemented |
| 11.4 | Establish and maintain an isolated instance of recovery data | S3 in separate AWS account/region possible; currently same region | Partial |
| 11.5 | Test data recovery | Manual restore tested; no automated recovery testing schedule | Partial |
| **12 — Network Infrastructure Management** | | | |
| 12.1 | Ensure network infrastructure is up-to-date | Fly.io managed platform; auto-updates | Implemented (delegated) |
| 12.2 | Establish and maintain a secure network architecture | Single-VM architecture; no internal network; HTTPS-only external | Implemented |
| **13 — Network Monitoring and Defense** | | | |
| 13.1 | Centralize security event alerting | Sentry for application errors; Fly.io for platform metrics; no unified SIEM | Partial |
| 13.3 | Deploy a network intrusion detection solution | Not implemented; Fly.io provides basic DDoS protection | Planned |
| 13.6 | Collect network traffic flow logs | Fly.io platform logs; no custom network flow capture | Partial |
| 13.8 | Deploy a WAF | Not implemented; rate limiting provides partial coverage | Planned |
| **14 — Security Awareness and Skills Training** | | | |
| 14.1 | Establish and maintain a security awareness program | Single operator; N/A | N/A |
| **15 — Service Provider Management** | | | |
| 15.1 | Establish and maintain an inventory of service providers | Fly.io (hosting), Stripe (payments), Sentry (monitoring), Plausible (analytics), AWS S3 (backup), Resend (email) | Implemented |
| 15.2 | Establish and maintain a service provider management policy | SOC 2/PCI DSS compliance verified for critical providers; no formal review cadence | Partial |
| **16 — Application Software Security** | | | |
| 16.1 | Establish and maintain a secure application development process | Manual code review; Bandit SAST on push/PR; Dependabot scanning; parameterized queries; template auto-escaping; security headers | Implemented |
| 16.2 | Establish and maintain a process to accept and address software vulnerabilities | See Section 12 (Responsible Disclosure) | Implemented |
| 16.4 | Establish and manage an inventory of third-party software components | pyproject.toml; no automated SBOM generation | Partial |
| 16.6 | Establish and maintain a severity rating system and process for application vulnerabilities | CVSS-based triage on dependency advisories; no formal internal rating system | Partial |
| 16.9 | Train developers in application security concepts | Single operator with security awareness; no formal training program | Partial |
| 16.10 | Apply secure design principles in application architectures | Parameterized queries, least privilege, defense in depth, secure defaults | Implemented |
| 16.11 | Leverage vetted modules or services for application security components | werkzeug (password hashing), PyJWT (JWT), Flask-Login (sessions), Flask-WTF (CSRF), Flask-Limiter (rate limiting) | Implemented |
| **17 — Incident Response Management** | | | |
| 17.1 | Designate personnel to manage incident handling | Single operator | Implemented |
| 17.2 | Establish and maintain contact information for reporting security incidents | See Section 12 | Implemented |
| 17.3 | Establish and maintain an enterprise process for reporting incidents | See Section 9 | Implemented |
| 17.4 | Establish and maintain an incident response process | See Section 9 | Implemented |
| 17.6 | Define mechanisms for communicating during incident response | Email (Resend integration); direct user notification capability | Implemented |
| 17.7 | Conduct routine incident response exercises | Not conducted | Planned |
| **18 — Penetration Testing** | | | |
| 18.1 | Establish and maintain a penetration testing program | No formal program; manual security testing during development | Planned |
| 18.2 | Perform periodic external penetration tests | Not performed | Planned |
| 18.3 | Remediate penetration test findings | N/A — no tests conducted yet | Planned |

---

## 5. Authentication & Access Control

### Password Policy

| Parameter | Value |
|-----------|-------|
| Minimum length | 12 characters (`MIN_PASSWORD_LENGTH = 12` in `auth.py`, enforced on both `create_user` and `reset_password`) |
| Common password screening | NIST SP 800-63B compliant; `data/common_passwords.txt` loaded at startup; rejects passwords found in common password list |
| Email validation | Proper regex validation in `auth.py` |
| Hashing algorithm | PBKDF2-SHA256 via `werkzeug.security.generate_password_hash` |
| Hash storage | `password_hash` column in `user` table |
| Password reset tokens | `secrets.token_urlsafe(32)`, stored as SHA-256 hash, 1-hour expiry |

### Session Authentication (Web)

- Flask-Login with server-side session management
- `remember_me` cookie: 30-day duration, HttpOnly, SameSite=Lax, Secure (production only)
- Session cookie: Secure flag in production
- SECRET_KEY: loaded from environment variable; runtime check prevents default value in production

### JWT Authentication (Mobile/API)

- **Access token:** HS256, configurable expiry (default 1 hour), stateless
- **Refresh token:** `secrets.token_urlsafe(48)`, stored as SHA-256 hash in DB, 30-day expiry
- **Token rotation:** Single refresh token per user (new token replaces old)
- **Revocation:** Explicit revoke endpoint clears refresh token from DB
- **Storage:** sessionStorage (not localStorage — no persistence after tab close; mitigates XSS token theft)
- **Transport:** Authorization Bearer header only; `?token=` query parameter support removed (prevents credential leakage via URL logs/referrer); WebSocket auth uses protocol-level message instead of URL query string

### Rate Limiting

| Endpoint | Limit |
|----------|-------|
| Login | 10/minute |
| Registration | 5/hour |
| Forgot password | 3/hour |
| Token obtain | 10/minute |
| Token refresh | 30/minute |
| Default (all routes) | 200/hour |

Rate limiting uses in-memory storage (`memory://`). Limits reset on application restart.

### Account Lockout

**Status: Implemented.** 5 failed login attempts trigger a 15-minute account lockout. The `user` table includes `failed_login_attempts` and `locked_until` columns. Failed attempts increment the counter; successful login or password reset clears both `failed_login_attempts` and `locked_until`. Lockout events are recorded in `security_audit_log`.

### MFA

**Status: Implemented.** TOTP-based multi-factor authentication (RFC 6238) is implemented via the `pyotp` library.

- **Enrollment:** Users generate a TOTP secret and scan a QR code or enter the secret manually into an authenticator app. Backup codes are generated at enrollment time for recovery.
- **Verification:** Both JWT (mobile/API) and web (Flask-Login) authentication flows support MFA. After primary credential verification, users with MFA enabled must provide a valid TOTP code or backup code to complete authentication.
- **Security events:** `MFA_ENABLED`, `MFA_DISABLED`, `MFA_VERIFIED`, and `MFA_FAILED` events are logged to `security_audit_log` via the `SecurityEvent` enum.
- **Backup codes:** One-time-use backup codes are provided at MFA enrollment for account recovery if the authenticator device is lost.
- **Mandatory for admins:** The `admin_required` decorator enforces MFA for all administrative access (CIS 6.5). Admin users without MFA enabled receive a 403 error with instructions to enable TOTP first.

### Role-Based Access

| Role | Mechanism | Capabilities |
|------|-----------|-------------|
| User | Default on registration | Learning features, data export, account settings |
| Admin | `is_admin` flag on user record | Admin dashboard, user management, system configuration |
| Inactive | `is_active = 0` | Blocked from authentication |

### Open Redirect Prevention

Login redirect (`next` parameter) validates against open redirect using `urlparse` — rejects any URL with a host or scheme component, preventing attacker-controlled redirects after login.

### Session Invalidation on Password Change

Password reset (`reset_password`) clears `refresh_token_hash`, `failed_login_attempts`, and `locked_until`, ensuring all existing sessions and tokens are invalidated when credentials change.

### Invite Code Gating

Production registration requires a valid invite code. Codes have configurable `max_uses` limits and track `use_count`.

---

## 6. Data Protection

### Data Classification

| Classification | Data Elements | Storage | Retention |
|----------------|---------------|---------|-----------|
| **Confidential** | Password hashes, JWT secrets, Stripe API keys, AWS credentials | Hashed in DB / environment variables (never in code) | Indefinite (hashes); secrets rotatable |
| **Internal** | Email addresses, display names, Stripe customer IDs, learning progress, session logs, error logs | SQLite DB, S3 replica | Indefinite; export available |
| **Public** | Content library (hanzi, pinyin, English translations), grammar points, dialogue scenarios | SQLite DB (shared tables, no user_id) | Indefinite |

### Encryption

| Layer | Mechanism | Status |
|-------|-----------|--------|
| Transit | TLS 1.2+ via Fly.io edge (`force_https = true`) | Implemented |
| At rest (DB) | Fly.io volume encryption | Implemented (delegated) |
| At rest (backup) | S3 server-side encryption (SSE-S3 or SSE-KMS) | Implemented |
| At rest (passwords) | PBKDF2-SHA256 hash | Implemented |
| At rest (tokens) | SHA-256 hash | Implemented |
| Application-layer DB encryption | Not implemented (SQLite does not natively support encryption) | Planned |

### PII Handling

- **Collected:** Email address, display name (optional), Stripe customer ID (payment users)
- **Not collected:** Real name, phone number, address, date of birth, government ID
- **Analytics:** Plausible (cookie-free, no PII, EU-hosted)
- **Error tracking:** Sentry (email may appear in user context; Sentry filters 401/404 errors)

### GDPR Compliance

| Right | Implementation | Status |
|-------|----------------|--------|
| Right to access (Art. 15) | Full JSON data export via `GET /api/account/export`; CSV export endpoints: `/api/export/progress`, `/api/export/sessions`, `/api/export/errors` | Implemented |
| Right to data portability (Art. 20) | Full JSON data export via `GET /api/account/export` | Implemented |
| Right to erasure (Art. 17) | `POST /api/account/delete` — anonymizes user record, deletes all personal data from all tables, records in `data_deletion_request` table for audit trail; implemented in `mandarin/web/gdpr_routes.py`. **Audit log retention exception:** Security audit log entries are retained after account deletion under GDPR Art. 17(3)(e) (compliance with legal obligations / establishment, exercise, or defense of legal claims); documented with legal basis in `gdpr_routes.py` | Implemented |
| Right to rectification (Art. 16) | Display name editable; email change not implemented | Partial |
| Data processing agreement | No formal DPA with sub-processors (Fly.io, Stripe, Sentry, AWS) | Planned |

### Data Retention

No automated data retention or purging policy is currently in place. Learning data is retained indefinitely. Session logs and error logs grow unbounded. A formal retention schedule should be established.

---

## 7. Application Security

### OWASP Top 10 Coverage

| Risk | Mitigation | Status |
|------|-----------|--------|
| **A01:2021 Broken Access Control** | `@login_required` on all authenticated routes; `user_id` scoping on all data queries; admin role separation; open redirect prevention via `urlparse` validation; subscription/discount endpoints use `current_user.id` instead of client-supplied `user_id` (IDOR fix); WebSocket resume verifies `user_id` ownership | Implemented |
| **A02:2021 Cryptographic Failures** | PBKDF2-SHA256 password hashing; common password screening (NIST SP 800-63B); SHA-256 for all hashing (tokens, static files, sync state, audio files — MD5 fully eliminated from scheduler.py and audio.py); HS256 JWT; TOTP MFA (pyotp); TLS in transit; HSTS with preload; secrets in environment variables | Implemented |
| **A03:2021 Injection** | Parameterized SQL queries (`?` placeholders) throughout codebase; all f-string SQL table names have regex assertions; `_col_set` table name validated against regex + allowlist; `_ALLOWED_FIELDS` allowlist in mc.py (security-commented); `validator.py format()` safety-annotated; no raw string concatenation in SQL; Jinja2 auto-escaping for HTML output; `_escape_html` in bridge.py escapes `&`, `<`, `>`, `"`, `'`; `innerHTML` hardened (simple cases converted to `textContent`/`createElement`; all HTML builders audited for `escapeHtml()`) | Implemented |
| **A04:2021 Insecure Design** | Invite-code gated registration; rate limiting; single-tenant architecture; minimal attack surface | Implemented |
| **A05:2021 Security Misconfiguration** | Production SECRET_KEY guard; Secure/HttpOnly/SameSite cookies; nonce-based CSP (no `unsafe-inline`); security headers; hardened Dockerfile (Python 3.12, non-root `appuser`, pinned `requirements.txt`); no debug mode in production | Implemented |
| **A06:2021 Vulnerable and Outdated Components** | Python 3.12 (supported through Oct 2028); Dependabot weekly scanning (pip + Docker); Bandit SAST on push/PR; OWASP ZAP DAST on push/PR; pinned `requirements.txt` | Implemented |
| **A07:2021 Identification and Authentication Failures** | PBKDF2-SHA256 hashing; 12-character minimum password; common password screening (NIST SP 800-63B); email regex validation; TOTP MFA with backup codes; rate-limited auth endpoints; account lockout (5 failed attempts, 15-minute lockout); `_get_user_id()` returns 401 (not default user_id); session-based and JWT auth; invite code gating; token expiry enforcement; session invalidation on password change | Implemented |
| **A08:2021 Software and Data Integrity Failures** | Stripe webhook signature verification; Docker image built from source; no CDN-hosted scripts (self-hosted except Plausible) | Implemented |
| **A09:2021 Security Logging and Monitoring Failures** | Structured JSON logging; Sentry error tracking; session/error log tables; `security_audit_log` table with 30+ event types (SecurityEvent enum) including MFA, token, admin, rate limit, CSRF, and logout events; severity, IP, user-agent, request path/method in all events; structured SIEM-ready log emission; PII (email addresses) excluded from logs | Implemented |
| **A10:2021 Server-Side Request Forgery** | No user-controlled outbound HTTP requests; no URL fetch features | N/A |

### Security Headers

Applied to all responses via Flask `after_request`:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy:
  default-src 'self';
  script-src 'self' https://plausible.io;
  style-src 'self' 'nonce-{per-request}' https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data:;
  connect-src 'self' wss: ws:;
  media-src 'self';
  worker-src 'self';
  frame-ancestors 'none'
```

**CSP nonce implementation:** `unsafe-inline` has been replaced with per-request nonce-based CSP for `style-src`. All template `<style>` blocks include a `nonce` attribute matching the per-request nonce generated by the server. This prevents injection of unauthorized inline styles while allowing the application's own styles to function. Bridge.py inline `style=` attributes have been eliminated in favor of CSS classes, removing the need for `unsafe-inline` in `style-src`.

Additional headers applied in production:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Permissions-Policy: camera=(), geolocation=(), payment=(self), microphone=(self)
Cache-Control: no-store, no-cache, must-revalidate, private  (on all API responses)
```

### CSRF Protection

- Flask-WTF `CSRFProtect` enabled globally for form submissions
- `/api/*` POST routes require `X-Requested-With` header on all cookie-authenticated requests (triggers CORS preflight, preventing cross-origin form submission attacks); added to CORS `Access-Control-Allow-Headers`
- JWT Bearer-authenticated requests are inherently CSRF-safe (no ambient credentials)
- CSRF violations logged as `CSRF_VIOLATION` security events via `_verify_api_csrf`
- Stripe webhook endpoint exempted (verified by Stripe signature)
- Token, sync, admin, and payment blueprints exempted (API-only, JWT or signature-protected); onboarding CSRF exemption removed

### CORS Policy

- **Production:** Origin restricted to `BASE_URL` environment variable
- **Development:** Permissive CORS for local development

### Input Validation

- Email: strip + lowercase + proper regex validation in `auth.py`
- Password: minimum length check + common password screening (NIST SP 800-63B)
- Form inputs: strip whitespace, default to empty string on None
- Invite codes: strip whitespace, database validation
- Blog slugs: strict regex validation (`[a-zA-Z0-9-]` only)
- JSON API: `request.get_json(silent=True) or {}` pattern (never crashes on bad JSON)
- Webhook responses: returns only `{"received": true}` (no internal details exposed)

---

## 8. Audit & Monitoring

### Application Logging

| Component | Format | Destination | Retention |
|-----------|--------|-------------|-----------|
| Flask request logs | JSON (`{ts, level, logger, msg}`) | stdout -> Fly.io logs | 72 hours (Fly.io default) |
| Sentry error tracking | Structured exceptions with request context | Sentry cloud | 90 days (plan-dependent) |
| Session log | SQLite table `session_log` (17 columns) | SQLite DB + S3 replica | Indefinite |
| Error log | SQLite table `error_log` (10 columns) | SQLite DB + S3 replica | Indefinite |
| Probe log | SQLite table `probe_log` (8 columns) | SQLite DB + S3 replica | Indefinite |
| Improvement log | SQLite table `improvement_log` (8 columns) | SQLite DB + S3 replica | Indefinite |

### Security Event Logging

**Status: Implemented.** The `mandarin/security.py` module defines a `SecurityEvent` enum with 30+ event types and a `log_security_event()` function. All events are written to the `security_audit_log` table with the following columns:

| Column | Description |
|--------|-------------|
| `timestamp` | UTC timestamp of event |
| `event_type` | SecurityEvent enum value |
| `user_id` | Associated user (nullable for pre-auth events) |
| `ip_address` | Client IP address |
| `user_agent` | Client user-agent string |
| `details` | JSON details specific to event type |
| `severity` | Event severity level |

Events are wired into `auth.py` (login, registration, password reset, lockout), `auth_routes.py` (logout — `LOGOUT`), `token_routes.py` (`TOKEN_ISSUED`, `TOKEN_REFRESHED`, `TOKEN_REVOKED`), admin decorator (`ADMIN_ACCESS`, `ACCESS_DENIED`), 429 handler (`RATE_LIMIT_HIT`), and CSRF verification (`CSRF_VIOLATION`). MFA events (`MFA_ENABLED`, `MFA_DISABLED`, `MFA_VERIFIED`, `MFA_FAILED`) are logged during MFA enrollment and verification flows. All security events include request path and method in the details field (appended by `security.py`). Each event also emits a structured log line for SIEM ingestion. PII (email addresses) is excluded from log output.

### Alerting

| Trigger | Channel | Status |
|---------|---------|--------|
| Unhandled exceptions | Sentry (email/Slack configurable) | Implemented |
| Rate limit exceeded | `RATE_LIMIT_HIT` event logged to `security_audit_log` and structured log; 429 handler | Implemented |
| Failed login threshold | Tracked in `failed_login_attempts` column; logged to `security_audit_log` | Implemented |
| Account lockout | 5 failed attempts → 15-minute lockout; event logged to `security_audit_log` with severity | Implemented |

---

## 9. Incident Response

### Severity Classification

| Severity | Description | Examples | Response Time |
|----------|-------------|----------|---------------|
| Critical | Active exploitation; data breach | DB exfiltration, credential compromise, RCE | Immediate (< 1 hour) |
| High | Vulnerability with exploit potential | SQL injection, auth bypass, privilege escalation | < 4 hours |
| Medium | Security deficiency without active exploit | Missing headers, weak rate limits, outdated dependency with CVE | < 24 hours |
| Low | Best practice deviation | Missing HSTS, verbose error messages | Next development cycle |

### Response Procedures

1. **Detect:** Sentry alert, log review, user report, or external disclosure
2. **Contain:** Fly.io machine stop (`fly machine stop`); user deactivation; refresh token revocation; secret rotation
3. **Investigate:** Review structured logs; Sentry event details; SQLite audit queries
4. **Remediate:** Code fix, dependency update, configuration change
5. **Deploy:** `fly deploy` with updated image
6. **Recover:** Litestream restore if data corruption; S3 point-in-time recovery
7. **Post-incident:** Document root cause; update this security policy; implement preventive controls

### Secret Rotation

| Secret | Rotation Method | Impact |
|--------|----------------|--------|
| SECRET_KEY | Update Fly.io environment variable; redeploy | Invalidates all active sessions |
| JWT_SECRET | Update Fly.io environment variable; redeploy | Invalidates all active JWT tokens |
| STRIPE_SECRET_KEY | Rotate in Stripe dashboard; update environment variable | Brief payment disruption |
| AWS credentials | Rotate in AWS IAM; update environment variable | Brief backup interruption |

### Contact

- **Security contact:** security@aeluapp.com
- **Responsible disclosure:** See Section 12

---

## 10. Vulnerability Management

### Dependency Management

| Practice | Implementation | Status |
|----------|----------------|--------|
| Dependency inventory | pyproject.toml; pinned `requirements.txt` for Docker builds | Implemented |
| Version pinning | Declared in pyproject.toml; Docker image pins Python 3.12 and Litestream versions; `requirements.txt` with pinned versions | Implemented |
| Automated dependency scanning | GitHub Dependabot configured (`.github/dependabot.yml`) for pip and Docker ecosystems, weekly scanning | Implemented |
| Automated SAST | Bandit runs on push/PR via GitHub Actions (`.github/workflows/security.yml`) | Implemented |
| Automated DAST | OWASP ZAP baseline scan on push/PR (`.github/workflows/dast.yml`); tuned rules in `.github/zap-rules.tsv` | Implemented |
| SBOM generation | Not implemented | Planned |
| License compliance | Not formally tracked | Planned |

### Known Technical Debt

| Item | Risk | Remediation |
|------|------|-------------|
| Rate limiter uses in-memory storage | Limits reset on restart; no cross-instance persistence | Acceptable for single-instance SQLite architecture; migrate to Redis if scaling to multiple instances |

### Code Review

All code changes are reviewed by the single operator before deployment. Bandit SAST and OWASP ZAP DAST run automatically on push/PR via GitHub Actions. Dependabot provides weekly dependency vulnerability scanning for pip and Docker ecosystems.

### Penetration Testing

No formal penetration testing has been conducted. An initial external penetration test should be scheduled, with annual recurrence thereafter.

---

## 11. Business Continuity

### Backup Strategy

| Component | Method | Frequency | Retention | Location |
|-----------|--------|-----------|-----------|----------|
| SQLite database | Litestream WAL replication | Continuous (real-time) | Configurable S3 lifecycle | AWS S3 (`${LITESTREAM_S3_BUCKET}`) |
| Application code | Git repository | On commit | Indefinite | Remote Git host |
| Configuration | Version-controlled (Dockerfile, fly.toml, litestream.yml) | On commit | Indefinite | Remote Git host |
| Secrets | Fly.io environment variables | Manual rotation | N/A | Fly.io secrets store |

### Disaster Recovery

| Scenario | Recovery Procedure | RTO | RPO |
|----------|-------------------|-----|-----|
| Application crash | Fly.io auto-restart | < 30 seconds | 0 (WAL replication) |
| VM failure | Fly.io auto-start new machine | < 2 minutes | < 1 second (Litestream) |
| Data corruption | Litestream restore from S3 | < 15 minutes | < 1 second |
| Region outage | Manual redeployment to alternate Fly.io region | < 1 hour | < 1 second |
| Complete Fly.io failure | Provision new infrastructure; restore from S3 | < 4 hours | < 1 second |
| S3 bucket loss | Rebuild from Fly.io volume snapshot (if available) | Variable | Variable |

### Recovery Procedure

```
# Restore database from S3 backup
litestream restore -config /etc/litestream.yml /data/mandarin.db

# Verify integrity
sqlite3 /data/mandarin.db "PRAGMA integrity_check;"

# Restart application
fly deploy
```

### Health Checks and SRE

Three health check endpoints support infrastructure probes and monitoring:

| Endpoint | Purpose | Checks | Use |
|----------|---------|--------|-----|
| `/api/health/live` | Liveness probe | Process alive, uptime | Fly.io/K8s restart trigger |
| `/api/health/ready` | Readiness probe | DB writable, schema current | Fly.io/K8s traffic routing |
| `/api/health` | Full health | DB + schema + content + uptime + latency | Monitoring dashboards |

All health endpoints return `latency_ms` for SLI measurement. SLO/SLI definitions, error budget policy, and runbook documented in `operations/sre/`.

### Single Points of Failure

| Component | Mitigation |
|-----------|-----------|
| Fly.io EWR region | Multi-region deployment available (not currently configured) |
| Single SQLite file | Litestream S3 replication |
| Single VM instance | Fly.io auto-restart; scale to N machines possible |
| S3 bucket | S3 cross-region replication available (not currently configured) |

---

## 12. Responsible Disclosure Policy

### Reporting a Vulnerability

If you discover a security vulnerability in the Aelu Learning System, please report it responsibly:

**Email:** security@aeluapp.com

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested remediation (optional)

**Our commitment:**
- Acknowledge receipt within 48 hours
- Provide an initial assessment within 7 days
- Keep you informed of remediation progress
- Credit you in the fix (unless you prefer anonymity)

**Scope:**
- The web application at the production domain
- The API endpoints (`/api/*`)
- The Capacitor mobile application
- Authentication and authorization mechanisms

**Out of scope:**
- Social engineering attacks
- Denial of service attacks
- Vulnerabilities in third-party services (Stripe, Fly.io, Sentry)
- Issues already documented in Section 10 (Known Technical Debt)

**Safe harbor:** We will not pursue legal action against researchers who report vulnerabilities responsibly, follow this policy, and avoid accessing or modifying other users' data.

---

## 13. Zero Trust Architecture

The system implements a zero trust security model: no request is trusted based on network position alone. Every access decision is verified explicitly.

### Principles and Implementation

| Principle | Implementation |
|-----------|----------------|
| **Verify every request** | JWT tokens verified on every request via `before_request` hook; no implicit trust from network position; `_get_user_id()` returns 401 instead of defaulting to a user |
| **Multi-factor authentication** | TOTP MFA (RFC 6238) via pyotp; JWT and web flows require MFA step for enrolled users; **mandatory for admin users** (CIS 6.5); backup codes for recovery |
| **Authenticate by default** | Endpoints require authentication by default (`@login_required`); public endpoints are explicitly opted out |
| **No credentials in URLs** | JWT removed from query strings (`?token=` support removed); WebSocket auth uses protocol-level message instead of URL parameter |
| **CSRF via custom header** | `X-Requested-With` header required on cookie-authenticated API POST requests; triggers CORS preflight, blocking cross-origin form submissions; CSRF violations logged |
| **Session ownership verification** | WebSocket resume path verifies `user_id` matches before allowing session swap |
| **Server-side identity** | Subscription and discount endpoints use `current_user.id` from server-side session; no client-supplied `user_id` accepted |
| **Ephemeral session tokens** | JWT tokens stored in `sessionStorage` (not `localStorage`); no persistence after tab close; reduces window of token theft |
| **Cache prevention** | API responses marked `Cache-Control: no-store, no-cache, must-revalidate, private`; service worker excludes authenticated API data from cache |
| **Principle of least privilege** | Users can only access their own data (`user_id` scoping); admin role is a separate flag with access logging; bootstrap user deactivated |
| **Audit every auth decision** | Security events logged for both success and failure via `security_audit_log` (login, logout, register, reset, lockout, MFA, token issuance/refresh/revocation, admin access, rate limit hits, CSRF violations); request path/method included in all events |

---

## Appendix: Control Status Summary

| Status | Count | Percentage |
|--------|-------|------------|
| Implemented | 115 | 87% |
| Partial | 13 | 10% |
| Planned | 4 | 3% |

**Priority remediation items (next 90 days):**

1. Conduct initial penetration test (CIS 18.1)
2. Establish formal DPA with sub-processors (GDPR)
3. Implement automated SBOM generation (CIS 16.4)
4. Set up centralized log aggregation / SIEM (CIS 8.9)

---

*This document is version-controlled and reviewed quarterly. Last substantive update: 2026-02-22.*
