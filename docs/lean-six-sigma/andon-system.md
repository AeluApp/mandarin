# Andon System — Aelu Failure Detection & Alerting

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Status:** Partially implemented — gaps identified

---

## 1. Overview

An andon system makes problems visible immediately so they can be addressed before they compound. In manufacturing, this is a physical cord or light. In software, it's crash logging, error alerting, and automated notification.

Aelu has four existing andon-equivalent systems and one critical gap.

---

## 2. Existing Andon Systems

### 2.1 Crash Log (Server-Side Errors)

**Table:** `crash_log`

```sql
CREATE TABLE IF NOT EXISTS crash_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    error_type TEXT NOT NULL,
    error_message TEXT,
    traceback TEXT,
    request_method TEXT,
    request_path TEXT,
    request_body TEXT,
    ip_address TEXT,
    user_agent TEXT,
    severity TEXT NOT NULL DEFAULT 'ERROR',
    FOREIGN KEY (user_id) REFERENCES user(id)
);
```

**Trigger:** Any unhandled Python exception during request processing.

**Flow:**
1. Flask error handler catches 500 errors
2. Exception details written to `crash_log` table
3. Sentry SDK sends exception to Sentry (cloud)
4. Sentry sends alert (email or webhook) based on alert rules

**Coverage:** Server-side Python errors (500 responses). Covers: route handlers, database errors, scheduler failures, grading logic errors.

**Blind spots:**
- Silent failures (function returns wrong result but doesn't raise exception)
- Background scheduler errors (may not go through Flask error handler)
- Database write failures that are caught and silenced

**Retention:** 90 days (per `retention_policy` table).

---

### 2.2 Client Error Log (JavaScript/Frontend Errors)

**Table:** `client_error_log`

```sql
CREATE TABLE IF NOT EXISTS client_error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    error_type TEXT NOT NULL,
    error_message TEXT,
    source_file TEXT,
    line_number INTEGER,
    col_number INTEGER,
    stack_trace TEXT,
    page_url TEXT,
    user_agent TEXT,
    event_snapshot TEXT,
    FOREIGN KEY (user_id) REFERENCES user(id)
);
```

**Trigger:** JavaScript `window.onerror` and `unhandledrejection` events in the web UI.

**Flow:**
1. Client-side error handler catches JS exceptions
2. POST to `/api/error-report` with error details
3. Server writes to `client_error_log` table
4. No automatic alerting (gap)

**Coverage:** Frontend JavaScript errors in the web UI and iOS Capacitor shell. Covers: DOM manipulation errors, WebSocket failures, audio API errors, navigation errors.

**Blind spots:**
- CSS rendering issues (no JS error for visual bugs)
- Slow/failed network requests (fetch errors may not trigger onerror)
- iOS WKWebView-specific errors that don't propagate to JS

**Retention:** 30 days.

---

### 2.3 Security Audit Log (Authentication/Authorization Failures)

**Table:** `security_audit_log`

```sql
CREATE TABLE IF NOT EXISTS security_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    user_id INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    details TEXT,
    severity TEXT NOT NULL DEFAULT 'INFO',
    FOREIGN KEY (user_id) REFERENCES user(id)
);
```

**Trigger:** Authentication events (login, logout, failed login, password reset, MFA challenge, token refresh).

**Flow:**
1. Auth route handlers log security events
2. Written to `security_audit_log` table
3. Events with severity >= 'WARNING' (repeated failed logins, account lockout) can trigger webhook
4. Webhook integration for high-severity events (if configured)

**Coverage:** Authentication and authorization events. Covers: brute force detection, account lockout, suspicious IP patterns, MFA failures.

**Blind spots:**
- Application-level authorization bypass (accessing another user's data without auth failure)
- API abuse within authenticated sessions (excessive requests)
- Rate limit hits are logged separately in `rate_limit` table but not cross-correlated

**Retention:** 365 days.

---

### 2.4 Churn Detection (Behavioral Early Warning)

**Module:** `mandarin/churn_detection.py`

**Signals detected:**
1. Session frequency drop (30%+ decline over 2 weeks vs trailing 30-day avg)
2. No session in 5+ days
3. No session in 10+ days
4. No session in 14+ days
5. Session duration drop (avg drops 50%+ from baseline)
6. Accuracy plateau (same range for 3+ weeks)
7. Single drill type usage (80%+ same type for 3+ weeks)
8. No reading/listening usage in 30+ days

**Flow:**
1. Run `./run churn-report` (manual CLI command)
2. Analyzes `session_log`, `review_event` data
3. Produces composite risk score 0-100
4. Score > 70 triggers re-engagement email via Resend

**Coverage:** Behavioral churn indicators. Provides early warning before the user actually churns.

**Blind spots:**
- Only runs on manual invocation (not continuous monitoring)
- No real-time alerting — must remember to run the report
- At N=1, churn detection is effectively "did Jason study today?"

---

## 3. Critical Gap: No Real-Time Developer Notification

### Problem Statement

When a user-facing failure occurs (crash, JS error, auth anomaly), there is no real-time push notification to the developer. The information is logged to the database and (for crashes) to Sentry, but:

1. **Sentry alerts depend on Sentry configuration** — If alert rules aren't set up or the email goes to spam, crashes go unnoticed.
2. **Client errors have NO alerting** — They sit in `client_error_log` until someone queries the table.
3. **Churn detection is manual** — Must remember to run `./run churn-report`.
4. **The developer may not check the database for hours or days** — During which the user is experiencing failures.

### Impact

At N=1 (Jason is the only user), the developer IS the user, so failures are noticed immediately. But at N=10+, a user could hit a crash, get frustrated, and churn before the developer ever knows about it.

---

## 4. Proposed Solution: Webhook Alerting on Critical Events

### 4.1 Architecture

```
crash_log INSERT ──┐
                   ├──▶ webhook_dispatch() ──▶ Discord/Slack webhook
client_error_log ──┘                          (with structured message)
INSERT (severity)
```

### 4.2 Implementation

```python
# mandarin/web/andon.py

import json
import logging
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Webhook URL set via environment variable or config
ANDON_WEBHOOK_URL = None  # Set to Discord/Slack webhook URL


def fire_andon(event_type: str, severity: str, summary: str,
               details: dict = None):
    """Send an andon alert to the configured webhook.

    Only fires for severity='ERROR' or 'CRITICAL'. Silently no-ops
    if no webhook is configured.
    """
    if not ANDON_WEBHOOK_URL:
        logger.debug("Andon: no webhook configured, skipping")
        return

    if severity not in ('ERROR', 'CRITICAL'):
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Discord webhook format
    payload = {
        "content": None,
        "embeds": [{
            "title": f"{'CRITICAL' if severity == 'CRITICAL' else 'Error'}: {event_type}",
            "description": summary[:2000],
            "color": 0xFF0000 if severity == 'CRITICAL' else 0xFF8800,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fields": [
                {"name": k, "value": str(v)[:1024], "inline": True}
                for k, v in (details or {}).items()
            ][:10],  # Discord limit: 10 fields
            "footer": {"text": "Aelu Andon System"}
        }]
    }

    try:
        req = urllib.request.Request(
            ANDON_WEBHOOK_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("Andon alert sent: %s", event_type)
    except Exception as e:
        # Never let andon alerting crash the application
        logger.error("Andon webhook failed: %s", e)
```

### 4.3 Integration Points

**Crash log (server errors):**
```python
# In the Flask error handler (server.py or middleware.py)
@app.errorhandler(500)
def handle_500(error):
    # ... existing crash_log INSERT ...

    fire_andon(
        event_type="server_crash",
        severity="ERROR",
        summary=f"{request.method} {request.path}: {str(error)[:200]}",
        details={
            "path": request.path,
            "method": request.method,
            "user_id": getattr(current_user, 'id', 'anonymous'),
            "error_type": type(error).__name__,
        }
    )
    return jsonify({"error": "internal_error"}), 500
```

**Client error log (JS errors):**
```python
# In the /api/error-report endpoint
@app.route('/api/error-report', methods=['POST'])
def report_error():
    # ... existing client_error_log INSERT ...

    # Only fire andon for errors that suggest a broken user experience
    if error_type in ('TypeError', 'ReferenceError', 'SyntaxError'):
        fire_andon(
            event_type="client_error",
            severity="ERROR",
            summary=f"JS {error_type}: {error_message[:200]}",
            details={
                "source": source_file,
                "line": line_number,
                "page": page_url,
                "user_agent": user_agent,
            }
        )
```

**Security events (auth anomalies):**
```python
# In auth_routes.py, after logging security event
if failed_login_attempts >= 5:
    fire_andon(
        event_type="brute_force_attempt",
        severity="CRITICAL",
        summary=f"5+ failed logins for user {email}",
        details={
            "email": email,
            "ip_address": ip_address,
            "attempts": failed_login_attempts,
        }
    )
```

**Churn detection (automated):**
```python
# Add to email_scheduler.py or retention_scheduler.py
# Run churn check daily, fire andon if any user crosses threshold
def check_churn_andon(conn):
    # ... run churn detection for all active users ...
    for user_id, risk_score in high_risk_users:
        if risk_score >= 70:
            fire_andon(
                event_type="churn_risk_high",
                severity="ERROR",
                summary=f"User {user_id} churn risk score: {risk_score}",
                details={
                    "user_id": user_id,
                    "risk_score": risk_score,
                    "days_since_last_session": days_inactive,
                }
            )
```

### 4.4 Alert Fatigue Prevention

| Rule | Implementation |
|------|---------------|
| Rate limit: max 10 alerts per hour | Counter in memory, reset every hour |
| Dedup: same error_type + path within 5 minutes → suppress | Hash of (error_type, path) with 5-minute TTL |
| Severity filter: only ERROR and CRITICAL fire webhooks | Checked in `fire_andon()` |
| Business hours preference: batch non-critical alerts for morning digest | Future enhancement |

---

## 5. Andon Coverage Matrix

| Failure Type | Detection | Logging | Alerting | Gap |
|-------------|-----------|---------|----------|-----|
| Server crash (500) | Flask error handler | crash_log + Sentry | Sentry email (if configured) | **Add webhook** |
| JS runtime error | window.onerror | client_error_log | **None** | **Add webhook** |
| CSS/layout breakage | Visual inspection only | Not logged | **None** | **No automated detection possible** |
| Auth brute force | Failed login counter | security_audit_log | Webhook (if configured) | Ensure webhook is active |
| User churn | churn_detection.py | CLI output only | Email (if run manually) | **Automate daily check + webhook** |
| Slow API response | Not instrumented | Not logged | **None** | **Add latency logging + threshold alert** |
| Database corruption | SQLite integrity check | Not automated | **None** | **Add daily PRAGMA integrity_check** |
| Litestream replication failure | Litestream logs | Container stdout | **None** | **Add Litestream health check** |
| Payment webhook failure | Stripe dashboard | Not in app DB | **None** | **Add Stripe webhook verification** |
| Email delivery failure | Resend dashboard | Not in app DB | **None** | **Add Resend delivery status check** |

---

## 6. Implementation Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 1 | Create `andon.py` with `fire_andon()` | 1 hour | Foundation for all alerts |
| 2 | Wire crash_log INSERT to fire_andon | 30 min | Immediate crash visibility |
| 3 | Wire client_error_log to fire_andon | 30 min | Frontend error visibility |
| 4 | Set up Discord webhook | 15 min | Alert delivery channel |
| 5 | Wire security_audit_log high-severity events | 30 min | Security visibility |
| 6 | Automate daily churn check in scheduler | 2 hours | Proactive retention |
| 7 | Add API latency logging + threshold alert | 2 hours | Performance visibility |
| 8 | Add rate limiting and dedup to andon | 1 hour | Alert fatigue prevention |
| **Total** | | **~8 hours** | |

---

## 7. Andon Dashboard (Future)

Once webhook alerting is in place, consider a lightweight andon dashboard:

```
┌─────────────────────────────────────────────────────┐
│  AELU ANDON BOARD                      2026-03-10   │
│                                                      │
│  Server Crashes (24h):    0  ●                      │
│  Client Errors (24h):     0  ●                      │
│  Auth Warnings (24h):     0  ●                      │
│  Churn Risk > 70:         0  ●                      │
│  API p95 Latency:       120ms ●                     │
│                                                      │
│  ● = Green (normal)                                  │
│  ● = Yellow (warning)                                │
│  ● = Red (action needed)                             │
│                                                      │
│  Last incident: None in past 7 days                  │
└─────────────────────────────────────────────────────┘
```

This could be a simple HTML page at `/admin/andon` (admin-only route), pulling from the four log tables with simple COUNT queries over the last 24 hours.
