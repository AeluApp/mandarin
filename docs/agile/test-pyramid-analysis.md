# Aelu Test Pyramid Analysis

**Last Updated:** 2026-03-10
**Total Tests:** 1,343 across 73 test files (71 main + 2 e2e)

---

## Test Categories

### Unit Tests (files that test single modules without Flask app context)

These test files import individual modules and test functions/classes directly, without creating a Flask app or using test_client.

| File | Description |
|---|---|
| test_anti_gaming.py | Anti-gaming detection logic |
| test_audio_safety.py | Audio safety checks |
| test_config.py | Configuration loading |
| test_consistency.py | Data consistency checks |
| test_constants_regression.py | Constants stability |
| test_content_integrity.py | Content data integrity |
| test_data_retention.py | Data retention policy logic |
| test_dialogue_reform.py | Dialogue reformatting |
| test_dialogue_support.py | Dialogue support functions |
| test_doctor.py | System health checks |
| test_drill_units.py | Individual drill type logic |
| test_edge_cases.py | Edge case handling |
| test_feature_flags.py | Feature flag evaluation |
| test_hardening.py | Input hardening/validation |
| test_hints.py | Hint generation |
| test_hsk_requirements.py | HSK level requirements |
| test_integration.py | Module integration (no Flask) |
| test_linguist.py | Linguistic analysis |
| test_listening_drills.py | Listening drill logic |
| test_logging.py | Log configuration |
| test_mastery_stages.py | Mastery stage transitions |
| test_measure_words.py | Measure word handling |
| test_metrics_report.py | Metrics report generation |
| test_mfa.py | MFA logic (no routes) |
| test_milestones.py | Milestone detection |
| test_new_drills.py | New drill types |
| test_personalization.py | Personalization engine |
| test_production_grading.py | Production drill grading |
| test_psychological.py | Psychological profile |
| test_report_forecast.py | Forecast reports |
| test_retention.py | Retention/SRS calculations |
| test_retention_scheduler.py | Retention scheduler logic |
| test_scaffold.py | Scaffolding logic |
| test_scheduler.py | Main scheduler logic |
| test_scheduler_lock.py | Scheduler locking |
| test_security_events.py | Security event detection |
| test_srs_decomposition.py | SRS algorithm decomposition |
| test_teacher.py | Teacher/tutor logic |
| test_telemetry.py | Telemetry collection |
| test_tier_gate.py | Subscription tier gating |
| test_tone_best_practices.py | Tone drill best practices |
| test_tone_features.py | Tone feature extraction |
| test_tone_validation.py | Tone input validation |
| test_ui.py | UI label generation |
| test_validator.py | Input validation |
| test_web_parity.py | Web/CLI parity checks |
| test_ws_resume.py | WebSocket resume logic |

**Count: 48 files**

### Integration Tests (files using `create_app(testing=True)` + Flask test_client)

These test files create a Flask application context and test HTTP routes, middleware, and request/response behavior.

| File | Description |
|---|---|
| test_admin_routes.py | Admin dashboard routes |
| test_api_error_handler.py | API error response format |
| test_auth.py | Authentication routes |
| test_classroom_routes.py | Classroom management routes |
| test_exposure_routes.py | Exposure/encounter routes |
| test_gdpr_routes.py | GDPR data export/deletion routes |
| test_golden_flows.py | Golden path flow tests |
| test_grammar_routes.py | Grammar API routes |
| test_jwt_auth.py | JWT authentication |
| test_listening_routes.py | Listening API routes |
| test_lti_routes.py | LTI integration routes |
| test_mfa_routes.py | MFA challenge routes |
| test_onboarding_routes.py | Onboarding flow routes |
| test_payment.py | Payment/Stripe routes |
| test_quality_fixes.py | Quality fix verification |
| test_reading_media_routes.py | Reading and media routes |
| test_security_headers.py | Security header verification |
| test_security_regression.py | Security regression tests |
| test_session_cleanup.py | Session cleanup logic |
| test_sync_routes.py | Offline sync routes |
| test_token_routes.py | JWT token routes |
| test_web_routes.py | Main web routes |

**Count: 22 files** (21 using create_app directly + 1 via conftest fixture)

### E2E Tests (full user journey tests)

| File | Description |
|---|---|
| tests/e2e/test_golden_paths.py | Complete user journeys (signup -> session -> progress) |
| tests/e2e/test_mobile.py | Mobile-specific flows (JWT auth, offline sync, native features) |

**Count: 2 files**

### Property-Based Tests (hypothesis)

| File | Description |
|---|---|
| test_retention_property.py | SRS interval calculations with random inputs |
| test_srs_property.py | SRS algorithm properties verified across input space |

**Count: 2 files**

---

## Test Count Estimates

Based on `grep -c "def test_"` across files (from the top-20 data plus BUILD_STATE.md total of 1,343):

| Category | Files | Estimated Tests | Percentage |
|---|---|---|---|
| Unit | 48 | ~870 | ~65% |
| Integration | 22 | ~410 | ~30% |
| E2E | 2 | ~30 | ~2% |
| Property-based | 2 | ~33 | ~3% |
| **Total** | **74** | **~1,343** | **100%** |

---

## Pyramid Analysis

### Target Pyramid (industry standard)

```
        /\
       /E2E\        10%
      /------\
     / Integ. \     20%
    /----------\
   /   Unit     \   70%
  /--------------\
```

### Current Pyramid

```
        /\
       /E2E\        2%
      /------\
     / Integ. \     30%
    /----------\
   /   Unit     \   65%
  /--------------\
  Prop:           3%
```

### Gap Analysis

| Layer | Target % | Current % | Gap | Assessment |
|---|---|---|---|---|
| Unit | 70% | 65% | -5% | Slightly below target. Acceptable but room for improvement. |
| Integration | 20% | 30% | +10% | Above target. Many route tests could be simplified to unit tests if the handler logic were extracted from route functions. |
| E2E | 10% | 2% | -8% | Significantly below target. This is the biggest gap. |
| Property-based | (bonus) | 3% | — | Good. Two property-based test files covering the SRS algorithm is appropriate. |

---

## Specific Gaps and Recommendations

### Gap 1: E2E Coverage is Thin (2% vs 10% target)
**Current state:** Only 2 E2E test files (`test_golden_paths.py`, `test_mobile.py`). These cover the happy path but likely miss edge cases in the full user journey.

**Missing E2E scenarios:**
- User signs up, completes onboarding, does 3 sessions across 3 days, checks progress
- User encounters a payment failure, sees the grace period banner, updates payment
- User starts a session, loses connectivity, reconnects, completes the session
- User appeals a grade, appeal is reviewed in admin, outcome is communicated
- Teacher creates a classroom, adds students, views progress dashboard
- User requests GDPR data export, receives ZIP, requests deletion

**Action:** Add 4-6 E2E test scenarios covering the most critical user journeys. Estimate: 8 story points.

### Gap 2: Integration Tests Are Heavy (30% vs 20% target)
**Current state:** 22 files use `create_app` + `test_client`. Many of these test route-level behavior that could be decomposed: extract business logic into service functions, unit test those, and thin out the route tests to only verify HTTP concerns (status codes, headers, auth).

**Example:** `test_classroom_routes.py` (37 tests) likely tests both HTTP routing AND classroom business logic. If classroom logic were in a service module, those tests could be split: unit tests for logic, integration tests for the HTTP layer only.

**Action:** Identify the 5 largest integration test files and audit whether they're testing HTTP concerns or business logic. Extract business logic tests to unit tests where possible. Estimate: 5 story points.

### Gap 3: No Contract Tests
**Current state:** The mobile app (Capacitor) and web app both consume the same Flask API. There are no contract tests verifying that the API responses match the client's expectations.

**Action:** Add contract tests for the 10 most critical API endpoints (token, sync, session, progress). These sit between integration and E2E. Estimate: 3 story points.

### Gap 4: No Visual Regression Tests
**Current state:** CSS changes are verified manually via screenshots. No automated visual comparison.

**Action:** Low priority for now. Consider Percy or BackstopJS if CSS regressions become a recurring problem. Estimate: 5 story points.

### Gap 5: Property Tests Only Cover SRS
**Current state:** Hypothesis tests exist for `test_retention_property.py` and `test_srs_property.py`. Other algorithmic modules (scheduler, personalization, tone_grading) could benefit from property-based testing.

**Action:** Add property-based tests for the scheduler's session-building algorithm (verify it always produces valid sessions regardless of input state). Estimate: 3 story points.

---

## Test Health Indicators

| Indicator | Status | Notes |
|---|---|---|
| All tests pass | Verified per DoD | `pytest -q` runs clean |
| Test run time | Unknown | Measure and set a budget (target: <60 seconds) |
| Flaky tests | Historically present | Flaky test fixes noted in memory as past tech debt work |
| Coverage floor | Enforced via `scripts/coverage_floors.py` | Exact percentage unknown — measure and document |
| Test isolation | Mostly good | SQLite in-memory databases for test isolation |
| Fixture reuse | `conftest.py` at root and e2e levels | Shared fixtures reduce boilerplate |

---

## Next Steps (Priority Order)

1. **Measure exact coverage percentage** and document the floor. (`pytest --cov=mandarin --cov-report=term-missing`)
2. **Add 4 E2E test scenarios** to close the E2E gap (biggest risk area).
3. **Audit top 5 integration test files** for logic that should be unit tested.
4. **Add scheduler property tests** (the scheduler is the most complex deterministic module).
5. **Measure test suite runtime** and set a budget. If >120 seconds, investigate parallelization.
