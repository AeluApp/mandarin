# Multi-Region Deployment Guide

## Architecture Overview

| Region | Role | Location |
|--------|------|----------|
| `ewr` | Primary (read/write) | US East (Newark) |
| `lax` | Read replica | US West (Los Angeles) |
| `ams` | Read replica | Europe (Amsterdam) |

The primary region handles all writes and serves reads for nearby users. Read replicas serve GET requests locally with near-zero latency. Litestream replicates the SQLite WAL to S3, and replicas restore from the same bucket with ~1-2s delay.

## Fly.io Configuration

### fly.toml

```toml
app = "mandarin"
primary_region = "ewr"

[env]
  PRIMARY_REGION = "ewr"

[http_service]
  internal_port = 5000
  force_https = true

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512
```

### Deploy to Multiple Regions

```bash
# Scale to additional regions
fly scale count 1 --region ewr
fly scale count 1 --region lax
fly scale count 1 --region ams
```

## Litestream S3 Replication

### litestream.yml

```yaml
dbs:
  - path: /data/mandarin.db
    replicas:
      - type: s3
        bucket: mandarin-backups
        path: litestream/mandarin
        region: us-east-1
        retention: 72h
        snapshot-interval: 1h
```

All regions replicate to the same S3 bucket. The primary writes WAL frames continuously; replicas restore on boot and poll for changes.

### Environment Variables (Fly secrets)

```bash
fly secrets set \
  AWS_ACCESS_KEY_ID=AKIA... \
  AWS_SECRET_ACCESS_KEY=... \
  LITESTREAM_REPLICA_BUCKET=mandarin-backups
```

## Read Replica Routing

### Write Forwarding

In the Flask app, detect write requests and replay them to the primary:

```python
@app.before_request
def route_writes():
    region = os.environ.get("FLY_REGION", "")
    primary = os.environ.get("PRIMARY_REGION", "ewr")
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and region != primary:
        return "", 409, {"fly-replay": f"region={primary}"}
```

Fly.io intercepts the `fly-replay` header and transparently replays the request to a machine in the primary region. The client sees a normal response.

### Read Routing

GET requests are served by the nearest replica. No special handling needed -- Fly.io anycast routes to the closest region automatically.

### WebSocket Connections

WebSocket sessions (drill and conversation) always pin to the primary since they involve writes:

```python
@app.before_request
def route_websockets():
    if request.headers.get("Upgrade") == "websocket":
        region = os.environ.get("FLY_REGION", "")
        primary = os.environ.get("PRIMARY_REGION", "ewr")
        if region != primary:
            return "", 409, {"fly-replay": f"region={primary}"}
```

## Health Checks

Configure per-region health checks in `fly.toml`:

```toml
[[services.http_checks]]
  interval = "15s"
  timeout = "5s"
  grace_period = "10s"
  method = "GET"
  path = "/api/health"
```

The `/api/health` endpoint checks:
- Database connectivity (read query)
- Schema version match
- Litestream replication lag (primary only)

## Failover Procedure

### Automatic (Fly.io managed)

If a replica becomes unhealthy, Fly.io stops routing traffic to it. Remaining healthy machines absorb the load.

### Primary Failure

1. **Detect**: Health checks fail on primary. Fly.io stops routing to `ewr`.
2. **Promote replica**: Pick the replica with the lowest replication lag.
   ```bash
   # Stop the failed primary
   fly machine stop <primary-machine-id>

   # Update a replica to become primary
   fly machine update <replica-machine-id> --env PRIMARY_REGION=lax
   ```
3. **Restore data**: The new primary restores from the latest Litestream snapshot in S3.
   ```bash
   litestream restore -o /data/mandarin.db s3://mandarin-backups/litestream/mandarin
   ```
4. **Update routing**: Set the new primary region.
   ```bash
   fly secrets set PRIMARY_REGION=lax
   ```
5. **Verify**: Confirm writes succeed and replication resumes.
6. **Rebuild original primary**: Once `ewr` is back, redeploy it as a read replica.

### RPO / RTO Targets

- **RPO** (Recovery Point Objective): ~1-2 seconds (Litestream WAL replication lag)
- **RTO** (Recovery Time Objective): ~2-5 minutes (S3 restore + health check pass)
