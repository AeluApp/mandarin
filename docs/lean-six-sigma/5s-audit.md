# 5S Audit — Aelu Codebase

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Audit Date:** 2026-03-10
**Overall Score:** 18/25

---

## 1. Sort (Seiri) — Remove what is not needed

**Score: 3/5**

### What's Been Done
- Removed dead loggers (identified and eliminated in waste register)
- Cleaned 2 unused imports
- Removed redundant `TESTING` config
- Fixed schema.sql drift

### What Needs Attention

#### Grammar Extra Files (10 files)

| File | HSK Range | Round | Status | Verdict |
|------|-----------|-------|--------|---------|
| `grammar_extra_hsk1_3.py` | 1-3 | R1 (original) | Active — imported by drill dispatch | Keep |
| `grammar_extra_hsk4_6.py` | 4-6 | R1 | Active | Keep |
| `grammar_extra_hsk7_9.py` | 7-9 | R1 | Active | Keep |
| `grammar_extra_hsk1_2_r2.py` | 1-2 | R2 (revision) | Unclear — is this additive or replacement? | **Audit needed** |
| `grammar_extra_hsk3_4_r2.py` | 3-4 | R2 | Unclear | **Audit needed** |
| `grammar_extra_hsk5_6_r2.py` | 5-6 | R2 | Unclear | **Audit needed** |
| `grammar_extra_hsk7_9_r2.py` | 7-9 | R2 | Unclear | **Audit needed** |
| `grammar_extra_hsk1_3_r3.py` | 1-3 | R3 (latest) | Unclear | **Audit needed** |
| `grammar_extra_hsk4_5_r3.py` | 4-5 | R3 | Unclear | **Audit needed** |
| `grammar_extra_hsk6_9_r3.py` | 6-9 | R3 | Unclear | **Audit needed** |

**Questions to resolve:**
1. Do R2/R3 files replace R1 files, or supplement them?
2. Are all entries in these files actually loaded and used by the drill system?
3. Can we consolidate to a single file per HSK band with version control handling history?

**Action:** Grep for import statements referencing each file. Any file not imported anywhere is dead code and should be removed.

#### Dead/Dormant Directories

| Directory | Purpose | Active? | Verdict |
|-----------|---------|---------|---------|
| `flutter_app/` | Flutter mobile prototype | Not in production | **Consider removing** (or archiving to a branch) |
| `desktop/` | Desktop app | Unknown | **Audit needed** |
| `k8s/` | Kubernetes configs | Not used (Fly.io deployment) | **Consider removing** if no Kubernetes plans |
| `mobile/` | Mobile-related code | Unknown overlap with flutter_app | **Audit needed** |
| `content_gen/` | Content generation scripts | Used for seed data generation | Keep |
| `tools/` | Development tools/scripts | Unknown | **Audit needed** |
| `build/` | Build artifacts | Should be in `.gitignore` | **Verify** |
| `dist/` | Distribution artifacts | Should be in `.gitignore` | **Verify** |

#### Features Without Users

| Feature | Schema/Code | Users | Verdict |
|---------|------------|-------|---------|
| Classroom system | `classroom`, `classroom_student`, LTI tables | 0 teachers | **Freeze** — no new investment |
| Affiliate system | `affiliate_partner`, `referral_tracking`, `affiliate_commission`, `discount_code` | 0 affiliates | **Freeze** |
| LTI integration | `lti_platform`, `lti_user_mapping`, `lti_routes.py` | 0 LTI connections | **Freeze** |
| xAPI export | `xapi.py` | 0 LRS consumers | **Freeze** |

### Sort Action Items
- [ ] Audit all grammar_extra files for import usage
- [ ] Remove or archive flutter_app/ if not production
- [ ] Audit desktop/, mobile/, k8s/, tools/ directories
- [ ] Verify build/ and dist/ are in .gitignore
- [ ] Document frozen features so they don't attract new development

---

## 2. Set in Order (Seiton) — A place for everything

**Score: 4/5**

### Current File Organization

```
mandarin/
├── __init__.py, __main__.py           # Package entry
├── cli.py, menu.py                    # CLI interface
├── runner.py                          # Session runner (core loop)
├── scheduler.py                       # SRS session planning
├── config.py                          # Configuration constants
├── db/                                # Database layer
│   ├── __init__.py (core DB functions)
│   ├── content.py
│   ├── curriculum.py
│   ├── profile.py
│   └── session.py
├── drills/                            # Drill engine
│   ├── __init__.py
│   ├── dispatch.py (registry + dispatcher)
│   ├── base.py (DrillResult, helpers)
│   ├── hints.py
│   ├── mc.py (implicit — imported but not in glob)
│   ├── pinyin.py
│   ├── tone.py
│   ├── listening.py
│   ├── production.py
│   ├── speaking.py
│   ├── advanced.py
│   ├── number.py (implicit)
│   └── grammar_drills.py (implicit)
├── web/                               # Web interface
│   ├── server.py (Flask app factory)
│   ├── routes.py (main routes)
│   ├── bridge.py (SPA bridge)
│   ├── auth_routes.py
│   ├── session_routes.py
│   ├── payment_routes.py
│   ├── settings_routes.py
│   ├── grammar_routes.py
│   ├── export_routes.py
│   ├── gdpr_routes.py
│   ├── lti_routes.py
│   ├── mfa_routes.py
│   ├── onboarding_routes.py
│   ├── landing_routes.py
│   ├── marketing_routes.py
│   ├── seo_routes.py
│   ├── sync_routes.py
│   ├── token_routes.py
│   ├── api_errors.py
│   ├── middleware.py
│   ├── session_store.py
│   ├── rate_limit_store.py
│   ├── push.py
│   ├── wsgi.py
│   ├── retention_scheduler.py
│   ├── stale_session_scheduler.py
│   └── email_scheduler.py
├── grammar_extra_*.py (x10)           # Grammar drill data (flat)
├── auth.py, jwt_auth.py, mfa.py       # Auth layer
├── payment.py, tier_gate.py           # Commerce
├── email.py                           # Email via Resend
├── security.py                        # Security utilities
├── feature_flags.py                   # Feature flag system
├── churn_detection.py                 # Churn analytics
├── retention.py                       # Half-life retention model
├── metrics_report.py                  # Session reporting
├── improve.py                         # Self-improvement engine
├── milestones.py                      # Streak/milestone tracking
├── context_notes.py                   # Context note management
├── tone_grading.py                    # Tone analysis
├── audio.py                           # Audio playback
├── display.py                         # Display formatting
├── ui_labels.py                       # Canonical UI labels
├── placement.py                       # Placement test
├── caliper.py                         # Learning analytics (Caliper)
├── validator.py                       # Input validation
├── personalization.py                 # Content personalization
├── media.py                           # Media shelf
├── conversation.py                    # Dialogue scenarios
├── export.py, cc_export.py            # Data export
├── data_retention.py                  # GDPR data purge
├── log_config.py                      # Logging setup
├── settings.py                        # User settings
├── tone_features.py                   # Tone feature extraction
├── marketing_hooks.py                 # Marketing analytics
├── scenario_loader.py                 # Scenario data loading
├── grammar_linker.py                  # Grammar-content linking
├── grammar_seed.py                    # Grammar data seeding
├── importer.py                        # Data import
├── scheduler_lock.py                  # Distributed lock
├── telemetry.py                       # Client telemetry
├── wiring.py                          # Dependency injection
└── doctor.py                          # System diagnostics
```

### Assessment
- **Good:** `db/`, `drills/`, `web/` subdirectories provide logical grouping for the three main subsystems
- **Good:** Single-responsibility files with clear names
- **Issue:** Grammar extra files (10) are flat in the root package — should be in a `grammar_data/` subdirectory or consolidated
- **Issue:** Some files in root that could be grouped: `auth.py + jwt_auth.py + mfa.py + security.py` → `auth/` package
- **Issue:** `caliper.py`, `xapi.py`, `cc_export.py` are learning analytics standards that could be grouped

### Recommendations
1. Move grammar_extra files to `mandarin/grammar_data/` subdirectory
2. Consider `mandarin/auth/` package for auth-related modules (only if refactoring is needed anyway)
3. Keep current flat structure for most files — over-packaging creates navigation overhead for a solo dev

---

## 3. Shine (Seiso) — Clean and inspect

**Score: 4/5**

### Lint Status

**Ruff configuration** (from `pyproject.toml`):
```toml
[tool.ruff]
target-version = "py39"
line-length = 120
select = ["E", "W", "F", "B", "S", "UP"]
ignore = ["E501", "S101", "S311", "B904"]
```

- Ruff rules: pycodestyle (E/W), pyflakes (F), bugbear (B), bandit security (S), pyupgrade (UP)
- Line length: 120 (generous, avoids excessive wrapping)
- Python target: 3.9 (matches dev environment)

**Current status:** Pre-commit hook runs ruff on every commit. The codebase should be ruff-clean if hooks are enforced.

**Action:** Run `ruff check mandarin/` and verify zero violations.

### Security Scanning

**Gitleaks** is configured in `.pre-commit-config.yaml`:
```yaml
- repo: https://github.com/gitleaks/gitleaks
  rev: v8.18.4
  hooks:
    - id: gitleaks
```

**Status:** Active — prevents secret commits.

**Additional security:**
- Bandit rules enabled via ruff's `S` selector
- `S101` (assert) and `S311` (random) ignored appropriately
- Fly.io secrets managed via `fly secrets set` (not in code)

### Test Coverage

Coverage configuration:
```toml
[tool.coverage.run]
source = ["mandarin"]
omit = ["mandarin/cli.py", "mandarin/menu.py", "mandarin/audio.py", ...]

[tool.coverage.report]
fail_under = 53
```

- `fail_under = 53` — minimum coverage threshold
- ~1,300 tests in the suite
- Coverage omits CLI, audio, templates, and server wiring (IO-heavy code)

**Improvement opportunity:** Raise `fail_under` to 60% as coverage grows.

---

## 4. Standardize (Seiketsu) — Make standards visible

**Score: 4/5**

### Coding Standards Documented

| Standard | Where Documented | Enforced? |
|----------|-----------------|-----------|
| Line length (120) | `pyproject.toml` [tool.ruff] | Yes (ruff pre-commit) |
| Python version (3.9) | `pyproject.toml` [tool.ruff] + Dockerfile (3.12 prod) | Yes (ruff UP rules) |
| Security rules (bandit) | `pyproject.toml` [tool.ruff] select S | Yes (ruff pre-commit) |
| Secret detection | `.pre-commit-config.yaml` (gitleaks) | Yes (pre-commit) |
| SQL injection prevention | Manual review (parameterized queries) | Partially (no automated check) |
| Error type taxonomy | `schema.sql` CHECK constraint | Yes (database-level enforcement) |
| Drill type registry | `drills/dispatch.py` DRILL_REGISTRY | Yes (runtime validation) |
| DB Row access pattern | `x.get("field") or 0` for LEFT JOIN nulls | Convention (not enforced) |
| UTC datetime | `datetime.now(timezone.utc)` in Python, `datetime('now')` in SQLite | Convention (not enforced) |
| Chinese writing quality | `chinese_writing_standard.md` | Manual review |
| Storytelling quality | `storytelling_standard.md` | Manual review |

### Missing Standards
- No documented API response format standard (JSON structure varies by endpoint)
- No documented error response format standard
- No documented commit message format
- No documented branch naming convention

---

## 5. Sustain (Shitsuke) — Maintain the discipline

**Score: 3/5**

### Pre-commit Hooks

Currently active (`.pre-commit-config.yaml`):
1. **ruff** — Linting and formatting (v0.4.4)
2. **gitleaks** — Secret detection (v8.18.4)

### What's Missing

| Hook | Purpose | Priority |
|------|---------|----------|
| pytest (quick subset) | Catch test regressions before commit | High |
| ruff format check | Enforce consistent formatting (not just linting) | Medium |
| mypy (type checking) | Catch type errors | Low (no type annotations in most code) |
| SQL schema validation | Verify schema.sql parses cleanly | Low |

### Discipline Practices

| Practice | Status | Notes |
|----------|--------|-------|
| Run tests before deploying | Manual — not automated | Should be in CI/CD pipeline |
| Review crash_log at session start | Documented in MEMORY.md | Requires discipline |
| Monthly SPC review | Not yet practiced | New (this document) |
| VoC interviews monthly | Not yet practiced | New (voc-program.md) |
| Waste register updates | Not yet practiced | New (waste-register.md) |

### Sustainability Risks
1. **Solo founder fatigue** — Many maintenance tasks documented here depend on one person remembering to do them. No backup.
2. **Automation gap** — Many checks are manual SQL queries. Should be automated into `./run audit` or similar.
3. **Pre-commit hooks not covering tests** — Code can be committed that breaks tests. Tests only run manually or in CI (if CI exists).

---

## 6. Scoring Summary

| S | Score | Rationale |
|---|-------|-----------|
| Sort | 3/5 | Dead loggers removed, imports cleaned, but 10 grammar_extra files unaudited, several directories of unknown status, features built without users |
| Set in Order | 4/5 | Good directory structure (db/, drills/, web/), clear file naming, but grammar_extra files misplaced in root |
| Shine | 4/5 | Ruff + gitleaks active, bandit security rules on, coverage tracked, but coverage threshold is low (53%) |
| Standardize | 4/5 | Key standards documented and enforced (ruff, gitleaks, DB constraints), but API format and commit message standards missing |
| Sustain | 3/5 | Pre-commit hooks exist but incomplete (no tests), many maintenance tasks are manual, solo founder dependency |
| **Total** | **18/25** | |

---

## 7. Action Items (Prioritized)

| Priority | Action | 5S Category | Effort |
|----------|--------|-------------|--------|
| 1 | Audit grammar_extra files — remove dead ones | Sort | 2 hours |
| 2 | Audit flutter_app/, desktop/, k8s/, mobile/ — remove or archive | Sort | 1 hour |
| 3 | Add pytest quick-subset to pre-commit hooks | Sustain | 30 min |
| 4 | Raise coverage fail_under to 60% | Shine | 1 hour (adding tests) |
| 5 | Move grammar_extra files to grammar_data/ subdirectory | Set in Order | 1 hour |
| 6 | Create `./run audit` CLI command for automated 5S checks | Sustain | 4 hours |
| 7 | Document API response format standard | Standardize | 1 hour |
| 8 | Verify build/ and dist/ are in .gitignore | Sort | 5 min |
