# Aelu Definition of Done

**Last Updated:** 2026-03-10

A Product Backlog item is "Done" when ALL of the following are true. No exceptions. If a criterion cannot be met, the item is not done -- it carries into the next sprint as incomplete work.

---

## Checklist

### 1. All Tests Pass
```bash
cd ~/mandarin && source venv/bin/activate && pytest -q
```
All 1343+ tests must pass. Zero failures, zero errors. Skipped tests are acceptable only if pre-existing and documented.

### 2. Coverage Does Not Decrease
```bash
pytest --cov=mandarin --cov-fail-under=<current_floor>
```
The `--cov-fail-under` threshold is maintained in `scripts/coverage_floors.py`. If the item adds new code, that code must have tests. Coverage floor must not drop.

### 3. No HIGH Bandit Findings
```bash
bandit -r mandarin/ -ll -q
```
Zero HIGH-severity security findings. MEDIUM findings are logged but do not block. LOW findings are informational.

### 4. Ruff Lint Clean
```bash
ruff check mandarin/ tests/
```
Zero lint errors. No `# noqa` additions unless justified in a code comment explaining why the rule is suppressed.

### 5. Deployed to Production
```bash
fly deploy --app aelu
```
The change is live on the Fly.io production instance. Not "ready to deploy" -- actually deployed. If the deploy fails, the item is not done.

### 6. Smoke Test Passes
```bash
./smoke_test.sh
```
Post-deploy smoke test confirms: landing page loads, login works, session can start, API responds to health check. If no smoke_test.sh exists yet, manually verify these four things and document results.

### 7. No New crash_log Entries for 24 Hours
After deployment, monitor the `crash_log` table for 24 hours. If any new entries appear that correlate with the deployed change, the item is not done until the crash is resolved.

```sql
SELECT * FROM crash_log WHERE created_at > datetime('now', '-24 hours') ORDER BY created_at DESC;
```

### 8. Admin Dashboard Shows No Regression
Check the admin dashboard for:
- Session completion rate has not dropped
- Drill accuracy has not dropped
- Error rate has not increased
- No new entries in `client_error_log` related to the change

This is a judgment call. If metrics are flat or improving, the criterion is met.

### 9. If User-Facing: 1 Person Other Than Developer Has Tested
For any change visible to users (UI, drill behavior, onboarding, emails), at least one person who is not Jason has gone through the affected flow and confirmed it works. This can be:
- A friend testing on their device
- A beta user providing feedback
- A recorded usability test session

For backend-only changes (schema migration, scheduler tuning, security patch), this criterion is waived.

### 10. BUILD_STATE.md Updated If Schema Changed
If the change includes a schema migration (new table, new column, altered constraint):
- `BUILD_STATE.md` reflects the new schema version
- `schema.sql` is updated
- The migration path from the previous version is documented
- `db/core.py` SCHEMA_VERSION constant is incremented

---

## When to Apply

- Every Product Backlog item pulled into a sprint must meet ALL criteria before being counted toward velocity.
- Partially done items are NOT counted. They return to the backlog.
- The DoD is reviewed at each Sprint Retrospective and updated if criteria prove too lax or too strict.

## Anti-Patterns to Avoid

- "It works on my machine" is not done. It must work in production.
- "Tests pass but I didn't write new tests" is not done if new behavior was added.
- "I'll write the docs later" is not done if schema changed.
- Deploying on Friday afternoon and calling it done without monitoring for 24 hours is not done.
