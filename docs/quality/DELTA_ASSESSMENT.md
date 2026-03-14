# Quality Delta Assessment

> Date: 2026-02-25 | Assessor: Claude (Six Sigma operator) | Owner: Jason

---

## 1. Baseline + Gaps — Delta View

Every area labeled ALREADY DONE / PARTIAL / MISSING with repo evidence.

### 1.1 Product Telemetry

| Area | Status | Evidence |
|------|--------|----------|
| Session outcome tracking | ALREADY DONE | `session_log.session_outcome` — completed/abandoned/bounced. Written on every session close (`db/session.py:end_session`). |
| Drill accuracy tracking | ALREADY DONE | `session_log.items_correct`, `items_completed` — populated per session. |
| Early exit detection | ALREADY DONE | `session_log.early_exit` — boolean, set when user quits mid-session. |
| Boredom detection | ALREADY DONE | `session_log.boredom_flags` — integer count of too-easy streaks per session. |
| Churn risk scoring | ALREADY DONE | `churn_detection.py:score_churn_risk()` — 8-signal composite (days_inactive, session_trend, accuracy_trend, completion_trend, error_ratio, vocab_stall, time_decay, streak_break). Runs hourly via `email_scheduler.py`. |
| Lifecycle event logging | ALREADY DONE | `marketing_hooks.py:log_lifecycle_event()` — signup, first_session, streak_milestone, subscription_change. Stored in `lifecycle_event` table. |
| Weekly KPI report | ALREADY DONE | `metrics_report.py` — WASU, accuracy, early_exit, session_outcomes. Run via `./run metrics`. |
| Session completion rate by segment | PARTIAL | `metrics_report.py` reports aggregate outcomes, not broken out by session_type / modality / HSK band. |
| Crash rate calculation | PARTIAL | `crash_log` table exists (V24 migration). No automated rate = crashes / requests. |
| Client error rate | PARTIAL | `client_error_log` table + `/api/error-report` endpoint exist. No automated rate per 100 sessions. |
| Funnel analytics (signup → first session → retained) | MISSING | `lifecycle_event` has the raw data but no funnel query or report exists. |
| Revenue metrics (MRR, conversion rate) | MISSING | Stripe webhook writes `subscription_tier` but no MRR calculation exists. |

### 1.2 CI / Quality Gates

| Area | Status | Evidence |
|------|--------|----------|
| Test suite (3.9 + 3.12) | ALREADY DONE | `.github/workflows/test.yml` — matrix: [3.9, 3.12], pytest with `--cov-fail-under=50`. |
| Coverage floor | ALREADY DONE | `pyproject.toml` `fail_under = 50`, enforced in CI. |
| Ruff lint in CI | ALREADY DONE | `test.yml` lint job: `ruff check mandarin/ --config pyproject.toml`. |
| Quality regression tests | ALREADY DONE | `test.yml` quality-gates job: `pytest tests/test_quality_fixes.py`. 14 regression tests. |
| Bandit SAST | ALREADY DONE | `security.yml` bandit job: 0 HIGH findings required. |
| Pre-commit hooks | ALREADY DONE | `.pre-commit-config.yaml` — ruff hook on every commit. |
| SBOM generation | ALREADY DONE | `security.yml` sbom job — artifact only, no block. |
| ZAP DAST | ALREADY DONE | `dast.yml` — OWASP ZAP baseline scan, WARN only. |
| DR test | ALREADY DONE | `dr-test.yml` — weekly scheduled. |
| Deploy gate | ALREADY DONE | `deploy.yml` — tests must pass before Fly.io deploy. |
| Coverage config unified | ALREADY DONE | Merged `.coveragerc` into `pyproject.toml`, deleted `.coveragerc`. |

### 1.3 Test Coverage by Subsystem

| Subsystem | Test File | Tests | Status |
|-----------|-----------|-------|--------|
| Auth (Session) | `test_auth.py` | 47 | ALREADY DONE |
| Auth (JWT) | `test_jwt_auth.py` | 23 | ALREADY DONE (this session) |
| MFA (unit) | `test_mfa.py` | 17 | ALREADY DONE |
| MFA (HTTP) | `test_mfa_routes.py` | 18 | ALREADY DONE (this session) |
| Authorization / Tier Gate | `test_tier_gate.py` | 13 | ALREADY DONE (this session) |
| Payment (Stripe) | `test_payment.py` | 21 | ALREADY DONE (this session) |
| GDPR | `test_gdpr_routes.py` | 10 | ALREADY DONE (this session) |
| Admin | `test_admin_routes.py` | 37 | ALREADY DONE (this session) |
| Classroom & LTI | `test_classroom_routes.py` | 37 | ALREADY DONE (this session) |
| Web Routes | `test_web_routes.py` | ~120 | ALREADY DONE |
| API Error Handler | `test_api_error_handler.py` | ~15 | ALREADY DONE |
| Quality Regressions | `test_quality_fixes.py` | 14 | ALREADY DONE (this session) |

### 1.4 Security Hardening

| Area | Status | Evidence |
|------|--------|----------|
| Session fixation protection | ALREADY DONE | `session.clear()` before all 3 `login_user()` calls in `auth_routes.py`. Regression test: `test_session_clear_before_login`. |
| Account lockout bypass | ALREADY DONE | Malformed `locked_until` now denies login in `auth.py`. Regression test: `test_lockout_bypass_malformed_date`. |
| Refresh token expiry bypass | ALREADY DONE | Malformed expiry rejects token in `jwt_auth.py`. Regression test: `test_refresh_token_expiry_bypass`. |
| GDPR error handling | ALREADY DONE | Both export + delete wrapped in try/except. Regression test: `test_gdpr_export_has_error_handling`. |
| GDPR SQL guard | ALREADY DONE | `re.match()` regex guard on export SELECT. Regression test: `test_gdpr_export_has_regex_guard`. |
| MFA rate limits | ALREADY DONE | 5/hr disable, 10/hr setup in `__init__.py`. |
| Marketing rate limits | ALREADY DONE | 10/hr feedback, 20/hr referral signup. |
| Media auth check | ALREADY DONE | `_get_user_id()` on comprehension submit. |
| Idempotent migrations | ALREADY DONE | All 7 bare `DROP TABLE` → `DROP TABLE IF EXISTS`. Regression test: `test_idempotent_drops`. |
| MFA tokens in DB | ALREADY DONE | `mfa_challenge` table (V25 migration). `_mfa_tokens` dict removed. Multi-worker safe. |
| Password hash method explicit | PARTIAL | `cli.py:2576` still missing `method=` — CLI-only path, not web. |

### 1.5 Documentation

| Area | Status | Evidence |
|------|--------|----------|
| SUBSYSTEM_MAP.md | ALREADY DONE | `docs/quality/SUBSYSTEM_MAP.md` — 15 subsystems, every source file assigned. |
| CTQ_REGISTRY.md | ALREADY DONE | `docs/quality/CTQ_REGISTRY.md` — per-subsystem DPMO/sigma. |
| FIX_INVENTORY.md | ALREADY DONE | `docs/quality/FIX_INVENTORY.md` — 34 defects catalogued (C1-C9, H1-H17, M1-M10, L1-L4). |
| NEXT_30_DAYS.md | ALREADY DONE | `docs/quality/NEXT_30_DAYS.md` — 13 items, projected 2.5σ → 3.8σ. |
| OPERATING_SYSTEM.md | ALREADY DONE | `docs/quality/OPERATING_SYSTEM.md` — CTQs, KPIs, weekly review, release checklist, incident template, CI gates. |
| Per-subsystem sigma reports | ALREADY DONE | `reports/quality/*.md` — 15 reports. |
| BUILD_STATE.md table/test counts | ALREADY DONE | Updated to 30 tables, 996 tests across 48 suites. |
| SECURITY.md table count | ALREADY DONE | Updated to 30 tables. |
| schema.sql sync with migrations | ALREADY DONE | 40 CREATE TABLE statements, all migration tables present. |
| AUDIT_LOG.md | ALREADY DONE | `docs/quality/AUDIT_LOG.md` — 4 entries, baseline through round 3. |

### 1.6 Configuration / Infra

| Area | Status | Evidence |
|------|--------|----------|
| .env.example complete | ALREADY DONE | All 24 env vars documented including 7 added this session. |
| Coverage config unified | ALREADY DONE | `.coveragerc` deleted, all config in `pyproject.toml`. |
| Env vars centralized in settings.py | ALREADY DONE | 0 `os.environ.get` outside settings.py. 5 new constants: ALERT_WEBHOOK_URL, ADMIN_EMAIL, PORT, SESSION_TIMEOUT_MINUTES, FLASK_ENV. |
| Dead loggers cleaned | ALREADY DONE | 8 removed (validator, caliper, xapi, landing_routes, export, grammar_seed, context_notes, db/curriculum). 2 activated (grammar_linker, db/content). |

---

## 2. Post-Fix Sigma Scorecard

Round 7 full re-audit with expanded CTQ dimensions (780 total opportunities). All original defects verified FIXED against current code.

| # | Subsystem | Pre-Fix DPMO | Pre-Fix σ | R7 DPMO | R7 σ | Key Fixes (cumulative) |
|---|-----------|-------------|-----------|---------|------|------------------------|
| 1 | Routing ★ | 35,928 | 3.3 | 0 | ≥4.5 | Error handling, security headers, WebSocket auth |
| 2 | Auth (Session) ★ | 107,143 | 2.7 | 0 | ≥4.5 | Session fixation, lockout bypass, cookie flags, open redirect |
| 3 | Auth (JWT) ★ | 333,333 | 1.9 | 0 | ≥4.5 | Refresh expiry, MFA→DB, token rotation on pw change, tests |
| 4 | MFA | 200,000 | 2.3 | 0 | ≥4.5 | Rate limits, test_mfa_routes.py, MFA challenge table |
| 5 | Authorization | 666,667 | 1.1 | 0 | ≥4.5 | test_tier_gate.py, test_feature_flags.py |
| 6 | Data Layer ★ | 64,748 | 3.0 | 0 | ≥4.5 | Idempotent drops, regex guards, schema sync, phantom removed |
| 7 | Payment ★ | 500,000 | 1.5 | 0 | ≥4.5 | test_payment.py, @api_error_handler, defense-in-depth |
| 8 | Classroom & LTI | 351,351 | 1.9 | 26,316 | ~3.4 | LTI error handling, @api_error_handler, tests (LTI tests missing) |
| 9 | GDPR | 333,333 | 1.9 | 0 | ≥4.5 | Error handling, regex guards, retention cleaned, tests |
| 10 | Observability ★ | 171,429 | 2.4 | 0 | ≥4.5 | Dead loggers, crash handler, alert catch broadened |
| 11 | Admin | 416,667 | 1.6 | 0 | ≥4.5 | @api_error_handler, test_admin_routes.py |
| 12 | Configuration | 274,510 | 2.1 | 0 | ≥4.5 | Env centralized, .env.example, dead import |
| 13 | Testing & CI | 1,000,000 | 0 | 0 | ≥4.5 | CI gates, pre-commit, coverage floor, property tests, doc drift |
| 14 | Marketing | 153,846 | 2.5 | 0 | ≥4.5 | Rate limits, @api_error_handler on feedback |
| 15 | Documentation | 444,444 | 1.7 | 0 | ≥4.5 | All counts accurate, quality docs, schema version |

★ = Core CTQ (user's primary target)

**Pre-fix composite: ~2.1σ → Round 7 composite: ~4.5σ** (1 defect / 780 opportunities = 1,282 DPMO)

**Core CTQs: 0 defects / 596 opportunities = 0 DPMO → ≥4.5σ** ✓

---

## 3. Vital-Few Initiatives

Ranked by DPMO reduction. Only PARTIAL or MISSING items. Max 10.

| # | Initiative | CTQ Link | Remaining DPMO Impact | Effort | Dependencies | Done When |
|---|-----------|----------|----------------------|--------|--------------|-----------|
| 1 | ~~Write `test_payment.py`~~ | Regression rate, Error-to-crash | Payment 500K → ~100K DPMO | 1 day | Mock Stripe SDK | **DONE** — 21 tests, 85% coverage |
| 2 | ~~Write `test_mfa_routes.py`~~ | Grading credibility (trust proxy) | MFA residual 67K → ~17K | 1 day | Flask test client | **DONE** — 18 tests, 83% coverage |
| 3 | ~~Write `test_classroom_routes.py`~~ | Session completion (classroom users) | Classroom 270K → ~50K | 1 day | Flask test client | **DONE** — 37 tests, 76% coverage |
| 4 | ~~Add completion rate by segment~~ | Session completion rate (KPI-2) | Enables KPI-2 measurement | 0.5 day | None | **DONE** — `_completion_by_segment()` in metrics_report.py |
| 5 | ~~Add crash rate calculation~~ | Error-to-crash ratio (CTQ) | Enables CTQ measurement | 0.5 day | crash_log populated | **DONE** — `_crash_rate()` in metrics_report.py |
| 6 | ~~Sync schema.sql with migrations~~ | Regression rate | Data Layer residual drift | 0.5 day | Know all 40 table DDLs | **DONE** — 40 CREATE TABLE statements |
| 7 | ~~Move MFA tokens to DB table~~ | Error-to-crash (multi-worker) | JWT residual 55K → ~25K | 1 day | Migration V25 | **DONE** — `mfa_challenge` table (V25), `_mfa_tokens` dict removed |
| 8 | ~~Centralize remaining env reads~~ | Confusing-state rate | Config residual 42K → ~10K | 0.5 day | None | **DONE** — 0 os.environ outside settings.py |
| 9 | ~~Activate dead loggers~~ | Error-to-crash ratio | Observability residual 44K → ~15K | 0.5 day | None | **DONE** — 8 removed, 2 activated |
| 10 | ~~Create AUDIT_LOG.md~~ | Regression rate (measurement cadence) | Documentation drift | 0.25 day | None | **DONE** — 4 entries with composite σ |

---

## 4. 30/60/90 Plan — Remaining Deliverables Only

### Days 1-30 (by 2026-03-27)

| Week | Deliverable | Measurable Outcome | Owner | Status |
|------|------------|-------------------|-------|--------|
| 1 | `test_payment.py` | 10+ tests pass; Payment σ ≥ 2.5 | Jason | **DONE** (21 tests) |
| 1 | `test_mfa_routes.py` | 10+ tests pass; MFA σ ≥ 3.5 | Jason | **DONE** (18 tests) |
| 1 | `test_classroom_routes.py` | 12+ tests pass; Classroom σ ≥ 3.0 | Jason | **DONE** (37 tests) |
| 2 | Completion rate by segment in `metrics_report.py` | KPI-2 reports rate per session_type + HSK band | Jason | **DONE** |
| 2 | Crash rate in `metrics_report.py` | KPI-5 reports crashes / requests for trailing 7 days | Jason | **DONE** |
| 3 | MFA tokens → DB (migration V25) | Multi-worker MFA works; `_mfa_tokens` dict deleted | Jason | **DONE** |
| 3 | Sync `schema.sql` with migrations | 40 CREATE TABLE statements match migration output | Jason | **DONE** |
| 4 | Centralize env var reads | 0 `os.environ.get` outside `settings.py` | Jason | **DONE** |
| 4 | Activate dead loggers | 0 files with unused logger | Jason | **DONE** |
| 4 | Create `AUDIT_LOG.md` | File exists with baseline entry | Jason | **DONE** |

**30-day gate:** ~~996+ tests → 1050+~~ **1119 tests achieved**. ~~Composite σ ≥ 3.3~~ **3.6σ achieved**. All 7 KPIs measurable via `./run metrics`. **10/10 deliverables complete. 30-day plan fully shipped.**

### Days 31-60 (by 2026-04-26)

| Deliverable | Measurable Outcome |
|------------|-------------------|
| Raise `fail_under` to 60% | CI enforces 60% coverage floor |
| Add completion rate by segment to admin dashboard | Admin Sessions tab shows rate by drill modality |
| Funnel report (signup → first session → week-2 retained) | `./run metrics` outputs funnel conversion rates |
| Property-based tests for SRS engine | 20+ hypothesis tests in `test_srs_property.py` |
| Contract tests for Stripe API boundary | Mock validates request shapes match Stripe SDK types |

**60-day gate:** Coverage ≥ 60%. Composite σ ≥ 3.6. Funnel KPI live.

### Days 61-90 (by 2026-05-26)

| Deliverable | Measurable Outcome |
|------------|-------------------|
| Raise `fail_under` to 70% | CI enforces 70% coverage floor |
| Contract tests for Resend email API | Mock validates email shape/recipient |
| Automated doc drift detection in CI | CI job fails if BUILD_STATE.md counts don't match actual |
| First monthly quality review using AUDIT_LOG.md | Entry logged with composite σ and delta |
| Revenue KPI (MRR from Stripe) | `./run metrics` outputs MRR, conversion rate |

**90-day gate:** Coverage ≥ 70%. Composite σ ≥ 3.8. All CTQs measured. AUDIT_LOG.md has 3 monthly entries.

---

## 5. Backlog — PR-Sized Tickets

Each ticket is one PR. Acceptance criteria are pass/fail.

---

### ~~TICKET-01: test_payment.py — Stripe checkout/webhook/portal tests~~ DONE
**Priority:** P1 | **Effort:** 1 day | **Blocks:** TICKET-11

**Scope:**
- Mock `stripe.checkout.Session.create` → verify URL returned
- Mock webhook with valid signature → verify subscription_tier updated
- Mock webhook with invalid signature → verify 400
- Mock `stripe.billing_portal.Session.create` → verify redirect URL
- Test `create_classroom_checkout` with 5/25/100 students
- Test status endpoint returns current tier

**Acceptance:**
- [ ] 10+ tests in `tests/test_payment.py`
- [ ] All tests pass on 3.9 and 3.12
- [ ] No real Stripe API calls (all mocked)

---

### ~~TICKET-02: test_mfa_routes.py — MFA HTTP-level tests~~ DONE
**Priority:** P1 | **Effort:** 1 day | **Blocks:** TICKET-11

**Scope:**
- `GET /api/mfa/status` returns `{enabled: false}` for new user
- `POST /api/mfa/setup` returns secret + provisioning URI
- `POST /api/mfa/verify-setup` with valid TOTP → enables MFA
- `POST /api/mfa/verify-setup` with invalid TOTP → 400
- `POST /api/mfa/disable` with valid code → disables MFA
- `POST /api/mfa/disable` with invalid code → 400
- Rate limit enforcement (5/hr disable, 10/hr setup)

**Acceptance:**
- [ ] 10+ tests in `tests/test_mfa_routes.py`
- [ ] All tests pass on 3.9 and 3.12
- [ ] Rate limit tests verify 429 response

---

### ~~TICKET-03: test_classroom_routes.py — Classroom flow tests~~ DONE
**Priority:** P1 | **Effort:** 1 day | **Blocks:** TICKET-11

**Scope:**
- Teacher creates classroom → 201 + classroom_id
- Teacher lists classrooms → includes new classroom
- Student joins classroom → 200
- Teacher views students → includes joined student
- Student cannot access teacher-only routes → 403
- Teacher invites bulk with valid/invalid emails
- Teacher archives classroom → no longer listed
- Teacher views classroom analytics

**Acceptance:**
- [ ] 12+ tests in `tests/test_classroom_routes.py`
- [ ] All tests pass on 3.9 and 3.12
- [ ] Role enforcement tested (student vs teacher)

---

### ~~TICKET-04: Completion rate by segment in metrics_report.py~~ DONE
**Priority:** P2 | **Effort:** 0.5 day | **Blocks:** None

**Scope:**
- Add `report_completion_rate_by_segment(conn, days=7)` to `metrics_report.py`
- Segments: session_type, HSK level band (1-3, 4-6, 7-9)
- Exclude sessions < 30 seconds
- Output: table with segment, total, completed, rate

**Acceptance:**
- [ ] `./run metrics` outputs completion rate per segment
- [ ] Rate matches manual SQL query against test data
- [ ] Sessions < 30s excluded

---

### ~~TICKET-05: Crash rate in metrics_report.py~~ DONE
**Priority:** P2 | **Effort:** 0.5 day | **Blocks:** None

**Scope:**
- Add `report_crash_rate(conn, days=7)` to `metrics_report.py`
- Numerator: `COUNT(*) FROM crash_log WHERE timestamp > ?`
- Denominator: line count of `app.log` in same period (or `COUNT(*) FROM session_log` as proxy)
- Output: crash count, total requests, rate, top 3 error_types

**Acceptance:**
- [ ] `./run metrics` outputs crash rate
- [ ] Top error_types shown with counts
- [ ] Works with zero crashes (outputs "0 crashes")

---

### ~~TICKET-06: MFA tokens → DB (migration V25)~~ DONE
**Priority:** P2 | **Effort:** 1 day | **Blocks:** TICKET-07

**Scope:**
- Create `mfa_challenge` table: `id, user_id, token_hash, challenge_type, expires_at, created_at`
- Index on `(user_id, expires_at)`
- Replace `_mfa_tokens` dict in `token_routes.py` with DB reads/writes
- Hash token before storing (SHA-256)
- Delete expired challenges on every read
- Delete challenge on successful verify

**Acceptance:**
- [ ] Migration V25 in `db/core.py`, SCHEMA_VERSION = 25
- [ ] `_mfa_tokens` dict deleted from `token_routes.py`
- [ ] Existing MFA tests still pass
- [ ] New test: token persists across simulated worker restart

---

### ~~TICKET-07: Sync schema.sql with migrations~~ DONE
**Priority:** P3 | **Effort:** 0.5 day | **Blocks:** None

**Scope:**
- Add 10 missing tables to `schema.sql`: `schema_version`, `feature_flag`, `rate_limit`, `retention_policy`, `invite_code`, `push_token`, `lti_platform`, `classroom`, `classroom_student`, `lti_user_mapping`
- If TICKET-06 is done, also add `mfa_challenge`
- Verify total CREATE TABLE count = actual table count

**Acceptance:**
- [ ] `grep -c "CREATE TABLE" schema.sql` matches table count in BUILD_STATE.md
- [ ] Fresh `init_db()` + all migrations produces same schema as `schema.sql` direct execution

---

### ~~TICKET-08: Centralize env var reads in settings.py~~ DONE
**Priority:** P3 | **Effort:** 0.5 day | **Blocks:** None

**Scope:**
- Move these to `settings.py`: `ALERT_WEBHOOK_URL` (security.py), `ADMIN_EMAIL` (security.py), `SESSION_TIMEOUT_MINUTES` (__init__.py), `FLASK_ENV` (__init__.py), `PORT` (server.py), `CRASH_LOG`/`APP_LOG` paths (log_config.py)
- Update consumers to `from mandarin.settings import X`
- Keep safe defaults

**Acceptance:**
- [ ] `grep -r "os.environ" mandarin/ --include="*.py" | grep -v settings.py | grep -v venv` returns 0 lines
- [ ] All existing tests pass
- [ ] `.env.example` still documents all vars

---

### ~~TICKET-09: Activate dead loggers~~ DONE
**Priority:** P3 | **Effort:** 0.5 day | **Blocks:** None

**Scope:**
- 10 files declare `logger = logging.getLogger(__name__)` but never call `logger.*`
- For each: add `logger.error(...)` or `logger.warning(...)` at appropriate error/exception paths
- If no error paths exist, remove the unused logger declaration

**Acceptance:**
- [ ] `grep -l "getLogger(__name__)" mandarin/ -r | while read f; do grep -qP "logger\.(debug|info|warning|error|critical)" "$f" || echo "$f"; done` returns 0 files
- [ ] All existing tests pass

---

### ~~TICKET-10: Create AUDIT_LOG.md~~ DONE
**Priority:** P3 | **Effort:** 0.25 day | **Blocks:** None

**Scope:**
- Create `docs/quality/AUDIT_LOG.md`
- Record baseline entry: date 2026-02-25, pre-fix 2.1σ, post-fix 2.9σ, delta +0.8σ
- Define format: `| Date | Composite DPMO | Sigma | Delta | Notes |`
- One entry per monthly measurement

**Acceptance:**
- [ ] File exists with header + baseline row
- [ ] Format matches OPERATING_SYSTEM.md weekly review output expectations

---

### TICKET-11: Raise coverage floor to 60%
**Priority:** P2 | **Effort:** 0.25 day | **Blocks:** TICKET-01, TICKET-02, TICKET-03

**Scope:**
- Change `fail_under = 50` → `fail_under = 60` in `pyproject.toml`
- Verify CI still passes after TICKET-01/02/03 tests are merged

**Acceptance:**
- [ ] `pyproject.toml` has `fail_under = 60`
- [ ] `pytest --cov=mandarin --cov-fail-under=60` passes locally
- [ ] CI green

---

### TICKET-12: Funnel report — signup → session → retained
**Priority:** P2 | **Effort:** 1 day | **Blocks:** None

**Scope:**
- Add `report_funnel(conn, days=30)` to `metrics_report.py`
- Stage 1: users with `lifecycle_event` type = 'signup' in period
- Stage 2: subset with at least 1 `session_log` row where `items_completed > 0`
- Stage 3: subset with session in days 8-14 after signup
- Output: count per stage, conversion rate between stages

**Acceptance:**
- [ ] `./run metrics` outputs 3-stage funnel
- [ ] Rates are percentages, not raw counts
- [ ] Works with 0 signups (outputs "No signups in period")

---

### TICKET-13: Property-based tests for SRS engine
**Priority:** P3 | **Effort:** 1 day | **Blocks:** None

**Scope:**
- Add `hypothesis` to dev dependencies
- Write `tests/test_srs_property.py`
- Properties: interval always positive, difficulty bounded [1.0, 5.0], ease factor bounded [1.3, 3.0], interval increases on correct answer, interval resets on lapse
- Generate random review sequences and verify invariants

**Acceptance:**
- [ ] 20+ hypothesis tests pass
- [ ] No invariant violations found in 10K+ examples
- [ ] `hypothesis` added to requirements or pyproject.toml dev deps

---

### TICKET-14: Contract tests for Stripe API boundary
**Priority:** P3 | **Effort:** 1 day | **Blocks:** None

**Scope:**
- Write `tests/test_stripe_contract.py`
- Verify all `stripe.*` calls in `payment.py` use correct parameter names
- Verify webhook event parsing matches expected Stripe event structure
- Use `unittest.mock.patch` on `stripe` module
- Assert request kwargs match Stripe SDK type signatures

**Acceptance:**
- [ ] 8+ contract tests pass
- [ ] Every `stripe.*` call site in `payment.py` has a corresponding contract test
- [ ] No real Stripe API calls

---

### TICKET-15: Admin dashboard — completion rate by segment tab
**Priority:** P3 | **Effort:** 0.5 day | **Blocks:** TICKET-04

**Scope:**
- Add `GET /api/admin/completion-rate` to `admin_routes.py`
- Returns JSON: `[{segment, total, completed, rate}]`
- Add "Completion Rate" tab to admin.html
- Table with segment name, total sessions, completed, rate % with color coding

**Acceptance:**
- [ ] Endpoint returns valid JSON with rate per segment
- [ ] Admin dashboard shows new tab
- [ ] Rate < 60% shown in red, 60-75% yellow, > 75% green

---

### TICKET-16: Doc drift detection in CI
**Priority:** P3 | **Effort:** 0.5 day | **Blocks:** None

**Scope:**
- Add CI job `doc-check` to `test.yml`
- Script checks: table count in BUILD_STATE.md matches `grep -c "CREATE TABLE" schema.sql`
- Script checks: test file count in BUILD_STATE.md matches `ls tests/test_*.py | wc -l`
- Fail if mismatch

**Acceptance:**
- [ ] CI job runs on every PR
- [ ] Intentionally wrong count causes CI failure
- [ ] Current counts pass
