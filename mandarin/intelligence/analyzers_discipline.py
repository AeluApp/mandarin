"""Product Intelligence — discipline analyzers for static code inspection.

10 analyzers that inspect actual code files (CSS, JS, templates, static assets)
rather than user data. Covers visual design, animation, sound, copywriting,
branding, mobile performance, behavioral economics, strategy, QA reliability,
and operations research patterns.
"""

from __future__ import annotations

import glob
import os
import re

from ._base import _f, _FILE_MAP, _finding

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

_TEMPLATE_DIR = os.path.join(_PROJECT_ROOT, "mandarin", "web", "templates")
_STATIC_DIR = os.path.join(_PROJECT_ROOT, "mandarin", "web", "static")
_STYLE_CSS = os.path.join(_STATIC_DIR, "style.css")
_APP_JS = os.path.join(_STATIC_DIR, "app.js")
_MANDARIN_PKG = os.path.join(_PROJECT_ROOT, "mandarin")

_TEMPLATE_NAMES = [
    "index.html", "admin.html", "login.html", "register.html",
    "forgot_password.html", "reset_password.html",
    "mfa_setup.html", "mfa_verify.html", "404.html", "500.html",
]


def _read_file(path: str) -> str | None:
    """Read a file, returning None on any error."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, IOError):
        return None


def _read_templates() -> dict[str, str]:
    """Read all template files, returning {name: content}."""
    templates = {}
    for name in _TEMPLATE_NAMES:
        content = _read_file(os.path.join(_TEMPLATE_DIR, name))
        if content is not None:
            templates[name] = content
    return templates


# ── 1. Visual Design ──────────────────────────────────────────────────


def _analyze_visual_design(conn) -> list[dict]:
    """Inspect CSS for palette consistency, typography, responsiveness, dark mode."""
    findings = []
    css = _read_file(_STYLE_CSS)
    if css is None:
        findings.append(_finding(
            "visual_design", "critical",
            "style.css not found",
            "The main stylesheet mandarin/web/static/style.css could not be read. "
            "All visual design analysis is blocked.",
            "Ensure style.css exists and is readable.",
            "Read mandarin/web/static/style.css — verify the file exists.",
            "Cannot assess visual design without the stylesheet.",
            _f("style_css"),
        ))
        return findings

    # --- Hex colors ---
    hex_colors = set(
        c.lower() for c in re.findall(r"#(?:[0-9a-fA-F]{3}){1,2}\b", css)
    )
    # --- rgb/rgba ---
    rgb_colors = set(
        c.lower().replace(" ", "")
        for c in re.findall(r"rgba?\([^)]+\)", css)
    )
    total_colors = len(hex_colors) + len(rgb_colors)
    if total_colors > 20:
        findings.append(_finding(
            "visual_design", "medium",
            f"Inconsistent color palette ({total_colors} unique colors)",
            f"Found {len(hex_colors)} unique hex colors and {len(rgb_colors)} "
            f"unique rgb/rgba values in style.css. More than 20 distinct colors "
            f"signals an ad-hoc palette rather than a design-system approach.",
            "Consolidate colors into CSS custom properties (--color-primary, etc.) "
            "and reference them throughout. Aim for 8-12 semantic tokens.",
            (
                f"style.css has {total_colors} unique color values.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Extract all hex/rgb colors\n"
                "3. Group by visual similarity\n"
                "4. Replace with CSS custom properties defined in :root"
            ),
            "Visual inconsistency erodes perceived quality and slows design iteration.",
            _f("style_css"),
        ))

    # --- Font families ---
    font_families = set(
        f.strip().strip("\"'").lower()
        for f in re.findall(r"font-family\s*:\s*([^;}{]+)", css)
    )
    if len(font_families) > 3:
        findings.append(_finding(
            "visual_design", "medium",
            f"Too many font families ({len(font_families)})",
            f"Found {len(font_families)} distinct font-family declarations. "
            f"More than 3 families creates typographic inconsistency and "
            f"increases page weight.",
            "Standardize on 1-2 font families (body + headings) plus a monospace "
            "for code. Define as CSS custom properties.",
            (
                f"style.css declares {len(font_families)} font families.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Search for font-family declarations\n"
                "3. Consolidate to max 2-3 families\n"
                "4. Use CSS custom properties for font stacks"
            ),
            "Extra fonts slow loading and fracture visual identity.",
            _f("style_css"),
        ))

    # --- Media queries ---
    media_queries = re.findall(r"@media\s*\(", css)
    if len(media_queries) < 2:
        findings.append(_finding(
            "visual_design", "high",
            f"Limited responsive breakpoints ({len(media_queries)} @media queries)",
            f"Only {len(media_queries)} @media query/queries found. A responsive "
            f"web app for language learning needs at minimum mobile and tablet "
            f"breakpoints.",
            "Add responsive breakpoints at minimum for mobile (<768px) and "
            "tablet (768-1024px).",
            (
                f"style.css has only {len(media_queries)} @media queries.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Add mobile-first breakpoints:\n"
                "   - @media (max-width: 767px) for phone\n"
                "   - @media (min-width: 768px) and (max-width: 1023px) for tablet"
            ),
            "Non-responsive design alienates mobile-majority users.",
            _f("style_css"),
        ))

    # --- Dark mode ---
    has_dark = "prefers-color-scheme" in css
    if not has_dark:
        findings.append(_finding(
            "visual_design", "low",
            "No dark mode via prefers-color-scheme",
            "style.css does not contain a prefers-color-scheme media query. "
            "Dark mode reduces eye strain and is expected in modern apps.",
            "Add a @media (prefers-color-scheme: dark) block that remaps "
            "CSS custom properties to dark variants.",
            (
                "No prefers-color-scheme media query found.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Add @media (prefers-color-scheme: dark) { :root { ... } }"
            ),
            "Missing dark mode may deter evening/night learners.",
            _f("style_css"),
        ))

    # --- CSS custom properties ---
    custom_props = re.findall(r"--[\w-]+\s*:", css)
    if len(custom_props) < 5:
        findings.append(_finding(
            "visual_design", "medium",
            f"Low CSS custom property usage ({len(custom_props)} definitions)",
            f"Found only {len(custom_props)} CSS custom property definitions. "
            f"Custom properties enable theming, dark mode, and design consistency.",
            "Define a comprehensive set of design tokens as CSS custom properties "
            "in :root (colors, spacing, typography, radii).",
            (
                f"Only {len(custom_props)} CSS custom properties defined.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Add :root { --color-primary: ...; --spacing-md: ...; } etc.\n"
                "3. Replace hard-coded values with var(--token-name)"
            ),
            "Without design tokens, maintaining visual consistency is manual and error-prone.",
            _f("style_css"),
        ))

    return findings


# ── 2. Animation Quality ─────────────────────────────────────────────


def _analyze_animation_quality(conn) -> list[dict]:
    """Inspect CSS/JS for animation accessibility, quality, and performance."""
    findings = []
    css = _read_file(_STYLE_CSS)
    js = _read_file(_APP_JS)

    if css is None and js is None:
        return findings

    css = css or ""
    js = js or ""

    # --- prefers-reduced-motion ---
    has_reduced_motion = "prefers-reduced-motion" in css or "prefers-reduced-motion" in js
    if not has_reduced_motion:
        findings.append(_finding(
            "animation", "critical",
            "Missing prefers-reduced-motion support",
            "Neither style.css nor app.js contains a prefers-reduced-motion check. "
            "Users with vestibular disorders or motion sensitivity need animations "
            "disabled. This is a WCAG 2.1 Level AAA requirement (2.3.3) and "
            "a Level AA best practice.",
            "Add @media (prefers-reduced-motion: reduce) { *, *::before, *::after "
            "{ animation-duration: 0.01ms !important; transition-duration: 0.01ms "
            "!important; } } to style.css.",
            (
                "No prefers-reduced-motion support found.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Add at the end:\n"
                "   @media (prefers-reduced-motion: reduce) {\n"
                "     *, *::before, *::after {\n"
                "       animation-duration: 0.01ms !important;\n"
                "       transition-duration: 0.01ms !important;\n"
                "     }\n"
                "   }"
            ),
            "Accessibility failure — animations can trigger nausea/seizures for "
            "vestibular disorder sufferers.",
            _f("style_css", "app_js"),
        ))

    # --- Transitions and keyframes ---
    has_transitions = bool(re.search(r"\btransition\s*:", css))
    has_keyframes = bool(re.search(r"@keyframes\s+", css))
    if not has_transitions and not has_keyframes:
        findings.append(_finding(
            "animation", "low",
            "No CSS transitions or keyframe animations",
            "style.css contains no transition or @keyframes declarations. "
            "Subtle animations improve perceived performance and polish.",
            "Add micro-interactions: button hover transitions, page-enter "
            "animations, loading states.",
            (
                "No transitions or @keyframes found in style.css.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Add transition: all 0.2s ease-in-out to interactive elements\n"
                "3. Consider @keyframes for loading spinners and page transitions"
            ),
            "Static UI feels unresponsive — animations signal interactivity.",
            _f("style_css"),
        ))

    # --- Animation durations ---
    # Match transition durations and animation-duration values
    duration_pattern = r"(?:transition|animation)(?:-duration)?\s*:[^;]*?(\d+(?:\.\d+)?)(m?s)"
    durations_raw = re.findall(duration_pattern, css)
    long_durations = []
    short_durations = []
    for val, unit in durations_raw:
        ms = float(val) * 1000 if unit == "s" else float(val)
        if ms > 500:
            long_durations.append(ms)
        elif ms < 100 and ms > 0:
            short_durations.append(ms)

    if long_durations:
        findings.append(_finding(
            "animation", "low",
            f"Slow animations detected ({len(long_durations)} over 500ms)",
            f"Found {len(long_durations)} animation/transition duration(s) "
            f"exceeding 500ms. Long animations feel sluggish and block "
            f"interaction, especially in a drill-based learning app.",
            "Keep UI transitions under 300ms. Reserve longer durations (500ms+) "
            "only for dramatic page transitions or celebration effects.",
            (
                f"{len(long_durations)} animations exceed 500ms.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Search for transition and animation-duration\n"
                "3. Reduce UI interaction animations to 150-300ms"
            ),
            "Slow animations frustrate power users doing rapid drill sessions.",
            _f("style_css"),
        ))

    if short_durations:
        findings.append(_finding(
            "animation", "low",
            f"Imperceptible animations detected ({len(short_durations)} under 100ms)",
            f"Found {len(short_durations)} animation/transition duration(s) "
            f"under 100ms. Sub-100ms transitions are invisible to most users "
            f"and waste rendering cycles.",
            "Either remove sub-100ms transitions or increase to 150ms minimum "
            "where visual feedback is intended.",
            (
                f"{len(short_durations)} animations are under 100ms.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Remove or increase sub-100ms durations to at least 150ms"
            ),
            "Imperceptible animations add code complexity with no UX benefit.",
            _f("style_css"),
        ))

    # --- Easing functions ---
    has_cubic_bezier = "cubic-bezier" in css
    has_ease_in_out = "ease-in-out" in css or "ease-out" in css
    uses_only_linear = "linear" in css and not has_cubic_bezier and not has_ease_in_out
    if uses_only_linear and (has_transitions or has_keyframes):
        findings.append(_finding(
            "animation", "low",
            "Animations use only linear easing",
            "CSS animations use linear easing exclusively. Natural motion uses "
            "ease-in-out or cubic-bezier curves that mimic physical acceleration.",
            "Replace linear with ease-out for entrances and ease-in for exits. "
            "Use cubic-bezier for custom spring physics.",
            (
                "Only linear easing found in style.css.\n\n"
                "1. Read mandarin/web/static/style.css\n"
                "2. Replace 'linear' with 'ease-out' for entrance animations\n"
                "3. Consider cubic-bezier(0.4, 0, 0.2, 1) for Material-style motion"
            ),
            "Linear easing feels robotic — natural easing improves perceived quality.",
            _f("style_css"),
        ))

    return findings


# ── 3. Sound Design ───────────────────────────────────────────────────


def _analyze_sound_design(conn) -> list[dict]:
    """Check for audio files in web static and Audio API usage in JS."""
    findings = []

    # --- Audio files in web static ---
    audio_extensions = ("*.mp3", "*.wav", "*.ogg", "*.m4a", "*.webm")
    web_audio_files = []
    for ext in audio_extensions:
        web_audio_files.extend(
            glob.glob(os.path.join(_STATIC_DIR, "**", ext), recursive=True)
        )

    # --- Audio API in JS ---
    js = _read_file(_APP_JS)
    has_audio_api = False
    if js:
        has_audio_api = bool(
            re.search(r"\bAudio\s*\(", js)
            or re.search(r"\.play\s*\(", js)
            or re.search(r"\bAudioContext\b", js)
        )

    if not web_audio_files and not has_audio_api:
        # Check if flutter has sounds
        flutter_sounds_dir = os.path.join(
            _PROJECT_ROOT, "flutter_app", "assets", "sounds"
        )
        flutter_sounds = []
        for ext in audio_extensions:
            flutter_sounds.extend(
                glob.glob(os.path.join(flutter_sounds_dir, ext))
            )

        flutter_note = ""
        if flutter_sounds:
            flutter_note = (
                f" Note: {len(flutter_sounds)} sound file(s) exist in "
                f"flutter_app/assets/sounds/ but are not available to the "
                f"web client."
            )

        findings.append(_finding(
            "sound_design", "medium",
            "No audio feedback in web client",
            f"No audio files found in mandarin/web/static/ and no Web Audio "
            f"API usage detected in app.js. Sound feedback (correct/wrong "
            f"chimes, streak celebrations) dramatically improves learning "
            f"reinforcement.{flutter_note}",
            "Add lightweight sound effects (.mp3, <50KB each) for correct/wrong "
            "answers at minimum. Use the Web Audio API for low-latency playback. "
            "Always gate behind a user preference toggle.",
            (
                "No audio in web client.\n\n"
                "1. Copy or create sound effects in mandarin/web/static/sounds/\n"
                "2. In mandarin/web/static/app.js, add:\n"
                "   const sfx = { correct: new Audio('/static/sounds/correct.mp3') };\n"
                "3. Gate behind user preference: if (prefs.soundEnabled) sfx.correct.play();\n"
                "4. Add a sound toggle in settings UI"
            ),
            "Audio feedback activates multi-sensory learning pathways and "
            "increases retention.",
            _f("app_js") + ["mandarin/web/static/sounds/"],
        ))
    elif web_audio_files and not has_audio_api:
        findings.append(_finding(
            "sound_design", "low",
            "Audio files present but no playback code",
            f"Found {len(web_audio_files)} audio file(s) in static/ but "
            f"no Audio API calls in app.js. Files may be unused.",
            "Wire up audio playback in app.js using the Web Audio API.",
            (
                "Audio files exist but no playback code in app.js.\n\n"
                "1. Read mandarin/web/static/app.js\n"
                "2. Search for Audio or .play() calls\n"
                "3. Add playback for existing audio files"
            ),
            "Unused assets waste bandwidth without providing feedback value.",
            _f("app_js"),
        ))

    return findings


# ── 4. Copywriting ────────────────────────────────────────────────────


def _analyze_copywriting(conn) -> list[dict]:
    """Scan templates for placeholder text, generic buttons, and empty states."""
    findings = []
    templates = _read_templates()

    if not templates:
        findings.append(_finding(
            "copywriting", "high",
            "No templates readable",
            "Could not read any HTML templates from mandarin/web/templates/. "
            "Copywriting analysis is blocked.",
            "Ensure template files exist and are readable.",
            "Check that mandarin/web/templates/ contains .html files.",
            "Cannot assess copy quality without templates.",
            [f"mandarin/web/templates/{n}" for n in _TEMPLATE_NAMES],
        ))
        return findings

    # --- Placeholder/TODO text ---
    placeholder_pattern = re.compile(
        r"\b(lorem|ipsum|todo|placeholder|tbd|fixme|xxx)\b", re.IGNORECASE
    )
    placeholder_hits = {}
    for name, content in templates.items():
        matches = placeholder_pattern.findall(content)
        if matches:
            placeholder_hits[name] = matches

    if placeholder_hits:
        files_list = ", ".join(placeholder_hits.keys())
        total = sum(len(v) for v in placeholder_hits.values())
        findings.append(_finding(
            "copywriting", "high",
            f"Placeholder text found in {len(placeholder_hits)} template(s)",
            f"Found {total} placeholder/TODO marker(s) across templates: "
            f"{files_list}. Placeholder text in production signals unfinished "
            f"work and undermines trust.",
            "Replace all placeholder text with finalized copy. Use a copy "
            "review checklist before deployment.",
            (
                f"Placeholder text in: {files_list}\n\n"
                "1. Read each template file\n"
                "2. Search for lorem, TODO, placeholder, TBD, FIXME\n"
                "3. Replace with real copy"
            ),
            "Placeholder text in production destroys user confidence.",
            [f"mandarin/web/templates/{n}" for n in placeholder_hits],
        ))

    # --- Generic button labels ---
    generic_pattern = re.compile(
        r'>\s*(Submit|Click [Hh]ere|OK|Press [Hh]ere)\s*<', re.IGNORECASE
    )
    generic_hits = {}
    for name, content in templates.items():
        matches = generic_pattern.findall(content)
        if matches:
            generic_hits[name] = matches

    if generic_hits:
        files_list = ", ".join(generic_hits.keys())
        total = sum(len(v) for v in generic_hits.values())
        unique_labels = sorted(set(
            label for labels in generic_hits.values() for label in labels
        ))
        findings.append(_finding(
            "copywriting", "medium",
            f"Generic button labels ({total} instances)",
            f"Found generic button labels ({', '.join(unique_labels)}) in "
            f"templates: {files_list}. Imperative, action-specific CTAs "
            f"('Start practicing', 'Save progress') outperform generic labels "
            f"by 20-30% in click-through rate.",
            "Replace generic labels with action-specific imperative verbs: "
            "'Submit' -> 'Save changes', 'OK' -> 'Got it', 'Click here' -> "
            "'View details'.",
            (
                f"Generic buttons in: {files_list}\n\n"
                "1. Read each template\n"
                "2. Replace 'Submit' with context-specific CTAs\n"
                "3. Replace 'Click here' with descriptive link text\n"
                "4. Replace 'OK' with affirming micro-copy"
            ),
            "Generic CTAs reduce conversion and feel lazy to users.",
            [f"mandarin/web/templates/{n}" for n in generic_hits],
        ))

    # --- Empty state content ---
    # Look for common empty-state patterns: "no items", "nothing here", "empty"
    empty_pattern = re.compile(
        r'(?:no\s+(?:items|results|data|content)|nothing\s+(?:here|to\s+show)|'
        r'empty\s+(?:state|list))',
        re.IGNORECASE,
    )
    has_empty_states = any(
        empty_pattern.search(content) for content in templates.values()
    )
    if not has_empty_states:
        findings.append(_finding(
            "copywriting", "low",
            "No empty-state copy patterns detected",
            "Templates do not appear to contain dedicated empty-state messaging. "
            "Empty states (first visit, no data yet) are critical onboarding "
            "moments that need encouraging copy and clear next-step CTAs.",
            "Add dedicated empty-state UI for lists, dashboards, and drill "
            "history views with encouraging copy and action buttons.",
            (
                "No empty-state copy found in templates.\n\n"
                "1. Identify views that can be empty (dashboard, history, word lists)\n"
                "2. Add empty-state messaging with illustrations and CTAs\n"
                "3. Examples: 'No reviews yet — start your first session!'"
            ),
            "Poor empty states cause users to bounce during onboarding.",
            [f"mandarin/web/templates/{n}" for n in _TEMPLATE_NAMES[:4]],
        ))

    return findings


# ── 5. Branding ───────────────────────────────────────────────────────


def _analyze_branding(conn) -> list[dict]:
    """Check index.html and style.css for brand consistency markers."""
    findings = []
    index_html = _read_file(os.path.join(_TEMPLATE_DIR, "index.html"))
    css = _read_file(_STYLE_CSS)

    if index_html is None:
        findings.append(_finding(
            "branding", "high",
            "index.html not readable",
            "Cannot read mandarin/web/templates/index.html. Branding analysis "
            "requires the base template.",
            "Ensure index.html exists and is readable.",
            "Check mandarin/web/templates/index.html exists.",
            "Cannot assess branding without the main template.",
            ["mandarin/web/templates/index.html"],
        ))
        return findings

    # --- Logo in header/nav ---
    has_logo_in_nav = bool(
        re.search(r"<(?:header|nav)[^>]*>[\s\S]*?(?:logo|\.svg|\.png)", index_html, re.IGNORECASE)
    )
    if not has_logo_in_nav:
        # Also check for logo img/svg anywhere prominent
        has_logo_anywhere = bool(
            re.search(r'(?:logo[\w-]*\.(?:svg|png)|class="[^"]*logo)', index_html, re.IGNORECASE)
        )
        if not has_logo_anywhere:
            findings.append(_finding(
                "branding", "medium",
                "No logo detected in main template",
                "index.html does not appear to include a logo image in the "
                "header or navigation area. A visible logo is essential for "
                "brand recognition.",
                "Add the logo SVG to the header/nav. Use logo-horizontal.svg "
                "for desktop and logo-mark.svg for mobile.",
                (
                    "No logo in index.html header/nav.\n\n"
                    "1. Read mandarin/web/templates/index.html\n"
                    "2. Add <img src='/static/logo-horizontal.svg' alt='Mandarin' "
                    "class='logo'> in the header\n"
                    "3. Use logo-mark.svg for compact mobile view"
                ),
                "Missing logo weakens brand recognition and trust.",
                ["mandarin/web/templates/index.html"] + _f("style_css"),
            ))

    # --- Favicon ---
    has_favicon = bool(
        re.search(r'<link[^>]*rel=["\'](?:icon|shortcut icon)', index_html, re.IGNORECASE)
    )
    if not has_favicon:
        findings.append(_finding(
            "branding", "medium",
            "No favicon link tag",
            "index.html does not include a <link rel='icon'> tag. Missing "
            "favicons make the app look unprofessional in browser tabs and "
            "bookmarks.",
            "Add <link rel='icon' href='/static/favicon.ico'> to the <head>.",
            (
                "No favicon link in index.html.\n\n"
                "1. Read mandarin/web/templates/index.html\n"
                "2. Add in <head>: <link rel='icon' href='/static/favicon.ico'>"
            ),
            "Missing favicon looks unprofessional in browser tabs.",
            ["mandarin/web/templates/index.html"],
        ))

    # --- Open Graph meta tags ---
    og_tags = {
        "og:title": bool(re.search(r'property=["\']og:title', index_html)),
        "og:description": bool(re.search(r'property=["\']og:description', index_html)),
        "og:image": bool(re.search(r'property=["\']og:image', index_html)),
    }
    missing_og = [tag for tag, present in og_tags.items() if not present]
    if missing_og:
        findings.append(_finding(
            "branding", "medium",
            f"Missing Open Graph tags: {', '.join(missing_og)}",
            f"index.html is missing {len(missing_og)} Open Graph meta tag(s): "
            f"{', '.join(missing_og)}. OG tags control how the app appears "
            f"when shared on social media and messaging apps.",
            "Add all three OG tags in <head>. og:image should point to "
            "/static/og-image.png.",
            (
                f"Missing OG tags: {', '.join(missing_og)}\n\n"
                "1. Read mandarin/web/templates/index.html\n"
                "2. Add in <head>:\n"
                "   <meta property='og:title' content='Mandarin — Learn Chinese'>\n"
                "   <meta property='og:description' content='...'>\n"
                "   <meta property='og:image' content='/static/og-image.png'>"
            ),
            "Missing OG tags mean ugly/blank previews when shared on social media.",
            ["mandarin/web/templates/index.html"],
        ))

    # --- Heading hierarchy ---
    headings = re.findall(r"<(h[1-6])\b", index_html, re.IGNORECASE)
    heading_levels = sorted(set(int(h[1]) for h in headings)) if headings else []
    if heading_levels:
        # Check for gaps (e.g., h1 -> h3 with no h2)
        gaps = []
        for i in range(len(heading_levels) - 1):
            if heading_levels[i + 1] - heading_levels[i] > 1:
                gaps.append(f"h{heading_levels[i]} -> h{heading_levels[i + 1]}")
        if gaps:
            findings.append(_finding(
                "branding", "low",
                f"Heading hierarchy has gaps: {', '.join(gaps)}",
                f"index.html heading hierarchy skips levels: {', '.join(gaps)}. "
                f"Proper h1>h2>h3 hierarchy is important for SEO and "
                f"screen reader navigation.",
                "Ensure headings follow a logical hierarchy without skipping levels.",
                (
                    f"Heading gaps: {', '.join(gaps)}\n\n"
                    "1. Read mandarin/web/templates/index.html\n"
                    "2. Fix heading hierarchy to not skip levels"
                ),
                "Broken heading hierarchy hurts SEO and accessibility.",
                ["mandarin/web/templates/index.html"],
            ))
    elif not headings:
        findings.append(_finding(
            "branding", "low",
            "No heading tags in index.html",
            "index.html contains no h1-h6 heading tags. Headings structure "
            "content for both SEO and screen readers.",
            "Add at least an h1 for the page title.",
            (
                "No headings in index.html.\n\n"
                "1. Read mandarin/web/templates/index.html\n"
                "2. Add h1 for the main page title"
            ),
            "Missing headings hurt SEO rankings and accessibility.",
            ["mandarin/web/templates/index.html"],
        ))

    return findings


# ── 6. Mobile Performance ────────────────────────────────────────────


def _analyze_mobile_performance(conn) -> list[dict]:
    """Check templates and static files for mobile performance indicators."""
    findings = []
    index_html = _read_file(os.path.join(_TEMPLATE_DIR, "index.html"))
    css = _read_file(_STYLE_CSS)

    # --- Viewport meta ---
    if index_html:
        has_viewport = bool(
            re.search(r'<meta[^>]*name=["\']viewport', index_html, re.IGNORECASE)
        )
        if not has_viewport:
            findings.append(_finding(
                "mobile_perf", "critical",
                "Missing viewport meta tag",
                "index.html does not contain <meta name='viewport'>. Without "
                "it, mobile browsers render the page at desktop width and zoom "
                "out, making the app unusable on phones.",
                "Add <meta name='viewport' content='width=device-width, "
                "initial-scale=1'> to <head>.",
                (
                    "No viewport meta tag.\n\n"
                    "1. Read mandarin/web/templates/index.html\n"
                    "2. Add in <head>: <meta name='viewport' "
                    "content='width=device-width, initial-scale=1'>"
                ),
                "Without viewport meta, the app is unusable on mobile devices.",
                ["mandarin/web/templates/index.html"],
            ))

    # --- JS file size ---
    try:
        js_size = os.path.getsize(_APP_JS)
        js_kb = js_size / 1024
        if js_kb > 500:
            findings.append(_finding(
                "mobile_perf", "high",
                f"app.js is {js_kb:.0f}KB (exceeds 500KB threshold)",
                f"mandarin/web/static/app.js is {js_kb:.0f}KB. Large JavaScript "
                f"bundles block rendering and drain battery on mobile. Parse "
                f"time alone can exceed 2 seconds on mid-range phones.",
                "Consider code splitting, tree shaking, or lazy loading "
                "non-critical modules. Target <200KB for initial bundle.",
                (
                    f"app.js is {js_kb:.0f}KB.\n\n"
                    "1. Read mandarin/web/static/app.js\n"
                    "2. Identify code that can be lazy-loaded\n"
                    "3. Consider splitting into core.js + feature modules\n"
                    "4. Enable gzip/brotli compression on the server"
                ),
                "Large JS bundles cause slow load times on 3G/4G connections.",
                _f("app_js"),
            ))
    except OSError:
        pass

    # --- CSS !important abuse ---
    if css:
        important_count = len(re.findall(r"!important", css))
        if important_count > 10:
            findings.append(_finding(
                "mobile_perf", "medium",
                f"CSS specificity war ({important_count} !important declarations)",
                f"style.css contains {important_count} !important declarations. "
                f"Excessive !important indicates specificity conflicts that "
                f"make CSS harder to maintain and override responsively.",
                "Refactor CSS to use proper specificity (BEM, utility classes, "
                "or CSS layers) instead of !important overrides.",
                (
                    f"{important_count} !important declarations in style.css.\n\n"
                    "1. Read mandarin/web/static/style.css\n"
                    "2. Search for !important\n"
                    "3. Fix specificity by restructuring selectors\n"
                    "4. Target <5 !important declarations total"
                ),
                "Specificity wars bloat CSS and cause mobile layout regressions.",
                _f("style_css"),
            ))

    # --- Lazy loading on images ---
    templates = _read_templates()
    all_template_content = "\n".join(templates.values())
    img_tags = re.findall(r"<img\b[^>]*>", all_template_content, re.IGNORECASE)
    if img_tags:
        lazy_count = sum(1 for tag in img_tags if 'loading="lazy"' in tag or "loading='lazy'" in tag)
        non_lazy = len(img_tags) - lazy_count
        if non_lazy > 2:
            findings.append(_finding(
                "mobile_perf", "low",
                f"{non_lazy} images without lazy loading",
                f"Found {len(img_tags)} <img> tags across templates but only "
                f"{lazy_count} use loading='lazy'. Below-the-fold images should "
                f"defer loading to improve initial page render.",
                "Add loading='lazy' to all non-critical images (keep hero/logo "
                "images eager).",
                (
                    f"{non_lazy} images lack lazy loading.\n\n"
                    "1. Read templates in mandarin/web/templates/\n"
                    "2. Add loading='lazy' to below-the-fold <img> tags"
                ),
                "Non-lazy images slow initial render on bandwidth-constrained "
                "mobile connections.",
                [f"mandarin/web/templates/{n}" for n in templates],
            ))

    # --- Service worker reference ---
    if index_html:
        has_sw = bool(
            re.search(r"(?:serviceWorker|sw\.js)", index_html)
            or re.search(r"(?:serviceWorker|sw\.js)", _read_file(_APP_JS) or "")
        )
        if not has_sw:
            findings.append(_finding(
                "mobile_perf", "low",
                "No service worker registration detected",
                "Neither index.html nor app.js references a service worker. "
                "Service workers enable offline support and faster repeat loads "
                "through caching.",
                "Register the existing sw.js in index.html or app.js.",
                (
                    "No service worker registration found.\n\n"
                    "1. Read mandarin/web/static/sw.js — it exists but may not be registered\n"
                    "2. Add registration in app.js or index.html:\n"
                    "   if ('serviceWorker' in navigator) {\n"
                    "     navigator.serviceWorker.register('/static/sw.js');\n"
                    "   }"
                ),
                "Without a service worker, the app has no offline support "
                "and slower repeat visits.",
                _f("app_js") + ["mandarin/web/static/sw.js"],
            ))

    return findings


# ── 7. Behavioral Economics ──────────────────────────────────────────


def _analyze_behavioral_economics(conn) -> list[dict]:
    """Check templates and JS for nudge/behavioral design patterns."""
    findings = []
    templates = _read_templates()
    js = _read_file(_APP_JS) or ""
    all_template_content = "\n".join(templates.values())
    all_content = all_template_content + "\n" + js

    if not templates:
        return findings

    # --- Loss aversion ---
    loss_patterns = re.findall(
        r"\b(?:lose|don'?t\s+lose|streak|losing)\b", all_content, re.IGNORECASE
    )
    if not loss_patterns:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No loss-aversion language detected",
            "Templates and JS contain no loss-aversion triggers (streak loss "
            "warnings, 'don't lose your progress'). Loss aversion is the "
            "strongest behavioral nudge for retention — people work 2x harder "
            "to avoid losing than to gain.",
            "Add streak-loss warnings ('Your 5-day streak is at risk!'), "
            "progress-loss reminders before leaving, and re-engagement copy "
            "emphasizing what they'll lose.",
            (
                "No loss-aversion language found.\n\n"
                "1. Read mandarin/web/static/app.js and templates\n"
                "2. Add streak-at-risk notifications\n"
                "3. Add exit-intent warnings for mid-session abandonment\n"
                "4. Use loss framing in re-engagement emails"
            ),
            "Missing loss-aversion cues reduce daily return rate.",
            _f("app_js") + [f"mandarin/web/templates/{n}" for n in _TEMPLATE_NAMES[:2]],
        ))

    # --- Social proof ---
    social_proof_patterns = re.findall(
        r"\b(?:learners?|students?|users?)\s+(?:have|are|already|joined|learning)\b",
        all_content, re.IGNORECASE,
    )
    social_proof_counts = re.findall(
        r"\b\d+[,.]?\d*\s*(?:learners?|students?|users?)\b",
        all_content, re.IGNORECASE,
    )
    if not social_proof_patterns and not social_proof_counts:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No social proof patterns detected",
            "No social proof language found (e.g., '1,000 learners', "
            "'students are already...'). Social proof reduces uncertainty "
            "and increases conversion during onboarding.",
            "Add user count displays, testimonials, or 'X learners studied "
            "this today' nudges on the landing page and drill screens.",
            (
                "No social proof found.\n\n"
                "1. Read mandarin/web/templates/index.html\n"
                "2. Add social proof to landing/onboarding:\n"
                "   - User count badges\n"
                "   - 'Join X learners' CTAs\n"
                "   - Community activity indicators"
            ),
            "Lack of social proof increases signup friction.",
            ["mandarin/web/templates/index.html"] + _f("landing_routes"),
        ))

    # --- Progress visualization ---
    progress_patterns = re.findall(
        r"\b(?:progress|level|mastery|badge|achievement|rank)\b",
        all_content, re.IGNORECASE,
    )
    has_progress_bar = bool(re.search(
        r"(?:progress[_-]?bar|progressbar|role=[\"']progressbar)", all_content, re.IGNORECASE
    ))
    if not progress_patterns and not has_progress_bar:
        findings.append(_finding(
            "behavioral_econ", "medium",
            "No progress visualization detected",
            "No progress-related UI elements (progress bars, levels, mastery "
            "indicators) found in templates or JS. Progress visualization is "
            "the #1 gamification element for learning app retention.",
            "Add visible progress tracking: XP bar, level indicator, mastery "
            "percentages per HSK level, and session completion progress.",
            (
                "No progress visualization found.\n\n"
                "1. Read mandarin/web/templates/index.html and app.js\n"
                "2. Add progress bar component for session progress\n"
                "3. Add mastery indicator for vocabulary items\n"
                "4. Add level/XP display in the header"
            ),
            "Without visible progress, learners cannot see improvement and churn.",
            _f("app_js") + ["mandarin/web/templates/index.html"],
        ))

    # --- Commitment devices ---
    commitment_patterns = re.findall(
        r"\b(?:goal|target|daily\s+(?:goal|target)|commit|pledge|reminder)\b",
        all_content, re.IGNORECASE,
    )
    if not commitment_patterns:
        findings.append(_finding(
            "behavioral_econ", "low",
            "No commitment device patterns detected",
            "No goal-setting or commitment language found. Commitment devices "
            "(daily goals, study pledges, reminder opt-ins) leverage consistency "
            "bias to increase daily active usage.",
            "Add daily goal setting during onboarding, study reminders, and "
            "'set your target' prompts in settings.",
            (
                "No commitment devices found.\n\n"
                "1. Read mandarin/web/templates/ and route files\n"
                "2. Add daily goal selector in onboarding flow\n"
                "3. Add study reminder scheduling\n"
                "4. Add 'Set your daily target' prompt in settings"
            ),
            "Without commitment devices, users have no self-imposed accountability.",
            _f("onboarding_routes", "settings_routes")
            + ["mandarin/web/templates/index.html"],
        ))

    return findings


# ── 8. Consulting Strategy ───────────────────────────────────────────


def _analyze_consulting_strategy(conn) -> list[dict]:
    """Check landing and payment routes for strategic product patterns."""
    findings = []

    # --- Landing page value prop ---
    landing_routes = _read_file(
        os.path.join(_MANDARIN_PKG, "web", "landing_routes.py")
    )
    if landing_routes:
        has_value_prop_route = bool(
            re.search(r"def\s+\w*(?:landing|home|index)\w*\s*\(", landing_routes)
            or re.search(r'@\w+\.route\s*\(\s*["\']/', landing_routes)
        )
        if not has_value_prop_route:
            findings.append(_finding(
                "strategic", "medium",
                "No clear landing page route",
                "landing_routes.py does not appear to define a root/home "
                "route. A clear landing page with value proposition is "
                "essential for conversion.",
                "Ensure landing_routes.py has a route serving the main "
                "landing page with clear value proposition.",
                (
                    "No landing/home route in landing_routes.py.\n\n"
                    "1. Read mandarin/web/landing_routes.py\n"
                    "2. Ensure a route for '/' or '/landing' exists\n"
                    "3. Template should communicate value prop above the fold"
                ),
                "Without a clear landing page, visitor-to-signup conversion suffers.",
                _f("landing_routes"),
            ))
    else:
        findings.append(_finding(
            "strategic", "high",
            "landing_routes.py not found",
            "Cannot read mandarin/web/landing_routes.py. Without a landing "
            "page route, there is no entry point for organic/paid traffic.",
            "Create landing_routes.py with a compelling landing page route.",
            (
                "landing_routes.py missing.\n\n"
                "1. Create mandarin/web/landing_routes.py\n"
                "2. Define a '/' route with landing page template\n"
                "3. Include value prop, social proof, and CTA"
            ),
            "No landing page means no top-of-funnel conversion.",
            _f("landing_routes"),
        ))

    # --- Payment/pricing ---
    payment_routes = _read_file(
        os.path.join(_MANDARIN_PKG, "web", "payment_routes.py")
    )
    if payment_routes:
        has_pricing_tiers = bool(
            re.search(r"(?:tier|plan|price|pricing|subscription)", payment_routes, re.IGNORECASE)
        )
        has_trial = bool(
            re.search(r"(?:trial|free_trial|freemium)", payment_routes, re.IGNORECASE)
        )
        if not has_pricing_tiers:
            findings.append(_finding(
                "strategic", "medium",
                "No pricing tier logic in payment routes",
                "payment_routes.py does not reference pricing tiers, plans, "
                "or subscriptions. Multi-tier pricing is essential for "
                "monetization and user segmentation.",
                "Define at least free/pro/premium tiers with clear feature "
                "differentiation.",
                (
                    "No pricing tiers in payment_routes.py.\n\n"
                    "1. Read mandarin/web/payment_routes.py\n"
                    "2. Add pricing tier definitions\n"
                    "3. Add /pricing route showing tier comparison"
                ),
                "Without pricing tiers, monetization is undefined.",
                _f("payment_routes"),
            ))
        if not has_trial:
            findings.append(_finding(
                "strategic", "low",
                "No free trial logic detected",
                "payment_routes.py does not reference trials or freemium. "
                "Free trials reduce signup friction and let users experience "
                "value before committing.",
                "Add a trial period (7-14 days) or freemium tier with "
                "daily session limits.",
                (
                    "No trial/freemium logic.\n\n"
                    "1. Read mandarin/web/payment_routes.py\n"
                    "2. Add trial_start, trial_end logic\n"
                    "3. Add trial expiration handling and upgrade prompts"
                ),
                "No trial means higher signup friction.",
                _f("payment_routes"),
            ))

    # --- Referral / invite / share ---
    all_routes = ""
    for route_key in ("routes", "session_routes", "dashboard_routes",
                      "landing_routes", "settings_routes"):
        path = os.path.join(_MANDARIN_PKG, "web", _FILE_MAP.get(route_key, "").split("/")[-1])
        content = _read_file(path)
        if content:
            all_routes += content + "\n"

    has_referral = bool(
        re.search(r"\b(?:referral|invite|share|affiliate)\b", all_routes, re.IGNORECASE)
    )
    if not has_referral:
        findings.append(_finding(
            "strategic", "low",
            "No referral/share functionality",
            "No route handlers reference referral, invite, or share "
            "mechanics. Word-of-mouth is the cheapest acquisition channel "
            "for language learning apps.",
            "Add a share/invite feature with referral tracking. Consider "
            "incentives (extra drills, premium days) for successful referrals.",
            (
                "No referral/share routes found.\n\n"
                "1. Read mandarin/web/routes.py and settings_routes.py\n"
                "2. Add /invite or /share route\n"
                "3. Add referral code tracking\n"
                "4. Add incentive for referrer and referee"
            ),
            "Missing referral mechanics leaves organic growth on the table.",
            _f("routes", "settings_routes"),
        ))

    # --- Activation metric tracking ---
    js = _read_file(_APP_JS) or ""
    has_activation_tracking = bool(
        re.search(r"(?:activation|onboard|first_session|gtag|analytics|GA4|dataLayer)",
                  js, re.IGNORECASE)
        or re.search(r"(?:activation|first_session|milestone)",
                     all_routes, re.IGNORECASE)
    )
    if not has_activation_tracking:
        findings.append(_finding(
            "strategic", "medium",
            "No activation metric tracking",
            "No activation milestone tracking found in JS or routes. "
            "Without measuring the 'aha moment' (first drill completed, "
            "first word learned), you cannot optimize the critical path.",
            "Define and instrument activation metrics: first drill completed, "
            "first 5 words learned, first return visit.",
            (
                "No activation tracking found.\n\n"
                "1. Read mandarin/web/static/app.js\n"
                "2. Add event tracking for activation milestones:\n"
                "   - gtag('event', 'activation_first_drill', ...)\n"
                "   - gtag('event', 'activation_5_words', ...)\n"
                "3. Add server-side activation flag in user model"
            ),
            "Cannot optimize onboarding without measuring activation.",
            _f("app_js", "routes"),
        ))

    return findings


# ── 9. QA Reliability ────────────────────────────────────────────────


def _analyze_qa_reliability(conn) -> list[dict]:
    """Scan Python files for reliability anti-patterns and best practices."""
    findings = []

    # Collect all .py files under mandarin/
    py_files = glob.glob(
        os.path.join(_MANDARIN_PKG, "**", "*.py"), recursive=True
    )
    if not py_files:
        return findings

    bare_except_files = []
    retry_files = []
    validation_files = []
    total_bare_excepts = 0

    for path in py_files:
        content = _read_file(path)
        if content is None:
            continue
        rel_path = os.path.relpath(path, _PROJECT_ROOT)

        # --- Bare except ---
        bare_matches = re.findall(r"^\s*except\s*:", content, re.MULTILINE)
        if bare_matches:
            bare_except_files.append(rel_path)
            total_bare_excepts += len(bare_matches)

        # --- Retry/backoff ---
        if re.search(r"\b(?:retry|backoff|tenacity|retrying)\b", content, re.IGNORECASE):
            retry_files.append(rel_path)

        # --- Input validation ---
        if re.search(r"\b(?:validate|schema|marshmallow|pydantic|wtforms|cerberus)\b",
                     content, re.IGNORECASE):
            validation_files.append(rel_path)

    # --- Bare excepts ---
    if total_bare_excepts > 0:
        severity = "high" if total_bare_excepts > 5 else "medium"
        sample = bare_except_files[:5]
        findings.append(_finding(
            "engineering", severity,
            f"Bare except clauses ({total_bare_excepts} across {len(bare_except_files)} files)",
            f"Found {total_bare_excepts} bare 'except:' clause(s) across "
            f"{len(bare_except_files)} file(s). Bare excepts silently swallow "
            f"all exceptions including KeyboardInterrupt and SystemExit, "
            f"masking bugs. Files: {', '.join(sample)}"
            f"{'...' if len(bare_except_files) > 5 else ''}",
            "Replace bare 'except:' with specific exception types "
            "(except ValueError, except OSError, etc.) or at minimum "
            "'except Exception:'.",
            (
                f"{total_bare_excepts} bare except clauses found.\n\n"
                f"Files to fix: {', '.join(sample)}\n\n"
                "1. Search for 'except:' (with no exception type)\n"
                "2. Replace with specific exception types\n"
                "3. At minimum use 'except Exception:' to preserve SystemExit"
            ),
            "Bare excepts mask bugs and make debugging extremely difficult.",
            sample,
        ))

    # --- Retry/backoff patterns ---
    if not retry_files:
        findings.append(_finding(
            "engineering", "low",
            "No retry/backoff patterns detected",
            "No Python files reference retry, backoff, or tenacity. Network "
            "calls, database operations, and external API calls should have "
            "retry logic with exponential backoff for transient failures.",
            "Add retry logic with exponential backoff for external API calls "
            "(Ollama, payment, email). Consider the tenacity library.",
            (
                "No retry/backoff found in any Python file.\n\n"
                "1. pip install tenacity\n"
                "2. Add @retry(stop=stop_after_attempt(3), "
                "wait=wait_exponential()) to external calls\n"
                "3. Priority: AI model calls, payment webhooks, email sending"
            ),
            "Without retries, transient network errors cause user-visible failures.",
            _f("routes", "scheduler"),
        ))

    # --- Input validation ---
    # Check route files specifically
    route_files = [
        p for p in py_files
        if "routes" in os.path.basename(p) or "route" in os.path.basename(p)
    ]
    route_validation = [
        os.path.relpath(p, _PROJECT_ROOT) for p in route_files
        if _read_file(p) and re.search(
            r"\b(?:validate|schema|wtforms|pydantic|marshmallow)\b",
            _read_file(p) or "", re.IGNORECASE,
        )
    ]
    if route_files and not route_validation:
        findings.append(_finding(
            "engineering", "medium",
            "No input validation in route handlers",
            f"Scanned {len(route_files)} route file(s) and found no "
            f"schema validation library usage (pydantic, marshmallow, "
            f"wtforms, cerberus). Route handlers accepting user input "
            f"without validation are vulnerable to malformed data.",
            "Add input validation using a schema library for all POST/PUT "
            "route handlers.",
            (
                f"No validation found in {len(route_files)} route files.\n\n"
                "1. Choose a validation library (pydantic, marshmallow, or wtforms)\n"
                "2. Add input schemas for all form/API endpoints\n"
                "3. Validate request.form / request.json before processing"
            ),
            "Missing input validation can cause crashes and security issues.",
            [os.path.relpath(p, _PROJECT_ROOT) for p in route_files[:5]],
        ))

    return findings


# ── 10. Operations Research ──────────────────────────────────────────


def _analyze_ops_research(conn) -> list[dict]:
    """Check code for caching, pooling, scheduling, and optimization patterns."""
    findings = []

    # Collect all .py files
    py_files = glob.glob(
        os.path.join(_MANDARIN_PKG, "**", "*.py"), recursive=True
    )
    if not py_files:
        return findings

    all_py_content = ""
    for path in py_files:
        content = _read_file(path)
        if content:
            all_py_content += content + "\n"

    # --- Caching ---
    has_cache = bool(re.search(
        r"\b(?:cache|lru_cache|functools\.cache|redis|memcache|cachetools)\b",
        all_py_content, re.IGNORECASE,
    ))
    if not has_cache:
        findings.append(_finding(
            "engineering", "medium",
            "No caching layer detected",
            "No caching patterns found across Python codebase (lru_cache, "
            "redis, memcached, cachetools). Repeated database queries and "
            "computation without caching wastes resources and increases "
            "response latency.",
            "Add functools.lru_cache for pure computation, and consider "
            "redis/memcached for shared state caching.",
            (
                "No caching found.\n\n"
                "1. Add @lru_cache to expensive pure functions\n"
                "2. Cache frequent DB queries (user settings, vocabulary stats)\n"
                "3. For multi-process: consider redis for shared cache"
            ),
            "Missing caching increases latency and database load.",
            _f("routes", "scheduler"),
        ))

    # --- Connection pooling ---
    has_pooling = bool(re.search(
        r"\b(?:pool|Pool|connection_pool|pool_size|QueuePool|StaticPool|"
        r"create_engine|ConnectionPool)\b",
        all_py_content,
    ))
    if not has_pooling:
        findings.append(_finding(
            "engineering", "low",
            "No connection pooling detected",
            "No connection pooling patterns found. Without pooling, each "
            "request opens a new database connection, which is expensive "
            "and does not scale.",
            "Use SQLAlchemy with pool_size or sqlite3 with a connection pool "
            "wrapper for concurrent access.",
            (
                "No connection pooling found.\n\n"
                "1. Read mandarin/db/core.py\n"
                "2. Add connection pooling for SQLite:\n"
                "   - Use check_same_thread=False with a threading lock, or\n"
                "   - Switch to SQLAlchemy with StaticPool for SQLite"
            ),
            "Without pooling, connection overhead dominates under concurrent load.",
            ["mandarin/db/core.py"] + _f("routes"),
        ))

    # --- Scheduler / queue optimization ---
    scheduler_path = os.path.join(_MANDARIN_PKG, "web", "quality_scheduler.py")
    scheduler_alt = os.path.join(_MANDARIN_PKG, "scheduler.py")
    scheduler_content = _read_file(scheduler_path) or _read_file(scheduler_alt) or ""

    if scheduler_content:
        has_queue_opt = bool(re.search(
            r"\b(?:priority|queue|heapq|PriorityQueue|celery|rq|dramatiq|"
            r"batch|bulk|chunk)\b",
            scheduler_content, re.IGNORECASE,
        ))
        if not has_queue_opt:
            findings.append(_finding(
                "engineering", "low",
                "Scheduler lacks queue optimization patterns",
                "The scheduler does not use priority queues, batching, or "
                "a task queue library. As the user base grows, sequential "
                "task processing will become a bottleneck.",
                "Add priority-based scheduling (heapq or PriorityQueue) and "
                "batch processing for bulk operations.",
                (
                    "No queue optimization in scheduler.\n\n"
                    "1. Read mandarin/web/quality_scheduler.py or mandarin/scheduler.py\n"
                    "2. Add priority queue for task scheduling\n"
                    "3. Batch database writes for bulk operations\n"
                    "4. Consider celery/rq for background job processing"
                ),
                "Sequential scheduling will not scale with user growth.",
                ["mandarin/web/quality_scheduler.py", "mandarin/scheduler.py"],
            ))

    # --- Background job processing ---
    has_bg_jobs = bool(re.search(
        r"\b(?:celery|rq|dramatiq|huey|arq|threading\.Thread|"
        r"concurrent\.futures|ProcessPoolExecutor|ThreadPoolExecutor|"
        r"asyncio\.create_task|BackgroundScheduler|APScheduler)\b",
        all_py_content,
    ))
    if not has_bg_jobs:
        findings.append(_finding(
            "engineering", "medium",
            "No background job processing detected",
            "No background job processing framework found (celery, rq, "
            "dramatiq, APScheduler, ThreadPoolExecutor). Long-running "
            "operations (AI generation, email, analytics) should run "
            "asynchronously to avoid blocking request handlers.",
            "Add background processing for AI drill generation, email "
            "sending, and analytics computation.",
            (
                "No background job processing found.\n\n"
                "1. Choose: APScheduler (simple), rq (medium), celery (production)\n"
                "2. Move long operations to background tasks:\n"
                "   - AI drill generation\n"
                "   - Email sending\n"
                "   - Analytics aggregation\n"
                "3. Add job status tracking for user-facing operations"
            ),
            "Without background jobs, slow operations block HTTP responses.",
            _f("routes", "scheduler"),
        ))

    return findings


# ── Analyzer registry ────────────────────────────────────────────────

ANALYZERS = [
    _analyze_visual_design,
    _analyze_animation_quality,
    _analyze_sound_design,
    _analyze_copywriting,
    _analyze_branding,
    _analyze_mobile_performance,
    _analyze_behavioral_economics,
    _analyze_consulting_strategy,
    _analyze_qa_reliability,
    _analyze_ops_research,
]
