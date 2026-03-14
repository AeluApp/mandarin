# Aelu Launch Runbook

Production deployment and launch procedures for aelu.app.

---

## Pre-Launch (48h before)

### Environment Variables

Verify every required secret is set in Fly.io. Cross-reference against `.env.example`:

```bash
fly secrets list
```

Required secrets (must be non-empty):

| Secret | Purpose |
|--------|---------|
| `SECRET_KEY` | Flask session signing (must not be `mandarin-local-only`) |
| `JWT_SECRET` | Mobile auth tokens (must not be `mandarin-local-only`) |
| `STRIPE_SECRET_KEY` | Payment processing |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature verification |
| `SENTRY_DSN` | Error monitoring |
| `RESEND_API_KEY` | Transactional email |
| `FROM_EMAIL` | Sender address for emails |
| `LITESTREAM_S3_BUCKET` | Database replication bucket |
| `AWS_ACCESS_KEY_ID` | S3 access for Litestream |
| `AWS_SECRET_ACCESS_KEY` | S3 access for Litestream |
| `AWS_REGION` | S3 region for Litestream |
| `VAPID_PUBLIC_KEY` | Push notification signing |
| `VAPID_PRIVATE_KEY` | Push notification signing |
| `VAPID_CLAIMS_EMAIL` | Push notification contact |
| `PLAUSIBLE_DOMAIN` | Analytics domain |

Set via fly.toml (not secrets):

| Variable | Value |
|----------|-------|
| `IS_PRODUCTION` | `true` |
| `PORT` | `8080` |
| `DATA_DIR` | `/data` |

Optional but recommended:

| Secret | Purpose |
|--------|---------|
| `ALERT_WEBHOOK_URL` | Slack webhook for security alerts |
| `ADMIN_EMAIL` | Admin notification recipient |
| `SESSION_TIMEOUT_MINUTES` | Idle session timeout (default 30) |

### Database Backup Verification

Test that Litestream restore works from the S3 replica:

```bash
# Check Litestream config is valid
fly ssh console -C "litestream databases -config /etc/litestream.yml"

# Verify S3 bucket contains replicas
fly ssh console -C "litestream snapshots -config /etc/litestream.yml /data/mandarin.db"

# Test restore to a temporary path
fly ssh console -C "litestream restore -config /etc/litestream.yml -o /tmp/test_restore.db /data/mandarin.db"
fly ssh console -C "sqlite3 /tmp/test_restore.db 'SELECT count(*) FROM vocab_item;'"
fly ssh console -C "rm /tmp/test_restore.db"
```

### Stripe Webhook

```bash
# Verify webhook endpoint is registered in Stripe dashboard
# Endpoint: https://aelu.app/api/webhook/stripe
# Events: checkout.session.completed, customer.subscription.updated,
#          customer.subscription.deleted, invoice.payment_failed

# Test with Stripe CLI
stripe listen --forward-to https://aelu.app/api/webhook/stripe
stripe trigger checkout.session.completed
```

### Domain and SSL

```bash
# Verify DNS is pointed to Fly.io
dig aelu.app +short
dig www.aelu.app +short

# Verify SSL certificate
fly certs show aelu.app
fly certs check aelu.app

# Verify HTTPS works
curl -sI https://aelu.app | head -5
```

### VAPID Keys

If not already generated:

```bash
# Generate VAPID key pair
python3 -c "from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print('Public:', v.public_key); print('Private:', v.private_key)"

# Set in Fly.io
fly secrets set VAPID_PUBLIC_KEY="..." VAPID_PRIVATE_KEY="..." VAPID_CLAIMS_EMAIL="mailto:admin@aelu.app"
```

### Sentry

```bash
# Verify DSN is set and reachable
fly secrets list | grep SENTRY_DSN
curl -s "https://sentry.io/api/0/" | head -1
```

### Email Verification

```bash
# Verify Resend API key works
curl -s -X POST https://api.resend.com/emails \
  -H "Authorization: Bearer $RESEND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"from":"Aelu <noreply@aelu.app>","to":"test@example.com","subject":"Launch test","text":"Email delivery verified."}'
```

### Test Suite

```bash
# Full test suite
python -m pytest tests/ -q

# Golden flows (critical user paths)
python -m pytest tests/test_golden_flows.py -v

# Security regression
python -m pytest tests/test_security_regression.py -v

# Security scan
bandit -r mandarin/ -ll
```

### Release Gate

```bash
./scripts/release_gate.sh
```

This runs all quality gates: tests, schema validation, SPC checks, DPMO thresholds, and Definition of Done criteria. Deployment is blocked if any gate fails.

### Smoke Test Staging

```bash
# If using a staging app
fly deploy --app mandarin-staging
curl -s https://mandarin-staging.fly.dev/api/health/ready | python3 -m json.tool
curl -s https://mandarin-staging.fly.dev/api/health | python3 -m json.tool
```

### Rate Limits

Review rate limits configured in `mandarin/web/__init__.py`:

- Login: 10/minute
- Registration: 5/hour
- Password reset: 3/hour
- Error reports: 20/hour
- Public stats: 30/minute
- Global default: 200/hour
- Feedback: 5/hour
- Referral signup: 20/hour

Confirm these are appropriate for expected launch traffic.

### GDPR Endpoints

```bash
# Verify data export works
curl -s -X POST https://aelu.app/api/gdpr/export \
  -H "Authorization: Bearer <test-token>" \
  -H "X-Requested-With: XMLHttpRequest" | head -20

# Verify account deletion works (use test account only)
curl -s -X POST https://aelu.app/api/gdpr/delete \
  -H "Authorization: Bearer <test-token>" \
  -H "X-Requested-With: XMLHttpRequest"
```

---

## Launch Day

### Deploy

```bash
# Final commit on main
git status
git log --oneline -3

# Deploy with rolling strategy (zero-downtime)
fly deploy --strategy rolling
```

### Verify Health

```bash
# Liveness probe (process alive, no dependency checks)
curl -s https://aelu.app/api/health/live | python3 -m json.tool

# Readiness probe (DB writable, schema current)
curl -s https://aelu.app/api/health/ready | python3 -m json.tool

# Full health check (DB, schema, content stats)
curl -s https://aelu.app/api/health | python3 -m json.tool
```

### Post-Deploy Smoke Test

```bash
# Landing page loads
curl -sI https://aelu.app | head -10

# Static assets load (CSS, JS)
curl -sI https://aelu.app/static/style.css | head -5
curl -sI https://aelu.app/static/app.js | head -5

# Auth flow
curl -s https://aelu.app/auth/login -o /dev/null -w "%{http_code}"

# API responds
curl -s https://aelu.app/api/health/live | python3 -m json.tool

# SW kill-switch endpoint
curl -s https://aelu.app/api/sw-status | python3 -m json.tool
```

### Verify Stripe Webhooks

```bash
# Check Stripe dashboard for recent webhook deliveries
# Endpoint: https://aelu.app/api/webhook/stripe
# All recent deliveries should show 200 status

# Or use Stripe CLI to send a test event
stripe trigger checkout.session.completed
```

### Verify Email

```bash
# Register a test account and verify the welcome email arrives
# Or trigger a password reset and confirm the email is delivered
```

### Monitor Sentry

For the first 2 hours after deploy:

- Watch Sentry dashboard for new errors
- Check for elevated error rates vs baseline
- Pay attention to 500 errors, unhandled exceptions, and JS client errors

```bash
# Check Fly.io logs for errors
fly logs --app mandarin | grep -i error | head -20
```

### Check Database Replication

```bash
# Verify Litestream is replicating
fly ssh console -C "litestream snapshots -config /etc/litestream.yml /data/mandarin.db"

# Check latest generation timestamp is recent
fly ssh console -C "litestream wal -config /etc/litestream.yml /data/mandarin.db"
```

### Test PWA Install

- **iOS Safari**: Navigate to https://aelu.app, tap Share, tap "Add to Home Screen". Open the PWA and verify it loads correctly.
- **Android Chrome**: Navigate to https://aelu.app, tap the install banner or menu > "Install app". Open and verify.

### Verify Push Notifications

```bash
# From the web app, enable notifications in Settings
# Trigger a test notification (e.g., streak reminder) and confirm delivery
```

---

## Post-Launch (first 24h)

### Review Sentry

```bash
# Check for any new issues since deploy
# Sentry dashboard: filter by environment=production, last 24h
# Focus on: unhandled exceptions, new issue types, error rate trends
```

### Financial Monitor

```bash
# Check for payment anomalies
fly ssh console -C "python3 -c \"
from mandarin import db
from mandarin.web.financial_monitor import get_financial_summary
with db.connection() as conn:
    summary = get_financial_summary(conn, days=1)
    print(summary)
\""
```

### Onboarding Agent

```bash
# Check for onboarding intervention logs
fly ssh console -C "sqlite3 /data/mandarin.db 'SELECT count(*), type FROM onboarding_event WHERE created_at > datetime(\"now\", \"-1 day\") GROUP BY type;'"
```

### Support Queue

```bash
# Check support ticket volume
fly ssh console -C "sqlite3 /data/mandarin.db 'SELECT count(*), status FROM support_ticket WHERE created_at > datetime(\"now\", \"-1 day\") GROUP BY status;'"
```

### Backup Verification

```bash
# Confirm at least one snapshot completed since launch
fly ssh console -C "litestream snapshots -config /etc/litestream.yml /data/mandarin.db"
```

### Access Logs

```bash
# Review recent logs for suspicious patterns
fly logs --app mandarin | grep -E "403|401|429" | tail -30

# Check for brute force attempts
fly logs --app mandarin | grep "Rate limit" | tail -10

# Check for CSRF violations
fly logs --app mandarin | grep "CSRF" | tail -10
```

### Compliance Monitor

```bash
# Check weekly compliance brief
fly ssh console -C "python3 -c \"
from mandarin import db
from mandarin.web.compliance_monitor import get_compliance_brief
with db.connection() as conn:
    brief = get_compliance_brief(conn)
    print(brief)
\""
```

---

## Rollback Procedure

If a critical issue is discovered after deploy:

### 1. List Recent Deployments

```bash
fly releases --app mandarin
```

Output shows version numbers and image references. Identify the last known-good release.

### 2. Roll Back

```bash
# Roll back to a specific previous image
fly deploy --app mandarin --image <previous-image-ref>

# Or roll back to a specific release version
fly releases rollback --app mandarin
```

### 3. Verify Health After Rollback

```bash
curl -s https://aelu.app/api/health/ready | python3 -m json.tool
curl -s https://aelu.app/api/health/live | python3 -m json.tool
```

### 4. Confirm Rollback Stability

```bash
# Watch logs for 5 minutes
fly logs --app mandarin

# Verify DB replication resumed
fly ssh console -C "litestream snapshots -config /etc/litestream.yml /data/mandarin.db"
```

### 5. Investigate Root Cause

Do not re-deploy until:

- Root cause is identified (check Sentry, Fly logs, crash_log table)
- Fix is implemented and tested locally
- `./scripts/release_gate.sh` passes
- Fix is reviewed

```bash
# Check crash_log table for details
fly ssh console -C "sqlite3 /data/mandarin.db 'SELECT error_type, error_message, request_path, created_at FROM crash_log ORDER BY created_at DESC LIMIT 10;'"
```

---

## Quick Reference

| Action | Command |
|--------|---------|
| Deploy | `fly deploy --strategy rolling` |
| Logs | `fly logs --app mandarin` |
| SSH | `fly ssh console --app mandarin` |
| Secrets | `fly secrets list` |
| Set secret | `fly secrets set KEY=value` |
| Health check | `curl -s https://aelu.app/api/health/ready` |
| Release gate | `./scripts/release_gate.sh` |
| DB shell | `fly ssh console -C "sqlite3 /data/mandarin.db"` |
| Rollback | `fly releases rollback --app mandarin` |
| Scale | `fly scale count 2 --app mandarin` |
| Restart | `fly apps restart mandarin` |
