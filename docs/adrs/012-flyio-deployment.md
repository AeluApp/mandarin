# ADR-003: Deploy on Fly.io

## Status

Accepted (2026-02)

## Context

Aelu needs a hosting platform that supports:

- Python/Flask application (gunicorn + gevent)
- Persistent SQLite database on a volume
- Simple CLI-based deployments
- Health checks and zero-downtime deploys
- SSL/TLS termination
- Affordable at low scale ($5-20/month)
- Dockerfile-based builds (for portability)

Options considered:

1. **Fly.io** with persistent volumes
2. **Railway** with persistent storage
3. **Render** with persistent disk
4. **AWS (EC2 or ECS)** with EBS volumes
5. **Hetzner** bare metal VPS

## Decision

Deploy on **Fly.io** with a single `shared-cpu-1x` machine (512MB RAM) in the `ewr` (Newark, US East) region, with a persistent volume for SQLite and Litestream for backup.

## Rationale

### Why Fly.io

1. **Volume support for SQLite.** Fly.io volumes are persistent NVMe-backed storage attached to a specific machine. SQLite runs directly on the volume with native file I/O performance (no network filesystem like EFS).

2. **Simple deployment.** `fly deploy` builds the Dockerfile, pushes the image, and performs a rolling restart. No CI/CD pipeline required (though one exists for testing).

3. **Built-in health checks.** Fly.io monitors `/health` and automatically restarts unhealthy machines. Configured in `fly.toml`.

4. **Automatic TLS.** SSL certificates are provisioned and renewed automatically for custom domains.

5. **Affordable.** `shared-cpu-1x` with 512MB RAM: ~$3.38/month. 1GB volume: ~$0.15/month. Total: **~$3.53/month** for a production deployment.

6. **Dockerfile-based.** The deployment is a standard Dockerfile. If Fly.io becomes unsuitable, the same Dockerfile runs on any container platform (Railway, Render, ECS, bare metal Docker).

### Current Configuration

```toml
# fly.toml (key sections)
app = "aelu"
primary_region = "ewr"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 5173
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[vm]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512

[mounts]
  source = "aelu_data"
  destination = "/data"

[[services.http_checks]]
  interval = 15000
  timeout = 5000
  path = "/health"
```

### Why Not Alternatives

| Platform | Reason Against |
|----------|---------------|
| Railway | Volume support is newer, less battle-tested. Pricing is usage-based (unpredictable). |
| Render | Persistent disk is limited to specific tiers. No equivalent to Fly.io's `flyctl ssh` for debugging. |
| AWS EC2 | Overkill operational complexity for a solo developer. VPC, security groups, IAM, EBS management. |
| AWS ECS | Same AWS complexity plus container orchestration overhead. |
| Hetzner | Cheapest option (~$4/month for 2GB VPS), but no managed TLS, no health checks, no deployment tooling. Would need to build everything manually. |

## Consequences

### Positive

- Deployment is a single command (`fly deploy`)
- Database lives on the same machine as the app (zero network latency for SQLite)
- Automatic TLS for custom domain
- Health check monitoring with automatic restart
- `flyctl ssh console` for production debugging
- Litestream runs as a sidecar process for continuous backup to S3

### Negative

- **Vendor lock-in (moderate).** Fly.io-specific configuration in `fly.toml`. However, the Dockerfile is portable.
- **Single region.** The machine runs only in `ewr`. Users in Asia or Europe experience 150-300ms additional latency. CDN for static assets partially mitigates this.
- **Shared CPU.** Under load, CPU time is not guaranteed. Noisy neighbor effects are possible.
- **Volume is tied to one machine.** Cannot horizontally scale with multiple machines sharing the same SQLite volume (by design — SQLite is single-writer).

### Neutral

- Fly.io's billing model (per-machine, not per-request) is predictable
- No auto-scaling needed at current scale (single machine handles the load)
- Fly.io's internal networking (WireGuard mesh) is not used (single region, single machine)

## Cost Breakdown

| Item | Monthly Cost |
|------|-------------|
| shared-cpu-1x 512MB | $3.38 |
| 1GB persistent volume | $0.15 |
| Outbound bandwidth (estimate 5GB) | $0.00 (included) |
| Litestream -> S3 (Backblaze B2) | ~$0.50 |
| **Total** | **~$4.03/month** |

## Revisit Triggers

1. **Multi-region deployment needed** — if >20% of users are outside the US, consider Fly.io multi-region with LiteFS or migrate to PostgreSQL (Neon/Supabase with multi-region)
2. **Fly.io pricing increase >2x** — current cost is ~$4/month; if it exceeds $10/month for equivalent resources, evaluate Hetzner + Coolify or Railway
3. **Uptime SLO breach** — if Fly.io availability drops below 99.5% for 2 consecutive months, evaluate alternatives
4. **Need for background workers** — if long-running tasks (audio generation, batch SRS recalculation) need a separate process, evaluate adding a second Fly.io machine or moving to a platform with built-in job queues
