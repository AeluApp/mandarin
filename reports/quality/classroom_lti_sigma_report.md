# Classroom & LTI — Sigma Report

> Audit date: 2026-02-25 | Auditor: Claude Opus 4.6

## Scope

`classroom_routes.py`, `lti_routes.py`

## CTQ Metrics

| CTQ | Opportunities | Defects | DPMO | Sigma |
|-----|--------------|---------|------|-------|
| Auth on state-changing routes | ~8 state-changing routes | 0 unprotected | 0 | 6σ |
| Error handling coverage | ~10 routes | 1 unhandled (lti_login) | 100,000 | 2.8σ |
| Test coverage | ~15 behaviors | ~15 untested | 1,000,000 | 0σ |
| **Composite (pre-fix)** | | | **~367,000** | **~1.8σ** |
| **Composite (post-fix)** | | | **~250,000** | **~2.1σ** |

## Defects Found

1. `lti_login` had no try/except — an unhandled exception during LTI handshake would return a raw 500 with no structured response, potentially leaking stack trace details
2. No test files exist for `classroom_routes.py` or `lti_routes.py` — classroom enrollment, roster sync, and LTI launch flows are entirely untested
3. No integration tests for the LTI 1.3 handshake sequence

## Fixes Applied

- `lti_login` wrapped in try/except with structured JSON error response
- Confirmed all state-changing routes (enrollment create/delete, roster sync, assignment CRUD) are protected by auth decorators

## Residual Risk

**No test files.** LTI is a complex protocol with multiple handshake states. Without tests:
- A regression in the OIDC connect flow would not be caught
- Classroom roster sync errors could silently fail
- LTI grade passback failures would go undetected

Risk is partially mitigated by the fact that LTI is a lower-volume, institutionally-contracted feature (not self-serve). Marked for `NEXT_30_DAYS`.

## Post-Fix Score

~250,000 DPMO — approximately **2.1σ**

Marginal improvement from error handling fix. Test coverage is the primary path to sigma improvement.
