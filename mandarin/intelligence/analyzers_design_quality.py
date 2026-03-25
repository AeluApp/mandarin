"""Design quality analyzers — detect visual-vibe drift, token mismatches, and motion gaps."""
import json
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


# ── Helpers ──────────────────────────────────────────────────────────────

def _parse_css_block(css, block_start_pattern):
    """Extract a CSS block (the { ... } contents) following a pattern match.

    Returns the content between the opening and closing braces, or empty string.
    """
    m = re.search(block_start_pattern, css)
    if not m:
        return ""
    start = css.find("{", m.start())
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[start + 1:i]
    return ""


def _parse_color_vars(block):
    """Extract --color-* variable declarations from a CSS block.

    Returns dict mapping variable name to value, e.g. {"--color-base": "#F2EBE0"}.
    """
    results = {}
    for m in re.finditer(r'(--color-[\w-]+)\s*:\s*([^;]+);', block):
        results[m.group(1)] = m.group(2).strip()
    return results


def _normalize_hex(value):
    """Normalize a hex color to uppercase 6-digit form for comparison.

    Returns the normalized hex string if it looks like a hex color, else the
    original value (lowered/stripped) for non-hex values like 'transparent' or
    rgba(...).
    """
    v = value.strip().upper()
    if v.startswith("#"):
        v = v.lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        return "#" + v[:6]
    return value.strip().lower()


# ── Token name mapping: design-tokens.json camelCase → CSS --color-* ─────

_TOKEN_TO_CSS = {
    "base": "--color-base",
    "surface": "--color-surface",
    "surfaceAlt": "--color-surface-alt",
    "text": "--color-text",
    "textDim": "--color-text-dim",
    "textFaint": "--color-text-faint",
    "textFaintest": "--color-text-faintest",
    "accent": "--color-accent",
    "accentDim": "--color-accent-dim",
    "onAccent": "--color-on-accent",
    "secondary": "--color-secondary",
    "correct": "--color-correct",
    "incorrect": "--color-incorrect",
    "border": "--color-border",
    "divider": "--color-divider",
    "shadow": "--color-shadow",
    "flashErrorBg": "--color-flash-error-bg",
    "flashInfoBg": "--color-flash-info-bg",
    "masteryDurable": "--color-mastery-durable",
    "masteryStable": "--color-mastery-stable",
    "masteryStabilizing": "--color-mastery-stabilizing",
    "skyTop": "--color-sky-top",
    "skyBottom": "--color-sky-bottom",
}

# Color keys that are accent/text (higher severity when mismatched)
_HIGH_SEVERITY_KEYS = {
    "text", "textDim", "textFaint", "accent", "accentDim", "onAccent",
    "correct", "incorrect", "secondary",
}


# ── Check 1: Color token consistency ─────────────────────────────────────

def _check_color_token_consistency(conn):
    """Compare design-tokens.json color values against CSS :root variables."""
    findings = []
    try:
        tokens_raw = _read_file("mandarin/web/static/design-tokens.json")
        css = _read_file("mandarin/web/static/style.css")
        if not tokens_raw or not css:
            return findings

        tokens = json.loads(tokens_raw)
        light_tokens = tokens.get("color", {}).get("light", {})

        # Parse :root block (first occurrence = light mode defaults)
        root_block = _parse_css_block(css, r':root\s*\{')
        css_vars = _parse_color_vars(root_block)

        mismatches = []
        for token_key, token_value in light_tokens.items():
            css_name = _TOKEN_TO_CSS.get(token_key)
            if not css_name or css_name not in css_vars:
                continue
            css_value = css_vars[css_name]
            # Only compare hex values — skip rgba, transparent, var() refs
            if not token_value.startswith("#") or not css_value.startswith("#"):
                continue
            if _normalize_hex(token_value) != _normalize_hex(css_value):
                mismatches.append((token_key, css_name, token_value, css_value))

        if mismatches:
            has_high = any(m[0] in _HIGH_SEVERITY_KEYS for m in mismatches)
            severity = "high" if has_high else "medium"
            detail_lines = [
                f"  {tk}: JSON={tv}  CSS={cv}"
                for tk, cn, tv, cv in mismatches[:8]
            ]
            findings.append(_finding(
                "visual_vibe", severity,
                f"{len(mismatches)} color token(s) differ between design-tokens.json and CSS :root",
                f"The following color tokens in design-tokens.json do not match their "
                f"CSS custom-property counterparts in :root:\n" + "\n".join(detail_lines),
                "Update CSS :root variables (or design-tokens.json) so they are identical.",
                "Reconcile mismatched color tokens between mandarin/web/static/design-tokens.json "
                "and the :root block in mandarin/web/static/style.css. The design-tokens.json "
                "file is the single source of truth.",
                "Brand color consistency across platforms",
                ["mandarin/web/static/design-tokens.json", "mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings


# ── Check 2: Dark mode coverage ──────────────────────────────────────────

def _check_dark_mode_coverage(conn):
    """Flag light-mode --color-* variables missing a dark-mode override."""
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        if not css:
            return findings

        # Light-mode variables from :root
        root_block = _parse_css_block(css, r':root\s*\{')
        light_vars = set(_parse_color_vars(root_block).keys())

        # Dark-mode variables from html[data-theme="dark"]
        dark_block = _parse_css_block(css, r'html\[data-theme="dark"\]\s*\{')
        dark_vars = set(_parse_color_vars(dark_block).keys())

        missing = sorted(light_vars - dark_vars)
        if missing:
            findings.append(_finding(
                "visual_vibe", "medium",
                f"{len(missing)} light-mode color variable(s) have no dark-mode override",
                f"These --color-* variables are defined in :root (light) but not in "
                f'html[data-theme="dark"]: {", ".join(missing[:10])}'
                + (f" ... and {len(missing) - 10} more" if len(missing) > 10 else ""),
                'Add matching overrides in the html[data-theme="dark"] block for all light-mode color variables.',
                'Add dark-mode overrides for missing --color-* variables in the '
                'html[data-theme="dark"] block of mandarin/web/static/style.css. '
                'Reference mandarin/web/static/design-tokens.json dark color values.',
                "Dark mode visual completeness",
                ["mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings


# ── Check 3: Reduced motion coverage ────────────────────────────────────

def _check_reduced_motion_coverage(conn):
    """Flag @keyframes animations not addressed in prefers-reduced-motion blocks."""
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        if not css:
            return findings

        # Collect all @keyframes names
        all_keyframes = set(re.findall(r'@keyframes\s+([\w-]+)', css))

        # Collect all prefers-reduced-motion blocks and their contents
        reduced_blocks = []
        for m in re.finditer(r'@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{', css):
            block = _parse_css_block(css, re.escape(css[m.start():m.end()].rstrip("{")))
            reduced_blocks.append(block)
        combined_reduced = "\n".join(reduced_blocks)

        # A keyframe is "covered" if the reduced-motion block contains either:
        #   - the keyframe name explicitly (in an animation: none rule or reference)
        #   - a blanket `animation-duration: 0.01ms !important` or `animation: none !important`
        #     on * (universal selector)
        has_blanket = bool(re.search(
            r'\*[^}]*animation-duration:\s*0\.01ms\s*!important', combined_reduced
        ))

        if has_blanket:
            # Blanket rule covers everything — no individual gaps to flag
            return findings

        uncovered = []
        for kf in sorted(all_keyframes):
            if kf not in combined_reduced:
                uncovered.append(kf)

        if uncovered:
            findings.append(_finding(
                "visual_vibe", "medium",
                f"{len(uncovered)} @keyframes animation(s) not covered by prefers-reduced-motion",
                f"These animations have no prefers-reduced-motion override, which may "
                f"cause discomfort for motion-sensitive users: "
                + ", ".join(uncovered[:12])
                + (f" ... and {len(uncovered) - 12} more" if len(uncovered) > 12 else ""),
                "Add animation: none or duration: 0.01ms overrides inside a "
                "@media (prefers-reduced-motion: reduce) block for each uncovered keyframe.",
                "Add prefers-reduced-motion: reduce overrides for uncovered @keyframes "
                "animations in mandarin/web/static/style.css. Either add individual rules "
                "or a blanket *, *::before, *::after { animation-duration: 0.01ms !important; } block.",
                "Accessibility — motion sensitivity",
                ["mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings


# ── Check 4: Typography compliance ──────────────────────────────────────

def _check_typography_compliance(conn):
    """Flag sans-serif font-family declarations in body/paragraph contexts.

    The brand requires serif fonts throughout (Source Serif 4 / Cormorant
    Garamond / Noto Serif SC). Sans-serif is allowed in .admin-*, code/mono
    contexts, and inline hanzi (.hanzi-inline).
    """
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        if not css:
            return findings

        # Allowed sans-serif contexts (regex patterns for the selector)
        allowed_patterns = [
            r'\.admin',
            r'\.hanzi-inline',
            r'code', r'pre', r'\.mono', r'\.code',
            r'font-mono',
            r'--font-mono',
            r'\.keyboard', r'\.kbd',
        ]

        violations = []
        # Find all font-family declarations with sans-serif family names
        sans_families = re.finditer(
            r'([^{}]+?)\{[^}]*?font-family\s*:\s*([^;]*(?:Arial|Helvetica|sans-serif)[^;]*);',
            css, re.DOTALL
        )
        for m in sans_families:
            selector = m.group(1).strip().split("\n")[-1].strip()
            value = m.group(2).strip()
            # Skip if selector matches an allowed context
            if any(re.search(pat, selector, re.IGNORECASE) for pat in allowed_patterns):
                continue
            # Skip CSS custom property definitions for --font-mono
            if "--font-mono" in m.group(0):
                continue
            # Skip if the value itself is a var(--font-mono) reference
            if "var(--font-mono)" in value:
                continue
            violations.append((selector, value))

        if violations:
            detail_lines = [
                f"  {sel}: font-family: {val}"
                for sel, val in violations[:6]
            ]
            findings.append(_finding(
                "visual_vibe", "high",
                f"{len(violations)} font-family declaration(s) use sans-serif outside admin/code contexts",
                f"The brand requires serif typography throughout (Source Serif 4 body, "
                f"Cormorant Garamond headings). These selectors use sans-serif:\n"
                + "\n".join(detail_lines),
                "Replace sans-serif font stacks with var(--font-body) or var(--font-heading).",
                "Replace sans-serif font-family declarations with the appropriate serif "
                "variable (var(--font-body) or var(--font-heading)) in mandarin/web/static/style.css. "
                "Only .admin-*, code/pre/mono, and .hanzi-inline contexts may use sans-serif.",
                "Brand typographic consistency",
                ["mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings


# ── Check 5: Border-radius compliance ────────────────────────────────────

def _check_border_radius_compliance(conn):
    """Flag hardcoded border-radius values that don't use design tokens.

    Allowed values:
      - var(--radius-card) / 8px, var(--radius-illustration) / 12px
      - var(--radius-sm) / 2px, var(--radius-lg) / 6px
      - var(--radius) / 0
      - 50% (circles), 0 (none)
      - Inside .admin-* or .badge selectors
    """
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        if not css:
            return findings

        allowed_values = {"0", "0px", "50%", "2px", "6px", "8px", "12px"}
        violations = []

        # Walk through all border-radius declarations with context
        for m in re.finditer(
            r'([^{}]+?)\{[^}]*?border-radius\s*:\s*([^;]+);',
            css, re.DOTALL
        ):
            selector = m.group(1).strip().split("\n")[-1].strip()
            value = m.group(2).strip()

            # Skip var() references — those use the token system
            if "var(" in value:
                continue

            # Skip admin and badge selectors
            if re.search(r'\.(admin|badge)', selector, re.IGNORECASE):
                continue

            # Check each value in the shorthand (e.g. "8px 8px 0 0")
            parts = value.split()
            for part in parts:
                part = part.strip().rstrip(",")
                if part and part not in allowed_values:
                    violations.append((selector, value))
                    break

        if violations:
            detail_lines = [
                f"  {sel}: border-radius: {val}"
                for sel, val in violations[:8]
            ]
            findings.append(_finding(
                "visual_vibe", "low",
                f"{len(violations)} border-radius value(s) use hardcoded pixels outside design tokens",
                f"These selectors use hardcoded border-radius values not in the token "
                f"system (0/2/6/8/12px or 50%):\n" + "\n".join(detail_lines),
                "Replace hardcoded border-radius with var(--radius-*) tokens or the allowed pixel values.",
                "Replace non-standard hardcoded border-radius values with design-token "
                "variables (var(--radius), var(--radius-sm), var(--radius-lg), "
                "var(--radius-card), var(--radius-illustration)) in mandarin/web/static/style.css.",
                "Design system shape consistency",
                ["mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings


# ── Check 6: Platform drift (Flutter vs. design tokens) ─────────────────

def _check_platform_drift(conn):
    """Compare design-tokens.json colors with Flutter AeluColors constants."""
    findings = []
    try:
        tokens_raw = _read_file("mandarin/web/static/design-tokens.json")
        flutter_src = _read_file("flutter_app/lib/theme/aelu_colors.dart")
        if not tokens_raw or not flutter_src:
            return findings

        tokens = json.loads(tokens_raw)
        light_tokens = tokens.get("color", {}).get("light", {})
        dark_tokens = tokens.get("color", {}).get("dark", {})

        # Parse Flutter Color(0xFFRRGGBB) constants
        flutter_colors = {}
        for m in re.finditer(
            r'static\s+const\s+Color\s+(\w+)\s*=\s*Color\(0xFF([0-9A-Fa-f]{6})\)',
            flutter_src
        ):
            name = m.group(1)
            hex_val = "#" + m.group(2).upper()
            flutter_colors[name] = hex_val

        # Map: (token_key, mode) → flutter_field_name
        comparisons = [
            # Light mode
            ("base", "light", "baseLight"),
            ("text", "light", "textLight"),
            ("accent", "light", "accent"),
            ("correct", "light", "correct"),
            ("secondary", "light", "secondary"),
            # Dark mode
            ("base", "dark", "baseDark"),
            ("text", "dark", "textDark"),
            ("accent", "dark", "accentDark"),
            ("correct", "dark", "correctDark"),
        ]

        drifts = []
        for token_key, mode, flutter_field in comparisons:
            source = light_tokens if mode == "light" else dark_tokens
            token_hex = source.get(token_key, "")
            if not token_hex.startswith("#"):
                continue
            flutter_hex = flutter_colors.get(flutter_field, "")
            if not flutter_hex:
                continue
            if _normalize_hex(token_hex) != _normalize_hex(flutter_hex):
                drifts.append((token_key, mode, token_hex, flutter_field, flutter_hex))

        if drifts:
            detail_lines = [
                f"  {tk} ({mode}): JSON={tv}  Flutter {ff}={fv}"
                for tk, mode, tv, ff, fv in drifts[:8]
            ]
            findings.append(_finding(
                "visual_vibe", "medium",
                f"{len(drifts)} color(s) differ between design-tokens.json and Flutter AeluColors",
                f"Platform visual drift detected — these colors in the Flutter theme "
                f"no longer match the canonical design tokens:\n" + "\n".join(detail_lines),
                "Update Flutter AeluColors constants to match design-tokens.json values.",
                "Update flutter_app/lib/theme/aelu_colors.dart Color constants to match "
                "the canonical values in mandarin/web/static/design-tokens.json.",
                "Cross-platform brand consistency (web vs. Flutter)",
                ["mandarin/web/static/design-tokens.json",
                 "flutter_app/lib/theme/aelu_colors.dart"],
            ))
    except Exception:
        pass
    return findings


# ── Check 7: Ollama visual assessment ────────────────────────────────────

def _check_ollama_visual_assessment(conn):
    """Use Ollama to evaluate CSS patterns against Awwwards best practices."""
    findings = []
    try:
        from ..ai.ollama_client import generate, is_ollama_available
        if not is_ollama_available():
            return findings

        tokens_raw = _read_file("mandarin/web/static/design-tokens.json")
        css = _read_file("mandarin/web/static/style.css")
        if not tokens_raw or not css:
            return findings

        tokens = json.loads(tokens_raw)

        # Build a concise context for the LLM
        color_light = tokens.get("color", {}).get("light", {})
        motion = tokens.get("motion", {})
        shape = tokens.get("shape", {})
        typography = tokens.get("typography", {})

        # Extract key CSS animation patterns (first 50 @keyframes names)
        keyframe_names = re.findall(r'@keyframes\s+([\w-]+)', css)[:50]

        # Count reduced-motion blocks
        reduced_blocks = len(re.findall(r'prefers-reduced-motion:\s*reduce', css))

        prompt = (
            "You are a senior design reviewer evaluating a web application's CSS "
            "against Awwwards best practices.\n\n"
            "## Design tokens\n"
            f"Color palette (light): {json.dumps(color_light, indent=None)}\n"
            f"Motion durations: {json.dumps(motion.get('duration', {}), indent=None)}\n"
            f"Motion easing: {json.dumps(motion.get('easing', {}), indent=None)}\n"
            f"Shape radii: {json.dumps(shape, indent=None)}\n"
            f"Typography fonts: heading={typography.get('fontHeading', 'N/A')}, "
            f"body={typography.get('fontBody', 'N/A')}\n\n"
            "## Animation inventory\n"
            f"Total @keyframes: {len(keyframe_names)}\n"
            f"Names: {', '.join(keyframe_names[:30])}\n"
            f"prefers-reduced-motion blocks: {reduced_blocks}\n\n"
            "## Task\n"
            "List 1-5 specific, actionable issues (if any) where this design system "
            "falls short of Awwwards/FWA-tier quality. Consider ANY aesthetic aspect:\n"
            "- Color contrast, palette harmony, warmth/coolness balance\n"
            "- Motion choreography (too many animations? missing easing variety? "
            "scroll-scrubbed animations tied to scroll position?)\n"
            "- Typography pairing quality, scale hierarchy, line-height for CJK text\n"
            "- Consistency of design language across all surfaces\n"
            "- Whether the overall gestalt feels award-worthy or has rough seams\n"
            "- Whether specific assets (illustrations, hero images) need upgrading\n"
            "- Whether sound design is coupled to visual transitions\n"
            "- Whether page/view transitions feel cinematic vs. abrupt\n"
            "- Whether the design system could benefit from A/B testing an alternative\n\n"
            "For each issue, output exactly one line in this format:\n"
            "ISSUE|<severity:high/medium/low>|<short title>|<one-sentence explanation>\n\n"
            "If no issues are found, output: NONE"
        )

        resp = generate(
            prompt,
            system="You are a design quality auditor. Be concise and specific. "
                   "Only flag genuine issues — do not invent problems.",
            temperature=0.2,
            max_tokens=512,
            conn=conn,
            task_type="aesthetic_quality_evaluation",
        )

        if resp.success and resp.text:
            text = resp.text.strip()
            if text.upper().startswith("NONE"):
                return findings

            for line in text.split("\n"):
                line = line.strip()
                if not line.startswith("ISSUE|"):
                    continue
                parts = line.split("|", 4)
                if len(parts) < 4:
                    continue
                severity = parts[1].strip().lower()
                if severity not in ("critical", "high", "medium", "low"):
                    severity = "medium"
                title = parts[2].strip()
                explanation = parts[3].strip() if len(parts) > 3 else title

                findings.append(_finding(
                    "visual_vibe", severity,
                    f"[LLM] {title}",
                    explanation,
                    "Review and address the identified design quality issue.",
                    f"Address the design quality issue identified by LLM review: {title}. "
                    f"Details: {explanation}",
                    "Awwwards-tier design quality",
                    ["mandarin/web/static/style.css",
                     "mandarin/web/static/design-tokens.json"],
                ))
    except (ImportError, Exception):
        pass
    return findings


# ── Analyzer registry ────────────────────────────────────────────────────

ANALYZERS = [
    _check_color_token_consistency,
    _check_dark_mode_coverage,
    _check_reduced_motion_coverage,
    _check_typography_compliance,
    _check_border_radius_compliance,
    _check_platform_drift,
    _check_ollama_visual_assessment,
]
