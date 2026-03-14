"""Standalone Flask server for desktop app sidecar."""
import logging
import sys
from . import create_app
from ..settings import IS_PRODUCTION, PORT, DEFAULT_PORT

logger = logging.getLogger(__name__)


def main():
    try:
        port = PORT or (int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT)
    except ValueError:
        logger.error("Invalid port: %s", sys.argv[1])
        print(f"Invalid port: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    host = "0.0.0.0" if IS_PRODUCTION else "127.0.0.1"
    app = create_app()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
