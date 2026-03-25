"""Product Intelligence — cross-platform analyzers.

Two analyzers that inspect platform configuration, assets, session
distribution, error disparities, and Flutter API parity against the
Flask web backend.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3

from ._base import _f, _FILE_MAP, _finding, _safe_query_all, _safe_scalar

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _read_file(path: str) -> str | None:
    """Read a file, returning None on any error."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# 1. Platform Health
# ---------------------------------------------------------------------------

def _analyze_platform_health(conn) -> list[dict]:
    """Inspect platform configs, assets, session distribution, error rates."""
    findings: list[dict] = []

    # ── 1. Capacitor config ───────────────────────────────────────────────
    cap_config_path = os.path.join(_PROJECT_ROOT, "mobile", "capacitor.config.ts")
    cap_content = _read_file(cap_config_path)
    if cap_content is None:
        findings.append(_finding(
            dimension="platform",
            severity="high",
            title="Capacitor config missing",
            analysis=(
                f"Expected {cap_config_path} but file does not exist. "
                "Mobile builds via Capacitor cannot proceed without a config."
            ),
            recommendation="Create mobile/capacitor.config.ts pointing webDir to the Flask static output.",
            claude_prompt=(
                "Create mobile/capacitor.config.ts with appId, appName, and "
                "webDir pointing to the correct build output directory."
            ),
            impact="Mobile app cannot be built or updated via Capacitor.",
            files=["mobile/capacitor.config.ts"],
        ))
    else:
        # Check webDir value
        web_dir_match = re.search(r'webDir\s*:\s*["\']([^"\']+)["\']', cap_content)
        if not web_dir_match:
            findings.append(_finding(
                dimension="platform",
                severity="medium",
                title="Capacitor config missing webDir",
                analysis=(
                    "capacitor.config.ts exists but does not specify a webDir. "
                    "Capacitor needs to know which directory to bundle."
                ),
                recommendation="Add webDir pointing to the web build output (e.g. '../mandarin/web/static').",
                claude_prompt=(
                    "In mobile/capacitor.config.ts, add or fix the webDir property "
                    "to point to the correct build output directory."
                ),
                impact="Capacitor sync will use default and may bundle wrong assets.",
                files=["mobile/capacitor.config.ts"],
            ))

    # ── 2. Tauri config ──────────────────────────────────────────────────
    tauri_config_path = os.path.join(
        _PROJECT_ROOT, "desktop", "tauri-app", "src-tauri", "tauri.conf.json"
    )
    tauri_content = _read_file(tauri_config_path)
    if tauri_content is None:
        findings.append(_finding(
            dimension="platform",
            severity="high",
            title="Tauri config missing",
            analysis=(
                f"Expected {tauri_config_path} but file does not exist. "
                "Desktop builds via Tauri cannot proceed."
            ),
            recommendation="Create desktop/tauri-app/src-tauri/tauri.conf.json.",
            claude_prompt=(
                "Create desktop/tauri-app/src-tauri/tauri.conf.json with "
                "productName, identifier, and build configuration."
            ),
            impact="Desktop app cannot be built via Tauri.",
            files=["desktop/tauri-app/src-tauri/tauri.conf.json"],
        ))
    else:
        try:
            tauri_json = json.loads(tauri_content)
            # Check required keys
            if not tauri_json.get("productName") and not tauri_json.get("identifier"):
                # Tauri v2 uses top-level identifier; v1 uses package.productName
                pkg = tauri_json.get("package", {})
                if not pkg.get("productName"):
                    findings.append(_finding(
                        dimension="platform",
                        severity="low",
                        title="Tauri config missing product metadata",
                        analysis="tauri.conf.json lacks productName/identifier. Builds may use defaults.",
                        recommendation="Add productName and identifier to tauri.conf.json.",
                        claude_prompt=(
                            "In desktop/tauri-app/src-tauri/tauri.conf.json, ensure "
                            "productName and identifier are set."
                        ),
                        impact="Desktop builds may use generic names.",
                        files=["desktop/tauri-app/src-tauri/tauri.conf.json"],
                    ))
        except (json.JSONDecodeError, TypeError):
            findings.append(_finding(
                dimension="platform",
                severity="high",
                title="Tauri config is invalid JSON",
                analysis="tauri.conf.json exists but cannot be parsed as JSON.",
                recommendation="Fix JSON syntax in tauri.conf.json.",
                claude_prompt="Fix JSON syntax errors in desktop/tauri-app/src-tauri/tauri.conf.json.",
                impact="Desktop builds will fail to parse configuration.",
                files=["desktop/tauri-app/src-tauri/tauri.conf.json"],
            ))

    # ── 3. Flutter pubspec.yaml ──────────────────────────────────────────
    flutter_pubspec_path = os.path.join(_PROJECT_ROOT, "flutter_app", "pubspec.yaml")
    flutter_content = _read_file(flutter_pubspec_path)
    if flutter_content is None:
        findings.append(_finding(
            dimension="platform",
            severity="high",
            title="Flutter pubspec.yaml missing",
            analysis=(
                f"Expected {flutter_pubspec_path} but file does not exist. "
                "Flutter builds cannot proceed."
            ),
            recommendation="Create flutter_app/pubspec.yaml with project dependencies.",
            claude_prompt="Create flutter_app/pubspec.yaml with name, version, and dependencies.",
            impact="Flutter app cannot be built.",
            files=["flutter_app/pubspec.yaml"],
        ))

    # ── 4. Platform-specific assets ──────────────────────────────────────
    asset_checks = [
        (
            os.path.join(_PROJECT_ROOT, "mobile", "ios", "App", "App", "Assets.xcassets"),
            "iOS",
            "mobile/ios/App/App/Assets.xcassets/",
        ),
        (
            os.path.join(_PROJECT_ROOT, "mobile", "android", "app", "src", "main", "res"),
            "Android",
            "mobile/android/app/src/main/res/",
        ),
        (
            os.path.join(_PROJECT_ROOT, "flutter_app", "assets"),
            "Flutter",
            "flutter_app/assets/",
        ),
    ]
    missing_assets = []
    for asset_dir, platform_name, _rel_path in asset_checks:
        if not os.path.isdir(asset_dir):
            missing_assets.append(platform_name)

    if missing_assets:
        findings.append(_finding(
            dimension="platform",
            severity="medium",
            title=f"Missing platform assets: {', '.join(missing_assets)}",
            analysis=(
                f"Asset directories missing for: {', '.join(missing_assets)}. "
                "Icon/splash assets may not be configured."
            ),
            recommendation="Generate platform-specific icon and splash assets for each target.",
            claude_prompt=(
                "Ensure icon and splash assets exist for all platforms: "
                + ", ".join(f"{p}" for p in missing_assets) + "."
            ),
            impact="Apps may display default placeholder icons/splash screens.",
            files=[c[2] for c in asset_checks if c[1] in missing_assets],
        ))

    # ── 5. Session distribution across platforms ─────────────────────────
    try:
        rows = _safe_query_all(conn, """
            SELECT COALESCE(client_platform, 'unknown') as platform,
                   COUNT(*) as cnt
            FROM session_log
            WHERE started_at >= datetime('now', '-30 days')
            GROUP BY client_platform
        """)
        if rows:
            platform_sessions = {r["platform"]: r["cnt"] for r in rows}
            # Identify platforms with route definitions but zero sessions
            defined_platforms = set()

            # Web always has routes
            defined_platforms.add("web")
            # iOS/Android defined if Capacitor config exists
            if cap_content is not None:
                defined_platforms.add("ios")
                defined_platforms.add("android")
            # Flutter defined if pubspec exists
            if flutter_content is not None:
                defined_platforms.add("flutter")
            # Desktop defined if Tauri config exists
            if tauri_content is not None:
                defined_platforms.add("desktop")

            zero_session_platforms = []
            for plat in defined_platforms:
                if platform_sessions.get(plat, 0) == 0:
                    zero_session_platforms.append(plat)

            if zero_session_platforms:
                findings.append(_finding(
                    dimension="platform",
                    severity="medium",
                    title=f"No sessions from: {', '.join(sorted(zero_session_platforms))} in 30 days",
                    analysis=(
                        f"Platform configs exist for {', '.join(sorted(defined_platforms))} "
                        f"but {', '.join(sorted(zero_session_platforms))} had zero sessions "
                        f"in the last 30 days. Distribution: {platform_sessions}."
                    ),
                    recommendation=(
                        "Investigate why configured platforms have no active sessions. "
                        "Check deployment status or client_platform tagging."
                    ),
                    claude_prompt=(
                        "Check session_log for client_platform values and verify "
                        "that mobile/desktop clients are correctly tagging their platform."
                    ),
                    impact="Investment in platform configs is wasted if no users are on those platforms.",
                    files=["mandarin/web/session_routes.py"],
                ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass

    # ── 6. Error rate disparities across platforms ───────────────────────
    try:
        error_rows = _safe_query_all(conn, """
            SELECT COALESCE(client_platform, 'unknown') as platform,
                   COUNT(*) as error_count
            FROM client_error_log
            WHERE created_at >= datetime('now', '-30 days')
            GROUP BY client_platform
        """)
        if error_rows and len(error_rows) >= 2:
            platform_errors = {r["platform"]: r["error_count"] for r in error_rows}
            min_errors = min(platform_errors.values())
            max_errors = max(platform_errors.values())
            max_platform = max(platform_errors, key=platform_errors.get)
            min_platform = min(platform_errors, key=platform_errors.get)

            if min_errors > 0 and max_errors / min_errors > 2.0:
                findings.append(_finding(
                    dimension="platform",
                    severity="high",
                    title=f"Error rate disparity: {max_platform} has {max_errors / min_errors:.1f}x more errors than {min_platform}",
                    analysis=(
                        f"Per-platform error counts (last 30 days): {platform_errors}. "
                        f"{max_platform} has >{2}x the error rate of {min_platform}, "
                        "suggesting platform-specific bugs."
                    ),
                    recommendation=(
                        f"Investigate {max_platform}-specific errors in client_error_log. "
                        "Check for browser/OS compatibility issues, missing polyfills, or "
                        "platform-specific rendering problems."
                    ),
                    claude_prompt=(
                        f"Query client_error_log WHERE client_platform='{max_platform}' "
                        "AND created_at >= datetime('now', '-30 days') to identify "
                        "the most frequent error types and stack traces."
                    ),
                    impact=f"Users on {max_platform} experience significantly more errors.",
                    files=["mandarin/web/static/app.js", "mandarin/web/routes.py"],
                ))
    except (sqlite3.OperationalError, sqlite3.Error):
        pass

    return findings


# ---------------------------------------------------------------------------
# 2. Flutter API Parity
# ---------------------------------------------------------------------------

def _analyze_flutter_api_parity(conn) -> list[dict]:
    """Compare Flask API route count with Flutter API client endpoints."""
    findings: list[dict] = []

    # ── 1. Count Flask API routes ────────────────────────────────────────
    web_dir = os.path.join(_PROJECT_ROOT, "mandarin", "web")
    flask_api_routes: set[str] = set()

    for py_file in glob.glob(os.path.join(web_dir, "*.py")):
        content = _read_file(py_file)
        if content is None:
            continue
        # Match @bp.route("/api/..."), @app.route("/api/..."), etc.
        matches = re.findall(
            r'@\w+\.route\s*\(\s*["\'](/api/[^"\']+)["\']',
            content,
        )
        for route in matches:
            # Normalize: strip trailing slashes and path parameters
            normalized = re.sub(r'<[^>]+>', '<param>', route).rstrip("/")
            flask_api_routes.add(normalized)

    # ── 2. Count Flutter API endpoints ───────────────────────────────────
    flutter_api_path = os.path.join(
        _PROJECT_ROOT, "flutter_app", "lib", "api", "api_client.dart"
    )
    flutter_content = _read_file(flutter_api_path)
    flutter_endpoints: set[str] = set()

    if flutter_content is not None:
        # Match URL path patterns like '/api/session/start', "/api/reviews"
        matches = re.findall(
            r'["\'](/api/[^"\']+)["\']',
            flutter_content,
        )
        for endpoint in matches:
            normalized = re.sub(r'\$\{?\w+\}?', '<param>', endpoint).rstrip("/")
            flutter_endpoints.add(normalized)

    # ── 3. Report delta ─────────────────────────────────────────────────
    if flask_api_routes:
        total_flask = len(flask_api_routes)
        total_flutter = len(flutter_endpoints)
        (total_flutter / total_flask * 100) if total_flask > 0 else 0

        missing_in_flutter = flask_api_routes - flutter_endpoints
        # Also check by prefix match (Flutter may abbreviate)
        still_missing = set()
        for route in missing_in_flutter:
            # Check if any flutter endpoint shares the same prefix (first 3 segments)
            prefix = "/".join(route.split("/")[:4])
            if not any(fe.startswith(prefix) for fe in flutter_endpoints):
                still_missing.add(route)

        effective_coverage = ((total_flask - len(still_missing)) / total_flask * 100) if total_flask > 0 else 0

        if effective_coverage < 80:
            severity = "high" if effective_coverage < 50 else "medium"
            sample_missing = sorted(still_missing)[:10]
            findings.append(_finding(
                dimension="platform",
                severity=severity,
                title=f"Flutter API parity: {effective_coverage:.0f}% ({total_flutter}/{total_flask} endpoints)",
                analysis=(
                    f"Flask backend exposes {total_flask} /api/ routes. "
                    f"Flutter api_client.dart references {total_flutter} endpoints. "
                    f"Effective coverage (prefix-matched): {effective_coverage:.0f}%. "
                    f"Missing routes (sample): {sample_missing}"
                ),
                recommendation=(
                    "Add missing API endpoints to flutter_app/lib/api/api_client.dart. "
                    "Prioritize session, review, and content endpoints for feature parity."
                ),
                claude_prompt=(
                    "Compare Flask API routes in mandarin/web/*.py (grep for "
                    "@*.route('/api/...')) with Flutter endpoints in "
                    "flutter_app/lib/api/api_client.dart. Add missing endpoints."
                ),
                impact="Flutter users cannot access all features available on web.",
                files=[
                    "flutter_app/lib/api/api_client.dart",
                    "mandarin/web/routes.py",
                    "mandarin/web/session_routes.py",
                ],
            ))
    elif flutter_content is None and os.path.isdir(os.path.join(_PROJECT_ROOT, "flutter_app")):
        findings.append(_finding(
            dimension="platform",
            severity="medium",
            title="Flutter API client not found",
            analysis=(
                f"Flutter project exists but {flutter_api_path} is missing. "
                "The Flutter app has no centralized API client."
            ),
            recommendation="Create flutter_app/lib/api/api_client.dart as a centralized API layer.",
            claude_prompt=(
                "Create flutter_app/lib/api/api_client.dart with endpoint methods "
                "matching Flask /api/ routes in mandarin/web/*.py."
            ),
            impact="Flutter app may use ad-hoc HTTP calls or lack API integration.",
            files=["flutter_app/lib/api/api_client.dart"],
        ))

    # ── 4. Flutter screens vs web SPA routes ─────────────────────────────
    flutter_lib = os.path.join(_PROJECT_ROOT, "flutter_app", "lib")
    flutter_screens: list[str] = []
    if os.path.isdir(flutter_lib):
        for _root, _dirs, files in os.walk(flutter_lib):
            for fname in files:
                if fname.endswith("_screen.dart"):
                    flutter_screens.append(fname.replace("_screen.dart", ""))

    # Count web route files as a proxy for SPA route surface
    web_route_files = glob.glob(os.path.join(web_dir, "*_routes.py"))
    web_route_modules = [
        os.path.basename(f).replace("_routes.py", "")
        for f in web_route_files
    ]

    if web_route_modules and flutter_screens:
        web_set = set(web_route_modules)
        flutter_set = set(flutter_screens)
        missing_screens = web_set - flutter_set
        # Filter out admin/internal routes that don't need mobile screens
        admin_only = {"admin", "genai_admin", "governance_admin", "strategy_admin",
                      "vibe_admin", "seo", "lti", "gdpr", "openclaw", "gap"}
        missing_user_facing = missing_screens - admin_only

        if len(missing_user_facing) > 3:
            findings.append(_finding(
                dimension="platform",
                severity="low",
                title=f"Flutter missing {len(missing_user_facing)} user-facing screens vs web",
                analysis=(
                    f"Web has route modules for: {sorted(web_set)}. "
                    f"Flutter has screens for: {sorted(flutter_set)}. "
                    f"User-facing modules without Flutter screens: {sorted(missing_user_facing)}."
                ),
                recommendation=(
                    "Add Flutter screens for key user-facing features: "
                    + ", ".join(sorted(missing_user_facing)[:5]) + "."
                ),
                claude_prompt=(
                    "Create Flutter screen files in flutter_app/lib/ for "
                    "missing user-facing features: "
                    + ", ".join(sorted(missing_user_facing)[:5]) + "."
                ),
                impact="Flutter users have fewer screens/features than web users.",
                files=["flutter_app/lib/"],
            ))

    return findings


# ---------------------------------------------------------------------------
# ANALYZERS registry
# ---------------------------------------------------------------------------

ANALYZERS = [_analyze_platform_health, _analyze_flutter_api_parity]
