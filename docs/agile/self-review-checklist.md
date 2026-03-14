# Aelu Self-Review Checklist

**Last Updated:** 2026-03-10

This checklist substitutes for code review when working as a solo developer. Every commit to main should pass all items. Print this out. Tape it next to your monitor. Do not skip items because you're in a hurry.

The purpose of code review is not approval — it's catching mistakes that the author is blind to because they're too close to the code. As a solo developer, you must deliberately create distance between "author brain" and "reviewer brain." The best way: write the code, step away for 10 minutes, then review with this checklist.

---

## Pre-Commit Checklist

### 1. Did I read the diff?
```bash
git diff --staged
```
Read every line. Not skim. Read. If the diff is too large to read carefully, the commit is too large. Split it.

**What to look for:**
- Accidental debug prints (`print(`, `console.log(`)
- Hardcoded secrets or API keys
- Commented-out code (delete it or explain why it's there)
- Unintended file changes (`.DS_Store`, `__pycache__/`, `.env`)
- Merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)

---

### 2. Are there any hardcoded values that should be config?
Look for:
- URLs (`http://localhost:5173` instead of reading from config)
- Timeouts (`sleep(30)` instead of `settings.TIMEOUT`)
- Feature flags that should be in the `feature_flag` table, not in code
- Database paths that assume a specific directory structure
- Email addresses, API endpoints, version numbers embedded in logic

If a value might need to change between environments (dev/staging/production), it belongs in `settings.py` or environment variables, not inline.

---

### 3. Did I add tests for new behavior?
If the commit adds a new function, a new route, a new drill type, or changes the behavior of an existing function, there must be at least one test that verifies the new behavior.

**Minimum test expectations:**
- New route: at least a success case and an auth-required case
- New function: at least a normal case and an edge case
- Bug fix: a test that would have caught the bug (regression test)
- Schema change: verify the migration runs cleanly in test setup

If you cannot think of what to test, that's a sign the code may be too complex.

---

### 4. Did I check for SQL injection?
Every SQL query that includes user input must use parameterized queries.

**Vulnerable (NEVER do this):**
```python
db.execute(f"SELECT * FROM user WHERE email = '{email}'")
db.execute("SELECT * FROM user WHERE email = '%s'" % email)
```

**Safe:**
```python
db.execute("SELECT * FROM user WHERE email = ?", (email,))
```

Check every `db.execute()` call in the diff. If user input reaches the query through any path (direct parameter, URL path, form field, JSON body), it must be parameterized.

---

### 5. Did I handle the error case?
For every operation that can fail, ask: "What happens when this fails?"

**Common missed error cases in Aelu:**
- `db.execute().fetchone()` returns `None` — did I check for None before accessing fields?
- SQLite Row with LEFT JOIN — fields can be `None`. Use `row.get("field") or 0`, not `row["field"]`.
- `datetime.strptime()` with malformed input — wrap in try/except
- Division by zero in metrics calculations — check denominator
- File not found when loading content (passages, dialogues)
- WebSocket disconnect during drill submission

---

### 6. Is this the simplest solution?
Could this be done with fewer lines? Fewer abstractions? Fewer new files?

**Warning signs of over-engineering:**
- A new class where a function would suffice
- A new module for a single function
- An abstraction used in only one place
- A configuration option for something that will never change
- A factory pattern for something that is constructed once

The system already has 51 tables and 100+ source files. Every new abstraction must earn its place.

---

### 7. Would I understand this code in 6 months?
Read the code as if you've never seen it before. Ask:
- Are variable names descriptive? (`x` is bad. `drill_accuracy_pct` is good.)
- Are there comments explaining WHY, not just WHAT? (The code shows what. Comments should explain why.)
- Is the control flow linear or spaghetti? (If you can't trace the execution path without jumping between 5 files, simplify.)
- Are magic numbers explained? (`if score > 0.7` — what's 0.7? Add a constant: `MASTERY_THRESHOLD = 0.7`)

---

### 8. Did I update relevant docs?
If the commit changes:
- **Schema** → Update `BUILD_STATE.md` (schema version, new tables/columns), `schema.sql`
- **API routes** → Update `openapi.yaml`
- **Configuration** → Update `.env.example`
- **CLI commands** → Update `./run` help text
- **Dependencies** → Update `pyproject.toml`

Documentation debt is the sneakiest tech debt because nobody notices it until someone (future you) wastes an hour figuring out what changed.

---

### 9. Did I check the admin dashboard after deploy?
After deploying to production:
- Load the admin dashboard. Does it render?
- Check session metrics: any anomalies?
- Check crash_log: any new entries?
- Check client_error_log: any new JS errors?

This takes 2 minutes. Do it every time.

---

### 10. Did I run the full test suite?
```bash
cd ~/mandarin && source venv/bin/activate && pytest -q
```

Not "the tests I wrote." Not "the tests for the module I changed." ALL tests. The full suite should run in under 2 minutes. If it takes longer, that's a tech debt item.

If a test fails that you didn't expect, investigate before committing. Do NOT add `@pytest.mark.skip` to make it go away.

---

### 11. YAGNI Check: Is this feature actually needed right now?
YAGNI = You Aren't Gonna Need It.

Before committing a new feature, ask:
- Is there a user asking for this? (Real user, not hypothetical user.)
- Is there a backlog item for this?
- If I didn't build this, what would happen? (If the answer is "nothing," don't build it.)

Past YAGNI violations in Aelu (acknowledged in po-decision-log.md):
- Affiliate system built before having affiliates
- Classroom features built before having teachers
- HSK 7-9 content seeded before any user reached HSK 4

This doesn't mean those were wrong — but they were speculative. Acknowledge when you're building speculatively and accept the risk.

---

### 12. Security Check: OWASP Top 10
Quick scan of the diff against the OWASP Top 10:

| # | Vulnerability | What to Check |
|---|---|---|
| 1 | Injection | Parameterized SQL? No string interpolation in queries? |
| 2 | Broken Auth | Auth required on new routes? JWT validation? |
| 3 | Sensitive Data Exposure | No secrets in code? No PII in logs? HTTPS enforced? |
| 4 | XXE | Not applicable (no XML parsing) |
| 5 | Broken Access Control | Can user A access user B's data? Is `user_id` checked? |
| 6 | Security Misconfiguration | CSP headers set? Debug mode off in production? |
| 7 | XSS | User input escaped in templates? No `| safe` on user content? |
| 8 | Insecure Deserialization | No `pickle.loads` on user input? |
| 9 | Known Vulnerabilities | Dependencies up to date? `pip-audit` clean? |
| 10 | Insufficient Logging | Security events logged in `security_audit_log`? |

If you answer "no" or "I'm not sure" to any check, investigate before committing.

---

## Workflow

1. Write the code
2. Step away for 10 minutes (get coffee, stretch, look out the window)
3. Run the full test suite
4. Read the diff with this checklist open
5. Fix anything that fails a check
6. Commit

Total added time: 15-20 minutes per commit. This is cheap insurance against shipping bugs to production where you are the only person who can fix them at 11pm.
