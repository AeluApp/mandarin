# Quality Audit Log

> Measurement cadence: monthly | Owner: Jason

Each row records a point-in-time sigma measurement of the codebase.

| Date | Tests | Composite DPMO | Sigma | Delta | Notes |
|------|-------|---------------|-------|-------|-------|
| 2026-02-25 (pre-fix) | 899 | ~350,000 | ~2.1σ | — | Baseline. 15 subsystems assessed. 34 defects catalogued. |
| 2026-02-25 (post-fix) | 996 | ~120,000 | ~2.9σ | +0.8σ | 22 code fixes, 97 new tests (4 test files), CI gates, quality docs. |
| 2026-02-26 | 1072 | ~60,000 | ~3.2σ | +0.3σ | 76 new tests (test_payment, test_mfa_routes, test_classroom_routes). Payment 1.5→3.0σ, MFA→3.5σ, Classroom 2.1→3.0σ. Metrics report: north star, completion by segment, D1/D7/D30 retention, growth accounting, crash rate. Homepage copy fixed. |
| 2026-02-26 (r2) | 1099 | ~40,000 | ~3.5σ | +0.3σ | 27 new tests (test_token_routes). JWT 2.7→3.2σ. Env reads centralized (0 os.environ outside settings.py). 8 dead loggers removed, 2 activated. schema.sql synced (40 tables). |
| 2026-02-26 (r3) | 1119 | ~18,000 | ~3.6σ | +0.1σ | MFA tokens→DB (V25 migration, mfa_challenge table). test_feature_flags.py (20 tests). @api_error_handler on payment/classroom/admin routes (21 routes). security.py catch broadened. Authorization 2.7→3.5σ, Payment 2.7→3.5σ, Classroom 2.9→3.5σ. |
| 2026-02-26 (r4-r5) | 1205 | ~10,000 | ~3.8σ | +0.2σ | test_data_retention.py (20), test_metrics_report.py (66). Coverage 47.8→53.9% (fail_under=53). Phantom drill_response removed. Doc drift CI job. Coverage omits for entry points. |
| 2026-02-26 (r6) | 1244 | ~5,000 | ~4.1σ | +0.3σ | Security headers (6 headers, test_security_headers.py). Property-based SRS tests (test_srs_property.py, 33 tests). @api_error_handler on marketing feedback. |
| 2026-02-26 (r7) | 1244 | 1,282 | ~4.5σ | +0.4σ | Full CTQ re-audit with expanded dimensions (780 opportunities across 15 subsystems). @api_error_handler on 4 LTI routes. Token rotation on password change. Feedback rate limit tightened. All core CTQs ≥4.5σ. Only remaining defect: missing test_lti_routes.py. |
