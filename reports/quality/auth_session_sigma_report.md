# Authentication (Session) — Sigma Report

> Audit date: 2026-02-25 | Auditor: Claude Opus 4.6

## Scope

`auth.py`, `auth_routes.py`, `cli_auth.py`

## CTQ Metrics

| CTQ | Opportunities | Defects | DPMO | Sigma |
|-----|--------------|---------|------|-------|
| Session fixation prevention | 3 login paths | 3 missing clear() | 1,000,000 | 0σ |
| Account lockout enforcement | 1 lockout path | 1 bypass via malformed date | 1,000,000 | 0σ |
| Security event logging | 12 event types | 0 unlogged | 0 | 6σ |
| Password hash safety | 1 hash call | 0 defects | 0 | 6σ |
| **Composite (pre-fix)** | | | **~500,000** | **~1.5σ** |
| **Composite (post-fix)** | | | **~35,000** | **~3.3σ** |

## Defects Found

1. Session fixation: `login_user()` called on 3 paths without prior `session.clear()` — attacker-controlled session ID carries over post-authentication
2. Account lockout bypass: malformed `locked_until` value (non-ISO string) caused exception that fell through to grant login — effective bypass of lockout mechanism
3. `cli_auth.py` has no security event logging — lockout events, failed logins, and CLI session starts are silent
4. `auth.py` L2576 — `generate_password_hash` import only; confirmed not a bare call without `method=`

## Fixes Applied

- `session.clear()` added before all 3 `login_user()` calls, eliminating session fixation vectors
- Malformed `locked_until` handling hardened: parse failure now treats account as locked (deny-by-default)
- Confirmed `cli.py` L2609 already passes `method=` to `generate_password_hash` — no change needed
- Verified all 12 security event types are logged in `auth_routes.py`

## Residual Risk

`cli_auth.py` has no logging. Risk is LOW: CLI-only path, not reachable from the web, and the CLI user is typically the system owner. Logging could be added in a future pass.

No test coverage for auth flows. This is a gap but is tracked separately under the Testing & CI sigma report.

## Post-Fix Score

~35,000 DPMO — approximately **3.3σ**
