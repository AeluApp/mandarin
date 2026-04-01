"""Integration wiring checker — catches disconnected CSS/data/API wires.

Run with: ./run wiring
"""

import json
import re
import sys
from pathlib import Path

from mandarin._paths import DATA_DIR

STATIC_DIR = Path(__file__).parent / "web" / "static"
WEB_DIR = Path(__file__).parent / "web"

# Classes that are legitimately dynamic (composed with variables, not literals)
DYNAMIC_CLASS_PREFIXES = (
    "dot-", "cost-", "hsk-", "section-", "rich-", "rec-state-",
)

# Classes defined outside style.css (browser defaults, third-party, or JS-only state)
KNOWN_EXTERNAL_CLASSES = {
    "hidden", "past", "sr-only", "in-session", "error", "success",
}

# Valid CSS class name pattern: starts with letter or hyphen+letter, then word chars/hyphens
_VALID_CLASS_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*$')


def _check(label, ok, detail=""):
    return {"label": label, "ok": ok, "detail": detail}


def _is_valid_class(cls):
    """Check if a string looks like a valid CSS class name (not a JS variable or operator)."""
    return bool(_VALID_CLASS_RE.match(cls)) and len(cls) >= 2


def _extract_js_classes(js_path):
    """Extract CSS class names used in app.js."""
    text = js_path.read_text()
    classes = set()

    # className = "foo bar" — only literal string values
    for m in re.finditer(r'className\s*=\s*"([^"]+)"', text):
        val = m.group(1)
        # Skip if the value contains JS concatenation (+ sign means dynamic)
        if "+" in val:
            continue
        for cls in val.split():
            if _is_valid_class(cls):
                classes.add(cls)

    # classList.add("foo")
    for m in re.finditer(r'classList\.add\(\s*"([^"]+)"', text):
        cls = m.group(1)
        if _is_valid_class(cls):
            classes.add(cls)

    # class="foo bar" inside HTML template strings
    for m in re.finditer(r'class="([^"]*)"', text):
        val = m.group(1)
        # Skip if it looks like it contains JS expressions
        if "+" in val or "'" in val:
            continue
        for cls in val.split():
            if _is_valid_class(cls):
                classes.add(cls)

    return classes


def _extract_css_selectors(css_path):
    """Extract class names defined in style.css."""
    text = css_path.read_text()
    # Remove comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    classes = set()
    for m in re.finditer(r'\.([a-zA-Z][\w-]*)', text):
        classes.add(m.group(1))
    return classes


def _is_dynamic(cls):
    """Check if a class looks like it's composed dynamically."""
    for prefix in DYNAMIC_CLASS_PREFIXES:
        if cls.startswith(prefix):
            return True
    return False


def _extract_json_fields(obj, prefix=""):
    """Recursively extract all field names from a JSON structure."""
    fields = set()
    if isinstance(obj, dict):
        for key, val in obj.items():
            fields.add(key)
            fields.update(_extract_json_fields(val, prefix=key))
    elif isinstance(obj, list):
        for item in obj:
            fields.update(_extract_json_fields(item, prefix=prefix))
    return fields


def _extract_jsonify_fields(routes_path):
    """Extract field names from jsonify() return dicts in routes.py.

    Only looks at fields inside jsonify() calls to avoid matching
    arbitrary dict keys elsewhere.
    """
    text = routes_path.read_text()
    fields = set()

    # Find jsonify({ ... }) blocks and extract keys from within them
    # Use a simpler heuristic: find lines with jsonify and nearby key:value pairs
    in_jsonify = False
    brace_depth = 0
    for line in text.split("\n"):
        if "jsonify(" in line:
            in_jsonify = True
            brace_depth = 0
        if in_jsonify:
            brace_depth += line.count("{") - line.count("}")
            for m in re.finditer(r'"([\w_]+)"\s*:', line):
                fields.add(m.group(1))
            if brace_depth <= 0 and ")" in line:
                in_jsonify = False

    return fields


def _extract_js_data_fields(js_path):
    """Extract data.fieldName access patterns from app.js."""
    text = js_path.read_text()
    fields = set()
    # data.fieldName (but not data.length, data.forEach, etc.)
    for m in re.finditer(r'\bdata\.(\w+)', text):
        fields.add(m.group(1))
    # data["fieldName"]
    for m in re.finditer(r'data\["([\w_]+)"\]', text):
        fields.add(m.group(1))
    return fields


def check_css_coverage():
    """Check A: CSS classes used in JS but not defined in CSS."""
    results = []
    js_path = STATIC_DIR / "app.js"
    css_path = STATIC_DIR / "style.css"

    if not js_path.exists() or not css_path.exists():
        results.append(_check("CSS coverage", False, "app.js or style.css missing"))
        return results

    js_classes = _extract_js_classes(js_path)
    css_classes = _extract_css_selectors(css_path)

    missing = set()
    for cls in js_classes:
        if cls in css_classes:
            continue
        if cls in KNOWN_EXTERNAL_CLASSES:
            continue
        if _is_dynamic(cls):
            continue
        missing.add(cls)

    if missing:
        detail = ", ".join(sorted(missing))
        results.append(_check(
            "CSS class coverage",
            False,
            f"{len(missing)} classes in JS with no CSS: {detail}"
        ))
    else:
        results.append(_check(
            "CSS class coverage",
            True,
            f"{len(js_classes)} classes used, all defined"
        ))

    return results


def check_data_field_coverage():
    """Check B: media_catalog.json fields not referenced in rendering code."""
    results = []
    catalog_path = DATA_DIR / "media_catalog.json"

    if not catalog_path.exists():
        results.append(_check("Data field coverage", True, "no media_catalog.json (optional)"))
        return results

    try:
        with open(catalog_path) as f:
            catalog = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        results.append(_check("Data field coverage", False, str(e)))
        return results

    fields = _extract_json_fields(catalog)
    # Exclude structural/meta fields
    meta_fields = {"entries"}
    fields -= meta_fields

    # Scan rendering code for field references
    scan_files = []
    js_path = STATIC_DIR / "app.js"
    if js_path.exists():
        scan_files.append(js_path)
    routes_path = WEB_DIR / "routes.py"
    if routes_path.exists():
        scan_files.append(routes_path)
    media_py = Path(__file__).parent / "media.py"
    if media_py.exists():
        scan_files.append(media_py)

    combined_text = ""
    for fp in scan_files:
        combined_text += fp.read_text()

    unreferenced = set()
    for field in fields:
        # Check if the field name appears in any rendering code
        if field not in combined_text:
            unreferenced.add(field)

    if unreferenced:
        detail = ", ".join(sorted(unreferenced))
        results.append(_check(
            "Data field coverage",
            False,
            f"{len(unreferenced)} catalog fields unreferenced: {detail}"
        ))
    else:
        results.append(_check(
            "Data field coverage",
            True,
            f"{len(fields)} fields, all referenced in rendering code"
        ))

    return results


def check_api_contract():
    """Check C: API response fields not consumed by frontend."""
    results = []
    routes_path = WEB_DIR / "routes.py"
    js_path = STATIC_DIR / "app.js"

    if not routes_path.exists() or not js_path.exists():
        results.append(_check("API contract", False, "routes.py or app.js missing"))
        return results

    api_fields = _extract_jsonify_fields(routes_path)
    js_fields = _extract_js_data_fields(js_path)

    # Fields that are internal/health-check/admin — not consumed by app.js
    infrastructure_fields = {
        "status", "error", "reason", "latency_ms", "uptime_seconds",
        "schema_version", "db_size_mb", "content_items", "sessions_30d",
        "learner_count", "missing_tables", "ok",
        # Health/readiness fields
        "status_code", "not_ready",
        # Scheduler detail fields (returned by /api/session/explain, only subset consumed)
        "adaptive_session_length", "base_session_length",
        "preferred_session_length", "target_sessions_per_week",
        "time_of_day_penalty", "modality_weights",
        "day_profile", "is_long_gap", "bounce_levels",
        "new_item_budget",
        # Settings/personalization fields not consumed by name in frontend
        "anonymous_mode", "preferred_domains",
        # Fields consumed via HTML templates (not app.js)
        "tables", "schema_current",
        # xAPI/Caliper — consumed by external LRS, not frontend
        "statements",
        # Upgrade-required error detail field
        "feature",
        # Mastery criteria sub-fields (gates object consumed, but item_id/stage in summary)
        "item_id", "mastery_stage", "gates_met", "difficulty",
        # POST response confirmations
        "encounters_logged",
        # Subscription lifecycle detail fields
        "free_tier_active", "reminder_date", "next_billing_date",
        "valid_reasons",
    }
    api_fields -= infrastructure_fields

    # Only flag fields returned by API but never consumed by frontend
    unconsumed = api_fields - js_fields

    # Filter: check if the field appears anywhere in JS text
    js_text = js_path.read_text()
    truly_unconsumed = set()
    for field in unconsumed:
        if field not in js_text:
            truly_unconsumed.add(field)

    if truly_unconsumed:
        detail = ", ".join(sorted(truly_unconsumed))
        results.append(_check(
            "API contract alignment",
            False,
            f"{len(truly_unconsumed)} API fields unconsumed by frontend: {detail}"
        ))
    else:
        results.append(_check(
            "API contract alignment",
            True,
            f"{len(api_fields)} API fields, all consumed"
        ))

    return results


def run_checks():
    """Run all wiring checks and return results."""
    results = []
    results.extend(check_css_coverage())
    results.extend(check_data_field_coverage())
    results.extend(check_api_contract())
    return results


def print_report(results):
    """Print a formatted wiring report."""
    print()
    print("  Aelu — Wiring Check")
    print("  " + "─" * 42)
    print()

    passed = 0
    failed = 0

    for r in results:
        if r["ok"]:
            icon = "  ✓"
            passed += 1
        else:
            icon = "  –"
            failed += 1

        detail = f"  ({r['detail']})" if r["detail"] else ""
        print(f"  {icon}  {r['label']}{detail}")

    print()
    print(f"  {passed} passed, {failed} failed")
    if failed == 0:
        print("  All wires connected.")
    else:
        print("  Fix the disconnected wires above.")
    print()


def main():
    results = run_checks()
    print_report(results)
    failed = sum(1 for r in results if not r["ok"])
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
