# Quality Operating System

> Owner: Jason (solo founder) | Cadence: weekly | Effective: 2026-02-25

---

## 1. CTQs — Outcome-Linked

Prior CTQs (in CTQ_REGISTRY.md) measure code-level defects. These CTQs link to **business/user outcomes**.

| CTQ | Outcome | Metric | Good | OK | Bad | Data Source |
|-----|---------|--------|------|----|----|-------------|
| Session completion rate | Retention — users who finish sessions come back | completed / (completed + abandoned + bounced) | > 75% | 60-75% | < 60% | `session_log.session_outcome` |
| Drill accuracy stability | Trust — accuracy should not regress release-over-release | Weekly avg accuracy ±3pp from prior week | delta < 3pp | 3-5pp | > 5pp | `session_log.items_correct / items_completed` |
| Grading credibility | Trust — users must believe grades are fair | % of sessions with boredom_flags = 0 AND early_exit = 0 | > 85% | 70-85% | < 70% | `session_log.boredom_flags`, `session_log.early_exit` |
| Error-to-crash ratio | Reliability — client errors should not escalate to server crashes | `crash_log` count / `client_error_log` count per week | < 5% | 5-15% | > 15% | `crash_log`, `client_error_log` |
| Regression rate per release | Quality — new deploys should not break existing behavior | Tests failing in first CI run post-merge / total tests | 0% | < 1% | > 1% | GitHub Actions test.yml |
| Confusing-state rate | UX — users should not encounter auth/loading/error dead-ends | Client errors of type `js_error` with message containing "undefined" or "null" per 100 sessions | < 2 | 2-5 | > 5 | `client_error_log` |

---

## 2. KPI Dictionary

### KPI-1: WASU (Weekly Active Studying Users)
- **Definition:** Count of distinct `user_id` values with at least 1 `session_log` row where `items_completed > 0` in the trailing 7 days
- **Data source:** `SELECT COUNT(DISTINCT user_id) FROM session_log WHERE items_completed > 0 AND started_at > datetime('now', '-7 days')`
- **Segments:** subscription_tier, platform (web/mobile via user_agent)
- **Thresholds:** Good: growing WoW; OK: flat; Bad: declining 2+ consecutive weeks
- **Review:** Weekly (via `metrics_report.py`)
- **Status:** ALREADY EXISTS in `metrics_report.py`

### KPI-2: Session Completion Rate
- **Definition:** `COUNT(session_outcome='completed') / COUNT(*) FROM session_log` (trailing 7 days, excluding sessions < 30s)
- **Data source:** `session_log.session_outcome`
- **Segments:** session_type, drill modality, HSK level band (1-3, 4-6, 7-9)
- **Thresholds:** Good: > 75%; OK: 60-75%; Bad: < 60%
- **Review:** Weekly
- **Status:** PARTIAL — `metrics_report.py` reports session_outcomes but not as a rate by segment

### KPI-3: Drill Accuracy (7-day rolling)
- **Definition:** `SUM(items_correct) / SUM(items_completed)` from `session_log` trailing 7 days
- **Data source:** `session_log.items_correct`, `session_log.items_completed`
- **Segments:** modality (reading/listening/speaking/ime), HSK level
- **Thresholds:** Good: 70-85%; OK: 60-70% or 85-95%; Bad: < 60% or > 95% (too easy)
- **Review:** Weekly
- **Status:** ALREADY EXISTS in `metrics_report.py`

### KPI-4: Early Exit Rate
- **Definition:** `COUNT(early_exit=1) / COUNT(*)` from `session_log` trailing 7 days
- **Data source:** `session_log.early_exit`
- **Segments:** session_type, time_of_day band (morning/afternoon/evening)
- **Thresholds:** Good: < 15%; OK: 15-25%; Bad: > 25%
- **Review:** Weekly
- **Status:** ALREADY EXISTS in `metrics_report.py`

### KPI-5: Crash Rate
- **Definition:** `COUNT(*) FROM crash_log` in trailing 7 days / total API requests (from access log line count)
- **Data source:** `crash_log`, `app.log` line count
- **Segments:** error_type, request_path
- **Thresholds:** Good: < 0.1%; OK: 0.1-1%; Bad: > 1%
- **Review:** Weekly
- **Status:** PARTIAL — crash_log exists, but no automated rate calculation

### KPI-6: Churn Risk Score Distribution
- **Definition:** Distribution of `churn_detection.score_churn_risk()` across all users with sessions in trailing 30 days
- **Data source:** `churn_detection.py` output
- **Segments:** subscription_tier, days_since_signup band
- **Thresholds:** Good: < 10% users at High/Critical; OK: 10-20%; Bad: > 20%
- **Review:** Weekly
- **Status:** ALREADY EXISTS — `churn_detection.py` + `email_scheduler.py` runs hourly

### KPI-7: Test Suite Health
- **Definition:** test pass rate = passed / collected; coverage = covered lines / total lines
- **Data source:** GitHub Actions test.yml output
- **Segments:** Python version (3.9, 3.12)
- **Thresholds:** Good: 100% pass + > 60% coverage; OK: 100% pass + > 50%; Bad: any failure
- **Review:** Every PR
- **Status:** ALREADY EXISTS in CI (test.yml)

---

## 3. Weekly Quality Review — Agenda (20 min)

**When:** Monday morning, first thing
**Input:** `./run metrics` output from prior week

| Time | Topic | Action |
|------|-------|--------|
| 0-3 min | WASU + session count WoW | If declining 2+ weeks → investigate |
| 3-6 min | Completion rate + early exit rate | If bad band → check drill difficulty calibration |
| 6-9 min | Accuracy by modality | If any modality < 60% → review error patterns |
| 9-12 min | Crash count + client error count | If > 5 crashes/week → triage top error_type |
| 12-15 min | Churn risk distribution | If > 20% high/critical → check engagement patterns |
| 15-18 min | Test suite: pass rate + coverage delta | If coverage dropped → block next deploy |
| 18-20 min | Action items for this week | Max 3 items, each with owner + due date |

**Output:** Update `reports/weekly-review-YYYY-MM-DD.md` with decisions.

---

## 4. Release Checklist

Before every deploy to production:

- [ ] All tests pass on both Python 3.9 and 3.12 (`test.yml` green)
- [ ] Ruff lint passes (`lint` job green)
- [ ] Quality regression tests pass (`quality-gates` job green)
- [ ] Coverage >= 50% (enforced by `--cov-fail-under=50`)
- [ ] Bandit SAST: zero HIGH findings (`security.yml` green)
- [ ] No new `FIXME` or `TODO` in changed files (grep check)
- [ ] Schema migration (if any) is idempotent (`DROP TABLE IF EXISTS`)
- [ ] .env.example updated if new env vars added
- [ ] BUILD_STATE.md table count and test count updated if changed

**Stop-the-line rules:**
1. Any test failure → no deploy
2. Coverage drop below 50% → no deploy
3. Bandit HIGH finding → no deploy
4. crash_log > 10 entries in last 24h → investigate before deploying new code
5. Session completion rate drops below 60% for 2 consecutive days → feature freeze, investigate

---

## 5. Incident / RCA Template

```markdown
# Incident: [TITLE]

**Severity:** P1 (data loss/security) / P2 (feature broken) / P3 (degraded) / P4 (cosmetic)
**Detected:** [timestamp] by [automated alert / user report / weekly review]
**Resolved:** [timestamp]
**Duration:** [minutes]

## Timeline
- HH:MM — [what happened]

## Root Cause
[1-2 sentences]

## Impact
- Users affected: [count or %]
- KPI impact: [which KPI, how much]

## Fix
- PR: [link]
- Regression test: [test name]

## Prevention
- [ ] Control added to prevent recurrence: [describe]
```

**Severity levels:**
- **P1:** Data loss, security breach, auth bypass, payment error → fix within 1 hour
- **P2:** Feature completely broken for all users → fix within 4 hours
- **P3:** Feature degraded (slow, partial) → fix within 24 hours
- **P4:** Cosmetic, non-blocking → fix in next sprint

---

## 6. CI Gates Summary

| Gate | Workflow | Blocks Merge | Threshold |
|------|----------|-------------|-----------|
| Tests (3.9 + 3.12) | test.yml / test | Yes | 0 failures |
| Coverage | test.yml / test | Yes | >= 50% |
| Ruff lint | test.yml / lint | Yes | 0 errors |
| Quality regressions | test.yml / quality-gates | Yes | 0 failures in test_quality_fixes.py |
| Bandit SAST | security.yml / bandit | Yes | 0 HIGH findings |
| SBOM generation | security.yml / sbom | No | Artifact only |
| ZAP DAST | dast.yml | No | WARN only (no FAIL rules) |
| DR test | dr-test.yml | No | Weekly scheduled |
| Deploy gate | deploy.yml | Yes | Tests must pass |

---

## 7. Coverage Config

**DONE** (2026-02-25): Merged `.coveragerc` into `pyproject.toml` and deleted `.coveragerc`.

Current coverage: **46%** (996 tests). The `fail_under = 50` gate is defined but not yet passing locally. Writing test_payment.py, test_mfa_routes.py, and test_classroom_routes.py (TICKET-01/02/03) will push past 50%.

Final config in `pyproject.toml`:
```toml
[tool.coverage.run]
source = ["mandarin"]
omit = [
    "mandarin/cli.py",
    "mandarin/menu.py",
    "mandarin/audio.py",
    "mandarin/tone_grading.py",
    "mandarin/web/templates/*",
    "mandarin/web/static/*",
    "mandarin/seed_data.py",
]
```
