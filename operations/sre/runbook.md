# SRE Runbook

## Health Check Failures

### `/api/health/live` returns non-200
**Meaning**: Process is unresponsive or crashed.
**Action**: Restart the container. If crash-looping, check application logs for startup errors.
```bash
fly machines restart
fly logs --app mandarin
```

### `/api/health/ready` returns 503
**Meaning**: Database unavailable or schema migration pending.
**Action**:
1. Check if migration is in progress: look for `schema migration pending` in response
2. If migration stuck: check logs for migration errors, may need manual intervention
3. If DB unreachable: verify Litestream replication, check disk space
```bash
fly ssh console -C "ls -la /data/mandarin.db"
fly ssh console -C "python -c 'import sqlite3; c=sqlite3.connect(\"/data/mandarin.db\"); print(c.execute(\"PRAGMA integrity_check\").fetchone())'"
```

### `/api/health` shows high `latency_ms`
**Meaning**: Database queries are slow.
**Action**:
1. Check DB file size (SQLite performance degrades > 1GB without optimization)
2. Run VACUUM if needed
3. Verify indexes exist on hot tables (progress, session_log)
```bash
fly ssh console -C "ls -lh /data/mandarin.db"
fly ssh console -C "python -c 'import sqlite3; c=sqlite3.connect(\"/data/mandarin.db\"); c.execute(\"VACUUM\"); print(\"done\")'"
```

---

## Common Incidents

### High Error Rate (> 1% 5xx)
1. Check Sentry for new error patterns
2. Review recent deployments (`fly releases`)
3. Check rate limiting isn't over-aggressive (429 count in logs)
4. If caused by a bad deploy: `fly deploy --image <previous-image>`

### WebSocket Sessions Failing
1. Check for `ConnectionClosed` errors in logs
2. Verify Fly.io WebSocket support (requires HTTP/2)
3. Check concurrent session limits (per-user locks in session_store)
4. Review bridge.py for serialization errors

### Database Locked
1. SQLite allows only one writer at a time
2. Check for long-running transactions in logs
3. Verify WAL mode is enabled: `PRAGMA journal_mode` should return `wal`
4. If persistent: restart to clear stale locks

### Rate Limit False Positives
1. Check `security_audit_log` for `rate_limit_hit` events
2. Verify `get_remote_address` resolves correctly behind proxy
3. Adjust limits in `__init__.py` if legitimate traffic exceeds thresholds
4. In-memory limiter resets on restart (by design for SQLite-based app)

---

## Deployment Checklist

- [ ] All tests pass (`python -m pytest tests/ -q`)
- [ ] No HIGH severity Bandit findings
- [ ] DAST scan shows no new findings
- [ ] Schema migration tested locally
- [ ] Environment variables set (SECRET_KEY, JWT_SECRET, etc.)
- [ ] Health checks pass after deploy
- [ ] Monitor error rate for 15 minutes post-deploy
