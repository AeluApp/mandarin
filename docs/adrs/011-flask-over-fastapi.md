# ADR-002: Use Flask Instead of FastAPI

## Status

Accepted (2025-01)

## Context

Aelu needs a Python web framework for:

- Server-rendered HTML pages (Jinja2 templates for the web UI)
- REST API endpoints for mobile (Capacitor) and CLI clients
- WebSocket support for real-time features (drill audio streaming)
- Session-based auth (web) and JWT auth (mobile API)
- Integration with SQLite (synchronous I/O)

Options considered:

1. **Flask** with Jinja2 templates and gevent for async I/O
2. **FastAPI** with Jinja2 and uvicorn
3. **Django** with Django REST Framework

## Decision

Use **Flask** with gevent workers via gunicorn.

## Rationale

### Why Flask

1. **Synchronous model matches SQLite.** SQLite operations are synchronous (no native async driver). Flask's synchronous request handling avoids the complexity of running sync SQLite calls inside async event loops (which requires `run_in_executor` or `databases` library workarounds).

2. **Jinja2 is native.** Flask includes Jinja2 for server-rendered templates. The "Civic Sanctuary" web UI uses server-rendered HTML with progressive enhancement, not a SPA. Flask's `render_template()` is the natural fit.

3. **Mature ecosystem.** Flask-Login for session auth, flask-sock for WebSocket, WTForms for form validation. Stable, well-documented, battle-tested.

4. **Simplicity.** For a solo developer, Flask's explicit routing and minimal magic reduce cognitive overhead. Every request handler is a plain function. No dependency injection, no Pydantic models required (though used selectively for API validation).

5. **gevent provides sufficient concurrency.** With 2 gunicorn workers using gevent, Aelu can handle hundreds of concurrent connections. The bottleneck is SQLite write throughput, not web framework throughput.

### Why Not FastAPI

1. **Async complexity for no benefit.** FastAPI's primary advantage is async/await for I/O-bound workloads (database queries, HTTP calls). Aelu's database is SQLite (synchronous), and external I/O (edge-tts) is handled in background workers, not request handlers.

2. **No native Jinja2 integration.** FastAPI can use Jinja2 but it's not idiomatic. FastAPI is designed for API-first (JSON responses), not server-rendered HTML.

3. **Pydantic v2 migration churn.** The Pydantic v1-to-v2 migration (2023-2024) caused ecosystem disruption. Flask avoids this dependency.

4. **Smaller deployment surface.** Flask + gunicorn is a simpler process model than FastAPI + uvicorn. Fewer moving parts in production.

### Why Not Django

1. **Too heavy.** Django's ORM, admin panel, migration system, and middleware stack are overkill for Aelu's needs. The schema is managed via raw SQL (`schema.sql`), not an ORM.

2. **ORM doesn't support SQLite well at scale.** Django's ORM generates SQL that may not optimize well for SQLite's query planner.

3. **Convention over configuration.** Django's opinionated project structure adds files and directories that a solo developer doesn't need.

## Consequences

### Positive

- Request handlers are simple functions with minimal boilerplate
- Template rendering is first-class (`render_template()`)
- gevent workers handle WebSocket and long-polling without blocking
- Deployment is `gunicorn -w 2 -k gevent app:app`
- Flask-Login handles session cookies; custom JWT middleware handles API auth

### Negative

- No native async/await (gevent monkey-patches instead)
- No automatic API documentation (Swagger/OpenAPI) — must document manually
- No built-in request validation (added manually or via marshmallow)
- Type hints are not enforced at the framework level

### Neutral

- Flask 2.x+ supports async views (via `async def`), but we don't use them (SQLite is sync)
- The `flask-sock` library handles WebSocket adequately for current needs (audio streaming)

## Revisit Triggers

1. **API latency p95 exceeds 500ms SLO consistently** — may need async I/O for external service calls
2. **Migration to PostgreSQL** — async PostgreSQL drivers (asyncpg) would make FastAPI's async model beneficial
3. **API-first mobile client** — if the Capacitor shell is replaced with a native app consuming a JSON API, FastAPI's auto-documentation and Pydantic validation become more valuable
4. **Team growth** — FastAPI's type-enforced request/response models reduce integration bugs in multi-developer teams
