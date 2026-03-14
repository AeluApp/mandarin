# CTQ (Critical-to-Quality) Registry

> Re-audited: 2026-02-26 (Round 7) | Measurement methodology: defect opportunities per subsystem | Expanded dimensions

Each CTQ defines a measurable quality characteristic. **Numerator** = defects found at audit. **Denominator** = total opportunities. **DPMO** = (defects / opportunities) × 1,000,000. Sigma from standard Z-table.

Notation: **[FIXED R1-R6]** = defect was present at baseline and fixed in rounds 1-6. Current count reflects code as-audited.

---

## 1. Routing & Request Handling ★ CORE

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Structured error handling (`@api_error_handler`) on all API routes | 0 | 44 | 0 | 6σ |
| Safe JSON parsing (`get_json(silent=True)`) on all POST endpoints | 0 | 44 | 0 | 6σ |
| All SQL parameterized (no f-string user input) | 0 | 44 | 0 | 6σ |
| CSRF protection on all state-changing routes | 0 | 35 | 0 | 6σ |
| Security response headers on all responses | 0 | 6 | 0 | 6σ |
| WebSocket authentication enforced | 0 | 1 | 0 | 6σ |

**Composite: 0 defects / 174 opportunities = 0 DPMO → ≥4.5σ**

---

## 2. Authentication (Session) ★ CORE

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Session fixation protection (`session.clear()` before `login_user()`) | 0 [FIXED R1] | 3 login sites | 0 | 6σ |
| Account lockout bypass protection (malformed `locked_until` → deny) | 0 [FIXED R1] | 1 | 0 | 6σ |
| All auth events logged (security_audit_log) | 0 | 12 event types | 0 | 6σ |
| Error handling on all auth routes | 0 | 9 routes | 0 | 6σ |
| Password hashing explicit (`method="pbkdf2:sha256"`) | 0 [FIXED R1] | 5 call sites | 0 | 6σ |
| Secure cookie flags (HttpOnly, SameSite, Secure) | 0 | 4 flags | 0 | 6σ |
| Open redirect prevention (validated `next` param) | 0 | 2 redirect sites | 0 | 6σ |
| Input validation (email format, password length + common list) | 0 | 3 checks | 0 | 6σ |

**Composite: 0 defects / 39 opportunities = 0 DPMO → ≥4.5σ**

---

## 3. Authentication (JWT) ★ CORE

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Algorithm restriction (`algorithms=["HS256"]`) on all decode sites | 0 | 2 | 0 | 6σ |
| Refresh token expiry enforced (malformed → reject) | 0 [FIXED R1] | 1 | 0 | 6σ |
| MFA tokens work cross-worker (DB-backed via `mfa_challenge` table) | 0 [FIXED R4] | 1 | 0 | 6σ |
| Test coverage (jwt_auth + token_routes) | 0 [FIXED R1+R3] | 2 files | 0 | 6σ |
| Error handling on all token routes | 0 | 4 routes | 0 | 6σ |
| Token rotation on credential change (refresh revoked on pw change) | 0 [FIXED R7] | 2 paths | 0 | 6σ |
| Rate limiting on auth endpoints | 0 | 4 endpoints | 0 | 6σ |

**Composite: 0 defects / 16 opportunities = 0 DPMO → ≥4.5σ**

---

## 4. MFA

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Rate limiting on MFA endpoints | 0 [FIXED R1] | 4 endpoints | 0 | 6σ |
| Error handling on all MFA routes | 0 | 4 routes | 0 | 6σ |
| Security event coverage (MFA_ENABLED, MFA_DISABLED, MFA_FAILED) | 0 | 3 event types | 0 | 6σ |
| Test coverage (HTTP-level) | 0 [FIXED R2] | 1 file | 0 | 6σ |

**Composite: 0 defects / 12 opportunities = 0 DPMO → ≥4.5σ**

---

## 5. Authorization & Tier Gating

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Access denial logged | 0 | 1 | 0 | 6σ |
| Tier gate test coverage | 0 [FIXED R1] | 1 file (13 tests) | 0 | 6σ |
| Feature flag rollout tested (deterministic hash bucketing) | 0 [FIXED R4] | 1 file (20 tests) | 0 | 6σ |

**Composite: 0 defects / 3 opportunities = 0 DPMO → ≥4.5σ**

---

## 6. Data Layer & Migrations ★ CORE

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| All SQL parameterized (no user input in f-strings) | 0 | ~200 execute() calls | 0 | 6σ |
| F-string SQL has regex validation guard | 0 [FIXED R1] | 14 f-string sites | 0 | 6σ |
| Migrations idempotent (IF EXISTS on all DROPs) | 0 [FIXED R1] | 12 DROP statements | 0 | 6σ |
| schema.sql matches migrations (41 tables) | 0 [FIXED R3] | 41 tables | 0 | 6σ |
| WAL + FK + busy_timeout enabled | 0 | 4 pragmas | 0 | 6σ |
| Retention scheduler active (purge logic runs) | 0 | 1 | 0 | 6σ |
| No phantom retention entries | 0 [FIXED R5] | 7 policies | 0 | 6σ |

**Composite: 0 defects / 279 opportunities = 0 DPMO → ≥4.5σ**

---

## 7. Payment & Billing ★ CORE

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Webhook signature verified (Stripe sig check) | 0 | 1 | 0 | 6σ |
| Error handling on all routes (try/except) | 0 | 5 routes | 0 | 6σ |
| `@api_error_handler` on all routes | 0 [FIXED R4] | 5 routes | 0 | 6σ |
| Test coverage (success + error paths) | 0 [FIXED R2] | 1 file (26 tests) | 0 | 6σ |
| Defense-in-depth (both decorator + try/except) | 0 | 5 routes | 0 | 6σ |

**Composite: 0 defects / 17 opportunities = 0 DPMO → ≥4.5σ**

---

## 8. Classroom & LTI

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Auth on all state-changing routes | 0 | 12 routes | 0 | 6σ |
| Error handling on all routes | 0 [FIXED R1] | 12 routes | 0 | 6σ |
| `@api_error_handler` on all routes | 0 [FIXED R4+R7] | 12 routes | 0 | 6σ |
| Test coverage — classroom flows | 0 [FIXED R2] | 1 file (37 tests) | 0 | 6σ |
| Test coverage — LTI flows | 1 | 1 required | 1,000,000 | ~0σ |

**Composite: 1 defect / 38 opportunities = 26,316 DPMO → ~3.4σ**

---

## 9. GDPR & Data Retention

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Error handling on GDPR routes | 0 [FIXED R1] | 2 routes | 0 | 6σ |
| SQL f-string guard consistency (regex on all sites) | 0 [FIXED R1] | 2 f-string sites | 0 | 6σ |
| Test coverage | 0 [FIXED R1] | 1 file (10 tests) | 0 | 6σ |
| No phantom retention entries | 0 [FIXED R5] | 7 policies | 0 | 6σ |

**Composite: 0 defects / 12 opportunities = 0 DPMO → ≥4.5σ**

---

## 10. Observability & Logging ★ CORE

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| No dead logger declarations | 0 [FIXED R3] | 66 files with logger | 0 | 6σ |
| crash.log handler wired (RotatingFileHandler at ERROR) | 0 | 1 | 0 | 6σ |
| 500 handler logs to DB (`_log_crash()`) | 0 | 1 | 0 | 6σ |
| Rate limiter fallback logged at WARNING+ | 0 [FIXED R1] | 1 | 0 | 6σ |
| Security event delivery catches all DB errors | 0 [FIXED R4] | 1 | 0 | 6σ |
| Structured JSON log format on all handlers | 0 | 1 | 0 | 6σ |

**Composite: 0 defects / 71 opportunities = 0 DPMO → ≥4.5σ**

---

## 11. Admin Dashboard

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Auth enforcement (admin_required + MFA) on all routes | 0 | 9 routes | 0 | 6σ |
| `@api_error_handler` on all API routes | 0 [FIXED R4] | 8 API routes | 0 | 6σ |
| Test coverage | 0 [FIXED R1] | 1 file (37 tests) | 0 | 6σ |
| SQL injection safety (f-string SQL safe) | 0 | 5 f-string sites | 0 | 6σ |

**Composite: 0 defects / 23 opportunities = 0 DPMO → ≥4.5σ**

---

## 12. Configuration

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| All env vars in settings.py (0 raw os.environ outside) | 0 [FIXED R3] | 22 env reads | 0 | 6σ |
| .env.example complete | 0 [FIXED R1] | 22 vars | 0 | 6σ |
| Production startup validation (fatal on insecure defaults) | 0 | 5 critical vars | 0 | 6σ |
| No dead imports in settings.py | 0 [FIXED R1] | 1 | 0 | 6σ |

**Composite: 0 defects / 50 opportunities = 0 DPMO → ≥4.5σ**

---

## 13. Testing & CI

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Coverage measured in CI (pytest-cov) | 0 [FIXED R1] | 1 | 0 | 6σ |
| Ruff lint in CI | 0 [FIXED R1] | 1 | 0 | 6σ |
| Pre-commit hooks exist | 0 [FIXED R1] | 1 | 0 | 6σ |
| Python version matrix (3.9 + 3.12) | 0 [FIXED R1] | 1 | 0 | 6σ |
| Coverage floor enforced (fail_under = 53) | 0 [FIXED R5] | 1 | 0 | 6σ |
| Business-critical modules all tested | 0 [FIXED R1-R5] | 4 modules | 0 | 6σ |
| Doc drift detection in CI | 0 [FIXED R5] | 1 | 0 | 6σ |
| Property-based tests for SRS invariants | 0 [FIXED R6] | 1 (33 tests) | 0 | 6σ |

**Composite: 0 defects / 11 opportunities = 0 DPMO → ≥4.5σ**

---

## 14. Onboarding & Marketing

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Auth on state-changing routes (intentional exceptions documented) | 0 | 9 POST routes | 0 | 6σ |
| Error handling on all routes | 0 | 15 routes | 0 | 6σ |
| Rate limiting on public POST endpoints | 0 [FIXED R1+R7] | 2 public routes | 0 | 6σ |

**Composite: 0 defects / 26 opportunities = 0 DPMO → ≥4.5σ**

---

## 15. Documentation

| CTQ | Numerator | Denominator | DPMO | σ |
|-----|-----------|-------------|------|---|
| Schema version current (V25) | 0 | 4 docs | 0 | 6σ |
| Table count accurate (41 tables) | 0 [FIXED R1+R7] | 2 docs | 0 | 6σ |
| Test count accurate (1244 tests, 57 suites) | 0 [FIXED R7] | 2 docs | 0 | 6σ |
| Quality docs populated | 0 [FIXED R1] | 1 | 0 | 6σ |

**Composite: 0 defects / 9 opportunities = 0 DPMO → ≥4.5σ**

---

## Overall Composite — Round 7 Re-Audit

### Core CTQs (target: 4.5σ+)

| Subsystem | Defects | Opportunities | DPMO | σ | Status |
|-----------|---------|---------------|------|---|--------|
| 1. Routing & Request Handling | 0 | 174 | 0 | ≥4.5σ | ✓ |
| 2. Auth (Session) | 0 | 39 | 0 | ≥4.5σ | ✓ |
| 3. Auth (JWT) | 0 | 16 | 0 | ≥4.5σ | ✓ |
| 6. Data Layer | 0 | 279 | 0 | ≥4.5σ | ✓ |
| 7. Payment | 0 | 17 | 0 | ≥4.5σ | ✓ |
| 10. Observability | 0 | 71 | 0 | ≥4.5σ | ✓ |

**Core composite: 0 defects / 596 opportunities = 0 DPMO → ≥4.5σ** ✓

### Full Composite (target: ~4.0σ)

| Subsystem | Defects | Opportunities | DPMO | σ |
|-----------|---------|---------------|------|---|
| 1. Routing | 0 | 174 | 0 | ≥4.5σ |
| 2. Auth (Session) | 0 | 39 | 0 | ≥4.5σ |
| 3. Auth (JWT) | 0 | 16 | 0 | ≥4.5σ |
| 4. MFA | 0 | 12 | 0 | ≥4.5σ |
| 5. Authorization | 0 | 3 | 0 | ≥4.5σ |
| 6. Data Layer | 0 | 279 | 0 | ≥4.5σ |
| 7. Payment | 0 | 17 | 0 | ≥4.5σ |
| 8. Classroom & LTI | 1 | 38 | 26,316 | ~3.4σ |
| 9. GDPR | 0 | 12 | 0 | ≥4.5σ |
| 10. Observability | 0 | 71 | 0 | ≥4.5σ |
| 11. Admin | 0 | 23 | 0 | ≥4.5σ |
| 12. Configuration | 0 | 50 | 0 | ≥4.5σ |
| 13. Testing & CI | 0 | 11 | 0 | ≥4.5σ |
| 14. Marketing | 0 | 26 | 0 | ≥4.5σ |
| 15. Documentation | 0 | 9 | 0 | ≥4.5σ |

**Full composite: 1 defect / 780 opportunities = 1,282 DPMO → ~4.5σ** ✓

### Remaining Defect

| ID | Subsystem | Description | Severity |
|----|-----------|-------------|----------|
| 8-LTI | Classroom & LTI | No `test_lti_routes.py` — LTI OIDC/JWT flows untested at HTTP level | Medium |

### Journey: 2.1σ → 4.5σ

| Round | Date | Tests | Composite DPMO | Sigma | Delta |
|-------|------|-------|---------------|-------|-------|
| Baseline | 2026-02-25 | 899 | ~350,000 | ~2.1σ | — |
| R1 | 2026-02-25 | 996 | ~120,000 | ~2.9σ | +0.8σ |
| R2 | 2026-02-26 | 1,072 | ~60,000 | ~3.2σ | +0.3σ |
| R3 | 2026-02-26 | 1,099 | ~40,000 | ~3.5σ | +0.3σ |
| R4 | 2026-02-26 | 1,119 | ~18,000 | ~3.6σ | +0.1σ |
| R5 | 2026-02-26 | 1,205 | ~10,000 | ~3.8σ | +0.2σ |
| R6 | 2026-02-26 | 1,244 | ~5,000 | ~4.1σ | +0.3σ |
| **R7** | **2026-02-26** | **1,244** | **1,282** | **~4.5σ** | **+0.4σ** |
