# ADR-005: Dual Auth System (JWT for API + Sessions for Web)

## Status

Accepted (2026-01)

## Context

Aelu serves three client types: (1) web browser (dashboard, drills, reader), (2) iOS app via Capacitor, and (3) macOS desktop app. Web browsers expect session-based auth with cookies. Mobile and desktop clients benefit from stateless JWT tokens that survive app restarts without server-side session storage.

Supporting both authentication patterns from a single Flask application requires careful middleware design.

## Decision Drivers

- Web UI needs CSRF-protected session cookies for secure form submissions
- Mobile clients need stateless tokens that don't require cookie management
- Both clients share the same user model and permission system
- JWT refresh tokens must be stored server-side for revocation capability
- MFA (TOTP) must work across both auth flows

## Considered Options

### Option 1: JWT Only

- **Pros**: Stateless, works for all clients, no server-side session storage
- **Cons**: CSRF protection is harder without cookies, token in localStorage is XSS-vulnerable, token refresh UX is awkward in web browsers, cannot revoke tokens without server-side blocklist (defeats stateless benefit)

### Option 2: Session Only

- **Pros**: Simple, CSRF protection built-in, easy revocation (delete session), familiar pattern
- **Cons**: Requires cookie handling in mobile clients (Capacitor handles this but it's fragile), session storage grows with user count, not truly stateless

### Option 3: Dual Auth (chosen)

- **Pros**: Each client uses the pattern best suited to its platform, shared user model, JWT for API + cookies for web is an industry-standard pattern
- **Cons**: Two auth code paths to maintain and test, middleware must check both token types, potential for auth bypass bugs at the boundary

## Decision

Implement dual authentication:

1. **Web browser**: Flask session cookies with `httponly`, `secure`, `samesite=lax` flags. CSRF token in forms. Session data stored in encrypted cookies (Flask's `SecureCookieSession`).

2. **API clients (mobile, desktop)**: JWT access tokens (15-minute expiry) + refresh tokens (30-day expiry). Refresh token hash stored in `user.refresh_token_hash` for revocation. Access token in `Authorization: Bearer` header.

3. **MFA bridge**: When MFA is enabled, both flows issue a temporary `mfa_challenge` token that must be exchanged for a full session/JWT after TOTP verification. Challenge tokens stored in `mfa_challenge` table with short expiry.

Auth middleware resolution order:
```python
def get_current_user():
    # 1. Check JWT in Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return validate_jwt(auth_header[7:])

    # 2. Check Flask session cookie
    if 'user_id' in session:
        return load_user(session['user_id'])

    # 3. No auth
    return None
```

## Consequences

### Positive

- **Platform-appropriate auth**: Web users get seamless cookie-based sessions. Mobile users get stateless JWTs that persist across app restarts.
- **Revocation capability**: Refresh tokens are hashed and stored server-side. Revoking a refresh token invalidates all future access tokens for that device.
- **MFA integration**: The `mfa_challenge` table bridges both flows. A user enabling TOTP affects both web sessions and API tokens uniformly.
- **Account lockout**: `failed_login_attempts` and `locked_until` in the user table work identically for both auth flows.

### Negative

- **Complexity**: Two code paths for authentication, token refresh, and logout. Every auth-related change must be tested on both paths.
- **Security surface**: More code = more potential vulnerabilities. The middleware must be carefully ordered to prevent auth bypass (e.g., a request with both a valid cookie and an invalid JWT should use the cookie, not reject).
- **Token storage on mobile**: JWT access tokens are stored in the Capacitor Preferences plugin (equivalent to SharedPreferences/Keychain). If the device is compromised, tokens are exposed until expiry.

### Security Controls

- JWT signing uses HS256 with a 256-bit secret from environment variable
- Refresh tokens are SHA256-hashed before storage (plaintext never persisted)
- Access tokens expire in 15 minutes (short window for stolen tokens)
- Rate limiting on `/api/auth/login` and `/api/auth/refresh` (10 req/min)
- Account lockout after 5 failed login attempts (30-minute lockout)
- Security audit log records all auth events (login, logout, refresh, MFA challenge)
