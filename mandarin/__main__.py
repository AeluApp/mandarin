import sys
import traceback
from pathlib import Path


def main():
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
        log_dir = Path(__file__).parent.parent / "data"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "crash.log"
        tb = traceback.format_exc()
        with open(log_path, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"\n{'='*60}\n")
            f.write(f"{datetime.now().isoformat()}\n")
            f.write(tb)
        print(f"\n  Something went wrong. Details saved to: {log_path}")
        print(f"  Run again or check the log.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
