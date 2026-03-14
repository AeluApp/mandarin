# Fix Inventory

> Generated: 2026-02-25 | Updated: 2026-03-10
> Sorted by severity then DPMO impact

Each row is a specific defect with patch-level fix instructions. Status: **DONE** = fixed, **DEFER** = deferred with workaround, **NFN** = not fixable now with technical blocker.

---

## Critical Severity (Security / Data Loss Risk)

| ID | Subsystem | Defect | File:Line | Status |
|----|-----------|--------|-----------|--------|
| C1 | Auth (Session) | No session ID rotation on login — session fixation | `auth_routes.py` | DONE — `session.clear()` before `login_user()` |
| C2 | Auth (Session) | Account lockout bypass on malformed `locked_until` | `auth.py` | DONE — parse failure treated as still locked |
| C3 | Auth (JWT) | Refresh token expiry bypass on malformed DB date | `jwt_auth.py` | DONE — token rejected on parse failure |
| C4 | GDPR | `export_data()` has zero error handling | `gdpr_routes.py` | DONE — wrapped in try/except |
| C5 | GDPR | `request_deletion()` has zero error handling | `gdpr_routes.py` | DONE — wrapped in try/except |
| C6 | GDPR | Export SELECT f-string missing regex guard | `gdpr_routes.py` | DONE — table names from hardcoded allowlist |
| C7 | Marketing | `POST /api/feedback` unauthenticated + no rate limit | `marketing_routes.py` | DONE — rate limit 5/hour in `__init__.py` |
| C8 | Marketing | `POST /api/referral/signup` unauthenticated write | `marketing_routes.py` | DONE — rate limit 20/hour in `__init__.py` |
| C9 | Routing | `POST /api/media/comprehension/submit` missing auth check | `exposure_routes.py` | DONE — `_get_user_id()` enforces auth |

---

## High Severity (Reliability / Observability)

| ID | Subsystem | Defect | File:Line | Status |
|----|-----------|--------|-----------|--------|
| H1 | Auth (JWT) | `_mfa_tokens` was in-process memory dict | `token_routes.py` | DONE — moved to `mfa_challenge` DB table |
| H2 | Auth (JWT) | Zero test coverage | `jwt_auth.py` | DONE — 23 tests in `test_jwt_auth.py` |
| H3 | MFA | `POST /api/mfa/disable` missing specific rate limit | `__init__.py` | DONE — 5/hour rate limit |
| H4 | MFA | `POST /api/mfa/setup` missing specific rate limit | `__init__.py` | DONE — 10/hour rate limit |
| H5 | Observability | Rate limiter fallback logged at DEBUG | `__init__.py` | DONE — rate limit event at WARNING severity |
| H6 | Observability | CSRF/rate-limit security event logging catch-all | `__init__.py` | DONE — WARNING severity for security events |
| H7 | Auth (Session) | Logout security event silently swallowed | `auth_routes.py` | DONE — `logger.warning` on failure |
| H8 | Data Layer | 6 non-idempotent DROP TABLE in migrations | `db/core.py` | DONE — all use IF EXISTS |
| H9 | Data Layer | schema.sql missing migration-only tables | `schema.sql` | DONE — added grammar_progress, reading_progress, listening_progress, scheduler_lock, user_feedback |
| H10 | Routing | `sync_push` has no outer try/except | `sync_routes.py` | DONE — wrapped in try/except |
| H11 | Routing | `index()` has no error handling | `routes.py` | DONE — try/except with 500 fallback |
| H12 | Classroom | `lti_login` has no try/except | `lti_routes.py` | DONE — try/except with error logging |
| H13 | Testing | Coverage not measured in CI | `.github/workflows/test.yml` | DONE — pytest-cov with 55% floor |
| H14 | Testing | Ruff not run in CI | `.github/workflows/test.yml` | DONE — ruff check step added |
| H15 | Testing | CI uses Python 3.12, target is 3.9 | `.github/workflows/test.yml` | DONE — matrix: [3.9, 3.12] |
| H16 | Config | 7 env vars missing from .env.example | `.env.example` | DONE — all vars documented |
| H17 | Config | 6 env reads outside settings.py | Various | DONE — only 2 justified reads remain (SW_KILL, FLY_MACHINE_ID) |

---

## Medium Severity (Inconsistency / Code Quality)

| ID | Subsystem | Defect | File:Line | Status |
|----|-----------|--------|-----------|--------|
| M1 | Observability | Dead logger declarations in 2 files | `grammar_drills.py`, `number.py` | DONE — removed unused imports |
| M2 | Config | Dead `import logging` in settings.py | `settings.py` | DONE — removed |
| M3 | Data Layer | Phantom `drill_response` in retention_policy | Migration V20 | NFN — historical migration, entry harmlessly skipped at runtime |
| M4 | Documentation | BUILD_STATE.md incorrect table count | `BUILD_STATE.md:8` | DONE — updated to V42 (56 tables) |
| M5 | Documentation | SECURITY.md incorrect schema version / table count | `SECURITY.md` | DONE — updated to V42 (56 tables) |
| M6 | Documentation | BUILD_STATE.md test count | `BUILD_STATE.md:9` | DONE — reflects 1531 tests |
| M7 | Auth (Session) | `cli.py` missing `method=` on password hash | `cli.py` | DONE — `method="pbkdf2:sha256"` present |
| M8 | Security | `_send_critical_alert` only catches OperationalError | `security.py` | DONE — catches `Exception` for delivery, `sqlite3.Error` for DB |
| M9 | Auth (JWT) | Token revoke doesn't log LOGOUT security event | `token_routes.py` | DONE — LOGOUT event logged |
| M10 | Testing | No pre-commit hooks | Project root | DONE — `.pre-commit-config.yaml` with ruff + gitleaks |
| M11 | Scheduler | Tone errors mapped to "speaking" modality instead of "reading" | `scheduler.py:454` | DONE — changed to "reading" |
| M12 | Documentation | BUILD_STATE.md/SECURITY.md wrong schema version after V42 migration | `BUILD_STATE.md`, `SECURITY.md` | DONE — updated to V42 (56 tables) |

---

## Low Severity (Polish / Best Practice)

| ID | Subsystem | Defect | File:Line | Status |
|----|-----------|--------|-----------|--------|
| L1 | Admin | No `@api_error_handler` on admin routes | `admin_routes.py` | DONE — verified all `/api/admin/*` routes already have `@api_error_handler` |
| L2 | Payment | No `@api_error_handler` on payment routes | `payment_routes.py` | DONE — verified all payment API routes already have `@api_error_handler` |
| L3 | Data Layer | `_ensure_indexes` incomplete for ~15 tables | `db/core.py` | DONE — added 40 missing indexes to match schema.sql |
| L4 | Observability | Sentry init logged at WARNING on ImportError | `__init__.py` | DONE — changed to INFO level |

---

## Deferred Items — Technical Blockers

| ID | Blocker | Workaround |
|----|---------|-----------|
| M3 | Phantom `drill_response` retention policy — historical migration V20 can't be retroactively changed | Entry is harmlessly skipped at runtime |
| L1-L4 | ~~Low severity polish items~~ | DONE — all four resolved |
