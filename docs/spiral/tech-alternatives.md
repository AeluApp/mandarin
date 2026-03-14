# Technology Alternatives Evaluation

> Last updated: 2026-03-10
> Format: ADR-inspired (Context, Options, Decision, Rationale, Consequences, Revisit Trigger)

---

## 1. Database: SQLite vs Postgres vs CockroachDB

**Context:** Aelu needs a persistent data store for user accounts, learning progress (SRS state), session logs, and content items. Currently 51 tables, ~10,000 content items per user. Single-region deployment on Fly.io.

**Options Evaluated:**

| Option | Pros | Cons |
|--------|------|------|
| SQLite + Litestream | Zero ops, sub-ms queries, single-file backup, WAL mode for concurrent reads, $0/month | Write contention at scale (1 writer at a time), no native replication, Litestream is a bolted-on solution |
| Postgres (managed, e.g., Supabase, Neon) | Proven at scale, concurrent writes, rich ecosystem, managed backups | $15-30/month for managed instance, network latency on every query, connection pooling complexity |
| CockroachDB (serverless) | Infinite horizontal scale, multi-region, strong consistency | Overkill for <1000 users, expensive at scale, different SQL dialect, vendor lock-in |

**Decision:** SQLite + Litestream

**Rationale:** At 0-100 users, SQLite is not just adequate — it's optimal. Sub-millisecond queries with no network hop. Zero operational burden. Litestream provides continuous backup to S3 for ~$1/month. The write contention issue only matters at >100 concurrent write-heavy users, and Aelu's write pattern is light (a few inserts per drill answer, a few updates per session).

**Consequences:**
- Positive: No database server to manage. Cold starts are instant (no connection pool warmup). Backup is continuous and cheap.
- Negative: Single-machine constraint. No horizontal scaling. Must migrate if write contention becomes measurable.
- Accepted trade-off: When the day comes to migrate to Postgres, the SQL is standard enough that migration is mechanical (rewrite datetime('now') to NOW(), INTEGER PRIMARY KEY to SERIAL, etc.).

**Revisit Trigger:** crash_log contains `sqlite3.OperationalError: database is locked` errors affecting users. Or user count exceeds 500 and growth is accelerating.

---

## 2. Framework: Flask vs FastAPI vs Django

**Context:** Web framework for serving the learning UI, API endpoints, and WebSocket connections. Needs to support: HTML templates, REST API, WebSocket, session auth, JWT auth, rate limiting.

**Options Evaluated:**

| Option | Pros | Cons |
|--------|------|------|
| Flask | Familiar, minimal, mature ecosystem (Flask-Login, Flask-Limiter, Flask-WTF), Jinja2 templates, flask-sock for WebSocket | No async by default, no built-in ORM, no auto-generated API docs |
| FastAPI | Async native, auto-generated OpenAPI docs, Pydantic validation, modern Python typing | Requires async everywhere (SQLite async is tricky), smaller ecosystem for auth/rate limiting, template rendering is second-class |
| Django | Batteries included (ORM, admin, auth, forms), large community | Heavy for a single-developer project, ORM doesn't play well with SQLite WAL, template language less flexible than Jinja2, opinionated structure conflicts with existing codebase |

**Decision:** Flask

**Rationale:** Flask's minimalism matches Aelu's architecture. The app is a monolith with 51 tables managed via raw SQL — an ORM would add friction, not value. flask-sock provides WebSocket support for the drill session bridge. The existing codebase (~20 route files, ~50 templates) is Flask-native. Switching would require rewriting everything with no user-facing benefit.

**Consequences:**
- Positive: Simple mental model. One thread per request. Synchronous code that's easy to debug.
- Negative: No auto-generated API docs (mitigated by manual openapi.yaml). No async (mitigated by gevent for WebSocket).

**Revisit Trigger:** Need for true async (e.g., streaming LLM responses, real-time collaboration). Or performance profiling shows Flask's synchronous model is the bottleneck (unlikely — SQLite queries are sub-ms).

---

## 3. Hosting: Fly.io vs Railway vs Render vs AWS

**Context:** Need to run a Docker container with persistent storage (SQLite file), health checks, auto-restart, and HTTPS termination. Budget: <$20/month.

**Options Evaluated:**

| Option | Pros | Cons |
|--------|------|------|
| Fly.io | Persistent volumes (SQLite-friendly), auto-stop/start, global edge network, Docker-native, excellent CLI | Smaller company (risk), occasional platform incidents, pricing model can be surprising |
| Railway | Simple deploy from Git, managed Postgres, good DX | No persistent volumes (bad for SQLite), Postgres-oriented |
| Render | Free tier, managed Postgres, simple | No persistent volumes on free tier, cold starts on free tier |
| AWS (ECS/Fargate) | Enterprise-grade, full control, EFS for persistent storage | Complex setup, minimum ~$30/month for ECS + ALB + EFS, over-engineered for a solo project |

**Decision:** Fly.io

**Rationale:** Fly.io is the only platform that offers persistent volumes at <$1/month, which is essential for SQLite. The auto-stop/start feature means the machine only runs when requests arrive, keeping costs at ~$5-7/month. Docker-native deployment means the same Dockerfile works locally and in production. The Fly CLI (`flyctl`) is excellent for debugging (SSH into machine, check logs, run one-off commands).

**Consequences:**
- Positive: $5-7/month all-in. Persistent SQLite. Health checks built in. HTTPS automatic.
- Negative: Single-vendor dependency. If Fly.io shuts down or has a major incident, migration is needed. Mitigated by: the app is a standard Docker container that runs anywhere.

**Revisit Trigger:** Fly.io pricing increases >3x. Fly.io has >2 multi-hour outages in a quarter. Need for managed Postgres (Railway or Render become better options). User base grows beyond single-machine capacity.

---

## 4. Mobile: Capacitor vs React Native vs Flutter

**Context:** Need iOS (and eventually Android) app. Existing codebase is Flask + vanilla JS + WebSocket. Don't want to rewrite the frontend.

**Options Evaluated:**

| Option | Pros | Cons |
|--------|------|------|
| Capacitor | Wraps existing web app in native shell, access to native APIs (haptics, push, keyboard), same codebase for web + mobile | Performance limited by WebView, may be rejected by Apple as "web wrapper," less native feel |
| React Native | True native components, large community, good performance | Requires complete frontend rewrite in React, separate codebase from web, React expertise needed |
| Flutter | Cross-platform with one codebase, excellent performance, Google-backed | Requires complete rewrite in Dart, separate codebase from web, new language to learn |

**Decision:** Capacitor

**Rationale:** Aelu's frontend is intentionally simple — no complex animations, no heavy UI. The learning experience is text-based (hanzi, pinyin, English) with occasional audio. A WebView renders this perfectly. Capacitor lets the same HTML/CSS/JS serve web and mobile with zero code duplication. Native plugins (haptics on correct/incorrect, push notifications for streak reminders, keyboard awareness for input drills) provide enough "native feel."

**Consequences:**
- Positive: One codebase. Changes to web UI automatically appear on mobile. Native plugin bridge (capacitor-bridge.js) provides haptics, push, status bar.
- Negative: Risk of Apple rejection (mitigated by using native plugins, not a bare web view). Performance ceiling for complex interactions (acceptable for Aelu's text-based UX).

**Revisit Trigger:** Apple rejects the app for being a web wrapper (despite native plugins). Users report the app feeling "laggy" compared to native competitors. Need for offline-first functionality that exceeds WebView's IndexedDB capabilities.

---

## 5. Architecture: Monolith vs Microservices

**Context:** Aelu has ~30 Python modules, 51 database tables, 12 drill types, and ~50 API endpoints. One developer.

**Options Evaluated:**

| Option | Pros | Cons |
|--------|------|------|
| Monolith | Simple deployment, simple debugging, shared database, no network calls between components | All-or-nothing deploy, harder to scale individual components |
| Microservices | Independent scaling, independent deployment, technology diversity | Network complexity, distributed transactions, service discovery, 10x operational burden for a solo developer |

**Decision:** Monolith

**Rationale:** A solo developer operating microservices is a recipe for burnout. Every feature touches 2-3 concerns (auth, content, SRS state) that share the same SQLite database. Splitting these into services would add network latency, require a message bus, and create distributed state management problems — all for zero user benefit. The monolith deploys in one `fly deploy` and debugs with one log stream.

**Consequences:**
- Positive: One deploy target. One log stream. Shared database with referential integrity. Simple debugging.
- Negative: Can't scale SRS computation independently from web serving. Acceptable because SRS computation is <1ms per item.

**Revisit Trigger:** Need to scale a specific component independently (e.g., audio generation takes too long and blocks web requests). At that point, extract that specific component as a background worker, not a full microservice.

---

## 6. Auth: Session-Based vs JWT-Only vs OAuth

**Context:** Need to authenticate users for web (browser) and mobile (Capacitor app). Support MFA (TOTP). Handle password reset flows.

**Options Evaluated:**

| Option | Pros | Cons |
|--------|------|------|
| Session-based (Flask-Login) | Simple, secure by default (HttpOnly cookies), server-side session invalidation | Doesn't work for mobile API (no cookies in native context), CSRF required for forms |
| JWT-only | Stateless, works for mobile API, no server-side session storage | Can't revoke tokens without blocklist, larger attack surface, complex refresh flow |
| Hybrid (session for web, JWT for mobile) | Best of both — cookies for browser, Bearer tokens for API | Two auth systems to maintain, more code paths to secure |
| OAuth (social login only) | No password management, trusted identity providers | Dependency on Google/Apple, not all users want social login, still need session/JWT for subsequent requests |

**Decision:** Hybrid (session for web + JWT for mobile API)

**Rationale:** Web users get Flask-Login sessions (secure HttpOnly cookies, CSRF protection via Flask-WTF). Mobile/API users get JWT access tokens (15-minute expiry) with hashed refresh tokens stored in the user table (30-day expiry). The JWT refresh token is hashed (SHA-256) in the database, enabling server-side revocation. Both paths converge on the same user model and permission checks.

**Consequences:**
- Positive: Browser users get simple, secure cookie auth. Mobile users get standard Bearer token auth. Refresh tokens are revocable.
- Negative: Two auth code paths (Flask-Login request_loader for JWT, session for cookies). Both are tested (23 JWT tests, session tests in auth test suites).

**Revisit Trigger:** If OAuth/social login is requested by users. Or if the JWT implementation creates security issues not caught by current tests.

---

## 7. SRS Engine: Custom FSRS vs Anki Algorithm vs SM-2

**Context:** Aelu needs a spaced repetition scheduler to determine when to review each vocabulary item. Must support: multiple modalities (reading, listening, speaking, IME), 6-stage mastery lifecycle, error-informed scheduling, half-life retention model.

**Options Evaluated:**

| Option | Pros | Cons |
|--------|------|------|
| SM-2 (SuperMemo 2) | Simple, well-understood, easy to implement | Fixed intervals, no per-item difficulty, poor for items with varied error patterns |
| Anki algorithm (SM-2 variant) | Proven at scale, interval modifiers, ease factors | Ease factor "hell" (items get stuck at minimum ease), no multi-modality support |
| FSRS (Free Spaced Repetition Scheduler) | State-of-the-art, per-item difficulty, stability/difficulty model | Complex to implement correctly, requires more review data to calibrate, black-box feel |
| Custom (SM-2 variant + half-life retention + error-informed) | Tailored to Aelu's 6-stage mastery lifecycle, integrates error shapes, supports modality-specific scheduling | Not battle-tested at scale, may have unknown failure modes |

**Decision:** Custom (SM-2 variant with extensions)

**Rationale:** Aelu's SRS engine needs features that no off-the-shelf algorithm provides: 6-stage mastery lifecycle (seen → passed_once → stabilizing → stable → durable → decayed), error-shape-informed scheduling (14 error types that influence drill selection), modality-specific intervals (reading and listening progress independently), and interest-driven scheduling (content lens weighting). Building custom allows tight integration with these systems.

**Consequences:**
- Positive: Scheduler is deeply integrated with mastery lifecycle, error tracking, and content lenses. Every scheduling decision is explainable.
- Negative: Not validated against FSRS or other state-of-the-art algorithms. May be suboptimal for long-term retention. No community of users to report issues.

**Revisit Trigger:** Users report feeling that review intervals are wrong (too frequent or too spaced). Or academic literature shows FSRS significantly outperforms SM-2 variants for language learning specifically. At that point, consider implementing FSRS as an alternative engine and A/B testing against the current scheduler.

---

## 8. TTS: edge-tts vs Google Cloud TTS vs Azure TTS

**Context:** Aelu needs text-to-speech for Mandarin audio. Used for: pronunciation examples in drills, extensive listening passages, speaking drill reference audio.

**Options Evaluated:**

| Option | Pros | Cons |
|--------|------|------|
| edge-tts | Free (uses Microsoft's endpoint), good Mandarin voices, async API | Unofficial API (could break/be blocked), no SLA, rate limits unknown |
| Google Cloud TTS | Official API, high quality, WaveNet voices, $4/1M chars | Costs money, requires GCP account and API key, network dependency |
| Azure TTS | Official API, neural voices, SSML support, $4/1M chars | Costs money, requires Azure account, similar to Google in quality |
| Browser Web Speech API | Free, no server dependency, works offline | Quality varies by browser/OS, no control over voice, unreliable for Mandarin tones |
| macOS `say` command | Free, built-in, offline | macOS only, mediocre Mandarin quality, not usable in production |

**Decision:** edge-tts (primary) + Browser Web Speech API (fallback for web extensive listening)

**Rationale:** edge-tts provides high-quality Mandarin voices at zero cost. Audio can be pre-generated and cached, so the unofficial API status is manageable — if it breaks, switch to Google/Azure TTS ($4/1M chars = ~$5/month at scale). The Browser Web Speech API is used for the extensive listening feature where pre-generation isn't practical (arbitrary passage text).

**Consequences:**
- Positive: $0/month TTS cost. Good voice quality. Pre-generation means no runtime dependency on the API.
- Negative: edge-tts could be discontinued or blocked at any time. Migration to Google/Azure TTS is straightforward but adds ~$5/month at scale.

**Revisit Trigger:** edge-tts starts failing (rate limits, API changes, quality degradation). Or users report that TTS pronunciation is inaccurate for specific tones/words. At that point, evaluate Google Cloud TTS Neural2 voices, which are considered best-in-class for Mandarin.
