"""PyInstaller entry point for the Mandarin Flask server sidecar."""
import sys
from mandarin.web import create_app


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173
    app = create_app()
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
