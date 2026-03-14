# Spiral Development Log

> Last updated: 2026-03-10
> Format: Each cycle documents objectives, risks, outcomes, and lessons.

---

## Cycle 1: V1 CLI — Personal SRS Engine (2025)

### Objectives
- Build a personal Mandarin spaced repetition system that is better than Anki for the founder's specific use case.
- Prove the SRS engine works: items get scheduled, reviewed, and progress through mastery stages.
- Zero external dependencies at runtime (no API calls, no cloud).

### Risks Identified
| Risk | Disposition |
|------|-----------|
| SRS algorithm produces bad intervals (too frequent or too spaced) | Mitigated: SM-2 variant with manual tuning based on personal experience |
| CLI UX too friction-heavy to maintain daily habit | Accepted: CLI is fine for personal use; web UI comes later |
| Content quality (HSK word lists) insufficient for real learning | Mitigated: context notes added to give cultural/usage depth |

### What Was Built
- Python CLI with Typer/Rich for terminal UI
- SQLite database with WAL mode, foreign keys
- SRS engine (SM-2 variant) with half-life retention model
- 12 drill types (MC, reverse MC, IME, tone, listening gist, etc.)
- HSK 1-3 vocabulary (299 items) with context notes
- 26 grammar points, 14 language skills
- 8 dialogue scenarios
- Day-of-week session profiles (consolidation/stretch modes)
- Error-shape tracking (14 types)
- Self-improvement pattern detection
- Diagnostics and forecasting
- `./run` launcher + interactive menu

### What Was Learned
- **SRS engines are easy to build, hard to tune.** The interval math is straightforward. The hard part is deciding when to promote, demote, and what "mastered" means. Led to the 6-stage mastery lifecycle.
- **Zero-token runtime is a real differentiator.** Every drill, every scheduling decision, every report is deterministic. No API latency, no cost per user, no privacy concerns.
- **Content quality matters more than quantity.** 299 well-annotated items with context notes are more valuable than 10,000 bare word lists.
- **Personal use ≠ product.** Building for yourself proves viability, not market demand.

### Next Cycle Plan
- Web UI to make it accessible beyond the terminal.
- Multi-user support (user accounts, per-user progress).

---

## Cycle 2: V2 Web Interface (February 2026)

### Objectives
- Build a web UI (Flask + WebSocket) that provides the same learning experience as the CLI.
- Add multi-user support (accounts, authentication, per-user progress).
- Add audio: TTS for pronunciation, speaking drill with tone grading.
- Add volume exposure features: graded reader, media shelf, extensive listening.

### Risks Identified
| Risk | Disposition |
|------|-----------|
| WebSocket complexity (state management, reconnection) | Resolved: exponential backoff reconnect, correlation IDs, max 5 attempts |
| Multi-user auth security | Resolved: Flask-Login sessions, CSRF, rate limiting, account lockout |
| macOS TTS dependency (non-portable) | Accepted: edge-tts for production, macOS `say` for local dev |
| Scope creep from feature additions | Partially mitigated: "stop expanding, start hardening" adopted as philosophy |

### What Was Built
- Flask web app with WebSocket drill sessions
- User accounts with email/password auth
- Session-based auth (Flask-Login) + CSRF protection
- Web UI: "Civic Sanctuary" aesthetic (warm stone + teal + terracotta)
- Audio: macOS TTS, edge-tts for production
- Speaking drill with tone grading
- Volume exposure: graded reader, media shelf, extensive listening
- Vocab encounter log for cleanup loop
- 13 new API endpoints
- Context notes system
- Streak counter + momentum indicator
- HSK 7-9 support
- Schema expanded to V13 (16+ tables)

### What Was Learned
- **WebSocket state is the hardest part of web development.** Reconnection, lost messages, correlation IDs — all non-trivial. The bridge pattern (bridge.py) with correlation IDs solved most issues.
- **Aesthetic matters for learning apps.** The "Civic Sanctuary" design (calm, warm, no gamification anxiety) is a product differentiator, not decoration.
- **SQLite Row returns can have None for LEFT JOIN fields.** The `x.get("field") or 0` pattern became essential.
- **"Stop expanding, start hardening" is the right instinct at this stage.** V2 added a lot. Time to stabilize before adding more.

### Next Cycle Plan
- Mobile app (Capacitor) to prove mobile delivery.
- Security hardening before accepting external users.

---

## Cycle 3: Mobile Delivery — Phases A-F (February 2026)

### Objectives
- Wrap the web app in a Capacitor shell for iOS (and Android staging).
- Add native plugins: haptics, push notifications, keyboard awareness.
- Add JWT auth for mobile API access.
- Add offline sync (IndexedDB queue, sync push/pull).
- Prepare App Store submission materials.

### Risks Identified
| Risk | Disposition |
|------|-----------|
| Apple rejection (web wrapper policy) | Mitigated: native plugins add genuine native functionality. TestFlight testing planned. |
| JWT security (token theft, replay) | Resolved: 15-minute access tokens, hashed refresh tokens in DB, server-side revocation |
| Offline sync conflicts | Partially resolved: last-write-wins for progress, append-only for session logs. Edge cases may exist. |
| Capacitor WKWebView differences from Safari | Mitigated: tested on iOS simulator, fixed 302 redirect issue (renders in Safari, not WKWebView) |

### What Was Built
- Capacitor 6 shell (mobile/package.json, capacitor.config.ts)
- JWT auth system (jwt_auth.py, token_routes.py)
- Offline sync (offline-queue.js, sync_routes.py)
- Native plugin bridge (capacitor-bridge.js)
- App icon and splash screen (漫 in terracotta)
- Submission checklist (iOS + Android)
- 23 JWT tests
- Schema expanded to V41 (51 tables)

### What Was Learned
- **Capacitor iOS: 302 redirects open Safari.** Must use `render_template()` directly, never `redirect()`. Documented in MEMORY.md.
- **Capacitor iOS: need `NSAllowsLocalNetworking` for HTTP localhost.** ATS blocks HTTP by default in WKWebView.
- **`server.url` in Capacitor config loads from remote.** Use `?native=1` query param to detect native app context.
- **JWT and session auth can coexist** with a request_loader that checks for Bearer token before falling back to session cookie.

### Next Cycle Plan
- Security hardening (FIX_INVENTORY audit).
- Quality baseline (test coverage, CI/CD).

---

## Cycle 4: Quality Hardening (February-March 2026)

### Objectives
- Systematic security audit and fix all critical/high defects.
- Establish CI/CD pipeline with coverage floor and linting.
- Document everything: BUILD_STATE.md, SECURITY.md, FIX_INVENTORY.md.
- Achieve production-grade reliability for external users.

### Risks Identified
| Risk | Disposition |
|------|-----------|
| Unknown security vulnerabilities | Resolved: FIX_INVENTORY audit found 9 critical, 17 high, 10 medium, 4 low. All critical/high fixed. |
| CI/CD not catching regressions | Resolved: GitHub Actions with pytest (coverage floor 55%), ruff linting, Python 3.9+3.12 matrix |
| MFA implementation complexity | Resolved: TOTP with pyotp, rate-limited, DB-backed challenge tokens |
| CSP breaking localhost development | Resolved: `upgrade-insecure-requests` only in production (`IS_PRODUCTION` flag) |

### What Was Built
- FIX_INVENTORY.md: 40 defects catalogued, 36 fixed, 4 deferred
- Security fixes: session fixation, lockout bypass, JWT token bypass, unauthenticated endpoints
- MFA (TOTP): setup, verify, disable with rate limiting
- CI pipeline: pytest + ruff + coverage + Python matrix
- Pre-commit hooks: ruff + gitleaks
- Security audit log table
- GDPR data export/deletion with error handling
- Crash log and client error log tables
- Grade appeal workflow
- 1,343 tests across 59 suites

### What Was Learned
- **Security audits find real bugs.** C1 (session fixation) and C3 (JWT bypass) were legitimate vulnerabilities that would have been exploitable in production.
- **Coverage floors are useful but crude.** 55% floor catches regressions but doesn't ensure critical paths are tested. Need targeted coverage for auth, payment, and SRS paths.
- **SQLite can't ALTER CHECK constraints.** Must recreate the table. Discovered during error_log migration.
- **Pre-commit hooks save time.** gitleaks caught a test fixture that looked like a credential.

### Next Cycle Plan
- Cloud deployment (Fly.io).
- First external users (PMF validation).

---

## Cycle 5: Cloud Deployment (March 2026)

### Objectives
- Deploy to Fly.io with Litestream backup.
- Verify health checks, auto-stop/start, HTTPS.
- Production configuration (secrets, CSP, environment variables).

### Risks Identified
| Risk | Disposition |
|------|-----------|
| Litestream backup reliability | Mitigated: health check endpoint, S3 versioning, monthly restore test planned |
| SQLite WAL mode on Fly.io volume | Resolved: WAL mode works on Fly.io persistent volumes. Tested. |
| Cold start latency (auto-stop/start) | Accepted: ~2-3 second cold start. Acceptable for current user base (just Jason). |
| Secret management | Resolved: `fly secrets set` for all sensitive config. No secrets in code. |

### What Was Built
- Dockerfile with gunicorn + gevent workers
- docker-entrypoint.sh (Litestream restore on startup)
- fly.toml (shared-cpu-1x, 512MB, persistent volume, health checks)
- litestream.yml (SQLite → S3 replication)
- Production CSP (upgrade-insecure-requests only when IS_PRODUCTION=true)
- .env.example with all required variables documented

### What Was Learned
- **Fly.io persistent volumes survive machine restarts.** SQLite data persists across deploys and auto-stop/start cycles.
- **Port 5000 is AirTunes on macOS Monterey+.** Use port 5173 for local development.
- **CSP `upgrade-insecure-requests` breaks localhost.** Silently upgrades HTTP to HTTPS, causing all sub-resources (CSS, JS, fonts) to fail to load. Only apply in production.
- **Health checks are essential.** Without `/api/health/ready`, Fly.io doesn't know if the app started successfully.

### Next Cycle Plan
- PMF validation: onboard external users, measure engagement, decide go/no-go.

---

## Cycle 6: PMF Validation (March 2026 — Current)

### Objectives
- Onboard 10 external beta users.
- Measure: signup conversion, session completion, 30-day retention.
- Content marketing: Reddit, language learning communities.
- Hit Milestone 1 criteria (see go-no-go-criteria.md).

### Risks Identified
| Risk | Status |
|------|--------|
| R1: No evidence of PMF | OPEN — this cycle's primary risk to resolve |
| R10: Burnout from doing everything | OPEN — marketing + development + operations simultaneously |
| R17: Negative public reception | OPEN — first public exposure |

### What Has Been Built (So Far)
- Landing page (marketing/)
- Kanban board and flow tracking (this docs/kanban/ directory)
- Risk register and spiral documentation (this docs/spiral/ directory)
- Reddit post draft (X-001 on board)

### What Has Been Learned (So Far)
- TBD — cycle is in progress.

### Next Cycle Plan
- Depends on Milestone 1 go/no-go decision.
