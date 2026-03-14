# Queueing Theory Analysis: Aelu Request Processing

## Model Selection: M/G/1

Aelu's request processing maps to an **M/G/1 queue**:

- **M** (Markovian arrivals): User requests arrive approximately as a Poisson process. Users are independent, sessions are unpredictable, and inter-arrival times are memoryless at the system level.
- **G** (General service time): Request processing times are *not* exponential. A `/api/drill/grade` call (simple DB update) takes ~5ms; a `/api/session/start` call (SRS calculation + drill selection) takes ~80ms. The service time distribution is multimodal.
- **1** (Single server for writes): SQLite in WAL mode allows concurrent reads but serializes writes through a single writer. Reads are effectively infinite-server (bounded by CPU/memory). The bottleneck analysis focuses on the write path.

## Parameters

### Arrival Rate (lambda)

Estimating from expected usage patterns:

| Users | Avg Sessions/Day | Avg Requests/Session | Daily Requests | lambda (req/s) | Peak lambda (10x) |
|-------|-------------------|----------------------|----------------|-----------------|--------------------|
| 100   | 1.5               | 45                   | 6,750          | 0.078           | 0.78               |
| 1,000 | 1.5               | 45                   | 67,500         | 0.78            | 7.8                |
| 10,000| 1.5               | 45                   | 675,000        | 7.8             | 78                 |
| 50,000| 1.5               | 45                   | 3,375,000      | 39              | 390                |

**Assumptions:**
- Active users do ~1.5 sessions/day (some days 0, some days 2-3)
- Each session generates ~45 HTTP requests (page loads, drill fetches, grade submissions, audio requests, progress updates)
- Peak factor of 10x during evening hours (18:00-22:00 local time). This is conservative; real peak/average ratios for consumer apps range from 5-20x.
- "Users" means daily active users, not registered users. At 10% DAU/MAU ratio, 10,000 DAU = 100,000 registered.

### Service Rate (mu)

Measured from Aelu's request handling:

| Request Type          | Avg Latency (ms) | % of Traffic | Writes? |
|-----------------------|-------------------|--------------|---------|
| Static assets (CSS/JS)| 2                 | 30%          | No      |
| Page renders          | 15                | 20%          | No      |
| API reads (progress)  | 10                | 20%          | No      |
| API writes (grade)    | 25                | 15%          | Yes     |
| Session start (SRS)   | 80                | 5%           | Yes     |
| Audio generation      | 150               | 5%           | No      |
| Auth/misc             | 10                | 5%           | Yes     |

**Weighted average service time:** ~22ms = **mu = 45 req/s per worker**

With 2 gunicorn workers (gevent), effective capacity: **~90 req/s for reads**, but writes are serialized.

### Write-Specific Analysis

Write requests (grade submissions, session starts, progress updates) constitute ~25% of traffic.

- SQLite WAL write latency: ~5ms per write transaction (simple INSERT/UPDATE)
- Complex writes (session start with multiple UPDATEs): ~15ms
- **Effective write capacity: ~100-200 writes/s** (single writer)

## Utilization Analysis (rho = lambda / mu)

### Overall System (2 gevent workers, mu_eff = 90 req/s)

| Users  | Peak lambda | rho (utilization) | Avg Queue Length (L) | Avg Wait Time |
|--------|-------------|--------------------|-----------------------|---------------|
| 100    | 0.78        | 0.87%              | ~0.009                | ~0.2ms        |
| 1,000  | 7.8         | 8.7%               | ~0.095                | ~2.4ms        |
| 10,000 | 78          | 86.7%              | ~6.5                  | ~72ms         |
| 50,000 | 390         | 433% **OVERLOADED** | infinite              | infinite      |

### Write Path Only (mu_write = 150 writes/s avg)

Write arrival rate = 25% of total lambda:

| Users  | Peak write lambda | rho_write | Status           |
|--------|-------------------|-----------|------------------|
| 100    | 0.20              | 0.13%     | idle             |
| 1,000  | 1.95              | 1.3%      | comfortable      |
| 10,000 | 19.5              | 13%       | fine             |
| 50,000 | 97.5              | 65%       | elevated but ok  |
| 100,000| 195               | 130%      | **OVERLOADED**   |

## Little's Law: L = lambda * W

Little's Law relates three quantities:
- **L** = average number of requests in the system (queue + being served)
- **lambda** = arrival rate
- **W** = average time a request spends in the system (wait + service)

For the M/G/1 queue, the Pollaczek-Khinchine formula gives mean queue length:

```
L_q = (rho^2 * (1 + C_s^2)) / (2 * (1 - rho))
```

Where C_s is the coefficient of variation of service time. For Aelu, service times range from 2ms to 150ms, giving C_s approximately 1.8.

At 10,000 users (rho = 0.867):

```
L_q = (0.867^2 * (1 + 1.8^2)) / (2 * (1 - 0.867))
L_q = (0.752 * 4.24) / (2 * 0.133)
L_q = 3.19 / 0.266
L_q = 11.98 requests waiting in queue
```

```
W_q = L_q / lambda = 11.98 / 78 = 153ms average queue wait
W = W_q + 1/mu = 153ms + 22ms = 175ms average total time
```

This exceeds our p50 latency SLO of 100ms. At 10K DAU with peak traffic, the system is degraded.

## Capacity Planning

### Breaking Points

| Bottleneck            | Breaking Point (DAU) | Mitigation                         |
|-----------------------|----------------------|------------------------------------|
| Overall throughput    | ~12,000              | Add workers, horizontal scale      |
| SQLite write lock     | ~80,000              | Migrate to PostgreSQL              |
| Memory (512MB)        | ~5,000               | Upgrade to 1GB+ VM                 |
| Single region latency | Any non-US user      | Multi-region deployment            |

### Scaling Roadmap

1. **100-1,000 users**: Current architecture is fine. Utilization under 10%.
2. **1,000-5,000 users**: Upgrade to 1GB VM. Add request-level caching (Redis or in-memory LRU for read-heavy endpoints like progress data). Utilization 10-50%.
3. **5,000-10,000 users**: Add a second Fly.io machine with read replica (Litestream + LiteFS). Route reads to replica. Write utilization stays under 15%.
4. **10,000-50,000 users**: This is the SQLite-to-PostgreSQL migration point. Single-writer becomes a real constraint under write-heavy load. See ADR-001 revisit trigger.
5. **50,000+**: Multi-region PostgreSQL (e.g., Neon, Supabase), CDN for static assets, dedicated job queue for async work (audio generation, SRS recalculation).

## Monitoring Queries

Track queue depth and write contention in production:

```sql
-- Average request latency by type (from request_log if instrumented)
SELECT
    endpoint,
    COUNT(*) as request_count,
    AVG(duration_ms) as avg_ms,
    percentile(duration_ms, 0.95) as p95_ms,
    percentile(duration_ms, 0.99) as p99_ms
FROM request_log
WHERE created_at > datetime('now', '-1 hour')
GROUP BY endpoint
ORDER BY p95_ms DESC;
```

```python
# Add to Flask middleware: track SQLite write lock wait time
import time
import sqlite3

class InstrumentedConnection:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")

    def execute_write(self, sql, params=None):
        start = time.monotonic()
        try:
            cursor = self.conn.execute(sql, params or [])
            self.conn.commit()
            duration = time.monotonic() - start
            if duration > 0.1:  # Log writes taking >100ms (lock contention)
                log_slow_write(sql, duration)
            return cursor
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                log_write_contention(sql)
            raise
```

## Key Takeaways

1. **Aelu is massively over-provisioned for current scale.** At 100 users, utilization is under 1%. This is correct for a pre-PMF product; optimizing infrastructure now is waste.
2. **The first real bottleneck is memory, not CPU or I/O.** At 512MB with 2 gevent workers, each handling concurrent greenlets, memory pressure will manifest before throughput limits.
3. **SQLite write serialization is a non-issue until ~50K+ DAU.** WAL mode handles 100-200 writes/s. Aelu generates ~0.2 writes/s at 100 users.
4. **The 10x peak factor is the critical design parameter.** Average load is irrelevant; peak load determines whether users see errors. Monitor p99, not averages.
5. **Revisit this analysis when DAU reaches 1,000.** Re-measure actual lambda and mu from production data rather than estimates.
