# Service Level Objectives (SLOs) and Indicators (SLIs)

## Service: Aelu Learning Platform

### SLO 1: Availability
- **SLI**: Proportion of successful health checks (HTTP 200 from `/api/health/ready`)
- **Target**: 99.5% over a rolling 30-day window
- **Measurement**: Fly.io health check probes every 10 seconds
- **Alert threshold**: < 99.0% triggers page

### SLO 2: Latency
- **SLI**: p95 response time for all API endpoints
- **Target**: p95 < 500ms, p99 < 2000ms
- **Measurement**: Server-side `latency_ms` in health responses; application logs
- **Alert threshold**: p95 > 750ms for 5 consecutive minutes triggers warning

### SLO 3: Session Reliability
- **SLI**: Proportion of WebSocket drill sessions that complete without error
- **Target**: 99.0% of started sessions complete successfully
- **Measurement**: `session_log` table (items_completed > 0 vs total started)
- **Alert threshold**: < 98% over 24h triggers investigation

### SLO 4: Data Freshness
- **SLI**: Schema version matches expected version on readiness check
- **Target**: 100% (schema migrations must complete before traffic)
- **Measurement**: `/api/health/ready` schema_current field
- **Alert threshold**: Any `not_ready` response triggers immediate investigation

---

## Error Budget Policy

### Budget Calculation
- **Monthly budget** = 100% - SLO target
- Availability: 0.5% = ~3.6 hours/month downtime allowed
- Latency: 5% of requests can exceed 500ms

### Budget Exhaustion Rules

**When > 50% of monthly error budget consumed:**
- No feature deployments
- Focus on reliability improvements
- Review recent changes for regressions

**When > 80% of monthly error budget consumed:**
- Feature freeze
- All hands on reliability
- Post-incident review required for next depletion event

**When budget is replenished (new 30-day window):**
- Resume normal feature development
- Carry forward any reliability improvements from freeze period

### Exemptions
- Scheduled maintenance windows (announced 24h in advance)
- Force majeure (cloud provider outages, DNS issues)
- Database migrations under 5 minutes

---

## Health Check Architecture

```
                   ┌──────────────────┐
                   │   Fly.io / K8s   │
                   │   Health Probes   │
                   └───────┬──────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────▼───┐ ┌─────▼─────┐ ┌───▼────────┐
     │ /health/   │ │ /health/  │ │ /health    │
     │ live       │ │ ready     │ │ (full)     │
     │            │ │           │ │            │
     │ Process    │ │ DB write  │ │ DB + schema│
     │ alive?     │ │ Schema    │ │ + content  │
     │ Uptime     │ │ current?  │ │ + uptime   │
     │            │ │ Latency   │ │ + latency  │
     └────────────┘ └───────────┘ └────────────┘
        Liveness      Readiness      Deep check
        (restart)     (route away)   (monitoring)
```

### Probe Configuration (Fly.io)

```toml
# fly.toml
[checks]
  [checks.liveness]
    type = "http"
    port = 8080
    path = "/api/health/live"
    interval = "10s"
    timeout = "5s"
    method = "GET"

  [checks.readiness]
    type = "http"
    port = 8080
    path = "/api/health/ready"
    interval = "15s"
    timeout = "10s"
    method = "GET"
```

---

## Monitoring and Alerting

### Key Metrics to Track
1. **Request rate** (requests/second by endpoint)
2. **Error rate** (5xx responses / total responses)
3. **Latency percentiles** (p50, p95, p99)
4. **WebSocket session duration** (median, failures)
5. **Database size** (SQLite file size)
6. **Health check latency** (`latency_ms` from `/api/health`)

### Alerting Channels
- **Sentry**: Application errors, unhandled exceptions
- **Structured logs**: Security events, audit trail (SIEM-ready JSON format)
- **Health probes**: Infrastructure-level availability

### Incident Severity Levels

| Level | Criteria | Response Time | Example |
|-------|----------|---------------|---------|
| P1 | Service down, all users affected | 15 min | DB corruption, process crash loop |
| P2 | Degraded, partial functionality | 1 hour | Slow queries, WebSocket failures |
| P3 | Minor issue, workaround exists | 4 hours | CSS rendering, non-critical API |
| P4 | Cosmetic, no user impact | Next sprint | Log formatting, minor UI glitch |
