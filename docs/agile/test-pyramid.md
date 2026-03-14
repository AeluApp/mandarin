# Aelu Test Pyramid Strategy

**Last Updated:** 2026-03-10

---

## Test Pyramid Overview

```
         /\
        /  \        E2E Tests (10%)
       /    \       Full user flows through Flask app + DB + templates
      /------\
     /        \     Integration Tests (20%)
    /          \    Flask test_client with real SQLite DB
   /------------\
  /              \  Unit Tests (70%)
 /                \ Pure function tests, no DB, no HTTP
/------------------\
```

The pyramid reflects cost: unit tests are fast, cheap, and numerous. E2E tests are slow, expensive, and few. Integration tests sit in the middle. Inverting this pyramid (more E2E than unit) creates a slow, brittle, expensive test suite.

---

## What Qualifies as Each Level for Aelu

### Unit Tests (70% target)

**Definition:** Tests that exercise a single function or method in isolation. No database. No HTTP requests. No file I/O. Dependencies are mocked or stubbed when necessary.

**Scope for Aelu:**
- SRS interval calculations in `scheduler.py` (given mastery_stage, return next interval)
- Tone grading logic in `tone_grading.py` (given audio features, return grade)
- Drill generation functions in `drills/` (given item data, return drill object)
- Grammar linking in `grammar_linker.py` (given sentence, return tagged grammar points)
- HSK level determination in `placement.py` (given scores, return level)
- Display formatting in `display.py` (given item, return formatted string)
- Config validation in `config.py` (given settings, return validated config)
- JWT token generation/validation in `jwt_auth.py` (given payload, return token)
- Feature flag evaluation in `feature_flags.py` (given user context, return flag value)
- Churn signal detection in `churn_detection.py` (given session history, return risk score)
- Email template rendering in `email.py` (given context, return HTML string)
- Tier gate checks in `tier_gate.py` (given user tier, return access boolean)

**Characteristics:**
- Execute in < 10ms each
- No `create_app()` or `test_client` calls
- No `sqlite3.connect()` calls
- Deterministic -- same input always produces same output
- Can run in parallel without conflict

**Naming convention:** `test_<module>_<function>_<scenario>()`

Example: `test_scheduler_next_interval_stage_3_correct()`, `test_tone_grading_flat_tone_returns_low_score()`

### Integration Tests (20% target)

**Definition:** Tests that exercise multiple components working together, typically a Flask route hitting a real SQLite database and returning a response.

**Scope for Aelu:**
- API routes in `web/routes.py` via `create_app()` + `test_client`
- Auth flows: signup, login, token refresh, MFA verification via `auth.py` + `jwt_auth.py` + DB
- Session lifecycle: start session, submit drill, complete session via routes + `scheduler.py` + DB
- Admin dashboard data via admin routes + DB queries
- Classroom routes via `test_classroom_routes.py` + DB
- GDPR export via `test_gdpr_routes.py` + DB
- Exposure routes (reading, media, listening) via `test_exposure_routes.py` + DB
- Grammar routes via `test_grammar_routes.py` + DB
- Data retention cleanup via `data_retention.py` + DB

**Characteristics:**
- Use `create_app()` with test configuration
- Use a fresh in-memory or temporary SQLite database per test (via `conftest.py` fixtures)
- Execute in < 500ms each
- Test HTTP status codes, response JSON structure, and database side effects
- May use `conftest.py` fixtures for user creation, session setup, seed data

**Naming convention:** `test_<route_or_flow>_<scenario>()`

Example: `test_login_correct_credentials_returns_jwt()`, `test_session_complete_updates_mastery_stage()`

### E2E Tests (10% target)

**Definition:** Tests that simulate a complete user flow from start to finish, spanning multiple routes and verifying the full interaction chain.

**Scope for Aelu:**
- `tests/e2e/test_golden_paths.py`: Complete flows like signup -> placement -> first session -> complete session -> dashboard
- `tests/e2e/test_mobile.py`: Capacitor-specific flows (native app detection, redirect handling)
- `tests/test_golden_flows.py`: Critical path tests (login -> session -> review -> logout)
- Smoke tests (`scripts/smoke_test.sh`): Post-deploy verification against production

**Characteristics:**
- Use `create_app()` + `test_client` with full middleware stack
- May span multiple HTTP requests in sequence (login, then session, then drill, then complete)
- Execute in < 2 seconds each
- Test the complete contract between client and server
- Fragile by nature -- changes to any layer can break them

**Naming convention:** `test_e2e_<user_flow>()`

Example: `test_e2e_new_user_signup_through_first_session()`, `test_e2e_returning_user_resumes_interrupted_session()`

---

## Current State

Run these commands to count tests by category:

```bash
# Total test count
pytest --co -q 2>/dev/null | tail -1

# Unit tests (files that don't import create_app or test_client)
grep -rL "create_app\|test_client\|client\." tests/test_*.py | wc -l

# Integration tests (files that use create_app/test_client)
grep -rl "create_app\|test_client\|client\." tests/test_*.py | wc -l

# E2E tests
ls tests/e2e/test_*.py 2>/dev/null | wc -l
```

### Current Test Files by Category

| Category | Files | Examples |
|---|---|---|
| Unit | test_drill_units.py, test_consistency.py, test_constants_regression.py, test_content_integrity.py, test_config.py, test_hints.py, test_hsk_requirements.py, test_linguist.py, test_edge_cases.py | Pure logic, no DB |
| Integration | test_auth.py, test_admin_routes.py, test_classroom_routes.py, test_exposure_routes.py, test_grammar_routes.py, test_gdpr_routes.py, test_jwt_auth.py, test_integration.py, test_feature_flags.py, test_data_retention.py, test_security_regression.py | Flask test_client + DB |
| E2E | e2e/test_golden_paths.py, e2e/test_mobile.py, test_golden_flows.py | Multi-step user flows |

### Target Ratios

| Category | Target % | Notes |
|---|---|---|
| Unit | 70% | Fast, deterministic, cheap to maintain |
| Integration | 20% | Verify component interactions, moderate cost |
| E2E | 10% | Critical paths only, high maintenance cost |

---

## Coverage Targets by Module

Coverage is tracked by `scripts/coverage_floors.py` and enforced in CI (`--cov-fail-under=55`). The floor is a ratchet -- it can only go up.

### Module-Level Coverage Targets

| Module | Current Floor | Target | Priority | Notes |
|---|---|---|---|---|
| `jwt_auth.py` | High | 95% | Critical | Auth is a security boundary |
| `auth.py` | High | 90% | Critical | Login/signup/MFA flows |
| `scheduler.py` | Medium | 90% | Critical | Core SRS algorithm -- wrong intervals = wrong learning |
| `drills/` | Medium | 85% | High | Drill generation and grading |
| `web/routes.py` | Medium | 80% | High | All API endpoints |
| `db/core.py` | Medium | 80% | High | Schema, migrations, queries |
| `tone_grading.py` | Medium | 80% | High | Grading accuracy affects learner trust |
| `churn_detection.py` | Low | 75% | Medium | Business logic, not user-facing |
| `personalization.py` | Low | 75% | Medium | Drill mix adjustment |
| `payment.py` | Low | 80% | High | Revenue-critical, Stripe integration |
| `email.py` | Low | 70% | Medium | Template rendering, send logic |
| `display.py` | Low | 60% | Low | Formatting only |
| `cli.py` | Low | 50% | Low | Developer tooling, not production |
| `menu.py` | Low | 50% | Low | Interactive menu, hard to test |

---

## Test Naming Conventions

### Pattern
```
test_<module_or_feature>_<function_or_scenario>_<expected_outcome>()
```

### Examples

```python
# Unit
def test_scheduler_next_interval_stage_3_returns_3_days():
def test_tone_grading_rising_tone_scores_above_threshold():
def test_placement_all_correct_returns_hsk_3():
def test_jwt_expired_token_raises_invalid_token():

# Integration
def test_login_valid_credentials_returns_200_with_jwt():
def test_session_start_creates_session_row_in_db():
def test_admin_dashboard_requires_admin_role():
def test_gdpr_export_includes_all_user_tables():

# E2E
def test_e2e_signup_placement_first_session_complete():
def test_e2e_teacher_views_student_progress():
```

### Anti-Patterns

```python
# Too vague
def test_login():
def test_scheduler():

# Tests implementation, not behavior
def test_scheduler_calls_sqlite_query():

# Negative name without clarity
def test_not_logged_in():  # Better: test_unauthenticated_request_returns_401()
```

---

## Mutation Testing Strategy

Mutation testing verifies that tests actually catch bugs. A mutant is a small code change (e.g., `>` becomes `>=`). If tests still pass after the mutation, the test suite has a gap.

### Tool: mutmut

```bash
# Install
pip install mutmut

# Run against a specific module (don't run against the whole codebase -- too slow)
mutmut run --paths-to-mutate mandarin/scheduler.py --tests-dir tests/

# View surviving mutants
mutmut results

# Inspect a specific mutant
mutmut show <mutant_id>
```

### mutmut Configuration

Add to `pyproject.toml` (or `setup.cfg`):

```toml
[tool.mutmut]
paths_to_mutate = "mandarin/"
tests_dir = "tests/"
runner = "python -m pytest -x -q --tb=line"
dict_synonyms = "Struct, NamedStruct"
```

### Priority Modules for Mutation Testing

Run mutation testing on high-risk modules first. Target: < 20% surviving mutants.

| Module | Why Mutate | Surviving Mutant Risk |
|---|---|---|
| `scheduler.py` | Wrong SRS intervals silently degrade learning | Boundary conditions (off-by-one in mastery_stage comparisons) |
| `jwt_auth.py` | Security boundary -- mutations could open auth bypass | Token expiry checks, role comparisons |
| `tone_grading.py` | Grading errors erode learner trust | Threshold comparisons, score calculations |
| `placement.py` | Wrong placement level means wrong content | Score aggregation, level boundary logic |
| `tier_gate.py` | Mutations could expose paid features to free users | Access control comparisons |
| `churn_detection.py` | Wrong thresholds miss at-risk users or create false alarms | Percentage calculations, day-count comparisons |

### Mutation Testing Cadence

- Run mutation testing on changed modules before each sprint's final deploy
- Full-codebase mutation testing quarterly (it's slow -- expect 30-60 minutes)
- When a production bug is found, run mutation testing on the affected module to check for similar gaps

### Interpreting Results

| Mutation Score | Assessment | Action |
|---|---|---|
| > 90% killed | Strong test suite for this module | Maintain |
| 70-90% killed | Adequate but gaps exist | Write tests for surviving mutants |
| < 70% killed | Tests are insufficient | Prioritize test writing for this module |

---

## Test Infrastructure

### conftest.py Fixtures

Key fixtures in `tests/conftest.py`:

- `app` -- Flask app instance with test configuration
- `client` -- Flask test client for HTTP requests
- `db` -- Fresh SQLite database (in-memory or temp file)
- `auth_headers` -- JWT headers for authenticated requests
- `admin_headers` -- JWT headers with admin role
- `seed_content` -- HSK 1-3 vocabulary and grammar points loaded
- `test_user` -- A user created with known credentials

### Test Database Isolation

Every test that touches the database must use a fresh database instance. Tests must not depend on each other's data. The `conftest.py` fixtures handle this -- never create a shared database across tests.

### CI Configuration

Tests run on every push and PR via `.github/workflows/test.yml`:
- Matrix: Python 3.9 and 3.12
- Coverage enforcement: `--cov-fail-under=55`
- Risk-weighted floors: `scripts/coverage_floors.py`
- Quality gates: `tests/test_quality_fixes.py`
- Audit: `scripts/audit_check.py` (13 checks)
