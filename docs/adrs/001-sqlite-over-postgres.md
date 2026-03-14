# ADR-001: SQLite Over PostgreSQL

## Status

Accepted (2025-10)

## Context

Aelu needed a persistent data store for user accounts, SRS progress, session logs, review events, content items, and several supporting tables (29+ tables as of schema v29). The application runs on a single Fly.io machine serving a Flask API to web, iOS (Capacitor), and macOS clients.

The developer is a solo operator building a niche Mandarin learning product. Operational simplicity directly affects development velocity. Time spent managing database infrastructure is time not spent on pedagogy.

## Decision Drivers

- Solo developer: no DBA, no ops team
- Single-server deployment on Fly.io ($5-20/mo budget)
- Read-heavy workload: ~75% reads, ~25% writes
- Need for zero-config backups (Litestream)
- Offline-first philosophy (SQLite can run embedded on client if needed)
- No need for concurrent multi-writer access at current scale

## Considered Options

### Option 1: PostgreSQL

- **Pros**: Industry standard, concurrent writes, rich extension ecosystem (PostGIS, pg_trgm, jsonb), connection pooling, multi-region replicas (Neon, Supabase)
- **Cons**: Requires managed service ($15-50/mo minimum), connection management complexity, network latency on every query, operational overhead (vacuuming, connection limits, SSL cert management)

### Option 2: MySQL

- **Pros**: Widely deployed, good tooling, PlanetScale for serverless
- **Cons**: Same operational overhead as PostgreSQL with fewer modern features, worse JSON support, less natural fit for Python ecosystem

### Option 3: SQLite with WAL Mode (chosen)

- **Pros**: Zero-config, single-file database, no network latency, sub-millisecond reads, embedded in Python stdlib, Litestream for streaming backups, WAL mode allows concurrent reads during writes
- **Cons**: Single writer (serialized writes), no built-in replication, scaling ceiling, no ALTER CHECK constraints (must recreate tables), no native connection pooling

## Decision

Use SQLite with WAL mode as the primary data store. Configure `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`. Use Litestream for continuous backup to S3-compatible storage.

Key configuration:
```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

## Consequences

### Positive

- **Zero operational overhead**: No database server to manage, monitor, or upgrade. The database is a single file (`mandarin.db`) that can be copied, backed up, or inspected with standard tools.
- **Sub-millisecond reads**: No network round-trip. A progress lookup takes ~0.5ms vs ~5-15ms for a networked PostgreSQL query.
- **Litestream integration**: Continuous replication to S3 with point-in-time recovery. Simpler than PostgreSQL WAL archiving.
- **Development/production parity**: The same SQLite file works identically in development and production. No "works on my machine" database issues.
- **Cost**: $0/month for the database itself. Only storage costs for Litestream backups (~$0.50/mo for <1GB).

### Negative

- **Scaling ceiling**: The single-writer bottleneck becomes a constraint at ~80,000 write-heavy DAU (see `docs/operations-research/queue-model.md`). For Aelu's current and near-term scale (<1,000 users), this is irrelevant.
- **No concurrent writes**: Long write transactions block other writes. Mitigated by keeping write transactions short (<50ms) and using `busy_timeout` for retry.
- **Schema migration friction**: SQLite lacks ALTER TABLE support for CHECK constraints, column type changes, and some ALTER operations. Must use CREATE TABLE + INSERT + DROP pattern.
- **No connection pooling**: Each Flask request creates a new connection. For SQLite, this is fast (~0.1ms) but means no shared prepared statements across requests.

### Revisit Trigger

Revisit this decision when any of the following occur:
- DAU exceeds 5,000 (write contention becomes measurable)
- Multi-region deployment is required (SQLite is single-node)
- A feature requires full-text search at scale (SQLite FTS5 is limited)
- A feature requires transactional guarantees across multiple services

At that point, migrate to PostgreSQL using Neon or Supabase. The migration path is straightforward: schema is standard SQL with minor SQLite-isms (`datetime('now')` -> `NOW()`, `INTEGER PRIMARY KEY AUTOINCREMENT` -> `SERIAL`).
