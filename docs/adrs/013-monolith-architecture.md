# ADR-005: Monolith Architecture Instead of Microservices

## Status

Accepted (2025-01)

## Context

Aelu consists of several functional domains:

- **Auth:** User registration, login, JWT, sessions
- **SRS Engine:** Spaced repetition scheduling, progress tracking
- **Drill System:** Drill selection, grading, modality management
- **Content:** Vocabulary items, grammar points, context notes, dialogues
- **Audio:** TTS generation (edge-tts), tone grading
- **Analytics:** Session stats, HSK projections, diagnostics
- **Web UI:** Flask templates, static assets, WebSocket
- **API:** REST endpoints for mobile and CLI clients

These could be deployed as separate services or as a single application.

## Decision

Deploy everything as a **single Flask application** (monolith).

## Rationale

### Why Monolith

1. **Solo developer.** Microservices add operational overhead per service: separate deployments, inter-service communication, distributed tracing, service discovery. For one developer, this overhead dwarfs any architectural benefit.

2. **Shared database.** All domains read from and write to the same SQLite database. Splitting into services while sharing a database (the "distributed monolith" anti-pattern) adds network latency without gaining independence.

3. **Simple deployment.** One Dockerfile, one `fly deploy`, one health check. No service mesh, no API gateway, no message queue.

4. **Cross-domain transactions.** A single drill submission touches auth (verify user), SRS (update progress), content (fetch item details), and analytics (log event). In a monolith, this is a single SQLite transaction. In microservices, this becomes a distributed saga.

5. **Latency.** In-process function calls are nanoseconds. Inter-service HTTP calls are milliseconds. For a real-time drill interaction (user submits answer → sees result), minimizing latency matters.

### Application Structure

The monolith is organized as a modular monolith — logically separated packages within one process:

```
mandarin/
├── app.py              # Flask app factory, route registration
├── auth.py             # Authentication (sessions + JWT)
├── srs.py              # SRS engine (scheduling, half-life regression)
├── drills.py           # Drill selection, grading
├── content.py          # Vocabulary, grammar, context notes
├── audio.py            # TTS generation, tone grading
├── analytics.py        # Stats, projections, diagnostics
├── web/                # Flask templates, static assets
│   ├── templates/
│   └── static/
├── api/                # REST API routes
├── db.py               # SQLite connection management
├── schema.sql          # Database schema (51 tables)
└── tests/              # 1,300+ tests
```

Modules communicate via function calls and shared database access. There are no HTTP calls between modules.

## Consequences

### Positive

- Single deployment artifact (Docker image)
- All code in one repository, one test suite
- Refactoring across domains is straightforward (IDE rename, single PR)
- No inter-service latency
- No distributed systems failure modes (network partitions, cascading failures, circuit breakers)

### Negative

- **All-or-nothing deploys.** A bug in the analytics module takes down the entire app, including drill serving. Mitigated by thorough testing (1,343 tests) and health checks.
- **Scaling is uniform.** Cannot independently scale the audio generation module (CPU-intensive) without scaling everything. Mitigated by the fact that audio generation is rare and fast (edge-tts is an external service call).
- **Module coupling risk.** Without discipline, modules can become entangled. Mitigated by code review (self-review) and clear import boundaries.
- **Memory pressure.** All modules share the 512MB memory allocation. A memory leak in any module affects the whole process.

### Neutral

- The monolith can be split later. Module boundaries are already defined by file/package structure. Extracting a module into a service requires: (1) defining an API contract, (2) replacing function calls with HTTP calls, (3) deploying separately. Estimated effort per module: 1-2 days.

## Revisit Triggers

1. **Team grows beyond 3 developers** — module ownership becomes important, independent deployment cycles reduce coordination cost
2. **Need for independent scaling** — if one module (e.g., audio generation) has vastly different resource needs than others
3. **Deployment frequency exceeds 10x/day** — if deploys become bottlenecked by other modules' changes (unlikely for solo developer)
4. **Fault isolation required** — if analytics processing crashes should not affect drill serving (currently they can)
5. **Different technology needs** — if a module would benefit from a different language/runtime (e.g., Rust for tone grading performance)
