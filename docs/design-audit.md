# Aelu Design Audit

Reference for AI agents working on the aelu Mandarin learning platform. Catalogs every visual pattern so you do not need to read 10,000+ lines of CSS.

---

## 1. Design Philosophy

Aelu follows a "Civic Sanctuary" aesthetic: warm Mediterranean civic architecture rendered in digital form -- plaster walls, bougainvillea rose, cypress olive, coastal indigo at dusk. The surface is continuous (no card borders, no decoration without function). Motion decelerates into rest; things arrive rather than pop. Typography carries information hierarchy instead of widgets or badges. The voice is a calm adult: data-grounded, no praise inflation, no gamification.

---

## 2. Global Tokens

Source of truth: `mandarin/web/static/design-tokens.json`. CSS variables are declared in `:root` in `style.css`. Flutter equivalents live in `flutter_app/lib/theme/aelu_colors.dart`, `aelu_spacing.dart`, and `aelu_theme.dart`.

### 2.1 Color

| Token | Light | Dark | Purpose |
|---|---|---|---|
| `base` / `surface` | `#F2EBE0` | `#1C2028` | Warm linen / deep indigo ground |
| `surface-alt` | `#EAE2D6` | `#242A34` | Slightly darker surface for layering |
| `text` | `#2A3650` | `#E4DDD0` | Primary body text |
| `text-dim` | `#5A6678` | `#A09888` | Secondary labels |
| `text-faint` | `#6A7080` (5.0:1) | `#A8A090` (5.2:1) | Tertiary / metadata (WCAG AA large) |
| `text-faintest` | `#707A8A` (4.5:1) | `#A0A8B8` (4.6:1) | Quaternary (WCAG AA small) |
| `accent` | `#946070` | `#B07888` | Bougainvillea rose -- primary action color |
| `accent-dim` | `#7A5060` | `#946070` | Darker accent for borders |
| `on-accent` | `#FFFFFF` | `#FFFFFF` | Text on accent backgrounds (4.89:1 AA large) |
| `secondary` | `#6A7A5A` | `#8AAA7A` | Cypress olive -- secondary actions |
| `correct` | `#5A7A5A` | `#7A9A7A` | Sage green -- earned, not celebrated |
| `incorrect` | `#806058` | `#A8988E` | Warm brown -- not red, not alarm |
| `divider` | `#D8D0C4` | `#3A3530` | Horizon lines |
| `border` | `transparent` | `transparent` | No visible borders by default |
| `shadow` | `rgba(42,54,80,0.04)` | `rgba(0,0,0,0.12)` | Base shadow tint |
| `flash-error-bg` | `#F0E0DD` | `#3A2828` | Error flash message background |
| `flash-info-bg` | `#DDE8DD` | `#283A28` | Info flash message background |
| `mastery-durable` | `#4A6A4A` | `#5A8A5A` | SRS mastery stage |
| `mastery-stable` | `#6A8A5A` | `#7AAA6A` | SRS mastery stage |
| `mastery-stabilizing` | `#B8A050` | `#D4B060` | SRS mastery stage |
| `sky-top` | `#E4E0D6` | `#222838` | Top of background sky gradient |
| `sky-bottom` | `#F2EBE0` | `#1C2028` | Bottom of background sky gradient |
| `overlay` | `rgba(0,0,0,0.45)` | same | Modal overlays |

### 2.2 Typography

| Token | Value |
|---|---|
| `font-heading` | `'Cormorant Garamond', 'Noto Serif SC', Georgia, serif` |
| `font-body` | `'Source Serif 4', 'Noto Serif SC', Georgia, serif` |
| `font-hanzi` | `'Noto Serif SC', 'Noto Sans SC', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', serif` |
| `font-mono` | `'SF Mono', 'Menlo', 'Consolas', monospace` |

**Type scale** (minor third, 1.2 ratio, fluid via `clamp()`):

| Step | Value |
|---|---|
| `xs` | `0.694rem` |
| `sm` | `0.833rem` |
| `base` | `1rem` |
| `lg` | `1.2rem` |
| `xl` | `clamp(1.2rem, 2vw, 1.44rem)` |
| `2xl` | `clamp(1.4rem, 2.8vw, 1.728rem)` |
| `3xl` | `clamp(1.6rem, 3.5vw, 2.074rem)` |
| `display` | `clamp(2.2rem, 5vw, 3.2rem)` |

**Line heights:** display 1.1, 3xl 1.2, xl/lg 1.3, base 1.6, sm 1.5, xs 1.4, tight 1.2, relaxed 1.8.

**Letter spacing:** tight `0.01em`, normal `0.03em`, wide `0.15em`.

### 2.3 Spacing

8-step scale based on 4px unit:

| Token | Value |
|---|---|
| `space-1` | `0.25rem` (4px) |
| `space-2` | `0.5rem` (8px) |
| `space-3` | `0.75rem` (12px) |
| `space-4` | `1rem` (16px) |
| `space-5` | `1.5rem` (24px) |
| `space-6` | `2rem` (32px) |
| `space-7` | `3rem` (48px) |
| `space-8` | `4rem` (64px) |

**Component spacing:** `--card-padding: space-3 space-4`, `--panel-padding: space-3 space-4`, `--btn-padding: 14px 32px`.

### 2.4 Shape (Radii)

| Token | Value | Usage |
|---|---|---|
| `radius` | `0` | Default -- structural elements have sharp corners |
| `radius-sm` | `2px` | Banners, tags |
| `radius-lg` | `6px` | Buttons |
| `radius-card` | `8px` | Cards, panels, metric cards |
| `radius-illustration` | `12px` | Illustration containers |
| `admin-radius` | `8px` | Admin-specific panels |

Flutter uses `12px` on interactive elements, `8px` on chips, `16px` on dialogs.

### 2.5 Shadow (6-level depth system)

| Level | Light | Dark |
|---|---|---|
| `xs` | `0 1px 1px rgba(42,54,80,0.04)` | `0 1px 1px rgba(0,0,0,0.2)` |
| `sm` | `0 1px 3px ..., 0 1px 2px ...` | `0 1px 3px ..., 0 1px 2px ...` |
| `md` | `0 2px 6px ..., 0 1px 3px ...` | `0 2px 6px ..., 0 1px 3px ...` |
| `lg` | `0 8px 24px rgba(0,0,0,0.08), 0 2px 8px ...` | `0 8px 24px rgba(0,0,0,0.2), ...` |
| `xl` | `0 16px 48px rgba(0,0,0,0.10), 0 4px 12px ...` | `... rgba(0,0,0,0.25), ...` |
| `2xl` | `0 24px 64px rgba(0,0,0,0.14), 0 8px 24px ...` | `... rgba(0,0,0,0.3), ...` |

Light shadows are tinted with the slate-blue text color. Dark shadows use pure black with higher opacity.

### 2.6 Glass

| Token | Value |
|---|---|
| `glass-blur` | `blur(20px) saturate(1.2)` |
| `glass-bg` (light) | `surface @ 78% opacity` |
| `glass-bg-dense` (light) | `surface @ 88% opacity` |
| `glass-bg` (dark) | `surface-alt @ 72% opacity` |
| `glass-bg-dense` (dark) | `surface-alt @ 85% opacity` |
| `glass-border` | `divider @ 40% (light) / 30% (dark) opacity` |

Implemented via `color-mix(in srgb, ...)` in CSS, `withValues(alpha:)` in Flutter.

### 2.7 Motion

**Durations:**

| Token | Value | Usage |
|---|---|---|
| `press` | `0.08s` | Button press feedback (near-instant) |
| `snappy` | `0.12s` | Feedback bar snap |
| `fast` | `0.18s` | Hover/color transitions |
| `base` | `0.3s` | Default transitions |
| `slow` | `0.4s` | Entrance/exit |
| `ambient` | `0.8s` | Shimmer, ambient loops |
| `float` | `1.5s` | Illustration hover drift |

**Easing curves:**

| Token | Value | Usage |
|---|---|---|
| `default` | `cubic-bezier(0.25, 0.1, 0.25, 1)` | General transitions |
| `upward` | `cubic-bezier(0.16, 1, 0.3, 1)` | Entry animations (decelerate into rest) |
| `exit` | `cubic-bezier(0.4, 0, 1, 1)` | Elements leaving (accelerate out) |
| `spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Physical gestures (button bounce-back) |

### 2.8 Gradient Mesh (Background)

The body background is a composite of five layers:
1. Radial gradient at 20%/0% tinted with accent at 6%
2. Radial gradient at 80%/10% tinted with secondary at 4%
3. Radial gradient at 50%/60% tinted with accent at 6%
4. Linear sky gradient (sky-top to sky-bottom over 280px)
5. SVG fractal noise at 6% opacity blended via `soft-light` (plaster texture)

Dark mode reduces the accent/secondary wash to 4%/3%.

---

## 3. Animation Systems

### 3.1 WebGL Atmosphere (`webgl/ink-atmosphere.js`)

Full-screen WebGL gradient mesh with animated control points and simplex noise grain. Attached via `<div id="webgl-atmosphere" data-scene="...">`.

**Scene configs:**

| Scene | Intensity | FPS | Where used |
|---|---|---|---|
| `marketing` | 0.32 | 30 | Landing/marketing pages (highest fidelity) |
| `login` | 0.22 | 30 | Auth pages |
| `dashboard` | 0.18 | 24 | Main dashboard (ambient, lightest) |
| `admin` | 0.12 | 20 | Admin panel (cool-toned, most restrained) |

Falls back to CSS gradient mesh if WebGL unavailable or `prefers-reduced-motion` is active. Pauses render loop when tab is hidden or canvas is off-screen. Mouse position gently biases one gradient control point.

### 3.2 Celebrations (`webgl/celebrations.js`)

2D canvas overlay effects (not WebGL -- lightweight). Two types:

| Effect | Trigger | Duration | Description |
|---|---|---|---|
| Paper lanterns | Session complete | 2.5s | 7 soft glowing circles rise with buoyancy + wind physics. Colors from mastery palette. |
| Ink bloom | Correct answer | 0.6s | Radial ink wash expanding from the answer element. Uses `--color-correct`. |

Both are `aria-hidden="true"`, `pointer-events: none`, `position: fixed`, `z-index: 9997-9998`. Skipped entirely under `prefers-reduced-motion`.

### 3.3 Scroll Engine (`scroll-engine.js`)

Continuous scroll-position-based animation system. Replaces binary IntersectionObserver with a 0-to-1 progress value per `[data-scroll-section]`.

- Sets `--scroll-progress` CSS custom property on each section
- Drives `AeluScene.setScrollProgress()` for WebGL integration
- Supports pinned sections via `data-scroll-pin`
- Public API: `AeluScroll.onProgress(name, cb)`, `.getProgress(name)`, `.scrollTo(name)`, `.scrollDriven(name, from, to)`
- Uses passive scroll listener + requestAnimationFrame debounce
- Still computes progress under reduced motion (skips animations)

### 3.4 Visual Elevation (`visual-elevation.js`)

Three systems, all IntersectionObserver-based:

| System | Selector | Behavior |
|---|---|---|
| Heading reveals | `.heading-reveal` | Adds `.is-visible` on 30% intersection (one-shot) |
| Scroll reveals | `[data-reveal]`, `.stagger-children` | Adds `.is-revealed`; children get 80ms staggered delays |
| Parallax | `[data-parallax="0.1"]` | `translateY(scrollY * -speed)` on RAF (marketing only) |
| Text splitting | `[data-split-text]` | Wraps each char in a span with 30ms stagger delays |

Under `prefers-reduced-motion`: only heading reveals run (no scroll reveals, no parallax).

### 3.5 CSS Keyframe Animations

| Animation | Duration | Easing | Usage |
|---|---|---|---|
| `driftUp` | `0.3s` | `ease-upward` | Default entrance: 6px upward drift + fade |
| `gentleBloom` | `0.6-0.8s` | `ease-upward` | Dashboard hero, empty states: scale 0.92 to 1 + fade |
| `logoSettle` | `1s` | `ease-upward` | Logo mark: 4px drift + fade |
| `horizonDraw` | `0.8s` | `ease-upward` | Horizon line: width 0 to full + fade |
| `inkSettleScale` | `0.5s` | `ease-spring` | Correct answer character: scale pulse 1 -> 1.05 -> 1 |
| `inkUnderlineDraw` | `0.4s` | `ease-upward` | Correct answer underline: scaleX 0 to 1 |
| `inkSpread` | `0.3s` | `ease-upward` | Ink ripple behind correct answer |
| `scoreReveal` | `0.5-0.6s` | `ease-spring` | Session complete title: scale 0.8 to 1.05 to 1 |
| `pctSlideUp` | `0.5s` | `ease-upward` | Session complete percentage: 12px drift |
| `illustrationFloat` | `4s` | `ease-in-out` | Empty state: 6px vertical breathing loop |
| `shimmer` | `1.5s` | `ease-in-out` | Skeleton loading: horizontal gradient sweep |
| `pulse` | `0.8s` | `ease-default` | Status dot: opacity 1 to 0.3 loop |
| `slowReveal` | `1.2s` | `cubic-bezier(0.2,0,0.2,1)` | Dashboard illustration fade to 0.5 opacity |
| `drillExit` | `0.3s` | `ease-default` | Drill group exit: slide left + fade |

**Button press pattern:** `:active` scales to `0.95`, release springs back over `0.4s` via `ease-spring`. Hover lifts `translateY(-2px)` with `shadow-lg`.

---

## 4. Per-Page Patterns

### 4.1 Dashboard

- **Background:** WebGL `dashboard` scene (intensity 0.18, 24fps) or CSS gradient mesh fallback
- **Entrance:** `.dashboard-hero` uses `gentleBloom` (0.8s), stats row fades in at 0.92 opacity
- **Illustrations:** `.dashboard-illustration` fades to 0.5 opacity (0.85 for PNGs); dark mode inverts with `sepia(0.2) hue-rotate(180deg)` or uses `-dark.png` variant
- **Hero image:** mask-image gradient fading to transparent at bottom; `shadow-md`; dismissible with glass-backed close button
- **Stats:** horizontal scroll on mobile (mask-image fade hints), flex-wrap on desktop; hover lifts 2px with `shadow-lg`
- **Primary CTA:** `#btn-start` oversized (18px 48px padding, text-lg) as singular focal point
- **Illustrations:** `mix-blend-mode: multiply` (light) / `screen` (dark)

### 4.2 Session / Drills

- **Drill transitions:** `.drill-group.exiting` slides left via `drillExit` keyframe
- **Correct answer:** `.ink-settle` scales with spring easing; `::after` pseudo-element draws underline via `inkUnderlineDraw`; ink bloom canvas effect from `celebrations.js`
- **Incorrect answer:** no animation (warm brown color, not red alarm); Capacitor haptic `'incorrect'`
- **Session complete:** staggered reveal sequence -- title at 0.4s, score at 0.6s, percentage at 0.8s; paper lantern celebration; Capacitor haptic `'success'`
- **Accuracy bar:** animated fill via `fillAccuracy` keyframe
- **Input:** `#answer-input` gets min-height 44px (48px on touch devices); iOS font-size 16px to prevent zoom
- **Answer options:** `.btn-option` min-height 48px; stagger entrance via JS-set transition-delay
- **Capacitor:** haptic feedback for correct/incorrect/success

### 4.3 Reading

- **Opener:** `.reading-opener` with passage title, label, hint text; serif typography throughout
- **Word interaction:** `.reading-word` hover reveals gloss; `.gloss-active` shifts to accent color with underline; `.gloss-fading` transitions out
- **Blocks:** `.reading-block` with label, title, text sections; exposure/reread variants get distinct label colors
- **Navigation:** `.reading-nav` buttons stack full-width on mobile (min-height 48px)
- **Ruby text:** `ruby rt` for pinyin annotations above characters

### 4.4 Listening

- **Layout:** `.listening-header` with controls, `.listening-content` for passage/questions
- **Self-assessment:** `.listening-self-assess` with correct/incorrect result colors
- **Dictation area:** `.dictation-input` textarea with focus glow; `.dictation-diff` shows character-level diff (correct/wrong/missing with distinct colors)
- **Score display:** `.listening-score` for accuracy percentage

### 4.5 Grammar

Grammar content is rendered within the reading/session framework. No grammar-specific CSS classes; grammar drills use the standard drill UI (`.drill-group`, `.btn-option`, answer input).

### 4.6 Admin

- **Radius:** uses `admin-radius: 8px`
- **Background:** WebGL `admin` scene (intensity 0.12, 20fps) -- coolest, most restrained
- **Tables:** `.admin-table` with sticky header (`thead th` position: sticky), compact mobile sizing
- **Overall:** minimal decoration; data-dense layout

### 4.7 Marketing / Upgrade

- **Background:** WebGL `marketing` scene (intensity 0.32, 30fps) -- richest, highest fidelity
- **Parallax:** `[data-parallax]` elements on scroll (marketing pages only)
- **Scroll sections:** `[data-scroll-section]` with pinned animations via scroll engine
- **Text splitting:** `[data-split-text]` for staggered character reveals in hero headlines
- **Pricing:** `.upgrade-pricing` section; `.upgrade-cta` primary action button
- **Upgrade banner:** `.upgrade-banner-cta` with hover opacity

### 4.8 Onboarding

- **Wizard:** `.onboarding-wizard` fullscreen card; `.onboarding-wizard-card` centered content
- **Exit:** `.onboarding-exit` class for dismiss animation
- **Options:** `.onboarding-opt` for selection items; `.onboarding-back-btn` for navigation
- **Checklist:** `.onboarding-checklist` with `.onboarding-fade-out` dismiss transition
- **Dismiss button:** min-height 48px on touch devices

---

## 5. Dark Mode Architecture

Three layers, in cascade order:

### 5.1 OS-level (base)

```css
@media (prefers-color-scheme: dark) { :root { ... } }
```

Responds to system dark mode setting. Sets all `--color-*`, `--shadow-*`, `--glass-*`, and `--mesh-*` variables.

### 5.2 Time-of-day override

JavaScript in `app.js` sets `data-theme="dark"` or `data-theme="light"` on `<html>`:
- **Dark hours:** 7:00 PM (`DARK_START_HOUR = 19`) through 6:59 AM (`DARK_END_HOUR = 7`)
- Applied immediately on script load (before DOMContentLoaded) to prevent flash
- Sets `document.documentElement.style.backgroundColor` inline as an anti-flash measure
- Updates `<meta name="theme-color">` to match

CSS selectors `html[data-theme="dark"]` and `html[data-theme="light"]` are placed after the `@media` rule for cascade precedence. This means time-of-day overrides the OS setting.

### 5.3 High contrast layer

`html[data-contrast="high"]` layers on top of whichever light/dark theme is active. Deepens text colors, strengthens accent/semantic colors, and increases divider opacity. Both `html[data-contrast="high"]` (light) and `html[data-theme="dark"][data-contrast="high"]` (dark) variants are defined.

### 5.4 Dark mode illustration handling

- SVG illustrations: color inherits from `--color-text`; `mix-blend-mode: multiply` (light) / `normal` (dark)
- PNG illustrations: `mix-blend-mode: multiply` (light); dark mode applies `filter: invert(0.88) sepia(0.2) hue-rotate(180deg) brightness(0.9)` + `mix-blend-mode: screen`
- Dark-specific PNGs (filename contains `-dark.png`): no filter applied, used as-is

---

## 6. Platform Parity

### 6.1 Shared between Web / Flutter / Capacitor

| Aspect | How it is shared |
|---|---|
| Color tokens | `design-tokens.json` is the single source. CSS `:root` vars and Flutter `AeluColors` class both derive from it. |
| Spacing scale | 8-step scale identical across platforms. Flutter `AeluSpacing` maps 1:1 with CSS `--space-{n}`. |
| Shadow system | 6-level depth scale (xs through 2xl) replicated in Flutter `AeluTheme.shadowsLight` / `shadowsDark`. |
| Glass tokens | Same opacity values. CSS uses `color-mix()`, Flutter uses `withValues(alpha:)`. |
| Motion curves | Spring easing `cubic-bezier(0.34, 1.56, 0.64, 1)` defined in both CSS and Flutter (`AeluTheme.springCurve`). |
| Typography families | Same font stack priority. Flutter theme specifies Cormorant Garamond headings, Source Serif 4 body. |

### 6.2 Web-only

- WebGL atmosphere (Three.js gradient mesh shader)
- Scroll engine with `--scroll-progress` CSS custom properties
- Canvas-based celebrations (paper lanterns, ink bloom)
- Visual elevation (IntersectionObserver reveals, parallax)
- CSS gradient mesh fallback
- SVG fractal noise plaster texture
- `data-theme` time-of-day switching
- `data-contrast` high-contrast mode toggle

### 6.3 Flutter-only

- `BackdropFilter` for glass effects (native blur compositing)
- `AeluTheme.pressScale = 0.98` for button press (slightly different from web's `scale(0.95)`)
- Platform-specific radius: interactive elements use 12px (vs web's 6px `radius-lg` for buttons)
- Dialog radius: 16px (no web equivalent defined in tokens)
- Chip radius: 8px
- Mastery stage colors include additional stages (`masteryPassed`, `masterySeen`, `masteryUnseen`)

### 6.4 Capacitor (native shell)

- `CapacitorBridge.hapticFeedback('success' | 'correct' | 'incorrect' | 'light')` for tactile feedback
- Network status monitoring via `CapacitorBridge.onNetworkChange()` and `CapacitorBridge.isOnline()`
- Safe area insets handled via `env(safe-area-inset-top)` / `env(safe-area-inset-bottom)` in CSS
- Dark mode illustration switching: JS checks `data-theme` and swaps to `-dark.png` variants

---

## 7. Accessibility Commitments

### 7.1 Reduced Motion

**Global kill switch** (appears twice in CSS for specificity):
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

**Targeted overrides** for specific components:
- `.ink-settle`, `.ink-scatter`, `.drill-group.exiting`: `animation: none`
- `.complete-accuracy-fill`: instantly set to final width
- `.empty-state-illustration`: bloom only (no float loop)
- Scroll reveals (`[data-reveal]`, `[data-reveal-child]`): immediately visible, no transform/opacity transition
- Stagger children: all visible immediately
- WebGL atmosphere: exits early, CSS gradient fallback shown
- Celebrations (paper lanterns, ink bloom): skipped entirely
- Visual elevation parallax: skipped entirely
- Scroll engine: still computes progress values (data-driven features work), skips visual animations

### 7.2 Contrast Modes

- All text colors annotated with contrast ratios vs their backgrounds
- `--color-text-faint` meets 5.0:1 (AA large text) on light, 5.2:1 on dark
- `--color-text-faintest` meets 4.5:1 (AA small text) in both modes
- `--color-on-accent` (white on accent): 4.89:1 (AA large text only)
- High contrast mode (`data-contrast="high"`) available: deepens all text, strengthens semantic colors, increases divider visibility
- High contrast has both light and dark variants

### 7.3 Focus Management

- `*:focus-visible`: 2px solid accent outline, 2px offset
- `--focus-ring`: `0 0 0 3px accent @ 20% opacity` (box-shadow variant for inputs)
- Skip link: `.skip-link` positioned off-screen, appears on focus with accent background
- `#app:focus { outline: none }` to prevent outline on programmatic focus

### 7.4 Touch Targets

All interactive elements enforce Apple HIG minimum 44px:
- `.btn-primary`, `.btn-secondary`: `min-height: 44px; min-width: 44px`
- Answer input, select, toggle labels, nav buttons, shortcuts: `min-height: 44px`
- `.btn-option` (answer choices): `min-height: 48px`

On `(pointer: coarse)` (touch devices), targets increase:
- `.btn-shortcut`: 48px min-height/width
- `.btn-primary`, `.btn-secondary`: 48px min-height
- `#answer-input`: 48px min-height, `font-size: 18px` (16px minimum prevents iOS zoom)
- Export links, panel toggles, onboarding dismiss: 48px

### 7.5 Other

- `scrollbar-gutter: stable` prevents layout shift
- `-webkit-text-size-adjust: 100%` prevents iOS landscape font inflation
- `::selection` uses accent at 25% opacity
- Celebration canvases are `aria-hidden="true"`
- `scroll-behavior: auto` under reduced motion (instead of `smooth`)

---

## 8. Brand Constraints

What NOT to do when modifying this design system:

| Constraint | Rationale |
|---|---|
| No bouncing animations | Motion decelerates into rest. `ease-upward` and `ease-exit`, never `ease-in-out` bounce. |
| No decoration without function | Every visual element must serve information hierarchy or wayfinding. |
| No rounded corners on structural elements | `--radius: 0` is the default. Only cards (8px), buttons (6px), illustrations (12px) get radius. |
| No gradient text | Gradients are reserved for the background mesh. Text is solid color. |
| No visible card borders | `--color-border: transparent`. Depth is communicated via shadow, not stroke. |
| No praise inflation | No "Great job!", stars, confetti, streaks celebrated. Consecutive days are noted, not rewarded. |
| No gamification elements | No points, levels, leaderboards, badges, fire emojis. |
| No red for errors | Incorrect answers use warm brown (`#806058` / `#A8988E`), not red/alarm. |
| No blur during learning | `inkBlurPulse` was explicitly removed -- blurring content defocuses what the learner needs to read. |
| No widget-heavy dashboards | Information hierarchy lives in typography and spacing, not in cards/widgets. |
| Streak treatment: same as other stats | `.stat-streak .stat-value` uses `--color-text`, not accent or gold. |
| Sound above 500Hz only | UI frequencies must not conflict with Mandarin tonal F0 range (75-500Hz). |
| Sound master gain 0.06-0.08 | UI sounds should be felt more than heard. |
| Descending intervals for session sounds | Arriving, settling -- not ascending/energizing. |
