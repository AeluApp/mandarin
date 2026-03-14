# Subsystem Map

> Updated: 2026-02-26 | Schema V25 | 15 subsystems | 80+ source files | 1244 tests across 57 suites

Every production source file is assigned to exactly one subsystem. Test files map to the subsystem they exercise.

---

## 1. Routing & Request Handling

Core HTTP dispatch, error formatting, CSRF enforcement, rate limiting setup.

| File | Role |
|------|------|
| `mandarin/web/routes.py` | 44 API/WS endpoints (core app) |
| `mandarin/web/landing_routes.py` | 19 static marketing pages |
| `mandarin/web/api_errors.py` | `@api_error_handler` decorator, error builders |
| `mandarin/web/__init__.py` | App factory, CSRF, rate limits, 500 handler |
| `mandarin/web/server.py` | Gunicorn/dev server entry |
| `mandarin/web/wsgi.py` | WSGI entry point |

**Tests:** `test_web_routes.py`, `test_web_parity.py`, `test_api_error_handler.py`, `test_security_headers.py`

---

## 2. Authentication (Session-Based)

Flask-Login session auth, registration, password reset, email verification.

| File | Role |
|------|------|
| `mandarin/auth.py` | `create_user`, `authenticate`, password reset tokens |
| `mandarin/web/auth_routes.py` | 9 routes: login, register, logout, forgot/reset password, verify email, unsubscribe, change password |
| `mandarin/cli_auth.py` | CLI credential file (~/.mandarin/auth.json) |

**Tests:** `test_auth.py` (47 tests)

---

## 3. Authentication (JWT)

Stateless JWT for mobile/API clients, refresh token rotation.

| File | Role |
|------|------|
| `mandarin/jwt_auth.py` | Token encode/decode, refresh token store/validate/revoke |
| `mandarin/web/token_routes.py` | 4 routes: obtain, MFA challenge, refresh, revoke |

**Tests:** `test_jwt_auth.py` (23 tests), `test_token_routes.py` (27 tests)

---

## 4. MFA (Multi-Factor Authentication)

TOTP setup/verify/disable, backup codes.

| File | Role |
|------|------|
| `mandarin/mfa.py` | TOTP generation, verification, backup code logic |
| `mandarin/web/mfa_routes.py` | 4 routes: status, setup, verify-setup, disable |

**Tests:** `test_mfa.py` (17 unit tests), `test_mfa_routes.py` (18 HTTP tests)

---

## 5. Authorization & Tier Gating

Subscription tier enforcement, feature flags, admin checks.

| File | Role |
|------|------|
| `mandarin/tier_gate.py` | `check_tier_access()` — gate by subscription tier |
| `mandarin/feature_flags.py` | Rollout % flags, `is_enabled()` |

**Tests:** `test_tier_gate.py` (13 tests), `test_feature_flags.py` (20 tests)

---

## 6. Data Layer & Migrations

SQLite connection management, schema migrations, SRS engine, content queries.

| File | Role |
|------|------|
| `mandarin/db/__init__.py` | Package init, public API |
| `mandarin/db/core.py` | Connection factory, 24 migrations, indexes, views |
| `mandarin/db/content.py` | Content item CRUD, due items, context notes |
| `mandarin/db/curriculum.py` | Grammar/skill queries, HSK coverage |
| `mandarin/db/profile.py` | Learner profile read |
| `mandarin/db/progress.py` | SRS engine, mastery stages, error focus |
| `mandarin/db/session.py` | Session lifecycle, history, error summary |
| `schema.sql` | Greenfield schema (41 tables) |

**Tests:** `test_hardening.py`, `test_integration.py`, `test_srs_decomposition.py`, `test_mastery_stages.py`, `test_edge_cases.py`, `test_retention.py`, `test_retention_property.py`, `test_srs_property.py`, `test_data_retention.py`

---

## 7. Payment & Billing

Stripe checkout, webhooks, billing portal, subscription status.

| File | Role |
|------|------|
| `mandarin/payment.py` | Stripe API calls, webhook handler |
| `mandarin/web/payment_routes.py` | 5 routes: checkout, classroom checkout, billing portal, webhook, status |

**Tests:** `test_payment.py` (21 tests), `test_web_routes.py` (error paths)

---

## 8. Classroom & LTI

Teacher/student classroom management, LTI 1.3 integration.

| File | Role |
|------|------|
| `mandarin/web/classroom_routes.py` | 8 routes: create, list, join, students, analytics, invite, archive |
| `mandarin/web/lti_routes.py` | 4 routes: OIDC login, launch, grade passback, JWKS |

**Tests:** `test_classroom_routes.py` (37 tests)

---

## 9. GDPR & Data Retention

Data export, account deletion, automated retention purge.

| File | Role |
|------|------|
| `mandarin/web/gdpr_routes.py` | 2 routes: export, delete |
| `mandarin/data_retention.py` | Retention policy engine, purge logic |
| `mandarin/export.py` | Data export formatting |

**Tests:** `test_gdpr_routes.py` (10 tests)

---

## 10. Observability & Logging

Structured logging, crash tracking, client error collection, security audit trail.

| File | Role |
|------|------|
| `mandarin/log_config.py` | Formatters, handlers, crash.log wiring |
| `mandarin/security.py` | Security event logging, alert delivery |
| `mandarin/web/rate_limit_store.py` | SQLite rate limiter backend |
| `mandarin/web/session_store.py` | WebSocket session resume store |

**Tests:** `test_logging.py` (15 tests), `test_security_events.py` (10 tests), `test_metrics_report.py` (66 tests)

---

## 11. Admin Dashboard

Admin-only metrics, user management, observability views.

| File | Role |
|------|------|
| `mandarin/web/admin_routes.py` | 9 routes: metrics, users, feedback, crashes, client errors, sessions, security, error patterns |
| `mandarin/web/templates/admin.html` | 6-tab dashboard UI |

**Tests:** `test_admin_routes.py` (37 tests)

---

## 12. Configuration

Environment variables, startup validation, feature toggles.

| File | Role |
|------|------|
| `mandarin/settings.py` | All env var reads + `validate_production_config()` |
| `mandarin/config.py` | Runtime config constants |
| `.env.example` | Documented env vars for operators |

**Tests:** `test_config.py` (9 tests)

---

## 13. Testing & CI Infrastructure

Test framework, fixtures, CI pipelines, linting config.

| File | Role |
|------|------|
| `tests/conftest.py` | `test_db` fixture, `OutputCapture`, `InputSequence` |
| `pyproject.toml` | pytest, coverage, ruff config |
| `.github/workflows/test.yml` | PR test gate |
| `.github/workflows/deploy.yml` | Test + deploy to Fly.io |
| `.github/workflows/security.yml` | SBOM + bandit SAST |
| `.github/workflows/dast.yml` | OWASP ZAP baseline scan |
| `.github/workflows/dr-test.yml` | Weekly DR test |

---

## 14. Onboarding & Marketing

New user wizard, placement quiz, affiliates, referrals, feedback, subscription lifecycle.

| File | Role |
|------|------|
| `mandarin/web/onboarding_routes.py` | 6 routes: wizard, level, goal, complete, placement start/submit |
| `mandarin/web/marketing_routes.py` | 9 routes: referral track/signup/link/stats, discount validate/apply, cancel/pause/resume, feedback |
| `mandarin/marketing_hooks.py` | Lifecycle event logging |
| `mandarin/placement.py` | Placement quiz generation + scoring |
| `mandarin/churn_detection.py` | Churn risk scoring |

**Tests:** Partial coverage via `test_web_routes.py`

---

## 15. Documentation

Architecture docs, security policy, brand guide, operational runbooks.

| File | Role |
|------|------|
| `BUILD_STATE.md` | Architecture, schema, module inventory |
| `SECURITY.md` | Security controls, threat model |
| `SOURCES.md` | Data sources and attribution |
| `BRAND.md` | Visual identity guide |
| `docs/multi-region.md` | Multi-region deployment |
| `docs/polish_notes.md` | QA checklist |
| `docs/vendor-migration.md` | Vendor migration plan |
| `docs/operations/rollback-procedure.md` | Rollback runbook |

---

## Unmapped Utility Files

These files provide shared functionality and are counted under the subsystem of their primary consumer:

| File | Primary Consumer |
|------|-----------------|
| `mandarin/web/bridge.py` | Routing (WebSocket drill bridge) |
| `mandarin/web/push.py` | Routing (push notification delivery) |
| `mandarin/web/email_scheduler.py` | Marketing (drip email scheduling) |
| `mandarin/web/retention_scheduler.py` | GDPR & Data Retention |
| `mandarin/web/sync_routes.py` | Routing (3 offline sync routes) |
| `mandarin/runner.py` | Routing (session runner for WS) |
| `mandarin/conversation.py` | Data Layer (dialogue engine) |
| `mandarin/diagnostics.py` | Data Layer (diagnostic reports) |
| `mandarin/reports.py` | Data Layer (report generation) |
| `mandarin/media.py` | Routing (media recommendations) |
| `mandarin/importer.py` | Data Layer (content import) |
| `mandarin/validator.py` | Data Layer (content validation) |
| `mandarin/xapi.py` | Routing (xAPI statement export) |
| `mandarin/caliper.py` | Routing (Caliper event export) |
| `mandarin/cc_export.py` | Routing (Common Cartridge export) |
| `mandarin/drills/*.py` | Data Layer (drill logic) |
| `mandarin/personalization.py` | Routing (user preferences) |
| `mandarin/milestones.py` | Routing (achievement tracking) |
| `mandarin/improve.py` | Data Layer (self-improvement engine) |
