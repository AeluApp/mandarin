# SIPOC Diagram — Aelu Mandarin Learning System

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Process:** Core Learning Loop (Session Lifecycle)

---

## High-Level SIPOC

```
SUPPLIERS → INPUTS → PROCESS → OUTPUTS → CUSTOMERS
```

---

## Suppliers

| Supplier | What They Provide | Interface |
|----------|------------------|-----------|
| HSK Standards Body (Chinese Ministry of Education) | HSK 1-9 word lists, grammar point definitions, level boundaries | Static seed data in `content_item`, `grammar_point`, `skill` tables |
| edge-tts (Microsoft) | Text-to-speech audio synthesis | Browser Web Speech API (client-side, zero server cost) |
| Content Authors (Jason) | 299 seed items, 299 context notes, 8 dialogue scenarios, 26 grammar points, 14 language skills, graded reading passages, media recommendations | `content_item`, `dialogue_scenario`, `grammar_point`, `skill` tables + JSON passage files |
| SQLite | ACID-compliant embedded database engine | WAL-mode single-file DB at `/data/mandarin.db` |
| Fly.io | Compute (shared-cpu-1x, 512MB), persistent volumes, TLS termination, health checks, auto-scaling | `fly.toml`, Dockerfile, `docker-entrypoint.sh` |
| Litestream | SQLite replication to S3 (disaster recovery) | `litestream.yml`, continuous WAL streaming |
| Stripe | Payment processing, subscription management, webhook events | `payment.py`, `payment_routes.py`, Stripe SDK |
| Resend | Transactional email delivery (welcome, password reset, streak reminders, churn re-engagement) | `email.py`, `email_scheduler.py`, Resend API |
| Sentry | Error monitoring, crash reporting | `sentry-sdk[flask]`, DSN in secrets |
| Python Runtime | Language runtime (3.12 in production, 3.9.6 in dev) | Dockerfile `python:3.12-slim` |
| Pre-commit / Ruff / Gitleaks | Code quality, linting, secret detection | `.pre-commit-config.yaml`, `pyproject.toml` |

---

## Inputs

| Input | Source | Format | Volume |
|-------|--------|--------|--------|
| HSK word lists | Ministry of Education via seed scripts | SQLite rows in `content_item` (299 items HSK 1-3, expanding) | ~7,000 total HSK 1-9 when complete |
| User drill responses | Learner via web/iOS/CLI | JSON POST to `/api/session/grade` | ~15 per session, ~45/week per active user |
| Audio TTS | edge-tts via browser | Client-side Web Speech API calls | 1 per drill item (on-demand, not pre-generated) |
| Payment info | Stripe checkout / customer portal | Stripe webhook events | Per subscription event |
| Session telemetry | Client instrumentation | `client_event` table INSERTs via `/api/events` | ~50-100 events per session |
| Error reports | Client JS error handler | `client_error_log` via `/api/error-report` | 0-5 per session (ideally 0) |
| User feedback | In-app NPS prompt | `user_feedback` table via `/api/feedback` | Post-session, optional |
| Learner profile | User settings, placement test | `learner_profile` row per user | 1 per user, updated continuously |

---

## Process — 6-Step Core Learning Loop

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  Step 1          Step 2          Step 3          Step 4                 │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │ User     │    │ Session  │    │ Drills   │    │ Grading +        │   │
│  │ opens    │───▶│ planned  │───▶│ delivered│───▶│ error            │   │
│  │ app      │    │ via SRS  │    │ (27      │    │ classification   │   │
│  └─────────┘    │ scheduler│    │ types)   │    │ (deterministic)  │   │
│                 └──────────┘    └──────────┘    └──────────────────┘   │
│                                                         │              │
│                                                         ▼              │
│                 Step 6          Step 5                                  │
│                 ┌──────────┐    ┌──────────────────┐                   │
│                 │ Review   │◀───│ SRS update +     │                   │
│                 │ scheduled│    │ progress tracking│                   │
│                 └──────────┘    └──────────────────┘                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Step 1: User Opens App
- **Action:** User navigates to Aelu web app, iOS app, or CLI
- **Systems:** Flask server (`server.py`), Capacitor iOS shell, CLI (`cli.py`)
- **Auth:** JWT token validation (`jwt_auth.py`), optional MFA (`mfa.py`)
- **Output:** Authenticated session, dashboard rendered

### Step 2: Session Planned via SRS Scheduler
- **Action:** Scheduler builds a session plan: which items, which drill types, what order
- **Systems:** `scheduler.py` — gap-aware, skip-tolerant, error-weighted, interleaved
- **Logic:** FSRS-based review queue + new item budget + error_focus boost + adaptive day profiles + interleaving enforcement + mapping group constraints
- **Data reads:** `progress`, `error_focus`, `error_log`, `review_event`, `session_log`, `learner_profile`, `content_item`
- **Output:** Ordered list of `(content_item_id, drill_type, modality)` tuples, stored as `plan_snapshot` in `session_log`

### Step 3: Drills Delivered
- **Action:** Each planned item is rendered as one of 27 drill types
- **Systems:** `drills/dispatch.py` routes to specific drill runner (MC, tone, IME, listening, production, speaking, advanced)
- **Drill types:** mc, reverse_mc, ime_type, tone, listening_gist, listening_detail, listening_tone, listening_dictation, intuition, english_to_pinyin, hanzi_to_pinyin, pinyin_to_hanzi, register_choice, pragmatic, slang_exposure, speaking, transfer, measure_word (4 variants), word_order, sentence_build, particle_disc, homophone, translation, cloze_context, synonym_disc, listening_passage, dictation_sentence, shadowing, minimal_pair, passage_dictation, number_system, tone_sandhi, complement, ba_bei, collocation, radical, error_correction, chengyu
- **Client interaction:** Present prompt, capture answer, optionally play TTS audio
- **Output:** User answer string, response time in ms

### Step 4: Grading + Error Classification
- **Action:** Deterministic grading (zero AI tokens) — exact string match, fuzzy pinyin match, tone number acceptance, multi-valid-answer resolution
- **Systems:** `drills/base.py` (`classify_error_cause`, `cause_to_error_type`), per-drill grading logic in each drill module
- **Error types:** tone, segment, ime_confusable, grammar, vocab, register_mismatch, particle_misuse, function_word_omission, temporal_sequencing, measure_word, politeness_softening, reference_tracking, pragmatics_mismatch, number, other
- **Output:** `DrillResult` dataclass (correct, error_type, confidence, score, feedback)

### Step 5: SRS Update + Progress Tracking
- **Action:** Update spaced repetition state, log review event, update error focus, compute session metrics
- **Systems:** `runner.py` (session runner), `db/session.py` (progress updates), `retention.py` (half-life model)
- **Data writes:** `progress` (ease_factor, interval_days, next_review_date, mastery_stage), `review_event`, `error_log`, `error_focus`, `session_metrics`
- **Mastery stages:** seen → shaky → fair → solid → strong → mastered (6-stage model)
- **Output:** Updated SRS state for each drilled item

### Step 6: Review Scheduled
- **Action:** Next review dates computed, session summary generated, streak updated
- **Systems:** `scheduler.py` (next review calculation), `metrics_report.py` (session report), `milestones.py` (streak tracking)
- **Data writes:** `progress.next_review_date`, `session_log.ended_at`, `session_log.session_outcome`
- **Output:** Session complete, user returned to dashboard with summary

---

## Outputs

| Output | Destination | Format | Frequency |
|--------|------------|--------|-----------|
| Mastery progress | Learner (dashboard) | Visual progress bars per modality, HSK level, mastery stage distribution | Real-time after each session |
| Session reports | Learner (post-session) | Accuracy %, items reviewed, items strengthened/weakened, session duration | After every session |
| Retention predictions | Learner (dashboard) | Half-life days, predicted recall probability per item | Updated per review event |
| Error focus patterns | Learner (focus view) | Top error types ranked by frequency, specific items with recurring errors | Updated per session |
| Churn risk scores | Admin (churn report) | 0-100 composite score from 8 behavioral signals | `./run churn-report` on demand |
| HSK projections | Learner (forecast view) | Multi-criteria projection of HSK level completion dates | `./run forecast` on demand |
| Improvement proposals | Admin (improve log) | System self-diagnosis: observations, proposed parameter changes | `./run improve` on demand |
| Crash/error logs | Dev (Sentry, crash_log table) | Tracebacks, request context, severity | On every server error |
| Grade appeals | Admin (appeal queue) | User-submitted challenges to grading decisions | On user submission |

---

## Customers

| Customer | Needs | Current Status |
|----------|-------|---------------|
| **Self-study learner** (primary) | Adaptive sessions, error-focused drilling, visible progress, tone feedback, reading/listening exposure | Active — all core features built |
| **Teacher** (classroom) | Student progress dashboards, assignment integration, LTI compatibility | Schema built (`classroom`, `classroom_student`, `lti_platform`), routes exist (`lti_routes.py`), no active teacher users |
| **Admin** (Jason) | System health monitoring, grading consistency, churn detection, improvement proposals | Active — CLI commands, crash_log, security_audit_log |

---

## Key Metrics per Process Step

| Step | Metric | Target | Current Measurement |
|------|--------|--------|-------------------|
| 1. Open app | Time to interactive | < 2s | `client_event` category='performance' |
| 2. Plan session | Planning latency | < 200ms | Server-side timing in `scheduler.py` |
| 3. Deliver drills | Drill render time | < 100ms | Client-side, not yet instrumented |
| 4. Grade | Grading consistency | 100% reproducible | Deterministic (Gage R&R = 0%) |
| 5. SRS update | DB write latency | < 50ms | SQLite WAL, not yet instrumented |
| 6. Schedule review | Session completion rate | 85% | `session_log.items_completed / items_planned` |
