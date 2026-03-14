"""SQLite load test — simulate concurrent read/write patterns."""
import sqlite3
import threading
import time
import argparse
import statistics
import shutil
import tempfile
import random
from pathlib import Path


def setup_wal(db_path: str) -> None:
    """Enable WAL mode on the database."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()


def reader_thread(db_path: str, duration: float, results: dict, thread_id: int) -> None:
    """Simulate read-heavy patterns: get_items_due, session_log lookups."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    queries = [
        # get_items_due pattern
        """SELECT ci.id, ci.hanzi, ci.pinyin, ci.english,
                  p.ease_factor, p.interval_days, p.next_review_date
           FROM content_item ci
           LEFT JOIN progress p ON ci.id = p.content_item_id AND p.modality = 'reading'
           WHERE ci.status = 'drill_ready'
             AND (p.next_review_date IS NULL OR p.next_review_date <= date('now'))
           ORDER BY p.next_review_date ASC
           LIMIT 20""",
        # Session log lookup
        """SELECT id, user_id, modality, items_drilled, correct_count, created_at
           FROM session_log
           ORDER BY created_at DESC
           LIMIT 50""",
        # Progress summary
        """SELECT modality, COUNT(*) as cnt, AVG(ease_factor) as avg_ease
           FROM progress
           GROUP BY modality""",
        # Content item count by HSK level
        """SELECT hsk_level, COUNT(*) as cnt
           FROM content_item
           GROUP BY hsk_level""",
    ]

    latencies = []
    errors = 0
    count = 0
    end_time = time.monotonic() + duration

    while time.monotonic() < end_time:
        query = random.choice(queries)
        t0 = time.monotonic()
        try:
            conn.execute(query).fetchall()
            latencies.append(time.monotonic() - t0)
            count += 1
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                errors += 1
            else:
                raise
        # Small jitter to avoid thundering herd
        time.sleep(random.uniform(0.001, 0.01))

    conn.close()
    results[f"reader_{thread_id}"] = {
        "queries": count,
        "latencies": latencies,
        "lock_errors": errors,
    }


def writer_thread(db_path: str, duration: float, results: dict, thread_id: int) -> None:
    """Simulate write patterns: review_event inserts, progress updates.

    Uses a dedicated test table to avoid corrupting real data.
    """
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Create a test table for writes (idempotent)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _load_test_writes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER,
            write_type TEXT,
            payload TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    latencies = []
    errors = 0
    count = 0
    end_time = time.monotonic() + duration

    write_types = ["review_event", "progress_update", "session_insert"]

    while time.monotonic() < end_time:
        wtype = random.choice(write_types)
        t0 = time.monotonic()
        try:
            conn.execute(
                "INSERT INTO _load_test_writes (thread_id, write_type, payload) VALUES (?, ?, ?)",
                (thread_id, wtype, f'{{"fake": true, "ts": {time.time()}}}'),
            )
            conn.commit()
            latencies.append(time.monotonic() - t0)
            count += 1
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                errors += 1
            else:
                raise
        # Writers are slower than readers
        time.sleep(random.uniform(0.01, 0.05))

    conn.close()
    results[f"writer_{thread_id}"] = {
        "queries": count,
        "latencies": latencies,
        "lock_errors": errors,
    }


def run_load_test(db_path: str, num_readers: int, num_writers: int, duration: float) -> None:
    """Run concurrent load test and print results."""
    src = Path(db_path)
    if not src.exists():
        print(f"ERROR: Database not found at {src}")
        return

    # Work on a temporary copy to avoid touching real data
    tmp_dir = tempfile.mkdtemp(prefix="mandarin_loadtest_")
    tmp_db = Path(tmp_dir) / "test.db"
    print(f"Copying database to {tmp_db} ...")
    shutil.copy2(src, tmp_db)
    # Also copy WAL/SHM if they exist
    for ext in (".wal", ".shm"):
        wal = src.with_suffix(src.suffix + ext)
        if wal.exists():
            shutil.copy2(wal, tmp_db.with_suffix(tmp_db.suffix + ext))

    setup_wal(str(tmp_db))
    print(f"WAL mode enabled. Running {num_readers} readers + {num_writers} writers for {duration}s ...\n")

    results: dict = {}
    threads = []

    for i in range(num_readers):
        t = threading.Thread(target=reader_thread, args=(str(tmp_db), duration, results, i))
        threads.append(t)

    for i in range(num_writers):
        t = threading.Thread(target=writer_thread, args=(str(tmp_db), duration, results, i))
        threads.append(t)

    t_start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_time = time.monotonic() - t_start

    # Aggregate results
    all_read_latencies = []
    all_write_latencies = []
    total_read_queries = 0
    total_write_queries = 0
    total_lock_errors = 0

    for key, val in sorted(results.items()):
        if key.startswith("reader_"):
            all_read_latencies.extend(val["latencies"])
            total_read_queries += val["queries"]
        else:
            all_write_latencies.extend(val["latencies"])
            total_write_queries += val["queries"]
        total_lock_errors += val["lock_errors"]

    print("=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)
    print(f"  Wall time:        {wall_time:.1f}s")
    print(f"  Readers:          {num_readers}")
    print(f"  Writers:          {num_writers}")
    print()

    if all_read_latencies:
        sorted_r = sorted(all_read_latencies)
        p95_r = sorted_r[int(len(sorted_r) * 0.95)] if len(sorted_r) > 1 else sorted_r[0]
        print("  READS")
        print(f"    Total queries:  {total_read_queries}")
        print(f"    Queries/sec:    {total_read_queries / wall_time:.1f}")
        print(f"    Avg latency:    {statistics.mean(all_read_latencies) * 1000:.2f} ms")
        print(f"    P95 latency:    {p95_r * 1000:.2f} ms")
        print(f"    Max latency:    {max(all_read_latencies) * 1000:.2f} ms")
        print()

    if all_write_latencies:
        sorted_w = sorted(all_write_latencies)
        p95_w = sorted_w[int(len(sorted_w) * 0.95)] if len(sorted_w) > 1 else sorted_w[0]
        print("  WRITES")
        print(f"    Total queries:  {total_write_queries}")
        print(f"    Queries/sec:    {total_write_queries / wall_time:.1f}")
        print(f"    Avg latency:    {statistics.mean(all_write_latencies) * 1000:.2f} ms")
        print(f"    P95 latency:    {p95_w * 1000:.2f} ms")
        print(f"    Max latency:    {max(all_write_latencies) * 1000:.2f} ms")
        print()

    print(f"  Lock contention errors: {total_lock_errors}")
    total_ops = total_read_queries + total_write_queries
    if total_ops > 0 and total_lock_errors > 0:
        print(f"  Contention rate:  {total_lock_errors / total_ops * 100:.2f}%")
    print("=" * 60)

    # Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"\nTemp database cleaned up.")


def main():
    parser = argparse.ArgumentParser(description="SQLite load test for Mandarin learning system")
    parser.add_argument(
        "--db-path", default="data/mandarin.db",
        help="Path to SQLite database (default: data/mandarin.db)",
    )
    parser.add_argument("--readers", type=int, default=10, help="Number of reader threads (default: 10)")
    parser.add_argument("--writers", type=int, default=3, help="Number of writer threads (default: 3)")
    parser.add_argument("--duration", type=float, default=30, help="Test duration in seconds (default: 30)")
    args = parser.parse_args()

    run_load_test(args.db_path, args.readers, args.writers, args.duration)


if __name__ == "__main__":
    main()
