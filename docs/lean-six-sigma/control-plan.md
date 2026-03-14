# Control Plan — Aelu Quality Assurance

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Review Cadence:** Monthly

---

## Control Plan Table

| # | CTQ (Critical to Quality) | Measurement | Operational Definition | Spec Limits | Sampling Plan | Control Method | Reaction Plan | Owner |
|---|--------------------------|-------------|----------------------|-------------|---------------|---------------|--------------|-------|
| 1 | Session completion rate | `items_completed / items_planned` per session | Proportion of planned drill items the user completes before the session ends (early_exit or natural completion) | Target: 85%, LSL: 65%, USL: 98% | Every session, daily aggregation | p-chart with Nelson rules (SPC Chart 1) | **Below 65%:** Check scheduler parameters — is session too long? Too many error-focus items? Review `plan_snapshot` for difficulty clustering. **Above 98%:** Check if session is too short or too easy — review `items_planned` distribution. **3 consecutive below 85%:** Review adaptive length algorithm (`ADAPTIVE_LENGTH_*` config). | Jason |
| 2 | Drill accuracy | `items_correct / items_completed` per session | Proportion of drill responses graded correct within a session | Target: 70%, LSL: 50%, USL: 90% | Every session, daily aggregation | p-chart with Goldilocks zones (SPC Chart 2) | **Below 50% for 3+ sessions:** Reduce `MAX_NEW_ITEM_RATIO`, increase scaffold hints, review HSK level calibration. Check if placement test needs adjustment. **Above 90% for 3+ sessions:** Increase new item budget (`NEW_BUDGET_*`), introduce harder drill types, check if mastered items are being recycled. **Single session below 30%:** Check for grading bug — review `error_log` entries for that session. | Jason |
| 3 | API latency p95 | 95th percentile server response time | Time from request received to response sent for API endpoints | Target: < 500ms, USL: 1000ms, Critical: 3000ms | Continuous (every request), daily p95 aggregation | I-MR chart (SPC Chart 3) | **p95 > 500ms:** Check SQLite query execution plans, review recent code changes for N+1 queries. **p95 > 1000ms:** Check Fly.io machine health, memory usage, WAL file size. Consider adding database indexes. **p95 > 3000ms:** Emergency — restart Fly.io machine (`fly machine restart`). Check for runaway queries or lock contention. | Jason |
| 4 | Grading consistency | Gage R&R (same input → same output) | Deterministic grading: identical drill type + item + user answer must always produce identical DrillResult | Target: 0% variation, USL: 0% (any variation is a defect) | 50-sample test plan, run monthly | Automated test suite (~1,300 tests) + dedicated Gage R&R test (MSA doc) | **Any variation detected:** This is a critical bug. Stop deployment. Investigate: was randomness introduced to grading logic? Time-dependent code in grader? External API call in grading path? Fix immediately and add regression test. | Jason |
| 5 | 30-day retention rate | % of users with at least 1 session in days 25-35 after their first session | User is "retained" if they have a `session_log` entry with `started_at` between `first_session_at + 25 days` and `first_session_at + 35 days` | Target: 60%, LSL: 40%, Industry baseline: 20% | Monthly cohort analysis | Cohort chart by signup month | **Below 40%:** Trigger churn investigation — run `./run churn-report` for all users in cohort. Review VoC data for exit reasons. Check: were welcome emails sent? Did onboarding complete? Was first session experience good? **Below 20%:** Product crisis — fundamentally rethink onboarding flow, session length, difficulty calibration. Consider free trial extension. | Jason |
| 6 | Error budget consumption | Crash rate per 1,000 sessions | `COUNT(crash_log) / (COUNT(session_log) / 1000)` over rolling 30-day window | Target: < 1.0, USL: 5.0, Critical: 10.0 | Every crash (automatic logging via crash_log table) | Count chart, rolling 30-day window | **Rate > 1.0:** Investigate top crash types in `crash_log`. Triage by `error_type` — are they concentrated or diverse? **Rate > 5.0:** Deploy freeze until top crash is fixed. Review Sentry alerts for patterns. **Rate > 10.0:** Incident response — notify users if user-facing. Rollback last deployment if correlated. | Jason |
| 7 | Churn risk score distribution | Composite score from `churn_detection.py` (0-100) | Weighted combination of 8 behavioral signals: session frequency drop, inactivity days, duration drop, accuracy plateau, drill type monotony, no reading/listening usage | Target: median < 30, USL: any user > 70 | Weekly for all active users | Run `./run churn-report` weekly | **Any user > 70:** Send re-engagement email via Resend. Review their recent session data — what changed? Offer help/guidance. **Any user > 50:** Monitor closely — check next 3 sessions for improvement. **Median > 30:** Systemic issue — the product isn't retaining users. Review all 8 signal components. | Jason |
| 8 | Error focus resolution rate | % of error_focus entries resolved within 14 days | `resolved = 1 AND julianday(resolved_at) - julianday(first_flagged_at) <= 14` | Target: 50%, LSL: 20% | Weekly aggregation | p-chart (SPC Chart 4) | **Below 20%:** Error remediation is not working. Check: is the scheduler actually boosting error-focus items? Is `ERROR_BOOST_FACTOR` high enough? Are the error-focus drill types appropriate for the error type? **Above 90%:** Check: is `consecutive_correct` threshold too low? Are items being resolved too easily? | Jason |
| 9 | Test suite pass rate | % of tests passing in CI | `pytest` exit code + test count | Target: 100%, LSL: 100% (zero tolerance) | Every commit (pre-commit hooks) | Pre-commit hook with ruff + pytest | **Any test failure:** Do not merge. Fix the test or the code. If test is flaky: fix the flakiness (see scheduler_lock.py for precedent). Never mark tests as `@pytest.mark.skip` without documented reason and ticket. | Jason |
| 10 | Content coverage | % of HSK level items with at least 1 drill attempt by any user | `content_item` with `times_shown > 0` per HSK level | Target: 100% for HSK 1-3, 80% for HSK 4-6, 50% for HSK 7-9 | Monthly | SQL query against `content_item.times_shown` | **HSK 1-3 below 100%:** Investigate — are some items never scheduled? Check scheduler filters, item status, difficulty gating. **HSK 4-6 below 50%:** Check if users are progressing to these levels. If no users at HSK 4+, this is expected. | Jason |
| 11 | Security audit events | Anomalous authentication events | `security_audit_log` entries with severity = 'WARNING' or 'ERROR' | Target: 0 per day, USL: 5 per day (could indicate attack) | Continuous (every auth event) | Count chart, daily aggregation | **> 5 WARNING events/day:** Check for brute force attempts — review `ip_address` patterns. Check if `failed_login_attempts` is incrementing on a single user. **Any ERROR event:** Investigate immediately — may indicate compromise attempt. Check `locked_until` timestamps. | Jason |
| 12 | Data retention compliance | Tables purged per retention policy | `retention_policy.last_purged` within `retention_days` window | `crash_log`: 90 days, `client_error_log`: 30 days, `security_audit_log`: 365 days | Weekly check | Automated purge via `data_retention.py` | **Table not purged within window:** Run `./run purge` manually. Check if retention scheduler is running. Verify `retention_policy` rows exist and have correct `retention_days`. | Jason |

---

## Escalation Matrix

| Severity | Definition | Response Time | Action |
|----------|-----------|---------------|--------|
| **Critical** | User-facing outage, data loss, security breach | Immediate (< 1 hour) | Stop all other work. Fix or rollback. Notify affected users. |
| **High** | Grading bug, persistent latency > 1000ms, crash rate > 5.0 | Same day | Deploy freeze until resolved. Root cause analysis required. |
| **Medium** | Completion rate or accuracy out of spec, churn risk > 70 | Within 48 hours | Investigate, implement countermeasure, monitor for improvement. |
| **Low** | Trend approaching limits, coverage gaps, retention policy delay | Within 1 week | Add to backlog, schedule fix. |

---

## Control Plan Review Schedule

| Review Type | Frequency | Content |
|-------------|-----------|---------|
| Daily check | Every day with a study session | Glance at completion rate and accuracy for today's session |
| Weekly review | Every Sunday | Run churn report, check error focus resolution, review crash_log |
| Monthly deep dive | 1st of each month | Recalculate SPC control limits, cohort retention analysis, content coverage audit |
| Quarterly review | Every 3 months | Review and update spec limits, add/remove CTQs, update sampling plans |
