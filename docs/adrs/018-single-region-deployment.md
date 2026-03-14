# ADR-010: Single Region (US East) Deployment

## Status

Accepted (2026-02)

## Context

Aelu must choose a deployment topology:

1. **Single region** — one Fly.io machine in one datacenter
2. **Multi-region** — machines in multiple datacenters with data replication

The choice affects latency for global users, availability during regional outages, operational complexity, and cost.

## Decision

Deploy in a **single Fly.io region: `ewr` (Newark, New Jersey, US East).**

## Rationale

### Why Single Region

1. **SQLite is single-writer.** The database cannot run multi-primary. Multi-region SQLite requires LiteFS (Fly.io's distributed SQLite solution), which adds complexity: read replicas are eventually consistent, writes must be proxied to the primary, and failover logic is non-trivial.

2. **Founder is US-based.** Initial users are likely US-based English speakers learning Mandarin. US East provides <50ms latency for 80%+ of the initial user base.

3. **Simplest possible deployment.** One machine, one volume, one region. No replication lag, no split-brain scenarios, no cross-region networking.

4. **Cost.** One machine = one set of charges. Multi-region doubles or triples hosting costs for marginal benefit at current scale.

### Latency Impact

| User Location | Latency to ewr (Newark) | Impact on UX |
|--------------|-------------------------|--------------|
| US East Coast | 10-30ms | Imperceptible |
| US West Coast | 60-80ms | Imperceptible |
| US Central | 30-50ms | Imperceptible |
| Western Europe | 80-120ms | Barely noticeable |
| East Asia (China, Japan) | 180-250ms | Noticeable on drill interactions |
| Southeast Asia | 200-280ms | Noticeable |
| Australia | 220-300ms | Noticeable |

For drill interactions (submit answer → see result), the perceived latency is:

```
Perceived latency = network RTT + server processing time
                  = 200ms (Asia) + 25ms (average request)
                  = 225ms
```

This is below the 300ms threshold where users perceive delay as "slow," but above the 100ms threshold for "instant." Asian users will notice a slight lag.

### Availability Impact

Single region means a regional Fly.io outage takes Aelu completely offline. Historical Fly.io outage data (2024-2025):

- ewr region: ~3 incidents/year, average duration 30-60 minutes
- Expected annual downtime from regional outages: ~2-3 hours
- Combined with other downtime (deploys, bugs): estimated 99.5% availability

This meets our current SLO of 99.5% (3.6 hours downtime/month budget).

## Consequences

### Positive

- Simplest possible deployment and operational model
- No replication lag — reads always see the latest write
- No cross-region networking configuration
- Lowest possible cost
- All debugging happens on one machine (`flyctl ssh console`)

### Negative

- **Higher latency for non-US users.** Users in Asia experience 200-300ms RTT. If Aelu gains traction in Asia (likely, given it teaches Mandarin), this becomes a real UX issue.
- **Single point of failure.** Regional outage = total outage. No geographic redundancy.
- **No failover.** If the ewr machine fails, Fly.io restarts it on the same region. There is no automatic failover to a different region.

### Neutral

- CDN for static assets (CSS, JS, fonts, images) partially mitigates latency for non-US users. Dynamic content (drill interactions) still requires the round trip to ewr.
- Litestream backup to S3 provides data durability even if the region is permanently lost. Recovery time: ~30 minutes to provision a new machine in a different region and restore from backup.

## Multi-Region Migration Path

If needed, the migration path depends on the database choice:

### Path A: Stay on SQLite (LiteFS)

1. Add LiteFS to the deployment (Fly.io provides native integration)
2. Configure primary region (ewr) for writes
3. Add read replicas in `lax` (US West) and `nrt` (Tokyo) or `sin` (Singapore)
4. Application code must distinguish read and write queries (route writes to primary)
5. Estimated effort: 2-3 days
6. Trade-off: Eventual consistency for reads (typically <100ms replication lag)

### Path B: Migrate to PostgreSQL

1. Migrate database to managed PostgreSQL (Neon, Supabase)
2. Use provider's built-in multi-region read replicas
3. Application connects to nearest read replica; writes go to primary
4. Estimated effort: 1-2 weeks (database migration + connection layer rewrite)
5. Trade-off: Higher cost ($20-50/month for managed PostgreSQL), but proven multi-region story

### Path C: CDN + Edge Workers

1. Keep SQLite in single region for data
2. Add Cloudflare Workers or Fly.io edge functions for caching
3. Cache static API responses (vocabulary data, grammar points) at the edge
4. Dynamic requests (drill grading, progress updates) still go to ewr
5. Estimated effort: 1-2 days
6. Trade-off: Only helps for read-heavy, cache-friendly endpoints

**Recommended sequence:** Path C first (cheapest, fastest), then Path A if latency for dynamic content is still a problem, then Path B if scale demands it.

## Revisit Triggers

1. **>20% of users outside the US** — latency becomes a real competitive disadvantage
2. **Availability SLO breach** — if regional outages cause >3.6h downtime in any month
3. **User complaints about latency** — specific feedback from Asian users about slow drill interactions
4. **Compliance requirements** — if GDPR or other regulations require data residency in specific regions
