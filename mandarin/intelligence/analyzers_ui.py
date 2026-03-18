"""UI visual design analyzers — detect style inconsistencies from code inspection."""
import os
import re
import logging
from ._base import _finding

logger = logging.getLogger(__name__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _read_file(path):
    try:
        with open(os.path.join(_PROJECT_ROOT, path)) as f:
            return f.read()
    except Exception:
        return ""

def _analyze_css_consistency(conn):
    """Check CSS for spacing scale violations."""
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        # Find padding declarations not using var(--space-*)
        hardcoded = re.findall(r'padding:\s*(\d+)px', css)
        non_scale = [p for p in hardcoded if int(p) not in (0, 2, 4, 8, 12, 16, 24, 32, 48, 64)]
        if len(non_scale) > 5:
            findings.append(_finding(
                "ui", "low",
                f"{len(non_scale)} CSS padding values don't follow spacing scale",
                f"Found {len(non_scale)} hardcoded padding values not on the 8px scale. "
                f"Examples: {', '.join(non_scale[:5])}px",
                "Replace hardcoded padding with var(--space-*) tokens.",
                "Replace hardcoded padding values with spacing scale variables in style.css.",
                "Design system consistency",
                ["mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings

def _analyze_responsive_tables(conn):
    """Check if admin tables have responsive wrappers."""
    findings = []
    try:
        html = _read_file("mandarin/web/templates/admin.html")
        tables = len(re.findall(r'class="admin-table"', html))
        wrapped = len(re.findall(r'class="table-wrap"', html))
        unwrapped = tables - wrapped
        if unwrapped > 0:
            findings.append(_finding(
                "ui", "medium",
                f"{unwrapped} admin tables lack responsive wrapper (broken on mobile)",
                f"{unwrapped} of {tables} admin tables don't have a .table-wrap div. "
                f"These tables overflow on mobile screens.",
                "Wrap all admin-table elements in <div class='table-wrap'>.",
                "Add <div class='table-wrap'> around all admin tables in admin.html.",
                "Mobile responsive design",
                ["mandarin/web/templates/admin.html"],
            ))
    except Exception:
        pass
    return findings

def _analyze_icon_accessibility(conn):
    """Check for icon-only buttons missing aria-label."""
    findings = []
    try:
        html = _read_file("mandarin/web/templates/index.html")
        # Find buttons containing SVG but no text content
        svg_buttons = re.findall(r'<button[^>]*>[\s]*<svg', html)
        no_label = [b for b in svg_buttons if 'aria-label' not in b]
        if no_label:
            findings.append(_finding(
                "ui", "medium",
                f"{len(no_label)} icon-only buttons missing aria-label",
                f"Found {len(no_label)} buttons with only an SVG icon and no aria-label. "
                f"Screen readers cannot identify these buttons.",
                "Add aria-label to all icon-only buttons.",
                "Add aria-label attributes to icon-only buttons in index.html.",
                "Accessibility compliance",
                ["mandarin/web/templates/index.html"],
            ))
    except Exception:
        pass
    return findings

def _analyze_color_usage(conn):
    """Check if accent color is overused (too many roles)."""
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        accent_uses = len(re.findall(r'var\(--color-accent\)', css))
        if accent_uses > 30:
            findings.append(_finding(
                "ui", "low",
                f"Accent color used {accent_uses} times — may indicate insufficient semantic differentiation",
                f"The accent color (--color-accent) appears {accent_uses} times in CSS. "
                f"Different UI contexts (buttons, links, badges, highlights) may benefit from distinct colors.",
                "Introduce semantic color variants for different contexts.",
                "Review accent color usage in style.css and introduce --color-link, --color-badge variants.",
                "Color system maturity",
                ["mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings

def _analyze_platform_style_drift(conn):
    """Check if Flutter theme diverges from web CSS variables."""
    findings = []
    try:
        flutter_theme = _read_file("flutter_app/lib/theme.dart") or _read_file("flutter_app/lib/config.dart")
        if not flutter_theme:
            findings.append(_finding(
                "platform", "low",
                "Flutter theme file not found — potential visual drift from web",
                "No theme.dart or config.dart found in flutter_app/lib/. "
                "Flutter UI may not match web design system.",
                "Create a Flutter theme that mirrors web CSS variables.",
                "Create flutter_app/lib/theme.dart with colors/fonts matching mandarin/web/static/style.css variables.",
                "Cross-platform visual consistency",
                ["flutter_app/lib/"],
            ))
    except Exception:
        pass
    return findings

ANALYZERS = [
    _analyze_css_consistency,
    _analyze_responsive_tables,
    _analyze_icon_accessibility,
    _analyze_color_usage,
    _analyze_platform_style_drift,
]
