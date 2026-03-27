"""E2E test fixtures — real Flask server + Playwright browser.

Requires: pip install pytest-playwright && playwright install chromium
"""

import os
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def e2e_server():
    """Start a real Flask server on a random port for E2E testing.

    Creates a fresh database with schema + migrations.
    Content is seeded automatically during onboarding (via _auto_seed_content).
    """
    # Create a temporary data directory with its own DB
    tmp_dir = tempfile.mkdtemp(prefix="aelu_e2e_")
    db_path = Path(tmp_dir) / "mandarin.db"

    # Set environment BEFORE importing any mandarin modules
    os.environ["DATA_DIR"] = tmp_dir
    os.environ["IS_PRODUCTION"] = "0"

    # Now import and initialize
    from mandarin import db
    from mandarin.db.core import _migrate

    # Monkey-patch DB_PATH so connection() uses our temp DB
    import mandarin.db.core as db_core
    db_core.DB_PATH = db_path
    db_core.DB_DIR = db_path.parent

    conn = db.init_db(db_path)
    _migrate(conn)

    # Pre-seed HSK 1 content so tests don't depend on onboarding auto-seed
    try:
        from mandarin.importer import import_hsk_level
        added, _ = import_hsk_level(conn, 1)
        print(f"E2E: Pre-seeded {added} HSK 1 items")
    except Exception as e:
        print(f"E2E: HSK seed failed (tests needing content may fail): {e}")

    conn.close()

    from mandarin.web import create_app
    app = create_app(testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "e2e-test-secret-key-for-testing"

    # Find a free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    # Start server in background thread
    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False, debug=False),
        daemon=True,
    )
    server_thread.start()

    # Wait for server to be ready
    base_url = f"http://127.0.0.1:{port}"
    import urllib.request
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{base_url}/api/health/live", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    yield base_url

    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def mobile_page(page):
    """Page fixture with mobile viewport (iPhone 13/14 dimensions) and touch enabled."""
    page.set_viewport_size({"width": 375, "height": 812})
    yield page
