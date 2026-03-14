import logging
import sys
import traceback
from pathlib import Path


def main():
    from mandarin.log_config import configure_logging, utc_now_iso, CRASH_LOG
    configure_logging(mode="cli")
    logger = logging.getLogger(__name__)

    from mandarin.cli import app
    try:
        app()
    except KeyboardInterrupt:
        print("\n")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        # Log full traceback to file, show clean message to user
        log_dir = CRASH_LOG.parent
        log_dir.mkdir(parents=True, exist_ok=True)
        tb = traceback.format_exc()
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"{utc_now_iso()}\n")
            f.write(tb)
        logger.error("Unhandled exception in CLI: %s", tb.splitlines()[-1])
        print(f"\n  Something went wrong. Details saved to: {CRASH_LOG}", file=sys.stderr)
        print(f"  Run again or check the log.\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
