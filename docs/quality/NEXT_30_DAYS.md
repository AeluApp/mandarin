# Next 30 Days — Quality Improvement Roadmap

> Generated: 2026-02-25 | Current composite: ~2.5σ post-fix | Target: 4.0σ

Items are ranked by DPMO reduction impact. Each moves the composite sigma upward.

---

## Week 1: Test Coverage for Business-Critical Modules (highest DPMO impact)

These 4 modules have zero tests and handle money, auth, or legal compliance. Fixing this alone drops composite DPMO by ~150K.

### 1. Write `test_jwt_auth.py` (JWT subsystem: 333K → ~50K DPMO)
- Test `create_access_token` round-trips through `decode_access_token`
- Test expired token rejection
- Test `store_refresh_token` / `validate_refresh_token` / `revoke_refresh_token`
- Test malformed refresh token expiry (already verified by `test_quality_fixes.py`)
- Test algorithm restriction (only HS256 accepted)
- **Target: 12-15 tests**

### 2. Write `test_tier_gate.py` (Authorization: 666K → ~100K DPMO)
- Test `check_tier_access` allows admin tier
- Test free tier denied for premium features
- Test logging on denial
- Test `is_enabled` feature flag rollout (50% rollout ≈ 50% of deterministic user IDs pass)
- **Target: 8-10 tests**

### 3. Write `test_payment.py` (Payment: 500K → ~100K DPMO)
- Mock `stripe.checkout.Session.create` — verify `create_checkout_session` returns URL
- Mock webhook with valid/invalid signature
- Test `create_classroom_checkout` with different student counts
- Test `create_billing_portal_session` calls Stripe correctly
- **Target: 10-12 tests**

### 4. Write `test_gdpr.py` (GDPR: 333K → ~50K DPMO)
- Test `export_data` returns JSON with all user tables
- Test `request_deletion` anonymizes user record
- Test `request_deletion` records `data_deletion_request`
- Test `data_retention.py` `purge_expired` with mock retention policies
- **Target: 8-10 tests**

---

## Week 2: HTTP-Level Tests for Web Routes

### 5. Write `test_admin_routes.py` (Admin: 416K → ~50K DPMO)
- Test all 9 admin endpoints with admin user (mock `is_admin=True`)
- Test non-admin gets 403
- Test pagination params
- Test user_id filtering
- **Target: 15-20 tests**

### 6. Write `test_mfa_routes.py` (MFA HTTP: 200K → ~50K DPMO)
- Test `/api/mfa/status` returns correct state
- Test `/api/mfa/setup` returns secret + QR data
- Test `/api/mfa/verify-setup` with valid/invalid TOTP
- Test `/api/mfa/disable` with valid/invalid code
- Test rate limits are enforced
- **Target: 10-12 tests**

### 7. Write `test_classroom_routes.py` (Classroom: 351K → ~50K DPMO)
- Test classroom create/list/join/archive flows
- Test teacher-only routes reject students
- Test invite bulk with valid/invalid data
- **Target: 12-15 tests**

---

## Week 3: Infrastructure Hardening

### 8. Move `_mfa_tokens` to DB (JWT: residual ~200K DPMO)
- Create `mfa_challenge` table in migration V25
- Store challenge token hash + user_id + expires
- Delete on verify or expiry
- This fixes the multi-worker MFA token loss issue (H1 in FIX_INVENTORY)

### 9. Sync `schema.sql` with migrations (Data Layer)
- Add 10 missing tables: `schema_version`, `feature_flag`, `rate_limit`, `retention_policy`, `invite_code`, `push_token`, `lti_platform`, `classroom`, `classroom_student`, `lti_user_mapping`
- Verify table count matches actual (40 total)

### 10. Centralize env var reads (Configuration: residual ~120K DPMO)
- Move `ALERT_WEBHOOK_URL`, `ADMIN_EMAIL`, `SESSION_TIMEOUT_MINUTES`, `FLASK_ENV`, `PORT` into `settings.py`
- Update consumers to import from settings instead of `os.environ.get()`

---

## Week 4: Polish & Documentation

### 11. Activate dead loggers (Observability)
- 10 files have `logger = logging.getLogger(__name__)` but never call `logger.*`
- Add meaningful log calls at error/warning paths in each

### 12. Add `--cov` to default pytest addopts
- Update `pyproject.toml` to include `--cov=mandarin` in addopts
- Raise `fail_under` from 50 to 60 once week 1-2 tests are merged

### 13. Create `docs/quality/AUDIT_LOG.md`
- Record each sigma audit date, composite score, and delta
- Establishes measurement cadence for continuous improvement

---

## Projected Impact

| Milestone | Composite DPMO | Sigma | Delta |
|-----------|---------------|-------|-------|
| Pre-fix (baseline) | ~350,000 | ~1.9σ | — |
| Post-fix (this session) | ~160,000 | ~2.5σ | +0.6σ |
| After Week 1 (4 test files) | ~80,000 | ~2.9σ | +0.4σ |
| After Week 2 (3 test files) | ~40,000 | ~3.3σ | +0.4σ |
| After Week 3 (infra hardening) | ~20,000 | ~3.6σ | +0.3σ |
| After Week 4 (polish) | ~10,000 | ~3.8σ | +0.2σ |

**Realistic 30-day target: 3.8σ** (from current 2.5σ)

Getting to 4.0σ+ requires:
- Per-subsystem coverage floors (80%+)
- Property-based testing for SRS engine
- Contract tests for all external API boundaries (Stripe, Resend, Sentry)
- Automated documentation drift detection in CI
