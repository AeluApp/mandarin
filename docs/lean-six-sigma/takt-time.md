# Takt Time Analysis — Aelu System Capacity

**Owner:** Jason Gerson
**Created:** 2026-03-10
**Infrastructure:** Fly.io shared-cpu-1x, 512MB RAM, SQLite WAL, 2 gunicorn workers + gevent

---

## 1. Current Demand

### Assumptions
- Active users: 1 (Jason)
- Sessions per user per week: 4
- Drills per session: 15
- Total drill requests per week: 1 x 4 x 15 = 60
- Each drill involves ~3 API calls (render drill, submit answer, get next): 180 requests/week

### Current Load
| Metric | Value |
|--------|-------|
| Requests per week | ~180 |
| Requests per day | ~26 |
| Requests per hour (peak) | ~50 (concentrated in one session) |
| Requests per second (average) | 0.0003 |
| Requests per second (peak) | ~0.14 (during active session) |

---

## 2. Takt Time Calculation

**Takt time = Available capacity / Customer demand**

### Available Capacity

| Component | Capacity |
|-----------|----------|
| Gunicorn workers | 2 |
| Gevent green threads per worker | ~1,000 (default) |
| Theoretical concurrent connections | ~2,000 |
| Practical concurrent requests | ~200 (accounting for SQLite write lock, memory limits) |
| Available time | 24/7 (always-on, auto-start on Fly.io) |
| Effective seconds per week | 604,800 |

### At Current Scale (1 User)

```
Demand: 180 requests/week
Takt time = 604,800 seconds / 180 requests = 3,360 seconds between requests

→ The system needs to handle 1 request every 56 minutes on average.
→ Massive headroom.
```

### At 100 Users

```
Demand: 100 users × 4 sessions/week × 15 drills × 3 API calls = 18,000 requests/week
Takt time = 604,800 / 18,000 = 33.6 seconds between requests (average)

Peak hour (assuming 20% of users active in the same hour):
  20 concurrent users × 15 drills × 3 calls / 3600 seconds = 0.25 requests/second
  → 1 request every 4 seconds at peak

→ Comfortable headroom. No contention issues.
```

### At 1,000 Users

```
Demand: 1,000 users × 4 sessions/week × 15 drills × 3 API calls = 180,000 requests/week
Takt time = 604,800 / 180,000 = 3.36 seconds between requests (average)

Peak hour (20% of users in same hour):
  200 concurrent users × 15 drills × 3 calls / 3600 seconds = 2.5 requests/second
  → 1 request every 0.4 seconds at peak

→ Still within capacity, but SQLite write contention becomes relevant.
```

### At 10,000 Users

```
Demand: 10,000 users × 4 sessions/week × 15 drills × 3 API calls = 1,800,000 requests/week
Takt time = 604,800 / 1,800,000 = 0.34 seconds between requests (average)

Peak hour (20% of users in same hour):
  2,000 concurrent users × 15 drills × 3 calls / 3600 seconds = 25 requests/second
  → 1 request every 0.04 seconds at peak

→ EXCEEDS single-machine capacity. SQLite write lock becomes bottleneck.
  Must scale horizontally (read replicas, or migrate to Turso/Postgres).
```

---

## 3. Capacity Summary Table

| Scale | Users | Req/sec (avg) | Req/sec (peak) | Takt Time | Status |
|-------|-------|--------------|----------------|-----------|--------|
| Current | 1 | 0.0003 | 0.14 | 56 min | Massive headroom |
| Target (12mo) | 100 | 0.03 | 0.25 | 33.6 sec | Comfortable |
| Goal | 1,000 | 0.3 | 2.5 | 3.36 sec | Monitor writes |
| Scale target | 10,000 | 3.0 | 25 | 0.34 sec | Requires architecture change |

---

## 4. Constraint Analysis

### 4.1 The Bottleneck: SQLite Single-Writer

SQLite uses a single-writer lock. WAL (Write-Ahead Logging) mode allows concurrent reads while one write is in progress, but writes are serialized.

**Write operations per drill:**
| Operation | Table | Frequency |
|-----------|-------|-----------|
| UPDATE progress | `progress` | Every drill (1 write) |
| INSERT review_event | `review_event` | Every drill (1 write) |
| INSERT error_log | `error_log` | On incorrect answers (~30% of drills = 1 write) |
| UPSERT error_focus | `error_focus` | On incorrect answers (1 write) |
| INSERT client_event | `client_event` | 3-5 per drill |
| UPDATE session_log | `session_log` | Once per session |
| INSERT session_metrics | `session_metrics` | Once per session |

**Average writes per drill:** ~5-7

**Write throughput needed:**

| Scale | Writes/sec (peak) | SQLite Can Handle? |
|-------|-------------------|-------------------|
| 100 users | ~1.5 writes/sec | Yes (SQLite handles ~1,000 writes/sec in WAL) |
| 1,000 users | ~15 writes/sec | Yes, but monitor for lock wait time |
| 10,000 users | ~150 writes/sec | Maybe not — depends on write complexity |
| 50,000 users | ~750 writes/sec | No — approaching SQLite write ceiling |

**SQLite WAL mode write throughput:** Approximately 500-2,000 simple writes/sec depending on hardware, transaction size, and fsync behavior. On Fly.io shared-cpu-1x (1 vCPU), expect the lower end (~500/sec).

### 4.2 Secondary Constraints

| Constraint | Threshold | Mitigation |
|-----------|-----------|-----------|
| Memory (512MB) | ~200 concurrent connections before OOM | Upgrade to shared-cpu-2x (1GB) at 500+ concurrent users |
| CPU (shared 1x) | CPU-bound scheduling takes ~150ms; at 25 req/sec, scheduling alone uses ~3.75 seconds of CPU per second | Upgrade to dedicated CPU at 1,000+ users |
| Disk I/O | WAL file growth under heavy writes | Periodic WAL checkpoint (SQLite does this automatically) |
| Network (Fly.io) | Single region (ewr) — latency for non-US users | Add regions (lax, ams, nrt) when international users appear |
| Litestream replication | Continuous WAL streaming to S3 — adds write overhead | Negligible at current scale; may need tuning at 1,000+ |
| TTS (client-side) | No server cost, but browser API quality varies | Not a server constraint |

### 4.3 Constraint Progression

```
Users:    1 ────── 100 ────── 1,000 ──────── 10,000 ────── 50,000
                                  │                  │
                                  │                  ├─ SQLite write ceiling
                                  │                  └─ Need: Turso or Postgres
                                  │
                                  ├─ CPU becomes relevant
                                  └─ Need: dedicated-cpu-1x or 2x

Constraint:  None → None → CPU → SQLite writes → Architecture change
```

---

## 5. Scaling Plan

### Phase 1: Current (1-100 users)
- **Infrastructure:** Fly.io shared-cpu-1x, 512MB, single region (ewr)
- **Database:** SQLite WAL, Litestream replication to S3
- **Cost:** ~$7/month
- **Action:** Nothing to change. Monitor.

### Phase 2: Growth (100-1,000 users)
- **Infrastructure:** Fly.io shared-cpu-2x, 1GB, add LAX region
- **Database:** SQLite WAL, still single writer
- **Cost:** ~$15-30/month
- **Action:** Add request latency monitoring. Set up SPC charts for write latency.

### Phase 3: Scale (1,000-10,000 users)
- **Infrastructure:** Fly.io dedicated-cpu-1x, 2GB, 3 regions
- **Database:** Consider Turso (libSQL, distributed SQLite) or migrate to Postgres
- **Cost:** ~$50-100/month
- **Action:** Benchmark SQLite write throughput under realistic load. Plan migration if writes > 50% of capacity.

### Phase 4: If successful (10,000+ users)
- **Infrastructure:** Fly.io dedicated-cpu-2x, 4GB, 5 regions, multiple machines
- **Database:** Turso (distributed) or Postgres with read replicas
- **Cost:** ~$200-500/month
- **Action:** This is a good problem to have.

---

## 6. Takt Time for Content Production

A separate takt time analysis for non-infrastructure capacity:

### Content Production Rate Needed

| Scale | New HSK levels needed | Vocab items | Grammar points | Context notes | Passages |
|-------|----------------------|-------------|----------------|---------------|----------|
| Current | HSK 1-3 complete | 299 | 26 | 299 | ~20 |
| Next | HSK 4 | +600 | +15 | +600 | +30 |
| Full | HSK 1-9 | ~7,000 | ~100+ | ~7,000 | ~200+ |

### Content Production Capacity (Jason, solo)
- Items per hour: ~10 (with context notes, quality review)
- Available hours per week for content: ~5 (competing with engineering, ops, marketing)
- Items per week: ~50
- Time to complete HSK 4: 600 items / 50 per week = **12 weeks**
- Time to complete HSK 1-9 fully: ~7,000 items / 50 per week = **140 weeks (~2.7 years)**

**Content is the long-pole constraint for curriculum expansion.** Not infrastructure.

---

## 7. Key Insight

At Aelu's current scale (1 user) and target scale (1,000 users), infrastructure capacity is not the constraint. The system has 10,000x headroom on compute.

The actual constraints are:
1. **Content production** — one person creating 7,000+ vocabulary items with context notes
2. **User acquisition** — getting from 1 to 1,000 paying users
3. **Solo founder time allocation** — engineering, content, marketing, ops, and support all compete for the same 40-60 hours/week

Optimizing server performance at this stage is overproduction waste. The takt time analysis confirms: spend zero engineering hours on performance optimization until request rates exceed 1/second sustained.
