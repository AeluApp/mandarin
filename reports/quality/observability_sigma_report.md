# Observability & Logging — Sigma Report

> Audit date: 2026-02-25 | Auditor: Claude Opus 4.6

## Scope

`log_config.py`, `security.py`, `rate_limit_store.py`, `session_store.py`

## CTQ Metrics

| CTQ | Opportunities | Defects | DPMO | Sigma |
|-----|--------------|---------|------|-------|
| Rate limiter fallback log level | 1 fallback path | 1 at DEBUG (should be WARNING) | 1,000,000 | 0σ |
| CSRF/rate-limit event log level | 2 event paths | 2 at DEBUG (should be WARNING) | 1,000,000 | 0σ |
| Security alert exception scope | 1 catch clause | 1 too narrow (OperationalError only) | 1,000,000 | 0σ |
| Dead loggers | 10 files | 10 logger instances never used | 1,000,000 | 0σ |
| **Composite (pre-fix)** | | | **~1,000,000** | **~0σ** |
| **Composite (post-fix)** | | | **~70,000** | **~3.0σ** |

## Defects Found

1. Rate limiter fallback (in-memory store activated on Redis failure) was logged at DEBUG — operator would have no visibility into a degraded rate-limiting state
2. CSRF violation events logged at DEBUG — security-relevant events were invisible in production log filters
3. Rate-limit breach events logged at DEBUG — same issue as CSRF
4. Security alert DB write caught only `sqlite3.OperationalError` — other `sqlite3.Error` subclasses (e.g., `IntegrityError`, `DatabaseError`) would propagate unhandled
5. 10 files import and instantiate loggers that are never called — dead code that creates false confidence in observability coverage

## Fixes Applied

- Rate limiter fallback elevated to `WARNING` level
- CSRF violation events elevated to `WARNING` level
- Rate-limit breach events elevated to `WARNING` level
- Security alert catch broadened from `sqlite3.OperationalError` to `sqlite3.Error`

## Residual Risk

**Dead loggers in 10 files.** These are modules that set up a logger but never emit a log line. They create an illusion of instrumentation without providing any signal. DEFERRED — requires audit of each file to determine whether log lines should be added or the logger removed.

## Post-Fix Score

~70,000 DPMO — approximately **3.0σ**

Four logging correctness defects resolved. Dead logger cleanup is the primary residual item.
