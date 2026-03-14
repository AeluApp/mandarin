# Authentication (JWT) — Sigma Report

> Audit date: 2026-02-25 | Auditor: Claude Opus 4.6

## Scope

`jwt_auth.py`, `token_routes.py`

## CTQ Metrics

| CTQ | Opportunities | Defects | DPMO | Sigma |
|-----|--------------|---------|------|-------|
| Algorithm restriction | 1 decode site | 0 (HS256 explicit) | 0 | 6σ |
| Refresh token expiry enforcement | 1 expiry path | 1 bypass via malformed date | 1,000,000 | 0σ |
| MFA token persistence | 1 store | 1 in-memory (NFN) | 1,000,000 | 0σ |
| Token revocation logging | 1 revoke path | 0 | 0 | 6σ |
| Test coverage | ~20 behaviors | ~20 untested | 1,000,000 | 0σ |
| **Composite (pre-fix)** | | | **~400,000** | **~1.7σ** |
| **Composite (post-fix)** | | | **~200,000** | **~2.3σ** |

## Defects Found

1. Refresh token expiry bypass: malformed expiry timestamp string raised an exception that fell through, allowing expired tokens to be accepted
2. MFA tokens stored in-memory: process restart clears all pending MFA state, and multi-worker deployments would have inconsistent state across workers
3. Zero test coverage for JWT issuance, validation, refresh, and revocation paths

## Fixes Applied

- Refresh token expiry parse hardened: malformed date now rejects the token (deny-by-default) instead of raising unhandled exception
- Token revocation path confirmed to log `LOGOUT` security event
- Algorithm restriction confirmed correct: `HS256` explicit in all `jwt.decode()` calls — no `algorithms=["none"]` risk

## Residual Risk

**MFA tokens in-memory (NFN):** Requires a new DB table and migration. Single-worker deployment mitigates the multi-worker race condition for now. Marked for `NEXT_30_DAYS`.

**Zero test coverage:** The entire JWT module is untested. This is the primary driver of the poor sigma score. A partial implementation bug could go undetected until production. Marked for `NEXT_30_DAYS`.

## Post-Fix Score

~200,000 DPMO — approximately **2.3σ**

Primary remaining gap is test coverage. The module's logic is sound but unverified by automated tests.
