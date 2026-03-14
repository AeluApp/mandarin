"""PyInstaller entry point for the Mandarin Flask server sidecar."""
import sys
from mandarin.web import create_app
from mandarin.settings import PORT, DEFAULT_PORT


def main():
    port = PORT or (int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT)
    app = create_app()
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
