"""Standalone Flask server for desktop app sidecar."""
import os
import sys
from . import create_app
from ..settings import IS_PRODUCTION


def main():
    try:
        port = int(os.environ.get("PORT", 0)) or (int(sys.argv[1]) if len(sys.argv) > 1 else 5173)
    except ValueError:
        print(f"Invalid port: {sys.argv[1]}")
        sys.exit(1)
    host = "0.0.0.0" if IS_PRODUCTION else "127.0.0.1"
    app = create_app()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
