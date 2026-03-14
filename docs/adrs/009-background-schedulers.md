# ADR-009: Daemon Thread Schedulers with DB-Backed Locks

## Status

Accepted (2026-02)

## Context

Aelu has several periodic background tasks that must run without user interaction:

1. **Email scheduler** (`email_scheduler.py`): Sends onboarding sequences, re-engagement emails, and retention nudges on a schedule.
2. **Retention scheduler** (`retention_scheduler.py`): Purges expired data according to `retention_policy` table (crash logs after 90 days, client errors after 30 days, security audit logs after 365 days).
3. **Security scan scheduler** (`security_scan_scheduler.py`): Runs bandit (static analysis) and pip-audit (dependency vulnerabilities) on a schedule, storing results in `security_scan` and `security_scan_finding` tables.
4. **Stale session scheduler** (`stale_session_scheduler.py`): Marks abandoned sessions as timed out.

These tasks need to run periodically (hourly, daily, weekly) without blocking web requests.

## Decision Drivers

- No external infrastructure: no Redis, no RabbitMQ, no separate worker process
- Must work on a single Fly.io machine (256MB-1GB RAM)
- Must not interfere with web request handling
- Must be safe against duplicate execution if multiple instances run (future multi-instance deployment)
- Tasks are short-lived (seconds to minutes, not hours)

## Considered Options

### Option 1: Celery + Redis/RabbitMQ

- **Pros**: Industry standard, reliable, task routing, retry logic, monitoring (Flower)
- **Cons**: Requires Redis or RabbitMQ ($5-15/mo), separate worker process, significant memory overhead, overkill for 4 simple periodic tasks

### Option 2: APScheduler

- **Pros**: Python-native, in-process, supports cron-style scheduling, persistent job stores
- **Cons**: Additional dependency, can miss jobs if the process restarts, job store configuration adds complexity

### Option 3: System Cron

- **Pros**: OS-native, reliable, well-understood
- **Cons**: Not available in containerized deployments (Fly.io), requires separate script execution, no easy integration with Flask app context

### Option 4: Custom Daemon Threads with DB-Backed Locks (chosen)

- **Pros**: Zero external dependencies, runs in the same process as Flask, DB locks prevent duplicate execution, simple implementation
- **Cons**: Tied to the Flask process lifecycle (if Flask dies, schedulers die), thread-based concurrency limitations in Python, no task queue or retry logic

## Decision

Implement background schedulers as Python daemon threads that start when the Flask application boots. Each scheduler runs in its own thread with a sleep loop. The `scheduler_lock` table prevents duplicate execution when multiple processes or instances are running.

### Lock Mechanism

```sql
CREATE TABLE scheduler_lock (
    name TEXT PRIMARY KEY,
    locked_by TEXT NOT NULL,     -- hostname:pid
    locked_at TEXT NOT NULL,     -- ISO timestamp
    expires_at TEXT NOT NULL     -- auto-release after this time
);
```

Lock acquisition:

```python
import socket, os
from datetime import datetime, timezone, timedelta

def acquire_lock(db, lock_name, duration_minutes=30):
    """Try to acquire a named lock. Returns True if acquired."""
    now = datetime.now(timezone.utc)
    host_id = f"{socket.gethostname()}:{os.getpid()}"
    expires = now + timedelta(minutes=duration_minutes)

    # Try to insert (new lock)
    try:
        db.execute(
            "INSERT INTO scheduler_lock (name, locked_by, locked_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (lock_name, host_id, now.isoformat(), expires.isoformat())
        )
        db.commit()
        return True
    except Exception:
        pass

    # Try to take over expired lock
    result = db.execute(
        "UPDATE scheduler_lock SET locked_by=?, locked_at=?, expires_at=? "
        "WHERE name=? AND expires_at < ?",
        (host_id, now.isoformat(), expires.isoformat(),
         lock_name, now.isoformat())
    )
    db.commit()
    return result.rowcount > 0

def release_lock(db, lock_name):
    """Release a named lock."""
    db.execute("DELETE FROM scheduler_lock WHERE name=?", (lock_name,))
    db.commit()
```

### Scheduler Pattern

Each scheduler follows the same pattern:

```python
import threading
import time

def start_scheduler(app, interval_seconds=3600):
    """Start a background scheduler as a daemon thread."""
    def run():
        while True:
            time.sleep(interval_seconds)
            try:
                with app.app_context():
                    db = get_db()
                    if acquire_lock(db, 'scheduler_name'):
                        try:
                            do_scheduled_work(db)
                        finally:
                            release_lock(db, 'scheduler_name')
            except Exception as e:
                app.logger.error(f"Scheduler error: {e}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
```

### Schedule

| Scheduler | Interval | Lock Duration | Lock Name |
|-----------|----------|---------------|-----------|
| Email | 1 hour | 30 min | `email_scheduler` |
| Retention | 24 hours | 60 min | `retention_scheduler` |
| Security scan | 24 hours | 120 min | `security_scan` |
| Stale session | 15 minutes | 10 min | `stale_session` |

## Consequences

### Positive

- **Zero external dependencies**: No Redis, no RabbitMQ, no cron. Everything runs in the Flask process.
- **Simple deployment**: A single `docker run` or `fly deploy` starts the web server and all schedulers. No separate worker container.
- **DB-backed locks**: The `scheduler_lock` table ensures that only one instance runs each task, even in a multi-instance deployment. Expired locks auto-release (preventing deadlocks from crashed instances).
- **Low resource usage**: Daemon threads sleep most of the time. Memory overhead is negligible (<1MB per thread).

### Negative

- **Process coupling**: If the Flask process crashes, all schedulers stop. Mitigated by Fly.io's auto-restart and by keeping each scheduler's work short (< 5 minutes).
- **No retry logic**: If a scheduler fails mid-task, it won't retry until the next interval. For critical tasks (email), this could mean delayed delivery. Mitigated by short intervals (email runs hourly).
- **Python GIL**: Daemon threads share the GIL with request-handling threads. A long-running scheduler task could theoretically delay request processing. Mitigated by keeping scheduler work short and I/O-bound (database queries, subprocess calls for bandit/pip-audit).
- **No task visibility**: No dashboard showing queued/running/failed tasks. Errors are logged to the application log. For more visibility, would need a task status table.

### Scaling Limit

This architecture works for a single-instance or dual-instance deployment. Beyond 3-4 instances, the DB-backed locking becomes a bottleneck (frequent lock contention on SQLite). At that point, migrate to a proper job queue (Celery with Redis, or a managed queue service).
