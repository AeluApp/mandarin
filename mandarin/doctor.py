"""System health check — verifies all components are working.

Run with: ./run doctor
"""

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from .db.core import DB_PATH

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

# Required data files with minimum expected entries
REQUIRED_DATA_FILES = {
    "hsk/hsk1.json": 50,
    "hsk/hsk2.json": 50,
    "hsk/hsk3.json": 50,
    "hsk_requirements.json": 1,
    "milestones.json": 10,
    "real_world_tasks.json": 10,
}

OPTIONAL_DATA_FILES = [
    "hsk/hsk4.json", "hsk/hsk5.json", "hsk/hsk6.json",
    "hsk/hsk7.json", "hsk/hsk8.json", "hsk/hsk9.json",
    "confusable_pairs.json", "measure_words.json", "radicals.json",
    "reading_passages.json", "media_catalog.json", "slang_expressions.json",
]

REQUIRED_PACKAGES = ["typer", "rich"]
OPTIONAL_PACKAGES = {
    "flask": "Web interface (./run app)",
    "flask_sock": "WebSocket support for web UI",
    "numpy": "Audio processing and tone grading",
    "sounddevice": "Microphone recording for speaking drills",
}


def _check(label: str, ok: bool, detail: str = "") -> dict:
    """Return a check result dict."""
    return {"label": label, "ok": ok, "detail": detail}


def run_checks() -> list:
    """Run all health checks and return results."""
    results = []

    # ── Python version ──
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 9
    results.append(_check(
        "Python version",
        ok,
        f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " (need 3.9+)")
    ))

    # ── Required packages ──
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
            results.append(_check(f"Package: {pkg}", True))
        except ImportError:
            results.append(_check(f"Package: {pkg}", False, "not installed"))

    # ── Optional packages ──
    for pkg, desc in OPTIONAL_PACKAGES.items():
        try:
            __import__(pkg)
            results.append(_check(f"Optional: {pkg}", True, desc))
        except ImportError:
            results.append(_check(f"Optional: {pkg}", False, f"{desc} — not installed"))

    # ── macOS TTS (say command) ──
    has_say = shutil.which("say") is not None
    results.append(_check(
        "macOS TTS (say)",
        has_say,
        "available" if has_say else "not found — audio playback disabled"
    ))

    # ── Data directory ──
    results.append(_check(
        "Data directory",
        DATA_DIR.is_dir(),
        str(DATA_DIR) if DATA_DIR.is_dir() else "missing"
    ))

    # ── Required data files ──
    for fname, min_entries in REQUIRED_DATA_FILES.items():
        path = DATA_DIR / fname
        if not path.exists():
            results.append(_check(f"Data: {fname}", False, "missing"))
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            # Data files may wrap content in a top-level key (e.g., "items", "tasks")
            if isinstance(data, dict) and len(data) <= 5:
                # Find the largest list value — that's the actual data
                lists = [(k, v) for k, v in data.items() if isinstance(v, list)]
                if lists:
                    _, biggest = max(lists, key=lambda x: len(x[1]))
                    count = len(biggest)
                else:
                    count = len(data)
            elif isinstance(data, list):
                count = len(data)
            else:
                count = 0
            ok = count >= min_entries
            results.append(_check(
                f"Data: {fname}",
                ok,
                f"{count} entries" + ("" if ok else f" (expected {min_entries}+)")
            ))
        except (json.JSONDecodeError, OSError) as e:
            results.append(_check(f"Data: {fname}", False, str(e)))

    # ── Optional data files ──
    for fname in OPTIONAL_DATA_FILES:
        path = DATA_DIR / fname
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                count = len(data) if isinstance(data, (list, dict)) else 0
                results.append(_check(f"Data: {fname}", True, f"{count} entries"))
            except (json.JSONDecodeError, OSError):
                results.append(_check(f"Data: {fname}", False, "invalid JSON"))
        else:
            results.append(_check(f"Data: {fname}", False, "not loaded (optional)"))

    # ── Scenario files ──
    scenario_dir = DATA_DIR / "scenarios"
    if scenario_dir.is_dir():
        scenario_count = len(list(scenario_dir.glob("*.json")))
        results.append(_check("Scenarios", scenario_count > 0, f"{scenario_count} files"))
    else:
        results.append(_check("Scenarios", False, "directory missing"))

    # ── Context notes ──
    notes_dir = DATA_DIR / "context_notes"
    if notes_dir.is_dir():
        note_count = len(list(notes_dir.glob("*.json")))
        results.append(_check("Context notes", note_count > 0, f"{note_count} files"))
    else:
        results.append(_check("Context notes", False, "directory missing"))

    # ── Database ──
    if DB_PATH.exists():
        try:
            from . import db as _db
            with _db.connection() as conn:
                # Schema version
                try:
                    row = conn.execute(
                        "SELECT value FROM system_meta WHERE key = 'schema_version'"
                    ).fetchone()
                    version = int(row["value"]) if row else 0
                    from .db.core import SCHEMA_VERSION
                    ok = version >= SCHEMA_VERSION
                    results.append(_check(
                        "Schema version",
                        ok,
                        f"v{version}" + ("" if ok else f" (expected v{SCHEMA_VERSION})")
                    ))
                except (sqlite3.Error, ValueError, TypeError) as e:
                    logger.debug("could not read schema version: %s", e)
                    results.append(_check("Schema version", False, "cannot read"))

                # Table existence
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()]
                expected_tables = [
                    "content_item", "progress", "session_log", "error_log",
                    "dialogue_scenario", "grammar_point", "skill",
                ]
                for t in expected_tables:
                    results.append(_check(f"Table: {t}", t in tables))

                # Content items
                row = conn.execute("SELECT COUNT(*) as cnt FROM content_item").fetchone()
                count = row["cnt"] if row else 0
                results.append(_check("Content items", count > 0, f"{count} items"))

                # WAL mode
                row = conn.execute("PRAGMA journal_mode").fetchone()
                mode = row[0] if row else "unknown"
                results.append(_check("WAL mode", mode == "wal", mode))

                # Foreign keys
                row = conn.execute("PRAGMA foreign_keys").fetchone()
                fk = row[0] if row else 0
                results.append(_check("Foreign keys", fk == 1, "on" if fk else "off"))
        except sqlite3.Error as e:
            results.append(_check("Database", False, str(e)))
    else:
        results.append(_check("Database", False, "not created yet (run a session first)"))

    # ── Disk space ──
    try:
        stat = os.statvfs(str(Path(__file__).parent.parent))
        free_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
        results.append(_check("Disk space", free_mb > 100, f"{free_mb:.0f} MB free"))
    except OSError as e:
        logger.debug("could not check disk space: %s", e)

    return results


def print_report(results: list):
    """Print a formatted doctor report."""
    print()
    print("  Mandarin Learning System — Health Check")
    print("  " + "─" * 42)
    print()

    passed = 0
    warned = 0
    failed = 0

    for r in results:
        if r["ok"]:
            icon = "  ✓"
            passed += 1
        elif "optional" in r["label"].lower() or "Optional" in r["label"]:
            icon = "  ○"
            warned += 1
        else:
            icon = "  –"
            failed += 1

        detail = f"  ({r['detail']})" if r["detail"] else ""
        print(f"  {icon}  {r['label']}{detail}")

    print()
    print(f"  {passed} passed, {warned} optional missing, {failed} failed")
    if failed == 0:
        print("  System is healthy.")
    else:
        print("  Fix the failed checks above.")
    print()


def main():
    results = run_checks()
    print_report(results)
    failed = sum(1 for r in results if not r["ok"] and "optional" not in r["label"].lower() and "Optional" not in r["label"])
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
