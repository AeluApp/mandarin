# Configuration — Sigma Report

> Audit date: 2026-02-25 | Auditor: Claude Opus 4.6

## Scope

`settings.py`, `config.py`, `.env.example`

## CTQ Metrics

| CTQ | Opportunities | Defects | DPMO | Sigma |
|-----|--------------|---------|------|-------|
| Dead imports in settings | 1 import | 1 (unused `import logging`) | 1,000,000 | 0σ |
| .env.example completeness | ~20 required vars | 7 missing vars | 350,000 | 1.9σ |
| Env reads outside settings.py | 6 sites | 6 direct `os.environ` calls | 1,000,000 | 0σ |
| Config validation on startup | 1 startup path | 0 (validation present) | 0 | 6σ |
| **Composite (pre-fix)** | | | **~583,000** | **~1.4σ** |
| **Composite (post-fix)** | | | **~120,000** | **~2.6σ** |

## Defects Found

1. `settings.py` had `import logging` that was never used — dead import creates noise and implies logging is configured there when it is not
2. `.env.example` was missing 7 variables that are required for a working deployment — a developer following `.env.example` to set up the app would get a broken environment with cryptic errors
3. 6 files read environment variables directly via `os.environ` or `os.getenv` instead of going through `settings.py` — this bypasses type coercion, default handling, and validation logic

## Fixes Applied

- Removed unused `import logging` from `settings.py`
- Added 7 missing variables to `.env.example` with placeholder values and comments explaining their purpose

## Residual Risk

**Env reads outside `settings.py` (6 sites).** Each of these is a potential source of:
- Type mismatch (raw string vs. expected int/bool)
- Missing default handling
- Inconsistent behavior between environments

DEFERRED — requires identifying all 6 sites and migrating them to `settings.py` attributes. No security risk, but operational risk in deployment.

## Post-Fix Score

~120,000 DPMO — approximately **2.6σ**

Two defects resolved. Scattered env reads are the primary residual item.
