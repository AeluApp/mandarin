#!/usr/bin/env python3
"""Route audit: detect orphaned routes and dead links in the Flask app.

Parses Flask route decorators from mandarin/web/*.py, then scans
templates and JS files for url_for() calls and href patterns.
Reports orphaned routes (defined but never linked to) and dead links
(references to routes that don't exist).

Exit code 0 if no dead links found, 1 otherwise.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "mandarin" / "web"
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

# Pattern to match @blueprint.route("/path") or @app.route("/path")
ROUTE_RE = re.compile(
    r"""@\w+\.route\(\s*["']([^"']+)["']""",
    re.MULTILINE,
)

# Pattern to match url_for("endpoint_name") in templates and Python
URL_FOR_RE = re.compile(
    r"""url_for\(\s*["']([^"']+)["']""",
    re.MULTILINE,
)

# Pattern to match href="/some/path" in templates and JS
HREF_RE = re.compile(
    r"""href=["'](/[a-zA-Z0-9_/\-\.]+)["']""",
    re.MULTILINE,
)

# Pattern to match fetch("/api/...") or fetch('/api/...') in JS
FETCH_RE = re.compile(
    r"""fetch\(\s*["'](/[a-zA-Z0-9_/\-\.]+)["']""",
    re.MULTILINE,
)


def collect_routes() -> dict[str, str]:
    """Return {route_path: filename} for all Flask routes in web/*.py."""
    routes: dict[str, str] = {}
    for pyfile in sorted(WEB_DIR.glob("*.py")):
        text = pyfile.read_text(errors="replace")
        for m in ROUTE_RE.finditer(text):
            path = m.group(1).split("<")[0].rstrip("/") or "/"
            routes[path] = pyfile.name
    return routes


def collect_references() -> tuple[set[str], set[str]]:
    """Return (url_for_endpoints, href_paths) from templates and JS."""
    url_for_refs: set[str] = set()
    href_refs: set[str] = set()

    scan_dirs = []
    if TEMPLATE_DIR.exists():
        scan_dirs.append(("*.html", TEMPLATE_DIR))
    if STATIC_DIR.exists():
        scan_dirs.append(("*.js", STATIC_DIR))
    # Also scan Python files for url_for
    scan_dirs.append(("*.py", WEB_DIR))

    for glob_pat, scan_dir in scan_dirs:
        for fpath in sorted(scan_dir.rglob(glob_pat)):
            text = fpath.read_text(errors="replace")
            for m in URL_FOR_RE.finditer(text):
                url_for_refs.add(m.group(1))
            for m in HREF_RE.finditer(text):
                href_refs.add(m.group(1).rstrip("/") or "/")
            for m in FETCH_RE.finditer(text):
                href_refs.add(m.group(1).rstrip("/") or "/")

    return url_for_refs, href_refs


def main() -> int:
    routes = collect_routes()
    route_paths = set(routes.keys())
    _url_for_refs, href_refs = collect_references()

    # Orphaned routes: defined but never referenced by any href or fetch
    orphaned = route_paths - href_refs
    # Dead links: hrefs pointing to paths that aren't defined as routes
    dead_links = href_refs - route_paths

    # Filter dead links: ignore fragment-only, static assets, and external
    dead_links = {
        p for p in dead_links
        if not p.startswith("/static/")
        and not p.startswith("/#")
        and not p.endswith(".css")
        and not p.endswith(".js")
        and not p.endswith(".png")
        and not p.endswith(".ico")
    }

    print(f"Defined routes: {len(route_paths)}")
    print(f"Href/fetch references: {len(href_refs)}")
    print()

    if orphaned:
        print(f"Orphaned routes ({len(orphaned)}) — defined but no incoming links:")
        for r in sorted(orphaned):
            print(f"  {r}  ({routes[r]})")
        print()

    if dead_links:
        print(f"Dead links ({len(dead_links)}) — referenced but no matching route:")
        for r in sorted(dead_links):
            print(f"  {r}")
        print()

    if dead_links:
        print("FAIL: dead links found")
        return 1

    print("OK: no dead links found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
