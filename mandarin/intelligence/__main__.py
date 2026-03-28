"""CLI entry point for the self-healing loop.

Usage:
    python -m mandarin.intelligence.self_healing [--include-tests] [--verbose]

Runs the complete self-healing loop:
1. Infrastructure health check (memory, disk, error rates, stale locks)
2. Alert ingestion (Sentry, UptimeRobot, GitHub Actions, intelligence findings)
3. Auto-fix classification and application
4. Human review queue for non-fixable issues
5. LLM-based auto-executor for complex code fixes
"""

from __future__ import annotations

import argparse
import json
import logging
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Run the Aelu self-healing loop",
        prog="python -m mandarin.intelligence.self_healing",
    )
    parser.add_argument(
        "--include-tests", action="store_true",
        help="Also run pytest and include test failures in the loop",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging output",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Classify alerts but do not apply any fixes",
    )
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    logger = logging.getLogger("mandarin.intelligence.self_healing")

    logger.info("Starting self-healing loop...")

    try:
        from .. import db
        conn = db.get_connection()
    except Exception as exc:
        logger.error("Cannot connect to database: %s", exc)
        sys.exit(1)

    try:
        if args.dry_run:
            _run_dry(conn, include_tests=args.include_tests)
        else:
            from .self_healing import run_self_healing_loop
            result = run_self_healing_loop(conn, include_tests=args.include_tests)
            _print_summary(result)
    except Exception as exc:
        logger.exception("Self-healing loop failed: %s", exc)
        sys.exit(1)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _run_dry(conn, include_tests: bool = False):
    """Dry-run mode: ingest and classify alerts without applying fixes."""
    from .alert_ingestion import ingest_all_alerts, ingest_test_results
    from .auto_fixer import classify_alert

    logger = logging.getLogger("mandarin.intelligence.self_healing")

    alerts = ingest_all_alerts(conn)
    if include_tests:
        try:
            alerts.extend(ingest_test_results())
        except Exception as exc:
            logger.warning("Test ingestion failed: %s", exc)

    logger.info("Ingested %d alerts (dry-run mode — no fixes will be applied)", len(alerts))

    auto_fixable = 0
    human_review = 0

    for alert in alerts:
        classification = classify_alert(alert)
        status = "AUTO-FIX" if classification["auto_fixable"] else "HUMAN"
        if classification["auto_fixable"]:
            auto_fixable += 1
        else:
            human_review += 1

        print(
            f"  [{status:9s}] [{alert.get('severity', '?'):8s}] "
            f"{alert.get('source', '?'):12s} | "
            f"{alert.get('title', '')[:80]}"
        )
        if classification.get("fix_strategy"):
            print(f"             Strategy: {classification['fix_strategy']}")

    print()
    print(f"Total: {len(alerts)} alerts")
    print(f"  Auto-fixable: {auto_fixable}")
    print(f"  Human review: {human_review}")


def _print_summary(result: dict):
    """Print a human-readable summary of the self-healing loop results."""
    print()
    print("=" * 60)
    print("Self-Healing Loop Summary")
    print("=" * 60)
    print(f"  Timestamp:     {result.get('timestamp', 'N/A')}")
    print(f"  Total issues:  {result.get('total_issues', 0)}")
    print(f"  Total actions: {result.get('total_actions', 0)}")
    print(f"  Errors:        {len(result.get('errors', []))}")
    print()

    phases = result.get("phases", {})

    if "health_check" in phases:
        hc = phases["health_check"]
        print("  Health Check:")
        if "error" in hc:
            print(f"    Error: {hc['error']}")
        else:
            print(f"    Issues found: {hc.get('issues_found', 0)}")
            print(f"    Actions taken: {hc.get('actions_taken', 0)}")

    if "ingestion" in phases:
        ing = phases["ingestion"]
        print("  Alert Ingestion:")
        if "error" in ing:
            print(f"    Error: {ing['error']}")
        else:
            print(f"    Total alerts: {ing.get('total_alerts', 0)}")
            by_source = ing.get("by_source", {})
            if by_source:
                print(f"    By source: {json.dumps(by_source)}")
            by_severity = ing.get("by_severity", {})
            if by_severity:
                print(f"    By severity: {json.dumps(by_severity)}")

    if "auto_fix" in phases:
        af = phases["auto_fix"]
        print("  Auto-Fix:")
        if "error" in af:
            print(f"    Error: {af['error']}")
        else:
            print(f"    Classified: {af.get('total_classified', 0)}")
            print(f"    Auto-fixable: {af.get('auto_fixable', 0)}")
            print(f"    Fixed: {af.get('fixed', 0)}")
            print(f"    Failed: {af.get('failed', 0)}")
            print(f"    Human review: {af.get('human_review_queued', 0)}")

    if "auto_executor" in phases:
        ae = phases["auto_executor"]
        print("  Auto-Executor (LLM):")
        if "error" in ae:
            print(f"    Error: {ae['error']}")
        elif "status" in ae:
            print(f"    Status: {ae['status']}")
        else:
            print(f"    Processed: {ae.get('processed', 0)}")
            print(f"    Applied: {ae.get('applied', 0)}")

    errors = result.get("errors", [])
    if errors:
        print()
        print("  Errors:")
        for err in errors:
            print(f"    - {err}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
