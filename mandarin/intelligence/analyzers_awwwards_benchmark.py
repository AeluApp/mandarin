"""Awwwards/FWA benchmark analyzers — measure Aelu against award-winning design practices.

Checks scroll choreography density, view transition coverage, micro-interaction
variety, type scale range, email illustration usage, and cross-platform parity
for radius/timing values.
"""
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


# ── Check 1: Scroll choreography density ───────────────────────────────

def _check_scroll_choreography_density(conn):
    """Count elements with continuous scroll-scrubbed animation bindings.

    FWA winners average 5+ scroll-driven choreography layers per landing page.
    One-shot IntersectionObserver reveals (data-reveal) don't count — only
    continuous bindings to scroll position (animation-timeline, --scroll-progress
    calc() usage, data-scroll-section with transform bindings).
    """
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        landing_html = _read_file("marketing/landing/index.html")
        if not css and not landing_html:
            return findings

        continuous_layers = 0

        # CSS animation-timeline: view() or scroll() — native scroll-driven
        continuous_layers += len(re.findall(r'animation-timeline:\s*(?:view|scroll)\(\)', css))

        # CSS calc() expressions using --scroll-progress (continuously interpolated)
        continuous_layers += len(re.findall(
            r'calc\([^)]*var\(--scroll-progress\)', css
        ))

        # Landing page inline styles using --scroll-progress
        continuous_layers += len(re.findall(
            r'calc\([^)]*var\(--scroll-progress\)', landing_html
        ))

        # data-scroll-section elements with continuous transform bindings in CSS
        # (not just one-shot reveals, but rules referencing --scroll-progress)
        scroll_section_selectors = re.findall(
            r'\[data-scroll-section\][^{]*\{[^}]*var\(--scroll-progress\)', css
        )
        continuous_layers += len(scroll_section_selectors)

        target = 5
        if continuous_layers < target:
            findings.append(_finding(
                "visual_vibe", "medium",
                f"Scroll choreography density is {continuous_layers}/{target} "
                f"(FWA winners average {target}+ layers)",
                f"The landing page has {continuous_layers} continuous scroll-driven "
                f"animation layer(s). Award-winning sites typically bind 5+ elements "
                f"to scroll position for a cinematic feel — parallax images, staggered "
                f"text reveals, opacity fades, scale shifts, and horizontal scroll "
                f"sections all tied to scroll progress rather than binary show/hide.",
                "Add continuous scroll-scrubbed animations to the landing page using "
                "var(--scroll-progress) in CSS calc() expressions. Consider: "
                "continuous parallax on feature cards, horizontal-scroll storytelling "
                "sections, and typography scale shifts tied to scroll position.",
                "Add continuous scroll-driven animations to marketing/landing/index.html "
                "and mandarin/web/static/style.css. Bind element transforms and opacity "
                "to var(--scroll-progress) using calc(). The scroll-engine.js already "
                "provides --scroll-progress per [data-scroll-section]. Use CSS like: "
                "transform: translateY(calc((1 - var(--scroll-progress)) * 30px)); "
                "opacity: calc(var(--scroll-progress) * 1.2);",
                "Landing page scroll-driven immersiveness",
                ["marketing/landing/index.html", "mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings


# ── Check 2: View transition coverage ──────────────────────────────────

def _check_view_transition_coverage(conn):
    """Count elements with view-transition-name and how many navigations use the API.

    FWA winners transition between all major views with shared-element morphing.
    """
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        app_js = _read_file("mandarin/web/static/app.js")
        if not css:
            return findings

        # Count view-transition-name declarations in CSS
        transition_names = re.findall(r'view-transition-name:\s*([\w-]+)', css)
        unique_names = set(transition_names)

        # Count startViewTransition calls in JS
        _vt_calls = len(re.findall(r'startViewTransition|viewTransition\(', app_js)) if app_js else 0

        target_names = 8
        if len(unique_names) < target_names:
            missing_suggestions = []
            existing = {n.lower() for n in unique_names}
            candidates = [
                ("nav-bar", "Navigation bar (stable across page transitions)"),
                ("drill-question", "Drill question area (morphs between drills)"),
                ("page-heading", "Section/page headings"),
                ("user-avatar", "User avatar/profile element"),
                ("mastery-bar", "Mastery progress bar"),
                ("cta-button", "Primary call-to-action button"),
            ]
            for name, desc in candidates:
                if name not in existing:
                    missing_suggestions.append(f"  {name}: {desc}")

            findings.append(_finding(
                "visual_vibe", "medium",
                f"Only {len(unique_names)} view-transition-name(s) defined "
                f"(target: {target_names}+ for cinematic navigation)",
                f"Currently these elements have view-transition-name: "
                f"{', '.join(sorted(unique_names))}. "
                f"Award-winning sites use shared-element transitions on navigation "
                f"bars, headings, avatars, and key interactive elements so page "
                f"changes feel like smooth morphs rather than hard cuts.\n"
                f"Suggested additions:\n" + "\n".join(missing_suggestions[:6]),
                "Add view-transition-name to more shared elements (nav bar, "
                "headings, drill containers) and wrap all internal navigations "
                "in document.startViewTransition().",
                "Add view-transition-name CSS properties to shared elements in "
                "mandarin/web/static/style.css. Add a global click handler in "
                "mandarin/web/static/app.js that intercepts internal <a> clicks "
                "and wraps navigation in document.startViewTransition(). Elements "
                "to name: nav bar, page headings, drill question area, mastery bar.",
                "Cinematic page transitions",
                ["mandarin/web/static/style.css", "mandarin/web/static/app.js"],
            ))
    except Exception:
        pass
    return findings


# ── Check 3: Micro-interaction variety ─────────────────────────────────

def _check_micro_interaction_variety(conn):
    """Count unique hover/focus/active state transformations per element type.

    Award winners have distinct tactile feedback on every interactive element.
    """
    findings = []
    try:
        css = _read_file("mandarin/web/static/style.css")
        if not css:
            return findings

        # Count interactive elements with :active transform/scale effects
        active_transforms = set()
        for m in re.finditer(r'([^{},\n]+):active\s*\{[^}]*(?:transform|scale)', css, re.DOTALL):
            selector = m.group(1).strip().split("\n")[-1].strip()
            active_transforms.add(selector)

        # Count interactive elements with :hover transform/shadow effects
        hover_effects = set()
        for m in re.finditer(r'([^{},\n]+):hover\s*\{[^}]*(?:transform|box-shadow|scale)', css, re.DOTALL):
            selector = m.group(1).strip().split("\n")[-1].strip()
            hover_effects.add(selector)

        # Count :focus-visible with ring/outline effects
        focus_effects = set()
        for m in re.finditer(r'([^{},\n]+):focus-visible\s*\{[^}]*(?:box-shadow|outline)', css, re.DOTALL):
            selector = m.group(1).strip().split("\n")[-1].strip()
            focus_effects.add(selector)

        # Check for specific missing micro-interaction categories
        missing = []

        # Check for input/textarea focus animation (underline grow, label float)
        has_input_focus_animation = bool(re.search(
            r'(?:input|textarea)[^{]*:focus[^{]*\{[^}]*(?:transform|animation|transition.*width)',
            css, re.DOTALL
        ))
        if not has_input_focus_animation:
            missing.append("Form inputs lack animated focus effects (label float, underline grow)")

        # Check for custom checkbox/radio styling
        has_custom_checkbox = bool(re.search(
            r'input\[type=["\']checkbox["\']\][^{]*(?:::before|::after)[^{]*\{',
            css, re.DOTALL
        ))
        if not has_custom_checkbox:
            missing.append("Checkboxes use browser defaults instead of branded styling")

        has_custom_radio = bool(re.search(
            r'input\[type=["\']radio["\']\][^{]*(?:::before|::after)[^{]*\{',
            css, re.DOTALL
        ))
        if not has_custom_radio:
            missing.append("Radio buttons use browser defaults instead of branded styling")

        # Check for card hover lift
        has_card_hover = bool(re.search(
            r'\.(?:card|panel)[^{]*:hover\s*\{[^}]*transform.*translateY',
            css, re.DOTALL
        ))
        if not has_card_hover:
            missing.append("Cards/panels lack hover lift effect")

        total_unique = len(active_transforms | hover_effects | focus_effects)
        target = 12

        if missing or total_unique < target:
            findings.append(_finding(
                "visual_vibe", "medium" if len(missing) <= 2 else "high",
                f"{len(missing)} micro-interaction gap(s) "
                f"({total_unique} unique interactive states, target: {target}+)",
                f"Award-winning sites have distinct tactile feedback on every "
                f"interactive element. Currently {total_unique} unique elements have "
                f"hover/focus/active effects.\n"
                f"Gaps found:\n" + "\n".join(f"  - {m}" for m in missing),
                "Add branded micro-interactions for form inputs (label float, "
                "underline grow), custom checkbox/radio styling, and card hover "
                "lift effects. All should use --ease-upward timing and have "
                "prefers-reduced-motion fallbacks.",
                "Add micro-interaction CSS to mandarin/web/static/style.css: "
                "(1) Label float animation on input:focus using transform: "
                "translateY(-20px) scale(0.8) on sibling label. "
                "(2) Underline grow on #answer-input using ::after width 0→100%. "
                "(3) Custom checkbox with accent-colored ::before fill animation. "
                "(4) Custom radio with accent-colored inner circle scale animation. "
                "All transitions use var(--ease-upward) and have "
                "@media (prefers-reduced-motion: reduce) fallbacks.",
                "Tactile polish on interactive elements",
                ["mandarin/web/static/style.css"],
            ))
    except Exception:
        pass
    return findings


# ── Check 4: Type scale dramatic range ─────────────────────────────────

def _check_type_scale_range(conn):
    """Check the ratio between largest and smallest text on marketing pages.

    FWA winners use 4.5x+ ratios. Aelu currently tops at 3.2rem display with
    1rem body — a 3.2x ratio.
    """
    findings = []
    try:
        tokens_raw = _read_file("mandarin/web/static/design-tokens.json")
        if not tokens_raw:
            return findings

        tokens = json.loads(tokens_raw)
        scale = tokens.get("typography", {}).get("scale", {})

        # Parse the largest and smallest rem values
        def extract_max_rem(value):
            """Extract the maximum rem value from a clamp() or plain rem value."""
            # clamp(min, preferred, max) — take the max
            clamp_match = re.search(r'clamp\([^,]+,\s*[^,]+,\s*([\d.]+)rem\)', str(value))
            if clamp_match:
                return float(clamp_match.group(1))
            plain_match = re.match(r'([\d.]+)rem', str(value))
            if plain_match:
                return float(plain_match.group(1))
            return None

        sizes = {}
        for key, value in scale.items():
            rem = extract_max_rem(value)
            if rem:
                sizes[key] = rem

        if not sizes:
            return findings

        largest = max(sizes.values())
        smallest = min(sizes.values())
        ratio = largest / smallest if smallest > 0 else 0

        target_ratio = 4.5
        if ratio < target_ratio:
            findings.append(_finding(
                "visual_vibe", "low",
                f"Type scale range is {ratio:.1f}x (target: {target_ratio}x+ for "
                f"marketing pages)",
                f"The type scale ranges from {smallest}rem ('{min(sizes, key=sizes.get)}') "
                f"to {largest}rem ('{max(sizes, key=sizes.get)}') — a {ratio:.1f}x ratio. "
                f"Award-winning marketing pages use dramatic display type "
                f"(4.5x–8x body size) to create visual impact. The core app can keep "
                f"the current scale, but marketing/landing pages benefit from larger "
                f"display headings.",
                "Consider adding a 'display-xl' size at ~4.5rem for marketing hero "
                "headings. This extends the type scale without affecting the app.",
                "Add a display-xl type scale entry to mandarin/web/static/design-tokens.json "
                "at approximately clamp(3rem, 6vw, 4.5rem). Add a corresponding CSS "
                "variable --text-display-xl and use it on marketing hero headings in "
                "marketing/landing/index.html.",
                "Marketing page visual impact via typography",
                ["mandarin/web/static/design-tokens.json", "mandarin/web/static/style.css",
                 "marketing/landing/index.html"],
            ))
    except Exception:
        pass
    return findings


# ── Check 5: Email illustration coverage ───────────────────────────────

def _check_email_illustration_coverage(conn):
    """Check how many email templates actually include header illustrations.

    The base.html template has an {{EMAIL_HEADER_URL}} slot, but individual
    templates may not populate it.
    """
    findings = []
    try:
        email_dir = os.path.join(_PROJECT_ROOT, "marketing", "email-templates")
        if not os.path.isdir(email_dir):
            return findings

        templates = [f for f in os.listdir(email_dir)
                     if f.endswith(".html") and f != "base.html"]

        missing_illustrations = []
        for template_name in sorted(templates):
            content = _read_file(f"marketing/email-templates/{template_name}")
            if not content:
                continue
            # Check if the template provides a header image URL
            # The base template uses {{EMAIL_HEADER_URL}} — individual templates
            # need to set this variable or include an <img> with illustration
            has_illustration = bool(
                re.search(r'EMAIL_HEADER_URL|email_header|header.*\.(jpg|png|webp)', content, re.IGNORECASE)
            )
            if not has_illustration:
                missing_illustrations.append(template_name)

        if missing_illustrations:
            findings.append(_finding(
                "visual_vibe", "low",
                f"{len(missing_illustrations)}/{len(templates)} email template(s) "
                f"lack header illustrations",
                f"These email templates don't include a header illustration: "
                f"{', '.join(missing_illustrations)}. The base.html template has an "
                f"{{{{EMAIL_HEADER_URL}}}} slot designed for this. Adding warm, "
                f"Civic Sanctuary-style watercolor illustrations to emails makes "
                f"them feel like the product rather than generic transactional mail.",
                "Generate header illustrations for each email type using the asset "
                "generator with the Civic Sanctuary style prompt. Queue images for "
                "human approval before deployment.",
                "Use mandarin/ai/asset_generator.py to generate 600px-wide header "
                "illustrations for each email template missing one. Style prompt: "
                "'watercolor, warm Mediterranean tones, linen texture, muted "
                "bougainvillea rose and cypress olive accents, editorial illustration "
                "style'. Queue all generated images as values_decision for human "
                "approval. Suggested themes: activation-nudge (doorway with warm "
                "light), churn-prevention (garden path), feature-announcement "
                "(open window with view), milestone (olive branch), payment-receipt "
                "(stone archway), weekly-progress (study desk by Mediterranean "
                "window), welcome (courtyard with morning light).",
                "Email visual warmth and brand consistency",
                ["marketing/email-templates/" + t for t in missing_illustrations] +
                ["mandarin/ai/asset_generator.py"],
            ))
    except Exception:
        pass
    return findings


# ── Check 6: Cross-platform radius/timing parity ──────────────────────

def _check_cross_platform_radius_timing(conn):
    """Compare Flutter radius and duration values against design-tokens.json.

    Extends the existing color-only platform drift check to cover shape and motion.
    """
    findings = []
    try:
        tokens_raw = _read_file("mandarin/web/static/design-tokens.json")
        flutter_theme = _read_file("flutter_app/lib/theme/aelu_theme.dart")
        if not tokens_raw or not flutter_theme:
            return findings

        tokens = json.loads(tokens_raw)

        drifts = []

        # ── Radius checks ──
        shape = tokens.get("shape", {})

        # Check interactive radius: Flutter _interactiveRadius vs tokens radiusLg/radiusCard
        interactive_match = re.search(r'Radius\.circular\((\d+)\)', flutter_theme)
        if interactive_match:
            flutter_interactive = int(interactive_match.group(1))
            token_card = shape.get("radiusCard", 8)
            token_lg = shape.get("radiusLg", 6)
            # Flutter's 12px interactive radius is intentionally different from
            # web's 6px for touch-target ergonomics. Document but don't flag as
            # a bug — flag only if it deviates from 12px (the documented value).
            if flutter_interactive not in (token_card, token_lg, 12):
                drifts.append(
                    f"Interactive radius: Flutter={flutter_interactive}px, "
                    f"tokens radiusLg={token_lg}px / radiusCard={token_card}px"
                )

        # Check chip radius
        chip_match = re.search(r'_chipRadius.*Radius\.circular\((\d+)\)', flutter_theme)
        if chip_match:
            flutter_chip = int(chip_match.group(1))
            token_card = shape.get("radiusCard", 8)
            if flutter_chip != token_card:
                drifts.append(
                    f"Chip radius: Flutter={flutter_chip}px, tokens radiusCard={token_card}px"
                )

        # ── Duration checks ──
        motion = tokens.get("motion", {}).get("duration", {})

        duration_map = {
            "durationPress": ("press", 80),     # 0.08s = 80ms
            "durationSnappy": ("snappy", 120),   # 0.12s = 120ms
            "durationFast": ("fast", 180),       # 0.18s = 180ms
            "durationNormal": ("base", 300),     # 0.3s = 300ms
        }

        for flutter_name, (token_key, expected_ms) in duration_map.items():
            match = re.search(
                rf'{flutter_name}\s*=\s*Duration\(milliseconds:\s*(\d+)\)',
                flutter_theme
            )
            if match:
                flutter_ms = int(match.group(1))
                token_value = motion.get(token_key, "")
                # Parse token value (e.g., "0.08s" → 80ms)
                token_match = re.match(r'([\d.]+)s', str(token_value))
                token_ms = int(float(token_match.group(1)) * 1000) if token_match else expected_ms

                if flutter_ms != token_ms:
                    drifts.append(
                        f"{flutter_name}: Flutter={flutter_ms}ms, "
                        f"tokens {token_key}={token_ms}ms"
                    )

        # ── Press scale check ──
        scale_match = re.search(r'pressScale\s*=\s*([\d.]+)', flutter_theme)
        if scale_match:
            flutter_scale = float(scale_match.group(1))
            # Web uses 0.95 for .btn-primary:active and 0.98 for #btn-submit
            # Document but flag if neither
            if flutter_scale not in (0.95, 0.97, 0.98):
                drifts.append(
                    f"Press scale: Flutter={flutter_scale}, "
                    f"web btn-primary=0.95 / btn-submit=0.98"
                )

        if drifts:
            findings.append(_finding(
                "visual_vibe", "medium",
                f"{len(drifts)} radius/timing value(s) differ between Flutter and design tokens",
                f"Cross-platform parity gaps found:\n"
                + "\n".join(f"  - {d}" for d in drifts),
                "Align Flutter theme constants to match design-tokens.json values. "
                "Document any intentional differences (like interactive radius for "
                "touch targets) in docs/design-audit.md.",
                "Update flutter_app/lib/theme/aelu_theme.dart duration constants to "
                "match mandarin/web/static/design-tokens.json motion.duration values. "
                "The interactive radius difference (12px Flutter vs 6px web) is "
                "intentional for touch targets — document this in docs/design-audit.md.",
                "Cross-platform visual consistency (shape and timing)",
                ["flutter_app/lib/theme/aelu_theme.dart",
                 "mandarin/web/static/design-tokens.json",
                 "docs/design-audit.md"],
            ))
    except Exception:
        pass
    return findings


# ── Analyzer registry ──────────────────────────────────────────────────

ANALYZERS = [
    _check_scroll_choreography_density,
    _check_view_transition_coverage,
    _check_micro_interaction_variety,
    _check_type_scale_range,
    _check_email_illustration_coverage,
    _check_cross_platform_radius_timing,
]
