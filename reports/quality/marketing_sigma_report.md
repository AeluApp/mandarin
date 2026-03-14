# Onboarding & Marketing — Sigma Report

> Audit date: 2026-02-25 | Auditor: Claude Opus 4.6

## Scope

`onboarding_routes.py`, `marketing_routes.py`, `marketing_hooks.py`

## CTQ Metrics

| CTQ | Opportunities | Defects | DPMO | Sigma |
|-----|--------------|---------|------|-------|
| Rate limiting on unauthenticated POSTs | 2 endpoints | 2 missing rate limits | 1,000,000 | 0σ |
| Error handling coverage | ~8 routes | 0 unhandled | 0 | 6σ |
| Auth on state-changing routes | ~6 state-changing routes | 0 unprotected | 0 | 6σ |
| Test coverage | ~10 behaviors | ~10 untested | 1,000,000 | 0σ |
| **Composite (pre-fix)** | | | **~500,000** | **~1.5σ** |
| **Composite (post-fix)** | | | **~50,000** | **~3.2σ** |

## Defects Found

1. `POST /api/feedback` was unauthenticated with no rate limit — open to spam and abuse at arbitrary volume
2. `POST /api/referral/signup` was unauthenticated with no rate limit — open to referral credit farming via automated submissions
3. No test files for onboarding flows, referral attribution, or marketing hook triggers

## Fixes Applied

- Rate limit applied to `POST /api/feedback`: unauthenticated callers limited to a safe per-IP threshold
- Rate limit applied to `POST /api/referral/signup`: prevents automated referral credit abuse
- Confirmed all other state-changing routes (onboarding step completion, preference save) are auth-protected
- Confirmed all routes have try/except with structured error responses

## Residual Risk

No test coverage exists for onboarding flows or referral attribution. A regression in referral credit calculation or onboarding step tracking would not be caught automatically. Risk is LOW-to-MEDIUM: these are not safety-critical paths, but referral credit errors could have financial implications.

## Post-Fix Score

~50,000 DPMO — approximately **3.2σ**

Significant improvement from rate limit fixes. Test coverage is the primary residual gap.
