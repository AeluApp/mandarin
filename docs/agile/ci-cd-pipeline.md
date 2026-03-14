# Aelu CI/CD Pipeline Documentation

**Last Updated:** 2026-03-10

---

## Pipeline Overview

```
Push/PR to main
    |
    v
+--------+    +---------+    +----------+    +--------+    +-------+
|  Lint  | -> |  Test   | -> | Security | -> | Build  | -> | Deploy|
| (ruff) |    | (pytest)|    | (bandit, |    | (fly)  |    | (fly) |
|        |    | +cover  |    |  gitleaks|    |        |    |       |
|        |    | +floors |    |  pip-aud)|    |        |    |       |
|        |    | +audit  |    |  +SBOM   |    |        |    |       |
+--------+    +---------+    +----------+    +--------+    +-------+
                                                              |
                                                              v
                                                          +-------+
                                                          | Smoke |
                                                          | Test  |
                                                          +-------+
```

---

## Current Pipeline: Implemented

### Stage 1: Lint (`.github/workflows/test.yml` -- lint job)

**Trigger:** Every push to `main` and every pull request.

**What it does:**
- Runs `ruff check mandarin/ --config pyproject.toml`
- Enforces zero lint errors
- Uses Python 3.12

**Failure behavior:** PR cannot merge. Fix all lint errors before re-pushing.

**No `# noqa` without justification.** Every suppressed rule must have a code comment explaining why.

---

### Stage 2: Test (`.github/workflows/test.yml` -- test job)

**Trigger:** Every push to `main` and every pull request.

**What it does:**
1. Runs full pytest suite across Python 3.9 and 3.12 matrix
2. Enforces coverage floor: `--cov-fail-under=55`
3. Runs risk-weighted coverage floors: `scripts/coverage_floors.py`
4. Runs quality regression tests: `tests/test_quality_fixes.py`
5. Runs deterministic audit: `scripts/audit_check.py` (13 checks)

**Coverage enforcement:**
- Global floor: 55% (ratchet -- only goes up)
- Per-module floors: Defined in `scripts/coverage_floors.py`
- Coverage report: `--cov-report=term-missing --cov-report=json`

**Failure behavior:** PR cannot merge if any test fails, coverage drops below floor, quality gates fail, or audit checks fail.

---

### Stage 3: Security (`.github/workflows/security.yml`)

**Trigger:** Every push to `main` and every pull request.

**Four parallel security jobs:**

#### 3a: Bandit SAST
- Runs `bandit -r mandarin/ -c pyproject.toml`
- Generates JSON report uploaded as artifact
- **Gate:** Fails on any HIGH-severity finding
- MEDIUM findings are logged but do not block

#### 3b: Secrets Scanning (gitleaks)
- Runs `gitleaks/gitleaks-action@v2`
- Scans full git history (fetch-depth: 0)
- **Gate:** Fails if any secrets are detected in the repository history

#### 3c: Dependency Audit (pip-audit)
- Runs `pip-audit --strict --desc on`
- Generates text report uploaded as artifact
- **Gate:** Fails on CRITICAL or HIGH severity dependency vulnerabilities

#### 3d: SBOM Generation
- Generates CycloneDX Software Bill of Materials
- Uploads `sbom.json` as artifact
- Informational -- does not block the pipeline

---

### Stage 4: Deploy (`.github/workflows/deploy.yml`)

**Trigger:** Push to `main` only (not PRs).

**Pre-deploy gate:** Full test suite must pass (including `test_golden_flows.py` and `test_security_regression.py`).

**Deployment:**
- Uses `superfly/flyctl-actions/setup-flyctl@1.5`
- Runs `flyctl deploy --remote-only`
- Deploys to Fly.io production instance (`aelu` app)
- Requires `FLY_API_TOKEN` secret

---

### Stage 5: Smoke Test (`.github/workflows/deploy.yml` -- smoke job)

**Trigger:** After successful deploy.

**What it does:**
- Waits 15 seconds for deploy to stabilize
- Runs `scripts/smoke_test.sh` against `https://aelu.app`
- Verifies: landing page loads, login endpoint responds, API health check passes

**Failure behavior:** Smoke failure does not auto-rollback (yet). It alerts via GitHub Actions notification. Manual rollback required.

---

### Additional Pipelines

#### DAST (`.github/workflows/dast.yml`)
- Dynamic Application Security Testing
- Tests the running application for vulnerabilities

#### DR Test (`.github/workflows/dr-test.yml`)
- Disaster Recovery testing
- Verifies backup restoration procedures

#### E2E (`.github/workflows/e2e.yml`)
- End-to-end test suite
- Full user flow testing

---

## Target Pipeline: Planned Additions

### Mutation Testing Stage (After Test, Before Security)

**Tool:** mutmut
**Scope:** Run against high-risk modules only (to keep CI under 10 minutes):
- `mandarin/scheduler.py`
- `mandarin/jwt_auth.py`
- `mandarin/tone_grading.py`
- `mandarin/tier_gate.py`

**Gate:** Fail if mutation score drops below 70% on any targeted module.

**Implementation:**
```yaml
mutation:
  runs-on: ubuntu-latest
  needs: test
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -e .
        pip install pytest mutmut
    - name: Run mutation testing on scheduler
      run: mutmut run --paths-to-mutate mandarin/scheduler.py --tests-dir tests/ --runner "pytest -x -q"
    - name: Check mutation score
      run: |
        python -c "
        import json
        # Parse mutmut results and check score
        "
```

### Load Testing Stage (After Deploy, Parallel to Smoke)

**Tool:** Locust (PB-024)
**Scope:** Simulate 50 concurrent users completing sessions against staging.
**Gate:** Fail if p95 response time exceeds 500ms.

**Implementation:**
```yaml
load-test:
  needs: deploy
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Run Locust
      run: |
        pip install locust
        locust -f tests/load/locustfile.py --headless -u 50 -r 10 --run-time 5m \
          --host https://aelu-staging.fly.dev --csv=results
    - name: Check p95
      run: python scripts/check_load_results.py results_stats.csv --p95-max 500
```

### Deployment Gates

Before deploy is allowed, ALL of these must pass:

| Gate | Check | Current Status |
|---|---|---|
| All tests pass | pytest exit code 0 | Implemented |
| Coverage floor met | --cov-fail-under + coverage_floors.py | Implemented |
| No HIGH bandit findings | bandit -ll | Implemented |
| No leaked secrets | gitleaks | Implemented |
| No critical dep vulnerabilities | pip-audit | Implemented |
| Golden flows pass | test_golden_flows.py | Implemented |
| Security regression tests pass | test_security_regression.py | Implemented |
| Quality gates pass | test_quality_fixes.py | Implemented |
| Audit checks pass (13 checks) | audit_check.py | Implemented |
| Doc drift check | BUILD_STATE.md matches schema.sql and test count | Implemented |
| Mutation score > 70% | mutmut on critical modules | Planned |
| Load test p95 < 500ms | Locust against staging | Planned |

---

## Branch Protection Rules

### `main` Branch

| Rule | Setting |
|---|---|
| Require pull request reviews | Yes (1 reviewer -- self-review with documented checklist acceptable for solo dev) |
| Require status checks to pass | Yes |
| Required status checks | `test`, `lint`, `quality-gates`, `audit`, `doc-check`, `bandit`, `secrets`, `dependency-audit` |
| Require branches to be up to date | Yes |
| Require linear history | No (merge commits acceptable) |
| Allow force pushes | No |
| Allow deletions | No |

### Feature Branches

| Naming Convention | Pattern | Example |
|---|---|---|
| Feature | `feature/PB-XXX-short-description` | `feature/PB-012-passage-difficulty` |
| Bug fix | `fix/PB-XXX-short-description` | `fix/PB-018-stale-websocket` |
| Tech debt | `debt/PB-XXX-short-description` | `debt/PB-026-dead-code-audit` |
| Spike | `spike/description` | `spike/srs-interval-experiment` |

---

## Deployment Rollback Procedure

### When to Rollback

Rollback if ANY of these occur within 24 hours of deploy:
- `crash_log` table has 3+ new entries correlated with the deployment
- Smoke test fails on production
- `client_error_log` shows a spike in errors
- Admin dashboard metrics (session completion rate, drill accuracy) drop by > 10%
- Users report a blocking issue

### How to Rollback

#### Option 1: Fly.io Rollback (Preferred -- fastest)

```bash
# List recent deployments
fly releases --app aelu

# Rollback to previous release
fly deploy --image <previous-image-ref> --app aelu

# Verify rollback
./scripts/smoke_test.sh
```

#### Option 2: Git Revert + Redeploy

```bash
# Identify the problematic commit
git log --oneline -5

# Revert the commit
git revert <commit-hash>

# Push to main (triggers deploy pipeline)
git push origin main

# Monitor deploy pipeline in GitHub Actions
```

#### Option 3: Feature Flag Disable

If the problematic change is behind a feature flag (`feature_flags.py`):

```bash
# Disable the flag in production
fly ssh console --app aelu
# Then update the feature flag in the database or config
```

### Post-Rollback Checklist

- [ ] Smoke test passes on production
- [ ] `crash_log` stops receiving new entries
- [ ] Notify affected users if the issue was user-facing
- [ ] Create a bug ticket (PB-XXX) for the root cause
- [ ] Add a regression test that would have caught this
- [ ] Update sprint notes with the incident and time spent

---

## Pipeline Performance Targets

| Metric | Current | Target |
|---|---|---|
| Lint job duration | ~30s | < 1 min |
| Test job duration | ~3 min | < 5 min |
| Security jobs duration | ~2 min | < 3 min |
| Full pipeline (push to deploy) | ~8 min | < 15 min |
| Smoke test duration | ~30s | < 1 min |

If the pipeline exceeds 15 minutes end-to-end, investigate:
- Are tests slow? Profile with `pytest --durations=10`
- Is install slow? Use pip caching in GitHub Actions
- Are security scans scanning too broadly? Scope to changed files

---

## Secrets Management

| Secret | Where Stored | Used By |
|---|---|---|
| `FLY_API_TOKEN` | GitHub Actions secrets | deploy.yml |
| `GITHUB_TOKEN` | Auto-provided by GitHub | gitleaks action |
| Database credentials | Fly.io secrets (`fly secrets set`) | Production app |
| Stripe API keys | Fly.io secrets | payment.py |
| JWT signing key | Fly.io secrets | jwt_auth.py |
| SMTP credentials | Fly.io secrets | email.py |

**Never commit secrets to the repository.** gitleaks scans full history to catch accidental commits. If a secret is accidentally committed, rotate it immediately -- removing it from history is insufficient (it's already in clones).
