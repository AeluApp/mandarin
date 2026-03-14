# ADR-003: Flask Over Django

## Status

Accepted (2025-10)

## Context

Aelu needed a Python web framework to serve its API (SRS calculations, drill selection, progress tracking), render web pages (dashboard, drills, graded reader, media shelf), and handle authentication (JWT for mobile, sessions for web). The web layer is relatively thin compared to the core SRS engine, which is a standalone Python library.

## Decision Drivers

- Core logic (SRS, drills, scheduling) is a standalone Python library, not web-framework-specific
- Need both HTML rendering (web dashboard) and JSON API (mobile clients)
- Solo developer: framework learning curve matters
- Need WebSocket support for real-time drill interactions
- Lightweight deployment on Fly.io (single process, small memory footprint)

## Considered Options

### Option 1: Django

- **Pros**: Batteries-included (ORM, admin, auth, forms, migrations), large ecosystem, well-documented
- **Cons**: Heavy for API-first app, ORM would compete with existing SQLite access layer, admin panel unnecessary (Aelu has its own admin routes), Django's auth system is session-based (would need Django REST Framework for JWT), larger memory footprint

### Option 2: Flask (chosen)

- **Pros**: Minimal core, blueprints for organization, Jinja2 templates, easy to add only what's needed, flask-sock for WebSocket, small memory footprint, natural fit for "library with a web layer" architecture
- **Cons**: No built-in ORM (not needed; Aelu uses raw SQLite), no built-in auth (implemented manually with JWT + sessions), no built-in migrations (handled by schema.sql + migration scripts), more manual setup for CSRF, rate limiting, security headers

### Option 3: FastAPI

- **Pros**: Modern async, automatic OpenAPI docs, type validation with Pydantic, high performance
- **Cons**: Async adds complexity without clear benefit for SQLite (single writer), Pydantic validation overhead for simple endpoints, less mature template rendering, would require separate template engine for HTML pages

## Decision

Use Flask with blueprints for route organization. The application is structured as:

```
mandarin/web/
    server.py          # Flask app factory, middleware, error handlers
    routes.py          # Core API routes (drills, sessions, progress)
    auth_routes.py     # Login, register, JWT refresh
    dashboard_routes.py # Web dashboard rendering
    session_routes.py  # Session management
    exposure_routes.py # Reader, media shelf, listening
    grammar_routes.py  # Grammar drills and progress
    payment_routes.py  # Stripe integration
    classroom_routes.py # Teacher/classroom features
    gdpr_routes.py     # Data export, deletion
    admin_routes.py    # Admin dashboard
    ...
```

Each blueprint groups related routes. The Flask app is created by `server.py` and served by gunicorn with gevent workers.

## Consequences

### Positive

- **Thin web layer**: The Flask app is a ~200-line server.py plus route files. The web framework doesn't dictate application architecture.
- **Blueprint organization**: 20+ route files are cleanly separated by domain. Each blueprint registers its own URL prefix.
- **Manual auth control**: JWT implementation (`mandarin/jwt_auth.py`) and session management (`mandarin/web/session_store.py`) are fully custom, giving precise control over token lifetimes, refresh logic, MFA integration, and the dual auth pattern (ADR-005).
- **Small footprint**: Flask + gunicorn uses ~80MB RAM for 2 workers, leaving headroom on a 512MB Fly.io machine.
- **WebSocket via flask-sock**: Real-time drill interactions and audio streaming use flask-sock, which integrates cleanly with Flask's routing.

### Negative

- **Manual security**: CSRF protection, rate limiting, security headers, and input validation are all manually implemented. Each is a potential vulnerability if misconfigured. Mitigated by security scanning (bandit + pip-audit, see ADR-009).
- **No ORM migrations**: Schema changes require manual SQL migration scripts. This is acceptable for a single-database application but would be painful with multiple database backends.
- **Template limitations**: Jinja2 is powerful but server-rendered. As the web UI grows more interactive, the boundary between server-rendered templates and client-side JavaScript becomes awkward. The current bridge.js handles this, but a future SPA migration may be warranted.

### Revisit Trigger

Consider migrating to FastAPI if:
- The API needs async I/O (e.g., external API calls become a bottleneck)
- Auto-generated OpenAPI docs become important for third-party integrations
- The web UI migrates to a full SPA (React/Vue) and Flask's template rendering is no longer needed
