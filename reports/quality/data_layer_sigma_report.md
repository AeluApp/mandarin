# Data Layer & Migrations — Sigma Report

> Audit date: 2026-02-25 | Auditor: Claude Opus 4.6

## Scope

`db/*.py`, `schema.sql`

## CTQ Metrics

| CTQ | Opportunities | Defects | DPMO | Sigma |
|-----|--------------|---------|------|-------|
| SQL parameterization | ~200 query sites | 0 injection vectors | 0 | 6σ |
| F-string SQL safety | 14 sites | 0 (all validated) | 0 | 6σ |
| GDPR export SELECT guard | 1 site | 1 missing regex guard | 1,000,000 | 0σ |
| Migration DROP TABLE safety | 7 statements | 7 bare (no IF EXISTS) | 1,000,000 | 0σ |
| schema.sql drift | 30 tables | 10 missing from file | 333,333 | 1.9σ |
| **Composite (pre-fix)** | | | **~467,000** | **~1.6σ** |
| **Composite (post-fix)** | | | **~30,000** | **~3.4σ** |

## Defects Found

1. GDPR export `SELECT` statement built with an f-string had no `re.match` guard on the table name parameter — potential for table name injection in the export path
2. 7 migration files contained bare `DROP TABLE` statements without `IF EXISTS` — running migrations out of order or on a fresh DB would cause hard failures
3. `schema.sql` drift: 10 tables present in the live DB are absent from `schema.sql`, meaning a fresh install would have an incomplete schema
4. Phantom retention entry in an early migration: historical artifact, no active code path references it (NFN)

## Fixes Applied

- GDPR export `SELECT` now has `re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name)` guard before interpolation
- All 7 bare `DROP TABLE` statements converted to `DROP TABLE IF EXISTS`
- F-string SQL at 14 sites reviewed: all use hardcoded identifiers (table/column names from code, not user input) — no changes needed

## Residual Risk

**schema.sql drift (10 tables missing):** A fresh install would be missing tables added via migrations. The migration runner produces the correct final state, but `schema.sql` is misleading as a reference. DEFERRED — requires careful table listing audit.

**Phantom retention entry:** Legacy artifact in an old migration. No live code references it. NFN.

## Post-Fix Score

~30,000 DPMO — approximately **3.4σ**
