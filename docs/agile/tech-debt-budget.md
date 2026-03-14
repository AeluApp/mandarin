# Aelu Tech Debt Budget

**Last Updated:** 2026-03-10

---

## Policy

**Allocate 20% of each sprint to tech debt work.** For a 2-week sprint with ~8 productive coding days, this means roughly 1.5-2 days dedicated to tech debt per sprint.

This is not optional. Tech debt compounds like financial debt. Skipping tech debt work to ship features faster is borrowing from the future. The 20% allocation is a floor, not a ceiling.

### What Counts as Tech Debt Work
Tech debt is any work that improves the codebase's health without adding user-facing features. It reduces the cost of future changes.

### What Does NOT Count as Tech Debt Work
- Bug fixes (those are defects, not debt)
- New features (even if they touch messy code)
- Refactoring that is part of a feature story (that's just good engineering within the feature)

---

## Tech Debt Categories

### 1. Test Coverage Gaps
Work that increases test coverage or test quality. Adding tests for untested modules, replacing brittle tests with robust ones, adding missing edge case tests.

**Current known gaps:**
- E2E test coverage is at ~2% (target: 10%). See test-pyramid-analysis.md.
- No contract tests for the API consumed by the Capacitor mobile app.
- No property-based tests for the scheduler module (only SRS has hypothesis tests).
- Coverage floor percentage is not measured and documented.

### 2. Dead Code Removal
Identifying and removing code that is no longer called, referenced, or needed. Dead code confuses future readers (including future Jason) and makes the codebase feel larger than it is.

**Current known dead code:**
- `flutter_app/` directory — Flutter was explored and abandoned in favor of Capacitor. The directory contains generated code, platform scaffolding, and early prototypes that are not used.
- Possible dead grammar extra files — multiple `grammar_extra_hsk*` files exist. Verify all are imported and used.
- `rewrite_hsk4.py`, `rewrite_hsk5.py`, `rewrite_passages.py` at repo root — one-time migration scripts that may no longer be needed.

### 3. Documentation Drift
Documentation that no longer matches the codebase. Schema docs that don't reflect v41. API docs that miss endpoints added in Phase A-F. BUILD_STATE.md sections that describe planned work as if it's complete (or vice versa).

**Current known drift:**
- BUILD_STATE.md references SCHEMA_VERSION=26 in one section but v41 in the header — need to verify consistency.
- `openapi.yaml` may not include the 8 new API routes added in Phase A-F (token, sync, push endpoints).
- `docs/` subdirectories contain framework documents that may reference outdated architecture.

### 4. Dependency Updates
Keeping Python packages and JavaScript dependencies current. Security patches, compatibility updates, removing pinned versions that are no longer necessary.

**Current known items:**
- `pyproject.toml` pins PyJWT>=2.8.0 — check if a newer version is available.
- Capacitor 6 dependencies in `mobile/package.json` — check for Capacitor updates.
- Run `pip-audit` and `npm audit` (for mobile/) quarterly.
- Python 3.9.6 is the runtime — check whether 3.10+ is feasible on Fly.io and macOS.

### 5. Performance Optimization
Work that makes the system faster or more resource-efficient without changing behavior. Query optimization, caching, reducing payload sizes.

**Current known items:**
- No load testing baseline exists. Unknown how many concurrent users the Fly.io instance supports.
- SQLite WAL mode is enabled but `PRAGMA` settings have not been tuned for production workload.
- No query performance monitoring — slow queries are invisible.
- GDPR data export for large accounts may be slow (see PB-025).

### 6. Code Quality
Refactoring for clarity, extracting duplicated logic, improving naming, splitting oversized modules.

**Current known items:**
- `mandarin/scheduler.py` has 124 tests, suggesting the module is large and complex. May benefit from decomposition.
- Route files in `mandarin/web/` may contain business logic that should be in service modules.
- Multiple `grammar_extra_*` files suggest a pattern that could be consolidated into a data-driven approach.

---

## Tech Debt Ledger

Track tech debt work completed and planned per sprint.

### Completed Tech Debt Work

| Date | Category | Work Done | Time Spent | Impact |
|---|---|---|---|---|
| 2026-02 (pre-sprints) | Code Quality | Flaky test fix | ~2 hours | Eliminated intermittent CI failures |
| 2026-02 (pre-sprints) | Documentation Drift | schema.sql sync with production schema | ~1 hour | Schema file now matches v41 |
| 2026-02 (pre-sprints) | Dead Code | Dead logger removal | ~30 min | Removed unused logging module |
| 2026-02 (pre-sprints) | Dead Code | FIX_INVENTORY cleanup | ~1 hour | Removed completed fix tracking that was no longer needed |

### Sprint Tech Debt Budget

| Sprint | Days Allocated | Days Used | Category | Work Planned | Status |
|---|---|---|---|---|---|
| Sprint 1 | 1.5 | — | Test Coverage | Measure coverage floor, document baseline | Planned |
| Sprint 2 | 1.5 | — | Dead Code | Audit grammar_extra files, remove unused scripts | Planned |
| Sprint 3 | 1.5 | — | Dependencies | Run pip-audit, update outdated packages | Planned |
| Sprint 4 | 1.5 | — | Test Coverage | Add 2 E2E test scenarios | Planned |
| Sprint 5 | 1.5 | — | Performance | Set up load testing baseline with Locust | Planned |
| Sprint 6 | 1.5 | — | Documentation | Sync openapi.yaml with Phase A-F routes | Planned |

---

## Prioritization

When choosing which tech debt to work on in a given sprint, use this priority order:

1. **Security vulnerabilities** (dependency CVEs, bandit findings) — always first
2. **Test coverage for recently changed modules** — prevent regressions in active code
3. **Dead code in areas you're currently working in** — clean as you go
4. **Documentation for recently shipped features** — while context is fresh
5. **Performance work** — only when evidence (user complaints, slow queries) justifies it
6. **Speculative refactoring** — only when the code is actively causing confusion or bugs

Do NOT do tech debt work on modules you're not planning to touch soon. Focus cleanup where it reduces friction for upcoming work.

---

## Tracking Metrics

| Metric | Target | How to Measure |
|---|---|---|
| Sprint tech debt allocation | 20% (1.5-2 days) | Self-reported in sprint retrospective |
| Tech debt backlog size | Decreasing or stable | Count items in the ledger above |
| Test coverage | Non-decreasing | `pytest --cov=mandarin --cov-fail-under=X` |
| Dependency vulnerabilities | 0 critical, 0 high | `pip-audit` quarterly |
| Dead code lines removed per quarter | >0 | Git diff stats |

---

## Anti-Patterns to Avoid

- **"We'll clean it up later"** — Later never comes. Allocate time now.
- **"Tech debt sprint"** — Don't save all debt for a dedicated sprint. Spread it across every sprint. A "tech debt sprint" signals that regular sprints are creating debt faster than it's being paid down.
- **Gold-plating disguised as tech debt** — Rewriting a working module because you don't like the style is not tech debt work. It's gold-plating. Tech debt work has a measurable outcome: faster tests, fewer warnings, updated dependencies, removed dead code.
- **Counting bug fixes as tech debt** — Bugs are defects, not debt. They go in the sprint backlog as regular work, not the tech debt budget.
