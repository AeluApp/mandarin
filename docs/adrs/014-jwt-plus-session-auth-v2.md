# ADR-006: Dual Auth (Session Cookies + JWT)

## Status

Accepted (2026-02)

## Context

Aelu serves two client types:

1. **Web browser:** Expects cookie-based sessions, CSRF protection, server-side session management.
2. **Mobile app (Capacitor) and CLI:** Expects token-based auth (JWT), stateless API calls, Bearer header authentication.

A single auth mechanism cannot serve both well:
- Cookies require CSRF tokens and don't work well in native apps
- JWTs in browsers (localStorage) are vulnerable to XSS and can't be HttpOnly

## Decision

Use **dual auth**: Flask-Login for session cookies (web) and custom JWT for API tokens (mobile/CLI).

## Rationale

### Implementation

```
Web browser → POST /login (form) → Flask-Login sets session cookie → subsequent requests use cookie
Mobile app  → POST /api/auth/login (JSON) → Server returns JWT → subsequent requests use Bearer header
CLI client  → POST /api/auth/login (JSON) → Server returns JWT → subsequent requests use Bearer header
```

### Web Auth (Flask-Login)

- Session cookie set with `HttpOnly`, `Secure`, `SameSite=Lax`
- CSRF token via `flask-wtf` on all POST forms
- Session stored server-side (Flask's default signed cookie, or server-side if needed)
- Login/logout handled by Flask-Login's `login_user()` / `logout_user()`

### API Auth (JWT)

- JWT issued on `/api/auth/login` with user_id, email, issued_at, expires_at
- Signed with HS256 using `SECRET_KEY` from environment
- 30-day expiry (mobile users shouldn't need to re-login frequently)
- Sent as `Authorization: Bearer <token>` header
- Verified by `@jwt_required` decorator on API routes

### Route Protection

```python
# Web route — uses Flask-Login session
@app.route("/dashboard")
@login_required  # Flask-Login decorator
def dashboard():
    return render_template("dashboard.html", user=current_user)

# API route — uses JWT
@app.route("/api/session/start", methods=["POST"])
@jwt_required  # Custom decorator
def api_start_session():
    user = get_jwt_user()  # Extracted from Bearer token
    return jsonify(start_session(user))

# Hybrid route — accepts either auth method
@app.route("/api/progress")
@auth_required  # Custom: checks JWT first, falls back to Flask-Login session
def api_progress():
    user = get_current_user()  # Works with either auth method
    return jsonify(get_progress(user))
```

## Consequences

### Positive

- Web users get secure, standard cookie-based auth with CSRF protection
- Mobile and CLI users get stateless JWT auth without cookie management
- Each auth mechanism uses the pattern best suited to its client type
- No third-party auth service dependency (self-hosted, zero cost)

### Negative

- **Two auth paths to maintain.** Bugs in one path may not be caught by testing the other. Mitigated by testing both paths in the test suite.
- **JWT revocation complexity.** JWTs are stateless — you can't "log out" a JWT without a blocklist. Current approach: short-ish expiry (30 days) + no blocklist. If a JWT is compromised, it's valid until expiry.
- **Secret key management.** The same `SECRET_KEY` signs both session cookies and JWTs. Key rotation requires invalidating all sessions and JWTs simultaneously.
- **No refresh token flow.** The JWT expires after 30 days and the user must re-login. A refresh token would extend sessions without re-authentication, but adds complexity.

### Neutral

- Both auth methods use the same `user` table and user model
- Password hashing uses bcrypt (via werkzeug.security) for both paths
- Rate limiting on login endpoints applies to both paths equally

## Revisit Triggers

1. **Security audit findings** — if penetration testing reveals auth vulnerabilities
2. **OAuth2 requirement** — if users request "Sign in with Google/Apple" (would replace both current mechanisms with a standard OAuth2 flow)
3. **JWT compromise incident** — would require adding token blocklist (Redis or DB table)
4. **Multi-device sync** — if users need to manage active sessions across devices (requires session table with explicit token tracking)
5. **Team growth** — a standard auth library (Flask-Security, Authlib) might be more maintainable than custom JWT code
